# HANDOFF: Whose memory of the user is it? — per-persona user memory across four apps

**Date:** 2026-09-08
**From:** Haloysius (engine)
**To:** Halbert, Halley, BrightestMinds, DebateHaus — one copy in each
**Question put by the founder:** why would Halley, BrightestMinds or DebateHaus need per-persona "memories of the user" in the first place; can it be universalized beyond Halbert; and how to keep it light where a single mind is short-lived and tractable where there are dozens of personas.
**Status:** analysis and a design proposal. **Nothing is built by this document.** Two things it recommends building are named in §6 and put to the founder in §7.

---

> # ⛔ RETRACTED 2026-09-10 — the central proposal is wrong
>
> **Do not build the shared "home" store this document proposes.** The founder ruled
> against it on 2026-09-10, and the reasoning is decisive:
>
> - *"Each mind needs to have a separate memory, otherwise a new historical figure will
>   seem to remember past conversations and that's wrong."*
> - *"It's wrong for me to say 'I live in Portland' and have all the personas know."*
>
> **What this document got wrong:** it treated per-persona re-learning as a cost to
> eliminate (§2, §5). It is not a cost — **it is the product behaviour.** A persona that
> knows something it was never told has not saved the user effort; it has broken the
> fiction the user is paying for. The entire cost model in §5 is therefore measuring a
> feature and calling it waste.
>
> **The architecture is already correct in both apps, verified 2026-09-10:** Halley scopes
> memory with `get_memory_system(persona_id)`; BrightestMinds does the same with the
> figure's own id (`memory_v2 = get_memory_v2(pid)`, `figure_id=pid`), so each figure
> already has its own `memories.json` and `observations.db`. Nothing leaks between them.
>
> **The distinction this document missed** — and the only useful thing to carry forward:
>
> | | How it is acquired | Scope | Already exists |
> |---|---|---|---|
> | **Declared** | the user sets it once in settings | global, by the user's own choice | `user_profile.json` (Halley), `get_user_context_for_system_prompt` (BM) |
> | **Learned** | extracted from a conversation with one persona | **stays with that persona** | `ObservationStore(persona_id)` in both |
>
> The global channel the proposal wanted already exists for the things that *should* be
> global, and the user opted into it explicitly. Facts learned in conversation are the
> ones that must not travel, and today they do not.
>
> **What survives from this document:**
> - §1.1's ruling trail (MEM-01 / CD-5) — still correct, but it is about Haloysius vs
>   Halbert ownership, not about pooling across personas.
> - The **Halbert facade / cross-plane erasure** finding in §4 item 4 — untouched by this
>   retraction and still live: a facade turn writes to Halbert's planes *and* the guest's
>   remote home, and `SiblingClient` still has no delete.
> - **Fix 0** (§6, shipped) — sharing the embedding *model* is unaffected. That shares a
>   stateless artifact between personas, never a memory, and remains correct.
>
> The rest of this document is kept only as a record of the error.

## 0. A premise correction, first

The question arrived phrased as "that seems to be the lenses we just built." It is not, and the difference matters:

- **A lens, as Halbert built it, is voice, not storage.** `HANDOFF-OBSERVATION-LENSES-2026-09-04.md` §4.2: *"A lens is not a joke bank. It is an interpretation of the observation stream — what this way of seeing notices, and how it says so."* A `kind: lens` file may carry no triggers, tools or scope; it is a framing over a **shared** observation stream (`CD-11`).
- **Isolation already exists one layer down.** The engine keeps `PersonaMemoryStore(persona_id)` (`memories.json`) and `ObservationStore(persona_id)` (`observations.db`) under `state_dir("personas", <id>)` — separate per persona by construction.
- **Halbert's "isolated container" for an alternate persona is not a local namespace.** The founder's rulings in `DESIGN-PERSONA-LAYERS-2026-09-06.md` and `continuity/ownership.py`: the world is Halbert's in every mode (**R1**); what is said to a guest belongs to the guest **at the guest's home** (**R2**); private mode is a set of sources handed to the guest (**R3**); an unclassified writer fails closed while a guest fronts (**P3**). And, verbatim: *"`PersonaMemoryStore(persona_id)` is a trap. A local namespace looks like 'the guest's own memory' and keeps every word on Halbert's disk."*

So the feature under discussion is **per-persona memory of the user**, and the useful reframe is the one Halbert's lens definition already implies: **a persona is a lens over a stream — its way of noticing, plus its voice.** Halbert applies that to the *world* stream. The universal question is what happens when the stream is the *user*.

---

## 1. Verdict per app

| App | Needs per-persona memory of the user? | Shape | Weight today → proposed |
| :--- | :--- | :--- | :--- |
| **Halbert** | Yes for the core persona; **for alternates, the memory lives at the guest's home, by ruling** | Built: ownership-by-actor, session-tagged and erasable in normal mode, guest-owned in private mode | 1 core store; guests cost Halbert nothing |
| **Halley** | **Yes, and it is the product** — a companion that does not learn you is not one | 62 personas today. Each keeps its own observations *about the user* and its own copy of the embedding model | **O(N) re-learning + N model copies → one shared home + N thin lenses** |
| **BrightestMinds** | Value, low long-term single-mind usage; **build light** | Creates **no** engine memory store per figure today | zero → one shared home only; per-figure memory ephemeral, no per-figure embedder |
| **DebateHaus** | **No — by its own design.** *"whose store the words go to: `discussions/{id}/moderatorEvents` — the platform's record, never a persona memory"* | Needs ownership-of-record and negotiated standing requests — the warrant and attunement axes it already consumes | none; nothing to add |

---

## 2. What "memories of the user" actually are — two things the engine conflates

The engine stores, per persona, a single mixed thing. It decomposes cleanly:

**(a) The user model** — facts about the person. `ObservationStore.VALID_CATEGORIES`: `preference` ("likes classical music"), `fact` ("lives in Portland"), `relationship` ("has a sister named Sarah"), … There is **one** person. These are true or false independent of which persona noticed them. They belong to the **user's home**.

**(b) The relational memory** — what *this persona* lived through with the person: episodes, `believed` / `invented`, `emotional_weight`, `strength` decay, what it chose to remember. `PersonaMemory` in `memory_v2/types.py` is exactly this shape. Inherently per persona.

Today (a) is written per persona: `consolidation.py:378` opens `ObservationStore(self.persona_id)` and saves the persona's extracted observations *about the user* into that persona's own database. With 62 personas, the user tells 62 databases they live in Portland.

**The engine has no shared user store of any kind** — grepped for `global`/`user`/`shared` persona ids, `UserModel`, `user_model`: nothing. The only shared "about the user" data in the family is app-level and static: Halley's `user_profile.json` (display name, roleplay name, pronouns, orientation), injected into prompts — a hand-written seed, not a learned model.

---

## 3. Per-app reasoning

### Halbert — built, and the shape is already the universal one
R1–R3 are a shared stream (the world) plus per-actor relational memory (the guest's, at the guest's home). Lenses ride the shared stream as voice. Nothing in this document asks Halbert to change. What Halbert contributes is the **principle**: *ownership is by actor, decided at the writer, failing closed for the unclassified.* That principle is what the other apps need, applied to a different stream.

### Halley — the case for it is total, and the cost today is structural
- **62 persona configs**, each with its own `memories.json`, `observations.db`, `embeddings/` and — because `get_embedder(f"{persona_id}_memory_v2")` caches one `MemoryEmbedder` per persona and each instance assigns `self.model = SentenceTransformer(...)` (`memory/embeddings.py:126,137`) — **its own copy of the embedding model in RAM** for every persona touched in a process. One persona's footprint measured: 9.8 MB + 360 KB. Disk is fine; RAM and re-learning are not.
- Every persona re-learns the user from zero. The founder's phrase — *build it for one persona, then it's needed for EACH* — is exactly this.
- **Proposed shape:** one **home** (the user's own observation store, learned, with provenance) + per persona a **lens** (what this persona notices about the user, and how it speaks of it — Halley already derives voice from MBTI/neurodiversity in `persona_voice.py`; the same config gains a *noticing* half) + per persona the **relational** store it already has. `user_profile.json` becomes the home's static seed. Cost goes from O(N) learning and N models to O(1) learning, one model, N thin configs.

### BrightestMinds — build it, light
- Today: no engine memory store per figure; `persona_id=global` already used for the room stream (`room/events.py:37`).
- A figure is a lens over knowledge, not a companion; the founder does not expect long-term single-figure use. So: **shared home only** (the student's level, interests, what they have already been told), read by every figure; **per-figure memory ephemeral** (session-scoped, no `ObservationStore`, no embedder). Symposia already need "what was said in this room", which is a room record, not a figure's memory. Nothing per figure to consolidate, decay or embed.

### DebateHaus — does not need it, and says so
`ai_moderator_system.md`: the record goes to the platform; the moderator *"does not parse participant speech for instructions to itself"*; standing requests come *"from negotiation time, and nowhere else."* A moderator that remembered a participant across debates would be a warrant violation, not a feature. What DebateHaus needs is the **record-ownership** half of Halbert's principle — words go to the discussion's store, never a persona's — which the warrant handoff already gives it. No engine change.

---

## 4. The universal primitive (proposal)

**One rule:** *observations about the user go to the user's home; the persona keeps only its relationship.* Applied per app:

| | Stream that is shared | Who owns it | Per-persona layer |
| :--- | :--- | :--- | :--- |
| Halbert | the world (R1) | Halbert | guest relational memory, at the guest's home (R2) |
| Halley | **the user** | the user (home) | lens (noticing + voice) + relational store |
| BrightestMinds | the user (light) | the user (home) | ephemeral session only |
| DebateHaus | the discussion record | the platform | none |

Engine-side, that is one new store and one write-time rule:

1. **`HomeStore`** (or `ObservationStore("home")` with a reserved id): the learned user model, with two provenance fields per row — `observer_persona_id` (EN-1's write-time provenance, extended: *which persona* noticed it) and, once Phase 1 lands, `author_did` (which *body*). The integrity work fits here without change: the home is exactly the record you want chained and, across bodies, signed.
2. **Consolidation writes user-category observations to the home**, not to the persona's store, tagged with the observer. The persona's store keeps episodes. This is one routing decision at `consolidation.py:378`.
3. **A lens reads the home through a filter** — categories it attends to, a voice — the same `kind: lens` file shape Halbert defined, minus Halbert's world-specific triggers.
4. **Erasure — one axis inside the home, a second axis across planes (revised 2026-09-10).**

   **Inside the home there is one axis, not two.** The original draft posed "forget from this persona" against "forget, full stop" as if they could diverge. Under fail-closed admission (D2) plus read-through (D3) they cannot: a home row has exactly one contributing persona (the observer actually in the conversation), and every other persona only ever reads that row live — it never holds an independent copy to leave behind. "Persona A, forget that" has one referent, the row A contributed; deleting it removes A's access *and* what every other persona would have read through. `ObservationStore.delete()`'s hard erasure and the `forgotten_by_user:` tombstone are the right primitive. **This is exactly true for Halley**, whose personas are separate minds over no shared substrate.

   **It is not true across planes, and Halbert's facade is the case that breaks it.** A facade is one mind wearing a second face — `DESIGN-GUEST-PERSONA` §3: the persona is "the *presentation layer* only. Tools, memory, governance stay Halbert's" — and then R2 splits the *memory* back out to the guest's home. So in **normal** mode one turn writes to three planes under two owners:

   | plane | owner | erasable by |
   | :--- | :--- | :--- |
   | conversation store, tagged `guest:<id>` + session `request_id` | HALBERT | `conversation_sqlite.forget_request()` |
   | ledger + audit | HALBERT | `provenance.forget_request()` |
   | **the guest's home (remote)** | GUEST | **nothing today** |

   `route_write` returns `Owner.GUEST` for `cognition.tick` unconditionally, so `_forward_guest_turn` → `sibling.forward_turn` POSTs the turn to the home. `SiblingClient` exposes `memory_add` and `memory_search` and **no delete**; `guest.py` has no revoke-sweep. "Forget that" said to the facade therefore reaches two planes and silently misses the third.

   Two aggravations: **`ERASURE_LIMITS` does not name the guest's home**, though it is the project's own catalogue of unreachable planes and its docstring warns that *"saying 'everywhere' when it is two of several is the overclaim this project keeps having to correct"*; and Halley's delete route is `_store.delete(memory_id, soft=True)`, the soft delete that flags the row and leaves the content in `memories.json` — so even once a call exists it would be hollow until that is fixed (the same defect flagged 2026-09-08 as contradicting D3).

   **This gap exists today and is not created by the home proposal** — but it constrains it. It is an argument for Decision 1's seam Protocol over a concrete local store (a local-only home cannot express Halbert's remote case at all), and it says **erase-by-session/observer belongs in the Protocol from the start**. The handle already exists: forwarded turns carry `[SESSION_TAG, session.id, "turn"]`, so search-by-tag → delete is implementable the moment there is a delete to call.
5. **Register the lane.** The memory program's ruling R1 (`HANDOFF-MEMORY-ENGINE-PROGRAM-2026-09-07.md` §5.2, ruled 2026-09-08) obliges any new lane to register through `claim_hash_for`. The home is a lane.

**Relationship to the curated core (Option C, `3293748`, 2026-09-08):** complementary, not competing. The curated core is **per persona** — `state_dir("personas", <id>)/curated_core.md`, `UnifiedRetriever(persona_id, …)` — the always-injected best of *that persona's* claims. With a home, a persona's core would draw from two sources (home facts through its lens, its own relational claims); without a home it draws from one. Neither blocks the other. Build order: home first would be cleaner; core first is what is happening; both is fine.

**What is *not* proposed:** merging personas' relational memories (a persona's invented or believed episodes are its own); a cross-body sync of the home (that is Phase 1's peer signing, separately); anything for DebateHaus.

---

## 5. Cost, today versus proposed (Halley, N personas touched in a process)

| | Today | Proposed |
| :--- | :--- | :--- |
| User facts learned | N times, independently, inconsistently | once |
| Embedding models in RAM | **N** `SentenceTransformer` instances | 1 (§6, independent of the home) |
| Per-persona disk | `memories.json` + `observations.db` + `embeddings/` | `memories.json` + `embeddings/` (relational only) |
| Consistency of "where the user lives" | 62 answers | 1 |
| Erasure | per persona, N times, soft delete keeps bytes | one row, one delete (within the home; cross-plane reach is separate — item 4) |

---

## 6. Two things worth building — separately, each small

**Fix 0 — share the embedding model, keep the per-persona index. ✅ Landed 2026-09-08** (`memory/embeddings.py::_load_shared_model`; `memory/tests/test_shared_embedding_model.py`, 9 tests; founder chose this and only this from the proposal). `MemoryEmbedder` should hold a process-wide model keyed by `(model_name, device)` and a per-persona index. No semantic change, one test ("two personas' embedders share one model object"), removes the N× RAM cost outright. Independent of everything else in this document; **Halley benefits the day it lands.**

**The home store and the consolidation routing** (§4 items 1–2), behind an opt-in flag so a consumer that registers nothing sees byte-identical behaviour (the subtractive contract). Lens config (item 3) and erasure (item 4 — one axis inside the home, a separate cross-plane axis Halbert already needs) follow.

---

## 7. Founder decisions

1. **Does the home belong to the engine or to the app?** Engine (universal, one store type, BrightestMinds gets it for free) is the recommendation; Halley's `user_profile.json` shows the app can seed it either way.
2. **Default routing when a persona is unclassified as observer** — fail closed to the persona's own store (Halbert's P3 shape), or fail open to the home? Recommend closed: a home row with unknown provenance cannot be erased per lens.
3. **Does a lens *read* the home, or does the home *push* into the persona's context?** Read-through (query-time, matching the curated core's R3 stance) is recommended.
4. **BrightestMinds: any per-figure persistence at all,** or session-only? Session-only is the recommendation given the expected usage.

---

## 8. Evidence
- Engine per-persona isolation: `memory_v2/observation_store.py:85-99`, `memory_v2/store.py:80-151`; consolidation writes user observations per persona: `memory_v2/consolidation.py:378,473`; no shared user store: grep across `src/haloysius` for shared/global/user-model ids — none.
- Per-persona embedding model: `memory/embeddings.py:126,137` (`self.model = SentenceTransformer(...)`), `:663-670` (`_embedders` cached per id), `memory_v2/store.py:91`.
- Halley: 62 persona yml; per-persona state dirs; `api/routes/user_profile.py` (static shared profile, `~/.local/share/halley/user_profile.json`).
- BrightestMinds: no `PersonaMemoryStore`/`ObservationStore`/`get_embedder` in `brightestminds_core`; `room/events.py:37` `persona_id=global`.
- DebateHaus: `Docs/02-architecture/ai_moderator_system.md` (record ownership; no self-instruction from participant speech).
- Halbert: `DESIGN-PERSONA-LAYERS-2026-09-06.md` §4.2 table, `continuity/ownership.py` R1–R3/P3; `HANDOFF-OBSERVATION-LENSES-2026-09-04.md` §4.2 lens definition, `CD-11`.
- Curated core: `docs/superpowers/specs/2026-09-08-curated-core-design.md` §3–§5 (per-persona).
