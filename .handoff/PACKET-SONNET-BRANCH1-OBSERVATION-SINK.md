# PACKET → Sonnet: branch 1, `fix/observation-sink`

**Read first**: `.handoff/HANDOFF-OBSERVATION-LENSES-2026-09-04.md` §3.2, §3.3, §5.1, §7 A0–A2b, §14 Branch 1.
**Tier/effort**: A0-code `high` · A1 `med` · A2 `xhigh` · A2b `high`
(A2c and A0-privacy are opus-tier and are **not yours** — see "Already done" and "Not yours".)

## Branch

Cut `fix/observation-sink` from `main`. An opus session is working
`feat/skills-wired` in parallel; it touches `dashboard/routes/agent.py`,
`skills/`, `tools/safety.py` and `agents/state_machine.py`. **You touch none of
those.** There is no file overlap, so neither branch needs to wait.

If you work in a git worktree: the editable install silently resolves
`halbert_core` to the **main** tree, so your tests will pass against code you did
not write. Use the meta-path-stripping wrapper, or work in the main checkout.

## Already done for you (on `fix/observation-text-normalisation`, merge it first)

`halbert_core/halbert_core/integrations/observation_text.py` — call it at the sink:

```python
from halbert_core.integrations.observation_text import (
    normalise_entity_id, normalise_observation_title,
)
```

`normalise_observation_title(text)` for `title` and `description`;
`normalise_entity_id(...)` for `entity_id`. Both never raise. Do not add your own
scrubbing, and do not redact `entity_id` yourself — that would destroy the
`count_by_entity` grouping A5 needs, and there is a test asserting it doesn't.

## Three forks already closed — do not re-open them

1. **`VIGILANCE` maps to `EmotionCategory.ANTICIPATION`.** Do not add an enum
   member to Haloysius. Plutchik defines vigilance as the intense form of
   anticipation, so the mapping is the model's own semantics and needs no
   cross-repo change and no mood-map entry. Apply at
   `frigate_event_mapper.py:223,248,258,262,267` and
   `system_event_mapper.py:194,220`; fix `skills/builtin/frigate-ops/SKILL.md`,
   which documents `VIGILANCE` as real.
2. **DetectorRunner → `add_event` is out of scope**, as is rewriting
   `_scan_discovery` against `DiscoveryEngine` methods that exist. State in the
   RESULTS row that a sysadmin ledger receives only VisualWatcher anomalies until
   that lands.
3. **Provenance prefix is `[t{id}]`** (that is branch 3's problem, but do not
   invent a different one in a comment).

## Not yours

- **A2c** — done, above.
- **A0-privacy** — naming the ledger in `ERASURE_LIMITS` and deciding
  person-keyed erasure for `occupancy_change` rows. The opus session lands that
  into this branch before it merges. Leave `continuity/provenance.py` alone.

## The work

**A0.** `get_timeline_store()` in `integrations/cognition_wiring.py` beside
`get_trackers()`; path from `utils.paths.data_dir()` (it exists, `paths.py:53`) so
`HALBERT_DATA_DIR` is honoured; always constructed, no capability gate
(`ALL_CAPABILITIES` is twelve presence probes for external resources and a local
SQLite file has nothing to probe; `FindingStore` is the ungated precedent); log
once at startup with its path. Add `timeline: Optional[TimelineStore] = None` to
`HAEventMapper.__init__` and `FrigateEventMapper.__init__`; inject at
`cognition_wiring.py:477`, `:500` and `dashboard/app.py:1090`. Make
`get_frigate_event_mapper()` accept `is_mqtt_configured()` so the `app.py`
fallback instance — which is not in the composite and can only ever be
cap-dropped — disappears.

**A1.** Move to `continuity/timeline.py`. Keep `home/timeline.py` as a one-line
shim **or** update `tests/test_timeline_store.py:9` and
`tests/test_behavior_store.py:18` **in the same commit** — an `__init__`
re-export alone leaves the module path gone and both files red. There are no
callers and no existing databases: nothing ever wrote one.

**A2.** Write at ingestion — `FrigateEventMapper.handle_event()` and
`HAEventMapper.add_event()` — via `record(TimelineEvent(timestamp=<the event's
own timestamp>, …))`. **Not** `record_simple()` inside `_add_observation`:
that runs only when someone chats and stamps `time.time()` at call time, so every
row would carry the next chat turn's timestamp and break A5's windows,
`get_correlations()` and the inferrer's slotting.

Row contract, exactly:

- Frigate: one row per message. `event_type="frigate_event"`, `source="frigate"`,
  `entity_id=f"{camera}:{sub_label or label}"` (the Frigate event id is unique per
  tracked object and never recurs, so it is useless as a grouping key),
  `data={type: new|update|end, frigate_event_id, zones, score}`.
  The `_apply_label_emotion` strings ("Person seen at …", "Vehicle at … at
  night", "Package detected at …") are **affect only, never a second row** —
  otherwise one detection yields two to five rows and A5 counts 6–9 for three
  sightings.
- HA: `event_type="ha_state_change"`, `source="ha"`, `entity_id=<HA entity_id>`,
  `data={domain, old_state, new_state, device_class}`. Person and
  `device_tracker` transitions **additionally** write `occupancy_change` with
  `data={"direction": arrival|departure}`. Those are the two shapes
  `PatternInferrer` and `get_correlations()` already read.

Keep `populate_cognition()` for worries and emotions. Do not silently drop
again: log once at startup if there is no timeline, and log the
`MAX_PENDING_EVENTS = 500` cap drop with a count, rate-limited.

**A2b.** `SystemEventMapper.populate_cognition()` records each drained event
(`event_type=event["type"]`, source, severity, `title=detail`) **before**
applying it. Without this the sysadmin install — the one that motivates the
whole ledger — has a ledger and still no writer.

## Two standing rules

- **Never a `MagicMock` cognition.** Real `PersonaCognition`, real
  `TimelineStore`. `test_frigate.py:233` builds `cognition = MagicMock();
  cognition.internal_state = MagicMock()` and asserts
  `internal_state.add_observation.called` at `:249`, `:288`, `:326` — `hasattr`
  is true on a mock, so those three assert a dead branch and pass today.
  **Rewrite them against a temp `TimelineStore`.** That mock is the entire reason
  DEFECT-2 stayed invisible.
- Run only the named files, from the repo root, `arch -arm64` prefixed. Never the
  whole suite in the review loop.

## Done evidence (ROADMAP rule 6)

- [ ] Startup log names the timeline path; `stats()` reachable on a sysadmin install; `HALBERT_DATA_DIR` honoured
- [ ] A synthetic Frigate `new person` through `handle_event()` yields **one** `timeline_events` row with the detection's own timestamp, **with no cognition tick having run**; likewise an HA `state_changed` via `add_event()`
- [ ] `test_frigate.py:249/288/326` rewritten against a temp `TimelineStore`
- [ ] One test per mapper against a real `PersonaCognition` — green only once VIGILANCE is fixed
- [ ] HA observation-path tests in `test_ha_phase2.py` (seven `populate_cognition` tests exist; none asserts the observation path)
- [ ] A `cognition_wiring` test that the getters inject the store
- [ ] The 500-cap drop is logged with a count
- [ ] `arch -arm64 .venv/bin/python -m pytest halbert_core/tests/test_frigate.py halbert_core/tests/test_ha_phase2.py halbert_core/tests/test_timeline_store.py -q` green from the repo root
- [ ] A RESULTS row citing the commit; `MIND-1` status gains "`C4-04` partial: HA/Frigate/system events land in the event ledger (`<sha>`)"

Rebase before writing the RESULTS row — this tree lands dozens of commits a day
and every line number above will drift.
