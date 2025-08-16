# semantic-copycat-oslili

A focused tool for identifying licenses and copyright information in local source code, producing evidence of where licenses are detected.

## What It Does

`semantic-copycat-oslili` analyzes local source code to produce evidence of:
- **License detection** - Shows which files contain which licenses (e.g., "LICENSE contains Apache-2.0 text")
- **SPDX identifiers** - Detects SPDX-License-Identifier tags in source files, documentation, and metadata
- **Copyright statements** - Extracts copyright holders and years from source files

The tool outputs JSON evidence showing exactly where each license was detected and how it was matched.

### Why Use This Tool?

- **Compliance Made Easy**: Automatically generate attribution notices required by most open source licenses
- **Accurate Detection**: Three-tier license detection system minimizes false positives
- **Offline Operation**: Works without internet - all SPDX license data is bundled
- **Multiple Formats**: Export to KissBOM, CycloneDX, or human-readable notices
- **Fast & Efficient**: Multi-threaded processing handles large codebases quickly
- **Smart Validation**: Filters out false positives in copyright detection

## Key Features

- **Evidence-based output**: Shows exactly where licenses are detected
- **Multi-method detection**: License text matching, SPDX identifiers, and pattern matching
- **Local scanning**: Analyzes files and directories on your filesystem
- **High accuracy**: 97%+ accuracy using Dice-Sørensen similarity and fuzzy hashing
- **Comprehensive coverage**: Detects licenses in source headers, LICENSE files, package.json, and more
- **Smart extraction**: Validated copyright detection with false positive filtering

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

# Scan a specific file
oslili /path/to/LICENSE

# Save results to file
oslili ./my-project -o license-evidence.json

# With custom configuration and verbose output
oslili ./src --config config.yaml --verbose
```

### Example Output

```json
{
  "scan_results": [{
    "path": "./project",
    "license_evidence": [
      {
        "file": "LICENSE",
        "detected_license": "Apache-2.0",
        "confidence": 0.98,
        "match_type": "license_text",
        "description": "File contains Apache-2.0 license text"
      },
      {
        "file": "src/main.py",
        "detected_license": "Apache-2.0",
        "confidence": 1.0,
        "match_type": "spdx_identifier",
        "description": "SPDX-License-Identifier: Apache-2.0 found"
      }
    ]
  }]
}
```

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
