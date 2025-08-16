# Implement Caching Layer for Performance

## Description
Add a persistent caching layer to avoid re-processing packages and improve performance for repeated scans.

## Current Behavior
- No persistent caching
- Re-processes same packages every time
- Performance impact on large-scale scans

## Proposed Solution
Implement multi-level caching system:

### Technical Requirements
- [ ] Package-level result caching
- [ ] License detection caching
- [ ] External API response caching
- [ ] Cache invalidation strategy
- [ ] Configurable cache TTL

### Implementation
```python
class CacheManager:
    def __init__(self, cache_dir: Path, ttl_days: int = 7):
        self.cache_dir = cache_dir
        self.ttl = timedelta(days=ttl_days)
        self.cache_dir.mkdir(exist_ok=True)
    
    def get_cached_result(self, purl: str) -> Optional[AttributionResult]:
        """Retrieve cached result for package."""
        cache_key = self._generate_key(purl)
        cache_file = self.cache_dir / f"{cache_key}.json"
        
        if cache_file.exists():
            if self._is_valid(cache_file):
                with open(cache_file) as f:
                    data = json.load(f)
                    return AttributionResult.from_dict(data)
        
        return None
    
    def cache_result(self, purl: str, result: AttributionResult):
        """Cache attribution result."""
        cache_key = self._generate_key(purl)
        cache_file = self.cache_dir / f"{cache_key}.json"
        
        with open(cache_file, 'w') as f:
            json.dump(result.to_dict(), f)
    
    def _is_valid(self, cache_file: Path) -> bool:
        """Check if cache entry is still valid."""
        age = datetime.now() - datetime.fromtimestamp(cache_file.stat().st_mtime)
        return age < self.ttl
```

### Cache Structure
```
~/.cache/oslili/
├── packages/
│   ├── pypi_requests_2.28.1.json
│   └── npm_express_4.18.2.json
├── licenses/
│   └── <file_hash>.json
└── api_responses/
    └── <api_endpoint_hash>.json
```

## Benefits
- Faster repeated scans
- Reduced API calls
- Better performance for CI/CD
- Lower resource usage

## Acceptance Criteria
- [ ] Cache hits improve performance by >80%
- [ ] Configurable TTL and location
- [ ] Cache invalidation options
- [ ] CLI flag to bypass cache
- [ ] Cache size management

## Priority
Medium

## Labels
`enhancement`, `performance`, `caching`