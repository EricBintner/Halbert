# PKT-VMV-5 — Coordinate mapping disclosure

Tier: **opus**   Milestone: **M4**   Effort: **S**
Collision lane: **none (file-disjoint)**   Merge order: **n/a**
Verified against: halbert `main` @ `fbd725e9` (2026-09-11)

---

## 1. Packet

**VMV-5** — Coordinate mapping disclosure.

## 2. User problem

VMV-5 — Coordinate mapping disclosure (deep-eval verdict: RESHAPE — ship the coordinate disclosure, defer the rest). Halbert's screenshot tool silently transforms the frame before the vision model sees it, then presents whatever the model reports as if the coordinates were on the original screen. `capture_screenshot()` in `halbert_core/halbert_core/tools/vision_tools.py:116-205` reads `max_dim` (default from `cfg.screen_capture.max_dimension`, 1568) and passes it to `ScreenCapture` (`vision/screen_capture.py:255-280`); `ScreenCapture._encode_jpeg()` (`screen_capture.py:429-470`) then downscales any frame whose longest side exceeds `max_dim` — including a patch-alignment step that rounds the target down to a 14px multiple, so the true scale factor is NOT simply `max_dim / max(h, w)`. A region capture additionally shifts the origin by (x, y) with no note. The tool's own docstring (`vision_tools.py:118-121`) promises `width, height` return fields that are never returned (`vision_tools.py:201-203` returns only `{'image', 'description'}`). On a Retina-class 5120px-wide display the model receives a frame roughly 3.3x smaller than the screen with zero indication; this matters precisely because Halbert stages UI commands rather than executing them — a human reads and acts on those coordinates. Source items: HM08-M3 (ship now, effort S, no founder gate); OC21-C1 (frame-token guard — bank only); OC20-C14 (day journal — deferred, founder-gated).

## 3. What to build

One-file-focused change, all in `halbert_core/halbert_core/tools/vision_tools.py` plus a small additive surface on `ScreenCapture` in `halbert_core/halbert_core/vision/screen_capture.py` (no shared hot files per the section doc).

1. Geometry threading out of `ScreenCapture`. The downscale decision lives inside `_encode_jpeg()` and is currently discarded. Add a `last_geometry` attribute on `ScreenCapture` (plain dataclass or dict, populated at the end of `_encode_jpeg`): `{"orig_w": w, "orig_h": h, "out_w": <final width>, "out_h": <final height>}` where orig is the frame shape BEFORE any downscale and out is the frame shape AFTER downscale/patch-align. When no downscale happened, out == orig. This is set identically for `capture_full`, `capture_region` (both funnel through `_encode_jpeg`), and `capture_window` (which also calls `_encode_jpeg`). Grayscale conversion does not change geometry and needs no handling. Compute the scale factor at the call site as `orig_w / out_w` (and assert orig_h/out_h matches within rounding); do NOT store `self.max_dim / max(h, w)` — patch alignment (`screen_capture.py:455-462`) makes that value wrong.

2. Deterministic scale/offset note in `capture_screenshot` (`vision_tools.py:169-203`). After a successful capture and after the redact step (the note must survive the `desc += " (redacted)"` append at `:184-190`), build the note purely from measured numbers, no model:
   - If downscaled: `desc += " (image downscaled {scale:.2f}x from {orig_w}x{orig_h} to {out_w}x{out_h}; multiply any coordinates you report by {scale:.2f} to get screen pixels)"` where scale = orig_w / out_w computed from the threaded geometry.
   - If a region capture: also append `"; add ({x}, {y}) to any coordinates to get absolute screen position"` using the same `region` dict already validated at `:152-160`.
   - If neither (full capture under max_dim): append nothing beyond the existing text.
   The invariant from the source item: a coordinate reported off a transformed frame is never presented as a coordinate on the original. Wording must contain the literal word "multiply" (the pin from HM08-M3).

3. Return the promised fields. Extend the success return at `:201-203` to `{"image": base64_img, "description": desc, "width": orig_w, "height": orig_h, "scale": scale}` where width/height are the ORIGINAL capture dimensions (matching the docstring at `:118-121`: "original capture dimensions (before downscale)"). Verify the state-machine consumer tolerates extra keys — `_handle_executing` keys off the "image" key per the docstring; grep `ctx.images` / the image-key detection path in `agents/state_machine.py` before shipping to confirm extra keys are ignored (the dedup early-return at `:194-198` and the "unchanged" dict are intentionally left alone — no image is sent there, so no coordinates can be reported).

4. Fix the docstring to describe what is now true: returns `image`, `description`, `width`, `height` (original dimensions), `scale` (downscale factor, 1.0 when unchanged), and note that `description` carries the human-readable mapping instructions.

Keep it text-only, first-person-neutral, no model involvement, no colour/emoji surface. Do not touch `vision/redact.py`, `vision/watcher.py`, or the dedup path.

## 4. What NOT to build

OC21-C1 (screen-input frame-token guard): banked, zero code. Do not add any frame hash, generation counter, or coordinate-action echo mechanism anywhere — the deep-eval section is explicit that the only UI-input route today is AppleScript System Events addressing elements by name/hierarchy, so the guard has no consumer yet. It is recorded as a precondition for any future coordinate-driven input tool (ROADMAP SHELL-1/SURF-1); the only permissible artifact, if anything, is a one-line note in the existing handoff backlog — no new module, no `vision/frame_token.py`.

OC20-C14 (screen-activity logbook / day journal): deferred behind a founder yes plus a privacy review of `vision/redact.py`'s blocklist against what a journal would capture. Do not create `vision/logbook/`, do not persist frames/observations/cards, do not build any standup surface, and do not touch `vision/watcher.py` to feed one. This is VMV-5 (tail) in the deferred-items table.

Also out of scope: changing `max_dim` defaults or the patch-align algorithm; altering the redaction blocklist; the dedup/unchanged early-return (leave its description exactly as-is); webcam capture (`capture_webcam` has no downscale origin problem and needs no note); OCR tools; any UI/dashboard surface (the note is pure text in the tool result).

## 5. Target files
- `halbert_core/halbert_core/tools/vision_tools.py`

## 6. Dependencies

None — may dispatch immediately.

## 7. Effort

**S** — S. Registry notes hold: one tool handler, one additive attribute on ScreenCapture, one note builder, one docstring fix. No founder gate (HM08-M3 is verifier-added with "no founder decision"), no new files beyond possibly a small geometry dataclass, no new dependencies (mss/opencv/numpy already imported), no config changes, no cross-cutting helper. The only care points are (a) computing scale from actual pre/post pixel dimensions rather than the nominal max_dim ratio because patch alignment shifts it, and (b) confirming the state machine's image-key detection ignores the three new return keys — both are read-before-write checks, not design work. The RESHAPE cut the M-effort logbook and the M-effort frame-token guard; what remains is the small core the deep-eval estimated at S.

## 8. UX rationale

No user-visible surface changes — this is tool-result truthfulness, not a UI feature. What changes is what Halbert knows about its own sight: when it captures the screen and the frame was shrunk, the observation it works from (and relays in the one seamless conversation) carries the measured mapping in plain words — "image downscaled 3.27x … multiply any coordinates you report by 3.27" — so when it stages (never executes) a UI action, the human reviewing the staged command sees coordinates that map back to the real screen instead of being silently off by a factor. That is the frame invariant: the machine speaks grounded in measured data, and a coordinate off a transformed frame is never presented as a coordinate on the original. First-person-as-the-machine is preserved: the note is a factual statement about the capture, not an assistant apology. No colours, no emoji, no model names, no settings toggle.

## 9. Acceptance criteria

1. A full-screen capture that exceeds `max_dim` returns a dict containing `width`, `height` (original, pre-downscale dimensions), and `scale` > 1.0 whose value equals `width / <actual encoded width>`; its `description` contains the literal word "multiply" and the numeric factor.
2. A region capture additionally names the origin offset: the description instructs adding (x, y) for absolute position, and reported `width`/`height` are the region's original dimensions before any downscale.
3. A capture whose longest side is already under `max_dim` returns `scale == 1.0` and its description gains no scale note (only the pre-existing text, plus " (redacted)" when redaction ran).
4. The docstring at `vision_tools.py:118-121` no longer promises fields that are not returned; every promised field is returned on the success path.
5. The dedup early-return (`{"unchanged": True}` path) and all error returns are byte-identical to before.
6. The state machine still routes the next LLM call through the vision model — the "image" key detection is unaffected by the new keys.

## 10. Verification (measured state, not model judgment)

Primary: add tests to `halbert_core/tests/test_vision_tools.py` (existing file, already patches `halbert_core.vision.screen_capture.ScreenCapture` with a mock — see `TestCaptureWindowHandler.test_returns_image_on_success` at :275 and `TestCaptureAndOcrHandler` at :154 for the pattern) and/or `halbert_core/tests/test_screen_capture.py` (existing `_encode_jpeg` downscale tests at :49/:61/:105 give the frame-construction pattern with synthetic numpy arrays):

- `test_downscaled_capture_returns_scale_and_note`: construct a synthetic frame wider than max_dim (mirror test_screen_capture.py:49), run through `ScreenCapture(quality=…, max_dim=…)` + `capture_screenshot`, assert returned `scale == width_returned / encoded_width` and `"multiply" in result["description"]`.
- `test_region_capture_note_names_offset`: assert the description contains the (x, y) addition instruction for a region call.
- `test_no_downscale_no_note`: frame under max_dim → `scale == 1.0`, "multiply" NOT in description.
- `test_geometry_threaded_through_patch_align`: a frame whose nominal `max_dim / max(h, w)` differs from the post-patch-align scale (e.g. the 1568 vs 1344 example from the patch-align comment) → returned `scale` matches the REAL ratio, not the nominal one.

Runnable command (must exit 0):
`arch -arm64 .venv/bin/python -m pytest halbert_core/tests/test_vision_tools.py halbert_core/tests/test_screen_capture.py -x -q`

Note the repo's standing rules: run from the main checkout (this packet's worktree uses `arch -arm64 ./wt_pytest.py halbert_core/tests/test_vision_tools.py halbert_core/tests/test_screen_capture.py -x -q` instead), and main carries a known nonzero failure baseline — compare against a baseline run on the merge-base before attributing any failure to this change. Full-suite sanity: `arch -arm64 .venv/bin/python -m pytest halbert_core/tests -q` shows no NEW failures versus baseline.

## 11. Exclusions

- OC21-C1 frame-token guard → banked per the deep-eval ("bank, do not schedule"); recorded as the precondition for future computer-use (ROADMAP SHELL-1/SURF-1). No unit owns it today; it activates only on a founder computer-use capability decision.
- OC20-C14 screen-activity logbook / day journal → VMV-5 (tail) in the deferred-items table of FINAL-CRITICAL-DISCOVERY-BACKLOG-2026-09-11.md; gated on founder decision plus a privacy review of `vision/redact.py`'s blocklist against journal exposure. Would live in a new `vision/logbook/` tree when revisited — explicitly NOT built here.
- `vision/watcher.py` changes (periodic monitor, OCR-on-change) → not touched; no current unit, would attach to the logbook tail if anything.
- `vision/redact.py` blocklist review → part of the OC20-C14 tail's privacy review, not this unit.
- `capture_window`'s raw-JPEG fallback path (`screen_capture.py:417-431` returns undecoded bytes when cv2 can't decode) → in that branch `last_geometry` may be absent; the note builder must treat missing geometry as "no scale note" rather than guessing. Not an exclusion so much as a required guard, flagged here so it is not "fixed" by inventing dimensions.
- Webcam path note parity → dropped per RESHAPE scope (no downscale-origin defect there; `capture_webcam` geometry is untouched).

---

## OSS reference

Greenfield — no direct OSS reference; see the deep-eval.

## Repo traps

- Every Python test run needs the `arch -arm64` prefix: `arch -arm64 .venv/bin/python -m pytest halbert_core/tests`.
- From a git worktree use `arch -arm64 ./wt_pytest.py halbert_core/tests`, NEVER bare pytest (the editable install pins halbert_core to the MAIN tree).
- `main` is NOT green. Known-red baseline (2026-09-11): test_agent_model_override.py, test_agent_model_selected_event.py, test_no_model_names_in_user_facing_source.py, test_num_ctx.py (~23 failures). A failure is yours iff absent from this baseline.
- Work in a git worktree; narrow commits; concurrent sessions edit this repo.
- NEVER add Co-Authored-By or 'Generated with …' trailers. Subject + body only.
- No emoji anywhere. Colours only from shared-tokens/tokens.css (run scripts/check_contrast.py).
- Never name/recommend an AI model on any user-facing surface; connection slots, not model menus.
- Model locality: is_local_model() (model/llm_config.py:181) is the ONLY judge; :cloud tag is primary.
- Feature gating: has_capability() (capabilities.py:499); never _is_home_variant.
- Redaction: ingestion/redaction_registry.py enforced at security/display_transport.py; scrub BEFORE the model.
- Commands staged from the UI are staged, never executed.
- No users yet: no migrations/back-compat shims unasked; leave superseded data on disk, unread, never delete.
- Line references drift: re-anchor by grep before editing; a failed anchor is a rebase signal, not a spec change.
- Modify only this packet's Target files. .handoff/ is correspondence, not authority (ROADMAP.md + DECISIONS.md are the spine).
