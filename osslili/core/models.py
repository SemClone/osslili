"""
Data models for the semantic-copycat-oslili package.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from enum import Enum


class DetectionMethod(Enum):
    HASH = "hash"  # Exact hash matching (SHA-256/MD5)
    DICE_SORENSEN = "dice-sorensen"
    TLSH = "tlsh"
    ML = "ml"
    REGEX = "regex"
    TAG = "tag"
    KEYWORD = "keyword"  # License keyword detection (GPL, BSD, Apache, etc.)
    FILENAME = "filename"


class LicenseCategory(Enum):
    """Categories for license hierarchy."""
    DECLARED = "declared"  # Explicitly declared in LICENSE files, package.json, etc.
    DETECTED = "detected"  # Inferred from source code content
    REFERENCED = "referenced"  # Mentioned but not primary


@dataclass
class DetectedLicense:
    """Represents a detected license."""
    spdx_id: str
    name: str
    text: Optional[str] = None
    confidence: float = 0.0
    detection_method: str = ""
    source_file: Optional[str] = None
    category: Optional[str] = None  # License category (declared/detected/referenced)
    match_type: Optional[str] = None  # Type of match (full_text, spdx_identifier, etc.)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "spdx_id": self.spdx_id,
            "name": self.name,
            "confidence": self.confidence,
            "detection_method": self.detection_method,
            "source_file": self.source_file,
            "category": self.category,
            "match_type": self.match_type
        }


@dataclass
class CopyrightInfo:
    """Represents copyright information."""
    holder: str
    years: Optional[List[int]] = None
    statement: str = ""
    source_file: Optional[str] = None
    confidence: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "holder": self.holder,
            "years": self.years,
            "statement": self.statement,
            "source_file": self.source_file,
            "confidence": self.confidence
        }


@dataclass
class DetectionResult:
    """Result of license and copyright detection for a local path."""
    path: str
    licenses: List[DetectedLicense] = field(default_factory=list)
    copyrights: List[CopyrightInfo] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    confidence_scores: Dict[str, float] = field(default_factory=dict)
    processing_time: float = 0.0
    package_name: Optional[str] = None
    package_version: Optional[str] = None
    
    def get_primary_license(self) -> Optional[DetectedLicense]:
        """Get the license with highest confidence."""
        if not self.licenses:
            return None
        return max(self.licenses, key=lambda x: x.confidence)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "package_name": self.package_name,
            "package_version": self.package_version,
            "licenses": [l.to_dict() for l in self.licenses],
            "copyrights": [c.to_dict() for c in self.copyrights],
            "errors": self.errors,
            "confidence_scores": self.confidence_scores,
            "processing_time": self.processing_time
        }


@dataclass
class Config:
    """Configuration for the license and copyright detector."""
    similarity_threshold: float = 0.97
    max_recursion_depth: int = 10
    max_extraction_depth: int = 3
    thread_count: int = 4
    verbose: bool = False
    debug: bool = False
    license_filename_patterns: List[str] = field(default_factory=lambda: [
        "LICENSE*", "LICENCE*", "COPYING*", "NOTICE*",
        "MIT-LICENSE*", "APACHE-LICENSE*", "BSD-LICENSE*",
        "UNLICENSE*", "COPYRIGHT*", "3rdpartylicenses.txt",
        "THIRD_PARTY_NOTICES*", "*GPL*", "*COPYLEFT*", 
        "*EULA*", "*COMMERCIAL*", "*AGREEMENT*", "*BUNDLE*",
        "*THIRD-PARTY*", "*THIRD_PARTY*", "LEGAL*"
    ])
    custom_aliases: Dict[str, str] = field(default_factory=lambda: {
        "Apache 2": "Apache-2.0",
        "Apache 2.0": "Apache-2.0",
        "Apache License 2.0": "Apache-2.0",
        "MIT License": "MIT",
        "BSD License": "BSD-3-Clause",
        "ISC License": "ISC",
        "GPLv2": "GPL-2.0",
        "GPLv3": "GPL-3.0",
        "LGPLv2": "LGPL-2.0",
        "LGPLv3": "LGPL-3.0",
    })
    cache_dir: Optional[str] = None