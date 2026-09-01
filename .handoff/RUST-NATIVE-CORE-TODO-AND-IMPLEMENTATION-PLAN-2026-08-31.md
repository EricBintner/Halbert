# Rust Native Core & HalbertOS — Long-Term Project TODO & Implementation Plan

**Date:** 2026-08-31
**Status:** Living document — synced with MASTER-TODO and the HA strategy scoping decisions
**Source documents:**
- `HA-STRATEGY-SCOPING-AND-DEPLOYMENT-PATHS-2026-08-31.md` (8 confirmed decisions)
- `documentation/experimental/` (5 corrected experimental docs)
- `MASTER-TODO.md` (existing work batches U1-U6)

---

## 0. Project Overview & Principles

### What this project is

A multi-phase effort to build a **Universal Rust Core** (`crates/halbert-*`)
that delivers kernel-level features (eBPF telemetry, Btrfs snapshots, Landlock
sandboxing, native MQTT) to the existing Halbert app on standard distros —
without requiring a custom OS. The "HalbertOS" brand applies to a future
turnkey appliance image (pre-configured standard distro + `halbertd`), not a
custom kernel.

### What this project is NOT

- A rewrite of the Python agent brain (state machine, CRAG, prompts, RAG)
- A rewrite of the 24 discovery scanners (I/O-bound, not CPU-bound)
- A custom Linux distribution (north-star only, deferred per D7)
- A Windows platform port (deferred per D7)

### Architectural principle

> **Rewrite the interfaces to stable system APIs in Rust.**
> **Keep the application logic in Python.**
> Rust crates are thin native layers; Python is the brain that calls them.

### Stability test (what qualifies for Rust)

A component qualifies for Rust rewrite only if:
1. It wraps a **stable kernel/syscall API** (eBPF, Btrfs ioctl, Landlock) or a
   **stable protocol** (MQTT, PTY) that hasn't changed in years
2. It is **CPU-bound or latency-sensitive** (not I/O-bound text parsing)
3. Its **interface contract** is unlikely to change (the application logic
   on top may churn, but the native layer itself is stable)

---

## 1. Model Tier & Effort Level Conventions

Consistent with MASTER-TODO conventions:

| Model | When to use | Effort levels |
|-------|-------------|---------------|
| **Fable** | Reserved for security review of kernel-level code, founder sign-off on OS-level architecture | n/a (review only) |
| **Opus** | Safety-critical kernel wrappers (eBPF, Landlock, Btrfs), system daemon design, MCP protocol extension | ultracode, max, xhigh, high |
| **Sonnet** | Well-specified mechanical work (FFI bindings, MQTT client, packaging, docker-compose, HA Add-on) | ultracode, max, xhigh, high, med |
| **GLM-5.3** | Default workhorse for Python-side integration (device registry, entity mapping) | ultracode, max, xhigh, high, med |

**Effort level definitions:**
- **ultracode**: Fan-out multi-agent workflow, full verify pass, production-ready
- **max**: Single-agent, maximum effort, thorough testing
- **xhigh**: High effort with extensive testing, but single-pass
- **high**: Standard implementation effort with tests
- **med**: Lighter effort, well-specified, lower risk

---

## 2. Phase Overview

```
Phase R0: Foundation (crates/ workspace + scaffolding)
    │
    ├── Phase R1: Native Device Bus (halbert-mqtt + Python registry)
    │       └── enables: HA becomes optional (Layer 2)
    │
    ├── Phase R2: Kernel Telemetry (halbert-telemetry / eBPF)
    │       └── enables: zero-overhead observability claim
    │
    ├── Phase R3: Atomic Safety (halbert-snapshots + halbert-sandbox)
    │       └── enables: Btrfs rollback + Landlock sandboxing
    │
    ├── Phase R4: PyO3 Bridge (halbert-ffi)
    │       └── enables: Python agent calls all Rust crates
    │
    ├── Phase R5: halbertd Daemon (systemd + MCP + wires all crates)
    │       └── enables: OS-level features on standard distros
    │
    ├── Phase R6: Deployment Paths (sidecar compose + HA Add-on + OS-MCP)
    │       └── enables: Path 2 (sidecar), Path 3 (HA funnel), os:// MCP
    │
    └── Phase R7: Turnkey Appliance (north-star, gated on R1-R6)
            └── enables: Path 4 (HalbertOS brand image)
```

**Dependency rule:** R0 is prerequisite for all. R1 and R2 are independent
and can run in parallel. R3 depends on R2 (sandbox needs telemetry context).
R4 depends on R1+R2+R3 (wraps all crates). R5 depends on R4. R6 depends on R5.
R7 is north-star, gated on R1-R6 completion and founder approval.

---

## 3. Phase R0 — Foundation (crates/ workspace + scaffolding)

**Goal:** Create the Cargo workspace, stub all crate skeletons, set up CI.
**Prerequisite:** None.
**Risk:** Zero — this is build infrastructure only.

| Task | Description | Model / Effort | Status |
|------|-------------|----------------|--------|
| R0.1 | Create `crates/` directory at repo root with Cargo workspace `Cargo.toml` | Sonnet med | Pending |
| R0.2 | Stub `crates/halbert-mqtt/` — `Cargo.toml`, `src/lib.rs` with trait definitions (`MqttClient`, `DeviceStateCache`), empty implementations | Sonnet med | Pending |
| R0.3 | Stub `crates/halbert-telemetry/` — `Cargo.toml`, `src/lib.rs` with trait definitions (`TelemetrySource`, `EventStream`), empty implementations | Sonnet med | Pending |
| R0.4 | Stub `crates/halbert-snapshots/` — `Cargo.toml`, `src/lib.rs` with trait definitions (`SnapshotEngine`, `SnapshotHandle`), empty implementations | Sonnet med | Pending |
| R0.5 | Stub `crates/halbert-sandbox/` — `Cargo.toml`, `src/lib.rs` with trait definitions (`SandboxEngine`, `SandboxRules`), empty implementations | Sonnet med | Pending |
| R0.6 | Stub `crates/halbert-ffi/` — `Cargo.toml` with `pyo3` dependency, `src/lib.rs` with empty Python module skeleton | Sonnet med | Pending |
| R0.7 | Add `crates/` to CI — ensure workspace compiles, clippy clean, tests pass (even if empty) | Sonnet med | Pending |
| R0.8 | Document crate trait contracts in `crates/README.md` — the trait definitions ARE the interface spec; Python side will implement against these | Sonnet high | Pending |

**Verification:** `cargo build --workspace` succeeds. `cargo clippy --workspace` clean. `cargo test --workspace` passes.

---

## 4. Phase R1 — Native Device Bus (halbert-mqtt + Python registry)

**Goal:** Halbert can see and control Zigbee devices via MQTT without HA.
**Prerequisite:** R0.
**Risk:** Low — MQTT is a 25-year-old standard. `rumqttc` is production-grade.
**Product value:** High — makes HA optional for core local devices (Layer 2).

| Task | Description | Model / Effort | Status | Stable? |
|------|-------------|----------------|--------|---------|
| R1.1 | Implement `crates/halbert-mqtt` — `rumqttc` client wrapper, connection management, QoS handling, auto-reconnect | Sonnet xhigh | Pending | Yes — MQTT 3.1.1/5.0 is a frozen OASIS standard |
| R1.2 | Implement device state cache in `halbert-mqtt` — in-memory topic → state map, retained message handling, last-will processing | Sonnet high | Pending | Yes — retained messages and LWT are spec-defined |
| R1.3 | Expose C-ABI or PyO3 interface for Python consumption | Sonnet high | Pending | Yes — the interface is `subscribe(topic)`, `publish(topic, payload)`, `get_state(topic)` |
| R1.4 | Build Python `mqtt_device_registry.py` — map MQTT topics to Halbert entity concepts (device_class, entity_id, state, attributes). Pattern follows existing `ha_event_mapper.py` | GLM-5.3 high | Pending | Medium — entity schema may evolve, but the MQTT→entity mapping pattern is stable |
| R1.5 | Build Zigbee2MQTT auto-discovery — detect Z2M on network via MQTT discovery topics (`homeassistant/` or `zigbee2mqtt/`), auto-subscribe to device topics, expose as Halbert entities | GLM-5.3 high | Pending | Medium — Z2M discovery topic format is stable, but new Z2M versions may add fields |
| R1.6 | Wire MQTT device bus into agent tools — `turn_on`, `turn_off`, `set_state` via MQTT publish (parallel to existing `ha_tool.py` HA WebSocket tools) | GLM-5.3 high | Pending | Medium — tool interface follows existing HA tool pattern |
| R1.7 | Wire MQTT events into cognition — `MQTTEventMapper` (parallel to `HAEventMapper`), feed into `CompositeEventMapper` | GLM-5.3 high | Pending | Medium — follows existing event mapper pattern |
| R1.8 | Frontend: MQTT device list in dashboard — show MQTT-discovered devices alongside HA entities, indicate source (MQTT vs HA) | Sonnet high | Pending | Medium — follows existing device card pattern |
| R1.9 | Tests — unit tests for MQTT client, device registry, Z2M discovery; integration test with Mosquitto container | Sonnet high | Pending | Yes |

**Verification:** Halbert discovers and controls a Zigbee device via Zigbee2MQTT + Mosquitto without Home Assistant running.

**What stays in Python (may churn):** The device registry, entity mapping, tool definitions, event mapper. These follow existing patterns but the schema may evolve.
**What's in Rust (won't churn):** The MQTT transport layer (connect, subscribe, publish, reconnect, state cache).

---

## 5. Phase R2 — Kernel Telemetry (halbert-telemetry / eBPF)

**Goal:** Zero-overhead kernel event streaming via eBPF.
**Prerequisite:** R0.
**Risk:** Medium — eBPF programs require Linux kernel >= 5.8, root access, and `libbpf`/`aya` toolchain. Cannot be tested on macOS.
**Product value:** High — this is the "zero-overhead observability" claim in the competitive analysis. Differentiator vs. all competitors.
**Platform:** Linux only. macOS stub returns empty (Endpoint Security framework is future research).

| Task | Description | Model / Effort | Status | Stable? |
|------|-------------|----------------|--------|---------|
| R2.1 | Choose eBPF framework — `aya` (pure Rust) vs `libbpf-rs` (C bindings). Recommend `aya` for pure-Rust stack alignment | Opus high | Pending | Yes — both are stable; `aya` is the Rust-native choice |
| R2.2 | Implement `execve` probe — hook `sys_enter_execve`, stream process creation events (pid, ppid, comm, argv) via ring buffer | Opus xhigh | Pending | Yes — `sys_enter_execve` is a stable kernel tracepoint |
| R2.3 | Implement `oom_mark_victim` probe — hook OOM killer, stream OOM events (pid, comm, score) | Opus high | Pending | Yes — stable tracepoint since kernel 4.15 |
| R2.4 | Implement `tcp_connect` probe — hook `tcp_v4_connect`/`tcp_v6_connect`, stream outbound connection events (pid, saddr, daddr, dport) | Opus xhigh | Pending | Yes — stable kprobe/kretprobe target |
| R2.5 | Implement `vfs_unlink` probe — hook `vfs_unlink`, stream file deletion events (pid, path) | Opus high | Pending | Yes — stable tracepoint |
| R2.6 | Implement ring buffer consumer — parse eBPF ring buffer events, convert to typed `TelemetryEvent` structs, expose via async stream | Opus xhigh | Pending | Yes — ring buffer format is defined by our eBPF programs |
| R2.7 | macOS stub — `TelemetrySource` trait returns empty stream on non-Linux, logs once at startup | Sonnet med | Pending | Yes — stub interface is stable |
| R2.8 | Expose PyO3 interface — Python agent can subscribe to telemetry event stream | Sonnet high | Pending | Yes — `TelemetryEvent` struct is the stable contract |
| R2.9 | Tests — unit tests for event parsing (mock ring buffer data), integration test on Linux VM with real eBPF probes | Opus high | Pending | Yes — event format is defined by our probes |
| R2.10 | Safety review — Fable second opinion on eBPF program safety (no infinite loops, no kernel panics, proper cleanup on unload) | Fable review | Pending | n/a |

**Verification:** On a Linux VM, `halbert-telemetry` streams real `execve` events to a test consumer. No kernel panics on load/unload.

**What's in Rust (won't churn):** The eBPF programs, ring buffer parser, event structs. These are defined by the kernel ABI.
**What stays in Python (may churn):** Which events to react to, how to feed them into the cognition loop, alert thresholds.

---

## 6. Phase R3 — Atomic Safety (halbert-snapshots + halbert-sandbox)

**Goal:** Btrfs snapshot/rollback + Landlock kernel sandboxing for agent actions.
**Prerequisite:** R0. (R2 is recommended but not strictly required — sandbox can work without telemetry.)
**Risk:** Medium — Btrfs ioctls require root and a Btrfs filesystem. Landlock requires kernel >= 5.13. Both are Linux-only.
**Product value:** High — this is the "guaranteed reversibility" and "kernel-enforced blast radius" claims. Core differentiator.
**Platform:** Linux only. macOS stubs return unsupported.

| Task | Description | Model / Effort | Status | Stable? |
|------|-------------|----------------|--------|---------|
| R3.1 | Implement `crates/halbert-snapshots` Btrfs backend — `BTRFS_IOC_SNAP_CREATE`, `BTRFS_IOC_SNAP_DESTROY`, `BTRFS_IOC_SUBVOL_CREATE` ioctl wrappers via `nix` crate | Opus xhigh | Pending | Yes — Btrfs ioctls are stable since 2009 |
| R3.2 | Implement `SnapshotEngine` trait — `create_snapshot(label, path)`, `rollback_snapshot(handle)`, `list_snapshots()`. Btrfs implementation + trait + stub for non-Btrfs | Opus high | Pending | Yes — trait contract is stable (create/rollback/list) |
| R3.3 | Implement `crates/halbert-sandbox` Landlock backend — `landlock_create_ruleset`, `landlock_add_rule`, `landlock_restrict_self` syscall wrappers | Opus xhigh | Pending | Yes — Landlock syscalls are stable since kernel 5.13 |
| R3.4 | Implement `SandboxEngine` trait — `create_sandbox(allowed_paths, allowed_network)`, `enter_sandbox()`, `exit_sandbox()`. Landlock implementation + stub for non-Linux | Opus high | Pending | Yes — trait contract is stable (restrict paths + network) |
| R3.5 | Implement cgroups v2 resource limits — CPU, memory, and PID limits for sandboxed processes | Opus high | Pending | Yes — cgroups v2 is stable since kernel 4.15 |
| R3.6 | Expose PyO3 interface — Python agent can create snapshots and enter sandboxes before executing commands | Sonnet high | Pending | Yes — interface is `snapshot.create()` / `sandbox.enter()` |
| R3.7 | macOS stubs — return `Unsupported` error, log once | Sonnet med | Pending | Yes |
| R3.8 | Tests — unit tests for ioctl wrapping (mock), integration test on Btrfs Linux VM | Opus high | Pending | Yes |
| R3.9 | Safety review — Fable second opinion on Landlock policy generation (no escape paths, proper restriction ordering) | Fable review | Pending | n/a |

**Verification:** On a Btrfs Linux VM, create a snapshot, modify a file, rollback, verify file is restored. Enter a Landlock sandbox, attempt to write outside allowed paths, verify kernel blocks it.

**What's in Rust (won't churn):** The ioctl wrappers, syscall wrappers, trait definitions. These are kernel ABI.
**What stays in Python (may churn):** Which paths to snapshot, which paths to allow in sandbox, when to rollback (the policy logic).

---

## 7. Phase R4 — PyO3 Bridge (halbert-ffi)

**Goal:** Python agent can `import halbert_rs` and call all Rust crates.
**Prerequisite:** R1 + R2 + R3 (wraps all crates).
**Risk:** Low — PyO3/Maturin is well-established. The interface is mechanical.
**Product value:** Critical — without this, the Rust crates are inaccessible to the Python agent.

| Task | Description | Model / Effort | Status | Stable? |
|------|-------------|----------------|--------|---------|
| R4.1 | Set up `crates/halbert-ffi` with `pyo3` + `maturin` build config | Sonnet high | Pending | Yes — PyO3/Maturin is stable |
| R4.2 | Expose `halbert_rs.mqtt` module — `MqttClient`, `DeviceStateCache` Python classes wrapping Rust implementations | Sonnet high | Pending | Yes — mirrors Rust trait interface |
| R4.3 | Expose `halbert_rs.telemetry` module — `TelemetryStream` async iterator wrapping Rust event stream | Sonnet xhigh | Pending | Yes — async bridge is the only non-trivial part |
| R4.4 | Expose `halbert_rs.snapshots` module — `SnapshotEngine` Python class | Sonnet high | Pending | Yes |
| R4.5 | Expose `halbert_rs.sandbox` module — `SandboxEngine` Python class with context manager support (`with sandbox.enter(): ...`) | Sonnet high | Pending | Yes |
| R4.6 | Build and publish wheel — `maturin build --release`, verify `pip install` works | Sonnet high | Pending | Yes |
| R4.7 | Tests — Python integration tests calling each Rust module, verify round-trip data integrity | Sonnet high | Pending | Yes |

**Verification:** `python -c "import halbert_rs; print(halbert_rs.mqtt.MqttClient)"` works. All modules importable.

---

## 8. Phase R5 — halbertd Daemon (systemd + MCP + wires all crates)

**Goal:** `halbertd` as a systemd/launchd service providing eBPF telemetry, Btrfs snapshots, Landlock sandboxing, and the OS-native MCP server.
**Prerequisite:** R4 (needs all crates accessible).
**Risk:** Medium — system service packaging, privilege management, MCP protocol extension.
**Product value:** Critical — this IS the near-term "HalbertOS." Without it, the kernel features are library-only.

| Task | Description | Model / Effort | Status | Stable? |
|------|-------------|----------------|--------|---------|
| R5.1 | Design `halbertd` architecture — daemon process, IPC socket (`/var/run/halbert.sock`), privilege separation (root for kernel ops, unprivileged for MCP) | Opus xhigh | Pending | Medium — daemon architecture is a design decision |
| R5.2 | Implement systemd unit file — `halbertd.service` with proper dependencies (After=network.target, Requires=Btrfs mount for snapshots) | Sonnet high | Pending | Yes — systemd unit format is stable |
| R5.3 | Implement launchd plist (macOS) — `ai.halbert.halbertd.plist` with KeepAlive and RunAtLoad | Sonnet high | Pending | Yes — launchd plist format is stable |
| R5.4 | Implement Unix socket IPC server — JSON-RPC 2.0 over Unix domain socket, auth via socket permissions (0660, group `halbert`) | Opus high | Pending | Yes — JSON-RPC 2.0 is a stable spec |
| R5.5 | Wire telemetry stream into daemon — `halbertd` subscribes to eBPF events, exposes via IPC `telemetry.subscribe` method | Opus high | Pending | Yes — follows R2 interface |
| R5.6 | Wire snapshot engine into daemon — `halbertd` exposes `snapshot.create`, `snapshot.rollback`, `snapshot.list` via IPC | Opus high | Pending | Yes — follows R3 interface |
| R5.7 | Wire sandbox engine into daemon — `halbertd` exposes `sandbox.create`, `sandbox.enter` via IPC. Daemon handles privilege escalation for Landlock setup | Opus xhigh | Pending | Yes — follows R3 interface |
| R5.8 | Extend MCP server with `os://` tools — `halbert.query_rag`, `halbert.preview_blast_radius`, `halbert.create_atomic_snapshot`, `halbert.execute_transactional_step`. Wire into existing `halbert_core/mcp/server.py` | Opus xhigh | Pending | Medium — tool definitions are new, but MCP protocol is stable |
| R5.9 | Implement `halbertd` CLI — `halbertd start/stop/status/snapshot list/rollback <id>` | Sonnet high | Pending | Yes |
| R5.10 | Package for apt (Debian/Ubuntu) — `.deb` with systemd unit, postinst script | Sonnet high | Pending | Yes |
| R5.11 | Package for pacman (Arch) — `PKGBUILD` with systemd unit | Sonnet high | Pending | Yes |
| R5.12 | Package for Homebrew (macOS) — `Formula` with launchd plist | Sonnet high | Pending | Yes |
| R5.13 | Tests — integration test: start daemon, call IPC methods, verify responses | Opus high | Pending | Yes |
| R5.14 | Security review — Fable second opinion on daemon privilege model, IPC auth, MCP egress boundary | Fable review | Pending | n/a |

**Verification:** `sudo systemctl start halbertd` on a Linux VM. `halbertd status` shows running. MCP client can call `halbert.create_atomic_snapshot` and get a snapshot handle.

---

## 9. Phase R6 — Deployment Paths (sidecar + HA Add-on + OS-MCP)

**Goal:** Document and package all three near-term deployment paths.
**Prerequisite:** R5 (needs `halbertd` for Path 2).
**Risk:** Low — mostly documentation and packaging.
**Product value:** High — enables user adoption across all three paths.

| Task | Description | Model / Effort | Status | Stable? |
|------|-------------|----------------|--------|---------|
| R6.1 | Sidecar docker-compose template — `docker-compose.yml` with Halbert + HA Container + Z2M + Mosquitto, documented in `deploy/sidecar/` | Sonnet high | Pending | Yes — docker-compose format is stable |
| R6.2 | Sidecar documentation — `deploy/sidecar/README.md` with setup guide, prerequisites, troubleshooting | Sonnet med | Pending | Yes |
| R6.3 | HA Add-on package — `Dockerfile`, `config.yaml` (HA Supervisor format), `run.sh` entrypoint. Package for HACS store | Sonnet xhigh | Pending | Medium — HA Add-on format is stable but Supervisor API may evolve |
| R6.4 | HA Add-on documentation — setup guide, limitations (no kernel access), graduation path to Path 1/2 | Sonnet med | Pending | Yes |
| R6.5 | OS-native MCP server documentation — `claude mcp add halbert`, `cursor mcp config`, Warp-CLI integration guide | Sonnet high | Pending | Yes |
| R6.6 | OS-native MCP auto-registration — detect installed AI CLIs (Claude Code, Cursor, Warp) and offer to register `halbert` MCP server | Sonnet high | Pending | Medium — CLI config formats may change |
| R6.7 | Integration test — full sidecar deployment on Linux VM: `docker-compose up`, verify Halbert sees HA entities + MQTT devices | Opus high | Pending | Yes |

**Verification:** A user can follow the sidecar README and get Halbert + HA + Z2M running on one box in under 30 minutes. A HAOS user can install the Halbert Add-on from HACS.

---

## 10. Phase R7 — Turnkey Appliance (north-star, gated)

**Goal:** Flashable HalbertOS appliance image.
**Prerequisite:** R1-R6 complete + founder approval.
**Risk:** High — mkosi image building, UKI signing, dm-verity.
**Product value:** Medium — convenience for dedicated appliance users. Not required for the core value proposition.
**Status:** **North-star. Do not start until R1-R6 are proven in production.**

| Task | Description | Model / Effort | Status |
|------|-------------|----------------|--------|
| R7.1 | mkosi build recipe — Arch or Fedora base, `halbertd` pre-installed, Btrfs default filesystem | Opus xhigh | Gated |
| R7.2 | Pre-configure docker-compose — HA + Z2M + Mosquitto template ready on first boot | Sonnet high | Gated |
| R7.3 | First-boot setup wizard — SSH + Halbert dashboard for HA URL, MQTT broker, model config | Opus high | Gated |
| R7.4 | Signed UKI boot — unified kernel image with Halbert recovery hooks | Opus xhigh | Gated |
| R7.5 | dm-verity /usr partition — read-only, verified OS image layer | Opus xhigh | Gated |
| R7.6 | QEMU/KVM test image — bootable VM image for testing without hardware | Sonnet high | Gated |

**Verification:** Flash image to USB, boot on a mini-PC, Halbert dashboard accessible on first boot.

---

## 11. Explicitly Deferred (North-Star, Not in This Plan)

These items from the experimental docs are explicitly deferred per founder
decision D7. They are tracked here for visibility but have no model/effort
assignment and no engineering time allocated.

| Item | Why deferred | Revisit when |
|------|-------------|--------------|
| Custom kernel with eBPF-LSM policies baked in | Multi-year effort, requires OS engineering team | `halbertd` proven in production for 12+ months |
| Wayland compositor (smithay/wlroots) | Enormous effort, Tauri webview covers UI need | Never, unless webview proves insufficient |
| `halbertd` as PID 1 | Only meaningful with custom distro | R7 appliance image proves viable |
| Custom initramfs sentinel | Only meaningful with custom distro | R7 appliance image proves viable |
| Native Matter controller (`rs-matter`) | `rs-matter` not production-ready for controllers, no 1.0 API freeze | `rs-matter` reaches 1.0 stability |
| BLE native support (`btleplug`) | Multi-device reliability is months of work | User demand justifies the investment |
| Windows platform (ETW, VSS, ConPTY, DirectML) | Second full platform engineering effort | `halbertd` proven on Linux + macOS for 12+ months |
| APFS snapshot transactions | Private SPIs, notarization risk | Apple publishes a stable public API |
| Z-Wave JS native client | Trivial but not on critical path | R1 MQTT bus proves the native device pattern |

---

## 12. Sync Points with MASTER-TODO

This plan intersects with existing MASTER-TODO items:

| MASTER-TODO item | This plan | Relationship |
|------------------|-----------|--------------|
| U2 — Voice / Auditory Cortex (Rust AEC) | R0-R4 infrastructure | AEC work in `src-tauri/audio_capture.rs` is separate from the crates/ workspace but benefits from the PyO3 bridge pattern |
| U6 — Home Automation Simplification (S1-S7) | R1 (MQTT device bus) | R1 makes HA architecturally optional, which is the end state U6 is working toward. U6 removes HA dependencies from the home variant; R1 provides the alternative device bus |
| Response Modality & Voice Path items | None | These are Python/React work, not Rust. No overlap. |
| `HALBERT_MODEL` env var wiring | None | Python-only, no Rust involvement. |

**Recommended execution order:**
1. Finish in-flight U1-U6 batches (Python/React work, no Rust dependency)
2. Start R0 (crates scaffolding) — can run in parallel with U-batches
3. Start R1 (MQTT bus) after R0 — delivers Layer 2, the highest product value
4. Start R2 (eBPF) in parallel with R1 if a Linux machine is available
5. R3-R6 follow sequentially after R1+R2

---

## 13. What Qualifies for Rust vs. Stays in Python (Reference)

### In Rust (stable interfaces, won't churn)

| Component | Interface | Stability proof |
|-----------|-----------|-----------------|
| MQTT transport | MQTT 3.1.1/5.0 (OASIS standard) | 25+ years, frozen spec |
| eBPF probes | Kernel tracepoints (`sys_enter_execve`, etc.) | Stable kernel ABI |
| Btrfs snapshots | Btrfs ioctls (`BTRFS_IOC_SNAP_*`) | Stable since 2009 |
| Landlock sandbox | Landlock syscalls | Stable since kernel 5.13 (2021) |
| cgroups v2 | cgroups v2 filesystem interface | Stable since kernel 4.15 |
| PyO3 bridge | PyO3/Maturin ABI | Stable, well-maintained |
| Unix socket IPC | JSON-RPC 2.0 over Unix domain socket | Both are stable specs |
| PTY plumbing | POSIX `forkpty`/`openpty` | Stable since 1980s |

### In Python (application logic, may churn)

| Component | Why it stays in Python |
|-----------|----------------------|
| Agent state machine / CRAG | High-velocity, LangGraph-style logic, idiomatic Python |
| Prompt assembly | Still evolving (modality/voice work, XML prompt system) |
| RAG / vector search | Mid-migration (ChromaDB retirement), retrieval backend changing |
| Discovery scanners (24 files) | I/O-bound, not CPU-bound. Rust won't help. Schema still evolving. |
| Device registry / entity mapping | Application logic on top of stable transport. Schema may evolve. |
| Event mappers (HA, MQTT) | Application logic, follows existing patterns but may change |
| Dashboard frontend | React/TypeScript, already fast, Tauri shell is already Rust |
| Tool definitions | Agent tool interface, high-velocity |
| Safety policy generation | Deciding which paths to snapshot/allow is application logic |

### The boundary rule

> If the interface is defined by a **kernel ABI, a published standard, or a
> stable protocol spec**, it goes in Rust.
> If the interface is defined by **our application's evolving logic**, it
> stays in Python.
> The Rust crate exposes a stable trait; Python implements the policy on top.

---

## 14. Effort Summary

| Phase | Tasks | Estimated effort | Model mix |
|-------|-------|-----------------|-----------|
| R0 — Foundation | 8 | ~2 days | Sonnet med |
| R1 — MQTT Device Bus | 9 | ~2 weeks | Sonnet xhigh + GLM-5.3 high |
| R2 — eBPF Telemetry | 10 | ~3 weeks | Opus xhigh + Fable review |
| R3 — Atomic Safety | 9 | ~2 weeks | Opus xhigh + Fable review |
| R4 — PyO3 Bridge | 7 | ~1 week | Sonnet xhigh |
| R5 — halbertd Daemon | 14 | ~3 weeks | Opus xhigh + Fable review |
| R6 — Deployment Paths | 7 | ~1 week | Sonnet high |
| **R1-R6 total** | **56** | **~12 weeks** | |
| R7 — Appliance (gated) | 6 | ~4 weeks | Opus xhigh |

**Parallelization opportunity:** R1 and R2 are independent. If two agents
work in parallel (R1 on any machine, R2 on a Linux VM), the R1-R6 timeline
compresses to ~9 weeks.

---

## 15. Open Questions

### Q1: `aya` vs `libbpf-rs` for eBPF?

`aya` is pure Rust (no C dependencies), aligns with the Universal Rust Core
vision, and is actively maintained. `libbpf-rs` is more mature and has more
examples but requires libbpf C library. **Recommendation: `aya`** for
architectural consistency, but this is an Opus-level design decision (R2.1).

### Q2: Should `halbertd` be a single binary or multiple?

Single binary with subcommands (`halbertd telemetry`, `halbertd snapshot`,
`halbertd mcp`) vs separate daemons. **Recommendation: single binary** —
simpler packaging, shared state, one systemd unit. But this is an Opus-level
design decision (R5.1).

### Q3: When does the Python agent start consuming Rust crates?

After R4 (PyO3 bridge). The Python agent's `requirements.txt` gains
`halbert_rs` as a dependency. The agent gracefully degrades if `halbert_rs`
is not installed (falls back to pure-Python scanners, no eBPF, no snapshots).

### Q4: How does `halbertd` interact with the existing Tauri desktop app?

The Tauri app (which is already Rust) can link the crates directly (Cargo
dependency). The Python agent uses PyO3. `halbertd` uses the crates as a
standalone binary. All three consume the same `crates/halbert-*` code.

### Q5: Should we create a separate repo for `crates/` or keep in monorepo?

**Recommendation: monorepo.** The crates are tightly coupled to Halbert's
trait contracts. A separate repo would create version sync overhead. The
`crates/` directory at repo root, alongside `halbert_core/`, is the right
structure (matches the experimental docs' proposed layout).
