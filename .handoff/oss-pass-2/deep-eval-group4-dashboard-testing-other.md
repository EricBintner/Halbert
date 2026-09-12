# Deep Critical Evaluation — Group 4: Dashboard/App/Onboarding/Diagnostics, Testing/Evals/QA/Ops, Other

Written from a full read of the three section files, the discovery digest, the coverage report, and the remediation tier assignment. Every packet is judged against what R-01..R-15 already merged, the standing rules in AGENTS.md, and whether the mechanism fits a single-user single-host machine that identifies as the computer itself.

---

## Workstream 1: dashboard-app-onboarding-diagnostics

### Packet: DIAG-01 — `halbert doctor` and the readiness endpoint

**What it actually proposes:** A `diagnostics/doctor.py` module with an ordered `(title, check)` registry and a `doctor_check()` decorator that always yields a `Finding` (reusing `findings/store.py`'s existing type, adding `fix_hint` and `RepairEffect`). A `halbert doctor [--json] [--fix]` CLI subcommand and a `GET /api/diagnostics` route render the same payload. The dead `utils/health.py` framework gets wired into `/health` with per-check `ok/degraded/unknown` states. Multiple doctor checks are specified: disk thresholds, SQLite bloat, version skew, configured-vs-observed drift, scheduler health, config-coherence snapshot, auto-clear of findings, content-signature snooze. The LLM judgement in `SystemHealthCheckTask` is deleted.

**Verdict: ACCEPT**

**Reasoning:**
- This is a real problem. Halbert has a dead `utils/health.py` framework (267 lines, unimported), a flat `/health` endpoint, and — critically — an `autonomous_tasks.py` self-health check that asks an LLM for the verdict. The standing directive "never a model where a template suffices" is directly violated by the live code. The doctor replaces that with deterministic thresholds. That alone justifies the packet.
- Overlap with merged remediation: R-03 (scheduler durability) already added `ticker_heartbeat`/`ticker_last_success`/`ticker_last_error` on-disk markers (A06-G11/A15-G5). HM16-C19's scheduler doctor check consumes those — it is a read-only consumer of R-03's output, not a duplicate. R-04 (conversation store hardening) touched `conversation_sqlite.py` corruption predicates; DIAG-02 handles the FTS classifier bug separately. R-05 (redaction registry) built the variant registry that OC04-M6's diagnostics-export variant registers into. No direct duplicate.
- No standing rule violated. The constraint "no model anywhere in a doctor check" aligns with the deterministic-policy directive. The "never name a model" rule is respected by OCC01-C12's configured-block (slot labels, resolution status, never model names).
- Effort justified. A founder running the machine would notice: the dashboard shows no health state, a corrupt DB degrades silently, a misconfigured MCP server has no surface. The doctor is the single highest-leverage diagnostics investment because it gives every other check a home.
- Minimum viable version: the registry + `halbert doctor --json` + `/api/diagnostics` + wiring `utils/health.py` into `/health` + deleting the LLM call in `SystemHealthCheckTask`. The SQLite bloat check, version skew, snooze-by-signature, and config-coherence snapshot are all valuable but can land as follow-on checks in the registry without blocking the core.

**Opportunities:** The doctor registry is the natural sink for residual checks from every other workstream. R-03's ticker markers, R-13's utility-slot locality result (A14-G4: a `:cloud` sibling passing as local), R-05's redaction coverage gaps — all become doctor checks. Build the registry once, populate incrementally.

---

### Packet: DIAG-02 — Store integrity on the diagnostics seam

**What it actually proposes:** Fixes the FTS corruption classifier bug (`_is_fts_write_corruption_error` at `conversation_sqlite.py:866-891` returns True for every `malformed` exception, the opposite of its docstring's claim), adds a read-only `open_read_only(path)` helper (`mode=ro`, `PRAGMA query_only=ON`), adds a divert/spool/replay path for a replaced or quarantined store handle, records `last_init_error`, and quarantines a zeroed file aside instead of bricking every boot.

**Verdict: ACCEPT**

**Reasoning:**
- This is a real, confirmed bug. The FTS classifier is audit A08-G1 and "the first A08 confirmed bug." The docstring says it mirrors Hermes; the code does the opposite. A bare `malformed` in any exception message triggers the FTS fail-open path, which lets the canonical write "continue" into a structurally damaged file. This is a data-loss bug, not a theoretical concern.
- Overlap with merged remediation: R-04 (conversation store + state ledger hardening) is the merged packet that touched `conversation_sqlite.py` corruption internals. However, R-04's scope was the store + state ledger hardening broadly; the FTS classifier bug (HM11-M1) is called out in the section file as "identical to A08-G1" and the section says "fix once" — meaning R-04 may or may not have closed this specific line. The section file's audit gap list at line 143 says "A08-G1 [confirmed/medium] and the first A08 bug: `_is_fts_write_corruption_error` contradicts its docstring — identical to HM11-M1; fix once." If R-04 already fixed the FTS classifier, DIAG-02 is mostly residual (read-only opener, divert path, init-error record). If not, the FTS fix is urgent.
- The read-only opener (OC01-C15) is a prerequisite for DIAG-01's probes, HM11-C3's readiness checks, and OC04-C4's bloat check. It is small, uncontroversial, and should ship regardless.
- The divert/spool/replay path (HM11-M5) is priority low in the section file itself: "becomes real the day a restore-from-backup flow exists." With no restore flow and no users, this is infrastructure for a consumer that does not exist yet.
- No standing rule violated.
- Minimum viable version: (1) fix the FTS classifier bug if R-04 didn't, (2) add `open_read_only()`, (3) record `last_init_error` and surface in `/health`. DEFER the divert/spool/replay path.

**If RESHAPE:** Split into "fix the bug + read-only opener" (ship now) and "divert/quarantine path" (defer until a restore flow exists).

---

### Packet: DAEMON-01 — One backend per data dir, exit vocabulary, PID-safe identity, boot forensics, wedge reclamation

**What it actually proposes:** An advisory flock on `<data_dir>/backend.lock` taken at FastAPI startup so a second launch attaches to the incumbent instead of spawning a second backend (which today runs two schedulers, two heartbeats, two writers against one conversation store). Distinct exit codes (75 = restart-me, 78 = fatal-config) plus a `supervised()` probe for launchd/systemd. PID-reuse-safe backend identity via `(pid, start_marker)` so an orphaned sidecar exits when the shell dies and the OS recycles the pid. A ring-buffered stdout/stderr tail captured at spawn so an import-time traceback survives in a native dialog. A stuck-turn reclamation watchdog that cancels a wedged turn after a no-progress age, gated by a closed enum of skip reasons (`awaiting_confirm`, `approval_pending`, etc.), with one typed receipt per reclamation to `obs/audit.py`.

**Verdict: RESHAPE**

**Reasoning:**
- The single-instance lock (HM11-M3) is a real problem today. The section file confirms: `lib.rs:44-70` and `dashboard/__main__.py:126,146-152 --find-port` both deliberately start a second backend on another port. Two schedulers against one conversation store is a data-corruption vector. This is the mechanism that makes "single-user single-host" actually true. ACCEPT this part.
- The exit vocabulary (HM11-M2) is cheap (two constants + a `supervised()` probe) and is a prerequisite for the stuck-turn watchdog and for OC22-C10's launch-at-login. ACCEPT.
- The stuck-turn reclamation (OC08-M1 = A07-G10) is a real problem — `state_machine.py:512-519` bounds only the acquire side; a wedged turn holds the lock for the process lifetime. But it touches `state_machine.py`, the hottest file in the tree (the section file itself names it "the fourth touch on the file; merge last"). R-01 (interrupt algebra) and R-06 (turn digest) and R-12 (session tree) all touch this file. The reclamation watchdog is valuable but should be sequenced after the opus-tier state-machine work settles.
- The PID-reuse-safe identity (HM18-C15) is medium priority and depends on `lib.rs` changes. The boot forensics ring buffer (HM18-C17) is medium and depends on `lib.rs` too. Both are real (a Finder-launched bundle's import-time traceback goes nowhere today) but they are Tauri/Rust-side work that should attach to the DIST-1 packaging track, not the diagnostics workstream.
- Overlap with merged remediation: R-03 (scheduler durability) added heartbeat liveness markers but did not address the single-instance problem. No direct duplicate.
- No standing rule violated. The exit codes and supervisor detection are standard process-lifecycle hygiene.
- Effort: the full packet is L. The single-instance lock + exit vocabulary is S. The stuck-turn watchdog is M and hot-file-sensitive.

**If RESHAPE:** Split into DAEMON-01a (single-instance lock + exit vocabulary + `supervised()` probe — S, ship now) and DAEMON-01b (stuck-turn reclamation — M, defer until state-machine work settles, merge last in its wave). Fold PID-reuse identity and boot forensics into DIST-01's Tauri-side work.

---

### Packet: LOG-01 — Log file, tail, Logs page, support bundle

**What it actually proposes:** Replaces the hand-built `basicConfig(format='{"ts": ...}')` JSON-by-%-interpolation (which breaks on any quote/backslash/newline in a message and forges a record on `", "level": "error` in a tool string) with `obs/logging.JsonFormatter` on a `RotatingFileHandler` under `log_subdir()`, keeping stdout. A redaction filter on the root handler applies `security/result_redaction.redact_error_text` (registry pass first per A03-G2, then pattern pass) to every record. A byte-bounded log-tail reader that drops corrupted partial lines. A Logs page with cursor-based incremental tail. A redacted, path-safe support bundle zip. A diagnostics-export redaction variant. A control-character sanitizer. A bounded fire-and-forget background-work helper.

**Verdict: ACCEPT**

**Reasoning:**
- The log-format bug is real and live. `dashboard/__main__.py:21-25` builds JSON by %-interpolation. Any `"` or `\n` in a tool/user message breaks the line. This is not theoretical — the section file spot-checked it. `obs/logging.py:9-21` already has a correct `JsonFormatter` that the daemon never installs. This is a one-file fix with high value.
- The redaction filter (OC08-C8) closes audit gap A03-G9: "the MCP dispatcher logs the raw exception before returning the redacted error." This is a confirmed leak. R-05 (redaction registry) built the registry and the Tier-2 choke point at the response surface, but logs are a separate emit path — the filter is not a duplicate of R-05, it extends R-05's registry to a new surface. The section file explicitly says "a second weaker pass would regress the 2026-09-06 audit" — the filter must use the existing redactors, not a new one.
- Overlap with merged remediation: R-05 built `redact_error_text` (A03-G5's helper) and the registry ordering (A03-G2: registry pass first). LOG-01's filter is a consumer of R-05's output, not a duplicate. R-10 (speech egress sanitizer) is unrelated. No duplicate.
- The support bundle (OC08-C7) and diagnostics-export variant (OC04-M6) depend on DIAG-01's doctor JSON. They are M effort and medium priority. The Logs page (OC23-C16) is M and medium. These are valuable but not urgent — the log file + redaction filter + tail reader is the MVP.
- No standing rule violated. The redaction is deterministic, registry-based, never a model. The support bundle is staged (UI button stages, never sends).
- Effort justified. An operator would notice: today there is no log file, no way to see what happened before a crash, and secrets leak into stderr. The MVP (file + filter + tail) is S effort.
- Minimum viable version: install `JsonFormatter` on a `RotatingFileHandler` + install the `RedactingFilter` on the root handler + the tail reader. DEFER the Logs page, support bundle, and diagnostics-export variant to follow-on packets after DIAG-01 lands.

**Opportunities:** The redaction filter and the `RedactingFilter` pattern are shared with OTHER-P2 (redacting, correlated logging). The two packets touch the same 30-line `obs/logging.py` hub and the same root handler in `dashboard/__main__.py`. They should be one packet, not two. See cross-cutting opportunities below.

---

### Packet: BIND-01 — Bind what was checked to what is touched

**What it actually proposes:** Routes every side-effecting write through `bind_path()`/`is_governed_path()` (currently dead code in `lease.py`) so a symlink swapped between guard inspection and write is refused. Adds a shared `utils/path_boundary.py` with lexical + realpath + hardlink containment. Adds a read-only recovery inventory with a demotion ladder for deletion candidates. Resolves `argv[0]` in the command-safety path and flags binaries outside trusted dirs. Strips `BASH_ENV`/`ENV`/`CDPATH` etc. from shell-wrapped spawn env. Relocates execute_code scratch to `<data_dir>/scratch/<run_id>` with `lstat` verification. Makes deny always win, evaluated before any I/O, with remembered approvals keyed to the canonical target. Adds scope escalation as a typed lattice transition. Adds CAS preconditions to config writes. Applies sensitivity tiers to the AI-proposed diff path. Adds write-only secret response models and per-credential `allowed_hosts` egress binding.

**Verdict: RESHAPE**

**Reasoning:**
- The core invariant — "the object the policy inspected must be the object the effect lands on" — is a real problem. `tools/write_config.py` reads a path, backs it up with symlink-following `shutil.copy2`, then opens it again with no `(dev, ino)` binding. `bind_path()` exists in `lease.py:394-413` and has no production caller. This is a TOCTOU gap.
- Overlap with merged remediation: R-08 (permission lattice: ask axis, approvals, leases, halt) merged the lattice, the ask axis, approvals, and leases. OC21-M3 (scope escalation as a typed lattice transition) and OC21-M4 (deny-always-wins, keyed to canonical target) touch `lease.py` and `consent/store.py` — files R-08 owns. These should be sequenced after R-08 or dispatched with the permissions workstream, not independently. The section file itself says "dispatch with the permissions workstream's packet if one is running."
- R-07 (execute_code hardening) already touched `tools/execute_code.py`. OC21-M2 (scratch root relocation) and A04-G3 (unbounded spill file) sit on the same file. If R-07 already capped/relocated the spill path, OC21-M2 is residual. If not, it should be a follow-on to R-07, not a standalone packet.
- The config CAS precondition (OC07-C8/OC12-C10) is a real bug: `model/llm_config.py:765-778 save()` replaces the whole section with no base check, and `routes/settings.py:1094-1111` rewrites `preferences.yml` unlocked. The founder runs concurrent sessions — a lost-update on the API-key store is a confirmed live defect (OC05's verifier found it). This is S effort and should ship independently of the security-heavy half.
- The `allowed_hosts` per-credential egress binding (OC23-M2) is M effort and gated by founder decision FD-4. It is a new security mechanism, not a binding fix. DEFER.
- The file-delivery convention (HM11-C14) is gated by FD-3 and the section file's own recommendation is "no for now." DEFER.
- No standing rule violated. The boundary is "scope by capability boundary, not filesystem path" — the section file explicitly states this constraint.
- Effort: the full packet is L. The security half (M1/M4/M2/M3) is S+S+M+S. The config-write trio (C8/M5/M2) is S+S+M.

**If RESHAPE:** Split into BIND-01a (config CAS preconditions — S, ship now, it is a confirmed live bug) and BIND-01b (file-binding security: `bind_path()` activation, path boundary helper, exec allowlist resolution, shell env stripping — M, sequence after R-08 and R-07 settle). DEFER the `allowed_hosts` egress binding and file-delivery convention to founder decisions.

---

### Packet: SURFACE-01 — Progress, staleness, polling, approvals, rendering, onboarding, skills

**What it actually proposes:** A live progress-draft compositor that publishes one dedup'd status object over SSE (replacing the keep-nothing `StatusStrip.tsx` snapshot). A per-turn file-mutation diffstat. A revisioned per-task progress card. A structured `{layer, code, retryable}` error surface. A "cold local model is loading" notice. A context-usage breakdown anchored on real provider usage. Stale-tone overrides on host meters (tracking `lastSuccessAt` so a wedged backend doesn't show a red bar over data of unknown age). A typed refresh policy (visibility/TTL/interruption/coalescing) replacing 20+ `setInterval` sites. A reconnect owner with bounded backoff. Approval expiry enforcement (currently `expires_at` is never compared to now, so a timed-out approval can still be approved). An LTR-forced approval surface (trojan-source defence). Closing orphaned code fences before rendering an interrupted reply. Code-region-aware tag stripping. Diagnostics sparkline tiles. A keyboard-shortcut catalog. Wizard back-navigation with answer replay. A skills settings page with per-category toggles. An automation blueprint catalog. A stat-based change watcher. React/react-dom pair drift tests.

**Verdict: RESHAPE**

**Reasoning:**
- The approval expiry bug (OC23-M6) is real and high priority. `approval/engine.py:317-332` never compares `expires_at` to now; `EXPIRED` (`:28`) is never assigned. A timed-out approval can still be approved. This is a security-relevant defect. R-08 (permission lattice) merged the ask axis, approvals, and leases — but the expiry enforcement gap may be residual. The section file lists it as "absent" and "spot-checked." If R-08 didn't close it, it is urgent. ACCEPT this sub-item unconditionally.
- The stale-tone override (OC23-C15) is a direct application of the standing directive "grounded in measured data." `Dashboard.tsx:48-58` keeps the last metrics on a failed poll, so a wedged backend leaves a red bar over data of unknown age. This is S effort and the section file raised it to high. ACCEPT.
- The progress-draft compositor (OC18-C1) is M effort and touches `state_machine.py` or `turn_event_tee.py` — hot files. It is high value (the status strip shows nothing useful today) but it should be sequenced after the opus-tier state-machine work. RESHAPE to defer.
- The typed refresh policy (OC23-M4) is high value: 20+ `setInterval` sites, a Tauri window left open all day keeps the host busy answering polls nobody reads. M effort. ACCEPT but it is frontend-only and can proceed independently.
- The reconnect owner (OC23-C12) is S effort and low priority — the 3-5s fixed backoff works for localhost. ACCEPT as low.
- The wizard back-navigation (OC07-C4) is M and medium. It depends on BIRTH-1's first-conversation redesign. DEFER until BIRTH-1 settles.
- The skills settings page (HM10-C20) is M and medium. A13-G10 is the same gap. ACCEPT — there is no skill disable surface today.
- The automation blueprint catalog (HM16-C1) needs a job-creation API first (`POST /api/jobs` doesn't exist). DEFER until that API ships.
- The change watcher (HM18-C5) is M and medium. It is the producer half of a skills-reload path (A13-G2). ACCEPT if it can be built without touching hot files.
- The LTR trojan-source defence (OC23-M1) is S and medium. `ConfirmationDialog.tsx:52-57` renders via `dangerouslySetInnerHTML` with no direction attribute. This is a real security gap on the one screen where a privileged action is authorised. ACCEPT.
- The remaining items (sparkline tiles, keyboard shortcuts, context-usage breakdown, tool tally, sender identity, Ollama cache, WS disconnect test, JSON-schema form, React pair test) are low priority and can be deferred or attached to their feature's packet.
- Overlap with merged remediation: R-06 (echo guard, display projection, turn digest) merged the display projection. A05-G2 (timeline reload serves persisted tool blocks with raw args) is the display-projection twin — if R-06 closed it, the history-projection prerequisite for TERM-02 is met. R-08 (permission lattice) merged approvals — the expiry enforcement is likely residual. R-11 (skills plane) merged skills — HM10-C20's settings page is a UI consumer of R-11's backend.
- No standing rule violated. The progress card is a turn side-car, not a session list. The status copy names the slot, never the model. Colours from shared tokens.
- Effort: the full packet is L. The section file itself says "too large for one branch" and proposes SURFACE-01a/b/c.

**If RESHAPE:** ACCEPT the sub-set that is (a) a confirmed bug or (b) S-effort and independent: approval expiry enforcement, stale-tone override, LTR trojan-source defence, typed refresh policy, skills settings page, reconnect owner. DEFER the compositor, wizard replay, blueprint catalog, and change watcher to their feature dependencies. The low items attach to their natural homes.

---

### Packet: TERM-02 — Watched-terminal read and close tools

**What it actually proposes:** A `tools/read_terminal.py` that round-trips to the frontend xterm buffer over the existing WS with a blocking request id and bounded timeout, letting the agent read the in-app terminal pane (page scrollback with `start_line + count`). A `close_terminal` that hides a tile without killing the process. Both gated by `has_capability()`, withdrawn from the tool list when no renderer is attached. The read passes through the display seam (`security/display_transport.py`) and the echo guard. The withdraw-not-refuse rule from HM10-C17 is adopted. A05-G2 (history projection on the shared display seam) is fixed first. HM09-C18 (agent-proposed MCP server install as a staged card) is held pending FD-7.

**Verdict: ACCEPT**

**Reasoning:**
- This is a real feature gap that aligns with the founder's recorded direction: "user shells stay but are WATCHED by the AI; agent reuses idle terminals." `streaming/terminal_bridge.py:3-25` is one-way executor→SSE; `InlineTerminals`/`TerminalTile` render tiles with no agent-callable read. The mechanism is concrete and well-scoped.
- Overlap with merged remediation: R-06 (echo guard, display projection) merged the display projection. A05-G2 (timeline reload serves persisted tool blocks with raw args) must be fixed first so the read seam and the timeline share one projection. If R-06 closed A05-G2, the prerequisite is met. If not, it is a small fix that should precede TERM-02.
- No standing rule violated. The read passes through the display seam and echo guard (a user shell can contain a pasted secret). The capability gate uses `has_capability()`, the only gate. Commands staged from the UI are staged, never executed — the read is read-only, the close is non-destructive (hide, not kill).
- Effort justified. M effort for a feature the founder has explicitly directed. A user would notice: the agent can see what's happening in the terminal beside the chat.
- FD-2 (may the agent read user shells, and under which consent axis) is a real founder decision. The recommended default (own capability `terminal.read_user_pane`, defaulting on for owner, denied for guests) is sound.
- HM09-C18 (agent-proposed MCP install) is correctly held — it needs the B6 MCP-server audit to close first and FD-7.

**Opportunities:** The withdraw-not-refuse rule (HM10-C17) is a general pattern for any capability-gated tool: when the capability is absent, the tool is not in the list, rather than present and failing. This should be a shared convention, not terminal-specific.

---

### Packet: DIST-02 — Signing, entitlements, usage strings, login item

**What it actually proposes:** `entitlements.mac.plist`/`entitlements.mas.plist` and `Info.plist` overrides for camera, microphone, screen recording, Apple Events, local network, worded in the onboarding name (never the raw hostname). A launch-at-login toggle using `tauri-plugin-autostart` with the idempotent-enable / non-destructive-disable guard. Banked design rules for the updater handoff gate and reset scope ladder.

**Verdict: DEFER**

**Reasoning:**
- The entitlements and usage strings are real gaps — `tauri.conf.json bundle.macOS` has `entitlements: null` and `signingIdentity: null`, and no `NSCameraUsageDescription`/`NSMicrophoneUsageDescription` exist. Without a matching string, the OS kills the process on first TCC request. The security audit already documents this (AVFoundation terminating the caller while `webcam_capture.py:102` blames the hardware).
- However, the section file itself says: "entitlements and signing are both null, so strings alone buy nothing durable (`os_grant.py:11-16`: an unsigned build's TCC grants do not persist)." The prerequisite is DIST-1's signing identity. Without a signing identity, usage strings are necessary but not sufficient — TCC grants won't persist across launches.
- The launch-at-login toggle depends on DAEMON-01's exit vocabulary (HM11-M2) so a supervised backend speaks the exit codes.
- No standing rule violated. The usage strings are worded in the onboarding name, never the raw hostname.
- This is correctly prerequisite-shaped. The gate is DIST-1's signing identity. DEFER until DIST-1 opens.

---

## Workstream 2: testing-evals-qa-ops

### Packet: T1 — Test-run blast radius

**What it actually proposes:** One `_hermetic_environment` autouse fixture in `conftest.py` that scrubs credential-shaped env vars (`HALBERT_API_TOKEN`, `*_API_KEY`, `*_TOKEN`, `*_SECRET`), `delenv`s Halbert's behavioural flags (voice/TTS entries that would produce "real synthesis, real playback, out of the developer's speakers"), redirects `HOME` to per-test tempdirs, pins `TZ=UTC`/`LANG=C.UTF-8`/`PYTHONHASHSEED=0`, and re-pins every import-time path constant (starting with the conversation store's default path that ignores `HALBERT_DATA_DIR`). An autouse egress-safety net that patches `socket.socket.connect` to refuse non-loopback addresses with a `RuntimeError`, with a `pytest.mark.allow_network` opt-out. A fail-closed live-database test-isolation guard (`testing_guard.py`) that checks env markers and a memoised process-ancestry walk, raising before any connection/mkdir/pragma when a test-context process would open a production path. A live-system guard intercepting `os.kill`, `os.killpg`, and `subprocess.Popen` against a denylist of killer executables.

**Verdict: ACCEPT**

**Reasoning:**
- This is the highest-value packet in the testing workstream and possibly across all three workstreams. The audit pass already confirmed two live-store leaks: the conversation store's default path ignores `HALBERT_DATA_DIR` so pytest can open the production `conversations.db` (A08-G12 + own bug), and skills tests read the developer's real `~/.config/halbert/skills` (A13 own bug). These are not theoretical — they are confirmed defects where a test run can corrupt the audit hash chain or depend on the machine's home directory.
- The egress-safety net is the cheapest high-leverage item. `model/client.py`'s context probe spawns background threads, and `tests/test_num_ctx.py:29-38` warns that an unjoined probe thread "outlives the patch and reaches a real daemon." A process-wide `socket.connect` patch catches what a per-test mock cannot, including off-thread calls. The section file raised this from medium to high.
- The live-system guard is justified by the blast radius: 28 test files import `subprocess` and many run it for real. `streaming/pty.py:362,432` calls `os.kill(self._pid, SIGTERM/SIGKILL)`, `dashboard/routes/services.py` shells `systemctl` with `stop/disable/restart`. A test that accidentally sends a real kill command to the developer's live processes is a serious hazard.
- Overlap with merged remediation: R-04 (conversation store hardening) touched `conversation_sqlite.py` but did not fix the default-path-ignores-`HALBERT_DATA_DIR` bug — that is a CFG-1 issue (the path resolver), not a store-hardening issue. R-03 (scheduler durability) is unrelated. No duplicate.
- No standing rule violated. The hermetic environment is a test-only mechanism. The `allow_network` marker is explicitly registered in `[tool.pytest.ini_options]` — the section file correctly notes that the "existing integration marker" does not exist and must be defined.
- FD-3 (raise vs redirect for the live-DB guard) is a real decision. The recommended default (raise, naming the path and the bypass marker) is correct — a silent redirect hides the misconfiguration that would corrupt the audit hash chain.
- Effort justified. The full suite runs in one interpreter today; the known failure mode is cross-file interpreter-state leakage (205 failures from the wave-4 merge log). T1 makes the suite hermetic, which is a prerequisite for T2 and T4.
- Minimum viable version: the hermetic environment fixture + the egress-safety net + the live-DB guard. The live-system guard can follow.

**Opportunities:** The hermetic environment fixture and the live-DB guard share the same "inventory every import-time path constant" task. The conversation store's default path is the first; the canon-store constants in `conftest.py:9-47` are already done. This inventory should be a shared checklist, not rediscovered per-fixture.

---

### Packet: T2 — Suite integrity and the async ratchet

**What it actually proposes:** A `scripts/run_tests_isolated.py` runner (~60 lines) that runs one `python -m pytest <file>` subprocess per test file, bounded by `os.cpu_count()`, carrying the two Halbert-specific constraints (`arch -arm64` prefix, `PYTHONPATH` pinned to `halbert_core`). A ruff gate selecting five ASYNC rules (ASYNC210/220/221/251 + PLW1514) with a per-file-ignores ratchet that freezes existing violations so the gate blocks new ones immediately. An AST guard at collection time that flags a `FunctionDef`/`AsyncFunctionDef`/`ClassDef` name defined twice in one scope. Plus the live defect OC22-C7 (Darwin `get_memory_info` opens `/proc/meminfo` unconditionally).

**Verdict: ACCEPT**

**Reasoning:**
- The per-file isolation runner addresses a confirmed, measured problem: 205 failures from the wave-4 merge that reproduce on the baseline and pass in isolation. The section file correctly rejects xdist ("persistent workers accumulate state across files, which is exactly the leakage we wanted to fix"). The process boundary is the isolation boundary.
- The ruff ASYNC gate addresses a confirmed, live problem: `dashboard/routes/services.py:246` runs `subprocess.run(['systemctl','status',...], timeout=10)` inside an `async def` — a ten-second freeze of the uvicorn event loop. More sites at `:276`, `:285`, `:448`, `dashboard/routes/discovery.py:501`, `dashboard/routes/rag.py:408`. Every one stalls the heartbeat, the WS pumps, and the scheduler tick for its duration. This is not a style preference; it is a liveness bug.
- The AST shadowed-definition guard is preventive (zero hits today) but priced as ~30 lines. Halbert's recorded working pattern is multiple concurrent sessions editing the same test files. A duplicate autouse fixture would silently disarm isolation for a whole file.
- The Darwin `get_memory_info` fix (OC22-C7) is a live defect: `tools/system_info.py:75-107` opens `/proc/meminfo` unconditionally; on Darwin the `FileNotFoundError` is caught and returned as "Error getting memory info: ..." straight to the model. The correct darwin logic already exists at `discovery/scanners/system_profile.py:443-460`. This is the "grounded in measured data" directive violated — the machine reports an error string about its own memory.
- Overlap with merged remediation: none. R-15 (eval harness) is in `continuity/`, not the test suite. No duplicate.
- No standing rule violated. The runner carries the `arch -arm64` prefix and the `PYTHONPATH` pin that AGENTS.md mandates.
- FD-1 (replace vs beside `pytest tests/` in CI) is a real decision. The recommended default (beside, as a second required job, until the surviving-failure list is reconciled to zero) is correct — the 205-failure set must be explained before the runner hides it.
- Effort justified. The runner is ~60 lines. The ruff gate is a config addition + baseline freeze. The ASYNC fixes are `await asyncio.to_thread(...)` / `asyncio.create_subprocess_exec` conversions.
- Minimum viable version: the ruff gate (config + baseline) + the Darwin memory fix. The isolated runner is valuable but can follow T1.

**Opportunities:** The ASYNC ratchet and the per-file isolation runner are complementary: the ratchet prevents new blocking calls, the runner prevents cross-file leakage. But they are independent — the ratchet can ship first. The Darwin memory fix is a one-file fix that should ship immediately regardless of the rest of T2.

---

### Packet: T3 — Verification before "done"

**What it actually proposes:** A verification evidence ledger (`agents/verification_evidence.py`) with three SQLite tables that shell-tokenise terminal commands, match them against a workspace's canonical verify commands, scope targeted/full, and only count attributable exit statuses. An edit after the last evidence makes the status `stale` by timestamp comparison. A verify-on-stop nudge: at turn end, if any changed path is code and `verification_status()` is not `passed`, synthesise one bounded follow-up naming the exact status and changed paths, asking for a real command or an honest blocker. A minimal stop-gate seam in `state_machine.py` (an ordered list of pure gate callables returning `continue(nudge)` or `pass`, with a per-turn attempt counter). An invented-completion-claim rate as an eval metric. A two-layer verification discipline for UI work (state-read proof is not rendered-UI proof).

**Verdict: RESHAPE**

**Reasoning:**
- The founder's own session notes record repeated premature-success episodes. The verification evidence ledger (HM04-C2) is the deterministic answer: it tracks what was actually proven, going stale on the next edit. This is a real problem for a machine that edits its own code.
- The verify-on-stop nudge (HM04-C1) is policy-only (never runs checks itself, never blocks a turn, appends one `"role": "user"` row). It is bounded to one nudge per turn (max_attempts=2). The cost is one extra local model call on unverified code edits. This is cheap and directly targets the recorded failure mode.
- However, the stop-gate seam in `state_machine.py` is a new framework. The section file confirms: "grep `stop_gate|pending_verification|finish_reason` over `agents/*.py` hits only `llm_client.py:42/277/489`, a response dataclass field with no consumer. The state machine has no place to hang 'the model stopped with text; run the gates'." This is hot-file work (`state_machine.py` is the hottest file in the tree). R-01, R-06, R-12 all touch it. The stop-gate seam should be sequenced after the opus-tier state-machine work.
- The invented-completion-claim eval metric (OC24-C8) extends the packet-09 eval harness (R-15, merged). It is S effort and depends on C2's ledger. ACCEPT as a follow-on to the ledger.
- The two-layer UI verification discipline (OC24-C20) is one paragraph in the repo's dev conventions. ACCEPT — it costs a paragraph and names a failure mode the founder has hit.
- Overlap with merged remediation: R-15 (eval harness and verdict contract) merged the eval framework. The invented-completion metric is a new dimension in the existing verdict/scorecard rows, not a duplicate. R-06 (turn digest) merged `record_effect` at `executor.py:645-647`, which the ledger's `mark_workspace_edited` calls. The ledger is a consumer of R-06's output.
- No standing rule violated. The nudge is a `"role": "user"` row, keeping role alternation legal. It never blocks a turn. No LLM in the gate logic.
- FD-2 (nudge default on or off) is a real decision. The recommended default (on, bounded, with a config switch) is sound — Hermes defaults off, but Halbert's own session notes record the premature-success episodes.
- Effort: the ledger is M. The nudge + stop-gate seam is M and hot-file-sensitive. The eval metric is S. The convention paragraph is S.

**If RESHAPE:** ACCEPT the verification evidence ledger (M, no hot files) + the invented-completion eval metric (S, extends R-15) + the UI verification convention paragraph (S). DEFER the stop-gate seam and the verify-on-stop nudge until the opus-tier state-machine work settles, then wire them in one branch.

---

### Packet: T4 — Wire contracts and the model-name surface eval

**What it actually proposes:** A loopback `ThreadingHTTPServer` fixture that records request path, headers, and JSON body, driving `agents/llm_client.py`'s real async client at both build sites (Ollama chat/generate and Anthropic messages shapes) and asserting the body (model tag, `options.num_ctx`, `tools` presence/absence, `stream` flag) and headers (no `Authorization` on a local target). A SEC-21 regression at the wire: a `:cloud`-tagged slot never produces a request from the local-mode code path. A surface-exhaustive constraint-removal eval for the "never a model name" directive: enumerate every production surface, drive each through a local-capture fixture with a sentinel model tag, and assert only slot labels render. Extending the static guard's `_sources()` to the three `model/*.py` files it misses. A large-batch eval orchestrator discipline as a README note.

**Verdict: ACCEPT**

**Reasoning:**
- The wire-level contract tests address a real gap. `agents/llm_client.py`'s async aiohttp payloads (`:128-137`, `:207-216`) have no body assertion. Nothing runs a real transport against a loopback server, so header/encoding/proxy behaviour is untested. The existing `tests/test_num_ctx.py:124-170` asserts the sync Ollama path only.
- The SEC-21 regression at the wire is directly aligned with the standing rule: `is_local_model()` in `llm_config.py:181` is the only judge of local vs cloud. A `:cloud`-tagged slot producing a request from the local-mode code path would be a locality predicate failure. Testing this at the wire level (not just the predicate level) is the strongest proof.
- The model-name surface eval extends the existing static guard (`tests/test_no_model_names_in_user_facing_source.py`), which the section file correctly identifies as "a tripwire for drift, not a proof of absence" — it is a source-text match over two directories only, never a runtime surface. The runtime eval catches a name assembled at runtime.
- Overlap with merged remediation: R-15 (eval harness) merged the eval framework. T4's model-name surface eval is a new battery in the existing framework, not a duplicate. R-13 (utility slot) merged the locality fix — the SEC-21 regression test pins R-13's fix at the wire.
- No standing rule violated. The wire tests scrub `os.environ` before constructing a client (the hermetic env from T1). The model-name eval never names a model — it uses a sentinel tag and asserts only slot labels render.
- Prerequisite: T1 (env scrub + loopback guard). The wire tests need the hermetic environment to be meaningful.
- Effort justified. The wire suite is S-M. The model-name eval is M. The orchestrator note is S.
- Minimum viable version: the wire contract tests for the Ollama and Anthropic shapes + the SEC-21 regression. The model-name surface eval can follow.

**Opportunities:** The loopback fixture is shared with T1's egress-safety net — both need a `ThreadingHTTPServer` that only accepts loopback. Build the fixture once.

---

### Packet: T5 — Doctor, diagnostics and host-truth

**What it actually proposes:** Unifies `utils/health.py`'s checks through `findings/store.py`'s `Finding` shape (severity, `why_trust` as `path:line` provenance, fix hint) rather than growing a second parallel shape. A SHA-256-pinned native-artifact verification for MCP server commands with symlink rejection, registered as a health check. A coverage registry: a static table of egress seams (MCP response choke point, dashboard WS, TTS/Wyoming path, terminal stream, turn-event tee, scheduler receipts) with `captured`/`proxy-only`/`uncovered` status and a health check per uncovered seam. A redacted diagnostic support bundle (extends the packet-09 eval harness). Fixes the Darwin `get_memory_info` defect (shared with T2).

**Verdict: RESHAPE**

**Reasoning:**
- The findings-shape unification (OC09-C16) is S effort and should be done first — it is the prerequisite for OC21-C2 and OC11-C11 registering into it. The section file says "do it first in the packet because OC21-C2 and OC11-C11 register into it." ACCEPT.
- The SHA-256 artifact verification (OC21-C2) is a real gap: `mcp/client.py:229-284` spawns external MCP servers by a config-supplied `command`, and audit gap A17-G3 confirms a `write_file` to `mcp_config.yml` classifies MEDIUM on macOS and the health monitor launches the new command within one tick. Verifying the binary by content hash against a manifest pinned at first approval is a deterministic gate. ACCEPT.
- The coverage registry (OC11-C11) is S effort and low priority. It is a static table that says where the redaction choke point is not. It is valuable as documentation but not urgent. ACCEPT as low.
- The support bundle (OC09-C13) is M effort and medium. It depends on C16's registry and DIAG-01's doctor JSON. It overlaps with LOG-01's support bundle (OC08-C7). These are the same mechanism — one bundle, not two. RESHAPE to merge with LOG-01's bundle.
- The Darwin memory fix is shared with T2. Ship once.
- Overlap with merged remediation: R-05 (redaction registry) built the registry. The coverage registry is a consumer of R-05's output (it documents where the registry is enforced). R-09 (MCP client boundary) merged the MCP client boundary — the artifact verification is a new check on top of R-09's boundary, not a duplicate. R-15 (eval harness) merged the eval framework — the support bundle reuses the redaction variant registry.
- No standing rule violated. The artifact verification is deterministic. The coverage registry is documentation. The support bundle is staged, never sent.
- Effort: the unification is S. The artifact check is S. The coverage registry is S. The bundle is M (shared with LOG-01).

**If RESHAPE:** ACCEPT the findings-shape unification + the SHA-256 artifact verification + the coverage registry. MERGE the support bundle with LOG-01's OC08-C7 — one bundle, one packet, one redaction variant.

---

### Packet: T6 — Posture contracts

**What it actually proposes:** Two vitest contract tests: (1) parse `tauri.conf.json` and assert `security.csp` is non-null and outbound navigation is deny-by-default; (2) parse the actual plists and assert every `com.apple.security.device.*` entitlement granted to the main app is also granted to the inherited helper. An npm install-script allowlist pinned to the lockfile it gates (`.npmrc` with `ignore-scripts=true` plus a short explicit allowlist). A security-regression rulepack (5-10 rules anchored on findings that actually recurred, each carrying `finding-id` + review-doc path metadata). An upstream-tracking loop over the three origin repos narrowed to one `detector_sweep`-class job.

**Verdict: RESHAPE**

**Reasoning:**
- The desktop-security contract tests are real gaps. `tauri.conf.json:22-24` has `"csp": null` and `:30-33` `"shell": {"open": true}`. The webview renders agent- and RAG-influenced data through `<a href={doc.url} target="_blank">`. There is no deny-by-default window-open policy. This is a security posture gap that a test can pin. ACCEPT.
- The entitlements test is blocked: no `entitlements.plist`, no `Info.plist` exist. The test can assert their absence as a failing contract, but the fix is DIST-02's work. DEFER the entitlements half until DIST-02 ships.
- The npm install-script allowlist is a real concern: every transitive postinstall runs unrestricted as the founder on the host Halbert administers, and the design-system workspace pulls a full Storybook 8 tree. FD-6 gates this. ACCEPT the posture decision and the test.
- The security-regression rulepack is M effort and the section file correctly lowered it from high to medium: "the reader's task ('one rule per closed SEC-N finding' across 186 findings) is the wholesale copy the origin's own contract warns against." A starter set of 5-10 rules anchored on findings that actually recurred is the right scope. ACCEPT but defer the async-blocking rule to T2's ruff gate (the section file says "overlaps M1's ruff gate and should defer to it").
- The upstream-tracking loop is S effort and low priority. It registers one `detector_sweep`-class job pointing at the three origin repos. ACCEPT as low — it is a scheduler config change, not code.
- Overlap with merged remediation: none directly. R-05 (redaction) and R-08 (permission lattice) are the sources of the findings the rulepack would anchor on, but the rulepack is a static analysis layer, not a duplicate.
- No standing rule violated. The rules are deterministic, metadata-bound, never touch runtime.
- FD-5 (entitlements test scope), FD-6 (npm posture), FD-7 (rulepack engine choice) are real decisions.

**If RESHAPE:** ACCEPT the CSP/window-open contract test + the npm install-script allowlist + the upstream-tracking job. DEFER the entitlements test until DIST-02 ships. DEFER the rulepack's async-blocking rule to T2's ruff gate. The starter rulepack (5-10 rules) can proceed once FD-7 picks an engine.

---

## Workstream 3: other

### Packet: OTHER-P1 — State backup, create-only

**What it actually proposes:** A `backup/create.py` module exposing `create_state_backup(state_dir, out_path) -> BackupResult` that tars the state dir while (a) skipping volatile paths (`.sock`/`.pid`/`.tmp`, sqlite transient files), (b) retrying only tar EOF/grow-shrink errors with backoff, and (c) refusing any symlink whose resolved target leaves the archive root. A `backup/sqlite_snapshot.py` using `sqlite3.Connection.backup()` (online backup API, no lock of the writer) followed by `PRAGMA integrity_check` on the copy. A vanished-file tolerance filter. A `halbert backup` CLI verb. An optional dashboard button on `Backups.tsx` later.

**Verdict: ACCEPT**

**Reasoning:**
- This is the highest-value feature gap in the "other" bucket. Halbert holds all of its own memory locally with no cloud sync and never backs up its own state. `discovery/scanners/backup.py` (946 lines) only discovers third-party backup tools. The single tar producer in the tree (`persona/memory_purge.py:294-297`) is a bare `tarfile.open(...,'w:gz'); tar.add(source_dir)` with no volatile filter, no vanished-file tolerance, and no symlink policy — it follows and archives any symlink planted under a persona memory dir.
- The SQLite snapshot is a prerequisite for the tar archiver: a live `.sqlite` plus `-wal`/`-shm` cannot be tar'd consistently. `sqlite3.Connection.backup()` is the online backup API that takes no lock of the writer. This is the correct mechanism.
- Overlap with merged remediation: none. R-04 (conversation store hardening) touched the store's corruption predicates, not its backup. R-03 (scheduler durability) added receipt retention (A06-G5) which the section file says is related ("so the archive is not bloated by unbounded receipts") — the backup should snapshot after retention prunes.
- No standing rule violated. The backup is create-only (restore is deferred). Old data is left on disk, unread, never deleted. The volatile filter reuses the Tier-2 secret paths for the exclude list (FD-1).
- FD-1 (secrets at rest in the archive) and FD-2 (create-only scope) are real decisions. The recommended defaults (exclude secrets by a declared deny list, defer encryption, create-only with restore deferred) are sound.
- Effort justified. M for the tar archiver + SQLite snapshot. A founder would notice: a machine that holds all its own memory locally with no backup is one disk failure away from total memory loss.
- Minimum viable version: the SQLite snapshot + the tar archiver with volatile filter and symlink containment + the CLI verb. The dashboard button is later.

**Opportunities:** The SQLite snapshot mechanism is shared with DIAG-02's read-only opener and T5's doctor checks. The `backup/sqlite_snapshot.py` and `agents/conversation_sqlite.py:open_read_only()` both need a "discover every owned SQLite store" list — build that list once.

---

### Packet: OTHER-P2 — Redacting, correlated logging

**What it actually proposes:** A `RedactingFilter(logging.Filter)` on the root handler in `dashboard/__main__.py` (and the CLI root in `Halbert/main.py`) whose `filter()` rewrites `record.msg`/`record.args` after formatting via `security/result_redaction.redact_error_text` (registry pass first, then `ingestion.redaction.redact_text(prose=True)`), with `JsonFormatter.format()` getting the same pass as a second line of defence. A first-character pre-check before the redaction matcher (early return when the registry is empty; lazily build the set of first characters of every registered value). A process-wide correlation id via `LogRecordFactory` reading a `ContextVar` (`turn_id`, `thread_id`, `channel`) set by the agent route, stamping every record.

**Verdict: ACCEPT**

**Reasoning:**
- The redaction filter closes audit gap A03-G9: "the MCP dispatcher logs the raw exception before returning the redacted error." This is a confirmed leak. `obs/logging.py` has no redaction; zero `logging.Filter`/`addFilter` hits. Every log record is synchronous stderr with no redaction.
- Overlap with merged remediation: R-05 (redaction registry, Tier-2 choke point) merged the registry and the response-surface choke point. The logging filter is a new surface for R-05's registry, not a duplicate. The section file explicitly says "do NOT add a `get_subsystem_logger(name)` factory" — every module already calls `logging.getLogger(__name__)` directly. The filter goes on the root handler, not per-logger. This is the correct architecture.
- The first-character pre-check (OC08-C9) is a sub-bullet of C8, not a standalone packet. It keeps unconditional per-record redaction cheap on the hot path. The section file notes that `redact_text` is already line-oriented and bounded, so the cliff is smaller than in OpenClaw, but the pre-check is still S effort and prevents a regression as the registry grows.
- The correlation id (HM13-C10) is narrowed by the verifier: the QueueListener half is dropped (Halbert has no file handlers, stderr only). Only the factory is needed — a `ContextVar` stamped on every record. S effort. Rides in the C8 packet because both touch the same 30-line hub.
- No standing rule violated. Redaction is deterministic, registry-based, never a model. The correlation id is a `ContextVar`, not a model-derived value.
- FD-7 (is a redaction pass on every log record acceptable as an unconditional cost?) — the recommended default is yes. The pass is deterministic, bounded, and the alternative is the A03-G9 leak class recurring at every new call site.
- Effort: M for the filter + pre-check + factory. All three touch `obs/logging.py` (30 lines) and the root handler in `dashboard/__main__.py`.

**Opportunities:** This packet and LOG-01 (OC08-M2) touch the exact same files: `obs/logging.py`, `dashboard/__main__.py`'s root handler, and `JsonFormatter`. LOG-01 installs the `JsonFormatter` on a `RotatingFileHandler`; OTHER-P2 installs the `RedactingFilter` on the root handler and the `LogRecordFactory`. They should be ONE packet. Building them separately means two branches touching the same 30-line hub and the same root handler, with merge conflicts. Build once: install `JsonFormatter` + `RotatingFileHandler` + `RedactingFilter` + `LogRecordFactory` in one commit sequence.

---

### Packet: OTHER-P3 — Measured, not assumed

**What it actually proposes:** A `system/vitals.py: sample_vitals() -> Vitals` that clamps every numeric to finite and its natural bound, returns `load_average: Optional[tuple]` = None when `os.getloadavg` is missing or all-zero, and an `unavailable: list[str]` naming omitted sensors. `extra_adapters._get_live_telemetry` and `routes/system.py` both read it and render "Load average: unavailable on this platform" rather than a number. A session-start hook in `conftest.py` that computes the foreign-module set (modules whose `__file__` is in `hermes-agent` but not under the test tree and not in `site-packages`) and fails the session. A `scripts/assert_tree.py` for ad-hoc runs. A `sys.path` hardening in `Halbert/main.py` (strip `''`/`'.'` entries, remove any entry whose abspath equals the root, `insert(0, root)`).

**Verdict: ACCEPT**

**Reasoning:**
- The vitals clamping (OC08-C16) is a direct application of the standing directive "grounded in measured data." `context/extra_adapters.py:328` formats `load_avg = ... else 0.0` into the prompt as `- Load average: 0.00` when `os.getloadavg` is missing. The machine is claiming a measurement it did not take. This is the STATE-1 acceptance clause "macOS says when a sensor is unavailable." S effort. ACCEPT.
- The foreign-module assertion (HM19-C11) is exactly Halbert's most expensive recorded footgun: memory `halbert-worktree-venv-gotchas` records that the venv's editable install silently resolves `halbert_core` to the MAIN tree from a worktree. The current mitigation is a hand-rolled meta-path-stripping wrapper (`wt_pytest.py`). A session-start hook that computes the foreign set and fails the session replaces the wrapper for pytest runs. S effort. ACCEPT.
- The `sys.path` hardening (HM13-C17) is three lines in `Halbert/main.py`. Low priority but S effort and prevents a same-named module in the launch directory from shadowing the first-party package. ACCEPT.
- Overlap with merged remediation: none. R-03 (scheduler durability) is unrelated. No duplicate.
- No standing rule violated. The vitals are measured, not assumed. The foreign-module assertion is a test-only mechanism.
- Effort: S for all three items. The optional navigability bench (part 2 of HM19-C11) is M and tied to the next large decomposition — DEFER the bench.
- Minimum viable version: vitals clamping + foreign-module assertion + sys.path hardening. All S, all independent, all ship now.

---

### Packet: OTHER-P4 — One bounded-execution helper, typed error outcomes

**What it actually proposes:** A `utils/deadline.py` with `clamp_timeout`, `run_bounded_sync`, `run_bounded_async`, and `kill_process_tree`. Migrates `executor._call_with_timeout` to it. On timeout, records `status='timeout'` on the run receipt (not `'error'`) and marks the worker abandoned so the retry decorator does not start a second copy. Deletes `retry_with_timeout` (zero callers, process-global SIGALRM, main-thread-only). A `ClassifiedError(Exception)` carrying `error_type`, and `_walk_causes(exc)` that walks `__cause__` then `__context__` with a seen-set. `classify_error` first returns a `ClassifiedError.error_type` found anywhere in the chain, then applies the substring ladder to every exception in the chain. A fatal/transient/config-error taxonomy for the top-level exception handler (design note only; lands when the handler exists).

**Verdict: ACCEPT**

**Reasoning:**
- The A06 timeout own-bug is confirmed: after a wall-clock timeout, the task thread keeps running with live side effects while the receipt says `error` and the retry decorator starts a second copy. `scheduler/executor.py:62-86 _call_with_timeout` is a thread-join bound that leaves the worker running. This is a real concurrency bug.
- The section file carries a critical correction: `retry_with_timeout` has ZERO callers. This is "delete dead unsafe code, keep one bounded-execution helper," not a live concurrency race. The `utils/retry.py:315-324` SIGALRM path is process-global and main-thread-only — unsafe if it ever were called.
- The typed error classification (OC14-C12) is a real defect: `agents/error_recovery.py:110-135 classify_error` substring-matches `str(error)` and `type(error).__name__` and never walks `__cause__`. There are 29 `raise ... from e` sites across the core, so a wrapped `TimeoutError` or `ConnectionError` falls to `ErrorType.UNKNOWN` and gets the wrong backoff. S effort, bounded to `execute_with_retry`. ACCEPT.
- The fatal/transient/config-error taxonomy (OC02-C12) is a design note — the top-level handler does not exist. The section file says "not dispatchable alone." DEFER until the handler exists, but carry the `EX_CONFIG=78` convention.
- Overlap with merged remediation: R-03 (scheduler durability) touched `scheduler/executor.py` and the receipt protocol. The timeout-status fix (`status='timeout'` not `'error'`) may be residual from R-03 — R-03's Phase B added "receipts for rejected/skipped runs" but the timeout-leave-worker-running bug is A06's own bug, listed in the section file's audit gaps. If R-03 closed it, the deadline helper is still valuable for the async flavour and the `clamp_timeout` normalisation. R-07 (execute_code hardening) is a consumer of `utils/deadline.py` once it exists (A04-G1: no deadline when the worker survives KeyboardInterrupt injection).
- No standing rule violated. The deadline is deterministic. The error classification is deterministic. No model involved.
- Effort: M for the deadline helper + migration. S for the error classification. The design note is free.
- Minimum viable version: `utils/deadline.py` + migrate `executor._call_with_timeout` + delete `retry_with_timeout` + the `ClassifiedError` classification. The taxonomy design note is recorded for when the handler exists.

**Opportunities:** `utils/deadline.py` is a primitive consumed by A04-G1 (execute_code monitor loop deadline), A02-G7 (eval judge timeout), and any future async model-call bound. Build it once, document the consumers.

---

### Packet: OTHER-P5 — Atomic durable files and a minted identity

**What it actually proposes:** An `identity/install_id.py: read_or_create_install_id(state_dir) -> Optional[str]` with `mkstemp` + `fsync` + `os.replace` + `_fsync_directory`, fcntl lock file, thread lock, 32-hex uuid4. `peer_discovery.py` uses it for `node_id` instead of `HALBERT_PERSONA_ID + '-' + socket.gethostname()`. A `utils/bounded_download.py: download(url, dest, max_bytes, max_decompressed=None) -> Path` with streamed cap via `iter_content`, `.partial` + `os.replace`, per-dest single-flight lock, stale-serves on refresh failure. An async `read_bounded(resp, max_bytes)` for aiohttp. Adopt in `homebrew.py` first, then `web_search.py`'s two fetches.

**Verdict: RESHAPE**

**Reasoning:**
- The install identity (HM14-C20) is a real problem: `federation/peer_discovery.py:295` builds `node_id` from `HALBERT_PERSONA_ID + '-' + socket.gethostname()` and broadcasts it in the mDNS TXT record. The standing directive says "never the raw hostname." The current value broadcasts the raw hostname on the LAN. The atomic minting recipe is S effort and removes a raw-hostname broadcast. ACCEPT.
- The bounded download (OC21-C6) is a real gap: 66 outbound `requests.get`/`urlopen` sites with no byte cap and no staged rename. `tools/web_search.py:100-103, 187-190` fetch third-party search endpoints with only an aiohttp total timeout and no response size bound. A malicious or buggy endpoint could allocate unbounded memory. ACCEPT.
- FD-4 (may the mDNS `node_id` switch, accepting that already-paired peers must re-pair?) is a real decision. The recommended default (yes; no users, old ids left unread) aligns with the "no migrations" directive.
- Overlap with merged remediation: none. R-03 (scheduler durability) added directory fsync to the restart ledger, but the general recipe is not shared. The A06 ledger fsync own-bug and A12-G8 (guest_homes.yml renamed without fsync) are the same recipe — the section file says "same packet."
- No standing rule violated. The install id is opaque, never the raw hostname. The bounded download is deterministic.
- Effort: S for the install identity. M for the bounded download. The fsync fixes are S and ride in the same packet.
- The two items share the "tmp + fsync + os.replace + directory-fsync" recipe but are otherwise unrelated. They are packeted together for the shared recipe, not for shared logic.

**If RESHAPE:** ACCEPT both items. The install identity is S and should ship now (it removes a raw-hostname broadcast, which is a standing-directive violation). The bounded download is M and should ship next (it closes a real DoS surface). The fsync fixes (A06 ledger, A12-G8) ride along. Coordinate with OTHER-P4 on `executor.py` since both touch the restart-ledger fsync.

---

### Packet: OTHER-P6 — Settings reload plan and dashboard storage hygiene

**What it actually proposes:** A `dashboard/settings_reload_plan.py: plan_reload(changed_paths) -> ReloadPlan(restart_required, hot_actions, reasons)` over a declarative table (`personality.*` → hot reload; `models.slots.*` → hot rebuild router; `dashboard.bind`/`dashboard.token`/`mcp.servers.*` → restart; `web_search.enabled` → hot toggle). A projected-view diff: compute the resolved model per slot before and after the save, so an effective owner change with no authored key change is detected. A `safeStorage.ts` guarded localStorage accessor migrating 11 unguarded sites (the most critical: `DebugContext.tsx:37` inside a `useState` initializer of a provider that wraps the app — a throwing `localStorage` takes the whole dashboard down at mount). A single-flight + negative-TTL cache for repeated subprocess probes in `development.py` (opportunistic, only if the file is open anyway).

**Verdict: RESHAPE**

**Reasoning:**
- The settings reload plan (OC16-C3) is a real gap: only the personality block hot-reloads (`dashboard/routes/settings.py:3201-3209`); everything else requires a restart or silently hot-patches. The founder runs concurrent sessions editing settings — a blanket restart on every save is disruptive. The declarative table is the minimal correct recovery. ACCEPT.
- The projected-view diff is the clever half: compute the resolved model per slot before and after the save. This catches an effective owner change (e.g., a slot's model tag changes because a different slot was promoted) with no authored key change. This is valuable but M effort and can follow the basic table.
- The guarded localStorage accessor (OC23-C23) is S effort and fixes a real crash: `DebugContext.tsx:37` is inside a `useState` initializer of a provider that wraps the app. A throwing `localStorage` (Tauri webview with storage disabled, private mode) takes the whole dashboard down at mount. ACCEPT — this is a one-file fix that prevents a total dashboard crash.
- The subprocess probe cache (HM18-C14) is low priority and opportunistic. DEFER unless `development.py` is touched for another reason.
- Overlap with merged remediation: none. R-13 (utility slot) touched `model/*` but not the settings reload path. No duplicate.
- No standing rule violated. The reload table names slots, never models (standing directive). The localStorage accessor is frontend-only.
- Effort: S for the localStorage accessor. M for the reload plan. S for the probe cache (opportunistic).
- The section file correctly notes that `routes/settings.py` is 3,200+ lines and heavily edited by concurrent sessions — rebase often.

**If RESHAPE:** ACCEPT the guarded localStorage accessor (S, ship now — prevents a dashboard crash). ACCEPT the basic reload table (S-M, ship next — the personality-only hot-reload is insufficient). DEFER the projected-view diff and the subprocess probe cache.

---

## F01–F20 Follow-up Units

### F01-macos-host-integration
**Verdict: READ-NOW**
**Reasoning:** Halbert is a macOS-resident daemon with a Tauri shell, an OS-grant permission module, screen capture, audio in, and open APPLE-1/DIST-1/SHELL-1 rows. This is the only origin tree that solves "being a macOS app that owns its host" — LaunchAgent lifecycle, TCC/Apple-Events consent, port ownership, bounded child processes, sleep/wake. OC22 read seven Swift files and every macOS-derived candidate was kept. 332 files are untouched. The density is proven. This is the highest-priority follow-up unit.

### F02-agents-tool-admission
**Verdict: READ-NOW**
**Reasoning:** This is the origin's answer to "one policy pipeline across MCP and internal tools" — the founder constraint Halbert is building toward under GATE-1/TRUST-1. Two units read 52 files and produced 26 kept candidates — one every two files. The remaining 97% is the densest unread mass in the corpus. Directly relevant to BIND-01's file-binding work and R-08's permission lattice.

### F03-mcp-server-side
**Verdict: READ-NOW**
**Reasoning:** MCP-1 and the founder-ruled B6 audit of Halbert's existing 18-tool `mcp/server.py`. HM09 covered the client and found that Halbert leaks its whole environment to stdio children. Nobody looked at what a hardened MCP server refuses to do. R-09 (MCP client boundary) merged the client side; the server side is unread. Small unit, direct hit on an open founder decision.

### F04-skill-workshop-governance
**Verdict: READ-NOW**
**Reasoning:** SKILL-1 + KNOW-1. The lifted SK-series gave Halbert the skill format; this is the lifecycle — how a skill is proposed from observed history, reviewed, applied under a lock, hash-pinned, and rolled back. R-11 (skills plane) merged the skills format and cache boundary, not the governance lifecycle. For a steward that learns its own host without a human approving every step, this is the missing governance layer. 144 files, 0.7% read, unassigned.

### F05-origin-rationale-docs
**Verdict: READ-NOW**
**Reasoning:** Cheapest unit on the list (~30 files) and it repairs a systematic weakness. Several solidity-audit gaps were refuted and several discovery candidates dropped for want of the origin's stated reason for a mechanism. Docs are where the origin records the incidents that produced its hardening — the "why_solid" evidence the refuters kept asking for. Best value per file.

### F06-config-state-durability
**Verdict: READ-NOW**
**Reasoning:** CFG-1 and STATE-1. OC05 already turned 24 files into a confirmed live Halbert defect: `models.yml`'s read-modify-write is unlocked while `being.yml`'s is flock-guarded, and the founder runs concurrent sessions. This is a lost-update on the API-key store. BIND-01a addresses this specific bug, but the rest of the durability story (atomic replace, last-known-good, polluted-placeholder gating) is unread. 653 files, ~5% read.

### F07-gateway-auth-approval
**Verdict: READ-LATER**
**Reasoning:** One door / SURF-1 / MCP-1. The two units here produced 24 kept candidates from 76 files. Valuable for the dashboard's auth surface and the approval flow, but R-08 (permission lattice) and R-01 (talk-door ordering) already merged the core of this. The residual is the gateway-level auth and route-admission patterns, which are relevant but not urgent given the merged remediation.

### F08-cli-self-diagnosis-and-update
**Verdict: READ-LATER**
**Reasoning:** DIST-1 and CLI-1: a steward that claims to be the machine should diagnose and repair its own install. Halbert's update path is unbuilt. Relevant to DIAG-01's doctor command and the DIST-1 packaging track, but not blocking. Read after DIAG-01 lands so the doctor can incorporate the self-diagnosis patterns.

### F09-first-run-and-onboarding
**Verdict: READ-LATER**
**Reasoning:** BIRTH-1: onboarding, naming, the first-run capability probe. Relevant to SURFACE-01's wizard back-navigation and the onboarding redesign, but BIRTH-1 is a ROADMAP row that has not opened. Read when BIRTH-1 opens.

### F10-plugin-capability-contract
**Verdict: READ-LATER**
**Reasoning:** What an extension is allowed to do, expressed as a contract. Relevant to FENCE-1 if Halbert ever admits third-party code. Halbert's "plugins" are SKILL.md text today, so this is not urgent. Read if a Python extension surface is decided.

### F11-control-ui-patterns
**Verdict: READ-LATER**
**Reasoning:** SURF-1: the dashboard is Halbert's only human surface and this is the least-read UI in the pass (2.1%). The constraint filter is important: take the state/streaming/deep-link patterns, not the visual language (Halbert has its own tokens and no-emoji rule). Relevant to SURFACE-01 but not blocking — the dashboard patterns can be absorbed incrementally.

### F12-hermes-plugin-runtime
**Verdict: SKIP**
**Reasoning:** Complements F10 with the Python-side loader and storage isolation. Halbert has no third-party Python extension ecosystem (its "plugins" are SKILL.md text). The section_other file explicitly says "Revisit only if a Python extension surface is decided." Not relevant to Halbert's architecture today.

### F13-reference-agent-loop
**Verdict: READ-LATER**
**Reasoning:** A decompiled reference implementation of the agent loop, terminal handling, and tool dispatch. Ground truth for TERM-1 and the turn machinery. Relevant to TERM-02 and the state-machine work, but R-01 (interrupt algebra) and R-06 (turn digest) already merged the core turn machinery. Read if the state-machine work needs a reference for the stop-gate seam (T3).

### F14-secrets-at-rest-and-broker
**Verdict: READ-LATER**
**Reasoning:** Tier-2 secrets, scrub-before-model, and the credential-as-reference pattern. R-05 (redaction registry) merged the registry and the Tier-2 choke point. The credential-as-reference pattern (a credential resolved at use time, not stored in config) is a genuine gap. Relevant to BIND-01's `allowed_hosts` egress binding (FD-4) but gated by a founder decision. Read when FD-4 is decided.

### F15-command-surface
**Verdict: SKIP**
**Reasoning:** Slash/command registry depth. CLI-1. OC03 already showed Halbert has one hardcoded `/model` parser against a data-driven registry. This is a CLI ergonomics improvement, not a safety or correctness issue. Low priority for a single-user product.

### F16-hermes-tools-remainder
**Verdict: SKIP**
**Reasoning:** `computer_use/`, the `browser_*` family tail, notes/memory tools. The browser family is explicitly not applicable (no browsing surface, `grep browser|playwright|puppeteer|cdp` over ROADMAP.md returns zero). `computer_use` is not on the ROADMAP spine. The notes/memory tools are covered by R-14 (memory promotion) and the memory workstream.

### F17-desktop-rpc-bridge
**Verdict: READ-LATER**
**Reasoning:** The RPC method surface between a desktop shell and an agent daemon — the pattern Halbert's `hostConversation` bridge is a small instance of. Relevant to TERM-02's terminal read tool (which round-trips over the existing WS) and the dashboard bridge, but not blocking. Read when the terminal read tool is built.

### F18-protocol-and-host-sdk-contracts
**Verdict: SKIP**
**Reasoning:** Typed wire contracts; useful mainly as a shape reference for Halbert's own event and memory boundaries. Halbert has its own event types (`agents/events.py`) and memory boundaries. The origin's contracts are TypeScript types for a different architecture. Low value for Halbert's Python backend.

### F19-cross-cutting-primitives
**Verdict: READ-LATER**
**Reasoning:** Small, and the place where a codebase keeps the invariants everything else assumes. `src/shared` (123, 4.1%) + `src/utils` (30, 0%) + `src/types` (4, 0%). Could contain reusable patterns for path containment (BIND-01), bounded execution (OTHER-P4), or redaction (R-05). Worth a skim for primitives, not a deep read.

### F20-deterministic-policy-extension
**Verdict: SKIP**
**Reasoning:** A policy engine shipped as an extension with doctor/auto-repair and state attestation. OC19's verifier already found Halbert's `consent/selfmod.py` ahead of it in places. R-08 (permission lattice) merged the lattice. The origin's policy extension is a TypeScript engine for a different architecture. Low value given the merged remediation.

---

## Cross-Cutting Opportunities

### 1. The logging hub: ONE packet, not two
LOG-01 (OC08-M2: `JsonFormatter` + `RotatingFileHandler` + redaction filter) and OTHER-P2 (OC08-C8: `RedactingFilter` + first-character pre-check + `LogRecordFactory`) touch the exact same files: `obs/logging.py` (30 lines), `dashboard/__main__.py`'s root handler, and `JsonFormatter`. Building them separately means two branches on the same 30-line hub with merge conflicts. Merge into one packet: install `JsonFormatter` on `RotatingFileHandler`, install `RedactingFilter` on the root handler, install the `LogRecordFactory`, wire the first-character pre-check. One commit sequence, one reviewer, one merge.

### 2. The doctor registry: build once, populate incrementally
DIAG-01's doctor registry is the natural sink for residual checks from every workstream:
- R-03's ticker markers → scheduler doctor check (HM16-C19)
- R-13's utility-slot locality result → configured-vs-observed drift check (OC08-C15)
- R-05's redaction coverage gaps → coverage registry (OC11-C11, from T5)
- R-09's MCP client boundary → SHA-256 artifact verification (OC21-C2, from T5)
- A08-G5's WAL-reset vulnerability → SQLite version check (from DIAG-02)
- A14-G4's `:cloud` sibling → drift check naming the locality result

Build the registry + `halbert doctor --json` + `GET /api/diagnostics` first. Every subsequent check is a new entry in the registry, not a new framework.

### 3. The read-only SQLite opener: shared by three packets
OC01-C15's `open_read_only(path)` helper (`mode=ro`, `PRAGMA query_only=ON`) is a prerequisite for:
- DIAG-01's readiness probes (HM11-C3)
- DIAG-02's store probes
- T5's SQLite bloat check (OC04-C4)
- OTHER-P1's backup snapshot (needs a "discover every owned SQLite store" list, which the opener's adoption path also needs)

Build the opener once in DIAG-02, reuse everywhere.

### 4. The bounded-execution primitive: shared by three consumers
OTHER-P4's `utils/deadline.py` is consumed by:
- A04-G1 (execute_code monitor loop deadline — R-07's domain)
- A02-G7 (eval judge timeout — R-15's domain)
- The A06 timeout own-bug (scheduler executor)

Build `utils/deadline.py` once, let each consumer adopt it in its own packet.

### 5. The hermetic environment + live-DB guard: shared inventory
T1's hermetic environment fixture and T1's live-DB guard both need to "inventory every import-time path constant." The conversation store's default path is the first (A08 own bug). The canon-store constants are already done (`conftest.py:9-47`). This inventory should be a shared checklist: every store that resolves a default path at import time must be re-pinned under the hermetic fixture. Build the checklist once, work through it.

### 6. The atomic-write recipe: shared by three packets
The "tmp + fsync + os.replace + directory-fsync" recipe is used by:
- OTHER-P5's install identity (HM14-C20)
- OTHER-P5's bounded download (OC21-C6)
- The A06 ledger fsync own-bug
- A12-G8 (guest_homes.yml renamed without fsync)

Halbert already uses `os.replace` for local state (`scheduler/run_receipts.py:121`, `consent/store.py:599`, etc.) but not for identity or network-fetched files. The recipe should be a shared `utils/durable_write.py` helper, not reimplemented per-packet. Note: OC02-C5 in the digest proposes exactly this (`utils/durable_write.py`), and it should be pulled into OTHER-P5.

### 7. The support bundle: ONE bundle, not two
LOG-01's OC08-C7 (redacted support bundle) and T5's OC09-C13 (redacted diagnostic support bundle) are the same mechanism: one zip under the data dir with redacted config, doctor JSON, log tail, health findings. Merge into one bundle, one redaction variant, one packet.

### 8. The withdraw-not-refuse rule: a general convention
TERM-02 adopts HM10-C17's withdraw-not-refuse rule for capability-gated tools: when the capability is absent, the tool is not in the list, rather than present and failing. This should be a shared convention for any capability-gated tool, not terminal-specific. Document it once in the tool-registration path.

---

## Summary of Verdicts

### Workstream 1: dashboard-app-onboarding-diagnostics (8 packets)
| Packet | Verdict |
|---|---|
| DIAG-01 | ACCEPT |
| DIAG-02 | ACCEPT (defer divert/spool path) |
| DAEMON-01 | RESHAPE (split: lock+exit codes now, stuck-turn watchdog later) |
| LOG-01 | ACCEPT (merge with OTHER-P2) |
| BIND-01 | RESHAPE (split: config CAS now, file-binding after R-08/R-07) |
| SURFACE-01 | RESHAPE (accept bug fixes + S-effort items, defer compositor/wizard/blueprint) |
| TERM-02 | ACCEPT |
| DIST-02 | DEFER (gate: DIST-1 signing identity) |

### Workstream 2: testing-evals-qa-ops (6 packets)
| Packet | Verdict |
|---|---|
| T1 | ACCEPT |
| T2 | ACCEPT |
| T3 | RESHAPE (accept ledger + eval metric + convention, defer stop-gate seam) |
| T4 | ACCEPT |
| T5 | RESHAPE (accept unification + artifact check + coverage, merge bundle with LOG-01) |
| T6 | RESHAPE (accept CSP test + npm allowlist + tracking job, defer entitlements + async rule) |

### Workstream 3: other (6 packets)
| Packet | Verdict |
|---|---|
| OTHER-P1 | ACCEPT |
| OTHER-P2 | ACCEPT (merge with LOG-01) |
| OTHER-P3 | ACCEPT |
| OTHER-P4 | ACCEPT |
| OTHER-P5 | RESHAPE (accept both items, ship install identity first) |
| OTHER-P6 | RESHAPE (accept localStorage guard + basic reload table, defer projected-view diff) |

### F01–F20 Follow-up Units
| Unit | Verdict |
|---|---|
| F01 | READ-NOW |
| F02 | READ-NOW |
| F03 | READ-NOW |
| F04 | READ-NOW |
| F05 | READ-NOW |
| F06 | READ-NOW |
| F07 | READ-LATER |
| F08 | READ-LATER |
| F09 | READ-LATER |
| F10 | READ-LATER |
| F11 | READ-LATER |
| F12 | SKIP |
| F13 | READ-LATER |
| F14 | READ-LATER |
| F15 | SKIP |
| F16 | SKIP |
| F17 | READ-LATER |
| F18 | SKIP |
| F19 | READ-LATER |
| F20 | SKIP |

### Counts
- **ACCEPT:** 8 (DIAG-01, DIAG-02, LOG-01, TERM-02, T1, T2, T4, OTHER-P1, OTHER-P2, OTHER-P3, OTHER-P4 — noting several ACCEPTs carry deferral notes for sub-items)
- **RESHAPE:** 8 (DAEMON-01, BIND-01, SURFACE-01, T3, T5, T6, OTHER-P5, OTHER-P6)
- **REJECT:** 0
- **DEFER:** 1 (DIST-02)
- **READ-NOW:** 6 (F01–F06)
- **READ-LATER:** 8 (F07–F11, F13, F14, F17, F19)
- **SKIP:** 5 (F12, F15, F16, F18, F20)

### Standout Opportunities
1. **Merge LOG-01 + OTHER-P2 into one logging packet** — same 30-line hub, same root handler, one merge.
2. **The doctor registry is the universal sink** — build once, populate from every workstream's residuals.
3. **The atomic-write recipe (`utils/durable_write.py`)** — shared by install identity, bounded download, ledger fsync, and guest_homes rename. Build once.
4. **The hermetic environment + live-DB guard** — the highest-leverage testing investment; makes the suite structurally unable to touch the live host.
5. **The read-only SQLite opener** — prerequisite for three packets; build once in DIAG-02.
6. **The support bundle** — LOG-01 and T5 propose the same mechanism; merge into one.
