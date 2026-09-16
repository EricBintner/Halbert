# Research — Public-Facing Storybook Audit & Gap Analysis

**Date:** 2026-09-15
**From:** Storybook public-publish feasibility review
**Status:** AUDIT COMPLETE — external best-practices research in flight (see §5)
**Resolution (2026-09-16):** §3's branding rows are implemented per
`documentation/design/STORYBOOK-CHROME-AND-ICON-DOCK-2026-09-16.md`. Still open
from §3: Welcome/MDX pages and CI deploy (founder: deploy is out of scope for now).
**Target surface:** `packages/design-system/.storybook/` (config), `packages/design-system/src/stories/` (stories), `.github/workflows/ci.yml` (deploy)
**Question asked:** Can we post our Storybook publicly online, and what does standard practice include that we're missing?

---

## 0. TL;DR

- **Yes, publishing is fine.** The repo is GPL-3.0-or-later OSS; the Storybook is a compiled view of `packages/design-system/src/` (a shipping package). No secrets, internal URLs, API keys, or endpoint references exist in any story file — the only URL in any story is `https://example.com` (a placeholder in `Agent.stories.tsx:46`).
- **What we have today is a well-built private component playground**, not a public design-system documentation site. The gap is in documentation, branding, SEO, and deploy automation — not in anything that would be dangerous to expose.
- **The story source IS the component source.** A built Storybook exposes the React component API (props, variants, token names) that's already in the public repo. Publishing it reveals nothing that `git clone` wouldn't.

---

## 1. What we verified about the current setup

### Storybook location and config
- `packages/design-system/.storybook/main.ts` — Storybook 8.4.7, React-Vite framework, addons: essentials + a11y. Telemetry disabled (`core: { disableTelemetry: true }`).
- `packages/design-system/.storybook/preview.tsx` — custom theme decorator that sets `data-theme` on `<html>` (the real token switch). Storybook's `backgrounds` addon intentionally disabled — the comment explains why: painting a background swatch while leaving tokens on light values is how dark mode ships broken. Global type `theme` with toolbar toggle: Daylight / After hours. Story sort order: Brand → Design Tokens → Primitives → Surfaces → Modules → Voice → Drafts.
- `packages/design-system/.storybook/preview-head.html` — loads self-hosted fonts from `/fonts/fonts.css` (synced from `/shared-tokens/fonts` by `scripts/sync_fonts.py`). No CDN dependency.
- `public/` — custom favicons (favicon.svg, .ico, apple-touch-icon.png, 16×16, 32×32) and `fonts/` directory with MANIFEST.json, OFL-1.1 licence, woff2 files.

### Stories (9 files, 1,786 lines, 47 stories)
| File | Stories | Section |
|------|---------|---------|
| `BrandMark.stories.tsx` | 3 | Brand |
| `Tokens.stories.tsx` | 4 | Design Tokens |
| `Primitives.stories.tsx` | 9 | Primitives |
| `Surfaces.stories.tsx` | 3 | Surfaces |
| `Modules.stories.tsx` | 2 | Modules |
| `NavRail.stories.tsx` | 3 | (untitled — no `title:` in meta, falls to default) |
| `Agent.stories.tsx` | 13 | Agent |
| `AudioReactiveHalbertMark.stories.tsx` | 8 | Voice |
| `HalbertMark.stories.tsx` | 2 | Drafts |

### Build
- `npm run build-storybook` → `storybook-static/` (6.7 MB, already exists in the working tree).
- Built `index.html` uses relative asset paths (`./`) — compatible with GitHub Pages subpath hosting.
- CI (`.github/workflows/ci.yml:158`) runs `npm run build-storybook -- --quiet` but **does not deploy** the output anywhere. `storybook-static` is in the CI upload artifact exclusion list (line 34).

### Security scan (all 9 story files)
Scanned for: `http://`, `https://`, `api_key`, `secret`, `token`, `password`, `localhost:PORT`, `127.0.0.1`, `BEGIN PRIVATE`, `endpoint`, `relay`, `proxy`.
- **Only hit:** `https://example.com` (placeholder in `Agent.stories.tsx:46`) and the string `"secret viewer"` in a `ModuleLoadError` demo label (`Agent.stories.tsx:100`).
- **Zero secrets, zero internal URLs, zero endpoint references.** Clean.

---

## 2. What we already do well (above the bare minimum)

| Feature | Status | Location |
|---------|--------|----------|
| Accessibility addon (a11y) | ✅ | `main.ts` |
| Theme switching (light/dark) | ✅ | `preview.tsx` — proper `data-theme`, not broken backgrounds-paint |
| Telemetry disabled | ✅ | `main.ts` |
| Self-hosted fonts (not CDN) | ✅ | `preview-head.html` + `public/fonts/` |
| Custom favicons (full set) | ✅ | `public/` |
| Build in CI | ✅ | `ci.yml:158` |
| Relative asset paths | ✅ | built `index.html` uses `./` |
| Build size | ✅ | 6.7 MB |
| Story sort order | ✅ | `preview.tsx` |

---

## 3. What we're missing vs. standard public Storybook practice

| Gap | Impact | Effort |
|-----|--------|--------|
| **Page `<title>` is `@storybook/core - Storybook`** | The default. Every public Storybook customizes this. | Trivial — `manager-head.html` or `preview-head.html` |
| **No SEO/meta** — no `<meta name="description">`, no `og:`/`twitter:` tags, no `og:image` | Not discoverable; shared link previews are blank. We already have og:image assets from the marketing site (1200×630 verified). | Small — `preview-head.html` |
| **No Welcome/Intro page** | Visitors land on the first story with zero context about what Halbert is. | Medium — one MDX file |
| **No autodocs** — `tags: ['autodocs']` appears in zero story files | No auto-generated ArgsTable / controls / prop docs. This is the single most valuable feature of a public Storybook. | Small — add tag to each meta |
| **No MDX documentation pages** — zero `.mdx` files exist | No usage guidelines, no install instructions, no design principles, no do/don't examples. | Medium — write per-component docs |
| **No custom Storybook chrome branding** — no `manager.ts` or `manager-head.html` | The Storybook sidebar/header uses default Storybook branding, not Halbert's Olivetti Vermilion & Bone. | Small-medium |
| **No links back to GitHub repo / source** | Visitors can't find the source or contribute. | Small — `manager-head.html` or MDX |
| **No CI auto-deploy** — CI builds but doesn't publish | No automated path to a public URL. | Medium — GitHub Actions workflow |
| **`NavRail.stories.tsx` has no `title:` in meta** | Story falls into an unnamed/default section, breaking the curated sort order. | Trivial — add `title: 'Surfaces/NavRail'` |

---

## 4. The gap in one sentence

We have a well-built **private component playground** — solid theme switching, a11y, self-hosted fonts — but it's missing everything that turns a Storybook into a **public-facing design system documentation site**: a branded intro page, autodocs with API tables, MDX usage docs, a custom page title, and an automated deploy pipeline.

---

## 5. External research — IN FLIGHT

A research agent was spawned in the 2026-09-15 session to gather concrete best-practice examples from well-known public Storybooks (GitHub Primer, Shopify Polaris, Adobe Spectrum, IBM Carbon, BBC, etc.) covering:

1. Real examples of public Storybooks and what makes each notable.
2. Standard inclusions beyond stories (MDX docs, theme toggles, a11y visibility, token pages, API docs, changelogs, source links, SEO).
3. Hosting/deploy patterns (GitHub Pages, Vercel, Netlify, Chromatic; CI/CD workflows; base-path gotchas).
4. What separates a "good" public Storybook from a bare one.
5. Chromatic vs self-hosting tradeoffs.
6. Gotchas (base path, source exposure, telemetry, build size, crawling).
7. Storybook 8.x features relevant to public deploys.

**The agent had not returned results when this handoff was written.** The next session should check for its output or re-run the research, then synthesize a concrete implementation plan from the combined audit (§1–§3) + research findings.

---

## 6. Recommended next steps (pending research synthesis)

1. **Add `tags: ['autodocs']`** to every story meta — instant ArgsTable + controls for all 47 stories. Lowest effort, highest value.
2. **Write a Welcome/Intro MDX page** — what Halbert is, the design system's scope (Olivetti Vermilion & Bone), how to install the package, link to GitHub.
3. **Fix the page title and add SEO meta** in `preview-head.html` — `<title>Halbert Design System</title>`, `<meta name="description">`, og/twitter tags. Reuse the 1200×630 og:image from the marketing site.
4. **Add `manager-head.html`** for Storybook chrome branding — set the title bar, add a GitHub link in the sidebar.
5. **Fix `NavRail.stories.tsx`** — add `title: 'Surfaces/NavRail'` to meta so it joins the curated sort order.
6. **Wire a CI deploy workflow** — build `storybook-static` on push to `main`, deploy to GitHub Pages (or Vercel/Netlify). Watch the base-path config (`basePath: '/Halbert/'` for GitHub Pages project sites).
7. **Decide hosting target** — GitHub Pages (free, lives under `ericbintner.github.io/Halbert/`), a custom subdomain (`design.halbert...`), or Chromatic (adds visual regression + review workflow but is a third-party service). This is a founder decision, not a technical one.

---

## 7. Pre-existing context this builds on

- The repo is GPL-3.0-or-later (`LICENSE`), with `LICENSE-EXCEPTION-APPSTORE` for the App Store distribution path.
- `packages/design-system` is one of the explicitly-shipping packages per CLAUDE.md — "independently consumable library, keep dependencies narrow enough to install standalone."
- The marketing site (`marketing/web-v10`) already has verified SEO/meta infrastructure (1200×630 og:image, JSON-LD, robots.txt, llms.txt) from the 2026-09-14 metadata review — assets and patterns can be reused for Storybook.
- The brand marks (7-line and 4-line) were ratified 2026-09-15 and already have Storybook stories (`BrandMark.stories.tsx`).