# Halbert Legal, Licensing & Compliance Hub

This directory contains the canonical legal, licensing, compliance, and governance documentation for Halbert.

Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors. Halbert is free software under the GNU General Public License v3.0 or later (`GPL-3.0-or-later`); the full text is in the repository root [`LICENSE`](../../LICENSE).

---

## Documents

| Document | Purpose | Status |
| :--- | :--- | :--- |
| [**`LICENSE.md`**](./LICENSE.md) | Project license summary (GPL-3.0-or-later), header conventions, and rationale | ✅ Active |
| [**`THIRD-PARTY-LICENSES.md`**](./THIRD-PARTY-LICENSES.md) | Attribution and notices for all 13 RAG data sources, software dependencies, derived source files, and foundation models | ✅ Active |
| [**`PRIVACY.md`**](./PRIVACY.md) | Formal zero-telemetry, local-first data sovereignty statement | ✅ Active |
| [**`TERMS.md`**](./TERMS.md) | Website Terms of Service, early access beta rules, and liability disclaimers | ✅ Active |
| [**`DISCLAIMER.md`**](./DISCLAIMER.md) | Autonomous action administrative liability waiver and operational risk notice | ✅ Active |
| [**`TRADEMARKS.md`**](./TRADEMARKS.md) | Third-party brand acknowledgments and non-affiliation disclaimers | ✅ Active |
| [**`SECURITY.md`**](./SECURITY.md) | Security vulnerability disclosure, security model, and trust boundaries | ✅ Active |
| [**`LEGAL-AND-LICENSING-TODO.md`**](./LEGAL-AND-LICENSING-TODO.md) | Prioritized compliance action plan (Critical → Minor) with role tags | ✅ Active |

Related, outside this directory:

- [`../contributing/CONTRIBUTING.md`](../contributing/CONTRIBUTING.md) — DCO sign-off and contributor licensing terms
- [`../../.github/workflows/dco.yml`](../../.github/workflows/dco.yml) / [`../../scripts/check-dco.sh`](../../scripts/check-dco.sh) — DCO enforcement
- [`../../scripts/add_spdx_headers.py`](../../scripts/add_spdx_headers.py) — SPDX header tagging and `--check`
- [`../../config/licensing.yml`](../../config/licensing.yml) — machine-enforced corpus/distribution licensing policy
- [`../../data/manifest.json`](../../data/manifest.json) — per-source corpus licenses and build flags
- `halbert_core/halbert_core/model/attribution.py` — foundation-model license and attribution notices

## In the Program

- `halbert --version`, `halbert info` — GPLv3 §5(d) legal notice
- `halbert license` (`--full`, `--third-party`) — license summary, verbatim GPLv3 text, third-party notices
- `halbert model-list-all` / `halbert model-router-status` — per-model license and attribution notice
- Dashboard → Settings → About / Legal Notices — rendered from `GET /api/legal/notices`

---

## Core Principles

1. **Copyleft & Open Ecosystem**: The core engine is licensed under the **GNU General Public License v3.0 or later** to enforce perpetual openness and protect against closed-source forks.
2. **Local Data Sovereignty**: Halbert operates local-first by default with zero analytics, telemetry, or third-party behavioral tracking.
3. **Transparent Provenance**: All knowledge retrieved through the RAG pipeline preserves source URLs, upstream licenses, and attribution.
4. **Safety-First Autonomy**: High-risk administrative actions are gated by human approval, dry-run previews, and atomic rollback guarantees.
