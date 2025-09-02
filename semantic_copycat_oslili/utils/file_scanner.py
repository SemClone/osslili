"""
Safe file scanner with depth limiting and symlink protection.
"""

import os
import logging
from pathlib import Path
from typing import Iterator, Set, Optional

logger = logging.getLogger(__name__)


class SafeFileScanner:
    """Scanner that safely traverses directories with depth and symlink protection."""
    
    def __init__(self, max_depth: int = 10, follow_symlinks: bool = False):
        """
        Initialize the scanner.
        
        Args:
            max_depth: Maximum recursion depth (-1 for unlimited)
            follow_symlinks: Whether to follow symbolic links
        """
        self.max_depth = max_depth
        self.follow_symlinks = follow_symlinks
        self.visited_inodes: Set[tuple] = set()
        
    def scan_directory(self, directory: Path, pattern: str = '*') -> Iterator[Path]:
        """
        Safely scan a directory with depth and symlink protection.
        
        Args:
            directory: Directory to scan
            pattern: Glob pattern to match
            
        Yields:
            Matching file paths
        """
        # Clear visited inodes for each new scan to avoid false positives
        self.visited_inodes.clear()
        
        try:
            # Get the real path to handle symlinks
            real_dir = directory.resolve()
            
            # Track visited inodes to prevent loops within this scan
            stat = real_dir.stat()
            inode = (stat.st_dev, stat.st_ino)
            
            if inode in self.visited_inodes:
                logger.warning(f"Symlink loop detected at {directory}, skipping")
                return
                
            self.visited_inodes.add(inode)
            
            # Use os.walk for better control over depth
            for root, dirs, files in self._walk_with_depth(real_dir, pattern):
                for file in files:
                    file_path = Path(root) / file
                    
                    # Skip symlinks if not following them
                    if file_path.is_symlink() and not self.follow_symlinks:
                        logger.debug(f"Skipping symlink: {file_path}")
                        continue
                    
                    # Additional safety check for file
                    if self._is_safe_file(file_path):
                        yield file_path
                        
        except (OSError, PermissionError) as e:
            logger.warning(f"Cannot access directory {directory}: {e}")
            
    def _walk_with_depth(self, directory: Path, pattern: str) -> Iterator[tuple]:
        """
        Walk directory tree with depth limiting.
        
        Args:
            directory: Starting directory
            pattern: File pattern to match
            
        Yields:
            (root, dirs, files) tuples
        """
        base_depth = len(directory.parts)
        
        for root, dirs, files in os.walk(directory, followlinks=self.follow_symlinks):
            current_path = Path(root)
            current_depth = len(current_path.parts) - base_depth
            
            # Check depth limit
            if self.max_depth >= 0 and current_depth >= self.max_depth:
                dirs.clear()  # Don't recurse deeper
                logger.debug(f"Reached max depth at {root}")
            else:
                # Filter out hidden directories and common build/cache dirs
                dirs[:] = [d for d in dirs if not self._should_skip_dir(d)]
                
            # Filter files by pattern
            if pattern != '*':
                import fnmatch
                files = [f for f in files if fnmatch.fnmatch(f, pattern)]
                
            yield root, dirs, files
            
    def _should_skip_dir(self, dirname: str) -> bool:
        """
        Check if a directory should be skipped.
        
        Args:
            dirname: Directory name
            
        Returns:
            True if directory should be skipped
        """
        skip_dirs = {
            '.git', '.svn', '.hg', '.bzr',  # Version control
            '__pycache__', '.pytest_cache', '.mypy_cache',  # Python caches
            'node_modules', 'bower_components',  # JavaScript
            'target', 'build', 'dist', 'out',  # Build directories
            '.idea', '.vscode', '.eclipse',  # IDE directories
            'venv', 'env', '.env', 'virtualenv',  # Virtual environments
        }
        
        # Skip hidden directories (starting with .)
        if dirname.startswith('.') and dirname not in {'.github', '.gitlab'}:
            return True
            
        # Skip known cache/build directories
        return dirname.lower() in skip_dirs
        
    def _is_safe_file(self, file_path: Path) -> bool:
        """
        Check if a file is safe to process.
        
        Args:
            file_path: File to check
            
        Returns:
            True if file is safe to process
        """
        try:
            # Check if it's a regular file
            if not file_path.is_file():
                return False
                
            # Check for circular symlinks
            if file_path.is_symlink():
                try:
                    # Resolve will raise if there's a circular reference
                    resolved = file_path.resolve(strict=True)
                    
                    # Check if we've seen this inode before
                    stat = resolved.stat()
                    inode = (stat.st_dev, stat.st_ino)
                    
                    if inode in self.visited_inodes:
                        logger.warning(f"Circular symlink detected: {file_path}")
                        return False
                        
                except (OSError, RuntimeError) as e:
                    logger.warning(f"Cannot resolve symlink {file_path}: {e}")
                    return False
                    
            # Check file size (skip files > 100MB)
            if file_path.stat().st_size > 100 * 1024 * 1024:
                logger.debug(f"Skipping large file (>100MB): {file_path}")
                return False
                
            return True
            
        except (OSError, PermissionError) as e:
            logger.debug(f"Cannot access file {file_path}: {e}")
            return False