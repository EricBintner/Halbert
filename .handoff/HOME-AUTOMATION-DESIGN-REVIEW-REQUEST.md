# Home Automation Design — Review Request

**Date:** 2026-08-27
**From:** Design exploration session
**To:** Review AI
**Status:** Awaiting design review and feedback

---

## Context

We're designing a home automation variant of Halbert — an AI sysadmin agent with a cognitive core (Haloysius). Halbert currently manages computers. The home variant would manage **the house** via Home Assistant, with cognition, memory, and personality.

This is still **design exploration and technical research**, not final implementation. Phase 1 implementation has begun in a worktree (`feat/home-automation`), but the broader architecture needs review before we go further.

**Two documents to review:**

1. **Design doc:** `/Volumes/4TB-BAD/Halbert/.handoff/HOME-AUTOMATION-DESIGN-2026-08-27.md` (821 lines)
   - Sections 1-11: Multi-instance architecture, deployment patterns, minimum requirements, light variant concept
   - Section 12: Frigate + voice assistant integration analysis, competitive landscape, unique value proposition
   - Section 13: Integration architecture research (HA custom integration, WebSocket API, conversation agent registration, LLM tool platform, power user hardware)
   - Section 14: 8-phase roadmap (Phase 1 through Phase 8)
   - Section 15: SourcePrep for home automation analysis
   - Section 16: Revised open questions (16 items)

2. **Implementation handoff:** `/Volumes/4TB-BAD/Halbert/.handoff/HOME-AUTOMATION-HANDOFF-2026-08-27.md` (340 lines)
   - Phase 1 file manifest, architecture constraints, testing plan
   - 12 points for the implementing AI session

---

## What We Need Reviewed

### 1. Architecture Soundness

The core architectural decision is **Path C (hybrid)**: Halbert runs as a standalone daemon (keeping its FastAPI dashboard, Haloysius cognition, Ollama integration), plus a thin HA custom integration (~200 lines) that bridges HA's voice pipeline and Assist API to the daemon.

- Is this the right call vs. running inside HA's process (Path B)?
- Are there hidden coupling risks we're not seeing?
- The daemon talks to HA via REST (Phase 1) + WebSocket (Phase 2). The HA integration talks to the daemon via HTTP. Is this transport stack sound?

### 2. Roadmap Sequencing

The 8-phase roadmap is:

| Phase | Goal |
|-------|------|
| 1 (current) | Home panel + HA REST client |
| 2 | HA WebSocket events → cognition |
| 3 | HA custom integration (HACS bridge) |
| 4 | Voice (Wyoming agent) |
| 5 | Frigate integration |
| 6 | SourcePrep for HA configs |
| 7 | Multi-instance (if needed) |
| 8 | Light variant packaging |

- Is this the right order? Should any phases be merged or reordered?
- Phase 3 (HACS bridge) before Phase 4 (voice) — does that make sense, or should voice come first to validate the conversation flow?
- Phase 6 (SourcePrep) is positioned late. Should it come earlier since it's "just a config change" and adds immediate value?

### 3. Multi-Instance Strategy

The design doc identifies single-instance blockers in `cognition_wiring.py` (module-level singletons, hardcoded `persona_id="halbert"`). The current plan is:
- Phase 7 addresses multi-instance **only if needed**
- Pragmatic approach: run two daemon processes on different ports with different config dirs
- No `InstanceManager` refactoring unless there's a real concurrency requirement

The user has annotated the handoff doc with "(unlikely)" next to the multi-instance spawning system. Is the two-process approach sufficient indefinitely, or are there scenarios where it breaks down?

### 4. SourcePrep Integration

The claim is that SourcePrep for HA configs requires **no Halbert refactoring** — just register a new project and wire `SourcePrepRetrievalBackend` with a different `project_id`. The backend already accepts `project_id` and `base_url` params.

- Is this accurate? Read `halbert_core/halbert_core/integrations/app_seam.py` and `halbert_core/halbert_core/integrations/sourceprep_retrieval_backend.py` to verify.
- Can one Halbert instance use two SourcePrep projects simultaneously (e.g., host-config + ha-config)? Or does the `SourcePrepRetrievalBackend` only support one project at a time?

### 5. Competitive Differentiation

Section 12.7 compares Halbert Home against 4 existing HA LLM integrations (`hass-agent-llm`, `ai-conversation`, `wyoming-letta`, `home_assistant_llm_claude`). The claim is that none have:
- Persistent episodic memory with emotional scoring and decay
- Inter-turn cognition (advance_turn)
- Proactive initiation
- Camera events as experiences
- Personality (archetypes, Big Five)
- Self-model (3-layer)

- Is this comparison accurate based on what these projects actually do?
- Is "cognition, not chat" the right framing for the moat?
- Are there other competitors we're missing?

### 6. Hardware/Resource Assumptions

The design assumes an N150 mini PC (16GB RAM, 6W idle) running Proxmox with HA in a VM, Ollama in another VM/LXC, and Halbert as a third service. Total budget ~9-10GB RAM with a 7B model, ~6.5GB with 3B.

- Are these numbers realistic?
- Is sentence-transformers (required for PersonaMemoryStore) a problem on low-power hardware?
- Should we consider remote embedding models to reduce local RAM?

### 7. Phase 1 Scope

The implementation handoff scopes Phase 1 as:
- HA REST client (`ha_client.py`)
- HA config dataclass (`ha_config.py`)
- Dashboard API routes (`home.py`)
- Frontend Home panel (`Home.tsx`)
- 4 home archetypes (`home_archetypes.py`)
- No cognition, no voice, no Frigate

- Is this too much or too little for a first slice?
- Should the home archetypes be in Phase 1 or deferred to when personality selection is wired?
- Should we add a minimal HA tool (e.g., `call_service`) in Phase 1 so the chat can actually control something?

---

## How to Review

1. Read the design doc: `/Volumes/4TB-BAD/Halbert/.handoff/HOME-AUTOMATION-DESIGN-2026-08-27.md`
2. Read the implementation handoff: `/Volumes/4TB-BAD/Halbert/.handoff/HOME-AUTOMATION-HANDOFF-2026-08-27.md`
3. Read these source files for accuracy verification:
   - `halbert_core/halbert_core/integrations/app_seam.py` — AppSeam wiring, `wire_halbert_seam()` params
   - `halbert_core/halbert_core/integrations/sourceprep_retrieval_backend.py` — SourcePrep backend, project_id support
   - `halbert_core/halbert_core/integrations/cognition_wiring.py` — singleton blockers, persona_id hardcoding
   - `halbert_core/halbert_core/config/being_config.py` — BeingConfig shape (personality fields now merged)
   - `halbert_core/halbert_core/persona/archetypes.py` — existing archetype pattern to follow
   - `halbert_core/halbert_core/dashboard/app.py` — route registration pattern (line 265-292)
   - `halbert_core/halbert_core/dashboard/frontend/src/components/Layout.tsx` — navigation array (line 49-72)
   - `halbert_core/halbert_core/dashboard/frontend/src/App.tsx` — route definitions (line 91-104)
4. Write feedback to: `/Volumes/4TB-BAD/Halbert/.handoff/HOME-AUTOMATION-DESIGN-REVIEW-FEEDBACK.md`

---

## Feedback Format

For each of the 7 review areas above, provide:

1. **Assessment:** Sound / Needs work / Problematic
2. **Findings:** Specific issues, inaccuracies, or confirmations (cite file paths and line numbers where relevant)
3. **Recommendations:** Concrete changes if any
4. **Open questions:** Things that need a human decision

Be direct and critical. We want to catch architectural mistakes before Phase 1 code is written, not after.
