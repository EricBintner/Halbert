# PLAN: Social Attunement — Halbert's side

**Date:** 2026-09-06
**Engine design:** `/Volumes/4TB-BAD/Haloysius/docs/superpowers/specs/2026-09-06-social-attunement-design.md` (DRAFT, not approved, not implemented)
**Our review:** `/Volumes/4TB-BAD/Haloysius/.handoff/HANDOFF-SOCIAL-ATTUNEMENT-REVIEW-REQUEST-2026-09-06.md` §10 (committed there as `40d461d`)
**Status:** **partly built** on `feat/attunement-halbert` (see §0). The engine
approved Phase A + Phase B core in handoff §14 and assigned Phase B wiring and
Phase D to Halbert; §2's no-regret work and the engine-independent half of §3
are landed and green. The rest below is planning only. The engine design is itself unapproved, and **seven** items are blocking for Halbert — five ours, two co-signed from Halley's review after we verified they are Halbert defects too (`44882ee`, §10.9).

---

## 0. Build status (2026-09-06)

Branch `feat/attunement-halbert`, four commits, **5626 tests pass** across the
repository with 6 strict xfails recording engine parser gaps.

| Landed | Module | Amendments |
|---|---|---|
| ✅ | `attunement/surfaces.py` — push/ambient/pull, every surface assigned | A-HB-8 |
| ✅ | `attunement/subject.py` — identified / unattributed / unknown | A-HB-3 |
| ✅ | `attunement/operation_state.py` — the four operation fields (HB-N1) | A-HB-1 |
| ✅ | `attunement/store.py` — SQLite store, satisfies `StandingRequestStore`, `transaction()` serializes RMW cross-process | A-HB-2, A-HB-24 |
| ✅ | `attunement/codec.py` — engine dataclasses ↔ dicts, driven by the engine's type hints | — |
| ✅ | `attunement/sensor.py` — thirteen receptivity rows | A-HB-12, A-HB-14, A-HB-19, A-HY-9 |
| ✅ | `attunement/shadow.py` + `proactive/gate.py` — every decision recorded (§4.6 stage 1) | A-HB-25 |
| ✅ | Morning report reaches the user at Balanced (HB-N2) | — |
| ✅ | `testing/corpora/halbert.yaml` — 52 cases in the shared fixture | corpus |
| ✅ | `test_attunement_engine_sync.py` — mirrors and constants asserted against the engine | — |

**Not yet built:** the `AttunementContext` builder and the `decide()` call
(HB-D3), `begin_turn` on the agent path (HB-D1/D2), the engagement state on
the Presence Pill (HB-N3), the surfaces decision in `DECISIONS.md` (HB-N4),
and everything in §3 from HB-D4 onward.

**Sync with spec revision 2: clean.** All four mirrored enums match exactly,
our `SituationSignals` fields are a strict subset, our two duplicated defaults
are asserted against the engine's rather than copied, and the store satisfies
the Protocol including `transaction()`. The three rows we do not feed are
asserted by name so the gap stays a decision. Six false negatives found in the
engine's parser are reported in handoff §10.11.

---

## 1. What this is

Haloysius is proposing `haloysius.attunement`: a directive parser ("leave me alone", "talk to me more"), a standing-request ledger, a receptivity estimator, one engagement policy producing SPEAK / SPEAK_MINIMAL / ASK_FIRST / HOLD / SILENT, and a persona stance that turns being told to be quiet into cognitive events rather than a mute switch.

For Halbert it replaces the *decision* half of `proactive/gate.py` and adds something we do not have at all: memory of what the person asked for. Our gate today answers "may this severity pass this dial at this hour". It cannot answer "they told me to shut up ninety seconds ago".

**The honest summary of the value:** Phase A of the engine's plan — directives, ledger, envelope, stance, prompt block, *no sensors* — is the part that changes the product. Everything after it is optimisation of timing. We should take Phase A eagerly and Phase B carefully.

---

## 2. What we do regardless — the no-regret work

These four items are worth doing whether or not attunement is ever approved, and three of them are already implied by open roadmap rows. Doing them first also means that if attunement lands, our Phase D is nearly free.

### HB-N1. Extract the operation-state predicate, once
The observation-lenses plan (`HANDOFF-OBSERVATION-LENSES-2026-09-04.md` §8 B4) specifies `suppress_lens(composed, *, intent, approval_pending, open_findings, flavor_intensity, proactivity)` — a pure function over `intent == "troubleshooting"`, `has_error_indicators`, a per-turn `required_confirmation` flag, `MessageSignals.is_destructive`, `is_incident` (`safe_mode_active` or an open critical finding), and subject overlap via `canonical_entities()`.

That predicate is also the answer to the biggest gap in the engine's receptivity table (our A-HB-1). Build it as a standalone, independently testable function returning a small typed record — not as a boolean buried in the lens gate — so both consumers read it:

```
halbert_core/proactive/operation_state.py
    OperationState(awaiting_confirmation, operation_in_progress,
                   destructive_turn, incident_active, subject_overlap)
    current_operation_state(...) -> OperationState
```

**Depends on:** the lenses branch landing B4. **Blocks:** HB-D2, and the lens gate itself. **Effort:** small; it is a refactor of code being written anyway.

### HB-N2. Fix the morning report's severity floor
`proactive/morning_report.py` derives severity from open findings, so a clean day yields `info`, and `_PROACTIVITY_THRESHOLD["balanced"] == 1` suppresses it. The engine's §6.1 assumes the report reaches the user at Balanced; ROADMAP `ATTN-2` says "morning report on by default at Balanced and persisted"; `C2-10` (report persistence) is open. Our code disagrees with both.

Fix: the report is `user_requested=True` in engine terms — the user configured a daily brief — and should pass the dial at Balanced independently of the day's findings. Practically: give the report its own gate path rather than letting the findings' severity decide whether the user hears from us at all.

**Independent of attunement. Already an `ATTN-2` obligation.**

### HB-N3. Engagement state on the Presence Pill
`C2-08` ("attention state on the pill in every layout") is open under `ATTN-2`. Today it would show attention; after attunement it shows engagement — withdrawn / minimal / normal / chatty, plus a held count. Design the pill's state model now with the second axis in it, so we do not ship it twice.

### HB-N4. Decide the surface taxonomy
Our attention channel is the bell, `/findings`, `/api/being/events`, the Presence Pill, the tray indicator, panel auto-open, and voice on satellites. "Shut up" means the voice and the auto-open. It must not empty the bell and must never hide a findings row.

Write the taxonomy down as a ratified list and put it in `DECISIONS.md`. **Revised after Halley's cross-check** (§10.9.3): the axis is **push vs. pull**, not voice vs. text — their narration case proves text can be push — with a third value restored because our bell badge is neither:

- `PUSH` — arrives unbidden and spends attention: voice, satellite audio, notifications, panel auto-open. **Suppressed** under a withdrawal, in every medium.
- `AMBIENT` — changes unbidden but demands nothing: bell count, tray badge, Presence Pill. **May update, must not escalate** — the count increments; nothing pulses, chimes or opens.
- `PULL` — persists on a surface the user navigates to: `/findings`, transcripts, logs. **Never suppressed by attunement.** This is a decision we need with or without the engine — the same question is already live for `the-being.md` §4's per-dial UI behaviour ("indicator pulses; no auto-open" vs "panel slides open on its own"), which currently exists only as prose.

---

## 3. If and when engine Phase A lands

### HB-D1. Wire the tick
`persona/cognition_tick.py` gains directive parsing; we supply `subject_id`, the ledger store, and the persona-name list from `identity.resolve_entity_name()` plus the computer name (A-HB-11). `TurnResult.envelope` reaches the assemble step in `agents/state_machine.py`, and the `[ATTUNEMENT]` block enters `context/prompt_pipeline.py`.

**Gated on A-HY-3** (`begin_turn`): **verified blocking for us**, not just Halley. `_handle_reflecting` (`state_machine.py:2852`) runs after the model has produced the turn's content and hands the tick a synthetic `assistant_response` built from `ctx.observations[-3:]`; `_handle_responding` (`:3065`) ticks with the real reply only for turns that skipped REFLECTING via a loop guard. So the directive is parsed *after* the reply is written, on every path, and *which* site parses it depends on how the turn terminated. Parsing must happen before the model runs, or Phase A does not work here.
**Gated on A-HY-1** (standalone `render_attunement_block()`): Halbert does not import `haloysius.context.prompt_pipeline` — the only engine import in our whole agent path is `from haloysius.seam import get_app_seam` (`:3245`). Our assembly is `prompts/agent_prompts.py::AgentPromptBuilder.build_system_prompt` plus `context/assembler.py::assemble`. As specified, the `[ATTUNEMENT]` block renders nowhere in this product.
**Gated on A-HB-3** (unattributed vs unknown): without it, every dashboard text turn inherits the household's most restrictive standing request.
**Gated on A-HB-10** (now the scope-hint form, §10.9.8): without it, a bare `"stop"` during `AgentState.EXECUTING` costs the user their cancel and buys two hours of silence. We will not ship the parser on the voice path until this exists.

### HB-D2. Ship the reactive half first, alone
Directives + envelope + stance, on the conversation path only. No proactive changes, no sensors, no ledger sharing across bodies. "Be quiet" acquires real semantics: recognised, acknowledged in the right tone, honoured for the right scope, and the persona stops offering to fix things.

This is the smallest change with a visible product effect, and it produces the directive corpus that Phase B's weights should be tuned against rather than guessed at.

**Verification:** assert on the assembled prompt, not on model output — same discipline the lenses plan's B4 verification uses, and the same reason (a green test on a mapper proved nothing when the text that actually reached the model was un-normalised; see `REVIEW-BRANCH1-OBSERVATION-SINK-2026-09-05.md` finding 1).

### HB-D3. The gate becomes an adapter
`ProactiveGate.should_notify` builds an `AttunementContext` and calls `policy.decide()`. Quiet hours stays delegated where it is. Safe mode becomes a consumer LIMIT with `severity_floor=CRITICAL, revocable_by_speech=False` (**gated on A-HB-17** — without it "talk to me more" lifts an incident gate). Finding snooze/dismiss become `DeferredTopic` lookups with an opaque `topic_key` (**gated on A-HB-13**).

Net effect on our code should be **subtractive**: the gate gets shorter, and four partial answers become one call.

**Gated on A-HB-4** (`EngagementDecision.reasons`): `the-being.md` §2 ratifies that nothing appears to the user without a why, and `why now` is documented as "severity × category × proactivity dial". The moment receptivity and standing requests enter that decision, the documented answer is false. We cannot ship the adapter until the decision carries its reasons out.

**Gated on A-HB-5** (HOLD suppresses the utterance, never the action): our proactive events frequently announce work that `scheduler/` and `home/cognitive_loop.py` have already done or scheduled. A HOLD that drops the event is a data-loss bug wearing a politeness costume.

### HB-D4. `SituationSensor`, in dependency order
Cheapest and least invasive first; each step independently shippable:

1. `system/display_power.report_idle` → IDLE. Already flowing, ≤30 s, no new plumbing.
2. `operation_state.py` (HB-N1) → the A-HB-1 fields. Highest value per line for this product.
3. `home/occupancy.py` + timeline `occupancy_change.direction` → ARRIVING / DEPARTING / others_present. Arrival is the good signal (BLE <60 s); departure only at the transition, because `AWAY_GRACE_PERIOD_SECONDS = 300` makes steady-state departure undetectable (A-HB-12).
4. `audio/speech/wake_word.py` → `addressed_to_persona`, where openwakeword is installed. Tri-state: `None` when absent, never `False` (A-HB-14).
5. `audio/acoustic/audio_tagger.py` speech class → `verbal_channel_busy`, low confidence, behind a setting. It cannot separate a person from a television.
6. HA calendar → `calendar_busy`.
7. Vision activity → last, opt-in, provenance-tagged, never persisted to the outcome ledger (A-HB-19).

### HB-D5. Federation
**Gated on A-HB-2.** `federation/peers_config.py` defines a peer with `role="body"` as another body of the same entity, one memory on the canonical host. A ledger under the engine's own `data_home()` is per-host, so a withdrawal spoken to the kitchen body is unknown to the study body. Once the store is injectable, we back it with the canonical host and the failure disappears.

Until then, attunement is **single-body only** and we should say so in the settings UI rather than let a user discover it by being ignored.

---

## 4. Implementation architecture

### 4.1 Where the code lives

A new adapter package, `halbert_core/attunement/`:

| Module | Owns |
|---|---|
| `sensor.py` | The `SituationSensor` implementation. Fuses occupancy, idle, operation state, acoustic, calendar into `SituationSignals` with per-signal provenance and freshness. |
| `subject.py` | Subject resolution — `identified` / `unattributed` / `unknown` (A-HB-3) from speaker identity plus channel. |
| `store.py` | SQLite-backed `StandingRequestStore`: standing requests, outcomes, suppressions. |
| `surfaces.py` | The PUSH / AMBIENT / PULL taxonomy (HB-N4) and the assignment of every Halbert surface to a class. |
| `adapter.py` | Builds `AttunementContext`, calls the engine, translates an `EngagementDecision` into surface actions. |

**Why a new package rather than extending `proactive/`.** `proactive/` is about *events*; `home/` is about *the house*. Attunement is about *the person*, and it must be callable from both plus the agent turn path. Filing it under either buries a cross-cutting concern inside a domain package, and we would end up importing `home/` from the agent path to ask whether someone is in the room — which is precisely the coupling `capabilities.py` exists to avoid.

Callers change, not structure: `proactive/gate.py` becomes a thin caller (HB-D3), `agents/state_machine.py` calls `begin_turn` before assembly, `home/cognitive_loop.py` calls `assess_presence` on occupancy transitions.

### 4.2 Three call sites, three cadences

| Call site | Engine call | Cadence | Budget | Note |
|---|---|---|---|---|
| `state_machine` before assemble | `begin_turn` | once per user turn | ~5 ms | in the turn's critical path; a slow call is felt as lag |
| `proactive/gate.should_notify` | `decide` | per proactive event | ~10 ms | tens per day; may be called speculatively for the shadow log |
| `home/cognitive_loop` | `assess_presence` | per occupancy transition + scheduled tick | ~50 ms | must never block the loop; runs on an always-on box |

This table is why **A-HB-22 (pure `decide`)** matters: two of the three sites want to call it speculatively, and one is in a latency-sensitive path. A policy function that reads the ledger and writes an outcome row cannot serve any of them well.

### 4.3 Subject resolution — the one piece of real logic we own

`integrations/voice_auth_gate.py` collapses three different situations onto `speaker_id=None` (§10.1.7). The adapter un-collapses them:

| Channel | Evidence | `subject_confidence` | Scope a directive may create |
|---|---|---|---|
| Dashboard, authenticated session | session identity | `identified` (primary) | entity-wide |
| Local typed turn, no session identity | possession of the host | `unattributed` | entity-wide |
| Voice, CAM++ ≥ member threshold | biometric | `identified` (`speaker_id`) | entity-wide |
| Voice, ≥ guest threshold only | weak biometric | `identified`, role `guest` | **area only**, short expiry |
| Voice, below threshold | none | `unknown` | **area only**, short expiry |
| Satellite, no speaker model installed | none | `unknown` | **area only**, short expiry |

The rule that falls out: **entity-wide silence requires entity-level identity.** Anything less quiets a room.

### 4.4 Storage

One SQLite database, `attunement.db`, alongside `findings.db` under `data_dir()`. Three tables: `standing_requests`, `outcomes`, `suppressions`.

Not inside `findings.db`: different lifecycle and different export semantics — findings are user-facing records we may want to hand over or purge independently of behavioural state. Not JSON: see A-HB-24 and the ten-constructor argument.

`purge(subject_id)` (A-HB-2, per Halley) deletes across all three tables in one transaction.

### 4.5 Testing

- **The pure `decide` gets a table test** — `(context → outcome)` cases asserted against the engine's *exported* constants, imported never copied. We have a repo-wide vocabulary guard test precisely because duplicated constants drifted while sixteen local tests stayed green.
- **The parser gets the shared corpus fixture**, must-not-fire rows included, contributed to the engine (§10.10.8.3).
- **The suppression log gets a composition test**: an event suppressed by two mechanisms must name both, not the first one that fired.
- **Assert on the assembled prompt, not on the mapper.** The `fix/observation-sink` review found a green mapper test sitting over a live prompt-injection path because the text that actually reached the model was normalised nowhere. The `[ATTUNEMENT]` block deserves the same discipline.

### 4.6 Rollout: shadow mode first

Attunement changes a *suppression* system, and suppression failures are silent — the class of bug that does not page anyone. So it ships in two stages, gated by capability:

1. **Shadow.** Compute the decision, write it to the suppression log with its reasons, and **do nothing with it**. `ProactiveGate` keeps deciding. We then have a queryable record of every place the new policy would have disagreed with the old one, over real days, before a single user-visible behaviour changes.
2. **Live**, per surface, starting with the surfaces where being wrong is cheapest — AMBIENT before PUSH, morning report before findings, desktop before satellites.

Shadow mode is cheap because `decide()` is pure (A-HB-22), and it is the only honest way to answer "did this make things quieter than we meant?" before it has already done so.

---

## 5. New Halbert features this unlocks

These are the reasons to want the feature, not just to accept it.

### F1. The dial learns — a roadmap item we already committed to
`the-being.md` §4 closes with: *"Post-MVP: a learning loop — which interrupts did you act on — that suggests dial adjustments rather than auto-tuning."* The engine's outcome ledger *is* that loop, recorded as `(source, severity, receptivity level, activity, outcome, reaction)`.

The feature: after enough evidence, a finding-shaped suggestion — "You've dismissed six of the last eight storage notices. Set storage to Quiet?" — with the four whys attached and a one-click `category_overrides` write. **Suggests, never auto-tunes**, exactly as ratified. This is the single most valuable thing attunement gives us and it costs almost nothing once the ledger exists.

### F2. Spoken and clicked become one mechanism
Saying "not that again" and clicking Dismiss on a finding become the same `DeferredTopic` write. Today the voice path cannot dismiss anything and the UI path cannot be reached by speech. Requires A-HB-13's opaque `topic_key` plus a small entity-extraction step on our side (`canonical_entities()` already exists).

Second-order benefit: `allow_escalation` gives us something the findings store lacks today — a dismissed topic that reopens when its severity strictly increases. A disk you told us to stop nagging about, that then goes pre-fail, speaks again.

### F3. The morning report stops being a routine
Anchor it to the person rather than to the clock: hold it `ON_ARRIVAL` (or on the first transition after the earliest allowed time) instead of firing at 08:30 every day. Better timing by the research (Cha's 96% on returning to a room), and it removes the failure the KAIST participant described — "the slightest feeling that the speaker is following a routine". Pairs directly with the lenses work, whose whole premise is that the morning report is the right first surface for interpretation.

### F4. Operation-aware silence
Halbert stops talking during `AWAITING_CONFIRMATION`, in-flight destructive tool calls, and open incidents — because it knows what it is doing, not because a clock said so. One predicate (HB-N1) serves both this and the lens suppression gate. This is the feature a sysadmin tool most obviously should have had from the start.

### F5. Per-room quiet
"Be quiet in here" silences the kitchen satellite and leaves the study alone. Requires A-HB-18's `scope_key`; we fill it with an area id. Also the mechanism for guest handling: a `guest` or `restricted` role (we have both, via `RoleGate`) can quiet the room they are in with a short expiry, and cannot silence the house for a week.

### F6. The held queue as a surface
"What did I miss" — the one phrase in our corpus that is both a RESUME and a queue flush. Three things while you were away, as one digest rather than twelve interruptions (A-HB-6), each with its whys, on the pill and in the conversation.

### F7. `why now` gets honest
Once A-HB-4 lands, the `WhyChip` can say *"critical, and you'd just come back into the room"* or *"held for forty minutes because you asked for quiet"* instead of restating the dial. The Four Whys stop being a static explanation of policy and start being an account of an actual decision.

---

## 6. What we are explicitly not doing

- **No age model, no emotion inference from vision, no new sensors.** Every signal in HB-D4 already exists or is off by default.
- **No migration or back-compat shim.** There are no users; standing requests start empty.
- **No second preference-inference path.** "Prefers quiet mornings" is a `memory_v2` `ObservationStore` preference row, which the lenses work already routes; the engine should emit an event and let us write it (our answer to the engine's Assumption 9).
- **No auto-tuning of the dial.** Suggestions only, per `the-being.md` §4.
- **Nothing on the voice path before A-HB-10.** See HB-D1.

---

## 7. Pitfalls

Ordered by how hard each is to detect after it happens.

**P1 — Suppression composes silently, and nobody notices.**
Eleven mechanisms can eat an event (dial, category override, quiet hours, safe mode, snooze, dismissal, WITHDRAW, LIMIT floor, DEFER_TOPIC, low receptivity, an unreleased HOLD). Every one is silent by design. A warning eaten by an interaction of two is indistinguishable from a warning never generated. *Mitigation:* A-HB-25's suppression log, plus §4.6 shadow mode, plus the composition test in §4.5. This is the pitfall that justifies most of the rest of the design.

**P2 — The learning loop ratchets toward silence.**
Reactions exist only where the persona spoke, so the ledger accumulates evidence about speaking and none about holding. Silence looks costless forever. *Mitigation:* A-HB-26 — ASK_FIRST as the exploration arm, plus retrospective labelling when a held item is released. Do not ship Phase C adaptation without one of them.

**P3 — Attunement becomes the place bugs hide.**
"Why didn't it alert?" acquires a plausible, unfalsifiable answer. Every future missed-alert report now has a suspect that is expensive to rule out. *Mitigation:* the suppression log again — a missed alert either appears in it with reasons, or attunement is exonerated in one query.

**P4 — The parser hears a room, not a text box.**
Halley's parser reads what a user typed *to the persona*. Ours reads ASR of a space containing a television, a phone call, children and a dog. Every entry in the must-not-fire list (§10.2) is far more likely here, and a false WITHDRAW silences a house. *Mitigation:* gate on `addressed_to_persona`; treat "no wake word installed" as unknown rather than addressed (A-HB-14); area-scope any directive parsed without addressing evidence; the scope-hint guard (§10.9.8).

**P5 — Decision flapping reads as a hardware fault.**
A person moving around a kitchen crosses thresholds repeatedly; an indicator that blinks or a persona that starts and stops looks broken rather than uncertain. *Mitigation:* A-HB-23 hysteresis and dwell — preferably engine-side, since every always-on consumer needs it.

**P6 — Surveillance by composition.**
Occupancy, acoustic, calendar, idle and vision are each individually consented and individually modest. Fused continuously into an activity estimate, they are an activity profile — and unlike a finding, it is computed whether or not anyone asked. *Mitigation:* A-HB-19 provenance; never persist `vision`/`audio`-derived labels; keep the fused estimate in memory and out of the durable log; and make the sensor's inputs visible in settings, per-source, with the same off-by-default posture the vision stack already has.

**P7 — Emotional drift from ambient ticks.**
`home/cognitive_loop.py` calls `advance_turn` on a schedule (it batches events rather than ticking per event, which bounds this — but does not eliminate it). If the stance re-emits `DRIVE_FRUSTRATED` and SADNESS every tick a WITHDRAW is active rather than once when it is applied, a single "leave me alone" compounds into a sulking persona over an afternoon. *Mitigation:* require that stance application is idempotent per standing request, not per tick, and verify it against the engine before wiring the home loop.

**P8 — Multi-room audio bleed.**
Two satellites within earshot both hear "be quiet". Either the directive is applied twice, or it is applied to the wrong area. *Mitigation:* directives carry the observing area; the adapter deduplicates by `(subject, utterance window)` before writing.

**P9 — Losing the dial's presentation half.**
`the-being.md` §4 gives each dial level a UI behaviour — "indicator pulses; no auto-open" at Quiet, "panel slides open on its own" at Assertive. Attunement models permission, not force. Mapping only severity silently drops ratified behaviour. *Mitigation:* HB-N4's surface taxonomy carries it; auto-open is PUSH, the pulse is AMBIENT.

**P10 — A multi-writer JSON ledger loses a withdrawal.**
Five entry points, ten constructors, read-modify-write. *Mitigation:* A-HB-24 and §4.4 — SQLite, as `FindingStore` already is.

---

**P11 — Three dials contradict each other.**
`proactivity`, the incoming `flavor_intensity`, and the engine's invitation level all answer "how much does it talk", and two of the three ship within weeks of each other. *Mitigation:* A-HB-7's precedence rule — the consumer dial is a ceiling, invitation positions within it, flavour is orthogonal but forced off while withdrawn — written into `DECISIONS.md` before any of the three ships.

**P12 — A held critical finding that nobody can see.**
HOLD is invisible until a surface shows it, and a held critical is strictly worse than an interruption. *Mitigation:* ship HB-N3's pill state, including the held count, in the same change as the first HOLD — never after it.

**P13 — Ledger drift across bodies.**
Until A-HB-2, a withdrawal spoken to one body is unknown to the next. The failure is the worst kind: the persona visibly ignores a direct instruction one room over. *Mitigation:* single-body only until the store is injectable, stated in the settings UI rather than discovered by being ignored.

**P14 — Engine integration points that do not reach us.**
Three of §5.9's five miss at least two consumers; we verified two miss Halbert entirely (§10.9.1, §10.9.2). Building against §5.9 as written would produce a wiring that compiles and does nothing. *Mitigation:* treat §5.9 as conveniences over a free-function core; A-HY-1, A-HY-3, A-HB-22.

---

## 8. Opportunities

**O1 — "What haven't you told me?"**
The suppression log (A-HB-25) is a mitigation that happens to be a feature. `why now` gets its complement: a surface answering *why not*, with the reasons that fired, the held queue, and the option to release. No proactive assistant we know of can answer this question, and for a sysadmin tool it is arguably more valuable than the alerts themselves — it converts "I hope it would have told me" into something checkable.

**O2 — `AVAILABLE` is the state that makes always-on tolerable.**
Without it Halbert has two modes: mute, and talking. The middle — present, listening, unobtrusive — is the whole felt difference between a house that watches and a house that is *there*. This is the single most product-defining item in the plan and it is currently absent from the engine (A-HB-21).

**O3 — Attunement × lenses is the ambient-presence thesis, complete.**
The lenses work decides *what is worth remarking on* (recurrence arithmetic over the timeline). Attunement decides *whether now*. Neither is much alone: selection without timing is a nagging assistant, timing without selection is a well-mannered one with nothing to say. Together they are "third time that grey van's parked out front this week", said at the moment the person walks in and not while they are mid-`fdisk`. Both plans should be sequenced as one.

**O4 — The dial learns, as already promised.**
`the-being.md` §4's post-MVP learning loop, delivered by the outcome ledger, suggesting never auto-tuning (F1).

**O5 — Shadow mode as a permanent capability.**
Built for rollout (§4.6), worth keeping: a "what would it have done" view over any policy or dial change, before it takes effect. Every future adjustment to the dial, a category override or a receptivity weight becomes a change you can preview against last week's real events rather than reason about.

**O6 — Halbert becomes the engine's proving ground.**
The §5.4 weights are literature-derived and currently unfalsifiable — no consumer has ever run them. We are the only one who can, and doing so converts the engine's shipped defaults from cited to measured (§10.10.8). That is the concrete form of being the design's primary voice: not more opinions, but the only evidence.

---

## 9. Sequencing and roadmap placement

Proposed new row, alongside `ATTN-1` / `ATTN-2`:

> **ATTN-3 — Engagement.** The persona can be told to be quiet, honours it for the right scope with the right tone, holds what it was going to say, shows what it is holding, and suggests dial changes from what you actually acted on.

Order:

1. **HB-N1 … HB-N4** — no-regret, independent of the engine, three of four already owed to `ATTN-2`.
2. *(gate)* **Phase A** approved and its blocking items resolved — A-HB-3, A-HB-4, A-HB-5, plus the two co-signed structural ones, A-HY-3 and A-HY-1, without which Phase A is unreachable in Halbert regardless of the rest.
   *(separate gate)* **Phase B** additionally needs A-HB-1 (operation state), A-HB-2 + A-HB-24 (an injected, serializing store), A-HB-21 (`AVAILABLE`), A-HB-22 (pure `decide`) and A-HB-25 (recorded suppression). Phase B is the part of this feature that exists for Halbert, and §10.10 is our attempt to give its contract the density Phase A's now has.
3. **HB-D1 → HB-D2** — reactive half only, conversation path, no sensors. First visible product change.
4. **Shadow mode** (§4.6) before any proactive behaviour changes: decide, log, act on nothing, and read the disagreement with `ProactiveGate` over real days.
5. **HB-D3** — the gate becomes an adapter. Subtractive.
6. **HB-D4** steps 1–3 — idle, operation state, occupancy. **F4** ships here.
7. **F1** — the learning loop, once the outcome ledger has run long enough to have evidence.
8. **HB-D5 / F5 / F6** — federation, per-room scope, the held queue.
9. **HB-D4** steps 4–7 — the audio and vision signals, each behind its own setting.

**Explicit dependency on work in flight:** HB-N1 depends on the observation-lenses B4 gate; HB-N3 depends on `C2-08`; HB-N2 discharges part of `C2-10`. None of them depend on attunement being approved.

---

## 10. Open questions for the founder

1. **ATTN-3 vs. the current spine.** `ROADMAP.md` §4 ("Next") is gated on every §3 row being green. Does ATTN-3 sit in §4 behind `ATTN-1` / `STATE-1` / `SHELL-1`, or does HB-N1–N4 — which is mostly work those rows already owe — proceed now as part of them?
2. **Surface taxonomy (HB-N4).** Confirm that "shut up" silences voice and panel auto-open, and never touches the bell count or the findings list.
3. **F1's threshold.** How much evidence before Halbert suggests a dial change — and is a suggestion itself an interruption that has to pass the gate it is about?
4. **Single-body honesty.** Until A-HB-2, do we ship attunement single-body with a stated limitation, or wait for the injectable store?
