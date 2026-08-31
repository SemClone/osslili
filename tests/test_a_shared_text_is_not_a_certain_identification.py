"""An exact match on a text several licences share is not certainty.

Sixteen texts on the SPDX list belong to more than one identifier. Eight of
those groups have members whose obligations genuinely differ:

    MPL-2.0   vs MPL-2.0-no-copyleft-exception
    OFL-1.1   vs OFL-1.1-RFN vs OFL-1.1-no-RFN
    GFDL-1.3  vs GFDL-1.3-invariants vs GFDL-1.3-no-invariants
    CAL-1.0   vs CAL-1.0-Combined-Work-Exception

The scanner answered with whichever it found first, at confidence 1.0 and
category `declared`. For MPL that is the dangerous direction: a project that
marks Exhibit B carries `MPL-2.0-no-copyleft-exception`, whose code cannot be
relicensed under the GPL, and reporting plain `MPL-2.0` at full confidence
tells a consumer the combination is allowed.

Issue #142. The text is read exactly; which licence it is is not determined
by the text, and the record now says so rather than picking one and calling it
certain. Working the answer out from the notice that does distinguish them is
#144, and is a different piece of work.

Two spellings of one licence are not this. `AGPL-3.0`, `AGPL-3.0-only` and
`AGPL-3.0-or-later` share a text and oblige the same things; the grant is
settled where the licence is applied, and #140 already refuses to treat them
as near misses at each other.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from osslili import LicenseCopyrightDetector

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def detector():
    made = LicenseCopyrightDetector()
    made.license_detector.spdx_data.get_all_license_ids()
    return made


def _a_licence_file_holding(detector, spdx_id):
    root = Path(tempfile.mkdtemp())
    text = detector.license_detector.spdx_data.get_license_text(spdx_id)
    assert text, f"{spdx_id} must ship its text for this to mean anything"
    (root / "LICENSE").write_text(text)
    return root


def _hash_records(detector, root):
    """The hash tier's records for this scan, and there must be one.

    A licence whose text the tier does not answer for says nothing about the
    question, so a test that quietly found none would prove nothing.
    """
    return [
        lic
        for lic in detector.process_local_path(str(root)).licenses
        if lic.detection_method == "hash"
    ]


def _the_one_hash_record(detector, root):
    found = _hash_records(detector, root)
    assert found, "the hash tier should answer for this text"
    return found[0]


class TestTheTextIsSharedAndTheRecordSaysSo:
    @pytest.mark.parametrize(
        "spdx_id,also",
        [
            ("MPL-2.0", "MPL-2.0-no-copyleft-exception"),
            ("OFL-1.1", "OFL-1.1-RFN"),
            ("GFDL-1.3-only", "GFDL-1.3-invariants-only"),
            ("CAL-1.0", "CAL-1.0-Combined-Work-Exception"),
        ],
    )
    def test_the_other_licence_is_named(self, detector, spdx_id, also):
        found = _the_one_hash_record(detector, _a_licence_file_holding(detector, spdx_id))

        assert also in (found.ambiguous_with or []), found.ambiguous_with

    @pytest.mark.parametrize(
        "spdx_id", ["MPL-2.0", "OFL-1.1", "GFDL-1.3-only", "CAL-1.0"]
    )
    def test_it_is_no_longer_reported_as_certain(self, detector, spdx_id):
        found = _the_one_hash_record(detector, _a_licence_file_holding(detector, spdx_id))

        assert found.confidence < 1.0, found.confidence
        assert found.match_type == "exact_hash_shared_text"

    @pytest.mark.parametrize(
        "spdx_id", ["MPL-2.0", "OFL-1.1", "GFDL-1.3-only", "CAL-1.0"]
    )
    def test_the_licence_is_still_reported(self, detector, spdx_id):
        """Uncertainty is not a reason to say nothing.

        The text is certainly one of a known few, so dropping the record
        would lose a licence the file plainly carries.
        """
        found = _the_one_hash_record(detector, _a_licence_file_holding(detector, spdx_id))

        assert found.spdx_id == spdx_id


class TestALicenceThatOwnsItsTextIsUnchanged:
    @pytest.mark.parametrize(
        # Licences whose text belongs to them alone, and which the hash tier
        # answers for. Apache-2.0 is deliberately not here: its text reaches
        # the reader by another route, so it says nothing about this tier.
        "spdx_id", ["MIT", "BSD-3-Clause", "ISC", "Sleepycat", "Zlib", "PostgreSQL"]
    )
    def test_it_is_still_certain(self, detector, spdx_id):
        found = _the_one_hash_record(detector, _a_licence_file_holding(detector, spdx_id))

        assert found.confidence == 1.0, found.confidence
        assert found.match_type == "exact_hash"
        assert not found.ambiguous_with


class TestTwoSpellingsOfOneLicenceAreNotAmbiguous:
    """The grant is settled where the licence is applied, not in the text.

    `AGPL-3.0-only` and `AGPL-3.0-or-later` share a text, and #140 already
    refuses to treat them as near misses. They must not be reported as an
    ambiguity either, or every GNU-family licence file would carry one.
    """

    @pytest.mark.parametrize(
        "spdx_id", ["AGPL-3.0-only", "GFDL-1.1-only", "AGPL-1.0-only"]
    )
    def test_the_twin_is_not_called_an_ambiguity(self, detector, spdx_id):
        found = _the_one_hash_record(detector, _a_licence_file_holding(detector, spdx_id))

        named = found.ambiguous_with or []
        assert not [
            other for other in named if other.startswith(spdx_id.rsplit("-", 1)[0])
            and ("only" in other or "later" in other)
            and "invariants" not in other
        ], named


class TestTheReportCarriesIt:
    def test_the_evidence_names_the_alternatives(self, detector):
        root = _a_licence_file_holding(detector, "MPL-2.0")

        finished = subprocess.run(
            [sys.executable, "-m", "osslili", "-f", "evidence", str(root)],
            capture_output=True, text=True, cwd=REPO_ROOT,
        )
        assert finished.returncode == 0, finished.stderr
        report = json.loads(finished.stdout[finished.stdout.index("{"):])

        shared = [
            e
            for scanned in report["scan_results"]
            for e in scanned.get("license_evidence", [])
            if e.get("match_type") == "exact_hash_shared_text"
        ]
        assert shared, report
        assert shared[0]["ambiguous_with"] == ["MPL-2.0-no-copyleft-exception"]
        assert "cannot say which" in shared[0]["description"]

    def test_an_unambiguous_record_carries_no_such_field(self, detector):
        root = _a_licence_file_holding(detector, "MIT")

        finished = subprocess.run(
            [sys.executable, "-m", "osslili", "-f", "evidence", str(root)],
            capture_output=True, text=True, cwd=REPO_ROOT,
        )
        report = json.loads(finished.stdout[finished.stdout.index("{"):])

        for scanned in report["scan_results"]:
            for e in scanned.get("license_evidence", []):
                assert "ambiguous_with" not in e, e
