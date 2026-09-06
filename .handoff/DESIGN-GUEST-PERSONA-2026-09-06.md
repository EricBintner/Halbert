# DESIGN: Guest Persona — a borrowed face over Halbert's body

**Date:** 2026-09-06
**From:** Design session (founder + Claude), 2026-09-06
**Status:** design only. Nothing here is authorised to be built. Every code
reference below was read during the session and is accurate as of
`fix/observation-text-normalisation`.
**Proposed roadmap row:** `GP-1` (see §11)
**Related:** `.handoff/MULTI-PERSONA-DESIGN-2026-08-29.md` (the persona store this
sits on), `.handoff/PLAN-ATTUNEMENT-HALBERT-2026-09-06.md` (`ATTN-3`; attunement
decides *whether now*, this decides *who is speaking*), `.handoff/HANDOFF-OBSERVATION-LENSES-2026-09-04.md`
(the observation sink private mode must gate)

> Throughout, **H2** is the sibling app. Its real product name is not written in
> this repo.

---

## 1. What this is

A **guest persona** is a persona owned and defined by H2 that fronts on Halbert
for a session: it supplies the name, voice, tone and directives the user hears,
while Halbert keeps running underneath exactly as before — same tools, same
memory, same safety gates, same autonomy, same background observation.

The founder's framing, which this design takes literally:

> Nobody uses a custom persona for IT admin. They use it for home and voice.
> It is fine for the guest to be limited — to say "ask Halbert" for anything
> system-level — while staying in character for "Frigate says the garage door
> is stuck".

Two shapes were considered and one is rejected:

- **Costume (chosen).** Halbert's agent answers every turn. The guest supplies
  the *presentation layer* only. Tools, memory, governance stay Halbert's.
- **Tenant (rejected, out of scope).** H2's agent answers and Halbert is the
  body. That is federation between two entities and puts an outside agent on
  Halbert's tool boundary. Different project; do not let this one drift into it.

**This is not persona import.** The persona never leaves H2's ownership, so
there is no file format, no versioning, no signing, no licensing question, and
no marketplace. A separate design (`chara_card_v3` export, §10) can build on
this later — once the guest object exists, serialising it is nearly free — but
it is not needed for any of the below.

---

## 2. What already exists

Verified during the session. This is why the estimate is a week and not a month.

**Multi-persona is real.** `persona/store.py` keeps each persona as a YAML in
`~/.config/halbert/personas/`, with `being.yml` a symlink to the active one.
Full CRUD and activate at `dashboard/routes/persona.py`; persona cards in
`components/settings/tabs/BeingTab.tsx:57`; activation hot-reloads the prompt
builder.

**Personality is already a swappable object.** `AgentPromptBuilder` holds one
snapshot, `self._being_cfg` (`prompts/agent_prompts.py:397`), refreshed by
`reload_personality()` (`:406`). It feeds
`persona/personality_prompt.py:generate_personality_section`, whose docstring
explicitly accepts *"a BeingConfig instance (or duck-typed object with the same
attributes)"*.

**The name has an override tier.** `identity.py:123 resolve_entity_name` is the
single point every user-facing surface resolves through — `/api/identity`,
`/api/instance/info`, the Presence Pill, MCP `serverInfo`, mDNS — and priority 1
is already an override (`HALBERT_DISPLAY_NAME`).

**Voice is already persona-shaped.** `integrations/modality_wiring.py:156-173`
builds `ModalityAwarePromptBuilder` from a small persona config dict; the engine
resolves voice identity via `PersonaVoiceProfile`.

**Tool scoping exists twice, with the right law.** `tools/role_gate.py` wraps
`ToolSafetyFramework` and *can only tighten, never loosen* (wired at
`tools/executor.py:447` and `dashboard/routes/agent.py:123`).
`federation/tool_allowlist.py` is a frozen allowlist for a restricted caller,
applied at `federation/compute_endpoint.py:191` so **the model never sees the
disallowed tool** — schema-level, not execution-level.

**There is one per-turn choke point.** `tools/executor.py:364 get_schemas()` →
`agents/state_machine.py:1802` → passed as `tools=` at `:1809`.

**Home actions are already governed.** `integrations/home_assistant/autonomy_gate.py`
— four governance levels, per-domain `autonomy_overrides`, proposal-vs-execute.
The guest inherits all of it and needs nothing new.

**The persona/system field split is already ratified.**
`MULTI-PERSONA-DESIGN-2026-08-29.md` §Q2 lists what is "the Character" versus
what is system (`variant`, `ha_url`/`ha_token`, `autonomy_level`, `security.*`).
That list is this design's allowlist; it is not re-litigated here.

**Known adjacent defect, deliberately not touched.** `PersonaManager`'s enum was
never unified with `PersonaStore`, so `/switch` and `/activate` disagree about
the active persona (`PERS-02` / REV-10 F7, open). The guest layer must not
depend on either — see I2.

---

## 3. The override layer

A guest persona is a **process-local, session-scoped object** holding the
persona-scoped subset of `BeingConfig`, installed above the persona store and
never written to it.

```
halbert_core/persona/guest.py

    GuestPersona            # duck-typed BeingConfig subset + provenance
    GuestSession            # id, offered_by, started_at, heartbeat, scopes
    current_guest()         # -> Optional[GuestSession]
    offer(...) / withdraw() # the only mutators
```

Three touch points, all of them existing single resolvers:

| Surface | Where | Change |
|---|---|---|
| Name | `identity.py:123 resolve_entity_name` | new tier above `HALBERT_DISPLAY_NAME` |
| Personality / prompt | `agent_prompts.py:397 self._being_cfg` | resolve through `current_guest()` first |
| Voice | `modality_wiring.py:168` persona config dict | guest supplies the voice profile |

`generate_personality_section` needs **no change at all** — it already takes a
duck-typed object.

Deliberately **not** a write to `being.yml`: the symlink never moves, the
persona store is untouched, and no bug can persist a guest's settings into the
user's own persona. Revocation is dropping the object.

---

## 4. Tool scoping — the guest profile

New: a frozen allowlist mirroring `federation/tool_allowlist.py` field for
field, including the paired denylist for testability and the import-time
self-check.

```
halbert_core/persona/guest_tools.py

    GUEST_ALLOWED_TOOLS: FrozenSet[str] = frozenset({
        "ha_get_entity_state", "ha_call_service",
        "detect_motion", "detect_objects", "detect_faces",
        "read_sensor", "recall_memory",
    })
    GUEST_DENIED_TOOLS: FrozenSet[str]  # run_command, read_file, write_file,
                                        # write_config, terminal_blocks,
                                        # set_autonomy_level, get_being_config, …
    filter_tools_for_guest(names) -> List[str]
```

Applied at `get_schemas()` (`tools/executor.py:364`), so the disallowed tools are
absent from the schema list the model receives. A model that cannot see
`run_command` does not have to be talked out of it.

Note the distinction from `capabilities.py`: that registry answers *what this
body can do*. The guest profile answers *what this caller may ask for*. The
guest mask is a caller-scoped filter over the capability set, never an edit to
it.

**In-character deflection.** With the tools absent, the prompt layer only has to
govern *how* the guest says no, not *whether*. One line in the guest prompt
block — "system-level work is Halbert's side of the house; say so in your own
voice and offer to hand over" — rather than a refusal rule. The failure mode to
write a test for is *narration*: the model saying "I'll check that for you" and
producing nothing, because it cannot tell a removed tool from a broken one.

**Handback must be an action.** "Ask Halbert" is useless if the user has no way
to reach Halbert. Required: the guest emits a handback signal, the override
drops for that turn (or for the session), Halbert answers under his own name,
and the Presence Pill shows the switch. This is the only moment the seam is
visible to the user and it is the piece to design most carefully.

---

## 5. Vision — a named source registry

The founder's decision: the built-in CV stays a core Halbert feature and is not
delegated. A persona does not get *vision*; it gets a **view** — "only the
webcam", "only the patio camera". No frames leave the machine, so there is no
egress path to secure.

**Current state — the halves exist in different places.**

- Local: `vision/config.py` has `webcam.camera_index: int = 0` and
  `screen_capture.monitor_index` — system-level, singular, **unnamed**.
- Frigate: `integrations/frigate/frigate_config.py:39` already has
  `enabled_cameras: list[str]`, `GET /api/frigate/cameras` lists them, and the
  subscriber filters on membership at `frigate_mqtt_subscriber.py:224` and `:248`.
- `config/being_config.py:164 SensesVisionConfig` is already per-persona, but
  carries only enable / proactive / interval / error-patterns. **No source
  selection.**

**Proposed.** One registry of named sources — `screen:1`, `webcam:0`,
`frigate:patio` — giving local capture the naming Frigate already has. Then
`SensesVisionConfig` gains `sources: List[str]`, and the persona mask becomes a
second, narrower filter of exactly the kind the Frigate subscriber already runs.

This is worth building **whether or not guest personas ship**: a named source
registry is the prerequisite for any per-persona, per-room or per-time-of-day
camera policy, and today there is no way to say "the patio camera only".

---

## 6. Memory — two stores, and the line between them

The founder's model: two modes. **Halbert mode** is today's behaviour. **Private
mode** runs the guest against H2's independent memory system and does *not*
write to Halbert's — while Halbert keeps running its own background memory
underneath, ignoring the user unless explicitly invoked or switched back to.

### 6.1 The line, stated plainly

> Halbert stops recording **what you say and what you asked**.
> He keeps recording **what the machine and the house are doing**.

This sentence belongs in the UI, not just in this document. A toggle labelled
"private" with no stated scope is a promise the system cannot keep, because
Halbert has cameras, a microphone and HA sensors that do not stop.

### 6.2 Enforce at the writers, not at the persona layer

Swapping the persona object changes *who speaks*. It changes nothing about who
writes. Private mode is a property of the write path.

The continuity ledger is in unusually good shape for this — there are only
**five** `record_state` call sites:

| Writer | Category | Private mode |
|---|---|---|
| `integrations/state_trackers.py` | the world | keeps writing |
| `config/watcher.py` | the world | keeps writing |
| `agents/threads.py:846` | the conversation | **stops** |
| `continuity/provenance.py` (×2) | derived | follows its source |
| `continuity/consolidation.py` (×2) | derived | follows its source |

So at the ledger, private mode is close to "one writer off, the rest on".

The ledger is not the only store. The audit that this design requires, and does
not yet contain, must enumerate every other writer against the same line —
`agents/conversation_sqlite.py` (threads), the engine's persona memory, the
cognitive tick, the observation sink, `integrations/home_assistant/ha_event_mapper.py`,
`vision/cache.py`, and `audio/storage/speaker_store.py` (voiceprints and
acoustic logs). **That enumeration is the actual work of private mode.** It is
an audit, not a feature.

### 6.3 Three risks

**R1 — Recall asymmetry is the exfiltration shape.** Writes going to H2's store
are fine. The guest *reading* Halbert's memory while writing to a store Halbert
cannot see or erase is a one-way valve out of the user's own machine. This is
structurally identical to finding C4 in `federation/tool_allowlist.py` and needs
gating in the same direction. Stated as an invariant: **the guest may not read
what it may not write** (I6).

**R2 — The wake word is the sharpest honesty question, and the news is good.**
"Halbert ignores you unless invoked" means something must keep listening during
private mode. `audio/speech/wake_word.py` uses openWakeWord — an **acoustic**
model over raw PCM frames, no transcription — so wake detection does not require
transcribing a private conversation. The architecture is already right; the
model is not yet trained ("deferred to a Fable/Colab session"). The invariant to
write down before that changes: **in private mode, wake detection is acoustic
and local; no STT runs and no PCM is buffered beyond the detection window.** If
anyone ever proposes wake-on-transcript, this is the line it breaks.

**R3 — Erasure already has a primitive; use it.** `StateStore.redact_request`
(`continuity/state_store.py:615`) removes everything from one request id, and
`record_state` (`:463`) already carries `source`, `actor`, `request_id`,
`thread_id` and `turn_id`. Tag every private-session turn with a session-scoped
`request_id`, and a *bug* that leaks private content into Halbert's ledger
becomes recoverable in one call instead of permanent. Cheap insurance on exactly
the failure that would matter most.

---

## 7. Session lifetime

- **Offer.** H2 offers a persona over the local channel (§8). Halbert installs
  the override and announces it.
- **Heartbeat.** H2 must keep the session alive. Missed heartbeat → automatic
  revert to Halbert, announced.
- **Withdraw.** Either side can end it. H2 withdrawing, the user ending it from
  the Presence Pill, and the guest's own handback signal all land in the same
  code path.
- **Restart.** A guest session **never** survives a Halbert restart (I3). This
  is a feature: it guarantees a floor state that is always Halbert, and it means
  no failure mode leaves an unattended machine wearing a face nobody chose.
- **Crash of H2.** Same as missed heartbeat.

Open (§12 Q2): whether *private mode* likewise always fails back to Halbert on
restart, or whether ending a private session unannounced is itself a privacy
event worth surviving.

---

## 8. The channel

How H2 hands the persona over. Three candidates, in preference order:

1. **The local MCP surface** (`mcp/server.py`) — two tools, `offer_persona` and
   `withdraw_persona`. Fits the "one MCP surface" direction; inherits the
   existing tool trust boundary and its tiering.
2. **HTTP on the existing pairing machinery** — Linked Devices already issues
   and validates a peer token (`peer_token`, `federation/`). Reuses real auth.
3. A watched file drop. Simplest, weakest; listed only to be rejected.

Whichever is chosen, the offered payload is validated against the §2 persona
field allowlist before it becomes a `GuestPersona`. Fields outside it are
dropped with a logged reason, never merged.

---

## 9. Invariants

These are the spine of the design. Each should have a test that fails if it
stops holding.

- **I1 — Tighten only.** The guest layer may narrow the tool surface, the
  autonomy level, and the vision source set. It may never widen any of them.
  This is `RoleGate`'s existing law applied one level up.
- **I2 — No persistence.** A guest never writes `being.yml`, the personas
  directory, or `PersonaManager` state. The symlink does not move.
- **I3 — No survival.** A guest session does not outlive the Halbert process.
- **I4 — Name transparency.** The user can always tell what is holding the
  tools. Proposed rendering: `Halbert · as ⟨guest⟩`.
- **I5 — Private is a property of writers.** Private mode is enforced at every
  write path, enumerated, not at the persona layer.
- **I6 — Recall symmetry.** The guest may not read what it may not write.
- **I7 — Erasability.** Every private-session turn carries a session-scoped
  `request_id`, so `redact_request` can undo a leak.
- **I8 — Guest text is voice, not authority.** The guest's `directives` and
  `custom_personality_prompt` still land verbatim in the system prompt
  (`personality_prompt.py:96`, first match wins) of an agent that holds tools.
  That text must not be able to widen autonomy, disable a safety rail, or
  override the identity block.

---

## 10. Not in scope

- Tenant mode (H2's agent answering on Halbert's body).
- Persona **import/export** and any portable file format. The engine already has
  a one-way `chara_card_v3` reader (`haloysius/persona/chara_card_v3.py`,
  import only, unused by Halbert); an exporter plus a
  `BeingConfig ⇄ PersonaConfig` mapper would make guest personas persistable.
  Deliberately deferred: it adds format governance, signing, provenance and
  content licensing, none of which a live borrowed face needs.
- Two personas fronting at once.
- Unifying `PersonaManager` with `PersonaStore` (`PERS-02`). Adjacent, still
  open, untouched here by design.
- Any change to what the built-in CV can do. The guest gets a view, not a
  capability.

---

## 11. Phases and effort

| # | Phase | Contents | Effort |
|---|---|---|---|
| 1 | Override layer | `persona/guest.py`; the three touch points; I2/I3 tests | 2–3 d |
| 2 | Guest tool profile | `persona/guest_tools.py`; filter at `get_schemas()`; denylist + self-check, mirroring `tool_allowlist.py` | ~1 d |
| 3 | Channel | MCP `offer_persona` / `withdraw_persona`; payload allowlist validation | ~2 d |
| 4 | Lifetime + handback | heartbeat, revert, handback signal, restart floor | ~2 d |
| 5 | Presence + UI | `Halbert · as ⟨guest⟩`, end-session control, private-mode banner with the §6.1 sentence | ~2 d |
| 6 | Vision source registry | name local sources; `SensesVisionConfig.sources`; persona mask | 2–3 d |
| 7 | **Private mode** | the writer audit (§6.2), the write guard, `request_id` tagging, recall gate | **largest, size after the audit** |

Phases 1–5 are about a week and deliver a working guest persona with Halbert's
memory. Phase 6 stands alone and is worth doing regardless. Phase 7 is the one
that must not be estimated before the audit is written — its cost is however
many writers turn out to sit on the wrong side of the §6.1 line.

Sequencing note: ship 1–5 with private mode **explicitly unavailable in the UI**
rather than half-enforced. A private mode that leaks is worse than no private
mode, because the user changes what they say based on believing it.

---

## 12. Open questions

**Q1 — May the guest read Halbert's memory at all?** §6.3 R1 argues no by
default. A softer option is a read allowlist (household facts yes, conversation
history no), which is more useful and considerably harder to bound. Needs a
decision before Phase 7.

**Q2 — Does private mode survive a restart?** I3 says the *guest* does not.
Whether *private mode* does is a separate call: failing back to Halbert is the
safe default, but a user who left a private conversation open may reasonably
expect it not to silently become recorded.

**Q3 — What does Halbert do while ignored?** `proactivity`, `quiet_hours` and
`morning_report` are persona-scoped. If the guest is fronting at 08:00, does the
morning report fire, and in whose voice? Proposal: Halbert's scheduled speech is
suppressed while a guest fronts, except life-safety
(`modality_wiring.is_life_safety_event`), which always speaks as Halbert.

**Q4 — Confirmed:** the Presence Pill shows both names (I4). Flagged here only
because it touches the ratified "engaged surface carries the onboarding
`ai_name`" directive, and this is a documented exception to it.

---

## 13. Proposed roadmap row

| Row | Statement | Notes |
|---|---|---|
| `GP-1` | A persona defined in H2 can front on Halbert for a session — its name, voice and manner — while Halbert keeps his tools, memory, governance and background observation; the user can always tell who holds the tools, and can hand back in one action | Phases 1–5. Private mode (§6) is **not** part of this row and gets its own once the writer audit exists. Depends on nothing. `ATTN-3` (attunement) and the observation-lenses work both edit the same prompt-assembly path, so if either is in flight it should land first to avoid a three-way conflict there. |

---

## 14. Key files

| File | Role |
|---|---|
| `persona/store.py` | persona files + `being.yml` symlink — untouched by I2 |
| `persona/personality_prompt.py:70` | takes a duck-typed config; the guest slots straight in |
| `prompts/agent_prompts.py:397` | `self._being_cfg` — touch point 2 |
| `identity.py:123` | `resolve_entity_name` — touch point 1 |
| `integrations/modality_wiring.py:168` | voice persona config — touch point 3 |
| `tools/executor.py:364` | `get_schemas()` — where the guest tool mask applies |
| `tools/role_gate.py` | the tighten-only law to mirror |
| `federation/tool_allowlist.py` | the frozen-allowlist pattern to copy wholesale |
| `integrations/home_assistant/autonomy_gate.py` | home governance the guest inherits unchanged |
| `vision/config.py`, `integrations/frigate/frigate_config.py:39` | the two halves of the source registry |
| `continuity/state_store.py:463`, `:615` | `record_state` provenance fields; `redact_request` |
| `audio/speech/wake_word.py` | acoustic, local wake detection — the R2 invariant |

---

## 15. Build notes — what landed on `feat/guest-persona` (2026-09-06)

The founder authorised building the complex parts; the rest is fill-in work
for other sessions. Every claim below was verified against the code on
`main` at `3efd3145`, and every module has tests that failed before it
existed.

### 15.1 Where the design and the code disagreed

Read these before doing the fill-in phases; two of them change §8 and §4.

1. **The MCP surface is the wrong process (§8 option 1 is out).**
   `mcp/server.py` is a standalone stdio/HTTP process (`halbert-mcp-serve`);
   nothing in the dashboard imports it, and its own docstring says its
   singletons are "only as full as this process made it". A process-local
   guest offered over MCP would be installed where no agent reads it.
   **Built:** option 2 — HTTP in the dashboard process on the pairing token
   (`dashboard/routes/guest.py`). Do not add `offer_persona` to the MCP
   tool table.
2. **Schema-level masking is necessary, not sufficient (§4).** The peer
   pattern hides tools from a prompt that never saw them. A guest inherits a
   conversation whose history holds Halbert's own `run_command` calls, and a
   model imitates calls it was not offered. **Built:** the mask at
   `get_schemas()` *and* a default-deny at `execute()`; a hidden tool named
   anyway is refused and audited, never run
   (`test_guest_tools.py::TestExecuteWhileAGuestFronts`).
3. **`read_sensor` does not exist.** The §4 allowlist named
   `detect_motion`/`detect_objects`/`detect_faces` (real, `vision_tools.py`,
   registered only when webcam or screen capture is enabled) and
   `read_sensor` (not registered anywhere). **Built:** the allowlist is
   pinned to the live registry by two tests — every allowlisted name must
   be a registered tool, and every registered tool must be on one list or
   the other. Adding an agent tool now fails a test until someone decides.
4. **The name tier must not go into `resolve_entity_name` (§3 table, row 1).**
   That resolver also feeds mDNS (`peer_discovery.py:299`) and MCP
   `serverInfo`; a costume must not rename the node to its peers.
   **Built:** `display_name` stays the machine's; `/api/instance/info` and
   `GET /api/guest` carry a `fronting` object with the guest's name, so the
   pill renders both (I4). The prompt uses the guest name via the builder.
5. **Touch point 3 is dead code.** `modality_wiring.get_modality_prompt_builder`
   has no callers and hardcodes `{"name": "Halbert"}` — it does not read
   being.yml even for Halbert. **Not built.** Wiring the voice persona is a
   separate defect; when it is fixed, read `current_guest()` there too.
6. **No overlay object.** `_embodiment_lines` reads system fields from the
   same snapshot as the persona fields, so a bare duck-typed guest would
   silently lose the body lines. Rather than layer objects, the builder
   renders a *different block* for a guest: guest identity → guest manner →
   boundaries. The machine's embodiment lines are not the guest's to claim.
7. **The accepted field set is narrower than §2's list, on purpose.**
   `GUEST_PERSONA_FIELDS` excludes `voice` (a guest is not the machine and
   never uses "the_computer"), `model`/`model_endpoint_id` (compute is not
   a face), `persona_id_override` (the memory namespace — private mode is
   a writer property, §6), `senses` (vision consent — Phase 6 narrows,
   never widens), and the scheduled-speech fields (Q3, undecided). A test
   asserts the set is a strict subset of the ratified list.
8. **"guest" already means something.** `role_gate.py` has
   `speaker_role="guest"` (who is *talking*). The guest persona is who is
   speaking *for* the machine. Nothing here touches `speaker_role`; do not
   pass "guest" as one.
9. **Handback inside a turn is bounded by the tool list.** `get_schemas()`
   is read once per turn, in PLANNING; RESPONDING has no tools. So the
   handback tool ends the session mid-turn, the identity block is re-rendered
   for RESPONDING (Halbert answers under his own name), and the full tools
   return on the *next* turn. The tool result tells the model exactly that.
10. **No timer.** Expiry is evaluated on every `current_guest()` read;
    nothing keeps a heartbeat thread alive, and the ending is announced once
    by whichever caller notices. Restart floor (I3) is automatic: the session
    is a module-level object with no load path.

### 15.2 What is built

| Design | Module | Tests |
|---|---|---|
| §3 override layer, §7 lifetime, I1/I2/I3/I8 | `persona/guest.py` — `GuestPersona.from_payload` (allowlist + caps), `GuestSession`, `current_guest`, `offer`, `heartbeat`, `withdraw`, `handback`, `on_session_end` | `tests/test_guest_persona.py` (24) |
| §4 tool profile + handback as an action | `persona/guest_tools.py`; `tools/executor.py` (`get_schemas`, `execute`, `_hand_back`) | `tests/test_guest_tools.py` (19) |
| §4 deflection, I4, I8 in the prompt | `prompts/agent_prompts.py` (`_GUEST_IDENTITY`, `_GUEST_BOUNDARIES`, `build_identity_block`, `_get_identity`) | `tests/test_guest_prompt.py` (9) |
| §8 channel, §7 announce, I4 payload | `dashboard/routes/guest.py`; `routes/instance.py` (`fronting`); `proactive/events.py` (`guest_session` is user-facing); `app.py` | `tests/test_guest_routes.py` (17) |

### 15.3 The contract for the fill-in work

**The app's side (H2), bearer = pairing token:**

```
POST /api/guest/offer      {"persona": {...GUEST_PERSONA_FIELDS...}, "ttl_seconds": 60}
                           → 200 {"status","session":{session_id,name,offered_by,offered_by_name,
                                  started_at,seconds_until_expiry,active,end_reason},"dropped":[...]}
                           → 400 bad persona · 401 no token · 409 another peer's session is live
POST /api/guest/heartbeat  {"session_id"}   → 200 · 404 unknown · 403 not yours
POST /api/guest/withdraw                    → 200 {"status":"ok"|"idle", "session"}
```

**The user's side (local only):** `POST /api/guest/end`; status for anyone:
`GET /api/guest` → `{"fronting": session|null}`; `/api/instance/info` carries
the same `fronting` object.

**Events:** type `guest_session`, severity `info`, `data.state` =
`"fronting"` | `"ended"`, `data.reason` on endings = `withdrawn` |
`handback` | `ended_by_user` | `heartbeat_missed` | `replaced`.

### 15.4 Left for others, in order

- ~~**Phase 5 UI.**~~ Done — §15.5.
- ~~**Q3.**~~ Answered and built — §15.5.
- **Touch point 3** (15.1 item 5) once the voice builder has a caller.
  Still blocked: `modality_wiring.get_modality_prompt_builder` has no
  callers and does not read being.yml even for Halbert. Wiring the voice
  persona is its own defect; fixing it is where `current_guest()` goes.
- **Phase 6** vision source registry — specified and ready to build:
  `.handoff/DESIGN-VISION-SOURCE-REGISTRY-2026-09-06.md` (row `VIS-1`). It
  found one thing §5 did not: the configured camera index is a *default*,
  not a bound — `vision_tools.py:137` reads it from tool args — so scoping
  built on the current shape would be decorative.
- **Phase 7** private mode — first pass of the §6.2 writer audit is written:
  `.handoff/REVIEW-PRIVATE-MODE-2026-09-06.md`. **Still not implementable.**
  The ledger split is cleaner than expected (five writers, falling almost
  exactly along the §6.1 line), but `obs/audit.py` — which §6.2 did not list
  — is a hash-chained log carrying user-derived text, so I7 (erasability)
  and its integrity guarantee are in direct conflict. Resolving that is an
  `EventLog` change in Haloysius. Three founder decisions are open there
  too.

---

## 15.5 Phase 5 and Q3 — the second pass (2026-09-06)

Built on the same branch, after §15.1–15.4. Full frontend suite green (106
files, 976 tests); backend `-k "guest or proactive or gate or persona or
morning or detector or watcher or instance"` green (676).

### The pill wears both names

`PresencePill.tsx` reads `fronting` off `/api/instance/info` (the object
§15.1 item 4 put there) and renders `⟨entity⟩ · as ⟨guest⟩` — never the
guest alone, which is I4 and is the assertion the first new test makes. The
body name moves into the dropdown while a guest fronts so the two names fit;
the dropdown gains a "Guest persona" section naming who lent the face, one
line saying the machine is underneath with its own tools and rules, and an
**End guest session** button posting `/api/guest/end`.

The end control renders only on the local body. `/api/guest/end` is
`require_local_admin` by design (§8), so offering it against a paired remote
would be a button that always fails.

**The pill polls, and that is load-bearing.** `current_guest()` evaluates
expiry lazily, on the read (§15.1 item 10) — so something has to read, or a
lapsed session stays on the face and its ending is never announced. A
10-second poll of the info endpoint makes the pill that reader. It is not
only a refresh: it is what notices `heartbeat_missed`.

### Q3: Halbert keeps watching, and does not interrupt

Answered in `proactive/gate.py::_guest_suppresses`, consulted first in
`should_notify`. While a guest fronts, Halbert's proactive events do not
push at the user.

Nothing is lost by this. `detector_runner` writes the finding to the store
*before* it consults the gate (`detector_runner.py:155`), so suppression
means "does not interrupt", never "was not noticed" — which is exactly the
background-observation half of §1.

Four things still pass, and one of them is wider than §12 Q3 proposed:

| Passes | Why |
|---|---|
| `guest_session` | how the user learns the face went on or came off (I4) |
| life safety | the exception Q3 names |
| confirmed acoustic anomaly | this gate already treats those as life safety |
| **`critical`** | **wider than Q3's "life-safety only"** |

The widening is deliberate and is the one call here a founder should
confirm or reverse. The gate's own precedent is that quiet hours never
suppress a critical event (step 2 skips `severity == "critical"`), and a
costume is a presentation choice, not a safety one: letting a failing disk
go unmentioned because a guest is speaking would be a new behaviour, and a
worse one than the suppression quiet hours already declines to do. It is a
single condition in `_guest_suppresses` if the answer is no.

The guest lookup fails open — a raise there must not silence Halbert, and a
test asserts it.

### Collateral, and why it was necessary

`guest_session` events carry a session in `data`, where acoustic findings
carry `AcousticAnomalyData`. Widening that field to a union made the two
existing readers type-errors, which is the union doing its job: both were
reading `data.anomaly_severity` and `data.sound_class` off a value that is
no longer always acoustic. Both now narrow through a new
`acousticData(event)` accessor, symmetric with `guestSessionData(event)`.
`VoiceMode.test.tsx` mocks that module and re-implements its predicates
deliberately, so the mock gained the new one — inside the factory, since
`vi.mock` is hoisted.

### Not done, deliberately

Private mode remains **absent from the UI**, per the §11 sequencing note. No
toggle exists, nothing claims it, and the §6.2 writer audit is still
unwritten.
