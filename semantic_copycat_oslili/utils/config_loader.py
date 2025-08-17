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