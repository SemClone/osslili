# SPDX License Data Management

This document describes how to update the bundled SPDX license data used by osslili for license detection.

## Overview

The tool uses bundled SPDX license data stored in `osslili/data/spdx_licenses.json`. This data includes:
- 700+ SPDX license definitions
- License texts for common licenses
- Aliases and name mappings
- TLSH hashes for fuzzy matching

## When to Update

Update the SPDX data when:
- New SPDX licenses are released (check https://spdx.org/licenses/)
- Before major releases
- At least quarterly to ensure data freshness
- The current data is checked via `scripts/build_hook.py` (30-day threshold)

## Update Process

### 1. Check Current Data Age

```bash
# Check if data needs updating (>30 days old)
python scripts/build_hook.py
```

### 2. Backup Current Data

```bash
# Create backup of current data
cp osslili/data/spdx_licenses.json osslili/data/spdx_licenses.json.backup
cp osslili/data/license_hashes.json osslili/data/license_hashes.json.backup
```

### 3. Run Update Script

```bash
# Download and process latest SPDX data
python scripts/download_spdx_licenses.py
```

This script will:
1. Download the latest SPDX license list from GitHub
2. Fetch license texts for common licenses
3. Generate TLSH hashes for fuzzy matching
4. Create aliases and name mappings
5. Save to `osslili/data/spdx_licenses.json`

### 4. Verify Update

```bash
# Check file was updated
ls -la osslili/data/spdx_licenses.json

# Verify JSON structure
python -c "import json; data = json.load(open('osslili/data/spdx_licenses.json')); print(f'Licenses: {len(data[\"licenses\"])}, Aliases: {len(data[\"aliases\"])}')"

# Compare with backup
python -c "
import json
old = json.load(open('osslili/data/spdx_licenses.json.backup'))
new = json.load(open('osslili/data/spdx_licenses.json'))
print(f'Old licenses: {len(old[\"licenses\"])}, New licenses: {len(new[\"licenses\"])}')
print(f'Old aliases: {len(old[\"aliases\"])}, New aliases: {len(new[\"aliases\"])}')
"
```

### 5. Test Detection

```bash
# Run tests to ensure detection still works
python -m pytest tests/test_license_detector.py -v

# Or manually test
python -c "
from osslili import LicenseCopyrightDetector
detector = LicenseCopyrightDetector()
# Test should detect MIT license
result = detector.process_local_path('LICENSE')
print(f'Detected: {result.licenses[0].spdx_id if result.licenses else \"None\"}')"
```

### 6. Commit Updates

```bash
# If tests pass, commit the updated data
git add osslili/data/spdx_licenses.json
git commit -m "chore: Update SPDX license data to latest version"
```

## Data Structure

The `spdx_licenses.json` file contains:

```json
{
  "licenses": {
    "MIT": {
      "name": "MIT License",
      "isOsiApproved": true,
      "text": "MIT License text...",
      "tlsh_hash": "T1..."
    },
    ...
  },
  "aliases": {
    "MIT License": "MIT",
    "Apache 2.0": "Apache-2.0",
    ...
  },
  "name_mappings": {
    "mit license": "MIT",
    "apache license 2.0": "Apache-2.0",
    ...
  }
}
```

## Troubleshooting

### Download Fails
- Check internet connection
- Verify GitHub API is accessible
- Check rate limits (script includes delays)

### JSON Structure Changed
- Review SPDX API changes at https://github.com/spdx/license-list-data
- Update `scripts/download_spdx_licenses.py` if needed

### Tests Fail After Update
- Check for removed licenses
- Verify TLSH hashes were generated
- Ensure aliases are properly mapped

## Manual Data Sources

If automatic download fails, manually download from:
- License list: https://raw.githubusercontent.com/spdx/license-list-data/main/json/licenses.json
- Individual licenses: https://raw.githubusercontent.com/spdx/license-list-data/main/json/details/[LICENSE-ID].json

## Notes

- The bundled data approach ensures offline operation
- SPDX licenses change infrequently (a few additions per year)
- The 30-day threshold in `build_hook.py` is configurable
- TLSH hashes are stored separately in `license_hashes.json`
- As of August 2025, the database contains 700+ licenses with 1841+ name mappings

## Last Update Test

Test performed on 2025-08-30:
- Successfully downloaded 703 licenses (3 new since last update)
- New licenses added: ESA-PL-weak-copyleft-2.4, BSD-3-Clause-Tso, WTFNMFPL
- Name mappings increased from 1841 to 1849
- File size: ~1.5MB
- License detection confirmed working after update