# Fable Handoff — Results (Remaining Work, 2026-08-25)

Results for [FABLE-HANDOFF-REMAINING-WORK-2026-08-25.md](./FABLE-HANDOFF-REMAINING-WORK-2026-08-25.md).
Every premise in the handoff was re-verified before acting; several were wrong
(called out per task). Test runner: `.venv/bin/python -m pytest halbert_core/tests/ -q`.

| Task | Outcome |
|---|---|
| F1 Install Haloysius | Done. 769 passed / 2 skipped → **771 passed / 0 skipped** (the 2 cognitive A/B tests now run and pass). Optional extra `cognition` added to pyproject (`f722f79`). |
| F2 CodeIndex smoke | **Superseded / do not repeat.** `knowledge/common` was already fully embedded (4150 chunks); a `--stage 1` build was already running in another session (PID 32969, ~10h in at 20:05). See F2 notes. |
| F3 halbert-api binary | Done + verified (`5dc0906`). Launches via uvicorn; serves `/api/agent/health` in ~10s. |
| F4 ModelBackend → TierRouter | Done + tested (`f7d9505`); 9 new tests, suite **780 passed**. Inert on this host — see bugs B2/B3. |
| F5 Boot smoke | **5/5 PASS** (server started via the F3 script on port 8011; port 8000 was held by another session's test server). |
| F6 format_context | **Dead.** Zero callers in Halbert; Haloysius never calls it either — Haloysius never consumes the seam's `RetrievalBackend` at all (only defines the Protocol). Safe to remove; `max_chars=1500` question is moot. |
| F7 Cognition tick | Wiring initialises at startup, but the tick **never fires** on real turns — see bug B1. |

## F2 notes
- The staged embed script's `REPO_ROOT` is `~/.local/share/halbert/sourceprep`, not this repo — `knowledge/common` lives there (8 dirs, 20 md files, 5 MB).
- My `--paths knowledge/common` run was a no-op: `files_reused: 20, chunks_reused: 4150, chunks_embedded: 0`, 1.3 s. It rewrote byte-identical `documents.json`/`embeddings.npy`/`fts.sqlite3`/`manifest.json` (snapshot in `backups/pre_stage_20260825_200225`). It ran concurrently with the user's stage-1 process, which the script's own docstring warns against. **User directive: never run embeddings while theirs is running; wait for stage 1 and use its output.**
- Throughput/ETA could not be measured (nothing embedded). Stage-1 stdout is not in a file.
- The daemon caches the index in memory; `status` will keep reporting 98 chunks / `source: knowledge` until the daemon is restarted after stage 1 finishes. The scoped-query acceptance check should be run then.

## Bugs discovered (not fixed — outside fable scope)
- **B1 — REFLECTING is unreachable on the normal path** (`agents/state_machine.py`). Observed on 3 turns (greeting, sshd_config question, disk-space question): `PLANNING → SEARCHING → OBSERVING → PLANNING → RESPONDING`. `OBSERVING` only transitions to `REFLECTING` when CRAG says `CORRECT` or `loop_count >= max_loops-1`; with empty retrieved context confidence is hard-set to 0.30/`INCORRECT`, so it goes back to `PLANNING`, and the second `PLANNING` pass goes directly to `RESPONDING`, bypassing `REFLECTING`. Net: `cognition_tick` is wired but never called. Fix candidates: route `PLANNING → RESPONDING` through `REFLECTING`, or run the tick in `RESPONDING`.
- **B2 — `TierRouter._find_config` off-by-one.** `Path(__file__).parent×5 / 'config' / 'models.yml'` resolves to `/Volumes/4TB-BAD/config/models.yml`, one level above the repo, so the repo's `config/models.yml` is never found and `TierRouter()` loads 0 models (`No model available for tier: guide`). Note `routes/compression.py` uses `parents[3]` (→ `halbert_core/config/`), also wrong, and `routes/agent.py` uses `get_config_dir()/models.yml` (`~/Library/Application Support/Halbert`, absent here). Three different discovery rules; none finds the repo file.
- **B3 — TierRouter has no production consumers.** Nothing in `halbert_core` instantiates `TierRouter` (only `test_cascade_router` via a stub). F4's wiring is the first; it falls back to raw Ollama on this host because of B2.
- **B4 — Haloysius never consumes the seam backends.** No code in Haloysius calls `get_model_backend()` / `get_retrieval_backend()` / `get_governance()`; only `seam.py` defines them. So `HalbertModelBackend.chat()` and `SourcePrepRetrievalBackend.search()/format_context()` have no callers anywhere. The AppSeam is registered but unused.
- **B5 — `python -m halbert_core.dashboard` is broken.** `dashboard/__main__.py` imports `create_dashboard_app` from `.app`, which only defines `create_app` (since `a94877d`). `python -m halbert_core.dashboard.app` (code-map.md, handoff) is a no-op — `app.py` has no `__main__` block. Working form: `python -m uvicorn halbert_core.dashboard.app:app`.
- **B6 — Tauri never launches the sidecar.** `lib.rs` has no `Command::sidecar`/spawn; `capabilities/default.json` grants no `shell:allow-spawn`/`shell:allow-execute`. The binary is bundled but nothing starts it. Also, once bundled into a `.app`, the script's walk-up-to-repo-root default will not find a checkout; set `HALBERT_REPO_ROOT` or ship a real bundle.
- **B7 — `app_seam.py` imports haloysius at module level** (not lazily as the handoff claims). It's only reached through guarded callers (`cognition_wiring.get_event_mapper`, `test_app_seam_model_backend` uses `importorskip`), so nothing breaks without haloysius, but it's not itself lazy.
- Startup warnings seen (not investigated): `Could not initialize memory service: No module named 'halbert_core.memory.store'`; `Journald ingestion error: journalctl not found` (macOS, expected).

## Concurrency notes
- Another session had created `src-tauri/binaries/halbert-api-{aarch64,x86_64}-apple-darwin` at 20:00:50 and was testing on port 8000 (`/private/tmp/halbert-api-test2.log`, system-Python uvicorn, cwd = `binaries/`). My first write at 20:04 overwrote those files. The committed version is the verified one.
- Another session committed `1043b40 docs(handoff): remaining work handoffs for fable and opus tracks` during this run.

---

## Fix round (2026-08-25, later the same day) — "do all this"

All bugs B1–B9 above were fixed, plus the deeper causes found on the way. Three
workflow rounds (investigate → implement → adversarial review + live server
verification), suite **780 → 912 passed**, boot smoke 5/5 throughout.

| Commit | What |
|---|---|
| `bb8de0f` fix(model) | single models.yml locator (`model/config_locator.py`); TierRouter finds the user config (1 model, kimi) instead of 0; compression route reads/writes the user file; trending discovery uses the configured model |
| `4d5a7a5` fix(agents) | cognition tick fires on every turn (PLANNING→REFLECTING + guarded safety-net in RESPONDING); pure greetings skip SEARCHING; AWAITING_CONFIRMATION pauses instead of busy-looping; max-loops guard no longer infinite-loops; ERROR give-up no longer raises error→success |
| `93a2edd` fix(retrieval) | SourcePrep project id resolved from `~/.local/share/halbert/sourceprep/.sourceprep/project.json` (was never set → every retrieval returned []); SEARCHING uses SourcePrepAdapter; CRAG scoring fixed (tokenisation, retriever score, robust LLM-reply parsing) |
| `dffe05d` fix(memory) | context memory adapters pointed at modules that exist (`memory.store` never existed); hybrid memory's self-knowledge + embeddings wiring fixed (two more nonexistent-module imports) |
| `d1e6555` fix(integrations) | seam ModelBackend follows the agent's config; `HALBERT_LLM_THOUGHTS=1` opt-in LLM thought generator; lazy haloysius import; `format_context` removed; honest docstrings |
| `07b6869` fix(dashboard) | `python -m halbert_core.dashboard` works; journald skipped off-Linux; Tauri CORS origins |
| `095acf7` feat(tauri) | sidecar spawn/kill + parent-pid watchdog; frontend API base for tauri://; **Halbert.app + DMG built** and launch/quit-tested |

### Live verification (server on :8012 / built .app on :8014)
- Greeting turn: `planning → reflecting → responding → idle`, no retrieval, one `thinking` event, no host files in the answer.
- Question turn (PermitRootLogin): `planning → searching → observing → planning → reflecting → responding → idle`, 5 SourcePrep hits (host scope), CRAG relevance 0.42 / confidence 0.37 (was 0.00/0.20), correct answer.
- No `Could not initialize memory service`, `Self-knowledge search failed`, `Embedding service not available`, `Journald ingestion error`, or tracebacks. `Cognitive tick complete` once per turn.
- Built app: sidecar starts, webview polls `/api/settings/metrics|docs/stats|scan/status` through the injected API base with CORS OK; backend exits within 3s of the shell dying (kill -9 and SIGTERM tested).

### Still open (need product decisions or your running build)
- **CRAG completeness is honestly 0.0**: SourcePrep currently returns catalogue summaries (File/Role/Summary) for sshd_config, not file bodies, so the LLM says the docs cannot answer. Expect this to change once stage 1 finishes and the daemon is restarted (O1/O4).
- **O5 memory persistence**: tick runs, template thoughts are generated ("This place…") but none reached the promotion threshold in test turns; `~/.local/share/haloysius/personas/halbert/memories.json` not created yet. Re-check after longer sessions / with `HALBERT_LLM_THOUGHTS=1`.
- `confirm_action()` runs only `_handle_executing` and evicts the session — a confirmed action never produces a RESPONDING/response_complete (pre-existing).
- `LLMClientAdapter.chat` ignores `tools`, so EXECUTING/READING/AWAITING_CONFIRMATION are unreachable from the API; the chat approval flow and `routes/approvals.py` are not bridged.
- Somatic blocks (C1d) have no producer in production.
- Greeting persona answers as a generic "AI assistant" (prompt/persona content, not wiring).
- `ProbeButton` calls `/compute/endpoint-probe`, which no backend route serves.
- Tauri: fixed port 8000 (override `HALBERT_PORT`); unsigned bundle; the .app still needs a checkout + .venv (`HALBERT_REPO_ROOT` for out-of-tree installs); Cmd-Q itself was not exercised headlessly (watchdog covers it regardless); no vitest for the frontend (tsc + static guard only).
- Haloysius-side: whether its core should consume the seam registry (or the seam be documented as consumer-side only) — needs an owner decision; nothing in Haloysius was changed.
- Another session's licensing work (`documentation/legal/`, `routes/legal.py`, `components/legal/`, `.github/`, `Halbert/main.py`, `config/model-catalog.yml`, `CONTRIBUTING.md`) was left uncommitted and untouched.
