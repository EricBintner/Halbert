# PKT-OTHER-P6b — Settings reload plan (declarative table)

Tier: **opus**   Milestone: **M4**   Effort: **S-M**
Collision lane: **O**   Merge order: **2/2 in O**
Verified against: halbert `main` @ `fbd725e9` (2026-09-11)

---

## 1. Packet

**OTHER-P6b** — Settings reload plan (declarative table).

## 2. User problem

Today only the personality block hot-reloads after a settings save. In `halbert_core/halbert_core/dashboard/routes/settings.py`, the `POST /api/settings/being` handler (`update_being_config`, line ~3093) ends with a hardcoded, personality-only hot path: it calls `get_agent()`, reaches `agent.prompt_builder`, and invokes `reload_personality()` (defined in `halbert_core/halbert_core/prompts/agent_prompts.py:509`, which re-reads being.yml and re-applies voice via `set_voice`). Every other settings change — a model slot reassignment in models.yml, a `dashboard.bind`/`dashboard.token` change, an `mcp.servers.*` edit, a `web_search.enabled` toggle — either silently hot-patches nothing (the user believes the save took effect and it did not) or implicitly demands a full backend restart with no signal to that effect. The founder runs concurrent sessions editing settings; a blanket restart-on-every-save is disruptive, and a silent no-op is worse — the machine then speaks as if a change it never applied is live. There is no single place that decides, per changed key, whether the running process can absorb the change hot, must rebuild a subsystem (the model router), or must restart. That decision is currently implicit, scattered, and wrong by omission. The machine is grounded in measured data and speaks first person; claiming a setting is saved while the running process still serves the old value is a groundedness violation.

## 3. What to build

Create a new module `halbert_core/halbert_core/dashboard/settings_reload_plan.py` owning one choke point: a declarative reload table plus a pure planner function `plan_reload(changed_paths: Iterable[str]) -> ReloadPlan`. `ReloadPlan` is a small dataclass/namedtuple with `restart_required: bool`, `hot_actions: tuple[str, ...]`, and `reasons: dict[str, str]` mapping each changed path to its disposition. The table (module-level, ordered, first-match-wins on dotted-path prefix) encodes: `personality.*` -> hot action `reload_personality` (re-read being.yml, re-apply voice — the existing `reload_personality()` in agent_prompts.py:509); `models.slots.*` and `models.routing.*` -> hot action `rebuild_model_router` (re-instantiate the router from `halbert_core/halbert_core/model/router.py` `ModelRouter` against the re-parsed models.yml from `halbert_core/halbert_core/model/llm_config.py`, then swap the reference the agent holds — slots, never model names, per the standing directive); `web_search.enabled` -> hot action `toggle_web_search`; `dashboard.bind`, `dashboard.token`, `mcp.servers.*` -> `restart_required=True` with a reason string, since the bind address, auth token, and MCP server set are process-lifetime wiring. Wire the planner into `update_being_config` in `routes/settings.py` at the exact seam where the personality-only block now sits (~lines 3201-3209): replace that hardcoded try/except with (1) collect the changed dotted paths from the `BeingConfigUpdate`, (2) `plan = plan_reload(paths)`, (3) execute each hot action through the same `get_agent()` reach the block uses today, wrapped per-action in try/except that logs a warning and downgrades to `restart_required` on failure, (4) include `restart_required` and per-path `reasons` in the 200 response payload alongside `config` so the UI can tell the user a restart is needed rather than silently half-applying. Keep the function pure and unit-testable: no I/O in `plan_reload` itself — it maps strings to dispositions. The table is data, not code, so adding a key later is a one-line edit. Do not rename anything user-facing; reasons are internal/log strings and must name slots and config keys, never AI models.

## 4. What NOT to build

Per the RESHAPE verdict in the deep-eval: (1) The projected-view diff — computing the resolved model per slot before and after the save to catch an effective owner change with no authored key change — is DEFERRED to the M5b tail; the basic table matches on authored dotted paths only. (2) The guarded `safeStorage.ts` localStorage accessor and the migration of the 11 unguarded sites (incl. `DebugContext.tsx:37`) is sibling unit OTHER-P6a, not this packet. (3) The single-flight + negative-TTL cache for repeated subprocess probes in `development.py` is dropped per RESHAPE (opportunistic; only if that file is opened for another reason). (4) No automatic restart mechanism — the planner reports `restart_required`; actually restarting the backend stays out of scope (no process manager changes, no self-kill). (5) No UI work beyond adding the two fields to the existing JSON response — the banner/modal that surfaces 'restart needed' on the dashboard surface is a follow-up, not this packet. (6) No changes to `is_local_model()`, capability gating, redaction, or the MCP trust boundary — those invariants are only consumed, never re-implemented.

## 5. Target files
- `halbert_core/halbert_core/dashboard/settings_reload_plan.py` [new file]
- `halbert_core/halbert_core/dashboard/routes/settings.py`

## 6. Dependencies

None — may dispatch immediately.

## 7. Effort

**S-M** — S-M. The work is one new module of pure logic (a prefix-match table and a dataclass) plus a surgical edit at a single, already-identified seam in `routes/settings.py`. The personality hot-reload reach (`get_agent()` -> `prompt_builder.reload_personality()`) already exists and is simply generalized; the model-router rebuild reuses the existing `ModelRouter` constructor and the models.yml load path in `llm_config.py` rather than inventing a new reload. What keeps it from being trivial-S: `routes/settings.py` is 3,491 lines and a known collision hub (lane E/O, shared with BIND-01a — do not run concurrently, rebase often), so the edit must be anchored by grep at apply time, not by line number; and the `models.slots.*` hot-rebuild path needs a test proving the agent's router reference is actually swapped, which requires a fixture around `get_agent()`. No new dependencies, no schema changes, no migrations.

## 8. UX rationale

The user edits settings from the dashboard while the machine is running — often across concurrent sessions. Today a save can produce a machine that claims a change it never applied, which breaks the first-person, measured-data contract: the computer says 'I updated' while still serving the old value. With the reload plan, a personality change (name, voice presentation) takes effect immediately on the next turn — the machine's greeting and Presence Pill reflect it without a restart, which is the common case. A slot change rebuilds the router in place, so the next turn routes to the new slot with no downtime. A bind/token/MCP change returns `restart_required: true` in the response, so the surface can say plainly 'this needs a restart to take effect' instead of silently half-applying — an honest, recoverable state rather than a hidden desync. The change is invisible when things go right and explicit when a restart is genuinely needed. No new surfaces, no conversation-list, no model names, no emoji; any future banner uses shared-tokens colours only.

## 9. Acceptance criteria

1. `halbert_core/halbert_core/dashboard/settings_reload_plan.py` exists and exports `plan_reload` and `ReloadPlan`; `plan_reload` is pure (no I/O, no imports of FastAPI/request state). 2. The table maps `personality.*` to a hot `reload_personality` action, `models.slots.*` to a hot `rebuild_model_router` action, and `dashboard.bind`, `dashboard.token`, `mcp.servers.*` to `restart_required=True`, each with a non-empty reason string. 3. `update_being_config` in `routes/settings.py` no longer contains the hardcoded personality-only block; it calls `plan_reload` and its 200 JSON includes `restart_required` (bool) and per-path dispositions. 4. After a `POST /api/settings/being` that changes only personality fields, the response reports `restart_required: false` and a hot action was executed (asserted via a spy/fake agent's `prompt_builder.reload_personality` having been called). 5. After a save touching `dashboard.bind` or `mcp.servers.*`, the response reports `restart_required: true`. 6. No AI model name appears in any response field or reason string (slots and config keys only). 7. New unit tests for the planner and the route seam pass under the repo's mandated runner.

## 10. Verification (measured state, not model judgment)

Run, from the repo worktree (never bare pytest — the editable install pins halbert_core to the main tree; always with the arch prefix):

  arch -arm64 ./wt_pytest.py halbert_core/tests/test_settings_reload_plan.py halbert_core/tests/test_being_routes.py -q

where the new `halbert_core/tests/test_settings_reload_plan.py` (added by this packet) asserts measured state, e.g.: `test_plan_personality_is_hot` -> `plan_reload(["personality.voice_presentation"]).restart_required is False` and `"reload_personality" in plan.hot_actions`; `test_plan_slots_rebuild` -> `plan_reload(["models.slots.chat"]).restart_required is False` and `"rebuild_model_router" in plan.hot_actions`; `test_plan_bind_restart` -> `plan_reload(["dashboard.bind"]).restart_required is True`; `test_plan_mcp_servers_restart` -> `plan_reload(["mcp.servers.0.command"]).restart_required is True`; and a route-level test posting a personality-only `BeingConfigUpdate` against a fake `get_agent()` asserting the response JSON `restart_required is False` and the fake's `reload_personality` call count == 1. Every assertion checks a concrete value (bool, tuple membership, call count, JSON field), never a model judgment. A failure is attributable to this packet only if absent from the known-red baseline on main (test_agent_model_override.py, test_agent_model_selected_event.py, test_no_model_names_in_user_facing_source.py, test_num_ctx.py, ~23 failures as of 2026-09-11). Confirm the exit code is 0 for the two named files.

## 11. Exclusions

Projected-view diff (resolved-model-per-slot before/after the save to catch effective owner changes with no authored key change): deferred to the M5b tail per the RESHAPE line. Guarded `safeStorage.ts` localStorage accessor and the 11-site migration (incl. the `DebugContext.tsx:37` mount-crash): sibling unit OTHER-P6a — do not touch frontend storage here. Subprocess probe single-flight + negative-TTL cache in `development.py` (HM18-C14): dropped per RESHAPE (opportunistic only). Automatic backend restart on `restart_required`: out of scope — this packet reports the flag; no process-manager or self-restart mechanism is added (no such unit; if one is later wanted it is new work). Dashboard UI surfacing of 'restart needed' (banner/modal): follow-up UI unit, not this packet — this packet only adds the two response fields the UI will consume. Any change to `is_local_model()` (model/llm_config.py:181), `has_capability()` (capabilities.py:499), the redaction choke point (security/display_transport.py), or the MCP trust boundary: consumed as-is, never modified here. Lane discipline: do not dispatch concurrently with BIND-01a — both edit `routes/settings.py` (3,491 lines, rebase risk); this unit is merge-order 2/2 in lane O.

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
