# External Review Request: Rust Native Core Architecture & Implementation Plan

**Date:** 2026-08-31
**Branch:** `feat/rust-native-core`
**Worktree:** `/Users/ericbintner/.config/superpowers/worktrees/Halbert/rust-native-core`
**Reviewer tier requested:** Opus high / Fable (architectural review of system-level Rust design)

---

## 1. Purpose

We are asking for an external architectural review of the Rust Native Core
project before we commit to the implementation path. We have:

1. Completed a strategy review that killed the "HalbertOS as HA host" plan
2. Defined a scoped three-layer strategy with 8 confirmed founder decisions
3. Written a 56-task implementation plan across 7 phases (R0-R7)
4. Built the first two phases (R0 scaffolding + R1.1/R1.2 MQTT client)

We need you to validate:

- **Is the Rust/Python boundary correct?** Are we rewriting the right things
  in Rust and keeping the right things in Python?
- **Are the trait contracts sound?** Will they hold up as the system evolves?
- **Is the phase ordering correct?** Are dependencies right? Are we building
  in the right order?
- **Are we missing anything critical?** Security, platform, packaging,
  testing gaps?
- **Is the "daemon first, distro later" strategy sound?** Does `halbertd` as
  a package on standard distros actually deliver the value we claim?

---

## 2. How to Review

### Files to read (in order)

#### Strategy & scoping (the "why")

| File | Lines | What it contains |
|------|-------|-----------------|
| `.handoff/REVIEW-RESULTS-HA-STRATEGY-AND-HALBERTOS-2026-08-31.md` | 213 | External review that killed HA Supervised hosting, approved three-layer strategy, added Options E (HA Add-on) and F (sidecar) |
| `.handoff/HA-STRATEGY-SCOPING-AND-DEPLOYMENT-PATHS-2026-08-31.md` | 470 | Synthesis document with all 8 confirmed decisions (D1-D8), 4 deployment paths, docker-compose template, scoped roadmap |
| `.handoff/MASTER-TODO.md` | 187 | Master task index — existing Python/React work batches (U1-U6) plus cross-reference to the Rust plan |

#### Implementation plan (the "what" and "when")

| File | Lines | What it contains |
|------|-------|-----------------|
| `.handoff/RUST-NATIVE-CORE-TODO-AND-IMPLEMENTATION-PLAN-2026-08-31.md` | 426 | 56 tasks across 7 phases (R0-R7), each with model tier + effort level, stability analysis, dependency graph, sync points with MASTER-TODO |

#### Experimental vision docs (the "where we're going")

| File | What it contains |
|------|-----------------|
| `documentation/experimental/README.md` | Maturity tiers (near-term actionable vs north-star) |
| `documentation/experimental/SINGULAR-ENTITY-HOME-ASSISTANT-AND-HALBERTOS-ECOSYSTEM.md` | Corrected HA integration paths (peer, sidecar, add-on), native MQTT/Matter direction |
| `documentation/experimental/HALBERT-OS-DISTRO-AND-UNIVERSAL-RUST-ARCHITECTURE.md` | Distro blueprint with maturity caveats (5ms rollback labeled aspirational, audio stubbed, north-star items deferred) |
| `documentation/experimental/COMPETITIVE-ANALYSIS-AI-OS-LANDSCAPE.md` | Competitive landscape (doc count corrected to 24,600, 0% failure labeled as future target) |
| `documentation/experimental/OS-NATIVE-MCP-WARP-AND-SOURCEPREP-INTEGRATION.md` | OS-native MCP server design (doc count corrected) |
| `documentation/experimental/UNIVERSAL-CROSS-PLATFORM-AND-MIGRATION-ROADMAP.md` | Cross-platform roadmap (APFS SPI caveat added, Windows deferred, timeline labeled aspirational) |

#### Built code (the "what we've done so far")

| File | Lines | What it contains |
|------|-------|-----------------|
| `crates/Cargo.toml` | 45 | Workspace manifest, shared dependencies |
| `crates/README.md` | 134 | Trait contract documentation, platform support matrix, build instructions |
| `crates/halbert-mqtt/src/lib.rs` | 455 | **Implemented:** MqttClient trait + RumqttClient (rumqttc 0.25), DeviceStateCache trait + InMemoryDeviceStateCache (DashMap), 6 tests passing |
| `crates/halbert-telemetry/src/lib.rs` | 134 | **Stubbed:** TelemetrySource trait, TelemetryEvent enum, TelemetryConfig, 2 tests passing |
| `crates/halbert-snapshots/src/lib.rs` | 129 | **Stubbed:** SnapshotEngine trait, SnapshotHandle, SnapshotConfig, 2 tests passing |
| `crates/halbert-sandbox/src/lib.rs` | 160 | **Stubbed:** SandboxEngine trait, SandboxRules, FsRule, FsAccess, NetAccess, 3 tests passing |
| `crates/halbert-ffi/src/lib.rs` | 50 | **Stubbed:** PyO3 module skeleton, PyUnsupportedError class |

### What's been built (git log)

```
ec1518c1 :rust re-write R1.1+R1.2: implement halbert-mqtt with rumqttc + device state cache
a6f624ee :rust re-write R0: scaffold crates/ workspace with trait definitions
3909a48c docs(handoff): Rust native core long-term TODO + implementation plan
41ae15d0 docs(experimental): apply 14 corrections from HA strategy review, add scoping decisions
```

### How to build and test

```bash
# IMPORTANT: use rustup's cargo (1.98+), not Homebrew's (1.84)
export PATH="$HOME/.cargo/bin:$PATH"

cd crates/
cargo build          # builds all default-members (excludes halbert-ffi)
cargo test           # all tests pass
cargo clippy -- -D warnings  # clean

# halbert-ffi requires maturin (Python linking):
cd crates/halbert-ffi && maturin build --release
```

---

## 3. The Architecture Under Review

### The core principle

> **Rewrite the interfaces to stable system APIs in Rust.**
> **Keep the application logic in Python.**
> Rust crates are thin native layers; Python is the brain that calls them.

A component qualifies for Rust rewrite only if:
1. It wraps a **stable kernel/syscall API** (eBPF, Btrfs ioctl, Landlock) or a
   **stable protocol** (MQTT, PTY) that hasn't changed in years
2. It is **CPU-bound or latency-sensitive** (not I/O-bound text parsing)
3. Its **interface contract** is unlikely to change

### What goes in Rust vs. stays in Python

| In Rust (stable interfaces) | Stays in Python (application logic) |
|----------------------------|--------------------------------------|
| MQTT transport (OASIS standard, 25+ years) | Agent state machine / CRAG |
| eBPF probes (stable kernel tracepoints) | Prompt assembly (still evolving) |
| Btrfs ioctls (stable since 2009) | RAG / vector search (mid-migration) |
| Landlock syscalls (stable since kernel 5.13) | Discovery scanners (24 files, I/O-bound) |
| cgroups v2 (stable since kernel 4.15) | Device registry / entity mapping |
| PyO3 bridge (stable ABI) | Event mappers (HA, MQTT) |
| Unix socket IPC (JSON-RPC 2.0) | Dashboard frontend (React/TypeScript) |
| PTY plumbing (POSIX, 1980s) | Tool definitions (high-velocity) |
| | Safety policy generation (which paths to snapshot/allow) |

### The 7-phase plan

```
R0: Foundation (crates/ workspace + scaffolding)         [DONE]
R1: Native Device Bus (halbert-mqtt + Python registry)   [R1.1+R1.2 DONE, R1.3-R1.9 pending]
R2: Kernel Telemetry (eBPF probes)                       [BLOCKED — Opus high design decision]
R3: Atomic Safety (Btrfs snapshots + Landlock)           [Pending, depends on R2]
R4: PyO3 Bridge (halbert-ffi)                            [Pending, depends on R1+R2+R3]
R5: halbertd Daemon (systemd + MCP + wires all crates)   [Pending, depends on R4]
R6: Deployment Paths (sidecar + HA Add-on + OS-MCP)      [Pending, depends on R5]
R7: Turnkey Appliance (north-star, gated)                [Gated on R1-R6 + founder approval]
```

### The 4 deployment paths

| Path | What | Status |
|------|------|--------|
| 1. Distributed peer | Halbert desktop + separate HA edge node | Already works (existing HA WebSocket integration) |
| 2. Sidecar (one box) | Standard Linux + halbertd + docker-compose (HA + Z2M + Mosquitto) | Template designed, not yet built |
| 3. HA Add-on (funnel) | Halbert as HACS add-on inside HAOS | Not yet built |
| 4. Turnkey appliance | Pre-configured standard distro + halbertd | North-star, gated on R1-R6 |

---

## 4. Specific Review Questions

### Q1: Is the Rust/Python boundary in the right place?

We're putting the MQTT transport in Rust but the device registry / entity
mapping in Python. The eBPF probes and ring buffer parser are in Rust, but
which events to react to and how to feed them into cognition is in Python.
Btrfs ioctl wrappers are in Rust, but which paths to snapshot and when to
rollback is in Python.

**Is this the right split?** Are there components we're keeping in Python
that would benefit from Rust, or vice versa?

Specifically: the 24 discovery scanners (13,836 lines of Python) read
`/sys` and `/proc` files and run subprocesses. We've classified these as
I/O-bound and not worth rewriting. **Do you agree, or should some scanners
move to Rust?**

### Q2: Are the trait contracts sound?

The five trait contracts are documented in `crates/README.md`:

- `MqttClient`: connect/subscribe/unsubscribe/publish/recv/disconnect
- `DeviceStateCache`: get_state/update_state/remove_state/list_topics/clear
- `TelemetrySource`: start/stop/is_running/recv
- `SnapshotEngine`: create_snapshot/rollback_snapshot/delete_snapshot/list_snapshots/is_available
- `SandboxEngine`: create_sandbox/enter_sandbox/is_available/destroy_sandbox

**Will these hold up as the system evolves?** Are we missing methods? Are
the return types right (e.g. should `recv()` return a stream instead of
blocking)? Should `SnapshotEngine` support partial/transactional snapshots?

### Q3: Is `aya` the right eBPF framework choice?

R2.1 (the blocker we hit) is the choice between:
- **`aya`** — pure Rust, no C dependencies, aligns with "Universal Rust Core" vision
- **`libbpf-rs`** — C bindings to libbpf, more mature, more examples, CO-RE support

We lean toward `aya` for architectural consistency. **Is this the right
call for production eBPF probes?** Are there stability or feature gaps in
`aya` that would bite us?

### Q4: Is the `halbertd` daemon architecture sound?

The plan is for `halbertd` to be a single binary with subcommands, running
as a systemd service, exposing a JSON-RPC 2.0 API over a Unix domain socket.
Privilege separation: root for kernel ops (eBPF, Btrfs, Landlock),
unprivileged for MCP serving.

**Is single-binary the right choice vs. multiple daemons?** Is Unix socket
+ JSON-RPC the right IPC mechanism? Is the privilege model correct?

### Q5: Are we missing anything critical?

Things we've considered and deferred:
- Windows platform (deferred per D7)
- Custom kernel / Wayland compositor / PID 1 (north-star per D7)
- Native Matter controller (gated on rs-matter 1.0)
- APFS snapshot transactions (private SPI, research only)

Things we have NOT considered:
- **macOS Endpoint Security framework** as an alternative to eBPF on Mac. Should we?
- **seccomp-bpf** as a complement to Landlock for syscall filtering
- **io_uring** for the MQTT client's network I/O (currently using tokio's standard async)
- **WireGuard** or **Tailscale** integration for secure peer-to-peer between Halbert nodes
- **SELinux** compatibility (we're designing for Landlock + AppArmor, but not SELinux)

**Are any of these critical? Are there other gaps we haven't considered?**

### Q6: Is the phase ordering and dependency graph correct?

Current dependency chain:
```
R0 → R1 (MQTT) ──────────────────────────┐
R0 → R2 (eBPF) → R3 (snapshots/sandbox) ─┤→ R4 (PyO3) → R5 (daemon) → R6 (deploy) → R7 (appliance)
```

R1 and R2 are independent and can run in parallel. R3 depends on R2 (sandbox
needs telemetry context — though this is debatable). R4 wraps all crates.
R5 wires everything into the daemon. R6 packages for deployment.

**Is R3 really dependent on R2?** The sandbox (Landlock) doesn't strictly
need the telemetry (eBPF) to function. We could build them in parallel.
**Should we decouple them?**

### Q7: Is the model tier assignment correct?

We've assigned:
- **Fable**: security review of kernel-level code (eBPF, Landlock, daemon privilege model)
- **Opus**: safety-critical kernel wrappers, daemon architecture, MCP protocol extension
- **Sonnet**: well-specified mechanical work (MQTT client, FFI bindings, packaging)
- **GLM-5.3**: Python-side integration (device registry, entity mapping, event mappers)

**Are these assignments right?** Specifically, is the eBPF probe
implementation really Opus xhigh, or could a Sonnet-level agent handle it
with good specs? Is the PyO3 bridge really Sonnet, or does the async
bridge need Opus-level care?

---

## 5. What We Want Back

A review document (`REVIEW-RESULTS-RUST-NATIVE-CORE-2026-08-31.md`) with:

1. **Architecture verdict**: Is the Rust/Python boundary correct? Any components that should move?
2. **Trait contract review**: Are the 5 trait contracts sound? Any missing methods or type issues?
3. **eBPF framework recommendation**: `aya` vs `libbpf-rs` — which and why?
4. **Daemon design review**: Is the `halbertd` architecture sound? IPC, privilege model, single-binary?
5. **Gap analysis**: What are we missing? (macOS ES framework, seccomp, io_uring, etc.)
6. **Phase ordering review**: Is the dependency graph correct? Should R3 be decoupled from R2?
7. **Model tier assessment**: Are the effort assignments appropriate?
8. **Risk assessment**: What are the top 5 risks of this approach? What would make you reject it?
9. **Alternative approaches considered and rejected**: Are there architectures we should have considered but didn't?

---

## 6. Context: What Halbert Is

For reviewers unfamiliar with the project:

**Halbert** is an AI agent that lives on your computer and manages it for
you. It has:

- A **Python core** (`halbert_core/`) with a state machine, CRAG
  (Cognitive RAG), prompt assembly, discovery scanners, and an MCP server
- A **Tauri desktop app** (`halbert_core/dashboard/frontend/`) with React UI
- A **Home Assistant integration** via WebSocket API (existing, working)
- A **voice pipeline** via Wyoming protocol (existing, partially working)
- A **local LLM router** supporting Ollama, vLLM, Apple Intelligence

The Rust Native Core project is adding kernel-level capabilities (eBPF
telemetry, Btrfs snapshots, Landlock sandboxing, native MQTT device bus)
that the Python core can't do efficiently. The goal is to deliver these
features on standard Linux distros (and macOS where possible) without
requiring a custom OS.

The existing codebase is ~50,000 lines of Python + ~2,000 lines of Rust
(in the Tauri shell). The Rust Native Core will add ~5,000-10,000 lines
of Rust across the 5 crates.

---

## 7. Constraints

- **GPL-3.0-or-later** license for all code
- **Rust 1.85+** required (edition2024 in transitive dependencies)
- **macOS development machine** (Apple Silicon, Rust 1.98 via rustup)
- **Linux VM available** for eBPF/Btrfs/Landlock testing
- **No Windows** support in scope (deferred per D7)
- **Existing Python agent must not break** — Rust crates are additive, not replacement
- **Subtractive contract**: the Python core has only 2 hard dependencies
  (`pyyaml`, `requests`); all heavy stacks are optional extras. The Rust
  extension (`halbert_rs`) must also be optional — the agent gracefully
  degrades if it's not installed.

---

## 8. Current Blocker

We've completed R0 (scaffolding) and R1.1+R1.2 (MQTT client + device state
cache). The next task that exceeds our tier is:

**R2.1 — Choose eBPF framework (`aya` vs `libbpf-rs`)** — assigned as
**Opus high** because it's an architectural design decision that affects
all subsequent eBPF work (R2.2-R2.10) and the daemon design (R5).

We need the reviewer's recommendation on Q3 (eBPF framework) to unblock
R2. We also need the reviewer's verdict on Q1 (Rust/Python boundary) before
we commit to R1.3-R1.9 (Python-side MQTT integration), since a boundary
shift would change what we build in Python.

---

## 9. File Index (Complete)

### Handoff & planning documents
```
.handoff/
├── REVIEW-REQUEST-HA-STRATEGY-AND-HALBERTOS-2026-08-31.md   # Original HA strategy analysis
├── REVIEW-RESULTS-HA-STRATEGY-AND-HALBERTOS-2026-08-31.md   # External review results (approved strategy)
├── HA-STRATEGY-SCOPING-AND-DEPLOYMENT-PATHS-2026-08-31.md   # Synthesis: 8 decisions, 4 paths, scoped roadmap
├── RUST-NATIVE-CORE-TODO-AND-IMPLEMENTATION-PLAN-2026-08-31.md  # 56 tasks, 7 phases, model tiers
└── MASTER-TODO.md                                             # Master task index (U1-U6 + Rust cross-ref)
```

### Experimental vision documents (corrected)
```
documentation/experimental/
├── README.md                                                  # Maturity tiers preamble
├── SINGULAR-ENTITY-HOME-ASSISTANT-AND-HALBERTOS-ECOSYSTEM.md  # HA integration paths (corrected)
├── HALBERT-OS-DISTRO-AND-UNIVERSAL-RUST-ARCHITECTURE.md       # Distro blueprint (maturity caveats added)
├── COMPETITIVE-ANALYSIS-AI-OS-LANDSCAPE.md                    # Competitive landscape (corrected)
├── OS-NATIVE-MCP-WARP-AND-SOURCEPREP-INTEGRATION.md           # OS-native MCP server design
└── UNIVERSAL-CROSS-PLATFORM-AND-MIGRATION-ROADMAP.md          # Cross-platform roadmap (caveats added)
```

### Built Rust code
```
crates/
├── Cargo.toml              # Workspace manifest
├── Cargo.lock              # Locked dependencies
├── README.md               # Trait contract documentation
├── .gitignore              # Ignores target/
├── halbert-mqtt/           # [IMPLEMENTED] MQTT client + device state cache
│   ├── Cargo.toml
│   └── src/lib.rs          # 455 lines, 6 tests passing
├── halbert-telemetry/      # [STUBBED] eBPF kernel telemetry
│   ├── Cargo.toml
│   └── src/lib.rs          # 134 lines, 2 tests passing
├── halbert-snapshots/      # [STUBBED] Btrfs atomic snapshots
│   ├── Cargo.toml
│   └── src/lib.rs          # 129 lines, 2 tests passing
├── halbert-sandbox/        # [STUBBED] Landlock kernel sandboxing
│   ├── Cargo.toml
│   └── src/lib.rs          # 160 lines, 3 tests passing
└── halbert-ffi/            # [STUBBED] PyO3 bridge
    ├── Cargo.toml
    └── src/lib.rs          # 50 lines, skeleton only
```

### Git history (this branch)
```
ec1518c1 :rust re-write R1.1+R1.2: implement halbert-mqtt with rumqttc + device state cache
a6f624ee :rust re-write R0: scaffold crates/ workspace with trait definitions
3909a48c docs(handoff): Rust native core long-term TODO + implementation plan
41ae15d0 docs(experimental): apply 14 corrections from HA strategy review, add scoping decisions
0c6c84ab docs(handoff): add review request for HA strategy and HalbertOS foundation
e15b50c7 docs(review): critical review of HA strategy & HalbertOS foundation
3f17d433 docs(experimental): add HalbertOS distro blueprints, cross-platform roadmap, AI-OS competitive research
```
