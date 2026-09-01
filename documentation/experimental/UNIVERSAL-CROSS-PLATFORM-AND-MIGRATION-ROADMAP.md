# Universal Cross-Platform Architecture & Rust Migration Roadmap

**Document Status:** Experimental / Architectural Strategy  
**Date:** 2026-08-31  
**Target Platforms:** Linux (HalbertOS & Standard Distros), macOS (Apple Silicon / Intel), Windows 11 / Server / WSL2  
**Host Frameworks:** Rust Core, Python Agent Brain (v1 Prototype ➔ Hybrid), Tauri v2, Swift/AppKit, Win32/WinUI  

---

## 1. Executive Summary & Strategy

Halbert is actively evolving. The current Python + Tauri/React stack serves as our **rapid-iteration prototype (v1)**. Halting feature velocity to execute a monolithic rewrite would be counterproductive.

Instead, we adopt a **two-track evolution strategy**:
1. **Prototype Track (Velocity First):** Continue building features, agent state-machine intelligence, CRAG refinement, prompt assembly, and UI components in Python and React.
2. **Universal Core Track (Subtractive Migration):** Incrementally carve out performance-critical, security-sensitive, and OS-deep hooks into **modular Rust crates** (`halbert-sys`). These crates are consumed by:
   * **The Current App:** via PyO3 C-extensions in Python and native Cargo imports in Tauri v2.
   * **Apple / Swift:** via C-ABI / `uniffi-rs` frameworks.
   * **Windows:** via `windows-rs`, ETW, VSS, and ConPTY.
   * **HalbertOS:** via root daemons (`halbertd`), eBPF probes, and initramfs sentinels.

```
┌──────────────────────────────────────────────────────────────────────────────────────────────┐
│                               THE UNIVERSAL PLATFORM MATRIX                                  │
├───────────────────────┬────────────────────────────┬─────────────────────────┬───────────────┤
│ OS Subsystem          │ Linux (HalbertOS / Native) │ macOS (Apple Silicon)   │ Windows 11/WSL│
├───────────────────────┼────────────────────────────┼─────────────────────────┼───────────────┤
│ Real-Time Telemetry   │ eBPF / procfs / sysfs      │ EndpointSecurity / IOKit│ ETW / PDH     │
│ Snapshot & Rollback   │ Btrfs / ZFS CoW ioctls     │ APFS `fs_snapshot_*`    │ VSS / Shadows │
│ Kernel Sandboxing     │ Landlock / eBPF-LSM        │ App Sandbox / SandboxExec│ Job Objects  │
│ Terminal Proxy        │ Linux PTY (`forkpty`)      │ macOS PTY (`openpty`)   │ ConPTY Win32  │
│ Local AI Inference    │ llama.cpp / vLLM (CUDA)    │ MLX / Metal / CoreML    │ DirectML / ONNX│
│ Desktop Wrapper       │ Tauri v2 / Wayland HUD     │ Tauri v2 / Swift NSPanel│ Tauri v2/WinUI│
└───────────────────────┴────────────────────────────┴─────────────────────────┴───────────────┘
```

---

## 2. Platform Deep Dives

### 2.1 Swift & Apple Ecosystem (macOS)

Halbert already has strong roots on macOS (as seen in [`src-tauri`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend/src-tauri) with `floating_panel.rs`, `hud_hotkey.rs`, and `audio_capture.rs`).

#### Deep macOS Integration Primitives
* **APFS Snapshot Transactions:** macOS supports instantaneous copy-on-write snapshots on APFS formatted drives via `fs_snapshot_create()` and `fs_snapshot_revert()`. Rust can invoke these private/public POSIX APIs directly to give macOS the same zero-risk rollback safety as Btrfs on Linux.
* **Apple Silicon Hardware Telemetry:** Accessing real-time GPU/Neural Engine wattage and memory bandwidth via `IOKit` and `AppleSilicon` sysctls.
* **Swift / SwiftUI Interop:**
  * Using **`uniffi-rs`** (Mozilla’s multi-language FFI generator) or **`swift-bridge`**, our Rust core compiles into a standard `.xcframework` or Swift Package.
  * If we ever want a 100% native Swift MenuBar/Settings app or iOS/iPadOS companion, Swift can call the Rust engine directly with native type safety (`HalbertCore.swift`).
* **Local Neural Engine (ANE) & MLX:** Rust bindings to Apple's `MLX` or `llama.cpp` Metal backend for local inference with zero cloud dependency.

---

### 2.2 Windows 11 & Windows Server Ecosystem

Windows has distinct architectural paradigms from Unix, but Rust has first-class Tier-1 Windows support via Microsoft’s official **`windows-rs`** crate.

#### Deep Windows Integration Primitives
* **Telemetry via ETW (Event Tracing for Windows):**
  * ETW is the Windows equivalent of eBPF. It provides kernel-level trace events for process creation, file I/O, registry modifications, and network connections.
  * `halbert-telemetry` on Windows subscribes to ETW real-time sessions with near-zero overhead.
* **Atomic Rollbacks via VSS (Volume Shadow Copy Service):**
  * Windows VSS allows creating instantaneous shadow copies of NTFS/ReFS volumes.
  * Before Halbert modifies a registry hive or updates system drivers, it triggers a VSS snapshot, allowing 1-click rollback via Windows System Restore APIs.
* **Terminal Interception via ConPTY:**
  * Windows 10/11 includes **ConPTY** (Windows Pseudo Console).
  * `halbert-sh` on Windows wraps `CreatePseudoConsole()` to parse PowerShell and CMD streams, catching dangerous commands and rendering inline AI hints in Windows Terminal.
* **Sandboxing via Windows Job Objects & AppContainers:**
  * Windows Job Objects allow restricting CPU, memory, active network ports, and child process spawning for any executed script.
* **The "WSL2 Dual-Citizen" Advantage:**
  * On Windows, Halbert can act as a bridge between the Windows Host and the Linux WSL2 subsystem. It can manage Windows services (via Win32 APIs) and WSL2 Ubuntu/Debian instances (via `wsl.exe` and `\\wsl$` network shares) inside a single unified dashboard.
* **Local AI Acceleration via DirectML & ONNX Runtime:**
  * Windows Copilot+ PCs feature Qualcomm, Intel, and AMD NPUs.
  * Rust binds to DirectML and ONNX Runtime to execute quantized local models on Windows NPUs without consuming discrete GPU power.

---

## 3. The Unified Hardware & OS Abstraction Layer (HAL)

In Rust, all platform-specific logic is hidden behind idiomatic, zero-cost Rust traits:

```rust
// crates/halbert-sys/src/traits.rs

#[async_trait]
pub trait SystemSnapshotEngine: Send + Sync {
    async fn create_snapshot(&self, label: &str, target_path: &Path) -> Result<SnapshotHandle, HalbertError>;
    async fn rollback_snapshot(&self, handle: SnapshotHandle) -> Result<(), HalbertError>;
    async fn list_snapshots(&self) -> Result<Vec<SnapshotInfo>, HalbertError>;
}

// Platform Implementations:
// • Linux:   BtrfsIoctlSnapshotEngine / ZfsSnapshotEngine
// • macOS:   ApfsSnapshotEngine
// • Windows: VssShadowCopyEngine
```

The higher-level agent loop (whether running in Python, Rust, or Swift) simply calls `snapshot_engine.create_snapshot(...)` without caring whether it is running on Arch Linux, macOS Tahoe, or Windows 11.

---

## 4. Pragmatic Phased Migration Roadmap

```
                                    MIGRATION TIMELINE
========================================================================================

  [Current Stage: v1 Prototype]
  ├── Focus: Agent capabilities, RAG completeness, Prompt XML Assembly, Dashboard UX
  └── Stack: Python 3.12 (halbert_core) + React (frontend) + Tauri v2 (shell)

  [Milestone 1: Shared Rust System Scanners (Q4 2026)]
  ├── Build `crates/halbert-telemetry` (sysinfo, procfs, IOKit, ETW)
  ├── Export PyO3 extension (`import halbert_rs`)
  ├── Drop Python `psutil` / regex scraping overhead
  └── Wire directly into Tauri `src-tauri` for instant desktop UI metric graphs

  [Milestone 2: Cross-Platform Transaction & Sandbox Engine (Q1 2027)]
  ├── Build `crates/halbert-snapshots` (Btrfs, APFS, VSS)
  ├── Build `crates/halbert-sandbox` (Landlock, App Sandbox, Job Objects)
  ├── Integrate rollback safety directly into the Python Agent verification step
  └── Result: Zero-risk execution across Linux, Mac, and Windows

  [Milestone 3: Universal Terminal & Shell Interceptor (Q2 2027)]
  ├── Build `crates/halbert-pty` (POSIX PTY + Windows ConPTY)
  ├── Release `halbert-sh` wrapper CLI for Bash, Zsh, and PowerShell
  └── Provide real-time inline safety gating and RAG auto-completions

  [Milestone 4: Native Daemons & Appliance Builds (Q3 2027+)]
  ├── `halbertd` systemd daemon for Linux / HalbertOS
  ├── `HalbertHelper` launchd daemon for macOS Pro
  ├── `HalbertService` Windows Background Service for Windows 11
  └── Bootable HalbertOS appliance ISO via `mkosi`
```

---

## 5. Conclusion & Immediate Action Items

* **Keep Building Forward:** Do not rewrite the Python codebase today. The v1 prototype is working, proving out the agent state machine, CRAG verification, and multi-model routing.
* **Design Clean Interfaces:** Ensure new Python scanners and tool executors adhere to modular inputs/outputs that map 1:1 to future Rust trait contracts.
* **Keep Platform Hooks Decoupled:** Keep OS-specific commands isolated in scanner/tool registries so they can be replaced with native Rust HAL calls seamlessly when Milestone 1 begins.
