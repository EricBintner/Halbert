# DISPATCH: Observation Lenses — model tier and effort per work item

**Date**: 2026-09-05
**Covers**: `.handoff/HANDOFF-OBSERVATION-LENSES-2026-09-04.md` (rev 2) §7–§9 tasks and §14 branches
**Base**: main `8a47c62e`. The handoff was verified against `44fc501e`; the four commits since
touch `.handoff/9-4-todo.md`, `ConfirmationDialog.escaping.test.ts`, `streaming/agent_pool.py`
and `tests/test_agent_pool_reaping.py` only — **no anchor file in the plan moved, so every line
number in it is still live.** No re-verification pass is needed before branches 1 and 2.

---

## 1. The scale, and what puts an item in each band

**Tier is decided by what a wrong answer costs, not by how much code there is.**

| Tier | Takes | Why |
|---|---|---|
| **Opus** (this session) | Trust boundaries, safety classification, store-shape choices that destroy data, anything that puts new text into `messages[0]`, anything constraining a model call — plus any item whose spec still contains a fork | These fail *silently*. DEFECT-2 is the house example: a dead `hasattr` branch, test-green on a `MagicMock`, losing every observation for months |
| **Sonnet** | Bounded implementation against a complete spec with a named failing test | The handoff already writes a **Verification** line for nearly every one of these. That line is what makes them dispatchable — no judgment is left in the task |
| **Fable** | Prose, voice, taste; broad-corpus verification sweeps; keeping the plan documents true as branches land | It wrote and verified the doc. The remaining fable work is writing, not code |

**Effort** is the second dial, independent of tier:

| Effort | Means |
|---|---|
| `med` | One file, one mechanism, spec is complete. No design left |
| `high` | Several call sites or one non-obvious trap that is already named in the doc |
| `xhigh` | A contract other code will depend on, or a behaviour change that lands the moment it merges |
| `max` | Get it wrong and something silently unsafe or unrecoverable ships |
| `ultracode` | Multi-agent fan-out. **Reserved for reviewing landed implementations, not for building.** Cap the fan-out (see §6) |

---

## 2. Assignment

### Track A — close the observation loop

| Item | What | Tier | Effort | Branch | Blocked on |
|---|---|---|---|---|---|
| **A0-code** | `get_timeline_store()` beside `get_trackers()`; path via `utils.paths.data_dir()` (it exists, :53); inject at `cognition_wiring.py:477,500` and `dashboard/app.py:1090`; `get_frigate_event_mapper()` takes `is_mqtt_configured()` | **Sonnet** | high | 1 | — |
| **A0-privacy** | Name the ledger in `ERASURE_LIMITS` (`continuity/provenance.py:316`); decide person-keyed erasure for `occupancy_change` rows (`timeline_events` has no `request_id`) | **Opus** | high | 1 | decided here, §3.4 |
| **A1** | Move to `continuity/timeline.py`; shim or fix `test_timeline_store.py:9` / `test_behavior_store.py:18` **in the same commit** | **Sonnet** | med | 1 | — |
| **A2** | Ingestion-time sink; the row contract exactly as written (one row per Frigate message, affect strings are never a second row); log the 500-cap drop with a count | **Sonnet** | xhigh | 1 | §3.1 (VIGILANCE) |
| **A2b** | `SystemEventMapper.populate_cognition()` records each drained event before applying it | **Sonnet** | high | 1 | §3.2 (scope) |
| **A2c** | Normalise + redact at the sink; raw only in `data`, never rendered | **Opus** | xhigh | 1 | — |
| **A3** | State vs event routing across the twelve HA sites; new predicates into `RE_OBSERVABLE_PREDICATES`; PROBE semantics for an HA subject; `decide()` on the answering path, never in recall | **Opus** | **max** | 3 | branch 1 |
| **A4** | World rows into `STATE-1`'s Eyes block at both render points | **Sonnet** | xhigh | 3 | §3.3 (`[t{id}]`), CD-10 |
| **A5** | `count_by_entity()` — `GROUP BY entity_id`, `json_extract(data,'$.type')='new'` | **Sonnet** | med | 3 | A2's row contract |

**Why A3 is the one `max` in Track A.** `StateStore.record_state()` dedups by design; route an event
into it and the recurrence this whole plan is built on is destroyed at the store's core invariant —
and the doc's own warning ("do not embed a timestamp in the object value to defeat the dedup") is
exactly the shortcut a model under pressure takes. It also decides `freshness.decide()` behaviour for
a stale lock row, and `write_guard.py` kept freshness out of recall on purpose.

### Track B — wire skills, add the lens kind

| Item | What | Tier | Effort | Branch | Blocked on |
|---|---|---|---|---|---|
| **B1** | Matcher from `builtin + ~/.config/halbert/skills`; **no cwd**; same-name override refused/flagged; skill dirs into `SENSITIVE_PATHS` with the literal-`~/.config/` bug fixed (`tools/safety.py:289`); acceptance checks for the three routing side effects that go live with it | **Opus** | xhigh | 2 | CD-6 ✅ |
| **B2** | Inject `composed.prompt` at `_build_messages` (`state_machine.py:1605-1606`), **with the cap** | **Opus** | high | 2 | B1 |
| **B3** | Skill safety per turn on `self.tools.safety`; cleared in the turn's `finally`; re-installed on `confirm_action()` resume; `cwd` classified; substring fallback anchored to the first token | **Opus** | **max** | 2 | B1 |
| **DOCS-1** | Correct `ROLE-SCOPED-SKILLS-2026-08-27.md` §11/§12 status claims | **Sonnet** | med | 2 | — |
| **B4a** | `suppress_lens()` on signals that exist today, at the assemble call, both paths | **Sonnet** | xhigh | 5 | CD-9 |
| **B4b** | `is_destructive` / `is_incident` on `MessageSignals`; the entity ∩ finding join | **Opus** | high | pre-C2 | CD-9 |
| **B5** | `kind: flavor` + `suppress_on` in the frontmatter schema; the "a lens never rides `active_skills`" carve-out through four call sites | **Opus** | high | 5 | CD-2, CD-3, **CD-11** |
| **B6** | `flavor_intensity` + `active_lens` on `BeingConfig`, four touch points each, plus the BeingTab control | **Sonnet** | med | 5 | CD-2, CD-11 |
| **B7** | Write the one built-in lens; teach `test_skills_builtin.py:39,44` about kinds | **Fable** | high | 5 | CD-3(b), CD-11 |

**Why B3 is `max`.** `_check_skill_safety` failing open means a skill-declared CRITICAL command runs
without confirmation. It has to install on the executor's framework (the one `RoleGate` wraps, so both
branches of `executor.py:448-453` see it), clear in the same `finally` that releases `turn_lock`, and
survive a `confirm_action()` resume. Then it closes the `cwd` channel — the same class of bypass
`44fc501e` just closed for the base classifier, four commits ago. This is not a Sonnet task.

**Why B1 is `xhigh` and not `high`.** It is the trust boundary for an instruction source
(invariant 8), and it changes live behaviour the moment it merges even before B2 exists: model tier
to the specialist slot, a `ContextBudget` reshuffle, and SourcePrep retrieval narrowing. `storage-ops`
declares `model: specialist`, budget 1.6.

**B7 is the one genuinely fable-shaped code-adjacent item.** It is a voice exercise with a hard
constraint list ("one sentence, never two"; no canon list; no analogy bank; under CD-3(b), not even a
"what this lens notices" section). Taste, in a house style, under restraint — and the founder
directive that the product never names or recommends AI models bounds it.

### Track C — the surface

| Item | What | Tier | Effort | Branch | Blocked on |
|---|---|---|---|---|---|
| **C0-gate** | Clean-day report passes at Balanced (CD-8 recommends the gate exemption) | **Sonnet** | high | 4 | CD-8 |
| **C0-persist** | `C2-10`: a reports store readable after restart, plus a view that renders the full body | **Sonnet** | xhigh | 4 | — |
| **C1a** | `observations_provider` on `MorningReportGenerator`; `## Noticed (last 24h)` with row ids, before any summarizer | **Sonnet** | high | 4 | A5 |
| **C1b** | The lens voice: pinned `secure_model`, `:cloud` rejected **by tag**, scrub→model→scrub, turn-lock try-acquire, contract changed from whole-body rewrite to a spliced flavor over the Noticed section | **Opus** | **max** | 6 | CD-7 **and** `C4-07` ratified |
| **C2** | Recurrence remarks in a live turn | **Opus** | xhigh | after | B4b + a week of persisted reports |
| **C3** | `/api/skills` with source directory shown; raw markdown via `/api/editor/file`; provenance affordance; no `dangerouslySetInnerHTML` | **Sonnet** | high | after | — |

**Why C1b is `max`.** It is the only model call in the plan, it runs unattended on a schedule, and it
sits on top of two standing rulings: scrub deterministically *before* the model, and pin local —
never `:cloud`. The doc's own reason for rejecting option (c) is that a whole-body rewrite can drop a
critical finding while the report still carries a `critical` label.

### Cross-cutting

| Item | Tier | Effort | Note |
|---|---|---|---|
| Re-anchor the doc against current main | — | — | **Done in this session: no anchor file moved since `44fc501e`** |
| CD-5-sub (preference writer + research ingestion: carry or defer) and **CD-11** (nomenclature) memos | **Fable** | high | The only two open decisions still needing argument rather than ratification |
| Keep §14 / ROADMAP status columns true as branches land | **Fable** | med | Ongoing |
| Adversarial review of the *landed* branch-1 and branch-2 implementations | **ultracode** | — | §6 |

---

## 3. Four forks closed here, so branch 1 ships to Sonnet fork-free

### 3.1 VIGILANCE → `ANTICIPATION`. Do not extend the enum.

`EmotionCategory` (`Haloysius/src/haloysius/persona/emotional_state.py:23-37`) is Plutchik's wheel,
closed on purpose, plus named secondary dyads. **Plutchik's own model defines vigilance as the
high-intensity form of anticipation** — so the mapping is the model's semantics, not a fudge. It needs
no cross-repo enum change and no mood-map entry, which is the difference between a one-line fix inside
branch 1 and a Haloysius change with its own review.

Apply at `frigate_event_mapper.py:223,248,258,262,267` and `system_event_mapper.py:194,220`; fix
`skills/builtin/frigate-ops/SKILL.md`, which documents `VIGILANCE` as real; un-mock `_add_emotion` in
the tests; log emotion-write failures at WARNING, rate-limited.

### 3.2 A2b's scope: DetectorRunner → `add_event` is **out** of branch 1

Rewriting `_scan_discovery` / `_check_critical_conditions` against `DiscoveryEngine` methods that
actually exist is its own investigation, not a line in a sink branch. Branch 1 states it as a
dependency and it opens as a follow-up under `MIND-1` `C4-04`. Consequence to write into the branch's
RESULTS row honestly: **a sysadmin ledger receives only VisualWatcher anomalies until that lands.**

### 3.3 Provenance ref format: `[t{id}]`, pinned now

`observation_id` is already in use for retrieval ids at `state_machine.py:3617-3621`, and the NOTE at
:3623-3626 records that plain strings cannot be cited. Ledger refs get the `t` prefix and emit
`ProvenanceRef(type="observation_id", ref="t{id}")`. Pinning this makes A4 mechanical, which is what
moves it from opus to Sonnet.

### 3.4 Person-keyed erasure — the one I am not closing by fiat

`timeline_events` has no `request_id`, so `forget` cannot reach an occupancy row the way it reaches
the change ledger. Two honest options: erase by `entity_id` match for `occupancy_change` and person
rows, or name the event ledger in `ERASURE_LIMITS` as a plane `forget` does not reach. `ERASURE_LIMITS`
is user-facing text asserting what erasure *does*, so this must be settled before branch 1 merges, not
after. **A0-privacy stays opus and I take it with branch 1.**

---

## 4. Work orders

### To Fable (hand back to the doc's author)

1. **B7** — the one built-in lens file, plus the two `test_skills_builtin.py` edits. Blocked on CD-11.
2. **The CD-11 memo** — naming. It has real consequences (`~/.config/halbert/<name>/`, the frontmatter
   `kind:` value, every UI string, C3's route) and it gates B5/B6/B7. §10 D10 already lists five
   candidates; what is missing is a recommendation the founder can ratify in one read.
3. **The CD-5-sub memo** — carry or defer the preference writer (no `remember`-shaped tool is
   registered in `tools/executor.py` today) and research ingestion. The default in flight is *deferred
   until C1a ships*; that needs to be stated with a reason or overturned, because it is the founder's
   requirement of record and rev 1 already dropped it once.
4. **Ongoing** — §14 and the ROADMAP status columns as branches land.

Not fable work: everything else. The doc is done; the remaining verification sweep is unnecessary
(see the base note in the header).

### To Sonnet

**Branch 1 body** — A0-code, A1, A2, A2b (opus supplies A2c as a called function, and takes
A0-privacy). Hand it: handoff §7 A0–A2b, §14 Branch 1's done-evidence list, and §3.1/§3.2 above.
Effort `xhigh` on A2 because its row contract is what A5 counts.

**Then, in order as their branches open**: A4 + A5 (branch 3), C0-gate + C0-persist + C1a (branch 4),
DOCS-1 (branch 2 housekeeping), B6 + B4a (branch 5), C3 (after).

Two standing rules for every Sonnet task here, both from the doc's invariant 4:
- **Never a `MagicMock` cognition.** Real `PersonaCognition`, real `TimelineStore`. That single habit
  is what hid DEFECT-2, and `test_frigate.py:249,288,326` are the false positives to rewrite.
- Run only the branch's named test files from the repo root, prefixed `arch -arm64` — never the whole
  suite in the review loop.

### To Opus (here)

**Branch 2 in full — B1 + B2 + B3 — is the natural thing to start.** It is entirely opus-tier, it is
independent of branch 1 so it runs in parallel with Sonnet, and it needs only CD-6, which is decided.
Its payoff is the largest single one in the document: eight written expert skills begin working the
moment B2 lands.

Then, in dependency order: A2c and A0-privacy (into branch 1), A3 (branch 3), B4b, B5, C1b (branch 6).

---

## 5. Sequencing

Branches 1 and 2 are independent and start now, in parallel — Sonnet on 1's body, opus on 2.
A2c and A0-privacy land into branch 1 from this session before it merges.

```
Sonnet ──▶ branch 1 body (A0-code, A1, A2, A2b) ──┐
Opus   ──▶ A2c + A0-privacy ──────────────────────┴──▶ branch 1 merges
Opus   ──▶ branch 2 (B1+B2+B3) ─────────────────────▶ merges independently
                                    │
        branch 3 (A3 opus, A4/A5 sonnet) ◀──── needs branch 1
        branch 4 (C0, C1a — sonnet)      ◀──── needs branch 1 + CD-8
                                    │
        ══ founder gate CD-1: open LENS-1, or leave in Next ══
                                    │
        branch 5 (B5 opus, B6/B4a sonnet, B7 fable) ◀── CD-2, CD-3, CD-9, CD-11
        branch 6 (C1b — opus)                       ◀── CD-7 + C4-07 ratified
```

Fable's CD-11 memo is on the critical path for branch 5 and nothing earlier, so it is not urgent —
but B5, B6 and B7 all three touch the name, so it must land before any of them start, not during.

## 6. Not dispatched, deliberately

- **Nothing goes to ultracode yet.** Fan-out belongs on landed code, not on a plan that has already
  survived a 155-agent pass. After branches 1 and 2 merge, one review pass over the two diffs is
  worth it — deduped first, three lenses on high findings and one on medium, well under the cap.
  A previous run at 3 refuters × 85 findings exhausted a session's budget; do not repeat that shape.
- **C2** (remarks in a live turn) stays unassigned until a week of persisted Noticed sections exists
  to judge from. That is the doc's own gate and it is the right one.
- **The six open CDs** are ratification, not analysis, except CD-5-sub and CD-11 — both above.
