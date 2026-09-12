# PKT-T4 — Wire contracts + model-name-surface evaluation

Tier: **opus**   Milestone: **M4**   Effort: **S-M**
Collision lane: **none (file-disjoint)**   Merge order: **n/a**
Verified against: halbert `main` @ `fbd725e9` (2026-09-11)

---

## 1. Packet

**T4** — Wire contracts + model-name-surface evaluation.

## 2. User problem

Two verified gaps in Halbert's contract surface. (1) Wire contracts: `halbert_core/halbert_core/agents/llm_client.py` builds aiohttp payloads at the Ollama chat site (`OllamaClient.chat`, payload at ~llm_client.py:128-137, posted to `/api/chat` via `aiohttp.ClientSession`) and the Ollama stream site (~:207-216, `"stream": True`), plus the `AnthropicClient.chat` site (~:335+). Nothing runs these through a real transport: the only payload assertions in the tree are on the *sync* `requests.post` path (`halbert_core/tests/test_num_ctx.py:124-186` patches `halbert_core.model.client.requests.post`). Header behaviour, JSON encoding, and — critically — the SEC-21 locality guarantee are untested at the wire: `is_local_model()` (`halbert_core/halbert_core/model/llm_config.py:181`) is the sole judge of local vs cloud, and `secure_model` slots carrying a `:cloud` tag are disabled at chooser time (`llm_config.py:505-520`), but no test proves a `:cloud`-tagged slot never produces a request from the local-mode code path. (2) Model-name surface: the standing founder directive "never name an AI model on any user-facing surface" is enforced only by a static source-text tripwire, `halbert_core/tests/test_no_model_names_in_user_facing_source.py`, whose own docstring admits it is "a tripwire for drift, not a proof of absence": its `_sources()` walks only `dashboard/frontend/src` and `dashboard/routes`, missing the `halbert_core/halbert_core/model/*.py` files (`attribution.py`, `client.py`, `llm_config.py`) that assemble user-facing strings, and it never executes a runtime surface, so a name assembled at runtime (e.g. from endpoint config rendered through a route) passes silently.

## 3. What to build

Three pieces, all under `halbert_core/tests/`. (1) A shared loopback capture fixture — a `ThreadingHTTPServer` bound to `127.0.0.1` on an ephemeral port that records each request's path, headers, and parsed JSON body, then answers with a canned Ollama (`{"message":{"content":"ok"}}`) or Anthropic-shaped (`{"content":[{"text":"ok"}]}`) response. Build it once as a pytest fixture in a new `halbert_core/tests/test_llm_wire_contracts.py`; this is the same fixture T1's egress-safety net needs, so shape it for reuse (loopback-only bind, refuse non-loopback connects). Scrub `os.environ` of proxy vars (`HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`, lowercase variants) and `ANTHROPIC_API_KEY`-style auth env before each client construction so a developer shell cannot leak into the wire. (2) Wire-contract tests driving the real async clients against that fixture with sentinel model tags (e.g. `"__sentinel_slot_tag__:latest"` — never a real model family): assert on `OllamaClient.chat` that the captured body carries `model` == the sentinel, `options.num_ctx` is a positive multiple of 512 (the `compute_num_ctx` rounding contract), `stream` is False, `tools` present iff tools were passed, and no `Authorization` header was sent to the loopback target; assert on `OllamaClient.stream` that `stream` is True; assert the Anthropic shape hits `/v1/messages` and never sends an auth header to a non-Anthropic loopback host. Plus the SEC-21 regression at the wire: construct the secure path with a `:cloud`-tagged slot (mirroring the disabled-slot case in `llm_config.py:512-520`) and assert zero requests reach the capture server — fail closed, nothing sent. (3) Extend the static guard's `_sources()` in `test_no_model_names_in_user_facing_source.py` to also rglob `halbert_core/halbert_core/model/*.py` (the three missed directories' worth of files), and add a new runtime battery `halbert_core/tests/test_no_model_names_on_surfaces.py`: enumerate the production JSON/rendered surfaces that can carry a model string (the settings/agent routes under `dashboard/routes/` that echo slot config, e.g. `routes/agent.py:677`'s secure-content notice and the `routes/llm.py` slot endpoints), drive each through the FastAPI test client with the sentinel tag configured in every slot, and assert the sentinel appears nowhere in any response body — only slot labels (`chat_model`, `secure_model`, etc.) may render. Add a short README note in the test file docstring on large-batch eval orchestration discipline (bounded concurrency, sentinel-only tags, no real model strings in fixtures).

## 4. What NOT to build

Not in this packet: (a) T1's hermetic-environment work itself — the env scrub and per-file isolation runner belong to T1 (ACCEPT, separate packet); T4 only scrubs the minimal proxy/auth env it needs inside its own fixture and assumes T1 lands independently (the deep-eval lists T1 as a prerequisite for full hermeticity but T4's wire tests are meaningful standalone). (b) Any eval-harness scorecard/verdict-row integration — R-15 merged `halbert_core/halbert_core/eval/`; wiring the model-name battery into that harness's verdict rows is follow-on work, not this packet. (c) Changes to `llm_client.py`, `llm_config.py`, or any route handler — this packet is tests plus one test-file `_sources()` extension only; if a test turns red the fix is a separate change. (d) The sync `model/client.py` payload path — already covered by `test_num_ctx.py:124-186`. (e) Enumerating model names anywhere — no test, fixture, or assertion may name a real model family; sentinel tags only, per the registry note.

## 5. Target files
- `halbert_core/tests/`

## 6. Dependencies

None — may dispatch immediately.

## 7. Effort

**S-M** — S-M is right. The loopback fixture is ~60 lines of stdlib (`http.server.ThreadingHTTPServer`, ephemeral port, request recorder) and is deliberately shared with T1 so it is not built twice. Each wire test is short — construct a real `OllamaClient`/`AnthropicClient` pointed at the fixture, await one call, assert on captured path/headers/body — but there are four build sites (Ollama chat/stream, Anthropic chat/stream) plus header-absence and SEC-21 fail-closed cases, which is what pushes past S. The static-guard extension is a five-line change to `_sources()`. The runtime surface battery is the M component: enumerating the real slot-echoing routes and driving them through the test client with sentinel config requires reading the route shapes, though the existing `conftest.py` (`HALBERT_API_TOKEN` fixture at conftest.py:197-232) already provides the authenticated client pattern. No new production code, no new dependencies (stdlib + existing aiohttp/pytest-asyncio), and the two-dependency Haloysius contract is untouched.

## 8. UX rationale

No user-facing surface changes. This packet is invisible to the founder except as green tests. Its product value is exactly one standing directive kept: the engaged surface continues to speak as the computer itself, first person, grounded in measured data, and never names an AI model — the runtime battery proves the slots render as slots (`chat_model`, `secure_model`) on every surface that echoes configuration, and the SEC-21 wire test proves a cloud-tagged slot fails closed rather than quietly proxying a secure turn out through a localhost relay. The founder-visible failure mode it prevents is the one already recorded in the tree's history: the About panel and Vision tab drift that `test_no_model_names_in_user_facing_source.py`'s docstring describes.

## 9. Acceptance criteria

(1) `halbert_core/tests/test_llm_wire_contracts.py` exists, uses a loopback-only `ThreadingHTTPServer` fixture, and contains passing tests asserting: the Ollama chat body carries the sentinel model tag, a `num_ctx` that is a positive multiple of 512, `stream: False`, and `tools` present iff passed; the Ollama stream body carries `stream: True`; no `Authorization` header is sent to any loopback target from either client; and a `:cloud`-tagged secure slot produces zero captured requests (fail-closed). (2) `test_no_model_names_in_user_facing_source.py::_sources()` additionally yields the `halbert_core/halbert_core/model/*.py` files, and the existing guard still passes. (3) `halbert_core/tests/test_no_model_names_on_surfaces.py` drives every slot-echoing production route with a sentinel tag configured and asserts the sentinel string appears in no response body. (4) No test, fixture, comment, or assertion anywhere in the change names a real model family — grep over the diff for the existing FAMILIES list returns only the guard file itself. (5) Full suite runs under the repo contract (`arch -arm64 .venv/bin/python -m pytest halbert_core/tests`) with no new failures beyond the known main baseline.

## 10. Verification (measured state, not model judgment)

Run, from the repo root (never bare pytest in a worktree — use `./wt_pytest.py` there): `arch -arm64 .venv/bin/python -m pytest halbert_core/tests/test_llm_wire_contracts.py halbert_core/tests/test_no_model_names_on_surfaces.py halbert_core/tests/test_no_model_names_in_user_facing_source.py -x -q` — measured state: exit 0 and the SEC-21 test's assertion `server.captured == []` (zero recorded requests) printed in verbose mode. Then prove the wire tests are not vacuous: temporarily point `OllamaClient` at a `10.255.255.1` (non-loopback unroutable) endpoint in one test invocation via env override and confirm the fixture's loopback-only guard rejects/skips rather than silently passing. Then the full measured gate: `arch -arm64 .venv/bin/python -m pytest halbert_core/tests -q` and diff the failure count against a baseline run on the merge-base — the delta must be zero new failures. Finally, the measured directive check: `grep -rniE '\b(llama|qwen|mistral|gemma|deepseek|gpt-4|claude|phi-3|falcon|vicuna|llava|mixtral|codellama|tinyllama|nomic-embed|starcoder|wizardlm|orca)\b' halbert_core/tests/test_llm_wire_contracts.py halbert_core/tests/test_no_model_names_on_surfaces.py` must return nothing (sentinels only).

## 11. Exclusions

Deliberately excluded and where each belongs: (a) The full hermetic-environment scrub (all `os.environ`, live-DB guard, per-file isolation runner) — that is packet T1, ACCEPT in the same milestone; T4's fixture scrubs only proxy/auth env vars it directly needs and must not grow into T1's scope, or the two packets will conflict when T1 lands. (b) Verdict/scorecard row integration for the new battery — belongs to whoever extends the merged R-15 eval harness (`halbert_core/halbert_core/eval/`), not to a test-only packet. (c) Any production-code fix a red test reveals (e.g. if a route does leak a model string) — a separate remediation change, filed against the owning route file, so this packet stays test-only and reviewable as such. (d) The sync `requests.post` payload contract — already asserted by `test_num_ctx.py:124-186`; re-adding it here would duplicate the invariant in a second place, violating the one-choke-point rule. (e) The T3 stop-gate seam and verify-on-stop nudge — deferred by the deep-eval until the opus-tier state-machine work settles. (f) Real model identifiers in any fixture — barred by the registry note; the existing guard's FAMILIES list is the oracle for what must never appear, and the verification step greps the new files against exactly that list.

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
