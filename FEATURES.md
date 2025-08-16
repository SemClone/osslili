# Feature Documentation

## Complete Feature List

### License Detection Capabilities

#### 1. Three-Tier Detection System
- **Tier 1: Dice-Sørensen Similarity** (Primary)
  - Compares file text against 700+ SPDX license texts
  - 97% similarity threshold for high accuracy
  - Character bigram comparison for fuzzy matching
  
- **Tier 2: TLSH Fuzzy Hashing** (Optional)
  - Pre-computed hashes for 699 SPDX licenses
  - Handles significant text variations
  - Install with: `pip install python-tlsh`
  
- **Tier 3: Regex Pattern Matching** (Fallback)
  - Detects common license patterns
  - Identifies license references and indicators

#### 2. Metadata Detection
The tool detects licenses in package metadata files:

- **Python Packages**:
  - `pyproject.toml`: `license = "MIT"` or `license = {text = "Apache-2.0"}`
  - `setup.py`: License field extraction
  - `METADATA`: `License-Expression: BSD-3-Clause`
  - `PKG-INFO`: License field detection

- **JavaScript/npm Packages**:
  - `package.json`: `"license": "MIT"`
  - `bower.json`: License field detection

- **Other Package Types**:
  - `Cargo.toml` (Rust)
  - `go.mod` (Go)
  - `composer.json` (PHP)
  - `*.gemspec` (Ruby)

#### 3. SPDX Tag Detection
Detects various SPDX identifier formats:
- `SPDX-License-Identifier: Apache-2.0`
- `License: MIT`
- `@license BSD-3-Clause`
- `Licensed under the GPL-3.0 License`

#### 4. License File Detection
Automatically finds and analyzes:
- `LICENSE`, `LICENSE.txt`, `LICENSE.md`
- `COPYING`, `COPYING.txt`
- `NOTICE`, `NOTICE.txt`
- `COPYRIGHT`
- Files with fuzzy name matching (85% similarity)

### Copyright Extraction

#### Intelligent Pattern Recognition
- Extracts copyright statements with years
- Handles various formats:
  - `Copyright (c) 2024 Company Name`
  - `© 2023-2024 Author Name`
  - `(C) 2022 Organization`
  - `Author: John Doe`

#### False Positive Filtering
- Filters out code patterns
- Removes invalid email-only entries
- Excludes URLs and domain references
- Validates holder names

#### Year Handling
- Extracts individual years
- Handles year ranges (2020-2024)
- Comma-separated years (2020, 2022, 2024)

### Performance Features

#### Parallel Processing
- Multi-threaded file scanning
- Configurable thread count (`--threads N`)
- Default: 4 threads
- Per-file timeout: 30 seconds

#### Smart File Handling
- **Small files** (<10MB): Full text processing
- **Large files** (>10MB): Intelligent sampling
  - Reads first 100KB + last 50KB
  - No hard size limits or timeouts
  
#### File Type Detection
- Automatically detects text vs binary files
- Skips binary files (images, executables, archives)
- Processes ALL readable text files
- No extension limitations

### Data and Normalization

#### SPDX License Database
- 700 complete SPDX license definitions
- Full license text for 40+ common licenses
- 699 pre-computed TLSH hashes
- 49 common license aliases

#### Text Normalization
- Case-insensitive matching
- Whitespace normalization
- Punctuation removal for comparison
- URL and email filtering
- Copyright line removal for matching

#### Alias Support
Built-in aliases for common variations:
- `Apache 2.0` → `Apache-2.0`
- `MIT License` → `MIT`
- `GPL v3` → `GPL-3.0`
- `BSD 3-Clause` → `BSD-3-Clause`

### Output Features

#### Evidence-Based JSON Output
```json
{
  "file": "/path/to/file",
  "detected_license": "MIT",
  "confidence": 0.98,
  "detection_method": "dice-sorensen",
  "match_type": "text_similarity",
  "description": "Text matches MIT license (98% similarity)"
}
```

#### Standardized Format
- Same JSON structure for all package types
- Consistent field names and types
- Machine-readable and human-understandable

#### Summary Statistics
- Total files scanned
- License counts by type
- Copyright holder counts
- Processing time (with `--verbose`)

### Configuration Options

#### CLI Arguments
- `--output FILE`: Save results to file
- `--threads N`: Number of parallel threads
- `--verbose`: Detailed logging
- `--debug`: Debug-level logging
- `--config FILE`: YAML configuration file
- `--similarity-threshold`: Adjust matching threshold

#### Configuration File
```yaml
similarity_threshold: 0.97
thread_count: 4
max_extraction_depth: 10
license_filename_patterns:
  - "LICENSE*"
  - "COPYING*"
  - "NOTICE*"
```

### Advanced Features

#### Deduplication
- Automatic deduplication of licenses by ID and confidence
- Deduplication of copyright statements
- Prevents duplicate entries in output

#### Error Handling
- Graceful handling of unreadable files
- Permission error logging
- Encoding fallbacks (UTF-8, Latin-1)
- Timeout protection for stuck files

#### Offline Operation
- No internet connection required
- All SPDX data bundled with package
- No external API calls
- Completely self-contained

## Use Cases

### 1. License Compliance Auditing
Scan your entire codebase to ensure all dependencies are properly licensed and documented.

### 2. Attribution Notice Generation
Generate complete attribution notices for open source projects as required by licenses like Apache-2.0.

### 3. SBOM Creation
Create Software Bill of Materials with accurate license information for all components.

### 4. CI/CD Integration
Integrate into build pipelines to verify license compliance before deployment.

### 5. Legal Review
Provide evidence-based reports for legal teams reviewing open source usage.

## Limitations

1. **TLSH Hashing**: Requires optional `python-tlsh` package
2. **ML Detection**: Requires optional ML dependencies (transformers, torch)
3. **Binary Files**: Cannot extract licenses from compiled binaries
4. **Obfuscated Code**: May not detect licenses in heavily obfuscated code
5. **Custom Licenses**: Best results with standard SPDX licenses

## Best Practices

1. **Use Parallel Processing**: Enable multi-threading for large projects
2. **Regular Updates**: Keep the tool updated for latest SPDX licenses
3. **Review Results**: Always review critical license decisions
4. **Configure Thresholds**: Adjust similarity threshold based on needs
5. **Combine Methods**: Use multiple detection methods for accuracy