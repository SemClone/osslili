"""Tests for third-party notice categorization (issue #78).

Bundled third-party notice/license files are dependency licenses, not the
project's own license. They must still be detected and reported, but tagged
with the THIRD_PARTY category so consumers determining the project's own
license in isolation can filter them out.
"""

from pathlib import Path

import pytest

import json

from osslili.core.models import (
    Config,
    DetectedLicense,
    DetectionResult,
    LicenseCategory,
)
from osslili.detectors.license_detector import LicenseDetector
from osslili.formatters.cyclonedx_formatter import CycloneDXFormatter
from osslili.formatters.kissbom_formatter import KissBOMFormatter


@pytest.fixture
def detector():
    return LicenseDetector(Config())


@pytest.mark.parametrize(
    "filename",
    [
        "THIRD_PARTY_NOTICES.txt",
        "THIRD_PARTY_NOTICES",
        "third-party-licenses.md",
        "ThirdPartyNotices.txt",
        "3rdpartylicenses.txt",
        "3rd-party-notices.txt",
    ],
)
def test_third_party_notice_files_are_recognized(detector, filename):
    assert detector._is_third_party_notice_file(Path(filename)) is True


@pytest.mark.parametrize(
    "filename",
    [
        "LICENSE",
        "LICENSE.txt",
        "COPYING",
        "NOTICE",
        "README.md",
        "COPYRIGHT",
        # marker present but no notice/license token -> ordinary source file
        "third_party_helpers.py",
        "thirdparty_adapter.js",
        "my-third-party-api.md",
    ],
)
def test_project_license_files_are_not_third_party(detector, filename):
    assert detector._is_third_party_notice_file(Path(filename)) is False


def _lic(spdx_id, category, confidence=0.9):
    return DetectedLicense(
        spdx_id=spdx_id,
        name=spdx_id,
        confidence=confidence,
        detection_method="regex",
        source_file="THIRD_PARTY_NOTICES.txt",
        category=category,
    )


def test_get_own_and_third_party_licenses_split():
    result = DetectionResult(
        path="/proj",
        licenses=[
            _lic("MIT", LicenseCategory.DECLARED.value),
            _lic("Apache-2.0", LicenseCategory.THIRD_PARTY.value),
            _lic("BSD-3-Clause", LicenseCategory.THIRD_PARTY.value),
        ],
    )
    assert [l.spdx_id for l in result.get_own_licenses()] == ["MIT"]
    assert sorted(l.spdx_id for l in result.get_third_party_licenses()) == [
        "Apache-2.0",
        "BSD-3-Clause",
    ]


def test_primary_license_ignores_third_party_even_at_higher_confidence():
    result = DetectionResult(
        path="/proj",
        licenses=[
            _lic("MIT", LicenseCategory.DECLARED.value, confidence=0.5),
            _lic("GPL-3.0-only", LicenseCategory.THIRD_PARTY.value, confidence=0.99),
        ],
    )
    assert result.get_primary_license().spdx_id == "MIT"


def test_primary_license_is_none_when_only_third_party():
    """Third-party notices are never promoted to the project's primary license."""
    result = DetectionResult(
        path="/proj",
        licenses=[_lic("GPL-3.0-only", LicenseCategory.THIRD_PARTY.value)],
    )
    assert result.get_primary_license() is None


def test_kissbom_third_party_only_does_not_contaminate_license():
    result = DetectionResult(
        path="/proj",
        licenses=[_lic("GPL-3.0-only", LicenseCategory.THIRD_PARTY.value)],
    )
    pkg = json.loads(KissBOMFormatter().format([result]))["packages"][0]
    assert pkg["license"] == "NO-ASSERTION"
    assert pkg["third_party_licenses"] == ["GPL-3.0-only"]


def test_kissbom_separates_third_party():
    result = DetectionResult(
        path="/proj",
        licenses=[
            _lic("MIT", LicenseCategory.DECLARED.value, confidence=0.9),
            _lic("Apache-2.0", LicenseCategory.DETECTED.value, confidence=0.8),
            _lic("GPL-3.0-only", LicenseCategory.THIRD_PARTY.value, confidence=0.99),
        ],
    )
    out = json.loads(KissBOMFormatter().format([result]))
    pkg = out["packages"][0]
    assert pkg["license"] == "MIT"  # never the third-party GPL
    assert "GPL-3.0-only" not in pkg.get("all_licenses", [])
    assert pkg["third_party_licenses"] == ["GPL-3.0-only"]


def test_cyclonedx_emits_third_party_as_properties_not_licenses():
    result = DetectionResult(
        path="/proj",
        licenses=[
            _lic("MIT", LicenseCategory.DECLARED.value),
            _lic("GPL-3.0-only", LicenseCategory.THIRD_PARTY.value),
        ],
    )
    out = json.loads(CycloneDXFormatter().format([result], "json"))
    comp = out["components"][0]
    license_ids = {entry["license"]["id"] for entry in comp["licenses"]}
    assert license_ids == {"MIT"}
    prop_values = {p["value"] for p in comp.get("properties", [])}
    assert prop_values == {"GPL-3.0-only"}


def test_cyclonedx_xml_is_wellformed_and_orders_copyright_before_properties():
    import xml.etree.ElementTree as ET

    result = DetectionResult(
        path="/proj",
        licenses=[
            _lic("MIT", LicenseCategory.DECLARED.value),
            _lic("GPL-3.0-only", LicenseCategory.THIRD_PARTY.value),
        ],
    )
    from osslili.core.models import CopyrightInfo

    result.copyrights = [CopyrightInfo(holder="ACME", statement="Copyright ACME")]
    xml = CycloneDXFormatter().format([result], "xml")
    root = ET.fromstring(xml)  # raises if malformed

    ns = {"c": "http://cyclonedx.org/schema/bom/1.4"}
    component = root.find(".//c:component", ns)
    child_tags = [child.tag.split("}")[-1] for child in component]
    assert "copyright" in child_tags and "properties" in child_tags
    assert child_tags.index("copyright") < child_tags.index("properties")


def test_categorize_tags_third_party_notice(detector):
    category, match_type = detector._categorize_license(
        Path("THIRD_PARTY_NOTICES.txt"), "regex", None
    )
    assert category == LicenseCategory.THIRD_PARTY.value
    assert match_type == "third_party_notice"


def test_categorize_keeps_project_license_declared(detector):
    category, _ = detector._categorize_license(Path("LICENSE"), "regex", None)
    assert category == LicenseCategory.DECLARED.value


def test_third_party_licenses_still_detected(detector, tmp_path):
    """A third-party notices file must still surface its licenses, just tagged."""
    third_party = tmp_path / "THIRD_PARTY_NOTICES.txt"
    third_party.write_text(
        "This product bundles the following components:\n\n"
        "SPDX-License-Identifier: MIT\n"
        "SPDX-License-Identifier: Apache-2.0\n"
    )

    results = detector.detect_licenses(third_party)

    assert results, "third-party notices should still be detected"
    spdx_ids = {r.spdx_id for r in results}
    assert spdx_ids & {"MIT", "Apache-2.0"}
    # Every finding sourced from the notices file is tagged THIRD_PARTY.
    assert all(
        r.category == LicenseCategory.THIRD_PARTY.value for r in results
    ), [r.category for r in results]


def test_project_license_detected_as_declared(detector, tmp_path):
    """A normal project LICENSE must not be tagged third-party."""
    lic = tmp_path / "LICENSE"
    lic.write_text("SPDX-License-Identifier: MIT\n")

    results = detector.detect_licenses(lic)

    assert results
    assert all(r.category != LicenseCategory.THIRD_PARTY.value for r in results)
