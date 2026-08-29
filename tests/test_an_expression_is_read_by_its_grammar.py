"""An SPDX expression is read by its grammar, not by patterns.

An expression is terms joined by OR, AND and WITH, nested in brackets, with a
deprecated "or later" plus. Taking that apart with patterns meant every shape
had to be thought of separately, and each one that was not either reported a
licence the file does not grant or dropped one it does. Issue #113 took twelve
rounds of review to find the shapes, and #118 found the same fault in four
tables.

The grammar comes from the SPDX expression parser. The vocabulary does not:
it is built from the licence list osslili ships, so that only the grammar
comes from outside and an upgrade of the library cannot change what a scan
reports.
"""

import pytest


@pytest.fixture(scope="module")
def detector():
    from osslili.core.models import Config
    from osslili.detectors.license_detector import LicenseDetector

    return LicenseDetector(Config())


class TestEveryIdentifierMeansItself:
    """The sweep that would have caught the vocabulary being swapped for
    another tool's, and that pins what a library upgrade may change."""

    def test_every_shipped_identifier_comes_back_as_itself(self, detector):
        wrong = {
            spdx_id: detector._parse_license_expression(spdx_id)
            for spdx_id in sorted(detector.spdx_data.licenses)
            if detector._parse_license_expression(spdx_id) != [spdx_id]
        }

        assert not wrong, wrong

    def test_and_there_are_as_many_as_are_shipped(self, detector):
        """So the test above cannot pass by having nothing to check."""
        assert len(detector.spdx_data.licenses) > 600

    @pytest.mark.parametrize("written,expected", [
        ("Net-SNMP", "Net-SNMP"),
        ("bzip2-1.0.5", "bzip2-1.0.5"),
        ("GPL", "GPL"),
        ("BSD-2-Clause-FreeBSD", "BSD-2-Clause-FreeBSD"),
        ("StandardML-NJ", "StandardML-NJ"),
    ])
    def test_the_names_another_vocabulary_would_have_rewritten(
        self, detector, written, expected
    ):
        """Each of these means something else in the list the library ships
        with, and one of them, Net-SNMP, is not in it at all and so was
        reported as no licence."""
        assert detector._parse_license_expression(written) == [expected]


class TestTheShapesOfAnExpression:
    @pytest.mark.parametrize("expression,expected", [
        ("MIT OR Apache-2.0", ["MIT", "Apache-2.0"]),
        ("MIT AND Apache-2.0", ["MIT", "Apache-2.0"]),
        ("MIT or Apache-2.0", ["MIT", "Apache-2.0"]),
        ("( MIT OR Apache-2.0 )", ["MIT", "Apache-2.0"]),
        ("((MIT OR Apache-2.0))", ["MIT", "Apache-2.0"]),
        ("mit OR apache-2.0", ["MIT", "Apache-2.0"]),
        ("MIT, Apache-2.0", ["MIT", "Apache-2.0"]),
        ("(MIT, BSD-3-Clause)", ["MIT", "BSD-3-Clause"]),
        ("MIT, Apache-2.0 OR BSD-3-Clause", ["MIT", "Apache-2.0", "BSD-3-Clause"]),
    ])
    def test_every_term_is_named(self, detector, expression, expected):
        assert detector._parse_license_expression(expression) == expected

    def test_an_exception_is_named_with_its_licence(self, detector):
        named = detector._parse_license_expression(
            "GPL-2.0 WITH Classpath-exception-2.0"
        )

        assert named == ["GPL-2.0", "Classpath-exception-2.0"], named

    def test_the_kernel_writes_it_nested(self, detector):
        named = detector._parse_license_expression(
            "((GPL-2.0 WITH Linux-syscall-note) OR BSD-2-Clause)"
        )

        assert named == ["GPL-2.0", "Linux-syscall-note", "BSD-2-Clause"], named

    def test_a_reference_to_a_licence_held_elsewhere(self, detector):
        named = detector._parse_license_expression(
            "DocumentRef-upstream:LicenseRef-foo OR MIT"
        )

        assert "MIT" in named, named


class TestANameWrittenInWords:
    """A term with a space in it is not an identifier, so the parser has taken
    a name apart rather than read it. Such a name goes back whole for the
    reader that knows prose, and the identifiers beside it are kept."""

    @pytest.mark.parametrize("written", [
        "GNU General Public License v2.0 or later",
        "The MIT License (MIT)",
        "Apache License 2.0",
        "BSD 3-Clause License",
    ])
    def test_it_is_not_taken_apart(self, detector, written):
        assert detector._parse_license_expression(written) == [written]

    def test_and_an_identifier_beside_it_is_still_read(self, detector):
        """One name in words does not make the rest of the line unreadable."""
        named = detector._parse_license_expression("MIT or Apache License 2.0")

        assert named == ["MIT", "Apache License 2.0"], named

    @pytest.mark.parametrize("written", [
        "GPL-2.0 or later",
        "LGPL-2.1 or later",
    ])
    def test_the_grant_written_in_words_stays_with_its_licence(self, detector, written):
        """"or later" is the whole of what the grant says. The parser reads
        the "or" as an operator, and keeping the pieces reports the licence
        without the permission, which is the opposite of what it grants."""
        assert detector._parse_license_expression(written) == [written]

    def test_a_licence_whose_grant_cannot_be_kept_is_not_reported(self, detector):
        """"GPLv2" is not an identifier, so the grant will not go back on it,
        and the GNU family says which grant it means in the name itself.
        Reporting GPL-2.0-only there gives the one permission the line does
        not, so the piece is dropped, and with nothing left the line goes
        back whole for a reader that may do better with it."""
        named = detector._parse_license_expression("GPLv2 or later")

        assert named == ["GPLv2 or later"], named
        assert "GPLv2" not in named

    def test_a_term_the_list_does_not_hold_is_still_a_term(self, detector):
        """Absence from the list is not the same as being words. A deprecated
        form and a description of a licence are both written as terms."""
        assert detector._parse_license_expression("GFDL-1.3+ or MIT") == [
            "GFDL-1.3+", "MIT",
        ]
        assert detector._parse_license_expression("MIT AND BSD-compatible") == [
            "MIT", "BSD-compatible",
        ]


class TestSomethingThatIsNotAnExpressionAtAll:
    @pytest.mark.parametrize("written", ["", "   "])
    def test_nothing_names_nothing(self, detector, written):
        assert detector._parse_license_expression(written) == []

    @pytest.mark.parametrize("written", [
        "See the file COPYING for details",
        "Proprietary - all rights reserved",
    ])
    def test_a_string_the_parser_refuses_comes_back_whole(self, detector, written):
        """For the tiers after this one to make sense of. What it must not do
        is hand back a line that does hold an expression: doing that for
        "Dual license: GPL-2.0 or MIT" got the GPL out of it and lost the
        MIT, which the class above covers."""
        assert detector._parse_license_expression(written) == [written]


class TestTheGrantWrittenAsAPhrase:
    """"or later" is written as one word and as several. A list of words
    could not see the longer spellings, so "GPL-2.0 or any later version"
    kept the GPL-2.0 alone and reported the opposite permission."""

    @pytest.mark.parametrize("written", [
        "GPL-2.0 or later",
        "GPL-2.0 or any later version",
        "GPL-2.0 or greater",
        "GPL-2.0 or above",
        "LGPL-2.1 or any later version",
    ])
    def test_the_grant_stays_with_its_licence(self, detector, written):
        assert detector._parse_license_expression(written) == [written]

    @pytest.mark.parametrize("written,expected", [
        ("GPL-2.0 or later", "GPL-2.0-or-later"),
        ("GPL-2.0 or any later version", "GPL-2.0-or-later"),
        ("LGPL-2.1 or later", "LGPL-2.1-or-later"),
    ])
    def test_and_is_read_as_the_grant_it_is(self, detector, written, expected):
        """Which is the point of keeping it: the licence alone means the
        opposite."""
        assert detector._normalize_license_id(written).rstrip('+') + (
            '-or-later' if detector._normalize_license_id(written).endswith('+') else ''
        ) == expected

    def test_a_grant_no_one_writes_that_way_keeps_the_licence(self, detector):
        """SPDX has no or-later form for Apache, so nothing can be made of
        the line whole, and the pieces are better than nothing."""
        assert detector._parse_license_expression("Apache 2.0 or above") == [
            "Apache 2.0",
        ]


class TestALabelInFrontOfAnExpression:
    """"Dual license: GPL-2.0 or MIT" makes the parser refuse the whole line.
    Handing that to the reader of prose names got the GPL out of it and lost
    the MIT."""

    @pytest.mark.parametrize("written,expected", [
        ("Dual license: GPL-2.0 or MIT", ["GPL-2.0", "MIT"]),
        ("License: MIT OR Apache-2.0", ["MIT", "Apache-2.0"]),
    ])
    def test_the_expression_after_it_is_read(self, detector, written, expected):
        assert detector._parse_license_expression(written) == expected

    def test_and_something_with_no_expression_in_it_still_comes_back_whole(
        self, detector
    ):
        written = "See the file COPYING for details"

        assert detector._parse_license_expression(written) == [written]


class TestAWordThatOnlyNamesALicenceInCompany:
    """"Affero", "Lesser" and "Library" name a GNU licence next to the GNU
    name and not otherwise. Claiming them anywhere took a string away from
    the steps that would have read it."""

    @pytest.mark.parametrize("written,expected", [
        ("zlib library 1.2", "Zlib"),
        ("lesser gplv2.1", "LGPL-v2"),
        ("library gplv2", "LGPL-v2"),
        ("affero gplv3", "AGPL-v3"),
        ("library general public license 2", "LGPL-v2"),
    ])
    def test_the_company_it_keeps(self, detector, written, expected):
        assert detector._normalize_license_id(written) == expected


class TestALineNamingTwoLicencesAndAGrant:
    """The grant speaks about the licence it was written after, and the line
    names another beside it. Handing the whole line to the reader of prose
    names answered with one family and lost the other."""

    @pytest.mark.parametrize("written,expected", [
        ("MIT or GPL-2.0 or later", ["MIT", "GPL-2.0+"]),
        ("MIT or LGPL-2.1 or later", ["MIT", "LGPL-2.1+"]),
        ("MIT or GPL-2.0 or any later version", ["MIT", "GPL-2.0+"]),
    ])
    def test_both_are_named_and_the_grant_kept(self, detector, written, expected):
        assert detector._parse_license_expression(written) == expected

    def test_the_grant_goes_on_the_one_before_it(self, detector):
        """Not on the first, and not on all of them."""
        named = detector._parse_license_expression("GPL-2.0 or MIT or later")

        assert named == ["GPL-2.0", "MIT"], named

    def test_and_a_licence_with_no_or_later_form_keeps_its_name(self, detector):
        """SPDX writes one for the GNU family and nowhere else, so a plus on
        anything else names nothing and would lose the licence."""
        named = detector._parse_license_expression("MIT or Apache-2.0 or above")

        assert named == ["MIT", "Apache-2.0"], named


class TestWhichLicenceTheGrantSpeaksAbout:
    """The GNU names contain one another, so finding where each was written
    has to match the whole name: "gpl-2.0" is inside "lgpl-2.0" and at a
    later place than the LGPL itself, which put the grant on the licence that
    was not written there and left the one that was with the wrong
    permission."""

    @pytest.mark.parametrize("written,expected", [
        ("GPL-2.0 or LGPL-2.0 or later", ["GPL-2.0", "LGPL-2.0+"]),
        ("LGPL-2.0 or GPL-2.0 or later", ["LGPL-2.0", "GPL-2.0+"]),
        ("GPL-3.0 or AGPL-3.0 or later", ["GPL-3.0", "AGPL-3.0+"]),
        ("AGPL-3.0 or GPL-3.0 or later", ["AGPL-3.0", "GPL-3.0+"]),
        ("GPL-2 or LGPL-2.1 or later", ["GPL-2", "LGPL-2.1+"]),
    ])
    def test_it_lands_on_the_one_written_before_it(self, detector, written, expected):
        assert detector._parse_license_expression(written) == expected

    def test_it_is_the_nearest_one_before_it(self, detector):
        """A name written twice is followed by the grant at its second
        place, not its first, and the grant speaks about the one it
        follows."""
        named = detector._parse_license_expression(
            "GPL-2.0 or MIT or GPL-2.0 or later"
        )

        assert named == ["GPL-2.0+", "MIT"], named

    def test_the_two_orders_do_not_agree_by_accident(self, detector):
        """Both orders being right is the point: one of them passed while the
        other was wrong, which is how the fault stayed hidden."""
        one = detector._parse_license_expression("GPL-2.0 or LGPL-2.0 or later")
        other = detector._parse_license_expression("LGPL-2.0 or GPL-2.0 or later")

        assert one != other, (one, other)


class TestALicenceTheWorkIsAlsoUnder:
    """A term of an AND is a licence the work is under as well, not instead.
    Leaving one out says the work is under fewer terms than it is."""

    def test_a_term_of_an_and_is_never_dropped(self, detector):
        """Even where its grant cannot be kept. "MIT AND GPLv2 or later" came
        back as MIT, and whoever read that would not know about the
        copyleft."""
        named = detector._parse_license_expression("MIT AND GPLv2 or later")

        assert "MIT" in named and any("GPL" in key for key in named), named

    def test_but_an_alternative_still_is(self, detector):
        """Where the licences are alternatives, saying nothing about one is
        better than saying the opposite of what it grants."""
        assert detector._parse_license_expression("MIT or GPLv2 or later") == ["MIT"]


class TestTheExceptionAndTheGrantTogether:
    """The form that took the longest to get right in #113, now with the
    grant written in words as well."""

    def test_the_grant_and_the_exception_both_survive(self, detector):
        named = detector._parse_license_expression(
            "GPL-2.0 or later WITH Classpath-exception-2.0"
        )

        assert named == ["GPL-2.0+", "Classpath-exception-2.0"], named

    def test_a_comma_list_carrying_a_grant(self, detector):
        named = detector._parse_license_expression("GPL-2.0 or later, MIT")

        assert "MIT" in named, named
        assert any(key.startswith("GPL-2.0") for key in named), named


class TestWhatTheReportSays:
    """Every other test here asks the reader. These ask what comes out, which
    is the only thing a consumer sees, and the two have disagreed before."""

    def _reported(self, tmp_path, value):
        import json
        import subprocess
        import sys
        from pathlib import Path

        root = Path(__file__).resolve().parents[1]
        (tmp_path / "package.json").write_text(
            json.dumps({"name": "x", "version": "1.0.0", "license": value})
        )
        result = subprocess.run(
            [sys.executable, "-m", "osslili", "-f", "evidence", str(tmp_path)],
            capture_output=True, text=True, cwd=root,
        )
        assert result.returncode == 0, result.stderr
        data = json.loads(result.stdout[result.stdout.find("{"):])
        return {
            record["detected_license"]
            for scan in data["scan_results"]
            for record in scan["license_evidence"]
        }

    @pytest.mark.parametrize("value,expected", [
        ("MIT OR Apache-2.0", {"MIT", "Apache-2.0"}),
        ("MIT or GPL-2.0 or later", {"MIT", "GPL-2.0-or-later"}),
        ("GPL-2.0 or later", {"GPL-2.0-or-later"}),
        ("Dual license: GPL-2.0 or MIT", {"GPL-2.0-only", "MIT"}),
    ])
    def test_what_is_reported(self, tmp_path, value, expected):
        assert expected <= self._reported(tmp_path, value), value

    def test_a_grant_that_cannot_be_kept_reports_nothing_for_it(self, tmp_path):
        """Rather than the licence with the opposite permission."""
        found = self._reported(tmp_path, "GPLv2 or later")

        assert "GPL-2.0-only" not in found, found
