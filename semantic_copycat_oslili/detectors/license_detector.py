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
            # Match until end of line, comment marker, or semicolon
            # Strip trailing comment markers and whitespace
            re.compile(r'SPDX-License-Identifier:\s*([^\n;#*]+?)(?:\s*[*/]*\s*)?$', re.IGNORECASE | re.MULTILINE),
            # Python METADATA: License-Expression: <license>
            re.compile(r'License-Expression:\s*([^\s\n]+)', re.IGNORECASE),
            # package.json style: "license": "MIT"
            re.compile(r'"license"\s*:\s*"([^"]+)"', re.IGNORECASE),
            # pyproject.toml style: license = {text = "Apache-2.0"}
            re.compile(r'license\s*=\s*\{[^}]*text\s*=\s*"([^"]+)"', re.IGNORECASE),
            # pyproject.toml style: license = "MIT"
            re.compile(r'^\s*license\s*=\s*"([^"]+)"', re.IGNORECASE | re.MULTILINE),
            # General License: <license> (but more restrictive to avoid false positives)
            re.compile(r'^\s*License:\s*([A-Za-z0-9\-\.]+)', re.IGNORECASE | re.MULTILINE),
            # @license <license>
            re.compile(r'@license\s+([A-Za-z0-9\-\.]+)', re.IGNORECASE),
            # Licensed under <license>
            re.compile(r'Licensed under (?:the\s+)?([^,\n]+?)(?:\s+[Ll]icense)?', re.IGNORECASE),
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
        
        # Process files in parallel for better performance
        max_workers = min(self.config.thread_count if hasattr(self.config, 'thread_count') else 4, len(files_to_scan))
        
        if max_workers > 1 and len(files_to_scan) > 1:
            # Parallel processing
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # Submit all files for processing
                future_to_file = {
                    executor.submit(self._detect_licenses_in_file_safe, file_path): file_path
                    for file_path in files_to_scan
                }
                
                # Collect results as they complete
                for future in as_completed(future_to_file):
                    try:
                        file_licenses = future.result(timeout=30)  # 30 second timeout per file
                        for license in file_licenses:
                            # Deduplicate by license ID and confidence
                            key = (license.spdx_id, round(license.confidence, 2))
                            if key not in processed_licenses:
                                processed_licenses.add(key)
                                licenses.append(license)
                    except Exception as e:
                        file_path = future_to_file[future]
                        logger.warning(f"Error processing {file_path}: {e}")
        else:
            # Sequential processing for single file or small sets
            for file_path in files_to_scan:
                try:
                    file_licenses = self._detect_licenses_in_file(file_path)
                    for license in file_licenses:
                        # Deduplicate by license ID and confidence
                        key = (license.spdx_id, round(license.confidence, 2))
                        if key not in processed_licenses:
                            processed_licenses.add(key)
                            licenses.append(license)
                except Exception as e:
                    logger.warning(f"Error processing {file_path}: {e}")
        
        # Sort by confidence
        licenses.sort(key=lambda x: x.confidence, reverse=True)
        
        return licenses
    
    def _detect_licenses_in_file_safe(self, file_path: Path) -> List[DetectedLicense]:
        """Thread-safe wrapper for file license detection."""
        try:
            return self._detect_licenses_in_file(file_path)
        except Exception as e:
            logger.debug(f"Error in file {file_path}: {e}")
            return []
    
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
        
        # Scan all files recursively
        for file_path in directory.rglob('*'):
            if not file_path.is_file():
                continue
            
            # Skip binary/archive files
            if file_path.suffix.lower() in skip_extensions:
                continue
            
            # Skip hidden files and directories (optional)
            if any(part.startswith('.') for part in file_path.parts[:-1]):
                continue
            
            # Skip __pycache__ and similar directories
            if '__pycache__' in file_path.parts or 'node_modules' in file_path.parts:
                continue
            
            # Try to determine if file is text/readable
            if self._is_readable_file(file_path):
                source_files.append(file_path)
                count += 1
                if count >= limit:
                    return source_files
        
        return source_files
    
    def _read_file_smart(self, file_path: Path) -> str:
        """
        Read large files intelligently by sampling beginning and end.
        License info is usually in the first few KB or at the end.
        """
        try:
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
        """Check if a file is likely readable text."""
        try:
            # Try to read first 1KB to check if it's text
            with open(file_path, 'rb') as f:
                chunk = f.read(1024)
                if not chunk:
                    return True  # Empty files are "readable"
                
                # Check for null bytes (binary indicator)
                if b'\x00' in chunk:
                    return False
                
                # Try to decode as UTF-8
                try:
                    chunk.decode('utf-8')
                    return True
                except UnicodeDecodeError:
                    # Try with common encodings
                    for encoding in ['latin-1', 'cp1252', 'iso-8859-1']:
                        try:
                            chunk.decode(encoding)
                            return True
                        except UnicodeDecodeError:
                            continue
                    return False
        except (OSError, IOError):
            return False
    
    def _detect_licenses_in_file(self, file_path: Path) -> List[DetectedLicense]:
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
        
        # Skip files that are likely to contain false positives
        file_name = file_path.name.lower()
        # Only skip our own detector/data files to avoid self-detection
        if any(name in file_name for name in ['spdx_licenses.py', 'license_detector.py']):
            return licenses
        
        for pattern in self.spdx_tag_patterns:
            matches = pattern.findall(content)
            
            for match in matches:
                # Clean up the match
                license_id = match.strip()
                
                # Skip obvious false positives
                if self._is_false_positive_license(license_id):
                    continue
                
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
                            # Only record unknown licenses if they look valid
                            if self._looks_like_valid_license(normalized_id):
                                licenses.append(DetectedLicense(
                                    spdx_id=normalized_id,
                                    name=normalized_id,
                                    confidence=0.9,
                                    detection_method=DetectionMethod.TAG.value,
                                    source_file=str(file_path)
                                ))
        
        return licenses
    
    def _normalize_license_id(self, license_id: str) -> str:
        """
        Normalize license ID to match SPDX format.
        Handles common variations and aliases using SPDX data mappings.
        """
        if not license_id:
            return license_id
        
        # Remove whitespace and normalize case for lookup
        normalized = license_id.strip()
        lookup_key = normalized.lower()
        
        # First, check the bundled SPDX aliases
        if hasattr(self.spdx_data, 'aliases') and self.spdx_data.aliases:
            if lookup_key in self.spdx_data.aliases:
                return self.spdx_data.aliases[lookup_key]
        
        # Check name mappings (includes full names to SPDX IDs)
        if hasattr(self.spdx_data, 'name_mappings') and self.spdx_data.name_mappings:
            if lookup_key in self.spdx_data.name_mappings:
                return self.spdx_data.name_mappings[lookup_key]
        
        # Check for common aliases first
        common_aliases = {
            'new bsd': 'BSD-3-Clause',
            'new bsd license': 'BSD-3-Clause',
            'simplified bsd': 'BSD-2-Clause', 
            'simplified bsd license': 'BSD-2-Clause',
            'the mit license': 'MIT',
            'cc0': 'CC0-1.0',
            'cc zero': 'CC0-1.0',
        }
        
        if lookup_key in common_aliases:
            return common_aliases[lookup_key]
        
        # Try variations of the input
        variations = [
            lookup_key,
            lookup_key.replace(' license', ''),
            lookup_key.replace(' public license', ''),
            lookup_key.replace(' general public license', ''),
            lookup_key.replace('licence', 'license'),  # British spelling
            lookup_key.replace('-', ' '),
            lookup_key.replace('_', ' '),
            lookup_key.replace('.', ' '),
        ]
        
        for variant in variations:
            if hasattr(self.spdx_data, 'name_mappings') and self.spdx_data.name_mappings:
                if variant in self.spdx_data.name_mappings:
                    return self.spdx_data.name_mappings[variant]
        
        # Common replacements for normalization
        replacements = {
            ' License': '',
            ' license': '',
            ' Licence': '',
            ' licence': '',
            'Apache ': 'Apache-',
            'GPL ': 'GPL-',
            'LGPL ': 'LGPL-',
            'BSD ': 'BSD-',
            'MIT ': 'MIT',
            'Mozilla ': 'MPL-',
            'Creative Commons ': 'CC-',
            ' version ': '-',
            ' Version ': '-',
            ' v': '-',
            ' V': '-',
            'v.': '-',
            'V.': '-',
            ' or later': '-or-later',
            ' OR LATER': '-or-later',
            ' only': '-only',
            ' ONLY': '-only',
            ' ': '-'
        }
        
        # Handle + suffix BEFORE other replacements (for GPL-3.0+, etc.)
        if normalized.endswith('+'):
            normalized = normalized[:-1] + '-or-later'
        
        for old, new in replacements.items():
            normalized = normalized.replace(old, new)
        
        # Check if normalized version exists in SPDX
        if self._is_valid_spdx_id(normalized):
            return normalized
        
        # Handle specific cases as fallback
        normalized_upper = normalized.upper()
        
        if normalized_upper == 'MIT':
            return 'MIT'
        elif normalized_upper == 'ISC':
            return 'ISC'
        elif normalized_upper == 'UNLICENSE':
            return 'Unlicense'
        elif normalized_upper == 'ZLIB':
            return 'Zlib'
        elif normalized_upper == 'WTFPL':
            return 'WTFPL'
        elif normalized_upper.startswith('APACHE'):
            if '2' in normalized:
                return 'Apache-2.0'
            elif '1.1' in normalized:
                return 'Apache-1.1'
            elif '1' in normalized:
                return 'Apache-1.0'
        elif normalized_upper.startswith('GPL') or normalized_upper.startswith('LGPL') or normalized_upper.startswith('AGPL'):
            version = self._extract_version(normalized)
            if 'LGPL' in normalized_upper:
                base = 'LGPL'
            elif 'AGPL' in normalized_upper:
                base = 'AGPL'
            else:
                base = 'GPL'
            
            if version:
                # Ensure version has .0 if it's a single digit (GPL-3 -> GPL-3.0)
                if '.' not in version and version in ['1', '2', '3']:
                    version = f'{version}.0'
                
                # Handle suffixes
                if 'later' in normalized.lower() or normalized.endswith('+') or normalized.endswith('-or-later'):
                    suffix = '-or-later'
                elif 'only' in normalized.lower() or normalized.endswith('-only'):
                    suffix = '-only'
                else:
                    suffix = ''
                    
                return f'{base}-{version}{suffix}'
        elif normalized_upper.startswith('BSD'):
            if '3' in normalized or 'three' in normalized.lower() or 'new' in normalized.lower():
                return 'BSD-3-Clause'
            elif '2' in normalized or 'two' in normalized.lower() or 'simplified' in normalized.lower():
                return 'BSD-2-Clause'
            elif '4' in normalized or 'four' in normalized.lower() or 'original' in normalized.lower():
                return 'BSD-4-Clause'
            elif '0' in normalized or 'zero' in normalized.lower():
                return '0BSD'
        elif normalized_upper.startswith('CC'):
            # Creative Commons licenses
            return self._normalize_cc_license(normalized)
        elif 'PYTHON' in normalized_upper:
            if '2' in normalized:
                return 'Python-2.0'
            else:
                return 'PSF-2.0'
        elif 'RUBY' in normalized_upper:
            return 'Ruby'
        elif 'PHP' in normalized_upper:
            if '3.01' in normalized:
                return 'PHP-3.01'
            elif '3' in normalized:
                return 'PHP-3.0'
        elif 'PERL' in normalized_upper:
            return 'Artistic-1.0-Perl'
        elif 'POSTGRESQL' in normalized_upper:
            return 'PostgreSQL'
        
        return normalized
    
    def _is_valid_spdx_id(self, license_id: str) -> bool:
        """Check if a license ID exists in SPDX data."""
        if hasattr(self.spdx_data, 'licenses') and self.spdx_data.licenses:
            return license_id in self.spdx_data.licenses
        return False
    
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
        """Parse SPDX license expression."""
        # Don't split if it contains "or later" or "or-later" (common suffix)
        expression_lower = expression.lower()
        if 'or later' in expression_lower or 'or-later' in expression_lower:
            # This is likely a single license with suffix, not an OR expression
            return [expression.strip()]
        
        # Simple parser for license expressions
        # Split on AND, OR, WITH operators
        expression = expression.replace('(', '').replace(')', '')
        
        # Split on operators (but not "or later")
        parts = re.split(r'\s+(?:AND|OR|WITH)\s+', expression, flags=re.IGNORECASE)
        
        return [p.strip() for p in parts if p.strip()]
    
    
    def _detect_license_from_text(self, text: str, file_path: Path) -> Optional[DetectedLicense]:
        """
        Detect license from text using three-tier detection.
        
        Args:
            text: License text
            file_path: Source file path
            
        Returns:
            Detected license or None
        """
        # Quick check for obvious MIT license
        text_lower = text.lower()
        if 'permission is hereby granted, free of charge' in text_lower and 'mit license' in text_lower:
            return DetectedLicense(
                spdx_id="MIT",
                name="MIT License",
                confidence=1.0,
                detection_method=DetectionMethod.REGEX.value,
                source_file=str(file_path)
            )
        
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
            # Confirm with TLSH to reduce false positives
            if self.tlsh_detector.confirm_license_match(text, best_match):
                license_info = self.spdx_data.get_license_info(best_match)
                return DetectedLicense(
                    spdx_id=best_match,
                    name=license_info.get('name', best_match) if license_info else best_match,
                    confidence=best_score,
                    detection_method=DetectionMethod.DICE_SORENSEN.value,
                    source_file=str(file_path)
                )
            else:
                logger.debug(f"Dice-Sørensen match {best_match} not confirmed by TLSH")
        
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
    
    def _is_false_positive_license(self, license_id: str) -> bool:
        """Check if a detected license ID is likely a false positive."""
        # Skip empty or too short
        if not license_id or len(license_id) < 2:
            return True
        
        # Skip if contains regex patterns or code-like syntax
        false_positive_patterns = [
            '\\', '{', '}', '[', ']', '(', ')', 
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