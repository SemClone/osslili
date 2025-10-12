# semantic-copycat-oslili

A high-performance tool for identifying licenses and copyright information in local source code, producing detailed evidence of where licenses are detected with support for all 700+ SPDX license identifiers.

## What It Does

`semantic-copycat-oslili` analyzes local source code to produce evidence of:
- **License detection** - Shows which files contain which licenses with confidence scores
- **SPDX identifiers** - Detects SPDX-License-Identifier tags in ALL readable files
- **Package metadata** - Extracts licenses from package.json, pyproject.toml, METADATA files
- **Copyright statements** - Extracts copyright holders and years with intelligent filtering

The tool outputs standardized JSON evidence showing exactly where each license was detected, the detection method used, and confidence scores.

### Key Features

- **Evidence-based output**: Shows exact file paths, confidence scores, and detection methods
- **License hierarchy**: Categorizes licenses as declared vs detected vs referenced
- **Multiple output formats**: Evidence JSON, KissBOM, CycloneDX SBOM
- **Archive extraction**: Automatically extracts and scans zip, tar, and other archive formats
- **Caching support**: Speed up repeated scans with intelligent caching
- **Parallel processing**: Multi-threaded scanning with configurable thread count
- **Three-tier detection**: 
  - Dice-Sørensen similarity matching (97% threshold)
  - TLSH fuzzy hashing with confirmation
  - Regex pattern matching
- **Safe directory traversal**: Depth limiting and symlink loop protection
- **Smart normalization**: Handles license variations and common aliases
- **No file limits**: Processes files of any size with intelligent sampling
- **Enhanced metadata support**: Detects licenses in package.json, METADATA, pyproject.toml
- **False positive filtering**: Advanced filtering for code patterns and invalid matches

### How It Works

#### Three-Tier License Detection System

The tool uses a sophisticated multi-tier approach for maximum accuracy:

1. **Tier 1: Dice-Sørensen Similarity with TLSH Confirmation**
   - Compares license text using Dice-Sørensen coefficient (97% threshold)
   - Confirms matches using TLSH fuzzy hashing to prevent false positives
   - Achieves 97-100% accuracy on standard SPDX licenses

2. **Tier 2: TLSH Fuzzy Hash Matching**
   - Uses Trend Micro Locality Sensitive Hashing for variant detection
   - Catches license variants like MIT-0, BSD-2-Clause vs BSD-3-Clause
   - Pre-computed hashes for all 700+ SPDX licenses

3. **Tier 3: Pattern Recognition**
   - Regex-based detection for license references and identifiers
   - Extracts from comments, headers, and documentation

#### Additional Detection Methods

- **Package Metadata Scanning**: Detects licenses from package.json, composer.json, pyproject.toml, etc.
- **Copyright Extraction**: Advanced pattern matching with validation and deduplication
- **SPDX Identifier Detection**: Finds SPDX-License-Identifier tags in source files

## Installation

```bash
pip install semantic-copycat-oslili
```

### Required Dependencies

The package includes all necessary dependencies including `python-tlsh` for fuzzy hash matching, which is essential for accurate license detection and false positive prevention.

## Usage

### CLI Usage

```bash
# Scan a directory and see evidence (default format)
oslili /path/to/project

# Generate different output formats
oslili ./my-project -f kissbom -o kissbom.json
oslili ./my-project -f cyclonedx-json -o sbom.json
oslili ./my-project -f cyclonedx-xml -o sbom.xml

# Scan with parallel processing (4 threads)
oslili ./my-project --threads 4

# Scan with limited depth (only 2 levels deep)
oslili ./my-project --max-depth 2

# Extract and scan archives
oslili package.tar.gz --max-extraction-depth 2

# Use caching for faster repeated scans
oslili ./my-project --cache-dir ~/.cache/oslili

# Check version
oslili --version

# Save results to file
oslili ./my-project -o license-evidence.json

# With custom configuration and verbose output
oslili ./src --config config.yaml --verbose

# Debug mode for detailed logging
oslili ./project --debug
```

### Example Output

```json
{
  "scan_results": [{
    "path": "./project",
    "license_evidence": [
      {
        "file": "/path/to/project/LICENSE",
        "detected_license": "Apache-2.0",
        "confidence": 0.988,
        "detection_method": "dice-sorensen",
        "category": "declared",
        "match_type": "text_similarity",
        "description": "Text matches Apache-2.0 license (98.8% similarity)"
      },
      {
        "file": "/path/to/project/package.json",
        "detected_license": "Apache-2.0",
        "confidence": 1.0,
        "detection_method": "tag",
        "category": "declared",
        "match_type": "spdx_identifier",
        "description": "SPDX-License-Identifier: Apache-2.0 found"
      }
    ],
    "copyright_evidence": [
      {
        "file": "/path/to/project/src/main.py",
        "holder": "Example Corp",
        "years": [2023, 2024],
        "statement": "Copyright 2023-2024 Example Corp"
      }
    ]
  }],
  "summary": {
    "total_files_scanned": 42,
    "declared_licenses": {"Apache-2.0": 2},
    "detected_licenses": {},
    "referenced_licenses": {},
    "copyright_holders": ["Example Corp"]
  }
}
```


### Library Usage

```python
from semantic_copycat_oslili import LicenseCopyrightDetector

# Initialize detector
detector = LicenseCopyrightDetector()

# Process a local directory
result = detector.process_local_path("/path/to/source")

# Process a single file  
result = detector.process_local_path("/path/to/LICENSE")

# Generate different output formats
evidence = detector.generate_evidence([result])
kissbom = detector.generate_kissbom([result])
cyclonedx = detector.generate_cyclonedx([result], format_type="json")
cyclonedx_xml = detector.generate_cyclonedx([result], format_type="xml")

# Access results directly
for license in result.licenses:
    print(f"License: {license.spdx_id} ({license.confidence:.0%} confidence)")
    print(f"  Category: {license.category}")  # declared, detected, or referenced
for copyright in result.copyrights:
    print(f"Copyright: © {copyright.holder}")
```


## Output Format

The tool outputs JSON evidence showing:
- **File path**: Where the license was found
- **Detected license**: The SPDX identifier of the license
- **Confidence**: How confident the detection is (0.0 to 1.0)
- **Match type**: How the license was detected (license_text, spdx_identifier, license_reference, text_similarity)
- **Description**: Human-readable description of what was found

## Configuration

Create a `config.yaml` file:

```yaml
similarity_threshold: 0.97
max_recursion_depth: 10
max_extraction_depth: 10
thread_count: 4
cache_dir: "~/.cache/oslili"
custom_aliases:
  "Apache 2": "Apache-2.0"
  "MIT License": "MIT"
```

## Documentation

- [Full Usage Guide](docs/USAGE.md) - Comprehensive usage examples and configuration
- [API Reference](docs/API.md) - Python API documentation and examples
- [Changelog](CHANGELOG.md) - Version history and changes
