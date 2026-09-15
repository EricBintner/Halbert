# Results — v10 Marketing Website Factual Review

**Date:** 2026-09-14
**From:** v10 factual-claims review session
**Status:** LANDED (copy fixes applied) — open items listed in §6
**Scope:** every user-facing copy surface of `marketing/web-v10/` — storyboard stops
(`src/content/stops.jsx`), placeholder plates (`src/content/ui.jsx`), `index.html`
meta, `public/privacy.html`, `public/terms.html`, `netlify.toml` — cross-checked
against the codebase, `data/manifest.json`, `DECISIONS.md`, the live GitHub repo,
and the durable legal docs in `documentation/legal/`.

---

## 1. What was reviewed and how

Every claimable sentence was extracted, then verified against ground truth:

- Technical capability claims → `halbert_core/halbert_core/` source (MCP server
  tools, secure-model gate, HA client, storage auditor, provenance ledger,
  federation compute broker, VitalsModule).
- Corpus claims → `data/manifest.json` + actual `.jsonl` line counts on disk.
- Platform/licence claims → `utils/platform.py`, `LICENSE`, live
  `github.com/EricBintner/Halbert` (confirmed public, GPL-3.0).
- Commercial claims → `DECISIONS.md` (`FDR-04`, `FDR-09`, the 2026-09-04
  macos-pro row) and `TASK-PACKET-06`.
- Privacy claims → `platform.py`/`paths.py` storage paths, `providers/__init__.py`,
  dependency tree, `security.py` scanner.

## 2. What held up (verified in code — no action)

| Claim | Ground truth |
|---|---|
| "give your AI tools MCP access to your systems, their configs and their hardware" | ~20 real MCP tools in `mcp/server.py` (vitals, discoveries, findings, config value/structure/diff/dependencies, knowledge search, scanner run, HA entities/services, autonomy level) |
| "sensitive system configs and credentials always require a private local model" | Real local-or-fail-closed gate at `dashboard/routes/agent.py:~652`; reality is stricter than copy (Tier 2 is a deterministic template, no model) |
| "Nothing leaves the machine unless you connect it" | Web search off by default (C3-08), cloud models opt-in |
| Zero telemetry | No analytics SDK in the dependency tree; `federation/telemetry_agent.py` is peer-to-peer (satellite → your own desktop's Fleet Cockpit), not cloud |
| "updates every 5s" vitals plate meta | Exact: `VitalsModule.tsx` `setInterval(fetchVitals, 5000)` |
| "I can turn out the lights for you" / dimming when you step away | Real HA REST client, `ha_call_service` with `light.*`, occupancy model (`home/occupancy.py`) |
| "validating ZFS pools", SMART pending/reallocated sectors | `storage_auditor.py` runs `zpool status` / `smartctl`, flags attrs 5/197/198 |
| "I remember why you changed that" + evidence + snapshot | `continuity/provenance.py record_file_change` requires a `reason`; config snapshots exist |
| "offload heavy reasoning to your desktop GPU … one continuous memory" | Federation compute broker/router + peer provider (secure_model never offloads — `model/providers/peer.py` slot rules); canonical memory/thread URLs (`routes/peers.py`) |
| "Open source, GPL-3.0" + GitHub link | Repo public, `LICENSE` is GPL-3.0, terms say `-or-later` correctly |
| "Linux today, macOS in beta" | Consistent with channel state in DECISIONS |
| Corpus sources (man pages, Arch Wiki, Homebrew formulae, TLDR) | All present in `data/manifest.json` (Homebrew 8,777 docs) |

## 3. Findings and founder dispositions

### F1 (High) — Early-access form is fake
`stops.jsx` `EarlyAccessForm.onSubmit` checks `email.includes('@')`, sets state,
shows "✓ You're on the list. The build goes to your inbox." No fetch, no POST,
no Netlify Forms attribute, nothing in `netlify.toml`. Nobody is on any list, and
privacy §3.1 describes the collection as though it happens.

**Founder disposition (2026-09-14):** two-phase plan needed — (a) pre-launch
make the surface honest, (b) post-launch wire real collection. NOT applied in
this session; the plan is §6 item 1. Until wired, candidate honest states:
"Early access opens soon — watch GitHub" (link), or wire Netlify Forms (one
`data-netlify` attribute + build-plugin config) before the next deploy.

### F2 (High) — "Linux · Mac · Win · Home Assistant" claims Windows
Windows is deferred (`ROADMAP.md` §5, 2026-08-31 HA-strategy decision row).
Contradicts the site's own meta ("Linux today, macOS in beta") and the reveal
CTA ("Linux / macOS").

**Founder disposition:** drop "Win"; announce it later when real.
**Applied:** kicker now `Linux · Mac · Home Assistant` (`stops.jsx`).

### F3 (High) — Halbert Pro / LemonSqueezy stated as present fact; 3-device limit
Privacy §4 and Terms §2.2 used present tense for a Merchant of Record and a
3-device licence grant. `FDR-04` is **open** (price/update window/device
count/refund undecided; three conflicting drafts exist). The 2026-09-04 DECISIONS
row: the Pro channel "may build and pass its gates before its product has
commercial terms — which is the state today."

**Founder disposition:** 3-device limit is outdated thinking; should be at
least 5, maybe 10 — final number to be settled by the monetization review
(see `HANDOFF-MONETIZATION-PLAN-REVIEW-2026-09-14.md`).
**Applied:** both surfaces now future-tense ("planned … terms not yet final …
will be published on this page"), no device number published. `FDR-04`
remains the decision point; this copy keeps the site truthful while it stays
open.

### F4 (Medium) — "over 20,000 system references and docs"
Measured from `data/manifest.json` + on-disk `.jsonl`:
- Union corpus: 28,957 claimed / **24,731 real on disk**
- macOS build: 19,747 (253 short of 20,000)
- Linux build: 14,059 claimed / ~9,833 real (the known man-pages data bug:
  142 records on disk vs 4,368 in the manifest)
- A fresh `git clone` gets roughly half the corpus (13 untracked JSONL files
  incl. Arch Wiki + TLDR; RAG-13)

So "over 20,000" is true only of the union of both platform builds, which no
single install indexes.

**Founder disposition:** "maybe 'thousands'" for the headline.
**Applied:** headline now "I know thousands of system references and docs."
**Left open:** the KnowledgePlate still shows `24,643` RAG docs (`ui.jsx`) —
that's the Aug-25 stale count. Real union today: 24,731 (manifest 28,957).
Plate numbers should be regenerated from a real install before the plates are
replaced with animated library components (spec §8 already defers that swap).
A headline "over 20,000" becomes defensible again only under a corpus-framing
("built from a 20,000+ doc knowledge base") and after RAG-13's git-tracking fix.

### F5 (Medium) — Legal contact email on the wrong domain
Privacy contact was `privacy@halbert.net` while v10's canonical is
`halbert.computer` (v7/v9 and durable docs said `halbert.net`).

**Founder disposition:** generic address at halbert.computer for now; whole
email ecosystem revisited in a later session.
**Applied:** `hello@halbert.computer` in `privacy.html` (×2),
`documentation/legal/PRIVACY.md` (×3), `TERMS.md` contact. The `legal@halbert.net`
in TERMS.md was also updated for consistency. **Verification still needed** that
the mailbox actually exists/forwards — flagged as a deploy-gate item in §6.

### F6 (Medium) — Privacy §2.1 access list inaccuracies (3)
- "Shell history" — Halbert never reads shell history; the only code references
  are about *avoiding* leaking secrets into it. Removed.
- XDG paths stated as universal — they're Linux-only; macOS uses
  `~/Library/Application Support/Halbert/`. Now platform-split.
- "Google Gemini" as a cloud-key example — no native Google provider; supported
  set is Ollama / MLX / lm-studio / llamacpp local runtimes plus Anthropic,
  OpenAI, OpenRouter, Peer. Example list corrected. (Gemini is reachable only
  via OpenRouter, so as a "configure keys" example it was wrong.)
**Founder disposition:** provide updated copy — **applied**, same wording on
site and durable docs. Also confirmed accurate now: "environment variables"
stays (Halbert reads its own env overrides; `$PATH` examples in code exist in
scanner command paths).

### F7 (Medium) — sshd drop-in conflict plate isn't implemented
The ProactiveEventsPlate's first row shows a conflict "across sshd_config and a
drop-in … from `/etc/ssh/sshd_config.d/50-cloud.conf:12`", but
`discovery/scanners/security.py` reads only `/etc/ssh/sshd_config` — it never
reads `sshd_config.d/` drop-ins and has no conflict detection.

**Founder disposition:** "is this a feature that's not been implemented yet?
if so validate it's needed and add it to the todo list."
**Assessment:** yes, needed. OpenSSH on modern distros (Ubuntu 22.04+, Debian 12+,
Arch) reads drop-ins first and "first value wins" — a main-file
`PermitRootLogin no` silently loses to a drop-in, which is exactly the failure
mode the plate dramatizes, and the shipped scanner cannot see it. A
`sshd_config.d/` scan with effective-value resolution is a genuine triage gap
(aligns with ATTN-1's drop-in-conflict proof slice, which uses a synthetic
`/etc` drop-in for exactly this class of bug). Added to the backlog via a
background task and listed in §6 item 3.

### F8 (Medium) — "Claude · Cursor · Agents" tile vs the model-naming directive
The 2026-08-25 directive says "Never name or recommend AI models on any
user-facing surface." The tile names clients that connect *to* Halbert, not
models Halbert recommends — but needed an explicit founder ruling.

**Founder disposition:** no misunderstanding of the directive — the concern is
*staleness of versioned names* (e.g. a "Claude Opus 4.0"-style versioned tile
ages fast), not the word "Claude" itself. Unversioned product names are fine.
**Action:** none needed now — the tile says "Claude · Cursor · Agents" with no
versions. Standing rule going forward: never put a *versioned* model name on
any v10+ surface; client/product names unversioned are acceptable. Recorded in
§7 as a sharpened reading of the directive, saved to session memory.

### F9 (Low) — applied cleanups
- `⚠️` emoji in terms.html ("Critical Administrative Warning") — removed
  (no-emoji directive). The plates' `✓ ✕ ◷ ● ▲ ℹ` are typographic symbols, fine.
- Legal-page Last Updated bumped to September 14, 2026 on both site pages and
  both durable docs.

### F10 (Low) — noted, not changed (Eric's-call or benign)
- Meta description "100% local host intelligence" — conscious simplification;
  body copy qualifies it correctly ("Nothing leaves the machine unless you
  connect it").
- Privacy §2.3 "Halbert never proxies your cloud requests through intermediate
  Halbert servers" — `:cloud` models do traverse Halbert's own localhost relay
  by design; it's the user's own machine so the claim is true in spirit, but
  "never" is over-absolute. Revisit at the email/legal session.
- "Any LLM" (reveal CTA) vs a fixed provider set — OpenRouter fronts most
  models; loose, not false.
- Copyright footer "© 2024–2026" with a 2025-12-08 first commit — `FDR-05`
  already owns this; recommendation on the table is "keep 2024–2026".
  Left as is.
- `#EFECE5` hardcodes on the static legal pages (outside the token palette) —
  benign for unbundled pages; note for the colour ratchet owner.

## 4. Changes applied this session

| File | Change |
|---|---|
| `marketing/web-v10/src/content/stops.jsx` | Kicker `Linux · Mac · Win · Home Assistant` → `Linux · Mac · Home Assistant`; headline "over 20,000 system references and docs" → "thousands of system references and docs" |
| `marketing/web-v10/public/privacy.html` | §2.1: shell-history claim removed, storage paths platform-split (Linux XDG + macOS Library), provider examples corrected (Gemini → OpenRouter); §2.3 example keys list corrected; §4 re-titled "Commercial Purchases (Planned)" + future tense; contact email ×2 → `hello@halbert.computer`; Last Updated → Sept 14, 2026 |
| `marketing/web-v10/public/terms.html` | §2.2 future-tense, 3-device number removed; ⚠️ emoji removed; Last Updated → Sept 14, 2026 |
| `documentation/legal/PRIVACY.md` | Scope domain → `halbert.computer`; §2.1 same three access-list fixes; §2.3 example keys corrected; §4 future-tense "Planned"; emails ×3 → `hello@halbert.computer`; Last Updated → 2026-09-14 |
| `documentation/legal/TERMS.md` | Applies-to domain → `halbert.computer`; §2.2 future-tense, device count removed; contact email → `hello@halbert.computer`; Last Updated → 2026-09-14 |

Concurrent sessions were editing `stops.jsx` (phone-responsive classes) and
`terms.html` during this pass; both merges landed clean.

## 5. Pre-release vs post-launch checklist (F1's two-phase plan)

**Before the site goes live (blocking):**
1. Decide the pre-launch form treatment: wire Netlify Forms (add the form-name
   attribute + `netlify` build plugin; `dist/` is gitignored so the deploy
   rebuild handles it) **or** replace the success state with an honest
   "Early access opens soon — watch GitHub" line. The current state — a fake
   success confirmation — must not ship.
2. Verify `hello@halbert.computer` exists / forwards somewhere real before
   pointing GDPR/CCPA requests at it. (Email ecosystem session owns the
   permanent answer.)
3. Rebuild + spot-check `dist/` is regenerated by the deploy pipeline
   (`scripts/deploy.sh`; `dist/` is gitignored — the published site is built
   by CI from the deployed ref, so these source edits go live on next deploy).

**After live:**
4. Wire real collection if not done pre-launch; reconcile privacy §3.1
   (retention wording, unsubscribe path) with whatever mechanism lands.
5. Re-check the "Linux / macOS" CTA line and platform kicker whenever a
   Windows build becomes real (announce, don't pre-announce).
6. Refresh the KnowledgePlate number (24,643 → current real count) when the
   plates are replaced with animated library components; re-derive after
   RAG-13's git-tracking fix so a fresh clone matches what the plate claims.
7. Revisit the over-absolute "never proxies" sentence in privacy §2.3 at the
   legal/email session.

## 6. Open items

1. **Early-access form** — pre-launch treatment + post-launch wiring (§5.1/§5.4).
   Owner: next marketing/web session. **This is the only remaining untruthful
   element on the site.**
2. **Monetization plan review** — separate handoff:
   `HANDOFF-MONETIZATION-PLAN-REVIEW-2026-09-14.md` (device count ≥5–10,
   price model, MoR, GPL constraints; reports back to founder).
3. **sshd_config.d drop-in scanner** — founder-validated need (F7). Suggested
   home: extend `discovery/scanners/security.py` to read
   `/etc/ssh/sshd_config.d/*.conf`, resolve effective values with first-wins
   semantics, and emit a drop-in-conflict discovery of the exact shape the
   plate shows. Fits ATTN-1's proof slice. Filed as a background task chip
   from this session.
4. **Email ecosystem session** — permanent contact addresses, MX for
   halbert.computer, unsubscribe tooling for the early-access list.
5. **KnowledgePlate corpus number** — regenerate from a real install when the
   plates become animated components (spec §8).
6. **halbert.net domain** — v7/v9 and older docs still reference it; decide
   whether to keep it as a redirect or let it lapse (email session).

## 7. Proposed DECISIONS rows (for the founder to ratify)

- **Sharpened model-naming rule:** "Never name or recommend AI models on any
  user-facing surface" — clarified 2026-09-14: unversioned *client/product*
  names (Claude, Cursor) may appear where they describe what connects to
  Halbert (e.g. the MCP tile); **versioned** model names (e.g. "Claude Opus
  4.0"-style) are never published, because they age. A versioned name on a
  shipped surface is a staleness bug, not just a policy miss.
- **Marketing corpus headline:** "thousands" (founder call, 2026-09-14) — a
  numeric headline ("over 20,000") may return only with corpus framing
  ("built from a 20,000+ doc knowledge base") *after* RAG-13 makes a fresh
  clone match the claim.
- **Device-count floor:** the 3-device-per-licence draft is outdated;
  any future FDR-04 decision sets ≥5 (10 preferred) — input to the
  monetization review, not yet decided.

## 8. Verification notes for the next session

- `dist/` is gitignored; the deployed site is built by Netlify from the
  deployed ref — no manual build needed, but run the deploy script rather
  than relying on a stale local `dist/`.
- `stops.jsx` and `terms.html` were concurrently edited (phone-responsive
  classes) by another session during this review; both files' current state
  was re-read before the final edits and merged cleanly.
- The site is not yet live at `halbert.computer` (403 from the sandbox's
  egress proxy is not evidence either way — check DNS/Netlify directly).