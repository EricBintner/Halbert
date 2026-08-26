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
