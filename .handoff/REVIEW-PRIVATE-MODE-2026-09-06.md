# REVIEW: Private mode — the writer audit, and the one thing that cannot forget

**Date:** 2026-09-06
**Status:** **review only. Not implementable.** Three decisions (§5) and one
engine-level change in Haloysius (§4) block a spec, let alone code. Private
mode stays absent from the UI meanwhile — see §7.
**Parent:** `.handoff/DESIGN-GUEST-PERSONA-2026-09-06.md` §6 and §11 phase 7.
That document says the writer audit must be written before Phase 7 is
sized. This is the first pass of it.
**For review by:** the founder (§5 is three product calls), and Haloysius
(§4 is theirs).

---

## 1. The shape being reviewed

Founder's model, from the 2026-09-06 session:

> Two modes. One is Halbert. The second is private: the guest runs against
> H2's own independent memory and does **not** write to Halbert's — but
> Halbert keeps running his own background memory underneath, ignoring the
> user unless they invoke him or switch back.

The design's line, which the UI has to state and not just imply:

> Halbert stops recording **what you say and what you asked**.
> He keeps recording **what the machine and the house are doing**.

This document asks one question of the code: **which writers sit on which
side, and can the ones that must stop actually be stopped.**

---

## 2. The writer audit, first pass

Every row was read. "Stops" means the writer must not run for a private
turn; "keeps" means it runs unchanged; "derived" means it follows whatever
produced its input.

### 2.1 The world — keeps writing

| Writer | Records |
|---|---|
| `integrations/state_trackers.py` → ledger | disk, services, host state |
| `config/watcher.py` → ledger | config file changes |
| `findings/store.py` | machine problems |
| `model/outcome_store.py` | model-call telemetry (no content) |
| `continuity/timeline.py` ← `system_event_mapper.py:102`, `ha_event_mapper.py:218,246`, `frigate_event_mapper.py:267` | HA state changes, Frigate events, discoveries |
| `home/behavior.py` | routines inferred from the timeline |

### 2.2 The conversation — must stop

| Writer | Records |
|---|---|
| `agents/conversation_sqlite.py:813 append_message` | the sole message write path |
| `agents/threads.py:846` → ledger | thread-close receipts, including the commands run during the thread |
| the cognitive tick — `integrations/cognition_wiring.py:378 tick(cognition, user_message, assistant_response)` | feeds the engine's emotional state, beliefs and thoughts **from the user's message** |
| `obs/audit.py write_audit(reason=…)` | see §4 — this is the blocker |

### 2.3 Derived, or not yet wired — verify before relying on the row

| Writer | Note |
|---|---|
| `continuity/provenance.py`, `continuity/consolidation.py` | derive from whatever produced them; follow their source |
| `somatic/store.py` | self-management cycles; holds ids only, models stay in `findings/`/`approval/`. Wired into `state_machine` but optional (`None` = no-ops) |
| `vision/cache.py` | anomaly screenshots on disk; episodic memory stores the URI, not the image. Its retention is 7-day TTL / 500MB — not a privacy control |
| `audio/storage/speaker_store.py` | one table, `speaker_profiles`. **No production caller today** (`SpeakerStore(` and `update_centroid` have none outside the module). The adaptive `update_centroid` path would refine a voiceprint from whatever speech reaches it — put it on this list *before* it is wired, not after |

### 2.4 What the audit changed about the design's estimate

Better than feared for the ledger — only five `record_state` call sites,
and the split falls almost exactly along §6.1's line. Worse than feared for
`obs/audit.py`, which the design did not list at all.

---

## 3. Two things the audit surfaced that the design did not say

### 3.1 The timeline records occupancy

`continuity/timeline.py` is world-side by the letter of §6.1: HA state
changes, Frigate events. But a Frigate person-detection and an HA motion
sensor, during a private evening, are a record of **who was in the room and
when**. The user's presence is not their conversation, and it is also not
"what the machine is doing".

Either the line gets stated more precisely than §6.1 does, or this is
accepted and said plainly in the UI. What is not acceptable is the current
position, where the sentence implies one thing and the timeline does
another.

### 3.2 A local namespace is a trap that looks like the feature

`PersonaMemoryStore(persona_id)` is namespaced per persona
(`dashboard/routes/memory.py:229`). So "the guest has its own memory" can be
faked in an afternoon by pointing it at a different namespace. It would look
identical to the user, cost nothing, and keep every word on Halbert's disk —
the opposite of what was asked for.

This is why `persona_id_override` is excluded from `GUEST_PERSONA_FIELDS`
(guest-persona §15.1 item 7). Recording it here because the shortcut is
attractive, invisible in review, and would be discovered only by someone
looking for it.

---

## 4. The blocker: the audit log cannot forget, by design

`obs/audit.py` is a tamper-evident, hash-chained log backed by
`haloysius.integrity.EventLog`. Its `write_audit` signature documents
`reason` as:

> why this happened — a human utterance from the causing turn, a
> deterministic rule that names itself, or `state_store.UNRECORDED`

In practice the model supplies it per tool call
(`tools/executor.py:935` — `args.get("reason")`, defaulting to
`UNRECORDED`), so it is user-derived text: a paraphrase of what the person
asked for.

Consequences:

- A private-mode turn that runs **any** tool writes user-derived text into
  an append-only chain.
- `StateStore.redact_request` (`continuity/state_store.py:615`) — the
  erasure primitive the design leans on (I7) — has **no counterpart here.**
  Being unerasable is the entire purpose of a hash chain.

So the erasability invariant and the integrity guarantee are in direct
conflict, and no amount of care at the persona layer resolves it.

**Three ways out. All are real; (c) is right and is not ours alone.**

**(a) Private turns get no tools.** Simple, provable, and a large
functional cut — a private conversation cannot check the door, look at a
camera, or answer anything about the house. Probably unacceptable given
private mode is a *home and voice* feature.

**(b) Private turns audit with a placeholder reason.** The record of *what
ran* survives; the record of *why* is permanently `UNRECORDED`. That
weakens the audit log's own guarantee in exactly the cases most likely to
need explaining later, and the audit docstring's warning against a
generated rationale ("a plausible invented reason is unfalsifiable")
applies doubly to a blank one.

**(c) Two-tier: the chain covers a digest; content lives beside it.**
Content can be dropped without breaking verification — the chain still
proves the sequence, and a redacted entry is visibly redacted rather than
missing. This is the right answer and it is an **engine-level change**:
`EventLog` is Haloysius, shared by all three consumers, so it needs their
review and their timeline, not ours.

**Ask of Haloysius:** is a redactable-content tier on `EventLog` something
you would take? If not, Halbert's private mode is choosing between (a) and
(b), and we would rather you told us that now than after we specified (c).

---

## 5. Decisions that block a spec

**Q1 — may the guest read Halbert's memory?**
Writes going to H2 is settled. Reads are not. A guest that reads Halbert's
conversation memory while writing to a store Halbert cannot see or erase is
a one-way valve out of the user's own machine — structurally identical to
finding C4 in `federation/tool_allowlist.py`.
*Recommendation:* **no** in v1 — no read of Halbert's conversation memory
or ledger. Household facts (who lives here, what the rooms are called) via
an explicit read allowlist is a later, separately-reviewed feature, not a
v1 convenience.

**Q2 — does private mode survive a restart?**
The guest session does not (I3, and it has no load path). Private mode is a
separate call.
*Recommendation:* **no** — fail back to Halbert *and* end private mode,
announced. A private session that silently resumes recording after a crash
is the worst available outcome; being dropped back to Halbert is merely
annoying.

**Q3 — the audit log.** (a), (b) or (c) from §4. Blocked on Haloysius for
(c).

---

## 6. Requirements, once those are answered

- **P1 — one switch, read lazily.** A session-scoped `PrivacyMode`, read
  the way `current_guest()` is: no timer, evaluated on the read, no load
  path across a restart (per Q2).
- **P2 — one guard, not a flag each store interprets.** Every writer
  consults `may_record(kind, actor)`. The reasoning lives in one file and
  is reviewable in one place.
- **P3 — an unlisted writer refuses.** During private mode, a writer not on
  the classification list fails **closed**. A store added next year cannot
  silently leak; it announces itself by not working until someone classifies
  it. Pinned by a test that enumerates writers, the way
  `test_guest_tools.py` pins the tool registry against the live tool list.
- **P4 — the wake path stays acoustic.** `audio/speech/wake_word.py` uses
  openWakeWord — an acoustic model over raw PCM, no transcription — so
  "Halbert still listens for his name" does not require transcribing a
  private conversation. The model is not yet trained ("deferred to a
  Fable/Colab session"), so write the invariant down before it is: **in
  private mode, wake detection is acoustic and local; no STT runs and no
  PCM is buffered beyond the detection window.** If anyone proposes
  wake-on-transcript, this is the line it breaks.
- **P5 — every private turn carries a session-scoped `request_id`**, so a
  bug that leaks into the ledger is recoverable via `redact_request` rather
  than permanent (I7).
- **P6 — the UI states the line.** §1's two sentences, in the interface, at
  the moment private mode is switched on. Not a toggle with a one-word
  label.

---

## 7. What holds until this is answered

Private mode stays **absent from the UI**. No toggle exists, nothing claims
it, and the guest persona ships without it (guest-persona §11 sequencing
note, §15.5).

The reason is worth restating because it is the whole argument for not
shipping a partial version: **a private mode that leaks is worse than no
private mode**, because the user changes what they say in front of it.

---

## 8. Key files

| File | Role |
|---|---|
| `continuity/state_store.py:463,615` | `record_state` provenance fields; `redact_request`, the erasure primitive |
| `agents/conversation_sqlite.py:813` | the sole message write path |
| `agents/threads.py:846` | thread-close receipts into the ledger |
| `integrations/cognition_wiring.py:378` | the tick, fed the user's message |
| `obs/audit.py:212` | `write_audit` — §4, the blocker |
| `tools/executor.py:935` | where the audit `reason` comes from |
| `continuity/timeline.py` + the three event mappers | the world, and the occupancy question (§3.1) |
| `dashboard/routes/memory.py:229` | `PersonaMemoryStore(persona_id)` — the trap in §3.2 |
| `audio/speech/wake_word.py` | acoustic, local — the P4 invariant |
| `audio/storage/speaker_store.py` | voiceprints; unwired today, classify before wiring |
