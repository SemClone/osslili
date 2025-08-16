# API Reference

## LegalAttributionGenerator

The main class for generating legal attribution notices.

### Constructor

```python
LegalAttributionGenerator(config: Optional[Config] = None)
```

Creates a new generator instance with optional configuration.

### Methods

#### process_purl

```python
process_purl(purl_string: str, use_external_sources: bool = False) -> AttributionResult
```

Process a single package URL.

**Parameters:**
- `purl_string`: Package URL in purl format (e.g., "pkg:pypi/requests@2.28.1")
- `use_external_sources`: Enable external API sources (default: False)

**Returns:** AttributionResult object containing licenses and copyrights

#### process_purl_file

```python
process_purl_file(file_path: str) -> List[AttributionResult]
```

Process multiple package URLs from a file.

**Parameters:**
- `file_path`: Path to file containing purl strings (one per line)

**Returns:** List of AttributionResult objects

#### process_local_path

```python
process_local_path(path: str) -> AttributionResult
```

Process a local directory or file.

**Parameters:**
- `path`: Path to local directory or file to analyze

**Returns:** AttributionResult object

#### generate_kissbom

```python
generate_kissbom(results: List[AttributionResult]) -> Dict[str, Any]
```

Generate KissBOM format output.

**Parameters:**
- `results`: List of attribution results

**Returns:** Dictionary in KissBOM format

#### generate_cyclonedx

```python
generate_cyclonedx(results: List[AttributionResult], format: str = "json") -> str
```

Generate CycloneDX SBOM output.

**Parameters:**
- `results`: List of attribution results
- `format`: Output format ("json" or "xml")

**Returns:** CycloneDX SBOM as string

#### generate_notices

```python
generate_notices(results: List[AttributionResult]) -> str
```

Generate human-readable legal notices with full license text.

**Parameters:**
- `results`: List of attribution results

**Returns:** Legal notices as formatted string

## Data Models

### AttributionResult

```python
@dataclass
class AttributionResult:
    purl: str                          # Package URL
    package_name: str                  # Package name
    package_version: Optional[str]     # Package version
    licenses: List[DetectedLicense]    # Detected licenses
    copyrights: List[CopyrightInfo]    # Copyright information
    errors: List[str]                  # Any errors encountered
    metadata: Dict[str, Any]           # Additional metadata
    processing_time: float              # Processing time in seconds
```

### DetectedLicense

```python
@dataclass
class DetectedLicense:
    spdx_id: Optional[str]         # SPDX license identifier
    name: str                      # License name
    confidence: float              # Detection confidence (0.0-1.0)
    detection_method: str          # How it was detected
    source_file: str              # Where it was found
    text: Optional[str]           # License text if available
```

### CopyrightInfo

```python
@dataclass
class CopyrightInfo:
    holder: str                    # Copyright holder
    years: Optional[List[int]]    # Copyright years
    statement: str                 # Full copyright statement
    source_file: str              # Where it was found
    confidence: float             # Detection confidence (0.0-1.0)
```

### Config

```python
@dataclass
class Config:
    verbose: bool = False
    debug: bool = False
    thread_count: int = 4
    similarity_threshold: float = 0.97
    max_extraction_depth: int = 10
    network_timeout: int = 30
    cache_dir: Optional[str] = None
    custom_aliases: Dict[str, str] = field(default_factory=dict)
    # ... additional configuration options
```

## CLI Options

```
oslili [OPTIONS] INPUT_PATH

Options:
  -f, --output-format [kissbom|cyclonedx-json|cyclonedx-xml|notices]
                                  Output format (default: kissbom)
  -o, --output PATH              Output file path (default: stdout)
  -v, --verbose                  Enable verbose logging
  -d, --debug                    Enable debug logging
  -t, --threads INTEGER          Number of processing threads
  -c, --config PATH              Path to configuration file
  --similarity-threshold FLOAT   License similarity threshold (0.0-1.0)
  --max-depth INTEGER            Maximum archive extraction depth
  --timeout INTEGER              Network request timeout in seconds
  --online                       Enable external API sources
  --help                         Show help message
```

## Environment Variables

The following environment variables can be used to configure the tool:

- `OSLILI_CACHE_DIR`: Directory for caching data
- `OSLILI_DEBUG`: Set to "1" to enable debug mode
- `OSLILI_THREAD_COUNT`: Number of processing threads
- `OSLILI_NETWORK_TIMEOUT`: Network timeout in seconds

## Configuration File

Create a YAML configuration file:

```yaml
# config.yaml
verbose: true
thread_count: 8
similarity_threshold: 0.95
network_timeout: 60

custom_aliases:
  "Apache 2": "Apache-2.0"
  "MIT License": "MIT"
  "BSD License": "BSD-3-Clause"

# External API URLs (optional)
pypi_api_url: "https://pypi.org/pypi"
npm_api_url: "https://registry.npmjs.org"
clearlydefined_api_url: "https://api.clearlydefined.io"
```

## Example Usage

### Basic Usage

```python
from semantic_copycat_oslili import LegalAttributionGenerator

# Create generator
gen = LegalAttributionGenerator()

# Process a package
result = gen.process_purl("pkg:pypi/requests@2.28.1")

# Print licenses
for license in result.licenses:
    print(f"License: {license.spdx_id}")
    print(f"  Confidence: {license.confidence:.0%}")
    print(f"  Method: {license.detection_method}")

# Print copyrights
for copyright in result.copyrights:
    print(f"Copyright: {copyright.statement}")

# Generate notices
notices = gen.generate_notices([result])
print(notices)
```

### With Configuration

```python
from semantic_copycat_oslili import LegalAttributionGenerator, Config

# Custom configuration
config = Config(
    verbose=True,
    thread_count=8,
    similarity_threshold=0.95
)

# Create generator with config
gen = LegalAttributionGenerator(config)

# Process with external sources
result = gen.process_purl(
    "pkg:npm/express@4.18.2",
    use_external_sources=True
)
```

### Batch Processing

```python
from semantic_copycat_oslili import LegalAttributionGenerator

gen = LegalAttributionGenerator()

# Process multiple packages
purls = [
    "pkg:pypi/flask@2.3.0",
    "pkg:pypi/django@4.2.0",
    "pkg:npm/react@18.2.0"
]

results = []
for purl in purls:
    result = gen.process_purl(purl)
    results.append(result)

# Generate combined output
kissbom = gen.generate_kissbom(results)
cyclonedx = gen.generate_cyclonedx(results, format="json")
notices = gen.generate_notices(results)
```