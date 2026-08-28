"""A file naming someone else's licence has not taken it.

"SPDX-License-Identifier: Apache-2.0" is a file declaring its licence. "the
bundled minifier is licensed under the Apache License" is a file crediting a
dependency. Both were reported the same way, at confidence 1.0, category
declared, so a consumer wanting to trust declarations had to refuse both. An
MIT package whose README credited a dependency was read as Apache-2.0.

What separates them is where the phrase sits. Apache's own boilerplate opens a
line, in the licence text and in every source header that carries it. A credit
has the thing being credited in front of it.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

FULL_MIT_TEXT = """MIT License

Copyright (c) 2024 Example

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
SOFTWARE."""

APACHE_BOILERPLATE = (
    'Licensed under the Apache License, Version 2.0 (the "License");\n'
    "you may not use this file except in compliance with the License.\n"
)


def _evidence(tmp_path, name, text):
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
        return []
    data = json.loads("\n".join(lines[start:]))
    return [
        (item.get("detected_license"), item.get("category"), item.get("match_type"))
        for scan in data.get("scan_results", [])
        for item in scan.get("license_evidence", [])
    ]


# The match types that mean "this file states this licence". The regex tier
# also reports a "documentation" record for prose, categorised declared, which
# is a separate defect about a different path and is tracked as #111. These
# tests are about the tag path, so they ask about the tag types.
DECLARING_TAGS = (
    "spdx_identifier", "header_tag", "package_metadata",
    "license_file", "license_header", "text_similarity", "exact_hash",
)


def _declared(evidence):
    return {
        spdx for spdx, category, match_type in evidence
        if category == "declared" and match_type in DECLARING_TAGS
    }


def _referenced(evidence):
    return {spdx for spdx, category, _ in evidence if category == "referenced"}


class TestACreditIsAReference:
    @pytest.mark.parametrize("sentence", [
        "The bundled minifier is licensed under the Apache License, Version 2.0.\n",
        "This project vendors terser, which is licensed under the BSD License.\n",
        "See NOTICE. The parser is licensed under the MIT License.\n",
    ])
    def test_it_is_not_reported_as_declared(self, tmp_path, sentence):
        evidence = _evidence(tmp_path, "README.md", sentence)

        assert _declared(evidence) == set(), evidence

    def test_and_it_is_reported_as_referenced(self, tmp_path):
        """Not discarded. The file does say something; it says it about
        something else."""
        evidence = _evidence(
            tmp_path, "README.md",
            "The bundled minifier is licensed under the Apache License, Version 2.0.\n",
        )

        assert "Apache-2.0" in _referenced(evidence), evidence

    def test_with_a_match_type_that_says_which_kind_it_is(self, tmp_path):
        evidence = _evidence(
            tmp_path, "README.md",
            "The bundled minifier is licensed under the Apache License, Version 2.0.\n",
        )
        kinds = {match_type for _, category, match_type in evidence
                 if category == "referenced"}

        assert kinds == {"prose_reference"}, evidence


class TestTheApacheBoilerplateIsADeclaration:
    """It opens a line, and it is how a file carrying the Apache licence says
    so. Reading it as a reference cost guava its licence entirely."""

    def test_in_a_source_header(self, tmp_path):
        evidence = _evidence(
            tmp_path, "Widget.java",
            "/*\n * " + APACHE_BOILERPLATE.replace("\n", "\n * ") + "\n */\npackage x;\n",
        )

        assert "Apache-2.0" in _declared(evidence), evidence

    def test_in_a_licence_file(self, tmp_path):
        evidence = _evidence(tmp_path, "LICENSE", "   " + APACHE_BOILERPLATE)

        assert "Apache-2.0" in _declared(evidence), evidence

    def test_and_it_is_not_called_a_reference(self, tmp_path):
        evidence = _evidence(tmp_path, "LICENSE", "   " + APACHE_BOILERPLATE)

        assert _referenced(evidence) == set(), evidence

    def test_a_whole_licence_file_still_resolves(self, tmp_path):
        """The case that caught this: guava ships the Apache text as
        META-INF/LICENSE, and its own boilerplate line is inside it. Reading
        that as a reference lost the licence of the package entirely."""
        text = (
            "                                 Apache License\n"
            "                           Version 2.0, January 2004\n"
            "                        http://www.apache.org/licenses/\n\n"
            "   TERMS AND CONDITIONS FOR USE, REPRODUCTION, AND DISTRIBUTION\n\n"
            "   " + APACHE_BOILERPLATE
        )
        evidence = _evidence(tmp_path, "LICENSE", text)

        assert "Apache-2.0" in _declared(evidence), evidence


class TestALicenceLineMustOpenTheLine:
    """"License: X" was matched after any space, so it fired mid-sentence."""

    @pytest.mark.parametrize("sentence", [
        "It bundles terser, license: BSD-2-Clause, for minification.\n",
        "Dependencies: react (License: MIT), terser (License: BSD-2-Clause)\n",
        "| terser | License: BSD-2-Clause |\n",
    ])
    def test_a_credit_line_declares_nothing(self, tmp_path, sentence):
        evidence = _evidence(tmp_path, "README.md", sentence)

        assert _declared(evidence) == set(), evidence

    @pytest.mark.parametrize("text", [
        "License: MIT\n\nA parser.\n",
        "  License: MIT\n",
        "# License: MIT\n",
        "<!-- License: MIT -->\n",
    ])
    def test_but_a_line_of_its_own_still_does(self, tmp_path, text):
        """In a document, opened the way a document opens a line."""
        evidence = _evidence(tmp_path, "README.md", text)

        assert "MIT" in _declared(evidence), evidence

    @pytest.mark.parametrize("text", [
        "// License: MIT\n",
        " * License: MIT\n",
        "/* License: MIT */\n",
    ])
    def test_and_a_comment_marked_one_does_in_code(self, tmp_path, text):
        evidence = _evidence(tmp_path, "widget.c", text)

        assert "MIT" in _declared(evidence), evidence

    @pytest.mark.parametrize("text", [
        "Dependencies:\n* Licensed under the MIT License.\n",
        "Dependencies:\n- Licensed under the MIT License.\n",
        "Dependencies:\n* License: MIT\n",
    ])
    def test_but_a_bullet_in_a_document_is_a_bullet(self, tmp_path, text):
        """An asterisk opens a comment in C and a list item in Markdown, and
        a README has no comment syntax to open."""
        evidence = _evidence(tmp_path, "README.md", text)

        assert _declared(evidence) == set(), evidence


class TestADeclarationIsUntouched:
    @pytest.mark.parametrize("name,text", [
        ("README.md", "SPDX-License-Identifier: MIT\n\nA parser.\n"),
        ("main.go", "// SPDX-License-Identifier: MIT\npackage main\n"),
        ("Widget.java", "/* SPDX-License-Identifier: Apache-2.0 */\n"),
        ("setup.py", "# SPDX-License-Identifier: BSD-3-Clause\n"),
    ])
    def test_it_still_declares(self, tmp_path, name, text):
        evidence = _evidence(tmp_path, name, text)

        assert _declared(evidence), evidence
        assert _referenced(evidence) == set(), evidence

    def test_a_prose_reference_does_not_replace_a_real_declaration(self, tmp_path):
        """A README can do both: declare its own licence and credit another."""
        evidence = _evidence(
            tmp_path, "README.md",
            "SPDX-License-Identifier: MIT\n\n"
            "The bundled minifier is licensed under the Apache License, Version 2.0.\n",
        )

        assert "MIT" in _declared(evidence), evidence
        assert "Apache-2.0" not in _declared(evidence), evidence

    def test_package_metadata_still_declares(self, tmp_path):
        evidence = _evidence(
            tmp_path, "package.json",
            json.dumps({"name": "x", "version": "1.0.0", "license": "MIT"}),
        )

        assert "MIT" in _declared(evidence), evidence


class TestACommentMarkerIsNotAWord:
    """The reference pattern asks for words in front of the phrase. Asking
    only for a non-space character counted the asterisk of a Java comment, so
    the Apache header opening " * Licensed under the Apache License" was read
    as a reference to someone else's licence."""

    @pytest.mark.parametrize("prefix", [" * ", "# ", "// ", "<!-- ", "   ", ""])
    def test_a_marked_up_header_is_not_a_reference(self, tmp_path, prefix):
        evidence = _evidence(
            tmp_path, "Widget.java",
            prefix + 'Licensed under the Apache License, Version 2.0 (the "License");\n',
        )

        assert _referenced(evidence) == set(), (prefix, evidence)

    @pytest.mark.parametrize("prefix", [" * ", "# ", "// ", "   "])
    def test_and_it_still_declares(self, tmp_path, prefix):
        evidence = _evidence(
            tmp_path, "Widget.java",
            prefix + 'Licensed under the Apache License, Version 2.0 (the "License");\n',
        )

        assert "Apache-2.0" in _declared(evidence), (prefix, evidence)

    def test_a_sentence_is_still_a_reference(self, tmp_path):
        """The other half, so the rule is not simply refusing everything."""
        evidence = _evidence(
            tmp_path, "README.md",
            "The bundled minifier is licensed under the Apache License, Version 2.0.\n",
        )

        assert "Apache-2.0" in _referenced(evidence), evidence


class TestTheHeaderFormIsReadAsAnIdentifier:
    """Apache's boilerplate is how a source file carrying that licence says
    so, and it deserves the same standing as an SPDX tag rather than only the
    weaker reading the text tier gives it."""

    def test_a_source_header_declares_by_identifier(self, tmp_path):
        evidence = _evidence(
            tmp_path, "Widget.java",
            '/*\n * Licensed under the Apache License, Version 2.0 (the "License");\n */\npackage x;\n',
        )
        kinds = {match_type for spdx, category, match_type in evidence
                 if spdx == "Apache-2.0" and category == "declared"}

        assert "spdx_identifier" in kinds, evidence


class TestTheReferencePatternOnItsOwn:
    """Asked of the pattern directly, because the end to end path cannot tell.

    The declaration form is checked before the reference form and the results
    are deduplicated by licence, so a header that both patterns match is
    claimed by the declaration and the reference never appears. That makes the
    behaviour right today and the reference pattern's own correctness
    invisible: loosening it changes nothing observable until someone reorders
    the two lists, and then it changes everything quietly.
    """

    def _reference_patterns(self):
        from osslili.detectors.license_detector import LicenseDetector

        return LicenseDetector._compile_prose_patterns(None)

    def _matches(self, text):
        return any(pattern.search(text) for pattern in self._reference_patterns())

    @pytest.mark.parametrize("line", [
        ' * Licensed under the Apache License, Version 2.0 (the "License");',
        "# Licensed under the Apache License, Version 2.0",
        "// Licensed under the Apache License, Version 2.0",
        "   Licensed under the Apache License, Version 2.0",
        "Licensed under the Apache License, Version 2.0",
        "<!-- Licensed under the Apache License, Version 2.0 -->",
    ])
    def test_a_line_that_opens_with_the_phrase_is_not_a_reference(self, line):
        assert not self._matches(line), line

    @pytest.mark.parametrize("line", [
        "The bundled minifier is licensed under the Apache License, Version 2.0.",
        "This project vendors terser, which is licensed under the BSD License.",
        " * The parser is licensed under the MIT License.",
    ])
    def test_a_phrase_with_words_before_it_is(self, line):
        assert self._matches(line), line


class TestAFileThatNamesItself:
    """"This file is licensed under the MIT License" and "Dual licensed under
    MIT OR Apache-2.0" are declarations with words in front of the phrase, so
    a rule that read any such words as a credit lost them."""

    @pytest.mark.parametrize("line", [
        "// This file is licensed under the MIT License.",
        "# This project is licensed under the MIT License.",
        " * This software is licensed under the MIT License.",
        "This package is licensed under the MIT License.",
        "Dual licensed under MIT OR Apache-2.0",
        "This software is dual licensed under the MIT License.",
        "Portions of this software are licensed under the MIT License.",
        "The software is licensed under the MIT License.",
    ])
    def test_it_declares(self, tmp_path, line):
        evidence = _evidence(tmp_path, "Widget.java", line + "\n")

        assert _declared(evidence), (line, evidence)
        assert _referenced(evidence) == set(), (line, evidence)

    def test_a_bare_also_continues_whatever_came_before(self, tmp_path):
        """"Also licensed under the MIT License" carries no subject of its
        own. After "the bundled parser is licensed under the BSD License" the
        sentence it continues is a credit, and there is no way to tell from
        the line itself. Reading it as a declaration is the answer that puts
        someone else's licence on the package, so it is read as a reference."""
        evidence = _evidence(
            tmp_path, "README.md",
            "The bundled parser is licensed under the BSD License.\n"
            "Also licensed under the MIT License.\n",
        )

        assert _declared(evidence) == set(), evidence

    @pytest.mark.parametrize("line", [
        "The bundled minifier is licensed under the Apache License, Version 2.0.",
        "This project vendors terser, which is licensed under the BSD License.",
    ])
    def test_but_naming_something_else_does_not(self, tmp_path, line):
        evidence = _evidence(tmp_path, "README.md", line + "\n")

        assert _referenced(evidence), (line, evidence)


class TestEveryCommentStyleOpensAHeader:
    """A header is a header whatever the language marks comments with."""

    @pytest.mark.parametrize("prefix", [
        "# ", "// ", " * ", "<!-- ", "; ", "% ", "(* ", "-- ", "   ", "",
    ])
    def test_a_licence_line_is_read(self, tmp_path, prefix):
        evidence = _evidence(tmp_path, "widget.c", prefix + "License: MIT\n")

        assert "MIT" in _declared(evidence), (prefix, evidence)

    @pytest.mark.parametrize("prefix", [
        "# ", "// ", " * ", "<!-- ", "; ", "% ", "(* ", "-- ", "   ", "",
    ])
    def test_and_so_is_an_identifier_line(self, tmp_path, prefix):
        evidence = _evidence(tmp_path, "widget.c", prefix + "SPDX-License-Identifier: MIT\n")

        assert "MIT" in _declared(evidence), (prefix, evidence)


class TestTheCreditDoesNotBecomeThePackageLicence:
    """What the reported bug actually costs: the credited licence reaching the
    package's own licence and its SBOM."""

    def _package(self, tmp_path):
        (tmp_path / "package.json").write_text(
            json.dumps({"name": "widget", "version": "1.0.0", "license": "MIT"})
        )
        (tmp_path / "README.md").write_text(
            "# widget\n\nThe bundled minifier is licensed under the "
            "Apache License, Version 2.0.\n"
        )
        (tmp_path / "LICENSE").write_text(
            "MIT License\n\nPermission is hereby granted, free of charge.\n"
        )
        return tmp_path

    def _output(self, tmp_path, form):
        command = Path(sys.executable).parent / "osslili"
        if not command.exists():
            pytest.skip("the osslili console script is not installed beside this interpreter")
        result = subprocess.run(
            [str(command), "-f", form, str(self._package(tmp_path))],
            capture_output=True, text=True, cwd=REPO_ROOT,
        )
        assert result.returncode == 0, result.stderr
        return result.stdout

    def test_the_primary_licence_is_the_package_s_own(self, tmp_path):
        output = self._output(tmp_path, "kissbom")

        assert json.loads(output[output.index("{"):])["packages"][0]["license"] == "MIT"

    def test_a_referenced_licence_is_not_one_of_the_project_s_own(self):
        """Asked of the model, which is what every formatter reads."""
        from osslili.core.models import DetectedLicense, DetectionResult, LicenseCategory

        result = DetectionResult(path="/repo")
        result.licenses = [
            DetectedLicense(spdx_id="MIT", name="MIT", confidence=1.0,
                            detection_method="tag", source_file="/repo/LICENSE",
                            category=LicenseCategory.DECLARED.value,
                            match_type="license_file"),
            DetectedLicense(spdx_id="Apache-2.0", name="Apache", confidence=1.0,
                            detection_method="tag", source_file="/repo/README.md",
                            category=LicenseCategory.REFERENCED.value,
                            match_type="prose_reference"),
        ]

        assert [lic.spdx_id for lic in result.get_own_licenses()] == ["MIT"]
        assert result.get_primary_license().spdx_id == "MIT"


class TestATagNamedInASentence:
    """The identifier is a header. Unanchored, a sentence about someone
    else's tag was read as this file's own."""

    def test_a_sentence_about_another_tag_does_not_declare(self, tmp_path):
        evidence = _evidence(
            tmp_path, "README.md",
            "Dependency foo declares SPDX-License-Identifier: MIT\n",
        )

        assert _declared(evidence) == set(), evidence

    @pytest.mark.parametrize("prefix", ["", "// ", "# ", " * ", "<!-- ", "-- "])
    def test_but_a_header_still_does(self, tmp_path, prefix):
        evidence = _evidence(
            tmp_path, "widget.c", prefix + "SPDX-License-Identifier: MIT\n",
        )

        assert "MIT" in _declared(evidence), (prefix, evidence)

    def test_an_expression_still_survives_the_anchor(self, tmp_path):
        evidence = _evidence(
            tmp_path, "widget.js",
            "// SPDX-License-Identifier: MIT OR Apache-2.0\n",
        )

        assert _declared(evidence) == {"MIT", "Apache-2.0"}, evidence


class TestAMarkdownBulletIsNotAComment:
    """A set of characters containing a hyphen accepted a bullet, so a credit
    under a Dependencies heading was read as a header."""

    def test_a_bulleted_credit_does_not_declare(self, tmp_path):
        evidence = _evidence(
            tmp_path, "README.md",
            "Dependencies:\n- Licensed under the MIT License.\n",
        )

        assert _declared(evidence) == set(), evidence

    def test_a_bulleted_licence_line_does_not_either(self, tmp_path):
        evidence = _evidence(
            tmp_path, "README.md", "Dependencies:\n- License: MIT\n",
        )

        assert _declared(evidence) == set(), evidence

    def test_but_a_double_hyphen_comment_still_does(self, tmp_path):
        evidence = _evidence(tmp_path, "main.hs", "-- License: MIT\n")

        assert "MIT" in _declared(evidence), evidence


class TestADocumentQuotingAMetadataFile:
    """A README showing what package.json contains is not package.json."""

    @pytest.mark.parametrize("text", [
        'This README documents package.json as {"license": "MIT"}\n',
        'Set `"license": "MIT"` in your package.json.\n',
        "Dependency metadata contains License-Expression: MIT\n",
        "Dependency foo declares @license MIT\n",
    ])
    def test_it_declares_nothing(self, tmp_path, text):
        evidence = _evidence(tmp_path, "README.md", text)

        assert _declared(evidence) == set(), evidence

    def test_but_the_metadata_file_itself_still_does(self, tmp_path):
        evidence = _evidence(
            tmp_path, "package.json",
            json.dumps({"name": "x", "version": "1.0.0", "license": "MIT"}),
        )

        assert "MIT" in _declared(evidence), evidence

    @pytest.mark.parametrize("name", ["LICENSE.txt", "LICENCE.md", "COPYING.txt"])
    def test_and_a_licence_file_is_never_a_document(self, tmp_path, name):
        """These carry a document suffix and hold the licence itself, so the
        rules for prose must not apply to them."""
        evidence = _evidence(tmp_path, name, FULL_MIT_TEXT)

        assert "MIT" in _declared(evidence), (name, evidence)


class TestTheDeclaredSetIsExact:
    """Asserting that something was declared says nothing about what."""

    def test_a_dual_licensed_header_reports_both(self, tmp_path):
        evidence = _evidence(
            tmp_path, "widget.rs", "// Dual licensed under MIT OR Apache-2.0\n",
        )

        assert _declared(evidence) == {"MIT", "Apache-2.0"}, evidence

    def test_a_single_declaration_reports_one(self, tmp_path):
        evidence = _evidence(
            tmp_path, "widget.rs", "// This file is licensed under the MIT License.\n",
        )

        assert _declared(evidence) == {"MIT"}, evidence

    def test_and_a_credit_names_the_credited_one(self, tmp_path):
        evidence = _evidence(
            tmp_path, "README.md",
            "The bundled minifier is licensed under the Apache License, Version 2.0.\n",
        )

        assert _referenced(evidence) == {"Apache-2.0"}, evidence


class TestTheSameRuleInCode:
    """The document pattern set has its own anchored copies, so a test
    written against a README says nothing about the set used for code."""

    @pytest.mark.parametrize("line", [
        "# the metadata of foo contains License-Expression: MIT",
        "# dependency foo declares @license MIT",
        "# see SPDX-License-Identifier: MIT in the vendored copy",
    ])
    def test_a_sentence_in_a_source_comment_declares_nothing(self, tmp_path, line):
        evidence = _evidence(tmp_path, "widget.py", line + "\n")

        assert _declared(evidence) == set(), (line, evidence)

    @pytest.mark.parametrize("line", [
        "# License-Expression: MIT",
        "# @license MIT",
        "# SPDX-License-Identifier: MIT",
    ])
    def test_but_the_header_forms_still_do(self, tmp_path, line):
        evidence = _evidence(tmp_path, "widget.py", line + "\n")

        assert "MIT" in _declared(evidence), (line, evidence)


class TestALicenceFileKeepsCodeRules:
    """A licence file is not a document however it is suffixed, so the
    narrower openings a document uses must not apply to it."""

    def test_an_asterisk_opened_header_is_read(self, tmp_path):
        evidence = _evidence(tmp_path, "LICENSE.txt", " * License: MIT\n")

        assert "MIT" in _declared(evidence), evidence

    def test_but_the_same_line_in_a_readme_is_a_bullet(self, tmp_path):
        evidence = _evidence(tmp_path, "README.md", " * License: MIT\n")

        assert _declared(evidence) == set(), evidence


class TestTheWordsAProjectCallsItself:
    """A project names itself in whatever word fits: repository, crate, gem,
    plugin. Each one missing from the set is a declaration read as a credit."""

    @pytest.mark.parametrize("subject", [
        "This repository", "This repo", "This crate", "This gem",
        "This plugin", "This extension", "This tool", "This application",
        "This app", "This component", "This utility", "This library",
        "This module", "The repository", "The library",
    ])
    def test_it_declares(self, tmp_path, subject):
        evidence = _evidence(
            tmp_path, "README.md", f"{subject} is licensed under the MIT License.\n",
        )

        assert "MIT" in _declared(evidence), (subject, evidence)
        assert _referenced(evidence) == set(), (subject, evidence)

    @pytest.mark.parametrize("subject", [
        "The bundled minifier", "Its parser", "terser",
    ])
    def test_but_naming_something_else_still_credits(self, tmp_path, subject):
        evidence = _evidence(
            tmp_path, "README.md",
            f"{subject} is licensed under the Apache License, Version 2.0.\n",
        )

        assert "Apache-2.0" in _referenced(evidence), (subject, evidence)


class TestOneAnswerToWhatALicenceFileIs:
    """Whether a file is a licence file is asked of _is_license_file rather
    than decided again, so the two cannot drift apart."""

    def test_the_document_rule_uses_the_detectors_own_answer(self):
        import inspect

        from osslili.detectors.license_detector import LicenseDetector

        source = inspect.getsource(LicenseDetector._reads_as_a_document)

        assert "_is_license_file" in source


class TestAHardWrappedCredit:
    """Seventy-two column wrapping puts the middle of a sentence at the start
    of a line, and the line-position rule read that as a header. It also let
    the capture run past the full stop and into the next sentence, so a name
    the file never wrote was normalised into a licence it never named."""

    WRAPPED = (
        "This distribution bundles a copy of terser for minification. terser is\n"
        "licensed under the BSD-2-Clause License. The bundled CSS minifier is\n"
        "licensed under the Apache License, Version 2.0.\n"
    )

    def test_it_declares_nothing(self, tmp_path):
        evidence = _evidence(tmp_path, "README.md", self.WRAPPED)

        assert _declared(evidence) == set(), evidence

    def test_and_invents_no_licence(self, tmp_path):
        """It said BSD-2-Clause and the tool reported BSD-3-Clause, which is
        a different licence with a clause the file does not carry."""
        evidence = _evidence(tmp_path, "README.md", self.WRAPPED)

        assert "BSD-3-Clause" not in {spdx for spdx, _, _ in evidence}, evidence

    def test_a_capitalised_header_still_declares(self, tmp_path):
        """The discriminator. A wrapped sentence continues in lower case."""
        evidence = _evidence(
            tmp_path, "Widget.java",
            ' * Licensed under the Apache License, Version 2.0 (the "License");\n',
        )

        assert "Apache-2.0" in _declared(evidence), evidence

    def test_and_a_subject_declares_in_any_case(self, tmp_path):
        """"This file is licensed under" is a sentence of its own, and its
        verb is lower case because that is how the sentence reads."""
        evidence = _evidence(
            tmp_path, "Widget.java", "// This file is licensed under the MIT License.\n",
        )

        assert "MIT" in _declared(evidence), evidence


class TestProseInsideALicenceFile:
    """A pointer-style LICENSE names the package and links to the text. There
    is no one else for it to be referring to."""

    POINTER = (
        "FooBar is licensed under the MIT License.\n"
        "See https://opensource.org/licenses/MIT for the full text.\n"
    )

    @pytest.mark.parametrize("name", ["LICENSE", "LICENCE.md", "COPYING"])
    def test_it_declares(self, tmp_path, name):
        evidence = _evidence(tmp_path, name, self.POINTER)

        assert "MIT" in _declared(evidence), (name, evidence)

    @pytest.mark.parametrize("name", ["LICENSE", "LICENCE.md", "COPYING"])
    def test_and_is_not_called_a_reference(self, tmp_path, name):
        evidence = _evidence(tmp_path, name, self.POINTER)

        assert _referenced(evidence) == set(), (name, evidence)

    def test_but_the_same_words_in_a_readme_still_credit(self, tmp_path):
        evidence = _evidence(tmp_path, "README.md", self.POINTER)

        assert "MIT" in _referenced(evidence), evidence


class TestDocumentsWithoutAMarkdownSuffix:
    """A suffix list that only proved itself on .md is a list of one."""

    BULLETED_CREDIT = "Bundled dependencies:\n* Licensed under the MIT License.\n"

    @pytest.mark.parametrize("name", [
        "README", "README.rst", "README.txt", "README.rdoc", "README.textile",
        "CHANGELOG", "INSTALL", "NEWS", "docs.org",
    ])
    def test_a_bulleted_credit_declares_nothing(self, tmp_path, name):
        evidence = _evidence(tmp_path, name, self.BULLETED_CREDIT)

        assert _declared(evidence) == set(), (name, evidence)

    @pytest.mark.parametrize("name", ["widget.c", "widget.py", "widget.rs"])
    def test_but_a_comment_marked_one_in_code_still_declares(self, tmp_path, name):
        evidence = _evidence(
            tmp_path, name, " * Licensed under the MIT License.\n",
        )

        assert "MIT" in _declared(evidence), (name, evidence)


class TestTheCodePathKeepsItsWholeMarkers:
    """Every bullet test uses a README, which takes the document openings, so
    nothing pinned the decision on the path where the code openings apply."""

    def test_a_double_hyphen_opens_a_comment_in_code(self, tmp_path):
        evidence = _evidence(tmp_path, "widget.hs", "-- License: MIT\n")

        assert "MIT" in _declared(evidence), evidence

    def test_a_single_hyphen_does_not(self, tmp_path):
        evidence = _evidence(tmp_path, "widget.hs", "- License: MIT\n")

        assert _declared(evidence) == set(), evidence

    def test_nor_does_a_single_hyphen_before_a_credit(self, tmp_path):
        evidence = _evidence(tmp_path, "widget.hs", "- Licensed under the MIT License.\n")

        assert _declared(evidence) == set(), evidence


class TestWhatCountsAsTheProjectsOwn:
    """get_own_licenses filters on the category, not on one match type."""

    def _result(self, category, match_type):
        from osslili.core.models import DetectedLicense, DetectionResult

        result = DetectionResult(path="/repo")
        result.licenses = [
            DetectedLicense(spdx_id="Apache-2.0", name="Apache", confidence=1.0,
                            detection_method="regex", source_file="/repo/README.md",
                            category=category, match_type=match_type),
        ]
        return result

    @pytest.mark.parametrize("match_type", ["prose_reference", "license_reference"])
    def test_every_referenced_record_is_excluded(self, match_type):
        result = self._result("referenced", match_type)

        assert result.get_own_licenses() == []

    def test_and_so_is_a_third_party_one(self):
        result = self._result("third-party", "third_party_notice")

        assert result.get_own_licenses() == []

    def test_but_a_declared_one_is_kept(self):
        result = self._result("declared", "license_file")

        assert [lic.spdx_id for lic in result.get_own_licenses()] == ["Apache-2.0"]


class TestTheSameTwoRulesOnTheCodePath:
    """The document set and the code set are separate copies of the same
    forms, so a test written against a README pins only one of them."""

    def test_a_capture_stops_at_the_end_of_a_sentence(self, tmp_path):
        """Capitalised, so the line does open a declaration. What must not
        happen is the name running on into the next sentence: "BSD-2-Clause
        License. The bundled CSS minifier is" was normalised to BSD-3-Clause,
        a licence the file never names."""
        evidence = _evidence(
            tmp_path, "widget.c",
            "/* Licensed under the BSD-2-Clause License. The bundled CSS\n"
            "   minifier is licensed under the Apache License. */\n",
        )
        found = {spdx for spdx, _, _ in evidence}

        assert "BSD-3-Clause" not in found, evidence
        assert "BSD-2-Clause" in _declared(evidence), evidence

    def test_a_wrapped_comment_does_not_open_a_declaration(self, tmp_path):
        """The continuation line starts with a lower case verb."""
        evidence = _evidence(
            tmp_path, "widget.c",
            "/* This bundles terser. terser is\n"
            " * licensed under the BSD-2-Clause License. */\n",
        )

        assert _declared(evidence) == set(), evidence

    def test_but_the_capitalised_form_still_does(self, tmp_path):
        evidence = _evidence(
            tmp_path, "widget.c", " * Licensed under the MIT License.\n",
        )

        assert "MIT" in _declared(evidence), evidence


class TestTheSubjectMayTakeEitherArticle:
    """"The package is licensed under" says the same as "This package is"."""

    @pytest.mark.parametrize("subject", [
        "The package", "The project", "The library", "The module",
        "The contents", "This source code", "The source code",
    ])
    def test_it_declares(self, tmp_path, subject):
        evidence = _evidence(
            tmp_path, "README.md", f"{subject} is licensed under the MIT License.\n",
        )

        assert "MIT" in _declared(evidence), (subject, evidence)


class TestADocumentNamedWithASuffixThatIsNotOne:
    """README.1st was listed and unreachable, because the check that found it
    also refused any name containing a dot."""

    def test_it_is_read_as_a_document(self, tmp_path):
        evidence = _evidence(
            tmp_path, "README.1st",
            "Bundled dependencies:\n* Licensed under the MIT License.\n",
        )

        assert _declared(evidence) == set(), evidence


class TestWhatTheCapitalisationRuleGivesUp:
    """Written down as a test so it is a decision on the record.

    A line opening "licensed under the MIT License" in lower case, with no
    subject, is not read as a declaration. Some projects do write their
    header that way. The alternative is accepting it, and then every
    hard-wrapped credit whose continuation line begins with the same words is
    a declaration too, at confidence 1.0, for a licence the package does not
    have. Over-claiming someone else's licence is the worse of the two.
    """

    def test_a_lower_case_subjectless_header_is_not_read(self, tmp_path):
        evidence = _evidence(tmp_path, "widget.c", "// licensed under the MIT License.\n")

        assert _declared(evidence) == set(), evidence

    def test_capitalising_it_is_enough(self, tmp_path):
        evidence = _evidence(tmp_path, "widget.c", "// Licensed under the MIT License.\n")

        assert "MIT" in _declared(evidence), evidence

    def test_and_so_is_naming_the_subject(self, tmp_path):
        evidence = _evidence(
            tmp_path, "widget.c", "// this file is licensed under the MIT License.\n",
        )

        assert "MIT" in _declared(evidence), evidence
