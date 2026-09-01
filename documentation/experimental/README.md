# Halbert Experimental Documentation

This folder houses forward-looking technical proposals, architectural thought-experiments, and long-term design blueprints for the Halbert ecosystem.

## Maturity & Status Tiers

> **Updated 2026-08-31:** Documents in this folder have been reviewed and
> categorized by maturity. Not everything here is near-term actionable — much
> of it is north-star vision. See
> [`.handoff/HA-STRATEGY-SCOPING-AND-DEPLOYMENT-PATHS-2026-08-31.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/HA-STRATEGY-SCOPING-AND-DEPLOYMENT-PATHS-2026-08-31.md)
> for the full scoping decisions.

### Near-term actionable (build now)
- **Rust crates** (`halbert-telemetry`, `halbert-snapshots`, `halbert-sandbox`, `halbert-mqtt`) — deliver value to the existing app on standard distros
- **`halbertd` daemon** — systemd/launchd package providing eBPF, Btrfs, Landlock, MCP server on standard Linux/macOS
- **MQTT device bus** — native Zigbee2MQTT / Mosquitto support (makes HA optional for core devices)
- **Sidecar deployment** — docker-compose template for Halbert + HA + Z2M + Mosquitto on one box
- **HA Add-on** — HACS-distributable package for HAOS user acquisition
- **OS-native MCP server** — `os://` tools for Warp/Claude/Cursor

### North-star / deferred (track as research, no near-term engineering)
- HalbertOS as a custom Linux distro (custom kernel, Wayland compositor, PID 1, initramfs sentinel, dm-verity)
- Native Matter controller (gated on `rs-matter` 1.0 API freeze)
- Windows platform (ETW, VSS, ConPTY, DirectML — second full platform effort)
- APFS snapshot transactions (private SPIs, notarization risk — research only)

## Documents

- [**HalbertOS & Universal Rust Architecture**](file:///Volumes/4TB-BAD/Halbert/documentation/experimental/HALBERT-OS-DISTRO-AND-UNIVERSAL-RUST-ARCHITECTURE.md)
  Explores building an AI-native Linux distribution (HalbertOS) with kernel-level eBPF telemetry, Btrfs atomic copy-on-write rollbacks, Landlock sandboxing, and a Universal Rust Crate Core that seamlessly powers the existing Tauri desktop app, Python agent brain (via PyO3), and native OS daemons.

- [**Universal Cross-Platform Architecture & Rust Migration Roadmap**](file:///Volumes/4TB-BAD/Halbert/documentation/experimental/UNIVERSAL-CROSS-PLATFORM-AND-MIGRATION-ROADMAP.md)
  Defines the two-track strategy (maintaining prototype velocity in Python/React while incrementally migrating performance/security-critical subsystems to Rust), deep integration strategies for the Swift/Apple ecosystem (APFS snapshots, IOKit, MLX, `uniffi-rs`) and Windows 11 / WSL2 (ETW, VSS, ConPTY, DirectML), and the phased milestone roadmap.

- [**Competitive Analysis: AI Operating System Landscape & Strategic Opportunities**](file:///Volumes/4TB-BAD/Halbert/documentation/experimental/COMPETITIVE-ANALYSIS-AI-OS-LANDSCAPE.md)
  Comprehensive audit of the 2026 AI-OS landscape, breaking down desktop AI shells (Deepin/UOS AI, Windows 11 Copilot+, Apple Intelligence), infrastructure appliances (RHEL AI, Ubuntu AI), autonomous device OSs (Open Interpreter 01), and academic literature (AIOS, OS-World, OS-Copilot, eBPF agent telemetry). Identifies key competitor blindspots and Halbert's moat.

- [**Singular Entity, Home Assistant & HalbertOS: Cross-Platform Node Architecture**](file:///Volumes/4TB-BAD/Halbert/documentation/experimental/SINGULAR-ENTITY-HOME-ASSISTANT-AND-HALBERTOS-ECOSYSTEM.md)
  Resolves the ecosystem topology across desktop apps (macOS, Windows, Linux), Home Assistant (HACS guest integration vs. HalbertOS sovereign host), and edge thin-clients. Shows how the "Singular Entity, Multi-Body" paradigm shares one canonical memory store across devices while Rust native networking/eBPF fortifies IoT security.

- [**OS-Native MCP, Warp-CLI Integration & Native SourcePrep Architecture**](file:///Volumes/4TB-BAD/Halbert/documentation/experimental/OS-NATIVE-MCP-WARP-AND-SOURCEPREP-INTEGRATION.md)
  Blueprint for exposing the operating system as an MCP server (`os://`). Shows how tools like Warp-CLI, Claude Code, and Cursor gain kernel-level telemetry, atomic Btrfs rollbacks, and offline sysadmin RAG, and why embedding SourcePrep as a native OS graph primitive transforms configuration management.

- [**Blue-Sky Architecture: Sentient Computing, Cognitive OS & The Neural Fabric**](file:///Volumes/4TB-BAD/Halbert/documentation/experimental/BLUE-SKY-SENTIENT-SYSTEMS-AND-COGNITIVE-OS.md)
  Explores the 2027–2030 horizon of AI-native operating systems: somatosensory physiology and autonomous nocturnal REM sleep/maintenance, synthetic intent virtual filesystems (`/halbert` VFS), sub-millisecond kernel eBPF reflex arcs, heterogeneous multi-tier neural fabric routing, and zero-knowledge holographic identity reincarnation.

- [**Second-Pass Blue-Sky Feasibility, Cross-Platform Realities & Pragmatic Architecture**](file:///Volumes/4TB-BAD/Halbert/documentation/experimental/SECOND-PASS-FEASIBILITY-AND-PRAGMATIC-BLUE-SKY.md)
  Rigorous feasibility and sanity audit of the 5 Blue-Sky pillars. Grounds them into practical cross-platform architectures (macOS, Windows, Linux, and the existing desktop app): user-owned encrypted cloud backups (iCloud/Google Drive), safe state directories instead of dangerous kernel FUSE mounts, cross-platform fast sentries (EndpointSecurity/ETW), and nightly memory consolidation today.






