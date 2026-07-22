"""License detection accuracy regression tests.

Covers the two accuracy problems reported in issue #76:

1. Over-matching that emitted invalid or extra SPDX identifiers (e.g.
   ``MIT-or-later``, which is not a real SPDX id, or a spurious second BSD
   variant). Detection must never emit an identifier outside the SPDX list.

2. Canonical license texts that failed to classify (starting with ISC). A
   corpus of canonical texts must each resolve to their single expected id.
"""

import pytest

from osslili.core.models import Config
from osslili.detectors.license_detector import LicenseDetector


# Canonical license texts as they ship in real packages. The ISC cases mirror
# picocolors@1.1.1: one with the "ISC License" heading and one canonical file
# that opens directly with the copyright line (the case that regressed).
ISC_CANONICAL = """Copyright (c) 2021-2024 Oleksii Raspopov, Kostiantyn Denysov, Anton Verinov

Permission to use, copy, modify, and/or distribute this software for any
purpose with or without fee is hereby granted, provided that the above
copyright notice and this permission notice appear in all copies.

THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
"""

ISC_WITH_HEADING = "ISC License\n\n" + ISC_CANONICAL

MIT_CANONICAL = """(The MIT License)

Copyright (c) 2014 Jonathan Ong
Copyright (c) 2015 Douglas Christopher Wilson

Permission is hereby granted, free of charge, to any person obtaining
a copy of this software and associated documentation files (the
'Software'), to deal in the Software without restriction, including
without limitation the rights to use, copy, modify, merge, publish,
distribute, sublicense, and/or sell copies of the Software, and to
permit persons to whom the Software is furnished to do so, subject to
the following conditions:

The above copyright notice and this permission notice shall be
included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED 'AS IS', WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
"""

BSD_2_CLAUSE_CANONICAL = """Copyright (c) 2015, Scott Motte
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

1. Redistributions of source code must retain the above copyright notice,
   this list of conditions and the following disclaimer.

2. Redistributions in binary form must reproduce the above copyright notice,
   this list of conditions and the following disclaimer in the documentation
   and/or other materials provided with the distribution.

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


# (fixture filename, license text, expected single SPDX id)
CANONICAL_CORPUS = [
    ("isc_canonical_LICENSE", ISC_CANONICAL, "ISC"),
    ("isc_heading_LICENSE", ISC_WITH_HEADING, "ISC"),
    ("mit_LICENSE", MIT_CANONICAL, "MIT"),
    ("bsd2_LICENSE", BSD_2_CLAUSE_CANONICAL, "BSD-2-Clause"),
]


@pytest.fixture(scope="module")
def detector():
    det = LicenseDetector(Config())
    # Force the SPDX license data to load so validity checks are authoritative.
    _ = det.spdx_data.licenses
    return det


def _detect_ids(detector, tmp_path, filename, text):
    license_file = tmp_path / filename
    license_file.write_text(text)
    detected = detector.detect_licenses(license_file)
    return sorted({d.spdx_id for d in detected})


@pytest.mark.parametrize("filename,text,expected", CANONICAL_CORPUS)
def test_canonical_text_classifies_to_single_expected_id(
    detector, tmp_path, filename, text, expected
):
    """Each canonical license text resolves to exactly its expected SPDX id."""
    ids = _detect_ids(detector, tmp_path, filename, text)
    assert ids == [expected], (
        f"{filename} classified as {ids}, expected exactly ['{expected}']"
    )


@pytest.mark.parametrize("filename,text,expected", CANONICAL_CORPUS)
def test_canonical_text_emits_only_valid_spdx_ids(
    detector, tmp_path, filename, text, expected
):
    """No detection over the corpus emits an identifier outside the SPDX list."""
    license_file = tmp_path / filename
    license_file.write_text(text)
    for detected in detector.detect_licenses(license_file):
        assert detector._is_valid_spdx_id(detected.spdx_id), (
            f"Non-SPDX identifier '{detected.spdx_id}' emitted from {filename}"
        )


def test_invalid_spdx_tag_is_not_emitted(detector, tmp_path):
    """An invented identifier such as 'MIT-or-later' must never be emitted."""
    source = tmp_path / "index.js"
    source.write_text("// SPDX-License-Identifier: MIT-or-later\nconsole.log(1);\n")
    ids = _detect_ids(detector, tmp_path, "index.js", source.read_text())
    assert "MIT-or-later" not in ids


def test_valid_gnu_or_later_tag_is_emitted(detector, tmp_path):
    """The '-or-later' guard rejects fakes but keeps real GNU suffixed ids."""
    source = tmp_path / "gnu.c"
    source.write_text("/* SPDX-License-Identifier: GPL-2.0-or-later */\nint main(){}\n")
    detected = detector.detect_licenses(source)
    assert detected, "expected a GNU license detection"
    for d in detected:
        assert detector._is_valid_spdx_id(d.spdx_id)


class TestEmittableLicenseIdGuard:
    """Unit coverage for the SPDX-list emission guard."""

    @pytest.mark.parametrize("license_id", [
        "MIT",
        "ISC",
        "BSD-2-Clause",
        "GPL-2.0-or-later",
        "GPL-2.0+",
        "MIT OR Apache-2.0",
        "GPL-3.0-only WITH Classpath-exception-2.0",
        "NOASSERTION",
        "LicenseRef-Custom",
    ])
    def test_accepts_valid_identifiers(self, detector, license_id):
        assert detector._is_emittable_license_id(license_id)

    @pytest.mark.parametrize("license_id", [
        "MIT-or-later",
        "BSD-or-later",
        "Bogus-License",
        "the",
        "",
    ])
    def test_rejects_invalid_identifiers(self, detector, license_id):
        assert not detector._is_emittable_license_id(license_id)
