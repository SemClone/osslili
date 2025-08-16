# Build TLSH Hash Database for Tier 2 Detection

## Description
Enhance the TLSH (Trend Micro Locality Sensitive Hash) implementation by building a persistent database of license hashes for fuzzy matching. This will improve detection of slightly modified standard licenses.

## Current Behavior
- Basic TLSH detector exists but lacks hash database
- Cannot compare against known license hashes
- Limited fuzzy matching capability

## Proposed Solution
Create and maintain a TLSH hash database for all known licenses:

### Technical Requirements
- [ ] Generate TLSH hashes for all SPDX licenses
- [ ] Store hashes in efficient database format
- [ ] Implement fuzzy matching with configurable threshold
- [ ] Add hash update mechanism for new licenses

### Implementation Details
```python
class TLSHDatabase:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.hashes = self._load_database()
    
    def build_database(self):
        """Generate TLSH hashes for all known licenses."""
        for license_id, license_text in spdx_licenses.items():
            if len(license_text) >= 50:  # TLSH minimum
                hash_value = tlsh.hash(license_text.encode())
                self.hashes[license_id] = hash_value
        
        self._save_database()
    
    def find_similar(self, text: str, threshold: int = 30):
        """Find licenses similar to given text."""
        query_hash = tlsh.hash(text.encode())
        matches = []
        
        for license_id, stored_hash in self.hashes.items():
            distance = tlsh.diff(query_hash, stored_hash)
            if distance <= threshold:
                matches.append((license_id, distance))
        
        return sorted(matches, key=lambda x: x[1])
```

### Database Structure
```json
{
  "version": "1.0.0",
  "generated": "2025-01-16",
  "hashes": {
    "MIT": "T1F7312B0A2C8F0E3D...",
    "Apache-2.0": "T1A8423C1B3D9E1F4E...",
    ...
  }
}
```

## Benefits
- Detect licenses with minor modifications
- Catch typos and formatting changes
- Improve Tier 2 accuracy to 97%+
- Fast fuzzy matching

## Acceptance Criteria
- [ ] Database includes all SPDX licenses
- [ ] Fuzzy matching with configurable threshold
- [ ] Detection accuracy > 97% for modified licenses
- [ ] Database bundled with package
- [ ] Update mechanism for new licenses

## Priority
Medium

## Labels
`enhancement`, `tier-2`, `tlsh`, `fuzzy-matching`