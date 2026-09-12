# PKT-VMV-3 — Central media limits + MIME sniffing + exception/URL leakage fixes

Tier: **opus**   Milestone: **M4**   Effort: **S-M**
Collision lane: **R**   Merge order: **2/2 in R**
Verified against: halbert `main` @ `fbd725e9` (2026-09-11)

---

## 1. Packet

**VMV-3** — Central media limits + MIME sniffing + exception/URL leakage fixes.

## 2. User problem

Inbound media surfaces and media/status displays leak or fall over in four verified ways, all on `main` (verified @ fbd725e9, deep-eval verdict ACCEPT — real DoS + secret-leak surface, no overlap with any merged R-packet):

1. UNBOUNDED BASE64 DECODE (DoS). `dashboard/routes/audio.py` `SpeakerEnrollRequest.audio_base64` and `SpeakerTestRequest.audio_base64` (pydantic models at audio.py:198-202, 257-258) carry no length bound; `base64.b64decode(req.audio_base64)` at audio.py:215 (enroll) and audio.py:267 (test) decodes an arbitrarily large request field straight into memory — a 200MB base64 body is fully materialized before any check runs. Same shape for images: `routes/agent.py:52` `SendMessageRequest.images: Optional[List[str]]` is an unbounded list of unbounded base64 strings, and `_attach_images` (agent.py:466-474) hangs the whole list on the last user message verbatim — no per-image cap, no count cap, no size cap, no MIME check. OC10-C3/OC10-C11/OC03-C11.

2. RAW EXCEPTION LEAK (secret-leak). Every Frigate tool handler in `integrations/frigate/frigate_tools.py` ends with `except Exception as e: return f"...: {e}"` — lines 226, 289, 310, 353, 379, 406. A requests/urllib error string interpolates the Frigate base URL it was connecting to, including any `user:pass@` credentials embedded in that URL, and that string is returned as the TOOL RESULT — straight into model context and the durable transcript, past the response choke point (the exception text is generated inside the tool, not scrubbed by display_transport, which only sees outbound display text). Same defect class as the SSE error leak fixed elsewhere; here it is six live call sites. OC11-C5.

3. CREDENTIALED GUEST-HOME URL AS DISPLAY NAME. `persona/guest.py` `GuestHome.from_payload` (guest.py:233-250) validates only `scheme in ("http","https")` and non-empty `parts.netloc` — credentials in the URL are accepted and stored raw in `base_url`, and `to_dict()` (guest.py:254-255) returns it raw. Then `dashboard/routes/guest.py:414` computes the display name as `home.label or (urlparse(home.base_url).netloc or home.base_url)` — and `urlparse('https://user:s3cr3t@home.local:8443/x?token=abc').netloc == 'user:s3cr3t@home.local:8443'` (verifier-confirmed), so a credentialed home URL is rendered on the Presence Pill / fronting surfaces. The same raw-netloc pattern feeds the peer-id stamp in `persona/guest_announce.py:137-148` `offered_by_for` (`f"home:{urlparse(...).netloc}"`), persisting credentials into session records. A05-G15 / backlog §3.16.

4. PRIVILEGED UNREDACTED PATH BY SHAPE ALONE. `security/result_redaction.py:39-60` documents KNOWN RISK NEW-01: `_redact_dict` honours `_egress_ack: True` on ANY dict at ANY depth purely by structural shape — a marker in a payload selects the unredacted path for that dict's `"value"` field. Nothing enforces that only `config.queries.get_config_value` set it; any tool handler returning `{"_egress_ack": True, "value": <secret>}` gets the same unredacted pass. OC11-C3.

## 3. What to build

Two new modules plus surgical edits at the six leak/decode sites. All copy is fixed template text, never an exception string; no model anywhere; no emoji (the origin's U+26A0 prefix is dropped per the deep-eval).

A. NEW `halbert_core/halbert_core/media/__init__.py` + `media/limits.py` — the single per-capability media-bounds table (deep-eval: "the media limits table and the MIME sniffer are one module"):
   - `MEDIA_LIMITS`: frozen dataclass instances per kind — `IMAGE` (max per-image decoded bytes, e.g. 10 MiB; max count per turn, e.g. 4; max base64 chars), `AUDIO` (max decoded bytes, e.g. 25 MiB; max base64 chars), each with a decode-timeout/char ceiling.
   - `check_base64(kind, s) -> bytes`: raises `MediaTooLarge`/`MediaMalformed` (both subclass a new `MediaRefused(Exception)` carrying a fixed, exception-free message string) when len(s) exceeds the kind's base64 char cap; decodes; checks decoded bytes against the byte cap; returns bytes.
   - `sniff_image_mime(data: bytes) -> Optional[str]`: magic-byte sniffing (JPEG FFD8, PNG 89504E47, GIF, WebP RIFF....WEBP) over a bounded prefix (first 32 bytes), never python-magic/libmagic (that would be a third hard dependency — the Haloysius subtractive contract forbids it). Returns None when unrecognised.
   - `check_images(images: Optional[List[str]]) -> List[Tuple[bytes, str]]`: enforces count cap then per-image check_base64 + sniff; returns decoded (bytes, mime) pairs or raises MediaRefused with fixed copy ("I can't take more than N images in one turn." / "That image is too large for me to hold." / "That doesn't look like an image I can read.").

B. NEW `media/failures.py` — the closed media-delivery failure taxonomy: a small enum `MediaFailure {UNREACHABLE, REFUSED, NOT_FOUND, MALFORMED, TOO_LARGE}` mapped to fixed first-person template strings, plus `failure_message(failure) -> str`. No field of any enum member or template accepts or interpolates an exception or URL.

C. `dashboard/routes/audio.py` — in `enroll_speaker` (line 215) and `test_speaker` (line 267), replace the bare `base64.b64decode(req.audio_base64)` with `media.limits.check_base64(MEDIA_LIMITS.AUDIO, req.audio_base64)`; catch `MediaRefused` → `HTTPException(413, <fixed refusal string from the exception's .message>)`. The generic `except Exception as e: raise HTTPException(500, str(e))` at lines 253-255 and 279-281 also leaks exception text into the HTTP detail — route those through `logger.error(...)` (keep logging the real exception) and return fixed detail strings ("I couldn't enroll that voice." / "I couldn't test that voice.") instead of `str(e)`.

D. `integrations/frigate/frigate_tools.py` — wrap the six handler bodies: on exception, log the real exception (`logger.warning("frigate_get_events failed: %s", e)` — logging is fine, the redaction registry scrubs logs), and return the taxonomy string from `media.failures` (UNREACHABLE for connection/timeout classes, else REFUSED) — never `f"...: {e}"`. Six return sites: lines 226, 289, 310, 353, 379, 406. Tool-result strings stay exception-free by construction.

E. `dashboard/routes/agent.py` — in `_attach_images` (line 466) replace the verbatim hang with `media.limits.check_images(images)` output (store decoded refs on the message as today, or keep base64 but only after the check passes); on `MediaRefused`, the refusal string becomes the turn's staged refusal — do not attach the images, do not 500.

F. Credentialed-URL fix via the P5 `url_guard` dependency (backlog §3.16 — "one SSRF/base-URL guard", needed by VMV-3): promote the existing `redact_url` logic from `mcp/config.py:249-256` into the P5 guard module (per the deep-eval opportunity: "The base-URL sanitizer promotes mcp/config.py's redact_url to security/ and routes every provider base-URL display through it"). If P5 has not landed when this builds, implement the minimal display-side half locally as `security/url_display.py` with `display_host(url) -> str` (hostname + optional non-default port only — userinfo and query ALWAYS stripped) and `safe_url(url) -> str` (credentials + query stripped, scheme+host+port kept), then migrate when P5 lands. Consumers to switch in THIS unit: `dashboard/routes/guest.py:414` (`who = home.label or display_host(home.base_url)`), `persona/guest_announce.py:137-148` `offered_by_for` (peer id built from display_host, not raw netloc), and `persona/guest.py:254-255` `to_dict()` (base_url returned through safe_url). Also add to `persona/guest.py` `from_payload` validation: reject a base_url whose parsed `.username` or `.password` is non-empty with a fixed GuestValidationError ("a home URL must not carry credentials — put the token in home.token"), so new credentialed homes fail closed at admission rather than being scrubbed forever. No migration of already-stored homes (no-users rule: leave old data unread).

G. `security/result_redaction.py` — bind the `_egress_ack` exemption to a host-owned retained set (OC11-C3): keep a module-level `_RETAINED_ACK_IDS: set[int]` (guarded by a lock) of `id()`s of dicts that `config.queries.get_config_value` itself created; `_redact_dict` honours `_egress_ack` only when `id(d) in _RETAINED_ACK_IDS` (and discards the id on use so it is single-shot). Update the two named contract tests' setup to register through the real path rather than by shape. The KNOWN RISK comment at lines 46-63 is rewritten to describe the enforced invariant. This is deliberately the minimal binding (id-set, not signed markers) per the packet registry note; the deep-eval called full provenance-checking "a real design change" — that stays out.

## 4. What NOT to build

Per the ACCEPT verdict's scope and the deep-eval reasoning, explicitly out:

1. The full provenance-checked `_egress_ack` redesign (signed markers, direct-top-level-only semantics, retiring the nested-payload contract) — the result_redaction.py:46-63 comment itself says that is "a real design change ... not a mechanical fix"; build only the retained-id binding (item G). The full redesign goes to M5b tail as a DECISIONS.md candidate.
2. The `media://` prompt-reference scheme (OC03-C13) — the deep-eval ranks it low ("with a pinned local model the disclosure is to the host's own model ... insurance for the :cloud slot case"). Deferred to M5b tail; do not build the reference indirection or prompt-rewriting here.
3. HM08-C9 — the upload-surface item is already deferred by the section itself ("deferred to an upload surface"); no upload endpoint work in this unit.
4. OC10-C18's other half — only the count cap half is in scope (bounded attachment count per turn); whatever the non-count half covers stays with its owning packet.
5. Any change to `ingestion/redaction_registry.py`, `security/display_transport.py`, or the SSE scrubber — those choke points are owned by R-10/VMV-2 territory; this unit only stops feeding them raw exceptions and credentialed URLs.
6. No new MIME library, no python-magic, no Pillow — magic-byte sniffing only (Haloysius two-hard-dependency contract; heavy/ML stacks stay lazy optional extras, and an imaging library is not needed to bound and sniff).
7. No guest-persona behavioural changes beyond the URL surfaces named (the broader guest build state — audio/vision gates, picker, verb — belongs to feat/guest-persona, not this packet).
8. No UI/dashboard frontend work — the display fix is at the API payload boundary (routes/guest.py `who`, guest.py `to_dict`), so every current and future surface inherits it.
9. No migrations or back-compat shims for already-stored credentialed `GuestHome` rows — no-users rule; validation now refuses new ones and display never renders credentials, which covers the leak without touching stored data.

## 5. Target files
- `halbert_core/halbert_core/dashboard/routes/audio.py`
- `halbert_core/halbert_core/integrations/frigate/frigate_tools.py`

## 6. Dependencies

text_hygiene, P5

## 7. Effort

**S-M** — S-M, matching the registry: the two new modules are small and self-contained (a frozen limits table, a magic-byte sniffer over 32 bytes, a five-member failure enum with template strings — no concurrency, no persistence, no config file). The edits are mechanical and site-bounded: two decode swaps in audio.py, six exception-return swaps in frigate_tools.py, one list-processing swap in agent.py's `_attach_images`, three one-line display/peer-id swaps plus one validation clause for the URL fix, and a contained change to one dict handler in result_redaction.py with its two contract tests updated. No founder-decision gate (the section says "Founder decision gates: no"), no schema or store changes, no frontend work. It clears S because it is more than a handful of one-line fixes — two new modules, a new package, edits across seven files in four subsystems, and a test surface that must prove measured bounds (byte counts, rejection status codes, absence of credential substrings in rendered output) — but stays under M because every change is a bounded swap at a named site with a template string, and the dependencies (text_hygiene for any free-text scrubbing, P5's url_guard for the display host extraction) absorb the only pieces that could balloon. The dominant risk is test-shape churn in the two `_egress_ack` contract tests, which is bounded and named.

## 8. UX rationale

Nothing new appears on any surface; what changes is that existing surfaces stop lying and stop leaking. The refusals speak as the machine, first person, grounded in the measured limit that fired: "I can't take more than 4 images in one turn." / "That audio clip is too large for me to hold (25 MB is my ceiling)." — never a stack trace, never an exception string, never a number the machine didn't measure. Frigate failures stop pasting internal URLs into the conversation: instead of `Failed to get snapshot: HTTPConnectionPool(host='user:s3cr3t@cam.local'...)` the model and transcript see one fixed line like "I couldn't reach the camera recorder." — consistent with commands-staged-never-executed honesty and the no-emoji rule (the origin packet's warning-sign prefix is dropped). The Presence Pill and guest fronting surfaces show a home as `home.local:8443`, never `user:s3cr3t@home.local:8443` — a guest persona's origin is a place, not a credential. No model is ever named on any surface (refusal copy names no engine); no colour is touched (no frontend change); the one seamless conversation is untouched — a refused attachment simply doesn't attach, and the turn continues with the staged refusal as its content.

## 9. Acceptance criteria

1. `POST /audio/speakers/enroll` and `POST /audio/speakers/{id}/test` with a base64 body whose decoded size exceeds MEDIA_LIMITS.AUDIO return HTTP 413 with a fixed refusal string and allocate no more than the cap (test asserts status 413 and that `b64decode` was never reached for the over-cap portion — e.g. by sending a syntactically valid but over-cap string and asserting the response detail equals the template, not a decode error).

2. `SendMessageRequest` with more images than the count cap, or one image over the byte cap, or a base64 string whose decoded bytes fail magic-byte sniffing, is refused with the fixed template; `_attach_images` attaches nothing in the refused case.

3. Each of the six Frigate handlers, with the client monkeypatched to raise `requests.ConnectionError("http://user:s3cr3t@cam.local:5000 refused")`, returns a string that (a) equals the fixed taxonomy message and (b) does NOT contain "s3cr3t", "user:", or the base URL — asserted by substring scan of the returned tool result.

4. `urlparse`-based display: `routes/guest.py`'s `who` for a home with `base_url="https://user:s3cr3t@home.local:8443/x?token=abc"` and no label equals "home.local:8443" (no "user", no "s3cr3t", no query); `offered_by_for` on the same URL contains no "s3cr3t"; `GuestHome.to_dict()["base_url"]` contains no "s3cr3t" and no "token=abc".

5. `GuestHome.from_payload` with a credentialed base_url raises `GuestValidationError` with the fixed message.

6. `result_redaction`: a dict shaped `{"_egress_ack": True, "value": "hunter2"}` constructed by test code (never registered through `config.queries.get_config_value`) is redacted — `"hunter2"` does not appear in `_redact_dict`'s output; the same shape produced through the real registered path still passes raw. The two existing contract tests (`test_egress_ack_does_not_leak_to_sibling_dicts`, `test_nested_secret_dict_keys_still_redacted_under_marker` in test_mcp_response_boundary.py) pass with registration routed through the real path.

7. Full suite delta: `arch -arm64 .venv/bin/python -m pytest halbert_core/tests` shows zero failures beyond the known-red baseline (test_agent_model_override.py, test_agent_model_selected_event.py, test_no_model_names_in_user_facing_source.py, test_num_ctx.py, ~23 failures as of 2026-09-11).

## 10. Verification (measured state, not model judgment)

Run, from the worktree root (never bare pytest — the editable install pins halbert_core to the main tree):

`arch -arm64 ./wt_pytest.py halbert_core/tests/test_media_limits.py halbert_core/tests/test_audio_routes.py halbert_core/tests/test_frigate.py halbert_core/tests/test_guest_routes.py halbert_core/tests/test_guest_persona.py halbert_core/tests/test_mcp_response_boundary.py -x -q`

where `test_media_limits.py` is the new test module this unit adds, with at minimum these measured assertions: `test_over_cap_audio_enroll_returns_413` (client posts `MEDIA_LIMITS.AUDIO.max_b64_chars + 4` chars; assert `response.status_code == 413` and `response.json()["detail"] == <fixed template>`), `test_image_count_cap_refuses` / `test_oversize_image_refuses` / `test_non_image_magic_refuses` (assert the refusal string and that no image reached the message dict), `test_frigate_handler_error_contains_no_credentials` (monkeypatch client to raise with a credentialed URL in the message; assert returned string == taxonomy template and `"s3cr3t" not in result`), `test_guest_display_host_strips_credentials` (assert `who == "home.local:8443"`), `test_credentialed_home_refused_at_admission` (assert GuestValidationError), and `test_unregistered_egress_ack_shape_is_redacted` / `test_registered_egress_ack_passes` for the result_redaction binding. Exit code 0 is the pass signal; a non-zero exit that also appears in the known-red baseline list is not this unit's failure (baseline: test_agent_model_override.py, test_agent_model_selected_event.py, test_no_model_names_in_user_facing_source.py, test_num_ctx.py).

Then the full-suite regression gate: `arch -arm64 ./wt_pytest.py halbert_core/tests -q` — pass means exit code reflects only baseline reds and nothing new.

Plus one static measured check, run with grep against the built tree: `grep -n 'return f".*: {e}"' halbert_core/halbert_core/integrations/frigate/frigate_tools.py` must produce zero matches (all six raw-exception returns are gone), and `grep -rn "urlparse(.*base_url).netloc" halbert_core/halbert_core/dashboard/routes/guest.py halbert_core/halbert_core/persona/guest_announce.py` must produce zero matches (no raw-netloc display or peer-id construction remains).

## 11. Exclusions

Real exclusions and where each goes:

1. `media://` prompt-reference indirection (OC03-C13) — M5b tail. Deep-eval: "low priority — with a pinned local model the disclosure is to the host's own model. Insurance for the :cloud slot case." Not built here; note it in the M5b backlog as the cloud-slot insurance follow-up.
2. Full `_egress_ack` provenance redesign (signed markers / direct-top-level-only, retiring the nested-payload contract) — M5b tail, and it needs a DECISIONS.md note first because it deliberately changes a contract two tests encode. This unit ships only the retained-id binding, which narrows the hole without redesigning the contract.
3. HM08-C9 (upload surface) — dropped per the section's own deferral ("deferred to an upload surface"); no packet owns it until an upload surface exists.
4. OC10-C18's non-count half — stays with whatever packet owns that item's other half; this unit takes only the bounded-attachment-count half.
5. Any SSE/error-scrubber work in display_transport.py or the agent SSE pipeline — owned by VMV-2's RESHAPE residual (full-tag-family SSE scrubber, HM02-C11). This unit's exception fix happens inside the tool handlers so the scrubber never sees the raw text; the scrubber itself is not touched.
6. Emoji/variation-selector stripping of spoken text (HM08-M4 half) — VMV-2 residual per the deep-eval ("the emoji strip is implied by 'no emoji in UI'"), not this unit.
7. Guest persona gates (audio/vision capability gates, picker, verb) — feat/guest-persona branch's remaining work per the guest-persona build-state memory; only the URL display/validation surfaces are in scope here.
8. The P5 url_guard module itself — P5 owns building the centralized guard; this unit consumes it. If P5 is unlanded at build time, this unit lands the minimal `security/url_display.py` (display_host/safe_url) as the consumer-side shim and P5's RESHAPE absorbs/promotes it — recorded here so the merge knows the shim is deliberately temporary, not a second guard.
9. Reconnect supervisor, replay tail, and anything from VMV-4/VMV-6 — separate ACCEPT/RESHAPE packets; the only shared dependency is text_hygiene (Wave-0, M0/M3), which must land first for any free-text scrubbing this unit's templates need.

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
