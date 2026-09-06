# DESIGN: Persona layers over a solid core — the memory divide, private sources, and the pull channel

**Date:** 2026-09-06
**From:** founder thinking session + review of the day's other sessions
**Status:** proposal. Nothing here is authorised to be built. It reframes
private mode (`REVIEW-PRIVATE-MODE-2026-09-06.md`) and extends the guest
persona (`DESIGN-GUEST-PERSONA-2026-09-06.md`, built through §15.5) with
what the founder asked for on the second pass: a divide between the
machine's memory and a guest persona's memory in **every** mode, private
mode as a matter of **which sources** the guest is handed, and a way for
the user to ask Halbert to wear a sibling's persona rather than wait to be
offered one.
**Sibling naming:** H2 is the companion-persona app; H3 is the
historical-minds app. Their real names are not written in this repo.

---

## 1. What changed since the design was written

Findings from the other sessions of 2026-09-06, all verified in code:

1. **Guest persona phases 1–5 and Q3 are built** (`feat/guest-persona`).
   The pill wears both names; while a guest fronts Halbert keeps noticing
   and stops interrupting, except life safety, a confirmed acoustic
   anomaly, critical, and the guest-session announcements.
2. **The camera index is a default, not a bound.** `vision_tools.py:137`
   reads the camera out of the model's arguments. Any per-persona vision
   scoping built on today's shape is decorative
   (`DESIGN-VISION-SOURCE-REGISTRY-2026-09-06.md` §3). The registry is the
   prerequisite for private sources (§5 below).
3. **The private-mode writer audit split cleanly** — five `record_state`
   sites along the world/conversation line — but named `obs/audit.py` as a
   blocker: a hash chain carrying user-derived `reason` text. §6 below
   shows that for *guest* turns the chain never receives that text, by
   construction, so the engine change the review asked for is not needed
   for v1.
4. **The timeline records occupancy** (Frigate person detections, HA
   motion). Presence is neither "the conversation" nor "what the machine
   is doing". §5 treats presence as belonging to a *source*, which is the
   unit the founder wants to hand over anyway.
5. **`PersonaMemoryStore(persona_id)` is a trap.** A local namespace looks
   like "the guest's own memory" and keeps every word on Halbert's disk.
   §4 routes the guest's words to the guest's home instead.
6. **The cognitive tick feeds Halbert's own psyche with the user's words.**
   `state_machine.py:2897 _run_cognition_tick` runs `advance_turn` against
   `get_cognition()` — `PersonaCognition(persona_id=<Halbert's id>)` — with
   `memory_store_add` bound to Halbert's `PersonaMemoryStore`. Nothing on
   the guest branch stops this, so today a guest conversation lands in
   Halbert's emotional state, beliefs and semantic memory. This is the
   reverse of the leak the founder named, and it is real now.
7. **Both siblings expose the same persona shape and a per-persona memory
   API.** They share the engine's `PersonaConfig` lineage (name, traits,
   communication_style, quirks, personality_profile, archetype_id,
   directives, speech_patterns, background, context). H2 serves
   `GET /personas`, `GET /personas/<id>`, `POST /personas/<id>/memories/search`,
   and `memory-v2/memories` `GET`/`POST`/`DELETE` (content ≤ 2000 chars,
   type, emotional weight/valence, tags). H3 serves the persona routes and
   `memories/search`. So the guest's memory can live at the guest's home
   through an API that already exists, and Halbert can *fetch* a persona
   rather than only be offered one.

---

## 2. The founder's model, as three rules

> Halbert facilitates the tools. Another AI persona appears to be the
> voice, the eyes and the ears. Background work — cameras, sounds, disks —
> continues regardless. The machine's memories never go into the guest
> persona; in private mode the user picks what the guest sees instead of
> Halbert.

- **R1 — The core never stops.** World writers, findings, the proactive
  gate, safety, the autonomy gate, the wake word. No mode routes these
  away from Halbert. (Built: Q3 makes them quiet, not blind.)
- **R2 — Ownership is by actor, in every mode.** What the machine and the
  house do belongs to Halbert. What was said to a guest belongs to the
  guest, at the guest's home. The two never cross. Private mode does not
  create this divide; it already has to exist the moment a guest fronts.
- **R3 — Private mode is a set of sources handed to the guest.** The user
  names sources (this webcam, this microphone, that camera). For the
  session, those sources are the guest's: their observations do not enter
  Halbert's stores, and Halbert stops recording the conversation. Nothing
  else changes.

---

## 3. The layers

| Layer | Owns | State today |
|---|---|---|
| 0 Core | body, tools, world memory, findings, safety, wake word | built |
| 1 Face | name, manner, tool mask, handback, pill, quiet | built (§15) |
| 2 Ownership | one function every conversation writer and the tick consult | **new** (§4) |
| 3 Private sources | session-scoped source → owner map; sensor pipelines consult it | **new** (§5), after VIS-1 |
| Pull channel | "Halbert, be Marnie" fetches the persona from a sibling | **new** (§7) |

Each layer narrows; none widens. Layer 3 depends on layer 2 and on the
vision source registry. Nothing depends on an engine change.

---

## 4. Layer 2 — the memory divide

### 4.1 One function

```
halbert_core/continuity/ownership.py

    class Owner(Enum): HALBERT | GUEST | DROP

    route_write(kind: str, *, actor: str, source: str = "") -> Owner
```

`kind` names the writer (`"conversation.message"`, `"conversation.receipt"`,
`"cognition.tick"`, `"observation"`, `"world"`). `actor` is
`ACTOR_USER`/`ACTOR_AGENT`/`ACTOR_SYSTEM` or `guest:<session_id>`.
`source` is a registry id (§5) for observations. The reasoning lives in one
file; a writer not on its list **fails closed while a guest fronts** — the
review's P3, applied from the first day rather than to private mode alone.

### 4.2 The table

| Writer | No guest | Guest, normal | Guest, private |
|---|---|---|---|
| world: `state_trackers`, `config/watcher`, `findings/store`, `outcome_store`, `timeline` (system + HA mappers), `home/behavior` | HALBERT | HALBERT | HALBERT |
| `conversation_sqlite.append_message` | HALBERT | HALBERT, `metadata.actor = guest:<id>`, session `request_id` | GUEST |
| `threads.py` close receipts → ledger | HALBERT | HALBERT, actor `guest:<id>`, session `request_id` | DROP |
| `_run_cognition_tick` → Halbert's cognition + `PersonaMemoryStore` | HALBERT | **GUEST** | GUEST |
| `provenance`, `consolidation` | follow their source | follow their source | follow their source |
| observations from a source (§5) | HALBERT | HALBERT | by source owner |

Two things this table fixes that are not fixed today:

- **The tick.** While a guest fronts, `advance_turn` must not run against
  Halbert's `PersonaCognition`. The turn (user message, reply) is forwarded
  to the guest's home as a memory (`memory-v2/memories` POST, tagged with
  the session id), and the home runs whatever tick it wants — it is the
  same engine. Halbert's psyche does not learn the guest's evenings; the
  guest's persona does not learn Halbert's disks. That is R2, and it holds
  in *normal* mode, which is the founder's second-pass point.
- **Erasability in normal mode.** Every guest-session write into Halbert's
  own stores carries the session's `request_id`, so `redact_request`
  removes the words of a whole session in one call. Normal mode is
  "Halbert remembers this happened, tagged and erasable", not "Halbert
  remembers nothing".

### 4.3 "GUEST" means the guest's home, never a local namespace

The destination for `GUEST` is the sibling's per-persona memory API, over
the pairing token, using the session's `offered_by`. If the home is
unreachable the write **fails closed** and the turn is told so (the guest
says it will not remember this) — never a silent local spool. A spool that
flushes later is a v2 question; a spool that stays is the trap in §1.5.

What the guest reads is what it wrote (I6): a guest-scoped
`recall_guest_memory` tool that calls the home's `memories/search`, and no
read of Halbert's conversation memory or ledger (`recall_memory` leaves the
guest allowlist; the review's Q1 answered **no**). Household facts via a
read allowlist remain a later feature.

---

## 5. Layer 3 — private sources

### 5.1 The unit is a source, and the registry names it

VIS-1 gives local vision the ids Frigate already has: `webcam:0`,
`screen:1`, `frigate:patio`. Audio events already carry `source` and
`area_id` (`audio/pipeline.py`), and the ingress adapters are enumerable
(local mic by device index, Wyoming satellites, RTSP, WebRTC), so the same
registry can name microphones: `mic:local:0`, `mic:wyoming:<satellite>`.
"Browser history" is not a sense Halbert has today — there is no reader —
so it is not a source yet; the registry is where it would be added.

### 5.2 One session-scoped map

```
halbert_core/persona/private_sources.py

    assign(source_id, Owner.GUEST)      # the user's action, from the pill
    owner_of(source_id) -> Owner        # HALBERT by default
    active() -> bool                    # any source assigned = private mode is on
```

Read lazily, like `current_guest()`; no load path; ends with the guest
session (I3) — and with it private mode, announced. That answers the
review's Q2 the safe way: a private session that silently resumes recording
after a crash is the worst outcome, so it does not resume at all.

### 5.3 Where the gate sits

At the *output* of each sensor pipeline, before findings, timeline, event
bus or ledger: `vision/watcher.py:218` (findings), `zone_watcher`,
`ambient_webcam`, the acoustic path in `audio/pipeline.py`, and the
Frigate mapper (`frigate_event_mapper.py:267`, which already has the
camera name). Detection still *runs* — the guest is meant to see through
the source — but the result routes by `owner_of(source)`: HALBERT as
today; GUEST forwarded to the guest's home (or to the guest turn as
context) and not written to Halbert's stores.

This is also the answer to the occupancy finding (§1.4): a person detected
on a private camera is the guest's to know. On a source the user did not
hand over, presence stays Halbert's, and the UI says so at the moment
private mode is switched on (the review's P6, restated by source rather
than by sentence).

### 5.4 The exception

Life safety on a private source (smoke, a fall, a confirmed acoustic
anomaly) is the one place privacy and safety collide. Q3 already lets
life safety through a guest's quiet. **Decision D1 (§10)**: does it also
cross a private source? Recommendation: yes, to Halbert, announced —
because the house is not private from its own smoke alarm.

---

## 6. The audit chain is not a blocker for guest turns

The review's §4 assumed every tool call writes user-derived text into the
hash chain. It does not:

- The agent's `ToolExecutor` has **no `audit_fn`** (`routes/agent.py:127`),
  so `_audit` is a no-op for ordinary tool calls.
- `write_audit` callers with a model-supplied `reason` are the config
  write plane: `tools/write_config.py`, `tools/schedule_cron.py`,
  `tools/base.py`, and `provenance.py` behind `write_file`
  (`executor.py:935`). **Every one is denied to a guest.**
- The other callers write deterministic summaries: `autonomy/guardrails.py`
  (confidence, budgets, safe mode), `autonomy/recovery.py`,
  `findings/proposal_generator.py`, `persona/manager.py`,
  `persona/memory_purge.py`. `ha_call_service` passes the `AutonomyGate`,
  which does not write the chain at all.

So a guest turn — normal or private — puts no user words into the chain
**as long as the write plane never enters the guest allowlist.** Pin it:

```
WRITE_PLANE_TOOLS = {"run_command", "write_file", "write_config",
                     "schedule_cron", "terminal_blocks"}
assert not GUEST_ALLOWED_TOOLS & WRITE_PLANE_TOOLS
```

next to the two registry tests in `test_guest_tools.py`. The engine-level
redactable tier on `EventLog` stays worth asking Haloysius for, but for a
different feature: Halbert's *own* private hour, with no guest and full
tools. That is v2 and is not what the founder described.

---

## 7. The pull channel — "Halbert, be Marnie"

The built channel is push: a sibling offers over `/api/guest/offer`. The
founder wants the user to ask Halbert. Both siblings serve `GET /personas`
and `GET /personas/<id>` in the engine's `PersonaConfig` shape, so:

```
halbert_core/persona/sibling.py

    list_personas(peer) -> [ {id, name, summary} ]      # GET /personas
    fetch_persona(peer, id) -> GuestPersona payload     # GET /personas/<id> → map
    memory_add(peer, id, content, tags) / memory_search(peer, id, q)
```

`peer` is a paired peer from `PeersConfig` whose role says it is a persona
home and whose record carries its base URL. The mapping to
`GUEST_PERSONA_FIELDS`: `traits` → `tone_descriptors`,
`communication_style` + `quirks` → `speech_patterns`, `background` +
`context` → `scene_context`, `directives`, `speech_patterns`,
`personality_profile`, `archetype_id` as-is; everything else dropped and
reported, exactly as `from_payload` does today. Then `guest.offer(...)`
with `offered_by = peer.node_id` — the same session, the same lifetime,
the same pill. Heartbeat becomes Halbert's own liveness check against the
home (a failed `memories/search` ping ends the session), since nobody on
the other side is beating.

The user-facing verb is one chat command or one pill action: "be
⟨name⟩" lists matches across paired homes and installs the one chosen.
Guest text stays voice, not authority (I8): the persona was chosen by the
user, but it was *written* by the sibling's builder, so the caps apply
unchanged.

---

## 8. The H3 experiment

H3's personas fit the same adapter, so wearing one costs nothing extra.
What H3 has that H2 does not is grounding: `memories/search` over a
figure's writings. The interesting experiment is not the face, it is
**a guest that brings one read-only tool from home** — `recall_guest_memory`
bound to H3's search — so the machine's model answers as the figure with
the figure's own citations, while every other tool stays Halbert's.
Tighten-only holds: the tool reads the sibling, never Halbert. It is the
same tool §4.3 already needs for H2, pointed at a different home.

What it will not do: a costume cannot carry H3's retrieval *pipeline*
(embeddings, reranking, the multi-figure discussion). If the founder wants
that, it is tenant mode, and it stays out of scope.

---

## 9. Approaches compared

**A — Route at the writers; the guest's memory lives at its home.**
(recommended) One ownership function; the tick skipped for guest turns and
the turn forwarded; private sources at the sensor output. Honest by
construction: guest words leave the disk, Halbert's psyche stays Halbert's,
no engine change. Cost: the sibling must be running and paired for a guest
to remember anything, and that is said to the user.

**B — Local guest namespace.** `PersonaMemoryStore("guest:…")` and a
cognition `base_path` per guest. An afternoon's work and the trap the
review named: everything stays on Halbert's disk under a different key.
Acceptable only as an *ephemeral* store deleted at session end, and only
as a fallback when the home is unreachable — which §4.3 declines for v1.

**C — Tenant.** The sibling's agent answers on Halbert's body. Already
rejected; listed so nobody drifts into it via the H3 experiment.

---

## 10. Decisions for the founder

| # | Question | Recommendation |
|---|---|---|
| **D1** | Does life safety on a private source still reach Halbert? | **Yes**, announced (§5.4). This is the one answer that changes the sensor gate's shape. |
| D2 | Normal mode: Halbert keeps the guest transcript, tagged and erasable? | Yes — "non-private" should mean what it says (§4.2). |
| D3 | Guest reads: none of Halbert's memory in v1? | Yes (review Q1); `recall_memory` leaves the guest allowlist. |
| D4 | Private mode never survives a restart? | Yes (review Q2). |
| D5 | Audit chain: engine change deferred to Halbert's own private hour? | Yes (§6). |

D1 is asked first. D2–D5 are stated as assumptions the build proceeds
under unless reversed.

---

## 11. Build order

| # | Piece | Depends on | Size |
|---|---|---|---|
| 1 | `continuity/ownership.py` + the tick skip + `append_message`/receipt tagging + the write-plane pin | nothing | 1–2 d |
| 2 | `persona/sibling.py` (fetch, memory add/search) + forward-the-turn + `recall_guest_memory` | 1, a paired sibling | 2 d |
| 3 | Pull channel: "be ⟨name⟩" in chat and the pill | 2 | 1 d |
| 4 | VIS-1 vision source registry (its own spec) | nothing | 2–3 d |
| 5 | Audio source ids in the same registry | 4 | 1 d |
| 6 | `persona/private_sources.py` + the sensor-output gate + the pill's source picker + the P6 statement | 1, 4, 5, D1 | 3 d |
| 7 | H3: the same adapter, `recall_guest_memory` pointed at its search | 2 | ½ d |

Private mode stays absent from the UI until 6 lands whole. Pieces 1–3
change normal mode and fix §1.6, which is a leak today.

---

## 12. Key files

| File | Role |
|---|---|
| `agents/state_machine.py:2897` | `_run_cognition_tick` — the tick to route |
| `integrations/cognition_wiring.py:201,280,378` | Halbert's cognition, memory store and tick closure, all keyed to Halbert's persona id |
| `agents/conversation_sqlite.py:813` | `append_message` — `origin`/`metadata` carry the actor without a schema change |
| `agents/threads.py:846` | thread-close receipts — `actor`, `request_id` |
| `continuity/state_store.py:615` | `redact_request` — session-wide erasure in normal mode |
| `tools/executor.py`, `persona/guest_tools.py` | the mask; where the write-plane pin goes |
| `obs/audit.py:212` and its callers | §6 — none reachable from a guest turn |
| `vision/watcher.py:218`, `audio/pipeline.py`, `integrations/frigate/frigate_event_mapper.py:267` | sensor outputs — where the source gate sits |
| `federation/peers_config.py`, `peer_middleware.py` | the paired-home record the pull channel reads |

---

## 13. Build notes — what landed on `feat/guest-persona` (2026-09-06, second pass)

The founder answered yes to D1–D5 and asked for the hardest pieces to be
built; the rest is fill-in work (§13.4). Every module below has tests that
failed before it existed. Full backend suite green with the worktree
runner at the time of the commit.

### 13.1 Built

| Plan row | Module | Tests |
|---|---|---|
| §4.1 one function; P3 fail-closed; §5.2 the map; D1 | `continuity/ownership.py` (`Owner`, `route_write`, `route_observation`, `guest_tag`); `persona/private_sources.py` (`assign`, `release`, `owner_of`, `active`; bound to the guest session, cleared on every ending) | `test_ownership.py` (37) |
| §4.2 the tick; forward the turn | `agents/state_machine.py` — `_run_cognition_tick` skips while a guest fronts; `_forward_guest_turn` runs from RESPONDING with the real reply and tells the user when the guest will not remember | `test_ownership_wiring.py::TestTheTick` |
| §4.2 the transcript; I7 | `agents/conversation_sqlite.py` — `append_message` tags rows with the session in normal mode and writes nothing in private mode; `forget_request(request_id)` is the transcript's half of "forget that session" | `::TestMessages` |
| §4.2 receipts | `agents/threads.py::_record_thread_state` — the session's actor and request id in normal mode; nothing in private mode | `::TestReceipts` |
| §5.3 the sensor gate, reference wiring | `integrations/frigate/frigate_event_mapper.py::handle_event` — routes by `frigate:<camera>` before the state tracker, the timeline and the cognition queue; a private camera's detection is forwarded to the guest's home; `LIFE_SAFETY_LABELS` (`fire`, `smoke`) always reach Halbert | `::TestFrigateGate` |
| §4.3, §7 the home, the client, the pull | `persona/guest.py` (`GuestHome`, `GuestSession.home`, `keepalive` renewal at most once per window); `persona/sibling.py` (`SiblingClient`, `persona_payload_from_config`, `forward_turn`, `forward_observation`, `install_from_home`) | `test_sibling_home.py` (24) |
| §4.3 / D3 / I6 the guest's own recall | `persona/guest_tools.py` — `recall_guest_memory` replaces `recall_memory`; `recall_thread`/`resume_thread` denied; `GUEST_ONLY_TOOLS` run by the executor's `_run_guest_only`; `WRITE_PLANE_TOOLS` pinned against the allowlist at import and in tests | `test_guest_tools.py` (27) |
| §7, §8 the channel | `dashboard/routes/guest.py` — `offer` accepts `home`; `POST /api/guest/pull` (local only) fetches, wears and announces; `/api/instance/info` reads the session in a worker thread so a keepalive ping never stalls the loop | `test_guest_routes.py` (22) |

### 13.2 What the build found

- **The tick defect is confirmed in a test, not fixed.** Without a guest,
  the tick fires from REFLECTING with Halbert's observations as the
  stand-in reply (attunement plan, HB-D1). The forward is therefore not
  hung on the tick: it runs from RESPONDING only, with the real reply, so
  no machine facts can reach a guest's home by that route.
- **H2's memory endpoints are two families.** `memory-v2/memories` (POST,
  the add) and `memory/search` (POST, the search) sit under
  `/api/personas/<id>/`; the structured-persona blueprint is a separate
  store under another prefix. `SiblingClient` uses the former pair; the
  paths are class attributes so a sibling that differs is one override.
  H3's list/detail routes match; its search is under its own blueprint and
  needs that override.
- **A pulled session is owned by its home.** `offered_by` is
  `home:<netloc>`, so the same home re-pulling replaces its own session
  and a different app cannot take it over (the existing conflict rule).
  The keepalive is `SiblingClient.ping` — a persona fetch — asked at most
  once per TTL window and bounded by `TRANSPORT_TIMEOUT_S`.
- **Frigate's life-safety labels are a guess about custom models.** Stock
  Frigate has no `fire`/`smoke` label; the set exists so that when a model
  emits one, D1 already holds. Audio's confirmed acoustic anomaly and HA's
  smoke/CO/gas entities are the real life-safety sources and are still to
  be wired (§13.4).

### 13.3 Contract additions

```
POST /api/guest/offer   body.home = {base_url, persona_id, token?, label?}   (optional)
POST /api/guest/pull    {base_url, persona_id, token?, label?, ttl_seconds?}  local only
                        → 200 {session (with home, token never shown), dropped}
                        → 400 bad home/persona · 409 another app fronts · 502 home did not answer
GET  /api/guest         fronting.home = {base_url, persona_id, label} | null
```

Memory at the home: one `episodic` memory per turn, content
`User: … \n<guest>: …` capped at 2000 characters, tags
`halbert-guest-session`, `<session_id>`, `turn`; observations from a
private source carry `observation` and the source id instead of `turn`.

### 13.4 Left for the fill-in session, in order

1. **Audio source ids and the acoustic gate.** `audio/pipeline.py` events
   already carry `source` and `area_id`; name them `mic:local:<n>` /
   `mic:wyoming:<satellite>` and route at the pipeline output exactly as
   the Frigate mapper does, with a confirmed acoustic anomaly as life
   safety. Then the HA mapper for smoke/CO/gas entities.
2. **VIS-1**, then the same gate at `vision/watcher.py:218`,
   `zone_watcher` and `ambient_webcam` with `webcam:<n>` / `screen:<n>`.
3. **Private-sources routes and the picker.** `POST /api/guest/private/assign`
   and `/release` (local only), the pill's source picker, and the P6
   statement at the moment the first source is handed over. Not before 1
   and 2 — a private mode that gates one sense and not another is the
   leak the design warns about.
4. **The verb.** "be ⟨name⟩" in chat and on the pill: list matches across
   paired homes (`SiblingClient.list_personas`) and call `/api/guest/pull`.
   The peer record needs a home URL and an outbound token; today the pull
   request carries them.
5. **The pill shows the home** (`fronting.home.label`) and says when a
   guest cannot remember (the `thinking` line the turn emits).
6. **H3.** Point `SiblingClient.PATH_MEMORY_SEARCH` at its blueprint and
   run the experiment; nothing else is needed.
7. **A session-erase control**: `forget_request` + `redact_request` under
   one local-only route, for the normal-mode transcript (D2).

---

## 14. A consideration — the "by what authority" axis, and Halbert as its reference

**Status:** consideration only, nothing to build here. Recorded so the
engine-side design starts from what already exists.

The founder raised (2026-09-06) that a debate-moderator consumer of
Haloysius may need a "by what authority" axis: a moderator that cuts a
speaker off must be able to say by whose rule, not its own preference.
The question is whether that axis is the one this document already
enforces with Halbert as the authority. It is, and Halbert is the better
first instance, because its authority is the most concrete kind there is: a
physical machine with tools, and rules written in code.

### 14.1 Three senses of the word already in use — keep them apart

| Sense | Where it lives today | Meaning |
|---|---|---|
| Who may *direct* the persona | Halbert `tools/role_gate.py` speaker roles; attunement `DirectiveContext.subject_confidence` and the `max_scope_entity_wide` role hook | the speaker's standing over the persona's actions and standing requests |
| Whose *rules bind* the voice | this document (I8, the tool mask, `ownership.py`, the BOUNDARIES block); engine `GovernancePolicy.authorize_action(action, args, context)` | the holder of the rules is not the one speaking |
| Which *store is truth* | `DECISIONS.md` MEM-03, the engine's memory handoffs ("a projection with no authority") | data authority |

And `haloysius.persona.values.MoralFoundation.AUTHORITY` is a fourth thing
— a personality trait — that must not be conflated with any of these. If
the engine lifts the axis, give it a name that is none of the above.
**Suggested: `Warrant`.** A warrant names who holds the rules, who speaks,
what the speaker may do on the holder's behalf, how the speaker hands
over what is not theirs, and the rule it cites when it acts.

### 14.2 The guest persona is already a warrant, spelled out by hand

| Warrant field | Halbert's guest layer | A debate moderator |
|---|---|---|
| holder | the machine, by its own name | the format's rules plus the host |
| voice | the guest persona | the moderator persona |
| mandate (tighten-only) | `GUEST_ALLOWED_TOOLS`, the write plane pinned out | floor, time, warnings; never the verdict |
| record | `ownership.route_write` — whose store the words go to | the platform's transcript, not the moderator's memory |
| hand-over | `hand_back_to_halbert`; "system work is the machine's side of the house" | "that is the host's call" |
| citation | the ledger's `reason`: "a deterministic rule that names itself" (`obs/audit.py`, `state_store.record_state`) | the rule id the cut-off cites |
| rendering | `_GUEST_BOUNDARIES` — said *after* the persona's own text (I8) | the moderator's rules block, said after the persona text |

Every row on Halbert's side exists and is tested. The moderator column is
the second instance; two instances is the right moment to lift a concept
into the engine, and not before.

### 14.3 Where it would plug in, if lifted

- `GovernancePolicy.authorize_action(..., context)` — `context` gains the
  warrant (holder, voice, mandate). Halbert's permissive policy would
  finally have something to say there; today its real gates sit outside
  the seam in `ToolSafetyFramework`, `RoleGate` and the autonomy gate.
- A prompt block, rendered last, the way `[ATTUNEMENT]` is rendered: who
  holds, who speaks, what the voice may do, how to hand over. Halbert's
  BOUNDARIES text is the hand-written draft of it.
- `DirectiveContext` gains the speaker's standing explicitly, so a
  moderator weighs "stop" from the host differently from "stop" from a
  participant — the same distinction `RoleGate` makes for tool risk.

### 14.4 What to do now

Filed with the engine as
`/Volumes/4TB-BAD/Haloysius/.handoff/HANDOFF-WARRANT-BY-WHAT-AUTHORITY-2026-09-06.md`
(indexed in that directory's README, §1c), with three questions for the
engine and no code requested.

Nothing in code. When the moderator design is written, start it from the
table in §14.2 and from `persona/guest_tools.py`, `continuity/ownership.py`
and `prompts/agent_prompts.py::_GUEST_BOUNDARIES` as the worked example,
rather than from a blank page — and name the engine type so it cannot be
mistaken for a trait or a store.
