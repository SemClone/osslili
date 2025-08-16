# Changelog

All notable changes to semantic-copycat-oslili will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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