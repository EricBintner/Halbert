# Master Architectural Specification: Sentient Computing, Cognitive OS & Pragmatic Blue-Sky Evolution

**Document Status:** Consolidated Master Specification & Architectural Review Packet  
**Date:** 2026-09-01  
**Target Systems:** Halbert Desktop (Tauri/React), Halbert Core (Python 3.12), Halbert Daemon (`halbertd`), Cross-Platform (macOS, Windows 11, Linux/HalbertOS)  
**Document Purpose:** Unified consolidation of the initial Blue-Sky Vision, Second-Pass Pragmatic Refinements, and Third-Pass Critical Scrutiny into a single cohesive reference for external and subagent architectural review.

---

## 1. Executive Summary & The Evolution Trajectory

This document consolidates the complete architectural thought trajectory of Halbert's long-term **Sentient Computing & Cognitive OS** roadmap across three iterative passes:

```
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│                               THE THREE-STAGE EVOLUTION                                     │
├─────────────────────────┬───────────────────────────┬───────────────────────────────────────┤
│ Stage 1: Blue-Sky Vision│ Stage 2: Pragmatic Reality│ Stage 3: Critical Scrutiny Mitigation │
├─────────────────────────┼───────────────────────────┼───────────────────────────────────────┤
│ **1. Somatosensory /    │ **Nightly Brain Sync &    │ • Hard AC-power + Clamshell gating    │
│    REM Sleep**          │ Idle Maintenance**        │ • Zero-token deterministic heuristics │
│                         │ (Universal across OSs)    │ • SQLite WAL concurrency locks        │
├─────────────────────────┼───────────────────────────┼───────────────────────────────────────┤
│ **2. Synthetic VFS      │ **Safe State Directory &  │ • Reject FUSE (eliminates D-state lock│
│    (`/halbert` mount)** │ Non-Blocking UDS Stream** │ • Atomic 0600 file permissions        │
│                         │ (No brittle FUSE drivers) │ • Expiration headers & cached TTLs    │
├─────────────────────────┼───────────────────────────┼───────────────────────────────────────┤
│ **3. Kernel Reflex Arc  │ **Hardware Sentry & Fast  │ • Fallback to userspace 100Hz worker  │
│    (eBPF Reflexes)**    │ Event Interceptor**       │   (bypasses Apple entitlement lock)   │
│                         │ (Platform-native sentry)  │ • Strict "Renice only, never SIGKILL" │
├─────────────────────────┼───────────────────────────┼───────────────────────────────────────┤
│ **4. Neural Fabric      │ **Adaptive Model Router** │ • Standard CoreML / DirectML runtimes │
│    (Tiered Inference)** │ (Apple ANE, Win NPU, Metal│ • 10-minute idle VRAM auto-eviction   │
│                         │ & Cloud frontier models)  │ • OS Memory Pressure drop listeners   │
├─────────────────────────┼───────────────────────────┼───────────────────────────────────────┤
│ **5. Soul Migration /   │ **Encrypted Personal      │ • Zero-cost user iCloud / GDrive path │
│    Holographic Soul**   │ Cloud Backup & Restore**  │ • Device-tagged sharding & WAL deltas │
│                         │ (User-owned storage)      │ • OS Keychain & BIP-39 recovery kit   │
└─────────────────────────┴───────────────────────────┴───────────────────────────────────────┘
```

---

## 2. Pillar 1: Nightly Brain Sync & Idle Maintenance

### 2.1 Concept & Value
Rather than running expensive memory indexing and hygiene tasks during active user interaction, Halbert schedules an autonomous **Idle Maintenance Cycle** during off-hours (typically 2:00 AM – 4:00 AM) or extended idle states.

### 2.2 Operational Components
1. **Autobiography Defragmentation:** Compresses multi-turn conversations into concise summary nodes, indexes them in vector storage, and vacuums SQLite tables.
2. **Contradiction Resolution:** Prunes duplicate/outdated facts in the memory graph (e.g. updating changed user preferences).
3. **Proactive Sanity Audit:** Runs `prep_audit` to detect broken shell symlinks, orphaned dotfiles, or deprecated environment variables.
4. **Morning Briefing Card:** Prepares a crisp summary card: *"Good morning! Overnight I cleaned up 12 orphaned configs and indexed your active project branch."*

### 2.3 Critical Scrutiny & Hard Constraints
* **The Backpack Overheating Hazard:** On modern laptops (macOS DarkWake or Windows Modern Standby S0ix), running heavy vector embeddings inside a closed laptop bag will drain the battery and cause thermal runaway.
  ```python
  def should_run_nightly_maintenance() -> bool:
      if not power_manager.is_ac_connected():
          return False  # NEVER run on battery
      if power_manager.is_lid_closed_and_not_docked():
          return False  # Prevent closed-bag overheating
      if idle_tracker.idle_duration_minutes() < 30:
          return False  # Ensure user is actively away
      return True
  ```
* **Preventing Silent Cloud API Cost Runaway:**
  * Routine hygiene and deduplication use **deterministic string/regex heuristics (0 LLM tokens)**.
  * Semantic dialogue summarization only triggers if **>50 new conversational turns** occurred since the last run.
  * Prefers local Tier 2 models (MLX/Ollama) over cloud models.
* **SQLite Concurrency:** Uses SQLite **WAL mode** with explicit `busy_timeout = 5000ms` to prevent `SQLITE_BUSY` lock contention with background daemons.

---

## 3. Pillar 2: Safe State Directory & IPC Interface (No FUSE)

### 3.1 Why Synthetic FUSE Mounts Were Rejected
The initial vision proposed mounting a synthetic virtual filesystem at `/halbert`. Scrutiny revealed severe production blockers:
1. **D-State Kernel Hangs:** If the user-space daemon crashes or blocks while handling a FUSE syscall, any shell executing `ls /halbert` or `find /` freezes in an unkillable D-state.
2. **Third-Party Kext Friction:** macOS requires `macFUSE` (triggering severe Apple security warnings); Windows requires `WinFsp` or `Dokany`.
3. **Security Vulnerability:** Mutating system state via `echo "..." > /halbert/actions/...` allows unauthenticated local scripts to trigger agent actions without consent.

### 3.2 The Production-Grade Replacement Architecture
We employ a decoupled dual-interface:

```
                               SAFE IPC TOPOLOGY
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│ 1. Atomic State Directory (`~/.local/state/halbert/` or `/run/user/$UID/halbert/`)          │
│    • Read-only JSON/Markdown state files written atomically via tempfile rename.            │
│    • Strict POSIX permissions: Directory `0700`, Files `0600`.                              │
│    • Stamped with TTL headers: `<!-- Generated: 2026-09-01T09:30:00Z | TTL: 300s -->`      │
│    • Allows `cat ~/.local/state/halbert/diagnosis.md | grep "error"` with 0% crash risk.    │
├─────────────────────────────────────────────────────────────────────────────────────────────┤
│ 2. Non-Blocking Unix Domain Socket (UDS) / Named Pipe (`/var/run/halbert.sock`)             │
│    • Live queries and mutating actions require authenticated JSON-RPC / MCP protocol.       │
│    • CLI wrapper: `halbert status`, `halbert eval "cmd"`, `halbert memory search "..."`.     │
└─────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Pillar 3: Hardware Sentry & Fast Event Interceptor

### 4.1 Concept & Latency Architecture
AI agents are notoriously slow (500ms–3000ms token generation). The **Hardware Sentry** acts as the system's "spinal reflex arc": a lightweight, deterministic pre-filter executing in **< 1 millisecond** to protect the host before the LLM wakes up.

```
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│                               FAST SENTRY VS. COGNITIVE PATH                                │
├─────────────────────────────────────────────────────────────────────────────────────────────┤
│ FAST PATH (< 1ms, Rust Sentry Thread, Zero LLM Tokens)                                      │
│ • Detects CPU starvation, runaway processes, socket floods, or disk exhaustion.             │
│ • Deterministic action: Throttles cgroup weight, drops network socket, or issues renice.    │
├─────────────────────────────────────────────────────────────────────────────────────────────┤
│ SLOW PATH (500ms – 2000ms, LLM Cognitive Analysis)                                         │
│ • Sentry queues incident report in the agent's sensory ring buffer.                          │
│ • LLM calmly generates diagnostic explanation and presents user with interactive remedy.   │
└─────────────────────────────────────────────────────────────────────────────────────────────┘
```

### 4.2 Cross-Platform Sentry Matrix & Apple Entitlement Reality
* **Apple EndpointSecurity Roadblock:** Apple restricts `com.apple.developer.endpoint-security.client` to enterprise security vendors. 
* **Production Implementation:**
  * **macOS:** Standard `FSEvents` (file changes) + `libproc` (`proc_pidinfo`) + `IOKit` + `sysctl` in a 100Hz Rust thread (zero special entitlements required).
  * **Windows:** Event Tracing for Windows (`ETW`) + Windows Job Objects.
  * **Linux:** `eBPF` tracepoints & Landlock security modules.
* **The "No False-Positive SIGKILL" Rule:**
  > **The fast sentry may THROTTLE (renice / cgroup weight down) or ALERT, but NEVER TERMINATE (SIGKILL/SIGSTOP) without interactive user confirmation.**

---

## 5. Pillar 4: Adaptive Model Router (Heterogeneous Inference)

### 5.1 Multi-Tiered Hardware Acceleration
Halbert orchestrates a multi-tier neural fabric mapping specific cognitive workloads to optimal local hardware:

```
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│                                 ADAPTIVE INFERENCE TIERS                                    │
├───────────────┬──────────────────────────┬─────────────────────────────┬────────────────────┤
│ Tier          │ Hardware Engine          │ Model Scale & Quantization  │ Primary Role       │
├───────────────┼──────────────────────────┼─────────────────────────────┼────────────────────┤
│ **Tier 1**    │ Apple Neural Engine (ANE)│ 0.5B – 1.5B (INT4 / CoreML) │ Voice VAD, Audio   │
│ < 50ms, < 2W  │ Windows DirectML / NPU   │ ONNX Runtime / SmolLM       │ Barge-in, Keywords │
├───────────────┼──────────────────────────┼─────────────────────────────┼────────────────────┤
│ **Tier 2**    │ Metal Unified Memory /   │ 7B – 14B Q4_K_M             │ Sysadmin Diffs,    │
│ 200ms – 600ms │ NVIDIA / AMD Local GPU   │ Qwen 2.5 Coder / Llama 3.3  │ CRAG Gating, Tools │
├───────────────┼──────────────────────────┼─────────────────────────────┼────────────────────┤
│ **Tier 3**    │ Frontier Cloud API       │ Claude 3.7 Sonnet / Opus /  │ Deep Architectural │
│ High Compute  │ (HTTPS / Tailscale Mesh) │ GPT-4o / DeepSeek R1        │ Synthesis & Coding │
└───────────────┴──────────────────────────┴─────────────────────────────┴────────────────────┘
```

### 5.2 Memory Management & Creative App Conflict Mitigation
* **10-Minute Auto-Eviction:** Model weights are automatically purged from VRAM/Unified Memory after 10 minutes of inactivity.
* **OS Memory Pressure Hooks:** Halbert listens to native OS memory pressure signals (`DISPATCH_SOURCE_TYPE_MEMORYPRESSURE` on macOS, `cgroup memory.pressure` on Linux) and immediately drops cached model weights if the user opens a memory-heavy creative app (Blender, DaVinci Resolve, Xcode).

---

## 6. Pillar 5: Encrypted Personal Cloud Vault (Zero-Cost Sync)

### 6.1 Zero-Hosting Cost Architecture
We do not host or operate a multi-tenant cloud storage backend. Users leverage storage they already own:

```
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│                               ZERO-KNOWLEDGE BACKUP VAULT                                   │
└─────────────────────────────────────────────────────────────────────────────────────────────┘

  Local Halbert State
  ├── 1. Memory Graph (SQLite conversation store & vector embeddings)
  ├── 2. Identity Config (`being.yml` & custom personas)
  └── 3. Machine Scans & Preferences
                 │
                 ▼
  [Client-Side Encryption Engine] (AES-256-GCM / libsodium with master passphrase)
                 │
                 ▼
  `vault-<device_id>-<epoch_timestamp>.enc`
                 │
                 ├──► macOS: `~/Library/Mobile Documents/com~apple~CloudDocs/Halbert/` (iCloud)
                 ├──► Windows / Linux: Google Drive / OneDrive folder or local NAS path
                 └──► Standalone: Manual export / import file picker
```

### 6.2 Scrutiny Mitigations: Sync Conflicts & Bandwidth Bloat
1. **Device-Tagged Sharding:** Each paired device writes its own timestamped snapshot (`vault-<device_id>-<timestamp>.enc`), completely eliminating Google Drive/iCloud conflicted copy overwrites (`vault (1).enc`).
2. **Delta WAL Diffing:** Daily syncs only upload incremental SQLite WAL deltas (< 2MB) rather than re-encrypting the entire multi-gigabyte historical database.
3. **Emergency Key Recovery:** Derived encryption keys are stored in native OS secure stores (**Apple Keychain**, **Windows Credential Manager**, **Linux Secret Service**), with an optional **12-Word BIP-39 Recovery Phrase** generated at setup.

---

## 7. Cross-Platform Implementation Matrix

| Subsystem | Linux / HalbertOS | macOS Tahoe / Apple Silicon | Windows 11 / Copilot+ PC | Tauri Desktop App (Today) |
| :--- | :--- | :--- | :--- | :--- |
| **Nightly Maintenance** | `systemd.timer` on AC | `NSBackgroundActivityScheduler` | Task Scheduler on AC/Idle | In-app AC/Idle timer |
| **State Inspection** | `/run/user/$UID/halbert/` | `~/.local/state/halbert/` | `%LOCALAPPDATA%\halbert\` | `~/.local/state/halbert/` |
| **Fast Sentry** | `eBPF` + Landlock | `FSEvents` + `libproc` | `ETW` + Job Objects | 100Hz Rust worker thread |
| **Tier 1 Inference** | `llama.cpp` CPU/NPU | Apple Neural Engine (CoreML) | Qualcomm/Intel DirectML NPU | Modular slot in `models.yml` |
| **Cloud Backup** | Local NAS / GDrive folder | iCloud Drive (`CloudDocs`) | OneDrive / GDrive folder | Native file export / import |

---

## 8. Review Directives for External Reviewers

When conducting a critical evaluation of this specification, please address the following specific questions:

1. **Pillar 1 (Nightly Maintenance):** Is the 30-minute idle + AC power pre-flight gate sufficient to guarantee zero laptop bag overheating across all OEM sleep implementations?
2. **Pillar 2 (Safe State Directory):** Does replacing FUSE with atomic JSON/Markdown state files and a UDS stream provide 100% of the desired CLI developer ergonomics without edge cases?
3. **Pillar 3 (Hardware Sentry):** Is the userspace 100Hz `libproc`/`FSEvents` polling loop on macOS lightweight enough to keep CPU consumption < 0.2% on idle?
4. **Pillar 4 (Adaptive Router):** Are there specific quantization or memory-pinning pitfalls with CoreML / DirectML NPU execution that should be gated behind opt-in flags?
5. **Pillar 5 (Cloud Backup Vault):** Does the device-tagged delta sharding strategy adequately handle a scenario where a user replaces a device and needs to reconstruct canonical memory from multiple shards?
