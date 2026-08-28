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


class TestWhatTheCountCounts:
    """Files, not matches. A header written "Copyright (c) 2014 ..." is found
    by the pattern for the word and again by the pattern for the sign, so
    counting the matches said a statement in twelve files was in twenty-four,
    and a licence file naming its author once said two."""

    def _written_twice_over(self, tmp_path, how_many):
        root = tmp_path / "widget"
        root.mkdir()
        for index in range(how_many):
            (root / f"f{index:02d}.c").write_text(
                "// Copyright (c) 2014 Manu Martinez-Almeida\n"
                f"int x{index};\n"
            )
        return root

    def test_a_statement_matched_twice_in_one_file_counts_once(self, tmp_path):
        root = self._written_twice_over(tmp_path, 12)

        counts = {
            c.statement: c.file_count
            for c in _extractor().extract_copyrights(root)
        }

        assert set(counts.values()) == {12}, counts

    def test_and_a_single_file_counts_one(self, tmp_path):
        root = self._written_twice_over(tmp_path, 1)

        counts = {
            c.statement: c.file_count
            for c in _extractor().extract_copyrights(root)
        }

        assert set(counts.values()) == {1}, counts


class TestTheMetadataFilesCountToo:
    """A name in both package.json and setup.py is in two files. The count
    was settled before those files were read, so it stayed at one."""

    def _a_package(self, tmp_path):
        import json as _json

        root = tmp_path / "widget"
        root.mkdir()
        (root / "package.json").write_text(
            _json.dumps({"name": "widget", "version": "1.0.0", "author": "Acme Labs"})
        )
        (root / "setup.py").write_text(
            'from setuptools import setup\nsetup(name="widget", author="Acme Labs")\n'
        )
        return root

    def test_the_name_is_found_at_all(self, tmp_path):
        """Metadata is a separate pass, and nothing else here would notice if
        it stopped running."""
        root = self._a_package(tmp_path)

        statements = {c.statement for c in _extractor().extract_copyrights(root)}

        assert "Copyright Acme Labs" in statements, statements

    def test_and_both_files_are_counted(self, tmp_path):
        root = self._a_package(tmp_path)

        counts = {
            c.statement: c.file_count
            for c in _extractor().extract_copyrights(root)
        }

        assert counts["Copyright Acme Labs"] == 2, counts


class TestEveryGroupOfFilesIsSorted:
    """The search reads author files, then licence files, then READMEs, then
    source. Each group is walked separately and each needed sorting: a group
    left in filesystem order picked whichever file the directory happened to
    list first."""

    def _named(self, tmp_path, *names):
        root = tmp_path / "widget"
        root.mkdir()
        for name in names:
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("Copyright 2014 Manu Martinez-Almeida\n")
        return root

    def test_the_author_files(self, tmp_path):
        root = self._named(
            tmp_path, "z/AUTHORS", "m/AUTHORS", "a/AUTHORS", "b/AUTHORS",
        )

        chosen = [
            p for p in _extractor()._find_copyright_files(root)
            if p.name == "AUTHORS"
        ]

        assert chosen == sorted(chosen), [str(p) for p in chosen]

    def test_the_directories_walked_are_not_already_in_order(self, tmp_path):
        """The same guard the README names get: two entries come back in
        order often enough that a test using two proves nothing."""
        import os

        self._named(
            tmp_path, "z/AUTHORS", "m/AUTHORS", "a/AUTHORS", "b/AUTHORS",
        )
        walked = [
            name for _, dirs, _ in os.walk(tmp_path / "widget") for name in dirs
        ]

        assert walked != sorted(walked), walked

    def test_the_licence_files_at_the_root(self, tmp_path):
        root = self._named(
            tmp_path, "LICENSE.z", "LICENSE.m", "LICENSE.a", "LICENSE.b",
        )

        chosen = [
            p.name for p in _extractor()._find_copyright_files(root)
            if p.name.startswith("LICENSE")
        ]

        assert chosen == sorted(chosen), chosen

    def test_the_readme_files_at_the_root(self, tmp_path):
        root = self._named(
            tmp_path, "README.z", "README.m", "README.a", "README.b",
        )

        chosen = [
            p.name for p in _extractor()._find_copyright_files(root)
            if p.name.startswith("README")
        ]

        assert chosen == sorted(chosen), chosen

    def test_the_names_used_here_are_not_already_in_order(self, tmp_path):
        """Two names come back from a directory in order often enough that a
        test using two proves nothing. These four do not."""
        root = self._named(
            tmp_path, "README.z", "README.m", "README.a", "README.b",
        )

        walked = [p.name for p in root.glob("README*")]

        assert walked != sorted(walked), walked


class TestOneFileIsOneFile:
    """A setup.py is read twice over: once as a source file, for the lines
    written in it, and once as metadata, for the author it declares. The two
    passes hold the file's name in different forms, and a set that mixed a
    path with a string counted the one file as two."""

    def _a_setup_py_that_says_it_both_ways(self, tmp_path):
        root = tmp_path / "widget"
        root.mkdir()
        (root / "setup.py").write_text(
            "# Copyright Acme Labs\n"
            "from setuptools import setup\n"
            'setup(name="widget", author="Acme Labs")\n'
        )
        return root

    def test_it_is_counted_once(self, tmp_path):
        root = self._a_setup_py_that_says_it_both_ways(tmp_path)

        counts = {
            c.statement: c.file_count
            for c in _extractor().extract_copyrights(root)
        }

        assert counts["Copyright Acme Labs"] == 1, counts

    def test_and_reported_once(self, tmp_path):
        root = self._a_setup_py_that_says_it_both_ways(tmp_path)

        statements = [c.statement for c in _extractor().extract_copyrights(root)]

        assert statements.count("Copyright Acme Labs") == 1, statements


class TestAStatementIsReportedOnce:
    """However many times it is found, and wherever it is found. Two records
    saying the same thing are not two copyrights."""

    def test_a_line_matched_by_two_patterns_is_one_record(self, tmp_path):
        """"Copyright (c) 2014 ..." is found by the pattern for the word and
        again by the pattern for the sign."""
        root = tmp_path / "widget"
        root.mkdir()
        (root / "widget.c").write_text(
            "// Copyright (c) 2014 Manu Martinez-Almeida\nint x;\n"
        )

        statements = [c.statement for c in _extractor().extract_copyrights(root)]

        assert len(statements) == len(set(statements)), statements
        assert len(statements) == 1, statements

    def test_the_same_statement_in_many_files_is_one_record(self, tmp_path):
        root = _a_package(tmp_path)

        statements = [c.statement for c in _extractor().extract_copyrights(root)]

        assert statements.count(SHARED) == 1, statements

    def test_and_metadata_does_not_repeat_what_a_file_already_said(self, tmp_path):
        import json as _json

        root = tmp_path / "widget"
        root.mkdir()
        (root / "package.json").write_text(
            _json.dumps({"name": "widget", "version": "1.0.0", "author": "Acme Labs"})
        )
        (root / "setup.py").write_text(
            'from setuptools import setup\nsetup(name="widget", author="Acme Labs")\n'
        )

        statements = [c.statement for c in _extractor().extract_copyrights(root)]

        assert statements.count("Copyright Acme Labs") == 1, statements


class TestOneFileReachedByTwoNames:
    """A file is reached more than once, and by names that do not match. A
    LICENSE may be a symbolic link to LICENSE.txt; two names may be hard
    links to one file; on a filesystem that ignores case, setup.py and
    Setup.py are one file spelled two ways. Counting the names counted the
    one file several times, and no comparison of names gets all of these
    right, which is why the filesystem is asked instead."""

    def test_a_hard_link_is_not_a_second_file(self, tmp_path):
        import os

        root = tmp_path / "widget"
        root.mkdir()
        (root / "f00.c").write_text("// Copyright 2014 Acme Labs\nint x;\n")
        os.link(root / "f00.c", root / "f01.c")

        counts = {
            c.statement: c.file_count
            for c in _extractor().extract_copyrights(root)
        }

        assert counts["Copyright 2014 Acme Labs"] == 1, counts

    def test_a_setup_py_spelled_with_a_capital(self, tmp_path):
        """On a filesystem that ignores case the metadata pass finds it under
        the name it looks for and the walk reports the spelling on disk."""
        root = tmp_path / "widget"
        root.mkdir()
        (root / "Setup.py").write_text(
            "# Copyright Acme Labs\n"
            "from setuptools import setup\n"
            'setup(name="widget", author="Acme Labs")\n'
        )

        counts = {
            c.statement: c.file_count
            for c in _extractor().extract_copyrights(root)
        }

        assert counts["Copyright Acme Labs"] == 1, counts

    def test_a_setup_py_that_is_a_link_to_the_real_one(self, tmp_path):
        """The metadata pass reads it as setup.py and the walk reads it as
        real.py, so the two sides must agree on what identifies a file."""
        import os

        root = tmp_path / "widget"
        root.mkdir()
        (root / "real.py").write_text(
            "# Copyright Acme Labs\n"
            "from setuptools import setup\n"
            'setup(name="widget", author="Acme Labs")\n'
        )
        os.symlink("real.py", root / "setup.py")

        counts = {
            c.statement: c.file_count
            for c in _extractor().extract_copyrights(root)
        }

        assert counts["Copyright Acme Labs"] == 1, counts

    def test_a_symbolic_link_is_not_a_second_file(self, tmp_path):
        import os

        root = tmp_path / "widget"
        root.mkdir()
        (root / "LICENSE.txt").write_text("Copyright Acme Labs\n")
        os.symlink("LICENSE.txt", root / "LICENSE")

        counts = {
            c.statement: c.file_count
            for c in _extractor().extract_copyrights(root)
        }

        assert counts["Copyright Acme Labs"] == 1, counts

    def test_and_two_real_files_still_are_two(self, tmp_path):
        root = tmp_path / "widget"
        root.mkdir()
        (root / "LICENSE.txt").write_text("Copyright Acme Labs\n")
        (root / "NOTICE.txt").write_text("Copyright Acme Labs\n")

        counts = {
            c.statement: c.file_count
            for c in _extractor().extract_copyrights(root)
        }

        assert counts["Copyright Acme Labs"] == 2, counts


class TestTheFilesAreReadOnMoreThanOneThread:
    """The race this file exists for is in the threaded path, and that path
    is taken only above a threshold. Raise the threshold and every assertion
    here still passes, on the single-threaded path, having tested nothing
    about the fault."""

    def test_a_directory_of_thirty_files_uses_the_pool(self, tmp_path, monkeypatch):
        import osslili.extractors.copyright_extractor as module

        root = _a_package(tmp_path)
        used = []
        real = module.ThreadPoolExecutor

        def watched(*args, **kwargs):
            used.append(True)
            return real(*args, **kwargs)

        monkeypatch.setattr(module, "ThreadPoolExecutor", watched)
        _extractor().extract_copyrights(root)

        assert used, "the files were read on one thread, so nothing raced"


class TestTheCountIsInTheRecord:
    def test_a_record_says_one_file_by_default(self):
        from osslili.core.models import CopyrightInfo

        record = CopyrightInfo(holder="ACME", statement="Copyright ACME")

        assert record.file_count == 1

    def test_and_carries_it_into_the_dictionary(self):
        from osslili.core.models import CopyrightInfo

        record = CopyrightInfo(holder="ACME", statement="Copyright ACME")
        record.file_count = 7

        assert record.to_dict()["file_count"] == 7


class TestWhatIdentifiesAFile:
    """The helper answers for a path that names no file, because a caller
    cannot always know that in advance and a count is not worth an error."""

    @pytest.mark.parametrize("kind", ["loop", "broken", "missing", "long"])
    def test_a_path_that_names_no_file_still_answers(self, tmp_path, kind):
        import os
        from osslili.extractors.copyright_extractor import _the_file_itself

        if kind == "loop":
            os.symlink(tmp_path / "b", tmp_path / "a")
            os.symlink(tmp_path / "a", tmp_path / "b")
            path = tmp_path / "a"
        elif kind == "broken":
            os.symlink(tmp_path / "nowhere", tmp_path / "broken")
            path = tmp_path / "broken"
        elif kind == "long":
            path = tmp_path / ("x" * 300)
        else:
            path = tmp_path / "nope.txt"

        assert _the_file_itself(path)

    @pytest.mark.parametrize("nothing", ["", None])
    def test_and_nothing_is_nothing(self, nothing):
        from osslili.extractors.copyright_extractor import _the_file_itself

        assert _the_file_itself(nothing) == ""

    def test_two_names_for_one_file_answer_alike(self, tmp_path):
        import os
        from osslili.extractors.copyright_extractor import _the_file_itself

        (tmp_path / "real.txt").write_text("x")
        os.symlink("real.txt", tmp_path / "linked.txt")
        os.link(tmp_path / "real.txt", tmp_path / "hard.txt")

        answers = {
            _the_file_itself(tmp_path / name)
            for name in ("real.txt", "linked.txt", "hard.txt")
        }

        assert len(answers) == 1, answers

    def test_the_device_is_part_of_the_answer(self, tmp_path, monkeypatch):
        """An inode number is unique within a filesystem and not between
        them, so a scan that crosses a mount point could see two files with
        the same number. Asserted here rather than through a scan, because
        arranging a second filesystem is not something a test can do."""
        from pathlib import Path as _Path
        from osslili.extractors.copyright_extractor import _the_file_itself

        (tmp_path / "one.txt").write_text("x")
        (tmp_path / "two.txt").write_text("x")
        real = _Path.stat

        class OnItsOwnDevice:
            def __init__(self, stat, device):
                self.st_ino = 7
                self.st_dev = device
                self._stat = stat

            def __getattr__(self, name):
                return getattr(self._stat, name)

        def stat_of(self, *args, **kwargs):
            device = 1 if self.name == "one.txt" else 2
            return OnItsOwnDevice(real(self, *args, **kwargs), device)

        monkeypatch.setattr(_Path, "stat", stat_of)

        assert _the_file_itself(tmp_path / "one.txt") != _the_file_itself(
            tmp_path / "two.txt"
        )

    def test_and_two_files_do_not(self, tmp_path):
        from osslili.extractors.copyright_extractor import _the_file_itself

        (tmp_path / "one.txt").write_text("x")
        (tmp_path / "two.txt").write_text("x")

        assert _the_file_itself(tmp_path / "one.txt") != _the_file_itself(
            tmp_path / "two.txt"
        )


class TestWhichFileAStatementIsAttributedTo:
    """Not merely a settled file: the right one.

    The search reads author files first, then licence files, then READMEs,
    then source, because that is the order in which a file is likely to carry
    the package's own copyright. A statement is attributed to the first file
    it was found in under that order.

    Every other fixture here puts the shared statement in files of a single
    group, where the order the files were chosen and their names in order are
    the same thing, so none of them can tell the two apart.
    """

    def _in_a_licence_and_in_source(self, tmp_path):
        root = tmp_path / "widget"
        root.mkdir()
        (root / "AAA.c").write_text("// Copyright 2014 Acme Labs\nint x;\n")
        (root / "LICENSE").write_text("Copyright 2014 Acme Labs\n")
        return root

    def test_the_licence_file_wins_over_an_earlier_name(self, tmp_path):
        root = self._in_a_licence_and_in_source(tmp_path)

        attributed = {
            c.statement: Path(c.source_file).name
            for c in _extractor().extract_copyrights(root)
        }

        assert attributed["Copyright 2014 Acme Labs"] == "LICENSE", attributed

    def test_and_the_names_alone_would_have_chosen_the_other(self, tmp_path):
        """Which is what makes the test above worth having."""
        root = self._in_a_licence_and_in_source(tmp_path)

        names = sorted(
            p.name for p in _extractor()._find_copyright_files(root)
        )

        assert names[0] == "AAA.c", names

    def test_an_author_file_wins_over_a_licence_file(self, tmp_path):
        root = tmp_path / "widget"
        root.mkdir()
        (root / "zz_AUTHORS").write_text("Copyright 2014 Acme Labs\n")
        (root / "AUTHORS").write_text("Copyright 2014 Acme Labs\n")
        (root / "LICENSE").write_text("Copyright 2014 Acme Labs\n")

        attributed = {
            c.statement: Path(c.source_file).name
            for c in _extractor().extract_copyrights(root)
        }

        assert attributed["Copyright 2014 Acme Labs"] == "AUTHORS", attributed


class TestTheListIsOrderedByConfidence:
    """The sort is what puts the surest statement first, and the settled
    order this file is about is only what it falls back on for a tie."""

    def test_the_surest_comes_first(self, tmp_path):
        root = tmp_path / "widget"
        root.mkdir()
        (root / "AAA.c").write_text("// Copyright Apple Pie Ltd\nint x;\n")
        (root / "BBB.c").write_text("// Copyright 2014 Zed Corp\nint y;\n")

        found = _extractor().extract_copyrights(root)
        confidences = [c.confidence for c in found]

        assert confidences == sorted(confidences, reverse=True), [
            (c.statement, c.confidence) for c in found
        ]

    def test_and_a_dated_statement_outranks_an_undated_one(self, tmp_path):
        root = tmp_path / "widget"
        root.mkdir()
        (root / "AAA.c").write_text("// Copyright Apple Pie Ltd\nint x;\n")
        (root / "BBB.c").write_text("// Copyright 2014 Zed Corp\nint y;\n")

        statements = [c.statement for c in _extractor().extract_copyrights(root)]

        assert statements[0] == "Copyright 2014 Zed Corp", statements


class TestAFileThatCannotBeRead:
    """A thread that raises is logged and yields nothing, so that file is
    missing from the results the walk reads back. The walk asks for what it
    may not find, and the rest of the scan carries on."""

    def test_the_others_are_still_reported(self, tmp_path, monkeypatch):
        import osslili.extractors.copyright_extractor as module

        root = _a_package(tmp_path)
        extractor = _extractor()
        real = extractor._extract_copyrights_from_file

        def refuses_one(file_path):
            if file_path.name == "f00.c":
                raise OSError("cannot read it")
            return real(file_path)

        monkeypatch.setattr(extractor, "_extract_copyrights_from_file", refuses_one)
        found = extractor.extract_copyrights(root)

        assert {c.statement for c in found} == {SHARED, IN_ONE_FILE}, found

    def test_and_the_statement_moves_to_the_next_file(self, tmp_path, monkeypatch):
        import osslili.extractors.copyright_extractor as module

        root = _a_package(tmp_path)
        extractor = _extractor()
        real = extractor._extract_copyrights_from_file

        def refuses_one(file_path):
            if file_path.name == "f00.c":
                raise OSError("cannot read it")
            return real(file_path)

        monkeypatch.setattr(extractor, "_extract_copyrights_from_file", refuses_one)
        attributed = {
            c.statement: Path(c.source_file).name
            for c in extractor.extract_copyrights(root)
        }

        assert attributed[SHARED] == "f01.c", attributed

    def test_and_it_is_not_counted_among_the_files(self, tmp_path, monkeypatch):
        root = _a_package(tmp_path)
        extractor = _extractor()
        real = extractor._extract_copyrights_from_file

        def refuses_one(file_path):
            if file_path.name == "f00.c":
                raise OSError("cannot read it")
            return real(file_path)

        monkeypatch.setattr(extractor, "_extract_copyrights_from_file", refuses_one)
        counts = {c.statement: c.file_count for c in extractor.extract_copyrights(root)}

        assert counts[SHARED] == HOW_MANY - 1, counts
