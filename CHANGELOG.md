# Changelog

All notable changes to osslili will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.9.2] - 2026-08-31

A licence a package plainly declared could be reported as nothing at all. One
fix, and the reason it is worth a release on its own is that the failure was
silence rather than a wrong answer, which is harder to notice.

### Fixed
- **A licence declared as `Affero GPLv3`, `Lesser GPLv3` or `LGPLv2.1` was reported as nothing at all** (Issue #125). The step that reads a version out of a vague name wrote it back exactly as it found it, and a licence is written "v3" as often as "3.0". Only the second is part of an identifier, so the step answered `AGPL-v3`, which names nothing, and returned, so the later steps that could have reached a real one never ran

  | declared | before | now |
  |---|---|---|
  | `GPLv3` | `GPL-3.0-only` | `GPL-3.0-only` |
  | `Affero GPLv3` | *nothing* | `AGPL-3.0-only` |
  | `Lesser GPLv3` | *nothing* | `LGPL-3.0-only` |
  | `LGPLv2.1` | *nothing* | `LGPL-2.1-only` |

  - The version is spelled the way an identifier spells it, and the answer is checked against the SPDX list, so a guess that names nothing falls through instead of stopping the search
  - The spellings are tried longest first. `gplv2.1` contains `v2` as well as `2.1`, and answering on the first found made LGPL-2.0 out of LGPL-2.1, which is a different licence rather than a different spelling of one
  - The same silence reached lines carrying the grant in words. `GPLv3 or later` answered `GPL-v3+` and a package declaring it reported nothing; it answers `GPL-3.0+` now, and the scan reports `GPL-3.0-or-later`. So do `Affero GPLv3 or later` and `Lesser GPLv3 or later`
  - Two licences the parser used to drop are kept. `MIT or GPLv2 or later` reported MIT alone, because saying nothing about the GPL was better than reporting it without the grant it could not carry; the grant goes on it now. `MIT AND GPLv2 or later` reported `GPL-2.0-only`, the opposite permission, and reports `GPL-2.0-or-later`
  - **The letters after `CC BY` are part of the licence.** Every Creative Commons attribution variant collapsed to `CC-BY`, so `CC BY-SA 3.0` answered `CC-BY-v3`, which names nothing and was dropped: the licence went missing. Checking the answer would have turned that into a confident `CC-BY-3.0`, which is worse, because ShareAlike is copyleft and NonCommercial and NoDerivatives are obligations the plain licence does not carry. The variant is kept, so it reports `CC-BY-SA-3.0`
  - Which licence such a line names is still settled by the expression reader, whose answers #120 and #127 spent a great deal on. `Apache 2.0 or above` reports `Apache-2.0` exactly as before

### Behaviour changes

| a package declaring | 1.9.1 | 1.9.2 |
|---|---|---|
| `Affero GPLv3` | *nothing* | `AGPL-3.0-only` |
| `Lesser GPLv3` | *nothing* | `LGPL-3.0-only` |
| `LGPLv2.1` | *nothing* | `LGPL-2.1-only` |
| `GPLv3 or later` | *nothing* | `GPL-3.0-or-later` |
| `CC BY-SA 3.0` | *nothing* | `CC-BY-SA-3.0` |
| `GPLv3`, `MIT`, `Apache 2.0` | unchanged | unchanged |

Two licences the expression reader used to drop are also kept. `MIT or GPLv2 or
later` reported MIT alone, and `MIT AND GPLv2 or later` reported `GPL-2.0-only`,
which is the opposite permission.

## [1.9.1] - 2026-08-31

One correction, and the reason it is worth a release on its own: for a licence
whose text several licences share, the scanner named one of them and called it
certain. For the Mozilla Public License that pointed the wrong way.

### Fixed
- **An exact match on a text several licences share no longer claims to identify one of them** (Issue #142). Sixteen texts on the SPDX list belong to more than one identifier, and eight of those groups have members that oblige different things. The scanner answered with whichever it found first, at confidence 1.0 and category `declared`

  | the text | belongs to |
  |---|---|
  | MPL-2.0 | `MPL-2.0`, `MPL-2.0-no-copyleft-exception` |
  | OFL-1.1 | `OFL-1.1`, `OFL-1.1-RFN`, `OFL-1.1-no-RFN` |
  | GFDL-1.3 | `GFDL-1.3-only`, its invariants and no-invariants variants |
  | CAL-1.0 | `CAL-1.0`, `CAL-1.0-Combined-Work-Exception` |

  - For MPL that was the dangerous direction. A project that marks Exhibit B carries `MPL-2.0-no-copyleft-exception`, whose code cannot be relicensed under the GPL, and reporting plain `MPL-2.0` at full confidence told a consumer the combination was allowed
  - Such a match is reported with match type `exact_hash_shared_text`, a confidence of 0.9 rather than 1.0, and a new `ambiguous_with` field naming the other members. The licence is still reported: the text is certainly one of a known few, and dropping the record would lose a licence the file plainly carries
  - Two spellings of one licence are not this. `AGPL-3.0-only` and `AGPL-3.0-or-later` share a text and oblige the same things, so they are not reported as an ambiguity
  - Working the answer out from the notice that does distinguish them, Exhibit B and its equivalents, is #144

### Behaviour changes

| a licence file holding | 1.9.0 | 1.9.1 |
|---|---|---|
| the MPL-2.0 text | `MPL-2.0` at 1.0 | `MPL-2.0` at 0.9, `ambiguous_with: [MPL-2.0-no-copyleft-exception]` |
| the OFL-1.1 text | `OFL-1.1` at 1.0 | `OFL-1.1` at 0.9, naming both reserved-font-name variants |
| the GFDL-1.3 text | `GFDL-1.3-only` at 1.0 | 0.9, naming the invariants variants |
| the MIT, BSD, ISC, Sleepycat texts | 1.0 | unchanged |

A consumer reading `confidence` sees the uncertainty; one reading `match_type`
sees `exact_hash_shared_text`; one that wants the alternatives has them by name.
Nothing is dropped and no record that was unambiguous changes shape.

## [1.9.0] - 2026-08-30

Every licence on the SPDX list now ships its text, and the tiers that read
words rather than texts were narrowed to match. Two entries change what a scan
reports; see Behaviour changes.

### Fixed
- **A licence word in a licence file whose text was already recognised is a word, not a grant.** The OFL says "Permission is hereby granted, free of charge", which is MIT's phrasing, so scanning an OFL font licence reported MIT beside it, and the AGPL names the GPL and reported that. Nothing in a file whose text matched outright is still an open question. Measured over all 737 bundled licence texts, the number reporting a licence they merely mention falls from 93 to 23
  - The 23 that remain are SPDX variant families whose texts are byte-identical: `GFDL-1.1-invariants-only` against `GFDL-1.1-only`, `OFL-1.1-RFN` against `OFL-1.1`, `MPL-2.0-no-copyleft-exception` against `MPL-2.0`. As with `-only` and `-or-later`, what separates them is stated where the licence is applied rather than in the licence, so nothing reading text can tell them apart
- **A licence word in a document is a mention until something agrees** (Issue #138). The keyword tier matches single words and short names, so ordinary prose reported licences the package never granted

  | package | reported | from | actually |
  |---|---|---|---|
  | `flask` | `JSON` | a changelog sentence about JSON encoding | BSD-3-Clause |
  | `urllib3` | `JSON` | `CHANGES.rst` | MIT |
  | `charset-normalizer` | `0BSD` | `README.md` | MIT |

  - An uncorroborated keyword match in a document is dropped once the scan has found a licence some other way. It is kept in a licence file, where a bare licence word is very often the grant itself and no other tier reads it, and kept in a package with nothing else to go on, where it is the only answer there is
  - Corroboration counts only licences that are actually reported. A README saying "licensed under GPL2" yields a tag reading `GPL2`, which is not an SPDX identifier and is dropped, and counting it took away the keyword match that was the real answer
- **A file that states its licence no longer gets a *near neighbour* reported beside it.** With every licence text bundled, a `LICENSE` stating `Python-2.0` also scored 0.961 against `Python-2.0.1`, the same licence one revision apart, and both were reported. Only a licence the stated one is nearly indistinguishable from is dropped, measured by comparing the two bundled texts. A file may state one licence and carry the text of a second, `MIT` beside the Apache-2.0 text, and that second one is a licence the file really does offer rather than a near miss at the first. Two spellings of one licence that differ only in the grant, `GPL-2.0-only` and `GPL-2.0-or-later`, are never near misses at each other: their texts are the same text and the grant is stated where the licence is applied, so nothing comparing text can tell them apart and deciding by accident is what #118 cost. This is what #108 settled for normalisation, applied to the tiers

  Measured over 13 real packages from PyPI: **0 licences lost, false positives from 3 to 0**.

### Changed
- **The text of every licence on the SPDX list is bundled** (Issue #126). 46 of 703 entries carried their text, so the tiers that compare text covered 6.5% of the list and the regex tier answered for the rest. It did not answer "unknown"; it named a licence:

  | full licence text scanned | before | now |
  |---|---|---|
  | `Sleepycat` | `BSD-3-Clause` @ 0.6 | `Sleepycat` @ 1.0 |
  | `BSD-4-Clause` | `BSD-3-Clause` @ 0.6 | `BSD-4-Clause` @ 1.0 |
  | `OFL-1.1` | `MIT` | `OFL-1.1` @ 1.0 |

  Sleepycat is copyleft and BSD-3-Clause is permissive. BSD-4-Clause is BSD-3-Clause plus the advertising clause, which is the whole difference between them.

  - The list is now 737 licences, all with text. 34 entries were added by SPDX since the last bundle and none were removed, so nothing previously reportable stops being reportable
  - Exact hashes go from 46 to 737, and the TLSH hashes from 699 to 737, so all three text tiers cover the whole list
  - `standardLicenseTemplate` is no longer stored. Nothing read it and it is roughly the size of the text again. The wheel goes from 0.40 MB to 1.20 MB
  - Scanning is faster per file, not slower. The bigrams of each licence were rebuilt for every file read; they are built once now, and a licence whose length is too far from the scanned text is skipped without comparing a bigram, which is sound because Dice cannot exceed `2*min/(a+b)`. A small package went from 0.13s to 0.02s once the licence data is warm, against a one-off 0.5s to build it
  - **TLSH no longer asserts a licence its own text contradicts.** The tier fell back to an uncorroborated match when corroboration failed, which was right when most entries shipped no text and most proposals could not be checked at all. Now that every entry carries its text, a failed corroboration means the text was read and disagreed, and asserting over that would be the fallback overruling the evidence. The fallback is kept only for a candidate with no text to check
  - **The TLSH near-neighbour cutoff was too tight to see its own answer.** Measured over 675 licences, taking the canonical text with a project's copyright line on top: at distance 30 the true licence was among the candidates only 76% of the time. Feeding the tier a BSD-3-Clause file shows why: it sits at distance 35 from BSD-3-Clause and 29 from BSD-4-Clause, so the only candidate inside the old cutoff was the neighbour a clause away. (Separately, in the table below, a *BSD-4-Clause* file used to report BSD-3-Clause; that one is the regex tier answering for a licence whose text was not bundled, and is what bundling fixes.) The cutoff is 60 now, covering 91%. Widening cannot cost precision, because corroboration keeps the candidate whose real text scores highest; it costs candidates to compare, and the median licence file has 2 of 737

### Behaviour changes

| what | 1.8.0 | 1.9.0 |
|---|---|---|
| a `Sleepycat` licence file | `BSD-3-Clause` at 0.6 | `Sleepycat` at 1.0 |
| a `BSD-4-Clause` licence file | `BSD-3-Clause` at 0.6 | `BSD-4-Clause` at 1.0 |
| an `OFL-1.1` font licence | `OFL-1.1` and `MIT` | `OFL-1.1` |
| an `AGPL-3.0-only` licence file | `AGPL-3.0-only` and `GPL-3.0-only` | `AGPL-3.0-only` |
| a changelog sentence about JSON | the `JSON` licence | nothing |
| the wheel | 0.40 MB | 1.20 MB |

Checked against 1.8.0 over 13 real packages from PyPI: none lose a licence, and
three stop reporting one they never granted.

Scanning is faster per file. The bigrams of each licence text are built once
rather than for every file read, and a licence whose length is too far from the
scanned text is skipped without comparing a bigram. Building them costs about
half a second the first time a scan reaches the similarity tier.

### Known limits

Twenty-three of the 737 licences share their text, byte for byte, with another:
the GFDL invariants variants, the OFL reserved-font-name variants, the MPL
copyleft exception. What separates them is stated where the licence is applied
rather than in the licence body, so nothing that reads text can tell them apart,
and the report does not yet say when the answer was ambiguous. Issue #142.

## [1.8.0] - 2026-08-30

Accuracy work across the detectors, plus per-category scan targets. Several
entries change what a scan reports; those are listed under Behaviour changes.

### Added

**Fine-grained scan targets** (Issue #79, PR #128). Each category of file a
scan reads can be turned on or off on its own: `--license-files`,
`--notice-files`, `--package-metadata`, `--documentation`, `--source-files`,
and `--text-similarity` for the full licence text comparison. Scanning modes
are presets over these.

Asked for by scanners running inside a pipeline that already reads declared
licences from package metadata, such as ORT, which repeated that step for
nothing and could not turn it off.

Categories are decided in one place, so the licence detector and the copyright
extractor agree. They did not, and a scan told to read only licence files
still reported the copyright out of a README.

### Fixed

**An SPDX expression is read by its grammar** (PR #127). The hand-written
reader took the string apart with patterns, so each shape had to be handled
separately and the ones that were not reported a licence the file does not
grant, or dropped one it does.

- `AGPL-3.0+` was reported as `GPL-3.0-only`, a different licence and the
  opposite grant (Issue #118)
- `MIT AND BSD-compatible` reported BSD-3-Clause, a clause the author never
  wrote down (Issue #119)
- `Dual license: GPL-2.0 or MIT` lost the MIT
- `MIT or GPL-2.0 or later` reported the opposite permission

**A header line carries an expression, not its first term** (Issue #113, PR
#120). The pattern stopped at the first space, so
`SPDX-License-Identifier: MIT OR Apache-2.0` reported MIT alone, and
`GPL-2.0-only WITH Classpath-exception-2.0` dropped the exception. Both at
confidence 1.0.

**A licence named in a sentence is a reference, not a declaration** (Issue
#109, PR #117). "the bundled minifier is licensed under the Apache License"
was reported exactly like an SPDX tag: confidence 1.0, category `declared`. A
consumer trusting declarations read an MIT package as Apache-2.0 because its
README credited something. Prose is `referenced` now.

**An identifier a file states is the identifier reported back** (Issue #108,
PR #114). A file saying `SPDX-License-Identifier: BSD-2-Clause` was reported
as BSD-3-Clause at confidence 1.0. `LGPL-2.1-or-later` came back as
`LGPL-2.1-only`. Normalisation turns vague input into an identifier; an exact
identifier is not vague input.

**A document scored differently depending on whether it or its directory was
scanned** (Issue #111). Which window was measured followed from how the scan
was started rather than from what the file is.

| a README carrying the whole MIT text | before | now |
|---|---|---|
| scanning the file | `text_similarity` 0.995 | `text_similarity` 0.995 |
| scanning the directory | `documentation` 0.95 and 0.6 | `text_similarity` 0.995 |

A licence file and a document are read whole now. A source file keeps the
window. A file named on the command line is read whole whatever it is.

The text tiers only run on a document that mentions a licence. Reading every
document whole cost 200 ordinary pages 6.0s to 17.8s for no evidence either
way.

This is what refusing the `documentation` match type used to cost a consumer:
a package whose only licence statement is the text in its README read as
unlicensed. It now reports through the similarity tier.

**Any filename containing a licence word was treated as a licence file**
(Issue #116). The test was a substring match, so `bundle.js` held the
project's licence, and so did every page written about licensing.

| name | before | now |
|---|---|---|
| `bundle.js` | licence file | source file |
| `docs/license-policy.md` | licence file | documentation |
| `license_manager.py` | licence file | source file |
| `LICENSE-MIT`, `COPYING.LESSER` | licence file | licence file |

A licence filename is recognised by shape now: the stem is a licence word on
its own, or a licence word joined to the licence being named. Every part has
to belong and at least one has to name a licence. A part matches whole, so
`gplus` is not `gpl`.

The same substring test existed in two places, the detector and the
scan-target reader, which could drift. There is one rule now.

Measured over 62 filenames: 34 of 34 real licence files still recognised,
false positives from 17 to 0.

**Evidence for an archive named a temporary directory** (Issue #121).
Extraction picks a fresh `mkdtemp` each run, so the same file was reported
under a different name every scan and the name pointed at a directory that no
longer existed. Two scans of one archive could not be diffed.

Reported now is the path inside the archive, `gin-1.10.0/auth.go`. Licence and
copyright evidence alike. A scan of a directory is unchanged.

**`extract_package_metadata()` did not modernise a deprecated identifier**
(Issue #112). A scan replaced the bare GNU-family forms; this entry point did
not, so one manifest gave two answers depending on how it was read.

| `license = ` | before | now |
|---|---|---|
| `GPL-2.0` | `GPL-2.0` | `GPL-2.0-only` |
| `GPL-2.0+` | `GPL-2.0+` | `GPL-2.0-or-later` |

Only the modernisation is shared. Dropping non-SPDX identifiers,
deduplicating and re-tagging third-party notices stay decisions a scan makes,
so metadata extraction still answers `Proprietary` where a scan reports
nothing.

**The CycloneDX SBOM named the wrong tool version and repeated a licence**
(Issue #132). The version was the literal `1.5.6` in both writers while the
package had moved to 1.7.5. It reads `__version__` now.

A `licenses` array listed one entry per detection, so a licence found by two
tiers appeared twice under one component. Identifiers are collapsed and
sorted.

**A scan of a directory answers the same way every time** (Issue #110, PR
#123). Copyright statements were merged as threads finished, so the same scan
returned the same statements arranged differently each run, and which file a
repeated statement was attributed to depended on the race.

**A scan lists its licence evidence the same way every time** (Issue #122, PR
#124). The same fault in the other half of the scanner. Four runs gave three
orderings, and five hash seeds gave five answers.

**CI tested only one of the two installations** (PR #115). Two tests cover the
tier-two band that exists only when `python-tlsh` is installed, and CI
installed without extras, so `main` had been red for a fortnight. The matrix
runs both now.

### Removed

**The `ml` extra and the `DetectionMethod.ML` value** (Issue #106).
`pip install osslili[ml]` pulled transformers, torch and scikit-learn, several
hundred MB, and changed nothing: no module imported any of them and no code
assigned the enum value. Anyone with it pinned gets pip's "does not provide
the extra" warning rather than a failed install.

### Behaviour changes

Each of these reports something different from 1.7.5. Every previous answer
was wrong, but a consumer pinned on the old output will see the change.

| what | 1.7.5 | 1.8.0 |
|---|---|---|
| `SPDX-License-Identifier: AGPL-3.0+` | `GPL-3.0-only` | `AGPL-3.0-or-later` |
| `SPDX-License-Identifier: MIT OR Apache-2.0` | `MIT` | `MIT`, `Apache-2.0` |
| `SPDX-License-Identifier: BSD-2-Clause` | `BSD-3-Clause` | `BSD-2-Clause` |
| a README crediting a dependency | `declared` at 1.0 | `referenced` |
| `bundle.js` | a licence file | a source file |
| `docs/license-policy.md` | a licence declaration | documentation |
| evidence inside an archive | a temporary path, new each run | the path inside the archive |
| `extract_package_metadata()` on `GPL-2.0` | `GPL-2.0` | `GPL-2.0-only` |
| a CycloneDX SBOM's tool version | `1.5.6` | the running version |
| `pip install osslili[ml]` | installed ~1 GB, changed nothing | warns the extra is gone |

Checked against 1.7.5 over 13 real packages from PyPI: twelve report
identically, one changes. `packaging` declares `Apache-2.0 OR BSD-2-Clause`
and was reported as carrying BSD-3-Clause, a licence with an
advertising-style clause it never granted. It now reports what the manifest
says.

### Packaging

The version is read from `osslili/__init__.py` rather than written twice.
`pyproject.toml` carried its own copy, so bumping one built an artifact
carrying the other.

### Documentation

The configuration page advertised the filename patterns removed with #116, so
a reader was told to expect the behaviour that issue was about. Replaced with
the shape rule and a table of what counts.

The tier table on the detection page (PR #105) and the `python-tlsh` build
requirement (PR #104) corrected.

## [1.7.5] - 2026-08-11

Recommended upgrade for anyone on 1.7.4 that does **not** have `python-tlsh`
installed — which is the default, since it builds from C and needs a compiler.

### Fixed
- **Borderline similarity matches were accepted without any corroboration when `python-tlsh` is absent.** 1.7.4 opened the band between the similarity floor (`0.90`) and `similarity_threshold` to matches that TLSH corroborates. But `confirm_license_match()` answers `True` when it cannot check, so with no TLSH installed the corroboration requirement silently became a rubber stamp
  - A Sleepycat license file was reported as `BSD-3-Clause` at **0.91** — the texts really are that similar, and the clauses that differ are what makes Sleepycat copyleft. In 1.7.3 the same file produced a low-confidence `0.60` pattern guess, so 1.7.4 made a wrong answer look credible
  - The band is now opened only when a corroborator is actually available. Installs with `python-tlsh` keep everything 1.7.4 added; installs without it get 1.7.3's stricter behaviour
  - New `TLSHDetector.can_confirm` distinguishes "confirmed" from "could not check"

### Documentation
- **`python-tlsh` is now documented as recommended**, in the README, the site overview, and the detection page, with what is actually lost without it — tier 2 does not run, and tier 1's borderline band stays shut. Includes the `gcc python3-dev` prerequisite for slim container images

## [1.7.4] - 2026-08-11

### Fixed
- **Corroborated similarity matches were discarded** (PR #101). The Dice-Sørensen tier accepts a strong score outright and a weaker one only once TLSH corroborates it, with a floor at 0.90. The cascade then re-checked the result against `similarity_threshold` (default 0.97), above the tier's own floor, so every corroborated match in between was computed and then thrown away
  - Real cost: `protobuf` and `multiprocess` both ship BSD-3-Clause license files scoring 0.957 and 0.932, and both were reported as carrying no license at all. Both licenses are in the bundled set, so this was lost recall on the most common licenses
  - `similarity_threshold` now applies where it means something: at or above it a score stands on its own, below it down to the floor a match must be corroborated. Raising the setting still makes matching stricter rather than deleting results

### Notes
- Across 69 real package license files, four change: `protobuf` and `multiprocess` gain the BSD-3-Clause they always carried, `dill` reports the same license at the same score through the similarity tier rather than the fuzzy one, and `numpy`'s bundled aggregate license file moves from `LGPL-3.0-only` at 0.60 to `GPL-3.0-only` at 0.948 — the GPL-3.0 text is 696 of its 971 lines, shipped for the GCC Runtime Library Exception. Scanning numpy's directory still reports `BSD-3-Clause` as its own license

## [1.7.3] - 2026-08-11

Recommended upgrade for anyone on 1.7.1 or 1.7.2. Those releases stopped
detecting licenses they previously found, including canonical GPL source
headers.

### Fixed
- **Licenses that 1.7.1 stopped detecting** (Issue #98). The matcher accuracy work in 1.7.1 fixed a class of false positives and introduced a larger class of false negatives. Verified against real license texts, 1.7.0 → 1.7.2 → this release:

  | Input | 1.7.0 | 1.7.1 / 1.7.2 | 1.7.3 |
  |---|---|---|---|
  | Canonical FSF GPL-2 header | `GPL-2.0-only` | *nothing* | `GPL-2.0-or-later` |
  | Canonical FSF GPL-3 header | `GPL-3.0-only` | *nothing* | `GPL-3.0-or-later` |
  | GPL header + linking exception | `GPL-3.0-only` | *nothing* | `GPL-3.0-or-later` |
  | `"licensed under GPL2"` | `GPL-2.0-only` | *nothing* | `GPL-2.0-only` |
  | zlib grant containing "compatibility" | `Zlib` | *nothing* | `Zlib` |
  | Sleepycat license file (copyleft) | `Sleepycat` | `BSD-3-Clause` @ 1.00 | `Sleepycat` |
  | CECILL-2.1 license file (copyleft) | `CECILL-2.1` | `GPL-3.0-only` @ 1.00 | `CECILL-2.1` |

  - **GNU version parsing** now reads the phrasing the FSF recommends — "either version 2 of the License, or (at your option) any later version" — where the version attaches to *the License* rather than to *GPL*. Also covers the separator-less `GPL2` form, and a trailing "any later version" now yields an `-or-later` identifier, which is what the grant says
  - **Linking exceptions no longer suppress the grant they are attached to.** The guard still prevents the carved-out library's license being asserted, but never applies to GNU-family matches — a file carrying a linking exception is by definition licensed under the copyleft license granting it. Paragraph detection now treats a line of bare comment markers as a break, since `\n\n` never occurs inside a `/* ... */` block
  - **Compatibility detection narrowed** to require a license name alongside the word, so ordinary English "compatibility" in a grant sentence no longer suppresses it
  - **The fuzzy tier may assert an unambiguous match again.** Requiring corroboration silenced it for the majority of SPDX entries that ship no license text, and the regex tier filled the vacuum at full confidence. It may now also assert a candidate that no other license comes near — its inability to separate near neighbours does not apply when there are none. The margin is measured: across the known near-neighbour confusions the wrong answer never leads by more than 13, and where the tier is right but uncorroborated the correct answer leads by 20 or more
  - **A regex match reached after every text tier declined is capped below the keyword tier.** It describes an unrecognized document rather than identifying one, and scoring it at 1.0 is what reported copyleft as permissive
- **A Lesser or Affero mention is no longer claimed by the generic GPL path**, which reported LGPL-2.1 files as `GPL-2.0-only`. Predates 1.7.1
- **PEP 639 `license = {file = "..."}` resolved to nothing** (Issue #96). The referenced file was passed to a method that does not exist, and the `AttributeError` was swallowed and logged as a failed file read. Full directory scans masked it — the referenced file is scanned independently — so it surfaced only where metadata is read without the license file, notably `extract_package_metadata()` and scans pointed at a manifest
- **PEP 639 references are now contained to the project directory.** A manifest path is untrusted input; `license = {file = "../../secrets.txt"}` read a file outside the scanned tree and reported its license as the project's own, and an absolute path discarded the base directory entirely. Symlinks out of the tree fail the same check; ordinary nested paths still resolve

### Notes
- Across 69 real package license files, no license identity changes relative to 1.7.2; thirteen regex detections drop from 1.0 to 0.6, which is the intended correction
- Detection of licenses whose text is not bundled still depends on the fuzzy tier, and the network fallback for missing texts is unreachable because bundled entries carry no `detailsUrl`. Widening bundled text coverage is tracked separately

## [1.7.2] - 2026-08-11

### Added
- **Documentation site** at [semclone.github.io/osslili](https://semclone.github.io/osslili/), built from `docs/` and published through GitHub Pages
  - New **Detection** page covering the tier cascade, what each detection method and category means, how to read confidence, and what osslili deliberately declines to report
  - New **Configuration** page documenting the full schema, split out of the API reference, with every field and its default

### Changed
- **`Documentation` project URL** now points at the published site instead of the GitHub-rendered README, so the PyPI project page links to the real documentation
- **Documentation rewritten against the current release.** The previous pages had drifted since v1.5.6: six command line flags were undocumented (`--fast`, `--detail`/`--evidence-detail`, `--max-file-size`, `--skip-content-detection`, `--skip-extensionless`, `--skip-smart-read`), a `--cache-dir` flag was documented that has never existed, seven `Config` fields were missing, the `keyword` detection method was absent, and the third-party license category added in 1.7.0 appeared nowhere
- **README** rewritten: corrected the stated Python requirement from 3.8 to 3.9, removed a dead link to a benchmark page deleted in 1.6.x, and replaced the outdated three-tier description with the actual four-tier cascade

### Notes
- `--max-extraction-depth` defaults to `10` and always sets the value, while a bare `Config` defaults to `3`. Both are documented where they apply; the inconsistency itself is unchanged in this release.

## [1.7.1] - 2026-08-11

### Fixed
- **TLSH matcher reported near-identical licenses as declared** (Issue #90): the matcher returned its nearest fuzzy-hash neighbour as the verdict at a confidence floored at 0.97, which outranked the matchers that had the file right. TLSH measures bulk document similarity, so licenses that differ by a single clause are indistinguishable to it — canonical MIT text sits closer to the JSON license (distance 17) than to MIT itself (29), and those clauses are exactly what changes the obligations
  - TLSH is now a candidate generator: every near neighbour within the distance threshold is collected, and a candidate is only asserted once its actual license text corroborates the scanned text (Dice-Sørensen ≥ 0.9)
  - A proposal that cannot be substantiated — most bundled SPDX entries ship no license text — is dropped rather than reported, leaving the answer to the tiers that can back it up
  - Reported confidence is now the measured text agreement instead of a fixed floor, so a fuzzy match no longer outranks an exact or keyword identification of the same file
  - Observed effect: MIT no longer reported as `JSON`, BSD-3-Clause no longer reported as `BSD-4-Clause` or `BSD-3-Clause-HP`
- **Keyword matcher asserted licenses from prose that only discusses them** (Issue #91): the PSF license stack explains at length how Python relates to the GPL while being distributed under Python-2.0, and a keyword hit on that commentary asserted `GPL-2.0-or-later` — copyleft claimed over a permissive package
  - Mentions framed as compatibility notes, license history, exclusions, or linking exceptions no longer count as a grant
  - All occurrences of a keyword are now examined rather than only the first, so rejecting a mention means "keep looking" instead of giving up on the file
  - An unversioned "GPL" / "General Public License" mention yields no identifier: it names a family, and GPL-2.0-only and GPL-3.0-only are mutually incompatible, so resolving it to either invents an obligation. The previous fallback guessed `GPL-2.0-or-later`, and its version sniffer accepted any digit in the surrounding window — a copyright year read as a version
  - Keyword variations now match on word boundaries; `MIT` was matching inside "per**mit**ted" and "li**mit**ation", which run throughout the LGPL and MPL texts

### Technical Details
- Added `TLSHDetector._find_near_neighbours()` and `TLSHDetector._corroborate()`; the tier-2 gate in `_detect_license_from_text` no longer re-checks `similarity_threshold`, which was a no-op against the old confidence floor
- Extracted `create_bigrams()` / `dice_coefficient()` into `osslili/utils/text_similarity.py`, shared by the Dice-Sørensen and TLSH tiers
- Added `tests/test_matcher_accuracy.py` covering both issues

## [1.7.0] - 2026-07-24

### Added
- **Third-party license category** (Issue #78): bundled third-party notice/license files (`THIRD_PARTY_NOTICES`, `3rdpartylicenses`, etc.) are now categorized as `third-party` rather than counted as the project's own license, so consumers determining a project's license in isolation can filter them out while artifact scans still surface them
  - New `LicenseCategory.THIRD_PARTY` and `DetectionResult.get_own_licenses()` / `get_third_party_licenses()` helpers
  - A third-party notice file is identified by a third-party marker combined with a notice/license token, avoiding misclassification of ordinary source files (e.g. `third_party_helpers.py`)
  - Evidence output gains a `third_party_licenses` summary bucket, preserved across all detail levels

### Changed
- **`get_primary_license()`** never selects a bundled third-party license; it returns `None` when only third-party notices were detected (they remain available via `get_third_party_licenses()`)
- **KissBOM**: `license` / `all_licenses` reflect the project's own licenses; third-party licenses are reported in a separate `third_party_licenses` field
- **CycloneDX**: component `licenses` use the project's own licenses; third-party licenses are emitted as `properties` (`osslili:third-party-license`), with `<copyright>` ordered before `<properties>` per the 1.4 XML schema

### Removed
- Redundant `THIRD_PARTY_NOTICES*` entry from `license_filename_patterns` (Issue #80); it was already covered by the existing `*THIRD_PARTY*` pattern and filename matching is set membership, not ordered priority

### CI
- Removed a redundant, broken publish workflow (#85)

## [1.6.5] - 2026-07-24

### Fixed
- **SPDX Compliance**: Emit modern SPDX ids for deprecated GNU-family licenses (Issue #82)
  - The tag and text detectors surfaced deprecated bare ids (`GPL-2.0`, `GPL-3.0`, `LGPL-3.0`, `AGPL-3.0`), which SPDX replaced with the explicit `-only` / `-or-later` disjunction
  - Detected ids are now normalized to their modern replacement at the emission boundary — `GPL-2.0` → `GPL-2.0-only`, and the deprecated `+` form `GPL-2.0+` → `GPL-2.0-or-later`
  - Normalization only applies when the computed replacement is itself a valid SPDX id, so unexpected inputs can never produce a bogus id; modern and non-GNU ids pass through unchanged

### Technical Details
- Added `_to_modern_spdx_id()` applied before the SPDX-list guard and dedup in both the parallel and sequential collection paths
- Added `TestDeprecatedGnuIdNormalization` regression coverage (unit mapping + end-to-end detection)

## [1.6.4] - 2026-07-21

### Fixed
- **License Detection**: Recognized canonical ISC license text (Issue #76)
  - The text normalizer stripped copyright lines after collapsing the text to a single line, so the copyright regex ran to the end of the string and deleted the license wording
  - Canonical ISC files that open with a copyright line normalized to empty text and never matched
  - ISC was also filtered out because it was listed among generic single words
- **SPDX Compliance**: Stopped emitting identifiers that are not valid SPDX ids (Issue #76)
  - Detected ids are now validated against the SPDX license list before being emitted
  - Invalid ids like `MIT-or-later` no longer reach SBOM or notice output
  - Expressions, `WITH` exceptions, `LicenseRef-` ids and `NOASSERTION` still pass through

### Technical Details
- Copyright lines are now removed per line before whitespace collapse in `SPDXLicenseData._normalize_text`
- Added `_is_emittable_license_id()` guard at the detection output stage
- Regenerated `exact_hashes.json` since it was built with the old normalizer
- Added regression tests for canonical ISC, MIT and BSD-2 texts and the invalid id guard

## [1.6.3] - 2026-01-31

### Fixed
- **SPDX Compliance**: Fixed invalid SPDX license suffix generation (Issue #64)
  - Prevented `-only` and `-or-later` suffixes from being added to non-GNU licenses
  - Invalid IDs like `MIT-only`, `Apache-2.0-only`, `BSD-3-Clause-only` are no longer generated
  - Suffixes now only applied to GNU family licenses: GPL, LGPL, AGPL, GFDL (per SPDX spec)
  - Improves compatibility with SBOM validators and compliance tools
- **License Detection**: Reduced false negatives for BlueOak licenses (Issue #63)
  - Added `blueoak-` to valid license ID patterns
  - `BlueOak-1.0.0` and other BlueOak licenses now correctly detected

### Technical Details
- Added whitelist validation in `handle_version_suffix()` function
- Only GNU licenses (GPL-*/LGPL-*/AGPL-*/GFDL-*) receive version suffixes
- All other licenses return base SPDX ID without modification
- Maintains backward compatibility for existing GNU license detection

## [1.6.1] - 2025-11-22

### Fixed
- **Copyright Extraction**: Fixed copyright detection when holder name is followed by email address in angle brackets (Issue #54)
  - Regex patterns now properly stop before `<` character
  - Correctly extracts names from formats like: `Copyright (c) 2003 Michael Niedermayer <michaelni@gmx.at>`
  - Affects all three copyright patterns: `Copyright`, `©`, and `(C)` formats
  - Impacts thousands of files in major projects (FFmpeg, Linux kernel, etc.)

### Added
- **Test Coverage**: Added 11 comprehensive test cases for copyright extraction with email addresses
  - Tests all copyright format variants with emails
  - Includes FFmpeg-style header examples
  - Validates email address cleanup in holder names

## [1.6.0] - 2025-11-14

### Added
- **Deep Scan Mode**: New `--deep` flag for comprehensive source code scanning
  - Scans all source files (.py, .js, .java, .c, .go, etc.) for embedded licenses
  - Ideal for legal compliance audits and finding license headers in code
  - Complements the fast default mode

### Changed
- **Default Scanning Behavior** (BREAKING CHANGE - but faster!):
  - Default mode now scans LICENSE files + package metadata + documentation
  - Provides 40x speedup over comprehensive scanning while capturing all declared licenses
  - New default covers 12+ package ecosystems and 40+ metadata files
  - Use `--deep` flag for old comprehensive behavior

- **Package Metadata Support** (Massive Expansion):
  - **NEW**: Go support (go.mod, go.sum)
  - **NEW**: Swift/CocoaPods support (Podfile, *.podspec)
  - **NEW**: Dart/Flutter support (pubspec.yaml)
  - **NEW**: Elixir support (mix.exs, mix.lock)
  - **NEW**: Scala support (build.sbt)
  - **Enhanced**: JavaScript (added yarn.lock, pnpm-lock.yaml)
  - **Enhanced**: Python (added Pipfile, requirements.txt)
  - **Enhanced**: .NET (added .csproj, .fsproj, .vbproj)
  - **Enhanced**: Rust (added Cargo.lock)
  - **Enhanced**: PHP (added composer.lock)
  - Total: 40+ metadata files across 12+ ecosystems (+200% increase)

- **Documentation File Support**:
  - Now scans all .txt, .md, .rst, .text, .markdown, .adoc, .asciidoc files
  - Captures README, CHANGELOG, CONTRIBUTING, AUTHORS, and other docs

### Performance
- **Benchmark Results** (ffmpeg-6.0, 4,139 files, 4 threads):
  - `--license-files-only` (strict): 7s, 8 files, 14 licenses
  - **Default mode**: **8.5s, 31 files, 16 licenses** ⚡ RECOMMENDED
  - `--deep` mode: 5m 37s, 4,800+ files, comprehensive
  - **40x speedup** in default mode vs deep scan!

### Fixed
- **Code Optimization**: Eliminated double-scanning in license file detection
- **Performance**: Changed from O(n) list lookups to O(1) set operations
- **Efficiency**: Pre-computed metadata filename sets outside loops

### Documentation
- **README.md**: Added comprehensive "Scanning Modes" section with examples
- **USAGE.md**: Added detailed scanning modes documentation
  - Performance comparison table
  - Use case recommendations for each mode
  - Package ecosystem coverage details
- **CLI Help**: Updated to explain new default behavior

### Migration Guide
- **No action needed**: Default mode is faster and better
- **For old behavior**: Use `--deep` flag for comprehensive source code scanning
- **Backwards compatible**: All existing flags still work

## [1.5.9] - 2025-11-14

### Added
- **Performance Optimization Flags**: New configurable flags for faster scanning (Issue #49)
  - `--skip-content-detection`: Skip content-based file type detection, rely only on extensions
  - `--license-files-only`: Only scan LICENSE files, skip source code (17x speedup on ffmpeg)
  - `--skip-extensionless`: Skip files without extensions unless they match known patterns
  - `--max-file-size <KB>`: Skip files larger than specified size in KB
  - `--skip-smart-read`: Read files sequentially instead of sampling start/end
  - `--fast`: Preset that combines multiple optimizations for maximum speed

### Changed
- **Config Model**: Added 6 performance optimization flags with `apply_fast_mode()` method
- **CLI**: Added 6 new command-line options for performance tuning
- **License Detector**: Enhanced file detection logic to respect performance flags
  - File size checking before processing
  - Configurable extensionless file handling
  - Optional content-based detection
  - Sequential vs smart file reading modes

### Performance
- **Benchmark Results** (ffmpeg-6.0 codebase, 4 threads):
  - Normal mode: 69s, 4,822 files, 5,566 licenses
  - `--fast`: 70s, 4,765 files, 5,549 licenses
  - `--skip-content-detection`: 71s, 4,770 files, 5,549 licenses
  - `--license-files-only`: **4s, 12 files, 14 licenses (17x speedup!)**
- **Use Case**: `--license-files-only` ideal for CI/CD pipelines needing quick declared license checks

### Fixed
- **Performance Degradation**: Addressed slowdown caused by content-based file detection (Issue #49)
  - Content detection now opens files only when necessary
  - Reduced I/O operations during file discovery phase
  - Eliminated unnecessary file reads for extensionless files

### Technical
- **Backward Compatibility**: All flags default to False, maintaining current behavior
- **Testing**: Added comprehensive test suite (10 tests) for performance flags
- **Documentation**: Updated CLI help text with performance flag descriptions

## [1.5.7] - 2025-10-30

### Changed
- **Performance Optimization**: Updated default values for better performance
  - Reduced default max recursion depth from 10 to 4 for faster directory scans
  - Set explicit thread count default to 4 in CLI (previously inherited from Config)
  - Aligned CLI and Config model defaults for consistency

### Technical
- **CLI Defaults**: Added explicit default values in CLI options for better visibility
- **Configuration**: Synchronized default values between CLI and Config model

## [1.5.6] - 2025-10-27

### Changed
- **Project Rename**: Renamed project from `semantic-copycat-oslili` to `osslili`
  - Updated package name and imports throughout codebase
  - Changed CLI command from `oslili` to `osslili`
  - Updated repository URL to `https://github.com/SemClone/osslili`
  - Renamed main Python package directory from `semantic_copycat_oslili` to `osslili`
  - Updated all documentation, configuration files, and scripts
  - Simplified project description to "Open Source License Identification Library"

### Technical
- **Package Structure**: Completely reorganized package structure for the new name
- **Import Compatibility**: All import statements updated to use new package name
- **Documentation**: Updated all references across README, docs, and examples

## [1.5.5] - 2025-10-24

### Fixed
- **False Positive Copyright Detection**: Eliminated false positive copyright holder detections
  - Fixed overly broad regex patterns that captured programming language constructs
  - Added filtering for Fortran data types (integer*1, character) being detected as copyright holders
  - Enhanced filtering for Python code fragments (is not None, or sig_pattern, is np, is not np)
  - Improved regex patterns to stop at programming keywords (is, or, and)
  - Added exact match filtering for known false positive patterns
  - Better handling of contributor phrases like "and individual contributors"

### Improved
- **Copyright Extraction Accuracy**: More precise copyright holder identification with significantly fewer false positives
- **Code Pattern Detection**: Enhanced recognition of programming language constructs to prevent them from being interpreted as copyright information

## [1.5.4] - 2025-10-24

### Fixed
- **False Positive License Detection**: Significantly reduced false positive license detections
  - Fixed overly broad keyword patterns for Python-2.0, ISC, and Perl licenses
  - Enhanced context validation to require license-specific contexts for matches
  - Added filtering for generic programming language names being detected as licenses
  - Improved ISC license pattern specificity to require actual ISC license text
  - Strengthened validation to prevent common programming terms from being flagged as licenses

### Improved
- **License Detection Accuracy**: More precise detection with fewer false positives while maintaining legitimate detection coverage
- **Context Checking**: Enhanced validation that license keywords appear in actual license contexts rather than general code comments

## [1.5.3] - 2025-10-21

### Added
- **Evidence Detail Levels**: New `--evidence-detail` CLI option with 4 levels for controlling output verbosity
  - `minimal`: Just license counts (compact 1KB output)
  - `summary`: Adds detection method breakdown (1KB output)
  - `detailed`: Includes sample evidence (72KB output) - default
  - `full`: Complete evidence (several MB output)
- **License Normalizer Utility**: New utility class for consistent license ID normalization
- **Regex Pattern Matcher**: Optimized regex matching with lookup tables for better performance

### Fixed
- **Critical Deduplication Bug**: Fixed license detection deduplication that was discarding 99% of detections
  - Changed deduplication key from (license_id, confidence) to (license_id, confidence, source_file)
  - Increases detection coverage from ~1% to 99%+ of expected files
- **File Readability Detection**: Enhanced detection for better source file coverage
  - Added more permissive encoding detection (UTF-8, Latin-1, cp1252, ISO-8859-1)
  - Improved binary file detection with magic number signatures
  - Better handling of files with mixed encodings

### Improved
- **License Detection Coverage**: Reduced false negatives while maintaining low false positive rate
  - Reduced license text indicator threshold from 3 to 1 for better coverage
  - Added validation filtering to reduce false positives
  - Enhanced match type categorization (license_file, spdx_identifier, package_metadata, etc.)
- **Performance Optimizations**: Maintained ~117 files/second processing speed
  - Memory-efficient streaming processing for large files
  - Optimized regex pattern matching with lookup tables
  - Parallel processing improvements

### Changed
- **Evidence Formatter**: Enhanced with detail level filtering and better match type descriptions
- **License Detector**: Improved categorization logic and false positive filtering

## [1.5.1] - 2025-10-17

### Fixed
- **Copyright Detection**: Fixed overly aggressive filtering of copyright holders (issue #32)
  - Copyright holders containing words like "Test", "Demo", etc. are now correctly detected when part of legitimate names
  - "Test Corporation", "TestCo Inc", and similar names are now properly recognized
  - Only standalone test/demo placeholders are filtered out (e.g., just "test" or "demo")
  - Maintains filtering of actual placeholder text while allowing real organizations with these words

## [1.5.0] - 2025-10-15

### Added
- **Enhanced License Detection Accuracy**: Significantly improved license detection with multi-pattern support (PR #30, issue #29)
  - Multi-line pattern detection for licenses split across lines
  - Fuzzy matching for common typos (e.g., "Lisense" to "License")
  - Version suffix handling (GPLv2+ to GPL-2.0-or-later)
  - License keyword detection with 47 comprehensive patterns
  - Support for detecting licenses in all file types
- **Comprehensive Benchmark**: Added detailed comparison with ScanCode Toolkit
  - Performance comparison showing 1.8x-30x faster execution
  - Detection accuracy analysis with feature comparison matrix
  - Use case recommendations for both tools

### Improved
- **4-Tier License Detection**: All detection methods now engage for maximum accuracy
  - Hash matching for exact license files
  - Dice-Sørensen similarity for text similarity
  - TLSH fuzzy hashing for variant detection
  - Enhanced regex patterns for edge cases
- **Edge Case Handling**: Fixed detection for numerous previously failing cases
  - Python Software Foundation License full phrase
  - GNU Lesser General Public License v2.1
  - Generic GPL references with context-aware version detection
  - MIT licenses in copyright lines
  - Apache License with newlines in header
- **Pattern Library**: Integrated patterns from scancode-licensedb
  - Added 47+ license patterns for comprehensive coverage
  - Improved detection for permissive, copyleft, and proprietary licenses
  - Better handling of license variations and aliases

### Fixed
- **License Normalization**: Improved SPDX ID normalization
  - GNU-GPL-v2 to GPL-2.0
  - GPLv2+ to GPL-2.0-or-later
  - Better handling of version suffixes and variations
- **False Negative Reduction**: Reduced false negative rate from 46.7% to near 0%
  - Previously undetected licenses now properly identified
  - Improved coverage across different file types and formats

### Performance
- **Copyright Extraction**: 26x more comprehensive than comparable tools
- **Speed**: Maintained 1.8x-30x faster performance while improving accuracy
- **Scalability**: Successfully tested on large codebases (FFmpeg-8.0)

## [1.4.1] - 2025-10-12

### Fixed
- **pyproject.toml PEP 639 File Reference**: Fixed license detection from `license = {file = "LICENSE"}` format
  - Changed from non-existent `_detect_license_from_text()` to proper `_detect_from_full_text()` method
  - Now correctly reads and detects licenses from referenced files in pyproject.toml
  - Properly sets category as DECLARED for licenses from metadata file references
  - Added debug logging when referenced license file doesn't exist

### Removed
- **Notices Output Format**: Removed human-readable notices format to focus on scanning and verification
  - Removed `notices_formatter.py` module
  - Removed `generate_notices()` method from LicenseCopyrightDetector
  - Removed notices option from CLI output formats
  - Updated documentation to remove references to notices format
  - This simplifies the codebase and clarifies the tool's primary purpose as a scanner/verifier

## [1.4.0] - 2025-10-12

### Added
- **Source Header License Detection in Metadata Files**: Extract SPDX tags and license references from comments/headers
  - Detects licenses in XML comments (pom.xml)
  - Detects licenses in Python comments (setup.py, setup.cfg)
  - Detects licenses in TOML comments (Cargo.toml)
  - Detects licenses in Ruby comments (*.gemspec)
  - New `_extract_header_licenses()` method for comprehensive header scanning
- **Enhanced Package Metadata Support**: Added extraction methods for additional formats
  - Full support for package.json (Node.js) with SPDX expressions and arrays
  - Full support for composer.json (PHP) with comment cleaning
  - Improved extraction from all major package formats
- **Fast-path Metadata API**: New `extract_package_metadata()` method for metadata-only extraction
  - Skips full text analysis for faster processing
  - Supports all major package metadata formats
  - Returns licenses from both structured metadata and source headers

### Improved
- **Intelligent License Deduplication**: Smart handling when same license found in multiple locations
  - Prefers metadata version over header version as more authoritative
  - Prevents duplicate licenses in results
  - Tracks licenses by (spdx_id, match_type) for accurate deduplication
- **Python Classifier Extraction**: Fixed to handle both quoted and unquoted formats
  - Works with setup.py quoted classifiers
  - Works with setup.cfg unquoted classifiers
  - Properly extracts OSI Approved licenses from trove classifiers
- **File Pattern Matching**: Enhanced to handle temporary files and various naming conventions
  - Supports files ending with metadata names (e.g., temp_xyz.package.json)
  - Better handling of edge cases in file detection
- **Gemspec and Cargo.toml Processing**: Added duplicate prevention
  - Tracks found licenses to avoid duplicates
  - Handles both single and array license declarations

### Fixed
- **Duplicate License Detection**: Resolved issues with licenses appearing multiple times
  - Fixed gemspec pattern matching causing duplicates
  - Fixed Cargo.toml SPDX expression parsing duplicates
  - Improved overall deduplication logic

## [1.3.6] - 2025-09-06

### Added
- **Tier 0 Exact Hash Matching**: Added SHA-256 and MD5 hash matching as the first detection tier
  - Pre-computed hashes for all 699 SPDX licenses
  - Support for license variants and aliases
  - 100% confidence for exact matches
  - New `DetectionMethod.HASH` enum value
- **Hash Inventory System**: Comprehensive hash inventory for license matching
  - Standard SPDX license hashes
  - Common variants (e.g., gradle-wrapper Apache-2.0)
  - Hash lookup tables for fast matching
  - Support for hash collisions (e.g., GPL versions)

### Improved
- **Detection Tier Reorganization**: Four-tier system: Hash → Dice-Sørensen → TLSH → Regex
  - Exact hash matching runs first for perfect matches
  - Dice-Sørensen no longer requires TLSH confirmation for >95% confidence
  - Better performance and accuracy
- **Apache-2.0 vs Pixar Disambiguation**: Special handling for Modified Apache 2.0 License
  - Prefers Apache-2.0 over Pixar when Dice-Sørensen scores are within 1%
  - Fixes issue #16 where Apache-2.0 was incorrectly detected as Pixar
  - Handles gradle-wrapper.jar Apache license variant correctly

### Fixed
- **TLSH Hash Collision**: Resolved Apache-2.0 being misidentified as Pixar license
  - TLSH hashes were too similar (distance 8-24)
  - Now handled by preferring base license over modified versions
  - Exact hash matching bypasses fuzzy matching issues
- **License Loading**: Fixed `get_all_license_ids()` to properly handle dictionary format

## [1.3.5] - 2025-09-03

### Added
- **Expanded License File Detection**: Added comprehensive license file patterns
  - GPL variants (`*GPL*`)
  - Copyleft files (`*COPYLEFT*`)
  - EULA files (`*EULA*`)
  - Commercial license files (`*COMMERCIAL*`)
  - Agreement files (`*AGREEMENT*`)
  - Bundle license files (`*BUNDLE*`)
  - Third-party license files (`*THIRD-PARTY*`, `*THIRD_PARTY*`)
  - Legal documents (`LEGAL*`)

### Improved
- **License Detection Coverage**: Extended fallback keyword detection to include: gpl, copyleft, eula, commercial, agreement, bundle, third-party, third_party
- **Pattern Flexibility**: All patterns now support characters before/after keywords (., -, _, etc.)

## [1.3.4] - 2025-09-02

### Added
- **Enhanced Archive Support**: Added support for additional archive formats:
  - Java archives (.jar, .war, .ear)
  - .NET packages (.nupkg)
  - Ruby gems (.gem) with nested archive extraction
  - Rust crates (.crate)

### Improved
- **Copyright Detection Completeness**: Removed artificial 20-file limit for source file scanning
  - Now scans ALL source files (.c, .h, .py, .js, .java, .cpp, .go, .rs, .ts, .tsx, .jsx)
  - Improves detection from ~12 to 700+ copyright statements on large codebases
  - Maintains 94% accuracy with comprehensive false positive filtering
- **File Scanner Reliability**: Fixed SafeFileScanner visited_inodes persistence bug
  - Eliminates false "symlink loop" warnings on subsequent scans
  - Enables proper scanning of multiple file extensions

### Fixed
- **Single File Detection**: Enhanced handling of directly-passed files as potential license content
- **MIT License Detection**: Improved regex patterns for partial MIT license text recognition
- **Archive Extraction**: Better support for nested archive formats and Ruby gem structure

### Repository
- **Cleanup**: Removed test-packages/ directory and added to .gitignore to keep repository clean

## [1.3.3] - 2025-08-30

### Improved
- **Confidence Scoring**: Enhanced regex-based license detection with context-aware confidence scoring
  - License files: 100% confidence for exact matches
  - Full license headers in source files: 90% confidence
  - License references: 30-50% confidence based on pattern matches
  - Better distinction between comprehensive headers vs. brief references
- **Categorization Logic**: Improved license categorization to distinguish between full license headers and simple references
- **Pattern Matching**: Enhanced regex detection to track exact number of patterns matched for more accurate confidence scoring

### Technical Changes
- Added `_adjust_regex_confidence` method for intelligent confidence adjustment
- Enhanced pattern matching to differentiate license headers from references
- Improved license categorization logic for better accuracy assessment

## [1.3.2] - 2025-08-30

### Fixed
- **CLI Options**: Fixed decorator ordering to enable `-f` output format option
- **Documentation**: Updated README with complete feature list and examples

### Changed
- **Version Option**: Moved to proper position in CLI decorator chain

## [1.3.1] - 2025-08-30

### Added
- **Archive Extraction**: Restored archive extraction capability with configurable `--max-extraction-depth` option for nested archives
- **Cache Functionality**: Added caching support with `--cache-dir` option to speed up repeated scans
- **Version Command**: Added `--version` option to display the tool version
- **Output Formats**: Restored support for multiple output formats:
  - `kissbom`: Simple JSON format with packages and licenses
  - `cyclonedx-json`: CycloneDX SBOM in JSON format
  - `cyclonedx-xml`: CycloneDX SBOM in XML format
  - `notices`: Human-readable legal notices with license texts

### Changed
- **Directory Traversal**: Restored `--max-depth` option with enhanced symlink loop protection using inode tracking
- **Safe File Scanner**: Implemented SafeFileScanner class for secure directory traversal with depth limiting

### Fixed
- **Missing Features**: Restored several features that were accidentally removed in previous refactoring
- **Documentation**: Updated all documentation to reflect current functionality
- **Code Quality**: Removed unused `get_license_aliases` method and other dead code

## [1.2.9] - 2025-08-30

### Added
- **License Hierarchy System**: Categorizes licenses as 'declared', 'detected', or 'referenced' for better understanding of license provenance
- **Enhanced Output Format**: Summary now shows declared_licenses, detected_licenses, and referenced_licenses separately
- **Copyright Holders List**: Summary includes unique list of copyright holders
- **Match Type Field**: Each license detection includes match_type (e.g., license_file, spdx_identifier, text_similarity)

### Changed
- **Class Renamed**: Main class renamed from `LegalAttributionGenerator` to `LicenseCopyrightDetector` to better reflect its functionality (BREAKING CHANGE)
- **Model Renamed**: `AttributionResult` renamed to `DetectionResult` to better reflect its purpose (BREAKING CHANGE)

### Fixed
- **Copyright False Positives**: Improved filtering to exclude placeholders like "YYYY Name", "TODO", and code fragments
- **Invalid Copyright Holders**: Added detection for fragments like "in result", "lines that vary", "detector", "generator"
- **Placeholder Detection**: Better filtering of template placeholders in copyright statements

### Removed
- **Dead Code**: Removed unused `max_extraction_depth` configuration option
- **Unused Import**: Removed unused `fuzz_process` import from license_detector.py
- **Misleading Function Name**: Renamed `_process_extracted_package()` to `_process_local_path()`
- **Test Files**: Removed development test files from repository
- **Build Directory**: Cleaned up build artifacts
- **Duplicate Method**: Consolidated duplicate `_is_license_file` implementations

## [1.2.8] - 2025-08-29

### Fixed
- **License Expression Parsing**: Fixed incorrect splitting of "or later" suffix (e.g., "LGPL 3 or later" now correctly parsed as single license)
- **False Positive Detection**: Added filtering for TODO, FIXME, XXX, and placeholder text that were incorrectly detected as licenses
- **MIT License Detection**: Added quick pattern matching for MIT licenses before TLSH to prevent misidentification as JSON
- **Test File Scanning**: Fixed overly aggressive filtering that skipped all files with "test_" prefix, now only skips specific test patterns

### Improved
- **Detection Accuracy**: Significantly reduced false positives in license identification
- **Expression Handling**: Better handling of license suffixes like "or later", "or-later", "+"

## [1.2.7] - 2025-08-29

### Added
- **Dynamic License Normalization**: Uses 1841+ name mappings from bundled SPDX data instead of hardcoding
- **Properties for SPDX Data**: Added `aliases` and `name_mappings` properties to SPDXLicenseData class
- **Comprehensive Normalization**: Support for 99.1% of SPDX licenses (694/700) with intelligent normalization
- **Better Version Handling**: GPL/LGPL/AGPL versions properly normalized (e.g., GPL-3 → GPL-3.0)
- **Common Aliases**: Added fallback aliases for "New BSD", "Simplified BSD", "CC0", etc.

### Changed
- **SPDX Tag Detection**: Improved regex to capture multi-word licenses like "Apache 2.0", "GPL v3"
- **Normalization Method**: Refactored to use data-driven approach with bundled mappings
- **Import Organization**: Moved module-level imports to avoid inline imports

### Fixed
- **Duplicate Methods**: Removed duplicate `_normalize_text()` and `get_all_license_ids()` methods in spdx_licenses.py
- **Dead Code**: Removed unused methods and unreachable code sections
- **Import Issues**: Fixed repeated inline imports of `re` module
- **License Detection**: Fixed normalization for licenses with spaces (e.g., "Apache 2.0" → "Apache-2.0")
- **Suffix Handling**: Proper handling of deprecated + suffix licenses (GPL-3.0+ → GPL-3.0-or-later)

### Performance
- **Code Quality**: Reduced duplication and improved maintainability
- **Normalization Coverage**: Increased from ~12% to 99.1% for SPDX license ID variations

## [1.2.6] - 2025-08-17

### Changed
- **Project Description**: Updated to "Semantic Copycat Open Source License Identification Library"

## [1.2.5] - 2025-08-17

### Added
- **TLSH Confirmation Mechanism**: Dice-Sørensen matches are now confirmed with TLSH to prevent false positives
- **Required TLSH Dependency**: `python-tlsh>=4.5.0` is now a required dependency (was optional)
- **Enhanced Documentation**: Comprehensive explanation of three-tier detection system in README and docs
- **TLSH Confirmation Method**: New `confirm_license_match()` method with configurable threshold

### Changed
- **TLSH Thresholds**: Strict threshold (30) for standalone detection, relaxed (100) for confirmation
- **Detection Flow**: Tier 1 now includes TLSH confirmation for all Dice-Sørensen matches
- **Documentation**: Updated README with detailed "How It Works" section
- **Project Status**: Updated CLAUDE.md to reflect v1.2.5 improvements

### Fixed
- **False Positive Prevention**: TLSH confirmation significantly reduces false positives
- **Code Cleanup**: Removed 8 unused utility methods from ConfigLoader and InputProcessor

### Performance
- **Testing Coverage**: Validated on 10+ language ecosystems with 97-100% accuracy
- **Detection Accuracy**: Maintained 97%+ accuracy while reducing false positives

## [1.2.0] - 2025-08-16

### Added
- **Parallel Processing**: Multi-threaded scanning with ThreadPoolExecutor for significantly faster performance
- **Enhanced License Detection**: Improved regex patterns for package metadata (package.json, METADATA, pyproject.toml)
- **Smart File Handling**: Intelligent sampling for large files (>10MB) without timeouts
- **Complete File Coverage**: Scans ALL readable text files, not limited to specific extensions
- **700+ SPDX Support**: Full support for all SPDX license IDs with alias normalization
- **Text Normalization**: Added `_normalize_text()` method for consistent license comparison
- **Configurable Threading**: CLI option `--threads` to control parallel processing (default: 4)
- **Better Metadata Detection**: 
  - Detects `"license": "MIT"` in package.json
  - Detects `License-Expression: MIT` in Python METADATA files
  - Detects `license = {text = "Apache-2.0"}` in pyproject.toml

### Changed
- **File Processing**: Now uses parallel processing for license and copyright detection
- **File Reading**: Smart reading strategy - full read for <10MB, sampling for larger files
- **Error Handling**: Improved with specific exception types and per-file timeouts (30s)
- **License Matching**: Enhanced normalization handles more variations (Apache 2.0 → Apache-2.0)
- **False Positive Filtering**: Better detection and filtering of code patterns in both license and copyright extraction

### Fixed
- Removed duplicate `_normalize_license_id()` method
- Removed unused imports (`time`, redundant `fnmatch`)
- Fixed bare `except:` clauses with specific exception types
- Removed redundant `hasattr()` checks
- Improved copyright holder validation to filter more false positives

### Performance Improvements
- Parallel file processing reduces scan time by up to 75% on multi-core systems
- Smart file sampling for large files prevents memory issues
- Deduplication during processing reduces post-processing time
- Lazy loading of SPDX data improves startup time

## [1.1.2] - 2025-01-16

### Breaking Changes
- **Removed package URL (purl) support**: Tool no longer downloads or processes packages from PyPI, npm, etc.
- **Removed external API integrations**: ClearlyDefined, PyPI, and npm APIs have been removed
- **Focus on local scanning only**: Tool now exclusively scans local directories and files

### Changed
- **Core functionality**: Refocused on local source code license and copyright identification
- **Input handling**: Now only accepts local file paths and directories
- **Attribution format**: Changed from purl-based to path-based attribution
- **Dependencies**: Removed packageurl-python dependency

### Removed
- Package downloading and extraction capabilities
- Purl file parsing functionality  
- External API data sources (ClearlyDefined, PyPI, npm)
- Network timeout configuration
- Online/offline mode distinction (tool is always offline)

### What the Tool Now Does
- Scans local source code for SPDX license identification
- Extracts copyright information from local files
- Identifies license files and matches them with bundled SPDX data
- Uses multi-tier detection: Dice-Sørensen similarity, TLSH fuzzy hashing, and regex patterns
- Generates attribution reports in KissBOM, CycloneDX, and human-readable formats

## [1.1.1] - 2025-01-16

### Added
- **Offline-first operation**: Tool now works offline by default, no API calls unless explicitly requested
- **`--online` flag**: New CLI option to enable external API sources (ClearlyDefined, PyPI, npm)
- **Bundled SPDX license data**: Package includes 700+ SPDX license definitions with full text for 40+ common licenses
- **License text in notices**: Human-readable notices now include full license text
- **Debug logging**: Added comprehensive debug logging for troubleshooting copyright extraction
- **Copyright validation**: Improved filtering of invalid copyright patterns (URLs, code snippets, etc.)
- **Build automation**: Scripts to update SPDX license data during package build

### Changed
- **Default behavior**: Changed from online-first to offline-first operation
- **API usage**: External APIs now supplement rather than replace local analysis
- **Copyright extraction**: Significantly improved accuracy with better pattern matching and deduplication
- **Logging**: Reduced verbosity in normal mode, cleaner output

### Fixed
- **Copyright false positives**: Fixed extraction of code patterns as copyright holders
- **Duplicate copyrights**: Improved deduplication of copyright holders with variations
- **Invalid domains**: Fixed "domain.invalid" and URL patterns appearing in copyright
- **SSL warnings**: Suppressed urllib3 SSL warnings on macOS systems
- **Package build**: Fixed missing submodules in wheel distribution

### Technical Improvements
- **Performance**: Faster processing without network calls in default mode
- **Reliability**: Works without internet connection
- **Privacy**: No data sent to external services by default
- **Size**: Package includes all necessary data (1.5MB of SPDX licenses)

## [0.1.0] - 2025-01-15

### Initial Release
- **Multi-source input**: Process single purls, purl files, or local directories
- **Three-tier license detection**: 
  - Tier 1: Dice-Sørensen similarity (97% threshold)
  - Tier 2: TLSH fuzzy hashing
  - Tier 3: Regex pattern matching
- **Copyright extraction**: Pattern-based extraction from source files
- **Multiple output formats**: KissBOM, CycloneDX, human-readable notices
- **External data sources**: Integration with ClearlyDefined, PyPI, npm APIs
- **CLI and library interfaces**: Use as command-line tool or Python library
- **Multi-threaded processing**: Configurable parallel processing
- **Configuration system**: YAML-based configuration with environment variables

### Package Metadata
- Author: Oscar Valenzuela B.
- Email: oscar.valenzuela.b@gmail.com
- License: Apache-2.0
- Repository: https://github.com/oscarvalenzuelab/semantic-copycat-oslili