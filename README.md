# osslili — OSS License & Copyright Detector

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![PyPI version](https://img.shields.io/pypi/v/osslili.svg)](https://pypi.org/project/osslili/)

osslili reads source code and tells you which licenses it carries and who holds the
copyright. It identifies licenses against the full SPDX list, extracts copyright
statements, and reports where every finding came from.

It is built for license compliance work, where the question is usually "what am I
allowed to do with this, and how do I know". Every detection is traceable to the file
and method that produced it, and osslili does not assert a license it cannot
substantiate — an identification it cannot back up is dropped rather than guessed at.

**Documentation: [semclone.github.io/osslili](https://semclone.github.io/osslili/)**

## Installation

```bash
pip install osslili
```

Requires Python 3.9 or later.

**Recommended:** install `python-tlsh` alongside it.

```bash
pip install osslili python-tlsh
```

It is optional, but detection is measurably better with it. It powers the fuzzy
matching tier, which identifies license texts too reformatted for exact or
similarity matching — several licenses are detectable only this way — and
corroborates borderline similarity matches so they can be reported at all.
Without a corroborator that band stays closed, because accepting an unverified
match there means reporting one license as another it merely resembles, and
copyleft and permissive licenses are often a single clause apart.

`python-tlsh` builds from C++ and needs a compiler. On slim container images
install one first:

```bash
apt-get install -y g++
```

For development:

```bash
git clone https://github.com/SemClone/osslili.git
cd osslili
pip install -e ".[dev]"
```

## Quick start

```bash
# Declared license of a project — license files, metadata, README
osslili .

# Everything, including license headers embedded in source
osslili --deep .

# SBOM output
osslili -f cyclonedx-json -o sbom.json .
```

```json
{
  "scan_results": [
    {
      "path": ".",
      "license_evidence": [
        {
          "file": "/path/to/project/package.json",
          "detected_license": "MIT",
          "confidence": 1.0,
          "detection_method": "tag",
          "category": "declared",
          "match_type": "package_metadata",
          "description": "Package metadata declares MIT license"
        },
        {
          "file": "/path/to/project/LICENSE",
          "detected_license": "MIT",
          "confidence": 0.997,
          "detection_method": "dice-sorensen",
          "category": "declared",
          "match_type": "license_file",
          "description": "License file contains MIT license"
        }
      ]
    }
  ]
}
```

## Scanning modes

| Mode | Command | Reads |
|---|---|---|
| Default | `osslili .` | License files, package metadata, README |
| Deep | `osslili --deep .` | All of the above plus every source file |
| Strict | `osslili --license-files-only .` | License files only |

Default mode answers "what does this project declare". Deep mode finds license headers
embedded in code and vendored third-party files, and is considerably slower.

## How detection works

Each file goes through several independent passes — package metadata, SPDX tags,
keyword matching, and a four-tier full-text cascade:

| Tier | Method | Basis |
|---|---|---|
| 0 | `hash` | Exact SHA-256 / MD5 of the normalized text |
| 1 | `dice-sorensen` | Character-bigram text similarity |
| 2 | `tlsh` | Fuzzy hashing, corroborated against the license text |
| 3 | `regex` | Patterns for references and headers |

Detections are not collapsed to a single answer — agreement between independent
methods is itself evidence. Each carries a `category` (`declared`, `detected`,
`referenced`, `third-party`) and a confidence score.

Licenses found in bundled third-party notice files are categorized separately, so a
vendored `THIRD_PARTY_NOTICES` file does not make a permissive project look copyleft.

See [Detection](https://semclone.github.io/osslili/detection/) for the full picture,
including why the fuzzy tier verifies its own candidates before reporting them.

## Library usage

```python
from osslili import LicenseCopyrightDetector

detector = LicenseCopyrightDetector()
result = detector.process_local_path("/path/to/source")

primary = result.get_primary_license()
if primary:
    print(f"{primary.spdx_id} ({primary.confidence:.0%} via {primary.detection_method})")

# The project's own licenses, excluding bundled third-party notices
for license in result.get_own_licenses():
    print(license.spdx_id, license.category, license.source_file)

for copyright in result.copyrights:
    print(copyright.statement)

# Output formats
evidence = detector.generate_evidence([result], detail_level="full")
kissbom = detector.generate_kissbom([result])
sbom = detector.generate_cyclonedx([result], format_type="json")
```

## Configuration

```bash
osslili -c osslili.yaml .
```

```yaml
similarity_threshold: 0.97
max_recursion_depth: 4
thread_count: 4
cache_dir: ~/.cache/osslili
custom_aliases:
  "My Company License": "LicenseRef-MyCompany"
```

Every option is documented at
[Configuration](https://semclone.github.io/osslili/configuration/).

## Documentation

Full documentation is at **[semclone.github.io/osslili](https://semclone.github.io/osslili/)**.

- [Overview](https://semclone.github.io/osslili/) — what osslili does, installing, first run
- [Usage](https://semclone.github.io/osslili/usage/) — scanning modes, every flag, output formats
- [Detection](https://semclone.github.io/osslili/detection/) — how licenses are identified, reading confidence and category
- [Python API](https://semclone.github.io/osslili/api/) — using osslili as a library
- [Configuration](https://semclone.github.io/osslili/configuration/) — config file schema and all options
- [SPDX data](https://semclone.github.io/osslili/spdx/) — refreshing the bundled license list

The pages are built from `docs/` in this repository, so corrections can go straight
into a pull request.

## Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for details on:
- Code of conduct
- Development setup
- Submitting pull requests
- Reporting issues

## Support

- [GitHub Issues](https://github.com/SemClone/osslili/issues) — bug reports and feature requests
- [Documentation](https://semclone.github.io/osslili/) — complete project documentation

## License

Apache License 2.0 — see [LICENSE](LICENSE) file for details.

## Authors

See [AUTHORS.md](AUTHORS.md) for a list of contributors.

---

*Part of the [SEMCL.ONE](https://semcl.one) ecosystem for comprehensive OSS compliance and code analysis.*
