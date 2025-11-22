# Changelog

All notable changes to osslili will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.6.1] - 2025-11-22

### Fixed
- **Copyright Extraction**: Fixed copyright detection when holder name is followed by email address in angle brackets (Issue #54)
  - Regex patterns now properly stop before `<` character
  - Correctly extracts names from formats like: `Copyright (c) 2003 Michael Niedermayer <michaelni@gmx.at>`
  - Affects all three copyright patterns: `Copyright`, `©`, and `(C)` formats
  - Impacts thousands of files in major projects (FFmpeg, Linux kernel, etc.)

### Added
- **Test Coverage**: Added 11 comprehensive test cases for copyright extraction with email addresses
  - Tests all copyright format variants with emails
  - Includes FFmpeg-style header examples
  - Validates email address cleanup in holder names

## [1.6.0] - 2025-11-14

### Added
- **Deep Scan Mode**: New `--deep` flag for comprehensive source code scanning
  - Scans all source files (.py, .js, .java, .c, .go, etc.) for embedded licenses
  - Ideal for legal compliance audits and finding license headers in code
  - Complements the fast default mode

### Changed
- **Default Scanning Behavior** (BREAKING CHANGE - but faster!):
  - Default mode now scans LICENSE files + package metadata + documentation
  - Provides 40x speedup over comprehensive scanning while capturing all declared licenses
  - New default covers 12+ package ecosystems and 40+ metadata files
  - Use `--deep` flag for old comprehensive behavior

- **Package Metadata Support** (Massive Expansion):
  - **NEW**: Go support (go.mod, go.sum)
  - **NEW**: Swift/CocoaPods support (Podfile, *.podspec)
  - **NEW**: Dart/Flutter support (pubspec.yaml)
  - **NEW**: Elixir support (mix.exs, mix.lock)
  - **NEW**: Scala support (build.sbt)
  - **Enhanced**: JavaScript (added yarn.lock, pnpm-lock.yaml)
  - **Enhanced**: Python (added Pipfile, requirements.txt)
  - **Enhanced**: .NET (added .csproj, .fsproj, .vbproj)
  - **Enhanced**: Rust (added Cargo.lock)
  - **Enhanced**: PHP (added composer.lock)
  - Total: 40+ metadata files across 12+ ecosystems (+200% increase)

- **Documentation File Support**:
  - Now scans all .txt, .md, .rst, .text, .markdown, .adoc, .asciidoc files
  - Captures README, CHANGELOG, CONTRIBUTING, AUTHORS, and other docs

### Performance
- **Benchmark Results** (ffmpeg-6.0, 4,139 files, 4 threads):
  - `--license-files-only` (strict): 7s, 8 files, 14 licenses
  - **Default mode**: **8.5s, 31 files, 16 licenses** ⚡ RECOMMENDED
  - `--deep` mode: 5m 37s, 4,800+ files, comprehensive
  - **40x speedup** in default mode vs deep scan!

### Fixed
- **Code Optimization**: Eliminated double-scanning in license file detection
- **Performance**: Changed from O(n) list lookups to O(1) set operations
- **Efficiency**: Pre-computed metadata filename sets outside loops

### Documentation
- **README.md**: Added comprehensive "Scanning Modes" section with examples
- **USAGE.md**: Added detailed scanning modes documentation
  - Performance comparison table
  - Use case recommendations for each mode
  - Package ecosystem coverage details
- **CLI Help**: Updated to explain new default behavior

### Migration Guide
- **No action needed**: Default mode is faster and better
- **For old behavior**: Use `--deep` flag for comprehensive source code scanning
- **Backwards compatible**: All existing flags still work

## [1.5.9] - 2025-11-14

### Added
- **Performance Optimization Flags**: New configurable flags for faster scanning (Issue #49)
  - `--skip-content-detection`: Skip content-based file type detection, rely only on extensions
  - `--license-files-only`: Only scan LICENSE files, skip source code (17x speedup on ffmpeg)
  - `--skip-extensionless`: Skip files without extensions unless they match known patterns
  - `--max-file-size <KB>`: Skip files larger than specified size in KB
  - `--skip-smart-read`: Read files sequentially instead of sampling start/end
  - `--fast`: Preset that combines multiple optimizations for maximum speed

### Changed
- **Config Model**: Added 6 performance optimization flags with `apply_fast_mode()` method
- **CLI**: Added 6 new command-line options for performance tuning
- **License Detector**: Enhanced file detection logic to respect performance flags
  - File size checking before processing
  - Configurable extensionless file handling
  - Optional content-based detection
  - Sequential vs smart file reading modes

### Performance
- **Benchmark Results** (ffmpeg-6.0 codebase, 4 threads):
  - Normal mode: 69s, 4,822 files, 5,566 licenses
  - `--fast`: 70s, 4,765 files, 5,549 licenses
  - `--skip-content-detection`: 71s, 4,770 files, 5,549 licenses
  - `--license-files-only`: **4s, 12 files, 14 licenses (17x speedup!)**
- **Use Case**: `--license-files-only` ideal for CI/CD pipelines needing quick declared license checks

### Fixed
- **Performance Degradation**: Addressed slowdown caused by content-based file detection (Issue #49)
  - Content detection now opens files only when necessary
  - Reduced I/O operations during file discovery phase
  - Eliminated unnecessary file reads for extensionless files

### Technical
- **Backward Compatibility**: All flags default to False, maintaining current behavior
- **Testing**: Added comprehensive test suite (10 tests) for performance flags
- **Documentation**: Updated CLI help text with performance flag descriptions

## [1.5.7] - 2025-10-30

### Changed
- **Performance Optimization**: Updated default values for better performance
  - Reduced default max recursion depth from 10 to 4 for faster directory scans
  - Set explicit thread count default to 4 in CLI (previously inherited from Config)
  - Aligned CLI and Config model defaults for consistency

### Technical
- **CLI Defaults**: Added explicit default values in CLI options for better visibility
- **Configuration**: Synchronized default values between CLI and Config model

## [1.5.6] - 2025-10-27

### Changed
- **Project Rename**: Renamed project from `semantic-copycat-oslili` to `osslili`
  - Updated package name and imports throughout codebase
  - Changed CLI command from `oslili` to `osslili`
  - Updated repository URL to `https://github.com/SemClone/osslili`
  - Renamed main Python package directory from `semantic_copycat_oslili` to `osslili`
  - Updated all documentation, configuration files, and scripts
  - Simplified project description to "Open Source License Identification Library"

### Technical
- **Package Structure**: Completely reorganized package structure for the new name
- **Import Compatibility**: All import statements updated to use new package name
- **Documentation**: Updated all references across README, docs, and examples

## [1.5.5] - 2025-10-24

### Fixed
- **False Positive Copyright Detection**: Eliminated false positive copyright holder detections
  - Fixed overly broad regex patterns that captured programming language constructs
  - Added filtering for Fortran data types (integer*1, character) being detected as copyright holders
  - Enhanced filtering for Python code fragments (is not None, or sig_pattern, is np, is not np)
  - Improved regex patterns to stop at programming keywords (is, or, and)
  - Added exact match filtering for known false positive patterns
  - Better handling of contributor phrases like "and individual contributors"

### Improved
- **Copyright Extraction Accuracy**: More precise copyright holder identification with significantly fewer false positives
- **Code Pattern Detection**: Enhanced recognition of programming language constructs to prevent them from being interpreted as copyright information

## [1.5.4] - 2025-10-24

### Fixed
- **False Positive License Detection**: Significantly reduced false positive license detections
  - Fixed overly broad keyword patterns for Python-2.0, ISC, and Perl licenses
  - Enhanced context validation to require license-specific contexts for matches
  - Added filtering for generic programming language names being detected as licenses
  - Improved ISC license pattern specificity to require actual ISC license text
  - Strengthened validation to prevent common programming terms from being flagged as licenses

### Improved
- **License Detection Accuracy**: More precise detection with fewer false positives while maintaining legitimate detection coverage
- **Context Checking**: Enhanced validation that license keywords appear in actual license contexts rather than general code comments

## [1.5.3] - 2025-10-21

### Added
- **Evidence Detail Levels**: New `--evidence-detail` CLI option with 4 levels for controlling output verbosity
  - `minimal`: Just license counts (compact 1KB output)
  - `summary`: Adds detection method breakdown (1KB output)
  - `detailed`: Includes sample evidence (72KB output) - default
  - `full`: Complete evidence (several MB output)
- **License Normalizer Utility**: New utility class for consistent license ID normalization
- **Regex Pattern Matcher**: Optimized regex matching with lookup tables for better performance

### Fixed
- **Critical Deduplication Bug**: Fixed license detection deduplication that was discarding 99% of detections
  - Changed deduplication key from (license_id, confidence) to (license_id, confidence, source_file)
  - Increases detection coverage from ~1% to 99%+ of expected files
- **File Readability Detection**: Enhanced detection for better source file coverage
  - Added more permissive encoding detection (UTF-8, Latin-1, cp1252, ISO-8859-1)
  - Improved binary file detection with magic number signatures
  - Better handling of files with mixed encodings

### Improved
- **License Detection Coverage**: Reduced false negatives while maintaining low false positive rate
  - Reduced license text indicator threshold from 3 to 1 for better coverage
  - Added validation filtering to reduce false positives
  - Enhanced match type categorization (license_file, spdx_identifier, package_metadata, etc.)
- **Performance Optimizations**: Maintained ~117 files/second processing speed
  - Memory-efficient streaming processing for large files
  - Optimized regex pattern matching with lookup tables
  - Parallel processing improvements

### Changed
- **Evidence Formatter**: Enhanced with detail level filtering and better match type descriptions
- **License Detector**: Improved categorization logic and false positive filtering

## [1.5.1] - 2025-10-17

### Fixed
- **Copyright Detection**: Fixed overly aggressive filtering of copyright holders (issue #32)
  - Copyright holders containing words like "Test", "Demo", etc. are now correctly detected when part of legitimate names
  - "Test Corporation", "TestCo Inc", and similar names are now properly recognized
  - Only standalone test/demo placeholders are filtered out (e.g., just "test" or "demo")
  - Maintains filtering of actual placeholder text while allowing real organizations with these words

## [1.5.0] - 2025-10-15

### Added
- **Enhanced License Detection Accuracy**: Significantly improved license detection with multi-pattern support (PR #30, issue #29)
  - Multi-line pattern detection for licenses split across lines
  - Fuzzy matching for common typos (e.g., "Lisense" to "License")
  - Version suffix handling (GPLv2+ to GPL-2.0-or-later)
  - License keyword detection with 47 comprehensive patterns
  - Support for detecting licenses in all file types
- **Comprehensive Benchmark**: Added detailed comparison with ScanCode Toolkit
  - Performance comparison showing 1.8x-30x faster execution
  - Detection accuracy analysis with feature comparison matrix
  - Use case recommendations for both tools

### Improved
- **4-Tier License Detection**: All detection methods now engage for maximum accuracy
  - Hash matching for exact license files
  - Dice-Sørensen similarity for text similarity
  - TLSH fuzzy hashing for variant detection
  - Enhanced regex patterns for edge cases
- **Edge Case Handling**: Fixed detection for numerous previously failing cases
  - Python Software Foundation License full phrase
  - GNU Lesser General Public License v2.1
  - Generic GPL references with context-aware version detection
  - MIT licenses in copyright lines
  - Apache License with newlines in header
- **Pattern Library**: Integrated patterns from scancode-licensedb
  - Added 47+ license patterns for comprehensive coverage
  - Improved detection for permissive, copyleft, and proprietary licenses
  - Better handling of license variations and aliases

### Fixed
- **License Normalization**: Improved SPDX ID normalization
  - GNU-GPL-v2 to GPL-2.0
  - GPLv2+ to GPL-2.0-or-later
  - Better handling of version suffixes and variations
- **False Negative Reduction**: Reduced false negative rate from 46.7% to near 0%
  - Previously undetected licenses now properly identified
  - Improved coverage across different file types and formats

### Performance
- **Copyright Extraction**: 26x more comprehensive than comparable tools
- **Speed**: Maintained 1.8x-30x faster performance while improving accuracy
- **Scalability**: Successfully tested on large codebases (FFmpeg-8.0)

## [1.4.1] - 2025-10-12

### Fixed
- **pyproject.toml PEP 639 File Reference**: Fixed license detection from `license = {file = "LICENSE"}` format
  - Changed from non-existent `_detect_license_from_text()` to proper `_detect_from_full_text()` method
  - Now correctly reads and detects licenses from referenced files in pyproject.toml
  - Properly sets category as DECLARED for licenses from metadata file references
  - Added debug logging when referenced license file doesn't exist

### Removed
- **Notices Output Format**: Removed human-readable notices format to focus on scanning and verification
  - Removed `notices_formatter.py` module
  - Removed `generate_notices()` method from LicenseCopyrightDetector
  - Removed notices option from CLI output formats
  - Updated documentation to remove references to notices format
  - This simplifies the codebase and clarifies the tool's primary purpose as a scanner/verifier

## [1.4.0] - 2025-10-12

### Added
- **Source Header License Detection in Metadata Files**: Extract SPDX tags and license references from comments/headers
  - Detects licenses in XML comments (pom.xml)
  - Detects licenses in Python comments (setup.py, setup.cfg)
  - Detects licenses in TOML comments (Cargo.toml)
  - Detects licenses in Ruby comments (*.gemspec)
  - New `_extract_header_licenses()` method for comprehensive header scanning
- **Enhanced Package Metadata Support**: Added extraction methods for additional formats
  - Full support for package.json (Node.js) with SPDX expressions and arrays
  - Full support for composer.json (PHP) with comment cleaning
  - Improved extraction from all major package formats
- **Fast-path Metadata API**: New `extract_package_metadata()` method for metadata-only extraction
  - Skips full text analysis for faster processing
  - Supports all major package metadata formats
  - Returns licenses from both structured metadata and source headers

### Improved
- **Intelligent License Deduplication**: Smart handling when same license found in multiple locations
  - Prefers metadata version over header version as more authoritative
  - Prevents duplicate licenses in results
  - Tracks licenses by (spdx_id, match_type) for accurate deduplication
- **Python Classifier Extraction**: Fixed to handle both quoted and unquoted formats
  - Works with setup.py quoted classifiers
  - Works with setup.cfg unquoted classifiers
  - Properly extracts OSI Approved licenses from trove classifiers
- **File Pattern Matching**: Enhanced to handle temporary files and various naming conventions
  - Supports files ending with metadata names (e.g., temp_xyz.package.json)
  - Better handling of edge cases in file detection
- **Gemspec and Cargo.toml Processing**: Added duplicate prevention
  - Tracks found licenses to avoid duplicates
  - Handles both single and array license declarations

### Fixed
- **Duplicate License Detection**: Resolved issues with licenses appearing multiple times
  - Fixed gemspec pattern matching causing duplicates
  - Fixed Cargo.toml SPDX expression parsing duplicates
  - Improved overall deduplication logic

## [1.3.6] - 2025-09-06

### Added
- **Tier 0 Exact Hash Matching**: Added SHA-256 and MD5 hash matching as the first detection tier
  - Pre-computed hashes for all 699 SPDX licenses
  - Support for license variants and aliases
  - 100% confidence for exact matches
  - New `DetectionMethod.HASH` enum value
- **Hash Inventory System**: Comprehensive hash inventory for license matching
  - Standard SPDX license hashes
  - Common variants (e.g., gradle-wrapper Apache-2.0)
  - Hash lookup tables for fast matching
  - Support for hash collisions (e.g., GPL versions)

### Improved
- **Detection Tier Reorganization**: Four-tier system: Hash → Dice-Sørensen → TLSH → Regex
  - Exact hash matching runs first for perfect matches
  - Dice-Sørensen no longer requires TLSH confirmation for >95% confidence
  - Better performance and accuracy
- **Apache-2.0 vs Pixar Disambiguation**: Special handling for Modified Apache 2.0 License
  - Prefers Apache-2.0 over Pixar when Dice-Sørensen scores are within 1%
  - Fixes issue #16 where Apache-2.0 was incorrectly detected as Pixar
  - Handles gradle-wrapper.jar Apache license variant correctly

### Fixed
- **TLSH Hash Collision**: Resolved Apache-2.0 being misidentified as Pixar license
  - TLSH hashes were too similar (distance 8-24)
  - Now handled by preferring base license over modified versions
  - Exact hash matching bypasses fuzzy matching issues
- **License Loading**: Fixed `get_all_license_ids()` to properly handle dictionary format

## [1.3.5] - 2025-09-03

### Added
- **Expanded License File Detection**: Added comprehensive license file patterns
  - GPL variants (`*GPL*`)
  - Copyleft files (`*COPYLEFT*`)
  - EULA files (`*EULA*`)
  - Commercial license files (`*COMMERCIAL*`)
  - Agreement files (`*AGREEMENT*`)
  - Bundle license files (`*BUNDLE*`)
  - Third-party license files (`*THIRD-PARTY*`, `*THIRD_PARTY*`)
  - Legal documents (`LEGAL*`)

### Improved
- **License Detection Coverage**: Extended fallback keyword detection to include: gpl, copyleft, eula, commercial, agreement, bundle, third-party, third_party
- **Pattern Flexibility**: All patterns now support characters before/after keywords (., -, _, etc.)

## [1.3.4] - 2025-09-02

### Added
- **Enhanced Archive Support**: Added support for additional archive formats:
  - Java archives (.jar, .war, .ear)
  - .NET packages (.nupkg)
  - Ruby gems (.gem) with nested archive extraction
  - Rust crates (.crate)

### Improved
- **Copyright Detection Completeness**: Removed artificial 20-file limit for source file scanning
  - Now scans ALL source files (.c, .h, .py, .js, .java, .cpp, .go, .rs, .ts, .tsx, .jsx)
  - Improves detection from ~12 to 700+ copyright statements on large codebases
  - Maintains 94% accuracy with comprehensive false positive filtering
- **File Scanner Reliability**: Fixed SafeFileScanner visited_inodes persistence bug
  - Eliminates false "symlink loop" warnings on subsequent scans
  - Enables proper scanning of multiple file extensions

### Fixed
- **Single File Detection**: Enhanced handling of directly-passed files as potential license content
- **MIT License Detection**: Improved regex patterns for partial MIT license text recognition
- **Archive Extraction**: Better support for nested archive formats and Ruby gem structure

### Repository
- **Cleanup**: Removed test-packages/ directory and added to .gitignore to keep repository clean

## [1.3.3] - 2025-08-30

### Improved
- **Confidence Scoring**: Enhanced regex-based license detection with context-aware confidence scoring
  - License files: 100% confidence for exact matches
  - Full license headers in source files: 90% confidence
  - License references: 30-50% confidence based on pattern matches
  - Better distinction between comprehensive headers vs. brief references
- **Categorization Logic**: Improved license categorization to distinguish between full license headers and simple references
- **Pattern Matching**: Enhanced regex detection to track exact number of patterns matched for more accurate confidence scoring

### Technical Changes
- Added `_adjust_regex_confidence` method for intelligent confidence adjustment
- Enhanced pattern matching to differentiate license headers from references
- Improved license categorization logic for better accuracy assessment

## [1.3.2] - 2025-08-30

### Fixed
- **CLI Options**: Fixed decorator ordering to enable `-f` output format option
- **Documentation**: Updated README with complete feature list and examples

### Changed
- **Version Option**: Moved to proper position in CLI decorator chain

## [1.3.1] - 2025-08-30

### Added
- **Archive Extraction**: Restored archive extraction capability with configurable `--max-extraction-depth` option for nested archives
- **Cache Functionality**: Added caching support with `--cache-dir` option to speed up repeated scans
- **Version Command**: Added `--version` option to display the tool version
- **Output Formats**: Restored support for multiple output formats:
  - `kissbom`: Simple JSON format with packages and licenses
  - `cyclonedx-json`: CycloneDX SBOM in JSON format
  - `cyclonedx-xml`: CycloneDX SBOM in XML format
  - `notices`: Human-readable legal notices with license texts

### Changed
- **Directory Traversal**: Restored `--max-depth` option with enhanced symlink loop protection using inode tracking
- **Safe File Scanner**: Implemented SafeFileScanner class for secure directory traversal with depth limiting

### Fixed
- **Missing Features**: Restored several features that were accidentally removed in previous refactoring
- **Documentation**: Updated all documentation to reflect current functionality
- **Code Quality**: Removed unused `get_license_aliases` method and other dead code

## [1.2.9] - 2025-08-30

### Added
- **License Hierarchy System**: Categorizes licenses as 'declared', 'detected', or 'referenced' for better understanding of license provenance
- **Enhanced Output Format**: Summary now shows declared_licenses, detected_licenses, and referenced_licenses separately
- **Copyright Holders List**: Summary includes unique list of copyright holders
- **Match Type Field**: Each license detection includes match_type (e.g., license_file, spdx_identifier, text_similarity)

### Changed
- **Class Renamed**: Main class renamed from `LegalAttributionGenerator` to `LicenseCopyrightDetector` to better reflect its functionality (BREAKING CHANGE)
- **Model Renamed**: `AttributionResult` renamed to `DetectionResult` to better reflect its purpose (BREAKING CHANGE)

### Fixed
- **Copyright False Positives**: Improved filtering to exclude placeholders like "YYYY Name", "TODO", and code fragments
- **Invalid Copyright Holders**: Added detection for fragments like "in result", "lines that vary", "detector", "generator"
- **Placeholder Detection**: Better filtering of template placeholders in copyright statements

### Removed
- **Dead Code**: Removed unused `max_extraction_depth` configuration option
- **Unused Import**: Removed unused `fuzz_process` import from license_detector.py
- **Misleading Function Name**: Renamed `_process_extracted_package()` to `_process_local_path()`
- **Test Files**: Removed development test files from repository
- **Build Directory**: Cleaned up build artifacts
- **Duplicate Method**: Consolidated duplicate `_is_license_file` implementations

## [1.2.8] - 2025-08-29

### Fixed
- **License Expression Parsing**: Fixed incorrect splitting of "or later" suffix (e.g., "LGPL 3 or later" now correctly parsed as single license)
- **False Positive Detection**: Added filtering for TODO, FIXME, XXX, and placeholder text that were incorrectly detected as licenses
- **MIT License Detection**: Added quick pattern matching for MIT licenses before TLSH to prevent misidentification as JSON
- **Test File Scanning**: Fixed overly aggressive filtering that skipped all files with "test_" prefix, now only skips specific test patterns

### Improved
- **Detection Accuracy**: Significantly reduced false positives in license identification
- **Expression Handling**: Better handling of license suffixes like "or later", "or-later", "+"

## [1.2.7] - 2025-08-29

### Added
- **Dynamic License Normalization**: Uses 1841+ name mappings from bundled SPDX data instead of hardcoding
- **Properties for SPDX Data**: Added `aliases` and `name_mappings` properties to SPDXLicenseData class
- **Comprehensive Normalization**: Support for 99.1% of SPDX licenses (694/700) with intelligent normalization
- **Better Version Handling**: GPL/LGPL/AGPL versions properly normalized (e.g., GPL-3 → GPL-3.0)
- **Common Aliases**: Added fallback aliases for "New BSD", "Simplified BSD", "CC0", etc.

### Changed
- **SPDX Tag Detection**: Improved regex to capture multi-word licenses like "Apache 2.0", "GPL v3"
- **Normalization Method**: Refactored to use data-driven approach with bundled mappings
- **Import Organization**: Moved module-level imports to avoid inline imports

### Fixed
- **Duplicate Methods**: Removed duplicate `_normalize_text()` and `get_all_license_ids()` methods in spdx_licenses.py
- **Dead Code**: Removed unused methods and unreachable code sections
- **Import Issues**: Fixed repeated inline imports of `re` module
- **License Detection**: Fixed normalization for licenses with spaces (e.g., "Apache 2.0" → "Apache-2.0")
- **Suffix Handling**: Proper handling of deprecated + suffix licenses (GPL-3.0+ → GPL-3.0-or-later)

### Performance
- **Code Quality**: Reduced duplication and improved maintainability
- **Normalization Coverage**: Increased from ~12% to 99.1% for SPDX license ID variations

## [1.2.6] - 2025-08-17

### Changed
- **Project Description**: Updated to "Semantic Copycat Open Source License Identification Library"

## [1.2.5] - 2025-08-17

### Added
- **TLSH Confirmation Mechanism**: Dice-Sørensen matches are now confirmed with TLSH to prevent false positives
- **Required TLSH Dependency**: `python-tlsh>=4.5.0` is now a required dependency (was optional)
- **Enhanced Documentation**: Comprehensive explanation of three-tier detection system in README and docs
- **TLSH Confirmation Method**: New `confirm_license_match()` method with configurable threshold

### Changed
- **TLSH Thresholds**: Strict threshold (30) for standalone detection, relaxed (100) for confirmation
- **Detection Flow**: Tier 1 now includes TLSH confirmation for all Dice-Sørensen matches
- **Documentation**: Updated README with detailed "How It Works" section
- **Project Status**: Updated CLAUDE.md to reflect v1.2.5 improvements

### Fixed
- **False Positive Prevention**: TLSH confirmation significantly reduces false positives
- **Code Cleanup**: Removed 8 unused utility methods from ConfigLoader and InputProcessor

### Performance
- **Testing Coverage**: Validated on 10+ language ecosystems with 97-100% accuracy
- **Detection Accuracy**: Maintained 97%+ accuracy while reducing false positives

## [1.2.0] - 2025-08-16

### Added
- **Parallel Processing**: Multi-threaded scanning with ThreadPoolExecutor for significantly faster performance
- **Enhanced License Detection**: Improved regex patterns for package metadata (package.json, METADATA, pyproject.toml)
- **Smart File Handling**: Intelligent sampling for large files (>10MB) without timeouts
- **Complete File Coverage**: Scans ALL readable text files, not limited to specific extensions
- **700+ SPDX Support**: Full support for all SPDX license IDs with alias normalization
- **Text Normalization**: Added `_normalize_text()` method for consistent license comparison
- **Configurable Threading**: CLI option `--threads` to control parallel processing (default: 4)
- **Better Metadata Detection**: 
  - Detects `"license": "MIT"` in package.json
  - Detects `License-Expression: MIT` in Python METADATA files
  - Detects `license = {text = "Apache-2.0"}` in pyproject.toml

### Changed
- **File Processing**: Now uses parallel processing for license and copyright detection
- **File Reading**: Smart reading strategy - full read for <10MB, sampling for larger files
- **Error Handling**: Improved with specific exception types and per-file timeouts (30s)
- **License Matching**: Enhanced normalization handles more variations (Apache 2.0 → Apache-2.0)
- **False Positive Filtering**: Better detection and filtering of code patterns in both license and copyright extraction

### Fixed
- Removed duplicate `_normalize_license_id()` method
- Removed unused imports (`time`, redundant `fnmatch`)
- Fixed bare `except:` clauses with specific exception types
- Removed redundant `hasattr()` checks
- Improved copyright holder validation to filter more false positives

### Performance Improvements
- Parallel file processing reduces scan time by up to 75% on multi-core systems
- Smart file sampling for large files prevents memory issues
- Deduplication during processing reduces post-processing time
- Lazy loading of SPDX data improves startup time

## [1.1.2] - 2025-01-16

### Breaking Changes
- **Removed package URL (purl) support**: Tool no longer downloads or processes packages from PyPI, npm, etc.
- **Removed external API integrations**: ClearlyDefined, PyPI, and npm APIs have been removed
- **Focus on local scanning only**: Tool now exclusively scans local directories and files

### Changed
- **Core functionality**: Refocused on local source code license and copyright identification
- **Input handling**: Now only accepts local file paths and directories
- **Attribution format**: Changed from purl-based to path-based attribution
- **Dependencies**: Removed packageurl-python dependency

### Removed
- Package downloading and extraction capabilities
- Purl file parsing functionality  
- External API data sources (ClearlyDefined, PyPI, npm)
- Network timeout configuration
- Online/offline mode distinction (tool is always offline)

### What the Tool Now Does
- Scans local source code for SPDX license identification
- Extracts copyright information from local files
- Identifies license files and matches them with bundled SPDX data
- Uses multi-tier detection: Dice-Sørensen similarity, TLSH fuzzy hashing, and regex patterns
- Generates attribution reports in KissBOM, CycloneDX, and human-readable formats

## [1.1.1] - 2025-01-16

### Added
- **Offline-first operation**: Tool now works offline by default, no API calls unless explicitly requested
- **`--online` flag**: New CLI option to enable external API sources (ClearlyDefined, PyPI, npm)
- **Bundled SPDX license data**: Package includes 700+ SPDX license definitions with full text for 40+ common licenses
- **License text in notices**: Human-readable notices now include full license text
- **Debug logging**: Added comprehensive debug logging for troubleshooting copyright extraction
- **Copyright validation**: Improved filtering of invalid copyright patterns (URLs, code snippets, etc.)
- **Build automation**: Scripts to update SPDX license data during package build

### Changed
- **Default behavior**: Changed from online-first to offline-first operation
- **API usage**: External APIs now supplement rather than replace local analysis
- **Copyright extraction**: Significantly improved accuracy with better pattern matching and deduplication
- **Logging**: Reduced verbosity in normal mode, cleaner output

### Fixed
- **Copyright false positives**: Fixed extraction of code patterns as copyright holders
- **Duplicate copyrights**: Improved deduplication of copyright holders with variations
- **Invalid domains**: Fixed "domain.invalid" and URL patterns appearing in copyright
- **SSL warnings**: Suppressed urllib3 SSL warnings on macOS systems
- **Package build**: Fixed missing submodules in wheel distribution

### Technical Improvements
- **Performance**: Faster processing without network calls in default mode
- **Reliability**: Works without internet connection
- **Privacy**: No data sent to external services by default
- **Size**: Package includes all necessary data (1.5MB of SPDX licenses)

## [0.1.0] - 2025-01-15

### Initial Release
- **Multi-source input**: Process single purls, purl files, or local directories
- **Three-tier license detection**: 
  - Tier 1: Dice-Sørensen similarity (97% threshold)
  - Tier 2: TLSH fuzzy hashing
  - Tier 3: Regex pattern matching
- **Copyright extraction**: Pattern-based extraction from source files
- **Multiple output formats**: KissBOM, CycloneDX, human-readable notices
- **External data sources**: Integration with ClearlyDefined, PyPI, npm APIs
- **CLI and library interfaces**: Use as command-line tool or Python library
- **Multi-threaded processing**: Configurable parallel processing
- **Configuration system**: YAML-based configuration with environment variables

### Package Metadata
- Author: Oscar Valenzuela B.
- Email: oscar.valenzuela.b@gmail.com
- License: Apache-2.0
- Repository: https://github.com/oscarvalenzuelab/semantic-copycat-oslili