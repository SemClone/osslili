"""Regression tests for the PEP 639 ``license = {file = ...}`` form (issue #96).

``_extract_from_pyproject_toml`` resolved the referenced license file by calling a
method that does not exist. The ``AttributeError`` was swallowed by a surrounding
``except Exception`` and logged as a failed file read, so the form silently detected
nothing.

A full directory scan masked it — the referenced license file is scanned on its own
anyway — so these tests exercise the paths where metadata is read without the license
file also being read.
"""

import pytest

from osslili.core.generator import LicenseCopyrightDetector
from osslili.core.models import Config, LicenseCategory

MIT_TEXT = """MIT License

Copyright (c) 2024 Example Corp

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

PYPROJECT = """[project]
name = "demo"
version = "1.0.0"
license = {file = "LICENSE"}
"""


@pytest.fixture
def project(tmp_path):
    (tmp_path / "LICENSE").write_text(MIT_TEXT)
    (tmp_path / "pyproject.toml").write_text(PYPROJECT)
    return tmp_path


@pytest.fixture(scope="module")
def generator():
    return LicenseCopyrightDetector(Config())


def test_metadata_fast_path_resolves_the_referenced_file(generator, project):
    """extract_package_metadata() is the documented fast path and read nothing."""
    result = generator.extract_package_metadata(str(project))
    assert {l.spdx_id for l in result.licenses} == {"MIT"}


def test_scanning_the_manifest_alone_resolves_the_referenced_file(generator, project):
    """A scan pointed straight at pyproject.toml never reads the license file itself."""
    result = generator.process_local_path(
        str(project / "pyproject.toml"), extract_archives=False
    )
    assert "MIT" in {l.spdx_id for l in result.licenses}


def test_detection_is_attributed_to_the_manifest(generator, project):
    """pyproject.toml is what declares the license, so it is the source."""
    result = generator.extract_package_metadata(str(project))
    detected = next(l for l in result.licenses if l.spdx_id == "MIT")

    assert detected.source_file.endswith("pyproject.toml")
    assert detected.category == LicenseCategory.DECLARED.value
    assert detected.match_type == "package_metadata_file"


def test_directory_scan_still_reports_it(generator, project):
    """The path that always worked must keep working."""
    result = generator.process_local_path(str(project), extract_archives=False)
    assert {l.spdx_id for l in result.licenses} == {"MIT"}


def test_missing_referenced_file_is_not_an_error(generator, tmp_path):
    """A manifest referencing a file that is not there yields nothing, quietly."""
    (tmp_path / "pyproject.toml").write_text(PYPROJECT)

    result = generator.extract_package_metadata(str(tmp_path))

    assert not result.errors
    assert not [l for l in result.licenses if l.spdx_id == "MIT"]


def test_unidentifiable_referenced_file_is_not_an_error(generator, tmp_path):
    """A referenced file that is not a license yields nothing, quietly."""
    (tmp_path / "LICENSE").write_text("This file intentionally contains no license.\n")
    (tmp_path / "pyproject.toml").write_text(PYPROJECT)

    result = generator.extract_package_metadata(str(tmp_path))

    assert not result.errors


def test_inline_license_text_form_still_works(generator, tmp_path):
    """The sibling `license = {text = ...}` form must be unaffected."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "1.0.0"\nlicense = {text = "Apache-2.0"}\n'
    )
    result = generator.extract_package_metadata(str(tmp_path))
    assert "Apache-2.0" in {l.spdx_id for l in result.licenses}
