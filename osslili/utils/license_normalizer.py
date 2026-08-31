"""
License ID normalization utility with external configuration.
"""

import json
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


# The families SPDX wrote the deprecated "or later" form for. A plus on
# anything else says nothing that resolves, and carrying it through produced
# an identifier no lookup could find.
_THE_OR_LATER_FAMILIES = frozenset({'GPL', 'LGPL', 'AGPL'})


# Words that name a GNU licence only when the GNU name is beside them.
_ONLY_BESIDE_THE_GNU_NAME = frozenset({'affero', 'lesser', 'library'})


def _a_gnu_name(lookup_key: str) -> bool:
    return 'gpl' in lookup_key or 'general public' in lookup_key


# The deprecated grant, written either way: a plus that ends the string, or
# the words that mean the same.
_OR_LATER_IN_WORDS = re.compile(
    r'\+\s*$|\b(?:or|and)[\s-]+(?:later|above|greater|any\s+later\s+version)\b',
    re.IGNORECASE,
)


class LicenseNormalizer:
    """Utility class for normalizing license IDs using external configuration."""

    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialize license normalizer.

        Args:
            config_path: Path to license normalization config file
        """
        if config_path is None:
            config_path = Path(__file__).parent.parent / "data" / "license_normalization.json"

        self.config_path = config_path
        self._spdx_ids = None
        self._load_config()

    def _load_config(self) -> None:
        """Load normalization configuration from JSON file."""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)

            self.common_aliases = config.get('common_aliases', {})
            self.text_variations = config.get('text_variations', [])
            self.version_patterns = config.get('version_patterns', {})
            self.spdx_corrections = config.get('spdx_corrections', {})

        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.warning(f"Failed to load license normalization config: {e}")
            # Use minimal defaults
            self.common_aliases = {}
            self.text_variations = []
            self.version_patterns = {}
            self.spdx_corrections = {}

    @staticmethod
    def _exact_spdx_id(license_id, spdx_data):
        """The SPDX identifier this string already is, if it is one.

        Matched without regard to case, so "mit" still becomes "MIT", and
        returned in SPDX's own spelling.
        """
        if not license_id or spdx_data is None:
            return None

        licenses = getattr(spdx_data, 'licenses', None)
        if not licenses:
            return None

        if license_id in licenses:
            return license_id

        wanted = license_id.lower()
        for known in licenses:
            if known.lower() == wanted:
                return known

        return None

    def normalize_license_id(self, license_id: str, spdx_data=None) -> str:
        """
        Normalize license ID to match SPDX format.

        Args:
            license_id: Raw license identifier
            spdx_data: Optional SPDX data object for additional lookups

        Returns:
            Normalized SPDX license ID
        """
        if not license_id:
            return license_id

        # Remove whitespace and normalize case for lookup
        normalized = license_id.strip()
        lookup_key = normalized.lower()

        # Step 0: a string that is already an SPDX identifier means itself.
        #
        # Everything below is for turning vague input into an identifier:
        # "BSD" into BSD-3-Clause, "lgpl" into LGPL-2.1. Those guesses used to
        # run first, and they do not check whether they are guessing about
        # something exact. "BSD-2-Clause" reduced to the base word "bsd" and
        # came back BSD-3-Clause, a different licence with a clause it does
        # not have. "LGPL-2.1-or-later" came back LGPL-2.1-only, dropping the
        # recipient's option to use a later version.
        canonical = self._exact_spdx_id(normalized, spdx_data)
        if canonical:
            return canonical

        # Step 1: Check SPDX data aliases first if available
        if spdx_data:
            if hasattr(spdx_data, 'aliases') and spdx_data.aliases:
                if lookup_key in spdx_data.aliases:
                    return spdx_data.aliases[lookup_key]

            # Check name mappings
            if hasattr(spdx_data, 'name_mappings') and spdx_data.name_mappings:
                if lookup_key in spdx_data.name_mappings:
                    return spdx_data.name_mappings[lookup_key]

        # Step 2: Check common aliases from config
        if lookup_key in self.common_aliases:
            return self.common_aliases[lookup_key]

        # Step 3: Try text variations
        for variation in self.text_variations:
            pattern = variation['pattern']
            replacement = variation['replacement']
            if pattern in lookup_key:
                variant = lookup_key.replace(pattern, replacement).strip()

                # Check if the variant matches any known license
                if self._check_variant_match(variant, spdx_data):
                    return self._check_variant_match(variant, spdx_data)

        # Step 4: Handle version-specific patterns
        result = self._handle_version_patterns(lookup_key)
        if result:
            return result

        # Step 5: Check SPDX corrections for base license types
        base_license = self._extract_base_license(lookup_key)
        if base_license in self.spdx_corrections:
            return self.spdx_corrections[base_license]

        # Step 6: Try direct SPDX lookup if available
        if spdx_data and hasattr(spdx_data, 'get_license_info'):
            license_info = spdx_data.get_license_info(normalized)
            if license_info:
                return license_info.get('licenseId', normalized)

        # Return original if no normalization found
        return normalized

    def _check_variant_match(self, variant: str, spdx_data=None) -> Optional[str]:
        """Check if a variant matches known licenses."""
        # Check against common aliases
        if variant in self.common_aliases:
            return self.common_aliases[variant]

        # Check against SPDX data if available
        if spdx_data:
            if hasattr(spdx_data, 'name_mappings') and spdx_data.name_mappings:
                if variant in spdx_data.name_mappings:
                    return spdx_data.name_mappings[variant]

        return None

    # How a version is written in an identifier. A licence is written "v3" as
    # often as "3.0", and only the second is part of one, so the spelling
    # found is not the spelling returned (issue #125).
    _AS_AN_IDENTIFIER_SPELLS_IT = {'v1': '1.0', 'v2': '2.0', 'v3': '3.0'}

    def _handle_version_patterns(self, lookup_key: str) -> Optional[str]:
        """Handle version-specific license patterns."""
        # Longest spelling first. "gplv2.1" contains "v2" as well as "2.1",
        # and answering on the first found turned LGPL-2.1 into LGPL-2.0,
        # which is a different licence.
        spellings = sorted(
            (
                (pattern, version)
                for version, patterns in self.version_patterns.items()
                for pattern in patterns
            ),
            key=lambda found: -len(found[0]),
        )
        for pattern, version in spellings:
            if True:
                if pattern in lookup_key:
                    family = self._gnu_or_other_family(lookup_key)
                    if not family:
                        continue
                    # A plus that ends the string is the deprecated "or later"
                    # form and is the whole of what it says: that a later
                    # version may be used. Dropping it here left the
                    # modernisation downstream with nothing to read and
                    # reported the -only grant, the opposite of the licence.
                    #
                    # Kept only for the family SPDX wrote it for. Elsewhere
                    # the plus resolves to nothing, so "Apache-2.0+" came back
                    # as an identifier no lookup could find, was recorded once
                    # at a guess and again once the plus was dropped, and one
                    # licence was reported twice.
                    # The grant is written two ways, "GPL-2.0+" and "GPL-2.0
                    # or later", and only the first was read. The second came
                    # back as the bare version and was modernised to the -only
                    # grant, which is the opposite of what it says.
                    or_later = (
                        '+' if family in _THE_OR_LATER_FAMILIES
                        and _OR_LATER_IN_WORDS.search(lookup_key) else ''
                    )
                    # A line carrying a grant in words is left exactly as it
                    # was read. Which licence such a line names, and whether
                    # the grant can be written on it, is settled by the
                    # expression reader, and the answers it gives today rest
                    # on what this step returns. Issue #125 is about a bare
                    # name that resolves to nothing, so that is all this
                    # changes.
                    if _OR_LATER_IN_WORDS.search(lookup_key):
                        return f"{family}-{version}{or_later}"

                    spelled = self._AS_AN_IDENTIFIER_SPELLS_IT.get(version, version)
                    answer = f"{family}-{spelled}{or_later}"
                    # An answer that names no licence is not an answer. It was
                    # returned anyway, and returning stopped the later steps
                    # that could have reached a real one, so "Affero GPLv3"
                    # became "AGPL-v3" and then nothing at all.
                    if self._names_a_licence(answer):
                        return answer

        return None

    def _names_a_licence(self, identifier: str) -> bool:
        """Whether SPDX lists this identifier, in any of its grant forms.

        Read from the bundled licence list rather than from the normalisation
        config, because the question is what SPDX has rather than what this
        file knows how to rewrite.
        """
        if self._spdx_ids is None:
            listed = Path(__file__).parent.parent / "data" / "spdx_licenses.json"
            try:
                with open(listed, 'r', encoding='utf-8') as handle:
                    self._spdx_ids = set(json.load(handle).get('licenses', {}))
            except Exception:
                self._spdx_ids = set()

        if not self._spdx_ids:
            # Nothing to check against. Answering is better than silence.
            return True

        bare = identifier[:-1] if identifier.endswith('+') else identifier
        return (
            bare in self._spdx_ids
            or f"{bare}-only" in self._spdx_ids
            or f"{bare}-or-later" in self._spdx_ids
        )

    @staticmethod
    def _gnu_or_other_family(lookup_key: str) -> Optional[str]:
        """Which licence family this string names.

        The GNU names contain one another: "agpl" contains "gpl", and so does
        "lgpl". Asking whether "gpl" is in the string, with only "lgpl" ruled
        out, answered GPL for an AGPL string. That is a different licence,
        not a different spelling: the Affero terms oblige whoever runs the
        software over a network to offer its source, and the GPL does not.
        The longest name is asked for first.
        """
        for name, family in (
            ('agpl', 'AGPL'),
            ('affero', 'AGPL'),
            ('lgpl', 'LGPL'),
            ('lesser', 'LGPL'),
            ('library', 'LGPL'),
            ('gpl', 'GPL'),
            ('apache', 'Apache'),
        ):
            if name not in lookup_key:
                continue
            # Written out, these names contain no "agpl" or "lgpl" at all,
            # while they do contain "gpl": "Affero GPLv3", "Lesser GPLv2.1",
            # and the older "Library General Public License". They only name
            # a licence next to the GNU name, though. "zlib library 1.2" is
            # not the Lesser GPL, and claiming it there took the string away
            # from the steps that would have answered Zlib.
            if name in _ONLY_BESIDE_THE_GNU_NAME and not _a_gnu_name(lookup_key):
                continue
            return family
        if 'cc' in lookup_key and 'by' in lookup_key:
            return 'CC-BY'
        return None

    def _extract_base_license(self, lookup_key: str) -> str:
        """Extract base license type from complex license string."""
        # Remove common suffixes and prefixes
        cleaned = lookup_key.lower()

        # Remove version numbers and common words
        for word in ['license', 'licence', 'version', 'ver', 'v', 'public', 'general', 'software']:
            cleaned = cleaned.replace(word, ' ')

        # Clean up whitespace and special chars
        cleaned = ' '.join(cleaned.split())
        cleaned = cleaned.replace('-', ' ').replace('_', ' ').replace('.', ' ')

        # Try to identify base license type
        words = cleaned.split()
        if not words:
            return lookup_key

        # Check for compound license names
        if 'lesser' in words and ('gpl' in words or 'general' in words):
            return 'lgpl'
        elif 'gpl' in words or 'general' in words:
            return 'gpl'
        elif 'bsd' in words:
            return 'bsd'
        elif 'apache' in words:
            return 'apache'
        elif 'mit' in words:
            return 'mit'

        # Return first meaningful word
        for word in words:
            if len(word) > 1 and word.isalpha():
                return word

        return lookup_key

    def is_valid_spdx_expression(self, license_id: str) -> bool:
        """Check if a license ID is a valid SPDX expression."""
        if not license_id:
            return False

        # Check for SPDX operators
        if any(op in license_id.upper() for op in [' OR ', ' AND ', ' WITH ']):
            return True

        # Check against known patterns
        return license_id in self.common_aliases or license_id in self.spdx_corrections