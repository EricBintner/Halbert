# Halbert macOS Strategy, Configuration Physiology & Multi-Session Architecture

> **Alignment note (2026-09-02):** §2 (tiering) stands. §1.3 and §4 ("Universal Multi-Session Client" with tabs each adopting "I AM <hostname>") are superseded by the singular-entity design and shell review §9.5: bodies of one Halbert are switched from the Presence Pill (Singular Entity), separate entities only in Independent Node mode, and the Free companion is the same app with no local backend connected to one paired body. No tab client exists in code. See `CORE-CONCEPTS-AND-ALIGNMENT-2026-09-02.md` §2.2.

**Date:** August 2026  
**Status:** Approved Design & Architectural Plan  
**Target Platforms:** macOS (Pro & Free), Linux (Flagship)

---

## 1. Executive Summary

This document establishes the strategic and architectural roadmap for Halbert on macOS and defines the **Universal Multi-Session Client** and **Configuration Physiology Engine** spanning both macOS and Linux.

### Key Decisions:
1. **Bifurcated macOS Distribution:**
   * **Halbert Pro (macOS)**: Paid direct-distribution app via **LemonSqueezy** (Notarized Developer ID, unsandboxed). Delivers full "Host Custodian" power: Full Disk Access, dotfile and environment management, Homebrew/launchd automation, and local Apple Silicon MLX inference.
   * **Halbert Free / Companion (Mac App Store)**: Sandboxed edition compliant with Apple App Store rules. Serves as a native **Multi-Session Remote Client** for managing networked Linux instances and homelabs, plus basic local queries and upgrade discovery.
2. **Deep Configuration & Hidden Rule Discovery ("Configuration as Physiology"):**
   * Solves configuration sprawl on macOS and Linux by mapping, surfacing, auditing, and organizing dotfiles, version managers (`mise`, `asdf`, `nvm`, `pyenv`, `brew`), shell environments (`zsh`, `bash`, `/etc/paths.d`), and hidden app configs using SourcePrep graph primitives.
3. **Universal Multi-Session Client (macOS & Linux):**
   * Both macOS (Pro & Free) and Linux apps can open multiple concurrent session tabs connected to different Halbert backends (e.g. Local Machine, Remote Ubuntu Devbox, Homelab Storage Server).
   * Each session tab adopts the authentic first-person identity (`"I AM <hostname>"`) and state of the target machine.

---

## 2. macOS Tiering Strategy: LemonSqueezy Pro vs. App Store Free

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                 DISTRIBUTION MATRIX                                    │
├────────────────────────────────────────────┬───────────────────────────────────────────┤
│    LEMONSQUEEZY PRO (Direct / Notarized)   │        MAC APP STORE (Free Companion)     │
├────────────────────────────────────────────┼───────────────────────────────────────────┤
│ • Unsandboxed Developer ID binary          │ • Strict Apple App Sandbox                │
│ • Full Disk Access & Terminal execution   │ • Zero low-level OS access                │
│ • Dotfile, Homebrew, launchd management    │ • Primary Role: Remote Linux Client       │
│ • Local MLX / Ollama / SourcePrep engine   │ • Secondary Role: Basic AI query / RAG    │
│ • Full "Host Custodian" capabilities       │ • Strategic Role: Funnel & Homelab GUI    │
│ • Multi-Session Remote Client enabled      │ • Multi-Session Remote Client enabled     │
└────────────────────────────────────────────┴───────────────────────────────────────────┘
```

### 2.1 The Sandbox Dilemma
Apple's App Store Sandbox prohibits:
* Arbitrary reads/writes to `~/.config`, `~/.zshrc`, `~/.ssh`, `~/.aws`, `/etc`, or `~/Library/LaunchAgents` without individual user-prompt file pickers.
* Spawning subprocesses (`brew`, `launchctl`, `git`, shell scripts, `sudo`).
* Reading system-level hardware sockets or telemetry without entitlements.

**Conclusion**: The full sovereign host custodian vision cannot exist inside the App Store sandbox. The Pro version must be distributed directly.

### 2.2 Product Tier Comparison

| Feature | macOS Pro (LemonSqueezy) | macOS Free (App Store) | Linux Flagship |
| :--- | :--- | :--- | :--- |
| **Distribution** | Direct download (.dmg) | Mac App Store | Direct / Package Managers |
| **Pricing** | Paid (LemonSqueezy) | Free / Free-tier | Open Source / Flagship |
| **Sandboxing** | Unsandboxed (Full Disk Access) | App Sandbox | Unsandboxed |
| **Local Config Management** | Full (`~/.zshrc`, `paths.d`, dotfiles) | None (Sandboxed) | Full (`/etc`, dotfiles, systemd) |
| **Local Service Control** | `launchd`, Homebrew services | None | `systemd`, containers, init |
| **Local Hardware Telemetry** | IOKit, `powermetrics` (via sudo) | Basic `psutil` battery | `/sys/class/hwmon`, GPU, thermals |
| **Local AI Inference** | Apple Silicon MLX, Ollama | None / Cloud API only | Ollama, llama.cpp, CUDA, ROCm |
| **Multi-Session Remote Client**| **Full (Local + Remote Hosts)** | **Full (Remote Hosts)** | **Full (Local + Remote Hosts)** |
| **RAG Knowledge Base** | macOS + BSD + Common + Host Graph | Basic macOS Help (~1.4 MB) | 40+ Collections (~43 MB) + Graph |

---

## 3. Configuration as Physiology & Hidden Rule Discovery

Both macOS and Linux users accumulate "configuration debt"—scattered dotfiles, overridden `$PATH` variables, conflicting version managers, and orphaned configuration files.

```
                  ┌────────────────────────────────────────────────────────┐
                  │                 THE CONFIGURATION JUNGLE               │
                  └───────────────────────────┬────────────────────────────┘
                                              │
         ┌───────────────────┬────────────────┴───────────────────┬───────────────────┐
         ▼                   ▼                                    ▼                   ▼
   Shell & Envs        Version Managers                     Tool Configs        System & Daemons
• ~/.zshrc, .zshenv   • Homebrew (Brewfile, casks)         • ~/.config/*       • ~/Library/LaunchAgents
• .zprofile, .bashrc  • mise, asdf, nvm, pyenv             • ~/.gitconfig      • /Library/LaunchDaemons
• /etc/paths          • conda, pipx, cargo, rbenv          • ~/.ssh, ~/.aws    • /etc/*.d drop-ins
• /etc/paths.d/*      • global vs local tool versions      • Cursor, Claude    • systemd / launchctl
```

### 3.1 Core Capabilities

1. **Ambient Config Discovery & Atlas (`prep`)**:
   * Auto-discovers and indexes all configuration files across `$HOME`, `~/.config`, `/etc`, and launch daemon paths.
   * Identifies orphaned configs from tools that are no longer installed.
2. **Precedence & Conflict Resolution Engine**:
   * Traces environment variable evaluation order (e.g. `$PATH` precedence across `.zshenv` → `.zprofile` → `/etc/paths` → `.zshrc`).
   * Flags duplicate aliases, conflicting shell functions, and mismatched Python/Node runtime versions.
3. **Hygiene & Sanity Audits (`prep_audit`)**:
   * Scans for syntax errors, deprecated flags, broken symlinks, and unsafe permission bits (e.g. `chmod 777` on SSH/GPG keys).
4. **Blast-Radius & Safe Diffs (`prep_impact` + Rollbacks)**:
   * Analyzes downstream impacts before applying any setting change.
   * Employs dry-run unified diffs with automatic backup snapshots and single-click rollback.

---

## 4. Universal Multi-Session Architecture

The multi-session architecture allows any Halbert frontend (macOS Pro, macOS Free, or Linux Flagship) to manage multiple machines simultaneously.

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                        MULTI-SESSION CLIENT ARCHITECTURE                               │
├────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                        │
│   ┌────────────────────────────────────────────────────────────────────────────────┐   │
│   │               Halbert Desktop UI (macOS Pro / Free / Linux)                    │   │
│   │                                                                                │   │
│   │   [ Tab 1: Local Host ]       [ Tab 2: Linux Devbox ]    [ Tab 3: Homelab Server]│   │
│   └───────────────┬───────────────────────────┬───────────────────────────┬────────┘   │
│                   │                           │                           │            │
│       REST / SSE  │               REST / SSE  │               REST / SSE  │            │
│       (localhost) │               (LAN / VPN) │               (Tailscale) │            │
│                   ▼                           ▼                           ▼            │
│   ┌───────────────────────┐   ┌───────────────────────┐   ┌────────────────────────┐   │
│   │   Local Backend       │   │   Ubuntu Devbox       │   │   Debian Homelab       │   │
│   │   "I AM macbook-pro"  │   │   "I AM titan-work"   │   │   "I AM storage-box"   │   │
│   │   • zsh / brew        │   │   • systemd / docker  │   │   • ZFS / KVM / cron   │   │
│   │   • Apple Silicon MLX │   │   • Dual RTX 4090 GPU │   │   • Ollama server      │   │
│   └───────────────────────┘   └───────────────────────┘   └────────────────────────┘   │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

### 4.1 Client-Server Decoupling
* **API Client Abstraction**: The frontend replaces hardcoded `localhost:8000` references with a configurable `HostConnectionContext`.
* **Host Profiles**: Host connection profiles are stored locally:
  ```json
  {
    "hosts": [
      {
        "id": "local",
        "name": "Local Host",
        "baseUrl": "http://127.0.0.1:8000",
        "apiKey": "local-token",
        "isLocal": true
      },
      {
        "id": "devbox-ubuntu",
        "name": "Titan Devbox",
        "baseUrl": "http://100.64.0.5:8000",
        "apiKey": "halbert-sec-token-xyz",
        "isLocal": false
      }
    ]
  }
  ```
* **Authentication**: Token-based bearer authentication (`X-Halbert-Token` or `Authorization: Bearer <token>`) with optional mTLS.
* **Network Transports**: Standard REST and SSE over LAN, Tailscale, WireGuard, or SSH port forwarding (`ssh -L 8000:localhost:8000 user@remote`).

### 4.2 First-Person Host Persona per Session
When switching tabs:
* The active session queries the remote `/api/persona/status` and `/api/discovery`.
* Halbert dynamically speaks as that specific computer:
  * **Tab 1**: *"I am MacBook Pro (M3 Max, 64GB). All Homebrew packages are up to date."*
  * **Tab 2**: *"I am Titan Workstation (Ubuntu 24.04, 2x RTX 4090). 4 Docker containers running, GPU temp 42°C."*

---

---

## 5. RAG Knowledge Expansion Blueprint (1.4 MB → 50+ MB)

The legacy macOS build shipped with an artificially minimal ~1.4 MB knowledge corpus. The expanded strategy scales this to 50+ MB through two concurrent phases:

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                 EXPANDED RAG KNOWLEDGE CORPUS                          │
├────────────────────────────────────────────┬───────────────────────────────────────────┤
│       1. CROSS-PLATFORM PROMOTION          │       2. DEDICATED macOS EXPANSION        │
│   (Migrate from data/linux → data/common)  │           (New macOS Datasets)            │
├────────────────────────────────────────────┼───────────────────────────────────────────┤
│ • Unix CLI & TLDR Man Pages (~12 MB)       │ • Darwin System Admin CLI (~8 MB)         │
│ • Git, SSH, Vim/Neovim, Zsh (~6 MB)        │ • macOS Developer Envs & Runtimes (~10 MB)│
│ • Docker, Lima, OrbStack, Podman (~8 MB)   │ • Apple Silicon, MLX & Metal (~5 MB)      │
│ • Cloud CLIs (AWS, GCP, Kube, Helm) (~8 MB)│ • macOS Security, SIP, TCC, APFS (~4 MB)  │
│ • Python, Node, Rust, Go Tooling (~6 MB)   │ • Troubleshooting & Error Atlas (~5 MB)   │
└────────────────────────────────────────────┴───────────────────────────────────────────┘
```

### 5.1 Cross-Platform Promotion (`data/linux/` → `data/common/`)
Promote ~35 MB of existing developer and CLI knowledge into `data/common/` so it is automatically included in macOS and Linux builds:
* `tldr_man_pages.jsonl` & `unix_commands.jsonl` (POSIX standard utilities)
* `git-docs`, `docker-docs`, `devtools-docs`, `database-docs`, `caching-docs`
* `aws-cli`, `kubernetes-docs`, `helm-k8s`
* `python-docs`, `shell-scripting-docs`, `ssh-docs`, `networking-docs` (`curl`, `openssl`, `dig`, `tcpdump`)

### 5.2 Dedicated macOS & BSD Expansion Datasets
1. **Darwin / macOS Native Administration CLI**:
   * Complete man pages and command syntaxes for `launchctl`, `defaults`, `scutil`, `networksetup`, `diskutil` (APFS partitions/snapshots), `tmutil` (Time Machine), `pmset` (power/thermal management), `sysadminctl`, `security` (Keychain CLI), `softwareupdate`, `xcode-select`.
2. **Mac Developer Runtimes & Version Managers**:
   * Deep guides for `brew` (formulas, casks, bundle, services), `mas` (App Store CLI), `mise`, `asdf`, `nvm`, `pyenv`, `rustup`/`cargo`, `pipx`, `colima`, `orbstack`.
3. **Apple Silicon & Hardware Optimization**:
   * Apple Silicon unified memory architecture, MLX framework documentation, Metal Performance Shaders, Rosetta 2 translation.
4. **macOS Security & Storage Topology**:
   * SIP boundaries, TCC privacy entitlements (Full Disk Access, Accessibility), Gatekeeper/Notarization rules, APFS encryption (FileVault) and snapshot retention.
5. **Common Mac Error Atlas**:
   * Common macOS failure patterns (PATH shadowing, Xcode Command Line Tools loops, Homebrew permission errors, Keychain unlock timeouts, DNS cache flushing via `mDNSResponder`).

---

## 6. SourcePrep Tooling Integration Architecture

SourcePrep replaces naive ChromaDB vector chunking with a live structural and epistemic graph, bridging static documentation and the live host operating environment.

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                         SOURCEPREP INTEGRATION PIPELINE                                │
├────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                        │
│   [ User: "My Python command is picking up Apple's python3 instead of pyenv 3.12" ]    │
│                                    │                                                   │
│                                    ▼                                                   │
│   ┌────────────────────────────────────────────────────────────────────────────────┐   │
│   │                        SOURCEPREP MCP ENGINE                                   │   │
│   │                                                                                │   │
│   │   1. prep          ──▶ Real-time Host Topology (OS: macOS, Shell: zsh)         │   │
│   │   2. prep_search   ──▶ Indexes ~/.zshrc, /etc/paths.d, pyenv shims at LOD 1-3  │   │
│   │   3. prep_audit    ──▶ Detects: /usr/bin prepended before ~/.pyenv/shims       │   │
│   │   4. prep_concepts ──▶ Retrieves WHY: "User previously added Homebrew in rc"   │   │
│   └────────────────────────────────┬───────────────────────────────────────────────┘   │
│                                    │ Synthesized Structural Context                    │
│                                    ▼                                                   │
│   ┌────────────────────────────────────────────────────────────────────────────────┐   │
│   │                         COGNITIVE CORE (Haloysius)                             │   │
│   │   • Local LLM (Ollama or Apple MLX)    formulates exact PATH fix               │   │
│   └────────────────────────────────┬───────────────────────────────────────────────┘   │
│                                    │ Proposed Diff                                     │
│                                    ▼                                                   │
│   ┌────────────────────────────────────────────────────────────────────────────────┐   │
│   │                        PRE-EXECUTION VALIDATION                                │   │
│   │   5. prep_impact   ──▶ Blast-Radius Check (Will this break brew or npm?)       │   │
│   │   • Safe Diff Preview + User 1-Click Approval                                  │   │
│   └────────────────────────────────┬───────────────────────────────────────────────┘   │
│                                    │ Post-Execution Memory                             │
│                                    ▼                                                   │
│   │   6. prep_observe  ──▶ Logs: "Moved pyenv shims before /usr/bin in ~/.zprofile" │   │
│   └────────────────────────────────────────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

### The 6 SourcePrep Primitives in Halbert

| SourcePrep Tool | Role in Static Knowledge (RAG) | Role in Live System (Host Custodian) |
|:---|:---|:---|
| **`prep`** *(Structural Atlas)* | Provides a structural index of documentation categories and topic hierarchies. | Maps the live host: running daemons (`launchd`/`systemd`), active mount points, `$PATH`, active shell, and network interfaces. |
| **`prep_search`** *(LOD Search)* | Level-Of-Detail search over documentation (returns condensed summaries first, zooming into full syntax only when needed). | AST-aware semantic search over config files (`~/.config`, `/etc`, dotfiles, plist files) rather than raw grep. |
| **`prep_impact`** *(Blast Radius)* | Cross-references command side-effects documented in man pages. | **Dependency Analysis before Edits**: Calculates what services, tools, or shims will be affected before modifying a config file. |
| **`prep_audit`** *(Hygiene Engine)* | Validates documentation consistency and flag deprecations. | **Config Hygiene**: Detects shadowed PATH entries, conflicting aliases, orphaned configs from uninstalled apps, and broken symlinks. |
| **`prep_observe`** *(Memory Tape)* | Indexes newly ingested documentation changelogs. | **Cross-Session Autobiographical Memory**: Records operations performed, hardware quirks, and diagnostic notes so Halbert remembers its own history. |
| **`prep_concepts`** *(WhyBrain)* | Maps high-level architectural concepts to command-line tools. | **Configuration Rationale**: Records *why* a setting was changed (e.g. *"Set MTU to 1420 because ISP fragments WireGuard packets"*). |

---

## 7. Implementation Roadmap

### Phase 1: Foundation & Frontend Decoupling
1. Fix frontend baseline (`.gitignore` rule for `src/lib/`).
2. Decouple frontend API layer from `localhost:8000` to support multi-session host switching.
3. Add `HostManager` UI in the desktop header/sidebar to add, test, and switch between remote Halbert instances.

### Phase 2: RAG Corpus Promotion & macOS Expansion
1. Promote cross-platform datasets from `data/linux` to `data/common` (Unix CLI, Git, Docker, Kubernetes, Python, DevTools).
2. Add macOS-specific JSONL scrapers (Darwin admin CLI, Homebrew/mas, Apple Silicon/MLX, APFS/SIP).

### Phase 3: Configuration Physiology & SourcePrep Integration
1. Implement macOS config inventory scanner (`~/.zshrc`, `~/.config`, `/etc/paths`, `~/Library/LaunchAgents`, version managers).
2. Wire the 6 SourcePrep MCP primitives (`prep`, `prep_search`, `prep_impact`, `prep_audit`, `prep_observe`, `prep_concepts`) into the host agent pipeline.
3. Build the Precedence Visualizer showing `$PATH` and environment variable inheritance with dry-run diffs.

### Phase 4: Packaging & Multi-Platform Distribution
1. Configure LemonSqueezy license verification module for Halbert Pro (macOS).
2. Build Tauri release pipelines:
   * **Target A**: Notarized `.dmg` / direct binary (Halbert Pro macOS).
   * **Target B**: App Store sandboxed package (Halbert Free Companion).
   * **Target C**: Linux `.deb`, `.rpm`, `.AppImage` with multi-session support.
