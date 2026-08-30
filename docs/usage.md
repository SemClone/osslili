---
layout: default
title: Usage
nav_order: 2
description: Scanning modes, every command line flag, and the output formats osslili produces.
---

# Usage

```
osslili [OPTIONS] INPUT_PATH
```

`INPUT_PATH` is a directory to scan recursively, a single file to analyze, or an
archive to extract and scan.

## Scanning modes

The mode decides which files are read. It is the single biggest influence on both
runtime and what you find.

### Default

```bash
osslili /path/to/project
```

Reads license files, package metadata, and documentation:

- license files — `LICENSE`, `COPYING`, `NOTICE`, `LICENSE-MIT`, `COPYING.LESSER`, `THIRD_PARTY_NOTICES` and anything else shaped like a license filename ([how that is decided]({{ site.baseurl }}/configuration/#license-file-recognition))
- package metadata — `package.json`, `pyproject.toml`, `setup.py`, `setup.cfg`, `pom.xml`, `Cargo.toml`, `composer.json`, `build.gradle`, `*.gemspec`, `*.nuspec`
- documentation — `README*` and other markdown and text files

This answers "what does this project declare its license to be". It does not look
inside source files, so an embedded license header in a vendored `.c` file will be
missed.

### Deep

```bash
osslili --deep /path/to/project
```

Everything the default mode reads, plus every readable source file. This is what
finds license headers embedded in code, vendored third-party files, and licenses
that are never declared in metadata. It is considerably slower, because each file
carrying license-like text is compared against the SPDX corpus.

### Strict

```bash
osslili --license-files-only /path/to/project
```

License files only — no metadata, no README. Useful when you want the license as
stated in the license file itself and nothing inferred from packaging.

## Options

### Output

| Flag | Description |
|---|---|
| `-o, --output PATH` | Write to a file instead of stdout |
| `-f, --output-format FORMAT` | `evidence` (default), `kissbom`, `cyclonedx-json`, `cyclonedx-xml` |
| `--evidence-detail LEVEL`, `--detail LEVEL` | `minimal`, `summary`, `detailed` (default), `full` |

`--evidence-detail` only affects the `evidence` format:

- `minimal` — the license summary only
- `summary` — per-method detection counts
- `detailed` — a sample of detections per license
- `full` — every detection, unabridged

### Scanning

| Flag | Description |
|---|---|
| `--deep` | Scan all source files, not just declared-license locations |
| `--license-files-only` | Scan only license files, excluding metadata and README |
| `--max-depth N`, `--max-recursion-depth N` | Directory recursion limit (default `4`, `-1` for unlimited) |
| `--max-extraction-depth N` | Nested archive extraction limit (default `10`) |
| `--similarity-threshold FLOAT` | Minimum text similarity for a match (default `0.97`) |

### Performance

| Flag | Description |
|---|---|
| `--fast` | Preset combining the four optimizations below |
| `--skip-content-detection` | Do not sniff file types by content, trust extensions |
| `--skip-extensionless` | Skip files with no extension unless they match a known license filename |
| `--max-file-size KB` | Skip files larger than this |
| `--skip-smart-read` | Read files whole instead of sampling start and end |
| `-t, --threads N` | Worker threads (default `4`) |

`--fast` sets `--skip-content-detection`, `--skip-extensionless`, `--skip-smart-read`,
and a 1 MB file size cap. It trades recall for speed: extensionless vendored files
and licenses buried deep in large files can be missed.

### General

| Flag | Description |
|---|---|
| `-c, --config PATH` | Load a YAML configuration file |
| `-v, --verbose` | Verbose logging |
| `-d, --debug` | Debug logging, including why detections were rejected |
| `--version` | Print the version |
| `--help` | Print usage |

`--debug` is the flag to reach for when osslili reports nothing for a file you expect
it to identify. Rejected candidates are logged with the reason.

## Output formats

### Evidence (default)

One entry per detection, with the file it came from, the method that produced it, and
the confidence. This is the format to use when you need to justify a conclusion rather
than just state it.

```json
{
  "scan_results": [
    {
      "path": ".",
      "license_evidence": [
        {
          "file": "/path/to/project/LICENSE",
          "detected_license": "MIT",
          "confidence": 0.997,
          "detection_method": "dice-sorensen",
          "category": "declared",
          "match_type": "license_file",
          "description": "License file contains MIT license"
        }
      ],
      "copyright_evidence": []
    }
  ]
}
```

See [Detection]({{ site.baseurl }}/detection/) for what `detection_method`,
`category`, and `confidence` mean.

### KissBOM

A minimal bill of materials: one entry per scanned path with the resolved license.

```json
{
  "packages": [
    {
      "path": ".",
      "license": "MIT",
      "copyright": "Andrey Petrov and contributors",
      "all_licenses": ["MIT"]
    }
  ]
}
```

`license` and `all_licenses` cover the project's own licenses. Licenses found in
bundled third-party notice files are reported separately under
`third_party_licenses`, so they do not get mistaken for the project's own.

### CycloneDX

```bash
osslili -f cyclonedx-json /path/to/project
osslili -f cyclonedx-xml  /path/to/project
```

Standard CycloneDX SBOM output. Component `licenses` carry the project's own
licenses; third-party licenses are emitted as `osslili:third-party-license`
properties rather than mixed into the component's license list.

## Examples

```bash
# Declared license of a project, quickly
osslili .

# Everything, including embedded headers in vendored code
osslili --deep .

# Full evidence to a file, for an audit trail
osslili --deep --detail full -o evidence.json .

# SBOM for a release artifact
osslili -f cyclonedx-json -o sbom.json ./dist

# Large monorepo: cap the work
osslili --fast --max-depth 3 -t 8 .

# A single license file
osslili ./LICENSE

# An archive, extracted and scanned in place
osslili ./package-1.0.0.tar.gz
```
