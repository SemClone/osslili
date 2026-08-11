---
layout: default
title: Python API
nav_order: 4
description: Using osslili as a library, with the classes and fields it actually exposes.
---

# Python API

Everything you normally need is exported from the top-level package:

```python
from osslili import (
    LicenseCopyrightDetector,
    DetectionResult,
    DetectedLicense,
    CopyrightInfo,
    Config,
)
```

## Quick start

```python
from osslili import LicenseCopyrightDetector

detector = LicenseCopyrightDetector()
result = detector.process_local_path("/path/to/project")

primary = result.get_primary_license()
if primary:
    print(f"{primary.spdx_id} ({primary.confidence:.2f} via {primary.detection_method})")

for c in result.copyrights:
    print(c.statement)
```

## LicenseCopyrightDetector

```python
LicenseCopyrightDetector(config: Optional[Config] = None)
```

Omit `config` for defaults. The detector loads its SPDX data lazily, so constructing
one is cheap; reuse a single instance across scans to avoid reloading it.

### process_local_path

```python
process_local_path(path: str, extract_archives: bool = True) -> DetectionResult
```

Scan a directory, a file, or an archive. With `extract_archives=True` an archive is
extracted to a temporary directory and scanned in place.

```python
result = detector.process_local_path("./package-1.0.0.tar.gz")
result = detector.process_local_path("./src", extract_archives=False)
```

### extract_package_metadata

```python
extract_package_metadata(path: str) -> DetectionResult
```

Read only the declared license from package metadata files, skipping all text
analysis. Use it when you want the declared license and nothing inferred — it is
substantially faster than a full scan.

```python
result = detector.extract_package_metadata("./package.json")
```

### generate_evidence

```python
generate_evidence(results: List[DetectionResult], detail_level: str = "detailed") -> str
```

Render results as an evidence JSON string. `detail_level` is `"minimal"`,
`"summary"`, `"detailed"`, or `"full"`. Note that it takes a **list** of results.

```python
print(detector.generate_evidence([result], detail_level="full"))
```

### generate_kissbom

```python
generate_kissbom(results: List[DetectionResult]) -> str
```

### generate_cyclonedx

```python
generate_cyclonedx(results: List[DetectionResult], format_type: str = "json") -> str
```

`format_type` is `"json"` or `"xml"`.

```python
with open("sbom.json", "w") as f:
    f.write(detector.generate_cyclonedx([result]))
```

## DetectionResult

| Field | Type | Description |
|---|---|---|
| `path` | `str` | The scanned path |
| `licenses` | `List[DetectedLicense]` | Every detection, sorted by confidence |
| `copyrights` | `List[CopyrightInfo]` | Extracted copyright statements |
| `errors` | `List[str]` | Non-fatal errors encountered |
| `confidence_scores` | `Dict[str, float]` | Highest confidence per category (`license`, `copyright`) |
| `processing_time` | `float` | Seconds elapsed |
| `package_name` | `Optional[str]` | Package name, when determinable |
| `package_version` | `Optional[str]` | Package version, when determinable |

### Methods

```python
get_primary_license() -> Optional[DetectedLicense]
get_own_licenses() -> List[DetectedLicense]
get_third_party_licenses() -> List[DetectedLicense]
to_dict() -> Dict[str, Any]
```

`get_primary_license()` returns the project's own best-supported license, or `None`.
It never returns a license sourced from a bundled third-party notice file — if only
third-party notices were found it returns `None`, and those licenses remain available
through `get_third_party_licenses()`.

This distinction matters when determining what a project is licensed under. A
vendored `THIRD_PARTY_NOTICES` file contains dependencies' licenses, and counting them
as the project's own can turn a permissive project into an apparently copyleft one:

```python
result = detector.process_local_path("./project")

own = result.get_own_licenses()
third_party = result.get_third_party_licenses()

print("This project:", sorted({l.spdx_id for l in own}))
print("Bundled deps:", sorted({l.spdx_id for l in third_party}))
```

## DetectedLicense

| Field | Type | Description |
|---|---|---|
| `spdx_id` | `str` | SPDX identifier, always validated against the SPDX list |
| `name` | `str` | Human-readable license name |
| `text` | `Optional[str]` | License text, when captured |
| `confidence` | `float` | 0.0–1.0 |
| `detection_method` | `str` | `hash`, `dice-sorensen`, `tlsh`, `regex`, `tag`, `keyword`, `filename` |
| `source_file` | `Optional[str]` | File the detection came from |
| `category` | `Optional[str]` | `declared`, `detected`, `referenced`, `third-party` |
| `match_type` | `Optional[str]` | How it matched, e.g. `license_file`, `package_metadata`, `keyword` |

See [Detection]({{ site.baseurl }}/detection/) for what these values mean.

## CopyrightInfo

| Field | Type | Description |
|---|---|---|
| `holder` | `str` | Copyright holder |
| `years` | `Optional[List[int]]` | Years claimed |
| `statement` | `str` | The full statement as it appears |
| `source_file` | `Optional[str]` | File it came from |
| `confidence` | `float` | 0.0–1.0 |

## Enums

```python
from osslili.core.models import LicenseCategory, DetectionMethod

LicenseCategory.DECLARED     # "declared"
LicenseCategory.DETECTED     # "detected"
LicenseCategory.REFERENCED   # "referenced"
LicenseCategory.THIRD_PARTY  # "third-party"

DetectionMethod.HASH           # "hash"
DetectionMethod.DICE_SORENSEN  # "dice-sorensen"
DetectionMethod.TLSH           # "tlsh"
DetectionMethod.REGEX          # "regex"
DetectionMethod.TAG            # "tag"
DetectionMethod.KEYWORD        # "keyword"
DetectionMethod.FILENAME       # "filename"
```

Compare against `.value` when reading a `DetectedLicense`, since its fields hold
strings:

```python
declared = [l for l in result.licenses if l.category == LicenseCategory.DECLARED.value]
```

## Examples

### Scanning several projects

```python
from pathlib import Path
from osslili import LicenseCopyrightDetector

detector = LicenseCopyrightDetector()
results = [detector.process_local_path(str(p)) for p in Path("./repos").iterdir() if p.is_dir()]

with open("sbom.json", "w") as f:
    f.write(detector.generate_cyclonedx(results))
```

### Deep scan with a tuned configuration

```python
from osslili import LicenseCopyrightDetector, Config

config = Config()
config.license_files_only = False   # scan all source files
config.deep_scan = True
config.thread_count = 8
config.max_recursion_depth = -1     # unlimited

result = LicenseCopyrightDetector(config).process_local_path("./project")
```

### Failing a build on an unexpected license

```python
ALLOWED = {"MIT", "Apache-2.0", "BSD-3-Clause", "ISC"}

result = detector.process_local_path("./project")
unexpected = {l.spdx_id for l in result.get_own_licenses()} - ALLOWED

if unexpected:
    raise SystemExit(f"Unexpected licenses: {sorted(unexpected)}")
```

Use `get_own_licenses()` rather than `result.licenses` here — bundled third-party
notices would otherwise fail the check for licenses the project does not itself carry.
