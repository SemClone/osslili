# OSS License & Copyright Detector (osslili)

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![PyPI version](https://img.shields.io/pypi/v/osslili.svg)](https://pypi.org/project/osslili/)

A high-performance tool for identifying licenses and copyright information in local source code. Produces detailed evidence of where licenses are detected with support for all 700+ SPDX license identifiers, enabling comprehensive compliance documentation for the SEMCL.ONE ecosystem.

## Features

- **Three-Tier License Detection**: Dice-Sørensen similarity, TLSH fuzzy hashing, and regex pattern matching
- **Evidence-Based Output**: Exact file paths, confidence scores, and detection methods
- **700+ SPDX Licenses**: Comprehensive support for all SPDX license identifiers
- **SEMCL.ONE Integration**: Works seamlessly with purl2notices, ospac, and other ecosystem tools

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
pip install osslili
```

For development:
```bash
git clone https://github.com/SemClone/osslili.git
cd osslili
pip install -e .
```

## Quick Start

```bash
# Scan current directory for licenses
osslili .

# Generate SBOM with license evidence
osslili ./my-project -f cyclonedx-json -o sbom.json
```

## Usage

### CLI Usage

```bash
# Scan a directory and see evidence (default format)
osslili /path/to/project

# Generate different output formats
osslili ./my-project -f kissbom -o kissbom.json
osslili ./my-project -f cyclonedx-json -o sbom.json
osslili ./my-project -f cyclonedx-xml -o sbom.xml

# Scan with parallel processing (4 threads)
osslili ./my-project --threads 4

# Scan with limited depth (only 2 levels deep)
osslili ./my-project --max-depth 2

# Extract and scan archives
osslili package.tar.gz --max-extraction-depth 2

# Use caching for faster repeated scans
osslili ./my-project --cache-dir ~/.cache/osslili

# Check version
osslili --version

# Save results to file
osslili ./my-project -o license-evidence.json

# With custom configuration and verbose output
osslili ./src --config config.yaml --verbose

# Debug mode for detailed logging
osslili ./project --debug
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
from osslili import LicenseCopyrightDetector

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

## Integration with SEMCL.ONE

OSS License & Copyright Detector is a core component of the SEMCL.ONE ecosystem:

- Works with **purl2notices** for comprehensive legal notice generation
- Integrates with **ospac** for policy-based compliance evaluation
- Supports **ossnotices** for simplified attribution documentation
- Complements **upmex** for package metadata extraction workflows

## Configuration

Create a `config.yaml` file:

```yaml
similarity_threshold: 0.97
max_recursion_depth: 10
max_extraction_depth: 10
thread_count: 4
cache_dir: "~/.cache/osslili"
custom_aliases:
  "Apache 2": "Apache-2.0"
  "MIT License": "MIT"
```

## Documentation

- [User Guide](docs/USAGE.md) - Comprehensive usage examples and configuration
- [API Reference](docs/API.md) - Python API documentation and examples
- [SPDX Updates](docs/SPDX.md) - How to update SPDX license data
- [Performance Benchmarks](docs/BENCHMARK_SCANCODE.md) - Comparison with other tools

## Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for details on:
- Code of conduct
- Development setup
- Submitting pull requests
- Reporting issues

## Support

For support and questions:
- [GitHub Issues](https://github.com/SemClone/osslili/issues) - Bug reports and feature requests
- [Documentation](https://github.com/SemClone/osslili) - Complete project documentation
- [SEMCL.ONE Community](https://semcl.one) - Ecosystem support and discussions

## License

Apache License 2.0 - see [LICENSE](LICENSE) file for details.

## Authors

See [AUTHORS.md](AUTHORS.md) for a list of contributors.

---

*Part of the [SEMCL.ONE](https://semcl.one) ecosystem for comprehensive OSS compliance and code analysis.*
