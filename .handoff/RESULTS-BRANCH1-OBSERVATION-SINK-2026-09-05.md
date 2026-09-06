# RESULTS: `fix/observation-sink` — review findings closed, plus what scrutiny found

**Branch**: `fix/observation-sink`, `85b9f3d0` (Sonnet) → `3d44f1be` (this pass)
**Suite**: `5535 passed, 14 skipped` — the whole of `halbert_core/tests/`, run from the
worktree with the new conftest, so against the worktree's own source.
**Review this answers**: `.handoff/REVIEW-BRANCH1-OBSERVATION-SINK-2026-09-05.md`

## The five review findings

| # | Finding | Commit |
|---|---|---|
| 5 | A worktree ran its tests against the main checkout's source | `65b0e016` |
| 1 | The prompt-injection path A2c was built for was still open | `5d5c7d0d` |
| 2 | HA and Frigate rows carried no title, so the prose was still discarded | `5d5c7d0d` |
| 3 | Frigate rows carried handle time, not the detection's own timestamp | `5d5c7d0d` |
| 4 | `_add_observation` was still the dead function | `ff932ff9` |

Finding 5 went first: until it was closed, every later test run was unreliable
evidence. Its own guard test was written, watched to *pass while the defect was
present*, and rewritten — asserting on the top-level namespace package proved
nothing, because it resolves to whatever directory pytest put on `sys.path`
even while every module inside it loads from another tree. The redirect it
installs was also a no-op at first: setuptools appends the finder *class* to
`sys.meta_path` while `MAPPING` is a module global, so `getattr(finder,
"MAPPING")` was always None. Both were caught by checking that the check
worked.

Finding 2's root cause was in the plan, not the implementation: §7 A2's row
contract lists `event_type`, `source`, `entity_id` and `data` and omits
`title`, while A2c ("redact the title") and A4 (rendering `[t{id}] Front door
opened 07:41`) both assume one. **The contract should be amended to include
`title` before branch 3 reads from it.**

## What scrutiny found afterwards

Three further defects, none of them in the review, all confirmed by running the
code rather than reading it.

### A. An unwritable data directory took the whole HA integration down (`2ceed3b2`)

`get_timeline_store()` constructed eagerly and let failures escape, so a
read-only data dir, a corrupt file or a full disk propagated out through the
mapper getters and killed construction. Both mappers already accept
`timeline=None` and warn, so degrading was the designed behaviour — an
observation *source* must not depend on the ledger that observes it. Returns
None now, once, at ERROR.

### B. A phone rejoining Wi-Fi was recorded as someone arriving home (`711e635d`)

The occupancy check was `new_state == "home" and old_state != "home"`, but
`old_state` is `None` whenever HA first adds an entity (restart, integration
reload) and `"unavailable"`/`"unknown"` every time a Wi-Fi device tracker drops
off the network. **Three of four realistic transitions into "home" were forged
arrivals.** A5's recurrence count — the thing the ledger exists to support —
would have reported "Sarah arrived home 14 times today", and the morning report
would have said so. An occupancy row asserts a transition, so it now requires a
known prior state; the `ha_state_change` row is still written either way.

### C. A removed entity killed the event, not just the row (`3d44f1be`)

Introduced by the finding-2 fix, then found by walking what HA actually puts on
the wire: `describe_state_change` called `new_state.startswith("armed_")`, and
HA sends a null state object when an entity is removed. `event.get("old_state",
"")` returns None for a key that is present and null, so the default never
applied. The `AttributeError` escaped `add_event`, which queues for the
cognitive tick *after* recording — so the affect was lost with the row, and the
stream logged it as a generic "Event callback error".

Fixed twice over, because coercing the states alone would only fix today's
instance: the recording step is now wrapped so nothing in it can escape into
ingestion again. Same rule as A, one layer in.

## Checked and deliberately left alone

- **Concurrency**: 800 writes across four threads land 800 rows, no errors. The
  process lock covers both ingestion threads.
- **SQL**: `query()` interpolates only fixed condition fragments and binds every
  value.
- **Ingestion cost**: 0.54 ms per event end to end (~1855/sec) against a few
  thousand events a day. `redact_text` at 19 µs is not the bottleneck.
- **`FrigateStateTracker.on_event`** does not guard a non-dict payload, but that
  is pre-existing and contained — the MQTT subscriber wraps the callback and
  drops the one message. Out of this branch's scope.

## Open, and worth tasking

1. **Retention is decided but not enforced.** CD-5 kept 90 days;
   `TimelineStore.cleanup(max_age_days=90)` is scheduled by nothing, and this
   branch gives the ledger its first writer, so growth is now real. Wiring a job
   belongs to `MIND-1`'s scheduler work, not here.
2. **Every HA and Frigate row is severity `info`.** The row contract does not
   specify severity, and CD-3 selects by `(count, severity, recency)`. A
   severity policy decides what the morning report surfaces, so it should be
   chosen in branch 3/4 rather than invented at the sink.
3. **A5's grouping will be coarser than the motivating example.** `entity_id` is
   `f"{camera}:{sub_label or label}"`, and Frigate usually assigns `sub_label`
   (face, plate) *after* the object is first tracked — so `new` rows, the only
   ones A5 counts, generally group as `front_door:person`. "Third time that grey
   van's parked out front" needs the sub_label at `new` time, or grouping on the
   tracked object rather than the label.
4. **The row contract should gain `title`** (see finding 2).
