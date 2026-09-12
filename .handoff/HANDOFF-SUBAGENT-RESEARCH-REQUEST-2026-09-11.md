# HANDOFF: Subagent architecture research request

**Date**: 2026-09-11
**Status**: Research requested. Not started. Parked from Phase 4 finalization.
**Origin**: Founder ruling during Phase 4 (detached-spawn split) review. Founder wants a Claude-Code-style subagent layer; confirmed it is out of scope for Phase 4 and should be researched separately.

---

## What was decided (Phase 4 context)

- **§3.1 detached-spawn split — CONFIRMED.** `background=true` spawns a detached subprocess (open-claude-code `runBackground` style), not a PTY pool entry. The turn returns immediately. Event vocabulary and frontend rendering stay single. This is a narrow spawn-mechanism fix, now approved.
- **Subagents — PARKED.** A CC-style subagent layer (independent agent loops with own context/tools/turn cycle for delegated subtasks) is a different, larger capability than detached spawn. It is not in the Phase 4 plan. The founder wants it researched.

## Why these are different (so the research doesn't conflate them)

| | Detached spawn (Phase 4, approved) | Subagents (this request) |
|---|---|---|
| Layer | Process | Agent loop |
| Problem | "Run my dev server without blocking the turn" | "Delegate this subtask to a separate reasoning loop that works autonomously" |
| OSS twin | open-claude-code `runBackground` (`bash.mjs:119-146`) | open-claude-code `Task` tool / agent-spawn |
| Reuse | A subagent layer *may* reuse the detached-spawn helper to run its own long-running commands, but the two are independently buildable | |

## What the research should answer

1. **OSS landscape.** How do the reference implementations do subagents?
   - open-claude-code: the `Task` tool / agent-spawn mechanism — read the actual source at `/Volumes/Thunderbolt/AI/OSS/open-claude-code/`. What is the spawn contract, the context isolation model, the tool-admission model, the result-handoff shape?
   - openclaw and hermes-agent: do they have a subagent concept? If so, what shape? (The OSS pass-2 discovery backlog TT workstream — "Terminal, tools, subagents", 96 items, packets TT-01–06 — is the relevant section; see `.handoff/oss-pass-2/section_terminal_tools_subagents.md` if it exists.)
   - warp: does the Rust TUI have any agent-delegation concept?

2. **What Halbert already has that a subagent layer would build on.**
   - The tiered model hierarchy (the founder named this as relevant infrastructure — a sub-agent could run on a cheaper model tier). Locate the tier system and document how a sub-agent would select its tier.
   - The agent pool / turn loop (`agent_pool.py`). Can a sub-agent be a second entry in the pool, or does it need a separate loop?
   - The tool-admission / permission lattice (`capabilities.py:499` `has_capability`). A sub-agent likely needs a *narrower* tool set than the parent — how does the lattice express per-agent scoping?
   - The conversation/session store. Does a sub-agent get its own session, or a thread within the parent's? (Relevant to the memory-boundary decisions, some of which are deferred for Fable.)

3. **The design questions that need founder rulings before building.**
   - **Context isolation**: does a sub-agent see the parent's full turn history, a curated summary, or a clean slate with only the delegated task? (This intersects the memory-boundary work — decisions 1, 2, 4 are deferred for Fable; decision 3 approved. A sub-agent context policy may need to wait on those.)
   - **Tool admission**: can the parent grant the sub-agent tools it itself lacks? Or is the sub-agent's tool set always a subset?
   - **Result handoff**: does the sub-agent's output become a tool result in the parent's turn (CC-style: the sub-agent runs, returns a final message, the parent treats it as a `Task` tool result), or does it stream into the parent's conversation?
   - **Lifecycle**: can a sub-agent be stopped/steered mid-turn? (The remediation work on turn-lock bounding, stop/steer verbs — R-01, on `fix/remediation-opus-batch-2` — is relevant here.)
   - **Nesting**: can a sub-agent spawn its own sub-agents? What is the depth limit?
   - **Cost/telemetry**: a sub-agent running on a cheaper tier still costs money. How is it metered? (The meter design docs on `fix/remediation-opus-batch-2` are relevant.)

4. **Relationship to the discovery backlog.** The OSS pass-2 discovery backlog has a "Terminal, tools, subagents" workstream (TT-01–06, 96 items). The research should cross-reference: which TT packets overlap with a subagent layer, which are independent, and whether the subagent layer should absorb or precede them.

5. **Relationship to the unmerged remediation branches.** `fix/remediation-opus-batch-2` carries turn-loop wiring, the yield primitive (A07-G8 — a command can be *let go of*, not killed), and branch-continuity work. A subagent layer would interact with all three. The research should note dependencies but should not block on the merge.

## Constraints the research must respect (from AGENTS.md)

- Never name or recommend an AI model on a user-facing surface. A sub-agent's tier is selected by capability/price, not surfaced as a model name.
- The system speaks as the computer itself, in first person. A sub-agent is still the computer, not an "assistant."
- Commands staged from the UI are staged, never executed.
- No users yet — do not build migrations or back-compat shims.
- Haloysius subtractive contract: exactly two hard dependencies (`pyyaml`, `requests`). A subagent layer must not add a third hard dependency.
- Feature gating through `has_capability()` (`capabilities.py:499`), not variant flags.
- One place each thing is decided: a subagent layer must route through the existing choke points (model locality, capability gating, redaction, colour, licence notices), not duplicate them.

## Deliverable

A design research document (in `.handoff/`) that:
1. Maps the OSS reference implementations concretely (file:line citations, like the Phase 4 plan's §7 table).
2. Proposes a subagent architecture for Halbert, grounded in what already exists (agent pool, tier hierarchy, capability lattice, session store).
3. Lists the founder decisions required before building, with the tradeoffs framed clearly.
4. Cross-references the TT discovery packets and the unmerged remediation work.
5. Does NOT prescribe a build order — that's a follow-up once the design is ruled.

## What this is NOT

- Not a Phase 4 deliverable. Phase 4 is the detached-spawn split + `task_started` + scheme-less port chip, all now confirmed/finalized.
- Not a commitment to build. The founder wants the research; the build decision comes after.
- Not blocked on the memory-boundary rulings (Fable, Q1/Q3), but the research should flag where it *intersects* them so a future build doesn't collide.
