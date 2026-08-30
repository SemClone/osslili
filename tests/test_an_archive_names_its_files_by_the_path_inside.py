"""Evidence for an archive is named by its path inside the archive.

Extraction picks a fresh temporary directory every run, so reporting where a
file was extracted to gave the same file a different name each time. Two
scans of one archive could not be compared byte for byte, and the path named
a directory that no longer existed by the time anyone read the report:

    run 1  /var/folders/.../oslili_extract_gj5ffp7e/extract_0_gin/gin-1.10.0/auth.go
    run 2  /var/folders/.../oslili_extract_x3wmyiba/extract_0_gin/gin-1.10.0/auth.go

The file is the same file. Issue #121. What is reported now is
``gin-1.10.0/auth.go``, which is stable across runs and means something to a
reader.

Sibling of #110 and #123, which settled *which* file a statement is
attributed to and in what order. This is the separate matter of what that
file is called.
"""

import json
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

MIT_TEXT = (
    "MIT License\n\nCopyright (c) 2024 Acme Corporation\n\nPermission is "
    "hereby granted, free of charge, to any person obtaining a copy of this "
    'software and associated documentation files (the "Software"), to deal '
    "in the Software without restriction, including without limitation the "
    "rights to use, copy, modify, merge, publish, distribute, sublicense, "
    "and/or sell copies of the Software.\n"
)

SOURCE_FILE = "// Copyright (c) 2023 Acme Corporation\nint main(){}\n"

# A directory below the root, because a fault that only ever sees a file at
# the top of the archive cannot tell a relative path from a basename.
TREE = {
    "proj-2.0/LICENSE": MIT_TEXT,
    "proj-2.0/src/main.c": SOURCE_FILE,
}


def _a_tree(tmp_path):
    """The files of TREE written under tmp_path, and their root."""
    root = tmp_path / "staging"
    for name, body in TREE.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body)
    return root


def _a_tarball(tmp_path):
    root = _a_tree(tmp_path)
    archive = tmp_path / "proj-2.0.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(root / "proj-2.0", arcname="proj-2.0")
    return archive


def _a_zip(tmp_path):
    root = _a_tree(tmp_path)
    archive = tmp_path / "proj-2.0.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        for name in TREE:
            zf.write(root / name, arcname=name)
    return archive


def _scan(target):
    """The evidence report for a target, as the CLI prints it."""
    finished = subprocess.run(
        [sys.executable, "-m", "osslili", "-f", "evidence", str(target)],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert finished.returncode == 0, finished.stderr
    body = finished.stdout[finished.stdout.index("{"):]
    return json.loads(body)


def _files_named(report):
    """Every path the report attributes a statement to."""
    named = []
    for scanned in report["scan_results"]:
        for evidence in scanned.get("license_evidence", []):
            named.append(evidence["file"])
        for evidence in scanned.get("copyright_evidence", []):
            named.append(evidence["file"])
    return named


class TestTheNameIsThePathInsideTheArchive:
    def test_a_tarball_names_the_path_inside(self, tmp_path):
        named = _files_named(_scan(_a_tarball(tmp_path)))

        assert named, "the archive carries a licence; something should be named"
        assert set(named) <= set(TREE), (
            f"expected only paths inside the archive, got {sorted(set(named))}"
        )

    def test_a_zip_names_the_path_inside(self, tmp_path):
        named = _files_named(_scan(_a_zip(tmp_path)))

        assert named
        assert set(named) <= set(TREE)

    def test_no_name_reaches_the_extraction_directory(self, tmp_path):
        """The temporary directory is what changed between runs."""
        named = _files_named(_scan(_a_tarball(tmp_path)))

        for path in named:
            assert "oslili_extract_" not in path, path
            assert "extract_0_" not in path, path
            assert not Path(path).is_absolute(), path

    def test_the_name_is_spelled_the_way_the_archive_spells_it(self, tmp_path):
        """Forward slashes on every platform, because tar and zip use them.

        Letting the local separator through would report `proj-2.0\\LICENSE`
        on Windows for a member stored as `proj-2.0/LICENSE` — a different
        name for the same file, which is the fault this issue is about,
        moved from the run to the platform.
        """
        named = _files_named(_scan(_a_tarball(tmp_path)))

        nested = [path for path in named if path.count("/") > 0 or "\\" in path]
        assert nested, "the tree has a file below the archive root"
        for path in named:
            assert "\\" not in path, path

    def test_a_copyright_is_named_the_same_way(self, tmp_path):
        """Both halves of the report carry a path; #110 was the copyright one."""
        report = _scan(_a_tarball(tmp_path))

        found = [
            evidence["file"]
            for scanned in report["scan_results"]
            for evidence in scanned.get("copyright_evidence", [])
        ]
        assert found, "the tree carries a copyright statement"
        assert set(found) <= set(TREE), sorted(set(found))


class TestTwoScansAgree:
    def test_the_same_archive_reports_the_same_names_twice(self, tmp_path):
        """The point of the issue: two runs must be comparable."""
        first = _files_named(_scan(_a_tarball(tmp_path)))
        second = _files_named(_scan(_a_tarball(tmp_path)))

        assert first == second

    def test_the_whole_report_is_unchanged_between_runs(self, tmp_path):
        """Not only the names: the report has to diff clean against itself."""
        archive = _a_tarball(tmp_path)

        def without_timings(report):
            report.pop("summary", None)
            return json.dumps(report, sort_keys=True)

        assert without_timings(_scan(archive)) == without_timings(_scan(archive))


class TestTwoArchivesAreTwoScans:
    """A member path is unique inside its archive, not across archives.

    The name reported for archive evidence is stable across runs, which is
    the point of #121, but two packages that each carry `pkg/LICENSE` name
    the same string for different files. Anything counting those names has
    to know which scan each belongs to; counting the names alone reported
    one file where two were read.

    `generate_evidence` takes a list of results, so this is reachable from
    the library even though the CLI scans one path at a time.
    """

    def _two_archives(self, tmp_path):
        archives = []
        for name in ("alpha", "beta"):
            root = tmp_path / name / "pkg"
            root.mkdir(parents=True)
            (root / "LICENSE").write_text(MIT_TEXT)
            archive = tmp_path / f"{name}.tar.gz"
            with tarfile.open(archive, "w:gz") as tar:
                tar.add(root, arcname="pkg")
            archives.append(archive)
        return archives

    def _summary(self, tmp_path, detail_level):
        from osslili import LicenseCopyrightDetector

        detector = LicenseCopyrightDetector()
        results = [
            detector.process_local_path(str(archive))
            for archive in self._two_archives(tmp_path)
        ]
        rendered = detector.generate_evidence(results, detail_level=detail_level)
        return results, json.loads(rendered)["summary"]

    def test_both_archives_name_the_same_member(self, tmp_path):
        """The premise: the collision is real, not hypothetical."""
        results, _ = self._summary(tmp_path, "detailed")

        named = {
            license.source_file for result in results for license in result.licenses
        }
        assert named == {"pkg/LICENSE"}

    @pytest.mark.parametrize("detail_level", ["detailed", "summary", "minimal"])
    def test_two_files_are_counted_as_two(self, tmp_path, detail_level):
        _, summary = self._summary(tmp_path, detail_level)

        assert summary["total_files_scanned"] == 2

    @pytest.mark.parametrize("detail_level", ["summary", "minimal"])
    def test_files_with_licenses_counts_both(self, tmp_path, detail_level):
        _, summary = self._summary(tmp_path, detail_level)

        assert summary["files_with_licenses"] == 2


class TestADirectoryIsUnaffected:
    def test_a_directory_scan_still_names_the_file_it_read(self, tmp_path):
        """Nothing was extracted, so there is no archive to be relative to.

        Rewriting a path that did not come out of an archive would lose the
        only name the caller can act on.
        """
        root = _a_tree(tmp_path) / "proj-2.0"

        named = _files_named(_scan(root))

        assert named
        for path in named:
            assert Path(path).is_absolute(), path
            assert str(root) in path, path
