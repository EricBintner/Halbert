# Handoff: External Design Review

**Created:** 2026-08-23
**For:** External reviewer (design + UX + product)
**From:** The Halbert build session
**Repository root:** `/Volumes/4TB-BAD/Halbert`

---

## What we are asking you to do

We have a mature plan for the *infrastructure spine* (retrieval, intake,
conversation consolidation) and a vision for the *being layers* (config
brain, proactive channel, reactive slice). What we do NOT have is a design
doc that a human reviewer can read and critique at the level of:

1. **Overall direction and planning** — are we building the right thing?
   Are there obvious gaps, sequencing errors, or architectural blind spots?
   Is the scope right? Are we missing whole categories of work?

2. **Design mechanics** — user flows, interaction patterns, the myopic
   details of how a user actually lives with this. What does the first
   conversation feel like? What does the proactive interrupt look like on
   screen? How does approve/dismiss/snooze work as a gesture? Where does
   the being's voice land as warm vs uncanny?

We need two documents back from you:

- **Doc 1:** `documentation/design/REVIEW-DIRECTION-2026-08-23.md` — notes,
  suggestions, and critique on the overall direction and planning. Focus on
  things we may have missed, sequencing risks, scope concerns, and
  architectural blind spots. This is the "are we building the right thing"
  doc.

- **Doc 2:** `documentation/design/REVIEW-DESIGN-MECHANICS-2026-08-23.md` —
  a design doc focused on user-flow and myopic interactions. Mark up the
  flows, propose interaction patterns, sketch the micro-interactions
  (approve/dismiss/snooze, the why affordance, module summoning, the
  proactive interrupt, the morning report, onboarding/birth). This is the
  "how does a human actually use this" doc.

Both docs should be written as if you are a senior product designer + UX
architect reviewing a peer's work. Be direct. Point out what's missing.
Propose alternatives where the current design is thin.

---

## The reading list (in order)

Read these in this order. Each one builds on the previous.

### 1. The vision (read first)

`/Volumes/4TB-BAD/Halbert/documentation/design/the-being.md`

This is the founding vision. It defines:
- What Halbert is becoming (a being that IS the computer, not a chatbot
  about computers)
- The design law: everything carries its why (four whys: why now, why care,
  why so, why trust)
- The physical design (conversation spine + context region + tray indicator)
- Proactive agency (the dial: off/quiet/balanced/assertive)
- Voice (first person / the computer / hybrid)
- The architecture (Haloysius mind + SourcePrep awareness + config brain +
  workers)
- The two proof slices (proactive config worry + reactive "how are you")

### 2. The design-to-implementation catalog

`/Volumes/4TB-BAD/Halbert/documentation/design/explorations.md`

This is every idea we could see, mapped to concrete code seams. It covers:
- A: The conversation core (collapse two chat paths into one)
- B: Module invocation (chat summons dashboard modules)
- C: The why data model (findings, proposals, rationale, provenance)
- D: The proactive channel (event flow, transport, gate, morning report)
- E: The config physiology brain (detectors, precedence, blast-radius)
- F: The SourcePrep adapter (awareness substrate)
- G: The mind spine (Haloysius wiring)
- H: Settings surface (being.yml)
- I: The ambient surface (tray indicator)
- J: Time and rituals
- Section 10: curation — what lands, in what order

### 3. The roadmap (the phased plan)

`/Volumes/4TB-BAD/Halbert/.handoff/ROADMAP-2026-08-23.md`

This is the approved phased plan:
- Phase 0: SourcePrep doc ingestion (the RAG corpus)
- Phase 1: Intake pipeline (signal detection, complexity routing, budget)
- Phase 2: RAG consolidation (SourcePrep replaces ChromaDB on chat path)
- Phase 3: Intake wiring (into the agent path)
- Phase 4: chat.py deprecation
- Phase 4.5: Boot-test gate (hard gate)
- Phase 5: Why data model + config brain v1
- Phase 6: Being config + voice
- Phase 7: Proactive channel
- Phase 8: Reactive slice + module invocation

### 4. The implementation plan (task-level breakdown)

`/Volumes/4TB-BAD/Halbert/.handoff/IMPLEMENTATION-PLAN-2026-08-23.md`

This is the task-level decomposition of the roadmap. 62 tasks across 8
phases, each with file paths, interfaces, acceptance criteria, and
dependencies. This is the most detailed document — read it for the
mechanics of what we're building, not for the vision.

### 5. The intake pipeline design

`/Volumes/4TB-BAD/Halbert/.handoff/INTAKE-PIPELINE-DESIGN-2026-08-23.md`

This is the design for the message intake module — the thing that runs
before the cognitive tick to classify intent, route by complexity, and
budget context. It defines the model-tier budget table and the complexity
router.

### 6. The RAG optimization plan (Phase 0 detail)

`/Volumes/4TB-BAD/Halbert/.handoff/RAG-OPTIMIZATION-PLAN-2026-08-23.md`

This is the detailed plan for Phase 0 — cleaning up the RAG corpus (30K
docs, 25% empty, 2K duplicates), replacing empty datasets, grouping into
markdown files for SourcePrep. It includes a sync analysis with the
implementation plan (section 7).

### 7. Existing design docs (for context)

`/Volumes/4TB-BAD/Halbert/documentation/design/philosophy.md` — the founding ethos
`/Volumes/4TB-BAD/Halbert/documentation/design/future.md` — long-term vision
`/Volumes/4TB-BAD/Halbert/documentation/design/macos-strategy.md` — macOS-specific plan
`/Volumes/4TB-BAD/Halbert/documentation/design/unified-model-picker.md` — model selection design

---

## What we want you to focus on

### For Doc 1 (direction + planning)

We have a lot of planning docs. What we may be missing:

- **Scope concerns:** Are we trying to do too much? Too little? Is the
  two-slice MVP the right cut, or should it be one slice done deeper?
- **Sequencing risks:** The dependency chain is Phase 0 → 2 → 3 → 4 → 4.5
  → 5/6 → 7 → 8. That's a long critical path. Where could we parallelize
  more? Where could we cut scope to land a slice sooner?
- **Architectural blind spots:** We have three stores (SourcePrep,
  memory_v2, SQLite findings). Is that the right split? We have two
  SourcePrep projects (halbert-knowledge for docs, halbert-host for
  config). Is that the right boundary? We're retiring ChromaDB from the
  chat path but keeping it for eval + telemetry. Is that the right
  migration strategy?
- **Missing categories of work:** We don't have: error handling strategy,
  observability/telemetry for the being itself, accessibility, i18n,
  mobile/remote access, multi-user, security model for the proactive
  channel (can a finding leak sensitive config in the notification?),
  testing strategy beyond unit tests, deployment/packaging.
- **The "obvious things we may have missed":** What would a senior
  engineer who has built a similar product immediately flag?

### For Doc 2 (design mechanics + user flows)

We have a vision and a plan but no detailed user flows. We need:

- **The first conversation (onboarding/birth):** The being.md mentions
  "birth" as a deeper vein. But what does the actual first-run experience
  look like? The user installs Halbert, opens it — what happens? Does the
  being introduce itself? Does it ask about purpose? Does it start
  scanning immediately or wait? What's the tone?

- **The proactive interrupt:** The being detects a config problem. What
  exactly appears on screen? Is it a toast notification? A slide-in
  panel? A tray badge that opens on click? What does the message say?
  How does the user interact with it (approve/dismiss/snooze/why)? What
  if they're in the middle of a conversation? What if the app is closed?

- **The "how are you?" flow:** The user asks "how are you?" What does the
  response look like? How is the vitals module summoned? Where does it
  render? How does provenance work as a UI element (the WhyChip)? What
  does the user click to see evidence? What does the evidence view look
  like?

- **The config-diff flow:** The being proposes a config change. What does
  the diff look like? How does approve/dismiss/rollback work as gestures?
  What does the blast-radius display look like? What happens after
  approval — does the being apply immediately or queue? What does the
  "I applied it, here's what changed" follow-up look like?

- **The morning report:** The user opens Halbert in the morning. What do
  they see? Is it a single message? A dashboard? A scrollable digest?
  How does it link to the findings/proposals it references?

- **The module palette:** The user wants to manually summon a module
  (e.g., vitals, storage, config-diff). How do they do it? A keyboard
  shortcut? A button in the input area? A command palette (Cmd+K style)?

- **The conversation surface itself:** What does a message look like?
  How are different message types rendered (text, module, proposal,
  evidence, morning report)? How does scrolling work when modules are
  inline? What happens to old modules — do they collapse?

- **The settings surface:** The "Being" tab in Settings. How does the
  voice picker work? The proactivity dial? Quiet hours? Purpose field?
  Is this a form, or something more conversational?

- **The tray indicator:** What are the visual states? How does the badge
  count work? What happens on click vs right-click? Does it have a
  context menu?

- **Error and degraded states:** SourcePrep is down. The LLM is down.
  A config detector throws. The being can't reach journald (macOS).
  What does the user see? How does the being explain its own
  limitations honestly?

- **The "living with it" rhythm:** Over a week of using Halbert, what
  does the interaction pattern look like? How many proactive interrupts?
  When does the morning report land? When does the user initiate vs the
  being initiating? What's the cadence?

---

## Constraints and context

- **No emojis.** Use icon fonts or clever graphic design. This is a
  project rule.
- **The product is a Tauri desktop app** (not a web app). The frontend
  is React + Radix UI + Tailwind. The backend is Python (FastAPI).
- **The target host is Ubuntu** (a home lab / dev server). The
  development host is macOS. The being must work on both, with graceful
  degradation on macOS (no journald, no systemd, MLX instead of Ollama).
- **The being is one mind, not many.** One thread of consciousness per
  host. Background workers are subsystems, not separate personalities.
- **The user is a technical user** — a sysadmin, developer, or
  power user. Not a beginner. The UI can be dense and information-rich.
- **The slices are the MVP.** Slice 1 (proactive config worry) and
  Slice 2 (reactive "how are you") are the minimum viable product.
  Everything else is post-MVP.
- **We have a lot of existing code.** This is not a greenfield project.
  The plan builds on existing infrastructure (Haloysius, SourcePrep,
  the approval engine, the config watcher, the state machine). The
  reviewer should look at the existing code where relevant.

---

## How to deliver

Write the two documents at:

1. `/Volumes/4TB-BAD/Halbert/documentation/design/REVIEW-DIRECTION-2026-08-23.md`
2. `/Volumes/4TB-BAD/Halbert/documentation/design/REVIEW-DESIGN-MECHANICS-2026-08-23.md`

Use markdown. Use diagrams (ASCII or mermaid) where they help. Be
specific — reference the existing docs by name and section. Propose
alternatives, don't just critique.

If you need to read code to ground your recommendations, the key files are:

- `halbert_core/halbert_core/dashboard/routes/agent.py` (the surviving chat path)
- `halbert_core/halbert_core/dashboard/routes/chat.py` (the legacy path being retired)
- `halbert_core/halbert_core/agents/state_machine.py` (the cognitive tick)
- `halbert_core/halbert_core/context/assembler.py` (context assembly)
- `halbert_core/halbert_core/dashboard/frontend/src/pages/Settings.tsx` (settings UI)
- `halbert_core/halbert_core/dashboard/frontend/src/pages/Agent.tsx` (agent page)
- `halbert_core/halbert_core/dashboard/frontend/src/components/SidePanel.tsx` (conversation UI)
- `halbert_core/halbert_core/dashboard/frontend/src/hooks/useAgentStream.ts` (SSE hook)
- `halbert_core/halbert_core/approval/engine.py` (approval flow)
- `halbert_core/halbert_core/config/watcher.py` (config watcher)
- `halbert_core/halbert_core/tools/write_config.py` (config write tool)

---

## Summary of where we are

We have:
- A clear vision (the-being.md)
- A complete design catalog (explorations.md)
- An approved phased roadmap (ROADMAP-2026-08-23.md)
- A task-level implementation plan (IMPLEMENTATION-PLAN-2026-08-23.md)
- An intake pipeline design (INTAKE-PIPELINE-DESIGN-2026-08-23.md)
- A RAG corpus optimization plan (RAG-OPTIMIZATION-PLAN-2026-08-23.md)
- ~30K docs in the RAG corpus (25% empty, needs cleanup)
- Existing code: state machine, approval engine, config watcher, context
  assembler, two chat paths (one being retired), Haloysius integration,
  SourcePrep integration

We do NOT have:
- A design doc focused on user flows and interaction mechanics
- External review of the overall direction
- A testing/QA strategy beyond unit tests
- An error handling and degraded-state strategy
- An onboarding/birth flow design
- A "living with it for a week" interaction rhythm design
- Accessibility, i18n, or mobile considerations
- A security model for the proactive channel

We are asking you to fill the first two gaps (design doc + direction
review) and to flag the rest.

---

*Questions? The build session is available for clarification. The
repository is at `/Volumes/4TB-BAD/Halbert`. All handoff docs are in
`.handoff/`. All design docs are in `documentation/design/`.*
