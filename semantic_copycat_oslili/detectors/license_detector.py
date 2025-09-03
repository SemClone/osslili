"""
License detection module with multi-tier detection system.
"""

import logging
import re
import fnmatch
from pathlib import Path
from typing import List, Optional, Set
from concurrent.futures import ThreadPoolExecutor, as_completed

from fuzzywuzzy import fuzz

from ..core.models import DetectedLicense, DetectionMethod, LicenseCategory
from ..core.input_processor import InputProcessor
from ..data.spdx_licenses import SPDXLicenseData
from .tlsh_detector import TLSHDetector
from ..utils.file_scanner import SafeFileScanner

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
    
    def _categorize_license(self, file_path: Path, detection_method: str, match_type: str = None) -> tuple[str, str]:
        """
        Categorize a license based on where and how it was detected.
        
        Returns:
            Tuple of (category, match_type)
        """
        file_name = file_path.name.lower()
        file_str = str(file_path).lower()
        
        # Primary declared licenses - found in LICENSE files or package metadata
        if self._is_license_file(file_path):
            return LicenseCategory.DECLARED.value, "license_file"
        
        # Package metadata files
        if file_name in ['package.json', 'setup.py', 'setup.cfg', 'pyproject.toml', 
                         'cargo.toml', 'pom.xml', 'build.gradle', 'composer.json']:
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
        
        # Track if this is a single file scan (user passed a file directly)
        single_file_mode = path.is_file()
        
        if single_file_mode:
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
                    executor.submit(self._detect_licenses_in_file_safe, file_path, single_file_mode): file_path
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
                    file_licenses = self._detect_licenses_in_file(file_path, single_file_mode)
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
    
    def _detect_licenses_in_file_safe(self, file_path: Path, single_file_mode: bool = False) -> List[DetectedLicense]:
        """Thread-safe wrapper for file license detection."""
        try:
            return self._detect_licenses_in_file(file_path, single_file_mode)
        except Exception as e:
            logger.debug(f"Error in file {file_path}: {e}")
            return []
    
    def _find_license_files(self, directory: Path) -> List[Path]:
        """Find potential license files in directory."""
        license_files = []
        scanner = SafeFileScanner(
            max_depth=self.config.max_recursion_depth,
            follow_symlinks=False
        )
        
        # Direct pattern matching
        for pattern in self.license_patterns:
            for file_path in scanner.scan_directory(directory, '*'):
                if pattern.match(file_path.name):
                    license_files.append(file_path)
        
        # Reset scanner for second pass (to reset visited inodes)
        scanner = SafeFileScanner(
            max_depth=self.config.max_recursion_depth,
            follow_symlinks=False
        )
        
        # Fuzzy matching for license-like filenames
        for file_path in scanner.scan_directory(directory, '*'):
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
        
        scanner = SafeFileScanner(
            max_depth=self.config.max_recursion_depth,
            follow_symlinks=False
        )
        
        # Scan all files recursively
        for file_path in scanner.scan_directory(directory, '*'):
            # Skip binary/archive files
            if file_path.suffix.lower() in skip_extensions:
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
        
        # Method 1: Detect SPDX tags
        tag_licenses = self._detect_spdx_tags(content, file_path)
        licenses.extend(tag_licenses)
        
        # Method 2: If in single file mode, ALWAYS treat as potential license content
        if single_file_mode:
            # Apply three-tier detection on full text
            detected = self._detect_license_from_text(content, file_path)
            if detected:
                licenses.append(detected)
        # Method 3: Detect by filename (for dedicated license files)
        elif self._is_license_file(file_path):
            # Apply three-tier detection on full text
            detected = self._detect_license_from_text(content, file_path)
            if detected:
                licenses.append(detected)
        
        # Method 4: Check for license indicators in regular files
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
                            category, match_type = self._categorize_license(
                                file_path, DetectionMethod.TAG.value
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
                                category, match_type = self._categorize_license(
                                    file_path, DetectionMethod.TAG.value
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
            category, match_type = self._categorize_license(
                file_path, DetectionMethod.REGEX.value
            )
            return DetectedLicense(
                spdx_id="MIT",
                name="MIT License",
                confidence=1.0,
                detection_method=DetectionMethod.REGEX.value,
                source_file=str(file_path),
                category=category,
                match_type=match_type
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
        if category == "declared":
            # License files and documentation should have high confidence
            if match_type == "license_file":
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
        Tier 3: Regex pattern matching fallback.
        
        Args:
            text: License text
            file_path: Source file
            
        Returns:
            Detected license or None
        """
        text_lower = text.lower()
        
        # MIT License patterns - check for key phrases
        mit_key_phrase = r'permission is hereby granted.*free of charge.*to any person.*obtaining.*copy.*software'
        mit_patterns = [
            r'permission is hereby granted.*free of charge.*to any person',
            r'mit license',
            r'software is provided.*as is.*without warranty',
            r'deal in the software without restriction',
            r'use.*copy.*modify.*merge.*publish.*distribute.*sublicense'
        ]
        
        # Strong indicator - the key MIT phrase
        has_key_phrase = bool(re.search(mit_key_phrase, text_lower))
        
        mit_matches = sum(1 for p in mit_patterns if re.search(p, text_lower))
        mit_score = mit_matches / len(mit_patterns)
        
        # If we have the key MIT phrase, lower the threshold
        threshold = 0.4 if has_key_phrase else 0.6
        
        if mit_score >= threshold or has_key_phrase:
            # Determine if this is a full license header or just a reference
            match_type_hint = "license_header" if mit_matches >= 2 else "license_reference"
            category, match_type = self._categorize_license(
                file_path, DetectionMethod.REGEX.value, match_type_hint
            )
            # Adjust confidence based on context and match type
            confidence = self._adjust_regex_confidence(mit_score, category, match_type, mit_matches)
            return DetectedLicense(
                spdx_id="MIT",
                name="MIT License",
                confidence=confidence,
                detection_method=DetectionMethod.REGEX.value,
                source_file=str(file_path),
                category=category,
                match_type=match_type
            )
        
        # Apache 2.0 patterns
        apache_patterns = [
            r'apache license.*version 2\.0',
            r'licensed under the apache license',
            r'www\.apache\.org/licenses/license-2\.0'
        ]
        
        apache_matches = sum(1 for p in apache_patterns if re.search(p, text_lower))
        apache_score = apache_matches / len(apache_patterns)
        
        if apache_score >= 0.6:
            # Determine if this is a full license header or just a reference
            match_type_hint = "license_header" if apache_matches >= 2 else "license_reference"
            category, match_type = self._categorize_license(
                file_path, DetectionMethod.REGEX.value, match_type_hint
            )
            # Adjust confidence based on context and match type
            confidence = self._adjust_regex_confidence(apache_score, category, match_type, apache_matches)
            return DetectedLicense(
                spdx_id="Apache-2.0",
                name="Apache License 2.0",
                confidence=confidence,
                detection_method=DetectionMethod.REGEX.value,
                source_file=str(file_path),
                category=category,
                match_type=match_type
            )
        
        # GPL patterns
        gpl_patterns = [
            r'gnu general public license',
            r'gpl.*version [23]',
            r'free software foundation'
        ]
        
        gpl_matches = sum(1 for p in gpl_patterns if re.search(p, text_lower))
        gpl_score = gpl_matches / len(gpl_patterns)
        
        if gpl_score >= 0.6:
            # Determine GPL version
            if 'version 3' in text_lower or 'gplv3' in text_lower:
                spdx_id = "GPL-3.0"
                name = "GNU General Public License v3.0"
            else:
                spdx_id = "GPL-2.0"
                name = "GNU General Public License v2.0"
            
            # Determine if this is a full license header or just a reference
            match_type_hint = "license_header" if gpl_matches >= 2 else "license_reference"
            category, match_type = self._categorize_license(
                file_path, DetectionMethod.REGEX.value, match_type_hint
            )
            # Adjust confidence based on context and match type
            confidence = self._adjust_regex_confidence(gpl_score, category, match_type, gpl_matches)
            return DetectedLicense(
                spdx_id=spdx_id,
                name=name,
                confidence=confidence,
                detection_method=DetectionMethod.REGEX.value,
                source_file=str(file_path),
                category=category,
                match_type=match_type
            )
        
        # BSD patterns
        bsd_patterns = [
            r'redistribution and use in source and binary forms',
            r'bsd.*license',
            r'neither the name.*nor the names of its contributors'
        ]
        
        bsd_matches = sum(1 for p in bsd_patterns if re.search(p, text_lower))
        bsd_score = bsd_matches / len(bsd_patterns)
        
        if bsd_score >= 0.6:
            # Determine if this is a full license header or just a reference
            match_type_hint = "license_header" if bsd_matches >= 2 else "license_reference"
            category, match_type = self._categorize_license(
                file_path, DetectionMethod.REGEX.value, match_type_hint
            )
            # Adjust confidence based on context and match type
            confidence = self._adjust_regex_confidence(bsd_score, category, match_type, bsd_matches)
            return DetectedLicense(
                spdx_id="BSD-3-Clause",
                name="BSD 3-Clause License",
                confidence=confidence,
                detection_method=DetectionMethod.REGEX.value,
                source_file=str(file_path),
                category=category,
                match_type=match_type
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