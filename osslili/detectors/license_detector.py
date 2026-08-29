"""
License detection module with multi-tier detection system.
"""

import itertools
import logging
import re
import fnmatch
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Optional, Set
from concurrent.futures import ThreadPoolExecutor, as_completed

from fuzzywuzzy import fuzz

from ..core.models import DetectedLicense, DetectionMethod, LicenseCategory
from ..core.input_processor import InputProcessor
from ..data.spdx_licenses import SPDXLicenseData
from .tlsh_detector import TLSHDetector
from ..utils.file_scanner import SafeFileScanner
from ..utils.license_normalizer import LicenseNormalizer
from ..utils.regex_matcher import RegexPatternMatcher
from ..utils.text_similarity import create_bigrams, dice_coefficient

logger = logging.getLogger(__name__)

# SPDX deprecated the bare GNU-family short identifiers (e.g. "GPL-2.0") in
# favour of an explicit -only / -or-later disjunction, because the bare id is
# ambiguous about whether later license versions are permitted. This matches a
# bare GNU-family id so it can be mapped to its modern replacement.
_DEPRECATED_GNU_RE = re.compile(r'^(?:A?GPL|LGPL|GFDL)-\d+(?:\.\d+)?$')

# Prose that *discusses* a license instead of granting it: compatibility notes,
# license history, explicit exclusions, and linking exceptions that name a
# library's license only to carve it out. A license name in a sentence like
# this says nothing about the terms the file carries. The PSF license stack is
# the motivating case — it explains at length how Python relates to the GPL
# while the package itself is Python-2.0, and a keyword hit on that prose used
# to assert copyleft over a permissive package (issue #91).
_LICENSE_DISCUSSION_RE = re.compile(
    # A compatibility *claim about licensing*, not the ordinary English word.
    # "ensuring compatibility with both open source and commercial products"
    # sits in a genuine grant sentence and must not suppress it.
    r'(?:licen[sc]e|GPL|LGPL|AGPL|BSD|MIT|Apache|MPL)[\s-]*(?:in)?compatib'
    r'|(?:in)?compatib\w*\s+with\s+(?:the\s+)?(?:GNU\s+)?'
    r'(?:GPL|LGPL|AGPL|BSD|MIT|Apache|MPL|General\s+Public|licen[sc]e)'
    r'|unlike\s+th(?:e|is)\b'
    r'|(?:previously|formerly|originally)\s+(?:distributed|released|licen[sc]ed)'
    r'|does\s+not\s+mean\b'
    r'|(?:is|are|was|were)\s+not\s+(?:distributed|released|licen[sc]ed)\b',
    re.IGNORECASE,
)

# Linking exceptions get their own guard. They name a library's license only to
# carve it out — "permission to link ... with the OpenSSL library" — so the
# named license does not govern the file. But the exception is *attached to* a
# copyleft grant, and the file carrying it is by definition licensed under that
# copyleft license. Suppressing the GNU-family match too reported GPL source
# files as carrying no license at all, so this guard never applies to them.
_LINKING_EXCEPTION_RE = re.compile(
    r'as\s+a\s+special\s+exception'
    r'|permission\s+to\s+link'
    r'|linking\s+exception',
    re.IGNORECASE,
)

# License families a linking exception is granted *over*, never carved out of.
_GNU_FAMILY_PREFIXES = ('GPL', 'LGPL', 'AGPL', 'GFDL')

# Cap on how far the discussion scan reaches from a match when the text has no
# paragraph breaks to bound it.
_DISCUSSION_SPAN_LIMIT = 400

# A paragraph break: a blank line, or a line carrying nothing but comment
# markers. Source headers are the reason for the second case — in a "/* ... */"
# block the blank lines read as " *", so searching for "\n\n" alone finds no
# break at all and runs the entire header together as one paragraph.
_PARAGRAPH_BREAK_RE = re.compile(r'\n[ \t]*(?:[*#]|//|--|;)?[ \t]*\r?\n')

# An explicit GNU version, as licenses actually write it. Covers the phrasing
# the FSF itself recommends and which most GPL source headers therefore use --
# "either version 2 of the License, or (at your option) any later version" --
# where the version attaches to "the License" rather than to "GPL". Also covers
# "GPL-2.0", "GPLv3", "GPL version 2", and the separator-less "GPL2".
#
# A bare digit near a license name is still not a version: a copyright year or a
# section number would qualify just as well, so an unversioned mention yields no
# identifier rather than a guessed one.
_GNU_VERSION_RE = re.compile(
    r'(?:A?GPL|LGPL|General\s+Public\s+License)[\s,-]*v?(?:ersion\s*)?([123])(?:\.\d+)?\b'
    r'|\bv(?:ersion\s*)?\s*([123])(?:\.\d+)?\s+of\s+the\s+(?:GNU\s+)?'
    r'(?:A?GPL|LGPL|General\s+Public\s+)?Licen[sc]e\b'
    r'|\bv(?:ersion\s*)?([123])(?:\.\d+)?\s*(?:of\s+the\s+)?(?:GNU\s+)?'
    r'(?:A?GPL|LGPL|General\s+Public\s+License)',
    re.IGNORECASE,
)

# "or (at your option) any later version" — the FSF header wording that makes a
# versioned grant an "-or-later" one rather than "-only".
_GNU_OR_LATER_RE = re.compile(
    r'any\s+later\s+version|or\s+later\b|or,?\s+at\s+your\s+option',
    re.IGNORECASE,
)

# A generic "General Public License" match that is really part of the Lesser or
# Affero name. Those have their own identifiers, so the generic GPL path must
# not claim them.
_GNU_VARIANT_PREFIX_RE = re.compile(r'(?:Lesser|Library|Affero)\s+$', re.IGNORECASE)

# Ceiling on a regex match reached through the full-text cascade, i.e. after
# every tier that compares actual text has declined. Set below the keyword tier
# so a pattern hit on an unrecognized document cannot outrank a license name
# read in context, let alone a real text match.
_UNIDENTIFIED_TEXT_CONFIDENCE_CAP = 0.6

# Lowest Dice-Sørensen score the similarity tier will consider at all. Between
# this floor and the configured similarity_threshold a match must be
# corroborated by TLSH; at or above the threshold the score stands on its own.
_DICE_FLOOR = 0.9

# The number of occurrences of a single keyword variation examined per file.
# Bounds the cost on pathological inputs while leaving room to skip over
# discussion prose to a real grant later in the same file.
_MAX_KEYWORD_OCCURRENCES = 50


def _paragraph_around(content: str, start: int, end: int) -> str:
    """Return the paragraph containing content[start:end].

    Discussion qualifiers govern their own paragraph: a linking exception names
    the library it carves out a sentence or two after "as a special exception",
    while the heading that states a file's real license sits in a paragraph of
    its own. A fixed character window cannot tell those apart — it either
    reaches too short to catch the exception or far enough to swallow the
    heading in a densely packed aggregate license file.
    """
    # Inside a block comment a "blank" line still carries its comment marker
    # (" *", "#", "//"), so a bare "\n\n" search runs the whole file together.
    # Treat a line with nothing but markers and whitespace as a break too.
    paragraph_start = 0
    for match in _PARAGRAPH_BREAK_RE.finditer(content, 0, start):
        paragraph_start = match.end()

    paragraph_end_match = _PARAGRAPH_BREAK_RE.search(content, end)
    paragraph_end = paragraph_end_match.start() if paragraph_end_match else len(content)

    return content[
        max(paragraph_start, start - _DISCUSSION_SPAN_LIMIT):
        min(paragraph_end, end + _DISCUSSION_SPAN_LIMIT)
    ]


def _is_contained_by(candidate: Path, base: Path) -> bool:
    """Whether ``candidate`` resolves to somewhere inside ``base``.

    A manifest's license path is untrusted input. Left unchecked,
    ``license = {file = "../../../secrets.txt"}`` makes osslili read a file
    outside the tree it was asked to scan and report its license as the
    project's own — and an absolute path is worse, because joining one discards
    the base directory entirely.

    Resolution follows symlinks, so a link pointing out of the tree is caught
    on the same test.
    """
    try:
        candidate.resolve().relative_to(base.resolve())
    except (ValueError, OSError):
        return False
    return True


def _bounded_pattern(variation: str) -> str:
    """Build a whole-word regex for a license keyword variation.

    Without word boundaries a short identifier matches inside ordinary words —
    "MIT" occurs in "permitted" and "limitation", which appear throughout the
    LGPL and MPL texts. Boundaries are only added on sides that end in a word
    character, so variations bounded by punctuation (e.g. "MIT/X11") still
    match.
    """
    prefix = r'\b' if variation[:1].isalnum() or variation[:1] == '_' else ''
    suffix = r'\b' if variation[-1:].isalnum() or variation[-1:] == '_' else ''
    return prefix + re.escape(variation) + suffix


# What may sit between the start of a line and a licence header: indentation
# and comment markers. Semicolons open a comment in Lisp and in ini files,
# percent signs in TeX and R, parentheses with a star in ML and Pascal, and a
# header written in one of those is as much a declaration as one in C.
#
# Written as whole markers rather than a set of characters, because a set
# containing a hyphen also accepted a Markdown bullet, and "- Licensed under
# the MIT License" under a Dependencies heading is a credit, not a header.
_COMMENT_OPENING = r'(?:[\s*#;%]|//|/\*|<!--|--|\(\*)*'

# Ways a file refers to itself before saying what it is licensed under.
# "This file is licensed under the MIT License" and "Dual licensed under MIT
# OR Apache-2.0" are the file stating its own licence, not crediting anything.
#
# A bare "Also" is not among them. It continues whatever sentence came before,
# and after "the bundled parser is licensed under the BSD License" the thing
# it continues is a credit. Without tracking what the previous sentence was
# about there is no way to tell, and reading it as a declaration is the answer
# that puts someone else's licence on the package.
# A file whose subject is prose. It has no comment syntax, so an asterisk or
# a hyphen opening a line is a bullet, and a quoted "license": "MIT" is the
# document showing what a metadata file contains rather than declaring
# anything. Only forms that are headers in prose as well count there.
_DOCUMENT_SUFFIXES = (
    '.md', '.markdown', '.mdown', '.rst', '.adoc', '.asciidoc',
    '.txt', '.text', '.textile', '.org', '.rdoc', '.pod', '.wiki', '.me',
)

# Prose files that carry no suffix at all. A GNU-style README is the common
# one, and it took the rules for code, so an asterisk opening a bullet was
# read as a comment marker and a credit under it declared.
_DOCUMENT_STEMS = (
    'readme', 'readme.1st', 'install', 'changelog', 'changes', 'news',
    'history', 'authors', 'contributors', 'contributing', 'credits',
    'thanks', 'todo', 'faq', 'security', 'support', 'roadmap', 'manual',
)

# The openings a document can have: indentation, and the markers that are
# still comments in one. Not the asterisk or the double hyphen, which are a
# bullet and a rule.
_DOCUMENT_OPENING = r'(?:[\s#]|<!--)*'


def _has_a_document_suffix(file_path) -> bool:
    """Whether the name says this file's subject is prose."""
    name = str(getattr(file_path, 'name', file_path)).lower()
    if any(name.endswith(suffix) for suffix in _DOCUMENT_SUFFIXES):
        return True
    # Matched whole, so the guard against names with a suffix is not needed
    # and did make README.1st unreachable, since the entry for it has one.
    return name in _DOCUMENT_STEMS


# What a licence name may be made of. It is the terminator below that keeps
# it from running on: ending the match at a full stop followed by a space
# stops the capture at the end of the sentence, which is what it took to
# report BSD-2-Clause rather than the whole of "BSD-2-Clause License. The
# bundled CSS minifier is", which normalised to BSD-3-Clause, a licence the
# file never names.
_LICENCE_NAME = r'([A-Za-z0-9\-\.\s]+?)'


# The shape of an SPDX expression: identifiers joined by OR, AND or WITH,
# optionally in parentheses. Used to take the expression off the front of a
# header line and leave whatever follows it, because the rest of the line is
# not always the expression: "License: BSD-2-Clause (see LICENSE)" handed
# whole to the parser became "BSD-2-Clause see LICENSE", which the normaliser
# then read as plain BSD and reported as BSD-3-Clause.
# A term of an expression: an identifier, wrapped in any number of brackets.
# Not one bracket: the kernel's own dual licence tag opens with two,
# "((GPL-2.0 WITH Linux-syscall-note) OR BSD-2-Clause)", and a term that
# allowed only one matched nothing at all, which threw the whole line away
# and left the file with no licence. Space is allowed inside the brackets,
# "( MIT OR Apache-2.0 )", for the same reason.
# The colon belongs to one shape only, "DocumentRef-x:LicenseRef-y", which
# names a licence held in another document. Leaving it out cut the term at
# the colon, and the operator after it was never reached, so
# "DocumentRef-upstream:LicenseRef-foo OR MIT" lost the MIT as well.
_IDENTIFIER = r'(?:DocumentRef-[A-Za-z0-9.\-]+:)?[A-Za-z0-9.\-+]+'
_TERM = r'(?:\(\s*)*' + _IDENTIFIER + r'(?:\s*\))*'


def _expression(joiner: str) -> "re.Pattern":
    return re.compile(_TERM + r'(?:' + joiner + _TERM + r')*')


_UPPER_CASE = r'\s+(?:OR|AND|WITH)\s+'
# A comma joins a list of licences, "GPL-2.0, BSD-3-Clause", and is read like
# a lower-case operator: only where the terms either side of it are licences,
# because "BSD-2-Clause, see LICENSE" is a sentence.
_ANY_CASE = (
    r'(?:\s+(?:[Oo][Rr]|[Aa][Nn][Dd]|[Ww][Ii][Tt][Hh])\s+|\s*,\s*)'
)


# One term and no operator, which is what is left when the terms of a longer
# reading are not all licences.
_JUST_A_TERM = re.compile(_TERM)


# Whether the operators must be upper case depends on the field, because the
# fields differ in what they are allowed to contain.
#
# "SPDX-License-Identifier" and "License-Expression" are defined to hold an
# expression and nothing else, so a lower-case operator there is a spelling
# slip and reading it costs nothing: "SPDX-License-Identifier: MIT or
# Apache-2.0" names two licences and reporting one drops a choice the
# licensor offered.
#
# "License:" and "@license" hold free text, and there the same words are
# ordinary English. "License: MIT and BSD-compatible" read "and" as an
# operator and reported BSD-3-Clause, which the file does not name.
_EXPRESSION = _expression(_UPPER_CASE)
_EXPRESSION_IN_ANY_CASE = _expression(_ANY_CASE)


# The header forms, whose capture runs to the end of a line and so may pick
# up a closing comment marker or a note to the reader. A quoted value is not
# among them however it is anchored: what follows it on the line is outside
# the quotes and was never captured.
#
# "Licensed under the ..." is not among them either. Its capture is a licence
# name in prose, not an expression, and trimming it to the expression at the
# front cut the name at its first space: "Licensed under the MIT No
# Attribution License" became MIT, asserting an attribution obligation the
# licensor had waived, and the longer names lost their identifier outright.
_LINE_FORMS = (
    'SPDX-License-Identifier',
    'License-Expression',
    'License:',
    '@license',
)


# The forms above that are defined to hold an expression and nothing else,
# and so may spell their operators in any case.
_EXPRESSION_FORMS = (
    'SPDX-License-Identifier',
    'License-Expression',
)


def _reads_a_line(pattern) -> bool:
    """Whether this pattern's capture runs to the end of a line.

    Decided by which form it matches, and no quoted value matches one, which
    a test asserts. Checking for a quote as well would be a second rule
    saying the same thing, and nothing could tell whether it still held.
    """
    return any(form in pattern.pattern for form in _LINE_FORMS)


def _holds_an_expression(pattern) -> bool:
    """Whether this pattern's field may hold nothing but an expression.

    Takes the pattern itself or its source, because the two readers of a
    header line hold one each, and asking the question two ways in two places
    let them drift: one called this and the other spelled it out again, so a
    free-text form reached only by the second was read as though it held an
    expression.
    """
    source = pattern if isinstance(pattern, str) else pattern.pattern
    return any(form in source for form in _EXPRESSION_FORMS)


_TERMS = re.compile(r'\s+(?:[Oo][Rr]|[Aa][Nn][Dd])\s+|\s*,\s*')
_AN_EXCEPTION = re.compile(r'\s+[Ww][Ii][Tt][Hh]\s+.*$')


def _every_term_names_a_licence(expression: str, names_a_licence) -> bool:
    """Whether each side of every operator is a licence, and not a word.

    This is what separates an expression whose operators are spelled in lower
    case from a sentence that merely contains the word "and". Both look the
    same; only their terms differ.

    A term is an operand of OR or AND. What follows WITH is an exception, not
    a licence, and asking whether it names one refused the whole expression:
    "GPL-2.0-only WITH Classpath-exception-2.0 or MIT" lost the MIT, which
    is a choice the licensor offered.
    """
    terms = [
        _AN_EXCEPTION.sub('', term).strip(' ()')
        for term in _TERMS.split(expression)
    ]
    return all(names_a_licence(term) for term in terms)


def _expression_at_the_front(
    text: str, names_a_licence, holds_an_expression: bool = False,
) -> str:
    """The SPDX expression this line opens with, and nothing after it.

    Brackets around a whole expression need no special handling: each term of
    the pattern above allows any number, so both "(MIT AND BSD-3-Clause)" and
    the nested "((GPL-2.0 WITH Linux-syscall-note) OR MIT)" match through.

    Three readings are tried, longest first, and the first whose every term
    is a licence is the answer. What separates an expression from a sentence
    is not the spelling of the word between the terms but the terms
    themselves, and each reading is only as good as they are.

    The longest reading is offered to a field defined to hold an expression
    and nothing else, where the operators may be spelled in any case and a
    comma may stand in for one. "SPDX-License-Identifier: MIT or Apache-2.0"
    names two licences, and so does "GPL-2.0, BSD-3-Clause".

    Then the upper-case reading, which any field may have, because upper case
    is what SPDX defines. It is still held to the same test: "License: MIT
    AND BSD-compatible" is a sentence about MIT, and taking the AND at its
    word reported BSD-3-Clause, which the file does not name.

    Last, one term and no operator, which is what a sentence leaves behind.

    A name written with a space in it, "Apache 2.0 or MIT", is not an SPDX
    identifier and no reading here can span it; the first licence is
    reported and the rest of the line is not. Admitting spaces into a term
    is how prose gets in, which is the fault this whole function exists to
    prevent.
    """
    text = text.strip()
    readings = [_EXPRESSION_IN_ANY_CASE] if holds_an_expression else []
    readings.append(_EXPRESSION)

    for reading in readings:
        match = reading.match(text)
        if match and _every_term_names_a_licence(match.group(0), names_a_licence):
            return match.group(0)

    # One term and no operator. Not held to the test, because it is the last
    # reading and there is no second term for it to invent: what a loose name
    # like "Apache" resolves to is the normaliser's business, and refusing it
    # here left a file whose licence line names one licence with none.
    match = _JUST_A_TERM.match(text)
    return match.group(0) if match else ''


_SELF_REFERRING = (
    # optionally "Portions of ..."
    r'(?:portions\s+of\s+)?'
    r'(?:th(?:is|e)\s+(?:file|project|software|package|library|module|work|'
    r'code|program|distribution|repository|repo|crate|gem|plugin|extension|'
    r'tool|application|app|component|utility|source\s+code|contents)|'
    r'dual|source\s+code)\s*'
    r'(?:is|are|was|may\s+be|can\s+be)?\s*'
    # "is dual licensed", "are jointly licensed"
    r'(?:dual|jointly|multi)?\s*'
)


class LicenseDetector:
    """Detect licenses in source code using multiple detection methods."""
    
    def __init__(self, config):
        """
        Initialize license detector.
        
        Args:
            config: Configuration object
        """
        self.config = config
        self.input_processor = InputProcessor()
        self.spdx_data = SPDXLicenseData(config)
        # Ensure SPDX data and hashes are loaded
        _ = self.spdx_data.licenses  # Trigger lazy loading of licenses and hashes
        self.tlsh_detector = TLSHDetector(config, self.spdx_data)
        self.license_normalizer = LicenseNormalizer()
        self.regex_matcher = RegexPatternMatcher()
        
        # License filename patterns
        self.license_patterns = self._compile_filename_patterns()
        
        # SPDX tag patterns
        self.spdx_tag_patterns = self._compile_spdx_patterns()
        self.prose_patterns = self._compile_prose_patterns()
        self.document_tag_patterns = self._compile_document_tag_patterns()
        
        # Common license indicators in text
        self.license_indicators = [
            'licensed under', 'license', 'copyright', 'permission is hereby granted',
            'redistribution and use', 'all rights reserved', 'this software is provided',
            'warranty', 'as is', 'merchantability', 'fitness for a particular purpose'
        ]
    
    def _categorize_license(self, file_path: Path, detection_method: str, match_type: str = None) -> tuple[str, str]:
        """
        Categorize a license based on where and how it was detected.
        
        Returns:
            Tuple of (category, match_type)
        """
        file_name = file_path.name.lower()
        file_str = str(file_path).lower()

        # Bundled third-party notices are dependency licenses, not the project's
        # own license. Tag them separately so they can be filtered out (issue #78).
        if self._is_third_party_notice_file(file_path):
            return LicenseCategory.THIRD_PARTY.value, "third_party_notice"

        # Primary declared licenses - found in LICENSE files or package metadata
        if self._is_license_file(file_path):
            return LicenseCategory.DECLARED.value, "license_file"
        
        # Package metadata files
        if file_name in ['package.json', 'setup.py', 'setup.cfg', 'pyproject.toml',
                         'cargo.toml', 'pom.xml', 'build.gradle', 'composer.json'] or \
           file_name.endswith('.gemspec') or file_name.endswith('.nuspec'):
            return LicenseCategory.DECLARED.value, "package_metadata"
        
        # SPDX tags in any file are considered declared
        if detection_method == DetectionMethod.TAG.value:
            return LicenseCategory.DECLARED.value, "spdx_identifier"
        
        # References in source code comments or documentation
        if detection_method == DetectionMethod.REGEX.value:
            # Check if it's in documentation
            if any(ext in file_name for ext in ['.md', '.rst', '.txt', '.adoc']):
                return LicenseCategory.DECLARED.value, "documentation"
            # Check if it's a full license header vs. brief reference
            # match_type gets passed with information about how many patterns matched
            if match_type == "license_header":
                return LicenseCategory.DECLARED.value, "license_header"
            else:
                return LicenseCategory.REFERENCED.value, "license_reference"
        
        # Text similarity matches in non-license files are detected
        if detection_method in [DetectionMethod.TLSH.value, DetectionMethod.DICE_SORENSEN.value]:
            if self._is_license_file(file_path):
                return LicenseCategory.DECLARED.value, "text_similarity"
            return LicenseCategory.DETECTED.value, "text_similarity"
        
        # Default to detected for unknown cases
        return LicenseCategory.DETECTED.value, match_type or "unknown"

    def _is_valid_license_id(self, license_id: str) -> bool:
        """Validate that detected license ID is actually a license."""
        if not license_id or not isinstance(license_id, str):
            return False

        # Authoritative shortcut: any real SPDX identifier is valid, even short
        # ones like "ISC" that the heuristics below would otherwise reject as
        # generic single words. A trailing "+" ("or later" form) is tolerated.
        if self._is_valid_spdx_id(license_id) or self._is_valid_spdx_id(license_id.rstrip('+')):
            return True

        license_lower = license_id.lower().strip()

        # Common false positive words
        false_positive_words = {
            'this', 'the', 'that', 'and', 'or', 'with', 'by', 'for', 'in', 'on', 'at',
            'frame', 'packet', 'data', 'file', 'code', 'text', 'software', 'terms',
            'license', 'copyright', 'notice', 'header', 'comment', 'version',
            'able', 'ed', 'ing', 'as', 'is', 'are', 'was', 'were', 'be', 'been',
            'filter', 'bit', 'flag', 'means', 'we', 'you', 'they', 'them'
        }

        # Filter partial phrases that contain stopwords
        partial_phrase_indicators = [
            'terms-of-the-', 'license-', 'copyright-', 'notice-', 'header-',
            'version-', 'file-', 'code-', 'software-', '-the-', '-of-', '-and-'
        ]

        if any(indicator in license_lower for indicator in partial_phrase_indicators):
            return False

        # Too short (but allow well-known short licenses like ISC)
        if len(license_id) < 3:
            return False

        # Exact match against false positives
        if license_lower in false_positive_words:
            return False

        # Must contain valid license pattern indicators - Made more specific
        valid_license_indicators = [
            'gpl', 'lgpl', 'mit', 'bsd', 'apache', 'mpl', 'zlib', 'openssl',
            'json', 'vim', 'unlicense', 'wtfpl', 'cc-', 'creative', 'copyleft',
            'artistic', 'eclipse', 'mozilla', 'cddl', 'epl', 'ibm', 'intel',
            'nvidia', 'ofl', 'sil', 'x11', 'ms-', 'microsoft', 'proprietary',
            'commercial', 'public-domain', 'bsl', 'boost', 'ijg', 'jpeg',
            'foundation', 'software', 'consortium', 'blueoak-'
        ]

        # Additional validation: single word generic terms should be rejected
        generic_single_words = ['python', 'ruby', 'php', 'perl', 'java', 'javascript',
                               'node', 'go', 'rust', 'swift', 'kotlin', 'scala',
                               'domain', 'free', 'open', 'source', 'clear']

        # Reject single generic words unless they're clearly license identifiers
        if license_lower in generic_single_words:
            return False

        # Special cases for build flags and restrictions
        build_flags = ['nonfree', 'unredistributable', 'proprietary', 'commercial']
        if license_lower in build_flags:
            return True  # These are valid license restrictions

        # Check if it contains any valid license indicators
        has_valid_indicator = any(indicator in license_lower for indicator in valid_license_indicators)

        # Additional check: if it looks like a proper SPDX identifier
        spdx_pattern_indicators = ['-only', '-or-later', '-with-', 'clause']
        has_spdx_pattern = any(indicator in license_lower for indicator in spdx_pattern_indicators)

        return has_valid_indicator or has_spdx_pattern

    def _create_detected_license(self, spdx_id: str, name: str, confidence: float,
                                file_path: Path, detection_method: str,
                                match_type: str = None) -> Optional[DetectedLicense]:
        """Create a DetectedLicense object with validation."""
        # Apply false positive filtering
        if not self._is_valid_license_id(spdx_id):
            logger.debug(f"Filtered out false positive license: '{spdx_id}' from {file_path}")
            return None

        # Get category and match info
        category, match_info = self._categorize_license(file_path, detection_method, match_type)

        from ..core.models import DetectedLicense
        return DetectedLicense(
            spdx_id=spdx_id,
            name=name,
            confidence=confidence,
            detection_method=detection_method,
            file_path=str(file_path),
            match_type=match_info,
            category=category,
            text_snippet="",  # Can be filled later if needed
            match_lines=[]
        )

    def _compile_filename_patterns(self) -> List[re.Pattern]:
        """Compile filename patterns for license files."""
        patterns = []
        
        for pattern in self.config.license_filename_patterns:
            # Convert glob to regex
            regex_pattern = fnmatch.translate(pattern)
            patterns.append(re.compile(regex_pattern, re.IGNORECASE))
        
        return patterns
    
    
    def _compile_spdx_patterns(self) -> List[re.Pattern]:
        """Compile SPDX identifier patterns."""
        return [
            # SPDX-License-Identifier: <license>
            # Match complex expressions including parentheses, AND, OR, WITH
            # Stop at newline or end of comment markers
            # Anchored, because the identifier is a header. Unanchored, the
            # sentence "dependency foo declares SPDX-License-Identifier: MIT"
            # was read as this file declaring MIT.
            re.compile(r'^' + _COMMENT_OPENING + r'SPDX-License-Identifier:\s*([^\n]+?)(?:\s*\*/)?(?:\s*-->)?$', re.IGNORECASE | re.MULTILINE),
            # Python METADATA: License-Expression: <license>
            re.compile(r'^' + _COMMENT_OPENING + r'License-Expression:\s*([^\n]+)', re.IGNORECASE | re.MULTILINE),
            # package.json style: "license": "MIT" or licenses array with "type": "MIT"
            re.compile(r'"license"\s*:\s*"([^"]+)"', re.IGNORECASE),
            # package.json licenses array: {"type": "MIT", ...}
            re.compile(r'"type"\s*:\s*"([^"]+)"', re.IGNORECASE),
            # pyproject.toml style: license = {text = "Apache-2.0"}
            re.compile(r'license\s*=\s*\{[^}]*text\s*=\s*"([^"]+)"', re.IGNORECASE),
            # pyproject.toml style: license = "MIT"
            re.compile(r'^\s*license\s*=\s*"([^"]+)"', re.IGNORECASE | re.MULTILINE),
            # General License: <license> (but more restrictive to avoid false positives)
            re.compile(r'^\s*License:\s*([A-Za-z0-9\-\.]+)', re.IGNORECASE | re.MULTILINE),
            # @license <license>
            re.compile(r'^' + _COMMENT_OPENING + r'@license\s+([^\n]+)', re.IGNORECASE | re.MULTILINE),
            # A line opening with "Licensed under <license>", which is how
            # Apache's boilerplate declares itself, in the licence text and in
            # every source header carrying it. Also the forms where the file
            # names itself first: "This file is licensed under the MIT
            # License", "Dual licensed under MIT OR Apache-2.0".
            # With no subject, capitalised. A hard-wrapped sentence
            # continues in lower case, so "licensed under the BSD-2-Clause
            # License. The bundled CSS minifier is" opening a line is the
            # middle of a credit, not the start of a header.
            re.compile(
                r'^' + _COMMENT_OPENING + r'(?-i:Licensed)\s+under\s+(?:the\s+)?'
                r'' + _LICENCE_NAME + r'(?:\s+[Ll]icense)?(?:\.\s|[,\n;]|$)',
                re.IGNORECASE | re.MULTILINE,
            ),
            # With a subject, any case: "This file is licensed under the MIT
            # License" is a sentence of its own however it is capitalised.
            re.compile(
                r'^' + _COMMENT_OPENING + _SELF_REFERRING
                + r'[Ll]icensed\s+under\s+(?:the\s+)?'
                r'' + _LICENCE_NAME + r'(?:\s+[Ll]icense)?(?:\.\s|[,\n;]|$)',
                re.IGNORECASE | re.MULTILINE,
            ),
        ]

    def _reads_as_a_document(self, file_path) -> bool:
        """Whether this file's subject is prose rather than code.

        A licence file is not a document however it is suffixed, since
        LICENSE.txt and LICENCE.md hold the licence itself. Which files those
        are is asked of _is_license_file rather than decided again here, so
        there is one answer to that question rather than two that can drift.
        """
        if not _has_a_document_suffix(file_path):
            return False
        return not self._is_license_file(Path(str(file_path)))

    def _compile_document_tag_patterns(self) -> List[re.Pattern]:
        """The declaration forms that mean something in a document.

        A README has no comment syntax. An asterisk or a hyphen opening a line
        is a bullet, so "- Licensed under the MIT License" under a
        Dependencies heading is a credit rather than a header, and a quoted
        \"license\": \"MIT\" is the document showing what a package file
        contains. Those forms are dropped here and kept for code.
        """
        return [
            re.compile(r'^' + _DOCUMENT_OPENING + r'SPDX-License-Identifier:\s*([^\n]+?)(?:\s*-->)?$', re.IGNORECASE | re.MULTILINE),
            re.compile(r'^' + _DOCUMENT_OPENING + r'License-Expression:\s*([^\n]+)', re.IGNORECASE | re.MULTILINE),
            re.compile(r'^' + _DOCUMENT_OPENING + r'License:\s*([A-Za-z0-9\-\.]+)', re.IGNORECASE | re.MULTILINE),
            re.compile(r'^' + _DOCUMENT_OPENING + r'@license\s+([^\n]+)', re.IGNORECASE | re.MULTILINE),
            re.compile(r'^' + _DOCUMENT_OPENING + r'(?-i:Licensed)\s+under\s+(?:the\s+)?' + _LICENCE_NAME + r'(?:\s+[Ll]icense)?(?:\.\s|[,\n;]|$)', re.IGNORECASE | re.MULTILINE),
            re.compile(r'^' + _DOCUMENT_OPENING + _SELF_REFERRING + r'[Ll]icensed\s+under\s+(?:the\s+)?' + _LICENCE_NAME + r'(?:\s+[Ll]icense)?(?:\.\s|[,\n;]|$)', re.IGNORECASE | re.MULTILINE),
        ]

    def _compile_prose_patterns(self) -> List[re.Pattern]:
        """Patterns that match a licence named inside a sentence.

        Kept apart from the ones above because they are a different kind of
        claim. "SPDX-License-Identifier: Apache-2.0" is a file declaring its
        licence. "the bundled minifier is licensed under the Apache License"
        is a file mentioning someone else's, and the two were reported
        identically: same method, same confidence, same category. A consumer
        that wanted to trust declarations had to refuse both.

        What separates them is where the phrase sits. Apache's own boilerplate
        opens a line: "Licensed under the Apache License, Version 2.0 (the
        "License")", and it opens one in the licence text itself and in every
        source header that carries it. A credit has the thing being credited
        in front of it. So a line that begins with the phrase, after nothing
        but indentation or a comment marker, is still read as a declaration,
        and only a phrase with words before it is read as a reference.

        Words, not merely something: requiring any non-space character in
        front counted the asterisk of a Java comment, so the Apache header
        that opens " * Licensed under the Apache License" was read as a
        reference to one. It has to be a letter or a digit.
        """
        return [
            # ... is licensed under <license>, with something in front of it.
            re.compile(r'[A-Za-z0-9][^\n]*?[Ll]icensed\s+under\s+(?:the\s+)?' + _LICENCE_NAME + r'(?:\s+[Ll]icense)?(?:\.\s|[,\n;]|$)', re.IGNORECASE),
        ]
    
    def detect_licenses(self, path: Path) -> List[DetectedLicense]:
        """
        Detect licenses in a directory or file.
        
        Args:
            path: Directory or file path to scan
            
        Returns:
            List of detected licenses
        """
        licenses = []
        processed_licenses = set()
        
        # Track if this is a single file scan (user passed a file directly)
        single_file_mode = path.is_file()
        
        if single_file_mode:
            files_to_scan = [path]
        else:
            # Find potential license files
            files_to_scan = self._find_license_files(path)

            # In default mode (license_files_only=True, strict_license_files=False),
            # also scan metadata and README files
            if self.config.license_files_only and not self.config.strict_license_files:
                files_to_scan.extend(self._find_metadata_and_readme_files(path))
            elif not self.config.license_files_only:
                # Deep scan mode: scan all source files for embedded licenses
                files_to_scan.extend(self._find_source_files(path))
        
        logger.info(f"Scanning {len(files_to_scan)} files for licenses")
        
        # What each file yielded, kept against the file rather than merged
        # as it arrives. Threads finish in whatever order they finish in, and
        # reading the results in that order decided the order of the
        # evidence, so the same scan of the same directory listed it
        # differently every run (issue #122, the sibling of #110).
        found_in = {
            file_path: results
            for file_path, results in self._detect_from_each(
                files_to_scan, single_file_mode
            )
        }

        # Read them back in the order the files were chosen. One body for
        # both ways of reading them, because there were two and they had to
        # agree: what a licence is, whether it may be emitted and when it is
        # a repeat were each written out twice.
        for file_path in files_to_scan:
            for license in found_in.get(file_path, []):
                # Emit modern SPDX ids; the bare GNU-family forms
                # osslili's detectors produce are deprecated.
                license.spdx_id = self._to_modern_spdx_id(license.spdx_id)
                # Never emit identifiers outside the SPDX list.
                if not self._is_emittable_license_id(license.spdx_id):
                    logger.debug(
                        f"Dropping non-SPDX license id '{license.spdx_id}' "
                        f"from {license.source_file}"
                    )
                    continue
                # Deduplicate by license ID, confidence, and source file
                key = (license.spdx_id, round(license.confidence, 2), license.source_file)
                if key not in processed_licenses:
                    processed_licenses.add(key)
                    licenses.append(license)

        # Re-tag bundled third-party notices (issue #78). Several construction
        # paths hard-code the DECLARED category; normalize here at the single
        # exit point so any license sourced from a third-party notice file is
        # reported under the THIRD_PARTY category regardless of how it was built.
        for license in licenses:
            if license.source_file and self._is_third_party_notice_file(Path(license.source_file)):
                license.category = LicenseCategory.THIRD_PARTY.value

        # Sort by confidence
        licenses.sort(key=lambda x: x.confidence, reverse=True)

        return licenses

    def _detect_from_each(self, files_to_scan: List[Path], single_file_mode: bool):
        """Every file paired with what it yielded, in no particular order.

        The caller puts them back in order. Threads are used only to read the
        files, not to decide what the answer looks like.
        """
        max_workers = min(
            self.config.thread_count if hasattr(self.config, 'thread_count') else 4,
            len(files_to_scan),
        )

        if max_workers > 1 and len(files_to_scan) > 1:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_file = {
                    executor.submit(
                        self._detect_licenses_in_file_safe, file_path, single_file_mode
                    ): file_path
                    for file_path in files_to_scan
                }

                for future in as_completed(future_to_file):
                    file_path = future_to_file[future]
                    try:
                        # 30 second timeout per file
                        yield file_path, future.result(timeout=30)
                    except Exception as e:
                        logger.warning(f"Error processing {file_path}: {e}")
        else:
            for file_path in files_to_scan:
                try:
                    yield file_path, self._detect_licenses_in_file(
                        file_path, single_file_mode
                    )
                except Exception as e:
                    logger.warning(f"Error processing {file_path}: {e}")

    def _detect_licenses_in_file_safe(self, file_path: Path, single_file_mode: bool = False) -> List[DetectedLicense]:
        """Thread-safe wrapper for file license detection."""
        try:
            return self._detect_licenses_in_file(file_path, single_file_mode)
        except Exception as e:
            logger.debug(f"Error in file {file_path}: {e}")
            return []
    
    def _find_license_files(self, directory: Path) -> List[Path]:
        """Find potential license files in directory."""
        license_files_set = set()  # Use set for O(1) lookup
        scanner = SafeFileScanner(
            max_depth=self.config.max_recursion_depth,
            follow_symlinks=False
        )

        # Single pass: check both pattern matching and fuzzy matching
        for file_path in scanner.scan_directory(directory, '*'):
            # Check direct pattern matching
            for pattern in self.license_patterns:
                if pattern.match(file_path.name):
                    license_files_set.add(file_path)
                    break  # No need to check other patterns for this file

            # If not already added, check fuzzy match
            if file_path not in license_files_set:
                name_lower = file_path.name.lower()
                for base_name in self.config.license_fuzzy_base_names:
                    ratio = fuzz.partial_ratio(base_name, name_lower)
                    if ratio >= 85:  # 85% similarity threshold
                        license_files_set.add(file_path)
                        break

        # Sorted, because a set is iterated in whatever order it likes and
        # that order differs between processes, so two scans of one
        # directory chose the files in a different order.
        return sorted(license_files_set)

    def _find_metadata_and_readme_files(self, directory: Path) -> List[Path]:
        """Find README, package metadata, and other readable documentation files (.txt, .md, .rst, etc.)."""
        metadata_files_set = set()  # Use set for O(1) lookup and automatic deduplication
        scanner = SafeFileScanner(
            max_depth=self.config.max_recursion_depth,
            follow_symlinks=False
        )

        # Readable documentation file extensions
        doc_extensions = {'.txt', '.md', '.rst', '.text', '.markdown', '.adoc', '.asciidoc'}

        # Package metadata files (pre-compute lowercase set for exact matches)
        # Covers top 15+ package ecosystems
        metadata_filenames_exact = {
            # JavaScript/Node.js (npm, yarn, pnpm)
            'package.json', 'package-lock.json', 'yarn.lock', 'pnpm-lock.yaml',
            # Python
            'pyproject.toml', 'setup.py', 'setup.cfg', 'pipfile', 'pipfile.lock', 'requirements.txt',
            # Go
            'go.mod', 'go.sum',
            # Java (Maven, Gradle)
            'pom.xml', 'build.gradle', 'build.gradle.kts', 'settings.gradle', 'manifest.mf',
            # .NET/NuGet
            'packages.config', 'paket.dependencies',
            # Rust
            'cargo.toml', 'cargo.lock',
            # Ruby
            'gemfile', 'gemfile.lock',
            # PHP/Composer
            'composer.json', 'composer.lock',
            # Swift/CocoaPods
            'podfile', 'podfile.lock',
            # Dart/Flutter
            'pubspec.yaml', 'pubspec.lock',
            # Elixir
            'mix.exs', 'mix.lock',
            # Scala
            'build.sbt',
            # Kotlin
            'build.gradle.kts',
        }

        # Pattern-based metadata extensions
        metadata_extensions = {
            '.gemspec',   # Ruby
            '.nuspec',    # NuGet
            '.csproj',    # .NET C#
            '.fsproj',    # .NET F#
            '.vbproj',    # .NET VB
            '.podspec',   # CocoaPods
        }

        for file_path in scanner.scan_directory(directory, '*'):
            name_lower = file_path.name.lower()
            ext_lower = file_path.suffix.lower()

            # Check for readable documentation files by extension
            if ext_lower in doc_extensions:
                metadata_files_set.add(file_path)
            # Check metadata files by exact name
            elif name_lower in metadata_filenames_exact:
                metadata_files_set.add(file_path)
            # Check pattern-based metadata files by extension
            elif ext_lower in metadata_extensions:
                metadata_files_set.add(file_path)

        return sorted(metadata_files_set)
    
    def _find_source_files(self, directory: Path, limit: int = -1) -> List[Path]:
        """Find all readable files to scan for embedded licenses."""
        source_files = []
        count = 0
        
        # Extensions to skip (binary files, archives, etc.)
        skip_extensions = {
            '.pyc', '.pyo', '.pyd', '.so', '.dll', '.dylib', '.exe',
            '.bin', '.dat', '.db', '.sqlite', '.sqlite3',
            '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.ico', '.svg',
            '.mp3', '.mp4', '.avi', '.mov', '.wav', '.flac',
            '.zip', '.tar', '.gz', '.bz2', '.xz', '.7z', '.rar',
            '.whl', '.egg', '.gem', '.jar', '.war', '.ear',
            '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
            '.ttf', '.otf', '.woff', '.woff2', '.eot',
            '.class', '.o', '.a', '.lib', '.obj'
        }
        
        scanner = SafeFileScanner(
            max_depth=self.config.max_recursion_depth,
            follow_symlinks=False
        )
        
        # Scan all files recursively, in a settled order: a directory walk
        # returns what the filesystem gives it and two machines need not
        # agree.
        for file_path in sorted(scanner.scan_directory(directory, '*')):
            # Skip binary/archive files
            if file_path.suffix.lower() in skip_extensions:
                continue
            
            # Try to determine if file is text/readable
            if self._is_readable_file(file_path):
                source_files.append(file_path)
                count += 1
                if limit > 0 and count >= limit:
                    return source_files
        
        return source_files
    
    def _read_file_smart(self, file_path: Path) -> str:
        """
        Read large files intelligently by sampling beginning and end.
        License info is usually in the first few KB or at the end.
        """
        try:
            # Performance optimization: Skip smart reading if flag is set
            if self.config.skip_smart_read:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    return f.read()

            with open(file_path, 'rb') as f:
                # Read first 100KB
                beginning = f.read(100 * 1024)

                # Seek to end and read last 50KB
                f.seek(0, 2)  # Seek to end
                file_size = f.tell()
                if file_size > 150 * 1024:
                    f.seek(-50 * 1024, 2)  # Seek to 50KB before end
                    ending = f.read()
                else:
                    ending = b''

                # Combine and decode
                combined = beginning + b'\n...\n' + ending if ending else beginning

                # Try to decode
                try:
                    return combined.decode('utf-8', errors='ignore')
                except UnicodeDecodeError:
                    return combined.decode('latin-1', errors='ignore')
        except Exception as e:
            logger.debug(f"Error reading large file {file_path}: {e}")
            return ""
    
    def _is_readable_file(self, file_path: Path) -> bool:
        """Check if a file is likely readable text - MODIFIED for better coverage."""
        try:
            # Performance optimization: Check file size limit first
            if self.config.max_file_size_kb is not None:
                try:
                    file_size_kb = file_path.stat().st_size / 1024
                    if file_size_kb > self.config.max_file_size_kb:
                        return False
                except:
                    pass

            # Skip test reference files (these are test outputs, not source)
            path_str = str(file_path).lower()
            if '/tests/ref/' in path_str or '/test/ref/' in path_str:
                return False

            # Get file extension
            ext = file_path.suffix.lower()

            # Performance optimization: Skip files without extensions if flag is set
            if self.config.skip_extensionless and not ext:
                # Still allow known patterns like LICENSE, README, Makefile
                name_lower = file_path.name.lower()
                known_text_files = [
                    'makefile', 'dockerfile', 'readme', 'license',
                    'copying', 'notice', 'changelog', 'authors'
                ]
                if not any(pattern in name_lower for pattern in known_text_files):
                    return False

            # Always include common source code extensions
            source_extensions = {
                '.c', '.h', '.cpp', '.cxx', '.hpp', '.cc', '.hh',
                '.java', '.py', '.js', '.ts', '.go', '.rs', '.rb',
                '.php', '.pl', '.pm', '.sh', '.bash', '.zsh',
                '.s', '.asm', '.cl', '.cu', '.comp', '.vert', '.frag',
                '.m', '.mm', '.swift', '.kt', '.scala', '.clj',
                '.hs', '.ml', '.fs', '.vb', '.cs', '.v', '.sv',
                '.txt', '.md', '.rst', '.tex', '.texi', '.yml', '.yaml',
                '.json', '.xml', '.html', '.css', '.scss', '.less',
                '.makefile', '.mak', '.mk', '.cmake', '.ninja',
                '.dockerfile', '.gitignore', '.editorconfig',
                '.rc', '.cfg', '.conf', '.ini', '.properties'
            }

            # Files without extensions (often makefiles, scripts, configs)
            if not ext:
                # Check filename patterns for known file types
                name_lower = file_path.name.lower()

                # Common known text files
                known_text_files = [
                    'makefile', 'dockerfile', 'readme', 'license',
                    'copying', 'notice', 'changelog', 'authors',
                    'contributors', 'maintainers', 'install',
                    'credits', 'thanks', 'history', 'news', 'releases',
                    'version', 'manifest', 'codeowners', 'security',
                    'contributing', 'code_of_conduct', 'funding',
                    'citation', 'coauthors', 'release_notes', 'release'
                ]

                if any(pattern in name_lower for pattern in known_text_files):
                    return True

                # Performance optimization: Skip content-based detection if flag is set
                if self.config.skip_content_detection:
                    return False

                # For other files without extensions, check if they're text
                # by reading a small portion and checking content
                # This will catch files like 'configure', 'bootstrap', etc.
                try:
                    with open(file_path, 'rb') as f:
                        chunk = f.read(512)  # Just check first 512 bytes
                        if not chunk:
                            return True  # Empty files are readable

                        # Quick check for binary content
                        null_count = chunk.count(b'\x00')
                        if null_count > len(chunk) * 0.05:  # More than 5% null bytes
                            return False

                        # Try to decode as text
                        try:
                            chunk.decode('utf-8')
                            return True
                        except UnicodeDecodeError:
                            # Check if mostly printable ASCII
                            printable = sum(1 for b in chunk if 32 <= b <= 126 or b in [9, 10, 13])
                            if printable >= len(chunk) * 0.75:  # 75% printable
                                return True
                except:
                    pass

                # Default to false for files without extensions that don't pass checks
                return False

            # If it's a known source extension, assume readable
            if ext in source_extensions:
                return True

            # For other files, do the content check but be more permissive
            # Try to read first 2KB instead of 1KB for better detection
            with open(file_path, 'rb') as f:
                chunk = f.read(2048)
                if not chunk:
                    return True  # Empty files are "readable"

                # Check for high density of null bytes (binary indicator)
                # Allow some null bytes for files that might have embedded nulls
                null_count = chunk.count(b'\x00')
                if null_count > len(chunk) * 0.1:  # More than 10% null bytes
                    return False

                # Check for other binary indicators
                # Look for common binary file magic numbers in first 16 bytes
                if len(chunk) >= 16:
                    magic_start = chunk[:16]
                    binary_signatures = [
                        b'\x7fELF',      # ELF executable
                        b'MZ',           # PE executable
                        b'\x89PNG',      # PNG image
                        b'\xff\xd8\xff', # JPEG image
                        b'GIF8',         # GIF image
                        b'\x00\x00\x01\x00', # ICO file
                        b'PK\x03\x04',   # ZIP archive
                        b'\x1f\x8b',     # GZIP
                        b'BZh',          # BZIP2
                    ]
                    if any(magic_start.startswith(sig) for sig in binary_signatures):
                        return False

                # Try to decode - be more permissive with encoding errors
                try:
                    # First try UTF-8
                    chunk.decode('utf-8')
                    return True
                except UnicodeDecodeError:
                    # Try with more encodings and be permissive with errors
                    for encoding in ['latin-1', 'cp1252', 'iso-8859-1', 'utf-16', 'ascii']:
                        try:
                            chunk.decode(encoding, errors='ignore')
                            # If we can decode at least 80% without errors, consider it text
                            try:
                                decoded = chunk.decode(encoding, errors='strict')
                                return True
                            except UnicodeDecodeError:
                                # Check if we can decode most of it
                                decoded_ignore = chunk.decode(encoding, errors='ignore')
                                if len(decoded_ignore) >= len(chunk) * 0.8:
                                    return True
                        except (UnicodeDecodeError, LookupError):
                            continue

                    # Last resort: if it looks like text (printable chars), allow it
                    printable_count = sum(1 for b in chunk if 32 <= b <= 126 or b in [9, 10, 13])
                    if printable_count >= len(chunk) * 0.7:  # 70% printable chars
                        return True

                    return False
        except (OSError, IOError):
            return False
    
    def _detect_licenses_in_file(self, file_path: Path, single_file_mode: bool = False) -> List[DetectedLicense]:
        """Detect licenses in a single file."""
        licenses = []
        
        # Read file content - for large files, read in chunks
        file_size = file_path.stat().st_size if file_path.exists() else 0
        
        # For very large files (>10MB), only read the beginning and end
        if file_size > 10 * 1024 * 1024:  # 10MB
            content = self._read_file_smart(file_path)
        else:
            # For smaller files, read the whole thing
            content = self.input_processor.read_text_file(file_path, max_size=file_size if file_size > 0 else 10*1024*1024)
        
        if not content:
            return licenses
        
        # Method 0: Extract from package metadata files first (highest priority)
        metadata_licenses = self._extract_package_metadata(content, file_path)
        licenses.extend(metadata_licenses)

        # Method 1: Detect SPDX tags
        tag_licenses = self._detect_spdx_tags(content, file_path)
        licenses.extend(tag_licenses)

        # Method 2: Detect license keywords (base licenses) with enhanced patterns
        keyword_licenses = self._detect_license_keywords(content, file_path)
        licenses.extend(keyword_licenses)

        # Method 3: Apply full three-tier detection
        # For single file mode or dedicated license files, use full content
        if single_file_mode or self._is_license_file(file_path):
            detected = self._detect_license_from_text(content, file_path)
            if detected:
                licenses.append(detected)
        # For regular files, if they contain license indicators, try both:
        # - License block extraction (for embedded licenses)
        # - Regex detection on full content (for scattered references)
        elif self._contains_license_text(content):
            # Try extracting a license block first
            license_block = self._extract_license_block(content)
            if license_block:
                detected = self._detect_license_from_text(license_block, file_path)
                if detected:
                    licenses.append(detected)

            # Also try regex patterns on the full content
            # This catches references that aren't in a clear block
            regex_detected = self._tier3_regex_matching(content, file_path)
            if regex_detected:
                licenses.append(regex_detected)
        # For all other files, still apply regex detection
        # This ensures we catch any license references
        else:
            regex_detected = self._tier3_regex_matching(content, file_path)
            if regex_detected:
                licenses.append(regex_detected)

        # Apply false positive filtering to all detected licenses
        filtered_licenses = []
        for license in licenses:
            if self._is_valid_license_id(license.spdx_id):
                filtered_licenses.append(license)
            else:
                logger.debug(f"Filtered out false positive license: '{license.spdx_id}' from {file_path}")

        return filtered_licenses
    
    # A bundled *third-party* notice/license file (licenses of dependencies
    # shipped alongside the project) is identified by a "third party" marker
    # combined with a notice/license token. Requiring both avoids misclassifying
    # ordinary source files such as ``third_party_helpers.py`` as license files.
    # These files are still detected and reported, but tagged with the
    # THIRD_PARTY category so consumers determining the project's own license in
    # isolation (e.g. ORT) can filter them out. See issue #78.
    _THIRD_PARTY_MARKERS = (
        'third-party', 'third_party', 'thirdparty',
        '3rdparty', '3rd-party', '3rd_party',
    )
    _THIRD_PARTY_NOTICE_TOKENS = (
        'notice', 'license', 'licence', 'legal', 'attribution',
    )

    def _is_third_party_notice_file(self, file_path: Path) -> bool:
        """Check if a file is a bundled third-party notice/license file."""
        name_lower = file_path.name.lower()
        has_marker = any(m in name_lower for m in self._THIRD_PARTY_MARKERS)
        has_token = any(t in name_lower for t in self._THIRD_PARTY_NOTICE_TOKENS)
        return has_marker and has_token

    def _is_license_file(self, file_path: Path) -> bool:
        """Check if file is likely a license file."""
        name_lower = file_path.name.lower()
        
        # Check patterns
        for pattern in self.license_patterns:
            if pattern.match(file_path.name):
                return True
        
        # Check common names
        license_names = ['license', 'licence', 'copying', 'copyright', 'notice', 'legal',
                        'gpl', 'copyleft', 'eula', 'commercial', 'agreement', 'bundle',
                        'third-party', 'third_party']
        for name in license_names:
            if name in name_lower:
                return True
        
        return False
    
    def _contains_license_text(self, content: str) -> bool:
        """Check if content contains license-related text."""
        content_lower = content.lower()

        # Check for license indicators
        indicator_count = sum(1 for indicator in self.license_indicators
                             if indicator in content_lower)

        return indicator_count >= 1  # At least 1 indicator (reduced from 3 for better coverage)
    
    def _extract_license_block(self, content: str) -> Optional[str]:
        """Extract license block from content."""
        lines = content.split('\n')
        
        # Look for license header/block
        license_start = -1
        license_end = -1
        
        for i, line in enumerate(lines):
            line_lower = line.lower()
            
            # Look for start markers
            if license_start == -1:
                if any(marker in line_lower for marker in 
                      ['license', 'copyright', 'permission is hereby granted']):
                    license_start = i
            
            # Look for end markers (empty line after substantial content)
            elif license_start != -1 and i > license_start + 5:
                if not line.strip() or i == len(lines) - 1:
                    license_end = i
                    break
        
        if license_start != -1 and license_end != -1:
            return '\n'.join(lines[license_start:license_end])
        
        # Fallback: return first 50 lines if they contain license indicators
        first_lines = '\n'.join(lines[:50])
        if self._contains_license_text(first_lines):
            return first_lines
        
        return None
    
    def _extract_package_metadata(self, content: str, file_path: Path) -> List[DetectedLicense]:
        """
        Extract license information from package metadata files.
        Supports: pom.xml, *.nuspec, *.gemspec, Cargo.toml, setup.cfg, setup.py, package.json, composer.json

        Also extracts SPDX tags from source headers in metadata files.
        """
        licenses = []
        file_name = file_path.name.lower()
        seen_licenses = {}  # Track licenses by (spdx_id, match_type) to avoid duplicates

        # First, check for SPDX tags in the header/comments of the metadata file
        header_licenses = self._extract_header_licenses(content, file_path)
        for license in header_licenses:
            key = (license.spdx_id, license.match_type)
            if key not in seen_licenses:
                licenses.append(license)
                seen_licenses[key] = license

        # Then extract from structured metadata
        metadata_licenses = []

        # Check if file matches metadata patterns (handles temp files with suffixes)
        # pom.xml (Maven)
        if file_name.endswith('pom.xml') or file_name == 'pom.xml':
            metadata_licenses.extend(self._extract_from_pom_xml(content, file_path))

        # *.nuspec (NuGet)
        elif file_name.endswith('.nuspec'):
            metadata_licenses.extend(self._extract_from_nuspec(content, file_path))

        # *.gemspec (Ruby)
        elif file_name.endswith('.gemspec'):
            metadata_licenses.extend(self._extract_from_gemspec(content, file_path))

        # Cargo.toml (Rust)
        elif file_name.endswith('cargo.toml') or file_name == 'cargo.toml':
            metadata_licenses.extend(self._extract_from_cargo_toml(content, file_path))

        # setup.cfg (Python)
        elif file_name.endswith('setup.cfg') or file_name == 'setup.cfg':
            metadata_licenses.extend(self._extract_from_setup_cfg(content, file_path))

        # setup.py (Python)
        elif file_name.endswith('setup.py') or file_name == 'setup.py':
            metadata_licenses.extend(self._extract_from_setup_py(content, file_path))

        # package.json (Node.js)
        elif file_name.endswith('package.json') or file_name == 'package.json':
            metadata_licenses.extend(self._extract_from_package_json(content, file_path))

        # composer.json (PHP)
        elif file_name.endswith('composer.json') or file_name == 'composer.json':
            metadata_licenses.extend(self._extract_from_composer_json(content, file_path))

        # pyproject.toml (Python)
        elif file_name.endswith('pyproject.toml') or file_name == 'pyproject.toml':
            metadata_licenses.extend(self._extract_from_pyproject_toml(content, file_path))

        # Add metadata licenses, but skip if the same license was already found in header
        for license in metadata_licenses:
            # If same SPDX ID was found in header, prefer the metadata version
            # as it's more authoritative
            header_key = (license.spdx_id, "header_tag")
            if header_key in seen_licenses:
                # Replace header version with metadata version
                idx = licenses.index(seen_licenses[header_key])
                licenses[idx] = license
                seen_licenses[(license.spdx_id, license.match_type)] = license
                del seen_licenses[header_key]
            else:
                key = (license.spdx_id, license.match_type)
                if key not in seen_licenses:
                    licenses.append(license)
                    seen_licenses[key] = license

        return licenses

    def _extract_header_licenses(self, content: str, file_path: Path) -> List[DetectedLicense]:
        """
        Extract license information from the header/comments of a metadata file.
        This includes SPDX tags and license references in comments.
        """
        licenses = []

        # Only check first 30 lines for header licenses
        lines = content.splitlines()[:30]
        header_content = '\n'.join(lines)

        # Extract SPDX tags from comments.
        #
        # Both anchored to the start of a line, allowing for a comment marker
        # or indentation. "License:" was matched after any space, so it fired
        # mid-sentence: "it bundles terser, license: BSD-2-Clause, for
        # minification" was reported as the file declaring BSD-2-Clause, at
        # confidence 1.0. A credits section near the top of a short README is
        # exactly where that sits.
        # A document has no comment syntax, so an asterisk opening a line is
        # a bullet: "* Licensed under the MIT License" under a Dependencies
        # heading is a credit rather than a header.
        opening = (
            _DOCUMENT_OPENING if self._reads_as_a_document(file_path)
            else _COMMENT_OPENING
        )
        # The rest of the line, not the first word of it. SPDX defines an
        # expression here, and stopping at the first space reported
        # "MIT OR Apache-2.0" as MIT, dropping a choice the licensor
        # offered, and "GPL-2.0-only WITH Classpath-exception-2.0" as
        # GPL-2.0-only, dropping the exception that form exists for.
        spdx_patterns = [
            r'^' + opening + r'SPDX-License-Identifier:\s*([^\n]+)',
            r'^' + opening + r'License:\s*([^\n]+)',
        ]

        for pattern in spdx_patterns:
            holds_an_expression = _holds_an_expression(pattern)
            matches = re.finditer(pattern, header_content, re.IGNORECASE | re.MULTILINE)
            for match in matches:
                expression = match.group(1).strip()
                # The expression, and not whatever follows it on the line:
                # a closing comment marker, or a note like "(see LICENSE)".
                expression = _expression_at_the_front(
                    expression, self._names_a_licence, holds_an_expression,
                )

                for license_id in self._parse_license_expression(expression):

                    normalized_id = self._normalize_license_id(license_id)
                    license_info = self.spdx_data.get_license_info(normalized_id)

                    if license_info:
                        licenses.append(DetectedLicense(
                            spdx_id=license_info['licenseId'],
                            name=license_info.get('name', normalized_id),
                            confidence=1.0,
                            detection_method=DetectionMethod.TAG.value,
                            source_file=str(file_path),
                            category=LicenseCategory.DECLARED.value,
                            match_type="header_tag"
                        ))

        return licenses

    def _extract_from_pom_xml(self, content: str, file_path: Path) -> List[DetectedLicense]:
        """Extract licenses from Maven pom.xml files."""
        licenses = []

        try:
            root = ET.fromstring(content)

            # Maven uses namespace, need to handle it
            # Extract namespace from root tag if present
            namespace = ''
            if root.tag.startswith('{'):
                namespace = root.tag[1:root.tag.index('}')]

            # Try without namespace first
            license_elements = root.findall('.//license')

            # Try with namespace if no results
            if not license_elements and namespace:
                namespaces = {'m': namespace}
                license_elements = root.findall('.//m:license', namespaces)

            for license_elem in license_elements:
                # Try to find name element with and without namespace
                name_elem = license_elem.find('name')
                if name_elem is None and namespace:
                    name_elem = license_elem.find(f'{{{namespace}}}name')

                if name_elem is not None and name_elem.text:
                    license_name = name_elem.text.strip()
                    normalized_id = self._normalize_license_id(license_name)

                    license_info = self.spdx_data.get_license_info(normalized_id)

                    licenses.append(DetectedLicense(
                        spdx_id=license_info['licenseId'] if license_info else normalized_id,
                        name=license_info.get('name', normalized_id) if license_info else license_name,
                        confidence=1.0,
                        detection_method=DetectionMethod.TAG.value,
                        source_file=str(file_path),
                        category=LicenseCategory.DECLARED.value,
                        match_type="package_metadata"
                    ))
        except ET.ParseError as e:
            logger.debug(f"Failed to parse pom.xml {file_path}: {e}")

        return licenses

    def _extract_from_nuspec(self, content: str, file_path: Path) -> List[DetectedLicense]:
        """Extract licenses from NuGet .nuspec files."""
        licenses = []

        try:
            root = ET.fromstring(content)

            # NuGet uses namespace
            namespaces = {'nuget': 'http://schemas.microsoft.com/packaging/2010/07/nuspec.xsd',
                         'nuget2': 'http://schemas.microsoft.com/packaging/2011/08/nuspec.xsd',
                         'nuget3': 'http://schemas.microsoft.com/packaging/2012/06/nuspec.xsd',
                         'nuget4': 'http://schemas.microsoft.com/packaging/2013/05/nuspec.xsd'}

            # Try different namespace versions and also without namespace
            license_elem = None
            for ns_prefix, ns_uri in namespaces.items():
                license_elem = root.find(f'.//{{{ns_uri}}}license')
                if license_elem is not None:
                    break

            # Try without namespace
            if license_elem is None:
                license_elem = root.find('.//license')

            if license_elem is not None and license_elem.text:
                license_text = license_elem.text.strip()
                normalized_id = self._normalize_license_id(license_text)

                license_info = self.spdx_data.get_license_info(normalized_id)

                licenses.append(DetectedLicense(
                    spdx_id=license_info['licenseId'] if license_info else normalized_id,
                    name=license_info.get('name', normalized_id) if license_info else license_text,
                    confidence=1.0,
                    detection_method=DetectionMethod.TAG.value,
                    source_file=str(file_path),
                    category=LicenseCategory.DECLARED.value,
                    match_type="package_metadata"
                ))
        except ET.ParseError as e:
            logger.debug(f"Failed to parse .nuspec {file_path}: {e}")

        return licenses

    def _extract_from_gemspec(self, content: str, file_path: Path) -> List[DetectedLicense]:
        """Extract licenses from Ruby .gemspec files."""
        licenses = []
        found_licenses = set()  # Track already found licenses to avoid duplicates

        # Gemspec uses Ruby syntax, so we use regex patterns
        # Pattern: spec.license = "MIT" or spec.licenses = ["MIT", "Apache-2.0"]
        patterns = [
            r'(?:s|spec|gem)\.licenses?\s*=\s*\[([^\]]+)\]',  # Array format
            r'(?:s|spec|gem)\.licenses?\s*=\s*["\']([^"\']+)["\']',  # Single string format
        ]

        for pattern in patterns:
            matches = re.finditer(pattern, content, re.IGNORECASE)
            for match in matches:
                license_text = match.group(1)

                # Handle array format: ["MIT", "Apache-2.0"]
                if ',' in license_text or '"' in license_text or "'" in license_text:
                    # Extract individual license strings
                    license_items = re.findall(r'["\']([^"\']+)["\']', license_text)
                    if not license_items:
                        license_items = [item.strip() for item in license_text.split(',')]
                else:
                    license_items = [license_text]

                for license_item in license_items:
                    license_item = license_item.strip()
                    if not license_item:
                        continue

                    normalized_id = self._normalize_license_id(license_item)

                    # Skip if already found this license
                    if normalized_id in found_licenses:
                        continue
                    found_licenses.add(normalized_id)

                    license_info = self.spdx_data.get_license_info(normalized_id)

                    licenses.append(DetectedLicense(
                        spdx_id=license_info['licenseId'] if license_info else normalized_id,
                        name=license_info.get('name', normalized_id) if license_info else license_item,
                        confidence=1.0,
                        detection_method=DetectionMethod.TAG.value,
                        source_file=str(file_path),
                        category=LicenseCategory.DECLARED.value,
                        match_type="package_metadata"
                    ))

        return licenses

    def _extract_from_cargo_toml(self, content: str, file_path: Path) -> List[DetectedLicense]:
        """Extract licenses from Rust Cargo.toml files."""
        licenses = []
        found_licenses = set()  # Track already found licenses to avoid duplicates

        # Cargo.toml format: license = "MIT OR Apache-2.0"
        # Pattern to match license field in [package] section
        pattern = r'^\s*license\s*=\s*["\']([^"\']+)["\']'

        matches = re.finditer(pattern, content, re.IGNORECASE | re.MULTILINE)
        for match in matches:
            license_expr = match.group(1).strip()

            # Parse license expression (may contain OR, AND)
            license_ids = self._parse_license_expression(license_expr)

            for license_id in license_ids:
                normalized_id = self._normalize_license_id(license_id)

                # Skip if already found this license
                if normalized_id in found_licenses:
                    continue
                found_licenses.add(normalized_id)

                license_info = self.spdx_data.get_license_info(normalized_id)

                licenses.append(DetectedLicense(
                    spdx_id=license_info['licenseId'] if license_info else normalized_id,
                    name=license_info.get('name', normalized_id) if license_info else license_id,
                    confidence=1.0,
                    detection_method=DetectionMethod.TAG.value,
                    source_file=str(file_path),
                    category=LicenseCategory.DECLARED.value,
                    match_type="package_metadata"
                ))

        return licenses

    def _extract_from_setup_cfg(self, content: str, file_path: Path) -> List[DetectedLicense]:
        """Extract licenses from Python setup.cfg files."""
        licenses = []

        # setup.cfg format:
        # [metadata]
        # license = MIT
        # Or classifiers with License :: OSI Approved :: MIT License

        # Simple license field
        license_pattern = r'^\s*license\s*=\s*(.+)$'
        matches = re.finditer(license_pattern, content, re.IGNORECASE | re.MULTILINE)
        for match in matches:
            license_text = match.group(1).strip()
            normalized_id = self._normalize_license_id(license_text)
            license_info = self.spdx_data.get_license_info(normalized_id)

            licenses.append(DetectedLicense(
                spdx_id=license_info['licenseId'] if license_info else normalized_id,
                name=license_info.get('name', normalized_id) if license_info else license_text,
                confidence=1.0,
                detection_method=DetectionMethod.TAG.value,
                source_file=str(file_path),
                category=LicenseCategory.DECLARED.value,
                match_type="package_metadata"
            ))

        # License classifiers
        licenses.extend(self._extract_python_classifiers(content, file_path))

        return licenses

    def _extract_from_setup_py(self, content: str, file_path: Path) -> List[DetectedLicense]:
        """Extract licenses from Python setup.py files."""
        licenses = []

        # setup.py format: license="MIT" or license='MIT'
        license_pattern = r'license\s*=\s*["\']([^"\']+)["\']'
        matches = re.finditer(license_pattern, content, re.IGNORECASE)
        for match in matches:
            license_text = match.group(1).strip()
            normalized_id = self._normalize_license_id(license_text)
            license_info = self.spdx_data.get_license_info(normalized_id)

            licenses.append(DetectedLicense(
                spdx_id=license_info['licenseId'] if license_info else normalized_id,
                name=license_info.get('name', normalized_id) if license_info else license_text,
                confidence=1.0,
                detection_method=DetectionMethod.TAG.value,
                source_file=str(file_path),
                category=LicenseCategory.DECLARED.value,
                match_type="package_metadata"
            ))

        # License classifiers
        licenses.extend(self._extract_python_classifiers(content, file_path))

        return licenses

    def _extract_python_classifiers(self, content: str, file_path: Path) -> List[DetectedLicense]:
        """Extract license from Python trove classifiers."""
        licenses = []

        # Patterns for both quoted (setup.py) and unquoted (setup.cfg) classifiers
        classifier_patterns = [
            r'["\']License\s*::\s*OSI Approved\s*::\s*([^"\']+)["\']',  # Quoted
            r'^\s*License\s*::\s*OSI Approved\s*::\s*(.+?)$'  # Unquoted (on its own line)
        ]

        for pattern in classifier_patterns:
            matches = re.finditer(pattern, content, re.IGNORECASE | re.MULTILINE)

            for match in matches:
                license_name = match.group(1).strip()
                # Remove " License" suffix if present
                license_name = re.sub(r'\s+License$', '', license_name, flags=re.IGNORECASE)

                normalized_id = self._normalize_license_id(license_name)
                license_info = self.spdx_data.get_license_info(normalized_id)

                licenses.append(DetectedLicense(
                    spdx_id=license_info['licenseId'] if license_info else normalized_id,
                    name=license_info.get('name', normalized_id) if license_info else license_name,
                    confidence=1.0,
                    detection_method=DetectionMethod.TAG.value,
                    source_file=str(file_path),
                    category=LicenseCategory.DECLARED.value,
                    match_type="package_metadata_classifier"
                ))

        return licenses

    def _extract_from_package_json(self, content: str, file_path: Path) -> List[DetectedLicense]:
        """Extract licenses from Node.js package.json files."""
        licenses = []

        try:
            import json
            data = json.loads(content)

            # Check for license field
            if 'license' in data:
                license_value = data['license']
                # Handle SPDX expression or plain string
                if isinstance(license_value, str):
                    license_ids = self._parse_license_expression(license_value)
                    for license_id in license_ids:
                        normalized_id = self._normalize_license_id(license_id)
                        license_info = self.spdx_data.get_license_info(normalized_id)

                        licenses.append(DetectedLicense(
                            spdx_id=license_info['licenseId'] if license_info else normalized_id,
                            name=license_info.get('name', normalized_id) if license_info else license_id,
                            confidence=1.0,
                            detection_method=DetectionMethod.TAG.value,
                            source_file=str(file_path),
                            category=LicenseCategory.DECLARED.value,
                            match_type="package_metadata"
                        ))

            # Also check licenses field (array)
            if 'licenses' in data:
                licenses_array = data['licenses']
                if isinstance(licenses_array, list):
                    for license_obj in licenses_array:
                        if isinstance(license_obj, dict) and 'type' in license_obj:
                            license_id = license_obj['type']
                        elif isinstance(license_obj, str):
                            license_id = license_obj
                        else:
                            continue

                        normalized_id = self._normalize_license_id(license_id)
                        license_info = self.spdx_data.get_license_info(normalized_id)

                        licenses.append(DetectedLicense(
                            spdx_id=license_info['licenseId'] if license_info else normalized_id,
                            name=license_info.get('name', normalized_id) if license_info else license_id,
                            confidence=1.0,
                            detection_method=DetectionMethod.TAG.value,
                            source_file=str(file_path),
                            category=LicenseCategory.DECLARED.value,
                            match_type="package_metadata"
                        ))
        except (json.JSONDecodeError, KeyError) as e:
            logger.debug(f"Failed to parse package.json {file_path}: {e}")

        return licenses

    def _extract_from_composer_json(self, content: str, file_path: Path) -> List[DetectedLicense]:
        """Extract licenses from PHP composer.json files."""
        licenses = []

        try:
            import json
            # Remove single-line comments (// ...) which are not valid JSON but common in composer.json
            lines = content.splitlines()
            cleaned_lines = []
            for line in lines:
                # Remove // style comments
                comment_pos = line.find('//')
                if comment_pos >= 0:
                    # Check if // is not inside a string
                    before_comment = line[:comment_pos]
                    quote_count = before_comment.count('"') - before_comment.count('\\"')
                    if quote_count % 2 == 0:  # Even number of quotes, so // is outside strings
                        line = line[:comment_pos]
                cleaned_lines.append(line)
            cleaned_content = '\n'.join(cleaned_lines)

            data = json.loads(cleaned_content)

            # Check for license field (can be string or array)
            if 'license' in data:
                license_value = data['license']
                if isinstance(license_value, str):
                    # Single license
                    license_ids = self._parse_license_expression(license_value)
                elif isinstance(license_value, list):
                    # Array of licenses
                    license_ids = []
                    for lic in license_value:
                        if isinstance(lic, str):
                            license_ids.extend(self._parse_license_expression(lic))
                else:
                    license_ids = []

                for license_id in license_ids:
                    normalized_id = self._normalize_license_id(license_id)
                    license_info = self.spdx_data.get_license_info(normalized_id)

                    licenses.append(DetectedLicense(
                        spdx_id=license_info['licenseId'] if license_info else normalized_id,
                        name=license_info.get('name', normalized_id) if license_info else license_id,
                        confidence=1.0,
                        detection_method=DetectionMethod.TAG.value,
                        source_file=str(file_path),
                        category=LicenseCategory.DECLARED.value,
                        match_type="package_metadata"
                    ))
        except (json.JSONDecodeError, KeyError) as e:
            logger.debug(f"Failed to parse composer.json {file_path}: {e}")

        return licenses

    def _categorize_tag(self, file_path: Path, is_prose: bool):
        """How to file a tag match, given which pattern found it.

        A licence named inside a sentence is a reference to one, which is
        what the referenced category is for. Reporting it as declared said
        the file states that licence, and a package whose README credits a
        dependency was read as carrying the dependency's licence.

        Except inside a licence file, where there is no one else to be
        referring to. A pointer-style LICENSE reading "FooBar is licensed
        under the MIT License. See ... for the full text." is that package
        stating its licence, and calling it a reference left the file with no
        declaration at all.
        """
        if is_prose and not self._is_license_file(file_path):
            return LicenseCategory.REFERENCED.value, "prose_reference"
        return self._categorize_license(file_path, DetectionMethod.TAG.value)

    def _detect_spdx_tags(self, content: str, file_path: Path) -> List[DetectedLicense]:
        """Detect SPDX license identifiers in content."""
        licenses = []
        found_ids = set()
        
        # Skip files that are likely to contain false positives
        file_name = file_path.name.lower()
        # Only skip our own detector/data files to avoid self-detection
        if any(name in file_name for name in ['spdx_licenses.py', 'license_detector.py']):
            return licenses
        
        in_a_document = self._reads_as_a_document(file_path)
        tag_patterns = (
            self.document_tag_patterns if in_a_document else self.spdx_tag_patterns
        )
        # Which patterns read to the end of a line, and so may pick up
        # whatever follows the expression on it. Said outright rather than
        # guessed from the anchor: the TOML form is anchored too, and its
        # capture is a quoted value, so trimming it took "The MIT License"
        # down to "The".
        for pattern, is_prose, reads_a_line, holds_an_expression in (
            [(p, False, _reads_a_line(p), _holds_an_expression(p))
             for p in tag_patterns]
            + [(p, True, False, False) for p in self.prose_patterns]
        ):
            matches = pattern.findall(content)
            
            for match in matches:
                # Clean up the match
                license_id = match.strip()

                # A pattern that reads to the end of a line reads whatever
                # else is on it: a closing comment marker, or a note such as
                # "(see LICENSE)". Handed whole to the parser that became
                # "BSD-2-Clause see LICENSE", which the normaliser read as
                # plain BSD and answered BSD-3-Clause.
                if reads_a_line:
                    license_id = _expression_at_the_front(
                        license_id, self._names_a_licence, holds_an_expression,
                    )

                # Skip obvious false positives
                if self._is_false_positive_license(license_id):
                    continue
                
                # Handle license expressions (AND, OR, WITH)
                license_ids = self._parse_license_expression(license_id)
                
                for lid in license_ids:
                    if lid not in found_ids:
                        found_ids.add(lid)

                        # Skip SPDX exceptions (they modify licenses, not standalone)
                        # Common exceptions end with "-exception" or are known exception IDs
                        if 'exception' in lid.lower() and not lid.startswith('Font-exception'):
                            continue

                        # Normalize license ID
                        normalized_id = self._normalize_license_id(lid)

                        # Get license info
                        license_info = self.spdx_data.get_license_info(normalized_id)

                        if license_info:
                            category, match_type = self._categorize_tag(
                                file_path, is_prose
                            )
                            licenses.append(DetectedLicense(
                                spdx_id=license_info['licenseId'],
                                name=license_info.get('name', normalized_id),
                                confidence=1.0,  # High confidence for explicit tags
                                detection_method=DetectionMethod.TAG.value,
                                source_file=str(file_path),
                                category=category,
                                match_type=match_type
                            ))
                        else:
                            # Only record unknown licenses if they look valid
                            if self._looks_like_valid_license(normalized_id):
                                category, match_type = self._categorize_tag(
                                    file_path, is_prose
                                )
                                licenses.append(DetectedLicense(
                                    spdx_id=normalized_id,
                                    name=normalized_id,
                                    confidence=0.9,
                                    detection_method=DetectionMethod.TAG.value,
                                    source_file=str(file_path),
                                    category=category,
                                    match_type=match_type
                                ))
        
        return licenses
    
    def _detect_license_keywords(self, content: str, file_path: Path) -> List[DetectedLicense]:
        """
        Detect license keywords for common base licenses.
        This handles variations like "GPL" for GPL/LGPL/AGPL, "BSD" for any BSD variant.
        Enhanced with fuzzy matching and multi-line pattern support.
        """
        from typing import Optional
        import re
        licenses = []

        # Base license families with common variations
        base_license_mapping = {
            # GPL family
            'GPL-3.0': ['GPL-3', 'GPL3', 'GPLv3', 'GPL version 3', 'GNU General Public License v3',
                        'GNU General Public License version 3', 'GPL v3'],
            'GPL-2.0': ['GPL-2', 'GPL2', 'GPLv2', 'GPL version 2', 'GNU General Public License v2',
                        'GNU General Public License version 2', 'GPL v2', 'GNU GPL v2',
                        'terms-of-the-GNU-GPL', 'GNU-GPL-v2'],  # Add normalization patterns
            'GPL': ['GPL', 'the GPL', 'GNU GPL', 'General Public License'],  # Generic GPL
            'LGPL-3.0': ['LGPL-3', 'LGPLv3', 'Lesser GPL v3', 'GNU Lesser General Public License v3',
                         'GNU Lesser General Public License version 3', 'LGPL v3'],
            'LGPL-2.1': ['LGPL-2.1', 'LGPLv2.1', 'Lesser GPL v2.1', 'GNU Lesser General Public License v2.1',
                         'GNU Lesser General Public License version 2.1', 'LGPL v2.1'],
            'AGPL-3.0': ['AGPL-3', 'AGPLv3', 'Affero GPL v3', 'GNU Affero General Public License v3'],

            # BSD family
            'BSD-3-Clause': ['BSD-3-Clause', 'BSD 3-Clause', '3-clause BSD', 'New BSD', 'Modified BSD'],
            'BSD-2-Clause': ['BSD-2-Clause', 'BSD 2-Clause', '2-clause BSD', 'Simplified BSD', 'FreeBSD'],

            # Apache - Enhanced with multi-line patterns
            'Apache-2.0': ['Apache-2.0', 'Apache 2.0', 'Apache License 2.0', 'Apache License, Version 2.0', 'ALv2',
                          'Apache License Version 2.0'],  # Added for multi-line
            'Apache-1.1': ['Apache-1.1', 'Apache 1.1', 'Apache License 1.1'],

            # MIT
            'MIT': ['MIT', 'MIT License', 'X11', 'Expat', 'under MIT', 'MIT license',
                    'the MIT License', 'MIT/X11', 'MIT-style'],

            # Mozilla
            'MPL-2.0': ['MPL-2.0', 'MPL 2.0', 'Mozilla Public License 2.0'],
            'MPL-1.1': ['MPL-1.1', 'MPL 1.1', 'Mozilla Public License 1.1'],

            # Creative Commons
            'CC0-1.0': ['CC0', 'CC0-1.0', 'Creative Commons Zero', 'Public Domain'],
            'CC-BY-4.0': ['CC-BY-4.0', 'CC BY 4.0', 'Creative Commons Attribution 4.0'],
            'CC-BY-SA-4.0': ['CC-BY-SA-4.0', 'CC BY-SA 4.0', 'Creative Commons Attribution-ShareAlike 4.0'],

            # Others
            'ISC': ['ISC License', 'Internet Systems Consortium License'],
            'Artistic-2.0': ['Artistic-2.0', 'Artistic License 2.0'],
            'Unlicense': ['Unlicense', 'The Unlicense'],
            # Additional patterns from license database - FIXED to be more specific
            'Python-2.0': ['Python Software Foundation License', 'PSF License', 'Python License 2.0',
                           'the Python Software Foundation License', 'PYTHON SOFTWARE FOUNDATION LICENSE'],
            'PHP-3.0': ['PHP License 3.0', 'PHP-3.0', 'The PHP License, version 3.0'],
            'PHP-3.01': ['PHP License 3.01', 'PHP-3.01', 'The PHP License, version 3.01'],
            'Ruby': ['Ruby License', 'RUBY LICENSE'],
            'Perl': ['Perl Artistic License', 'Artistic License (Perl)', 'Perl License'],
            'Zlib': ['zlib', 'Zlib', 'ZLIB License'],
            'OpenSSL': ['OpenSSL', 'OpenSSL License', 'OpenSSL/SSLeay'],
            'JSON': ['JSON', 'JSON License', 'The JSON License'],
            '0BSD': ['0BSD', 'BSD Zero Clause', 'BSD-0-Clause', 'Free Public License'],
            'PostgreSQL': ['PostgreSQL', 'PostgreSQL License', 'PGSQL'],
            'WTFPL': ['WTFPL', 'Do What The F*ck You Want To Public License'],
            'Vim': ['Vim', 'Vim License', 'VIM'],
            'Beerware': ['Beerware', 'Beer-ware', 'THE BEER-WARE LICENSE'],

            # Additional license patterns for better coverage
            'GPL-1.0': ['GPL-1', 'GPLv1', 'GPL version 1', 'GNU General Public License v1',
                        'GNU General Public License version 1', 'GPL v1'],
            'BSD-3-Clause-Clear': ['BSD-3-Clause-Clear', 'BSD 3-Clause Clear License',
                                  'Clear BSD License', 'BSD Clear'],
            'BSD-Source-Code': ['BSD-Source-Code', 'BSD Source Code Attribution'],
            'BSL-1.0': ['BSL-1.0', 'Boost Software License', 'Boost Software License 1.0',
                        'BSL', 'Boost License'],
            'IJG': ['IJG', 'Independent JPEG Group', 'JPEG License', 'libjpeg'],
        }

        # Helper method for version suffixes
        def handle_version_suffix(base_license: str, context: str) -> str:
            """
            Handle version suffixes like +, -or-later, -only.
            Only applies to GNU family licenses that support these suffixes per SPDX spec.
            """
            # Only GNU family licenses support -only/-or-later suffixes in SPDX
            gnu_licenses = {
                'GPL-1.0', 'GPL-2.0', 'GPL-3.0',
                'LGPL-2.0', 'LGPL-2.1', 'LGPL-3.0',
                'AGPL-1.0', 'AGPL-3.0',
                'GFDL-1.1', 'GFDL-1.2', 'GFDL-1.3',
                'GFDL-1.1-invariants', 'GFDL-1.1-no-invariants',
                'GFDL-1.2-invariants', 'GFDL-1.2-no-invariants',
                'GFDL-1.3-invariants', 'GFDL-1.3-no-invariants',
            }

            # Only apply suffixes to licenses that support them
            if base_license not in gnu_licenses:
                return base_license

            # Check for + suffix or "or later" text
            if '+' in context or 'or later' in context.lower() or 'or-later' in context.lower():
                if not base_license.endswith('-or-later') and not base_license.endswith('-only'):
                    return base_license + '-or-later'
            # Check for "only" suffix
            elif 'only' in context.lower() and not 'or later' in context.lower():
                if not base_license.endswith('-only') and not base_license.endswith('-or-later'):
                    return base_license + '-only'
            return base_license

        # Helper method for fuzzy patterns
        def create_fuzzy_pattern(text: str) -> Optional[str]:
            """
            Create a fuzzy regex pattern that allows for common typos.
            """
            if len(text) < 3:
                return None

            # Common typo patterns
            typo_replacements = {
                'license': r'licen[sc]e',  # License/Lisense
                'general': r'gen[ae]ral',  # General/Genaral
                'public': r'publ[il]c',    # Public/Publlc
            }

            pattern = re.escape(text)
            for correct, fuzzy in typo_replacements.items():
                pattern = pattern.replace(correct, fuzzy, 1)  # Replace once
                pattern = pattern.replace(correct.capitalize(), fuzzy, 1)

            return pattern if pattern != re.escape(text) else None

        # Multi-line regex patterns for complex license headers
        multi_line_patterns = {
            'Apache-2.0': [
                r'Apache\s+License\s*[\r\n]+\s*Version\s+2\.0',  # Apache License\nVersion 2.0
                r'Licensed\s+under\s+the\s+Apache\s+License[,]?\s+Version\s+2\.0',
            ],
            'GPL-3.0': [
                r'GNU\s+GENERAL\s+PUBLIC\s+LICENSE\s*[\r\n]+\s*Version\s+3',
                r'GPL\s+version\s+3',
            ],
            'GPL-2.0': [
                r'GNU\s+GENERAL\s+PUBLIC\s+LICENSE\s*[\r\n]+\s*Version\s+2',
                r'GPL\s+version\s+2',
            ],
            'MIT': [
                r'MIT\s+Licen[sc]e',  # Handles typos like "Lisense"
                r'Permission\s+is\s+hereby\s+granted[,]?\s+free\s+of\s+charge',
            ],
        }

        # Contextual patterns that suggest license mentions
        context_patterns = [
            r'[Ll]icensed?\s+under\s+(?:the\s+)?',
            r'(?:distributed|released|available)\s+under\s+(?:the\s+)?',
            r'(?:uses?|using)\s+(?:the\s+)?',
            r'(?:dual|tri)\s+licensed?:?\s*',
            r'under\s+(?:the\s+)?',  # Simple "under X license"
            r'(?:copyright|©).*under\s+',  # Copyright under X
            r'\bsoftware\s+under\s+',  # Software under X
            r'\bcode\s+under\s+',  # Code under X
            r'subject\s+to\s+(?:the\s+)?',
            r'terms\s+of\s+(?:the\s+)?',
            r'This\s+(?:program|software|project)\s+is\s+',
        ]

        found_licenses = set()  # Track found licenses to avoid duplicates

        # First, try multi-line regex patterns for complex license headers
        for spdx_id, patterns in multi_line_patterns.items():
            for pattern in patterns:
                if re.search(pattern, content, re.IGNORECASE | re.MULTILINE | re.DOTALL):
                    if spdx_id not in found_licenses:
                        found_licenses.add(spdx_id)
                        # Handle version suffixes
                        final_spdx_id = handle_version_suffix(spdx_id, content)
                        licenses.append(DetectedLicense(
                            spdx_id=final_spdx_id,
                            name=final_spdx_id,
                            confidence=0.90,  # Higher confidence for regex patterns
                            detection_method=DetectionMethod.KEYWORD.value,
                            source_file=str(file_path),
                            category='detected',
                            match_type='keyword'
                        ))
                    break

        # Then check standard keyword patterns
        for spdx_id, variations in base_license_mapping.items():
            if spdx_id in found_licenses:
                continue

            # Check exact matches first
            for variation in variations:
                if variation.lower() not in content.lower():
                    continue

                pattern_re = re.compile(_bounded_pattern(variation), re.IGNORECASE)

                # Walk every occurrence rather than only the first. A license
                # file may mention a license in passing (compatibility notes,
                # history) well before it states the terms it actually grants,
                # so rejecting an occurrence has to mean "keep looking", not
                # "give up on this variation".
                for match in itertools.islice(pattern_re.finditer(content), _MAX_KEYWORD_OCCURRENCES):
                    # Check if it appears in a license context
                    start = max(0, match.start() - 100)
                    end = min(len(content), match.end() + 50)
                    context = content[start:end]

                    # Skip mentions that discuss a license rather than grant it
                    paragraph = _paragraph_around(content, match.start(), match.end())
                    if _LICENSE_DISCUSSION_RE.search(paragraph):
                        logger.debug(
                            f"Skipping '{variation}' in {file_path}: mention is "
                            f"discussion, not a grant"
                        )
                        continue

                    # A linking exception carves out the library it names, but is
                    # itself granted over a copyleft license — so it never
                    # disqualifies a GNU-family match in the same paragraph.
                    if (not spdx_id.startswith(_GNU_FAMILY_PREFIXES)
                            and _LINKING_EXCEPTION_RE.search(paragraph)):
                        logger.debug(
                            f"Skipping '{variation}' in {file_path}: named by a "
                            f"linking exception, not granted"
                        )
                        continue

                    has_context = any(re.search(pattern, context, re.IGNORECASE) for pattern in context_patterns)

                    # Check for comment or line start (more strict)
                    line_start = False
                    if match.start() > 0:
                        # Look at the entire line leading up to the match
                        line_start_pos = content.rfind('\n', 0, match.start())
                        if line_start_pos == -1:
                            line_start_pos = 0
                        else:
                            line_start_pos += 1
                        line_prefix = content[line_start_pos:match.start()].strip()

                        # Check if line starts with comment markers or license-related keywords
                        comment_markers = ['#', '//', '/*', '*', '--', '%', ';']
                        license_keywords = ['license', 'copyright', '©', 'spdx', 'distributed under', 'licensed under']

                        line_start = (
                            any(line_prefix.startswith(marker) for marker in comment_markers) or
                            any(keyword in line_prefix.lower() for keyword in license_keywords) or
                            line_prefix == ''
                        )
                    else:
                        line_start = True

                    # Only match if we have strong license context or it's in a clear license statement
                    if not (has_context and line_start):
                        continue

                    # Handle version suffixes and normalization
                    final_spdx_id = handle_version_suffix(spdx_id, content[match.start():match.end()+20])

                    # Resolve a generic "GPL" / "General Public License" mention
                    # to a versioned id. Without an explicit version the mention
                    # names a license family, not a license: GPL-2.0-only and
                    # GPL-3.0-only are mutually incompatible, so guessing one
                    # invents an obligation. Report nothing instead.
                    if final_spdx_id == 'GPL':
                        # "Lesser"/"Affero General Public License" have their own
                        # identifiers; the generic path must not claim them.
                        preceding = content[max(0, match.start() - 16):match.start()]
                        if _GNU_VARIANT_PREFIX_RE.search(preceding):
                            continue

                        # Wide enough to reach the version in the FSF header,
                        # where it trails the license name by a clause.
                        context_text = content[
                            max(0, match.start() - 120):min(len(content), match.end() + 180)
                        ]
                        version_match = _GNU_VERSION_RE.search(context_text)
                        if not version_match:
                            logger.debug(
                                f"Skipping unversioned GPL mention in {file_path}: "
                                f"no explicit version to resolve it to"
                            )
                            continue
                        version = next(g for g in version_match.groups() if g)
                        final_spdx_id = f'GPL-{version}.0'

                        # "or (at your option) any later version" makes the grant
                        # an -or-later one; without it the version stands alone.
                        if _GNU_OR_LATER_RE.search(context_text):
                            final_spdx_id += '-or-later'

                    licenses.append(DetectedLicense(
                        spdx_id=final_spdx_id,
                        name=final_spdx_id,
                        confidence=0.85,
                        detection_method=DetectionMethod.KEYWORD.value,
                        source_file=str(file_path),
                        category='detected',
                        match_type='keyword'
                    ))
                    found_licenses.add(spdx_id)
                    break

                if spdx_id in found_licenses:
                    break

            # If no exact match, try fuzzy matching for common typos
            if spdx_id not in found_licenses and spdx_id in ['MIT', 'Apache-2.0', 'GPL-2.0', 'GPL-3.0']:
                for variation in variations:
                    # Use fuzzy matching for common typos
                    fuzzy_pattern = create_fuzzy_pattern(variation)
                    if fuzzy_pattern and re.search(fuzzy_pattern, content, re.IGNORECASE):
                        licenses.append(DetectedLicense(
                            spdx_id=spdx_id,
                            name=spdx_id,
                            confidence=0.75,  # Lower confidence for fuzzy matches
                            detection_method=DetectionMethod.KEYWORD.value,
                            source_file=str(file_path),
                            category='detected',
                            match_type='keyword_fuzzy'
                        ))
                        found_licenses.add(spdx_id)
                        break

        return licenses


    def _extract_from_pyproject_toml(self, content: str, file_path: Path) -> List[DetectedLicense]:
        """Extract licenses from Python pyproject.toml files."""
        licenses = []
        import re

        # First check for license = {file = "LICENSE"} format (PEP 639)
        file_pattern = re.compile(r'license\s*=\s*\{[^}]*file\s*=\s*"([^"]+)"', re.IGNORECASE)
        file_match = file_pattern.search(content)

        if file_match:
            # Extract the license file path
            license_file_name = file_match.group(1).strip()
            license_file_path = file_path.parent / license_file_name

            # Try to read and detect license from the referenced file
            if not _is_contained_by(license_file_path, file_path.parent):
                logger.debug(
                    f"Ignoring license file {license_file_name!r} referenced in "
                    f"{file_path}: resolves outside the project directory"
                )
            elif license_file_path.exists():
                license_content = None
                try:
                    license_content = self.input_processor.read_text_file(license_file_path)
                except Exception as e:
                    logger.debug(f"Failed to read license file {license_file_path}: {e}")

                if license_content:
                    # Identify the referenced text through the full tier cascade.
                    # This returns at most one license, not a list.
                    detected = self._detect_license_from_text(license_content, license_file_path)
                    if detected:
                        # Report it against pyproject.toml, which is what declares it
                        detected.source_file = str(file_path)
                        detected.match_type = "package_metadata_file"
                        detected.category = LicenseCategory.DECLARED.value
                        licenses.append(detected)
                    else:
                        logger.debug(
                            f"No license identified in {license_file_path} referenced by "
                            f"{file_path}"
                        )
            else:
                logger.debug(f"License file {license_file_path} referenced in pyproject.toml does not exist")

        # Patterns for other pyproject.toml license formats
        patterns = [
            # Pattern for license = "LICENSE_ID"
            (re.compile(r'^\s*license\s*=\s*"([^"]+)"', re.MULTILINE), 'simple'),
            # Pattern for license = {text = "LICENSE_ID"}
            (re.compile(r'license\s*=\s*\{[^}]*text\s*=\s*"([^"]+)"', re.IGNORECASE), 'dict'),
        ]

        for pattern, format_type in patterns:
            for match in pattern.finditer(content):
                license_id = match.group(1).strip()
                license_ids = self._parse_license_expression(license_id)

                for lid in license_ids:
                    normalized_id = self._normalize_license_id(lid)
                    license_info = self.spdx_data.get_license_info(normalized_id)

                    licenses.append(DetectedLicense(
                        spdx_id=license_info['licenseId'] if license_info else normalized_id,
                        name=license_info.get('name', normalized_id) if license_info else lid,
                        confidence=1.0,
                        detection_method=DetectionMethod.TAG.value,
                        source_file=str(file_path),
                        category=LicenseCategory.DECLARED.value,
                        match_type="package_metadata"
                    ))

                # Only process first match of each format to avoid duplicates
                break

        return licenses

    def _normalize_license_id(self, license_id: str) -> str:
        """
        Normalize license ID to match SPDX format.
        Delegates to external LicenseNormalizer for maintainability.
        """
        return self.license_normalizer.normalize_license_id(license_id, self.spdx_data)
    
    def _is_valid_spdx_id(self, license_id: str) -> bool:
        """Check if a license ID exists in SPDX data."""
        return license_id in self._known_spdx_ids()

    def _known_spdx_ids(self):
        """Every identifier the SPDX list holds, or nothing if it has none."""
        if hasattr(self.spdx_data, 'licenses') and self.spdx_data.licenses:
            return self.spdx_data.licenses
        return ()

    def _names_a_licence(self, term: str) -> bool:
        """Whether this term of an expression is a licence.

        Asking the SPDX list alone was too strict, because the deprecated
        forms this detector resolves itself are not in it: "GFDL-1.3+" is a
        licence, and calling it a word refused the expression around it, so
        "GFDL-1.3+ or MIT" lost the MIT.

        A reference to a licence held elsewhere, "LicenseRef-x" or
        "DocumentRef-x:LicenseRef-y", names one too. Nothing can be looked up
        about it, which is the point of the form.
        """
        if not term:
            return False
        if 'LicenseRef-' in term:
            return True
        if self._is_valid_spdx_id(term) or self._is_valid_spdx_id(
            self._to_modern_spdx_id(term)
        ):
            return True
        # The tag itself is matched without regard to case, and the licence
        # named in it may be written the way its authors write it: the SPDX
        # id is CECILL-2.1 and the licence is called CeCILL. Asking the list
        # case-sensitively refused the expression around such a term, so
        # "EUPL-1.2 or CeCILL-2.1" lost the CeCILL.
        folded = term.casefold()
        return any(
            known.casefold() == folded for known in self._known_spdx_ids()
        )

    def _to_modern_spdx_id(self, license_id: str) -> str:
        """Map a deprecated bare GNU-family id to its modern SPDX replacement.

        ``GPL-2.0`` -> ``GPL-2.0-only`` and the deprecated "or later" form
        ``GPL-2.0+`` -> ``GPL-2.0-or-later``, matching SPDX's documented
        replacements. Ids that are already modern, are not GNU-family, or whose
        computed replacement is not itself a valid SPDX id are returned
        unchanged, so an unexpected input can never produce a bogus id.
        """
        if not license_id or not isinstance(license_id, str):
            return license_id
        lid = license_id.strip()

        # Deprecated "or later" form: GPL-2.0+ -> GPL-2.0-or-later.
        if lid.endswith('+'):
            base = lid[:-1]
            if _DEPRECATED_GNU_RE.match(base):
                candidate = base + '-or-later'
                if self._is_valid_spdx_id(candidate):
                    return candidate
            # SPDX replaced the form for the GNU family and nowhere else, so
            # "MIT+" names no licence and was emitted verbatim as though it
            # did. The plus is what does not resolve, not the identifier
            # under it, and dropping the whole thing left a file whose only
            # licence statement is that line with no licence at all.
            if self._is_valid_spdx_id(base):
                return base
            return lid

        # Bare deprecated form: GPL-2.0 -> GPL-2.0-only.
        if _DEPRECATED_GNU_RE.match(lid):
            candidate = lid + '-only'
            if self._is_valid_spdx_id(candidate):
                return candidate
        return lid

    def _is_emittable_license_id(self, license_id: str) -> bool:
        """
        Whether a detected identifier may be emitted in results.

        A detection must resolve to a real SPDX license id, an SPDX license
        expression, an SPDX exception, or an explicit marker. Strings that
        merely *look* license-like but are not valid SPDX identifiers (e.g.
        "MIT-or-later", which is not a real id) are rejected so they never
        reach an SBOM or notice file.
        """
        if not license_id or not isinstance(license_id, str):
            return False

        lid = license_id.strip()
        if not lid:
            return False

        # Explicit non-SPDX markers we intentionally allow through.
        if lid == 'NOASSERTION':
            return True
        if lid.startswith('LicenseRef-'):
            return True

        # SPDX license exceptions are tracked separately from the license list.
        if 'exception' in lid.lower():
            return True

        # SPDX expressions (compound) — every operand must itself be emittable.
        if re.search(r'\s+(?:AND|OR|WITH)\s+', lid, re.IGNORECASE):
            operands = [
                op.strip()
                for op in re.split(r'\s+(?:AND|OR|WITH)\s+', lid, flags=re.IGNORECASE)
                if op.strip()
            ]
            return bool(operands) and all(self._is_emittable_license_id(op) for op in operands)

        # Bare identifier: must exist in the SPDX license list. A trailing "+"
        # (deprecated "or later" form, e.g. "GPL-2.0+") is tolerated.
        return self._is_valid_spdx_id(lid.rstrip('+'))


    def _extract_version(self, text: str) -> Optional[str]:
        """Extract version number from license text."""
        # Match patterns like 2.0, 3, 3.0, etc.
        match = re.search(r'(\d+(?:\.\d+)?)', text)
        if match:
            return match.group(1)
        return None
    
    def _normalize_cc_license(self, license_text: str) -> str:
        """Normalize Creative Commons license identifiers."""
        # Handle CC0 first
        if 'CC0' in license_text.upper() or ('CC' in license_text.upper() and 'ZERO' in license_text.upper()):
            return 'CC0-1.0'
        
        # Extract CC components
        
        # Common CC license pattern: CC-BY-SA-4.0
        cc_match = re.search(r'CC[- ]?(BY|ZERO)?[- ]?(SA|NC|ND)?[- ]?(\d+\.\d+)?', license_text.upper())
        if cc_match:
            parts = ['CC']
            if cc_match.group(1) and cc_match.group(1) != 'ZERO':
                parts.append(cc_match.group(1))
            if cc_match.group(2):
                parts.append(cc_match.group(2))
            if cc_match.group(3):
                parts.append(cc_match.group(3))
            return '-'.join(parts)
        
        return license_text
    
    def _parse_license_expression(self, expression: str) -> List[str]:
        """Parse SPDX license expression including complex formats."""
        # Don't split if it contains "or later" or "or-later" (common suffix)
        expression_lower = expression.lower()
        if 'or later' in expression_lower or 'or-later' in expression_lower:
            # Check if this is really a suffix or an OR expression
            # GPL-2.0-or-later is a suffix, but "MIT OR Apache" is an expression
            #
            # An AND or a WITH makes it an expression too, whatever the
            # suffix. Returning "GPL-2.0-or-later WITH Classpath-exception-2.0"
            # whole left the normaliser to read it, and it reduced the lot to
            # the base word gpl and answered GPL-2.0, which the emission
            # boundary then modernised to GPL-2.0-only: the opposite of what
            # the file grants.
            joined = re.search(r'\s+(?:OR(?!\s+later)|AND|WITH)\s+', expression,
                               re.IGNORECASE)
            if not joined:
                return [expression.strip()]

        # Collect all licenses found in the expression
        licenses = []

        # First handle WITH exceptions specially (keep them together)
        # e.g., "GPL-3.0 WITH Classpath-exception-2.0"
        # The operand may carry the deprecated "+" form, GPL-2.0+, which is
        # handled everywhere else. Leaving it out took the plus off and
        # reported GPL-2.0, modernised later to GPL-2.0-only: the opposite of
        # what the file grants.
        with_pattern = r'([A-Za-z0-9\-\.+]+)\s+WITH\s+([A-Za-z0-9\-\.]+)'
        with_matches = re.findall(with_pattern, expression, re.IGNORECASE)

        # Keep track of what we've processed
        processed = set()

        for base_license, exception in with_matches:
            # Add both the base license and the exception
            licenses.append(base_license.strip())
            licenses.append(exception.strip())
            processed.add(f"{base_license} WITH {exception}")

        # Replace WITH expressions with placeholder to avoid re-processing
        temp_expression = expression
        for match in re.finditer(with_pattern, expression, re.IGNORECASE):
            temp_expression = temp_expression.replace(match.group(), '__WITH__')

        # Remove parentheses but keep track of the structure
        # For now, just flatten everything
        temp_expression = temp_expression.replace('(', '').replace(')', '')

        # Split on AND/OR operators, and on the comma that stands in for one.
        # A comma was handled only where the expression had no operator at
        # all, so a list that mixed the two lost a term: "MIT, Apache-2.0 OR
        # BSD-3-Clause" reported the two after the comma and not the one
        # before it.
        parts = re.split(r'\s*,\s*|\s+(?:AND|OR)\s+', temp_expression,
                         flags=re.IGNORECASE)

        for part in parts:
            part = part.strip()
            if part and part != '__WITH__' and part not in processed:
                # This might be a license ID
                licenses.append(part)

        # Remove duplicates while preserving order
        seen = set()
        result = []
        for lic in licenses:
            if lic not in seen:
                seen.add(lic)
                result.append(lic)

        return result if result else [expression.strip()]
    
    
    def _detect_license_from_text(self, text: str, file_path: Path) -> Optional[DetectedLicense]:
        """
        Detect license from text using four-tier detection.
        
        Args:
            text: License text
            file_path: Source file path
            
        Returns:
            Detected license or None
        """
        # Tier 0: Exact hash matching (SHA-256 and MD5)
        detected = self._tier0_exact_hash(text, file_path)
        if detected:
            return detected
        
        # Tier 1: Dice-Sørensen similarity. The tier applies its own acceptance
        # rule — a strong score outright, a weaker one only if TLSH corroborates
        # it — so anything it returns is accepted here. Re-gating on
        # similarity_threshold discarded every corroborated match below it,
        # which made the corroboration step dead code and silently lost
        # licenses whose text is bundled (protobuf scored 0.957 against
        # BSD-3-Clause and was reported as having no license at all).
        detected = self._tier1_dice_sorensen(text, file_path)
        if detected:
            return detected
        
        # Tier 2: TLSH fuzzy hashing. The detector applies its own bar — a
        # proposed near neighbour is only returned once the license's real text
        # corroborates it — so anything it returns is accepted here. Gating on
        # similarity_threshold instead would be a no-op, because TLSH used to
        # floor its confidence at exactly that value (issue #90).
        detected = self.tlsh_detector.detect_license_tlsh(text, file_path)
        if detected:
            return detected
        
        # Tier 3: Regex pattern matching. Reaching here means every tier that
        # actually compares text declined to identify this one, so a pattern hit
        # is a weak signal about an unrecognized document — not the confident
        # identification that a license file would otherwise be scored at.
        #
        # Left unbounded, this asserted the wrong license at full confidence for
        # any license whose text is not bundled: a Sleepycat file, which no tier
        # could match, was reported as BSD-3-Clause at 1.0 because the patterns
        # for the BSD clauses it shares fired. Copyleft reported as permissive,
        # with nothing in the output to suggest doubt.
        detected = self._tier3_regex_matching(text, file_path)
        if detected:
            if detected.confidence > _UNIDENTIFIED_TEXT_CONFIDENCE_CAP:
                logger.debug(
                    f"Capping regex confidence for {detected.spdx_id} in {file_path}: "
                    f"no text tier could identify this document"
                )
                detected.confidence = _UNIDENTIFIED_TEXT_CONFIDENCE_CAP
            return detected
        
        # No match found
        return None
    
    def _tier0_exact_hash(self, text: str, file_path: Path) -> Optional[DetectedLicense]:
        """
        Tier 0: Exact hash matching using SHA-256 and MD5.
        
        Args:
            text: License text
            file_path: Source file
            
        Returns:
            Detected license or None
        """
        # Compute SHA-256 hash of the input text
        sha256_hash = self.spdx_data.compute_text_hash(text, 'sha256')
        
        # Try to find exact match by SHA-256
        license_id = self.spdx_data.find_license_by_hash(sha256_hash, 'sha256')
        
        if not license_id:
            # Fall back to MD5 if SHA-256 doesn't match
            md5_hash = self.spdx_data.compute_text_hash(text, 'md5')
            license_id = self.spdx_data.find_license_by_hash(md5_hash, 'md5')
        
        if license_id:
            license_info = self.spdx_data.get_license_info(license_id)
            category, match_type = self._categorize_license(
                file_path, DetectionMethod.HASH.value
            )
            
            logger.debug(f"Exact hash match found for {license_id}")
            
            return DetectedLicense(
                spdx_id=license_id,
                name=license_info.get('name', license_id) if license_info else license_id,
                confidence=1.0,  # Exact match = 100% confidence
                detection_method=DetectionMethod.HASH.value,
                source_file=str(file_path),
                category=category,
                match_type="exact_hash"
            )
        
        return None
    
    def _tier1_dice_sorensen(self, text: str, file_path: Path) -> Optional[DetectedLicense]:
        """
        Tier 1: Dice-Sørensen similarity matching.
        
        Args:
            text: License text
            file_path: Source file
            
        Returns:
            Detected license or None
        """
        # Normalize text
        normalized_text = self.spdx_data._normalize_text(text)
        
        # Create bigrams for input text
        input_bigrams = self._create_bigrams(normalized_text)
        if not input_bigrams:
            return None
        
        # Keep track of all matches to handle ties
        matches = []
        
        # Compare with known licenses
        for license_id in self.spdx_data.get_all_license_ids():
            # Get license text
            license_text = self.spdx_data.get_license_text(license_id)
            if not license_text:
                continue
            
            # Normalize and create bigrams
            normalized_license = self.spdx_data._normalize_text(license_text)
            license_bigrams = self._create_bigrams(normalized_license)
            
            if not license_bigrams:
                continue
            
            # Calculate Dice-Sørensen coefficient
            score = self._dice_coefficient(input_bigrams, license_bigrams)
            
            if score >= 0.9:  # Only keep high-scoring matches
                matches.append((license_id, score))
        
        if not matches:
            return None
        
        # Sort by score descending
        matches.sort(key=lambda x: -x[1])
        best_score = matches[0][1]
        
        # Get all matches within 1% of best score
        close_matches = [(lid, score) for lid, score in matches if score >= best_score - 0.01]
        
        # Choose the best match, with special handling for known problematic pairs
        best_match = close_matches[0][0]
        
        # Special case: Prefer Apache-2.0 over Pixar when scores are close
        # Pixar is "Modified Apache 2.0 License", so Apache-2.0 is more likely correct
        license_ids = [m[0] for m in close_matches]
        if 'Apache-2.0' in license_ids and 'Pixar' in license_ids:
            # Find Apache-2.0 score
            for lid, score in close_matches:
                if lid == 'Apache-2.0':
                    best_match = 'Apache-2.0'
                    best_score = score
                    logger.debug(f"Preferring Apache-2.0 over Pixar (Dice-Sørensen scores within 1%)")
                    break
        
        if best_match and best_score >= _DICE_FLOOR:

            # At or above the configured similarity threshold the score speaks
            # for itself. Below it, down to the floor, the match must be
            # corroborated before it is accepted — which is what makes the band
            # between the two usable rather than simply discarded.
            #
            # Corroboration needs TLSH, which is an optional dependency that
            # needs a C toolchain, so a plain install usually does not have it.
            # Without it there is nothing to corroborate with, and accepting the
            # band anyway is how a Sleepycat license file came to be reported as
            # BSD-3-Clause at 0.91 — the two texts really are that similar, and
            # the clauses that differ are the whole point. So when no confirmer
            # is available the band is not opened at all.
            corroborated = (
                self.tlsh_detector.can_confirm
                and self.tlsh_detector.confirm_license_match(text, best_match)
            )
            if best_score >= self.config.similarity_threshold or corroborated:
                license_info = self.spdx_data.get_license_info(best_match)
                category, match_type = self._categorize_license(
                    file_path, DetectionMethod.DICE_SORENSEN.value
                )
                return DetectedLicense(
                    spdx_id=best_match,
                    name=license_info.get('name', best_match) if license_info else best_match,
                    confidence=best_score,
                    detection_method=DetectionMethod.DICE_SORENSEN.value,
                    source_file=str(file_path),
                    category=category,
                    match_type=match_type
                )
            else:
                logger.debug(f"Dice-Sørensen match {best_match} not confirmed by TLSH")
        
        return None
    
    def _create_bigrams(self, text: str) -> Set[str]:
        """Create character bigrams from text."""
        return create_bigrams(text)

    def _dice_coefficient(self, set1: Set[str], set2: Set[str]) -> float:
        """Calculate Dice-Sørensen coefficient between two sets."""
        return dice_coefficient(set1, set2)

    def _adjust_regex_confidence(self, raw_score: float, category: str, match_type: str, match_count: int) -> float:
        """
        Adjust confidence scores for regex-based license detection based on context.
        
        Args:
            raw_score: Raw pattern matching score (0.0-1.0)
            category: License category (declared/detected/referenced)
            match_type: Type of match (license_file, license_reference, etc.)
            match_count: Number of patterns that matched
            
        Returns:
            Adjusted confidence score
        """
        # Bundled third-party notice files are still license files, just
        # categorized separately (issue #78); they keep the same high
        # confidence treatment as declared license files.
        if category in ("declared", "third-party"):
            # License files and documentation should have high confidence
            if match_type in ("license_file", "third_party_notice"):
                return 1.0  # Full confidence for exact license file matches
            elif match_type == "documentation":
                return min(0.95, raw_score + 0.2)  # High confidence for docs
            elif match_type == "license_header":
                return min(0.9, raw_score + 0.2)  # High confidence for full headers
            else:
                return min(0.9, raw_score + 0.1)
        
        elif category == "referenced":
            # License references should have lower confidence
            if match_type == "license_reference":
                # Scale down references based on match strength
                if match_count == 1:
                    return 0.3  # Single pattern match = low confidence
                elif match_count == 2:
                    return 0.4  # Two patterns = medium-low confidence  
                else:
                    return 0.5  # Multiple patterns = medium confidence
            else:
                return min(0.6, raw_score)
        
        else:  # detected category
            return raw_score
    
    def _tier3_regex_matching(self, text: str, file_path: Path) -> Optional[DetectedLicense]:
        """
        Tier 3: Regex pattern matching using optimized lookup tables.

        Args:
            text: License text
            file_path: Source file

        Returns:
            Detected license or None
        """
        return self.regex_matcher.match_license_patterns(
            text, file_path, self._categorize_license, self._adjust_regex_confidence
        )
    
    def _is_false_positive_license(self, license_id: str) -> bool:
        """Check if a detected license ID is likely a false positive."""
        # Skip empty or too short
        if not license_id or len(license_id) < 2:
            return True

        # Skip if it's a valid SPDX expression with parentheses (not a false positive)
        if any(op in license_id.upper() for op in [' OR ', ' AND ', ' WITH ']):
            # This looks like a valid SPDX expression, not a false positive
            return False

        # A plus that ends an identifier is the deprecated or-later form,
        # GPL-2.0+, not a regex quantifier. Rejecting it outright left
        # "@license GPL-2.0+" with no licence at all once the reader stopped
        # truncating the line and the plus reached this check.
        if re.fullmatch(r'[A-Za-z0-9.\-]+\+', license_id):
            return False

        # Skip if contains regex patterns or code-like syntax
        # Note: Removed '(' and ')' as they're valid in SPDX expressions
        false_positive_patterns = [
            '\\', '{', '}', '[', ']',
            '<', '>', '?:', '^', '$', '*', '+',
            'var;', 'name=', 'original=', 'match=',
            '.{0', '\\n', '\\s', '\\d'
        ]
        
        for pattern in false_positive_patterns:
            if pattern in license_id:
                return True
        
        # Skip if it's a sentence or description (too long)
        if len(license_id) > 100:
            return True
        
        # Skip common false positive phrases
        false_phrases = [
            'you comply', 'their terms', 'conditions',
            'adapt all', 'organizations', 'individuals',
            'a compatible', 'certification process',
            'its license review', 'this license',
            'this public license', 'with a notice',
            'todo', 'fixme', 'xxx', 'placeholder',
            'insert license here', 'your license',
            'license_type', 'not-a-real-license'
        ]
        
        license_lower = license_id.lower()
        for phrase in false_phrases:
            if phrase in license_lower:
                return True
        
        return False
    
    def _looks_like_valid_license(self, license_id: str) -> bool:
        """Check if a string looks like a valid license identifier."""
        # Should be alphanumeric with hyphens, dots, or plus
        if not license_id:
            return False
        
        # Check length (most license IDs are between 2 and 50 chars)
        if len(license_id) < 2 or len(license_id) > 50:
            return False
        
        # Should mostly contain valid characters
        valid_chars = set('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-+. ')
        if not all(c in valid_chars for c in license_id):
            return False
        
        # Common license ID patterns
        known_patterns = [
            'MIT', 'BSD', 'Apache', 'GPL', 'LGPL', 'MPL',
            'ISC', 'CC', 'Unlicense', 'WTFPL', 'Zlib',
            'Python', 'PHP', 'Ruby', 'Perl', 'PSF'
        ]
        
        license_upper = license_id.upper()
        for pattern in known_patterns:
            if pattern in license_upper:
                return True
        
        # Check if it matches common license ID format (e.g., Apache-2.0, GPL-3.0+)
        if re.match(r'^[A-Za-z]+[\-\.]?[0-9]*\.?[0-9]*[\+]?$', license_id):
            return True
        
        return False