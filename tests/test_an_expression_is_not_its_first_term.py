"""An SPDX expression on a header line is read whole.

`SPDX-License-Identifier:` may carry an expression, and the header pattern
stopped at the first space. `MIT OR Apache-2.0` was reported as MIT, dropping
a choice the licensor offered, and `GPL-2.0-only WITH Classpath-exception-2.0`
as GPL-2.0-only, dropping the exception that form exists for. Both at
confidence 1.0, both stating something the file does not.

The metadata paths always handled expressions: `"license": "MIT OR Apache-2.0"`
in package.json comes back whole. It was only the header line that truncated.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def _reported(tmp_path, name, text):
    target = tmp_path / name
    target.write_text(text)
    command = Path(sys.executable).parent / "osslili"
    if not command.exists():
        pytest.skip("the osslili console script is not installed beside this interpreter")
    result = subprocess.run(
        [str(command), "-f", "evidence", str(target)],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )
    assert result.returncode == 0, result.stderr
    lines = result.stdout.splitlines()
    start = next((i for i, line in enumerate(lines) if line.strip().startswith("{")), -1)
    if start < 0:
        return set()
    data = json.loads("\n".join(lines[start:]))
    return {
        item.get("detected_license")
        for scan in data.get("scan_results", [])
        for item in scan.get("license_evidence", [])
        if item.get("match_type") in (
            "header_tag", "spdx_identifier", "package_metadata",
        )
    }


class TestAChoiceIsKept:
    @pytest.mark.parametrize("expression,expected", [
        ("MIT OR Apache-2.0", {"MIT", "Apache-2.0"}),
        ("Apache-2.0 OR MIT", {"MIT", "Apache-2.0"}),
        ("Apache-2.0 OR MIT OR BSD-3-Clause", {"MIT", "Apache-2.0", "BSD-3-Clause"}),
        ("MIT AND BSD-3-Clause", {"MIT", "BSD-3-Clause"}),
        ("(MIT AND BSD-3-Clause)", {"MIT", "BSD-3-Clause"}),
    ])
    def test_every_term_is_reported(self, tmp_path, expression, expected):
        found = _reported(tmp_path, "widget.c", f"// SPDX-License-Identifier: {expression}\n")

        assert found == expected, (expression, found)

    @pytest.mark.parametrize("expression,expected", [
        ("MIT OR Apache-2.0", {"MIT", "Apache-2.0"}),
        ("MIT", {"MIT"}),
    ])
    def test_the_licence_line_form_too(self, tmp_path, expression, expected):
        found = _reported(tmp_path, "widget.c", f"// License: {expression}\n")

        assert found == expected, (expression, found)


class TestASingleIdentifierIsUnchanged:
    @pytest.mark.parametrize("identifier", [
        "MIT", "Apache-2.0", "GPL-2.0-or-later", "BSD-2-Clause", "0BSD",
        "LGPL-2.1-only", "CC-BY-NC-SA-3.0",
    ])
    def test_it_is_reported_as_itself(self, tmp_path, identifier):
        found = _reported(tmp_path, "widget.c", f"// SPDX-License-Identifier: {identifier}\n")

        assert found == {identifier}, (identifier, found)

    def test_an_or_later_suffix_is_not_an_expression(self, tmp_path):
        """"GPL-2.0-or-later" contains the word or and is one identifier."""
        found = _reported(tmp_path, "widget.c", "// SPDX-License-Identifier: GPL-2.0-or-later\n")

        assert found == {"GPL-2.0-or-later"}, found


class TestTheLineEndsWhereTheCommentDoes:
    """Taking the rest of the line means taking whatever closes the comment."""

    @pytest.mark.parametrize("text,expected", [
        ("/* SPDX-License-Identifier: MIT OR Apache-2.0 */\n", {"MIT", "Apache-2.0"}),
        ("<!-- SPDX-License-Identifier: MIT OR Apache-2.0 -->\n", {"MIT", "Apache-2.0"}),
        ("// SPDX-License-Identifier: MIT OR Apache-2.0\n", {"MIT", "Apache-2.0"}),
        ("# SPDX-License-Identifier: MIT\n", {"MIT"}),
    ])
    def test_the_marker_is_not_taken_for_a_licence(self, tmp_path, text, expected):
        found = _reported(tmp_path, "widget.c", text)

        assert found == expected, (text, found)


class TestTheMetadataPathsStillAgree:
    """They always read an expression whole. The header line now matches."""

    def test_package_json(self, tmp_path):
        found = _reported(
            tmp_path, "package.json",
            json.dumps({"name": "x", "version": "1.0.0", "license": "MIT OR Apache-2.0"}),
        )

        assert {"MIT", "Apache-2.0"} <= found, found

    def test_and_a_header_says_the_same(self, tmp_path):
        found = _reported(
            tmp_path, "widget.rs", "// SPDX-License-Identifier: MIT OR Apache-2.0\n",
        )

        assert {"MIT", "Apache-2.0"} <= found, found


def _header_records(tmp_path, name, text):
    """Only what the header line itself produced.

    The identifier is also matched by a second pattern elsewhere, which
    reports under a different match type, so a test that looks at both
    together cannot see the header line truncating.
    """
    target = tmp_path / name
    target.write_text(text)
    command = Path(sys.executable).parent / "osslili"
    if not command.exists():
        pytest.skip("the osslili console script is not installed beside this interpreter")
    result = subprocess.run(
        [str(command), "-f", "evidence", str(target)],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )
    assert result.returncode == 0, result.stderr
    lines = result.stdout.splitlines()
    start = next((i for i, line in enumerate(lines) if line.strip().startswith("{")), -1)
    if start < 0:
        return set()
    data = json.loads("\n".join(lines[start:]))
    return {
        item.get("detected_license")
        for scan in data.get("scan_results", [])
        for item in scan.get("license_evidence", [])
        if item.get("match_type") == "header_tag"
    }


class TestTheHeaderLineItself:
    @pytest.mark.parametrize("expression,expected", [
        ("MIT OR Apache-2.0", {"MIT", "Apache-2.0"}),
        ("Apache-2.0 OR MIT OR BSD-3-Clause", {"MIT", "Apache-2.0", "BSD-3-Clause"}),
        ("MIT AND BSD-3-Clause", {"MIT", "BSD-3-Clause"}),
    ])
    def test_it_reports_every_term(self, tmp_path, expression, expected):
        found = _header_records(
            tmp_path, "widget.c", f"// SPDX-License-Identifier: {expression}\n",
        )

        assert found == expected, (expression, found)

    def test_and_a_parenthesised_expression_too(self, tmp_path):
        found = _header_records(
            tmp_path, "widget.c", "// SPDX-License-Identifier: (MIT AND BSD-3-Clause)\n",
        )

        assert found == {"MIT", "BSD-3-Clause"}, found

    def test_a_single_identifier_stays_one(self, tmp_path):
        found = _header_records(
            tmp_path, "widget.c", "// SPDX-License-Identifier: GPL-2.0-or-later\n",
        )

        assert found == {"GPL-2.0-or-later"}, found
