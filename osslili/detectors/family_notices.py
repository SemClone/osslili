"""Which member of a shared-text family a project says it carries.

Seven texts on the SPDX list are shared by licences that oblige different
things, so an exact match on the text names a family rather than a licence.
#142 stopped the scanner claiming otherwise: such a match is reported with
`ambiguous_with` naming the alternatives, and a confidence below certainty.

    CAL-1.0   against CAL-1.0-Combined-Work-Exception
    MPL-2.0   against MPL-2.0-no-copyleft-exception
    OFL-1.0   against OFL-1.0-RFN and OFL-1.0-no-RFN
    OFL-1.1   against OFL-1.1-RFN and OFL-1.1-no-RFN
    GFDL-1.1  against its invariants and no-invariants members, and 1.2, 1.3

What separates the members is written down, just not in the licence file. A
font declares a Reserved Font Name after its copyright statement; a document
names its Invariant Sections; a Mozilla project attaches the Exhibit B notice.
This module reads those, so the scan can name the member instead of the family
(issue #144).

The one thing that makes it hard is that every distinguishing phrase also
appears in the licence text that defines it. "Incompatible With Secondary
Licenses" occurs five times in MPL-2.0 itself, "Invariant Section" twenty
times in GFDL-1.3, and both texts close with a template inviting you to copy
the phrase out. A search that did not know the difference would mark every
MPL project as carrying Exhibit B, which is the direction that costs
something: it says code cannot be relicensed under the GPL when it can.

So each reader is written to recognise the notice where a project *applies*
it, and to refuse it where the licence *defines* it. The guards differ by
family because the templates differ:

  - MPL and GFDL print their notice inside the licence text, under a heading.
    A file carrying that heading is carrying the template, and is not read.
  - The OFL prints no copyright line at all in the SPDX text, and the hash
    tier strips copyright lines before comparing, so a font's real
    "with Reserved Font Name" line survives in the very file that matched.
    There is nothing to refuse but SIL's unfilled placeholder.

Nothing here infers a member from the absence of a notice. A plain OFL.txt
with no Reserved Font Name is not evidence of OFL-1.1-no-RFN; it is a file
that did not say. Silence leaves the ambiguity #142 reports.
"""

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple


@dataclass(frozen=True)
class Notice:
    """A notice a file carries, and the words that carry it.

    `marker` names what was read rather than an SPDX identifier, because one
    notice can settle a member of several families: "with no Invariant
    Sections" says the same thing about GFDL 1.1, 1.2 and 1.3, and which
    version is in play is decided by the licence text that was matched.
    """
    marker: str
    phrase: str
    source_file: Optional[str] = None


# What the notices are called here. Not SPDX identifiers: the marker says what
# the file stated, and `the_member_named` works out which identifier that is
# for the family actually in hand.
EXHIBIT_B = "exhibit-b"
RESERVED_FONT_NAME = "reserved-font-name"
INVARIANT_SECTIONS = "invariant-sections"
NO_INVARIANT_SECTIONS = "no-invariant-sections"

# How far a notice speaks. Exhibit B and a document's Invariant Sections are
# statements about the work, made in one file and answering for the licence
# file beside it -- that cross-file reading is what #144 is for.
#
# A reserved font name is not like them. It is written on the licence file's
# own copyright line, so it needs no inference: the file that carries it is
# the file it settles. Read across a scan it did real harm, because a project
# may hold two OFL files -- its own font and a vendored one -- and one
# naming a reserved name said nothing whatever about the other.
SPEAKS_FOR_THE_PROJECT = frozenset({
    EXHIBIT_B, INVARIANT_SECTIONS, NO_INVARIANT_SECTIONS,
})

# Which shared-text family each notice speaks for. Two markers share one
# because they are the two answers to one question: a document either names
# its invariant sections or says it has none, and either way the GFDL family
# has been settled and there is nothing left to look for.
_FAMILY_OF = {
    EXHIBIT_B: "mpl",
    RESERVED_FONT_NAME: "ofl",
    INVARIANT_SECTIONS: "gfdl",
    NO_INVARIANT_SECTIONS: "gfdl",
}


# ---------------------------------------------------------------------------
# Reading the notices
# ---------------------------------------------------------------------------

# Comment markers and list bullets open a line without being part of the
# sentence, and a notice pasted into a source header is wrapped across several
# lines. Both are removed before matching so that the notice reads as the one
# sentence it is.
_LINE_OPENING = re.compile(r'^[ \t]*(?:[/*#;!<>|-]+|//+|\*/)[ \t]?', re.MULTILINE)


# What may sit between the words of a notice that wrapped onto a new line:
# whitespace, and whatever marks a comment in the language it landed in.
_WRAPPED = r'[\s*#/;>|!-]+'


def _flowing(text: str) -> str:
    """The text as sentences, with comment markers and line breaks removed."""
    return ' '.join(_LINE_OPENING.sub(' ', text).split())


# Whether it is worth flowing the text at all. A deep scan reads every file in
# a repository and almost none of them carry any of these words, so the words
# are looked for once over the text as it is, before anything is copied or
# rewritten.
#
# It accepts exactly the separators the careful matchers accept, because the
# two have to agree about what a wrapped line looks like: written out twice
# they drifted, and the cheap check did not know about `;` or `!`, so an
# Exhibit B notice wrapped across an assembler header was never looked at.
_COULD_BE_A_NOTICE = re.compile(
    'incompatible' + _WRAPPED + 'with' + _WRAPPED + 'secondary'
    r'|invariant' + _WRAPPED + 'sections'
    r'|reserved' + _WRAPPED + 'font' + _WRAPPED + 'names?',
    re.IGNORECASE,
)


# The notice a Mozilla project attaches to a file it does not want combined
# with GPL code. Section 10.4 of the licence says to use the words in
# Exhibit B, so the words are the same either way and only the setting
# differs.
#
# It has to open a line, after nothing but indentation and a comment marker.
# That is the rule `_compile_prose_patterns` already applies to "Licensed
# under the Apache License", and for the same reason: the notice is attached
# as a header, and a sentence with words in front of it is talking about the
# notice rather than giving it. A CONTRIBUTING.md explaining that a file
# saying `This Source Code Form is "Incompatible With Secondary Licenses"`
# cannot be combined with GPL code marked its whole project as carrying the
# exception it was telling contributors not to add.
#
# Matched on the raw window rather than the flowed text, because flowing is
# what removes the line openings this depends on. The separators between the
# words let the sentence wrap and carry a comment marker onto the next line,
# which is how it is written in a real source header.
_EXHIBIT_B_NOTICE = re.compile(
    r'^[ \t]*(?:[/*#;!<>|-]+[ \t]*)?'
    r'this' + _WRAPPED + r'source' + _WRAPPED + r'code' + _WRAPPED + r'form'
    + _WRAPPED + r'is' + _WRAPPED + r'"?incompatible' + _WRAPPED + r'with'
    + _WRAPPED + r'secondary' + _WRAPPED + r'licenses',
    re.IGNORECASE | re.MULTILINE,
)

# The heading Exhibit B sits under in the licence text. A file carrying it is
# carrying MPL's own template, whatever else it also says.
_EXHIBIT_B_HEADING = re.compile(
    r'exhibit b\s*-\s*"?incompatible with secondary licenses"?\s*notice',
    re.IGNORECASE,
)

# The GFDL prints its notice in an ADDENDUM at the end of the licence, with
# the titles left as "LIST THEIR TITLES" for an author to replace.
_GFDL_ADDENDUM = re.compile(
    r'addendum\s*:\s*how to use this license for your documents',
    re.IGNORECASE,
)

_INVARIANT_SECTIONS = re.compile(
    r'with the invariant sections being\s+(?P<titles>[^\n]{1,200}?)'
    r'\s*(?=,\s*with\b|\.|;|$)',
    re.IGNORECASE,
)

_NO_INVARIANT_SECTIONS = re.compile(
    r'with no invariant sections',
    re.IGNORECASE,
)

# The licence the notice is a condition of. A document applying it says so:
# "Permission is granted to copy, distribute and/or modify this document
# under the terms of the GNU Free Documentation License, Version 1.3; with
# ...". The invariant-sections phrase on its own is not that -- a
# CONTRIBUTING.md telling authors not to write "with no Invariant Sections"
# carries the words without granting anything, and settled the whole project
# as having none. Required near the notice for the same reason Exhibit B has
# to open a line: the words alone do not say who is speaking.
_GFDL_IS_NAMED = re.compile(
    r'(?:gnu\s+)?free documentation license|\bgfdl\b',
    re.IGNORECASE,
)

# And being granted, not merely named. A CONTRIBUTING.md saying "do not add
# the phrase ... to GFDL manuals" names the licence while granting nothing,
# and naming alone let it settle the whole project. The addendum's own
# wording is what a document applying the licence carries: "Permission is
# granted to copy, distribute and/or modify this document under the terms
# of ...".
_A_GRANT_IS_BEING_MADE = re.compile(
    r'under the terms of|permission is (?:hereby )?granted',
    re.IGNORECASE,
)

# "Reserved Font Name" refers to any names specified as such after the
# copyright statement, so the licence itself says where to look: the
# copyright line, which is exactly the line the hash tier strips before
# comparing texts. That is why a font whose OFL.txt names a reserved name
# still matches the licence exactly, and why the name is still there to read.
_RESERVED_FONT_NAME = re.compile(
    r'^[^\n]*\bcopyright\b[^\n]*?\bwith reserved font names?\b'
    r'(?P<names>[^\n]*)$',
    re.IGNORECASE | re.MULTILINE,
)

# What SIL ships for an author to replace, and what a document author is told
# to replace in the GFDL's addendum. A placeholder is not a declaration.
_UNFILLED = re.compile(r'^(?:<[^>]*>|list their titles)$', re.IGNORECASE)

# The sentence the notice sits in punctuates around it: SIL's template line
# ends "with Reserved Font Name <Reserved Font Name>." and a real one ends
# 'with Reserved Font Name "Wobble".'. Neither the quotes nor the full stop
# are part of the name, and leaving them on made the placeholder look filled.
_AROUND_THE_ANSWER = ' \t.,;:"\'()'


def _is_unfilled(value: str) -> bool:
    """Whether this is the template's placeholder rather than an answer."""
    bare = value.strip(_AROUND_THE_ANSWER)
    return not bare or bool(_UNFILLED.match(bare))


# How much text around a candidate phrase is rewritten to read it. A notice
# is one sentence, so the window is small and lopsided: the words the
# pre-filter matches sit near the front of the sentence, and what follows
# them -- a list of invariant section titles -- is the long part. Bounded so
# that the cost of reading a file is the cost of the notices in it rather
# than of its size: a deep scan that flowed every matching file whole spent
# most of its time rewriting licence databases and minified bundles that
# mention the words in passing.
#
# Small also keeps a window from reaching into a template that the candidate
# itself sits outside of.
_BEFORE_A_CANDIDATE = 300
_AFTER_A_CANDIDATE = 600

# How far a licence's own printing of a notice runs from its heading. MPL's
# Exhibit B is the heading, a rule and two lines; the GFDL's addendum is a
# page and ends the licence.
_EXHIBIT_B_IS_THIS_LONG = 500
_THE_ADDENDUM_IS_THIS_LONG = 2000

# A project file states a notice once. A file that mentions the words dozens
# of times is a licence list, a test corpus or a minified bundle, and reading
# further into it buys nothing.
_MOST_CANDIDATES_WORTH_READING = 64


def notices_in(text: str, source_file: Optional[str] = None) -> List[Notice]:
    """Every family notice this text applies, in no particular order.

    Applies, not mentions. A file that carries the licence's own template for
    a notice is carrying the template, and says nothing about itself.
    """
    if not text:
        return []
    candidates = [match.start() for match in _COULD_BE_A_NOTICE.finditer(text)]
    if not candidates:
        return []

    # Where in this file the licence prints its own template for a notice.
    # A span rather than a fact about the whole file: a GFDL manual states
    # its grant near the top and very often appends the licence itself, so a
    # guard that dismissed any file containing the addendum dismissed exactly
    # the documents this is for. Only a notice read inside the template is
    # the template.
    templates = _template_spans(text)

    found: Dict[str, Notice] = {}
    # Every candidate is read, not just the first of each family, because a
    # file that states its invariant sections *and* states it has none is
    # contradicting itself and the caller has to see both to leave the
    # ambiguity alone. Bounded, because a licence database mentions the
    # words hundreds of times and no project file mentions them twice.
    for at in candidates[:_MOST_CANDIDATES_WORTH_READING]:
        if len(found) == len(_FAMILY_OF):
            break
        if any(start <= at < end for start, end in templates):
            continue
        window = text[max(0, at - _BEFORE_A_CANDIDATE):at + _AFTER_A_CANDIDATE]
        for marker, phrase in _read(window):
            found.setdefault(marker, Notice(marker, phrase, source_file))

    return list(found.values())


def _template_spans(text: str):
    """Where this file prints a licence's own template for a notice.

    Both licences print theirs under a heading and neither runs long: MPL's
    Exhibit B is the heading, a rule and two lines, and the GFDL's addendum
    is a page. Measured from the heading rather than to the end of the file,
    so that a manual with the licence appended keeps the notice it states in
    its own right.
    """
    spans = []
    for heading, length in (
        (_EXHIBIT_B_HEADING, _EXHIBIT_B_IS_THIS_LONG),
        (_GFDL_ADDENDUM, _THE_ADDENDUM_IS_THIS_LONG),
    ):
        for printed in heading.finditer(text):
            spans.append((printed.start(), printed.start() + length))
    return spans


def _read(window: str):
    """The notices in one window, as (marker, phrase) pairs."""
    flowed = _flowing(window)

    # Read on the raw window: whether the notice opens a line is the whole
    # of what separates it from a sentence about it, and flowing is what
    # takes the line openings away.
    applied = _EXHIBIT_B_NOTICE.search(window)
    if applied:
        yield EXHIBIT_B, _flowing(applied.group(0))

    # Both forms are reported when both are there, rather than the first or
    # the stronger. They cannot both be true of one document, and which of
    # them a scan should believe is not a question about this window: the
    # caller holds every notice in the scan and leaves a family alone when
    # its notices disagree. Deciding it here would settle a contradiction by
    # reading order and hide it.
    if (
        _GFDL_IS_NAMED.search(flowed)
        and _A_GRANT_IS_BEING_MADE.search(flowed)
    ):
        named = _INVARIANT_SECTIONS.search(flowed)
        if named and not _is_unfilled(named.group('titles')):
            yield INVARIANT_SECTIONS, named.group(0)
        disclaimed = _NO_INVARIANT_SECTIONS.search(flowed)
        if disclaimed:
            yield NO_INVARIANT_SECTIONS, disclaimed.group(0)

    # Read on the raw lines rather than the flowed text, because the licence
    # puts the reserved name after the copyright statement and it is the line
    # that makes it a copyright statement.
    for reserved in _RESERVED_FONT_NAME.finditer(window):
        if not _is_unfilled(reserved.group('names')):
            yield RESERVED_FONT_NAME, reserved.group(0).strip()
            break


# ---------------------------------------------------------------------------
# Working out which identifier a notice names
# ---------------------------------------------------------------------------

def _carries_no_copyleft_exception(spdx_id: str) -> bool:
    return spdx_id.endswith('-no-copyleft-exception')


def _carries_a_reserved_font_name(spdx_id: str) -> bool:
    return spdx_id.endswith('-RFN') and not spdx_id.endswith('-no-RFN')


def _carries_invariant_sections(spdx_id: str) -> bool:
    # `-no-invariants-` contains `-invariants-`, so the negative form has to
    # be excluded rather than merely not matched.
    return '-invariants' in spdx_id and '-no-invariants' not in spdx_id


def _carries_no_invariant_sections(spdx_id: str) -> bool:
    return '-no-invariants' in spdx_id


_NAMES_THE_MEMBER = {
    EXHIBIT_B: _carries_no_copyleft_exception,
    RESERVED_FONT_NAME: _carries_a_reserved_font_name,
    INVARIANT_SECTIONS: _carries_invariant_sections,
    NO_INVARIANT_SECTIONS: _carries_no_invariant_sections,
}

# Notices that cannot both be true of one work. A scan finding both has found
# a project that contradicts itself, or a reader that misread one of them, and
# either way the honest answer is the ambiguity #142 already reports.
_CONTRADICTS = {
    INVARIANT_SECTIONS: NO_INVARIANT_SECTIONS,
    NO_INVARIANT_SECTIONS: INVARIANT_SECTIONS,
}


def names_a_member(spdx_id: str) -> bool:
    """Whether this identifier already says which member of its family it is.

    A notice adds what an identifier left out, so it has something to say
    about `MPL-2.0` and nothing to say about `MPL-2.0-no-copyleft-exception`.
    A file that states a member has already answered, and where the two
    disagree that disagreement is the finding: read as a qualification
    instead, the notice quietly replaced the identifier the file wrote.

    Asked of the identifier's own shape rather than of the notices, because
    not every member has a notice that names it. Nothing reads a font's
    licence and concludes `OFL-1.1-no-RFN`, but a file may still say so, and
    borrowing the notice predicates left that identifier looking like an
    unanswered family for a Reserved Font Name line to overwrite.
    """
    return (
        spdx_id.endswith((
            '-RFN',                       # and `-no-RFN`, which ends with it
            '-no-copyleft-exception',
            '-Combined-Work-Exception',
        ))
        or '-invariants' in spdx_id       # and `-no-invariants`
    )


def any_contradiction(markers) -> bool:
    """Whether these notices include two that cannot both be true.

    Asked of a whole scan before any of them is allowed to answer for a file
    other than the one it was read in. A project whose documents disagree
    about their invariant sections has not settled anything, and letting the
    first one reached answer for the licence file they share made the report
    depend on which thread finished first.
    """
    held = set(markers)
    return any(_CONTRADICTS.get(marker) in held for marker in held)


def settled_only_in_its_own_file(spdx_id: str) -> bool:
    """Whether evidence for this member says anything about other files.

    The reserved-name members are the ones it does not. A font's reserved
    name is a fact about that font, written on its own licence file, and a
    project may hold two OFL files -- its own and a vendored one. Said of the
    identifier rather than of the notice, because a project can name the
    member outright as well as describe it, and `SPDX-License-Identifier:
    OFL-1.1-RFN` in one licence file is no more about the other than the
    copyright line is.
    """
    return '-RFN' in spdx_id


def _grant(spdx_id: str) -> str:
    """The `-only` or `-or-later` this identifier carries, if it carries one.

    Which version of a licence may be used is a different question from which
    member of a family a work carries, and the notices read here answer only
    the second. A GFDL document naming its Invariant Sections has said nothing
    about later versions, so the grant already worked out is kept as it is.
    """
    for suffix in ('-or-later', '-only'):
        if spdx_id.endswith(suffix):
            return suffix
    return ''


def the_member_named(chosen: str, candidates: Sequence[str],
                     notices: Dict[str, Notice]
                     ) -> Optional[Tuple[str, Notice]]:
    """Which of these candidates the notices name, and the notice that said so.

    `candidates` is the whole family in play -- the identifier the hash tier
    chose, and the ones #142 named beside it. Returns the one member the
    notices settle on, or None, which leaves the record ambiguous.

    None is the answer whenever anything is in doubt: no notice, a notice
    contradicted by another, or a notice that narrows the family without
    settling it. A scan that reports the family is right about less than it
    could be; a scan that picks the wrong member is wrong.
    """
    family = list(dict.fromkeys([chosen, *candidates]))
    if len(family) < 2:
        return None

    for marker, notice in notices.items():
        names_it = _NAMES_THE_MEMBER.get(marker)
        if not names_it:
            continue
        if _CONTRADICTS.get(marker) in notices:
            continue

        named = [spdx_id for spdx_id in family if names_it(spdx_id)]
        if len(named) > 1:
            # The family splits on a second axis the notice says nothing
            # about, as the GFDL's does on `-only` against `-or-later`.
            # Whatever the scan already worked out about that axis stands.
            named = [
                spdx_id for spdx_id in named if _grant(spdx_id) == _grant(chosen)
            ]
        if len(named) == 1:
            return named[0], notice

    return None
