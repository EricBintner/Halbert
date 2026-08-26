# Halbert Legal, Licensing & Compliance Action Plan

**Date:** 2026-08-25 (fable review pass: 2026-08-25, see §5)  
**Status:** Living Master Action Plan & Priority Matrix  
**Scope:** Core Engine (GPL-3.0), Dual-Distribution (macOS Pro LemonSqueezy vs. Mac App Store), RAG Knowledge Base (28,869 docs), Third-Party Dependencies, AI Model Licensing, and Autonomous System Liability.

---

## 1. Role & Capability Tiering Legend

Every task is labeled with the appropriate agent or human execution tier:
- **`[founder]`** — Founder/Lead Executive decisions: legal strategy, commercial pricing/EULA selection, licensing agreements, trademark ownership.
- **`[opus]`** — High-reasoning architecture: open-core boundaries, Mac App Store sandbox isolation, dataset ingestion pipelines, license quarantine systems.
- **`[sonnet]`** — Standard implementation & authoring: creating legal artifacts (`THIRD-PARTY-LICENSES.md`, `PRIVACY.md`), UI attribution viewers, dataset cards.
- **`[fable]`** — Deterministic / mechanical execution: SPDX header mass-tagging, manifest verification, CLI disclaimers, schema validations.

---

## 2. Priority Matrix Overview

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                              PRIORITY & SEVERITY OVERVIEW                              │
├──────────┬───────┬─────────────────────────────────────────────────────────────────────┤
│ Level    │ Items │ Core Areas                                                          │
├──────────┼───────┼─────────────────────────────────────────────────────────────────────┤
│ CRITICAL │ 4     │ SS64 Non-Commercial Quarantine, Contributor IP Agreement,           │
│          │       │ Mac App Store GPLv3 Conflict, Autonomous Action Liability Waiver    │
│ MAJOR    │ 6     │ Missing THIRD-PARTY-LICENSES, HuggingFace Dataset Licences,         │
│          │       │ Missing Privacy Policy, LemonSqueezy Commercial EULA,               │
│          │       │ Arch Wiki GNU FDL macOS Isolation, DCO Commit Sign-off Setup        │
│ MODERATE │ 5     │ Dashboard UI Attribution Modal, Cloud API Data Flow Disclosure,     │
│          │       │ Third-Party Trademark Notice, Meta Llama 3.1 Attribution Badge,     │
│          │       │ CLI First-Run Disclaimers                                           │
│ MINOR    │ 4     │ SPDX-License-Identifier Source Tagging, Repository Copyright Sync,  │
│          │       │ Upstream RAG Scraper License Checks, Docs Cross-Reference Cleanup   │
└──────────┴───────┴─────────────────────────────────────────────────────────────────────┘
```

---

## 3. Prioritized Action Checklist

### 🔴 Critical Priority (Immediate Legal & Release Blockers)

- [x] **`LEG-CRIT-01`** `[opus]` **SS64 Non-Commercial (`CC BY-NC 4.0`) Dataset Quarantine**
  - **Problem**: SS64 macOS command references (`data/macos/support/macos_support.jsonl` slice) carry `CC BY-NC 4.0` (Non-Commercial). Including this in any commercial distribution (Halbert Pro on LemonSqueezy or Mac App Store) constitutes direct copyright infringement.
  - **Action**:
    1. Separate SS64 items into `data/non-commercial/macos_ss64/`.
    2. Expand Halbert-authored synthetic guides to provide 100% replacement coverage for macOS command syntax.
    3. Update `scripts/build-macos.sh` and packaging scripts to enforce an automated assertion preventing `CC-BY-NC` data from entering commercial release bundles.
  - **Delivered (2026-08-25)**:
    - 87 SS64 records split out to `data/non-commercial/macos_ss64/` by `scripts/quarantine_ss64.py` (idempotent; now run automatically at the end of the SS64 scrape in `scripts/scrape_macos.sh`, which previously undid the quarantine on every run).
    - 87 original Halbert-authored command references written to replace them: `data/macos/support/macos_command_guides.jsonl`, generated from `scripts/macos_command_data.py`. 100% command coverage, asserted by a `coverage_contracts` entry in `config/licensing.yml`, not by hand.
    - Policy engine `halbert_core/halbert_core/corpus/license_policy.py` + gate `scripts/corpus_license_gate.py`, enforcing at **path and record level** — the mixed-licence file that started this would have passed a path allowlist.
    - `scripts/build-macos.sh` created (it did not exist); `scripts/build-linux.sh` now stages via the gate and bundles only the staged tree.
    - `scripts/upload_hf_dataset.py` refuses to publish quarantined paths or records.
    - Architecture: `documentation/legal/CORPUS-LICENSING-ARCHITECTURE.md`. Tests: `halbert_core/tests/test_corpus_license_gate.py` (51 tests).

- [ ] **`LEG-CRIT-02`** `[founder]` **Contributor License Agreement (CLA) & Dual-Licensing Rights**
  - **Problem**: `CONTRIBUTING.md` currently enforces inbound=outbound GPL-3.0 without a relicensing grant. If external developers contribute without an agreement, the copyright is fragmented, legally blocking the founder from ever releasing commercial builds (Halbert Pro) or adding Mac App Store exceptions without 100% contributor approval.
  - **Action**:
    1. Decide between a lightweight **Developer Certificate of Origin (DCO)** with commercial relicensing grant vs. a full **Contributor License Agreement (CLA)**.
    2. Formalize that Halbert Core remains GPL-3.0, but the project maintainer retains rights to distribute binaries across proprietary marketplaces (App Store, LemonSqueezy) with appropriate exceptions.
    3. Update `documentation/contributing/CONTRIBUTING.md` and repository PR templates.

- [ ] **`LEG-CRIT-03`** `[founder]` + `[opus]` **GPL-3.0 vs. Mac App Store Conflict Strategy** — *opus half done; blocked on founder decision*
  - **Problem**: Apple Mac App Store DRM and Sandbox terms conflict with GPL-3.0 Section 6 (Installation Information) and Section 10 (prohibition against further restrictions).
  - **Action**:
    1. Adopt the dual-licensing / GPLv3 exception model (under GPLv3 Section 7) for the App Store companion client:
       > *"As a special exception, the copyright holders of Halbert grant permission to convey the object code of this work through the Apple Mac App Store notwithstanding Sections 6 and 10 of GPLv3."*
    2. Ensure no third-party GPLv3/copyleft libraries (which lack this exception) are statically linked into the Mac App Store binary target.
  - **Delivered (2026-08-25, `[opus]` half)**:
    - `documentation/legal/APP-STORE-DISTRIBUTION-STRATEGY.md` — the §6/§10 conflict stated precisely, proposed §7 exception text, where it goes (including the SPDX `WITH` form), the open-core boundary, and the required entitlements.
    - Action 2 automated: `scripts/check_appstore_deps.py` + `config/dependency-licenses.yml` fail the App Store build on any strong/weak copyleft or unclassified dependency across Python, Rust and npm. Wired into `scripts/build-macos.sh --channel macos-app-store`. Currently passing.
    - The one copyleft dependency, `systemd-python` (LGPL-2.1-or-later), is verified excluded from macOS by its `platform_system == 'Linux'` marker plus `--exclude-module systemd`; a test fails if that marker is ever removed.
  - **Still blocked on the founder** (see §7 of the strategy doc): approve the exception text; settle `LEG-CRIT-02` first, because the exception is only durable if future contributors are bound by it; confirm the App Store client stays a sandboxed remote companion; reconcile the bundle identifiers (`config/platforms.yml` says `ai.halbert.macos.free`, `tauri.conf.json` hard-codes `ai.halbert.dashboard` for every target).

- [x] **`LEG-CRIT-04`** `[sonnet]` **Autonomous Action Administrative Liability Waiver**
  - **Problem**: Halbert executes destructive system actions (editing `/etc/fstab`, stopping services, updating network configurations, modifying launchd daemons). While GPLv3 has general Section 15/16 disclaimers, a specialized operational disclaimer is required to protect maintainers against claims of production outages or data loss.
  - **Action**:
    1. Author `documentation/legal/DISCLAIMER.md`.
    2. Embed an administrative acknowledgment in first-run onboarding (CLI and GUI) requiring users to accept that they are solely responsible for testing proposed actions and keeping offline backups.

---

### 🟠 Major Priority (Required for Public Release & Distribution)

- [x] **`LEG-MAJ-01`** `[sonnet]` **Create Canonical `THIRD-PARTY-LICENSES.md`**
  - **Problem**: `data/manifest.json` line 207 references `THIRD-PARTY-LICENSES.txt`, but the file is missing from the repository.
  - **Action**:
    1. Author `documentation/legal/THIRD-PARTY-LICENSES.md` and copy to root distribution.
    2. Document upstream licenses for all 13 RAG data sources:
       - GNU FDL 1.3 (Arch Linux Wiki)
       - CC BY 4.0 (TLDR Pages)
       - BSD-2-Clause (Homebrew)
       - CC BY-SA 4.0 (Ask Different / Stack Exchange)
       - APSL 2.0 / BSD (macOS Man Pages)
       - FreeBSD Documentation License (FreeBSD Handbook & Man Pages)
       - Apache 2.0 / MIT (Vendor & Common System Docs)
    3. Document software dependencies: Python packages (`chromadb`, `sentence-transformers`, `fastapi`, `apscheduler`), Rust crates (`tauri`, `sysinfo`), and npm packages (`radix-ui`, `monaco-editor`, `xterm`).

- [x] **`LEG-MAJ-02`** `[sonnet]` **Create Zero-Telemetry Privacy Policy (`PRIVACY.md`)**
  - **Problem**: Halbert's primary competitive advantage is local data sovereignty, but there is no formal user-facing privacy statement for the website, CLI, or desktop app.
  - **Action**:
    1. Create `documentation/legal/PRIVACY.md`.
    2. Explicitly document:
       - 100% Local execution by default (Ollama/MLX).
       - Zero telemetry, analytics, or behavioral tracking collected or phoned home.
       - Vector database and autobiographical memory stored strictly on local disk (`~/.local/share/halbert`).
       - Clear delineation of what occurs when an optional Cloud API key (OpenAI/Anthropic/Google) is configured.

- [x] **`LEG-MAJ-03`** `[sonnet]` **HuggingFace RAG Dataset Publishing Compliance**
  - **Problem**: Publishing `halbert-rag-linux`, `halbert-rag-macos`, and `halbert-rag-eval` to HuggingFace requires explicit metadata cards matching upstream terms (especially CC BY-SA and GNU FDL).
  - **Action**:
    1. Update `scripts/upload_hf_dataset.py` to generate compliant `README.md` dataset cards with proper `license:` YAML tags and attribution lists.
    2. Ensure each dataset includes origin URLs and author acknowledgments in each JSONL record.

- [ ] **`LEG-MAJ-04`** `[founder]` **LemonSqueezy Commercial Terms & EULA (Halbert Pro)**
  - **Problem**: Distributing Halbert Pro as a paid product via LemonSqueezy requires Terms of Sale, an End User License Agreement (EULA), and Merchant of Record (MoR) disclosures.
  - **Action**:
    1. Draft standard Commercial EULA for Halbert Pro macOS binaries.
    2. Specify refund policies, license key activation rules (e.g. 3 devices per license), and support SLAs.

- [x] **`LEG-MAJ-05`** `[opus]` **Arch Wiki (GNU FDL 1.3) macOS Build Gate Validation**
  - **Problem**: Arch Wiki is licensed under GNU FDL 1.3 with copyleft terms. It is designated `mac_build: false` in `manifest.json`.
  - **Action**:
    1. Audit RAG build scripts (`scripts/scrape_macos.sh`, `scripts/build-linux.sh`) to verify that no Arch Wiki vectors leak into macOS index bundles.
    2. Add unit test asserting `data/linux/arch-wiki/` is completely excluded from macOS artifacts.
  - **Delivered (2026-08-25)**:
    - Audited every path that could put Arch content into a macOS artifact — build scripts, scrape scripts, `config/platforms.yml`, the runtime `PlatformDataLoader`, and the HuggingFace uploader. Results table in `documentation/legal/CORPUS-LICENSING-ARCHITECTURE.md` §4.
    - The exclusion is now enforced, not assumed: GFDL is classified `copyleft: strong` + `drm_conflict: true` in `config/licensing.yml`, so it fails the App Store channel on its own terms as well as on platform separation.
    - Tests assert exclusion from all three macOS channels, that a *planted* Arch file fails the audit, and that Arch still ships in the DRM-free `oss-linux` build (the exclusion is a property of the channel, not the content).
  - **Defects found and fixed while auditing**:
    - `data/manifest.json` marked three Linux-only sources (`linux_man_pages`, `linux_system_docs`, `vendor_and_distro_docs`) as `mac_build: true` although every one of their paths lives under `linux/`. Corrected; the engine now reports this class of inconsistency as an advisory.
    - `scripts/scrape_macos.sh:138` could not run at all — a redirection inside a `for` word list is a bash syntax error, present at `HEAD`. Fixed (this was the item flagged in §5.3).
    - `scripts/build-macos.sh` did not exist, so `LEG-CRIT-01`'s "update build-macos.sh" had nothing to update. Created.

- [x] **`LEG-MAJ-06`** `[fable]` **Implement DCO (`Signed-off-by`) in GitHub Workflow**
  - **Problem**: Contributions must have clear provenance.
  - **Action**:
    1. Add GitHub Actions DCO check (`probot/dco` or custom check) requiring all commits in PRs to carry `Signed-off-by: Name <email>`.
    2. Update `.github/PULL_REQUEST_TEMPLATE.md`.
  - **Status (2026-08-25, fable):** Done. `.github/workflows/dco.yml` checks out `pull_request.head.sha` with full history and runs `scripts/check-dco.sh <base> <head>`, which ranges from `merge-base`, requires the `Signed-off-by` name/email to match the commit author or committer, and skips merge and `[bot]` commits (same semantics as the probot DCO app). `.github/PULL_REQUEST_TEMPLATE.md` and CONTRIBUTING (commit-message section) tell contributors to use `git commit -s`. Covered by `tests/test_legal_metadata.py::test_check_dco_script_detects_missing_signoff`. See §5.2(1): the sign-off is a certification, not a licence grant.

---

### 🟡 Moderate Priority (Product Polish & Transparency)

- [x] **`LEG-MOD-01`** `[sonnet]` **Dashboard UI "About & Third-Party Notices" Modal**
  - **Problem**: Open source permissive licenses (MIT, BSD, Apache 2.0, CC BY) legally require that their copyright notices and license texts accompany the binary/web application.
  - **Action**:
    1. Add an "About / Legal Notices" section in the React dashboard settings.
    2. Fetch and render `THIRD-PARTY-LICENSES.md` or a structured JSON manifest directly within the UI.
    3. Ensure `WhyChip` renders source links for Stack Exchange (`CC BY-SA 4.0`) citations.

- [x] **`LEG-MOD-02`** `[sonnet]` **Cloud Provider Data Flow Disclosure & Consent**
  - **Problem**: When users switch from local Ollama/MLX to cloud models (Claude, GPT-4, Gemini), log snippets and system configurations leave the local machine.
  - **Action**:
    1. Add a visual confirmation dialog when enabling Cloud APIs: *"Enabling Cloud Models sends system logs and prompts to [Provider]. Do not enable on systems processing sensitive/restricted data."*
    2. Document OpenAI, Anthropic, and Google commercial terms in `guides/model-selection.md`.

- [x] **`LEG-MOD-03`** `[sonnet]` **Create Third-Party Trademark & Fair Use Notice (`TRADEMARKS.md`)**
  - **Problem**: Halbert frequently references Linux®, Ubuntu®, Apple®, macOS®, Apple Silicon®, Docker®, Kubernetes®, etc.
  - **Action**:
    1. Create `documentation/legal/TRADEMARKS.md`.
    2. Include standard non-affiliation and nominative fair use disclaimers.
    3. Add a condensed footer to `marketing/web/index.html`.

- [x] **`LEG-MOD-04`** `[fable]` **Meta Llama 3.1 & Foundation Model Attribution Notice**
  - **Problem**: The Meta Llama 3.1 Community License requires the user-facing notice *"Built with Llama"* (§1.b.i — the exact phrase, with no version number; the older Meta Llama 3 licence says *"Built with Meta Llama 3"*) from anyone who distributes the weights or a product that contains them.
  - **Action**:
    1. Add model attribution tags in the Model Catalog UI and CLI `info` command.
    2. Verify compliance with DeepSeek and Qwen license terms.
  - **Status (2026-08-25, fable):** Done. `halbert_core/halbert_core/model/attribution.py` is the single source of truth (family → licence name/id/URL, required display notice, NOTICE-file sentence, notes), verified against the licence texts. Wired into `halbert model-list-all`, `halbert model-router-status`, `halbert info`, `POST /api/llm/proxy/models` (`license`, `license_id`, `license_url`, `attribution` per model) and the model picker (`ModelCard.tsx` renders the licence link and the notice badge). `config/model-catalog.yml` and `THIRD-PARTY-LICENSES.md` §5 corrected: Llama 3.1 → "Built with Llama"; Qwen2.5-Coder-14B → Apache-2.0; the "Powered by DeepSeek/Qwen" notices were not required by any licence and were removed. `tests/test_model_attribution.py`.

- [x] **`LEG-MOD-05`** `[fable]` **CLI First-Run Banner Legal Notice (GPLv3 §5d Compliance)**
  - **Problem**: GPL-3.0 §5(d) expects interactive terminal tools to display copyright, warranty exclusion, and license inspection commands.
  - **Action**:
    1. Update `Halbert/main.py` CLI header to include:
       `Halbert (C) 2024-2026 Eric Bintner. Free software under GNU GPLv3; type 'halbert license' for details. ABSOLUTELY NO WARRANTY.`
    2. Add `halbert license` subcommand to output the license summary.
  - **Status (2026-08-25, fable):** Done. `halbert --version`, `halbert info`, and `python -m halbert_core.dashboard --version` (plus the dashboard startup log) print the GPLv3 appendix-style four-line notice (`LEGAL_NOTICE` in `halbert_core/__init__.py`: copyright, ABSOLUTELY NO WARRANTY, free to redistribute, how to view the licence). `halbert license` prints the summary, `--full` the verbatim GPLv3, `--third-party` the notices file. Covered by `tests/test_legal_metadata.py`. Note GPLv3 §5(d) only *requires* Appropriate Legal Notices where the interactive interface already displays them; this is the FSF-recommended practice rather than a strict obligation.

---

### 🟢 Minor Priority (Code Hygiene & Long-Term Maintenance)

- [x] **`LEG-MIN-01`** `[fable]` **Mass-Tag Source Files with SPDX Identifiers**
  - **Problem**: Inconsistent or missing file headers across Python, Rust, and TypeScript code.
  - **Action**:
    1. Add standard SPDX headers to all `.py`, `.rs`, `.ts`, and `.tsx` files:
       `// SPDX-License-Identifier: GPL-3.0-or-later` or `# SPDX-License-Identifier: GPL-3.0-or-later`.
  - **Status (2026-08-25, fable):** Done. `scripts/add_spdx_headers.py` tagged 579/579 tracked `.py/.rs/.ts/.tsx/.sh` files under `Halbert/`, `halbert_core/`, `scripts/`, `tests/`, `config/`, `packaging/` (header after shebang/coding line; REUSE 3.3 accepts the `Copyright (C)` form). `--check` runs in `tests/test_legal_metadata.py`, so untagged files fail CI. The 10 UI files derived from shadcn/ui keep `SPDX-License-Identifier: MIT` with the shadcn copyright (MIT notice retention) — listed in `THIRD-PARTY-LICENSES.md` §3.5.

- [x] **`LEG-MIN-02`** `[fable]` **Synchronize Copyright Notices Across Repository**
  - **Problem**: Some documentation files list different copyright dates or lack author names.
  - **Action**:
    1. Standardize all docs to: `Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors`.
  - **Status (2026-08-25, fable):** Done. Copyright line + `GPL-3.0-or-later` now declared in `halbert_core/__init__.py` (`__version__`, `__license__`, `__copyright__`), `halbert_core/pyproject.toml` (PEP 639 `license` string, `license-files`, `setuptools>=77`, authors), `src-tauri/Cargo.toml` (placeholders `"you"`/`"A Tauri App"` replaced; `license`), frontend `package.json` (`license`, `author`), `tauri.conf.json` (`bundle.copyright`, `bundle.license`), `LICENSE.md`, `README.md`, `documentation/README.md`, `documentation/legal/README.md`. `tests/test_legal_metadata.py` asserts version/licence consistency. Open: confirm the 2024 start year (first commit is 2025-12-08) — §5.2(5).

- [x] **`LEG-MIN-03`** `[sonnet]` **Upstream Scraper License Verification Harness**
  - **Problem**: Documentation URLs can change licensing terms upstream without notice.
  - **Action**:
    1. Add an upstream license check in `scripts/corpus_quality_gate.py` that verifies terms of scraped domains during the monthly CI/CD refresh.

- [x] **`LEG-MIN-04`** `[fable]` **Documentation Cross-Reference Audit**
  - **Problem**: References in docs to older license paths (e.g. `docs/Phase54_licensing-roundup/`) need updating to canonical paths in `documentation/legal/`.
  - **Action**:
    1. Update `data/manifest.json` and `README.md` to point to `documentation/legal/`.
  - **Status (2026-08-25, fable):** Done. `data/manifest.json`, `README.md`, `documentation/README.md`, `documentation/legal/README.md` (absolute `file:///Volumes/...` links → relative), `documentation/RAG-DATA-SOURCES-2026-08-24.md` ("missing artifact" note resolved), `documentation/DOCUMENTATION-PLAN.md` (legal tree + items 33/34), `CHANGELOG.md` (Unreleased entry). No `docs/Phase54_licensing-roundup/` or `THIRD-PARTY-LICENSES.txt` references remain outside this file; guarded by `test_no_stale_legal_paths_in_tracked_docs`.

---

## 4. Work Breakdown by Execution Tier

### 🧑‍💼 Founder Tasks (`[founder]`)
1. `LEG-CRIT-02`: Decide Contributor License Agreement / DCO strategy for dual-licensing.
2. `LEG-CRIT-03`: Approve Mac App Store GPLv3 Section 7 exception clause.
3. `LEG-MAJ-04`: Establish LemonSqueezy commercial pricing, refund terms, and EULA for Halbert Pro.

### 🧠 Opus Tasks (`[opus]`)
1. ✅ `LEG-CRIT-01`: Architect SS64 non-commercial quarantine and build-time exclusion pipeline. *(done 2026-08-25)*
2. ✅ `LEG-MAJ-05`: Implement and verify Arch Wiki (GNU FDL) build gate for macOS bundles. *(done 2026-08-25)*
3. ✅ `LEG-CRIT-03` (opus half): App Store distribution architecture + automated dependency copyleft gate. *(done 2026-08-25 — founder decision still outstanding)*

**Opus deliverables**

| Artefact | Purpose |
|----------|---------|
| `config/licensing.yml` | Licence registry + per-channel distribution policy |
| `config/dependency-licenses.yml` | Third-party dependency licence register |
| `halbert_core/halbert_core/corpus/license_policy.py` | Policy engine (path + record level) |
| `scripts/corpus_license_gate.py` | Build-time corpus gate; non-zero exit blocks the build |
| `scripts/check_appstore_deps.py` | Dependency copyleft gate for the App Store target |
| `scripts/quarantine_ss64.py` | Idempotent CC BY-NC splitter |
| `scripts/generate_macos_command_guides.py` + `scripts/macos_command_data.py` | 87 Halbert-authored replacement references |
| `scripts/build-macos.sh` | Channel-aware macOS build, gated twice |
| `halbert_core/tests/test_corpus_license_gate.py` | 51 tests, mostly planted-violation negatives |
| `documentation/legal/CORPUS-LICENSING-ARCHITECTURE.md` | Corpus licensing architecture + audit results |
| `documentation/legal/APP-STORE-DISTRIBUTION-STRATEGY.md` | GPLv3 §7 exception strategy + open-core boundary |

### ✍️ Sonnet Tasks (`[sonnet]`)
1. `LEG-CRIT-04`: Draft `documentation/legal/DISCLAIMER.md`.
2. `LEG-MAJ-01`: Author `documentation/legal/THIRD-PARTY-LICENSES.md`.
3. `LEG-MAJ-02`: Author `documentation/legal/PRIVACY.md`.
4. `LEG-MAJ-03`: Author HuggingFace dataset license cards and upload templates.
5. `LEG-MOD-01`: Implement React Dashboard UI "About & Licenses" modal.
6. `LEG-MOD-02`: Implement Cloud API privacy disclosure modal in frontend.
7. `LEG-MOD-03`: Draft `documentation/legal/TRADEMARKS.md`.
8. `LEG-MIN-03`: Implement scraper license verification harness in quality gate.

### ⚙️ Fable Tasks (`[fable]`) — all complete 2026-08-25
1. ✅ `LEG-MAJ-06`: DCO workflow check (`scripts/check-dco.sh` + `.github/workflows/dco.yml`) and PR template.
2. ✅ `LEG-MOD-04`: Foundation-model attribution (`halbert_core/model/attribution.py` → CLI, API, model picker).
3. ✅ `LEG-MOD-05`: CLI legal notices (`--version`, `info`, `license [--full|--third-party]`, dashboard `--version`).
4. ✅ `LEG-MIN-01`: SPDX headers on all 579 first-party source files (`scripts/add_spdx_headers.py --check`).
5. ✅ `LEG-MIN-02`: Copyright + `GPL-3.0-or-later` synchronized across package manifests and docs.
6. ✅ `LEG-MIN-04`: Legal cross-references updated; stale paths guarded by a test.

---

## 5. Fable Review — 2026-08-25 (second pass)

Reviewed the initial fable pass, verified the licence facts against primary
sources (Meta Llama 2 / 3 / 3.1 / 3.2 / 3.3 licence texts and the licence
blobs Ollama ships, Qwen / DeepSeek / Mistral / Nomic model cards and LICENSE
files, GPLv3 §0 / §5(d) / appendix, developercertificate.org, the probot DCO
app source, the Tauri v2 config schema, PEP 639 + setuptools 84, REUSE 3.3,
shadcn/ui LICENSE.md), and completed every `[fable]` item above.

Verification run: `pytest tests/test_legal_metadata.py tests/test_model_attribution.py
tests/test_cli_smoke.py` (43 passed), `scripts/add_spdx_headers.py --check`
(579/579), frontend `tsc --noEmit` (clean), `cargo metadata` (Cargo.toml valid),
`python -m halbert_core.dashboard --version`, `halbert --version|info|license`.

### 5.1 Corrections to the initial pass

| Item | Initial pass | Corrected | Primary source |
| :--- | :--- | :--- | :--- |
| LEG-MOD-04 | `attribution: "Built with Meta Llama 3.1"` (catalog); `"Built with Llama 3.1."` (THIRD-PARTY §5) | **"Built with Llama"** — Llama 3.1 / 3.2 / 3.3 §1.b.i require exactly this phrase; only the older Meta Llama 3 licence uses "Built with Meta Llama 3" | llama.com/llama3_1/license (identical clause in 3.2, 3.3) |
| LEG-MOD-04 | "Powered by DeepSeek." / "Powered by Qwen." listed as *required* notices | Removed — no DeepSeek or Qwen licence contains any display-notice requirement | DeepSeek LICENSE-MODEL v1.0; Qwen Apache-2.0 / Qwen License / Qwen Research License texts |
| LEG-MOD-04 | Qwen2.5-Coder-14B: "Apache-2.0 / Qwen Community License" | Apache-2.0 (only the 3B size is Qwen Research License; Qwen2.5-72B is the Qwen License Agreement) | HF `Qwen/Qwen2.5-Coder-14B-Instruct` LICENSE |
| LEG-MOD-04 | `deepseek-r1:70b` treated as plain MIT | MIT **and** Llama 3.3 Community License — it is distilled from Llama-3.3-70B-Instruct, so "Built with Llama" applies | HF `deepseek-ai/DeepSeek-R1-Distill-Llama-70B` |
| LEG-MOD-04 | Code Llama: "CodeLlama by Meta AI" as attribution | No display notice under the Llama 2 Community License; only a NOTICE-file sentence when weights are distributed | ai.meta.com/llama/license |
| LEG-MAJ-06 | Workflow ranged `origin/$base_ref..HEAD` against the synthetic merge commit, accepted any `Signed-off-by` text, mis-labelled checkout step | Checks out `pull_request.head.sha` with full history; `merge-base(base, head)..head`; sign-off must match author or committer; merge + `[bot]` commits skipped; logic in `scripts/check-dco.sh` (runs locally, tested) | github.com/apps/dco; actions/checkout README |
| LEG-MOD-05 | `info` / `license` only; licence read from LICENSE.md | + `--version` on both CLIs, `license --third-party`, dashboard startup notice; four-line notice wording from the GPLv3 appendix | gnu.org/licenses/gpl-3.0.txt |
| LEG-MIN-01 | 3 / 579 files tagged | 579 / 579 with an idempotent tool + CI check; shadcn/ui-derived files keep MIT | REUSE 3.3; shadcn LICENSE.md (MIT) |
| LEG-MIN-02 | Placeholders (`authors = ["you"]`, "A Tauri App", "Halbert Team"), no licence field in any manifest, LICENSE.md linked `GPL-3.0-only` while headers said `-or-later` | `GPL-3.0-or-later` + copyright everywhere; PEP 639 `license` string + `license-files`; Tauri `bundle.copyright` / `bundle.license` (no `licenseFile`: it becomes a DMG/NSIS click-through EULA, which GPLv3 §9 says is not needed) | PEP 639; setuptools 84; Tauri v2 schema |
| LEG-MIN-04 | manifest only | README, docs index, legal hub (absolute `file:///Volumes/...` links → relative), RAG data-sources note, documentation plan, changelog | — |

### 5.2 Facts that change the plan — founder attention

1. **LEG-CRIT-02 — a DCO sign-off is not a licence grant.** DCO 1.1 only
   certifies provenance ("I have the right to submit it under the open source
   license indicated in the file"); it contains no words of grant. The
   "Dual-Licensing & Commercial Permission Grant" that CONTRIBUTING.md §2
   attaches to the `Signed-off-by` trailer therefore does not give the
   maintainer relicensing or App-Store-exception rights over third-party
   contributions. Options: (a) add a real CLA with an assent step (CLA
   Assistant / EasyCLA) alongside the DCO; (b) stay DCO-only and accept that
   the GPLv3 §7 App Store exception can only be granted for Eric Bintner's own
   copyright, so third-party code in the App Store target needs per-contributor
   permission. Until decided, CONTRIBUTING §2–3 is a statement of intent, not a
   binding grant. (Also: `LEG-CRIT-02` / `LEG-CRIT-03` are still unchecked
   above even though CONTRIBUTING already contains the exception text.)
2. **Llama notices bind distributors, not recommenders.** Llama 3.x §1.b.i
   triggers on distributing the weights, a derivative, or a product that
   *contains* them; recommending a model the user pulls via Ollama does not.
   Halbert shows "Built with Llama" anyway (courtesy + Pro-readiness). A
   Halbert Pro build that bundles Llama weights must also ship a copy of the
   Agreement and the per-version NOTICE sentence (`notice_file_sentence` in
   `attribution.py`). The older Meta Llama 3 licence has a broader trigger ("a
   product or service that *uses* any of them") and a no-improve-other-LLM
   clause — consider dropping `llama3-8b` from the catalog (already marked
   superseded).
3. **Llama 3.2 vision + EU.** The restriction is in the Llama 3.2 *Acceptable
   Use Policy*, not the licence; it bars EU-domiciled licensees, not end users
   of products that incorporate the model. Only matters if Halbert Pro bundles
   `llama3.2-vision`.
4. **Outbound licence id.** This plan, the initial pass and CONTRIBUTING use
   `GPL-3.0-or-later`; README / LICENSE.md said bare "GPL-3.0" (deprecated
   SPDX id, meaning `-only`). Everything now says `-or-later` — confirm.
5. **Copyright years.** "2024-2026" is used throughout per this plan; the
   repo's first commit is 2025-12-08. Confirm 2024 (prior Cerebric / LinuxBrain
   history) or change to 2025 in one place: `COPYRIGHT` in
   `scripts/add_spdx_headers.py` + `halbert_core/__init__.py`, then re-run.
6. **shadcn/ui files stay MIT.** Ten UI primitives derived from shadcn/ui carry
   `SPDX-License-Identifier: MIT` with the shadcn copyright (MIT requires the
   notice to be retained; MIT is GPL-compatible). Halbert's edits to those files
   are therefore MIT too.
7. **Wheel licence file.** PEP 639 forbids `..` in `license-files`, so
   `halbert_core/LICENSE` is a copy of the root `LICENSE`. Keep them identical.

### 5.3 Defects found in files owned by other active sessions (not edited)

- `halbert_core/halbert_core/dashboard/routes/legal.py` `_FOUNDATION_MODELS`:
  "Built with Llama 3.1.", "Powered by DeepSeek.", "Powered by Qwen." are wrong
  (§5.1). Replace the hard-coded list with
  `halbert_core.model.attribution.FOUNDATION_MODEL_LICENSES` / `as_dict()` so
  the About panel, the API and the CLI cannot drift. (LEG-MOD-01 owner)
- `config/models.yml`: `qwen3-v1:32b` is not an Ollama tag — probably
  `qwen3-vl:32b` (Apache-2.0).
- `config/model-catalog.yml`: `llama3.1:8b-instruct` and `llama3:8b-instruct`
  do not exist on the Ollama registry (404 MANIFEST_UNKNOWN); the registry has
  `llama3.1:8b` and suffixed `…:8b-instruct-q4_K_M` tags. The catalog is also
  not read by any code path. Left as-is — product decision.
- ~~`scripts/scrape_macos.sh:138`: `for jsonl in "${source_file}"*.jsonl 2>/dev/null; do`
  is a bash syntax error (a redirection on a `for` word list); the script
  cannot run.~~ **Fixed 2026-08-25** (LEG-MAJ-05). The script also now runs
  `scripts/quarantine_ss64.py` after the SS64 scrape, which otherwise
  re-populated the shippable corpus with CC BY-NC content on every run.
- `Halbert/main.py`: every `model-*` / `persona-*` command prints "… not
  available" in this venv because the single top-level `try:` import block
  soft-fails as a whole; the attribution output was verified by calling
  `_print_model_attribution` directly. Pre-existing.

### 5.4 Open questions the research could not settle

- Whether a product that runs `ollama pull` on the user's behalf (onboarding)
  "makes available" Llama Materials under §1.b.i. Conservative reading: the
  notices are already shown, so nothing changes unless weights are bundled.
- Whether `github.event.pull_request.base.sha` is refreshed on `synchronize`
  events; the workflow avoids the question by using `merge-base` against
  `origin/<base branch>`.
