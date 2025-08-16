# Add SPDX Document Output Format

## Description
Implement SPDX document generation as an output format to comply with industry standards for Software Bill of Materials (SBOM).

## Current Behavior
- Only supports KissBOM and CycloneDX formats
- No SPDX document generation
- Missing industry-standard SBOM format

## Proposed Solution
Add SPDX document generation capability:

### Technical Requirements
- [ ] Implement SPDX 2.3 format support
- [ ] Support both JSON and Tag-Value formats
- [ ] Include all required SPDX fields
- [ ] Add relationship information

### Implementation
```python
class SPDXFormatter:
    def format(self, results: List[AttributionResult]) -> Dict:
        """Generate SPDX document."""
        spdx_doc = {
            "spdxVersion": "SPDX-2.3",
            "dataLicense": "CC0-1.0",
            "SPDXID": "SPDXRef-DOCUMENT",
            "name": "Attribution Report",
            "documentNamespace": self._generate_namespace(),
            "creationInfo": {
                "created": datetime.now().isoformat(),
                "creators": ["Tool: semantic-copycat-oslili-1.1.1"],
                "licenseListVersion": "3.20"
            },
            "packages": []
        }
        
        for result in results:
            package = self._create_spdx_package(result)
            spdx_doc["packages"].append(package)
        
        return spdx_doc
    
    def _create_spdx_package(self, result: AttributionResult):
        """Create SPDX package entry."""
        return {
            "SPDXID": f"SPDXRef-Package-{self._sanitize_id(result.purl)}",
            "name": result.package_name,
            "downloadLocation": result.source_location or "NOASSERTION",
            "filesAnalyzed": True,
            "licenseConcluded": result.get_primary_license().spdx_id,
            "licenseInfoFromFiles": [l.spdx_id for l in result.licenses],
            "copyrightText": self._format_copyright(result.copyrights)
        }
```

### Output Example
```json
{
  "spdxVersion": "SPDX-2.3",
  "dataLicense": "CC0-1.0",
  "SPDXID": "SPDXRef-DOCUMENT",
  "name": "Attribution Report",
  "packages": [
    {
      "name": "requests",
      "licenseConcluded": "Apache-2.0",
      "copyrightText": "Copyright 2019 Kenneth Reitz"
    }
  ]
}
```

## Benefits
- Industry-standard SBOM format
- Better tool interoperability
- Compliance with regulations
- Machine-readable attribution data

## Acceptance Criteria
- [ ] Valid SPDX 2.3 document generation
- [ ] Passes SPDX validation tools
- [ ] Includes all detected licenses and copyrights
- [ ] Supports JSON and Tag-Value formats
- [ ] CLI option: `-f spdx-json` and `-f spdx-tv`

## Priority
Medium

## Labels
`enhancement`, `output-format`, `spdx`, `sbom`