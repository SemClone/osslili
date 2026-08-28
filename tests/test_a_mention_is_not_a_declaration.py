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
        "// License: MIT\n",
        " * License: MIT\n",
        "<!-- License: MIT -->\n",
    ])
    def test_but_a_line_of_its_own_still_does(self, tmp_path, text):
        evidence = _evidence(tmp_path, "README.md", text)

        assert "MIT" in _declared(evidence), evidence


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
        "Also licensed under MIT",
        "The software is licensed under the MIT License.",
    ])
    def test_it_declares(self, tmp_path, line):
        evidence = _evidence(tmp_path, "Widget.java", line + "\n")

        assert _declared(evidence), (line, evidence)
        assert _referenced(evidence) == set(), (line, evidence)

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
        evidence = _evidence(tmp_path, "source.txt", prefix + "License: MIT\n")

        assert "MIT" in _declared(evidence), (prefix, evidence)

    @pytest.mark.parametrize("prefix", [
        "# ", "// ", " * ", "<!-- ", "; ", "% ", "(* ", "-- ", "   ", "",
    ])
    def test_and_so_is_an_identifier_line(self, tmp_path, prefix):
        evidence = _evidence(tmp_path, "source.txt", prefix + "SPDX-License-Identifier: MIT\n")

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
