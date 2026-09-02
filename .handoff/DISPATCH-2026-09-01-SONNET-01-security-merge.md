# DISPATCH SONNET-01 — Merge `feat/security-review-01`, close REV-01/02 residuals, run the unredacted rebuild gate

**Owner:** a Sonnet session. **Effort:** medium. **Order:** after SONNET-02 has committed the dirty main tree (so `main` is clean) — or run in a worktree and fast-forward main at the end.
**Parent:** `.handoff/HANDOFF-STATE-OF-WORK-2026-09-01.md` §3.1, §6.7. Evidence ids: `SEC-01..11` (areas F17/F23), `R1-F4`, `R2-P3`, `R2-P1/P2/P4/P5`, `R2-OBS-1` (area F1) in `.handoff/audit-2026-09-01/AUDIT-FINDINGS-DETAIL.md`.

## Shared rules
- Work in a fresh worktree: `git -C /Volumes/4TB-BAD/Halbert worktree add ~/.config/superpowers/worktrees/Halbert/sec01 -b chore/security-review-01-merge main`. Run `git branch --show-current` before every commit (concurrent sessions have switched shared worktrees before).
- Python tests from a worktree ONLY via the wrapper: `arch -arm64 /Volumes/4TB-BAD/Halbert/.venv/bin/python wt_pytest.py <test paths>` (copy `wt_pytest.py` from the repo root once SONNET-02 has committed it, else from `/Volumes/4TB-BAD/Halbert/.claude/worktrees/central-todo-batches/wt_pytest.py`). Plain pytest in a worktree silently tests main's code.
- Baseline: main has 71 pre-existing failures (`.handoff/audit-2026-09-01/pytest-main-failed-4a7bf71f.txt`). Criterion: no new failures; your packet's tests green.
- TDD: failing test first. No `Co-Authored-By`/generation trailers. Never edit `.handoff/MASTER-TODO.md` (SONNET-05 owns it); write results to `.handoff/RESULTS-SONNET-01-<date>.md`.
- Do not call SourcePrep `prep*` MCP tools; do not run `scripts/staged_knowledge_embed.py`.
- Refer to sibling apps only as H2/H3.

## Task 1 — Merge the branch (P1, HIGH security fix)
Facts: 3 commits ahead (`9e057db7` redactor caps, `c5b6bb91` MCP path allowlist, `a09632e1` progress doc). On main, `config/queries.py:102-122` (`_get_current_canon`) hashes and `parse_config()`s any readable path and `_write_canon` (`:128-165`) persists it to the canon DB and `latest.json`; `mcp/server.py:188-256` forwards any client path. The branch's `TestPathAllowlist::test_arbitrary_path_rejected` and `::test_dotdot_traversal_blocked` fail against main.

Steps:
1. `git merge --no-ff feat/security-review-01`. Expect exactly one conflict: `halbert_core/tests/test_mcp_server.py` (main's `0f750c3a` and the branch both appended test classes). `server.py` and `redaction.py` auto-merge.
2. Resolve by copying the pre-resolved file: `cp /Volumes/4TB-BAD/Halbert/.handoff/audit-2026-09-01/security-review-01-merge-resolved-test_mcp_server.py.txt halbert_core/tests/test_mcp_server.py`. It keeps main's `TestAutonomyEscalationPhrase` + `TestHighRiskProposalPhrase`, main's `TestProtocol` (18 tools), the branch's two 3-line `_load_latest_snapshot` monkeypatch inserts (after each `monkeypatch.setattr(q_module, "_get_current_canon", mock_get_current_canon)`), and the branch's `TestPathAllowlist` appended. It was built against `4a7bf71f`; if main has moved in that file, redo the resolution by hand with the same rule.
3. Verify: `test_mcp_server.py test_redaction_gaps.py` (expect 90 passed), then `test_tier2_guarantee.py test_mcp_response_boundary.py test_mcp_http.py test_security_roles.py test_config_queries.py test_cli_security.py test_secure_response.py test_redact.py` (all green; scratch run was 500/500).
4. Add the precondition note to the three tool descriptions (`mcp/server.py:766-800` on the merged tree): "path must be in the host's config snapshot manifest; on hosts without a ConfigWatcher run a snapshot first." (The fail-closed posture itself is founder decision `SEC-05`; do not change the gate's behaviour.)
5. Optional polish: `_is_allowed_config_path` re-reads `latest.json` and realpaths every entry per call; cache by file mtime if trivial.
6. Do NOT commit the two untracked docs in the branch's worktree (`SCOPE-01-DUPLICATE-WORK-RECONCILIATION.md`, `HANDOFF-HOME-AUTOMATION-SIMPLIFICATION-2026-08-30.md`) — obsolete. After merge, update the merged `.handoff/SCOPE-01-SECURITY-REVIEW-PROGRESS.md` §6 ("clean merge" → note the resolved test conflict) and list main-side work it predates (`5a132654`, `74401f12`, `51082f83`, `360effab`, `7e9ebaae`, `0f750c3a`, `cb69442f`).
7. Fast-forward main (`git -C /Volumes/4TB-BAD/Halbert merge --ff-only chore/security-review-01-merge`), then `git branch -d feat/security-review-01` and `git worktree remove ~/.config/superpowers/worktrees/Halbert/security-review-01 --force` (it has an untracked `node_modules` symlink).

## Task 2 — `R1-F4` MCP `set_autonomy_level` still races (P1)
`360effab` added `update_being_config(mutator)` (`being_config.py:728-755`, docstring names MCP `set_autonomy_level` as an intended caller); dashboard (`settings.py:3079-3150`) and devices routes use it, but `mcp/server.py:644-669` `_tool_set_autonomy_level` still does `load_being_config()` … `save_being_config(cfg)` under two separate locks. Rewrite it to call `update_being_config` so the escalation/phrase check and the write happen under one exclusive lock. Test: a relock persisted between load and save is not clobbered by the MCP path.

## Task 3 — `R2-P3` id-less `tools/call` executes (P2)
`mcp/server.py:1043-1061` runs the handler and only afterwards returns `None` for notifications. Reject `tools/call` without an `id` (`-32600`, or ignore) before invoking the handler. `test_mcp_server.py:261 test_notification_tools_call_no_response` currently pins "no response", not "no execution" — extend it to assert the handler was not called.

## Task 4 — Retarget and run the unredacted rebuild gate (`SEC-03`, `SEC-04`, `SEC-11`) (P2)
- `scripts/rebuild_sourceprep_unredacted.py` (246 lines, `5a132654`) calls `register_host_project(redact=False)` — the LEGACY `halbert-host` project that `sourceprep_setup.py` lists in `LEGACY_PROJECT_NAMES` and retires. Rewrite step 2 to `SourcePrepSetup().apply(redact_host=False)` on the unified `halbert` project (id `735a592e-a2da-499b-a614-854a5fc461f5`, daemon `127.0.0.1:8400`); keep the snapshot and egress self-check steps. Document the caveat: boundary 2 of the egress check goes through `_tool_get_config_value → load_being_config()`; if the host is UNLOCKED (cloud_ok + acknowledged) the value legitimately crosses with `_egress_ack` and the script would report a false exit 2 — run only while locked or make the check lock-aware.
- Before running: the real canon DB `~/.local/share/halbert/config/{canon,snapshots}` holds only pytest tmp paths (`latest.json` mtime Aug 31 08:07). Add a `tests/conftest.py` autouse fixture that points `CANON_DIR`/`SNAP_DIR`/`RAW_DIR` at `tmp_path` so tests stop writing to the real store; clear the two junk records.
- Then: `arch -arm64 .venv/bin/python scripts/rebuild_sourceprep_unredacted.py --dry-run`, then the real run **only while the host is locked and no other SourcePrep build is running** (`ps aux | grep -E 'staged_knowledge_embed|prep.cli'` first — a previous collision froze the machine). Record exit code + report in your results doc. The staging tree `~/.local/share/halbert/sourceprep/host` was last written 2026-08-24, before the redact/`write_text` staging code existed.

## Task 5 — Low residuals (P3, do if time remains)
`R2-P1` `verify_token` iterates the peer dict without the lock while `add_peer` mutates; `R2-P2` synchronous atomic file write per authenticated request inside the event loop; `R2-P4` stdio transport has no line-size limit; `R2-P5` `Authorization` scheme match is case-sensitive; `R2-OBS-1` `mcp/camera_gate.py` is dead code while `mcp/__init__.py` advertises it; `R2-F2b` no socket timeout on the HTTP handler; `NEW-01` `_egress_ack` marker honoured on any dict at any depth of an MCP payload, not only `get_config_value`'s top-level result; `SEC-14` the SourcePrep daemon answers `/projects` without a bearer (report to the founder, do not fix here — that is CoDRAG).

## Coordination
- OPUS-03 owns `federation/**` and `routes/peers.py`; leave `R2-F6` (FleetProxy raw token) to them.
- Nothing here touches `agents/state_machine.py` (OPUS-01) or `capabilities.py` (SONNET-03).

## Results
Write `.handoff/RESULTS-SONNET-01-<date>.md`: merge sha, test counts before/after, rebuild exit code and report, residuals left open.
