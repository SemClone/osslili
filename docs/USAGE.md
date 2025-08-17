# OSLILI Usage Guide

This guide provides comprehensive instructions for using the `semantic-copycat-oslili` package to identify licenses and extract copyright information from local source code.

## Table of Contents

1. [Installation](#installation)
2. [Quick Start](#quick-start)
3. [CLI Usage](#cli-usage)
4. [Python API Usage](#python-api-usage)
5. [Configuration](#configuration)
6. [Output Formats](#output-formats)
7. [Real-World Examples](#real-world-examples)
8. [Troubleshooting](#troubleshooting)

## Installation

### Basic Installation

```bash
pip install semantic-copycat-oslili
```

### Dependencies

The package includes all required dependencies:
- `python-tlsh`: Required for fuzzy hash matching and false positive prevention
- `fuzzywuzzy`: For string similarity matching
- `pyyaml`: For configuration file support
- `requests`: For optional online features
- `click` and `colorama`: For CLI interface

**Note**: `python-tlsh` is a required dependency as of v1.2.0 for accurate license detection and confirmation.

### Development Installation

```bash
git clone https://github.com/oscarvalenzuelab/semantic-copycat-oslili.git
cd semantic-copycat-oslili
pip install -e .[dev]
```

## How License Detection Works

### Three-Tier Detection System

OSLILI uses a sophisticated multi-tier approach for accurate license detection:

1. **Tier 1: Dice-Sørensen with TLSH Confirmation**
   - Compares license text using Dice-Sørensen coefficient (97% similarity threshold)
   - **TLSH Confirmation**: Every match is verified using TLSH fuzzy hashing to prevent false positives
   - This combination achieves 97-100% accuracy on standard SPDX licenses

2. **Tier 2: TLSH Fuzzy Hash Matching**
   - Uses Trend Micro Locality Sensitive Hashing for detecting license variants
   - Pre-computed hashes for 699 SPDX licenses bundled with the package
   - Catches variants like MIT-0, BSD-2-Clause vs BSD-3-Clause
   - Threshold: TLSH distance ≤30 for high confidence matches

3. **Tier 3: Pattern Recognition**
   - Regex-based detection for license references and identifiers
   - Extracts from comments, headers, and documentation
   - Detects SPDX-License-Identifier tags

### Additional Detection Sources

- **Package Metadata**: Automatically detects licenses from package.json, composer.json, pyproject.toml, Cargo.toml, etc.
- **Copyright Extraction**: Advanced pattern matching with validation and deduplication
- **File Name Patterns**: Recognizes LICENSE, COPYING, MIT-LICENSE, and other standard file names

## Quick Start

### Scan Local Source Code

```bash
# Analyze a local directory
oslili /path/to/project -f notices -o NOTICE.txt

# Analyze current directory
oslili . -f kissbom

# Analyze a specific file
oslili /path/to/LICENSE -o license-info.json
```

## CLI Usage

### Basic Syntax

```bash
oslili [OPTIONS] PATH
```

### Arguments

- `PATH`: Path to local directory or file to analyze

### Options

#### Output Options

- `-f, --output-format`: Output format
  - `kissbom` (default): Enriched JSON format with license and copyright info
  - `cyclonedx-json`: CycloneDX JSON SBOM
  - `cyclonedx-xml`: CycloneDX XML SBOM
  - `notices`: Human-readable legal notices

- `-o, --output`: Output file path (default: stdout)

#### Configuration Options

- `-c, --config`: Path to YAML configuration file
- `--similarity-threshold`: License similarity threshold (0.0-1.0, default: 0.97)
- `--max-depth`: Maximum archive extraction depth (default: 10)
- `-t, --threads`: Number of processing threads (default: CPU count)

#### Logging Options

- `-v, --verbose`: Enable verbose output
- `-d, --debug`: Enable debug output

### CLI Examples

```bash
# Generate KissBOM for a project
oslili /path/to/project -o attribution.json

# Generate human-readable notices
oslili ./my-app -f notices -o NOTICE.txt

# Generate CycloneDX SBOM
oslili ./src -f cyclonedx-json -o sbom.json

# Use custom configuration
oslili /project --config my-config.yaml

# Verbose output with custom threshold
oslili ./code -v --similarity-threshold 0.95

# Process with limited threads
oslili /large/project --threads 2 -o attribution.json

# Debug mode for troubleshooting
oslili ./lib -d
```

## Python API Usage

### Basic Usage

```python
from semantic_copycat_oslili import LegalAttributionGenerator

# Create generator with default config
generator = LegalAttributionGenerator()

# Process a local directory
result = generator.process_local_path("/path/to/project")

# Check results
print(f"Found {len(result.licenses)} license(s)")
print(f"Found {len(result.copyrights)} copyright(s)")

# Generate output
kissbom = generator.generate_kissbom([result])
print(kissbom)
```

### Advanced Configuration

```python
from semantic_copycat_oslili import LegalAttributionGenerator, Config

# Create custom configuration
config = Config(
    similarity_threshold=0.95,
    thread_count=8,
    verbose=True,
    custom_aliases={
        "Apache 2": "Apache-2.0",
        "MIT License": "MIT"
    }
)

# Initialize with config
generator = LegalAttributionGenerator(config)

# Process local path
result = generator.process_local_path("/path/to/source")
```

### Processing Multiple Directories

```python
from semantic_copycat_oslili import LegalAttributionGenerator

generator = LegalAttributionGenerator()

# Process multiple directories
paths = [
    "/path/to/project1",
    "/path/to/project2",
    "/path/to/library"
]

results = []
for path in paths:
    result = generator.process_local_path(path)
    results.append(result)

# Generate combined output
kissbom = generator.generate_kissbom(results)
notices = generator.generate_notices(results)
```

### Analyzing Specific Files

```python
from semantic_copycat_oslili import LegalAttributionGenerator

generator = LegalAttributionGenerator()

# Process specific file
result = generator.process_local_path("/path/to/LICENSE")

# Access detected information
for license in result.licenses:
    print(f"License: {license.spdx_id} (confidence: {license.confidence:.2%})")

for copyright in result.copyrights:
    print(f"Copyright: {copyright.statement}")
```

### Custom Output Handling

```python
import json
from semantic_copycat_oslili import LegalAttributionGenerator

generator = LegalAttributionGenerator()

# Process directory
result = generator.process_local_path("./src")

# Generate different output formats
kissbom = generator.generate_kissbom([result])
with open("attribution.json", "w") as f:
    json.dump(kissbom, f, indent=2)

cyclonedx = generator.generate_cyclonedx([result], format="json")
with open("sbom.json", "w") as f:
    f.write(cyclonedx)

notices = generator.generate_notices([result])
with open("NOTICE.txt", "w") as f:
    f.write(notices)
```

## Configuration

### Configuration File Format

Create a `config.yaml` file:

```yaml
# License detection settings
similarity_threshold: 0.97  # Minimum similarity for license matching
max_extraction_depth: 10    # Maximum nested archive depth

# Performance settings
thread_count: 4              # Number of parallel threads

# Output settings
verbose: false
debug: false

# License detection patterns
license_filename_patterns:
  - "LICENSE*"
  - "LICENCE*"
  - "COPYING*"
  - "NOTICE*"
  - "COPYRIGHT*"

# License name mappings
custom_aliases:
  "Apache 2": "Apache-2.0"
  "Apache 2.0": "Apache-2.0"
  "MIT License": "MIT"
  "BSD License": "BSD-3-Clause"

# Cache settings
cache_dir: "~/.cache/oslili"
```

### Environment Variables

You can also configure via environment variables:

```bash
export OSLILI_SIMILARITY_THRESHOLD=0.95
export OSLILI_THREAD_COUNT=8
export OSLILI_VERBOSE=true
export OSLILI_DEBUG=false
export OSLILI_CACHE_DIR=~/.cache/oslili

oslili /path/to/project
```

### Configuration Priority

Configuration is applied in this order (later overrides earlier):
1. Default values
2. Configuration file
3. Environment variables
4. Command-line arguments

## Output Formats

### KissBOM Format

Enriched JSON format with license and copyright information:

```json
{
  "packages": [
    {
      "path": "/path/to/project",
      "license": "Apache-2.0",
      "copyright": "2024 John Doe, 2023 Jane Smith"
    }
  ]
}
```

### CycloneDX SBOM

Industry-standard SBOM format (JSON or XML):

```json
{
  "bomFormat": "CycloneDX",
  "specVersion": "1.4",
  "components": [
    {
      "type": "library",
      "name": "my-project",
      "version": "unknown",
      "path": "/path/to/project",
      "licenses": [
        {"license": {"id": "Apache-2.0"}}
      ]
    }
  ]
}
```

### Human-Readable Notices

Text format suitable for NOTICE files:

```
/path/to/project - Apache-2.0
  Copyright 2024 John Doe
  Copyright 2023 Jane Smith

-------
Apache License 2.0 text...
```

## Real-World Examples

### Example 1: Generate NOTICE file for a project

```bash
# Generate NOTICE file for current project
oslili . -f notices -o NOTICE.txt

# View results
cat NOTICE.txt
```

### Example 2: Analyze multiple projects and create combined SBOM

```bash
# Create a script to analyze multiple directories
cat > analyze.sh << 'EOF'
#!/bin/bash
oslili ./frontend -f cyclonedx-json -o frontend-sbom.json
oslili ./backend -f cyclonedx-json -o backend-sbom.json
oslili ./shared -f cyclonedx-json -o shared-sbom.json
EOF

chmod +x analyze.sh
./analyze.sh
```

### Example 3: Batch processing with custom config

```bash
# Create custom config
cat > strict-config.yaml << EOF
similarity_threshold: 0.99
thread_count: 8
verbose: true
custom_aliases:
  "Apache-2": "Apache-2.0"
  "GPLv2+": "GPL-2.0-or-later"
EOF

# Process with strict matching
oslili /path/to/codebase --config strict-config.yaml -o attribution.json
```

### Example 4: Python script for CI/CD

```python
#!/usr/bin/env python3
import sys
import json
from pathlib import Path
from semantic_copycat_oslili import LegalAttributionGenerator, Config

def check_licenses(project_path, allowed_licenses):
    """Check if project has only allowed licenses."""
    
    config = Config(verbose=True)
    generator = LegalAttributionGenerator(config)
    
    # Process project
    result = generator.process_local_path(project_path)
    
    # Check licenses
    violations = []
    for license_info in result.licenses:
        if license_info.spdx_id not in allowed_licenses:
            violations.append({
                'file': license_info.source_file,
                'license': license_info.spdx_id
            })
    
    # Report results
    if violations:
        print("License violations found:")
        for v in violations:
            print(f"  - {v['file']}: {v['license']}")
        return 1
    else:
        print(f"All licenses are allowed")
        return 0

if __name__ == "__main__":
    allowed = ["MIT", "Apache-2.0", "BSD-3-Clause", "ISC"]
    sys.exit(check_licenses(".", allowed))
```

## Troubleshooting

### Common Issues

#### 1. License not detected

**Problem**: License returns as "NO-ASSERTION"

**Solutions**:
- Lower similarity threshold: `--similarity-threshold 0.90`
- Check if license file exists in the directory
- Enable debug mode to see detection attempts: `-d`
- Ensure file is readable and not binary

#### 2. Slow processing

**Problem**: Processing takes too long

**Solutions**:
- Reduce thread count if system is overloaded: `--threads 2`
- Install fast dependencies: `pip install python-Levenshtein`
- Exclude unnecessary directories from scan
- Limit extraction depth for archives: `--max-depth 5`

#### 3. Memory issues

**Problem**: Out of memory errors

**Solutions**:
- Process smaller directories individually
- Reduce thread count: `--threads 1`
- Limit extraction depth: `--max-depth 5`

#### 4. Copyright extraction issues

**Problem**: Missing or incorrect copyright statements

**Solutions**:
- Check file encoding (UTF-8 is preferred)
- Enable debug mode to see extraction patterns
- Review copyright format in source files

### Debug Mode

Enable debug output to see detailed processing:

```bash
oslili /path/to/project -d 2> debug.log
```

### Getting Help

```bash
# Show help message
oslili --help

# Check version
oslili --version
```

## Best Practices

1. **Use Configuration Files**: For consistent results across team members
2. **Regular Scans**: Run license scans as part of CI/CD pipeline
3. **Verify Critical Files**: Manually review important license files
4. **Custom Aliases**: Add project-specific license mappings
5. **Test Threshold**: Adjust similarity threshold based on your needs
6. **Version Control**: Track attribution files in your repository
7. **Exclude Build Artifacts**: Don't scan generated or compiled files

## License

This tool is provided under the Apache License 2.0. See LICENSE file for details.

## Support

For issues, feature requests, or questions:
- GitHub Issues: https://github.com/oscarvalenzuelab/semantic-copycat-oslili/issues
- Documentation: https://github.com/oscarvalenzuelab/semantic-copycat-oslili#readme