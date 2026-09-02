# DISPATCH SONNET-03 — Capability registry regressions, Apple Intelligence gate, model-routing leftovers

**Owner:** a Sonnet session. **Effort:** medium; every item is line-targeted with a reproduction.
**Parent:** `.handoff/HANDOFF-STATE-OF-WORK-2026-09-01.md` §6.6. Evidence ids: `U4-18`, `R05-N1`, `U6-BUG-01`, `U6-BUG-02`, `U6-TEST-01`, `CAP-01`, `R05-F2`, `R05-F3`, `U4-20`, `STUB-01`, `PICK-02/03/04`, `U6-DESIGN-01`, `U6-25/26/27/28`, `R05-F4..F8` in `.handoff/audit-2026-09-01/AUDIT-FINDINGS-DETAIL.md`.

## Shared rules
- Fresh worktree off main: `git -C /Volumes/4TB-BAD/Halbert worktree add ~/.config/superpowers/worktrees/Halbert/s03-registry -b fix/capability-registry main`. `git branch --show-current` before every commit.
- Tests ONLY via `arch -arm64 /Volumes/4TB-BAD/Halbert/.venv/bin/python wt_pytest.py <paths>` from the worktree (wrapper at repo root after SONNET-02; else copy from `.claude/worktrees/central-todo-batches/wt_pytest.py`).
- Baseline 71 failures (`.handoff/audit-2026-09-01/pytest-main-failed-4a7bf71f.txt`); no new failures; the ones named below must go green **both in isolation and in the full suite**.
- TDD. No trailers. Never edit `MASTER-TODO.md`; results → `.handoff/RESULTS-SONNET-03-<date>.md`. Never name or recommend AI models in user-facing strings. No `prep*` MCP calls.
- Files you own: `halbert_core/halbert_core/capabilities.py`, `model/auto_provision.py`, `model/config_wizard.py`, `model/tier_router.py`, `model/cascade_router.py`, `model/llm_config.py`, `dashboard/routes/llm.py`, `dashboard/routes/compression.py`, `tests/conftest.py`, and their tests. Do not touch `agents/state_machine.py` (OPUS-01), `federation/**`/`routes/agent.py` (OPUS-03), `audio/**` (OPUS-02).

## Task 1 — Autouse registry reset (`U6-TEST-01`) — do first
`capabilities.py:348-367` holds a process-wide singleton that probes once and is never reset; `_probe_secure_model` (`:192-204`) reads the developer's REAL `models.yml` (an apple-foundation secure endpoint at `127.0.0.1:11435`). Result: 6 order-dependent failures (`test_llm_routes` 4, `test_llm_config_layers` 2) after `test_agent_model_override.py`, and `test_auto_provision.py` passing in the suite only because of that pollution. Add an autouse fixture in `halbert_core/tests/conftest.py` that calls `capabilities.reset_registry()` (exists; only `test_capabilities.py` uses it) and clears the `llm_config` caches before each test. Re-run `test_llm_routes.py test_llm_config_layers.py test_auto_provision.py test_agent_model_override.py` in both orders.

## Task 2 — Circular secure-model gate (`U4-18` / `R05-N1` / `U6-BUG-02`) (P1)
`330f641b` gated provisioning on `has_capability(CAP_SECURE_MODEL)` in `auto_provision.py:72-83`, `routes/llm.py:213-222`, `config_wizard.py:141-154` and `:492-499` (`secure_allowed = _has_secure_cap`). The probe means "a secure model is already configured" → fresh installs never provision; `test_auto_provision.py` fails 4/11 in isolation. Fix: gate provisioning and the wizard's secure write on "this variant may host a secure model" — the registry's preset/`being.yml` override for `CAP_SECURE_MODEL` without the probe, or a new `secure_model_allowed` capability — and keep the probe as the "is it configured" signal for the turn gate only. Repro command in the evidence (`HALBERT_CONFIG_DIR=<empty> … has(CAP_SECURE_MODEL)=False`). Make `test_auto_provision.py` hermetic via the conftest capability controller.

## Task 3 — Registry ignores `HALBERT_VARIANT` (`U6-BUG-01`) (P1)
`capabilities.py:264-267` uses `load_being_config().variant` (defaults sysadmin) and never consults `explicit_variant()`/env, unlike `cognition_wiring._get_variant()` (`:158-174`). The documented home deployment (`deploy/halbert-home.service` env-only) therefore gets the sysadmin preset (scheduler, ingestion, discovery, terminal all True). Resolve through `_get_variant()` (being.yml > env > sysadmin); add a `test_capabilities.py` case for env-only home. Also `U6-28`: `llm_config` still checks the retired `home-light` variant — remove.

## Task 4 — Bridge-running gate and hide `apple-foundation` (`R05-F2`, `U4-20` option b) (P1)
`auto_provision.py:69` gates on `hardware.apple_intelligence_available` only; `config_wizard.py:491` `ai_takes_chat = ai_available and mem <= 24` and `:504-506` override a user-chosen Ollama model; `hardware_detector.py:297-315` computes `apple_intelligence_bridge_running` but nobody reads it. No Swift bridge source, build script or `externalBin` exists anywhere in the repo (`U4-20`). Until a founder decides to build it: gate slot assignment on `bridge_running`, never override an explicitly chosen local model, surface "eligible, bridge not started" in Settings, and hide the `apple-foundation` provider from the picker/auto-provision when the bridge is absent. `test_auto_provision.py::_hw` defaults `bridge_running=False` and expects success — fix the test with the behaviour.

## Task 5 — `CAP_SOURCEPREP` probe (`CAP-01`) (P1)
`capabilities.py:146-163` probes `importlib.import_module('sourceprep')`; the adapter talks to a daemon over HTTP and the venv has no such package, so retrieval is silently disabled on this dev box (consumers: `context/adapters.py:432-434`, `routes/agent.py:149`). Change the probe to a config/presence check (daemon URL configured or the client's token/URL present). Test: probe True with only the daemon configured. Then decide `U6-DESIGN-01` with the founder: the registry's "probe beats preset" order (`:293-303`) silently re-enables SourcePrep on home nodes where the package is present; the U6 handoff and `deploy/README.md:126` say home never uses it. Default until ratified: make the home preset an explicit False override unless `being.yml` opts in.

## Task 6 — API keys in plaintext (`R05-F3`) (P1 security)
`routes/llm.py:148-176` returns `layered.effective` and `layered.global_config` verbatim; a saved `api_key` appears 2× in `GET /api/llm/config` and 1× in `/effective`. Redact to `""`/`key_set: true`; `_carry_forward_api_keys` (`llm_config.py:694-717`) already makes round-trips safe. Test: the key never appears in GET bodies.

## Task 7 — Model-picker cleanup leftovers (`PICK-02/03/04`, `STUB-01`)
- `PICK-02` (P1): `routes/compression.py:96-118` reads via `find_models_config()` (may resolve to the repo's `config/models.yml`), mutates the whole dict and `yaml.safe_dump`s to `write_models_config()` — no atomic rename, no `.bak`, no 0600, no normalisation, and it copies the repo's `routing:` block into the user file. Read via `llm_store.load_file()`, write via `llm_store.set_top_level('compression', …)` (`llm_config.py:653`, `:746`); one-shot strip of a stray `routing:` block.
- `PICK-03` (P2): `routing.complexity_threshold` is read on two incompatible scales — unify.
- `PICK-04` (P2): delete `model/cascade_router.py`, its tests and the two `is_enabled()` branches in `tier_router.py:552/566` (imports at `:31`, `:287`); keep `OutcomeStore` only if telemetry is wanted.
- `STUB-01` (P2): `tier_router.py:381-383` raises `NotImplementedError` for `openai` while `model/client.py:75-77` lists `openai` as chat-capable. Trace whether the dashboard chat path goes through `tier_router` for an `openai`/`llamacpp` slot; if yes it crashes at first turn — implement or route around; if `tier_router` is legacy on that path, delete the stub branches.
- `U6-25/26/27` (if SONNET-02 did not port them): dead `secure` resolution `tier_router.py:162`, stale comment `config_wizard.py:692`, test for secure-turn-skips-slot when `CAP_SECURE_MODEL` absent.

## Task 8 — Lower REV-05 items if time remains
`R05-F4` images never translated for OpenAI-compatible/Anthropic wires; `R05-F5` GPU advisory lock not taken on the streaming path; `R05-F6` `call_llm_chat(stream=True)` calls `.json()` on an SSE body; `R05-F7` TierRouter caches `models.yml` for process life; `R05-F8` `is_model_loaded` prefix false positives; `R05-P2` `HALBERT_MODEL` override silently disabled on any `cognition_wiring` import error.

## Results
`.handoff/RESULTS-SONNET-03-<date>.md`: per task, the test file(s) added, isolation + full-suite counts, and which founder decisions (`U6-DESIGN-01`, `U4-20`) you assumed.
