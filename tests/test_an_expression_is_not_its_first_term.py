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
    result = subprocess.run(
        [sys.executable, "-m", "osslili", "-f", "evidence", str(target)],
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
    result = subprocess.run(
        [sys.executable, "-m", "osslili", "-f", "evidence", str(target)],
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
        result = subprocess.run(
            [sys.executable, "-m", "osslili", "-f", "evidence", str(target)],
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


class TestEveryLineBasedFormIsTrimmed:
    """The trimming was applied where the header line is read and not where
    the same forms are read a second time, so widening the capture carried
    the trailing text into the other path instead."""

    def _tags(self, tmp_path, name, text):
        target = tmp_path / name
        target.write_text(text)
        result = subprocess.run(
            [sys.executable, "-m", "osslili", "-f", "evidence", str(target)],
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

    @pytest.mark.parametrize("line,expected", [
        ("License-Expression: MIT and BSD-compatible", {"MIT"}),
        ("License-Expression: BSD-2-Clause (see LICENSE)", {"BSD-2-Clause"}),
        ("License-Expression: MIT OR Apache-2.0", {"MIT", "Apache-2.0"}),
        ("License-Expression: MIT", {"MIT"}),
    ])
    def test_the_python_metadata_form(self, tmp_path, line, expected):
        found = self._tags(tmp_path, "METADATA", line + "\n")

        assert found == expected, (line, found)

    def test_and_it_invents_no_licence(self, tmp_path):
        found = self._tags(
            tmp_path, "METADATA", "License-Expression: BSD-2-Clause (see LICENSE)\n",
        )

        assert "BSD-3-Clause" not in found, found


class TestAMetadataValueIsNotTrimmed:
    """A JSON or TOML value is already bounded by its quotes, so the rule for
    lines must not be applied to it."""

    def _tags(self, tmp_path, name, text):
        return TestEveryLineBasedFormIsTrimmed._tags(
            TestEveryLineBasedFormIsTrimmed(), tmp_path, name, text,
        )

    @pytest.mark.parametrize("value,expected", [
        ("MIT OR Apache-2.0", {"MIT", "Apache-2.0"}),
        ("MIT", {"MIT"}),
        ("BSD-3-Clause", {"BSD-3-Clause"}),
        # Names rather than identifiers, which is what a metadata value often
        # carries. Trimming these to their first word would leave "The" and
        # "Apache", and the first of those is nothing at all.
        ("The MIT License", {"MIT"}),
        ("Apache License 2.0", {"Apache-2.0"}),
    ])
    def test_package_json_reads_its_value_whole(self, tmp_path, value, expected):
        found = self._tags(
            tmp_path, "package.json",
            json.dumps({"name": "x", "version": "1.0.0", "license": value}),
        )

        assert expected <= found, (value, found)


class TestWhichPatternsCountAsALine:
    """Whether a capture is trimmed is decided by whether its pattern is
    anchored to the start of a line. That distinction is hard to see from
    outside, because the metadata files each have their own parser as well,
    so it is asserted here on the patterns themselves.
    """

    def _detector(self):
        from osslili.core.models import Config
        from osslili.detectors.license_detector import LicenseDetector

        return LicenseDetector(Config())

    def test_the_header_forms_read_a_line(self):
        from osslili.detectors.license_detector import _reads_a_line

        reading = [
            p.pattern for p in self._detector().spdx_tag_patterns
            if _reads_a_line(p)
        ]
        joined = " ".join(reading)

        for form in ("SPDX-License-Identifier", "License-Expression",
                     "License:", "@license"):
            assert form in joined, (form, reading)

    def test_and_no_quoted_value_does(self):
        """A value is bounded by its quotes, so what follows it on the line
        was never captured, and trimming would take "The MIT License" down to
        "The". The TOML form is anchored to a line start as well, so the
        anchor cannot be what decides this."""
        from osslili.detectors.license_detector import _reads_a_line

        trimmed = [
            p.pattern for p in self._detector().spdx_tag_patterns
            if _reads_a_line(p)
        ]

        assert not any('"' in pattern for pattern in trimmed), trimmed

    def test_including_the_anchored_toml_one(self):
        from osslili.detectors.license_detector import _reads_a_line

        toml = [
            p for p in self._detector().spdx_tag_patterns
            if p.pattern.startswith("^") and 'license\\s*=\\s*"' in p.pattern
        ]

        assert toml, "no anchored TOML value pattern found"
        assert not any(_reads_a_line(p) for p in toml), [p.pattern for p in toml]

    def test_the_trimming_takes_the_expression_only(self):
        from osslili.detectors.license_detector import _expression_at_the_front

        assert _expression_at_the_front("MIT OR Apache-2.0") == "MIT OR Apache-2.0"
        assert _expression_at_the_front("BSD-2-Clause (see LICENSE)") == "BSD-2-Clause"
        assert _expression_at_the_front("MIT and BSD-compatible") == "MIT"

    def test_and_would_ruin_a_licence_name(self):
        """Which is why the metadata values are left alone."""
        from osslili.detectors.license_detector import _expression_at_the_front

        assert _expression_at_the_front("The MIT License") == "The"


class TestTheAnnotationFormTakesAnExpression:
    """@license is the JavaScript annotation, and it read one word."""

    @pytest.mark.parametrize("value,expected", [
        ("MIT OR Apache-2.0", {"MIT", "Apache-2.0"}),
        ("MIT", {"MIT"}),
        ("MIT AND BSD-3-Clause", {"MIT", "BSD-3-Clause"}),
    ])
    def test_every_term_is_reported(self, tmp_path, value, expected):
        found = _reported(tmp_path, "widget.js", f"// @license {value}\n")

        assert expected <= found, (value, found)

    def test_and_a_note_after_it_is_not_a_licence(self, tmp_path):
        found = _reported(tmp_path, "widget.js", "// @license MIT (see LICENSE)\n")

        assert found == {"MIT"}, found


class TestTheDeprecatedPlusFormInAWithExpression:
    """GPL-2.0+ means or-later. Leaving the plus out of the operand took it
    off and reported GPL-2.0, modernised later to GPL-2.0-only."""

    def test_the_grant_survives(self, tmp_path):
        found = _header_records(
            tmp_path, "widget.c",
            "// SPDX-License-Identifier: GPL-2.0+ WITH Classpath-exception-2.0\n",
        )

        assert found == {"GPL-2.0-or-later"}, found

    def test_and_is_not_turned_into_only(self, tmp_path):
        found = _header_records(
            tmp_path, "widget.c",
            "// SPDX-License-Identifier: GPL-2.0+ WITH Classpath-exception-2.0\n",
        )

        assert "GPL-2.0-only" not in found, found

    def test_the_plus_form_alone_still_works(self, tmp_path):
        found = _header_records(
            tmp_path, "widget.c", "// SPDX-License-Identifier: GPL-2.0+\n",
        )

        assert found == {"GPL-2.0-or-later"}, found


class TestBracketsAroundPartOfTheExpression:
    """The kernel's own dual licence tag nests brackets:

        SPDX-License-Identifier: ((GPL-2.0 WITH Linux-syscall-note) OR MIT)

    A term that allowed a single bracket matched nothing at the first
    character, so the trim returned the empty string and the whole line was
    thrown away, leaving a file with no licence at all.
    """

    def test_a_nested_expression_is_read(self, tmp_path):
        found = _reported(
            tmp_path, "widget.h",
            "/* SPDX-License-Identifier: ((GPL-2.0 WITH Linux-syscall-note)"
            " OR MIT) */\n",
        )

        assert "MIT" in found, found

    def test_and_the_line_is_not_thrown_away(self, tmp_path):
        found = _reported(
            tmp_path, "widget.h",
            "/* SPDX-License-Identifier: ((GPL-2.0 WITH Linux-syscall-note)"
            " OR MIT) */\n",
        )

        assert found, "the licence on line 1 was discarded"

    def test_a_doubled_bracket_keeps_both_terms(self, tmp_path):
        found = _reported(
            tmp_path, "widget.h",
            "/* SPDX-License-Identifier: ((MIT OR Apache-2.0)) */\n",
        )

        assert found == {"MIT", "Apache-2.0"}, found


class TestALicenceNameIsNotAnExpression:
    """"Licensed under the ..." carries a licence name in prose, not an SPDX
    expression. Trimming its capture to the expression at the front cut the
    name at its first space: "the MIT No Attribution License" became MIT,
    asserting an attribution obligation the licensor had waived, and the
    longer names lost their identifier outright.
    """

    @pytest.mark.parametrize("name,expected", [
        ("MIT No Attribution License", "MIT-0"),
        ("Eclipse Public License 2.0", "EPL-2.0"),
        ("European Union Public License 1.2", "EUPL-1.2"),
        ("Creative Commons Attribution 4.0 International License", "CC-BY-4.0"),
    ])
    def test_the_whole_name_is_read(self, tmp_path, name, expected):
        found = _reported(tmp_path, "widget.c", f"// Licensed under the {name}\n")

        assert expected in found, (name, found)

    def test_and_no_attribution_is_not_turned_into_attribution(self, tmp_path):
        found = _reported(
            tmp_path, "widget.c",
            "// Licensed under the MIT No Attribution License\n",
        )

        assert "MIT" not in found, found

    def test_an_expression_after_the_words_still_parses(self, tmp_path):
        found = _reported(
            tmp_path, "widget.c", "// Licensed under the MIT OR Apache-2.0\n",
        )

        assert {"MIT", "Apache-2.0"} <= found, found


class TestSpaceInsideTheBrackets:
    """SPDX allows space inside the brackets. A term that did not was refused
    at the first character, so the trim returned nothing and the whole line
    was discarded."""

    @pytest.mark.parametrize("expression", [
        "( MIT OR Apache-2.0 )",
        "(MIT OR Apache-2.0 )",
        "( MIT OR Apache-2.0)",
        "( ( MIT OR Apache-2.0 ) )",
    ])
    def test_both_terms_survive_the_space(self, tmp_path, expression):
        found = _reported(
            tmp_path, "widget.c", f"// SPDX-License-Identifier: {expression}\n",
        )

        assert found == {"MIT", "Apache-2.0"}, (expression, found)


class TestThePlusIsAGrantNotAQuantifier:
    """A plus that ends an identifier is the deprecated or-later form. It was
    listed among the regex characters that mark a false positive, so once the
    reader stopped truncating the line and the plus reached that check,
    "@license GPL-2.0+" was thrown away and the file had no licence."""

    def test_the_licence_line_keeps_it(self, tmp_path):
        found = _reported(tmp_path, "widget.js", "// @license GPL-2.0+\n")

        assert found == {"GPL-2.0-or-later"}, found

    def test_and_it_is_not_read_as_only(self, tmp_path):
        found = _reported(tmp_path, "widget.js", "// @license GPL-2.0+\n")

        assert "GPL-2.0-only" not in found, found

    def test_a_regex_is_still_refused(self, tmp_path):
        found = _reported(tmp_path, "widget.js", "// @license [a-z]+\n")

        assert not found, found

    @pytest.mark.parametrize("value,is_false_positive", [
        ("GPL-2.0+", False),
        ("LGPL-2.1+", False),
        ("a[b]+", True),
        ("GPL-2.0\\d+", True),
        (".*+", True),
        ("MIT{2}+", True),
    ])
    def test_only_an_identifier_may_carry_it(self, value, is_false_positive):
        """The rule is an identifier followed by a plus, not a trailing plus.

        A value that reaches this check without passing through the line trim
        keeps whatever else is written in it, and a bare "ends with a plus"
        would wave a regex through on the strength of its last character.
        """
        from osslili.core.models import Config
        from osslili.detectors.license_detector import LicenseDetector

        detector = LicenseDetector(Config())

        assert detector._is_false_positive_license(value) is is_false_positive, value
