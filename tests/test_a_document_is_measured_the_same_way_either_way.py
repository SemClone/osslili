"""A document is measured the same way whether it or its directory is scanned.

Which window was measured followed from how the scan was *started* rather
than from what the file is. A README carrying the whole MIT text was compared
against the licence texts whole when named on the command line, and measured
through a short window around the first line saying "license" when the
directory holding it was scanned:

    scanning the file       MIT  0.995  text_similarity
    scanning the directory  MIT  0.95   documentation
                            MIT  0.6    documentation

One file, three answers, two of them contradicting each other under one name,
and no threshold worked in both modes. Issue #111.

## What it cost

A consumer that could not tell a full licence text from a fragment refused
the `documentation` match type outright, which lost it the genuine case: a
package whose only licence statement is the text in its README read as
unlicensed.

## The rule now

A licence file and a document are read whole — both are prose, and a README
carrying a licence is carrying it. A source file keeps the window, where
comparing a whole file against a licence text means nothing. A file named on
the command line is still read whole whatever it is, because it was named.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from osslili import LicenseCopyrightDetector

REPO_ROOT = Path(__file__).resolve().parents[1]


def _the_text_of(spdx_id):
    detector = LicenseCopyrightDetector().license_detector
    record = detector.spdx_data.get_license_info(spdx_id)
    assert record and record.get("text"), spdx_id
    return record["text"]


def _scan(target):
    finished = subprocess.run(
        [sys.executable, "-m", "osslili", "-f", "evidence", str(target)],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert finished.returncode == 0, finished.stderr
    return json.loads(finished.stdout[finished.stdout.index("{"):])


def _evidence(report):
    """Every licence record, without the file it came from.

    The path differs between the two modes by construction; what has to
    agree is what was found and how sure the scan is of it.
    """
    return sorted(
        (e["detected_license"], e["confidence"], e["match_type"], e["category"])
        for scanned in report["scan_results"]
        for e in scanned.get("license_evidence", [])
    )


@pytest.fixture
def a_readme_carrying_the_whole_licence():
    root = Path(tempfile.mkdtemp())
    (root / "README.md").write_text("# widget\n\n" + _the_text_of("MIT") + "\n")
    return root


@pytest.fixture
def a_readme_merely_crediting_one():
    root = Path(tempfile.mkdtemp())
    (root / "README.md").write_text(
        "# widget\n\nThis project depends on foo, which is licensed under Apache-2.0.\n"
    )
    return root


class TestTheTwoModesAgree:
    def test_a_readme_carrying_the_licence(self, a_readme_carrying_the_whole_licence):
        root = a_readme_carrying_the_whole_licence

        assert _evidence(_scan(root / "README.md")) == _evidence(_scan(root))

    def test_a_readme_crediting_a_dependency(self, a_readme_merely_crediting_one):
        root = a_readme_merely_crediting_one

        assert _evidence(_scan(root / "README.md")) == _evidence(_scan(root))


class TestAFullTextIsToldFromAFragment:
    def test_the_whole_licence_is_matched_as_text(
        self, a_readme_carrying_the_whole_licence
    ):
        """The number has to mean the same thing in both modes."""
        for target in (
            a_readme_carrying_the_whole_licence / "README.md",
            a_readme_carrying_the_whole_licence,
        ):
            found = _evidence(_scan(target))
            similarity = [row for row in found if row[2] == "text_similarity"]
            assert similarity, found
            assert similarity[0][0] == "MIT"
            assert similarity[0][1] > 0.9

    def test_a_mention_is_not_scored_as_a_licence_text(
        self, a_readme_merely_crediting_one
    ):
        for target in (
            a_readme_merely_crediting_one / "README.md",
            a_readme_merely_crediting_one,
        ):
            found = _evidence(_scan(target))
            assert not [row for row in found if row[2] == "text_similarity"], found

    def test_one_file_is_not_scored_twice_under_one_name(
        self, a_readme_carrying_the_whole_licence
    ):
        """0.95 and 0.6 for one file, both called `documentation`."""
        found = _evidence(_scan(a_readme_carrying_the_whole_licence))

        by_name = [(row[0], row[2]) for row in found]
        assert len(by_name) == len(set(by_name)), found


class TestTheGenuineCaseSurvives:
    """A package whose only licence statement is the text in its README.

    This is what refusing the `documentation` match type cost, and what
    scoring it the same way in both modes gives back.
    """

    def test_it_is_reported_without_the_documentation_match_type(self):
        root = Path(tempfile.mkdtemp())
        (root / "README.md").write_text(
            "# widget\n\nA thing.\n\n## License\n\n" + _the_text_of("MIT") + "\n"
        )
        (root / "pyproject.toml").write_text(
            '[project]\nname = "widget"\nversion = "1.0"\n'
        )

        found = _evidence(_scan(root))

        without_documentation = {
            row[0] for row in found if row[2] != "documentation"
        }
        assert "MIT" in without_documentation, found


class TestADocumentWithNothingToSayIsCheap:
    """The text tiers are only worth running on a document that mentions one.

    Reading every document whole compared each page against every licence
    text to find nothing. Two hundred ordinary pages went from 6.0s to 17.8s
    and produced no evidence either way, so a documentation-heavy repository
    paid three times over for the same answer.

    Pinned by which files reach the text tiers rather than by how long the
    scan took, so it does not depend on the machine it runs on.
    """

    def _pages_read_whole(self, root):
        """How many files were handed to the text tiers.

        Counted rather than timed: a wall-clock bound depends on the machine
        and can pass on a fast run with the guard removed.
        """
        detector = LicenseCopyrightDetector()
        reader = detector.license_detector
        read_whole = []
        original = reader._detect_license_from_text

        def counting(content, file_path, *args, **kwargs):
            read_whole.append(Path(file_path).name)
            return original(content, file_path, *args, **kwargs)

        reader._detect_license_from_text = counting
        found = detector.process_local_path(str(root))
        return read_whole, found

    def test_ordinary_pages_are_not_compared_against_every_licence(self):
        root = Path(tempfile.mkdtemp())
        for n in range(20):
            (root / f"page{n}.md").write_text(
                f"# Page {n}\n\n" + "Some ordinary prose about the product. " * 40
            )

        read_whole, found = self._pages_read_whole(root)

        assert read_whole == [], read_whole
        assert not found.licenses

    def test_a_page_that_mentions_one_is_read_whole(self):
        """The guard must not cost the case the fix exists for."""
        root = Path(tempfile.mkdtemp())
        (root / "boring.md").write_text("# Boring\n\nNothing to declare here.\n")
        (root / "README.md").write_text("# widget\n\n" + _the_text_of("MIT") + "\n")

        read_whole, _ = self._pages_read_whole(root)

        assert "README.md" in read_whole, read_whole
        assert "boring.md" not in read_whole, read_whole

    def test_a_document_that_does_mention_one_is_still_read_whole(self):
        root = Path(tempfile.mkdtemp())
        (root / "README.md").write_text("# widget\n\n" + _the_text_of("MIT") + "\n")

        found = _evidence(_scan(root))

        assert [row for row in found if row[2] == "text_similarity"], found


class TestWhatIsStillReadWhole:
    def test_a_file_named_on_the_command_line_whatever_it_is(self):
        """Scanning one file is a question about that file.

        It carries no licence-shaped name and no document suffix, and is
        still compared whole, which is what finds the exact match.
        """
        root = Path(tempfile.mkdtemp())
        target = root / "MIT.data"
        target.write_text(_the_text_of("MIT"))

        found = {
            (lic.spdx_id, lic.match_type)
            for lic in LicenseCopyrightDetector().license_detector.detect_licenses(target)
        }

        assert ("MIT", "exact_hash") in found, found
