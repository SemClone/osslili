"""A licence word in a document is a mention until something agrees.

The keyword tier matches single words and short names, so it reported the
JSON licence for the word "JSON" in a changelog and 0BSD for "0BSD" in a
README, in packages that are BSD-3-Clause and MIT. Over 13 real packages from
PyPI every licence it found on its own was wrong, and every licence it found
that was right had already been read from a declaration or a licence file.

Issue #138, the second half of #126. It waited for the first half: while most
of the SPDX list shipped no text, the keyword tier was sometimes the only
reader there was, and dropping it would have turned a wrong answer into no
answer.

## What is deliberately kept

Not every keyword match is noise, and the rule is narrower than "drop
uncorroborated keyword matches" because that loses real grants:

- a bare licence word in a *licence file* is very often the grant itself,
  "distributed under the terms of the GNU GPL version 2" in a COPYING, and no
  other tier reads it
- a README can state a grant the same way, "licensed under GPL2", and nothing
  else reads that either

What separates those from the JSON changelog is that the package has already
said what it is licensed under. An extra licence appearing only as a word in
prose, in a package whose licence is established, is noise. The same word in
a package with nothing else to go on is the only answer there is.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from osslili import LicenseCopyrightDetector

REPO_ROOT = Path(__file__).resolve().parents[1]

MIT_TEXT = (
    "MIT License\n\nCopyright (c) 2024 Acme Corporation\n\nPermission is "
    "hereby granted, free of charge, to any person obtaining a copy of this "
    'software and associated documentation files (the "Software"), to deal '
    "in the Software without restriction, including without limitation the "
    "rights to use, copy, modify, merge, publish, distribute, sublicense, "
    "and/or sell copies of the Software.\n"
)


def _scan(target):
    finished = subprocess.run(
        [sys.executable, "-m", "osslili", "-f", "evidence", str(target)],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert finished.returncode == 0, finished.stderr
    return json.loads(finished.stdout[finished.stdout.index("{"):])


def _licences(report):
    return {
        e["detected_license"]
        for scanned in report["scan_results"]
        for e in scanned.get("license_evidence", [])
    }


class TestAWordInProseIsNotALicence:
    """The three false positives measured over real packages."""

    # Real changelog prose from Flask, reduced to the smallest window that
    # still made the keyword tier report the JSON licence. Flask is
    # BSD-3-Clause; this is a sentence about character encoding.
    A_CHANGELOG_ABOUT_JSON = (
        "Changelog\n=========\n\n"
        "-   ``Request.get_json`` no longer accepts arbitrary encodings. Incoming\n"
        "    JSON should be encoded using UTF-8 per :rfc:`8259`, but Flask will\n"
        "    autodetect UTF-16 and UTF-32.\n"
    )

    def _a_package_whose_changelog_talks_about_json(self):
        root = Path(tempfile.mkdtemp())
        (root / "LICENSE").write_text(MIT_TEXT)
        (root / "CHANGES.rst").write_text(self.A_CHANGELOG_ABOUT_JSON)
        return root

    def test_the_keyword_tier_really_does_read_it_as_a_licence(self):
        """The premise. Without this the rest proves nothing."""
        detector = LicenseCopyrightDetector().license_detector

        found = detector._detect_license_keywords(
            self.A_CHANGELOG_ABOUT_JSON, Path("CHANGES.rst")
        )

        assert "JSON" in {lic.spdx_id for lic in found}

    def test_it_is_not_reported_as_a_licence(self):
        root = self._a_package_whose_changelog_talks_about_json()

        found = _licences(_scan(root))

        assert "MIT" in found, found
        assert "JSON" not in found, found

    def test_the_package_licence_is_untouched(self):
        root = self._a_package_whose_changelog_talks_about_json()

        assert _licences(_scan(root)) == {"MIT"}


class TestAWordInARecognisedLicenceFile:
    """Once a licence file's text is recognised, a word in it is a word.

    The OFL says "Permission is hereby granted, free of charge", which is
    MIT's phrasing, so scanning an OFL font licence reported MIT beside it.
    The AGPL names the GPL and reported that. Measured over all 737 bundled
    texts, 82 of them reported a licence they merely mention.
    """

    def _a_package_licensed_under(self, spdx_id):
        detector = LicenseCopyrightDetector()
        root = Path(tempfile.mkdtemp())
        (root / "LICENSE").write_text(
            detector.license_detector.spdx_data.get_license_text(spdx_id) or ""
        )
        return root

    @pytest.mark.parametrize(
        "spdx_id,merely_mentioned",
        [("OFL-1.1", "MIT"), ("AGPL-3.0-only", "GPL-3.0-only")],
    )
    def test_a_licence_it_only_mentions_is_not_reported(
        self, spdx_id, merely_mentioned
    ):
        found = _licences(_scan(self._a_package_licensed_under(spdx_id)))

        assert spdx_id in found, found
        assert merely_mentioned not in found, found

    def test_the_licence_itself_is_untouched(self):
        assert _licences(_scan(self._a_package_licensed_under("OFL-1.1"))) == {
            "OFL-1.1"
        }

    def test_a_manifest_never_counts_as_recognised(self):
        """PEP 639 attributes a referenced file's match to the manifest.

        `license = {file = "LICENSE"}` resolves the file and records the match
        against `pyproject.toml`, so the manifest carried an exact hash for
        text that is not in it. Treating that as "this file has spoken" threw
        away a second grant written there in words.
        """
        detector = LicenseCopyrightDetector()
        root = Path(tempfile.mkdtemp())
        (root / "LICENSE").write_text(
            detector.license_detector.spdx_data.get_license_text("MIT") or ""
        )
        (root / "pyproject.toml").write_text(
            '[project]\nname = "x"\nversion = "0.1.0"\n'
            'license = { file = "LICENSE" }\n'
            "# This package is also distributed under the terms of the GNU GPL "
            "version 2.\n"
        )

        found = _licences(_scan(root))

        assert "MIT" in found, found
        assert "GPL-2.0-only" in found, found

    def test_a_manifest_stays_a_manifest_however_it_is_configured(self):
        """`license_filename_patterns` is the caller's to widen.

        A pattern covering `pyproject.toml` would otherwise let the manifest
        count as a recognised licence file and take the grant away again.
        """
        from osslili.core.models import Config

        config = Config()
        config.license_filename_patterns = config.license_filename_patterns + [
            "pyproject.toml"
        ]
        detector = LicenseCopyrightDetector(config)
        root = Path(tempfile.mkdtemp())
        (root / "LICENSE").write_text(
            detector.license_detector.spdx_data.get_license_text("MIT") or ""
        )
        (root / "pyproject.toml").write_text(
            '[project]\nname = "x"\nversion = "0.1.0"\n'
            'license = { file = "LICENSE" }\n'
            "# This package is also distributed under the terms of the GNU GPL "
            "version 2.\n"
        )

        found = {lic.spdx_id for lic in detector.process_local_path(str(root)).licenses}

        assert {"MIT", "GPL-2.0-only"} <= found, found


class TestAGrantIsKeptWhereverItIsStated:
    """The rule must not cost a grant the keyword tier alone can read."""

    def test_a_licence_file_saying_it_in_words(self):
        """No other tier reads "the terms of the GNU GPL version 2"."""
        root = Path(tempfile.mkdtemp())
        (root / "COPYING").write_text(
            "This program is distributed under the terms of the GNU GPL version 2.\n"
        )

        found = _licences(_scan(root))

        assert any(lic.startswith("GPL-2.0") for lic in found), found

    def test_a_readme_that_is_the_only_thing_there(self):
        """A package with nothing else to go on keeps its one answer."""
        root = Path(tempfile.mkdtemp())
        (root / "README.md").write_text("This project is licensed under GPL2.\n")

        found = _licences(_scan(root))

        assert any(lic.startswith("GPL-2.0") for lic in found), found

    def test_a_readme_naming_the_licence_the_package_states(self):
        """Corroboration is asked of the scan, not of one file."""
        root = Path(tempfile.mkdtemp())
        (root / "LICENSE").write_text(MIT_TEXT)
        (root / "README.md").write_text("# widget\n\nReleased under the MIT license.\n")

        assert _licences(_scan(root)) == {"MIT"}


class TestAStatedLicenceWinsOverAGuess:
    """A file that states its licence has answered the question.

    With every licence text bundled (#126) the near neighbours are all present
    to be guessed at: a LICENSE stating Python-2.0 also scored 0.961 against
    Python-2.0.1, the same licence one revision apart, and both were reported.
    This is what #108 settled for normalisation, applied to the tiers.
    """

    # The licence file typing_extensions ships: the PSF stack, which states
    # Python-2.0 and is a variant of it rather than the canonical text, so it
    # misses the exact hash and reaches the similarity tier. The canonical
    # text does not reproduce this, because it matches exactly and never gets
    # that far.
    PSF_STACK = (
        Path(__file__).parent / "fixtures" / "psf_licence_stack.txt"
    ).read_text()

    def test_the_file_really_does_state_its_licence(self):
        """The premise: a tag at 1.0 is what the rule keys on."""
        detector = LicenseCopyrightDetector().license_detector
        root = Path(tempfile.mkdtemp())
        target = root / "LICENSE"
        target.write_text(self.PSF_STACK)

        stated = [
            lic for lic in detector.detect_licenses(target)
            if lic.detection_method == "tag" and lic.confidence >= 1.0
        ]
        assert stated, "the fixture must state a licence for this rule to apply"
        assert stated[0].spdx_id == "Python-2.0"

    def test_a_near_neighbour_is_not_reported_beside_it(self):
        root = Path(tempfile.mkdtemp())
        (root / "LICENSE").write_text(self.PSF_STACK)

        found = _licences(_scan(root))

        assert "Python-2.0" in found, found
        assert "Python-2.0.1" not in found, found

    def test_a_second_licence_the_file_really_offers_is_kept(self):
        """Only a near miss at the stated licence is dropped.

        A file may state one licence and carry the text of a second, and that
        second one is a licence the file really does offer rather than a
        guess at the first. Dropping every score on a file that states
        anything would lose it, which is worse than the duplicate this rule
        exists to remove.
        """
        detector = LicenseCopyrightDetector()
        root = Path(tempfile.mkdtemp())
        (root / "LICENSE").write_text(
            "SPDX-License-Identifier: MIT\n\n"
            "This file may alternatively be used under the Apache License 2.0:\n\n"
            + (detector.license_detector.spdx_data.get_license_text("Apache-2.0") or "")
        )

        found = _licences(_scan(root))

        assert "MIT" in found, found
        assert "Apache-2.0" in found, found

    def test_two_grants_of_one_licence_are_never_near_misses(self):
        """The -or-later grant is stated where the licence is applied.

        `GPL-2.0-only` and `GPL-2.0-or-later` are the same text, so nothing
        that compares text can tell them apart, and dropping one on the
        strength of the other would decide the grant by accident. Which of
        the two a file carries is the difference between being allowed to use
        a later version and not; #118 is what getting it wrong costs.
        """
        detector = LicenseCopyrightDetector()
        root = Path(tempfile.mkdtemp())
        (root / "COPYING").write_text(
            "SPDX-License-Identifier: GPL-2.0-only\n\n"
            "This package is also available under the GNU GPL version 2 or, at "
            "your option, any later version.\n\n"
            + (detector.license_detector.spdx_data.get_license_text("GPL-2.0-only") or "")
        )

        found = _licences(_scan(root))

        assert "GPL-2.0-only" in found, found
        assert "GPL-2.0-or-later" in found, found

    def test_a_file_that_states_nothing_still_gets_the_comparison(self):
        """The rule only applies where the file spoke for itself."""
        detector = LicenseCopyrightDetector()
        root = Path(tempfile.mkdtemp())
        (root / "LICENSE").write_text(
            detector.license_detector.spdx_data.get_license_text("Sleepycat") or ""
        )

        assert "Sleepycat" in _licences(_scan(root))
