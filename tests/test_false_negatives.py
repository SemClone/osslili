"""Regression tests for the false negatives introduced in 1.7.1.

1.7.1 fixed a class of false positives (issues #90 and #91) and, in doing so,
created a larger class of false negatives. Its own tests could not see them:
they asserted that licenses which *should* resolve still did, which cannot
detect a license that stopped resolving, and every fixture was a full LICENSE
file drawn from the minority of SPDX entries that ship their text — exactly the
population where the new failures do not occur.

These tests cover what that corpus could not:

* source-file license headers, not just LICENSE files
* licenses whose text is *not* bundled, so the fuzzy tier cannot corroborate
* the direction that matters most for compliance — a license that used to be
  identified and now is not, or copyleft reported as permissive
"""

import tempfile
from pathlib import Path

import pytest

from osslili.core.models import Config
from osslili.detectors.license_detector import LicenseDetector


# The header the FSF itself recommends, and therefore the most widely used
# license header in existence. The version attaches to "the License", not to
# "GPL", which is what the 1.7.1 version regex failed to parse.
FSF_GPL2_HEADER = """/*
 * demo.c - part of the demo project
 *
 * Copyright (C) 2024 Example Corp
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation; either version 2 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
 */

int main(void) { return 0; }
"""

FSF_GPL3_HEADER = FSF_GPL2_HEADER.replace(
    "version 2 of the License", "version 3 of the License"
)

# A GPL grant carrying a linking exception. Files like this are, by definition,
# GPL-licensed — the exception is granted *over* the GPL, not instead of it.
GPL_WITH_LINKING_EXCEPTION = """/*
 * Copyright (C) 2024 Example Corp
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation; either version 3 of the License, or
 * (at your option) any later version.
 *
 * In addition, as a special exception, the copyright holders give
 * permission to link the code of this program with the OpenSSL library.
 */
int main(void) { return 0; }
"""

# "compatibility" as an ordinary English word inside a real grant sentence.
ZLIB_GRANT_MENTIONING_COMPATIBILITY = (
    "minizip is distributed under the zlib license, ensuring compatibility\n"
    "with both open source and commercial products.\n"
)

LGPL_21_MENTION = (
    "This library is distributed under the GNU Lesser General Public "
    "License version 2.1.\n"
)


@pytest.fixture(scope="module")
def detector():
    det = LicenseDetector(Config())
    _ = det.spdx_data.licenses
    return det


def _ids(detector, filename, text):
    with tempfile.TemporaryDirectory() as td:
        path = Path(td, filename)
        path.write_text(text)
        return {d.spdx_id for d in detector.detect_licenses(path)}


def _detections(detector, filename, text):
    with tempfile.TemporaryDirectory() as td:
        path = Path(td, filename)
        path.write_text(text)
        return detector.detect_licenses(path)


class TestSourceHeaderGrants:
    """A license header in source must still be identified.

    Requiring an explicit GNU version was right; the version regex was too
    narrow to read the phrasing licenses actually use.
    """

    @pytest.mark.parametrize("label,text,expected", [
        ("GPL-2 FSF header", FSF_GPL2_HEADER, "GPL-2.0"),
        ("GPL-3 FSF header", FSF_GPL3_HEADER, "GPL-3.0"),
    ])
    def test_canonical_fsf_header_is_identified(self, detector, label, text, expected):
        ids = _ids(detector, "demo.c", text)
        assert any(i.startswith(expected) for i in ids), (
            f"{label} reported {ids or 'nothing'}; a GPL source file must not "
            f"read as carrying no license"
        )

    def test_any_later_version_resolves_to_or_later(self, detector):
        """"or (at your option) any later version" is an -or-later grant."""
        ids = _ids(detector, "demo.c", FSF_GPL2_HEADER)
        assert "GPL-2.0-or-later" in ids, (
            f"expected GPL-2.0-or-later for a header offering later versions, got {ids}"
        )

    def test_version_only_grant_is_not_reported_as_or_later(self, detector):
        """Without the later-version clause the grant is version-specific."""
        text = (
            "/* This program is distributed under the terms of the GNU General\n"
            " * Public License, version 2 of the License.\n"
            " */\n"
        )
        ids = _ids(detector, "demo.c", text)
        assert "GPL-2.0-or-later" not in ids, (
            f"read an -or-later grant where the text offers only version 2: {ids}"
        )

    def test_informal_separatorless_mention(self, detector):
        """"licensed under GPL2" is common in READMEs."""
        ids = _ids(detector, "README.md", "This project is licensed under GPL2.\n")
        assert any(i.startswith("GPL-2.0") for i in ids), f"got {ids}"


class TestLinkingExceptionKeepsItsGrant:
    """A linking exception carves out a library; it does not remove the grant."""

    def test_gpl_grant_survives_its_own_linking_exception(self, detector):
        ids = _ids(detector, "demo.c", GPL_WITH_LINKING_EXCEPTION)
        assert any(i.startswith("GPL-3.0") for i in ids), (
            f"a GPL file carrying a linking exception reported {ids or 'nothing'}"
        )

    def test_carved_out_library_is_still_not_asserted(self, detector):
        """The reason the guard exists must keep working."""
        ids = _ids(detector, "demo.c", GPL_WITH_LINKING_EXCEPTION)
        assert "OpenSSL" not in ids, (
            f"asserted the carved-out library's license: {ids}"
        )


class TestCompatibilityIsNotAlwaysDiscussion:
    """"compatibility" is an ordinary word, not only a licensing claim."""

    def test_grant_mentioning_compatibility_is_kept(self, detector):
        ids = _ids(detector, "README.md", ZLIB_GRANT_MENTIONING_COMPATIBILITY)
        assert "Zlib" in ids, (
            f"a genuine zlib grant was suppressed by the word 'compatibility': {ids}"
        )

    def test_licensing_compatibility_claim_is_still_discussion(self, detector):
        """The PSF-stack case that motivated the guard must stay suppressed."""
        text = (
            "Historically, most, but not all, Python releases have also been\n"
            "GPL-compatible; the table below summarizes the various releases.\n"
        )
        ids = _ids(detector, "LICENSE", text)
        assert not [i for i in ids if "GPL" in i.upper()], (
            f"asserted a GPL identifier from a compatibility note: {ids}"
        )


class TestGnuVariantsAreNotClaimedAsGpl:
    """Lesser and Affero have their own identifiers."""

    def test_lgpl_mention_does_not_assert_plain_gpl(self, detector):
        ids = _ids(detector, "README.md", LGPL_21_MENTION)
        assert not [i for i in ids if i.startswith("GPL-")], (
            f"claimed a plain GPL identifier for an LGPL mention: {ids}"
        )
        assert any(i.startswith("LGPL-2.1") for i in ids), f"got {ids}"


class TestUnidentifiableTextIsNotConfident:
    """A pattern hit on text no tier could identify is not a full-confidence
    identification.

    A Sleepycat license file was reported as BSD-3-Clause at 1.0 because the
    BSD clauses it shares matched patterns — copyleft as permissive, with
    nothing in the output to signal doubt.
    """

    UNKNOWN_LICENSE_TEXT = """Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

1. Redistributions of source code must retain the above copyright notice,
   this list of conditions and the following disclaimer.

2. Redistributions in any form must be accompanied by information on how to
   obtain complete source code for this software and any accompanying
   software that uses this software.  The source code must either be
   included in the distribution or be available for no more than the cost
   of distribution plus a nominal fee, and must be freely redistributable
   under reasonable conditions.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS "AS IS" AND ANY EXPRESS
OR IMPLIED WARRANTIES ARE DISCLAIMED.
"""

    def test_regex_fallback_is_capped(self, detector):
        for detected in _detections(detector, "LICENSE", self.UNKNOWN_LICENSE_TEXT):
            if detected.detection_method == "regex":
                assert detected.confidence <= 0.6, (
                    f"{detected.spdx_id} asserted at {detected.confidence} from a "
                    f"pattern match on text no tier could identify"
                )

    def test_regex_fallback_cannot_outrank_a_text_match(self, detector):
        """Whatever it reports must not look like an identification."""
        detections = _detections(detector, "LICENSE", self.UNKNOWN_LICENSE_TEXT)
        regex_hits = [d for d in detections if d.detection_method == "regex"]
        if regex_hits:
            assert max(d.confidence for d in regex_hits) < 0.85, (
                "a regex fallback outranks a keyword identification"
            )


try:  # pragma: no cover - the import is the test
    import tlsh as _tlsh  # noqa: F401
    HAS_TLSH = True
except ImportError:  # pragma: no cover
    HAS_TLSH = False


@pytest.mark.skipif(
    not HAS_TLSH,
    reason="the corroborated band this covers only exists with the TLSH backend",
)
class TestSimilarityThresholdGate:
    """A corroborated similarity match must not be discarded by the caller.

    The similarity tier accepts a strong score outright and a weaker one only
    when TLSH corroborates it. The cascade then re-checked the result against
    ``similarity_threshold``, which is higher than the tier's own floor — so
    every corroborated match below the threshold was computed, confirmed, and
    thrown away, making the corroboration step dead code.

    Real cost: protobuf and multiprocess ship BSD-3-Clause license files that
    scored 0.957 and 0.932 against the bundled BSD-3-Clause text, and both were
    reported as carrying no license at all.
    """

    BSD_3_SLIGHTLY_REWORDED = """Copyright 2024 Example Corp.  All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

    * Redistributions of source code must retain the above copyright
notice, this list of conditions and the following disclaimer.
    * Redistributions in binary form must reproduce the above
copyright notice, this list of conditions and the following disclaimer
in the documentation and/or other materials provided with the
distribution.
    * Neither the name of Example Corp nor the names of its
contributors may be used to endorse or promote products derived from
this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
"AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
(INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
"""

    # A trailing clause of the kind projects really do ship beside the license
    # text. It drops the similarity score to 0.955 -- inside the band that was
    # computed, TLSH-corroborated, and then discarded.
    TRAILER = """
Code generated by the compiler is owned by the owner of the input file
used when generating it.  This code is not standalone and requires a
support library to be linked with it.  This support library is itself
covered by the above license.
"""

    def test_corroborated_match_below_threshold_is_reported(self, detector):
        """A real license text scoring under the threshold still resolves."""
        text = self.BSD_3_SLIGHTLY_REWORDED + self.TRAILER
        ids = _ids(detector, "LICENSE", text)
        assert "BSD-3-Clause" in ids, (
            f"a recognizable BSD-3-Clause file reported {ids or 'nothing'}"
        )

    def test_the_fixture_really_sits_below_the_threshold(self, detector):
        """Guards the test above: if the fixture drifts over the threshold it
        would pass without exercising the band at all."""
        text = self.BSD_3_SLIGHTLY_REWORDED + self.TRAILER
        result = detector._tier1_dice_sorensen(text, Path("LICENSE"))
        assert result is not None
        assert result.confidence < detector.config.similarity_threshold, (
            f"fixture scores {result.confidence}, at or above the threshold"
        )
        assert result.confidence >= 0.9

    def test_reported_confidence_is_the_measured_score(self, detector):
        """The score is passed through, not rounded up to the threshold."""
        text = self.BSD_3_SLIGHTLY_REWORDED + self.TRAILER
        for detected in _detections(detector, "LICENSE", text):
            if detected.detection_method == "dice-sorensen":
                assert 0.9 <= detected.confidence < 0.97
                return


class TestCorroborationRequiresAConfirmer:
    """The weaker-score band must stay shut when nothing can corroborate.

    ``python-tlsh`` is optional and needs a C toolchain, so a plain
    ``pip install osslili`` usually has no TLSH. ``confirm_license_match``
    answers True when it cannot check — sensible on its own, but a caller
    treating that as corroboration gets a rubber stamp. Accepting the band on
    that basis reported a Sleepycat license file as BSD-3-Clause at 0.91: the
    texts really are that similar, and the clauses that differ are the point.
    """

    @pytest.fixture
    def detector_without_tlsh(self, monkeypatch):
        import osslili.detectors.tlsh_detector as tlsh_module
        monkeypatch.setattr(tlsh_module, "TLSH_AVAILABLE", False)
        det = LicenseDetector(Config())
        _ = det.spdx_data.licenses
        assert not det.tlsh_detector.can_confirm
        return det

    def test_band_stays_shut_without_a_confirmer(self, detector_without_tlsh):
        """A sub-threshold similarity match is not accepted unverified."""
        text = (
            TestSimilarityThresholdGate.BSD_3_SLIGHTLY_REWORDED
            + TestSimilarityThresholdGate.TRAILER
        )
        for detected in _detections(detector_without_tlsh, "LICENSE", text):
            if detected.detection_method == "dice-sorensen":
                assert detected.confidence >= detector_without_tlsh.config.similarity_threshold, (
                    f"accepted an uncorroborated {detected.confidence} match with "
                    f"no confirmer available"
                )

    def test_strong_matches_are_unaffected(self, detector_without_tlsh):
        """Licenses that match outright must not need a confirmer at all."""
        ids = _ids(
            detector_without_tlsh,
            "LICENSE",
            TestSimilarityThresholdGate.BSD_3_SLIGHTLY_REWORDED,
        )
        assert "BSD-3-Clause" in ids, f"got {ids}"

    def test_can_confirm_reports_availability(self, detector):
        """The flag must reflect reality where TLSH *is* installed."""
        import osslili.detectors.tlsh_detector as tlsh_module
        assert detector.tlsh_detector.can_confirm == tlsh_module.TLSH_AVAILABLE
