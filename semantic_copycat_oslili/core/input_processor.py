"""
Input processing module for handling files and local paths.
"""

import os
import logging
from pathlib import Path
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)


class InputProcessor:
    """Process and validate various input types."""
    
    @staticmethod
    def validate_local_path(path: str) -> Tuple[bool, Optional[Path], Optional[str]]:
        """
        Validate a local file or directory path.
        
        Args:
            path: Path to validate
            
        Returns:
            Tuple of (is_valid, Path object or None, error message or None)
        """
        try:
            path_obj = Path(path).resolve()
            
            if not path_obj.exists():
                return False, None, f"Path does not exist: {path}"
            
            if not os.access(path_obj, os.R_OK):
                return False, None, f"Path is not readable: {path}"
            
            return True, path_obj, None
        
        except Exception as e:
            return False, None, str(e)
    
    @staticmethod
    def find_files_in_directory(
        directory: Path,
        patterns: Optional[List[str]] = None,
        recursive: bool = True
    ) -> List[Path]:
        """
        Find files in a directory matching patterns.
        
        Args:
            directory: Directory to search
            patterns: Optional list of glob patterns
            recursive: Whether to search recursively
            
        Returns:
            List of matching file paths
        """
        files = []
        
        if patterns is None:
            patterns = ['*']
        
        for pattern in patterns:
            if recursive:
                matches = directory.rglob(pattern)
            else:
                matches = directory.glob(pattern)
            
            for match in matches:
                if match.is_file():
                    files.append(match)
        
        return sorted(set(files))
    
    @staticmethod
    def is_text_file(file_path: Path, sample_size: int = 8192) -> bool:
        """
        Check if a file is likely a text file.
        
        Args:
            file_path: Path to file
            sample_size: Number of bytes to sample
            
        Returns:
            True if file appears to be text
        """
        try:
            with open(file_path, 'rb') as f:
                sample = f.read(sample_size)
            
            # Check for null bytes
            if b'\x00' in sample:
                return False
            
            # Try to decode as UTF-8
            try:
                sample.decode('utf-8')
                return True
            except UnicodeDecodeError:
                pass
            
            # Try common encodings
            for encoding in ['latin-1', 'cp1252', 'iso-8859-1']:
                try:
                    sample.decode(encoding)
                    return True
                except UnicodeDecodeError:
                    pass
            
            return False
        
        except Exception:
            return False
    
    @staticmethod
    def read_text_file(file_path: Path, max_size: Optional[int] = None) -> Optional[str]:
        """
        Read a text file with automatic encoding detection.
        
        Args:
            file_path: Path to file
            max_size: Maximum bytes to read
            
        Returns:
            File contents as string or None if failed
        """
        encodings = ['utf-8', 'utf-8-sig', 'latin-1', 'cp1252', 'iso-8859-1']
        
        for encoding in encodings:
            try:
                with open(file_path, 'r', encoding=encoding) as f:
                    if max_size:
                        content = f.read(max_size)
                    else:
                        content = f.read()
                return content
            except (UnicodeDecodeError, UnicodeError):
                continue
            except Exception as e:
                logger.debug(f"Error reading {file_path} with {encoding}: {e}")
        
        return None