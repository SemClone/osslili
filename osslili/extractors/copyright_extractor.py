"""
Copyright extraction module with pattern recognition.
"""

import logging
import re
from pathlib import Path
from typing import List, Optional, Set, Tuple
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

from ..core.models import CopyrightInfo
from ..core.input_processor import InputProcessor
from ..utils.file_scanner import SafeFileScanner

logger = logging.getLogger(__name__)


class CopyrightExtractor:
    """Extract copyright information from source code."""
    
    def __init__(self, config):
        """
        Initialize copyright extractor.
        
        Args:
            config: Configuration object
        """
        self.config = config
        self.input_processor = InputProcessor()
        
        # Compile copyright patterns
        self.copyright_patterns = self._compile_copyright_patterns()
        
        # Common author/contributor file names
        self.author_files = [
            'AUTHORS', 'AUTHORS.md', 'AUTHORS.txt', 'AUTHORS.rst',
            'CONTRIBUTORS', 'CONTRIBUTORS.md', 'CONTRIBUTORS.txt',
            'CREDITS', 'CREDITS.md', 'CREDITS.txt',
            'MAINTAINERS', 'MAINTAINERS.md'
        ]
    
    def _compile_copyright_patterns(self) -> List[re.Pattern]:
        """Compile regex patterns for copyright detection."""
        patterns = [
            # Standard copyright format: Copyright (c) YYYY Name
            # More restrictive: stop at common delimiters and code patterns
            re.compile(
                r'Copyright\s*(?:\(c\)|©)?\s*(\d{4}(?:\s*[-,]\s*\d{4})*)?[\s,]*(?:by\s+)?([A-Za-z][^;\{\}\[\]\(\)<>\n\r]*?)(?:\.|,|\s*$|\s*All\s+rights)',
                re.IGNORECASE | re.MULTILINE
            ),
            
            # Alternative format: © YYYY Name
            re.compile(
                r'©\s*(\d{4}(?:\s*[-,]\s*\d{4})*)?[\s,]*([A-Za-z][^;\{\}\[\]\(\)<>\n\r]*?)(?:\.|,|\s*$|\s*All\s+rights)',
                re.IGNORECASE | re.MULTILINE
            ),
            
            # (C) YYYY Name format
            re.compile(
                r'\(C\)\s*(\d{4}(?:\s*[-,]\s*\d{4})*)?[\s,]*(?:by\s+)?([A-Za-z][^;\{\}\[\]\(\)<>\n\r]*?)(?:\.|,|\s*$|\s*All\s+rights)',
                re.IGNORECASE | re.MULTILINE
            ),
            
            # Author: Name format - more restrictive
            re.compile(
                r'^\s*(?:Author|Created by|Written by):\s*([A-Za-z][^;\{\}\[\]\(\)<>\n\r]*?)(?:\s*$|\s*<)',
                re.IGNORECASE | re.MULTILINE
            ),
            
            # Contributors format - more restrictive  
            re.compile(
                r'^\s*(?:Contributor|Maintainer):\s*([A-Za-z][^;\{\}\[\]\(\)<>\n\r]*?)(?:\s*$|\s*<)',
                re.IGNORECASE | re.MULTILINE
            ),
        ]
        
        return patterns
    
    def extract_copyrights(self, path: Path) -> List[CopyrightInfo]:
        """
        Extract copyright information from a directory or file.
        
        Args:
            path: Directory or file path to scan
            
        Returns:
            List of copyright information
        """
        copyrights = []
        processed_statements = set()
        
        if path.is_file():
            files_to_scan = [path]
        else:
            # Find files to scan
            files_to_scan = self._find_copyright_files(path)
        
        logger.info(f"Scanning {len(files_to_scan)} files for copyright information")
        
        # Process files
        if self.config.thread_count > 1 and len(files_to_scan) > 10:
            # Multi-threaded processing for many files
            with ThreadPoolExecutor(max_workers=self.config.thread_count) as executor:
                futures = {
                    executor.submit(self._extract_copyrights_from_file, file_path): file_path
                    for file_path in files_to_scan
                }
                
                for future in as_completed(futures):
                    try:
                        file_copyrights = future.result()
                        for copyright_info in file_copyrights:
                            # Deduplicate by statement
                            if copyright_info.statement not in processed_statements:
                                processed_statements.add(copyright_info.statement)
                                copyrights.append(copyright_info)
                    except Exception as e:
                        file_path = futures[future]
                        logger.error(f"Error extracting copyright from {file_path}: {e}")
        else:
            # Single-threaded processing
            for file_path in files_to_scan:
                file_copyrights = self._extract_copyrights_from_file(file_path)
                for copyright_info in file_copyrights:
                    if copyright_info.statement not in processed_statements:
                        processed_statements.add(copyright_info.statement)
                        copyrights.append(copyright_info)
        
        # Sort by confidence
        copyrights.sort(key=lambda x: x.confidence, reverse=True)
        
        # Also check package metadata
        metadata_copyrights = self._extract_from_metadata(path)
        for mc in metadata_copyrights:
            if mc.statement not in processed_statements:
                processed_statements.add(mc.statement)
                copyrights.append(mc)
        
        return copyrights
    
    def _find_copyright_files(self, directory: Path) -> List[Path]:
        """Find files likely to contain copyright information."""
        files_to_scan = []
        scanner = SafeFileScanner(
            max_depth=self.config.max_recursion_depth,
            follow_symlinks=False
        )
        
        # Priority 1: License and author files
        for file_name in self.author_files:
            for file_path in scanner.scan_directory(directory, file_name):
                files_to_scan.append(file_path)
        
        # Priority 2: License files (only at root level)
        license_patterns = ['LICENSE*', 'LICENCE*', 'COPYING*', 'COPYRIGHT*', 'NOTICE*']
        for pattern in license_patterns:
            for file_path in directory.glob(pattern):
                if file_path.is_file() and file_path not in files_to_scan:
                    files_to_scan.append(file_path)
        
        # Priority 3: README files (only at root level)
        readme_patterns = ['README*', 'readme*']
        for pattern in readme_patterns:
            for file_path in directory.glob(pattern):
                if file_path.is_file() and file_path not in files_to_scan:
                    files_to_scan.append(file_path)
        
        # Priority 4: Source file headers (scan ALL source files for complete copyright detection)
        source_extensions = ['.py', '.js', '.java', '.c', '.cpp', '.go', '.rs', '.h', '.hpp', '.ts', '.tsx', '.jsx']
        
        # Reset scanner for source files
        scanner = SafeFileScanner(
            max_depth=self.config.max_recursion_depth,
            follow_symlinks=False
        )
        
        # Scan ALL source files - no limit
        for ext in source_extensions:
            for file_path in scanner.scan_directory(directory, f'*{ext}'):
                if file_path not in files_to_scan:
                    files_to_scan.append(file_path)
        
        return files_to_scan
    
    def _extract_copyrights_from_file(self, file_path: Path) -> List[CopyrightInfo]:
        """Extract copyright information from a single file."""
        copyrights = []
        
        # Read file content (limit to first 10KB for performance)
        content = self.input_processor.read_text_file(file_path, max_size=10240)
        if not content:
            return copyrights
        
        # Apply patterns
        for pattern in self.copyright_patterns:
            matches = pattern.findall(content)
            
            for match in matches:
                copyright_info = self._parse_copyright_match(match, file_path)
                if copyright_info:
                    copyrights.append(copyright_info)
        
        return copyrights
    
    def _parse_copyright_match(self, match: Tuple, file_path: Path) -> Optional[CopyrightInfo]:
        """Parse a copyright regex match into CopyrightInfo."""
        try:
            if len(match) == 2:
                # Format with year and holder
                year_str, holder = match
                
                # Check if this is a placeholder pattern like "YYYY Name"
                if year_str and re.match(r'^(YYYY|yyyy|XXXX|xxxx)', year_str):
                    # This is likely a placeholder, skip it
                    return None
                
                years = self._parse_years(year_str) if year_str else None
                original_holder = holder
                holder = self._clean_holder(holder)
            elif len(match) == 1:
                # Format with just holder
                original_holder = match[0]
                holder = self._clean_holder(match[0])
                years = None
            else:
                return None
            
            if not holder:
                logger.debug(f"Rejected copyright holder from {file_path}: '{original_holder}' (cleaned to empty)")
                return None
            
            # Debug log successful extraction
            logger.debug(f"Extracted copyright from {file_path}: '{original_holder}' -> '{holder}'")
            
            # Build statement
            if years:
                year_display = self._format_years(years)
                statement = f"Copyright {year_display} {holder}"
            else:
                statement = f"Copyright {holder}"
            
            return CopyrightInfo(
                holder=holder,
                years=years,
                statement=statement,
                source_file=str(file_path),
                confidence=0.9 if years else 0.8
            )
        
        except Exception as e:
            logger.debug(f"Error parsing copyright match: {e}")
            return None
    
    def _parse_years(self, year_str: str) -> Optional[List[int]]:
        """Parse year string into list of years."""
        if not year_str:
            return None
        
        # Check for placeholder year patterns
        if re.match(r'^(YYYY|yyyy|XXXX|xxxx|YY|yy|XX|xx)', year_str):
            return None
        
        years = []
        
        # Remove spaces
        year_str = year_str.replace(' ', '')
        
        # Handle ranges (e.g., "2020-2023")
        if '-' in year_str:
            parts = year_str.split('-')
            if len(parts) == 2:
                try:
                    start = int(parts[0])
                    end = int(parts[1])
                    years.extend(range(start, end + 1))
                except ValueError:
                    pass
        
        # Handle comma-separated years
        if ',' in year_str:
            for part in year_str.split(','):
                try:
                    year = int(part.strip())
                    if year not in years:
                        years.append(year)
                except ValueError:
                    pass
        
        # Single year
        if not years:
            try:
                year = int(year_str.strip())
                years.append(year)
            except ValueError:
                pass
        
        # Validate years (reasonable range)
        current_year = datetime.now().year
        years = [y for y in years if 1900 <= y <= current_year + 1]
        
        return sorted(years) if years else None
    
    def _format_years(self, years: List[int]) -> str:
        """Format list of years for display."""
        if not years:
            return ""
        
        if len(years) == 1:
            return str(years[0])
        
        # Check if consecutive range
        if years == list(range(years[0], years[-1] + 1)):
            return f"{years[0]}-{years[-1]}"
        
        # Otherwise comma-separated
        return ", ".join(str(y) for y in years)
    
    def _clean_holder(self, holder: str) -> str:
        """Clean and normalize copyright holder name."""
        if not holder:
            return ""
        
        # Remove common prefixes
        holder = holder.strip()
        holder = re.sub(r'^\s*(?:by|By)\s+', '', holder)
        
        # Check for placeholder patterns FIRST
        placeholder_patterns = [
            r'^(YYYY|yyyy|XXXX|xxxx)',  # Year placeholders
            r'^(NAME|Name|name)',  # Name placeholders
            r'^(AUTHOR|Author|author)$',  # Just "author"
            r'^(HOLDER|Holder|holder)$',  # Just "holder"
            r'^(OWNER|Owner|owner)$',  # Just "owner"
            r'^(YOUR|Your|your)\s+(NAME|Name|name)',  # "Your Name"
            r'^<.*>$',  # Just brackets
            r'^\[.*\]$',  # Just square brackets
            r'^\{.*\}$',  # Just curly brackets
            r'^TODO',  # TODO markers
            r'^TBD',  # TBD markers
            r'^FIXME',  # FIXME markers
        ]
        
        for pattern in placeholder_patterns:
            if re.match(pattern, holder):
                return ""
        
        # Remove "All rights reserved" and similar
        holder = re.sub(r'\s*[,.]?\s*All rights reserved\.?$', '', holder, flags=re.IGNORECASE)
        
        # Remove trailing punctuation
        holder = re.sub(r'\s*[.,;:]+$', '', holder)
        
        # Extract from email format (Name <email>)
        email_match = re.match(r'^([^<]+?)\s*<[^>]+>$', holder)
        if email_match:
            holder = email_match.group(1).strip()
        
        # Remove standalone email addresses
        if re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', holder):
            return ""
        
        # Remove trailing parentheses content (but keep if it's the whole thing)
        if '(' in holder and ')' in holder:
            base = re.sub(r'\s*\([^)]+\)$', '', holder).strip()
            if base:
                holder = base
        
        # Clean whitespace
        holder = ' '.join(holder.split())
        
        # Don't return if it's just punctuation or too short
        if len(holder) < 3 or not any(c.isalnum() for c in holder):
            return ""
        
        # Filter out code-like patterns (common false positives)
        code_indicators = [
            'return ', 'function ', 'def ', 'class ', 'import ',
            'from ', 'if ', 'for ', 'while ', 'const ', 'let ', 'var ',
            'public ', 'private ', 'static ', 'void ', 'int ', 'string ',
            'package ', 'module ', 'export ', 'require ', 'use ',
            '==', '!=', '>=', '<=', '&&', '||', '->', '=>', '::',
            '${', '#{', '{{', '}}', '/*', '*/', '//'
        ]
        
        holder_lower = holder.lower()
        for indicator in code_indicators:
            if indicator in holder_lower:
                return ""
        
        # Check if it looks like a file path or URL
        if '/' in holder and (holder.startswith('/') or holder.startswith('./') or 
                              holder.startswith('../') or '://' in holder or
                              'http:' in holder or 'https:' in holder or 
                              'ftp:' in holder or 'domain.invalid' in holder):
            return ""
        
        # Filter out if it looks like HTML or XML tags
        if '<' in holder and '>' in holder and not email_match:
            return ""
        
        # Filter out common invalid patterns
        invalid_patterns = [
            r'^by\s+http',  # "by http://..."
            r'^by\s+[a-z]+://',  # "by protocol://..."
            r'^\w+\.\w+/',  # domain.com/...
            r'^https?://',  # URLs
            r'\.invalid',  # Invalid domains
            r'^localhost',  # Localhost
            r'^127\.0\.0\.1',  # IP addresses
        ]
        
        holder_lower = holder.lower()
        for pattern in invalid_patterns:
            if re.search(pattern, holder_lower):
                return ""
        
        # Filter out if it contains too many special characters (likely code)
        special_char_count = sum(1 for c in holder if c in '{}[]()<>;:=+-*/%&|^~!@#$')
        if special_char_count > len(holder) * 0.2:  # More than 20% special chars
            return ""
        
        # Filter out single words that are common programming keywords
        programming_keywords = [
            'copyright', 'license', 'patent', 'holder', 'owner', 'statement',
            'information', 'extractor', 'info', 'notice', 'permission',
            'you', 'your', 'must', 'retain', 'that', 'this', 'with',
            'evidence', 'found', 'detection', 'patterns', 'regex',
            'file', 'from', 'name', 'format', 'match', 'future'
        ]
        
        # Check if it's a single word that's a keyword
        if ' ' not in holder:
            if holder.lower() in programming_keywords:
                return ""
        
        # Filter out phrases that are clearly not copyright holders
        invalid_phrases = [
            'copyright', 'license', 'patent', 'you must', 'notice',
            'owner or entity', 'owner that', 'information', 'extraction',
            'regex match', 'name format', 'years', 'statement',
            'holder', 'owner', 's_from', 's =', 'info"', 's_found',
            'evidence', 'by source', 's in ', 'you comply', 'their terms',
            'in result', 'lines that vary', 'may vary', 'will vary',
            'varies', 'variable', 'placeholder', 'example', 'sample',
            'lorem ipsum', 'detector', 'generator', 'scanner', 'analyzer', 'processor'
        ]

        # Check for exact matches of test placeholders (not as part of larger names)
        # Only filter if it's EXACTLY these words (case-insensitive)
        test_placeholders = ['test', 'demo', 'dummy', 'foo', 'bar', 'baz']
        if holder_lower.strip() in test_placeholders:
            return ""

        # For test-related words, only filter if they're standalone words
        # Allow names like "Test Corporation" or "TestCo Inc"
        test_word_patterns = [r'\btest\b', r'\bdemo\b', r'\bdummy\b', r'\bfoo\b', r'\bbar\b', r'\bbaz\b']
        for pattern in test_word_patterns:
            # Check if it's ONLY the test word (not part of a larger name)
            if re.fullmatch(pattern, holder_lower):
                return ""

        for phrase in invalid_phrases:
            if phrase in holder_lower:
                return ""
        
        return holder
    
    def _extract_from_metadata(self, path: Path) -> List[CopyrightInfo]:
        """Extract copyright from package metadata files."""
        copyrights = []
        
        # Check for package.json (npm)
        package_json = path / 'package.json'
        if package_json.exists():
            copyrights.extend(self._extract_from_package_json(package_json))
        
        # Check for setup.py or setup.cfg (Python)
        setup_py = path / 'setup.py'
        if setup_py.exists():
            copyrights.extend(self._extract_from_setup_py(setup_py))
        
        setup_cfg = path / 'setup.cfg'
        if setup_cfg.exists():
            copyrights.extend(self._extract_from_setup_cfg(setup_cfg))
        
        # Check for Cargo.toml (Rust)
        cargo_toml = path / 'Cargo.toml'
        if cargo_toml.exists():
            copyrights.extend(self._extract_from_cargo_toml(cargo_toml))
        
        return copyrights
    
    def _extract_from_package_json(self, file_path: Path) -> List[CopyrightInfo]:
        """Extract copyright from package.json."""
        copyrights = []
        
        try:
            import json
            with open(file_path, 'r') as f:
                data = json.load(f)
            
            # Check author field
            if 'author' in data:
                author = data['author']
                if isinstance(author, str):
                    holder = self._clean_holder(author)
                elif isinstance(author, dict):
                    holder = self._clean_holder(author.get('name', ''))
                else:
                    holder = None
                
                if holder:
                    copyrights.append(CopyrightInfo(
                        holder=holder,
                        statement=f"Copyright {holder}",
                        source_file=str(file_path),
                        confidence=0.85
                    ))
            
            # Check contributors
            if 'contributors' in data and isinstance(data['contributors'], list):
                for contributor in data['contributors'][:5]:  # Limit to first 5
                    if isinstance(contributor, str):
                        holder = self._clean_holder(contributor)
                    elif isinstance(contributor, dict):
                        holder = self._clean_holder(contributor.get('name', ''))
                    else:
                        continue
                    
                    if holder:
                        copyrights.append(CopyrightInfo(
                            holder=holder,
                            statement=f"Copyright {holder}",
                            source_file=str(file_path),
                            confidence=0.7
                        ))
        
        except Exception as e:
            logger.debug(f"Error extracting from package.json: {e}")
        
        return copyrights
    
    def _extract_from_setup_py(self, file_path: Path) -> List[CopyrightInfo]:
        """Extract copyright from setup.py."""
        copyrights = []
        
        try:
            content = self.input_processor.read_text_file(file_path, max_size=50000)
            if not content:
                return copyrights
            
            # Look for author in setup() call
            author_pattern = re.compile(r'author\s*=\s*["\']([^"\']+)["\']')
            match = author_pattern.search(content)
            
            if match:
                holder = self._clean_holder(match.group(1))
                if holder:
                    copyrights.append(CopyrightInfo(
                        holder=holder,
                        statement=f"Copyright {holder}",
                        source_file=str(file_path),
                        confidence=0.85
                    ))
        
        except Exception as e:
            logger.debug(f"Error extracting from setup.py: {e}")
        
        return copyrights
    
    def _extract_from_setup_cfg(self, file_path: Path) -> List[CopyrightInfo]:
        """Extract copyright from setup.cfg."""
        copyrights = []
        
        try:
            import configparser
            config = configparser.ConfigParser()
            config.read(file_path)
            
            if 'metadata' in config:
                author = config['metadata'].get('author', '')
                if author:
                    holder = self._clean_holder(author)
                    if holder:
                        copyrights.append(CopyrightInfo(
                            holder=holder,
                            statement=f"Copyright {holder}",
                            source_file=str(file_path),
                            confidence=0.85
                        ))
        
        except Exception as e:
            logger.debug(f"Error extracting from setup.cfg: {e}")
        
        return copyrights
    
    def _extract_from_cargo_toml(self, file_path: Path) -> List[CopyrightInfo]:
        """Extract copyright from Cargo.toml."""
        copyrights = []
        
        try:
            # Simple TOML parsing for authors field
            content = self.input_processor.read_text_file(file_path, max_size=50000)
            if not content:
                return copyrights
            
            # Look for authors field
            authors_pattern = re.compile(r'authors\s*=\s*\[(.*?)\]', re.DOTALL)
            match = authors_pattern.search(content)
            
            if match:
                authors_str = match.group(1)
                # Extract quoted strings
                author_pattern = re.compile(r'"([^"]+)"')
                for author_match in author_pattern.findall(authors_str):
                    holder = self._clean_holder(author_match)
                    if holder:
                        copyrights.append(CopyrightInfo(
                            holder=holder,
                            statement=f"Copyright {holder}",
                            source_file=str(file_path),
                            confidence=0.85
                        ))
        
        except Exception as e:
            logger.debug(f"Error extracting from Cargo.toml: {e}")
        
        return copyrights