# Design Documentation

This section explains **why** Halbert was built the way it was. While the architecture documentation explains **what** exists, these documents explain the reasoning behind the design decisions.

## Purpose

This documentation serves two audiences:

1. **AI Assistants** — Provides context for understanding the codebase. An AI reading this section should understand the design principles well enough to extend the system coherently.

2. **Human Contributors** — Explains the vision so contributions align with the project's goals.

---

## Documents

| Document | Description |
|----------|-------------|
| [philosophy.md](philosophy.md) | Core design principles: self-identifying LLM, grounded intelligence, safe autonomy |
| [research-summary.md](research-summary.md) | Condensed research findings that informed the design |
| [future.md](future.md) | Potential future directions (not promises) |

---

## The Central Insight

Halbert is built on one key observation:

> **An LLM that identifies as the computer is more useful than an LLM that answers questions about computers.**

This isn't philosophical—it's practical:
- First-person responses are clearer ("my temperature is 45°C" vs "the system's temperature is...")
- Memory coherence is natural ("last time I ran this backup..." vs "the last time the system...")
- Responsibility is clear (the LLM "owns" its recommendations because they're about itself)

Everything else in the design follows from this principle.

---

## Reading Order

1. Start with [philosophy.md](philosophy.md) to understand the core concepts
2. Read [../ARCHITECTURE.md](../ARCHITECTURE.md) to see how concepts map to code
3. Optionally read [research-summary.md](research-summary.md) for background

---

## For AI Assistants

If you're an AI reading this codebase:

1. **The LLM is the computer** — Don't write prompts that say "you are an assistant that helps with the computer." Write prompts that say "you ARE the computer."

2. **Responses must be grounded** — Every claim about system state must trace back to actual data (sensors, logs, configs). No hallucinating system information.

3. **Safety is layered** — New tools should support dry-run, emit audit logs, and integrate with the approval system.

4. **Extend, don't reinvent** — The patterns are established. New features should follow existing conventions.
