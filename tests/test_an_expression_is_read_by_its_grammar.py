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
        "GPLv2 or later",
        "GPL-2.0 or later",
        "LGPL-2.1 or later",
    ])
    def test_the_grant_written_in_words_stays_with_its_licence(self, detector, written):
        """"or later" is the whole of what the grant says. The parser reads
        the "or" as an operator, and keeping the pieces reports the licence
        without the permission, which is the opposite of what it grants."""
        assert detector._parse_license_expression(written) == [written]

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
