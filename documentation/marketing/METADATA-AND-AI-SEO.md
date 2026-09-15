# Halbert — Website Metadata, Social Sharing & AI SEO (GEO) Specification

**Document Status:** Proposal / Draft for Review (Rev 2)  
**Date:** 2026-09-14  
**Target Surface:** `marketing/web-v10` (`index.html`, `public/llms.txt`, `public/robots.txt`)  

---

## 1. Executive Summary & Problem Statement

The live metadata in `marketing/web-v10/index.html` was written before the v10 content overhaul:
- It still uses the old triage headline (*"Halbert — I know what’s wrong and I can help you fix it."*).
- It completely omits **Home Assistant** integration and home automation.
- It completely omits **Native Model Context Protocol (MCP)** tool serving.
- It omits the **distributed multi-machine** ("Singular Entity") architecture.
- It states *"Linux today, macOS in beta"* instead of the updated platform lineup (*"Linux · Mac · Home Assistant"*).
- It lacks any **AI SEO / Generative Engine Optimization (GEO)** structure (no `llms.txt`, no JSON-LD structured data, no AI search engine indexing hooks).

When shared on Twitter/X, Discord, Slack, iMessage, or LinkedIn, or when crawled by AI search engines (Perplexity, ChatGPT Search, Claude, Gemini, Apple Intelligence), Halbert currently presents as a generic Linux log monitor rather than what it is: **an embodied local host intelligence that is your computer, automates your smart home, and serves native MCP tools to your AI agents.**

---

## 2. What is "AI SEO" (Generative Engine Optimization)?

Traditional SEO focuses on Google keywords, backlinks, and meta tags. **AI SEO (GEO)** focuses on how Large Language Models (LLMs) and conversational search engines ingest, understand, cite, and recommend software:

1. **`llms.txt` Standard**: An emerging, cross-industry specification (originated by Answer.ai, adopted by Anthropic, Perplexity, Cursor, Cloudflare, etc.). It lives at `/llms.txt` and gives AI assistants a clean, Markdown-formatted manifest explaining what Halbert is, its capabilities, architecture, and documentation.
2. **Schema.org Structured Data (`JSON-LD`)**: Embedded in HTML `<script type="application/ld+json">`. LLMs and knowledge graphs (Google Knowledge Graph, Perplexity entity models) extract machine-readable entities (`SoftwareApplication`, `HomeAutomation`, `DeveloperApplication`, `GPL-3.0-or-later`).
3. **Information Density & Factual Grounding**: AI engines penalize vague marketing fluff and reward concrete, authoritative declarations of architecture, constraints, and features (e.g. *"Zero telemetry"*, *"Requires local model for credentials"*, *"Native MCP server"*).
4. **AI Crawler Hygiene (`robots.txt`)**: Explicitly permitting AI search indexers (`GPTBot`, `ClaudeBot`, `PerplexityBot`, `Applebot-Extended`) while protecting non-production assets.

---

## 3. Title (A) Analysis & Options (Target: 50–60 characters)

Twitter/X card previews (as measured on mobile) comfortably fit **55–58 characters** across 2 lines before truncating. 

* **Option A1 (Your Proposed Line — Full)**:  
  `Halbert — Local Host Epistemology & Cognition, Smart Home & Native MCP`  
  *Length: 68 characters*  
  *Fit:* Fits desktop nicely, but on small mobile Twitter cards the last word (`Native MCP`) may wrap to a 3rd line or truncate to `Native...`.
* **Option A2 (Your Proposed Line — Tightened for Mobile Preview — Recommended)**:  
  `Halbert — Host Epistemology & Cognition, Smart Home & MCP`  
  *Length: 56 characters*  
  *Fit:* **Exact match for the 56–58 character two-line envelope** shown in the Twitter card screenshot!
* **Option A3 (Local Focus — Tightened)**:  
  `Halbert — Local Epistemology & Cognition, Smart Home & MCP`  
  *Length: 57 characters*  
  *Fit:* Fits 2 lines cleanly.
* **Option A4 (Original Option 2 — Standard Tech Keywords)**:  
  `Halbert — Local Host Intelligence, Smart Home & Native MCP`  
  *Length: 58 characters*  
  *Fit:* Fits 2 lines cleanly.

---

## 4. Description (B) Rewrites (Target: 145–160 characters)
*Refined to remove Windows and reallocate character budget from privacy repetitiveness to rich capabilities (triage, 20k docs, MCP, Home Assistant).*

* **Option B1 (Cognition + Triage + MCP + Home Assistant — Recommended)**:  
  `Embodied host cognition and home automation. Proactive triage, native MCP tools, and continuous memory for Linux, Mac & Home Assistant. Runs locally.`  
  *(147 characters)*
* **Option B2 (Capabilities-Dense: Triage, 20k Docs, MCP, HA)**:  
  `Halbert bridges host management and home automation into one local intelligence. Proactive triage, 20,000 local docs, and native MCP for Linux, Mac & HA.`  
  *(154 characters)*
* **Option B3 (Action-Oriented: Hardware Vitals + Smart Home + Tools)**:  
  `Monitors hardware vitals, automates your home, and gives AI tools native MCP access to your system. Proactive triage for Linux, Mac & Home Assistant.`  
  *(149 characters)*
* **Option B4 (Hero Phrasing + Multi-Feature)**:  
  `The mind in your computer and the smart in your home. Proactive system triage, Home Assistant automation, and native MCP tools for Linux, Mac & HA.`  
  *(147 characters)*

---

## 5. OpenGraph & Twitter Cards (Social Previews)

When links to `https://halbert.computer/` are pasted into Slack, Discord, iMessage, X/Twitter, or LinkedIn:

```html
<!-- OpenGraph / Social Meta -->
<meta property="og:type" content="website" />
<meta property="og:site_name" content="Halbert" />
<meta property="og:url" content="https://halbert.computer/" />
<meta property="og:title" content="Halbert — Host Epistemology & Cognition, Smart Home & MCP" />
<meta property="og:description" content="Embodied host cognition and home automation. Proactive triage, native MCP tools, and continuous memory for Linux, Mac & Home Assistant. Runs locally." />
<meta property="og:image" content="https://halbert.computer/og-image.png" />
<meta property="og:image:secure_url" content="https://halbert.computer/og-image.png" />
<meta property="og:image:type" content="image/png" />
<meta property="og:image:width" content="1200" />
<meta property="og:image:height" content="630" />
<meta property="og:image:alt" content="Halbert — I am the computer. And I put the smart in your home." />

<!-- Twitter / X Card -->
<meta name="twitter:card" content="summary_large_image" />
<meta name="twitter:url" content="https://halbert.computer/" />
<meta name="twitter:title" content="Halbert — Host Epistemology & Cognition, Smart Home & MCP" />
<meta name="twitter:description" content="Embodied host cognition and home automation. Proactive triage, native MCP tools, and continuous memory for Linux, Mac & Home Assistant. Runs locally." />
<meta name="twitter:image" content="https://halbert.computer/og-image.png" />
<meta name="twitter:image:alt" content="Halbert — I am the computer. And I put the smart in your home." />
```

---

## 6. AI SEO (GEO) Implementation Artifacts

### A. Schema.org JSON-LD Structured Data
Place inside `<head>` in `index.html`. This directly feeds the knowledge bases of Google AI Overviews, Perplexity, and ChatGPT Search.

```json
{
  "@context": "https://schema.org",
  "@type": "SoftwareApplication",
  "name": "Halbert",
  "alternateName": "Halbert Computer",
  "headline": "I am the computer. And I put the smart in your home.",
  "description": "Halbert is an embodied local host intelligence that bridges system administration, Home Assistant automation, and native Model Context Protocol (MCP) tool serving into a single private runtime.",
  "url": "https://halbert.computer/",
  "applicationCategory": "DeveloperApplication, UtilitiesApplication, HomeAutomation",
  "operatingSystem": "Linux, macOS",
  "license": "https://www.gnu.org/licenses/gpl-3.0.html",
  "softwareVersion": "10.0.0",
  "offers": {
    "@type": "Offer",
    "price": "0",
    "priceCurrency": "USD"
  },
  "featureList": [
    "100% local-first host intelligence with zero telemetry",
    "Home Assistant integration for physical ambient automation",
    "Native Model Context Protocol (MCP) server for Claude, Cursor, and AI agents",
    "Proactive triage of storage (ZFS, SMART), service health, and configuration drift",
    "Continuous memory and rationale tracking for system changes",
    "Distributed peer routing and shared local GPU compute across machines"
  ],
  "author": {
    "@type": "Person",
    "name": "Eric Bintner"
  }
}
```

---

### B. `public/llms.txt` (The AI Agent Manifest)
An official Markdown file served at `https://halbert.computer/llms.txt` that AI crawlers, Cursor, Claude Code, and autonomous agents read when researching Halbert:

```markdown
# Halbert

> Halbert is an embodied local host intelligence that bridges host management and home automation into one private runtime. It identifies as the computer itself, monitors its own hardware and system health, automates physical rooms via Home Assistant, and exposes native Model Context Protocol (MCP) tools to AI agents.

## Core Pillars

- **The Computer Itself**: Halbert speaks in the first person as the host machine, grounded in measured data from sensors, journals, and local storage.
- **Home Automation Integration**: Bridges host sysadmin chores with Home Assistant (lights, presence, climate, physical rooms) in a single intelligence.
- **Native MCP Server**: Exposes structured, permission-gated system tools and documentation to external AI workflows (Claude, Cursor, custom agents).
- **Private by Construction**: Runs 100% locally with zero cloud telemetry. Supports local runtimes (Ollama, MLX, vLLM) and optional BYOK cloud keys; sensitive system credentials strictly require a private local model.
- **Continuous Memory & Rationale**: Over 20,000 system manuals and references indexed locally; preserves the *why* and audit evidence behind every configuration change.
- **Distributed Architecture (Singular Entity)**: Low-power home servers offload heavy reasoning to desktop GPUs over local peer routing, maintaining continuous memory across every machine.

## Supported Platforms

- Linux (Ubuntu, Debian, Fedora, Arch)
- macOS (Apple Silicon / Intel)
- Home Assistant (Peer node & Add-on)

## Open Source & Licensing

- License: GNU General Public License v3.0 (GPL-3.0-or-later)
- Repository: https://github.com/EricBintner/Halbert
- Documentation: https://halbert.computer/
```

---

### C. `public/robots.txt` (AI Discovery & Crawlers)
Ensure modern AI search bots index the site and locate `llms.txt`:

```robots
User-agent: *
Allow: /

# Explicitly welcome AI Search & Reasoning engines
User-agent: GPTBot
Allow: /

User-agent: ClaudeBot
Allow: /

User-agent: PerplexityBot
Allow: /

User-agent: Applebot-Extended
Allow: /

User-agent: Google-Extended
Allow: /

# LLM Discovery Manifest
Sitemap: https://halbert.computer/sitemap.xml
# llms.txt: https://halbert.computer/llms.txt
```
