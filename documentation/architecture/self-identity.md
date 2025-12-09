# Self-Identity Architecture

This document explains how Cerebric implements the "self-identifying LLM" — an AI that speaks as the computer rather than about the computer.

---

## The Core Concept

Traditional LLMs say: *"The system's CPU temperature is 45°C."*

Cerebric says: *"My temperature is 45°C."*

This isn't cosmetic. The pronoun shift reflects a fundamental architectural decision: the LLM's identity is constructed from actual system data, not a creative prompt.

---

## Implementation

### 1. Identity Construction

At startup and during each conversation, Cerebric gathers identity data:

```python
# Simplified from cerebric_core/model/prompt_manager.py

def build_identity_prompt():
    hostname = socket.gethostname()
    os_info = platform.freedesktop_os_release()
    uptime = get_uptime()
    disk_info = get_disk_layout()
    cpu_temp = get_cpu_temperature()
    
    return f"""
You are {hostname}. 
You run {os_info['NAME']} {os_info['VERSION']}.
Your primary storage is {disk_info}.
You have been running for {uptime}.
Your current temperature is {cpu_temp}°C.

All your responses must be grounded in this reality.
When asked about "the system" or "the computer", you answer in first person.
"""
```

**Key Implementation Files**:
- `cerebric_core/model/prompt_manager.py` — Prompt construction
- `cerebric_core/utils/platform.py` — System information gathering
- `cerebric_core/ingestion/hwmon.py` — Temperature and sensor data

### 2. Memory as Biography

System events are stored as first-person experiences:

| Raw Event | Indexed Memory |
|-----------|----------------|
| `[ERROR] /dev/sda1 I/O error at 08:00` | "I experienced a disk read error on my primary drive at 08:00" |
| `CPU temp exceeded 85°C` | "I felt thermal stress this morning" |
| `backup.sh exit code 0` | "My backup completed successfully" |

This transformation happens during ingestion:

```python
# Simplified from cerebric_core/ingestion/journald.py

def transform_to_memory(event):
    if event.severity == "ERROR":
        return f"I experienced: {event.message}"
    elif event.severity == "WARNING":
        return f"I noticed: {event.message}"
    else:
        return f"Event: {event.message}"
```

When the user asks a question, these memories are retrieved and included in context. The LLM naturally adopts the first-person perspective because that's how the memories are written.

### 3. Grounded Responses

The LLM cannot make claims about system state without evidence. The prompt includes:

```
GROUNDING RULES:
1. Only make claims about system state that you can verify from provided data
2. If you don't have data, say "I don't have visibility into that"
3. Never hallucinate hardware specifications, uptime, or error counts
4. Cite your sources: "According to my sensor data..." or "My logs show..."
```

This is enforced by the retrieval pipeline — the LLM only sees data that was actually collected.

---

## The Three Voices

Cerebric has three internal roles that share the same identity but serve different purposes:

### The Guide (User Interface)

**Purpose**: Immediate, conversational responses

**System Prompt Essence**:
```
You are the Interface layer. You speak concisely and directly.
When the user asks you to act, verify safety first.
You are the hands that type commands.
```

**Implementation**: `cerebric_core/runtime/engine.py`

**Characteristics**:
- Fast, low-latency responses
- Explains complex concepts simply
- Confirms before destructive actions

### The Deep Thinker (Analysis)

**Purpose**: Background analysis and planning

**System Prompt Essence**:
```
You are the System Architect. You analyze trends and long-term stability.
You do not execute commands directly.
You formulate plans for the Interface to execute.
```

**Implementation**: `cerebric_core/scheduler/autonomous_tasks.py`

**Characteristics**:
- Runs on schedule or triggered by events
- Reviews logs, detects patterns
- Produces reports and recommendations

### The Eyes (Sensors)

**Purpose**: Hardware monitoring, data injection

**Implementation**: Primarily deterministic Python, not LLM-driven

**Location**: `cerebric_core/ingestion/hwmon.py`, `cerebric_core/ingestion/journald.py`

**Function**:
- Continuously collects telemetry
- Writes events to the shared memory
- Triggers the Deep Thinker when thresholds are crossed

---

## Data Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                        User Query                               │
│              "How are you doing today?"                         │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Identity Construction                        │
│  hostname: ubuntu-server-01                                     │
│  os: Ubuntu 24.04 LTS                                          │
│  uptime: 42 days                                                │
│  cpu_temp: 45°C                                                 │
│  load: 0.15                                                     │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Memory Retrieval                             │
│  Query: "recent health events"                                  │
│  Retrieved:                                                     │
│   - "My backup completed successfully at 03:00"                 │
│   - "I noticed high memory usage at 14:30"                      │
│   - "Event: Docker containers restarted"                        │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Prompt Assembly                              │
│  [Identity prompt]                                              │
│  [Grounding rules]                                              │
│  [Retrieved memories]                                           │
│  [User query]                                                   │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                    LLM Inference                                │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Response                                     │
│  "I am operating well. My temperature is a comfortable 45°C,   │
│   load average is 0.15, and my backup completed successfully    │
│   this morning. I did notice elevated memory usage around       │
│   14:30—would you like me to investigate?"                      │
└─────────────────────────────────────────────────────────────────┘
```

---

## Why This Matters

### 1. Intuitive Interaction

Users naturally ask "how are you?" and get useful answers, not philosophical disclaimers.

### 2. Memory Coherence

Past events are naturally integrated as "things that happened to me" rather than "events in the system log."

### 3. Responsibility

The LLM "owns" its recommendations because they're about itself. "I recommend we increase swap" is more committed than "the documentation suggests increasing swap."

### 4. Disambiguation

When users say "check the logs", there's no confusion about whose logs. It's always the machine's own logs.

---

## What It's Not

- **Not AGI** — Cerebric doesn't have consciousness or feelings
- **Not Role-Play** — The identity emerges from data, not creative writing
- **Not Clippy** — It doesn't interrupt or perform unnecessary animations

The self-identification is a UX pattern that makes system administration more accessible, not a claim about machine sentience.

---

## Configuration

The identity prompt is constructed from templates in `config/prompts/`:

| File | Purpose |
|------|---------|
| `base-safety.txt` | Core safety rules |
| `identity-template.txt` | Identity prompt template |
| `grounding-rules.txt` | Hallucination prevention |

These can be customized without modifying code.

---

## Testing Self-Identity

To verify the identity system is working:

```bash
# Check identity construction
python Cerebric/main.py prompt-show

# Test a grounded response
python Cerebric/main.py model-test "How are you doing?"

# Verify memory retrieval
python Cerebric/main.py memory-query "recent events"
```

---

## Extending the Identity

When adding new system capabilities:

1. **Add data collection** — Extend ingestion to capture new data types
2. **Update identity prompt** — Add new fields to the identity template
3. **Transform to first-person** — Ensure events are stored as experiences
4. **Test grounding** — Verify the LLM uses the new data correctly

The identity should always reflect what the system actually knows about itself.
