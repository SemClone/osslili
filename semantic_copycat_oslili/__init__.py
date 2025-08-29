"""
semantic-copycat-oslili: Legal attribution notice generator for software packages.
"""

# Suppress SSL warnings before importing anything else
import warnings
import os
if os.environ.get('OSLILI_DEBUG') != '1':
    warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL.*')
    try:
        from urllib3.exceptions import NotOpenSSLWarning
        warnings.filterwarnings('ignore', category=NotOpenSSLWarning)
    except ImportError:
        pass

__version__ = "1.2.7"

from .core.generator import LegalAttributionGenerator
from .core.models import (
    AttributionResult,
    DetectedLicense,
    CopyrightInfo,
    Config
)

__all__ = [
    "LegalAttributionGenerator",
    "AttributionResult", 
    "DetectedLicense",
    "CopyrightInfo",
    "Config",
]