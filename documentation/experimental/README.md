# Halbert Experimental Documentation

This folder houses forward-looking technical proposals, architectural thought-experiments, and long-term design blueprints for the Halbert ecosystem.

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




