# Somatic Blocks & The Biological Nervous System

**Version:** 1.0.0  
**Date:** August 2026  
**Status:** Core Architectural Specification  
**Reads with:**
- [README.md](file:///Volumes/4TB-BAD/Halbert/documentation/sovereign-host-vision/README.md)
- [SUBAGENTS-AND-TASK-DAEMONS.md](file:///Volumes/4TB-BAD/Halbert/documentation/sovereign-host-vision/SUBAGENTS-AND-TASK-DAEMONS.md)
- [STREAMING-TERMINALS-AND-UI-ORCHESTRATION.md](file:///Volumes/4TB-BAD/Halbert/documentation/sovereign-host-vision/STREAMING-TERMINALS-AND-UI-ORCHESTRATION.md)

---

## 1. The Concept: Beyond Chat Bubbles & Shell Buffers

Traditional terminal emulators (like iTerm or standard xterm) treat execution as a continuous, unparsed byte stream. **Warp** pioneered the **Block Paradigm**, grouping each command and its output into a discrete visual and logical unit. **Claude Code** adapted this into agentic conversation turns with folding tool calls and linter outputs.

In Halbert, we elevate this concept into **Computational Biology**:
An event inside the host is not just a bash command or a text query; it is a **Somatic Impulse** traversing the host's nervous system.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       THE SOMATIC IMPULSE LIFECYCLE                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   [ 1. SENSORY BLOCK ] ────▶ [ 2. DELIBERATION BLOCK ] ────▶ [ 3. PROPOSAL ]│
│   • inotify write event      • Haloysius Cognitive Tick       • AST Diff    │
│   • Kernel OOM / dmesg       • SourcePrep Blast-Radius        • Dry-Run     │
│   • Hardware Sensor Event    • Law of Four Whys Validation    • Rollback ID │
│                                                                      │      │
│                                                                      ▼      │
│   [ 5. REFLECTION BLOCK ] ◀── [ 4. VERIFICATION BLOCK ] ◀── [ APPROVE ]     │
│   • SourcePrep Concept        • Polkit Helper Execution                     │
│   • Living Muscle Memory      • Post-Apply Health Probe (`sshd -t`)         │
│   • Biographical Memory       • Automated 250ms Rollback (if failed)        │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Anatomy of the 5 Somatic Blocks

### 2.1 Sensory Block (`SomaticSensory`)
Captures raw, ambient perceptions from the underlying operating environment.
* **Payload:** Subsystem type (`filesystem`, `thermal`, `service`, `kernel`), raw event cursor, severity score, and timestamp.
* **Example:** `inotify` triggered when an unmanaged edit touches `/etc/sysctl.d/99-custom.conf`.

### 2.2 Deliberation Block (`SomaticDeliberation`)
Represents the internal cognitive synthesis performed by Haloysius and SourcePrep.
* **Payload:** The Four Whys evaluation:
  * **Why Now:** Immediate trigger conditions.
  * **Why Care:** Consequence and failure mode if left unaddressed.
  * **Why So:** Historical context and past user intentions.
  * **Why Trust:** Exact file anchors, log hash cursors, and man-page documentation citations.
* **Visual Presentation:** Foldable cognitive tree with expandable provenance chips (`WhyChips`).

### 2.3 Proposal Block (`SomaticProposal`)
A deterministic, atomic plan for state modification.
* **Payload:** AST diff of target configuration, service state transition matrix, blast-radius score ($0.0 \rightarrow 1.0$), and pre-allocated rollback snapshot ID.
* **Affordances:** `[Approve & Apply (Polkit)]`, `[Dry-Run Test]`, `[Snooze...]`, `[Mark as Intentional]`.

### 2.4 Action & Verification Block (`SomaticAction`)
The execution trace executed via the privileged setuid/polkit helper (`halbert-exec`).
* **Payload:** PTY command stream, exit code, execution duration, and post-apply health check result (e.g. `sshd -t` or `mount -a`).
* **Safety Mechanism:** If verification fails, the system executes an automated rollback within 250ms and marks the block as `AUTO_RESTORED`.

### 2.5 Reflection Block (`SomaticReflection`)
The autobiographical memory consolidation step.
* **Payload:** SourcePrep concept creation/invalidation, `memory_v2` turn recording, and optional synthesis into a **Living Reflex**.

---

## 3. Biological Model Allocation (The 4-Tier Hierarchy)

To eliminate latency, avoid excessive cloud API costs, and guarantee local-first privacy, Halbert structures its model compute like the human nervous system:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      BIOLOGICAL COMPUTE HIERARCHY                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │ TIER 0: SPINAL REFLEXES (0ms Latency | 0 LLM Tokens)                │   │
│   │ • inotify watchers, SQLite finding detectors, AST parsers           │   │
│   │ • MemoryLOD rule-based compression, regex semantic filters          │   │
│   └──────────────────────────────────┬──────────────────────────────────┘   │
│                                      │ (Elevates on Pattern Match)          │
│                                      ▼                                      │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │ TIER 1: BRAINSTEM & CEREBELLUM (Local Fast Model | <250ms)          │   │
│   │ • Small local model (3B–7B) / Apple Silicon MLX 4-bit               │   │
│   │ • Intent routing, command syntax generation, host autocompletion    │   │
│   │ • WhyChip citation extraction & live conversational banter          │   │
│   └──────────────────────────────────┬──────────────────────────────────┘   │
│                                      │ (Elevates on High Complexity)        │
│                                      ▼                                      │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │ TIER 2: CEREBRAL CORTEX (Specialist Model | Local 24B/70B or Cloud) │   │
│   │ • Deep fault tree analysis (e.g. OOM killer cascade post-mortem)    │   │
│   │ • Multi-file AST refactoring, ZFS layout restructuring               │   │
│   │ • SourcePrep prep_impact simulation & multi-step execution plans    │   │
│   └──────────────────────────────────┬──────────────────────────────────┘   │
│                                      │ (Asynchronous Idle Trigger)          │
│                                      ▼                                      │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │ TIER 3: THE SUBCONSCIOUS ("Dream Cycle" | Overnight Consolidation)  │   │
│   │ • Scheduled 03:00 background maintenance & memory consolidation     │   │
│   │ • Synthesis of Living Reflexes & Morning Report generation          │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Living Reflexes & Host Muscle Memory

### 4.1 From Static Workflows to Dynamic Host Reflexes
* **Warp Drive** uses static, user-written markdown files with placeholder syntax.
* **Halbert Living Reflexes** are self-synthesized, executable behavioral units generated from real troubleshooting interactions between Halbert and the user.

### 4.2 Reflex Schema (`~/.config/halbert/reflexes/{reflex_id}.yml`)
```yaml
id: reflex_zfs_arc_backup_throttle
name: "Throttle ZFS ARC During Large Tar Backups"
created_at: "2026-08-24T03:30:00Z"
trigger_signature:
  telemetry:
    memory_usage_pct: "> 90"
    active_process_regex: "tar|rsync|borg"
    zfs_arc_size_gb: "> 20"
blast_radius_score: 0.2
actions:
  - name: "Cap ARC Max"
    command: "echo 17179869184 > /sys/module/zfs/parameters/zfs_arc_max"
    elevation_required: true
    verification_probe: "cat /sys/module/zfs/parameters/zfs_arc_max"
  - name: "Drop pagecache gently"
    command: "sync; echo 1 > /proc/sys/vm/drop_caches"
    elevation_required: true
rollback:
  command: "echo 0 > /sys/module/zfs/parameters/zfs_arc_max"
rationale: "Prevents Linux OOM-killer from terminating dockerd during backup bursts."
provenance:
  incident_id: "inc_01J5K89"
  sourceprep_concept_id: "c_arc_throttle_01"
```

### 4.3 Autonomous Recognition
When identical stress patterns occur in the future, Halbert's Tier 0/1 sensory loops detect the signature and proactively suggest:
> *"I notice our backup process is consuming 92% RAM with ZFS ARC at 22GB. This matches our `zfs_arc_backup_throttle` reflex. Shall I engage the throttle?"*

---

## 5. Codebase Reality Check (August 2026 Audit)

### 5.1 The Somatic Block Lifecycle Does Not Exist Yet — But Its Pieces Do

A grep for `somatic`/`Somatic` across `halbert_core/` returns **zero matches**. There is no `SomaticBlock` dataclass, no lifecycle state machine, and no unifying orchestrator. However, the five blocks map to existing modules that were built independently and can be glued together:

| Somatic Block | Existing Code | What's Missing |
|---|---|---|
| **Sensory** (`SomaticSensory`) | `proactive/detector_runner.py`, `discovery/` event sources, `autonomy/anomaly_detector.py` | No unified `SomaticSensory` payload schema; events aren't typed as somatic impulses |
| **Deliberation** (`SomaticDeliberation`) | `agents/state_machine.py` REFLECTING state runs Haloysius cognitive tick (line 733); `findings/blast_radius.py` computes impact | No Four Whys structured output; no foldable cognitive tree; no `WhyChips` UI |
| **Proposal** (`SomaticProposal`) | `findings/proposals.py` (302 lines, `Proposal` dataclass with PENDING/APPROVED/REJECTED/APPLIED/ROLLED_BACK); `findings/precedence.py` (353 lines, real AST-level sshd/systemd precedence resolution); `approval/simulator.py` (380 lines, `SimulationResult` with before/after/diffs) | Not unified under a `SomaticProposal` name; no `[Approve & Apply]`/`[Dry-Run]`/`[Snooze]` affordance wiring |
| **Action & Verification** (`SomaticAction`) | `approval/engine.py` (417 lines, `ApprovalRequest` lifecycle); `autonomy/recovery.py` (307 lines, `RecoveryAction.ROLLBACK`); `autonomy/guardrails.py` (292 lines, confidence thresholds) | No PTY command stream (backend is `subprocess.run()`); no post-apply health probe automation (`sshd -t`, `mount -a`); no 250ms automated rollback trigger |
| **Reflection** (`SomaticReflection`) | `proactive/morning_report.py` (225 lines); `context/assembler.py` `_compress_with_cascade()` | No SourcePrep concept auto-creation from resolved incidents; no Living Reflex synthesis |

### 5.2 The 250ms Rollback Claim Is Aspirational

The spec says *"the system executes an automated rollback within 250ms."* This is physically impossible to guarantee for arbitrary config changes:
- **Single-file changes** (e.g. one `sysctl.d/` drop-in): achievable in ~1-5 seconds with `cp` + service reload.
- **Multi-file changes** (e.g. systemd unit refactor + `daemon-reload` + service restart): cannot be atomic; requires manual confirmation.

**Revised guarantee:** Best-effort rollback within 1-5 seconds for single-file changes. Multi-file changes require explicit user confirmation before apply and use a staged rollback (reverse the diff, reload, re-verify).

### 5.3 Living Reflexes Do Not Exist

Zero `reflex`/`Reflex` matches in `halbert_core/`. The `reflexes/{reflex_id}.yml` schema, trigger signature matching, and self-synthesis loop are pure spec. The closest existing module is `modules/registry.py` (128 lines), which is a generic module registry, not reflex-shaped.

**Build path:** Once the Reflection block (§5.1) is unified, add a `reflexes/` YAML store that the Reflection block writes to. Trigger matching can be a simple regex/telemetry signature match in Tier 0 — no LLM needed for recognition.

### 5.4 Biological Model Tiering — Mostly Built

The 4-tier hierarchy (§3) maps to existing code:
- **Tier 0 (Spinal Reflexes):** `intake/signals.py` — zero-LLM signal detection (<1ms), regex intent extraction
- **Tier 1 (Brainstem):** `intake/budget.py` + `model/client.py` — model-tier detection routes to local fast models
- **Tier 2 (Cerebral Cortex):** `model/client.py` routing to specialist/cloud models
- **Tier 3 (Subconscious/Dream Cycle):** `proactive/morning_report.py` exists but is not scheduled at 03:00; must be opt-in

### 5.5 Stage 1 Build Estimate

Unifying the existing scattered modules under a `SomaticBlock` lifecycle dataclass + state machine is approximately **200-300 lines of glue code**. The underlying capabilities (blast-radius, precedence resolution, dry-run simulation, approval gating, rollback) already work — they just need a common lifecycle wrapper and naming convention.
