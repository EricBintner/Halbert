# Task Packet 07: Auditory Cortex Critical Fixes & Modality Prompt Defanging

**Target Model:** **GLM-5.3 medium** (reassigned 2026-08-30; Batch U2 — runs with REV-09/REV-03 as one ultracode workflow; the four fixes fan out cleanly)  
**Domain:** Voice AI Safety, Wyoming Protocol Integration, Text-to-Speech Preprocessing, and Prompt Delimiter Defanging  
**Target Date:** 2026-08-30  
**Status (verified 2026-08-30):** all four gaps confirmed still open in code — `wyoming_agent.py:130` still uses `session_id=f"wyoming-{os.getpid()}"` and calls `agent.process()` without `speaker_role`; `audio/speech/text_preprocessor.py` does not exist; `BargeInHandler` (in `audio/speech/barge_in.py`) is not wired into `audio/pipeline.py`; `_CONTINUITY_TAG_RE` in `agent_prompts.py:197` defangs only `<continuity>` tags, not `<speech>`.  
**Governing Documents:**
- [`documentation/design/13-adversarial-review-modality-handoff.md`](file:///Volumes/4TB-BAD/Halbert/documentation/design/13-adversarial-review-modality-handoff.md)
- [`.handoff/audio/01-CORRECTED-ARCHITECTURE.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/audio/01-CORRECTED-ARCHITECTURE.md)
- [`.handoff/MASTER-TODO.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/MASTER-TODO.md)

---

## 1. Executive Summary & Objective

An adversarial review (`13-adversarial-review-modality-handoff.md`) identified three critical vulnerabilities and gaps in the voice pipeline that must be resolved before voice features can go live:
1. **Wyoming Admin Privilege Escalation:** `wyoming_agent.py` executes voice turns with `speaker_role="admin"` by default, granting kitchen satellites full root tool access.
2. **Missing Markdown Stripper for Speech:** `tts_engine.py` passes raw markdown (`## headers`, ```` ``` ````, bullet points) to Piper TTS, causing the voice synthesizer to read formatting characters aloud.
3. **Wyoming Session ID Collision:** `session_id=f"wyoming-{os.getpid()}"` causes collisions across concurrent voice satellites.
4. **Barge-In Handler Wiring:** `BargeInHandler` is not connected to `AudioPipelineCoordinator`.

---

## 2. Detailed Task Breakdown & Implementation Steps

### Task 7.1: Fix Wyoming Speaker Role & Session ID
- **File:** [`halbert_core/halbert_core/integrations/wyoming_agent.py`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/integrations/wyoming_agent.py)
  1. Fix default speaker role: Pass `speaker_role="unknown"` (or the HA authenticated user role) into `agent.process()`.
  2. Mint a unique UUID per voice turn (`session_id=str(uuid.uuid4())`).
  3. Thread HA's incoming `conversation_id` as `thread_id` to `process()`.

### Task 7.2: Implement `strip_markdown_for_speech()` Utility
- **File:** `halbert_core/halbert_core/audio/speech/text_preprocessor.py`
  1. Implement robust markdown stripping:
     - Remove header hashes (`#`, `##`, `###`).
     - Remove code fences and inline backticks while retaining inner text.
     - Convert bullet lists to natural conversational commas/pauses.
     - Strip markdown links `[text](url)` to just `text`.
     - Strip HTML and XML tags.
  2. Wire `strip_markdown_for_speech()` into:
     - `halbert_core/halbert_core/audio/speech/tts_engine.py` before `self._tts.generate()`.
     - `wyoming_agent.py` `proactive_speak()` before sending text to Home Assistant `tts.speak`.

### Task 7.3: Wire Barge-In Handler & Speech Tag Defanging
- **File:** [`halbert_core/halbert_core/audio/pipeline.py`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/audio/pipeline.py)
  1. Instantiate `BargeInHandler` inside `AudioPipelineCoordinator`.
  2. Wire incoming VAD speech detection events to trigger `barge_in.handle_user_interruption()`.
- **File:** [`halbert_core/halbert_core/prompts/agent_prompts.py`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/prompts/agent_prompts.py)
  1. Extend `_CONTINUITY_TAG_RE` defanging to defang `<speech>` and `</speech>` tags in untrusted inputs.

---

## 3. Verification & Test Plan

1. **Audio Text Preprocessor Unit Tests:**
   ```bash
   pytest halbert_core/tests/test_text_preprocessor.py -v
   ```
2. **Wyoming Role & Session Isolation Tests:**
   ```bash
   pytest halbert_core/tests/test_wyoming_agent.py -v
   ```
3. **RoleGate Invariant Test:**
   ```bash
   pytest halbert_core/tests/test_role_gate.py -v
   ```
