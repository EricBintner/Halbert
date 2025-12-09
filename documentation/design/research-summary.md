# Research Summary

This document condenses the research that informed Cerebric's design. The full research (79 user scenarios, 120+ tools analyzed, forum deep-dives) is distilled here into the key insights that shaped the architecture.

---

## Core Research Question

> What do Linux system administrators actually struggle with, and how could an AI-powered tool help?

The research analyzed real user pain points from StackOverflow, Reddit (/r/linux, /r/sysadmin, /r/selfhosted), and Level1Techs forums.

---

## Key Findings

### 1. systemd is the #1 Confusion Point

**The Problem**:
- Users don't understand cryptic failure messages
- Root causes are hidden ("disk full" manifests as "docker.service failed to start")
- The man pages are comprehensive but not accessible

**Example**:
```
User sees: "Job for docker.service failed because the control process exited"
Actual cause: /var partition is 100% full, journald can't write
```

**Design Implication**: Cerebric should explain systemd errors in plain English and trace root causes.

---

### 2. Disk Space Always Fills Up

**Typical Reclaimable Space**:
| Source | Typical Waste |
|--------|---------------|
| Docker images/containers | 50-100 GB |
| Logs (no rotation) | 10-30 GB |
| Package caches (apt, npm, pip) | 20-40 GB |
| Forgotten trash | 10-20 GB |
| **Total** | **100-200 GB typical** |

**The Problem**: Users don't know WHERE space went, just that it's gone.

**Design Implication**: Cerebric should categorize disk usage and suggest safe cleanup.

---

### 3. I/O Wait is Misunderstood

**The Problem**:
- Users see "CPU at 45%" but the system is slow
- They don't realize I/O wait (10-15%) is the actual bottleneck
- The cascading effect: Disk full → slow I/O → swap → CPU wait

**Example**:
```
User: "My CPU is barely used, why is everything slow?"
Answer: iowait is 15%, disk is the bottleneck
```

**Design Implication**: Cerebric should surface I/O wait prominently and explain it.

---

### 4. Package Manager Locks Cause Panic

**The Problem**:
- Users kill apt/dnf mid-update (corrupts the database)
- They don't know: Who has the lock? How long will it take? Is it safe to wait?

**Dangerous Pattern**:
```bash
# User runs:
sudo kill -9 $(pgrep apt)
# Result: Corrupted dpkg database
```

**Design Implication**: Cerebric should explain locks, show progress, and warn against killing.

---

### 5. Backups are Set-and-Forget

**The Problem**:
- Users configure backups once, never verify they work
- Cron jobs fail silently (syntax errors, permission issues)
- External drives get disconnected (backups skipped)
- Nobody tests restores until disaster strikes

**Design Implication**: Cerebric should proactively validate backups and alert on failures.

---

### 6. Configuration File Confusion

**The Problem**:
- Which config file is authoritative? (systemd service, drop-in, environment file?)
- What did I change and when?
- "It worked before I upgraded"

**Design Implication**: Cerebric should track config changes with diffs and timestamps.

---

## Tool Categories Identified

Research identified ~120 tools needed across categories:

| Category | Examples | Priority |
|----------|----------|----------|
| **System Health** | CPU, memory, disk, temperature | HIGH |
| **Process Management** | systemd, services, cgroups | HIGH |
| **Package Management** | apt, dnf, pacman, locks, updates | HIGH |
| **Disk Management** | Space analysis, cleanup, SMART | HIGH |
| **Backup** | Validation, restore testing, scheduling | HIGH |
| **Networking** | DNS, firewall, connectivity, VPN | MEDIUM |
| **Performance** | Bottleneck detection, profiling | MEDIUM |
| **Security** | SSH, updates, hardening | MEDIUM |
| **Containers** | Docker, Podman, image cleanup | MEDIUM |
| **Hardware** | Sensors, fans, GPU | MEDIUM |

---

## Competitive Analysis

**Existing Linux Tools**:

| Tool | What It Does | Gap |
|------|--------------|-----|
| **htop/top** | Process monitoring | No explanations, expert-only |
| **System Monitor** | Basic GUI | No intelligence, just data |
| **Cockpit** | Server management | Server-focused, no AI |
| **Stacer** | System optimizer | Generic, no root cause analysis |

**The Gap**: No tool currently:
1. Explains WHY something is happening (not just WHAT)
2. Traces root causes (disk full → service failed)
3. Predicts issues (disk will fill in 12 days)
4. Automates common fixes safely
5. Learns from past issues

This gap defined Cerebric's value proposition.

---

## Design Decisions Informed by Research

### Self-Identification

Research showed users naturally ask "how are you doing?" or "what's wrong?"—not "what is the system's CPU usage?" The self-identifying LLM pattern emerged from this natural interaction style.

### Grounded Responses

Users are tired of generic advice. Research showed they want:
- Specific to THEIR system (not generic best practices)
- Aware of THEIR history (what changed recently)
- Actionable (not just "check the logs")

This drove the RAG architecture—every response is grounded in actual system data.

### Safety Guardrails

Research uncovered dangerous patterns:
- Killing package managers mid-update
- Running random StackOverflow commands with sudo
- Applying advice meant for different distros

This drove the approval workflow, dry-run defaults, and rollback capability.

### Minimal Interruption

Users complained about noisy monitoring tools. Research showed they want:
- Alerts only when something is actionable
- Batched notifications (not one per log line)
- Context (why this matters NOW)

This informed the anomaly detection threshold design.

---

## Validation Sources

| Source | Insights |
|--------|----------|
| StackOverflow | 500+ systemd questions analyzed |
| Reddit /r/linux | 200+ posts on disk/performance issues |
| Reddit /r/sysadmin | 150+ posts on backup/recovery |
| Level1Techs forums | 100+ posts on desktop Linux issues |
| AskUbuntu | 300+ questions on package management |

---

## Summary

The research validated three core insights:

1. **Linux system administration is unnecessarily hard** — not because the systems are complex, but because the feedback is cryptic and scattered

2. **An AI that understands YOUR system specifically** is more valuable than generic knowledge bases

3. **Safety and reversibility** are critical — users make dangerous mistakes when panicking

These insights directly shaped Cerebric's architecture: self-identifying LLM, grounded responses via RAG, and layered safety controls.
