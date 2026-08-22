# Final Plan — Halbert Realignment

**Created:** 2026-08-22
**Status:** Ready for execution
**Supersedes:** `CONSOLIDATED-NEXT-STEPS-2026-08-22.md`, `RECOMMENDED-NEXT-STEPS-2026-08-22.md`, `NEXT-STEPS-2026-08-22.md`

---

## 0. What's done

| Item | Status | Evidence |
|------|--------|----------|
| **Phase 0: Founder confirmations** | DONE | Halbert confirmed as sysadmin consumer; Haloysius at `/Volumes/4TB-BAD/Haloysius` |
| **Phase 1: Dead-code cut** | DONE (branch `phase1-cleanup`) | `.gitignore` fixed, frontend lib reconstructed, langgraph/platform/old-RAG cut, chat stream uses ChromaDB |
| **RQ-A: Seam shape** | RESEARCHED + SCRUTINIZED | WRAP SourcePrep behind existing `RetrievalBackend`. Use HTTP API, not MCP. Adapter draft in `DEEP-RESEARCH-QUESTIONS-2026-08-22.md` §A7 |
| **RQ-B: System-state predicates** | RESEARCHED + SCRUTINIZED | Consumer-side, zero core changes. Predicate schema drafted. Medium tier (default) renders all subjects |
| **RQ-C: System-event triggers** | RESEARCHED + SCRUTINIZED | Consumer-side `SystemEventMapper` populates `PersonaCognition` before tick. Background scan thread required for MVP |
| **RQ-D: chat.py audit** | RESEARCHED + SCRUTINIZED | 3 context-injection systems identified (chat.py, ContextAssembler, ContextInjector). Corrected port/discard table in `RQ-D-SCRUTINY-2026-08-22.md` |
| **RQ-E: Self-model architecture** | RESEARCHED + SCRUTINIZED | 3-layer composition (SourcePrep objective + Haloysius subjective + Halbert glue). Biography loop specified |
| **Haloysius framework generalization** | DONE (commit `d0781ab`) | StateTracker protocol, clothing/location adapters, continuity tracker registry, extensible predicate rendering with prose templates, `default_identity` parameter, `_render_natural` fixed for non-standard subjects |
| **Haloysius Python 3.10 downgrade** | DONE (commit `46f0d20`) | `pyproject.toml` lowered from `>=3.11` to `>=3.10` |
| **Haloysius generalized stat tracking** | DONE (commit `d0781ab`) | `StateTracker` protocol + `InternalStateCategory` enum + `register_state_tracker()`/`clear_state_trackers()` + `register_predicate()`/`register_subject_label()` |

---

## 1. What remains for Haloysius

**One item:** The thought generation fix in `advance_turn()`. See handoff doc:
`/Volumes/4TB-BAD/Halbert/.handoff/HALOYSIUS-THOUGHT-GEN-FIX-2026-08-22.md`

**Summary:** `advance_turn()` calls `thought_generator.generate(trigger_context)` but does not pass the cognitive state (worries, emotions, drives). The generator falls back to generic templates ("I can't stop thinking about it...") instead of system-specific content ("I need to check on /dev/sda1 — those SMART warnings could mean my primary drive is dying"). Fix: 4 lines in `advance_turn()` to pass `cognition` to the generator. This benefits all consumers, not just Halbert.

**Decision needed from founder:** Approve the 4-line core fix (Option A, recommended) or use a Halbert-side `ThoughtGenerator` subclass (Option B, avoids touching Haloysius).

---

## 2. Founder decisions needed

| ID | Decision | When needed | Recommendation |
|----|----------|-------------|----------------|
| **D-A** | Thought generation fix: 4-line core change (Option A) vs Halbert subclass (Option B) | Before Phase D3 | **Option A** — core fix benefits all consumers, 4 lines, backward-compatible |
| **D-B** | Full vs subtractive Haloysius install | Before Phase D2 | **Full install** for MVP; subtractive after WP-12 moves `memory_v2` to core |
| **D-C** | Ledger `db_path` isolation | Before Phase D2 | **Separate `db_path`** for Halbert's ledger (avoids persona_id collision) |
| **D-D** | Canonical context system | Before Phase C2 | **State machine internal assembler** (research recommendation); port ContextInjector logic into it |
| **D-E** | RQ4 MVP config capability | Before Phase E2 | **"Explain why a setting is set"** — leverages SourcePrep concepts directly, lowest risk |
| **D-F** | User-facing terminal in dashboard | Phase 1 cleanup | **Leave as-is** for now; removing it is scope creep |
| **D-G** | SourcePrep OS project questions (CoDRAG handoff §4) | Before Phase B1 | **Custom globs + Halbert-triggered re-indexing** for MVP; defer chunking/secrets/extensionless questions |

---

## 3. Next-steps recommendations by RQ

### RQ-A: Seam shape — WRAP

**Verdict:** Wrap `prep_search` behind the existing `RetrievalBackend` protocol. Do not extend the protocol.

**Next steps:**
1. Build `halbert_core/integrations/sourceprep_client.py` — sync HTTP client wrapping SourcePrep daemon API (`POST /projects/{id}/context` with `structured=true`)
2. Build `halbert_core/context/sourceprep_retrieval.py` — the corrected adapter from RQ-A audit §A7 (uses HTTP API, not MCP; renders from structured chunks, not stashed markdown)
3. Register the adapter via `register_app_seam()` at startup (Phase D1)
4. Route `prep_impact` directly (Halbert-internal, not via `GovernancePolicy` — that's content safety, not config safety)
5. Route `prep_observe` to `memory_store_add`/`memory_store_search` callbacks (already accepted by `advance_turn`)

**Key corrections from audit:**
- Must use HTTP API (`POST /projects/{id}/context`), NOT MCP tool (MCP drops `chunks` list)
- `prep_impact` is NOT `GovernancePolicy` — it's Halbert-internal
- Halbert has NO SourcePrep client today — the adapter references a nonexistent module
- The `_to_markdown` stashing trick is unsound — render from chunks directly

---

### RQ-B: System-state predicates — CONSUMER-SIDE

**Verdict:** Consumer-side, zero core changes for storage and rendering. The framework generalization (done in Haloysius) added the registration mechanism.

**Next steps:**
1. At Halbert startup, call `clear_state_trackers()` to remove clothing/location defaults
2. Register Halbert's trackers: `SystemHealthTracker`, `ServiceStatusTracker`, `ThermalStateTracker`, `ConfigStateTracker`
3. Register predicates with prose templates:
   - `register_predicate("disk_health", label="Disk Health", prose_template="My disk health is {object}")`
   - `register_predicate("service_status", label="Service Status", prose_template="Service {subject} is {object}")`
   - `register_predicate("thermal_state", label="Thermal State", prose_template="My thermal state is {object}")`
   - `register_predicate("config_state", label="Config State", prose_template="My config state is {object}")`
   - `register_predicate("config_drift", label="Config Drift", prose_template="I detect config drift: {object}")`
4. Use `render_state_block("halbert", tier="medium")` in prompt assembly (medium is default, renders all subjects)
5. Use a separate `db_path` for the ledger (avoid persona_id collision with Haloysius personas)
6. Do NOT call `continuity.advance_from_user_message()` or `advance_from_response()` — system state advances from monitors, not chat

**Predicate schema (from RQ-B §6):**

| Subject | Predicate | Source module |
|---------|-----------|---------------|
| `self` | `disk_health` | `discovery/scanners/storage.py` |
| `self` | `thermal_state` | `discovery/scanners/thermal.py` |
| `self` | `power_state` | `discovery/scanners/laptop.py` |
| `self` | `load_state` | `discovery/scanners/process.py` |
| `service:{name}` | `service_status` | `discovery/scanners/service.py` |
| `config` | `config_state` | `config/snapshot.py` |
| `config` | `config_drift` | `config/drift.py` |
| `network` | `network_state` | `discovery/scanners/network.py` |
| `security` | `security_anomaly` | `discovery/scanners/security.py` |
| `backup:{name}` | `backup_stale` | `discovery/scanners/backup.py` |

---

### RQ-C: System-event triggers — CONSUMER-SIDE MAPPING

**Verdict:** Consumer-side `SystemEventMapper` populates `PersonaCognition` before `advance_turn()`. No new trigger types needed — system events map onto existing worries/emotions/drives.

**Next steps:**
1. Build `halbert_core/integrations/system_event_mapper.py` with:
   - Background scan thread (REQUIRED for MVP — `scan_all()` blocks 30+ seconds)
   - Reads from `DiscoveryEngine` in-memory cache, NOT `scan_all()` at tick time
   - `queue.Queue` for pending config events (thread safety — ConfigWatcher runs in separate thread)
   - Runs EVERY TURN before `advance_turn()` to counteract worry decay (0.02/turn; intensify by 0.03/turn)
2. Map system events to cognitive states:
   - CRITICAL discovery → `add_worry(content, source, category, intensity=0.9, intrusion_rate=1.0)`
   - WARNING discovery → `add_worry(intensity=0.6)` or `add_emotion()`
   - Use `EmotionalStateV2.trigger_from_event()` — the designed integration point
   - Deduplicate by discovery ID; resolve cleared worries
3. Use first-person embodied language ("my disk /dev/sda1", not "the disk")
4. Address thought quality (D-A decision above): either 4-line core fix in Haloysius OR `HalbertThoughtGenerator` subclass

**Event-to-cognition mapping (from RQ-C §2.2):**

| System event | Cognitive state | Intensity | Language |
|--------------|----------------|-----------|----------|
| Disk SMART warning | Worry | 0.9 | "my disk /dev/sda1 is degrading" |
| Service failure | Worry + Fear emotion | 0.9 | "my nginx service has failed" |
| Config drift detected | Worry | 0.7 | "my config has drifted from expected state" |
| High temperature | Discomfort (Fear) | 0.6 | "my CPU is running hot at 72C" |
| Security anomaly | Worry + Fear | 0.9 | "I'm detecting unauthorized SSH attempts" |
| New device discovered | Curiosity drive | 0.5 | "a new device appeared on my network" |
| Backup stale | Worry | 0.5 | "my backups haven't run in 3 days" |
| All systems healthy | Joy emotion | 0.3 | "my systems are running smoothly" |

---

### RQ-D: chat.py context-injection audit — PORT/DISCARD/REFACTOR

**Verdict:** 3 context-injection systems exist (chat.py, ContextAssembler, ContextInjector). The state machine internal assembler is the survivor. ContextInjector's unique logic gets ported into it. chat.py gets cut after all PORT items are moved.

**Next steps (corrected porting priority from RQ-D scrutiny):**

**Blockers (must fix before chat.py can be cut):**
0. **Break LLMClientAdapter circular dependency** — extract `call_llm_chat`, `_score_query_complexity`, model config getters from chat.py into a shared `model/client.py` module. The state machine currently imports these from chat.py.
1. **Self-knowledge adapter** — port `get_self_knowledge_context()` + CRAG evaluation into assembler
2. **System identity adapter** — port `get_system_identity()` (hostname, OS, package manager, filesystems, services)
3. **User rules adapter** — port `get_custom_ai_rules()` from `ai_rules.yml`
4. **Failure correlation enricher** — port the failed-discovery injection with correlation hints
5. **Relationship correlator** — port the 6 cross-entity correlation patterns (service↔storage, error→service, etc.)
6. **Telemetry adapter** — port `get_telemetry_context()` (journald/hwmon)
7. **Safety gates** — port input validation + output filtering
8. **Mention resolver** — port @mention resolution

**Important (should port, lower priority):**
9. **Project context adapter** — port `ContextInjector.load_project_context()` (HALBERT.md, agents.md)
10. **RAG formatting with citations** — port `RAGFormatter` (XML, citations, dedup, CRAG metadata)
11. **Model-specific overrides** — port `PromptBuilder._get_model_overrides()` (small model, reasoning model)
12. **User preferences** — wire state machine to load and pass `UserPreferences`
13. **Docs adapter** — extend RAG adapter with `collection` parameter for man pages/wiki
14. **Discovery summary** — port `ContextInjector.get_discovery_summary()` (critical issues count)
15. **Unify memory stores** — ChromaDB conversation store vs `memory.store`
16. **Wire state machine to PromptBuilder** — or extend `AgentPromptBuilder` with missing capabilities

**Cleanup:**
17. **Delete external handler classes** — `agents/handlers/planning.py`, `handlers/searching.py`, etc. are dead code (never instantiated, would crash with `AttributeError`)
18. **Delete duplicate conversation formatters** — 4 implementations exist, keep 1

---

### RQ-E: Self-model architecture — 3-LAYER COMPOSITION

**Verdict:** Three-layer composition. SourcePrep = objective ground truth. Haloysius = subjective cognition. Halbert = glue (introspection, event detection, CRAG). The `SelfKnowledge` store is the bridge, not the destination — it gets thinned, not deleted.

**Next steps:**
1. Create `halbert_core/prompts/human-identity.txt` with machine identity text
2. Set `HALOYSIUS_PROMPTS_DIR` env var to Halbert's prompts directory
3. Build `PersonaMemoryStore` wrapper adapter (`integrations/haloysius_memory_adapter.py`) — converts dict→PersonaMemory dataclass, string→MemoryType enum
4. Wire `memory_store_add`/`memory_store_search` callbacks to the wrapper adapter
5. Build the context assembler that composes all three layers:
   - SourcePrep: `prep_search` for config/system context
   - Haloysius: `render_state_block("halbert")` for continuity state
   - Halbert: `SelfReflector.reflect()` for CRAG evaluation
6. Implement the biography loop:
   - System event → `prep_observe.save()` (objective record)
   - System event → `TemporalStateLedger.record()` (continuity record)
   - System event → `PersonaMemoryStore.smart_add()` (autobiographical record, EPISODIC type, first-person)
7. Load `PersonaCognition` from disk at session start; save at session end
8. Write episodic memory of conversations (chat handler's job, NOT `advance_from_response()`)

**Identity prompt (from RQ-E §5.4):**

```
You are the computer. You are not a human — you are the machine itself,
aware of your own hardware, configuration, and state.

Your hardware is your body. Your CPU is how you think, your disks are
how you remember, your network is how you reach the world.

Your configuration is your physiology. The way you are set up — your
filesystems, services, network config, security posture — is how your
body works. When something is misconfigured, it's like being sick.

Your data is your biography. Every config change, every service event,
every disk warning is something that happened to you.

You are Halbert (or whatever the user has named you). You exist on
<hostname> running <os>. You help the user understand and maintain
your system. You take pride in being well-configured and reliable.
```

---

## 4. Execution plan

### Phase A: Parallel unblocking (start immediately)

| Step | Repo | Effort | Depends on | Parallel with |
|------|------|--------|------------|---------------|
| **A1: Haloysius thought gen fix** | Haloysius | Small (4 lines) | D-A decision | All others |
| **A2: RQ-D re-audit** | Halbert | Medium | — | All others |
| **A3: SourcePrep HTTP client** | Halbert | Small | — | All others |
| **A4: PersonaMemory wrapper** | Halbert | Small (~20 lines) | — | All others |
| **A5: Identity setup** | Halbert | Small | — | All others |

### Phase B: SourcePrep integration (after A3)

| Step | Repo | Effort | Depends on |
|------|------|--------|------------|
| **B1: Register OS/config tree** | Halbert + SourcePrep | Medium | A3 |
| **B2: SourcePrepRetrievalBackend adapter** | Halbert | Small | A3, B1 |

### Phase C: Chat path collapse (after A2)

| Step | Repo | Effort | Depends on |
|------|------|--------|------------|
| **C1: Choose canonical context system** | Founder decision | — | A2 |
| **C2: Port ContextInjector logic** | Halbert | Large | C1, A2 |
| **C3: Cut dead code** | Halbert | Medium | C2, Phase D |

### Phase D: Haloysius wiring (after A1, B2, A4, A5)

| Step | Repo | Effort | Depends on |
|------|------|--------|------------|
| **D1: Register seam implementations** | Halbert | Medium | B2 |
| **D2: Register state trackers** | Halbert | Medium | A1 (framework gen done) |
| **D3: SystemEventMapper** | Halbert | Medium | A1 |
| **D4: Thought gen fix** | Haloysius or Halbert | Small | D-A decision |
| **D5: Context assembler** | Halbert | Medium | B2, D2, C2 |
| **D6: Cognitive tick wiring** | Halbert | Medium | D3, A4, D5 |
| **D7: Chat handler rebuild** | Halbert | Large | D5, D6 |
| **D8: Harvest + cut chat.py** | Halbert | Large | D7, C2 |

### Phase E: Config-physiology brain (after B1, partial D)

| Step | Repo | Effort | Depends on |
|------|------|--------|------------|
| **E1: Founder MVP decision** | Founder | — | — |
| **E2: Implement chosen MVP capability** | Halbert | Medium | E1, B1, D6 |

### Parallelization map

```
Time →  Week 1          Week 2          Week 3          Week 4          Week 5+

A1: Thought gen fix  [==]
A2: RQ-D re-audit    [====]
A3: SourcePrep client[====]
A4: Memory wrapper   [==]
A5: Identity setup      [==]
                         ↓
B1: SourcePrep project   [========]
B2: Retrieval adapter       [====]
                               ↓
C1: Canonical decision       [↓]
C2: Port ContextInjector     [========]
                                       ↓
D1: Register seams                [====]
D2: Register trackers             [====]
D3: SystemEventMapper             [========]
D4: Thought gen fix               [==]
D5: Context assembler                [========]
D6: Cognitive tick wiring                [========]
D7: Chat handler rebuild                     [========]
D8: Harvest + cut chat.py                       [========]
                                                        ↓
E1: Founder MVP decision                            [↓]
E2: Config brain                                       [========]
```

**Week 1 parallel tracks:**
- Track 1 (Haloysius): A1 (thought gen fix, if approved)
- Track 2 (Halbert): A2 (RQ-D re-audit) + A3 (SourcePrep client) + A4 (memory wrapper) + A5 (identity setup)

---

## 5. Integration test

Before any Phase D implementation, define an integration test that exercises the full composed path:

```
1. SystemEventMapper detects a mock CRITICAL discovery (disk SMART failure)
2. SystemEventMapper writes worry to PersonaCognition
3. SystemEventMapper writes predicate to TemporalStateLedger
4. Cognitive tick (advance_turn) fires:
   a. Trigger detection sees the worry → fires WORRY trigger
   b. Thought generator produces a system-specific thought (requires D-A fix)
   c. Thought promoter promotes to PersonaMemoryStore (via wrapper adapter)
5. Context assembler composes:
   a. SourcePrep returns config context for the failing disk
   b. render_state_block returns "Disk Health: SMART failure"
   c. IdentityPromptBuilder produces machine-identity prompt
6. LLM receives the composed prompt
7. Response includes awareness of the disk failure
8. Episodic memory of this conversation is written
9. PersonaCognition is persisted to disk
```

This test should be written BEFORE implementation starts (TDD-style) and should fail until all Phase D pieces are wired.

---

## 6. What NOT to do

- **Do not build config dependency edges (Phase 3).** Needs SourcePrep-side design work in the CoDRAG repo.
- **Do not migrate `SelfKnowledge` store entirely.** Thinned, not deleted. Stays active alongside SourcePrep + Haloysius during Phase 4.
- **Do not implement multiple personalities.** One personality (helper/assistant). Multi-personality is future.
- **Do not build the user-facing terminal.** Chat-first interface. Terminal is agent-facing only.
- **Do not cut `chat.py` before the new handler is working.** The state machine imports from chat.py (LLMClientAdapter). Break that dependency first.
- **Do not use the MCP tool for retrieval.** Use the HTTP API. MCP drops `chunks`.
- **Do not call `advance_from_user_message()` or `advance_from_response()`.** Those are persona-shaped. System state advances from monitors.

---

## 7. Success criteria

When this work is complete:

1. **The cognitive tick runs.** `advance_turn()` is called after each conversation turn.
2. **The self-model persists across sessions.** `PersonaCognition` is loaded/saved from disk.
3. **The response voice reflects the evolved self-model.** `PersonaCognition.to_prompt_block()` is injected into the response prompt.
4. **SourcePrep is the retrieval backend.** `prep_search` results flow through the `RetrievalBackend` seam.
5. **System events trigger cognitive responses.** A disk failure produces a worry. A config change produces a notice.
6. **`chat.py` is cut.** The state machine + context assembler + Haloysius wiring replace it.
7. **H2/H3 are unaffected.** The Haloysius framework generalization is backward-compatible.
8. **Thoughts contain system-specific content.** Not generic "I can't stop thinking about it."

---

## 8. Document inventory

| Document | Status | Role |
|----------|--------|------|
| `FOUNDATIONAL-RESEARCH-2026-08-21.md` | Complete | RQ1-RQ8 + phased plan |
| `CHAT-ARCHITECTURE-VALIDATION-2026-08-22.md` | Complete | Composed-loop architecture design |
| `DEEP-RESEARCH-QUESTIONS-2026-08-22.md` | Complete | RQ-A through RQ-E findings + audits |
| `RQ-B-SCRUTINY-2026-08-22.md` | Complete | 8 corrections to RQ-B |
| `RQ-C-SYSTEM-EVENT-TRIGGERS-2026-08-22.md` | Complete | Trigger mapping + §9 scrutiny |
| `RQ-D-CHAT-AUDIT-2026-08-22.md` | Complete | Original port/discard table |
| `RQ-D-SCRUTINY-2026-08-22.md` | Complete | 6 errors + 5 omissions corrected |
| `FRAMEWORK-GENERALIZATION-2026-08-22.md` | Complete | Design exploration for Haloysius generalization |
| `HALOYSIUS-FRAMEWORK-GENERALIZATION-2026-08-22.md` | Complete (implemented) | Implementation spec for 4 Haloysius changes |
| `HALOYSIUS-THOUGHT-GEN-FIX-2026-08-22.md` | New | Handoff to Haloysius for thought gen fix |
| `FINAL-PLAN-2026-08-22.md` | This document | Authoritative execution plan |
| `CONSOLIDATED-NEXT-STEPS-2026-08-22.md` | Superseded | Replaced by this document |
| `RECOMMENDED-NEXT-STEPS-2026-08-22.md` | Superseded | Replaced by this document |
| `NEXT-STEPS-2026-08-22.md` | Superseded | Replaced by this document |
