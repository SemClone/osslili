"""A version written as v3 rather than 3.0 still has to name a licence.

The step that reads a version out of a vague licence name wrote it back
exactly as it found it, and a licence is written "v3" as often as "3.0". Only
the second is part of an identifier, so the step answered with strings that
name nothing:

    _handle_version_patterns("gplv3")        -> "GPL-v3"
    _handle_version_patterns("affero gplv3") -> "AGPL-v3"

It then returned, so the later steps that could have reached a real
identifier never ran. Some inputs were rescued by an alias further along and
some were not, and the ones that were not were lost in silence:

    {"license": "GPLv3"}         ->  GPL-3.0-only
    {"license": "Affero GPLv3"}  ->  nothing
    {"license": "Lesser GPLv3"}  ->  nothing
    {"license": "LGPLv2.1"}      ->  nothing

Issue #125. Two things were needed and neither was the whole answer on its
own: the version has to be spelled the way an identifier spells it, and the
answer has to be checked against the SPDX list so a guess that names nothing
falls through instead of stopping the search.

The spellings are also tried longest first. "gplv2.1" contains "v2" as well
as "2.1", and answering on the first found turned LGPL-2.1 into LGPL-2.0,
which is a different licence rather than a different spelling of one.

## What this deliberately leaves alone

A line carrying a grant in words. "GPL-2.0 or later" and "Apache 2.0 or
above" are read by the expression reader, whose answers rest on what this
step returns, and #120 and #127 settled them at length. This issue is about a
bare name that resolves to nothing, so that is all that changed.
"""

import tempfile
from pathlib import Path

import pytest

from osslili import LicenseCopyrightDetector
from osslili.utils.license_normalizer import LicenseNormalizer


@pytest.fixture(scope="module")
def normalizer():
    return LicenseNormalizer()


@pytest.fixture(scope="module")
def detector():
    return LicenseCopyrightDetector()


def _a_package_declaring(value):
    root = Path(tempfile.mkdtemp())
    (root / "pyproject.toml").write_text(
        f'[project]\nname = "widget"\nversion = "1.0"\nlicense = "{value}"\n'
    )
    return root


class TestAVagueNameReachesAnIdentifier:
    @pytest.mark.parametrize(
        "written,expected",
        [
            ("GPLv3", "GPL-3.0"),
            ("Affero GPLv3", "AGPL-3.0"),
            ("Lesser GPLv3", "LGPL-3.0"),
            ("LGPLv2.1", "LGPL-2.1"),
            ("Apache 2.0", "Apache-2.0"),
        ],
    )
    def test_the_version_is_spelled_the_way_an_identifier_spells_it(
        self, normalizer, written, expected
    ):
        assert normalizer.normalize_license_id(written) == expected

    @pytest.mark.parametrize(
        "written", ["GPLv3", "Affero GPLv3", "Lesser GPLv3", "LGPLv2.1"]
    )
    def test_the_answer_names_a_real_licence(self, normalizer, written):
        """`AGPL-v3` is not an identifier, and answering it stopped the search."""
        from osslili.core.models import Config

        answer = normalizer.normalize_license_id(written)
        listed = set(
            LicenseCopyrightDetector().license_detector.spdx_data.get_all_license_ids()
        )
        bare = answer.rstrip("+")
        assert (
            bare in listed
            or f"{bare}-only" in listed
            or f"{bare}-or-later" in listed
        ), answer


class TestTheLicenceIsNoLongerLostInSilence:
    """The fault as a consumer met it: a package declaring a licence, and a
    scan reporting nothing at all."""

    @pytest.mark.parametrize(
        "declared,expected",
        [
            ("GPLv3", "GPL-3.0-only"),
            ("Affero GPLv3", "AGPL-3.0-only"),
            ("Lesser GPLv3", "LGPL-3.0-only"),
            ("LGPLv2.1", "LGPL-2.1-only"),
        ],
    )
    def test_a_package_declaring_it_reports_it(self, detector, declared, expected):
        found = {
            lic.spdx_id
            for lic in detector.process_local_path(str(_a_package_declaring(declared))).licenses
        }

        assert expected in found, found


class TestTheLongestSpellingWins:
    def test_two_point_one_is_not_two(self, normalizer):
        """"gplv2.1" holds "v2" as well as "2.1", and LGPL-2.0 is not LGPL-2.1."""
        assert normalizer.normalize_license_id("lesser gplv2.1") == "LGPL-2.1"
        assert normalizer.normalize_license_id("LGPLv2.1") == "LGPL-2.1"

    def test_a_version_with_no_point_still_reads(self, normalizer):
        assert normalizer.normalize_license_id("library gplv2") == "LGPL-2.0"


class TestAGrantInWordsIsLeftToTheExpressionReader:
    """#120 and #127 settled these, and they are not this issue's business."""

    @pytest.mark.parametrize(
        "written,expected",
        [
            ("GPL-2.0 or later", "GPL-2.0-or-later"),
            ("GPL version 3 or later", "GPL-3.0-or-later"),
            ("Apache 2.0 or above", "Apache-2.0"),
        ],
    )
    def test_the_reported_licence_is_unchanged(self, detector, written, expected):
        root = Path(tempfile.mkdtemp())
        (root / "widget.c").write_text(f"// Licensed under {written}.\n")

        found = {
            lic.spdx_id
            for lic in detector.license_detector.detect_licenses(root / "widget.c")
        }

        assert expected in found, found

    def test_the_or_later_grant_is_not_inverted(self, detector):
        """The contradiction this issue was blocked on.

        Resolving these values used to reach a reader with no or-later
        context, and "GPL version 3 or later" came back as GPL-3.0-only
        beside the correct GPL-3.0-or-later: one statement, two contradictory
        grants. #120 and #127 settled it, and it must stay settled.
        """
        root = Path(tempfile.mkdtemp())
        (root / "widget.c").write_text("// Licensed under GPL version 3 or later.\n")

        found = {
            lic.spdx_id
            for lic in detector.license_detector.detect_licenses(root / "widget.c")
        }

        assert "GPL-3.0-or-later" in found, found
        assert "GPL-3.0-only" not in found, found
