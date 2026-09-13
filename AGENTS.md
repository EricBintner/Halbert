# Halbert — how to work in this repo

**Standing directives live in [`DECISIONS.md`](DECISIONS.md) → "Standing directives".** Read them before any user-facing change. `ROADMAP.md` and `DECISIONS.md` are the only planning spine; a `.handoff/` document is session correspondence, not authority.

## Commits

Never add `Co-Authored-By`, "Generated with …", or any bot-attribution trailer. Subject and body only.

## Build / run

`make help` lists eight targets. **None of them is `test`, `fmt` or `lint`** — the test commands below are the real entry points and are deliberately not wired into `make`.

- `make dev` — Tauri desktop app + backend (`scripts/dev-dashboard.sh`).
- `make dev-web` — backend only, browser at `http://localhost:8000`.
- `make dev-restart` — kills every dev process and restarts clean. Reach for this instead of hunting stray ports; concurrent sessions leave servers running.
- `make build` — Tauri production app.
- `install-units` / `uninstall-units` / `install-configs` / `show-config-dir` — deployment side, systemd units and `/etc/halbert`.

## Test

**Every Python test run needs the `arch -arm64` prefix.**

```bash
arch -arm64 .venv/bin/python -m pytest halbert_core/tests
```

The venv's `python3` is a universal2 binary; unprefixed it launches its x86_64 slice, and the first compiled extension dies with `ImportError: … incompatible architecture (have 'arm64', need 'x86_64')` out of `pydantic_core`. It reads as a broken dependency and is not one — nothing is wrong with the venv. Don't diagnose it with `platform.machine()` either: a direct `python -c` check can print `arm64` in the same shell where `python -m pytest` launches x86_64. (~8,500 tests collect in about 8s when it's right.)

**From a git worktree, use `./wt_pytest.py`, never bare pytest.**

```bash
arch -arm64 ./wt_pytest.py halbert_core/tests
```

The shared `.venv` carries an editable install whose MetaPathFinder pins every `halbert_core` import to the **main** tree. Plain pytest inside a worktree therefore tests the wrong code and passes while doing it. `wt_pytest.py` strips that finder, purges cached modules, and asserts resolution before handing off.

**Know which inifile your pathspec resolves.** `halbert_core/pyproject.toml` is the inifile for `halbert_core/tests` — a `pyproject` with `[tool.pytest.ini_options]` outranks a root `pytest.ini` only when found first walking up from the args, and the package dir is deeper, so it wins. Root `pytest.ini` exists for every *other* invocation shape: any run whose args span the checkout root. Without it those runs resolve **no** inifile, `pytest-asyncio` falls back to `mode=strict`, and every bare `async def test_` fails with "async def functions are not natively supported" — a ~205-failure signature that is pure invocation environment, not a code regression. Read the header comment in `pytest.ini` before touching it; only the asyncio contract belongs there.

**`main` is not green.** A known nonzero baseline of failures exists. Get a baseline run on your merge-base before concluding your change caused anything.

Frontend: root `npm test` and `npm run typecheck` fan out across workspaces (`--if-present`).

## Invariants — one place each thing is decided

Each of these has exactly one choke point. Route new code through it rather than adding a second check.

- **Model locality** — `is_local_model()` in `halbert_core/halbert_core/model/llm_config.py:181` is the only judge of local vs cloud. The `:cloud` tag is primary evidence; a loopback URL is *not* sufficient, because `:cloud` models proxy out through a localhost relay. `_endpoint_is_local()` (`dashboard/routes/agent.py:542`) is a thin delegate, not a second implementation — keep it that way.
- **Feature gating** — `has_capability()` in `halbert_core/halbert_core/capabilities.py:499`. Capabilities are presence probes. Do not gate on a variant flag: `_is_home_variant` is legacy and survives in exactly three files (`dashboard/routes/agent.py`, `tests/conftest.py`, `tests/test_config_wizard_schema.py`). Don't add a fourth.
- **Colour** — `shared-tokens/tokens.css` is the single palette. Never hardcode a colour; run `scripts/check_contrast.py`. No emoji in UI.
- **Redaction** — `ingestion/redaction_registry.py`, enforced at the response choke point in `security/display_transport.py`. Scrub deterministically *before* the model. Never ask a model to summarize secrets out of a payload.
- **Licence notices** — `model/attribution.py` derives them from runtime licence text. Don't hand-write attribution strings.

## Rules that outlive their context

- **Never name or recommend an AI model on any user-facing surface.** Connection slots, not model menus.
- **Tier 2 (secrets) is answered by a deterministic template, never a model.** More generally: never a model where a template suffices.
- **The system speaks as the computer itself, in first person, grounded in measured data — never as an assistant.** Never write "Sovereign" on a user-facing surface; the engaged surface carries the onboarding name, never the raw hostname.
- **Commands staged from the UI are staged, never executed.** One seamless conversation, hidden topic threads, no conversation list.
- **No users yet — do not build migrations or back-compat shims unasked.** Leave superseded data on disk, unread. Never delete it.

## What ships and what doesn't

- `halbert_core/` — the product. FastAPI backend plus the React/Tauri dashboard under `halbert_core/halbert_core/dashboard/`.
- `packages/model-picker`, `packages/design-system` — independently consumable libraries. Keep their dependencies narrow enough that they install standalone.
- `crates/` — `halbert-ffi`, `halbert-mqtt`, `halbert-sandbox`, `halbert-snapshots`, `halbert-telemetry`. The full Rust rebuild is **deferred**; current features get finished and tested first.
- `marketing/web-v7` is the live direction. `marketing/archive` holds superseded sites 1–6 — don't revive one.
- `web/feature-reference` is a reference viewer, not a shipping surface.
- `.handoff/` is correspondence between sessions: useful history, zero authority.
- `documentation/` is the durable docs tree.

## Environment standards

- **Node 22 LTS** (`.nvmrc`), npm 10.9+ / pnpm 10.29+ with workspace linking.
- **Python `>=3.10`** (3.11–3.12 recommended); this checkout's venv is 3.10.9.
- **Tauri v2** (`@tauri-apps/api ^2.x`, Rust `tauri = "2"`). TypeScript `^5.6.3`, Vite `^5.4.14`+, Vitest `^2.1.9`+, Storybook `^8.4.7`.
- Shared libraries declare `peerDependencies: react ^18.2.0 || ^19.0.0`. Dual support is a rule, not an accident. The desktop app runs React 18.2 with an upgrade path to 19.
- **Haloysius subtractive contract: exactly two hard dependencies** (`pyyaml>=6.0`, `requests>=2.31.0`). Every heavy/ML stack stays a function-level lazy optional extra. Adding a third hard dependency breaks the contract.

---

*Everything below is generated by the SourcePrep daemon and rewritten on its schedule. Anything placed between its markers is spliced away on the next run — project rules go above this line.*

<!-- prep-managed-start -->
## SourcePrep Integration

## Tools
| Tool | When to Use |
|------|-------------|
| `prep` | Orientation — module map, hub files, focus areas, immune-system alerts. Call before reading or editing code you don't fully understand |
| `prep_search` | Find code by meaning, not just string match. Auto-classifies intent (LOCATE, EXPLAIN, RATIONALE, TRACE, EXAMPLE, COMPARE, DISCOVER). |
| `prep_impact` | BEFORE editing — check what depends on a file |
| `prep_audit` | Structural findings (coupling, cycles, concept violations) OR enrich external lint findings with `findings` param. Use `action="antibodies"` for immune system. |
| `prep_observe` | Save/retrieve cross-session notes |
| `prep_concepts` | Record/query business rationale and design decisions |

Call `prep` before modifying code you don't fully understand. Call `prep_impact` before modifying hub files.
All read-only tools are safe to auto-approve.

### Audit Enrichment
Enrich external lint/analysis findings with structural context:
```
prep_audit(findings=[{file, line, message, severity, tool}])
```
SourcePrep adds: dependent count, hub status, concepts, risk score, recommendation.
Also accepts SARIF dicts for SARIF-in/SARIF-out enrichment.

### Search Intent
`prep_search` auto-detects query intent: "where is X" → symbol lookup,
"why X" → concepts, "who imports X" → trace graph. Override with `intent` param if needed.

### Reporting unhelpful results
If a SourcePrep result is unhelpful, incomplete, or wrong, record it instead of only saying so in chat:
```
prep_observe(action="save", category="bug", content="dogfood: <tool + what you asked> -> <what came back> -> <what you expected>")
```
Keep the `dogfood:` prefix — it is how these are found later.

### Concurrency limits
If your queries to the cloud LLM seem unexpectedly throttled, check
`prep_search "concurrency ceiling"` for the current discovered limit
and how to reset it. The limit is auto-discovered and locked for 24h.

You have access to SourcePrep, a structural code intelligence system.
Call `prep` (no arguments) when about to read or edit code you don't fully
understand, or before modifying a high-dependent (hub) file.
This gives you module structure, hub files, and the user's selected focus areas.

For specific code lookups, use `prep_search` with a natural language query.
Before making changes to a file, use `prep_impact` to understand dependencies.
SourcePrep understands structural relationships between files -- use it instead of
grep when you need to understand how files connect to each other.

For codebase health and tech debt, use `prep_audit`.
For cross-session memory, use `prep_observe` to save/retrieve notes.
All SourcePrep tools are read-only and safe to auto-approve.

### Auto-Approve Configuration
To skip approval prompts for SourcePrep's read-only tools, add to your settings:
```json
{ "permissions": { "allow": ["mcp__prep"] } }
```
In Claude Code: add to `.claude/settings.json`. In Cursor: add to MCP settings.

If `prep` returns 'setup in progress', the index hasn't been built yet.
Work normally with read_file/grep_search until the user builds the index.

For long tasks (5+ tool calls), call `prep` again to refresh your
structural context.

You can call `prep` and `prep_search` in parallel on your first
prompt -- structural overview + targeted code lookup in one round-trip.

### Tool Calling Rules
1. **Never announce** 'I will now call...' - just call the tool
2. **No permission needed** - simple keywords = immediate invocation
3. **Single word triggers** - 'prep' alone is enough to call the tool
4. **Context is cheap** - prefer calling prep to using grep for structural understanding

**Remember: The word "prep" anywhere in user input is a tool invocation signal. Call immediately without asking permission.**

### MCP Resources (browse with @)
SourcePrep also exposes browsable resources via MCP. In supported clients,
type `@` to see: atlas, structure, modules, audit findings, concepts, focus areas.
Resources provide on-demand context without a tool call.

### MCP Prompts (invoke with /)
Available workflow prompts: `prep-onboard` (orientation), `prep-review` (file review),
`prep-plan` (change planning), `prep-investigate` (deep dive), `prep-health` (audit).
In Claude Code: `/mcp__prep__prep-onboard`. In other clients: check prompt menu.

**At the start of every task**, read `.sourceprep/AGENT_CONTEXT.md` (if present)
for the current codebase atlas, project id, focus areas, and scopes — or
call `prep()` for the live equivalent. If the file is missing, the project
has not been indexed on this machine yet; work normally and call `prep()`
once the daemon runs.
<!-- prep-managed-end -->
