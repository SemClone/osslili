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


class TestTheLettersAfterCCBYAreTheLicence:
    """NonCommercial and NoDerivatives are obligations and ShareAlike is
    copyleft, so answering plain CC-BY for any of them says the work carries
    none of that.

    Every `CC BY` variant collapsed to `CC-BY`, which with the old version
    spelling made `CC-BY-v3`: an identifier that names nothing, so it was
    dropped and the licence went missing. Checking the answer would have
    turned that into a confident wrong one, which is worse, so the variant is
    kept instead.
    """

    @pytest.mark.parametrize(
        "written,expected",
        [
            ("CC BY-SA 3.0", "CC-BY-SA-3.0"),
            ("CC BY-SA v3", "CC-BY-SA-3.0"),
            # No plus: SPDX writes no or-later form for CC-BY-SA, so the
            # grant cannot be carried and the licence is reported without it,
            # exactly as for Apache.
            ("CC BY-SA v3 or later", "CC-BY-SA-3.0"),
            ("CC BY-NC 3.0", "CC-BY-NC-3.0"),
            ("CC BY-ND 3.0", "CC-BY-ND-3.0"),
            ("CC BY-NC-SA 3.0", "CC-BY-NC-SA-3.0"),
            ("CC BY-NC-ND 3.0", "CC-BY-NC-ND-3.0"),
            ("CC BY 3.0", "CC-BY-3.0"),
        ],
    )
    def test_the_variant_survives(self, normalizer, written, expected):
        assert normalizer.normalize_license_id(written) == expected

    @pytest.mark.parametrize(
        "written,expected",
        [
            ("CC BY NC SA 3.0", "CC-BY-NC-SA-3.0"),
            ("CC BY NC ND 3.0", "CC-BY-NC-ND-3.0"),
        ],
    )
    def test_the_terms_are_read_apart_as_well_as_joined(
        self, normalizer, written, expected
    ):
        """One licence, written two ways. Matching only the hyphenated
        spelling read the second as CC-BY-NC and lost the other term."""
        assert normalizer.normalize_license_id(written) == expected

    @pytest.mark.parametrize(
        "written,expected",
        [
            ("CC BY-SA3.0", "CC-BY-SA-3.0"),
            ("CC BY-NC-SA3.0", "CC-BY-NC-SA-3.0"),
        ],
    )
    def test_a_version_arriving_without_a_separator(self, normalizer, written, expected):
        """A digit after a term is the version, not the end of a word."""
        assert normalizer.normalize_license_id(written) == expected

    def test_a_term_inside_an_ordinal_is_not_a_term(self, normalizer):
        """"2nd" holds "nd", and reading that as NoDerivatives puts an
        obligation on a licence that has none."""
        assert normalizer.normalize_license_id("CC BY 3.0 2nd edition") == "CC-BY-3.0"

    def test_it_reaches_the_report(self, detector):
        found = {
            lic.spdx_id
            for lic in detector.process_local_path(
                str(_a_package_declaring("CC BY-SA 3.0"))
            ).licenses
        }

        assert "CC-BY-SA-3.0" in found, found
        assert "CC-BY-3.0" not in found, found


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
