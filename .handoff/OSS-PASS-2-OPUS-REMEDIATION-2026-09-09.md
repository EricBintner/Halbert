# OSS-pass-2 remediation — the opus tier, as executed

Branch `fix/remediation-opus-batch-1`, worktree `.claude/worktrees/remediation-opus-1`, cut from `main` at `f22a57b4`.

Scope: the twelve opus-tier packets from `.handoff/OSS-PASS-2-REMEDIATION-TIER-ASSIGNMENT-2026-09-09.md` — everything the tiering pass did **not** hand to sonnet (which is running R-03, R-13, R-15 and R-12 Phase A on `fix/remediation-sonnet-batch-1`). Packet definitions are `.handoff/oss-pass-2/remediation_plan.md` §4; the founder-decision defaults are §7, and this batch proceeds on those defaults, as §7 instructs.

## Baseline

`main` at `f22a57b4` is **fully green**: 7772 passed, 15 skipped, 6 xfailed, 0 failed, ~4 minutes, with

```
cd <worktree>/halbert_core && arch -arm64 /Volumes/4TB-BAD/Halbert/.venv/bin/python -m pytest tests/ -q -p no:randomly
```

No `wt_pytest.py` wrapper is needed any more — `halbert_core/conftest.py` strips the editable finder and asserts the worktree's own source. So every failure on this branch is this branch's.

Two environmental failures to know about, neither caused by this work:

- `tests/test_vision_tools.py::TestCaptureScreenshotHandler::test_region_capture` — reads the real display geometry and fails on this host ("that region is not inside screen:1"). Fails in isolation too; this branch touches no vision file.
- `tests/test_scheduler_executor.py::test_one_time_job_runs_and_records_outcome` — asserts a REAL CPU budget (`CPU budget exceeded: 85.5% > 50%`) and fails when the machine is loaded (e.g. two sessions running the suite at once). Passes in isolation.

## Done

### R-01 — talk-door ordering and the interrupt algebra

| Phase | Commit | What |
|---|---|---|
| A | `96afc16e` | Stamp before the verb |
| B | `4d200b9f` | One stop verb, and it stops what is running |
| C | `320ee14f` | An accepted steer is delivered |
| D+E | `fef55a7c` | Turn-liveness watchdog; one deny shape at the talk door |

- **A09-G1 = A07-G1 = A07 bug 3 = A09 bug 2** (the pass's #1 finding). The talk door called `handle_midturn_arrival` ~100 lines above the block that consumes the voice relay receipt and stamps the claim and role, so a guest with no voiceprint and no relay token could steer the owner's running admin turn — and the single-use receipt stayed spendable. The stamping block moved above the mid-turn branch (nothing in it changed, only where it runs), and `handle_midturn_arrival` takes the stamped identity as arguments so the old order cannot come back by accident.
- **A07-G1 role floor.** A new `Verdict.REFUSED`, ordered ahead of the command bypass because `/stop` is the strongest verb and not an exemption. Both sides of the comparison read through `role_gate.turn_role_order` — the existing role table capped by the existing claim ladder — so no role vocabulary was minted (the packet's STOP condition).
- **A09 bug 1**: `process()` normalised an unrecognised modality to `"text"`, which is the dashboard channel, whose default role is admin. `modality='mcp'` got an admin turn. It resolves through the one registry now and refuses what the registry does not admit.
- **A12 bug 1**: a claim the ladder could not derive was left `None` — and `None` is not a weak claim, it is *no cap*, so the executor's voice ceiling never ran. A failed derivation binds UNVERIFIED.
- **A07-G2**: `/stop` during a tool batch was demoted to a steer. The demotion rule is "never kill a tool to deliver *guidance*", which is Rule 3's plain text; transcribed onto Rule 1 it left the algebra unable to stop a running command. Rule 1 is unconditional, the tool wait loop is bounded by `STOP_POLL_SECONDS` and polls the flag, and `task.cancel()` reaches `run_command`'s own `except BaseException`, which kills and reaps the child.
- **A07-G13 + bug 2**: `/cancel` raised the flag with no generation claim while a typed `/stop` claimed it — two verbs, two semantics, and a paused turn that tore down under one and not the other. `cancel_session` delegates to `request_stop`; the client posts `/stop` on both the button and the unmount path.
- **A07-G5**: a stop could not abort an in-flight model request. `_model_call` / `_model_stream` wait in poll-sized slices and cancel the request task; `_drive` catches the resulting `TurnStopped`.
- **A07-G9**: a turn queued on the turn lock was not in `active_sessions`, so a stop declined and the queued turn ran anyway. Queued sessions are tracked and the flag is read first thing under the lock.
- **A07-G3 / G6 / bug 1**: a steer after a stop or after commit was confirmed then discarded; the pending slot was replace-not-grow so a second steer erased the first after both were told "accepted"; an empty arrival joined the turn as a blank line. All three refuse or concatenate now, with closed-set reason codes.
- **A07-G4**: the marker is a labelled `[steered]`/`[/steered]` pair, and a turn carrying one renders `STEER_CONTRACT` — what the block is, that it may redirect the turn, and that it carries the turn's authority and never widens it.
- **A07-G10**: `TURN_LOCK_TIMEOUT_S` bounds a *waiter*; nothing bounded the *holder*. `StateContext` gains the liveness clock the origin's watchdog is built on, stamped at handler entry, tool start/output/completion and every stream chunk, with one sampler bound to the generation it observed. A turn parked on a confirmation is exempt — waiting on a person is not wedging.
- **A12-G6**: the door hand-copied the guest routes' deny payload in `agents/channels.py`, and the copy had drifted (it interpolated the client's own modality string into the message it echoed back). The reason-text registry and the allow/block/deny_payload helpers moved to `persona/admission.py`; the door walks a named gate list and produces an `IngressDecision`.

**Not built, and why.** A07-G11 (auto-continue after a daemon crash): FD-1's default is no auto-continue. A07-G8 (a yield primitive): REDIRECT is dormant — no channel declares it and no provider client exposes a cancellable request — so a yield primitive would ship with no consumer, which is precisely the cross-cutting defect (`remediation_plan.md` §2 theme 1) this whole pass exists to remove. Build it with the verb, not before.

**Not run:** the frontend vitest suite. `useAgentStream.ts` and its cancel test changed (two URLs and a filter string), and the frontend dependencies are not installed anywhere in this checkout — `npx vitest` cannot resolve `vite`. Worth a run wherever `node_modules` exists.

### R-09 — MCP client boundary

| Phase | Commit | What |
|---|---|---|
| A | `7edf3908` | Child env allowlist; bounded frames; the config path is sensitive; the loader rule |
| B | `865e016c` | Bounded, attributed, sanitized server text |
| C | `ab0750a1` | Process groups, list_changed, breaker, proven sessions |
| D | `d569883d` | HTTP hygiene, bounded pagination, an operator tool filter |
| E | `afc2f1b9` | The door declares what each of its tools is |

- **A17-G1** (the pass's #2 finding): a configured stdio server inherited Halbert's whole environment, so an npx package could read `HALBERT_MCP_TOKEN`, `HALBERT_PEER_TOKEN`, every other server's key, and call back into Halbert's own authenticated MCP server *as Halbert*. `child_env()` is an allowlist plus the server's own configured env; `DYLD_*`/`LD_*` are dropped from both sources.
- **A17-G2 + bug 1**: no `limit=` on the stdio stream, so a 200,000-character result killed the transport and failed every pending request. 16 MiB bound; an oversized frame is drained in bounded chunks, fails the longest-outstanding request, and the loop lives.
- **A17-G3 + bug 2**: `mcp_config.yml` is a list of commands Halbert executes, and on macOS it lives under `~/Library/Application Support` — not under `~/.config`, so the agent's own `write_file` to it classified MEDIUM. Halbert's config and data directories are in `SENSITIVE_PATHS` now, and `mcp/entry_guard.py` is the second gate: an entry whose *shape* is a payload (a shell with an inline script, a fetch piped into an interpreter, a raw egress helper, a persistence write) does not spawn. Deliberately not an allowlist; findings name the shape, never the entry's own strings. **Checked before shipping** (the STOP condition): this host has no `mcp_config.yml`, so the rule skips no server the founder has.
- **A17-G5 / G6 / G7 / bug 6**: server text is capped and stripped of Unicode tag characters (U+E0000–U+E007F: invisible to a reviewer, plain text to a tokeniser) and override phrases; `MCPToolError` goes through `redact_error_text` (landed in `security/result_redaction.py` as the shared A03-G5 helper R-05 builds on); results are fenced and attributed, with `ExecutionResult.provenance`; non-text blocks are projected as facts about themselves rather than tens of thousands of tokens of base64.
- **A17-G8 (FD-8) / G10 / G11 / G12 / G13 / G14**: `destructiveHint → HIGH` (an annotation is a claim by the party being gated, so it may tighten and never loosen); `start_new_session=True` and a group sweep on close, because npx exiting is not the server exiting; `tools/list_changed` sets a flag the health monitor consumes off the read loop; an intra-server name collision is excluded rather than suffixed (a suffixed twin makes a per-tool risk override name two tools and fence neither); a DOWN server fails fast with text written for the model; and only a *proven* session clears the reconnect budget.
- **A17-G15 / G16 / G18 / bugs 3, 4, 5**: DELETE on close, scheme validation, `allow_redirects=False` (a redirect carried the session id and bearer token to another origin); pagination bounded by cursor set, bytes and deadline, not page count alone; `tools: {include, exclude}` applied before the 64-tool cap; `ping` answered; honest client capabilities (`tools`/`resources` are SERVER capabilities — advertising them invited a server to ask for something that comes back method-not-found); and the HA handlers work in both hosting modes, since MCP-04's topology is open.
- **A17-G9**, scoped inside the founder-ruled B6 audit. The first reading of this gap was wrong and is corrected in the commit: the four state-changing tools are **not** ungated (`run_scanner` needs `confirm=True`, `approve_proposal` needs `confirm` plus a typed phrase for a critical proposal, `ha_call_service` runs through the AutonomyGate, `set_autonomy_level` needs the escalation phrase). What was missing is a PLACE where the question is asked: nothing said which tools the door serves or what gates each one. `mcp_tool_policy` is that declaration, enforced at the existing dispatch choke point, with `audit_mcp_tool_classifications()` rendering the table for the B6 record. A tool nobody has classified is refused.

**Not built:** A17-G19 (opt-in OSV malware preflight) — FD-10's default is "not now; record".

### R-08 — permission lattice

| Phase | Commit | What |
|---|---|---|
| A | `219a32bc` | Fail closed, one clock, typed refusals |
| B | `e5a65f4f` | The ask axis is enforced; an approval binds to what it approved |
| C | `dde1436f` | A lease ends when its permission does |
| D | `d58bc027` | A Stop survives a restart; a resume is authorised |
| E | `ea31520f` | A grant resolves to real words, and to what the server validated |

- **A11-G2 + bug 1**, reproduced before fixing: `Scope.from_mapping` raised on any key outside its binding four, and **24 of the 47 shipped profile rows** carry one, so the first `require()` after first-run acceptance raised a bare `ValueError` and crashed the turn. The vocabulary splits — binding facts through `Scope`, provenance recorded beside it, a key in neither still raising — and any failure inside `require()` becomes `Denied(SCOPE_UNREADABLE)`.
- **A11 bugs 3, 6, 7**: two clocks (an injected `now` past expiry with wall time before it produced ALLOWED with `granted_scope=None`); `halt=None` reading as "not halted", so a wiring site that omitted the argument never observed Stop; `TypeError` escaping the ledger reader instead of taking the halt path.
- **A11-G1 + bug 2 (FD-6)**: `role_gate.py` said it in its own comment — "Recorded, never enforced". `accept_profile` dropped `ask_every_use`, and `axis_floor` was a constant OFF, so the per-use confirmation the review screen promises existed only as a Python constant. The disposition now rides the hash-chained event, reaches the lattice as `AskPolicy.ALWAYS`, and `require()` denies `NEEDS_APPROVAL` without a receipt. `persona/permission/approval.py` binds an approval to the capability, the artefact digest and a single use.
- **A11-G3 / G8 / G10 / G11 / bug 4**: narrowing consent reached the ledger and nothing else (a revoked camera grant left the capture running); `max_session_lease` was written and read by nothing; a voiceprint grant without a TTL lived forever; there was nowhere to say what a lease must undo; and a lease revoked between mint and `with` leaked its indicator row.
- **A11-G6 (FD-5) + bug 5**: the halt was in-process only, and the conditions that halt the machine are exactly the ones a restart does not fix. `<data_dir>/runtime/halt.json` (0600, atomic, flock), read at boot, unreadable-fails-closed; `resume()` takes a single-use token minted for that halt. And `projection_status` compared an old log against a new projection under two different locks, so a concurrent decision halted a healthy machine and called it tampering — reproduced with two threads before fixing.
- **A11-G4 / G5 / G7 (FD-7) / G12, A12-G2**: a grant's digest must be shipped wording; a widening folds an old grant to ask-again (declared, never inferred); QUIET has a producer; `meets_floor` has a consumer and the claim is its own axis with a per-capability floor table.

**REPORTED, per the packet's STOP condition — A11-G12's `os_reauth` leg cannot be minted.** `dashboard/auth.py` validates a session credential and a Host header; nothing in the tree performs an OS re-authentication (no LocalAuthentication, no polkit, no sudo challenge). `SurfaceReceipt.for_session` therefore always records `os_reauth=False`, and a grant requiring a live re-auth cannot be recorded until that handler lands. That is the correct state rather than a gap — the packet forbids accepting a caller-supplied `authn` string as an interim, and a promise the code cannot keep is worse than a missing one. Nothing in production records grants yet (`accept_profile` has no route caller), so nothing regresses today; **the OS re-auth handler is what unblocks first-run acceptance**, and it is named here so it cannot be forgotten.

## Left

R-05, R-06, R-07, R-10, R-04, R-02, R-11, R-14 and R-12 Phases B/C, in the plan's dispatch order (R-05 before R-06/R-07/R-10; R-04 before R-11/R-12/R-14; R-08 is done, which unblocks R-02).
