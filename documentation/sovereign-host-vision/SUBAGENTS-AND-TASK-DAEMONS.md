# Autonomous Host Subagents & Task Daemons

**Version:** 1.0.0  
**Date:** August 2026  
**Status:** Core Architectural Specification  
**Reads with:**
- [README.md](file:///Volumes/4TB-BAD/Halbert/documentation/sovereign-host-vision/README.md)
- [SOMATIC-BLOCKS-AND-NERVOUS-SYSTEM.md](file:///Volumes/4TB-BAD/Halbert/documentation/sovereign-host-vision/SOMATIC-BLOCKS-AND-NERVOUS-SYSTEM.md)
- [STREAMING-TERMINALS-AND-UI-ORCHESTRATION.md](file:///Volumes/4TB-BAD/Halbert/documentation/sovereign-host-vision/STREAMING-TERMINALS-AND-UI-ORCHESTRATION.md)

---

## 1. Overview: Subagents as Living Host Daemons

In standard coding agent frameworks, subagents are typically generic software developers (e.g., "Codebase Researcher", "Linter", "Test Writer").

In Halbert, subagents are **Autonomous Host Daemons and Organ Sub-Processes**. They represent specialized lobes of the host mind spawned to perform deep diagnostic passes, background audits, forensic traces, or long-running maintenance procedures without polluting or stalling the primary conversational mind spine.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     HALBERT SUBAGENT ORCHESTRATION                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│                     ┌─────────────────────────────┐                         │
│                     │   HALBERT PRIMARY MIND      │                         │
│                     │   (Haloysius advance_turn)  │                         │
│                     └──────────────┬──────────────┘                         │
│                                    │                                        │
│          Spawns Daemon /           │ Dispatches Task with Scoped Context    │
│          Subagent Worker           │                                        │
│                                    ▼                                        │
│          ┌───────────────────────────────────────────────────────┐          │
│          │             AUTONOMOUS HOST SUBAGENT POOL             │          │
│          ├───────────────────┬───────────────────┬───────────────┤          │
│          │ StorageAuditor    │ ConfigRefactor    │ IncidentTrace │          │
│          │ • SMART long tests│ • .d drop-in AST  │ • journald    │          │
│          │ • bcachefs scrub  │ • shadow analysis │ • cgroup logs │          │
│          │ • inode tracking  │ • lint & test     │ • OOM tree    │          │
│          └─────────┬─────────┴─────────┬─────────┴───────┬───────┘          │
│                    │                   │                 │                  │
│                    └───────────────────┼─────────────────┘                  │
│                                        ▼                                    │
│                    ┌───────────────────────────────────────┐                │
│                    │    DEDICATED PTY STREAM & TERMINAL    │                │
│                    │   (Flows in Chat -> Docks to Right)   │                │
│                    └───────────────────┬───────────────────┘                │
│                                        │                                    │
│                                        ▼                                    │
│                    ┌───────────────────────────────────────┐                │
│                    │    SQLITE FINDINGS & SOMATIC BLOCKS   │                │
│                    │ (Reports actionable items & whys)     │                │
│                    └───────────────────────────────────────┘                │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. The 5 Core Specialized Host Subagents

| Subagent Type | Specialized Focus | Tools & Subsystem Access | Typical Output |
|---|---|---|---|
| **`StorageAuditorAgent`** | Deep drive health, ZFS/bcachefs pool integrity, sector analysis, scrub orchestration. | `smartctl`, `zpool status -v`, `bcachefs fs show`, `lsblk -J`, `df -i` | Detailed pool topology map, drive degradation timeline, SMART self-test schedule. |
| **`ConfigRefactorAgent`** | Configuration drop-in deduplication, precedence resolution, AST diff synthesis. | SourcePrep `prep_search`, `write_config` (dry-run mode), `systemd-analyze verify`, `sshd -t` | Atomic proposal blocks, shadowed key reports, clean consolidated drop-in diffs. |
| **`IncidentInvestigatorAgent`** | Post-mortem root cause analysis following crashes, service failures, or kernel panics. | `journalctl`, `dmesg`, `/proc/kmsg`, `systemd-coredump`, cgroup memory telemetry | Fault tree diagram, timeline of resource exhaustion, proposed sysctl/cgroup fixes. |
| **`SecurityHardeningAgent`** | Network perimeter audit, listening sockets, sudoers permissions, SSH key validity. | `ss -tulpn`, `ufw status verbose`, `auditd`, `/etc/sudoers.d/`, Polkit rules | Security findings with Four Whys justifications, recommended firewall rules. |
| **`EphemeralTaskSubagent`** | Long-running procedures (compiling custom kernel modules, package upgrades, backups). | Direct isolated PTY session with streaming output and cancellation tokens. | Live streaming terminal block, exit code status, receipt summary. |

---

## 3. Subagent Execution & Lifecycle Protocol

### 3.1 Invocation Protocol
Subagents are spawned either **reactively** (in response to a user request) or **proactively** (triggered by an ambient sensor event or during the Morning Report sweep):

```python
# Conceptual Subagent Dispatch Contract
async def spawn_host_subagent(
    agent_type: str,            # e.g., "IncidentInvestigatorAgent"
    task_goal: str,             # e.g., "Investigate dockerd OOM kill at 02:41 UTC"
    scoped_sources: List[str],  # e.g., ["/var/log/journal", "/etc/docker/daemon.json"]
    model_tier: str = "fast",   # "fast" (Tier 1 local) or "cortex" (Tier 2 local/cloud)
    allocate_pty: bool = True   # Spawns dedicated interactive terminal tile
) -> SubagentHandle:
    ...
```

### 3.2 Context Isolation & Epistemic Scoping
To prevent context window bloat in the primary conversation:
1. **Isolated Context Buffer:** The subagent operates in its own execution context. It only reads the specific files and logs needed for its assigned goal.
2. **Deterministic Output Shape:** When the subagent completes its task, it does not dump hundreds of raw log lines back into the chat. Instead, it emits:
   - A structured **Somatic Block** (`Finding` or `Proposal`).
   - Grounded **Four Whys** metadata (with exact log cursors and file anchors).
   - An archived **Terminal Session Reference** that the user can expand on demand.

### 3.3 Reactive Non-Blocking Behavior
While a subagent runs in the background (e.g. running a 15-minute ZFS scrub or auditing 40 SSH drop-in files), the user can continue conversing with Halbert. The primary mind remains completely responsive:
> *User:* "What's the weather like today?"  
> *Halbert:* "It's 72°F and clear outside. Meanwhile, my `StorageAuditor` subagent is 40% through the storage scrub on `/dev/nvme0n1` (all checksums clean so far)."

---

## 4. UI & Terminal Interaction for Subagents

Every active subagent is paired with a **Live Streaming Terminal Tile**:
1. **Spawned Inline:** Appears as an interactive, collapsible terminal block in the left conversation stream.
2. **Auto-Docking:** If the user scrolls past the terminal or continues chatting, the subagent's terminal smoothly docks into the **Right-Column Accordion Dock**.
3. **Completion Receipt:** Once finished, the terminal folds into a compact badge: `[✓ StorageAuditor: Completed in 4m 12s | 0 Errors]`. Clicking the badge re-opens the terminal output with full ANSI color and scrollback.
