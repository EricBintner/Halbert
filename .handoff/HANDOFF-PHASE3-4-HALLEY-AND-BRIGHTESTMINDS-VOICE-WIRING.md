# Handoff: Modality-Voice Phase 3 & 4 — Halley and BrightestMinds Consumer Wiring

**Date:** 2026-08-31
**Status:** Ready for consumer-side implementation
**Originating Work:** Halbert Phase 2 (commit `0a2c3dfd` on `feat/modality-voice-phase2`) + Haloysius Phase 1 engine (branch `worktree-modality-voice-phase1`)

> **Per-app handoffs split from this document:**
> - **Halley (Phase 3):** `PHASE3-HALLEY-VOICE-WIRING-HANDOFF.md` — detailed wiring tasks, code sketches, verification, risks
> - **BrightestMinds (Phase 4):** `PHASE4-BRIGHTESTMINDS-VOICE-WIRING-HANDOFF.md` — detailed wiring tasks, code sketches, verification, risks
>
> The per-app files are the authoritative handoffs for each consumer team. This
> combined document remains as the cross-consumer overview and verification matrix.

---

## 1. What's Done

### Phase 1: Haloysius Engine (complete)
- **Branch:** `worktree-modality-voice-phase1` at `/Volumes/4TB-BAD/Haloysius/.claude/worktrees/modality-voice-phase1/`
- **Spec:** `docs/MODALITY-VOICE-SPEC.md` (1600 lines)
- **Modules built:** `modality/types.py`, `modality/resolver.py`, `modality/prosody.py`, `modality/demuxer.py`, `modality/pronunciation.py`, `modality/prompt_builder.py`
- **Seam extensions:** `VoiceBackend`, `ChannelCapability`, `VoiceAuthGate`, `SpeakerIdentity`, `EarconBackend` protocols in `seam.py`
- **Blocks resolved:** B1 (asymmetric channel markers), B2 (life-safety bypass advisory-only), B3 (import-scan as canonical §8 check), B4 (voice-id precedence), B5 (barge-in consumer-defined), B6 (staged_actions schema), B7 (cross-channel secret leak)
- **Tests:** 635 engine tests + 62,208 life-safety probe combinations in `src/haloysius/modality/tests/`

### Phase 2: Halbert Consumer Wiring (complete)
- **Branch:** `feat/modality-voice-phase2` at `/Users/ericbintner/.config/superpowers/worktrees/Halbert/modality-voice-phase2/`
- **Commit:** `0a2c3dfd` — 13 files, 2199 insertions
- **Voice accessors:** `voice_backend.py`, `channel_capability.py`, `voice_auth_gate.py` (all lazy-import the engine, subtractive-safe)
- **Per-turn modality flow:** `modality_wiring.py` — `build_modality_context()`, `resolve_turn_modality()`, `defang_user_input()`, `demux_response()`, quiet hours (22:00-07:00), life-safety bypass
- **State machine wiring:** `_handle_responding()` resolves modality, defangs input, demuxes response, emits `modality_resolved` + `speech_segment` SSE events
- **TASK-07 fixes:** Wyoming agent (unique session_id, conversation_id threading, markdown stripping, fixed relative import bug), pipeline barge-in
- **Frontend:** `ModalityHandoffBadge.tsx`, `VoiceCompanionPill.tsx`, `useAgentStream.ts` event handlers
- **Tests:** 40 passed, 9 skipped (engine not installed in worktree), 0 regressions

### Phase 2.5: Halbert Refactor (partially done)
The following Phase 3 Halbert items were already completed during Phase 2:
- `wyoming_agent.py`: markdown stripping, `speaker_role="unknown"`, unique per-turn session_id

---

## 2. What's Left for Halbert (Phase 2.5 continued)

These items remain in the Halbert worktree and are being addressed in the current session:

| Item | File | What |
|------|------|------|
| 1 | `prompts/agent_prompts.py:697` | Remove hardcoded `"use markdown formatting"` — replace with modality-conditional formatting via `ModalityAwarePromptBuilder` |
| 2 | `persona/personality_prompt.py:38-87` | Remove `TONE`/`SPEECH PATTERNS`/`VOICE PRESENTATION` prompt injection — moved to engine prompt builder, applied conditionally per modality |
| 3 | `proactive/gate.py` | Remove `ProactiveGate.should_notify()` — replaced by `TemporalOrchestrator.should_speak_proactively()` with `QuietHoursPolicy` |
| 4 | `proactive/morning_report.py` | Remove `ProactiveGate` consultation — scheduling moves to `TemporalOrchestrator` |
| 5 | `dashboard/app.py` | Move cron scheduling decisions to `TemporalOrchestrator`; keep task registration as thin consumer hook |
| 6 | Pronunciation lexicon | Populate `PronunciationLexicon` with Halbert domain terms (service names, config paths, API endpoints) |

---

## 3. Phase 3: Halley Companion Consumer Integration

**Target repo:** `/Volumes/4TB-BAD/HumanAI/LinuxBrain/`
**Governing document:** `/Volumes/4TB-BAD/Haloysius/.handoff/REVIEW-FEEDBACK-HALLEY-VOICE-MULTICHANNEL.md`

### 3.1 Context

Halley is a local-first AI companion app with roleplay worlds. It uses a **four-channel interleaved stream** (dialogue / action / scene / cameo) that the bipartite `DualStreamPayload` could not express. The spec was upgraded to `MultiStreamPayload` with typed `SpeechSegment`s based on Halley's feedback.

### 3.2 Tasks

1. **Format Convention Split:**
   - Update `parseMessageBlocks.ts` and `FormatHelpDialog.tsx` to split thoughts into `//thought//` (or `<<thought>>`) distinct from `**action**`
   - Update `MessageBlockRenderer.tsx` with distinct internal monologue styling
   - Add `((OOC))` channel rendered as dimmed marginalia (`SpeechRole.SILENT`)

2. **Multi-Channel Pipeline Wiring:**
   - Implement `VoiceBackend` wrapping XTTS-v2 / local neural TTS with persona reference latents
   - Implement `ChannelCapability` for mobile Bluetooth / web / desktop ingress
   - Wire `VoicePolicy` starting at Tier 0 (dialogue-only), layering Tier 1 (narrator voice) and Tier 2 (expressive tokens)
   - Feed `VisualBlock`s directly from `MultiStreamPayload` to frontend to eliminate regex parsing drift
   - Configure world-scoped `PronunciationLexicon` in `persona/worlds.py`
   - Wire `QuietHoursPolicy` with `silence_narrator_in_whisper = True`
   - Derive `PersonaVoiceProfile` from MBTI/personality config (40% base / 60% PAD)

3. **Cameo Voice Registry:**
   - Build consumer-owned cameo voice registry
   - Engine emits `character_name` + `cameo_id`; consumer maps to voice model

4. **Ambient Audio Beds (Tier 2):**
   - Scene-level ambient audio for immersion
   - Consumer-side `EarconBackend` implementation

### 3.3 Key Architecture Decisions

- **Prosody weighting:** 40% personality base / 60% dynamic PAD (Halley is emotion-driven)
- **Channel markers:** `**action**`, `^scene^`, `[CAMEO]`, `//thought//`, `((OOC))`
- **Voice policy tier progression:** Ship Tier 0 first (dialogue-only), layer narrator (Tier 1) and expressions (Tier 2)
- **Thought/action split:** Actions are narratable; thoughts are private/internal (`SpeechRole.SILENT`)
- **Sotto Voce:** -12dB whisper for nighttime, narrator silenced in whisper mode

### 3.4 Verification

```bash
cd /Volumes/4TB-BAD/HumanAI/LinuxBrain
# Run Halley's test suite after wiring
# Verify multi-channel segment parsing
# Verify //thought// is silent, **action** is narrated
# Verify ((OOC)) is silent
# Verify cameo voice routing
# Verify quiet hours + silence_narrator_in_whisper
```

---

## 4. Phase 4: BrightestMinds Consumer Integration

**Target repo:** `/Volumes/4TB-BAD/BrightestMinds/`
**Governing document:** `/Volumes/4TB-BAD/Haloysius/.handoff/REVIEW-REQUEST-BRIGHTESTMINDS-VOICE-SPEC.md`

### 4.1 Context

BrightestMinds is a historical philosophy chat app with Gutenberg RAG grounding. It features multi-figure symposia (e.g., Socrates + Plato debating), historical persona prosody, and classical pronunciation requirements.

### 4.2 Tasks

1. **RAG Citation & Pronunciation Integration:**
   - Provide `CitationRewriter` callable to `SpeechTextDemuxer` to convert `[Gutenberg #...]` markers into spoken attributions ("As I wrote in Poor Richard's Almanack...")
   - Connect `MultiStreamPayload.citations` to frontend `Citations.tsx` source cards
   - Populate `PronunciationLexicon` with classical Latin, Ancient Greek, and archaic English terms

2. **Historical Voice & Prompt Wiring:**
   - Implement `VoiceBackend` for browser WebRTC / Web Audio API
   - Implement `ChannelCapability` for browser ingress
   - Wire `PersonaVoiceProfile` with 70% oratorical base / 30% PAD delta
   - Close the `DynamicPromptBuilder` bypass so historical figures reach `ModalityAwarePromptBuilder`
   - Wire `RoomOrchestrator.compute_reply_jobs()` with sequential voice playback for multi-figure symposia
   - Set `VoicePolicy` Tier 0 -> Tier 1 (narrator for lectures, figure cameos)

3. **Symposia Multi-Figure Voice:**
   - `RoomOrchestrator` sequences turns across multiple historical figures
   - Each figure gets distinct `PersonaVoiceProfile` (oratorical base varies per era/style)
   - `((OOC))` meta channel for instructor interventions (`SpeechRole.SILENT`)

### 4.3 Key Architecture Decisions

- **Prosody weighting:** 70% oratorical base / 30% PAD (historical figures have strong fixed speaking identity)
- **No biometric auth:** Open educational dialogue, no `VoiceAuthGate`
- **No quiet hours:** Normal playback at all hours
- **No barge-in at stream level:** Segment-level cancellation only (educational pacing)
- **Citation routing:** `CitationRewriter` transforms RAG citations for spoken output
- **Pronunciation scope:** Classical terms (Latin, Ancient Greek, archaic English)

### 4.4 Verification

```bash
cd /Volumes/4TB-BAD/BrightestMinds
# Run BrightestMinds test suite after wiring
# Verify [Gutenberg #...] citations are rewritten for speech
# Verify classical pronunciation lexicon substitutions
# Verify multi-figure symposia voice sequencing
# Verify ((OOC)) is silent
# Verify PersonaVoiceProfile oratorical base weighting
```

---

## 5. Cross-Consumer Verification

After all three consumers are wired, run the multi-consumer subtractive tests from the spec (section 12):

| Consumer Shape | VoiceBackend | VoicePolicy | ChannelMarkers | Expected Behavior |
|---|---|---|---|---|
| Pure text | None | N/A | N/A | All modality fields `None`, `display_text` only |
| Halbert (Tier 0) | Piper | Tier 0 | None | Single PERSONA segment, 35-word cap, CAM++ gate, credential redaction |
| Halley (Tier 1-2) | XTTS | Tier 1-2 | Configured | Multi-channel segments, narrator + cameos, thoughts silent, no credential redaction |
| BrightestMinds (Tier 1) | WebRTC | Tier 1 | Scholar's Script + OOC | Multi-figure symposia, citation rewrite, classical lexicon |

---

## 6. Engine Branch Merging

The Haloysius Phase 1 engine work is on `worktree-modality-voice-phase1` and needs to be merged to `main` before the consumer apps can pull it as a dependency. The engine worktree is at:

```
/Volumes/4TB-BAD/Haloysius/.claude/worktrees/modality-voice-phase1/
```

Once merged, each consumer app can `pip install -e /Volumes/4TB-BAD/Haloysius` to get the modality engine.

---

## 7. Open Questions (from spec section 13)

These are non-blocking for consumer wiring but should be resolved during implementation:

1. **Voice selection policy** — engine vs consumer sets `voice_id` (recommendation: consumer default, engine override for scene-specific)
2. **Streaming prosody** — compute once per turn vs adapt mid-sentence
3. **Multi-language** — markdown stripping locale awareness
4. **Earcons vs TTS** — needs `EarconBackend` protocol (defined in spec, not yet implemented)
5. **`thread_id` continuity** — consumer-specific wiring
6. **Thought/action marker split** — Halley consumer-side format change
7. **Structured output vs inline markdown** — future improvement
8. **Cameo voice registry** — consumer-owned, engine emits `character_name` + `cameo_id`
