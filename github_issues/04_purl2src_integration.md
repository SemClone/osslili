# Complete purl2src Integration for Package Acquisition

## Description
Fully integrate the purl2src library to improve package URL resolution and source code acquisition across different package ecosystems.

## Current Behavior
- Using fallback URL resolution
- Limited to basic PyPI and npm support
- Manual URL construction for package downloads

## Proposed Solution
Integrate purl2src for comprehensive package acquisition:

### Technical Requirements
- [ ] Add purl2src as a dependency
- [ ] Implement purl2src resolver
- [ ] Add fallback for when purl2src fails
- [ ] Support additional package ecosystems

### Implementation
```python
class PackageAcquisition:
    def __init__(self, config):
        self.config = config
        try:
            from purl2src import resolve
            self.purl2src_available = True
            self.resolver = resolve
        except ImportError:
            self.purl2src_available = False
    
    def acquire_package(self, purl: PackageURL):
        """Acquire package using purl2src or fallback."""
        if self.purl2src_available:
            try:
                source_info = self.resolver(str(purl))
                return self._download_from_source(source_info)
            except Exception as e:
                logger.warning(f"purl2src failed: {e}, using fallback")
        
        return self._fallback_resolution(purl)
```

### Supported Ecosystems
- PyPI (Python)
- npm (JavaScript)
- Maven Central (Java)
- RubyGems (Ruby)
- Cargo/crates.io (Rust)
- NuGet (.NET)
- Go modules

## Benefits
- Support for more package ecosystems
- More reliable package acquisition
- Automatic source repository discovery
- Better handling of package mirrors

## Acceptance Criteria
- [ ] purl2src integration working
- [ ] Fallback mechanism in place
- [ ] Support for at least 5 ecosystems
- [ ] Improved success rate for package downloads
- [ ] Documentation updated

## Priority
Medium

## Labels
`enhancement`, `package-acquisition`, `purl2src`, `ecosystems`