"""
External data source integration for license and copyright information.
"""

import logging
import json
from typing import Optional, Dict, Any, List
from urllib.parse import quote

import requests
from packageurl import PackageURL

from ..core.models import DetectedLicense, CopyrightInfo

logger = logging.getLogger(__name__)


class ExternalDataSources:
    """Fetch license and copyright data from external sources."""
    
    def __init__(self, config):
        """
        Initialize external data sources.
        
        Args:
            config: Configuration object
        """
        self.config = config
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'semantic-copycat-oslili/0.1.0',
            'Accept': 'application/json'
        })
    
    def fetch_from_clearlydefined(self, purl: PackageURL) -> Dict[str, Any]:
        """
        Fetch license and copyright data from ClearlyDefined.
        
        Args:
            purl: PackageURL object
            
        Returns:
            Dictionary with license and copyright information
        """
        try:
            # Build ClearlyDefined coordinates
            coordinates = self._build_clearlydefined_coordinates(purl)
            if not coordinates:
                return {}
            
            # Fetch definition
            url = f"{self.config.clearlydefined_api_url}/definitions/{coordinates}"
            
            logger.debug(f"Fetching from ClearlyDefined: {url}")
            response = self.session.get(url, timeout=self.config.network_timeout)
            
            if response.status_code == 404:
                logger.debug(f"No ClearlyDefined data for {coordinates}")
                return {}
            
            response.raise_for_status()
            data = response.json()
            
            result = {
                'licenses': [],
                'copyrights': []
            }
            
            # Extract licensed information
            if 'licensed' in data:
                licensed = data['licensed']
                
                # Declared license
                if 'declared' in licensed:
                    declared = licensed['declared']
                    if declared and declared != 'NOASSERTION':
                        result['licenses'].append(DetectedLicense(
                            spdx_id=declared,
                            name=declared,
                            confidence=0.95,
                            detection_method='clearlydefined-declared',
                            source_file='ClearlyDefined API'
                        ))
                
                # Discovered licenses
                if 'facets' in licensed:
                    facets = licensed['facets']
                    if 'core' in facets and 'discovered' in facets['core']:
                        discovered = facets['core']['discovered']
                        if 'expressions' in discovered:
                            for expr in discovered['expressions'][:3]:  # Limit to top 3
                                if expr and expr != 'NOASSERTION':
                                    result['licenses'].append(DetectedLicense(
                                        spdx_id=expr,
                                        name=expr,
                                        confidence=0.85,
                                        detection_method='clearlydefined-discovered',
                                        source_file='ClearlyDefined API'
                                    ))
                
                # Copyright attributions
                if 'facets' in licensed:
                    facets = licensed['facets']
                    if 'core' in facets and 'attribution' in facets['core']:
                        attribution = facets['core']['attribution']
                        if 'parties' in attribution:
                            for party in attribution['parties'][:5]:  # Limit to top 5
                                if party:
                                    # Parse copyright statement
                                    logger.debug(f"ClearlyDefined copyright party: '{party}'")
                                    copyright_info = self._parse_copyright_statement(party)
                                    if copyright_info:
                                        copyright_info.source_file = 'ClearlyDefined API'
                                        logger.debug(f"ClearlyDefined parsed copyright: '{copyright_info.holder}'")
                                        result['copyrights'].append(copyright_info)
                                    else:
                                        logger.debug(f"ClearlyDefined rejected copyright: '{party}'")
            
            return result
        
        except requests.RequestException as e:
            logger.warning(f"Error fetching from ClearlyDefined: {e}")
            return {}
        except Exception as e:
            logger.error(f"Unexpected error with ClearlyDefined: {e}")
            return {}
    
    def _build_clearlydefined_coordinates(self, purl: PackageURL) -> Optional[str]:
        """
        Build ClearlyDefined coordinates from PackageURL.
        
        Args:
            purl: PackageURL object
            
        Returns:
            ClearlyDefined coordinates string or None
        """
        # Map purl types to ClearlyDefined types
        type_mapping = {
            'pypi': 'pypi/pypi',
            'npm': 'npm/npmjs',
            'gem': 'gem/rubygems',
            'maven': 'maven/mavencentral',
            'nuget': 'nuget/nuget',
            'cargo': 'crate/cratesio',
            'github': 'git/github',
        }
        
        cd_type = type_mapping.get(purl.type)
        if not cd_type:
            return None
        
        # Build coordinates
        if purl.type == 'maven' and purl.namespace:
            # Maven uses namespace/name
            name = f"{purl.namespace}/{purl.name}"
        elif purl.type == 'github' and purl.namespace:
            # GitHub uses namespace/name
            name = f"{purl.namespace}/{purl.name}"
        elif purl.namespace and purl.type == 'npm':
            # Scoped npm packages
            name = f"@{purl.namespace}/{purl.name}"
        else:
            name = purl.name
        
        # Add version if available
        if purl.version:
            return f"{cd_type}/-/{name}/{purl.version}"
        else:
            return f"{cd_type}/-/{name}"
    
    def _parse_copyright_statement(self, statement: str) -> Optional[CopyrightInfo]:
        """
        Parse a copyright statement into CopyrightInfo.
        
        Args:
            statement: Copyright statement string
            
        Returns:
            CopyrightInfo object or None
        """
        import re
        
        # Try to extract holder from copyright statement
        patterns = [
            r'Copyright\s*(?:\(c\)|©)?\s*(?:\d{4}(?:\s*[-,]\s*\d{4})*\s*)?(?:by\s+)?(.+)',
            r'©\s*(?:\d{4}(?:\s*[-,]\s*\d{4})*\s*)?(.+)',
            r'\(C\)\s*Copyright\s*(?:\d{4}(?:\s*[-,]\s*\d{4})*\s*)?(?:by\s+)?(.+)',
            r'\(C\)\s*(?:\d{4}(?:\s*[-,]\s*\d{4})*\s*)?(?:by\s+)?(.+)',
        ]
        
        holder = None
        for pattern in patterns:
            match = re.search(pattern, statement, re.IGNORECASE)
            if match:
                holder = match.group(1).strip()
                break
        
        if not holder:
            holder = statement.strip()
        
        # Clean up holder - remove common suffixes
        holder = re.sub(r'\s*[,.]?\s*All rights reserved\.?$', '', holder, flags=re.IGNORECASE)
        holder = re.sub(r'\s*[.,;]+$', '', holder)  # Remove trailing punctuation
        holder = holder.strip()
        
        # Remove "by" prefix if it got through
        if holder.lower().startswith('by '):
            holder = holder[3:].strip()
        
        # Validate holder - reject invalid patterns
        if len(holder) < 3:
            return None
        
        # Check for URL/domain patterns that indicate bad data
        invalid_patterns = [
            r'https?://',  # URLs
            r'ftp://',  # FTP URLs
            r'\.invalid',  # Invalid domains
            r'^localhost',  # Localhost
            r'domain\.',  # domain.something
            r'<[^>]*>',  # HTML tags
            r'^by\s+http',  # "by http://..."
        ]
        
        for pattern in invalid_patterns:
            if re.search(pattern, holder, re.IGNORECASE):
                logger.debug(f"Rejecting invalid copyright holder: '{holder}'")
                return None
        
        # Additional validation - must contain at least one letter
        if not any(c.isalpha() for c in holder):
            return None
        
        return CopyrightInfo(
            holder=holder,
            statement=statement,
            confidence=0.8
        )
    
    def fetch_from_pypi(self, purl: PackageURL) -> Dict[str, Any]:
        """
        Fetch metadata from PyPI.
        
        Args:
            purl: PackageURL object (must be type 'pypi')
            
        Returns:
            Dictionary with license and copyright information
        """
        if purl.type != 'pypi':
            return {}
        
        try:
            url = f"{self.config.pypi_api_url}/{purl.name}/json"
            if purl.version:
                url = f"{self.config.pypi_api_url}/{purl.name}/{purl.version}/json"
            
            logger.debug(f"Fetching from PyPI: {url}")
            response = self.session.get(url, timeout=self.config.network_timeout)
            
            if response.status_code == 404:
                logger.debug(f"Package not found on PyPI: {purl.name}")
                return {}
            
            response.raise_for_status()
            data = response.json()
            
            result = {
                'licenses': [],
                'copyrights': []
            }
            
            # Get package info
            info = data.get('info', {})
            
            # Extract license
            license_str = info.get('license')
            if license_str and license_str not in ['UNKNOWN', '', 'None']:
                # Try to normalize to SPDX
                from ..data.spdx_licenses import SPDXLicenseData
                spdx_data = SPDXLicenseData(self.config)
                aliases = spdx_data.get_license_aliases()
                
                spdx_id = aliases.get(license_str, license_str)
                
                result['licenses'].append(DetectedLicense(
                    spdx_id=spdx_id,
                    name=license_str,
                    confidence=0.9,
                    detection_method='pypi-metadata',
                    source_file='PyPI API'
                ))
            
            # Extract author/maintainer as copyright
            author = info.get('author')
            if author and author not in ['UNKNOWN', '', 'None']:
                result['copyrights'].append(CopyrightInfo(
                    holder=author,
                    statement=f"Copyright {author}",
                    source_file='PyPI API',
                    confidence=0.85
                ))
            
            maintainer = info.get('maintainer')
            if maintainer and maintainer not in ['UNKNOWN', '', 'None'] and maintainer != author:
                result['copyrights'].append(CopyrightInfo(
                    holder=maintainer,
                    statement=f"Copyright {maintainer}",
                    source_file='PyPI API',
                    confidence=0.75
                ))
            
            return result
        
        except requests.RequestException as e:
            logger.warning(f"Error fetching from PyPI: {e}")
            return {}
        except Exception as e:
            logger.error(f"Unexpected error with PyPI: {e}")
            return {}
    
    def fetch_from_npm(self, purl: PackageURL) -> Dict[str, Any]:
        """
        Fetch metadata from npm registry.
        
        Args:
            purl: PackageURL object (must be type 'npm')
            
        Returns:
            Dictionary with license and copyright information
        """
        if purl.type != 'npm':
            return {}
        
        try:
            # Handle scoped packages
            if purl.namespace:
                package_name = f"@{purl.namespace}/{purl.name}"
            else:
                package_name = purl.name
            
            url = f"{self.config.npm_api_url}/{quote(package_name)}"
            
            logger.debug(f"Fetching from npm: {url}")
            response = self.session.get(url, timeout=self.config.network_timeout)
            
            if response.status_code == 404:
                logger.debug(f"Package not found on npm: {package_name}")
                return {}
            
            response.raise_for_status()
            data = response.json()
            
            result = {
                'licenses': [],
                'copyrights': []
            }
            
            # Get version-specific data
            version_data = None
            if purl.version and 'versions' in data:
                version_data = data['versions'].get(purl.version)
            elif 'dist-tags' in data and 'latest' in data['dist-tags']:
                latest = data['dist-tags']['latest']
                if 'versions' in data:
                    version_data = data['versions'].get(latest)
            
            if not version_data:
                version_data = data
            
            # Extract license
            license_info = version_data.get('license')
            if license_info:
                if isinstance(license_info, str):
                    license_str = license_info
                elif isinstance(license_info, dict):
                    license_str = license_info.get('type', '')
                else:
                    license_str = None
                
                if license_str:
                    # Try to normalize to SPDX
                    from ..data.spdx_licenses import SPDXLicenseData
                    spdx_data = SPDXLicenseData(self.config)
                    aliases = spdx_data.get_license_aliases()
                    
                    spdx_id = aliases.get(license_str, license_str)
                    
                    result['licenses'].append(DetectedLicense(
                        spdx_id=spdx_id,
                        name=license_str,
                        confidence=0.9,
                        detection_method='npm-metadata',
                        source_file='npm Registry API'
                    ))
            
            # Extract author/contributors as copyright
            author = version_data.get('author')
            if author:
                if isinstance(author, str):
                    holder = author
                elif isinstance(author, dict):
                    holder = author.get('name', '')
                else:
                    holder = None
                
                if holder:
                    result['copyrights'].append(CopyrightInfo(
                        holder=holder,
                        statement=f"Copyright {holder}",
                        source_file='npm Registry API',
                        confidence=0.85
                    ))
            
            # Contributors
            contributors = version_data.get('contributors', [])
            for contributor in contributors[:3]:  # Limit to first 3
                if isinstance(contributor, str):
                    holder = contributor
                elif isinstance(contributor, dict):
                    holder = contributor.get('name', '')
                else:
                    continue
                
                if holder:
                    result['copyrights'].append(CopyrightInfo(
                        holder=holder,
                        statement=f"Copyright {holder}",
                        source_file='npm Registry API',
                        confidence=0.7
                    ))
            
            return result
        
        except requests.RequestException as e:
            logger.warning(f"Error fetching from npm: {e}")
            return {}
        except Exception as e:
            logger.error(f"Unexpected error with npm: {e}")
            return {}
    
    def fetch_all_sources(self, purl: PackageURL) -> Dict[str, Any]:
        """
        Fetch data from all available external sources.
        
        Args:
            purl: PackageURL object
            
        Returns:
            Combined dictionary with license and copyright information
        """
        combined = {
            'licenses': [],
            'copyrights': []
        }
        
        # Fetch from ClearlyDefined
        cd_data = self.fetch_from_clearlydefined(purl)
        combined['licenses'].extend(cd_data.get('licenses', []))
        combined['copyrights'].extend(cd_data.get('copyrights', []))
        
        # Fetch from package-specific registries
        if purl.type == 'pypi':
            pypi_data = self.fetch_from_pypi(purl)
            combined['licenses'].extend(pypi_data.get('licenses', []))
            combined['copyrights'].extend(pypi_data.get('copyrights', []))
        elif purl.type == 'npm':
            npm_data = self.fetch_from_npm(purl)
            combined['licenses'].extend(npm_data.get('licenses', []))
            combined['copyrights'].extend(npm_data.get('copyrights', []))
        
        # Deduplicate licenses by SPDX ID
        seen_licenses = set()
        unique_licenses = []
        for license in combined['licenses']:
            if license.spdx_id not in seen_licenses:
                seen_licenses.add(license.spdx_id)
                unique_licenses.append(license)
        combined['licenses'] = unique_licenses
        
        # Deduplicate copyrights by holder
        seen_holders = set()
        unique_copyrights = []
        for copyright in combined['copyrights']:
            if copyright.holder not in seen_holders:
                seen_holders.add(copyright.holder)
                unique_copyrights.append(copyright)
        combined['copyrights'] = unique_copyrights
        
        return combined