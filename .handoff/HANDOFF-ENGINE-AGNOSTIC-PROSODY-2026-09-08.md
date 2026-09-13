# HANDOFF: the reference TTS layer can now host an engine that is not Piper

**Date:** 2026-09-08
**From:** Haloysius (engine)
**To:** Halley, BrightestMinds, Halbert — one copy in each `.handoff/`
**Resolves:** the engine-side item in Halley's `HANDOFF-TO-HALOYSIUS-LICENSING-CORRECTIONS-2026-09-02.md` §6 — "`TTSRequest` has no field for `expression_tokens` / `cadence_style` / whisper; they are dropped at the adapter boundary before any engine sees them."
**Landed:** `voice_backend.py`, `service.py`, `services/tts/__init__.py`; 26 new tests, the pre-existing 35 prosody tests unchanged in intent; `TTSRequest` still frozen per spec §5.7.

---

## 0. In one paragraph

Before today the engine's *reference* TTS path could only ever drive Piper. The seam
(`VoiceBackend.synthesize(text, prosody)`) always carried the full `ProsodyHints`, but
everything under it — the service, the adapter, the request — was Piper-only by
construction, so the expression tokens the demuxer produces (`sigh`, `laugh`, `gasp`…)
reached no engine at all, and no other engine could be routed to. Both Halley and
BrightestMinds go through that layer. Three small, additive changes fix it: the
adapter-local request now carries the whole hints object; a generic backend wraps any
`TTSEngine`; the service routes prosody to any registered engine by name. A pure helper
renders the shared expression vocabulary into each real engine's inline syntax. Nothing
changes for Piper — its projection of the request is byte-identical. Reference engines
(Kokoro, Chatterbox) are deliberately **not** shipped yet; see §5.

---

## 1. Why — what the research established first

Halley's critique of the licensing escalation was, at root, that Haloysius had acted
without understanding what Halley *is*. So this time the purpose came first:

| App | What it is | What its voice must do (its own docs + the spec table) |
| :--- | :--- | :--- |
| **Halley** | Local-first AI companion; personas that believe they are human; "companionship, not surveillance" | One distinct voice per persona; local and free (must); cloning (nice-to-have); **`expression_tokens` required** — sighs, laughs, whispers; `cadence_style` intimate / teasing / contemplative; whisper via quiet hours |
| **BrightestMinds** | Historical-figure conversation, educational | Per-figure voices; oratorical cadence and contemplative pacing (`rate`); classical pronunciation (lexicon, separate); expression **no-op** |
| **Halbert** | Sysadmin assistant, one mind in several bodies | Tier-0 dialogue; life-safety alarms; its own sherpa-onnx `VoiceBackend`; expression optional |

Against that, the finding was structural, not a missing field:

1. `TTSService._prosody_backend_for()` hard-coded `"piper"` — any other registered engine returned `None`.
2. `prosody_to_request()` emitted a `ProsodyTTSRequest` carrying only Piper's `noise_scale`; a test pinned the expressive fields as dropped.
3. `TTSService.synthesize(text, voice_id, speed)` — and Halley's verbatim copy of it — could carry nothing else.

Halley's `HalleyVoiceBackend` receives every field at the seam and then calls (3).
BrightestMinds calls `synthesize_with_prosody`, which hits (1) and (2). The critique was
correct and understated.

---

## 2. What changed (the contract)

**A. The request carries the whole hints.**
```python
@dataclass
class ProsodyTTSRequest(TTSRequest):        # TTSRequest itself: still text / voice_id / speed
    noise_scale: Optional[float] = None    # Piper's, as before
    prosody: Optional[ProsodyHints] = None # NEW — everything, for engines that can use it
```
Piper reads `text`, `voice_id`, `speed`, `getattr(request, "noise_scale")` and nothing
else; that projection is unchanged and tested. An engine that can do more reads
`request.prosody` defensively (`getattr(request, "prosody", None)`), exactly the pattern
spec §5.7 already prescribed for extras.

**B. Any engine, routed by name.**
```python
from haloysius.services.tts import TTSService, EngineVoiceBackend

service = TTSService(config)
service.register_engine("chatterbox", MyChatterboxEngine(...))   # any TTSEngine subclass
result = await service.synthesize_with_prosody(text, prosody, engine="chatterbox")
service.cancel(engine="chatterbox")                               # barge-in
```
`EngineVoiceBackend(engine)` is the generic seam adapter (satisfies `VoiceBackend`);
`PiperVoiceBackend` is now its Piper specialisation, kept by name. An engine that is not
registered still degrades to `None` — nothing is wrapped speculatively.

**C. Rendering the shared vocabulary.**
```python
from haloysius.services.tts import render_expression_tokens, EXPRESSION_STYLES
render_expression_tokens(["sigh", "laugh"], "orpheus")  # "<sigh> <laugh>"
render_expression_tokens(["sigh", "laugh"], "dia")      # "(sighs) (laughs)"
render_expression_tokens(["sigh"], "none")              # ""
```
Styles: `orpheus`, `dia`, `bracket`, `none`. A token with no documented tag in that
engine is **dropped, never guessed** — an invented tag is read aloud as text. `whisper`
is never rendered: it is a mode on `ProsodyHints.whisper`, not a sound. Placement is the
adapter's decision; this only decides spelling.

---

## 3. Engine capability map (verified 2026-09-08)

How each `ProsodyHints` field lands on the engines that are actually on the table.

| | Piper | Kokoro-82M | Chatterbox | Orpheus | Dia |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Licence (code / weights) | MIT / per-voice | Apache-2.0 | MIT | Apache-2.0 | Apache-2.0 |
| Size | tiny, CPU | 82M, CPU | 0.5B | 3B (Llama-based) | 1.6B |
| `rate` | `speed` | `speed` (0.1–5×) | ≈ `cfg_weight` (lower = slower) | — | — |
| `energy` | `noise_scale` | — | **`exaggeration`** (0.25–2, default 0.5) | — | — |
| `expression_tokens` | ignored | ignored | ignored (no tags) | `<laugh> <sigh> <gasp> <groan> <yawn>` | `(laughs) (sighs) (gasps) (groans) (humming)` |
| `voice_id` | model file | named voice | **reference clip** (`audio_prompt_path`) | reference clip | reference clip / speaker tag |
| `whisper` | — | — | — | — | — |
| Notes | reference impl | best quality-per-byte | zero-shot cloning; **Perth watermark in every output**; MPS in code, Linux-only tested | tags cover the demuxer vocabulary almost exactly; heavy | dialogue-shaped |

Two consequences worth stating plainly:

- **No engine has a whisper mode.** The spec already degrades whisper to low `volume` /
  low `energy` (night + interior). For cloning engines the honest implementation is a
  *second, whispered reference clip per voice* — a voice-profile design decision for
  Halley, not an engine flag.
- **`expression_tokens` only render on Orpheus/Dia.** On Chatterbox the equivalent
  lever is `exaggeration` driven by `energy`/PAD. The demuxer's vocabulary and the
  hints are engine-neutral; the *mapping* is per engine, and now has somewhere to live.

---

## 4. What each app should do

### Halley
1. **Route through the prosody path.** `HalleyVoiceBackend.synthesize` currently calls
   your copied `TTSService.synthesize(text, voice_id, engine, speed)`, which cannot carry
   hints. Either call the engine's `synthesize_with_prosody(text, prosody, engine=...)`
   (as BrightestMinds does) or mirror `register_engine` / `_prosody_backend_for` into
   your copy — the diff is small and the tests in
   `services/tts/tests/test_engine_agnostic_prosody.py` are the spec.
2. **Register the engine your spike picks** with `register_engine`; in its `synthesize`,
   read `request.prosody` and map per §3. For Chatterbox: `energy → exaggeration`,
   `rate → cfg_weight` (inverse-ish; calibrate), `voice_id → audio_prompt_path`.
3. **Render tokens** with `render_expression_tokens(prosody.expression_tokens, style)`
   only for an engine with a `style`; for Chatterbox fold them into `exaggeration`
   instead of rendering.
4. **Whisper / sotto voce** = the spec's volume/energy degrade + a whispered reference
   clip per persona voice. Worth deciding now, before the voice-profile schema sets.
5. The spike gate stands: **measure on an M-series Mac before implementing.** Two
   questions it should answer for everyone: does Chatterbox actually run on MPS without
   the community patches, and is the Perth watermark acceptable in a local-first
   companion (it is imperceptible and survives editing; it is also a third party's
   detector on your users' audio).

### BrightestMinds
Nothing required — you already route through `synthesize_with_prosody`, and expression
is no-op for you. When you want better-than-Piper quality cheaply, `register_engine("kokoro", …)`
is a one-class adapter; Kokoro's licence is clean and its controls (voice, speed) are
exactly what oratorical pacing needs.

### Halbert
Nothing required — your `integrations/voice_backend.py` implements the seam directly.
If you ever route through the reference layer, the same API applies.

---

## 5. What is deliberately not here, and why

- **Reference engines (Kokoro, Chatterbox).** Deferred until Halley's spike reports
  what these engines actually do on Apple Silicon. A reference written first would encode
  unverified assumptions about MPS and about the `energy → exaggeration` curve. The
  contract above lets a consumer register its own engine today, so nothing waits on
  this.
- **Widening `TTSRequest`.** Spec §5.7 freezes it because mutating the ABC's
  `synthesize()` signature breaks every external `TTSEngine` subclass. The subclass
  carries the extras instead, as §5.7 prescribes.
- **A whisper engine mode.** None exists to wrap.

---

## 6. Evidence

- New: `src/haloysius/services/tts/tests/test_engine_agnostic_prosody.py` — 26 tests
  (request carries hints; Piper projection unperturbed; generic backend satisfies the
  seam; routing by name; unregistered still `None`; rendering per style; whisper never a
  tag; no tag is ever guessed).
- The one pre-existing test that asserted the whole request was unperturbed now asserts
  the *Piper projection* is — same invariant, stated as what Piper reads.
- Full suite green (count in the commit message).
