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

### R-05 — redaction registry, Tier-2 choke point, error-text hygiene

| Phase | Commit | What |
|---|---|---|
| A+B | `a270d3cc` | Every encoded form registered; nothing crosses uncoerced |
| C+D+E | `09d7a5e6` | MCP credentials registered; logs redacted; one scrub seam |

- **A03-G6 (FD-15)** min length 4 → 6; **bug 2** the raw form was evicted first because `_variants_of` returned its forms sorted, so insertion order was alphabetical; **A03-G4** one encoder was registered where four are needed (`quote` default, `quote(safe="")`, `quote_plus`, JSON-escaped); **bug 3** replacement was a sequence of `str.replace` calls, so a form could match inside the placeholder an earlier one had just written — one compiled longest-first alternation, one `re.sub`, which cannot collide with its own output. The registry is locked: it is written from request threads and read from the turn's.
- **A03-G1 + bug 1** (fix-first row 7): `redact_result` returned anything that was not a str/dict/list untouched, and the MCP dispatcher then ran `json.dumps(result, default=str)` *after* the pass. Coerce first; re-scan the serialized text with the registry only (the pattern pass rewrites `key: value` shapes and would leave the reply unparseable). **A03-G2** registry before patterns. **A03-G3** circular-reference guard. **bug 5** the confirmation dialog's args preview showed an MCP call's arguments verbatim.
- **A03-G7** MCP bearer tokens were never registered, so the one class of secret this process resolves on every request was invisible to the exact-value pass. **A03-G8** `JsonFormatter` wrote whatever it was handed, and there are several hundred `logger.warning(f"...")` call sites.

### R-06 — echo guard, display projection, turn digest

| Phase | Commit | What |
|---|---|---|
| A | `09d7a5e6` | `EchoGuard.redact` + the shared seam (landed with R-05) |
| B–E | `261ab8b2` | Digest truth and bounds; history projected like live |

- **A05-G1 + bug 1** (row 8): the guard matched on a normalised window then called `registry.redact_text`, which replaces whole forms — so a reply carrying the first 85 characters of a 98-character acked value matched, changed nothing, and was delivered while the log said `redacted: true`. `EchoGuard.redact` replaces maximal RUNS, joined with `\s+` so a re-wrapped echo is caught too.
- **A05-G4** the seam existed twice, the copy commented as "mirrors" the original. **R-05 Phase E** both were "non-fatal by construction" and returned the text RAW on failure.
- **A05-G9 + bug 6** the digest recorded successes only, and `success` is True for a command that returned 1 — "I restarted sshd" was spoken for a restart that failed. **G8** forty files meant forty spoken lines. **G10** a binary target rendered as its own length in characters of noise. **bug 7** the tail and the audit rollup bypassed the egress seam.
- **A05-G3 (FD-16)**, **G5 + bug 5**, **G6**, **G7**, **G11**, **G15**: the display seam gains the pattern pass; the cap stops cutting mid-line and names both cuts; a capped block carries structured facts; the budget is per-payload not per-string; the seam fails closed; chat input is NFC-normalised with NUL refused.
- **A05-G4 (history half)**: a live `tool_complete` crossed the wire projected and a HISTORY read came straight out of SQLite, so a value redacted when it happened was delivered raw on the next page load.
- Recorded, not changed (**A05 bug 2**): the streaming draft is emitted before the guard by design.

### R-10 — speech egress

Commit `f82cbc5a`, under FD-4.

- **A10-G5** (row 9): the satellite path collected `response_chunk` events — raw model output that bypasses the module-invocation parser, the echo guard, the engine's word cap and `tts_quality` — and read the concatenation aloud on the one screenless surface. It takes the committed `speech_segment` text now; the chunk fallback goes through the same pipeline. **The STOP condition asked whether `response_complete` is observable there: it is, and carries no content, so the committed text comes from the speech segments and no event-stream contract changed.**
- **A10-G1** reasoning and control tokens were spoken as words. **G3 + bug 1** the fence scanner was a non-greedy regex matching any closer, so an unclosed fence counted as nothing and a four-backtick container closed on the first inner three. **G12** the shaping facts were recorded nowhere.
- **A10-G7** `get_modality_prompt_builder` appears exactly once in the tree, at its own `def`, so the engine's budget block was never reached: every voice reply was written at essay length and cut mid-sentence at 12–35 words. The prompt now carries the budget; the cap itself is untouched (FD-4) and no engine file is edited. **The `AreaContext(multi_occupant=True)` STOP condition did not fire** — the hint reads the resolved policy's own `max_spoken_words`.
- **A10-G6** barge-in told the model nothing, and the commonest reason a person interrupts is that the answer had already gone wrong.
- **A14-G4/G7 (summarizer halves)**, **A14 bug 3**, **A10 bug 3**: `require_local` on a secure turn, one retry excluding a failed pick, an off-loop form, and a docstring that stops claiming a seam that has never run — with the arithmetic pinned (600-char gate behind a 12–35-word cap), so a later change to either number is a change someone has to look at.

### R-07 — execute_code hardening

Commit `7b3910a3`, under FD-17 and FD-18. F-1's in-process model is accepted: no child process, no sandbox.

- **A04-G1 + bug 2** (row 12): the wait loop ran `while not done.is_set()` with the grace loop AFTER it, so an `except BaseException` retry wrapper, an `input()` or an `Event().wait()` made `run_script` never return — the turn hung holding the turn lock.
- **A04-G2** (row 11) the dispatch hook was never cleared. **G3** (row 13) the spill was unbounded and every byte counted as activity. **bug 1** (row 34) the AST gate missed `import os as o` and `from os import system`. **bug 4 + G11** two overlapping runs corrupted each other's `sys.stdout`. **bug 6** `max_tool_calls=0` became 25.
- **A04-G5/G6** `__name__` was `"__halbert_script__"` so no `if __name__ == "__main__":` block ever fired; a raising script lost its partial stdout. **G8** stderr was not captured. **G9** a user stop ended the turn but not the script. **G4** stdout/stderr/error/traceback go through the shared redaction core — the TEXT fields only, because redacting the whole dict rewrote `spill_path` into `<token>.txt`. **G7** the schema names the stub set.

### R-04 — conversation store and state ledger hardening

Commit `1d9497f7`.

**The fixture came first, and it reproduces.** `_corrupt_fts_for_test` raised a MOCKED exception, so every corruption test exercised the handler and none exercised SQLite. Dropping the `messages_fts_data` shadow table produces `sqlite3.DatabaseError('vtable constructor failed')` deterministically — the `CREATE VIRTUAL TABLE IF NOT EXISTS` still succeeds, so the open looks fine and the first USE raises.

- **A08-G2 + bug 3** (row 14): that is the PARENT class and the store caught only `OperationalError`, so it escaped, `_conn` went None, and the store was bricked on that open and every reopen — the conversation was never recorded again. The breadcrumb is read at the TOP of the migration now, not after the DDL that runs against the index it distrusts.
- **A08-G1**: the predicate matches the origin, deliberately narrow — "vtable constructor failed" is a missing shadow table, which a rebuild fixes. **Recorded (FD-11's other half): `sqlite_errorcode` does not exist before Python 3.11 and this venv is 3.10.9, so that arm of any classifier is dead here.**
- **A08-G3 + bug 7** (row 15) `rebuild_fts` had no caller and `search_snippets` returned `[]` while degraded — permanently. **G7/G8** an unopenable store said only `connected is False`; a zeroed or NOT-A-DB file is moved aside, never deleted. **bug 2** (row 23) `add_open_loop`/`close_open_loop` committed outside the lock. **bug 5** (row 24) `forget_request` had no error handling at all. **G12 + bug 4** the default path was a module constant computed at import; the pytest guard fires only when nothing has redirected the data directory. **A16-G4** a newer schema is refused rather than migrated backwards.
- **A08-G5 (FD-11)**: SQLite 3.39.4 is in the WAL-reset range. Said once at the first store open; the journal mode is NOT changed, because doing that would quietly alter the durability of the operator's existing database.

### R-02 — claims, admission graph, guest routes, voice provenance

Commit `b41f3626`.

- **A12 bug 4** (row 27): the loopback predicate accepted the hostname strings `'localhost'` and `'testclient'`, and it fronts eleven of the fifteen guest routes including the camera. Four suites relied on that string and now map the TestClient host to local explicitly — the audit's own remedy — while the tests that want a REMOTE caller keep working on real addresses.
- **A12 bugs 5 and 6** (row 28): `persona_id` went into a sibling home's URL PATH raw and a remote home's listing supplies it; and the `home:` namespace was never fenced from operator-chosen node ids. **A12-G1** the walk did not stop at the first BLOCK. **A12-G4** SKIP and OBSERVE dispatched nowhere.
- **A09 bug 4** `weakest_claim([])` raised out of the claim ladder. **bug 5** (row 29) a match whose profile lookup failed kept its speaker_id, which is what stamps a verification claim. **bug 6** one utterance could become two turns — two answers, and for a command two executions.

### R-11 — skills plane

Commit `c1d844e5`.

- **A13 bug 1** (row 25) the YAML alias bomb: the type check comes first and the bound second, because measuring the result is measuring it after the damage. **bug 2** `float()` accepts nan/inf, and a `.nan` multiplier raised out of `ContextAssembler.assemble` on every matching turn. **A13-G1** the loader caught two exception types, so one bad file cost every skill on the machine (`KeyboardInterrupt`/`SystemExit` deliberately re-raised).
- **A13 bug 5** (row 26) protected paths were compared raw, and the bare `startswith` made `/opt/bootleg` match a rule about `/opt/boot`. **bug 6** `allowed_tools` was merged, warned about, and enforced nowhere.
- **A13-G7 (FD-19)** telemetry is erased with the run and suppressed when the conversation is not Halbert's; the permission check fails closed and asks the thread manager the same question it already asks before recording promotion evidence.

### R-14 — memory promotion follow-through

Commit `8448280b`.

- **A01-G2 + bug 2** (row 21): "decay multiplies ranking" was a no-op — the field is a snapshot and both callers passed 0.0, so a key recalled once sixty days ago ranked as if recalled today. Derived at rank time, calibrated against the origin's 0.25-at-60-days figure.
- **A01 bug 6 + G5** (row 35): a guest's recall persisted evidence about them that "forget me" could not reach. Both closed, and `ERASURE_LIMITS` states the residual honestly (signals a PREVIOUS process recorded are keyed by claim and outlive their run id).

### R-12 Phase B — deterministic compaction v0

Commit `e510262f`, under FD-3.

**A16-G1 + bug 1**: `compact_boundaries` shipped with a schema, an index and no writer. `continuity/rotation.py` extracts rather than composes — the exact command, path and error string — and a test greps the module for a model so one cannot arrive by accident. The guards (**A16-G6**, **A16-G10**) each refuse with a reason, because a rotation that quietly does not happen is indistinguishable from one that happened and lost everything. The store side is one transaction. **A16-G3** `context_included` has both halves.

### R-11 Phases C, D and E — the skills plane, closed out

| Phase | Commit | What |
|---|---|---|
| C | `4bc526ad` | The catalog says what it is for, and stays bounded |
| D | `4bc526ad` | It follows the disk; runtime tools are reserved; ids survive a restart |
| E | `b9bf7757` | The body is read; the declared gates are consulted |
| E | `27639116` | The CC flags, a colon in a description, what `extends` means |
| tail | `ef15d8eb` | A receipt for a read that happened; a suite that reads CI's skills |

- **A13-G3** (the audit's "cheapest high-leverage" row): the block listed nine skills and never said what a skill is FOR. Track B is progressive disclosure and it worked only if the model already guessed the convention. Four lines above the block, outside `<available_skills>` where the origin puts them, so the element stays byte-for-byte the ecosystem shape — with a test on that specifically, because the ingest contract is the reason the shape exists.
- **A13-G4**: between the parse ceiling (4096, a DoS bound) and the ladder's cap sat rung 0, where a description renders in full because the total happens to fit — so one pack entry with a 4000-character description became the catalog. The ceiling is 200, not the 60-character create bar: clamping to that would cut founder copy mid-sentence, which is FD-20's to trim in words.
- **A13 bug 7**: the notice told the operator to audit with `halbert skills list`. There is no such command. The one line in the render whose only job is honesty was the line that was not true. While fixing it I had the render ask itself whether it said "truncated" — this module's own documented anti-pattern, and wrong on top of it, since a skill installed under a path containing the word answers yes. The ladder returns the flag.
- **A13-G2**: `get_agent()` is a process singleton, so an edited SKILL.md never reached the running daemon — while `read_file`, following the `<location>` the catalog had just printed, served the NEW body. Hermes's manifest shape, restatted at turn start. Two invariants have tests because both are ways a fix for this reintroduces it: the matcher keeps its identity across a reload, and the signature is committed only on success.
- **A13-G13**: "tool registration is static per process" — which the cache rested on — is simply false. HA registers two tools, Frigate six, and an MCP server whatever it likes. The static half stays cached; a live half is asked every check.
- **A13-G8**: an id-less skill got a fresh random ULID at every load, so every skill was a new row in the telemetry table after every restart. Derived from the canonical path, **not** written into the sidecar: the origin's fix would make the load path write into the operator's directory and into the installed package.
- **A13-G5 (SK-5)**: nothing looked at what a skill body SAID. The posture is the design's — bundled fail CI, everything else is refused with the finding logged and never scrubbed. The two severities are explained under FD-notes below; running the scanner over the shipped set is the packet's own STOP condition and it found both a real false positive of mine (`<user>` as a forged-role tag, which `home-ops` writes as placeholder prose) and the `chmod 777` case.
- **A13-G6**, **G10**: `SkillRequirements` said outright "parsed — not evaluated. Evaluation is SK-4's", and nothing was SK-4. Four answers, because they are four facts an operator acts on differently. An explicit `/name` ignores TRIGGERS now, not gates.
- **A13-G9**, **G11**, **G12**, **bugs 3/4/9/10**: the CC invocation flags read and honoured on their own surfaces; one colon-rich `description` line recovered and nothing else; `extends` can declare a default back and unions `requires`; `skill_for_path` no longer gives a bare-layout skill the whole root; the read receipt follows the read; the suite stops reading the developer's own skill directory.

### R-02 Phases C and E — receipts, and the tee's other half

Commit `d2ca50ad`.

- **A12-G3, the live half.** `decide_ingress` stopped at the first BLOCK; the BUILDER loop did not. The builders are documented read-only and are not: on `/api/guest/private/assign` and `/api/guest/forget` the second one calls `current_guest()`, which can fire the session keepalive — an outbound request to a sibling home — and can end a live session. An off-machine caller refused 403 could still make this machine talk to a sibling home while being told no.
- **A12-G5**, **G7**, **G8**: a denial no longer echoes its machine code as the human message, and an AST walk of every `block(...)` call site fails CI instead of a person's screen; the role cap records what capped it *and* records that nothing did, which is what tells a reader the claim was looked at; `guest_homes.yml` holds a bearer token and is fsync'd before the rename.
- **A09 bug 3**: the tee scrubbed top-level strings and a tool result's stdout sits one layer down. Depth-bounded, because a recursion limit reached inside an *observation* would take down the turn being observed. Plus `seq`/`ts` on every delivered event, and a turn-scoped event with no session id dropped rather than guessed at.

### R-14 Phase C — the promotion gates

Commit `af98be77`.

**A01-G7** is two problems. The origin's four calibrated gates arrived here as two, with the diversity floor halved and days not counted — no handoff records a decision to drop the rest, which is what makes it a gap rather than a difference. And importing `MIN_SCORE=0.75` meant fixing the scale first: the score summed an uncapped `log1p` with three fractions and could exceed 1.0, so 0.75 laid over it would have passed anything with three recalls — a gate in name. The weights are fitted to the origin's own three published bands.

**A01-G11** reproduced before it was fixed (three spellings of one question counted as three). **A01-G12** was worse than reported: the failing load left a half-loaded store, so a persisted key came back with zeroed counts rather than absent. **A01-G13**'s liveness predicate keeps a candidate when the check itself raises. **A01-G9**'s two events land on the ratified ledger, carrying keys, counts and scores and never the words that were recalled.

**A01-G1 stays unbuilt and a test says so**: FD-22's Phase-B checkpoint stands, and if someone wires the ranker the test names the decision that was skipped.

### R-12 Phase C — branch summaries, and a hole Phase B opened

Commit `b017e65e`.

**A16-G7**: leave the Samba subject for the scanner-share subject, come back six turns later, and the reopened thread's history is its last twelve rows — the detour and what it decided are nowhere in the transcript. What existed was an ephemeral one-turn note that stored nothing and a recall chip carrying `{thread_id, title, date, status, at}`: a pointer, not a sentence. `move_leaf` had no message insert at all, and its own docstring said T2 would add one.

`continuity/branch_summary.py` builds both rows by template (FD-3's rule and the tiered-sensitivity rule are the same rule here), and the titles go through `threads.py`'s `_fence` rather than a fourth private copy of the sanitizer this tree already has three of. The crossing is keyed on the last **turn** in the thread being left, not the last row — one choice that does both jobs the design asked of the key: a retried crossing writes only the half that is missing, and a switch loop with nothing said in between writes nothing at all. `context_included` is 0 on the departure row and 1 on the return row, per §2.3.

Also closed: `search_snippets` joins `messages_fts` and skips hidden rows, and rotation hides every covered turn — so **this branch's own Phase B** made a compacted thread's scrolled-away history unfindable, because the summary row was written with raw SQL and there are no triggers on that table. `_index_message_fts` puts `append_message`'s three rules in one place and `write_compact_boundary` calls it.

## Left

**The turn-loop wiring**, for both halves of R-12: the rotation writer has no caller in the turn loop, and the branch-summary minting has no caller because `move_leaf` still has none. Both callers live in `agents/threads.py` (`_reopen_thread`, `end_turn`), which is R-12 Phase A's file and belongs to the sonnet batch (`fix/remediation-sonnet-batch-1`) — nothing here touches it, so the two branches merge cleanly and the wiring is one commit after Phase A lands. Naming it is the point: this is the cross-cutting defect shape the whole pass exists to stop recreating ("module ported, consumer never wired"), and it is recorded here rather than left to be rediscovered.

Also left, and each for a stated reason rather than for lack of time:

- **R-09's A17-G19** — FD-10 says record, do not build.
- **R-01's A07-G11** — FD-1 says no auto-continue; the interrupted turn heals to a persisted status and nothing re-submits it.
- **R-01's A07-G8** (low) — the origin's yield-during-a-foreground-command concept has no analogue here at all. It is a feature, not a defect: nothing in this tree claims to yield, so nothing lies about it.
- **R-14's Phase D consumer (A01-G1)** — FD-22, above.

Everything else in the twelve opus packets is landed. Suite at the end of the batch: **8420 passed, 15 skipped, 6 xfailed, 1 failed** — the one failure being `test_vision_tools.py::TestCaptureScreenshotHandler::test_region_capture`, which reads this host's real display geometry and fails in isolation on a clean checkout of `main`.

## Two decisions waiting on the founder

**FD-20 — the six bundled SKILL.md description trims.** The packet's STOP condition is explicit: this is founder-authored copy, to be proposed and not invented. Measured on this branch (limit 60):

| Skill | Now | Current text | Proposed trim |
|---|---|---|---|
| `config-ops` | 72 | Configuration files — what they say, what changed, and what reads them | *Configuration files — what they say, what changed, what reads them* (69) |
| `frigate-ops` | 82 | Frigate NVR, camera streams, object tracking, Coral Edge TPU, and MQTT integration | *Frigate NVR: camera streams, object tracking, Coral TPU, MQTT* (58) |
| `home-ops` | 80 | Home Assistant, smart home devices, room lighting, climate, and spatial presence | *Home Assistant: devices, lighting, climate, and room presence* (59) |
| `security-ops` | 61 | SSH, authentication, permissions, certificates, and hardening | *SSH, authentication, permissions, certificates, hardening* (57) |
| `service-ops` | 65 | Services and daemons — start, stop, enable, and why they failed | *Services and daemons — start, stop, enable, why they failed* (58) |
| `understated` | 76 | Says what was noticed in one plain sentence and lets it carry its own weight | *Says what was noticed in one plain sentence, and stops* (53) |

Every proposal removes words only; none introduces a term the original did not use. `config-ops` still exceeds 60 with words alone — it needs a real edit, not a trim, which is why it is not made here.

Two notes for whoever applies these. The `frigate-ops` and `home-ops` proposals introduce a colon, which is exactly the shape A13-G11 was about: a colon-rich `description` used to make the whole skill unparseable. It is recovered now, and the recovery logs a warning telling you to quote it — so write those two as `description: "Frigate NVR: …"` and the recovery never runs. And `skills.catalog.descriptions_over_limit(registry)` is the sweep as a lint: `tests/test_skills_catalog_guidance.py` asserts the over-limit set can only SHRINK, so each approved trim makes the test's known list smaller and a new long description fails CI.

**The OS re-auth handler (A11-G12's residual).** Named above under R-08: it is what unblocks first-run acceptance, and until it exists no grant requiring a live re-auth can be recorded.
