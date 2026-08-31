# REV-05 Review Results — Unified LLM Router, GPU Locking & Apple Intelligence

**Review date:** 2026-08-31
**Reviewer model:** GLM-5.3
**Packet:** `.handoff/REVIEW-PACKET-05-UNIFIED-LLM-ROUTER-AND-GPU.md` (2026-08-29)
**Code reviewed at:** branch `worktree-central-todo-batches`, HEAD `149b3e75` (packet's `232adf4f`-era code reviewed as it exists *today*, including the post-packet merges: Apple Intelligence `11ded488`, U6 home-variant simplification, `HALBERT_MODEL` override `7c70276d`)

**Method:** full read of `model/llm_config.py`, `model/client.py`, `model/tier_router.py`, `model/hardware_detector.py`, `model/auto_provision.py`, `model/providers/peer.py`, `utils/platform.py`, and the production chat path (`dashboard/routes/agent.py` model resolution, `chat()`, `stream()`, `_stream_turn`; `agents/state_machine.py` stream preference; `integrations/app_seam.py` TierRouter seam). Every finding was adversarially traced to a concrete failure scenario; the peer-streaming defect was reproduced empirically (aiohttp raises `NonHttpUrlClientError` on `peer://`). Tests run read-only via the worktree wrapper, all green:

- `test_num_ctx.py test_model_client_byok.py test_llm_config_store.py test_llm_show_context_length.py test_auto_provision.py test_apple_intelligence_platform.py` — **179 passed**
- `tests/federation/` — **135 passed, 15 skipped**
- `test_agent_model_override.py test_agent_model_selected_event.py test_num_ctx.py test_tool_calling_bridge.py` — **178 passed**

**Overall verdict: PASS WITH FINDINGS.** The unified store, num_ctx sizing, and Apple Intelligence *eligibility* gating are solid and well-defended against their historical bugs. The defects are concentrated at the seams the packet predates: the home-variant peer provider is registered everywhere except the production streaming adapter, and Apple Intelligence provisioning assigns live slots to a bridge that does not exist in this repo.

---

## 1. Verdict per area

| Area | Verdict |
|---|---|
| `model/llm_config.py` (store, layers, migration, parse cache) | **PASS.** Careful separation of read-cache vs write-path (`use_cache=False` for every write), refusal to overwrite unparsable files, key carry-forward. Two PLAUSIBLE minors below. |
| Model resolution & fallback chains (`client.py` getters, `_resolve_turn_model`, guide fallback, secure gate) | **PASS WITH FINDINGS.** Per-call resolution is correct and pin-aware; the secure gate order (dedicated slot → local resolved model → local guide → fail-closed) is right. But see F1/F2. |
| `num_ctx` sizing (client.py §7) | **PASS.** Math verified: `clamp(round_up(prompt+512+num_predict,1024), 4096, min(model_max, ceiling))`; high-water/release semantics cannot truncate; probe paths are off the event loop; listing-derived caps can only ever raise, never bind. Only estimate-accuracy minors. |
| GPU advisory lock | **FAIL (coverage) / PASS (crash safety).** POSIX `flock` auto-releases on process death, so the packet's stale-lockfile-hang concern is structurally resolved — but the lock guards only the *planning* calls, not the streaming answer that actually loads models (F5). |
| Apple Intelligence platform gating (`utils/platform.py`, hardware detector, auto-provision) | **PASS on eligibility, FAIL on provisioning.** All four eligibility conditions (Apple Silicon, macOS ≥ 15.1, ≥ 16GB, Metal) are enforced and tested; but auto-provision never consults `apple_intelligence_bridge_running`, which it computes one branch away (F2). |
| Provider registration (peer, apple-foundation, OpenAI-compat) | **PASS WITH ONE GAP.** `peer` is chat-capable, normalise-safe, TierRouter-registered, and tested — but the streaming adapter (`_stream_turn`) has no `peer` branch (F1). `apple-foundation` is correctly OpenAI-compat-wire on :11435 and correctly never a peer backend (compute_endpoint docstrings + slot rules enforce it; peer compute listing is still a TODO(federation-9.3) stub). |
| Tool-calling payload translation | **PASS.** `_normalise_tool_calls` handles Ollama-decoded vs OpenAI-string args and Anthropic `input`; the retry-without-tools registry is evidence-based (only latches when the retry succeeds). The agent loop folds tool results into plain-text observations, so no `role:"tool"` messages exist to mistranslate across providers. |
| Credential storage | **MIXED.** 0600 perms, atomic temp-file writes, `.bak` on rewrite, no plaintext key dumps found in settings routes — but `GET /api/llm/config` serves every key to the frontend (F3), and keys remain in plaintext YAML rather than a keyring (accepted design deviation from the packet's directive). |

---

## 2. Findings (most severe first)

### F1 — CONFIRMED (High): peer:// turns break the production streaming path; home-variant chat answers die on a URL-scheme error

- **Files:** `halbert_core/halbert_core/dashboard/routes/agent.py:1052-1106` (`_stream_turn` wire dispatch), `agent.py:1001-1022` (`stream()` fallback), `agent.py:646-682` (`_fallback_to_guide`); contrast `halbert_core/halbert_core/model/client.py:503-510` (`_call_peer` deliberately raises `NotImplementedError` on `stream=True`).
- **Scenario:** Since U6/S3, a home variant pairs to a workstation and `POST /api/peers/compute-peer` sets **both** `chat_model` and `specialist_model` to model `auto` at a `peer://host:8000` endpoint (`dashboard/routes/peers.py:344-368`). The answering turn is the streaming one: `AgentStateMachine._generate_response` prefers `stream()` whenever the client exposes it (`agents/state_machine.py:2770`), and `LLMClientAdapter` always exposes it. `_resolve_turn_model` correctly returns `TurnModel(provider="peer", endpoint="peer://…")`, but `_stream_turn` has no `peer` branch — `peer` is not in `OPENAI_COMPATIBLE_PROVIDERS` (`client.py:68`), so the turn falls into the Ollama wire and posts to `peer://host:8000/api/chat` via aiohttp, which raises `NonHttpUrlClientError` (**reproduced empirically**). The handler converts it to `_ModelUnreachable`; `_fallback_to_guide` returns `None` because on a home variant the guide *is* the same `auto`@peer slot; the user sees `[Error: peer://host:8000/api/chat]`. Note the asymmetry: PLANNING works (it goes through `chat()` → `call_llm_chat` → `_call_peer`), so the model plans, executes tools, and then fails to answer.
- **Additional irony:** `_call_peer`'s deliberate loud `NotImplementedError` ("fail loudly rather than returning a non-streaming body") is unreachable from this path — the streaming adapter builds its own request and fails *quietly* with a mangled error instead.
- **Mitigating context:** the workstation side of the compute contract is still a TODO(federation-9.3) stub (`federation/compute_endpoint.py:_submit_to_broker` raises), so no real home deployment can chat end-to-end today. The defect is nonetheless real and will bite the moment the workstation side ships — and it makes the failure mode silent where the design demanded loud.
- **Suggested fix:** in `LLMClientAdapter.stream`, detect `turn.provider == "peer"` and delegate to the non-streaming `chat()` (via `asyncio.to_thread`), yielding the buffered content as one chunk — or add a `peer` branch to `_stream_turn` once federation-9.4 gives the compute endpoint an SSE path. Either way the state machine's `hasattr(stream)` check should not be the only signal that streaming is possible.

### F2 — CONFIRMED (High): Apple Intelligence auto-provision assigns live slots to a bridge that does not exist, without consulting the bridge-running flag it computes

- **Files:** `halbert_core/halbert_core/model/auto_provision.py:69,99-109` (gates on `apple_intelligence_available` only), `model/hardware_detector.py:296-315` (sets `apple_intelligence_available = apple_intelligence_eligible()` and separately computes `apple_intelligence_bridge_running`), `model/config_wizard.py:467-489` (`ai_takes_chat` overrides even a user-chosen Ollama model).
- **Scenario:** `halbert-foundation-bridge` (the Swift sidecar on 127.0.0.1:11435) is a "separate deliverable" and is **absent from this repo** (verified: no Swift sources, no sidecar config). Yet on any Apple-Silicon Mac with macOS ≥ 15.1 and 16-24GB unified memory, first `GET /api/llm/config` (`dashboard/routes/llm.py:213-222`) and the config wizard both assign `chat_model` (and always `secure_model`) to the `apple-foundation` endpoint. Every chat turn then dead-ends: connection refused → `_ModelUnreachable` → `_fallback_to_guide` → guide is the same dead endpoint → `[Error: …]`. Worse, in the wizard `_build_config`, `ai_takes_chat` **overrides** a local Ollama model the user explicitly picked (`config_wizard.py:483-489`): on a 16-24GB Mac the wizard silently points chat at the unbundled bridge even when a working local model was just configured. Secure turns degrade more gracefully (the gate falls to a local guide), but each one pays a failed round trip plus an error log first.
- **The specific defect:** `HardwareDetector.detect()` computes `apple_intelligence_bridge_running` one branch away from the eligibility flag, and neither `auto_provision_apple_intelligence` nor the wizard's slot assignment ever reads it. Registering the *endpoint* while inert is documented and fine (`llm_config.ensure_apple_foundation_endpoint` docstring); assigning *slots* is not inert — it is the difference between "inert until the bridge exists" and "chat is broken until the bridge exists".
- **Suggested fix:** gate slot *assignment* (not endpoint registration) on `hardware.apple_intelligence_bridge_running`, or at minimum on the wizard only when the user did not choose a local model; surface "eligible, bridge not started" in Settings as the wizard's status line already does (`config_wizard.py:238`).

### F3 — CONFIRMED (Medium, security): `GET /api/llm/config` returns every saved provider API key in plaintext to the frontend

- **Files:** `halbert_core/halbert_core/dashboard/routes/llm.py:148-176` (`_effective_block` and `_editor_payload` return `layered.effective` / `layered.global_config` verbatim, both of which carry `saved_endpoints[].api_key` through `normalise`).
- **Scenario:** Opening Settings → AI Models fetches `/api/llm/config`; the response body — and therefore React state, devtools, and anything riding an XSS in the dashboard — contains every cloud provider key in cleartext. The write path provably does not need them: `llm_config._carry_forward_api_keys` (`llm_config.py:694-717`) re-attaches stored keys to any endpoint that omits them, and the frontend "cannot echo a secret back just to rename an endpoint" by design. The packet's directive ("never exposed in plaintext frontend state dumps") is therefore not met.
- **Suggested fix:** redact `api_key` in both blocks of the editor payload (e.g. `""` or a `"key_set": true` marker). Round-trips keep working via carry-forward; a deliberate clear still works because the frontend sends an explicit `api_key: ""` (carry-forward skips keys that are present).

### F4 — CONFIRMED (Medium): images are never translated for OpenAI-compatible or Anthropic wires — vision slots only work on Ollama-family endpoints

- **Files:** `halbert_core/halbert_core/model/client.py:555-563` (`_call_openai_compatible` passes `messages` verbatim, so the Ollama-shaped `"images": [base64…]` field goes out unchanged), `client.py:593-607` (`_anthropic_payload` never reads `images` — silently dropped), `dashboard/routes/agent.py:1062-1068` (streaming OpenAI branch, same verbatim pass), `agent.py:1079-1096` (streaming Anthropic branch, same silent drop). No `image_url` conversion exists anywhere in the tree (grep-verified; the only OpenAI-style image translation lives in the unused-by-this-path `providers/anthropic.py`).
- **Scenario:** A user configures the vision slot to a cloud OpenAI-compatible vision model (or LM Studio) and attaches a screenshot. The turn resolves to vision, `_attach_images` hangs the base64 on the user message, and the request goes out with an `images` key no OpenAI-compatible server accepts — a strict endpoint answers 400 (the tool-fallback retry without tools also 400s, since the bad field is in `messages`, not `tools`), and the turn falls back to text. On Anthropic the image is silently discarded and the model answers *blind* about a picture it never saw — silent data loss, the worst variant. On the streaming path both variants reproduce identically.
- **Suggested fix:** translate `images` per wire at the payload builders: OpenAI content-parts (`[{"type":"image_url","image_url":{"url":"data:image/jpeg;base64,…"}}]`) and Anthropic `image` blocks. Until then, restrict the vision slot in the picker to Ollama-family endpoints or log loudly when images are dropped.

### F5 — CONFIRMED (Medium): the GPU advisory lock is not taken on the production streaming path, serialises everything when it is taken, and its comment contradicts its code

- **Files:** `halbert_core/halbert_core/model/client.py:336-345` (lock only wraps `call_llm_chat`), `client.py:154` vs `client.py:166` ("shared lock, so multiple readers are OK" — code takes `LOCK_EX`), `client.py:97` (`_LOCK_TIMEOUT_S = 30`).
- **Scenario (coverage gap):** the lock exists to keep Halbert and the SourcePrep pipeline from loading models onto the same VRAM simultaneously. But the call that actually triggers a model load — the streaming answer turn, including the num_ctx high-water resize that forces an Ollama reload — builds its own aiohttp request in `_stream_turn` with no lock at all. Only the short planning/complexity calls (`call_llm_chat`, all `stream=False`) are serialized. The lock therefore protects the cheap calls and ignores the expensive one; it is largely decorative against the failure it was built for.
- **Scenario (fail-open cost):** because the lock is exclusive and held for the *entire* call, a second local-GPU call during a long planning call blocks the full 30s and then proceeds anyway. Fail-open is documented as deliberate, but the 30s stall before failing open is the worst of both worlds for the waiting turn; a shared (`LOCK_SH`) lock for read-only inference, or a short hold covering only the model-load probe, would match the stated intent ("multiple readers are OK").
- **Crash safety (resolved):** POSIX `flock` is released by the kernel on process death, so the packet's stale-lockfile-hang concern does not apply on macOS/Linux. Windows is a different story (F9).
- **Suggested fix:** take the lock in `_stream_turn` (or hoist request execution for local-GPU providers through a shared helper), and either switch to `LOCK_SH` or fix the comment.

### F6 — CONFIRMED (Low, latent): `call_llm_chat(stream=True)` is broken for every adapter — `response.json()` on an SSE/NDJSON body

- **Files:** `halbert_core/halbert_core/model/client.py:573-575` (`_call_openai_compatible`), `client.py:755-757` (`_call_ollama`).
- **Scenario:** with `stream=True` and no tools, Ollama answers NDJSON and OpenAI-compatible endpoints answer SSE; both adapters then call `response.json()`, which raises. Every production caller currently passes `stream=False` (verified by enumerating all `call_llm_chat` call sites), so this is latent — but the API advertises the parameter, the peer adapter alone fails loudly (`_call_peer` raises `NotImplementedError` for `stream=True`), and the next caller to pass `stream=True` gets a confusing JSON decode error instead of a clear one.
- **Suggested fix:** either raise `NotImplementedError("streaming is not supported by this transport")` in `call_llm_chat` for all providers (matching `_call_peer`), or implement iteration over the streamed body.

### F7 — CONFIRMED (Low): TierRouter caches models.yml for the life of the process; Settings edits never reach the cognition path

- **Files:** `halbert_core/halbert_core/model/tier_router.py:252-262` (config loaded once in `__init__`), `tier_router.py:328-341` (`refresh()` reloads **only** when the bound session changed), `integrations/app_seam.py:138-162`.
- **Scenario:** `llm_config`'s parse cache is built on the promise that "an edit made while Halbert is running is picked up by the next read, which is existing, relied-on behaviour". `chat`/`vision`/planning honour it (they resolve per call); the TierRouter seam — which drives the cognitive tick's thought generation — does not: a user who swaps the chat model in Settings leaves cognition generating on the old (possibly removed) model until the process restarts or a different session binds. The failure is quiet: the router's own health cache then reports the stale model unhealthy and cognition silently falls back.
- **Suggested fix:** extend `refresh()` to also reload when the store's file identity (`llm_config.global_config_path()` mtime/size) changed, not only on session change.

### F8 — CONFIRMED (Low): `is_model_loaded` family-prefix match returns false positives

- **File:** `halbert_core/halbert_core/model/client.py:1494` — `if model_name.startswith(loaded_name.split(":")[0]): return True`.
- **Scenario:** with `llama3:8b` loaded, asking for `llama3.1` (or `llama3.70b`) returns True because `"llama3.1".startswith("llama3")` — a *different model family* counts as loaded. Affects the Settings model-management surfaces that use it (`dashboard/routes/settings.py:78-82`); at worst the UI suppresses a needed pull, so low impact.
- **Suggested fix:** match on `loaded_name.split(":")[0] == model_name.split(":")[0]` (exact family) rather than prefix.

### F9 — CONFIRMED (Low, Windows-only): O_EXCL lock steals a live holder's lock after 5 minutes

- **File:** `halbert_core/halbert_core/model/client.py:135-143`.
- **Scenario:** on Windows the lock is a file whose mtime is its creation time. A holder that keeps the lock for more than 300s (a long planning call; the POSIX side holds across a 180s timeout routinely) has a lockfile older than the staleness threshold, so a second process unlinks it and acquires — both processes then believe they hold the lock. Two waiters can also both unlink-and-recreate in the staleness race. Windows is not a first-class target, hence Low.
- **Suggested fix:** refresh the lockfile's mtime while held (heartbeat), or write the pid and check liveness rather than age.

### PLAUSIBLE findings (could not be fully substantiated; recorded for the next pass)

- **P1 — `llm_config.update()` lost-update race** (`llm_config.py:720-739` with `save()` at `669-682`): `update()` reads uncached, merges, then `save()` re-reads fresh bytes but writes the *merged payload built from the earlier read* — a concurrent writer (dashboard picker save vs wizard vs peer pairing) landing in that window has its `llm_config` changes lost. Narrow window, single-machine, multi-process Halbert is a real deployment shape (dashboard + CLI wizard). A compare-on-identity (optimistic concurrency on the file stamp) in `save()` would close it.
- **P2 — `HALBERT_MODEL` override silently disabled** (`llm_config.py:813-819`): `_env_chat_model_override` returns None on *any* exception importing `cognition_wiring`, not just variant-resolution failure — an unrelated import error in integrations silently turns the documented deployment dial off with no log line. At minimum log the exception.
- **P3 — token estimate underestimates CJK** (`client.py:1226-1248`, 4 chars/token): a CJK prompt is ~1-2 chars/token, so `num_ctx` is undersized for CJK users and Ollama truncates the prompt head — the exact failure this module exists to prevent. The loud warning does fire, so it is degradation, not silence.
- **P4 — AMD VRAM never parsed** (`hardware_detector.py:366-381`): the rocm-smi branch returns `None` by design ("simplified"), so AMD-GPU hosts are budgeted from system RAM with CPU-provider notes. Acknowledged in code; listed because it silently changes the recommended budget on a supported platform.

---

## 3. Packet claims now resolved (superseded or already fixed)

1. **`model/lock_manager.py` / `tests/test_model_lock.py` no longer exist** (packet §3/§4). The advisory lock was vendored inline as `client.py::llm_advisory_lock`; the packet's verification command (`pytest halbert_core/tests/test_model_lock.py …`) is not runnable. Crash-safety is better than the packet's ask: POSIX `flock` needs no stale-file cleanup at all.
2. **Packet §5.1 (GPU deep-scan refactor):** `dashboard/routes/gpu.py` `POST /analyze` is now marked deprecated and dispatches the agent tool framework rather than raw Ollama calls (`routes/gpu.py:11,316`). Resolved.
3. **Packet §5.2 (tool-calling payload adaptation):** JSON-schema tool calls are serialised per wire (Ollama/OpenAI verbatim, Anthropic `input_schema`), arguments decoded from OpenAI's JSON-string form, and the retry-without-tools registry is evidence-based. Resolved for every supported wire. (Image payloads are the remaining translation gap — F4.)
4. **Packet §6 deadlock directive:** satisfied on POSIX by construction (kernel releases the lock on process death); `finally` cleanup is present on both platforms. Windows staleness has the F9 race.
5. **Packet credential directive (keyring):** deliberately not implemented — keys live in plaintext `models.yml` hardened to 0600 with atomic writes and a 0600 `.bak`. Acceptable as a documented deviation, but F3 (keys served to the frontend over the API) is *not* covered by that decision and should be fixed regardless.
6. **Post-packet changes the packet could not know about, verified correct:** `secure_model` is sysadmin-only and home variants skip it consistently at every read site (agent `_resolve_turn_model`, tier_router, auto_provision, wizard); the peer provider is registered across the model stack (CHAT_CAPABLE_PROVIDERS, normalise, TierRouter, providers package) with `secure_model` peer-ineligible at two enforced layers; Apple Intelligence is never a peer backend (compute listing/broker docstrings and slot rules; listing is still a TODO(federation-9.3) stub); `HALBERT_MODEL` fills only an *empty* chat slot and is variant-gated, home-excluded, with tests.

---

## 4. Recommended follow-up order

1. **F1** (peer streaming) — required before the federation-9.3 workstation side ships; cheap fix in `LLMClientAdapter.stream`.
2. **F2** (bridge-running gate) — user-visible breakage on every eligible 16-24GB Mac today; one-line gate plus wizard override removal.
3. **F3** (key redaction in `/api/llm/config`) — small change, existing carry-forward makes it safe.
4. **F4** (image translation) — gates the vision slot to Ollama until done.
5. **F5** (lock coverage/exclusivity) — decide whether the lock is real (take it on the streaming path) or theatre (drop the 30s block).
6. F6-F9, P1-P4 as opportunity cost allows.