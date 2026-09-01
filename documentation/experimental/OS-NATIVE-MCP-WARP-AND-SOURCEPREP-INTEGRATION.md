# OS-Native MCP, Warp-CLI Integration & Native SourcePrep Architecture

**Document Status:** Experimental Architecture & Strategy  
**Date:** 2026-08-31  
**Target Systems:** HalbertOS Daemon (`halbertd`), Halbert Desktop (Tauri/React), External AI CLIs (Warp, Claude Code, Cursor, Zed)  
**Core Thesis:** Exposing the operating system itself as a Model Context Protocol (MCP) server, powered by an embedded native SourcePrep structural graph.

---

## 1. Executive Summary & The Core Concept

Today, developer AI tools like **Warp-CLI**, **Claude Code**, and **Cursor** interact with the host operating system blindly: they generate raw bash/zsh strings, execute them in unconstrained subprocesses, and parse unstructured stderr text outputs. 

This introduces three critical risks:
1. **Hallucinated System Flags:** The AI guesses command flags for the wrong Linux distro or macOS version.
2. **Silent Failure & The Semantic Gap:** The tool cannot tell if a background daemon silently crashed after a configuration change.
3. **Catastrophic Configuration Drift:** Modifying one file (e.g. `/etc/pam.d/sudo` or `~/.zshrc`) unintentionally breaks downstream services or authentication.

### The Solution: The OS as an MCP Server (`os://`)
By having **Halbert (and HalbertOS)** expose a native **Model Context Protocol (MCP)** server on local socket (`/var/run/halbert.sock`) or stdio:
* **Warp-CLI and external AI agents gain superpowers:** Instead of guessing shell commands, Warp queries verified OS tools (`halbert.query_rag`, `halbert.preview_blast_radius`, `halbert.create_atomic_snapshot`).
* **SourcePrep becomes the Native System Graph:** Instead of being an external add-on, SourcePrep is embedded directly into the OS core, continuously indexing the system's configuration physiology, dotfiles, shell precedence, and service dependencies.

```
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│                              THE OS-NATIVE MCP ECOSYSTEM                                    │
└─────────────────────────────────────────────────────────────────────────────────────────────┘

    ┌─────────────────┐       ┌─────────────────┐       ┌─────────────────┐
    │    WARP-CLI     │       │   CLAUDE CODE   │       │  CURSOR / ZED   │
    │  (AI Terminal)  │       │   (CLI Agent)   │       │  (IDE Agents)   │
    └────────┬────────┘       └────────┬────────┘       └────────┬────────┘
             │                         │                         │
             └─────────────────────────┼─────────────────────────┘
                                       │
                      Local Unix Socket / Stdio MCP Transport
                                       │
┌──────────────────────────────────────▼──────────────────────────────────────────────────────┐
│                                 HALBERT OS-NATIVE MCP SERVER                                │
│  ┌───────────────────────────────────────────────────────────────────────────────────────┐  │
│  │ Egress Redaction & Safety Boundary (mcp_response: strips keys, tokens, auth secrets)   │  │
│  └───────────────────────────────────┬───────────────────────────────────────────────────┘  │
│                                      │                                                      │
│  ┌───────────────────────────────────▼───────────────────────────────────────────────────┐  │
│  │ NATIVE SOURCEPREP GRAPH ENGINE (Continuous Configuration Physiology & AST Index)      │  │
│  │ • prep: Instant structural atlas of /etc, dotfiles, services, and codebases           │  │
│  │ • prep_impact: Real-time blast-radius dependency analyzer                             │  │
│  │ • prep_search: Intent-aware semantic & structural search                              │  │
│  │ • prep_audit: Hygiene, broken symlinks, orphaned configs, conflicting $PATHs          │  │
│  └───────────────────────────────────┬───────────────────────────────────────────────────┘  │
│                                      │                                                      │
│  ┌───────────────────────────────────▼───────────────────────────────────────────────────┐  │
│  │ NATIVE OS EXECUTION & TELEMETRY BROKER (halbertd / halbert-sys)                       │  │
│  │ • 14,000+ Sysadmin Offline RAG Documents (ArchWiki, systemd, Debian, RHEL)            │  │
│  │ • Btrfs / APFS / VSS Atomic Snapshot & Sub-Second Rollback Engine                     │  │
│  │ • Landlock & eBPF-LSM Temporal Kernel Sandboxing                                      │  │
│  │ • Zero-overhead eBPF Kernel Event Ring Buffers                                        │  │
│  └───────────────────────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Why This is a Superpower for Warp-CLI & Developer Tools

Warp is pioneering the agentic AI terminal. However, Warp-CLI currently lacks native kernel telemetry, filesystem snapshot rollback, and verified Linux configuration graphs.

When Warp-CLI connects to Halbert’s OS-level MCP server:

### Scenario Comparison: Modifying a System Service

#### Traditional Warp-CLI (Blind & Unprotected)
1. **User asks Warp:** *"Fix my broken DNS resolution on this machine."*
2. **Warp guesses:** Generates `echo "nameserver 8.8.8.8" | sudo tee /etc/resolv.conf` and `sudo systemctl restart systemd-resolved`.
3. **Failure:** Overwrites `/etc/resolv.conf` (which was a symlink managed by `systemd-resolved`), breaking DNS completely on reboot.
4. **Result:** Broken system, manual recovery required.

#### Warp-CLI + Halbert OS-Native MCP (Grounded & Reversible)
1. **User asks Warp:** *"Fix my broken DNS resolution on this machine."*
2. **Warp queries Halbert MCP:** Calls `halbert.query_rag(topic="dns_troubleshooting")` and `prep_impact(file="/etc/resolv.conf")`.
3. **Halbert MCP returns:** 
   * *"Target file is a systemd-resolved symlink; editing directly will break symlink integrity."*
   * Grounded fix: Modify `/etc/systemd/resolved.conf.d/dns_servers.conf` instead.
4. **Warp executes via MCP:** Calls `halbert.execute_transactional_step(command=..., allowed_paths=["/etc/systemd/resolved.conf.d/"])`.
5. **Halbert Engine:**
   * Takes a 5ms Btrfs/APFS subvolume snapshot.
   * Compiles a Landlock sandbox restricting file writes to that single directory.
   * Applies the change and verifies DNS resolution via eBPF network probe.
6. **Result:** Flawless, verified, 100% reversible repair.

---

## 3. Rolling in SourcePrep as a Native OS / App Feature

In the current prototype, SourcePrep is integrated via external client APIs. **Rolling SourcePrep into the native Rust core (`crates/halbert-graph`) transforms it from a tool into the OS's fundamental sensory organ.**

### What Native SourcePrep Does at the OS Level

#### 1. Configuration as Physiology
Traditional operating systems treat configuration files as isolated strings of text on disk. Native SourcePrep indexes them as a **living semantic dependency graph**:
* **Shell Precedence Graph:** Maps how environment variables flow (`/etc/paths.d` ➔ `/etc/profile` ➔ `~/.zshenv` ➔ `~/.zprofile` ➔ `~/.zshrc`).
* **Service Dependency Graph:** Connects `systemd` / `launchd` service units to their drop-in configs, socket activations, and log paths.
* **Toolchain & Version Manager Graph:** Tracks global vs. local runtimes across `mise`, `asdf`, `nvm`, `pyenv`, and `brew`.

#### 2. Native MCP Tools Exposed to the Entire System

| MCP Tool | Function | What External Tools (Warp, Claude, Cursor) Gain |
| :--- | :--- | :--- |
| **`prep`** | Returns structural codebase / system atlas. | External agents get instant topological orientation without spending thousands of tokens scraping directory trees. |
| **`prep_impact`** | Analyzes downstream dependency blast radius. | Before an AI modifies `/etc/nginx/nginx.conf` or a library module, it knows exactly which 14 files and 3 services depend on it. |
| **`prep_search`** | Semantic & structural intent-aware search. | Differentiates between *"where is symbol X"* (LOCATE), *"why was Y configured"* (RATIONALE), and *"who imports Z"* (TRACE). |
| **`prep_audit`** | Continuous sanity and hygiene auditing. | Flags conflicting `$PATH` entries, broken symlinks, orphaned configs from uninstalled apps, and insecure file permissions (`chmod 777`). |

---

## 4. Security & Privacy at the MCP Boundary

Exposing OS primitives to external LLMs requires strict zero-trust boundaries:

1. **The `mcp_response` Choke Point:**  
   As established in our MCP architecture ([`halbert_core/mcp/response.py`](file:///Volumes/4TB-BAD/Halbert/.handoff/HALBERT-MCP-HANDOFF-2026-08-28.md)), every MCP payload passes through a multi-stage redaction boundary:
   * **Structural Redaction:** Key-value pairs containing API keys, private keys (`id_ed25519`), passwords, and tokens are replaced with `<secret>`.
   * **Text Redaction:** Strips PEM certificate blocks, JWT tokens, URL-embedded credentials, and internal IP ranges before leaving the daemon.
2. **Capability-Gated Access Control:**  
   * **Read-Only Tools (`prep`, `prep_search`, `query_rag`, `get_telemetry`):** Safe to auto-approve for any authenticated local client (Warp, Cursor, Claude Code).
   * **Mutating Tools (`execute_transactional_step`, `rollback_snapshot`):** Require interactive user consent or a cryptographic session grant.

---

## 5. Implementation Path: Moving SourcePrep to the Universal Rust Core

```
Step 1: Embed SourcePrep Graph Engine in Rust (`crates/halbert-graph`)
  ├── Fast C/Rust tree-sitter & AST parsers
  ├── In-memory directed acyclic graph (petgraph)
  └── Sub-millisecond `prep_impact` and `prep_search` queries

Step 2: Standalone Local MCP Transport
  ├── Support both Unix Domain Socket (`/var/run/halbert.sock`) and stdio
  ├── Zero-dependency JSON-RPC 2.0 / MCP 1.0 protocol parser
  └── Automatic registration in Warp, Claude Code (`claude mcp add halbert`), and Cursor configs

Step 3: Universal Consumption
  ├── Tauri v2 Desktop App links directly to `halbert-graph`
  ├── Python Agent Brain imports `halbert_rs.graph`
  └── HalbertOS Daemon serves system-wide MCP queries for all desktop terminals
```

---

## 6. Strategic Takeaway

Exposing Halbert as an **OS-Native MCP Server** and embedding **SourcePrep as a native core feature** creates an unmatched developer moat:

* Halbert doesn't just help you in its own app window—**it powers and protects every AI tool in your entire development workflow (Warp, Cursor, Claude Code, Zed).**
* Every terminal command executed in Warp is grounded by Halbert’s RAG and guarded by Halbert’s atomic Btrfs/Landlock transactions.
