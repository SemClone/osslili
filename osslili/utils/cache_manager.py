"""
Cache manager for storing detection results.
"""

import os
import json
import hashlib
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class CacheManager:
    """Manage caching of license and copyright detection results."""
    
    def __init__(self, cache_dir: Optional[str] = None, ttl_hours: int = 24):
        """
        Initialize cache manager.
        
        Args:
            cache_dir: Directory for cache storage (uses temp if None)
            ttl_hours: Time-to-live for cache entries in hours
        """
        if cache_dir:
            self.cache_dir = Path(cache_dir).expanduser()
        else:
            # Default to ~/.cache/oslili
            self.cache_dir = Path.home() / '.cache' / 'oslili'
        
        self.ttl = timedelta(hours=ttl_hours)
        self._ensure_cache_dir()
    
    def _ensure_cache_dir(self):
        """Ensure cache directory exists."""
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            logger.debug(f"Using cache directory: {self.cache_dir}")
        except Exception as e:
            logger.warning(f"Failed to create cache directory: {e}")
            # Fallback to temp directory
            import tempfile
            self.cache_dir = Path(tempfile.gettempdir()) / 'oslili_cache'
            self.cache_dir.mkdir(parents=True, exist_ok=True)
    
    def _get_cache_key(self, path: str) -> str:
        """
        Generate cache key for a path.
        
        Args:
            path: File or directory path
            
        Returns:
            Cache key string
        """
        # Include file modification time in key for invalidation
        path_obj = Path(path)
        if path_obj.exists():
            mtime = path_obj.stat().st_mtime
            key_str = f"{path}:{mtime}"
        else:
            key_str = path
        
        # Create hash of the key
        return hashlib.sha256(key_str.encode()).hexdigest()
    
    def _get_cache_file(self, cache_key: str) -> Path:
        """
        Get cache file path for a key.
        
        Args:
            cache_key: Cache key
            
        Returns:
            Path to cache file
        """
        # Use first 2 characters for subdirectory to avoid too many files in one dir
        subdir = self.cache_dir / cache_key[:2]
        subdir.mkdir(exist_ok=True)
        return subdir / f"{cache_key}.json"
    
    def get(self, path: str) -> Optional[Dict[str, Any]]:
        """
        Get cached result for a path.
        
        Args:
            path: File or directory path
            
        Returns:
            Cached result or None if not found/expired
        """
        try:
            cache_key = self._get_cache_key(path)
            cache_file = self._get_cache_file(cache_key)
            
            if not cache_file.exists():
                return None
            
            # Check if cache is expired
            cache_mtime = datetime.fromtimestamp(cache_file.stat().st_mtime)
            if datetime.now() - cache_mtime > self.ttl:
                logger.debug(f"Cache expired for {path}")
                cache_file.unlink()
                return None
            
            # Load cached data
            with open(cache_file, 'r') as f:
                data = json.load(f)
            
            logger.debug(f"Cache hit for {path}")
            return data
            
        except Exception as e:
            logger.debug(f"Cache miss for {path}: {e}")
            return None
    
    def set(self, path: str, data: Dict[str, Any]):
        """
        Store result in cache.
        
        Args:
            path: File or directory path
            data: Data to cache
        """
        try:
            cache_key = self._get_cache_key(path)
            cache_file = self._get_cache_file(cache_key)
            
            # Store data
            with open(cache_file, 'w') as f:
                json.dump(data, f, indent=2)
            
            logger.debug(f"Cached result for {path}")
            
        except Exception as e:
            logger.warning(f"Failed to cache result for {path}: {e}")
    
    def clear(self):
        """Clear all cache entries."""
        try:
            import shutil
            if self.cache_dir.exists():
                shutil.rmtree(self.cache_dir)
                self._ensure_cache_dir()
                logger.info("Cache cleared")
        except Exception as e:
            logger.error(f"Failed to clear cache: {e}")
    
    def get_size(self) -> int:
        """
        Get total size of cache in bytes.
        
        Returns:
            Total cache size
        """
        total_size = 0
        try:
            for root, dirs, files in os.walk(self.cache_dir):
                for file in files:
                    file_path = Path(root) / file
                    total_size += file_path.stat().st_size
        except Exception:
            pass
        return total_size
    
    def cleanup_expired(self):
        """Remove expired cache entries."""
        try:
            now = datetime.now()
            cleaned = 0
            
            for root, dirs, files in os.walk(self.cache_dir):
                for file in files:
                    file_path = Path(root) / file
                    if file.endswith('.json'):
                        cache_mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                        if now - cache_mtime > self.ttl:
                            file_path.unlink()
                            cleaned += 1
            
            if cleaned > 0:
                logger.info(f"Cleaned {cleaned} expired cache entries")
                
        except Exception as e:
            logger.error(f"Failed to cleanup cache: {e}")