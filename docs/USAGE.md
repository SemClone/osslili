# OSLILI Usage Guide

This guide provides comprehensive instructions for using the `semantic-copycat-oslili` package to generate legal attribution notices from software packages.

## Table of Contents

1. [Installation](#installation)
2. [Quick Start](#quick-start)
3. [CLI Usage](#cli-usage)
4. [Python API Usage](#python-api-usage)
5. [Configuration](#configuration)
6. [Input Formats](#input-formats)
7. [Output Formats](#output-formats)
8. [Real-World Examples](#real-world-examples)
9. [Troubleshooting](#troubleshooting)

## Installation

### Basic Installation

```bash
pip install semantic-copycat-oslili
```

### Installation with Optional Features

```bash
# For faster fuzzy matching
pip install semantic-copycat-oslili[fast]

# For TLSH fuzzy hashing (Tier 2 detection)
pip install semantic-copycat-oslili[tlsh]

# For better package URL resolution
pip install semantic-copycat-oslili[purl2src]

# For CycloneDX SBOM support
pip install semantic-copycat-oslili[cyclonedx]

# Install all optional features
pip install semantic-copycat-oslili[all]
```

### Development Installation

```bash
git clone https://github.com/oscarvalenzuelab/semantic-copycat-oslili.git
cd semantic-copycat-oslili
pip install -e .[dev]
```

## Quick Start

### Process a Single Package

```bash
# Process a PyPI package
oslili pkg:pypi/requests@2.31.0

# Process an npm package
oslili pkg:npm/express@4.18.2

# Process a GitHub repository
oslili pkg:github/facebook/react@v18.2.0
```

### Process Multiple Packages

Create a file `packages.txt`:
```
pkg:pypi/django@4.2.0
pkg:npm/lodash@4.17.21
pkg:gem/rails@7.0.4
```

Then run:
```bash
oslili packages.txt -o attribution.json
```

### Process Local Source Code

```bash
# Analyze a local directory
oslili /path/to/project -f notices -o NOTICE.txt

# Analyze current directory
oslili . -f kissbom
```

## CLI Usage

### Basic Syntax

```bash
oslili [OPTIONS] INPUT
```

### Arguments

- `INPUT`: Package URL (purl), path to purl list file, or local directory/file

### Options

#### Output Options

- `-f, --output-format`: Output format
  - `kissbom` (default): Enriched KissBOM JSON format
  - `cyclonedx-json`: CycloneDX JSON SBOM
  - `cyclonedx-xml`: CycloneDX XML SBOM
  - `notices`: Human-readable legal notices

- `-o, --output`: Output file path (default: stdout)

#### Configuration Options

- `-c, --config`: Path to YAML configuration file
- `--similarity-threshold`: License similarity threshold (0.0-1.0, default: 0.97)
- `--max-depth`: Maximum archive extraction depth (default: 10)
- `--timeout`: Network request timeout in seconds (default: 30)
- `-t, --threads`: Number of processing threads (default: CPU count)

#### Logging Options

- `-v, --verbose`: Enable verbose output
- `-d, --debug`: Enable debug output

### CLI Examples

```bash
# Generate KissBOM for a package
oslili pkg:pypi/flask@2.3.0 -o flask-attribution.json

# Generate human-readable notices
oslili pkg:npm/react@18.2.0 -f notices -o REACT-NOTICE.txt

# Generate CycloneDX SBOM
oslili packages.txt -f cyclonedx-json -o sbom.json

# Use custom configuration
oslili pkg:pypi/django@4.2.0 --config my-config.yaml

# Verbose output with custom threshold
oslili pkg:gem/rails@7.0.0 -v --similarity-threshold 0.95

# Process with limited threads
oslili /large/project --threads 2 -o attribution.json

# Debug mode for troubleshooting
oslili pkg:npm/express@4.18.2 -d
```

## Python API Usage

### Basic Usage

```python
from semantic_copycat_oslili import LegalAttributionGenerator

# Create generator with default config
generator = LegalAttributionGenerator()

# Process a package
result = generator.process_purl("pkg:pypi/requests@2.31.0")

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

# Process with external sources disabled
result = generator.process_purl(
    "pkg:pypi/django@4.2.0",
    use_external_sources=False
)
```

### Processing Multiple Packages

```python
from semantic_copycat_oslili import LegalAttributionGenerator

generator = LegalAttributionGenerator()

# Process list of purls
purls = [
    "pkg:pypi/flask@2.3.0",
    "pkg:npm/express@4.18.2",
    "pkg:gem/rails@7.0.0"
]

results = []
for purl in purls:
    result = generator.process_purl(purl)
    results.append(result)

# Generate combined output
kissbom = generator.generate_kissbom(results)
notices = generator.generate_notices(results)
```

### Processing Local Files

```python
from semantic_copycat_oslili import LegalAttributionGenerator

generator = LegalAttributionGenerator()

# Process local directory
result = generator.process_local_path("/path/to/project")

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
results = generator.process_purl_file("packages.txt")

# Generate different output formats
kissbom = generator.generate_kissbom(results)
with open("attribution.json", "w") as f:
    json.dump(kissbom, f, indent=2)

cyclonedx = generator.generate_cyclonedx(results, format="json")
with open("sbom.json", "w") as f:
    f.write(cyclonedx)

notices = generator.generate_notices(results)
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
network_timeout: 30          # Seconds before network timeout

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

# External API endpoints
spdx_data_url: "https://raw.githubusercontent.com/spdx/license-list-data/main/json/licenses.json"
clearlydefined_api_url: "https://api.clearlydefined.io"
pypi_api_url: "https://pypi.org/pypi"
npm_api_url: "https://registry.npmjs.org"

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

oslili pkg:pypi/requests@2.31.0
```

### Configuration Priority

Configuration is applied in this order (later overrides earlier):
1. Default values
2. Configuration file
3. Environment variables
4. Command-line arguments

## Input Formats

### Package URLs (purl)

Standard purl format: `pkg:type/namespace/name@version`

Examples:
- `pkg:pypi/django@4.2.0`
- `pkg:npm/@angular/core@15.0.0`
- `pkg:gem/rails@7.0.0`
- `pkg:maven/org.apache.commons/commons-lang3@3.12.0`
- `pkg:cargo/serde@1.0.152`
- `pkg:github/facebook/react@v18.2.0`

### Package List File (KissBOM format)

Create a text file with one purl per line:

```
# Comments start with #
pkg:pypi/requests@2.31.0
pkg:npm/express@4.18.2
pkg:gem/rails@7.0.0

# Empty lines are ignored
pkg:cargo/tokio@1.28.0
```

### Local Paths

- Single file: `/path/to/LICENSE`
- Directory: `/path/to/project/`
- Current directory: `.`

## Output Formats

### KissBOM Format

Enriched JSON format with package, license, and copyright information:

```json
{
  "packages": [
    {
      "purl": "pkg:pypi/requests@2.31.0",
      "license": "Apache-2.0",
      "copyright": "Kenneth Reitz, Python Software Foundation",
      "notes": "Additional information"
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
      "name": "requests",
      "version": "2.31.0",
      "purl": "pkg:pypi/requests@2.31.0",
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
pkg:pypi/requests@2.31.0 - Apache-2.0
  Copyright 2019 Kenneth Reitz
  Copyright Python Software Foundation

pkg:npm/express@4.18.2 - MIT
  Copyright (c) 2009-2014 TJ Holowaychuk
  Copyright (c) 2013-2014 Roman Shtylman
  Copyright (c) 2014-2015 Douglas Christopher Wilson

-------
Apache License 2.0 text...

-------
MIT License text...
```

## Real-World Examples

### Example 1: Generate NOTICE file for a project

```bash
# Create package list
cat > packages.txt << EOF
pkg:pypi/django@4.2.0
pkg:pypi/celery@5.2.7
pkg:pypi/redis@4.5.5
pkg:npm/react@18.2.0
pkg:npm/webpack@5.88.0
EOF

# Generate NOTICE file
oslili packages.txt -f notices -o NOTICE.txt

# View results
cat NOTICE.txt
```

### Example 2: Analyze dependencies and create SBOM

```bash
# For a Python project
pip freeze | sed 's/==/@/g' | sed 's/^/pkg:pypi\//' > deps.txt
oslili deps.txt -f cyclonedx-json -o sbom.json

# For a Node.js project
npm list --depth=0 --json | jq -r '.dependencies | keys[] | "pkg:npm/\(.)@\(.)"' > deps.txt
oslili deps.txt -f cyclonedx-json -o sbom.json
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
oslili packages.txt --config strict-config.yaml -o attribution.json
```

### Example 4: Python script for CI/CD

```python
#!/usr/bin/env python3
import sys
import json
from semantic_copycat_oslili import LegalAttributionGenerator, Config

def check_licenses(allowed_licenses):
    """Check if all dependencies have allowed licenses."""
    
    config = Config(verbose=True)
    generator = LegalAttributionGenerator(config)
    
    # Read package list
    with open("requirements.txt") as f:
        purls = [f"pkg:pypi/{line.strip().replace('==', '@')}" 
                 for line in f if line.strip()]
    
    # Process packages
    results = []
    for purl in purls:
        result = generator.process_purl(purl)
        results.append(result)
    
    # Check licenses
    violations = []
    for result in results:
        if result.licenses:
            license_id = result.get_primary_license().spdx_id
            if license_id not in allowed_licenses:
                violations.append((result.purl, license_id))
    
    # Report results
    if violations:
        print("License violations found:")
        for purl, license_id in violations:
            print(f"  - {purl}: {license_id}")
        return 1
    else:
        print(f"All {len(results)} packages have allowed licenses")
        return 0

if __name__ == "__main__":
    allowed = ["MIT", "Apache-2.0", "BSD-3-Clause", "ISC"]
    sys.exit(check_licenses(allowed))
```

## Troubleshooting

### Common Issues

#### 1. Package download fails

**Problem**: "Failed to download or extract package"

**Solutions**:
- Check network connectivity
- Increase timeout: `--timeout 60`
- Try with verbose mode: `-v`
- Check if package exists: verify the purl is correct

#### 2. License not detected

**Problem**: License returns as "NO-ASSERTION"

**Solutions**:
- Lower similarity threshold: `--similarity-threshold 0.90`
- Check if license file exists in package
- Enable debug mode to see detection attempts: `-d`

#### 3. Slow processing

**Problem**: Processing takes too long

**Solutions**:
- Reduce thread count if system is overloaded: `--threads 2`
- Install fast dependencies: `pip install python-Levenshtein`
- Use local cache directory in config

#### 4. Memory issues

**Problem**: Out of memory errors

**Solutions**:
- Process packages in smaller batches
- Reduce thread count: `--threads 1`
- Limit extraction depth: `--max-depth 5`

### Debug Mode

Enable debug output to see detailed processing:

```bash
oslili pkg:pypi/django@4.2.0 -d 2> debug.log
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
2. **Cache SPDX Data**: Set `cache_dir` to avoid repeated downloads
3. **Verify Critical Packages**: Manually review high-importance dependencies
4. **Regular Updates**: Keep SPDX data current for best detection
5. **Combine Sources**: Use external APIs for better coverage
6. **Test Threshold**: Adjust similarity threshold based on your needs
7. **Version Control**: Track attribution files in your repository

## License

This tool is provided under the Apache License 2.0. See LICENSE file for details.

## Support

For issues, feature requests, or questions:
- GitHub Issues: https://github.com/oscarvalenzuelab/semantic-copycat-oslili/issues
- Documentation: https://github.com/oscarvalenzuelab/semantic-copycat-oslili#readme