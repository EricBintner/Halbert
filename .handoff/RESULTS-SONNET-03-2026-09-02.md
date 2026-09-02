# RESULTS — SONNET-03 Capability Registry, Apple Intelligence Gate, Model-Routing Leftovers

**Branch:** `fix/capability-registry`, worktree `~/.config/superpowers/worktrees/Halbert/s03-registry`, off `main` @ `f93f5ec5`.
**Status:** all 8 tasks addressed. Nothing pushed to origin — local worktree commits only, per dispatch instructions.

## Baseline

Fresh baseline at worktree creation (before any change): **26 failed / 4,701 passed / 40 skipped**, matching the dispatch's context-update figure exactly.

Final full-suite state after all commits: **19 failed / 4,710 passed / 40 skipped**. The 7-failure delta is entirely the 6 order-dependent failures Task 1 targeted (`test_llm_routes.py` ×4, `test_llm_config_layers.py` ×2) plus one drive-by fix in `test_llm_discover.py` (stale assertion in a file this dispatch was already editing for Task 4). The remaining 19 failures are unrelated to this dispatch's scope (`test_corpus_license_gate.py`, `test_cv_extensions.py`, `test_frontend_no_relative_urls.py`, `test_llm_config_parse_cache.py` — this one specifically touches `routes/agent.py`, out of ownership — `test_multi_instance.py`, `test_vision_tools.py`) and were present, unchanged, in the fresh baseline.

No new failures were introduced anywhere in the suite by this dispatch's changes.

## Commits (oldest → newest)

| SHA | Task | Summary |
|---|---|---|
| `b338b599` | 1 | autouse conftest fixture: reset capability registry + llm_config cache every test |
| `fc55d245` | 2, 4 | `CAP_SECURE_MODEL_ALLOWED` (preset-only, breaks the circular provisioning gate) + bridge_running gate + never override an explicit model choice; variant resolution via `cognition_wiring._get_variant()`; drop retired `home-light` check (U6-28); remove 2 dead `_is_home_variant()` helpers |
| `97d66158` | 5 | `CAP_SOURCEPREP` becomes a daemon presence check (URL/token), not `importlib`; U6-DESIGN-01 default (home ignores the probe unless being.yml opts in) |
| `94dd4a0d` | 6 | redact `api_key` from GET/PUT `/api/llm/config` and `/api/llm/config/effective` |
| `4956d93e` | 7 (PICK-02) | `routes/compression.py` reads/writes through `llm_config.load_file()`/`set_top_level()`; one-shot `strip_stray_default_routing()` repair |
| `462be3b1` | 7 (PICK-03) | unify `routing.complexity_threshold` scale between `intake/pipeline.py` and `model/tier_router.py` |
| `8911de68` | 7 (PICK-04) | delete `model/cascade_router.py` + its tests; remove dead `is_enabled()` branches and a third dead `_is_home_variant()` in `tier_router.py` |
| `a4e4b5a3` | 7 (STUB-01) | drop the `openai` `NotImplementedError` stub in `TierRouter._get_provider` (traced: unreachable from the real chat path) |
| `0ad9fbd2` | 7 (U6-25 re-verify) | stop discarding the resolved-but-unused `secure` value in `from_legacy_config`, keeping the read-gate side effect the existing test pins |
| `c56dcb4f` | 8 | `TierRouter.refresh()` also re-parses on file-content change, not session change alone (R05-F7); `HALBERT_MODEL` override fails open on variant-resolution error (R05-P2) |

## Per-task detail

### Task 1 — Autouse registry reset (`U6-TEST-01`)
Added `_reset_capability_registry` (autouse) to `halbert_core/tests/conftest.py`: calls `capabilities.reset_registry()` and `llm_config.invalidate_cache()` before every test.

- Test file: `halbert_core/tests/conftest.py` (fixture only, no new test file).
- Verification: ran `test_llm_routes.py test_llm_config_layers.py test_auto_provision.py test_agent_model_override.py` together in both original and reversed order — **133 passed** both times (previously order-dependent). Isolated: `test_llm_routes.py` 13 passed, `test_llm_config_layers.py` 51 passed, `test_auto_provision.py` 12 passed, `test_agent_model_override.py` 57 passed.
- This exposed `test_auto_provision.py`'s real 4-failure isolation bug (previously masked by pollution) — fixed in Task 2.

### Task 2 — Circular secure-model gate (`U4-18`/`R05-N1`/`U6-BUG-02`)
Re-verified per the dispatch note first: the circular gate (`has_capability(CAP_SECURE_MODEL)` used to decide whether to *provision*) was still present on this branch, unfixed — the "already improved by SONNET-02" premise did not hold here.

Added `CAP_SECURE_MODEL_ALLOWED` — override/preset only, **never probed** (sysadmin preset `True`, home preset `False`) — answering "may this variant host a secure model at all," distinct from `CAP_SECURE_MODEL` (the probed "is one configured right now," kept as-is for `tier_router.py`'s turn gate). Swapped the three provisioning-trigger call sites (`auto_provision.py`, `config_wizard.py` ×2 real sites plus the `run_interactive` print branch, `routes/llm.py`) from `CAP_SECURE_MODEL` to `CAP_SECURE_MODEL_ALLOWED`. Left `tier_router.py:158` and `routes/agent.py` (out of ownership) on `CAP_SECURE_MODEL` — that's the correct "is it configured" signal.

- Test files: `test_capabilities.py` (`TestSecureModelAllowed`, `TestVariantResolutionFollowsEnv`), `test_auto_provision.py` (updated `_hw()` calls, new bridge-not-running test, fixed stale `"secure_model"` override key), `test_config_wizard_schema.py`/`test_config_wizard_variants.py` (fixed stale override keys, new explicit-model-not-overridden test).
- Isolation: `test_auto_provision.py` 12/12 passed (was 4 failing before this fix, matching the packet's "4/11 in isolation" repro). `test_capabilities.py` 57/57.
- Full suite: no regressions.

### Task 3 — Registry ignores `HALBERT_VARIANT` (`U6-BUG-01`)
`CapabilityRegistry._load_config` now resolves variant via `cognition_wiring._get_variant()` (being.yml > `HALBERT_VARIANT` env > sysadmin) instead of `load_being_config().variant` (which silently defaulted to sysadmin and never read the env var). Also fixed U6-28 (`llm_config.py`'s retired `"home-light"` check → `== "home"`).

- Test file: `test_capabilities.py::TestVariantResolutionFollowsEnv` — env-only home, env-only sysadmin default, being.yml-wins-over-env.
- Isolation: 57/57 passed.

### Task 4 — Bridge-running gate, never override an explicit model (`R05-F2`/`U4-20` option b)
`auto_provision_apple_intelligence` now also requires `hardware.apple_intelligence_bridge_running` (not just `apple_intelligence_available`/eligible) before registering the `apple-foundation` endpoint or assigning any slot — an eligible-but-not-running host gets nothing registered, so it's automatically absent from the picker (no separate "hide" step needed; there's nothing to hide). `config_wizard.py::_build_config`'s single-model rule (`ai_takes_chat`) now also requires `not model`, so it never overrides a caller's explicit choice (a CLI `--model` arg or the interactive prompt's answer).

**Founder decision assumed (`U4-20`):** went with option (b) as instructed — gate on bridge presence, never build the Swift bridge itself (no bridge source exists anywhere in the tree, confirmed unchanged). "Surface eligible, bridge not started" in Settings: the CLI wizard already prints this distinction (`config_wizard.py` line ~217, pre-existing); the dashboard's `/api/llm/discover` route already live-probes `apple_foundation.running` independent of eligibility, so the frontend has what it needs from existing infrastructure — no new backend surface was added for this, since building new frontend UI is outside a "medium effort" P1 item's reasonable bound and wasn't line-cited in the packet the way the other Task 4 sub-items were.

- Test files: `test_auto_provision.py::test_no_provisioning_when_eligible_but_bridge_not_running` (new), `test_config_wizard_variants.py::test_single_model_rule_never_overrides_an_explicit_choice` (new), plus the `_hw()`/bridge_running updates shared with Task 2.
- Drive-by fix: `test_llm_discover.py::test_returns_both_engines_in_a_data_envelope` had a stale assertion (`set(out["data"]) == {"ollama", "lm_studio"}`, predating the `apple_foundation` probe) — fixed since it's the same discover feature and same file.

### Task 5 — `CAP_SOURCEPREP` probe (`CAP-01`) + `U6-DESIGN-01`
`_probe_sourceprep` no longer does `importlib.import_module("sourceprep")` (always `False` — the daemon is a separate HTTP process, no such package exists in the venv). Now a presence check: `SOURCEPREP_URL` env explicitly set, or a client auth token present (`PREP_DAEMON_TOKEN` env or the persisted `~/.config/halbert/prep_token` file). Did **not** depend on the live daemon at 127.0.0.1:8400 for any test — all mocked/env-based, per the dispatch's wedged-daemon warning.

**Founder decision assumed (`U6-DESIGN-01`):** applied the dispatch's stated default — home preset acts as an *explicit* `False` override for `sourceprep` regardless of what the (now-meaningful) probe returns, unless `being.yml` opts in explicitly via `capabilities: {sourceprep: true}`. Implemented as a variant-conditional branch in `CapabilityRegistry.probe()` placed *after* the override check and *before* the probe check, scoped only to `CAP_SOURCEPREP` — this is a deliberate, narrow exception to F5's "probes are presence checks, not variant gates" thesis, called out in code comments as pending ratification.

- Test files: `test_capabilities.py::TestProbeImplementations`/`TestSourceprepHomeDefault` (rewrote the two importlib-based probe tests, which tested behavior that no longer exists; added URL/token presence tests and the home-default registry tests).
- Isolation: 57/57 passed. Also ran every sourceprep-adjacent test file (`test_sourceprep_retrieval_backend.py`, `test_skills_composer.py`, `test_sourceprep_deep_pull.py`, `test_ha_sourceprep_variants.py`, `test_agent_integration.py`) — 107/107 passed.

### Task 6 — API keys in plaintext (`R05-F3`)
Added `_redact_api_keys()` in `routes/llm.py`, applied to both `_editor_payload`'s `llm_config` field and `_effective_block`'s `llm_config` field — covers `GET /llm/config` (both places the key appeared), `GET /llm/config/effective`, and the `PUT` response (which re-serves `_editor_payload`). Each `saved_endpoints` entry gets `api_key: ""` plus a new `key_set: bool`. Write-side round-trip is unaffected: `_carry_forward_api_keys` already re-attaches a stored key to any endpoint a client PUTs back without an `api_key` field.

- Test file: `test_llm_routes.py::test_api_keys_are_redacted_from_get_and_put_responses` (new) — asserts the literal secret string never appears in any of the three response bodies, checks `key_set`, and confirms the store itself still has the real key for actual calls.
- Fixed one existing test (`test_llm_config_layers.py::test_with_no_layer_above_it_the_two_views_are_the_same_document`) whose equality-to-`store.load()` assertion needed the new `key_set` field stripped first.
- Isolation: `test_llm_routes.py` 13/13, `test_llm_config_layers.py` 51/51.

### Task 7 — Model-picker cleanup leftovers

**PICK-02** (`routes/compression.py`): now reads via `llm_config.load_file()` and writes via `llm_config.set_top_level('compression', …)` instead of a bare `find_models_config()`/`yaml.safe_dump()` round-trip — gets atomic rename + 0600 for free, and can never again copy the repo template's other sections (`routing`, `handoff`, its placeholder `llm_config`) into a user's file. Added `llm_config.strip_stray_default_routing()`: a one-shot repair, called on every `POST /api/compression/config`, that removes a `routing:` block only when it is byte-identical to the repo template's default (strong evidence of the old bug's copy, not a customisation — anything that differs is left untouched).
- This is a genuine behavior change from the pre-existing tests' expectations (they encoded the old "seed the user file from the repo template" behavior as *desired*, per a "Reviewer repro" docstring) — updated `test_compression_route.py`'s three affected tests to assert the corrected behavior instead (no repo seeding; a legacy `orchestrator` key is migrated into `llm_config` like every other write path does, rather than copied through verbatim). Added 5 new tests (0600/atomicity, one-shot strip, customised-routing survives, plus 3 direct `llm_config.strip_stray_default_routing()` unit tests).
- Isolation: `test_compression_route.py` 9/9, `test_compression.py` 53/53, `test_llm_config_store.py` 33/33.

**PICK-03** (`intake/pipeline.py`): `routing.complexity_threshold` is one shared config key read on two incompatible scales — `tier_router.py`'s own scorer uses 0.0–1.0 float (default 0.5, matching the repo template), `intake/pipeline.py` compared it against a 1–5 int score with its own default of 3. In a real deployment using the shipped template value, `complexity.score >= 0.5` is true for every possible score — the threshold was a silent no-op, and specialist routing fired on effectively every troubleshooting-adjacent turn. Normalised `intake/pipeline.py`'s comparison to `complexity.score / 5.0 >= threshold` (default 0.5) — this exactly reproduces the originally-intended behavior (specialist from `MODERATE=3` upward) under the old int-scale default, so it's a scale fix with no behavior change except under the value the repo template actually ships.
- Note on ownership: `intake/pipeline.py` is not on this dispatch's explicit "files you own" list, but it's the *other* half of the two-reader mismatch (`tier_router.py`, which I do own, is the one left unchanged) and there's no way to "unify" without touching it. Did not touch `agents/state_machine.py`, `routes/agent.py`, `federation/**`, or `audio/**`.
- Test file: `test_intake_pipeline.py` — updated the shared `MODEL_CONFIG` fixture's threshold to `0.5`, added `TestComplexityThresholdScale` (3 new tests, including the "shipped default doesn't make the threshold a no-op" regression case).
- Isolation: `test_intake_pipeline.py` 24/24. Ran every consumer (`test_cognition_tick_once.py`, `test_skills.py`, `test_skills_composer.py`, `test_visual_intent.py`) — 111/111 passed.

**PICK-04**: deleted `model/cascade_router.py` (`MetaHarnessRouter`, opt-in/default-off with no build flag or UI toggle anywhere to enable it — pure dead code) and its two dedicated test files (`test_cascade_router.py`, `test_c2b_wiring.py`, 27 tests total). Removed the `self.cascade_router = MetaHarnessRouter(...)` instantiation and both `is_enabled()` branches in `tier_router.py::route_request`, collapsing to the single heuristic path that was already the only reachable behavior. Kept `OutcomeStore` — `TierRouter._record_outcome` writes to it on every `generate()` call independent of cascade routing, so it stands on its own as plain telemetry; only updated its docstrings to say the cascade consumer was removed.
- `federation/compute_router.py` has one stale docstring mention of `cascade_router.py` — left untouched (out of ownership, `federation/**` explicitly excluded).
- Isolation: `test_tier_router_config.py` 8/8, plus `test_llm_config_layers.py`/`test_outcome_store.py`/`test_rate_limiter.py`/`test_model_router_config.py` together — 94/94.

**STUB-01**: traced the call graph before touching anything. `TierRouter`'s `ModelProvider` hierarchy (ollama/anthropic/peer) is **not** the dashboard's chat path — `dashboard/routes/chat.py` and `model/client.py::call_llm_chat` implement every `CHAT_CAPABLE_PROVIDERS` entry, `openai` included, directly, and nothing outside `integrations/app_seam.py` imports `tier_router` at all. `app_seam.py`'s `HalbertModelBackend` (the sole consumer, used only by the optional cognitive-tick `ThoughtGenerator` behind `HALBERT_LLM_THOUGHTS`) already wraps every call into `TierRouter.generate()`/`_get_provider()` in a broad `try/except` that falls back to raw Ollama on any exception — so the stub never crashes a real turn; it silently degrades. Removed the special-cased `raise NotImplementedError("OpenAI provider not yet implemented")`, letting `"openai"` fall through to the same generic `Unknown provider` `ValueError` every other provider this legacy hierarchy doesn't implement (`llamacpp`, `mlx`, `lm-studio`, ...) already gets.
- New test file: `test_tier_router_provider.py` (3 tests) — confirms `openai` and `llamacpp` now raise the identical error shape, confirms `NotImplementedError` is gone, confirms `ollama` still resolves.

**U6-25/26/27 re-verification** (per the shared-rules note): re-verified all three against this branch's actual state rather than trusting the "already done" claim.
- **U6-26** (stale "three slots" comment): confirmed already fixed — `config_wizard.py` reads "four slots". No action.
- **U6-27** (test coverage for the secure-slot capability gate): confirmed already present — `test_agent_model_override.py::test_home_variant_ignores_the_secure_slot` / `test_sysadmin_variant_still_uses_the_secure_slot` already exist and cover exactly what the finding asked for. No action.
- **U6-25** (dead `secure` value in `tier_router.py::from_legacy_config`): **not actually fixed** on this branch — the dead computation was still present. Fixed it: the capability-gated call to `_resolve_slot('secure_model')` is kept (it has a tested side effect — `test_home_variant_does_not_read_the_secure_slot` pins that the key is never even read via a spy dict when the capability is absent — deleting the call outright would have broken that test), but the pointless assignment to an unused `secure` local is dropped in favor of a comment explaining why the call stays despite the result being discarded.

### Task 8 — Lower REV-05 items (time remained; did the two in owned files)
- **R05-F7**: `TierRouter.refresh()` checked only whether the bound session changed, so an edit to `models.yml` (a different guide model, a new endpoint) within the same session was never picked up until process restart. `refresh()` now also loads and compares the raw config content, re-resolving on either signal. `_load_raw_config()` already delegates to `llm_config`'s own freshness-checked read (1s TTL/file-stamp cache), so this adds no meaningful cost when nothing changed. New test: `test_llm_config_layers.py::test_the_tier_router_re_resolves_when_the_file_changes_mid_session`.
- **R05-P2**: `_env_chat_model_override` (the `HALBERT_MODEL` env fallback) caught *any* exception resolving the variant and treated it as "this is home, disable the override" — an unrelated import error would silently take away the only chat model a sysadmin box without `models.yml` has. Now fails open (proceeds as sysadmin, matching `_get_variant()`'s own error fallback) instead of closed. New test: `test_llm_config_env_override.py::test_variant_resolution_failure_fails_open_not_closed`.
- **R05-F4/F5/F6/F8** (images not translated for OpenAI/Anthropic wires, GPU lock not taken on the streaming path, `stream=True` calling `.json()` on an SSE body, `is_model_loaded` prefix false positives): all four live in `model/client.py`, which is **not** on this dispatch's "files you own" list. Deliberately not touched, to avoid stepping on whatever session owns that file in this shared, concurrently-edited repo. Flagging for a follow-up packet scoped to `model/client.py`.

## Assumptions requiring founder ratification

- **`U4-20`**: went with option (b) — gate Apple Intelligence slot assignment on `apple_intelligence_bridge_running`, never build the Swift bridge. No bridge source/build script exists anywhere in the tree; this remains true after this dispatch.
- **`U6-DESIGN-01`**: home preset is an explicit `False` override for `CAP_SOURCEPREP`, beating the probe, unless `being.yml` opts in. Implemented as the stated default "until ratified" — flagged in code comments (`capabilities.py::probe()`) as pending founder decision.

## Files touched (this dispatch's ownership + one cross-boundary item)

`halbert_core/halbert_core/capabilities.py`, `model/auto_provision.py`, `model/config_wizard.py`, `model/tier_router.py`, `model/llm_config.py`, `model/outcome_store.py` (docstrings only), `dashboard/routes/llm.py`, `dashboard/routes/compression.py`, `tests/conftest.py`, and their tests — plus `model/cascade_router.py` (deleted) and `intake/pipeline.py` (PICK-03 — the other half of the two-scale mismatch; not on the owned-files list but required to actually unify the scales; no other excluded-domain file was touched).

Confirmed **not** touched: `agents/state_machine.py`, `federation/**`, `routes/agent.py`, `audio/**`, `model/client.py`.

## Not pushed

All ten commits above are local to the `fix/capability-registry` branch in the worktree. Nothing was pushed to `origin`.
