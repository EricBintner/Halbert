# Web v10 clarity review

**Date:** 2026-09-15
**Reviewed:** `marketing/web-v10` at commit `52c48591`, served by the local dev server, walked at 1024×768 and 375×812.
**Status:** Proposal. Nothing on the site has been changed. Every suggested copy line below is a draft for the founder to accept, edit or reject.
**Question asked:** Is it clear to a first-time visitor what Halbert actually is?

Standing directives this review respects (DECISIONS.md → Standing directives):

- The system speaks as the computer itself, in first person, grounded in measured data. Never an assistant.
- Never name or recommend an AI model on any user-facing surface. Connection slots, not model menus.
- Never write "Sovereign" on a user-facing surface.
- Colours only from the shared tokens. No emoji in UI.

House rule for this site, from the header comment in `src/content/stops.jsx`: headlines are fixed, everything else is copy. This review proposes one headline change (the Distributed stop) and flags it as such.

---

## 1. The two readers

**Reader A, the agent-framework user.** Runs or has run OpenClaw, Hermes, or similar. Knows what MCP is, what a local model is, what Home Assistant is. Arrives asking: *what shape is this thing, what does it plug into, and can I install it tonight?* Their second click is GitHub.

**Reader B, the mildly technical user.** Comfortable installing software, may run a Plex box or a Raspberry Pi, has heard of AI tools. Does not know MCP, BYOK, ZFS or sshd. Arrives asking: *what is it, does it run on my computer, and what does it do for me?* Will scroll two or three stops before deciding.

We are not marketing to non-technical people. Reader B is the floor. Jargon is fine in the bottom-left dossier, which is intended to impress computer scientists, and nowhere else.

---

## 2. Verdict

The site is beautiful and the voice is consistent, but neither reader is told what kind of thing Halbert is.

- The hero says "I am the computer" beside a picture of a tablet. Reader B can reasonably conclude Halbert is a hardware device or a kiosk. Nothing on the page ever confirms "app".
- The only explanatory paragraph on the page uses "host management", "MCP" and "configs and their hardware". The first words after the logo are `// NATIVE MCP & HOST INTELLIGENCE`.
- Reader A gets the pitch by the Triage stop but never receives the one sentence they want: *a local agent with a built-in MCP server, dozens of system scanners, Home Assistant control and voice.* That sentence exists, but only inside the dossier behind an unlabeled book icon.
- The call to action collects nothing. The email form has no backend. Meanwhile the repo is public today, so "early build" undersells an installable product to Reader A.
- Reader A's second click lands on a README that describes a different product: "an AI assistant", "hybrid cloud by default", four named model vendors. The site says local-first and never-an-assistant.

The fixes are mostly copy. Two files carry almost all of it.

---

## 3. Stop by stop

Each stop: what is on screen, how each reader takes it, and a proposal. Proposed copy is a draft in the site's voice.

### Stop 1 · Meet Halbert (`intro`)

**On screen.** Kicker `// NATIVE MCP & HOST INTELLIGENCE`. Headline "I am the computer." / "And I put the smart in your home." One body paragraph. Right field: a dark tablet showing voice mode with the animated mark.

**Reader A.** MCP in the kicker is a hook. "Host intelligence" is undefined. The body says "give your AI tools MCP access", which implies an MCP server without saying so. Does not learn that Halbert is a process that runs on the box.

**Reader B.** "I am the computer" plus a tablet reads as a product you buy. "Host management" and "configs" are sysadmin words. Does not learn which computers it runs on until stop 4. The paragraph starts in third person ("Halbert bridges…") and switches to first person ("I monitor…"), so it is unclear who is speaking.

**Proposal.**

Kicker, current:

```
// NATIVE MCP & HOST INTELLIGENCE
```

Kicker, proposed. The platform line moves up from stop 4, because "which computers" is the fastest what-is-it signal on the page:

```
// OPEN SOURCE · LINUX · MAC · HOME ASSISTANT
```

Headline: unchanged.

Body, current:

> Halbert bridges host management and home automation into one local intelligence. I monitor my own hardware, help automate your home, and give your AI tools MCP access to your systems, their configs and their hardware. And I run locally.

Body, proposed, first person throughout:

> I run on your Linux or Mac machine and I know it from the inside: the drives, the services, the logs, the temperatures. I flag what is wrong and fix it when you say so. I run the lights and the rooms through Home Assistant. And nothing I know leaves this machine unless you connect it.

Coda, proposed, a single serif line under the body in the register the first-person voice cannot use. This is the split that commit `0669c1d3` tried and `4cc803ba` reverted; the instinct was right, the coda just needs to carry the category sentence rather than more voice:

> Halbert is an open-source app that runs on your own hardware, and it gives your other AI tools a door into the machine through MCP.

Why a coda: the first-person voice cannot say "I am an app" without breaking character. A one-line third-person caption can, and it is the only place on the page that needs to.

### Stop 2 · Triage (`open`)

**On screen.** "I know what's up and I can fix it." Body about running on your hardware and reading its own sensors. Proactive Events plate with an sshd drop-in conflict, SMART pending sectors, and a borg backup row.

**Reader A.** Strong. The plate rows read as real engineering. The sshd drop-in example is the kind of thing only a tool that actually parsed the config would know.

**Reader B.** Headline is plain and good. Plate content is jargon but the shape communicates "it watches and warns, and I can snooze or dismiss". Fine.

**Proposal.** No copy change.

### Stop 3 · Automation (`apex`)

**On screen.** "I can turn out the lights for you." Body lists dimming lights, validating ZFS pools, rotating journals, restarting a stalled service. Vitals plate.

**Reader A.** Fine.

**Reader B.** The headline carries it. The list mixes one plain item with three sysadmin items, which is acceptable because the reader can skim a list. Optional softening below.

**Proposal.** None required. Optional: "validating ZFS pools" → "checking the storage pools" if the body should be plainer. The vitals plate is the most self-explanatory plate on the page and helps Reader B.

### Stop 4 · Local (`diagonal`)

**On screen.** "Local." then `{or BYOK, whatever you want}`. Body. "Open source, GPL-3.0". Kicker "Linux · Mac · Home Assistant".

**Reader A.** Understands BYOK. "Sensitive system configs and credentials always require a private local model" is the strongest security claim on the page and lands well.

**Reader B.** Does not know BYOK. The body expands it two lines later ("bring your own cloud keys") but the acronym came first. The sentence "but importantly sensitive system configs…" is grammatically rough.

**Proposal.**

Sub-headline, current:

```
{or BYOK, whatever you want}
```

Sub-headline, proposed:

```
{or bring your own keys}
```

Body, current:

> Built to be local and private first. Nothing leaves the machine unless you connect it. Run local LLMs or bring your own cloud keys, but importantly sensitive system configs and credentials always require a private local model.

Body, proposed:

> Built local and private first. Nothing leaves this machine unless you connect it. Run a local model, or bring your own cloud keys. Either way, passwords, keys and sensitive configs are only ever handled by a private model on this hardware.

Keep "Open source, GPL-3.0" and the platform kicker here even if the platform line also moves to the intro. Repetition of the platform line is cheap and useful.

### Stop 5 · Rationale (`rise`)

**On screen.** "I remember why you changed that." The SSH port 2222 story. Rationale plate with the config line, the human's reason, and evidence rows.

**Both readers.** The best stop on the page. Concrete, specific, and both readers understand it on the first read.

**Proposal.** No change. If anything else on the page needs a model for how to write for both readers, it is this stop.

### Stop 6 · Knowledge (`hop`)

**On screen.** "I know thousands of system references and docs." Body naming man pages, Arch Wiki, Homebrew, TLDR. Knowledge Base plate showing 24,643 RAG docs.

**Reader A.** "No invented flags" is the anti-hallucination hook and is the best line on the page for this reader. The SQLite mention in the plate reads as honest.

**Reader B.** Fine. "Man pages" and "Arch Wiki" are recognisable as "documentation".

**Proposal.** No copy change. One fact alignment: the plate says 24,643, the README says 16,000+, and the approved metadata was adjusted to "thousands" per a factual review (commit `7869e292`). Pick one number and use it in the plate, or make the plate clearly illustrative. See F10.

### Stop 7 · Distributed (`cap`)

**On screen.** "Nodes of shared intelligence." Body about a closet server offloading reasoning to a desktop GPU. Quote "Your machines, thinking together." Kicker "Shared local models · Peer routing".

**Reader A.** Body is concrete and good.

**Reader B.** The headline is the most abstract on the page. The body copy is the concrete version of it. The quote does the headline's job better than the headline.

**Proposal.** This is the one headline change in this review. It echoes the standing directive "one mind, many hands" and the catalog category the dossier already shows on this stop, "One mind across every machine".

Headline, current:

```
Nodes of shared intelligence.
```

Headline, proposed:

```
One mind, many machines.
```

Kicker, current `// DISTRIBUTED ARCHITECTURE`. Proposed `// MORE THAN ONE MACHINE`. Body and quote unchanged.

### Stop 8 · Get Halbert (`reveal`)

**On screen.** "Hi, I'm your computer." Full mark. Email form with "Get access" and placeholder "you@yourhost — for the early build". Line "Linux / macOS / Home Assistant · Any LLM or BYOK". Footer links Privacy · Terms · Open Source GPL-3.0 at 10px, 50% opacity.

**Reader A.** Wants a GitHub button and an install line. Gets a waitlist. The GPL link is the smallest text on the page.

**Reader B.** "Get access" to what? Nothing on this stop says what they would receive. "Any LLM or BYOK" is two acronyms in five words.

**Proposal.** Three parts.

1. A feature strip above the form, one line, monospace kicker style, built from the catalog's fact-checked feature titles so it cannot drift from the source of truth:

```
BUILT-IN MCP SERVER · 37 SYSTEM SCANNERS · HOME ASSISTANT · LOCAL VOICE · MEMORY WITH A WHY
```

   This is the sentence Reader A came for. Only `status: shipped` catalog entries may appear here.

2. Two actions instead of one, pending decision D1:

   - Primary button: **Get the source on GitHub**. The repo is public. Quick Start is clone, `pip install -e`, `make dev`.
   - Secondary: the email field, relabelled **Send me the packaged build**, and actually wired (see F1).

3. Footer line, current `Linux / macOS / Home Assistant · Any LLM or BYOK`. Proposed:

```
LINUX / MACOS / HOME ASSISTANT · LOCAL MODELS OR YOUR OWN KEYS
```

---

## 4. Findings validated in source

Each finding was checked against the code, not just the screen.

**F1. The form collects nothing.** `EarlyAccessForm` in `src/content/stops.jsx` sets local state and renders a success message. No `action`, no `data-netlify`, no `fetch`, nothing in `netlify.toml`. A grep across `src/` and `index.html` for `netlify|action=|fetch(|formspree|mailchimp|buttondown` returns nothing. Every "Get access" click today is silently discarded and the visitor is told "You're on the list."

**F2. The repo is public and has no releases.** `gh repo view EricBintner/Halbert` reports `PUBLIC`. `gh release list` is empty. README Quick Start is a source install: Python 3.11+, Node 22, clone, venv, `pip install -e halbert_core/`, `make dev`. So "early build" is wrong for Reader A, who can install tonight, and roughly right for Reader B, who has no packaged build to install. The CTA should serve both.

**F3. The tab and share-card title is the most jargon-heavy line on the site.** `<title>`, `og:title` and `twitter:title` in `index.html` all read "Meet Halbert: Host Epistemology & Cognition, Smart Home + MCP". This was approved on 2026-09-14 (commit `7869e292`, `documentation/marketing/METADATA-AND-AI-SEO.md`) for two stated reasons: it fits the 56-character two-line envelope on mobile link cards, and it packs "high-intent search signals". The first reason holds. The second is doubtful for these readers: neither Reader A nor Reader B would type "host epistemology". Two alternatives that keep the envelope and keep "Smart Home + MCP":

| Candidate | Chars |
|---|---|
| `Halbert — The AI That Is Your Computer. Smart Home + MCP` | 56 |
| `Halbert — Local AI for Your Computer, Smart Home + MCP` | 54 |

   Note `og-image.png` may carry the title in pixels (commit `52c48591` enlarged its typography) and would need regenerating if the title changes. Decision D2.

**F4. The README describes a different product.** `README.md` lines 11–15 and 43: "An AI assistant that actually knows your computer"; "By default, Halbert uses a hybrid AI architecture: fast, capable cloud models handle everyday conversation"; cloud models named as Claude, OpenAI, Gemini, DeepSeek; "16,000+" documentation guides. The site says local-first and private by construction, the directives say never an assistant and never name a model, and the metadata review settled on "thousands". Reader A's second click is GitHub, so this is a clarity problem for the site even though the file is not in `marketing/`. Decision D3.

**F5. BYOK is unexpanded at first use.** Stop 4 sub-headline and stop 8 footer, both in `src/content/stops.jsx`. The stop 4 body does expand it, but after the acronym.

**F6. The dossier trigger has no visible label.** `src/components/TechnicalDossierModal.jsx` renders a `BookOpen` icon with `aria-label="Research & Architecture Dossier"`. Screen readers get the label; sighted users get a book. The dossier holds the clearest product description on the page (the catalog one-liners: "Halbert exposes its own tools and resources for external agents to consume via the Model Context Protocol", "37 Pluggable System Scanners"). It is the best content for Reader A and nothing invites them to open it.

**F7. The dossier names seven AI vendors.** `marketing/feature-reference/src/catalog.json`, feature `hot-swap-providers`, `oneLine`: "Switch between Ollama, LM Studio, Apple Foundation Models, OpenAI, Anthropic, Google, and Azure without restarting." `howItWorks` repeats the list. `air-gapped-private-execution.howItWorks` names Ollama. `llms.txt` and the JSON-LD name "Claude, Cursor" as MCP consumers. The 2026-08-25 directive says never name or recommend AI models on any user-facing surface, connection slots not model menus. Strictly these are providers and clients, not models, but "Apple Foundation Models" is a model family and the directive's intent is slots not menus. Decision D4.

**F8. The intro body breaks voice.** "Halbert bridges…" then "I monitor…" in one paragraph. `git log` shows commit `0669c1d3` split it into voice plus a serif coda and `4cc803ba` merged it back. Proposal in Stop 1 above.

**F9. The stop label sits on the dark plate.** `src/components/ScrollHUD.jsx` renders the active stop name in `--color-ink` regardless of which colour field is behind it. On the intro stop at 1024×768 the "Meet Halbert" label's bounding box overlaps the dark tablet plate (verified by script: label `rgb(28,25,23)`, boxes overlap). It is legible on the bone field for every other stop. Minor.

**F10. Three different corpus numbers.** Knowledge plate 24,643 (`src/content/ui.jsx`), README 16,000+, approved metadata "thousands". The plates are declared placeholders in `ui.jsx`, so this is low stakes, but Reader A notices numbers.

---

## 5. Decisions needed from the founder

**D1. Shape of the call to action.**
- (a) **Recommended.** Primary button to GitHub. Secondary email field for the packaged build, wired to a real backend.
- (b) Waitlist only, wired. Keeps the current look; still hides an installable product from Reader A.
- (c) GitHub only. Loses the Reader B lead.

**D2. Tab and share title.** Keep the approved title, or swap the epistemology phrase for one of the F3 candidates. Keeping "Host Epistemology" for the JSON-LD `description`, `llms.txt` and the dossier is compatible with either choice; the question is only what appears in the tab and on link cards.

**D3. README positioning.** Realign `README.md` to the site's positioning and the standing directives as its own task, or accept the mismatch for now. This review recommends its own packet; it is not a marketing-folder edit.

**D4. Vendor names in the dossier and `llms.txt`.** Keep on the grounds that providers and clients are not models, or reword to "seven provider types" and "any MCP client". This review leans reword, because the directive's stated intent is slots not menus and the dossier is user-facing.

---

## 6. Recommended changes, ranked

| # | Change | Where | Effort | Needs |
|---|---|---|---|---|
| R1 | Wire the email form or replace it | `index.html` (static form for Netlify build-time detection) + `src/content/stops.jsx` | small | D1 |
| R2 | Intro kicker, body and coda per Stop 1 | `src/content/stops.jsx` | small | none |
| R3 | Reveal stop: feature strip, dual CTA, footer line | `src/content/stops.jsx` | small | D1 |
| R4 | Expand BYOK at both uses | `src/content/stops.jsx` | trivial | none |
| R5 | Distributed headline and kicker | `src/content/stops.jsx` | trivial | founder (headline rule) |
| R6 | Visible caption on the dossier trigger, e.g. `RESEARCH` in the kicker style | `src/components/TechnicalDossierModal.jsx` | small | none |
| R7 | Title in `<title>`, `og:title`, `twitter:title`; update the metadata spec doc; regenerate `og-image.png` if it carries the title | `index.html`, `documentation/marketing/METADATA-AND-AI-SEO.md`, `public/og-image.png` | small–medium | D2 |
| R8 | Stop label legibility over the stroke field: a canvas-coloured pill behind the label, or ink-on-stroke when the label's field is stroke | `src/components/ScrollHUD.jsx` | small | none |
| R9 | One corpus number in the Knowledge plate | `src/content/ui.jsx` | trivial | pick the number |
| R10 | README realignment | `README.md` | medium | D3, own packet |
| R11 | Reword provider lists | `marketing/feature-reference/src/catalog.json`, `public/llms.txt`, JSON-LD in `index.html` | trivial | D4 |

Netlify Forms note for R1: the SPA renders the form client-side, so Netlify's build-time form detection needs a hidden static `<form name="early-build" netlify netlify-honeypot="…" hidden>` in `index.html` with the same field names, and the React form posts to `/` with `form-name=early-build` encoded. Alternatively post to a Netlify Function. Either is under an hour.

---

## 7. Implementation order

1. **Pure copy, no decisions:** R2, R4, R6, R8, R9. One branch, one commit per stop.
2. **Headline change:** R5, once the founder accepts the exception to the fixed-headlines rule.
3. **After D1:** R1 and R3 together, since the reveal stop's layout depends on whether there are one or two actions.
4. **After D2:** R7, including the OG image check.
5. **After D4:** R11.
6. **Own packet:** R10.

Verification for each step: walk all eight stops at 1024×768 and 375×812, run `scripts/check_contrast.py` if any colour is touched (R8), and confirm the form submission reaches the backend before claiming R1 done.

---

## Appendix A · Evidence log

- Dev server already running on port 5188; attached rather than started a second copy.
- Stop centres at 1024×768, from `stopCenterS(i, aspect)` in `src/lib/cameraEngine.js`, as scroll offsets: 211, 1177, 2284, 3267, 4251, 5375, 6499, 7940 px.
- Dossier opened on stop 1: two SPEC rows (Wyoming Protocol, Model Context Protocol Specification) and three FEATURE rows (Built-in MCP Server, Instant Local Voice Pipeline, Acoustic Environment Sensing). Detail pane for Built-in MCP Server shows category "One mind across every machine" and source `mcp/server.py, mcp/camera_gate.py`.
- Citation counts per stop from `marketing/shared/researchCitations.json`: hop 6, diagonal 4, cap 4, all others 2. Total 24.
- HUD overlap check on stop 1: label box `[877,260,972,281]`, plate box `[560,109,967,651]`, overlap true, label colour `rgb(28,25,23)`.
- Form wiring grep across `src/` and `index.html`: no matches.
- `gh repo view`: visibility PUBLIC, description "An LLM brain for your computer." `gh release list`: empty.
- Console: no errors. Two preload warnings for font files not used within a few seconds of load; cosmetic, unrelated to this review.

## Appendix B · Not reviewed

- `public/privacy.html` and `public/terms.html` content.
- `og-image.png` pixels. Whether it carries the title text was not confirmed.
- `marketing/feature-reference` as a site.
- Performance, bundle size, and accessibility beyond the dossier's focus trap and the HUD label.
- Whether "Instant Local Voice Pipeline" and other catalog `shipped` statuses match the current state of the app. The feature strip in R3 depends on that status being accurate.
