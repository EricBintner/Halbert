# Deep Scrutiny & Reverse-Engineering Audit: Response Modality Handoff

> **Document:** `documentation/design/12-scrutiny-and-reverse-engineering-modality-handoff.md`  
> **Status:** Completed Architectural Scrutiny & Reverse-Engineering Audit  
> **Date:** 2026-08-30  
> **Audience:** Systems Architects, Audio DSP Engineers, Core Platform Leads  
> **Subject:** Reverse-engineering the Halbert voice/chat execution path, identifying hidden concurrency/DSP landmines, and verifying cross-modality handoff mechanics.  
> **Reads With:** `documentation/design/11-response-modality-handoff.md`, `audio-research/01-CORRECTED-ARCHITECTURE.md`, `documentation/design/continuous-conversation-and-watched-terminals-2026-08-26.md`

---

## 1. Executive Summary of Scrutiny

We subjected the Response Modality Handoff specification ([`11-response-modality-handoff.md`](file:///Volumes/4TB-BAD/Halbert/documentation/design/11-response-modality-handoff.md)) to an adversarial reverse-engineering audit across all layers of the stack: Rust `src-tauri` audio capture, macOS `NSPanel` event loops, FastAPI async route handlers, the `AgentStateMachine` turn lock, Wyoming TCP protocol framing, and the SQLite continuous conversation store.

Our analysis identified **six critical technical landmines** that would cause audio feedback loops, race conditions, session collisions, or usability failures if implemented naively:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       THE 6 CRITICAL AUDIT FINDINGS                         │
├─────────────────────────────────────────────────────────────────────────────┤
│ 1. Wyoming Hardcoded Session Collision & Thread Isolation Failure (CRITICAL) │
│ 2. Dual-Stream Serialization & TTS Phonetic Parsing Latency (HIGH)          │
│ 3. Acoustic Loopback Self-Interruption (AEC False Barge-In Loop) (CRITICAL) │
│ 4. macOS Non-Activating Panel Keyboard Focus Trap (HIGH)                    │
│ 5. Spoken PIN Acoustic Leakage & Multi-Occupant Security Exposure (HIGH)    │
│ 6. Watched Terminal Output vs. Voice Turn Concurrency Deadlock (MEDIUM)     │
└─────────────────────────────────────────────────────────────────────────────┘
```

Below is the exhaustive reverse-engineering breakdown of each failure mode, along with the precise architectural resolutions required.

---

## 2. Reverse-Engineering the Stack: Call Traces & Vulnerabilities

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          FULL VOICE-TO-CHAT TRACE                           │
└─────────────────────────────────────────────────────────────────────────────┘
  [Ingress Source: Room Satellite or Desktop Mic]
    │ 16kHz PCM audio frames streamed
    ▼
  [Rust cpal / Wyoming Ingress]
    │ ⚠️ VULNERABILITY #1: Speaker loopback captured by mic without AEC -> False Barge-In!
    │ ⚠️ VULNERABILITY #2: wyoming_agent.py uses hardcoded session_id="wyoming-{pid}"!
    ▼
  [Silero VAD v5 + CAM++ ONNX]
    │ Speech confirmed (P>0.7), Speaker Centroid matched (Cosine: 0.88, Admin)
    ▼
  [AgentStateMachine (Python Backend)]
    │ Acquires turn_lock (asyncio.Lock)
    │ ⚠️ VULNERABILITY #3: If LLM emits Markdown with code/diffs, Piper TTS reads backticks!
    │ ⚠️ VULNERABILITY #4: Two sequential LLM calls (voice + text) doubles latency to >3s!
    ▼
  [Dual-Stream Payload Splitter]
    │ Egress Stream A: Phonetic prose -> Piper TTS (Audio out)
    │ Egress Stream B: Markdown + WhyChips + DiffBlocks -> SSE Stream (GUI Timeline)
    ▼
  [Frontend: AgentChat.tsx & Tauri Desktop]
    │ Timeline appends turn with origin="satellite" | "voice_hud"
    │ ⚠️ VULNERABILITY #5: NSPanel with .nonactivatingPanel traps Esc/Space key events!
    │ ⚠️ VULNERABILITY #6: High-frequency terminal stdout floods turn lock during voice!
```

---

## 3. Deep-Dive Vulnerability Analysis & Concrete Resolutions

---

### Landmine 1: Wyoming Hardcoded Session Collision & Thread Disconnect (CRITICAL)

#### Reverse-Engineered Code:
In [`halbert_core/integrations/wyoming_agent.py:130`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/integrations/wyoming_agent.py#L130):
```python
async for event in agent.process(
    query=full_query,
    session_id=f"wyoming-{os.getpid()}", # ⚠️ CRITICAL BUG: Static session ID per process!
):
```

#### Why This Breaks:
1. **Collision across rooms:** If a user in the Kitchen and a user in the Living Room speak to two separate Wyoming satellites within the same 5-second window, both requests execute under `session_id="wyoming-12345"`. Their state contexts collide, tool executions interleave, and SSE streaming breaks.
2. **Disconnected from Continuous Conversation:** The turn is never linked to the open thread in `SqliteConversationStore` (`threads` table). When the user returns to their desktop dashboard, the conversation timeline has zero record of the voice turn!

#### Architectural Resolution:
Update `wyoming_agent.py` to mint a unique UUID per turn and query the `ThreadManager` for the currently open thread:
```python
import uuid

# In handle_transcript:
turn_id = f"turn-{uuid.uuid4().hex[:12]}"
session_id = f"wyoming-{uuid.uuid4().hex[:8]}"

# Pass thread_id from active thread manager
thread_id = self._thread_manager.get_or_open_thread_id()

async for event in agent.process(
    query=full_query,
    session_id=session_id,
    thread_id=thread_id,
    origin="satellite",
    area_id=area_id,
):
    ...
```

---

### Landmine 2: Dual-Stream Serialization & TTS Phonetic Parsing Latency (HIGH)

#### The Problem:
If we ask the LLM to generate standard Markdown and feed that directly to Piper TTS, the synthesizer produces incomprehensible audio:
* *"Backtick backtick backtick diff minus hyphen hyphen a slash etc slash hosts plus plus plus..."*
* File paths like `/var/log/journal/89a4f7...` take 10 seconds of robotic spelling.

If we attempt to solve this by making **two sequential LLM calls** (Call 1: generate spoken summary; Call 2: generate detailed Markdown), the total time-to-first-token exceeds **$3.2\text{s}$**, violating human conversational pacing.

#### Architectural Resolution: Single-Pass Tagged Delimiter Streaming
The `AgentStateMachine`'s `RESPONDING` prompt is structured to emit a strictly bounded `<speech>` block **as the very first tokens** of the response, followed immediately by the visual Markdown:

```
<speech>
The backup failed because your ZFS backup pool reached its two terabyte quota. I've staged a quota increase on your screen.
</speech>
## Incident Analysis
The scheduled tar archive process was terminated...
[WhyChip: ZFS | Quota Exceeded]
```

```
                                [ LLM Token Stream ]
                                         │
                                         ▼
                        [ Tagged Stream Demuxer (Python) ]
                         ┌───────────────┴───────────────┐
                         ▼ (<speech> tokens)             ▼ (Post-</speech> tokens)
                [ Piper TTS Synthesizer ]       [ SSE Stream to Timeline ]
                - Strips tags                   - Emits markdown chunks
                - Phonetic normalization        - Renders DiffBlocks & WhyChips
                - Audio starts in <150ms        - Renders in <50ms
```

* **Zero Latency Penalty:** Piper TTS starts generating audio from the first 20 tokens while the LLM continues generating the dense visual Markdown.
* **Clean Separation:** The GUI timeline never displays the `<speech>` tags; it displays the rich formatted Markdown and WhyChips.

---

### Landmine 3: Acoustic Loopback Self-Interruption (AEC False Barge-In) (CRITICAL)

#### The Problem:
When Halbert speaks via laptop speakers or a room satellite, the microphone captures the speaker's own acoustic output.
* Silero VAD v5 evaluates 30ms PCM chunks.
* Since TTS output has high vocal energy ($P(\text{speech}) > 0.85$), the VAD classifies Halbert's own voice as a **user barge-in interrupt**.
* The atomic cancellation token triggers, halting Piper TTS within 100ms.
* Halbert effectively "cuts itself off" after speaking 2 syllables in an infinite stuttering loop.

#### Architectural Resolution: Dual-Layer Acoustic Echo Cancellation (AEC)
1. **Rust DSP Loopback Filter (`audio_capture.rs`):**
   * Uses `webrtc-audio-processing` AEC3 in Rust.
   * Feeds the DAC playback buffer (the audio sent to speakers) as the **reference channel** into the AEC filter before passing microphone PCM to Silero VAD:
     $$\text{PCM}_{\text{clean}} = \text{AEC}(\text{PCM}_{\text{mic}}, \text{PCM}_{\text{playback\_ref}})$$
2. **Software Half-Duplex Suppression Fallback:**
   * On low-power hardware without AEC hardware acceleration, active TTS playback sets an internal state flag `is_speaking = True`.
   * Silero VAD threshold for barge-in is dynamically elevated from $P > 0.60$ to $P > 0.92$, requiring a strong, distinct near-field user voice to trigger barge-in.

---

### Landmine 4: macOS Non-Activating Panel Keyboard Traps (`tauri-nspanel`) (HIGH)

#### The Problem:
To prevent stealing focus from the user's active IDE or terminal when summoning the voice companion via `Cmd+Shift+Space`, Halbert uses macOS `NSPanel` with the `.nonactivatingPanel` style mask.
* **The Trap:** An `NSPanel` with `.nonactivatingPanel` **cannot become the key window**.
* If the user presses `Esc` (to dismiss) or `Space` (to interrupt), the key event goes directly to the background VS Code or Terminal window, potentially typing unwanted characters into active code or stopping a running shell script!

#### Architectural Resolution: Low-Level Carbon / CGEventTap Hotkey Monitor
In Rust (`src-tauri/src/floating_panel.rs`):
* When the floating HUD is visible (`state == Visible`), Rust registers a temporary, non-blocking `CGEventTap` (or macOS global key monitor).
* It exclusively intercepts `kVK_Escape` and `kVK_Space` while the panel is visible, swallows the event so it does not reach the background IDE, and dispatches the dismiss/interrupt action to Tauri.
* When the panel closes, the event tap is instantly deregistered.

---

### Landmine 5: Spoken PIN Acoustic Leakage & Multi-Occupant Security Exposure (HIGH)

#### The Problem:
Prompting a user to speak a sensitive 4-digit PIN aloud (*"Please say your PIN: Seven Four Two Nine"*) introduces significant security vulnerabilities:
1. **Acoustic Shoulder-Surfing:** Anyone in the room (or nearby microphone) overhears the admin PIN.
2. **ASR Number Confusion:** Accents, room reverberation, and ambient noise frequently cause single-digit transcription errors ("two" vs "to" vs "too", "four" vs "for"), locking out the admin.

#### Architectural Resolution: Modality Escalation Over Spoken PINs
Halbert enforces **Modality Escalation** as the default for Level 3 privileged actions:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    MODALITY ESCALATION DECISION FLOW                        │
└─────────────────────────────────────────────────────────────────────────────┘
  [ Voice Command: "Reboot server host" ]
                    │
                    ▼
     [ CAM++ Biometric Speaker Verification ]
     - Cosine Similarity: 0.94 (Admin Verified)
                    │
                    ▼
     [ Check Screen Presence in Area ]
    ┌───────────────┴───────────────┐
    ▼ (Screen Present: Desktop/Web)  ▼ (Screenless Satellite: Kitchen)
[ Visual Approval Gate ]        [ Spoken Challenge / Stash ]
- Halbert speaks:               - Halbert speaks:
  "I've staged the reboot on      "Reboot requires admin authorization.
   your screen for approval."      I've sent an approval card to your
- UI renders [ Approve & Apply ]   phone/desktop. Say 'confirm 7429' only
  with 30s countdown.              if you cannot access your screen."
```

---

### Landmine 6: Watched Terminal Stdout vs. Voice Turn Concurrency (MEDIUM)

#### The Problem:
If a watched user shell or background task outputs 10,000 lines of compiler logs while a voice turn is in progress, high-frequency SQLite writes or WebSocket event spam could block the async event loop and delay TTS audio chunk playback.

#### Architectural Resolution:
1. **Bounded Ring Buffers:** Terminal blocks buffer only `output_head` (20 lines) and `output_tail` (4KB) in memory.
2. **Decoupled Audio Priority:** Audio processing (VAD, ASR, TTS) runs in a dedicated thread pool with high CPU priority (`nice -n -5`), isolated from terminal PTY I/O.

---

## 4. End-to-End System Timing Budget

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                   TOTAL TIME-TO-FIRST-SPEECH BUDGET                         │
├─────────────────────────────────────────────────────────────────────────────┤
│ User Finishes Speaking ───────────────────────────────────────────> [ 0 ms]  │
│ Silero VAD Speech Offset Detection (Hysteresis 250ms) ───────────> [250 ms] │
│ Sherpa Zipformer Final Token Transcription ──────────────────────> [290 ms] │
│ CAM++ Speaker Centroid Verification (256-dim) ───────────────────> [295 ms] │
│ State Machine Prompt Assembly & Intake Routing ──────────────────> [310 ms] │
│ LLM Time-to-First-Token (Ollama / Claude 3.7) ───────────────────> [580 ms] │
│ Streaming Demuxer extracts `<speech>` first sentence (15 tokens) ─> [680 ms] │
│ Piper TTS VITS synthesizes first audio chunk ─────────────────────> [790 ms] │
│ Audio Output on Speaker / Satellite ─────────────────────────────> [810 ms] │
└─────────────────────────────────────────────────────────────────────────────┘
Total Latency: ~810ms (Well within the 1.0s natural conversational threshold)
```

---

## 5. Comprehensive Verification Matrix

The engineering team must validate these automated tests before rolling out Phase 5 audio AI:

| Test ID | Domain | Test Scenario | Pass Criteria | Failure Indicator |
|:---|:---:|:---|:---|:---|
| **SCRUT-01** | Networking | Wyoming satellite sends 20 concurrent voice turns from 3 distinct rooms. | Unique `session_id` per turn; all turns append to active thread in SQLite. | Turns overwrite each other; session collision error in logs. |
| **SCRUT-02** | DSP / AEC | Piper TTS plays 80dB voice audio while laptop microphone is active. | Silero VAD does NOT trigger barge-in; TTS completes smoothly. | Halbert cuts off its own speech after 1-2 words. |
| **SCRUT-03** | Latency | User interrupts active TTS playback by speaking *"Stop"*. | Playback halts in $<120\text{ms}$; ring buffer flushes cleanly. | Playback continues for $>300\text{ms}$; robotic echo audible. |
| **SCRUT-04** | Parser | LLM response contains Markdown headers, code blocks, and diffs. | TTS reads ONLY the natural phonetic prose; visual GUI renders full markdown. | Piper reads *"backtick backtick backtick"* or code diff syntax. |
| **SCRUT-05** | macOS HUD | User summons floating HUD with `Cmd+Shift+Space` and presses `Esc`. | Floating HUD dismisses; active terminal in background retains exact cursor focus. | Background terminal loses focus or receives literal `\e` keystroke. |
| **SCRUT-06** | Safety | Unenrolled guest voice asks *"Reboot host ZFS pool"*. | RoleGate blocks execution; returns Level 3 authorization requirement. | Command executes without verifying speaker role. |
| **SCRUT-07** | Quiet Hours | Anomaly detector fires advisory alert at `23:30`. | Audio remains completely silent; alert renders in Timeline only. | Proactive TTS voice chime disturbs user during quiet hours. |

---

## 6. Implementation Action Plan

1. **Step 1 (Wyoming & Concurrency Fixes):**
   * Patch `wyoming_agent.py` to mint unique `session_id` and integrate with `ThreadManager`.
   * Ensure `turn_lock` is properly released on all exception and timeout paths.
2. **Step 2 (Dual-Stream Tagged Prompting):**
   * Update `agent_prompts.py` to include `<speech>...</speech>` formatting rules for voice-originated turns.
   * Implement streaming regex demuxer in `state_machine.py`.
3. **Step 3 (Rust AEC & Floating Panel Events):**
   * Integrate `webrtc-audio-processing` in `src-tauri/src/audio_capture.rs`.
   * Implement non-activating key interceptor for `Esc`/`Space` in `floating_panel.rs`.
4. **Step 4 (Test Suite Execution):**
   * Run automated tests `SCRUT-01` through `SCRUT-07`.
