# State of Work — Verified Inventory of Incomplete and Merge-Ready Work (2026-09-01)

> **Baseline:** `main` = `4a7bf71f` = `origin/main`, 2026-09-01 evening.
> **Method:** 26 read-only audit agents (one per branch, task packet, review report, workstream, and test surface), 6 adversarial verifier passes, a 71-failure pytest triage, and inline git forensics. Nothing was checked out, merged, deleted, or committed. Evidence for every item (file:line, sha, command output) is in `.handoff/audit-2026-09-01/AUDIT-FINDINGS-INDEX.md` (one line per item) and `AUDIT-FINDINGS-DETAIL.md` (remaining work + evidence per item). Item ids below (e.g. `R06-F2`, `SE-09`) index into those files.
> **Direction this inventory serves:** the full Rust rebuild is deferred, a Linux OS is far future; the priority is to get the current features completed and tested.
> **Dispatch:** the work is split into packets for Opus and Sonnet sessions plus one founder-decisions sheet, all listed in §9. Packets are self-contained; start there.
> **Coverage caveat:** the adversarial verify pass completed for 6 of 26 areas (agent core/terminals, U3 frontend, main dirty tree, voice-mark lineages, singular-entity-opus branch, rust branch) before the session usage limit ended the run. The other 20 areas carry finder evidence only. The CI-config agent never ran; CI facts below come from the frontend-suite agent and the pytest triage. This supersedes `HANDOFF-BRANCH-AND-WORKTREE-AUDIT-2026-09-01.md` (earlier today), which is wrong on four load-bearing claims (§2.4).

---

## 1. Headline

- **Everything that matters is already on `main`.** All 10 "merged" local branches, both remote-only branches, both stashes, and three of the five "unmerged" branches contain nothing `main` lacks. Only **one** branch carries work that must be merged: `feat/security-review-01` (a HIGH arbitrary-file-read fix for the MCP config-query tools). `feat/rust-native-core` stays parked by direction.
- **The dirty `main` working tree is finished work from three unrelated efforts** (design-system mark line-count tiers, the Rust roadmap doc augmentation, two audit handoffs) and can be committed after four small clean-ups (§3.2).
- **Test health:** frontend fully green (design-system 70/70, model-picker 103/103, dashboard 699/699, `tsc` clean in all three). Python: 71 failed / 4,509 passed. Of the 71, **38 are real regressions**, mostly two one-line seams in the agent state machine introduced 2026-08-30 (`R06-F1`, `R06-F2`) that also break the Plan A gate test; 13 are a missing `vision` extra that CI lacks too; 20 are stale tests or test-order pollution. **CI is red on `main`** on the literal-colour ratchet (11 files) and has been red on the 13 cv2 tests since 2026-08-29.
- **Shipped-but-dead paths a user hits today** (all P0, all verified on `4a7bf71f`): previous turn's question leaks into the next turn's planning prompt; user terminal tiles are killed after 60 s idle; Settings › Devices is 404 (router mounted without `/api`); Settings › Identity & Voice persona calls 404 (double `/api`); audio quiet-hours hits a route that does not exist; the compute-peer path is dead at three independent points (no `peer://` streaming branch, workstation compute endpoint never mounted, health route does not exist); peer pairing is self-service token issuance with no confirmation; Voice Mode never turns spoken input into an agent turn and can never resolve the VOICE modality in production; the Wyoming TCP server is unauthenticated on `0.0.0.0:10400` by default.
- **The batch work recorded in `MASTER-TODO.md` is done** (U1–U6 all merged) but the file still lists it open. The real remaining backlog is the ten `REVIEW-RESULTS-REV-*` reports (REV-01/02/03 fixed, REV-04/05/06/08/09/10/11 essentially untouched) plus the new regressions found today.

---

## 2. Branch and worktree register

### 2.1 Unmerged branches (5)

| Branch | Worktree | vs main | Verdict | Detail |
|---|---|---|---|---|
| `feat/security-review-01` | `~/.config/superpowers/worktrees/Halbert/security-review-01` | 169 behind / 3 ahead | **MERGE** (packet SONNET-01) | `c5b6bb91` path allowlist for `get_config_value/structure/dependencies` closes a live arbitrary-file-read + canon-DB pollution on main (`config/queries.py:102-165` parses and persists any readable path). `9e057db7` redactor caps = defence in depth (its 9 tests already pass on main). `git merge-tree` **conflicts** in `halbert_core/tests/test_mcp_server.py` only (both sides appended test classes); server.py auto-merges. Resolved test file (90/90 with merged code) saved at `.handoff/audit-2026-09-01/security-review-01-merge-resolved-test_mcp_server.py.txt`. Behavioural consequence needing a founder call: the allowlist fails closed when `latest.json` is empty, and only Linux hosts with a config-registry start the ConfigWatcher that populates it (`SEC-05`). Do not commit the two untracked docs in that worktree (obsolete). |
| `feat/voice-mode-mark-v2` | `.../voice-mode-visual-ui` (10 dirty files) | 32 / 1 | **RETIRE** | Its one commit `25213235` is patch-identical (`git patch-id`) to `82543232` on `voice-mode-v2-backup`, which is an ancestor of main via `6f532ed2`; merge-tree into main yields main's exact tree. The 10 uncommitted worktree files are a strict subset of main (main additionally has the analyser-disconnect fix and one more test). Needs `git branch -D` (git sees it as unmerged by sha). |
| `feat/singular-entity-opus` | `.../opus-singular-tasks` | 76 / 7 | **RETIRE** | All 7 commits reached main via cherry-picks `e04ad14e`, `922122b2` then were superseded (`27fcfb95`, `330f641b`, `28df5910`, `de74e18a`, merge `15560fdb`). 7 of 13 touched files byte-identical, 6 strict supersets on main. Merge dry-run conflicts in 3 files; branch-unique content is only inferior earlier variants. `git branch -D`. |
| `worktree-u6-home-simplification` | `.claude/worktrees/u6-home-simplification` | 148 / 16 | **RETIRE** | Every commit has an equivalent on main from `feat/ha-simplification` (`a161bb9a`, `6a077653`, `226555ef`, `5e2ce6b4`, `6f46f09a`, `5f87520c`, `0514a5c3`, `3ce98551`, `092117dd`, `8545af94`); W14/W15/W16/W19 that its handoff lists as remaining are done on main. Merge dry-run: 34 conflicting files. Residue worth a 10-minute cleanup on main: dead `secure` resolution in `tier_router.py:162`, stale "three slots" comment in `config_wizard.py:692`, one missing test (secure turn skips the dedicated slot when `CAP_SECURE_MODEL` is absent). |
| `feat/rust-native-core` | `.../rust-native-core` | 43 / 3 | **PARK** (by direction) | 5-crate workspace under `crates/`; only `halbert-mqtt` has real code (rumqttc client + DashMap cache, 6 unit tests, no broker test, no reconnect backoff). `merge-tree` is clean; no CI covers `crates/`. **Local-only, no remote** — push it as a backup. Path collision: the branch committed `.handoff/REVIEW-REQUEST-RUST-NATIVE-CORE-2026-08-31.md` (382-line external review request) while main's untracked file of the same name is a different 360-line sanity review (`RNC-06`, §3.2). |

### 2.2 Fully merged (retire, verified strict ancestors of main)

Local: `docs/chat-ui-audit`, `feat/compute-peer-setting` (no worktree), `feat/ha-simplification`, `feat/halbert-mcp`, `feat/modality-voice-phase2`, `feat/rev03-sentient-home-fixes`, `feat/singular-entity`, `feat/voice-mode-visual-ui` (worktree `.claude/worktrees/voice-mode-opus`), `voice-mode-v2-backup` (worktree `voice-mode-reland`), `worktree-central-todo-batches` (7.0 GB worktree, 6.4 GB of it ignored `src-tauri/target`). Remote-only: `origin/feat/federated-fleet`, `origin/feat/plan-b-terminals`. Uncommitted content in these worktrees is noise: `halbert-mcp` holds a MASTER-TODO.md byte-identical to an older commit already on main; `chat-ui-audit` holds a 1-line README link to a gitignored 283-line precursor of `documentation/design/11-response-modality-handoff.md` (`U3-26` — confirm subsumed, then discard); four identical untracked `wt_pytest.py` copies (commit one canonical copy at the repo root first, `WT-01`).

Stashes: `stash@{0}` (peer provider registration) and `stash@{1}` (PeerPairingModal one-liner) are both already on main — drop.

Not a worktree: `~/.config/superpowers/worktrees/Halbert/home-automation` is a 128 KB leftover of three edited files from 2026-08-28 (no `.git`). Its `app.py` lines 578-610 and 661-670 are the only existing draft of `HomeCognitiveLoop` startup wiring (`LOOP-01`); save those lines if the founder chooses to wire the loop, then delete the directory.

Orphan commit `5057e893` is a reset-and-recommitted duplicate of `31fa91ef`; the REV-02 results doc content is identical to main's. The earlier audit's claim that it carries six extra findings is wrong.

Disk reclaimed by the full retire list: about 11 GB. Exact command sequence: packet SONNET-02 §3.

### 2.3 Continuous-conversation and Plan B

`feat/continuous-conversation` was merged (`c1840008`, `ddf22122`) and its worktree removed; `feat/plan-b-terminals` merged at `0ba316b2`. Both landed as primitives, not wiring (§6.4).

### 2.4 Corrections to the earlier audit (`HANDOFF-BRANCH-AND-WORKTREE-AUDIT-2026-09-01.md`)

1. "merge-tree clean" for `feat/security-review-01` — **false** since `0f750c3a`; one test-file conflict.
2. "5057e893 carries 6 new REV-02 findings incl. autonomy escalation" — **false**; identical to `31fa91ef`, and that F1 is fixed on main by `0f750c3a` (17 phrase-gate tests pass).
3. "voice-mark lineages need reconciling; neither is an ancestor of the other" — **false**; main already contains both, byte-for-byte.
4. "two untracked docs in security-review-01 worktree: PROGRESS + RECONCILIATION" — PROGRESS is committed on the branch (`a09632e1`); the untracked pair is RECONCILIATION + an obsolete pre-revision HA-simplification draft.
5. It never mentions REV-04/REV-06, the state machine, terminals, or the Python baseline — the largest body of real defects.

---

## 3. Ready to merge or commit

### 3.1 Merge: `feat/security-review-01` → packet SONNET-01
Recipe verified in scratch against `4a7bf71f`: merge; resolve `halbert_core/tests/test_mcp_server.py` by keeping main's `TestAutonomyEscalationPhrase` + `TestHighRiskProposalPhrase` then appending the branch's `TestPathAllowlist`, plus the branch's two 3-line `_load_latest_snapshot` monkeypatch inserts; keep main's `TestProtocol` (18 tools). Merged security suites: 90/90 + 500/500. Re-verify if main has moved.

### 3.2 Commit: the dirty `main` working tree → packet SONNET-02
Pre-steps (verified): delete the resurrected, unreferenced `halbert_core/halbert_core/dashboard/frontend/src/components/brand/HalbertMark.tsx` (main deleted it in `493956ab`; something re-created it at 08:41 today — **do not commit**); fix the dropped word at `packages/design-system/src/primitives/HalbertMark.tsx:45` ("Overrides `density` if provided."); align the story labels (`stories.tsx:50` says "Proposed Small", `:108` says "Proposed Micro"); resolve the `REVIEW-REQUEST-RUST-NATIVE-CORE-2026-08-31.md` name collision (recommended: commit main's copy under the current name, and rename the branch's file when that branch is next touched — keeps 7 cross-references intact); drop or scrub the machine path in `PAUSE-STATE-RUST-ROADMAP-AUGMENTATION-2026-08-31.md`.

Commits (no trailers):
1. `feat(design-system): HalbertMark explicit line counts via lines prop; density aliases preserved` — `HalbertMark.tsx`, `HalbertMark.stories.tsx`, `primitives.test.tsx` (23/23, `tsc` clean, 70/70 package suite).
2. `feat(brand): 5/7/8-line mark variants` — only the 15 genuinely new `assets/brand/halbert-mark-{5,7,8}lines*.svg`; the other 20 are byte- or whitespace-duplicates of the tracked `display/medium/compact/small` set and must not be committed as a parallel naming scheme (`VMK-09`). Add `-charcoal` variants for 5/7/8 or amend `assets/brand/README.md:31`, and add README rows.
3. `docs(rust): apply sanity review — 72-task plan, FFI waves, Docker track, scoping amendments` — plan doc, HA-STRATEGY doc, `MASTER-TODO.md` (its entire diff is the one Rust hunk), the review doc, optionally PAUSE-STATE.
4. `docs(handoff): semantic-audit proposal and 2026-09-01 audits` — semantic-audit handoff (note its `~/.gemini` reference is a dead external link and `halbert_core/cli/` does not exist at that path), plus this document, its appendix, the dispatch packets, and `REVIEW-REQUEST-SHELL-ARCHITECTURE-AND-ENTITY-NAV-2026-09-01.md` (a 795-line design-stage review request a concurrent session wrote at 18:31 today; not covered by this audit — it asks for a Fable-level design review of the shell architecture and entity-aware navigation before any code).

### 3.3 Small, well-specified fixes that unblock the most tests (→ OPUS-01, first hour)
- `R06-F2` hoist `response_modality = "text"` above `if self.prompts:` in `agents/state_machine.py` (`:2743` vs `:2761`) — clears 24–33 failures.
- `R06-F1` reset `self._defanged_query` at the top of `process()` under the turn lock (currently reset at `:2701`, after the next turn's PLANNING has read it at `:1519`) — clears `test_thread_e2e` and stops the live prompt leak.
- `R04-F8` add `speaker_role="admin"` to the three `fake_execute` doubles (`test_terminal_e2e.py:142`, `test_state_machine_turn_lock.py:308`, `test_state_machine_turn_persistence.py:119`).
- `R06-X1` add `"secure": False` to the two expected dicts in `test_state_machine_meta_tools.py:356, :550-552`.
Together ≈ 31 of the 71 baseline failures.

---

## 4. Test and CI health (main `4a7bf71f`)

| Surface | Result | Notes |
|---|---|---|
| design-system vitest / tsc | 70/70, clean | with the uncommitted HalbertMark changes applied |
| model-picker vitest / tsc / boundary | 103/103, clean, clean | |
| dashboard vitest / tsc | 699/699 (65 files), clean | 35 of 136 components/pages have a test; all 16 pages untested |
| Python full suite | 71 failed / 4,509 passed / 41 skipped | list: `audit-2026-09-01/pytest-main-failed-4a7bf71f.txt`; triage: `PYTEST-BASELINE-TRIAGE.md` |
| CI `design-tokens` job | **red** | `scripts/check_literal_colors.py --check` exit 1: 11 files gained literal palette classes since the 2026-08-27 baseline (StateBadge, NodeFleetCockpit 0→20, DeviceCard 0→15, AcousticAnomalyModule, VisionTab, …) |
| CI Python job | **red since 2026-08-29** | installs `[dashboard,dev]`, never the `vision` extra → 13 cv2 tests fail in CI (`test_cv_extensions`, `test_vision_tools`); plus the REV-06 seams. `gh` is not installed locally, so the remote run status was not read |
| CI suite census | green | every tracked test file is gated |
| Rust (`src-tauri`) | compiles test binaries offline, 0 warnings; **no CI job**; 28 tests never run in CI | |
| Playwright e2e | 2 smoke scripts, not in CI, need a live backend | |

Python failure triage (71): **real regressions 38** — `R06-F2` (33), `R06-F1` (2), App Store dependency-licence gate red (2: 8 unregistered deps + `scripts/check_appstore_deps.py:74-86` counts the self-referential `halbert-core[...]` extras), `lib/peerApi.ts:122` bare `/api/peers|fleet` fetches that 404 in the Tauri webview (1). **Environmental 13** (cv2). **Test rot 10** (three `speaker_role` doubles; three CRAG `secure` kwarg expectations; `test_llm_discover` pins two engines but `apple_foundation` is a third; `test_multi_instance::test_instance_info_home` predates REV-03 F8; two parse-count tests count `being.yml` loads). **Order-dependent 10** (6 from the process-wide `CapabilityRegistry` singleton probing the developer's real `models.yml` and never being reset — add an autouse `reset_registry()` fixture; 4 from `asyncio.get_event_loop().run_until_complete` in sync tests under `asyncio_mode=auto`, `test_peer_tool_proxy.py:264-311`).

Hidden by the pollution: `test_auto_provision.py` fails 4/11 **in isolation** and passes in the full run only because an earlier test warms the registry — CI's red set differs from local.

---

## 5. Batches and packets: what is actually done

| Batch | MASTER-TODO says | Reality on main |
|---|---|---|
| U1 security | tests missing, verification pending | Done (`5a132654`): `test_tier2_guarantee.py`, `test_security_roles.py`, `test_cli_security.py`; dispatch choke point, CORS, server-side phrase all verified. Rebuild script exists but **targets the legacy `halbert-host` project**, and the operational unredacted rebuild has **never been run** (staging tree last written 2026-08-24). |
| U2 voice | all four TASK-07 fixes undone | Wyoming `speaker_role`, per-turn UUID, `conversation_id` threading, ThreadManager injection, BargeIn wiring done. Still open: satellite replies send raw markdown to TTS (`U2-05`), `<speech>` defanging (`U2-07`), modality-context XML (`U2-09`), and the whole voice-out chain is unreachable (`U2-15`). |
| U3 frontend | all open | Done: Settings 3,291→880 lines, 10 tabs, 3-domain rail, `/security`→`/findings`, `useTokenBuffer`, ARIA. Not done: lazy tab mounting, shell <300 lines. |
| U4 routing | mostly open | Done: `HALBERT_MODEL`, GPU tools (raw Ollama call gone), role taxonomy. Not done: GPU module cards (steps 3-5), dead `routes/gpu.py` endpoints, CUDA doc written to a directory nothing indexes (`U4-08`), role scopes unreachable because no template scope carries `assigned_to_role` (`U4-14`/`RAG-06`), Swift bridge has no source anywhere (`U4-20`), and Apple Intelligence provisioning is **regressed** (§6.6). |
| U5 founder | founder-gated | Drafts committed; nothing ratified (§7). |
| U6 home simplification | all unchecked | Fully merged (`4e4ff2f4`, `93c863c1`, D4 `8545af94`); D2/D3/D4/Q3/Q4 resolved by AI sessions and awaiting ratification. Two later P1 regressions on its seams (§6.6) and the Frigate queue cap + snapshot routing follow-ups not landed. |
| REV-01/02 | — | 11 of 12 closed. Open: `R1-F4` MCP `set_autonomy_level` still does an unlocked load→modify→save (`mcp/server.py:644-669`; the locked composite exists but was never wired in), `R2-P3` id-less `tools/call` still executes, `R2-P1/P2/P4/P5`, `R2-F6` decision. |
| REV-03 | fixed | 11 of 14 fixed. Not working: audio-chunk drain reads `payload_length` from the wrong JSON level (`wyoming_agent.py:291`, reproduced), Wyoming cross-loop stop calls `Server.aclose()` which does not exist on Python 3.10 (reproduced), `HomeCognitiveLoop` still never instantiated. |
| REV-04/05/06/08/09/10/11 | not tracked | **Nothing remediated.** Every confirmed finding reproduces on `4a7bf71f`. §6. |

---

## 6. Incomplete work by feature (verified on main; P0 = user hits it today or security)

### 6.1 Agent core (state machine) — packet OPUS-01
P0 `R06-F1` prompt leak; P0 `R06-F2` UnboundLocalError on the no-prompt-builder path (Wyoming and any non-dashboard constructor); P1 `R06-F3` SEARCHING ignores `retrieval_scope`/skill scope (`state_machine.py:2199`); P1 `R06-F4` failed chmod excluded from rollback (`findings/proposal_generator.py:265-277`, `:561-563`); P2 `R06-F5` `merge_thread` orphans `open_loops`/`terminal_blocks` rows (`conversation_sqlite.py:1820-1879`); P2 `R06-O2` `recall_memory`/`search_discoveries` silently substituted; P3 `R06-F6` Wyoming turn abandons `agent.process()` without `aclosing`; P3 `R06-F8` bare `except TypeError` retries retrieval unscoped (`context/assembler.py:600-604`). Test hygiene: `R04-F8`, `R06-X1`, autouse registry reset (`U6-TEST-01`), `SE-11` event-loop tests.

### 6.2 Voice (Voice Mode, Wyoming, audio pipeline) — packet OPUS-02
Doc 16's task list (F1–F5, O1–O9, P1–P4, G1–G4) is complete on main and P4 did get its two-stage review (`88413a42`; the results handoff and a memory note saying otherwise are stale). What is missing is the loop itself:
- P0 `VM-STT` spoken input never becomes a turn: `coordinator.on_voice_turn` is never set (`app.py:654-722`), `VoiceMode.tsx:32-35, 333-338` explicitly submits nothing on end-of-speech. Voice Mode is a keyboard mode with a reactive mark.
- P0 `U2-15`/`R9-F05` production never resolves VOICE: `channel_capability.py:150` imports a nonexistent `get_audio_pipeline`; `set_audio_pipeline`/`set_wyoming_active` have zero callers; so `speech_segment`, the TTS egress hook (`should_speak()`), the speaking state and the HUD relay are unreachable.
- P0 `R9-F01` Wyoming TCP unauthenticated, `0.0.0.0:10400`, `WYOMING_ENABLED` default `1`, not capability-gated, turns run at `speaker_role="unknown"` with MEDIUM tools allowed.
- P1 `R9-F02` Wyoming turns on a second event loop with a per-loop turn lock (`app.py:763-765`, `state_machine.py:341-345`); P1 `R9-F03`/`U2-14` VAD fed 480-sample frames while Silero needs 512 (`audio/pipeline.py:334`, `vad.py:164-166`) — live now that the coordinator boots in `app.py`; P1 `R9-F04` enrolled voiceprints never loaded into the matcher; P1 `U2-05` satellite replies send raw markdown to HA TTS; P1 `R3-F04` audio-chunk drain key; P2 `R3-F10b` `Server.aclose()`; P2 `R9-F06/F07/F08/F10/F13`, `U2-07` `<speech>` defang, `U2-09` modality-context XML; P2 `U6-BUG-03` Frigate mapper queue unbounded (HA's was capped); P2 `U6-BUG-04` Frigate snapshots returned as base64 strings, never routed to the vision model.
- Verification: no real-audio run has ever happened (sherpa-onnx/openwakeword not in the venv, `AudioConfig.enabled` default False, all 185 backend tests use stubs); hardware matrix 0/22 (`VM-15`, `HW-01`, its "not yet built" notes are stale). Decisions: Python consumer for the Rust AEC socket 18400 (`VM-22`), `macos-private-api` channel (`FDR-08`).

### 6.3 Compute peer, Devices, federation (singular entity) — packet OPUS-03
The merge `15560fdb` landed all seven phases as code units with tests, but the feature is not usable end to end and the plan doc's "Status: COMPLETE" overstates it:
- P0 `ROUTE-01`/`R10-N1` devices router mounted at `/devices/*` (`app.py:306`, no prefix) while the frontend and tests use `/api/devices/*` → Settings › Devices dead; `DELETE /devices/{id}` needs no auth at all.
- P0 `SE-09`/`R10-F2` workstation compute endpoint never mounted; broker `NotImplementedError` (`compute_endpoint.py:265`, `compute_broker.py:166/202/218`) → a home node linked via ComputePeerCard gets 404 on every turn.
- P0 `SE-16`/`R10-F1` pairing returns the PIN to the requester and `/verify` issues a bearer with no confirmation/expiry/rate limit (`routes/peers.py:159-251`); P0 `SE-15` UI pairing cannot succeed (mDNS list hardcoded `[]`, manual tab throws, token never reaches the other machine's `being.yml`); P1 `R10-F5` any peer can revoke any other.
- P1 `R05-F1` no `peer://` branch in `_stream_turn` (`routes/agent.py:1065-1110`); P1 `R10-F3`/`SE-08` three components disagree on the health route and `/api/compute/v1/health` exists nowhere; P1 `SE-05` `ComputeRouter.route()` is never instantiated by production code (chat still uses TierRouter via `app_seam.py`); P1 `SE-10` PeerToolProxy never injected; P2 `SE-12` deferred queue unbounded, replay unimplemented; P1 `SE-28` no two-machine test exists. Also P1 `PERS-02` two persona sources of truth (`/switch` vs `/activate`).

### 6.4 Terminals — packet OPUS-04
P0 `R04-F1` `spawn_session` (`routes/terminal.py:320`) passes no `kind`, so every tile is `oneshot` with a 60 s TTL and the WS route never calls `attach_client` → the reaper (`app.py:642`) kills a quiet shell. P1 `R04-F3` pool leaks a busy slot on error (`streaming/agent_pool.py:131-206`); P1 `R04-F4` `block_output` unbounded (~800 MB reproduced by the review); P2 `R04-F7` `/api/terminal/exec` unbounded timeout/output; P2 `R04-F5/F6`; P3 `F10-F13`. Built-but-unwired, needing a decision not code: watched-shell → thread pipeline (`R04-F2`), agent PTY pool (only tests enable it, `R04-POOL`), somatic block pipeline (`R04-F9`), `TasksColumn`/`YourShellRegion` never mounted (`TERM-08`), subagent seams (`R06-O3`).

### 6.5 Chat UI and frontend — packets OPUS-05 (streaming hook) and SONNET-04 (mechanical)
P1 `R11-01` every completed turn aborts its own SSE stream and POSTs `/api/agent/cancel` (`useAgentStream.ts:379-390`); P2 `R11-02` queued send bypasses parked-turn guards and drops pending approvals (`AgentChat.tsx:561-592`); P2 `R11-03` side effects inside the `setSession` updater; P1 `R08-01` Approvals and six other routed pages have no nav entry (`Layout.tsx:70-91`); P1 `R08-04` literal-colour ratchet red; P2 `R08-02` NavRail ARIA tabs half-implemented; P1 `ROUTE-02` BeingTab double `/api`; P1 `ROUTE-03` AudioSettings `/api/being`; P1 `peerApi.ts:122` bare URLs; P3 a11y residuals `R11-05..13`; chat-ui audit P0/P1 sprints are done, P2 D3 streaming markdown open.

### 6.6 Model routing, capability registry, Apple Intelligence — packet SONNET-03
P1 `U4-18`/`R05-N1`/`U6-BUG-02` the F5 refactor (`330f641b`) gated auto-provisioning, the wizard's secure write and `routes/llm.py:219` on `has_capability(CAP_SECURE_MODEL)`, whose probe (`capabilities.py:192-204`) means "a secure model is already configured" — circular; fresh installs can never provision. P1 `U6-BUG-01` registry resolves the variant from `being.yml` only, ignoring `HALBERT_VARIANT` (`capabilities.py:264-267`) → the documented env-only home deployment gets the sysadmin preset. P1 `CAP-01` `CAP_SOURCEPREP` probes `import sourceprep` but the adapter talks to a daemon over HTTP → retrieval silently disabled on this dev box. P1 `R05-F2` slot assignment ignores `apple_intelligence_bridge_running`; P1 `U4-20` no Swift bridge source exists → hide `apple-foundation` until it does. P1 `R05-F3` `GET /api/llm/config` returns provider API keys in plaintext. P2 `STUB-01` `tier_router.py:381` OpenAI branch raises `NotImplementedError`; P1 `PICK-02` `routes/compression.py` writes `models.yml` around the store; P2 `PICK-04` delete `cascade_router.py`; P2 `U6-DESIGN-01` "probe beats preset" silently re-enables SourcePrep on home nodes where the package is importable (ratify or override).

### 6.7 Security residuals — packet SONNET-01
`SEC-01/SEC-03` merge; `R1-F4`; `R2-P3`; `SEC-04` run the unredacted rebuild (after retargeting the script to the unified `halbert` project, `SEC-03` in F17); `SEC-11` real canon DB contains only pytest tmp paths (a conftest should redirect `CANON_DIR/SNAP_DIR/RAW_DIR`); `SEC-14` SourcePrep daemon answers `/projects` without a bearer; `R2-P1/P2/P4/P5`, `R2-OBS-1` dead `camera_gate.py` advertised as live.

### 6.8 Knowledge / RAG / corpus — packet SONNET-05 (+ founder)
`RAG-01` the daemon-side halves of the scope fix (LOD skip for doc-role chunks, `scope_mode=hard`) exist only as **uncommitted edits in the CoDRAG checkout** the running daemon happens to execute — any clean launch reverts Halbert to 1-chunk file-head responses; `RAG-06`/`U4-14` role scopes unreachable (no `assigned_to_role`); `RAG-13` `*.jsonl` gitignore hides 13 corpus files (71 MB) so a fresh clone cannot rebuild the corpus while RAG-DATA-SOURCES claims it can; `RAG-14` no way for a new install to obtain the ~20-hour index; `RAG-12`/`LEG-GATE` licence manifest red; `RAG-19/20` `documentation/GAPS.md` and `RAG_AUDIT_REPORT.md` describe the retired ChromaDB era; `RAG-21` legacy ChromaDB doc indexing still exposed in Settings/CLI but no longer feeds the agent.

### 6.9 Home automation residue
`LOOP-01` `HomeCognitiveLoop` never instantiated (instantiate or delete); `U6-25/26/27/28` cosmetic residue incl. `llm_config` still checking the retired `home-light`; `R3-F02-T` no tests for the chat-path AutonomyGate.

### 6.10 Older workstream leftovers
Continuous conversation: `CC-02` SendToChat "new conversation" affordance produced by a dozen callers and consumed by nothing; Plan C (background tasks, notifications) not started. Model picker: `PICK-02/03/04/05`. Multi-persona: `PERS-02/03/05`. Marketing web-v7: the early-access form is a client-side no-op (`MKT-03`), no new stops, eight founder questions open. Semantic audit: doc-only, not started, three founder forks. Python baseline: `>=3.10` in metadata/venv vs `3.11+` in README/INSTALLATION/CI (`ENV-01`).

---

## 7. Founder decisions (full sheet: `DISPATCH-2026-09-01-FOUNDER-DECISIONS.md`)
Legal/App Store `FDR-01..04` (drafts exist, nothing ratified; two conflicting §7 exception texts in tree; bundle identifiers disagree in three places), copyright year and `-or-later` (`FDR-05/06`), open-core boundary (`FDR-07`), `macos-private-api` channel (`FDR-08`), `SEC-05` fail-closed MCP config queries on macOS, U6 D2/D4/Q3/Q4 ratification, `U6-DESIGN-01`, `LOOP-01`, `R04-POOL` and the watched-shell/Plan B wiring (`R04-F2`, `TERM-08`), `SE-05` wire ComputeRouter or defer, `VM-22`, `VM-01/02` parked voice calls, 7-line/4-line mark candidates (`MD-04`) and SVG naming (`VMK-09`), `RNC-06` doc name, recording the Rust deferral in the roadmap (`HA-01`), semantic forks (`SEM-01..03`), `RAG-13/14` corpus distribution, `ENV-01` Python floor, marketing Q1–Q8, dependency-licence classes that turn out copyleft, hardware runs (`HW-01..04`).

---

## 8. Documents that are wrong and should be corrected (→ SONNET-05)
- `MASTER-TODO.md`: U1–U6 rows and §3 open loops are stale wholesale (everything in §5 above); no entries at all for REV-04/05/06/08/09/10/11 remediation, for `feat/singular-entity-opus`, or for Voice Mode visual UI.
- `IMPL-PLAN-SINGULAR-ENTITY-TASKS-2026-08-31.md` "Status: COMPLETE" and Phase 7 acceptance ("pair through the UI, no YAML") are not met; its note that `test_cognition_tick_once` is order-sensitive is wrong (deterministic `R06-F2`).
- `HANDOFF-VOICE-MODE-OPUS-RESULTS-2026-09-01.md`: "O3 TTS egress end-to-end" is only true under a mocked modality; "P4 unreviewed" caveat is stale (`88413a42`); line 12's "confirm before touching design-system voice files" is stale.
- `REV-03-RESUBMISSION-2026-08-31.md` / `HANDOFF-WRAP-UP-2026-08-31.md` overclaim REV-03 F3/F4/F10; `HANDOFF-CENTRAL-TODO-BATCHES` "28/28 Apple PASS" predates the F5 regression.
- `HARDWARE-VALIDATION-MATRIX-2026-08-31.md` notes say P2/O3/O5 are unbuilt — all on main.
- `documentation/FEATURES.md`: Backend API table lists eight endpoints that do not exist; scanner table names missing files; Settings/Chat/Terminal/Debug describe a UI that is gone; Anomaly Detection / Recovery Playbooks / Dry-run Simulation / Why Brain presented as available but are backend-only or unwired.
- `documentation/GAPS.md`, `RAG_AUDIT_REPORT.md`, `design/prebuilt-knowledge-index.md`: ChromaDB-era, argue against the architecture that shipped.
- `RAG-DATA-SOURCES-2026-08-24.md` §1.1 "all 53 JSONL files committed" (45 tracked, 13 ignored).
- `documentation/design/unified-model-picker.md` lacks its "Superseded 2026-08-26" header; four workstream docs still say DRAFT/awaiting input for merged work.
- `TASK-PACKET-03/09` headers, `LEGAL-AND-LICENSING-TODO.md:74` "currently passing".
- `CODEINDEX-BUILD-LOCK.txt` says a build is running; it finished 2026-08-26.

---

## 9. Dispatch

Sequencing: **SONNET-02 first** (stabilises main and the worktrees, commits the canonical `wt_pytest.py`), then **SONNET-01** (security merge). Opus packets start in fresh worktrees off the resulting main. SONNET-05 (doc resync) runs last, after the code packets report.

| Packet | Owner | Scope | Files it owns (others must not edit) |
|---|---|---|---|
| `DISPATCH-2026-09-01-SONNET-01-security-merge.md` | Sonnet | merge `feat/security-review-01`, `R1-F4`, `R2-P3`, retarget + run the unredacted rebuild | `mcp/server.py`, `ingestion/redaction.py`, `scripts/rebuild_sourceprep_unredacted.py`, security tests |
| `DISPATCH-2026-09-01-SONNET-02-commit-and-cleanup.md` | Sonnet | commit the dirty main tree, canonical `wt_pytest.py`, retire branches/worktrees/stashes/orphan dir, push backups | `packages/design-system/**`, `assets/brand/**`, the Rust docs, git refs |
| `DISPATCH-2026-09-01-SONNET-03-capability-registry-and-routing.md` | Sonnet | `U4-18`, `U6-BUG-01/02`, `CAP-01`, `U6-TEST-01`, `R05-F2/F3`, `U4-20(b)`, `STUB-01`, `PICK-02/03/04`, u6 residue | `capabilities.py`, `model/auto_provision.py`, `model/config_wizard.py`, `routes/llm.py`, `routes/compression.py`, `model/tier_router.py`, `model/cascade_router.py`, `tests/conftest.py` |
| `DISPATCH-2026-09-01-SONNET-04-frontend-mechanical.md` | Sonnet | `ROUTE-02/03`, `peerApi` bare URLs, `R08-01/02/03/04/05/07`, `CC-02`, `FEAT-02`, `U3-04` | `Layout.tsx`, `NavRail.tsx`, `BeingTab.tsx`, `AudioSettings.tsx`, `lib/peerApi.ts`, the 11 ratchet files, `SendToChat.tsx`, `Backups.tsx`, `Settings.tsx` |
| `DISPATCH-2026-09-01-SONNET-05-ci-tests-docs.md` | Sonnet | CI `vision` extra, Rust CI job, test rot (`llm_discover`, `multi_instance`, parse-cache), licence manifest + checker bug, `U4-08`, `U4-14`/`RAG-06`, doc corrections in §8, `MASTER-TODO.md` resync | `.github/workflows/ci.yml`, `config/dependency-licenses.yml`, `scripts/check_appstore_deps.py`, `sourceprep_template.yml`, `data/knowledge/**`, all `.handoff/*.md` and `documentation/**` |
| `DISPATCH-2026-09-01-OPUS-01-agent-core.md` | Opus | §6.1 | `agents/state_machine.py`, `agents/react_agent.py`, `context/assembler.py`, `findings/proposal_generator.py`, `agents/conversation_sqlite.py`, agent-core tests |
| `DISPATCH-2026-09-01-OPUS-02-voice-chain.md` | Opus | §6.2 | `integrations/channel_capability.py`, `integrations/wyoming_agent.py`, `integrations/modality_wiring.py`, `audio/**`, `dashboard/routes/audio.py`, `prompts/agent_prompts.py`, `integrations/frigate/**`, `VoiceMode.tsx`, `app.py` voice/wyoming bootstrap lines |
| `DISPATCH-2026-09-01-OPUS-03-compute-peer-and-devices.md` | Opus | §6.3 | `federation/**`, `dashboard/routes/peers.py`, `routes/devices.py`, `routes/agent.py` streaming dispatch, `model/providers/peer.py`, `persona/**`, `routes/persona.py`, `PeerPairingModal.tsx`, `DiscoveredPeerCard.tsx`, `app.py` router mounts |
| `DISPATCH-2026-09-01-OPUS-04-terminals.md` | Opus | §6.4 | `streaming/**`, `dashboard/routes/terminal.py`, `dashboard/routes/websocket.py`, `tools/executor.py` pool gate, `ContextStage.tsx`/`TasksColumn.tsx`/`YourShellRegion.tsx` (only if the founder decides to mount) |
| `DISPATCH-2026-09-01-OPUS-05-chat-streaming-hook.md` | Opus | `R11-01/02/03`, `R11-10/12/13`, `CUA-04` | `hooks/useAgentStream.ts`, `components/agent/AgentChat.tsx`, `MessageContent.tsx`, `ThinkingPanel.tsx`, `hooks/useTimeline.ts` |
| `DISPATCH-2026-09-01-FOUNDER-DECISIONS.md` | Founder | §7 | — |

Shared rules for every packet are repeated at the top of each file. Results go to `.handoff/RESULTS-<PACKET>-<date>.md`; only SONNET-05 edits `MASTER-TODO.md`.
