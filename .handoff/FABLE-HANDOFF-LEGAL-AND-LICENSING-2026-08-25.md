# Fable Handoff — Legal, Licensing & Compliance Review (2026-08-25)

**Date:** 2026-08-25  
**Model Tier:** fable / research  
**Context:** Master action plan in `documentation/legal/LEGAL-AND-LICENSING-TODO.md`  
**Purpose:** Initial pass results, validation checklist, and research instructions for fable-track legal audit.

---

## 1. Initial Pass Completed (This Session)

The following initial pass items have been implemented and verified:

1. **`LEG-MOD-05` (CLI Legal Notice & Subcommand)**:
   - Added `SPDX-License-Identifier: GPL-3.0-or-later` and copyright headers to `Halbert/main.py`.
   - Updated `cmd_info` to display GPLv3 license status, author copyright, and warranty disclaimer.
   - Added interactive `halbert license` CLI subcommand reading `documentation/legal/LICENSE.md` with pointers to third-party notices.
   - Verified via `/usr/bin/python3 Halbert/main.py info` and `/usr/bin/python3 Halbert/main.py license`.

2. **`LEG-MAJ-06` (DCO & PR Template)**:
   - Created `.github/workflows/dco.yml` to automatically verify `Signed-off-by:` trailers on all commits in pull requests.
   - Created `.github/PULL_REQUEST_TEMPLATE.md` with Developer Certificate of Origin (DCO) sign-off check and contribution certification.

3. **`LEG-MOD-04` (Foundation Model Attribution)**:
   - Updated `config/model-catalog.yml` with explicit `license:` and `attribution:` metadata for `llama3.1-8b`, `llama3-8b`, `qwen2.5-coder-14b`, `deepseek-coder-33b`, and `codellama-34b`.

4. **`LEG-MIN-04` (Documentation Cross-References)**:
   - Updated `data/manifest.json` cross-references from obsolete paths to canonical `documentation/legal/` and `documentation/legal/THIRD-PARTY-LICENSES.md`.

5. **`LEG-MIN-01` (Core SPDX Headers)**:
   - Added SPDX headers to `halbert_core/halbert_core/__init__.py` and `halbert_core/halbert_core/dashboard/__main__.py`.

---

## 2. Fable Review & Further Research Assignment

### Review Objective
Review all changes made during the initial pass to verify syntax integrity, compliance with GPL-3.0 Section 5(d), schema validity of modified YAML/JSON files, and lack of regressions.

### Deep Research Questions to Investigate
1. **APSL 2.0 (Apple Public Source License) Man Page Chunking**:
   - 5,280 macOS man pages are stored in `data/macos/man-pages/`. Some utilities (e.g., Apple-authored CLI tools) carry APSL 2.0.
   - *Question*: Does vectorizing and embedding APSL 2.0 / BSD man pages into JSONL and SourcePrep graph nodes trigger APSL 2.0 source distribution obligations? (Check APSL 2.0 Section 2.2).
2. **CC BY-SA 4.0 Share-Alike Boundaries in RAG Citations**:
   - Ask Different / Stack Exchange Q&A (269 documents in `data/macos/ask-different/`) carry `CC BY-SA 4.0`.
   - *Question*: When the LLM retrieves a CC BY-SA 4.0 chunk and synthesizes a sysadmin response, does the resulting response constitute an adapted derivative work under CC BY-SA 4.0 requiring Share-Alike licensing, or is the citation covered by fair use / fact extraction?
3. **SPDX Coverage Expansion**:
   - Identify all Python, TypeScript, and Rust files in `halbert_core/` and `dashboard/frontend/` that still lack SPDX headers.

---

## 3. Verification Commands

```bash
# Verify CLI legal command
/usr/bin/python3 Halbert/main.py license

# Verify YAML syntax of model catalog
python3 -c "import yaml; yaml.safe_load(open('config/model-catalog.yml'))"

# Verify JSON syntax of manifest
python3 -c "import json; json.load(open('data/manifest.json'))"
```
