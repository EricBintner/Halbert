# PKT-SUPPORT-BUNDLE — Redacted support bundle (zip: config, doctor JSON, log tail)

Tier: **opus**   Milestone: **M3**   Effort: **S-M**
Collision lane: **none (file-disjoint)**   Merge order: **n/a**
Verified against: halbert `main` @ `fbd725e9` (2026-09-11)

---

## 1. Packet

**SUPPORT-BUNDLE** — Redacted support bundle (zip: config, doctor JSON, log tail).

## 2. User problem

When Halbert misbehaves, the founder has no way to hand over a safe diagnostic snapshot. Today's pieces are scattered and individually unsafe: `dashboard/__main__.py:21-25` builds "JSON" log lines by %-interpolation (any quote/backslash/newline in a message breaks the record), there is no log file at all until LOG-01 lands, config files under the config dir contain secrets in plaintext, and doctor/health output (DIAG-01's `/api/diagnostics` JSON) is about to exist but has no export path. The deep-eval confirmed this twice as OC08-C7 (LOG-01) and OC09-C13 (T5) — the same mechanism proposed in two packets — and the backlog verdict (section 3.6 "One support bundle", line 312; cross-cutting line 530) rules: one bundle, one redaction variant, one packet, staged locally and never sent, redacted deterministically through the registry — never a model. The user-facing need is a single "stage a support bundle" action that produces a zip under the data dir containing redacted config copies, the DIAG-01 doctor JSON, and a bounded redacted log tail, so a broken install can be diagnosed without the founder hand-scrubbing files or pasting secrets into a chat.

## 3. What to build

One new module `halbert_core/halbert_core/obs/support_bundle.py` implementing `build_support_bundle(dest_dir: str | None = None, *, log_bytes: int = 256_000) -> Path` plus a small staged-export route. Concretely:

1. `build_support_bundle()` assembles a zip via stdlib `zipfile` (ZIP_DEFLATED) into `data_subdir("support")` (utils/paths.py:85) named `halbert-support-<utc ISO>-<short uuid4>.zip`, with an allow-listed member set — never a directory walk:
   - `doctor.json` — the DIAG-01 doctor output. Import the registry from `halbert_core/halbert_core/obs/doctor.py` (new in DIAG-01) and serialize the same `DiagnosticFinding(domain,code,severity,message,why_trust,remediation)` list the `/api/diagnostics` route in `halbert_core/halbert_core/dashboard/routes/diagnostics.py` serves. If DIAG-01 has not landed in the merge wave yet, call `utils/health.py:get_system_health(include_api=True)` (:235) and serialize its `SystemHealth` as the fallback member `health.json` — the bundle must build on main today and upgrade to doctor.json when DIAG-01 merges.
   - `config/` — copies of the known config files only (being.yml, models.yml, preferences.yml, mcp_config.yml — resolve via `utils/paths.py:config_dir()`), each passed through the redaction pass before writing into the zip.
   - `logs/halbert.log.tail` — the last `log_bytes` bytes of the RotatingFileHandler file LOG-01 installs under `log_subdir()` (utils/paths.py:88), read with the byte-bounded tail reader from LOG-01 that drops a corrupted partial first line. If the file does not exist yet (pre-LOG-01 or fresh install), write a one-line `logs/README` member stating no log file exists — never fail the bundle over a missing log.
   - `manifest.json` — bundle format version, Halbert version (from `halbert_core/__init__.py:__version__`), UTC timestamp, member list with per-member byte counts, and the redaction registry's variant count so a reviewer can confirm the pass ran.
2. One redaction function `_redact_member(text: str) -> str` that applies the exact same order as the Tier-2 choke point and the LOG-01 filter: `get_global_registry().redact_text(text)` (ingestion/redaction_registry.py:150) first, then `ingestion/redaction.redact_text(..., prose=True)` (:1221). Registry first, pattern pass second — the pattern pass rewrites part of what it matches, and an exact-value registry cannot match what has already been partly rewritten (A03-G2). Wrap each member's redaction in try/except that, on redactor failure, substitutes the literal member content `<redaction failed: member omitted>` — a bundle that silently carries an unredacted secret is worse than a missing member, and a bundle that raises is worse than both.
3. Path safety: member names are the fixed allow-list above; no member name is ever derived from a path read off disk (zip-slip is a non-issue by construction, not by sanitization).
4. Dashboard surface: `POST /api/diagnostics/support-bundle` added to `halbert_core/halbert_core/dashboard/routes/diagnostics.py` (DIAG-01's route file; if DIAG-01 is unmerged at dispatch time, put the route in `dashboard/routes/system.py` instead and move it when DIAG-01 lands — note this in the commit message). The route calls `build_support_bundle()` and returns `{staged: true, path: <absolute zip path>, bytes: <n>}`. Staged, never sent: no upload, no FileResponse download-on-GET-without-confirmation, no telemetry hook. The UI button (follow-on, not this unit) stages and shows the path.
5. Tests: `halbert_core/tests/obs/test_support_bundle.py` covering (a) bundle builds with all members present when doctor/health, config, and log exist; (b) a planted secret registered in `get_global_registry()` appears nowhere in any member's bytes (assert on the raw zip bytes, not the Python strings); (c) missing log file yields the README member, not an exception; (d) a redactor that raises yields the omission sentinel, not the unredacted content and not an exception; (e) member names match the allow-list exactly.

## 4. What NOT to build

- No Logs page UI and no frontend button — the UI that stages the bundle from the dashboard is follow-on work after DIAG-01's page lands (deep-eval line 73/76: Logs page OC23-C16 is M effort, deferred past the MVP). This unit is the backend mechanism plus the staging route only.
- No upload, send, share, or telemetry path of any kind. Staged means staged: the zip is written under the data dir and its path is returned. Any "send to support" flow is a separate, future, founder-gated decision — do not even stub an upload function.
- No second redaction variant registry for "diagnostics export" (OC04-M6) as a standalone mechanism — the deep-eval folds it into this one bundle with this one pass (registry-first ordering). Do not fork `_redact_log_text` from obs/logging.py:10 into a near-copy; call the same two primitives it calls.
- No recursive config-dir or log-dir sweep into the zip. Only the allow-listed members. A directory walk is how an unexpected secrets file (or a 2 GB rotated log) ends up in a bundle.
- No model involvement anywhere in the pipeline — no summarization, no "sanitize this for me" LLM call. Deterministic registry + pattern redaction only (standing rule: never a model where a template suffices).
- No new CLI subcommand (`halbert support-bundle`) — DIAG-01 owns the `halbert doctor` CLI shape; a bundle subcommand would be a second CLI surface to reconcile. The Python API plus the route is the whole interface.
- No migrations, no reading of superseded bundle formats, no cleanup of old bundles beyond leaving them on disk (standing rule: no users yet; leave superseded data on disk, unread, never delete).

## 5. Target files
- `halbert_core/halbert_core/obs/support_bundle.py` [new file]

## 6. Dependencies

DIAG-01, LOG-01

## 7. Effort

**S-M** — S-M, matching the packet header and the deep-eval's own split. The mechanism is small because every hard part already exists and is owned elsewhere: the redaction primitives (`get_global_registry().redact_text`, `ingestion/redaction.redact_text`) were built by R-05 and are already composed in exactly the required order by `obs/logging.py:_redact_log_text`; path resolution is `utils/paths.py`'s `data_subdir`/`log_subdir`/`config_dir`; the doctor payload is DIAG-01's output with `utils/health.py:get_system_health` as a working fallback; the byte-bounded tail reader is LOG-01's. What remains is one zipfile assembly with an allow-listed member set, one redaction wrapper with a fail-closed omission sentinel, one thin route, and five focused tests — that is S. It trends toward M only because of the two integration seams it must straddle: it must build green on main today (pre-DIAG-01, possibly pre-LOG-01 file) while upgrading cleanly as each dependency lands in the wave, and the fallback path plus the missing-log and redactor-failure branches are real test cases, not hypotheticals. The deep-eval rated the bundle M when it was entangled with the rest of T5; split out as this unit with the dependencies named, S-M is honest.

## 8. UX rationale

The support bundle is how the computer answers "something is wrong — show me" without the founder becoming a redaction engine. In Halbert's frame the system speaks as the machine itself in first person, grounded in measured data: the bundle is exactly that — measured data (doctor findings with `why_trust` provenance, health checks, the actual log tail) packaged by the machine about itself. The interaction contract is one action, staged, with a concrete result: a path to a zip the founder can inspect before it goes anywhere, consistent with the standing rule that anything staged from a surface is staged, never executed — here, never transmitted. There is no new conversation surface, no list, no dialog chrome beyond what DIAG-01's diagnostics page already provides; the route returns a path, and surfacing that path (a staged card in the one seamless conversation, or a line on the diagnostics page) is the follow-on UI's job. Nothing in the bundle names an AI model; doctor findings name checks and paths, not providers. No emoji, no new colours — this unit ships no frontend pixels at all, so the tokens palette is untouched. The trust property that matters is verifiable: the manifest records that the redaction pass ran, and the test suite proves a planted secret does not survive it.

## 9. Acceptance criteria

1. `POST /api/diagnostics/support-bundle` returns 200 with `{staged: true, path, bytes}` and the named zip exists on disk at that path under `data_subdir("support")`.
2. The zip contains the allow-listed members only: `manifest.json`, `doctor.json` (post-DIAG-01) or `health.json` (fallback), one redacted file per known config under `config/`, and `logs/halbert.log.tail` or `logs/README` when no log file exists.
3. A secret registered in `get_global_registry()` during the test is absent from every byte of every member; `manifest.json` records the redaction variant count.
4. Bundle builds successfully on a fresh install with no log file and no doctor module (health fallback), and again after DIAG-01 and LOG-01 land, with no code change required in this unit beyond the documented import seam.
5. A redactor that raises produces the omission sentinel for that member and a still-valid zip — never an HTTP 500, never unredacted content.
6. All five tests in `halbert_core/tests/obs/test_support_bundle.py` pass; no failure appears that is absent from the known-red baseline on main (test_agent_model_override.py, test_agent_model_selected_event.py, test_no_model_names_in_user_facing_source.py, test_num_ctx.py, ~23 failures as of 2026-09-11).

## 10. Verification (measured state, not model judgment)

Run from the worktree: `arch -arm64 ./wt_pytest.py halbert_core/tests/obs/test_support_bundle.py -v` (never bare pytest — the shared venv's editable install pins `halbert_core` to the main tree; `wt_pytest.py` strips that finder; the `arch -arm64` prefix is mandatory or pydantic_core dies with the x86_64 ImportError). Every test in the file must pass; confirm no new failures elsewhere with `arch -arm64 ./wt_pytest.py halbert_core/tests -x -q` compared against the known-red baseline. Then measure OS-observable state end-to-end: with the backend running (`make dev-web`), `curl -s -X POST http://localhost:8000/api/diagnostics/support-bundle | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d["staged"], d["bytes"])'` prints `True` with a positive byte count; `unzip -l <path>` lists exactly the allow-listed members; and `unzip -p <path> config/models.yml | grep -c <planted-secret>` returns exit code 1 (zero matches) after planting a registry-known secret in a test config. Exit codes and zip listings are the oracle — not a read-through of the output.

## 11. Exclusions

Real exclusions and where each goes: (1) Logs page with cursor-based incremental tail (OC23-C16) — stays in LOG-01's deferred tail, M5b per the dispatch index. (2) The frontend staging button/card that surfaces the bundle path — follow-on UI after DIAG-01's diagnostics page lands; M5b. (3) The standalone "diagnostics-export redaction variant" (OC04-M6) as its own mechanism — dropped per RESHAPE: deep-eval line 261 and backlog section 3.6 fold it into this one bundle with one redaction pass; building a second variant registry would duplicate R-05. (4) T5's OC09-C13 bundle as a separate artifact — dropped per RESHAPE ("one bundle, not two", deep-eval line 530); this unit IS the merged bundle. (5) Log tailing machinery beyond the bounded read — owned by LOG-01's tail reader; this unit consumes it and degrades to the README member if absent. (6) The doctor findings registry itself and `/api/diagnostics` — owned by DIAG-01; this unit consumes its output with a `utils/health.py:get_system_health` fallback. (7) Any upload/transmission channel — out of scope entirely; no packet owns it because it is an unmade founder decision, not deferred engineering.

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
