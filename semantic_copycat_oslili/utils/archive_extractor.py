"""
Archive extraction utilities for processing compressed files.
"""

import os
import zipfile
import tarfile
import tempfile
import shutil
import logging
from pathlib import Path
from typing import Optional, List, Set

logger = logging.getLogger(__name__)


class ArchiveExtractor:
    """Extract and process archive files recursively."""
    
    SUPPORTED_ARCHIVES = {
        '.zip', '.tar', '.tar.gz', '.tgz', '.tar.bz2', '.tbz2', 
        '.tar.xz', '.txz', '.gz', '.bz2', '.xz', '.whl', '.egg',
        '.jar', '.war', '.ear',  # Java archives (ZIP-based)
        '.nupkg',  # .NET packages (ZIP-based)
        '.gem',  # Ruby gems (TAR-based)
        '.crate',  # Rust crates (TAR-based)
    }
    
    def __init__(self, max_depth: int = 10, temp_dir: Optional[str] = None):
        """
        Initialize archive extractor.
        
        Args:
            max_depth: Maximum extraction depth for nested archives
            temp_dir: Temporary directory for extraction (auto-created if None)
        """
        self.max_depth = max_depth
        self.temp_dir = temp_dir or tempfile.mkdtemp(prefix='oslili_extract_')
        self.extracted_paths: Set[Path] = set()
        
    def __enter__(self):
        """Context manager entry."""
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - cleanup temp files."""
        self.cleanup()
        return False  # Don't suppress exceptions
        
    def cleanup(self):
        """Clean up temporary extracted files."""
        if self.temp_dir and os.path.exists(self.temp_dir):
            try:
                shutil.rmtree(self.temp_dir)
                logger.debug(f"Cleaned up temp directory: {self.temp_dir}")
            except Exception as e:
                logger.warning(f"Failed to cleanup temp directory {self.temp_dir}: {e}")
    
    def is_archive(self, file_path: Path) -> bool:
        """
        Check if a file is a supported archive.
        
        Args:
            file_path: Path to check
            
        Returns:
            True if file is a supported archive
        """
        # Check by extension
        for ext in self.SUPPORTED_ARCHIVES:
            if file_path.name.lower().endswith(ext):
                return True
        
        # Check by magic bytes for zip files
        try:
            with open(file_path, 'rb') as f:
                magic = f.read(4)
                if magic[:2] == b'PK':  # ZIP file signature
                    return True
        except:
            pass
            
        return False
    
    def extract_archive(self, archive_path: Path, depth: int = 0) -> Optional[Path]:
        """
        Extract an archive file recursively.
        
        Args:
            archive_path: Path to archive file
            depth: Current extraction depth
            
        Returns:
            Path to extracted directory or None if extraction failed
        """
        if depth >= self.max_depth:
            logger.warning(f"Max extraction depth {self.max_depth} reached for {archive_path}")
            return None
            
        # Create extraction directory
        extract_dir = Path(self.temp_dir) / f"extract_{depth}_{archive_path.stem}"
        extract_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            # Try to extract based on file type
            name_lower = archive_path.name.lower()
            
            # Check for ZIP-based formats first
            if (name_lower.endswith('.zip') or name_lower.endswith('.jar') or 
                name_lower.endswith('.war') or name_lower.endswith('.ear') or 
                name_lower.endswith('.nupkg') or name_lower.endswith('.whl') or
                name_lower.endswith('.egg')):
                if self._extract_zip(archive_path, extract_dir):
                    logger.debug(f"Extracted ZIP-based archive: {archive_path}")
                else:
                    logger.warning(f"Failed to extract ZIP-based archive: {archive_path}")
                    return None
            # Then check for TAR-based formats
            elif (name_lower.endswith('.tar') or name_lower.endswith('.tar.gz') or
                  name_lower.endswith('.tgz') or name_lower.endswith('.tar.bz2') or
                  name_lower.endswith('.tbz2') or name_lower.endswith('.tar.xz') or
                  name_lower.endswith('.txz') or name_lower.endswith('.gem') or
                  name_lower.endswith('.crate')):
                if self._extract_tar(archive_path, extract_dir):
                    logger.debug(f"Extracted TAR-based archive: {archive_path}")
                else:
                    logger.warning(f"Failed to extract TAR-based archive: {archive_path}")
                    return None
            else:
                # Fallback: try both methods
                if self._extract_zip(archive_path, extract_dir):
                    logger.debug(f"Extracted ZIP archive: {archive_path}")
                elif self._extract_tar(archive_path, extract_dir):
                    logger.debug(f"Extracted TAR archive: {archive_path}")
                else:
                    logger.warning(f"Unsupported archive format: {archive_path}")
                    return None
                
            self.extracted_paths.add(extract_dir)
            
            # Look for nested archives
            if depth + 1 < self.max_depth:
                for root, dirs, files in os.walk(extract_dir):
                    for file in files:
                        file_path = Path(root) / file
                        if self.is_archive(file_path):
                            logger.debug(f"Found nested archive: {file_path}")
                            nested_dir = self.extract_archive(file_path, depth + 1)
                            if nested_dir:
                                # For Ruby gems, extract data.tar.gz contents to parent directory
                                if archive_path.name.endswith('.gem') and file == 'data.tar.gz':
                                    # Move contents up to gem extract directory
                                    for item in nested_dir.iterdir():
                                        dest = extract_dir / item.name
                                        if item.is_dir():
                                            shutil.copytree(item, dest, dirs_exist_ok=True)
                                        else:
                                            shutil.copy2(item, dest)
            
            return extract_dir
            
        except Exception as e:
            logger.error(f"Failed to extract {archive_path}: {e}")
            return None
    
    def _extract_zip(self, archive_path: Path, extract_dir: Path) -> bool:
        """
        Extract a ZIP archive (including JAR, NUPKG, etc).
        
        Args:
            archive_path: Path to ZIP file
            extract_dir: Directory to extract to
            
        Returns:
            True if extraction successful
        """
        try:
            # JAR, WAR, EAR, NUPKG, and WHL files are all ZIP-based
            with zipfile.ZipFile(archive_path, 'r') as zip_ref:
                # Check for zip bomb
                total_size = sum(zinfo.file_size for zinfo in zip_ref.filelist)
                compressed_size = sum(zinfo.compress_size for zinfo in zip_ref.filelist)
                
                # Reject if uncompressed size is more than 100x compressed size
                if compressed_size > 0 and total_size / compressed_size > 100:
                    logger.warning(f"Potential zip bomb detected in {archive_path}")
                    return False
                    
                # Reject if total size > 1GB
                if total_size > 1024 * 1024 * 1024:
                    logger.warning(f"Archive too large to extract: {archive_path} ({total_size} bytes)")
                    return False
                
                zip_ref.extractall(extract_dir)
                return True
        except (zipfile.BadZipFile, Exception):
            return False
    
    def _extract_tar(self, archive_path: Path, extract_dir: Path) -> bool:
        """
        Extract a TAR archive (including compressed variants).
        
        Args:
            archive_path: Path to TAR file
            extract_dir: Directory to extract to
            
        Returns:
            True if extraction successful
        """
        try:
            # Determine mode based on extension
            name_lower = archive_path.name.lower()
            if name_lower.endswith('.tar.gz') or name_lower.endswith('.tgz'):
                mode = 'r:gz'
            elif name_lower.endswith('.tar.bz2') or name_lower.endswith('.tbz2'):
                mode = 'r:bz2'
            elif name_lower.endswith('.tar.xz') or name_lower.endswith('.txz'):
                mode = 'r:xz'
            elif name_lower.endswith('.tar'):
                mode = 'r'
            elif name_lower.endswith('.gem'):
                # Ruby gems are plain TAR archives
                mode = 'r'
            elif name_lower.endswith('.crate'):
                # Rust crates are gzipped TAR archives
                mode = 'r:gz'
            else:
                return False
            
            with tarfile.open(archive_path, mode) as tar_ref:
                # Check for tar bomb
                total_size = sum(member.size for member in tar_ref.getmembers())
                
                # Reject if total size > 1GB
                if total_size > 1024 * 1024 * 1024:
                    logger.warning(f"Archive too large to extract: {archive_path} ({total_size} bytes)")
                    return False
                
                # Extract with safety checks
                for member in tar_ref.getmembers():
                    # Prevent path traversal attacks
                    if member.name.startswith('..') or member.name.startswith('/'):
                        logger.warning(f"Skipping unsafe path in archive: {member.name}")
                        continue
                    tar_ref.extract(member, extract_dir)
                    
                return True
        except (tarfile.TarError, Exception):
            return False
    
    def get_extracted_paths(self) -> List[Path]:
        """
        Get all extracted directory paths.
        
        Returns:
            List of paths to extracted directories
        """
        return list(self.extracted_paths)