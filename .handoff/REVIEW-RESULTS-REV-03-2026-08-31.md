# REV-03 Review Results — Sentient Home Architecture (HA, Wyoming, Frigate, Multi-Instance)

**Date:** 2026-08-31
**Reviewer:** GLM-5.3 (adversarial review with verification)
**Packet:** `.handoff/REVIEW-PACKET-03-SENTIENT-HOME-AND-VOICE.md` (2026-08-29), reviewed against CURRENT code per the 2026-08-30 simplification addendum (no secure_model on home variants, no SourcePrep retrieval, Compute Peer setting replaces the model picker, HA-config bridge retired).
**Tree:** worktree `central-todo-batches`, branch `worktree-central-todo-batches`

## 0. Overall verdict

**FAIL — significant defects.** The simplification addendum items (S1/S2/S3) are correctly landed and the packet's open items 5.1/5.2 are resolved, but the sentient-home perception pipeline as shipped is **disconnected dead code with an unbounded memory leak**, physical-actuator governance is bypassable on two of its three call paths, and the Wyoming server violates the protocol it claims to implement in two ways that prevent real Home Assistant integration. 14 findings: **12 CONFIRMED, 2 PLAUSIBLE** (one CONFIRMED finding carries a PLAUSIBLE exploit-chain variant). Test suite at HEAD: 163 passed, 5 failed — one failure exposes a production bug (F11), the rest are mock misuse / test drift.

---

## 1. Verdicts per area

| Area | Verdict | Key findings |
|---|---|---|
| HA event stream & cognition wiring | **FAIL** | F1 (perception disconnected, unbounded queue), F10 (cross-loop stop), F11 (sensor debounce dead code), F13 (stale config after token rotation) |
| HA client / config / credential handling | **FAIL** | F5 (token file 0644), F6 (startup seeding clobbers dashboard config), F9 (legacy env-var isolation gap) |
| Dashboard home routes | **FAIL** | F2c (`/api/home/service` ungated), F8 (frontend role/variant divergence) |
| Autonomy & governance enforcement | **FAIL** | F2 (gate wired only into MCP; Level-2 confirmations are a dead end; `observe` not enforced on chat) |
| Wyoming voice agent | **FAIL** | F3 (describe→describe handshake reply), F4 (audio-chunk frame desync), F12 (per-turn client leaks) |
| Frigate NVR (client, routes, MQTT) | **PASS** (with one leak pattern, F12b) | Clean client lifecycle in routes; masked-credential save handling; the only cross-loop-safe `stop()` in the codebase |
| Variant gating (`app.py`, `cognition_wiring.py`) | **FAIL** | F7 (`home-light` divergence), F8 (persona-vs-variant role), F1 (HA stream ungated by variant) |
| Multi-instance isolation | **FAIL** | F9 (legacy env var), F6 (cross-instance file clobber when data dirs collide) |
| Packet open items 5.1 / 5.2 / simplification S1–S3 | **PASS** | See §4 resolved list |

---

## 2. Findings (most severe first)

### F1 — CONFIRMED (Critical) — HA events never reach cognition; the pending-event queue grows without bound
**Files:** `halbert_core/halbert_core/integrations/cognition_wiring.py:295-301` (composite excludes the HA mapper), `cognition_wiring.py:388-414` (`start_ha_event_stream`), `halbert_core/halbert_core/dashboard/routes/agent.py:196-198,264`, `halbert_core/halbert_core/home/cognitive_loop.py` (only `populate_cognition` consumer, **never instantiated anywhere**), `halbert_core/halbert_core/integrations/home_assistant/ha_event_mapper.py:34-46`.

**Scenario:** `dashboard/app.py` startup calls `start_ha_event_stream()` (on *every* variant, not just home) whenever HA is configured. The stream forwards each filtered `state_changed` event to `HAEventMapper.add_event`, which appends to `_pending_events`. Grep-verified consumers of `HAEventMapper.populate_cognition`: only `HomeCognitiveLoop._flush_events_to_cognition` — a class with **zero instantiation sites** in the tree — and `state_machine.py:2620`, whose `event_mapper` is the `CompositeEventMapper` built in `get_event_mapper()` from `SystemEventMapper` + Frigate only. The HA mapper is not in that composite. Consequences:
1. The persona never learns anything from the house: no lock/alarm worries, no occupancy observations, no emotion events — the entire "sentient home" perception layer is dead wiring despite an active WS connection.
2. `_pending_events` (a plain list, never drained) grows for process lifetime. Every light/switch/cover/person/media_player state change appends a dict including full `attributes` (media_player attributes are large). On a home node running for weeks this is a monotonic memory leak.

**Fix:** add the HA mapper to the `CompositeEventMapper` in `get_event_mapper()` (it becomes the intended consumer until the cognitive loop is wired), and cap `_pending_events` (drop oldest / coalesce per entity) so a quiet agent can't accumulate unbounded state. Either instantiate `HomeCognitiveLoop` at startup or delete it; do not ship the mapper/loop half-wired.

### F2 — CONFIRMED (High) — Physical-actuator governance/autonomy is enforced on only one of three call paths
**Files:** `halbert_core/halbert_core/integrations/home_assistant/ha_tool.py:94-127` (chat tool handler), `halbert_core/halbert_core/dashboard/routes/home.py:140-153` (`POST /api/home/service`), `halbert_core/halbert_core/integrations/home_assistant/autonomy_gate.py`, `halbert_core/halbert_core/mcp/server.py:395-470` (the only AutonomyGate wiring), `halbert_core/halbert_core/config/being_config.py:243` (`observe` = "No device commands ever").

Three paths can drive HA, and only the MCP path consults `AutonomyGate`:
- **(a) Chat tool ignores `autonomy_level`.** `_ha_call_service_handler` runs `HAGovernancePolicy.classify` only. At `autonomy_level: observe` — defined as "perceive and report only. No device commands" — governance Level 0/1 calls (`light.*`, `cover.*`, `switch.*`, `scene.*`, unknown domains default to Level 1) execute immediately through the agent. The gate exists but nothing on the dashboard/agent path references it.
- **(b) Level-2 confirmation is a dead end.** For `lock`/`alarm_control_panel` the handler returns the same "Confirmation required … Please confirm this action." string on *every* call — there is no confirmation state, no second-phase executor. Locks and alarms can therefore **never** be operated via chat at any autonomy level, while the "user is in the loop" confirmation the design promises is unimplementable as written.
- **(c) `POST /api/home/service` has no gating at all.** It calls `client.call_service(domain, service, data)` directly — no governance, no autonomy, no role check. Any HTTP client that can reach the dashboard can `lock.unlock` or `alarm_control_panel.alarm_disarm`. Default bind is `127.0.0.1` via `dashboard/__main__.py`, but `dashboard/app.py:830`'s `__main__` fallback binds `HALBERT_HOST` default **`0.0.0.0`** — the two entry points disagree, so a LAN-exposed launch exposes unauthenticated actuator control. **PLAUSIBLE exploit chain** (depends on the operator binding non-loopback); the code-level bypass is CONFIRMED.

**Fix:** route the chat handler through `AutonomyGate` (gate from `BeingConfig.autonomy_level/autonomy_overrides` exactly as `mcp/server.py` does); make `requires_confirmation` a real two-step flow (approval request → `approvals` route → execute) or explicitly scope chat to Level 0/1 and hard-block Level 2; put governance+autonomy in `/api/home/service` (or gate the route to the dashboard's own UI with an approval step); align the two `__main__` bind defaults.

### F3 — CONFIRMED (High) — Wyoming handshake reply violates the protocol: replies `describe` instead of `info`
**File:** `halbert_core/halbert_core/integrations/wyoming_agent.py:287-301`.

**Scenario:** the canonical Wyoming handshake is: client sends `{"type":"describe"}`, server replies with an `info` event (verified against the Wyoming protocol docs — see sources in §5). The agent replies with `{"type":"describe", "data": {...}}`. A real Wyoming client (Home Assistant's Wyoming integration, `wyoming-satellite`) waits for `info`, never receives it, and drops/errors the connection. The packet's claim of "zero-latency Home Assistant Voice Assistant integration" cannot work against any real Wyoming peer; the server currently only interops with a hypothetical client that speaks this custom dialect. (HA Assist integration actually works via the separate HACS custom component in `custom_components/halbert/`, which is a different path than this packet claims.)

**Fix:** reply `{"type":"info","data":{"name":"halbert","description":...,"versions":[...]}}` per the spec, and handle the version negotiation (`synthesize`/`describe` version fields).

### F4 — CONFIRMED (High) — `audio-chunk` frames corrupt the TCP stream; the "ignored" claim is false
**File:** `halbert_core/halbert_core/integrations/wyoming_agent.py:283-285` (comment claims "Ignore audio data"), contrast `halbert_core/halbert_core/audio/ingress/wyoming_ingress.py:12-18`.

**Scenario:** a real `audio-chunk` event is a JSON header line with `payload_length: N` followed by N bytes of raw PCM (spec-verified). The agent's `readline()` loop parses the header fine (type `audio-chunk`, no branch side-effects) but then **reads the PCM bytes as the next "line"** — `json.loads` on partial PCM fails (log spam per chunk), and any `0x0A` byte inside the PCM splits the payload arbitrarily, permanently desynchronizing the frame stream. Every subsequent `transcript` message on that connection is lost. The codebase's own `wyoming_ingress.py` docstring states this plainly ("BREAKS on audio-chunk frames — the readline parser tries to parse raw PCM bytes as JSON") but the agent was never fixed or documented as text-only-only. Combined with F3, any satellite streaming audio to port 10400 wedges the connection.

**Fix:** either reject/`readexactly(payload_length)`-drain audio frames in the agent (making "ignore" true), or have `start()` reply `info` with no `stt` stage so satellites never send audio here; document the text-only contract.

### F5 — CONFIRMED (High) — HA long-lived access token written world-readable (0600 only for Frigate)
**Files:** `halbert_core/halbert_core/integrations/home_assistant/ha_config.py:82-87` (`save_ha_config` → plain `Path.write_text`, i.e. 0644 under default umask), contrast `halbert_core/halbert_core/integrations/frigate/frigate_config.py:128-143` (explicit `0o600` "because the file contains API keys and MQTT passwords").

**Scenario:** the HA long-lived access token grants full house control via HA's REST API (locks, alarm panel, garage). `ha_config.json` in the data dir is created with default permissions, so any local user/process on a shared HAOS/Linux box can read it. The Frigate module already contains the correct pattern — the HA module predates it and was never aligned. (`being.yml` also stores `ha_token` in plaintext YAML; it's user-owned, but the same 0600 discipline should apply to `save_being_config`.)

**Fix:** write `ha_config.json` with `os.open(..., 0o600)` exactly as `save_frigate_config` does; chmod existing files on load.

### F6 — CONFIRMED (High) — Home-variant startup clobbers the dashboard-saved HA config on every boot
**File:** `halbert_core/halbert_core/dashboard/app.py:649-660`.

**Scenario:** on the home variant, if `being.yml` carries `ha_url`+`ha_token`, startup calls `save_ha_config(HAConfig(url=..., token=...))` — a **full overwrite** of `ha_config.json` with defaults for everything else. `routes/home.py:76-93` lets the user set `verify_ssl` and `visible_domains` (and rotate the token) via the Home panel; every restart silently reverts them. Concrete failure: user with a self-signed cert sets `verify_ssl: false` in the dashboard → works until restart → SSL verification re-enabled → all HA calls fail; a token rotated in the panel is silently replaced by the stale `being.yml` token after reboot.

**Fix:** seed only when `ha_config.json` doesn't exist, or merge (fill only missing url/token fields), preserving `verify_ssl`/`visible_domains`; never overwrite an operator-edited file from an unedited source.

### F7 — CONFIRMED (Medium) — `home-light` variant gating divergence
**Files:** `halbert_core/halbert_core/model/llm_config.py:816` (`_get_variant() in ("home", "home-light")`), contrast `halbert_core/halbert_core/integrations/cognition_wiring.py:105` (`HA_VARIANTS = ("home",)`), `dashboard/app.py:427-433` (`_is_home = _variant == "home"`), `config/being_config.py:33` (`VALID_VARIANTS = {"sysadmin","home"}`).

**Scenario:** the design docs (`HANDOFF-AUDIO-AI-ARCHITECTURE-AND-UX-2026-08-29.md` and the simplification addendum) treat `home-light` as a real planned variant (Linux homelab, pure compute client). `llm_config` already special-cases it (HALBERT_MODEL override disabled), but every other gate keys on `"home"` only, and being.yml validation rejects `variant: home-light` while the **unvalidated** env path accepts it. With `HALBERT_VARIANT=home-light`: the node starts ingestion, discovery scan, scheduler, terminal reaper and the secure-model wizard (`config_wizard.py:479`, `auto_provision.py`, `tier_router.py:155` resolve a `secure_model` slot) — exactly the sysadmin services the simplification forbids on a light node — **and** is refused the Compute-Peer link/probe routes (`routes/peers.py:335-341`, `routes/compute.py:315-321` return NOT_HOME_VARIANT), i.e. the one variant that is only a compute client is denied its only LLM route. Latent today (nothing deploys home-light yet) but the divergence is already in the tree and the failure mode is severe.

**Fix:** make `HA_VARIANTS = ("home", "home-light")` the single source (or a `is_home_variant()` predicate consumed by llm_config), add `home-light` to `VALID_VARIANTS`, and validate env-provided variants (a typo like `Host` currently silently behaves as sysadmin).

### F8 — CONFIRMED (Medium) — Frontend feature gating keys off persona_id, not variant
**Files:** `halbert_core/halbert_core/dashboard/routes/instance.py:27-45` (`role = "host" if persona_id == "halbert" else "home"`), `dashboard/frontend/src/components/Layout.tsx:177` (`/home` nav hidden unless `features.home`).

**Scenario:** the docs say `being.yml` is "the single file a home user needs to deploy". A home node configured with `variant: home` in being.yml and no `HALBERT_PERSONA_ID`/`persona_id_override` gets `persona_id == "halbert"` → `role: "host"` → `features.home: false` → the **Home tab is hidden in its own UI**, while Development/GPU tabs are shown and the backend simultaneously runs home-gated (services skipped, secure gate skipped). The code comment in `instance.py` acknowledges variant must reach the frontend ("Same resolution as backend service gating") but `role`/`features` still derive from persona id. The backend/frontend gating can disagree in both directions.

**Fix:** derive `role`/`features` from `_get_variant()` (with persona id as a display label only), or require `persona_id_override` whenever `variant: home` is set (validation at config load).

### F9 — CONFIRMED (Medium) — Legacy env-var isolation gap: HA/Frigate credentials ignore `Halbert_DATA_DIR`
**Files:** `halbert_core/halbert_core/integrations/home_assistant/ha_config.py:57-61`, `halbert_core/halbert_core/integrations/frigate/frigate_config.py:93-98` (both check only `HALBERT_DATA_DIR`), contrast `halbert_core/halbert_core/utils/platform.py:344`, `utils/paths.py:50`, `integrations/cognition_wiring.py:33` (all honor legacy `Halbert_DATA_DIR`).

**Scenario:** the codebase explicitly supports the legacy `Halbert_DATA_DIR`/`Halbert_CONFIG_DIR` spellings for multi-instance isolation (and `cognition_wiring` maps it onto `HALOYSIUS_DATA_HOME`, so persona memory *is* isolated). An instance isolated with only the legacy var writes its `ha_config.json`/`frigate_config.json` to the **default shared** `~/.local/share/halbert`. Two simultaneous host+home daemons configured this way share one credential file: the home instance's startup seeding (F6) overwrites the host instance's HA settings, and either instance reads the other's HA/Frigate tokens — precisely the cross-instance collision the packet's multi-instance directive asks about.

**Fix:** both `_config_path()` helpers should call `get_data_dir()` (which already handles both spellings) instead of re-implementing a partial resolution.

### F10 — CONFIRMED (Medium) — Cross-loop shutdown: HA event stream and Wyoming agent can never be stopped cleanly
**Files:** `halbert_core/halbert_core/dashboard/app.py:661-680` (HA stream), `682-700` (Wyoming), `779-787` and `799-807` (shutdown awaits), `ha_event_stream.py:96-109` (`stop()`), `wyoming_agent.py:332-339` (`stop()`), contrast `frigate_mqtt_subscriber.py:76-103` (explicitly cross-loop-safe via `call_soon_threadsafe`).

**Scenario (empirically reproduced):** the stream/agent run on dedicated event loops created in daemon starter threads (`loop.run_until_complete(start())` + `loop.run_forever()`). The FastAPI `shutdown` event runs on uvicorn's loop and does `await _ha_event_stream.stop()` / `await _wyoming_agent.stop()`, which await futures bound to the dedicated loop. Repro on this machine (Python 3.10, venv): awaiting a foreign-loop task raises `RuntimeError: Task ... got Future ... attached to a different loop`. Both stop calls always land in the `except` → "Failed to stop ..." warning; the WS connection, TCP server and aiohttp sessions are never closed, and `cognition_shutdown()` drops the `_ha_event_stream` reference while the task is still running. The Frigate subscriber's `stop()` shows the correct pattern — it was fixed there and not in the other two. Impact is bounded (daemon threads die at process exit) but graceful shutdown, hot-reload and test teardown all leak, and the shutdown log is permanently lying ("stopped" vs actually stopped).

**Fix:** adopt the Frigate subscriber's pattern (store the owning loop; from a foreign loop use `call_soon_threadsafe` to schedule stop and wait via an event), and stop the stream inside `cognition_shutdown()` before nulling it.

### F11 — CONFIRMED (Medium) — `sensor` domain dropped before the debounce check: `DEBOUNCE_DOMAINS` is dead code; test fails at HEAD
**File:** `halbert_core/halbert_core/integrations/home_assistant/ha_event_stream.py:27-41` (`FILTERED_DOMAINS` has no `sensor`), `:193` (domain filter returns first), `:206-212` (unreachable debounce).

**Scenario:** `test_ha_phase2.py::TestHAEventStream::test_debounce_sensor` **fails at HEAD** at its first assertion (first sensor event expected to pass the callback, got 0 calls): `_process_state_changed` returns at the `domain not in FILTERED_DOMAINS` guard before the `DEBOUNCE_DOMAINS` logic can run. No telemetry sensor ever reaches cognition, contradicting the module docstring ("debounces telemetry sensors") and the test. Either the domain filter should include `sensor` (so the 30s debounce forwards one value per window, as designed) or the debounce block should be deleted as vestigial. Leaving it as-is means the failing test documents a real behavioral regression silently shipping.

**Fix:** add `"sensor"` to `FILTERED_DOMAINS` (debounce then applies), or remove `DEBOUNCE_DOMAINS` and update docstring + test. Either way the suite must go green.

### F12 — CONFIRMED (Medium) — aiohttp client/session leaks on the voice and MCP paths; loop-bound session reuse in the dead cognitive loop
**Files:** `halbert_core/halbert_core/integrations/wyoming_agent.py:211` (`_resolve_area_context` — new `HAClient` per voice turn, never closed), `wyoming_agent.py:383` (`proactive_speak` — same), `mcp/server.py:395-404` (`_get_ha_client` — new `HAClient` per tool call, never closed, driven by `asyncio.run`), `home/cognitive_loop.py:229,318-331` (`asyncio.run(self.ha_client.*)` per tick on a shared client).

**Scenario:** every voice turn with an `area_id` and every proactive speak creates an `HAClient`, whose `ClientSession` is created on the Wyoming thread's loop and then never `close()`d — a slow fd/session leak on a long-running always-on node; same per MCP HA tool call (each additionally spins an ephemeral `asyncio.run` loop). In `HomeCognitiveLoop` (currently dead code, F1), the pattern is worse: the shared client's session is created on tick 1's ephemeral loop and reused on tick 2's — the closed loop makes all HA perception fail silently from the second tick on (runtime errors are swallowed at debug level). If the loop is ever wired up per the design, this bug activates immediately.

**Fix:** use the `ha_tool._get_client()` singleton on the running loop, or `async with aiohttp.ClientSession()` per call; never call `asyncio.run` against a shared client. For the cognitive loop, pass a loop-owned client and run the whole loop as one async task.

### F13 — CONFIRMED (Low) — Event stream never re-reads HA config; a rotated token means silent permanent reconnect loop
**Files:** `halbert_core/halbert_core/integrations/cognition_wiring.py:388-412` (config captured once at creation), `dashboard/routes/home.py:76-93` (config save + `close_client()`), `ha_event_stream.py:111-122` (5s reconnect, auth failure not distinguished).

**Scenario:** user rotates the HA token in the Home panel. The REST client singleton is reset and works with the new token, but `HAEventStream` keeps authenticating its reconnects with the captured old `HAConfig` — `auth_failed` every 5 seconds forever, event flow dead, and the only signal is a WARNING in the log every 5s. Auth failure is also not distinguished from connection failure (no backoff cap).

**Fix:** have the save route recreate the stream (stop/restart with fresh config), or have the stream reload config on each reconnect; treat `auth_failed` as terminal (log once, stop) instead of retrying forever.

### F14 — CONFIRMED (Low) — Test drift and packet rot
**Files:** `halbert_core/tests/test_mcp_ha_tools.py:37` (expects 17 tools, 18 registered — a schema was added without updating the count), `halbert_core/tests/test_home_assistant.py` (3 `TestHAClient` failures from AsyncMock misuse: `mock_session.request` returns a coroutine that can't be used as an `async with` context — the tests never exercised the real code path and fail at HEAD), and the packet's verification command (`pytest test_home_*.py test_wyoming_agent.py test_multi_instance.py`) references files that no longer exist (`test_wyoming_agent.py` is now `test_task07_voice_turn_plumbing.py`; `test_home_*.py` collapsed into `test_home_assistant.py`/`test_ha_phase*.py`).

**Fix:** update the tool count and the HAClient mocks (patch `aiohttp.ClientSession.request` or use `aresponses`), and re-point the packet's verification command.

---

## 3. Tested evidence

`arch -arm64 /Volumes/4TB-BAD/Halbert/.venv/bin/python wt_pytest.py` over `test_home_assistant.py, test_ha_phase2.py, test_ha_phase4.py, test_ha_phase6.py, test_ha_sourceprep_variants.py, test_frigate.py, test_multi_instance.py, test_mcp_ha_tools.py, test_task07_voice_turn_plumbing.py`:

**163 passed, 5 failed**
- `test_ha_phase2.py::test_debounce_sensor` — real production bug (F11).
- `test_home_assistant.py::test_get_status_connected`, `test_call_service`, `test_get_entities_by_domain` — mock misuse (F14), pre-existing, not production defects.
- `test_mcp_ha_tools.py::test_total_tool_count` — count drift (F14).

Cross-loop stop failure (F10) reproduced standalone: `RuntimeError: Task ... got Future ... attached to a different loop` when awaiting a task from a second event loop, matching the app.py shutdown pattern.

## 4. Resolved / superseded packet claims

- **Packet §5.1 — `HALBERT_MODEL` not threaded into model resolution: RESOLVED.** `llm_config._env_chat_model_override()` (commit `7c70276d`) fills an *empty* chat slot only, and is deliberately disabled on home variants (home/home-light have no local model).
- **Packet §5.2 — missing `BeingConfig` fields: RESOLVED.** `variant`, `scene_context`, `ha_url`, `ha_token` all serialize via `being.yml` (`config/being_config.py:225-235`), with `explicit_variant()` correctly distinguishing an explicit key from the dataclass default so env fallback still works.
- **Packet claim — SourcePrep HA-config graph indexing: RETIRED per S2 (superseded, not lost).** `ha_config_bridge.py` is default-disabled (`HA_SOURCEPREP_ENABLED=0`), `/home/config-search` endpoints and the `ha_search_config` LLM tool are gone from `routes/home.py:177-182`; the bridge module remains for explicit opt-in only.
- **Packet claim — model picker on home: SUPERSEDED by the Compute Peer setting (S3), correctly implemented.** `routes/peers.py` link route saves one `peer://` endpoint into both `chat_model` and `specialist_model`, gated home-only, never touching `secure_model`; `routes/compute.py` probe reuses the PeerProvider health probe and blocks metadata hosts. `secure_model` is skipped for home variants in the agent's secure gate (`routes/agent.py:508`), the config wizard, auto-provisioning and tier router.
- **TASK-07 voice fixes (`58adce12`, `149b3e75`): VERIFIED LANDED.** Per-turn session UUID (`wyoming-{uuid}`), `conversation_id` threaded through the turn lifecycle with ThreadManager grouping, `speaker_role="unknown"` on voice turns, markdown stripping before TTS, pronunciation substitution.
- **Packet §3's `platform.py` / `os` import fix and Phase 7 variant scrutiny:** the multi-instance platform module was absorbed into `utils/platform.py` / `utils/paths.py`; variant resolution is now being.yml > env > default and reaches the frontend — the backend/frontend *agreement* claimed in the comments still has the persona-id hole (F8).

## 5. Sources consulted for protocol claims

- Wyoming protocol / event format: [rhasspy3 wyoming.md](https://github.com/rhasspy/rhasspy3/blob/master/docs/wyoming.md), [Wyoming event format reference](https://julianbei.github.io/wyoming/05-api-reference/event-format/), [Wyoming protocol reference](https://julianbei.github.io/wyoming/03-protocol/) — confirm the JSON-header + `payload_length` binary framing (the codebase's `wyoming_ingress.py` framing is correct; `wyoming_agent.py`'s readline assumption is only valid for payload-free events) and the `describe` → **`info`** handshake reply (F3).

## 6. Suggested fix order

1. F1 (wire or delete the HA perception path + cap the queue) — the architecture's centerpiece is dead and leaking.
2. F2 (autonomy/governance on all three HA call paths, real Level-2 confirmation flow, `__main__` bind alignment).
3. F3/F4 (Wyoming handshake + audio-frame draining — or explicitly document the text-only dialect and drop the "Wyoming protocol" claim).
4. F5/F6 (token file perms; stop clobbering the operator's HA config at boot).
5. F7/F8/F9 (variant gating unification: one `HA_VARIANTS` source incl. `home-light`, frontend role from variant, legacy env-var in config paths).
6. F10–F14 (cross-loop stop pattern from the Frigate subscriber, sensor debounce green test, client leaks, test drift).