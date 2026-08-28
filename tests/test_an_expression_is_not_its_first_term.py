"""An SPDX expression on a header line is read whole.

`SPDX-License-Identifier:` may carry an expression, and the header pattern
stopped at the first space, so `MIT OR Apache-2.0` was reported as MIT,
dropping a choice the licensor offered, at confidence 1.0.

The exception in `GPL-2.0-only WITH Classpath-exception-2.0` is still not
reported. That is a different thing: the whole detector drops SPDX exceptions
rather than tracking them, which is issue #24. What this file covers is the
truncation, and the licence in a WITH expression now survives it.

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
        ("(* SPDX-License-Identifier: MIT *)\n", {"MIT"}),
        ("(* SPDX-License-Identifier: BSD-2-Clause *)\n", {"BSD-2-Clause"}),
    ])
    def test_the_marker_is_not_taken_for_a_licence(self, tmp_path, text, expected):
        """Asked of the header line alone. A second pattern reports the same
        identifier under another match type, so looking at both together
        cannot see this one failing."""
        found = _header_records(tmp_path, "widget.c", text)

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


class TestWhatFollowsTheExpressionIsNotPartOfIt:
    """Taking the rest of the line meant taking a note written after the
    licence, and the parser and the normaliser between them turned
    "BSD-2-Clause (see LICENSE)" into BSD-3-Clause, a different licence."""

    @pytest.mark.parametrize("text,expected", [
        ("// License: BSD-2-Clause (see LICENSE)\n", {"BSD-2-Clause"}),
        ("// License: GPL-2.0-only (see COPYING)\n", {"GPL-2.0-only"}),
        ("// License: MIT for the parser only\n", {"MIT"}),
        ("// SPDX-License-Identifier: MIT (see LICENSE for details)\n", {"MIT"}),
    ])
    def test_only_the_expression_is_read(self, tmp_path, text, expected):
        found = _header_records(tmp_path, "widget.c", text)

        assert found == expected, (text, found)

    def test_and_no_other_licence_is_invented(self, tmp_path):
        found = _header_records(
            tmp_path, "widget.c", "// License: BSD-2-Clause (see LICENSE)\n",
        )

        assert "BSD-3-Clause" not in found, found


class TestALicenceInAWithExpressionSurvives:
    """The exception itself is not reported, which is issue #24 and the whole
    detector's behaviour. The licence it modifies must at least come back."""

    def test_the_licence_is_reported(self, tmp_path):
        found = _header_records(
            tmp_path, "widget.c",
            "// SPDX-License-Identifier: GPL-2.0-only WITH Classpath-exception-2.0\n",
        )

        assert found == {"GPL-2.0-only"}, found

    def test_and_it_keeps_its_only_suffix(self, tmp_path):
        """Reporting GPL-2.0 instead would say something stricter about later
        versions than the file says."""
        found = _header_records(
            tmp_path, "widget.c",
            "// SPDX-License-Identifier: GPL-2.0-only WITH Classpath-exception-2.0\n",
        )

        assert "GPL-2.0" not in found, found


class TestALaterVersionGrantSurvivesAnException:
    """"GPL-2.0-or-later WITH Classpath-exception-2.0" was returned whole to
    the normaliser, which reduced it to the base word and answered GPL-2.0,
    modernised at the emission boundary to GPL-2.0-only: the opposite of what
    the file grants."""

    @pytest.mark.parametrize("expression,expected", [
        ("GPL-2.0-or-later WITH Classpath-exception-2.0", {"GPL-2.0-or-later"}),
        ("GPL-2.0-only WITH Classpath-exception-2.0", {"GPL-2.0-only"}),
        ("LGPL-2.1-or-later WITH Classpath-exception-2.0", {"LGPL-2.1-or-later"}),
        ("GPL-3.0-or-later", {"GPL-3.0-or-later"}),
    ])
    def test_the_licence_keeps_its_suffix(self, tmp_path, expression, expected):
        found = _header_records(
            tmp_path, "widget.c", f"// SPDX-License-Identifier: {expression}\n",
        )

        assert found == expected, (expression, found)

    def test_and_never_reads_as_only(self, tmp_path):
        found = _header_records(
            tmp_path, "widget.c",
            "// SPDX-License-Identifier: GPL-2.0-or-later WITH Classpath-exception-2.0\n",
        )

        assert "GPL-2.0-only" not in found and "GPL-2.0" not in found, found


class TestProseIsNotAnExpression:
    """SPDX writes its operators in upper case. Accepting them in any case
    made a sentence into an expression."""

    @pytest.mark.parametrize("text,expected", [
        ("// License: MIT and BSD-compatible\n", {"MIT"}),
        ("// License: MIT or something similar\n", {"MIT"}),
        ("// License: MIT with attribution\n", {"MIT"}),
    ])
    def test_a_lower_case_conjunction_is_a_word(self, tmp_path, text, expected):
        found = _header_records(tmp_path, "widget.c", text)

        assert found == expected, (text, found)

    def test_and_invents_no_second_licence(self, tmp_path):
        found = _header_records(tmp_path, "widget.c", "// License: MIT and BSD-compatible\n")

        assert "BSD-3-Clause" not in found, found

    @pytest.mark.parametrize("text,expected", [
        ("// License: MIT OR Apache-2.0\n", {"MIT", "Apache-2.0"}),
        ("// License: MIT AND BSD-3-Clause\n", {"MIT", "BSD-3-Clause"}),
    ])
    def test_but_upper_case_still_joins(self, tmp_path, text, expected):
        found = _header_records(tmp_path, "widget.c", text)

        assert found == expected, (text, found)


class TestTheExpressionHeaderTakesAnExpression:
    """License-Expression: is the Python metadata form, and it was reading
    one word of one."""

    def _all_tags(self, tmp_path, text):
        target = tmp_path / "METADATA"
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
            if item.get("match_type") in ("header_tag", "spdx_identifier")
        }

    def test_both_terms_are_reported(self, tmp_path):
        found = self._all_tags(tmp_path, "License-Expression: MIT OR Apache-2.0\n")

        assert found == {"MIT", "Apache-2.0"}, found

    def test_and_one_term_is_still_one(self, tmp_path):
        found = self._all_tags(tmp_path, "License-Expression: MIT\n")

        assert found == {"MIT"}, found
