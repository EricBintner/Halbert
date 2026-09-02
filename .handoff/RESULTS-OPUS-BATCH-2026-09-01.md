# RESULTS — Opus packets 01–05, one session (2026-09-01)

> **Branch:** `fix/opus-packets-2026-09-01`, 26 commits off `main` = `941cc14b`.
> **Scope:** all five Opus dispatch packets, worked sequentially in one session rather than five parallel worktrees. Commits are scoped by finding and by file, so any subset can be cherry-picked; nothing in one packet's commits touches another's files except where a finding genuinely spans them (noted below).
> **Baseline note:** `main` had moved from the audit's `4a7bf71f` to `941cc14b` (six shell-redesign commits). Python was untouched by that merge and the 71-failure baseline reproduced **byte-identically**, so the audit's list held.

---

## 1. Headline

| Gate | Before | After |
|---|---|---|
| Python suite | 71 failed / 4,509 passed | **26 failed / 4,679 passed** |
| New failures introduced | — | **zero** (diffed against the baseline list every run) |
| dashboard frontend | 699 passed, `tsc` clean | 715 passed, `tsc` clean |
| design-system | 70 passed | 70 passed |
| model-picker | 103 passed | 103 passed |

**All 26 remaining failures belong to Sonnet packets** and none is in Opus scope:

- 13 — `test_cv_extensions` (11) + `test_vision_tools` (2): the missing `vision` extra → **SONNET-05**
- 10 — `test_llm_routes` (4), `test_llm_config_layers` (2), `test_llm_config_parse_cache` (2), `test_llm_discover` (1), `test_multi_instance` (1): CapabilityRegistry pollution and test rot → **SONNET-03** / **SONNET-05**
- 2 — `test_corpus_license_gate`: dependency-licence manifest → **SONNET-05**
- 1 — `test_frontend_no_relative_urls`: `peerApi.ts` bare URLs → **SONNET-04**

---

## 2. What landed, by packet

### OPUS-01 — agent core (complete)

| Finding | Commit | Note |
|---|---|---|
| `R06-F2` response_modality UnboundLocalError | `58863b5e` | Hoisted above the branch. Cleared 24–33 tests. |
| `R06-F1` defanged query leaks into the next turn | `e0052bce` | Fixed at the class it belongs to — moved onto `StateContext`, which `process()` rebuilds per turn — rather than by moving the reset. The leak is now structurally impossible and cannot be reintroduced by an edit that moves a line. It also crossed *sessions*, not only turns: one machine instance serves them all. |
| `R04-F8`, `R06-X1`, `SE-11` test drift | `902c485c` | The `speaker_role` drift had left the terminal-bridge e2e guard dark, not merely red. |
| `R06-F3` SEARCHING ignores the scope + `R06-F8` bare `except TypeError` | `90207b55` | One seam, two halves. Both now use shared helpers in `context/assembler.py`; scope support is decided by `inspect.signature`, so a TypeError raised *inside* a scope-aware adapter can no longer be read as "takes no scope" and retried over everything. |
| `R06-F4` chmod excluded from rollback | `5e090cf5` | The undo is now recorded on the line after `os.chmod`. Fixing it exposed the same shape one level down — a rollback's own audit write could drop a *completed* undo out of `rolled_back`. The two directions want opposite policies and now get them. |
| `R06-F5` `merge_thread` orphans rows | `2d99bc27` | Three tables, not the two named: `compact_boundaries` is the same shape and costs nothing to move now. |
| `R06-O2` substituted tools, `R06-O1` mispaired ReAct observations | `2857a641` | `react_agent.py` had no tests at all; the three added fail on the old code. |
| `R06-F6` (state-machine side) | — | Already correct: `process()` releases the lock from a `finally` and lock acquisition is bounded at 600 s. The real fix was the Wyoming call site — done in OPUS-02 (`8e18a93c`). |

### OPUS-02 — voice chain (Tasks 1–6; 7–9 below)

| Finding | Commit |
|---|---|
| `U2-15`/`R9-F05` production can never resolve VOICE | `65ff3e83` |
| `R9-F01` Wyoming unauthenticated on `0.0.0.0:10400` | `65ff3e83` |
| `R3-F04`/`R9-F10` audio-chunk framing | `65ff3e83` |
| `R3-F10b` `Server.aclose()` on 3.10 | `65ff3e83` |
| `U2-05` raw markdown to HA TTS | `65ff3e83` |
| `R9-F03`/`U2-14` VAD frame size | `409fc509` |
| `R9-F04` enrolled voiceprints never loaded | `409fc509` |
| `VM-STT` spoken input never becomes a turn | `9ec19f8a` |
| `R9-F02` second event loop, `R06-F6` aclosing, `U2-07` `<speech>` defang | `8e18a93c` |

Two of these deserve calling out:

- **`U2-15` was the keystone.** `HalbertChannelCapability` decides whether Halbert can speak, and the seam builds it with no arguments — so it resolved the pipeline through a lazy import of a function that did not exist. `has_speaker()` was permanently False and everything downstream was unreachable. Every existing capability test injected a pipeline at construction, which is exactly why the production shape stayed dark.
- **`VM-STT` needed no new endpoint.** The browser already holds the mic uplink open and that socket is bidirectional; it was only ever read upward. The transcript now comes back down it, so the status endpoint keeps its contract (who spoke, not what was said).

### OPUS-03 — compute peer, devices, pairing

| Finding | Commit |
|---|---|
| `ROUTE-01`/`R10-N1` Devices API 404, `R10-F5` (devices half) | `1f3b68fc` |
| `SE-16`/`R10-F1` self-service pairing, `R10-F5` (peer half) | `7dc93e68` |
| `SE-09`/`R10-F2` compute endpoint, `SE-08`/`R10-F3` health path | `92cf9868` |
| `R05-F1` peer turns raise on the scheme | `e7bcf029` |
| `FED-01`/`R10-F10`/`R10-F11` 500s on unbuilt surfaces | `0175377d` |

**Two bugs the new tests found rather than confirmed:**

1. `mcp_response` was applied to the whole compute response envelope. It is secret-key-aware and every usage counter is named `*_tokens`, so `prompt_tokens`/`completion_tokens`/`total_tokens` all came back `"<secret>"` and then failed integer validation — the happy path would have 500'd on the first real peer turn, on code that had never been executed. Redaction now covers the model's text; counts are integers and cannot carry a secret.
2. `test_peer_redaction`'s skipped compute-endpoint test asserted that prose saying a password out loud would be redacted. `redact_text` does not claim that and does not do it. Rewritten against the shapes the boundary actually covers (PEM blocks, JWTs, credentials in URLs).

### OPUS-04 — terminals (Tasks 1–3; 4–5 are founder calls, §4)

| Finding | Commit |
|---|---|
| `R04-F1` reaper kills live user terminals | `426b3be2` |
| `R04-F3` pool leaks busy slots, `R04-F4` unbounded block output | `0a35c1b2` |
| `R04-F7` unbounded `/exec`, `R04-F10` stale-thread guard, `R04-F11` dead emitter, `TERM-10` dead history route | `e8358ed5` |
| `R04-F5` `kill()` blocks the loop, `R04-F6` unbounded fan-out, `R04-F13` fd leak | `98662c4a` |
| `R04-F12` post-SIGKILL zombie | `ec924bbc` |

`R04-F10` was implemented rather than documented away: `tick()`'s docstring has promised the live-terminal guard since Plan B and `_close_due` never had it, so a thread whose command was still running got summarised and put away under the user.

`ec924bbc` also fixes a bug in `98662c4a`, one commit earlier: `kill()` sets `_exited` unconditionally on its way out, so a deferred escalation that tested `_exited` was a guaranteed no-op. The child still died in practice — closing the PTY master SIGHUPs it — which is why that needed a test watching the reap rather than the corpse.

### OPUS-05 — chat streaming hook

| Finding | Commit |
|---|---|
| `R11-01` every completed turn cancels itself | `c099be47` |
| `R11-02` queued send drops pending approvals | `edb36d25` |
| `R11-03` impure updater, `R11-13` callback churn | `9cfb10c2` |
| `R11-12` re-parsing every frame, `R11-10` overlapping loads, `R11-04`, `R11-05`, `R11-06`, `R11-09` | `689f5f78` |
| `R11-11` composer claims a popup that is not rendered | `7dce8e58` |

`R11-01` was worse than "a stray POST": an explicit stop sent **two** cancels, and a normal completion sent one that the backend can persist as a cancelled reply. No test referenced `/api/agent/cancel` at all.

`R11-10`'s abort half is not done. `useTimeline` shares `api.ts`, which is not this packet's file and is used by many components; the shared `inFlight` flag — the part that silently dropped "Try again" — is fixed in-file with request tickets, which also makes a stale response harmless. Adding an optional `signal` to `api.getTimeline` is a one-line follow-up for whoever owns that file.

---

## 3. Deliberately not done

| Item | Why |
|---|---|
| `CUA-04` adopt `react-markdown` + `remark-gfm` | Adds an unregistered dependency to a repo whose licence gate is already red (`test_corpus_license_gate`, 2 failures) and whose manifest — `config/dependency-licenses.yml` — is SONNET-05's file. Landing it here turns a red gate into a redder one owned by someone else. |
| `R11-07` focus after "Forget this" | Lives in `DevicesTab.tsx` (OPUS-03's `components/settings/devices/**`), not in OPUS-05's files. Still open. |
| `R11-08` HostShell landmark | `components/shell/**` — not an Opus packet's file, and that tree moved under the shell redesign merged into `main` today. |
| `R9-F07`/`F08`/`F11`/`F13`, `U2-09` modality XML | Voice residuals below the P0/P1 line; the chain now runs end to end without them. |
| `SE-05` wire `ComputeRouter.route()` | Explicit founder decision (§4). |
| `SE-12` bounded deferred queue, `replay_deferred` | Gated on `SE-05`. |
| `PERS-02/03/05` persona sources of truth | Not started. Design recommendation A (pick `PersonaStore`) still stands; it is a coherent standalone piece. |
| `U6-BUG-03/04` Frigate queue cap and snapshot routing | Not started. |
| `SE-28` two-process pairing test | Not written. The single-process security properties are covered (13 tests); a genuine two-port test wants the founder's two-machine run behind it, §4. |
| Anything needing real audio | No sherpa-onnx, no openwakeword, no Piper voices in `.venv`, and the packet forbids installing into the shared one. §4. |

---

## 4. For the founder — decisions and hardware

**Terminals (OPUS-04 Task 4), the one that needs an answer before more work:**
Plan B's watched-shell pipeline, the agent PTY pool, the somatic block pipeline and `TasksColumn`/`YourShellRegion` are all built and unwired. The pool is now *safe* to enable (`R04-F3`/`F4` were the blockers) but is still enabled only by tests. **Recommendation: (a), wire it** — the design's direction is "user shells stay but are watched by the AI", the components exist, and option (b) means deleting work that is finished apart from its wiring. One change of shape since the packet was written: `ModeSwitch.tsx` was **deleted** by the shell redesign merged into `main` today and replaced by `PanelToggle`, so `TERM-08`'s "aggregate StatusLight on ModeSwitch" needs a new home.

**Compute (OPUS-03 Task 4, `SE-05`):** `ComputeRouter.route()` is still never instantiated; chat goes through `TierRouter`. The endpoint it routes *to* now exists and works, so wiring it is no longer blocked. **Recommendation: wire it for the HOME variant only**, which is where the Compute Peer card ships.

**`R2-F6` outbound token custody:** the Fleet Cockpit cannot be built until this is decided. `PeersConfig` deliberately stores only hashes (M14), so the Desktop's outbound satellite credentials need their own store — a separate credentials file or a keychain reference. I left the routes answering 501 rather than inventing one, because inventing one silently downgrades M14.

**Wyoming defaults changed, and this is operator-visible:** `WYOMING_ENABLED` now defaults to `0` and the bind to `127.0.0.1`. Anyone running an HA satellite against Halbert must now set `WYOMING_ENABLED=1`, and if the satellite is on another host, `WYOMING_HOST` **and** `WYOMING_TOKEN` — the server refuses to start on a non-loopback address without a secret. This is a deliberate breaking change: the old defaults ran agent turns for anyone who could reach the port.

**Hardware runs still at 0/22** (`VM-27`, `VM-15`, `HW-01`). The voice chain is now wired end to end and testable, but no real audio has ever gone through it. What a run would settle that tests cannot:
1. Whether `is_speech`'s per-frame `detector.flush()` is right. The packet asked me to remove it; I did not. Silero is a stateful RNN and flushing per window discards the context hysteresis depends on, but with sherpa-onnx absent I cannot measure the difference, and changing untestable inference behaviour on reasoning alone is worse than flagging it. **This is the one packet instruction I deliberately did not follow.**
2. Whether the 8 s recognition watchdog in Voice Mode is the right length.
3. The 22-row hardware matrix, still entirely empty.

**`VM-22`** (Python consumer for the Rust AEC socket 18400): unchanged, and I agree with the packet's recommendation — doc 16 Decision 1 made the browser the audio terminal, so `audio_capture.rs` should be marked dormant rather than given a consumer.

---

## 5. Doc corrections for SONNET-05

- `IMPL-PLAN-SINGULAR-ENTITY-TASKS-2026-08-31.md` "Status: COMPLETE" — Phase 7's acceptance ("pair through the UI, no YAML") is *closer* but still not met: the API is correct and tested, the host-side approval UI is not built. Its note that `test_cognition_tick_once` is order-sensitive is wrong (`R06-F2`, deterministic, fixed).
- `compute_router.py:348-351` docstring says PeerProvider HTTP is TODO. It was implemented; the workstation side was what was missing, and now exists.
- `HANDOFF-README-PEER-COMPUTE.md` presents peer compute as the recommended home build. It works now, but pairing needs a person at the host.
- `documentation/design/16-voice-mode-visual-ui-implementation-plan.md` defers STT in O7's prose and no task owns it. It is built (`VM-STT`).
- Wyoming's operator-visible default change (above) needs to reach `documentation/` and any install guide that mentions `WYOMING_ENABLED`.
- `HARDWARE-VALIDATION-MATRIX-2026-08-31.md` is still 0/22 and its "not yet built" notes are still stale.

---

## 6. Method notes

- Every fix was driven from a failing test first, and for each I checked the test fails on the *pre-fix* code — several times by stashing the fix and re-running, which is recorded where it mattered.
- The full Python suite was run at every checkpoint and the sorted FAILED list diffed against `pytest-main-failed-4a7bf71f.txt`, never eyeballed. Nine full runs; new failures at every one: zero.
- Four tests were changed to assert different behaviour rather than being made to pass. Each is called out in its commit message with the reason: two encoded the Wyoming vulnerability itself (`0.0.0.0` + enabled-by-default, and skip-a-bad-line framing), one encoded the missing STT as the contract, one asserted a redaction guarantee the redactor does not make.
- `wt_pytest.py` was copied to the repo root as an untracked helper (SONNET-02 owns committing the canonical copy, `WT-01`). It is not in any commit here.
