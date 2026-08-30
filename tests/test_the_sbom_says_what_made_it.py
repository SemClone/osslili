"""A CycloneDX SBOM names the tool that made it, and each licence once.

Two faults in one formatter, both visible to whoever reads the SBOM.

The tool version was the literal `"1.5.6"` in both the JSON and the XML
writer while the package had moved to 1.7.5. An SBOM records which tool made
it so a consumer can reason about what the scan could and could not detect,
and those are not the same scanner: 1.7.3 alone changed what is found for
GNU headers, Sleepycat and CECILL-2.1.

A `licenses` array listed one entry per *detection*, so a file matched by the
keyword tier and the regex tier appeared twice under one component. It is a
statement of what the component is under, not a log of how many times a
scanner noticed. The third-party path beside it already collapsed its
identifiers, which is why this reads as an omission rather than a choice.

Issue #132.
"""

import json
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from osslili import LicenseCopyrightDetector, __version__

BOM = "{http://cyclonedx.org/schema/bom/1.4}"

MIT_TEXT = (
    "MIT License\n\nCopyright (c) 2024 Acme Corporation\n\nPermission is "
    "hereby granted, free of charge, to any person obtaining a copy of this "
    'software and associated documentation files (the "Software"), to deal '
    "in the Software without restriction, including without limitation the "
    "rights to use, copy, modify, merge, publish, distribute, sublicense, "
    "and/or sell copies of the Software.\n"
)


@pytest.fixture
def detector():
    return LicenseCopyrightDetector()


@pytest.fixture
def results(detector):
    """A package whose licence more than one tier finds.

    That overlap is the whole point: one grant, several detections, and the
    duplicate only appears when a licence is reached more than one way.
    """
    root = Path(tempfile.mkdtemp())
    (root / "LICENSE").write_text(MIT_TEXT)
    (root / "README.md").write_text("# Widget\n\nLicensed under the MIT license.\n")
    return [detector.process_local_path(str(root))]


class TestTheToolVersion:
    def test_the_json_names_the_running_version(self, detector, results):
        sbom = json.loads(detector.generate_cyclonedx(results, format_type="json"))

        assert sbom["metadata"]["tools"][0]["version"] == __version__

    def test_the_xml_names_the_running_version(self, detector, results):
        root = ET.fromstring(detector.generate_cyclonedx(results, format_type="xml"))

        found = root.find(f"{BOM}metadata/{BOM}tools/{BOM}tool/{BOM}version")
        assert found is not None
        assert found.text == __version__

    def test_it_is_not_restated(self):
        """The version is read, not written down a second time.

        A literal is what let the two drift three releases apart.
        """
        source = Path(__file__).resolve().parents[1] / (
            "osslili/formatters/cyclonedx_formatter.py"
        )
        body = source.read_text()

        assert "1.5.6" not in body
        assert "__version__" in body


class TestALicenceIsListedOnce:
    def test_more_than_one_tier_finds_the_licence(self, detector, results):
        """The premise: without the overlap this proves nothing."""
        found = [license.spdx_id for license in results[0].get_own_licenses()]

        assert found.count("MIT") > 1, f"expected a repeated detection, got {found}"

    def test_the_json_lists_each_licence_once(self, detector, results):
        sbom = json.loads(detector.generate_cyclonedx(results, format_type="json"))

        for component in sbom["components"]:
            listed = [
                entry["license"]["id"] for entry in component.get("licenses", [])
            ]
            assert len(listed) == len(set(listed)), listed

    def test_the_xml_lists_each_licence_once(self, detector, results):
        root = ET.fromstring(detector.generate_cyclonedx(results, format_type="xml"))

        for component in root.iter(f"{BOM}component"):
            listed = [
                element.text
                for element in component.iter(f"{BOM}id")
            ]
            assert len(listed) == len(set(listed)), listed

    def test_the_licence_is_still_reported(self, detector, results):
        """Collapsing duplicates must not lose the grant itself."""
        sbom = json.loads(detector.generate_cyclonedx(results, format_type="json"))

        listed = {
            entry["license"]["id"]
            for component in sbom["components"]
            for entry in component.get("licenses", [])
        }
        assert "MIT" in listed

    def test_two_renders_agree(self, detector, results):
        """Sorted, so the same scan does not render two ways (cf. #123)."""
        first = json.loads(detector.generate_cyclonedx(results, format_type="json"))
        second = json.loads(detector.generate_cyclonedx(results, format_type="json"))

        def licences(sbom):
            return [component.get("licenses") for component in sbom["components"]]

        assert licences(first) == licences(second)
