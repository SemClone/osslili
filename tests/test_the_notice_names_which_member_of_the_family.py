"""A shared text names a family; the project's own notice names the member.

Seven texts on the SPDX list are shared by licences that oblige different
things. #142 stopped the scanner picking one of them and calling it certain:
such a match is reported with `ambiguous_with` naming the alternatives. This
is the other half -- working the answer out (issue #144).

What separates the members is written down, just not in the licence file:

    MPL-2.0-no-copyleft-exception   Exhibit B, attached in the source headers
    OFL-1.1-RFN                     a Reserved Font Name after the copyright
    GFDL-1.3-invariants-*           the document names its Invariant Sections
    CAL-1.0-Combined-Work-Exception the identifier itself, in a source header

Two things make it real work, and most of what is asserted here is about
them.

The phrase is in the licence text too. `Incompatible With Secondary Licenses`
occurs five times in MPL-2.0, because the licence defines the notice it is
asking for; `Invariant Section` occurs twenty times in GFDL-1.3. A reader
that did not know the difference would mark every MPL project as carrying
Exhibit B, which is the direction that costs something: it says code cannot
be relicensed under the GPL when it can. So the notice has to be recognised
where a project *applies* it and refused where the licence *defines* it.

And it needs cross-file inference. A notice in `src/main.c` changes the
identifier reported for `LICENSE`. Nothing else in osslili works that way.
"""

import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

import pytest

from osslili import LicenseCopyrightDetector
from osslili.detectors import family_notices

REPO_ROOT = Path(__file__).resolve().parents[1]

EXHIBIT_B = (
    '/* This Source Code Form is subject to the terms of the Mozilla Public\n'
    ' * License, v. 2.0. If a copy of the MPL was not distributed with this\n'
    ' * file, You can obtain one at http://mozilla.org/MPL/2.0/. */\n'
    '\n'
    '/* This Source Code Form is "Incompatible With Secondary Licenses", as\n'
    ' * defined by the Mozilla Public License, v. 2.0. */\n'
    '\n'
    'int main(void) { return 0; }\n'
)

# One line, as SIL writes it, and as it has to be: the hash tier drops a
# copyright line before comparing texts, and it drops one line. A statement
# wrapped onto a second line leaves that second line in the text, so the file
# no longer matches the licence at all and there is no family to settle.
A_RESERVED_FONT_NAME = (
    'Copyright (c) 2011, Foo Foundry (https://example.com), '
    'with Reserved Font Name "Wobble".\n\n'
)

# What SIL ships for a font author to fill in. Every OFL.txt in the world
# that nobody edited carries this, and it declares nothing.
THE_UNFILLED_TEMPLATE = (
    'Copyright (c) <dates>, <Copyright Holder> (<URL|email>), '
    'with Reserved Font Name <Reserved Font Name>.\n\n'
)


def _naming_invariant_sections(titles='"History" and "Credits"'):
    return (
        "The Wobble Manual\n\n"
        "Copyright (c) 2011 Foo. Permission is granted to copy, distribute\n"
        "and/or modify this document under the terms of the GNU Free\n"
        "Documentation License, Version 1.3; with the Invariant Sections\n"
        f"being {titles}, with no Front-Cover Texts, and with no Back-Cover\n"
        "Texts.\n"
    )


NAMING_NO_INVARIANT_SECTIONS = (
    "The Wobble Manual\n\n"
    "Copyright (c) 2011 Foo. Permission is granted to copy, distribute\n"
    "and/or modify this document under the terms of the GNU Free\n"
    "Documentation License, Version 1.3; with no Invariant Sections, no\n"
    "Front-Cover Texts, and no Back-Cover Texts.\n"
)


@pytest.fixture(scope="module")
def detector():
    made = LicenseCopyrightDetector()
    made.license_detector.spdx_data.get_all_license_ids()
    return made


def _a_project(detector, spdx_id, files=(), licence_name="LICENSE", prefix=""):
    """A directory holding a licence text, and whatever else is named."""
    root = Path(tempfile.mkdtemp())
    text = detector.license_detector.spdx_data.get_license_text(spdx_id)
    assert text, f"{spdx_id} must ship its text for this to mean anything"
    (root / licence_name).write_text(prefix + text)
    for name, content in files:
        written = root / name
        written.parent.mkdir(parents=True, exist_ok=True)
        written.write_text(content)
    return root


def _scan(detector, root, deep=False):
    detector.config.deep_scan = deep
    detector.config.license_files_only = not deep
    try:
        return detector.process_local_path(str(root)).licenses
    finally:
        detector.config.deep_scan = False
        detector.config.license_files_only = True


def _the_hash_record(detector, root, deep=False):
    """The hash tier's record for this scan, and there must be exactly one.

    A licence whose text the tier does not answer for says nothing about the
    question, so a test that quietly found none would prove nothing.
    """
    found = [
        lic for lic in _scan(detector, root, deep)
        if lic.detection_method == "hash"
    ]
    assert len(found) == 1, found
    return found[0]


class TestTheNoticeNamesTheMember:
    """The answer is recoverable, and the scan recovers it."""

    def test_exhibit_b_in_a_source_header_names_the_mpl_variant(self, detector):
        root = _a_project(detector, "MPL-2.0", [("src/main.c", EXHIBIT_B)])

        found = _the_hash_record(detector, root, deep=True)

        assert found.spdx_id == "MPL-2.0-no-copyleft-exception"
        assert found.match_type == "exact_hash_named_by_notice"
        assert not found.ambiguous_with

    def test_a_reserved_font_name_names_the_ofl_variant(self, detector):
        # The reserved name is on the copyright line, which the hash tier
        # strips before comparing texts. That is why the file still matches
        # the licence exactly and why the name is still there to read.
        root = _a_project(
            detector, "OFL-1.1", licence_name="OFL.txt",
            prefix=A_RESERVED_FONT_NAME,
        )

        found = _the_hash_record(detector, root)

        assert found.spdx_id == "OFL-1.1-RFN"

    def test_a_document_naming_its_invariant_sections(self, detector):
        root = _a_project(
            detector, "GFDL-1.3-only", [("README.md", _naming_invariant_sections())],
            licence_name="COPYING",
        )

        found = _the_hash_record(detector, root)

        assert found.spdx_id == "GFDL-1.3-invariants-only"

    def test_a_document_declaring_it_has_none(self, detector):
        root = _a_project(
            detector, "GFDL-1.3-only", [("README.md", NAMING_NO_INVARIANT_SECTIONS)],
            licence_name="COPYING",
        )

        found = _the_hash_record(detector, root)

        assert found.spdx_id == "GFDL-1.3-no-invariants-only"

    def test_two_documents_saying_opposite_things_are_read_differently(self, detector):
        """The point of the whole exercise.

        These two scans were byte-identical before #144: same identifier,
        same confidence, same evidence, for documents that oblige different
        things.
        """
        naming = _a_project(
            detector, "GFDL-1.3-only", [("README.md", _naming_invariant_sections())],
            licence_name="COPYING",
        )
        disclaiming = _a_project(
            detector, "GFDL-1.3-only", [("README.md", NAMING_NO_INVARIANT_SECTIONS)],
            licence_name="COPYING",
        )

        assert (
            _the_hash_record(detector, naming).spdx_id
            != _the_hash_record(detector, disclaiming).spdx_id
        )

    def test_an_identifier_in_a_source_header_names_the_cal_variant(self, detector):
        """The CAL's notice is the identifier itself.

        Section 2 of the licence says to mark a file with
        `SPDX-License-Identifier: CAL-1.0-Combined-Work-Exception`, so unlike
        the other three families nothing new has to be read: the tag tier
        already finds it, and what was missing was letting it answer for the
        LICENSE beside it.
        """
        root = _a_project(detector, "CAL-1.0", [
            ("src/lib.py",
             "# SPDX-License-Identifier: CAL-1.0-Combined-Work-Exception\n"),
        ])

        found = _the_hash_record(detector, root, deep=True)

        assert found.spdx_id == "CAL-1.0-Combined-Work-Exception"


class TestATemplateIsNotANotice:
    """Where the licence *defines* the notice, it is not applying it."""

    @pytest.mark.parametrize(
        "spdx_id",
        ["MPL-2.0", "GFDL-1.1-only", "GFDL-1.2-only", "GFDL-1.3-only",
         "OFL-1.0", "OFL-1.1", "CAL-1.0"],
    )
    def test_the_licence_text_alone_settles_nothing(self, detector, spdx_id):
        """A licence file and nothing else stays as ambiguous as #142 left it.

        Every phrase read by #144 also occurs in the licence that defines it.
        Matching one there would mark every project under that licence as
        carrying a variant nobody granted.
        """
        found = _the_hash_record(detector, _a_project(detector, spdx_id))

        assert found.match_type == "exact_hash_shared_text"
        assert found.ambiguous_with

    def test_sils_unfilled_placeholder_is_not_a_reserved_name(self, detector):
        """A font that never filled the template in has declared nothing.

        Asked of the reader rather than of a scan. The copyright line the
        template sits on is stripped before hashing only when it carries a
        year, and `<dates>` carries none, so an unedited OFL.txt does not
        match the licence at all and never reaches the question. What the
        reader must not do is answer it if it ever does.
        """
        text = THE_UNFILLED_TEMPLATE + (
            detector.license_detector.spdx_data.get_license_text("OFL-1.1")
        )

        assert not [
            notice for notice in family_notices.notices_in(text, "OFL.txt")
            if notice.marker == family_notices.RESERVED_FONT_NAME
        ]

    def test_a_filled_template_beneath_an_unfilled_one_is_still_read(self, detector):
        """Skipping the placeholder must not stop the reader looking."""
        text = THE_UNFILLED_TEMPLATE + A_RESERVED_FONT_NAME

        assert [
            notice for notice in family_notices.notices_in(text, "OFL.txt")
            if notice.marker == family_notices.RESERVED_FONT_NAME
        ]

    def test_but_a_manual_with_the_licence_appended_is_still_read(self, detector):
        """A GFDL manual states its grant and then prints the licence.

        That is what the licence tells an author to do -- "include a copy of
        the License in the document" -- so a guard that dismissed any file
        containing the addendum dismissed exactly the documents this reads.
        Only a notice inside the template is the template.
        """
        gfdl = detector.license_detector.spdx_data.get_license_text("GFDL-1.3-only")
        root = _a_project(detector, "GFDL-1.3-only", [
            ("MANUAL.md", _naming_invariant_sections() + "\n\n" + gfdl),
        ], licence_name="COPYING")

        found = _the_hash_record(detector, root)

        assert found.spdx_id == "GFDL-1.3-invariants-only"

    def test_the_gfdls_own_addendum_is_not_a_document_notice(self, detector):
        """`with no Invariant Sections` is printed in the GFDL itself.

        The licence closes with an addendum telling an author what to paste
        into their document, placeholders and all. A scan that read it there
        would report every GFDL work as having no invariant sections, which
        is the reading that loses obligations.
        """
        found = _the_hash_record(detector, _a_project(
            detector, "GFDL-1.3-only", licence_name="COPYING"
        ))

        assert "no-invariants" not in found.spdx_id

    def test_a_sentence_about_the_notice_is_not_the_notice(self, detector):
        """A project explaining Exhibit B has not attached it.

        The notice is attached as a header, so it opens a line after nothing
        but indentation and a comment marker -- the rule the prose patterns
        already apply to "Licensed under the Apache License". A
        CONTRIBUTING.md telling contributors not to add the marker put the
        words in a sentence, and marked the whole project as carrying the
        exception it was warning against.
        """
        root = _a_project(detector, "MPL-2.0", [("CONTRIBUTING.md", (
            "# Contributing\n\n"
            "A file that says This Source Code Form is \"Incompatible With\n"
            "Secondary Licenses\" cannot be combined with GPL code, so please\n"
            "do not add that marker.\n"
        ))])

        found = _the_hash_record(detector, root, deep=True)

        assert found.spdx_id == "MPL-2.0"
        assert found.ambiguous_with

    @pytest.mark.parametrize(
        "header",
        [
            '/* This Source Code Form is "Incompatible With Secondary\n'
            ' * Licenses", as defined by the Mozilla Public License, v. 2.0. */\n',
            '# This Source Code Form is "Incompatible With Secondary Licenses".\n',
            '// This Source Code Form is "Incompatible With Secondary Licenses".\n',
            'This Source Code Form is "Incompatible With Secondary Licenses".\n',
            # Wrapped across the comment marker, in the languages that use
            # one the cheap pre-check did not know about.
            '; This Source Code Form is "Incompatible\n'
            '; With Secondary Licenses", as defined by the MPL.\n',
            '! This Source Code Form is "Incompatible\n'
            '! With Secondary Licenses".\n',
        ],
    )
    def test_but_a_header_still_attaches_it_however_it_is_marked(self, header):
        """Refusing the sentence must not refuse the header.

        A notice pasted into a source file wraps, and carries whatever
        comment marker that language uses onto the next line.
        """
        assert [
            notice for notice in family_notices.notices_in(header, "main.c")
            if notice.marker == family_notices.EXHIBIT_B
        ], header

    def test_a_document_quoting_the_whole_licence_is_still_quoting(self, detector):
        """Not every copy of a licence text is called LICENSE.

        A README carrying the MPL in full carries Exhibit B in full with it,
        and the file was never hashed as a licence file, so the heading is
        what has to be recognised rather than the filename.
        """
        mpl = detector.license_detector.spdx_data.get_license_text("MPL-2.0")
        root = _a_project(
            detector, "MPL-2.0",
            [("README.md", "# Wobble\n\nOur licence in full:\n\n" + mpl)],
        )

        found = _the_hash_record(detector, root, deep=True)

        assert found.spdx_id == "MPL-2.0"
        assert found.ambiguous_with


class TestTheCorrectionSurvivesToTheAnswer:
    """Naming the member is worth nothing if the report still leads with the
    family."""

    def test_the_header_that_carries_both_declares_the_member(self, detector):
        """Mozilla's standard header states the identifier and attaches the
        notice, and the two are one declaration.

        Read as two they contradicted each other: the LICENSE was corrected
        to `MPL-2.0-no-copyleft-exception` at 0.95 while the header went on
        declaring plain `MPL-2.0` at 1.0, and every consumer that takes the
        most confident record reported the licence the correction was made to
        replace.
        """
        root = _a_project(detector, "MPL-2.0", [
            ("src/main.c", EXHIBIT_B + "\n// SPDX-License-Identifier: MPL-2.0\n"),
        ])

        found = _scan(detector, root, deep=True)

        assert found
        assert max(found, key=lambda lic: lic.confidence).spdx_id == \
            "MPL-2.0-no-copyleft-exception"
        assert "MPL-2.0" not in {lic.spdx_id for lic in found}

    def test_a_header_with_no_licence_file_beside_it_still_declares_it(self, detector):
        """There need not be a LICENSE for the header to mean what it means.

        The reading used to hang off an ambiguous hash record, so a source
        tree with no licence file in it -- or one file named on the command
        line -- had nothing to hang it on, and the header went on declaring
        the family it had already qualified.
        """
        root = Path(tempfile.mkdtemp())
        (root / "main.c").write_text(
            EXHIBIT_B + "\n// SPDX-License-Identifier: MPL-2.0\n"
        )

        assert {lic.spdx_id for lic in _scan(detector, root, deep=True)} == \
            {"MPL-2.0-no-copyleft-exception"}

    def test_and_so_does_that_file_named_on_its_own(self, detector):
        root = Path(tempfile.mkdtemp())
        named = root / "main.c"
        named.write_text(EXHIBIT_B + "\n// SPDX-License-Identifier: MPL-2.0\n")

        found = detector.process_local_path(str(named)).licenses

        assert {lic.spdx_id for lic in found} == {"MPL-2.0-no-copyleft-exception"}

    def test_a_manifest_naming_the_family_elsewhere_is_left_alone(self, detector):
        """Only the notice's own file is qualified by it.

        Exhibit B is attached per file: some files in a project carry it and
        others do not, so a manifest naming the family is a different claim
        about a different scope.
        """
        root = _a_project(detector, "MPL-2.0", [
            ("src/main.c", EXHIBIT_B),
            ("package.json", '{"name": "wobble", "license": "MPL-2.0"}\n'),
        ])

        found = {lic.spdx_id for lic in _scan(detector, root, deep=True)}

        assert "MPL-2.0-no-copyleft-exception" in found
        assert "MPL-2.0" in found


    def test_a_declaration_carries_to_the_rest_of_the_family_too(self, detector):
        """One text read twice must not get two answers in one scan.

        A manifest declaring `MPL-2.0-no-copyleft-exception` settled the
        LICENSE, but a README quoting the same shared text went on scoring
        against the plain family: one licence, two readings, in one scan.
        Only a notice used to carry across files, and an identifier is no
        less a statement about the project than a notice is.
        """
        mpl = detector.license_detector.spdx_data.get_license_text("MPL-2.0")
        root = _a_project(detector, "MPL-2.0", [
            ("package.json",
             '{"name": "wobble", "license": "MPL-2.0-no-copyleft-exception"}\n'),
            ("README.md", "# Wobble\n\nOur licence in full:\n\n" + mpl),
        ])

        found = _scan(detector, root)

        assert found
        assert {lic.spdx_id for lic in found} == \
            {"MPL-2.0-no-copyleft-exception"}, found

    def test_a_document_that_prints_the_licence_names_the_member_too(self, detector):
        """A manual prints the licence, and the similarity tier scores it.

        The GFDL tells an author to include a copy of the licence in the
        document, so the manual scored 0.999 against `GFDL-1.3-only` beside a
        COPYING corrected to `GFDL-1.3-invariants-only` at 0.95, and the
        higher score won. The score is not wrong; it is answering the wrong
        question, because the text it matched is the text the whole family
        shares.
        """
        gfdl = detector.license_detector.spdx_data.get_license_text("GFDL-1.3-only")
        root = _a_project(detector, "GFDL-1.3-only", [
            ("MANUAL.md", _naming_invariant_sections() + "\n\n" + gfdl),
        ], licence_name="COPYING")

        found = _scan(detector, root)

        assert found
        assert {lic.spdx_id for lic in found} == {"GFDL-1.3-invariants-only"}


class TestWhoseNoticeItIs:
    def test_a_licence_quoted_in_a_document_still_quotes_its_identifiers(self, detector):
        """The argument is about the text, not about the filename.

        A README carrying the CAL in full carries its instructions for
        marking a file, identifiers and all, exactly as a LICENSE does. Held
        to the licence-file test it declared `CAL-1.0-Combined-Work-Exception`
        at confidence 1.0 and then used that declaration to settle its own
        hash record -- the false positive this change removes, surviving
        under a different filename.
        """
        root = _a_project(detector, "CAL-1.0", licence_name="README.md")

        found = _scan(detector, root)

        assert "CAL-1.0-Combined-Work-Exception" not in {
            lic.spdx_id for lic in found
        }, found

    def test_a_project_notice_does_not_settle_a_dependency(self, detector):
        """The notice cuts the other way too.

        A vendored font under the plain OFL, bundled beside a project OFL.txt
        that names a reserved font name, had its own record rewritten to the
        project's variant on the strength of a file it has nothing to do with.
        """
        ofl = detector.license_detector.spdx_data.get_license_text("OFL-1.1")
        root = _a_project(
            detector, "OFL-1.1", [("THIRD_PARTY_NOTICES.txt", ofl)],
            licence_name="OFL.txt", prefix=A_RESERVED_FONT_NAME,
        )

        found = _scan(detector, root)

        theirs = [lic for lic in found if "THIRD_PARTY" in (lic.source_file or "")]
        assert theirs, found
        assert all(lic.spdx_id == "OFL-1.1" for lic in theirs), theirs
        assert "OFL-1.1-RFN" in {lic.spdx_id for lic in found}

    def test_a_header_shown_in_documentation_is_not_attached(self, detector):
        """Exhibit B is attached to a source file, not printed in prose.

        A CONTRIBUTING.md showing the header in a fenced code block -- to
        tell contributors *not* to add it -- opens a line with it exactly as
        the real thing does, and settled the whole project as carrying the
        exception. On a default scan, too: documentation is read without
        `--deep`, so this needed no source file to go wrong.
        """
        root = _a_project(detector, "MPL-2.0", [("CONTRIBUTING.md", (
            "# Contributing\n\n"
            "Do NOT add the following header to new files:\n\n"
            "```c\n"
            '/* This Source Code Form is "Incompatible With Secondary\n'
            " * Licenses\", as defined by the Mozilla Public License. */\n"
            "```\n\n"
            "It prevents relicensing under the GPL.\n"
        ))])

        found = _the_hash_record(detector, root)

        assert found.spdx_id == "MPL-2.0"
        assert found.ambiguous_with

    def test_nor_does_declaring_the_reserved_name_member_elsewhere(self, detector):
        """Said of the identifier, not only of the notice.

        A project can name the member outright as well as describe it, and
        `SPDX-License-Identifier: OFL-1.1-RFN` in one licence file is no more
        about the vendored font beside it than that font's copyright line is
        about this one.
        """
        ofl = detector.license_detector.spdx_data.get_license_text("OFL-1.1")
        root = _a_project(
            detector, "OFL-1.1", [("vendor/LICENSE.txt", ofl)],
            licence_name="OFL.txt",
            prefix="SPDX-License-Identifier: OFL-1.1-RFN\n\n",
        )

        theirs = [
            lic for lic in _scan(detector, root)
            if lic.source_file.endswith("vendor/LICENSE.txt")
        ]
        assert theirs
        assert all(lic.spdx_id == "OFL-1.1" for lic in theirs), theirs

    def test_a_reserved_font_name_settles_its_own_file_and_no_other(self, detector):
        """A project may hold two OFL files: its font and a vendored one.

        Unlike Exhibit B, a reserved font name needs no cross-file reading at
        all -- it is written on the licence file's own copyright line. Read
        across the scan it settled a second, plain OFL.txt as the
        reserved-name variant on the strength of a file that says nothing
        about it.
        """
        ofl = detector.license_detector.spdx_data.get_license_text("OFL-1.1")
        root = _a_project(
            detector, "OFL-1.1", [("vendor/LICENSE.txt", ofl)],
            licence_name="OFL.txt", prefix=A_RESERVED_FONT_NAME,
        )

        named = {
            Path(lic.source_file).name: lic.spdx_id
            for lic in _scan(detector, root) if lic.detection_method == "hash"
        }

        assert named == {"OFL.txt": "OFL-1.1-RFN", "LICENSE.txt": "OFL-1.1"}, named

    def test_a_preface_does_not_make_the_quoted_identifiers_declarations(self, detector):
        """A licence text does not stop being one for having a sentence in
        front of it.

        A LICENSE opening "This project is licensed as follows" no longer
        hashes, so the CAL's printed identifiers went on being declarations
        at 1.0 -- and then suppressed the 0.999 similarity match on the same
        file as a guess at what the file had already said. The quoted
        identifier was silencing the reading that would have contradicted it.
        """
        root = _a_project(
            detector, "CAL-1.0",
            prefix="This project is licensed as follows.\n\n",
        )

        found = _scan(detector, root)

        assert {lic.spdx_id for lic in found} == {"CAL-1.0"}, found

    def test_a_header_beside_a_copied_licence_still_names_the_member(self, detector):
        """One file can declare its licence and quote it too.

        Naming the member drops the header below certainty, which takes it
        out of the licences the file is held to have stated -- so the copied
        text was no longer read as a guess at the header, and a 0.99 score
        for the plain family outranked the header that named the member.
        """
        mpl = detector.license_detector.spdx_data.get_license_text("MPL-2.0")
        root = Path(tempfile.mkdtemp())
        named = root / "main.c"
        named.write_text(
            '/* This Source Code Form is "Incompatible With Secondary\n'
            ' * Licenses", as defined by the Mozilla Public License. */\n'
            "// SPDX-License-Identifier: MPL-2.0\n"
            f"/*\n{mpl}\n*/\nint main(void){{return 0;}}\n"
        )

        found = detector.process_local_path(str(named)).licenses

        assert found
        assert max(found, key=lambda lic: lic.confidence).spdx_id == \
            "MPL-2.0-no-copyleft-exception"
        assert "MPL-2.0" not in {lic.spdx_id for lic in found}

    def test_a_source_file_keeps_its_own_declaration(self, detector):
        """A licence block cut out of a source file is not the whole file.

        Only a whole-file match proves the file is a quoted licence. A source
        file carrying a short licence verbatim and declaring
        `SPDX-License-Identifier: 0BSD OR Apache-2.0` beside it had the block
        treated as canonical text, and lost the Apache half of its own
        declaration.
        """
        zero_bsd = detector.license_detector.spdx_data.get_license_text("0BSD")
        root = Path(tempfile.mkdtemp())
        (root / "util.c").write_text(
            "// SPDX-License-Identifier: 0BSD OR Apache-2.0\n"
            f"/*\n{zero_bsd}\n*/\nint f(void){{return 0;}}\n"
        )

        found = {lic.spdx_id for lic in _scan(detector, root, deep=True)}

        assert {"0BSD", "Apache-2.0"} <= found, found

    def test_a_document_that_only_warns_about_the_wording_is_not_applying_it(
        self, detector
    ):
        """The invariant-sections phrase alone does not say who is speaking.

        A CONTRIBUTING.md telling authors not to write "with no Invariant
        Sections" carries the words without granting anything, and settled
        the whole project as having none. The notice is a condition of a
        grant, so the grant has to be there: a document applying it names the
        licence it is applying.
        """
        root = _a_project(detector, "GFDL-1.3-only", [("CONTRIBUTING.md", (
            "# Contributing\n\n"
            'Do not add the phrase "with no Invariant Sections" to new '
            "manuals.\n"
        ))], licence_name="COPYING")

        found = _the_hash_record(detector, root)

        assert found.spdx_id == "GFDL-1.3-only"
        assert found.ambiguous_with

    def test_a_notice_file_listing_the_header_has_not_attached_it(self, detector):
        """Exhibit B says what it applies to in its own first words.

        "This Source Code Form is ..." is about a source code form, and a
        NOTICE listing the header for contributors to copy is not one. A
        NOTICE is read as a licence file rather than as a document, so ruling
        out prose alone let it through and settled the project as carrying
        the exception it said no file yet carried.
        """
        root = _a_project(detector, "MPL-2.0", [("NOTICE", (
            "Wobble\n======\n\n"
            "Files that are incompatible with secondary licenses carry this "
            "header:\n\n"
            'This Source Code Form is "Incompatible With Secondary Licenses", '
            "as\ndefined by the Mozilla Public License, v. 2.0.\n\n"
            "None currently do.\n"
        ))])

        found = _the_hash_record(detector, root)

        assert found.spdx_id == "MPL-2.0"
        assert found.ambiguous_with

    def test_naming_the_licence_is_not_granting_it(self, detector):
        """A warning that names the GFDL is still only a warning.

        Requiring the licence's name nearby was not enough: "do not add the
        phrase ... to GFDL manuals" names it while granting nothing, and
        settled the whole project. What a document applying the licence
        carries is the addendum's own wording -- permission granted, under
        the terms of.
        """
        root = _a_project(detector, "GFDL-1.3-only", [("CONTRIBUTING.md", (
            "# Contributing\n\n"
            'Do not add the phrase "with no Invariant Sections" to GFDL '
            "manuals.\n"
        ))], licence_name="COPYING")

        found = _the_hash_record(detector, root)

        assert found.spdx_id == "GFDL-1.3-only"
        assert found.ambiguous_with

    def test_a_build_script_describing_the_manual_is_not_the_manual(self, detector):
        """Invariant Sections are stated in the document the licence covers.

        Under `--deep` every file is read, and a build script commenting that
        "the generated manual ships with no Invariant Sections" rewrote the
        licence of a document it only describes.
        """
        root = _a_project(detector, "GFDL-1.3-only", [("build.py", (
            "# The generated manual ships with no Invariant Sections, no\n"
            "# Front-Cover Texts.\n"
            "print(1)\n"
        ))], licence_name="COPYING")

        found = _the_hash_record(detector, root, deep=True)

        assert found.spdx_id == "GFDL-1.3-only"
        assert found.ambiguous_with

    def test_a_manifest_is_never_where_a_notice_is_applied(self, detector):
        """A manifest describes a package; it does not carry its terms.

        A `pyproject.toml` long description showing contributors the Exhibit
        B header settled the LICENSE beside it as carrying the exception it
        was quoting. Metadata is read by default, so this needed no flags.
        """
        root = _a_project(detector, "MPL-2.0", [("pyproject.toml", (
            '[project]\nname = "wobble"\ndescription = """\n'
            "Add this to new files:\n"
            'This Source Code Form is "Incompatible With Secondary Licenses", as\n'
            "defined by the Mozilla Public License, v. 2.0.\n"
            '"""\n'
        ))])

        found = _the_hash_record(detector, root)

        assert found.spdx_id == "MPL-2.0"
        assert found.ambiguous_with

    def test_a_credit_to_a_bundled_font_is_not_the_projects_notice(self, detector):
        """The OFL says where a reserved name is written.

        "Any names specified as such after the copyright statement" is the
        licence's own copyright line. The same words in a README are
        crediting somebody else's font, and read across the scan they settled
        the project's own OFL.txt as the variant.
        """
        root = _a_project(detector, "OFL-1.1", [("README.md", (
            "# Wobble\n\n"
            'Bundled font: Copyright (c) 2005 Someone, with Reserved Font '
            'Name "Vendored".\n'
        ))], licence_name="OFL.txt")

        found = _the_hash_record(detector, root)

        assert found.spdx_id == "OFL-1.1"
        assert found.ambiguous_with

    def test_a_mention_of_a_variant_is_not_a_declaration_of_it(self, detector):
        """A credit names a licence; it does not grant one.

        The tag tier answers for a licence named in prose too, and #117
        separated the two by category. Taken as a declaration, a README
        saying the vendored font is under `OFL-1.1-RFN` rewrote the project's
        own licence to the dependency's.
        """
        root = _a_project(detector, "OFL-1.1", [("README.md", (
            "# Wobble\n\nThe vendored font is licensed under OFL-1.1-RFN.\n"
        ))], licence_name="OFL.txt")

        found = _the_hash_record(detector, root)

        assert found.spdx_id == "OFL-1.1"
        assert found.ambiguous_with

    def test_a_bundled_third_party_notice_does_not_settle_the_project(self, detector):
        """A dependency's paperwork is not this project's (issue #78).

        A vendored font's THIRD_PARTY_NOTICES names its own reserved font
        name, and reading it scan-wide settled the project's own OFL.txt as
        the reserved-name variant on a dependency's say-so.
        """
        root = _a_project(detector, "OFL-1.1", [
            ("THIRD_PARTY_NOTICES.txt",
             'Copyright (c) 2005 Someone Else, with Reserved Font Name "Vendored".\n'),
        ], licence_name="OFL.txt")

        found = _the_hash_record(detector, root)

        assert found.spdx_id == "OFL-1.1"
        assert found.ambiguous_with


class TestTwoFilesHoldingOneSharedText:
    def test_both_are_named_and_the_scan_still_answers(self, detector):
        """A project may hold the same licence twice.

        Settling one record settles every other reading of that text, so the
        second was answered before the loop reached it and then unpacked an
        ambiguity that was no longer there. The error surfaced inside the
        scan's own handling, which reported the whole path as carrying no
        licence at all: the worst thing a tool for reading licences can say.
        """
        mpl = detector.license_detector.spdx_data.get_license_text("MPL-2.0")
        root = _a_project(detector, "MPL-2.0", [
            ("COPYING", mpl),
            ("src/main.c", EXHIBIT_B),
        ])

        found = _scan(detector, root, deep=True)

        assert found, "the scan must still answer"
        named = {
            Path(lic.source_file).name: lic.spdx_id
            for lic in found if lic.detection_method == "hash"
        }
        assert named == {
            "LICENSE": "MPL-2.0-no-copyleft-exception",
            "COPYING": "MPL-2.0-no-copyleft-exception",
        }, named


class TestSilenceIsNotAnAnswer:
    def test_no_notice_leaves_the_ambiguity(self, detector):
        """A project that did not say has not said the negative.

        A plain OFL.txt with no reserved name is not evidence of
        OFL-1.1-no-RFN. Inferring a member from the absence of a notice would
        turn every unedited licence file into a declaration.
        """
        root = _a_project(
            detector, "OFL-1.1", [("src/main.c", "int main(void) { return 0; }\n")],
            licence_name="OFL.txt",
        )

        found = _the_hash_record(detector, root, deep=True)

        assert found.spdx_id == "OFL-1.1"
        assert "no-RFN" not in (found.ambiguous_with and found.spdx_id or "")
        assert found.ambiguous_with

    @pytest.mark.parametrize(
        "spdx_id,is_a_member",
        [
            ("MPL-2.0", False),
            ("OFL-1.1", False),
            ("GFDL-1.3-only", False),
            ("CAL-1.0", False),
            ("MPL-2.0-no-copyleft-exception", True),
            ("OFL-1.1-RFN", True),
            # The negative members name one just as plainly. Borrowing the
            # notice predicates missed them, because nothing reads a font's
            # licence and concludes `OFL-1.1-no-RFN` -- but a file may say
            # so, and that identifier was left open to be overwritten.
            ("OFL-1.1-no-RFN", True),
            ("OFL-1.0-no-RFN", True),
            ("GFDL-1.3-invariants-only", True),
            ("GFDL-1.3-no-invariants-only", True),
            ("CAL-1.0-Combined-Work-Exception", True),
        ],
    )
    def test_which_identifiers_already_name_a_member(self, spdx_id, is_a_member):
        assert family_notices.names_a_member(spdx_id) is is_a_member

    def test_a_notice_cannot_overrule_a_member_the_file_named(self, detector):
        """A notice fills in what an identifier left out.

        It has something to say about `GFDL-1.3-only` and nothing to say
        about `GFDL-1.3-no-invariants-only`, which has already answered.
        Read as a qualification anyway, the notice quietly replaced the
        identifier the file actually wrote, and the report named the
        opposite member with the contradiction gone from it.
        """
        root = _a_project(detector, "GFDL-1.3-only", [("MANUAL.md", (
            "SPDX-License-Identifier: GFDL-1.3-no-invariants-only\n\n"
            "The Wobble Manual\n\n"
            "Permission is granted to copy this document under the terms of "
            "the GNU Free\nDocumentation License, Version 1.3; with the "
            'Invariant Sections being\n"History", with no Front-Cover Texts.\n'
        ))], licence_name="COPYING")

        named = {
            Path(lic.source_file).name: lic.spdx_id
            for lic in _scan(detector, root)
        }

        # What the file wrote stands, and the licence it shares stays open.
        assert named["MANUAL.md"] == "GFDL-1.3-no-invariants-only", named
        assert named["COPYING"] == "GFDL-1.3-only", named

    def test_a_contradiction_inside_one_file_is_left_as_one(self, detector):
        """Both forms in one document is still a disagreement.

        The two phrases sit close enough to be read together, and preferring
        the one that carries an obligation, or the one that came first,
        settles a contradiction by reading order and hides it.
        """
        root = _a_project(detector, "GFDL-1.3-only", [("MANUAL.md", (
            "The Wobble Manual\n\n"
            "... under the GNU Free Documentation License, Version 1.3; with\n"
            'the Invariant Sections being "History", with no Front-Cover\n'
            "Texts.\n\n"
            "Appendix: an earlier edition was released with no Invariant\n"
            "Sections, no Front-Cover Texts, and no Back-Cover Texts.\n"
        ))], licence_name="COPYING")

        found = _the_hash_record(detector, root)

        assert found.match_type == "exact_hash_shared_text"
        assert found.ambiguous_with

    def test_a_tree_where_only_some_files_carry_exhibit_b(self, detector):
        """Exhibit B is attached per file, so a project can carry both.

        A qualified header changes what its file declares, and answering
        before every header had been read gave the shared LICENSE the
        exception on the strength of whichever file came first. Where one
        source file carries the notice and another does not, the project has
        not settled the question.
        """
        root = _a_project(detector, "MPL-2.0", [
            ("src/a.c", EXHIBIT_B + "\n// SPDX-License-Identifier: MPL-2.0\n"),
            ("src/b.c", "// SPDX-License-Identifier: MPL-2.0\nint b(void){return 0;}\n"),
        ])

        found = _the_hash_record(detector, root, deep=True)

        assert found.spdx_id == "MPL-2.0"
        assert found.ambiguous_with

    def test_and_the_same_tree_when_the_notice_bearing_file_says_nothing_else(
        self, detector
    ):
        """The mixed tree reached the other way round.

        When the file carrying Exhibit B states no identifier of its own,
        nothing qualifies it, so the disagreement never appears as two
        declarations -- one file plainly says `MPL-2.0` and another carries
        the notice, and the licence file was given the exception anyway.
        """
        root = _a_project(detector, "MPL-2.0", [
            ("src/a.c",
             '/* This Source Code Form is "Incompatible With Secondary '
             'Licenses", as\n * defined by the Mozilla Public License, v. '
             "2.0. */\nint a(void){return 0;}\n"),
            ("src/b.c",
             "// SPDX-License-Identifier: MPL-2.0\nint b(void){return 0;}\n"),
        ])

        found = _the_hash_record(detector, root, deep=True)

        assert found.spdx_id == "MPL-2.0"
        assert found.ambiguous_with

    def test_a_manifest_beside_the_declaring_sources_changes_nothing(
        self, detector
    ):
        """Every file that declares an identifier counts, not the first one.

        `package.json` sorts before `src/`, so a source file plainly saying
        `MPL-2.0` beside a manifest saying the same was read as though the
        declaration came from metadata alone -- and the metadata exemption
        then let the mixed tree resolve when it should have stayed open.
        """
        root = _a_project(detector, "MPL-2.0", [
            ("package.json", '{"name": "w", "license": "MPL-2.0"}\n'),
            ("src/a.c",
             '/* This Source Code Form is "Incompatible With Secondary '
             'Licenses", as\n * defined by the Mozilla Public License, v. '
             "2.0. */\nint a(void){return 0;}\n"),
            ("src/b.c",
             "// SPDX-License-Identifier: MPL-2.0\nint b(void){return 0;}\n"),
        ])

        found = _the_hash_record(detector, root, deep=True)

        assert found.spdx_id == "MPL-2.0"
        assert found.ambiguous_with

    def test_but_a_manifest_alone_does_not_hold_the_family_open(self, detector):
        """A manifest naming the family the text already chose adds nothing.

        Every Mozilla-shaped package has one, and weighing it against a
        member named in a source file left the licence file unresolved
        whenever a header supplied the distinguishing notice.
        """
        root = _a_project(detector, "MPL-2.0", [
            ("package.json", '{"name": "w", "license": "MPL-2.0"}\n'),
            ("src/a.c",
             "// SPDX-License-Identifier: MPL-2.0-no-copyleft-exception\n"),
        ])

        found = _the_hash_record(detector, root, deep=True)

        assert found.spdx_id == "MPL-2.0-no-copyleft-exception"
        assert not found.ambiguous_with

    def test_a_qualified_header_agrees_with_a_file_declaring_the_member(
        self, detector
    ):
        """Qualifying a header changes what it states.

        A file carrying `SPDX-License-Identifier: MPL-2.0` and Exhibit B
        states the exception member once the two have been read together.
        Counting its first answer left it looking as though it disagreed
        with another file declaring that same member outright, and the
        shared LICENSE was held ambiguous over a disagreement that was not
        there.
        """
        root = _a_project(detector, "MPL-2.0", [
            ("src/a.c", EXHIBIT_B + "\n// SPDX-License-Identifier: MPL-2.0\n"),
            ("src/b.c",
             "// SPDX-License-Identifier: MPL-2.0-no-copyleft-exception\n"),
        ])

        found = _the_hash_record(detector, root, deep=True)

        assert found.spdx_id == "MPL-2.0-no-copyleft-exception"
        assert not found.ambiguous_with

    def test_two_files_declaring_different_members_leave_it_as_one(self, detector):
        """The project's own identifiers disagree.

        Counted including the member the text itself chose: one source file
        saying `CAL-1.0` and another saying
        `CAL-1.0-Combined-Work-Exception` is exactly such a disagreement, and
        leaving the first out of the count made it look like a single clear
        answer and granted the exception.
        """
        root = _a_project(detector, "CAL-1.0", [
            ("src/a.py", "# SPDX-License-Identifier: CAL-1.0\n"),
            ("src/b.py",
             "# SPDX-License-Identifier: CAL-1.0-Combined-Work-Exception\n"),
        ])

        found = _the_hash_record(detector, root, deep=True)

        assert found.spdx_id == "CAL-1.0"
        assert found.ambiguous_with

    def test_a_notice_and_a_conflicting_declaration_leave_it_as_one(self, detector):
        """A project contradicts itself in two ways, and both count.

        A document stating its invariant sections beside another declaring
        `GFDL-1.3-no-invariants-only` outright is as much a disagreement as
        two notices are. Checking only notice against notice let the notice
        answer for the COPYING they share and clear its ambiguity.
        """
        root = _a_project(detector, "GFDL-1.3-only", [
            ("docs/a.md", "SPDX-License-Identifier: GFDL-1.3-only\n\n"
             'Permission is granted to copy this document under the terms of '
             'the GNU Free Documentation License, Version 1.3; with the '
             'Invariant Sections being "History", '
             "with no Front-Cover Texts.\n"),
            ("docs/b.md", "SPDX-License-Identifier: GFDL-1.3-no-invariants-only\n\n"
             "Nothing else here.\n"),
        ], licence_name="COPYING")

        shared = [
            lic for lic in _scan(detector, root)
            if Path(lic.source_file).name == "COPYING"
        ]

        assert shared
        assert all(lic.spdx_id == "GFDL-1.3-only" for lic in shared), shared
        assert all(lic.ambiguous_with for lic in shared), shared

    def test_a_document_is_aligned_with_itself_however_the_scan_disagrees(
        self, detector
    ):
        """A disagreement elsewhere is not a reason to leave a file
        contradicting itself.

        Two manuals that disagree and each append the licence: the shared
        COPYING must stay ambiguous, but each manual's own copy of the plain
        text scored above the 0.95 its own notice earned, so each document
        was led by the family rather than by what it said about itself.
        """
        gfdl = detector.license_detector.spdx_data.get_license_text("GFDL-1.3-only")
        root = _a_project(detector, "GFDL-1.3-only", [
            ("docs/a.md", "SPDX-License-Identifier: GFDL-1.3-only\n\n"
             'Permission is granted to copy this document under the terms of '
             'the GNU Free Documentation License, Version 1.3; with the '
             'Invariant Sections being "History", '
             "with no Front-Cover Texts.\n\n" + gfdl),
            ("docs/b.md", "SPDX-License-Identifier: GFDL-1.3-only\n\n"
             "Permission is granted to copy this document under the terms of "
             "the GNU Free Documentation License, Version 1.3; with no "
             "Invariant Sections, no Front-Cover "
             "Texts.\n\n" + gfdl),
        ], licence_name="COPYING")

        named = {
            Path(lic.source_file).name: lic.spdx_id
            for lic in _scan(detector, root)
        }

        assert named == {
            "COPYING": "GFDL-1.3-only",
            "a.md": "GFDL-1.3-invariants-only",
            "b.md": "GFDL-1.3-no-invariants-only",
        }, named

    def test_a_contradiction_between_two_declaring_documents_is_left_as_one(
        self, detector
    ):
        """Two documents that state their licence and disagree about their
        invariant sections settle their own records and nothing else.

        Each settled its own header first, and then answered for the COPYING
        they share -- before anything had looked at whether they agreed, and
        in whatever order the threads happened to finish. Two identical scans
        gave the shared file different answers.
        """
        root = _a_project(detector, "GFDL-1.3-only", [
            ("docs/a.md", "SPDX-License-Identifier: GFDL-1.3-only\n\n"
             'Permission is granted to copy this document under the terms of '
             'the GNU Free Documentation License, Version 1.3; with the '
             'Invariant Sections being "History", '
             "with no Front-Cover Texts.\n"),
            ("docs/b.md", "SPDX-License-Identifier: GFDL-1.3-only\n\n"
             "Permission is granted to copy this document under the terms of "
             "the GNU Free Documentation License, Version 1.3; with no "
             "Invariant Sections, no Front-Cover "
             "Texts.\n"),
        ], licence_name="COPYING")

        shared = set()
        for _ in range(3):
            shared |= {
                lic.spdx_id for lic in _scan(detector, root)
                if Path(lic.source_file).name == "COPYING"
            }

        assert shared == {"GFDL-1.3-only"}, shared

    def test_a_contradiction_is_left_as_one(self, detector):
        """Two notices that cannot both be true settle nothing.

        Picking a side would hide the disagreement, which is itself the
        finding worth reporting.
        """
        root = _a_project(detector, "GFDL-1.3-only", [
            ("README.md", _naming_invariant_sections()),
            ("MANUAL.md", NAMING_NO_INVARIANT_SECTIONS),
        ], licence_name="COPYING")

        found = _the_hash_record(detector, root)

        assert found.match_type == "exact_hash_shared_text"
        assert found.ambiguous_with


class TestTheGrantIsADifferentQuestion:
    """Which version may be used is not what these notices answer.

    The GFDL family splits on two axes at once. One is invariant sections,
    which the document states and this issue reads. The other is `-only`
    against `-or-later`, which is settled where the licence is applied and is
    what #118 and #140 are about. A notice about the first must leave the
    second exactly as the scan already had it.

    Asked of the reader directly, because the two grants share a text: there
    is no licence file that makes the hash tier answer `-or-later`, so a scan
    cannot put that case to it.
    """

    THE_WHOLE_GFDL_FAMILY = [
        "GFDL-1.3-invariants-only", "GFDL-1.3-invariants-or-later",
        "GFDL-1.3-no-invariants-only", "GFDL-1.3-no-invariants-or-later",
    ]

    @pytest.mark.parametrize(
        "chosen,expected",
        [
            ("GFDL-1.3-only", "GFDL-1.3-invariants-only"),
            ("GFDL-1.3-or-later", "GFDL-1.3-invariants-or-later"),
        ],
    )
    def test_the_only_or_or_later_already_worked_out_is_kept(self, chosen, expected):
        notice = family_notices.Notice(
            family_notices.INVARIANT_SECTIONS,
            'with the Invariant Sections being "History"', "README.md",
        )

        named = family_notices.the_member_named(
            chosen, self.THE_WHOLE_GFDL_FAMILY, {notice.marker: notice}
        )

        assert named is not None
        assert named[0] == expected

    def test_a_family_the_notice_cannot_narrow_to_one_is_left_alone(self):
        """Nothing is settled unless exactly one member is named."""
        notice = family_notices.Notice(
            family_notices.INVARIANT_SECTIONS,
            'with the Invariant Sections being "History"', "README.md",
        )

        # A base identifier carrying no grant leaves both `-only` and
        # `-or-later` invariants members standing.
        assert family_notices.the_member_named(
            "GFDL-1.3", self.THE_WHOLE_GFDL_FAMILY, {notice.marker: notice}
        ) is None


class TestALicenceQuotingItselfIsNotADeclaration:
    """An identifier printed inside a recognised licence text is SPDX's.

    The CAL prints both of its own identifiers in its section on how to mark
    a file, so every project under CAL-1.0 declared
    `CAL-1.0-Combined-Work-Exception` at confidence 1.0 from its LICENSE
    alone: an exception nobody had granted, read out of the instructions for
    granting it. The Community Specification does the same with `CC-BY-4.0`.

    Sound because of what an exact match means. The hash is taken over the
    file's whole text, so a file that matched carries the canonical text and
    nothing else, and anything printed in it is SPDX's words rather than this
    project's.
    """

    def test_the_cals_own_identifiers_are_not_read_as_declarations(self, detector):
        found = _scan(detector, _a_project(detector, "CAL-1.0"))

        declared = {
            lic.spdx_id for lic in found if lic.detection_method == "tag"
        }
        assert "CAL-1.0-Combined-Work-Exception" not in declared, found

    def test_the_community_spec_does_not_declare_cc_by(self, detector):
        found = _scan(detector, _a_project(detector, "Community-Spec-1.0"))

        assert "CC-BY-4.0" not in {lic.spdx_id for lic in found}, found

    def test_a_declaration_above_the_licence_text_is_kept(self, detector):
        """A file may carry a licence text *and* declare something.

        The rule is about the identifier, not the file. Held against every
        tag in a file that matched a licence, a LICENSE opening
        `SPDX-License-Identifier: MIT OR 0BSD` above the MIT text lost the
        0BSD half of the choice it was offering. What is quoted is an
        identifier the matched licence prints in its own words, and MIT
        prints none.
        """
        mit = detector.license_detector.spdx_data.get_license_text("MIT")
        root = Path(tempfile.mkdtemp())
        (root / "LICENSE").write_text(
            f"SPDX-License-Identifier: MIT OR 0BSD\n\n{mit}"
        )

        found = {lic.spdx_id for lic in _scan(detector, root)}

        assert {"MIT", "0BSD"} <= found, found

    def test_a_header_stating_what_the_licence_also_prints_is_kept(self, detector):
        """A project may grant the exception the CAL explains how to grant.

        A LICENSE opening `SPDX-License-Identifier:
        CAL-1.0-Combined-Work-Exception` above the CAL text holds two of that
        identifier where the licence holds one, and the extra one is the
        project speaking. Counting answers it without needing to know where
        in the file either occurrence sits.
        """
        root = _a_project(
            detector, "CAL-1.0",
            prefix="SPDX-License-Identifier: CAL-1.0-Combined-Work-Exception\n\n",
        )

        found = {lic.spdx_id for lic in _scan(detector, root)}

        assert "CAL-1.0-Combined-Work-Exception" in found, found

    def test_and_however_the_file_spells_it(self, detector):
        """The identifier on the record is normalised; the file's is not.

        A grant written `SPDX-License-Identifier:
        cal-1.0-combined-work-exception` is a declaration however it is
        cased, and reading the preface with the same reader that read the
        file settles it without either having to match the other's spelling.
        """
        root = _a_project(
            detector, "CAL-1.0",
            prefix="SPDX-License-Identifier: cal-1.0-combined-work-exception\n\n",
        )

        found = {lic.spdx_id for lic in _scan(detector, root)}

        assert "CAL-1.0-Combined-Work-Exception" in found, found

    def test_a_licence_naming_another_licence_is_not_declaring_it(self, detector):
        """Fourteen texts name a second licence in their own words.

        GPL-3.0 names the AGPL in its section on remote interaction, and
        `copyleft-next-0.3.1` names GPL-2.0-only. A file carrying one of
        those texts is not declaring the licence its licence talks about --
        every project under GPL-3.0 was reported as carrying the AGPL too.
        """
        found = _scan(detector, _a_project(detector, "GPL-3.0-only"))

        assert {lic.spdx_id for lic in found} == {"GPL-3.0-only"}, found

    def test_an_edited_licence_keeps_the_declaration_above_it(self, detector):
        """Not knowing where the licence starts is not the same as there
        being no preface.

        Both were answered the same way, so a LICENSE stating
        `SPDX-License-Identifier: GPL-3.0-only OR AGPL-3.0-only` above a
        lightly edited GPL text -- its title lines gone -- had the AGPL half
        discarded as the licence quoting itself. Not being able to place the
        licence is a reason to leave what the file says alone.
        """
        gpl = detector.license_detector.spdx_data.get_license_text("GPL-3.0-only")
        root = Path(tempfile.mkdtemp())
        (root / "LICENSE").write_text(
            "SPDX-License-Identifier: GPL-3.0-only OR AGPL-3.0-only\n\n"
            + "\n".join(gpl.splitlines()[3:])
        )

        found = {lic.spdx_id for lic in _scan(detector, root)}

        assert "AGPL-3.0-only" in found, found

    def test_and_a_preface_does_not_change_that(self, detector):
        """The licence's own mention stays its own however the file opens.

        What is read is the run of text before the licence begins, so a
        sentence in front of it neither creates a declaration nor hides one.
        """
        root = _a_project(
            detector, "GPL-3.0-only",
            prefix="This project is licensed as follows.\n\n",
        )

        found = _scan(detector, root)

        assert "AGPL-3.0-only" not in {lic.spdx_id for lic in found}, found

    def test_a_quoted_identifier_cannot_corroborate_a_keyword_either(self, detector):
        """Dropping it late let it do its damage first.

        FSL-1.1-ALv2 prints the Apache boilerplate as the licence a work
        converts to, so its LICENSE carried an Apache identifier this
        discards -- but the discard happens at the end, and the corroboration
        set was built before it. The doomed Apache tag kept the Apache
        keyword match in the same file alive, and the scan reported
        `Apache-2.0` on the strength of two findings that were both the FSL
        text.
        """
        found = _scan(detector, _a_project(detector, "FSL-1.1-ALv2"))

        assert {lic.spdx_id for lic in found} == {"FSL-1.1-ALv2"}, found

    def test_a_licence_named_like_an_exception_is_still_a_licence(self, detector):
        """`--deep --no-package-metadata` lost the declaration entirely.

        SPDX exceptions modify a licence in a `WITH` expression rather than
        standing alone, and the tag detector dropped any identifier with
        "exception" in it. But two licences carry the word in their own
        names, `CAL-1.0-Combined-Work-Exception` and
        `MPL-2.0-no-copyleft-exception`, and the spelling is not what tells
        them apart -- the licence list is.
        """
        root = _a_project(detector, "CAL-1.0", [
            ("src/lib.py",
             "# SPDX-License-Identifier: CAL-1.0-Combined-Work-Exception\n"),
        ])

        detector.config.scan_package_metadata = False
        try:
            found = _scan(detector, root, deep=True)
        finally:
            detector.config.scan_package_metadata = None

        assert {lic.spdx_id for lic in found} == \
            {"CAL-1.0-Combined-Work-Exception"}, found

    def test_but_a_real_spdx_exception_is_still_not_a_licence(self, detector):
        """The carve-out must not let the operators back in.

        `Classpath-exception-2.0` is on the exception list, not the licence
        list, and it qualifies GPL-2.0-only rather than standing beside it.
        """
        root = Path(tempfile.mkdtemp())
        (root / "a.c").write_text(
            "// SPDX-License-Identifier: GPL-2.0-only WITH Classpath-exception-2.0\n"
            "int f(void){return 0;}\n"
        )

        found = {lic.spdx_id for lic in _scan(detector, root, deep=True)}

        assert found == {"GPL-2.0-only"}, found

    def test_a_real_declaration_elsewhere_still_counts(self, detector):
        """Only the licence file's own text is discounted."""
        root = _a_project(detector, "CAL-1.0", [
            ("src/lib.py",
             "# SPDX-License-Identifier: CAL-1.0-Combined-Work-Exception\n"),
        ])

        declared = {
            lic.spdx_id for lic in _scan(detector, root, deep=True)
            if lic.detection_method == "tag"
        }
        assert "CAL-1.0-Combined-Work-Exception" in declared


class TestTheReportCarriesIt:
    def test_the_evidence_says_what_named_the_member(self, detector):
        root = _a_project(detector, "MPL-2.0", [("src/main.c", EXHIBIT_B)])

        finished = subprocess.run(
            [sys.executable, "-m", "osslili", "--deep", "-f", "evidence", str(root)],
            capture_output=True, text=True, cwd=REPO_ROOT,
        )
        assert finished.returncode == 0, finished.stderr
        report = json.loads(finished.stdout[finished.stdout.index("{"):])

        named = [
            e
            for scanned in report["scan_results"]
            for e in scanned.get("license_evidence", [])
            if e.get("match_type") == "exact_hash_named_by_notice"
        ]
        assert named, report
        assert named[0]["detected_license"] == "MPL-2.0-no-copyleft-exception"
        # The finding is an inference across two files, so the record has to
        # say which file and which words, or a reader who doubts it cannot
        # go and look.
        assert named[0]["resolved_by"]["file"].endswith("main.c")
        assert "Incompatible With Secondary Licenses" in \
            named[0]["resolved_by"]["notice"]
        assert "ambiguous_with" not in named[0]

    def test_two_scans_name_the_same_file_as_having_said_so(self, detector):
        """`resolved_by` has to be the same file every run.

        What each file yielded is collected as the threads finish, so taking
        the first file to declare a member took whichever worker won the
        race, and two identical scans credited different files (#122).
        """
        root = _a_project(detector, "CAL-1.0", [
            (f"src/{name}.py",
             "# SPDX-License-Identifier: CAL-1.0-Combined-Work-Exception\n")
            for name in ("a", "b", "c", "d", "e", "f")
        ])

        credited = set()
        for _ in range(5):
            credited |= {
                lic.resolved_by["file"]
                for lic in _scan(detector, root, deep=True)
                if lic.resolved_by and lic.detection_method == "hash"
            }

        assert len(credited) == 1, credited

    def test_an_archive_names_the_notice_by_its_path_inside(self, detector):
        """The notice's file is a second path into the archive.

        Extraction picks a fresh temporary directory every run, so a record
        that read `pkg/LICENSE` and pointed the notice at
        `/var/.../extract_0_pkg/pkg/src/main.c` named a directory that is gone
        by the time anyone opens the report, and answered differently every
        run. This is what #121 settled for `source_file`, applied to the path
        #144 adds beside it.
        """
        made = _a_project(detector, "MPL-2.0", [("src/main.c", EXHIBIT_B)])
        packed = Path(tempfile.mkdtemp()) / "pkg.zip"
        with zipfile.ZipFile(packed, "w") as archive:
            for held in made.rglob("*"):
                archive.write(held, Path("pkg") / held.relative_to(made))

        detector.config.deep_scan = True
        detector.config.license_files_only = False
        try:
            found = detector.process_local_path(str(packed)).licenses
        finally:
            detector.config.deep_scan = False
            detector.config.license_files_only = True

        named = [lic for lic in found if lic.resolved_by]
        assert named, found
        for lic in named:
            assert lic.resolved_by["file"] == "pkg/src/main.c", lic.resolved_by

    def test_a_record_nothing_named_carries_no_such_field(self, detector):
        finished = subprocess.run(
            [sys.executable, "-m", "osslili", "-f", "evidence",
             str(_a_project(detector, "MIT"))],
            capture_output=True, text=True, cwd=REPO_ROOT,
        )
        report = json.loads(finished.stdout[finished.stdout.index("{"):])

        for scanned in report["scan_results"]:
            for e in scanned.get("license_evidence", []):
                assert "resolved_by" not in e, e
