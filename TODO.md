# Halbert Master Roadmap & Engineering TODO

> **SUPERSEDED 2026-09-02 by `ROADMAP.md` and `DECISIONS.md`.** Kept as history. WS1.3 and WS1.5 landed; WS-2 (multi-session tabs) is replaced by the Presence Pill body switch (shell review §9.5); nothing here is scheduled.

**Status:** Active  
**Last Updated:** August 2026  
**Architecture Reference:** [`documentation/design/macos-strategy.md`](documentation/design/macos-strategy.md) & [`GEMINI-Opinion.md`](GEMINI-Opinion.md)

---

## 🎯 Progress Overview

```
[░░░░░░░░░░] 0% Complete (19 Tasks Pending, 0 In Progress, 0 Done)
```

| Workstream | Focus Area | Status | Priority |
| :--- | :--- | :--- | :--- |
| **WS-1** | Baseline Cleanup & Build Stabilization | 📋 Planned | 🔴 P0 |
| **WS-2** | Universal Multi-Session Client | 📋 Planned | 🔴 P0 |
| **WS-3** | RAG Corpus Expansion (1.4MB → 50MB+) | 📋 Planned | 🟡 P1 |
| **WS-4** | SourcePrep Epistemic & Graph Integration | 📋 Planned | 🟡 P1 |
| **WS-5** | "Configuration as Physiology" & Hidden Rules | 📋 Planned | 🟡 P1 |
| **WS-6** | Dual macOS Packaging (LemonSqueezy & App Store) | 📋 Planned | 🟢 P2 |

---

## 📋 Workstream Breakdown

### Workstream 1: Baseline Cleanup & Build Stabilization (P0)
*Objective: Unblock frontend builds, eliminate dead scaffolding, unify chat execution, and decompose monolithic UI files.*

- [ ] **WS1.1 Fix Frontend Build Tracking**: Remove bare `lib/` rule from `.gitignore` and ensure `frontend/src/lib/api.ts` and `frontend/src/lib/utils.ts` are committed and tracked.
- [ ] **WS1.2 Decommission Dead Runtime Scaffolds**: Remove unused `runtime/langgraph_engine.py` and legacy `runtime/graph.py` files.
- [ ] **WS1.3 Unify Chat Hot Path**: Retire the orphaned 4,240-line `dashboard/routes/chat.py` in favor of the clean Phase 36 SSE state machine in `dashboard/routes/agent.py`.
- [ ] **WS1.4 Purge Deprecated In-Memory RAGPipeline**: Remove the dual-instantiation of the deprecated `rag/pipeline.py` on the live query path.
- [ ] **WS1.5 Settings Monolith Modular Decomposition**: Refactor the monolithic 3,273-line `halbert_core/dashboard/frontend/src/pages/Settings.tsx` into clean, isolated domain tab components in `src/components/settings/tabs/` (`SystemTab`, `KnowledgeTab`, `SafetyTab`, `VisionTab`, `AlertsTab`, `BeingTab`, `AboutTab`, `DebugTab`) with shared types in `types.ts`, reducing `Settings.tsx` to a thin ~120-line coordinator/NavRail shell.

---

### Workstream 2: Universal Multi-Session Client (P0)
*Objective: Allow macOS (Pro & Free) and Linux apps to manage multiple local and remote hosts concurrently.*

- [ ] **WS2.1 Frontend API Decoupling**: Abstract the hardcoded `localhost:8000` base URL into a dynamic `HostConnectionContext`.
- [ ] **WS2.2 Host Manager Profile Store**: Implement local profile management (`id`, `name`, `baseUrl`, `apiKey`, `isLocal`) in the desktop app.
- [ ] **WS2.3 Host Switcher / Tabbed UI**: Build the multi-host switcher component in the desktop app header/sidebar.
- [ ] **WS2.4 First-Person Host Persona Switching**: Ensure switching tabs dynamically adopts the target machine's unique identity (`"I AM <hostname>"`), telemetry, and storage topology.
- [ ] **WS2.5 Secure Remote Transports**: Implement `X-Halbert-Token` header authentication and verify SSE streaming over LAN, Tailscale, WireGuard, and SSH tunnels.

---

### Workstream 3: RAG Knowledge Corpus Expansion (P1)
*Objective: Expand the macOS knowledge base from 1.4 MB to 50+ MB.*

- [ ] **WS3.1 Cross-Platform Data Promotion**: Move platform-agnostic collections (`tldr_man_pages`, `unix_commands`, `git`, `docker`, `aws-cli`, `k8s`, `python`, `devtools`, `networking`) from `data/linux/` to `data/common/`.
- [ ] **WS3.2 Update Platform Manifests**: Update `config/platforms.yml` and `data/manifest.json` to link `data/common/` to macOS builds.
- [ ] **WS3.3 Ingest Darwin System Admin Corpus**: Scrape and index man pages for `launchctl`, `defaults`, `scutil`, `networksetup`, `diskutil`, `tmutil`, `security`, `pmset`.
- [ ] **WS3.4 Ingest Mac Developer Tooling Corpus**: Add dedicated knowledge sets for `brew` (bundle/services/casks), `mas`, `mise`, `asdf`, `pyenv`, `nvm`, `orbstack`, and `colima`.
- [ ] **WS3.5 Ingest Apple Silicon & Security Corpus**: Index documentation for Apple Silicon MLX, Unified Memory, SIP boundaries, TCC permissions, and APFS snapshots.

---

### Workstream 4: SourcePrep Epistemic & Graph Integration (P1)
*Objective: Replace naive ChromaDB chunking with a live structural and epistemic graph.*

- [ ] **WS4.1 Ambient Host Topology (`prep`)**: Wire `prep` to generate an instant structural map of the host OS (running daemons, mount points, network interfaces, active shell).
- [ ] **WS4.2 LOD Search (`prep_search`)**: Integrate Level-Of-Detail search over documentation and AST-parsed configuration files.
- [ ] **WS4.3 Pre-Execution Blast-Radius (`prep_impact`)**: Hook `prep_impact` into the agent's action loop to evaluate downstream dependencies before modifying system configs.
- [ ] **WS4.4 Config & System Hygiene (`prep_audit`)**: Implement automated audits for shadowed PATH entries, conflicting aliases, orphaned configs, and permission drifts.
- [ ] **WS4.5 Autobiographical Memory (`prep_observe`)**: Record operational events, hardware quirks, and diagnostic notes into cross-session memory.
- [ ] **WS4.6 Configuration Rationale ("WhyBrain") (`prep_concepts`)**: Maintain a persistent knowledge graph of *why* specific configuration settings were created.

---

### Workstream 5: "Configuration as Physiology" & Hidden Rules (P1)
*Objective: Give Halbert master ownership over user configuration files and environment debt.*

- [ ] **WS5.1 Mac & Linux Config Inventory Scanner**: Build scanners for dotfiles (`~/.zshrc`, `~/.zshenv`, `~/.config`, `/etc/paths.d`, `~/Library/LaunchAgents`).
- [ ] **WS5.2 Environment & PATH Precedence Visualizer**: Build a precedence tracer that models how `$PATH` and environment variables are inherited and shadowed.
- [ ] **WS5.3 Safe Config Editor & Rollback**: Implement Monaco/search-replace config editor with unified dry-run diffs and automatic snapshot rollbacks.

---

### Workstream 6: Dual macOS Packaging & Distribution (P2)
*Objective: Ship Halbert Pro via LemonSqueezy and Halbert Free Companion via the Mac App Store.*

- [ ] **WS6.1 LemonSqueezy License Validation**: Implement offline-tolerant license key activation for Halbert Pro (macOS).
- [ ] **WS6.2 Unsandboxed Pro Build Pipeline**: Configure Tauri v2 pipeline to output Developer ID signed and notarized `.dmg` binaries with Full Disk Access entitlements.
- [ ] **WS6.3 Sandboxed App Store Build Pipeline**: Configure App Store compliant build with `com.apple.security.network.client` for remote multi-session operation.
- [ ] **WS6.4 Linux Distribution Packaging**: Maintain `.deb`, `.rpm`, and `.AppImage` packaging with full multi-session host and client capabilities.
