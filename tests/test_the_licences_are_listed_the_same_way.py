"""A scan lists its licence evidence the same way every time.

Licences were detected concurrently and merged as the threads finished, so
the same scan of the same directory listed the evidence in a different order
on each run, and the files were chosen from a set, whose iteration order
differs between processes. Four runs gave three orderings within one process,
and five hash seeds gave five answers across processes.

This is the sibling of issue #110, which was the same fault in the copyright
half of the scanner. The set of licences was stable in both; the report was
not the same report twice, so it could not be diffed against a previous
release or attested to (issue #122).

The threads still read the files. They no longer decide what the answer looks
like.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

# More than one file, because that is when the detector uses threads at all
# and there is a race to lose.
HOW_MANY = 20


# Several per group, because the fault is a set iterated in whatever order it
# likes, and with one or two entries that order is the sorted one often enough
# to prove nothing.
LICENCE_FILES = ("LICENSE", "LICENCE", "COPYING", "NOTICE", "LICENSE.txt", "COPYRIGHT")
DOCUMENT_FILES = ("README.md", "HISTORY.md", "CHANGELOG.rst", "NOTES.txt", "setup.cfg")

MIT_TEXT = (
    "MIT License\n\nPermission is hereby granted, free of charge, to any "
    "person obtaining a copy of this software and associated documentation "
    'files (the "Software"), to deal in the Software without restriction.\n'
)


def _a_package(tmp_path):
    """A directory whose files name licences, and enough of them to race."""
    root = tmp_path / "widget"
    root.mkdir()
    for name in LICENCE_FILES:
        (root / name).write_text(MIT_TEXT)
    for name in DOCUMENT_FILES:
        (root / name).write_text("Released under the MIT License.\n")
    (root / "package.json").write_text('{"name": "widget", "license": "MIT"}\n')
    for index in range(HOW_MANY):
        (root / f"f{index:02d}.c").write_text(
            f"// SPDX-License-Identifier: MIT\nint x{index};\n"
        )
    (root / "vendor.c").write_text(
        "// SPDX-License-Identifier: Apache-2.0\nint vendored;\n"
    )
    return root


def _detector():
    from osslili.core.models import Config
    from osslili.detectors.license_detector import LicenseDetector

    config = Config()
    config.deep_scan = True
    config.license_files_only = False
    return LicenseDetector(config)


def _records(root):
    return [
        (lic.spdx_id, lic.match_type, Path(lic.source_file).name if lic.source_file else None)
        for lic in _detector().detect_licenses(root)
    ]


class TestTheOrderIsSettled:
    def test_every_run_returns_the_same_list(self, tmp_path):
        root = _a_package(tmp_path)

        runs = {tuple(_records(root)) for _ in range(8)}

        assert len(runs) == 1, runs

    @pytest.mark.parametrize("finder", [
        "_find_license_files",
        "_find_metadata_and_readme_files",
        "_find_source_files",
    ])
    def test_the_files_are_chosen_in_a_settled_order(self, tmp_path, finder):
        """A set is iterated in whatever order it likes, and that order
        differs between processes, so two scans of one directory chose the
        files in a different order."""
        root = _a_package(tmp_path)
        found = getattr(_detector(), finder)(root)

        assert found == sorted(found), (finder, [str(p) for p in found])

    @pytest.mark.parametrize("names", [LICENCE_FILES, DOCUMENT_FILES])
    def test_the_names_used_here_are_not_already_in_order(self, tmp_path, names):
        """Which is what makes the test above worth having. With one or two
        entries a set comes back in order often enough to prove nothing."""
        root = _a_package(tmp_path)

        walked = [p.name for p in {root / name for name in names}]

        assert walked != sorted(walked), walked

    def test_across_processes_too(self, tmp_path):
        """Within one process a set iterates the same way twice. What differs
        is the hash seed, which is settled once when the process starts."""
        root = _a_package(tmp_path)

        def once(seed):
            import os

            environment = dict(os.environ, PYTHONHASHSEED=str(seed))
            result = subprocess.run(
                [sys.executable, "-m", "osslili", "-f", "evidence", "--deep", str(root)],
                capture_output=True, text=True, cwd=REPO_ROOT, env=environment,
            )
            assert result.returncode == 0, result.stderr
            start = result.stdout.find("{")
            data = json.loads(result.stdout[start:])
            return json.dumps([
                (r["file"], r["detected_license"], r["match_type"])
                for scan in data["scan_results"]
                for r in scan["license_evidence"]
            ])

        assert len({once(seed) for seed in (1, 2, 3, 4)}) == 1


class TestNothingIsLost:
    def test_both_licences_are_reported(self, tmp_path):
        root = _a_package(tmp_path)

        found = {spdx_id for spdx_id, _, _ in _records(root)}

        assert {"MIT", "Apache-2.0"} <= found, found

    def test_a_file_that_cannot_be_read_does_not_stop_the_rest(self, tmp_path, monkeypatch):
        """A thread that raises is logged and yields nothing, so that file is
        missing from the results the walk reads back."""
        root = _a_package(tmp_path)
        detector = _detector()
        real = detector._detect_licenses_in_file_safe

        def refuses_one(file_path, *args, **kwargs):
            if file_path.name == "vendor.c":
                raise OSError("cannot read it")
            return real(file_path, *args, **kwargs)

        monkeypatch.setattr(detector, "_detect_licenses_in_file_safe", refuses_one)
        found = {lic.spdx_id for lic in detector.detect_licenses(root)}

        assert "MIT" in found, found


class TestOneBodyReadsThemBoth:
    """The merge was written out twice, once for the threaded reading and
    once for the sequential one, and the two had to agree about what a licence
    is, whether it may be emitted, and when it is a repeat. They are now one."""

    def test_the_two_ways_of_reading_agree(self, tmp_path):
        root = _a_package(tmp_path)

        threaded = _detector()
        threaded.config.thread_count = 4
        on_one_thread = _detector()
        on_one_thread.config.thread_count = 1

        assert [
            (l.spdx_id, l.match_type, l.source_file)
            for l in threaded.detect_licenses(root)
        ] == [
            (l.spdx_id, l.match_type, l.source_file)
            for l in on_one_thread.detect_licenses(root)
        ]

    def test_and_a_deprecated_id_is_modernised_either_way(self, tmp_path):
        root = tmp_path / "widget"
        root.mkdir()
        (root / "widget.c").write_text("// SPDX-License-Identifier: GPL-2.0\nint x;\n")

        for threads in (1, 4):
            detector = _detector()
            detector.config.thread_count = threads
            found = {lic.spdx_id for lic in detector.detect_licenses(root)}

            assert "GPL-2.0-only" in found, (threads, found)
            assert "GPL-2.0" not in found, (threads, found)
