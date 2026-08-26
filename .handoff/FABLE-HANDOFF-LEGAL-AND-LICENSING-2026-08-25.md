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
   - Added `license:` / `attribution:` metadata to the (since removed) model catalog.

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

# Verify JSON syntax of manifest
python3 -c "import json; json.load(open('data/manifest.json'))"
```

---

## 4. Second Fable Pass — Results (2026-08-25)

All six `[fable]` items are complete; details, corrections and founder flags are
in `documentation/legal/LEGAL-AND-LICENSING-TODO.md` §5. Highlights:

- **Corrected notices** (verified against licence texts via a 15-agent research +
  adversarial-verification workflow): several hand-typed notice strings did not
  match the licence wording. Replaced by reading the licence text the runtime
  ships with each model — no model names remain in code or docs.
- **New code**: `halbert_core/halbert_core/model/attribution.py` (source of truth),
  `scripts/add_spdx_headers.py` (+ `--check`), `scripts/check-dco.sh`,
  `tests/test_legal_metadata.py`, `tests/test_model_attribution.py`,
  `halbert_core/LICENSE` (PEP 639 copy).
- **Edited**: `Halbert/main.py` (`--version`, `info`, `license --full|--third-party`,
  model attribution), `halbert_core/__init__.py` (`__version__`, `LEGAL_NOTICE`),
  `dashboard/__main__.py` (`--version`, startup notice), `routes/llm.py`
  (licence fields on `/api/llm/proxy/models`), `ModelCard.tsx` (licence badge),
  `.github/workflows/dco.yml`, `pyproject.toml`,
  `Cargo.toml`, `package.json`, `tauri.conf.json`, `LICENSE.md`, `README.md`,
  `documentation/README.md`, `documentation/legal/README.md`,
  `THIRD-PARTY-LICENSES.md` (§3.5, §4, §5), `RAG-DATA-SOURCES`, `DOCUMENTATION-PLAN`,
  `CHANGELOG.md`, `CONTRIBUTING.md` (commit sign-off note) — plus SPDX headers on
  566 source files.
- **Section 2 research questions** (APSL 2.0 chunking, CC BY-SA synthesis
  boundaries) were out of the `[fable]` scope and remain open for the `[opus]`
  LEG-CRIT-01 / LEG-MAJ-05 track; the `[fable]` SPDX-coverage question is closed.
- **Not touched (other sessions active)**: `routes/legal.py` (wrong notices —
  should import from `attribution.py`), `config/licensing.yml`, `corpus/`,
  `scripts/scrape_macos.sh` (pre-existing syntax error at line 138).

Verification commands:

```bash
.venv/bin/python -m pytest tests/test_legal_metadata.py tests/test_model_attribution.py tests/test_cli_smoke.py -q
.venv/bin/python scripts/add_spdx_headers.py --check
.venv/bin/python Halbert/main.py --version && .venv/bin/python Halbert/main.py license --third-party | head
(cd halbert_core/halbert_core/dashboard/frontend && ./node_modules/.bin/tsc --noEmit)
bash scripts/check-dco.sh origin/main
```

---

## 5. Model-Mention Sweep — 2026-08-25 (founder directive: no model names or recommendations anywhere)

Inventory (5 read-only agents): 379 occurrences in ~90 files, classified as
user-facing recommendation / hard-coded default / functional name list /
test fixture / runtime-name-only / historical. Edit pass (6 agents on disjoint
file sets, Edit-only because other sessions were active), then cross-area
fixes by the orchestrator.

What changed, by kind:

- **Docs** (README, INSTALLATION, CONFIGURATION, CLI/API reference, FEATURES,
  ARCHITECTURE, guides/model-selection → "Sizing a Model for Your Hardware",
  troubleshooting, quickstart, architecture/*, design/*, prompts READMEs):
  every named model, "recommended model" table, hardware→model tier and
  `ollama pull <name>` replaced by `<model>` placeholders or parameter-size /
  memory budgets. Broken README link fixed.
- **Config templates**: `config/model-catalog.yml` deleted; `config/models.yml`
  is a neutral template (empty `model:` slots, private Tailscale endpoint
  replaced by localhost — the live config is the user config dir);
  `config/model.json` template emptied; `.env.example` dead model vars
  commented out.
- **Code defaults → configuration**: `get_configured_model()` returns "" when
  nothing is configured; `router.py`, `loader.py`, `app_seam.py`,
  `agents/llm_client.py`, `rag/llm.py`, `rag/raptor.py`, `rag/graphrag.py`,
  `rag/trending_discovery.py`, `routes/discovery.py`, `routes/agent.py`,
  `routes/gpu.py`, `halbert ask --model` all resolve the configured model
  lazily and raise "No model configured — choose one in Settings → AI Models"
  instead of posting a fabricated id.
- **Detection without names**: `ModelCapabilities.detect()` uses models.yml
  overrides → runtime metadata (Ollama `/api/show` `capabilities`,
  `context_length`) → generic tokens (think/reason/vision/-vl/embed/code, size
  tags, MoE `NxMb`); `OllamaProvider.show_model()` caches `/api/show`;
  Anthropic provider allow-list removed (ids pass through); reasoning
  detection centralised in `utils/reasoning.is_reasoning_model`; intake budget
  MoE regex generic + optional `tier:` override.
- **Recommendation engine → size budgets**: `HardwareDetector.recommend_budget()`
  (max parameters at 4-/8-bit) replaces named recommendations;
  `pick_installed_model()` chooses the largest already-installed model that
  fits; `halbert hardware-detect` prints budgets (`--recommend` removed);
  `config-wizard --model <id>`; Settings "Quick Setup" → "Apply Hardware
  Defaults" (compression tier + largest installed model, never a fixed list);
  `GET /settings/model/status` no longer returns `recommended_model`.
- **Dashboard**: `_OLLAMA_CLOUD_CANDIDATES` list removed — cloud discovery
  probes `advanced.ollama_cloud_candidates` from the user's llm config (empty
  by default; typed in `types/llm.ts`); `RECOMMENDED_MODELS` removed, embedding
  auto-select is capability-based; no literal HF repo id.
- **Licence notices**: `attribution.py` classifies the licence text the runtime
  ships (`/api/show` → `license`); no model table anywhere.
- **Tests**: fixtures use `example-*` ids; suites green (`pytest tests/`
  122 passed; `halbert_core/tests` 1069 passed; `tsc --noEmit` clean; SPDX
  583/583).

Deliberately left (infrastructure / other owners / history):
- Embedding-model defaults in `rag/embeddings.py`, `rag/pipeline.py`,
  `index/chroma_index.py` (tied to existing indices) and the matching
  dependency row in `THIRD-PARTY-LICENSES.md` §3.1; docs now say "the
  configured embedding model".
- `dashboard/routes/legal.py` `_FOUNDATION_MODELS` (LEG-MOD-01 session's
  file): still a hand-typed model list with wrong notices — should be
  computed from configured models via `attribution.py`.
- External docs links to docs.sourceprep.io/guides/models in the model picker.
- Historical records: `CHANGELOG.md`, `.handoff/*`, `documentation/RAG_AUDIT_REPORT.md`,
  `documentation/design/unified-model-picker.md` decision log (mentions the
  old "Apply Recommended Config" button name), sovereign-host-vision reviews.

Behavioural notes for the founder:
- A dev checkout with no user-level models.yml now has **no model** until one
  is chosen in Settings → AI Models (previously a fabricated default id that
  usually was not installed anyway).
- Reasoning-model prompt overrides now trigger on generic tokens, Ollama's
  `thinking` capability, or a models.yml `capabilities:` override — a
  reasoning model whose id has none of these needs the override.
- `OllamaProvider.list_models()` makes one cached `/api/show` call per model.
