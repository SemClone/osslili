"""SPDX keeps exceptions on a list of their own, and now so does osslili.

What follows WITH in an expression is a licence exception: `GPL-2.0-only WITH
Classpath-exception-2.0`. It is not a licence, and it never stands alone.
Until now the scan had no way to know that except by looking for the word
"exception" in the identifier, which is a guess about spelling rather than a
question about what the identifier is.

The guess was wrong in both directions. Two licences carry the word in their
own names, `CAL-1.0-Combined-Work-Exception` and
`MPL-2.0-no-copyleft-exception`, and the scan dropped them wherever they were
declared until 1.10.0. And an exception that did not carry the word would
have been read as a licence.

This is the list, so the question can be asked instead of guessed. Nothing
reads it yet; reporting exceptions alongside their licence is issue #24, and
this is the piece that has to exist first.
"""

import json
from pathlib import Path

import pytest

from osslili import LicenseCopyrightDetector

REPO_ROOT = Path(__file__).resolve().parents[1]


def _scanned(detector, root):
    """The licences a scan of this directory reports, source files included."""
    detector.config.deep_scan = True
    detector.config.license_files_only = False
    try:
        return detector.process_local_path(str(root)).licenses
    finally:
        detector.config.deep_scan = False
        detector.config.license_files_only = True


@pytest.fixture(scope="module")
def detector():
    made = LicenseCopyrightDetector()
    made.license_detector.spdx_data.get_all_license_ids()
    return made


@pytest.fixture(scope="module")
def spdx():
    made = LicenseCopyrightDetector()
    made.license_detector.spdx_data.get_all_license_ids()
    return made.license_detector.spdx_data


class TestTheListIsShipped:
    def test_it_is_in_the_bundled_data(self):
        """Read from the file rather than through the loader, so that a
        packaging change that stops shipping it is caught here."""
        bundled = json.loads(
            (REPO_ROOT / "osslili" / "data" / "spdx_licenses.json").read_text()
        )

        assert "exceptions" in bundled, sorted(bundled)
        assert len(bundled["exceptions"]) > 50, len(bundled["exceptions"])

    def test_the_loader_reads_it(self, spdx):
        assert len(spdx.exceptions) > 50, len(spdx.exceptions)

    def test_each_one_carries_a_name(self, spdx):
        without = [
            exception_id
            for exception_id, about in spdx.exceptions.items()
            if not about.get("name")
        ]
        assert not without, without


class TestAnExceptionIsNotALicence:
    """The two lists do not overlap, which is what makes asking worthwhile."""

    def test_no_identifier_is_on_both(self, spdx):
        both = set(spdx.exceptions) & set(spdx.licenses)

        assert not both, sorted(both)

    @pytest.mark.parametrize(
        "spdx_id",
        ["Classpath-exception-2.0", "LLVM-exception", "GCC-exception-3.1",
         "Autoconf-exception-3.0", "Font-exception-2.0"],
    )
    def test_the_common_ones_are_there(self, spdx, spdx_id):
        assert spdx.names_an_exception(spdx_id)

    @pytest.mark.parametrize(
        "spdx_id",
        [
            # The two the spelling test dropped. They are licences, and the
            # whole reason for shipping the list is to stop guessing from the
            # word in the name.
            "CAL-1.0-Combined-Work-Exception",
            "MPL-2.0-no-copyleft-exception",
            "MIT",
            "GPL-2.0-only",
        ],
    )
    def test_a_licence_is_not_one_however_it_is_named(self, spdx, spdx_id):
        assert not spdx.names_an_exception(spdx_id)

    def test_it_is_asked_without_regard_to_case(self, spdx):
        assert spdx.names_an_exception("classpath-exception-2.0")

    def test_nothing_is_not_one(self, spdx):
        assert not spdx.names_an_exception("")
        assert not spdx.names_an_exception("   ")


class TestTheDownloaderFetchesIt:
    def test_the_script_asks_for_the_exception_list(self):
        """The bundled data is generated. A list nothing refreshes goes stale
        the first time SPDX adds an exception."""
        script = (REPO_ROOT / "scripts" / "download_spdx_licenses.py").read_text()

        assert "exceptions.json" in script
        assert '"exceptions"' in script


class TestAnExceptionIsReportedWithItsLicence:
    """One record, because there is one licence and a condition on it.

    OR and AND join two licences and give two records. WITH qualifies one, so
    the licence goes in `spdx_id` and the condition in `exception`.
    """

    @pytest.mark.parametrize(
        "declared,licence,exception",
        [
            ("GPL-2.0-only WITH Classpath-exception-2.0",
             "GPL-2.0-only", "Classpath-exception-2.0"),
            ("Apache-2.0 WITH LLVM-exception",
             "Apache-2.0", "LLVM-exception"),
            ("GPL-3.0-or-later WITH GCC-exception-3.1",
             "GPL-3.0-or-later", "GCC-exception-3.1"),
            # The deprecated plus form keeps its grant as well as its
            # exception. Losing the plus reported the opposite permission.
            ("GPL-2.0+ WITH Classpath-exception-2.0",
             "GPL-2.0-or-later", "Classpath-exception-2.0"),
        ],
    )
    def test_the_licence_and_the_exception_are_both_kept(
        self, detector, tmp_path, declared, licence, exception
    ):
        (tmp_path / "widget.c").write_text(
            f"// SPDX-License-Identifier: {declared}\nint w(void){{return 0;}}\n"
        )

        found = _scanned(detector, tmp_path)

        assert [(lic.spdx_id, lic.exception) for lic in found] == \
            [(licence, exception)], found

    def test_the_exception_is_not_a_record_of_its_own(self, detector, tmp_path):
        """It is not a licence, so it must not be reported as one."""
        (tmp_path / "widget.c").write_text(
            "// SPDX-License-Identifier: GPL-2.0-only WITH Classpath-exception-2.0\n"
        )

        found = _scanned(detector, tmp_path)

        assert "Classpath-exception-2.0" not in {lic.spdx_id for lic in found}

    def test_a_choice_written_after_an_exception_still_survives(
        self, detector, tmp_path
    ):
        """What #120 was protecting. The MIT must not be lost to the WITH."""
        (tmp_path / "widget.c").write_text(
            "// SPDX-License-Identifier: GPL-2.0-only WITH"
            " Classpath-exception-2.0 or MIT\n"
        )

        found = _scanned(detector, tmp_path)

        assert {lic.spdx_id for lic in found} == {"GPL-2.0-only", "MIT"}, found
        granted = {lic.spdx_id: lic.exception for lic in found}
        assert granted["GPL-2.0-only"] == "Classpath-exception-2.0", granted
        assert granted["MIT"] is None, granted

    def test_a_licence_after_with_is_not_an_exception(self, detector, tmp_path):
        """`GPL-2.0-only WITH MIT` is malformed, and MIT is not an exception.

        Taken as one, a licence would be filed under a field nothing reports
        as a licence.
        """
        licence, exception = detector.license_detector._the_licence_and_its_exception(
            "GPL-2.0-only WITH MIT"
        )

        assert exception is None
        assert licence == "GPL-2.0-only WITH MIT"

    def test_a_licence_with_no_exception_carries_none(self, detector, tmp_path):
        (tmp_path / "widget.c").write_text(
            "// SPDX-License-Identifier: MIT\nint w(void){return 0;}\n"
        )

        found = _scanned(detector, tmp_path)

        assert [(lic.spdx_id, lic.exception) for lic in found] == [("MIT", None)]


class TestTheReportCarriesTheExpression:
    def test_the_evidence_names_both(self, detector, tmp_path):
        (tmp_path / "widget.c").write_text(
            "// SPDX-License-Identifier: GPL-2.0-only WITH Classpath-exception-2.0\n"
        )

        written = [
            entry.to_dict() for entry in _scanned(detector, tmp_path)
        ]

        assert written[0]["exception"] == "Classpath-exception-2.0", written

    def test_a_record_with_no_exception_carries_no_such_field(
        self, detector, tmp_path
    ):
        (tmp_path / "widget.c").write_text(
            "// SPDX-License-Identifier: MIT\nint w(void){return 0;}\n"
        )

        written = [entry.to_dict() for entry in _scanned(detector, tmp_path)]

        assert "exception" not in written[0], written


class TestAGrantWrittenInWordsIsPartOfTheExpression:
    """"GPL-2.0 or later" in a header was trimmed to "GPL-2.0".

    The line was cut before the parser or the normaliser saw it, by the step
    that strips whatever else is on a header line: a closing comment marker,
    a note such as "(see LICENSE)". A grant is not that. It was reported as
    `-only`, the opposite permission, which is what #118 costs (issue #155).
    """

    @pytest.mark.parametrize(
        "declared,expected",
        [
            ("GPL-2.0 or later", [("GPL-2.0-or-later", None)]),
            ("GPL-2.0 or any later version", [("GPL-2.0-or-later", None)]),
            # The hyphenated and plus forms were never affected, and must
            # stay where they were.
            ("GPL-2.0-or-later", [("GPL-2.0-or-later", None)]),
            ("GPL-2.0+", [("GPL-2.0-or-later", None)]),
            # And the grant carries its exception across, which is what the
            # issue was originally filed about.
            ("GPL-2.0 or later WITH Classpath-exception-2.0",
             [("GPL-2.0-or-later", "Classpath-exception-2.0")]),
            ("GPL-2.0-or-later WITH Classpath-exception-2.0",
             [("GPL-2.0-or-later", "Classpath-exception-2.0")]),
            ("GPL-2.0+ WITH Classpath-exception-2.0",
             [("GPL-2.0-or-later", "Classpath-exception-2.0")]),
        ],
    )
    def test_the_grant_survives_the_header(
        self, detector, tmp_path, declared, expected
    ):
        (tmp_path / "widget.c").write_text(
            f"// SPDX-License-Identifier: {declared}\nint w(void){{return 0;}}\n"
        )

        found = _scanned(detector, tmp_path)

        assert [(lic.spdx_id, lic.exception) for lic in found] == expected, found

    def test_and_never_reads_as_only(self, detector, tmp_path):
        (tmp_path / "widget.c").write_text(
            "// SPDX-License-Identifier: GPL-2.0 or later\n"
        )

        found = {lic.spdx_id for lic in _scanned(detector, tmp_path)}

        assert "GPL-2.0-only" not in found and "GPL-2.0" not in found, found

    def test_a_note_after_the_licence_is_still_trimmed(self, detector, tmp_path):
        """What the trimming is for. Only a grant is spared, not prose."""
        (tmp_path / "widget.c").write_text(
            "// SPDX-License-Identifier: BSD-2-Clause see LICENSE\n"
        )

        found = {lic.spdx_id for lic in _scanned(detector, tmp_path)}

        assert found == {"BSD-2-Clause"}, found

    def test_a_real_choice_is_not_read_as_a_grant(self, detector, tmp_path):
        """"or" before a licence is still an operator."""
        (tmp_path / "widget.c").write_text(
            "// SPDX-License-Identifier: MIT or Apache-2.0\n"
        )

        found = {lic.spdx_id for lic in _scanned(detector, tmp_path)}

        assert found == {"MIT", "Apache-2.0"}, found
