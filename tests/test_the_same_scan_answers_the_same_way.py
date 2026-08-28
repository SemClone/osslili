"""A scan of a directory answers the same way every time.

Copyright statements were extracted concurrently and merged as the threads
finished, so the same scan of the same directory returned them in a different
order on each run. A statement said in more than one file is kept once, and
which file it was said to come from was decided by the same race: the same
statement came back against one file on one run and another on the next.

That made `file` the least reliable field in the record, which is a shame,
because it is the one a consumer wants in order to tell a package's own
copyright from a vendored one's. A record whose content depends on the run
cannot be diffed against a previous release or attested to (issue #110).

The threads are still there. They read the files; they no longer decide what
the answer looks like.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

# More than ten files, because that is when the extractor uses threads at all
# and there is a race to lose.
HOW_MANY = 30
SHARED = "Copyright 2014 Manu Martinez-Almeida"
IN_ONE_FILE = "Copyright 2021 Gin Core Team"


def _a_package(tmp_path):
    """A directory whose own copyright is in every file, and one that is not."""
    root = tmp_path / "gin"
    root.mkdir()
    for index in range(HOW_MANY):
        lines = [f"// {SHARED}\n"]
        if index == 17:
            lines.append(f"// {IN_ONE_FILE}\n")
        lines.append(f"int x{index};\n")
        (root / f"f{index:02d}.c").write_text("".join(lines))
    return root


def _extractor():
    from osslili.core.models import Config
    from osslili.extractors.copyright_extractor import CopyrightExtractor

    config = Config()
    config.deep_scan = True
    config.license_files_only = False
    return CopyrightExtractor(config)


def _records(root):
    return [
        (c.statement, Path(c.source_file).name if c.source_file else None)
        for c in _extractor().extract_copyrights(root)
    ]


class TestTheOrderIsSettled:
    def test_every_run_returns_the_same_list(self, tmp_path):
        root = _a_package(tmp_path)

        runs = {tuple(_records(root)) for _ in range(8)}

        assert len(runs) == 1, runs

    def test_and_the_file_does_not_move(self, tmp_path):
        """The statement in every file is the one with a race to lose: the
        thread that reached it first decided which file it came from."""
        root = _a_package(tmp_path)

        files = {
            next(name for statement, name in _records(root) if statement == SHARED)
            for _ in range(8)
        }

        assert files == {"f00.c"}, files

    def test_the_file_is_the_first_one_in_scan_order(self, tmp_path):
        """Not merely stable: the extractor reads the files most likely to
        carry the package's own copyright first, and the statement is
        attributed to the first file it was found in."""
        root = _a_package(tmp_path)
        chosen = _extractor()._find_copyright_files(root)

        records = _records(root)
        first = next(name for statement, name in records if statement == SHARED)

        assert first == chosen[0].name, (first, chosen[0].name)

    def test_the_files_are_chosen_in_a_settled_order(self, tmp_path):
        """A directory walk returns what the filesystem gives it, and two
        machines need not agree."""
        root = _a_package(tmp_path)

        walks = {
            tuple(p.name for p in _extractor()._find_copyright_files(root))
            for _ in range(4)
        }

        assert len(walks) == 1, walks
        assert list(walks)[0] == tuple(sorted(list(walks)[0]))


class TestHowManyFilesSaidIt:
    """`source_file` names one file, and one file cannot tell a package's own
    copyright from a vendored one's. A statement in thirty files is the
    package; a statement in one usually is not."""

    def test_a_statement_in_every_file_is_counted(self, tmp_path):
        root = _a_package(tmp_path)

        counts = {
            c.statement: c.file_count
            for c in _extractor().extract_copyrights(root)
        }

        assert counts[SHARED] == HOW_MANY, counts

    def test_and_one_in_a_single_file_is_not(self, tmp_path):
        root = _a_package(tmp_path)

        counts = {
            c.statement: c.file_count
            for c in _extractor().extract_copyrights(root)
        }

        assert counts[IN_ONE_FILE] == 1, counts

    def test_the_count_reaches_the_evidence(self, tmp_path):
        root = _a_package(tmp_path)
        result = subprocess.run(
            [sys.executable, "-m", "osslili", "-f", "evidence", "--deep", str(root)],
            capture_output=True, text=True, cwd=REPO_ROOT,
        )
        assert result.returncode == 0, result.stderr
        start = result.stdout.find("{")
        assert start >= 0, result.stdout
        data = json.loads(result.stdout[start:])

        counts = {
            record["statement"]: record.get("file_count")
            for scan in data["scan_results"]
            for record in scan["copyright_evidence"]
        }

        assert counts.get(SHARED) == HOW_MANY, counts
        assert counts.get(IN_ONE_FILE) == 1, counts

    def test_the_whole_report_is_the_same_every_run(self, tmp_path):
        root = _a_package(tmp_path)

        def once():
            result = subprocess.run(
                [sys.executable, "-m", "osslili", "-f", "evidence", "--deep", str(root)],
                capture_output=True, text=True, cwd=REPO_ROOT,
            )
            assert result.returncode == 0, result.stderr
            start = result.stdout.find("{")
            data = json.loads(result.stdout[start:])
            return json.dumps([
                (r["statement"], r["file"], r.get("file_count"))
                for scan in data["scan_results"]
                for r in scan["copyright_evidence"]
            ])

        assert len({once() for _ in range(3)}) == 1
