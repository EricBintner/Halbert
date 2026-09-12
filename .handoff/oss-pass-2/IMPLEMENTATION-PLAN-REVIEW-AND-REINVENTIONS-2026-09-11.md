# OSS Pass-2 Implementation Plan — Deep Review & Architectural Reinventions

Written 2026-09-11. Companion and critical review to:
- `.handoff/oss-pass-2/IMPLEMENTATION-PLAN-2026-09-11.md`
- `.handoff/oss-pass-2/FINAL-CRITICAL-DISCOVERY-BACKLOG-2026-09-11.md`
- Source inspirations in `/Volumes/Thunderbolt/AI/OSS/` (`hermes-agent`, `open-claude-code`, `openclaw`, `warp`)

This document performs a deep review of the proposed pass-2 implementation plan. It evaluates what ideas make the most sense for Halbert, extracts and reinvents the transformative design patterns of the four reference OSS applications, identifies major design opportunities, and restructures the execution roadmap to untangle the 28-item Phase 3 bottleneck.

No code is changed by this document. It serves as strategic architectural guidance for dispatch.

---

## 1. Critical Appraisal of the Implementation Plan

The plan in `IMPLEMENTATION-PLAN-2026-09-11.md` is a rigorous, highly granular operational document. It provides essential corrections to earlier assumptions and lays out a disciplined foundation. However, when measured against the goal of lifting and *reinventing* the best ideas from modern OSS AI systems, several structural issues emerge.

### 1.1 What the Plan Gets Exactly Right

1. **Remediation Status Realism (§0)**: Correctly identifies that the Sonnet batch (`R-03` scheduler durability, `R-13` locality everywhere, `R-15` eval harness, `R-12 Phase A` compaction) is **unmerged** and remains on branch `fix/remediation-sonnet-batch-1`. Isolating unmerged work prevents false assumptions of codebase capabilities.
2. **Primitives Before Consumers (Phase 0)**: Building foundational utilities (`durable_write`, `process_group`, `text_hygiene`, `subprocess_env`, `DIAG-02` read-only opener) before dependent consumers prevents duplicated, divergent implementations across workstreams.
3. **Hermetic Test Isolation First (`T1`)**: Prior audits proved tests were opening the host's live `conversations.db` and reading `~/.config/halbert/skills`. Prioritizing `T1` in Phase 0 protects the development environment from accidental self-corruption.
4. **Targeting Live Data-Loss Defects (Phase 1)**: Correctly prioritizes bugs that actively lose user data or hang sessions today:
   - `SP-3`: Multi-tool dispatch dropping all but the first tool call in `state_machine.py:2669`.
   - `MP-2`: Provider 429/529 backoff blocking the server with bare `time.sleep` and clamping `Retry-After` to 60s.
   - `MP-3`: `aiohttp.ClientTimeout(total=120)` terminating healthy local LLM generation streams mid-sentence.
5. **Part E's User-Experience Scrutiny**: The scrutiny pass in Part E is perceptive: it correctly identifies that stability bugs (like terminal disconnects, silent settings reverts, and hung turns) are direct product UX failures, successfully promoting 12 packets into earlier phases.

### 1.2 Critical Flaws & Strategic Gaps in the Plan

1. **The Phase 3 Congestion (The 28-Unit Logjam)**:
   - In Part F, Phase 3 has ballooned into an unmanageable 28-unit monolith. It mixes low-level macOS Darwin memory probes (`T2`), terminal PTY reattach (`TT-04a`), audio DSP wake-word tuning (`VMV-1`), SQLite integrity checks (`MEM-P3`), dashboard polling interval refactoring (`SURFACE-01b`), and stuck-turn reclamation (`DAEMON-01b`).
   - *Impact*: Any agent or engineer attempting Phase 3 will suffer context fragmentation, hot-file merge collisions (e.g., `state_machine.py`, `pty.py`), and stalled progress.
2. **Audit-Code Fragmentation vs. Cohesive System Design**:
   - The plan organizes work by discovery ticket IDs (`TT-01`, `VMV-3`, `CSC-06`, `OTHER-P5`) rather than cohesive architectural subsystems.
   - For instance, command normalization (`TT-03`), approval binding (`P2`), shell executor hardening (`TT-01`), and dialog injection defense (`SURFACE-01a`) are scattered across three phases, even though they form one cohesive subsystem: **The Sovereign Command & Staging Engine**.
3. **Bug-Fixing Mindset vs. Architectural Reinvention**:
   - The plan views `/Volumes/Thunderbolt/AI/OSS/` primarily as a catalog of bugs, leaks, and regexes to port.
   - It misses the larger architectural inventions pioneered by those apps:
     - **Warp's** semantic block-level terminal execution.
     - **Open-Claude-Code's** unified diff-staging and deterministic tool permission lattices.
     - **Hermes's** measured stop-gates and autonomous tool-call repair loops.
     - **OpenClaw's** trusted gateway and provenance-carrying event bus.
4. **Missing Primitive: The Activity Clock**:
   - The plan lists `activity-clock` as an external prerequisite in Phase 3 for `SCHED-P2`, `SCHED-P4`, `TT-05`, and `TT-06`, but **never defines where or when it is built**. It is absent from Phase 0.
5. **Accidental Dropping of `MP-5` (Local Model Tool-Call Repair)**:
   - In `FINAL-CRITICAL-DISCOVERY-BACKLOG-2026-09-11.md`, `MP-5` was marked **ACCEPT**.
   - In `IMPLEMENTATION-PLAN-2026-09-11.md`, `MP-5` disappeared from both the Phase 1 and Phase 3 tables in Part F. Local models frequently output markdown-wrapped or prose-prefixed tool calls; without `MP-5`, local tool execution remains fragile.

---

## 2. Lifting & Reinventing Features from the OSS Repositories

The four reference repositories in `/Volumes/Thunderbolt/AI/OSS/` each represent a distinct paradigm in the 2026 agent landscape. Below is how their best concepts must be reinvented for Halbert.

```
┌───────────────────────────────────────────────────────────────────────────────────────────┐
│                                HALBERT SOVEREIGN POSTURE                                  │
│  - Speaks as the computer itself, in first person, grounded in measured hardware data.     │
│  - One seamless conversation with hidden topic threads; no conversation list.             │
│  - Commands staged, never executed.                                                       │
│  - User shells stay, watched by the AI with subtle ambient indicator lights.               │
│  - No model names on user surfaces (connection slots). Zero UI emoji. Shared CSS tokens.  │
│  - Local-first; Tier 2 secrets handled by deterministic templates, never a model.         │
└───────────────────────────────────────────────────────────────────────────────────────────┘
                                ▲                     ▲
        ┌───────────────────────┴──────┐       ┌──────┴──────────────────────┐
        │                              │       │                             │
┌───────┴─────────────────┐ ┌──────────┴───────┴───────┐ ┌───────────────────┴───────┐
│ WARP                    │ │ OPEN-CLAUDE-CODE         │ │ HERMES-AGENT              │
│ Block-level terminal    │ │ Strict permission gate   │ │ Self-improving loop       │
│ Semantic command stream │ │ Diff & command staging   │ │ Stop-gates & tool repair  │
└─────────────────────────┘ └──────────────────────────┘ └───────────────────────────┘
        │                              │                             │
        ▼                              ▼                             ▼
┌─────────────────────────┐ ┌──────────────────────────┐ ┌───────────────────────────┐
│ REINVENTION:            │ │ REINVENTION:             │ │ REINVENTION:              │
│ Semantic Watched Shells │ │ Inode-Bound Staging Card │ │ Measured Machine Gates    │
│ & Ambient Indicator     │ │ Content SHA-256 + Inode  │ │ Deterministic system-state│
│ Triage (OSC 133/7).     │ │ binding; anti-trojan LTR.│ │ verification; tool salvage│
└─────────────────────────┘ └──────────────────────────┘ └───────────────────────────┘
```

### 2.1 From Warp: Semantic Watched Terminal Envelopes

#### What Warp Does
Warp moves beyond the unstructured ANSI byte stream. Commands, working directories, execution timings, and outputs are framed into discrete **semantic blocks** tracked via shell integrations (OSC 133 / OSC 7).

#### Halbert's Standing Directive
*"User shells stay but are watched by the AI; the agent reuses idle terminals; subtle indicator-light notifications."* (`DECISIONS.md`).

#### The Reinvention
Instead of dumb text-scraping across PTY streams, Halbert reinvents Warp's block model into **Semantic Watched Envelopes**:
1. **Passive Diagnostic Awareness**: Halbert attaches to existing user shells without interfering. Using the existing OSC 133/7 state machine in `streaming/shell_integration.py`, Halbert tracks:
   - Working directory changes (`OSC 7`).
   - Command boundaries and exit codes (`OSC 133;D;<exit_code>`).
   - Failure patterns (e.g., `command not found`, `ModuleNotFoundError`, `merge conflict`, `137 OOM`).
2. **Ambient Triage via Subtle Indicator Lights**: When a user's command fails in their terminal (e.g., a homebrew install fails or a Python script misses a dependency), Halbert does not interrupt or pop open modals. It updates the ambient Status Light and stages a diagnostic finding in the Findings rail:
   - *"I noticed your build in `~/src/web` failed with exit code 1 (missing libssl). I have staged the dependency install."*
3. **Session Reconnect Without State Loss (`CSC-06` + `TT-04a`)**: By preserving PTY session leaders and wiring the PTY replay ring to WebSocket reconnects with `since_seq`, closing a laptop lid or experiencing network jitter never drops the shell with `exitCode -1`.

### 2.2 From Open-Claude-Code: Unified Staging & Inode Approval Protocol

#### What Claude Code Does
Claude Code implements a strict terminal-first execution harness with structured diff viewing, explicit permission boundaries, and fail-closed command execution.

#### Halbert's Standing Directive
*"Commands staged from the UI are staged, never executed."* (`DECISIONS.md`).

#### The Reinvention
The implementation plan fragments approvals across `TT-01`, `TT-03`, `P2`, and `SURFACE-01a`. Halbert must synthesize these into a **Unified Staging & Inode Approval Protocol**:
1. **Content SHA-256 & Inode Binding (`P2`)**:
   - Approvals must never bind to a raw path string (e.g., `/etc/hosts` or `~/script.sh`).
   - The approval receipt must bind to `(device_id, inode, content_sha256)`. If a file is modified out of band between staging and user confirmation, the approval receipt is immediately invalidated with an honest explanation:
     - *"I cancelled this execution because the target file was modified after you reviewed it."*
2. **Normalization & Anti-Trojan Defense (`TT-03` + `SURFACE-01a`)**:
   - Commands must be normalized before safety classification: strip ANSI escapes, resolve variable expansions (`$IFS`), collapse backslash escapes (`r\m`), and evaluate command starts (`$(echo rm)`).
   - In the frontend (`ConfirmationDialog.tsx`), enforce strict Left-to-Right (LTR) bidirectional Unicode overrides. Trojan source characters (e.g., U+202E) cannot visually invert dangerous commands in the approval card.

### 2.3 From Hermes-Agent: Sovereign Verification Stop-Gates & Local Model Salvage

#### What Hermes Does
Hermes Agent excels at two production realities:
1. `turn_stop_gates.py`: Intercepting an agent turn before text is committed if changes lack verification.
2. Rescuing corrupted or malformed tool calls emitted by non-frontier models.

#### Halbert's Standing Directive
*"The LLM identifies as the computer itself, first person, grounded in measured data... never a model where a template suffices."* (`DECISIONS.md`).

#### The Reinvention
1. **Measured Machine Stop-Gates (Reinventing `T3` / `TT-05`)**:
   - In Hermes, an LLM checks if code was verified. In Halbert, as *the computer itself*, verification is **grounded in measured system state**.
   - When Halbert stages an action that changes machine state (e.g., modifying a service configuration, killing a runaway process), the stop-gate evaluates deterministic OS metrics:
     - Did port 8000 stop listening?
     - Did the systemd service enter `active (running)`?
     - Did the exit code equal 0?
   - If verification fails, Halbert reports measured reality: *"I applied the change, but port 8000 remains unbound. I have marked this finding unresolved."*
2. **Deterministic Tool-Call Repair (`MP-5`)**:
   - Local models (Qwen-2.5, Llama-3.1, Mistral running via Ollama or LM Studio) frequently leak markdown fences (````json ... ````) or conversational chatter into tool calls.
   - `model/client.py:457-465` currently coerces unparseable arguments to `{}`—silently destroying tool calls.
   - Implement Hermes's deterministic extractor: scan for JSON blocks, strip conversational framing, repair trailing commas, and re-parse before failing closed. This single fix transforms local models from barely usable to reliable tool executors.
3. **Receipt-to-Reflex Staging (Reinventing `SP-5` / `SP-6` Safely)**:
   - Hermes allows the model to autonomously rewrite skill files. In Halbert, autonomous model-driven disk writes violate security directives.
   - **The Halbert Solution**: When a complex troubleshooting sequence succeeds, Halbert synthesizes a deterministic **Machine Reflex** staged under the Findings UI. The human reviews the recipe and clicks *"Save to Local Reflexes"*. This achieves the self-improving loop without autonomous prompt-injection or hallucinated file corruption.

### 2.4 From OpenClaw: Unified Cause & Attribution Engine (`CH-A++`)

#### What OpenClaw Does
OpenClaw operates a trusted local gateway orchestrating multiple messaging channels, enforcing strict credential isolation, and attaching immutable provenance to every event.

#### Halbert's Standing Directive
*"The system speaks as the computer itself, in first person... Connection slots, not model menus."* (`DECISIONS.md`).

#### The Reinvention
1. **Turn Cause Axis (`CH-A`)**:
   - In Halbert today, `agents/channels.py` only understands turns originating from the dashboard chat. Background scheduler runs, memory consolidation passes, and watched-terminal alerts have to fake a dashboard channel.
   - `CH-A` introduces `InternalTurnSource`:
     ```python
     class InternalTurnSource(str, Enum):
         USER_DASHBOARD = "user_dashboard"
         USER_VOICE = "user_voice"
         WATCHED_TERMINAL = "watched_terminal"
         SCHEDULER_CRON = "scheduler_cron"
         HARDWARE_ALERT = "hardware_alert"
         INTERNAL_REFLEX = "internal_reflex"
     ```
   - Turns originating from machine events carry honest provenance and no speaker claims. When Halbert responds to a thermal alert, it speaks as the machine reacting to sensors, not an assistant responding to an imaginary prompt.
2. **Subprocess Credential Quarantine (`MP-6`)**:
   - `tools/system_tools.py` and `streaming/pty.py` copy `os.environ` wholesale into every child shell. `HALBERT_API_TOKEN` and remote provider keys leak to every invoked script.
   - Replicating OpenClaw's strict child environment whitelist via `tools/subprocess_env.py` guarantees zero ambient credential leakage.

---

## 3. What Ideas Make the Most Sense: The 5 Non-Negotiable Pillars

The ~64 discovery items must be anchored around five non-negotiable architectural pillars that directly uphold Halbert's identity:

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                        THE FIVE NON-NEGOTIABLE PILLARS                                 │
├───────────────────────────────┬────────────────────────────────────────────────────────┤
│ 1. Substrate & Test Integrity │ T1 (Hermetic Tests), DAEMON-01a (Single-Instance Lock) │
│                               │ Protects live data and databases from test corruption. │
├───────────────────────────────┼────────────────────────────────────────────────────────┤
│ 2. Local Model & Transport    │ SP-3 (Multi-Tool Bug), MP-2 (Retry-After),             │
│    Resilience                 │ MP-3 (Stream Idle Timeout), MP-4/5 (Context & Repair)  │
│                               │ Guarantees local inference does not stall or drop work.│
├───────────────────────────────┼────────────────────────────────────────────────────────┤
│ 3. Watched Terminal &         │ CSC-06 (PTY Reconnect), TT-01/03 (Shell Hardening),    │
│    Staging Safety             │ TT-04a (Guardrails), P2 (Inode Approval Binding)       │
│                               │ Core desktop steward shell experience.                 │
├───────────────────────────────┼────────────────────────────────────────────────────────┤
│ 4. Turn Watchdogs & Liveness  │ DAEMON-01b (Stuck-Turn Watchdog), SCHED-P2/P4/P5       │
│                               │ Eliminates eternal spinners and hung locks forever.    │
├───────────────────────────────┼────────────────────────────────────────────────────────┤
│ 5. Memory Trust & Compaction  │ MEM-P1 (Read Trust), MEM-P3 (SQLite Backup/Salvage),   │
│                               │ MEM-P6 (Compaction Follows Real Tokens)                │
│                               │ Ensures cross-session continuity is honest and durable.│
└───────────────────────────────┴────────────────────────────────────────────────────────┘
```

1. **Substrate & Test Integrity (`T1`, `DAEMON-01a`, `DIAG-02`)**:
   - Halbert stores memory in SQLite on `/Volumes/4TB-BAD`. If tests open live databases (`conversations.db`), or if two instances spawn concurrently during development, database corruption is guaranteed.
2. **Local Model & Transport Resilience (`SP-3`, `MP-2`, `MP-3`, `MP-4`, `MP-5`)**:
   - Unlike cloud-only web agents, Halbert runs on local compute (Ollama, LM Studio, Apple Silicon). Sizing context by character guesses (`MP-4`), dropping tool calls (`SP-3`, `MP-5`), or killing 120s generation streams mid-word (`MP-3`) makes local execution completely unreliable.
3. **Watched Terminal & Staging Safety (`CSC-06`, `TT-01`, `TT-03`, `TT-04a`, `P2`)**:
   - Halbert’s physical presence is the desktop terminal and dashboard. If shells die on laptop sleep (`CSC-06`), or if approvals can be tricked by quoting bypasses (`TT-03`) or TOCTOU file replacement (`P2`), the security and continuity model collapses.
4. **Turn Watchdogs & Process Liveness (`DAEMON-01b`, `SCHED-P2`, `SCHED-P4`, `SCHED-P5`)**:
   - A turn that hangs holding the conversation lock freezes the dashboard permanently. Replacing flat wall-clock timeouts with monotonic activity clocks guarantees hung turns are cleanly reclaimed.
5. **Memory Trust & Compaction (`MEM-P1`, `MEM-P2`, `MEM-P3`, `MEM-P6`)**:
   - Reading memory must enforce ownership: guest persona facts must never leak into the host's psyche. Compaction must track real token counts (`MEM-P6`), and the database must have automated integrity verification and online backups (`MEM-P3`).

---

## 4. Key Design Opportunities

### 4.1 Build `activity_clock` in Phase 0 as a Unified Primitive
The plan currently treats the "activity clock" as an abstract requirement needed by Phase 3 packets (`SCHED-P2`, `SCHED-P4`, `TT-05`).
* **Design Opportunity**: Create `utils/activity_clock.py` in Phase 0.
* **Contract**:
  ```python
  class ActivityClock:
      def __init__(self, idle_timeout: float): ...
      def record_activity(self, source: str = "") -> None: ...
      def idle_seconds(self) -> float: ...
      def is_stalled(self) -> bool: ...
  ```
* Consumed uniformly by:
  - LLM client streaming (`sock_read` idle detection in `MP-3`).
  - Terminal watched sessions (inactivity watchdog in `TT-04a`).
  - Scheduler job runs (detecting hung subprocesses in `SCHED-P2`).
  - Turn state machine (reclaiming hung turn locks in `DAEMON-01b`).

### 4.2 Establish `halbert doctor` (`DIAG-01`) as the Universal Diagnostic Bus
Instead of ad-hoc diagnostic scripts, unify `DIAG-01` into a single finding registry:
```python
class DiagnosticFinding(NamedTuple):
    domain: str            # 'memory', 'sqlite', 'model', 'scheduler', 'terminal'
    code: str              # 'SQLITE_WAL_VERSION', 'MODEL_LOCALITY_DRIFT'
    severity: Severity     # INFO, WARNING, CRITICAL
    message: str           # "I observed SQLite 3.39.4 with WAL reset vulnerability..."
    why_trust: str         # "Measured from sqlite3.sqlite_version"
    remediation: Optional[StagedAction]
```
Every workstream's residual checks register findings into this bus. The CLI (`halbert doctor --json`) and the dashboard (`GET /api/diagnostics`) consume this identical registry without new bespoke endpoints.

### 4.3 First-Person Machine Tone in Error & Recovery States
In accordance with `DECISIONS.md` (*"The LLM identifies as the computer itself, first person, grounded in measured data; never an assistant"*), all failure triage, fallback notices, and doctor findings must speak from hardware truth:
- **Never**: *"I apologize, an error occurred with Claude while processing your request."*
- **Always**: *"My local inference server on port 11434 stopped responding mid-generation. I preserved your conversation state and restarted the connection."*
- **Always**: *"I observed that `/etc/resolv.conf` was modified out of band after you approved the DNS change. I have halted execution to protect system consistency."*

---

## 5. The Restructured 5-Milestone Implementation Plan

To solve the 28-item Phase 3 bottleneck, this roadmap groups the accepted and promoted packets into **five cohesive, testable milestones**.

```
MILESTONE 0: Substrate Integrity & Hermetic Harness (Foundations)
  │  (T1, DAEMON-01a, durable_write, process_group, activity_clock, subprocess_env, DIAG-02)
  ▼
MILESTONE 1: Model Pipeline & Conversational Resilience
  │  (SP-3, MP-5, MP-2, MP-3, MP-4, DAEMON-01b)
  ▼
MILESTONE 2: Watched Terminal & Sovereign Command Engine
  │  (CSC-06, TT-01, TT-03, TT-04a, P2, TERM-02)
  ▼
MILESTONE 3: Memory Trust, Turn Provenance & Diagnostic Core
  │  (CH-A, MEM-P1, MEM-P2, MEM-P3, MEM-P6, DIAG-01, LOG-01)
  ▼
MILESTONE 4: Grounded UI, Voice & Ambient Stewarding
  │  (SURFACE-01a/b, VMV-1, VMV-3, VMV-5, VMV-6, SCHED-P6, OTHER-P6a/b)
  ▼
MILESTONE 5: Upstream Harmonization & Founder Gates
     (Verify Sonnet batch R-03/R-13/R-15/R-12 on merge; Phase 5 founder decisions)
```

---

### Milestone 0: Substrate Integrity & Hermetic Harness
*Goal: Ensure the test suite cannot touch the live host, eliminate multi-instance corruption, and establish atomic primitives.*

| Packet | Scope & Deliverable | Files | Effort | Depends on | Verification |
|---|---|---|---|---|---|
| **T1** | Hermetic test fixture; live-DB guard failing suite if test opens `conversations.db` or `~/.config/halbert`. | `tests/conftest.py`, new fixture | M | — | Test suite runs with zero live host file touches; guard asserts on forbidden paths. |
| **DAEMON-01a** | Single-instance lock (`flock`) on data dir; exit vocabulary (`supervised()` probe). | `dashboard/__main__.py`, `dashboard/app.py` | S | — | Second launch exits immediately with clean status; probe detects supervisor. |
| **durable_write** | Atomic file-publish helper: tempfile + fsync file + `os.replace` + fsync dir + 0600 mode. | new `utils/durable_write.py` | S | — | Unit test: simulate crash before replace (temp remains, target unchanged); verify atomic swap. |
| **process_group** | `start_new_session` + `killpg` tree escalation helper. | new `utils/process_group.py` | S | — | Unit test: child spawns background grandchild; group kill reaps both cleanly. |
| **activity_clock** | Monotonic activity tracker with idle detection and timeout gates. | new `utils/activity_clock.py` | S | — | Unit test: verify activity updates reset idle count; timer fires on inactivity. |
| **OTHER-P4** | Bounded-execution deadline helper (`deadline.py`). | new `utils/deadline.py` | S | — | Unit test: deadline expiry, cancellation token, clean exit. |
| **subprocess_env** | Child environment builder stripping credentials and API keys. | new `tools/subprocess_env.py` | S | — | Unit test: child environment verified free of all `*_API_TOKEN` / `*_KEY` strings. |
| **DIAG-02** | Read-only SQLite opener (`mode=ro`, `PRAGMA query_only=ON`). | new `utils/sqlite_safety.py` | M | — | Open production database read-only; assert writes throw `sqlite3.OperationalError`. |

---

### Milestone 1: Model Pipeline & Conversational Resilience
*Goal: Fix silent data-loss bugs, enable reliable local model tool execution, and eliminate UI freeze/hangs.*

| Packet | Scope & Deliverable | Files | Effort | Depends on | Verification |
|---|---|---|---|---|---|
| **SP-3** | Fix multi-tool dispatch data-loss bug in `state_machine.py` (drops all but first tool call). | `agents/state_machine.py` | S | — | Test: model emits two tool calls in one turn; assert both execute and return results. |
| **MP-5** | Local model tool-call repair: salvage markdown-wrapped JSON and strip conversational prefixes. | `model/client.py`, `agents/state_machine.py` | S-M | — | Test: feed raw ````json {"tool": ...}```` string; assert clean tool execution. |
| **MP-2** | Provider failure semantics: honor `Retry-After` up to 600s; replace bare `time.sleep` with interruptible backoff; split `BackendIdentity` health axes. | `model/rate_limiter.py`, `model/tier_router.py` | M | activity_clock | Test: `/stop` during backoff halts wait within 0.5s; 401 marks credential unhealthy, not DNS. |
| **MP-3** | Stream liveness: replace 120s total timeout with idle-gap detector (`sock_read`); foreign-thread abort hook. | `agents/llm_client.py`, `model/client.py` | M | activity_clock | Test: healthy stream running >120s completes; stopped stream terminates session in <0.5s. |
| **MP-4** | Measured context: anchor token counts to provider usage; route-keyed context cache; LM Studio loaded-state check. | `model/client.py`, `model/llm_config.py` | M | — | Test: local endpoint and remote endpoint with same model hold independent context limits. |
| **DAEMON-01b** | Stuck-turn reclamation watchdog: monitor turn-lock acquisition; auto-reclaim wedged locks. | `agents/state_machine.py` | M | activity_clock | Test: simulated wedged tool call triggers reclamation; conversation lock released cleanly. |

---

### Milestone 2: Watched Terminal & Sovereign Command Engine
*Goal: Transform user shell monitoring into a seamless, crash-proof, injection-proof environment.*

| Packet | Scope & Deliverable | Files | Effort | Depends on | Verification |
|---|---|---|---|---|---|
| **CSC-06** | Fix split-UTF-8 decoding corruption; PTY reattach loop on socket close; port announcement on stdout. | `streaming/pty.py`, `src-tauri/src/lib.rs` | S-M | — | Test: multi-byte CJK/emoji across read boundary decoded cleanly; drop socket, assert session reattaches. |
| **TT-01** | Shell executor hardening: process-group termination, PID+start-time fingerprint, redact-before-cap. | `tools/executor.py`, `streaming/agent_pool.py` | M | process_group, durable_write | Test: timeout kills process tree; planted secret across truncation boundary is fully redacted. |
| **TT-03** | Command normalization: de-obfuscate ANSI/IFS/quotes before classification; deny-list precedence. | `tools/command_norm.py`, `tools/safety.py` | S | text_hygiene | Test: `r\m -rf` and `rm${IFS}-rf` classify as HIGH; deny-list outranks all bypasses. |
| **TT-04a** | PTY reattach + foreground guardrails: nudge long-running servers (`npm run dev`) to background; progress labels. | `streaming/session_manager.py`, `tools/safety.py` | S-M | CSC-06 | Test: `npm run dev` yields foreground guidance; PTY session survives client restart. |
| **P2** | Approval bound to artifact: bind confirmation to `(device, inode, content_sha256)`, not raw path string. | `approval/engine.py` | S | durable_write | Test: approve file modification; modify file out of band; assert execution rejected. |
| **TERM-02** | Watched-terminal read/close tools with withdraw-not-refuse semantics. | `tools/terminal_tools.py` | S-M | TT-04a | Test: terminal tools withdrawn gracefully when no session is active. |

---

### Milestone 3: Memory Trust, Turn Provenance & Diagnostic Core
*Goal: Ensure the AI's memory is honest, partitioned, resilient to crashes, and verifiable.*

| Packet | Scope & Deliverable | Files | Effort | Depends on | Verification |
|---|---|---|---|---|---|
| **CH-A** | Turn cause axis (`InternalTurnSource` for scheduler, terminal events, hardware alarms); envelope hygiene. | `agents/channels.py`, `config/watcher.py` | M | text_hygiene | Test: scheduler turn admitted with honest provenance, zero user-chat claim; rapid file edits do not starve watcher. |
| **MEM-P1** | Read-side trust axis: add `origin_class` column; untrusted rows excluded from silent prompt injection. | `continuity/memory_v2.py`, `continuity/recall_gate.py` | M | — | Test: untrusted tool observation stored but never silently injected into psyche prompt. |
| **MEM-P2** | Product-boundary test: assert raw secrets in transcripts never survive into promoted memory. | `tests/test_redaction_product_boundary.py` | S | MEM-P1 | Test: secret embedded in turn transcript is scrubbed prior to memory promotion. |
| **MEM-P3** | SQLite durability: `PRAGMA integrity_check`; atomic online backup command; safe archive salvage. | `continuity/backup.py`, `tools/salvage.py` | M | durable_write, DIAG-02 | Test: `halbert backup` generates verified online backup; corrupted DB salvaged without overwriting live files. |
| **MEM-P6** | Compaction follows real numbers: persist provider `prompt_tokens` per thread; gate uses real counts. | `agents/assembler.py`, `agents/llm_client.py` | S | — | Test: compaction gate triggers based on actual provider usage, not character estimates. |
| **DIAG-01** | `halbert doctor` findings registry (`--json` and `GET /api/diagnostics`). | new `obs/doctor.py`, `dashboard/routes/diagnostics.py` | M | DIAG-02 | Test: `halbert doctor --json` outputs structured finding objects; findings register cleanly. |
| **LOG-01** | JSON rotating file logging with root redaction filter; redacted support bundle. | `obs/logging.py`, `dashboard/__main__.py` | M | text_hygiene | Test: log records formatted as valid JSON; secrets redacted before writing to disk. |

---

### Milestone 4: Grounded UI, Voice & Ambient Stewarding
*Goal: Elevate the dashboard and ambient interfaces to reflect live measured data without silent degradation.*

| Packet | Scope & Deliverable | Files | Effort | Depends on | Verification |
|---|---|---|---|---|---|
| **SURFACE-01a** | Approval expiry enforcement; stale-tone override (prevent false green/red); LTR trojan defense. | `approval/engine.py`, `Dashboard.tsx`, `ConfirmationDialog.tsx` | S | — | Test: expired approval rejected; stale poll data flagged; RTL Unicode override neutralized. |
| **SURFACE-01b** | Typed refresh policy (idle window halts polling); skills disable/enable page; jittered reconnect. | `usePolling.ts`, `SkillsSettings.tsx` | S-M | — | Test: idle dashboard reduces polling CPU to near-zero; disabled skill omitted from catalog. |
| **SCHED-P6** | Dashboard scheduled-work surface: wire list/history/cancel controls to live engine; webhook normalizer. | `ScheduledJobs.tsx`, `scheduler/executor.py` | S-M | — | Test: cancel button in UI cancels APScheduler job directly; webhook URLs normalized. |
| **OTHER-P6a & b** | Guarded `localStorage` accessor (prevent blank mount); hot-reload settings table. | `DebugContext.tsx`, `routes/settings.py` | S-M | — | Test: storage-disabled webview mounts cleanly; personality changes take effect without restart. |
| **VMV-1 & VMV-6** | Wake-word correctness on Apple Silicon ARM64; audio capability probes (`has_capability()`). | `voice/wake.py`, `routes/audio.py` | S-M | — | Test: wake-word resets cleanly on audio device reconnect; audio footprint bounded. |
| **VMV-3 & VMV-5** | Central media limits & MIME sniffing; coordinate mapping disclosure (scale/offset notes). | `routes/audio.py`, `tools/screen.py` | S-M | text_hygiene | Test: oversized base64 payload rejected; downscaled screenshot appends scale metadata. |

---

### Milestone 5: Upstream Harmonization & Founder Gates
*Goal: Integrate unmerged branches once landed and resolve strategic product boundaries.*

| Unit | Trigger / Gate | Action |
|---|---|---|
| **Sonnet Verification** | Merge of `fix/remediation-sonnet-batch-1` | Re-verify and wire: `R-03` (scheduler durability), `R-13` (locality everywhere), `R-15` (eval harness), `R-12 Phase A` (compaction session tree). |
| **MEM-P5** | Founder Decision F-3 (Curated Core & Memory Write Path) | Memory write approval staging; standing intents with deterministic cooldowns. |
| **SP-5 / SP-6** | Founder Decision SK-6 (Skills Write Path) | `/learn` and `/review` workflows; reserve slash-command names now. |
| **DIST-02** | Founder Decision FDR-04 / FDR-09 (Signing Identity) | Developer ID notarization, Hardened Runtime entitlements, and App Store packaging. |

---

## 6. Tactical Directives for the Next Dispatch Session

1. **Do Not Touch Product Code Before Milestone 0 Lands**:
   - The test suite must be made hermetic (`T1`) and the daemon protected from multi-instance collisions (`DAEMON-01a`) before any agent edits agent state machines or tool executors.
2. **Dispatch Milestones Sequentially; Parallelize Within Milestones**:
   - Units within Milestone 0 are file-disjoint and can run concurrently once `T1` is committed.
   - Milestone 1 (Model Pipeline) must precede Milestone 2 (Command Staging) so the state machine's multi-tool dispatch bug (`SP-3`) does not corrupt command execution testing.
3. **Always Run Tests with the `arch -arm64` Prefix**:
   ```bash
   arch -arm64 .venv/bin/python -m pytest halbert_core/tests
   ```
   Or from a git worktree:
   ```bash
   arch -arm64 ./wt_pytest.py halbert_core/tests
   ```
4. **Enforce Grounded First-Person Phrasing**:
   - Reject any model-generated error message that speaks as an assistant. Halbert is the computer itself.
