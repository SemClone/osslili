"""
Package acquisition module for downloading and extracting packages.
"""

import os
import logging
import tempfile
import shutil
import tarfile
import zipfile
from pathlib import Path
from typing import Optional, Tuple, List
from urllib.parse import urlparse

import requests
from packageurl import PackageURL

logger = logging.getLogger(__name__)


class PackageAcquisition:
    """Handle package downloading and extraction."""
    
    def __init__(self, config):
        """
        Initialize package acquisition handler.
        
        Args:
            config: Configuration object
        """
        self.config = config
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'semantic-copycat-oslili/0.1.0'
        })
    
    def resolve_purl_to_url(self, purl: PackageURL) -> Optional[str]:
        """
        Resolve a PackageURL to a download URL using purl2src.
        
        Args:
            purl: PackageURL object
            
        Returns:
            Download URL or None if resolution fails
        """
        try:
            # Import purl2src dynamically to handle optional dependency
            from purl2src import get_repo_url
            
            # Get repository URL
            repo_url = get_repo_url(str(purl))
            if repo_url:
                logger.debug(f"Resolved {purl} to {repo_url}")
                return repo_url
            
            # Fallback to direct registry URLs for common ecosystems
            return self._fallback_url_resolution(purl)
        
        except ImportError:
            logger.warning("purl2src not available, using fallback URL resolution")
            return self._fallback_url_resolution(purl)
        except Exception as e:
            logger.error(f"Error resolving purl {purl}: {e}")
            return self._fallback_url_resolution(purl)
    
    def _fallback_url_resolution(self, purl: PackageURL) -> Optional[str]:
        """
        Fallback URL resolution for common package ecosystems.
        
        Args:
            purl: PackageURL object
            
        Returns:
            Download URL or None
        """
        try:
            if purl.type == "pypi":
                # PyPI package
                return self._get_pypi_url(purl.name, purl.version)
            elif purl.type == "npm":
                # npm package
                return self._get_npm_url(purl.name, purl.version)
            elif purl.type == "gem":
                # RubyGems package
                return self._get_gem_url(purl.name, purl.version)
            elif purl.type == "maven":
                # Maven package
                return self._get_maven_url(purl.namespace, purl.name, purl.version)
            elif purl.type == "cargo":
                # Cargo/crates.io package
                return self._get_cargo_url(purl.name, purl.version)
            elif purl.type == "github":
                # GitHub repository
                return self._get_github_url(purl.namespace, purl.name, purl.version)
            else:
                logger.warning(f"Unsupported package type: {purl.type}")
                return None
        except Exception as e:
            logger.error(f"Fallback URL resolution failed for {purl}: {e}")
            return None
    
    def _get_pypi_url(self, name: str, version: Optional[str]) -> Optional[str]:
        """Get PyPI package download URL."""
        try:
            url = f"https://pypi.org/pypi/{name}/json"
            if version:
                url = f"https://pypi.org/pypi/{name}/{version}/json"
            
            response = self.session.get(url, timeout=self.config.network_timeout)
            response.raise_for_status()
            
            data = response.json()
            
            # Try to find sdist (source distribution)
            urls = data.get('urls', [])
            for url_info in urls:
                if url_info.get('packagetype') == 'sdist':
                    return url_info.get('url')
            
            # Fallback to any available URL
            if urls:
                return urls[0].get('url')
            
            return None
        except Exception as e:
            logger.error(f"Failed to get PyPI URL for {name}@{version}: {e}")
            return None
    
    def _get_npm_url(self, name: str, version: Optional[str]) -> Optional[str]:
        """Get npm package download URL."""
        try:
            url = f"https://registry.npmjs.org/{name}"
            response = self.session.get(url, timeout=self.config.network_timeout)
            response.raise_for_status()
            
            data = response.json()
            
            if version and 'versions' in data and version in data['versions']:
                dist = data['versions'][version].get('dist', {})
                return dist.get('tarball')
            elif 'dist-tags' in data and 'latest' in data['dist-tags']:
                latest = data['dist-tags']['latest']
                if 'versions' in data and latest in data['versions']:
                    dist = data['versions'][latest].get('dist', {})
                    return dist.get('tarball')
            
            return None
        except Exception as e:
            logger.error(f"Failed to get npm URL for {name}@{version}: {e}")
            return None
    
    def _get_gem_url(self, name: str, version: Optional[str]) -> Optional[str]:
        """Get RubyGems package download URL."""
        if version:
            return f"https://rubygems.org/downloads/{name}-{version}.gem"
        return f"https://rubygems.org/downloads/{name}.gem"
    
    def _get_maven_url(self, namespace: str, name: str, version: Optional[str]) -> Optional[str]:
        """Get Maven package download URL."""
        if not namespace or not version:
            return None
        
        group_path = namespace.replace('.', '/')
        return f"https://repo1.maven.org/maven2/{group_path}/{name}/{version}/{name}-{version}-sources.jar"
    
    def _get_cargo_url(self, name: str, version: Optional[str]) -> Optional[str]:
        """Get Cargo/crates.io package download URL."""
        if version:
            return f"https://crates.io/api/v1/crates/{name}/{version}/download"
        return None
    
    def _get_github_url(self, namespace: str, name: str, version: Optional[str]) -> Optional[str]:
        """Get GitHub repository archive URL."""
        if not namespace:
            return None
        
        if version:
            # Try tag/release
            return f"https://github.com/{namespace}/{name}/archive/refs/tags/{version}.tar.gz"
        else:
            # Default branch
            return f"https://github.com/{namespace}/{name}/archive/refs/heads/main.tar.gz"
    
    def download_package(self, url: str, target_dir: Optional[Path] = None) -> Optional[Path]:
        """
        Download a package from URL.
        
        Args:
            url: Download URL
            target_dir: Optional target directory
            
        Returns:
            Path to downloaded file or None if failed
        """
        try:
            if not target_dir:
                target_dir = Path(tempfile.mkdtemp(prefix="oslili_"))
            
            # Parse filename from URL
            parsed = urlparse(url)
            filename = os.path.basename(parsed.path) or "package.tar.gz"
            
            # Download file
            logger.info(f"Downloading {url}")
            response = self.session.get(
                url,
                stream=True,
                timeout=self.config.network_timeout,
                allow_redirects=True
            )
            response.raise_for_status()
            
            # Save to file
            file_path = target_dir / filename
            with open(file_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
            logger.debug(f"Downloaded to {file_path}")
            return file_path
        
        except Exception as e:
            logger.error(f"Failed to download {url}: {e}")
            return None
    
    def extract_archive(
        self,
        archive_path: Path,
        target_dir: Optional[Path] = None,
        max_depth: Optional[int] = None
    ) -> Optional[Path]:
        """
        Extract an archive file recursively.
        
        Args:
            archive_path: Path to archive file
            target_dir: Optional extraction directory
            max_depth: Maximum extraction depth
            
        Returns:
            Path to extraction directory or None if failed
        """
        if max_depth is None:
            max_depth = self.config.max_extraction_depth
        
        try:
            if not target_dir:
                target_dir = Path(tempfile.mkdtemp(prefix="oslili_extract_"))
            
            # Extract based on file type
            extracted = self._extract_single_archive(archive_path, target_dir)
            if not extracted:
                return None
            
            # Recursively extract nested archives
            if max_depth > 1:
                self._extract_nested_archives(target_dir, max_depth - 1)
            
            return target_dir
        
        except Exception as e:
            logger.error(f"Failed to extract {archive_path}: {e}")
            return None
    
    def _extract_single_archive(self, archive_path: Path, target_dir: Path) -> bool:
        """
        Extract a single archive file.
        
        Args:
            archive_path: Path to archive
            target_dir: Extraction directory
            
        Returns:
            True if successful
        """
        try:
            archive_str = str(archive_path).lower()
            
            # Try tar-based formats
            if any(archive_str.endswith(ext) for ext in ['.tar', '.tar.gz', '.tgz', '.tar.bz2', '.tar.xz']):
                with tarfile.open(archive_path, 'r:*') as tar:
                    # Security check for path traversal
                    for member in tar.getmembers():
                        if os.path.isabs(member.name) or ".." in member.name:
                            logger.warning(f"Skipping potentially unsafe path: {member.name}")
                            continue
                    tar.extractall(target_dir)
                return True
            
            # Try zip format
            elif archive_str.endswith('.zip'):
                with zipfile.ZipFile(archive_path, 'r') as zip_file:
                    # Security check for path traversal
                    for name in zip_file.namelist():
                        if os.path.isabs(name) or ".." in name:
                            logger.warning(f"Skipping potentially unsafe path: {name}")
                            continue
                    zip_file.extractall(target_dir)
                return True
            
            # Try gem format (tar inside tar)
            elif archive_str.endswith('.gem'):
                # First extract outer tar
                temp_dir = target_dir / '_gem_temp'
                temp_dir.mkdir(exist_ok=True)
                
                with tarfile.open(archive_path, 'r:*') as tar:
                    tar.extractall(temp_dir)
                
                # Then extract data.tar.gz if it exists
                data_tar = temp_dir / 'data.tar.gz'
                if data_tar.exists():
                    with tarfile.open(data_tar, 'r:gz') as tar:
                        tar.extractall(target_dir)
                
                # Clean up temp directory
                shutil.rmtree(temp_dir, ignore_errors=True)
                return True
            
            else:
                logger.warning(f"Unknown archive format: {archive_path}")
                return False
        
        except Exception as e:
            logger.error(f"Failed to extract {archive_path}: {e}")
            return False
    
    def _extract_nested_archives(self, directory: Path, remaining_depth: int):
        """
        Recursively extract nested archives.
        
        Args:
            directory: Directory to search for archives
            remaining_depth: Remaining extraction depth
        """
        if remaining_depth <= 0:
            return
        
        archive_extensions = [
            '.tar', '.tar.gz', '.tgz', '.tar.bz2', '.tar.xz',
            '.zip', '.gem', '.jar', '.war', '.ear'
        ]
        
        for root, _, files in os.walk(directory):
            for file in files:
                file_path = Path(root) / file
                file_str = str(file).lower()
                
                if any(file_str.endswith(ext) for ext in archive_extensions):
                    logger.debug(f"Extracting nested archive: {file_path}")
                    
                    # Create extraction directory next to archive
                    extract_dir = file_path.parent / f"{file_path.stem}_extracted"
                    extract_dir.mkdir(exist_ok=True)
                    
                    # Extract archive
                    if self._extract_single_archive(file_path, extract_dir):
                        # Recursively check for more nested archives
                        self._extract_nested_archives(extract_dir, remaining_depth - 1)
    
    def acquire_and_extract_package(self, purl: PackageURL) -> Optional[Path]:
        """
        Complete pipeline to acquire and extract a package.
        
        Args:
            purl: PackageURL object
            
        Returns:
            Path to extracted package directory or None
        """
        try:
            # Resolve purl to download URL
            download_url = self.resolve_purl_to_url(purl)
            if not download_url:
                logger.error(f"Could not resolve download URL for {purl}")
                return None
            
            # Create temporary directory for this package
            temp_dir = Path(tempfile.mkdtemp(prefix=f"oslili_{purl.name}_"))
            
            # Download package
            downloaded_file = self.download_package(download_url, temp_dir)
            if not downloaded_file:
                shutil.rmtree(temp_dir, ignore_errors=True)
                return None
            
            # Extract package
            extract_dir = temp_dir / "extracted"
            extract_dir.mkdir()
            
            extracted = self.extract_archive(downloaded_file, extract_dir)
            if not extracted:
                shutil.rmtree(temp_dir, ignore_errors=True)
                return None
            
            return extracted
        
        except Exception as e:
            logger.error(f"Failed to acquire package {purl}: {e}")
            return None
    
    def cleanup_temp_directory(self, directory: Path):
        """
        Clean up temporary directory.
        
        Args:
            directory: Directory to remove
        """
        try:
            if directory and directory.exists():
                shutil.rmtree(directory, ignore_errors=True)
                logger.debug(f"Cleaned up {directory}")
        except Exception as e:
            logger.warning(f"Failed to clean up {directory}: {e}")