# semantic-copycat-oslili

A powerful, accurate, and fast tool for identifying licenses and copyright information in local source code. Perfect for open source compliance, license auditing, and SBOM generation.

## What It Does

`semantic-copycat-oslili` automatically analyzes local source code to extract:
- **License information** - Detects and identifies SPDX licenses with 97%+ accuracy using regex and fuzzy hashing
- **Copyright statements** - Intelligently extracts copyright holders and years
- **Attribution notices** - Generates legally compliant attribution documentation

The tool scans local directories and files, identifying license files and extracting copyright information, then outputs attribution data in multiple formats suitable for compliance documentation, SBOMs, and legal notices.

### Why Use This Tool?

- **Compliance Made Easy**: Automatically generate attribution notices required by most open source licenses
- **Accurate Detection**: Three-tier license detection system minimizes false positives
- **Offline Operation**: Works without internet - all SPDX license data is bundled
- **Multiple Formats**: Export to KissBOM, CycloneDX, or human-readable notices
- **Fast & Efficient**: Multi-threaded processing handles large codebases quickly
- **Smart Validation**: Filters out false positives in copyright detection

## Key Features

- **Offline Operation**: No internet required - includes 700+ SPDX licenses
- **Local Scanning**: Process local directories and files
- **High Accuracy**: Multi-tier detection with Dice-Sørensen, TLSH, and regex
- **Full License Text**: Notices include complete license text for compliance
- **Fast Processing**: Multi-threaded analysis of multiple packages
- **Smart Extraction**: Validated copyright detection eliminates false positives

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
# Process local directory
oslili /path/to/source -f notices -o NOTICE.txt

# Scan a specific file
oslili /path/to/file.py -f kissbom -o attribution.json

# Generate human-readable notices with full license text
oslili ./my-project -f notices -o NOTICE.txt

# Export to CycloneDX format
oslili ./src -f cyclonedx-json -o sbom.json

# With custom configuration and verbose output
oslili ./project --config config.yaml --verbose
```

### Library Usage

```python
from semantic_copycat_oslili import LegalAttributionGenerator

# Initialize generator
generator = LegalAttributionGenerator()

# Process a local directory
result = generator.process_local_path("/path/to/source")

# Process a single file
result = generator.process_local_path("/path/to/file.py")

# Generate outputs
kissbom = generator.generate_kissbom([result])
notices = generator.generate_notices([result])

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

## Output Formats

- **KissBOM**: Enriched JSON format with package, license, and copyright information
- **CycloneDX**: Standard SBOM format (JSON/XML)
- **Legal Notices**: Human-readable attribution text

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
