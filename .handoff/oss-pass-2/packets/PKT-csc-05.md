# PKT-CSC-05 — Turn admission and identity

Tier: **opus**   Milestone: **M3**   Effort: **M**
Collision lane: **A**   Merge order: **5/9 in A**
Verified against: halbert `main` @ `fbd725e9` (2026-09-11)

---

## 1. Packet

**CSC-05** — Turn admission and identity.

## 2. User problem

Turn admission in Halbert has three residual defects after R-01 (talk-door ordering/interrupt algebra), R-02 (claims/admission graph/channels), and R-08 (permission lattice/leases) merged. (1) A machine-originated turn — scheduler tick, heartbeat, watcher fire — has no declared ingress channel: `agents/channels.py` registers exactly DASHBOARD_CHANNEL, VOICE_CHANNEL, TERMINAL_CHANNEL, so any `system`/`scheduler` modality hits `ChannelRefused` fail-closed in `state_machine.py:630-640`, and historically (A09) an unknown modality silently entered the one seamless conversation as a typed admin turn, indistinguishable from the owner. (2) `POST /message` (`dashboard/routes/agent.py:1660`) has no idempotency key: `SendMessageRequest` carries message/session_id/images/max_tokens only, so a client retry after a dropped SSE stream re-enters `process()` and pays a second full generation for the same user intent. (3) A turn parked in `AgentState.AWAITING_CONFIRMATION` on a HIGH-risk approval holds its session and its claim on the turn lock; the next queued request's bounded wait (`TURN_LOCK_TIMEOUT_S = 600.0`, state_machine.py:262) burns while the owner reads the approval — the approval wait does not pause the clock. Supporting gap: there is one progress clock (`ctx.last_activity`, states.py:337, consumed only by the liveness watchdog at state_machine.py:2185 with TURN_STALL_SECONDS=900), but no stall notice reaches the surface — a turn quietly thinking for minutes gives the owner no measured "still working, last moved at X" signal, and AWAITING_CONFIRMATION is correctly exempted from the watchdog but its pause duration is not credited anywhere.

## 3. What to build

Build the RESHAPE-kept residual of deep-eval CSC-05, all in/around `agents/state_machine.py` plus small declared neighbours. (1) System channel: register a `SYSTEM_CHANNEL` ChannelDeclaration in `agents/channels.py` (id "system", default_role not admin — machine-originated, first-person "I" voice but never the owner's typed identity), so `resolve_channel("system"|"scheduler")` in `state_machine.py:630-656` admits scheduler/tick turns with honest provenance instead of refusing or masquerading as admin; CH-A (dependency, `InternalTurnSource`) supplies the cause axis this declaration hangs on. (2) Idempotency key on `POST /message`: add optional `idempotency_key` to `SendMessageRequest` (agent.py:39); the route records key→turn in-flight in a bounded dict on the agent (not persisted — no migrations), and a duplicate key while the original turn is live attaches the retry to the in-flight turn's stream instead of calling `process()` again; after the turn finalizes the key is replay-safe (returns the persisted result marker, never regenerates). (3) Approval-wait pauses the clock: when the machine enters AWAITING_CONFIRMATION (state_machine.py:4298 `_transition(AgentState.AWAITING_CONFIRMATION)`), record the pause start on ctx; a waiter in `_acquire_turn_lock` (state_machine.py:1061-1080) whose wait overlaps a confirmed-approval pause gets that pause duration credited — concretely, the 600s budget is measured against turn-active time, not wall time parked on approval. (4) Stall notice: reuse the existing `ctx.last_activity`/`touch()` clock — extend the watchdog loop (state_machine.py:2185) so that at a notice threshold below TURN_STALL_SECONDS (e.g. 120s idle, well under the 900s abort) it emits one measured status event ("still working — last progress: <last_activity_note>, <idle>s ago") onto the turn's event stream, single-shot per turn; no second clock, no new colour/emoji surface. Mid-turn input admitted with correct identity = a system-modality turn resolves SYSTEM_CHANNEL, is stamped channel=system, and never reads as the owner's typed admin turn.

## 4. What NOT to build

Per the RESHAPE verdict, do not build: the structured `clarify` verb (founder decision 8, deferred — goes to the M5b tail with P2's approval-presentation builder, which shares its question payload); the side-question mechanism (founder decision 4, deferred — same tail, ephemeral hidden thread); the per-turn tool-call budget (dropped per RESHAPE, low priority); the canonical tool policy projected onto MCP identities (dropped per RESHAPE, low priority — MCP work belongs to MCP-A/B/C units); replay-safety classification of tools (dropped per RESHAPE, medium — can follow as its own unit if wanted). Do not re-fix the A07-G1..G13 interrupt-algebra gaps (R-01 merged: steer-before-receipt, stop-during-tool, bare [steered] marker, stop-abort-in-flight-model via _model_call, second-steer, yield, watchdog, dashboard-stop-bypass), the A12-G6 IngressDecision gap or A09-G1 voice-injection gap (R-02 merged), or the general approval-lattice/lease work (R-08 merged — only the clock-credit residual above is in scope, and only after verifying R-08's lease code doesn't already credit it). No conversation list, no new user-facing surface beyond the one status event; no migrations or persisted idempotency store.

## 5. Target files
- `halbert_core/halbert_core/agents/state_machine.py`

## 6. Dependencies

CH-A

## 7. Effort

**M** — M is right: four tight, well-located mechanisms. The system channel is one ChannelDeclaration plus resolution coverage (channels.py, ~40 lines) but its correctness depends on CH-A's InternalTurnSource landing first (the declared dependency). The idempotency key touches the request schema, the route, and an in-flight registry keyed to the turn lifecycle with a finalize-time replay answer (~100 lines across agent.py/state_machine.py). The approval-pause clock credit is a small but delicate change inside the turn-lock acquire path where a wrong accounting deadlocks or double-credits (~40 lines plus tests). The stall notice is small precisely because `ctx.last_activity` already exists — it reuses states.py:337-347 and slots one branch into the existing watchdog loop (~30 lines). What keeps it from being S is the blast radius: `process()` is the single admission choke point for every turn in the product, and each mechanism must compose with R-01's interrupt algebra, R-02's channel layer, and R-08's approval state without regressing any of them — the deep-eval names this the hottest packet in the workstream.

## 8. UX rationale

One seamless conversation, no lists, no emoji, colours from shared-tokens — all preserved. The only new surface signal is the stall notice, rendered inside the existing turn stream as a measured first-person status ("Still working — last moved on planning, 2 minutes ago"), spoken as the computer itself and grounded in the real clock (`ctx.last_activity_note`, `idle_seconds()`), never a spinner or a guessed ETA. Scheduler/tick turns enter as system-channel turns: they speak in first person as the machine but are stamped so no surface ever confuses them with the owner's typed turn — consistent with the one-name, computer-as-speaker directive and founder decision 7 (declared non-admin channel). Idempotency is invisible: a retried send simply continues the same answer stream, so the owner never sees a duplicate reply after a network flap. Approval waits stop silently taxing the next message — the owner takes fifteen minutes to read a HIGH-risk confirmation and the next thing they type is answered normally instead of failing on an exhausted lock budget.

## 9. Acceptance criteria

(1) A turn submitted with modality "system" (or the CH-A InternalTurnSource equivalent) is admitted, resolves SYSTEM_CHANNEL via `resolve_channel`, writes its user row with metadata.channel="system", and never carries speaker_role admin — a machine turn is distinguishable from the owner's typed turn in the persisted thread. (2) Two `POST /message` calls bearing the same idempotency_key produce exactly one generation: the second attaches to the in-flight turn (or, after finalize, returns the persisted outcome) and the model client is invoked once. (3) A turn parked in AWAITING_CONFIRMATION for longer than a queued waiter's remaining budget does not kill the waiter: measured lock-wait time excludes the approval pause (next request admitted after confirm, not refused at 600s). (4) A turn idle past the notice threshold emits exactly one stall-status event containing the measured last_activity_note and idle seconds; a turn idle past TURN_STALL_SECONDS is still ended by the watchdog exactly as before; a turn in AWAITING_CONFIRMATION emits no stall notice and is not aborted (existing exemption holds). (5) No regression in R-01/R-02/R-08 behaviour: steer/stop semantics, channel fail-closed for unknown modalities, and approval confirm/reject paths all behave as on the merge-base.

## 10. Verification (measured state, not model judgment)

Runnable checks against measured state: `cd /Volumes/4TB-BAD/Halbert && arch -arm64 .venv/bin/python -m pytest halbert_core/tests -k "channel or admission or idempot or stall or awaiting_confirmation" -x -q` — plus the targeted new tests this unit adds, by ID: (a) a test that `resolve_channel("system").id == "system"` and `process()` with a system modality records metadata.channel="system" with non-admin role (asserts the ChannelDeclaration and the state_machine.py:630-656 resolution path); (b) a test that posts two `SendMessageRequest`s with equal idempotency_key and asserts the LLM client's call count is 1 and both responses carry the same session_id (in-flight replay); (c) a test that holds a turn in AWAITING_CONFIRMATION past a shortened TURN_LOCK_TIMEOUT_S (monkeypatch the constant) and asserts the queued waiter is admitted after confirm rather than timing out (exit state, not wall clock); (d) a watchdog-loop test with TURN_STALL_SECONDS and the notice threshold monkeypatched to ~0 that asserts exactly one stall event with the measured note is emitted and an AWAITING_CONFIRMATION turn emits none. Baseline first: main is not green — run `arch -arm64 .venv/bin/python -m pytest halbert_core/tests -q` on the merge-base before and diff failures; this unit must add zero new failures. From the worktree, use `arch -arm64 ./wt_pytest.py halbert_core/tests` instead.

## 11. Exclusions

Deferred to the M5b tail: the `clarify` verb (founder decision 8 — its question payload should be built with the shared approval-presentation builder alongside P2's fence helper, not here) and the side-question mechanism (founder decision 4 — ephemeral hidden thread, needs the founder ruling ratified first). Dropped per RESHAPE: the per-turn tool-call budget, the canonical tool policy projected onto MCP identities (MCP-surface policy belongs to the MCP-A/B/C units if anywhere), and replay-safety classification of tools (may return as its own small unit). Already-merged work explicitly out of scope: A07-G1..G13 interrupt algebra (R-01), A12-G6 IngressDecision + A09-G1 voice-injection (R-02), approval lattice/leases/halt (R-08) — the approval-pause clock credit must first verify R-08's lease code doesn't already handle it, and if it does, that sub-item is dropped as a duplicate, not rebuilt. The opaque conversation address from transport identity (session_affinity regex defect) noted in the deep-eval's "what it proposes" is not in the kept-residual list — if it survives triage it belongs to a separate unit, not this one.

---

## OSS reference

Greenfield — no direct OSS reference; see the deep-eval.

## Repo traps

- Every Python test run needs the `arch -arm64` prefix: `arch -arm64 .venv/bin/python -m pytest halbert_core/tests`.
- From a git worktree use `arch -arm64 ./wt_pytest.py halbert_core/tests`, NEVER bare pytest (the editable install pins halbert_core to the MAIN tree).
- `main` is NOT green. Known-red baseline (2026-09-11): test_agent_model_override.py, test_agent_model_selected_event.py, test_no_model_names_in_user_facing_source.py, test_num_ctx.py (~23 failures). A failure is yours iff absent from this baseline.
- Work in a git worktree; narrow commits; concurrent sessions edit this repo.
- NEVER add Co-Authored-By or 'Generated with …' trailers. Subject + body only.
- No emoji anywhere. Colours only from shared-tokens/tokens.css (run scripts/check_contrast.py).
- Never name/recommend an AI model on any user-facing surface; connection slots, not model menus.
- Model locality: is_local_model() (model/llm_config.py:181) is the ONLY judge; :cloud tag is primary.
- Feature gating: has_capability() (capabilities.py:499); never _is_home_variant.
- Redaction: ingestion/redaction_registry.py enforced at security/display_transport.py; scrub BEFORE the model.
- Commands staged from the UI are staged, never executed.
- No users yet: no migrations/back-compat shims unasked; leave superseded data on disk, unread, never delete.
- Line references drift: re-anchor by grep before editing; a failed anchor is a rebase signal, not a spec change.
- Modify only this packet's Target files. .handoff/ is correspondence, not authority (ROADMAP.md + DECISIONS.md are the spine).
