# Role-Scoped Skills for Halbert

**Date:** 2026-08-27
**Status:** Reviewed against implementation 2026-08-27 — see §16 before building
**Reconciled with:** `documentation/design/SCOPE-AXES-RECONCILIATION-2026-08-27.md`
(role-scoped config harvesting ships `*_admin` scopes that this design partitions
independently — §16.9 records the agreed single list)
**Depends on:** SourcePrep scope system, intake signals, context assembler, agent state machine

---

## 1. Motivation

Halbert's domain is finite and enumerable: disk, services, network, config,
security, packages, users, logs, processes, boot. This is fundamentally
different from a general-purpose coding agent, where "skills" teach the
agent arbitrary workflows (review PRs, deploy apps, run migrations).

For Halbert, a skill system is about **role-scoped operational expertise**:
when the user asks about storage, Halbert should become the storage
expert — with the right knowledge scope, the right safety constraints,
the right toolset, and the right model tier. Today these concerns are
scattered across four modules with no unifying abstraction:

| Concern | Current location | Problem |
|---------|-----------------|---------|
| Retrieval scope routing | `sourceprep_retrieval_backend.scope_for_query()` | Regex heuristic, not extensible by users |
| Domain detection | `intake/signals.py` `_DOMAIN_KEYWORDS` | Hardcoded dict, 6 domains, no user customization |
| Safety constraints | `prompts/safety.py` + scattered approval checks | Global, not per-domain |
| Context budget | `context/assembler.py` `DEFAULT_PRIORITIES` | Flat weights, not role-aware |
| Model tier selection | `intake/pipeline.py` + `model/router.py` | Complexity-based, not domain-based |

A skill system unifies all five into a single declarative unit that users
can create, share, and compose.

### 1.1 Inspiration sources

- **Claude Code skills** (`.claude/skills/<name>/SKILL.md` or `<name>.md`):
  YAML frontmatter + prompt body, progressive disclosure (name+description
  in context, body on invocation), tool restrictions, and subagent execution.
- **open-claude-code** (`v2/src/skills/`, `v2/src/agents/`, `v2/src/hooks/`):
  Skills loader + runner, agent teams with roles, hook engine with 6
  event types (PreToolUse, PostToolUse, Stop, Notification, PrePrompt,
  PostResponse), plugin loader for git/npm distribution.
- **SourcePrep scope system**: `ScopeRecord{id, display_name, paths,
  pipeline_profile, assigned_to_role}` — the `assigned_to_role` field
  is reserved (v1.1) but unused. This is the keystone that connects
  indexing to skills.

### 1.2 What makes Halbert skills different from Claude Code skills

| Dimension | Claude Code skills | Halbert skills |
|-----------|-------------------|----------------|
| Primary purpose | Inject workflow prompts | Bundle domain expertise + retrieval scope + safety + model tier + budget |
| Activation | `/command` or model auto-invoke | Intake signal domain matching + `/command` + platform detection |
| Scope concept | None (same codebase) | SourcePrep scope (retrieval partition with pipeline profile) |
| Safety | Tool permissions (allow/deny lists) | Destructive-op approval + protected paths + protected services |
| Model routing | Per-skill model override | Per-skill model tier (orchestrator / specialist / vision) |
| Context | Full conversation window | Scope-filtered + budget-allocated per skill |
| Composition | One skill at a time | Multiple skills compose (merge prompts, union scopes, intersect safety) |
| Distribution | Git/npm plugins | Built-in app skills + user config + optional git packs |

---

## 2. The Skill Format

A Halbert skill is a `SKILL.md` file (or `<name>.md` file) loaded from standard locations in order of precedence:

```
halbert_core/skills/builtin/<name>/SKILL.md   # built-in skills shipped with Halbert App
~/.config/halbert/skills/<name>/SKILL.md      # global user skills (homelab, personal quirks)
.halbert/skills/<name>/SKILL.md               # host-specific skills (optional local override)
.claude/skills/<name>/SKILL.md                # compatibility path (or .claude/skills/<name>.md)
```

### 2.1 Frontmatter reference

```yaml
---
# ── Identity ──
name: storage-ops
description: Disk, filesystem, ZFS, RAID, SMART operations
aliases: [disk, zfs, raid]

# ── Activation ──
triggers:
  domains: [storage, backup]         # intake signal domains that auto-activate
  keywords: [zfs, smart, raid, nvme]  # additional keyword triggers
  platform: [linux, darwin]           # restrict to platforms (omit = all)
  intent: [troubleshooting, command]  # restrict to intents (omit = all)

# ── Retrieval ──
scope: host                           # primary SourcePrep scope
knowledge_scope: knowledge-linux      # reference corpus scope (optional)
trace_expand: true                    # follow edges in retrieval

# ── Model ──
model: specialist                     # chat | specialist | vision (see §16.3)
# Or explicit:
# model: "deepseek-v4-pro:cloud"

# ── Context budget ──
priority: high                        # low | normal | high | critical
budget_multiplier: 1.5                # multiply this skill's source budget

# ── Safety ──
safety:
  destructive_requires_approval: true
  protected_paths: ["/boot", "/dev", "/proc", "/sys"]
  protected_services: ["sshd", "systemd-journald"]
  blocked_commands: ["mkfs", "dd of=/dev/"]

# ── Tools ──
allowed_tools: [exec, read, write, discovery, config_watcher]
# Omit = inherit all tools

# ── Subagent ──
subagent: false                       # run as independent subagent with own context
max_turns: 10                         # if subagent: true
---

You are Halbert's storage operations specialist.

When examining disk health, always cross-reference SMART data with ZFS
pool status. When a disk shows SMART failure AND belongs to a degraded
pool, the disk is the root cause.

Never run `zpool destroy` without explicit human approval.
Never run `mkfs` on a mounted filesystem.
```

### 2.2 Field semantics

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | string | dir name | Skill identifier |
| `description` | string | none | Shown in completions and skill listing |
| `aliases` | list | [] | Alternative invocation names |
| `triggers.domains` | list | [] | Intake signal domains that auto-activate this skill |
| `triggers.keywords` | list | [] | Additional regex/keyword triggers beyond domains |
| `triggers.platform` | list | all | Restrict to platforms (linux, darwin, freebsd) |
| `triggers.intent` | list | all | Restrict to intents (question, command, troubleshooting, informational) |
| `scope` | string | none | Primary SourcePrep scope for retrieval |
| `knowledge_scope` | string | none | Secondary reference corpus scope |
| `trace_expand` | bool | true | Follow edges in SourcePrep retrieval |
| `model` | string | chat | Model tier (`chat`/`specialist`/`vision`) or explicit model name |
| `priority` | enum | normal | Context budget weight class |
| `budget_multiplier` | float | 1.0 | Multiply this skill's allocated budget |
| `safety.destructive_requires_approval` | bool | false | Gate destructive ops behind human approval |
| `safety.protected_paths` | list | [] | Paths that cannot be modified without approval |
| `safety.protected_services` | list | [] | Services that cannot be stopped/restarted without approval |
| `safety.blocked_commands` | list | [] | Commands that are flatly blocked when skill is active |
| `allowed_tools` | list | all | Tool restrictions for this skill |
| `subagent` | bool | false | Run as independent subagent with own context window |
| `max_turns` | int | 10 | Max turns if subagent is true |

### 2.3 The prompt body

The markdown body after the frontmatter is the **expertise prompt** —
domain-specific instructions, heuristics, cross-reference rules, and
operational knowledge. This is what gets injected into the system prompt
when the skill activates.

Unlike Claude Code skills (where the prompt *is* the skill), in Halbert
the prompt is one component of five: prompt + scope + safety + model +
budget. The prompt provides the "how to think about this domain"
knowledge; the other four components shape the retrieval, constraints,
and compute around it.

---

## 3. Activation Model

### 3.1 The activation pipeline

```
User message
    │
    ▼
┌─ intake/signals.py ─────────────────────┐
│ analyze_message() → MessageSignals      │
│   .detected_domains: [storage, service] │
│   .intent: troubleshooting               │
│   .has_error_indicators: true            │
│   .platform: darwin                      │
└──────────────────────────────────────────┘
    │
    ▼
┌─ skills/matcher.py ─────────────────────┐
│ For each loaded skill:                   │
│   - domain match? (storage ∈ triggers)  │
│   - keyword match? (zfs ∈ triggers)     │
│   - platform match? (darwin ∈ triggers) │
│   - intent match? (troubleshooting ∈?)  │
│ Score = weighted sum of matches          │
│ Active skills = score > threshold        │
└──────────────────────────────────────────┘
    │
    ▼
┌─ skills/composer.py ────────────────────┐
│ Merge prompts (concatenate with headers)│
│ Union scopes (host + knowledge-linux)    │
│ Intersect safety (most restrictive wins) │
│ Select model (highest-priority skill)    │
│ Adjust budget (sum of multipliers)       │
└──────────────────────────────────────────┘
    │
    ▼
┌─ context/assembler.py ──────────────────┐
│ assemble() with:                         │
│   - scope-filtered retrieval             │
│   - adjusted priorities                  │
│   - injected skill prompts               │
│   - safety constraints applied           │
└──────────────────────────────────────────┘
    │
    ▼
┌─ agents/state_machine.py ───────────────┐
│ PLANNING → SEARCHING → EXECUTING →       │
│ OBSERVING → REFLECTING → RESPONDING      │
│ (skill active throughout the turn)       │
└──────────────────────────────────────────┘
```

### 3.2 Activation example

```
User: "why is my ZFS pool degraded?"

Intake signals:
  detected_domains: [storage, service]
  intent: troubleshooting
  has_error_indicators: true
  platform: linux

Skill matching:
  storage-ops:    domains=[storage,backup] → 2/2 match, priority=high
  service-ops:    domains=[service]        → 1/1 match, priority=normal
  security-ops:   domains=[security]       → 0/1 match, NOT activated

Active skills: [storage-ops, service-ops]

Composed context:
  Prompt: storage-ops body + service-ops body
  Scopes: host + knowledge-linux (union)
  Safety: destructive_requires_approval=true (both skills agree)
          protected_paths: ["/boot", "/dev", "/proc", "/sys", "/etc/systemd/"]
  Model:  specialist (storage-ops priority=high wins over service-ops normal)
  Budget: retrieval=0.8 × 1.5 (storage-ops multiplier) = 1.2
          discovery=0.6 × 1.0 = 0.6
```

### 3.3 Explicit invocation

Users can also invoke skills explicitly via `/skill-name` in chat:

```
User: /storage-ops check my pool status

→ storage-ops activates regardless of domain detection
→ other skills do not activate (explicit invocation overrides auto-matching)
```

### 3.4 Skill pinning and deactivation

Skills remain active for the duration of a turn by default (one FSM cycle:
PLANNING → RESPONDING). They do not persist across turns — each turn
re-runs the matcher to prevent context bleeding: a storage question
in turn 1 does not contaminate a networking question in turn 2.

For extended multi-turn troubleshooting, skills can be pinned via slash commands
(aligning with Halbert's `/model` command pattern):
- `/skill <name>` — Run current turn with `<name>` active (manual override)
- `/skill pin <name>` (or `/pin <name>`) — Pin `<name>` across turns until unpinned
- `/skill unpin` — Release back to automatic intake signal matching
- `/skill list` — Display loaded skills and current active status

### 3.5 Mid-turn skill escalation (Symptom-to-Root-Cause)

In operational troubleshooting, user queries almost always report **symptoms**
rather than root causes:
1. User reports: *"Why is my Nextcloud container throwing 502 Bad Gateway?"*
2. Intake classifies domain as `service` → activates `service-ops`.
3. During `EXECUTING`, Halbert inspects `journalctl` or `dmesg` and uncovers disk
   I/O timeouts or a degraded ZFS pool.

If skill activation were locked strictly at `PLANNING`, Halbert would be stranded
without `storage-ops` expertise and safety constraints for the remainder of the turn.

To solve this, Halbert supports **dynamic mid-turn escalation**:
- During `OBSERVING` and `REFLECTING`, the state machine checks tool execution results
  for cross-domain error indicators (e.g. disk faults, OOM kills, permission denials).
- The state machine invokes `skills/activator.py` to escalate:
  `active_skills.append("storage-ops")`.
- Halbert immediately:
  1. Issues an incremental retrieval query against `host_storage` (SourcePrep scope).
  2. Injects the `storage-ops` expertise prompt into the turn context.
  3. Upgrades the safety gate (`PreToolUse`) to intersect the more restrictive storage rules
     before running any further remediation commands.
- Alternatively, Halbert's model can self-invoke mid-turn via a `Skill` tool call
  (matching open-claude-code's `SkillTool`), requesting specialist escalation explicitly.

---

## 4. Skill Composition

When multiple skills activate simultaneously, the composer merges them:

### 4.1 Prompt merging

```
[Active Skill: storage-ops]
You are Halbert's storage operations specialist.
When examining disk health, always cross-reference SMART data...

[Active Skill: service-ops]
You are Halbert's service management specialist.
When a service fails, check journald for the last 50 lines before
the failure timestamp. Correlate with config changes...
```

Prompts are concatenated with clear headers. The base identity prompt
(SystemIdentityAdapter) always comes first.

### 4.2 Scope union

```
storage-ops:  scope=host, knowledge_scope=knowledge-linux
service-ops:  scope=host, knowledge_scope=knowledge-linux

Union: scopes=[host], knowledge_scopes=[knowledge-linux]
```

SourcePrep's context endpoint accepts a single scope today. The composer
would either:
- **v1**: Pick the highest-priority skill's scope (simple, loses multi-scope)
- **v2**: Issue parallel retrieval per scope and merge results (richer, more API calls)
- **v3**: SourcePrep adds multi-scope support (union of scope masks)

v1 is the pragmatic starting point. v2 is the right long-term answer.

### 4.3 Safety intersection

Safety is always **most restrictive wins**:

```
storage-ops:  destructive_requires_approval=true,  protected_paths=["/boot", "/dev"]
service-ops:  destructive_requires_approval=false, protected_paths=["/etc/systemd/"]

Intersection:
  destructive_requires_approval=true   (true OR false → true)
  protected_paths=["/boot", "/dev", "/etc/systemd/"]  (union of protected)
  blocked_commands=["mkfs", "dd of=/dev/", "systemctl disable sshd"]  (union)
```

### 4.4 Model selection

The highest-priority skill's model tier wins. If two skills have the same
priority, the one with more domain matches wins. Ties break to the more
capable model (specialist > chat > vision).

### 4.5 Budget allocation

> **Corrected 2026-08-27.** The mechanism below replaces an earlier version
> that multiplied `ContextAssembler.DEFAULT_PRIORITIES`. That dict's values
> are dead — see §16.4. Multiplying them would have been a silent no-op.

Context budget is not a set of ratios. `intake/budget.py` defines
`ContextBudget` as **absolute token counts per model tier**, with an
explicitly maintained invariant: the per-category fields sum to `total`.
`ContextAssembler._allocate_budget_from_intake()` reads those fields
directly on the live path.

So a skill cannot "multiply its retrieval budget" — that would break the
sum-to-total invariant and overrun the tier's context window. A skill
expresses budget appetite by **reallocating within the fixed total**:

```python
# ContextBudget for the active tier, e.g. MEDIUM
#   total=2000  retrieval=400  memory=300  discovery=300  observations=200 ...
#
# storage-ops wants retrieval depth. It does not raise `total`; it shifts
# tokens into retrieval from the categories it cares least about, then
# renormalizes so the invariant still holds.
```

Rules:
1. `total` is never changed by a skill — the tier owns it.
2. A skill declares relative *appetite* per category, not a multiplier.
3. When several skills are active, take the **max** appetite per category
   (not the mean — averaging dilutes a deep specialist against an incidental
   co-active generic skill).
4. Renormalize the reallocated categories back to `total`.
5. Floors are non-negotiable: `system_identity` and `user_rules` cannot be
   reduced by a skill, or role adoption would eat the base identity prompt.

The frontmatter field stays `budget_multiplier` for authoring ergonomics,
but it is interpreted as appetite weight, not as a multiplier on a token count.

## 5. The SourcePrep `assigned_to_role` Bridge

SourcePrep's `ScopeRecord` has an `assigned_to_role` field. **Verified
2026-08-27:** it is fully implemented daemon-side — `scope_store` CRUD,
`POST`/`PUT /scopes` accept it, and `scope_resolver.resolve_mask()` resolves
by it — but no Halbert scope sets it (all six live scopes report
`assigned_to_role: null`). So the bridge is built and unused, not reserved.

Two constraints the daemon imposes (see §16.2):
- **A role is unique per project.** Two scopes cannot share `assigned_to_role`,
  so one skill maps to at most one role-scope, and two skills cannot share a role.
- **`resolve_mask` accepts `role=` directly**, as a peer of `scope=`. Skills can
  send their role name and let the daemon resolve which scope carries it —
  see §16.5 for why that is the better bridge.

This is the structural bridge between skills and indexing:

```yaml
# SourcePrep scope definition
- id: host-storage
  paths: ["host/etc/fstab", "host/etc/zfs/", "host/etc/mdadm/"]
  assigned_to_role: storage-ops
  pipeline_profile: system_config

# Halbert skill definition
- name: storage-ops
  scope: host-storage    # matches assigned_to_role
```

When the storage-ops skill activates, it doesn't just query a scope —
it queries a scope that SourcePrep has **already indexed with the right
pipeline profile** (`system_config` for host files, `prose_docs` for
knowledge). The skill and the scope are two sides of the same coin:

- **SourcePrep side**: `assigned_to_role` tells the indexer "these files
  belong to the storage-ops role" → applies the right pipeline profile
  → generates the right enrichment, atlas segments, and prompt variants.
- **Halbert side**: `scope: host-storage` tells the retrieval backend
  "query the files indexed for storage-ops" → gets scope-filtered
  results with the right enrichment.

This means a skill isn't just a prompt — it's a **full vertical slice**
from indexing through retrieval through reasoning through safety.

### 5.1 Fine-grained scopes per role

Today Halbert has 5 scopes (host, knowledge-linux, knowledge-macos,
knowledge-bsd, knowledge-common). With `assigned_to_role`, we could
subdivide `host` into role-specific scopes:

| Scope | Paths | assigned_to_role | pipeline_profile |
|-------|-------|-----------------|-----------------|
| `host-storage` | `host/etc/fstab`, `host/etc/zfs/`, `host/etc/mdadm/` | storage-ops | system_config |
| `host-network` | `host/etc/network/`, `host/etc/iptables/`, `host/etc/resolv.conf` | network-ops | system_config |
| `host-security` | `host/etc/ssh/`, `host/etc/fail2ban/`, `host/etc/sudoers` | security-ops | system_config |
| `host-services` | `host/etc/systemd/`, `host/etc/cron.d/` | service-ops | system_config |

This gives each role a precisely scoped view of the host config tree.
A storage-ops query never retrieves nginx config; a security-ops query
never retrieves fstab.

### 5.2 Backward compatibility

The coarse `host` scope continues to work for unscoped queries. Fine-
grained scopes are additive — they partition the same files but with
role tags. A file can belong to multiple scopes (e.g. `/etc/ssh/sshd_config`
is in both `host-security` and `host-services` if SSH is considered a
service). Most-specific path prefix wins per SourcePrep's existing
overlap resolution.

### 5.3 Scope identifier normalization and fallback chain

> **Corrected 2026-08-27.** The hyphen/underscore concern described here was
> real but already handled; the *silent global fallback* was the actual bug,
> and it is now fixed. See §16.1.

1. **Identifier normalization** — already correct, no change needed.
   The pipeline is deliberate: `sourceprep_template.yml` writes a hyphenated
   `id` (`knowledge-linux`), which becomes the daemon's `display_name`; the
   daemon derives its own underscored `id` (`knowledge_linux`); and
   `scope_for_query()` emits that underscored id. Verified against the live
   daemon — the six provisioned scopes are `global`, `host`, `knowledge_bsd`,
   `knowledge_common`, `knowledge_linux`, `knowledge_macos`.

2. **Graceful scope fallback chain** — this was the real hazard, and the
   daemon's own behaviour is worse than this section originally assumed.
   `scope_resolver.resolve_mask()` rule 2 answers an *unknown* scope with
   `mask=None` — a full **global** union — plus an advisory `scope_warning`
   that Halbert was discarding. Requesting an unprovisioned `host_storage`
   did not degrade to `host`; it degraded to everything, invisibly. Confirmed
   live: a `host_storage`-scoped ZFS query on a macOS host was answered out
   of the FreeBSD handbook, defeating the `scope_mode="hard"` isolation
   guarantee.

   The fallback must therefore be enforced **client-side, before the request
   goes out**, not left to the daemon:

   $$\texttt{host\_storage} \longrightarrow \texttt{host} \longrightarrow \text{unscoped (deliberate)}$$

   Implemented in `SourcePrepRetrievalBackend.resolve_scope()`: it walks the
   underscore-delimited chain from most to least specific against the daemon's
   real scope list, returns the nearest provisioned ancestor, and returns
   `None` only when no ancestor exists — asking for an unscoped union on
   purpose rather than tripping the daemon's silent one. It fails *open*
   (returns the requested scope unchanged) when the scope list cannot be read,
   so a transient daemon hiccup does not widen retrieval. `_check_applied_scope()`
   logs `applied_scope` / `scope_warning` whenever the daemon does not honour
   the request.

   This is what lets fine-grained role scopes ship progressively: skills can
   declare `host_storage` today and degrade cleanly to `host` on any host
   where Phase 3 has not run.

## 6. Role-Scoped Subagents

For complex multi-domain problems, skills can spawn specialist subagents
with their own context windows. This follows open-claude-code's
`AgentTeams` pattern but with Halbert's scope awareness.

### 6.1 Example: backup system setup

```
User: "set up a new backup system with ZFS snapshots and restic to B2"

Intake → domains: [storage, backup, network, security]
       → skills match: storage-ops, backup-ops, security-ops

Halbert orchestrator decides this is multi-domain (3 skills, high complexity):
  → spawns 3 subagents in parallel

  ┌─ storage-ops subagent ──────────────────┐
  │ Scope: host-storage                     │
  │ Task: design ZFS snapshot schedule      │
  │ Model: specialist                       │
  │ Context: fstab, zfs config, pool status │
  └─────────────────────────────────────────┘
  ┌─ backup-ops subagent ───────────────────┐
  │ Scope: knowledge-linux                  │
  │ Task: configure restic with B2 backend  │
  │ Model: specialist                       │
  │ Context: restic man pages, arch wiki    │
  └─────────────────────────────────────────┘
  ┌─ security-ops subagent ─────────────────┐
  │ Scope: host-security                    │
  │ Task: review B2 credentials, encryption │
  │ Model: specialist                       │
  │ Context: ssh config, fail2ban, cert dir │
  └─────────────────────────────────────────┘

  Orchestrator synthesizes:
  → "Here's your backup plan: ZFS snapshots every hour,
     restic to B2 nightly at 2am, B2 key in /etc/restic/env
     (chmod 600). Review the security notes about key rotation."
```

### 6.2 Subagent isolation

Each subagent:
- Has its own context window (no cross-contamination)
- Queries only its skill's scope (no scope bleeding)
- Uses its skill's model tier
- Is bound by its skill's safety constraints
- Returns a structured result to the orchestrator

The orchestrator (running on the orchestrator model) synthesizes the
subagent results into a single response. It does not re-retrieve — it
works from the subagent outputs.

### 6.3 When to spawn subagents

Not every multi-skill query needs subagents. Heuristics:

| Condition | Action |
|-----------|--------|
| 1 skill active | No subagent — inline execution |
| 2 skills, same model tier | Inline with composed prompt |
| 2+ skills, different model tiers | Consider subagents |
| 3+ skills active | Subagents (complexity warrants parallelism) |
| Explicit `/storage-ops /backup-ops` invocation | Subagents (user requested specialists) |
| `subagent: true` in skill frontmatter | Always subagent |

---

## 7. Hooks System

Adapted from open-claude-code's `HookEngine` (6 event types) with
Halbert-specific safety and automation hooks.

### 7.1 Event types

| Event | When it fires | Halbert use case |
|-------|--------------|-----------------|
| `PreToolUse` | Before any tool execution | Safety gate: check destructive commands, protected paths, blocked commands |
| `PostToolUse` | After tool execution completes | Verify side effects: did the service actually restart? did the config file actually change? |
| `PrePrompt` | Before sending prompt to LLM | Inject skill prompts, adjust system message |
| `PostResponse` | After LLM generates response | Filter output, add safety disclaimers for destructive suggestions |
| `Stop` | Before Halbert ends a turn | Check for unresolved failures, prompt to investigate |
| `Notification` | Fire-and-forget events | Config file changed → trigger SourcePrep edge refresh + scope rebuild |

### 7.2 Hook definitions

Hooks are defined in skills (scoped to activation) or globally in
`~/.config/halbert/hooks.toml`:

```toml
# Global hooks
[[PreToolUse]]
name = "destructive-command-gate"
command = "python3 -m halbert_core.hooks.safety_gate"
timeout = 5000
failOpen = false   # if the hook crashes, BLOCK the tool (fail closed)

[[Notification]]
name = "config-change-reactor"
event = "config_file_changed"
command = "python3 -m halbert_core.hooks.config_reactor"
timeout = 30000
```

```yaml
# Declarative safety & hooks in SKILL.md frontmatter
safety:
  destructive_requires_approval: true
  blocked_commands:
    - "zpool destroy*"
    - "mkfs*"
    - "dd if=* of=/dev/*"
  protected_paths:
    - "/boot/**"
    - "/dev/**"
    - "/proc/**"
    - "/sys/**"
    - "/etc/zfs/**"
  protected_services:
    - "sshd"
    - "systemd-journald"

hooks:
  PostToolUse:
    - name: verify-pool-health
      tools: [exec]
      command_pattern: "*zpool*"
      action: run_followup
      followup: "zpool status"
```

### 7.3 The safety gate

> **Corrected 2026-08-27.** The original design added a standalone
> `fnmatch`-based gate. Halbert already has four enforcement layers; a fifth,
> parallel one would be bypassable and would drift. See §16.6.

Skill safety constraints must **compile into the enforcement chain that
already runs**, not sit beside it. What exists today:

| Layer | Role |
|-------|------|
| `tools/safety.py` `ToolSafetyFramework` | `classify(tool, args)` → `RiskLevel`; the actual policy brain |
| `tools/executor.py` (`execute`, ~L250–273) | The single choke point: CRITICAL blocks, HIGH requires confirmation |
| `policy/engine.py` + `loader.py` | Declarative YAML policy from `config_dir()/policy.yml` |
| `approval/engine.py` `ApprovalEngine` | Approval request/queue/history, CLI + dashboard prompts |
| `prompts/safety.py` `SafetyValidator` | Injection detection, command classification, output filtering |

Every tool call already passes through `ToolExecutor.execute()`, which
already consults `ToolSafetyFramework.classify()` and already escalates HIGH
risk to confirmation. The FSM already has an `AWAITING_CONFIRMATION` state
wired to that path.

So the skill layer contributes **rules**, not enforcement:

```
SKILL.md safety: block
    │
    ▼
skills/composer.py  — intersect across active skills (most restrictive wins)
    │
    ▼
ToolSafetyFramework.classify()  — skill rules evaluated alongside built-in rules
    │                              protected_paths / protected_services → HIGH
    │                              blocked_commands                     → CRITICAL
    ▼
ToolExecutor.execute()  — existing choke point, unchanged
    │
    ▼
ApprovalEngine → FSM AWAITING_CONFIRMATION  — existing approval flow, unchanged
```

This deletes most of the original Phase 3: no new gate, no new approval flow,
no new hook plumbing for safety. What is left is a rule-compilation step and
a way to scope rules to the currently active skills. It also means skill
safety cannot be bypassed by any code path that skips the hook engine,
because there is no separate hook engine in the safety path.

The `hooks/` engine (§7.1) is still worth building for `PostToolUse`
verification, `Notification` config reactions, and `Stop` checks — but
**not** for `PreToolUse` safety.

### 7.4 The config reactor

The `Notification` hook for config changes wires into the existing
ConfigWatcher → SourcePrep edge refresh pipeline:

```
Config file changed
    │
    ▼
Notification hook fires
    │
    ▼
config_reactor.py:
    1. Identify which scope the file belongs to (path → scope mapping)
    2. Re-stage the file into sourceprep/host/
    3. Push updated external edges (edge_extractor.py)
    4. Trigger debounced scope rebuild (SourcePrep API)
    5. Log the change as a SourcePrep Concept (rationale capture)
```

---

## 8. User-Customizable Skills

### 8.1 The value proposition

This is where the Claude Code model shines for Halbert. Users create
skills that encode **their specific setup** — not generic domain
knowledge, but the particular quirks of their machine:

**`~/.config/halbert/skills/homelab-nginx/SKILL.md`**:
```yaml
---
name: homelab-nginx
description: My nginx reverse proxy setup (3 services, TLS termination)
triggers:
  domains: [network, service]
  keywords: [nginx, proxy, tls, 502, 503]
scope: host
model: specialist
priority: high
safety:
  destructive_requires_approval: true
  protected_paths: ["/etc/nginx/sites-enabled/homelab.conf"]
---

My nginx setup: reverse proxy for jellyfin (port 8096),
nextcloud (port 8443), and gitea (port 3000). TLS certs via certbot.

Common failures:
- Certbot renewal breaks → check /etc/letsencrypt/renewal/ and
  run `certbot renew --dry-run`
- 502 on jellyfin → check if jellyfin.service is running
- Nextcloud maintenance mode → `sudo -u www-data php occ maintenance:mode --off`

Config at /etc/nginx/sites-available/homelab.conf.
Always reload (not restart) nginx after config changes: `nginx -t && systemctl reload nginx`.
```

**`~/.config/halbert/skills/macbook-dev/SKILL.md`**:
```yaml
---
name: macbook-dev
description: My MacBook dev environment (Homebrew, pyenv, nvm)
triggers:
  domains: [config]
  keywords: [brew, python, node, pyenv, nvm]
platform: [darwin]
scope: knowledge-macos
model: orchestrator
priority: normal
---

This machine uses Homebrew at /opt/homebrew, pyenv for Python,
nvm for Node.

When Python version issues arise, check `pyenv versions` and
~/.python-version. When brew update fails, run `brew doctor` first.

Key paths:
- Homebrew: /opt/homebrew/bin/brew
- pyenv: ~/.pyenv/versions/
- nvm: ~/.nvm/versions/node/
- Shell config: ~/.zshrc (sources ~/.zprofile for pyenv/nvm init)
```

### 8.2 Skill packs

Users could share skill packs via git:

```bash
# Install a skill pack from git
halbert skills install https://github.com/user/halbert-skills-homelab

# List installed skills
halbert skills list

# Remove a skill pack
halbert skills remove halbert-skills-homelab
```

A skill pack is a directory with a `pack.json` manifest:

```json
{
  "name": "halbert-skills-homelab",
  "version": "1.0.0",
  "description": "Skills for homelab server management",
  "skills": ["nginx-proxy", "docker-compose", "pi-hole", "adguard"],
  "hooks": ["config-change-reactor"],
  "scopes": [
    {"id": "host-nginx", "paths": ["host/etc/nginx/"], "assigned_to_role": "nginx-proxy"}
  ]
}
```

Installing a skill pack:
1. Clones the repo to `~/.config/halbert/skills/packs/<name>/`
2. Registers skills in the skill loader
3. Registers hooks in the hook engine
4. Creates SourcePrep scopes via API (if not already present)
5. Triggers a scope rebuild for new scopes

### 8.3 Built-in skills

Halbert ships with a set of built-in skills that cover the 6 intake
domains:

| Skill | Domains | Scope | Model | Priority |
|-------|---------|-------|-------|----------|
| `storage-ops` | storage, backup | host + knowledge-* | specialist | high |
| `service-ops` | service | host + knowledge-* | orchestrator | normal |
| `network-ops` | network | host + knowledge-* | specialist | high |
| `security-ops` | security | host + knowledge-* | specialist | critical |
| `config-ops` | config | host | orchestrator | normal |
| `discovery-ops` | (all) | host | orchestrator | low |

These live in `halbert_core/halbert_core/skills/builtin/` and are always
available as core components of the Halbert App. User skills in
`~/.config/halbert/skills/` and host-local `.halbert/skills/` override
built-ins with the same name.

---

## 9. Architecture

### 9.1 Module layout

```
halbert_core/halbert_core/
  skills/
    __init__.py
    loader.py          # Load SKILL.md from builtin/ + ~/.config/halbert/skills/ + .halbert/skills/
    parser.py          # Parse SKILL.md frontmatter + body
    matcher.py         # Match intake signals → skills (domain, keyword, platform, intent)
    activator.py       # Activate skill: inject prompt, set scope, apply safety, allocate budget
    composer.py        # Compose multiple active skills (merge prompts, union scopes, intersect safety)
    registry.py        # In-memory skill registry + CRUD
    builtin/           # Built-in skills shipped with Halbert
      storage-ops/SKILL.md
      service-ops/SKILL.md
      network-ops/SKILL.md
      security-ops/SKILL.md
      config-ops/SKILL.md
      discovery-ops/SKILL.md
  hooks/
    __init__.py
    engine.py          # Hook engine: PreToolUse, PostToolUse, PrePrompt, PostResponse, Stop, Notification
    safety_gate.py     # Destructive-op approval flow (PreToolUse hook)
    config_reactor.py  # Config-change → SourcePrep edge refresh (Notification hook)
    stop_check.py      # Unresolved-failure check (Stop hook)
  agents/
    subagent.py        # Role-scoped subagent with own context window + scope-filtered retrieval
    teams.py           # Multi-agent orchestration (storage + backup + security → plan)
    orchestrator.py    # Decides when to spawn subagents vs inline execution
```

### 9.2 Integration points

| Component | How skills integrate |
|-----------|---------------------|
| `intake/signals.py` | No change — `MessageSignals.detected_domains` feeds the matcher |
| `intake/pipeline.py` | Receives active skills from matcher, passes to assembler |
| `context/assembler.py` | Accepts `active_skills` param; adjusts priorities, injects prompts, filters scopes |
| `context/adapters.py` | `SourcePrepAdapter.search()` accepts scope from active skills |
| `integrations/sourceprep_retrieval_backend.py` | `scope_for_query()` enhanced: skill scope overrides regex heuristic |
| `agents/state_machine.py` | `advance_turn()` calls matcher at PLANNING, passes skills to assembler at SEARCHING |
| `model/client.py` | `get_configured_model()` checks active skills for model tier override |
| `prompts/safety.py` | SafetyValidator delegates to active skills' safety constraints |
| `config/watcher.py` | Fires Notification hook on config change |

### 9.3 Data flow through the state machine

```
PLANNING
  │
  ├── intake/signals.py → MessageSignals
  ├── skills/matcher.py → active_skills[]
  ├── skills/composer.py → composed context (prompts, scopes, safety, model, budget)
  └── agents/orchestrator.py → decide: inline or subagents?
          │
          ▼
SEARCHING
  │
  ├── context/assembler.py.assemble(
  │     query, intake, active_skills=composed.skills
  │   )
  │     ├── SourcePrepAdapter.search(query, scope=composed.scope)
  │     ├── TelemetryAdapter.search(query)  [if error keywords]
  │     ├── FailureCorrelationAdapter.search(query)  [if error keywords]
  │     └── SystemIdentityAdapter.search(query)  [always]
  │
  ▼
EXECUTING
  │
  ├── hooks/engine.py.runPreToolUse(tool, input)
  │     └── safety_gate.py checks active skills' safety constraints
  │         └── if destructive + requires_approval → AWAITING_CONFIRMATION
  ├── tool execution
  └── hooks/engine.py.runPostToolUse(tool, result)
          └── verify side effects
  │
  ▼
OBSERVING
  │
  └── collect observations, check for new failures
  │
  ▼
REFLECTING
  │
  ├── Haloysius cognitive tick (existing)
  └── skills still active (same turn)
  │
  ▼
RESPONDING
  │
  ├── hooks/engine.py.runPostResponse(response)
  │     └── add safety disclaimers if destructive suggestions
  ├── hooks/engine.py.runStop()
  │     └── stop_check.py: any unresolved failures? prompt to investigate
  └── skills deactivated (turn complete)
```

---

## 10. Dynamic Skill Composition (advanced)

### 10.1 Cross-domain queries

A query about "encrypted ZFS backup over SSH" spans three domains:

```
Intake → domains: [storage, backup, network, security]
       → skills: storage-ops, backup-ops, security-ops

Composer:
  Prompts:  storage-ops + backup-ops + security-ops (concatenated)
  Scopes:   host_storage + host_security + knowledge_linux (fallback to host if unpartitioned)
  Safety:   destructive_requires_approval=true (any skill → true)
            protected_paths = union of all skills' protected_paths
  Model:    specialist (highest priority among active skills)
  Budget:   retrieval × 1.8 (max of active multipliers, capped at 2.0)
```

### 10.2 Skill inheritance

Skills can extend other skills:

```yaml
---
name: zfs-ops
extends: storage-ops
triggers:
  keywords: [zfs, zpool, dataset, snapshot]
safety:
  blocked_commands: ["zpool destroy"]   # adds to parent's blocked list
---

Additional ZFS-specific rules:
- Always check pool health before modifying datasets
- Snapshot before any destructive zfs operation
- Never destroy a dataset that has snapshots unless --r flag is explicit
```

The parser resolves `extends` by merging parent + child frontmatter
(child overrides for scalar fields, unions for list fields).

### 10.3 Skill conditions

Skills can have conditional activation rules:

```yaml
---
name: low-disk-space
triggers:
  domains: [storage]
  conditions:
    - type: telemetry
      metric: disk_usage_percent
      operator: ">"
      value: 85
scope: host
priority: critical
---

Disk space is critically low (>85%). Prioritize cleanup suggestions.
Check for: large log files, old journal entries, docker images,
package cache. Suggest `journalctl --vacuum-size=100M` and
`docker system prune` as first steps.
```

The matcher evaluates conditions against the telemetry adapter's live
readings. This enables **proactive skill activation** — Halbert notices
low disk space and activates the cleanup skill before the user asks.

---

## 11. Implementation Phases

> **Resequenced 2026-08-27.** Two changes from the original plan. A Phase 0
> was added for corrections the later phases silently assumed were already
> true. And the original Phase 2/3 split — which shipped the `safety:` block
> one phase before anything enforced it — is merged: a skill that advertises
> `protected_paths` while enforcing nothing is worse than one that has no
> safety field at all.

### Phase 0 — Correct the assumed foundations ✅ *(scope work done)*

| Task | Status | Files |
|------|--------|-------|
| Client-side scope fallback chain + `applied_scope`/`scope_warning` logging | **done** | `sourceprep_retrieval_backend.py`, `sourceprep_client.py` |
| `resolve_role()` — role → scope id locally, never `role=` over the wire (§16.5) | **done** | `sourceprep_retrieval_backend.py` |
| `list_scopes()` on the client; `_get()` gains `project_id` | **done** | `sourceprep_client.py` |
| Tests: fallback chain, fail-open, caching, warning surfacing, role mapping | **done** (11 pass) | `tests/test_sourceprep_retrieval_backend.py` |
| Budget mechanism corrected to reallocation (§4.5) | plan only — code lands in Phase 2 | — |
| Model tier vocabulary corrected to `chat`/`specialist`/`vision` | plan only | — |

**Deliverable:** fine-grained role scopes can be declared before they are
provisioned without silently widening retrieval. This unblocks Phase 3 from
having to land atomically with a SourcePrep rebuild.

### Phase 1 — Skill loader + matcher (foundation) ✅ *done*

| Task | Status | Files |
|------|--------|-------|
| `skills/parser.py` — frontmatter + body, tier/priority validation, scope canonicalization | **done** | new |
| `skills/loader.py` — 4 dirs, both layouts, malformed files skipped not fatal | **done** | new |
| `skills/registry.py` — registry, aliases, `extends` flattening | **done** | new |
| `skills/matcher.py` — signals → skills; resolves platform itself (§16.7) | **done** | new |
| Wire matcher into `intake/pipeline.py` (optional, additive) | **done** | modified |
| Tests | **done** (29 pass) | `tests/test_skills.py` |

**Deliverable:** Skills load and match against intake signals. No retrieval,
budget, or safety integration yet — just the activation pipeline.

Decisions taken during implementation:

- **Activation is conservative.** `MIN_SCORE` equals one domain hit, so a
  keyword alone cannot activate a skill and a skill with no triggers never
  auto-activates (it stays reachable explicitly). Weights: domain 3, keyword 2.
- **Platform and intent are filters, not contributors.** A skill restricted to
  a platform we are not on cannot activate at any score — otherwise every
  `platform: [darwin]` skill would score on every macOS turn.
- **Skills carry a `role`, not just a `scope`.** Per §16.5, `role:` is the
  preferred bridge and is left hyphenated; `scope:` is canonicalized to
  underscores, since a scope name a skill invents has no daemon-side
  `display_name` mapping to save it from silently widening.
- **Matching never fails a turn.** A broken skill file or a throwing matcher
  costs the turn its expertise prompt and role scope, not its answer.

### Phase 2 — Composer, context, and safety *(was Phase 2 + Phase 3)*

| Task | Est. lines | Files |
|------|-----------|-------|
| `skills/composer.py` — merge prompts, union scopes, intersect safety, max-appetite budget | 120 | new |
| `context/assembler.py` — accept `active_skills`; reallocate within `ContextBudget` total | 50 | modified |
| `context/adapters.py` — scope from active skills instead of `scope_for_query()` | 20 | modified |
| Skill safety rules compiled into `ToolSafetyFramework.classify()` (§7.3) | 80 | modified |
| `model/client.py` — model tier from active skills | 20 | modified |
| Tests: composer, budget invariant, scope routing, safety compilation | 250 | new |

**Deliverable:** Active skills shape retrieval scope, context budget, model
selection, **and enforced safety** — in one step, through the existing
`ToolExecutor` → `ApprovalEngine` chain.

### Phase 3 — Built-in skills + SourcePrep role scopes

| Task | Est. lines | Files |
|------|-----------|-------|
| 6 built-in SKILL.md files (storage, service, network, security, config, discovery) | 300 | new |
| Assign `assigned_to_role` to the three **shipped** `*_admin` scopes (§16.9) | 15 | SourcePrep-side config |
| Path-mask migration: role scopes from staged copies to masks (§16.9) | 60 | `roles.py`, template |
| `sourceprep_setup.py` — provision role scopes; `invalidate_scope_cache()` after | 40 | modified |
| `sourceprep_template.yml` — role definitions (**keep hyphens** — §16.1, do not migrate) | 30 | modified |
| Tests: built-in skill activation, role-scoped retrieval, fallback when unprovisioned | 100 | new |

**Deliverable:** Halbert ships with 6 domain skills. Thanks to Phase 0, they
work before the role scopes exist and sharpen once provisioned.

### Phase 4 — Hooks engine *(was part of Phase 3)*

| Task | Est. lines | Files |
|------|-----------|-------|
| `hooks/engine.py` — 5 events (PreToolUse safety is **not** here — §7.3) | 130 | new |
| `hooks/config_reactor.py` — Notification → SourcePrep edge refresh | 60 | new |
| `hooks/stop_check.py` — Stop → unresolved failure check | 40 | new |
| Wire into `state_machine.py` and `config/watcher.py` | 50 | modified |
| Tests: config reactor, stop check, hook engine | 150 | new |

### Phase 5 — Subagents + skill packs (advanced)

Unchanged from the original Phase 5.

### Phase 6 — Proactive activation + conditions (advanced)

Unchanged from the original Phase 6.

## 12. Open Questions & Resolutions

1. **Scope union vs single-scope retrieval**: Resolved by the fallback
   chain in §5.3. Pick the highest-priority skill's scope, canonically
   normalize to underscores (`host_storage`), and if not provisioned on
   the daemon, gracefully fall back to `host`. Multi-scope union can
   follow in v2.

2. **Skill precedence when user invokes `/skill <name>` explicitly vs
   auto-matched skills**: Explicit `/skill <name>` invocation overrides
   auto-matching for that turn (predictable behavior). Pinning via
   `/skill pin <name>` locks the skill across turns until `/skill unpin`.

3. **Fine-grained host scopes vs single `host` scope**: Fine-grained
   scopes (`host_storage`, `host_network`, etc.) give precise retrieval.
   With the §5.3 fallback chain, fine-grained scopes can be introduced
   progressively: skills declare them today, but immediately fall back to
   coarse `host` on unpartitioned daemons.

4. **Skill prompt injection point**: Inject as a system message (before
   conversation) or as a user message (before the query)? System message
   is more natural for "role adoption" but some models weight user
   messages higher. Recommendation: system message, consistent with
   how SystemIdentityAdapter works today.

5. **Hook execution model**: Shell commands (like open-claude-code) or
   Python callables? Built-in hooks use in-process Python callables
   (fast, zero fork overhead). User-defined hooks in `hooks.toml` use
   sandboxed subprocesses with env-var-only context passing (matching
   open-claude-code's security model).

6. **Skill versioning and compatibility**: When a skill pack depends on
   a specific SourcePrep scope layout or Halbert API version, how do we
   express and enforce that? Recommendation: `pack.json` includes
   `halbert_version` and `sourceprep_version` constraints; loader warns
   on mismatch.

7. **Skill discovery for auto-activation**: The matcher scores skills by
   domain/keyword/platform/intent overlap. What's the activation
   threshold? Start conservative (require ≥1 domain match), tune based
   on usage logs.

8. **Cross-session skill state & memory**: Resolved. Diagnostic outcomes,
   root-cause findings, and configuration actions taken under an active
   skill are logged as SourcePrep Concepts (`POST /concepts`) at turn
   completion. In future sessions, SourcePrep's concept recall surface
   automatically re-surfaces that operational history without carrying
   stale session transcripts.

---

## 13. Relationship to Existing Work

| Existing system | Relationship |
|----------------|-------------|
| SourcePrep scopes + pipeline profiles | Skills consume scopes; `assigned_to_role` is the bridge |
| Intake signals (`signals.py`) | Feeds the skill matcher — no changes needed |
| Context assembler (`assembler.py`) | Extended to accept `active_skills` for budget/priority adjustment |
| SourcePrep retrieval backend | `scope_for_query()` enhanced: skill scope takes precedence |
| Agent state machine | Hooks fire at state transitions; skills activate at PLANNING |
| Haloysius cognitive core | Skill prompts become part of the cognitive context at REFLECTING |
| ConfigWatcher | Fires Notification hook → config_reactor → SourcePrep refresh |
| Config edge extractor | Runs as part of config_reactor hook |
| Model router / tier router | Skill model tier overrides complexity-based routing |
| Safety validator | Delegates to active skills' safety constraints |
| Cross-session continuity | Skill activations logged as Concepts for recall |

---

## 14. Risks and Mitigations

| Risk | Mitigation |
|------|-----------|
| Skill prompt injection bloats context window | Budget multiplier caps skill prompt tokens; prompts truncated to N tokens |
| Too many skills activate simultaneously | Matcher threshold + max active skills limit (default 3) |
| User skill contains malicious hook | Shell hooks run with user's permissions but are validated against allowlist; Python hooks must be in trusted paths |
| Fine-grained scopes increase SourcePrep build time | Scopes are additive; existing single-scope builds unchanged; fine-grained scopes only created when skill pack requests them |
| Skill conflicts (two skills, same domain, different safety rules) | Most-restrictive-wins for safety; highest-priority-wins for model; union for scopes |
| Skill pack installs malicious scope that reads sensitive files | Scope paths validated against exclude_globs (ssl, shadow, keys); SourcePrep's existing exclude patterns apply |

---

## 15. Summary

Role-scoped skills unify five scattered concerns — retrieval scope,
domain detection, safety constraints, context budget, and model tier —
into a single declarative unit that users can create, share, and compose.

The architecture has three layers:

1. **Skills** (`SKILL.md`): Domain expertise + retrieval scope + safety +
   model + budget, activated by intake signals or explicit invocation
2. **Hooks**: Event-driven safety gates and automation reactors that
   fire at state machine transitions
3. **Subagents**: Role-scoped specialists with own context windows for
   complex multi-domain problems

The SourcePrep `assigned_to_role` field is the keystone: it connects
the indexing layer (which pipeline profile, which enrichment, which
prompt variants) to the skill layer (which scope to query, which
expertise to inject). A skill isn't just a prompt — it's a full
vertical slice from indexing through retrieval through reasoning
through safety.

At full maturity, this turns Halbert from "a chatbot with RAG" into "a
role-based operations team that lives on your machine" — one that knows
your specific setup, applies the right safety constraints automatically,
and can spawn specialist subagents for complex problems.

---

## 16. Verified Against Implementation (2026-08-27)

Every claim in §1's table and §9.2's integration points was checked against
the codebase, and the scope behaviour was checked against a **live SourcePrep
daemon** (`localhost:8400`, standalone project `735a592e`). What follows is
what the original draft got wrong.

**Confirmed accurate:** `intake/signals.py` `_DOMAIN_KEYWORDS` (6 domains),
`ContextAssembler.DEFAULT_PRIORITIES` (exact values), `scope_for_query()` as
a regex heuristic, the five-scope template with per-scope `pipeline_profile`,
the FSM's `AWAITING_CONFIRMATION` state, `ConfigWatcher`, `edge_extractor`.

### 16.1 The silent global fallback (fixed in Phase 0)

`scope_resolver.resolve_mask()` rule 2 answers an unknown scope with
`mask=None` — a full global union — and an advisory `scope_warning` that
Halbert discarded at `context/adapters.py`. Reproduced live:

```
POST /projects/{halbert}/context  {"scope": "host_storage", "scope_mode": "hard"}
→ applied_scope  = "global"
  scope_warning  = "requested 'host_storage' not found, used global"
  chunk 1        = knowledge/bsd/freebsd-handbook/freebsd_handbook_03.md
```

A ZFS query scoped to `host_storage` on a **macOS** host was answered from the
FreeBSD handbook — precisely the cross-platform leak `scope_mode="hard"` was
added to prevent. Fixed by `resolve_scope()` (§5.3). Post-fix, the same query
narrows to `host` and returns host config files.

### 16.2 `assigned_to_role` is built, not reserved

Contrary to §5's original claim, it is fully implemented daemon-side:
`scope_store` create/update, `POST`/`PUT /scopes`, and `resolve_mask()`, all
under test in SourcePrep's suite. Halbert simply never sets it — all six live
scopes report `assigned_to_role: null`.

Two constraints follow:
- **Uniqueness per project** (`test_assigned_to_role_uniqueness`): two scopes
  cannot share a role. One skill ↔ at most one role-scope; no shared roles.
- **`resolve_mask` takes `role=` as a peer of `scope=`**, and the context
  response echoes `applied_role`.

### 16.3 Model tier vocabulary is stale

`model/llm_config.py` defines `SLOTS = ("chat_model", "specialist_model",
"vision_model")` and lists `orchestrator`/`specialist`/`vision` in
`LEGACY_KEYS` with a live migration path. The draft's frontmatter used the
legacy names throughout. Corrected to `chat` / `specialist` / `vision`.

### 16.4 `DEFAULT_PRIORITIES` values are dead

`self.priorities` is referenced at `assembler.py` lines 142, 284, and 346 —
every one of them `list(self.priorities.keys())`, i.e. as a **source-name
list**. The values are never used as weights. The non-intake path uses a
hardcoded `base_ratios` dict; the live path uses
`_allocate_budget_from_intake()`, which reads `ContextBudget` fields directly.

The draft's `retrieval: 0.8 × 1.8 = 1.44` would have multiplied a number
nothing reads. Worse, `ContextBudget` holds **absolute token counts with a
sum-to-total invariant**, so even a correctly-targeted multiplier would have
overrun the tier's context window. Hence the reallocation model in §4.5.

### 16.5 Use the role as the bridge — but resolve it locally, never over the wire

A skill should identify itself by **role**, not by scope id, so the two names
stay decoupled (the two-sides-of-the-same-coin framing in §5 becomes literal).
That part is adopted.

But `role=` **must not be sent to the daemon.** Probed live 2026-08-27 with an
unassigned role, `resolve_mask()`'s role path fails open *and silently*:

```
role=storage-ops  →  applied_scope : "global"       ← silently widened
                     applied_role  : "storage-ops"  ← echoed as though honoured
                     scope_warning : null           ← no warning at all
```

That is strictly worse than the scope path, which at least sets
`scope_warning` (§16.1). A ZFS query under an unprovisioned role was answered
out of the FreeBSD handbook on a macOS host.

**Resolution:** `SourcePrepRetrievalBackend.resolve_role()` maps role → scope
id locally, against `assigned_to_role` in the daemon's scope list, then routes
through the hardened `resolve_scope()` path. An unassigned role returns None
and the caller falls back to its own scope rather than querying by role.

### 16.6 Four safety layers already exist

`ToolSafetyFramework`, the `ToolExecutor.execute()` choke point, the
`policy/` engine, and `ApprovalEngine` — plus `SafetyValidator`. The draft's
standalone `fnmatch` gate would have been a fifth, parallel, bypassable path.
See §7.3 for the compile-into-the-existing-chain design.

### 16.7 `MessageSignals` has no `platform` field

§3.1's pipeline diagram shows `.platform: darwin` emerging from intake. It
does not exist. `scope_for_query()` derives platform itself, from
`platform.system()` plus a regex over the query text. The matcher must do the
same to honour `triggers.platform`; it cannot read it off the signals object.

### 16.8 Naming nit

`SourcePrepRetrievalBackend.search()` still takes the scope as `figure_id`, a
leftover from the Haloysius `RetrievalBackend` protocol. It maps correctly to
`scope=`, so this is cosmetic — but it should be renamed before skills make
scope routing a first-class concern.

### 16.9 Reconciliation with role-scoped config harvesting

This design was written the same day as, and independently of,
`.handoff/ROLE-SCOPED-CONFIG-HARVESTING-DESIGN-2026-08-26.md`, which **shipped**
(`511dd5d`) three role scopes over the host config tree. Both partition the same
thing. Reconciled in `documentation/design/SCOPE-AXES-RECONCILIATION-2026-08-27.md`;
the outcome for this document:

- **Scope names:** keep the shipped, indexed, underscored ids. This design's
  `host-storage`/`host-network`/`host-services` name the *same partitions*, so
  adopting them would duplicate indexed scopes. The skill declares a role; the
  scope keeps its id.

  | scope id | role a skill declares | status |
  |---|---|---|
  | `storage_admin` | `storage-ops` | shipped — role not yet assigned |
  | `network_admin` | `network-ops` | shipped — role not yet assigned |
  | `service_admin` | `service-ops` | shipped — role not yet assigned |
  | `security_admin` | `security-ops` | not built — wave 2 |
  | `config_admin` | `config-ops` | not built — wave 2 |

- **Path model:** this design's masks-over-the-flat-tree model wins over the
  shipped staged-copy model. The harvesting design had deferred that choice as
  a KNOWN LIMITATION (staging 42 → 99 files, 40 duplicated, and `trace_expand`
  finding no edges inside a role scope). Two independent designs converging on
  masks settles it.

- **Skills are not a fourth axis.** They are the *consumer* of the platform
  axis and the role axis. That is what makes this work the routing layer the
  harvesting work lacks — the shipped `*_admin` scopes are currently
  **unreachable at query time**, because `scope_for_query()` can only return
  `None`, `host`, or `knowledge_<platform>`. The matcher is what reaches them.

### 16.10 Prior findings now resolved

`.handoff/HANDOFF-SCOPE-FILTER-REVIEW-2026-08-26.md` recorded three defects
that would have invalidated this design's retrieval assumptions. All three are
fixed as of 2026-08-27, verified live:

| Finding | Was | Now |
|---|---|---|
| F1 — structured `/context` replaced chunks with file heads | 1 anonymous 12k blob per query | real chunks with `text`; 4451 → 3730 chars |
| F2 — `host/` had **zero** indexed files (`host/**` matches dirs only on Py3.11) | `scope=host` returned nothing | `host/etc/ssh/sshd_config` returned |
| F3 — `scope_mode` boosted rank instead of filtering | cross-platform probes leaked 4/4 | leak probes pass; hard mode pre-filters |

F2's fix (`host/**` → `host/**/*`) and the client's `scope_mode="hard"` are
still **uncommitted** in the working tree — see reconciliation §8.4 item 1.
