"""An SPDX identifier a file states is the identifier reported back.

Everything the normaliser does is for turning vague input into an identifier:
"BSD" into BSD-3-Clause, "lgpl" into LGPL-2.1. Those guesses used to run
before anything checked whether the input was already exact, so a file saying
SPDX-License-Identifier: BSD-2-Clause was reported as BSD-3-Clause, at
confidence 1.0, from an unambiguous declaration. That is a different licence:
BSD-3-Clause carries a non-endorsement clause BSD-2-Clause does not.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
BUNDLED = REPO_ROOT / "osslili" / "data" / "spdx_licenses.json"


def _bundled_identifiers():
    with open(BUNDLED) as handle:
        return json.load(handle)["licenses"]


def _reported(tmp_path, text, name="LICENSE"):
    """What the tool says about a file, through the interface a caller uses."""
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
        (evidence.get("detected_license"), evidence.get("match_type"))
        for scan in data.get("scan_results", [])
        for evidence in scan.get("license_evidence", [])
    ]


def _tagged(tmp_path, identifier):
    reported = _reported(tmp_path, f"SPDX-License-Identifier: {identifier}\n")
    tags = [spdx for spdx, match_type in reported if match_type == "header_tag"]
    return tags[0] if tags else None


# The families that collapsed: each has a sibling that differs in a term
# someone relies on, and each used to be reported as that sibling.
@pytest.mark.parametrize("identifier", [
    "BSD-2-Clause", "BSD-3-Clause", "BSD-4-Clause",
    "LGPL-2.1-only", "LGPL-2.1-or-later",
    "GPL-2.0-only", "GPL-2.0-or-later", "GPL-3.0-only", "GPL-3.0-or-later",
    "AGPL-3.0-only", "AGPL-3.0-or-later",
    "Apache-2.0", "Apache-1.1", "MIT", "ISC", "0BSD", "Zlib", "MPL-2.0",
])
class TestAStatedIdentifierIsReportedBack:
    def test_it_is(self, tmp_path, identifier):
        assert _tagged(tmp_path, identifier) == identifier

    def test_and_the_case_it_was_written_in_does_not_matter(self, tmp_path, identifier):
        assert _tagged(tmp_path, identifier.lower()) == identifier


class TestEveryIdentifierInTheBundledList:
    """The families above are the ones that were wrong. This is the rest of
    them, so the next family to be given a shortcut is caught here."""

    def test_normalising_one_never_produces_a_different_one(self):
        from osslili.utils.license_normalizer import LicenseNormalizer

        class Data:
            licenses = _bundled_identifiers()

        normalizer = LicenseNormalizer()
        changed = {
            identifier: normalizer.normalize_license_id(identifier, Data())
            for identifier in Data.licenses
        }
        wrong = {
            given: got for given, got in changed.items() if got != given
        }

        assert wrong == {}, dict(list(wrong.items())[:20])

    def test_and_the_sweep_read_the_whole_list(self):
        """Without this the test above passes by checking nothing."""
        assert len(_bundled_identifiers()) > 500


class TestVagueInputStillResolves:
    """The guesses are still there, and still wanted: a package saying
    "License: BSD" has said something, just not precisely."""

    @pytest.mark.parametrize("given,expected", [
        ("BSD", "BSD-3-Clause"),
        ("bsd", "BSD-3-Clause"),
        ("Apache", "Apache-2.0"),
        ("MIT License", "MIT"),
        ("python", "Python-2.0"),
    ])
    def test_it_does(self, tmp_path, given, expected):
        reported = _reported(tmp_path, f"License: {given}\n")
        tags = [spdx for spdx, match_type in reported if match_type == "header_tag"]

        assert tags and tags[0] == expected, (given, tags)
