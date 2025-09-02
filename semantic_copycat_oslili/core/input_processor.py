"""
Input processing module for handling files and local paths.
"""

import os
import logging
from pathlib import Path
from typing import Optional, Tuple

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