
### F1 R1-F4 — REV-01 F4: cross-process lost-update race on being.yml (relock silently reverted)
status=in_progress cat=bug prio=P1 conf=high act=True
REMAINING: Rewrite _tool_set_autonomy_level to call update_being_config(mutator) so the escalation check + write happen under one exclusive lock; add a test that a relock persisted between load and save is not clobbered by the MCP path.
EVID: 360effab adds being_config.py:458-590 flock + :728-755 update_being_config composite (docstring :735 names 'MCP set_autonomy_level' as an intended caller). Dashboard uses it: settings.py:3079-3150; devices.py:262,281,411. BUT mcp/server.py:644-669 `_tool_set_autonomy_level` still does `cfg = load_being_config()` (shared lock, released) ... `save_being_config(cfg)` (separate exclusive lock) — lock 
DOC: HANDOFF-CENTRAL-TODO-BATCHES §1 says 'REV-01 F4+F5 (360effab, 7e9ebaae): cross-process flock for being.yml (+ update_being_config composite)' as fixed; the composite exists but the MCP writer the finding is about was never migrated.

### F1 R1-OPS-1 — REV-01 §4 packet §5.2: run the unredacted SourcePrep rebuild with live egress self-check
status=blocked cat=deferred prio=P2 conf=medium act=True
REMAINING: Operational: run the script on the live host; exit 2 = boundary failed. Record the result in a handoff.
EVID: scripts/rebuild_sourceprep_unredacted.py exists on main (10471 bytes, 2026-08-31). Report said run it only after F1's invariant is settled — F1 is now settled on raw-by-design. Requires live SourcePrep daemon + PREP_DAEMON_TOKEN; not runnable in this audit (no daemon, prep tools prohibited).

### F1 R1-OPS-2 — REV-01 §4 packet §5.3: live scanner egress testing with mock API keys
status=not_started cat=test_gap prio=P3 conf=high act=True
REMAINING: Integration test on a macOS host: seed mock keys in the discovery scanners' inputs, run every scanner, assert nothing crosses mcp_response / the dashboard.
EVID: grep -rlniE 'mock.*api.?key.*scanner|scanner.*egress' halbert_core/tests/ → no matches. Branch doc SCOPE-01-SECURITY-REVIEW-PROGRESS §4 also lists it PENDING.

### F1 R2-F1b — REV-02 F1 residual: low-risk proposals still apply host config on confirm=true; phrase is a public constant
status=in_progress cat=decision prio=P2 conf=high act=True
REMAINING: Founder decision: (a) accept phrase-as-friction, or (b) forbid raising autonomy over MCP entirely / require a dashboard-issued one-time approval token, and (c) whether non-critical proposal execution over MCP should route through ApprovalEngine.
EVID: server.py:377 phrase branch only when `finding is None or finding.severity == 'critical'`; test_mcp_server.py:508 test_low_risk_proposal_without_phrase_allowed pins that non-critical proposals execute with confirm only; store.approve (findings/proposals.py:266) is called directly (:403), not via an ApprovalEngine request. security_constants.py:24 phrase is a repo-public literal, so the REV-02 thre

### F1 R2-F2b — REV-02 F2 secondary: no socket timeout on the HTTP handler (slowloris with a valid small Content-Length)
status=not_started cat=security prio=P3 conf=medium act=True
REMAINING: Set `timeout = <N seconds>` on _MCPHTTPHandler (BaseHTTPRequestHandler honours it as the socket timeout) and add a test.
EVID: grep -n timeout mcp/server.py → only ThreadingHTTPServer/daemon_threads at :1488-1494; _MCPHTTPHandler (:1124) sets no `timeout` class attribute, so rfile.read(content_length) blocks for a client that never sends the body. Rate limiter is consumed first (F3), which bounds it to 60 pinned threads/min/IP.

### F1 R2-F6 — REV-02 F6: FleetProxy needs raw peer token but PeersConfig stores only hashes
status=blocked cat=decision prio=P2 conf=high act=True
REMAINING: Design decision before federation-9.9: bidirectional pairing with a separate outbound-credential store (keychain/keyring or 0600 file), never plaintext in peers.json. Not a code fix yet.
EVID: d5ce2858 only adds a docstring: federation/fleet_proxy.py:158-175 TODO(federation-9.4) token-custody design required; get_fleet_proxy still raises NotImplementedError (:180). No custody store exists.
DOC: HANDOFF-CENTRAL-TODO-BATCHES lists d5ce2858 among 'REV-02 F1–F5 … fixed'; it is a TODO note for F6, not a fix (the handoff wording is ambiguous, not wrong).

### F1 R2-P1 — REV-02 P1: verify_token iterates the peer dict without the lock while add_peer mutates in place
status=not_started cat=bug prio=P2 conf=high act=True
REMAINING: Iterate `list(self._peers.values())` or implement the copy-on-write replacement the docstring promises. One line + a test.
EVID: federation/peers_config.py:342 `for peer in self._peers.values():` outside self._lock; add_peer :381-407 mutates `self._peers[node_id] = cred` under the lock (not copy-on-write as the module docstring claims). Concurrent pairing + authed request → RuntimeError: dictionary changed size during iteration → 500.

### F1 R2-P2 — REV-02 P2: synchronous atomic file write on every authenticated peer request inside the async event loop
status=not_started cat=bug prio=P3 conf=high act=True
REMAINING: Throttle (monotonic timestamp, write at most every N s) and/or offload the write; remove the TODO.
EVID: federation/peer_middleware.py:160-161 `config.update_last_seen(peer.node_id)` in async require_peer_auth; peers_config.py:511-522 still saves every call with the TODO(federation-9.1) comment intact.

### F1 R2-P3 — REV-02 P3: tools/call notifications execute side-effectful tools with no acknowledgment
status=not_started cat=security prio=P2 conf=high act=True
REMAINING: Reject `tools/call` without an id (-32600 or silently ignore) before invoking the handler; update the pinned test.
EVID: mcp/server.py:1043-1061: handler runs (`result = mcp_response(handler(tool_args))`) and only then `if is_notification: return None`. test_mcp_server.py:261 test_notification_tools_call_no_response pins the no-response behaviour, not non-execution. An id-less approve_proposal/set_autonomy_level still executes (HTTP 202).

### F1 R2-P4 — REV-02 P4: stdio transport has no line-size limit
status=not_started cat=bug prio=P3 conf=high act=True
REMAINING: Read with a bounded buffer (e.g. reject lines > _MAX_REQUEST_SIZE with -32600).
EVID: mcp/server.py:1094-1096 `for line in sys.stdin:` then json.loads(line) — no length guard.

### F1 R2-P5 — REV-02 P5: Authorization scheme match is case-sensitive ('bearer x' → 401)
status=not_started cat=cleanup prio=P3 conf=high act=True
REMAINING: Case-insensitive scheme match (`auth[:7].lower() == 'bearer '`). Fails closed today, so security-neutral.
EVID: mcp/server.py:1155 `auth.startswith("Bearer ")`.

### F1 R2-OBS-1 — REV-02 §5: mcp/camera_gate.py is dead code while mcp/__init__.py still advertises it as a live guarantee
status=not_started cat=cleanup prio=P3 conf=high act=True
REMAINING: Decide: wire gate_response() into the dispatch choke point (and register the tools) or delete the module + its test; fix the package docstring either way.
EVID: grep -rn 'camera_gate|gate_response|verify_bearer_token' halbert_core/halbert_core → only mcp/__init__.py:15 (docstring) and the module itself; server.py:683 TOOL_HANDLERS registers none of its handlers and never imports it. mcp/__init__.py:8 also names a non-existent `_mcp_response()` and :15-17 claims 'no raw frames … ever leave the local host through MCP'. tests/test_mcp_camera_gate.py tests th

### F1 R2-DOC-1 — REV-02 §4 packet §5.2: documentation/guides/mcp-setup.md client config snippets
status=not_started cat=doc_only prio=P3 conf=high act=True
REMAINING: Write the setup guide (stdio + HTTP/bearer + SSE) for Claude Desktop/Cursor/Warp with the 32-char token requirement and CORS note.
EVID: find documentation -iname '*mcp*' → only documentation/experimental/OS-NATIVE-MCP-WARP-AND-SOURCEPREP-INTEGRATION.md; documentation/guides/ has no mcp-setup.md.

### F1 R2-TEST-1 — REV-02 §4 packet §5.3: concurrency pressure tests for concurrent tool execution / SQLite locks
status=not_started cat=test_gap prio=P3 conf=medium act=True
REMAINING: Add a ThreadPool harness firing mixed tools/call + pairing, assert no 500s and no dict-mutation errors.
EVID: grep for concurrency in tests/test_mcp_*.py → only test_mcp_http.py (one threaded unauthenticated-flood test :303). No concurrent tools/call harness; P1/P2 would be caught by one.

### F1 SR1-01 — Unmerged c5b6bb91 (feat/security-review-01): MCP config-query tools accept arbitrary paths — reproduced on main, and raw canon persistence compounds it
status=in_progress cat=merge_ready prio=P1 conf=high act=True
REMAINING: Merge feat/security-review-01 (c5b6bb91 + 9e057db7) into main; resolve the test_mcp_server.py append-conflict (keep both TestPathAllowlist and the escalation/proposal classes); run test_mcp_server.py, test_tier2_guarantee.py, test_mcp_response_boundary.py, test_redaction_gaps.py. Consider also refusing _write_canon for paths not in the manifest as defence in depth.
EVID: main mcp/server.py:188-255 has no _is_allowed_config_path (grep 'allowlist|realpath|manifest' → 0 hits); queries.py:102-124 _get_current_canon re-parses any live path and :127-144 _write_canon persists it. Sandboxed probe (scratchpad probe_path.py, CANON_DIR/SNAP_DIR redirected): _tool_get_config_structure on a never-staged file returned its keys/types; get_config_value returned the raw non-secret
DOC: REV-02 §2 marks tier routing/get_config_value PASS and states the reviewed tree 'includes the feat/security-review-01 merge 297ceb67' — 297ceb67 (2026-08-30) predates c5b6bb91/9e057db7 (2026-08-31 08:08), so the allowlist gap was never evaluated. SCOPE-01-DUPLICATE-WORK-RECONCILIATION.md (untracked 

### F1 SR1-02 — Unmerged 9e057db7 (feat/security-review-01): redactor base64 size/depth caps + recursive nested-JSON leaf redaction
status=in_progress cat=merge_ready prio=P2 conf=high act=True
REMAINING: Merge with SR1-01; run test_redaction_gaps.py / test_redact.py / test_redaction_secrets.py.
EVID: main ingestion/redaction.py:1311-1333 _redact_base64_secrets has no token-size cap and re-enters redact_text(decoded) with no depth bound; :1270-1298 _redact_nested_json handles flat objects only. Probe on main: 1 MB base64 of plain ASCII costs ~1.0 s per redact_text call; nested docker `{"auths":{...{"auth":"…"}}}` is ALREADY over-redacted by the line pass to `{<secret>}` (so the 'leaf leak' half
DOC: Branch doc SCOPE-01-SECURITY-REVIEW-PROGRESS.md §2 #6 frames nested-JSON leaf redaction as a leak fix; on main the line pass already catches that shape conservatively. REV-01 rated the backstop 'Strong' and did not flag the missing base64 caps.

### F1 SR1-03 — feat/security-review-01 docs: a09632e1 progress doc (committed, unmerged) + 2 untracked handoffs in its worktree
status=in_progress cat=needs_commit prio=P3 conf=high act=True
REMAINING: When merging the branch, commit or discard the two untracked docs. The reconciliation doc's plan steps 2–5 (cherry-pick 5a132654/5057e893, create REV-02 work items) are obsolete — all of that is already on main via the central-todo merge; only its Step 1 (merge the two commits) still applies.
EVID: a09632e1 adds .handoff/SCOPE-01-SECURITY-REVIEW-PROGRESS.md (merges with the branch). Untracked in ~/.config/superpowers/worktrees/Halbert/security-review-01: .handoff/SCOPE-01-DUPLICATE-WORK-RECONCILIATION.md (2026-08-31) and .handoff/HANDOFF-HOME-AUTOMATION-SIMPLIFICATION-2026-08-30.md (out of this scope; may overlap main's HA-STRATEGY doc).
DOC: SCOPE-01-DUPLICATE-WORK-RECONCILIATION.md: 'clean merge, no conflicts' (now a test-file conflict); REV-02 F1–F5 listed as 'neither effort fixed yet' (all fixed on main since).

### F1 NEW-01 — NEW: _egress_ack marker honoured on any dict at any depth of an MCP payload, not only get_config_value's top-level result
status=not_started cat=security prio=P3 conf=low act=True
REMAINING: Hardening: honour the marker only on the top-level dict of the get_config_value result (or strip EGRESS_ACK_FIELD from every nested dict before rule evaluation), plus a test.
EVID: mcp/response.py:138 `egress_ack = d.get(EGRESS_ACK_FIELD) is True` inside the recursive _redact_dict, applied to every nested dict. Today no tool returns parsed config trees with values (get_config_structure replaces leaves with type names, queries.py:347), so there is no live path; a future tool that returns raw parsed trees would let a staged file containing a literal `_egress_ack: true` beside 

### F1 DOC-MASTER-TODO — MASTER-TODO.md on main still describes U1 security tests as missing and phrase/CORS verification as pending
status=obsolete cat=doc_only prio=P3 conf=high act=True
REMAINING: Strike U1 items; add the open items from this audit (R1-F4 MCP caller, R2-F1b decision, R2-P1/P3, SR1-01/02 merge, camera_gate, mcp-setup.md).
EVID: `git show main:.handoff/MASTER-TODO.md` :27 'missing security tests (test_tier2_guarantee.py, test_redactor.py, test_security_roles.py do not exist)' and :103 'Verification of the dispatch egress gate, CORS default-deny, and server-side phrase enforcement still pending'. On main: tests/test_tier2_guarantee.py, test_security_roles.py, test_cli_security.py exist and pass; REV-01 §3 and REV-02 §4 rec
DOC: MASTER-TODO claims tests do not exist / verification pending; both are done on main.

### F2 R06-F2 — REV-06 F2: `response_modality` UnboundLocalError on every RESPONDING entry when no prompt builder (24 of 30 red agent-core tests)
status=not_started cat=bug prio=P0 conf=high act=True [V:confirmed]
REMAINING: Hoist `response_modality = "text"` (and the modality_ctx resolution) above `if self.prompts:` in `_handle_responding` so both arms see it. Re-run the eight files; expect ~24 failures to clear. Production dashboard is safe today only because `get_agent()` always wires a prompt builder; Wyoming/other constructors without one hit this on every turn.
EVID: halbert_core/halbert_core/agents/state_machine.py:2743 `response_modality = "text"` is inside `if self.prompts:` (2741); the `else:` branch at 2760-2762 calls `self._build_simple_response_prompt(response_modality=response_modality)`. `git blame -L 2759,2763` => 2f595bc0 (2026-08-30, 'refactor(modality-voice): Phase 2.5'), on main (`git merge-base --is-ancestor` OK). Test run from main: `pytest tes
DOC: REV-06 report says '~27 x F2' and lists test_agent_integration.py / test_agent_chat_off_the_event_loop.py among the red suites; on main the count is 24 and those two files have 0 failures.
VERIFY: confirmed — Re-read main HEAD 4a7bf71f state_machine.py: `response_modality = "text"` is at :2743 inside `if self.prompts:` (:2740); the `else:` arm at :2759-2762 calls `_build_simple_response_prompt(response_modality=response_modality)` with the name unbound. `git blame -L 2740,2765` => the hoist-needing lines are 2f595bc0 (2026-08-30, on main). Test run from main (arch -arm64 .venv pytest, 9 files incl. tes

### F2 R06-F1 — REV-06 F1: previous turn's question leaks into the next turn's PLANNING prompt (`_defanged_query` reset too late)
status=not_started cat=bug prio=P0 conf=high act=True [V:confirmed]
REMAINING: Move the reset to the top of `process()` under the turn lock (next to `self.cancelled.pop`), or store the defanged query on `StateContext` per-turn instead of on `self`. Re-run test_thread_e2e.py (2 tests).
EVID: state_machine.py:1519 `query = getattr(self, "_defanged_query", None) or self.ctx.user_query` (read in `_build_messages`, used by PLANNING); :2701 `self._defanged_query = None` (reset, top of `_handle_responding`); :2724 `self._defanged_query = defang_user_input(self.ctx.user_query)` (set). Reset lives on the shared machine instance and runs after turn N+1's PLANNING. Blame: set introduced by 0a2c
VERIFY: confirmed — state_machine.py:1519 `query = getattr(self, "_defanged_query", None) or self.ctx.user_query` (in `_build_messages`, used by PLANNING via :1702); reset `self._defanged_query = None` is at :2701 (top of `_handle_responding`, blame 3d4b5a1b 2026-08-31); set at :2724 (blame 0a2c3dfd 2026-08-30); both on main. The reset runs after turn N+1's PLANNING, so turn N+1 plans against turn N's question. The s

### F2 R04-F1 — REV-04 F1: idle reaper kills live user terminal tiles after 60 s of quiet
status=not_started cat=bug prio=P0 conf=high act=True [V:confirmed]
REMAINING: (1) pass `kind="user"` in `spawn_session` (or add `kind` to SpawnRequest with a whitelist); (2) call `manager.attach_client(session_id)` after `websocket.accept()` and `detach_client` in the `finally` of terminal_websocket; (3) optionally treat any session with an attached WS as user-TTL. Add a reaper test: user-kind + attached => not reaped past 60 s.
EVID: dashboard/routes/terminal.py:320-323 `manager.spawn(wrapped, cwd=..., cols=..., rows=...)` — no `kind=`; SpawnRequest (terminal.py:85-91) has no `kind` field. streaming/session_manager.py:23 `_DEFAULT_KIND_TTLS = {"user": 1800, "agent-pool": 900, "oneshot": 60}`; :257 `kind = self._kinds.get(sid, "oneshot")`; :262 exemption `if kind == "user" and self._attach_counts.get(sid, 0) > 0`. `grep -rn att
DOC: Review cites app.py:644 for the reaper start; it is app.py:642 on main (line drift only).
VERIFY: confirmed — terminal.py:306-323 `spawn_session` calls `manager.spawn(wrapped, cwd=..., cols=..., rows=...)` with no `kind=`; SpawnRequest (:85-91) has only command/cwd/cols/rows/writable_paths. session_manager.py:78 `kind: str = "oneshot"`, :23 `_DEFAULT_KIND_TTLS = {"user": 1800, "agent-pool": 900, "oneshot": 60}`, :257 `kind = self._kinds.get(sid, "oneshot")`, :262 exemption requires `kind == "user"` AND at

### F2 R04-F8 — REV-04 F8 / REV-06 O4: terminal e2e test and two agent-core tests use `fake_execute` doubles without the `speaker_role` kwarg (bridge coverage dark)
status=not_started cat=test_gap prio=P1 conf=high act=True [V:confirmed]
REMAINING: Add `speaker_role="admin"` (or `**kwargs`) to the three fake_execute doubles; fix R06-F2 first or the e2e test still fails in RESPONDING. Then confirm `terminal_spawn` appears in the e2e event list (test_terminal_e2e.py:168).
EVID: halbert_core/tests/test_terminal_e2e.py:142 `async def fake_execute(tool_name, args, session_id=None, confirmed=False)` vs tools/executor.py:314-321 `execute(..., speaker_role: str = "admin")` (added by 58adce12, on main). Run from main: `pytest halbert_core/tests/test_terminal_e2e.py` => `1 failed` (`test_e2e_agent_block_persisted_and_replayed`, captured log: `fake_execute() got an unexpected key
DOC: REV-06 says '1 x O4'; there are 2 such tests among the 30 plus the e2e test (3 doubles total).
VERIFY: confirmed — Exactly three doubles lack the kwarg: test_terminal_e2e.py:142, test_state_machine_turn_lock.py:308, test_state_machine_turn_persistence.py:119 (`async def fake_execute(tool_name, args, session_id=None, confirmed=False)`); tools/executor.py:314-320 `execute(..., speaker_role: str = "admin")`; state_machine.py:2364 passes `speaker_role=self.ctx.speaker_role`; 58adce12 (2026-08-31) is on main. Captu

### F2 R06-BASE — 31 of the 71 baseline suite failures are REV-06 F1/F2 + the speaker_role doubles
status=not_started cat=test_gap prio=P0 conf=high act=True [V:confirmed]
REMAINING: Fix R06-F2 (hoist), R06-F1 (move reset), R04-F8 (3 test doubles), and R06-X1 (3 CRAG-override expectations) — expected to drop the baseline from 71 to ~40.
EVID: scratchpad/pytest-main.txt (full-suite run from main, 2026-09-01 14:17): `71 failed, 4509 passed, 41 skipped`; `grep ^FAILED` by file: test_cognition_tick_once.py 10, test_state_machine_turn_lock.py 7, test_state_machine_meta_tools.py 5, test_state_machine_turn_persistence.py 4, test_state_machine.py 2, test_thread_e2e.py 2, test_terminal_e2e.py 1 => 31. Remaining 40 are elsewhere (test_cv_extensi
DOC: HANDOFF-WRAP-UP-2026-08-31.md:119 says 'several' of the 67 baseline failures are REV-06 seam regressions; the number is 31 of 71.
VERIFY: confirmed — Re-read scratchpad/pytest-main.txt (full suite from main, 2026-09-01 14:17): `71 failed, 4509 passed, 41 skipped`. `grep ^FAILED | by file`: test_cv_extensions 11, test_cognition_tick_once 10, test_agent_memory 10, test_state_machine_turn_lock 7, test_state_machine_meta_tools 5, test_state_machine_turn_persistence 4, test_peer_tool_proxy 4, test_llm_routes 4, test_vision_tools 2, test_thread_e2e 2

### F2 R06-X1 — NEW: 3 meta-tools CRAG-override tests fail on expectation drift, not on F1/F2
status=not_started cat=test_gap prio=P2 conf=medium act=True [V:adjusted]
REMAINING: Confirm by reading test_state_machine_meta_tools.py:340-360 and :540-555 against the overrides dict the state machine now passes to CRAG; update expectations (or restore the dict shape if `secure` was not meant to be exposed). Not called out separately in the REV-06 report.
EVID: Captured-log attribution of the 30 failures: test_state_machine_meta_tools.py::test_a_turn_with_no_pin_still_names_both_overrides_to_crag, ::test_the_turns_pin_rides_along_to_crag[planning], ::test_the_turns_pin_rides_along_to_crag[observing] contain no UnboundLocalError; their assertions are `assert {'model_overr...ecure': False} == {'model_overr... 'specialist'}` (meta_tools.py:550) and `[{'mode
DOC: REV-06 attributes all 30 to F1 (2) / F2 (~27) / O4 (1); 3 are this separate drift.
VERIFY: adjusted — Confirmed and can be upgraded from medium to high confidence. The three failing meta-tools tests carry no ULE/TypeError in their logs; the assertion diffs in the report are literal: `{'model_override': None, 'tier_override': None, 'secure': False} != {'model_override': None, 'tier_override': None}` (test :356) and `Extra items in the left set: {'secure': False}` (test :550-552). Source: state_mach
  CORRECTED_REMAINING: Update the two expected dicts in test_state_machine_meta_tools.py (:356 and :550-552) to include `"secure": False` — the `secure` kwarg is intentional per 4db888a9 and must keep reaching CRAG. Verified on a scratch copy: exactly these two edits clear the 3 tests.

### F2 R04-F2 — REV-04 F2: watched-shell -> thread pipeline (B8/B9/B22) is dead code; /stage always 409, /watched no-op, terminal hint never renders
status=not_started cat=incomplete_feature prio=P1 conf=high act=True [V:adjusted]
REMAINING: Decide: (a) wire it — one OSCParser + WatchedShellProcessor per user-kind session fed from the PTY fan-out, call `update_parser_state` from that reader and `insert_terminal_session` from `spawn`; wire the frontend toggle/stage calls; or (b) relabel B8/B9/B22 as unshipped in plan docs. Also fix R04-F1 first since watched shells presuppose `kind="user"`.
EVID: Production-tree grep (tests excluded): zero callers of `process_block_close` (watched_shell.py:51), `update_parser_state` (session_manager.py:184), `insert_terminal_session` (conversation_sqlite.py:2076; only peer_conversation_store.py:453 RPC proxy and the def). Consumers exist but read empty state: terminal.py:402 `if not manager.is_at_prompt(session_id): raise HTTPException(409, "shell busy")`;
DOC: REV-04 says 'the frontend ContextStage component is talking to a dead endpoint' — ContextStage.tsx makes no /stage call; the endpoint has no frontend caller at all (dead on both sides).
VERIFY: adjusted — All production-caller greps re-run and confirmed: `process_block_close` only defined (watched_shell.py:51); `update_parser_state` only defined (session_manager.py:184); `insert_terminal_session` only conversation_sqlite.py:2076 def + peer_conversation_store.py:452-453 RPC proxy. Consumers read empty state: terminal.py:402-403 `if not manager.is_at_prompt(session_id): raise HTTPException(409, "shel
  CORRECTED_REMAINING: As the finder wrote, plus: the frontend side is not merely missing a prop — `YourShellRegion` (B16) is never mounted in Layout/HostShell/ContextStage, so wiring means mounting it (or an equivalent toggle in TerminalTile/TerminalAccordionDock) and calling POST /sessions/{id}/watched and /stage; backe

### F2 R04-F3 — REV-04 F3: `TerminalPool.run_block` leaks a permanently-busy PTY slot on any error before the drain loop
status=not_started cat=bug prio=P1 conf=high act=True [V:confirmed]
REMAINING: Move attach/replay/write inside the try; clear the busy flag in `finally` (`set_block_open(sid, False)`, evict on the kill path). Latent until the pool is enabled (see R04-POOL).
EVID: streaming/agent_pool.py: `q = await session.attach()` :131, `replay = await asyncio.wait_for(q.get(), timeout=5.0)` :133, `await session.write_stdin(block_cmd)` :142 all precede the `try:` at :161 whose `finally` (:181) only does `session.detach(q)`; `self._manager.set_block_open(sid, False)` is at :206 outside any guard. session_manager.py:264 exempts `agent-pool` + block_open from the reaper, so
VERIFY: confirmed — agent_pool.py re-read at main: `q = await session.attach()` :131, `replay = await asyncio.wait_for(q.get(), timeout=5.0)` :133, `await session.write_stdin(block_cmd)` :142 all precede `try:` at :161; the `finally:` at :181 only does `session.detach(q)`; `self._manager.set_block_open(sid, False)` is at :206 after the try and after redaction, unguarded. The busy flag is set at :55 in `_acquire`. ses

### F2 R04-F4 — REV-04 F4: pool `block_output` bytearray is unbounded (review reproduced ~800 MB RSS)
status=not_started cat=bug prio=P1 conf=high act=True [V:confirmed]
REMAINING: Cap while accumulating (keep first/last N KiB with an elision marker). Ship together with R04-F3 before enabling the pool.
EVID: agent_pool.py:137 `block_output = bytearray()`; :154 `block_output.extend(out.block_bytes)` with no cap; head/tail applied only after completion at :194-199. Contrast pty.py:367-372 `_append_buffer` bounded at `_buffer_bytes`.
VERIFY: confirmed — agent_pool.py:137 `block_output = bytearray()`; :154 `block_output.extend(out.block_bytes)` inside `_drain_until_closed` with no size check; head/tail (`lines[:20]`, `output_text[-4096:]`) applied only after the drain at :194-199. Contrast pty.py:367-372 `_append_buffer` trims to `_buffer_bytes`. Unchanged on main and all unmerged branches. I did not re-run the 300 MiB reproduction (the structural

### F2 R04-POOL — Agent PTY pool is unreachable in the running app (only tests enable it)
status=blocked cat=decision prio=P2 conf=high act=True [V:confirmed]
REMAINING: Founder decision: enable the pool in app startup (after R04-F3/F4 fixes) or leave the subprocess path as the shipped executor and mark B7 unshipped.
EVID: streaming/terminal_bridge.py:142-152 `set_terminal_pool_enabled` / `terminal_pool_wanted() = _pool_enabled and terminal_stream_wanted()`; production grep: `set_terminal_pool_enabled` has no caller outside tests; dashboard/app.py greps show only `start_reaper()` (:642), no pool enable. tools/executor.py:528-531 gates on `terminal_pool_wanted()`.
VERIFY: confirmed — terminal_bridge.py:140 `_pool_enabled: bool = False`; :143-146 `set_terminal_pool_enabled`; :149-155 `terminal_pool_wanted() = _pool_enabled and terminal_stream_wanted()`. Repo-wide grep: `set_terminal_pool_enabled` is called only from tests/test_terminal_e2e.py:121/124; dashboard/app.py has only `get_terminal_manager().start_reaper()` (:642) and `shutdown()` (:844) — no pool enable. tools/executo

### F2 R04-F7 — REV-04 F7: `/api/terminal/exec` accepts an unbounded client timeout and accumulates unbounded output
status=not_started cat=security prio=P2 conf=high act=True [V:confirmed]
REMAINING: Clamp timeout (e.g. 1..300) via a pydantic validator; cap output head/tail like the pool does.
EVID: dashboard/routes/terminal.py:62 `timeout: int = 30` (no ceiling, no validator); :269 `output = bytearray()` with `output.extend(chunk)` in `drain()` and `asyncio.wait_for(drain(), timeout=request.timeout)` at :276.
VERIFY: confirmed — terminal.py:59-63 `class CommandRequest(BaseModel): ... timeout: int = 30` — `grep -n 'validator\|Field(' terminal.py` returns nothing, so no ceiling. :269 `output = bytearray()`, :273 `output.extend(chunk)` in `drain()`, :276 `await asyncio.wait_for(drain(), timeout=request.timeout)`. Both unbounded as claimed. Unchanged since the review.

### F2 R04-F5 — REV-04 F5: `PTYSession.kill()` blocks the event loop with synchronous sleeps (~50-70 ms per kill)
status=not_started cat=bug prio=P2 conf=high act=True [V:confirmed]
REMAINING: Make kill async or defer the SIGKILL escalation via `loop.call_later`; drop the sleeps and rely on the next `is_alive()` poll.
EVID: streaming/pty.py:340 `time.sleep(0.05)` and :347 `time.sleep(0.02)` inside sync `kill()`, called from the async reaper (`_reap_once`, session_manager.py:249/268), route handlers, and the pool timeout path.
VERIFY: confirmed — pty.py `kill()` at :316; `time.sleep(0.05)` at :340 and `time.sleep(0.02)` at :347 inside the sync method. Callers: session_manager.py:249/268 (`_reap_once`, run from the async `_reaper_loop` task), terminal.py route handlers (`manager.kill`), agent_pool.py:176 timeout path. Confirmed; I did not re-measure the 54 ms stall.

### F2 R04-F6 — REV-04 F6: PTY fan-out queues are unbounded; the drop-on-overflow branch is unreachable
status=not_started cat=bug prio=P2 conf=high act=True [V:confirmed]
REMAINING: Attach with a real bound (e.g. 1024 chunks), drop-oldest in `_push_to_all`; scrollback replay already covers re-attachers.
EVID: pty.py:119 `async def attach(self, *, _maxsize: int = 0)` -> `asyncio.Queue(maxsize=0)` (infinite); no caller passes a size (`read_chunk` pty.py:~289 `await self.attach()`, agent_pool.py:131 `session.attach()`); :190 `except asyncio.QueueFull` is dead. terminal_bridge.py bounds its bus at 512 (the intended pattern).
VERIFY: confirmed — pty.py:119 `async def attach(self, *, _maxsize: int = 0)` -> :133 `asyncio.Queue(maxsize=_maxsize)`; production callers `grep -rn '\.attach('` => pty.py:288 (`read_chunk`, used by the WS/SSE routes and /exec) and agent_pool.py:131, both without a size; :190 `except asyncio.QueueFull` is therefore unreachable. terminal_bridge.py bounds its bus at 512 as the finder notes.

### F2 R04-F9 — REV-04 F9: somatic block pipeline (C1a-C1d) is built but unwired in the shipped app
status=not_started cat=incomplete_feature prio=P2 conf=high act=True [V:confirmed]
REMAINING: Wire detector -> lifecycle -> store into the agent construction, or mark C1a-C1d 'built, unwired' in plan docs.
EVID: dashboard/routes/agent.py:256 constructs `AgentStateMachine(` without `somatic_lifecycle`/`somatic_store` (grep of routes/agent.py for 'somatic' => none); state_machine.py:242-243 accept them, :2679-2685 C1d seam requires `self.ctx.current_somatic_block_id`, which nothing sets (states.py:139 default None; no production writer); `session_somatic_blocks` (conversation_sqlite.py:352) has writer metho
VERIFY: confirmed — routes/agent.py:256 `AgentStateMachine(` — `grep -n somatic routes/agent.py` returns nothing; constructor params `somatic_lifecycle = None` / `somatic_store = None` at state_machine.py:242-243; C1d seam :2679-2686 requires `self.ctx.current_somatic_block_id`; states.py:139 default None; repo grep for `current_somatic_block_id =` outside tests => none; `SomaticLifecycle`/`SomaticStore`/`get_somatic

### F2 R06-F3 — REV-06 F3: SEARCHING state ignores per-turn `retrieval_scope` and skill scope
status=not_started cat=bug prio=P1 conf=high act=True [V:confirmed]
REMAINING: Pass `scope=self.ctx.retrieval_scope` (and the active skill's role/scope) to `rag.search` in `_handle_searching`, or route SEARCHING through the assembler's `_search_retrieval`. Add a test asserting the GPU deep-scan turn (`retrieval_scope="host"`) never queries unscoped.
EVID: state_machine.py:2199 `tasks.append(("rag", self.rag.search(search_query, limit=5)))` — no scope/role; `retrieval_scope` is consumed only at :1642 (PLANNING assemble). Routing :1841 `elif self.ctx.loop_count == 0: yield await self._transition(AgentState.SEARCHING)` — every non-greeting, no-tool-call first loop goes through SEARCHING. context/adapters.py:374 `SourcePrepAdapter.search(query, limit=5
VERIFY: confirmed — state_machine.py:2199 `tasks.append(("rag", self.rag.search(search_query, limit=5)))` — no scope/role kwargs; `retrieval_scope` appears at :389 (param), :421 (doc), :488 (ctx), :1642 (the single consumer, inside the PLANNING `assemble(...)` call at :1636-1643). Routing :1841 `elif self.ctx.loop_count == 0: yield await self._transition(AgentState.SEARCHING)` after the greeting guard at :1834. conte

### F2 R06-F4 — REV-06 F4: chmod change that fails after `os.chmod` is excluded from the rollback set
status=not_started cat=bug prio=P1 conf=high act=True [V:confirmed]
REMAINING: In the handler, for a failed chmod change re-stat and append `{"kind":"chmod","path":..,"old_mode":..}` when the mode differs from the recorded expectation; or wrap the post-chmod audit write so it cannot fail the change after the side effect.
EVID: findings/proposal_generator.py:265-277 exception handler appends to `applied` only when `change.get("action") != "chmod"` (:270); `_apply_chmod` does `os.chmod(path, mode_int)` at :561 then `write_audit(...)` at :563 — an audit write failure leaves the mode changed and un-rolled-back while the proposal reports ROLLED_BACK.
VERIFY: confirmed — findings/proposal_generator.py:265-277: `except Exception:` handler appends a rollback record only when `change.get("action") != "chmod"` (:270); `_apply_chmod` does `os.chmod(path, mode_int)` at :561 then `write_audit(...)` at :563 with no try around the audit write. A post-chmod audit failure therefore leaves the mode changed and excluded from `applied`. Confirmed.

### F2 R06-F5 — REV-06 F5: `merge_thread` orphans `open_loops` and `terminal_blocks` rows of the merged thread
status=not_started cat=bug prio=P2 conf=high act=True [V:confirmed]
REMAINING: Inside the merge transaction add `UPDATE open_loops SET thread_id=? WHERE thread_id=?` and the same for `terminal_blocks`; add a store test.
EVID: conversation_sqlite.py:1820-1879 updates `messages`, `messages_fts`, `receipts_fts`, `conversations` only; `open_loops` (schema :437, `thread_id TEXT NOT NULL`) and `terminal_blocks` (schema :392, `thread_id TEXT`) untouched.
VERIFY: confirmed — conversation_sqlite.py:1820 `def merge_thread`; the transaction's statements (awk over :1815-1885) are `UPDATE messages SET conversation_id`, `UPDATE messages_fts SET conversation_id`, `DELETE FROM receipts_fts WHERE thread_id`, two `UPDATE conversations` — nothing touches `open_loops` (schema :437, `thread_id TEXT NOT NULL`, index :449) or `terminal_blocks` (schema :392, `thread_id TEXT`, index :

### F2 R06-O2 — REV-06 O2: `recall_memory` / `search_discoveries` tool calls are substituted with generic search and marked success
status=not_started cat=bug prio=P2 conf=high act=True [V:confirmed]
REMAINING: Either implement the two tools or report them as unsupported so the model is not told an action worked.
EVID: state_machine.py:1822 `if tool_name in ["search", "search_discoveries", "recall_memory", "web_search"]: yield await self._transition(AgentState.SEARCHING)`; `_handle_searching` (:2185-2205) runs `self.rag.search` / `self.memory.recall` regardless of tool name; with production `memory_service=None` the recall 'succeeds' recalling nothing.
VERIFY: confirmed — state_machine.py:1822 routes `search_discoveries`/`recall_memory`/`web_search`/`search` to SEARCHING; `_handle_searching` :2190-2202 only special-cases `search`/`web_search` for the query and always runs `self.rag.search` + `self.memory.recall` (when present); :2231-2233 `tool_call.status = "success"; tool_call.result = {"count": ...}` regardless of tool name. Production `memory_service = None` at

### F2 R06-F6 — REV-06 F6: Wyoming voice turn abandons `agent.process()` without `aclosing`, holding the turn lock until GC
status=not_started cat=bug prio=P3 conf=high act=True [V:confirmed]
REMAINING: Wrap in `aclosing(agent.process(...))` as the dashboard routes do.
EVID: integrations/wyoming_agent.py:168-187 `_collect_turn` does `async for event in agent.process(...)` and `break`s on response_complete with no `aclosing`; dashboard/routes/agent.py:1497/1566 use `async with aclosing(agent.process(...))` for exactly this reason.
VERIFY: confirmed — integrations/wyoming_agent.py:168-187 `_collect_turn` iterates `agent.process(...)` with a bare `async for` and `break`s on `response_complete`; `grep -n aclosing wyoming_agent.py` => nothing. routes/agent.py:14 imports `aclosing` and uses it at :1497 (`agent.process`) and :1566 (`agent.confirm_action`) with the comment explaining the turn-lock reason (:1491). wyoming_agent.py was touched by 149b3

### F2 R06-F7 — REV-06 F7: compression cascade unreachable on the agent path at TINY..LARGE; LLMLingua FORCE_TOKENS lacks `-`
status=not_started cat=decision prio=P3 conf=high act=True [V:confirmed]
REMAINING: Decide whether the cascade should be live on the agent path; if so trigger on a fraction of the intake budget and add `-`/`--` to FORCE_TOKENS; if not, say so in the packet-facing docs.
EVID: context/assembler.py:127 `_compressor_threshold = 4000`; :314 `combined_tokens > self._compressor_threshold`; :181 `max_tokens = intake.context_budget.total`; intake/budget.py totals TINY 400 / SMALL 800 / MEDIUM 2000 / LARGE 4000 / XLARGE 8000 / MASSIVE 16000. compression/lingua_compressor.py:47-67 FORCE_TOKENS contains `/ = | > < $ \` #` but no `-`.
VERIFY: confirmed — context/assembler.py:127 `_compressor_threshold = 4000`; `assemble(..., max_tokens: int = 8000, use_compression: bool = True, intake=None)` (:136-139); :181 `max_tokens = intake.context_budget.total`; the agent path passes intake (state_machine.py:1636-1643). Stronger than the finder's arithmetic: :307-310 clamps `combined_tokens = max_tokens` after truncation BEFORE the :314 check `combined_token

### F2 R06-F8 — REV-06 F8: bare `except TypeError` in assembler silently retries retrieval unscoped
status=not_started cat=bug prio=P3 conf=high act=True [V:confirmed]
REMAINING: Check the adapter signature once with `inspect` or re-raise TypeErrors raised inside a scope-aware adapter.
EVID: context/assembler.py:600-604 `try: return await self.retrieval.search(query, limit=5, scope=scope, role=role) except TypeError: logger.debug(...)` then unscoped `search(query, limit=5)`.
VERIFY: confirmed — context/assembler.py:599-604: `if role or scope: try: return await self.retrieval.search(query, limit=5, scope=scope, role=role) except TypeError: logger.debug("retrieval source takes no scope; querying unscoped")` then :604 unscoped `search(query, limit=5)`. Confirmed.

### F2 R04-F10 — REV-04 F10: `tick()` docstring promises a live-terminal guard that `_close_due` does not implement
status=not_started cat=doc_only prio=P3 conf=high act=True [V:confirmed]
REMAINING: Delete the claim, or implement when R04-F2 lands (sessions carry no thread id today).
EVID: agents/threads.py:556-557 docstring 'Plan B adds the live-terminal guard: never close while a terminal session of this thread is open'; `_close_due` :795-804 checks only GRACE_MINUTES and successor turns.
VERIFY: confirmed — agents/threads.py:556-557 docstring: 'Plan B adds the live-terminal guard: never close while a terminal session of this thread is open (spec §5 "Stale")'; `_close_due` :795-804 checks only `GRACE_MINUTES` and the successor's `turns_since_pause`. No terminal/session lookup anywhere in `tick`/`_close_due`. Confirmed doc_only.

### F2 R04-F11 — REV-04 F11: `streaming/emitter.py` EventEmitter is dead code with a shared-queue consumer-splitting bug
status=not_started cat=cleanup prio=P3 conf=high act=True [V:confirmed]
REMAINING: Delete the module (and the __init__ export), or fix per-consumer queues before anyone wires it.
EVID: Production grep for `get_event_emitter|init_event_emitter|EventEmitter` => only streaming/__init__.py:10,14 re-export and a docstring mention in agents/events.py:723; no constructor/caller. Module is 281 lines.
VERIFY: confirmed — `grep -rn 'get_event_emitter\|init_event_emitter\|EventEmitter'` over production => streaming/__init__.py:10,14 (re-export) and a docstring at agents/events.py:723 only; `wc -l streaming/emitter.py` = 281. `subscribe()` :144-162 returns `self.subscribers[session_id]` — one shared queue per session id, and evicts the oldest subscriber at max. Confirmed cleanup.

### F2 R04-F12 — REV-04 F12 (plausible): SIGKILLed child not reaped within 20 ms leaks as a zombie forever
status=not_started cat=bug prio=P3 conf=medium act=True [V:confirmed]
REMAINING: Only set `_exited` after a successful reap, or do a final blocking/threaded reap.
EVID: pty.py:347-348 `time.sleep(0.02); self._reap(blocking=False)` then :355 unconditional `self._exited = True`; `is_alive()` short-circuits on the flag so the pid is never reaped.
VERIFY: confirmed — pty.py `_reap(blocking=False)` :374-393 returns without touching `_exited` when `waitpid(WNOHANG)` gives pid==0; `kill()` then unconditionally sets `self._exited = True` at :355; `is_alive()` :105-106 returns False immediately when `_exited`. So a child not reaped within the 20 ms window is never waited on again. Mechanism confirmed; remains 'plausible' severity as the review said (needs an unusua

### F2 R04-F13 — REV-04 F13 (plausible): PTY fd pair leaks if `os.fork()` raises
status=not_started cat=bug prio=P3 conf=medium act=True [V:confirmed]
REMAINING: Close both fds in an except around fork.
EVID: pty.py:224 `self._master_fd, self._slave_fd = os.openpty()` ... :239 `pid = os.fork()` with no try/except closing both fds on failure; `manager.spawn` never registers the session on that path.
VERIFY: confirmed — pty.py:224 `self._master_fd, self._slave_fd = os.openpty()`; :239 `pid = os.fork()` with no try/except in the parent path (:268 `except Exception` belongs to the child branch; parent branch :270-275 only closes the slave on success). session_manager.spawn (:100) registers the session only after `await session.spawn()` returns, so a fork failure leaves both fds open and unregistered. Confirmed.

### F2 R06-O1 — REV-06 O1: `react_agent.py` attaches the last observation to every same-named tool call (dormant)
status=not_started cat=cleanup prio=P3 conf=high act=False
REMAINING: Match observations by call id, or delete the module since nothing constructs it.
EVID: agents/react_agent.py:300-313 reversed search by `step.tool_name == tool_name` for each tool_call; production grep for `ReactAgent(` => no constructor outside tests.

### F2 R06-O3 — REV-06 O3 / REV-04 subagent seam: `spawn_subagent` / `await_subagent_completion` / WAITING_FOR_EVENTS have no callers
status=not_started cat=incomplete_feature prio=P3 conf=high act=False
REMAINING: Deferred by direction (current features first); mark unshipped in plan docs.
EVID: Production grep for `spawn_subagent|await_subagent_completion|subagent_manager=` => only the definitions; `AgentStateMachine(` at routes/agent.py:256 passes no subagent_manager. Consistent with the 2026-08-26 'orchestrator = stubs' audit.

### F3 SE-05 — P4b ComputeRouter corrected fallback chain is implemented but never wired into any production path
status=in_progress cat=incomplete_feature prio=P1 conf=high act=True
REMAINING: Decide: either wire ComputeRouter.route() into the agent/cognition turn path (and then fix SE-08 health route + SE-12 deferred queue first), or explicitly mark P4b as a decision layer for Phase 9.3 in the plan. Until then the 'corrected chain' has no runtime effect.
EVID: compute_router.py:311-417 route() implements cloud > local > peer > WoL > template > no-AI and is tested (test_compute_fallback, test_compute_router_route); but `grep -rn 'ComputeRouter\|compute_router' halbert_core/halbert_core` outside federation/ hits only docstrings (routes/peers.py:324, providers/peer.py:58) - no instantiation; route() docstring itself says 'the decision layer is complete; th
DOC: IMPL-PLAN-SINGULAR-ENTITY-TASKS lists P4b/O3 as done with acceptance 'cloud is tried first ... if cloud fails local model is tried'; that acceptance is only met inside unit tests.

### F3 SE-06 — P4a connectivity probe + P4c degraded marker exist but have no production consumers
status=in_progress cat=incomplete_feature prio=P2 conf=high act=True
REMAINING: Both ride on SE-05: the '[no thinking power' marker is never applied to a real response and connectivity is never checked. Acceptance 'user is never confused about degraded mode' is unmet at runtime.
EVID: federation/connectivity.py (141 lines) + test_connectivity pass; compute_router.py:121-127 DEGRADED_MARKER_PREFIX/apply_degraded_marker + test_degraded_marker pass; grep for apply_degraded_marker/is_degraded_response/ConnectivityProbe outside federation/ and tests returns nothing

### F3 SE-08 — Peer health probe targets a route that does not exist (REV-10 F3)
status=not_started cat=bug prio=P1 conf=high act=True
REMAINING: Add GET /api/compute/v1/health to compute_endpoint.py (auth'd, no GPU cost) and encode the path as one shared constant used by compute_router, config_wizard and PeerProvider.
EVID: compute_router.py:625 and model/config_wizard.py:437 GET /api/compute/v1/health; providers/peer.py:367-384 probes /api/compute/v1/models; `grep -rn 'compute/v1' halbert_core/halbert_core` shows no server route for either outside the unmounted compute_endpoint.py (which has only chat/completions and models). Router docstring :588 admits 'peer-side health route is not scaffolded'. Wizard's peer test

### F3 SE-09 — Workstation compute endpoint never mounted; broker is NotImplementedError - peer offload is a dead end (Phase 9.3, REV-10 F2)
status=not_started cat=incomplete_feature prio=P0 conf=high act=True
REMAINING: Mount compute_endpoint.router in app.py; implement _submit_to_broker as a direct local-model call for the 1:1 case (route to Ollama/vLLM, never apple-foundation); populate /api/compute/v1/models; unskip test_peer_redaction.py:91; add a TestClient test that mounts the real app and completes a chat round-trip. Until then ComputePeerCard should refuse to save a link or label the feature as not serving.
EVID: app.py:274-308 include_router list has no compute_endpoint (routes/compute.py mounted at :298 is the capacity-probe module, different thing); `grep -rn compute_endpoint halbert_core/halbert_core` outside federation/ hits only docstrings; compute_endpoint.py:265 `raise NotImplementedError('_submit_to_broker — TODO(federation-9.3)')`; :220-246 models route returns data: []; compute_broker.py:166/202
DOC: HANDOFF-README-PEER-COMPUTE and MASTER-TODO §U6 present peer compute as the recommended home build; on main a home node that follows that flow has a total inference outage (every turn 404s).

### F3 SE-10 — P5a/P5b PeerToolProxy + executor fallback: implemented, tested, but never injected and cannot reach a real workstation MCP server
status=in_progress cat=incomplete_feature prio=P1 conf=high act=True
REMAINING: (a) Inject a PeerToolProxy built from peers_config into ToolExecutor in routes/agent.py when a paired peer has the needed capability; (b) unify auth so the MCP HTTP server accepts peers.json tokens (Phase 9.1 C1) or point the proxy at the MCP port with the MCP token; (c) an integration test against the real MCP HTTP handler. Security tests (24) stay valid.
EVID: agents/peer_tool_proxy.py posts JSON-RPC to f'{peer_url}/' (:93) with the peers.json bearer token; tools/executor.py:342-366 routes unknown tools to self.peer_tool_proxy; but `grep -rn 'peer_tool_proxy='` finds no caller outside executor.py, and routes/agent.py:127 constructs `ToolExecutor(safety=safety, role_gate=RoleGate(safety))` with no proxy. The MCP HTTP transport is a separate http.server i
DOC: Tasks plan marks P5b 'state-machine routing ... TestExecutorPeerFallback suite green' as done; routing exists only when a proxy is passed, and nothing passes one.

### F3 SE-11 — 4 TestExecutorPeerFallback tests are order-dependent and fail in the full suite
status=not_started cat=test_gap prio=P2 conf=high act=True
REMAINING: Replace with `asyncio.run(...)` or mark the four tests `@pytest.mark.asyncio`. One-line fix each; then the scoped suite is 512/0.
EVID: tests/test_peer_tool_proxy.py:268,282,297,311 use `asyncio.get_event_loop().run_until_complete(...)`; halbert_core/pyproject.toml:139 asyncio_mode = 'auto'. Solo: `pytest test_peer_tool_proxy.py` -> 24 passed. After any async test file (e.g. federation/test_compute_fallback.py first) -> 4 failed 'RuntimeError: There is no current event loop'. They are 4 of the 71 failures in scratchpad/pytest-main
DOC: Tasks plan: 'TestExecutorPeerFallback suite green' - only true in isolation; the merge commit's '71 failures byte-identical to baseline' includes these 4 new-in-branch failures.

### F3 SE-12 — Deferred queue unbounded and replay_deferred unimplemented (Phase 9.6, REV-10 F4)
status=not_started cat=bug prio=P2 conf=high act=True
REMAINING: Bound the queue (ring + dropped counter), persist deferrals, implement replay with the §11.3 conflict policy, unskip test_split_brain - BEFORE wiring the router (SE-05).
EVID: compute_router.py:304 `self._deferred_queue: list = []  # TODO(federation-9.6)`; :673-683 replay_deferred raises NotImplementedError; tests/federation/test_split_brain.py 6 tests skipped 'requires replay_deferred()'. Latent because of SE-05 (router not instantiated in production).

### F3 SE-15 — P7c pairing flow cannot succeed through the UI on main
status=blocked cat=incomplete_feature prio=P0 conf=high act=True
REMAINING: Build the real cross-device handshake: workstation UI enters the canonical host URL, calls the HOST's /api/peers/pair, host UI shows the PIN/approval, workstation submits the PIN to the host's /verify, and the returned token is persisted to the workstation's being.yml via PUT /api/devices/peer-token (already exists). Remove the localStorage-only path. Add a component test for the manual flow. Today the only working path is curl + pasting the token into the Advanced field.
EVID: PeerPairingModal reused as-is. Discovered tab: routes/peers.py:414-430 `/api/peers/discovered` returns hardcoded [] (mDNS 9.7 stubs, peer_discovery.py:191/198/250/257 NotImplementedError) so the list is always empty. Manual tab: PeerPairingModal.tsx:161-170 `throw new Error('Manual pairing flow — TODO(federation-9.1)')`. Even when a peer is listed, DiscoveredPeerCard.tsx:57-65 auto-calls verifyPai
DOC: IMPL-PLAN Phase 7 acceptance 'User can pair a workstation to an HA server through the UI. No YAML editing required' is claimed done (P7b-d/G12 row) but is not met; G12 §10 explicitly scoped the manual-pairing TODO out.

### F3 SE-16 — Pairing is self-service token issuance with no desktop confirmation, expiry or rate limit (REV-10 F1)
status=not_started cat=security prio=P0 conf=high act=True
REMAINING: Make the PIN out-of-band (display on the approving device only), add an explicit approval state gate on /verify, 60s expiry, attempt limiting, and restrict /pair to local/admin callers. This is the 'desktop confirmation' the task asked about: it does not exist.
EVID: routes/peers.py:159-197 request_pairing returns the 4-digit PIN to the requester in the HTTP response; :195 `# TODO(federation-9.1): Emit a WebSocket event so the Desktop UI shows a pairing confirmation dialog`; :200-251 verify_pairing issues a raw bearer token on PIN match only; `_pending_pairings` (:76) has no expiry/attempt counter (grep for expire/ttl/attempt: none). Any host that can reach a 

### F3 SE-17 — Any authenticated peer can revoke any other peer (REV-10 F5)
status=not_started cat=security prio=P1 conf=high act=True
REMAINING: Restrict to node_id == ctx.node_id or local-admin.
EVID: routes/peers.py:284-300 DELETE /api/peers/{node_id} depends only on require_peer_auth; :294 TODO acknowledges it should be local-admin or self-only. devices.py DELETE /devices/{node_id} is the unauthenticated dashboard alias.

### F3 SE-18 — Phase 9.1 'one token, one validation path' (MCP + peers) not implemented (REV-10 F6)
status=not_started cat=incomplete_feature prio=P1 conf=high act=True
REMAINING: Route MCP HTTP auth through PeersConfig.verify_token (needed by SE-10) or document two separate credential surfaces; throttle last_seen writes.
EVID: mcp/server.py:1136-1162 `_bearer_token` static, hmac compare; `grep -rn 'peers_config\|verify_token\|require_peer_auth' halbert_core/halbert_core/mcp/` returns nothing; federation/peer_middleware.py:103 TODO(federation-9.1) app-lifespan wiring; peers_config.py:514-522 saves on every last_seen update (F9).

### F3 SE-19 — Phase 9.2 Instance Switcher extended with remote peers
status=not_started cat=incomplete_feature prio=P3 conf=high act=False
REMAINING: Low value until mDNS (SE-20) returns anything. Defer or drop the README claim.
EVID: components/shell/InstanceSwitch.tsx (244 lines): grep -i 'discover|peer' -> 0 hits; useDiscoveredPeers.ts exists and is consumed only by PeerPairingModal; federation/README.md claims the hook 'feeds InstanceSwitch'

### F3 SE-20 — Phase 9.7 mDNS discovery is a scaffold
status=not_started cat=deferred prio=P2 conf=high act=True
REMAINING: Implement beacon/listener or make start() log-and-return; wire /api/peers/discovered to the listener. Manual pairing (SE-15) is the prerequisite path for LAN-less/Tailscale setups anyway.
EVID: peer_discovery.py:191,198,250,257 raise NotImplementedError after the lazy zeroconf import succeeds (crashes if zeroconf IS installed, REV-10 F11); :285-294 compute_backends detection TODO; test_peer_discovery.py 2 skipped

### F3 SE-21 — Phase 9.5 telemetry, 9.8 broker, 9.9 fleet cockpit are scaffolds; fleet routes 500 (REV-10 F10)
status=not_started cat=deferred prio=P3 conf=high act=True
REMAINING: Founder decision: given the Rust rebuild/OS deferral, either unmount fleet.router (or return None from get_fleet_proxy so routes 404) and park 9.5/9.8/9.9, or schedule them. Not needed for the 1 HA + 1 workstation singular-entity case.
EVID: telemetry_agent.py:181-227, compute_broker.py:166/202/218, fleet_proxy.py:115-177 all NotImplementedError; routes/fleet.py:142-199 raise NotImplementedError before the 404 check; fleet router mounted app.py:307; test_compute_broker 4 skipped

### F3 SE-22 — Phase 9.4 egress redaction on the compute endpoint
status=blocked cat=deferred prio=P2 conf=high act=False
REMAINING: Unblocked by SE-09; then unskip the redaction test and decide on SSE streaming.
EVID: compute_endpoint.py:184-217 applies filter_tools_for_peer + mcp_response - correct but unmounted (SE-09); test_peer_redaction.py:91 skipped; streaming deliberately raises (client.py:509, compute_endpoint.py:62,105)

### F3 SE-25 — Dead private _is_home_variant helpers left after F5
status=not_started cat=cleanup prio=P3 conf=high act=True
REMAINING: Delete the four dead helpers. Optional decision: the home-only 403 on compute-peer linking is a variant gate the F5 principle argues against; keep only if the founder still wants sysadmin nodes to use the picker exclusively.
EVID: routes/agent.py:416, model/config_wizard.py:29, model/auto_provision.py:33, model/tier_router.py:37 define _is_home_variant with no callers (F5 review notes them as retained-harmless). Intentional label uses remain at peers.py:383 and routes/compute.py:315 (compute-peer link/probe are home-only by design) and adapters.py:438 (fallback).

### F3 SE-26 — body_name is never surfaced to the entity (handoff §3, open question 5)
status=not_started cat=incomplete_feature prio=P2 conf=high act=True
REMAINING: Feed body_name into the system prompt ('You are currently at your <body_name>') and the 'my desk body is asleep' capability phrasing; add a prompt test. Without it the singular entity has no idea which body it is in.
EVID: `grep -rn body_name` outside being_config/devices/cognition_wiring returns nothing; _get_body_name (cognition_wiring.py:81) is consumed only by routes/devices.py:190-197; no prompt-builder or PersonaCognition usage

### F3 SE-27 — Runtime disconnect behaviour undecided (handoff §18 Q1-Q3, §11 table)
status=not_started cat=decision prio=P2 conf=medium act=True
REMAINING: Founder decision per §18: fail-gracefully-and-log vs buffer-and-flush for memory writes; whether cognition pauses when the canonical host is down. Then implement the chosen behaviour and test 'HA server reboots' from the §11 table.
EVID: cognition_wiring.py:254-276 falls back to local only when peer_token is missing or the import fails; PeerMemoryUnavailable / PeerConversationUnavailable are not caught anywhere in halbert_core at runtime (grep); no buffering, no read-only cache

### F3 SE-28 — No two-process / two-machine end-to-end test of singular mode exists
status=not_started cat=test_gap prio=P1 conf=high act=True
REMAINING: One scripted validation: two Halbert processes on different ports (or two machines), pair, set singular mode, write a memory on A, retrieve on B, continue a thread across bodies, and (after SE-09) one chat turn served over the peer link. Record the result in the handoff.
EVID: All cross-node tests are in-process: test_shared_threads uses FakeConversationServer/SQLite WAL, test_memory_routes/test_conversation_routes use TestClient, test_peer_provider mocks requests; the P5 hardware/LAN run in the memory notes was never executed for this feature; REV-10 §verification also ran only unit suites

### F3 SE-29 — feat/singular-entity branch + worktree fully merged
status=obsolete cat=retire prio=P3 conf=high act=True
REMAINING: Delete worktree and branch.
EVID: Branch state: feat/singular-entity 59 behind / 0 ahead of main; merge 15560fdb; worktree ~/.config/superpowers/worktrees/Halbert/singular-entity clean

### F3 SE-30 — feat/singular-entity-opus (7 unmerged commits) is superseded by main and conflicts on merge
status=obsolete cat=retire prio=P2 conf=high act=True
REMAINING: Do not merge. Delete branch and the opus-singular-tasks worktree.
EVID: git log main..feat/singular-entity-opus: 8e56eab6 O1 .. b6bf6371 O6, 132f2019 docs; main got them via e04ad14e 'cherry-pick Opus P3d/P4b/P5c/P6b' + 27fcfb95 remediation; `git diff feat/singular-entity-opus main` on peer_conversation_store.py, test_peer_conversation_store.py, test_shared_threads.py, test_capability_routing.py is empty and on compute_router/peers_config/devices.py/test_device_routes

### F3 SE-31 — feat/compute-peer-setting merged; origin/feat/federated-fleet merged
status=obsolete cat=retire prio=P3 conf=high act=True
REMAINING: Delete local feat/compute-peer-setting and remote feat/federated-fleet.
EVID: Branch state 148/0 (no worktree) and remote ahead=0; content on main at 0514a5c3/5f87520c and 928c9166/9fff12a7

### F3 SE-32 — Both stashes are obsolete duplicates of code already on main
status=obsolete cat=retire prio=P3 conf=high act=True
REMAINING: git stash drop both (founder action; audit is read-only).
EVID: stash@{0} 'duplicate U6-S3 compute-peer work' adds 'peer' to CHAT_CAPABLE_PROVIDERS in model/client.py - main client.py:75-76 already has it. stash@{1} renames onPaired -> _onPaired in PeerPairingModal.tsx:147 - main already has that exact line.

### F3 SE-33 — worktree-u6-home-simplification (16 unmerged) compute/federation work was re-implemented on main via feat/ha-simplification
status=obsolete cat=retire prio=P2 conf=medium act=True
REMAINING: Coordinate with the HA-simplification auditor; if load_explicit_variant is not wanted, delete the branch + .claude/worktrees/u6-home-simplification. Do not merge.
EVID: u6 commits 115dbdb3 (W18 ComputeRouter.route + health probe), 6b66321f (W17), 91189ac1 (W22/23), 8fbf23ee (W24), plus its HANDOFF-U6-S3 'remaining' W14/W15/W16/W19 - all have main equivalents: 6f46f09a 'U6 S4 ... compute router fallback chain', 6a077653 'U6 S6 ... PeerAuthMiddleware fix', 0514a5c3 (W14/W16), 5f87520c (W15), a161bb9a (D1). `git merge-tree --write-tree main worktree-u6-home-simplifi

### F3 SE-34 — MASTER-TODO.md is stale for this area
status=not_started cat=doc_only prio=P2 conf=high act=True
REMAINING: Tick S3/S4/S6/D2; add a 'Singular entity - remaining to be usable' block pointing at SE-09, SE-15, SE-16, SE-05/SE-10, SE-11, SE-28.
EVID: HEAD:.handoff/MASTER-TODO.md lines 132-137 still list S3 (W14-W16), S4 (W17-W19), S6 (W22-W24) and D2 as unchecked although main has 0514a5c3, 5f87520c, 6f46f09a, 6a077653, 3ce98551 (D2 resolved as strict <4GB); it has no entry at all for the singular-entity feature, the Devices page, or the remaining Phase 9 items (9.1 confirmation, 9.3 endpoint, 9.6 replay, 9.7 mDNS). Working-tree diff of MASTER

### F3 SE-35 — IMPL-PLAN-SINGULAR-ENTITY-TASKS 'Status: COMPLETE' overstates readiness
status=not_started cat=doc_only prio=P2 conf=high act=True
REMAINING: Amend the completion record with the 'implemented as unit vs. wired in production' distinction and link REV-10.
EVID: Doc header 'COMPLETE — all Fable/Opus/GLM tasks implemented and green' and 'Open items (future work, none blocking)'; verified reality: P7c pairing non-functional (SE-15), P4b/P5b unwired (SE-05/SE-10), workstation compute serving absent (SE-09), 4 tests order-fail (SE-11). REVIEW-RESULTS-REV-10-2026-08-31 already documents F1-F11 and none were fixed after it.
DOC: Claims every phase done and 'none blocking'; pairing UI, compute serving and runtime wiring are blocking for a user.

### F3 SE-36 — Pending doc deliverables (README peer-compute section, design guide, multi-workstation research, remote-Ollama pattern)
status=not_started cat=doc_only prio=P3 conf=high act=False
REMAINING: Hold the README section until SE-09 makes the feature real (writing it now would advertise a broken flow); write the remote-Ollama config pattern (five lines) any time; multi-workstation research stays deferred.
EVID: README.md grep for 'peer compute|Compute Peer|Home Server with' -> 0 hits (HANDOFF-README-PEER-COMPUTE deliverable not written); documentation/design/home-automation.md missing; .handoff/RESEARCH-MULTI-WORKSTATION-RESULTS.md not created (research request open, declared non-blocking); IMPL-PLAN Phase 4 'Ollama endpoints across devices - document only' not documented anywhere (grep)

### F3 SE-37 — PeersConfig singleton: per-request full-file save, no cross-process coherence (REV-10 F9)
status=not_started cat=bug prio=P3 conf=high act=True
REMAINING: Throttle last_seen persistence; mtime-check before save.
EVID: peers_config.py:514-522 `TODO(federation-9.1): Throttle disk writes — for now, save every time`; peer_middleware.py:160 update_last_seen on every authenticated request

### F4 RET-01 — Retire docs/chat-ui-audit branch + worktree (uncommitted README line is a dead link)
status=done cat=retire prio=P2 conf=high act=True
REMAINING: git worktree remove --force ~/.config/superpowers/worktrees/Halbert/chat-ui-audit; git branch -d docs/chat-ui-audit; git push origin --delete docs/chat-ui-audit. Optionally (doc_only) add a correct cross-link from the chat-ui-audit README to documentation/design/11-response-modality-handoff.md on main — neither README nor documentation/design/README.md references the other today.
EVID: git rev-list --left-right --count main...docs/chat-ui-audit = 171/0; merge-base --is-ancestor = yes; tip 0f04d00f == origin/docs/chat-ui-audit. Worktree diff adds one line to halbert_core/halbert_core/dashboard/frontend/docs/chat-ui-audit/README.md linking ./11-response-modality-handoff.md; `git ls-tree main -- .../chat-ui-audit/` lists only 01-10 + README and `git log --all --diff-filter=A -- ...

### F4 RET-02 — Retire feat/compute-peer-setting (no worktree, no remote)
status=done cat=retire prio=P2 conf=high act=True
REMAINING: git branch -d feat/compute-peer-setting (after dropping stash@{0}, which references it only by message).
EVID: main...feat/compute-peer-setting = 148/0; is-ancestor yes; tip 24eb91aa 'chore: ignore .claude/worktrees directory' (main .gitignore:150-151 has the entry). stash@{0} was created on this branch (stash parent 24eb91aa) — see STASH-01.

### F4 RET-03 — Retire feat/ha-simplification branch + worktree (clean)
status=done cat=retire prio=P2 conf=high act=True
REMAINING: git worktree remove ~/.config/superpowers/worktrees/Halbert/ha-simplification; git branch -d feat/ha-simplification.
EVID: main...feat/ha-simplification = 134/0; is-ancestor yes; tip 5f2e7a3e. `git -C ~/.config/superpowers/worktrees/Halbert/ha-simplification status --porcelain` empty. Only .handoff difference vs main is an older MASTER-TODO.md (branch is an ancestor, so strictly older). Worktree 602M incl. 12 node_modules dirs. No remote branch.

### F4 RET-04 — Retire feat/halbert-mcp branch + worktree (uncommitted MASTER-TODO.md is an OLDER copy already on main)
status=done cat=retire prio=P2 conf=high act=True
REMAINING: git worktree remove --force ~/.config/superpowers/worktrees/Halbert/halbert-mcp; git branch -d feat/halbert-mcp; git push origin --delete feat/halbert-mcp.
EVID: main...feat/halbert-mcp = 252/0; is-ancestor yes; tip 4bcccb1b == origin/feat/halbert-mcp. Worktree `.handoff/MASTER-TODO.md` is modified (101+/131-) but `git hash-object` = cd2a7449e86cf2bdbe5fd6905bc297a57e6b5f95, which is byte-identical to the blob committed at abd97592 (2026-08-30 14:38, is-ancestor of main = yes). It is 106 lines with header 'Updated: 2026-08-30' and no U6 reassessment block;
DOC: The halbert-mcp worktree MASTER-TODO.md still lists TASK-01/02/09/10 items (HALBERT_MODEL env wiring, secure_model slot, Settings.tsx decomposition, egress interceptor) as open '- [ ]' rows; main's MASTER-TODO.md supersedes it (commits 7c70276d, 0a610642/bacbfa6b/108c17d9 etc. landed on main after a

### F4 RET-05 — Retire feat/modality-voice-phase2 branch + worktree (clean) + remote
status=done cat=retire prio=P2 conf=high act=True
REMAINING: git worktree remove ~/.config/superpowers/worktrees/Halbert/modality-voice-phase2; git branch -d feat/modality-voice-phase2; git push origin --delete feat/modality-voice-phase2.
EVID: main...feat/modality-voice-phase2 = 144/0; is-ancestor yes; tip 3d4b5a1b == origin/feat/modality-voice-phase2. Worktree status empty. Worktree 617M (12 node_modules).

### F4 RET-06 — Retire feat/rev03-sentient-home-fixes branch + worktree (clean)
status=done cat=retire prio=P2 conf=high act=True
REMAINING: git worktree remove ~/.config/superpowers/worktrees/Halbert/rev03-sentient-home-fixes; git branch -d feat/rev03-sentient-home-fixes.
EVID: main...feat/rev03-sentient-home-fixes = 125/0; is-ancestor yes; tip 7d01720e merged into main by 9a292ce6 (2026-08-31 09:16). Worktree status empty. 601M. No remote.

### F4 RET-07 — Retire feat/singular-entity branch + worktree (clean)
status=done cat=retire prio=P2 conf=high act=True
REMAINING: git worktree remove ~/.config/superpowers/worktrees/Halbert/singular-entity; git branch -d feat/singular-entity.
EVID: main...feat/singular-entity = 59/0; is-ancestor yes; tip 91332aa5. Worktree status empty. 612M. No remote. (feat/singular-entity-opus at 76/7 is a DIFFERENT, unmerged branch — out of this scope.)

### F4 RET-08 — Retire feat/voice-mode-visual-ui branch + worktree .claude/worktrees/voice-mode-opus (only untracked wt_pytest.py)
status=done cat=retire prio=P2 conf=high act=True
REMAINING: After WT-01: git worktree remove --force /Volumes/4TB-BAD/Halbert/.claude/worktrees/voice-mode-opus; git branch -d feat/voice-mode-visual-ui.
EVID: main...feat/voice-mode-visual-ui = 18/0; is-ancestor yes; tip 88413a42 is the second parent of main's HEAD merge 4a7bf71f. Worktree status: only `?? wt_pytest.py` (identical to the other 3 copies, see WT-01). 604M. No remote. `.claude/worktrees/` is git-ignored (main .gitignore:151).

### F4 RET-09 — Retire voice-mode-v2-backup branch + worktree voice-mode-reland (only untracked wt_pytest.py)
status=done cat=retire prio=P2 conf=high act=True
REMAINING: After WT-01: git worktree remove --force ~/.config/superpowers/worktrees/Halbert/voice-mode-reland; git branch -d voice-mode-v2-backup.
EVID: main...voice-mode-v2-backup = 14/0; is-ancestor yes; tip 38e95899. Worktree status: only `?? wt_pytest.py`. 604M. No remote. The 'backup' purpose is moot since main contains every commit.

### F4 RET-10 — Retire worktree-central-todo-batches branch + worktree (7.0G, of which 6.4G is git-ignored src-tauri/target)
status=done cat=retire prio=P1 conf=high act=True
REMAINING: After WT-01: git worktree remove --force /Volumes/4TB-BAD/Halbert/.claude/worktrees/central-todo-batches; git branch -d worktree-central-todo-batches. Reclaims ~7 GB.
EVID: main...worktree-central-todo-batches = 85/0; is-ancestor yes; tip f112151b 'Merge branch main into worktree-central-todo-batches'. Worktree status: only `?? wt_pytest.py` (+ ignored __pycache__/.pytest_cache). du: halbert_core/halbert_core/dashboard/frontend/src-tauri = 6.4G (check-ignore: src-tauri/.gitignore:3 `/target/`), packages 242M, node_modules 260M. This branch's reflog is the only refere

### F4 RET-11 — Delete remote-only origin/feat/federated-fleet
status=done cat=retire prio=P3 conf=high act=True
REMAINING: git push origin --delete feat/federated-fleet.
EVID: main...origin/feat/federated-fleet = 204/0; is-ancestor yes; tip 7bff44ca 'fix: §11 scrutiny pass'. No local branch, no worktree.

### F4 RET-12 — Delete remote-only origin/feat/plan-b-terminals
status=done cat=retire prio=P3 conf=high act=True
REMAINING: git push origin --delete feat/plan-b-terminals.
EVID: main...origin/feat/plan-b-terminals = 347/0; is-ancestor yes; tip ee5e3c4c 'test(e2e): Plan B Playwright browser smoke (B20)'; merged at 0ba316b2. No local branch, no worktree.

### F4 STASH-01 — Drop stash@{0} 'duplicate U6-S3 compute-peer work' — fully superseded on main
status=obsolete cat=retire prio=P2 conf=high act=True
REMAINING: git stash drop stash@{0} (drop by index carefully: dropping @{0} renumbers @{1} to @{0}; or drop stash@{1} first).
EVID: `git stash show -p stash@{0}`: 3-line change to halbert_core/halbert_core/model/client.py adding "peer" to CHAT_CAPABLE_PROVIDERS. main client.py:72-77 already has `{"ollama", "llamacpp", "mlx", "anthropic", "peer"}` with a fuller comment (commit 0514a5c3 'feat(peer): register PeerProvider in the model stack ... (U6 S3 W14/W16)'). The stash also carries an untracked-files tree (stash@{0}^3) with h

### F4 STASH-02 — Drop stash@{1} 'WIP on main: ece8972a' — 1-line change already on main
status=obsolete cat=retire prio=P3 conf=high act=True
REMAINING: git stash drop stash@{1}.
EVID: `git stash show -p stash@{1}`: renames the unused prop `onPaired` to `onPaired: _onPaired` in ManualPairingForm, halbert_core/halbert_core/dashboard/frontend/src/components/fleet/PeerPairingModal.tsx. main's PeerPairingModal.tsx:147 reads exactly `function ManualPairingForm({ onClose, onPaired: _onPaired }: ...)`. No untracked tree on this stash.

### F4 ORPHAN-01 — Commit 5057e893 is a reset-and-recommitted duplicate of 31fa91ef; REV-02 doc content is identical to main
status=obsolete cat=cleanup prio=P3 conf=high act=False
REMAINING: Nothing. The commit disappears with the worktree-central-todo-batches reflog (RET-10) and eventual gc.
EVID: `git branch -a --contains 5057e893` = none. Reflog of worktree-central-todo-batches: @{36} commit 5057e893 (08:34:06), @{35} 'reset: moving to HEAD~1', @{34} commit 31fa91ef (08:34:15) with the same subject. `git diff 5057e893 main -- .handoff/REVIEW-RESULTS-REV-02-2026-08-31.md` is EMPTY; both versions carry the same 11 headings (F1 confirm-gate escalation, F2 Content-Length, F3 auth-before-ratel
DOC: An earlier audit claimed 5057e893 carries '6 new findings incl. F1 HIGH' not on main. Wrong: the document is byte-identical to main's 31fa91ef version; all six confirmed findings F1-F6 are already on main.

### F4 HADIR-01 — ~/.config/superpowers/worktrees/Halbert/home-automation is NOT a worktree — a 128K leftover of 3 edited files from the Aug-28 feat/home-automation era
status=obsolete cat=cleanup prio=P2 conf=high act=True
REMAINING: rm -rf ~/.config/superpowers/worktrees/Halbert/home-automation (plain directory; no git command needed). If the founder decides to wire HomeCognitiveLoop (LOOP-01), copy its app.py lines 578-610 and 661-670 out first as a starting draft; note that draft predates the REV-03 F12 aiohttp-session fix advice.
EVID: `ls -la` shows only halbert_core/ (no .git file); `.git/worktrees/` holds 15 admin entries, none for home-automation, so `git worktree prune` has nothing to prune. Files: halbert_core/halbert_core/dashboard/app.py (678 lines), integrations/cognition_wiring.py (316), dashboard/routes/agent.py (1863), all mtime 2026-08-31 07:47:34; `git log --all --find-object=<blob>` finds no commit for any of them

### F4 LOOP-01 — HomeCognitiveLoop is defined and tested but never instantiated at runtime on main — 'instantiate or delete' half of REV-03 F1 still open
status=in_progress cat=decision prio=P1 conf=high act=True
REMAINING: Founder decision: (A) wire HomeCognitiveLoop start/stop into dashboard/app.py lifespan gated by the home capability, fixing F12 (loop-owned aiohttp client, run as one async task) and adding a startup test; or (B) delete home/cognitive_loop.py + test_cognitive_loop.py and update the HA strategy doc. Given 'complete current features' direction, (A) is the feature-complete path; the home-automation dir app.py draft (HADIR-01) is a usable starting point.
EVID: `git grep -n 'HomeCognitiveLoop(' main -- 'halbert_core/halbert_core/**/*.py'` returns nothing outside halbert_core/tests/test_cognitive_loop.py; class lives at halbert_core/halbert_core/home/cognitive_loop.py:59, exported in home/__init__.py:12. .handoff/REVIEW-RESULTS-REV-03-2026-08-31.md:33 states the class has 'zero instantiation sites' and :39 says 'Either instantiate HomeCognitiveLoop at sta
DOC: .handoff/REVIEW-REQUEST-HA-STRATEGY-AND-HALBERTOS-2026-08-31.md:231/281 claim 'The cognitive loop IS the automation engine' / 'already is the automation engine'; on main the loop has no instantiation site, so nothing ticks.

### F4 WT-01 — Commit one canonical wt_pytest.py at the repo root (4 identical untracked copies; a dozen handoff docs tell sessions to use it)
status=not_started cat=needs_commit prio=P2 conf=high act=True
REMAINING: cp any one copy to /Volumes/4TB-BAD/Halbert/wt_pytest.py and commit it on main (subject e.g. 'chore(test): add wt_pytest.py worktree test wrapper') BEFORE removing the worktrees in RET-08/09/10. Every future worktree then gets it automatically and the untracked-file noise disappears.
EVID: md5 of all four copies = 1e4ec209aa07868d844d807d21b966cc (2278 bytes, executable): ~/.config/superpowers/worktrees/Halbert/voice-mode-reland/wt_pytest.py, .../voice-mode-visual-ui/wt_pytest.py, /Volumes/4TB-BAD/Halbert/.claude/worktrees/central-todo-batches/wt_pytest.py, .../voice-mode-opus/wt_pytest.py. `git log --all -- wt_pytest.py '*/wt_pytest.py'` empty (never tracked); `git check-ignore -v 

### F5 U4-01 — TASK-01 remainder: HALBERT_MODEL env override fills an unconfigured chat slot
status=done cat=merge_ready prio=P2 conf=high act=True
REMAINING: Nothing in code. Tick MASTER-TODO.md line 121 ('[ ] HALBERT_MODEL env var wiring') and TASK-PACKET-01 status — both still say it is open.
EVID: Commit 7c70276d on main (git merge-base --is-ancestor OK, dated 2026-08-31). halbert_core/halbert_core/model/llm_config.py:781-823 — resolve() falls through to _env_chat_model_override() only for slot=='chat_model' and only when models.yml has no assignment; returns None on home/home-light via cognition_wiring._get_variant(). Test run on main: halbert_core/tests/test_llm_config_env_override.py 5 p
DOC: MASTER-TODO.md:121 and :79 say the env override is still open; it landed on main in 7c70276d.

### F5 U4-02 — test_multi_instance::test_instance_info_home fails on main (baseline, not U4-caused)
status=unknown cat=bug prio=P3 conf=medium act=True
REMAINING: Decide whether get_instance_info()'s role field should still say 'home' for HALBERT_PERSONA_ID=home (test expectation) or the test is stale after the variant/capability rework; fix one side.
EVID: arch -arm64 pytest halbert_core/tests/test_multi_instance.py → 1 failed: test_instance_info_home asserts result['role']=='home' but gets 'host' (test file line 104). Present in the whole-suite baseline: scratchpad/pytest-main.txt line 122. Not touched by 7c70276d (which only changed llm_config.py + its test).

### F5 U4-03 — TASK-01 Task 1.4: no deployment doc/unit mentions the new HALBERT_MODEL dial
status=not_started cat=doc_only prio=P3 conf=high act=True
REMAINING: Optional: add an `Environment=HALBERT_MODEL=` example (commented) to the sysadmin deploy unit/README. Packet 1.4 erratum suggested doing this as part of 1.1; it was not.
EVID: grep HALBERT_MODEL over *.service/*.md/*.yml outside .handoff → no hits in deploy/ (deploy/halbert-home.service has none; packet erratum confirmed). test_llm_config_env_override.py:5-6 documents the intended use as an Environment= line.

### F5 U4-06 — TASK-04 Steps 3-5: gpu-assessment module + GpuAssessmentModule.tsx + ModuleRenderer/onModuleInvoke — NOT built
status=not_started cat=incomplete_feature prio=P2 conf=high act=True
REMAINING: Decide whether structured assessment cards are still wanted. If yes: register `gpu-assessment` ModuleDef, add GpuAssessmentModule.tsx, add `onModuleInvoke` to AIAnalysisPanel and handle `module_invoke` SSE events (plan Option B), render ModuleRenderer under the panel in GPU.tsx. If no: mark steps 3-5 as deliberately dropped in the plan doc.
EVID: grep -i gpu halbert_core/halbert_core/modules/registry.py → nothing. ls dashboard/frontend/src/components/modules/ → ConfigDiffModule, DriveHealthModule, EvidenceModule, ModuleLoadError, VitalsModule only. grep onModuleInvoke|module_invoke AIAnalysisPanel.tsx → nothing; ModuleRenderer.tsx has no gpu entry. fbfb5614 commit message: dropped 'the now-dead inline analysis rendering, GPUAnalysis interf
DOC: HANDOFF-CENTRAL-TODO-BATCHES §1 U4 describes the GPU work as complete; the plan's structured-output half (steps 3-5) was silently dropped.

### F5 U4-08 — TASK-04 Step 7: CUDA/driver knowledge doc is orphaned — written to data/knowledge/linux/, which nothing stages or indexes
status=in_progress cat=incomplete_feature prio=P1 conf=high act=True
REMAINING: Put the document where retrieval can see it: either move it under the real corpus/knowledge staging path (knowledge/linux) and add it to the corpus manifest, or stage it into the host tree so scope 'host' carries it; re-embed; update the matrix to 2026 (580.x/CUDA 13 per the plan). Add a retrieval test or a quality-gate query that proves the doc is returned.
EVID: data/knowledge/linux/nvidia_cuda_compatibility.md exists (70 lines, matrix ends at 575.x). `git log -- data/knowledge` → only 162f3965: the directory is new. The corpus lives in data/linux, data/macos, data/common (scripts/merge_rag_data.py:82, dedup_corpus.py:135) and the SourcePrep knowledge tree is staged at ~/.local/share/halbert/sourceprep/knowledge/<platform> (scripts/staged_knowledge_embed.
DOC: HANDOFF-CENTRAL-TODO-BATCHES claims 'CUDA knowledge extracted to data/knowledge/linux/nvidia_cuda_compatibility.md' as done — the file exists but is unreachable by any index.

### F5 U4-09 — TASK-04 Step 8: dead code left in routes/gpu.py (analyze endpoint, YAML analysis cache, search_latest_driver_info)
status=not_started cat=cleanup prio=P3 conf=high act=True
REMAINING: Remove /analyze, /analysis-cache and the YAML cache (or document the back-compat client that needs them); drop search_latest_driver_info tool or at least remove the stale year literals; update test_gpu_routes.py accordingly.
EVID: halbert_core/halbert_core/dashboard/routes/gpu.py: _get_analysis_cache_path/save_gpu_analysis/load_gpu_analysis :47-99, GET /analysis-cache :277-313, POST /analyze :316-379 (now delegates to agent via _run_agent_turn :180-203; commit 162f3965 says kept 'for backward compatibility'). No frontend caller for either endpoint (grep 'gpu/analy|analysis-cache' in frontend src → none). tools/gpu_tools.py:

### F5 U4-11 — MASTER-TODO/packet still say the GPU raw-Ollama call is open
status=obsolete cat=doc_only prio=P3 conf=high act=True
REMAINING: Rewrite the two MASTER-TODO lines: tools/registration/panel/tests done; steps 3-5, 7 (indexing), 8 remain.
EVID: MASTER-TODO.md:82 'Open — raw Ollama call still in routes/gpu.py:693' and :148 '[ ] GPU Page Deep Scan Rebuild'; TASK-PACKET-04 'Verified 2026-08-30: confirmed still open'. On main gpu.py is 378 lines with no requests.post/api/chat (grep), tests assert it. The dirty-tree MASTER-TODO diff adds no U4 lines.
DOC: MASTER-TODO.md:82,148 stale vs main 162f3965/fbfb5614.

### F5 U4-12 — TASK-05 Task 5.1 (SendMessageRequest.context plumbing) — obsolete, confirmed removed
status=obsolete cat=deferred prio=P3 conf=high act=False
REMAINING: 
EVID: halbert_core/halbert_core/dashboard/routes/agent.py:39 class SendMessageRequest has no `context` field (grep). Packet + MASTER-TODO erratum 1 agree. halbert_core/tests/test_agent_context_plumbing.py does not exist (correctly).

### F5 U4-14 — TASK-05 Task 5.3: role scopes are indexed but unreachable at query time — no template scope carries assigned_to_role
status=in_progress cat=incomplete_feature prio=P1 conf=high act=True
REMAINING: Add assigned_to_role to sourceprep_template.yml for scopes with a builtin skill (network_admin→network-ops, service_admin→service-ops, storage_admin→storage-ops, security_admin→security-ops); decide skills for shell/package/boot/sharing/credentials (none exist) or accept they are keyword-unreachable; re-apply against a live daemon and confirm _role_warning is empty; add a test that the template declares a role for every scope a builtin skill names.
EVID: sourceprep_template.yml scopes (:48-94) have id/paths/pipeline_profile only; `grep assigned_to_role sourceprep_template.yml` → none; `git log -S assigned_to_role -- sourceprep_template.yml` → never present. integrations/sourceprep_retrieval_backend.py:296-316 builds _roles_to_scope solely from the daemon's assigned_to_role, and resolve_role():351-375 returns None otherwise; context/adapters.py:384
DOC: HANDOFF-CENTRAL-TODO-BATCHES lists 'Role-scope taxonomy completed' as done; the taxonomy is complete but the retrieval routing to it never was.

### F5 U4-15 — RoleScope.aliases_from is declared (5 edges) but has no consumer
status=not_started cat=incomplete_feature prio=P2 conf=high act=True
REMAINING: Either have _reconcile_scopes/stage_role_tree add aliased primaries' paths into the aliasing scope's mask, or delete the field and its comments.
EVID: config/roles.py:80,101,127,155 declare aliases_from; `grep -rn aliases_from halbert_core/halbert_core` outside roles.py → nothing. TODO-ROLE-SCOPED-CONFIG-2026-08-27 §3.4 flagged 'wire aliasing in wave 2 or drop the field'; e567a529 added more edges and 'resolves the two dangling alias claims' but still wires no consumer.

### F5 U4-16 — Role-scoped carry-forwards from TODO-ROLE-SCOPED-CONFIG: verified status
status=in_progress cat=deferred prio=P3 conf=medium act=True
REMAINING: Run corpus_quality_gate.py once against a built index (Linux for package/boot); decide flat-vs-role staging topology; two narrow redaction fixes.
EVID: Landed: scope_mode='hard' default (integrations/sourceprep_client.py:118,153); applied_scope/scope_warning observability (_check_applied_scope backend:377-385,464); per-scope to_remove reconciliation (sourceprep_setup.py:355-368). Not done: end-to-end quality gate never run (scripts/corpus_quality_gate.py now 19 role queries; e567a529 says package/boot terms 'require a Linux-built corpus'); role t

### F5 U4-18 — REGRESSION: Apple Intelligence auto-provisioning can never fire — gated on a capability whose probe requires the secure slot to already exist
status=in_progress cat=bug prio=P1 conf=high act=True
REMAINING: Gate provisioning on a non-circular predicate (variant preset / being.yml override, i.e. the registry's preset for CAP_SECURE_MODEL without the probe, or a new 'secure_model_allowed' capability), keep _probe_secure_model as the 'is it configured' signal only; make test_auto_provision.py hermetic (use the conftest capability controller) so it fails in the suite too; re-run test_auto_provision.py + test_apple_intelligence_platform.py.
EVID: Commit 330f641b (2026-08-31, on main; 'complete F5 — convert all remaining variant gates') replaced the home-variant check with has_capability(CAP_SECURE_MODEL) in model/auto_provision.py:72-83, dashboard/routes/llm.py:213-222 and model/config_wizard.py:141-154. capabilities.py:192-204 _probe_secure_model returns True only if resolve('secure_model') yields a local URL, and capabilities.py:86 prese
DOC: HANDOFF-CENTRAL-TODO-BATCHES §1 U4 'Apple Intelligence platform verification: PASS (28/28)' — the two named files hold 26 tests and 4 now fail on main; the claim was true on the batches branch before F5 landed.

### F5 U4-19 — REV-05 F2 still open: slot assignment ignores apple_intelligence_bridge_running; wizard overrides a user-chosen local chat model on 16-24GB Macs
status=not_started cat=bug prio=P1 conf=high act=True
REMAINING: Gate slot assignment (not endpoint registration) on bridge_running, or on the bridge existing at all; stop ai_takes_chat from overriding an explicit Ollama choice; surface 'eligible, bridge not started' in Settings. Currently masked by U4-18 — fixing U4-18 alone re-exposes dead-slot assignment.
EVID: model/auto_provision.py:69 gates only on hardware.apple_intelligence_available; hardware_detector.py:296-299 computes bridge_running separately and nothing reads it for slot writes; config_wizard.py:475-524 writes ep_apple_foundation + secure/chat slots whenever ai_available. .handoff/REVIEW-RESULTS-REV-05-2026-08-31.md F2 (CONFIRMED High) and §4 item 2 'one-line gate plus wizard override removal'

### F5 U4-20 — Swift FoundationModels bridge (halbert-foundation-bridge) — no source, no build script, no sidecar config; feature is inert end-to-end
status=not_started cat=incomplete_feature prio=P1 conf=high act=True
REMAINING: Founder decision: (a) build the sidecar — Swift SPM package implementing /v1/health, /v1/models, /v1/chat/completions on loopback via LanguageModelSession, arm64 build script, tauri externalBin + spawn/kill lifecycle, App Store entitlement review; or (b) hide/disable the apple-foundation provider in the picker and skip provisioning until (a) exists. Given 'finish current features', (b) is the cheap correct interim step and unblocks U4-18/U4-19 safely.
EVID: find repo -name '*.swift' / Package.swift → none; root tools/ directory does not exist (handoff §6.12 planned tools/apple_intelligence_bridge/); src-tauri/tauri.conf.json:40-42 externalBin = ['binaries/halbert-api'] only; src-tauri/binaries/ holds only halbert-api stubs; src-tauri/src/*.rs has no foundation-bridge spawn (grep). Python expects it on 127.0.0.1:11435 (/v1/models): hardware_detector.p
DOC: HANDOFF-CENTRAL-TODO-BATCHES correctly calls it the 'known open deliverable'; MASTER-TODO :155/:88 imply the merge finished the feature.

### F5 U4-21 — TASK-10 Task 10.2(1): HardwareDetector.detect() is uncached; skipped today only as a side effect of the U4-18 gate
status=not_started cat=bug prio=P2 conf=medium act=True
REMAINING: Memoise detect() per process (or persist an 'apple_intelligence_checked' marker) so the probe runs once at first boot as the packet requires; add a test that a second GET does not call HardwareDetector.detect().
EVID: grep -i cache model/hardware_detector.py → none (only a KV-cache comment :94). routes/llm.py:205-222 skips detect() when the apple-foundation endpoint already exists OR has_capability(CAP_SECURE_MODEL) is False. On a host that is not eligible (Intel Mac, <16GB, Linux) the endpoint is never registered, so once the U4-18 gate is fixed detect() (system_profiler + sysctl ~1s on Macs, per the code comm

### F5 U4-23 — REV-05 review (U4 deliverable) executed; F1/F3-F9 remain unfixed on main
status=done cat=deferred prio=P2 conf=high act=True
REMAINING: Triage F3 (small, security) and F5 with the LLM-router owner; F1 belongs to the compute-peer session.
EVID: .handoff/REVIEW-RESULTS-REV-05-2026-08-31.md: PASS WITH FINDINGS; F1 peer:// streaming (High, federation owner), F2 (U4-19), F3 /api/llm/config serves plaintext API keys (Medium, security), F4 no image translation for OpenAI/Anthropic wires, F5 GPU advisory lock not on streaming path, F6-F9 low. §3 confirms the GPU refactor and HALBERT_MODEL override as resolved packet claims.

### F6 U6-W25 — W25/S7 — LOW-POWER handoff §7 revision + stale <=4GB comments
status=in_progress cat=doc_only prio=P3 conf=high act=True
REMAINING: Doc-only sweep of HANDOFF-LOW-POWER-HARDWARE-TIERS-AND-EDGE-CASES-2026-08-29.md: mark D2 resolved (<4GB, code wins), drop home-light, tick §8 :194; fix two test docstrings.
EVID: Code comments fixed: hardware_detector.py:34 '<4GB', compute_router.py:29 '<4GB' (3ce98551). Doc §7.1 1B row dropped and Q2_K/IQ2_XXS struck (.handoff/HANDOFF-LOW-POWER-...md:159,174-176, commit 1fd6dba1). BUT the doc still says 'open decision D2' at :7,20,53,111,155,185 (D2 was resolved option b), 'home-light' 28 times (D4 merged it away), §8 :185 '<=4GB', §8 :194 unchecked though W17-W19 shipped
DOC: LOW-POWER doc says D2 is an open decision and refers to home-light; both were resolved 2026-08-30 (8545af94, 3ce98551).

### F6 U6-D4 — D4 — home-light merged into home (single variant)
status=done cat=cleanup prio=P3 conf=high act=True
REMAINING: Trim the dead 'home-light' literal at llm_config.py:816 and the comment in test_llm_config_env_override.py:12 (harmless but misleading).
EVID: config/being_config.py:36 VALID_VARIANTS = {'sysadmin','home'}; cognition_wiring.py:182 HA_VARIANTS=('home',); app.py has no 'home-light'; commit 8545af94 (33 files). Residual stale refs introduced AFTER D4: model/llm_config.py:816 `if _get_variant() in ('home','home-light')` (7c70276d, 2026-08-31) and tests/test_llm_config_env_override.py:12 comment; only 2 code/test files reference home-light on
DOC: MASTER-TODO.md:123 still says 'Phase 8 Light Variant (home-light) Done' and :30/:121-122 reference home/home-light; the variant no longer exists.

### F6 U6-BUG-01 — Capability registry ignores HALBERT_VARIANT env — documented home deployment gets the sysadmin preset
status=not_started cat=bug prio=P1 conf=high act=True
REMAINING: Make CapabilityRegistry._load_config resolve the variant through cognition_wiring._get_variant() (or explicit_variant() then env), add a test_capabilities.py case for env-only home, and either add `variant: home` to the deploy README/being.yml example or keep env as a supported leg.
EVID: capabilities.py:264-267 `cfg = load_being_config(); variant = cfg.variant` (defaults 'sysadmin' when being.yml lacks variant:), never consults explicit_variant()/env; vs cognition_wiring.py:158-174. Repro (HALBERT_VARIANT=home, empty config dir): `_get_variant()=home, is_home_variant()=True` but `registry _load_config variant = sysadmin; has(scheduler)=True has(ingestion)=True has(discovery)=True 

### F6 U6-BUG-02 — secure_model provisioning is gated on a capability that is only true once provisioned (fresh sysadmin installs never get a secure model)
status=not_started cat=bug prio=P1 conf=high act=True
REMAINING: Gate provisioning/wizard writes on 'can host a secure model' (variant preset / Apple Intelligence or local Ollama presence, e.g. CAP_LOCAL_LLM or hardware.apple_intelligence_available), not on CAP_SECURE_MODEL; keep CAP_SECURE_MODEL for the turn gate. Then make test_auto_provision.py pass in isolation.
EVID: capabilities.py:192-204 _probe_secure_model = 'secure_model slot resolves to a local URL'; :86 sysadmin preset False ('only if a secure endpoint is configured'); probe wins over preset (:293-303). Consumers: auto_provision.py:72-83 returns False when !has_capability(CAP_SECURE_MODEL); routes/llm.py:219 same gate; config_wizard.py _build_config secure_allowed=_has_secure_cap -> writes ''. Repro (no
DOC: HANDOFF-F5-REVIEW-2026-08-31.md:30-31 claims 'config_wizard + auto_provision + llm.py Apple Intelligence provisioning — all converted' correctly; the conversion made provisioning unreachable on fresh installs.

### F6 U6-BUG-03 — Frigate event-mapper queue still unbounded (HA queue was capped)
status=in_progress cat=bug prio=P2 conf=high act=True
REMAINING: Add the same MAX_PENDING_EVENTS cap/drop-oldest (or deque(maxlen)) to FrigateEventMapper.handle_event and a test mirroring the HA one.
EVID: integrations/home_assistant/ha_event_mapper.py:36 MAX_PENDING_EVENTS=500, :52-54 drop-oldest (7d01720e REV-03 F1) — fixed. integrations/frigate/frigate_event_mapper.py:120 `_pending_events: List = []`, :135 append with no cap. Drained only by state_machine.py:2628 populate_cognition inside the cognition tick (requires haloysius; cognition_wiring.py:350) or home/cognitive_loop.py:269 (HomeCognitive

### F6 U6-BUG-04 — Frigate snapshots never reach the vision model (returned as base64 strings, router only handles dict['image'])
status=not_started cat=bug prio=P2 conf=high act=True
REMAINING: Return {'image': b64, 'description': ...} from frigate_get_snapshot / frigate_get_latest_frame (the vision-tool contract) so the base64 is routed as an image instead of a giant text observation; add a state-machine test.
EVID: integrations/frigate/frigate_tools.py:239-240 and :256-257 return 'data:image/jpeg;base64,...' strings; agents/state_machine.py:2492 routes to ctx.images only when `isinstance(result.result, dict) and 'image' in result.result` (same at :1621). Surfaced by Q3 investigation (continuation handoff §2.3, §4.1); no fix commit since.

### F6 U6-BUG-05 — test_multi_instance.py::test_instance_info_home fails deterministically (test not updated for REV-03 F8)
status=not_started cat=test_gap prio=P2 conf=high act=True
REMAINING: Set HALBERT_VARIANT=home in the test env (and clear any being.yml variant); one-line fix.
EVID: routes/instance.py:39-41 role derived from _get_variant() (7d01720e REV-03 F8); tests/test_multi_instance.py:93-104 sets only HALBERT_PERSONA_ID=home, never HALBERT_VARIANT -> 'assert result["role"] == "home"' fails with 'host'. `git diff 4e4ff2f4 main -- tests/test_multi_instance.py` is empty. Present in the full-suite baseline.

### F6 U6-TEST-01 — Capability-registry singleton pollution makes U6-adjacent tests order-dependent
status=not_started cat=test_gap prio=P2 conf=high act=True
REMAINING: Add an autouse fixture in tests/conftest.py calling capabilities.reset_registry() (and clearing llm_config caches) so every test starts from an unprobed registry; then re-run test_llm_routes + test_auto_provision in both orders.
EVID: tests/test_llm_routes.py: 12/12 alone; 4 fresh-install tests fail after tests/test_auto_provision.py or tests/test_agent_model_override.py (bisect output) and in the full suite (pytest-main.txt). tests/test_auto_provision.py: 4 fail alone, pass in the full suite. capabilities.py:_registry singleton is only reset by tests that opt into conftest.py:35-75 capability_registry (monkeypatch) — no autous

### F6 U6-DESIGN-01 — F5 'probe beats preset' silently reverses U6 S2 on any home node where sourceprep is importable
status=unknown cat=decision prio=P2 conf=high act=True
REMAINING: Founder ratification: either accept 'home uses SourcePrep if installed' (then update the U6 handoff + deploy/README.md:126), or make the home preset an explicit False override for sourceprep/config_watcher unless being.yml opts in.
EVID: capabilities.py:293-303 order = being.yml override > probe > preset; :146-160 _probe_sourceprep = importlib.import_module('sourceprep') succeeds -> True regardless of variant (09ec6eb7 made probes presence-only on purpose). Home preset sourceprep False (:92) is therefore dead whenever the package is installed; same for config_watcher when config-registry.yml exists. U6 handoff §12 W7-W11 and deplo
DOC: HANDOFF-HOME-AUTOMATION-SIMPLIFICATION §12 / deploy/README.md:126 state home never uses SourcePrep; capabilities.py (F5) makes that conditional on package presence.

### F6 U6-CLEANUP-01 — Retire worktree-u6-home-simplification (parallel U6 implementation, superseded)
status=obsolete cat=retire prio=P2 conf=high act=True
REMAINING: git worktree remove .claude/worktrees/u6-home-simplification && git branch -D worktree-u6-home-simplification (nothing to salvage).
EVID: 16 commits main..worktree-u6-home-simplification (8fbf23ee..12e31380); `git merge-tree --write-tree main worktree-u6-home-simplification` exit 1 with conflicts in 36 files; 092117dd ported its unique tests (test_compute_router_route, test_memory_route_degrades, wizard-schema fix, explicit_variant tests) and documents test_public_api.py -> test_package_exports.py and test_ha_no_sourceprep.py -> tes

### F6 U6-CLEANUP-02 — Delete fully-merged feat/ha-simplification + feat/compute-peer-setting branches and drop stash@{0}
status=obsolete cat=retire prio=P3 conf=high act=True
REMAINING: git worktree remove ha-simplification; git branch -d feat/ha-simplification feat/compute-peer-setting; git stash drop stash@{0}.
EVID: `git branch --merged main` lists feat/ha-simplification and feat/compute-peer-setting; `git merge-base --is-ancestor feat/compute-peer-setting main` true; ha-simplification worktree (~/.config/superpowers/worktrees/Halbert/ha-simplification) status clean; stash@{0} 'duplicate U6-S3 compute-peer work' = the single `"peer"` addition to CHAT_CAPABLE_PROVIDERS already on main at client.py:75-76.

### F6 U6-DOC-01 — MASTER-TODO.md Batch U6 section is stale (everything listed unchecked)
status=not_started cat=doc_only prio=P3 conf=high act=True
REMAINING: Tick D1/S1-S7/D2-D4 with the merge shas, add the four open follow-ups (U6-BUG-01..04), and drop home-light wording.
EVID: .handoff/MASTER-TODO.md:129-139 D1, S1-S7, D2-D4 all '[ ]' though merged in 4e4ff2f4/93c863c1 (2026-08-30); :123 'Phase 8 Light Variant (home-light) Done' post-D4 stale; :30,:121-122 mention home/home-light. Untracked .handoff/HANDOFF-BRANCH-AND-WORKTREE-AUDIT-2026-09-01.md:32-34 (another session) already flags both. MASTER-TODO.md is modified in the dirty main tree by another session — do not edi
DOC: MASTER-TODO says U6 is entirely open; main has it entirely merged.

### F6 U6-COSMETIC-01 — Continuation handoff §2.5 minor findings — status
status=in_progress cat=cleanup prio=P3 conf=high act=False
REMAINING: Optional tidy: unify peer_probe error convention, add trailing newlines, delete the four dead _is_home_variant helpers when those files are next touched.
EVID: Still present: routes/compute.py:27,36,39 peer_probe returns HTTP 200 {'error':...} while peers.py raises HTTPException; providers/peer.py:349 is_loaded(PEER_GOVERNED_MODEL) unconditionally True (deliberate until federation-9.3); client.py:503-509 _call_peer stream NotImplementedError (TODO 9.4); hooks/useInstanceVariant.ts and .test.ts lack trailing newline (xxd). Resolved: app.py 'HALBERT_VARIAN

### F7 R3-F01b — REV-03 F1 residual: HomeCognitiveLoop is still dead code with asyncio.run-per-tick client reuse
status=not_started cat=cleanup prio=P3 conf=high act=True
REMAINING: Delete home/cognitive_loop.py and its export, or wire it as one loop-owned async task with a per-loop client. Do not leave it half-wired.
EVID: grep HomeCognitiveLoop: only home/__init__.py:12,18 (export), zero instantiation sites; home/cognitive_loop.py:178,229,325 still call asyncio.run() on a shared ha_client (the REV-03 F12 loop-bound-session bug). Review said 'instantiate at startup or delete it' — neither happened.

### F7 R3-F02-T — No tests cover the chat-path AutonomyGate or the /home/service 403
status=not_started cat=test_gap prio=P2 conf=high act=True
REMAINING: Add tests: _ha_call_service_handler at autonomy_level=observe returns 'Blocked', lock.unlock at act returns proposal message, POST /api/home/service returns 403 when gate blocks.
EVID: grep 'autonomy|observe|_get_autonomy_gate' halbert_core/tests/test_home_assistant.py → no hits; grep 'home/service' halbert_core/tests/*.py → no hits. test_mcp_ha_tools.py covers only the MCP path.

### F7 R3-F03 — REV-03 F3: describe → info handshake (event type fixed; payload keys not per spec)
status=in_progress cat=bug prio=P2 conf=medium act=True
REMAINING: Emit a spec-shaped Info (e.g. handle: [{name, attribution:{name,url}, installed:true, version, models:[...]}]) or explicitly document the text-only dialect and drop the native-HA claim in the module docstring (:21-22).
EVID: wyoming_agent.py:301-315 replies type 'info' (test_ha_phase4.py:240 asserts it). Payload uses 'versions': '1' and a 'conversation' object; the Wyoming Info event carries service lists (asr/tts/handle/intent/wake/satellite) with per-service 'installed'/'attribution'/'version' — HA's integration keys off those lists, so it still would not register Halbert as a handler. The wyoming package is not in 
DOC: REV-03-RESUBMISSION says F3 is fixed 'per the Wyoming protocol spec'; only the event type is.

### F7 R3-F04 — REV-03 F4: audio-chunk PCM drain is ineffective — reads payload_length from data{} instead of the header
status=in_progress cat=bug prio=P1 conf=high act=True
REMAINING: Use msg.get('payload_length') and msg.get('data_length') (or reuse read_wyoming_frame from audio/ingress/wyoming_ingress.py) and add a test that feeds header+PCM+ping and asserts a pong.
EVID: wyoming_agent.py:291 `payload_len = data.get('payload_length', 0)`; the spec and the repo's own reader put it at header top level (wyoming_ingress.py:8, :75 `header.get('payload_length')`). Repro (scratchpad/agents/rv-03-09-home-voice/repro_f4_f10.py): one canonical audio-chunk frame → 8× 'Invalid JSON from Wyoming client' warnings and a following ping produced no pong (writer output b''). data_le
DOC: REV-03-RESUBMISSION claims F4 fixed via readexactly(payload_length); the key lookup is wrong so it never executes.

### F7 R3-F07 — REV-03 F7: home-light divergence — obsolete after D4, two residual crumbs
status=obsolete cat=cleanup prio=P3 conf=high act=True
REMAINING: Drop the 'home-light' literal at llm_config.py:816; validate env-provided variant against VALID_VARIANTS.
EVID: being_config.py:36 VALID_VARIANTS={'sysadmin','home'}; cognition_wiring.py:182 HA_VARIANTS=('home',); test_multi_instance.py history 8545af94 'merge home-light into home (D4)'. Residual: model/llm_config.py:816 still tests `in ('home','home-light')`; cognition_wiring.py:174 returns HALBERT_VARIANT env unvalidated (a typo silently behaves as sysadmin).

### F7 R3-F08 — REV-03 F8: role derives from variant — fixed, but test_instance_info_home is red on main
status=in_progress cat=test_gap prio=P2 conf=high act=True
REMAINING: Update the test to set HALBERT_VARIANT=home (and clear being.yml variant) or assert on persona_id only; confirm test_instance_info_display_name expectations too.
EVID: routes/instance.py:36-38 role from _get_variant(). test_multi_instance.py:93-108 sets HALBERT_PERSONA_ID=home with no HALBERT_VARIANT and asserts role=='home' → FAILED (assert 'host' == 'home') in my run and in baseline scratchpad/pytest-main.txt:122. 7d01720e did not touch test_multi_instance.py (git show --stat → 0 hits).
DOC: REV-03-RESUBMISSION says 'Zero new failures introduced'; this test fails specifically because of the F8 change.

### F7 R3-F10b — REV-03 F10 (Wyoming agent): cross-loop stop is broken — Server.aclose() does not exist on Python 3.10
status=in_progress cat=bug prio=P2 conf=high act=True
REMAINING: Replace with self._server.close() (sync) followed by ensure_future(self._server.wait_closed(), loop=self._loop); add a two-loop stop test.
EVID: wyoming_agent.py:373-377 _close_safely → asyncio.ensure_future(self._server.aclose(), loop=self._loop). Python 3.10.9 venv: hasattr(Server,'aclose') → False. Repro: start on thread loop, stop() from another loop → loop exception handler receives AttributeError("'Server' object has no attribute 'aclose'") 'Exception in callback HalbertWyomingAgent._close_safely()'. The TCP server is never closed; _
DOC: REV-03-RESUBMISSION says F10 fixed for both stream and agent 'same pattern as FrigateMQTTSubscriber'; the agent half raises.

### F7 R9-F01 — REV-09 F1: Wyoming TCP server unauthenticated, enabled by default, bound to 0.0.0.0:10400
status=not_started cat=security prio=P0 conf=high act=True
REMAINING: Default WYOMING_ENABLED=0 or bind 127.0.0.1 unless a shared token is configured; require a token in transcript frames (reuse PeersConfig token); consider confirmation for MEDIUM on unknown voice turns.
EVID: wyoming_agent.py:37 DEFAULT_HOST='0.0.0.0', :50 enabled=True, :62 WYOMING_ENABLED default '1'; app.py:753-770 starts it whenever wyoming_cfg.enabled (not capability-gated: capabilities.py has no wyoming cap); _handle_client (:236-330) accepts any transcript with no token; turns run at speaker_role='unknown' (:180) whose RoleGate cap is MEDIUM without confirmation. HANDOFF-WRAP-UP-2026-08-31.md:54-

### F7 R9-F02 — REV-09 F2: Wyoming turns run on a second event loop; per-loop turn lock lets turns interleave on the shared state machine
status=not_started cat=bug prio=P1 conf=high act=True
REMAINING: Submit voice turns to the uvicorn loop via asyncio.run_coroutine_threadsafe (or make the Wyoming thread enqueue-only), or give the voice channel its own AgentStateMachine.
EVID: app.py:763-765 asyncio.new_event_loop() + run_forever in a daemon thread; wyoming_agent.py:231-232 uses the dashboard's get_agent() singleton; state_machine.py:341-345 builds a fresh asyncio.Lock per loop; grep run_coroutine_threadsafe in halbert_core → no hits.

### F7 R9-F03 — REV-09 F3: VAD frame-size mismatch (480 vs 512 samples) — is_speech always False; now LIVE, not latent
status=not_started cat=bug prio=P1 conf=high act=True
REMAINING: Slice 1024-byte frames (or accumulate to 512 samples), stop flush() per frame, keep one segment stream and map segment start/end to state transitions; add a frame-size regression test with a fake VAD that records chunk lengths.
EVID: audio/pipeline.py:334 frame_target=960 bytes (480 samples); audio/speech/vad.py:31 SILERO_WINDOW_SAMPLES=512, :164-166 returns False when n<512, :175 flush() per frame. Since d967cc8b the coordinator is bootstrapped at app.py:659-672 with a WebRtcIngress whenever CAP_AUDIO probes true, so the dead loop now runs in production. No test feeds real frame sizes (sherpa-onnx not installed in venv; test_

### F7 R9-F04 — REV-09 F4: enrolled voiceprints never loaded into the runtime matcher; /speakers/{id}/test always False
status=not_started cat=bug prio=P1 conf=high act=True
REMAINING: On SpeakerIdentifier init (or coordinator start) load SpeakerProfileStore.list_all() into the manager; have enroll/delete routes call identifier.enroll/remove; add a store→manager seam test.
EVID: routes/audio.py:195-208 enroll extracts an embedding and calls only SpeakerProfileStore.enroll (no SpeakerIdentifier.enroll / manager.add); :236 test route builds a fresh SpeakerIdentifier() with an empty manager → verify() hits `speaker_id not in self._manager` (speaker_id.py:243) → (False, 0.0); pipeline.py:265 SpeakerIdentifier() likewise never loads store.list_all(). grep 'list_all|embedding_a

### F7 R9-F05 — REV-09 F5: modality can never resolve VOICE in production — and now gates the O3 TTS egress
status=in_progress cat=bug prio=P1 conf=high act=True
REMAINING: Point _get_pipeline at app.state.audio_coordinator (or call set_audio_pipeline from app.py after bootstrap); call set_wyoming_active around Wyoming turns or pass a per-turn capability; thread ctx.speaker_role into SpeakerIdentity; add a non-monkeypatched test that a voice turn emits speech_segment.
EVID: channel_capability.py:150 imports dashboard.routes.audio.get_audio_pipeline — no such function exists (grep 'def get_audio_pipeline' → none; the coordinator lives on app.state.audio_coordinator, app.py:673) so _get_pipeline() is always None; set_wyoming_active/set_audio_pipeline have zero callers; app_seam.py:418 constructs HalbertChannelCapability() with defaults → has_speaker() False → should_sp
DOC: HANDOFF-VOICE-MODE-OPUS-RESULTS-2026-09-01.md:21 calls O3 'TTS egress end-to-end'; the production gate (should_speak) is never true.

### F7 R9-F06 — REV-09 F6: enrollment role overrides biometric confidence bands (latent until F4)
status=not_started cat=security prio=P2 conf=high act=True
REMAINING: Accept profile.role only when confidence meets that role's band threshold; PIN-challenge admin-band actions regardless.
EVID: voice_auth_gate.py:159 `role = profile.role or role` after classify_speaker_role(match.confidence) at :145; PIN challenge only for guest band (:147).

### F7 R9-F07 — REV-09 F7: barge-in cannot abort synthesis — full waveform generated before first chunk (partially mitigated per-segment)
status=in_progress cat=bug prio=P2 conf=high act=True
REMAINING: Synthesize sentence-by-sentence inside PiperTTS.synthesize with token checks between executor calls.
EVID: tts_engine.py:125 awaits the whole _generate() before the chunk loop checks cancel_token (:135); state_machine.py:3133-3137 (c818191c) checks the token between demuxed segments, so cancellation now saves later segments but not the one in flight.

### F7 R9-F08 — REV-09 F8: HIGH-risk confirmation from a voice turn is unreachable (user hears a non-sequitur)
status=not_started cat=bug prio=P2 conf=high act=True
REMAINING: Surface the confirmation text as the spoken response, key pending confirmation to conversation_id, route a 'confirm' transcript to it.
EVID: wyoming_agent.py:182-186 collects only response_chunk/response_complete; tool_confirmation_required (state_machine.py:2454) is ignored; each turn mints a new session (:151) so pending_confirmation is orphaned; fallback text at :123.

### F7 R9-F09 — REV-09 F9: sample rate now recorded; raw PCM still labelled format='wav' in SpeechResult
status=in_progress cat=bug prio=P3 conf=high act=True
REMAINING: Label SpeechResult.format='pcm_s16le' (or emit a WAV header).
EVID: tts_engine.py:130 sets self._sample_rate=sr (O3 side-fix, c841b35b) and voice_backend.py:144 reads it — rate half fixed; voice_backend.py:150 still format='wav' on headerless PCM. tts_egress.py:21 correctly advertises 's16le'.
DOC: REV-09 report's 'PiperTTS never sets _sample_rate' is now stale.

### F7 R9-F10 — REV-09 F10: Wyoming agent still speaks a non-canonical JSONL dialect
status=in_progress cat=bug prio=P2 conf=high act=True
REMAINING: Reuse read_wyoming_frame/write_wyoming_frame in the agent; emit spec events (handled/not-handled or synthesize) or document text-only.
EVID: wyoming_agent.py:250 bare readline() (no data_length/payload_length framing — see R3-F04), :276-280 emits a non-spec 'response' event; only the describe→info type was changed (:302). The canonical reader/writer exists unused at audio/ingress/wyoming_ingress.py:51-113.

### F7 R9-F11 — REV-09 F11: wake-word detection runs on the single VAD-trigger frame
status=not_started cat=bug prio=P2 conf=high act=True
REMAINING: Feed every frame to the stateful spotter and trigger on wake-word state with VAD as a gate.
EVID: pipeline.py:357-361 `wake_detected = self._wake_word.detect(frame)` on the 30 ms trigger frame only; masked today by the `wake_detected = True` fallback (:359) and by R9-F03.

### F7 R9-F12 — REV-09 F12: wyoming_agent and WyomingIngress both default to 0.0.0.0:10400 (latent)
status=not_started cat=bug prio=P3 conf=high act=True
REMAINING: Separate defaults (e.g. ingress 10401) or a startup port check.
EVID: wyoming_agent.py:38 DEFAULT_PORT=10400; audio/config.py:51-53 WyomingIngressConfig enabled=False, port=10400; pipeline.py:289-300 starts the ingress when enabled.

### F7 R9-F13 — REV-09 F13: blocking ONNX inference and per-sample loops on the event loop — now on uvicorn's loop
status=not_started cat=bug prio=P2 conf=high act=True
REMAINING: Wrap ASR/tagger calls in run_in_executor (tts_engine already does); bulk-copy in RingBuffer.write.
EVID: pipeline.py:393 self._asr.transcribe_chunk(pcm) and :478 self._audio_tagger.classify(pcm) called synchronously; buffer.py:78-81 per-sample write loop under asyncio.Lock. app.py:663-672 now starts the coordinator on the dashboard loop, so a 10 s decode stalls every SSE stream and WebSocket.

### F7 R9-F14 — REV-09 F14 (PLAUSIBLE): one malformed Wyoming header closes the satellite connection
status=not_started cat=bug prio=P3 conf=medium act=True
REMAINING: Distinguish bad-header from EOF and resynchronize (skip line, continue).
EVID: wyoming_ingress.py:66-70 returns None on JSONDecodeError; :177-179 treats None as clean EOF and breaks.

### F7 R9-F15 — REV-09 F15 (PLAUSIBLE): `speaker_id not in self._manager` may not be supported by sherpa-onnx
status=unknown cat=bug prio=P3 conf=low act=True
REMAINING: Verify on a machine with sherpa-onnx; fall back to manager.contains(name) if __contains__ is absent.
EVID: speaker_id.py:243; sherpa_onnx is not installed in the venv (ModuleNotFoundError) so __contains__ support cannot be verified here.

### F7 R9-P5 — REV-09 packet item 5: Rust AEC capture exists but has no Python consumer
status=in_progress cat=incomplete_feature prio=P2 conf=high act=True
REMAINING: Wire the 127.0.0.1:18400 loopback PCM socket into an ingress adapter; on-hardware verification on the founder's machine.
EVID: src-tauri/src/audio_capture.rs present (e10ea62f, feature-gated OFF); grep '18400|loopback' in halbert_core Python → no audio consumer (only capabilities.py/redaction.py unrelated hits). HANDOFF-WRAP-UP-2026-08-31.md:92-99 lists the consumer, HUD, and on-hardware verification as follow-ups.
DOC: REV-09 report says 'No audio_capture.rs exists' — stale since e10ea62f.

### F7 R3-TEST — Targeted test runs on main for this scope
status=done cat=test_gap prio=P2 conf=high act=True
REMAINING: Fix R3-F08 test; add tests for R3-F04/R3-F10b/R3-F02 gates (none exist: grep 0o600|seed_ha_config_from_being|call_soon_threadsafe|HAAuthError in tests → no HA hits).
EVID: arch -arm64 .venv/bin/python -m pytest test_home_assistant.py test_mcp_ha_tools.py test_ha_phase2.py test_ha_phase4.py test_ha_phase6.py test_frigate.py test_multi_instance.py test_ha_sourceprep_variants.py test_task07_voice_turn_plumbing.py → 167 passed, 1 failed (test_instance_info_home). pytest test_audio_buffer.py test_role_gate.py test_modality_voice_phase2.py test_audio_pipeline_speaker.py t

### F7 DOC-01 — MASTER-TODO.md still lists TASK-07 voice fixes as undone
status=not_started cat=doc_only prio=P3 conf=high act=True
REMAINING: Tick the TASK-07 items and update the U2 row (do not edit the dirty working tree from this audit).
EVID: MASTER-TODO.md (HEAD and dirty working-tree copy) lines 28, 85, 109-112, 118: 'all four fixes verified still undone', unchecked speaker_role / markdown stripper / session UUID / BargeInHandler / ThreadManager items. All landed: 58adce12, 149b3e75 (wyoming_agent.py:151,160-161,180,464-512), pipeline.py:592-650; REV-09 §3 and REV-03 §4 both verified them.
DOC: MASTER-TODO claims TASK-07 open; code and both review reports show it landed.

### F7 DOC-02 — REV-03-RESUBMISSION / HANDOFF-WRAP-UP overstate REV-03 completeness
status=not_started cat=doc_only prio=P3 conf=high act=True
REMAINING: Annotate the resubmission with the two broken fixes and the red test once they are addressed.
EVID: REV-03-RESUBMISSION-2026-08-31.md claims all 13 fixed with zero new failures; F4 is ineffective (R3-F04), F10's Wyoming half raises (R3-F10b), F3 payload is non-spec (R3-F03), and test_instance_info_home is red (R3-F08). HANDOFF-WRAP-UP-2026-08-31.md:47 'REV-03's were fixed separately (already on main)'.

### F7 RET-01 — Retire feat/rev03-sentient-home-fixes branch and worktree
status=done cat=retire prio=P3 conf=high act=True
REMAINING: Founder: git worktree remove + branch -d (not done by this read-only audit).
EVID: git log main..feat/rev03-sentient-home-fixes → empty; merge commit 9a292ce6 is an ancestor of main; worktree ~/.config/superpowers/worktrees/Halbert/rev03-sentient-home-fixes is clean.

### F8 FDR-01 — FDR-DEC-01: ratify DCO-with-relicensing-grant (vs full CLA) as the inbound licence
status=blocked cat=decision prio=P1 conf=high act=True
REMAINING: Founder chooses (a) DCO-only (accepting the exception covers only the founder's own copyright, per-contributor permission needed for third-party code in the App Store target) or (b) add a real CLA with an assent step. Then tick LEG-CRIT-02 and FOUNDER-TODO.md section 1. Must land before accepting external PRs.
EVID: documentation/contributing/CONTRIBUTING.md:289-322 already contains DCO 1.1 + 'Dual-Licensing & Commercial Permission Grant' + a section-7 clause; CI enforces sign-off (.github/workflows/dco.yml, scripts/check-dco.sh, both present). documentation/legal/LEGAL-AND-LICENSING-TODO.md:60-65 LEG-CRIT-02 still unchecked; its section 5.2(1) at :292-303 states a DCO sign-off is a certification not a licenc
DOC: TASK-PACKET-06 Task 6.1 instructs 'Add a mandatory DCO clause' as if missing; it is already committed. The drafts doc recommends DCO-only without surfacing the legal TODO 5.2(1) counter-argument that DCO-only leaves the grant non-binding.

### F8 FDR-02 — FDR-DEC-02: approve one section-7 App Store exception text, commit LICENSE-EXCEPTION-APPSTORE, choose SPDX WITH form
status=blocked cat=decision prio=P1 conf=high act=True
REMAINING: Founder picks the section 2.1 text (recommended) or the CONTRIBUTING.md:320 text, ideally after counsel review (strategy section 7(1)); commits LICENSE-EXCEPTION-APPSTORE; then AI work: replace CONTRIBUTING section 3 with a pointer, add pointers in LICENSE/README/LICENSE.md, extend add_spdx_headers.py + test_legal_metadata.py for the WITH form and run the tree-wide header rewrite on covered files only.
EVID: `ls /Volumes/4TB-BAD/Halbert/LICENSE-EXCEPTION-APPSTORE` -> No such file; loop over every local branch with `git cat-file -e <branch>:LICENSE-EXCEPTION-APPSTORE` found none. Two conflicting texts in-tree: documentation/legal/APP-STORE-DISTRIBUTION-STRATEGY.md section 2.1 (Mac-App-Store-only scope, third-party carve-out, fork-freedom clause) vs documentation/contributing/CONTRIBUTING.md:320 ('...or
DOC: REVIEW-PACKET-07 section 4 and MASTER-TODO.md:162 still quote the invalid 'WITH MacAppStore-Exception' identifier.

### F8 FDR-03 — FDR-DEC-03: lock bundle identifiers (three schemes + a fourth linux id) and per-channel entitlements
status=blocked cat=decision prio=P1 conf=high act=True
REMAINING: Founder confirms the scheme (drafts recommend home/pro/dashboard). Then AI work: platforms.yml diff, per-channel identifier injection in build-macos.sh (does NOT exist today, contrary to the drafts' 'verify the injection exists' hedge), create entitlements.mas.plist (app-sandbox, network.client, device.microphone, files.user-selected.read-write) and entitlements.mac.plist (Hardened Runtime), wire bundle.macOS.entitlements per channel.
EVID: halbert_core/halbert_core/dashboard/frontend/src-tauri/tauri.conf.json:5 "identifier": "ai.halbert.dashboard" (all targets), bundle.macOS.entitlements: null, signingIdentity: null, providerShortName: null. config/platforms.yml:216 ai.halbert.linux, :226 ai.halbert.macos.pro, :239 ai.halbert.macos.free. packaging/flatpak/ai.halbert.dashboard.yml app-id ai.halbert.dashboard. FOUNDER-TODO.md section 
DOC: TASK-PACKET-06 Task 6.3 and REVIEW-PACKET-07 section 3 cite src-tauri/tauri.conf.json at repo root (does not exist; erratum already noted). The drafts' three-way table omits config/platforms.yml:216 ai.halbert.linux, a fourth identifier.

### F8 FDR-04 — FDR-DEC-04: lock Halbert Pro pricing, update window, renewal, refund terms and device count; commit HALBERT-PRO-COMMERCIAL-TERMS.md (also closes LEG-MAJ-04 EULA)
status=blocked cat=decision prio=P2 conf=high act=True
REMAINING: Founder fills the three placeholders, reconciles the device count with TERMS.md:25, approves the Ed25519 offline-key architecture, and commits the doc. Nothing in code depends on it until Milestone 3 (activation modal, Sparkle) is built.
EVID: documentation/legal/HALBERT-PRO-COMMERCIAL-TERMS.md absent on main and on every local branch (git cat-file loop). Draft in FOUNDER-DECISION-DRAFTS-2026-08-31.md with three {FOUNDER: ...} placeholders (promo end date, renewal $12-15/yr, refund policy). documentation/legal/OPEN-CORE-AND-DISTRIBUTION-STRATEGY.md:110-113 says $24-$29 one-time, no subscription. documentation/legal/TERMS.md:24-25 alread
DOC: TASK-PACKET-06 says '$29 ($24 launch promo)'; the strategy doc says '$24-$29'; TERMS.md adds a 3-device limit the drafts omit.

### F8 FDR-05 — Copyright first-year: confirm 2024 (pre-repo Cerebric/LinuxBrain history) or change to 2025
status=blocked cat=decision prio=P3 conf=high act=True
REMAINING: One-word founder answer. If 2025: change COPYRIGHT in scripts/add_spdx_headers.py, halbert_core/__init__.py, tests/test_legal_metadata.py:21, tauri.conf.json bundle.copyright, then re-run the header script (mechanical AI work).
EVID: `git log --reverse --date=short` first commit b6a77dd7 2025-12-08. 731 py + 304 ts/tsx headers say 'Copyright (C) 2024-2026'; tests/test_legal_metadata.py:21 EXPECTED_COPYRIGHT hard-codes 2024-2026 and :133 asserts it in CLI output; scripts/add_spdx_headers.py COPYRIGHT; halbert_core/__init__.py __copyright__; tauri.conf.json bundle.copyright. LEGAL-AND-LICENSING-TODO.md:323-326 section 5.2(5) fla

### F8 FDR-06 — Confirm outbound licence id stays GPL-3.0-or-later (not GPL-3.0-only)
status=blocked cat=decision prio=P3 conf=high act=True
REMAINING: Founder confirmation only; if 'only' is chosen every statement plus 1,036 headers must change before external contributions land.
EVID: All manifests already say or-later: src-tauri/Cargo.toml:6, halbert_core/pyproject.toml:12, frontend package.json:5, packages/model-picker/package.json:6, packages/design-system/package.json:6, tauri.conf.json bundle.license, README.md:275, CONTRIBUTING.md:291. LEGAL-AND-LICENSING-TODO.md:320-322 section 5.2(4) asks the founder to confirm; drafts recommend keep.

### F8 FDR-07 — Confirm the App Store build stays a sandboxed remote companion (open-core boundary)
status=blocked cat=decision prio=P2 conf=high act=True
REMAINING: Founder states it explicitly (yes/no). A 'no' re-opens the licensing analysis, entitlements and product differentiation.
EVID: documentation/legal/APP-STORE-DISTRIBUTION-STRATEGY.md section 7(3): 'The whole open-core boundary rests on this.' config/platforms.yml:239-247 app_store: sandboxed true, category developer-tools, price free. FOUNDER-TODO.md Milestone 2 describes a menu-bar companion with Wyoming voice streaming. Not recorded as decided in any doc (FOUNDER-TODO section 1 lists only FDR-DEC-01..04).

### F8 FDR-08 — macos-private-api (transparent floating voice HUD): acceptable in the App Store target, or Pro-channel only?
status=blocked cat=decision prio=P2 conf=high act=True
REMAINING: Founder picks: (a) HUD ships Pro/direct only and the Cargo feature + macOSPrivateApi become per-channel build config (depends on FDR-03 per-channel build plumbing), (b) App Store build drops transparency, or (c) accept review risk. Then AI implements the gating.
EVID: tauri.conf.json:13 "macOSPrivateApi": true (app-wide, every target); src-tauri/Cargo.toml:35 tauri features include "macos-private-api"; src-tauri/src/floating_panel.rs:19-21 comment: 'App Store distribution restricts private API use, so App Store builds may need to drop the transparency instead'; .handoff/HANDOFF-WRAP-UP-2026-08-31.md:102 item 4 poses the decision; grep HALBERT_CHANNEL in src-tau

### F8 FDR-09 — Founder-only infrastructure: Apple Developer Program certs, Lemon Squeezy product + Ed25519 keypair, halbert-ha-addon Supervisor repository
status=not_started cat=deferred prio=P2 conf=high act=True
REMAINING: Accounts, certificates, merchant setup and the public add-on repo can only be created by the founder; the add-on itself is additionally blocked on the deferred Docker track (see HA-01).
EVID: FOUNDER-TODO.md section 2 FDR-INF-01/02/03 all unchecked. tauri.conf.json bundle.macOS signingIdentity: null, providerShortName: null. `find` for repository.yaml across the repo -> none; hacs.json + custom_components/halbert exist (a HACS integration, which the amended HA strategy doc notes is NOT an add-on channel). No Dockerfile or docker-compose anywhere (find -> none), so the add-on wrapper (R

### F8 U6-D2 — U6 D2 (4GB boundary): resolved option (b) by the AI session and merged; founder ratification requested
status=done cat=decision prio=P3 conf=high act=True
REMAINING: Founder ratifies (or reverses to '4GB = offload-only', which would re-touch hardware_detector.py:433, compute_router.py and test_hardware_profile_fallback.py). Update MASTER-TODO.md:137.
EVID: halbert_core/halbert_core/model/hardware_detector.py:34 '<4GB RAM', :433 `>= 4` -> ENTRY_8GB, :437 SBC_LOW_POWER, :455-462 offload-only budget. Commit 3ce98551 (W25 comment fix) merged via 4e4ff2f4 'Merge feat/ha-simplification into main'. .handoff/HANDOFF-HA-SIMPLIFICATION-CONTINUE-2026-08-30.md section 2.1 records the resolution; HANDOFF-WRAP-UP-2026-08-31.md section 4 lists 'D2/D4 ratification'
DOC: MASTER-TODO.md:137 still lists D2 as an open unchecked decision although the resolution is merged.

### F8 U6-D4 — U6 D4 (merge home-light into home): done and merged; founder ratification requested; residual dead strings
status=done cat=decision prio=P3 conf=high act=True
REMAINING: Founder ratifies. AI cleanup after: drop 'home-light' from llm_config.py:816 and the test docstring; fix MASTER-TODO.md:123,139.
EVID: Commit 8545af94 'feat(home): merge home-light into home (D4) + resolve Q3/Q4', merged via 4e4ff2f4 and 93c863c1. halbert_core/halbert_core/config/being_config.py:36 VALID_VARIANTS = {"sysadmin", "home"}; integrations/cognition_wiring.py:182 HA_VARIANTS = ("home",). Residual references: model/llm_config.py:816 still tests `in ("home", "home-light")` (dead string, harmless); tests/test_llm_config_en
DOC: MASTER-TODO.md:139 frames D4 as 'if home retires into home-light'; the merged code did the opposite (home-light retired into home). MASTER-TODO.md:123 still describes a home-light variant.

### F8 U6-Q34 — U6 Q3/Q4 resolutions (keep vision_model; keep advance_turn) rest on a contradictory haloysius-availability claim: founder should ratify
status=done cat=decision prio=P3 conf=medium act=True
REMAINING: Founder confirms whether haloysius is mandatory on HA nodes (which changes packaging for the [cognition] extra) or optional (which re-opens Q4's ImportError concern). The Frigate snapshot routing bug and deque(maxlen) queue bounding are AI-closable follow-ups outside this area.
EVID: Same commit 8545af94. .handoff/HANDOFF-HA-SIMPLIFICATION-CONTINUE-2026-08-30.md section 2.4 justifies keeping advance_turn with 'Haloysius is fundamental - every Halbert install includes it', while section 1 (W20) of the same doc states that on a home node installed per the deploy docs 'haloysius is absent (optional [cognition] extra, not on PyPI)'. Section 2.3 keeps vision_model and flags a separ
DOC: HANDOFF-HA-SIMPLIFICATION-CONTINUE section 1 vs section 2.4 contradict each other on haloysius presence.

### F8 HA-01 — HA strategy D1-D8 are 'Confirmed' but the roadmap still says build Rust/halbertd/MQTT now; the founder's Rust deferral is recorded nowhere, and feat/rust-native-core has 3 unmerged commits awaiting merge-or-park
status=blocked cat=deferred prio=P2 conf=high act=True
REMAINING: Founder decides: (1) record the deferral explicitly in MASTER-TODO and the scoping/plan docs (currently only D7 north-star items are marked deferred); (2) merge the R0/R1 scaffold as parked code or leave feat/rust-native-core unmerged; (3) whether the zero-Rust Docker track (R0.9/R0.10 Dockerfile + R6.1 sidecar compose + R6.3 add-on wrapper, which D4/D5 depend on) is carved out of the deferral or deferred with it.
EVID: .handoff/HA-STRATEGY-SCOPING-AND-DEPLOYMENT-PATHS-2026-08-31.md section 8 table: D1-D8 all Confirmed (working copy; file is uncommitted-modified by another session, `git status --porcelain` shows M). D8 corrections landed in 41ae15d0 (COMPETITIVE-ANALYSIS:18,139 '24,600+'; HALBERT-OS-DISTRO:91 'aspirational', :173 'Retain (stubbed)'; experimental/README.md:8 maturity tiers; SINGULAR-ENTITY:46-47 S
DOC: HA-STRATEGY section 9 and MASTER-TODO.md:168-189 present the Rust track as near-term/start-now; the founder's stated direction is that the full Rust rebuild is deferred.

### F8 SEM-01 — Terminology fork 1: 'Self' vs 'Identity' as the replacement for 'The Being' (the audit itself recommends both)
status=blocked cat=decision prio=P2 conf=high act=True
REMAINING: Founder picks one word. Phase 1 (docs/comments) and Phase 3 shims (identity.yml with being.yml fallback; /api/settings/identity alias) are AI work after the pick.
EVID: .handoff/HANDOFF-SEMANTIC-AUDIT-AND-TERMINOLOGY-REVIEW-2026-09-01.md Task 4(1). The source artifact ~/.gemini/antigravity/brain/.../semantic_audit.md row 38 recommends 'Self' for The Being while row 41 recommends 'Standardize on Identity' for the Persona/Being/Identity alias set: internally inconsistent. Rename targets all exist on main: documentation/design/the-being.md, dashboard/frontend/src/co

### F8 SEM-02 — Terminology fork 2: 'Compute Mesh' vs 'Mesh Computing' vs 'Continuity Grid' for the multi-machine peer layer (federation/)
status=blocked cat=decision prio=P2 conf=high act=True
REMAINING: Founder picks the noun and rules on whether the COMPETITIVE-ANALYSIS positioning phrase is exempt from the style rule.
EVID: Semantic handoff Task 4(2); semantic_audit.md:51 recommends 'Compute Mesh' (architecture) / 'Linked Devices' (UI). halbert_core/halbert_core/federation/ exists on main; dashboard components NodeFleetCockpit.tsx present; no 'Federat' string in user-facing .tsx (grep -> none), so the UI cost is low but the package rename (federation/ -> mesh/) is Phase 4 backend work. Also conflicts with the positio

### F8 SEM-03 — Terminology fork 3: singular-entity mode naming ('Unified Mode' vs 'One Halbert' vs 'Shared Presence'); current UI says 'Singular Entity' / 'Independent Node'
status=blocked cat=decision prio=P2 conf=high act=True
REMAINING: Founder picks the user-facing pair before feat/singular-entity-opus merges, so labels land once; API field values can stay as-is behind the label.
EVID: Semantic handoff Task 4(3); semantic_audit.md:55 recommends 'Unified Mode' vs 'Standalone Mode'. On main: EntityIdentityCard.tsx:182 'Singular Entity', :197 'Independent Node'; lib/peerApi.ts:370 entity_mode: 'singular' | 'independent'; routes/devices.py:196,222; cognition_wiring.py:148 is_singular_entity_mode(). feat/singular-entity-opus (7 unmerged commits) adds more 'singular entity' naming (be

### F8 VM-01 — Voice mode parked product call: is getUserMedia-denied a full machine 'error' for keyboard-only users?
status=blocked cat=decision prio=P3 conf=high act=True
REMAINING: Founder decides: degrade to a muted/keyboard posture on NotAllowedError, or keep the error state. Small AI change after.
EVID: On main (feat/voice-mode-visual-ui merged 18/0): hooks/useVoiceModeMachine.ts:17 and :166-172 route turn_complete -> listening; pages/VoiceMode.tsx:283-290 re-arms ensureUplink() whenever state is listening/recognized/interrupted and unmuted; lib/pcmCapture.ts:273 calls getUserMedia; PcmUplink onError -> dispatch({type:'error'}) at VoiceMode.tsx:262. .handoff/HANDOFF-VOICE-MODE-OPUS-RESULTS-2026-0

### F8 VM-02 — Voice mode parked product call: severity-2 acoustic wakes bypass quiet hours but are still suppressed by the 'quiet' proactivity dial and safe mode
status=blocked cat=decision prio=P3 conf=high act=True
REMAINING: Founder decides whether an acoustic life-safety wake must be unconditional (publish as critical) or may be dialled off. The doc-16/gate.py comment is AI work after.
EVID: halbert_core/halbert_core/proactive/gate.py:70-76 dial threshold (step 1) applies before the acoustic bypass; :84 bypass covers quiet hours only; :94-100 safe mode (step 3) suppresses non-critical; :138-148 docstring names the residual dial/safe-mode suppression. HANDOFF-VOICE-MODE-OPUS-RESULTS section 'Parked decisions' items 2-3 propose publishing severity-2 acoustic findings as severity 'critic

### F8 MKT-01 — Marketing website messaging decisions Q1-Q8 unanswered; no home/voice stops built on web-v7
status=blocked cat=decision prio=P3 conf=high act=True
REMAINING: Founder answers Q1-Q8; Q5 waits on FDR-04; Q1 should be decided together with SEM-03.
EVID: .handoff/HANDOFF-MARKETING-WEBSITE-UPDATE-2026-08-31.md section 4 table Q1-Q8 ('must be answered before the website AI begins build'). marketing/web-v7/src/content/stops.jsx contains none of the proposed transition copy (grep 'learned to hear|moved into the house|live in your home' -> none). Q1 recommendation (C, growth story) conflicts with HANDOFF-SINGULAR-ENTITY-MULTI-BODY-2026-08-31.md:385 whi

### F8 LEG-GATE — App Store dependency-licence gate currently FAILS (rc=1, 10 unclassified deps) - AI-closable exception in this area, but it hard-blocks the App Store build path the FDR decisions unblock
status=not_started cat=bug prio=P2 conf=high act=True
REMAINING: Classify the 10 dependencies in config/dependency-licenses.yml (verify each upstream licence; webrtc-audio-processing wraps a BSD-3 library but the Rust crate's own licence must be checked). Not a founder decision unless a copyleft one turns up.
EVID: `arch -arm64 .venv/bin/python scripts/check_appstore_deps.py --target macos-app-store --no-color` -> 'python: 25 permissive, 2 noted, 6 blocking; rust: 2 blocking; npm: 2 blocking', exit code 1. Unclassified: python opencv-python, sherpa-onnx, openwakeword, pyacoustid (+2); rust cpal, webrtc-audio-processing; npm @halbert/design-system, @halbert/model-picker. scripts/build-macos.sh:197 runs this g
DOC: LEGAL-AND-LICENSING-TODO.md:74 'Currently passing' is stale.

### F9 VMK-01 — feat/voice-mode-mark-v2 (25213235) is already on main via voice-mode-v2-backup -> 6f532ed2; branch adds nothing
status=obsolete cat=retire prio=P1 conf=high act=True [V:confirmed]
REMAINING: Delete branch feat/voice-mode-mark-v2 (`git branch -D`) and remove worktree ~/.config/superpowers/worktrees/Halbert/voice-mode-visual-ui (--force is safe, see VMK-02). Nothing to merge.
EVID: `git show 25213235 | git patch-id --stable` = 70a209a4ba6984164ba317b11bea5dcb169ad7fd; `git show 82543232 | git patch-id --stable` = same id. `git branch --contains 82543232` -> main, voice-mode-v2-backup. `git merge-tree --write-tree main feat/voice-mode-mark-v2` exit 0 -> tree 320cbc974215c514d6c329af51db84c5ebd0690c == `git rev-parse main^{tree}`; `git diff --stat main 320cbc97` empty. Merge 6
DOC: .handoff/HANDOFF-BRANCH-AND-WORKTREE-AUDIT-2026-09-01.md:20 says 'Neither branch is an ancestor of the other — pick one lineage'. Reality: voice-mode-v2-backup IS an ancestor of main (`git merge-base --is-ancestor voice-mode-v2-backup main` true) and its first commit is patch-identical to feat/voice
VERIFY: confirmed — Re-ran independently: `git show 25213235 | git patch-id --stable` -> 70a209a4ba6984164ba317b11bea5dcb169ad7fd; `git show 82543232 | git patch-id --stable` -> same 70a209a4…; `git branch --contains 82543232` -> `* main`, `+ voice-mode-v2-backup`. `git merge-tree --write-tree main feat/voice-mode-mark-v2` exit 0 -> 320cbc974215c514d6c329af51db84c5ebd0690c == `git rev-parse main^{tree}` (identical tr
  CORRECTED_REMAINING: Delete branch feat/voice-mode-mark-v2 with `git branch -D` (it is not a SHA-ancestor of main, so lowercase -d refuses) and `git worktree remove --force ~/.config/superpowers/worktrees/Halbert/voice-mode-visual-ui`. Nothing to merge. corrected_status=obsolete

### F9 VMK-02 — voice-mode-visual-ui worktree's 10 uncommitted files are a strict subset of main (main is ahead, not behind)
status=obsolete cat=retire prio=P1 conf=high act=True [V:confirmed]
REMAINING: None to salvage. Discard the worktree (`git worktree remove --force`); untracked wt_pytest.py is an untracked helper also present in 3 other worktrees and tracked on no branch.
EVID: `git -C <wt> diff --stat main -- packages/design-system` -> only voice/spectrum.ts (22 lines) and test/voiceSpectrum.test.ts (60 lines); the diff shows MAIN has `analyser?.disconnect()` in createNodeAnalyserSource.stop() (worktree lacks it; came from 5bee80c7 / 38e95899) and MAIN has the extra test 'createNodeAnalyserSource disconnects its analyser on stop (no accumulation)'. Docs: `git -C <wt> di
DOC: .handoff/HANDOFF-BRANCH-AND-WORKTREE-AUDIT-2026-09-01.md:19 says 'The fix is already sitting uncommitted in the same worktree ... 39/39 vitest' and :20 'Before committing that fix: reconcile against voice-mode-v2-backup'. Reality: the fix was committed on the backup lineage (5cd62840 etc.) and merge
VERIFY: confirmed — `git -C <wt> status --porcelain` -> 10 ' M' files (2 docs + 8 design-system) + `?? wt_pytest.py`; HEAD = 25213235 on feat/voice-mode-mark-v2. `git -C <wt> diff --stat main -- packages/design-system` -> ONLY src/test/voiceSpectrum.test.ts (-60) and src/voice/spectrum.ts (22 lines): the worktree's spectrum.ts LACKS main's `let analyser` + `analyser?.disconnect()` in createNodeAnalyserSource.stop() (
  CORRECTED_REMAINING: None to salvage. `git worktree remove --force` is safe. wt_pytest.py is untracked everywhere (`git ls-files | grep -c wt_pytest` = 0) and md5-identical (1e4ec209…) in all four worktrees that carry it. corrected_status=obsolete

### F9 VMK-03 — 25213235 merged alone would break the design-system build (removed TINE_COUNT/STATIC_TINE_PATHS still imported) — confirmed, but moot
status=obsolete cat=bug prio=P3 conf=high act=False
REMAINING: None — never merge the branch alone; delete it (VMK-01).
EVID: `git show 25213235:packages/design-system/src/voice/index.ts` lines 28,35 re-export TINE_COUNT and STATIC_TINE_PATHS; `git show 25213235:.../AudioReactiveHalbertMark.tsx:5` imports `{ STATIC_TINE_PATHS, TINE_AMPLITUDES, TINE_COUNT, tinePathD }`; `git show 25213235:.../geometry.ts | grep ^export` exposes only tineCount()/staticTinePaths()/laneCount() and Record-shaped TINE_AMPLITUDES. Superseded on

### F9 VMK-04 — voice-mode-v2-backup branch + voice-mode-reland worktree fully merged; retire
status=done cat=retire prio=P2 conf=high act=True [V:confirmed]
REMAINING: Remove the voice-mode-reland worktree and delete branch voice-mode-v2-backup (it was the reland vehicle; merged as 6f532ed2). Optionally commit one copy of wt_pytest.py somewhere canonical — it is currently untracked in every worktree.
EVID: `git merge-base --is-ancestor voice-mode-v2-backup main` -> true; `git rev-list --count voice-mode-v2-backup..main` = 14, main..backup = 0. `git diff --stat voice-mode-v2-backup main -- packages/design-system/src/voice src/test src/stories src/primitives` -> empty (identical). Worktree ~/.config/superpowers/worktrees/Halbert/voice-mode-reland: HEAD voice-mode-v2-backup, `status --porcelain` -> onl
VERIFY: confirmed — `git merge-base --is-ancestor voice-mode-v2-backup main` -> true; `git rev-list --count voice-mode-v2-backup..main` = 14, `main..voice-mode-v2-backup` = 0; branch tip 38e95899 = second parent of merge 6f532ed2. `git diff --stat voice-mode-v2-backup main -- packages/design-system` -> empty (design-system identical between the branch tip and main HEAD, i.e. every mark-v2 commit landed). Worktree ~/.
  CORRECTED_REMAINING: `git worktree remove ~/.config/superpowers/worktrees/Halbert/voice-mode-reland` (--force only needed because of the untracked wt_pytest.py) and `git branch -d voice-mode-v2-backup`. Optionally commit one canonical copy of wt_pytest.py (all four copies share md5 1e4ec209aa07868d844d807d21b966cc). corrected_status=done

### F9 VMK-05 — Prior audit's 'still needs unifying with feat/voice-mode-visual-ui Opus work' is stale — already merged
status=done cat=doc_only prio=P3 conf=high act=True [V:confirmed]
REMAINING: Strike lines 19-21 of .handoff/HANDOFF-BRANCH-AND-WORKTREE-AUDIT-2026-09-01.md (untracked doc) or replace with 'both mark lineages merged via 6f532ed2; branches retired'.
EVID: main HEAD 4a7bf71f 'merge: voice mode Opus P1/P2/P4 + review fixes'; feat/voice-mode-visual-ui is 18 behind / 0 ahead of main (task brief). main's documentation/design/16-voice-mode-visual-ui-implementation-plan.md carries the 'Build status: ALL PHASE-2 AND PHASE-3 [OPUS] TASKS COMPLETE' block (present on main, absent in the mark-v2 worktree).
DOC: .handoff/HANDOFF-BRANCH-AND-WORKTREE-AUDIT-2026-09-01.md:21 claims the mark work 'still needs unifying with feat/voice-mode-visual-ui's Opus-tier work before the overall Voice Mode feature is mergeable' — main already contains both (6f532ed2 then 4a7bf71f).
VERIFY: confirmed — `git rev-list --count main..feat/voice-mode-visual-ui` = 0, `feat/voice-mode-visual-ui..main` = 18; main HEAD 4a7bf71f 'merge: voice mode Opus P1/P2/P4 + review fixes'. Main's documentation/design/16-voice-mode-visual-ui-implementation-plan.md carries the Build-status block (shown as the '-' side of the worktree-vs-main diff). The earlier audit doc's mtime is 2026-09-01 13:55:00 — about six hours 
  CORRECTED_REMAINING: Rewrite lines 19-21 and the '35 new brand SVGs' clause of line 25 in .handoff/HANDOFF-BRANCH-AND-WORKTREE-AUDIT-2026-09-01.md: both mark lineages merged via 6f532ed2 (07:58 on 2026-09-01) and Opus work via 4a7bf71f; only branch/worktree retirement remains. Tracked docs on main that still mention fea corrected_status=done

### F9 VMK-06 — Main's uncommitted HalbertMark numeric density tiers + `lines` prop (design-system) — complete, green, ready to commit
status=done cat=needs_commit prio=P1 conf=high act=True [V:confirmed]
REMAINING: Fix the JSDoc dropped word (VMK-07), then commit the three design-system files as one commit. Decide separately what to do with the SVGs (VMK-09) and the stray dashboard copy (VMK-11) — do not sweep them into the same commit.
EVID: `git diff` on packages/design-system/src/primitives/HalbertMark.tsx (+PATHS_8/PATHS_7/PATHS_5, CONFIG_BY_LINE_COUNT, resolveLineCount(), `lines?: 3|4|5|6|7|8|10`, class `hb-mark--{n}lines` plus preserved alias classes hb-mark--display/medium/compact/small), stories/HalbertMark.stories.tsx (OpticalTiers rewritten as candidate matrix), test/primitives.test.tsx (+1 test 'supports explicit line counts
DOC: .handoff/HANDOFF-BRANCH-AND-WORKTREE-AUDIT-2026-09-01.md:25 '23/23 tests pass, tsc --noEmit clean — finished work' is ACCURATE for primitives.test.tsx (verified 23/23; package total 70/70).
VERIFY: confirmed — `git diff --stat -- packages/design-system` -> HalbertMark.tsx +164/-, stories +142/-36, primitives.test.tsx +11; 3 files, +277/-76. Diff content verified: `HalbertMarkDensity` widened to '10'|'8'|'7'|'6'|'5'|'4'|'3' + the four aliases; new PATHS_8/PATHS_7/PATHS_5 (PATHS_6/4/3 renamed from MEDIUM/COMPACT/SMALL, PATHS_10 from DISPLAY); `CONFIG_BY_LINE_COUNT` with stroke widths 26.67/34.29/40/48/60/
  CORRECTED_REMAINING: Fix the JSDoc word (VMK-07), optionally drop the dead `|| CONFIG_BY_LINE_COUNT[6]` guard at HalbertMark.tsx:202, then commit exactly these three design-system files. Do NOT `git add -A`: the untracked components/brand/HalbertMark.tsx (VMK-11) and the 35 SVGs (VMK-09) must stay out of this commit. corrected_status=done

### F9 VMK-07 — JSDoc dropped word in `lines` prop: 'Overrides  if provided.'
status=in_progress cat=cleanup prio=P3 conf=high act=True [V:adjusted]
REMAINING: Change to 'Overrides `density` if provided.' before committing VMK-06.
EVID: packages/design-system/src/primitives/HalbertMark.tsx (working copy) line 45: `   * Overrides  if provided.` — double space where the word `density` (probably backtick-quoted and lost) belongs. Same text duplicated into the untracked dashboard copy at halbert_core/halbert_core/dashboard/frontend/src/components/brand/HalbertMark.tsx (comment-stripped there).
VERIFY: adjusted — Confirmed the defect: `grep -n Overrides packages/design-system/src/primitives/HalbertMark.tsx` -> line 45 `   * Overrides  if provided.` (double space, missing `density`). The finder's secondary claim that the same text is duplicated into the untracked dashboard copy is wrong: `grep -n Overrides halbert_core/…/components/brand/HalbertMark.tsx` returns nothing — that file is comment-stripped and d
  CORRECTED_REMAINING: Change HalbertMark.tsx:45 to `Overrides \`density\` if provided.` before committing VMK-06. Nothing to fix in the dashboard copy (it has no JSDoc and is to be deleted). corrected_status=in_progress

### F9 VMK-08 — PATHS_3 second path uses 137.94 while every SVG (small/3lines/5lines/7lines) uses 137.88 — pre-existing 0.06-unit inconsistency
status=not_started cat=cleanup prio=P3 conf=high act=True [V:confirmed]
REMAINING: Optional: align PATHS_3 to 137.88 so the component and the exported SVG are byte-consistent. Visually irrelevant (0.06/1024).
EVID: HalbertMark.tsx:137 `'M 296.00 137.94 V 512.00 A 216.00 216.00 0 0 0 728.00 512.00 V 137.94'` (unchanged from the old PATHS_SMALL); assets/brand/halbert-mark-small.svg and halbert-mark-3lines.svg contain `296.00 137.88`; the new PATHS_5 in the same diff uses 137.88.
VERIFY: confirmed — HalbertMark.tsx PATHS_3 second path reads `M 296.00 137.94 V 512.00 A 216.00 216.00 0 0 0 728.00 512.00 V 137.94` (unchanged from the old PATHS_SMALL — it appears as context, not a changed line, in the diff). `grep -l 137.94 assets/brand/*.svg` -> no files; halbert-mark-small.svg, -3lines.svg, -5lines.svg, -7lines.svg and favicon.svg all use 137.88. Arithmetic: 512 − sqrt(432² − 216²) = 137.88 (py
  CORRECTED_REMAINING: Optional one-token fix: PATHS_3 137.94 -> 137.88 (both occurrences) so the component matches the shipped SVGs and favicon. Could ride along in the VMK-06 commit. corrected_status=not_started

### F9 VMK-09 — 35 untracked assets/brand/halbert-mark-{N}lines*.svg: 20 duplicate tracked tier files, 15 new (5/7/8 lines), unreferenced, no generator, README not updated
status=in_progress cat=decision prio=P2 conf=high act=True [V:confirmed]
REMAINING: Founder/design decision: (a) commit only the 15 new 5/7/8-line files (recommended) and drop the 20 duplicates, or (b) rename the tracked set to the numeric scheme in one deliberate move. Either way add the missing `-charcoal` variant for 5/7/8 (or amend README:31) and add 5/7/8 rows to README's tier table. Do not commit as-is: it leaves two parallel naming schemes for the same four files.
EVID: `git status --porcelain -- assets/brand | grep ^??` = 35, all mtime 2026-09-01 08:42. cmp: 10lines/6lines/4lines/3lines `.svg` and `-vermilion.svg` are byte-IDENTICAL to display/medium/compact/small; their -badge/-charcoal-on-canvas/-vermilion-on-canvas differ ONLY by `<rect ... />` vs `<rect .../>` whitespace (diff output). Only 5lines/7lines/8lines x 5 variants (15 files) are new geometry. No `-
VERIFY: confirmed — `git status --porcelain -- assets/brand | grep -c '^??'` = 35 (10/8/7/6/5/4/3 lines × 5 variants: plain, -vermilion, -badge, -charcoal-on-canvas, -vermilion-on-canvas). Tracked set is display/medium/compact/small × 6 variants (includes -charcoal). cmp results: 10lines/6lines/4lines/3lines `.svg` and `-vermilion.svg` are byte-IDENTICAL to display/medium/compact/small (8 files); the 12 -badge/-charc
  CORRECTED_REMAINING: Decide: (a) commit only the 15 new 5/7/8-line files and delete the 20 duplicates, or (b) migrate the tracked set to the numeric naming in one deliberate rename. Either way add `-charcoal.svg` for 5/7/8 (or amend README:31) and add rows for 5/7/8 to README's tier table. Do not commit all 35 as-is. corrected_status=in_progress

### F9 VMK-10 — Design decision pending: 7-line 'Proposed Primary' and 4-line 'Proposed Micro' candidates (story only; code/README defaults unchanged)
status=not_started cat=decision prio=P2 conf=high act=True [V:adjusted]
REMAINING: Founder views the OpticalTiers story and decides whether 7/4 replace 10/6/3 as the primary/micro marks. If yes: change `auto` thresholds, regenerate favicon + tracked tier SVGs, update README and the three density="medium" call sites; if no: keep the story as a reference matrix and close the item. Record the decision in a handoff.
EVID: packages/design-system/src/stories/HalbertMark.stories.tsx (working copy) OpticalTiers: LINE_COUNTS entries `{ count: 7, ... candidate: 'Proposed Primary' }`, `{ count: 4, ... candidate: 'Proposed Small' }`, cards titled '7 Lines (Candidate)' / '4 Lines (Candidate)'. resolveLineCount() `auto` still maps to 3/6/10; assets/brand/README.md and favicon.svg still use the 3-line small tier; no handoff/M
VERIFY: adjusted — Confirmed the story markers in the working-copy diff: LINE_COUNTS entries `{ count: 7, … candidate: 'Proposed Primary' }`, `{ count: 4, … candidate: 'Proposed Small' }`, `{ count: 8, … candidate: '8-line alternative' }`, and cards '7 Lines (Candidate)' / '8 Lines (Candidate)' / '4 Lines (Candidate)' with a 'Proposed Micro' badge. `auto` still maps to 3/6/10; favicon.svg still uses the 3-line geome
  CORRECTED_REMAINING: Founder reviews the OpticalTiers story and decides on 7/4 vs 10/6/3. If yes: change `auto` thresholds, regenerate favicon + tracked SVGs, update README and the three density="medium" call sites, AND add a third VoiceDensity (lane count 6, pitch 72, stroke 40) with drift/amplitude/frequency/vocal-ban corrected_status=not_started

### F9 VMK-11 — Stray untracked dashboard copy components/brand/HalbertMark.tsx — unreferenced, hardcoded hex colours; delete
status=not_started cat=cleanup prio=P2 conf=high act=True [V:confirmed]
REMAINING: Delete the file (or `rm -r` the untracked components/brand dir). It duplicates a design-system primitive and violates the canonical-tokens rule (never hardcode a colour).
EVID: Untracked `halbert_core/halbert_core/dashboard/frontend/src/components/brand/HalbertMark.tsx` (217 lines, mtime 2026-09-01 08:41). grep for 'components/brand' or './brand' importers in dashboard src -> none. Dashboard already imports the real one: components/Layout.tsx:40 `import { HalbertMark, NavRail ... } from '@halbert/design-system'`. Comment-stripped diff vs the design-system file: no `cx`/n
VERIFY: confirmed — `git status --porcelain` -> `?? halbert_core/halbert_core/dashboard/frontend/src/components/brand/`; file is 217 lines, mtime Sep 1 08:41. Hex literals at lines 159 (`color ?? '#D34E24'`), 166, 169 (`'#1A1918'`), 172/178 (`'#F7F5F0'`), 179; comment-stripped diff vs the design-system file also shows `size = 20` default, no `cx` import, and no `var(--color-…)` tokens. grep for any import of `compone
  CORRECTED_REMAINING: Delete the untracked directory halbert_core/halbert_core/dashboard/frontend/src/components/brand/ (rm -r). Unreferenced duplicate of a design-system primitive with hardcoded colours, violating the canonical-tokens rule. corrected_status=not_started

### F9 VMK-12 — Test gap for the new HalbertMark resolution logic (precedence, string-size auto fallback, invalid `lines`, string densities)
status=not_started cat=test_gap prio=P3 conf=high act=True [V:adjusted]
REMAINING: Add 4-5 assertions to the HalbertMark describe block (precedence, string density, string-size fallback, default stroke-width per tier).
EVID: packages/design-system/src/test/primitives.test.tsx:238-248 (new test) only asserts class names for lines={7|4|8}. Untested paths in HalbertMark.tsx resolveLineCount(): `lines` overriding an explicit `density`; `density='5'|'10'|'8'` string forms; `auto` with size='3rem' (returns 6); out-of-table `lines` value falling back to 6; strokeWidth defaults 34.29/40/60 for the new tiers.
VERIFY: adjusted — Confirmed: the only new test is primitives.test.tsx:238-248, asserting `hb-mark--7lines` / `--4lines` / `--8lines` classes for `lines={7|4|8}`; existing tests at :210-228 cover the `auto` mapping and alias classes. Genuinely untested: `lines` taking precedence over an explicit `density`; string densities '5'/'7'/'8'/'10'; `auto` with a string size (-> 6); and the new default stroke widths 34.29/40
  CORRECTED_REMAINING: Add 3-4 assertions to the HalbertMark describe block: `lines={7} density="display"` -> 7lines class; `density="8"` -> 8lines class and stroke-width 34.29; `size="3rem"` (string) with auto -> 6lines; `lines={5}` -> stroke-width 60. Skip the 'invalid lines' case (unreachable in TS) and consider removi corrected_status=not_started

### F10 VM-04 — O3 TTS egress: hub + /api/audio/tts WS + state-machine Piper streaming + TtsPlaybackClient
status=done cat=test_gap prio=P1 conf=high act=True
REMAINING: Never verified with real audio: the hook is silent unless the Haloysius seam exposes a voice backend AND a Piper model + sherpa-onnx are present (state_machine.py:3033-3036 'the egress hook then stays silent'). No integration test drives a real PiperTTS; P5 matrix rows 4.1/4.3/4.4 (TTS↔visualizer sync, AEC, barge-in) are unfilled.
EVID: routes/tts_egress.py; routes/websocket.py:162 tts_egress_endpoint; agents/state_machine.py:2999 call, :3026 _voice_tts_for_egress (via haloysius.seam get_app_seam().get_voice_backend().get_tts()), :3046 _speak_to_tts_egress with barge-in (:3122 pipeline.create_barge_in_token) and wake-before-speak (:3107-3111 display_power.wake); frontend src/lib/ttsPlayback.ts + ttsPlayback.test.ts (20 its); Voic

### F10 VM-06 — O5 acoustic anomaly → findings → SSE → timeline + voice wake chain
status=done cat=merge_ready prio=P3 conf=high act=True
REMAINING: Parked product decision (results handoff): severity-2 acoustic wakes bypass quiet HOURS only — a 'quiet' proactivity dial or safe mode still suppresses them (gate.py note added in 88413a42). Suggested long-term fix: publish severity-2 acoustic findings as severity 'critical'. P5 row 6.x (smoke-alarm detection on device) unfilled.
EVID: proactive/acoustic_bridge.py attached at app.py:698-702; hooks/useBeingEvents.ts:31 'acoustic' union; AcousticAnomalyModule rendered in components/agent/ProactiveEventsBadge.tsx; hooks/voiceModeEvents.ts acoustic_wake seam consumed by useVoiceModeMachine.ts:23-26; gate.py severity>=2 life-safety + 88413a42 doc note. test_acoustic_bridge.py 11 tests pass. Commits 98a434f9, 2033ad79.

### F10 VM-STT — Spoken input never reaches the agent: ASR transcript observation channel not wired (on_voice_turn unset; VoiceMode submits nothing on end-of-speech)
status=not_started cat=incomplete_feature prio=P0 conf=high act=True
REMAINING: Wire coordinator.on_voice_turn in app.py to deliver VoiceTurnObservation.text to the browser session (SSE/WS or a status-style channel keyed by session) and call submitTurn(transcript) in VoiceMode.tsx; add a backend test (observation → channel) and a frontend test (transcript → sendMessage). Until then Voice Mode is 'keyboard mode with a reactive mark'.
EVID: `grep -rn on_voice_turn halbert_core/` hits only audio/pipeline.py (:103 declared None, :443/:528 invoked if set); dashboard/app.py:654-722 bootstrap sets on_acoustic_event via attach_acoustic_bridge but never on_voice_turn; pipeline.get_status() deliberately excludes transcript text (pipeline.py:556-557). VoiceMode.tsx:32-35 'v1 input reality: the STT observation channel is not live' and :333-338
DOC: Doc 16 §5 banner and the results handoff say 'ALL PHASE-2 AND PHASE-3 [OPUS] TASKS COMPLETE'; true for the task list as written, but the plan's own O7 text defers STT and no task owns it — the headline voice-in feature has no owner.

### F10 VM-11 — P1 StandbyController multi-tier standby (30s dim+clock / 10min blackout / restore)
status=done cat=merge_ready prio=P3 conf=high act=True
REMAINING: Parked product call (results handoff): turn_complete → listening re-opens the mic; on a deployment without pre-granted permission, getUserMedia denial lands the machine in 'error' for keyboard-only users.
EVID: components/voice/StandbyController.tsx:66-68 TIER1_IDLE_MS=30_000 / TIER2_IDLE_MS=600_000, :76 DISPLAY_REPORT_PATH, :148 visibilitychange wake, :190-203 POST {idle_seconds}; StandbyController.test.tsx 18 its pass; mounted VoiceMode.tsx:472. Commits 08a6691b, 81495230.

### F10 VM-13 — P3 [GLM] kiosk packaging: runbook + systemd --user unit
status=done cat=merge_ready prio=P3 conf=medium act=True
REMAINING: Minor: the unit orders `After=graphical-session.target halbert.service` but no `halbert.service` exists in the repo (units shipped are halbert-dashboard/halbert-api/halbert-host/halbert-home) — harmless ordering-only reference, but pick the real backend unit name. Never installed on a device.
EVID: documentation/operations/kiosk-appliance.md (Chromium kiosk, WebKitGTK caveat :90-105, udev backlight fix :127-139); scripts/halbert-kiosk.service (xset s off / -dpms preamble, chromium --kiosk --app=http://localhost:${HALBERT_PORT}/voice ... --autoplay-policy=no-user-gesture-required). Commit 2293a160 + 88413a42.

### F10 VM-15 — P5 [GLM] hardware validation matrix — checklist exists, zero results recorded
status=not_started cat=test_gap prio=P1 conf=high act=True
REMAINING: Run the matrix on the N150 + 10" touch panel (60fps, wake latency, 44px hit areas, TTS↔mark sync/clap test, AEC, barge-in, 24h soak, smoke-alarm detection) and record results. Blocked on the founder's hardware; also blocked functionally on VM-STT for any row that involves speaking to the device.
EVID: .handoff/HARDWARE-VALIDATION-MATRIX-2026-08-31.md: 'Status: Pending hardware testing'; all 21 Result cells and the Sign-off row are empty. Its Notes section still says P2/O3/O5 are 'not yet built'.
DOC: Matrix Notes claim P2, O3, O5 are unbuilt — all three are on main.

### F10 VM-18 — G3 [GLM] AudioSettings quiet-hours UI + dead privacy switches — one dead switch remains (AEC)
status=in_progress cat=cleanup prio=P3 conf=high act=True
REMAINING: Wire the AEC switch to POST /api/audio/config local_mic.aec_enabled, or remove/disable it with a tooltip (the browser path uses getUserMedia echoCancellation, so this switch only matters for the Rust/local-mic path).
EVID: components/audio/AudioSettings.tsx:73-77 loads quiet_hours from /api/being, :108-111 POST {quiet_hours}, :412-442 enable + start/end inputs; delete_raw_audio/ignore_tv_babble no-ops are gone. BUT :207-216 'Acoustic Echo Cancellation (AEC)' Switch still has `onCheckedChange={() => {}}` (config.local_mic.aec_enabled, audio/config.py:44).

### F10 VM-20 — Retire feat/voice-mode-mark-v2 + worktree voice-mode-visual-ui (unmerged commit is content-identical to main; dirty files are identical or older than main)
status=obsolete cat=retire prio=P2 conf=high act=True
REMAINING: Nothing to salvage. Founder: discard the worktree's dirty changes, remove worktree ~/.config/superpowers/worktrees/Halbert/voice-mode-visual-ui, delete branch feat/voice-mode-mark-v2.
EVID: `git log main..feat/voice-mode-mark-v2` → 25213235 (geometry.ts + voiceGeometry.test.ts only); `diff -q` of the worktree's committed geometry.ts and voiceGeometry.test.ts against main → identical (main got the same content via 82543232/5cd62840 in merge 6f532ed2); `git merge-tree --write-tree main feat/voice-mode-mark-v2` exit 0. Worktree dirty files (10 M): springs.ts, AudioReactiveHalbertMark.ts

### F10 VM-21 — Retire merged voice branches/worktrees: feat/voice-mode-visual-ui (.claude/worktrees/voice-mode-opus), voice-mode-v2-backup (voice-mode-reland), feat/modality-voice-phase2
status=obsolete cat=retire prio=P2 conf=high act=True
REMAINING: Remove the three worktrees and delete the three branches; keep wt_pytest.py only if the founder wants the meta-path-stripping wrapper checked in somewhere (it is untracked in three worktrees).
EVID: `git branch --merged main` lists feat/modality-voice-phase2, feat/voice-mode-visual-ui, voice-mode-v2-backup. Worktree HEADs: voice-mode-opus @88413a42 (=main^), voice-mode-reland @38e95899 (in main), modality-voice-phase2 @3d4b5a1b (clean, merged). Only untracked wt_pytest.py helper in the first two.

### F10 VM-22 — Python consumer of the Rust AEC loopback socket (127.0.0.1:18400) — never built; decide if still needed
status=not_started cat=decision prio=P2 conf=high act=True
REMAINING: Decision: doc 16 Decision 1 makes the BROWSER the audio terminal (getUserMedia AEC + WS uplink), which Voice Mode now uses end-to-end, so the Rust cpal/AEC3 capture is only a desktop-Tauri hedge (kept per P4). Either (a) build a small TCP→AudioChunk ingress adapter (mirrors WebRtcIngress) for the desktop shell, or (b) mark audio_capture.rs dormant and drop the follow-up. Also open: MASTER-TODO line 113 still lists 'Rust AEC implementation' unchecked though audio_capture.rs exists.
EVID: `grep -rn 18400` → only src-tauri/src/audio_capture.rs:36 DEFAULT_AUDIO_PORT and handoff docs; no .py file references 18400/loopback PCM. Cargo.toml:18-22 features voice-capture/aec default OFF. HANDOFF-WRAP-UP-2026-08-31.md §3 item 1 lists it as a follow-up ('wire it into integrations/voice_backend.py / the audio pipeline so mic capture replaces the dead VAD path').

### F10 VM-23 — Wake word ('Hey Halbert') — deferred by design; no model, no dependency installed
status=not_started cat=deferred prio=P3 conf=high act=False
REMAINING: Train/export an openWakeWord model and place it at the documented path; no code change needed (WakeWordSpotter is lazily wired at pipeline.py:255). Not required to call Voice Mode v1 complete.
EVID: audio/speech/wake_word.py:15-19 expects ~/.local/share/halbert/audio/models/hey_halbert.ww.tflite — directory does not exist on this machine; openwakeword not importable in .venv; pyproject.toml:107-109 optional extra 'Requires a trained "Hey Halbert" model'. Doc 16 §8 risk 2: v1 wake is tap/PTT/acoustic-anomaly only.

### F10 VM-24 — H2/H3 voice wiring handoff — Phase 3/4 live in other repos; Halbert Phase 2.5 items 3-5 (TemporalOrchestrator refactor) not done and arguably superseded
status=in_progress cat=decision prio=P3 conf=medium act=True
REMAINING: Decide whether the 'remove ProactiveGate.should_notify / move scheduling to TemporalOrchestrator' refactor is still wanted; O5 chose to extend ProactiveGate instead, so the handoff's items 3-5 should be either re-scoped or closed as superseded. H2/H3 work is not a Halbert deliverable.
EVID: .handoff/HANDOFF-PHASE3-4-...-VOICE-WIRING.md §3/§4 target /Volumes/4TB-BAD/HumanAI/LinuxBrain and /Volumes/4TB-BAD/H3 (out of this repo). §2 Halbert Phase 2.5 table: item 1 done (prompts/agent_prompts.py:690-701 modality-conditional formatting), item 2 done (persona/personality_prompt.py:47,103 VOICE PRESENTATION skipped for voice turns), item 6 done (modality_wiring.py 39-term lexicon); items 3-

### F10 VM-25 — MASTER-TODO voice entries are stale (claims 'confirmed undone' work that is on main; no entry for Voice Mode visual UI at all)
status=done cat=doc_only prio=P3 conf=high act=True
REMAINING: Update MASTER-TODO: check off the done U2 items, correct line 28, and add a Voice Mode section pointing at doc 16 with the open items (VM-STT, VM-15, VM-18, VM-22, parked decisions).
EVID: HEAD:.handoff/MASTER-TODO.md:28 'wyoming speaker_role+session_id fixes, text_preprocessor.py, BargeInHandler wiring, <speech> defanging all confirmed undone' vs integrations/wyoming_agent.py:151 uuid per-turn session_id, :141 speaker_role="unknown", :118-174 conversation_id threading, :464 _strip_markdown_for_speech; modality_wiring.py:347 defang_user_input; pipeline.py:593-597 BargeInHandler + st
DOC: MASTER-TODO line 28 and lines 110-120 describe as undone work that has been merged since 2026-08-31.

### F10 VM-26 — Results handoff / plan banner minor SHA and status drift
status=done cat=doc_only prio=P3 conf=medium act=True
REMAINING: One-line corrections in .handoff/HANDOFF-VOICE-MODE-OPUS-RESULTS-2026-09-01.md and doc 16 §5 banner; also update the HARDWARE-VALIDATION-MATRIX Notes (see VM-15).
EVID: Doc 16 §5 banner and results handoff list P2 as `07d53549`+`48868145`; `git log` on main shows the P2 polish as f2b6c68c (48868145 exists as a commit object but is not the sha main's first-parent history shows). Results handoff §caveats item 1 says P4 unreviewed (see VM-14).

### F10 VM-27 — End-to-end voice loop has no automated or manual verification (mic→VAD→ASR→agent→TTS→mark)
status=not_started cat=test_gap prio=P1 conf=high act=True
REMAINING: Minimum to call the feature 'tested': (1) install the sherpa-onnx extra + a Piper voice on one machine, enable audio_config.yml, open /voice in Chromium, confirm TTS audio + mark sync on a keyboard turn; (2) after VM-STT, confirm a spoken turn round-trips; (3) run the P5 matrix on the appliance. Consider one opt-in integration test gated on sherpa_onnx availability.
EVID: All 185 backend tests use stub coordinators/fake TTS (test_tts_egress.py:486-802 monkeypatch a fake tts); frontend tests stub AudioContext/getUserMedia; sherpa_onnx not importable in .venv; AudioConfig.enabled default False; no Playwright/e2e for /voice. Nothing exercises a real Piper voice or real ASR.

### F10 VM-28 — macos-private-api / App Store channel decision for the transparent HUD (founder-gated)
status=blocked cat=decision prio=P3 conf=high act=True
REMAINING: Founder decides whether the transparent NSPanel HUD ships in the App Store target (private API is disallowed there) or only in a direct/Pro channel.
EVID: src-tauri/tauri.conf.json:13 "macOSPrivateApi": true; Cargo.toml:35 tauri features include "macos-private-api"; HANDOFF-WRAP-UP-2026-08-31.md §3 item 4 and §4 'Founder-gated'.

### F11 SEO-01 — All 7 branch commits already on main (7/13 files byte-identical, 6/13 strict supersets on main)
status=obsolete cat=retire prio=P1 conf=high act=True [V:adjusted]
REMAINING: 
EVID: `git diff main feat/singular-entity-opus -- <file>` is EMPTY for: agents/peer_conversation_store.py, federation/__init__.py, tests/federation/test_capability_routing.py, tests/federation/test_compute_router_route.py, tests/federation/test_hardware_profile_fallback.py, tests/test_peer_conversation_store.py, tests/test_shared_threads.py. Non-empty diffs (main -> branch) are net deletions only: app.p
VERIFY: adjusted — VERDICT (obsolete/retire) HOLDS; evidence needed corrections. Re-ran per-file diffs myself: `git diff --numstat main feat/singular-entity-opus -- <file>` is EMPTY for exactly the 7 files the finder named (peer_conversation_store.py, federation/__init__.py, test_capability_routing.py, test_compute_router_route.py, test_hardware_profile_fallback.py, test_peer_conversation_store.py, test_shared_threa
  CORRECTED_REMAINING: None. Do NOT merge: merge-tree conflicts in 3 files and every branch-side hunk is superseded code. Nothing to salvage. corrected_status=obsolete

### F11 SEO-04 — Branch-unique content is all inferior earlier variants — nothing to salvage
status=obsolete cat=retire prio=P2 conf=high act=False
REMAINING: 
EVID: Branch-only lines from `git diff main feat/singular-entity-opus`: (a) compute_router.py `self._probe_lock = None  # asyncio.Lock, created lazily` + lazy `if self._probe_lock is None` — main has `asyncio.Lock()  # created eagerly to avoid race` (27fcfb95 remediation); (b) peers_config.py set_wol sets `peer.wol_enabled = enabled` BEFORE the MAC check and only warns — main rejects with return False a

### F11 SEO-05 — Delete branch feat/singular-entity-opus and worktree opus-singular-tasks
status=not_started cat=cleanup prio=P2 conf=high act=True [V:confirmed]
REMAINING: `git worktree remove ~/.config/superpowers/worktrees/Halbert/opus-singular-tasks` then `git branch -D feat/singular-entity-opus` (must be -D: git cherry reports all commits as unmerged so `-d` will refuse). Optionally `git tag archive/singular-entity-opus 132f2019` first if an archive is wanted — nothing on it is needed.
EVID: Worktree /Users/ericbintner/.config/superpowers/worktrees/Halbert/opus-singular-tasks: HEAD 132f2019 on feat/singular-entity-opus, `git status --porcelain` empty, no wt_pytest.py. `git branch -r --list '*singular-entity-opus*'` empty and for-each-ref shows no upstream — branch was never pushed (local-only; also true of feat/singular-entity at 91332aa5, which IS fully merged, 59/0). Stashes stash@{
VERIFY: confirmed — Re-checked: `git -C ~/.config/superpowers/worktrees/Halbert/opus-singular-tasks rev-parse --abbrev-ref HEAD` = feat/singular-entity-opus at 132f2019; `status --porcelain` empty; no wt_pytest.py in the worktree; `git worktree list` shows the entry. `git branch -r --list '*singular*'` is empty and `for-each-ref` shows no upstream for either feat/singular-entity-opus or feat/singular-entity — both lo

### F11 SEO-06 — ComputeRouter (P4b cloud-primary chain, P4c marker, P6b WoL tier) is never instantiated by production code on main
status=in_progress cat=incomplete_feature prio=P1 conf=high act=True [V:adjusted]
REMAINING: Decide whether ComputeRouter is meant to replace/wrap TierRouter for the singular-entity compute chain, then wire it into the agent turn path (app_seam / state machine) so cloud->peer->local->WoL->template ordering and the degraded marker actually govern real turns; add an integration test that exercises a turn through the router. Also the plan doc's 'CAP_LOCAL_LLM has no consumer yet (natural home: ComputeRouter's local tier)' depends on this.
EVID: `git grep -n -E 'ComputeRouter\(|\.route\(' main -- 'halbert_core/halbert_core/**'` (excluding tier_router/APIRouter matches) returns NOTHING. `git grep 'ComputeRouter|compute_router' main -- halbert_core/halbert_core/**` outside compute_router.py hits only docstrings/README/__init__ lazy export (federation/__init__.py:61,91-93; federation/README.md:12,49,126; compute_broker.py:187; connectivity.p
DOC: .handoff/IMPL-PLAN-SINGULAR-ENTITY-TASKS-2026-08-31.md:6 says 'COMPLETE — all Fable/Opus/GLM tasks implemented and green' and rows P4b/P4c/P6b cite commits, but nothing calls ComputeRouter; the doc's open-items list (lines 43-49) does not mention this.
VERIFY: adjusted — CORE CLAIM CONFIRMED: `git grep -n -E 'ComputeRouter\(' main -- 'halbert_core/halbert_core/**'` returns nothing (9 hits only under halbert_core/tests); `\.route\(` excluding APIRouter/tier_router = nothing; every non-test mention of ComputeRouter outside compute_router.py is a docstring/README/lazy `__init__` export (federation/__init__.py:61,91-93; peers.py:324; compute_broker.py:187; connectivit
  CORRECTED_REMAINING: Decide the relationship first: either wrap TierRouter as ComputeRouter's cloud/local tiers and construct ComputeRouter(cloud_enabled=..., peers_config=...) in app_seam/HalbertModelBackend, or fold the WoL-wake and template/degraded tiers into TierRouter's existing fallback chain. Then add an integra corrected_status=not_started

### F11 SEO-07 — P4c '[no thinking power]' degraded marker never reaches a user-visible response
status=in_progress cat=incomplete_feature prio=P2 conf=high act=True [V:confirmed]
REMAINING: Once ComputeRouter is wired (SEO-06), call apply_degraded_marker on template/heuristic/deferred results before the text is emitted to the chat/voice surfaces; add a route-level test asserting the marker appears in the response body.
EVID: `git grep -n -E 'apply_degraded_marker|is_degraded_response|degraded_marker\('` on main outside federation/compute_router.py and tests returns nothing; only callers are tests/federation/test_degraded_marker.py and test_compute_fallback.py:149-160. Root cause is SEO-06 (no ComputeRouter consumer).
DOC: Plan doc row 'P4c/G7 degraded marker | 28df5910 | "[no thinking power]" marker' reads as shipped end-to-end; it is library-only.
VERIFY: confirmed — Re-ran: `git grep -n -E 'DEGRADED_MARKER_PREFIX|degraded_marker|apply_degraded_marker|is_degraded_response' main -- 'halbert_core/**'` hits only federation/compute_router.py (:121-138, :191-193, :548) and tests (tests/federation/test_degraded_marker.py, test_compute_fallback.py:149-160). The literal string 'no thinking power' appears on main only in compute_router.py, those two tests, and handoff 

### F11 SEO-08 — Plan doc open items (self-declared 'future work, none blocking')
status=not_started cat=deferred prio=P3 conf=medium act=False [V:adjusted]
REMAINING: Triage: the begin_turn atomic get-or-open and capability re-probe are small backend tasks; the frontend capabilities endpoint and ManualPairingForm gap are UI work; test_cognition_tick_once needs an isolation fix.
EVID: .handoff/IMPL-PLAN-SINGULAR-ENTITY-TASKS-2026-08-31.md (main) lines 43-49 list: server-side atomic get-or-open for the cross-node begin_turn race (P3d); CAP_LOCAL_LLM has no consumer; no capability re-probe path in a running process; frontend capabilities endpoint; ManualPairingForm TODO(federation-9.1) gap (excluded from G12 by review); test_cognition_tick_once order-sensitive (fails solo, passes
VERIFY: adjusted — I verified each sub-item against code, and one is misdiagnosed. CONFIRMED OPEN: (a) begin_turn atomic get-or-open — tests/test_shared_threads.py:210-225 documents the check-then-create race as 'out of scope for P3d'; no get_or_open/atomic path in agents/peer_conversation_store.py or routes/conversations.py. (b) CAP_LOCAL_LLM has no consumer — capabilities.py:56,68,85,98,231 + tests/test_capabiliti
  CORRECTED_REMAINING: Split this item. READY NOW (bug, not deferred): hoist `response_modality = "text"` above `if self.prompts:` in agents/state_machine.py (~line 2743) per REV-06 F2; re-run test_cognition_tick_once.py, test_state_machine*.py, test_agent_integration.py, test_agent_chat_off_the_event_loop.py — expect ~27 corrected_status=in_progress

### F12 R05-F1 — peer:// chat turns break the production streaming path (no peer branch in _stream_turn)
status=not_started cat=bug prio=P1 conf=high act=True
REMAINING: In LLMClientAdapter.stream()/_stream_turn detect turn.provider == 'peer' and either delegate to chat() via asyncio.to_thread and yield one buffered chunk, or add a peer wire (OpenAI-shaped, http:// rewrite of peer://, bearer from api_key_for) once the workstation has an SSE path. Add a test that streams a TurnModel(provider='peer') and asserts no NonHttpUrlClientError. Coordinate with R10-F2/F3: end-to-end chat on a home node needs all three.
EVID: dashboard/routes/agent.py:1065-1110 dispatches only `provider in OPENAI_COMPATIBLE_PROVIDERS` / `== "anthropic"` / else-Ollama (`url = f"{endpoint}/api/chat"`, agent.py:1112); grep 'peer' in agent.py returns nothing; model/client.py:68 OPENAI_COMPATIBLE_PROVIDERS excludes peer while :75-76 CHAT_CAPABLE_PROVIDERS includes it; agents/state_machine.py:2778 `if hasattr(self.llm, 'stream')` prefers str
DOC: HANDOFF-WRAP-UP-2026-08-31.md:78-81 lists it as open ('coordinate'); MASTER-TODO.md has no entry.

### F12 R05-F2 — Apple Intelligence auto-provision/wizard assign chat slot to a bridge that is not running
status=in_progress cat=bug prio=P1 conf=high act=True
REMAINING: Gate slot assignment (not endpoint registration) on hardware.apple_intelligence_bridge_running in auto_provision_apple_intelligence and in the wizard's ai_takes_chat; never override an explicitly chosen local model; surface 'eligible, bridge not started' in Settings. Fix together with R05-N1 since both touch the same gate.
EVID: model/auto_provision.py:69 gates only on hardware.apple_intelligence_available; the string bridge_running does not occur in auto_provision.py; model/config_wizard.py:491 `ai_takes_chat = ai_available and mem and mem <= 24` and :504-506 override a user-chosen Ollama model; hardware_detector.py:297-315 computes apple_intelligence_bridge_running but nobody reads it except the wizard status line (conf
DOC: test_auto_provision.py::_hw defaults bridge_running=False and expects provisioning to succeed, i.e. the tests pin the defective behaviour.

### F12 R05-N1 — NEW regression (merge 15560fdb): secure_model capability gate is circular — fresh-install Apple Intelligence provisioning is dead and 4 tests fail in isolation
status=not_started cat=bug prio=P1 conf=high act=True
REMAINING: Decide what CAP_SECURE_MODEL means: if it is 'this variant may have a secure slot', drop the slot-state probe (use the preset/override only) or add a separate probe; if it is 'a secure model is configured', the provisioning/wizard paths must not gate on it. Then pin the 4 tests with capability_registry.set_capability('secure_model', True) or the corrected semantics. Re-run test_auto_provision.py and test_config_wizard_variants.py in isolation.
EVID: capabilities.py:192-204 _probe_secure_model() returns True only when resolve('secure_model') already yields a local URL; auto_provision.py:72-83 and routes/llm.py:219 and config_wizard.py:492-499 (`secure_allowed = _has_secure_cap`) all gate on that capability. Empirical (HALBERT_CONFIG_DIR=scratch, empty secure slot, variant sysadmin): CapabilityRegistry().probe() -> secure_model False; auto_prov
DOC: Merge 15560fdb message: 'backend failure set byte-identical to the pre-branch environmental baseline (zero regressions)' — true only for full-suite ordering; isolated runs regress.

### F12 R05-F3 — GET /api/llm/config (and /effective) return every provider api_key in plaintext
status=not_started cat=security prio=P1 conf=high act=True
REMAINING: Redact api_key in both blocks (empty string or key_set:true); _carry_forward_api_keys (llm_config.py:694-717) already makes round-trips safe. Add a test asserting the key never appears in GET responses.
EVID: routes/llm.py:148-176 _effective_block/_editor_payload return layered.effective and layered.global_config verbatim; llm_config.py:378 normalise keeps api_key; no 'redact'/'key_set' in llm_config.py or llm.py. Empirical: saved endpoint with api_key 'sk-SECRET-LEAK-TEST-123' -> get_llm_config() body contains it 2x (llm_config + effective blocks), get_effective_llm_config() 1x.

### F12 R05-F4 — Images never translated for OpenAI-compatible or Anthropic wires (vision only works on Ollama-family)
status=not_started cat=bug prio=P2 conf=high act=True
REMAINING: Translate `images` per wire in the payload builders (OpenAI image_url content parts; Anthropic image blocks) on both call_llm_chat and _stream_turn; until then restrict the vision slot to Ollama-family in the picker or log loudly when images are dropped.
EVID: client.py:555-557 _call_openai_compatible sends `messages` verbatim (Ollama-shaped `images` key); client.py:585-607 _anthropic_payload never reads images; agent.py:1067-1073 and :1084-1100 streaming branches identical; grep image_url in halbert_core/halbert_core -> only mcp/camera_gate.py:70 (a field-name list).

### F12 R05-F5 — GPU advisory lock not taken on the streaming path; exclusive lock contradicts 'shared' comment
status=not_started cat=bug prio=P2 conf=high act=True
REMAINING: Decide: take the lock (LOCK_SH or short hold around model load) in _stream_turn for local-GPU providers, or drop the 30s blocking wait; fix the comment either way.
EVID: client.py:339 lock wraps only call_llm_chat; grep llm_advisory_lock in routes/agent.py -> no match (_stream_turn builds its own aiohttp request, agent.py:1062-1160); client.py:154 comment 'shared lock, so multiple readers are OK' vs :166 fcntl.LOCK_EX; :97 _LOCK_TIMEOUT_S = 30.

### F12 R05-F6 — call_llm_chat(stream=True) calls response.json() on an SSE/NDJSON body (latent)
status=not_started cat=bug prio=P3 conf=high act=True
REMAINING: Raise NotImplementedError for stream=True in call_llm_chat (all providers) or implement body iteration.
EVID: client.py:557 `"stream": stream` then :575 response.json(); _call_ollama :757 same; only _call_peer (:503-510) fails loudly.

### F12 R05-F7 — TierRouter caches models.yml for process life; refresh() only reacts to session change
status=not_started cat=bug prio=P3 conf=high act=True
REMAINING: Extend refresh() to reload when llm_config.global_config_path() mtime/size changed.
EVID: model/tier_router.py:335-345 refresh() compares only self._active_session(); no mtime/global_config_path() check in tier_router.py (grep).

### F12 R05-F8 — is_model_loaded family-prefix match returns false positives
status=not_started cat=bug prio=P3 conf=high act=True
REMAINING: Compare exact family: loaded_name.split(':')[0] == model_name.split(':')[0].
EVID: client.py:1494 `if model_name.startswith(loaded_name.split(":")[0]): return True` unchanged.

### F12 R05-F9 — Windows O_EXCL lock steals a live holder's lock after 300s
status=not_started cat=bug prio=P3 conf=high act=False
REMAINING: Heartbeat the lockfile mtime or write pid + liveness check. Windows is not a first-class target; defer.
EVID: client.py:129-143 unchanged (age > 300 -> unlink).

### F12 R05-P1 — llm_config.update() lost-update race across processes (PLAUSIBLE)
status=not_started cat=bug prio=P3 conf=medium act=False
REMAINING: Optimistic concurrency on file identity in save(), or a file lock. Low priority unless multi-process deployments are common.
EVID: llm_config.py:720-739 update() reads uncached then save() (:669-682) re-reads raw and writes the earlier merge; no file-stamp compare.

### F12 R05-P2 — HALBERT_MODEL override silently disabled on any cognition_wiring import error (PLAUSIBLE)
status=not_started cat=bug prio=P3 conf=high act=True
REMAINING: Log the exception at warning level before returning None.
EVID: llm_config.py:813-819 `except Exception: return None` with no log line.

### F12 R05-P3 — Token estimate (4 chars/token) undersizes num_ctx for CJK prompts (PLAUSIBLE)
status=not_started cat=bug prio=P3 conf=medium act=False
REMAINING: Script-aware estimate or a tokenizer probe; degradation, not silence.
EVID: client.py:1227-1247 and :1283-1285 use `// 4`; loud warning still fires (agent.py:1150-1156).

### F12 R05-P4 — AMD VRAM never parsed (rocm-smi branch returns None)
status=not_started cat=bug prio=P3 conf=high act=False
REMAINING: Parse rocm-smi --showmeminfo vram output. Acknowledged in code.
EVID: hardware_detector.py:366-381 'This is a simplified version' -> return None.

### F12 R10-F1 — Pairing is self-service token issuance: PIN returned to requester, verify issues bearer with no confirmation/expiry/rate-limit
status=not_started cat=security prio=P1 conf=high act=True
REMAINING: Make the PIN out-of-band (show on workstation UI only, via the existing WS manager), gate /verify on a desktop-side approval state, add 60s PIN expiry + attempt counter, require local-origin (or admin) for /pair, and pin the flow with tests. Wire PeerPairingModal's manual flow. Do this before or together with R10-F2 (once the endpoint is mounted this becomes the live risk).
EVID: routes/peers.py:159-197 request_pairing has no auth dependency and returns PairResponse(pin=pin) (:197); :200-251 verify_pairing pops the PIN and returns raw_token; _pending_pairings (:76) stores no created_at/attempts despite the comment; TODO(federation-9.1) at :195-196 is the only 'desktop confirmation'. Empirical (TestClient, scratch peers.json): POST /api/peers/pair {node_id:'attacker'} -> 20
DOC: peers.py:18-44 docstring and PeerPairingModal.tsx:4-10 describe a 'user confirms' step that does not exist in code; HANDOFF-WRAP-UP-2026-08-31.md:60-65 lists it open.

### F12 R10-F2 — Workstation never serves the compute contract: compute_endpoint.router unmounted, broker/_submit_to_broker are stubs
status=not_started cat=incomplete_feature prio=P1 conf=high act=True
REMAINING: federation-9.3: mount compute_endpoint.router in app.py, implement ComputeBroker.start/submit/_worker_loop and _submit_to_broker (direct local Ollama/vLLM call for 1:1), populate /api/compute/v1/models (never apple-foundation, never secure_model), and add a mounted-route test like test_compute_probe.py::TestRouteIsMounted. Until then ComputePeerCard should refuse to save a link or label the feature as not serving.
EVID: dashboard/app.py:272-308 mounts routes.compute (capacity probe) but never federation.compute_endpoint.router (grep compute_endpoint outside its own file -> docstrings only); federation/compute_endpoint.py:184 TODO, :237 models route TODO, :265 `_submit_to_broker` raises NotImplementedError; compute_broker.py:166/202/218 start/submit/_worker_loop raise. Empirical TestClient on create_app(): POST /a
DOC: compute_router.py:348-351 docstring says PeerProvider HTTP methods are TODO(9.3) — they are implemented (peer.py:203-300); it is the workstation side that is missing.

### F12 R10-F3 — Three components disagree on the peer health route; /api/compute/v1/health exists nowhere
status=not_started cat=bug prio=P1 conf=high act=True
REMAINING: Add GET /api/compute/v1/health (auth'd, no GPU cost) to compute_endpoint.py or align all three on the models route; encode as one shared constant; add a non-monkeypatched test against the mounted app.
EVID: federation/compute_router.py:626 probes /api/compute/v1/health; model/config_wizard.py:437 same; model/providers/peer.py:106,378 probes /api/compute/v1/models; grep 'v1/health' in halbert_core/halbert_core -> only those callers and docstrings, no route. Empirical: GET /api/compute/v1/health -> 404 on create_app(). tests/federation/test_compute_router_route.py monkeypatches the probe so unit tests 

### F12 R10-F4 — Deferred queue unbounded and never drained; split-brain/replay policy unimplemented (latent: ComputeRouter not wired)
status=not_started cat=incomplete_feature prio=P2 conf=high act=True
REMAINING: Bound the queue (ring + dropped counter), persist deferrals, implement replay_deferred with the §11.3 conflict policy and un-skip the 6 split-brain tests — before wiring ComputeRouter.route() into the agent loop.
EVID: compute_router.py:304 `self._deferred_queue: list = []  # TODO(federation-9.6)`; :522-530 appends full messages on every deferred template fallback; :673-683 replay_deferred raises NotImplementedError; tests/federation/test_split_brain.py:25-56 six tests @skip. grep 'ComputeRouter(' in halbert_core/halbert_core -> no production instantiation; integrations/cognition_wiring.py has no reference. Merg

### F12 R10-F5 — Any authenticated peer can revoke any other peer — and the new /devices alias needs no auth at all
status=not_started cat=security prio=P1 conf=high act=True
REMAINING: Restrict revoke/forget to local-admin (loopback origin or a dashboard auth mechanism) or self-revocation only; apply the same to the being.yml-writing device routes. Depends on the dashboard-wide 'no auth' posture flagged in HANDOFF-WRAP-UP item 1.
EVID: routes/peers.py:284-306 DELETE /api/peers/{node_id} depends only on require_peer_auth (TODO at :294-298 unchanged). New in 15560fdb: routes/devices.py:418-439 DELETE /devices/{node_id} (+ ?forget=true -> delete_peer) has no dependency; PUT /devices/entity-mode (:221), /devices/body-name (:270), /devices/peer-token (:387) likewise. Empirical: after pairing 'attacker' via R10-F1, DELETE /devices/att

### F12 R10-F6 — C1 'one token, one validation path' not implemented: MCP uses its own static bearer
status=not_started cat=incomplete_feature prio=P2 conf=high act=True
REMAINING: Route MCP _check_auth through PeersConfig.verify_token (per-node identity, revocation) or correct the C1 docstrings to describe two surfaces.
EVID: mcp/server.py:1136 `_bearer_token: str = ""`, :1147-1162 _check_auth compares against it; grep PeersConfig/peers_config under halbert_core/mcp -> none; federation/peer_middleware.py:22 and routes/peers.py:7-11 still claim one token/one revocation path. feat/security-review-01's server.py delta (c5b6bb91) is a config-path allowlist only, no auth change.

### F12 R10-F7 — Two persona systems with two sources of truth; per-persona memory isolation absent
status=not_started cat=cleanup prio=P2 conf=medium act=True
REMAINING: Retire PersonaManager routes (/switch, /status) or route them through PersonaStore; implement or explicitly de-scope memory_{persona_id}.db before advertising isolation.
EVID: routes/persona.py:102-148 POST /switch drives PersonaManager (persona_state.json); :230-251 POST /{id}/activate drives PersonaStore (being.yml symlink); frontend BeingTab.tsx:92 calls only /activate, so /switch and GET /status are a dead/parallel surface. Per-persona memory db not re-verified in depth (report's claim carried at medium confidence).

### F12 R10-F8 — PersonaStore fixed-name temp symlink is racy across processes (PLAUSIBLE)
status=not_started cat=bug prio=P3 conf=high act=True
REMAINING: Unique staging name per call (pid + uuid); one-line fix.
EVID: persona/store.py:150-160 tmp_link = being_yml.with_name('.being.yml.tmp-link') then os.replace.

### F12 R10-F9 — PeersConfig has no cross-process coherence and persists on every authenticated request (PLAUSIBLE)
status=not_started cat=bug prio=P3 conf=high act=True
REMAINING: Throttle last_seen writes, re-read/mtime-check before save, snapshot-iterate in verify_token, use a distinct temp name.
EVID: peers_config.py:253-260 _save rewrites whole file to `with_suffix('.tmp')` (peers.tmp) with no mtime check; :342 verify_token iterates self._peers.values() directly; :511-523 update_last_seen calls _save() every time (TODO at :522); peer_middleware.py:166-168 calls it per request.

### F12 R10-F10 — Fleet routes raise NotImplementedError (500) instead of 404; entire Fleet Cockpit is stubs
status=not_started cat=incomplete_feature prio=P3 conf=high act=True
REMAINING: Have get_fleet_proxy return None until 9.9 lands (routes already 404 on None), or unmount fleet.router (app.py:307) until then.
EVID: routes/fleet.py:138 calls get_fleet_proxy before the None check; federation/fleet_proxy.py:177 get_fleet_proxy raises NotImplementedError('TODO(federation-9.4)'); fleet_proxy.py:115/124/134/143 and telemetry_agent.py:181-227 all raise. Empirical: GET /api/fleet/x/info on create_app() raised NotImplementedError through TestClient (500 in production).

### F12 R10-F11 — mDNS beacon/listener raise when zeroconf IS installed; advertised compute_backends empty; parse_txt_record unguarded int()
status=not_started cat=incomplete_feature prio=P3 conf=high act=True
REMAINING: Log-and-return like the ImportError path until 9.7; populate compute_backends from Ollama/vLLM probes; wrap api_port parse; label the discovery list as unavailable in the UI.
EVID: federation/peer_discovery.py:191 and :250 raise NotImplementedError after the lazy import succeeds; :288 `compute_backends: List[str] = []` with TODO(9.7); :137 `int(txt.get('api_port','8000'))` unguarded; routes/peers.py:414-428 GET /api/peers/discovered hardcoded [] (empirical 200 []).

### F12 R10-MIN — Minor notes from the report all still present (PersonaManager non-atomic save, discovered [] stub)
status=not_started cat=cleanup prio=P3 conf=high act=True
REMAINING: Atomic write in _save_state; UI label for the empty discovery list.
EVID: persona/manager.py:115-126 json.dump with no temp+rename; routes/peers.py:426-428 return [].

### F12 R10-N1 — NEW (merge 15560fdb): devices router mounted at /devices/* but frontend and tests use /api/devices/* — Settings -> Devices page is non-functional
status=not_started cat=bug prio=P1 conf=high act=True
REMAINING: Mount with prefix='/api' (or prefix the decorators like peers.py); add a mounted-route test against create_app() (pattern: test_compute_probe.py::TestRouteIsMounted); re-run DevicesTab against a real backend. One-line fix plus one test.
EVID: dashboard/app.py:306 `app.include_router(devices.router, tags=["devices"])` with no prefix (identical on feat/singular-entity-opus b6bf6371 app.py:306); routes/devices.py:203-418 paths are /devices, /devices/entity-mode, /devices/{node_id}...; frontend lib/peerApi.ts:388-455 fetches `${API_BASE}/api/devices...` with API_BASE=''; tests/test_device_routes.py:14-15 builds its own FastAPI() with inclu
DOC: Merge 15560fdb message and IMPL-PLAN-SINGULAR-ENTITY-TASKS-2026-08-31.md record P7a/P7c as complete and verified (frontend 469 passed) — frontend tests mock fetch; backend tests mount their own prefix.

### F12 R05-10-TEST — Test gaps that let every finding above survive
status=not_started cat=test_gap prio=P2 conf=high act=True
REMAINING: Add: peer streaming test; pairing-flow tests (PIN not in body once fixed, expiry, attempts); mounted-route tests for compute_endpoint and devices against create_app(); un-skip split-brain once replay exists; capability_registry in the auto-provision tests.
EVID: No test streams a provider='peer' TurnModel (grep 'peer://' in tests -> compute_probe, sbc_offload_only, federation/* only; none touch _stream_turn); no test references /api/peers/pair, verify_pairing or _pending_pairings; test_compute_router_route.py monkeypatches the health probe; test_device_routes.py mounts its own prefix; test_split_brain.py skips 6/8; TestAutoProvisionAppleIntelligence ignor

### F12 R05-10-BRANCH — No unmerged branch carries remediation for REV-05/REV-10; u6 and opus worktrees are superseded by main
status=obsolete cat=retire prio=P3 conf=high act=False
REMAINING: Branch disposition belongs to the worktree-audit agent; from this scope's view nothing on those branches needs merging for REV-05/REV-10.
EVID: git log main..worktree-u6-home-simplification (16 commits) has main equivalents (main log: 0514a5c3, 5f87520c, 6f46f09a, 5e2ce6b4, d733ec9a, 226555ef, 6a077653 'U6 S1-S6'); its compute_endpoint.py delta is docstring-only and its agent.py delta has no peer/stream lines. git diff feat/singular-entity-opus main on devices.py/compute_router.py/peers_config.py shows main +150 lines over the branch (sup

### F12 R05-10-DOC — Tracking gap: MASTER-TODO.md has no remediation entries for REV-05/REV-10; only HANDOFF-WRAP-UP lists them and defers ownership
status=not_started cat=doc_only prio=P2 conf=high act=True
REMAINING: Add the R05/R10 items above (plus R05-N1, R10-N1) to MASTER-TODO with an owner; record that 15560fdb closed none of the review findings.
EVID: .handoff/MASTER-TODO.md:56,61,64-68 list only the review packets and the 2026-08-30 addendum; grep for _stream_turn/bridge_running/compute_endpoint/pairing in MASTER-TODO -> none (the dirty working-tree diff of MASTER-TODO adds nothing on REV-05/10 either). HANDOFF-WRAP-UP-2026-08-31.md:60-65,78-81,127 lists REV-10 F1 and REV-05 F1/F2 as open and says 'may have an owning session — check for a newe
DOC: REVIEW-RESULTS-REV-10 §1 'the peer provider is registered in the model stack' is true; its statement that ComputeRouter is 'unwired (no production instantiation)' is still true after the merge despite the merge message's 'corrected compute fallback chain'.

### F13 U2-01 — TASK-07 7.1a: Wyoming passes speaker_role="unknown" (not admin) through process() -> StateContext -> RoleGate
status=done cat=doc_only prio=P3 conf=high act=True
REMAINING: Only the MASTER-TODO checkbox. Note REV-09 F1: unknown still gets MEDIUM-risk tools without confirmation (see U2-17).
EVID: halbert_core/halbert_core/integrations/wyoming_agent.py:176-180 speaker_role="unknown"; commit 58adce12 on main; tests test_task07_voice_turn_plumbing.py::TestProcessSpeakerRolePlumbing + TestWyomingTurnPlumbing pass (78 passed run 2026-09-01)
DOC: MASTER-TODO.md:109 still '[ ]' — done.

### F13 U2-02 — TASK-07 7.1b: per-turn session UUID (no more wyoming-{pid} collision)
status=done cat=doc_only prio=P3 conf=high act=True
REMAINING: MASTER-TODO checkbox only.
EVID: wyoming_agent.py:151 turn_session_id = f"wyoming-{uuid.uuid4().hex[:12]}"; test_modality_voice_phase2.py::TestWyomingSessionId passes
DOC: MASTER-TODO.md:111 still '[ ]' — done.

### F13 U2-03 — TASK-07 7.1c + MASTER-TODO: conversation_id threaded as thread_id and ThreadManager injected into Wyoming turns
status=done cat=doc_only prio=P3 conf=high act=True
REMAINING: MASTER-TODO checkbox only. Injection is via get_thread_manager() inside the turn rather than constructor injection — equivalent for the doc-14 Gap 3 intent.
EVID: wyoming_agent.py:159-175 get_thread_manager() + thread_id=conversation_id or None, thread_manager=thread_manager; commit 149b3e75 on main; test_task07_voice_turn_plumbing.py passes
DOC: MASTER-TODO.md:118 still '[ ]' — done.

### F13 U2-04 — TASK-07 7.2: strip_markdown_for_speech utility — exists but not where/how the packet specified
status=in_progress cat=incomplete_feature prio=P2 conf=high act=True
REMAINING: (1) Apply stripping to the Wyoming satellite reply path (see U2-05). (2) Decide whether tts_engine.synthesize should strip defensively (today the local path relies on the engine demuxer's get_speech_text; state_machine.py:2920-2935). (3) Fallback stripper does not strip HTML/XML tags or convert bullets to pauses as the packet asked. (4) Packet-named tests test_text_preprocessor.py / test_wyoming_agent.py do not exist — coverage lives elsewhere.
EVID: No halbert_core/halbert_core/audio/speech/text_preprocessor.py (find/grep). Function is _strip_markdown_for_speech at wyoming_agent.py:464-512 (delegates to haloysius.modality.demuxer.strip_markdown, regex fallback). Wired ONLY into proactive_speak (wyoming_agent.py:425). tts_engine.py has zero strip/markdown references (grep). 9 tests in test_modality_voice_phase2.py::TestWyomingMarkdownStripping
DOC: MASTER-TODO.md:110 '[ ]'; REV-09 results §3 says 'RESOLVED' but only the proactive path is covered; packet names test files that were never created.

### F13 U2-05 — BUG: Wyoming satellite replies send raw markdown to HA TTS (main voice-turn path unstripped)
status=not_started cat=bug prio=P1 conf=high act=True
REMAINING: Call _strip_markdown_for_speech (+ apply_pronunciation) on the joined reply in _process_agent_turn before returning to HA; add a test asserting a markdown response comes back plain.
EVID: wyoming_agent.py:182-196 collects response_chunk events and returns ''.join(response_chunks).strip() with no _strip_markdown_for_speech call; response_modality is never 'voice' in production (U2-16) so the model is not even asked for plain text. Only proactive_speak (line 425) strips.

### F13 U2-06 — TASK-07 7.3a: BargeInHandler wired into AudioPipelineCoordinator
status=done cat=doc_only prio=P3 conf=high act=True
REMAINING: Code-level wiring complete. Functionally dead until U2-14 (VAD never fires) and U2-23 (generation not cancellable) are fixed; pipeline.speak() playback body is still 'pass' (pipeline.py:686-691).
EVID: audio/pipeline.py:115-119 (state), 371-376 (VAD-in-SPEAKING -> trigger_barge_in), 589-651 (_get_barge_in_handler/create_barge_in_token/trigger_barge_in), 655-695 speak(); test_modality_voice_phase2.py::TestPipelineBargeIn passes; coordinator now constructed in production at dashboard/app.py:663
DOC: MASTER-TODO.md:112 still '[ ]' — wired. REV-09 §3 item 4 'zero production instantiation sites' is now stale (app.py:663 since O2).

### F13 U2-07 — TASK-07 7.3b: defang <speech>/</speech> tags in untrusted inputs in agent_prompts.py
status=not_started cat=security prio=P2 conf=high act=True
REMAINING: Extend _CONTINUITY_TAG_RE (or add a sibling) to cover <speech>, <text>, <modality_context> in _defang_continuity so tool stdout/history rows and the no-engine path are covered; add a TestLiveDefangEntryPoint case.
EVID: prompts/agent_prompts.py:197 _CONTINUITY_TAG_RE = re.compile(r"</?\s*continuity\s*>") — no speech variant; grep '</\?speech' across halbert_core returns only comments (state_machine.py:1516, modality_wiring.py:354). Only user-query defang exists via haloysius demuxer.defang_input (state_machine.py:2722, modality_wiring.py:347-364) and only when the engine is installed; defang_system_text/_defang_s
DOC: HANDOFF-CENTRAL-TODO-BATCHES §1 U2 lists TASK-07 as landed but silently omits this sub-item; packet Status line said it was open and it still is.

### F13 U2-08 — Modality-aware prompt builder (MASTER-TODO:114)
status=in_progress cat=incomplete_feature prio=P2 conf=high act=True
REMAINING: Decide: Tier-0 single-segment design (no <speech> contract needed) vs the doc-14 dual-stream contract. If the latter, call get_modality_prompt_builder() from the response-prompt path. Either way response_modality is never 'voice' in production until U2-16 is fixed.
EVID: agent_prompts.py:593,685-692 build_response_prompt(response_modality=...) emits plain-text-for-speech guidance; _generate_personality(response_modality) -> persona/personality_prompt.py:72. BUT modality_wiring.get_modality_prompt_builder() (line 156-177, the engine's ModalityAwarePromptBuilder that emits <modality_context> + <speech> contract) has ZERO callers outside its own module (grep). No '<s
DOC: HANDOFF-CENTRAL-TODO-BATCHES §1 U2 claims 'prompt builder' and '<modality_context> XML' verified DONE — the engine has them; Halbert never invokes them.

### F13 U2-09 — <modality_context> XML injection block at the head of every task prompt (MASTER-TODO:117)
status=not_started cat=incomplete_feature prio=P2 conf=high act=True
REMAINING: Wire the engine's builder (or a Halbert-side block with channel/origin_area/speaker_verified/speaker_role/screen_present/quiet_hours/active_background_tasks) into build_response_prompt when the engine is present.
EVID: grep 'modality_context' in halbert_core/halbert_core/prompts/ -> no hits; only haloysius/modality/prompt_builder.py (lines 24,235,481,545,561,738) builds it, reached through get_modality_prompt_builder() which nothing calls.
DOC: HANDOFF-CENTRAL-TODO-BATCHES §1 says verified DONE by the modality merge — wrong for Halbert's prompt path.

### F13 U2-10 — StreamingTagDemuxer / speech_chunk events + frontend handler (MASTER-TODO:115-116)
status=done cat=doc_only prio=P3 conf=high act=True
REMAINING: Doc sync only: event is named speech_segment (not speech_chunk) and demux is post-hoc on clean_response, not streaming. Functionally unreachable in production until U2-16.
EVID: state_machine.py:2907-2985 demux_response -> emits 'modality_resolved' and 'speech_segment' StreamEvents (post-response demux via haloysius SpeechTextDemuxer, not a token-streaming buffer); frontend useAgentStream.ts:804-817 handles both; useVoiceModeMachine.ts:60-61,147-153 consumes them.
DOC: MASTER-TODO.md:115-116 '[ ]' and name the event speech_chunk; actual is speech_segment.

### F13 U2-11 — Frontend voice UI components (AcousticAuraIndicator, VoiceCompanionPill, ModalityHandoffBadge, AcousticEventCard)
status=done cat=doc_only prio=P3 conf=high act=True
REMAINING: MASTER-TODO checkbox; AcousticAnomalyModule action buttons (View Camera/Mute/Call) have no handlers and are hidden by default (file header lines 9-12).
EVID: src/components/audio/AcousticAuraIndicator.tsx, VoiceCompanionPill.tsx (G1 cycling fix present: setCurrentIdx((idx)=>(idx+1)%len) at ~line 38), ModalityHandoffBadge.tsx exist; 'AcousticEventCard' was realized as src/components/audio/AcousticAnomalyModule.tsx (O5, rendered by ProactiveEventsBadge.tsx); Layout.tsx:43 mounts AcousticAuraIndicator; vitest voice subset 136/136, tsc --noEmit exit 0 (202
DOC: MASTER-TODO.md:119 '[ ]'; HANDOFF-CENTRAL says 'all four' — the fourth is AcousticAnomalyModule, no AcousticEventCard file exists.

### F13 U2-12 — Rust AEC capture pipeline audio_capture.rs (MASTER-TODO:113)
status=in_progress cat=incomplete_feature prio=P2 conf=high act=True
REMAINING: (1) Python loopback ingress (audio/ingress/ has local_mic, rtsp, webrtc, wyoming — no TCP-loopback reader) wired into the coordinator; (2) frontend toggle invoking the Tauri commands; (3) hardware run. DECISION for founder: the dashboard already ingests mic via WebRtcIngress + browser getUserMedia (built-in AEC) — is the native AEC path still wanted, or should audio_capture.rs stay a dormant hedge?
EVID: src-tauri/src/audio_capture.rs on main (e10ea62f): DEFAULT_AUDIO_PORT=18400 (line 36), commands start/stop_audio_capture, set_mic_muted, get_audio_capture_status, feed_tts_reference registered lib.rs:513-517; Cargo.toml features voice-capture/aec default=[] (OFF). grep 18400 across repo: ONLY audio_capture.rs:36 + three handoff docs — no Python consumer. grep frontend for start_audio_capture/feed_
DOC: MASTER-TODO.md:113 '[ ]' though the Rust side landed; REV-09 §1 'No audio_capture.rs exists' is stale (landed later the same day).

### F13 U2-13 — macOS NSPanel + CGEventTap floating HUD + voice-hud frontend route (MASTER-TODO:120, P4)
status=done cat=doc_only prio=P3 conf=high act=True
REMAINING: Follow-ups from VoiceHud.tsx header: 'voice-hud:hotkey' interrupt event reaches only the HUD webview, not the main window's TTS player (Space can dismiss but not pause voice); P4 (78d21a7e) never got an external review pass (Opus results note 1); no hardware run. HUD shows nothing in production until U2-16 (no speech segments to relay).
EVID: floating_panel.rs:30 HUD_WINDOW_LABEL="voice-hud", :108 WebviewUrl::App("voice-hud"); hud_hotkey.rs; lib.rs:518-520 show/hide/get_voice_hud_status; capabilities/default.json:5 windows [main, voice-hud]; App.tsx:147 <Route path="/voice-hud" element={<VoiceHud/>}>, App.tsx:101 onboarding-gate skip; pages/VoiceHud.tsx; lib/hudChannel.ts + hooks/useHudSpeech(.Publisher).ts; AgentChat.tsx:357 publisher
DOC: MASTER-TODO.md:120 '[ ]'; documentation/design/16 line 54 'voice-hud route was never built' is stale; HANDOFF-WRAP-UP §3 item 2 stale.

### F13 U2-14 — REV-09 F3: VAD frame-size bug (480 vs 512 samples) — speech track can never trigger
status=not_started cat=bug prio=P1 conf=high act=True
REMAINING: Slice 1024-byte frames (or accumulate to 512 samples); stop flush() per frame; add a test driving _speech_track_loop with real frame sizes. Blocks wake, ASR turns, speaker-ID and VAD barge-in.
EVID: audio/pipeline.py:334 frame_target = 960 (bytes = 480 samples); audio/speech/vad.py:31 SILERO_WINDOW_SAMPLES=512, :164-166 'if n < SILERO_WINDOW_SAMPLES: return False'; vad.py:175 flush() per frame. grep tests for frame_target/_speech_track_loop/is_speech: no coverage.

### F13 U2-15 — REV-09 F5: production never resolves VOICE modality — entire voice-out chain unreachable
status=not_started cat=bug prio=P0 conf=high act=True
REMAINING: After coordinator start in app.py, call get_app_seam().get_channel_capability().set_audio_pipeline(coordinator) (or define get_audio_pipeline in routes/audio.py reading app.state); wrap Wyoming turns with set_wyoming_active(True/False); thread ctx.speaker_role into build_modality_context (its speaker_role param is dead, modality_wiring.py:245-324); add an integration test that a turn with a running coordinator+TTS emits speech_segment.
EVID: integrations/channel_capability.py:150 'from ..dashboard.routes.audio import get_audio_pipeline' — no such function (grep 'def get_audio_pipeline' empty; coordinator lives at request.app.state.audio_coordinator, routes/audio.py:121); set_audio_pipeline/set_wyoming_active have zero callers (grep); app_seam.py:418 lazily builds HalbertChannelCapability() with defaults; cognition_wiring.py:305 wire_h
DOC: HANDOFF-VOICE-MODE-OPUS-RESULTS calls O3 'TTS egress end-to-end' — only end-to-end under a mocked modality; no unmerged branch touches these files either.

### F13 U2-16 — REV-09 F1: Wyoming TCP server unauthenticated, binds 0.0.0.0:10400, enabled by default
status=not_started cat=security prio=P1 conf=high act=True
REMAINING: Default WYOMING_ENABLED=0 or bind 127.0.0.1 unless a shared token is configured; require a token in the transcript frame; consider confirmation for MEDIUM on unknown voice turns.
EVID: wyoming_agent.py:37 DEFAULT_HOST="0.0.0.0", :62 WYOMING_ENABLED default "1"; app.py:752-770 starts it unconditionally when enabled; unknown role still executes MEDIUM-risk tools without confirmation (REV-09 F1 chain).

### F13 U2-17 — REV-09 F2: Wyoming turns run on a second event loop; per-loop turn lock lets turns clobber shared AgentStateMachine state
status=not_started cat=bug prio=P1 conf=high act=True
REMAINING: Funnel Wyoming turns onto the app loop (run_coroutine_threadsafe) or give the voice channel its own AgentStateMachine; add a two-loop test.
EVID: app.py:759-768 asyncio.new_event_loop() + run_forever in a daemon thread; wyoming_agent.py:226-234 _get_agent() returns the dashboard singleton; REV-09 F2 (state_machine turn_lock is per-loop).

### F13 U2-18 — REV-09 F4: enrolled voiceprints never loaded into the runtime matcher; /speakers/{id}/test always False
status=not_started cat=bug prio=P2 conf=high act=True
REMAINING: On SpeakerIdentifier construction (or pipeline start) load store.list_all() into the embedding manager; remove on delete; add an enroll->identify seam test.
EVID: routes/audio.py:179-225 enroll builds a fresh SpeakerIdentifier(threshold=...) per request and persists via store.enroll; no code calls SpeakerProfileStore.list_all() except the list endpoint (routes/audio.py:153); speaker_id.py has no loader (grep list_all/embedding_as_list in audio/ -> only definitions).

### F13 U2-19 — REV-09 F6: enrollment role overrides biometric confidence bands (0.75 match -> admin)
status=not_started cat=security prio=P2 conf=high act=True
REMAINING: Accept profile.role only when confidence meets that role's band; PIN challenge for admin band.
EVID: integrations/voice_auth_gate.py:158-159 'role = profile.role or role' after band classification; latent only because U2-18 keeps the matcher empty.

### F13 U2-20 — REV-09 F7: Piper synthesizes the whole clip before the first chunk — barge-in cannot abort generation
status=not_started cat=bug prio=P2 conf=high act=True
REMAINING: Sentence-level synthesis with token checks between sentences.
EVID: audio/speech/tts_engine.py:109-125 full generate() in run_in_executor, cancel token checked only in the chunk loop; state_machine.py:3077-3080 docstring acknowledges it.

### F13 U2-21 — REV-09 F8: HIGH-risk confirmation unreachable from voice — satellite hears 'I'm not sure how to help'
status=not_started cat=bug prio=P2 conf=high act=True
REMAINING: Speak the confirmation prompt as the reply; key pending confirmation to conversation_id; route a 'confirm' transcript to it.
EVID: wyoming_agent.py:182-186 collects only response_chunk/response_complete, ignores tool_confirmation_required; :123 fallback text; per-turn UUID orphans pending_confirmation.

### F13 U2-22 — REV-09 F9: SpeechResult sample-rate/format labelling
status=in_progress cat=bug prio=P3 conf=high act=True
REMAINING: Label format pcm_s16le (or emit a WAV header) in HalbertVoiceBackend.synthesize.
EVID: FIXED half: tts_engine.py:126-130 now records self._sample_rate (O3). OPEN half: voice_backend.py:150 format="wav" on headerless PCM (egress hub correctly says s16le).

### F13 U2-23 — REV-09 F10: Wyoming agent speaks a non-canonical JSONL variant
status=in_progress cat=bug prio=P2 conf=high act=True
REMAINING: Reuse the canonical frame reader/writer in the agent; implement info/synthesize events if native HA Wyoming is the target.
EVID: Landed (REV-03 F3/F4): describe->info reply wyoming_agent.py:296-315, audio-chunk payload drain :287-294. Still open: bare readline() framing (:250), non-canonical 'response' event (:276-279); canonical read_wyoming_frame/write_wyoming_frame exist in audio/ingress/wyoming_ingress.py:51,99 and are unused by the agent (grep).

### F13 U2-24 — REV-09 F11: wake-word detection runs on a single trigger frame
status=not_started cat=bug prio=P3 conf=high act=False
REMAINING: Feed openWakeWord every frame; trigger on wake state with VAD as gate. Wake word is deferred for Voice Mode v1 (doc 16 line 50) — low priority.
EVID: audio/pipeline.py:357-360 self._wake_word.detect(frame) on the VAD-trigger frame only; masked today by wake_detected=True fallback and by U2-14.

### F13 U2-25 — REV-09 F12: wyoming_agent and WyomingIngress both default to port 10400
status=not_started cat=bug prio=P3 conf=high act=True
REMAINING: Separate defaults (e.g. ingress 10401) or a startup port check.
EVID: wyoming_agent.py:38 DEFAULT_PORT=10400; audio/config.py:53 port=10400. Latent: app.py:663-673 attaches only WebRtcIngress, not WyomingIngress.

### F13 U2-26 — REV-09 F13: blocking ONNX inference on the event loop
status=not_started cat=bug prio=P3 conf=high act=True
REMAINING: Executor-wrap ASR/tagger calls; bulk-write in buffer.py.
EVID: audio/pipeline.py:393 self._asr.transcribe_chunk(pcm) and :478 self._audio_tagger.classify(pcm) called inline; grep run_in_executor in pipeline.py: none.

### F13 U2-27 — pipeline.speak() local device playback is a stub
status=in_progress cat=incomplete_feature prio=P3 conf=high act=True
REMAINING: DECISION: is native device playback needed for the kiosk/HA-node case, or is browser playback the only sink? If the latter, delete the stub or document it.
EVID: audio/pipeline.py:686-691 loop body is 'pass' with comment 'In a full implementation, this would write to the audio output device'; browser playback exists instead via TTS egress hub + frontend src/lib/ttsPlayback.ts (O3).

### F13 U2-28 — On-hardware verification of mic capture + AEC + NSPanel + CGEventTap (P5)
status=not_started cat=test_gap prio=P2 conf=medium act=True
REMAINING: Founder's machine: build with --features aec, start capture, summon HUD, verify Esc/Space tap (needs Accessibility trust), verify no focus steal.
EVID: HANDOFF-CENTRAL-TODO-BATCHES §3 and HANDOFF-WRAP-UP §3 item 3: compile/unit-verified only; HANDOFF-VOICE-MODE-VISUAL-UI line 34 lists P5 still open; no evidence of a run since.

### F13 U2-29 — macos-private-api enabled for the transparent HUD — App Store acceptability decision
status=blocked cat=decision prio=P2 conf=high act=True
REMAINING: Founder decides: drop transparency for App Store builds (feature-gate) or ship the HUD only in the non-App-Store channel. Ties to FDR-DEC-03 / TASK-06.
EVID: src-tauri/Cargo.toml:35 tauri features include "macos-private-api"; tauri.conf.json:13 "macOSPrivateApi": true; floating_panel.rs:19-21 caveat comment.

### F13 U2-30 — feat/voice-mode-mark-v2: 1 unmerged commit + 10 uncommitted design-system/voice files in its worktree
status=in_progress cat=needs_commit prio=P2 conf=medium act=True
REMAINING: Owner session must commit the WIP (v2 founder tuning: pluck springs, traveling bulges) and run packages/design-system tests; then merge. I did not run the branch's tests (would require checkout). Opus results note: createNodeAnalyserSource analyser-disconnect fix on main (5bee80c7) should be reconciled on merge.
EVID: git log main..feat/voice-mode-mark-v2 -> 25213235 (geometry.ts + voiceGeometry.test.ts, +239/-106); merge-tree --write-tree main feat/voice-mode-mark-v2 exit 0 (no conflicts). Worktree ~/.config/superpowers/worktrees/Halbert/voice-mode-visual-ui status: 10 modified (AudioReactiveHalbertMark.tsx, spectrum.ts, springs.ts, index.ts, 3 tests, story, doc 16, visual-ui handoff; +479/-145) + untracked wt

### F13 U2-31 — Test-coverage gaps in the voice chain
status=not_started cat=test_gap prio=P2 conf=high act=True
REMAINING: Add the four tests alongside the fixes in U2-14/15/17/18.
EVID: No test drives _speech_track_loop frame sizing (grep frame_target in tests: none); no enroll->identify seam test; test_modality_voice_phase2.py:192 constructs HalbertChannelCapability(wyoming_active=True) directly and test_tts_egress.py:338 mocks recommended_modality — production wiring untested; no two-loop Wyoming test.

### F13 U2-32 — MASTER-TODO 'Sentient Home & Auditory Cortex' section is stale wholesale
status=not_started cat=doc_only prio=P3 conf=high act=True
REMAINING: Strike 9 items with commit shas; re-word 110/114/117 per U2-04/08/09; add REV-09 open findings (U2-14..26) as the real remaining list.
EVID: .handoff/MASTER-TODO.md:109-120 — all 12 items '[ ]'; verified done: 109,111,112,113(Rust half),115,116,118,119,120; partial: 110,114; not done: 117. HANDOFF-CENTRAL §5 says strikethroughs were deferred to merge time and never landed.
DOC: See per-item notes; also HANDOFF-CENTRAL §1 U2 'Verified DONE ... <modality_context> XML, prompt builder, all four voice UI components' is wrong in substance for the first two and in name for the fourth.

### F14 MD-01 — Design-system HalbertMark: explicit line counts (3/4/5/6/7/8/10) + `lines` prop, density aliases kept
status=done cat=needs_commit prio=P1 conf=high act=True [V:confirmed]
REMAINING: Fix the JSDoc typo (MD-02), then commit with the stories + test files. No behavioural follow-up required.
EVID: git diff packages/design-system/src/primitives/HalbertMark.tsx: HalbertMarkDensity union expanded (lines 6-19), new `lines?: 3|4|5|6|7|8|10` prop (line 48), PATHS_8/PATHS_7/PATHS_5 added, CONFIG_BY_LINE_COUNT + resolveLineCount() replace TIER_CONFIG; className emits `hb-mark--{n}lines` plus legacy `hb-mark--display|medium|compact|small` aliases (lines 239-247). `auto` mapping unchanged (<=24→3, <=
VERIFY: confirmed — Re-ran independently: `git diff packages/design-system/src/primitives/HalbertMark.tsx` = +124/-40; HalbertMarkDensity union now 'auto'|'10'|'8'|'7'|'6'|'5'|'4'|'3'|'display'|'medium'|'compact'|'small' (lines 6-19); `lines?: 3|4|5|6|7|8|10` (line 48); PATHS_10/8/7/6/5/4/3 + CONFIG_BY_LINE_COUNT + resolveLineCount() replace TIER_CONFIG; className emits `hb-mark--{n}lines` plus the four legacy alias 

### F14 MD-02 — JSDoc dropped word in `lines` prop doc ("Overrides  if provided.")
status=in_progress cat=bug prio=P3 conf=high act=True [V:confirmed]
REMAINING: Change to "Overrides `density` if provided." before committing MD-01.
EVID: packages/design-system/src/primitives/HalbertMark.tsx:45 reads `* Overrides  if provided.` — the word `density` is missing (likely eaten by a template/brace).
VERIFY: confirmed — `grep -n Overrides packages/design-system/src/primitives/HalbertMark.tsx` → `45:   * Overrides  if provided.` — double space where the word `density` (or a backticked `density`) was dropped. Note the same dropped-word text exists in the dead dashboard copy (components/brand/HalbertMark.tsx), which is further evidence both files were produced by the same templated edit.

### F14 MD-03 — Storybook OpticalTiers story rewritten as candidate comparison + full 10→3 progression
status=done cat=needs_commit prio=P2 conf=high act=True [V:adjusted]
REMAINING: Commit alongside MD-01. Minor: `undefined` inside a Storybook select `options` array renders an 'undefined' entry — consider `control: { type: 'select' }` with a labelled 'auto' mapping. Story copy hard-codes hex fallbacks in `var(--color-x, #hex)` — acceptable in stories but not in components.
EVID: git diff packages/design-system/src/stories/HalbertMark.stories.tsx: +178/-? lines; argTypes.lines options `[undefined, 10, 8, 7, 6, 5, 4, 3]`; render() builds a 'Candidate Replacement Focus' panel labelling 7-line 'Proposed Primary' and 4-line 'Proposed Micro'. Test file adds one case asserting hb-mark--7lines/4lines/8lines classes (primitives.test.tsx:238-248).
VERIFY: adjusted — Diff is +142/-36 by numstat (the finder's '+178' is the diffstat total churn, not additions). Confirmed: argTypes.lines `options: [undefined, 10, 8, 7, 6, 5, 4, 3]` (diff line 15); density options extended with the numeric strings (line 21); candidate panel with 'Proposed Primary' badge for 7-line; hex fallbacks inside `var(--color-x, #hex)` throughout (lines 66-169 of the diff). Test file adds on
  CORRECTED_REMAINING: Commit alongside MD-01 after (a) fixing the JSDoc typo and (b) reconciling 'Proposed Small' (stories.tsx:50) vs 'Proposed Micro' (stories.tsx:108). The `undefined` select entry and hex fallbacks are acceptable in stories.

### F14 MD-04 — Founder decision pending: adopt 7-line as primary mark and 4-line as micro?
status=not_started cat=decision prio=P2 conf=high act=True [V:confirmed]
REMAINING: Founder picks: keep 3/6/10 auto mapping, or switch auto to 4/7/10 (or 4/7/8) and regenerate favicon/README banner accordingly. If adopted, change resolveLineCount() thresholds, README §1 table, favicon.svg, and marketing assets in one follow-up commit.
EVID: Stories label 7-line 'Proposed Primary' and 4-line 'Proposed Micro' (HalbertMark.stories.tsx candidate panel); `auto` density still maps to 3/6/10 (HalbertMark.tsx resolveLineCount default branch), assets/brand/README.md still documents the 4-tier display/medium/compact/small scheme, favicon.svg still uses the 3-line small tier. Nothing in the diff changes the shipped mark.
VERIFY: confirmed — assets/brand/favicon.svg still uses the 3-path tier (stroke-width 116.00, paths M512 80 / M296 137.88 / M80 512 — checked with `head -c 400`); assets/brand/README.md §1 still documents exactly four tiers Display/Medium/Compact/Small (README lines 9-16), mtime 2026-08-26, unmodified; resolveLineCount default branch still returns 3/6/10 for auto. Nothing in the diff changes the shipped mark; the 7/4

### F14 MD-05 — MUST NOT COMMIT: resurrected duplicate halbert_core/.../components/brand/HalbertMark.tsx
status=obsolete cat=cleanup prio=P1 conf=high act=True [V:adjusted]
REMAINING: Delete the directory (`rm -rf halbert_core/halbert_core/dashboard/frontend/src/components/brand/`). Do not stage it.
EVID: Untracked dir halbert_core/halbert_core/dashboard/frontend/src/components/brand/ (1 file, 217 lines, mtime 2026-09-01 08:41) — NOT in the orchestrator's brief because `git status` output was truncated. History: created in caac105e (2026-08-26), deleted on main in 493956ab (2026-08-29 'refactor: kill 5 duplicate component files, consolidate into canonical sources'). Nothing imports it (`grep -rn co
VERIFY: adjusted — Path confirmed untracked (`git status --porcelain --untracked-files=all` line 46 — the orchestrator's truncated brief omitted it), mtime 2026-09-01 08:41:48, 217 lines. History confirmed: created caac105e (2026-08-26), deleted on main by 493956ab; `git ls-tree main -- .../components/brand/` is empty. Nothing imports it (grep over dashboard src and packages: only node_modules/storybook noise). Hard
  CORRECTED_REMAINING: Delete `halbert_core/halbert_core/dashboard/frontend/src/components/brand/` before committing anything. Founder should identify which agent/tool session regenerated it (same session that wrote the 08:42 SVGs) so it does not recur.

### F14 MD-06 — 35 new assets/brand/halbert-mark-{N}lines*.svg — 15 new, 20 duplicates, no generator, unreferenced
status=in_progress cat=decision prio=P2 conf=high act=True [V:confirmed]
REMAINING: Decide naming scheme: (a) commit only the 15 new 8/7/5-line files under the existing tier vocabulary, or (b) commit all 35 as a numeric `{N}lines` scheme and retire the tier-named files. Either way update assets/brand/README.md (MD-07) in the same commit, add the missing `-charcoal` variant for consistency, and ideally check in the generator script (scripts/gen_brand_marks.py) so the SVGs are reproducible from the component's path tables.
EVID: `git status --porcelain | grep lines` → 35 files (7 line counts × 5 variants: plain/currentColor, -vermilion, -vermilion-on-canvas, -charcoal-on-canvas, -badge), all mtime 2026-09-01 08:42. diff shows 10lines/6lines/4lines/3lines sets are identical to display/medium/compact/small except `<rect ... />` vs `<rect .../>` whitespace (different generator than caac105e). Genuinely new: 8lines, 7lines, 5
VERIFY: confirmed — `git status --porcelain --untracked-files=all | grep assets/brand/` → exactly 35 files (3/4/5/6/7/8/10 lines × plain/-vermilion/-vermilion-on-canvas/-charcoal-on-canvas/-badge), all mtime 2026-09-01 08:42. My cmp/whitespace-stripped diff: for 10/6/4/3 lines the plain and -vermilion files are BYTE-IDENTICAL to display/medium/compact/small (8 files), the -on-canvas and -badge files differ only in wh

### F14 MD-07 — assets/brand/README.md not updated for new line-count variants
status=not_started cat=doc_only prio=P3 conf=high act=True [V:confirmed]
REMAINING: Add the 8/7/5 rows (pitch 61.71/72.0/108.0 px, stroke 34.29/40.0/60.0) and the `lines={7}` usage example; document whichever filename scheme MD-06 settles on.
EVID: assets/brand/README.md is unmodified (not in `git status`); §1 table lists only Display/Medium/Compact/Small and §2 lists `{tier}` filenames; §5 React example does not mention the `lines` prop.
VERIFY: confirmed — assets/brand/README.md is not in `git status`; mtime 2026-08-26 10:18; §1 table lists only Display/Medium/Compact/Small; §2 uses `{tier}` filenames; the only React examples (lines 67-68) use `density="medium"`/`"small"` — no `lines` prop mentioned.

### F14 MD-08 — Rust-native-core plan doc augmentation (56→72 tasks, FFI waves, Docker track, §16 L0–L3)
status=done cat=needs_commit prio=P2 conf=high act=True [V:confirmed]
REMAINING: Commit together with MD-09/MD-10/MD-12 as one docs commit. Depth review of the plan's technical content belongs to the Rust-docs agent.
EVID: git diff --numstat → +2383/-169; file now 2,640 lines. Verified: 72 unique task ids; R0.1–R0.10 rows present (lines 205-214); R4a/R4b/R4c mentioned 46/32/34×; `rust-toolchain.toml` 9×; `mcp_response` 8×; `halbert-core[rust]` 8×; `ghcr.io/ericbintner/halbert-core` 6×; §16 'Long-Term Strategy Beyond R7' at line 2450 with L0–L3; F7 applied as 'runtime Btrfs detection, no Requires=' (line 1646) rather
VERIFY: confirmed — `git diff --numstat` → 2383/169; file is 2,640 lines. Unique task ids matching `R[0-7]\.\d+` = 72 and table rows beginning `| R…` = 72; per phase R0=10, R1=9, R2=10, R3=9, R4=7, R5=14, R6=7, R7=6. Keyword counts: R4a 46, R4b 32, R4c 34, rust-toolchain.toml 9, mcp_response 8, halbert-core[rust] 8, ghcr.io/ericbintner/halbert-core 6, ConditionPathIsMountPoint 0, `Requires=` 5. §16 'Long-Term Strateg

### F14 MD-09 — HA-STRATEGY scoping doc amendments (HACS→Supervisor add-on repo, hardened compose §7, Path 3 correction, §9 rows)
status=done cat=needs_commit prio=P2 conf=high act=True [V:confirmed]
REMAINING: None beyond committing. Nit: the doc says the review's findings were applied 'per founder directive' — no founder sign-off artefact is in the tree; the plan header says the same. Founder should confirm that directive actually happened.
EVID: git diff .handoff/HA-STRATEGY-SCOPING-AND-DEPLOYMENT-PATHS-2026-08-31.md: +165 lines; status line amended 2026-09-01; §7 compose rewritten (bridge net, Mosquitto auth + 127.0.0.1:1883 only, HA alone on host net, host.docker.internal:host-gateway); Path 3 'agent already runs in Docker' struck; §8 amendments block; §9 adds container-image and `halbert-core[rust]` rows. Fact-checks: HACS indeed does 
VERIFY: confirmed — numstat +128/-37 (finder's '+165' is total churn). Read the full diff: status line amended 2026-09-01 (line 4); Option E/HACS wording → Supervisor add-on repository (lines 30-32, 81-83, 213-214, 223-226); new 'Agent container image' row in the near-term table; Path 3 'agent code already runs in Docker' explicitly struck with a 2026-09-01 correction; §7 compose rewritten (bridge network `halbert-ne

### F14 MD-10 — MASTER-TODO.md Rust-section diff: every changed line checked — accurate
status=done cat=needs_commit prio=P2 conf=high act=True [V:confirmed]
REMAINING: Commit with MD-08/09. The link target is an untracked file (MD-12) — commit in the same commit or the link dangles; and if MD-12's rename is adopted, update this link.
EVID: git diff .handoff/MASTER-TODO.md touches only lines 168-193 (Rust Native Core subsection). Line-by-line: heading adds 'augmented 2026-08-31, edits landed 2026-09-01' ✓; '72 tasks across 8 phases … 56 in R1–R6' ✓ (10+9+10+9+7+14+7+6=72; 9+10+9+7+14+7=56); R0 '10 tasks' ✓ (R0.1–R0.10); R1/R2/R3 '+ FFI wave R4a/b/c' ✓ matches plan §7; R5 'internal socket IPC + one external MCP surface' ✓ (plan mcp_re
VERIFY: confirmed — `git diff .handoff/MASTER-TODO.md` is a single hunk @@ -165,23 +165,25 @@ (13 added / 11 removed) — the Rust subsection only. Checked each changed line against the plan doc: 72 tasks / 8 phases and 56 in R1–R6 (9+10+9+7+14+7) ✓; R0 10 tasks 'Sonnet med/high, ~3 days' matches plan line 2321; R1 '+ wave R4a … ~2.5 weeks' matches line 2322; R4 three waves ✓ (46/32/34 mentions); R5 'internal socket IP

### F14 MD-11 — MASTER-TODO.md unchanged lines are stale vs git (security tests, U6 boxes, Findings.tsx rename, Updated date)
status=in_progress cat=doc_only prio=P2 conf=high act=True [V:adjusted]
REMAINING: Separate `docs(todo)` commit: strike S1–S4/S6/W25 with shas, keep S5/S7/D1–D4 open only if the ha-simplification agent confirms; drop the two existing tests from the 'missing tests' list (keep only test_redactor.py, and note it is a documented non-goal); tick the Findings.tsx rename; bump Updated date. Also note MASTER-TODO uses file:///Volumes/4TB-BAD links throughout (pre-existing convention, machine-specific).
EVID: Lines 27 and 41 say `test_tier2_guarantee.py`, `test_security_roles.py` 'do not exist' — both exist on main (`git ls-tree main` halbert_core/tests/; landed via 5a132654 which IS an ancestor of main). U6 subsection (lines 125-160) has 18 unchecked boxes incl. S1–S6, yet main has 226555ef/d733ec9a (S1), 5e2ce6b4 (S2), 5f87520c/0514a5c3 (S3), 6f46f09a (S4), 6a077653 (S6), 3ce98551 (W25) and merges 4e
DOC: MASTER-TODO claims test_tier2_guarantee.py/test_security_roles.py do not exist and lists U6 S1–S6 as open; git shows both tests present and S1–S4/S6 merged 2026-08-30.
VERIFY: adjusted — All stated claims confirmed: line 27 (U1 row) and line 41 both say test_tier2_guarantee.py/test_security_roles.py 'do not exist', yet `git ls-tree main halbert_core/tests/` lists both and 5a132654 is an ancestor of main; U6 subsection has 18 unchecked boxes while 226555ef, d733ec9a, 5e2ce6b4, 5f87520c, 0514a5c3, 6f46f09a, 6a077653, 3ce98551, 4e4ff2f4, 93c863c1 are all ancestors; 'Rename pages/Secu
  CORRECTED_REMAINING: Separate `docs(todo)` commit that: strikes S1–S4, S6, S7, W25, D1, D4 with shas; leaves S5, D2, D3 open unless the ha-simplification agent finds commits; ticks Findings.tsx rename (e7e7ad2f), Settings decomposition (0a610642…108c17d9), sidebar consolidation (91e7b6eb), line-156 S6 duplicate (6a07765

### F14 MD-12 — Path collision: untracked REVIEW-REQUEST-RUST-NATIVE-CORE-2026-08-31.md vs the different doc committed on feat/rust-native-core
status=blocked cat=bug prio=P1 conf=high act=True [V:confirmed]
REMAINING: Rename main's copy (e.g. .handoff/REVIEW-RESULTS-RUST-NATIVE-CORE-SANITY-2026-08-31.md) and update its cross-references in MASTER-TODO.md (1 link in the diff), HA-STRATEGY doc (3 mentions), and the plan doc header/source list — `grep -rn REVIEW-REQUEST-RUST-NATIVE-CORE .handoff` before committing. Alternatively rename the branch's file when that branch is next touched.
EVID: `git show feat/rust-native-core:.handoff/REVIEW-REQUEST-RUST-NATIVE-CORE-2026-08-31.md` (cc19695d, 382 lines) = 'External Review Request: Rust Native Core Architecture & Implementation Plan' asking for an Opus/Fable architecture review and embedding the worktree path /Users/ericbintner/.config/superpowers/worktrees/Halbert/rust-native-core. Working-tree file (360 lines) = 'Review Request — Rust Na
VERIFY: confirmed — `git show feat/rust-native-core:.handoff/REVIEW-REQUEST-RUST-NATIVE-CORE-2026-08-31.md` = 382 lines, title 'External Review Request: Rust Native Core Architecture & Implementation Plan', line 5 embeds `/Users/ericbintner/.config/superpowers/worktrees/Halbert/rust-native-core`, committed in cc19695d. Working-tree file = 360 lines, title 'Review Request — Rust Native Core Plan & Docker Integration P

### F14 MD-13 — PAUSE-STATE-RUST-ROADMAP-AUGMENTATION-2026-08-31.md is obsolete and carries a machine-specific path — do not commit
status=obsolete cat=retire prio=P2 conf=high act=True [V:confirmed]
REMAINING: Delete the file (or, if the founder wants the pause history, strip the ~/.claude path and fold the 'Grounding facts' block into the plan doc). Not worth a commit on its own.
EVID: File header: '> **RESUMED AND COMPLETED 2026-09-01.**' (61 lines, mtime 08:18). Line 25 embeds `/Users/ericbintner/.claude/projects/-Volumes-4TB-BAD-Halbert/3c9feb2a-.../workflows/scripts/augment-rust-roadmap-docs-wf_4fe60499-a7b.js`. Everything it records is now captured by the plan doc header and REVIEW-REQUEST §7. Memory note 'Rust roadmap augmentation DONE' agrees.
VERIFY: confirmed — File is 61 lines, mtime 08:18:20, header '> **RESUMED AND COMPLETED 2026-09-01.**'; line 25 embeds `/Users/ericbintner/.claude/projects/-Volumes-4TB-BAD-Halbert/3c9feb2a-…/workflows/scripts/augment-rust-roadmap-docs-wf_4fe60499-a7b.js`. Nothing references it (`grep -rn PAUSE-STATE .handoff documentation` → only itself). I checked its 'Grounding facts' block is already in the plan doc: suite-census

### F14 MD-14 — HANDOFF-SEMANTIC-AUDIT-AND-TERMINOLOGY-REVIEW-2026-09-01.md — unstarted proposal from an external tool; dead link and a wrong path
status=not_started cat=decision prio=P2 conf=high act=True [V:adjusted]
REMAINING: Founder decision: adopt as a terminology workstream or park. If kept: remove the ~/.gemini link (or copy semantic_audit.md into the repo), fix `halbert_core/cli/`, add a MASTER-TODO pointer, and note that phases 3–4 (config shims, package renames) are large refactors that conflict with the 'finish current features' priority — only Phase 1 (docs/prompts wording) is cheap.
EVID: 129 lines, mtime 10:12; 'Status: Initial Audit Complete; Ready for Deep Scrutiny'. Line 111 links its primary evidence to file:///Users/ericbintner/.gemini/antigravity/brain/b690d9c9-…/semantic_audit.md (not in repo, machine-specific). Task 1.1 references `halbert_core/cli/` — does not exist (`[ -e halbert_core/cli ]` false; CLI lives in Halbert/main.py). All other referenced paths exist (BeingTab
VERIFY: adjusted — Confirmed: 129 lines, mtime 10:12:23, Status line 6 'Initial Audit Complete; Ready for Deep Scrutiny…'; line 111 links `file:///Users/ericbintner/.gemini/antigravity/brain/b690d9c9-…/semantic_audit.md` (outside repo); lines 113-129 use file:///Volumes links; `grep -c SEMANTIC-AUDIT .handoff/MASTER-TODO.md` = 0; the banned host term appears 2× (line 62 table row proposes eliminating it); proposes r
  CORRECTED_REMAINING: Founder decision: adopt as a terminology workstream or park. If kept: remove/replace the ~/.gemini link (copy semantic_audit.md into the repo or drop the link), add a MASTER-TODO pointer, and note that Phases 3–4 are large refactors conflicting with the finish-current-features priority. Do NOT edit 

### F14 MD-15 — HANDOFF-BRANCH-AND-WORKTREE-AUDIT-2026-09-01.md — claim register with two contradicted load-bearing claims
status=in_progress cat=doc_only prio=P1 conf=high act=True [V:adjusted]
REMAINING: Before committing: rewrite the 'Do this first' bullets — security-review-01 needs a conflict resolution in test_mcp_server.py, and the 5057e893 bullet should be struck as already-landed (31fa91ef); add the four omissions. Then commit as docs(handoff).
EVID: 38 lines, mtime 13:55 (latest file in tree). CLAIMS → my check: (1) 9e057db7/c5b6bb91/a09632e1 not on main → CONFIRMED (`git merge-base --is-ancestor` false for all three). (2) 'merge-tree dry run against current main is clean' for feat/security-review-01 → CONTRADICTED: `git merge-tree --write-tree main feat/security-review-01` exit 1, 'CONFLICT (content): Merge conflict in halbert_core/tests/tes
DOC: Doc says feat/security-review-01 merge-tree is clean (it conflicts in halbert_core/tests/test_mcp_server.py) and that 5057e893's REV-02 results are not on main (they are, as 31fa91ef).
VERIFY: adjusted — Re-ran every check. (1) 9e057db7/c5b6bb91/a09632e1 all `merge-base --is-ancestor` false → CONFIRMED not on main. (2) `git merge-tree --write-tree main feat/security-review-01` exit 1, 'CONFLICT (content): Merge conflict in halbert_core/tests/test_mcp_server.py' → the audit's 'dry run is clean' is WRONG, confirmed. (3) 5057e893 is a dangling commit (`git branch -a --contains` empty; worktree-centra
  CORRECTED_REMAINING: Before committing the audit doc: fix 'merge-tree clean' → conflict in test_mcp_server.py; strike the 5057e893 bullet (landed as 31fa91ef + e7e7ad2f); fix the security-review-01 untracked-docs bullet (PROGRESS is committed; the untracked pair is RECONCILIATION + a divergent HANDOFF-HOME-AUTOMATION-SI

### F14 MD-16 — Cross-worktree overlap check: none with voice-mode-visual-ui; halbert-mcp's uncommitted MASTER-TODO is a stale restructure
status=done cat=cleanup prio=P2 conf=high act=True [V:confirmed]
REMAINING: Committing MD-01 on main is conflict-free. The halbert-mcp worktree's MASTER-TODO edit must be discarded (never applied over main) — flag to the halbert-mcp agent/founder.
EVID: voice-mode-visual-ui dirty files: voice/AudioReactiveHalbertMark.tsx, voice/index.ts, voice/spectrum.ts, voice/springs.ts, stories/AudioReactiveHalbertMark.stories.tsx, test/audioReactiveMark.test.tsx, test/voiceSpectrum.test.ts, test/voiceSprings.test.ts + 2 docs — disjoint from main's dirty primitives/HalbertMark.tsx, stories/HalbertMark.stories.tsx, test/primitives.test.tsx. halbert-mcp worktre
VERIFY: confirmed — voice-mode-visual-ui `status --porcelain`: 2 docs + stories/AudioReactiveHalbertMark.stories.tsx, test/audioReactiveMark.test.tsx, test/voiceSpectrum.test.ts, test/voiceSprings.test.ts, voice/AudioReactiveHalbertMark.tsx, voice/index.ts, voice/spectrum.ts, voice/springs.ts, + untracked wt_pytest.py — disjoint from main's three dirty design-system files; its voice code imports only `type HalbertMar

### F14 MD-17 — Proposed commit plan for the dirty main tree (no trailers)
status=not_started cat=decision prio=P1 conf=high act=True [V:adjusted]
REMAINING: PRE-STEP: `rm -rf halbert_core/halbert_core/dashboard/frontend/src/components/brand/` and `rm .handoff/PAUSE-STATE-RUST-ROADMAP-AUGMENTATION-2026-08-31.md`; fix HalbertMark.tsx:45 typo; rename REVIEW-REQUEST-RUST-NATIVE-CORE-2026-08-31.md and fix its cross-refs.

COMMIT 1 — `feat(design-system): HalbertMark explicit line counts via lines prop; density aliases preserved` — packages/design-system/src/primitives/HalbertMark.tsx, src/stories/HalbertMark.stories.tsx, src/test/primitives.test.tsx. (Ready now.)

COMMIT 2 — `feat(brand): 5/7/8-line mark variants and README update` — the 15 new 8/7/5-l
EVID: Groupings derived from file mtimes (08:18 Rust review/pause docs; 08:41-08:42 brand SVGs + resurrected dashboard copy; 10:12 semantic audit; 10:27 design-system + Rust plan/HA/MASTER-TODO batch; 13:55 branch audit) and from the disjoint concerns above.
VERIFY: adjusted — Groupings and mtime clusters verified (08:18 review/pause docs; 08:41-08:42 SVGs + dead dashboard copy; 10:12 semantic audit; 10:27 design-system + plan/HA/MASTER-TODO batch; 13:55 branch audit). Plan is sound with three corrections: (a) COMMIT 3's 'MASTER-TODO.md (Rust hunk only — use git add -p)' is unnecessary — the whole MASTER-TODO diff is that one hunk (lines 165-193), so a plain `git add` i
  CORRECTED_REMAINING: PRE-STEP: delete components/brand/ and PAUSE-STATE; fix HalbertMark.tsx:45 typo and stories.tsx:50/108 label; rename REVIEW-REQUEST-RUST-NATIVE-CORE-2026-08-31.md (e.g. REVIEW-RESULTS-RUST-NATIVE-CORE-SANITY-2026-08-31.md) and update refs in MASTER-TODO:185, plan doc:4,10, HA-STRATEGY:4,507,528. COM

### F14 MD-18 — Machine-specific file:///Volumes links are a pre-existing convention in .handoff docs
status=unknown cat=cleanup prio=P3 conf=medium act=False [V:confirmed]
REMAINING: Tolerate for now (consistency with the rest of the file), but a repo-wide sed to relative links (`./REVIEW-PACKET-…`) would make the handoff index portable; not urgent for the 'finish current features' priority.
EVID: MASTER-TODO.md lines 32, 52-62, 79-87, 103, 121 etc. already use file:///Volumes/4TB-BAD/Halbert/… links on committed main; the new Rust-section link and the semantic-audit doc follow the same pattern. Only the ~/.claude (PAUSE-STATE:25) and ~/.gemini (semantic audit:111) links point outside the repo.
VERIFY: confirmed — `git show main:.handoff/MASTER-TODO.md | grep -c 'file:///Volumes'` = 43 on committed main; working tree = 44 (the one new Rust-section link). Added lines of the HA-STRATEGY and plan diffs contain 0 file:/// or /Users/ paths. Paths escaping the repo: PAUSE-STATE:25 (~/.claude workflow script), semantic audit:111 (~/.gemini/antigravity), branch audit:6 (/Volumes/4TB-BAD/Haloysius/.handoff/HANDOFF-E

### F15 ROUTE-01 — Devices API mounted at /devices but frontend and tests use /api/devices — Settings > Devices tab is dead in the real app
status=in_progress cat=bug prio=P0 conf=high act=True
REMAINING: One-line fix: add prefix="/api" at app.py:306 (matches the G12 handoff table and the test fixture). Then add an app-level test that hits /api/devices through create_app() rather than a hand-built FastAPI() so the mount prefix is covered. Introduced by 922122b2 / 5ab70760 (2026-08-31).
EVID: halbert_core/halbert_core/dashboard/app.py:306 `app.include_router(devices.router, tags=["devices"])` (no prefix); routes/devices.py:53 `router = APIRouter()` and :203 `@router.get("/devices")`; runtime route table from create_app() lists '/devices', '/devices/entity-mode', '/devices/body-name', '/devices/{node_id}/capabilities', '/devices/{node_id}/discover', '/devices/{node_id}/wol', '/devices/p
DOC: .handoff/HANDOFF-G12-DEVICES-PAGE-DESIGN-REVIEW-2026-08-31.md:28-44 documents the endpoints as /api/devices/*; the code serves /devices/*.

### F15 ROUTE-02 — Settings > Identity & Voice persona calls are double-prefixed (/api/api/persona/*) — list/create/activate/delete all 404
status=in_progress cat=bug prio=P1 conf=high act=True
REMAINING: Change the four fetches to `${API_BASE}/persona/...` (or use apiUrl('/api/persona/...')). Add a BeingTab vitest that asserts the fetched URL.
EVID: components/settings/tabs/BeingTab.tsx:21 `const API_BASE = apiUrl('/api')` then :59 `${API_BASE}/api/persona/list`, :73 `${API_BASE}/api/persona`, :92 `${API_BASE}/api/persona/${id}/activate`, :108 `${API_BASE}/api/persona/${id}` (DELETE). Backend routes/persona.py:52 `APIRouter(prefix="/api/persona")` mounted with no extra prefix (app.py:290) — real paths are /api/persona/*. Introduced by bacbfa6

### F15 ROUTE-03 — Audio quiet-hours reads/writes /api/being, which does not exist (route is /api/settings/being)
status=in_progress cat=bug prio=P1 conf=high act=True
REMAINING: Point both calls at /api/settings/being and add a test. Verify the POST body shape ({quiet_hours}) matches what settings.py:3070 accepts.
EVID: components/audio/AudioSettings.tsx:73 `fetch(apiUrl('/api/being'))` and :108 POST to the same path. routes/being.py only defines /being/events, /being/events/{id}/snooze, /being/events/{id}/dismiss, /being/events/recent (being.py:33,143,162,180); the config endpoints are /api/settings/being GET/POST (settings.py:3052,3070). Runtime route table confirms no '/api/being' path. Both fetches swallow th

### F15 FEAT-01 — "Why Brain" feature documented as available has no backend and is not mounted on any discovery card
status=not_started cat=incomplete_feature prio=P2 conf=high act=True
REMAINING: Decide: either back saveWhy with /api/settings/knowledge/explain-config (already exists, settings.py:1571) and mount WhyBrain on discovery cards, or delete why-brain.tsx/why-overlay.tsx/saveWhy and the FEATURES.md section.
EVID: documentation/FEATURES.md:208-223 claims WhyBrain/WhyOverlay on 'any discovery card' saved to self-knowledge. lib/api.ts:337-345 saveWhy() POSTs '/api/why' with an in-code NOTE: 'no backend endpoint exists for this yet (verified 2026-08-22)'. Route inventory (320 decorators) and runtime table contain no /why. WhyBrain is imported only by components/ComponentLibraryViewer.tsx:34 (the Settings compo
DOC: FEATURES.md 'Why Brain UI' section describes a shipped feature; it is a demo-only component with no persistence.

### F15 FEAT-02 — Backups page 'Run' action is an alert() placeholder
status=not_started cat=incomplete_feature prio=P2 conf=high act=True
REMAINING: Either implement a gated run-backup route (Timeshift/Borg/rsync via the approval flow) or remove the Run button until it exists.
EVID: pages/Backups.tsx:168-170 `} else if (action === 'run') { // TODO: Implement run backup\n alert(`Would run backup: ${backup.name}`) }`. No backend route to trigger a backup exists (discovery.py exposes only /api/discoveries/backup/{name}/history, /backup/statuses, /backup/{name}/logs).

### F15 FEAT-03 — Home cognitive loop decides nothing and is never instantiated outside tests
status=in_progress cat=incomplete_feature prio=P2 conf=high act=True
REMAINING: Decide whether the autonomous home tick is in scope for the 'finish current features' push; if yes, wire it into cognition_wiring/app lifespan behind CAP_HA_CONNECTION and give _decide at least the occupancy heuristic it references; if no, mark it experimental in docs.
EVID: home/cognitive_loop.py:296-317 `_decide()` — comments 'For now, this is a placeholder that demonstrates the pattern' and unconditionally `return actions` (empty). `grep -rn 'HomeCognitiveLoop(' halbert_core/halbert_core` → no callers; only exported from home/__init__.py:12. tests/test_cognitive_loop.py exists, so the class is tested but unwired.

### F15 FEAT-04 — Federation (Phase 9) is a NotImplementedError scaffold: fleet proxy, telemetry agent, compute broker, peer discovery, compute endpoint, peer streaming
status=in_progress cat=deferred prio=P2 conf=high act=False
REMAINING: Nothing for the current-features push; keep deferred. But see FED-01/FED-02 for the pieces that are reachable from the UI today.
EVID: ~90 TODO(federation-9.x) markers. Raising NotImplementedError today: federation/fleet_proxy.py:115,124,134,143,177; telemetry_agent.py:181,197,210,218,227; compute_broker.py:166,202,218; peer_discovery.py:191,198,250,257; compute_endpoint.py:265; compute_router.py:683 (replay_deferred); model/client.py:508-509 (peer streaming 'not supported yet'); dashboard/routes/fleet.py:142,154,176,186,199 (GET

### F15 FED-01 — Fleet cockpit UI shows 'TODO(federation-9.9)' text and its five backend routes return 500 — component is never mounted, so only /api/fleet/nodes is live
status=in_progress cat=incomplete_feature prio=P3 conf=high act=True
REMAINING: Either hide the fleet API and components until 9.9, or mount nothing and delete the dead component + peerApi fleet helpers to shrink the surface.
EVID: components/fleet/NodeFleetCockpit.tsx:361-369 renders literal 'MCP tool picker and log viewer — TODO(federation-9.9)'; :57-61 status TODO. `grep -rn NodeFleetCockpit src` → referenced only in comments of PeerPairingModal.tsx:13 and DiscoveredPeerCard.tsx:6; no page or tab renders it. lib/peerApi.ts still exports getFleetNodes/getNodeInfo/... calling /api/fleet/*; routes/fleet.py:120 hard-codes `on

### F15 FED-02 — Peer pairing UI: manual pairing throws by design; discovered-peer pairing auto-verifies the PIN ('development mode')
status=in_progress cat=security prio=P2 conf=high act=True
REMAINING: Before any peer-pairing surface is exposed as 'done': require the human PIN confirmation step (remove the auto-verify), decide on admin auth for /api/peers/*, and persist pending pairings. If pairing is deferred, hide the 'Add device' path that reaches DiscoveredPeerCard.
EVID: components/fleet/PeerPairingModal.tsx:161-170 `throw new Error('Manual pairing flow — TODO(federation-9.1)')` on submit. components/fleet/DiscoveredPeerCard.tsx:57-64 'The PIN needs to be confirmed by the user on the Desktop UI. For now, auto-verify (development mode)' → calls verifyPairing({pin: resp.pin}) immediately with the PIN returned by /api/peers/pair. routes/peers.py:73 pending pairings i

### F15 STUB-01 — tier_router OpenAI branch raises NotImplementedError although 'openai' is chat-capable in model/client.py
status=unknown cat=bug prio=P2 conf=medium act=True
REMAINING: Trace which code path the dashboard chat uses for an 'openai'/'llamacpp' slot; if tier_router is on that path, a picker-selectable provider crashes at first turn. If tier_router is legacy, delete the stub branches.
EVID: model/tier_router.py:381-383 `elif model.provider == ProviderType.OPENAI ...: raise NotImplementedError("OpenAI provider not yet implemented")`. model/client.py:75-77 CHAT_CAPABLE_PROVIDERS = {ollama, llamacpp, mlx, anthropic, peer} | OPENAI_COMPATIBLE_PROVIDERS. model/providers/llamacpp.py:70,92 also raise NotImplementedError. Whether the agent's chat path goes through tier_router (vs. model/clie

### F15 STUB-02 — runtime/ package is a placeholder graph with no importers
status=obsolete cat=cleanup prio=P3 conf=high act=True
REMAINING: Delete halbert_core/runtime/ (agents/state_machine.py is the real orchestrator).
EVID: runtime/engine.py:9 'Minimal runtime Engine to wire the placeholder graph and state'; runtime/graph.py:9 'Real orchestration will be implemented (e.g., LangGraph). This stub allows local tests.' `grep -rn 'runtime' --include=*.py` outside runtime/ → no imports.

### F15 STUB-03 — Approval engine 'dashboard' mode auto-rejects — dead path, but misleading
status=obsolete cat=cleanup prio=P3 conf=high act=True
REMAINING: Remove the 'dashboard' mode branch or make it delegate to queue_request; update the docstring so nobody wires it by mistake.
EVID: approval/engine.py:279-301 `_prompt_dashboard` logs 'Dashboard approval not yet implemented (Phase 3 M5). Auto-rejecting for safety.' Reached only via request_approval(mode='dashboard') (engine.py:166); the only request_approval caller is engine.py:106 with mode='cli'. Real dashboard flow is queue_request (approvals.py:153, settings.py:3012, findings/proposal_generator.py:197) + /api/approvals/{id
DOC: FEATURES.md:453-459 'Approval Workflow' is accurate for the queue path; the engine's own comment claims dashboard approval is unimplemented, which is stale.

### F15 STUB-04 — Smaller live stubs a user can notice: audio ingress 'running' always false; context_loaded token count always 0; persona history is a one-row stub; ConfigEditor session never records chat; rag/llm stream unimplemented
status=in_progress cat=incomplete_feature prio=P3 conf=high act=True
REMAINING: Each is a 1–2 hour fix or a delete; none blocks a release but they contradict UI labels (context chips report 0 tokens).
EVID: dashboard/routes/audio.py:275 `"running": False,  # TODO: read from pipeline` (GET /api/audio/ingress/status, no FE consumer); agents/state_machine.py:2224 `0  # TODO: token count` in StreamEvent.context_loaded (consumed by hooks/useAgentStream.ts:629); persona/manager.py:279 'TODO: Implement full history tracking'; ConfigEditor.tsx:286 `chat_history: [], // TODO: integrate with chat`; rag/llm.py:

### F15 ORPHAN-01 — Frontend pages Jobs.tsx and Memory.tsx are not routed or imported anywhere
status=obsolete cat=cleanup prio=P3 conf=high act=True
REMAINING: Delete both pages (Settings > Knowledge already covers memory collections via /api/memory/collections) or route them; delete /api/jobs if the Settings scheduler endpoints (settings.py:2917-2961) are the kept API.
EVID: pages/Jobs.tsx:20 `export function Jobs()`, pages/Memory.tsx:37 `export function Memory()`; App.tsx:119-147 has no /jobs or /memory route; `grep -rn 'pages/Jobs\|pages/Memory' src` → nothing. Their backend counterparts /api/jobs (jobs.py:13,69,103) and /api/memory/* CRUD (memory.py:252-344) are consequently unconsumed too.

### F15 ORPHAN-02 — Frigate NVR: 8 backend routes + a backend-served /frigate SPA route with zero frontend code
status=obsolete cat=decision prio=P3 conf=high act=True
REMAINING: Decide keep-or-cut. If keep, build the panel (or fold cameras into Home) and add a React route; if cut, remove router + SPA route.
EVID: routes/frigate.py:50-214 (status/config/cameras/events/reviews/snapshot/latest); app.py:303 mounts it 'Frigate NVR panel'; app.py:366-371 serves index.html for GET /frigate. `grep -rli frigate src` → no files; App.tsx has no /frigate route and no catch-all, so /frigate renders an empty <Routes>. tests: test_frigate.py exists (client), 0 route tests.

### F15 ORPHAN-03 — 143 of 316 HTTP routes have no frontend consumer (backend-only surface)
status=in_progress cat=cleanup prio=P2 conf=high act=True
REMAINING: Triage per router: keep-and-test (MCP/agent tools may use some, e.g. web_search, knowledge), wire a UI (anomaly/recovery/simulate are advertised in FEATURES.md), or delete. Scratch list at scratchpad/agents/ws-features-vs-code-stubs/routes.txt.
EVID: Programmatic match of routes.txt (from app.py includes + @router decorators) against every '/api|/llm|/compute|/devices' literal and ${API_BASE} concatenation in frontend/src (tests excluded). Unconsumed by module: settings 41 (ingestion 3, docs reset/query 2, knowledge graph+hierarchical+reflect 15, anomaly 2, recovery 4, simulate 4, personality 5, prompts, computer-name, model/install, system-pr

### F15 ORPHAN-04 — Two parallel approval APIs; the UI straddles both
status=in_progress cat=cleanup prio=P3 conf=high act=True
REMAINING: Collapse to one router; keep the AI-rules conflict check on the decide path.
EVID: routes/approvals.py (GET /api/approvals, /history, /proposals, /{id}, POST /{id}/approve|reject) constructs `ApprovalEngine()` per call (approvals.py:69,101,237,316); routes/settings.py has GET /api/settings/approvals/pending|history and POST /{id}/decide via the singleton get_approval_engine() (settings.py:2054-2059,2133,2190,2208). lib/tauri.ts:133-151 lists via /api/settings/approvals/pending, 

### F15 NAV-01 — Seven documented dashboard pages are routed but hidden from navigation (URL-only)
status=in_progress cat=decision prio=P3 conf=high act=True
REMAINING: Either re-expose them (compute/homelab sub-views + approvals badge as the comment plans) or mark them hidden/experimental in FEATURES.md.
EVID: components/Layout.tsx:64-66 comment: 'Pages that fall outside these domains — Apps, Network, Sharing, Containers, GPU, Development, Approvals — stay routed but leave the rail. They are slated for future sub-views'. navSections (Layout.tsx:70-92) lists only Dashboard, Home, Findings, Services, Storage, Backups, Terminal. App.tsx:123-134 still routes all seven. FEATURES.md:17-113 lists them as first

### F15 DOC-01 — FEATURES.md 'Backend API' table lists endpoints that do not exist
status=obsolete cat=doc_only prio=P2 conf=high act=True
REMAINING: Rewrite the table from routes.txt; drop the 'Chat Request Fields' block (fields belong to the agent message API now).
EVID: FEATURES.md:351-362 lists /api/chat/send, /api/chat/config, /api/discovery/{type}, /api/settings/endpoints, /api/settings/assign/{role}, /api/terminal/execute, /api/services/{action}; :182 /api/chat/memory/stats|query. None appear in the 320-decorator route inventory or the runtime table. Real equivalents: POST /api/agent/message (agent.py:1430), GET /api/discoveries/ (discovery.py:43), GET/PUT /l
DOC: Documented endpoints vs actual: 8 of 10 rows wrong.

### F15 DOC-02 — FEATURES.md scanner table names files that do not exist; GPU/Development/Containers are route modules, not scanners
status=obsolete cat=doc_only prio=P3 conf=high act=True
REMAINING: Regenerate the table from engine.py; add the macOS scanner set.
EVID: FEATURES.md:330-343 lists disk_usage.py, network.py, services.py, sharing.py, backup.py, security.py, gpu.py, containers.py, development.py, flatpak.py, snap.py, appimage.py. discovery/scanners/ actually has service.py, container.py, storage.py, package.py, apps/{flatpak,snap,appimage}.py, macos/* and no gpu.py/development.py; engine.py:107-126 registers Backup, Service, Storage, Network, Security

### F15 DOC-03 — FEATURES.md Settings/Chat/Terminal/Debug descriptions describe a UI that no longer exists
status=obsolete cat=doc_only prio=P3 conf=high act=True
REMAINING: Rewrite those sections against Settings.tsx and Layout.tsx.
EVID: FEATURES.md:114-135 'AI Models / AI Rules / Data Scan' tabs vs pages/Settings.tsx:76-113 actual tabs (Identity & Voice, Devices, Models & Providers, Knowledge, Tool Permissions, Alert Rules, Trust Boundary, Vision, Audio & Voice, System Info, About, Debug). :141-147 'AI Assistant (Sidebar)… Conversation History: Persistent conversations with search' vs one continuous timeline (/api/agent/timeline,

### F15 DOC-04 — FEATURES.md advertises Anomaly Detection, Recovery Playbooks and Dry-run Simulation as available — backend-only, no UI, no tests
status=in_progress cat=incomplete_feature prio=P2 conf=high act=True
REMAINING: Either build the Settings surfaces (or surface via the agent's tools) and add route tests, or move these sections to a 'backend-only / experimental' heading.
EVID: FEATURES.md:426-451. Backend routes exist (settings.py:2544 anomaly/status, :2571 anomaly/check, :2628-2695 recovery/*, :2733-2840 simulate/*) but none is called from frontend/src (ORPHAN-03 list) and `grep -rl '/api/settings/anomaly\|recovery\|simulate' tests/` → 0 files. Also /api/settings/ingestion/* (FEATURES.md:234) and /api/settings/docs/index|query (:263-266) have no FE caller and 0 tests.

### F15 TEST-01 — 18 of 35 dashboard route modules have zero backend tests
status=not_started cat=test_gap prio=P1 conf=high act=True
REMAINING: Prioritise TestClient tests through create_app() (not hand-built apps — see ROUTE-01) for the routes the UI actually calls: services control, editor file/backup, containers, gpu, development, alerts/rules, legal, storage/chromadb, rag, persona, being/events, approvals approve/reject.
EVID: Two greps over halbert_core/tests (by module name 'routes.<name>' and by URL prefix) both return 0 for: alerts, approvals, being, containers, development, downloads, editor, fleet, frigate, jobs, legal, persona, rag, services, storage, vision, web_search (discovery: 0 by module, 1 by URL). settings.py sub-areas with 0 tests by URL: knowledge, ai-rules, policy, anomaly, recovery, simulate, schedule

### F15 TEST-02 — Discovery scanners the FEATURES.md relies on are largely untested
status=not_started cat=test_gap prio=P2 conf=medium act=True
REMAINING: Fixture-based scanner tests (canned command output → Discovery objects) for the Linux set and the macOS set, since 'macOS Beta' is a stated platform.
EVID: grep of tests/ for scanner module names: disk_usage 0, service 0, sharing 0, container 0, apps/flatpak 0, apps/appimage 0, storage (n/a), network 5 (mostly HA/network tests, not the scanner), backup 2, security 1, snap 2. The macOS scanner set (discovery/scanners/macos/*, 9 scanners) has no dedicated tests found by name.

### F15 TEST-03 — 13 of 16 frontend pages have no vitest coverage
status=not_started cat=test_gap prio=P2 conf=high act=True
REMAINING: At minimum, smoke-render each routed page with fetch mocked and assert the URLs it calls (that alone would have caught ROUTE-02 and ROUTE-03).
EVID: 65 test files under frontend/src; page-level tests exist only for Settings.tabs, VoiceHud, VoiceMode. No tests for Dashboard, Services, Storage, Backups, Findings, Home, Terminal, Apps, Network, Sharing, Containers, GPU, Development, Approvals. Component coverage is concentrated in agent/, voice/, llm/, shell/ (all recent work).

### F15 CAP-01 — CAP_SOURCEPREP probes `import sourceprep` but the adapter talks to a daemon over HTTP — retrieval silently disabled on this dev box
status=in_progress cat=bug prio=P1 conf=medium act=True
REMAINING: Change the probe to a config/presence check (daemon URL configured, or the sourceprep_client's token/URL present) instead of importability; add a test that the probe is True when only the daemon is configured. Confirm whether any deployment actually pip-installs 'sourceprep'.
EVID: capabilities.py:146-163 `_probe_sourceprep` = importlib.import_module('sourceprep') (docstring admits 'deliberately coarse proxy'). `arch -arm64 .venv/bin/python -c 'import sourceprep'` → ModuleNotFoundError. Registry probe on this machine: {'sourceprep': False, ...}. Consumers gate on it: context/adapters.py:432-434 returns None (no SourcePrepAdapter), dashboard/routes/agent.py:149, integrations/

### F15 CAP-02 — CAP_LOCAL_LLM is probed but has no consumer
status=in_progress cat=cleanup prio=P3 conf=high act=True
REMAINING: Either gate something on it (e.g. the local-tier fallback in compute_router) or drop it from ALL_CAPABILITIES.
EVID: capabilities.py:166-189 `_probe_local_llm` and _PROBES entry at :231; `grep -rn 'CAP_LOCAL_LLM\|has_capability("local_llm")'` outside capabilities.py and tests → nothing. All other capabilities have consumers (app.py:432,456,477,601,622,639,655,722; llm.py:212-219; agent.py:148-149,510-511; adapters.py:432; cognition_wiring.py:299-300; auto_provision.py:74-75; config_wizard.py:144-145,269-270,494-

### F15 FEAT-05 — FEATURES.md 'Multi-Session & Remote Host Management' and 'Configuration as Physiology' are correctly marked planned; InstanceSwitch is the only shipped piece
status=not_started cat=deferred prio=P3 conf=medium act=False
REMAINING: Keep deferred; consistent with founder direction.
EVID: FEATURES.md:506-527 carry the 📋 marker. components/shell/InstanceSwitch.tsx + lib/apiBase.ts:21-31 setInstanceEndpoint() implement endpoint switching; /api/instance/info (instance.py:18) is consumed. Remote tool execution/streaming depend on the federation scaffolds in FEAT-04.

### F16 RNC-01 — Branch inventory: 5-crate workspace, only halbert-mqtt has an implementation
status=in_progress cat=deferred prio=P3 conf=high act=False
REMAINING: Against the amended plan: R0.1 rust-toolchain.toml (absent on branch: git ls-tree feat/rust-native-core -- crates/rust-toolchain.toml → nothing), R0.7 CI job (none), R0.9/R0.10 Docker track, R1.3–R1.9, R2–R7 entirely. 9 of 72 tasks have any code (R0.1–R0.6, R0.8, R1.1, R1.2).
EVID: git diff --stat main...feat/rust-native-core: 15 files, +2597 (Cargo.lock 1023, halbert-mqtt/src/lib.rs 455, sandbox 160, telemetry 134, snapshots 129, ffi 50, README 134, REVIEW-REQUEST doc 382). crates/Cargo.toml members = halbert-mqtt, -telemetry, -snapshots, -sandbox, -ffi; default-members exclude halbert-ffi (needs maturin). grep TODO|FIXME|todo!|unimplemented! over all crate files on the bra
DOC: Untracked .handoff/HANDOFF-BRANCH-AND-WORKTREE-AUDIT-2026-09-01.md:38 says '70 of 72 planned tasks are untouched' — actually 9 tasks have code (63 untouched), though its 'leave as is' conclusion is right.

### F16 RNC-02 — halbert-mqtt is a real rumqttc client but shallow: no broker test, cache unwired, no reconnect backoff
status=in_progress cat=incomplete_feature prio=P3 conf=medium act=False [V:adjusted]
REMAINING: Per amended plan R1.1: exponential backoff + jitter (1s→60s cap, stop after N auth failures) and make the event-loop task exit on disconnect; R1.2: wire incoming Publish events into the cache, retained-message replay on subscribe, LWT offline marking; R1.9: integration test against an authenticated Mosquitto container. connect() also returns Ok without awaiting ConnAck, and `connected` flips true on any non-Publish Ok event including Outgoing ones.
EVID: crates/halbert-mqtt/src/lib.rs (branch): RumqttClient::connect (l.206–273) builds MqttOptions, spawns tokio task polling event_loop; on Err it only logs warn and loops immediately (l.261–266, comment claims 'set_auto_reconnect(true)' which is never called); disconnect() (l.320–330) drops the AsyncClient but the spawned task keeps polling — rumqttc returns Err on every poll once requests are done, 
DOC: Branch REVIEW-REQUEST doc l.133/l.312 and commit ec1518c1 call R1.1+R1.2 'DONE'; even the original committed plan wording (HEAD plan l.131–132: 'auto-reconnect', 'retained message handling, last-will processing') is not met, and the amended plan rows (working plan l.600–601) still say 'Pending' for 
VERIFY: adjusted — Re-read crates/halbert-mqtt/src/lib.rs from the branch (git show feat/rust-native-core:…, 455 lines). Every line reference checks out: connect() l.206–273 returns Ok(()) at l.272 without awaiting ConnAck; the spawned task's Err arm l.261–266 only warns and loops (no sleep/backoff); `Ok(_)` at l.257–260 sets connected=true for ANY non-Publish event including Event::Outgoing; disconnect() l.320–330 
  CORRECTED_REMAINING: Per amended plan R1.1 (plan l.600): exponential backoff + jitter (1s→60s, stop after N auth failures) with a sleep in the Err arm; make disconnect() call AsyncClient::disconnect() (rumqttc client.rs:217) and make the event-loop task exit (break on RequestsDone / a shutdown flag) instead of drop-and-

### F16 RNC-03 — halbert-ffi is a PyO3 skeleton only; unused workspace dep pyo3-asyncio 0.22 is a latent resolve trap
status=not_started cat=incomplete_feature prio=P3 conf=medium act=False [V:adjusted]
REMAINING: R4a: expose halbert_rs.mqtt; the async bridge (R4.3) will need pyo3-async-runtimes (pyo3-asyncio stopped at 0.20 and was superseded), so the 0.22 workspace entry should be corrected before first use.
EVID: crates/halbert-ffi/src/lib.rs l.26–36: #[pymodule] halbert_rs adds only __version__ and UnsupportedError ('Sub-modules will be registered here in R4.2-R4.5'). crates/Cargo.toml [workspace.dependencies] declares pyo3-asyncio = 0.22 but no member references it; Cargo.lock has no pyo3-asyncio entry (grep → absent). No halbert_rs cdylib in target/ (only pyo3_ffi/pyo3_build_config rlibs) — never built 
VERIFY: adjusted — Confirmed the skeleton: crates/halbert-ffi/src/lib.rs is 50 lines; #[pymodule] halbert_rs (l.26–36) adds only __version__ and UnsupportedError ('Sub-modules will be registered here in R4.2-R4.5'). Confirmed the dependency trap: crates/Cargo.toml [workspace.dependencies] has `pyo3-asyncio = { version = "0.22", features = ["tokio-runtime"] }`; no member Cargo.toml references it; `git show feat/rust-
  CORRECTED_REMAINING: Before R4a: add crates/halbert-ffi/build.rs calling pyo3_build_config::add_extension_module_link_args() (plus `pyo3-build-config` as a build-dependency) or build only via maturin and drop halbert-ffi from `--workspace` CI commands on macOS; replace the workspace `pyo3-asyncio = 0.22` entry with pyo3 corrected_status=not_started (module content) — but the R0.6 skeleton is broken on macOS: link fails with plain cargo

### F16 RNC-06 — REVIEW-REQUEST-RUST-NATIVE-CORE-2026-08-31.md: branch and main hold two DIFFERENT documents under the same path
status=blocked cat=decision prio=P1 conf=high act=True [V:confirmed]
REMAINING: Founder decision before committing main's docs: (a) commit main's copy under its current name (keeps 7 cross-references intact) and, at eventual branch merge, drop/rename the branch's file (e.g. REVIEW-REQUEST-RUST-NATIVE-CORE-EXTERNAL-2026-08-31.md); or (b) rename main's copy now and fix the 7 references. (a) is less work.
EVID: diff <(git show feat/rust-native-core:.handoff/REVIEW-REQUEST-RUST-NATIVE-CORE-2026-08-31.md) /Volumes/4TB-BAD/Halbert/.handoff/REVIEW-REQUEST-RUST-NATIVE-CORE-2026-08-31.md → 592 changed lines. Branch version (382 lines, commit cc19695d 2026-08-31 23:30): 'External Review Request: Rust Native Core Architecture & Implementation Plan' — 7 questions, §8 'Current Blocker: R2.1'. Main's untracked vers
DOC: PAUSE-STATE l.11 describes the review doc as 'landed' on main, but the branch already committed an unrelated file at that path.
VERIFY: confirmed — Re-ran: `git show feat/rust-native-core:.handoff/REVIEW-REQUEST-RUST-NATIVE-CORE-2026-08-31.md` = 382 lines, title 'External Review Request: Rust Native Core Architecture & Implementation Plan', sections §1–§9 incl. '## 8. Current Blocker' (R2.1, l.310–323), committed cc19695d 2026-08-31 23:30. Main's file at the same path: untracked (`git ls-files --error-unmatch` → pathspec error; status `??`), 

### F16 RNC-07 — Plan doc uncommitted edit (426→2,640 lines) is finished and ready to commit
status=done cat=needs_commit prio=P1 conf=high act=True [V:confirmed]
REMAINING: Commit on main (pathspec the .handoff files only — do not sweep in the other session's design-system/HalbertMark and assets/brand changes).
EVID: git diff --stat: .handoff/RUST-NATIVE-CORE-TODO-AND-IMPLEMENTATION-PLAN-2026-08-31.md 2552 +-; 56 hunks; wc -l 2640 (HEAD: 426); mtime Sep 1 10:27. Header l.4: 'edits landed 2026-09-01 … 72 tasks across 8 phases'. Added headings include R0.9/R0.10 implementation notes, §4.1–4.9 (R1), §5.1–5.7 (R2), §6.1–6.7 (R3), §7.1–7.11 (R4 waves R4a/b/c), §8.1–8.7 (R5 one-MCP-surface), §9.1–9.6 (R6 revised com
DOC: Every R0/R1 row still reads 'Pending' although the branch has R0.1–R0.6/R0.8 scaffolded and R1.1/R1.2 partially built (see RNC-02); consider a one-line 'branch state' note when committing.
VERIFY: confirmed — Re-ran all numbers: `git diff --stat` → RUST-NATIVE-CORE-TODO-AND-IMPLEMENTATION-PLAN-2026-08-31.md 2552 +-; HEAD 426 lines, working tree 2640, branch copy 426 (`git diff --stat main feat/rust-native-core -- <plan>` → empty, so committing on main cannot conflict with the branch); mtime Sep 1 10:27:07; hunk count is 8 with default context and 56 with -U0 (the finder's 56 is the -U0 count — immateri
  CORRECTED_REMAINING: Commit on main with a pathspec limited to the five .handoff files (do not sweep in the other session's HalbertMark/brand-asset changes). Optionally, in a later edit, mark R0.2–R0.6/R0.8 'Done on feat/rust-native-core' and R1.1/R1.2 'Partial on branch' so the plan reflects the parked code.

### F16 RNC-08 — Scoping doc uncommitted edit is finished and ready to commit
status=done cat=needs_commit prio=P1 conf=high act=True [V:confirmed]
REMAINING: Commit together with RNC-07.
EVID: git diff .handoff/HA-STRATEGY-SCOPING-AND-DEPLOYMENT-PATHS-2026-08-31.md: 165 +- across 8 hunks — status line amended (F2/F6/F13/RB), HACS→Supervisor add-on repository wording, new 'Agent container image' row, Path 3 'already runs in Docker' struck with explicit correction, §7 compose template hardened (bridge network, loopback-only authenticated Mosquitto, HA alone on host networking, optional ha
VERIFY: confirmed — `git diff --stat` → HA-STRATEGY-SCOPING-AND-DEPLOYMENT-PATHS-2026-08-31.md 165 +-; I count 9 hunks (@@ at l.1, 27, 76, 94, 206, 215, 350, 430, 440 — finder said 8; immaterial). Content verified by reading the +/- lines: status line 'amended 2026-09-01 (F2/F6/F13 and RB applied)', HACS→'Supervisor add-on repository' wording in three places, new 'Agent container image' row (R0.9/R0.10, ghcr.io/ericb

### F16 RNC-09 — MASTER-TODO uncommitted diff touches ONLY the Rust Native Core subsection
status=done cat=needs_commit prio=P1 conf=high act=True [V:confirmed]
REMAINING: Commit with RNC-07/08. Note: the halbert-mcp worktree carries an unrelated, older (dated 2026-08-30) 232-line MASTER-TODO rewrite of lines 1–136 that predates the Rust section; if that is ever committed it will conflict with this hunk's context — not blocking now.
EVID: git diff .handoff/MASTER-TODO.md: exactly one hunk @@ -165,23 +165,25 @@ — heading '(… augmented 2026-08-31, edits landed 2026-09-01)', 56→72 tasks, phase summary rows R0–R6 rewritten (R0.9/R0.10, waves R4a/b/c), 'Recommended start' paragraph, new 'Review applied 2026-08-31' paragraph linking the review doc, D7 deferral line gains Z-Wave JS note. No other section touched.
VERIFY: confirmed — `git diff -- .handoff/MASTER-TODO.md` → exactly one hunk `@@ -165,23 +165,25 @@`, entirely inside '### Rust Native Core & HalbertOS': heading gains 'augmented 2026-08-31, edits landed 2026-09-01'; 56→72 tasks; phase rows R0–R6 rewritten (R0.9/R0.10 Docker track, waves R4a/b/c, R5 'one external MCP surface', R6 registry image); 'Recommended start' paragraph rewritten; new 'Review applied 2026-08-31

### F16 RNC-10 — PAUSE-STATE doc (untracked) is a finished historical record, ready to commit
status=done cat=needs_commit prio=P2 conf=high act=True [V:confirmed]
REMAINING: Commit with the other four docs.
EVID: .handoff/PAUSE-STATE-RUST-ROADMAP-AUGMENTATION-2026-08-31.md (61 lines, mtime Sep 1 08:18): header 'RESUMED AND COMPLETED 2026-09-01 … 72 tasks / 8 phases, ~2,640 lines' — matches the working plan doc (2,640 lines, 72 IDs). Its 'Remaining after resume' items 1–3 are all reflected in RNC-07/08/09 diffs. References a workflow script under another session's ~/.claude/projects dir (informational only)
DOC: Header says the workflow resumed '17/17 agents' but the body lists 7+7+1=15 agents — cosmetic.
VERIFY: confirmed — Read .handoff/PAUSE-STATE-RUST-ROADMAP-AUGMENTATION-2026-08-31.md in full: 61 lines, untracked (`??`), mtime Sep 1 08:18:20. Header l.3–7 'RESUMED AND COMPLETED 2026-09-01 … 72 tasks / 8 phases, ~2,640 lines' matches the working plan doc (wc -l 2640, 72 IDs). Its 'Remaining after resume' items 1–3 (l.32–44) correspond exactly to the RNC-07/08/09 diffs. The referenced workflow script still exists (

### F16 RNC-11 — Branch merges cleanly today; recommend leaving it parked and unmerged per founder deferral
status=blocked cat=deferred prio=P2 conf=high act=True [V:adjusted]
REMAINING: Decision: keep unmerged (recommended — additive, no consumer, no CI, founder deferred). If the founder prefers to merge to avoid the RNC-06 conflict, merge only after resolving the doc-name collision and accept that crates/ is CI-unenforced until R0.7.
EVID: git merge-tree --write-tree main feat/rust-native-core → 1349aa826ccc6e97856bce435cc0de24ddee5866, exit 0 (no conflicts). Worktree status --porcelain: clean (only ignored crates/target/, 757 MB of build artefacts). Branch is 43 behind / 3 ahead. No CI job on main builds crates/ (ci.yml GATES cover tests/, halbert_core/tests/, frontend, packages only), so merging would land ~2.6k lines of unenforce
VERIFY: adjusted — Re-ran `git merge-tree --write-tree main feat/rust-native-core` → 1349aa826ccc6e97856bce435cc0de24ddee5866, exit 0 (no conflicts). Worktree status --porcelain: empty; only ignored crates/target/ (757 MB). `git rev-list --left-right --count main...feat/rust-native-core` → 43 behind / 3 ahead. `grep -rn cargo|crates/ .github/workflows/` → nothing; ci.yml GATES (l.37–48) cover tests/, halbert_core/te
  CORRECTED_REMAINING: Keep unmerged (recommended). Push the branch to origin as a backup (`git push -u origin feat/rust-native-core` — outside this audit's write limits) so the parked work is not local-only. Resume point is R1.1/R1.2 hardening + R0.6 link fix, then R2.1 per the branch's §8; plan says R2.1's aya recommend

### F16 RNC-12 — Exact resume point: branch says R2.1, amended plan says R0.7/R0.9/R0.10 and R1.3–R1.9 + R4a first; R2.1 is an OPEN reviewer question
status=blocked cat=decision prio=P2 conf=high act=False
REMAINING: When un-parked: (1) R0.1 add rust-toolchain.toml, R0.7 cargo CI job + rust-macos job, R0.9/R0.10 Dockerfile + image CI (zero Rust, could be done independently of the branch); (2) finish R1.1/R1.2 gaps (RNC-02), R1.3–R1.9, wave R4a; (3) decide R2.1 (needs a Linux VM per RD/F11 anyway). Nothing on the branch blocks current-feature work.
EVID: Branch REVIEW-REQUEST §8 (l.310–325): 'completed R0 and R1.1+R1.2 … blocker R2.1 (aya vs libbpf-rs, Opus high) … also need Q1 boundary verdict before R1.3–R1.9'. Main's newer review doc §1: 'The plan is sane … boundary rule sound' (answers the boundary question) and §6 item 2 leaves R2.1 open; working plan l.868: R2.1 '**pending external reviewer confirmation — Q1 (§15) stays open**'; plan 'Recomm
DOC: Branch doc l.148 still says 'HACS add-on' (corrected to Supervisor add-on repository in main's scoping doc).

### F17 SEC-01 — Merge feat/security-review-01 c5b6bb91 — MCP path allowlist for config-query tools (HIGH, unmerged)
status=in_progress cat=security prio=P1 conf=high act=True
REMAINING: Merge feat/security-review-01 into main; resolve the single test_mcp_server.py conflict (keep both appended test classes; the two monkeypatch additions for _load_latest_snapshot in TestTierRouting/TestEgressBoundary are needed once the gate exists). Re-run test_mcp_server.py + test_tier2_guarantee.py. Note the allowlist also fixes the canon-DB pollution mechanism in SEC-06 for the MCP path only — dashboard routes still call get_config_* unguarded.
EVID: git log main..feat/security-review-01 = a09632e1, c5b6bb91, 9e057db7; git cherry main feat/security-review-01 shows all three '+' (not on main by patch-id). Main has no allowlist: grep -iE 'allowlist|not in snapshot' mcp/server.py → nothing. halbert_core/halbert_core/config/queries.py:103-125 _get_current_canon(): 'if live_hash and (not canon_hash or canon_hash != live_hash): canon = parse_config(
DOC: security-review-01 worktree's untracked .handoff/SCOPE-01-DUPLICATE-WORK-RECONCILIATION.md says 'Clean merge, no conflicts' and 'git merge-tree … → 21dae4b7 (clean)' — that was against worktree-central-todo-batches before it merged; against current main it conflicts. Its Step 2/3 cherry-picks (5a132

### F17 SEC-02 — Merge feat/security-review-01 9e057db7 — redactor base64 size/depth caps + nested-JSON leaf redaction (MEDIUM DoS + coverage gap, unmerged)
status=in_progress cat=security prio=P2 conf=high act=True
REMAINING: Lands with the SEC-01 merge (same branch). After merge run test_redaction_gaps.py, test_redact.py, test_mcp_response_boundary.py (branch doc claims 458 security tests green on its base).
EVID: git diff main...feat/security-review-01 -- halbert_core/halbert_core/ingestion/redaction.py: adds _B64_MAX_TOKEN_CHARS=8192, _B64_MAX_DEPTH=2 (redact_text gains _depth, _redact_base64_secrets stops recursing), _NESTED_JSON_WHOLE_MAX=1 MiB, _NESTED_JSON_MAX_DEPTH=8 and _redact_json_leaves() recursive walker; main's _redact_base64_secrets (redaction.py:1298-1330) has no size cap and re-enters redact

### F17 SEC-03 — TASK-03 Task 3.2 — scripts/rebuild_sourceprep_unredacted.py written (all 5 packet steps present), but targets the LEGACY 'halbert-host' project instead of the unified 'halbert' project
status=done cat=decision prio=P2 conf=high act=True
REMAINING: Decide: (a) rewrite step 2 of the script to call SourcePrepSetup().apply(redact_host=False) on the unified 'halbert' project (keep the snapshot + egress-check steps), or (b) accept a second legacy 'halbert-host' project. (a) is consistent with T-H1.1/T-H1.4 and the retirement logic. Caveat to document: boundary-2 of the egress check goes through _tool_get_config_value → load_being_config(); if the host is currently UNLOCKED (secret_tier cloud_ok + acknowledged) the value legitimately crosses with _egress_ack and the script would report a false 'EGREGIOUS' exit 2 — run only while locked, or mak
EVID: scripts/rebuild_sourceprep_unredacted.py (246 lines, commit 5a132654): step1 prep_token auth (:74-86), step2 register_host_project(redact=False) (:217-222), step3 snapshot(registry, redact=False) (:225-231), step4 build triggered via registrar's POST /projects/{id}/trace/build — the packet's POST /api/reindex does not exist (curl GET /api/reindex → 404; daemon openapi lists only /projects/{id}/tra
DOC: TASK-PACKET-03 header 'Only Task 3.2 (rebuild script) remains' and 'test_cli_security.py does not exist yet' are stale — both exist since 5a132654 (2026-08-31). Packet step 4 names POST /api/reindex which the daemon does not expose (script docstring :27-30 already says so).

### F17 SEC-04 — MASTER-TODO 'Rebuild index unredacted (operational gate)' — NOT RUN; only the script exists
status=not_started cat=incomplete_feature prio=P2 conf=high act=True
REMAINING: After SEC-03's decision: from the repo root run `arch -arm64 .venv/bin/python scripts/rebuild_sourceprep_unredacted.py --dry-run`, then the real run while the host is locked; record exit code + the printed report in a handoff and strike the MASTER-TODO line. Also REV-01 §5.3 'live scanner egress testing with mock API keys' remains not done (same open-items list).
EVID: Staging tree ~/.local/share/halbert/sourceprep/host: 40 files, stat ctime of every file = Aug 24 21:33 2026 (e.g. host/etc/hosts, host/etc/ssh/sshd_config) — that predates the write_text()/redact staging code (4408d8a1, 2026-08-26), so no staging run of any kind since Aug 24, let alone redact=False. find ~/.local/share/halbert/sourceprep -newer ~/.config/halbert/prep_token (Aug 29) → no files. Dae
DOC: HANDOFF-CENTRAL-TODO-BATCHES §1 U1 lists the script as delivered (true) but reads as if the gate is closed; it is not — nothing was staged or rebuilt.

### F17 SEC-11 — Real canon DB polluted by test runs — ~/.local/share/halbert/config/{canon,snapshots} contain only pytest tmp paths
status=unknown cat=bug prio=P3 conf=medium act=True
REMAINING: Identify/quarantine the writer (a conftest autouse fixture pointing CANON_DIR/SNAP_DIR/RAW_DIR at tmp_path would close the class of bug); clear the two junk records before running the SEC-04 rebuild so the egress probe scans host data only (the script re-snapshots first, so it is not blocked by this).
EVID: ~/.local/share/halbert/config/snapshots/latest.json (mtime Aug 31 08:07) = [{path: /private/var/folders/…/pytest-of-ericbintner/pytest-2/test_symlink_traversal_blocked0/link.conf, hash: 'x'}, {path: …/real_secret, hash: 2bb80d5…}]; canon/2bb80d5….json has path …/real_secret (1 line); canon/add504f….json (Aug 27) path /var/folders/…/tmp_thohsc5/wg0.conf. Mechanism: config/queries.py:103-125 _get_cu

### F17 SEC-12 — REV-01 / REV-02 fix commits all on main; residual open items
status=in_progress cat=deferred prio=P3 conf=medium act=True
REMAINING: Triage REV-02 P1–P5 (all low) into a follow-up; run REV-01 §5.3 live scanner egress test on the macOS host when SEC-04 is executed. F6 stays deferred with the federation broker stub.
EVID: On main: 74401f12 (F1 canon raw-by-design; snapshot() default redact=False confirmed by signature), 51082f83 (F2+F3), 360effab + 7e9ebaae (F4 flock, F5 HMAC pepper — ~/.local/share/halbert/config/secret_correlations.pepper exists 0600), 0f750c3a (REV-02 F1 phrase gates), cb69442f (F2–F5 transport), d5ce2858 (F6 flagged TODO(federation-9.4)). REVIEW-RESULTS-REV-01 §4 open: §5.3 live scanner egress 

### F17 SEC-13 — Cleanup: feat/security-review-01 worktree has two untracked stale docs; branch/worktree retire after SEC-01/02 merge
status=not_started cat=cleanup prio=P3 conf=high act=True
REMAINING: Discard the stale HA-simplification draft; either commit the reconciliation doc with corrected claims or drop it; after merging the 3 commits, remove the worktree and delete the branch.
EVID: git -C ~/.config/superpowers/worktrees/Halbert/security-review-01 status --porcelain: ?? .handoff/HANDOFF-HOME-AUTOMATION-SIMPLIFICATION-2026-08-30.md (408 lines; main's committed version 1fd6dba1 is 485 lines, 205 diff lines — the worktree copy is an older draft), ?? .handoff/SCOPE-01-DUPLICATE-WORK-RECONCILIATION.md (not on main; its merge plan is stale per SEC-01), plus node_modules. Worktree H

### F17 SEC-14 — Observation: SourcePrep daemon on :8400 answers /projects without a bearer token
status=unknown cat=security prio=P3 conf=low act=True
REMAINING: Confirm whether the running daemon was started with PREP_DAEMON_TOKEN; if not, the token gate the rebuild script relies on is not actually enforced (the script still works either way).
EVID: curl -s http://127.0.0.1:8400/projects with no Authorization header → HTTP 200 (full project list), while ~/.config/halbert/prep_token exists (Aug 29) and prep_token.py:49 says the daemon returns 403 to unauthenticated calls when PREP_DAEMON_TOKEN is set on the daemon side. Daemon process is /Volumes/4TB-BAD/HumanAI/CoDRAG/.venv/bin/prep (PID 89851). Outside Halbert's tree — SourcePrep-side config

### F18 MKT-01 — Marketing website update: founder must answer Q1-Q8 before any build
status=blocked cat=decision prio=P1 conf=high act=True
REMAINING: Founder picks messaging option (A/B/C/D; doc recommends C), thesis-stop change, MCP/persona/pricing/HA-naming/N150/stop-count answers (Q3-Q8); then a messaging brief; then build in marketing/web-v7 (or web-v8).
EVID: .handoff/HANDOFF-MARKETING-WEBSITE-UPDATE-2026-08-31.md header 'Status: DRAFT'; §9 'The website AI should NOT start building until the founder has answered Q1 (messaging option) and Q2 (thesis stop)'; grep -rni 'growth story|messaging option|Option C' FOUNDER-TODO.md .handoff/MASTER-TODO.md TODO.md -> no hits; git log -1 -- marketing/ = 493956ab 2026-08-29 (no marketing commits after the handoff w

### F18 MKT-02 — New home/voice/bridge/dotfile stops and their plates are not started
status=not_started cat=incomplete_feature prio=P2 conf=high act=True
REMAINING: Depends on MKT-01. Up to 7 new stops + 8 new plates (HA entity grid, Frigate timeline, waveform, speaker card, alert/quiet-hours card, two-box topology, MCP graph, PATH tracer) per handoff §5.1; footer line update to 'Linux / macOS / Home Assistant' (stops.jsx:199).
EVID: marketing/web-v7/src/lib/storyboard.js:36-95 has exactly 7 stop ids (open, apex, diagonal, rise, hop, cap, reveal); src/content/stops.jsx:2 imports only ProactiveEventsPlate, VitalsPlate, RationalePlate, KnowledgePlate; grep -rniE 'federat|sovereign|home assistant|hear you|watch the doors|wherever I live' marketing/web-v7/src -> none

### F18 MKT-03 — Early-access form on web-v7 submits nothing (client-side no-op)
status=in_progress cat=bug prio=P1 conf=high act=True
REMAINING: Wire the form to a real sink (Netlify Forms attribute, a serverless endpoint, or a mailing-list API) or remove the success message. Also decide the post-launch CTA split (handoff §8.3).
EVID: marketing/web-v7/src/content/stops.jsx:36-50 EarlyAccessForm onSubmit = `if (email.includes('@')) setDone(true)` then renders 'You're on the list' — no fetch, no action=, no data-netlify; grep 'fetch|netlify|action=|data-netlify|formspree|mailto' in stops.jsx/index.html -> none; marketing/web-v7/netlify.toml has build+headers only, no forms config

### F18 MKT-04 — Honesty flags from 2026-08-25 still unresolved: '16,000 manuals' headline and man-page manifest mismatch
status=not_started cat=decision prio=P2 conf=high act=True
REMAINING: Founder decides whether the headline number changes; fix data/manifest.json linux_man_pages count (or the jsonl) — data bug outside marketing but surfaced here.
EVID: stops.jsx:154 'I know 16,000 manuals by heart.'; HANDOFF-MARKETING-SUITE §3 Round 3: real corpus 24,643 docs / 5,603 man pages; data/manifest.json sources.linux_man_pages.document_count=4368 while `wc -l data/linux/man-pages/man_pages.jsonl` = 142

### F18 MKT-06 — web-v7 has no automated build/test gate; not built during this audit
status=unknown cat=test_gap prio=P3 conf=medium act=True
REMAINING: Add a `vite build` (and Playwright screenshot) job or at least run `npm run build` before the next deploy.
EVID: marketing/web-v7/package.json scripts: dev/build/preview only, no test; dist/ is gitignored; a vite build was not run because it writes into the repo

### F18 DS-03 — Uncommitted design-system HalbertMark work on main (another session) is green and needs a commit by its owner
status=in_progress cat=needs_commit prio=P2 conf=medium act=True
REMAINING: Owning session commits (tine-density mark variants + brand SVGs). Do not touch from this audit.
EVID: git status: M packages/design-system/src/primitives/HalbertMark.tsx (+164), M src/stories/HalbertMark.stories.tsx (+178), M src/test/primitives.test.tsx (+11); 40 untracked assets/brand/halbert-mark-*lines*.svg; with these changes present design-system vitest = 70/70 and tsc clean

### F18 DS-04 — SETTINGS-REDESIGN Phase 1 eliminations mostly done; three dead component files remain and the 'delete personas' item now conflicts with the multi-persona store feature
status=in_progress cat=cleanup prio=P3 conf=high act=True
REMAINING: Delete the 3 orphan .tsx files; decide whether ChromaDB endpoints in routes/settings.py stay; update SETTINGS-REDESIGN §3.1(3) — the persona UI in BeingTab is the new feature, not the legacy IT-Admin/Casual toggle.
EVID: pages/Settings.tsx = 880 lines (was 2,681); grep halbert_gpu_tweaks src -> none; components/CompressionSettings.tsx, components/domain/ChromaDBSettings.tsx, components/domain/DatasetManager.tsx still exist but are imported by no non-test file (grep -rln -> only themselves); routes/settings.py has no /persona-names routes (only prefs.pop('persona_names') at :1089) but ChromaDB indexing endpoints re
DOC: SETTINGS-REDESIGN §7 Phase 1-4 boxes all unchecked although Settings.tsx is decomposed (commits bacbfa6b..108c17d9) and persona routes are gone.

### F18 DS-05 — Settings master-detail rail DONE (via NavRail); ⌘F search and ?section= deep-links not done
status=in_progress cat=incomplete_feature prio=P3 conf=high act=True
REMAINING: Wire NavRail search into Settings and bind ⌘F (SETTINGS-REDESIGN Phase 2 item 2); optionally rename ?tab= to ?section=. Phase 6 (About in avatar menu / macOS native menu) is superseded — Layout.tsx:474 comment keeps About inside Settings.
EVID: pages/Settings.tsx:687-692 renders <NavRail sections={SETTINGS_SECTIONS}> with 4 groups (Personality & Identity, Intelligence, System & Security, General; 12 tabs incl. devices/audio/debug); deep link is `?tab=` (Settings.tsx:136-141); grep metaKey|searchQuery|search prop in Settings.tsx -> none although NavRail exposes hb-navrail__search (packages/design-system/src/surfaces/NavRail.tsx:96-109); S

### F18 DS-06 — UI-REDESIGN Phase 2 nav consolidation DONE; Approvals top-bar badge and off-rail pages still pending
status=in_progress cat=incomplete_feature prio=P2 conf=high act=True
REMAINING: Approvals badge/drawer in the top bar; Host & Homelab sub-views for Containers/GPU/Development/Network/Sharing/Apps (currently reachable only by URL).
EVID: Layout.tsx:70-96 navSections = 3 sections / 7 items (Dashboard, Home, Findings, Services, Storage, Backups, Terminal) + Settings via gear (commit 91e7b6eb); Layout.tsx:63-66 comment: Apps, Network, Sharing, Containers, GPU, Development, Approvals 'stay routed but leave the rail … slated for future sub-views and a top-bar approvals badge'; pages/Security.tsx removed, pages/Findings.tsx present (REV

### F18 DS-07 — UI-REDESIGN Phase 3 (HA Area Registry cards in Home.tsx) not started
status=not_started cat=incomplete_feature prio=P2 conf=high act=True
REMAINING: Home.tsx consumes HA Area Registry; auto-generated Area cards with occupancy/temperature/Frigate previews; HomeSettings connection/presence/safety controls (some of this now lives in DevicesTab — not verified).
EVID: grep -n 'area|Area' frontend/src/pages/Home.tsx -> none; frontend/src/components/home/ does not exist; only backend integrations/home_assistant/ha_client.py references area_registry

### F18 DS-08 — UI-REDESIGN Phase 4 responsive/collapsible rail not started
status=not_started cat=incomplete_feature prio=P3 conf=high act=True
REMAINING: Icon-only rail on medium viewports; touch-friendly wall-tablet styling.
EVID: grep 'md:w-16|lg:w-60|collaps' Layout.tsx and packages/design-system/src/surfaces/NavRail.tsx -> none

### F18 DS-10 — 56 hardcoded hex colours remain in dashboard src despite the 'never hardcode a colour' rule
status=unknown cat=cleanup prio=P3 conf=low act=True
REMAINING: Triage the 56 hits; route legitimate ones through tokens.css.
EVID: grep -rnoE '#[0-9A-Fa-f]{6}\b' frontend/src --include=*.tsx --include=*.ts (excluding tests/stories) = 56 matches; not triaged for legitimacy (SVG fills, canvas, xterm themes may be exempt)

### F18 SEM-00 — Semantic audit handoff is untracked/doc-only; its primary reference artifact lives outside the repo
status=not_started cat=needs_commit prio=P2 conf=high act=True
REMAINING: Commit the handoff; copy semantic_audit.md into .handoff/ or documentation/ so successors can read it.
EVID: git status: '?? .handoff/HANDOFF-SEMANTIC-AUDIT-AND-TERMINOLOGY-REVIEW-2026-09-01.md'; doc §4 links semantic_audit.md at /Users/ericbintner/.gemini/antigravity/brain/b690d9c9-.../semantic_audit.md (exists, 14,895 bytes, not in repo); no LEXICON/DICTIONARY doc in repo

### F18 SEM-01 — Semantic Task 1 (scrutiny of CLI, prompts, frontend names, backend packages) not started
status=not_started cat=cleanup prio=P3 conf=high act=True
REMAINING: Audit Halbert/main.py + halbert_core/cli help text; prompts (already clean per grep); frontend component names; backend package names.
EVID: All rename targets still present: frontend/src/components/settings/tabs/BeingTab.tsx, components/fleet/NodeFleetCockpit.tsx, components/voice/TouchBar.tsx; halbert_core/halbert_core/{federation,persona,somatic}/ exist; {mesh,identity,maintenance}/ absent; no SelfTab/IdentityTab/DeviceGrid/ControlStrip files; config/prompts: 0 files match 'the being' or 'sovereign'; frontend: 2 files contain 'sover

### F18 SEM-02 — Semantic Task 2 (Brand Lexicon & Dictionary) not started
status=not_started cat=doc_only prio=P3 conf=high act=True
REMAINING: Author the lexicon table (legacy term / canonical name / code identifier / layer / definition / usage rule).
EVID: find repo -iname '*LEXICON*' -o -iname '*DICTIONARY*' (excluding .venv/node_modules) -> none

### F18 SEM-03 — Semantic Task 3 (phased migration plan + compatibility shims) not started
status=not_started cat=incomplete_feature prio=P3 conf=high act=True
REMAINING: Phases 1-4 as written (docs → UI labels → identity.yml/being.yml shim + API alias → module renames).
EVID: no identity.yml in repo; grep 'api/settings/identity' routes/ -> none; being.yml remains the config name (HANDOFF-N150-* reference /etc/halbert-home/being.yml)

### F18 SEM-04 — Semantic Task 4 founder fork decisions (Self vs Identity; Compute Mesh naming; Unified Mode naming) pending — note Settings already relabelled 'The Being' → 'Personality & Identity'
status=not_started cat=decision prio=P2 conf=high act=True
REMAINING: Founder picks: Self vs Identity; Compute Mesh vs Mesh Computing vs Continuity Grid; Unified Mode vs One Halbert vs Shared Presence.
EVID: Handoff §3 Task 4 lists 3 decisions; pages/Settings.tsx:76-79 SETTINGS_SECTIONS label 'Personality & Identity' / 'Identity & Voice' (commit b2629f69 'rename The Being to Personality') — a partial Phase-2 relabel already shipped ahead of the plan

### F18 HW-01 — Hardware Validation Matrix: 0 of 22 cells recorded, sign-off empty; its 'not yet built' notes are stale — nothing is software-blocked any more
status=blocked cat=test_gap prio=P2 conf=high act=True
REMAINING: Run all 22 tests on the physical N150 + 10-inch touch display with backend audio enabled and kiosk at /voice; record results; file issues. Update the Notes block (drop the three 'not yet built' lines).
EVID: .handoff/HARDWARE-VALIDATION-MATRIX-2026-08-31.md: every Result cell empty, Sign-off table empty; Notes claim P2/O3/O5 'not yet built', but `git merge-base --is-ancestor 07d53549 main` = yes (display power daemon), and git ls-files shows halbert_core/system/display_power.py, dashboard/routes/tts_egress.py, proactive/acoustic_bridge.py, findings/detectors/acoustic_anomaly.py tracked on main (merge 
DOC: Matrix Notes say tests 2.2/5.2 (P2), 4.3/4.4 (O3) and 6.x (O5) are blocked on unbuilt work; all three are merged on main.

### F18 HW-02 — N150 target-spec procurement checklist (6 items) unchecked — physical/founder
status=not_started cat=decision prio=P3 conf=high act=True
REMAINING: Founder confirms BOM before ordering.
EVID: .handoff/HANDOFF-N150-TARGET-SPEC.md:100-105 six '- [ ]' BOM confirmations (16GB fit, 256GB NVMe, passive thermal, 2.5GbE, M.2 slots, share BOM)

### F18 HW-03 — N150 Halbert-stack install checklist (9 items) unrun and references the removed 'home-light' variant
status=not_started cat=test_gap prio=P3 conf=high act=True
REMAINING: Rewrite §2B/§7/§8 for the 'home' variant; run the 9 verification steps on the box.
EVID: .handoff/HANDOFF-N150-HALBERT-STACK.md:145-153 nine '- [ ]' items; :145 'verify the instance variant resolves to home-light'; code: halbert_core/config/being_config.py:36 VALID_VARIANTS = {'sysadmin','home'} (home-light removed by D4); sole remnant string at model/llm_config.py:816
DOC: Doc says the N150 runs variant 'home-light'; being_config.py rejects any variant other than sysadmin/home.

### F18 HW-04 — N150 ↔ compute-host peer-offload integration checklist (8 items) unrun; all software prerequisites exist on main
status=not_started cat=test_gap prio=P2 conf=high act=True
REMAINING: Two-machine run over Tailscale: pairing, offload, offline fallback to template thoughts, mDNS TXT check.
EVID: .handoff/HANDOFF-N150-PEER-OFFLOAD.md:157-164 eight '- [ ]'; prerequisites verified: model/client.py:75-77 CHAT_CAPABLE_PROVIDERS includes 'peer'; model/providers/__init__.py:17 imports PeerProvider; pages/Settings.tsx:731 `isHomeVariant ? <ComputePeerCard/> : <ModelSettings/>`; federation/compute_router.py:311 `async def route(`; model/config_wizard.py:101-128 --peer

### F18 HW-05 — Low-power handoff S2/S3/S4/deploy-README items are DONE in code but still unchecked in the doc and in committed MASTER-TODO (S3 note about PeerProvider is stale)
status=done cat=doc_only prio=P3 conf=high act=True
REMAINING: Tick §8 lines 187,191,192,193,194 and MASTER-TODO S3/S4 (MASTER-TODO is currently dirty in another session — coordinate).
EVID: HANDOFF-LOW-POWER-...:191-194 unchecked; `git show main:.handoff/MASTER-TODO.md` lines 132-133 say 'peer is missing from CHAT_CAPABLE_PROVIDERS' — false (client.py:75-77); deploy/README.md:13,102,126 already state Home runs without SourcePrep; capabilities.py:50-79 CAP_SOURCEPREP gating; hardware_detector.py:455-462 SBC_LOW_POWER offload-only budget; packages/model-picker RoleAssignmentRow.tsx:65 
DOC: MASTER-TODO S3 claims PeerProvider is unregistered; it is registered and ComputePeerCard is mounted.

### F18 HW-06 — Three small low-power edge-case fixes not done: http:// auto-prefix, host.docker.internal allowlist, cloud→local fallback prompt
status=not_started cat=incomplete_feature prio=P3 conf=high act=True
REMAINING: Sysadmin-variant only: prefix bare hosts with http:// in _clean_endpoint/_is_local_url; allowlist host.docker.internal; 1-click local fallback banner when cloud chat_model errors.
EVID: model/llm_config.py:135-150 _is_local_url and :369+ _clean_endpoint contain no scheme auto-prefix (only model/attribution.py:191 does); grep 'host.docker.internal' llm_config.py -> none; grep 'switch to local|fallback.*local' frontend/src/components/chat hooks -> none (HANDOFF-LOW-POWER §8 lines 188-190)

### F18 HW-07 — D2 — 4GB boundary decision unresolved (code: 4GB host = ENTRY_8GB local-capable; docs: 4GB = offload-only)
status=blocked cat=decision prio=P2 conf=high act=True
REMAINING: Founder picks: move the boundary to <=4GB in hardware_detector.py + compute_router + test_hardware_profile_fallback.py, or change the docs to '<4GB'.
EVID: model/hardware_detector.py:433-437 `if hw.total_ram_gb >= 4: return ENTRY_8GB` else SBC_LOW_POWER; HANDOFF-LOW-POWER §4/§7 revision notes and MASTER-TODO:137 both flag the conflict

### F18 LEG-01 — FDR-DEC-01 / LEG-CRIT-02: DCO + commercial permission grant text is already committed in CONTRIBUTING.md but has no founder sign-off
status=in_progress cat=decision prio=P1 conf=high act=True
REMAINING: Founder reviews and confirms that a sign-off-based grant (a DCO, not a CLA) is the intended legal instrument, ideally with counsel; then tick the four trackers.
EVID: documentation/contributing/CONTRIBUTING.md:293-330 — DCO 1.1, '§2 Dual-Licensing & Commercial Permission Grant' (App Store §7, commercial distribution, upstream parity), '§3 Apple Mac App Store GPLv3 Section 7 Exception Clause'; .github/workflows/dco.yml + scripts/check-dco.sh exist (commit 12a29b55); yet LEGAL-AND-LICENSING-TODO LEG-CRIT-02 '[ ]', FOUNDER-TODO FDR-DEC-01 '[ ]', TASK-PACKET-06 §3 
DOC: Four trackers say 'commit CONTRIBUTING.md with DCO commercial rights language' is outstanding; the language is already in the file.

### F18 LEG-02 — FDR-DEC-02 / LEG-CRIT-03: §7 App Store exception text exists in two docs but no LICENSE-EXCEPTION-APPSTORE file and no SPDX 'WITH' headers
status=in_progress cat=decision prio=P1 conf=high act=True
REMAINING: Founder approves the exception wording; commit LICENSE-EXCEPTION-APPSTORE; apply the SPDX WITH form to the App Store target; confirm the App Store client stays a sandboxed remote companion.
EVID: Exception text at CONTRIBUTING.md:316-324 and documentation/legal/APP-STORE-DISTRIBUTION-STRATEGY.md §2.1; `ls LICENSE* documentation/legal/LICENSE*` -> only LICENSE and LICENSE.md; grep 'GPL-3.0-or-later WITH' across repo -> none; scripts/check_appstore_deps.py + config/dependency-licenses.yml exist (LEG-CRIT-03 opus half done)

### F18 LEG-03 — FDR-DEC-03: bundle identifiers disagree in three places
status=not_started cat=decision prio=P2 conf=high act=True
REMAINING: Founder locks one scheme; update tauri.conf.json per target, platforms.yml, FOUNDER-TODO.
EVID: frontend/src-tauri/tauri.conf.json:5 'ai.halbert.dashboard'; config/platforms.yml:216/226/239 'ai.halbert.linux' / 'ai.halbert.macos.pro' / 'ai.halbert.macos.free'; FOUNDER-TODO.md:22 'ai.halbert.home'

### F18 LEG-04 — FDR-DEC-04 / LEG-MAJ-04: pricing, Ed25519 offline licence keys and Lemon Squeezy EULA — nothing exists in code or docs
status=not_started cat=decision prio=P2 conf=high act=True
REMAINING: Founder settles $24-29 perpetual terms; author EULA; then build key generation/verification + settings activation modal.
EVID: grep -rln 'ed25519|Ed25519' halbert_core -> only tools/register_host_project.py, vision/redact.py, rag/scrapers/git_docs.py (unrelated uses); find documentation -iname '*EULA*' -> none; FOUNDER-TODO Milestone 3 'Wire offline Ed25519 license key activation modal' unchecked; LEGAL-AND-LICENSING-TODO LEG-MAJ-04 '[ ]'

### F18 LEG-05 — Founder confirmations from legal TODO §5.2: '-or-later' (verified consistent) and 2024 copyright start year (pending)
status=in_progress cat=decision prio=P3 conf=high act=True
REMAINING: Founder confirms 2024 (prior Cerebric/LinuxBrain history) or changes COPYRIGHT in scripts/add_spdx_headers.py + halbert_core/__init__.py and re-runs the tagger.
EVID: grep -rhoE 'GPL-3.0(-or-later|-only)?' halbert_core (py/ts/tsx) -> 699 '-or-later', 0 bare 'GPL-3.0' followed by non-dash; 462 py files carry 'Copyright (C) 2024-2026' while LEGAL-AND-LICENSING-TODO §5.2(5) notes the first commit is 2025-12-08; SPDX coverage: 459/459 tracked py files (the single miss is node_modules/flatted/python/flatted.py, untracked)

### F18 LEG-07 — All AI-tier legal items delivered; documentation/legal/ complete; remaining TASK-PACKET-06 items are external founder actions
status=done cat=decision prio=P2 conf=high act=True
REMAINING: Founder: Apple Developer Program certificates, Lemon Squeezy product + webhook, create halbert-ha-addon public repo.
EVID: LEGAL-AND-LICENSING-TODO.md: only LEG-CRIT-02, LEG-CRIT-03 (founder half) and LEG-MAJ-04 remain '[ ]'; documentation/legal/ has LICENSE, THIRD-PARTY-LICENSES, PRIVACY, TERMS, DISCLAIMER, TRADEMARKS, SECURITY, APP-STORE-DISTRIBUTION-STRATEGY, CORPUS-LICENSING-ARCHITECTURE, OPEN-CORE-AND-DISTRIBUTION-STRATEGY; Halbert/main.py:110-148 `halbert license` CLI; TASK-PACKET-06:61-65 five '[ ]' (two are LE

### F18 ENV-01 — Python baseline unresolved: handoff says >=3.11 but CLAUDE.md (same day) codifies >=3.10; metadata/venv at 3.10, docs/CI at 3.11
status=blocked cat=decision prio=P2 conf=high act=True
REMAINING: Founder chooses the floor. If 3.11: Phase 1 (pyproject, Haloysius, CoDRAG engine, PKGBUILD), Phase 2 (delete/retarget requirements-rag.txt, drop Z workarounds), Phase 3 (rebuild .venv on arm64 3.11), Phase 4 gates. If 3.10: fix README/INSTALLATION to say 3.10+ and mark the handoff superseded.
EVID: PYTHON-ENVIRONMENT-AUDIT §1 verdict requires-python '>=3.11,<3.13'; CLAUDE.md 'Python >=3.10 (recommended 3.11 or 3.12)' committed 78eb3d4d 2026-08-29; halbert_core/pyproject.toml:15 '>=3.10'; /Volumes/4TB-BAD/Haloysius/pyproject.toml:10 '>=3.10'; packaging/arch/PKGBUILD:12 'python>=3.10'; .github/workflows/ci.yml:21,124,206 python 3.11; README.md:145 'Python 3.11+'; documentation/INSTALLATION.md:
DOC: Public docs promise 3.11+ while package metadata accepts 3.10; the handoff's Phase 1-3 boxes are all unchecked and CLAUDE.md contradicts its verdict.

### F18 ENV-02 — Node/React Packet 01 (root workspace, workspace deps, alias cleanup, .nvmrc) DONE; CI still pins Node 20
status=done cat=cleanup prio=P3 conf=high act=True
REMAINING: Bump ci.yml node-version to 22 to match .nvmrc/CLAUDE.md.
EVID: /package.json matches Task 1.1 verbatim (workspaces packages/* + dashboard, packageManager npm@10.9.3); frontend/package.json:19-20 '@halbert/design-system': '*', '@halbert/model-picker': '*'; grep MODEL_PICKER_SRC|fs.allow frontend/vite.config.ts -> none; .nvmrc = 22 in Halbert and /Volumes/4TB-BAD/Haloysius; .github/workflows/ci.yml:153,170,188 node-version '20'

### F18 ENV-07 — Dashboard React 19 upgrade path not started (marketing web-v7 already on React 19 / Vite 6 outside the workspace)
status=not_started cat=deferred prio=P3 conf=high act=False
REMAINING: Planned path only; no action needed until founder schedules it.
EVID: frontend/package.json react ^18.2.0; design-system devDeps react ^18.3.1 (peer '^18.2.0 || ^19.0.0'); marketing/web-v7/package.json react ^19.0.0, vite ^6.0.0, tailwindcss ^4.0.0 and not in root workspaces

### F19 R08-01 — Approvals page (and GPU/Containers/Development/Network/Sharing/Apps) orphaned off the nav rail
status=not_started cat=bug prio=P1 conf=high act=True
REMAINING: Add an Approvals item (Intelligence & Findings section) and/or the promised top-bar pending-count badge polling getPendingApprovals(); decide whether GPU/Containers/Development/Network/Sharing/Apps get re-railed, become sub-views, or get their routes removed. Add a Layout test asserting every App.tsx route has an entry point.
EVID: src/components/Layout.tsx:70-91 navSections = Dashboard('/'), Home('/home'), Findings('/findings'), Services, Storage, Backups, Terminal only. src/App.tsx:123-134 still routes /gpu /containers /development /network /sharing /apps /approvals. grep across src for `/approvals`, `getPendingApprovals`, `to="/gpu"`… returns only App.tsx:134 and lib/tauri.ts:132-151 (consumed solely by pages/Approvals.ts

### F19 R08-02 — Settings NavRail declares ARIA tabs pattern without arrow keys, roving tabindex, or panel wiring
status=not_started cat=bug prio=P2 conf=high act=True
REMAINING: Either implement Up/Down/Home/End + roving tabindex in NavRail tabMode and give tab buttons ids + aria-controls matching each TabsContent (pass id/aria-labelledby), or drop role=tablist/tab for nav semantics with aria-current and give each panel an aria-label. Update Settings.tabs.test.tsx accordingly.
EVID: packages/design-system/src/surfaces/NavRail.tsx:123-124 role=tablist/aria-orientation, :136-137 role=tab/aria-selected; the only onKeyDown in the file is the search input's Escape at :113; no tabIndex, aria-controls, or id on tab buttons (grep). NavRail.tsx last changed in 0a32e26e (pre-review). Settings.tsx:6 imports only {Tabs, TabsContent}; :716-845 renders 12 TabsContent panels with no TabsTri

### F19 R08-03 — Hardcoded Tailwind palette classes in VisionTab and Findings (Daylight token violation)
status=not_started cat=bug prio=P2 conf=high act=True
REMAINING: Replace with text-success / text-error / text-info; then re-record the ratchet baseline (see R08-04).
EVID: src/components/settings/tabs/VisionTab.tsx:135,138,141 `text-green-500`/`text-red-500`; src/pages/Findings.tsx:69 `text-purple-500` (siblings at :68/:70 already use text-info/text-success).

### F19 R08-04 — NEW: literal-colour ratchet (CI design-tokens job) fails on main — 11 files grew since baseline
status=not_started cat=bug prio=P1 conf=high act=True
REMAINING: Fix or consciously accept the new debt: VisionTab/Findings entries are renames (baseline still keyed to Settings.tsx/Security.tsx) — re-baseline those; the other 9 files are genuinely new literal colours from voice/fleet/devices work and should be swept to tokens (text-success/-warning/-error/-info, bg-muted etc.) before `--baseline` is re-recorded. Verify the CI run on GitHub.
EVID: `python3 scripts/check_literal_colors.py --check` → exit 1: StateBadge.tsx 7→12, audio/AcousticAnomalyModule.tsx 0→9, audio/AcousticAuraIndicator.tsx 0→4, audio/VoiceEnrollmentModal.tsx 0→3, fleet/DiscoveredPeerCard.tsx 0→2, fleet/NodeFleetCockpit.tsx 0→20, settings/devices/DeviceCard.tsx 0→15, settings/tabs/VisionTab.tsx 0→6, shell/InstanceSwitch.tsx 0→4, ui/button.tsx 0→4, pages/Findings.tsx 0→1

### F19 R08-05 — Indexing poll interval leaks on Settings unmount / stacks on Re-index
status=not_started cat=bug prio=P3 conf=high act=True
REMAINING: Hold the interval in a ref, clear it in an unmount cleanup, and guard against starting a second poll while one is active.
EVID: src/pages/Settings.tsx:589-627 pollIndexingStatus() returns `() => clearInterval(interval)`; both callers at :315 (checkIndexingStatus) and :571 (re-index) discard the return; the only clearInterval besides the returned closure is the self-clear at :607 on is_running=false; no useEffect cleanup references it.

### F19 R08-06 — Settings shell still fetches everything on mount; no tab-level lazy mounting (packet §6)
status=not_started cat=deferred prio=P3 conf=high act=False
REMAINING: Move per-tab loads into their tabs or lazy-mount heavy tabs; re-fetch on activation. Structure (props-drilled Knowledge/Safety tabs) is ready for it.
EVID: src/pages/Settings.tsx:232-240 mount effect calls loadSettings, loadSystemProfile, loadAiRules, loadSelfKnowledge, checkIndexingStatus, loadDocSuggestions, loadTrendingSuggestions regardless of tab; grep finds no React.lazy/lazy( in the file.

### F19 R08-07 — Carried-over nits: placebo 'Clear cache', Debug label targets a Button, blocklist PUT per keystroke
status=not_started cat=bug prio=P3 conf=high act=True
REMAINING: Wire or remove the clear-cache button; make the debug toggle a Switch/checkbox or drop the htmlFor; debounce/blur-save the blocklist.
EVID: Settings.tsx:380-387 handleClearDiscoveries = confirm + timeout + alert('Cache cleared…'), no API call; components/settings/tabs/DebugTab.tsx:28 `<Label htmlFor="debug-toggle">` → :34 `<Button id="debug-toggle">`; VisionTab.tsx:336-338 textarea onChange → updateConfig('redaction_blocklist') which PUTs at :58-59 and refetches via loadConfig() at :64.

### F19 R11-01 — F1: every normally-completed turn aborts its own SSE stream and POSTs /api/agent/cancel
status=not_started cat=bug prio=P1 conf=high act=True
REMAINING: Make the effect unmount-only (deps [] + isStreamingRef read in cleanup) or null sessionIdRef/source on the normal end paths (response_complete / loop exit / cancel()); add a test asserting no cancel POST after a normal completion and exactly one on unmount mid-stream.
EVID: src/hooks/useAgentStream.ts:379-390 unchanged: `useEffect(() => { const source = eventSourceRef.current; return () => { source?.close(); if (sessionIdRef.current && isStreaming) fetch(apiUrl(`/api/agent/cancel/${sessionIdRef.current}`), {method:'POST'}) } }, [isStreaming])` — cleanup runs on the true→false transition with captured isStreaming===true; no isStreamingRef/queueMicrotask anywhere (grep

### F19 R11-02 — F2: queued-message auto-send bypasses the parked-turn guards and drops pending approvals
status=not_started cat=bug prio=P2 conf=high act=True
REMAINING: Park the queue while session.pendingConfirmation / state==='awaiting_confirmation' / a pending diffProposal is showing; drain after resolution. Add an AgentChat test: queue a message, end the turn on tool_confirmation_required, assert the ConfirmationDialog survives.
EVID: src/components/agent/AgentChat.tsx:561-592 drain effect fires on `!isStreaming && messageQueue.length > 0`, calls foldLiveTurn() at :583 and sendMessage at :589 with no pendingConfirmation/diffProposals check. The guard exists twice elsewhere in the same file — fold effect :499-506 and the 'Reply finished' announcer :385-386 — but not here.

### F19 R11-03 — F3: side effects still inside the setSession updater (StrictMode double-fire in dev)
status=not_started cat=bug prio=P2 conf=high act=True
REMAINING: Hoist every remaining side effect into the pre-updater block at :434-460 so the updater is pure; add a StrictMode-wrapped test that module_invoke renders once and fallback announces once.
EVID: useAgentStream.ts inside the setSession updater: :495-499 announce(fallback), :501 setTurnModel, :527 onToolStart, :545 onToolComplete, :555 onConfirmationRequired, :566-574 setProvenance/setResponse/setIsStreaming/onComplete, :578 setProvenance, :582 setModuleInvocations, :590 onError + :594 setIsStreaming, :604-605 setIsStreaming/onComplete. Only the confirmation announce, chunk appends, flush a

### F19 R11-04 — F4: timeout error points at a removed 'Settings > AI > Performance Tweaks' panel
status=not_started cat=bug prio=P3 conf=high act=True
REMAINING: Drop the sentence.
EVID: useAgentStream.ts:884 error string still ends 'Try increasing timeout in Settings > AI > Performance Tweaks.'; comment at :866-868 says the Tweaks override was removed.

### F19 R11-05 — F5 / audit E6-E7: ThinkingPanel toggles lack aria-expanded/aria-controls; emoji in the header
status=not_started cat=bug prio=P3 conf=high act=True
REMAINING: Add aria-expanded + aria-controls to both toggles pointing at id'd regions; replace emoji with a lucide icon (aria-hidden) or text.
EVID: components/agent/ThinkingPanel.tsx:44-64 outer <button> has only onClick/className; :50 renders 🧠/💭; :107-118 section toggle likewise; grep for aria-expanded/aria-controls in the file: 0 hits.

### F19 R11-06 — F6 / audit E10: StateBadge pulse ignores prefers-reduced-motion
status=not_started cat=bug prio=P3 conf=high act=True
REMAINING: Add motion-reduce:animate-none to the ping span.
EVID: components/agent/StateBadge.tsx:101 `animate-ping …` with no motion-reduce:/motion-safe: variant; AgentChat.tsx:1175 already uses `motion-reduce:animate-none` for the caret.

### F19 R11-07 — F7 / audit E9: focus dropped to <body> after a successful 'Forget this'
status=not_started cat=bug prio=P3 conf=high act=True
REMAINING: On success move focus to the article or the redaction marker.
EVID: components/agent/Timeline.tsx:350-365 confirm(): finally { setPending(false); setConfirming(false) } with no focus move on success; only focus() in the file is confirmRef at :306-308 (into the dialog).

### F19 R11-08 — F8 / audit E11: HostShell conversation column is not a landmark
status=not_started cat=bug prio=P3 conf=high act=True
REMAINING: Add role="region" (or use <section>/<main>).
EVID: components/shell/HostShell.tsx:75-79 `<div ref={conversationRef} … aria-label="Conversation">` with no role; sibling :88 is `<aside aria-label="Context stage">`.

### F19 R11-09 — F9 / audit E8: scrollable <pre> blocks not keyboard-reachable
status=not_started cat=bug prio=P3 conf=high act=True
REMAINING: tabIndex={0} + focus-visible ring on each scrollable <pre>.
EVID: ThinkingPanel.tsx:83 overflow-auto; ToolExecutionCard.tsx:140,159,169 overflow-x-auto; domain/CodeBlock.tsx:245,316 overflow-x-auto — none carry tabIndex (grep: 0 hits in all three files).

### F19 R11-10 — F10 / audit C4-C5: useTimeline has no request abort and one shared inFlight flag
status=not_started cat=bug prio=P3 conf=high act=True
REMAINING: AbortController per request threaded through api.getTimeline; per-variant in-flight tracking so a later 'Back to latest' supersedes a slow 'Load earlier' instead of silently no-op'ing.
EVID: hooks/useTimeline.ts:199 `const inFlight = useRef(false)`; initial load :239-265 uses only a `cancelled` flag; loadOlder :281, loadAround :298, loadLatest :318 all early-return on the same inFlight.current; grep AbortController/signal: 0 hits.

### F19 R11-11 — F11: composer aria-expanded claims a mention popup that is not rendered
status=not_started cat=bug prio=P3 conf=high act=True
REMAINING: `aria-expanded={showMentions && filteredMentionables.length > 0}` or keep the listbox mounted with a 'no matches' option.
EVID: AgentChat.tsx:1380 `aria-expanded={showMentions}` while the listbox mounts only when `showMentions && filteredMentionables.length > 0` (:1281); aria-activedescendant at :1382-1386 already applies the length guard.

### F19 R11-12 — F12 / audit C2-C3: MessageContent and ThinkingPanel re-parse the whole text every frame
status=not_started cat=bug prio=P3 conf=high act=True
REMAINING: useMemo keyed on content; wrap in React.memo. Bounded to ~60 fps by the token buffer so it is optimisation, not a stall.
EVID: components/agent/MessageContent.tsx:19-41 regex parse in the render body, no useMemo/React.memo (grep 0 hits); ThinkingPanel.tsx:40 `parseThinkingSections(thinking)` unmemoized.

### F19 R11-13 — F13: handleEvent/sendMessage/confirmAction identity churns on every render (options literal)
status=not_started cat=cleanup prio=P3 conf=high act=True
REMAINING: Store options in a ref inside the hook and depend on the ref.
EVID: useAgentStream.ts:840 handleEvent deps `[options]`; :979 sendMessage deps `[initSession, handleEvent, options, flushNow]`; AgentChat.tsx:332-348 passes a fresh options object literal each render; no optionsRef in the hook (grep).

### F19 CUA-04 — Chat-ui-audit P2: D3 streaming markdown rendering
status=not_started cat=incomplete_feature prio=P2 conf=high act=True
REMAINING: Adopt react-markdown + remark-gfm using CodeBlock for code fences; memoize (overlaps R11-12).
EVID: components/agent/MessageContent.tsx (65 lines) renders plain text + fenced code only via a regex at :19-41; grep react-markdown/remark-gfm in frontend package.json: 0 hits.

### F19 CUA-05 — Chat-ui-audit P2: D2 human-readable status_detail in StateBadge
status=not_started cat=incomplete_feature prio=P3 conf=high act=True
REMAINING: Backend emits status_detail on state_change; StateBadge shows it as a subtitle. Needs backend coordination.
EVID: grep status_detail/statusDetail in useAgentStream.ts and StateBadge.tsx: 0 hits.

### F19 CUA-06 — Chat-ui-audit P2: B5 diff apply/reject has no failure rollback
status=not_started cat=bug prio=P3 conf=high act=True
REMAINING: Return the promise, revert status on non-2xx/throw, announce the failure.
EVID: useAgentStream.ts:1093-1108 applyDiff and :1110-1125 rejectDiff optimistically set status then fetch(...).catch(console.error) — no revert, no announce.

### F19 CUA-07 — Chat-ui-audit P2: F2 copy-response button
status=not_started cat=incomplete_feature prio=P3 conf=high act=True
REMAINING: Hover action bar with copy on assistant turns (live + stored).
EVID: grep clipboard.writeText under components/agent, domain, shell: only CodeBlock.tsx:87 (code fences) and TerminalTile.tsx:254; none for an assistant reply in AgentChat/Timeline.

### F19 CUA-08 — Chat-ui-audit P3 items still open: B6 silent SSE parse errors, B8 no image size limit, D1 submitted state, D4 reconnect/resume, D5 eventSourceRef type, D6 token usage, F3 regenerate/edit, F6 line-length cap, F8 focus-composer shortcut, F9 document.title, F10 read-more
status=not_started cat=deferred prio=P3 conf=medium act=False
REMAINING: Pick from the P3 table by user feedback, per the audit's own Sprint 4 guidance; none blocks a ship.
EVID: useAgentStream.ts:955-957 empty catch on JSON.parse; AgentChat.tsx:601-640 processImageFile rejects only non-images (no size check); grep submitted/reconnect/resume/token_usage in useAgentStream.ts: 0; :978 `as EventSource` cast remains; grep regenerate in components/agent: 0; grep metaKey/ctrlKey/document.title in HostShell/AgentChat/App/Layout: 0; grep max-w-prose/max-w-2xl/3xl in AgentChat: 0. 

### F19 CUA-09 — Chat-ui-audit strategic G1 typed message 'parts' model and G2 assistant-ui evaluation
status=not_started cat=decision prio=P3 conf=high act=False
REMAINING: Founder decision on whether to plan these; given the 'finish current features' direction they should stay deferred.
EVID: No parts model or assistant-ui dependency in the frontend (grep 'assistant-ui' in package.json: 0); README lists both as separate initiatives.

### F19 WT-01 — docs/chat-ui-audit worktree: +1 README line linking a gitignored, never-committed 283-line precursor handoff
status=in_progress cat=decision prio=P3 conf=high act=True
REMAINING: Founder choice: (a) commit the precursor as the historical request (`git add -f` the file + the README line, docs-only, trivially mergeable) and retire the worktree, or (b) discard the worktree change and delete the worktree. Do not merge the README line alone — the link would dangle on main.
EVID: `git -C ~/.config/superpowers/worktrees/Halbert/chat-ui-audit diff` → README.md +`11. [Response Modality & Conversational Style — Design Handoff](./11-response-modality-handoff.md)`. The target exists in the worktree docs dir (283 lines, dated 2026-08-30, 'Status: Findings documented. Awaiting external design & UX review', Parts A/B/C) but `git check-ignore -v` → `.gitignore:108 docs/`, so it is i

### F19 DOC-01 — Handoff/TODO accuracy for REV-08/REV-11
status=done cat=doc_only prio=P3 conf=high act=True
REMAINING: Update MASTER-TODO TASK-08 line; when fixes land, close the REV-08/REV-11 entries in one place rather than three.
EVID: HANDOFF-WRAP-UP-2026-08-31.md:74-84 and HANDOFF-CENTRAL-TODO-BATCHES-2026-08-31.md:90-94 correctly list all REV-08/REV-11 findings as open — verified true on main today. MASTER-TODO.md:36,:86 (TASK-08 'token buffer + ARIA open') is stale — both shipped. Review docs' line numbers drifted: REV-11 F2 AgentChat 552-583→561-592, F11 1371→1380, F3 updater 488-606→485-606; REV-08 Settings poll 584-623→58
DOC: MASTER-TODO.md:86 claims 'token buffer + ARIA open' for TASK-08; both landed on main in 7fad824b and c5cd65ce.

### F20 U3-02 — TASK-02 Task 2.2.1 — Settings shell under 300 lines
status=in_progress cat=incomplete_feature prio=P3 conf=high act=True [V:confirmed]
REMAINING: Move per-tab state/loaders (Knowledge, Safety, Alerts, System) into their tabs so the shell becomes a coordinator. Not blocking; behaviour is identical to the megafile.
EVID: wc -l src/pages/Settings.tsx = 880. The shell still owns ~40 pieces of state and all loaders (Settings.tsx:233-241 mount effect: loadSettings, loadSystemProfile, loadAiRules, loadSelfKnowledge, checkIndexingStatus, loadDocSuggestions, loadTrendingSuggestions) and drills them into KnowledgeTab/SafetyTab (REV-08: '40 props into KnowledgeTab').
VERIFY: confirmed — Re-checked on main 4a7bf71f: `wc -l src/pages/Settings.tsx` = 880 (packet Task 2.2.1 target <300). `grep -c useState` = 45. Mount effect at Settings.tsx:233-241 calls loadSettings/loadSystemProfile/loadAiRules/loadSelfKnowledge/checkIndexingStatus/loadDocSuggestions/loadTrendingSuggestions unconditionally. Prop drilling is even heavier than stated: `<KnowledgeTab` at :735-785 receives 44 props (aw

### F20 U3-04 — TASK-02 Task 2.2.3 — React.lazy/Suspense tab loading
status=not_started cat=incomplete_feature prio=P3 conf=high act=True [V:confirmed]
REMAINING: Lazy-mount heavy tabs (Knowledge, Being, Vision) with React.lazy + Suspense and move their fetches to tab activation; add a cache-invalidation story. Packet manual check 'loads the Security tab without rendering background tabs' currently fails in spirit (Radix only mounts the active TabsContent, but the shell still fetches everything).
EVID: grep -n 'lazy\|Suspense' src/pages/Settings.tsx returns nothing; all tabs statically imported at Settings.tsx:27-55. Mount effect at :233-241 fires 7 loaders regardless of active tab (incl. GitHub trending). REV-08 Finding 5 (PLAUSIBLE, LOW) confirms.
VERIFY: confirmed — `grep -n -E 'lazy|Suspense' Settings.tsx` returns nothing; all tabs are static imports (Settings.tsx:27-51: BeingTab, DevicesTab, SecurityTab, VisionTab, SystemTab, SafetyTab, AlertsTab, AboutTab, DebugTab). Mount effect :233-241 fires 7 loaders regardless of tab (loadTrendingSuggestions hits `${API_BASE}/rag/trending` → GitHub). Packet Task 2.2.3 is therefore not started. Task 2.2.2 (?tab= URL bi

### F20 U3-06 — REV-08 F1 — Approvals (and 6 other pages) orphaned off the rail
status=not_started cat=bug prio=P1 conf=high act=True [V:adjusted]
REMAINING: Re-add an Approvals item under 'Intelligence & Findings' (or ship the promised top-bar pending-count badge). Decide whether Apps/Network/Sharing/Containers/GPU/Development get a sub-view or a rail entry — today they are reachable only by typing the URL.
EVID: App.tsx:123-134 still routes /gpu /containers /development /network /sharing /apps /approvals; `grep -rn "['\"]/(approvals|gpu|network|sharing|apps|containers|development)['\"]" src/ | grep -v App.tsx` returns nothing; getPendingApprovals() (lib/tauri.ts:132) is only called from pages/Approvals.tsx:44 — no badge. Layout.tsx:64-66 comment promises 'future sub-views and a top-bar approvals badge'. N
VERIFY: adjusted — Conclusion holds, one evidence claim is wrong. Layout.tsx:70-92 navSections on main = 3 sections / 7 items (Dashboard, Home, Findings, Services, Storage, Backups, Terminal); Approvals/Apps/Network/Sharing/Containers/GPU/Development are routed in App.tsx:123-134 but `grep -rn "['\"]/(approvals|gpu|network|sharing|apps|containers|development)['\"]" src | grep -v App.tsx` is empty; getPendingApproval corrected_status=not_started

### F20 U3-09 — REV-08 F2 — Settings rail declares ARIA tabs pattern without implementing it
status=not_started cat=bug prio=P2 conf=high act=True [V:confirmed]
REMAINING: Either implement Up/Down/Home/End + roving tabindex in NavRail tabMode and pass id/aria-controls to match Radix panel ids, or drop the tab roles in favour of nav semantics + aria-current and aria-label each TabsContent. Update Settings.tabs.test.tsx alongside.
EVID: packages/design-system/src/surfaces/NavRail.tsx:123-137: role=tablist/aria-orientation + role=tab/aria-selected, but the only onKeyDown is the search input's Escape (:113-115); no arrow keys, no roving tabindex, no aria-controls. Settings.tsx:713-845 renders Radix <Tabs>/<TabsContent> with no TabsTrigger (grep TabsTrigger = 0) so every panel's computed aria-labelledby points at a nonexistent id. S
VERIFY: confirmed — packages/design-system/src/surfaces/NavRail.tsx:123-124 sets role=tablist/aria-orientation and :136-137 role=tab/aria-selected when tabMode; the only onKeyDown in the file is :113 (search input). `ls packages/design-system/src/surfaces | grep -i navrail` → only NavRail.tsx (no test); `grep -rl NavRail --include=*.test.tsx` in design-system → none. Settings.tsx:713-845 renders <Tabs>/<TabsContent> 

### F20 U3-10 — REV-08 F3 — 4 hardcoded Tailwind palette classes in moved code
status=not_started cat=cleanup prio=P3 conf=high act=True [V:confirmed]
REMAINING: Replace with text-success / text-error / text-info tokens (founder directive: never hardcode a colour). Optional follow-up: repo-wide sweep (~200 occurrences per REV-08).
EVID: grep on main: VisionTab.tsx:135,138,141 `text-green-500`/`text-red-500`; Findings.tsx:69 `text-purple-500`. Same files already use text-success/text-error tokens elsewhere.
VERIFY: confirmed — `grep -n -E 'text-(green|red|purple)-[0-9]{3}'` over components/settings/tabs/*.tsx and pages/Findings.tsx on main: VisionTab.tsx:135,138,141 (`deps.x ? 'text-green-500' : 'text-red-500'`) and Findings.tsx:69 (`text-purple-500`). Exactly the 4 occurrences REV-08 F3 named; still present at 4a7bf71f.

### F20 U3-11 — REV-08 F4 — Indexing poll interval leaks on unmount
status=not_started cat=bug prio=P3 conf=high act=True [V:confirmed]
REMAINING: Hold the interval in a ref, clear in a useEffect cleanup, guard against double-start.
EVID: Settings.tsx:589-627 pollIndexingStatus returns `() => clearInterval(interval)` but both callers (:315, :571) discard it; no useEffect cleanup owns the interval. Re-index while a poll is alive stacks a second interval.
VERIFY: confirmed — Settings.tsx:589-627 `pollIndexingStatus` creates setInterval at :590, self-clears at :607 only on is_running=false, and returns `() => clearInterval(interval)` at :627. Callers at :315 (checkIndexingStatus, mount path) and :571 (re-index) both discard the return value; no useEffect cleanup references the interval. Unchanged since REV-08 (only 5ab70760 touched Settings.tsx after it, unrelated).

### F20 U3-12 — REV-08 minor — placebo cache-clear, DebugTab label targets a Button, VisionTab PUT per keystroke
status=not_started cat=bug prio=P3 conf=high act=True [V:adjusted]
REMAINING: Wire a real clear-discoveries endpoint (or remove the button); use a Switch/checkbox or drop htmlFor in DebugTab; debounce/blur-save the blocklist textarea.
EVID: Settings.tsx:380-388 handleClearDiscoveries = confirm + 1s setTimeout + alert, no API call. DebugTab.tsx:28 `<Label htmlFor="debug-toggle">` targets `<Button id="debug-toggle">` at :33-34 (label click inert). VisionTab.tsx:331-341 textarea onChange → updateConfig('redaction_blocklist') → PUT + refetch per keystroke.
VERIFY: adjusted — All three confirmed on main, and the VisionTab one is worse than described. Settings.tsx:380-388 handleClearDiscoveries = confirm() + 1s setTimeout + alert(), no fetch. DebugTab.tsx:28 `<Label htmlFor="debug-toggle">` targets `<Button id="debug-toggle">` at :33-34. VisionTab.tsx:331-341 textarea onChange → updateConfig('redaction_blocklist') → PUT /api/vision/config (:53-61) per keystroke — AND th
  CORRECTED_REMAINING: Wire a real clear-discoveries endpoint (or remove the button); use a Switch/checkbox or drop htmlFor in DebugTab; make the blocklist textarea local-state + save on blur/debounce — the current `disabled={saving}` on a per-keystroke PUT also disables the field mid-typing and loses focus.

### F20 U3-13 — TASK-02 §2.1.6 — IntegrationsSettings tab (HA / Wyoming / SourcePrep)
status=obsolete cat=deferred prio=P3 conf=medium act=True [V:confirmed]
REMAINING: Founder decision: is a single cross-integrations settings surface still wanted? If yes, file as new work; SourcePrep has no settings surface at all today.
EVID: No IntegrationsSettings/IntegrationsTab file under src/components/settings/tabs/. Wyoming ingress lives in components/audio/AudioSettings.tsx (Audio tab, Settings.tsx:829-832); HA surfaces via ComputePeerCard on the AI tab for the home variant (Settings.tsx:147-152, :730). REV-08 §3 classifies it 'NOT BUILT as a tab — overtaken by design'.
VERIFY: confirmed — `ls src/components/settings/tabs/` has no Integrations* file. Wyoming lives in components/audio/AudioSettings.tsx (15 'wyoming' matches) rendered by the Audio tab (Settings.tsx:829-832). HA: Settings.tsx:152-153 `useInstanceVariant`/isHomeVariant and :730-731 `{isHomeVariant ? <ComputePeerCard /> : <ModelSettings />}`. SourcePrep: the only mention under settings is a device-capability label (compo

### F20 U3-15 — REV-11 F1 — cleanup effect aborts the stream and POSTs cancel on EVERY normally-completed turn
status=not_started cat=bug prio=P1 conf=high act=True [V:confirmed]
REMAINING: Make the effect unmount-only (deps [] + isStreamingRef read inside cleanup) or null sessionIdRef/source on the normal end paths (response_complete, loop exit, cancel()). Add a test that a completed turn issues no cancel POST.
EVID: useAgentStream.ts:379-390 on main: `useEffect(() => { const source = eventSourceRef.current; return () => { source?.close(); if (sessionIdRef.current && isStreaming) fetch(apiUrl('/api/agent/cancel/'+sid), {method:'POST'}) } }, [isStreaming])` — the cleanup runs on the true→false transition at stream end with the captured isStreaming===true, so it aborts the reader mid-drain and cancels the just-c
VERIFY: confirmed — useAgentStream.ts:379-390 on main is exactly as quoted: `useEffect(() => { const source = eventSourceRef.current; return () => { source?.close(); if (sessionIdRef.current && isStreaming) fetch(apiUrl('/api/agent/cancel/'+…), {method:'POST'}) } }, [isStreaming])`. sessionIdRef is only nulled at :1082 (clearSession), never on the normal end paths, so the true→false cleanup always POSTs cancel. Preci

### F20 U3-16 — TASK-08 Task 8.1.3 — submission mutex while streaming
status=obsolete cat=decision prio=P2 conf=high act=True [V:confirmed]
REMAINING: Accept queue-while-streaming as the design (it is what the code and UX copy say), then fix the queue's race (U3-17). If the founder wants the packet's literal mutex instead, that is a UX reversal, not a bug fix.
EVID: Not implemented as 'disable submission'. AgentChat.tsx:899 `if (isStreaming && input.trim())` queues the message; :1393 placeholder 'Type to queue next message…'; :1444 'Agent working... type to queue'; drain effect :562-592 auto-sends when !isStreaming. The Send button is only disabled for empty input (:1430).
VERIFY: confirmed — AgentChat.tsx:898-905 `if (isStreaming && input.trim()) { setMessageQueue(...); setInput(''); announce('Message queued') }`; :1393 placeholder 'Type to queue next message...'; :1444 'Agent working... type to queue'; Send button :1430 `disabled={!input.trim() && attachedImages.length === 0}` (never disabled for streaming). Queue-while-streaming is the implemented design; the packet itself struck Ta

### F20 U3-17 — REV-11 F2 — queued-message drain bypasses the parked-turn guards (drops pending approvals)
status=not_started cat=bug prio=P1 conf=high act=True [V:confirmed]
REMAINING: Gate the drain on the same three parked-turn conditions; drain once the confirmation/proposal resolves or is dismissed. Add a test: queued message + turn parked on approval → dialog survives.
EVID: AgentChat.tsx:562 drain condition is only `!isStreaming && messageQueue.length > 0` (100 ms setTimeout, then foldLiveTurn + sendMessage at :590-595); the fold effect at :499-506 explicitly returns on session.pendingConfirmation / state==='awaiting_confirmation' / pending diffProposals. Unchanged since 375e8171.
VERIFY: confirmed — AgentChat.tsx:561-592 drain effect condition is only `!isStreaming && messageQueue.length > 0`, then a 100 ms setTimeout → foldLiveTurn() + sendMessage() (:583-589). The fold effect at :499-506 explicitly returns on pendingConfirmation / awaiting_confirmation / pending diffProposals — the drain has no such guard. I also verified the trigger is real end to end: state_machine.py:2454-2469 yields too

### F20 U3-22 — REV-11 F3/F4 — side effects inside setSession updater; dead 'Performance Tweaks' timeout text
status=not_started cat=bug prio=P2 conf=high act=True [V:confirmed]
REMAINING: Hoist the remaining side effects out of the updater the way :437-451 already does; delete the dead sentence at :884.
EVID: useAgentStream.ts: setSession(prev => …) updater begins ~:465 and still contains announce() (~:496 model fallback), setModuleInvocations (~:583), options.onError (~:591), setIsStreaming/onComplete (~:574-576, :605-606) — under main.tsx React.StrictMode these double-fire in dev. :884 error string 'Try increasing timeout in Settings > AI > Performance Tweaks.' while :867 says the Tweaks override was
VERIFY: confirmed — useAgentStream.ts: `setSession(prev => {` opens at :464 and the switch continues past :606 (session_ended returns at :606); inside it: announce() at :495, setIsStreaming(false)+options.onComplete at :573-574 and :604-605, setModuleInvocations(prev=>…) at :582, options.onError at :590/:594. main.tsx wraps in React.StrictMode (per REV-11; not re-verified but not disputed). :884 error string still sa

### F20 U3-23 — REV-11 F5–F11 a11y residuals (ThinkingPanel, StateBadge, HostShell, <pre> focus, useTimeline abort, mention aria-expanded)
status=not_started cat=bug prio=P3 conf=high act=True [V:confirmed]
REMAINING: Work REV-11 §4 worklist rows 5–13 (each is a small, local fix with the pattern already established in ToolExecutionCard). Another agent owns the full REV-11 audit; listed here because they fall under TASK-08's Sprint-2 a11y remit.
EVID: ThinkingPanel.tsx:45/:108 toggles have no aria-expanded/aria-controls; :50 renders emoji (founder no-emoji rule). StateBadge.tsx:101 animate-ping without motion-reduce. HostShell.tsx:75-79 conversation <div aria-label="Conversation"> has no role (dead label). No tabIndex on scrollable <pre>: ThinkingPanel.tsx:81,120; ToolExecutionCard.tsx:140,159,169,180. useTimeline.ts:199-312 single inFlight ref
VERIFY: confirmed — Each location re-checked on main: ThinkingPanel.tsx:44-45 and :107-108 toggles have onClick only (no aria-expanded/aria-controls), :50 renders the two brain emoji; StateBadge.tsx:101 `animate-ping` with no motion-reduce/motion-safe in the file; HostShell.tsx:75-79 conversation `<div aria-label="Conversation">` has no role while :88 `<aside aria-label="Context stage">` is a landmark; `grep -c tabIn

### F20 U3-25 — MASTER-TODO.md still lists all four U3 items as open
status=not_started cat=doc_only prio=P2 conf=high act=True [V:adjusted]
REMAINING: Strike the four items and update rows 80/86 (TASK-02 done except lazy-mount + shell size; TASK-08 done except 8.1.3-by-design + REV-11 F1/F2). Do this on main, not via the halbert-mcp worktree's stale diff.
EVID: `git show main:.handoff/MASTER-TODO.md` lines 144-147 and the dirty working-tree copy: `[ ] Settings.tsx Decomposition`, `[ ] Sidebar Navigation Consolidation`, `[ ] Rename pages/Security.tsx → Findings.tsx`, `[ ] Chat UI Sprint 1 & 2 Execution`; row 80/86 say TASK-02 'Open — 3,283 lines' and TASK-08 'Partially done'. HANDOFF-CENTRAL-TODO-BATCHES §5 said the strikethroughs 'should land at merge ti
VERIFY: adjusted — `git show main:.handoff/MASTER-TODO.md` lines 144-147 are `- [ ]` for Settings.tsx Decomposition / Sidebar Navigation Consolidation / Rename Security.tsx→Findings.tsx / Chat UI Sprint 1 & 2; row 80 'TASK-02 … **Open** — Settings.tsx now 3,283 lines'; row 86 'TASK-08 … **Partially done** … token buffer + ARIA open'. Additionally row 29 (the U3 batch row) still says 'Settings.tsx is 3,283 lines' — a
  CORRECTED_REMAINING: On main: strike lines 144-147; update rows 29, 80 and 86 (TASK-02 done except lazy-mount + shell size + REV-08 F1-F4; TASK-08 done except 8.1.3-by-design + REV-11 F1/F2 + a11y residuals). Ignore/discard the halbert-mcp worktree's stale MASTER-TODO diff.

### F20 U3-26 — Gitignored 283-line doc in chat-ui-audit worktree is not in git anywhere
status=blocked cat=needs_commit prio=P2 conf=high act=True [V:adjusted]
REMAINING: Founder/owner decision: if the doc is wanted, `git add -f` it (as 01-10 must have been) together with the README line on a branch off main; otherwise delete. Do not prune the worktree first or the file is gone.
EVID: Worktree ~/.config/superpowers/worktrees/Halbert/chat-ui-audit: README.md has a 1-line uncommitted edit adding '11. Response Modality & Conversational Style — Design Handoff (./11-response-modality-handoff.md)'. That file exists there (283 lines) but `git ls-files` returns nothing and `git check-ignore -v` reports `.gitignore:108: docs/` — it is ignored, invisible to `git status`, and absent from 
VERIFY: adjusted — Mechanics confirmed: worktree status ` M …/docs/chat-ui-audit/README.md` (adds the '11. Response Modality & Conversational Style — Design Handoff' line); 11-response-modality-handoff.md exists there (283 lines, dated 2026-08-30, 'Findings documented. Awaiting external design & UX review.'), `git ls-files` lists only 01-10+README, `git check-ignore -v` → `.gitignore:108: docs/`; main's docs/chat-ui
  CORRECTED_REMAINING: Founder/owner: confirm the 283-line precursor is subsumed by documentation/design/11-14 (same date, same subject). If yes, discard the README edit and retire the chat-ui-audit worktree (branch is 171 behind / 0 ahead). If not, `git add -f` it under documentation/design/ with a distinct name (the doc corrected_status=blocked

### F20 U3-27 — Unmerged worktree-u6-home-simplification conflicts on AgentChat.tsx
status=blocked cat=decision prio=P2 conf=high act=True [V:adjusted]
REMAINING: Not U3 work, but any REV-11 F1/F2 fix to AgentChat.tsx/useAgentStream.ts should land before or be rebased across the U6 merge to avoid a second conflict. The U6 agent owns the merge itself.
EVID: `git diff main...worktree-u6-home-simplification -- …/AgentChat.tsx` = 11 lines (useInstanceVariant + rolesForVariant into useModelPicker). `git merge-tree --write-tree main worktree-u6-home-simplification` exit 1: CONFLICT in frontend/src/components/agent/AgentChat.tsx (plus ModelSettings.tsx, halbertModelRoles.ts, deploy/README.md, deploy/halbert-home.service, context/adapters.py, context/extra_
VERIFY: adjusted — `git merge-tree --write-tree main worktree-u6-home-simplification` exit 1 with 34 CONFLICT lines (saved to scratchpad/agents/verify-pk-u3-frontend/mt-u6.txt), including AgentChat.tsx, ModelSettings.tsx, halbertModelRoles.ts(+test), useInstanceVariant.ts, deploy/*, context/adapters.py, dashboard/app.py, routes/agent.py, federation/*, model/*, 9 test files, packages/model-picker/src/types.ts — the f
  CORRECTED_REMAINING: Not U3 work. Decide U6's fate first (earlier audit: retire as superseded). Only if U6 is still to be merged do REV-11 F1/F2 fixes to AgentChat.tsx/useAgentStream.ts need sequencing against it; otherwise fix them on main freely.

### F21 RAG-01 — Daemon-side F1 (LOD skip for doc-role chunks) and F3 (scope_mode=hard exclude_paths pre-filter) are uncommitted in the CoDRAG checkout
status=in_progress cat=needs_commit prio=P1 conf=high act=True
REMAINING: In the CoDRAG repo (outside Halbert): commit the search.py/models.py/index.py edits with a test that a .md chunk survives structured mode verbatim and that scope_mode=hard returns zero chunks + scope_warning on an empty scope. Until then any checkout/stash/clean-clone launch of the daemon silently reverts Halbert to 1-chunk file-head responses and boost-only scoping (Halbert's `scope_mode` body field would be ignored).
EVID: `git -C /Volumes/4TB-BAD/HumanAI/CoDRAG log -1` = 2691fc91 (the pre-review S2 commit); `git show HEAD:src/prep/api/routers/projects/search.py | grep -c scope_mode` = 0; `git status --porcelain` shows M search.py (+85 lines), models.py (+1), core/index.py (+6), mtime 2026-08-26 10:28. Working-tree search.py:1328-1348 implements `req.scope_mode == "hard"` -> `_hard_exclude_paths`, :323-367 skips LOD
DOC: SCOPE-AXES §8.2 says scope_mode is 'live daemon-side' — true only for the dirty working tree, not for any committed CoDRAG revision.

### F21 RAG-04 — Quality gate hardened (text-only term matching, >=2 chunks, cross-platform negative probes, consistent trace_expand, envelope parsing) — but the committed report JSONs are stale
status=done cat=cleanup prio=P3 conf=high act=True
REMAINING: Re-run `scripts/corpus_quality_gate.py` (both runners) against the live daemon after RAG-05/06 land and commit fresh reports, or stop tracking the JSON reports. Note the scoped gate cannot pass until role scopes exist (RAG-05): 19 r* entries out of 43 scoped queries fail by construction against a 90% threshold.
EVID: scripts/corpus_quality_gate.py:247-253 matches terms against chunk text only, :253 `len(chunks) >= 2`, :225/:493 `trace_expand: True` in both runners, :457-464 s21-s24 negative probes, :492 `scope_mode: "hard"`; 92b840e7 (2026-08-27) fixed envelope/field parsing (+114 test lines, test_corpus_quality_gate.py passes). data/quality_gate_report.json and _scoped.json are tracked, dated 2026-08-26 12:04

### F21 RAG-05 — Role scopes (10 *_admin) registered in the template but never provisioned on the live daemon; role trees never staged or indexed
status=in_progress cat=incomplete_feature prio=P1 conf=high act=True
REMAINING: Operational: decide the TODO-ROLE-SCOPED-CONFIG §3.1 duplication question first (path masks over the flat host tree vs staged copies — staged copies go 42→99 files and break trace_expand inside role scopes because remap_edges_for_unified_root maps only to host/), then run `python -m halbert_core.integrations.sourceprep_setup apply` against the daemon and verify role scopes + files land in documents.json. Confirm the daemon's build reuses the externally-embedded 71k chunks (manifest file_hashes) before running — the staged build took ~20 h.
EVID: Template `sourceprep_template.yml:48-95` declares 14 scopes (host, network/service/storage/credentials/security/shell/package/boot/sharing_admin, 4 knowledge-*). Live `GET /projects/735a592e…/scopes` returns 6: global, host, knowledge_bsd/common/linux/macos. Staging root ~/.local/share/halbert/sourceprep/host contains only etc/ and Library/ (40 files); `ls host/{network,service,storage,credentials
DOC: REVIEW-PACKET-06 §5 and MASTER-TODO call role harvesting 'design done, harvester pending'; the harvesting code (stage_role_tree, config/roles.py) is merged — what is missing is provisioning, not code. PLAN-ROLE-SCOPED-CONFIG-HARVESTING header says 'EXECUTED AND MERGED'.

### F21 RAG-06 — Skill role -> scope bridge is inert: no template scope carries assigned_to_role, so resolve_role() always returns None and routing falls back to the keyword heuristic
status=not_started cat=incomplete_feature prio=P1 conf=high act=True
REMAINING: Add `assigned_to_role: <name>-ops` to each *_admin scope in sourceprep_template.yml (10 lines, matching skills/builtin/*/SKILL.md roles incl. security-ops, config-ops), add a test asserting every builtin skill role maps to a template scope, then run apply (RAG-05). Without this the entire skills→retrieval design and the 19 role gate queries have no production effect.
EVID: `grep assigned_to_role sourceprep_template.yml` = 0 hits; `_reconcile_scopes` reads roles only from the template spec (sourceprep_setup.py:342, :390); live daemon scopes all report `assigned_to_role: null`. All 8 builtin skills declare `role:` (skills/builtin/*/SKILL.md:8, e.g. storage-ops, network-ops, security-ops) and none declares `scope:`. `context/adapters.py:347-370` _route: role→resolve_ro
DOC: SCOPE-AXES §8.4 item 2 says routing (skills matcher) is 'the critical path' — the matcher has since landed (b17dcd5f, 2660326b, 1a0dd362, 57af6751); the role assignment step (item 3) is the remaining blocker.

### F21 RAG-07 — _reconcile_scopes can never remove paths: GET /scopes returns path_count, not paths
status=not_started cat=bug prio=P2 conf=high act=True
REMAINING: Fetch `GET /projects/{pid}/scopes/{sid}` per scope (or otherwise obtain paths) before diffing; add a test with a summary-shaped listing proving to_remove fires. Scope masks currently only grow.
EVID: Raw daemon response: `{"id":"host","display_name":"host","path_count":1,"assigned_to_role":null,"pipeline_profile":"system_config"}` — no `paths` key. `sourceprep_setup.py:361-363` `current_paths = set(rec.get("paths") or [])` → always empty → `to_add` re-sends every path on each apply and `to_remove` is always empty. Predicted unverified in TODO-ROLE-SCOPED-CONFIG §2b; now confirmed against the l

### F21 RAG-09 — Upstream CoDRAG defects noted during the cap work (hardcoded per-file dedup index.py:1425-1431; chunk metadata mislabelling)
status=not_started cat=deferred prio=P3 conf=medium act=False
REMAINING: File against CoDRAG; do not remove the per-file dedup without measuring (it is currently the only source-balancing mechanism daemon-side).
EVID: documentation/design/KNOWLEDGE-SCOPE-REVISION-2026-08-27.md 'Two upstream bugs found along the way'; neither is tracked in the CoDRAG repo (no commits since 2691fc91).

### F21 RAG-10 — Stale build-lock file and handoff status headers (CODEINDEX-BUILD-LOCK.txt says a build is running; it finished 2026-08-26)
status=obsolete cat=cleanup prio=P3 conf=high act=True
REMAINING: `git rm .handoff/CODEINDEX-BUILD-LOCK.txt`; add a one-line 'executed 2026-08-26' banner to the three handoffs.
EVID: .handoff/CODEINDEX-BUILD-LOCK.txt is tracked and says 'PID 66131 … IN PROGRESS — DO NOT INTERRUPT'; `ps -p 66131` → no such process; no staged_knowledge_embed process running; index built_at 2026-08-26T16:03Z. OPUS-HANDOFF-REMAINING-WORK O1 'RUNNING NOW, DO NOT START', HANDOFF-RAG-ARCHITECTURE-REVIEW 'CodeIndex build in progress', HANDOFF-STAGED-CODEINDEX-BUILD 'Ready to execute' are all supersede

### F21 RAG-11 — Corpus licence policy engine and build-time distribution gates
status=done cat=security prio=P2 conf=high act=True
REMAINING: Not a CI gate: .github/workflows/ci.yml has no corpus_license_gate step (only contrast/shadcn/literal-colour/fonts). Consider adding `corpus_license_gate.py --coverage --all-channels` to CI.
EVID: deb22b1a (2026-08-25): halbert_core/corpus/license_policy.py (LicensePolicy, audit_tree, assert_tree_clean, coverage_gaps), scripts/corpus_license_gate.py, config/licensing.yml; wired into scripts/build-macos.sh:141 (--coverage), :150 (--print-paths), :182 (--bundle audit). Ran read-only: `corpus_license_gate.py --coverage` exit 0 ('macos-command-reference: quarantined content is 100% replaced, no

### F21 RAG-12 — Dependency licence manifest is red: 10 dependencies unregistered in config/dependency-licenses.yml (App Store dependency check fails)
status=not_started cat=bug prio=P1 conf=high act=True
REMAINING: Verify each upstream licence and register the 10 entries (three are first-party workspace packages: halbert-core, @halbert/design-system, @halbert/model-picker). Rust audio crates (cpal, webrtc-audio-processing) and Python audio/vision deps need real classification; do not guess. Re-run the two tests.
EVID: `pytest halbert_core/tests/test_corpus_license_gate.py::test_real_dependency_manifests_pass_the_app_store_check ::test_every_declared_dependency_is_registered` → 2 failed on main; scripts/check_appstore_deps.py output: BLOCKING python:halbert-core, python:mss, python:opencv-python, python:sherpa-onnx, python:openwakeword, python:pyacoustid, rust:cpal, rust:webrtc-audio-processing, npm:@halbert/des

### F21 RAG-13 — Blanket *.jsonl gitignore hides 13 corpus files (71 MB incl. macOS man pages, Arch Wiki, tldr); a fresh clone cannot rebuild the knowledge corpus; HF publishing never done
status=not_started cat=decision prio=P1 conf=high act=True
REMAINING: Founder decision: (a) track the 13 files (repo +71 MB) with negated patterns or a narrower ignore, or (b) publish the three HF datasets via scripts/upload_hf_dataset.py and populate manifest remote_url/check_updates_url, and make jsonl_to_markdown/onboarding download them. Either way fix documentation/RAG-DATA-SOURCES-2026-08-24.md §1.1.
EVID: .gitignore:123 `*.jsonl` (`git check-ignore -v` confirms for data/common/docker-docs/docker_docs.jsonl and data/linux/arch-wiki/arch_wiki.jsonl). `git ls-files | grep .jsonl$` = 45 files (24 MB); `find data -name '*.jsonl'` = 58. Untracked: data/macos/man-pages/macos_man_pages.jsonl (44 MB), data/linux/arch-wiki/arch_wiki.jsonl (18 MB), data/common/tldr (5 MB), data/linux/tldr (2 MB), devtools-doc
DOC: RAG-DATA-SOURCES §1.1 claims 'All 53 JSONL data files … are committed to git — no download or scraping step is required'. Reality: 45 tracked, 13 ignored, 58 on disk.

### F21 RAG-14 — No way for a new install to obtain the knowledge index (pre-built index distribution / background build) — RAG only works on the dev machine
status=not_started cat=incomplete_feature prio=P1 conf=high act=True
REMAINING: Decision + build: ship the built index directory (embeddings.npy 218 MB, documents.json 106 MB, fts.sqlite3 166 MB) as a versioned release/HF asset that sourceprep_setup installs, or provide a UI-driven background build with progress. Then rewrite or delete prebuilt-knowledge-index.md.
EVID: Staged embed took ~20 h across 3 stages (HANDOFF-SCOPE-FILTER-REVIEW 'What was accomplished'). grep for prebuilt/download/huggingface in sourceprep_setup.py, routes/downloads.py, routes/settings.py = 0 hits; nothing in dashboard/app.py, routes/*.py or Halbert/main.py invokes SourcePrepSetup.apply. documentation/design/prebuilt-knowledge-index.md proposes a two-project embedded-mode split that cont
DOC: prebuilt-knowledge-index.md 'Why Not One Unified Project?' argues against the architecture that actually shipped.

### F21 RAG-15 — Operational gate: rebuild the SourcePrep index unredacted (MASTER-TODO item) — script exists, run status unknown
status=unknown cat=deferred prio=P2 conf=medium act=True
REMAINING: Decide whether to stage unredacted (egress redaction must then be verified — the security-review-01 branch's redactor hardening is the related unmerged work), run the script, record the result, and tick MASTER-TODO. Fix MASTER-TODO line 27 which claims the script is still missing.
EVID: scripts/rebuild_sourceprep_unredacted.py exists (U1 batch 5a132684). MASTER-TODO (HEAD) line 104 '[ ] Rebuild index unredacted (operational gate)' unchecked; line 27 still lists the script as 'remaining' (stale). apply() default `redact_host=True` (sourceprep_setup.py:182). Staged host tree has 0 files containing '[redacted]' — cannot tell whether it was staged unredacted or nothing matched.
DOC: MASTER-TODO U1 row says `scripts/rebuild_sourceprep_unredacted.py` is remaining; it exists on main.

### F21 RAG-16 — Phase V daemon-pipeline verifications T-V.0/T-V.1/T-V.3/T-V.5 never recorded as run
status=unknown cat=test_gap prio=P3 conf=medium act=False
REMAINING: Either run the T-V.1 (trace_epistemic host-only), T-V.3 (host drop-in trace_expand) and T-V.5 (cluster/group reasoning) checks against the live daemon and record them, or close the handoff as superseded.
EVID: .handoff/PHASE-V-VERIFICATION-HANDOFF-2026-08-24.md still says BLOCKED on an old daemon; the daemon now runs from the CoDRAG checkout at 2691fc91 (includes S1/S2). grep for T-V.1/T-V.3/T-V.5 results across .handoff and documentation finds only the handoff and the plan — no result doc. T-V.2 is realised by the scoped gate queries; T-V.4 done. Atlas/trace manifests in the project dir are dated 2026-
DOC: Handoff says the daemon runs 'OLD code (Prep 0.1.0)'; it now runs the post-S2 checkout (still reports version 0.1.0).

### F21 RAG-18 — Corpus automation and coverage backlog (missing refresh scripts, HF datasets, Debian/Gentoo/RHEL coverage) plus stale data/staging/sourceprep mirror
status=not_started cat=deferred prio=P3 conf=high act=False
REMAINING: Deferred by the founder's priority (complete current features first). Local cleanup only: delete data/staging/sourceprep; update RAG-DATA-SOURCES §1.2/§5.4.
EVID: documentation/RAG-DATA-SOURCES-2026-08-24.md §5.4: scripts/tldr_to_jsonl.py, scripts/update_manifest.py, scripts/refresh_all.sh still missing (ls confirms); §5 automation pipeline marked Future; §7.2 gaps (Debian, Gentoo, OpenBSD/NetBSD) open; KNOWLEDGE-SCOPE-REVISION: RHEL/Fedora `rpm -qa` appears in zero files. data/staging/sourceprep (87 MB, gitignored via .gitignore:136) is the old bridge desc
DOC: RAG-DATA-SOURCES §1.2 describes data/staging/sourceprep as the SourcePrep bridge; the live bridge is ~/.local/share/halbert/sourceprep.

### F21 RAG-19 — documentation/GAPS.md is obsolete (Dec 2025, ChromaDB/chat.py era) and makes false claims about the current tree
status=obsolete cat=doc_only prio=P2 conf=high act=True
REMAINING: Retire GAPS.md from the public documentation/ folder or regenerate it from this audit; update guides/dashboard-pages.md page list.
EVID: GAPS.md cites `SidePanel.tsx` (deleted: ls → no such file), `chat.py` as a key route (retired in 5141cfe1; absent from dashboard/routes/), `runtime/langgraph_engine.py`/`LGEngine` (no such file; grep for LGEngine|langgraph in halbert_core = 0), `useChatStream()` WebSocket hook (hooks/ has only useAgentStream.ts; SSE is the live path; WebSocket is used for /ws/terminal/{id}), a 'Security' page (no 
DOC: See evidence — at least seven concrete claims reference files/routes that do not exist on main.

### F21 RAG-20 — documentation/RAG_AUDIT_REPORT.md describes the retired ChromaDB chat RAG path as production
status=obsolete cat=doc_only prio=P3 conf=high act=True
REMAINING: Mark superseded or delete; if kept, add a banner pointing to the SourcePrep design docs.
EVID: Dated Dec 17/19 2024; diagram 'Chat Route (chat.py) → get_docs_context() → Document Indexer → ChromaDB linux_docs'. On main the agent path uses SourcePrepAdapter only (dashboard/routes/agent.py:141-150; context/adapters.py:307+), RAGServiceAdapter is deprecated (context/adapters.py:23-44), chat.py is gone. Its items #6 BM25 tokenizer, #9 dedup, #11 graph, #12 hardcoded model names all live in rag/

### F21 RAG-21 — Two knowledge systems still exposed to users: legacy ChromaDB doc indexing (routes/rag.py, /settings/docs/*, Settings UI, CLI rag-add) no longer feeds the agent
status=unknown cat=decision prio=P2 conf=high act=True
REMAINING: Founder decision: retire the ChromaDB doc-index surface (routes/rag.py, /settings/docs/*, Settings Knowledge indexing UI, CLI rag-add, rag/{document_indexer,raptor,graphrag,pipeline,retriever}.py, tests/rag/) or re-point 'add a URL/doc' at SourcePrep staging so user-added docs actually influence answers.
EVID: routes/rag.py registered at dashboard/app.py:283 (/api/indexes, /api/add, /api/documents, /api/merge, /api/trending…); routes/settings.py `/settings/docs/index` and `/docs/stats` are called from Settings.tsx:304,560 (POST docs/index?max_docs=10000),592 and Layout.tsx:313; Halbert/main.py:2122-2187 `rag-add`/`rag-sources`; rag/document_indexer.py, raptor.py, graphrag.py, pipeline.py import ChromaDB

### F21 RAG-22 — Keyword scope routing quality (O4) never evaluated; heuristic remains the effective router while roles are unassigned
status=not_started cat=test_gap prio=P3 conf=medium act=False
REMAINING: After RAG-06, run the O4 query battery through SourcePrepAdapter._route and record which scope each query resolves to; only then tune the heuristic.
EVID: OPUS-HANDOFF-REMAINING-WORK O4 has no recorded report; `scope_for_query` (sourceprep_retrieval_backend.py:140-183) is the fallback in context/adapters.py:369-370 and, given RAG-06, the router for every turn. agent.py:70 adds an explicit per-turn `scope` request field (SCOPE-AXES §0d item 4 partially done).

### F21 RAG-23 — Known role-scope limitations carried forward (duplicated role trees break trace_expand; RoleScope.aliases_from has no consumer; plist integer redaction yields invalid plist; schemeless URL credentials not redacted; fnmatch * crosses /)
status=not_started cat=deferred prio=P2 conf=medium act=True
REMAINING: Item 1 must be decided before RAG-05 provisioning; items 2-3 are narrow redaction correctness bugs worth folding into the security-review work; item 4 is a KeyError trap for a future ROLES[alias] call.
EVID: .handoff/TODO-ROLE-SCOPED-CONFIG-2026-08-27.md §3 items 1-6; config/roles.py RoleScope with file_backed_platforms (:62-165); none addressed in later commits (git log on config/roles.py, tools/register_host_project.py shows no follow-up).

### F22 U6-01 — Retire branch worktree-u6-home-simplification and its worktree (fully superseded by feat/ha-simplification on main)
status=obsolete cat=retire prio=P1 conf=high act=True
REMAINING: Founder: git worktree remove /Volumes/4TB-BAD/Halbert/.claude/worktrees/u6-home-simplification && git branch -D worktree-u6-home-simplification. Nothing to salvage first (see U6-26..U6-28 for the three trivial residues, all easier to re-do on main than to port).
EVID: git log --oneline main..worktree-u6-home-simplification = 16 commits (8fbf23ee..12e31380), merge-base 24eb91aa; main has the same workstream via a161bb9a, 6a077653, 226555ef, d733ec9a, 5e2ce6b4, 6f46f09a, 5f87520c, 0514a5c3, 3ce98551, 092117dd, 8545af94 (git log main --grep=U6). git merge-tree --write-tree main worktree-u6-home-simplification -> exit 1, 34 CONFLICT lines. Worktree is clean (git -C

### F22 U6-17 — 12e31380 HANDOFF-U6-S3-COMPUTE-PEER-2026-08-30.md (remaining-work handoff)
status=obsolete cat=doc_only prio=P3 conf=high act=False
REMAINING: 
EVID: File exists only on the branch (not on main). Its § 2 lists W14/W16/W15/W19 as remaining and § 1 says 'Decision still open: D4' — all done on main (U6-21..U6-24; D4 resolved 8545af94 'merge home-light into home (D4)', VALID_VARIANTS = {sysadmin, home} at being_config.py:36). Its § 4 errata about the D4 service matrix is moot post-D4. Main already carries HANDOFF-HA-SIMPLIFICATION-CONTINUE-2026-08-
DOC: Claims W14/W15/W16/W19 remain and D4 is open; on main all four are shipped (0514a5c3, 5f87520c, 6f46f09a) and D4 was resolved in 8545af94.

### F22 U6-19 — Merge dry run: 34 conflicting files against main
status=blocked cat=retire prio=P3 conf=high act=False
REMAINING: None: do not merge; retire (U6-01).
EVID: git merge-tree --write-tree main worktree-u6-home-simplification -> exit 1; 34 CONFLICT lines: 4 add/add (useInstanceVariant.ts, halbertModelRoles.test.ts, test_compute_router_route.py, test_sbc_offload_only.py) + 30 content conflicts spanning federation/*, model/*, context/*, dashboard routes, deploy/*, packages/model-picker/src/types.ts and 8 test files. Full list saved at /private/tmp/claude-50

### F22 U6-24 — MASTER-TODO.md on main still lists D1, S3, S4, S6 as unchecked although all are shipped
status=done cat=doc_only prio=P2 conf=high act=True
REMAINING: Tick D1/S3/S4/S6 in MASTER-TODO.md and drop the stale 'peer is missing from CHAT_CAPABLE_PROVIDERS' prerequisite text. Coordinate with the session that currently has MASTER-TODO.md modified in the main tree.
EVID: git show main:.handoff/MASTER-TODO.md: :129 '- [ ] D1', :132 '- [ ] S3 ... peer is missing from CHAT_CAPABLE_PROVIDERS', :133 '- [ ] S4', :156 '- [ ] Apple Intelligence local-only scoping (S6)'. Reality: D1 a161bb9a, S3 0514a5c3+5f87520c, S4 6f46f09a, S6 6a077653, all on main. The main working-tree copy (dirty, another session) still has :132 unchecked; the halbert-mcp worktree also has an uncommi
DOC: MASTER-TODO claims S3/S4/S6/D1 open; code and git on main show them complete.

### F22 U6-25 — tier_router.from_legacy resolves a 'secure' value it never uses (dead code the branch removed)
status=not_started cat=cleanup prio=P3 conf=high act=True
REMAINING: Delete lines 151-162 of tier_router.py (or keep only a comment). Trivial; do on main rather than porting.
EVID: main model/tier_router.py:151-162 computes `secure = _resolve_slot('secure_model') if _has_secure_cap else None`; `awk 'NR>162 && /secure/'` over the file returns nothing, so the value (and the capability lookup feeding it) is unused. Branch ef34ae4c deleted it with a comment explaining the tier router never routes to the secure slot.

### F22 U6-26 — Stale 'three slots' comment in config_wizard.validate_config
status=not_started cat=cleanup prio=P3 conf=high act=True
REMAINING: One-line comment fix on main.
EVID: main model/config_wizard.py:692 '# Check llm_config has the three slots' directly above a loop over four slots (chat_model, specialist_model, vision_model, secure_model). Branch ecc3bccd changed it to 'all four slots'.

### F22 U6-27 — Test gap: no main test pins that a secure turn skips the dedicated secure slot when CAP_SECURE_MODEL is absent
status=not_started cat=test_gap prio=P3 conf=medium act=True
REMAINING: Add two tests to test_agent_model_override.py that patch halbert_core.capabilities.has_capability (or the registry) to False/True and assert _resolve_turn_model(COMPLEX, secure=True) ignores/uses the dedicated slot respectively.
EVID: main routes/agent.py:508-521 skips get_secure_model() unless has_capability(CAP_SECURE_MODEL); main test_agent_model_override.py TestSecureTurn (:255-300) only exercises the configured path and never patches has_capability (git grep has_capability in that file: none). Branch had test_home_variants_ignore_the_dedicated_secure_slot / test_sysadmin_variant_uses_the_dedicated_secure_slot, but they mon

### F22 U6-28 — Post-D4 leftover: llm_config still checks for the retired 'home-light' variant
status=not_started cat=cleanup prio=P3 conf=high act=True
REMAINING: Change to `== "home"` (or use has_capability). Cosmetic; discovered incidentally, not from this branch.
EVID: main model/llm_config.py:816 `if _get_variant() in ("home", "home-light")` (HALBERT_MODEL env override, 7c70276d); being_config.py:36 VALID_VARIANTS = {"sysadmin", "home"} since 8545af94. Only remaining 'home-light' reference in halbert_core code (git grep count = 1 file).

### F22 U6-29 — ComputeRouter deferred-turn replay (federation-9.6) unimplemented on both branch and main
status=not_started cat=deferred prio=P3 conf=high act=False
REMAINING: Implement the deferred-queue drain when the peer transitions offline->online (or when cloud returns), plus re-enable the split-brain tests. Not branch-specific; belongs to the federation backlog.
EVID: Branch compute_router.py:416-426 replay_deferred() raises NotImplementedError (scaffold from merge base); branch test_split_brain.py:25-55 skips 6 tests on it. main compute_router.py:304 keeps `_deferred_queue: list = []  # TODO(federation-9.6)` and has no replay method at all (git grep replay_deferred main: none). route() marks turns deferred=True (main :522-523) but nothing drains the queue.

### F22 U6-30 — stash@{0} 'duplicate U6-S3 compute-peer work' is redundant with main
status=obsolete cat=cleanup prio=P3 conf=high act=True
REMAINING: Founder: git stash drop stash@{0} (read-only audit did not touch it).
EVID: git stash show -p stash@{0}: 3-line change to model/client.py adding 'peer' to CHAT_CAPABLE_PROVIDERS with a comment. main client.py:72-77 already has exactly that (0514a5c3). Stash message itself says 'wrong task, other session owns this'.

### F22 U6-31 — Baseline failure seen while verifying: test_multi_instance::test_instance_info_home (stale test, pre-existing on main)
status=unknown cat=test_gap prio=P3 conf=medium act=False
REMAINING: Update the test to set HALBERT_VARIANT=home (or a being.yml) alongside the persona env; out of this branch's scope.
EVID: arch -arm64 .venv/bin/python -m pytest halbert_core/tests/test_multi_instance.py::TestInstanceInfoEndpoint::test_instance_info_home -> AssertionError: assert 'host' == 'home' (:104). Listed in the known baseline at scratchpad/pytest-main.txt:122. main routes/instance.py:31-38 derives role from the variant (REV-03 F8), while the test only sets the persona env, so the test is stale rather than the r

### F23 SEC-01 — c5b6bb91 — MCP path allowlist for config-query tools (genuinely missing on main)
status=done cat=merge_ready prio=P1 conf=high act=True
REMAINING: Merge feat/security-review-01 into main. Resolve the single conflict in halbert_core/tests/test_mcp_server.py by keeping BOTH sides: main's TestAutonomyEscalationPhrase + TestHighRiskProposalPhrase (from 0f750c3a) followed by the branch's TestPathAllowlist; the two `_load_latest_snapshot` monkeypatch inserts in TestTierRouting/TestEgressBoundary auto-merge. Keep main's TestProtocol (18 tools). Then run test_mcp_server.py, test_redaction_gaps.py, test_tier2_guarantee.py, test_mcp_response_boundary.py, test_mcp_http.py, test_security_roles.py, test_config_queries.py. Optional polish: _is_allowed
EVID: `git diff main...feat/security-review-01 -- halbert_core/halbert_core/mcp/server.py` adds _is_allowed_config_path() (realpath match against config.queries._load_latest_snapshot()) and gates _tool_get_config_value/_tool_get_config_structure/_tool_get_config_dependencies before any file access. `grep -n _is_allowed_config_path halbert_core/halbert_core/mcp/server.py` on main → no match; main's handl
DOC: Earlier audit today said 'merge-tree is clean' — false as of 0f750c3a (2026-08-31): `git merge-tree --write-tree main feat/security-review-01` → EXIT=1, 'CONFLICT (content): Merge conflict in halbert_core/tests/test_mcp_server.py'. Earlier audit's 'branch tests 73/73' could not be re-verified on bra

### F23 SEC-02 — Arbitrary file read + canon-DB pollution via MCP config-query tools on CURRENT main (closed by SEC-01)
status=in_progress cat=security prio=P1 conf=high act=True
REMAINING: Closed by merging c5b6bb91 (SEC-01). No separate work.
EVID: main halbert_core/halbert_core/config/queries.py:102-122 _get_current_canon(path): `_live_hash(path)` (opens and hashes any existing file, :86-98) then `parse_config(path)` when no canon hash exists, then `_write_canon(path, live_hash, canon)` (:128-145) writes <hash>.json into CANON_DIR and `_update_latest_snapshot` (:148-165) appends {path, hash} to SNAP_DIR/latest.json. server.py:188-256 forwar

### F23 SEC-03 — 9e057db7 — redactor hardening: base64 8192-char cap + depth-2 recursion cap, nested-JSON leaf walker
status=done cat=merge_ready prio=P2 conf=high act=True
REMAINING: Merge with SEC-01 (same branch, no conflict in this file). Nothing else; treat as defence-in-depth. The progress doc's 'MEDIUM DoS' framing overstates it — the cap saves ~0.5s/MB, the remaining ~0.9s is the rest of the pipeline on the same text.
EVID: `git diff main...feat/security-review-01 -- halbert_core/halbert_core/ingestion/redaction.py` (+125/-16); main's redaction.py:1221-1311 has none of _B64_MAX_TOKEN_CHARS/_B64_MAX_DEPTH/_NESTED_JSON_WHOLE_MAX/_redact_json_leaves; no main commit touched redaction.py since merge-base (`git log da75bca1..main -- ...redaction.py` empty). BUT all 9 new tests (TestNestedJsonHardening, TestBase64Hardening)
DOC: SCOPE-01-SECURITY-REVIEW-PROGRESS.md §2 #6 presents this as closing a leak; the tests do not distinguish main from branch, so it is hardening only.

### F23 SEC-04 — a09632e1 — .handoff/SCOPE-01-SECURITY-REVIEW-PROGRESS.md (committed on branch, not on main)
status=done cat=doc_only prio=P3 conf=high act=True
REMAINING: Merges with the branch. After merge, update it: (a) §6 'ready to merge, clean' → note the test-file conflict resolution; (b) add Effort B's main-side work (5a132654 dispatch exception redaction + test_tier2_guarantee/test_security_roles/test_cli_security; REV-01 fixes 74401f12/51082f83/360effab/7e9ebaae; REV-02 fixes 0f750c3a/cb69442f); (c) §4 items 2 and 3 remain open (see SEC-11).
EVID: `git show feat/security-review-01:.handoff/SCOPE-01-SECURITY-REVIEW-PROGRESS.md`; `git ls-tree main .handoff | grep SCOPE-01` → 0. Its 5 'already merged' shas (06e113cc, 4db888a9, f800789c, da75bca1, 78e9d141) verified as ancestors of main. §5 '458 passed' was run under a Python 3.9 conda env (doc §5 note), not the project venv (>=3.10 per CLAUDE.md); in the project venv test_security_unlock_phras

### F23 SEC-05 — DECISION: allowlist fails closed on hosts with no snapshot manifest (macOS never starts the ConfigWatcher)
status=not_started cat=decision prio=P1 conf=high act=True
REMAINING: Founder call: (a) accept fail-closed as the intended posture ('MCP may only read what the host staged') and add a snapshot step to onboarding/first-run on macOS (or a dashboard 'stage config' action) so MCP config tools work out of the box; or (b) relax the gate to an explicit allow-root policy. Recommend (a); document the precondition in the get_config_* tool descriptions (server.py:766-800) so an MCP client sees why it was refused.
EVID: Branch server.py _is_allowed_config_path returns False for every path when _load_latest_snapshot() is empty (SNAP_DIR/latest.json absent → [] at queries.py:55-64). latest.json is written only by config/snapshot.py:133-135 (snapshot()), the lazy _write_canon path in queries.py (which the gate now blocks for MCP), and scripts/rebuild_sourceprep_unredacted.py. snapshot() is invoked by ConfigWatcher (

### F23 SEC-06 — Untracked .handoff/SCOPE-01-DUPLICATE-WORK-RECONCILIATION.md in worktree — mostly executed, one claim now false
status=obsolete cat=retire prio=P3 conf=high act=True
REMAINING: Do not commit as-is. Either delete it, or fold its two live items (merge branch; update progress doc) into SCOPE-01-SECURITY-REVIEW-PROGRESS.md and delete it.
EVID: File mtime 2026-08-31 08:35, 6.3KB, not on main. Its plan: Step 1 merge this branch (still pending = SEC-01); Step 2 cherry-pick 5a132654 → already on main (`git merge-base --is-ancestor 5a132654 main` true, via f112151b); Step 3 cherry-pick 5057e893 → that sha is NOT on main but its content landed as 31fa91ef (.handoff/REVIEW-RESULTS-REV-02-2026-08-31.md exists on main); Step 4 REV-02 F1 fixed 0f

### F23 SEC-07 — Untracked .handoff/HANDOFF-HOME-AUTOMATION-SIMPLIFICATION-2026-08-30.md in worktree — obsolete pre-revision draft of a file main already has
status=obsolete cat=retire prio=P3 conf=high act=True
REMAINING: Delete the worktree copy. Committing it would regress main's corrected document.
EVID: Worktree copy: 408 lines, mtime 2026-08-30 19:39, header 'Status: Architectural Feedback & Simplification Proposal'. Main's copy (added 1fd6dba1, 2026-08-30, 485 lines) carries 'code-verified revision same day — see Section 12' plus inline 'Code-verified correction' blocks. diff main-copy vs worktree-copy: 122 main-only lines, 45 worktree-only lines; the worktree-only lines are the pre-correction 

### F23 SEC-08 — Worktree stray: node_modules symlink into the main tree (shows as untracked)
status=done cat=cleanup prio=P3 conf=high act=True
REMAINING: Remove the symlink in the worktree before any `git add -A` there (or it will be committed as a symlink).
EVID: `git -C <worktree> status --porcelain` → '?? halbert_core/halbert_core/dashboard/frontend/node_modules'; readlink → /Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend/node_modules (0B symlink). .gitignore line 69 'node_modules/' is a directory pattern, so a symlink (file entry) is not ignored ('pathspec ... is beyond a symbolic link').

### F23 SEC-09 — REV-02 low/latent findings still open on main: F6, P1-P5
status=not_started cat=deferred prio=P3 conf=high act=True
REMAINING: Small batch: P1 iterate over list(self._peers.values()); P2 throttle update_last_seen by monotonic timestamp; P3 reject tools/call notifications with -32600; P4 cap stdin line length; P5 case-insensitive scheme match. F6 is a design decision (outbound credential store) to make before implementing the fleet proxy — no code yet.
EVID: F6 (FleetProxy needs raw peer token, PeersConfig stores hashes): federation/fleet_proxy.py still has 5 NotImplementedError stubs. P1: peers_config.py:330-347 verify_token still iterates self._peers.values() lock-free while add_peer mutates in place. P2: peer_middleware.py:159-161 still calls config.update_last_seen() synchronously per request with 'TODO(federation-9.1): make this async / throttled

### F23 SEC-10 — REVIEW-PACKET-01 §5 operational gates still open: unredacted SourcePrep index run + live scanner egress test
status=not_started cat=test_gap prio=P2 conf=high act=True
REMAINING: (1) Run scripts/rebuild_sourceprep_unredacted.py against the live daemon with PREP_DAEMON_TOKEN; exit 2 means the egress check failed. (2) Write/run a scanner egress test: seed mock API keys, run each macOS discovery scanner, assert nothing raw leaves mcp_response/secure routing.
EVID: .handoff/REVIEW-PACKET-01-SECURITY-AND-TRUST-BOUNDARY.md §5 items 2-3; REVIEW-RESULTS-REV-01-2026-08-31.md §4: 'scripts/rebuild_sourceprep_unredacted.py now exists ... run it after F1's invariant is settled' (F1 settled by 74401f12) and '§5.3 live scanner egress testing: not done'. scripts/rebuild_sourceprep_unredacted.py exists on main (5a132654). No test under halbert_core/tests references keych

### F23 SEC-11 — MASTER-TODO.md / TASK-PACKET-09 claim security tests 'do not exist' and TASK-09 verification open — stale
status=done cat=doc_only prio=P3 conf=medium act=True
REMAINING: Whoever owns the current MASTER-TODO.md edit: mark TASK-09 complete, drop 'do not exist' for the two files that exist, note test_redactor.py is intentionally absent; add SEC-05 decision and SEC-09/SEC-10 as the remaining U1 items.
EVID: main .handoff/MASTER-TODO.md:27,41,87 and TASK-PACKET-09 status line say test_tier2_guarantee.py/test_security_roles.py/test_redactor.py do not exist and Task 9.2 verification remains. On main: halbert_core/tests/test_tier2_guarantee.py, test_security_roles.py, test_cli_security.py exist (5a132654, 2026-08-31); test_tier2_guarantee.py pins the dispatch choke point (Task 9.2's dispatcher assertion)
DOC: MASTER-TODO.md:27/41/87 and TASK-PACKET-09 say the three security test files do not exist and Task 9.2 is open; two of the three exist and are the Task 9.2 assertions.

### F24 FE-06 — Tauri src-tauri crate compiles test binaries offline with 0 warnings (tests not executed per scope)
status=done cat=merge_ready prio=P2 conf=high act=True
REMAINING: Run `cargo test --offline` (not done here by instruction) to confirm the 28 Rust unit tests actually pass; no CI job runs cargo at all (.github/workflows/ci.yml has no Rust job).
EVID: src-tauri/target/ existed (4.8G). `cargo test --offline --no-run` (cargo 1.98.0) -> "Finished `test` profile ... in 51.33s", exit 0, `grep -c '^warning'`=0, produced target/debug/deps/test_halbert_lib-291e6cd8560c4e3b and test_halbert-701309be29dc51f8. 28 `#[test]`/`#[cfg(test)]` attributes across src/lib.rs, src/hud_hotkey.rs, src/audio_capture.rs, src/floating_panel.rs (2158 lines total).

### F24 FE-07 — Uncommitted HalbertMark line-count tiers (3/4/5/6/7/8/10 + `lines` prop) on main are finished, green, and backward-compatible
status=done cat=needs_commit prio=P1 conf=high act=True
REMAINING: Commit (the other session's work — do not touch from this audit). Before committing, fix docstring typo at HalbertMark.tsx:45 "Overrides  if provided." (missing the word `density`), and add the 35 new -Nlines SVGs to assets/brand/README.md (README has no mention of 'lines'). No non-story consumer uses `lines` yet.
EVID: `git diff --stat` on main: packages/design-system/src/primitives/HalbertMark.tsx (+164/-), src/stories/HalbertMark.stories.tsx (+178/-), src/test/primitives.test.tsx (+11). New CONFIG_BY_LINE_COUNT + resolveLineCount() keep 'display'/'medium'/'compact'/'small' aliases and still emit hb-mark--display/--medium/--compact/--small classes alongside hb-mark--Nlines (diff hunk at className cx(...)). Exis
DOC: .handoff/HANDOFF-BRANCH-AND-WORKTREE-AUDIT-2026-09-01.md:25 says '23/23 tests pass, tsc --noEmit clean, 35 new brand SVGs' — verified correct — but omits the untracked duplicate dashboard/frontend/src/components/brand/HalbertMark.tsx (see FE-09).

### F24 FE-08 — Decision pending: adopt 7-line mark as primary / 4-line as micro (story labels them 'Proposed Primary' / 'Proposed Micro'); voice geometry cannot render 7 or 8 lines
status=in_progress cat=decision prio=P2 conf=medium act=True
REMAINING: Founder decides whether 7-line becomes the primary mark. If yes: change 'auto' thresholds, update the 2 dashboard + 1 marketing call sites, add a 7-line VoiceDensity (lanes=6) to voice/geometry.ts (note feat/voice-mode-mark-v2 commit 25213235 also rewrites geometry.ts — coordinate), regenerate favicons. If no: leave 'auto' as is and treat the extra tiers as options.
EVID: Uncommitted HalbertMark.stories.tsx OpticalTiers render: LINE_COUNTS entries `{ count: 7, ... candidate: 'Proposed Primary' }`, `{ count: 4, ... candidate: 'Proposed Small' }`, `{ count: 8, ... candidate: '8-line alternative' }`; 'auto' density still resolves to 3/6/10 (resolveLineCount: size<=24->3, <=64->6, else 10). packages/design-system/src/voice/geometry.ts:32 `export type VoiceDensity = 'me

### F24 FE-09 — Untracked, unreferenced duplicate HalbertMark.tsx in dashboard/frontend/src/components/brand/
status=unknown cat=cleanup prio=P2 conf=high act=True
REMAINING: Decide: delete it (dashboard already consumes @halbert/design-system) or, if it was meant to decouple the app from the package, wire it and add a test. As-is it is dead code that will drift from the design-system copy.
EVID: `git status --porcelain` -> `?? halbert_core/halbert_core/dashboard/frontend/src/components/brand/` containing one file HalbertMark.tsx (6546 bytes, Sep 1 08:41). It is a self-contained copy of the new design-system component (same HalbertMarkDensity union incl. '10'..'3', `lines?: 3|4|5|6|7|8|10`; no `cx` import; docstrings stripped). Nothing imports it: grep for `components/brand`/`from './brand

### F24 FE-10 — CI literal-colour ratchet FAILS on main: 11 dashboard files gained literal Tailwind palette classes since the 2026-08-27 baseline
status=not_started cat=bug prio=P1 conf=high act=True
REMAINING: Either replace the new literal classes in those 11 files with the semantic tokens the script names (bg-background, text-foreground, text-muted-foreground, border-border, text-success/-warning/-error/-info) or, if the debt is accepted, run `scripts/check_literal_colors.py --baseline` and commit the regenerated .literal-colors-baseline.json. Most of the growth came from the merged fleet/audio/devices/settings branches (commits above).
EVID: `arch -arm64 .venv/bin/python scripts/check_literal_colors.py --check` -> exit 1, "FAILED — files gained literal palette classes:" StateBadge.tsx 7->12 (e52e5516 2026-08-30), audio/AcousticAnomalyModule.tsx 0->9 (2033ad79 08-31), audio/AcousticAuraIndicator.tsx 0->4 (9f001d00 08-31), audio/VoiceEnrollmentModal.tsx 0->3 (384364c6 08-29), fleet/DiscoveredPeerCard.tsx 0->2 (6a077653 08-30), fleet/Nod

### F24 FE-14 — design-system unit-test gaps: 7 primitives and 3 surfaces have no tests
status=not_started cat=test_gap prio=P3 conf=high act=True
REMAINING: Add render/a11y tests for the 10 untested components (NavRail and DiffBlock are used by the dashboard shell and agent chat, so start there).
EVID: describe blocks in src/test/*.test.ts(x): Button, StatusBadge, Input, Select, ParametricSlider, HalbertMark (primitives.test.tsx), AppWindow, MetricCard (surfaces.test.tsx), AudioReactiveHalbertMark, voice geometry/springs/spectrum. Untested exports: WhyChip, StatusLight, EmptyState, ModuleLoadError, Collapsible, CollapsibleGroup (primitives); ThinkingPanel, DiffBlock, DiffSummary, NavRail (surfac

### F24 FE-15 — Dashboard test coverage is thin: 35 of 136 components/pages have a sibling test; all 16 pages untested
status=not_started cat=test_gap prio=P2 conf=high act=True
REMAINING: Given the founder priority (current features tested), the highest-value gaps are the recently merged feature surfaces with zero tests: fleet/NodeFleetCockpit + DiscoveredPeerCard, settings/tabs (9 files incl. VisionTab), pages/Findings, pages/Home, pages/Terminal, and audio/VoiceEnrollmentModal.
EVID: find src/components src/pages -name '*.tsx' ! -name '*.test.tsx' = 136; those with a matching *.test.tsx or *.<x>.test.tsx = 35. Untested pages: Approvals, Apps, Backups, Containers, Dashboard, Development, Findings, GPU, Home, Jobs, Memory, Network, Services, Sharing, Storage, Terminal. Untested by dir: components/ui 19, pages 16, components/agent 13, components/domain 12, components/ (top) 10, s

### F24 FE-16 — Playwright e2e smoke scripts exist but are not run by CI and were not run here (need live backend + dev server)
status=blocked cat=deferred prio=P3 conf=high act=True
REMAINING: Run manually against a live backend before any release; consider a mocked-backend variant for CI.
EVID: halbert_core/halbert_core/dashboard/frontend/e2e/plan-b.smoke.mjs and e2e/continuity.smoke.mjs; headers say "Needs the `playwright` package (NOT a project dependency)" and "Deliberately not part of `npm test` ... never run in CI: it needs a model answering on the other end". package.json has no playwright dep or e2e script.

### F24 FE-17 — Root `npm run typecheck` silently skips the dashboard (no `typecheck` script); CI compensates with a direct `npx tsc --noEmit`
status=not_started cat=cleanup prio=P3 conf=high act=True
REMAINING: Add "typecheck": "tsc --noEmit" to the dashboard package.json so the root script and CI agree.
EVID: Root package.json typecheck = "npm run --workspaces --if-present typecheck"; dashboard frontend package.json scripts = dev/build/preview/tauri*/test/test:watch (no typecheck), whereas packages/design-system and packages/model-picker both define "typecheck": "tsc --noEmit". ci.yml dashboard-frontend job line 196 runs `npx tsc --noEmit` explicitly.

### F24 FE-18 — marketing/web-v7 has no test/typecheck scripts and no CI job; consumes @halbert/design-system HalbertMark
status=not_started cat=test_gap prio=P3 conf=high act=True
REMAINING: At minimum a `vite build` smoke in CI so design-system API changes cannot break the marketing site unnoticed.
EVID: marketing/web-v7/package.json scripts = dev/build/preview only; not in root workspaces (root package.json workspaces = packages/*, dashboard frontend); no ci.yml job. App.jsx:9 imports HalbertMark from '@halbert/design-system', App.jsx:97 uses density="medium" (still valid after the uncommitted change).

### F24 FE-19 — Minor: stale baseline-browser-mapping data warning in dashboard vitest output
status=not_started cat=cleanup prio=P3 conf=high act=False
REMAINING: Bump the devDependency when next touching the dashboard lockfile. Cosmetic only.
EVID: dash-vitest.txt line 4: "[baseline-browser-mapping] The data in this module is over two months old. ... npm i baseline-browser-mapping@latest -D"

### F24 FE-20 — No Rust CI job: cargo tests in src-tauri never run in CI
status=not_started cat=test_gap prio=P3 conf=high act=True
REMAINING: Add a `cargo test` job (macOS runner needed for the objc2/AppKit deps that compiled here) once the Tauri app is considered a shipped surface.
EVID: .github/workflows/ci.yml jobs: suite-census, design-tokens, design-system, model-picker, dashboard-frontend, test (Python). No job invokes cargo; 28 `#[test]`/`#[cfg(test)]` markers exist in src-tauri/src (lib.rs, hud_hotkey.rs, audio_capture.rs, floating_panel.rs).

### F25 CC-02 — SendToChat 'new conversation' affordance is dead (Plan A follow-up 3.2)
status=not_started cat=bug prio=P2 conf=high act=True
REMAINING: Decide: map newConversation to a new_thread request in hostConversation/askHost, or delete the flag, the Shift+click branch, the right-click handler, the MessageSquarePlus icon and the tooltip text from SendToChat and all producers.
EVID: src/components/SendToChat.tsx:42 newConversation prop, :95 `alwaysNewChat || e.shiftKey`, :117 right-click hard-codes true, :122-125 MessageSquarePlus icon + tooltip 'Continue in chat (Shift+click for new)'; openChat (:60-76) dispatches 'halbert:open-chat'; the only listener Layout.tsx:242-253 onOpenChat reads prefillMessage/context/itemId/title/configPath and ignores newConversation; grep '\.newC

### F25 CC-05 — REGRESSION: stale _defanged_query leaks the previous turn's question into the next PLANNING prompt
status=not_started cat=bug prio=P0 conf=high act=True
REMAINING: Reset `_defanged_query = None` at turn start (in process()/_begin_turn) or compute the defanged query in PLANNING; re-run test_thread_e2e.py (the Plan A §14 gate) to green.
EVID: agents/state_machine.py:1519 `_build_messages` uses `getattr(self, '_defanged_query', None) or self.ctx.user_query` and is called from PLANNING at :1702; the attribute is set at :2724 inside _handle_responding and reset only at :2701 (start of RESPONDING) — i.e. AFTER the next turn's PLANNING has already read it. Reproduced: tests/test_thread_e2e.py::test_second_message_sees_the_first fails with p
DOC: Plan A results doc §1 claims 'the second message sees the first' gate is green; it is red on main.

### F25 CC-06 — REGRESSION: response_modality referenced before assignment on the no-prompt-builder path
status=not_started cat=bug prio=P1 conf=high act=True
REMAINING: Hoist `response_modality = 'text'` above the `if self.prompts:` block (one line), then re-run the four state-machine test files.
EVID: agents/state_machine.py:2740-2763: `response_modality = 'text'` is assigned only inside `if self.prompts:`; the `else:` branch at :2760 calls `_build_simple_response_prompt(response_modality=response_modality)` → 'Handler error in AgentState.RESPONDING: local variable response_modality referenced before assignment' (captured in test logs). Introduced by 2f595bc0 (modality-voice Phase 2.5). Isolate

### F25 CC-07 — REGRESSION (test debt): speaker_role kwarg breaks executor fakes (REV-04 F8)
status=not_started cat=test_gap prio=P2 conf=high act=True
REMAINING: Accept **kwargs in the two fake_execute doubles; this restores the only end-to-end guard of the executor→bus→state-machine→SSE terminal bridge.
EVID: agents/state_machine.py:2359 now passes speaker_role= to execute (commit 58adce12 TASK-07); tests/test_terminal_e2e.py::test_e2e_agent_block_persisted_and_replayed fails 'fake_execute() got an unexpected keyword argument speaker_role' (reproduced, also pytest-main.txt:145); tests/test_state_machine_turn_lock.py::TestTerminalSessionIds::test_spawn_payloads_are_collected_once_on_ctx same TypeError

### F25 CC-08 — test_llm_config_parse_cache: a turn's model resolution parses models.yml twice
status=unknown cat=test_gap prio=P3 conf=low act=True
REMAINING: Bisect which reader added the second parse per turn; restore the once-per-turn cache or update the test if a second parse is intended.
EVID: tests/test_llm_config_parse_cache.py::TestOneTurnParsesOnce (2 tests) fail 'assert 2 == 1' at :93 both in isolation and in the full suite (pytest-main.txt); likely from the secure_model 4th slot / appleFoundation commits (cca3591a, a74ca171, 14cd028b) adding a second load — not bisected

### F25 CC-09 — Order-dependent failures in test_llm_config_layers (2) and test_llm_routes (1)
status=unknown cat=test_gap prio=P3 conf=medium act=True
REMAINING: Find the earlier test leaking llm_config/session-layer global state (module-level caches in model/llm_config.py); isolate with a fixture.
EVID: Both files pass in isolation (50 passed; 12 passed) but fail in the full-suite run (pytest-main.txt lists test_the_editor_round_trip_cannot_write_a_higher_layer, test_the_editor_is_served_the_global_layer_with_the_effective_view_beside_it, test_fresh_install_with_nothing_that_fits_still_serves_the_picker)

### F25 CC-10 — compact_boundaries table has no writers (opt-in LLM summaries)
status=not_started cat=deferred prio=P3 conf=high act=False
REMAINING: Deliberately deferred; nothing to do now.
EVID: agents/conversation_sqlite.py:372-385 only CREATE TABLE/INDEX; grep 'INSERT INTO compact_boundaries' → none; design doc §14 defers opt-in LLM summaries to spec 2

### F25 CC-11 — Plan C (background commands, task notifications, timeline SSE/search, thread export) not started
status=not_started cat=incomplete_feature prio=P2 conf=high act=True
REMAINING: Write and execute Plan C per design §9.4/§10/§12: run_command(background=true) + tasks table + task_output/task_stop SAFE tools + origin=task-notification rows + StatusLight lighting + persistent timeline SSE + /timeline/search + export. Depends on TERM-03/TERM-04 wiring for the terminal half.
EVID: grep over halbert_core for background=, task_output, task_stop, task-notification, timeline/search, export_thread → no production hits; only useAgentStream.ts:138 carries a `task_completed` placeholder comment; CONTINUOUS-CONVERSATION-HANDOFF-2026-08-26.md §3 'Plan C — Not yet written'

### F25 CC-13 — Design §8 deletion of routes/conversations.py and agents/conversation.py is obsolete
status=obsolete cat=cleanup prio=P3 conf=high act=False
REMAINING: None — do not delete; the cleanup handoff's gate ('if a plan intends to reach it, it is early, not dead') applies.
EVID: routes/conversations.py is now the P3b peer conversation API (commit 3bbcc4d4; module docstring 'Conversation API — the P3b server half'); agents/conversation.py has live importers (peer_conversation_store.py:55, migrations.py:66, conversation_sqlite.py:28, agents/__init__.py:22); tests/test_legacy_conversations_removed.py pins the old /api/conversations shape as 404

### F25 TERM-01 — Plan B (terminal sessions, blocks, watched shell, pool, TasksColumn, StatusLight) executed and merged
status=done cat=doc_only prio=P3 conf=high act=True
REMAINING: Update the doc headers (see doc_discrepancy). The functional gaps are TERM-02..TERM-10.
EVID: merge 0ba316b2 'Merge branch feat/plan-b-terminals into main'; branch commits 0a6cbcbf (B1) … 1e29cf43 (B22) incl. dbdc665f B3 OSC parser, a54052cc B4 fan-out, 4a040e2a B5 kinds, 0327dbaf B6 pool, 9a6ac801 B7/B12, 4f6ba16a B8, fafc530d B9 stage, 1d33cad1 B13 StatusLight, 0c845668 B15 TasksColumn, 5ffcec8c B16 YourShellRegion, ee5e3c4c Playwright smoke; new modules streaming/{agent_pool,watched_she
DOC: .handoff/CONTINUOUS-CONVERSATION-PLAN-B-2026-08-27.md header still reads 'Status: DRAFT — contracts and task outline only; full inline code not yet generated'; CONTINUOUS-CONVERSATION-HANDOFF-2026-08-26.md §2 still says Plan B 'Not yet written'; REVIEW-PACKET-04 §4 file map names agents/terminal_poo

### F25 TERM-02 — Reaper kills the admin's interactive terminal after 60 s of quiet (REV-04 F1) — the one user-facing terminal bug
status=not_started cat=bug prio=P0 conf=high act=True
REMAINING: spawn user-facing sessions with kind='user' (add kind to SpawnRequest, default 'user' for the launcher), call manager.attach_client/detach_client at WS accept/disconnect; add a regression test for 'attached user shell survives past the oneshot TTL'.
EVID: routes/terminal.py spawn_session (:305) calls manager.spawn() with no kind= (grep -n kind terminal.py → no hits; SpawnRequest has no kind field); streaming/session_manager.py:49-64 has kind_caps/kind_ttls (user TTL 1800 s, oneshot 60 s) and the attach-count exemption, but routes/websocket.py never calls attach_client/detach_client (grep → none; its only change since REV-04 HEAD 51082f83 adds the t
DOC: Not tracked in MASTER-TODO.md (only the REV-04 packet row at :55; no F1–F13 entries).

### F25 TERM-03 — Watched-shell → thread pipeline is dead code; stage-into-shell always 409; watched toggle is a no-op (REV-04 F2)
status=in_progress cat=incomplete_feature prio=P1 conf=high act=True
REMAINING: Add the reader loop: one OSCParser + WatchedShellProcessor per kind='user' session fed from PTYSession.attach() fan-out; call update_parser_state from it; call insert_terminal_session in spawn; then wire YourShellRegion's watched toggle and the composer's 'stage into my shell' action. Until then relabel B8/B9/B22 as unshipped.
EVID: No production caller of WatchedShellProcessor.process_block_close, TerminalSessionManager.update_parser_state or store.insert_terminal_session (grep excluding tests; peer_conversation_store.py:453 only proxies the name); agents/threads.py:340-346 constructs WatchedShellProcessor and calls build_hint_text over the never-populated terminal_blocks table (hint always None); routes/terminal.py:391-408 
DOC: Plan B doc and REV-04 packet present the watched-shell loop as delivered; the founder's 2026-08-26 'terminals are watched by the AI' direction is not implemented end to end.

### F25 TERM-04 — Agent PTY terminal pool is unreachable in the running app
status=in_progress cat=incomplete_feature prio=P1 conf=high act=True
REMAINING: Decide the enable path (config key/capability) and enable it only after TERM-05 is fixed; add an integration test that runs a command through the pool from routes/agent.py.
EVID: streaming/terminal_bridge.py:142 set_terminal_pool_enabled() has no production caller; tools/executor.py:528 reads terminal_pool_wanted() which defaults False; agent commands therefore still run through the asyncio subprocess mirror path (no stdin, no reuse of idle shells — contrary to the founder's 'agent reuses a terminal window' direction)

### F25 TERM-05 — Pool run_block leaks a permanently-busy slot on error and accumulates block_output unbounded (REV-04 F3/F4)
status=not_started cat=bug prio=P1 conf=high act=True
REMAINING: Move attach/replay/write inside the try, clear the busy flag in finally (evict on the kill path), cap block_output while accumulating (first/last N bytes with an elision marker).
EVID: streaming/agent_pool.py:131 attach(), :133 replay get, :142 write_stdin(block_cmd) all run before the try at :161 whose finally (:180) only detaches; set_block_open(sid, False) at :206 is outside any exception guard; block_output = bytearray() at :137 grows at :154 with no cap (head/tail applied only at :195-199). File unchanged since REV-04 (51082f83).

### F25 TERM-06 — /api/terminal/exec accepts an unbounded client timeout and accumulates unbounded output (REV-04 F7)
status=not_started cat=security prio=P2 conf=high act=True
REMAINING: Clamp timeout (e.g. 1..300) and cap the output buffer head/tail.
EVID: routes/terminal.py:62 `timeout: int = 30` with no ceiling, :276 wait_for(drain(), timeout=request.timeout); output bytearray (:269 per REV-04) uncapped; file unchanged since 51082f83

### F25 TERM-07 — PTY primitives: kill() blocks the loop, fan-out queues unbounded, zombie/fd-leak edge cases (REV-04 F5/F6/F12/F13)
status=not_started cat=bug prio=P3 conf=medium act=True
REMAINING: Async kill/reap, bounded attach queues with drop-oldest, close fds on fork failure, do not latch _exited until reaped.
EVID: REVIEW-RESULTS-REV-04-2026-08-31.md F5 (pty.py:340,347 time.sleep in kill), F6 (:119-132 attach maxsize=0), F12 (:349-355 _exited latched), F13 (:224-239 openpty then fork failure); streaming/pty.py unchanged since the reviewed tree (git diff --stat 51082f83 main)

### F25 TERM-08 — Plan B frontend surface not mounted: TasksColumn/YourShellRegion orphaned, TerminalAccordionDock still the dock
status=in_progress cat=incomplete_feature prio=P1 conf=high act=True
REMAINING: Mount TasksColumn (Running / Finished N › / Clear) and the pinned YourShellRegion in ContextStage, retire TerminalAccordionDock, wire the aggregate StatusLight onto ModeSwitch and the Sheet below md; needs TERM-03 for the watched toggle and stage target to do anything.
EVID: components/shell/ContextStage.tsx:18 imports and :73 renders <TerminalAccordionDock>; TasksColumn.tsx and YourShellRegion.tsx have no importers outside their own tests (grep over src); components/agent/index.ts:23 still exports TerminalAccordionDock; Plan B B16 spec 'Replace all references to TerminalAccordionDock with TasksColumn' and 'Delete TerminalAccordionDock.tsx' not done; ContextStage.tsx:

### F25 TERM-09 — PTY key ownership half-done: tile consumes keys, but Cmd/Ctrl+B still toggles mode inside a tile (Plan B B18)
status=in_progress cat=bug prio=P3 conf=medium act=True
REMAINING: Add the e.target.closest('.xterm') bail in ShellModeContext's Cmd/Ctrl+B handler and a test.
EVID: components/agent/TerminalTile.tsx:170 attachCustomKeyEventHandler present; contexts/ShellModeContext.tsx has no `.xterm` / closest('.xterm') guard (grep → none)

### F25 TERM-10 — /api/terminal/history reads a file nothing writes (Plan B B11 said delete/repoint)
status=not_started cat=cleanup prio=P3 conf=high act=True
REMAINING: Delete the endpoint or repoint it at store.list_terminal_blocks per design §9.6.
EVID: routes/terminal.py:485-505 get_history reads ~/.config/halbert/terminal_history.json; grep 'terminal_history' over halbert_core → only that line (no writer)

### F25 TERM-11 — Somatic block pipeline and sub-agent seams remain unwired (REV-04 F9; SOVEREIGN findings #8)
status=blocked cat=decision prio=P3 conf=high act=True
REMAINING: Founder decision: wire (after fixing the listed defects) or relabel C1a–C1d and the subagent track as 'built, unwired' in the plan docs. Given the current-features priority, relabel is the cheaper honest option.
EVID: routes/agent.py: grep somatic_lifecycle|somatic_store|subagent_manager → none (agent constructed without them); REV-04 results §2 'NOT WIRED' for both; SOVEREIGN-HOST-REVIEW-FINDINGS #8 lists the fix-before-enabling defects (SubagentManager no reaper, await_subagent_completion ValueError on cancel)

### F25 TERM-12 — ThreadManager.tick() docstring promises a live-terminal guard that does not exist (REV-04 F10)
status=not_started cat=cleanup prio=P3 conf=high act=True
REMAINING: Implement when TERM-03 lands (sessions get a thread id) or delete the sentence.
EVID: agents/threads.py:556-557 'Plan B adds the live-terminal guard: never close while a terminal session of this thread is open' vs _close_due at :795 which checks only grace window and successor turns; sessions carry no thread id

### F25 TERM-14 — SOVEREIGN-HOST-REVIEW-FINDINGS deferred list — current status
status=in_progress cat=doc_only prio=P3 conf=medium act=True
REMAINING: Mark the resolved rows in the findings doc; the rest fold into PICK-04 / TERM-11.
EVID: #1 conversation_sqlite save transactional → resolved (REV-04 §2 'every write transactional', WAL, _locked); #9 terminal UI unreachable → resolved (TERM-13); #4 FTS MATCH abort → resolved per design §8/Plan A; #2/#3 cascade_router defects → still present and still off (PICK-04); #6/#7 context/watermark → still no production importer (unverified); #8 subagents → TERM-11; #10 tier_router retry loop →

### F25 TERM-15 — REV-04 and REV-10 review results are not folded into MASTER-TODO
status=not_started cat=doc_only prio=P2 conf=high act=True
REMAINING: Add TERM-02..TERM-07, PERS-02/03 and CC-05/06/07 as tracked items under §3 (Frontend/Chat UI and Core Agent subsystems).
EVID: .handoff/REVIEW-RESULTS-REV-04-2026-08-31.md (47f824ef) and REVIEW-RESULTS-REV-10-2026-08-31.md exist; MASTER-TODO.md mentions only the packet rows (:55, :61); grep for reaper|attach_client|REVIEW-RESULTS|response_modality|_defanged_query in MASTER-TODO → none

### F25 PICK-02 — compression.py still writes models.yml around the llm_config store (cleanup handoff §1, 'the one live bug')
status=in_progress cat=bug prio=P1 conf=high act=True
REMAINING: Read via llm_store.load_file(), write via llm_store.set_top_level('compression', …); one-shot strip of a stray routing: block in normalise_file (or ship with a note). Do together with PICK-03.
EVID: routes/compression.py:96-118 update_config: reads via find_models_config() (may resolve to the repo's config/models.yml), mutates the whole dict, writes with bare yaml.safe_dump to write_models_config() — no atomic rename, no .bak, no 0600, no normalisation; copies the repo's routing: block into the user file. Store API exists: model/llm_config.py:653 load_file, :746 set_top_level; settings.py:275

### F25 PICK-03 — routing.complexity_threshold read on two incompatible scales (cleanup handoff §2)
status=not_started cat=bug prio=P2 conf=high act=True
REMAINING: Collapse to one scale, rename the key so the scale is in the name, migrate the shipped 0.5, delete the two duplicate scorers.
EVID: intake/pipeline.py:167 default 3 (1–5 scale, authoritative for chat turns); model/tier_router.py:85,115,235 default 0.5 and router.py:494 default 0.5 (0.0–1.0); two _score_complexity implementations (router.py:365, tier_router.py:592) alongside client.score_query_complexity

### F25 PICK-04 — model/cascade_router.py still present and imported (cleanup handoff §3: delete, do not fix)
status=not_started cat=retire prio=P2 conf=high act=True
REMAINING: Delete cascade_router.py, its tests and the two is_enabled() branches; keep OutcomeStore if telemetry is wanted.
EVID: halbert_core/halbert_core/model/cascade_router.py exists; tier_router.py:31 imports MetaHarnessRouter, :287 constructs it, :552 and :566 is_enabled() branches; tests/test_cascade_router.py exists; SOVEREIGN findings #2/#3 (every model classifies 'other'; unbounded recursion when enabled) unfixed

### F25 PICK-05 — Picker edges from cleanup handoff §5 (vision-loss warning, inline key verify, dead session layer, /model status, Cmd+/, design-review Resolution)
status=not_started cat=incomplete_feature prio=P3 conf=medium act=True
REMAINING: Per handoff: D-4.3 vision-slot warning; verify API key on paste; wire or remove the session config layer (revision 2 D-6); /model status session state; Cmd+/; append the Resolution section.
EVID: grep for vision-provided-by-chat / chatHasVision → none; grep verifyKey|inline verif in components/llm and packages/model-picker → none; bind_session/set_session_slot have no production caller (only a docstring mention at model/llm_config.py:657); Cmd+/ handler grep in src → none; .handoff/LLM-PICKER-DESIGN-REVIEW-2026-08-26.md has no 'Resolution' section (grep)

### F25 PICK-06 — Model-picker design §11 follow-ups: Anthropic adapter landed; Google/Azure, vision-by-chat, SourcePrep import, streaming remain
status=in_progress cat=incomplete_feature prio=P3 conf=medium act=True
REMAINING: Founder call on Google/Azure adapters and the SourcePrep one-shot import (likely drop); implement the vision-by-chat badge when model/capabilities reports it; confirm one live Anthropic completion.
EVID: Done: model/client.py:1276 `_call_anthropic` dispatch and 'anthropic' in CHAT_CAPABLE_PROVIDERS (:76). Not done: google/azure-openai absent from CHAT_CAPABLE_PROVIDERS; no vision-provided-by-chat badge (grep); hooks/useSourcePrepDaemon.ts deleted and no import button (import-from-SourcePrep is arguably obsolete under the 2026-08-26 'no SourcePrep coupling' decision); handoff §5 V-02 'live Anthropi

### F25 PICK-07 — documentation/design/unified-model-picker.md lacks the 'Superseded 2026-08-26' header
status=not_started cat=doc_only prio=P3 conf=high act=True
REMAINING: Add the header linking to model-picker-independent-2026-08-26.md.
EVID: grep -i supersed documentation/design/unified-model-picker.md → none; model-picker-independent-2026-08-26.md §10 asks for it

### F25 PERS-01 — Multi-persona Phase 1 (store + API) and Phase 2 (persona cards, +, activate, delete, hot reload) merged
status=done cat=incomplete_feature prio=P3 conf=high act=True
REMAINING: Doc header refresh (see discrepancy). No PUT /{id}: edits go through POST /settings/being via the symlink — acceptable but undocumented.
EVID: merge 9f4d4b16 (persona/store.py 248 lines, routes/persona.py, config/being_config.py, Settings.tsx, tests/test_persona_store.py 192 lines) + cc47d5ab scrutiny fixes; routes/persona.py:189 POST /api/persona, :201 GET /{id}, :214 DELETE /{id}, :230 POST /{id}/activate with agent.prompt_builder.reload_personality() at :242; frontend components/settings/tabs/BeingTab.tsx:59 list, :73 create, :92 acti
DOC: MULTI-PERSONA-DESIGN-2026-08-29.md says 'Status: Awaiting design input before implementation' and 'Branch: feat/multi-persona' — it is merged; its API table names /api/personas while the router prefix is /api/persona (persona.py:52); the 'PUT /api/personas/{id}' row was never implemented.

### F25 PERS-02 — PersonaManager was never unified with PersonaStore — two sources of truth for the active persona (design Q4; REV-10 F7)
status=not_started cat=bug prio=P1 conf=high act=True
REMAINING: Pick PersonaStore (design recommendation A): route /switch and /status through it, replace the enum with directory personas, or delete the old surface; then per-persona memory dirs become a field on the persona YAML.
EVID: persona/manager.py:25-29 hardcoded Persona enum (IT_ADMIN/FRIEND/CUSTOM 'Phase 5'), :156-158 CUSTOM raises 'coming in Phase 5', :165-168 memory_dir 'core'/'personas/friend'; routes/persona.py:102 POST /switch drives PersonaManager (persona_state.json) while :230 /activate drives PersonaStore (being.yml symlink); :55-74 GET /status reports the manager view, :84 /list the store view; grep PersonaSto

### F25 PERS-03 — Fixed-name temp symlink makes persona activation racy across processes (REV-10 F8)
status=not_started cat=bug prio=P3 conf=high act=True
REMAINING: Use a per-call unique staging name (pid+uuid); one line.
EVID: persona/store.py:157 `tmp_link = self.being_yml.with_name('.being.yml.tmp-link')`, unlinked and recreated on every activate before os.replace at :161

### F25 PERS-04 — Multi-persona Phase 3 polish (composer quick-switch, per-persona memory dirs, audit, export/import)
status=not_started cat=deferred prio=P3 conf=medium act=True
REMAINING: After PERS-02: per-persona memory path on the persona record; export/import of persona YAML; audit line on activate.
EVID: Composer quick-switch: founder wrote 'settings only' in the design §2 Q5 → obsolete; per-persona memory: manager.py:213 get_memory_dir has no consumers, no memory_{persona_id}.db anywhere (REV-10 §3 open item 3); export/import: grep export_persona|import_persona → none; audit logging exists only in the old PersonaManager path

### F25 PERS-05 — PersonaManager._save_state writes persona_state.json non-atomically
status=not_started cat=cleanup prio=P3 conf=high act=True
REMAINING: Moot if PERS-02 deletes PersonaManager; otherwise mirror the store's atomic write.
EVID: persona/manager.py:115-131 plain open(self.state_file,'w').write (no temp+rename), inconsistent with store.py's _write_persona_file temp+rename+0600

### F25 PERS-06 — Design §7 open questions (card layout, creation flow, switch confirmation, icons, name vs display name)
status=unknown cat=decision prio=P3 conf=low act=True
REMAINING: Record the de-facto answers in the design doc; founder confirms name-vs-display-name and switch-confirmation choices.
EVID: MULTI-PERSONA-DESIGN §7 lists 7 questions; the shipped BeingTab.tsx answers layout/creation/delete implicitly (cards + prompt), PersonaSummary carries a display name (store.py:47), but no written resolution exists in the doc

### F25 DOC-01 — Stale status headers across the four workstream docs
status=not_started cat=doc_only prio=P3 conf=high act=True
REMAINING: One doc pass: mark merged/executed, point Plan B readers at REV-04 results for what is wired vs not.
EVID: CONTINUOUS-CONVERSATION-PLAN-A-RESULTS: 'not merged to main' (merged c1840008/ddf22122) and §3.1 'no producer' (fixed 5d0e3405); PLAN-B doc: 'Status: DRAFT' (merged 0ba316b2); CONTINUOUS-CONVERSATION-HANDOFF §2/§3: Plan B 'Not yet written'; MULTI-PERSONA-DESIGN: 'Awaiting design input', branch feat/multi-persona (merged 9f4d4b16); HANDOFF-CLEANUP-AND-ROUTING §1 'verified still open' is still true 