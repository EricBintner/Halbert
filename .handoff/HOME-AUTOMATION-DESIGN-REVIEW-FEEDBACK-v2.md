# Halbert Home Automation — Second-Pass Design Review

**Date:** 2026-08-27  
**Pass:** Second (with self-correction of first-pass findings)  
**Model:** Claude Sonnet (Thinking)

---

## Critical Self-Corrections from First Pass

Before continuing, we need to retract or revise three findings from the first review that were wrong or oversimplified, and add several areas the first pass missed entirely.

---

### Correction 1: The Persona_id Hardcoding Severity Was Understated

The first pass called out three hardcoded strings in `cognition_wiring.py`. On deeper inspection, the problem is **substantially worse** than reported:

**Files with hardcoded `"halbert"` persona identity (full audit):**

| File | Line | Hardcode |
|------|------|----------|
| [`cognition_wiring.py:33`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/integrations/cognition_wiring.py#L33) | `PersonaCognition(persona_id="halbert")` | Memory partition key |
| [`cognition_wiring.py:39-43`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/integrations/cognition_wiring.py#L39-L43) | `cognition.scene_context = "macOS system administration"` | Cognitive framing |
| [`cognition_wiring.py:66`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/integrations/cognition_wiring.py#L66) | `PersonaMemoryStore("halbert")` | SQLite/JSON storage path |
| [`cognition_wiring.py:110`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/integrations/cognition_wiring.py#L110) | `ThoughtGenerator("halbert", "Halbert", ...)` | Thought generation identity |
| [`agents/states.py:183`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/agents/states.py#L183) | `persona_id: str = "halbert"` | Per-turn state context |
| [`haloysius_memory_adapter.py:48`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/integrations/haloysius_memory_adapter.py#L48) | `persona_id=d.get("persona_id", "halbert")` | Memory object default |
| [`haloysius_memory_adapter.py:139`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/integrations/haloysius_memory_adapter.py#L139) | `"persona_id": "halbert"` | Memory serialization |
| [`integrations/state_trackers.py:20`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/integrations/state_trackers.py#L20) | `DEFAULT_PERSONA_ID = "halbert"` | Tracker default |
| [`conversation/summarization.py:517`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/conversation/summarization.py#L517) | `Path.home() / '.halbert' / 'personas' / persona_id / 'conversation_memories'` | Conversation memory path |

**Critical discovery — Haloysius `paths.py` provides the actual fix:**

Verified in [`/Volumes/4TB-BAD/Haloysius/src/haloysius/paths.py`](file:///Volumes/4TB-BAD/Haloysius/src/haloysius/paths.py):
```python
DATA_HOME_ENV = "HALOYSIUS_DATA_HOME"
_DEFAULT_DATA_HOME = Path.home() / ".local" / "share" / "haloysius"

def data_home() -> Path:
    """Root directory for persisted state. Honours HALOYSIUS_DATA_HOME."""
    override = os.environ.get(DATA_HOME_ENV, "").strip()
    if override:
        return Path(override).expanduser()
    return _DEFAULT_DATA_HOME
```

**This means `PersonaMemoryStore` storage paths flow through `state_dir()` → `data_home()` → `HALOYSIUS_DATA_HOME` env var.** Running the home instance with `HALOYSIUS_DATA_HOME=/home/user/.local/share/halbert-home` cleanly isolates ALL Haloysius memory storage without touching a line of code.

**Revised Assessment:**  
- Memory storage isolation: **Solvable via `HALOYSIUS_DATA_HOME` env var. No code change needed.**
- `scene_context` hardcode in `_create_cognition()`: **Still broken. Home instance will think it's running "macOS system administration" unless `being.yml` adds a `scene_context` field and it's read there.**
- `persona_id="halbert"` in `PersonaCognition`: **The memory store will still create directories named "halbert" under `HALOYSIUS_DATA_HOME`. The persona ID itself needs to be read from `BeingConfig` for the embedding cache to be named correctly (line 85: `get_embedder(f"{persona_id}_memory_v2")`).**

**Minimum fix for two-process strategy:**
1. Set `HALOYSIUS_DATA_HOME=/path/to/halbert-home/data` in the home instance environment.
2. Add `scene_context: str = ""` to `BeingConfig` and `being.yml`.
3. In `_create_cognition()`: read `scene_context` from `BeingConfig` rather than platform detection.
4. Read `persona_id` from `BeingConfig` in `_create_cognition()`, `_create_memory_adapter()`, and `_create_thought_generator()`.

---

### Correction 2: The SourcePrep "One Project Only" Finding Is Correct But Incomplete

The first pass correctly identified that `SourcePrepRetrievalBackend` and `wire_halbert_seam()` bind to a single `project_id`. However, it missed a nuance:

**The scope system within a single project can simulate multiple data sources.** Looking at [`sourceprep_retrieval_backend.py:86-99`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/integrations/sourceprep_retrieval_backend.py#L86-L99), SourcePrep supports named scopes (`host`, `knowledge_linux`, `knowledge_macos`) within one project. If the HA config tree were indexed as a separate scope within the same project, `scope_for_query()` could route home-config queries to a `ha_config` scope and host queries to `host`, all from a single backend instance.

**The revised recommendation:** Before building a `CompositeRetrievalBackend`, check whether SourcePrep's scope provisioning can treat HA configs as a new scope partition within the existing project. This may require zero Halbert code changes and only a SourcePrep project config change.

---

### Correction 3: The SPA Route Finding is Correct — But the Scope of Impact Is Larger

The first pass found that `@app.get("/home")` is missing from `app.py`'s explicit SPA route list. On closer inspection of the explicit route list (lines 326–347), **every** future panel will hit this same pattern: `/home`, `/automation`, `/energy`, `/cameras` — each needs explicit registration. This is a structural gap in the handoff procedure, not a one-time fix.

**Recommendation:** Add a comment in `app.py` and the handoff template noting that every new frontend route MUST add both (a) `App.tsx` `<Route>` and (b) `@app.get("/route-name")` in `app.py`. This should also be a checklist item in the handoff doc format.

---

### Correction 4: The Config Path Isolation Problem Is Worse Than Stated

The first pass called out `~/.config/halbert/being.yml` as a single shared path. Looking at `get_config_dir()` in [`platform.py:192-211`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/utils/platform.py#L192-L211), there is **no env var override** for the config directory:

```python
def get_config_dir() -> Path:
    if is_macos():
        return Path.home() / "Library" / "Application Support" / "Halbert"
    else:
        return Path.home() / ".config" / "halbert"
```

There is no `HALBERT_CONFIG_DIR` or `HALBERT_CONFIG_PATH` equivalent. This means:

1. Two processes both call `load_being_config()` and both read the same `~/.config/halbert/being.yml`.
2. The startup scan (`bootstrap_identity()`) in `app.py:376-384` touches shared self-knowledge structures.
3. The APScheduler (`AutonomousExecutor`) and ingestion service also start from the same codebase — both processes attempt to run detector sweeps and morning reports for a sysadmin context.

**The two-process strategy requires adding `HALBERT_CONFIG_DIR` support to `platform.get_config_dir()`.** Without this, the home instance always loads the host's `being.yml` and starts the sysadmin ingestion pipeline (journald scraping, hwmon, disk monitoring) which is meaningless on the HA target hardware.

---

## Newly Discovered Issues

### New Issue 1: The Ingestion Service Is Not "NOT NEEDED" — It Will Start Automatically

Design doc Section 9.3 marks the `ingestion/` service as "NOT NEEDED" for home automation. But `app.py:386-403` starts the ingestion service at every startup in a background thread:

```python
def start_ingestion_delayed():
    from ..ingestion.service import get_ingestion_service
    service = get_ingestion_service()
    service.start()
```

This ingestion service (journald + hwmon) will start on the home instance and attempt to scrape Linux system journals and hardware monitor data from the HA server VM. On an HA OS VM (running a musl-based Alpine Linux), hwmon devices exist but journald may not, which will generate log errors. The sysadmin-specific discovery scan (`bootstrap_identity()`, line 376) will also fire and attempt CPU/disk/service enumeration that is semantically wrong for a home identity.

**Fix:** The home instance needs either:
- A `HALBERT_VARIANT=home` env var checked at startup to suppress the sysadmin pipeline.
- Or the `BeingConfig` `purpose` field used to gate which startup services launch.

This is not a minor issue — the home instance will start partially as a Linux sysadmin agent by default.

---

### New Issue 2: The `StateContext` `persona_id` in `agents/states.py` Matters More Than Thought

Found in [`agents/states.py:183`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/agents/states.py#L183):
```python
persona_id: str = "halbert"
```

This is the per-turn state context passed through the agent's state machine. The `persona_id` here feeds into memory operations during the turn. If this stays `"halbert"` while the Haloysius store is partitioned to a "home" persona, memory written during turns will carry the wrong identity tag and may not be searchable under the home persona's namespace. This is a subtle data corruption risk, not just a naming issue.

---

### New Issue 3: `BeingConfig` Has No `ha_url` Field — The Handoff is Internally Inconsistent

Design doc Section 5 (Home being.yml example) shows:
```yaml
ha_url: "http://localhost:8123"
```
But verified in [`being_config.py`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/config/being_config.py#L33-L58): `BeingConfig` has NO `ha_url` field. The handoff says HA config goes into a separate `ha_config.yml`, which is correct — but the design doc contradicts this. The design doc's `being.yml` example is wrong and will confuse the implementing agent. It should show `ha_url` only in `ha_config.yml`, not in `being.yml`.

---

### New Issue 4: The `advance_turn` Call Pattern Does NOT Fit a Streaming Event Architecture

Looking at how `advance_turn` is currently invoked (via `cognition_tick()` in the agent state machine), it's called **per user turn** — once per message exchange. It is not designed to be called on arbitrary HA events arriving asynchronously over WebSocket.

**The design doc proposes in Phase 2:**
> `ha_event_mapper.py` — WebSocket client subscribing to `state_changed` events, mapping to PersonaCognition observations

But `advance_turn` is a discrete tick, not a streaming consumer. The proposed architecture of calling it on every HA event would be incorrect — it should accumulate HA events into `_pending_events` (following the existing `SystemEventMapper` pattern), then fire `advance_turn` on a configurable interval (e.g., every 5 minutes, or when a significant event arrives, or on next user interaction).

The `SystemEventMapper`'s existing design (lines 60-97) already shows the right pattern: `add_event()` queues events, `populate_cognition()` flushes them before `advance_turn`. The HA event mapper should mirror this exactly, not trigger `advance_turn` on every HA state change.

---

### New Issue 5: Token Budget Starvation in Voice Context

For voice interaction, the agent's `SendMessageRequest` supports `max_tokens: Optional[int] = Field(8192, ...)`. A voice transcript like "Hey home, what happened overnight?" must generate:
1. A tool call to query episodic memory
2. A tool call to query HA Recorder history
3. A natural-language voice response

With a 3B model's limited context window (~4K-8K tokens) and a Halbert system prompt that likely exceeds 2K tokens alone, plus memory context, the remaining token budget for the actual voice reply may be less than 300 tokens (~200 words). This is borderline for conversational voice responses that include summarized overnight events.

**Recommendation:** Voice responses need a separate, leaner system prompt path. The full sysadmin context prompt is inappropriate for voice. A "voice mode" system prompt variant should be wired at the Wyoming agent layer.

---

## Reconsidered First-Pass Findings — Standing, Revised, or Retracted

| Finding | Status | Revision |
|---------|--------|----------|
| Path C (hybrid) is correct | **CONFIRMED** | Still the right call. |
| WebSocket event flood | **CONFIRMED** | The existing `SystemEventMapper` pattern (queue + batch flush) is the proven template for fixing this. Use it exactly. |
| State hydration on boot | **CONFIRMED + STRENGTHENED** | Now also recommend querying HA Recorder `/api/history/period` for 14 days of history on first boot. |
| Phase 3/4 sequence swap (voice before HACS) | **CONFIRMED** | Wyoming agent requires no HACS. Voice should precede the custom component. |
| SourcePrep early (Phase 3) | **CONFIRMED** | The automation conflict diagnosis use case is the strongest early value. |
| `persona_id` hardcoding severity | **UPGRADED** | The full scope is 9 sites, not 4. `HALOYSIUS_DATA_HOME` solves memory isolation; `HALBERT_CONFIG_DIR` (doesn't exist yet) is still needed. |
| SourcePrep single project | **REVISED** | Scope partitioning within one project may be viable before building a CompositeRetrievalBackend. Investigate first. |
| SPA route missing `@app.get("/home")` | **CONFIRMED + EXPANDED** | This is a structural gap in the handoff process, not a one-time fix. |
| RAM numbers (7B → 3B recommendation) | **CONFIRMED** | 7B on N150 is voice-unusable. 3B is required for sub-2s voice. |
| Embedding offload to Ollama | **CONFIRMED** | Haloysius `PersonaMemoryStore` embeds via `get_embedder()` which calls `MemoryEmbedder` with `all-MiniLM-L6-v2`. This loads PyTorch. Making this configurable to use Ollama embeddings would save ~500MB RAM. |
| Extended OpenAI Conversation as missed competitor | **CONFIRMED** | Must be in the competitive landscape. |
| Multi-human household blind spot | **CONFIRMED** | No design doc mentions it at all. |
| Physical safety governance levels | **CONFIRMED** | `HalbertGovernancePolicy` returns `safe=True` universally — this is dangerous for home control. |

---

## New Recommendations

### Priority 1: Config Isolation Infrastructure (Pre-Phase 1)

Add `HALBERT_CONFIG_DIR` support to `platform.get_config_dir()` before ANY home instance work:

```python
def get_config_dir() -> Path:
    override = os.environ.get("HALBERT_CONFIG_DIR", "").strip()
    if override:
        return Path(override).expanduser()
    if is_macos():
        return Path.home() / "Library" / "Application Support" / "Halbert"
    else:
        return Path.home() / ".config" / "halbert"
```

This one change, combined with `HALOYSIUS_DATA_HOME`, gives you complete two-process isolation with zero architecture changes.

### Priority 2: `BeingConfig` Additions for Home Identity

Add to `BeingConfig`:
```python
# Home identity fields
scene_context: str = ""           # e.g. "smart home automation" (overrides platform detection)
persona_id_override: str = ""     # e.g. "home" (overrides hardcoded "halbert")
variant: str = "sysadmin"         # "sysadmin" | "home" — gates startup service selection
```

The `variant` field is the cleanest way to suppress the sysadmin ingestion pipeline on a home instance.

### Priority 3: Handoff Doc Structural Fix

The handoff document needs an explicit SPA route checklist and must clarify:
- `being.yml` does NOT contain `ha_url` (contradicts design doc Section 5)
- Every new frontend route needs BOTH `App.tsx` `<Route>` AND `@app.get("/route-name")` in `app.py`
- The `agents/states.py` `persona_id` field must be wired from `BeingConfig` before cognition is considered "home-aware"

### Priority 4: HA Event Mapper Architecture (Phase 2)

The `HAEventMapper` must follow the exact `SystemEventMapper` pattern:
```python
class HAEventMapper:
    """Async bridge from HA WebSocket state_changed events to PersonaCognition.
    
    Mirrors SystemEventMapper's queue-and-flush pattern:
    - add_event(): thread-safe enqueue from the WS coroutine
    - populate_cognition(): called before advance_turn(), flushes pending events
    
    advance_turn is NOT called per HA event. Events accumulate until:
    - User sends a message (natural flush point)
    - Scheduled cognitive tick interval (e.g., every 5-10 minutes)
    - Significant event threshold (e.g., security alert)
    """
```

### Priority 5: Voice System Prompt Variant

Wire a `voice_mode: bool` flag into `AgentPromptBuilder`. When the Wyoming agent processes a transcript, it sets `voice_mode=True`, which selects a compact system prompt variant (no sysadmin sections, no tool documentation for non-voice tools, under 800 tokens) to preserve context budget for the actual response.

---

## User Interaction: Still-Missing Patterns

The first pass covered multi-human household and the three interaction tiers. This pass adds three more patterns not discussed anywhere:

### Pattern: The Absent User ("Check On House While Traveling")
Users frequently want to check in on their house when away for work or vacation:
> *"Halbert, I'm in Tokyo. What's going on at home?"*

This requires:
- A public-facing query interface (Tailscale dashboard access, or a push channel)
- A "summary since N hours ago" capability drawing from episodic memory
- Camera snapshot retrieval (Frigate Phase 5) as proof/reassurance

The design doc assumes local interaction. **Remote check-in is the #2 most common home automation use case and isn't mentioned once.**

### Pattern: Routine-Learning vs. Rule-Setting
Current users set HA automations by writing YAML rules. A major user need that Halbert can address uniquely:
> *"Learn from what I actually do and suggest automations I'd probably want."*

This is enabled by longitudinal memory. If Halbert observes that every weekday at 7:15 AM the user manually turns on the kitchen lights, it can suggest: *"I've noticed you turn on the kitchen lights weekday mornings around 7:15. Want me to automate that?"*

No other HA LLM integration can do this. It's a killer feature hiding in the memory system.

### Pattern: Failure-Mode Conversational Repair
When Halbert misunderstands or executes the wrong action:
> User: *"Turn off the bedroom lights"*  
> Halbert: *(turns off ALL lights in house)*  
> User: *"No, not everything, just the bedroom"*

The agent must support conversational repair — storing the mistake in episodic memory with negative valence, updating its spatial context model, and confirming the corrective action explicitly. This is a UX and safety requirement, not a nice-to-have.
