---
layout: default
title: Configuration
nav_order: 5
description: The YAML configuration file schema and every Config option, with defaults.
---

# Configuration

Configuration can come from a YAML file passed with `-c`, or be set directly on a
`Config` object when using the library. Command line flags override file values.

```bash
osslili -c osslili.yaml /path/to/project
```

```python
from osslili import LicenseCopyrightDetector, Config
from osslili.utils.config_loader import ConfigLoader

config = ConfigLoader.load_from_file("osslili.yaml")
detector = LicenseCopyrightDetector(config)
```

Unknown keys are logged as warnings and ignored, so a typo will not silently change
behaviour — run with `-v` to see them.

## Example

```yaml
# Matching
similarity_threshold: 0.97

# Traversal
max_recursion_depth: 4
max_extraction_depth: 3
thread_count: 4

# Scanning mode
license_files_only: true
strict_license_files: false
deep_scan: false

# Performance
skip_content_detection: false
skip_extensionless: false
skip_smart_read: false
max_file_size_kb: null
fast_mode: false

# Caching
cache_dir: ~/.cache/osslili

# Logging
verbose: false
debug: false

# Names that count as a license file, beyond the ones recognized by shape
license_filename_patterns:
  - "LICENSE"
  - "LICENCE"
  - "COPYING"
  - "NOTICE"
  - "OUR-TERMS*"

license_fuzzy_base_names:
  - license
  - licence
  - copying
  - copyright
  - notice

# Extra name-to-SPDX mappings, merged with the built-in aliases
custom_aliases:
  "My Company License": "LicenseRef-MyCompany"
  "Apache Software License": "Apache-2.0"
```

## Options

### Matching

| Option | Default | Description |
|---|---|---|
| `similarity_threshold` | `0.97` | Minimum text similarity for a full-text match. Lowering it increases recall and false positives. |

### Traversal

| Option | Default | Description |
|---|---|---|
| `max_recursion_depth` | `4` | Directory recursion limit. `-1` for unlimited. |
| `max_extraction_depth` | `3` | Nested archive extraction limit. |
| `thread_count` | `4` | Worker threads. |

{: .note }
> `max_extraction_depth` defaults to `3` on a bare `Config`, but the
> `--max-extraction-depth` flag defaults to `10` and always sets it. A library caller
> who wants the CLI's behaviour has to set it explicitly.

### Scanning mode

| Option | Default | Description |
|---|---|---|
| `license_files_only` | `true` | Scan license files, metadata, and README only. Set `false` for a full source scan. |
| `strict_license_files` | `false` | With `license_files_only`, restrict further to license files alone — no metadata, no README. |
| `deep_scan` | `false` | Comprehensive scan of all source files. Set together with `license_files_only: false`. |

These three combine into the modes described in [Usage]({{ site.baseurl }}/usage/):

| Mode | `license_files_only` | `strict_license_files` | `deep_scan` |
|---|---|---|---|
| Default | `true` | `false` | `false` |
| Strict | `true` | `true` | `false` |
| Deep | `false` | `false` | `true` |

### Performance

| Option | Default | Description |
|---|---|---|
| `fast_mode` | `false` | Preset; enables the three skips below and caps file size at 1024 KB. |
| `skip_content_detection` | `false` | Trust file extensions instead of sniffing content. |
| `skip_extensionless` | `false` | Skip files with no extension unless they match a known license filename. |
| `skip_smart_read` | `false` | Read files whole rather than sampling their start and end. |
| `max_file_size_kb` | `None` | Skip files larger than this. `None` means no limit. |

### Caching

| Option | Default | Description |
|---|---|---|
| `cache_dir` | `None` | Directory for cached scan results. `None` disables caching. |

Caching is keyed on the scanned path. Enable it when scanning the same trees
repeatedly; leave it off for one-shot scans.

There is no `--cache-dir` command line flag — set `cache_dir` in a config file, or
assign it on a `Config` object.

### License file recognition

| Option | Default | Description |
|---|---|---|
| `license_filename_patterns` | see below | Glob patterns identifying license files. Replaces the built-in list when set. |
| `license_fuzzy_base_names` | `license`, `licence`, `copying`, `copyright`, `notice` | Base names matched fuzzily, catching misspellings and suffixed variants. |

The built-in patterns are the canonical names:

```
LICENSE  LICENCE  COPYING  NOTICE  COPYRIGHT
UNLICENSE  COPYLEFT  EULA  LEGAL
MIT-LICENSE  APACHE-LICENSE  BSD-LICENSE
3rdpartylicenses.txt
```

Most license files need no pattern at all, because a license filename is recognized
by its **shape**: the stem is a license word on its own, or a license word joined to
the license being named. `LICENSE-MIT`, `MIT-LICENSE.txt`, `COPYING.LESSER`,
`LICENSE.APACHE2` and `THIRD_PARTY_NOTICES` are all recognized without being listed.

One limit worth knowing: a strict scan (`--license-files-only`) looks for candidates
using the patterns above and the `license_fuzzy_base_names`, and applies the shape
rule to what it finds. A name carrying only the license and no license word —
`GPL-3.0.txt` — is not among those candidates, so add a pattern for it if your
project uses that form. An ordinary scan reads it anyway, as documentation.

Every part of the name has to belong and at least one has to name a license, so a
file that merely mentions one is not treated as holding one:

| name | license file? | why |
|---|---|---|
| `LICENSE-MIT` | yes | a license word joined to a license |
| `COPYING.LESSER` | yes | the license is written into the suffix |
| `docs/license-policy.md` | no | "policy" is not a license word |
| `license_manager.py` | no | a code suffix, and "manager" is not a license word |
| `bundle.js` | no | "bundle" is not a license word at all |
| `gplus.py` | no | a part matches whole; `gplus` is not `gpl` |

Earlier releases matched any name *containing* a license word, so every JavaScript
bundle and every page written about licensing was read as the project's own license
declaration. See issue #116.

Setting `license_filename_patterns` replaces the built-in list rather than adding to
it, but the shape rule still applies either way — a pattern is for a name your project
uses that no rule would guess, such as `OUR-TERMS.md`.

Files matching a third-party marker together with a notice token — `THIRD_PARTY_NOTICES`,
`3rdparty-licenses.txt` — are still scanned, but their findings are categorized as
`third-party` rather than as the project's own license.

### Aliases

| Option | Default | Description |
|---|---|---|
| `custom_aliases` | see below | Extra license-name-to-SPDX mappings. Merged with the built-ins, not replaced. |

Built-in aliases cover the common informal names:

```
Apache 2, Apache 2.0, Apache License 2.0  ->  Apache-2.0
MIT License                               ->  MIT
BSD License                               ->  BSD-3-Clause
ISC License                               ->  ISC
GPLv2 -> GPL-2.0    GPLv3 -> GPL-3.0
LGPLv2 -> LGPL-2.0  LGPLv3 -> LGPL-3.0
```

For a license with no SPDX identifier, map it to a `LicenseRef-` identifier — those
pass the SPDX validation that would otherwise reject an invented name.

### Logging

| Option | Default | Description |
|---|---|---|
| `verbose` | `false` | Verbose logging. |
| `debug` | `false` | Debug logging, including rejected detection candidates and why. |

## Environment variables

| Variable | Description |
|---|---|
| `OSLILI_DEBUG` | Set to `1` to keep SSL and urllib3 warnings visible, which osslili otherwise suppresses on import. |
