"""
License ID normalization utility with external configuration.
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


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

    def _handle_version_patterns(self, lookup_key: str) -> Optional[str]:
        """Handle version-specific license patterns."""
        for version, patterns in self.version_patterns.items():
            for pattern in patterns:
                if pattern in lookup_key:
                    # Try to determine the base license type
                    if 'gpl' in lookup_key and 'lgpl' not in lookup_key:
                        return f"GPL-{version}"
                    elif 'lgpl' in lookup_key:
                        return f"LGPL-{version}"
                    elif 'apache' in lookup_key:
                        return f"Apache-{version}"
                    elif 'cc' in lookup_key and 'by' in lookup_key:
                        return f"CC-BY-{version}"

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