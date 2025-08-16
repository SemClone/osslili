"""
Configuration loader with YAML support.
"""

import os
import logging
from pathlib import Path
from typing import Optional, Dict, Any

import yaml

from ..core.models import Config

logger = logging.getLogger(__name__)


class ConfigLoader:
    """Load and manage configuration from various sources."""
    
    @staticmethod
    def load_from_file(config_path: str) -> Config:
        """
        Load configuration from YAML file.
        
        Args:
            config_path: Path to YAML configuration file
            
        Returns:
            Config object with loaded settings
        """
        try:
            with open(config_path, 'r') as f:
                data = yaml.safe_load(f)
            
            return ConfigLoader.create_config(data or {})
        
        except FileNotFoundError:
            logger.error(f"Configuration file not found: {config_path}")
            raise
        except yaml.YAMLError as e:
            logger.error(f"Error parsing YAML configuration: {e}")
            raise
        except Exception as e:
            logger.error(f"Error loading configuration: {e}")
            raise
    
    @staticmethod
    def load_from_env() -> Config:
        """
        Load configuration from environment variables.
        
        Environment variables:
        - OSLILI_SIMILARITY_THRESHOLD
        - OSLILI_MAX_EXTRACTION_DEPTH
        - OSLILI_NETWORK_TIMEOUT
        - OSLILI_THREAD_COUNT
        - OSLILI_VERBOSE
        - OSLILI_DEBUG
        - OSLILI_CACHE_DIR
        
        Returns:
            Config object with environment settings
        """
        data = {}
        
        # Map environment variables to config fields
        env_mapping = {
            'OSLILI_SIMILARITY_THRESHOLD': ('similarity_threshold', float),
            'OSLILI_MAX_EXTRACTION_DEPTH': ('max_extraction_depth', int),
            'OSLILI_NETWORK_TIMEOUT': ('network_timeout', int),
            'OSLILI_THREAD_COUNT': ('thread_count', int),
            'OSLILI_VERBOSE': ('verbose', lambda x: x.lower() in ['true', '1', 'yes']),
            'OSLILI_DEBUG': ('debug', lambda x: x.lower() in ['true', '1', 'yes']),
            'OSLILI_CACHE_DIR': ('cache_dir', str),
        }
        
        for env_var, (config_field, converter) in env_mapping.items():
            value = os.environ.get(env_var)
            if value is not None:
                try:
                    data[config_field] = converter(value)
                except ValueError as e:
                    logger.warning(f"Invalid value for {env_var}: {value}")
        
        return ConfigLoader.create_config(data)
    
    @staticmethod
    def load_default_config() -> Config:
        """
        Load default configuration from package data.
        
        Returns:
            Config object with default settings
        """
        default_config_path = Path(__file__).parent.parent / 'data' / 'default_config.yaml'
        
        if default_config_path.exists():
            try:
                return ConfigLoader.load_from_file(str(default_config_path))
            except Exception:
                logger.warning("Failed to load default config file, using defaults")
        
        return Config()
    
    @staticmethod
    def create_config(data: Dict[str, Any]) -> Config:
        """
        Create Config object from dictionary.
        
        Args:
            data: Configuration dictionary
            
        Returns:
            Config object
        """
        config = Config()
        
        # Update config with provided data
        for key, value in data.items():
            if hasattr(config, key):
                # Special handling for certain fields
                if key == 'license_filename_patterns' and isinstance(value, list):
                    config.license_filename_patterns = value
                elif key == 'custom_aliases' and isinstance(value, dict):
                    config.custom_aliases.update(value)
                else:
                    setattr(config, key, value)
            else:
                logger.warning(f"Unknown configuration key: {key}")
        
        return config
    
    @staticmethod
    def merge_configs(*configs: Config) -> Config:
        """
        Merge multiple configuration objects.
        Later configs override earlier ones.
        
        Args:
            *configs: Config objects to merge
            
        Returns:
            Merged Config object
        """
        merged = Config()
        
        for config in configs:
            if not config:
                continue
            
            # Merge all attributes
            for attr in dir(config):
                if not attr.startswith('_'):
                    value = getattr(config, attr)
                    if value is not None:
                        if attr == 'custom_aliases' and hasattr(merged, 'custom_aliases'):
                            # Merge dictionaries
                            merged.custom_aliases.update(value)
                        else:
                            setattr(merged, attr, value)
        
        return merged
    
    @staticmethod
    def save_config(config: Config, file_path: str):
        """
        Save configuration to YAML file.
        
        Args:
            config: Config object to save
            file_path: Path to save configuration
        """
        try:
            # Convert config to dictionary
            data = {
                'similarity_threshold': config.similarity_threshold,
                'max_extraction_depth': config.max_extraction_depth,
                'network_timeout': config.network_timeout,
                'thread_count': config.thread_count,
                'verbose': config.verbose,
                'debug': config.debug,
                'license_filename_patterns': config.license_filename_patterns,
                'custom_aliases': config.custom_aliases,
                'spdx_data_url': config.spdx_data_url,
                'clearlydefined_api_url': config.clearlydefined_api_url,
                'pypi_api_url': config.pypi_api_url,
                'npm_api_url': config.npm_api_url,
            }
            
            if config.cache_dir:
                data['cache_dir'] = config.cache_dir
            
            # Write to file
            with open(file_path, 'w') as f:
                yaml.dump(data, f, default_flow_style=False, sort_keys=False)
            
            logger.info(f"Configuration saved to {file_path}")
        
        except Exception as e:
            logger.error(f"Error saving configuration: {e}")
            raise
    
    @staticmethod
    def generate_sample_config(file_path: str):
        """
        Generate a sample configuration file.
        
        Args:
            file_path: Path to save sample configuration
        """
        sample_config = """# Semantic Copycat OSLILI Configuration File
# This file configures the behavior of the oslili tool

# License detection similarity threshold (0.0-1.0)
# Higher values require more exact matches
similarity_threshold: 0.97

# Maximum depth for recursive archive extraction
max_extraction_depth: 10

# Network request timeout in seconds
network_timeout: 30

# Number of threads for parallel processing
thread_count: 4

# Verbose output
verbose: false

# Debug output
debug: false

# Additional license filename patterns to search for
license_filename_patterns:
  - "LICENSE*"
  - "LICENCE*"
  - "COPYING*"
  - "NOTICE*"
  - "COPYRIGHT*"
  - "MIT-LICENSE*"
  - "APACHE-LICENSE*"
  - "BSD-LICENSE*"
  - "UNLICENSE*"
  - "3rdpartylicenses.txt"
  - "THIRD_PARTY_NOTICES*"

# Custom license name aliases
# Map common variations to SPDX identifiers
custom_aliases:
  "Apache 2": "Apache-2.0"
  "Apache 2.0": "Apache-2.0"
  "Apache License 2.0": "Apache-2.0"
  "MIT License": "MIT"
  "BSD License": "BSD-3-Clause"
  "ISC License": "ISC"
  "GPLv2": "GPL-2.0"
  "GPLv3": "GPL-3.0"
  "LGPLv2": "LGPL-2.0"
  "LGPLv3": "LGPL-3.0"

# External data source URLs
spdx_data_url: "https://raw.githubusercontent.com/spdx/license-list-data/main/json/licenses.json"
clearlydefined_api_url: "https://api.clearlydefined.io"
pypi_api_url: "https://pypi.org/pypi"
npm_api_url: "https://registry.npmjs.org"

# Cache directory (optional)
# cache_dir: "~/.cache/oslili"
"""
        
        try:
            with open(file_path, 'w') as f:
                f.write(sample_config)
            
            logger.info(f"Sample configuration generated at {file_path}")
        
        except Exception as e:
            logger.error(f"Error generating sample configuration: {e}")
            raise