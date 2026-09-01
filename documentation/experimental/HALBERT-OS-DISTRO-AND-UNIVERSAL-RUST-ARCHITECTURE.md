# HalbertOS: AI-Native Linux Distribution & Universal Rust Architecture

**Document Status:** Experimental / Architectural Proposal  
**Date:** 2026-08-31  
**Target Systems:** Halbert Desktop (Tauri/React), Halbert Daemon (`halbertd`), HalbertOS Linux Distro  

---

## 1. Executive Summary & Vision

Halbert currently operates as an intelligent userspace application: it inspects `/proc` and `/sys`, queries `journalctl`, runs administrative commands through `sudo` subprocesses, and renders insights through a Tauri/React desktop interface or CLI.

While effective, userspace agents suffer from three fundamental limitations:
1. **Asynchronous Blindness:** Polling logs or process lists misses ephemeral events and introduces latency.
2. **Blast-Radius Insecurity:** Ad-hoc scripts executed via `sudo` cannot be constrained at the kernel level without pre-existing sandboxing policies.
3. **Fragile State Transitions:** Reverting broken system changes requires heuristic undo scripts rather than kernel/filesystem-enforced atomic transactions.

**HalbertOS** is an exploration of an **AI-Native Operating System** where the OS kernel, init system, storage layer, and shell are co-designed around an autonomous agentic loop. 

Crucially, building towards this vision does not require throwing away our existing stack. By designing a **Universal Rust Core**, the same native primitives that power HalbertOS can immediately supercharge the existing Halbert Desktop App and Python Agent Brain.

```
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│                                     THE UNIVERSAL TRI-BRIDGE                                 │
└─────────────────────────────────────────────────────────────────────────────────────────────┘

                  ┌─────────────────────────────────────────────────────────┐
                  │                 SHARED RUST CRATE CORE                  │
                  │  • halbert-telemetry (eBPF, procfs, sysinfo)            │
                  │  • halbert-snapshots (Btrfs/ZFS CoW ioctls)             │
                  │  • halbert-sandbox   (Landlock, cgroups v2, namespaces) │
                  │  • halbert-pty       (Zero-latency shell interceptor)   │
                  └───────┬───────────────────┬───────────────────┬─────────┘
                          │                   │                   │
        Direct Cargo Dep  │     PyO3 / Maturin│   Standalone Build│
        (Zero-overhead)   │     FFI Bindings  │   (Native Binaries│
                          │                   │                   │
         ┌────────────────▼──────┐  ┌─────────▼────────┐  ┌───────▼─────────────────┐
         │    TAURI V2 DESKTOP   │  │   PYTHON AGENT   │  │  HALBERT-OS DAEMONS     │
         │  • Desktop Dashboard  │  │  • CRAG State    │  │  • halbertd (PID 1/bus) │
         │  • Wayland/macOS HUD  │  │    Machine       │  │  • halbert-sh (PTY)     │
         │  • React UI & Tokens  │  │  • Hybrid RAG    │  │  • halbert-ebpf (Kernel)│
         │  • Audio/Echo Cancel  │  │  • Multi-LLM     │  │  • Sentinel Recovery    │
         └───────────────────────┘  └──────────────────┘  └─────────────────────────┘
```

---

## 2. The HalbertOS Linux Distribution Blueprint

HalbertOS integrates agentic intelligence across five distinct rings of the Linux operating system:

```
                               ┌──────────────────────────────────────────────────────────┐
                               │                    HALBERT DESKTOP / UI                  │
                               │  Tauri v2 + Wayland Compositor (Smithay/wlroots) HUD     │
                               │  Native Split-Canvas Terminal, Visual Blast-Radius Diffs │
                               └────────────────────────────┬─────────────────────────────┘
                                                            │ IPC / D-Bus
                               ┌────────────────────────────▼─────────────────────────────┐
                               │                   HALBERT AGENT ENGINE                   │
                               │  [Python / PyO3] CRAG State Machine, Hybrid RAG,         │
                               │  Safety Guardrails, Multi-Model Router (Local NPU/Cloud) │
                               └──────────────┬────────────────────────────┬──────────────┘
                                              │                            │
                     RPC / Unix Domain Socket │                            │ D-Bus System Bus
                                              │                            │
                ┌─────────────────────────────▼─────────┐        ┌─────────▼────────────────────────────┐
                │          HALBERTD SYSTEM DAEMON       │        │          HALBERT-SH PTY PROXY        │
                │  [Rust] Root Broker, Transaction Hub, │        │  [Rust] Shell Interceptor, ANSI      │
                │  Btrfs CoW Snapshot & Rollback Engine │        │  Parser, Real-Time Command Guardrail │
                └───────────────────┬───────────────────┘        └──────────────────┬───────────────────┘
                                    │                                               │
                                    │ Netlink / Ring Buffer                         │ Syscalls
                                    │                                               │
┌───────────────────────────────────▼───────────────────────────────────────────────▼───────────────────────────────────┐
│                                                 LINUX KERNEL (HALBERT MODS)                                           │
│  ┌─────────────────────────┐   ┌──────────────────────────┐   ┌───────────────────────────┐   ┌────────────────────┐  │
│  │   eBPF Telemetry Core   │   │  eBPF-LSM / Landlock     │   │     Btrfs / ZFS VFS       │   │ Hardware Isolation │  │
│  │ (execve, connect, oom)  │   │  Dynamic Kernel Sandboxing│   │ Auto-Snapshot Subvolumes  │   │ NPU/VRAM Agent Resv│  │
│  └─────────────────────────┘   └──────────────────────────┘   └───────────────────────────┘   └────────────────────┘  │
└───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

### Ring 0: Kernel Telemetry & LSM Enforcement
* **eBPF Tracepoint Streaming:** `halbert-ebpf` hooks `sys_enter_execve`, `oom_mark_victim`, `tcp_connect`, and `vfs_unlink`. Kernel events stream through a ring buffer directly into Halbert’s observation loop with microsecond latency and zero CPU polling overhead.
* **Kernel-Enforced Blast Radius (Landlock / LSM):** When Halbert plans a remediation task (e.g. modify `/etc/systemd/resolved.conf`), it generates a temporal Landlock security profile. The kernel actively blocks any attempted file modification outside the declared boundary.

### Ring 1: Storage & Filesystem (Atomic CoW Transactions)
* **Subvolume Shadowing:** The base root filesystem is immutable (using `systemd-repart` and read-only dm-verity or Btrfs subvolumes).
* **Instant Rollback:** Every multi-step plan executes within an atomic snapshot generation. If post-execution verification or health probes fail, the filesystem rolls back in under 5ms, ensuring zero unrecoverable states.

### Ring 2: Init, Systemd & Sentinel Recovery
* **`halbertd` System Daemon:** Runs as a privileged systemd unit on the D-Bus system bus (`org.halbert.SystemdBroker`), exposing safe, policy-checked APIs for process, network, and storage manipulation.
* **Early-Boot Sentinel Target:** In case of kernel panic, failed DKMS module compilation, or broken graphics drivers, systemd hands boot control over to the Halbert Sentinel recovery shell. Halbert analyzes early `dmesg`, retrieves fixes from offline RAG docs, applies the patch, or reboots into the previous working Btrfs generation.

### Ring 3: Shell & PTY Interception (`halbert-sh`)
* **Live Command Proxy:** A Rust PTY wrapper sits between the user/agent and the shell session.
* **Inline Risk Detection:** Typo interception (e.g. `rm -rf /usr /local`), missing package detection, and context-aware man-page/RAG auto-suggestions rendered directly into terminal standard output.

### Ring 4: Compositor & Desktop Environment
* **Wayland Compositor HUD:** Implemented using Rust (`smithay` or `wlroots`) alongside our Tauri v2 frontend.
* **Global Diagnostic Canvas:** Super+Space hotkey triggers a native floating HUD showing live system topology, blast-radius diffs, and real-time logs.

---

## 3. The Universal Rust Codebase Strategy

A common pitfall in system rewrites is creating duplicate codebases (one for desktop, one for the OS). We avoid this by adopting a **Modular Rust Crate Architecture** that serves both targets simultaneously.

### Crate Hierarchy & Target Matrix

```
Halbert Monorepo
├── crates/
│   ├── halbert-telemetry/   # eBPF probes, procfs/sysfs parsers, sysinfo
│   ├── halbert-snapshots/   # Btrfs / ZFS ioctl bindings, snapshot transactions
│   ├── halbert-sandbox/     # Landlock, cgroups v2, Linux namespace isolation
│   ├── halbert-pty/         # Zero-latency terminal emulator & ANSI proxy
│   └── halbert-ffi/         # PyO3 Python bindings for the crates above
├── halbert_core/            # Existing Python Agent (CRAG, RAG, Prompt Engines)
│   └── halbert_core/
│       └── native/          # `import halbert_rs` (loads halbert-ffi)
└── halbert_core/dashboard/frontend/src-tauri/  # Tauri Desktop Shell
    └── Cargo.toml           # Directly imports crates/halbert-telemetry, etc.
```

### 1. How the Existing Tauri Desktop App Uses Rust
Tauri v2 is written in Rust. Currently, `src-tauri/src/lib.rs` spawns a Python sidecar for all backend logic.

By adding our shared Rust crates directly to `src-tauri/Cargo.toml`:
* System metrics, telemetry, and process scans can be executed **directly in the Tauri process** with zero HTTP latency.
* The desktop application on macOS/Linux becomes significantly lighter and faster, only invoking the Python backend for heavy LLM reasoning and RAG vector searches.

### 2. How the Existing Python Backend Uses Rust
Python remains the premier language for dynamic agent loops, LangGraph-style state machines, and rapid prompt engineering.

Using **PyO3** and **Maturin**, we compile the shared Rust crates into a native Python extension module (`halbert_rs`):

```python
# In halbert_core/scanners/native_scanner.py
import halbert_rs

class NativeSystemScanner:
    def get_realtime_telemetry(self):
        # Native Rust eBPF/procfs reader with zero Python GIL overhead
        return halbert_rs.telemetry.collect_system_state()

    def execute_transactional_step(self, command: str, allowed_paths: list[str]):
        # Native Rust Btrfs snapshot + Landlock kernel sandbox
        with halbert_rs.snapshots.transaction(paths=allowed_paths) as tx:
            result = tx.run_sandboxed(command)
            if not result.success:
                tx.rollback() # Sub-second rollback
```

### 3. How HalbertOS Daemons Use Rust
The exact same `crates/` compile into standalone binaries:
* `halbertd`: Privileged system daemon managing D-Bus and root transactions.
* `halbert-sh`: Standalone terminal multiplexer and PTY wrapper.
* `halbert-sentinel`: Minimal recovery binary included in the `initramfs`.

---

## 4. Work Breakdown: Rebuilding vs. Retaining

| Component | Language | Status in Halbert | Role in HalbertOS / Desktop |
| :--- | :--- | :--- | :--- |
| **Agent State Machine & CRAG** | Python 3.12 | **Retain** | High-level reasoning, multi-turn dialogue, tool orchestration. |
| **Hybrid RAG & Vector Index** | Python (SQLite/LanceDB) | **Retain** | Documentation indexing, BM25 + dense vector search. |
| **Dashboard UI & Design Tokens**| React 18/19 + TS | **Retain** | Shared webview UI across Tauri and Wayland compositor HUD. |
| **Model Picker & Provider Hub** | TypeScript / Rust | **Retain & Extend** | Manages local (llama.cpp/vLLM) and cloud API endpoints. |
| **Audio Capture & Echo Cancel** | Rust (`cpal`/`webrtc`) | **Retain** | Already native in `src-tauri`! |
| **System Scanners & Probes** | Python ➔ Rust | **Migrate to Rust** | Move from `/proc` text parsing to eBPF + native syscalls. |
| **Execution Engine & Sandbox** | Python ➔ Rust | **Migrate to Rust** | Move from standard `sudo` subprocesses to Landlock / Btrfs CoW. |
| **PTY / Shell Interceptor** | New (Rust) | **Build Native** | Zero-latency command parser and terminal streaming HUD. |
| **Init & System Daemon** | New (Rust) | **Build Native** | D-Bus broker (`halbertd`) for root-level transactions. |

---

## 5. Base Distro Strategy & Build Pipeline

To prototype HalbertOS without maintaining millions of lines of upstream package trees, we utilize the modern standard for custom Linux appliances:

1. **Build Toolchain:** `mkosi` (Make Operating System Image) + `systemd-repart`.
2. **Base System:** Minimal Arch Linux or Fedora CoreOS base with a signed unified kernel image (UKI).
3. **Storage Layout:**
   * `/efi`: Systemd-boot / UKI with Halbert recovery hooks.
   * `/usr`: Read-only, dm-verity protected OS image layer.
   * `/var`: Btrfs subvolumes for user data, logs, and transactional snapshots.
   * `/opt/halbert/rag`: Read-only SquashFS / `systemd-sysext` layer containing offline sysadmin documentation vectors (ArchWiki, man pages, Debian/RHEL docs).
4. **Local AI Runtime:** Embedded `llama.cpp` server bound to local GPU/NPU with dedicated early-boot memory reservation.

---

## 6. Phased Implementation Roadmap

```
Phase 1: Shared Rust Native Crate Core
  ├── Create `crates/halbert-telemetry` & `crates/halbert-snapshots`
  ├── Add PyO3 bindings (`halbert-ffi`)
  └── Wire directly into `src-tauri` and `halbert_core`

Phase 2: Sandboxed Command Execution Engine
  ├── Implement Landlock-based dynamic LSM policy generator
  ├── Integrate Btrfs snapshot hooks into Python Agent verification loop
  └── Release as native performance upgrade for existing Halbert App

Phase 3: Terminal Interceptor (`halbert-sh`)
  ├── Build Rust PTY proxy with ANSI parser
  └── Enable real-time inline RAG hints and safety interception

Phase 4: HalbertOS Appliance Prototype
  ├── Create `mkosi` build recipes for Arch/Btrfs base
  ├── Package `halbertd` systemd service and initramfs sentinel
  └── Produce bootable ISO / VM image (QEMU/KVM)
```

---

## 7. Conclusion

A HalbertOS Linux distribution is both theoretically sound and practically achievable by leveraging modern Linux primitives (eBPF, Landlock, Btrfs, `mkosi`, and systemd). 

Furthermore, by adopting a **Universal Rust Core**, every hour invested in low-level OS engineering directly benefits the existing Tauri desktop app and Python agents—delivering faster scans, safer execution, and lower resource consumption across all platforms.
