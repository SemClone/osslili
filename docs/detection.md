---
layout: default
title: Detection
nav_order: 3
description: How osslili identifies a license, and how to read the method, category, and confidence it reports.
---

# Detection

Every finding osslili reports carries three fields that say how much weight it
deserves: `detection_method`, `category`, and `confidence`. This page explains what
each one means and how identification actually works.

## What runs on a file

Each file is put through several independent passes. They do not stop at the first
hit — a file can produce several detections, and that redundancy is deliberate:
agreement between independent methods is itself evidence.

**Package metadata.** For `package.json`, `pyproject.toml`, `pom.xml`, `Cargo.toml`
and friends, the declared license field is read directly. Structured, unambiguous,
and reported at full confidence.

**SPDX tags.** `SPDX-License-Identifier:` lines anywhere in a file, including license
expressions such as `MIT OR Apache-2.0` and `GPL-3.0-only WITH Classpath-exception-2.0`.

**Keywords.** Names of well-known licenses appearing in license context — "Licensed
under the Apache License, Version 2.0". Cheap, and works on prose that is not a full
license text.

**Full text matching.** A four-tier cascade, described below, that identifies a file
by comparing it against the SPDX license corpus.

## The text matching tiers

Tiers run in order, and the first one to produce a match wins.

| Tier | Method | How it works |
|---|---|---|
| 0 | `hash` | SHA-256 / MD5 of the normalized text against a table of known license hashes. An exact match is reported at confidence `1.0`. |
| 1 | `dice-sorensen` | Character-bigram Dice-Sørensen similarity against the license corpus. Tolerates reformatting, differing copyright lines, and minor edits. |
| 2 | `tlsh` | Fuzzy hashing, for texts too modified for tier 1. Requires the optional `python-tlsh` package. |
| 3 | `regex` | Pattern matching for license references and headers that are not full texts. |

{: .note }
> **Install `python-tlsh`.** Without it, tier 2 does not run *and* tier 1 loses
> its borderline band, described below — so detection is meaningfully weaker.
> See [Overview]({{ site.baseurl }}/).

### What tier 1 accepts

A similarity score at or above `similarity_threshold` (default `0.97`) is
accepted outright. Between that and a floor of `0.90`, the match is only
accepted if the fuzzy tier corroborates it.

That band is where licenses like a reformatted BSD-3-Clause file live — real
matches that a strict threshold would throw away. But it is also where
near-identical licenses collide: a Sleepycat license file scores `0.906` against
BSD-3-Clause, and Sleepycat is copyleft while BSD-3-Clause is not.

So the band is only opened when something can actually corroborate. **With no
`python-tlsh` installed there is no corroborator, and the band stays shut** —
osslili reports less rather than reporting a license that the text merely
resembles.

Normalization strips copyright holder lines before comparison, so the same license
matches regardless of who holds the copyright or which years are listed.

### Why the TLSH tier verifies itself

TLSH measures overall document similarity, which makes it good at finding which
licenses a text resembles and bad at telling those licenses apart. Canonical MIT text
sits closer to the JSON license than it does to MIT itself — the JSON license is MIT
plus the "Good, not Evil" sentence, and that sentence offsets the length difference of
a package's own copyright line. BSD-3-Clause and BSD-4-Clause differ by one
advertising clause and are similarly close.

Those clauses are exactly what changes your obligations, so nearest-neighbour alone is
not a safe answer. The TLSH tier therefore proposes candidates rather than deciding:
every near neighbour within the distance threshold is collected, and a candidate is
only reported once its own license text agrees with the scanned text closely enough to
confirm it. A proposal that cannot be substantiated is dropped, and the answer is left
to a tier that can back it up.

The practical consequence is that this tier is quiet. That is intended — for
compliance work, reporting nothing is safer than reporting a license one clause away
from the real one.

## Detection methods

The `detection_method` field takes one of:

| Method | Meaning |
|---|---|
| `hash` | Exact match of the full license text |
| `dice-sorensen` | Text similarity match |
| `tlsh` | Fuzzy hash match, corroborated against the license text |
| `regex` | Pattern match on a license reference or header |
| `tag` | An `SPDX-License-Identifier` tag or a package metadata license field |
| `keyword` | A license named in license context in prose |
| `filename` | Inferred from the file's name |

## Categories

`category` says what role the finding plays, which usually matters more than the
confidence number.

| Category | Meaning |
|---|---|
| `declared` | The project states this is its license — a license file, package metadata, or an SPDX tag |
| `detected` | Found in file content that is not a formal declaration |
| `referenced` | A passing mention of a license, not a grant |
| `third-party` | From a bundled third-party notice file — a dependency's license, not the project's |

The `third-party` distinction matters when you are determining what a project is
licensed under. A vendored `THIRD_PARTY_NOTICES` file is full of other projects'
licenses, and counting those as the project's own turns a permissive project into an
apparently copyleft one. `DetectionResult.get_own_licenses()` and
`get_third_party_licenses()` separate the two, and `get_primary_license()` never
returns a third-party license.

## Confidence

`confidence` runs from 0.0 to 1.0 and means "how well does the evidence support this
identifier", not "how likely is this the project's license".

| Range | Typical source |
|---|---|
| `1.0` | Exact hash match, SPDX tag, or declared metadata |
| `0.95`–`1.0` | Strong text similarity |
| `0.85`–`0.95` | Keyword match in clear license context |
| below `0.85` | Weaker pattern matches |

Compare confidence within a method, not across methods. A keyword hit at 0.9 and a
text match at 0.9 are not equivalent claims — the keyword saw a license name, the text
match saw the license.

## What osslili will not do

**It does not guess a version.** An unversioned mention of "the General Public
License" names a family, not a license: `GPL-2.0-only` and `GPL-3.0-only` carry
incompatible obligations, so resolving it to either one would invent an obligation
that the text does not state. No identifier is reported.

**It does not read discussion as a grant.** Licenses named in compatibility notes,
project history, exclusions, or linking exceptions are not treated as the license of
the file. The Python license stack, for instance, discusses the GPL at length while
being distributed under the PSF license; the GPL mentions there are commentary.

**It does not emit identifiers outside the SPDX list.** Every reported identifier is
validated against the SPDX license list — or is an SPDX expression, an SPDX exception,
`NOASSERTION`, or a `LicenseRef-` identifier. Deprecated GNU-family identifiers are
normalized to their modern replacements, so `GPL-2.0` is reported as `GPL-2.0-only`
and `GPL-2.0+` as `GPL-2.0-or-later`.

## When nothing is found

If a scan reports no licenses, in order of likelihood:

1. The license is in a source file and you did not use `--deep`.
2. The license text is modified enough that no tier can confirm it. Run with `--debug`
   to see rejected candidates and why.
3. `--fast` skipped the file — it caps file size and skips extensionless files.
4. The project genuinely declares nothing.
