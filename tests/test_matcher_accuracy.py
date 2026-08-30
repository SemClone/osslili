"""Matcher accuracy regression tests for issues #90 and #91.

Both issues share a failure shape: a matcher asserted a license the scanned
text does not carry, and did so at a confidence that outranked the matcher
that had it right.

1. Issue #91 — the keyword matcher read license *discussion* as a grant. The
   PSF license stack describes at length how Python relates to the GPL while
   being distributed under Python-2.0, and a keyword hit on that prose asserted
   ``GPL-2.0-or-later``: copyleft claimed over a permissive package.

2. Issue #90 — the TLSH matcher reported the nearest fuzzy-hash neighbour as
   the declared license. TLSH measures bulk document similarity, so licenses
   that differ by one clause are indistinguishable to it: canonical MIT text
   sits closer to the JSON license than to MIT. Those clauses are exactly what
   changes the obligations.
"""

import pytest

from osslili.core.models import Config
from osslili.detectors.license_detector import LicenseDetector


# The Python license stack as shipped by CPython and typing_extensions: a
# history section, GPL-compatibility footnotes, the PSF agreement, and the CNRI
# clause that mentions material "previously distributed under the GNU General
# Public License". Every GPL mention here is commentary; the grant is PSF's.
PSF_LICENSE_STACK = """A. HISTORY OF THE SOFTWARE
==========================

Python was created in the early 1990s by Guido van Rossum at Stichting
Mathematisch Centrum (CWI) in the Netherlands as a successor of a language
called ABC.

All Python releases are Open Source (see https://opensource.org for the Open
Source Definition).  Historically, most, but not all, Python releases have
also been GPL-compatible; the table below summarizes the various releases.

Footnotes:

(1) GPL-compatible doesn't mean that we're distributing Python under
    the GPL.  All Python licenses, unlike the GPL, let you distribute
    a modified version without making your changes open source.  The
    GPL-compatible licenses make it possible to combine Python with
    other software that is released under the GPL; the others don't.

(2) According to Richard Stallman, 1.6.1 is not GPL-compatible, because
    its license has a choice of law clause.

B. TERMS AND CONDITIONS FOR ACCESSING OR OTHERWISE USING PYTHON
===============================================================

PYTHON SOFTWARE FOUNDATION LICENSE VERSION 2
--------------------------------------------

1. This LICENSE AGREEMENT is between the Python Software Foundation
("PSF"), and the Individual or Organization ("Licensee") accessing and
otherwise using this software in source or binary form and its
associated documentation.

2. Subject to the terms and conditions of this License Agreement, PSF hereby
grants Licensee a nonexclusive, royalty-free, world-wide license to reproduce,
analyze, test, perform and/or display publicly, prepare derivative works,
distribute, and otherwise use this software alone or in any derivative version.

7. Nothing in this License Agreement shall be deemed to create any
relationship of agency, partnership, or joint venture between PSF and
Licensee.

ACCEPT
------

CNRI LICENSE AGREEMENT FOR PYTHON 1.6.1
---------------------------------------

7. This License Agreement shall be governed by the federal intellectual
property law of the United States.  Notwithstanding the foregoing, with
regard to derivative works based on Python 1.6.1 that incorporate
non-separable material that was previously distributed under the GNU
General Public License (GPL), the law of the Commonwealth of Virginia
shall govern this License Agreement.
"""

# Canonical MIT text, as a package ships it. The JSON license is this text plus
# "The Software shall be used for Good, not Evil." — one sentence apart, and
# the pair TLSH could not separate.
MIT_CANONICAL = """MIT License

Copyright (c) 2008-2020 Andrey Petrov and contributors

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

# Canonical BSD-3-Clause, as Flask and Click ship it. BSD-4-Clause is this text
# plus the advertising clause; BSD-3-Clause-HP is a near-identical variant.
BSD_3_CLAUSE_CANONICAL = """Copyright 2014 Pallets

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

1.  Redistributions of source code must retain the above copyright notice,
    this list of conditions and the following disclaimer.

2.  Redistributions in binary form must reproduce the above copyright notice,
    this list of conditions and the following disclaimer in the documentation
    and/or other materials provided with the distribution.

3.  Neither the name of the copyright holder nor the names of its contributors
    may be used to endorse or promote products derived from this software
    without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
POSSIBILITY OF SUCH DAMAGE.
"""


@pytest.fixture(scope="module")
def detector():
    det = LicenseDetector(Config())
    _ = det.spdx_data.licenses
    return det


def _detect(detector, tmp_path, filename, text):
    license_file = tmp_path / filename
    license_file.write_text(text)
    return detector.detect_licenses(license_file)


def _ids(detector, tmp_path, filename, text):
    return sorted({d.spdx_id for d in _detect(detector, tmp_path, filename, text)})


class TestKeywordDiscussionProse:
    """Issue #91: a license discussed is not a license granted."""

    def test_psf_stack_does_not_assert_gpl(self, detector, tmp_path):
        """The PSF stack's GPL commentary must not yield a GPL identifier."""
        ids = _ids(detector, tmp_path, "LICENSE", PSF_LICENSE_STACK)
        gpl_ids = [i for i in ids if "GPL" in i.upper()]
        assert not gpl_ids, (
            f"asserted {gpl_ids} from a package licensed under the PSF stack; "
            f"every GPL mention in that text is compatibility or history prose"
        )

    def test_psf_stack_is_recognised(self, detector, tmp_path):
        """Suppressing the GPL false positive must not silence the real answer."""
        ids = _ids(detector, tmp_path, "LICENSE", PSF_LICENSE_STACK)
        assert "Python-2.0" in ids, f"PSF stack classified as {ids}"

    @pytest.mark.parametrize("prose", [
        "This library is GPL-compatible, but is distributed under the MIT license.",
        "Unlike the GPL, this license does not require you to publish changes.",
        "Material previously distributed under the GNU General Public License "
        "has been removed.",
    ])
    def test_discussion_prose_yields_no_gpl(self, detector, tmp_path, prose):
        ids = _ids(detector, tmp_path, "NOTICE", prose)
        assert not [i for i in ids if "GPL" in i.upper()], (
            f"asserted a GPL identifier from discussion prose: {prose!r} -> {ids}"
        )

    def test_linking_exception_does_not_assert_the_carved_out_license(
        self, detector, tmp_path
    ):
        """A linking exception names a library to carve it out, not to adopt it.

        The GPL "special exception" boilerplate names the library it permits
        linking against; that library's license does not govern the file.
        """
        text = (
            "In addition, as a special exception, Nokia gives permission to link\n"
            "the code of its release of Qt with the OpenSSL project's \"OpenSSL\"\n"
            "library (or modified versions of it that use the same license as the\n"
            "\"OpenSSL\" library), and distribute the linked executables.\n"
        )
        ids = _ids(detector, tmp_path, "LICENSE", text)
        assert "OpenSSL" not in ids, (
            f"asserted the OpenSSL license from a linking exception: {ids}"
        )


class TestUnversionedGnuMention:
    """Issue #91: an unversioned GPL mention names a family, not a license.

    GPL-2.0-only and GPL-3.0-only are mutually incompatible, so resolving a
    bare "General Public License" to either one invents an obligation.
    """

    def test_unversioned_mention_yields_no_identifier(self, detector, tmp_path):
        text = "This program is distributed under the terms of the General Public License.\n"
        ids = _ids(detector, tmp_path, "COPYING", text)
        assert not [i for i in ids if "GPL" in i.upper()], (
            f"guessed {ids} from a mention that names no version"
        )

    @pytest.mark.parametrize("text,expected", [
        ("This program is distributed under the terms of the GNU GPL version 2.\n",
         "GPL-2.0"),
        ("This program is distributed under the terms of the GNU GPL version 3.\n",
         "GPL-3.0"),
        ("Licensed under the GNU General Public License v3.\n", "GPL-3.0"),
    ])
    def test_versioned_mention_resolves_to_that_version(
        self, detector, tmp_path, text, expected
    ):
        ids = _ids(detector, tmp_path, "COPYING", text)
        # Emitted in modern SPDX form, so the bare id appears with a suffix.
        assert any(i.startswith(expected) for i in ids), (
            f"{text!r} classified as {ids}, expected a {expected} identifier"
        )

    def test_a_year_is_not_a_version(self, detector, tmp_path):
        """The old version sniffer accepted any digit in a 200-character window."""
        text = (
            "Copyright 2003 Example Corp.\n"
            "Redistribution is governed by the General Public License referenced above.\n"
        )
        ids = _ids(detector, tmp_path, "NOTICE", text)
        assert "GPL-3.0-only" not in ids and "GPL-3.0-or-later" not in ids, (
            f"read the year 2003 as a GPL version: {ids}"
        )


class TestKeywordWordBoundaries:
    """A short identifier must not match inside an ordinary word.

    "MIT" occurs in "permitted" and "limitation", which run throughout the
    LGPL and MPL texts.
    """

    @pytest.mark.parametrize("text", [
        "Redistribution is permitted under the terms of this license.\n",
        "Including without limitation the rights granted under this license.\n",
    ])
    def test_mit_inside_a_word_is_not_a_match(self, detector, tmp_path, text):
        ids = _ids(detector, tmp_path, "NOTICE", text)
        assert "MIT" not in ids, f"matched MIT inside a word: {text!r} -> {ids}"

    def test_real_mit_mention_still_matches(self, detector, tmp_path):
        keywords = detector._detect_license_keywords(
            "This project is distributed under the MIT License.\n",
            tmp_path / "README.md",
        )
        assert "MIT" in {k.spdx_id for k in keywords}


class TestTlshCorroboration:
    """Issue #90: TLSH proposes candidates; it does not get to decide."""

    NEAR_NEIGHBOUR_CASES = [
        ("LICENSE.txt", MIT_CANONICAL, "MIT", "JSON"),
        ("LICENSE.txt", BSD_3_CLAUSE_CANONICAL, "BSD-3-Clause", "BSD-4-Clause"),
    ]

    @pytest.mark.parametrize(
        "filename,text,actual,near_neighbour", NEAR_NEIGHBOUR_CASES
    )
    def test_near_neighbour_is_not_asserted(
        self, detector, tmp_path, filename, text, actual, near_neighbour
    ):
        """The neighbour a clause away must never be reported for this text."""
        result = detector.tlsh_detector.detect_license_tlsh(text, tmp_path / filename)
        assert result is None or result.spdx_id != near_neighbour, (
            f"TLSH reported {near_neighbour} for {actual} text"
        )

    @pytest.mark.parametrize(
        "filename,text,actual,near_neighbour", NEAR_NEIGHBOUR_CASES
    )
    def test_pipeline_reports_the_actual_license(
        self, detector, tmp_path, filename, text, actual, near_neighbour
    ):
        ids = _ids(detector, tmp_path, filename, text)
        assert ids == [actual], f"{actual} text classified as {ids}"

    def test_a_candidate_its_text_contradicts_is_not_asserted(self, detector):
        """A proposal the license's own text does not support is dropped.

        This used to be tested with the JSON license, which shipped no text,
        so the proposal could not be checked at all. Every license on the list
        carries its text now (#126), so the case that remains is the one that
        always mattered: the text is there and it disagrees.
        """
        tlsh_detector = detector.tlsh_detector
        assert tlsh_detector.spdx_data.get_license_text("GPL-3.0-only")

        # MIT text against a GPL-3.0-only proposal. The texts are nothing
        # alike, so nothing substantiates it.
        assert tlsh_detector._corroborate(MIT_CANONICAL, [(3, "GPL-3.0-only")]) is None

    def test_a_candidate_with_no_text_is_not_asserted(self, detector):
        """The path is kept even though the bundled list no longer takes it.

        Silence beats a license assertion nothing can check, whether the text
        is missing because SPDX has none or because the id is not one of ours.
        """
        tlsh_detector = detector.tlsh_detector
        assert tlsh_detector.spdx_data.get_license_text("Not-A-Real-License") is None

        assert tlsh_detector._corroborate(
            MIT_CANONICAL, [(3, "Not-A-Real-License")]
        ) is None

    def test_corroborated_candidate_reports_text_agreement(self, detector, tmp_path):
        """Confidence is the measured agreement, not a fixed floor."""
        corroborated = detector.tlsh_detector._corroborate(
            MIT_CANONICAL, [(29, "MIT")]
        )
        assert corroborated is not None, "MIT text should corroborate the MIT candidate"
        license_id, similarity = corroborated
        assert license_id == "MIT"
        assert similarity >= 0.95, (
            f"canonical MIT text agrees with the MIT license text at only {similarity}"
        )
