<!-- Research + plan. No code was changed to produce this. -->

# REVISION 2 — 2026-08-27

**The first pass was misguided and its delete list must not be executed as written.**

It asked one question of every module — *can a real user action reach this?* — and
answered it correctly against `origin/main`. That is the right test for finished code
and the **wrong test for scaffolding that an in-flight plan is about to land on.**
Unreachable-because-abandoned and unreachable-because-not-wired-yet are indistinguishable
from a call graph. The first pass treated them as the same thing.

Continuous Conversation **Plan A is complete** — 33/33 tasks, 87 commits, 18,314
insertions across 86 files, `4 failed / 1546 passed` backend (the 4 are documented
pre-existing), 126 frontend, `tsc` clean — and **merged to `main`** as `c184000` while this
document was being written. Measured, not claimed:
`.handoff/CONTINUOUS-CONVERSATION-PLAN-A-RESULTS-2026-08-27.md`.

## Eight deletions withdrawn

Cross-checking §2 against the active plans and the Plan A branch:

| Withdrawn | Why |
|---|---|
| **D-8 diff review** | Plan A persists `diff_proposals_json` as a **column on `messages`**; apply/reject read from it. 56 mentions across the plans. The plan *names the exact 404 the first pass found* — it is a repair in progress, not an abandoned feature. Branch goes 0 → 5 non-test files. |
| **`conversation_sqlite.py`** | Plan A makes `SqliteConversationStore` the **store of record**. 108 mentions. Branch goes 2 → 5. |
| **A-3 delete `turn_lock`** | Plan A has `tests/test_state_machine_turn_lock.py` asserting `isinstance(agent.turn_lock, asyncio.Lock)` and builds on it (emit `conversation_status "waiting"` while held). The lock is the design. |
| **D-3 `somatic/`** | Spec §8 threads `thread_id` through `session_somatic_blocks`. Still unwired (branch 0 → 0) but it is a named seam in an active design, not residue. |
| **D-1 `handlers/`, D-2 `react_agent.py`, D-4 subagents, `session_affinity.py`** | All named in the plans. Withdraw pending an explicit decision from whoever owns that direction — not from a call graph. |

**A gate the first pass lacked, and every future pass needs:** before proposing a
deletion, grep `.handoff/*PLAN*` and `documentation/design/` for the module. If anything
intends to reach it, it is not dead — it is early. Reachability is only a defect when
nothing means to reach it.

## What still stands

Untouched by any plan, and verified against the Plan A branch as well as main:

- **W-1** — `routes/compression.py` is a second writer of `models.yml`, bypassing the
  store's atomic write / `.bak` / 0600 and copying the repo's `routing:` block into the
  operator's file. `compression.py` is **untouched by Plan A**. Still the one live bug.
- **W-2** — `routing.complexity_threshold` read on two incompatible scales
  (intake 1–5, `router.py`/`tier_router.py` 0–1). All three files untouched by Plan A.
- **D-5 `cascade_router`** — off by default, wrong when on (every query, including "hi",
  routes to the **vision** slot), cost axis hardcoded to zero, and an OCC *add-on* rather
  than Claude Code behaviour. `tier_router.py` untouched by Plan A.
- **D-6** workspace/session config layers, **D-7** `feature_flags.py` (212 lines, zero
  references, and it misinforms), **D-12** `pages/Terminal.tsx` (the simulated AI),
  **D-14** orphaned frontend modules, **W-5** `register_system_tools`.

## §7 — The routing plan against Plan A

Plan A and the model-picker work are **almost disjoint**. Measured on
`origin/main...feat/continuous-conversation`:

| File the routing plan targets | Plan A |
|---|---|
| `intake/pipeline.py`, `routes/compression.py`, `model/router.py`, `model/tier_router.py` | **untouched** |
| `model/client.py` | +142 / −14 |
| `dashboard/routes/agent.py` | +428 / −151 |

So W-1, W-2, D-5 and D-6 are independent and can proceed. **W-4** (invalidating
`_agent_instance` so a model change takes effect without a restart) must be re-derived
against the branch, since `routes/agent.py` is heavily rewritten there.

### R-1 — Close Plan A's `num_ctx` gap from the picker side. **DONE — not to be re-done.**

> Closed by `5d0e340 fix(model): size num_ctx from the model's real window, and never
> block on it`, after this revision was written. `num_ctx_for_model` now resolves the
> ceiling itself via `_num_ctx_ceiling()` and `compute_num_ctx` clamps to
> `min(model_max, ceiling)` (`client.py:1056`). The analysis below is kept because it
> records why the risk existed; **do not schedule it as work.**

Plan A §3.1 records this as its top operational risk, and it lands in the picker's own
file. Verified on the branch:

- `num_ctx_for_model(model, prompt_tokens, num_predict, model_max=None)` — **every one of
  its five callers passes three arguments**, so `model_max` is always `None`.
- `compute_num_ctx(..., None)` therefore uses `_NUM_CTX_DEFAULT_MAX = 32768`
  (`client.py:483`).
- `_do_llm_call` reads `options.get("num_ctx_max")` (`client.py:596`) and **nothing in the
  tree sets it**.

Before this branch a call with no options sent no `options` block and the runtime used its
own small default. Now every local call sets an explicit `num_ctx` that grows monotonically
per model to 32k — roughly **+2 GB of KV cache for a 7B model, enough to OOM a GPU that was
previously fine**.

The producer already exists and is picker work: `dashboard/routes/llm.py::_ollama_show_detail`
returns `context_tokens` (`llm.py:305`), already surfaced per model at `llm.py:421-422` and
already passed as `context_length` into capability detection at `llm.py:433`. Thread that
value into `num_ctx_for_model` as `model_max`. **Size: small. Behaviour-changing: caps
`num_ctx` at each model's real context window instead of 32k.** Until it is wired, lower
`_NUM_CTX_DEFAULT_MAX`.

This is the clearest argument for doing the two tracks together rather than in sequence:
Plan A created the risk, and the model picker already discovers the number that removes it.

### R-2 — `payload["options"]` is now unconditional

`client.py:606` on the branch always populates `options`, where it was previously set only
`if options:`. Every in-tree caller passes explicit options, so nothing regresses today —
but this is the same function E-1 rewrote for provider dispatch. Anyone touching
`_do_llm_call` should read both changes together.

### R-3 — Merge order

Plan A is "doc-and-code disjoint from the model-picker work but has not been attempted",
and neither branch has seen the other. Merge Plan A first, re-run all three suites, then
re-derive W-4 and land R-1 on the merged result. Do **not** execute the deletions below
until Plan A is merged — several of them are decided by it.

---

# Halbert Cleanup and Wiring Plan (revision 1 — superseded in part by revision 2 above)

## 0. Verification ledger

I re-checked every load-bearing claim against `origin/main` (533c3a0), not the working tree. Baseline: `1506 passed` (`cd /Volumes/4TB-BAD/Halbert/halbert_core && arch -arm64 ../.venv/bin/python -m pytest tests/ -q`).

### The correction that invalidates part of the research

**The tree the researchers read is not main.** `/Volumes/4TB-BAD/Halbert` is on `feat/role-scoped-skills` at 4c7841d: **7 commits ahead** of `origin/main` and **10+ commits behind** it. `git ls-tree -r origin/main --name-only | grep -c "halbert_core/skills/"` → `0`. **The entire `skills/` package does not exist on main.**

Consequences:

- Researcher 1's finding 1 and Researcher 5's findings 1–2 (skills unreachable, `set_skill_safety` unwired) describe **unmerged work on a feature branch**, not shipped code. They are correct *about that branch* and are input to a merge decision, not to a cleanup of main.
- Researcher 4 read a tree where the picker had been reverted (`git diff --stat origin/main..HEAD` shows `packages/model-picker/src/primitives/ModelSelectorPill.tsx | 270 +---`, `useModelPicker.ts | 21 -`). Their conclusions about the effective-layer surface are wrong on main — see the next correction.
- Line numbers in Researchers 1, 2 and 5 are shifted wherever `intake/pipeline.py`, `tools/safety.py`, `dashboard/routes/agent.py` or `context/assembler.py` are cited. All file:line references below are **main's**.

Also note six other live worktrees (`git worktree list`), including `feat/continuous-conversation` and `feat/model-picker-independent`. Concurrent sessions are editing this repo. Execute this plan from a fresh worktree off `origin/main`.

### VERIFIED

| Claim | Evidence on main |
|---|---|
| `agents/handlers/` (840 lines) is dead and diverged | `state_machine.py:670-683` dispatches to `self._handle_*`. `git grep -n "PlanningHandler(\|RespondingHandler(\|ExecutingHandler(" origin/main -- '*.py'` → one hit, `tests/test_agent_identity.py:91`. |
| `somatic/` (794 lines) never constructed | `AgentStateMachine(` at `routes/agent.py:188-200` passes no `somatic_lifecycle`/`somatic_store`. `git grep -n "somatic_lifecycle=\|somatic_store=" origin/main -- '*.py'` → only `tests/test_somatic_wiring.py:33-34`. |
| Subagents (542 lines) never constructed | `state_machine.py:624` `if self.subagents is None: return`. `git grep "subagent_manager="` → only `tests/test_subagent_wiring.py:21`. |
| `react_agent.py` (447) dead | `git grep -n "ReActAgent" origin/main -- '*.py'` → 3 hits: the class, and two lines in `agents/__init__.py:10,37`. |
| `conversation_sqlite.py` (410) + `session_affinity.py` (168) have no production importer | `git grep -n "conversation_sqlite\|SqliteConversationStore" origin/main -- '*.py'` outside its own file → `session_affinity.py:19` (a docstring) and two test files only. |
| `config/feature_flags.py` (212) referenced nowhere | `git grep -rn "feature_flags\|is_feature_enabled" origin/main` minus its own file → **no output**. Not even a test. |
| `context/extra_adapters.py` + `prioritizer.py` + `cache.py` (1256) reachable only via re-export | non-test hits outside their own files are `context/__init__.py:18,24,26,33,45,50,52,58` only. |
| `routes/jobs.py` (123) has zero callers | `git grep -n "api/jobs" origin/main` → one hit, `app.py:236`, the mount itself. |
| `routes/memory.py` (221) + `pages/Memory.tsx` (369) jointly unreachable | `App.tsx:91-104` has 14 routes, no `/memory`. `Memory.tsx:56,73,88,109,128` are the only `/api/memory` callers. |
| `pages/Terminal.tsx` (483) is a fake AI on an unlinked route | Routed at `App.tsx:92`; `Layout.tsx:49-72` nav array has 13 entries and **no `/terminal`**. `Terminal.tsx:132-137` `connectWebSocket` calls `setIsConnected(true)` and connects to nothing; `:296` `simulateAIResponse` sleeps 1000ms and returns hardcoded strings. |
| The diff propose→apply feature is broken in four places | (1) `state_machine.py:1468` emits `type="diff_proposed"`; `useAgentStream.ts:488` listens for `'diff_proposal'`. (2) The only emitter of `diff_proposal` is dead `handlers/executing.py:181`. (3) `state_machine.py:322-325` deletes the session in `process()`'s `finally`, so `routes/agent.py:1447` `if session_id not in agent.active_sessions: raise HTTPException(404)` fires first. (4) The payload sets `"file_path": None` and never sets `new_content`, so `routes/agent.py:1464` `os.makedirs(os.path.dirname(file_path))` → `TypeError`. `git grep "StreamEvent.diff_applied\|StreamEvent.diff_rejected\|StreamEvent.plan_step_update" origin/main` → **no output**. |
| Only the first tool call runs | `state_machine.py:798-799` `if hasattr(response, 'tool_calls') and response.tool_calls: tool_call = response.tool_calls[0]`. |
| Tool results never re-enter the message array | `state_machine.py:704-715` `_build_messages` builds `[system] + history + [user]` and nothing else. |
| The agent has exactly five tools | `ToolExecutor(` non-test → one hit, `routes/agent.py:105`. `_register_builtins` registers `run_command`, `web_search`, `read_file`, `write_file`, `list_directory`. `git grep -n "register_system_tools" origin/main -- '*.py'` → one hit, the definition at `executor.py:536`. `tools/system_tools.py` (469) has no caller outside `tools/__init__.py:10-13`. |
| `max_loops=5` | `routes/agent.py:196`. |
| Session and workspace config layers have no writer | `git grep "set_session_slot\|bind_session" origin/main` minus tests → the two definitions in `config_layers.py:159,168` and one docstring at `llm_config.py:498`. `workspace_models_config` is read at `config_layers.py:118`, written nowhere. Therefore `llm_config.py:478` `if len(layers) == 1: return ...` always short-circuits and `merge_layers_with_sources` never runs in production. |
| `cascade_router` is both unreachable **and** wrong | Default OFF (`cascade_router.py:58`); only `enable()` calls are in tests. Runtime probe against real `TierRouterConfig.from_legacy_config` output: `cfg.guide.primary = 'guide-model'` while `model_ids = ['<small>','<large>','<vision>']`. `route()` passes `model.model_id` to `predict()` → `_tier_of` returns `'other'` → prior `0.60` < `quality_bar 0.7` → falls through to `ladder[-1]`. Measured: `q='hi' complexity=0.00 -> chose '<vision>'`. Every query, including "hi", would route to the vision model. |
| `ModelRouter` is frozen at first use and never invalidated | `router.py:90` `self.config = self._load_config()` runs once in `__init__`; `_load_config` (`:130-153`) does a raw `yaml.safe_load` + `normalise_file`, no layers. `services.py:132-145` caches it in a module global; `git grep "_model_router" origin/main` outside `services.py` → nothing. Live surface: `generationQueue.ts:92-93` calls `/api/services/{name}/explain|diagnose`, served via `services.py:185,299`. |
| `/model` is dropped while streaming | `AgentChat.tsx:642` `if (!isStreaming && handleModelCommand(input)) return;`; `:645-648` queues instead; the drain at `:379-397` calls `sendMessage(nextMessage, ...)` with no parse. Typing `/model auto` mid-stream posts the literal string to the LLM. |
| `api.ts sendAgentStream` is dead and speaks the *live* event name | `git grep "sendAgentStream" origin/main` → only its own definition at `api.ts:143`. It handles `case 'diff_proposed':` at `:273` — the name the backend emits — while the live client handles the stale one. |
| `execute_with_retry` is dead | `git grep "execute_with_retry" origin/main -- '*.py'` → the definition at `error_recovery.py:151` plus two comments (`rate_limiter.py:54`, `tier_router.py:650`). |
| `get_outcome_store()` is dead | `git grep "get_outcome_store" origin/main -- '*.py'` → one hit, the definition at `outcome_store.py:222`. The only production `OutcomeStore()` is `tier_router.py:256`, which ignores the singleton. |
| `turn_lock` exists and its own docstring names the fix | `state_machine.py:186-205`: *"the fix is not a narrower lock but per-turn state."* Held at `routes/agent.py:1110,1227`; protects the shared-adapter mutation at `:1130`. |
| OCC batches all tool calls, threads state per call, and its permission layer never prompts | `agent-loop.mjs:178-237` (all `toolUseBlocks`, one `state.messages.push({role:'user', content: toolResults})`, then `yield* run(null, {continuation:true, _depth: depth+1})`); `:22-32` state created per `createAgentLoop`; `:9-10` `MAX_TOOL_RECURSION_DEPTH = 50`. `permissions/checker.mjs:46-53` `default:` returns `true` unconditionally; `grep -rn "promptPermission" v2/src` → the definition and one comment. `grep -rn "providers.mjs\|core/providers" v2/src` → **no importers**. `grep -rn "Sandbox" v2/src` minus `sandbox.mjs` → one comment. |

### CORRECTED

**C1 — `GET /llm/config`'s `effective` block is NOT dead.** Researcher 4's finding 5 fails on main. `modelPickerTransport.ts:135-142` reads `effective.llm_config` into `effectiveAssignments` and `effective.overridden_slots` into `overriddenSlots`; `useModelPicker.ts:279-284` exposes `effectiveAssignmentFor`, and `ModelSelectorPill.tsx:120,148,196` consumes it — that is commit d2e8e79, *"the pill names the model in force, not the one being edited."* Deleting `_effective_block` would regress a shipped fix. **What is genuinely dead is narrower:** `overrideLayerFor` (`useModelPicker.ts:285-287`) is exported and consumed by no component (only test mocks at `ModelSelectorPill.test.tsx:89` etc.), and the standalone route `GET /llm/config/effective` (`routes/llm.py:191`) has no caller — `git grep "config/effective" origin/main` outside `routes/llm.py` → one hit, `tests/test_llm_config_layers.py:631`.

**C2 — `model/router.py` cannot be deleted.** Researcher 2 implied 612 lines come off. `Halbert/main.py` constructs `ModelRouter()` at lines 1253, 1303, 1350, 1380, 1571, 1642, 1692, and `config_wizard.py` is CLI-reachable via `main.py:1465`. Only the *dashboard's* use is re-pointable.

**C3 — the shipped `complexity_threshold: 0.5` does not reach intake by the route Researcher 2 named.** `llm_config._read_path()` is `find_models_config(include_repo=False)` (`llm_config.py:138`), so the store deliberately never reads the repo's `config/models.yml`. R2's mechanism is wrong. **The real vector is worse and I reproduced it — see §1.**

**C4 — `prep-primitives` is not wholly orphaned.** `Button.tsx` is live (`components/llm/ProbeButton.tsx:5`, `components/llm/QuickSetup.tsx:5`). Only `InfoTooltip.tsx`, `SearchableSelect.tsx`, `Toggle.tsx`, `Select.tsx` have zero importers. Do not delete the directory.

**C5 — Researcher 3's "`grep tool_result|tool_use` in `agents/` returns nothing" is false**, and the truth is a *stronger* finding — see §1, the seventh instance.

### Contradictions resolved

- **skills/ line count (R1 1324 vs R5 1055):** both right. 1055 Python lines + 269 lines of `SKILL.md`. Moot for main.
- **`conversation_sqlite`: R1 says WIRE, R2 says "decide".** Neither, yet. Plan B (`.handoff/CONTINUOUS-CONVERSATION-PLAN-B-2026-08-27.md`) is a DRAFT on an unmerged branch (commit 4c7841d's own message says DRAFT). Leave the file; do not delete it and do not wire it as part of this cleanup. Flagged in §6.
- **`handlers/`: R1/R3 say delete; `test_agent_identity.py` guards it.** Delete, and re-point the test — resolution in §2.
- **`react_agent.py`: R3 says "harvest its protocol first".** Rejected. `agents/blocks.py` + `states.py` already contain a better version of that protocol (§1), so there is nothing to harvest.
- **`register_system_tools`: R3 says wire (one line); founder prefers deletion.** Wire — resolution and reasoning in §3.

---

## 1. What is actually true now

**A chat turn is decided by three things, in this order.** `POST /api/agent/message` → `routes/agent.py:1110` takes `agent.turn_lock` for the whole turn → `_resolve_turn_model(prompt, intake_result, images, model_override, tier_override, endpoint_id)` at `routes/agent.py:279`:

1. **`model_override`** (the chat pill / `/model pin`) → `pinned=True`, router bypassed entirely.
2. **`tier_override`** (`/model guide|specialist|vision`) → that tier's slot, falling back to guide with a log line if unconfigured.
3. **Automatic.** Images or `intake_result.recommended_model == "vision"` → vision slot. Otherwise, *if the specialist slot is configured*: if intake ran, `use_specialist = intake_result.recommended_model == "specialist"`; if it did not, `score = score_query_complexity(prompt); use_specialist = score >= 0.5` (`routes/agent.py:365-369`). Else guide.

**Intake's verdict is authoritative when present.** `IntakePipeline` is built once at `routes/agent.py:178-182` from a `models.yml` snapshot taken at agent construction, cached in `_agent_instance` (`:85`), and never invalidated. Its rule is `complexity.score >= threshold and specialist_enabled` where `complexity.score` is an **integer 1–5** from an LLM call (`intake/complexity.py:36` `score: int  # 1-5`) and `threshold` defaults to **3** (`intake/pipeline.py:111`).

**`routing.complexity_threshold` is read on two incompatible scales.** Intake reads it as 1–5 (`intake/pipeline.py:111`, default 3). `tier_router.py:100,208` and `router.py:494` read the same key as 0.0–1.0 (default 0.5). The shipped `config/models.yml:53` sets `complexity_threshold: 0.5`.

**The headline bug — reproduced end to end.** `routes/compression.py:100-117` is a second writer of `models.yml` that violates the invariant `settings.py:203-207` states out loud (*"Every write goes through the store, so the file keeps its backup, atomic rename, 0600 mode and sibling keys"*). It reads with `find_models_config()` — `include_repo=True`, so it *can* read the repo's `config/models.yml` — mutates the whole dict, and writes it back with `open(write_path,'w')` + `yaml.safe_dump`. Running the real route on a simulated fresh install:

```
user file   = .../Halbert/models.yml exists: False
read_path   = /Volumes/4TB-BAD/Halbert/config/models.yml
write_path  = .../Halbert/models.yml
created: True mode: 0o644
top-level keys : ['llm_config', 'compression', 'routing', 'handoff', 'persona_names']
routing carried: {'strategy': 'auto', ..., 'complexity_threshold': 0.5}
threshold intake now sees: 0.5 float
  LLM complexity 1/5 -> recommended = specialist
  LLM complexity 2/5 -> recommended = specialist
  ... 5/5 -> specialist
```

One click on Settings → Compression (`Settings.tsx:1183` `<CompressionSettings />` → `CompressionSettings.tsx:102` POST `/compression/config`) permanently writes `complexity_threshold: 0.5` into the operator's `models.yml`. From then on **every message, including "hi", routes to the specialist** whenever that slot is enabled, and the turn banner reads "Intake routing: specialist". The same write creates the file at **0644 instead of 0600**, non-atomically, carrying `llm_config.saved_endpoints` — including the `api_key` field (`llm_config.py:244`) — forward. Compression already has a correct writer at `settings.py:216` using `llm_store.set_top_level("compression", ...)`.

**There are three live model resolvers, not two.** `_resolve_turn_model` (per-call, layered). `TierRouter` (store-backed, `refresh()`es on session change) → `app_seam` → Haloysius. And `ModelRouter`, frozen at first use in `services.py:135-145`, serving `/api/services/*/explain|diagnose`. After the operator changes their chat model, "explain this service" keeps answering from the old model — including a cloud endpoint they just deleted — with nothing in the UI saying so.

**Five complexity scorers exist; three are live and they disagree.** `client._score_query_complexity` (`client.py:695`, live on chat), `ModelRouter._score_complexity` (`router.py:365`, live on services), `TierRouter._score_complexity` (`tier_router.py:550`, live via app_seam), `cascade_router.estimate_complexity` (default OFF), `intake/complexity.py` (LLM, 1–5, live on chat). The middle two are forked 55-line keyword tables that have already drifted despite `tier_router.py:552-554` claiming byte-identical behaviour.

**The config-layer engine is unreachable.** No writer exists for the session layer or the workspace layer, so `llm_config.py:478` always short-circuits and roughly 340 of `config_layers.py`'s 453 lines never execute in production. The per-turn override the founder actually wants already exists and is reachable — it is `model_override`/`tier_override` at `routes/agent.py:279`.

**The seventh instance of the dominant defect class, which nobody reported.** `agents/blocks.py` (156 lines) defines `TextBlock`/`ToolUseBlock`/`ToolResultBlock` — the exact Anthropic content-block shape — and `states.py:226-278` defines `StateContext.add_text_block()`, `add_tool_use_block()`, `add_tool_result_block()` to record them. `git grep "add_tool_use_block\|add_tool_result_block\|add_text_block" origin/main` → **the definitions, `tests/test_blocks.py`, and two planning docs. Zero production callers.** Same for `content_to_anthropic` and `is_block_content`. Only the *flattening* helper `content_to_text` is live, and it is live everywhere (`state_machine.py:706`, `assembler.py:382,402,863,892`, `prompts/builder.py:235`, `conversation/summarization.py:75`, `model/training_data.py:132`). So: **the structured-history mechanism that Researcher 3 wants to port from OCC is already built, already tested, and mounted nowhere — while every consumer flattens to prose.** That is the same shape as `ContextWatermark` before E-3, and it is why `_already_called()` (`state_machine.py:802`) and the 2000-char observation truncation had to be invented as compensations.

**Confirmed defect-class tally on main: seven.** watermark (fixed), the pill chain (fixed), the fallback chip (fixed), `cascade_router`, `somatic/`, subagents, and now `blocks.py`/`states.py` structured history — plus `handlers/`, `react_agent.py`, `conversation_sqlite.py`, `feature_flags.py`, the three `context/` modules, `system_tools.py`, `routes/jobs.py`, `routes/memory.py`, and the whole diff-review affordance.

---

## 2. What to delete

Do these first. Each is a straight removal with the test change named. Totals: **≈5,900 backend production lines, ≈1,500 frontend lines, ≈1,900 test lines.**

**D-1 — `agents/handlers/` (840 lines).** `handlers/{__init__,planning,searching,reading,executing,observing,responding}.py`, plus the import block at `agents/__init__.py:30-33` and the four `__all__` lines at `:53-56`. **Cost:** `tests/test_agent_identity.py::TestRespondingFallback` (3 tests, `:86-91`) currently asserts an identity fallback that lives only in `handlers/responding.py:124` — `grep -n "_get_system_prompt" state_machine.py` → nothing. Re-point it at the live `_handle_responding` (`state_machine.py:1346`) and **expect it to fail**: the live path has no such fallback. Record that as a real finding rather than deleting the test. *Size: small. Invisible to users.*

**D-2 — `agents/react_agent.py` (447)** plus `agents/__init__.py:10,37`. **Cost:** none; nothing imports it. Note that `documentation/sovereign-host-vision/IMPLEMENTATION-STRATEGY-2026-08-24.md:235` proposes adding `spawn_subagent()` "in ReActAgent" — grep the docs after deleting and fix that line, or it will send the next reader to a file that no longer exists. *Size: small. Invisible.*

**D-3 — `somatic/` (794) and its seams.** Delete `somatic/{__init__,block,checkpoints,lifecycle,store}.py`, the `somatic_lifecycle`/`somatic_store` params (`state_machine.py:128-129`), the C1d branch (`:1330-1341`), `_emit_somatic_block()` (`:579-604`), the `StreamEvent.somatic_block` factory, `useAgentStream.ts:114,524-527` (`somaticBlocks`), and `tests/test_somatic_wiring.py` (108). **Cost:** loses an unshipped concept entirely. If it returns, it must return with a consumer. *Size: medium. Invisible — the SSE event can never have been received.*

**D-4 — subagents (542 + 379 test lines).** `agents/subagent.py` (283), `agents/subagents/` (259), `spawn_subagent`/`await_subagent_completion` (`state_machine.py:611-663`), the `subagent_manager` param, `StreamEvent.subagent_event`, `useAgentStream.ts:559-563`, and `tests/test_subagent_{manager,events,wiring}.py`. **Cost:** if orchestration starts soon this is re-work — but OCC shows the replacement is ~40 lines (`tools/agent.mjs:83-88` just calls `createAgentLoop()` again), not a 283-line manager. `.handoff/TERMINAL-AND-ORCHESTRATOR-REVIEW-2026-08-26.md` already records the orchestrator as stubs. *Size: medium. Invisible.*

**D-5 — `model/cascade_router.py` (190) + `tests/test_cascade_router.py` (199) + `tests/test_c2b_wiring.py` (155), and the two `is_enabled()` branches at `tier_router.py:510,524`.** Do **not** "fix" it. It is off by default, it is wrong when on (proven above: everything routes to vision), its tests pass only because the fixture makes `model_id == name == primary` — the one shape `from_legacy_config` never produces — and the design underneath has no cost axis: `tier_router.py:748` writes `cost_usd=0.0,  # price table wired in C2`, so `OutcomeStore.avg_cost` is structurally always zero. Also delete `get_outcome_store()` (`outcome_store.py:217-227`). **Cost:** loses the outcome-blended-routing idea. Keep `OutcomeStore` itself if latency/success telemetry is wanted. *Size: small. Invisible — it never ran.*

**D-6 — the workspace and session config layers (≈340 of `config_layers.py`'s 453, plus most of `tests/test_llm_config_layers.py`'s 728).** Remove `bind_session`, `set_session_slot`, `session_layer`, `file_overlay_layers`, `merge_layers`, `merge_layers_with_sources`, `_endpoint_layers`, `_layer_endpoints`, `_carry_api_key`, `_endpoint_identity`, `_merge_slot`, `_SlotWin`, `_alias_id`, `MergedConfig`, `WORKSPACE_SETTING_KEY`, and the `session_id` parameter thread through `load`, `load_file`, `load_layered`, `resolve` and `routes/llm.py:178,192,204`. Also remove `overrideLayerFor` (`useModelPicker.ts:63,285-287,468`), `overriddenSlots` (`types.ts:155`, `modelPickerTransport.ts:124,140-141`), `LayeredConfig.slot_layers`, and the standalone route `GET /llm/config/effective` (`routes/llm.py:191`). **Keep `_effective_block`'s `llm_config` half and `effectiveAssignments`** — see C1; with layers gone it becomes a trivial identity, and you may then collapse it in a separate, deliberate commit. **Cost:** removes multi-workspace model config as a future direction. That is the point: the per-turn override at `routes/agent.py:279` already does what the operator needs. *Size: medium. Invisible — no layer was ever populated.*

**D-7 — `config/feature_flags.py` (212).** Zero references, zero tests. Worth deleting on the founder's terms specifically: a reader who finds `use_new_agent: bool = False` (`:22`) concludes the new agent is off by default, which is the opposite of the truth. *Size: small. Invisible.*

**D-8 — `context/extra_adapters.py` (596) + `prioritizer.py` (294) + `cache.py` (366) = 1256**, plus `context/__init__.py:17-33,44-58`. The live factory is `create_wired_context_assembler()` (`adapters.py:421`, called at `routes/agent.py:108`); `create_extended_context_assembler()` (`extra_adapters.py:541`) is called only by `tests/test_phase_d_integration.py:437,448`. `FailureCorrelationAdapter` (`extra_adapters.py:450`) has no reference anywhere, not even a test. **Cost:** loses `SystemIdentityAdapter`, `SelfKnowledgeAdapter`, `TelemetryAdapter`, `SafetyAdapter` and 25 tests. If any of those four are actually wanted, promote them into `create_wired_context_assembler` *instead of* this deletion — but do not keep two factories. The real win is removing a false second answer to "how does Halbert prioritise/cache context?" *Size: medium. Invisible.*

**D-9 — `routes/jobs.py` (123)** and `app.py:236`. Two APIs for one concept, neither reachable. The live one is `settings.py:2906` `/scheduler/jobs`. *Size: small. Invisible.*

**D-10 — `routes/memory.py` (221) + `pages/Memory.tsx` (369)** and `app.py:237`. Unreachable end to end. *Size: small. Invisible.*

**D-11 — `pages/Jobs.tsx` (218)** — no importer, no route. *Size: small. Invisible.*

**D-12 — `pages/Terminal.tsx` (483)** and `App.tsx:7,92`. This is the best single deletion in the frontend: it advertises "AI-enhanced shell with /explain /dryrun" (`:108`), reports "● Connected to local shell" while connecting to nothing (`:132-137`), and answers every slash command from `simulateAIResponse` (`:296`) with a hardcoded string after a fake 1000ms think — `/fix` returns the same three suggestions regardless of what failed; `/dryrun` always reports "Risk Level: ⚠️ Medium". The real terminal work is `components/agent/{TerminalAccordionDock,TerminalTile,InlineTerminals}.tsx`. Deleting it also removes two of the four slash parsers, and the divergence between them (`:156-171` knows six commands, `:281` knows those plus `/help`). *Size: small. Behaviour-changing only for someone who hand-types the URL — no nav link exists.*

**D-13 — `lib/api.ts sendAgentStream` (~177 lines, `api.ts:140-319`)** and its `onDiffProposed` callback contract. Dead since the SidePanel deletion. *Size: small. Invisible.*

**D-14 — eight orphaned frontend modules.** `components/prep-primitives/{InfoTooltip,SearchableSelect,Toggle,Select}.tsx` (**not `Button.tsx`** — C4), `components/ui/{activity-indicators,model-reasoning,thinking-steps}.tsx`, `components/agent/index.ts`. *Size: small. Invisible.*

**D-15 — two dead methods.** `ErrorRecoveryManager.execute_with_retry()` (`error_recovery.py:151`, ~50 lines) and the two comments that describe it as if it ran (`rate_limiter.py:54`, `tier_router.py:650`); `model/client._truncate_messages_for_context` (`client.py:641`, ~50) plus its alias at `:801` and the `model/__init__.py:35,76` re-export. Deleting the first makes the actual retry policy visible: a bare counter at `state_machine.py:1518-1524` that gives up at 3. *Size: small. Invisible.*

**D-16 — `agents/llm_client.py`'s three client classes (~420 of 470).** `BaseLLMClient` (`:49`), `OllamaClient` (`:72`), `AnthropicClient` (`:264`), `get_llm_client` (`:454`), and `agents/__init__.py:14-16,42-43`. **Keep** `ToolCall`, `FunctionCall`, `LLMResponse` (`:36-46`) and delete the *duplicate* `LLMResponse` at `routes/agent.py:887`, importing the dataclass instead — one type, with `finish_reason`, `usage` and `has_tool_calls()`. Today three test modules feed the state machine a response object production never constructs. *Size: small. Invisible.*

**Deletions deliberately NOT proposed:** `model/router.py` (C2 — the CLI needs it), `agents/conversation_sqlite.py` and `session_affinity.py` (§6), `tools/safety.py` (§6).

---

## 3. What to wire

**W-1 — Fix the compression writer. This is the one urgent bug.** `routes/compression.py:100-117` → read via `llm_store.load_file()` and write via `llm_store.set_top_level("compression", updates)`, which already exists (`llm_config.py:586`) and is already used for this exact key at `settings.py:216`. That deletes ~30 lines, restores the atomic write / 0600 / normalisation, and stops the `routing:` block being copied out of the repo checkout into the operator's file. **Wire, not delete.** *Size: small. Behaviour-changing for every turn on any install whose `models.yml` was created this way — those files need `routing.complexity_threshold` removed, or a one-shot migration in `normalise_file`.*

**W-2 — Collapse `complexity_threshold` to one scale.** Delete `complexity_threshold: 0.5` from `config/models.yml:53`, delete `ModelRouter._score_complexity` and `TierRouter._score_complexity` (~110 duplicated lines) and have both call `client.score_query_complexity`, and leave intake's 1–5 comparison as the only reader of the config key — renamed so the scale is in the name. **Do this in the same change as W-1**, or the migration has no destination. *Size: medium. Behaviour-changing: `/api/services/*/explain|diagnose` and the Haloysius seam will start escalating on the same sentences chat does.*

**W-3 — Re-point `/api/services/*/explain|diagnose` off `ModelRouter`.** Replace `services.py:135-145,185,299` with `_resolve_turn_model` + `model/client.call_llm_chat`, the way chat does. Alternative if that is too large: lift `tier_router.py:282-294`'s pattern (`if self.config_path == llm_store.global_config_path(): return llm_store.load_file(...)`) plus its `refresh()` (`:308-321`) into `ModelRouter._load_config` — reusing a concept that already exists rather than adding one. **Wire.** *Size: medium (re-point) or small (refresh). Behaviour-changing: explain/diagnose will start honouring model changes without a restart.*

**W-4 — Invalidate `_agent_instance` on `PUT /llm/config`.** `routes/agent.py:85` caches the agent, and with it a `models.yml` snapshot and a `ComplexityRouter` pinned to the guide model and endpoint that existed at boot (`:167-181`). Enabling the specialist slot after boot can therefore never take effect: intake's frozen `specialist_enabled` stays False and `_resolve_turn_model` obeys its verdict (`:364-366`). Worse, changing the chat model leaves every turn making an intake LLM call to the *old* model at the *old* endpoint; when it fails, `complexity._call_llm` returns `3`, which at the default threshold flips every message to the specialist. One line (reset the global) is the cheap fix; passing config per call is the correct one. **Wire.** *Size: small (reset) / medium (per-call). Behaviour-changing.*

**W-5 — Wire `register_system_tools()` and delete its twin.** `executor.py:536` exists and is called nowhere; the agent's entire host-inspection ability is shelling out through `run_command`. Add the call at `routes/agent.py:105` and delete `tools/system_tools.py` (469) plus `tools/__init__.py:10-13,20-22`. **This is the one place where wiring beats deleting**, because the alternative — deleting both inventories — leaves a host-administration agent that can only shell out, and the founder's goal is control, which structured tools serve better than free-form shell. *Size: small. Behaviour-changing: the model gains 8 typed tools; expect prompt/token effects and re-check `tools/safety.py` classification for each.*

**W-6 — Wire the structured history that already exists, or delete it.** `states.py:226-278`'s three `add_*_block` recorders and `blocks.py`'s `content_to_anthropic` are the mechanism §4 wants. Wiring means: `_handle_planning` records `add_tool_use_block` for every call it takes, `_handle_executing` records `add_tool_result_block` per result, and `_build_messages` (`state_machine.py:704-715`) emits blocks instead of flattening. **Prefer wiring** — it is already written and tested (`tests/test_blocks.py`, 174 lines) and it is the prerequisite for W-7. If W-7 is not being done this cycle, delete `add_text_block`/`add_tool_use_block`/`add_tool_result_block`, `content_to_anthropic`, `is_block_content` and the matching tests, keeping only `content_to_text`; leaving a built, correct, unreachable protocol implementation in the tree is precisely the defect this plan exists to remove. *Size: medium. Behaviour-changing (see W-7).*

**W-7 — Execute every tool call, not just the first.** `state_machine.py:798-799` takes `tool_calls[0]` and silently drops the rest; any model that emits parallel calls has its plan truncated to one step per loop, and with `max_loops=5` (`routes/agent.py:196`) a turn is capped at roughly four tool executions. Loop over `response.tool_calls`, queue them, drain in EXECUTING, and raise `max_loops` once batching lands. **Wire.** With W-6 in place, `_already_called()` (`state_machine.py:802-861`) and `_detect_oscillation` become deletable — the model can see what it already ran. *Size: large. Behaviour-changing for every turn — this is the biggest behavioural change in the plan.*

**W-8 — Decide the diff-review affordance.** Four independent breaks (§0). **Recommend delete**, not wire: remove `state_machine.py:1455-1480`, the `apply_diff`/`reject_diff` routes (`routes/agent.py:1436-1500`), `useAgentStream.ts:488`, `AgentChat.tsx:846-856`'s `DiffViewer` block with `applyDiff`/`rejectDiff`, and the three never-emitted `StreamEvent` constructors. Wiring it means fixing an event name, changing session lifetime so a completed turn stays addressable, populating `file_path`, and inventing `new_content` from `edit_blocks` — four changes to ship an affordance nobody has asked for since the chat retirement. **Cost of deleting:** the config-editor flow loses its (never-working) apply path. *Size: medium. Invisible — it has never once worked.*

**W-9 — One slash-command table, one dispatch.** `AgentChat.tsx:642` parses commands only when not streaming; the queue drain (`:379-397`) calls `sendMessage` directly, so `/model auto` typed mid-stream is posted to the LLM as prose and answered. Move the claim decision into a table in `lib/slashCommands.ts` and have both `handleSend` and the drain call one `dispatch(input)`. Render the table as a completion list when the composer starts with `/` — today `AgentChat.tsx:1038`'s placeholder advertises "@ to mention, paste/drop images" and never mentions `/`. *Size: small. Behaviour-changing: `/model` starts working while streaming; commands become discoverable.*

---

## 4. What to adopt from OCC

**A-1 — Batch every tool call into one `tool_result` message. (Real Claude Code behaviour.)** `agent-loop.mjs:178-237`: collect all `tool_use` blocks, run them, push **one** user message containing every `tool_result`, then recurse. Halbert file: `agents/state_machine.py` (`_handle_planning:798`, `_handle_executing`, `_build_messages:704`). This is W-6 + W-7. Halbert already has the block types — adopt the *loop shape*, not the types.

**A-2 — A depth guard instead of a loop budget. (Real Claude Code behaviour.)** `agent-loop.mjs:9-10` `MAX_TOOL_RECURSION_DEPTH = 50`. OCC can afford 50 because it batches; Halbert needs 5 because it does not. Halbert file: `dashboard/routes/agent.py:196`. Raise only *after* A-1, or you multiply the truncation.

**A-3 — Per-turn state as arguments; no lock. (Real Claude Code behaviour.)** OCC separates three lifetimes: shared immutable services passed into `createAgentLoop`; conversation state created *inside each call* (`agent-loop.mjs:22-32`) — which is why the Agent tool gets independent state just by calling it again (`tools/agent.mjs:83-88`); and per-turn ephemera as function arguments (`:56-57` `const depth = options._depth || 0`). Nothing is read off a process-wide singleton, so OCC's core contains no lock. Halbert files: keep `get_agent()`'s expensive wiring as a services object, construct a cheap `AgentStateMachine` per request (or thread `ctx` + state through the `_handle_*` methods), then delete `turn_lock` (`state_machine.py:182-214`), the `_turn_lock_loop` re-binding, `routes/agent.py:1110,1227`, the pre-turn `agent.current_state = AgentState.IDLE` reset, and the shared-adapter mutation at `:1130`. `state_machine.py:186-205` already prescribes exactly this. *Size: large. Behaviour-changing: Halbert stops being single-user; a slow turn stops blocking every other request.*

**A-4 — One command table, three consumers. (Real Claude Code behaviour, `v2/src/ui`.)** `commands.mjs:27` `COMMANDS` is one object literal; dispatch (`:517`), `/help` (`:32`), and completion (`:532`) all read it and nothing else, and both UIs — Ink TUI (`ui/app.mjs:82`) and readline (`ui/repl.mjs:61`) — call the same `executeCommand`. Halbert file: `dashboard/frontend/src/lib/slashCommands.ts`. This is W-9. **Do not copy `commands.mjs:13`**, which imports `OutcomeStore` from `../optimize/store.mjs` — the OCC authors' opt-in add-on hard-linked into a core UI file, exactly the coupling a registry prevents.

**A-5 — Config precedence: one persisted file, one call-site override, no provenance. (Real Claude Code behaviour.)** `settings.mjs:68-79` merges three files, `:85` applies env, and `index.mjs:146` applies `--model` **at the point of use** (`args.model || settings.model || default`) without merging it into settings or making it a layer. Halbert already has both halves: `models.yml` and `_resolve_turn_model`'s overrides. Adopting this is D-6 — a deletion, not an addition. Note OCC's own header (`settings.mjs:5-6`) misdescribes its precedence as "user > project" with five layers; the code does the opposite. If Halbert keeps a layer-order doc, derive it from code.

**Not from OCC, from Halbert:** `tier_router.py:282-294`'s "if this path is the store's own file, read the store" plus `refresh()` is the pattern for W-3. It already exists here; do not invent a new one.

---

## 5. Sequencing

**Before anything: rebase.** Branch off `origin/main` in a fresh worktree. Do not execute this plan in `/Volumes/4TB-BAD/Halbert` — it is on `feat/role-scoped-skills`, behind main, with a reverted picker.

**Track 1 — ship today, independently, in one commit each.** W-1 (+ the `models.yml` migration), then D-7, D-9, D-10, D-11, D-12, D-13, D-14, D-15. All are pure removals with no ordering between them. W-1 is the only one that changes behaviour, and it changes it for every turn on affected installs — ship it first and alone so it is bisectable.

**Track 2 — the agent-package cleanup.** D-1 → D-2 → D-16 in that order (D-1 frees `agents/__init__.py`, D-16 then collapses `LLMResponse`). Then D-3 and D-4, which are independent of each other. Then D-8. All invisible; all safe behind the 1506-test baseline.

**Track 3 — the model/config collapse. Strictly ordered.** W-1 → W-2 → D-5 → D-6 → W-3 → W-4. W-2 must follow W-1 (the migration needs its destination). D-5 must precede D-6 only to keep the diffs readable. W-3 and W-4 both change what model answers, so land them last and separately.

**Track 4 — the agent loop. Strictly ordered, and the only large work.** W-6 (structured history) → W-7 (batch all tool calls) → A-2 (raise `max_loops`) → delete `_already_called`/`_detect_oscillation` → A-3 (per-turn state, delete `turn_lock`). Do not start W-7 before W-6: batching without blocks in the message array just multiplies the prose observations. Do not start A-3 before W-7 lands and is stable — it touches every handler.

**Track 5 — W-5 and W-9, independent of everything.** W-5 changes the model's tool surface; ship it alone and watch for prompt-size and safety-classification effects.

**Changes behaviour for every turn — flag loudly, ship isolated:** W-1, W-2, W-4, W-5, W-7, A-2, A-3. Everything else in this plan is invisible to the operator.

---

## 6. What NOT to do

**Do not merge or extend `feat/role-scoped-skills` as part of this cleanup.** It adds 1,324 lines of skills machinery whose only seam into the chat path — `IntakePipeline(skill_matcher=...)` — the branch's own production constructor does not pass, so `active_skills` is always `[]` and 121 tests pass over code no user action can execute. If it lands as-is it is instance number eight. Two further blockers, both correctly identified by Researcher 5: `set_skill_safety` (`tools/safety.py:295` on that branch) has no production caller, so wiring the *matcher* alone would inject `storage-ops`' prompt while silently not enforcing its `blocked_commands` (`mkfs*`, `dd*of=/dev/*`, `zpool destroy*`) — worse than today's honest nothing. And `SkillMatcher.match` auto-selects by keyword score with no operator-visible surface (`grep -rni skill` over the entire frontend → no output), so `/etc/fstab` would become write-protected because the word "zfs" appeared in a sentence, with no way to see why. If skills ship, ship the **explicit** half only (`matcher.py:202 _explicit()` plus a `/skill <name>` entry in the W-9 table) and delete the scoring path — that is OCC's model too (`skills/loader.mjs:143` parses a `trigger` field that `grep -rn "\.trigger" v2/src` proves nothing ever reads).

**Do not "fix" `cascade_router`.** It is off, it is wrong when on, its cost axis is hardcoded to zero (`tier_router.py:748`), and its top rung is the *vision* slot — a capability slot treated as a capability tier, so the fallback for a hard **text** task is a vision model. Fixing `_tier_of` would produce a working router for a design that does not hold. Delete it (D-5). Note for the record: `v2/src/optimize` is the OCC authors' own opt-in add-on, **not Claude Code behaviour**; there was never an upstream mandate to have this.

**Do not adopt OCC's permissions, providers, or auth.** `permissions/checker.mjs:46-53`'s `default` branch returns `true` unconditionally and `promptPermission` has zero callers — OCC never actually asks the user anything. `permissions/sandbox.mjs`'s `Sandbox` is imported nowhere and `bash.mjs` spawns unsandboxed. `core/providers.mjs` has no importers (`agent-loop.mjs:263-267` reimplements a three-line `detectProvider` inline). `auth/oauth.mjs` is imported nowhere. Halbert's `tools/safety.py` + `AWAITING_CONFIRMATION` is genuinely better: it is reachable end to end (the `tool_confirmation_required` event name matches the frontend case and `confirm_action` resumes through the same `_drive()` loop), and it classifies by risk rather than by tool name. Keep it. Likewise Halbert's `saved_endpoints` — explicit provider + url + api_key, validated against `CHAT_CAPABLE_PROVIDERS` — beats what OCC runs, which cannot address a local runtime at all.

**Do not copy OCC's named model slots.** `settings.mjs:34-36` declares `subagentModel`, `fastModel`, `fastMode` and reads none of them; the code that picks a subagent model reads a *differently named* env var and never consults settings (`tools/agent.mjs:62`). That is OCC's own instance of this defect class. Halbert's three slots are genuinely resolved (`client.py:190-231`) and genuinely consumed. **Delete the layers under the slots, not the slots.**

**Do not delete `_effective_block` or `effectiveAssignments`.** See C1 — it backs a shipped fix (d2e8e79) that the pill depends on at `ModelSelectorPill.tsx:148`. Delete only `overridden_slots`/`overrideLayerFor` and the standalone route.

**Do not delete `model/router.py`.** See C2 — `Halbert/main.py` constructs it at seven sites.

**Do not delete `agents/conversation_sqlite.py` or `session_affinity.py`, and do not wire them either.** They have no production importer today (578 lines, 341 test lines, 33 passing tests). But `documentation/design/continuous-conversation-and-watched-terminals-2026-08-26.md:224` names `SqliteConversationStore` as the future store of record, and Plan B lists it as a Modify target — while itself being a DRAFT on an unmerged branch. Deleting it costs the founder's chosen direction; wiring it now is a large behaviour change with two known unreviewed issues (`conversation_sqlite.py:211` `save()`, the FTS5 concern at `:284`, both flagged in `.handoff/SOVEREIGN-HOST-REVIEW-FINDINGS-2026-08-25.md`). **The only correct action is to say plainly, in the Plan B document, that every step reading "modify `conversation_sqlite.py`" is building on a module the running system does not import** — and to make "wire it and re-point `routes/agent.py:937,972,1318,1329,1343` off the JSON store" step one of that work rather than an assumption inside it. `session_affinity.py` is not referenced by Plan B at all (`grep -n "session_affinity"` on it → no match); it goes with whichever way that decision falls.

**Do not write new tests against `agents/handlers/`, `react_agent.py`, or any module in §2.** `tests/test_agent_identity.py::TestRespondingFallback` is the cautionary case: three green tests asserting that "a wiring failure must not change who Halbert says it is", against a code path no user can reach, while the live `_handle_responding` has no such fallback and could regress that guarantee with the suite still green.

**Do not treat the 1506-test baseline as coverage of the running path.** Across the deletions above, roughly 1,900 test lines protect code no user action can execute. A green suite is currently weak evidence that chat works.