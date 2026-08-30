"""A deprecated identifier is modernised whichever entry point read it.

A scan modernised the identifiers it emitted; `extract_package_metadata()`
reached the reader directly and did not, so one manifest gave two answers:

    through a scan                      GPL-2.0-only
    through extract_package_metadata()  GPL-2.0

`GPL-2.0` is deprecated in SPDX precisely because it does not say whether
later versions are permitted, so which form is reported is a difference a
consumer cares about, and the deprecated spelling answers neither. Issue
#112.

What the two entry points deliberately do *not* share is what a scan decides
after the identifier is settled. `detect_licenses` drops identifiers outside
the SPDX list, deduplicates, and re-tags third-party notices; those are
decisions about what a *scan* reports. Metadata extraction has not asked for
them, and the drop in particular would turn a declared `Proprietary` into no
licence at all — which reads as "nothing declared", the opposite conclusion,
and a worse failure than the deprecated identifier this is about.
"""

import tempfile
from pathlib import Path

import pytest

from osslili import LicenseCopyrightDetector


# The GNU family, because that is the whole of what SPDX deprecated: the bare
# form says nothing about later versions and the plus form says the opposite
# of the -only it used to collapse into.
DEPRECATED = [
    ("GPL-2.0", "GPL-2.0-only"),
    ("GPL-3.0", "GPL-3.0-only"),
    ("LGPL-2.1", "LGPL-2.1-only"),
    ("AGPL-3.0", "AGPL-3.0-only"),
    ("GPL-2.0+", "GPL-2.0-or-later"),
    ("GPL-3.0+", "GPL-3.0-or-later"),
    ("LGPL-2.1+", "LGPL-2.1-or-later"),
]

# Identifiers that were never deprecated must come back untouched.
ALREADY_MODERN = ["MIT", "Apache-2.0", "BSD-3-Clause", "ISC", "GPL-2.0-only"]


@pytest.fixture
def detector():
    return LicenseCopyrightDetector()


def _a_package(declaring):
    """A directory whose pyproject.toml declares `declaring`."""
    root = Path(tempfile.mkdtemp())
    (root / "pyproject.toml").write_text(
        f'[project]\nname = "widget"\nversion = "1.0"\nlicense = "{declaring}"\n'
    )
    return root


def _through_metadata(detector, root):
    return [license.spdx_id for license in detector.extract_package_metadata(str(root)).licenses]


def _through_a_scan(detector, root):
    return [license.spdx_id for license in detector.process_local_path(str(root)).licenses]


class TestTheDeprecatedFormIsModernised:
    @pytest.mark.parametrize("declared,modern", DEPRECATED)
    def test_metadata_extraction_reports_the_modern_identifier(
        self, detector, declared, modern
    ):
        assert _through_metadata(detector, _a_package(declared)) == [modern]

    @pytest.mark.parametrize("declared,modern", DEPRECATED)
    def test_a_scan_reports_the_same_identifier(self, detector, declared, modern):
        assert set(_through_a_scan(detector, _a_package(declared))) == {modern}


class TestTheTwoEntryPointsAgree:
    @pytest.mark.parametrize("declared,_modern", DEPRECATED)
    def test_one_manifest_gives_one_answer(self, detector, declared, _modern):
        """The fault: the same input answered differently by entry point."""
        root = _a_package(declared)

        assert set(_through_metadata(detector, root)) == set(
            _through_a_scan(detector, root)
        )

    @pytest.mark.parametrize("declared", ALREADY_MODERN)
    def test_an_identifier_that_was_never_deprecated_is_untouched(
        self, detector, declared
    ):
        root = _a_package(declared)

        assert _through_metadata(detector, root) == [declared]
        assert set(_through_a_scan(detector, root)) == {declared}


class TestAScanDecidesMoreThanTheIdentifier:
    """Only the modernisation is shared. The rest belongs to a scan."""

    def test_metadata_extraction_still_reports_a_non_spdx_declaration(self, detector):
        """A caller looking for proprietary packages must still find them.

        `detect_licenses` drops identifiers outside the SPDX list. Applying
        that here would answer with an empty list for a package that plainly
        declares something, and an empty list reads as "nothing declared".
        """
        root = _a_package("Proprietary")

        assert _through_metadata(detector, root) == ["Proprietary"]
        assert _through_a_scan(detector, root) == []

    def test_metadata_extraction_does_not_deduplicate_across_files(self, detector):
        """Two manifests declaring the same licence are two declarations.

        A scan collapses them; this entry point reports what each file said,
        which is what a caller reading manifests is asking for.
        """
        root = Path(tempfile.mkdtemp())
        (root / "pyproject.toml").write_text(
            '[project]\nname = "widget"\nversion = "1.0"\nlicense = "GPL-2.0"\n'
        )
        (root / "setup.cfg").write_text("[metadata]\nname = widget\nlicense = GPL-2.0\n")

        found = detector.extract_package_metadata(str(root)).licenses

        assert [license.spdx_id for license in found] == ["GPL-2.0-only"] * 2
        assert len({license.source_file for license in found}) == 2


class TestTheModernisationIsOneFunction:
    """A third entry point should not be able to miss it."""

    def test_the_boundary_is_callable_on_its_own(self, detector):
        from osslili.core.models import DetectedLicense

        license = DetectedLicense(spdx_id="GPL-2.0+", name="whatever")

        returned = detector.license_detector.modernise_identifier(license)

        assert returned.spdx_id == "GPL-2.0-or-later"
        assert returned is license, "the licence is modernised in place"
