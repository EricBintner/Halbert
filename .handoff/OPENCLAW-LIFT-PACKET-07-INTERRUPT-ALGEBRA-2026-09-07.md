# OPENCLAW-LIFT-PACKET-07 — The interrupt algebra: stop / steer / redirect

**Series:** Hermes-derived packet 2 of 4 (master plan: `OPENCLAW-LIFT-MASTER-PLAN-2026-09-07.md`)
**Source research:** `.handoff/OSS-REVIEW-HERMES-2026-09-07.md` §2
**Hermes source of record:** `/Volumes/Thunderbolt/AI/OSS/hermes-agent/agent/interrupt_control.py` (the whole algebra), `gateway/run_inbound.py:599-651` (busy-mode decision tree), `tui_gateway/session_auto_continue.py:234`
**Executor tier:** Phase A pure — small-model friendly. Phases B–C touch the live state machine — medium, verify-first, review before merge.
**Status:** READY TO DISPATCH (Phase A); B–C after A merges and its verify-first findings are recorded

---

## Objective

Halbert today has exactly one mid-turn behavior: the heartbeat skips while `_turn_lock` is held, and the dashboard has no verb for "the agent is busy and I typed." Hermes's review produced a proper **interrupt algebra** — three protocol verbs with distinct safety properties:

- **interrupt (stop)** — hard stop, with a **generation claim**: the abort publishes only if the turn's activity-generation still matches at the final mutation edge, so an abort that loses the race to a finishing turn *declines* instead of double-firing.
- **steer** — never interrupts: user text is appended to the **last tool result** once the current tool batch finishes (multiple steers concatenate).
- **redirect** — the middle ground: cancels the current model request only (completed work kept, partial output becomes context, the correction appended as a real user message, loop retries); during a tool call it degrades to steer and asks the tool to **yield, never kill**.

Plus one shared lock so a stop can never race an accepted correction into a retry, and demotion rules (interrupt → queue when a turn-critical subsystem is mid-flight).

## Verified current state (do not re-derive; verified 2026-09-07)

- Turns are serialized by `routes/agent._agent_instance._turn_lock`; the heartbeat's `_agent_turn_busy()` checks it (`dashboard/app.py:306-439`).
- The state machine: `agents/state_machine.py` — `process()` (~502, speaker_role default), `IDLE→PLAN→…→RESPONDING` states, `_handle_planning` at :1939, `_handle_responding` (~3313, guest forwarding), `speaker_role` threading at ~403/502/2752.
- The dashboard turn surface: `POST /api/agent/message` SSE (`routes/agent.py:1532`); no busy/queue/steer surface exists today.
- **Not yet mapped (Phase B must verify):** Halbert's current abort paths inside the state machine (whether any exist, how tool batches iterate, where the model request is made and whether it's cancellable). Do not assume; map first.

## Out-of-scope guards

- No new conversation-fork machinery (Hermes's cache-parity fork is an anti-pattern per the review; Halbert's steering stays inside the state machine).
- No per-channel busy modes yet (interrupt/queue/steer as a dashboard setting) — Phase C records the decision; the verbs land first.
- Do NOT copy Hermes's queued-envelope rescue/merge machinery (~three overlapping queue structures) — Halbert needs exactly one pending slot per session with replace-not-grow semantics.
- Voice: interrupt-with-transcript is already recorded in PACKET-04's addendum; this packet exposes the verbs, not the voice wiring.

---

## Phase A — the algebra as pure mechanics (small-model friendly)

**Branch:** `feat/interrupt-algebra` off `main`.

### Task A1: Generation claims

**Files:**
- Create: `halbert_core/halbert_core/agents/turn_activity.py`
- Test: `halbert_core/tests/agents/test_turn_activity.py`

- [ ] **Step 1: Write the failing tests**

```python
"""Activity generations: a cross-thread cancel that loses the race to a
finishing turn must DECLINE, not double-fire (Hermes require_generation)."""
from halbert_core.halbert_core.agents.turn_activity import TurnActivity

def test_fresh_claim_publishes():
    act = TurnActivity()
    gen = act.stamp()
    assert act.claim(gen, lambda: "published") == "published"

def test_stale_claim_declines():
    act = TurnActivity()
    old = act.stamp()
    act.stamp()  # the turn moved on
    fired = []
    assert act.claim(old, lambda: fired.append(1)) is None
    assert fired == []

def test_claim_is_single_shot_under_lock():
    act = TurnActivity()
    gen = act.stamp()
    results = [act.claim(gen, lambda: "x") for _ in range(2)]
    assert results.count("x") == 1
```

- [ ] **Step 2: Run, verify failure.** **Step 3: Implement** — `TurnActivity` with a `threading.Lock`, a monotonically increasing generation, `stamp()` returning the current generation, and `claim(gen, fn)` executing `fn` under the lock iff `gen == current` (exactly once).

- [ ] **Step 4: Run, verify pass. Commit:** `feat(agents): turn activity generations for race-safe cancellation`

### Task A2: The three verbs as a decision core

**Files:**
- Create: `halbert_core/halbert_core/agents/steering.py`
- Test: `halbert_core/tests/agents/test_steering.py`

- [ ] **Step 1: Write the failing tests**

```python
"""The decision core: which verb applies to a mid-turn arrival, and its
invariants. Pure; the state machine supplies the predicates."""
from halbert_core.halbert_core.agents.steering import decide_midturn, Verdict, apply_steer_to_results

def test_idle_arrives_as_normal_turn():
    v = decide_midturn(turn_active=False, is_command=False, text="hello")
    assert v.verb == Verdict.NORMAL_TURN

def test_busy_command_bypasses():
    v = decide_midturn(turn_active=True, is_command=True, text="/stop")
    assert v.verb == Verdict.STOP

def test_busy_text_steers():
    v = decide_midturn(turn_active=True, is_command=False, text="also check the logs")
    assert v.verb == Verdict.STEER

def test_stop_and_redirect_share_safety():
    # a stop accepted at the same edge as a redirect must not produce a retry:
    # one lock decides; second caller sees the decided state
    v1 = decide_midturn(turn_active=True, is_command=True, text="/stop")
    v2 = decide_midturn(turn_active=True, is_command=False, text="do this instead")
    assert {v1.verb, v2.verb} <= {Verdict.STOP, Verdict.STEER}

def test_steer_appends_to_last_tool_result():
    results = [{"name": "recall_memory", "output": "ok"}]
    apply_steer_to_results(results, "also check the logs")
    assert "also check the logs" in results[-1]["output"]
    apply_steer_to_results(results, "and the camera too")
    assert "and the camera too" in results[-1]["output"]  # steers concatenate

def test_interrupt_demotes_when_unsafe():
    v = decide_midturn(turn_active=True, is_command=True, text="/stop",
                      tool_batch_in_flight=True)
    assert v.verb == Verdict.STEER  # never kill a tool to deliver guidance; queue/steer instead
```

- [ ] **Step 2: Run, verify failure.** **Step 3: Implement** — `Verdict` enum (`NORMAL_TURN, STOP, STEER, REDIRECT`), `decide_midturn(...)` with the invariants above as explicit branches (comments name each rule and its Hermes source), `apply_steer_to_results(results, text)` appending with a `\n[steered] ` marker to the last tool result only. `REDIRECT` is decided when the state machine reports it is inside a model request (Phase B wires that predicate; A returns REDIRECT only if `in_model_request=True` is passed).

- [ ] **Step 4: Run, verify pass. Commit:** `feat(agents): stop/steer/redirect decision core with demotion rules`

---

## Phase B — state-machine integration (verify-first; review before dispatch)

**Before any edit:** map and record (in the master plan status row) — (1) where the state machine iterates tool batches; (2) where the model request is made and whether it is cancellable (if the provider client exposes no cancellation, REDIRECT degrades to STEER + a post-completion correction turn — write that in the packet's handoff, don't invent cancellation); (3) every existing abort path.

- [ ] **Task B1:** Thread a `TurnActivity` through the running turn (`process()` stamps on start; RESPONDING finalize stamps again). Surface `/stop` on the dashboard agent route: `STOP` verdict → generation-claimed abort of the running turn.
- [ ] **Task B2:** Mid-turn message arrivals while `_turn_lock` is held: route through `decide_midturn`; STEER → `apply_steer_to_results` at the next batch boundary; the pending slot is a single replace-not-grow slot per session.
- [ ] **Task B3:** The generation-claim race test at the integration level: a stop issued as the turn completes produces either "turn completed, stop declined" or "stopped", never both, never a retry.
- Tests at each step; suites: agents + dashboard. Commit per task.

## Phase C — recorded decisions, not work

- Per-channel busy modes (interrupt vs queue as a dashboard/voice setting); burst-tolerance windows (Hermes queues <3s bursts rather than interrupting); demotion rules for compression-in-flight (relevant when the session-tree work lands); queued-message editing UI. All deferred until the verbs exist and usage says which defaults matter.

## Verification gates (whole packet)

- Phase A: pure suites green; `cd halbert_core && arch -arm64 ../.venv/bin/python -m pytest tests/agents -q`.
- Phase B: the race test; the heartbeat's `_agent_turn_busy()` still works unchanged; guest forwarding paths unaffected (run the persona suite).
- No mid-turn arrival can ever be silently dropped — an arrival while busy always yields a verdict the user can observe (steer confirmation line, stop confirmation, or queue slot), pinned by test.

## Executor gotchas

- Standard set: arch-arm64 pytest (main checkout) / `wt_pytest.py` (worktrees); pathspec commits; no co-author trailers.
- The state machine file is large (~3k+ lines); read the specific handler regions before editing and match its existing locking idioms — do not introduce a second lock where `_turn_lock` discipline already applies.
- SSE event vocabulary is frontend contract: any new event types (steer-accepted, stop-declined) must be added to the frontend types and rendered, or explicitly marked as backend-only in the handoff.