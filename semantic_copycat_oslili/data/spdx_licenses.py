"""
SPDX license data management module.
Downloads and caches SPDX license list data.
"""

import json
import logging
import hashlib
import re
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta

import requests

logger = logging.getLogger(__name__)


class SPDXLicenseData:
    """Manage SPDX license data with caching."""
    
    def __init__(self, config):
        """
        Initialize SPDX license data manager.
        
        Args:
            config: Configuration object
        """
        self.config = config
        
        # Path to bundled license data
        self.bundled_data_file = Path(__file__).parent / "spdx_licenses.json"
        
        # Set cache directory for any additional downloads
        if config.cache_dir:
            self.cache_dir = Path(config.cache_dir)
        else:
            self.cache_dir = Path.home() / ".cache" / "oslili"
        
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Cache file paths
        self.licenses_cache_file = self.cache_dir / "spdx_licenses.json"
        self.license_texts_dir = self.cache_dir / "license_texts"
        self.license_texts_dir.mkdir(exist_ok=True)
        
        # Cache duration (7 days)
        self.cache_duration = timedelta(days=7)
        
        # Loaded data
        self._bundled_data = None
        self._licenses = None
        self._license_texts = {}
        self._license_index = {}
        self._aliases = {}
        self._name_mappings = {}
        self._license_hashes = {}  # Store SHA-256 and MD5 hashes
    
    @property
    def licenses(self) -> Dict[str, Any]:
        """Get SPDX licenses data (lazy loading)."""
        if self._licenses is None:
            self._load_licenses()
        return self._licenses
    
    @property
    def aliases(self) -> Dict[str, str]:
        """Get license aliases mapping."""
        if self._aliases is None:
            self._load_licenses()
        return self._aliases
    
    @property
    def name_mappings(self) -> Dict[str, str]:
        """Get license name to SPDX ID mappings."""
        if self._name_mappings is None:
            self._load_licenses()
        return self._name_mappings
    
    def _load_licenses(self):
        """Load SPDX licenses from bundled data, cache, or download."""
        # First try bundled data
        if self.bundled_data_file.exists():
            logger.debug("Loading bundled SPDX license data")
            try:
                with open(self.bundled_data_file, 'r', encoding='utf-8') as f:
                    self._bundled_data = json.load(f)
                
                # Extract licenses for compatibility  
                # Keep as dict format, not list
                self._licenses = self._bundled_data.get("licenses", {})
                
                # Load aliases and mappings
                self._aliases = self._bundled_data.get("aliases", {})
                self._name_mappings = self._bundled_data.get("name_mappings", {})
                
                logger.debug(f"Loaded {len(self._bundled_data.get('licenses', {}))} bundled licenses")
                
                # Build index
                self._build_license_index()
                # Load or compute hashes
                self._load_license_hashes()
                return
            except Exception as e:
                logger.warning(f"Failed to load bundled data: {e}")
        
        # Fall back to cache or download
        if self._is_cache_valid(self.licenses_cache_file):
            logger.debug("Loading SPDX licenses from cache")
            with open(self.licenses_cache_file, 'r') as f:
                self._licenses = json.load(f)
        else:
            logger.info("Downloading SPDX license list")
            self._download_licenses()
        
        # Build index
        self._build_license_index()
        # Load or compute hashes
        self._load_license_hashes()
    
    def _is_cache_valid(self, cache_file: Path) -> bool:
        """Check if cache file is valid and recent."""
        if not cache_file.exists():
            return False
        
        # Check age
        mtime = datetime.fromtimestamp(cache_file.stat().st_mtime)
        age = datetime.now() - mtime
        
        return age < self.cache_duration
    
    def _download_licenses(self):
        """Download SPDX license list from GitHub."""
        try:
            response = requests.get(
                self.config.spdx_data_url,
                timeout=self.config.network_timeout
            )
            response.raise_for_status()
            
            data = response.json()
            
            # Save to cache
            with open(self.licenses_cache_file, 'w') as f:
                json.dump(data, f, indent=2)
            
            self._licenses = data
            logger.info(f"Downloaded {len(data.get('licenses', []))} SPDX licenses")
        
        except Exception as e:
            logger.error(f"Failed to download SPDX licenses: {e}")
            # Try to load stale cache
            if self.licenses_cache_file.exists():
                logger.warning("Using stale cache")
                with open(self.licenses_cache_file, 'r') as f:
                    self._licenses = json.load(f)
            else:
                # Use embedded minimal set
                self._licenses = self._get_embedded_licenses()
    
    def _get_embedded_licenses(self) -> Dict[str, Any]:
        """Get minimal embedded license set as fallback."""
        return {
            "licenses": [
                {
                    "licenseId": "MIT",
                    "name": "MIT License",
                    "isOsiApproved": True,
                    "detailsUrl": "https://spdx.org/licenses/MIT.json"
                },
                {
                    "licenseId": "Apache-2.0",
                    "name": "Apache License 2.0",
                    "isOsiApproved": True,
                    "detailsUrl": "https://spdx.org/licenses/Apache-2.0.json"
                },
                {
                    "licenseId": "GPL-3.0",
                    "name": "GNU General Public License v3.0 only",
                    "isOsiApproved": True,
                    "detailsUrl": "https://spdx.org/licenses/GPL-3.0.json"
                },
                {
                    "licenseId": "BSD-3-Clause",
                    "name": "BSD 3-Clause \"New\" or \"Revised\" License",
                    "isOsiApproved": True,
                    "detailsUrl": "https://spdx.org/licenses/BSD-3-Clause.json"
                },
                {
                    "licenseId": "ISC",
                    "name": "ISC License",
                    "isOsiApproved": True,
                    "detailsUrl": "https://spdx.org/licenses/ISC.json"
                }
            ]
        }
    
    def _build_license_index(self):
        """Build index for quick license lookup."""
        self._license_index = {}
        
        # Handle dict format
        if isinstance(self._licenses, dict):
            for license_id, license_info in self._licenses.items():
                # Index by ID (case-insensitive)
                self._license_index[license_id.lower()] = {
                    'licenseId': license_id,
                    **license_info
                }
                
                # Also index by name variations
                name = license_info.get('name', '')
                if name:
                    self._license_index[name.lower()] = {
                        'licenseId': license_id,
                        **license_info
                    }
    
    def get_license_info(self, license_id: str) -> Optional[Dict[str, Any]]:
        """
        Get license information by ID.
        
        Args:
            license_id: SPDX license ID
            
        Returns:
            License information or None
        """
        # First check aliases
        if self._bundled_data and 'aliases' in self._bundled_data:
            aliased_id = self._bundled_data['aliases'].get(license_id, license_id)
        else:
            aliased_id = license_id
        
        # Check bundled data directly
        if self._bundled_data and 'licenses' in self._bundled_data:
            licenses_dict = self._bundled_data['licenses']
            if aliased_id in licenses_dict:
                return {
                    'licenseId': aliased_id,
                    **licenses_dict[aliased_id]
                }
        
        # Fall back to index lookup
        return self._license_index.get(aliased_id.lower())
    
    def get_alias(self, license_name: str) -> Optional[str]:
        """
        Get canonical SPDX ID for a license alias.
        
        Args:
            license_name: License name or alias
            
        Returns:
            Canonical SPDX ID or None
        """
        if self._bundled_data and 'aliases' in self._bundled_data:
            return self._bundled_data['aliases'].get(license_name)
    
    def _normalize_text(self, text: str) -> str:
        """
        Normalize text for comparison.
        Removes whitespace variations, punctuation, and case differences.
        """
        if not text:
            return ""
        
        # Remove extra whitespace first
        text = ' '.join(text.split())
        
        # Convert to lowercase
        normalized = text.lower()
        
        # Remove URLs
        normalized = re.sub(r'https?://[^\s]+', '', normalized)
        
        # Remove email addresses
        normalized = re.sub(r'\S+@\S+', '', normalized)
        
        # Remove common variable placeholders
        normalized = re.sub(r'\[year\]|\[yyyy\]|\[name of copyright owner\]|\[fullname\]', '', normalized)
        normalized = re.sub(r'<year>|<name of author>|<organization>', '', normalized)
        normalized = re.sub(r'\{year\}|\{fullname\}|\{email\}', '', normalized)
        
        # Remove punctuation except for essential ones
        normalized = re.sub(r'[^\w\s\-]', ' ', normalized)
        
        # Normalize whitespace
        normalized = re.sub(r'\s+', ' ', normalized)
        
        # Remove common copyright lines that vary
        normalized = re.sub(r'copyright.*?\d{4}.*?(?:\n|$)', '', normalized, flags=re.IGNORECASE)
        
        # Remove leading/trailing whitespace
        normalized = normalized.strip()
        
        return normalized
    
    def get_all_license_ids(self) -> List[str]:
        """
        Get all available SPDX license IDs.
        
        Returns:
            List of all SPDX license IDs
        """
        if self._bundled_data and 'licenses' in self._bundled_data:
            return list(self._bundled_data['licenses'].keys())
        
        # Fall back to getting from licenses dict
        if isinstance(self.licenses, dict):
            return list(self.licenses.keys())
        
        # Legacy format support
        license_ids = []
        for license_info in self.licenses.get('licenses', []):
            license_id = license_info.get('licenseId')
            if license_id:
                license_ids.append(license_id)
        return license_ids
    
    def get_license_text(self, license_id: str) -> Optional[str]:
        """
        Get license text for a specific license.
        
        Args:
            license_id: SPDX license ID
            
        Returns:
            License text or None
        """
        # Check memory cache
        if license_id in self._license_texts:
            return self._license_texts[license_id]
        
        # Check bundled data first
        if self._bundled_data and license_id in self._bundled_data.get("licenses", {}):
            bundled_license = self._bundled_data["licenses"][license_id]
            if "text" in bundled_license and bundled_license["text"]:
                text = bundled_license["text"]
                self._license_texts[license_id] = text
                return text
        
        # Check file cache
        text_file = self.license_texts_dir / f"{license_id}.txt"
        if text_file.exists():
            with open(text_file, 'r') as f:
                text = f.read()
                self._license_texts[license_id] = text
                return text
        
        # Download license details as last resort
        license_info = self.get_license_info(license_id)
        if not license_info:
            return None
        
        details_url = license_info.get('detailsUrl')
        if not details_url:
            return None
        
        try:
            logger.debug(f"Downloading license text for {license_id}")
            response = requests.get(details_url, timeout=self.config.network_timeout)
            response.raise_for_status()
            
            data = response.json()
            text = data.get('licenseText', '')
            
            # Cache the text
            if text:
                with open(text_file, 'w') as f:
                    f.write(text)
                self._license_texts[license_id] = text
                return text
        
        except Exception as e:
            logger.debug(f"Failed to download license text for {license_id}: {e}")
        
        return None
    
    
    def get_license_aliases(self) -> Dict[str, str]:
        """
        Get common license aliases mapped to SPDX IDs.
        
        Returns:
            Dictionary mapping aliases to SPDX IDs
        """
        aliases = dict(self.config.custom_aliases)
        
        # Add common variations
        for license_info in self.licenses.get('licenses', []):
            license_id = license_info.get('licenseId')
            if not license_id:
                continue
            
            # Add case variations
            aliases[license_id.lower()] = license_id
            aliases[license_id.upper()] = license_id
            
            # Add common variations
            if license_id == "Apache-2.0":
                aliases["Apache 2.0"] = license_id
                aliases["Apache License 2.0"] = license_id
                aliases["Apache Software License 2.0"] = license_id
                aliases["ASL 2.0"] = license_id
            elif license_id == "MIT":
                aliases["MIT License"] = license_id
                aliases["The MIT License"] = license_id
                aliases["Expat License"] = license_id
            elif license_id == "BSD-3-Clause":
                aliases["BSD"] = license_id
                aliases["BSD License"] = license_id
                aliases["BSD 3-Clause"] = license_id
                aliases["New BSD License"] = license_id
            elif license_id == "GPL-3.0":
                aliases["GPLv3"] = license_id
                aliases["GPL v3"] = license_id
                aliases["GNU GPLv3"] = license_id
            elif license_id == "LGPL-3.0":
                aliases["LGPLv3"] = license_id
                aliases["LGPL v3"] = license_id
                aliases["GNU LGPLv3"] = license_id
        
        return aliases
    
    def compute_text_hash(self, text: str, algorithm: str = 'sha256') -> str:
        """
        Compute hash of license text for comparison.
        
        Args:
            text: License text
            algorithm: Hash algorithm to use
            
        Returns:
            Hex digest of hash
        """
        # Normalize text for hashing
        normalized = self._normalize_text(text)
        
        if algorithm == 'sha256':
            hasher = hashlib.sha256()
        elif algorithm == 'md5':
            hasher = hashlib.md5()
        else:
            hasher = hashlib.sha256()
        
        hasher.update(normalized.encode('utf-8'))
        return hasher.hexdigest()
    
    def _load_license_hashes(self):
        """Load or compute hashes for all bundled licenses."""
        # First try to load from exact_hashes.json file
        exact_hash_file = Path(__file__).parent / 'exact_hashes.json'
        if exact_hash_file.exists():
            try:
                with open(exact_hash_file, 'r', encoding='utf-8') as f:
                    self._license_hashes = json.load(f)
                logger.debug(f"Loaded {len(self._license_hashes)} pre-computed exact hashes")
                return
            except Exception as e:
                logger.warning(f"Failed to load exact hashes: {e}")
        
        # Fall back to bundled data if available
        if self._bundled_data and 'license_hashes' in self._bundled_data:
            # Use pre-computed hashes if available
            self._license_hashes = self._bundled_data['license_hashes']
            logger.debug(f"Loaded {len(self._license_hashes)} pre-computed license hashes")
        else:
            # Compute hashes for all licenses
            self._compute_all_license_hashes()
    
    def _compute_all_license_hashes(self):
        """Compute SHA-256 and MD5 hashes for all licenses."""
        # This method is kept for backward compatibility but won't compute anything
        # since license texts aren't stored in bundled data.
        # Hashes are pre-computed and loaded from exact_hashes.json instead.
        self._license_hashes = {}
        logger.debug("Hash computation skipped - using pre-computed hashes from exact_hashes.json")
    
    def get_license_hash(self, license_id: str, algorithm: str = 'sha256') -> Optional[str]:
        """
        Get pre-computed hash for a license.
        
        Args:
            license_id: SPDX license ID
            algorithm: Hash algorithm ('sha256' or 'md5')
            
        Returns:
            Hash hex digest or None
        """
        if license_id in self._license_hashes:
            return self._license_hashes[license_id].get(algorithm)
        return None
    
    def find_license_by_hash(self, text_hash: str, algorithm: str = 'sha256') -> Optional[str]:
        """
        Find license ID by text hash.
        
        Args:
            text_hash: Hash hex digest to search for
            algorithm: Hash algorithm used
            
        Returns:
            License ID if found, None otherwise
        """
        for license_id, hashes in self._license_hashes.items():
            if hashes.get(algorithm) == text_hash:
                return license_id
        return None
    
