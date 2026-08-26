# Corpus Licensing Architecture & Build Gate

**Date:** 2026-08-25
**Status:** Implemented
**Covers:** `LEG-CRIT-01` (SS64 non-commercial quarantine), `LEG-MAJ-05` (Arch Wiki GNU FDL macOS gate)
**Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors**

---

## 1. The problem this solves

Halbert's RAG corpus is assembled from thirteen upstream sources under seven
different licences. Two of them cannot ship everywhere:

| Content | Licence | Cannot ship in |
|---------|---------|----------------|
| SS64.com macOS command pages | CC BY-NC 4.0 | Any **paid** channel — LemonSqueezy Pro or the Mac App Store |
| Arch Wiki | GNU FDL 1.3 | Any **DRM-wrapped** channel — the Mac App Store |

Before this work, both restrictions lived only in prose: a `note` field in
`data/manifest.json` and a paragraph in a planning document. The build scripts
bundled `data/linux` and `data/common` wholesale with no idea what was inside
them, and `data/macos/support/macos_support.jsonl` mixed 87 CC BY-NC SS64 pages
with 17 Halbert-authored guides **inside a single file** — so even a per-path
allowlist would have shipped the non-commercial content.

Two independent failures were therefore one careless `--add-data` away:

* **Commercial infringement.** CC BY-NC judges "NonCommercial" on the purpose of
  the distribution, not on whether an individual file is priced. Bundling SS64
  into Halbert Pro infringes even though the file itself is not sold.
* **Copyleft/DRM conflict.** GFDL 1.3 §2 forbids "technical measures to obstruct
  or control the reading or further copying" of the copies you distribute. The
  App Store's FairPlay wrapper is exactly such a measure. The licence permits
  commercial use; it does not permit *that*.

---

## 2. Architecture

Policy is separated from facts, and both are separated from enforcement.

```
config/licensing.yml                    ← the RULES     (what each licence allows,
                                                         what each channel requires)
data/manifest.json                      ← the FACTS     (which licence each corpus
                                                         path actually carries)
halbert_core/.../corpus/license_policy.py ← the ENGINE  (decide, and prove)
scripts/corpus_license_gate.py          ← the GATE      (CLI; non-zero exit blocks)
scripts/build-{linux,macos}.sh          ← the CALLERS   (stage, audit, then package)
halbert_core/tests/test_corpus_license_gate.py ← the PROOF
```

The split matters. A reviewer or a lawyer can read `config/licensing.yml` and
check the reasoning without reading any Python, and adding a source means adding
one `license_spdx` tag rather than editing build scripts.

### 2.1 Licence registry

Every licence is reduced to four machine-readable properties:

| Property | Meaning | Drives |
|----------|---------|--------|
| `commercial_use` | `allowed` / `prohibited` | Blocks CC BY-NC from paid channels |
| `copyleft` | `none` / `weak` / `strong` | Blocks GFDL from the App Store |
| `share_alike` | Derivatives must carry the same licence | Attribution and adaptation obligations |
| `drm_conflict` | Licence forbids "further restrictions" | Blocks GFDL and GPL text from DRM channels |

Aggregate tags (`LicenseRef-Mixed-Manpages`, `LicenseRef-Mixed-Permissive`) exist
for scraped sets whose individual pages differ, and are always rated at their
**worst case** so an aggregate can never be more permissive than its contents.

### 2.2 Distribution channels

| Channel | Commercial | DRM | Data roots | Max copyleft | Carries CC BY-NC | Carries GFDL |
|---------|-----------|-----|------------|--------------|------------------|--------------|
| `oss-linux` | no | no | linux, common | strong | no | **yes** |
| `oss-macos` | no | no | macos, bsd, common | strong | no | no (wrong platform) |
| `macos-pro` | **yes** | no | macos, bsd, common | strong | **no** | no (wrong platform) |
| `macos-app-store` | **yes** | **yes** | macos, bsd, common | **weak** | **no** | **no** |
| `hf-dataset` | no | no | all | strong | no | yes |

`oss-linux` shipping GFDL content is correct, not an oversight: the community
Linux build is GPL-3.0, free of charge and free of DRM, which is exactly what
GFDL contemplates. The exclusion is a property of the *channel*, not of the
content.

The quarantine directory is excluded from every channel, including the free ones.
One corpus build then serves every macOS channel, and no future repackaging can
promote a free build into a paid one and carry the non-commercial slice with it.

### 2.3 Two enforcement layers

**Path level.** Each channel declares its `data_roots` and a `deny_paths` list.
A path outside the roots, or matching a deny entry, cannot ship.

**Record level.** Every `.jsonl` in a staged bundle is scanned. A record is a
violation if its `source` is registered under `record_quarantine:`, or if it
carries a `license_spdx` / `license` tag whose terms fail the channel policy.

The second layer is the one that matters. It is what catches a re-scrape
re-populating a shippable file with SS64 content, and it is why the gate would
have caught the original mixed-licence file that a path allowlist would have
waved through.

An unrecognised licence string is a **violation**, not a default-allow. Free-text
strings written by the scrapers (`"FreeBSD Documentation License"`, `"local"`)
are mapped onto registry ids via `license_aliases:`; anything unmapped stops the
build with "classify it before shipping".

---

## 3. LEG-CRIT-01 — SS64 quarantine

### 3.1 What was done

```
data/macos/support/macos_support.jsonl        104 records (87 SS64 + 17 Halbert)
                    ↓  scripts/quarantine_ss64.py
data/macos/support/macos_support.jsonl         17 records (Halbert-authored)
data/non-commercial/macos_ss64/ss64_macos.jsonl 87 records (CC BY-NC, tagged)
```

Every quarantined record gained explicit `license_spdx`, `license_url` and
`attribution` fields, so the record-level gate recognises it wherever it turns up
— including in a bundle produced by a future script nobody has written yet.

The split is idempotent and is now **run automatically** by
`scripts/scrape_macos.sh` immediately after the SS64 scraper. Without that, every
scrape silently undid the quarantine.

### 3.2 Replacement coverage

Removing 87 command references from the shippable corpus would have left a hole
in the most frequently asked category of question. So all 87 were rewritten from
scratch:

`data/macos/support/macos_command_guides.jsonl` — 87 original Halbert-authored
references (≈236 KB), generated from `scripts/macos_command_data.py` by
`scripts/generate_macos_command_guides.py`.

They are written against the behaviour of the tools as shipped on macOS 13–15,
verifiable by running the commands, and regenerable by anyone reading the
repository. No SS64 text, structure or ordering was copied. Holding the content
as a data table in version control rather than as a scraped artefact is what
makes that provenance checkable.

Each entry carries a summary, synopsis, an options table, worked examples and —
the part a generic man page does not give you — the macOS-specific traps: BSD vs
GNU flag differences, SIP and TCC interactions, Apple Silicon and Rosetta
behaviour, launchd instead of systemd.

Coverage is a **contract**, not a hope. `config/licensing.yml` declares:

```yaml
coverage_contracts:
  - id: macos-command-reference
    quarantined: non-commercial/macos_ss64/ss64_macos.jsonl
    replacement: macos/support/macos_command_guides.jsonl
    key: metadata.command
```

and `test_halbert_guides_fully_replace_the_quarantined_commands` fails if any
command loses its replacement. `scripts/build-macos.sh` checks the same contract
before it stages anything, so a build cannot silently ship reduced coverage.

`--check` mode on the generator asserts the committed JSONL still matches its
source table, so the corpus cannot drift away from the auditable content.

---

## 4. LEG-MAJ-05 — Arch Wiki build gate audit

Every path that could put Arch Wiki content into a macOS artifact was traced.

| Path | Before | After |
|------|--------|-------|
| `scripts/build-linux.sh` | Bundled `data/linux` + `data/common` wholesale, no checks | Stages via the gate, audits the staged tree, aborts on violation |
| `scripts/build-macos.sh` | **Did not exist** — no macOS build path at all | Created; channel-aware, gated twice, refuses to bundle raw `data/` |
| `scripts/scrape_macos.sh` | Writes only to `data/macos/*`; never touches `linux/` | Unchanged in that respect. Quarantine step added; pre-existing glob syntax error fixed |
| `config/platforms.yml` | macOS lists `data/macos`, `data/bsd`, `data/common` | Unchanged — correct, and now enforced rather than assumed |
| `halbert_core/rag/platform_loader.py` | Excludes `linux` on macOS at runtime | Also excludes `non-commercial` on every platform |
| `scripts/upload_hf_dataset.py` | Selects explicit directories; never selected `non-commercial/` | Hard assertion added: refuses to upload quarantined paths or records |

### 4.1 Defects found and fixed

1. **`data/manifest.json` claimed three Linux-only sources were macOS-eligible.**
   `linux_man_pages`, `linux_system_docs` and `vendor_and_distro_docs` all carried
   `mac_build: true` while every one of their paths lives under `linux/` — which
   macOS builds never ship. Harmless in effect, actively misleading to read, and
   exactly the kind of stale flag a future build script would trust. Corrected to
   `mac_build: false`; the engine reports this class of inconsistency as an
   advisory so it cannot recur unnoticed.

2. **`scripts/scrape_macos.sh` could not run at all.** A `2>/dev/null` inside a
   `for ... in` list is a bash syntax error, present at `HEAD`. The whole script
   aborted on parse. Fixed.

3. **No macOS build script existed.** `LEG-CRIT-01` asked for an assertion in
   `scripts/build-macos.sh`; there was no such file. It now exists, and the
   channel is a required argument precisely because the licence answer differs
   between them.

### 4.2 Why Linux man pages are treated as strong copyleft

`LicenseRef-Mixed-Manpages` is rated `copyleft: strong` and `drm_conflict: true`.
A meaningful slice of Linux man pages is GPL-licensed, and GPLv3 §10 forbids
imposing further restrictions on recipients. Rating the aggregate at its worst
case means the set can never reach a DRM-wrapped bundle by accident. Since Linux
man pages are Linux-only anyway, the rating costs nothing and closes a door.

---

## 5. Using it

```bash
# What would ship for a channel, and why everything else is excluded
python3 scripts/corpus_license_gate.py --channel macos-app-store

# Every channel at once
python3 scripts/corpus_license_gate.py --all-channels

# Gate a staged bundle — non-zero exit means do not ship
python3 scripts/corpus_license_gate.py --channel macos-pro --bundle build/corpus

# Replacement-coverage contracts only
python3 scripts/corpus_license_gate.py --coverage

# Stage and gate a macOS build without packaging anything
./scripts/build-macos.sh --channel macos-app-store --gate-only

# The tests
python3 -m pytest halbert_core/tests/test_corpus_license_gate.py
```

### Adding a corpus source

1. Add it to `data/manifest.json` with a `license_spdx`.
2. If that licence is not yet in `config/licensing.yml`, add it — with
   `commercial_use`, `copyleft`, `share_alike` and `drm_conflict` filled in
   deliberately, not copied from a neighbour.
3. Run `python3 scripts/corpus_license_gate.py --all-channels` and read which
   channels it lands in.
4. Run the tests. `test_every_manifest_source_has_a_registered_license` fails on
   anything unclassified.

### Adding non-commercial or otherwise restricted content

1. Put it under `data/non-commercial/<upstream-name>/`.
2. Stamp `license_spdx`, `license_url` and `attribution` on **every record**.
3. Register its record `source` under `record_quarantine:` in
   `config/licensing.yml`.
4. Add a replacement and a `coverage_contracts` entry **before** anything in the
   product depends on it.

---

## 6. Known gaps

* **359 records carry `"CC BY-SA (assumed; verify per site)"`** and 142 carry
  `"local"`. Both are scraper assumptions, not licences read off the page. They
  are resolved at their assumed terms and reported as advisories by the gate on
  every run. `LEG-MIN-03` adds the harness that confirms them upstream; until
  then the assumption is visible rather than buried.
* **The gate reads declared content, not a built artifact.** It audits the staged
  corpus tree, which is what the build then bundles. It does not crack open a
  finished `.app` or `.dmg` and re-verify. Auditing the extracted bundle as a
  post-build step is a worthwhile addition.
* **Vector indices are not covered.** The gate governs source documents. If an
  index is ever built from the full corpus and shipped pre-computed, embeddings
  derived from quarantined text would bypass every check here. Index builds must
  run from a gated, staged corpus — which is why the build scripts stage first
  and point `--add-data` at the staged tree only.

---

## 7. Related

* `documentation/legal/APP-STORE-DISTRIBUTION-STRATEGY.md` — GPLv3 §7 exception and open-core boundary (`LEG-CRIT-03`)
* `documentation/legal/LEGAL-AND-LICENSING-TODO.md` — the master action plan
* `data/non-commercial/README.md` — what is quarantined and why
* `config/licensing.yml` — the policy itself
