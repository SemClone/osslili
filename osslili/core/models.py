"""
Data models for the semantic-copycat-oslili package.
"""

from dataclasses import dataclass, field, replace
from typing import List, Optional, Dict, Any
from enum import Enum


# Scanning modes are presets over the individual scan targets (issue #79).
SCAN_MODES = ("default", "deep", "license-files", "lightweight")


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
    THIRD_PARTY = "third-party"  # Bundled third-party notice/license files (deps, not the project itself)


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
    
    def get_own_licenses(self) -> List[DetectedLicense]:
        """Licenses representing the project itself.

        Excludes bundled third-party notice files, which carry dependency
        licenses rather than the project's own license (issue #78).
        """
        return [l for l in self.licenses
                if l.category != LicenseCategory.THIRD_PARTY.value]

    def get_third_party_licenses(self) -> List[DetectedLicense]:
        """Licenses detected in bundled third-party notice files (issue #78)."""
        return [l for l in self.licenses
                if l.category == LicenseCategory.THIRD_PARTY.value]

    def get_primary_license(self) -> Optional[DetectedLicense]:
        """Get the highest-confidence license representing the project itself.

        Bundled third-party dependency licenses are never selected as the
        project's primary license (issue #78). If only third-party notice
        licenses were detected, there is no project-owned primary license and
        this returns None (they remain available via get_third_party_licenses).
        """
        own_licenses = self.get_own_licenses()
        if not own_licenses:
            return None
        return max(own_licenses, key=lambda x: x.confidence)
    
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


@dataclass(frozen=True)
class ScanTargets:
    """Which categories of files a scan reads (issue #79).

    Resolved from the scanning mode plus any explicit per-category override, so
    a consumer that already has declared licenses from package metadata (ORT's
    analyzer, for instance) can scan every file while disregarding metadata.
    """
    license_files: bool = True      # LICENSE, COPYING, ... (the project's own)
    notice_files: bool = True       # bundled third-party notices (issue #78)
    package_metadata: bool = True   # package.json, pom.xml, requirements.txt, ...
    documentation: bool = True      # README and other readable documentation
    source_files: bool = False      # every other readable file (content scan)


@dataclass
class Config:
    """Configuration for the license and copyright detector."""
    similarity_threshold: float = 0.97
    max_recursion_depth: int = 4
    max_extraction_depth: int = 3
    thread_count: int = 4
    verbose: bool = False
    debug: bool = False
    license_filename_patterns: List[str] = field(default_factory=lambda: [
        "LICENSE*", "LICENCE*", "COPYING*", "NOTICE*",
        "MIT-LICENSE*", "APACHE-LICENSE*", "BSD-LICENSE*",
        "UNLICENSE*", "COPYRIGHT*", "3rdpartylicenses.txt",
        "*GPL*", "*COPYLEFT*",
        "*EULA*", "*COMMERCIAL*", "*AGREEMENT*", "*BUNDLE*",
        "*THIRD-PARTY*", "*THIRD_PARTY*", "LEGAL*"
    ])
    license_fuzzy_base_names: List[str] = field(default_factory=lambda: [
        'license', 'licence', 'copying', 'copyright', 'notice'
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

    # Performance optimization flags
    skip_content_detection: bool = False  # Skip content-based file type detection
    license_files_only: bool = True  # By default, only scan license files, metadata, and README (use --deep for comprehensive scan)
    strict_license_files: bool = False  # When True, scan ONLY license files (no metadata, no README)
    skip_extensionless: bool = False  # Skip files without extensions unless known patterns
    max_file_size_kb: Optional[int] = None  # Skip files larger than this size in KB
    skip_smart_read: bool = False  # Read files sequentially instead of sampling start/end
    fast_mode: bool = False  # Enable multiple optimizations for maximum speed
    deep_scan: bool = False  # Enable comprehensive scan of all source files

    # Fine-grained scan targets (issue #79). None means "whatever the scanning
    # mode selects"; setting one to True/False overrides the mode's preset.
    scan_license_files: Optional[bool] = None
    scan_notice_files: Optional[bool] = None
    scan_package_metadata: Optional[bool] = None
    scan_documentation: Optional[bool] = None
    scan_source_files: Optional[bool] = None

    # Full license text comparison (exact hash, Dice-Sørensen, TLSH). Disabling
    # it leaves the cheap detectors (SPDX tags, keywords, references) in place,
    # which is what a lightweight all-files scan wants.
    text_similarity_matching: bool = True

    def apply_scan_mode(self, mode: str):
        """Apply a scanning mode preset (one of SCAN_MODES).

        Presets only set what the mode itself defines, so explicit scan target
        overrides applied afterwards still win.
        """
        if mode not in SCAN_MODES:
            raise ValueError(
                f"Unknown scan mode: {mode!r} (expected one of {', '.join(SCAN_MODES)})"
            )

        if mode == "default":
            self.license_files_only = True
            self.strict_license_files = False
            self.deep_scan = False
        elif mode == "deep":
            self.license_files_only = False
            self.strict_license_files = False
            self.deep_scan = True
        elif mode == "license-files":
            self.license_files_only = True
            self.strict_license_files = True
            self.deep_scan = False
        elif mode == "lightweight":
            # All files, cheap detection only, package metadata disregarded:
            # for scanners whose declared licenses come from elsewhere.
            self.license_files_only = False
            self.strict_license_files = False
            self.deep_scan = True
            self.scan_package_metadata = False
            self.text_similarity_matching = False

    def scan_targets(self) -> ScanTargets:
        """Resolve the scan targets this configuration selects."""
        if self.strict_license_files:
            base = ScanTargets(package_metadata=False, documentation=False)
        elif self.deep_scan or not self.license_files_only:
            base = ScanTargets(source_files=True)
        else:
            base = ScanTargets()

        overrides = {
            'license_files': self.scan_license_files,
            'notice_files': self.scan_notice_files,
            'package_metadata': self.scan_package_metadata,
            'documentation': self.scan_documentation,
            'source_files': self.scan_source_files,
        }
        return replace(base, **{k: v for k, v in overrides.items() if v is not None})

    def apply_fast_mode(self):
        """Apply fast mode preset - enables multiple optimizations for maximum speed."""
        if self.fast_mode:
            self.skip_content_detection = True
            self.skip_extensionless = True
            self.skip_smart_read = True
            if self.max_file_size_kb is None:
                self.max_file_size_kb = 1024  # Skip files larger than 1MB