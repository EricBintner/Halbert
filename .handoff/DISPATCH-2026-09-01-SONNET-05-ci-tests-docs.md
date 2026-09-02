# DISPATCH SONNET-05 — CI gates, test rot, licence manifest, knowledge-index plumbing, document resync

**Owner:** a Sonnet session. **Effort:** medium-high volume, low risk. **Order:** LAST — after the code packets (OPUS-01..05, SONNET-01..04) have written their `RESULTS-*` docs, because the `MASTER-TODO.md` resync must reflect them.
**Parent:** `.handoff/HANDOFF-STATE-OF-WORK-2026-09-01.md` §4, §5, §6.8, §8. Evidence ids: pytest triage (`.handoff/audit-2026-09-01/PYTEST-BASELINE-TRIAGE.md`), `FE-10/12/16/17/18/20`, `RAG-01..24`, `LEG-GATE`, `U4-08`, `U4-14`, `U4-03/09/11`, `DOC-*`, `SE-34/35/36`, `VM-25/26`, `U2-32`, `TERM-15`, `PICK-07`, `HW-01/05`, `ENV-01/02`, `R05-10-DOC`.

## Shared rules
- Fresh worktree off main (`-b chore/ci-tests-docs`). `git branch --show-current` before every commit. No trailers.
- Python tests ONLY via `arch -arm64 /Volumes/4TB-BAD/Halbert/.venv/bin/python wt_pytest.py <paths>`. Never run `scripts/staged_knowledge_embed.py`, never call `prep*` MCP tools, never trigger a SourcePrep build while another runs (`ps aux | grep -E 'staged_knowledge_embed|prep.cli'`).
- You are the ONLY packet allowed to edit `.handoff/MASTER-TODO.md`. Refer to sibling apps only as H2/H3; never write "Sovereign" in prose (filenames excepted).

## Task 1 — CI (P1)
- `.github/workflows/ci.yml:214` installs `halbert_core/[dashboard,dev]`; `opencv-python` lives only in the `vision` extra (`pyproject.toml:95-97`) → `test_cv_extensions.py` (11) and `test_vision_tools.py` (2) have been red in CI since `067855c0` (2026-08-29). Either add the `vision` extra to the CI install or make the tests `importorskip("cv2")` (the helper at `test_cv_extensions.py:21` does not). Prefer installing the extra (the feature is shipped).
- `ENV-02`: CI still pins Node 20 while `.nvmrc` says 22 — align.
- `FE-20`: no `cargo test` job; 28 `#[test]`s in `src-tauri/src` never run in CI. Add a macOS-runner job (`objc2`/AppKit deps) that runs `cargo test --offline --no-run` at minimum.
- `FE-16`: the two Playwright smoke scripts need a live backend; leave out of CI but document how to run them.
- `FE-17`: root `npm run typecheck` silently skips the dashboard (no `typecheck` script in its `package.json`); add one.
- `FE-18`: `marketing/web-v7` has no test/typecheck scripts and no CI job; add at least `tsc`/build.
- Confirm remote CI status once `gh` is available (not installed on this machine).

## Task 2 — Test rot and the App Store licence gate (P1)
From the triage (all classified, with commits):
- `test_llm_discover.py:141` pins `{ollama, lm_studio}`; `discover_local_engines` now returns `apple_foundation` too (`routes/llm.py:939-966`, `944422d7`) — update.
- `test_multi_instance.py:96-104` sets only `HALBERT_PERSONA_ID=home`; role now derives from `_get_variant()` (`instance.py:31-38`, REV-03 F8, `7d01720e`) — set the variant.
- `test_llm_config_parse_cache.py` counts every `yaml.safe_load`; the extras are `being.yml` loads (`routes/agent.py:487` per-turn `load_being_config`; `capabilities.py:266/:276/:119`), not `models.yml`. Scope the counter to `models.yml`, and file the per-turn `being.yml` reload as a P3 perf note.
- `test_peer_tool_proxy.py:264-311` uses `asyncio.get_event_loop().run_until_complete` in sync tests under `asyncio_mode=auto` → replace with `asyncio.run(...)` or mark async (4 tests). (Coordinate with OPUS-03 if they got there first.)
- Licence gate (`RAG-12`/`LEG-GATE`): `test_corpus_license_gate.py` 2 failures. (a) `scripts/check_appstore_deps.py:74-86` parses the self-referential extras `halbert-core[dashboard]`/`halbert-core[…]` (`pyproject.toml:41,52`) as dependencies — fix the parser. (b) Register the unclassified deps in `config/dependency-licenses.yml` after verifying each upstream licence: python `mss`, `opencv-python` (wheels bundle FFmpeg — check), `sherpa-onnx`, `openwakeword`, `pyacoustid` (needs chromaprint); rust `cpal`, `webrtc-audio-processing` (the crate's own licence, not just the wrapped BSD-3 library); npm `@halbert/design-system`, `@halbert/model-picker` (first-party). Do not guess; anything copyleft goes to the founder sheet. Then fix `LEGAL-AND-LICENSING-TODO.md:74` ("currently passing").
- Do NOT touch the REV-06 seam tests, `speaker_role` doubles or meta_tools expectations — OPUS-01 owns them; nor the registry autouse fixture — SONNET-03.

## Task 3 — Knowledge index plumbing (P1)
- `U4-08`: `data/knowledge/linux/nvidia_cuda_compatibility.md` (from `162f3965`) sits in a brand-new directory nothing stages or indexes (corpus lives in `data/linux|macos|common`, staging at `~/.local/share/halbert/sourceprep/knowledge/<platform>`); the specialist prompt tells the model to retrieve it. Move it under the real corpus path, add it to the manifest, update its matrix to 2026 (580.x / CUDA 13 per the plan), and add a retrieval or quality-gate query that proves it is returned. Do NOT re-embed yourself — record that a re-embed is required and hand it to the founder (their build queue).
- `U4-14`/`RAG-06`: add `assigned_to_role: <name>-ops` to each `*_admin` scope in `sourceprep_template.yml` (`:48-94`) matching `skills/builtin/*/SKILL.md` roles (network-ops, service-ops, storage-ops, security-ops, config-ops …); add a test that every builtin skill role maps to a template scope. Without it `resolve_role()` (`sourceprep_retrieval_backend.py:351-375`) always returns `None` and routing falls back to the keyword heuristic. Re-applying to the live daemon (`RAG-05`) is a founder-scheduled step — say so.
- `RAG-07`: `_reconcile_scopes` can never remove paths (GET `/scopes` returns `path_count`, not paths) — fix if the daemon API allows, else document.
- `RAG-10`: delete `CODEINDEX-BUILD-LOCK.txt` (build finished 2026-08-26) and fix stale status headers in the RAG handoffs.
- `RAG-01` is in the CoDRAG repo (uncommitted daemon-side edits at `/Volumes/4TB-BAD/HumanAI/CoDRAG`: `search.py` +85, `models.py` +1, `core/index.py` +6) — report it prominently to the founder; do not commit in that repo from this packet.

## Task 4 — Documents: corrections (P2)
Apply the list in state-of-work §8:
- `documentation/FEATURES.md`: remove the eight non-existent Backend API endpoints, fix the scanner table (GPU/Development/Containers are route modules), rewrite the Settings/Chat/Terminal/Debug descriptions to the current UI, and mark Anomaly Detection / Recovery Playbooks / Dry-run Simulation / Why Brain as backend-only/unwired with no UI (`DOC-01..04`, `FEAT-01`).
- Retire or rewrite `documentation/GAPS.md`, `documentation/RAG_AUDIT_REPORT.md`, `documentation/design/prebuilt-knowledge-index.md` (ChromaDB era; the last argues against the architecture that shipped) — default: move to `documentation/archive/` with a banner.
- `documentation/RAG-DATA-SOURCES-2026-08-24.md` §1.1: 45 JSONL files tracked, 13 ignored by `.gitignore:123 *.jsonl` (71 MB incl. macOS man pages, Arch Wiki, tldr) — state it honestly pending founder decision `RAG-13`.
- `IMPL-PLAN-SINGULAR-ENTITY-TASKS-2026-08-31.md`: change "Status: COMPLETE" to "code units complete; not usable end to end" with the P0 list from state-of-work §6.3; fix the `test_cognition_tick_once` note (deterministic `R06-F2`, not order-sensitive).
- `HANDOFF-VOICE-MODE-OPUS-RESULTS-2026-09-01.md`: P4 review done (`88413a42`); "O3 end-to-end" only under a mocked modality; drop the "confirm before touching design-system voice files" caveat.
- `HARDWARE-VALIDATION-MATRIX-2026-08-31.md` notes: P2/O3/O5 are on main.
- `REV-03-RESUBMISSION-2026-08-31.md`: F3/F4/F10 partially open (`R3-F03/F04/F10b`).
- `TASK-PACKET-03/09` headers; `documentation/design/unified-model-picker.md` "Superseded 2026-08-26" header; the four workstream docs still marked DRAFT/awaiting input for merged work (`DOC-01` in F25: continuous conversation, Plan B, model-picker cleanup, multi-persona).
- `HANDOFF-N150-*` checklists reference the removed `home-light` variant; `HANDOFF-LOW-POWER-…` S2/S3/S4 boxes done in code.
- Python floor: README/INSTALLATION say 3.11+, `pyproject`/PKGBUILD/venv say 3.10 — pending `ENV-01`; add a one-line note in INSTALLATION that the tested floor is 3.10 until the founder decides.

## Task 5 — `MASTER-TODO.md` resync (P1, last)
Rewrite §0–§3 against reality (keep the strike-through convention):
- Strike U1 (tests exist; verification done; rebuild = SONNET-01 status), U2 (four TASK-07 items done; list `U2-05/07/09/15` as the open voice items), U3 (all four done; lazy mounting open), U4 (env override, GPU tools, role taxonomy done; open: `U4-06/08/09/14/18/20`), U6 (all merged; D2/D4/Q3/Q4 resolved pending ratification; open regressions `U6-BUG-01..04`).
- Add a "Review remediation backlog" section with one row per REV-04/05/06/08/09/10/11 finding and its packet owner, seeded from state-of-work §6 and the `RESULTS-*` docs.
- Add rows for: Voice Mode visual UI (done; open `VM-STT`, `VM-15`, `VM-22`, `VM-27`), singular entity (open P0s), branch hygiene outcome (SONNET-02 results), CI status.
- Move every founder-gated item to a pointer at `DISPATCH-2026-09-01-FOUNDER-DECISIONS.md`.
- Update the "Updated" date and the Rust section's note that the rebuild is deferred by direction (`HA-01`).

## Results
`.handoff/RESULTS-SONNET-05-<date>.md`: CI changes, test counts, licence classifications with sources, doc list changed, and the re-embed/re-apply steps handed to the founder.
