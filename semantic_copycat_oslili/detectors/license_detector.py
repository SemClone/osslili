"""
License detection module with multi-tier detection system.
"""

import logging
import re
import fnmatch
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Optional, Set, Tuple
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
        # Ensure SPDX data and hashes are loaded
        _ = self.spdx_data.licenses  # Trigger lazy loading of licenses and hashes
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
            re.compile(r'SPDX-License-Identifier:\s*([^\n]+?)(?:\s*\*/)?(?:\s*-->)?$', re.IGNORECASE | re.MULTILINE),
            # Python METADATA: License-Expression: <license>
            re.compile(r'License-Expression:\s*([^\s\n]+)', re.IGNORECASE),
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
            re.compile(r'@license\s+([A-Za-z0-9\-\.]+)', re.IGNORECASE),
            # Licensed under <license> - Fixed to capture full license name
            re.compile(r'[Ll]icensed\s+under\s+(?:the\s+)?([A-Za-z0-9\-\.\s]+?)(?:\s+[Ll]icense)?(?:[,\n;]|$)', re.IGNORECASE),
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

        # Extract SPDX tags from comments
        spdx_patterns = [
            r'(?:^|\s)SPDX-License-Identifier:\s*([^\s\n]+)',
            r'(?:^|\s)License:\s*([^\s\n]+)',
        ]

        for pattern in spdx_patterns:
            matches = re.finditer(pattern, header_content, re.IGNORECASE | re.MULTILINE)
            for match in matches:
                license_id = match.group(1).strip()
                # Remove comment markers if present
                license_id = license_id.rstrip('*/>').strip()

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

                        # Skip SPDX exceptions (they modify licenses, not standalone)
                        # Common exceptions end with "-exception" or are known exception IDs
                        if 'exception' in lid.lower() and not lid.startswith('Font-exception'):
                            continue

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
            'GPL-3.0': ['GPL-3', 'GPLv3', 'GPL version 3', 'GNU General Public License v3',
                        'GNU General Public License version 3', 'GPL v3'],
            'GPL-2.0': ['GPL-2', 'GPLv2', 'GPL version 2', 'GNU General Public License v2',
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
            'ISC': ['ISC', 'ISC License'],
            'Artistic-2.0': ['Artistic-2.0', 'Artistic License 2.0'],
            'Unlicense': ['Unlicense', 'The Unlicense'],
            # Additional patterns from scancode-licensedb
            'Python-2.0': ['Python', 'Python License', 'Python Software Foundation License', 'PSF', 'PYTHON',
                           'Python Software Foundation', 'PSF License', 'the Python Software Foundation License'],
            'PHP-3.0': ['PHP', 'PHP License', 'PHP-3.0', 'PHP 3.0'],
            'PHP-3.01': ['PHP-3.01', 'PHP 3.01', 'PHP License 3.01'],
            'Ruby': ['Ruby', 'Ruby License', 'RUBY'],
            'Perl': ['Perl', 'Perl License', 'Artistic-Perl'],
            'Zlib': ['zlib', 'Zlib', 'ZLIB License'],
            'OpenSSL': ['OpenSSL', 'OpenSSL License', 'OpenSSL/SSLeay'],
            'JSON': ['JSON', 'JSON License', 'The JSON License'],
            '0BSD': ['0BSD', 'BSD Zero Clause', 'BSD-0-Clause', 'Free Public License'],
            'PostgreSQL': ['PostgreSQL', 'PostgreSQL License', 'PGSQL'],
            'WTFPL': ['WTFPL', 'Do What The F*ck You Want To Public License'],
            'Vim': ['Vim', 'Vim License', 'VIM'],
            'Beerware': ['Beerware', 'Beer-ware', 'THE BEER-WARE LICENSE'],
        }

        # Helper method for version suffixes
        def handle_version_suffix(base_license: str, context: str) -> str:
            """
            Handle version suffixes like +, -or-later, -only.
            """
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
                if variation.lower() in content.lower():
                    # Check context
                    pattern_re = re.compile(re.escape(variation), re.IGNORECASE)
                    match = pattern_re.search(content)
                    if match:
                        # Check if it appears in a license context
                        start = max(0, match.start() - 50)
                        context = content[start:match.end()]
                        has_context = any(re.search(pattern, context, re.IGNORECASE) for pattern in context_patterns)

                        # Check for comment or line start
                        if match.start() > 0:
                            prefix = content[max(0, match.start()-3):match.start()]
                            line_start = any(c in prefix for c in '\n*#/') or prefix.strip() in ['', '//', '/*', '#', '*']
                        else:
                            line_start = True

                        if has_context or line_start:
                            # Handle version suffixes and normalization
                            final_spdx_id = handle_version_suffix(spdx_id, content[match.start():match.end()+20])

                            # Normalize generic GPL to GPL-2.0-or-later if no version specified
                            if final_spdx_id == 'GPL':
                                # Look for version hints nearby
                                context_text = content[max(0, match.start()-100):min(len(content), match.end()+100)]
                                if '3' in context_text or 'v3' in context_text or 'version 3' in context_text.lower():
                                    final_spdx_id = 'GPL-3.0'
                                elif '2' in context_text or 'v2' in context_text or 'version 2' in context_text.lower():
                                    final_spdx_id = 'GPL-2.0'
                                else:
                                    final_spdx_id = 'GPL-2.0-or-later'  # Default for generic GPL

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
            if license_file_path.exists():
                try:
                    license_content = self.input_processor.read_text_file(license_file_path)
                    if license_content:
                        # Detect license from the file content using Dice-Sørensen with TLSH confirmation
                        detected_licenses = self._detect_from_full_text(license_content, license_file_path)
                        for detected in detected_licenses:
                            # Update the source to show it came from pyproject.toml reference
                            detected.source_file = str(file_path)
                            detected.match_type = "package_metadata_file"
                            detected.category = LicenseCategory.DECLARED.value
                            licenses.append(detected)
                except Exception as e:
                    logger.debug(f"Failed to read license file {license_file_path}: {e}")
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
        """Parse SPDX license expression including complex formats."""
        # Don't split if it contains "or later" or "or-later" (common suffix)
        expression_lower = expression.lower()
        if 'or later' in expression_lower or 'or-later' in expression_lower:
            # Check if this is really a suffix or an OR expression
            # GPL-2.0-or-later is a suffix, but "MIT OR Apache" is an expression
            if not re.search(r'\s+OR\s+(?!later)', expression, re.IGNORECASE):
                return [expression.strip()]

        # Handle comma-separated licenses (e.g., "MIT, Apache-2.0, BSD")
        if ',' in expression and not any(op in expression.upper() for op in [' OR ', ' AND ', ' WITH ']):
            parts = [p.strip() for p in expression.split(',')]
            return [p for p in parts if p]

        # Collect all licenses found in the expression
        licenses = []

        # First handle WITH exceptions specially (keep them together)
        # e.g., "GPL-3.0 WITH Classpath-exception-2.0"
        with_pattern = r'([A-Za-z0-9\-\.]+)\s+WITH\s+([A-Za-z0-9\-\.]+)'
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

        # Split on AND/OR operators
        parts = re.split(r'\s+(?:AND|OR)\s+', temp_expression, flags=re.IGNORECASE)

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
        
        if best_match and best_score >= 0.9:  # 90% threshold
            
            # For very high confidence (>95%), skip TLSH confirmation
            # For lower confidence, confirm with TLSH to reduce false positives
            if best_score >= 0.95 or self.tlsh_detector.confirm_license_match(text, best_match):
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

        # Skip if it's a valid SPDX expression with parentheses (not a false positive)
        if any(op in license_id.upper() for op in [' OR ', ' AND ', ' WITH ']):
            # This looks like a valid SPDX expression, not a false positive
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