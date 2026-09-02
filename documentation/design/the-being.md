# The Being — Halbert's Next Form

> **Alignment note (2026-09-02):** §3's physical design shipped 2026-09-01 as the three-panel shell (`.handoff/REVIEW-REQUEST-SHELL-ARCHITECTURE-AND-ENTITY-NAV-2026-09-01.md` §9); ENGAGED/browsing are code modes, the UI says Conversation/Dashboard. §6 "One Halbert per host" is amended to "one mind per entity; an entity may have many bodies, each running its own tick against the one memory on the Canonical Host" (singular-entity design, 2026-08-31). §3/§9 say 17 pages; there are 14. §8's landed items (Presence Pill, panels, WhyChip, proactivity dial, voice setting) and the open ones (module summoning, tray indicator, the two proof slices end to end) are tracked as ROADMAP rows SHELL-1, ATTN-1, STATE-1. Concept status: `CORE-CONCEPTS-AND-ALIGNMENT-2026-09-02.md`.

**Status:** Vision + plan set (brainstorm synthesis, 2026-08-23, recalibrated same day).
Not yet an implementation plan.
**Reads with:** [philosophy.md](philosophy.md) (the founding ethos),
`.handoff/FOUNDATIONAL-RESEARCH-2026-08-21.md` (the diagnosis this builds on).

---

## 1. What Halbert is becoming

The founding ethos: *"an LLM that identifies as the computer itself is fundamentally more useful
than an LLM that merely answers questions about computers."*

The drift: Halbert became a 17-page IT operations dashboard with a chatbot bolted to the side.

The correction: **the conversation is the core layer; the dashboard runs under the hood; and
everything the user sees carries its "why."** Scope stays narrow and deep: exactly one "repo" —
the host OS itself — and exactly one job — know it, care for it, and talk to its person about it.

The being concept (identity, continuity, proactive channel) stays, but the frame is practical:
**the most helpful colleague you have, who happens to be your computer.** What makes it
meaningful to a user is not that it has feelings — it's that:

1. **It triages, not monitors.** What needs your attention *now*, ranked, with why. Everything
   else stays out of the way.
2. **Consequences are stated.** Every item says what happens if you ignore it. No naked metrics.
3. **Every claim can show its provenance.** One click from any statement to its evidence.
4. **Rationale persists.** *Why* things are configured the way they are is remembered forever.
5. **It remembers so you don't have to.**
6. **Actions have visible outcomes.** What changed, what it affected, how to undo.

---

## 2. The design law: everything carries its why

Nothing appears to the user without a why attached. Four whys, answerable on every element:

| Why | Question | Grounded in |
|---|---|---|
| **Why now** | Why am I seeing this at this moment? | severity × category × proactivity dial |
| **Why care** | What happens if I ignore this? | consequence model (blast-radius, failure modes) |
| **Why so** | Why is the system this way / why this recommendation? | rationale store, config history, reasoning |
| **Why trust** | What data grounds this claim? | provenance: logs, snapshots, metrics, snapshots |

Applied per element:

| Element | Why now | Why care | Why so | Why trust |
|---|---|---|---|---|
| **Proactive interrupt** | severity × dial | consequence | — | evidence links |
| **Summoned module** | why it's in this conversation | consequence | why the system is this way | live data |
| **Proposed action** | why now | what it fixes / what breaks without it | why *this* fix | blast-radius + rollback plan |
| **Config entry** | why it changed | what it controls | **who set it, when, and why** | snapshot history |

**"Why so" is where SourcePrep's concepts layer fits**: it is a file-anchored rationale store
(concepts = the why, anchored to paths, flagged stale when the anchor changes). The old WhyBrain
UI idea survives — capture why anything exists — but the store is real this time, not a
bespoke endpoint.

---

## 3. The physical design

### Core layer: the conversation (ENGAGED — the home)

```
┌──────────────────────┬─────────────────────────────────┐
│  CONVERSATION        │   CONTEXT REGION                │
│  (the spine —        │   (summoned modules)            │
│   always present)    │                                 │
│                      │   Halbert mentions storage →    │
│  Halbert: I found    │   the storage module renders    │
│  two SSH configs     │   here, live and interactive    │
│  that disagree...    │                                 │
│                      │   [approve] [dismiss] [why?]    │
│  you: which wins?    │                                 │
│                      │   or: the user summons modules  │
│                      │   manually from the palette     │
├──────────────────────┴─────────────────────────────────┤
│ [type…]                                  [modules ▾]   │
└──────────────────────┴─────────────────────────────────┘
```

- The conversation spine is always present when the app is engaged.
- **Module invocation:** as Halbert communicates, it summons dashboard modules into the context
  region — talking about storage summons the storage module, proposing a config change summons
  the diff module with approve/dismiss. The user can also summon any module manually.
- Every message and module carries its why affordance (§2).

### Under the hood: the dashboard (browsing mode)

Same window, module grid instead of the conversation layout. Direct browsing, bulk operations,
settings, the Memory/Jobs/inspection surfaces. Always accessible, never the home. The 17 pages
get refactored into **modules: one component, two containers** — standalone in the dashboard,
summoned in the conversation.

### Ambient: the tray indicator (at rest)

Calm / needs-attention / urgent. Halbert works in the background without taking screen space.
Click / hotkey / `halbert` in a terminal → ENGAGED.

### Proactive: the channel that opens on its own

When something crosses the threshold, ENGAGED slides in — and **the first message justifies the
interruption**: what it found, why now, why care, what it proposes. Configurable (§4).

---

## 4. Proactive agency: configurable presence (decided)

One mechanism, gated by **severity × category × user preference**:

| Setting | Behavior |
|---|---|
| **Off** | Never initiates. Purely reactive. |
| **Quiet** | Critical findings only (failing drive, security exposure, a decision it needs). Indicator pulses; no auto-open. |
| **Balanced** (default MVP) | Important findings + a scheduled morning report. Auto-open for critical only. |
| **Assertive** | Anything worth saying — anomaly, drift, a question, a pattern. Panel slides open on its own. |

Per-category overrides (assertive for security, quiet for storage). Post-MVP: a learning loop —
which interrupts did you act on — that suggests dial adjustments rather than auto-tuning.

---

## 5. Voice: configurable self-reference (decided)

Same self-model underneath; only the expression changes:

| Voice | Example |
|---|---|
| **First person** (default) | "I'm worried about `/dev/sda1`. I logged three read errors this morning." |
| **The computer** | "Your computer's primary drive logged three read errors this morning. I'd check it." |
| **Hybrid** | First person for state, neutral for concerns. |

A system-prompt + continuity-renderer setting. First-person is the founding ethos and stays
default; the setting exists because some users find "I" uncanny.

---

## 6. The architecture: three pillars, one mind, many hands

```
        ┌─────────────────────────────────────────────────────────┐
        │  Haloysius core — THE MIND (external package)            │
        │  cognitive tick · continuity ledger · memory_v2          │
        │  believes / wants / worries_about / conflicted_about     │
        │  → mapped onto system state                              │
        └───────────────────────────┬─────────────────────────────┘
        ┌───────────────────────────┼─────────────────────────────┐
        ▼                           ▼                             ▼
┌──────────────────┐   ┌──────────────────────────┐   ┌──────────────────────┐
│ SourcePrep        │   │ Config Physiology Brain  │   │ THE HANDS (workers)  │
│ — awareness       │   │ — owns config & settings │   │ log ingester         │
│ OS indexed as a   │   │ misconfig detection      │   │ config watcher       │
│ repo: /etc,       │   │ dedupe · dependency      │   │ sensor layer         │
│ systemd, dotfiles,│   │ graph · blast-radius     │   │ diagnostics          │
│ logs, snapshots   │   │ propose → approve → act  │   │ Deep Thinker         │
│ concepts (the why)│   │ → rollback               │   │ (background analysis)│
│ observations      │   └──────────────────────────┘   └──────────────────────┘
└──────────────────┘
```

**One mind, many hands (decided).** One Halbert per host: one thread of consciousness (cognitive
tick + continuity ledger + memory_v2). Background workers are subsystems reporting into the one
mind, not separate personalities. The user always experiences one Halbert that happens to have
been doing things in the background.

**Sibling leverage:**
- **Haloysius** (agnostic cognitive core, external package): the mind. Halbert implements its own
  `ModelBackend` / `RetrievalBackend` / `GovernancePolicy` behind the seam — our model/RAG/
  governance layers are stronger than the core's and stay ours.
- **SourcePrep** (repo: CoDRAG): the awareness substrate + the rationale store (concepts = the
  why, file-anchored, stale-flagged). Pointing it at the OS needs a thin adapter, not a fork
  (verified: RQ2 in the foundational research).
- **Halbert keeps and deepens:** model layer, RAG stack, governance (approval/autonomy/policy),
  discovery scanners, ingestion, config primitives — plus the piece neither sibling has: the
  config physiology brain.

---

## 7. The proof slices (decided: both, in parallel)

Two thin end-to-end behaviors, each touching all three pillars, each demonstrating the why-law:

### Slice 1 — Proactive: "I found a config problem, and here's why you're hearing about it"
Detect a config problem (drop-in conflict, drift from known-good, contradiction) → config brain
computes the consequence and blast-radius → the mind records it (`conflicted_about`) → the
proactive channel opens with the finding **and its why**: why now, what happens if ignored, the
proposed fix, what it affects, how to undo. The SSH config summons into the context region.

### Slice 2 — Reactive: "How are you?" answered with evidence
You ask about its state → it retrieves its biography (recent logs, config changes, self-knowledge)
via the awareness layer → answers in the configured voice, grounded in real data, **every claim
one click from its provenance**. A vitals module summons alongside the narrative answer.

Each slice proves one direction of the relationship: **it speaks** (slice 1) and **you speak to
it** (slice 2). Together they are the minimum viable product.

---

## 8. Sequencing sketch

1. **Mind spine (Haloysius):** register Halbert's `AppSeam`; wire `advance_turn` + continuity +
   memory_v2 into one conversation path; add the `worries_about` / `conflicted_about` / `wants` /
   `believes` predicates (Haloysius WP-8 — possibly our upstream contribution); scheduled
   unprompted tick so the being keeps working between conversations.
2. **Awareness (SourcePrep):** register the host config tree as a project with OS globs; feed it
   from `config/snapshot.py` + `config/watcher.py`; route retrieval, observations, and the
   rationale store through it.
3. **Config brain v1:** misconfig detection (drop-in conflicts, schema drift, contradictions) +
   blast-radius via config dependency edges (Phase 3 groundwork exists) + propose-through-approval
   using the existing `write_config` tool + approval engine. Every finding ships with its four whys.
4. **Surface:** conversation spine + module context region + tray indicator + proactive-open
   channel; voice setting; proactivity dial; the why affordance on everything. Dashboard pages
   refactor into dual-container modules; demote the dashboard to browsing mode last.

The slices land as soon as (1)–(3) have their thin versions; (4) is what the slices are felt
through.

---

## 9. What we deliberately keep / demote / cut

**Keep (load-bearing):** model layer + routing, retrieval + corpus (moving from ChromaDB to
SourcePrep — ChromaDB stays for eval only), governance stack (approval/autonomy/policy — made
real), discovery scanners, ingestion, config snapshot/parser/watcher primitives, `write_config`
tool, conversation summarization/compression cascade.

**Demote:** the 17 dashboard pages → modules (dual-container) + browsing mode. Settings gains the
being's own preferences (voice, proactivity, purpose).

**Cut (when the mind spine lands):** the dual chat paths collapse into one conversation on
Haloysius; the old side-panel chat retires; dead scaffolds cut in Phase 1 stay cut. The WhyBrain
UI folds into SourcePrep concepts rather than a bespoke `/api/why`.

---

## 10. Deeper veins (worth keeping in view, not MVP)

Ideas from the brainstorm that are real but later:

- **Inner life:** the tick runs unprompted between conversations — consolidating, reviewing,
  preparing the morning report. Continuity of experience independent of attention.
- **Worry as persistent state:** `worries_about(/dev/sda1)` lives in the ledger until resolved
  and colors responses in the meantime; relief when cleared.
- **Purpose:** "What am I for?" (NAS / dev box / laptop / server) shapes what it watches and
  interrupts for.
- **Birth:** onboarding reframed as the first conversation — wake up, discover the body, ask
  purpose, on in obvious cases ask if it is a server or workstation for inatance (found server ram and motherboard, etc)
- **Confession:** a record of its own actions and their outcomes; admits what proved wrong.
- **User model:** your hours, habits, skill level — explanations and timing calibrated to you.
- **Death/migration:** identity survives hardware — self-knowledge + continuity export to a new
  machine.
- **Society of beings:** multi-host as relationships, not tabs; machines that know each other
  through you.
- **Rituals:** morning report, Sunday backup review, monthly storage audit.

---

## 11. Open questions

- **CLI vs desktop shell for ENGAGED** — which is the reference surface for the slices?
  (Leaning: desktop first — proactive-open is the signature behavior and needs a GUI.)
- **Module granularity** — how do the 17 pages decompose into summonable modules? Which merge?
- **The why data model** — consequence and provenance fields on findings/proposals: what schema,
  and where does each field come from (config brain, SourcePrep, snapshots)?
- **Onboarding/birth** — how much of current Onboarding.tsx survives as the first conversation?
- **Purpose taxonomy** — free text, or a starter set that seeds watch-priorities?
- **The attention-learning loop** — what signal, and when is auto-suggesting dial changes safe?
- **Migration** — what precisely exports, and what's body-specific and must be relearned?

---

*Vision layer only. The design-to-implementation catalog (every idea, its code seam, and the
curation of what lands in each slice) lives in [explorations.md](explorations.md).
The phased implementation plan — infrastructure spine (Phases 0–4.5) then being layers
(Phases 5–8) — lives in `.handoff/ROADMAP-2026-08-23.md`. The intake pipeline design is in
`.handoff/INTAKE-PIPELINE-DESIGN-2026-08-23.md`. The foundational diagnosis this builds on
is in `.handoff/FOUNDATIONAL-RESEARCH-2026-08-21.md`.*
