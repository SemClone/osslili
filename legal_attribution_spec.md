# semantic-copycat-oslili Package Specification

## 1. Overview

This specification defines `semantic-copycat-oslili`, a Python package that generates standardized legal attribution notices from software packages. The package functions as both a CLI tool and a Python library, capable of processing package URLs (purls), scanning local source code, and producing attribution notices in multiple standardized formats.

## 2. Package Architecture

### 2.1 Core Components
- **CLI Interface**: Command-line tool for direct usage
- **Library API**: Python library for programmatic integration
- **License Detection Engine**: Multi-tier license identification system
- **Copyright Extraction Engine**: Comprehensive copyright information extraction
- **Output Formatters**: Multiple output format generators
- **Configuration System**: Customizable behavior and thresholds

### 2.2 Dependencies
- `purl2src` (https://pypi.org/project/semantic-copycat-purl2src/) - Package URL to source resolution
- `requests` - HTTP client for downloads and API calls
- `tlsh` - Fuzzy hashing for license text comparison
- `fuzzywuzzy` - Fuzzy string matching
- `cyclonedx-python-lib` - CycloneDX SBOM generation
- `concurrent.futures` - Multi-threading support
- Standard library modules: `re`, `os`, `pathlib`, `tempfile`, `tarfile`, `zipfile`, `json`, `logging`

## 3. Input Processing

### 3.1 Input Types
The package accepts three input types:

#### 3.1.1 Single Package URL (purl)
- **Format**: Valid purl string conforming to https://github.com/package-url/purl-spec
- **Validation**: Must validate against purl specification before processing
- **Example**: `pkg:pypi/requests@2.28.1`

#### 3.1.2 Multiple Package URLs File
- **Format**: Plain text file containing one purl per line
- **Schema**: KissBOM format (https://github.com/kissbom/kissbom-spec)
- **Processing**: Each line processed as individual purl
- **Empty lines**: Ignored
- **Comments**: Lines starting with `#` ignored

#### 3.1.3 Local Source Path
- **Format**: File system path to directory or file
- **Validation**: Must exist and be readable
- **Processing**: Recursive directory traversal for files

### 3.2 Package Acquisition Pipeline

#### 3.2.1 purl Processing (Types 3.1.1 and 3.1.2)
1. **Validation**: Validate purl format against specification
2. **URL Resolution**: Use `purl2src` to identify package download URL
3. **Download**: Retrieve tarball/archive artifact
4. **Extraction**: Decompress to temporary directory with recursive handling
5. **Cleanup**: Automatic cleanup of temporary files

#### 3.2.2 Recursive Decompression
- Handle nested archives (tar.gz, zip, tar.bz2, etc.)
- Maximum nesting depth: 10 levels (configurable)
- Preserve directory structure
- Handle various compression formats

## 4. License Detection System

### 4.1 License File Identification

#### 4.1.1 Curated Filename Patterns
Maintain embedded list of known license filename patterns including:
```
LICENSE, LICENCE, LICENSE.txt, LICENSE.md, LICENSE-MIT, LICENSE-APACHE,
MIT-LICENSE, COPYING, NOTICE, UNLICENSE, COMMERCIAL-LICENSE,
3rdpartylicenses.txt, THIRD_PARTY_NOTICES.md, etc.
```

#### 4.1.2 Fuzzy Filename Matching
- Apply fuzzy matching for filename variations
- Configurable similarity threshold (default: 85%)
- Case-insensitive matching
- Handle file extensions and prefixes/suffixes

#### 4.1.3 Content Scanning
- Scan all readable text files for embedded license information
- Parse source code comments for license headers
- Supported file types: `.py`, `.js`, `.java`, `.c`, `.cpp`, `.h`, `.go`, `.rs`, `.rb`, `.php`, `.cs`, etc.

### 4.2 License Tag Detection

#### 4.2.1 SPDX License Identification
- Regex patterns for SPDX license identifiers
- Support for license expressions (AND, OR, WITH operators)
- Fuzzy matching for SPDX license names
- Alias resolution (e.g., "Apache 2.0" → "Apache-2.0")

#### 4.2.2 Normalization
- Convert all license identifiers to lowercase for comparison
- Create normalized alias mappings
- Handle common variations and misspellings

### 4.3 Three-Tier License Text Identification

#### 4.3.1 Tier 1: Dice-Sørensen Similarity
- **Algorithm**: Dice-Sørensen coefficient calculation
- **Corpus**: Embedded repository of all SPDX license texts
- **Threshold**: 97% similarity minimum
- **Implementation**: Bigram tokenization for comparison
- **Preprocessing**: Normalize whitespace, remove formatting

#### 4.3.2 Tier 2: Fuzzy Hashing
- **Algorithm**: TLSH (Trend Micro Locality Sensitive Hash)
- **Preprocessing**: 
  - Extract only alphanumeric and printable characters
  - Convert to lowercase
  - Remove excessive whitespace
- **Threshold**: 97% similarity minimum
- **Corpus**: Pre-computed TLSH hashes for all SPDX licenses

#### 4.3.3 Tier 3: Machine Learning Classification
- **Primary Method**: Transformer-based text classification
  - Use pre-trained BERT or similar model
  - Fine-tune on SPDX license corpus
  - Confidence threshold: 97%
- **Fallback Method**: Regex pattern matching
  - Extract key phrases and clauses from license text
  - Match against known license patterns
  - Weight-based scoring system

#### 4.3.4 Failure Handling
- If all tiers fail to reach 97% confidence: Flag as "NO-ASSERTION"
- Log detailed information about attempted matches
- Include confidence scores in debug output

## 5. Copyright Extraction System

### 5.1 Information Sources

#### 5.1.1 Direct Source Scanning
- **File Headers**: Parse copyright statements in source files
- **License Files**: Extract copyright from dedicated license files
- **Metadata Files**: Process package.json, setup.py, Cargo.toml, etc.
- **Documentation**: README files, AUTHORS, CONTRIBUTORS

#### 5.1.2 External Data Sources
- **Package Registries**: Query upstream registries using purl information
  - PyPI API for Python packages
  - npm registry for JavaScript packages
  - crates.io for Rust packages
  - Maven Central for Java packages
- **ClearlyDefined API**: Retrieve curated license and copyright data
- **Version Control**: Git log analysis when repository information available

### 5.2 Copyright Pattern Recognition

#### 5.2.1 Pattern Types
- **Standard Format**: `Copyright (c) YYYY Name`
- **Alternative Formats**: `© YYYY Name`, `(C) YYYY Name`
- **Range Formats**: `Copyright 2020-2023 Name`
- **Multiple Years**: `Copyright 2020, 2021, 2023 Name`
- **No Year**: `Copyright Name`
- **Informal**: `Created by Name`, `Author: Name`

#### 5.2.2 Entity Types
- Individual author names
- Company/organization names
- Multiple contributors
- Email addresses
- GitHub usernames

#### 5.2.3 Year Handling
- Extract copyright years when present
- Support year ranges and multiple years
- Mark as optional in output
- Default to "present" if no year found

### 5.3 Multi-threaded Processing
- **Thread Pool**: Configurable number of worker threads (default: CPU count)
- **File Distribution**: Distribute files across threads for parallel processing
- **Result Aggregation**: Thread-safe collection of results
- **Error Handling**: Individual thread error isolation

## 6. Output Formats

### 6.1 Enriched KissBOM Format

#### 6.1.1 Structure
```json
{
  "packages": [
    {
      "purl": "pkg:pypi/requests@2.28.1",
      "license": "Apache-2.0",
      "copyright": "Kenneth Reitz, Python Software Foundation",
      "notes": "Additional attribution notes"
    }
  ]
}
```

#### 6.1.2 Field Specifications
- **purl**: Package URL string (required)
- **license**: SPDX license expression string (optional, "NO-ASSERTION" if unknown)
- **copyright**: Copyright holder names string (optional, comma-separated)
- **notes**: Additional notes string (optional)

### 6.2 CycloneDX SBOM Format

#### 6.2.1 Integration
- Use `cyclonedx-python-lib` for standard SBOM generation
- Include license and copyright information in component metadata
- Support both JSON and XML output formats
- Include tool information and generation timestamp

#### 6.2.2 License Mapping
- Map detected licenses to CycloneDX license structure
- Include license text when available
- Support license expressions

### 6.3 Human-Readable Legal Notices

#### 6.3.1 Format Structure
```
<package_url> - <spdx-id>
<authors_or_copyright_statements>

<package_url> - <spdx-id>
<authors_or_copyright_statements>

<package_url> - <spdx-id>
<authors_or_copyright_statements>

-------
<spdx-text-content>
```

#### 6.3.2 Grouping Logic
- Group packages by identical license (SPDX ID)
- List all packages using same license first
- Include copyright statements for each package
- Show license text once per license group
- Use "-------" as separator between sections

#### 6.3.3 Multi-License Handling
- Create separate sections for each unique license
- Maintain chronological order within license groups
- Include license text for each license type

## 7. CLI Interface

### 7.1 Command Structure
```bash
oslili [OPTIONS] INPUT
```

### 7.2 Arguments

#### 7.2.1 Positional Arguments
- `INPUT`: Single purl, path to purl file, or local directory path

#### 7.2.2 Optional Arguments
- `--output-format, -f`: Output format choice
  - `kissbom` (default): Enriched KissBOM JSON
  - `cyclonedx-json`: CycloneDX JSON SBOM
  - `cyclonedx-xml`: CycloneDX XML SBOM  
  - `notices`: Human-readable legal notices
- `--output, -o`: Output file path (default: stdout)
- `--verbose, -v`: Enable verbose logging
- `--debug, -d`: Enable debug logging
- `--threads, -t`: Number of processing threads (default: CPU count)
- `--config, -c`: Path to configuration file
- `--similarity-threshold`: License similarity threshold (default: 0.97)
- `--max-depth`: Maximum archive extraction depth (default: 10)
- `--timeout`: Network request timeout in seconds (default: 30)

### 7.3 Configuration File

#### 7.3.1 Format (YAML)
```yaml
similarity_threshold: 0.97
max_extraction_depth: 10
network_timeout: 30
thread_count: 4
license_filename_patterns:
  - "LICENSE*"
  - "LICENCE*"
  - "COPYING*"
custom_aliases:
  "Apache 2": "Apache-2.0"
  "MIT License": "MIT"
```

#### 7.3.2 Configuration Options
- **similarity_threshold**: Float (0.0-1.0) for license matching confidence
- **max_extraction_depth**: Integer for nested archive handling
- **network_timeout**: Timeout for network requests in seconds
- **thread_count**: Number of processing threads
- **license_filename_patterns**: List of additional filename patterns
- **custom_aliases**: Custom license name mappings

### 7.4 Exit Codes
- `0`: Success
- `1`: General error
- `2`: Invalid input format
- `3`: Network/download error
- `4`: File system error

## 8. Library API

### 8.1 Core Classes

#### 8.1.1 LegalAttributionGenerator
```python
class LegalAttributionGenerator:
    def __init__(self, config: Optional[Config] = None):
        """Initialize the attribution generator with optional configuration."""
        
    def process_purl(self, purl: str) -> AttributionResult:
        """Process a single package URL."""
        
    def process_purl_list(self, purls: List[str]) -> List[AttributionResult]:
        """Process multiple package URLs."""
        
    def process_purl_file(self, file_path: str) -> List[AttributionResult]:
        """Process package URLs from file."""
        
    def process_local_path(self, path: str) -> AttributionResult:
        """Process local source code directory."""
        
    def generate_kissbom(self, results: List[AttributionResult]) -> dict:
        """Generate enriched KissBOM format."""
        
    def generate_cyclonedx(self, results: List[AttributionResult], format: str = 'json') -> str:
        """Generate CycloneDX SBOM."""
        
    def generate_notices(self, results: List[AttributionResult]) -> str:
        """Generate human-readable legal notices."""
```

#### 8.1.2 AttributionResult
```python
@dataclass
class AttributionResult:
    purl: str
    licenses: List[DetectedLicense]
    copyrights: List[CopyrightInfo]
    errors: List[str]
    confidence_scores: dict
    processing_time: float
```

#### 8.1.3 DetectedLicense
```python
@dataclass
class DetectedLicense:
    spdx_id: str
    name: str
    text: Optional[str]
    confidence: float
    detection_method: str  # 'dice-sorensen', 'tlsh', 'ml', 'regex', 'tag'
    source_file: Optional[str]
```

#### 8.1.4 CopyrightInfo
```python
@dataclass
class CopyrightInfo:
    holder: str
    years: Optional[List[int]]
    statement: str
    source_file: Optional[str]
    confidence: float
```

### 8.2 Usage Examples

#### 8.2.1 Basic Usage
```python
from semantic_copycat_oslili import LegalAttributionGenerator

generator = LegalAttributionGenerator()

# Process single purl
result = generator.process_purl("pkg:pypi/requests@2.28.1")

# Generate output
kissbom = generator.generate_kissbom([result])
notices = generator.generate_notices([result])
```

#### 8.2.2 Advanced Configuration
```python
from semantic_copycat_oslili import LegalAttributionGenerator, Config

config = Config(
    similarity_threshold=0.95,
    thread_count=8,
    custom_aliases={"Apache 2": "Apache-2.0"}
)

generator = LegalAttributionGenerator(config)
results = generator.process_purl_file("packages.txt")
```

## 9. Error Handling and Logging

### 9.1 Error Categories

#### 9.1.1 Input Validation Errors
- Invalid purl format
- Non-existent file paths
- Malformed purl list files

#### 9.1.2 Network Errors
- Failed package downloads
- API timeouts
- Registry unavailability

#### 9.1.3 Processing Errors
- Archive extraction failures
- File encoding issues
- Memory limitations

### 9.2 Error Response Strategy

#### 9.2.1 Graceful Degradation
- Continue processing remaining packages on individual failures
- Log errors with detailed context
- Use "NO-ASSERTION" for missing data
- Provide partial results when possible

#### 9.2.2 Logging Levels
- **ERROR**: Critical failures preventing processing
- **WARNING**: Non-critical issues with fallback handling
- **INFO**: General processing information
- **DEBUG**: Detailed processing steps and intermediate results

### 9.3 Logging Format
```
[TIMESTAMP] [LEVEL] [COMPONENT] MESSAGE
2024-01-15 10:30:45 INFO LicenseDetector Processing package: pkg:pypi/requests@2.28.1
2024-01-15 10:30:46 DEBUG TierOneDetector Dice-Sørensen similarity: 0.98 for MIT license
2024-01-15 10:30:46 WARNING CopyrightExtractor No copyright information found in metadata
```

## 10. Performance Considerations

### 10.1 Multi-threading Strategy
- **File Processing**: Parallel processing of individual files
- **Package Processing**: Concurrent handling of multiple packages
- **Network Requests**: Parallel downloads and API calls
- **Thread Safety**: Ensure thread-safe operations for shared resources

### 10.2 Memory Management
- **Streaming Processing**: Process large files in chunks
- **Temporary File Cleanup**: Automatic cleanup of extracted archives
- **Result Streaming**: Support for processing large package lists
- **Memory Limits**: Configurable memory usage limits

### 10.3 Optimization Features
- **Early Termination**: Stop processing on high-confidence matches
- **Smart Caching**: Cache regex patterns and fuzzy hashes
- **Batch Processing**: Group similar operations for efficiency

## 11. Testing Strategy

### 11.1 Unit Tests
- License detection accuracy across all three tiers
- Copyright extraction pattern matching
- Output format validation
- Configuration handling

### 11.2 Integration Tests
- End-to-end processing with real packages
- Multi-format output generation
- Error handling scenarios
- Performance benchmarks

### 11.3 Test Data
- Curated set of packages with known license information
- Edge cases and challenging license texts
- Various copyright statement formats
- Malformed and problematic inputs

## 12. Security Considerations

### 12.1 Input Validation
- Sanitize all file paths to prevent directory traversal
- Validate purl format to prevent injection attacks
- Limit extraction depth to prevent zip bombs
- Implement file size limits for processing

### 12.2 Network Security
- Use HTTPS for all external requests
- Implement request timeouts
- Validate downloaded content integrity
- Limit network request frequency

### 12.3 Temporary File Handling
- Use secure temporary directories
- Ensure complete cleanup on exit
- Restrict file permissions appropriately

## 13. Compliance and Legal

### 13.1 SPDX Compliance
- Use official SPDX license list
- Support SPDX license expressions
- Include SPDX document generation capabilities
- Maintain compatibility with SPDX tools

### 13.2 Accuracy Disclaimer
- Include disclaimer about automated detection limitations
- Recommend manual review for critical applications
- Provide confidence scores for all detections
- Document known limitations and edge cases

## 14. Installation and Dependencies

### 14.1 Package Distribution
- Publish to PyPI as `semantic-copycat-oslili`
- Include all embedded license data
- Support Python 3.8+
- Provide wheel and source distributions

### 14.2 Installation Commands
```bash
pip install semantic-copycat-oslili

# With optional ML dependencies
pip install semantic-copycat-oslili[ml]

# Development installation
pip install semantic-copycat-oslili[dev]
```

### 14.3 Optional Dependencies
- **ml**: Machine learning libraries for Tier 3 detection
- **dev**: Development and testing tools
- **docs**: Documentation generation tools

## 15. Future Enhancements

### 15.1 Planned Features
- Support for additional package ecosystems
- Custom license template support
- Integration with CI/CD pipelines
- Web service API
- License compatibility analysis

### 15.2 Extensibility
- Plugin architecture for custom license detectors
- Configurable output templates
- Custom copyright extraction patterns
- External tool integrations