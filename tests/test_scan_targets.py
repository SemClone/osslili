"""Tests for fine-grained scan targets and scanning-mode presets (issue #79).

Scanning modes are presets over per-category scan targets (license files,
bundled notice files, package metadata, documentation, source files), so a
consumer that gets declared licenses elsewhere - ORT's analyzer, for example -
can scan all files while disregarding package metadata.
"""

from pathlib import Path

import json
import pytest
from click.testing import CliRunner

from osslili.cli import main
from osslili.core.models import Config, ScanTargets
from osslili.core.generator import LicenseCopyrightDetector
from osslili.detectors.license_detector import LicenseDetector


MIT_TEXT = """MIT License

Copyright (c) 2024 Project Author

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""


@pytest.fixture
def project(tmp_path):
    """A project with one file per scan target category."""
    (tmp_path / "LICENSE").write_text(MIT_TEXT)
    (tmp_path / "package.json").write_text(
        json.dumps(
            {
                "name": "demo",
                "version": "1.0.0",
                "license": "Apache-2.0",
                "author": "Metadata Corp <legal@metadata.example>",
            }
        )
    )
    (tmp_path / "README.md").write_text(
        "# Demo\n\nThis project is licensed under the MIT License.\n"
    )
    (tmp_path / "requirements.txt").write_text("requests>=2.0\n")
    (tmp_path / "THIRD_PARTY_NOTICES.txt").write_text(
        "This product bundles zlib.\n\nSPDX-License-Identifier: Zlib\n"
    )
    src = tmp_path / "src"
    src.mkdir()
    (src / "app.py").write_text(
        "# SPDX-License-Identifier: BSD-3-Clause\n"
        "# Copyright (c) 2024 Source Author\n\n"
        "def main():\n    pass\n"
    )
    return tmp_path


def scanned_files(config: Config, path: Path) -> set:
    """Names of the files a configuration would scan for licenses."""
    detector = LicenseDetector(config)
    return {p.name for p in detector._find_files_to_scan(path, config.scan_targets())}


def source_files(licenses) -> set:
    return {Path(l.source_file).name for l in licenses if l.source_file}


# --------------------------------------------------------------------------
# Scan target resolution
# --------------------------------------------------------------------------


# The scans the flags select, named here for the tests rather than in the tool.
# They were presets once; the tool now offers the targets and lets a caller say
# which it wants, so these are the combinations worth asserting about.
def _a_config(scan):
    config = Config()
    if scan == "default":
        config.license_files_only = True
    elif scan == "deep":
        config.license_files_only = False
        config.deep_scan = True
    elif scan == "license-files":
        config.license_files_only = True
        config.strict_license_files = True
    elif scan == "all-files-no-metadata":
        config.license_files_only = False
        config.deep_scan = True
        config.scan_package_metadata = False
        config.text_similarity_matching = False
    else:
        raise AssertionError(scan)
    return config


def test_default_targets_exclude_source_files():
    targets = Config().scan_targets()
    assert targets == ScanTargets(
        license_files=True,
        notice_files=True,
        package_metadata=True,
        documentation=True,
        source_files=False,
    )


def test_default_config_keeps_text_similarity_matching():
    assert Config().text_similarity_matching is True


@pytest.mark.parametrize(
    "mode,expected",
    [
        (
            "default",
            ScanTargets(
                license_files=True,
                notice_files=True,
                package_metadata=True,
                documentation=True,
                source_files=False,
            ),
        ),
        (
            "deep",
            ScanTargets(
                license_files=True,
                notice_files=True,
                package_metadata=True,
                documentation=True,
                source_files=True,
            ),
        ),
        (
            "license-files",
            ScanTargets(
                license_files=True,
                notice_files=True,
                package_metadata=False,
                documentation=False,
                source_files=False,
            ),
        ),
        (
            "all-files-no-metadata",
            ScanTargets(
                license_files=True,
                notice_files=True,
                package_metadata=False,
                documentation=True,
                source_files=True,
            ),
        ),
    ],
)
def test_the_targets_each_scan_selects(mode, expected):
    config = _a_config(mode)
    assert config.scan_targets() == expected


def test_an_all_files_scan_without_metadata_disables_text_similarity_matching():
    config = _a_config("all-files-no-metadata")
    assert config.text_similarity_matching is False


@pytest.mark.parametrize("mode", ["default", "deep", "license-files"])
def test_every_other_scan_keeps_text_similarity_matching(mode):
    config = _a_config(mode)
    assert config.text_similarity_matching is True


def test_comparing_licence_text_is_on_unless_it_is_turned_off():
    """It is the tier that identifies a licence nobody tagged, so it is not
    something a caller loses without asking."""
    assert Config().text_similarity_matching is True


def test_the_flags_still_resolve_to_targets():
    assert Config(deep_scan=True).scan_targets().source_files is True
    assert Config(license_files_only=False).scan_targets().source_files is True
    strict = Config(strict_license_files=True).scan_targets()
    assert (strict.package_metadata, strict.documentation) == (False, False)


def test_explicit_target_overrides_win_over_the_mode():
    config = _a_config("deep")
    config.scan_package_metadata = False
    targets = config.scan_targets()
    assert targets.package_metadata is False
    assert targets.source_files is True

    # ... and the other way around: metadata back on in an all-files scan without metadata.
    config = _a_config("all-files-no-metadata")
    config.scan_package_metadata = True
    assert config.scan_targets().package_metadata is True


# --------------------------------------------------------------------------
# File selection
# --------------------------------------------------------------------------


def test_default_mode_scans_license_metadata_and_documentation(project):
    scanned = scanned_files(Config(), project)
    assert {"LICENSE", "package.json", "README.md", "THIRD_PARTY_NOTICES.txt"} <= scanned
    assert "app.py" not in scanned


def test_deep_mode_scans_source_files_and_metadata(project):
    config = _a_config("deep")
    scanned = scanned_files(config, project)
    assert {"LICENSE", "package.json", "README.md", "app.py"} <= scanned


def test_disabling_package_metadata_keeps_every_other_file(project):
    config = _a_config("deep")
    config.scan_package_metadata = False
    scanned = scanned_files(config, project)
    assert "package.json" not in scanned
    # requirements.txt is package metadata even though it has a doc extension
    assert "requirements.txt" not in scanned
    assert {"LICENSE", "README.md", "app.py"} <= scanned


def test_an_all_files_scan_without_metadata_scans_all_files_without_metadata(project):
    config = _a_config("all-files-no-metadata")
    scanned = scanned_files(config, project)
    assert "package.json" not in scanned
    assert {"LICENSE", "README.md", "app.py"} <= scanned


def test_disabling_documentation_keeps_license_files(project):
    config = Config()
    config.scan_documentation = False
    scanned = scanned_files(config, project)
    assert "README.md" not in scanned
    assert "LICENSE" in scanned


def test_disabling_notice_files_keeps_project_license_files(project):
    config = Config()
    config.scan_notice_files = False
    scanned = scanned_files(config, project)
    assert "THIRD_PARTY_NOTICES.txt" not in scanned
    assert "LICENSE" in scanned


def test_disabling_license_files_keeps_notice_files(project):
    config = Config()
    config.scan_license_files = False
    scanned = scanned_files(config, project)
    assert "LICENSE" not in scanned
    assert "THIRD_PARTY_NOTICES.txt" in scanned


def test_license_files_mode_scans_license_files_only(project):
    config = _a_config("license-files")
    scanned = scanned_files(config, project)
    assert "package.json" not in scanned
    assert "README.md" not in scanned
    assert "app.py" not in scanned
    assert "LICENSE" in scanned


# --------------------------------------------------------------------------
# Detection
# --------------------------------------------------------------------------


def test_default_mode_reports_metadata_declared_license(project):
    licenses = LicenseDetector(Config()).detect_licenses(project)
    assert "Apache-2.0" in {l.spdx_id for l in licenses}
    assert "package.json" in source_files(licenses)


def test_disabling_package_metadata_drops_metadata_licenses(project):
    config = Config()
    config.scan_package_metadata = False
    licenses = LicenseDetector(config).detect_licenses(project)
    assert "package.json" not in source_files(licenses)
    assert "MIT" in {l.spdx_id for l in licenses}


def test_disabling_package_metadata_applies_to_single_file_scans(project):
    config = Config()
    config.scan_package_metadata = False
    licenses = LicenseDetector(config).detect_licenses(project / "package.json")
    assert licenses == []


def test_an_all_files_scan_without_metadata_detects_source_tags_without_metadata(project):
    config = _a_config("all-files-no-metadata")
    licenses = LicenseDetector(config).detect_licenses(project)
    spdx_ids = {l.spdx_id for l in licenses}
    assert "BSD-3-Clause" in spdx_ids  # SPDX tag in src/app.py
    assert "Apache-2.0" not in spdx_ids  # declared in package.json only
    assert "package.json" not in source_files(licenses)


def test_disabling_text_similarity_skips_full_text_comparison(project):
    config = Config()
    config.text_similarity_matching = False
    licenses = LicenseDetector(config).detect_licenses(project)
    methods = {l.detection_method for l in licenses}
    assert not methods & {"hash", "dice-sorensen", "tlsh"}
    # The cheap detectors still run.
    assert licenses
    assert methods <= {"tag", "regex", "keyword", "filename"}


def test_text_similarity_matching_is_on_by_default(project):
    licenses = LicenseDetector(Config()).detect_licenses(project)
    methods = {l.detection_method for l in licenses}
    assert methods & {"hash", "dice-sorensen", "tlsh"}


def test_disabling_package_metadata_drops_metadata_copyrights(project):
    config = Config()
    config.scan_package_metadata = False
    result = LicenseCopyrightDetector(config).process_local_path(str(project))
    holders = " ".join(c.holder for c in result.copyrights)
    assert "Metadata Corp" not in holders

    with_metadata = LicenseCopyrightDetector(Config()).process_local_path(str(project))
    assert "Metadata Corp" in " ".join(c.holder for c in with_metadata.copyrights)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def test_cli_no_package_metadata_excludes_metadata_evidence(project):
    result = CliRunner().invoke(
        main, [str(project), "--deep", "--no-package-metadata", "-f", "evidence"]
    )
    assert result.exit_code == 0, result.output
    assert "package.json" not in result.output


def test_cli_all_files_without_metadata_excludes_metadata_evidence(project):
    """What issue #79 asked for, said in flags: read everything, and leave
    the metadata to whoever already read it."""
    result = CliRunner().invoke(
        main,
        [str(project), "--deep", "--no-package-metadata", "--no-text-similarity",
         "-f", "evidence"],
    )
    assert result.exit_code == 0, result.output
    assert "package.json" not in result.output


def test_cli_default_run_includes_metadata_evidence(project):
    result = CliRunner().invoke(main, [str(project), "-f", "evidence"])
    assert result.exit_code == 0, result.output
    assert "package.json" in result.output


def test_cli_rejects_deep_together_with_license_files_only(project):
    """They ask for opposite scans. Taken together they used to resolve
    silently to deep, which answers a question the caller did not ask."""
    result = CliRunner().invoke(main, [str(project), "--deep", "--license-files-only"])
    assert result.exit_code == 2
    assert "--deep" in result.output and "--license-files-only" in result.output


def _evidence_summary(output: str) -> dict:
    """The scan summary from evidence output, ignoring per-detection ordering."""
    payload = json.loads(output[output.index("{"):])
    return payload["summary"]


class TestEachFlagReachesTheScan:
    """Every target flag asserted through the command line, because the
    wiring from a flag to the config is its own step and each line of it
    could be removed with the rest of this file still passing."""

    @pytest.fixture
    def project(self, tmp_path):
        root = tmp_path / "project"
        root.mkdir()
        (root / "LICENSE").write_text(
            "MIT License\n\nPermission is hereby granted, free of charge, to any "
            "person obtaining a copy of this software.\n"
        )
        (root / "THIRD_PARTY_NOTICES.txt").write_text(
            "zlib License\n\nThis software is provided 'as-is', without any express "
            "or implied warranty.\n"
        )
        # Written as a tag, because a licence named in a sentence in a README
        # is a reference to one rather than a declaration (issue #109), and
        # this fixture is about which files are read, not how they are read.
        (root / "README.md").write_text("# Demo\n\nSPDX-License-Identifier: BSD-3-Clause\n")
        (root / "package.json").write_text('{"name": "demo", "license": "Apache-2.0"}\n')
        (root / "app.py").write_text("# SPDX-License-Identifier: ISC\nx = 1\n")
        return root

    def _licences(self, target, *flags):
        result = CliRunner().invoke(main, [str(target), "-f", "evidence", *flags])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output[result.output.index("{"):])
        return {
            record["detected_license"]
            for scan in data["scan_results"]
            for record in scan["license_evidence"]
        }

    @pytest.mark.parametrize("flag,gone", [
        ("--no-license-files", "MIT"),
        ("--no-notice-files", "Zlib"),
        ("--no-package-metadata", "Apache-2.0"),
        ("--no-documentation", "BSD-3-Clause"),
    ])
    def test_turning_a_category_off_removes_its_licence(self, project, flag, gone):
        with_it = self._licences(project, "--deep")
        without = self._licences(project, "--deep", flag)

        assert gone in with_it, with_it
        assert gone not in without, without

    def test_turning_source_files_off_removes_the_tag_in_one(self, project):
        assert "ISC" in self._licences(project, "--deep")
        assert "ISC" not in self._licences(project, "--deep", "--no-source-files")

    def test_the_deep_flag_reaches_the_scan(self, project):
        """It is applied where the mode preset used to apply it, and removing
        that left --deep reading four files instead of sixteen."""
        assert "ISC" not in self._licences(project)
        assert "ISC" in self._licences(project, "--deep")

    def test_the_license_files_only_flag_reaches_the_scan(self, project):
        only = self._licences(project, "--license-files-only")

        assert only == {"MIT", "Zlib"}, only

    def _how_it_was_found(self, target, *flags):
        result = CliRunner().invoke(main, [str(target), "-f", "evidence", *flags])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output[result.output.index("{"):])
        return {
            record["detection_method"]
            for scan in data["scan_results"]
            for record in scan["license_evidence"]
        }

    @pytest.fixture
    def a_licence_written_out(self, tmp_path):
        """The real text, so the tiers that compare text have something to
        match. A paraphrase is found by keyword and proves nothing about
        them."""
        from osslili.core.models import Config
        from osslili.detectors.license_detector import LicenseDetector

        root = tmp_path / "written-out"
        root.mkdir()
        record = LicenseDetector(Config()).spdx_data.get_license_info("MIT")
        (root / "LICENSE").write_text(record["text"])
        return root

    def test_the_text_tiers_are_used_when_they_are_on(self, a_licence_written_out):
        how = self._how_it_was_found(a_licence_written_out, "--deep")

        assert how & {"hash", "dice-sorensen", "tlsh"}, how

    def test_and_not_when_they_are_off(self, a_licence_written_out):
        how = self._how_it_was_found(
            a_licence_written_out, "--deep", "--no-text-similarity"
        )

        assert not how & {"hash", "dice-sorensen", "tlsh"}, how
        assert how, "every reader was turned off, not just the comparison"


class TestAFileNamedOnItsOwn:
    """Naming a file is the choice to read it, whatever a directory scan
    would have picked up. What it is not read for is a category the caller
    turned off."""

    @pytest.fixture
    def files(self, tmp_path):
        (tmp_path / "LICENSE").write_text(
            "MIT License\n\nPermission is hereby granted, free of charge.\n"
        )
        (tmp_path / "app.py").write_text("# SPDX-License-Identifier: ISC\nx = 1\n")
        (tmp_path / "setup.py").write_text(
            "# Copyright (c) 2024 Metadata Corp.\n"
            "from setuptools import setup\n"
            'setup(name="demo", license="MIT", author="Metadata Corp")\n'
        )
        return tmp_path

    def _reported(self, target, *flags):
        result = CliRunner().invoke(main, [str(target), "-f", "evidence", *flags])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output[result.output.index("{"):])
        return (
            {r["detected_license"] for s in data["scan_results"] for r in s["license_evidence"]},
            {r["holder"] for s in data["scan_results"] for r in s["copyright_evidence"]},
        )

    def test_a_source_file_named_on_its_own_is_read(self, files):
        """Source files are not in the default scan, and pointing straight at
        one has always read it."""
        licences, _ = self._reported(files / "app.py")

        assert licences == {"ISC"}, licences

    @pytest.mark.parametrize("name,flag", [
        ("LICENSE", "--no-license-files"),
        ("app.py", "--no-source-files"),
        ("setup.py", "--no-package-metadata"),
    ])
    def test_but_not_for_a_category_turned_off(self, files, name, flag):
        licences, _ = self._reported(files / name, flag)

        assert licences == set(), licences

    def test_disregarding_metadata_takes_the_holder_with_it(self, files):
        """A manifest carries its author as well as its licence, and reading
        it for the copyright line while refusing it for the licence reported
        half of what the file says."""
        _, holders = self._reported(files / "setup.py", "--no-package-metadata")

        assert holders == set(), holders

    def test_and_the_holder_is_there_without_the_flag(self, files):
        _, holders = self._reported(files / "setup.py")

        assert "Metadata Corp" in holders, holders


class TestAPackageOfOnlyOneCategory:
    """The walk that gathers metadata and documentation is entered when
    either is wanted. Asking only about metadata left a package with nothing
    but a README unread."""

    def test_documentation_alone_is_still_gathered(self, tmp_path):
        root = tmp_path / "docs-only"
        root.mkdir()
        (root / "README.md").write_text("# Demo\n\nSPDX-License-Identifier: BSD-3-Clause\n")

        result = CliRunner().invoke(
            main, [str(root), "-f", "evidence", "--no-package-metadata"]
        )
        assert result.exit_code == 0, result.output
        data = json.loads(result.output[result.output.index("{"):])
        found = {
            record["detected_license"]
            for scan in data["scan_results"]
            for record in scan["license_evidence"]
        }

        assert found == {"BSD-3-Clause"}, found

    def test_and_metadata_alone_is_too(self, tmp_path):
        root = tmp_path / "metadata-only"
        root.mkdir()
        (root / "package.json").write_text('{"name": "demo", "license": "Apache-2.0"}\n')

        result = CliRunner().invoke(
            main, [str(root), "-f", "evidence", "--no-documentation"]
        )
        assert result.exit_code == 0, result.output
        data = json.loads(result.output[result.output.index("{"):])
        found = {
            record["detected_license"]
            for scan in data["scan_results"]
            for record in scan["license_evidence"]
        }

        assert found == {"Apache-2.0"}, found


class TestACategoryTurnedOffTakesItsCopyrightToo:
    """A scan target says which files are read, and a file that is not read
    has no copyright in it either. Only package metadata was being filtered,
    so a scan told to read licence files alone still reported the copyright
    out of a README and a source file."""

    @pytest.fixture
    def project(self, tmp_path):
        root = tmp_path / "holders"
        root.mkdir()
        (root / "LICENSE").write_text(
            "MIT License\n\nCopyright (c) 2024 Licenza Labs\n\n"
            "Permission is hereby granted, free of charge.\n"
        )
        (root / "README.md").write_text("# Demo\n\nCopyright (c) 2024 Documentation Works\n")
        (root / "app.py").write_text("# Copyright (c) 2024 Source Works\nx = 1\n")
        (root / "package.json").write_text(
            '{"name": "demo", "license": "MIT", "author": "Metadata Works"}\n'
        )
        return root

    def _holders(self, target, *flags):
        result = CliRunner().invoke(main, [str(target), "-f", "evidence", *flags])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output[result.output.index("{"):])
        return {
            record["holder"]
            for scan in data["scan_results"]
            for record in scan["copyright_evidence"]
        }

    def test_all_of_them_are_there_to_begin_with(self, project):
        """Which is what makes the tests below worth having."""
        assert self._holders(project, "--deep") >= {
            "Licenza Labs", "Documentation Works", "Source Works", "Metadata Works",
        }

    @pytest.mark.parametrize("flag,gone", [
        ("--no-documentation", "Documentation Works"),
        ("--no-source-files", "Source Works"),
        ("--no-package-metadata", "Metadata Works"),
        ("--no-license-files", "Licenza Labs"),
    ])
    def test_turning_a_category_off_removes_its_holder(self, project, flag, gone):
        assert gone not in self._holders(project, "--deep", flag)

    def test_reading_licence_files_alone_reports_only_their_holders(self, project):
        """A scan told to read licence files and nothing else means it,
        including the source headers this extractor otherwise always reads."""
        assert self._holders(project, "--license-files-only") == {"Licenza Labs"}

    def test_a_default_scan_still_reads_source_headers(self, project):
        """It always has, whatever the licence scan was told to read, and a
        default scan that stopped reporting them would be a different tool."""
        assert "Source Works" in self._holders(project)

    def test_a_file_named_on_its_own_still_gives_its_holder(self, project):
        """Naming it is the choice to read it, whatever the default scan
        would have picked up."""
        assert self._holders(project / "app.py") == {"Source Works"}

    def test_unless_its_category_was_turned_off(self, project):
        assert self._holders(project / "app.py", "--no-source-files") == set()

    def test_naming_a_file_beats_a_narrower_scan(self, project):
        """The narrowing says which files a directory scan reads. Naming one
        says to read that one, and the two disagree here: the same flag that
        keeps a README out of the walk still reads it when it is named."""
        assert self._holders(project, "--license-files-only") == {"Licenza Labs"}
        assert self._holders(project / "README.md", "--license-files-only") == {
            "Documentation Works",
        }
