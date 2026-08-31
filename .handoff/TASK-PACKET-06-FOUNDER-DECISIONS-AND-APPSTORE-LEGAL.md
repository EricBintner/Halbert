# Task Packet 06: Executive Decisions, Legal DCO & App Store Distribution

**Target Model:** **GLM-5.3 high** for drafting (reassigned 2026-08-30; Batch U5) — **but FDR-DEC-01…04 are founder decisions; no model closes them.** AI drafts the text, the founder approves and commits.
**Domain:** Open-Core Commercial Strategy, GPLv3 + App Store §7 Exception, DCO Policy, and Packaging Architecture  
**Target Date:** 2026-08-29  
**Status:** Ready for Executive Decision Formulation & Legal Drafting  
**Erratum (verified 2026-08-30):** Task 6.3's file path `src-tauri/tauri.conf.json` (repo root) **does not exist** — the actual Tauri config is `halbert_core/halbert_core/dashboard/frontend/src-tauri/tauri.conf.json`.  
**Governing Documents:**
- [`FOUNDER-TODO.md`](file:///Volumes/4TB-BAD/Halbert/FOUNDER-TODO.md)
- [`documentation/legal/OPEN-CORE-AND-DISTRIBUTION-STRATEGY.md`](file:///Volumes/4TB-BAD/Halbert/documentation/legal/OPEN-CORE-AND-DISTRIBUTION-STRATEGY.md)
- [`documentation/legal/APP-STORE-DISTRIBUTION-STRATEGY.md`](file:///Volumes/4TB-BAD/Halbert/documentation/legal/APP-STORE-DISTRIBUTION-STRATEGY.md)

---

## 1. Executive Summary & Objective

Halbert is poised to launch across dual distribution channels: a self-hosted GPLv3 backend + Home Assistant add-on, a free Apple Mac App Store menu bar companion (`ai.halbert.home`), and a paid direct commercial desktop edition (`ai.halbert.pro`).

Before opening public repositories or accepting external pull requests, four critical executive decisions (`FDR-DEC-01` through `FDR-DEC-04`) must be formalized and committed to prevent copyright fragmentation and store rejection.

---

## 2. Detailed Task Breakdown & Drafting Directives

### Task 6.1: Formalize DCO Language in `CONTRIBUTING.md` (`FDR-DEC-01`)
- **File:** [`documentation/contributing/CONTRIBUTING.md`](file:///Volumes/4TB-BAD/Halbert/documentation/contributing/CONTRIBUTING.md)
  1. Add a mandatory Developer Certificate of Origin (DCO 1.1) clause.
  2. Include explicit sub-clause granting project maintainers (Eric Bintner / Magnetic Anomaly LLC) the perpetual, non-exclusive right to distribute binary releases under commercial, App Store, or multi-licensed channels with GPLv3 §7 exceptions.
  3. Ensure contributors agree via Git `Signed-off-by:` trailers.

### Task 6.2: Commit GPLv3 §7 Exception & SPDX Headers (`FDR-DEC-02`)
- **Files:**
  - Create `LICENSE-EXCEPTION-APPSTORE` in repo root.
  - Text to commit (per [`APP-STORE-DISTRIBUTION-STRATEGY.md`](file:///Volumes/4TB-BAD/Halbert/documentation/legal/APP-STORE-DISTRIBUTION-STRATEGY.md) §2.1):
    ```
    Additional permission under GNU GPL version 3 section 7:
    If you modify this Program, or any covered work, by linking or combining it with
    Apple Inc.'s proprietary App Store libraries, DRM, and frameworks (or a modified version
    of those libraries), the licensors of this Program grant you additional permission to
    convey the resulting work under terms of your choice.
    ```
  - Standardize source code SPDX headers to:
    `SPDX-License-Identifier: GPL-3.0-or-later WITH MacAppStore-Exception`

### Task 6.3: Lock Bundle Identifiers & Packaging Namespaces (`FDR-DEC-03`)
- **File:** [`src-tauri/tauri.conf.json`](file:///Volumes/4TB-BAD/Halbert/src-tauri/tauri.conf.json)
  1. Configure multi-target bundle identifiers:
     - `ai.halbert.home` (Free Mac App Store companion with App Sandbox enabled)
     - `ai.halbert.pro` (Paid Direct DMG with Hardened Runtime & Sparkle auto-updates)
  2. Validate entitlement files in `src-tauri/entitlements.mas.plist` and `src-tauri/entitlements.mac.plist`.

### Task 6.4: Finalize Pricing & Ed25519 License Architecture (`FDR-DEC-04`)
- **File:** `documentation/legal/HALBERT-PRO-COMMERCIAL-TERMS.md`
  1. Document Halbert Pro pricing: **$29 one-time perpetual** ($24 launch promo) for lifetime application use + 12 months update window.
  2. Specify offline Ed25519 cryptographic keypair verification (public key hardcoded in binary, private key secured on merchant webhook server).

---

## 3. Executive Checklist for Founder Action

- [ ] Commit `CONTRIBUTING.md` with DCO commercial rights language.
- [ ] Commit `LICENSE-EXCEPTION-APPSTORE`.
- [ ] Set up Apple Developer Program certificates (`Mac App Store` profile & `Developer ID Application`).
- [ ] Set up Lemon Squeezy product entry for Halbert Pro with Ed25519 webhook.
- [ ] Create public GitHub repo `EricBintner/halbert-ha-addon`.
