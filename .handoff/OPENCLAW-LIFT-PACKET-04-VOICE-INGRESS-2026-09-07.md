# OPENCLAW-LIFT-PACKET-04 — Typed voice ingress: speaker claims, mutation digest, TTS quality rules

**Series:** OpenClaw lift program (master plan: `OPENCLAW-LIFT-MASTER-PLAN-2026-09-07.md`)
**Source research:** `.handoff/OSS-REVIEW-OPENCLAW-2026-09-07.md` §6 (Voice mode)
**OpenClaw source of record:** `/Volumes/Thunderbolt/AI/openclaw` — `src/talk/agent-consult-runtime.ts`, `client-voice-session*.ts`, `speech-text.ts`, `tts-summary`, `fast-context-runtime.ts`
**Executor tier:** Phase A is plumbing through an existing verified path — medium scope but well-specified. Phases B–C small. Depends on PACKET-02 Phase B (claims ladder) being merged for Phase A's full value, but A1 can land first.
**Status:** READY TO DISPATCH (note the PACKET-02 dependency in A2)

---

## Objective

OpenClaw's voice review produced one structural lesson and one security-grade gap:

1. **One typed ingress**: in OpenClaw, speech reaches the agent through exactly one typed tool call — no implicit side channel exists to forget to wire. Halbert's equivalent defect was fixed by *adding* a path (the VM-STT relay), but the path that now exists carries **no identity and no modality**: a voice turn arrives at `POST /api/agent/message` as a plain text turn, `speaker_role` defaults to `"admin"`, and **RoleGate therefore treats every spoken command as the owner**. This packet gives voice turns a typed ingress: modality, speaker identity, and claim strength flow into the turn — closing the gap with PACKET-02's claims ladder.
2. **Accountability for what a voice turn did**: OpenClaw records every voice call durably with a **mutation digest** of the tool effects that happened during it. Halbert has the raw material (hash-chained audit log, write-plane tools) but no per-turn digest a user can ask about afterwards.
3. **TTS quality rules**: code-heavy replies speak a deterministic fallback line instead of garbage; long spoken segments get summarized before synthesis. Halbert has `should_speak`/`demux_response` but neither rule.

## Verified current state (do not re-derive; verified 2026-09-07)

- **The wired spoken-input path (the resolved defect — fragile, single-wired):**
  1. `audio/pipeline.py` `_speech_track_loop` (:328+) → VAD → wake word → `_process_speech_segment` → `StreamingASR.transcribe_chunk` → `SpeakerIdentifier.identify` (CAM++; **not** ECAPA-TDNN) → `VoiceTurnObservation` → `self.on_voice_turn`. **Landmine: the VAD frame size must be ≥1024 bytes (512 samples) or the whole speech path silently goes dead** (documented R9-F03/U2-14).
  2. `dashboard/app.py:1007-1036` `_relay_voice_turn` broadcasts `{"type": "transcript", "text", "speaker_name", "speaker_role", "area_id"}` over the WebRTC ingress — the transcription lands in the *browser* that sent the audio (because `/api/audio/status` deliberately never carries transcript text). **`on_voice_turn` has exactly one production setter — this relay. Removing it re-creates the dead-turn defect with no backend test failing.**
  3. Frontend: `lib/pcmCapture.ts` `PcmUplink.onTranscript` (:383) → `pages/VoiceMode.tsx:272` → `submitTurn` (:317) → `hooks/useAgentStream.ts` `agent.sendMessage` → `POST /api/agent/message` (routes/agent.py:1532).
- **The gap**: `/api/agent/message` carries no `speaker_role`/`modality`; `process()` defaults `speaker_role` to `"admin"` (state_machine.py:502); RoleGate wired at `routes/agent.py:123-127`. The identified speaker name/role reaches the UI badge but **not the agent's tool gate**. Also `build_modality_context(user_query, speaker_role)` is called without `audio_features` (state_machine.py:3151-3154), so biometric identification on the modality path is never exercised.
- **Speaker identification exists and is wired on the audio side**: `audio/speech/speaker_id.py` `SpeakerIdentifier` + `SpeakerProfileStore` (`audio/storage/speaker_store.py`); `integrations/voice_auth_gate.py` `HalbertVoiceAuthGate` (CAM++ + RoleGate) is reachable via `app_seam.get_voice_auth_gate()` / `resolve_voice_auth_gate` — but the state machine's modality path doesn't call it.
- **TTS reply path**: `state_machine.py` `_handle_responding` → `integrations/modality_wiring.py` (`build_modality_context`, `resolve_turn_modality`, `demux_response`, `should_speak`, `apply_pronunciation`) → SSE `modality_resolved`/`speech_segment` events → `_speak_to_tts_egress` (:3500+). Gate: `dashboard/routes/tts_egress.py` `TtsEgressHub` — **no `/api/audio/tts` subscriber for the session → no synthesis at all**. Engine: `HalbertVoiceBackend.get_tts()` via `haloysius.seam.get_app_seam().get_voice_backend()` (one PiperTTS per process); wake-before-speak via `system/display_power.wake`; barge-in tokens from the coordinator cancel browser playback.
- Modality resolution: `haloysius.modality.resolver.resolve_modality` with `VoicePolicy(tier=0)`, `AreaContext(multi_occupant=True)`, quiet-hours via `modality_wiring.is_quiet_hours`; channel capability via the seam (`get_audio_pipeline`); text turns pass `speaker=None` (decision 51 — "opts out of biometric risk hobble").
- `AudioPipelineCoordinator.speak()` is defined with **no caller** (pipeline.py:669 comment).
- Guest/vision/audio source-id work (N1/N2) already routes audio observations via `ownership.route_observation` before the event bus — that machinery is for *observations*, not voice *turns*; don't conflate.

## Out-of-scope guards

- Do NOT change the browser-relay architecture (transcript → browser → HTTP turn). OpenClaw's consult-tool design is for a *realtime voice model that owns turn-taking* — Halbert's architecture is browser-relayed STT and stays. What we lift is the *typed ingress discipline*, not the transport.
- Do NOT touch `VoicePolicy`/`AreaContext`/quiet-hours semantics (Haloysius-owned resolver; ratified decisions 51 etc.).
- Do NOT wire `AudioPipelineCoordinator.speak()` or `HomeCognitiveLoop` as side effects.
- Do NOT put speaker biometrics into the *auth* path for guests beyond what voice_auth_gate already defines — Phase A carries the identification result as a *claim with strength* (PACKET-02), not as an implicit role grant. If speaker verification fails or is unknown, the claim strength is what changes — never a silent default to admin.
- `EGRESS`/privacy rules stay: `/api/audio/status` never carries transcript text (deliberate).

---

## Phase A — typed voice turn ingress

**Branch:** `feat/voice-ingress` off `main`.

### Task A1: Carry modality + speaker fields from the relay into the turn

**Files:**
- Modify: `halbert_core/halbert_core/dashboard/app.py` `_relay_voice_turn` (:1007-1036)
- Modify: `halbert_core/halbert_core/dashboard/routes/agent.py` `send_message` (:1532) and the `/api/agent/message` request model
- Modify: `halbert_core/halbert_core/agents/state_machine.py` `process()` speaker_role handling (:502) and `build_modality_context` call site (:3151-3154)
- Test: `halbert_core/tests/dashboard/test_voice_ingress.py`

- [ ] **Step 1: Write the failing tests**

```python
"""A voice turn must arrive as a VOICE turn with its speaker claim — never as a
defaulted admin text turn. OpenClaw lesson: one typed ingress, no implicit
side channel that silently drops identity."""
def test_voice_turn_carries_modality_and_speaker(client, monkeypatch):
    resp = client.post("/api/agent/message", json={
        "message": "what's running on the scanner",
        "modality": "voice",
        "speaker_name": "Eric",
        "speaker_role": "member",
        "claim_source": "voice_speaker_verification",
    })
    assert resp.status_code == 200
    # assert the turn context recorded modality/voice and the speaker claim, not the admin default
    recorded = _last_turn_context(client)
    assert recorded["speaker_role"] == "member"
    assert recorded["modality"] == "voice"
    assert recorded["claim_source"] == "voice_speaker_verification"

def test_text_turn_unchanged(client):
    resp = client.post("/api/agent/message", json={"message": "hello"})
    recorded = _last_turn_context(client)
    assert recorded["modality"] == "text"
    assert recorded["speaker_role"] == "admin"  # existing default preserved for typed turns

def test_unknown_speaker_never_becomes_admin(client):
    resp = client.post("/api/agent/message", json={
        "message": "delete everything",
        "modality": "voice",
        "speaker_name": "unknown",
        "speaker_role": "unknown",
        "claim_source": "free_text_name",
    })
    recorded = _last_turn_context(client)
    assert recorded["speaker_role"] != "admin"
```

- [ ] **Step 2: Run, verify failure.**

- [ ] **Step 3: Implement.** (a) Extend the request model with optional `modality`, `speaker_name`, `speaker_role`, `claim_source` — all optional, absent = today's behavior exactly (typed turns are unchanged). (b) In `process()`, thread `modality` into the turn context alongside `speaker_role`, replacing the unconditional `"admin"` default with: explicit field if present, else `"admin"` for `text` modality, else `"unknown"` for `voice` (never a silent admin default on a voice turn). (c) In `build_modality_context`, pass the request's `speaker_role` (it already takes the parameter — verify the call site at :3151-3154 and stop hardcoding). (d) In `pcmCapture.ts`/`VoiceMode.tsx`, include the relayed `speaker_name`/`speaker_role` in `submitTurn`'s payload. (e) In `_relay_voice_turn`, keep the broadcast shape unchanged (frontend consumes it) — the claim fields already exist in it.

- [ ] **Step 4: Run, verify pass. Commit:** `feat(voice): typed voice turn ingress — modality and speaker claim carried into the turn`

### Task A2: Claim strength at the voice gate (depends on PACKET-02 Phase B)

- [ ] With `persona/claims.py` (PACKET-02) merged: map `claim_source` → `CLAIM_SOURCE_STRENGTHS` (`voice_speaker_verification` → ASSERTED, `free_text_name` → MUTABLE, absent → UNVERIFIED), attach the resulting `IdentifierClaim` to the turn context, and log the claim strength on each voice turn's audit line. RoleGate consumption (acting on the claim rather than just recording it) is **not** in this packet — recording first, enforcement is the deep pass with the permission-system work. Write one test: a voice turn with an unverified claim logs `claim_strength=unverified` and does not log the string "admin".

---

## Phase B — mutation digest per voice turn

OpenClaw records every voice call with a `ClientVoiceToolEffect` digest — evidence for "what did you just do to my files?" Halbert's equivalents already exist as ingredients: the write-plane tools (`WRITE_PLANE_TOOLS` in `persona/guest_tools.py`: `run_command`, `write_file`, `write_config`, `schedule_cron`, `terminal_blocks`) write the hash-chained audit log.

### Task B1: Turn-scoped effect digest

**Files:**
- Create: `halbert_core/halbert_core/security/turn_digest.py`
- Modify: `halbert_core/halbert_core/tools/executor.py` `execute()` — where a write-plane tool succeeds, append an effect line to the current turn's digest (turn context object attribute set in `process()`).
- Test: `halbert_core/tests/security/test_turn_digest.py`

- [ ] **Step 1: Failing tests:**

```python
from halbert_core.halbert_core.security.turn_digest import TurnDigest

def test_empty_digest_reports_nothing():
    d = TurnDigest()
    assert d.summary() == "no side effects"

def test_effects_are_counted_and_redacted():
    d = TurnDigest()
    d.record(tool="write_file", target="~/notes/plan.md")
    d.record(tool="run_command", target="systemctl status halbert")  # commands redacted to argv head only
    s = d.summary()
    assert "write_file" in s and "run_command" in s and "2 effect" in s

def test_raw_tool_args_never_enter_the_digest():
    d = TurnDigest()
    d.record(tool="write_file", target="x", raw_args={"contents": "SECRET"})
    assert "SECRET" not in d.summary()
```

- [ ] **Step 2: Implement** — `TurnDigest` holds `(tool, redacted_target)` pairs only; `redacted_target` passes through the existing `redact_text()` (`ingestion/redaction.py`) and truncates; `summary()` renders one line ("2 effects: write_file ×1, run_command ×1") plus per-effect lines. **Never raw args.**
- [ ] **Step 3:** Wire: at the start of `process()`, create a digest on the turn context; in `execute()`'s write-plane success path, `ctx.turn_digest.record(...)`; at turn finalize in `_handle_responding`, if `modality == "voice"` and digest is non-empty, emit the digest line into the spoken TTS tail AND append it to the audit log (it is already hash-chained via the write plane — this is a turn-scoped rollup, not a new audit channel).
- [ ] **Step 4:** Tests pass; run agents + tools suites. Commit: `feat(voice): per-turn mutation digest surfaced to voice replies and the audit log`

---

## Phase C — TTS quality rules (OpenClaw speech-text.ts patterns)

### Task C1: Code-heavy fallback line

**Files:**
- Create: `halbert_core/halbert_core/integrations/tts_quality.py`
- Modify: `halbert_core/halbert_core/integrations/modality_wiring.py` — in the spoken-segment selection (`should_speak` consumer path)
- Test: `halbert_core/tests/integrations/test_tts_quality.py`

- [ ] **Step 1: Failing tests:**

```python
from halbert_core.halbert_core.integrations.tts_quality import adapt_for_speech

def test_plain_text_passes_through():
    assert adapt_for_speech("The scanner is back online.") == "The scanner is back online."

def test_code_heavy_reply_gets_fallback_line():
    reply = "Here is the fix:\n```python\n" + "x = 1\n" * 30 + "```\nthats the whole change"
    spoken = adapt_for_speech(reply, fallback="I've put the detailed response on screen.")
    assert spoken == "I've put the detailed response on screen."

def test_mixed_reply_strips_fences_and_speaks_prose():
    reply = "Two things.\n```\nsome code\n```\nThat's it."
    spoken = adapt_for_speech(reply)
    assert "```" not in spoken and "Two things." in spoken
```

- [ ] **Step 2: Implement** — fenced-block ratio ≥50% of characters → return the fallback line verbatim; otherwise strip fenced/inline code and markdown noise from the *spoken* copy only (the on-screen text is untouched). Wire into the spoken-segment path in `modality_wiring` before `_speak_to_tts_egress`.
- [ ] **Step 3:** Commit: `feat(tts): code-heavy replies speak a deterministic fallback, prose is fence-stripped`

### Task C2 (recorded, defer): spoken summarization of long replies

OpenClaw summarizes long replies with the utility model before synthesis. Halbert has no utility-model slot yet (see master plan: model-picker follow-up) and founder rules require care with model routing (Tier 0/1/2). **Defer until the utility slot exists.** `adapt_for_speech`'s signature leaves a hook: a `summarizer=None` parameter.

## Verification gates (whole packet)

- `cd halbert_core && arch -arm64 ../.venv/bin/python -m pytest tests/dashboard tests/agents tests/tools tests/security tests/integrations -q` — pass; the existing voice/audio suites unaffected.
- The regression pin: a test asserting `_relay_voice_turn` remains the single `on_voice_turn` production setter and that its broadcast shape is unchanged (frontend contract).
- A typed-text turn behaves byte-identically to today (request shape without the new fields → same defaults).
- VAD frame-size landmine untouched: no changes to `pipeline.py` frame constants.

## Executor gotchas

- Same invocation rules: main checkout `cd halbert_core && arch -arm64 ../.venv/bin/python -m pytest tests/ -q`; worktrees `arch -arm64 ./wt_pytest.py`.
- The frontend is a Vite/React app under `halbert_core/halbert_core/dashboard/frontend/` — after touching `pcmCapture.ts`/`VoiceMode.tsx`, run its typecheck/build (`npm run build` or the repo's standard check) and note it in the handoff; frontend tests run separately (986 tests per the sec-branch ledger).

---

## ADDENDUM (2026-09-07, from the Hermes review — see `OSS-REVIEW-HERMES-2026-09-07.md` §7)

Hermes's voice-memo pipeline (`gateway/run_inbound.py:1335-2047`, `run_voice.py`) adds five disciplines to this packet:

1. **STT-eligible vs file-audio classification** (A1 scope note): only voice notes are auto-STT; a message attachment that happens to be audio (a song, a recording the agent should inspect as a file) is NOT transcribed on ingress — per-attachment MIME wins over message type, and the agent transcribes files itself via tool when relevant. Keep Halbert's voice-turn path distinct from any future audio-attachment path the same way.
2. **Transcribe-once, cached on the event.** The transcription result is cached on the turn's event object so every consumer (interrupt monitor, queue drain, echo) reads one STT call — never one per consumer.
3. **Echo-back for live verification.** Successful transcripts are echoed to the user (`🎙️ "…"`) so STT quality is verifiable in the moment. In Halbert this is a frontend affordance on the transcript SSE event (VoiceMode badge path already carries speaker identity; the transcript line itself is the echo).
4. **Empty/failure sentinels.** Empty transcript → a sentinel note telling the agent not to guess; failure → a neutral path-marker that never mentions STT setup (Hermes #41603: setup-advice text persisted in history and the model kept volunteering it). And the transcript is prepended as a **plain quoted line** — no wrapper phrase (a wrapper was read by the LLM as a meta-instruction).
5. **Interrupt-with-transcript, never interrupt-with-placeholder** — and duplicate-transcript suppression (SequenceMatcher ≥0.95 within a short window; VAD re-emits duplicates). Wire into A1/A2's turn handling and into any future barge-in steering (see PACKET-07).
- `speaker_id` model is CAM++ (`wespeaker_en_voxceleb_CAM++.onnx`) — NOT ECAPA-TDNN; don't "fix" that comment.
- The modality resolver and voice backend are Haloysius-owned (`haloysius.seam`, `haloysius.modality.resolver`) — fail-soft imports; never make them hard dependencies of the turn path.
- Frontend contract: `/api/audio/status` never carries transcript text (deliberate privacy rule) — the digest and speaker fields ride the agent-turn path and SSE, never the status endpoint.
- Pathspec commits; no Co-Authored-By trailers.