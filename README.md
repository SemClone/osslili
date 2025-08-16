# semantic-copycat-oslili

A high-performance tool for identifying licenses and copyright information in local source code, producing detailed evidence of where licenses are detected with support for all 700+ SPDX license identifiers.

## What It Does

`semantic-copycat-oslili` analyzes local source code to produce evidence of:
- **License detection** - Shows which files contain which licenses with confidence scores
- **SPDX identifiers** - Detects SPDX-License-Identifier tags in ALL readable files
- **Package metadata** - Extracts licenses from package.json, pyproject.toml, METADATA files
- **Copyright statements** - Extracts copyright holders and years with intelligent filtering

The tool outputs standardized JSON evidence showing exactly where each license was detected, the detection method used, and confidence scores.

### Why Use This Tool?

- **Compliance Made Easy**: Automatically generate attribution notices required by open source licenses
- **Complete Coverage**: Scans ALL readable text files, not limited to specific extensions
- **High Performance**: Parallel processing with configurable thread count for fast scanning
- **700+ SPDX Licenses**: Full support for all SPDX license IDs with alias normalization
- **Smart File Handling**: Intelligently handles large files (>10MB) without timeouts
- **Accurate Detection**: Three-tier detection system with 97%+ accuracy
- **Offline Operation**: Works without internet - all SPDX license data is bundled
- **Cross-Platform**: Same output format for Python, npm, Go, Ruby, and other package types

## Key Features

- **Evidence-based output**: Shows exact file paths, confidence scores, and detection methods
- **Parallel processing**: Multi-threaded scanning with configurable thread count
- **Three-tier detection**: 
  - Dice-Sørensen similarity matching (97% threshold)
  - TLSH fuzzy hashing (optional)
  - Regex pattern matching
- **Smart normalization**: Handles license variations and common aliases
- **No file limits**: Processes files of any size with intelligent sampling
- **Enhanced metadata support**: Detects licenses in package.json, METADATA, pyproject.toml
- **False positive filtering**: Advanced filtering for code patterns and invalid matches

## Installation

```bash
pip install semantic-copycat-oslili
```

For ML-based license detection:
```bash
pip install semantic-copycat-oslili[ml]
```

For CycloneDX support:
```bash
pip install semantic-copycat-oslili[cyclonedx]
```

## Usage

### CLI Usage

```bash
# Scan a directory and see evidence
oslili /path/to/project

# Scan with parallel processing (4 threads)
oslili ./my-project --threads 4

# Scan a specific file
oslili /path/to/LICENSE

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
        "match_type": "text_similarity",
        "description": "Text matches Apache-2.0 license (98.8% similarity)"
      },
      {
        "file": "/path/to/project/package.json",
        "detected_license": "Apache-2.0",
        "confidence": 1.0,
        "detection_method": "tag",
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
    "licenses_found": {
      "Apache-2.0": 2
    },
    "copyrights_found": 1
  }
}
```

## Performance

The tool is optimized for speed and efficiency:

- **Parallel Processing**: Uses multiple threads to scan files concurrently
- **Smart Sampling**: Large files (>10MB) are intelligently sampled rather than fully read
- **Efficient Matching**: Pre-computed TLSH hashes and normalized text for fast comparison
- **Memory Efficient**: Processes files incrementally without loading everything into memory

Performance benchmarks on a typical project:
- Small project (100 files): ~1 second
- Medium project (1,000 files): ~5 seconds  
- Large project (10,000 files): ~30 seconds

Use `--threads N` to control parallelism based on your system.

### Library Usage

```python
from semantic_copycat_oslili import LegalAttributionGenerator

# Initialize generator
generator = LegalAttributionGenerator()

# Process a local directory
result = generator.process_local_path("/path/to/source")

# Process a single file  
result = generator.process_local_path("/path/to/LICENSE")

# Generate evidence output
evidence = generator.generate_evidence([result])
print(evidence)

# Access results
for license in result.licenses:
    print(f"License: {license.spdx_id} ({license.confidence:.0%} confidence)")
for copyright in result.copyrights:
    print(f"Copyright: © {copyright.holder}")
```

## License Detection

The package uses a three-tier license detection system:

1. **Tier 1**: Dice-Sørensen similarity (97% threshold)
2. **Tier 2**: TLSH fuzzy hashing (97% threshold)
3. **Tier 3**: Machine learning or regex pattern matching

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
max_extraction_depth: 10
thread_count: 4
custom_aliases:
  "Apache 2": "Apache-2.0"
  "MIT License": "MIT"
```

## Documentation

- [Full Usage Guide](docs/USAGE.md) - Comprehensive usage examples and configuration
- [API Reference](docs/API.md) - Python API documentation and examples
- [Changelog](CHANGELOG.md) - Version history and changes
