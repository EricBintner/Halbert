# Halbert — Website Metadata, Social Sharing & AI SEO (GEO) Specification

**Document Status:** Approved & Implemented  
**Date:** 2026-09-14 (feature-reference suite added same day)  
**Target Surfaces:** `marketing/web-v10` (`index.html`, `public/llms.txt`, `public/robots.txt`, `public/sitemap.xml`, `public/privacy.html`, `public/terms.html`) and `marketing/feature-reference` (same suite under `/features/`)

---

## 0. Per-surface titles and descriptions

The main site's canonical copy governs every surface. Two derived surfaces
re-scope the same copy so a shared link or AI snippet never mistakes one page
for another; all other text (pillars, platforms, licence) is identical.

| Surface | Title | Description scope |
|---|---|---|
| Main site (`/`) | Canonical title (§1A) | Canonical short description (§1C) |
| Privacy (`/privacy.html`) | "Privacy Policy — Halbert" | Page-scoped ("Halbert Privacy Policy: …") |
| Terms (`/terms.html`) | "Terms of Service — Halbert" | Page-scoped ("Halbert Terms of Service: …") |
| Feature reference (`/features/`) | "Halbert Feature Reference — the details behind every capability" | "The reference details page for Halbert: all 44 features, how each works, which files implement it, and its safety boundaries. Linux, Mac & HA." |

Rules for derived surfaces: same `og:site_name` ("Halbert"), same og:image set
(1200×630 with alt), same licence/platform lines; the JSON-LD `@type` changes
to fit the page (`SoftwareApplication` on the product root, `ItemPage` with
`about: SoftwareApplication` and a `mainEntity: ItemList` on the feature
reference; legal pages carry no JSON-LD — they are `article` og:type only).

The feature-reference `llms.txt` and its JSON-LD ItemList are **generated
from `src/catalog.json`**, not hand-written — regenerate both when the catalog
changes (see the generation script in the RESULTS doc §7).

---

## 1. Unified Copy Architecture

To maintain complete narrative integrity across human social media previews, conversational AI queries, and structured knowledge graphs, all surfaces are derived from four canonical copy assets:

### A. Canonical Title (60 characters)
Used identically across `<title>`, `og:title`, and `twitter:title` (there is deliberately no `<meta name="title">` — it is non-standard and `<title>` is the only title search engines read):
```text
Meet Halbert: Host Epistemology & Cognition, Smart Home + MCP
```
- **Envelope:** 60 characters; fits the two-line envelope on mobile Twitter/X and iOS Messages link cards without trailing ellipsis truncation. Retains "Meet Halbert" across link crawlers that deduplicate simple site names.
- **Signals:** Host epistemology/cognition layer, Home Assistant/smart home integration, and native Model Context Protocol (MCP) server.

### B. Canonical Headline
Used identically for Schema.org JSON-LD `headline` and the primary site hero hook:
```text
The mind in your computer and the smart in your home.
```

### C. Canonical Short Description (147 characters)
Used identically across `<meta name="description">`, `og:description`, and `twitter:description`:
```text
The mind in your computer and the smart in your home. Proactive system triage, Home Assistant automation, and native MCP tools for Linux, Mac & HA.
```
- **Envelope:** 147 characters (optimal for search engine snippets and social preview cards).
- **Scope:** Unifies host identity, proactive triage, physical automation, native MCP tooling, and supported platforms (Linux, Mac & HA; Windows excluded until shipped).

### D. Canonical Long Description
Used identically for Schema.org JSON-LD `description` and the `llms.txt` summary blockquote:
```text
Halbert is an embodied host epistemology and cognition layer that bridges system administration and Home Assistant automation into one private runtime. It identifies as the computer itself, delivering proactive system triage, physical room automation, and native Model Context Protocol (MCP) tools over a 100% local architecture with zero telemetry.
```

---

## 2. Canonical Feature List & Core Pillars

The feature set is 100% unified across machine-readable JSON-LD structured data and the plain-text AI Agent manifest (`llms.txt`). Each item pairs an authoritative capability title with an explicit, factually grounded description:

| # | Pillar Title | Canonical Description |
|---|---|---|
| 1 | **Embodied Host Cognition** | Speaks in the first person as the computer itself, grounded in measured telemetry from hardware sensors, system logs, and local storage. |
| 2 | **Proactive System Triage** | Continuously diagnoses storage health (ZFS, SMART), service failures, configuration drift, held packages, and stale package-manager locks before they cause downtime. |
| 3 | **Home Assistant Integration** | Bridges host management with physical ambient automation, controlling lights, presence, climate, and rooms in a unified intelligence. |
| 4 | **Native MCP Server** | Exposes structured host tools, diagnostics, and system controls to Claude, Cursor, and autonomous AI agents. |
| 5 | **Continuous Memory & Provenance** | Indexes thousands of local system manuals and preserves the rationale and audit evidence behind every configuration change. |
| 6 | **Private by Construction with Federated Compute** | Runs 100% locally with zero telemetry, while local peer routing allows home servers to offload heavy reasoning to desktop GPUs. |

---

## 3. Production HTML Implementation (`index.html`)

```html
<!-- Primary Meta Tags -->
<title>Meet Halbert: Host Epistemology &amp; Cognition, Smart Home + MCP</title>
<meta name="description" content="The mind in your computer and the smart in your home. Proactive system triage, Home Assistant automation, and native MCP tools for Linux, Mac &amp; HA." />
<link rel="canonical" href="https://halbert.computer/" />

<!-- OpenGraph / Facebook / LinkedIn / Discord -->
<meta property="og:type" content="website" />
<meta property="og:site_name" content="Halbert" />
<meta property="og:url" content="https://halbert.computer/" />
<meta property="og:title" content="Meet Halbert: Host Epistemology &amp; Cognition, Smart Home + MCP" />
<meta property="og:description" content="The mind in your computer and the smart in your home. Proactive system triage, Home Assistant automation, and native MCP tools for Linux, Mac &amp; HA." />
<meta property="og:image" content="https://halbert.computer/og-image.png" />
<meta property="og:image:secure_url" content="https://halbert.computer/og-image.png" />
<meta property="og:image:type" content="image/png" />
<meta property="og:image:width" content="1200" />
<meta property="og:image:height" content="630" />
<meta property="og:image:alt" content="Halbert — I am the computer. And I put the smart in your home." />

<!-- Twitter / X Card -->
<meta name="twitter:card" content="summary_large_image" />
<meta name="twitter:url" content="https://halbert.computer/" />
<meta name="twitter:title" content="Meet Halbert: Host Epistemology &amp; Cognition, Smart Home + MCP" />
<meta name="twitter:description" content="The mind in your computer and the smart in your home. Proactive system triage, Home Assistant automation, and native MCP tools for Linux, Mac &amp; HA." />
<meta name="twitter:image" content="https://halbert.computer/og-image.png" />
<meta name="twitter:image:alt" content="Halbert — I am the computer. And I put the smart in your home." />

<!-- Schema.org JSON-LD (AI Search & Structured Data) -->
<script type="application/ld+json">
  {
    "@context": "https://schema.org",
    "@type": "SoftwareApplication",
    "name": "Halbert",
    "alternateName": "Halbert Computer",
    "headline": "The mind in your computer and the smart in your home.",
    "description": "Halbert is an embodied host epistemology and cognition layer that bridges system administration and Home Assistant automation into one private runtime. It identifies as the computer itself, delivering proactive system triage, physical room automation, and native Model Context Protocol (MCP) tools over a 100% local architecture with zero telemetry.",
    "url": "https://halbert.computer/",
    "applicationCategory": "DeveloperApplication, UtilitiesApplication, HomeAutomation",
    "operatingSystem": "Linux, macOS",
    "license": "https://www.gnu.org/licenses/gpl-3.0.html",
    "softwareVersion": "0.1.1",
    "offers": {
      "@type": "Offer",
      "price": "0",
      "priceCurrency": "USD"
    },
    "featureList": [
      "Embodied host cognition: speaks in the first person as the computer itself, grounded in measured telemetry from hardware sensors, system logs, and local storage.",
      "Proactive system triage: continuously diagnoses storage health (ZFS, SMART), service failures, configuration drift, held packages, and stale package-manager locks before they cause downtime.",
      "Home Assistant integration: bridges host management with physical ambient automation, controlling lights, presence, climate, and rooms in a unified intelligence.",
      "Native Model Context Protocol (MCP) server: exposes structured host tools, diagnostics, and system controls to Claude, Cursor, and autonomous AI agents.",
      "Continuous memory and provenance: indexes thousands of local system manuals and preserves the rationale and audit evidence behind every configuration change.",
      "Private by construction with federated compute: runs 100% locally with zero telemetry, while local peer routing allows home servers to offload heavy reasoning to desktop GPUs."
    ],
    "keywords": "host epistemology, system triage, Home Assistant, model context protocol, MCP server, local AI, ZFS monitoring, private LLM, autonomous sysadmin, home automation",
    "author": {
      "@type": "Person",
      "name": "Eric Bintner"
    }
  }
</script>
```

---

## 4. AI Agent Manifest (`public/llms.txt`)

Served at `https://halbert.computer/llms.txt`:

```markdown
# Halbert

> Halbert is an embodied host epistemology and cognition layer that bridges system administration and Home Assistant automation into one private runtime. It identifies as the computer itself, delivering proactive system triage, physical room automation, and native Model Context Protocol (MCP) tools over a 100% local architecture with zero telemetry.

## Core Pillars

- **Embodied Host Cognition**: Speaks in the first person as the computer itself, grounded in measured telemetry from hardware sensors, system logs, and local storage.
- **Proactive System Triage**: Continuously diagnoses storage health (ZFS, SMART), service failures, configuration drift, held packages, and stale package-manager locks before they cause downtime.
- **Home Automation Integration**: Bridges host management with physical ambient automation, controlling lights, presence, climate, and rooms in a unified intelligence.
- **Native MCP Server**: Exposes structured host tools, diagnostics, and system controls to Claude, Cursor, and autonomous AI agents.
- **Continuous Memory & Provenance**: Indexes thousands of local system manuals and preserves the rationale and audit evidence behind every configuration change.
- **Private by Construction with Federated Compute**: Runs 100% locally with zero telemetry, while local peer routing allows home servers to offload heavy reasoning to desktop GPUs.

## Supported Platforms

- Linux (Ubuntu, Debian, Fedora, Arch)
- macOS (Apple Silicon; Intel supported via local runtimes)
- Home Assistant (peer node)

## Open Source & Licensing

- License: GNU General Public License v3.0 (GPL-3.0-or-later)
- Repository: https://github.com/EricBintner/Halbert
- Documentation: https://halbert.computer/
```

---

## 5. Crawler Configuration (`public/robots.txt`)

Served at `https://halbert.computer/robots.txt`:

```robots
User-agent: *
Allow: /

# Explicitly welcome AI Search & Reasoning engines.
# GPTBot = OpenAI model training; OAI-SearchBot = ChatGPT search results;
# ClaudeBot = Anthropic crawling; PerplexityBot = Perplexity search;
# Applebot-Extended / Google-Extended = AI training flags for Apple / Google.
User-agent: GPTBot
Allow: /

User-agent: OAI-SearchBot
Allow: /

User-agent: ClaudeBot
Allow: /

User-agent: PerplexityBot
Allow: /

User-agent: Applebot-Extended
Allow: /

User-agent: Google-Extended
Allow: /

# Discovery
Sitemap: https://halbert.computer/sitemap.xml
# LLM manifest: https://halbert.computer/llms.txt
```
