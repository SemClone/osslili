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
