# Deep Critical Evaluation — Group 2: Scheduler, Terminal-Tools, Voice-Media-Vision

Written 2026-09-11. A judgment exercise, not a ranking. Every packet is evaluated against the merged remediation (R-01 through R-15), the standing rules in AGENTS.md, and whether the proposed work serves a real Halbert need today.

---

## SCHEDULER-HEARTBEAT-DAEMON-WATCHDOG (SCHED-P1 through SCHED-P6)

### Packet: SCHED-P1 — Receipt truth and job-record authority

**What it actually proposes:** Makes the durable job record the authority at fire time (re-read before firing, refuse cancelled/paused), routes the dashboard cancel button through the live executor, adds PID+start_time owner identity to run receipts, adds a per-job fire fence (flock), terminalizes every abandonment path, adds owner-only file permissions, and detaches teardown to a done-callback so a timed-out worker cannot overwrite a terminal receipt.

**Verdict: RESHAPE**

**Reasoning:**
- R-03 (scheduler durability, complete pending-merge) already landed the large majority of this packet's audit items: occurrence-level idempotency wiring (A06-G1), boot recovery coordination (A06-G2), receipt retention (A06-G5), corrupt-receipts handling (A06-G9), boot recovery arming (A15-G3), schedule-edit guard (A15-G4), catch-up writes to parent record (A15-G1), failed-slot backoff (A15-G8), per-fire monitor gate (A06-G7), heartbeat BaseException (A15-G6), join in-flight sweep (A15-G7), retirement diagnostic (A15-G9), liveness markers (A06-G11/A15-G5), own-bugs 1/2/5/6/7, and the ~/.ssh digest-only fix. R-03 Phase B explicitly did "receipts for rejected/skipped runs" — that IS OC18-M7 (abandonment path terminalization).
- The residual that R-03 did NOT address is real and valuable: (1) HM16-M1 — the fire-path re-read and routing cancel through the live executor is a live defect (the dashboard cancel button writes state='cancelled' to a JSON file and never touches APScheduler; the job keeps firing). (2) PID+start_time identity (OC06-C13) — R-03 explicitly left this out, and the boot-namespace argument is correct: recover_on_boot compares a previous boot's pid against a freshly reassigned namespace. (3) HM16-M8 — owner-only permissions (0700/0600) on the scheduler data dir. (4) OC14-C18 — detach teardown so a timed-out worker cannot overwrite a terminal receipt. (5) HM16-M5 — the per-job fire fence.
- The per-job fire fence (HM16-M5) is the weakest residual. The section itself says "single-user single-host — the cross-process half exists only because the route and the executor already are separate instances; do not build a lock server." The right fix is one shared engine on app.state (which R-03 may have partially addressed with the single-instance flock), not a per-job flock.
- No standing-rule violation.
- The cancel-through-live-executor fix is the highest-value residual — an operator would notice that cancelling a job does nothing.

**If RESHAPE: what should it become?**
A small packet with three items: (1) route cancel through the live executor + add is_runnable re-read at the top of wrapped() [HM16-M1, effort S], (2) PID+start_time identity field on receipts [OC06-C13, effort S, gated by founder decision 1], (3) owner-only permissions on the scheduler dir [HM16-M8, effort S]. Drop OC18-M7 (done by R-03), drop HM16-M5's flock (replace with shared engine on app.state if not already done), fold OC14-C18 into SCHED-P2's inactivity watchdog (it only matters when a timeout fires).

---

### Packet: SCHED-P2 — Honest timeouts

**What it actually proposes:** Replaces the flat wall-clock timeout with an inactivity-based watchdog (stamps a monotonic activity clock, interrupts only on genuine idleness), adds phase-aware budgets (queued/model_resolution/context_assembled/executing with separate deadlines), adds an idle-stall watchdog for the streaming LLM client (sock_read timeout instead of total timeout), kills timed-out subprocesses as a process group, and adds a DaemonThreadPoolExecutor that propagates contextvars.

**Verdict: ACCEPT (with one reshape)**

**Reasoning:**
- R-03 did not touch any timeout mechanism. The section explicitly says HM16-C16 is "packet 03 addendum item 7, packeted and unimplemented." This is entirely new work.
- The inactivity watchdog (HM16-C16) fixes a live behavioural defect: after a timeout the thread keeps running with side effects while the receipt says error and the retry decorator starts a second run (A06 own-bug 3). This is real and an operator would notice it.
- The streaming idle-stall (OC18-M2) fixes a real defect: a healthy long local generation is aborted at 120s wall clock, and a mid-generation stall goes unnoticed until the same 120s. The morning report calls this client. This is the kind of thing that makes the machine look broken.
- The process-group kill (HM16-M4) is the same mechanism as TT-01's process-group kill — build once.
- The phase-aware watchdog (OC18-M1) is valuable but lower priority — it improves diagnostics ("blocked on Ollama model load" vs "ran long") but is not a correctness fix.
- The DaemonThreadPoolExecutor (HM07-C19) is low priority — the contextvar half matters (persona/permission scope resets on a pool worker) but the section itself says "Low."
- HM06-C15 (exclude human-wait time) is explicitly "nothing to build now" — bank the rule.
- No standing-rule violation. Local models are pinned; the streaming fix must not change endpoint selection.

**If RESHAPE: what should it become?**
Ship in two phases: Phase 1 = inactivity watchdog (HM16-C16) + streaming idle-stall (OC18-M2) + process-group kill (HM16-M4, shared with TT-01). Phase 2 = phase-aware budgets (OC18-M1) + DaemonThreadPoolExecutor (HM07-C19). The hand-teardown (HM16-C10) folds into Phase 1's watchdog.

---

### Packet: SCHED-P3 — Failure containment, admission and the kill switch

**What it actually proposes:** Per-job auto-disable after a consecutive-failure streak (10 runs / 3 schedule errors), model-endpoint preflight before admission, fail-before-spend config preflight, failure-incident dedup by error signature, a filesystem ESTOP sentinel, standing-order documents replacing the model-produced requires_approval, ticker liveness markers, and golden-text eval for status copy.

**Verdict: RESHAPE**

**Reasoning:**
- R-03 already delivered the liveness markers (HM16-M3 = A06-G11/A15-G5) in Phase F. That item is DONE — drop it.
- R-03 already addressed A06-G4 (clock rollback) but that is a different mechanism from the auto-disable streak.
- The per-job auto-disable (OC18-C11 + HM16-C14) fixes a real live defect: one broken job trips the GLOBAL anomaly streak and safe-modes every job. The section spot-checked this: anomaly_detector.py keeps a global failure_streak, guardrails.py writes the safe-mode flag, and executor.py then skips every job. One broken job halts the entire scheduler. An operator would absolutely notice this.
- The ESTOP (HM01-C1) has two live bugs the verifier found: the flag resolves against process CWD (so a pause from one directory is invisible to a process started from another), and is_safe_mode_active syncs file→memory only in the True direction (a flag removed out of band never lifts). These are real defects. But the ESTOP also proposes checking at state_machine.py turn admission and tools/executor.py dispatch — that's new surface area.
- The standing-order documents (OC24-C19) fix a standing-rule violation: autonomous_tasks.py:84-110 asks a model for requires_approval with a confidence_threshold dial — a model judging its own approval gate, against the directive that no LLM makes a permission decision. This is a rule violation that should be fixed regardless.
- The preflight (OC18-M3 + HM16-C11) is valuable: a laptop that suspended overnight wakes, fails sweeps against an unstarted Ollama, and safe-modes the scheduler. But it depends on P1's receipts being trustworthy first.
- The failure-incident dedup (HM16-C8) is medium value — it's a nicer findings store, not a correctness fix.
- The golden-text eval (HM19-C13) is low — Halbert already has a stronger copy-manifest discipline for consent copy.
- HM16-M9 (agent-facing scheduling tool denied model fields) is effort 0 — record in DECISIONS.md, build nothing.

**If RESHAPE: what should it become?**
Three items in priority order: (1) Per-job auto-disable (OC18-C11) — the one-broken-job-halts-all defect is the highest value. Make the anomaly detector's streak per-job. (2) Standing-order documents (OC24-C19) — fixes the model-judging-approval-gate rule violation. (3) ESTOP fixes (HM01-C1) — fix the CWD and one-way-sync bugs, add turn-admission and dispatch checks. Preflight (OC18-M3/HM16-C11) defers until P1's cancel fix lands. Drop HM16-M3 (done), HM19-C13 (low), HM16-M9 (effort 0, doc only).

---

### Packet: SCHED-P4 — Turn liveness and local-model priority

**What it actually proposes:** A turn-liveness watchdog that force-aborts a turn that stalls silently while holding the one conversation's lock, a tool-execution activity heartbeat so a long tool call never trips the watchdog, idle-deferred background inference that does not take the local model slot the next live turn needs, and thread-scoped stdout/stderr silencing.

**Verdict: ACCEPT**

**Reasoning:**
- R-01 (interrupt algebra) merged, and the section says "Prerequisites: none (the interrupt algebra and turn_activity.py are merged)." So the prerequisite is met.
- The turn-liveness watchdog (HM01-C2) fixes a real defect: state_machine.py:223-232 TURN_LOCK_TIMEOUT_S bounds only a QUEUED waiter; a wedged holder is never released. A model that hangs forever pins the one conversation's lock and no subsequent turn can start. An operator would notice this as "Halbert stopped responding."
- The section found that agents/turn_activity.py already has the lock + monotonic generation + single-shot claim() — so the primitive exists. The task is to stamp the activity clock at handler entry, each tool start/complete, each stream chunk, and add a sampler that compares idle against a ceiling. This is less work than it sounds.
- The tool-execution heartbeat (HM01-C3) is a strict dependent of C2 — ship together.
- The idle-deferred background inference (HM04-C12) fixes a real priority inversion: model/client.py's llm_advisory_lock is plain mutual exclusion with no priority, so a background job that takes the lock first delays the live turn. This is the kind of subtle bug that makes the machine feel sluggish.
- The thread-scoped stdout/stderr (HM02-C16) fixes a live bug: execute_code.py:447 assigns the PROCESS-GLOBAL sys.stdout from a worker thread, so every other thread's prints land in the script's capture buffer. R-07 (execute_code hardening) may have addressed this — the section says "process-wide sys.* mutation serialization" is in R-07's scope. If R-07 fixed it, drop it; if not, it's a real defect.
- No standing-rule violation. The abort goes through the lifted request_stop, so subprocesses are not killed silently.
- Founder decision 4 (ceiling default, 30 minutes) is a small gate.

**Opportunities:** The activity-clock primitive is shared with TT-06's subagent staleness monitor (HM05-M1) and SCHED-P2's inactivity watchdog (HM16-C16). Build one `stamp_activity()` / `check_idle()` pair in turn_activity.py and reuse across all three.

---

### Packet: SCHED-P5 — Process lifecycle (the deferred daemon packet)

**What it actually proposes:** A bounded shutdown sequence (every await stop() under a timeout, with a closed|uncertain outcome), an unclean-exit sentinel with a state-db integrity check on suspicious boot, a periodic RSS log line, a port guardian that reaps orphaned prior backends, a thaw-reconnect triggered from the heartbeat tick gap, a sleep/wake suspension lease, event-loop health hysteresis, and tri-state readiness. The gated tail adds an event-loop liveness watchdog, a startup-deadlock watchdog, a restart-loop breaker, and launchd registration.

**Verdict: RESHAPE (accept the core, defer the tail)**

**Reasoning:**
- R-03 did not address any process lifecycle items. This is entirely new.
- The bounded shutdown (OC16-C7) fixes a real defect: dashboard/app.py:1623-1724 has ten unbounded awaits; one hung websocket close forces SIGKILL. An operator would notice this as a hung shutdown.
- The unclean-exit sentinel (HM11-C2) is valuable: app.py:141-172 heals turn rows on EVERY boot without classifying the previous death or inspecting the store. Running quick_check(1) only on suspicious boot is cheap and catches corruption early.
- The RSS log (HM11-C10) is "harmless" per the section — 40 lines, one log line per 300s. Low value but zero risk.
- The port guardian (OC22-C11) is low value — a crashed backend's orphan pushing the next boot to a new port is a nuisance, not a correctness issue.
- The thaw reconnect (OC16-C8) is medium value — after a laptop sleep, HA stream/Frigate MQTT/Wyoming each reconnect on their own sweep, but a coordinated thaw reconnect from the heartbeat tick gap is cleaner. The section notes this also closes A06-G3 (slots missed while asleep).
- The sleep/wake suspension lease (OC22-C4) is medium — it requires PyObjC in the sidecar and a generation fence. It's real work for a feature that only matters on a laptop that sleeps.
- The event-loop watchdog (HM11-C1), startup-deadlock watchdog (HM13-C9), and launchd registration are all gated by founder decision 2 and HM11-M2 (exit-code vocabulary + supervisor probe). The section itself says "Under no supervisor, a hard-exit watchdog converts a wedge into an outage." This is correct — do not build hard-exit paths until a supervisor exists.
- No standing-rule violation.

**If RESHAPE: what should it become?**
Core (founder-independent, ship now): bounded shutdown (OC16-C7) + unclean-exit sentinel (HM11-C2) + RSS log (HM11-C10) + thaw reconnect (OC16-C8). Defer: sleep/wake (OC22-C4, medium effort, laptop-only), port guardian (OC22-C11, low), event-loop health (OC17-C4, low), tri-state readiness (OC17-C5, low). Gated tail: event-loop watchdog, startup-deadlock, launchd — all wait on founder decision 2 and HM11-M2.

---

### Packet: SCHED-P6 — The scheduled-work surface

**What it actually proposes:** A deterministic NL schedule parser, timezone-correct cron handling, three job shapes (prompt/script-augmented/no_agent), a per-job durable notepad, a consent-first automation suggestion queue, a batch classifier script, a weekly host-state digest with read-back verification, a scheduler dashboard page (list/history/cancel), a run-receipt inspector, a detached background-task registry, notification-level idempotency keys, a three-way completion status, a delivery outbox, and webhook URL normalization.

**Verdict: DEFER (with two exceptions)**

**Reasoning:**
- Most of this packet builds infrastructure for user-created scheduled jobs that do not exist. The section itself says "a create endpoint on an engine that cannot cancel is not shippable" and gates creation behind founder decision 7. The NL schedule parser, timezone handling, job shapes, per-job notepad, suggestion queue, and batch classifier are all consumer-facing features for a consumer that does not exist.
- The detached task registry (OC09-C1) is the largest item (effort L) and builds a unified registry across runtimes (scheduled job, subagent, execute_code, terminal block) — but the section says "dispatch after Theme 1 so receipts are trustworthy input." This is real infrastructure but it's a big build for a dashboard "Workloads rail" that doesn't exist yet.
- TWO EXCEPTIONS that have standalone value:
  1. The scheduler dashboard page (OC23-C13, list/history/cancel half) — the section found that lib/tauri.ts:209-218 already exports getScheduledJobs()/cancelScheduledJob() against live endpoints and nothing in the frontend calls them. This is dead client code that lands with P1's cancel fix. Effort S-M, no founder decision needed.
  2. The weekly host-state digest improvements (HM20-C11) — morning_report.py already exists; the two additions (coverage-gaps section and read-back verification of approved writes) are deterministic and medium effort. An operator would notice the difference.
- The webhook normalizer (OC18-C14, ~20 lines) applies now to any outbound URL Halbert accepts from config. Effort S, standalone value.
- HM16-M9 (no inference-slot field on agent-facing scheduling tool) is effort 0 — record in DECISIONS.md.
- No standing-rule violation, but the suggestion queue must respect the proactive dial and be staged, never executed.

**If RESHAPE: what should it become?**
Ship the scheduler dashboard page (list/history/cancel) + webhook normalizer + weekly digest improvements now. Record HM16-M9 in DECISIONS.md. DEFER everything else behind founder decision 7 (user-created jobs) and the detached task registry behind a named dashboard consumer.

---

## TERMINAL-TOOLS-SUBAGENTS (TT-01 through TT-06)

### Packet: TT-01 — Shell executor hardening

**What it actually proposes:** Process-group ownership with a graded kill ladder on the shell-exec path, a PID+start_time identity fingerprint, cap-plus-spill for every tool result (redacted before the write, cut on a line boundary), fixing the redact-before-cap ordering defect in the agent pool, an ANSI-escape and Unicode-tag stripper for subprocess output, deterministic exit-code/signal interpretation with failure hints, atomic write in the agent-facing file-write tool with read-back verification, and (device,inode) binding across the approve-then-execute gap.

**Verdict: ACCEPT**

**Reasoning:**
- R-07 (execute_code hardening) already covered the execute_code-specific items: monitor loop deadline, dispatch hook disarm, unbounded spill for execute_code's stdout, redaction before context, stderr capture, process-wide sys.* mutation. The "execute_code phase" of TT-01 overlaps heavily with R-07 — but TT-01's scope is the shell-exec path (tools/executor.py _run_command) and the agent pool, which R-07 did not touch.
- R-05 (redaction registry, Tier-2 choke point) already established the redaction choke point. TT-01's cap-plus-spill must route through R-05's registry, not build a second one. The section says "redaction at the response choke point" — this is the right constraint.
- R-06 (echo guard, display projection) already covers display projection. The durable-row redaction in TT-01 (executor.py:806-822) should route through the same seam.
- What is NOT covered by merged remediation and is genuinely valuable:
  - Process-group kill: executor.py:832 spawns with no start_new_session and :908 is an immediate SIGKILL to /bin/sh only, so every shell timeout orphans grandchildren. Real defect.
  - PID+start_time fingerprint: parent_watchdog.py and run_receipts.py probe with bare os.kill(pid, 0). A reused pid keeps an orphaned backend alive. Real defect.
  - Redact-before-cap ordering: agent_pool.py:312-324 severs head/tail and only then redacts each fragment independently. A secret straddling the cut boundary leaks in halves. Real defect, confirmed by the verifier.
  - ANSI/Unicode tag stripper: the model never sees raw control sequences it could copy into a file write. The section notes this also closes A17-G5 (remote tool descriptions enter the prompt without tag stripping).
  - Exit-code interpretation: a non-zero exit counts as a success (A05-G4). The model spends a turn misdiagnosing "ModuleNotFoundError" as a missing package. This is the "never a model where a template suffices" rule.
  - Atomic write: write_config.py writes with plain open(path, "w") behind a .bak, writing through any hardlink/symlink. Real defect for a tool that edits launchd/systemd units.
- No standing-rule violation. The redaction goes through the deterministic registry.
- The effort is justified — these are the agent's primary interaction surface with the host.

**Opportunities:** The process-group kill helper is shared with SCHED-P2 (HM16-M4). The PID+start_time fingerprint is shared with SCHED-P1 (OC06-C13). The text-hygiene module is shared with TT-03 (normalization step one). Build each once.

---

### Packet: TT-02 — Child-process boundary fence

**What it actually proposes:** A minimal-allowlist environment for every stdio MCP server Halbert launches (PATH/HOME/locale plus declared names only), a positive denial marker that survives exec for agent-pool and guest shells, background offloads in an empty Context (so a thread offload does not inherit the caller's security ContextVars), and a trusted-executable path check on security-load-bearing binaries.

**Verdict: RESHAPE**

**Reasoning:**
- R-09 (MCP client boundary) already addressed A17-G1 (stdio MCP servers inherit the whole environment). The section says "This is audit A17-mcp-boundary-G1 (high) — one fix closes both." If R-09 fixed the MCP env leak, then the MCP half of TT-02's first item is DONE.
- What R-09 likely did NOT address: the PTY shell env leak. streaming/pty.py:289-293 does child_env = dict(os.environ) then execvpe for every PTY; session_manager.py:99 passes env=None for the agent's own pool shells. Every shell the machine runs for itself inherits HALBERT_API_TOKEN and ANTHROPIC_API_KEY. This is the same class of leak but on a different surface.
- The positive denial marker (HM05-M4) is valuable: a descendant is fenced by a value that is PRESENT (HALBERT_CHILD_CONTEXT=<kind>), never by a key that is missing. Absence alone promotes a descendant to an orchestrator. This is a real security principle.
- The background-offloads-in-empty-Context (HM05-M3) is a real defect: 20+ bare asyncio.to_thread sites inherit whatever current_turn_claim / current_speaker_role / current_turn_channel was bound. The cognitive-loop tick (home/cognitive_loop.py:289) runs autonomous work attributed to a user turn's identity. This violates "autonomous work is never attributed to a user turn."
- The trusted-executable check (OC12-C4) is medium: it defends against an attacker who can already write a PATH directory. The real targets are crypto/storage.py (security/secret-tool) and streaming/sandbox.py (bwrap/sandbox-exec). A hijacked sandbox binary silently defeats the sandbox. Real but requires an attacker already on PATH.
- No standing-rule violation. "Scope by capability boundary, not filesystem path" — the section explicitly states the cooperative-scoping caveat.

**If RESHAPE: what should it become?**
Drop the MCP env-allowlist if R-09 covered it. Ship: (1) PTY shell env fence + positive denial marker [HM05-M4, effort M], (2) background offloads in empty Context [HM05-M3, effort S], (3) trusted-executable check [OC12-C4, effort S-M]. The first two are the high-value items.

---

### Packet: TT-03 — Command classifier v2 and the confirmation gate

**What it actually proposes:** Normalize and de-obfuscate commands before any pattern match (strip ANSI/NUL, NFKC, collapse backslash-newline, fold $HOME, strip escapes, iterate command starts), fail closed when a command cannot be parsed, a founder-authored deny list that outranks every bypass, combined approval requests when independent detectors both fire, an unattended-origin approval policy (deny for scheduler/MCP, ask with a 10-minute bound for voice/dashboard, deny-on-timeout), and a self-repo worktree-mutation rule.

**Verdict: ACCEPT**

**Reasoning:**
- R-08 (permission lattice: ask axis, approvals, leases, halt) already addressed the approval infrastructure. But the unattended-origin policy (HM06-M2) is about what happens when no human is present — the section says executor.py:604-611 returns requires_confirmation unconditionally and _handle_awaiting_confirmation is a no-op with no timeout and no origin check. A HIGH-risk tool from the scheduler, an MCP-originated turn, or a voice turn with no dashboard open pins the session forever. This is a real defect that R-08's "ask axis" may or may not have fully addressed — the section says "A11-permission-lattice-G7 (the Attentive/Present line is data only, QUIET never computed)" is the same seam. If R-08 computed QUIET, this is done; if not, it's a residual.
- The normalizer (HM07-M4) is the highest-value item and has NO overlap with any merged remediation. The verifier confirmed live bypasses: rm -rf ~/Documents → HIGH/confirm, but r\m -rf ~/Documents, rm${IFS}-rf${IFS}~/Documents, and $(echo rm) -rf ~/Documents → MEDIUM, allowed, no confirmation. This is a real security defect on the agent's primary command surface.
- The fail-closed-on-unparseable (HM06-M1) is a real defect: _shell_segments returning None only suppresses the SAFE tier; CRITICAL/HIGH/MEDIUM rules still regex the raw string, so an unsegmentable command can land on MEDIUM and execute after a generic confirmation.
- The founder-authored deny list (HM06-M3) is the cleanest expression of the founder's posture — a config line the human wrote is a floor below every other decision.
- The self-repo worktree mutation rule (HM06-C2) is real: the founder runs concurrent sessions in this checkout, so an agent-initiated git reset --hard destroys another session's uncommitted work.
- No standing-rule violation. This is squarely the "one policy pipeline" directive. The normalizer is deterministic, no LLM.
- Founder decision gates: the per-origin approval defaults and the bounded-wait length, and the deny-list file location.

**Opportunities:** The text-hygiene module from TT-01 (ANSI/NUL strip) is step one of the normalizer. Build it once, use it in both packets. The combined-approval-request (HM06-M5) makes "one policy pipeline across MCP and internal tools" enforceable.

---

### Packet: TT-04 — Background registry, yield, wake, and the watched-terminal surface

**What it actually proposes:** A ProcessRegistry for terminal(background=true) with poll/log/wait/kill/write/submit, a yield-to-background primitive (a mid-turn user message hands off the live foreground process instead of killing it), a foreground-command guardrail (nudge nohup/&/dev-server commands toward tracked background mode), a watch-pattern notification throttle, crash-recovery checkpoint for background processes, a terminal "blocked" outcome detector, wake-into-conversation for background completions, a resettable idle deadline, PTY socket reattach, bounded wait on a watched session, a server-side status controller, progress labels, a restart-safe PTY lease, and parent-death grace.

**Verdict: RESHAPE (large — split into two dispatchable halves)**

**Reasoning:**
- R-01 (interrupt algebra) already addressed the kill vs steer distinction. The yield primitive (HM07-M1 = A07-G8) is part of the interrupt algebra — "three distinct bits: kill, steer, yield." If R-01 delivered the yield bit, then HM07-M1 is DONE. The section says "agents/steering.py:18 promises 'yield, never kill' in prose; grep for yield in steering.py/turn_activity.py returns only that docstring." If R-01 only delivered kill and steer but not yield, then the yield primitive is still needed.
- The PTY reattach (HM18-C18) is a live defect with real user impact: the server keeps the PTY alive for reattach but the client marks a live shell as 'done' on any close. Laptop sleep or a wifi flap shows a running shell as exited while the process keeps running. This is the founder-named surface ("user shells stay but are watched by the AI"). ROADMAP TERM-1.
- The ProcessRegistry (HM07-C3) is the largest item (effort L) and resolves the "terminals built for one turn only, agent gets NO history" gap. It's real infrastructure but it's a big build.
- The foreground-command guardrail (HM07-C8) has standalone value before the registry — today npm run dev burns the full DEFAULT_TIMEOUT.
- The status controller (OC18-C6) is medium effort — a server-side controller driving TaskCardData.state with debounce/stall timers. No Python producers of needs_attention exist today.
- The watch-pattern notification throttle (HM07-C4) has no consumer yet (no autonomous mid-process notification path exists).
- The crash-recovery checkpoint (HM07-C6) depends on the registry.
- The wake-into-conversation (HM11-C11) is founder-gated — the wake lane is behind the proactivity dial.
- No standing-rule violation. User shells stay watched, never adopted by the registry.

**If RESHAPE: what should it become?**
Split into two halves:
- Half A (ship now, no registry dependency): PTY reattach (HM18-C18) + foreground-command guardrail (HM07-C8) + progress labels (OC03-C12) + bounded wait on watched session (OC24-C10). These fix live defects on the existing watched-terminal surface.
- Half B (ship after the registry): ProcessRegistry (HM07-C3) + yield-to-background (HM07-M1, if not done by R-01) + notification throttle (HM07-C4) + crash-recovery checkpoint (HM07-C6) + status controller (OC18-C6) + wake-into-conversation (HM11-C11, founder-gated). This is the big build.

---

### Packet: TT-05 — Tool-loop guardrails and malformed-call recovery

**What it actually proposes:** Refuse (not coerce) unparseable tool arguments with a 3-strike repair budget, signature-hashed per-tool guardrails (failing-repeat vs no-progress vs identical-streak, with tolerant tools and progress resets), a per-run tool-call ceiling on the interactive path, detach-not-cancel (a late tool result cannot land in a newer generation's context), and persisting an UNKNOWN-effect marker when a turn dies after a side-effecting tool ran.

**Verdict: ACCEPT**

**Reasoning:**
- R-01 (interrupt algebra) may overlap with detach-not-cancel (OC14-C4) — both are about turn abort semantics. But detach-not-cancel is specifically about a late tool result landing in a newer generation's context, which is a different concern from the interrupt algebra's kill/steer/yield. If R-01 delivered the generation claim, this is the consumer.
- The malformed-call repair (HM01-C13) is the highest-value item and has no overlap with merged remediation. model/client.py:457-465 swallows the parse failure and dispatches the tool with {}. A local model emitting truncated JSON gets terminal {} / write_file {} run, burning one of five loops, and _already_called may then refuse the corrected retry as a duplicate. The verifier calls this "the most likely real-world failure in the set" — local models are Halbert's primary target.
- The signature-hashed guardrails (HM01-C5) fix a real defect: _already_called refuses any (name, args) already settled this turn, forcing REFLECTING. After a failing terminal <test>, an edit, and the same command again, Halbert refuses the retry and ends the turn. The PROGRESS_RESET_TOOL_NAMES concept (a successful mutating call clears failing signatures) is the fix.
- The per-run tool-call ceiling (OC14-C20) is a real gap: the interactive path bounds iterations only (max_loops=5) and loops over an unbounded tool_calls list per iteration. A model returning 40 calls in one message is unbounded.
- The UNKNOWN-effect marker (HM02-C9) is real: observations die with ctx, so the next turn is silent about a possibly-completed destructive action. The section notes this also closes A16-G5 (interrupted turn leaves a dangling question with no persisted fact).
- No standing-rule violation. The repair ladder is deterministic (close-name repair within edit distance 2), no model.

**Opportunities:** The activity-stamp primitive from SCHED-P4 (HM01-C2) and TT-06 (HM05-M1) is shared with the tool-execution heartbeat. The generation-claim primitive from R-01 is the substrate for detach-not-cancel.

---

### Packet: TT-06 — Subagent manager correctness

**What it actually proposes:** Replace the 300s wall-clock deadline with a staleness monitor (progress-based liveness), abandonment accounting (an unfinished child gets an explicit terminal entry, cooperative stop, never wedges the slot), steer into a running subagent with the completion race closed, leased delivery of completed results, spawn depth from persisted lineage, ownership-scoped control plane, per-child transcript, and optimistic-concurrency writes.

**Verdict: DEFER**

**Reasoning:**
- The section explicitly states: "SubagentManager is constructed only in tests and spawn_subagent is a no-op in production (state_machine.py:2007)." This is infrastructure for a consumer that does not exist.
- The founder decision asks: "Is SubagentManager to be wired to a production consumer now, and which one?" The recommended default is: "fix the wedge and staleness bugs (tests pin the manager), leave spawn_subagent unwired until a consumer is named."
- The wedge bugs (two abandoned subagents wedge the manager and _promote_next never drains) are real but only affect tests. The staleness monitor is real but only affects tests.
- Building a full subagent management stack (lease delivery, spawn depth, ownership scoping, per-child transcripts, optimistic-concurrency writes) for a no-op production consumer is cargo-culting an origin pattern that doesn't fit Halbert's current architecture.
- The section itself says "M1/M2 are worth fixing regardless because tests pin the manager and the interrupt algebra assumes it." So the minimum viable version is: fix the two wedge bugs (M2) and add the staleness monitor (M1), nothing else.

**If RESHAPE: what should it become?**
Fix the two wedge bugs (abandoned subagents wedge the manager, cancelled-then-completed drops the result) and add the staleness monitor (progress-based liveness replacing the 300s wall-clock). DEFER everything else behind the founder decision to wire a production consumer. The wedge fixes are S-M effort and keep the tests honest.

---

## VOICE-MEDIA-VISION (VMV-1 through VMV-6)

### Packet: VMV-1 — A wake word that fires

**What it actually proposes:** Fix the hardcoded ONNX wake-word backend (dead on macOS ARM64 — openWakeWord's ONNX embedding model scores near zero on Apple Silicon, so a detector arms cleanly and never fires), add sherpa-onnx open-vocabulary keyword spotting as the wake engine (zero training — any typed phrase is BPE-tokenized at runtime), production-harden the listener (cooldown, confirmation-frame debounce, dead-mic detection, reset on resume, correct 1280-sample frame size), and add a transcript-level activation-name matcher for mid-session address.

**Verdict: ACCEPT**

**Reasoning:**
- No overlap with any merged remediation. This is entirely new work on a broken subsystem.
- The wake word is broken on macOS ARM64 — the target platform. The detector arms and never fires. VAD alone opens every turn. This is a real defect that makes the voice surface unusable for its intended purpose.
- The sherpa-onnx KWS is zero-training and fits the "never bake a model name" rule — the phrase is data derived from configuration (the onboarding ai_name), never a shipped artifact. sherpa-onnx is already a first-class dependency (asr_engine, tts_engine, audio_tagger, speaker_id), so this adds a model file, not an ML stack. No Haloysius contract violation.
- The listener hardening (C3) fixes a real defect: pipeline.py:347 sets frame_target = SILERO_WINDOW_SAMPLES * 2 (512 samples / 32ms, the VAD window) and hands that same frame to the wake detector, but openWakeWord expects 1280-sample / 80ms frames. Halbert feeds a frame 2.5x too short. This is a concrete bug.
- The activation-name matcher (OC11-C1) is the only mechanism by which the onboarding name works as an address without a retrain — a trained .tflite cannot follow a rename. It degenerates cleanly to one user.
- The shared-room rule (OC11-C20) depends on this theme — with one human present every utterance is addressed to the assistant; the moment a second human is detected a name becomes required.
- No standing-rule violation. The phrase is the onboarding name, never "Sovereign," never the raw hostname.
- The effort is justified — the voice surface is a core feature and it's broken.

**Opportunities:** C2 (KWS engine) and OC11-C1 (activation name matcher) both key on ai_name — build the name-resolution path once. C3's listener reset-on-resume also fixes the A09-G2 duplicate-transcript root cause on the pipeline side.

---

### Packet: VMV-2 — One spoken egress

**What it actually proposes:** One streaming think/reasoning scrubber for all tag families on the SSE path (currently the SSE filter recognizes only ⊗/⊗, so a local model emitting <reasoning> or <thought> streams its chain of thought to the dashboard), spoken-text normalization residue (emoji/variation selectors and unterminated think blocks), an output-activity tracker (is speech actually playing, is it interruptible, watchdog for playback that outlives its audio), and transcript persistence as a bounded serial queue that stops the session on overflow.

**Verdict: RESHAPE**

**Reasoning:**
- R-10 (speech egress: one pipeline, budget hint, sanitizer) already addressed the core speech-egress pipeline. The A10 audit gaps (G7 budget hint, G5 Wyoming bypass, G3 fence regex) were R-10's scope. If R-10 wired the budget hint, fixed the Wyoming bypass, and fixed the fence regex, then those items are DONE.
- The section says "the engine's VoiceRiskPolicy word budget caps every spoken copy at 12-35 words, so the C2 speech summarizer is dead code." R-10 was supposed to wire the budget hint (A10-G7) and fix the Wyoming bypass (A10-G5). If those are done, the residual is:
  1. The think/reasoning scrubber (HM02-C11) — the SSE filter recognizes only ⊗/⊗. A local model emitting <reasoning> or <thought> streams its chain of thought to the dashboard. This is a real leak that R-10's "sanitizer" may or may not have addressed. The section says "nothing handles think tags on the spoken path at all." If R-10's sanitizer covered the spoken path but not the SSE path, the SSE filter is a residual.
  2. The output-activity tracker (OC11-M3) — no overlap with R-10. A satellite that swallowed audio and one mid-sentence look identical to barge-in. This is real for the Wyoming path.
  3. The transcript persistence serial queue (OC11-C19) — no overlap with R-10. The ChunkQueue silently drops the oldest chunk with no counter, no log, no signal. This is a "grounds claims in measured data" violation.
  4. The spoken-text normalization (HM08-M4) — emoji/variation selectors and unterminated think blocks. R-10's sanitizer may have covered the think-block stripping; the emoji strip is implied by "no emoji in UI."
- The spoken-tail-through-echo-guard (A05-G5) should route through R-05's redaction registry and R-06's echo guard — both merged. If those seams are already in place, the residual is wiring the spoken tail through them.
- No standing-rule violation. The scrubber is deterministic.

**If RESHAPE: what should it become?**
First, verify what R-10 actually delivered. The residual is likely: (1) the full-tag-family SSE scrubber (HM02-C11, if R-10 only covered the spoken path), (2) the output-activity tracker (OC11-M3, no overlap), (3) the ChunkQueue dropped-chunk counter (OC11-C19, S effort, no overlap). Drop anything R-10 already covered. The emoji strip is already implied by "no emoji in UI."

---

### Packet: VMV-3 — Inbound media bounds and leak-free media/status surfaces

**What it actually proposes:** A centralized per-capability media size/timeout/char-limit table, MIME sniffing from a bounded base64 prefix, a bounded attachment count per turn, a closed media-delivery failure taxonomy (fixing the Frigate raw-exception leak), sanitizing configured base URLs before display (fixing the guest-home display leak), a stable media:// reference for inbound media in prompts, and binding the privileged unredacted path to a host-owned retained set.

**Verdict: ACCEPT**

**Reasoning:**
- No overlap with any merged remediation.
- The unbounded inbound media inputs are real security defects: routes/agent.py:52 takes an unbounded image list; routes/audio.py:215 and :267 b64decode an unbounded request field with no length check. A 200MB base64 string is decoded into memory without any check.
- The Frigate raw-exception leak is real: frigate_tools.py returns raw exception text as the tool result, so a requests/urllib error carrying the Frigate base URL (or credentials embedded in it) lands in the model's context and the transcript. Same shape as the SSE error leak fixed elsewhere.
- The guest-home URL leak is real and verified: persona/guest.py validates only scheme and non-empty netloc, to_dict() returns the URL raw, and routes/guest.py:421 uses urlparse(home.base_url).netloc as the display name. The verifier confirmed that urlparse('https://user:s3cr3t@home.local:8443/x?token=abc').netloc == 'user:s3cr3t@home.local:8443'. A credentialed home URL is rendered as a display name.
- The privileged-unredacted-path binding (OC11-C3) fixes a real defect: result_redaction.py:39-60 documents KNOWN RISK NEW-01 — _egress_ack: True is honoured by _redact_dict on any dict at any depth purely by shape, i.e. a marker in a payload selects the unredacted path. This is exactly what the OpenClaw comment forbids.
- The media:// reference (OC03-C13) is low priority — with a pinned local model the disclosure is to the host's own model. Insurance for the :cloud slot case.
- No standing-rule violation. The redaction goes through the deterministic registry. The failure taxonomy uses fixed copy, never an exception string. No emoji (the origin's U+26A0 prefix is dropped).
- The effort is justified — these are security defects on inbound surfaces.

**Opportunities:** The base-URL sanitizer promotes mcp/config.py's redact_url to security/ and routes every provider base-URL display through it. One helper, multiple consumers. The media limits table and the MIME sniffer are one module.

---

### Packet: VMV-4 — Voice ingress hardening and turn replay

**What it actually proposes:** A sequenced, replayable per-turn event tail so a reconnecting surface recovers the turn, a three-axis budget with maintained running footprint (eviction only on the ephemeral tail), a reconnect supervisor with backoff/jitter/stability-window, WS keepalive missed-pong diagnostics, and a fast-context shortcut for spoken what/when questions gated on a STRONG recall.

**Verdict: RESHAPE**

**Reasoning:**
- R-02 (claims, admission graph, guest routes, voice provenance) already addressed voice provenance and speaker claims. A09-G1 (busy verbs bypass the speaker-claim clamp) is about the admission graph — routes/agent.py:1697-1700 calls handle_midturn_arrival before the receipt is consumed. This is the talk-door ordering that R-01 fixed. If R-01 fixed the midturn arrival ordering, A09-G1 is DONE.
- R-01 (talk-door ordering) already addressed the receipt-before-steer ordering. The section says A09-G1 is "Fix: consume the receipt and stamp first" — this is R-01's talk-door ordering fix. If R-01 delivered this, A09-G1 is DONE.
- A09-G2 (duplicate-transcript suppression) was "Called for in the packet-04 Hermes addendum and never built." This is a known gap that was never addressed. It belongs with VMV-1's C3 (reset-on-resume removes the root cause on the pipeline side) and the relay-side suppressor.
- The replayable event tail (OC11-M1) is real: the turn runs inside the SSE generator, so a dropped SSE, a reloaded tab, or a voice HUD attaching mid-turn gets nothing. The turn_event_tee is process-wide, in-memory, observe-only. This is a real defect for a surface that drops connections (laptop sleep, wifi flap).
- The three-axis budget (OC11-M2) is medium — it's a maintained aggregate for O(1) size queries. Valuable but not urgent.
- The reconnect supervisor (OC10-C9) is real: ha_event_stream.py is a flat 5s retry loop with no backoff, jitter, or stability window. mcp/health.py's counter resets on the first success, so a server that accepts and immediately drops resets the budget every cycle. This is the same mechanism as SCHED-P5's thaw reconnect.
- The WS keepalive (OC17-C15) is low — no flapping observed.
- The fast-context shortcut (OC11-C4) is medium — a bounded memory search before a full agent run. It depends on the recall-decision log (OC11-M6, re-homed to the memory packet) for tuning.
- No standing-rule violation. Recovery of the one continuous conversation, not a session list.

**If RESHAPE: what should it become?**
First, verify R-01 and R-02 delivered A09-G1 and the voice provenance fixes. The residual: (1) replayable event tail (OC11-M1) + A09-G4 (seq/ts on tee payloads) — real defect, M effort. (2) reconnect supervisor (OC10-C9) — shared with SCHED-P5's thaw reconnect, build once. (3) A09-G2 duplicate-transcript suppressor — pairs with VMV-1's C3. DEFER: three-axis budget (OC11-M2, needs a DECISIONS note first), fast-context shortcut (OC11-C4, needs the memory packet's decision log first), WS keepalive (OC17-C15, low).

---

### Packet: VMV-5 — Screen and vision truthfulness, and the day journal

**What it actually proposes:** Disclose the coordinate mapping when a screenshot is downscaled or cropped (thread pre/post geometry and crop origin out of ScreenCapture, append a scale/offset note to the description), bind screen-input authorization to a generation+geometry frame hash (bank only, no build), and a consented screen-activity logbook (frames → observations → goal-merged cards → evidence-only standup, founder-gated).

**Verdict: RESHAPE (accept the coordinate disclosure, defer the rest)**

**Reasoning:**
- The coordinate mapping disclosure (HM08-M3) is a real defect: tools/vision_tools.py returns only {'image', 'description'} while the docstring promises width, height that are never returned. This matters precisely because Halbert stages UI commands rather than executing them — a human reads those coordinates. A 2x downscaled capture returns coordinates that are wrong by 2x with no indication. Effort S, no founder decision.
- The frame-token guard (OC21-C1) is "bank, do not schedule" — the section says "not yet needed: the only UI-input route is AppleScript System Events addressing elements by name/hierarchy." No work now.
- The screen-activity logbook (OC20-C14) is founder-gated and the recommended default is "not yet — first review vision/redact.py's blocklist against a journal's exposure." This is a big build (effort M) for a feature that needs a founder yes and a privacy review.
- No standing-rule violation. The coordinate note is pure text, no model. The logbook must not copy the baked provider name.

**If RESHAPE: what should it become?**
Ship the coordinate mapping disclosure (HM08-M3) now — it's S effort, fixes a real defect, no founder gate. Bank the frame-token guard as a precondition for future computer-use. DEFER the logbook behind founder decision 1 and a privacy review of redact.py's blocklist.

---

### Packet: VMV-6 — Audio runtime footprint, BYO providers, capability assertions, runtime health

**What it actually proposes:** An idle-unload watcher for resident local audio models (release hundreds of MB after N idle seconds, reload on next use), a bring-your-own-CLI command-provider slot for STT/TTS, per-operation host-capability requirements with a declare-and-assert layer, and durable subsystem quarantine records whose expiry is process liveness.

**Verdict: ACCEPT (with one gate)**

**Reasoning:**
- No overlap with any merged remediation.
- The idle-unload watcher (HM08-M1) is a real resource issue: every audio model (ASR, TTS, tagger, speaker_id) is resident for the daemon's life. Hundreds of MB held indefinitely on a machine that may not use voice for hours. The invariant (an in-flight use always holds its own reference) is clean. Effort M, deterministic, config-only.
- The BYO CLI STT/TTS (HM08-C11) fits "connection slots, not model menus" — the user declares a shell-command template, Halbert code names no vendor. But it needs a founder decision (it hands arbitrary shell execution to a config file). The section says execution goes through the existing RoleGate + safety pipeline, never a bare subprocess.run. This is the right constraint.
- The capability assertions (OC11-M4) are a general mechanism: has_capability() is a bare boolean and every consumer writes its own refusal. A declare-and-assert layer would produce one consistent refusal that tells the founder what the machine has versus what the operation needed. This touches many files but is the concrete form of "scope by capability boundary."
- The runtime health records (OC11-M5) are a general mechanism: a subsystem that failed at runtime is a durable health record the dashboard can show. "This part of me is not working, since when, why." This fits "first-person as the machine, grounded in measured data." No migration — new records in a new kind.
- No standing-rule violation. The BYO provider uses the utility slot's resolve-never-hardcode ladder. The capability assert implements "scope by capability boundary."
- The idle-unload and capability assertions need no founder gate. The BYO CLI provider needs a founder yes.

**Opportunities:** The capability-assert layer (OC11-M4) is a cross-cutting mechanism — it could serve TT-03's unattended policy (checking capability before admission) and SCHED-P3's preflight (checking model endpoint capability before running). The runtime-health records (OC11-M5) could serve SCHED-P3's failure containment (a quarantined subsystem is a health record).

---

## CROSS-CUTTING OPPORTUNITIES

### 1. Process-group kill helper (`utils/process_group.py`)
Appears in: SCHED-P2 (HM16-M4), TT-01 (OC13-C5/OC08-C1). Also closes A17-G10 (stdio MCP server kill).
Build once: `spawn_with_session()` + `kill_tree(pid, grace_s)` with start-time verification. Use at executor.py:832, pty.py:362/432, tools/system_info.py:43, mcp/client.py:331, applescript_tools.py:85.

### 2. PID + start_time identity (`utils/process_identity.py`)
Appears in: SCHED-P1 (OC06-C13), TT-01 (HM11-C18/HM07-C5), SCHED-P5 (HM11-C2 unclean-exit sentinel), TT-02 (trusted-executable check).
Build once: `get_process_start_time(pid)` + `pid_matches(pid, expected_start_time)`. Use in run_receipts liveness, parent_watchdog, the unclean-exit sentinel, and the trusted-executable check. psutil is already a hard dependency.

### 3. Activity clock / progress stamp (`agents/turn_activity.py`)
Appears in: SCHED-P2 (HM16-C16 inactivity watchdog), SCHED-P4 (HM01-C2 turn-liveness), TT-06 (HM05-M1 subagent staleness), TT-05 (tool-execution heartbeat).
Build once: `stamp_activity(desc)` on a monotonic clock + `check_idle(ceiling_s)` comparator. The primitive already exists in turn_activity.py (lock + monotonic generation + single-shot claim). Extend it with an activity timestamp and reuse across the scheduler watchdog, the turn watchdog, the subagent staleness monitor, and the tool heartbeat.

### 4. Text hygiene / ANSI-Unicode strip (`security/text_hygiene.py`)
Appears in: TT-01 (HM06-C5 ANSI/Unicode tag stripper), TT-03 (HM07-M4 normalizer step one), TT-01's display-boundary item (OC07-M1).
Build once: `strip_ansi()`, `strip_unicode_tags()`, `sanitize_display_text()` with the CR fold. Use at executor.py command results, agent_pool.py block output, MCP tool results/descriptions, the confirmation dialog, and the command normalizer.

### 5. Atomic write helper (`utils/atomic_write.py`)
Appears in: TT-01 (HM07-M2 write_config atomic write), SCHED-P1 (HM16-M8 chmod in the replace helper).
Build once: temp-in-target-dir, mode copied, fsync, os.replace, optional chmod. Use in write_config.py's four apply paths and the scheduler's _persist_job/receipts writer. Six internal stores already do a partial version — consolidate.

### 6. Reconnect supervisor (`net/reconnect_supervisor.py`)
Appears in: VMV-4 (OC10-C9 HA event stream + MCP health), SCHED-P5 (OC16-C8 thaw reconnect).
Build once: backoff with jitter, stability window before budget reset, bounded drop-oldest outbound queue. Use by ha_event_stream.py, mcp/health.py, and the heartbeat tick's thaw detector.

### 7. Capability assert layer (`capabilities.py` extension)
Appears in: VMV-6 (OC11-M4), TT-03 (unattended policy could check capability), SCHED-P3 (preflight could check model endpoint capability).
Build once: `require_capabilities(op, {...})` over the existing `has_capability()` probe registry. One consistent refusal string naming required/missing/present. Migrate consumers one by one, voice/vision operations first.

### 8. Notification throttle (`utils/notification_throttle.py`)
Appears in: TT-04 (HM07-C4 watch-pattern throttle), SCHED-P3 (HM16-C8 failure-incident dedup).
Build once: per-source strikes + global circuit breaker with a window and lifetime cap. Use by the registry's watch patterns and the scheduler's failure-incident dedup.

---

## SUMMARY OF VERDICTS

### Scheduler (SCHED-P1 through SCHED-P6)
- ACCEPT: P2 (honest timeouts), P4 (turn liveness)
- RESHAPE: P1 (receipt truth — 80% done by R-03, residual is cancel fix + PID identity + permissions), P3 (failure containment — drop done items, keep auto-disable + standing-orders + ESTOP fixes), P5 (process lifecycle — accept core, defer tail), P6 (scheduled-work surface — defer most, ship dashboard page + digest + webhook normalizer)
- REJECT: none
- DEFER: P6 (most of it, behind founder decision 7)

### Terminal-Tools (TT-01 through TT-06)
- ACCEPT: TT-01 (shell executor hardening), TT-03 (command classifier v2), TT-05 (tool-loop guardrails)
- RESHAPE: TT-02 (child-process boundary — drop MCP env if R-09 covered it, keep PTY fence + ContextVar hygiene), TT-04 (split: ship PTY reattach + guardrails now, defer registry + wake)
- REJECT: none
- DEFER: TT-06 (subagent manager — fix wedge bugs only, defer the rest behind a production consumer)

### Voice-Media-Vision (VMV-1 through VMV-6)
- ACCEPT: VMV-1 (wake word), VMV-3 (inbound media bounds), VMV-6 (audio footprint + capability assertions)
- RESHAPE: VMV-2 (one spoken egress — verify what R-10 delivered, keep the residual), VMV-4 (voice ingress — verify R-01/R-02 delivered A09-G1, keep replay tail + reconnect), VMV-5 (screen truth — ship coordinate disclosure, defer logbook)
- REJECT: none
- DEFER: none (all have a dispatchable core)

### Standout opportunities
The three highest-leverage cross-cutting builds are: (1) the process-group kill helper (serves 4+ call sites across scheduler and terminal), (2) the activity-clock primitive (serves 4 packets across scheduler, terminal, and subagent), and (3) the text-hygiene module (serves TT-01, TT-03, and the display-boundary work). Each is small effort, unblocks multiple packets, and has no founder-decision gate.
