---
layout: default
title: Overview
nav_order: 1
description: What osslili does, how to install it, and how to run it for the first time.
permalink: /
---

# osslili

osslili reads source code and tells you which licenses it carries and who holds the
copyright. It identifies licenses against the full SPDX list, extracts copyright
statements, and reports where every finding came from.

It is built for license compliance work, where the question is usually "what am I
allowed to do with this, and how do I know". That focus shows up in two places.
Every detection is traceable to the file and method that produced it, and osslili
does not assert a license it cannot substantiate — an identification it cannot back
up is dropped rather than guessed at.

## Installing

```bash
pip install osslili
```

osslili needs Python 3.9 or later.

### Recommended: install `python-tlsh` too

```bash
pip install osslili python-tlsh
```

`python-tlsh` is optional, but **detection is measurably better with it** and we
recommend installing it for any compliance use.

It powers the fuzzy matching tier, which does two jobs nothing else can. It
identifies license texts that have been reformatted or lightly edited past what
exact and similarity matching recognise — several licenses are detectable *only*
this way. And it corroborates borderline similarity matches, which lets those be
reported at all: without a corroborator the borderline band is closed, because
accepting an unverified match there means reporting one license as another it
merely resembles. Copyleft and permissive licenses are often only a clause apart.

Without it osslili still works and still refuses to guess — it reports less.

`python-tlsh` builds from C++, so it needs a compiler. On a slim container image
install one first — note it is `g++`, not `gcc`:

```bash
apt-get install -y g++ && pip install python-tlsh
```

To work on osslili itself, install it from a checkout in editable mode:

```bash
git clone https://github.com/SemClone/osslili.git
cd osslili
pip install -e ".[dev]"
```

## First run

Point osslili at a directory:

```bash
osslili /path/to/project
```

By default it scans license files, package metadata, and documentation — enough to
answer "what does this project say its license is" in a second or two. It prints
evidence: one entry per detection, with the file, the method, and the confidence.

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

To search every source file for embedded license headers rather than just the
declared license, use `--deep`:

```bash
osslili --deep /path/to/project
```

## What to read next

- **[Usage]({{ site.baseurl }}/usage/)** — scanning modes, every CLI flag, output formats
- **[Detection]({{ site.baseurl }}/detection/)** — how licenses are identified and how to read confidence and category
- **[Python API]({{ site.baseurl }}/api/)** — using osslili as a library
- **[Configuration]({{ site.baseurl }}/configuration/)** — the config file schema and every option
- **[SPDX data]({{ site.baseurl }}/spdx/)** — how the bundled license list is updated

## Where it fits

osslili is the license identification layer of the [SEMCL.ONE](https://semcl.one)
toolchain. [upmex](https://github.com/SemClone/upmex) uses it to resolve the license
of a package archive, and binarysniffer uses it when identifying components inside
compiled artifacts. Anything osslili reports flows through to those tools, which is
why it prefers reporting nothing over reporting a guess.
