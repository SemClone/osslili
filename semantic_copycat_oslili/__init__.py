"""
semantic-copycat-oslili: License and copyright detector for software packages.
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

__version__ = "1.5.1"

from .core.generator import LicenseCopyrightDetector
from .core.models import (
    DetectionResult,
    DetectedLicense,
    CopyrightInfo,
    Config
)

__all__ = [
    "LicenseCopyrightDetector",
    "DetectionResult", 
    "DetectedLicense",
    "CopyrightInfo",
    "Config",
]