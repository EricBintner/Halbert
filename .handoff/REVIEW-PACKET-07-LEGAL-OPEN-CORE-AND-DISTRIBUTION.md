# Review Packet 07: Product Strategy, Legal/Licensing Architecture & Open-Core Commercialization

**Review Level:** **GLM-5.3 high (drafts) + founder sign-off (reassigned 2026-08-30)**  
**Domain:** Open-Core Business Strategy, GPLv3 + App Store §7 Exception, Corpus Licensing, Distribution Channels, and Founder Decision Matrix  
**Target Date:** 2026-08-29  
**Status:** Ready for Strategic Legal & Product Synthesis Review  

---

## 1. Executive Summary & Review Scope

Halbert is transitioning from a private development project into a dual-distribution open-core commercial ecosystem. Over the past two weeks, a comprehensive legal and distribution architecture was formulated to reconcile copyleft open-source software (GPLv3) with the restrictive requirements of the Apple Mac App Store, Home Assistant Add-on ecosystem, and a commercial paid desktop edition (Halbert Pro).

Key strategic documents and architectures created:
1. **Open-Core & Distribution Strategy:** Definition of three distinct distribution tiers:
   - *Tier 1 (OSS Self-Hosted Backend):* GPLv3 pure daemon for Linux and Home Assistant OS.
   - *Tier 2 (Free "Halbert Home" App Store Companion):* Sandboxed macOS GUI with GPLv3 §7 App Store exception (`ai.halbert.home`).
   - *Tier 3 (Paid "Halbert Pro" Direct Edition):* Unsandboxed $29 perpetual license with offline Ed25519 activation and multi-node management (`ai.halbert.pro`).
2. **Corpus Licensing Architecture:** Legal categorization and attribution audit across documentation, RAG data sources, scrapers, and third-party dependencies.
3. **Founder Decision Matrix (`FOUNDER-TODO.md`):** Executive decision tree covering Developer Certificate of Origin (DCO) formalization, pricing, and infrastructure provisioning.

The reviewing model (**GLM-5.3**, drafting; founder signs off) must perform a high-level strategic review of this legal framework, verify GPLv3 §7 compliance against Apple Developer Agreement terms, ensure DCO terms protect project copyright integrity, and validate the pricing and release roadmap.

---

## 2. Planning & Strategy Documents (Past 2 Weeks)

| Document | Purpose | Key Themes |
|---|---|---|
| [`documentation/legal/OPEN-CORE-AND-DISTRIBUTION-STRATEGY.md`](file:///Volumes/4TB-BAD/Halbert/documentation/legal/OPEN-CORE-AND-DISTRIBUTION-STRATEGY.md) | Governing open-core commercial strategy | 3-tier distribution, monetization model, commercial rights |
| [`documentation/legal/APP-STORE-DISTRIBUTION-STRATEGY.md`](file:///Volumes/4TB-BAD/Halbert/documentation/legal/APP-STORE-DISTRIBUTION-STRATEGY.md) | Mac App Store legal compatibility | GPLv3 §7 additional permission clause, sandbox compliance |
| [`documentation/legal/CORPUS-LICENSING-ARCHITECTURE.md`](file:///Volumes/4TB-BAD/Halbert/documentation/legal/CORPUS-LICENSING-ARCHITECTURE.md) | Dataset and knowledge licensing | Scraped data rights, attribution notices, SPDX metadata |
| [`documentation/legal/LEGAL-AND-LICENSING-TODO.md`](file:///Volumes/4TB-BAD/Halbert/documentation/legal/LEGAL-AND-LICENSING-TODO.md) | Legal compliance task list | Action items for trademark, privacy, terms, and third-party notices |
| [`FOUNDER-TODO.md`](file:///Volumes/4TB-BAD/Halbert/FOUNDER-TODO.md) | Living executive action checklist | Executive decisions (`FDR-DEC-01` to `FDR-DEC-04`), accounts & milestones |
| [`.handoff/FABLE-HANDOFF-LEGAL-AND-LICENSING-2026-08-25.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/FABLE-HANDOFF-LEGAL-AND-LICENSING-2026-08-25.md) | Initial legal review handoff | Previous review findings and SPDX audit baseline |

---

## 3. Key Files & Strategy Components

- **Legal Framework Suite:**
  - [`documentation/legal/LICENSE.md`](file:///Volumes/4TB-BAD/Halbert/documentation/legal/LICENSE.md) (GPLv3 base)
  - [`documentation/legal/PRIVACY.md`](file:///Volumes/4TB-BAD/Halbert/documentation/legal/PRIVACY.md) (Local-first privacy commitment)
  - [`documentation/legal/TERMS.md`](file:///Volumes/4TB-BAD/Halbert/documentation/legal/TERMS.md) (Standard end-user terms)
  - [`documentation/legal/THIRD-PARTY-LICENSES.md`](file:///Volumes/4TB-BAD/Halbert/documentation/legal/THIRD-PARTY-LICENSES.md) (Dependency attributions)
  - [`documentation/legal/TRADEMARKS.md`](file:///Volumes/4TB-BAD/Halbert/documentation/legal/TRADEMARKS.md) (Halbert name and mark policy)
- **Packaging & Build Automation:**
  - [`scripts/build-macos.sh`](file:///Volumes/4TB-BAD/Halbert/scripts/build-macos.sh) (Multi-channel build script)
  - [`src-tauri/tauri.conf.json`](file:///Volumes/4TB-BAD/Halbert/src-tauri/tauri.conf.json) (App bundle metadata and capabilities)

---

## 4. Incomplete Decisions & Open Action Items (from `FOUNDER-TODO.md`)

1. **`FDR-DEC-01` DCO Relicensing Language:** Update `documentation/contributing/CONTRIBUTING.md` with explicit Developer Certificate of Origin language granting the maintainer rights to distribute across proprietary channels.
2. **`FDR-DEC-02` GPLv3 §7 Exception Approval:** Commit `LICENSE-EXCEPTION-APPSTORE` and add SPDX identifier `GPL-3.0-or-later WITH MacAppStore-Exception` to source headers.
3. **`FDR-DEC-03` Bundle Identifier Alignment:** Confirm namespaces (`ai.halbert.home` vs `ai.halbert.pro` vs `ai.halbert.dashboard`).
4. **`FDR-DEC-04` Pricing Terms:** Finalize Halbert Pro pricing ($29 perpetual, 12 months updates, no recurring subscription).
5. **Infrastructure Setup:** Provision Apple Developer Program certificates, Lemon Squeezy merchant account, and public GitHub repository `EricBintner/halbert-ha-addon`.

---

## 5. Review Directives for Opus

- **Copyleft / App Store Interoperability:** Review the exact GPLv3 §7 additional permissions clause in `APP-STORE-DISTRIBUTION-STRATEGY.md`. Confirm that it legally shields the project maintainer and end-users from GPL enforcement conflicts caused by Apple's FairPlay DRM.
- **Copyright Cohesion via DCO:** Verify that the proposed DCO contribution policy adequately protects commercial dual-licensing rights without requiring a full copyright assignment (CLA).
- **Go-To-Market Coherence:** Evaluate the multi-channel launch roadmap across Home Assistant community, Reddit, Hacker News, and the `halbert.dev` documentation portal.
