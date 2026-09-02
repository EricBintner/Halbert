# Core Concepts & Alignment Review (2026-09-02)

**Baseline:** `main` = `c36ae12e` (after the 2026-09-01 shell redesign merge, the Opus 01–05 batch, the security-review merge, and the SONNET-02 cleanup). Working tree clean.
**Method:** sixteen read-only review agents (four on founding concepts, six walking user journeys through the current code, four on architecture and planning, one lexicon sweep, one promise-vs-reality check), each followed by an adversarial verifier; the shell-redesign founder rulings, the singular-entity design, the HA strategy, yesterday's state-of-work audit and the overnight results were the anchors. Fifteen of sixteen finders and five of the verifiers completed before the session usage limit ended the run (the surface-sprawl finder and the completeness critic did not run); the per-item evidence (file:line, commit, command output) is in `.handoff/audit-2026-09-02/ALIGNMENT-FINDINGS.md`, keyed by the item ids cited below (e.g. `C1-01`, `J3-7`, `A4-02`).
**Direction in force:** the full Rust rebuild is deferred and a Linux OS is far future; current features get completed and tested first. This document weights the recent planning (shell review §9, singular entity, HA strategy, the 2026-09-01 audit and results) over the older design docs.
**Companions written with this review:** `ROADMAP.md` (the single living plan) and `DECISIONS.md` (the append-only decisions log) at the repo root.

---

## 1. The verdict in one paragraph

The founding thesis, the 2026-08-23 vision (the-being.md), the 2026-08-31 singular-entity design and the 2026-09-01 shell rulings are compatible, and the code built in the last ten days is mostly the right code. What is not cohesive is the *joints*: the identity layer that says "I am the machine" is never sent to the model on the production turn path; findings carry their four whys but no route lists them, no surface renders them, and a detected finding never becomes a proposal or a conversation turn; the scheduler that carries every "it tells you first" ritual cannot register a job; the multi-body journey has a correct, tested backend and no completable UI path; the machine has six names; three "master" planning documents disagree with each other and with the direction. Almost every gap is wiring, fencing or a one-line default, not new subsystems. The exceptions that need a founder decision are listed in §8.

---

## 2. What Halbert is (the reconciled concept)

This is the statement every doc, prompt and surface should agree with. Items marked **[decided]** come from an anchor (philosophy, the-being, shell §9, singular entity, HA §8); items marked **[proposed]** reconcile anchors that disagreed and need ratification in `DECISIONS.md`.

1. **Halbert is one entity that speaks as the machine.** It speaks in the first person, grounded in data it measured; every claim can show its evidence; it never calls itself an assistant. **[decided]** The entity's name is the one the user chose at onboarding; the hostname is a fact about a body, never the entity's name: *"I am Titan; this body is erics-mac-studio.local."* **[proposed, C1-02/W1-01]** This reconciles philosophy.md's "I am ubuntu-server-01", the singular entity's "one Halbert, many bodies", and marketing's "I am the machine".
2. **One mind, many bodies.** A body is a host running Halbert. In Singular Entity mode the always-on body is the Canonical Host and holds the one memory and the one conversation; other bodies proxy to it and each runs its own cognitive tick against that shared memory. An Independent Node is a separate entity with its own name. **[decided, singular entity §2/§7]** the-being.md §6's "one Halbert per host" is amended to "one mind per entity; an entity may have many bodies". **[proposed, W4-17]** Multi-session tabs (macos-strategy §4) are superseded; what survives is the Remote Client: the same app with no local backend, pointed at one paired body through the Presence Pill. **[proposed, W4-01]**
3. **The conversation is the core layer; the dashboard runs under the hood.** Shipped as the three-panel shell: rail, centre page, conversation; side-by-side is the default; Cmd+D/J/B toggle panels; Settings renders in the centre; `/voice` stays a full-bleed route. **[decided, shell §9.6–9.7]** The side-by-side default fulfils the thesis only when three links exist: the turn knows what page and item are in the centre, Halbert can summon a page or module into the centre, and the proactive channel lands in the timeline and shows in the top bar in every panel state. Today only the layout exists; the three links are stubs. **[W5-SHELL-02]**
4. **A Finding is the unit of attention.** It carries why now / why care / why so / why trust. The proactive interrupt, the Dashboard attention row, the proposal, the morning report and the summoned module are all projections of a Finding. Discovery-scanner results are sensor readings ("Health Checks"), not attention items; a reading becomes a Finding only when a detector attaches its whys. **[proposed, C2 concept model]** This collapses the two parallel issue systems that exist today (discovery severities on fourteen pages vs FindingStore findings behind a hidden bell).
5. **One mind, one heartbeat.** The Guide is the single `AgentStateMachine`; REFLECTING runs the Haloysius tick once per turn. The Deep Thinker is not a second personality but the scheduled, unprompted work of the same mind: detector sweeps, the morning report, thread consolidation, tracker sync. The Eyes are deterministic workers that report into the mind through the event mapper and the state ledger. **[decided, philosophy + the-being §6]** Today the Guide is real and tested; the heartbeat, the Eyes feeding the mind, and worry persistence are design, not code. **[C4]**
6. **Knowledge and rationale.** SourcePrep is the awareness substrate (host config tree, manuals corpus) and the rationale store; memory_v2 is the mind's private stream; the thread store plus the state ledger are the Halbert-owned biography read into every turn; findings.db is the single proactive/approval ledger. **[decided, ROADMAP-08-23 §1 as amended to four stores, A2-13]** "I remember why you changed that" requires a change ledger written by every write path (approval execution, editor save, diff apply, watcher-observed change) and a recall tool over it. **[proposed, J4/X-3]**
7. **Trust.** One owner: the person at the keyboard of the canonical host. Three boundaries: what the model may *do* (one gate for every surface: risk classification tightened by speaker role, dry-run for mutations, human approval in one ledger, undo next to the change, audit), what it may *see and where it may think* (Tier 0/1/2 sensitivity, secure turn latches local or fails closed, Tier 2 crosses an egress point only with the typed acknowledgement), and what *leaves the machine* (nothing by default; cloud LLMs, web search and peers are named switches, each off until enabled). **[decided, philosophy + tiered sensitivity]** Today the full chain exists only on secondary surfaces; the conversation has one regex gate, and web search is on with no switch. **[C3]**
8. **The home body.** Halbert on an always-on node is a body of the one Halbert, not a second product. On that body the house is the physiology: HA entities and areas are its organs and rooms, HA history and Frigate events are its biography. Capability, not variant, decides what a body can do; the variant is a preset. A household member who is not the administrator is a first-class persona: voice-first, cannot approve, must be told honestly when the entity is degraded. **[proposed, W3 concept model]**
9. **Lexicon.** Shell review §9.2 is definitive for UI labels; code names never change. §3 below extends it to the concepts §9.2 did not cover.

---

## 3. Lexicon extensions (UI label / code name unchanged / avoid in UI)

Shell review §9.2 rules the shell, entity and audio terms. The sweep (`T1`) found the shipped shell lexicon-clean and adds these rulings for the rest of the surface; none proposes a code rename.

| Concept | UI label | Code name (unchanged) | Avoid in UI |
|---|---|---|---|
| The entity | **Halbert** or the chosen name | `persona_id`, `BeingConfig` | assistant, chatbot, sentient consciousness, The Being |
| Physical device | **Body** (label: Body Name) | `body_name`, `node_id`, `instance` | instance, node, host (as the noun), satellite |
| The set of devices | **Linked Devices** | `federation/`, `peers_config.py`, `DevicesTab.tsx` | Federation, Fleet, Mesh, Devices alone, Paired Bodies & Compute Providers |
| Device that serves models to another body | **Compute peer** | `ComputePeerCard.tsx`, `/api/compute` | Workstation (as a label), Compute Provider |
| Something Halbert surfaces for a human | **Finding** (rail: Findings) | `findings/`, `FindingStore` | issue, alert (reserved for threshold rules), discovery, Proactive Events, Being events |
| A change awaiting approval | **Proposal**; queue **Approvals** | `approval/`, `proposals` | pending action |
| Scanner fact | not a UI noun; pages show the facts | `discovery/` | Discoveries as a page or badge |
| Threshold rule | **Alert Rules** | `alerts/` | alert for anything else |
| Conversation surface | **Conversation**; buttons "Continue in Conversation", "Ask Halbert" | `HostShell`, `AgentChat`, `ShellMode='engaged'` | Chat (19 strings today), Engaged, Host Canvas |
| Right-hand evidence area | **Context** | `ContextStage.tsx` | stage, drawer |
| What a body can do | **Capabilities** | `capabilities.py`, `features` | variant, Host Mode / Home Mode, feature flag |
| Model assignment | **Model slot** (Guide / Specialist / Vision / Secure) under Models & Providers | `roles`, `secure_model` | Response tier, Deep Thinker, Eyes |
| Config sensitivity | **Tier 1 / Tier 2** under Trust Boundary | tier routing | Tier for model slots or compression stages |
| Health scans | **Health Checks** | scanners, `somatic/` | Somatosensory, REM sleep, Nightly Maintenance |
| Background loop (docs only) | tick = one `advance_turn`; heartbeat = the loop that schedules ticks and sweeps; idle sweep = `ThreadManager.tick`; sweep = a detector run | — | "tick" for four different things |
| Smart home surface | **Home** | `home/`, `ha_connection` | Ambient Home, Space, Zone; "Sentient Home" allowed in product, not preferred in marketing |

Banned strings still on a visible surface today (all one-line fixes): "Host Canvas" (`TouchBar.tsx:51`), "Halbert Auditory Cortex" and "sovereign mode" (`AudioSettings.tsx:165, :479`), "The being never initiates conversation" (`BeingTab.tsx:403`), "AI-powered Linux assistant" (`Onboarding.tsx:163`, `AboutTab.tsx:22`, `Terminal.tsx:433`), and "assistant" in every package description (`tauri.conf.json:51`, snap/arch/nix/flatpak, `pyproject.toml:8`).

---

## 4. Founding principles vs the code (status on `c36ae12e`)

| Principle (anchor) | Status | The one fix |
|---|---|---|
| **The LLM is the computer** (philosophy) | **Missing on the turn path.** `build_system_prompt`, the only assembly of the identity layer (voice table, name, body, and the v2 `identity.xml`), has no caller; PLANNING/RESPONDING send `build_planning_prompt`/`build_response_prompt`, which carry no identity. The v2 `identity.xml` it would load calls Halbert an "assistant" and a "sentient consciousness". Verified by call-path grep and a rendered-prompt probe. | Prepend one identity block to `messages[0]` every turn (name, platform, body, voice, personality) and rewrite `identity.xml`/`safety.xml` in the machine's voice. `C1-01`, `T1-01` |
| **One name** (onboarding rule) | **Six sources disagree:** `preferences.yml ai_name`, `being.yml name` (never synced despite the comment), `HALBERT_DISPLAY_NAME`/"Host", Haloysius `persona_id`, PersonaStore "default", hostname over MCP. The Presence Pill reads "Host @ workstation" while the greeting says "I am <name>". | One resolver (`ai_name` > `being.name` > "Halbert"), used by instance info, the pill, MCP `serverInfo`, and the identity block. `C1-02`, `W1-01`, `W4-04` |
| **Voice setting** (the-being §5) | Wired UI→`being.yml`→builder, but only the continuity preamble and the morning report consume it. | Falls out of the identity block. `C1-04` |
| **Memory as biography / autobiography loop** (philosophy) | **Not real on the conversation path.** memory_v2 receives only promoted template thoughts and is never read into a turn; the event→worry path is dead (mapper probes methods `DiscoveryEngine` does not have; `telemetry_store=None`); cognition is never persisted; the state ledger has no writer on a sysadmin host; ingestion feeds a ChromaDB index the agent is fenced from. Thread receipts and recall *are* wired and good. | Feed the ledger from real sensors, read it into a turn as an "Observed now" block, persist cognition. `C1-05`, `C4-04`, `C4-05` |
| **Three roles / one mind** (philosophy, the-being §6) | Guide wired and tested (one machine, one tick per turn). **Deep Thinker blocked:** `AutonomousExecutor.schedule_cron_job` raises "This Job cannot be serialized" (the SQLAlchemy job store pickles a local closure), `app.py` swallows it, so the six-hourly sweep and the morning report have never run from the dashboard. Eyes write to stores the mind never reads. No unprompted tick. | Fix the scheduler (memory job store) or replace five daemon-thread cadences with one heartbeat coroutine on the dashboard loop. `C4-01`, `C4-10` |
| **Everything carries its why** (the-being §2) | Data model implemented and tested; four detectors populate it. **Never reaches a human:** `ProactiveEvent` drops the whys, no route lists findings, the `/findings` page shows discovery security scans, MCP `get_findings` calls a method that does not exist. WhyChip provenance works for agent replies only. | `GET /api/findings`, whys on the event, a FindingCard reused by the page, the bell and the conversation. `C2-02`, `C2-03`, `C2-05`, `P1-10` |
| **Triage, not monitor** (the-being §1) | Dashboard is four telemetry tiles plus discovery rows whose only action links to `/services`. | Rebuild `/` as the ranked attention list of open findings and pending proposals. `C2-14` |
| **Proactive channel + dial** (the-being §3–4) | Gate, quiet hours, snooze/dismiss wired. **The only surface is a bell inside the context stage, which the default side-by-side layout hides;** nothing auto-opens; tray is static; events never enter the conversation. Morning report off by default and delivered nowhere durable. | Attention state on the Presence Pill in every layout; finding as a persisted conversation turn; morning report on by default at Balanced. `C2-08`, `C2-10`, `C2-11`, `W5-PROACT-01` |
| **Proposals → approval → execution → rollback** (philosophy hierarchy) | Detect→finding→gate wired. **`generate_for_finding` is never called on the sweep path** (only MCP and the unmounted somatic lifecycle); approving a drop-in fix is a verified no-op (prose "requires manual review" marked "applied"); no receipt; four approval surfaces, two ledgers; chat confirmations bypass ApprovalEngine; the critical-tier phrase is enforced on MCP only. | Proof slice 1 as one workstream: propose at detection, real edit blocks for drop-in/fstab, one approvals API with the phrase gate, change receipt into the thread. `J3-7`, `J3-10`, `J3-9`, `X-2`, `A1-09` |
| **Rationale persists / "I remember why"** (the-being §1.4, marketing) | **No capture, no recall.** No write path records a reason; `recall_memory` is substituted by a manuals search; WhyBrain posts to a `/api/why` that does not exist; SourcePrep concepts are write-only. | The change ledger. `J4-1`, `J4-2`, `C2-15`, `A1-03`, `X-3` |
| **Modules: one component, two containers** (the-being §3) | Five modules summonable from chat; **0 of 14 pages** have a module twin; `HostVitals` duplicates `VitalsModule`. | FindingCard and ApprovalCard first, then Vitals, DriveHealth. `C2-12`, `C2-13` |
| **Safety hierarchy** (philosophy) | Tiers 0/1/2, secure latch, egress choke point: coherent and wired. **Conversation path has one regex gate:** no dry-run, diff, backup or audit for `run_command`/`write_file`; `sed -i /etc/ssh/sshd_config`, `dd if=/dev/zero of=/dev/nvme0n1`, `curl … \| sh`, `zpool destroy` classify MEDIUM (run without confirmation); `iptables -F` classifies SAFE; kill switch is a CWD-relative flag read by four enforcer instances; budgets check after the job; cooling-off is a string suffix. | Invert the default to HIGH for unrecognised commands; audit_fn on the chat executor; one decision function; safe mode as an XDG flag every actor consults. `C3-01`, `C3-02`, `C3-05`, `C3-14` |
| **Local-first** (philosophy, marketing) | No telemetry, no update checks, loopback bind: true. **Web search is registered unconditionally, classified SAFE, and queries DuckDuckGo with no switch.** `GET /api/llm/config` returns cloud API keys in plaintext. Dashboard has no auth; "reachable = admin" is unstated. | `network.web_search: false` default and a Settings Network section; mask keys on read; refuse a non-loopback bind without a token. `C3-08`, `C3-09`, `C3-19` |
| **XDG paths** (philosophy) | Two path resolvers; config in two dirs and data in four roots on macOS; `conversations.db`, the state ledger, somatic and outcome stores ignore `HALBERT_DATA_DIR`, so a host+home pair on one box shares one thread store. Any Settings save drops the `capabilities:` section from `being.yml`. | One resolver; stores resolve at call time; typed `capabilities` field. `A2-01`, `A2-02`, `A2-03` |
| **Birth = first conversation** (the-being §10) | Onboarding is an undismissable form: asks name and a user type nobody reads, no purpose, no body, no model step, blocks the event loop behind a fake progress bar, calls Halbert a "Linux assistant" on macOS. The deterministic first greeting (`/api/identity` + `HostGreeting`) is the one surface that keeps the promise. | First-conversation onboarding with background scan; ask name, purpose, body. `W1-04`, `W1-05`, `W1-06` |

---

## 5. Workflow cohesion verdicts

| Journey | Verdict | What a user experiences today | Joint to close |
|---|---|---|---|
| **First boot (sysadmin)** | Partial | Grounded greeting with the chosen name; then the Presence Pill says "Host @ workstation"; body switch is a no-op (endpoint override discarded by the reload); onboarding scan blocks the loop and runs twice. | `W1-01/02/03/05` |
| **"How are you?" (slice 2)** | Partial, best of the set | State-query trigger, vitals module, WhyChip, receipts all fire; grounding depends on the model choosing tools; no deterministic sensor read, no findings in the prompt, no temperature on macOS. | Eyes pre-step before PLANNING. `J2-2`, `X-4` |
| **Proactive finding → approval (slice 1)** | Pipeline of primitives, both joints missing | On Linux, after up to six hours (if the scheduler worked; it does not) or on a config change, a bell count appears in Host Focus only; no whys, no proposal, no execution, no receipt. | `X-2` |
| **"Why is SSH on 2222?" (archaeology)** | Missing | Nothing captures a reason; nothing recalls one. | `X-3` |
| **Daily driver on the 3-panel shell** | Layout wired and green; semantics stubbed | Side-by-side default; conversation cannot see the page beside it; agent cannot summon a page; proactive badge hidden; `/terminal` is a simulated shell while the real PTY dock is hidden. | `W5-CONV-02/03`, `W5-TERM-01/02` |
| **Terminals** | Agent half real, user half scaffolding | Agent commands run as live tiles with confirmation; staging into the composer works; watched shell, pool enable, TasksColumn/YourShellRegion unwired; a legacy Terminal page forks the concept. | Founder call `R04-POOL`/`R04-F2` (recommend wire). `T-5`, `T-8` |
| **Home node (N150)** | Backend real; journey undefined | Documented install gets the sysadmin capability preset; pairing unreachable from the UI on both machines; the issued token lands in localStorage where the compute link never reads it; nothing proactive on the home body; `/voice` not in the SPA route list; Home page is an entity list whose light toggle lies at the default autonomy. | `W3-S01/S04/S08/S09`, persona 4 (`W3-C03`) |
| **Multi-body (pair, join, talk from either body)** | Backend wired; UI cannot complete it | mDNS list is `[]`, manual tab throws, no component approves pending requests, `PeerToolProxy` never injected, canonical host reports "Independent Node", `body_name` never reaches the prompt. | One "Join Halbert" flow. `W4-02/03/05/06/09` |
| **External MCP client** | Half dead | 7 of 18 tools work; `get_findings`, `get_proposals`, `search_knowledge` fail on every call; discoveries/events empty by construction (separate process); identity is the raw hostname; config queries fail closed on macOS with no way to stage a snapshot. | `MCP-01/02/04/05/06` |
| **CLI** | No conversation entry | `halbert` starts the dashboard server; `halbert info` and the GPL notice's `halbert license` fail when installed; help exposes deferred personas and legacy RAG. | `CLI-01/02/03` |
| **Contributor** | Broken from a clean clone | Quick start installs without the dashboard extra; root suite fails on two missing SPDX headers; knowledge index and corpus absent by design. | `DEV-01/02/03` |

---

## 6. Architecture improvements (fence, wire, or delete; no rewrites)

Ordered by leverage against the direction. Each fits "finish current features".

1. **Identity block on every turn** and one name resolver (`C1-01`, `C1-02`). S. Unblocks voice setting, body awareness, MCP identity.
2. **Proof slice 1 end to end** (`X-2`): propose at detection, real edit blocks, `GET /api/findings`, whys on the wire, FindingCard, finding as a conversation turn, attention state on the Presence Pill, change receipt. M. This is the MVP the-being.md names.
3. **Fix the scheduler or ship the heartbeat** (`C4-01`, `C4-10`). M. Without it "it tells you first" is Linux-config-watcher-only and the morning report is fiction.
4. **Eyes before any state answer** (`X-4`, `J2-2`): identity + vitals + open findings + recent changes as observations with ids before PLANNING. S–M.
5. **The change ledger** (`X-3`): one SQLite ledger written by all four write paths, a reason prompt on approve/apply, `recall_memory` over it, config-diff before/after. M–L. It also gives slice 1 its receipt and slice 2 its biography.
6. **One trust chain** (`C3-14`, `C3-01`, `C3-02`, `C3-04`, `C3-05`, `C3-08`): audit_fn on the chat executor, HIGH default for unknown commands, one approvals API with the phrase gate, XDG safe-mode flag, web-search switch off. S each.
7. **Multi-body journey** (`W4-02/03/05/09`, `W3-S04`, `A1-07`): Join flow with host-side approval, persist the active body, tri-state entity role, write `persona_id_override`, inject `PeerToolProxy`. M.
8. **Findings feed the mind** (`A1-02`): a `FindingsEventMapper` so a HIGH finding becomes a worry at the next tick. S.
9. **One path resolver and typed capabilities** (`A2-01/02/03/04`): stores resolve at call time; `policy.yml` written and read from the same dir; capabilities survive a Settings save. S–M.
10. **Gating: one model** (`A1-05`): delete `feature_flags.py`; replace the six `is_home_variant()` callers with the capability they mean; registry honours `HALBERT_VARIANT`; `CAP_SOURCEPREP` probes daemon reachability, not importability; add `CAP_WEB`, `CAP_CLOUD_LLM`, `CAP_PEER_COMPUTE`. S.
11. **Fence the scaffold** (`A1-06`, `A1-13`, `A2-16`): status headers on the seven unwired federation modules; stop the UI polling `/api/peers/discovered`; delete `runtime/`, `cascade_router.py`, dead `autonomous_tasks`, the legacy PersonaManager path; freeze the ~110 caller-less routes with `include_in_schema=False`. S.
12. **Move governance singletons out of `routes/settings.py`** (`A1-08`): mechanical, no URL changes. M.
13. **MCP topology** (`MCP-04`, `C3-13`): mount JSON-RPC inside the dashboard behind peer auth, point `PeerToolProxy` at it, keep stdio for local coding agents; fix the three always-failing tools first. S then M.
14. **Pages become modules in why-law order** (`C2-13`): FindingCard, ApprovalCard, Vitals (merge three), DriveHealth. L, incremental.

Deferred by direction and not in this list: Rust crates, halbertd, MQTT bus, HalbertOS, Windows, the blue-sky pillars, the App Store companion build.

---

## 7. Planning coherence

**Findings.** Three documents claim to be the master plan and disagree: root `TODO.md` (2026-08-30, "0% complete", schedules the superseded multi-session tabs), `.handoff/MASTER-TODO.md` (2026-08-30, every U1–U6 row still open though all are merged, no rows for REV-04..11 remediation, multi-body, or Voice Mode), and the HA strategy §9 "Now" list, which, together with `MASTER-TODO.md:183`, the experimental README and the Rust plan's milestone ladder, still says "build the Rust crates and halbertd now" against the 2026-09-01 deferral. `ROADMAP-2026-08-23`'s eight phases all landed as code but the doc has no status and the-being.md still calls it the plan. Decisions live in seven places; yesterday's founder sheet has no status column although several defaults were implemented overnight (Wyoming loopback, pairing handshake, STT) and one was resolved contrary to its default (`U3-26`). "Phase N" means four different things. The semantic-audit handoff and the sheet's `SEM-01..03` rows present as open what shell §9.1/9.2 already ruled. `macos-strategy.md`, `README.md`, `FEATURES.md` and `ARCHITECTURE.md` present the multi-session tab client as shipped; there is no code behind it. (`A4-01..23`, `W4-01`, `W3-C01`)

**Fix (done with this review).** Three living artefacts and nothing else says "now":
- `ROADMAP.md` (repo root): the dated Direction block, the rule set, one row per workstream with a definition of done ("wired in production and tested", never "documented"), current status with evidence, owner, and the gating decision; "Deferred by direction" as a section with revive triggers.
- `DECISIONS.md` (repo root): append-only, dated, one line per decision with its source; standing directives; AI-resolved items awaiting ratification; open decisions with a status column.
- Per-workstream handoffs and results in `.handoff/` with a fixed status enum (DRAFT / ACTIVE / LANDED / SUPERSEDED-BY / DEFERRED). Results docs are the only inputs that move a ROADMAP row.

Superseded or banner-needed: root `TODO.md` (SUPERSEDED-BY ROADMAP.md), `MASTER-TODO.md` §0/§3 (index only), the two 08-29 master indexes, HA strategy §9 "Now" (split into no-Rust items vs deferred), the Rust plan header (DEFERRED BY DIRECTION), experimental README ("north-star research", not "build now"), `ROADMAP-2026-08-23` (LANDED as code), the semantic-audit handoff (SUPERSEDED-BY shell §9), `macos-strategy.md` §1.3/§4 (tabs → Presence Pill / Remote Client), `HALBERT-UI-REDESIGN-PLAN.md` (SUPERSEDED-BY shell §9), `HANDOFF-FEDERATED-…` (SUPERSEDED-BY singular entity + OPUS-03), `IMPL-PLAN-SINGULAR-ENTITY-TASKS` ("backend complete; journey incomplete").

**Two corrections to yesterday's results docs.** `RESULTS-OPUS-BATCH-2026-09-01.md` cites branch shas that are not ancestors of main (the packet commits were rebased on merge); the content is on main under `aac3de62`, `cdaf478d`, `9ba12428`, `591068d1`, `3bb28f81`, `9c602c68`, `b5e013b9`, `86a7061b` and others. `SONNET-03/04/05` have not run: five of their failures reproduce on `c36ae12e`, `BeingTab.tsx` still double-prefixes `/api`, `AudioSettings.tsx` still fetches a `/api/being` route that does not exist, and `tier_router.py:383` still raises for OpenAI while the site footer promises "Any LLM or BYOK".

---

## 8. Decisions this review adds (beyond the 2026-09-01 sheet)

| Id | Decision | Recommended default |
|---|---|---|
| `C1-02` | Ratify the identity rule: name = user-chosen entity name; hostname and `body_name` are body facts; `I` is the entity, bodies are "my desk body". | Ratify; amend the-being §6. |
| `W4-01` | One multi-machine concept: bodies of one mind (Singular) or separate entities (Independent); tabs are gone; the Remote Client is the same app with no backend. | Ratify; amend macos-strategy §4. |
| `C2-03` / `T1-11` | Finding is the unit of attention; discovery is sensor input; the `/findings` page lists FindingStore findings with security-scan issues folded in as findings. | Ratify. |
| `C4-10` | One heartbeat coroutine replaces the APScheduler executor, the 30 s mapper scan, the ingestion threads' cadence, the watcher debounce timer and the never-called idle sweep. | Fix the scheduler first (S), heartbeat as the follow-on (M). |
| `C4-07` | The Deep Thinker is the scheduled deterministic work of the one mind; the LLM-summarised report is opt-in behind the dial. Delete the dead LLM autonomous tasks. | Ratify. |
| `A2-05` | Split `being.yml`: persona file owns identity and voice; a body/host file owns variant, body, capabilities, canonical URLs, peer credential reference, security, autonomy, integration connections. | Ratify the split; schedule after the P0 joints. |
| `C3-14` | One `decide(action, actor, context)` for every surface (chat, voice, MCP, peer, scheduler). | Ratify; implement incrementally starting with the chat executor. |
| `C3-08` | Web search off by default, behind a visible switch. | Ratify now (marketing depends on it). |
| `C3-19` | Dashboard bearer token required whenever the bind is non-loopback (same posture Wyoming now has). | Ratify before any remote-client claim. |
| `W3-C03` | Add persona 4 (household member on the kitchen panel) and Journey 6; define speaker-role → tier mapping (guest < household < admin). | Ratify. |
| `W3-C07` | Is the home body a v1 promise? HA §8 D6 says HA is the marketed path; the site has no home stop. | Post-v1 for marketing; keep the sysadmin slices first. |
| `P1-11` | How a fresh install gets the manuals: SourcePrep as a started sidecar with a prebuilt index, a local fallback retriever, or state the dependency. | Sidecar + prebuilt index asset (matches `RAG-14`). |
| `CLI-01` | `halbert` with no arguments opens the conversation (deep link to the app, or a REPL on headless hosts); operational verbs live under it. | Ratify (a). |
| `MCP-04` | MCP topology: mount inside the dashboard behind peer auth; stdio stays for local agents. | Ratify. |
| `T1-03` | One product line for every package description and store listing, in the machine's voice, with no "assistant". | "Halbert — the AI that is your computer." |

---

## 9. Anchor documents: what changes and what does not

- **philosophy.md** stays the ethos. Its "Autobiography Loop" and "Implementation in Code" sections describe the ChromaDB era and point at a placeholder `runtime/` graph, a removed `memory/retrieval.py` and dead autonomous tasks; a dated alignment note now points here, and a rewrite of those two sections is scheduled in `ROADMAP.md` (docs row).
- **the-being.md** stays the vision. §6 "one Halbert per host" is amended by note to "one mind per entity, many bodies"; §3/§8 get a "shipped as the 3-panel shell" note; §8 step 4's landed items are marked; "17 pages" is 14.
- **Shell review §9** is the ruling for the shell and the lexicon; it needs a one-line "Phases 1–5 shipped on `941cc14b` + `601c2fdb`" note so nobody re-plans them, plus the two things it ruled but the code lacks (Cmd+\ rail collapse; persisted body switch).
- **Singular-entity handoff** stays the design; its plan's "Status: COMPLETE" becomes "backend complete; journey incomplete".
- **HA strategy** stays the scoping; §4 Path 1 is redrawn with the home body on the always-on node; §9 "Now" is split.
- **macos-strategy §2** (tiering) stays; §1.3/§4 (tabs) are superseded by note.
- **USER-JOURNEY-METHODOLOGY** is a 2026-08-23 target spec with component names that do not exist; it is re-issued only after the P0 joints land, with a today/target column and persona 4.

---

## 10. What "current features complete and tested" means

The definition-of-done table lives in `ROADMAP.md` §3 so it can be maintained; the order it implies is: CI green (SONNET-03/04/05, SPDX headers, vision extra) → the identity block and one name → proof slice 1 end to end → the scheduler/heartbeat → the multi-body join flow → the trust-chain fixes → the two proof-slice e2e tests and the three hardware runs (real audio, two-machine pairing, the N150 matrix). Nothing in "Next" (container image, marketing extension, App Store companion) starts before those rows are green.
