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
