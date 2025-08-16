"""
License detection module with multi-tier detection system.
"""

import logging
import re
import fnmatch
from pathlib import Path
from typing import List, Optional, Dict, Set, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

from fuzzywuzzy import fuzz
from fuzzywuzzy import process as fuzz_process

from ..core.models import DetectedLicense, DetectionMethod
from ..core.input_processor import InputProcessor
from ..data.spdx_licenses import SPDXLicenseData
from .tlsh_detector import TLSHDetector

logger = logging.getLogger(__name__)


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
        self.tlsh_detector = TLSHDetector(config, self.spdx_data)
        
        # License filename patterns
        self.license_patterns = self._compile_filename_patterns()
        
        # SPDX tag patterns
        self.spdx_tag_patterns = self._compile_spdx_patterns()
        
        # Common license indicators in text
        self.license_indicators = [
            'licensed under', 'license', 'copyright', 'permission is hereby granted',
            'redistribution and use', 'all rights reserved', 'this software is provided',
            'warranty', 'as is', 'merchantability', 'fitness for a particular purpose'
        ]
    
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
            re.compile(r'SPDX-License-Identifier:\s*([^\s\n]+)', re.IGNORECASE),
            # License: <license>
            re.compile(r'^\s*License:\s*([^\n]+)', re.IGNORECASE | re.MULTILINE),
            # @license <license>
            re.compile(r'@license\s+([^\s\n]+)', re.IGNORECASE),
            # Licensed under <license>
            re.compile(r'Licensed under (?:the\s+)?([^,\n]+)', re.IGNORECASE),
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
        
        if path.is_file():
            files_to_scan = [path]
        else:
            # Find potential license files
            files_to_scan = self._find_license_files(path)
            
            # Also scan common source files for embedded licenses
            files_to_scan.extend(self._find_source_files(path))
        
        logger.info(f"Scanning {len(files_to_scan)} files for licenses")
        
        # Process files
        for file_path in files_to_scan:
            file_licenses = self._detect_licenses_in_file(file_path)
            
            for license in file_licenses:
                # Deduplicate by license ID and confidence
                key = (license.spdx_id, round(license.confidence, 2))
                if key not in processed_licenses:
                    processed_licenses.add(key)
                    licenses.append(license)
        
        # Sort by confidence
        licenses.sort(key=lambda x: x.confidence, reverse=True)
        
        return licenses
    
    def _find_license_files(self, directory: Path) -> List[Path]:
        """Find potential license files in directory."""
        license_files = []
        
        # Direct pattern matching
        for pattern in self.license_patterns:
            for file_path in directory.rglob('*'):
                if file_path.is_file() and pattern.match(file_path.name):
                    license_files.append(file_path)
        
        # Fuzzy matching for license-like filenames
        for file_path in directory.rglob('*'):
            if file_path.is_file():
                name_lower = file_path.name.lower()
                
                # Check fuzzy match with common license names
                for base_name in ['license', 'licence', 'copying', 'copyright', 'notice']:
                    ratio = fuzz.partial_ratio(base_name, name_lower)
                    if ratio >= 85:  # 85% similarity threshold
                        if file_path not in license_files:
                            license_files.append(file_path)
                        break
        
        return license_files
    
    def _find_source_files(self, directory: Path, limit: int = 100) -> List[Path]:
        """Find source files to scan for embedded licenses."""
        source_extensions = [
            '.py', '.js', '.ts', '.java', '.c', '.cpp', '.h', '.hpp',
            '.go', '.rs', '.rb', '.php', '.cs', '.swift', '.kt', '.scala',
            '.md', '.txt', '.json', '.yaml', '.yml', '.toml'
        ]
        
        source_files = []
        count = 0
        
        for ext in source_extensions:
            for file_path in directory.rglob(f'*{ext}'):
                if file_path.is_file():
                    source_files.append(file_path)
                    count += 1
                    if count >= limit:
                        return source_files
        
        return source_files
    
    def _detect_licenses_in_file(self, file_path: Path) -> List[DetectedLicense]:
        """Detect licenses in a single file."""
        licenses = []
        
        # Read file content
        content = self.input_processor.read_text_file(file_path, max_size=1024*1024)  # 1MB limit
        if not content:
            return licenses
        
        # Method 1: Detect SPDX tags
        tag_licenses = self._detect_spdx_tags(content, file_path)
        licenses.extend(tag_licenses)
        
        # Method 2: Detect by filename (for dedicated license files)
        if self._is_license_file(file_path):
            # Apply three-tier detection on full text
            detected = self._detect_license_from_text(content, file_path)
            if detected:
                licenses.append(detected)
        
        # Method 3: Check for license indicators in regular files
        elif self._contains_license_text(content):
            # Extract potential license block
            license_block = self._extract_license_block(content)
            if license_block:
                detected = self._detect_license_from_text(license_block, file_path)
                if detected:
                    licenses.append(detected)
        
        return licenses
    
    def _is_license_file(self, file_path: Path) -> bool:
        """Check if file is likely a license file."""
        name_lower = file_path.name.lower()
        
        # Check patterns
        for pattern in self.license_patterns:
            if pattern.match(file_path.name):
                return True
        
        # Check common names
        license_names = ['license', 'licence', 'copying', 'copyright', 'notice', 'legal']
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
        
        return indicator_count >= 3  # At least 3 indicators
    
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
    
    def _detect_spdx_tags(self, content: str, file_path: Path) -> List[DetectedLicense]:
        """Detect SPDX license identifiers in content."""
        licenses = []
        found_ids = set()
        
        for pattern in self.spdx_tag_patterns:
            matches = pattern.findall(content)
            
            for match in matches:
                # Clean up the match
                license_id = match.strip()
                
                # Handle license expressions (AND, OR, WITH)
                license_ids = self._parse_license_expression(license_id)
                
                for lid in license_ids:
                    if lid not in found_ids:
                        found_ids.add(lid)
                        
                        # Normalize license ID
                        normalized_id = self._normalize_license_id(lid)
                        
                        # Get license info
                        license_info = self.spdx_data.get_license_info(normalized_id)
                        
                        if license_info:
                            licenses.append(DetectedLicense(
                                spdx_id=license_info['licenseId'],
                                name=license_info.get('name', normalized_id),
                                confidence=1.0,  # High confidence for explicit tags
                                detection_method=DetectionMethod.TAG.value,
                                source_file=str(file_path)
                            ))
                        else:
                            # Unknown license ID, but still record it
                            licenses.append(DetectedLicense(
                                spdx_id=normalized_id,
                                name=normalized_id,
                                confidence=0.9,
                                detection_method=DetectionMethod.TAG.value,
                                source_file=str(file_path)
                            ))
        
        return licenses
    
    def _parse_license_expression(self, expression: str) -> List[str]:
        """Parse SPDX license expression."""
        # Simple parser for license expressions
        # Split on AND, OR, WITH operators
        expression = expression.replace('(', '').replace(')', '')
        
        # Split on operators
        parts = re.split(r'\s+(?:AND|OR|WITH)\s+', expression, flags=re.IGNORECASE)
        
        return [p.strip() for p in parts if p.strip()]
    
    def _normalize_license_id(self, license_id: str) -> str:
        """Normalize license ID using aliases."""
        aliases = self.spdx_data.get_license_aliases()
        
        # Try exact match first
        if license_id in aliases:
            return aliases[license_id]
        
        # Try case-insensitive match
        license_lower = license_id.lower()
        if license_lower in aliases:
            return aliases[license_lower]
        
        # Try fuzzy matching
        if aliases:
            match, score = fuzz_process.extractOne(
                license_id,
                aliases.keys(),
                scorer=fuzz.ratio
            )
            
            if score >= 90:  # 90% similarity
                return aliases[match]
        
        return license_id
    
    def _detect_license_from_text(self, text: str, file_path: Path) -> Optional[DetectedLicense]:
        """
        Detect license from text using three-tier detection.
        
        Args:
            text: License text
            file_path: Source file path
            
        Returns:
            Detected license or None
        """
        # Tier 1: Dice-Sørensen similarity
        detected = self._tier1_dice_sorensen(text, file_path)
        if detected and detected.confidence >= self.config.similarity_threshold:
            return detected
        
        # Tier 2: TLSH fuzzy hashing
        detected = self.tlsh_detector.detect_license_tlsh(text, file_path)
        if detected and detected.confidence >= self.config.similarity_threshold:
            return detected
        
        # Tier 3: Regex pattern matching
        detected = self._tier3_regex_matching(text, file_path)
        if detected:
            return detected
        
        # No match found
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
        
        best_match = None
        best_score = 0.0
        
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
            
            if score > best_score:
                best_score = score
                best_match = license_id
        
        if best_match and best_score >= 0.9:  # 90% threshold
            license_info = self.spdx_data.get_license_info(best_match)
            return DetectedLicense(
                spdx_id=best_match,
                name=license_info.get('name', best_match) if license_info else best_match,
                confidence=best_score,
                detection_method=DetectionMethod.DICE_SORENSEN.value,
                source_file=str(file_path)
            )
        
        return None
    
    def _create_bigrams(self, text: str) -> Set[str]:
        """Create character bigrams from text."""
        bigrams = set()
        
        for i in range(len(text) - 1):
            bigrams.add(text[i:i+2])
        
        return bigrams
    
    def _dice_coefficient(self, set1: Set[str], set2: Set[str]) -> float:
        """Calculate Dice-Sørensen coefficient between two sets."""
        if not set1 or not set2:
            return 0.0
        
        intersection = len(set1 & set2)
        return (2.0 * intersection) / (len(set1) + len(set2))
    
    def _tier3_regex_matching(self, text: str, file_path: Path) -> Optional[DetectedLicense]:
        """
        Tier 3: Regex pattern matching fallback.
        
        Args:
            text: License text
            file_path: Source file
            
        Returns:
            Detected license or None
        """
        text_lower = text.lower()
        
        # MIT License patterns
        mit_patterns = [
            r'permission is hereby granted.*free of charge.*to any person',
            r'mit license',
            r'software is provided.*as is.*without warranty'
        ]
        
        mit_score = sum(1 for p in mit_patterns if re.search(p, text_lower)) / len(mit_patterns)
        
        if mit_score >= 0.6:
            return DetectedLicense(
                spdx_id="MIT",
                name="MIT License",
                confidence=mit_score,
                detection_method=DetectionMethod.REGEX.value,
                source_file=str(file_path)
            )
        
        # Apache 2.0 patterns
        apache_patterns = [
            r'apache license.*version 2\.0',
            r'licensed under the apache license',
            r'www\.apache\.org/licenses/license-2\.0'
        ]
        
        apache_score = sum(1 for p in apache_patterns if re.search(p, text_lower)) / len(apache_patterns)
        
        if apache_score >= 0.6:
            return DetectedLicense(
                spdx_id="Apache-2.0",
                name="Apache License 2.0",
                confidence=apache_score,
                detection_method=DetectionMethod.REGEX.value,
                source_file=str(file_path)
            )
        
        # GPL patterns
        gpl_patterns = [
            r'gnu general public license',
            r'gpl.*version [23]',
            r'free software foundation'
        ]
        
        gpl_score = sum(1 for p in gpl_patterns if re.search(p, text_lower)) / len(gpl_patterns)
        
        if gpl_score >= 0.6:
            # Determine GPL version
            if 'version 3' in text_lower or 'gplv3' in text_lower:
                spdx_id = "GPL-3.0"
                name = "GNU General Public License v3.0"
            else:
                spdx_id = "GPL-2.0"
                name = "GNU General Public License v2.0"
            
            return DetectedLicense(
                spdx_id=spdx_id,
                name=name,
                confidence=gpl_score,
                detection_method=DetectionMethod.REGEX.value,
                source_file=str(file_path)
            )
        
        # BSD patterns
        bsd_patterns = [
            r'redistribution and use in source and binary forms',
            r'bsd.*license',
            r'neither the name.*nor the names of its contributors'
        ]
        
        bsd_score = sum(1 for p in bsd_patterns if re.search(p, text_lower)) / len(bsd_patterns)
        
        if bsd_score >= 0.6:
            return DetectedLicense(
                spdx_id="BSD-3-Clause",
                name="BSD 3-Clause License",
                confidence=bsd_score,
                detection_method=DetectionMethod.REGEX.value,
                source_file=str(file_path)
            )
        
        return None