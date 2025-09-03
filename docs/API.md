# API Reference

## LicenseCopyrightDetector

The main class for detecting licenses and copyright information in source code.

### Constructor

```python
LicenseCopyrightDetector(config: Optional[Config] = None)
```

Creates a new detector instance with optional configuration.

### Methods

#### process_local_path

```python
process_local_path(path: str, extract_archives: bool = True) -> DetectionResult
```

Process a local directory or file to detect licenses and copyrights.

**Parameters:**
- `path`: Path to local directory or file to analyze
- `extract_archives`: Whether to extract and scan archives (default: True)

**Returns:** DetectionResult object containing detected licenses and copyrights

#### generate_evidence

```python
generate_evidence(results: List[DetectionResult]) -> str
```

Generate evidence-based JSON output showing file-to-license mappings.

**Parameters:**
- `results`: List of detection results

**Returns:** JSON string with evidence of detected licenses and copyrights

#### generate_kissbom

```python
generate_kissbom(results: List[DetectionResult]) -> str
```

Generate KissBOM (Keep It Simple Software Bill of Materials) output.

**Parameters:**
- `results`: List of detection results

**Returns:** KissBOM as JSON string

#### generate_cyclonedx

```python
generate_cyclonedx(results: List[DetectionResult], format_type: str = "json") -> str
```

Generate CycloneDX SBOM output.

**Parameters:**
- `results`: List of detection results
- `format_type`: Output format ("json" or "xml", default: "json")

**Returns:** CycloneDX SBOM as string

#### generate_notices

```python
generate_notices(results: List[DetectionResult]) -> str
```

Generate human-readable legal notices with license texts.

**Parameters:**
- `results`: List of detection results

**Returns:** Legal notices as formatted string

## Data Models

### DetectionResult

```python
@dataclass
class DetectionResult:
    path: str                          # Path that was analyzed
    licenses: List[DetectedLicense]    # Detected licenses
    copyrights: List[CopyrightInfo]    # Copyright information
    errors: List[str]                  # Any errors encountered
    confidence_scores: Dict[str, float] # Confidence scores by method
    processing_time: float              # Processing time in seconds
    package_name: Optional[str]        # Package name if detected
    package_version: Optional[str]     # Package version if detected
```

### DetectedLicense

```python
@dataclass
class DetectedLicense:
    spdx_id: str                  # SPDX license identifier
    name: str                     # License name
    text: Optional[str]           # License text if available
    confidence: float             # Detection confidence (0.0-1.0)
    detection_method: str         # How it was detected (dice-sorensen, tlsh, regex, tag, filename)
    source_file: Optional[str]    # Where it was found
    category: Optional[str]       # License category (declared, detected, referenced)
    match_type: Optional[str]     # Type of match (license_file, package_metadata, spdx_identifier, documentation, license_header, license_reference, text_similarity, etc.)
```

### CopyrightInfo

```python
@dataclass
class CopyrightInfo:
    holder: str                    # Copyright holder
    years: Optional[List[int]]    # Copyright years
    statement: str                 # Full copyright statement
    source_file: Optional[str]    # Where it was found
    confidence: float             # Detection confidence (0.0-1.0)
```

### LicenseCategory

```python
class LicenseCategory(Enum):
    DECLARED = "declared"    # Explicitly declared in LICENSE files, package.json, etc.
    DETECTED = "detected"    # Inferred from source code content
    REFERENCED = "referenced" # Mentioned but not primary
```

### Config

```python
@dataclass
class Config:
    similarity_threshold: float = 0.97      # License similarity threshold
    max_recursion_depth: int = 10          # Maximum directory recursion depth
    max_extraction_depth: int = 3          # Maximum archive extraction depth (default: 3)
    thread_count: int = 4                   # Number of parallel threads
    verbose: bool = False                   # Enable verbose output
    debug: bool = False                     # Enable debug output
    license_filename_patterns: List[str]    # Patterns for license files
    custom_aliases: Dict[str, str]         # Custom license name mappings
    cache_dir: Optional[str] = None        # Cache directory for results
```

## CLI Options

```
oslili [OPTIONS] INPUT_PATH

Arguments:
  INPUT_PATH              Path to local directory or file to analyze

Options:
  -o, --output PATH                    Output file path (default: stdout)
  -f, --output-format                  Output format (evidence|kissbom|cyclonedx-json|cyclonedx-xml|notices)
  -v, --verbose                        Enable verbose logging
  -d, --debug                          Enable debug logging
  -t, --threads INTEGER                Number of processing threads
  -c, --config PATH                    Path to configuration file
  --similarity-threshold FLOAT         License similarity threshold (0.0-1.0)
  --max-depth, --max-recursion-depth INTEGER   Maximum directory recursion depth (default: 10, use -1 for unlimited)
  --max-extraction-depth INTEGER       Maximum archive extraction depth (default: 10)
  --version                            Show version and exit
  --help                               Show help message
```

## Environment Variables

The following environment variables can be used to configure the tool:

- `OSLILI_SIMILARITY_THRESHOLD`: License similarity threshold
- `OSLILI_THREAD_COUNT`: Number of processing threads
- `OSLILI_VERBOSE`: Set to "true" to enable verbose mode
- `OSLILI_DEBUG`: Set to "true" to enable debug mode
- `OSLILI_CACHE_DIR`: Directory for caching data
- `OSLILI_MAX_RECURSION_DEPTH`: Maximum directory recursion depth

## Configuration File

Create a YAML configuration file:

```yaml
# config.yaml
# License detection settings
similarity_threshold: 0.97  # Minimum similarity for license matching
max_recursion_depth: 10     # Maximum directory recursion depth
max_extraction_depth: 10    # Maximum archive extraction depth

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
  - "*GPL*"
  - "*COPYLEFT*"
  - "*EULA*"
  - "*COMMERCIAL*"
  - "*AGREEMENT*"
  - "*BUNDLE*"
  - "*THIRD-PARTY*"
  - "*THIRD_PARTY*"
  - "LEGAL*"

# License name mappings
custom_aliases:
  "Apache 2": "Apache-2.0"
  "Apache 2.0": "Apache-2.0"
  "MIT License": "MIT"
  "BSD License": "BSD-3-Clause"

# Cache settings
cache_dir: "~/.cache/oslili"
```

## Example Usage

### Basic Usage

```python
from semantic_copycat_oslili import LicenseCopyrightDetector

# Create detector
detector = LicenseCopyrightDetector()

# Process a local directory
result = detector.process_local_path("/path/to/project")

# Print licenses by category
for license in result.licenses:
    print(f"License: {license.spdx_id}")
    print(f"  Category: {license.category}")
    print(f"  Confidence: {license.confidence:.0%}")
    print(f"  Method: {license.detection_method}")
    print(f"  Found in: {license.source_file}")

# Print copyrights
for copyright in result.copyrights:
    print(f"Copyright: {copyright.statement}")

# Generate evidence output
evidence = detector.generate_evidence([result])
print(evidence)
```

### With Configuration

```python
from semantic_copycat_oslili import LicenseCopyrightDetector, Config

# Custom configuration
config = Config(
    verbose=True,
    thread_count=8,
    similarity_threshold=0.95,
    max_recursion_depth=5  # Limit directory depth
)

# Create detector with config
detector = LicenseCopyrightDetector(config)

# Process local path
result = detector.process_local_path("/path/to/source")
```

### Processing Multiple Directories

```python
from semantic_copycat_oslili import LicenseCopyrightDetector
import json

detector = LicenseCopyrightDetector()

# Process multiple directories
paths = [
    "/path/to/project1",
    "/path/to/project2",
    "/path/to/library"
]

results = []
for path in paths:
    result = detector.process_local_path(path)
    results.append(result)

# Generate combined evidence
evidence = detector.generate_evidence(results)

# Save to file
with open("license-evidence.json", "w") as f:
    f.write(evidence)
```

### Analyzing with License Hierarchy

```python
from semantic_copycat_oslili import LicenseCopyrightDetector

detector = LicenseCopyrightDetector()
result = detector.process_local_path("/path/to/project")

# Separate licenses by category
declared_licenses = [l for l in result.licenses if l.category == "declared"]
detected_licenses = [l for l in result.licenses if l.category == "detected"]
referenced_licenses = [l for l in result.licenses if l.category == "referenced"]

print(f"Declared licenses: {[l.spdx_id for l in declared_licenses]}")
print(f"Detected licenses: {[l.spdx_id for l in detected_licenses]}")
print(f"Referenced licenses: {[l.spdx_id for l in referenced_licenses]}")
```

### Safe Directory Traversal

```python
from semantic_copycat_oslili import LicenseCopyrightDetector, Config

# Configure with depth limiting
config = Config(
    max_recursion_depth=3,  # Only go 3 levels deep
    verbose=True
)

detector = LicenseCopyrightDetector(config)

# Process a deep directory structure safely
result = detector.process_local_path("/path/to/deep/project")

# The detector will automatically:
# - Skip directories beyond the depth limit
# - Detect and avoid symbolic link loops
# - Filter out common build/cache directories
```

### Archive Processing

```python
from semantic_copycat_oslili import LicenseCopyrightDetector, Config

# Configure archive extraction
config = Config(
    max_extraction_depth=2,  # Extract up to 2 levels of nested archives
    verbose=True
)

detector = LicenseCopyrightDetector(config)

# Process an archive file
result = detector.process_local_path("/path/to/package.tar.gz")

# Archives are automatically extracted and scanned
# Supports: .zip, .tar, .tar.gz, .tar.bz2, .tar.xz, .whl, .egg
```

### Using Cache

```python
from semantic_copycat_oslili import LicenseCopyrightDetector, Config

# Configure with cache
config = Config(
    cache_dir="~/.cache/oslili",  # Enable caching
    verbose=True
)

detector = LicenseCopyrightDetector(config)

# First scan - results are cached
result1 = detector.process_local_path("/path/to/project")

# Second scan - uses cached results (much faster)
result2 = detector.process_local_path("/path/to/project")

# Cache automatically invalidates when files are modified
```

## License Tag Identification

OSLILI automatically detects various forms of license tags and identifiers in source code:

### Supported Tag Formats

1. **SPDX-License-Identifier**
   - `SPDX-License-Identifier: MIT`
   - `SPDX-License-Identifier: Apache-2.0`
   - Commonly found in source code headers

2. **Package Metadata**
   - `package.json`: `"license": "MIT"`
   - `pyproject.toml`: `license = "Apache-2.0"` or `license = {text = "MIT"}`
   - `setup.py`: `license='BSD-3-Clause'`
   - `Cargo.toml`: `license = "MIT OR Apache-2.0"`
   - `composer.json`: `"license": "GPL-3.0"`

3. **Documentation Tags**
   - `@license MIT` (JSDoc style)
   - `License: Apache-2.0` (in metadata files)
   - `Licensed under the MIT License`
   - `License-Expression: MIT` (Python METADATA)

### License Expression Support

OSLILI parses complex license expressions:
- `MIT OR Apache-2.0` - Dual licensing
- `GPL-3.0-or-later` - Version with modifier
- `Apache-2.0 WITH LLVM-exception` - License with exception

### Tag Detection Example

```python
from semantic_copycat_oslili import LicenseCopyrightDetector

detector = LicenseCopyrightDetector()
result = detector.process_local_path("/path/to/source.js")

# Filter by detection method
tag_licenses = [l for l in result.licenses if l.detection_method == "tag"]
for license in tag_licenses:
    print(f"Tag found: {license.spdx_id} in {license.source_file}")
    print(f"  Match type: {license.match_type}")
```

### Detection Methods

OSLILI uses multiple methods to detect licenses:

1. **Tag Detection (`detection_method: "tag"`)**
   - SPDX identifiers in comments
   - Package metadata declarations
   - High confidence (1.0)

2. **Text Similarity (`detection_method: "dice-sorensen"` or `"tlsh"`)**
   - Full license text comparison
   - Fuzzy matching for variants
   - Confidence based on similarity score

3. **Pattern Matching (`detection_method: "regex"`)**
   - License references in text
   - Copyright headers
   - Variable confidence based on context

4. **Filename Detection (`detection_method: "filename"`)**
   - LICENSE, COPYING files
   - Standard naming patterns
   - High confidence when content matches