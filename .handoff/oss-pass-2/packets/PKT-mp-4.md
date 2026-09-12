# PKT-MP-4 — Usage-anchored token accounting + route-keyed cache

Tier: **opus**   Milestone: **M1**   Effort: **M**
Collision lane: **G,N**   Merge order: **2/3 in G; 1/2 in N**
Verified against: halbert `main` @ `fbd725e9` (2026-09-11)

---

## 1. Packet

**MP-4** — Usage-anchored token accounting + route-keyed cache.

## 2. User problem

Halbert's context-window bookkeeping is built on estimates that never get corrected by the measurements the providers already return, and three adjacent surfaces are keyed or read wrong in ways that mislead the picker and the num_ctx sizing path.

Concrete live defects (all spot-checked against main):

1. Character-estimated tokens drive num_ctx, and the error compounds across a whole conversation. `context/tokens.py:16-80` (TokenCounter: CHARS_PER_TOKEN=4 fallback) and `model/client.py:1228-1250` (`estimate_prompt_tokens`: `len(content)//4`) produce a guess; `num_ctx_for_model` (client.py:1143-1225) sizes `options.num_ctx` from that guess. When the guess under-runs the real count, Ollama silently truncates the HEAD of the prompt — the instruction sheet plus thread receipt — and all we do is log a warning at client.py:744-747. The provider returns authoritative counts on every call (`prompt_eval_count`/`eval_count` on Ollama, already parsed into `LLMResponse.usage` at agents/llm_client.py:278-281; `usage` on OpenAI-compatible and Anthropic responses), and nothing feeds them back. So every turn after the first is sized off an uncorrected estimate while the true previous-turn count sits unused in the response object.

2. The real context window is only learned from successful probes, never from failure. `_MODEL_MAX_CACHE` (client.py:850) is fed by `remember_model_context_limit` / `_probe_model_architecture` (`/api/show` model_info). When a daemon rejects a request with a context-overflow error, the error body carries the actual limit (Ollama: "context length" / "exceeds" phrasing; OpenAI-compatible: `context_length_exceeded` / "maximum context length is N"), and that number is thrown away. The one signal that would correct an over-optimistic window never lands.

3. `_MODEL_MAX_CACHE` and `_NUM_CTX_CACHE` are keyed by bare model name (client.py:850, :780, :1182-1224). The same model name served by a local daemon and by a saved remote endpoint collapse into one process-lifetime maximum, and the num_ctx high-water mark of one route bleeds onto the other. A local 8k-window entry and a remote 128k-window entry with the same name share one cache slot.

4. LM Studio "loaded" means "installed." `get_loaded_models`/`is_model_loaded` (client.py:1453-1498) hit `{endpoint}/v1/models` with no Authorization header for provider="openai" and treat any listing as loaded. On LM Studio, `/v1/models` lists downloaded models, not JIT-loaded instances; the real loaded set lives on LM Studio's own API (`/api/v0/models`, which carries a `state: "loaded"` field). The picker can therefore claim a model is resident when it is only on disk.

5. No mid-conversation slot-switch consequence notice. Switching the chat slot to a different route mid-conversation invalidates every cached prefix and any provider-side session state, and the first turn on the new slot silently re-sends the whole transcript. The picker applies the change with no warning.

6. `keep_alive` is never set on Ollama calls (client.py:706-752 payload carries model/messages/stream/options only), so Ollama's default 5-minute unload clock governs regardless of whether a conversation is live — a slow turn gap can unload a multi-GB model mid-conversation, and an idle machine keeps it resident.

7. The Anthropic adapter (`_anthropic_payload`, client.py:590-632) sends no `cache_control` markers, so every turn re-bills the full system prompt + transcript prefix even though the prompt builder already emits a cache-boundary marker (SK-2, `prompts/agent_prompts.py:20-31`).

8. No usage ledger. `_record_outcome` (tier_router.py:763-789) reads `metadata.input_tokens`/`output_tokens` but the ModelResponse metadata on the Ollama path is not populated from `prompt_eval_count`/`eval_count` (that parse exists only in the agents/llm_client.py copy), and cost_usd is hardcoded 0.0. There is no durable per-call usage row keyed by connection slot and locality.

## 3. What to build

MP-4 lands four working changes plus the wiring for two more, all inside model/client.py, model/llm_config.py, and context/tokens.py (lane B — coordinate with MP-3/MP-5 on client.py and BIND-01a on llm_config.py; touch disjoint regions and rebase on their head).

A. Usage-anchored token accounting (the C5 core). Add a per-route anchor in client.py: a module-level dict keyed by route key (see C) holding `{fingerprint, prompt_tokens, completion_tokens, monotonic_ts}`. The fingerprint is a cheap stable hash (blake2b-16 over the concatenated message contents + tool schemas, already JSON-serialized by `estimate_prompt_tokens`) of the messages actually sent. After each successful call, the adapter path records the provider's authoritative counts into the anchor: on the Ollama path lift `prompt_eval_count`/`eval_count` out of the raw response dict in `_call_ollama` (client.py:757-766, which already returns `raw: data`) and on the OpenAI-compatible/Anthropic paths lift `usage.prompt_tokens`/`usage.completion_tokens` / `usage.input_tokens`/`usage.output_tokens` from the response JSON. `num_ctx_for_model`'s callers pass the previous anchor: when the incoming messages' fingerprint shares a prefix with the anchored fingerprint (same conversation continuing), the estimate for the shared prefix is REPLACED by the anchored authoritative prompt_tokens and only the delta (new turns since the anchor) is estimated by `estimate_prompt_tokens`. This confines estimation error to one turn instead of the whole transcript. Wire the same anchor through the async streaming path (agents/llm_client.py:278-281 already parses the counts; hand them up so the caller can store them). `context/tokens.py` gains a `count_delta(messages_after_anchor)` helper so the delta estimate uses the same CHARS_PER_TOKEN fallback in one place rather than a third copy of `//4`.

B. Error-text context-limit learning (M2). Add `learn_context_limit_from_error(provider, model, route_key, exc_text) -> Optional[int]` in client.py: a deterministic parser (regex over the provider's known phrasings — Ollama's "model requires more context length" / "input length exceeds the context length N", OpenAI-wire "maximum context length is N", llama.cpp "n_ctx" numbers) that extracts a candidate limit. Adoption is DOWNWARD-ONLY and route-keyed: the candidate may lower `_MODEL_MAX_CACHE[route_key]` (unlike `remember_model_context_limit`, which only raises — the docstring at client.py:899-913 explains why raising-only guards against Modelfile-default regression; the error path is the sanctioned exception because an observed rejection is stronger evidence than a probe). Call it from the GenerationError/HTTPError sites in `call_llm_chat`/`_call_with_tool_fallback` where a 400-class error body is available. After adopting a lowered limit, bump the `_NUM_CTX_CACHE[route_key]` high-water down to the new cap so the next turn sizes honestly instead of re-hitting the wall.

C. Route-keyed caches (M2 second half). Introduce `_route_key(provider, base_url, model) -> tuple` in client.py: `(provider, base_url.rstrip('/').lower(), model)`. Re-key `_MODEL_MAX_CACHE`, `_NUM_CTX_CACHE`, `_NUM_CTX_HIGH_WATER_AT`, and the MP-4 anchor dict from bare `model` to this tuple. Normalise the base_url the same way `_probe_context_limits` already does (`(endpoint or '').rstrip('/')` at client.py:1001) plus lowercasing the host. Every reader/writer of these caches (num_ctx_for_model, remember_model_context_limit, remember_listing_context_length, _probe_context_limits, _probe_model_architecture, model_context_limit[_nowait], and dashboard/routes/llm.py's `_publish_context_limit` at :330) threads the route key through; the public signatures gain an optional `provider`/`base_url` pair rather than changing positional args, so existing callers without route info behave as before (keyed `(provider or '', endpoint or '', model)`).

D. LM Studio loaded-state (M5). In `get_loaded_models`/`is_model_loaded` (client.py:1453-1498): when provider is lm-studio (or the OpenAI-compatible endpoint answers LM Studio's API), query LM Studio's native loaded-instance endpoint (`{base}/api/v0/models`) and treat only entries with loaded state as loaded; fall back to `/v1/models` listing only when the native endpoint is absent (older LM Studio), and in that case report "installed, load state unknown" rather than loaded=true. Add the provider constant to llm_config.py's LOCAL_RUNTIME_PROVIDERS handling only if a new provider spelling is introduced (lm-studio is already a member at llm_config.py:151 — do not add a second locality judge; route any locality question through `is_local_model()` at llm_config.py:181).

E. Slot-switch warning (M1). At the seam where a new chat-slot assignment is applied (the picker's chooseModel → settings write path), detect "active conversation exists AND new route key != current route key" and surface a one-time consequence notice BEFORE the next turn is admitted: the notice names the slot and locality (never the model), states that the next turn re-sends the conversation on a new connection and any cached state is lost, and requires no new UI chrome — a staged system-notice row in the one seamless conversation, first person, measured ("the next message will resend the full conversation"). Detection state lives next to the MP-4 anchor: a `current_route_key` recorded at turn admission; a mismatch on the next admission is what triggers the notice.

F. keep_alive from conversation liveness (C9) — wiring only, behind founder decision 6. Add `keep_alive` to the Ollama payload at client.py:706-752 computed from a liveness signal the caller passes in (conversation active → a multi-hour keep_alive; turn finalised and conversation idle → 0 to release). The liveness signal itself is a one-field parameter threaded from the state machine; MP-4 ships the payload plumbing and the parameter, defaulting to current behaviour (absent = Ollama default) until the founder rules on the policy values.

G. Anthropic prompt-prefix caching (C8) — wiring only, behind founder decision 7. In `_anthropic_payload` (client.py:590-632), split `system_parts` and the message prefix at the cache-boundary marker the prompt builder already emits (SK-2, prompts/agent_prompts.py:20-31) and attach `cache_control: {"type": "ephemeral"}` to the last block of the stable prefix. Off by default until the founder rules; the split point reuses the existing marker, never a new one.

H. Usage-row instrumentation (theme I). One deterministic append per model call: after each call (success or failure), write one row to a local JSONL usage ledger under the data dir (create-only, 0o600, fsync-then-replace is NOT required for an append-only log — plain append with flush is fine; follow the redaction registry for any endpoint text). Row shape: `{ts, route_key: {provider, base_url_host, model_id_hash}, locality: is_local_model(...) verdict, prompt_tokens, completion_tokens, latency_ms, status}`. Locality comes from `is_local_model()` (llm_config.py:181) — the one judge. The model identity is hashed (blake2b-16) in the row so the ledger never becomes a model-name surface; the raw name stays in process memory only. Populate `ModelResponse.metadata["input_tokens"]/["output_tokens"]` on the Ollama path from `prompt_eval_count`/`eval_count` so tier_router._record_outcome (tier_router.py:763-789) starts recording real numbers instead of zeros — this is a metadata-population fix in model/client.py and providers, not a tier_router edit (tier_router is MP-2's lane).

## 4. What NOT to build

Not in this packet:

- No pricing or cost tables. cost_usd stays 0.0 in tier_router._record_outcome; the usage ledger records measured tokens, never dollars. Any cost UI is a separate founder-gated unit.
- No eviction/compaction policy change. num_ctx sizing stays sized-to-prompt with the existing high-water/release logic (client.py:1180-1225); MP-4 only makes the inputs honest. Compaction policy belongs to the CSC units.
- No changes to `is_local_model()` semantics (llm_config.py:181) — it stays the one locality judge; MP-4 consumes it. No second judge, no per-provider locality overrides.
- No tier_router.py, rate_limiter.py, error_recovery.py edits — that is MP-2's lane. MP-4 touches only the metadata-population seam on the provider response side.
- No llm_client.py timeout/abort changes — that is MP-3's lane. MP-4's streaming-path touch in agents/llm_client.py is limited to handing the already-parsed usage counts upward.
- No tool-call repair or `_normalise_tool_calls` changes — that is MP-5's lane.
- No migrations, no back-compat shims for the cache re-key. The caches are process-lifetime in-memory structures; a restart naturally rebuilds them route-keyed. Old bare-name cache entries simply do not exist after restart.
- No new hard dependency. The anchor fingerprint uses hashlib.blake2b (stdlib). tiktoken stays an optional lazy extra exactly as context/tokens.py:37-44 handles it today.
- No model names on any surface: the slot-switch warning names slot + locality; the ledger hashes the model id; the num_ctx logs already log the model name at DEBUG/INFO only inside process logs, not on any user surface (keep it that way).
- No UI chrome for the slot-switch warning beyond one staged notice row in the existing conversation surface; no settings page, no modal.

## 5. Target files
- `halbert_core/halbert_core/model/client.py`
- `halbert_core/halbert_core/model/llm_config.py`
- `halbert_core/halbert_core/context/tokens.py`

## 6. Dependencies

None — may dispatch immediately.

## 7. Effort

**M** — M (medium), opus tier — and the effort is justified item by item:

- A (usage anchor) is the bulk of the M: it touches the request/response seam in `_call_ollama`, the OpenAI-compatible adapter, the Anthropic adapter, plus the async streaming path, and it must thread the route key through five cache structures without breaking the existing high-water/release invariants documented at client.py:1087-1130. The logic is straightforward bookkeeping but the blast radius across four call paths is real.
- B (error-text parser) is S: one regex table + one downward-adoption function + call-site wiring in the two error paths.
- C (route re-key) is S-to-M: mechanical but touches every reader/writer of four module-level dicts, and getting the normalisation identical to `_probe_context_limits`'s existing `rstrip('/')` convention is the only subtlety. The dashboard `_publish_context_limit` caller (routes/llm.py:330) must thread provider through — one extra parameter.
- D (LM Studio loaded-state) is S: one additional endpoint probe with a fallback, confined to client.py:1453-1498.
- E (slot-switch warning) is S: one route-key comparison at turn admission plus one staged notice row; no new UI.
- F (keep_alive) and G (Anthropic cache_control) are S wiring-only changes gated on founder decisions 6 and 7 — MP-4 ships the parameter plumbing, not the policy.
- H (usage ledger) is S: one append function + one call per adapter path + the metadata-population fix.

Total: roughly 1.5–2 days of focused work on hot files, which is why it is opus tier and lane-B coordinated (client.py is shared with MP-3/MP-5, llm_config.py with BIND-01a). The value is that A+B together make the context window honest for the first time: today the system sizes num_ctx from an uncorrected character guess and learns nothing from the authoritative counts and rejection errors it already receives; after MP-4 the estimate is anchored to measurement each turn and a provider rejection permanently corrects the cap. That directly serves the "grounded in measured data" frame — the system stops claiming a window it has never measured.

## 8. UX rationale

One user-visible surface, plus operator-visible telemetry:

1. Slot-switch consequence notice (the only new user-facing element). When the chat slot changes mid-conversation, the next turn is preceded by one staged system-notice row in the one seamless conversation — not a modal, not a settings banner, not a conversation list. First person, measured, no model name, no emoji: the notice states that the connection for this conversation changed and the next message will resend the conversation over the new connection, so any cached state on the previous connection is gone. It names the slot ("the chat connection") and its locality ("a connection on this machine" / "a remote connection") using the `is_local_model()` verdict — never the model, never the raw hostname. It appears once per actual switch (route-key mismatch), not on every turn, and it is a notice, not a confirmation gate: the turn proceeds. Colour from shared-tokens only; the notice uses the existing system-notice styling in the chat surface.

2. No other user-facing change. num_ctx honesty, the anchor, the re-keyed caches, the LM Studio loaded-state fix, keep_alive, and the Anthropic cache split are all invisible correctness/resource improvements. The LM Studio fix changes picker behaviour only in that the "loaded" badge now reflects measured loaded state rather than installed state — the badge text does not change, it just stops being wrong.

3. Operator telemetry. The usage ledger is a local JSONL file under the data dir, not a dashboard surface in this packet. If any future surface reads it, that surface shows tokens and locality, never model names.

4. Nothing is executed from the UI as a result of this packet; the slot-switch notice stages nothing. Commands staged from the UI remain staged, untouched by MP-4.

## 9. Acceptance criteria

Every item below is checkable by running code, not by judgment:

A1. Anchor correctness: in a test double of the Ollama adapter, send turn 1 with a scripted `prompt_eval_count` of 10000; send turn 2 whose messages are turn-1 messages plus one new short message. Assert the effective prompt-token figure used for num_ctx on turn 2 equals 10000 + estimate(new content only), i.e. the estimate for the shared prefix was replaced by the anchored count, and that the character estimate for the full transcript (which would differ by >20%) was NOT used.

A2. Anchor miss safety: clear the anchor (or change the fingerprint by editing an early message), send a turn, assert the code falls back to the full `estimate_prompt_tokens` path and num_ctx is sized from the estimate. No exception, no stale anchor reuse.

B1. Error-text learning: feed the parser a synthetic Ollama context-overflow error body and an OpenAI-wire "maximum context length is N" body; assert the parsed limit is adopted DOWNWARD into the route-keyed cache and a subsequent `num_ctx_for_model` for the same route key caps at the learned value. Feed a bogus/error body with no number; assert nothing is adopted. Feed a number LARGER than the currently cached window via the error path and a number SMALLER via `remember_model_context_limit`; assert the error path may lower and the remember path may only raise (both guards hold).

C1. Route-key isolation: seed the cache with a window for (ollama, http://localhost:11434, m) and a different window for (ollama, http://remote-host:11434, m); assert `model_context_limit` returns each for its own endpoint and neither collides. Assert the num_ctx high-water for one route does not cap or grow the other route.

D1. LM Studio loaded-state: against a stubbed LM Studio native endpoint returning one loaded and one installed-only entry, assert `is_model_loaded` is True only for the loaded entry. Against a stubbed endpoint with no native API (404), assert the fallback reports load-state-unknown rather than loaded=true for a bare `/v1/models` listing.

E1. Slot-switch notice: with an active conversation anchored on route key K1, apply a slot change to route key K2, admit the next turn, assert exactly one staged notice row is emitted before the turn and that its text contains the slot label and the locality verdict and contains no model name (assert against a denylist of the configured model ids). Admit a further turn with no slot change; assert no second notice.

F1. keep_alive plumbing: with the liveness parameter passed as active, assert the Ollama payload at the request seam contains the keep_alive field; with the parameter absent, assert the payload is byte-identical to current behaviour (no keep_alive key). Policy values are founder-gated; this test checks plumbing only.

G1. Anthropic cache split: build a payload whose system prompt contains the SK-2 cache-boundary marker; assert the emitted payload carries `cache_control` on the block ending the stable prefix when the feature flag is on, and is byte-identical to current behaviour when off.

H1. Usage ledger: run one stubbed call per adapter path; assert one JSONL row per call exists with prompt/completion tokens populated from the provider counts, locality matching `is_local_model()`'s verdict for the route, and the model id stored only as a hash (assert the raw model id string does not appear anywhere in the ledger file bytes). Assert `ModelResponse.metadata["input_tokens"]`/`["output_tokens"]` are non-zero on the Ollama path after the fix.

## 10. Verification (measured state, not model judgment)

All verification is runnable, measured-state checking. Run from the repo root with the mandatory arch prefix (the venv's python3 is universal2 and launches x86_64 unprefixed):

Primary gate — new packet tests (created by MP-4 in halbert_core/tests/test_model_usage_anchor.py and halbert_core/tests/test_model_route_keyed_cache.py, each test ID below maps 1:1 to an acceptance row):

  arch -arm64 .venv/bin/python -m pytest halbert_core/tests/test_model_usage_anchor.py halbert_core/tests/test_model_route_keyed_cache.py -q

  Required test IDs: test_anchor_replaces_prefix_estimate (A1), test_anchor_miss_falls_back_to_estimate (A2), test_error_text_adopts_downward (B1), test_error_text_bogus_body_no_adoption (B1), test_remember_path_only_raises (B1), test_route_key_isolation (C1), test_num_ctx_high_water_route_scoped (C1), test_lmstudio_loaded_state (D1), test_lmstudio_fallback_unknown (D1), test_slot_switch_notice_once (E1), test_slot_switch_notice_no_model_name (E1), test_keep_alive_plumbing (F1), test_keep_alive_absent_byte_identical (F1), test_anthropic_cache_split_flag_on_off (G1), test_usage_ledger_row_populated (H1), test_usage_ledger_hashes_model_id (H1), test_ollama_metadata_tokens_populated (H1).

Regression gate — the pre-existing suites for the touched files must not regress beyond the known nonzero main baseline (main is not green; capture a baseline on the merge-base first per CLAUDE.md):

  arch -arm64 .venv/bin/python -m pytest halbert_core/tests -q -k "num_ctx or context_limit or estimate_prompt_tokens or model_context or llm_client or token"

Measured end-to-end check (live, not a model judgment): start the backend (`make dev-web`), send two consecutive chat turns on a local Ollama route, then inspect the usage ledger file and assert (via `grep -c` / `jq`) that (a) two JSONL rows exist, (b) each row's prompt_tokens is a positive integer, (c) the raw model id string appears zero times in the file (`grep -c "$(model_id)" ledger.jsonl` returns 0), and (d) the backend log's num_ctx line for turn 2 shows the anchored figure (log line at client.py:753-756 prints prompt_tokens= — assert it equals the anchored value, within the delta estimate of the new turn). Exit code of every pytest invocation above must be 0 (or equal to the recorded merge-base baseline for the regression gate), and the ledger grep counts are integer comparisons, not judgments.

## 11. Exclusions

Named exclusions and where each goes:

1. keep_alive POLICY VALUES (how long to keep a model resident when a conversation is active vs idle) — MP-4 ships only the payload plumbing and the liveness parameter. The policy values are gated on founder decision 6 per the deep-eval and the final backlog's "MP-4 (tail)" row (keep_alive policy + prompt-prefix caching → founder decisions 6, 7). Goes to the Wave-2 founder-decision tail; until ruled, the payload carries no keep_alive key and behaviour is byte-identical to today.

2. Anthropic prompt-prefix caching ENABLEMENT — same treatment: MP-4 ships the split-at-marker plumbing behind a flag that defaults off. The enable/default-on decision is founder decision 7 (Wave-2 tail), because it changes billing behaviour on a cloud slot and the founder rules on cloud-slot spend posture.

3. Cost accounting / pricing tables / any dollar figure — deliberately excluded from the usage ledger (tokens + locality only). cost_usd in tier_router._record_outcome stays 0.0. A cost surface would name or rank providers by price, which collides with the never-name-models directive; if ever wanted it is a separate founder-gated unit, not an M5b tail item.

4. Compaction/eviction policy when num_ctx pressure is high — MP-4 makes the measurement honest; deciding to compact earlier or differently is the CSC-03/CSC-05 conversation-compaction units' scope, not this one.

5. The reroute-notice text for slot/locality fallback ("this turn ran on a cloud connection") — the deep-eval's MP-1 residual explicitly assigns OC14-C22 to MP-2's fallback transition notice work (OC03-C9), not to MP-4's slot-switch warning. MP-4's notice covers mid-conversation manual slot switches; MP-2's covers automatic fallback. Do not build both here.

6. Any change to `is_local_model()` or a second locality judge — forbidden outright (the invariant at llm_config.py:181 is the one choke point; MP-4 only consumes it). Any change to `has_capability()` gating — not touched.

7. tier_router.py / rate_limiter.py / error_recovery.py internals — MP-2's lane (hot-file separation). MP-4's only crossing into that territory is populating ModelResponse.metadata on the provider side so MP-2's telemetry starts seeing real numbers.

8. llm_client.py timeout and abort-hook work — MP-3's lane. MP-4's touch of agents/llm_client.py is limited to handing already-parsed usage counts upward; the ClientTimeout(total=120) defect belongs to MP-3.

9. Tool-call repair and `_normalise_tool_calls` — MP-5's lane (client.py:440-469 region). Lane-B coordination: MP-4 works client.py regions 590-790 (adapters + num_ctx), 840-1130 (context caches), 1228-1290 (estimate + dispatch), 1453-1498 (loaded-state); MP-5 works 440-469 (normalise) and the state_machine.py dispatch; MP-3 works llm_client.py. Rebase on the current lane-B head before touching client.py.

10. LM Studio loaded-state for the PICKER'S TypeScript side (packages/model-picker) — MP-4 fixes the Python `is_model_loaded` verdict the backend serves; if the picker caches its own loaded badge client-side, refreshing that rendering is a model-picker unit, not this packet.

11. No migrations and no back-compat handling for the cache re-key — per the no-users directive, the process-lifetime caches are simply rebuilt route-keyed on restart; nothing persisted needs converting, and nothing old is deleted.

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
