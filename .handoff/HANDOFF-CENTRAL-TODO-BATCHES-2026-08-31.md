# Handoff: Central Task List Execution — U1–U5 (2026-08-31)

**Branch:** `worktree-central-todo-batches` in
`/Volumes/4TB-BAD/Halbert/.claude/worktrees/central-todo-batches` — 36 commits on top of
main `7e8c03b3`. **Not merged.** A concurrent session has since landed
`9a292ce6` (REV-03 remediation) on main — merge order matters (§5).

**What this session did:** worked the entire central task list
(`.handoff/MASTER-TODO.md`) through batches U1–U5 in dependency order, running
implementation and review agents per batch, plus a security-fix pass on the confirmed
review findings. Stopped at the founder gate (U5) as the fable-level blocker.

---

## 1. Completed work (all committed on the branch)

### U4 — Model routing & agent tooling
- `HALBERT_MODEL` env override fills an unconfigured chat slot (`7c70276d`, sysadmin-only, models.yml wins, test-pinned).
- GPU deep-scan refactored through the agent specialist path: 4 registered GPU tools, raw Ollama call gone, CUDA knowledge extracted to `data/knowledge/linux/nvidia_cuda_compatibility.md`, GPU.tsx on the shared AIAnalysisPanel (`162f3965`, `fbfb5614`).
- Role-scope taxonomy completed: waves 2–3 (security/shell/package/boot/sharing admin) in the existing `config/roles.py` idiom, 18 new tests (`e567a529`). NOTE: the TASK-05 packet's `ServerRole`/`RoleConfigHarvester` spec is stale — the design doc + existing registry govern.
- Apple Intelligence platform verification: PASS (28/28; eligible on this M1 Ultra/macOS 26.5; Swift bridge build remains its known open deliverable).

### U1 — Security & trust boundary
- Real egress leak found+fixed: MCP dispatcher's catch-all leaked handler exception text unredacted (`5a132654`).
- New guarantee tests: `test_tier2_guarantee.py` (dispatch choke point), `test_security_roles.py` (credentials_admin boundary), `test_cli_security.py` (14). `test_redactor.py` from the packet deliberately NOT created — duplicate coverage (documented in the commit).
- `scripts/rebuild_sourceprep_unredacted.py` — the operational raw-rebuild gate (TASK-03 Task 3.2), with live egress self-check, exit 2 = boundary failed.
- REV-01 F1: canon DB reconciled on raw-by-design (`74401f12`) — snapshot() defaults redact=False, RAW_DIR text sink always redacted, Tier-2 describe now receives real values.
- REV-01 F2+F3 (`51082f83`): unlock phrase no longer echoed in 403s, gates ALL exposure-increasing security changes; `_egress_ack` marker makes the escape hatch behave identically for all key classes at the MCP boundary.
- REV-01 F4+F5 (`360effab`, `7e9ebaae`): cross-process flock for being.yml (+ `update_being_config` composite); correlation index HMAC-peppered.
- REV-02 F1–F5 (`0f750c3a`, `cb69442f`, `d5ce2858`): autonomy escalation + critical-proposal approval require the shared phrase; Content-Length bounds, rate-limit-before-auth, SSE slot leak, non-ASCII bearer all fixed.

### U3 — Frontend
- Settings.tsx decomposed 3,291 → 870 lines into 9 tab components under `src/components/settings/tabs/` (5 commits).
- Sidebar consolidated to 4 domains; `Security.tsx` → `Findings.tsx` with `/security` redirect (`e7e7ad2f`, `91e7b6eb`).
- rAF token buffer (`useTokenBuffer`, O(n²)→O(1)) + 11 ARIA gaps in AgentChat/useAgentStream (`7fad824b`, `c5cd65ce`).

### U2 — Voice / modality
- TASK-07's speaker_role + conversation threading were docstring-only claims; now real: `process(speaker_role=…)` → StateContext → RoleGate; Wyoming passes "unknown" + threads conversation_id (`58adce12`).
- Runtime breaks fixed: `asyncio.timeout` (3.11+) crashed every Wyoming turn on 3.10; `ha_config`/`ha_client` imports pointed at nonexistent modules so proactive_speak always failed; ThreadManager injected into Wyoming turns (`149b3e75`).
- Verified DONE by the modality merge (stale MASTER-TODO items): dual-stream demux (`modality_resolved`/`speech_segment` events), `<modality_context>` XML, prompt builder, all four voice UI components.
- Rust AEC + NSPanel/CGEventTap HUD: see §3 (in flight at handoff time).

### U5 — Founder gate (STOPPED HERE)
- All four drafts committed to `.handoff/FOUNDER-DECISION-DRAFTS-2026-08-31.md` (`fd1854af`): DCO ratification (text already lives in CONTRIBUTING.md), LICENSE-EXCEPTION-APPSTORE (with the in-tree two-text conflict flagged), bundle-identifier reconciliation (3 schemes in flight), HALBERT-PRO-COMMERCIAL-TERMS.md draft. **No decision is made; the founder's.**

### Review passes (11 of 11 executed; reports in .handoff/)
REV-01 (`98d57f39`), REV-02 (`31fa91ef`), REV-03 (`ae376866`), REV-04 (`47f824ef`),
REV-05 (`1541380c`), REV-06 (`2199d634`), REV-08 (`7bbc8f9b`), REV-09 (`ef09f56a`),
REV-10 (`08c9f615`), REV-11 (`375e8171`). REV-07 is founder-gated (U5).

---

## 2. Consolidated verification (2026-08-31)

- Backend (worktree wrapper): **71 failed / 4,079 passed**. Main at same moment: **74 failed**. The branch FIXES 8 of main's failures and introduces **zero regressions** — all 5 branch-only failures are merge-drift from main's post-fork `7d01720e` (files this branch never touched; all 5 pass on current main).
- Frontend: `npm run build` clean, vitest **451/451**, `tsc --noEmit` clean.
- Worktree testing: ALWAYS `arch -arm64 /Volumes/4TB-BAD/Halbert/.venv/bin/python wt_pytest.py <args>` (wrapper at worktree root strips the editable-install finder that pins halbert_core to the MAIN tree; it asserts resolution before running). Plain pytest tests the wrong code.

---

## 3. Rust voice workstream (landed)

- **AEC capture pipeline** (`e10ea62f`): `audio_capture.rs` — cpal → 16 kHz mono → WebRTC AEC3 (`webrtc-audio-processing 2.1.1` bundled) → loopback TCP (127.0.0.1:18400) for the Python pipeline; TTS far-end reference via second listener + `feed_tts_reference`. Behind optional `voice-capture`/`aec` Cargo features (default build has no audio backends; commands degrade gracefully). Full `cargo build --features aec` verified arm64 (Rosetta toolchain fixed by the committed `build_aec_arm64.sh`); 24/24 unit tests.
- **NSPanel + CGEventTap HUD** (`057990e9`): `floating_panel.rs` + `hud_hotkey.rs` — non-activating always-on-top pill window (opt-in `voice-hud` label/capability), Esc/Space event tap with focus never stolen, macOS-only cfg gating, Linux stubs compile. `objc2-app-kit` used directly (`tauri-nspanel` does not exist on crates.io).
- **Follow-ups:** on-hardware runtime testing not attempted (compile-verified only); the Python consumer of the loopback socket (T2.2) and the frontend `voice-hud` route are unbuilt; `macos-private-api` enabled for the transparent pill (App Store caveat in code).

---

## 4. Next work — the review-finding remediation backlog (in priority order)

Reviews found real defects; only REV-01 and REV-02 findings were fixed (all 12). The
rest are specified with file:line + scenarios in their reports:

1. **REV-03 (13 findings)** — **ALREADY FIXED on main** by the concurrent session
   (`9a292ce6`); just needs the merge (§5). Do not redo.
2. **REV-04 (11 CONFIRMED)** — terminal reaper kills live user tiles (F1, user-facing
   today), pool slot leak, unbounded `block_output` (~800MB RSS reproduced), watched-shell
   pipeline is dead code, one e2e guard dark from test rot.
3. **REV-05 (9 CONFIRMED)** — top two: `peer://` chat turns break the production streaming
   path (belongs with the compute-peer owner session), Apple Intelligence auto-provision
   can assign a dead chat slot.
4. **REV-06 (F1–F4 regressions)** — state-machine prompt-assembly seams break 30 agent-core
   tests and corrupt multi-turn planning; retrieval-scope + rollback violations.
5. **REV-09 (12 CONFIRMED)** — Wyoming binds 0.0.0.0:10400 unauthenticated (F1, severe);
   second event loop clobbers shared state machine; VAD frame-size bug (512 vs 480) kills
   wake/barge-in; speaker enrollment never loaded.
6. **REV-10 (9 CONFIRMED)** — self-service peer pairing (F1, severe); compute endpoint
   never mounted (federation-9.3); health-probe path mismatch; deferred-queue policy
   unimplemented. Federation-phase work — coordinate with the compute-peer session.
7. **REV-08 (4 CONFIRMED)** — Approvals page orphaned off the rail (HIGH); NavRail ARIA
   tabs pattern half-implemented; 2 token violations; poll-interval leak.
8. **REV-11 (11 CONFIRMED)** — stray cancel POST on every completed turn can persist
   replies as "cancelled" (HIGH); queued-send drops pending approvals; 13-item worklist
   in the report.
9. **Founder gate** — FDR-DEC-01…04 drafts awaiting decisions (`.handoff/FOUNDER-DECISION-DRAFTS-2026-08-31.md`).

## 5. Merge notes

- Merge order: **merge current main into this branch first** (or rebase) to pick up
  `9a292ce6` (REV-03 fixes) — it touches `mcp/server.py`, `ha_event_stream/mapper`,
  `test_home_assistant.py`, `test_mcp_ha_tools.py`, which this branch also touches in
  places; expect small conflicts in `mcp/server.py` (both sides added phrase-gating —
  prefer the branch's `security_constants.py`-based single source).
- After the merge, the 5 merge-drift failures should disappear; rerun the full suite
  (worktree wrapper) + `npm run build` to confirm.
- `MASTER-TODO.md` was NOT updated on this branch (concurrent sessions edit it; the
  strikethroughs should land at merge time, from §1 above).
- The usage wall: this session lost 8 agents to a 429 mid-run; they were all salvaged by
  resuming them one at a time. Worked sequentially after that with no further losses.