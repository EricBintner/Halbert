# Review Request: Haloysius Modality & Voice Intelligence Spec

**Review Level:** **Fable Level Review**
**Domain:** Engine/Consumer Boundary Architecture, Modality Decision Logic, Voice Prosody Mapping, Speech Safety Gating, Multi-Stream Output Contracts, Multi-Consumer Alignment, Subtractive Contract Preservation
**Target Date:** 2026-08-30
**Status:** Ready for External Scrutiny — Spec Updated with Sister-App Feedback, Pre-Implementation

---

## 1. Executive Summary & Review Scope

A new specification document has been produced in the Haloysius engine
repo that defines how modality intelligence (voice vs. text, prosody,
speech safety, multi-stream output) moves from Halbert's app-specific
code into Haloysius's engine-level protocols. The spec is **documentation
only at this stage** — no engine code has been written yet. This review
request asks an external reviewer to scrutinize the spec before
implementation begins.

The spec has been informed by three inputs:

1. **Code audit of Halbert** found that Halbert has **no modality
   intelligence module**. The words `modality`, `prosody`,
   `NarratorMode`, `query_risk`, and `safe_to_speak` appear nowhere in
   the codebase. There is **no markdown stripper for speech** —
   `PiperTTS.synthesize()` feeds raw text to sherpa-onnx, so a markdown
   model response would be spoken including `## headers` and ```` ``` ````
   syntax. The `AudioPipelineCoordinator` declares a `SPEAKING` state
   but is **not wired** to the agent response stream. The only speech
   output path is `proactive_speak()` → HA `tts.speak`, which is manual.

2. **Design doc cross-check** of `11-response-modality-handoff.md`,
   `13-adversarial-review-modality-handoff.md`,
   `14-system-prompts-and-modality-gap-analysis.md`, and
   `TASK-PACKET-07-AUDITORY-CORTEX-CRITICAL-FIXES.md` found **~45
   concrete requirements** touching modality, voice, or speech. Five
   areas were uncovered by the initial spec draft and have been added:
   `VoiceAuthGate` (CAM++ biometrics), `QuietHoursPolicy` /
   `InterruptPolicy`, `DualStreamPayload` contract, input tag
   defanging, and multi-occupant privacy redaction.

3. **Sister-app review feedback** from two other Haloysius consumers
   (a companion app and an educational app — kept anonymous in this
   handoff) identified that the original bipartite
   `DualStreamPayload` (speech_text + display_text) is insufficient
   for multi-channel consumers. Companion apps emit interleaved
   dialogue/action/scene/cameo channels that need per-segment voice
   routing. The spec has been upgraded to a multipartite
   `MultiStreamPayload` with an ordered list of typed `SpeechSegment`s
   — a clean superset that serves all three consumers. See section 5
   below for details.

The reviewer should assess whether the spec is **architecturally sound,
subtractively safe, multi-consumer-aligned, and complete enough to
begin Phase 1 implementation** without discovering major gaps
mid-build.

---

## 2. Documents Under Review

| Document | Location | Purpose |
|---|---|---|
| **Spec (primary)** | [`docs/MODALITY-VOICE-SPEC.md`](file:///Volumes/4TB-BAD/Haloysius/docs/MODALITY-VOICE-SPEC.md) | 1159-line spec defining engine protocols, modality package, migration path |
| Design doc 11 | [`documentation/design/11-response-modality-handoff.md`](file:///Volumes/4TB-BAD/Halbert/documentation/design/11-response-modality-handoff.md) | Original modality handoff design (dual-stream, S/D/I/R routing, barge-in, RoleGate, quiet hours) |
| Design doc 13 | [`documentation/design/13-adversarial-review-modality-handoff.md`](file:///Volumes/4TB-BAD/Halbert/documentation/design/13-adversarial-review-modality-handoff.md) | Adversarial review (Sotto Voce, earcons, local sovereignty, CAM++ thresholds) |
| Design doc 14 | [`documentation/design/14-system-prompts-and-modality-gap-analysis.md`](file:///Volumes/4TB-BAD/Halbert/documentation/design/14-system-prompts-and-modality-gap-analysis.md) | Prompt architecture gap analysis (7-layer prompt, `<modality_context>` XML, `<speech>` contract) |
| Task packet 07 | [`.handoff/TASK-PACKET-07-AUDITORY-CORTEX-CRITICAL-FIXES.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/TASK-PACKET-07-AUDITORY-CORTEX-CRITICAL-FIXES.md) | Critical fixes (Wyoming role bug, markdown stripper, session ID, barge-in wiring) |

The spec lives in the **Haloysius** repo (`/Volumes/4TB-BAD/Haloysius/`),
not Halbert, because the modality intelligence is being added to the
engine. The design docs and task packets live in Halbert because they
describe the consumer's requirements.

---

## 3. Spec Structure (13 Sections)

| Section | Title | What It Defines |
|---|---|---|
| 1 | Problem | Why modality intelligence is currently app-specific and must move to engine |
| 2 | Design Principle | Engine decides modality + prosody; consumer executes speech + renders visual |
| 3 | New Seam Protocols | `VoiceBackend`, `ChannelCapability`, `AppSeam` extensions |
| 4 | New `modality/` Package | `types.py` (with `MultiStreamPayload`, `SpeechRole`, `VoicePolicy`), `resolver.py`, `prosody.py` (with `PersonaVoiceProfile`), `demuxer.py` (with `split_channels`, `split_stream`), `prompt_builder.py` |
| 5 | Extensions to Existing Modules | 15 subsections (5.1–5.15) covering `TurnResult`, `TemporalOrchestrator`, `NarratorMode`, `EmotionalStateV2`, `SceneContext`, `DynamicPromptBuilder`, TTS service, `VoiceAuthGate`, quiet hours, input defanging, `MultiStreamPayload`, multi-occupant redaction, `PronunciationLexicon`, multi-consumer alignment |
| 6 | Per-Turn Flow | ASCII diagram of the full turn lifecycle (multi-segment) |
| 7 | What Stays in Each Consumer | Halbert, companion apps, educational apps boundaries |
| 8 | Subtractive Contract Verification | How to verify zero-dep text-only fallback still works |
| 9 | Migration Path from Halbert | 4-phase migration with concrete file/line references |
| 10 | File Manifest | New + modified files in both repos |
| 11 | Dependencies | Zero new deps in Haloysius (subtractive contract preserved) |
| 12 | Testing Strategy | Unit, integration, consumer, multi-consumer subtractive tests |
| 13 | Open Questions | 11 open questions (3 resolved by sister-app review, 3 new from sister-app review) |

---

## 3.5 Sister-App Feedback Integration

Two other Haloysius consumers (kept anonymous in this handoff) reviewed
the spec and provided feedback that has been integrated. The key
finding was that the original `DualStreamPayload` (bipartite
speech_text + display_text) is insufficient for multi-channel
consumers. The spec has been upgraded accordingly.

### What changed in the spec

| Change | Why | Spec Section |
|---|---|---|
| `DualStreamPayload` → `MultiStreamPayload` with `List[SpeechSegment]` | Companion apps emit interleaved dialogue/action/scene/cameo channels needing per-segment voice routing. Bipartite model can't express this. | 5.12 |
| Added `SpeechRole` enum (PERSONA, NARRATOR, CAMEO, THOUGHT_ASIDE, SILENT) | Each segment needs a voice role for routing. Halbert uses PERSONA only; companion apps use all five. | 5.12 |
| Added `VoicePolicy` (tiered: Tier 0 dialogue-only, Tier 1 narrator+cameos, Tier 2 expressive+ambient) | Ships MVP voice first (Tier 0), layers narrator later. Wiring-time config, not hardcoded. | 5.12 |
| Added `ChannelMarkers` (configurable inline markdown markers) | Companion apps use `**action**`, `^scene^`, `[CAMEO]`, `//thought//`. Engine becomes single source of truth for channel parsing. | 5.12 |
| Added `VisualBlock` (mirrors frontend parseMessageBlocks) | Engine returns structured visual blocks; frontend stops re-parsing. Eliminates frontend/backend drift. | 5.12 |
| `ProsodyMapper.map()` accepts `persona_voice_profile` as base, PAD as delta | Persona's fixed speaking identity sets base prosody; PAD modulates around it. Different weightings per consumer type. | 4.3 |
| Added `PersonaVoiceProfile` dataclass | Consumer-derived base prosody (Halbert: from BeingConfig; companions: from MBTI/personality; educational: from oratorical identity). | 4.3 |
| `ProsodyHints` gains `expression_tokens` + `cadence_style` | Expression tokens for XTTS inline expressiveness (sighs, laughs). Cadence style for style-conditioning engines. | 4.1 |
| `SpeechTextDemuxer` gains `split_channels()` + `split_stream()` | Multi-channel parsing + streaming segment emission for low-latency voice. | 4.4 |
| Added `PronunciationLexicon` module | TTS mispronounces domain terms. Halbert: technical terms. Companions: world-specific names. Educational: classical terms. | 5.14 |
| `QuietHoursPolicy` gains `silence_narrator_in_whisper` | Narration at whisper volume is awkward; drop it in quiet hours. | 5.10 |
| `InterruptPolicy` gains `barge_in_segment_mode` | Multi-segment barge-in: cancel all remaining vs skip current segment. | 5.10 |
| Added multi-consumer alignment table (section 5.15) | Shows which features each consumer uses, no-ops, or partially adopts. Engine doesn't branch on consumer type. | 5.15 |
| Added multi-consumer subtractive tests | Verify Halbert-shaped, companion-shaped, educational-shaped, and pure-text consumers all work correctly. | 12 |

### What Halbert leverages from the sister apps

Halbert is the simplest consumer (Tier 0, single-channel, no narrator),
but the sister-app review produced several improvements that Halbert
benefits from:

1. **`MultiStreamPayload` is a cleaner output contract** — even with
   one segment, the segment list is more explicit than a flat
   `speech_text` string. Halbert's consumer flow is trivial: iterate
   one PERSONA segment, synthesize it.

2. **`PersonaVoiceProfile` gives Halbert persona-driven prosody** —
   Halbert's `BeingConfig.tone_descriptors` and `speech_patterns`
   now have a clear path to setting base prosody, with PAD as delta.
   This was previously implicit; now it's explicit.

3. **`expression_tokens` enables emotional acknowledgments** — Halbert
   can use expression tokens for emotional responses (a frustrated
   sigh, a confident chuckle) without narrating them.

4. **`PronunciationLexicon` fixes TTS mispronunciation** — Halbert
   deals with technical terms (service names, config paths, API
   endpoints) that Piper will mispronounce. The lexicon is shared
   infrastructure Halbert can populate from its technical term config.

5. **`split_stream()` enables low-latency voice** — Halbert's streaming
   responses can begin voice synthesis before the full response
   completes, reducing time-to-first-audio.

6. **`cadence_style` enables style conditioning** — Halbert can label
   responses as "calm", "urgent", or "measured" for engines that
   support style-level control.

### What Halbert does NOT adopt from the sister apps

- `NARRATOR` / `CAMEO` / `THOUGHT_ASIDE` speech roles (no fiction/roleplay)
- `ChannelMarkers` for inline markdown channels (uses tagged format)
- Thought/action marker split (no `**...**` convention)
- OOC channel
- Content-level-aware voice policy (SFW/romantic/nsfw)
- Ambient audio beds
- Multi-persona rooms / RoomOrchestrator
- Cameo voice registry

These are all companion-app or educational-app specific. The engine
supports them via the subtractive contract, but Halbert doesn't
register them.

---

## 4. Key Architectural Decisions to Scrutinize

The reviewer should pay particular attention to these decisions, which
represent the spec's most significant architectural claims:

### 4.1 Engine decides, consumer executes

The spec's core principle (section 2) is that the **engine** computes
modality decisions (`ModalityResolver`), prosody (`ProsodyMapper`),
speech safety (`VoiceRiskPolicy`), and prompt formatting
(`ModalityAwarePromptBuilder`), while the **consumer** only executes
speech synthesis (`VoiceBackend`) and renders visual output. The
reviewer should assess whether this boundary is clean or whether it
leaks consumer-specific concerns into the engine.

### 4.2 `ModalityResolver` decision matrix

Section 4.2 defines a decision matrix over four inputs: ingress channel
(voice/text), screen availability (present/absent), content density
(low/high), and risk level (safe/low/medium/high/critical). The matrix
produces a `ResponseModality` enum (`TEXT`, `VOICE`, `DUAL`,
`TEXT_WITH_VOICE_OFFER`). The reviewer should verify this matrix covers
all combinations correctly and matches the S/D/I/R routing in design
doc 11.

### 4.3 `ProsodyMapper` with `PersonaVoiceProfile` base + PAD delta

**RESOLVED by sister-app review.** The original spec flagged
`ProsodyMapper` as forward-looking (not design-doc-backed). The
sister-app review confirmed that all three consumers need PAD-driven
prosody, and additionally need a persona-driven base. The spec now
defines `ProsodyMapper.map(..., persona_voice_profile=...)` with a
weighting parameter: Halbert (50% base / 50% PAD), companion apps
(40% / 60%), educational apps (70% / 30%). The reviewer should assess
whether this weighting model is sound and whether the
`PersonaVoiceProfile` dataclass is the right abstraction for
consumer-derived base prosody.

### 4.4 Graduated risk gating replaces binary `should_speak()`

Section 5.8 replaces the original binary `should_speak()` (speak for
SAFE/LOW, text-only for HIGH/CRITICAL) with a graduated
`VoiceRiskPolicy` that allows speaking a brief warning at HIGH risk
before deferring details to text/screen. This was driven by design doc
11 section 3, which requires speaking a warning then gating the action
in UI. The reviewer should verify this doesn't create a security gap
where sensitive information leaks through the spoken warning.

### 4.5 `VoiceAuthGate` extends `GovernancePolicy`, not a new seam

Section 5.9 defines `VoiceAuthGate` as a Protocol that extends the
existing `GovernancePolicy.authorize_action()` flow rather than
creating a new seam. The reviewer should assess whether CAM++
biometric thresholds (0.82 admin, 0.70 member, 0.60–0.69 PIN, <0.60
block) belong in the engine protocol definition or in the consumer
implementation. The spec defines the thresholds in the protocol docstring
but the consumer implements them.

### 4.6 `MultiStreamPayload` vs streaming

**RESOLVED by sister-app review.** The spec now defines
`SpeechTextDemuxer.split_stream()` as an async generator that yields
`SpeechSegment`s as channel boundaries are detected mid-token-stream.
The consumer synthesizes each segment as it arrives for low-latency
voice. The final `MultiStreamPayload` is assembled from accumulated
segments at turn completion. The reviewer should assess whether this
dual (streaming + final) approach is sound and whether the async
generator interface is the right abstraction for the engine.

### 4.7 `MultiStreamPayload` superset design (NEW from sister-app review)

The spec upgrades `DualStreamPayload` to `MultiStreamPayload` with a
segment list. This is a clean superset: text-only consumers ignore
`segments` and render `display_text`; simple voice consumers (Halbert)
use the bipartite `speech_text` field (derived from segments); multi-
channel consumers iterate `segments` with per-segment voice routing.
The reviewer should verify:
- The superset is truly backward-compatible (text-only behavior
  unchanged)
- The bipartite fields (`speech_text`, `display_text`) are correctly
  derived from the segment list
- The `VoicePolicy` tier system doesn't leak complexity into Tier 0
  consumers
- The `ChannelMarkers` config is sufficient for companion-app inline
  formats without requiring engine knowledge of specific marker
  conventions

### 4.7 Subtractive contract preservation

Section 11 claims zero new dependencies in Haloysius. The entire
`modality/` package is stdlib-only. The `VoiceBackend` protocol is
structural (`Protocol`, not ABC) so it adds no import cost. The
reviewer should verify this claim by tracing every import in the
proposed new modules. The existing subtractive contract test
(`test_thin_consumer.py`) should still pass after implementation.

---

## 5. Known Gaps & Open Questions

The spec documents 11 open questions (section 13). Three were resolved
by sister-app review, three are new from sister-app review. The
reviewer should assess whether any are **blocking** for Phase 1:

**Resolved by sister-app review:**
- ~~`ProsodyMapper` scope~~ → confirmed required, now has `PersonaVoiceProfile` base
- ~~`DualStreamPayload` vs streaming~~ → `split_stream()` async generator defined
- ~~`ModalityPolicy` struct~~ → `VoicePolicy` dataclass at wiring time

**New from sister-app review:**
9. **Thought/action marker split** — companion-app format change (not Halbert)
10. **Structured output vs inline markdown** — future improvement, not blocking
11. **Cameo voice registry** — consumer-owned, engine emits `character_name` + `cameo_id`

**Still open:**
1. **Voice selection policy** — engine vs consumer sets `voice_id`
2. **Streaming prosody** — compute once per turn vs adapt mid-sentence
3. **Multi-language** — markdown stripping locale awareness
7. **Earcons vs TTS** — needs `EarconBackend` protocol
8. **`thread_id` continuity** — consumer-specific wiring

Additionally, the design doc cross-check identified areas the spec does
**not** cover (these are intentionally out of scope for the engine):

- **Frontend UI components** (`AcousticAura.tsx`,
  `VoiceCompanionPill.tsx`, `ModalityHandoffBadge.tsx`,
  `AcousticEventCard.tsx`) — these stay in Halbert
- **Rust desktop audio capture** (`audio_capture.rs`, cpal,
  webrtc-audio-processing) — consumer-specific hardware
- **macOS NSPanel + CGEventTap** for floating HUD — consumer OS integration
- **`rolegate_audit_log` persistence** — consumer storage
- **Wyoming protocol integration** (`ThreadManager` injection,
  `conversation_id` threading) — consumer ingress adapter

The reviewer should confirm these exclusions are correct.

---

## 6. Audit Methodology Used

The spec was produced by two parallel background audits:

### 6.1 Code audit (Halbert)

A read-only subagent audited `/Volumes/4TB-BAD/Halbert/halbert_core/`
across 7 categories: modality/prosody logic, proactive speech
scheduling, TTS engine wrapping, emotional state usage, scene context,
markdown stripping, and NarratorMode/query risk. For each finding it
reported file path, line range, behavior, MOVE/STAY recommendation, and
spec section mapping. Key findings:

- **No modality intelligence exists** — the words `modality`, `prosody`,
  `NarratorMode`, `query_risk` appear nowhere
- **No markdown stripper for speech** — `PiperTTS.synthesize()` feeds
  raw text to sherpa-onnx
- **`AudioPipelineCoordinator.SPEAKING` state is unwired** — no path
  from `response_complete` to TTS playback
- **`ProactiveGate.should_notify()`** in `proactive/gate.py` is the
  closest thing to temporal modality gating — should move to
  `TemporalOrchestrator`
- **`personality_prompt.py`** injects `TONE`/`SPEECH PATTERNS`/
  `VOICE PRESENTATION` directly into prompts — should move to
  `ModalityAwarePromptBuilder` with modality-conditional application

### 6.2 Design doc cross-check

A read-only subagent read all four design documents and extracted ~45
concrete requirements, classifying each by category and mapping to spec
sections. It identified 5 uncovered areas that were then added to the
spec as sections 5.8–5.13.

### 6.3 Sister-app review feedback

Two other Haloysius consumers reviewed the spec and provided detailed
feedback. Their review is at:
`/Volumes/4TB-BAD/Haloysius/.handoff/REVIEW-FEEDBACK-HALLEY-VOICE-MULTICHANNEL.md`

Key findings integrated into the spec:
- `DualStreamPayload` → `MultiStreamPayload` with segment list
- `SpeechRole` / `SpeechSegment` / `VisualBlock` types
- `VoicePolicy` (tiered) at wiring time
- `ProsodyMapper` with `PersonaVoiceProfile` base + PAD delta
- `expression_tokens` + `cadence_style` in `ProsodyHints`
- `PronunciationLexicon` module
- `split_channels()` + `split_stream()` in `SpeechTextDemuxer`
- `QuietHoursPolicy.silence_narrator_in_whisper`
- Multi-consumer alignment table (section 5.15)

The full audit outputs are available in the conversation history at:
`/Users/ericbintner/.local/share/devin/cli/summaries/history_3b21304c8d0e455f.md`

---

## 7. Review Directives

The reviewer (Fable) should address these specific questions:

### 7.1 Architectural soundness

- Is the engine/consumer boundary clean? Does any consumer-specific
  concern leak into engine protocols?
- Is `ModalityResolver` the right abstraction, or should modality
  decisions be distributed across `NarratorMode`, `TemporalOrchestrator`,
  and `SceneContext` instead of centralized?
- Should `VoiceAuthGate` be a new seam or an extension of
  `GovernancePolicy`? The spec chooses the latter — is this correct?
- Is `MultiStreamPayload` with segment list the right output contract?
  Does the superset design (segments + bipartite fields) create
  redundancy or confusion?
- Does the `VoicePolicy` tier system leak Tier 1+ complexity into
  Tier 0 consumers (Halbert)?

### 7.2 Subtractive contract

- Trace every proposed import in `modality/types.py`,
  `modality/resolver.py`, `modality/prosody.py`, `modality/demuxer.py`,
  `modality/prompt_builder.py`, `modality/pronunciation.py`. Confirm
  all are stdlib.
- Confirm `VoiceBackend`, `ChannelCapability`, `VoiceAuthGate` are
  `Protocol` (structural) not `ABC` (imported).
- Confirm that `pip install haloysius` with no extras still produces
  text-only behavior identical to current.
- Verify the `MultiStreamPayload` segment list is additive — a
  text-only consumer that ignores `segments` and renders
  `display_text` gets identical behavior to today.
- Verify `VoicePolicy`, `ChannelMarkers`, `PersonaVoiceProfile` are
  all optional (default to no-op / empty / None).

### 7.3 Security

- Does graduated `VoiceRiskPolicy` (speak warning at HIGH, defer details)
  create a path for sensitive information to leak through speech?
- Is input tag defanging (section 5.11) sufficient to prevent prompt
  injection via `<speech>` tags in user messages?
- Is multi-occupant privacy redaction (section 5.13) sufficient, or
  does it need to redact more than passwords/tokens/IPs/paths?
- Does `VoiceAuthGate` with CAM++ thresholds create a bypass where a
  confident impersonator (0.71 cosine) gets member access?
- Does the `ChannelMarkers` config create an injection vector where
  a consumer's marker config could conflict with model output in
  unexpected ways?

### 7.3.5 Multi-consumer alignment (NEW from sister-app review)

- Does the multi-consumer alignment table (section 5.15) correctly
  capture which features each consumer uses, no-ops, or partially
  adopts?
- Does the engine truly avoid branching on consumer type? Verify
  that all consumer-specific behavior flows through registered
  protocols and wiring config, not through `if consumer_type ==`
  checks.
- Is the `PersonaVoiceProfile.weight` parameter (50% Halbert / 40%
  companion / 70% educational) a sound model, or should the
  weighting be fixed per-consumer-type rather than configurable?
- Are the multi-consumer subtractive tests (section 12) sufficient
  to verify all three consumer shapes work correctly?

### 7.4 Completeness

- Are there requirements in design docs 11/13/14 or TASK-PACKET-07 that
  are still uncovered after sections 5.8–5.15 were added?
- Are there requirements from the sister-app review that are still
  uncovered?
- Is the migration path (section 9) concrete enough to execute, or are
  there missing steps?
- Are the 11 open questions (section 13) correctly classified as
  non-blocking for Phase 1?

### 7.5 Testability

- Does the testing strategy (section 12) cover every protocol and
  decision matrix cell?
- Is the subtractive contract test sufficient to catch dependency
  regressions?
- Are there integration test scenarios missing (e.g., streaming
  multi-stream, earcon selection, voice PIN challenge flow,
  multi-channel segment parsing, pronunciation lexicon)?
- Are the multi-consumer subtractive tests sufficient to verify all
  three consumer shapes (Halbert, companion, educational)?

---

## 8. Verification Commands

The spec is documentation-only. No code has been written. The reviewer
can verify the current state:

```bash
# Confirm Haloysius tests pass (baseline before implementation)
cd /Volumes/4TB-BAD/Haloysius
python -m pytest src/ -q

# Confirm no modality code exists yet in Haloysius
ls src/haloysius/modality/ 2>/dev/null  # Should not exist

# Confirm no modality code exists in Halbert
cd /Volumes/4TB-BAD/Halbert
grep -r "modality\|prosody\|NarratorMode\|query_risk" halbert_core/ --include="*.py" -l
# Should return no results

# Confirm the spec file exists and is well-formed
wc -l /Volumes/4TB-BAD/Haloysius/docs/MODALITY-VOICE-SPEC.md
grep -c "^##\|^###" /Volumes/4TB-BAD/Haloysius/docs/MODALITY-VOICE-SPEC.md
```

---

## 9. Expected Review Output

The reviewer should produce:

1. **Verdict:** APPROVED / APPROVED-WITH-CONDITIONS / REJECTED
2. **Blocking issues** (must resolve before Phase 1 implementation)
3. **Non-blocking recommendations** (should address during implementation)
4. **Uncovered requirements** (if any design doc requirements are still missing)
5. **Subtractive contract assessment** (confirmed safe / violations found)
6. **Security assessment** (risk gating, input defanging, biometric thresholds)
7. **Open question dispositions** (which of the 8 can be deferred, which must be resolved)

---

## 10. Post-Review Next Steps

Upon APPROVED or APPROVED-WITH-CONDITIONS:

1. Resolve any blocking issues in the spec
2. Begin Phase 1 implementation in Haloysius:
   - Add `VoiceBackend`, `ChannelCapability`, `VoiceAuthGate` protocols
     to `seam.py`
   - Build `modality/` package (5 modules + types, all stdlib)
   - Extend `TurnResult`, `TemporalOrchestrator`, `NarratorMode`
   - Upgrade `services/tts/` to `VoiceBackend` reference impl
   - Write unit + subtractive contract tests
3. Verify Haloysius test suite still passes (currently 417 passed, 2
   pre-existing failures unrelated to this work)
4. Proceed to Phase 2: Halbert consumer wiring
