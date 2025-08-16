# semantic-copycat-oslili

A powerful, accurate, and fast tool for generating legal attribution notices from software packages. Perfect for open source compliance, license auditing, and SBOM generation.

## What It Does

`semantic-copycat-oslili` automatically analyzes software packages to extract:
- **License information** - Detects and identifies licenses with 97%+ accuracy
- **Copyright statements** - Intelligently extracts copyright holders and years
- **Attribution notices** - Generates legally compliant attribution documentation

The tool processes packages from various sources (PyPI, npm, local directories) and outputs attribution data in multiple formats suitable for compliance documentation, SBOMs, and legal notices.

### Why Use This Tool?

- **Compliance Made Easy**: Automatically generate attribution notices required by most open source licenses
- **Accurate Detection**: Three-tier license detection system minimizes false positives
- **Offline Operation**: Works without internet - all SPDX license data is bundled
- **Multiple Formats**: Export to KissBOM, CycloneDX, or human-readable notices
- **Fast & Efficient**: Multi-threaded processing handles large codebases quickly
- **Smart Validation**: Filters out false positives in copyright detection

## Key Features

- **Offline-first**: No internet required - includes 700+ SPDX licenses
- **Universal Input**: Process package URLs, files, or local directories  
- **High Accuracy**: Three-tier detection with Dice-Sørensen, TLSH, and regex
- **Full License Text**: Notices include complete license text for compliance
- **Fast Processing**: Multi-threaded analysis of multiple packages
- **Smart Extraction**: Validated copyright detection eliminates false positives
- **Optional APIs**: Enable online mode for supplemental data when needed

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
# Process a single package URL (offline by default)
oslili pkg:pypi/requests@2.28.1

# Enable external API sources with --online
oslili pkg:pypi/requests@2.28.1 --online

# Process multiple packages from file
oslili packages.txt -f kissbom -o attribution.json

# Process local directory
oslili /path/to/source -f notices -o NOTICE.txt

# Generate human-readable notices with full license text
oslili pkg:npm/express@4.18.0 -f notices -o NOTICE.txt

# With custom configuration and verbose output
oslili pkg:npm/express@4.18.0 --config config.yaml --verbose
```

### Library Usage

```python
from semantic_copycat_oslili import LegalAttributionGenerator

# Initialize generator
generator = LegalAttributionGenerator()

# Process a package (offline by default)
result = generator.process_purl("pkg:pypi/requests@2.28.1")

# Process with external API sources
result = generator.process_purl("pkg:pypi/requests@2.28.1", use_external_sources=True)

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
network_timeout: 30
thread_count: 4
custom_aliases:
  "Apache 2": "Apache-2.0"
  "MIT License": "MIT"
```

## Documentation

- [Full Usage Guide](docs/USAGE.md) - Comprehensive usage examples and configuration
- [API Reference](docs/API.md) - Python API documentation and examples
- [Changelog](CHANGELOG.md) - Version history and changes
