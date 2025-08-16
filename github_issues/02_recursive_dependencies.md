# Implement Recursive Dependency Analysis

## Description
Add support for analyzing transitive dependencies to generate complete Software Bill of Materials (SBOM). Currently, the tool only analyzes direct packages without exploring their dependency trees.

## Current Behavior
- Only processes explicitly specified packages
- No dependency tree traversal
- Incomplete SBOM for packages with dependencies

## Proposed Solution
Implement recursive dependency analysis for complete attribution:

### Technical Requirements
- [ ] Parse dependency information from package metadata
- [ ] Implement depth-limited recursion
- [ ] Add cycle detection to prevent infinite loops
- [ ] Support different package manager formats

### Implementation Approach
```python
def process_dependencies(self, purl: str, max_depth: int = 5, processed: Set[str] = None):
    """Recursively process package dependencies."""
    if processed is None:
        processed = set()
    
    if purl in processed or max_depth <= 0:
        return []
    
    processed.add(purl)
    results = []
    
    # Process current package
    result = self.process_purl(purl)
    results.append(result)
    
    # Get dependencies
    dependencies = self._extract_dependencies(result)
    
    # Process each dependency
    for dep_purl in dependencies:
        dep_results = self.process_dependencies(
            dep_purl, 
            max_depth - 1, 
            processed
        )
        results.extend(dep_results)
    
    return results
```

### Package-Specific Implementations
- **PyPI**: Parse requirements from metadata
- **npm**: Read dependencies from package.json
- **Maven**: Parse pom.xml
- **Go**: Parse go.mod

## Benefits
- Complete SBOM generation
- Full license compliance checking
- Accurate attribution for all dependencies
- Better supply chain visibility

## Acceptance Criteria
- [ ] Recursively analyzes dependencies up to configurable depth
- [ ] Detects and handles circular dependencies
- [ ] Supports PyPI, npm at minimum
- [ ] Performance remains acceptable (< 30s for typical project)
- [ ] Can be disabled via configuration

## Priority
High

## Labels
`enhancement`, `dependencies`, `sbom`, `feature`