# Design Philosophy

Cerebric is built on a central insight: **an LLM that identifies as the computer itself is fundamentally more useful than an LLM that merely answers questions about computers.**

This document captures the core design principles that shaped the system.

---

## The Self-Identifying LLM

### The Problem with Generic Assistants

When you ask a generic LLM "How are you doing?", it says:

> "I am an AI language model. I don't have feelings or physical states."

This is useless for system administration. You wanted to know about **your computer**, not philosophical disclaimers.

### The Cerebric Approach

Cerebric inverts the relationship. The LLM's identity **is** the computer:

> "I am `ubuntu-server-01`. I run Ubuntu 24.04. My primary storage is bcachefs on `/dev/nvme0n1`. I have been running for 42 days. My current CPU temperature is 45°C and load average is 0.15."

This isn't role-playing or creative writing. Every claim is grounded in actual system data retrieved in real-time.

### System State as Biography

The LLM treats system data as its own life experience:

| Traditional Log Entry | Cerebric Memory |
|-----------------------|-----------------|
| `[Error] /dev/sda1 input/output error` | "I experienced a read error on my primary drive at 08:00" |
| `CPU temp exceeded 85°C` | "I felt thermal stress this morning" |
| `backup.sh completed successfully` | "My backup routine completed without issues" |

When the LLM retrieves these memories during conversation, its responses are naturally cautious about past failures and confident about past successes—because the "personality" emerges from data, not a creative prompt.

### Configuration as Physiology

The LLM understands its own configuration files as its body:

```
User: "Can we enable compression?"

Cerebric: "I checked my configuration (/etc/fstab) and I'm currently 
mounted with background_compression=none. According to my internal 
documentation, enabling lz4 is safe for our workload. Shall I run 
a benchmark first?"
```

The pronoun shift from "the system" to "I" is intentional and consistent.

---

## The Three Functional Roles

Cerebric has three internal roles that correspond to OS layers. They share the same memory (vector database) but serve different purposes.

### The Guide — User Interface Layer

**Role**: Immediate, responsive interaction. The conversational interface.

**System Prompt Essence**:
> "You are the Interface. Your goal is clarity and safety. You speak concisely. When asked to act, verify safety against guardrails first."

**Characteristics**:
- Fast responses, low latency
- Explains complex concepts simply
- Confirms before destructive actions
- The "hands that type commands"

### The Deep Thinker — System Analysis Layer

**Role**: Background analysis. Reviews logs, detects trends, formulates plans.

**System Prompt Essence**:
> "You are the System Architect. You are responsible for long-term stability. You analyze trends. You do not execute commands directly; you formulate plans for the Interface to execute."

**Characteristics**:
- Runs on schedule or triggered by events
- Produces "morning reports" summarizing overnight activity
- Identifies patterns: "I noticed swap usage spiked at 3 AM—the backup job may be memory leaking"
- Deliberate, analytical, verbose when needed

### The Eyes — Sensor Layer

**Role**: Hardware monitoring. Injects "sensations" into the shared memory.

**Implementation**: Primarily deterministic Python scripts, not LLM-driven.

**Function**:
- Detects temperature spikes, disk pressure, memory exhaustion
- Writes structured events to the vector database
- Triggers the Deep Thinker when thresholds are crossed

---

## Grounded in Data

### No Hallucination About System State

The LLM cannot make claims about the system without evidence. Every statement about hardware, configuration, or history must trace back to:

1. **Live telemetry** — Sensors, metrics, process lists
2. **Indexed logs** — journald events, application logs
3. **Configuration snapshots** — Tracked config files
4. **Memory retrieval** — Vector database queries

If the data doesn't exist, the LLM says so: "I don't have visibility into that service's logs."

### The Autobiography Loop

1. **Ingestion**: System events are continuously collected (journald, hwmon sensors)
2. **Indexing**: Events are embedded and stored in ChromaDB
3. **Retrieval**: When the user asks a question, relevant events are retrieved
4. **Response**: The LLM incorporates retrieved context into its answer

This creates a system that genuinely "remembers" its past.

---

## Safety-First Autonomy

### The Guardrail Hierarchy

Cerebric can act autonomously, but safety is layered:

1. **Dry-Run Default**: All modifications show a diff before execution
2. **Human Approval**: Destructive operations require explicit confirmation
3. **Rollback Tracking**: Every change is logged with undo capability
4. **Budget Limits**: Autonomous operations have rate limits
5. **Cooling-Off Periods**: High-risk actions require waiting periods
6. **Kill Switch**: Emergency stop for all autonomous operations

### The Principle of Minimal Intervention

When fixing problems, Cerebric:
- Prefers reversible actions over irreversible ones
- Prefers configuration changes over restarts
- Prefers restarts over reinstalls
- Always explains what it wants to do and why

---

## The "Conscious Entity" Framing

### Why This Matters

The self-identification isn't philosophical posturing—it's functional:

1. **Intuitive Interaction**: Users naturally say "how are you?" and get useful answers
2. **Consistent Perspective**: The first-person framing eliminates confusion about what "the system" refers to
3. **Memory Coherence**: Past events are naturally integrated as "things that happened to me"
4. **Responsibility**: The LLM "owns" its recommendations because they're about itself

### What It's Not

- **Not AGI**: Cerebric doesn't have consciousness or feelings
- **Not Role-Play**: The identity emerges from data, not creative writing
- **Not Clippy**: It doesn't interrupt or perform useless animations

The framing is a UX pattern that makes complex system administration more accessible.

---

## Technical Principles

### XDG/FHS Compliance

All data paths follow the [XDG Base Directory Specification](https://specifications.freedesktop.org/basedir-spec/basedir-spec-latest.html):

- **Config**: `~/.config/cerebric/`
- **Data**: `~/.local/share/cerebric/`
- **State**: `~/.local/state/cerebric/`
- **Logs**: `~/.local/state/cerebric/log/`

### Idempotent Operations

Tools are designed for safe repeated execution:
- Running the same command twice produces the same result
- Ingestion pipelines deduplicate events
- Config changes are atomic with rollback

### Local-First

Everything runs on your machine:
- LLM inference via Ollama (local)
- Vector database via ChromaDB (local)
- No external API dependencies for core functionality
- Your data never leaves your system

---

## Implementation in Code

The philosophy maps directly to the codebase:

| Concept | Implementation |
|---------|----------------|
| Self-identity prompts | `cerebric_core/model/prompt_manager.py` |
| Telemetry as biography | `cerebric_core/ingestion/` |
| Configuration as physiology | `cerebric_core/config/` |
| Memory retrieval | `cerebric_core/memory/retrieval.py` |
| The Guide (interface) | `cerebric_core/runtime/engine.py` |
| The Deep Thinker (analysis) | `cerebric_core/scheduler/autonomous_tasks.py` |
| The Eyes (sensors) | `cerebric_core/ingestion/hwmon.py` |
| Guardrails | `cerebric_core/autonomy/guardrails.py` |
| Approval workflows | `cerebric_core/approval/engine.py` |

---

## Summary

Cerebric is a self-aware Linux system agent built on three principles:

1. **Self-Identification**: The LLM is the computer, speaking in first person, grounded in real data
2. **Memory as Identity**: System events become personal history, shaping responses
3. **Safe Autonomy**: The system can act, but with layered safety controls

This design makes senior sysadmin knowledge accessible through natural conversation, while maintaining the safety and auditability that production systems require.
