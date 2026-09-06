# Halbert Decisions Log

Append-only. One line per decision, dated, with its source. Status values: **decided** (founder or anchor doc), **implemented-per-default** (an AI session acted on the recommended default; needs ratification), **open** (founder call pending; the default assumed by work in flight is stated). Code names never change (shell review §9.1 ruling 8); labels do.

## Standing directives

| Date | Directive | Source |
|---|---|---|
| 2025-12 | The LLM identifies as the computer itself, first person, grounded in measured data; never an assistant. | philosophy.md |
| 2026-08-23 | The conversation is the core layer; the dashboard runs under the hood; everything carries its why; triage, not monitor; one mind, many hands. | the-being.md |
| 2026-08-25 | Never name or recommend AI models on any user-facing surface; connection slots, not model menus. | legal pass; Rust plan §16.5a |
| 2026-08-25 | Never write "Sovereign" on a user-facing surface; the engaged surface is labelled with the onboarding name, never the raw hostname. | founder |
| 2026-08-26 | One seamless conversation with hidden topic threads; no conversation list; commands from the UI are staged, never executed. | continuity direction |
| 2026-08-26 | User shells stay but are watched by the AI; the agent reuses idle terminals; subtle indicator-light notifications. | terminal direction |
| 2026-08-26 | Colours only from the shared tokens; no hardcoded colours; no emoji in UI. | design tokens |
| 2026-08-27 | Tier 2 (secrets) is answered by a deterministic template, never a model; scrub before the model; local-first. | tiered sensitivity |
| 2026-08-30 | Never `Co-Authored-By` or generation trailers in commits. | CLAUDE.md |
| 2026-09-01 | Full Rust rebuild deferred; Linux OS far future; current features completed and tested first. | founder |

## Decided

| Date | Decision | Source |
|---|---|---|
| 2026-08-23 | Proactive dial Off / Quiet / Balanced (default) / Assertive with per-category overrides; voice setting first_person (default) / the_computer / hybrid. | the-being §4–5 |
| 2026-08-23 | Docs go into SourcePrep, not ChromaDB; ChromaDB stays for eval only; three stores with clear ownership (amended 2026-09-02 to four: thread store + state ledger, memory_v2, SourcePrep, findings.db). | ROADMAP-2026-08-23 §1; `A2-13` |
| 2026-08-26 | Model picker is independent of SourcePrep; chat/specialist/vision slots. | model-picker-independent |
| 2026-08-30 | Home variant = compute client: no secure_model, no SourcePrep, no model picker (Compute Peer card instead); Apple Intelligence local-only, never a peer backend; peers get ollama/vllm only. | home simplification §12 |
| 2026-08-31 | Singular Entity (default) vs Independent Node; memory is the identity; canonical host holds memory and threads; `body_name` is a location label; capability from hardware replaces variant gates (variant = preset). | singular-entity handoff §2–4 |
| 2026-08-31 | HA strategy D1–D8: three-layer strategy; MQTT/Z2M first (deferred with Rust); halbertd as a package not an OS; sidecar compose and HA add-on as paths; HA stays the marketed smart-home path; Windows/compositor/kernel deferred; experimental docs corrected. | HA strategy §8 |
| 2026-09-01 | Shell: three panels (rail / centre / conversation), side-by-side default, Cmd+D/J/B, Presence Pill replaces InstanceSwitch, rail = Overview / Findings & Approvals / System / Workloads with adaptive headers, Settings in the centre, `/voice` full-bleed; §9.2 lexicon; no backend renames; no emojis; no Cmd+K; cross-body data via endpoint switch, PeerToolProxy is agent-to-tool only. Shipped `941cc14b` + `601c2fdb`. | shell review §9 |
| 2026-09-01 | Terminology forks closed by §9.2: UI says Halbert / Identity & Voice / Singular Entity / Independent Node / Linked Devices; `identity.yml`, `mesh/`, `identity/` renames rejected. `SEM-01..03` are not open. | shell review §9.1 rulings 3, 8; `A4-04` |
| 2026-09-01 | Wyoming defaults: `WYOMING_ENABLED=0`, bind `127.0.0.1`, non-loopback requires `WYOMING_TOKEN`. Operator-visible; docs must follow. | RESULTS-OPUS-BATCH §4; `A4-19` |
| 2026-09-02 | Planning spine: `ROADMAP.md` (only now/next/deferred), this log, per-workstream handoffs with a status enum; root TODO.md, MASTER-TODO §0/§3, the 08-29 indexes and the HA §9 "Now" list are superseded. | alignment review §7 |
| 2026-09-04 | `FDR-01` Contributor terms are DCO 1.1 with an explicit commercial and App Store grant to the maintainer, not a full CLA. The text was already committed in `CONTRIBUTING.md` and already enforced by `.github/workflows/dco.yml`; what was missing was ratification. Lighter contributor friction, sufficient for a single maintainer. | founder, this session |
| 2026-09-04 | `FDR-02` Exactly one GPLv3 §7 exception text, at `LICENSE-EXCEPTION-APPSTORE` in the repo root, verbatim from `APP-STORE-DISTRIBUTION-STRATEGY.md` §2.1 — the narrow form, scope-limited to the Mac App Store, with the third-party carve-out and the fork-freedom clause. Three divergent wordings existed before today; the other two are now pointers. Never paraphrase it: a second wording is a second grant, and a text cannot be retracted for builds already conveyed under it. SPDX form `GPL-3.0-or-later WITH LicenseRef-Halbert-AppStore-Exception`; the ~1,036-file header rewrite is deferred, not part of this. | founder, this session |
| 2026-09-04 | `FDR-03` Bundle identifiers: `ai.halbert.home` (App Store), `ai.halbert.pro` (direct DMG), `ai.halbert.dashboard` (dev, internal **and Linux** — matching the shipped `packaging/flatpak/ai.halbert.dashboard.yml` rather than renaming a published app-id; this fourth conflict was missed by the earlier drafts). `tauri.conf.json` keeps the dev id; per-channel ids are injected at build time. | founder, this session |
| 2026-09-04 | `FDR-07` The App Store build stays a sandboxed remote companion — it connects to a Halbert instance elsewhere and never administers the Mac it runs on. The entire licensing analysis, the entitlement set and the product boundary rest on this; growing local administration into it means redoing all three. | founder, this session |
| 2026-09-04 | `FDR-08` `macos-private-api` is Pro-channel only. The App Store build sets it false and the floating voice HUD degrades to an opaque window rather than failing to open. Private API use is grounds for App Store rejection. | founder, this session |
| 2026-09-04 | Paid-line **mechanism** constraint (bounds `FDR-04` and the deferred open-core line): `GPL-3.0-or-later` means a recipient gets the source and may remove a licence check, so per-feature gating of core code is not durably enforceable. The enforceable paid artifact is the signed, notarized, auto-updating binary and its update stream (the Ardour/Krita model). Feature gating would need Pro-only code outside the GPL core, ending the free-software-core claim. Where the line goes is still deferred; this only bounds the mechanisms. | founder, this session |
| 2026-09-04 | `macos-pro` (a build channel: unsandboxed, Hardened Runtime, Developer ID) and **Halbert Pro** (the product sold through it) are different nouns and are kept apart in the docs. A channel may build and pass its gates before its product has commercial terms — which is the state today. | founder, this session |

| 2026-09-05 | `CD-1` Observation lenses land on existing rows — Track A → `MIND-1` (`C4-04`), `STATE-1` (`J2-2`), `CFG-1` (`A2-02`); B1–B3 (wire the skills matcher, inject the composed prompt, bind skill safety) → new row `SKILL-1`; lens work (schema and load path, dial, suppression gate, lens-voiced report, recurrence remarks, UI) stays §4 Next until a deterministic Noticed section has shipped and a week of them has been read. | founder, 2026-09-05 chat; lenses handoff §13 |
| 2026-09-05 | `CD-4` The event ledger is written at ingestion (`FrigateEventMapper.handle_event`, `HAEventMapper.add_event`) with the event's own timestamp; `populate_cognition()` keeps only the affective half; the ledger never depends on `LOOP-01`/`C4-02`. | founder, 2026-09-05 chat; lenses handoff §13 |
| 2026-09-05 | `CD-5` `TimelineStore` is the Halbert **event** ledger (`continuity/timeline.py`; `MEM-01` continuity group; named in `ERASURE_LIMITS`), `StateStore` holds state, and user favourites/opinions are persona insights in Haloysius `memory_v2` (handoff D9) — never in the event ledger. Sub-question (build the preference writer and research ingestion now, or defer) answered below. | founder, 2026-09-05 chat; lenses handoff §13 |
| 2026-09-05 | `CD-6` The daemon's skill registry reads only `skills/builtin` and `~/.config/halbert/skills` (and, once B5 lands, `~/.config/halbert/lenses`); the cwd entries (`<cwd>/.halbert/skills`, `<cwd>/.claude/skills`) leave the daemon path; a user skill overriding a builtin name is refused or flagged with its source; skill directories join `SENSITIVE_PATHS` and the literal-tilde matching bug in `tools/safety.py` is fixed. | founder, 2026-09-05 chat; lenses handoff §13 |
| 2026-09-05 | `CD-11` Nomenclature: the layer is **Lenses** — `~/.config/halbert/lenses/`, `kind: lens`. Chosen over Affinities because rev 2's reframe made the layer an interpretation of the observation stream rather than a taste bank, which is the condition D10 itself named for preferring Lenses. | founder; lenses handoff §10 D10, `CD-11` |
| 2026-09-05 | `CD-3` Selection is arithmetic and lens-independent: top N by (recurrence count, severity, recency), clamped by the dial. The lens file carries voice only — no `observes:` block, no "what this notices" prose. The model may phrase the selection; it may not choose it or add to it. | founder; lenses handoff §13 `CD-3`(b) |
| 2026-09-05 | `CD-2` Activation is the standing `BeingConfig.active_lens`, not topical matching. Forced by `CD-3`: a voice-only file carries no domains or keywords, so `SkillMatcher`'s `MIN_SCORE` can never fire. `/skill <lens>` stays a per-turn override. | consequence of `CD-3`, 2026-09-05 |
| 2026-09-05 | `CD-7` The morning report ships deterministic first (C1a, no model call). The lens-voiced version (C1b) is gated on `C4-07` being ratified **and** report persistence existing, so a week of real Noticed sections exists to judge from before a model touches it. | founder; lenses handoff §13 `CD-7`(a) |
| 2026-09-05 | `CD-5` sub-question: the user-interest half (preference writer, research ingestion) is **deferred**, with a research and UX planning handoff opened so it cannot be dropped silently a third time. | founder |
| 2026-09-05 | Event-ledger erasure: `ERASURE_LIMITS` names the ledger as a plane `forget` does not reach — true today — and subject-scoped deletion of `occupancy_change` rows is tasked separately. `timeline_events` has no `request_id`, and occupancy rows are a named person's movement history. | founder; branch 1 review, A0-privacy |
| 2026-09-05 | A5 counts `end` rows, not `new`. One `end` per tracked object dedupes identically, and Frigate has resolved `sub_label` by then — so recurrence groups on a recognised identity where one exists. Counting `new` made the plan's own motivating example ("that grey van, three times") unreachable. | founder; branch 1 scrutiny |
| 2026-09-05 | Ledger rows carry a severity from an explicit table at the sink (alarm triggered, water leak → critical; unlocked entry door, person at an entry at night → warning; otherwise info), because `CD-3` sorts by it and the report gate keys off it. | founder; branch 1 scrutiny |
| 2026-09-05 | Timeline retention: `cleanup(90)` runs at store construction now, with a periodic job tasked under `MIND-1` for the daemon that never restarts. | founder; `CD-5` 90-day retention |
| 2026-09-05 | The A2 row contract includes `title`. It was omitted while A2c ("redact the title") and A4 (rendering `[t{id}] …`) both assumed one, so following the contract literally left the mappers' prose discarded — the half of DEFECT-2 that motivated the branch. | branch 1 review finding 2 |

## Implemented per default — needs ratification

| Date | Item | What was done | Ratify? |
|---|---|---|---|
| 2026-08-30 | U6 D2 | <4 GB = offload-only; 4 GB stays local-capable. | pending |
| 2026-08-30 | U6 D4, Q3, Q4 | home-light merged into home; `vision_model` kept; `advance_turn` kept. | pending |
| 2026-09-01 | `R9-F01` | Wyoming loopback + token (above). | pending |
| 2026-09-01 | `R10-F1` | Pairing handshake with host-side approval API, 60 s PIN, attempt cap (UI not built). | pending |
| 2026-09-01 | `VM-STT` | Spoken input relayed back down the WS uplink into a turn. | pending |
| 2026-09-01 | `R04-F1..F13` | Terminal reaper, pool safety, bounds. | pending |
| 2026-09-01 | `U3-26` | Precursor chat-UI doc was NOT subsumed; rescued to `documentation/design/chat-ui-audit-11-…`. | resolved contrary to default |
| 2026-09-01 | `RNC-06` | Main's Rust review doc committed under the current name; branch file to be renamed on merge. | pending |
| 2026-09-01 | Voice `is_speech` per-frame flush | Left as-is deliberately (untestable without sherpa-onnx). | pending |
| 2026-09-02 | `U6-DESIGN-01` | SONNET-03: home preset is an explicit False override for `CAP_SOURCEPREP` unless `being.yml` opts in (`fc55d245`/`97d66158`). | pending |
| 2026-09-02 | `STUB-01` | SONNET-03: `TierRouter` OpenAI stub removed; traced as off the chat path (`a4e4b5a3`); cost-cascade router deleted (`8911de68`). | pending |
| 2026-09-02 | `CC-02` | SONNET-04: SendToChat "new conversation" affordance removed rather than wired, per the one-conversation direction (`cf7face5`). | pending |
| 2026-09-02 | `MEM-01` | **D1 narrowed and finally recorded.** Cross-session *continuity* — threads, receipts, recall, open loops, machine-state history, consolidation — is Halbert's; present-state cognition is Haloysius's. Identity and semantic memory stay in Haloysius `memory_v2`, a ratified store of record whose `ObservationStore` is explicitly cross-session. D1 had no row until now; it lived only in `.handoff/HANDOFF-CONTINUITY-AFTER-PLAN-A-2026-08-26.md §1`. | decided 2026-09-03 |
| 2026-09-02 | `MEM-02` | `halbert_core.continuity.StateStore` is **the** machine-state change ledger; Haloysius `TemporalStateLedger` is retired from Halbert's path (it stays correct and in use inside Haloysius). `LEDGER-1` is a Halbert row; `StateStore` carries `thread_id` and no `persona_id`, is already wired from `agents/threads.py` and `integrations/state_trackers.py`, and does not inherit `PERS-02`'s two persona sources of truth. | decided 2026-09-03 |
| 2026-09-02 | `MEM-03` | A Markdown memory vault, if built, is a **rebuildable projection with no authority** — justified by erasure reach, not store arithmetic. The 2026-08-23 row assigns *ownership*, it does not cap artifacts (it keeps ChromaDB; the audit log, key store, scheduler history and peer credentials are separately ratified). The objection to a file-primary vault is that it would be a fifth **authority**. | decided 2026-09-03 |
| 2026-09-02 | `MEM-04` | Background memory work registers on **Halbert's APScheduler**, gated by the 60 s turn-lock heartbeat — never on `haloysius.background`. `IdleDetector`/`BackgroundDaemon`/`TaskScheduler` have zero importers in either tree and no darwin idle probe, so adopting them would manufacture a macOS blocker rather than remove one. Quiet hours become a Halbert policy choice. | decided 2026-09-03 |
| 2026-09-02 | `MEM-05` | Corrects `INTEG-07`: only the `EventLog` append/verify/**erase** lock belongs upstream in Haloysius. The custody lock does **not** — `haloysius.integrity.identity` performs no file I/O and holds no key on disk (the `SigningBackend` seam keeps custody consumer-side), so `<keys>/.custody.lock` in `crypto/storage.py` is its correct and final home. `erase()` is a third unlocked read-modify-write, named in neither `INTEG-06` nor `INTEG-07`. | decided 2026-09-03 |
| 2026-09-02 | `MEM-06` | `reason` and `actor` are mandatory on every ledger write and are **never** filled by a model after the fact. Permitted values: a human utterance from the causing turn, a deterministic rule that names itself, or the `UNRECORDED` sentinel, which renders as *unknown*. Same honesty constraint as `INTEG-05`. Enforced at the signature (keyword-only, no default) in `46241c94`. | implemented-per-default |
| 2026-09-02 | `INTEG-01` | Hardware custody (Secure Enclave / TPM) shipped as a registrable seam, not an implementation: SEP key creation needs a signed binary with entitlements and could not be verified here. Ladder is hardware -> Keychain -> Secret Service -> `0600` file. | founder-agreed before start |
| 2026-09-02 | `INTEG-02` | No migration of legacy `audit/YYYY/MM/DD/*.jsonl` records; left on disk, unread. `EventLog` globs `audit/*.jsonl`, so the old nested tree is invisible. | founder: "no users, so nobody will need legacy support" |
| 2026-09-02 | `INTEG-03` | Audit signing is **opt-in** (`set_audit_signer()` or `HALBERT_AUDIT_SIGNING=1`). Resolving a signer creates a private key on the machine — on macOS in the login keychain — which a tool call must not do unannounced. Unsigned, the log appends, verifies, and reports `signed: 0`. | pending |
| 2026-09-02 | `INTEG-04` | `obs/audit.py` guards its haloysius import (the core must import without it) and, when absent, **writes nothing, loudly** rather than falling back to a chain nobody can verify. `verify_audit` raises; the CLI exits 2, distinct from exit 1 for tampering. | pending |
| 2026-09-02 | `INTEG-05` | No "memory verified" badge anywhere, per handoff §3.5. Copy is "no tampering detected since this log began / since last sync with `<peer>`", plus an explicit statement of what a single machine cannot prove. Binds any future dashboard integrity surface. | pending |
| 2026-09-02 | `INTEG-06` | `EventLog.append`'s unlocked read-modify-write of the head made 24 concurrent audit writes report 46 integrity problems on an untouched log. Fixed in Halbert with an `flock` on `<audit>/.append.lock`; **the real fix belongs in Haloysius**, since every concurrent consumer has this bug. | pending; raise on Haloysius Phase 1 |
| 2026-09-02 | `INTEG-07` | Adversarial pass found the read-modify-write hazard was a *pattern*, not one bug: verifying while writing produced **288 false tamper reports in 3 s**, and concurrent first starts minted **5 identities, destroying 4 keys**. `verify_audit` now takes the append lock; `<keys>/.custody.lock` makes find-or-create-key atomic. Both also belong upstream in Haloysius. | pending; raise on Haloysius Phase 1 |
| 2026-09-02 | `INTEG-08` | A key store holding material that cannot be read is **never written to**. A corrupt key file used to make the body silently mint a new identity and overwrite the old key. The body now runs unsigned and says why: destroying an identity is not error recovery, and is irreversible. | pending |
| 2026-09-02 | `INTEG-09` | Audited fields (`ts`, `tool`, `mode`, `request_id`, `ok`, `summary`) are reserved; a caller's keyword argument can no longer overwrite one, and collisions are preserved under `shadowed`. Previously an extra could rewrite what the record claimed happened. | pending |
| 2026-09-02 | `INTEG-10` | `audit-verify` on a missing directory exits **2** and creates nothing; it used to create the directory and print "no tampering detected". A check that cannot run must never read as a pass. | pending |
| 2026-09-02 | `C1-02` / `W4-06` phrasing | Alignment fixes: identity block on every turn with provisional body/canonical-host wording ("You are currently at your {body} body ({hostname})"; the_computer: "This machine is the {body} body"); name precedence HALBERT_DISPLAY_NAME > preferences ai_name > being.yml name > short hostname > "Halbert"; tri-state entity role (canonical / body / independent). | pending |
| 2026-09-02 | `C2-10` | Morning report defaults to enabled at 08:00 regardless of dial (gating stays in ProactiveGate). | pending |
| 2026-09-02 | `C3-08` | Web search off by default; setting lives in `web_search.yml`, `being.yml capabilities.web` overrides; classified MEDIUM egress; dashboard `/api/web-search` and the GPU driver lookup follow the same switch. | pending |
| 2026-09-02 | `J3-7` | Proposals are auto-generated at detection only for executable fixes (permissions chmod today); drop-in/fstab stay manual-review. | pending |
| 2026-09-02 | `C4-01` | Scheduler uses an in-memory APScheduler job store (jobs re-register at boot; SchedulerEngine JSON keeps history); heartbeat 60 s, floor 5 s. | pending |

## Open — founder calls (default assumed by work in flight)

| Id | Decision | Default | Status |
|---|---|---|---|
| `C1-02` | Identity rule: entity name = user-chosen; hostname and body are body facts; "I" is the entity. | ratify | open |
| `W4-01` | One multi-machine concept; tabs superseded; Remote Client = same app, no backend, one paired body. | ratify | open |
| `C2-03` / `T1-11` | Finding is the unit of attention; `/findings` lists FindingStore; security-scan issues fold in. | ratify | open |
| `C4-10` / `C4-01` | Fix the scheduler now; heartbeat coroutine as follow-on. | ratify | open |
| `C4-07` | Deep Thinker = scheduled deterministic work; delete dead LLM tasks; report LLM summary opt-in. | ratify | open |
| `A2-05` | Split being.yml into persona file + body/host file. | ratify, after P0s | open |
| `C3-14` | One `decide(action, actor, context)` for every surface. | ratify, incremental | open |
| `C3-08` | Web search off by default behind a visible switch. | ratify now | open |
| `C3-19` | Dashboard bearer token whenever bound off loopback. | ratify before remote-client work | open |
| `SEC-05` | MCP config queries fail closed without a snapshot; add an onboarding/Settings "stage my config" step (macOS registry list needed). | fail-closed + staging step | open |
| `SE-05` | Wire `ComputeRouter.route()`. | HOME variant only | open |
| `R2-F6` | Outbound peer credential store. | `being.yml peer_token` 0600 declared the store (or keychain on macOS Pro) | open |
| `R04-POOL` / `R04-F2` | Enable the agent PTY pool; wire the watched shell; mount TasksColumn/YourShellRegion. | wire (a) | open |
| `LOOP-01` | HomeCognitiveLoop. | instantiate behind `CAP_HA_CONNECTION` | open |
| `W3-C03` | Persona 4 (household member) and Journey 6; speaker-role → tier mapping. | ratify | open |
| `W3-C07` | Is the home body a v1 marketing promise? | post-v1 | open |
| `P1-11` / `RAG-13` / `RAG-14` | Manuals on a fresh install; corpus distribution; prebuilt index. | sidecar + prebuilt index asset; publish HF datasets | open |
| `CLI-01` | `halbert` opens the conversation. | (a) | open |
| `MCP-04` / `C3-13` | MCP mounted inside the dashboard behind peer auth; stdio for local agents; one token system. | ratify | open |
| `T1-03` | One product line for every listing, no "assistant". | "Halbert — the AI that is your computer." | open |
| `U6-DESIGN-01` | Probe-beats-preset re-enables SourcePrep on a home node where importable. | explicit False on home unless `being.yml` opts in (moot once `CAP_SOURCEPREP` probes reachability) | open |
| `VM-22` | Python consumer for the Rust AEC socket. | dormant | open |
| `VM-01` / `VM-02` | gUM-denied as machine error; quiet-dial suppression of severity-2 wakes. | keep v1 | open |
| `FDR-04` | Halbert Pro price, update window, renewal, refund policy, device count; then `HALBERT-PRO-COMMERCIAL-TERMS.md`. Blocks Phase B (Ed25519 keys, Sparkle, Lemon Squeezy). The 2026-08-29 draft said "$24–$29", `TASK-PACKET-06` said "$29 ($24 launch promo)", `TERMS.md:25` adds a 3-device limit the drafts omit — three numbers, no decision. | none | open |
| `FDR-05` | Copyright first year: 2024 or 2025. First commit is `b6a77dd7` 2025-12-08; 1,036 headers and `tests/test_legal_metadata.py:21` say 2024–2026. | keep 2024–2026 | open |
| `FDR-06` | Outbound licence stays `GPL-3.0-or-later` rather than `-only`. One word; changing it later means every statement plus 1,036 headers, and must happen before external contributions land. | keep or-later | open |
| `FDR-09` | Developer infrastructure, all external to this repo: Apple Developer Program enrollment, Developer ID + Mac App Store certificates, Lemon Squeezy product and webhook, the `halbert-ha-addon` public repo. | none | open |
| `MD-04` / `VMK-09` | 7-line primary / 4-line micro mark; SVG naming scheme. | undecided / keep tier names | open |
| `ENV-01` | Python floor 3.10 vs 3.11. | 3.10; fix docs | open |
| `A1-11` | Owner of "what the machine knows about itself": SourcePrep observations vs `knowledge/`. | SourcePrep observations; shim the 3 consumed routes | open |
| `HW-01..04`, `SE-28`, `VM-27` | Hardware and two-machine runs. | schedule after `VOICE-1`/`LD-1` land | open |
