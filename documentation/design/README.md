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
| [macos-strategy.md](macos-strategy.md) | macOS tiering strategy (LemonSqueezy Pro vs. App Store Free), config physiology, and universal multi-session architecture |
| [research-summary.md](research-summary.md) | Condensed research findings that informed the design |
| [unified-model-picker.md](unified-model-picker.md) | Strategy for unifying Halbert and SourcePrep's model picker into a shared layer (superseded by independent design) |
| [model-picker-independent-2026-08-26.md](model-picker-independent-2026-08-26.md) | Approved independent model picker design: 3-slot schema, single store module, and trimmed UI |
| [UI-SPEC-REUSABLE-MODEL-PICKER-2026-08-26.md](UI-SPEC-REUSABLE-MODEL-PICKER-2026-08-26.md) | UI/UX specification: Reusable Local + BYOK model picker, dual-surface runtime controls, and /model command |
| [SCRUTINY-AND-REVERSE-ENGINEERING-MODEL-PICKER-2026-08-26.md](SCRUTINY-AND-REVERSE-ENGINEERING-MODEL-PICKER-2026-08-26.md) | Deep scrutiny & reverse-engineering audit: BYOK authentication gaps, runtime payload mismatches, and multi-turn memory |
| [TRIAGE-SCRUTINY-FEEDBACK-2026-08-26.md](TRIAGE-SCRUTINY-FEEDBACK-2026-08-26.md) | Triage response, user decisions, headless component architecture, and engineering handoff specifications |
| [continuous-conversation-and-watched-terminals-2026-08-26.md](continuous-conversation-and-watched-terminals-2026-08-26.md) | Architectural specification for continuous conversation memory, watched PTY terminals, and sub-threads |
| [future.md](future.md) | Potential future directions (not promises) |
| [DESIGN-SYSTEM-SPEC.md](DESIGN-SYSTEM-SPEC.md) | Formalized Design System Specification: Daylight tokens, typography, surfaces, motion, and accessibility |
| [COMPONENT-ARCHITECTURE.md](COMPONENT-ARCHITECTURE.md) | Component Catalog & Architecture: Atoms, Molecules, Organisms, and existing dashboard component migration |
| [USER-JOURNEY-METHODOLOGY.md](USER-JOURNEY-METHODOLOGY.md) | User-Journey Methodology: Attention economics, Four Whys matrix, and 5 end-to-end user workflows |
| [DOMAIN-MODULES-AND-WHY-MECHANICS.md](DOMAIN-MODULES-AND-WHY-MECHANICS.md) | Summonable Domain Modules & Four Whys Mechanics: Module lifecycle, Vitals, ConfigDiff, Storage, Evidence, and Approvals |
| [CORE-CONCEPTS-AND-ALIGNMENT-2026-09-02.md](CORE-CONCEPTS-AND-ALIGNMENT-2026-09-02.md) | **Start here for the current concept model:** reconciled identity/bodies/surfaces/mind/knowledge/trust, lexicon extensions, founding principles vs code, workflow verdicts, prioritised architecture fixes, planning corrections (2026-09-02) |
| [16-voice-mode-visual-ui-implementation-plan.md](16-voice-mode-visual-ui-implementation-plan.md) | Voice Mode visual UI implementation plan of record (task list, tiers, build status) |
| [the-being.md](the-being.md) | The vision for Halbert's next form — the conversation as core layer, the being concept, the two proof slices |
| [explorations.md](explorations.md) | Design-to-implementation catalog — every idea mapped to concrete code seams, with curation at section 10 |
| [REVIEW-DIRECTION-2026-08-23.md](REVIEW-DIRECTION-2026-08-23.md) | External review — overall direction and planning critique |
| [REVIEW-DESIGN-MECHANICS-2026-08-23.md](REVIEW-DESIGN-MECHANICS-2026-08-23.md) | External review — user flows and interaction mechanics design doc |
| [11-response-modality-handoff.md](11-response-modality-handoff.md) | Response Modality Handoff: Chat, voice, watched terminals, and visual handoff interaction architecture |
| [12-scrutiny-and-reverse-engineering-modality-handoff.md](12-scrutiny-and-reverse-engineering-modality-handoff.md) | Deep Scrutiny & Reverse-Engineering Audit: Identifying 6 critical DSP, concurrency, and session landmines in modality handoff |
| [13-adversarial-review-modality-handoff.md](13-adversarial-review-modality-handoff.md) | Theoretical Foundations & Blue-Sky Review: How humans truly want to engage with an embodied computer/home voice assistant |
| [14-system-prompts-and-modality-gap-analysis.md](14-system-prompts-and-modality-gap-analysis.md) | Embodied System Prompts & Codebase Gap Analysis: Modality-aware prompt engineering, <speech> demuxing, and file-by-file implementation gaps |
| [15-voice-mode-visual-ui-and-touchscreen-spec.md](15-voice-mode-visual-ui-and-touchscreen-spec.md) | Voice Mode Visual UI & Touchscreen Architecture: Audio-reactive Halbert Mark SVG vibration mechanics, N150 appliance power management, and touch interactions |

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
