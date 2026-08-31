# Review Packet 04: Sovereign Host Vision & Continuous Terminal / Somatic Nervous System

**Review Level:** **GLM-5.3 (reassigned 2026-08-30 — see MASTER-REVIEW-INDEX § 2 for effort tier and batch)**  
**Domain:** Operating System Primitives, Headless PTY Terminals, Somatic Context Blocks, Agent State Machines, and Cross-Session Continuity  
**Target Date:** 2026-08-29  
**Status:** Ready for Deep Systems & Concurrency Review  

---

## 1. Executive Summary & Review Scope

The "Sovereign Host Vision" represents the evolution of Halbert into an autonomous, self-aware operating system nervous system. Under this paradigm, the AI agent does not simply run batch commands; it maintains continuous awareness of host execution, monitors interactive terminal sessions, ingests structured somatic blocks, and preserves cross-session cognitive continuity.

Between 2026-08-24 and 2026-08-28, a major architectural leap was realized:
1. **The Sovereign Host Blueprint Suite:** 12 foundational specification documents detailing continuous session orchestration, subagent daemons, somatic blocks, and cross-codebase pattern inventories.
2. **Terminal Pool & Watched Shell (Plan B Terminals):** Async PTY manager (`TerminalPool` & `WatchedShell`) enabling the agent to spawn, observe, interrupt, and interact with long-running CLI tasks without blocking the web event loop.
3. **Block-Typed Conversation History (A1) & State Machine (A2a):** Migration from raw text strings to structured `MessageBlock` objects and formalizing the `ConversationStatus` lifecycle.
4. **Cross-Session Continuity (R2–R9):** Implementation of date-stamped receipts, open loops tracking, state-at-close persistence, domain-scoped recall, and memory consolidation fences.

The reviewing model (**GLM-5.3**) must review the async PTY lifecycle, inspect potential file-descriptor leaks, audit state-machine transitions under error conditions, and verify memory consolidation bounds.

---

## 2. Planning & Design Documents (Past 2 Weeks)

| Document | Purpose | Key Themes |
|---|---|---|
| [`documentation/sovereign-host-vision/README.md`](file:///Volumes/4TB-BAD/Halbert/documentation/sovereign-host-vision/README.md) | Index to the 12 Sovereign Host Blueprints | Nervous system vision, subagent daemons, terminal orchestration |
| [`documentation/sovereign-host-vision/CONTINUOUS-ORCHESTRATOR-AND-SESSION-ENGINE.md`](file:///Volumes/4TB-BAD/Halbert/documentation/sovereign-host-vision/CONTINUOUS-ORCHESTRATOR-AND-SESSION-ENGINE.md) | Continuous session architecture | Lifecycle hooks, session resumption, background task pools |
| [`documentation/sovereign-host-vision/SOMATIC-BLOCKS-AND-NERVOUS-SYSTEM.md`](file:///Volumes/4TB-BAD/Halbert/documentation/sovereign-host-vision/SOMATIC-BLOCKS-AND-NERVOUS-SYSTEM.md) | Somatic telemetry representation | Structural event schemas, system sensory streams |
| [`.handoff/CONTINUOUS-CONVERSATION-PLAN-B-2026-08-27.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/CONTINUOUS-CONVERSATION-PLAN-B-2026-08-27.md) | Terminal Pool & watched shells plan | Async PTY allocation, ANSI stripping, stream buffers |
| [`.handoff/TERMINAL-AND-ORCHESTRATOR-REVIEW-2026-08-26.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/TERMINAL-AND-ORCHESTRATOR-REVIEW-2026-08-26.md) | Deep scrutiny & architectural review | Concurrency limits, signal trapping (`SIGINT`/`SIGTERM`), memory limits |
| [`documentation/research/CROSS-SESSION-CONTINUITY-RESEARCH-2026-08-26.md`](file:///Volumes/4TB-BAD/Halbert/documentation/research/CROSS-SESSION-CONTINUITY-RESEARCH-2026-08-26.md) | Cognitive continuity strategies | Episodic memory decay, working context reconstruction |

---

## 3. Git History & Code Commits (Past Week: Aug 22 – Aug 29)

| Commit | Date | Summary | Key Files Changed |
|---|---|---|---|
| `c691ddd3` | 2026-08-24 | Add Halbert 2.0 Sovereign Host Vision blueprints and feasibility architecture | `documentation/sovereign-host-vision/*` |
| `531007be` | 2026-08-25 | Docs: add codebase reality checks to sovereign-host-vision blueprints | `documentation/sovereign-host-vision/*` |
| `602ef24b` | 2026-08-25 | Test: activate pytest-asyncio for 18 previously-skipped async tests | `tests/test_async_agents.py` |
| `0b35a7e4` | 2026-08-25 | Refactor: unify `StreamEvent` into `agents.events` (A0b) | `agents/events.py`, `dashboard/routes/agent.py` |
| `6d11a1b5` | 2026-08-25 | Feat(agents): block-typed conversation history (A1) | `conversation/history.py`, `conversation/blocks.py` |
| `6d1ca5d0` | 2026-08-25 | Feat(agents): ConversationStatus enum + state machine (A2a) | `agents/state_machine.py`, `agents/states.py` |
| `1e29cf43` | 2026-08-28 | Test(agents): end-to-end terminal integration — pool, watched shell, blocks | `agents/terminal_pool.py`, `agents/watched_shell.py` |
| `0ba316b2` | 2026-08-28 | Merge branch `feat/plan-b-terminals` into main | Merge commit |
| `2ea971e8` | 2026-08-28 | Continuity: R2-R9 — receipts, open loops, state at close, domain recall | `memory/continuity.py`, `memory/fences.py` |
| `3f438204` | 2026-08-28 | Continuity fixes: wire call sites, adopt margin gate, harden fences | `memory/hybrid.py`, `agents/state_machine.py` |

---

## 4. Key Files & Architectural Components

- **Terminal Pool & Shell Primitives:**
  - [`halbert_core/halbert_core/agents/terminal_pool.py`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/agents/terminal_pool.py)
  - [`halbert_core/halbert_core/agents/watched_shell.py`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/agents/watched_shell.py)
- **Agent State Machine & Events:**
  - [`halbert_core/halbert_core/agents/state_machine.py`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/agents/state_machine.py)
  - [`halbert_core/halbert_core/agents/events.py`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/agents/events.py)
  - [`halbert_core/halbert_core/conversation/history.py`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/conversation/history.py)
- **Continuity & Memory Fencing:**
  - [`halbert_core/halbert_core/memory/continuity.py`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/memory/continuity.py)
  - [`halbert_core/halbert_core/memory/fences.py`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/memory/fences.py)

---

## 5. Incomplete Work & Open Items

1. **PTY Stream Backpressure:** Audit ring buffer behavior in `watched_shell.py` when an executed process emits massive output (e.g. `cat /dev/urandom` or heavy compiler output) to ensure memory ceiling is strictly enforced.
2. **Frontend Virtualized Terminal Renderer:** Connect raw terminal block events over SSE to a virtualized xterm.js or ANSI-aware React component in the web UI.
3. **Daemon Reboot Recovery:** Ensure background task records in SQLite cleanly mark interrupted tasks as `ABORTED_ON_RESTART` when the daemon re-initializes.

---

## 6. Review Directives for Fable

- **Process Isolation & Signal Safety:** Trace process termination paths in `terminal_pool.py` to ensure children receive `SIGTERM` followed by graceful `SIGKILL` escalations with no zombie processes left in `ps`.
- **State Machine Deadlock Analysis:** Audit `agents/state_machine.py` for any unhandled async exceptions in intermediate states (`REFLECTING`, `TOOL_EXECUTION`, `STREAMING`) that could leave conversations stuck in non-terminal states.
- **Verification Command:** Run `pytest halbert_core/tests/test_terminal_pool.py halbert_core/tests/test_watched_shell.py halbert_core/tests/test_continuity.py -v`.
