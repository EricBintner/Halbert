# Plan: web-v10 & feature-reference — Technical Dossier, Research Citations & Architecture Catalog

**Date:** 2026-09-15  
**Author:** AI Session (Pair Programming)  
**Status:** REV 2 — approved; review deltas folded in (see §7). Founder ruling recorded: the citation layer speaks in **third person, academic register, for the academic community** — it is a non-conversational reference layer; the storyboard stops keep their first-person voice.  
**Affected Packages:** `marketing/web-v10`, `marketing/feature-reference`, `marketing/shared`  
**Reference Example:** `/Volumes/4TB-BAD/HumanAI/CoDRAG/websites/apps/marketing/src/app/research/page.tsx`  
**Design Tokens:** `/shared-tokens/tokens.css` (Olivetti Vermilion & Bone, zero hardcoded colors)

---

## 1. Executive Summary & Problem Statement

`marketing/web-v10` features high-fidelity vector parallax animation and typographic choreography across 8 storyboard stops. While its visual pacing and first-person voice are polished, the surface presents only top-level claims with no visible technical depth, architecture mechanisms, or academic citations. 

At the same time:
- Halbert contains deep internal research (`.handoff/research/multi-node-systems/`, `.handoff/research/security/`, `.handoff/research/sec-2-3/`),
- Sister projects (like CoDRAG's research bibliography at `/Volumes/4TB-BAD/HumanAI/CoDRAG/packages/ui/src/data/researchSources.ts`) contain extensive citations directly applicable to Halbert's retrieval, compression, and knowledge systems,
- `marketing/feature-reference` contains an exhaustive dictionary of features (`catalog.json`), but in a linear, standalone reference viewer that feels disconnected from the marketing narrative.

### The Solution
Introduce an unobtrusive, tactile **Technical & Academic Research Dossier** trigger in the **bottom-left corner** of `marketing/web-v10`. 

- **Corner Trigger**: A mechanical icon button in the bottom-left corner (`fixed bottom-6 left-6 z-40`) styled with the Olivetti palette, showing an indicator dot and dynamic section badge (e.g. `[3 PAPERS · 4 FEATURES]`).
- **Expanding Dossier**:
  - **Desktop**: Expands upwards from the bottom-left corner (`w-[540px] max-h-[82vh] backdrop-blur-xl bg-[var(--color-surface)]/95`) with smooth scaling and tactile framing.
  - **Mobile**: Expands to a clean full-screen sheet with dismiss controls and touch-friendly scrolling.
  - **Context-Aware Content**: Dynamically tracks `camera.stopIndex` (0–7) as the user scrolls, highlighting the foundational research papers and core features relevant to the on-screen stop.
  - **Tabs**:
    1. `Section Focus`: Research citations and features tailored to the active stop.
    2. `All Research (18)`: Complete searchable academic bibliography (papers, RFCs, specs) with topic filters.
    3. `Feature Matrix`: Searchable catalog of technical features with implementation file paths and fail-closed invariants.
- **Unified Data**:
  - Centralize research papers in `marketing/shared/researchCitations.json`.
  - Enrich `marketing/feature-reference/src/catalog.json` with `stopId` and `citationIds`.
  - Update `marketing/feature-reference` to render academic citation blocks inside `FeatureDossier.jsx` and index them in `CommandPalette.jsx`.

---

## 2. Research Citations & Stop Mapping

A total of 30 papers, RFCs, specs, standards, and engineering reports are curated and mapped across the 8 storyboard stops. **No count in this table or in any UI string is authoritative by hand** — the UI derives every count from `researchCitations.json` at load. Each card carries an honest type badge and a `peerReviewed` flag: engineering reports (Anthropic's Contextual Retrieval post, Chroma's Context Rot) are labelled `engineering-report`, never passed off as peer-reviewed. Every entry's identifier is pinned (arXiv / RFC / DOI / SPDX) and machine-checked by `scripts/check_research_citations.py` before anything renders. **Verification outcome (2026-09-15, one web agent per citation):** of the four entries flagged suspect in review, two were confirmed nonexistent and are replaced in `researchCitations.json` by verified equivalents — "Log-Based Anomaly (Lin et al. 2020)" → **LogAnomaly, Meng et al., IJCAI 2019**, and "Proactive Telemetry (Poskitt 2018)" → **Donut, Xu et al., WWW 2018**; the other two ("Context Length Alone Hurts", arXiv:2510.05381, and "RAG vs. GraphRAG", Han et al., arXiv:2502.11371) verified as real and correctly attributed — the suspect flags were false alarms from title truncation. Two further corrections from the same pass: the TLS 1.3 citation is now **RFC 9846** (July 2026; it formally obsoletes RFC 8446), and "macOS Seatbelt / TrustedBSD MAC" is corrected to the canonical published description of that mechanism, **Blazakis, "The Apple Sandbox", Black Hat DC 2011**. The table below is the planning sketch; the JSON is the record.

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                             HALBERT RESEARCH TAXONOMY                            │
├──────────────┬───────────────────────────────┬───────────────────────────────────┤
│ Stop ID      │ Storyboard Stop & Concept     │ Primary Research Citations & RFCs │
├──────────────┼───────────────────────────────┼───────────────────────────────────┤
│ 00 intro     │ Meet Halbert                  │ MCP Specification (2024-11-05)   │
│              │ Native MCP & Ambient Sensory  │ RFC 9383: SPAKE2+ PAKE (2023)     │
│              │                               │ Wyoming Protocol (2023)           │
├──────────────┼───────────────────────────────┼───────────────────────────────────┤
│ 01 open      │ Triage                        │ SWIM Protocol (Das et al. 2002)   │
│              │ Proactive Anomaly Detection   │ LogAnomaly (Meng et al. 2019 —   │
│              │                               │   replacement for the planned    │
│              │                               │   "Lin et al. 2020", which does  │
│              │                               │   not exist)                     │
│              │                               │ Donut (Xu et al. WWW 2018 —       │
│              │                               │   replacement for the planned   │
│              │                               │   "Poskitt 2018", which does not │
│              │                               │   exist)                         │
├──────────────┼───────────────────────────────┼───────────────────────────────────┤
│ 02 apex      │ Automation                    │ Matter IP Spec (CSA 2022)         │
│              │ Home & Host Chores            │ RFC 6762/6763: mDNS/DNS-SD (2013) │
│              │                               │ Distributed Clocks (Lamport 1978) │
├──────────────┼───────────────────────────────┼───────────────────────────────────┤
│ 03 diagonal  │ Local                         │ The Apple Sandbox (Blazakis '11)  │
│              │ Private by Construction       │ RFC 9846: TLS 1.3 (2026, obsoletes│
│              │ Air-Gapped Execution & Tier 2 │   RFC 8446)                       │
│              │                               │ NIST SP 800-207: Zero Trust (2020) │
│              │                               │ OSV Vulnerability Database (2021) │
├──────────────┼───────────────────────────────┼───────────────────────────────────┤
│ 04 rise      │ Rationale                     │ Dynamo Store (DeCandia et al. 07) │
│              │ Intent Beside the Change      │ Concurrency & WAL (Bernstein 87)  │
│              │ State Vault & Rollback        │ Linearizability (Herlihy 1990)    │
├──────────────┼───────────────────────────────┼───────────────────────────────────┤
│ 05 hop       │ Knowledge                     │ Lost in the Middle (Liu et al 24) │
│              │ Grounded Sysadmin RAG         │ Context Length Alone Hurts        │
│              │ ~21.5k unique manuals         │   (Du et al. 2025, arXiv:2510.05381│
│              │ (measured; never "14k")       │   — verified real)               │
│              │                               │ Context Rot (Chroma 2025)         │
│              │                               │ Contextual Retrieval (Anthropic)  │
│              │                               │ RAG vs GraphRAG (Han et al. 2025, │
│              │                               │   arXiv:2502.11371 — verified)  │
│              │                               │ BM25 (Robertson & Zaragoza 2009) │
│              │                               │ Reciprocal Rank Fusion (2009)   │
├──────────────┼───────────────────────────────┼───────────────────────────────────┤
│ 06 cap       │ Distributed                   │ Splitwise: Phase Split (ISCA '24) │
│              │ Nodes of Shared Intelligence  │ DistServe: Prefill/Decode (OSDI)  │
│              │ LAN Compute Offloading        │ Petals: Collaborative (ACL '23)   │
│              │                               │ Ray Distributed AI (OSDI '18)     │
├──────────────┼───────────────────────────────┼───────────────────────────────────┤
│ 07 reveal    │ Get Halbert                   │ GNU GPLv3 & Section 7 Exception   │
│              │ (third-person citation layer; │ Ed25519 Signatures (Bernstein 12) │
│              │  never "Sovereign" in copy)   │ Saltzer & Schroeder (IEEE 1975)   │
└──────────────┴───────────────────────────────┴───────────────────────────────────┘
```

---

## 3. Detailed Data Schemas

### 3.1 Research Citation Schema (`marketing/shared/researchCitations.json`)

**Voice ruling (founder, 2026-09-15):** `takeaway` and `howHalbertApplies` are **third person, academic register** — "Halbert fuses BM25 sparse retrieval with dense embeddings under reciprocal rank fusion." This layer is for the academic community; the storyboard stops keep their first-person voice. A third-person citation layer does not inherit the marketing voice directives; it does inherit the copy bans below.

```typescript
export interface ResearchCitation {
  id: string;                       // Unique kebab-case slug (e.g. "lost-in-the-middle")
  stopId: string;                   // Corresponding storyboard stop id ('intro' | 'open' | etc.)
  title: string;                    // Formal paper / RFC / spec title
  authors: string;                 // "Liu et al.", "Anthropic", "Taubert & Wood"
  venue: string;                    // "TACL 2024", "IETF RFC 9383", "ISCA '24"
  year: number;                     // 2024
  url: string;                      // Canonical link (arXiv, IETF, ACM, IEEE, GitHub)
  identifier: string;               // REQUIRED: "arXiv:2307.03172", "RFC 9383", DOI, SPDX, or
                                    // official spec/version label. "" only for works with none.
  type: 'paper' | 'rfc' | 'spec' | 'benchmark' | 'survey' | 'engineering-report' | 'licence';
  peerReviewed: boolean;            // RFCs/specs/standards/blog posts: false. Honest per-card.
  category: 'retrieval' | 'compute' | 'security' | 'distributed' | 'systems' | 'licensing';
  applied: 'shipped' | 'design' | 'deferred';
                                    // 'shipped': code in halbert_core/ implements the mechanism
                                    //   today — howHalbertApplies names the file and mechanism.
                                    // 'design': the work informed the architecture via research
                                    //   docs (.handoff/research/) but the mechanism itself is
                                    //   not implemented — prose says so.
                                    // 'deferred': a DECISIONS.md/.handoff row explicitly defers
                                    //   or rejects it (e.g. SPAKE2+, SEC-TLS) — prose states
                                    //   the disposition, never implies adoption.
  takeaway: string;                 // One-line crisp academic finding (third person)
  howHalbertApplies: string;        // 2–3 sentences, third person, grounded per `applied`
}
```

**Join direction (one way only):** features in `catalog.json` carry `citationIds: string[]` referencing entries here. This schema deliberately has **no** `relatedFeatureIds` — a second join direction would drift against the first. The reverse mapping is derived at load, never stored. **Stop association is independent, not coupled (ruling folded in 2026-09-15):** features carry `stopIds: string[]` as *curated marketing anchors* for the Section Focus tab — they are not derived from the stops of the feature's citations, and the gate checks only storyboard membership. Coupling them would have forced `peer-pairing` (10 citations across 7 stops) to anchor nearly every stop, which is UX noise, not signal.

**Copy directives enforced on the prose fields (standing directives, binding):** no "Sovereign" (any case); no AI model names; no unverified counts (the corpus is ~21.5k unique non-empty manuals per `data/manifest.json` / `RAG-DATA-SOURCES` — never "14k"). `scripts/check_research_citations.py` enforces these plus the structural rules below, and is wired into Step 4 verification.

### 3.2 Enhanced Feature Schema (`marketing/feature-reference/src/catalog.json`)

Features in `catalog.json` are augmented with:
- `stopIds`: storyboard stop association, plural (`["diagonal", "hop"]` — a feature can anchor more than one stop; e.g. the secure-model gate serves both the Local stop and the Knowledge stop).
- `citationIds`: string array referencing entries in `researchCitations.json`. The **only** join direction; the reverse is derived at load.
- Refined `whatItIs`, `howItWorks`, `toolingAndBackend`, and `limitsAndInvariants` for improved digestibility and technical rigor — **with a sync constraint:** `index.html`'s JSON-LD hand-mirrors `catalog.json` copy (landed `b2926c26`; no generator exists). Editing mirrored fields desyncs the deployed AI-SEO metadata. Either add a sync-check script in the same change, or keep the mirrored fields frozen and refine the non-mirrored ones only.

---

## 4. Component Design: `TechnicalDossierModal.jsx`

### 4.1 Trigger Button
- **Placement**: `fixed bottom-6 left-6 z-40` with `padding-bottom: env(safe-area-inset-bottom)`.
- **Styling**: Mechanical Vermilion & Bone palette:
  - Clean border, surface tint, and accent indicator dot.
  - Text badge: `RESEARCH & SPECS` + dynamic badge showing count for active stop (`[3 PAPERS · 4 FEATURES]`).
  - Tactile hover state with smooth micro-interaction.

### 4.2 Modal Panel Architecture
- **Desktop Dimensions**: `w-[540px] max-w-[calc(100vw-3rem)] max-h-[82vh]`. Anchored bottom-left, scaling out with `origin-bottom-left`.
- **Mobile Dimensions**: `fixed inset-0 z-50 rounded-none w-full h-full`.
- **Header**:
  - Stop selector navigation (`STOP 02 / 08 · PROACTIVE TRIAGE`).
  - Search bar (placeholder computed at render: `Filter {papers} papers & {features} features...`).
  - Tab Switcher:
    - `Active Section` (dynamically bound to `camera.stopIndex`)
    - `All Research` (full searchable bibliography)
    - `Architecture Catalog` (features and code paths)
  - Close button (`✕`) + keyboard shortcut (`Esc`); focus is trapped in the panel while open and returned to the trigger on close; the trigger carries `aria-expanded` + `aria-controls`.
- **Citation Card Elements**:
  - Badge: `PAPER` / `RFC` / `SPEC`.
  - Title: Linked with external link indicator icon (`↗`).
  - Monospace citation: `Liu et al. · TACL 2024 · arXiv:2307.03172`.
  - Takeaway: Theoretical finding.
  - Engineering Application: "How Halbert applies this" in plain, grounded language.
  - Source links to relevant Halbert backend files.
- **Citation Card Elements**:
  - Badge: `PAPER` / `RFC` / `SPEC` / `SURVEY` / `ENG. REPORT` / `LICENCE` (from the `type` field — an engineering report is never badged `PAPER`; `peerReviewed: true` papers may additionally show a peer-review tick).
  - Title: Linked with external link indicator icon (`↗`).
  - Monospace citation: `Liu et al. · TACL 2024 · arXiv:2307.03172`.
  - Takeaway: Theoretical finding (third person).
  - Engineering Application: "How Halbert relates" — labelled by `applied`: shipped mechanisms cite the file, design influences say they shape the architecture, deferred ones state the disposition. Never a uniform "applies this".
  - Source links to relevant Halbert backend files (shipped citations only).
- **Feature Card Elements**:
  - Feature name + Status pill from the **catalog's own enum**: `shipped` / `hidden` / `deferred` — not `backend-only`, which is not a catalog value. The dossier filters exactly like the reference site: `hidden` and `deferred` features are excluded from the marketing dossier (the reference site remains the full, unfiltered dictionary).
  - One-line purpose.
  - Implementation mechanism.
  - Backend source file paths (`halbert_core/model/tier_router.py`).
  - Invariant / fail-closed boundary note.
- **Footer**:
  - Link to the canonical deployed reference: `https://halbert.computer/features/` ("Open Full Architecture Dictionary →"). Not `/feature-reference`, which is not a deployed route and 404s.
  - License notice: "Open Source · GPL-3.0 · Zero Cloud Telemetry".
- **Counts**: every visible count — the tab label, the search placeholder, the trigger's `[3 PAPERS · 4 FEATURES]` badge — is **computed from the JSON at render**, never a typed literal. A typed count is a stale claim waiting to happen.

---

## 5. Integration with `marketing/feature-reference`

1. **FeatureDossier Enhancement**:
   - In `FeatureDossier.jsx`, whenever a feature has `citationIds`, render an **Academic Foundations & Standards** block.
   - Displays each cited paper with author, year, venue, URL, and why it grounds the feature.
2. **Command Palette Integration**:
   - Update `CommandPalette.jsx` so queries matching paper titles, authors (e.g. "Liu", "Splitwise", "SPAKE2+"), or RFC numbers directly return citation results and jump to the relevant feature. Citation matches surface only for features whose status passes the site's existing visibility filter.
3. **Dedicated Research Category**:
   - Add a "Research & Foundations" category view to browse all papers (count derived from the JSON) alongside the feature categories.

---

## 6. Implementation Sequence

1. **Step 1: Canonical Data Setup — LANDED 2026-09-15**
   - `marketing/shared/researchCitations.json` landed with the complete verified citation dictionary (30 entries; every field pinned by web verification, every `applied` status measured against the code, replacements substituted for the two confirmed-hallucinated entries). Builder: `scripts/build_research_citations.py` (provenance); gate: `scripts/check_research_citations.py` (fail-closed).
   - `marketing/feature-reference/src/catalog.json` enriched (v4) with `citationIds` (22 features, 52 join rows, inverted from the grounding pass's measured relatedFeatureIds) and `stopIds` (36 curated marketing anchors). **Ruling folded in (2026-09-15): stopIds and citationIds are deliberately INDEPENDENT associations** — stopIds are curated Section Focus anchors; the gate checks storyboard membership, not citation-stop coupling. Builder: `scripts/enrich_catalog_citations.py`.
   - The JSON-LD sync constraint from §3.2 resolved for this change: enrichment added fields only, mirrored copy untouched (verified — all 44 `oneLine` strings still present in index.html, byte-identical to HEAD; an apparent `why-brain` drift was a false positive from JSON-escaping in the HTML).
   - Founder ruling (2026-09-15) on finding 4 recorded: `applied` statuses are a snapshot to refresh at launch (the codebase is actively building; many design/deferred mechanisms will ship before launch), not permanent labels.
2. **Step 2: Marketing v10 Dossier Component**
   - Configure the shared-data aliases in `marketing/web-v10/vite.config.js`: `@halbert/shared` → `marketing/shared` (researchCitations.json) and `@halbert/catalog` → `marketing/feature-reference/src/catalog.json` (the dossier's Feature Matrix needs feature data; one copy of each dataset, aliased across, never duplicated) — alongside the existing `@tokens` / `@halbert/design-system`, not `@shared`, which reads as generic. Ports: `.claude/launch.json` already runs web-v10's dev server at 5189 via CLI override; feature-reference's config port moves 5188 → 5190 so no two dev servers collide.
   - Build `marketing/web-v10/src/components/TechnicalDossierModal.jsx`.
   - Mount and wire into `marketing/web-v10/src/App.jsx` passing `camera.stopIndex`. Respect `prefers-reduced-motion` for the panel scaling transition.
   - Mobile breakpoints follow the site's existing `max-sm:` convention (not ad-hoc `sm:` inversions).
3. **Step 3: Feature Reference Updates**
   - Configure the same shared-data aliases in `marketing/feature-reference/vite.config.js` (`@halbert/shared` → `../shared`, `@halbert/catalog` → `./src/catalog.json`; port 5190, per above).
   - Update `FeatureDossier.jsx` to render cited research.
   - Update `CommandPalette.jsx` and `App.jsx` for citation search and category browsing.
4. **Step 4: Verification & Polish**
   - Run production builds: `npm run build` on both sites.
   - Run `scripts/check_research_citations.py` — the citation gate must pass before any deploy.
   - Run `check_contrast.py` to ensure token compliance.
   - Test responsive layout on mobile (375px) and desktop (1920px).
   - Verify the `bg-[var(--color-surface)]/95` opacity-modifier pattern renders correctly under Tailwind v4 color-mix on first build (arbitrary-var opacity modifiers are a known v4 seam).

---

## 7. Review deltas folded into this revision (2026-09-15, rev 2)

A structural review of rev 1 against the codebase found the plan sound in shape
but wrong in its data layer. All findings below are already folded into the
sections above; they are recorded here so the history survives the session.

| # | Finding (rev 1) | Disposition in rev 2 |
|---|---|---|
| 1 | The §2 table lists 30 citations, but the prose said "a total of 18" and the tab label / search placeholder hardcoded 18 (and 25 features; the catalog has 44). | Counts corrected and **removed from prose entirely** — every visible count is computed from the JSON at render (§2, §4.2). |
| 2 | "Peer-reviewed papers" framing was false for several entries (Anthropic Contextual Retrieval and Chroma Context Rot are engineering blog posts). | §2 now says "papers, RFCs, specs, standards, and engineering reports"; the schema carries `type: engineering-report` and a per-card `peerReviewed` flag; the card badge derives from `type` and never badged a blog post as a paper (§3.1, §4.2). |
| 3 | Four entries were flagged suspect in review: "Log-Based Anomaly (Lin et al. 2020)", "Proactive Telemetry (Poskitt 2018)", "Context Length Alone Hurts (2025)", "RAG vs GraphRAG (Han et al. 2025)". **Measured outcome:** the first two are confirmed nonexistent (no first-author Lin 2020 log-anomaly paper in any canonical index; no Poskitt-authored 2018 telemetry work in his complete publication record) and are replaced by verified equivalents — LogAnomaly (Meng et al., IJCAI 2019) and Donut (Xu et al., WWW 2018). The last two verified as real and correctly attributed; the flags were false alarms from title truncation. | All 30 entries were web-verified one-by-one (one agent per citation); replacements substituted for the two confirmed-hallucinated entries; `identifier` is required and machine-checked, so an unidentifiable work cannot enter the dictionary. Two bonus corrections from the same pass: TLS 1.3 → RFC 9846 (the current spec; RFC 8446 is formally obsoleted), and "macOS Seatbelt / TrustedBSD MAC" (a mechanism name, not a work) → Blazakis, "The Apple Sandbox", Black Hat DC 2011. |
| 4 | `howHalbertApplies` as written would have claimed unshipped mechanisms for roughly half the bibliography (SWIM, Matter, Lamport clocks, Dynamo-style replication, linearizability, Splitwise/DistServe/Petals/Ray are research-informed design, not shipped code; SPAKE2+ is explicitly deferred by `SEC-TLS`). | Schema gains `applied: shipped / design / deferred`, each status measured against the code, with prose rules per status (§3.1). `shipped` requires a named file. **Founder ruling (2026-09-15): low concern** — Halbert is actively building and many of these mechanisms are expected to ship before the dossier launches; `applied` is a snapshot to refresh at launch time, not a permanent label. |
| 5 | "14k Verified Manuals" has no ground truth — the corpus is 28,869 docs / ~21.5k unique non-empty per `data/manifest.json`; the live stop copy deliberately says "thousands". | The claim is removed from the plan; the copy directive says the measured number or "thousands", never "14k" (§2, §3.1). |
| 6 | Step 1's "refined `whatItIs`/`howItWorks`" would silently desync `index.html`'s hand-mirrored JSON-LD metadata (landed `b2926c26`; no generator exists; strings verified identical today). | §3.2 declares the sync constraint: add a sync-check script or freeze the mirrored fields. |
| 7 | The footer linked `/feature-reference`, which 404s on the deployed site — the reference site's canonical URL is `https://halbert.computer/features/`. | Footer now links the canonical URL (§4.2). |
| 8 | §4.2's status pill invented `backend-only`, which is not a catalog value (`shipped` / `hidden` / `deferred`). | Pill uses the catalog's enum; `hidden`/`deferred` features are excluded from the marketing dossier as on the reference site (§4.2). |
| 9 | The reveal row used "Sovereign Machine Being" — a standing directive bans "Sovereign" from user-facing surfaces. | Struck from the table and the copy directives (§2, §3.1). |
| 10 | `citationIds` on features *and* `relatedFeatureIds` on citations would drift as two join directions. | One join direction only: features carry `citationIds`; the reverse is derived at load (§3.1). Likewise `stopId` → `stopIds` on features (§3.2). |
| 11 | Voice: rev 1's schema baked in third person; the marketing stops are first-person by standing directive. Both options were presented to the founder. | **Founder ruling (2026-09-15): third person, academic register — for the academic community.** Recorded in the status line and §3.1. |
| 12 | Minor: both vite dev configs use port 5188 (collision); `@shared` alias collides with nothing and reads generic; the Tailwind v4 `bg-[var(--color-surface)]/95` opacity-modifier seam needed a first-build check; missing a11y (focus trap, `aria-expanded`); no `prefers-reduced-motion`; counts typed as literals. | §4.2 a11y + computed counts; §6 Step 2 port 5189 + `@halbert/shared` alias + reduced-motion; Step 4 adds the color-mix seam check. |

**Verification methodology (rev 2):** the citation dictionary was not taken on
trust. Each of the 30 entries was checked by a separate web-research agent
pinning title / authors / venue / year / canonical URL / stable identifier /
type / peer-review status, with the four suspect entries flagged for
replacement search — of which two were confirmed nonexistent and replaced, and
two verified as real (see table row 3). Each of the 8 stops' citations was
separately grounded against the codebase by an agent measuring shipped /
design / deferred status with file-path evidence. The JSON is assembled from
those verified results, not from this plan's table. The builder is
`scripts/build_research_citations.py`; the standing gate is
`scripts/check_research_citations.py`.
