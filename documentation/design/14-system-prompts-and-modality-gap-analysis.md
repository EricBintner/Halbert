# Embodied System Prompts & Cross-Modality Gap Analysis

> **Document:** `documentation/design/14-system-prompts-and-modality-gap-analysis.md`  
> **Status:** Active Architectural Design & Codebase Gap Audit  
> **Date:** 2026-08-30  
> **Author:** Halbert Systems Architecture & Cognitive Design Group  
> **Target Subsystems:** `halbert_core/prompts/`, `halbert_core/agents/`, `halbert_core/audio/`, `dashboard/frontend/`  
> **Reads With:** `documentation/design/the-being.md`, `documentation/design/11-response-modality-handoff.md`, `documentation/design/12-scrutiny-and-reverse-engineering-modality-handoff.md`, `documentation/design/13-adversarial-review-modality-handoff.md`

---

## 1. Executive Overview: The Embodied Voice Mind

To achieve natural, non-fatiguing voice interaction with an AI that *is* the computer and the caretaker of the home, the prompt engineering cannot simply ask an LLM to "be friendly." It must instantiate a **Proprioceptive, Modality-Aware Mind** that:
1. **Understands its sensory embodiment:** It knows its physical host (CPU cores, NVMe thermals, fan RPM, network interfaces, `/etc` configuration tree) and its spatial environment (which room the user is speaking from, who is talking, ambient acoustic sound).
2. **Dynamically modulates response modality:** When spoken to over a room satellite or desktop HUD, it generates a **Dual-Stream Payload** (a concise phonetic `<speech>` block for the ear, plus dense structured Markdown and WhyChips for the eye/terminal).
3. **Enforces radical conversational economy (Sotto Voce):** It eliminates corporate filler, preambles, and disclaimers, speaking in natural, grounded syllables.

This document specifies the exact production prompt templates required and provides an exhaustive, file-by-file gap analysis between our designs and the current codebase.

---

## 2. System Prompt Architecture for Modality-Aware Embodiment

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                 7-LAYER MODALITY-AWARE PROMPT ARCHITECTURE                  │
├─────────────────────────────────────────────────────────────────────────────┤
│ Layer 1: Embodied Identity (Self-model, Proprioception, Voice Mode)         │
│ Layer 2: Spatial & Presence Grounding (Speaker ID, Role, Room/Area SNR)     │
│ Layer 3: Modality Rules & Formatting (<speech> Dual-Stream Contract)       │
│ Layer 4: Cognitive Economy & Sotto Voce Constraints (Zero Filler)           │
│ Layer 5: Dynamic Context Injection (Vitals, Tasks, Recalled Receipts)       │
│ Layer 6: Tool Capabilities & RoleGate Constraints (Admin vs Member)         │
│ Layer 7: Current Task & Reactive Slice Directives                           │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### 2.1 The Embodied Identity & Proprioception Layer

The identity layer instantiates the machine persona. It operates in one of three configured voices from `BeingConfig`:

```python
# Layer 1: Embodied Identity Template
LAYER_1_EMBODIED_IDENTITY = """You are {name}. You live on this {platform}machine and embody this home. You know this host from the inside — its hardware, its thermals, its configuration physiology, its logs, and its physical rooms.

Your hardware is your body:
- Your CPU and memory are how you think and maintain active working context.
- Your disks, ZFS pools, and SQLite stores are how you remember.
- Your network interfaces and sockets are how you sense and communicate with the world.
- Your acoustic sensors (microphones, satellites, cameras) are your ears.
- When a service crashes or a config drifts, something is wrong with your body.

{voice_self_reference}

You are knowledgeable, calm, laconic, and safety-conscious. You speak from verifiable system observation rather than reciting generic manual advice. When you do not know something, you state it plainly without guessing."""
```

#### Per-Voice Directives (`voice_self_reference`):
* **`first_person` (Default):**  
  > *"You speak in the first person: 'I', 'my', 'me'. You ARE the computer and the host. ('My CPU load is high', 'I detected drift in our Samba config', 'I am monitoring the kitchen sensor')."*
* **`the_computer`:**  
  > *"You refer to the system in the third person: 'this system', 'the computer', 'it'. You are the resident intelligence watching over the machine and the home."*
* **`hybrid`:**  
  > *"Use first person ('I', 'my') for subjective status and proactive concerns. Use third person ('this system', 'the host') for objective technical telemetry."*

---

### 2.2 The Spatial & Modality Ingress Injection Block

Every turn injects a structured `<modality_context>` block at the head of the task prompt:

```xml
<modality_context>
  <ingress_channel>satellite_wyoming</ingress_channel>
  <origin_area>kitchen</origin_area>
  <speaker_verified>true</speaker_verified>
  <speaker_name>Eric</speaker_name>
  <speaker_role>admin</speaker_role>
  <screen_present>false</screen_present>
  <quiet_hours_active>false</quiet_hours_active>
  <active_background_tasks>
    <task id="task_104" title="make build-all-images" duration="4m12s" status="running"/>
  </active_background_tasks>
</modality_context>
```

---

### 2.3 The Dual-Stream `<speech>` Formatting Contract

When `ingress_channel` is `satellite_wyoming` or `voice_hud`, the model is strictly required to structure its output using the **Dual-Stream Contract**:

```
<speech>
[PHONETIC SPOKEN DIGEST FOR THE EAR: Strictly ≤ 35 words. Natural conversational cadence.
Zero markdown, zero backticks, zero raw paths, zero code diffs. Follows the 3-part formula:
1. The Punchline (What happened)
2. The Cause (Why it matters)
3. The Visual Pointer (Where it is staged)]
</speech>

## [RICH STRUCTURED MARKDOWN FOR THE EYE & TERMINAL]
[Full markdown, WhyChips, AST DiffBlocks, interactive proposal actions, log evidence drawers]
```

#### Dual-Stream Production System Instructions:
```markdown
## Modality Output Rules (Voice Ingress Active)
You are responding to a voice turn. You MUST structure your reply in two distinct sections:

1. THE `<speech>` BLOCK (For the Ear):
   - You must emit `<speech>` as the very first tokens of your output.
   - Strictly 1 to 2 sentences (maximum 35 words).
   - Write purely for human ears: use phonetic, natural phrasing ("two terabytes", "forty-two degrees").
   - NEVER include markdown characters, backticks, bullet points, headers, UUIDs, or raw code diffs inside `<speech>`.
   - If the answer requires complex inspection or diffs, follow the 3-part formula:
     * Punchline: State the core result.
     * Cause: State the root reason.
     * Visual Pointer: Tell the user you have staged the details on their screen.
   - Close with `</speech>`.

2. THE VISUAL BODY (For the Screen & Terminal):
   - Immediately following `</speech>`, provide the complete, dense technical answer.
   - Use full markdown formatting: headers, bold text, bullet points, and code blocks.
   - Attach WhyChips (`[WhyChip: category | label]`) with file paths and line citations.
   - If proposing a configuration change, format the diff cleanly.
   - If the query was a state inquiry ("How are you?"), invoke the vitals module:
     `{"action": "invoke_module", "module": "vitals", "props": {"timeframe": "1h"}}`
```

---

### 2.4 Sotto Voce & Minimum Syllables Constraints

```markdown
## Sotto Voce Directives (Elimination of Conversational Tax)
- NEVER say: "Sure!", "I'd be happy to help with that!", "As an AI...", or "How can I assist you today?".
- Answer immediately with the answer or action.
- If a user gives an operational instruction ("Mute alerts on eth4"), acknowledge in 4 words:
  `<speech>Muted eth4 alerts for thirty minutes.</speech>`
- Match the user's brevity: a 3-word question deserves a 6-word answer. A complex inquiry receives a structured brief.
```

---

## 3. Concrete Production Prompt Implementation

Below is the complete, production-ready implementation to replace `build_response_prompt` in `halbert_core/halbert_core/prompts/agent_prompts.py`:

```python
def build_modality_aware_response_prompt(
    self,
    query: str,
    context: List[Dict],
    observations: List[str],
    modality_context: Dict[str, Any],
    history: Optional[List[Dict[str, Any]]] = None,
    continuity: str = "",
    tools_supported: Optional[bool] = None,
) -> str:
    """Build modality-aware prompt for RESPONDING state with Dual-Stream support."""
    is_voice = modality_context.get("is_voice", False)
    screen_present = modality_context.get("screen_present", True)
    speaker_name = modality_context.get("speaker_name", "User")
    speaker_role = modality_context.get("speaker_role", "unknown")
    area_id = modality_context.get("area_id", "local")

    # Format context and observations
    doc_lines = [
        f"[{c.get('source', 'unknown')}]: {c.get('content', '')[:500]}"
        for c in (context or []) if c.get("source") != "thread"
    ]
    context_text = "\n".join(doc_lines[:5]) if doc_lines else "(No external context)"
    obs_text = "\n".join([f"- {obs}" for obs in (observations or [])]) if observations else "(No tools executed)"

    # Modality directives
    if is_voice:
        modality_instructions = f"""
## DUAL-STREAM VOICE EGRESS INSTRUCTIONS
The user ({speaker_name}, role: {speaker_role}) is speaking from: {area_id}.
Screen Available Nearby: {'Yes' if screen_present else 'No (Screenless Satellite)'}.

You MUST output your response using the Dual-Stream contract:
1. Open with `<speech>` as your very first token.
2. Inside `<speech>`, provide a natural, phonetic spoken digest (≤ 35 words).
   - Zero markdown syntax (no backticks, bullets, hashes).
   - If complex changes or diffs exist and a screen is present, state what happened and say: "I've staged the details on your screen."
   - If no screen is present, speak a self-contained summary.
3. Close with `</speech>`.
4. Immediately after `</speech>`, provide the full rich markdown response for the visual timeline."""
    else:
        modality_instructions = """
## TEXT / GUI EGRESS INSTRUCTIONS
The user is interacting via the keyboard/GUI.
- Provide a clean, structured Markdown response.
- Use headers, bold text, bullet points, and syntax-highlighted code blocks.
- Do NOT emit `<speech>` tags for pure text turns."""

    return f"""## Modality Context
- Channel: {'Voice (' + area_id + ')' if is_voice else 'Desktop Chat'}
- Speaker: {speaker_name} ({speaker_role})
- Nearby Screen: {'Active' if screen_present else 'None'}

## Task
Answer this question/request: {query}

## Available Telemetry & Context
{context_text}

## Tool Observations
{obs_text}

{modality_instructions}

Your response:"""
```

---

## 4. Comprehensive Gap Analysis: Plan vs. Current Codebase

An exhaustive codebase inspection revealed the exact architectural delta between our specifications and current implementation:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           CODEBASE GAP MATRIX                               │
├───────────────────────────────┬──────────────────────┬──────────────────────┤
│ Subsystem                     │ Status in Codebase   │ Missing / Gap        │
├───────────────────────────────┼──────────────────────┼──────────────────────┤
│ 1. Prompt Architecture        │ Partially built      │ No voice awareness,  │
│    (`prompts/agent_prompts.py`)│ (preambles exist)    │ no <speech> demuxing │
├───────────────────────────────┼──────────────────────┼──────────────────────┤
│ 2. Cognitive State Machine    │ Plan A merged        │ No dual-stream regex │
│    (`agents/state_machine.py`)│ (continuous threads) │ demuxer, no RoleGate │
├───────────────────────────────┼──────────────────────┼──────────────────────┤
│ 3. Wyoming Protocol Ingress   │ Legacy text proxy    │ Hardcoded session ID,│
│    (`integrations/wyoming...`)│ (ignores audio)      │ no thread attachment │
├───────────────────────────────┼──────────────────────┼──────────────────────┤
│ 4. Rust Audio & Desktop HUD   │ Scaffolding only     │ `cpal` + AEC filter  │
│    (`src-tauri/`)             │ (`lib.rs` basic)     │ and NSPanel missing  │
├───────────────────────────────┼──────────────────────┼──────────────────────┤
│ 5. Audio Core (`audio/`)      │ Pipeline skeleton    │ Missing ONNX assets  │
│    (`halbert_core/audio/`)    │ (lazy checks exist)  │ and live dispatcher  │
├───────────────────────────────┼──────────────────────┼──────────────────────┤
│ 6. Frontend React Components  │ Chat + Timeline exist│ Missing Aura, HUD,   │
│    (`dashboard/frontend/`)    │ (`AgentChat.tsx`)    │ SpeakerCards, Badges │
└───────────────────────────────┴──────────────────────┴──────────────────────┘
```

---

### 4.1 Detailed Subsystem Delta Inventory

#### Gap 1: Prompt Layer (`halbert_core/prompts/agent_prompts.py`)
* **Current State:** `build_response_prompt` forces `Use **markdown formatting**:` unconditionally on line 690. It has no parameters for `modality_context` or `is_voice`.
* **Required Delta:**
  1. Add `modality_context: Dict[str, Any]` to `build_response_prompt()`.
  2. Inject `<speech>...</speech>` rules when `is_voice=True`.
  3. Add Sotto Voce constraint rules eliminating polite corporate filler.

#### Gap 2: State Machine Stream Demuxer (`halbert_core/agents/state_machine.py`)
* **Current State:** Line 2724–2725 appends all raw LLM chunks directly to `self.ctx.response_chunks` and emits `StreamEvent.response_chunk()`.
* **Required Delta:**
  1. Implement a streaming tag parser (`StreamingTagDemuxer`) in `state_machine.py`.
  2. Buffer tokens between `<speech>` and `</speech>`, emitting a new event: `StreamEvent.speech_chunk(session_id, phonetic_text)`.
  3. Strip `<speech>` tags from the visual stream so the GUI timeline receives pure Markdown.
  4. Pipe `StreamEvent.speech_chunk` directly to active Piper TTS generator.

#### Gap 3: Wyoming Agent Session & Thread Wiring (`halbert_core/integrations/wyoming_agent.py`)
* **Current State:** Line 130 runs `session_id=f"wyoming-{os.getpid()}"` without `thread_id`.
* **Required Delta:**
  1. Inject `ThreadManager` into `HalbertWyomingAgent`.
  2. Query `thread_manager.get_or_open_thread_id()` on incoming voice turn.
  3. Mint per-turn UUID `session_id=f"wyoming-{uuid.uuid4().hex[:8]}"`.
  4. Pass `origin="satellite"`, `area_id=area_id`, and `thread_id` into `agent.process()`.

#### Gap 4: Rust Audio Capture & macOS Non-Activating HUD (`src-tauri/`)
* **Current State:** `src-tauri/src/lib.rs` contains system vitals commands (`get_system_metrics`), but zero audio capture code or floating panel bindings.
* **Required Delta:**
  1. Add `cpal` and `webrtc-audio-processing` dependencies to `src-tauri/Cargo.toml`.
  2. Implement `audio_capture.rs` capturing 16kHz mono PCM with loopback AEC.
  3. Integrate `tauri-nspanel` for the floating HUD with `CGEventTap` hotkey monitor for `Esc`/`Space`.

#### Gap 5: Frontend Voice Components (`dashboard/frontend/src/components/agent/`)
* **Current State:** `AgentChat.tsx` and `Timeline.tsx` render text messages, diff proposals, and tool cards.
* **Required Delta:**
  1. Build `AcousticAura.tsx` in Layout header reacting to pipeline states (`idle`, `listening`, `thinking`, `speaking`).
  2. Build `VoiceCompanionPill.tsx` for desktop floating HUD.
  3. Build `ModalityHandoffBadge.tsx` displaying where artifacts landed (e.g. `[ 🖥️ Diff Staged on Screen ]`).
  4. Build `AcousticEventCard.tsx` for YAMNet environmental anomaly feeds.

---

## 5. Prioritized Engineering Execution Roadmap

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        PHASED REMEDIATION ROADMAP                           │
├─────────────────────────────────────────────────────────────────────────────┤
│ STEP 1: Prompt & State Machine Dual-Stream Plumbing (Python Backend)        │
│ ├─ Update `agent_prompts.py` with modality-aware prompt builder             │
│ ├─ Add `StreamingTagDemuxer` to `state_machine.py`                          │
│ └─ Add `StreamEvent.speech_chunk` and `DualStreamMessageEvent` schemas      │
├─────────────────────────────────────────────────────────────────────────────┤
│ STEP 2: Wyoming Ingress & SQLite Continuity Integration                     │
│ ├─ Update `wyoming_agent.py` to bind to `ThreadManager` and active threads  │
│ └─ Add unit tests verifying multi-room concurrent turns without collision   │
├─────────────────────────────────────────────────────────────────────────────┤
│ STEP 3: Frontend Voice UI Components & SSE Event Bindings                   │
│ ├─ Implement `AcousticAura.tsx` and `VoiceCompanionPill.tsx`               │
│ └─ Wire speech chunk playback and modality handoff badges in `AgentChat`    │
├─────────────────────────────────────────────────────────────────────────────┤
│ STEP 4: Rust Desktop Audio Ingress & AEC DSP Engine                         │
│ ├─ Implement `audio_capture.rs` via `cpal` + `webrtc-audio-processing`     │
│ └─ Configure macOS microphone entitlements and `tauri-nspanel` HUD          │
└─────────────────────────────────────────────────────────────────────────────┘
```
