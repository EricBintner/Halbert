# Results — Metadata, Social & AI-SEO (GEO) Review

**Date:** 2026-09-14
**From:** metadata/AI-SEO factual review session
**Status:** LANDED (fixes applied, dist rebuilt, live-verified on the dev server) — open items in §6
**Target surface:** `documentation/marketing/METADATA-AND-AI-SEO.md` (spec), `marketing/web-v10/index.html`, `public/llms.txt`, `public/robots.txt`, `dist/` (rebuilt)
**Method:** same as the v10 copy review — extract every claimable statement, verify against codebase ground truth, then standards-check the machine-readable surfaces against schema.org, OpenGraph/Twitter, robots.txt semantics, and llms.txt's published spec.

---

## 1. What held up (verified)

- **Canonical long description** — every clause traces to code verified in the
  2026-09-14 copy review: HA bridge (REST client + occupancy), first-person
  identity, proactive triage (findings/events), room automation (`ha_call_service`),
  native MCP server (~20 tools), federated GPU offload (compute broker), zero
  telemetry (no analytics deps; federation telemetry is peer-to-peer).
- **Character envelopes** — title is 57 chars (spec said 56; corrected in the
  spec), description is exactly 147. Both fit social-card envelopes.
- **og:image** — 1200×630 verified on disk, matches the declared
  `og:image:width/height`; square 1200×1200 variant exists but is unused by any
  tag (fine).
- **JSON-LD is well-formed**, uses real schema.org properties throughout:
  `softwareVersion`, `featureList`, `offers(Offer/price/priceCurrency)`,
  `operatingSystem`, `license` (URL form), `keywords`, `author(Person)`.
  `headline` is inherited-valid from CreativeWork (SoftwareApplication is a
  CreativeWork subtype) — unconventional but legal.
- **`applicationCategory: "DeveloperApplication, UtilitiesApplication, HomeAutomation"`**
  — schema.org's expected type for this property is free-form Text ("Type of
  software application, e.g. 'Game, Multimedia'"), and their own example shows a
  comma string. Valid as written.
- **Pillar 4 naming "Claude, Cursor, and autonomous AI agents"** — covered by the
  founder's 2026-09-14 ruling (unversioned client names acceptable; versioned
  model names never).
- **"Indexes thousands of local system manuals"** — survives the copy review's
  finding: 24,731 docs union on disk; "thousands" is true at every per-install
  floor (Linux ~9.8k).

## 2. Findings, dispositions, and applied fixes

### M1 (High) — `softwareVersion: "10.0.0"` was false
The product version is **0.1.1** (`halbert_core/pyproject.toml`, `__init__.py`,
`tauri.conf.json` all say 0.1.1). "10.0.0" appears to be the *site generation*
number (web-v10) leaking into the product schema — the exact class of number
drift the copy review flagged elsewhere.
**Applied:** JSON-LD now says `"softwareVersion": "0.1.1"` (source + dist + spec).

### M2 (High) — robots.txt omitted OpenAI's *search* crawler
The file welcomed `GPTBot` (OpenAI model **training**), `ClaudeBot`,
`PerplexityBot`, `Applebot-Extended`, `Google-Extended` — but not
`OAI-SearchBot`, the bot that surfaces sites in **ChatGPT search results**
([OpenAI's bot docs](https://developers.openai.com/api/docs/bots) are explicit
about the split). The wildcard `User-agent: *` already allowed it, so this was
signaling, not blocking — but a file whose whole purpose is to "explicitly
welcome AI search engines" should name the search engine's search bot.
**Applied:** `OAI-SearchBot` block added, with comments identifying each bot's
role (also synced to the spec doc).

### M3 (High) — Spec promised a sitemap; none existed
The spec's robots.txt block includes `Sitemap: https://halbert.computer/sitemap.xml`,
but (a) the shipped robots.txt **dropped the Sitemap line**, and (b) no
sitemap.xml existed anywhere — the reference 404s.
**Applied:** created `public/sitemap.xml` (index, privacy, terms — the three
crawlable pages), restored the `Sitemap:` line to robots.txt, verified served as
`text/xml` with 3 URLs. Synced the spec. Note: `changefreq`/`priority` are
ignored by modern engines; kept minimal.

### M4 (Medium) — "package conflicts" pillar overstated
The JSON-LD featureList and llms.txt said Halbert "continuously diagnoses …
package conflicts." The package scanner detects: updatable packages, **held
packages** (`apt-mark showhold`), and **stale package-manager lock files**
(dpkg/apt/yum/rpm/pacman lock checks with fuser staleness detection) — but has
no dependency-conflict/broken-deps diagnosis (S10.10 is an aspirational comment
in the scanner header, not code).
**Applied:** both surfaces now say "held packages, and stale package-manager
locks" — what the code actually does. Spec synced.

### M5 (Medium) — "macOS (Apple Silicon / Intel)" ambiguous
llms.txt listed Intel as co-equal. Reality: MLX (the recommended provider on
Apple Silicon) is arm-only; Intel Macs are supported through the generic local
runtimes (Ollama et al.) — `get_recommended_provider()` itself says "Ollama
works well on Linux and Intel Mac."
**Applied:** "macOS (Apple Silicon; Intel supported via local runtimes)."

### M6 (Medium) — "Home Assistant (Peer node & Add-on)" — Add-on doesn't exist
The HA add-on is *planned external infrastructure* (`FDR-09`: the
`halbert-ha-addon` public repo is an open item; ROADMAP §4 lists it as "next,"
not built). The peer-node path is real today (HA REST client + MCP HA tools +
fleet pairing). Stating "Add-on" as present fact repeats the same
present-tense-for-planned-features error as the Pro/commercial copy fixed
earlier today.
**Applied:** "Home Assistant (peer node)" in llms.txt; spec synced.

### M7 (Low) — `<meta name="title">` never existed
The spec §3 showed it; no build ever contained it (verified across source and
dist). It's also non-standard — `<title>` is the only title tag engines read.
**Applied:** spec corrected (also fixed the "56 characters" label → 57, the
actual length).

### M8 (Low) — spec drift between §2 pillar table and shipped text
The spec's own pillar table still carried pre-unification wording in two rows
while claiming "Approved & Implemented." §3/§4 blocks now match the shipped
files exactly; the §2 table rows for pillar 2 updated to match.

## 3. Best-practices observations (no change required, worth knowing)

1. **The SPA is nearly invisible to AI crawlers without the head.** The v10 app
   renders all copy client-side (React/Vite); AI crawlers overwhelmingly do not
   execute JavaScript (OpenAI's own bot docs describe fetch-and-parse, and
   GPTBot is documented without rendering capability). This makes the
   `<head>` metadata + JSON-LD + llms.txt effectively the *entire* AI-visible
   content of the site — which validates the spec's "unified copy architecture"
   approach: these surfaces aren't complements to the page, they *are* the page
   for GEO purposes.
2. **No `<h1>` and no `<noscript>` fallback exist.** A JS-disabled crawler or
   user sees an empty `<div id="root">`. A `<noscript>` block with the canonical
   headline + short description + GitHub link would make the page meaningful
   without JS at near-zero cost. (Eric's call — the design is
   scroll-choreography-first; a noscript block is invisible to normal users.)
3. **llms.txt is a bet, not a guarantee.** The [llms.txt spec](https://llmstxt.org/)
   (v2, revised Aug 2026) reports ecosystem adoption ("thousands of sites,"
   Mintlify/GitBook/Wix auto-generation, Lighthouse auditing for one) — but
   names **no search engine that consumes llms.txt automatically today**. Its
   value for Halbert: ChatGPT/Perplexity search indexing of the head +
   JSON-LD is the *realistic* AI-SEO channel; llms.txt is cheap, spec-conformant
   (H1 + blockquote + H2 sections ✓), and future-proofs the manual's structure.
   Keep it, don't count on it.
4. **JSON-LD could carry more without risk**: `screenshot`, `downloadUrl`
   (GitHub releases), `datePublished`/`dateModified` (CreativeWork-inherited),
   and `isAccessibleForFree: true` are all valid SoftwareApplication properties
   that map to real facts. Deferred — current form is already rich; adding is
   mechanical.
5. **`offers.price "0"`** is accurate today (free/OSS core; Pro undecided — see
   the monetization handoff). If Pro ships, this becomes an `AggregateOffer`
   or the Pro product gets its own page/schema; do not edit this until FDR-04
   lands.
6. **Twitter card validators**: `twitter:url` is non-standard (X ignores it;
   the page URL comes from the card's page). Harmless. `summary_large_image`
   with the 1200×630 image is correct.
7. **Netlify headers** (`X-Frame-Options: DENY`, `nosniff`,
   `strict-origin-when-cross-origin`) are solid; robots/llms/sitemap all get
   `Cache-Control: max-age=0, must-revalidate` under the `/*` rule — fine
   (they must update on deploy).

## 4. Changes applied this session

| File | Change |
|---|---|
| `marketing/web-v10/index.html` | JSON-LD `softwareVersion` → `0.1.1`; pillar-2 wording → "held packages, stale package-manager locks" |
| `marketing/web-v10/public/llms.txt` | Same pillar-2 wording; macOS line → "Apple Silicon; Intel supported via local runtimes"; HA line → "peer node" (Add-on removed) |
| `marketing/web-v10/public/robots.txt` | `OAI-SearchBot` block added; `Sitemap:` line restored; per-bot comments |
| `marketing/web-v10/public/sitemap.xml` | **New** — index/privacy/terms |
| `documentation/marketing/METADATA-AND-AI-SEO.md` | All of the above synced; `<meta name="title">` removed from the spec block; title length corrected 56 → 57; §2 pillar table row synced |
| `marketing/web-v10/dist/` | Rebuilt (`npm run build`), all fixes verified in the built artifacts |

All verified live on the dev server: robots.txt carries Sitemap + OAI-SearchBot;
sitemap.xml serves `text/xml` with 3 URLs; llms.txt carries the new platform
lines and no "package conflicts"; JSON-LD parses with version 0.1.1.

## 5. Deployment note

`dist/` is gitignored and regenerated by the Netlify build from the deployed
ref — but the repo *does* carry a `dist/` snapshot (from the metadata commits)
which is now updated locally. The next `scripts/deploy.sh` run publishes all of
this. The rebuilt dist was produced with the same Vite version as CI.

## 6. Open items (Eric's call or future session)

1. **`<noscript>` fallback** (§3.2) — recommend adding: headline + description +
   GitHub link, one block, invisible to JS users. Awaiting founder ok.
2. **JSON-LD enrichment** (§3.4) — screenshot/downloadUrl/dates; mechanical,
   deferred until product screenshots exist.
3. **The spec's "Approved & Implemented" status line** — after this session it
   is true again, but the doc has now drifted twice in one day (the robots/llms
   drift was the same failure mode as the copy drift: spec written, then
   implementation edited without back-sync). Recommend the spec block-quote the
   *files* (or be generated) rather than duplicating them.
4. **`offers`** — revisit when FDR-04 (monetization) lands; see
   `HANDOFF-MONETIZATION-PLAN-REVIEW-2026-09-14.md`, now superseded by
   `RESULTS-MONETIZATION-PLAN-REVIEW-2026-09-14.md`.
5. **Title A/B** — "Host Epistemology & Cognition" is differentiated but jargon-
   dense for a title tag; the meta description carries the plainer hook. No
   data to act on pre-launch; noted for post-launch iteration.

---

## 7. Addendum (same day): feature-reference metadata suite + page parity

Founder directive: apply the same metadata/AI-SEO treatment to the feature
website (`marketing/feature-reference` — the "details page" companion), reusing
the canonical copy with a re-scope to clarify it is a reference page; and
complete the sub-pages of the main site.

### Applied to `marketing/feature-reference`

- **index.html head rewritten**: same canonical copy, re-scoped title
  ("Halbert Feature Reference — the details behind every capability") and
  description ("The reference details page for Halbert: all 44 features, how
  each works, which files implement it, and its safety boundaries…");
  canonical + OG/Twitter full set (`og:site_name`, `og:image` 1200×630 with
  alt + secure_url + type, `twitter:card`) pointing at
  `https://halbert.computer/features/` (placeholder — see open item 8).
- **JSON-LD**: `@type: ItemPage` (a details page about the product) with
  `isPartOf: WebSite(halbert.computer)`, `about: SoftwareApplication` (the
  product entity stays on the site root), and `mainEntity: ItemList` of all
  44 catalog features with one-line descriptions — **generated from
  `src/catalog.json`**, not hand-typed.
- **`public/llms.txt`**: generated from the catalog — H1, blockquote carrying
  the canonical long description re-scoped for the reference page, all 44
  features grouped by the 8 categories (hidden/deferred statuses annotated),
  platform lines, licence. Conforms to the llms.txt v2 shape (H1 + blockquote
  + H2 sections).
- **`public/robots.txt`**: same AI-crawler welcome as the main site (incl.
  `OAI-SearchBot`), sitemap at the `/features/` path.
- **`public/sitemap.xml`**: single URL, `/features/`.
- **Google Fonts CDN removed** — the old head loaded Fraunces/Space
  Grotesk/JetBrains Mono from `fonts.googleapis.com` *while also* self-hosting
  the same faces; a local-first product shipping a page that phones Google's
  CDN was both a brand contradiction and a double font load. All faces now
  self-hosted only (Fraunces preload added); verified 200s and correct
  rendering with CDN links gone.
- **Favicon set copied** from web-v10 (16/32/ico/apple-touch, `?v=4` cache
  busting) and og-image copied (absolute URL in meta, so it also works
  cross-site).
- **`scripts/sync_fonts.py`**: `marketing/feature-reference/public/fonts` added
  to CONSUMERS — its fonts previously existed on disk from one manual copy and
  were covered by no sync/CI check; now `--check` passes across 5 consumers.
- **`.claude/launch.json`**: `marketing-feature-reference` dev-server config
  added (port 5189, autoPort).

### Applied to the main site's sub-pages

`privacy.html` / `terms.html` got the missing tags to match the index:
`og:site_name`, `og:image:secure_url`, `og:image:type`, `og:image:alt`,
`twitter:image:alt`. (They already had page-scoped titles/descriptions,
canonicals, `og:type article`, and `twitter:card` — left as-is.)

### Catalog factual fix (found by the manifest generation)

`src/catalog.json` feature 23 was **"14,000+ Indexed Documents"** — the same
stale corpus number the earlier reviews corrected (real union today: 24,731).
Fixed in the catalog itself (the UI renders from it):
name → "Thousands of Indexed Documents"; oneLine dropped "Stack Exchange"
(see open item 9). The generated llms.txt and JSON-LD therefore carry no
stale number.

### Spec updated

`documentation/marketing/METADATA-AND-AI-SEO.md` gained §0 (per-surface title/
description rules table, derivation rules, and the generate-don't-hand-write
note for the feature site's manifest and ItemList).

### Verification

All checks live on the dev server (port 5189): title/canonical/og present;
JSON-LD parses as ItemPage with 44 items; robots.txt has Sitemap +
OAI-SearchBot; sitemap serves as XML; llms.txt has the corrected feature list;
fonts (incl. Fraunces) serve 200 with the CDN links removed; the app renders
correctly. `dist/` rebuilt and re-verified.

### Open items (continued)

8. **Feature-site URL** — `https://halbert.computer/features/` is a placeholder
   decision (subpath of the main domain). No prior decision exists anywhere
   in the repo. Wiring it means either a second Netlify site + a path-based
   Cloudflare rule, or (simpler) publishing the built feature-reference
   `dist/` as a subdirectory of the main site's deploy. Founder call needed;
   canonical/OG URLs must be updated in one commit with whatever lands.
9. **Stack Exchange sources** — dropped from the catalog oneLine because the
   current `data/manifest.json` has no Stack Exchange source (sources: Arch
   Wiki, man pages, TLDR, common tools, vendor docs, Homebrew, macOS support,
   Ask Different, MacPorts, FreeBSD). If Stack Exchange content was removed
   in a corpus cleanup, the `howItWorks` text mentioning it should also be
   reviewed by the corpus owner.
10. **Cross-linking** — neither site links to the other yet (v10's footer has
    no features link; the feature site has no "back to halbert.computer" CTA).
    Natural pairing once the URL decision (item 8) lands: add a
    "Full feature reference →" link to the v10 reveal section and a
    "← Back to Halbert" header link on the feature site.