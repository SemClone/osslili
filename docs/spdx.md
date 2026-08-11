---
layout: default
title: SPDX data
nav_order: 6
description: How the bundled SPDX license list is stored, when to refresh it, and how to regenerate the derived hash tables.
---

# SPDX data

osslili ships the SPDX license list rather than fetching it at runtime, so scans are
deterministic and work offline. This page covers refreshing that data — a maintainer
task, not something users need to do.

## What is bundled

All under `osslili/data/`:

| File | Contents |
|---|---|
| `spdx_licenses.json` | The SPDX license list: identifiers, names, deprecation status, OSI/FSF flags, and license text for a subset |
| `exact_hashes.json` | SHA-256 and MD5 hashes of normalized license texts, used by the tier 0 exact matcher |
| `license_hashes.json` | TLSH fuzzy hashes, used by the tier 2 matcher |
| `license_normalization.json` | Text normalization rules applied before comparison |
| `regex_patterns.json` | Patterns for the tier 3 reference matcher |

`spdx_licenses.json` records the upstream `licenseListVersion`, its release date, and
the date it was downloaded.

Not every entry carries its license text. Entries without text can still be matched by
tag, keyword, or fuzzy hash, but cannot be confirmed by full-text comparison — which
is why the [TLSH tier]({{ site.baseurl }}/detection/) declines to assert a candidate
whose text it cannot check. Widening text coverage widens what that tier can confirm.

## When to refresh

- SPDX has published a new license list version
- Before a significant release
- Roughly quarterly

`scripts/build_hook.py` reports the age of the bundled data and refreshes it if it is
more than 30 days old.

```bash
python scripts/build_hook.py
```

## Refreshing

{: .warning }
> `scripts/download_spdx_licenses.py` takes no arguments and rewrites
> `osslili/data/spdx_licenses.json` as soon as it is run — there is no dry run and no
> `--help`. Work on a branch and check `git diff` before committing.

### 1. Download the license list

```bash
python scripts/download_spdx_licenses.py
```

Fetches from the [SPDX license-list-data](https://github.com/spdx/license-list-data)
repository and rewrites `spdx_licenses.json`.

### 2. Regenerate the exact hash table

```bash
python scripts/compute_exact_hashes.py
```

Recomputes SHA-256 and MD5 hashes over the normalized texts into
`exact_hashes.json`. This must be run after any change to the license data or to the
normalization rules — stale hashes silently stop the tier 0 matcher from firing.

### 3. Verify

```bash
python -m pytest tests/ -q
```

`tests/test_license_detection_accuracy.py` checks a corpus of canonical license texts
against their expected identifiers, and is what catches a normalization or hash
regression.

Then scan a few real projects and compare against the previous output. A license
count that moves in the hundreds, or canonical texts that stop resolving, means
something went wrong in normalization rather than upstream.

### 4. Review the diff

```bash
git diff --stat osslili/data/
```

Expect new identifiers, updated deprecation flags, and hash churn proportional to the
text changes. Wholesale hash changes with no corresponding text changes indicate a
normalization change, which affects detection for every user.

## Deprecated identifiers

SPDX deprecates identifiers rather than removing them — the bare GNU-family ids
(`GPL-2.0`, `LGPL-2.1`) were replaced by an explicit `-only` / `-or-later`
disjunction, because the bare form does not say whether later versions are permitted.

Deprecated entries stay in the bundled data so existing tags keep matching, and
osslili normalizes them at the emission boundary: `GPL-2.0` is reported as
`GPL-2.0-only`, and the deprecated `GPL-2.0+` form as `GPL-2.0-or-later`.
Normalization only applies when the computed replacement is itself a valid SPDX
identifier, so an unexpected input cannot produce an invented one.

## Adding a license SPDX does not list

Do not hand-edit the bundled data — the next refresh overwrites it. Map the name to a
`LicenseRef-` identifier through `custom_aliases` instead:

```yaml
custom_aliases:
  "My Company Internal License": "LicenseRef-MyCompany-Internal"
```

`LicenseRef-` identifiers pass the SPDX validation that rejects invented names. See
[Configuration]({{ site.baseurl }}/configuration/).
