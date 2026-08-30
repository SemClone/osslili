"""
Data models for the semantic-copycat-oslili package.
"""

from pathlib import Path
from dataclasses import dataclass, field, replace
from typing import List, Optional, Dict, Any
from enum import Enum


# Scanning modes are presets over the individual scan targets (issue #79).


class DetectionMethod(Enum):
    HASH = "hash"  # Exact hash matching (SHA-256/MD5)
    DICE_SORENSEN = "dice-sorensen"
    TLSH = "tlsh"
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
    # How many files the statement was found in. `source_file` names the
    # first of them in scan order, and one file alone cannot tell a package's
    # own copyright from a vendored one's: a statement in forty files is the
    # package, a statement in one is usually not.
    file_count: int = 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "holder": self.holder,
            "years": self.years,
            "statement": self.statement,
            "source_file": self.source_file,
            "file_count": self.file_count,
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
        licenses rather than the project's own license (issue #78), and
        licences the project only refers to. A README saying "the bundled
        minifier is licensed under the Apache License" is crediting a
        dependency, and that credit reached the package licence and the SBOM
        (issue #109).
        """
        borrowed = {
            LicenseCategory.THIRD_PARTY.value,
            LicenseCategory.REFERENCED.value,
        }
        return [l for l in self.licenses if l.category not in borrowed]

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


PACKAGE_METADATA_FILENAMES = {
    # JavaScript/Node.js (npm, yarn, pnpm)
    'package.json', 'package-lock.json', 'yarn.lock', 'pnpm-lock.yaml',
    # Python
    'pyproject.toml', 'setup.py', 'setup.cfg', 'pipfile', 'pipfile.lock', 'requirements.txt',
    # Go
    'go.mod', 'go.sum',
    # Java (Maven, Gradle)
    'pom.xml', 'build.gradle', 'build.gradle.kts', 'settings.gradle', 'manifest.mf',
    # .NET/NuGet
    'packages.config', 'paket.dependencies',
    # Rust
    'cargo.toml', 'cargo.lock',
    # Ruby
    'gemfile', 'gemfile.lock',
    # PHP/Composer
    'composer.json', 'composer.lock',
    # Swift/CocoaPods
    'podfile', 'podfile.lock',
    # Dart/Flutter
    'pubspec.yaml', 'pubspec.lock',
    # Elixir
    'mix.exs', 'mix.lock',
    # Scala
    'build.sbt',
    # Kotlin
    'build.gradle.kts',
}

# Pattern-based metadata extensions
PACKAGE_METADATA_EXTENSIONS = {
    '.gemspec',   # Ruby
    '.nuspec',    # NuGet
    '.csproj',    # .NET C#
    '.fsproj',    # .NET F#
    '.vbproj',    # .NET VB
    '.podspec',   # CocoaPods
}


DOCUMENTATION_EXTENSIONS = {
    '.txt', '.md', '.rst', '.text', '.markdown', '.adoc', '.asciidoc'
}

# A bundled notice names both a third party and the kind of file it is.
THIRD_PARTY_MARKERS = (
    'third-party', 'third_party', 'thirdparty',
    '3rdparty', '3rd-party', '3rd_party',
)
THIRD_PARTY_NOTICE_TOKENS = (
    'notice', 'license', 'licence', 'legal', 'attribution',
)

# The words a licence file is named by, beyond the configured patterns.
LICENCE_FILE_WORDS = (
    'license', 'licence', 'copying', 'copyright', 'notice', 'legal',
    'gpl', 'copyleft', 'eula', 'commercial', 'agreement', 'bundle',
    'third-party', 'third_party',
)


def names_a_third_party_notice(file_path) -> bool:
    """Whether this file is a bundled third-party notice."""
    name = Path(file_path).name.lower()
    return (any(marker in name for marker in THIRD_PARTY_MARKERS)
            and any(token in name for token in THIRD_PARTY_NOTICE_TOKENS))


def names_a_licence_file(file_path, patterns=()) -> bool:
    """Whether this file is a licence file, by name."""
    name = Path(file_path).name
    if any(pattern.match(name) for pattern in patterns):
        return True
    return any(word in name.lower() for word in LICENCE_FILE_WORDS)


def names_documentation(file_path) -> bool:
    """Whether this file is readable documentation."""
    return Path(file_path).suffix.lower() in DOCUMENTATION_EXTENSIONS


def the_category_of(file_path, patterns=()) -> str:
    """Which scan target this file belongs to.

    The categories are mutually exclusive and asked in precedence order: a
    bundled notice is a notice rather than a licence file, and package
    metadata wins over the documentation extensions it shares
    (``requirements.txt``).

    Asked here rather than in each reader, because the licence detector and
    the copyright extractor have to agree about it. They did not, and a
    scan told to read only licence files still reported the copyright out of
    a README and a source file.
    """
    if names_a_third_party_notice(file_path):
        return 'notice_files'
    if names_a_licence_file(file_path, patterns):
        return 'license_files'
    if names_package_metadata(file_path):
        return 'package_metadata'
    if names_documentation(file_path):
        return 'documentation'
    return 'source_files'


def names_package_metadata(file_path) -> bool:
    """Whether this file is a package manifest or lock file.

    Asked here rather than in each reader, because the licence detector and
    the copyright extractor both have to agree about it: disregarding package
    metadata means the file is not read at all, and the two disagreeing meant
    a manifest's licence was left out while its author was still reported.
    """
    name = Path(file_path).name.lower()
    return (name in PACKAGE_METADATA_FILENAMES
            or Path(file_path).suffix.lower() in PACKAGE_METADATA_EXTENSIONS)


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
    # for a caller that wants every file read but not compared against every
    # licence text.
    text_similarity_matching: bool = True

    def wants(self, file_path) -> bool:
        """Whether this file's category is one the scan is reading.

        The one question both readers ask, so that turning a category off
        means the file is not read at all rather than read by whichever of
        them was not told.
        """
        import re

        if not hasattr(self, '_licence_name_patterns'):
            object.__setattr__(self, '_licence_name_patterns', tuple(
                re.compile(pattern.replace('*', '.*'), re.IGNORECASE)
                for pattern in self.license_filename_patterns
            ))
        category = the_category_of(file_path, self._licence_name_patterns)
        return getattr(self.scan_targets(), category)

    def the_category(self, file_path) -> str:
        """Which scan target this file belongs to."""
        self.wants(file_path)  # compiles the patterns once
        return the_category_of(file_path, self._licence_name_patterns)

    def was_not_turned_off(self, file_path) -> bool:
        """Whether this file's category was explicitly disregarded.

        Asked of what the caller said rather than of what a directory scan
        would have chosen, because naming a file is itself the choice to read
        it: a source file is not in the default scan, and pointing straight
        at one has always read it.
        """
        said = ScanTargets(
            license_files=self.scan_license_files,
            notice_files=self.scan_notice_files,
            package_metadata=self.scan_package_metadata,
            documentation=self.scan_documentation,
            source_files=self.scan_source_files,
        )
        self.wants(file_path)  # compiles the patterns once
        category = the_category_of(file_path, self._licence_name_patterns)
        return getattr(said, category) is not False

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