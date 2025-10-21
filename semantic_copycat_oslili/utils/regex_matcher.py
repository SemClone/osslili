"""
Optimized regex pattern matcher using lookup tables.
"""

import json
import re
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ..core.models import DetectedLicense, DetectionMethod

logger = logging.getLogger(__name__)


class RegexPatternMatcher:
    """Optimized regex pattern matcher using external configuration."""

    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialize regex pattern matcher.

        Args:
            config_path: Path to regex patterns config file
        """
        if config_path is None:
            config_path = Path(__file__).parent.parent / "data" / "regex_patterns.json"

        self.config_path = config_path
        self._load_patterns()

    def _load_patterns(self) -> None:
        """Load regex patterns from JSON configuration."""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)

            self.license_patterns = config.get('license_patterns', [])
            self.reference_patterns = config.get('license_reference_patterns', [])

            # Pre-compile regex patterns for performance
            for license_config in self.license_patterns:
                license_config['compiled_patterns'] = [
                    re.compile(pattern, re.IGNORECASE)
                    for pattern in license_config['patterns']
                ]

                # Compile key phrase if present
                if 'key_phrase' in license_config:
                    license_config['compiled_key_phrase'] = re.compile(
                        license_config['key_phrase'], re.IGNORECASE
                    )

            # Compile reference patterns
            self.compiled_reference_patterns = [
                {
                    'compiled': re.compile(ref['pattern'], re.IGNORECASE),
                    'group': ref['group']
                }
                for ref in self.reference_patterns
            ]

        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.warning(f"Failed to load regex patterns config: {e}")
            # Use minimal defaults
            self.license_patterns = []
            self.reference_patterns = []
            self.compiled_reference_patterns = []

    def match_license_patterns(self, text: str, file_path: Path,
                             categorize_func, adjust_confidence_func) -> Optional[DetectedLicense]:
        """
        Match license patterns against text using lookup table approach.

        Args:
            text: Text to search
            file_path: Source file path
            categorize_func: Function to categorize license
            adjust_confidence_func: Function to adjust confidence

        Returns:
            Detected license or None
        """
        text_lower = text.lower()

        # Iterate through license patterns in priority order
        for license_config in self.license_patterns:
            result = self._match_single_license(
                license_config, text_lower, file_path,
                categorize_func, adjust_confidence_func
            )
            if result:
                return result

        # Try reference patterns as fallback
        return self._match_reference_patterns(text_lower, file_path, categorize_func)

    def _match_single_license(self, license_config: Dict, text_lower: str, file_path: Path,
                            categorize_func, adjust_confidence_func) -> Optional[DetectedLicense]:
        """Match a single license configuration against text."""
        patterns = license_config['compiled_patterns']

        # Count matches
        matches = sum(1 for pattern in patterns if pattern.search(text_lower))

        # Check key phrase if present
        has_key_phrase = False
        if 'compiled_key_phrase' in license_config:
            has_key_phrase = bool(license_config['compiled_key_phrase'].search(text_lower))

        # Calculate score
        total_patterns = len(patterns)
        score = matches / total_patterns if total_patterns > 0 else 0

        # Determine threshold
        if has_key_phrase and 'key_phrase_threshold' in license_config:
            threshold = license_config['key_phrase_threshold']
        else:
            threshold = license_config.get('threshold', 0.6)

        # Check minimum matches requirement
        min_matches = license_config.get('min_matches', 0)
        if min_matches > 0 and matches < min_matches:
            return None

        # Check if score meets threshold or key phrase is present
        if score >= threshold or has_key_phrase:

            # Handle version-specific detection
            spdx_id, name = self._determine_license_version(license_config, text_lower)

            # Determine match type
            match_type_hint = "license_header" if matches >= 2 else "license_reference"
            category, match_type = categorize_func(
                file_path, DetectionMethod.REGEX.value, match_type_hint
            )

            # Adjust confidence
            confidence = adjust_confidence_func(score, category, match_type, matches)

            return DetectedLicense(
                spdx_id=spdx_id,
                name=name,
                confidence=confidence,
                detection_method=DetectionMethod.REGEX.value,
                source_file=str(file_path),
                category=category,
                match_type=match_type
            )

        return None

    def _determine_license_version(self, license_config: Dict, text_lower: str) -> Tuple[str, str]:
        """Determine specific license version based on text content."""
        base_spdx_id = license_config['spdx_id']
        base_name = license_config['name']

        version_detection = license_config.get('version_detection')
        if not version_detection:
            return base_spdx_id, base_name

        # Check for version 3 patterns (GPL/LGPL)
        if 'v3_patterns' in version_detection:
            for pattern in version_detection['v3_patterns']:
                if pattern in text_lower:
                    if base_spdx_id.startswith('GPL-'):
                        return "GPL-3.0", "GNU General Public License v3.0"
                    elif base_spdx_id.startswith('LGPL-'):
                        return "LGPL-3.0", "GNU Lesser General Public License v3.0"

        # Check for specific version patterns (LGPL 2.1)
        if 'v2_1_patterns' in version_detection:
            for pattern in version_detection['v2_1_patterns']:
                if pattern in text_lower:
                    return "LGPL-2.1", "GNU Lesser General Public License v2.1"

        # Return default version
        default = version_detection.get('default', base_spdx_id)
        if default != base_spdx_id:
            # Update name accordingly
            if default == "GPL-2.0":
                return default, "GNU General Public License v2.0"
            elif default == "LGPL-2.1":
                return default, "GNU Lesser General Public License v2.1"

        return base_spdx_id, base_name

    def _match_reference_patterns(self, text_lower: str, file_path: Path,
                                categorize_func) -> Optional[DetectedLicense]:
        """Match license reference patterns."""
        for ref_pattern in self.compiled_reference_patterns:
            match = ref_pattern['compiled'].search(text_lower)
            if match:
                license_name = match.group(ref_pattern['group']).upper()

                # Only return if it looks like a valid license
                if self._is_valid_license_reference(license_name):
                    category, match_type = categorize_func(
                        file_path, DetectionMethod.REGEX.value, "license_reference"
                    )

                    return DetectedLicense(
                        spdx_id=license_name,
                        name=license_name,
                        confidence=0.70,  # Lower confidence for extracted references
                        detection_method=DetectionMethod.REGEX.value,
                        source_file=str(file_path),
                        category=category,
                        match_type=match_type
                    )

        return None

    def _is_valid_license_reference(self, license_name: str) -> bool:
        """Check if extracted license name is likely valid."""
        if not license_name or len(license_name) < 2:
            return False

        # Known license name patterns
        known_patterns = ['MIT', 'BSD', 'APACHE', 'GPL', 'LGPL', 'MPL', 'ISC', 'CC']
        license_upper = license_name.upper()

        return any(pattern in license_upper for pattern in known_patterns)

    def get_pattern_count(self) -> int:
        """Get total number of license patterns loaded."""
        return len(self.license_patterns)

    def reload_patterns(self) -> None:
        """Reload patterns from configuration file."""
        self._load_patterns()