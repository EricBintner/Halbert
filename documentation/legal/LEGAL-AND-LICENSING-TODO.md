# Halbert Legal, Licensing & Compliance Action Plan

**Date:** 2026-08-25  
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

- [ ] **`LEG-CRIT-01`** `[opus]` **SS64 Non-Commercial (`CC BY-NC 4.0`) Dataset Quarantine**
  - **Problem**: SS64 macOS command references (`data/macos/support/macos_support.jsonl` slice) carry `CC BY-NC 4.0` (Non-Commercial). Including this in any commercial distribution (Halbert Pro on LemonSqueezy or Mac App Store) constitutes direct copyright infringement.
  - **Action**:
    1. Separate SS64 items into `data/non-commercial/macos_ss64/`.
    2. Expand Halbert-authored synthetic guides to provide 100% replacement coverage for macOS command syntax.
    3. Update `scripts/build-macos.sh` and packaging scripts to enforce an automated assertion preventing `CC-BY-NC` data from entering commercial release bundles.

- [ ] **`LEG-CRIT-02`** `[founder]` **Contributor License Agreement (CLA) & Dual-Licensing Rights**
  - **Problem**: `CONTRIBUTING.md` currently enforces inbound=outbound GPL-3.0 without a relicensing grant. If external developers contribute without an agreement, the copyright is fragmented, legally blocking the founder from ever releasing commercial builds (Halbert Pro) or adding Mac App Store exceptions without 100% contributor approval.
  - **Action**:
    1. Decide between a lightweight **Developer Certificate of Origin (DCO)** with commercial relicensing grant vs. a full **Contributor License Agreement (CLA)**.
    2. Formalize that Halbert Core remains GPL-3.0, but the project maintainer retains rights to distribute binaries across proprietary marketplaces (App Store, LemonSqueezy) with appropriate exceptions.
    3. Update `documentation/contributing/CONTRIBUTING.md` and repository PR templates.

- [ ] **`LEG-CRIT-03`** `[founder]` + `[opus]` **GPL-3.0 vs. Mac App Store Conflict Strategy**
  - **Problem**: Apple Mac App Store DRM and Sandbox terms conflict with GPL-3.0 Section 6 (Installation Information) and Section 10 (prohibition against further restrictions).
  - **Action**:
    1. Adopt the dual-licensing / GPLv3 exception model (under GPLv3 Section 7) for the App Store companion client:
       > *"As a special exception, the copyright holders of Halbert grant permission to convey the object code of this work through the Apple Mac App Store notwithstanding Sections 6 and 10 of GPLv3."*
    2. Ensure no third-party GPLv3/copyleft libraries (which lack this exception) are statically linked into the Mac App Store binary target.

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

- [ ] **`LEG-MAJ-05`** `[opus]` **Arch Wiki (GNU FDL 1.3) macOS Build Gate Validation**
  - **Problem**: Arch Wiki is licensed under GNU FDL 1.3 with copyleft terms. It is designated `mac_build: false` in `manifest.json`.
  - **Action**:
    1. Audit RAG build scripts (`scripts/scrape_macos.sh`, `scripts/build-linux.sh`) to verify that no Arch Wiki vectors leak into macOS index bundles.
    2. Add unit test asserting `data/linux/arch-wiki/` is completely excluded from macOS artifacts.

- [ ] **`LEG-MAJ-06`** `[fable]` **Implement DCO (`Signed-off-by`) in GitHub Workflow**
  - **Problem**: Contributions must have clear provenance.
  - **Action**:
    1. Add GitHub Actions DCO check (`probot/dco` or custom check) requiring all commits in PRs to carry `Signed-off-by: Name <email>`.
    2. Update `.github/PULL_REQUEST_TEMPLATE.md`.

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

- [ ] **`LEG-MOD-04`** `[fable]` **Meta Llama 3.1 & Foundation Model Attribution Notice**
  - **Problem**: The Meta Llama 3.1 Community License requires user-facing notice: *"Built with Llama 3.1"*.
  - **Action**:
    1. Add model attribution tags in the Model Catalog UI and CLI `info` command.
    2. Verify compliance with DeepSeek and Qwen license terms.

- [ ] **`LEG-MOD-05`** `[fable]` **CLI First-Run Banner Legal Notice (GPLv3 §5d Compliance)**
  - **Problem**: GPL-3.0 §5(d) expects interactive terminal tools to display copyright, warranty exclusion, and license inspection commands.
  - **Action**:
    1. Update `Halbert/main.py` CLI header to include:
       `Halbert (C) 2024-2026 Eric Bintner. Free software under GNU GPLv3; type 'halbert license' for details. ABSOLUTELY NO WARRANTY.`
    2. Add `halbert license` subcommand to output the license summary.

---

### 🟢 Minor Priority (Code Hygiene & Long-Term Maintenance)

- [ ] **`LEG-MIN-01`** `[fable]` **Mass-Tag Source Files with SPDX Identifiers**
  - **Problem**: Inconsistent or missing file headers across Python, Rust, and TypeScript code.
  - **Action**:
    1. Add standard SPDX headers to all `.py`, `.rs`, `.ts`, and `.tsx` files:
       `// SPDX-License-Identifier: GPL-3.0-or-later` or `# SPDX-License-Identifier: GPL-3.0-or-later`.

- [ ] **`LEG-MIN-02`** `[fable]` **Synchronize Copyright Notices Across Repository**
  - **Problem**: Some documentation files list different copyright dates or lack author names.
  - **Action**:
    1. Standardize all docs to: `Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors`.

- [x] **`LEG-MIN-03`** `[sonnet]` **Upstream Scraper License Verification Harness**
  - **Problem**: Documentation URLs can change licensing terms upstream without notice.
  - **Action**:
    1. Add an upstream license check in `scripts/corpus_quality_gate.py` that verifies terms of scraped domains during the monthly CI/CD refresh.

- [ ] **`LEG-MIN-04`** `[fable]` **Documentation Cross-Reference Audit**
  - **Problem**: References in docs to older license paths (e.g. `docs/Phase54_licensing-roundup/`) need updating to canonical paths in `documentation/legal/`.
  - **Action**:
    1. Update `data/manifest.json` and `README.md` to point to `documentation/legal/`.

---

## 4. Work Breakdown by Execution Tier

### 🧑‍💼 Founder Tasks (`[founder]`)
1. `LEG-CRIT-02`: Decide Contributor License Agreement / DCO strategy for dual-licensing.
2. `LEG-CRIT-03`: Approve Mac App Store GPLv3 Section 7 exception clause.
3. `LEG-MAJ-04`: Establish LemonSqueezy commercial pricing, refund terms, and EULA for Halbert Pro.

### 🧠 Opus Tasks (`[opus]`)
1. `LEG-CRIT-01`: Architect SS64 non-commercial quarantine and build-time exclusion pipeline.
2. `LEG-MAJ-05`: Implement and verify Arch Wiki (GNU FDL) build gate for macOS bundles.

### ✍️ Sonnet Tasks (`[sonnet]`)
1. `LEG-CRIT-04`: Draft `documentation/legal/DISCLAIMER.md`.
2. `LEG-MAJ-01`: Author `documentation/legal/THIRD-PARTY-LICENSES.md`.
3. `LEG-MAJ-02`: Author `documentation/legal/PRIVACY.md`.
4. `LEG-MAJ-03`: Author HuggingFace dataset license cards and upload templates.
5. `LEG-MOD-01`: Implement React Dashboard UI "About & Licenses" modal.
6. `LEG-MOD-02`: Implement Cloud API privacy disclosure modal in frontend.
7. `LEG-MOD-03`: Draft `documentation/legal/TRADEMARKS.md`.
8. `LEG-MIN-03`: Implement scraper license verification harness in quality gate.

### ⚙️ Fable Tasks (`[fable]`)
1. `LEG-MAJ-06`: Set up DCO workflow check and PR template.
2. `LEG-MOD-04`: Add Meta Llama 3.1 attribution badges in Model Catalog.
3. `LEG-MOD-05`: Add interactive CLI legal notices in `Halbert/main.py`.
4. `LEG-MIN-01`: Apply SPDX headers across `halbert_core/`, `Halbert/`, `src-tauri/`, and `frontend/`.
5. `LEG-MIN-02`: Synchronize copyright years across all documentation.
6. `LEG-MIN-04`: Update cross-references in `data/manifest.json` to point to `documentation/legal/`.
