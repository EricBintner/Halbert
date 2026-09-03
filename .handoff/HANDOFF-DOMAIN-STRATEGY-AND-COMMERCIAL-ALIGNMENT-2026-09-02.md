# HANDOFF & RESEARCH: Domain Strategy, Brand Namespace & Commercial Tier Alignment

**Date:** 2026-09-02  
**Target:** Founder / Product Strategy / Marketing Website AI / Distribution Engineering  
**Status:** Active Strategy & Research Brief  
**Parent Strategy & Decision Documents:**
- [`documentation/legal/OPEN-CORE-AND-DISTRIBUTION-STRATEGY.md`](file:///Volumes/4TB-BAD/Halbert/documentation/legal/OPEN-CORE-AND-DISTRIBUTION-STRATEGY.md)
- [`FOUNDER-TODO.md`](file:///Volumes/4TB-BAD/Halbert/FOUNDER-TODO.md) (`FDR-DEC-03`, `FDR-DEC-04`)
- [`.handoff/HANDOFF-MARKETING-WEBSITE-UPDATE-2026-08-31.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/HANDOFF-MARKETING-WEBSITE-UPDATE-2026-08-31.md)
- [`documentation/design/macos-strategy.md`](file:///Volumes/4TB-BAD/Halbert/documentation/design/macos-strategy.md)

---

## 1. Executive Summary & Objective

The primary domain names initially considered in project documentation (`halbert.ai`, `halbert.dev`, `halbert.com`, `halbert.io`, `halbert.app`, `halbert.org`, `halbert.co`) are **unavailable / registered by third parties**.

This document captures:
1. **Empirical registry research** identifying exactly which domain variations are available vs. taken.
2. **Alignment with Halbert’s Open-Core business model** ($24–$29 one-time perpetual license, free Mac App Store companion, 100% GPLv3 self-hosted core).
3. **Resolving namespace dependencies** in [`FOUNDER-TODO.md`](file:///Volumes/4TB-BAD/Halbert/FOUNDER-TODO.md) (e.g., updating Apple bundle identifiers from `ai.halbert.*` to a valid registered domain namespace).
4. **Concrete registration recommendations** and next steps.

---

## 2. Empirical Domain Availability Findings

Global DNS and registry SOA records were analyzed across candidate prefixes, suffixes, and TLDs.

### 2.1 Available Candidates (Confirmed Unregistered)

| Domain | Category | Strategic Fit for Halbert |
| :--- | :--- | :--- |
| **`runhalbert.com`** | **Action Prefix (`.com`)** | ⭐ **Top Flagship Recommendation.** Active verb that represents CLI execution, local model inference, and autonomous agent workflows. |
| **`halbert.sh`** | **Developer TLD (`.sh`)** | ⭐ **Top Developer / CLI Recommendation.** The gold-standard TLD for Unix/Linux CLI utilities (`brew.sh`, `ohmyz.sh`). Ideal for `curl -fsSL https://halbert.sh/install \| bash`. |
| **`halberthq.com`** | **SaaS Suffix (`.com`)** | Clean, credible fallback for corporate, documentation, and licensing operations. |
| **`halbertos.com`** | **System Suffix (`.com`)** | Matches the "sentient machine / home operating system" concept. |
| **`halbertcli.com`** | **Product Suffix (`.com`)** | Clear, unambiguous developer focus. |
| **`halbertcore.com`** | **Architecture (`.com`)** | Directly matches the internal engine namespace (`halbert_core`). |
| **`halbertops.com`** | **DevOps / Sysadmin (`.com`)** | Emphasizes system administration and telemetry automation. |
| **`askhalbert.com`** | **Conversational (`.com`)** | Emphasizes the natural language voice and chat assistant capabilities. |
| **`heyhalbert.com`** | **Conversational (`.com`)** | Friendly assistant branding (similar to Hey Siri / Hey Google). |
| **`halbert-ai.com`** | **Hyphenated (`.com`)** | Direct fallback for the `.ai` concept. |
| **`halbert.run`** | **Modern TLD (`.run`)** | Punchy and execution-oriented. |
| **`halbert.tech`** | **Tech TLD (`.tech`)** | General tech industry TLD. |
| **`halbert.so`** | **Modern App TLD (`.so`)** | Popular in the modern productivity/developer software space. |
| **`halbert.tools`** | **Tooling TLD (`.tools`)** | Descriptive utility positioning. |
| **`halbertproject.org`** | **Open Source (`.org`)** | Established convention for open-source foundations and community projects. |
| **`gethalbert.dev`** | **Developer (`.dev`)** | Action prefix on developer TLD. |

### 2.2 Unavailable Candidates (Confirmed Taken / Active)

| Domain | Status | Note |
| :--- | :--- | :--- |
| `halbert.com` | **Taken** | Registered (Legacy / Private owner) |
| `halbert.ai` | **Taken** | Registered (Currently referenced in older docs) |
| `halbert.io` | **Taken** | Registered |
| `halbert.app` | **Taken** | Registered |
| `halbert.dev` | **Taken** | Registered (Referenced in older docs) |
| `halbert.co` | **Taken** | Registered |
| `halbert.org` | **Taken** | Registered |
| `halbert.me` | **Taken** | Registered |
| `gethalbert.com` | **Taken** | Registered |
| `usehalbert.com` | **Taken** | Registered |
| `tryhalbert.com` | **Taken** | Registered |
| `halbertlabs.com` | **Taken** | Registered |
| `halbertapp.com` | **Taken** | Registered |

---

## 3. Product Seam & Business Model Alignment

Halbert's monetization and product architecture requires a domain that can host both **open-source community trust** and **commercial desktop conversion**:

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                   HALBERT ECOSYSTEM                                    │
├───────────────────────────────────────────┬────────────────────────────────────────────┤
│        OPEN-SOURCE CORE (GPL-3.0)         │            COMMERCIAL DESKTOP              │
│      (Server / Homelab / Linux / HA)      │          (macOS & Windows Clients)         │
├───────────────────────────────────────────┼────────────────────────────────────────────┤
│ • Full Python Engine & LangGraph Agent    │ • Halbert Companion (Mac App Store - FREE) │
│ • Linux CLI & Local Dashboard (:8000)     │   - Sandboxed (Apple compliant)            │
│ • Home Assistant Client & Config Bridge   │   - Menu Bar / Voice Satellite             │
│ • Wyoming Voice TCP Server (:10401)       │   - Connects to remote HA/Halbert host     │
│ • Frigate NVR Event Ingestion & Scanners  │                                            │
│ • HAOS Add-on / Docker Containers         │ • Halbert Pro (Lemon Squeezy - $24–$29)    │
│ • Linux native packages (apt, AUR, snap)  │   - Unsandboxed Apple-Notarized DMG / MSI  │
│                                           │   - Local Mac & Linux Sysadmin Cockpit     │
│                                           │   - Multi-Host Fleet SSH / Tailscale       │
│                                           │   - Ed25519 Offline Signed License Keys    │
└───────────────────────────────────────────┴────────────────────────────────────────────┘
```

### 3.1 Why SaaS Domains Don't Match, but Developer + Desktop Domains Do
- **Zero Recurring SaaS Costs:** Halbert runs on local compute (Ollama, Apple Silicon, N150 homelab boxes). The monetization is a **$24–$29 one-time perpetual license** (with 12 months of updates), avoiding subscription burnout.
- **Audience Intersection:** Users are split between Linux/Homelab sysadmins (*"I am the machine"*) and Home Assistant enthusiasts (*"I am the home"*).
- **Dual-Purpose Website:** The website must provide quick install strings (`curl ... | bash` / Docker instructions) alongside direct purchase links and Mac App Store badges.

---

## 4. Recommended Namespace & Identifier Strategy

### 4.1 Primary Domain Pair Strategy
1. **Primary Commercial & Ecosystem Hub (`.com`):** **`runhalbert.com`** (or **`halberthq.com`**)
   - Serves the marketing website, documentation, download links, and Lemon Squeezy payment flows.
   - Provides clean corporate email (`founder@runhalbert.com`, `support@runhalbert.com`).
2. **Developer & CLI Shortlink (`.sh`):** **`halbert.sh`**
   - Serves the curl-pipe-bash installer script: `curl -fsSL https://halbert.sh/install | bash`.
   - Serves short documentation redirects: `halbert.sh/docs`, `halbert.sh/ha-addon`.

---

### 4.2 Updating Bundle Identifiers (`FOUNDER-TODO.md` `FDR-DEC-03`)

Because `halbert.ai` is taken, the planned `ai.halbert.*` bundle IDs must be updated to avoid reverse-DNS namespace collisions.

#### Proposed Updated Bundle Identifier Mapping:

| Surface | Previous (Assuming `halbert.ai`) | Updated with `runhalbert.com` | Updated with `halbert.sh` |
| :--- | :--- | :--- | :--- |
| **Free Mac App Store Companion** | `ai.halbert.home` | `com.runhalbert.companion` (or `com.runhalbert.home`) | `sh.halbert.companion` |
| **Paid Pro Direct DMG** | `ai.halbert.pro` | `com.runhalbert.pro` | `sh.halbert.pro` |
| **Local Daemon / Dashboard** | `ai.halbert.dashboard` | `com.runhalbert.dashboard` | `sh.halbert.dashboard` |

> [!TIP]
> Using `com.runhalbert.companion` for the free Mac App Store app resolves the naming collision between the "Halbert Home" desktop app and the "Halbert home variant" (Home Assistant server engine).

---

## 5. Immediate Action Items for the Founder

- [ ] **Step 1:** Register **`runhalbert.com`** (primary storefront/ecosystem hub) and **`halbert.sh`** (CLI installer / developer shortlink).
- [ ] **Step 2:** Update [`FOUNDER-TODO.md`](file:///Volumes/4TB-BAD/Halbert/FOUNDER-TODO.md) item `FDR-DEC-03` to formally lock the new bundle identifier namespace (`com.runhalbert.*`).
- [ ] **Step 3:** Update [`documentation/legal/OPEN-CORE-AND-DISTRIBUTION-STRATEGY.md`](file:///Volumes/4TB-BAD/Halbert/documentation/legal/OPEN-CORE-AND-DISTRIBUTION-STRATEGY.md) and [`marketing/MARKETING-WEBPAGE-PLAN-2026-08-23.md`](file:///Volumes/4TB-BAD/Halbert/marketing/MARKETING-WEBPAGE-PLAN-2026-08-23.md) to reference `runhalbert.com` / `halbert.sh` instead of `halbert.dev` or `halbert.ai`.
- [ ] **Step 4:** Set up DNS records:
  - Root `@` and `www` $\rightarrow$ Marketing site (Vite/Cloudflare Pages/Vercel).
  - `docs` $\rightarrow$ Technical documentation & man pages.
  - `install.sh` / `halbert.sh/install` $\rightarrow$ Raw bash deployment script for Linux/HAOS.
