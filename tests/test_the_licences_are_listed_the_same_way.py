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
        "_find_metadata_and_documentation_files",
        "_find_source_files",
    ])
    def test_the_files_are_chosen_in_a_settled_order(self, tmp_path, finder):
        """A set is iterated in whatever order it likes, and that order
        differs between processes, so two scans of one directory chose the
        files in a different order."""
        root = _a_package(tmp_path)
        found = getattr(_detector(), finder)(root)

        assert found == sorted(found), (finder, [str(p) for p in found])

    @pytest.mark.parametrize("finder", [
        "_find_license_files",
        "_find_metadata_and_documentation_files",
    ])
    def test_and_alike_in_every_process(self, tmp_path, finder):
        """Which is what makes the test above worth having, and asserting it
        this way rather than by checking that these names are not already in
        order: that would itself be an assertion about arbitrary set order,
        and roughly one hash seed in two hundred would fail it."""
        root = _a_package(tmp_path)

        def once(seed):
            import os

            program = (
                "import sys, warnings; warnings.filterwarnings('ignore');"
                "sys.path.insert(0, %r);"
                "from pathlib import Path;"
                "from osslili.core.models import Config;"
                "from osslili.detectors.license_detector import LicenseDetector;"
                "c = Config(); c.deep_scan = True; c.license_files_only = False;"
                "print([p.name for p in getattr(LicenseDetector(c), %r)(Path(%r))])"
                % (str(REPO_ROOT), finder, str(root))
            )
            result = subprocess.run(
                [sys.executable, "-c", program],
                capture_output=True, text=True, cwd=REPO_ROOT,
                env=dict(os.environ, PYTHONHASHSEED=str(seed)),
            )
            assert result.returncode == 0, result.stderr
            return result.stdout.strip()

        answers = {once(seed) for seed in (1, 97, 126, 300)}

        assert len(answers) == 1, answers

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
        # And the file really did fail, otherwise the assertion above holds
        # whether or not anything was refused.
        assert "Apache-2.0" not in found, found


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


class TestWhatTheOneBodyDoes:
    """Merging the two readings put the whole contract in one place. Each
    part of it is asserted here, because a body nothing checks is a body that
    can quietly lose a piece."""

    def _a_licence_stated_twice(self, tmp_path):
        """A LICENSE whose text matches, and a package.json that declares it.
        The licence file yields two records at different confidences, from
        the text match and from the filename."""
        root = tmp_path / "widget"
        root.mkdir()
        (root / "LICENSE").write_text(MIT_TEXT)
        (root / "package.json").write_text('{"name": "widget", "license": "MIT"}\n')
        return root

    def test_the_surest_evidence_comes_first(self, tmp_path):
        root = self._a_licence_stated_twice(tmp_path)

        confidences = [lic.confidence for lic in _detector().detect_licenses(root)]

        assert confidences == sorted(confidences, reverse=True), confidences

    def test_two_readings_of_one_file_are_both_kept(self, tmp_path):
        """They differ in confidence and in how they were found, so they are
        two pieces of evidence about the same file and not a repeat."""
        root = self._a_licence_stated_twice(tmp_path)

        from_the_licence_file = [
            (lic.spdx_id, round(lic.confidence, 2))
            for lic in _detector().detect_licenses(root)
            if lic.source_file and Path(lic.source_file).name == "LICENSE"
        ]

        assert len(from_the_licence_file) == len(set(from_the_licence_file)) >= 2, (
            from_the_licence_file
        )

    def test_and_the_same_reading_twice_is_not(self, tmp_path):
        root = self._a_licence_stated_twice(tmp_path)

        records = [
            (lic.spdx_id, round(lic.confidence, 2), lic.source_file)
            for lic in _detector().detect_licenses(root)
        ]

        assert len(records) == len(set(records)), records

    def test_an_identifier_outside_the_spdx_list_is_not_emitted(self, tmp_path):
        """"MIT-or-later" is not an SPDX id. SPDX writes the or-later form
        only for the GNU family, and a string that merely looks like an
        identifier must never reach an SBOM."""
        root = tmp_path / "widget"
        root.mkdir()
        (root / "bad.c").write_text(
            "// SPDX-License-Identifier: MIT-or-later\nint x;\n"
        )

        found = {lic.spdx_id for lic in _detector().detect_licenses(root)}

        assert "MIT-or-later" not in found, found

    def test_a_deprecated_identifier_is_modernised(self, tmp_path):
        root = tmp_path / "widget"
        root.mkdir()
        (root / "widget.c").write_text("// SPDX-License-Identifier: GPL-2.0\nint x;\n")

        found = {lic.spdx_id for lic in _detector().detect_licenses(root)}

        assert "GPL-2.0-only" in found and "GPL-2.0" not in found, found


class TestTheFilesAreReadOnMoreThanOneThread:
    """The race this file exists for is in the threaded path. Take that path
    away and every assertion here still passes, on the sequential one, having
    tested nothing about the fault."""

    def _workers_used(self, tmp_path, monkeypatch):
        import osslili.detectors.license_detector as module

        root = _a_package(tmp_path)
        asked_for = []
        real = module.ThreadPoolExecutor

        def watched(*args, **kwargs):
            asked_for.append(kwargs.get("max_workers"))
            return real(*args, **kwargs)

        monkeypatch.setattr(module, "ThreadPoolExecutor", watched)
        _detector().detect_licenses(root)
        return asked_for

    def test_a_directory_of_many_files_uses_the_pool(self, tmp_path, monkeypatch):
        asked_for = self._workers_used(tmp_path, monkeypatch)

        assert asked_for, "the files were read on one thread, so nothing raced"

    def test_and_asks_for_more_than_one_thread(self, tmp_path, monkeypatch):
        """A pool of one is a pool."""
        asked_for = self._workers_used(tmp_path, monkeypatch)

        assert all(workers > 1 for workers in asked_for), asked_for


class TestWhatMakesTwoRecordsDifferent:
    """A record is kept once per licence, confidence and file. Each of those
    three carries a distinction, and dropping any of them from the key throws
    away evidence: two files stating the same licence, two licences offered
    by one file, and two readings of one file at different confidences."""

    def test_two_files_stating_the_same_licence_are_two_records(self, tmp_path):
        root = tmp_path / "widget"
        root.mkdir()
        (root / "a.c").write_text("// SPDX-License-Identifier: MIT\nint x;\n")
        (root / "b.c").write_text("// SPDX-License-Identifier: MIT\nint y;\n")

        files = sorted(
            Path(lic.source_file).name
            for lic in _detector().detect_licenses(root)
            if lic.spdx_id == "MIT"
        )

        assert files == ["a.c", "b.c"], files

    def test_two_licences_from_one_file_are_two_records(self, tmp_path):
        """A choice the licensor offered. Both terms come from package.json
        at the same confidence, so only the identifier tells them apart."""
        root = tmp_path / "widget"
        root.mkdir()
        (root / "package.json").write_text(
            '{"name": "widget", "license": "MIT OR Apache-2.0"}\n'
        )

        found = {lic.spdx_id for lic in _detector().detect_licenses(root)}

        assert {"MIT", "Apache-2.0"} <= found, found


class TestABundledNoticeStaysThirdParty:
    """A licence found in a bundled third-party notice is a dependency's, not
    the package's own, and several construction paths hard-code the declared
    category. It is re-tagged at the one exit point, after the merge this
    branch rewrote, and nothing was asserting that it still happens."""

    def test_the_category_survives_the_merge(self, tmp_path):
        root = tmp_path / "widget"
        root.mkdir()
        (root / "third_party_notice.c").write_text(
            "// SPDX-License-Identifier: Apache-2.0\nint x;\n"
        )

        categories = {
            lic.spdx_id: lic.category for lic in _detector().detect_licenses(root)
        }

        assert categories.get("Apache-2.0") == "third-party", categories

    def test_and_an_ordinary_file_is_not_third_party(self, tmp_path):
        """Which is what makes the test above worth having."""
        root = tmp_path / "widget"
        root.mkdir()
        (root / "widget.c").write_text(
            "// SPDX-License-Identifier: Apache-2.0\nint x;\n"
        )

        categories = {
            lic.spdx_id: lic.category for lic in _detector().detect_licenses(root)
        }

        assert categories.get("Apache-2.0") == "declared", categories


class TestWhatDecidesTheOrderOfEqualEvidence:
    """The sort by confidence is stable, so two records of equal confidence
    keep the order they were read in, which is the order the files were
    chosen: licence files before source files.

    Every other fixture here either has one file per confidence or puts the
    files in one group, where the order they were chosen and their names in
    order are the same thing, so none of them can tell the two apart.
    """

    def _a_licence_file_and_an_earlier_name(self, tmp_path):
        root = tmp_path / "widget"
        root.mkdir()
        (root / "license.txt").write_text(
            "// SPDX-License-Identifier: Apache-2.0\n"
        )
        (root / "a.c").write_text("// SPDX-License-Identifier: MIT\nint x;\n")
        return root

    def test_the_licence_file_is_read_first(self, tmp_path):
        root = self._a_licence_file_and_an_earlier_name(tmp_path)

        order = [
            (lic.spdx_id, Path(lic.source_file).name)
            for lic in _detector().detect_licenses(root)
        ]

        assert order[0] == ("Apache-2.0", "license.txt"), order

    def test_both_are_equally_sure(self, tmp_path):
        """Which is what leaves the order to the fallback, and so is what
        makes the test above worth having."""
        root = self._a_licence_file_and_an_earlier_name(tmp_path)

        confidences = {lic.confidence for lic in _detector().detect_licenses(root)}

        assert confidences == {1.0}, confidences

    def test_source_files_keep_the_order_they_were_walked_in(self, tmp_path):
        """The case above cannot tell a reversed reading from a right one,
        because a licence file is walked twice, once as a licence file and
        again as a source file, so it comes first either way."""
        root = tmp_path / "widget"
        root.mkdir()
        (root / "a.c").write_text("// SPDX-License-Identifier: MIT\nint x;\n")
        (root / "b.c").write_text("// SPDX-License-Identifier: Apache-2.0\nint y;\n")
        (root / "c.c").write_text("// SPDX-License-Identifier: BSD-3-Clause\nint z;\n")

        order = []
        for lic in _detector().detect_licenses(root):
            name = Path(lic.source_file).name
            if name not in order:
                order.append(name)

        assert order == ["a.c", "b.c", "c.c"], order

    def test_and_the_names_alone_would_have_chosen_the_other(self, tmp_path):
        root = self._a_licence_file_and_an_earlier_name(tmp_path)

        names = sorted(
            {Path(lic.source_file).name for lic in _detector().detect_licenses(root)}
        )

        assert names[0] == "a.c", names


class TestScanningOneFileOnItsOwn:
    """Whether one file is being scanned, rather than a directory, is carried
    through the reading of the files and changes what is looked for: a file
    given on its own is compared whole against the licence texts, and matches
    one exactly. Merging the two readings moved that flag, and nothing here
    was carrying it far enough to notice if it stopped arriving."""

    def _the_text_of(self, spdx_id):
        record = _detector().spdx_data.get_license_info(spdx_id)
        assert record and record.get("text"), spdx_id
        return record["text"]

    def test_the_text_matches_the_licence_exactly(self, tmp_path):
        target = tmp_path / "MIT.data"
        target.write_text(self._the_text_of("MIT"))

        found = {
            (lic.spdx_id, lic.match_type)
            for lic in _detector().detect_licenses(target)
        }

        assert ("MIT", "exact_hash") in found, found

    def test_and_at_no_doubt_at_all(self, tmp_path):
        target = tmp_path / "MIT.data"
        target.write_text(self._the_text_of("MIT"))

        exact = [
            lic for lic in _detector().detect_licenses(target)
            if lic.match_type == "exact_hash"
        ]

        assert exact and all(lic.confidence == 1.0 for lic in exact), [
            (lic.spdx_id, lic.confidence) for lic in exact
        ]
