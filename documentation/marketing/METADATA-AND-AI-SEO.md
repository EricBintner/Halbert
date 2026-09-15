# Halbert — Website Metadata, Social Sharing & AI SEO (GEO) Specification

**Document Status:** Approved & Implemented  
**Date:** 2026-09-14  
**Target Surface:** `marketing/web-v10` (`index.html`, `public/llms.txt`, `public/robots.txt`)  

---

## 1. Approved Social & Search Copy

These selections are live in `marketing/web-v10/index.html`:

### Page Title & OpenGraph/Twitter Title
```text
Halbert — Host Epistemology & Cognition, Smart Home + MCP
```
- **Length:** 56 characters.
- **Envelope:** Exactly fits the 56–58 character two-line envelope on mobile Twitter/X link cards without trailing ellipsis truncation.
- **Keywords:** Names the host cognition layer, smart home integration, and native MCP capability.

### Meta Description & OpenGraph/Twitter Description (Option B4)
```text
The mind in your computer and the smart in your home. Proactive system triage, Home Assistant automation, and native MCP tools for Linux, Mac & HA.
```
- **Length:** 147 characters (optimal for the 140–160 search/social preview budget).
- **Core Pillars:**
  1. *Host identity:* "The mind in your computer and the smart in your home."
  2. *Triage:* "Proactive system triage"
  3. *Physical Automation:* "Home Assistant automation"
  4. *Agent Tooling:* "native MCP tools"
  5. *Platforms:* "for Linux, Mac & HA" (omits unreleased Windows).

---

## 2. Production HTML Snippet (`index.html`)

The following tags are implemented in `<head>`:

```html
<!-- Primary Meta Tags -->
<title>Halbert — Host Epistemology &amp; Cognition, Smart Home + MCP</title>
<meta name="title" content="Halbert — Host Epistemology &amp; Cognition, Smart Home + MCP" />
<meta name="description" content="The mind in your computer and the smart in your home. Proactive system triage, Home Assistant automation, and native MCP tools for Linux, Mac &amp; HA." />
<link rel="canonical" href="https://halbert.computer/" />

<!-- OpenGraph / Facebook / LinkedIn / Discord -->
<meta property="og:type" content="website" />
<meta property="og:site_name" content="Halbert" />
<meta property="og:url" content="https://halbert.computer/" />
<meta property="og:title" content="Halbert — Host Epistemology &amp; Cognition, Smart Home + MCP" />
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
<meta name="twitter:title" content="Halbert — Host Epistemology &amp; Cognition, Smart Home + MCP" />
<meta name="twitter:description" content="The mind in your computer and the smart in your home. Proactive system triage, Home Assistant automation, and native MCP tools for Linux, Mac &amp; HA." />
<meta name="twitter:image" content="https://halbert.computer/og-image.png" />
<meta name="twitter:image:alt" content="Halbert — I am the computer. And I put the smart in your home." />
```

---

## 3. What is AI SEO (Generative Engine Optimization)?

Traditional SEO focuses on Google keywords, backlinks, and meta tags. **AI SEO (GEO)** focuses on how Large Language Models (LLMs) and conversational search engines (Perplexity, ChatGPT Search, Claude, Gemini, Apple Intelligence) ingest, understand, cite, and recommend software:

1. **`llms.txt` Standard**: An emerging, cross-industry specification (originated by Answer.ai, adopted by Anthropic, Perplexity, Cursor, Cloudflare, etc.). It lives at `/llms.txt` and gives AI assistants a clean, Markdown-formatted manifest explaining what Halbert is, its capabilities, architecture, and documentation.
2. **Schema.org Structured Data (`JSON-LD`)**: Embedded in HTML `<script type="application/ld+json">`. LLMs and knowledge graphs extract machine-readable entities (`SoftwareApplication`, `HomeAutomation`, `DeveloperApplication`, `GPL-3.0-or-later`).
3. **Information Density & Factual Grounding**: AI engines reward concrete, authoritative declarations of architecture, constraints, and features (*"Zero telemetry"*, *"Requires local model for credentials"*, *"Native MCP server"*, *"Home Assistant integration"*).
4. **AI Crawler Hygiene (`robots.txt`)**: Explicitly permitting AI search indexers (`GPTBot`, `ClaudeBot`, `PerplexityBot`, `Applebot-Extended`, `Google-Extended`).

---

## 4. AI SEO (GEO) Implementation Artifacts

### A. Schema.org JSON-LD Structured Data
Implemented in `<head>` in `marketing/web-v10/index.html`:

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

### B. `marketing/web-v10/public/llms.txt`
Served at `https://halbert.computer/llms.txt` for AI crawlers, Cursor, Claude Code, and autonomous agents:

```markdown
# Halbert

> Halbert is an embodied local host intelligence that bridges host management and home automation into one private runtime. It identifies as the computer itself, monitors its own hardware and system health, automates physical rooms via Home Assistant, and exposes native Model Context Protocol (MCP) tools to AI agents.

## Core Pillars

- **The Computer Itself**: Halbert speaks in the first person as the host machine, grounded in measured data from sensors, journals, and local storage.
- **Home Automation Integration**: Bridges host sysadmin chores with Home Assistant (lights, presence, climate, physical rooms) in a single intelligence.
- **Native MCP Server**: Exposes structured, permission-gated system tools and documentation to external AI workflows (Claude, Cursor, custom agents).
- **Private by Construction**: Runs 100% locally with zero cloud telemetry. Supports local runtimes (Ollama, MLX, vLLM) and optional BYOK cloud keys; sensitive system credentials strictly require a private local model.
- **Continuous Memory & Rationale**: Thousands of system manuals and references indexed locally; preserves the *why* and audit evidence behind every configuration change.
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

### C. `marketing/web-v10/public/robots.txt`
Permits AI search indexers to crawl and discover `llms.txt`:

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

---

## 5. Rationale & Decision History

- **Why Title `Halbert — Host Epistemology & Cognition, Smart Home + MCP`**: Fits within 56 characters, avoiding mobile preview card clipping on Twitter/X, while packing high-intent search signals (Host Epistemology, Smart Home, MCP).
- **Why Description Option B4**: Previous drafts spent too much character budget repeating "private local models, zero telemetry". Option B4 captures the identity hook (*"The mind in your computer and the smart in your home"*), triage capability, Home Assistant, and native MCP tools in 147 characters.
- **Platform Scope**: Windows was intentionally excluded as it is deferred to a future milestone; platform scope is locked to `Linux, Mac & HA`.
