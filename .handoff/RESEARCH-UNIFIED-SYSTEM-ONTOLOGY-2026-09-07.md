# RESEARCH: Unified System Ontology — Connecting OS State, Configs, and Code

**Date:** 2026-09-07
**Author:** Devin session
**Status:** Research request — foundational findings complete, deeper research needed
**Related:** HANDOFF-SOURCEPREP-REVIEW-2026-09-07.md

---

## 0. The Question

> We understand an OS pretty easily because it tends to follow very
> specific patterns, but a codebase is more freeform. This is the real
> divide between how a codebase uses SourcePrep and how Halbert would
> use SourcePrep. We need some "glue" to modularize this properly. We
> have an OS, and we have a thousand config files of various importance
> and various levels of use — some never touched, some changed often.
> Halbert claims to have built a config registry but I suspect it's
> incomplete or could be far more robust. SourcePrep probably should
> be part of this ingestion system.

This document records what I found in the codebase and frames the
research questions that follow.

---

## 1. The Ontological Divide

### 1.1 Why an OS is "easy" to understand

An operating system follows rigid, documented patterns:

- **Filesystem hierarchy** is standardized (`/etc` = config, `/var` =
  runtime, `/proc` = process info, `/sys` = hardware, `/dev` = devices)
- **Process model** is well-defined (PID, parent, signals, cgroups)
- **Service management** follows a known schema (systemd units, launchd
  plists — both have structured fields with defined semantics)
- **Device model** is tree-structured (`/sys/devices/`, IOKit registry)
- **Network stack** has standard layers and interfaces

A scanner can probe any of these and know what it's looking at. The
schema is external, stable, and documented. You don't need to "understand"
an OS — you need to read it.

### 1.2 Why a codebase is "hard" to understand

A codebase is freeform:

- **File organization** is arbitrary (any directory structure)
- **Dependencies** are implicit (imports, calls, references — not
  declared in a registry)
- **Architecture** is emergent (no standard schema for "what a module
  is" or "what a subsystem is")
- **Design decisions** are undocumented (the "why" lives in people's
  heads or scattered docs)
- **Relationships** span languages, frameworks, and paradigms

This is the problem SourcePrep solves: it synthesizes structure from
freeform code by parsing ASTs, tracing imports, and using LLMs to
group files into modules and extract concepts.

### 1.3 The divide

SourcePrep is built for the freeform world (code). Halbert's discovery
engine is built for the structured world (OS). The config layer sits
between them — partially structured (ini, yaml, plist have schemas)
but partially freeform (what the keys mean, which service a config
controls, whether a change matters).

**The real question is: what is the ontology that connects all three
layers into a single knowledge graph?**

---

## 2. Foundational Findings — What Halbert Has Today

### 2.1 Three separate knowledge systems

Halbert currently has three systems that each know about one layer
but don't fully connect to each other:

#### Layer 1: Discovery Engine (OS State)

**Location:** `halbert_core/halbert_core/discovery/`

**What it knows:** Live system state — running services, network
interfaces, storage devices, GPUs, AI accelerators, backups, security
posture, sharing services, packages, hardware, thermal.

**How it stores it:** `Discovery` objects (defined in
`discovery/schema.py`) with a type, severity, status, data dict, and
actions. Stored in ChromaDB with embeddings for semantic search.

**Scanner registry:** `DiscoveryEngine` in `discovery/engine.py`
registers platform-specific scanners:
- macOS: LaunchdScanner, HomebrewScanner, MacThermalScanner,
  MacNetworkScanner, MacStorageScanner, MacSecurityScanner,
  TimeMachineScanner, HomebrewAppScanner, MacAppStoreScanner,
  MacSharingScanner, GpuScanner, AiAcceleratorScanner
- Linux: BackupScanner, ServiceScanner, StorageScanner,
  NetworkScanner, SecurityScanner, SharingScanner, FlatpakScanner,
  SnapScanner, AppImageScanner, GpuScanner, AiAcceleratorScanner

**DiscoveryType enum** (21 types): SYSTEM_PRESERVATION, PERFORMANCE,
BACKUP, NETWORK, FILESYSTEM, SERVICE, PACKAGE, SECURITY, DESKTOP,
STORAGE, HARDWARE, GPU, AI_ACCELERATOR, TASK, CONTAINER, POWER,
SHARING, PROCESS, ALERT, SESSION, PRINTER.

**What it doesn't know:** Which config files control the things it
discovers. It knows nginx is running but not that
`/etc/nginx/nginx.conf` controls it. It knows en0 exists but not
which config file set it up.

#### Layer 2: Config Registry (Config Files)

**Location:** `halbert_core/halbert_core/config/`

**What it knows:** Which config files exist on the system, their
parsed content (canonical JSON), their relationships (edges), and
when they change (drift detection).

**Components:**
- `manifest.py` — YAML manifest defining which files to track
  (include/exclude globs) with platform-specific registries
- `snapshot.py` — Parses tracked files into canonical JSON, stores
  raw text (redacted) and parsed canon, builds secret correlation index
- `watcher.py` — Filesystem watcher that detects changes, triggers
  SourcePrep re-index and detector sweeps
- `drift.py` — Compares snapshots to detect what changed
- `edge_extractor.py` — Extracts dependency edges between config files
  (systemd unit dependencies, include directives, fstab references,
  drop-in relationships, ini file references)
- `roles.py` — Role-based scope registry (network_admin, service_admin,
  storage_admin, security_admin, credentials_admin, shell_admin,
  package_admin, boot_admin, sharing_admin) with per-role manifests
- `sensitivity.py` — Classifies config files by sensitivity level
- `secret_correlation.py` — Groups identical secret values across files

**What it doesn't know:** Which discoveries (OS state) are affected by
the configs it tracks. It knows `/etc/nginx/nginx.conf` exists and
what's in it, but not that the `nginx` service discovery depends on it.

#### Layer 3: SourcePrep Integration (Indexing + Search)

**Location:** `halbert_core/halbert_core/integrations/sourceprep_setup.py`

**What it knows:** A unified SourcePrep project ("halbert") with two
scope families:
- `host/` — staged live config files (from the config registry),
  organized by role (host/network, host/service, host/storage, etc.)
- `knowledge/{platform}/` — prose documentation corpus

**How it works:** `SourcePrepSetup.apply()` creates the project,
reconciles scopes, runs ordered builds (fast_sync → deep_enrichment →
finalize), and pushes external config edges (from
`ConfigEdgeExtractor`) into the trace graph.

**Config watcher integration:** When a config file changes, the
watcher triggers a debounced SourcePrep re-index
(`create_sourceprep_reindex_callback`) that re-stages host files and
runs incremental fast_sync.

**What it doesn't know:** The Halbert codebase itself. The codebase
(the Python source, TypeScript frontend, Rust engine) is in a
*separate* SourcePrep project. The unified "halbert" project only
contains host configs and knowledge docs, not the code that probes
them.

### 2.2 The connection points that exist but are incomplete

There are partial connections between the layers:

1. **Discovery → Config (weak):** `Discovery.config_path` field exists
   in the schema (added in Phase 24 for consolidation) — a discovery
   can reference the config file that controls it. But this is
   sparsely populated. Most scanners don't set it.

2. **Config → SourcePrep (strong):** The config watcher triggers
   SourcePrep re-indexing. Config edges are pushed into the trace
   graph. This connection is well-built.

3. **Discovery → SourcePrep (none):** Discoveries are stored in
   ChromaDB, not in SourcePrep's graph. There is no edge from "nginx
   service discovery" to "/etc/nginx/nginx.conf config file" in
   SourcePrep's trace graph.

4. **Code → Config (none):** The codebase (scanner implementations,
   tool functions) is not connected to the configs it reads or the
   discoveries it produces. SourcePrep indexes the code in a separate
   project from the configs.

5. **Code → Discovery (none):** There is no structural link from
   `ServiceScanner` (code) to the `service/nginx` discovery it
   produces (OS state).

### 2.3 The config registry's completeness

The user suspects the config registry is incomplete. Having read both
manifests, this is confirmed:

#### macOS registry (`config-registry.macos.yml`)

**Tracks (~15 patterns):**
- `/etc/*.conf`, `/etc/hosts`, `/etc/aliases`, `/etc/auto_master`,
  `/etc/auto_home`, `/etc/ssh/*`, `/etc/pam.d/*`, `/etc/apache2/*.conf`,
  `/etc/newsyslog.d/*.conf`
- `/Library/LaunchDaemons/*.plist`, `/Library/LaunchAgents/*.plist`
- `/opt/homebrew/etc/**/*.conf`, `/opt/homebrew/etc/*.cfg`,
  `/opt/homebrew/etc/gitconfig`

**Missing:**
- User-level configs: `~/.config/`, `~/.local/`, dotfiles (`.zshrc`,
  `.bashrc`, `.gitconfig`, `.vimrc`)
- Application configs: `~/Library/Application Support/`,
  `~/Library/Preferences/`
- VPN/network configs: Tailscale (`/var/run/tailscale/`),
  WireGuard (`/opt/homebrew/etc/wireguard/`)
- Container configs: Docker (`~/.docker/`, `~/Library/Containers/`)
- Halbert's own configs: policy YAML, prompt XML, scanner configs,
  feature flags
- Runtime/dynamic configs: anything not in /etc
- `/etc/fstab` (macOS has a synthetic.conf equivalent)
- `/etc/synthetic.conf`
- `/etc/exports` (NFS)
- `/etc/nfs.conf`
- Homebrew services: `/opt/homebrew/var/` (logs, runtime)
- cron/at jobs: `crontab -l` output isn't a file

#### Linux registry (`config-registry.yml`)

**Tracks (4 patterns — very thin):**
- `/etc/**/*.conf`, `/etc/systemd/*.service`, `/etc/default/*`

**Missing:**
- `/etc/systemd/system/` (user-created units — only `/etc/systemd/*.service`
  is tracked, not subdirectories)
- `/etc/sysconfig/` (RHEL/Fedora service configs)
- `/etc/modprobe.d/`, `/etc/sysctl.d/`, `/etc/modules-load.d/`
- `/etc/security/` (PAM, limits, access.conf)
- `/etc/fstab` (not a .conf file)
- `/etc/crontab`, `/etc/cron.d/`, `/etc/cron.{daily,weekly,monthly}/`
- `/etc/sudoers.d/` (excluded entirely — but sudoers.d contains
  policy, not just secrets)
- `/etc/ssh/sshd_config.d/` (drop-in configs)
- `/etc/network/`, `/etc/netplan/` (network configs)
- `/etc/docker/`, `/etc/containerd/`
- `/etc/nginx/`, `/etc/apache2/` (application configs — only flat
  .conf is caught)
- `/etc/logrotate.d/`
- `/etc/rsyslog.d/`, `/etc/journald.conf.d/`
- User crontabs (`/var/spool/cron/`)
- Application-specific locations (`~/.config/`, `/opt/*/etc/`)

#### Role-scoped manifests (`config/scopes/*.yml`)

The role system (`config/roles.py`) adds per-role manifests that
provide more targeted coverage. There are 9 roles:
network_admin, service_admin, storage_admin, security_admin,
credentials_admin, shell_admin, package_admin, boot_admin,
sharing_admin.

This is a good architecture — role-based scoping is the right
pattern. But the base registry is still thin, and the role manifests
inherit the same gaps for files not explicitly listed in any role.

### 2.4 The "importance" and "mutation frequency" dimensions

The user mentioned "various importance and various levels of use —
some never touched, some changed often." Halbert has partial support
for this:

- **Sensitivity** (`config/sensitivity.py`): Classifies files by
  sensitivity level (for tier routing and egress redaction). This is
  a security dimension, not an importance dimension.
- **Drift detection** (`config/drift.py`): Detects when files change
  between snapshots. This gives mutation frequency *after the fact*
  but doesn't classify files by expected mutation rate.
- **Watcher change log** (`config/watcher.py`): Rolling log of recent
  changes with timestamps. This is raw mutation data, not classified.

**What's missing:**
- No "importance" classification (critical/important/cosmetic)
- No "expected mutation rate" classification (static/slow/dynamic)
- No "last touched" timestamp tracked persistently across sessions
- No "who touched this last" provenance for config changes (the
  watcher records system-initiated changes but not human-initiated
  ones with attribution)
- No "blast radius" for config changes (which services/discoveries
  are affected if this config changes)

---

## 3. The Unified Ontology — What "Glue" Would Look Like

### 3.1 The three layers as a single graph

The goal is a single knowledge graph where:

```
OS State (Discoveries)     Config Files           Code
─────────────────────     ─────────────          ─────────
service/nginx         ←─── /etc/nginx/nginx.conf  ←─── ServiceScanner.scan()
network/en0           ←─── /etc/network/interfaces ←─── NetworkScanner.scan()
storage/dev-sda1      ←─── /etc/fstab             ←─── StorageScanner.scan()
gpu/apple-m1-ultra    ←─── (no config — hardware)  ←─── GpuScanner.scan()
sharing/smb           ←─── /etc/samba/smb.conf     ←─── SharingScanner.scan()
```

The arrows are:
- **controlled_by**: discovery → config (which config file controls
  this OS state)
- **probed_by**: discovery → code (which scanner produces this discovery)
- **reads**: code → config (which scanner reads which config files)
- **configures**: config → discovery (inverse of controlled_by)

### 3.2 Why SourcePrep is the right "glue"

SourcePrep already has:
- A trace graph with nodes and edges
- External edge injection (`push_external_edges`)
- Scope-based filtering (role scopes)
- Semantic search over the graph
- Module synthesis and hub detection
- Concept recording (design decisions)

What it would need:
- A new node type for discoveries (or a mapping from Discovery IDs
  to SourcePrep node IDs)
- New edge kinds: `controlled_by`, `probed_by`, `reads`, `configures`
- A discovery-to-config mapping table (which scanner discovers what,
  and which config files control it)
- A code-to-config mapping table (which scanner reads which configs)
- Integration with the config watcher to update edges when configs
  change

### 3.3 The "importance" and "mutation frequency" axes

Each config file node in the graph should carry metadata:

| Field | Values | Source |
|-------|--------|--------|
| `importance` | critical / important / cosmetic | Inferred from role scope + service criticality |
| `mutation_rate` | static / slow / dynamic / volatile | Computed from watcher change log history |
| `last_touched` | ISO8601 timestamp | From watcher change log |
| `touch_count_30d` | integer | From watcher change log |
| `blast_radius` | list of discovery IDs | From the controlled_by edges |
| `sensitivity` | public / internal / secret | From existing sensitivity.py |

This metadata would let the agent answer questions like:
- "Which configs changed recently that affect critical services?"
- "Which configs are volatile but low-importance (safe to ignore)?"
- "Which configs are static but high-importance (change = alarm)?"
- "If I change this config, what discoveries are affected?"

---

## 4. Research Questions

The following questions need deeper research before implementation:

### R1: Discovery-to-config mapping

**Question:** For each DiscoveryType, what are the config files that
typically control discoveries of that type?

**Why it matters:** This is the `controlled_by` edge. Without it, the
three layers stay disconnected.

**Research approach:**
- For each scanner, identify which config files (if any) it reads or
  which configs control the things it discovers
- Build a mapping table: `{scanner_class → [config_paths]}`
- For scanners that don't read configs (e.g., GpuScanner probes
  hardware directly), note that the discovery is config-independent
- Consider platform differences (nginx config path differs by distro)

**Sub-questions:**
- Should this mapping be declarative (a YAML table the scanner
  declares) or inferred (the scanner reports which configs it read)?
- How to handle dynamic/runtime configs that aren't files (e.g.,
  `networksetup -setdnsservers` writes to a system store, not a file)?
- How to handle configs that control multiple discovery types (e.g.,
  `/etc/ssh/sshd_config` controls both SERVICE and SECURITY discoveries)?

### R2: Config registry completeness audit

**Question:** What is the full set of config files that an
administrator would want Halbert to track on macOS and Linux?

**Why it matters:** The current registries are thin (4 patterns on
Linux, ~15 on macOS). The user suspects this and the codebase
confirms it.

**Research approach:**
- Survey common macOS administration configs (deployment tools, MDM,
  enterprise management, developer tools, server software)
- Survey common Linux administration configs across distros (Debian,
  RHEL, Arch, Alpine — paths differ)
- Categorize by: OS-level, service-level, application-level, user-level
- For each, assess: importance (critical/important/cosmetic), expected
  mutation rate (static/slow/dynamic), sensitivity (public/secret)
- Consider how to handle configs that live in non-standard locations
  (Homebrew, Snap, Flatpak, AppImage, container volumes)

**Sub-questions:**
- Should the registry auto-discover config files (scan for known
  patterns) or remain an explicit allowlist?
- How to handle user-level configs (`~/.config/`, dotfiles) without
  invading privacy or tracking personal preferences?
- Should Halbert's own configs (policy YAML, prompt XML) be in the
  registry? They're already in the codebase, but they're also runtime
  configs that change behavior.

### R3: Mutation frequency tracking

**Question:** How should Halbert classify and track the mutation
frequency of config files?

**Why it matters:** The user specifically mentioned "some never
touched, some changed often." This is a dimension the current system
doesn't classify.

**Research approach:**
- Define mutation rate buckets: static (changed <1x/year), slow
  (<1x/month), dynamic (<1x/week), volatile (>1x/week)
- Use the existing watcher change log to compute historical rates
- For files with no history, infer from file type (fstab = static,
  hosts = dynamic, sshd_config = slow)
- Consider how to surface this to the agent: "this config is volatile,
  changes are expected" vs "this config is static, any change is
  notable"

**Sub-questions:**
- How long of a history window is needed to classify mutation rate
  reliably? (1 week? 1 month? 3 months?)
- Should mutation rate affect alerting? (A change to a static file
  should alert; a change to a volatile file should not.)
- How to distinguish "system changed this automatically" (apt upgrade,
  macOS update) from "human changed this deliberately"?

### R4: Importance classification

**Question:** How should Halbert classify the importance of config
files?

**Why it matters:** Not all configs are equal. `/etc/fstab` is
critical (wrong mount = data loss). `/etc/issue` is cosmetic (login
banner text). The agent needs to know the difference.

**Research approach:**
- Define importance levels: critical (system won't boot/work without
  it), important (affects a service or security posture), cosmetic
  (display text, preferences)
- Build a classification table mapping file patterns to importance
  levels
- Allow role scopes to override (a file that's cosmetic in one role
  might be important in another)
- Consider blast radius: a config's importance is partly determined by
  how many discoveries depend on it

**Sub-questions:**
- Should importance be declarative (a YAML table) or inferred (from
  service criticality + blast radius)?
- How to handle configs whose importance varies by content (e.g.,
  `/etc/hosts` is cosmetic if it only has localhost, critical if it
  overrides DNS for production services)?
- Should the agent be able to change importance classifications, or
  are they product-defined?

### R5: SourcePrep as the unified graph store

**Question:** Should SourcePrep's trace graph become the single store
for all three layers (OS state, configs, code), or should the layers
remain separate with cross-references?

**Why it matters:** This is an architecture decision that affects
everything downstream.

**Option A: Unified graph.** Push discoveries into SourcePrep as
nodes with edges to config files and code. One graph, one query
interface, one set of MCP tools. Pros: single source of truth,
structural queries across all layers. Cons: SourcePrep becomes a
runtime system (not just an index), must handle live state changes,
node types proliferate.

**Option B: Federated graphs with cross-references.** Keep
discoveries in ChromaDB, configs in the config canon, code in
SourcePrep. Add a cross-reference layer that maps IDs between stores.
Pros: each system stays specialized, no schema migration. Cons:
queries that span layers require join logic, no single structural
view.

**Option C: SourcePrep as the config+code graph, discoveries as
external nodes.** Keep SourcePrep for configs and code (which it
already does), but add discovery nodes as external references (like
the current external edge mechanism). Discoveries are stored in
ChromaDB but appear as nodes in SourcePrep's graph with edges to
configs. Pros: minimal change to SourcePrep, discoveries stay in
their optimized store. Cons: two stores to keep in sync.

**Research approach:**
- Prototype each option with a small example (nginx service +
  nginx.conf + ServiceScanner)
- Assess query complexity for cross-layer questions
- Assess update complexity when configs change or services restart
- Consider the SourcePrep team's roadmap — would they accept
  discovery nodes, or is that out of scope?

### R6: The codebase as a tracked artifact

**Question:** Should Halbert's own codebase be in the same SourcePrep
project as the host configs, or in a separate project?

**Why it matters:** Currently the code is in a separate SourcePrep
project from the configs. This means there's no edge from
`ServiceScanner` (code) to `/etc/systemd/system/nginx.service` (config)
to `service/nginx` (discovery). The three-layer graph requires all
three in the same project (or with cross-project edges, which
SourcePrep may not support).

**Research approach:**
- Assess whether SourcePrep supports cross-project edges
- If not, assess the impact of merging the code project into the
  unified "halbert" project (code + configs + knowledge docs in one
  project)
- Consider whether the code should be a separate scope within the
  unified project (like host/ and knowledge/ are today)
- Assess the indexing cost — code is much larger than configs, and
  re-indexing on every config change would be expensive

### R7: Declarative scanner-to-config mapping

**Question:** Should each scanner declaratively specify which config
files it reads and which discoveries it produces?

**Why it matters:** This is how the `probed_by` and `reads` edges
would be populated. Without it, the mapping has to be inferred.

**Current state:** Scanners don't declare what they read. A scanner
might call `systemctl list-units`, read `/etc/systemd/system/*.service`,
parse the output, and produce Discovery objects — but none of this is
declared in a machine-readable way.

**Research approach:**
- Design a declarative mapping format (e.g., a class attribute or
  YAML sidecar):
  ```python
  class ServiceScanner(BaseScanner):
      reads_configs = ["/etc/systemd/system/*.service", "/etc/systemd/*.service"]
      produces_type = DiscoveryType.SERVICE
      config_to_discovery = {
          "/etc/systemd/system/{name}.service": "service/{name}"
      }
  ```
- Assess how many scanners could populate this trivially vs. how
  many would need refactoring
- Consider whether this should be a class attribute, a method, or a
  separate registry file

### R8: The "freeform" problem at the config layer

**Question:** Configs are partially structured (ini/yaml/plist have
schemas) but partially freeform (what the keys mean, which service
they control). How much of this can be automated vs. needs to be
curated?

**Why it matters:** This is the core ontological question. An OS is
fully structured. Code is fully freeform. Configs are in between.

**Research approach:**
- For standard configs (systemd units, fstab, sshd_config, nginx.conf,
  smb.conf), assess whether the config→service mapping can be
  extracted from the config content itself (e.g., a systemd unit's
  `Description=` field names the service)
- For non-standard configs (application-specific yaml, dotfiles),
  assess whether the mapping needs to be curated or can be inferred
  from context (file location, naming convention)
- Consider whether SourcePrep's LLM augmentation could help: given a
  config file's content and location, can it infer which service it
  controls?

---

## 5. Proposed Research Plan

### Phase 1: Mapping audit (no code changes)

1. **Scanner audit:** For each of the 21 scanners (11 macOS + 10
   Linux), document:
   - What OS state it discovers
   - What config files (if any) control that state
   - What config files (if any) the scanner reads directly
   - Whether the discovery→config mapping is 1:1, 1:many, or none

2. **Config registry gap analysis:** For each platform, produce a
   comprehensive list of admin-relevant config files and compare
   against the current registry. Categorize gaps by:
   - Missing entirely
   - Tracked but wrong pattern (e.g., `/etc/systemd/*.service` misses
     `/etc/systemd/system/` subdirectory)
   - Tracked but wrong scope (in base registry but should be in a
     role scope)

3. **Importance + mutation rate classification:** For each tracked
   config file, assign:
   - Importance: critical / important / cosmetic
   - Expected mutation rate: static / slow / dynamic / volatile
   - Rationale (why this classification)

### Phase 2: Architecture decision

4. **Graph topology decision (R5):** Choose between unified graph,
   federated graphs, or SourcePrep-as-config+code-with-discovery-refs.
   Document the trade-offs and decision.

5. **Codebase placement decision (R6):** Decide whether to merge the
   code SourcePrep project into the unified "halbert" project or keep
   them separate with cross-references.

### Phase 3: Prototype

6. **Build a minimal three-layer graph for one scanner:** Take
   ServiceScanner as the prototype. Connect:
   - `ServiceScanner` (code node) → reads → `/etc/systemd/system/*.service`
     (config nodes) → controls → `service/nginx` (discovery node)
   - Demonstrate a cross-layer query: "show me all configs that
     control running services, ranked by importance"

7. **Prototype the importance + mutation rate metadata:** Add these
   fields to config nodes in the prototype and demonstrate queries
   that use them.

### Phase 4: Scale

8. **Extend the declarative mapping to all scanners:** Based on the
   Phase 1 audit, add `reads_configs` and `config_to_discovery`
   declarations to each scanner.

9. **Expand the config registry:** Based on the Phase 1 gap analysis,
   add missing patterns to the platform registries and role manifests.

10. **Integrate with SourcePrep's graph:** Push the discovery nodes
    and cross-layer edges into SourcePrep's trace graph via the
    external edges API.

---

## 6. What I Need From Other Researchers

### From the SourcePrep team

1. **Does SourcePrep support cross-project edges?** If I have a
   "halbert-code" project and a "halbert-host" project, can a node
   in one reference a node in the other?

2. **Can SourcePrep handle non-file nodes?** Discoveries are not
   files — they're runtime state (a running service, a network
   interface). Can these be nodes in the trace graph, or does
   SourcePrep require all nodes to be file-backed?

3. **Can SourcePrep handle live state changes?** The config watcher
   already triggers re-indexing, but discoveries change more
   frequently (services start/stop, network interfaces go up/down).
   Is SourcePrep's incremental update fast enough for this?

4. **Would the SourcePrep team accept discovery nodes as a first-class
   node type, or is that out of scope for the product?**

### From a Halbert architecture reviewer

1. **Is the Discovery schema (`Discovery.config_path`) the right
   mechanism for the discovery→config edge, or should it be in a
   separate mapping table?**

2. **Should the scanner-to-config mapping be declarative (class
   attribute) or inferred (scanner reports what it read)?**

3. **How to handle the "freeform" config problem — configs that
   don't have a standard schema or a clear service mapping?**

### From a systems administration domain expert

1. **What is the comprehensive set of admin-relevant config files on
   macOS 15+ and common Linux distros?**

2. **How do enterprise management tools (MDM, Ansible, Salt) affect
   the config landscape — do they create configs in non-standard
   locations?**

3. **What importance and mutation rate classifications make sense
   from an operator's perspective?**

---

## 7. Summary

Halbert has three knowledge systems — discovery (OS state), config
registry (config files), and SourcePrep integration (indexing) —
that each work well in isolation but don't form a unified graph.

The config registry is confirmed incomplete: the Linux registry has
only 4 patterns, the macOS registry has ~15 but misses user-level,
application, and Halbert's own configs. The role-scoped manifests
help but inherit the base gaps.

The "glue" the user is asking for is a unified ontology that connects
OS state ↔ configs ↔ code in a single graph, with metadata for
importance and mutation frequency. SourcePrep is the natural home for
this graph because it already indexes configs and code, already has a
trace graph with external edges, and already has the LLM augmentation
to synthesize structure from partially-freeform data.

The research questions in Section 4 frame the work needed before
implementation. The most critical are:
- **R1** (discovery-to-config mapping) — the core connection
- **R2** (config registry completeness) — the user's specific concern
- **R5** (graph topology) — the architecture decision
- **R7** (declarative scanner mapping) — the implementation mechanism

The proposed research plan (Section 5) starts with a no-code audit
(Phase 1), moves to an architecture decision (Phase 2), prototypes
with one scanner (Phase 3), and scales to all scanners (Phase 4).
