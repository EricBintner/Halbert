# HANDOFF (for the Opus session): finish the guest persona and private mode

**Date:** 2026-09-06
**Branch:** `feat/guest-persona`, worktree
`/Volumes/4TB-BAD/Halbert/.claude/worktrees/feat-guest-persona` (from `main`
at `3efd3145`; do not rebase onto the main tree's checked-out branch, which
another session owns)
**Read first:** `DESIGN-GUEST-PERSONA-2026-09-06.md` (§15 for what landed),
`DESIGN-PERSONA-LAYERS-2026-09-06.md` (§13 for what landed, §14 for the
warrant), `REVIEW-PRIVATE-MODE-2026-09-06.md`,
`DESIGN-VISION-SOURCE-REGISTRY-2026-09-06.md` (VIS-1, ready to build).
**Founder decisions in force:** D1 life safety on a private source still
reaches Halbert · D2 normal mode keeps the guest transcript, tagged and
erasable · D3 the guest reads only its own memory · D4 private mode never
survives a restart · D5 the audit-chain engine change is deferred.

---

## 1. State of the branch

Everything below is built, tested, and green with the full backend suite
(5762 passed at commit `31ff43c4`). New tests: 125 across
`test_guest_persona.py`, `test_guest_tools.py`, `test_guest_prompt.py`,
`test_guest_routes.py`, `test_sibling_home.py`, `test_ownership.py`,
`test_ownership_wiring.py`.

| Layer | Built |
|---|---|
| Face | `persona/guest.py` session; tool mask at `get_schemas()` and `execute()`; handback; guest identity block with BOUNDARIES last; pill wears both names; Halbert stays quiet, not blind |
| Ownership | `continuity/ownership.py` — world is Halbert's in every mode; tick is the guest's; transcript tagged (normal) or the guest's (private); receipts follow; unclassified writers fail closed while a guest fronts |
| Home | `persona/sibling.py` — fetch a persona, forward each turn as one memory, `recall_guest_memory`, keepalive by ping; `POST /api/guest/pull` (local) |
| Private sources | `persona/private_sources.py` — the session-bound source → owner map; `route_observation` with the life-safety exception; **Frigate mapper is the reference gate** |

What is deliberately **absent**: any private-mode UI or route. The founder's
rule: a private mode that gates one sense and not another is worse than none.

## 2. How to run tests here (three traps)

```bash
cd /Volumes/4TB-BAD/Halbert/.claude/worktrees/feat-guest-persona
arch -arm64 /Volumes/4TB-BAD/Halbert/.venv/bin/python ./wt_pytest.py halbert_core/tests/ -q -p no:cacheprovider
```

1. The venv's editable install points at the **main** tree; `wt_pytest.py`
   strips that finder. Never run bare `pytest` from a worktree.
2. The Bash cwd resets between calls; prefix every command with `cd`.
3. `arch -arm64`, or the universal binary runs x86_64 and collection dies on
   `psutil`.

## 3. Next steps, in order, with the acceptance test for each

### N1 — Audio source ids and the acoustic gate — **DONE**
See `DESIGN-PERSONA-LAYERS-2026-09-06.md` §13.5. Built, +10 tests, full
suite green (5772). Two departures from the brief below, both forced by the
code: the ids are per-adapter (`mic:local:study`, `mic:rtsp:patio`) because
per-satellite and per-peer identity does not reach the chunk; and the ring
buffer is shared, so events name every live ear and `route_mixed_observation`
drops a window whose ears disagree instead of guessing. Original brief:

`audio/pipeline.py` events already carry `source` and `area_id`. Name them
`mic:local:<device_index>`, `mic:wyoming:<satellite>`, `mic:rtsp:<name>`,
`mic:webrtc:<peer>` (the ingress adapters in `audio/ingress/` know which
they are). At the pipeline's output — before the event bus, findings,
timeline or ledger — call `ownership.route_observation(source_id,
life_safety=<confirmed acoustic anomaly>)` exactly as
`frigate_event_mapper.handle_event` does: GUEST → `sibling.forward_observation`
and nothing of Halbert's; DROP → nothing; HALBERT → as today.
*Accept:* a test in the shape of `test_ownership_wiring.py::TestFrigateGate`
for the acoustic path, including the life-safety case.

### N2 — VIS-1, then the local vision gate (2–3 d)
Build the registry as specified (`vision/sources.py`, `permit_source`,
`SensesVisionConfig.sources`, the tool-argument fix at `vision_tools.py:137`).
Then gate `vision/watcher.py:218`, `zone_watcher`, `ambient_webcam` with
`webcam:<n>` / `screen:<n>` ids, same shape as N1.
*Accept:* VIS-1's own tests plus a `TestVisionGate` mirroring the Frigate one;
and a test that a persona scoped to one source cannot capture another by
passing a tool argument.

### N3 — The HA mapper for smoke / CO / gas (½ d)
`ha_event_mapper.py:218,246` write the timeline. Those entities are life
safety (`modality_wiring.LIFE_SAFETY_EVENT_TYPES`); route with
`life_safety=True` so D1 holds there too. Other HA entities are the house,
Halbert's in every mode — no source assignment applies to them yet.

### N4 — Private-sources routes, the picker, and the statement (1–2 d)
Only after N1–N3. `POST /api/guest/private/assign` and `/release`
(`require_local_admin`), `GET /api/guest` gains `private_sources`. The pill's
source picker lists registry ids (VIS-1 + audio). At the first assignment,
show the review's P6 statement, by source: "Halbert stops recording what you
say and what ⟨source⟩ sees; it keeps recording what the machine and the rest
of the house are doing; life safety still reaches Halbert."
*Accept:* route tests in `test_guest_routes.py` style; a frontend test that
the statement renders before the first source is handed over.

### N5 — The verb: "be ⟨name⟩" (1 d)
In chat and on the pill: list matches across paired homes
(`SiblingClient.list_personas`) and call `POST /api/guest/pull`. The peer
record needs a home URL and outbound token; today the pull request carries
them. The pill shows `fronting.home.label` and surfaces the turn's
"⟨guest⟩ will not remember this turn" line (a `thinking` event).

### N6 — Session erase (½ d)
One local-only route that calls `SqliteConversationStore.forget_request`
and `StateStore.redact_request` with `guest-session-<id>` (D2's promise).

### N7 — H3 (½ d)
Override `SiblingClient.PATH_MEMORY_SEARCH` for the historical-minds app's
blueprint prefix; run the experiment; nothing else.

### N8 — Adopt the engine's `Warrant` once `feat/warrant` merges in Haloysius
`haloysius.warrant.Warrant` / `render_warrant_block` now exist on that
branch (worktree `/Volumes/4TB-BAD/Haloysius-worktrees/warrant`). When it
merges: build the guest's warrant from `GUEST_ALLOWED_TOOLS` (holder = the
machine's name, voice = the guest, mandate = tool → "guest_profile",
hand_over = the handback line) and render `_GUEST_BOUNDARIES` through the
engine renderer, keeping the ordering rule (after the persona text). Also
`Utterance.authority` gained `authority_rule`; Halbert's attunement codec is
type-hint driven and should absorb the new fields — run
`test_attunement_engine_sync.py` on `feat/attunement-halbert` to confirm.

## 4. Known and deliberately untouched

- **The tick fires at REFLECTING with a synthetic reply** (attunement plan
  HB-D1). Pinned as today's behaviour by
  `test_ownership_wiring.py::TestTheTick`; the guest forward does not depend
  on it. Fix it on the attunement branch, not here.
- **`modality_wiring.get_modality_prompt_builder`** has no callers and
  hardcodes "Halbert". When it is wired, read `current_guest()` there.
- **`PersonaManager` vs `PersonaStore`** (PERS-02) — the guest layer depends
  on neither; leave it.
- **Frigate life-safety labels** (`fire`, `smoke`) are a guess about custom
  models; the real life-safety sources are N1 and N3.

## 5. Naming and secrecy

The sibling apps are H2 (companion) and H3 (historical minds) in every
document and commit in this repo; their product names are never written
here. The debate-moderator consumer is referred to by role in Halbert's
documents.
