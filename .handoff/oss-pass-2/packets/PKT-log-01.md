# PKT-LOG-01 — Structured redacted logging (JsonFormatter+RotatingFileHandler+RedactingFilter+LogRecordFactory)

Tier: **opus**   Milestone: **M3**   Effort: **M**
Collision lane: **Q,E**   Merge order: **1/2 in Q; 3/3 in E**
Verified against: halbert `main` @ `fbd725e9` (2026-09-11)

---

## 1. Packet

**LOG-01** — Structured redacted logging (JsonFormatter+RotatingFileHandler+RedactingFilter+LogRecordFactory).

## 2. User problem

Two live defects, one hub. (1) `halbert_core/halbert_core/dashboard/__main__.py:21-25` configures the root logger with `logging.basicConfig(format='{"ts": "%(asctime)s", ..., "msg": "%(message)s"}')` — JSON built by %-interpolation. Any `"`, `\` or newline in a user/tool message breaks the line into invalid JSON, and a tool string containing `", "level": "error` forges a record. The correct `JsonFormatter` already exists at `halbert_core/halbert_core/obs/logging.py:45` but the daemon never installs it — it only gets used where `get_logger()` (`obs/logging.py:59`) is called, and the root handler that `uvicorn.run(app, ...)` inherits still carries the broken basicConfig format. (2) There is no log file at all: `get_logger()` installs only a `StreamHandler` (`obs/logging.py:62`), so when the backend wedges or crashes, everything before the last terminal scrollback is gone — a founder running `make dev-restart` after a bad turn has no forensics, and the SUPPORT-BUNDLE unit (which tails this file) has nothing to read. A03-G9's residual: the MCP dispatcher and several hundred `logger.warning(f"...{value}...")` call sites emit raw exception text; the formatter pass (`_safe_redact`, obs/logging.py:30) redacts `msg` and the eight known structured keys, but nothing guards a record built with `extra={}` keys outside that list, and nothing stamps a correlation id so one turn's lines can be gathered out of an interleaved stream.

## 3. What to build

One commit sequence on the two target files (this packet absorbed OTHER-P2 — same hub, one merge; see FINAL-CRITICAL-DISCOVERY-BACKLOG §4 "LOG-01 + OTHER-P2").

In `halbert_core/halbert_core/obs/logging.py`:
1. `RedactingFilter(logging.Filter)`: `filter(record)` runs the existing `_safe_redact` over `record.getMessage()` and over every string value in `record.__dict__` beyond the `logging.LogRecord` standard attribute set (so arbitrary `extra={}` keys get the pass the formatter's fixed key list misses), then rewrites `record.msg = rendered` and `record.args = None` so a downstream plain formatter cannot re-interpolate unredacted args. Never raises — a filter exception must fall back to passing the record through, mirroring `_safe_redact`'s contract (losing the line is worse). The pass order stays registry-then-pattern exactly as `_redact_log_text` (obs/logging.py:9-27) already does it; do not add a second, weaker pass (the 2026-09-06 audit rule) and do not call `redact_error_text` — its 2000-char cap is for error surfaces, not log lines.
2. First-character pre-check inside the filter's hot path: lazily build a frozenset of the first characters of every registered registry variant (invalidate/rebuild when `len(get_global_registry())` changes; `SecretVariantRegistry.redact_text` already returns O(1) on an empty registry, so the pre-check only guards the pattern pass and the non-empty registry case). Early-return records whose rendered text contains no registered first character and no pattern-shaped marker.
3. `install_log_record_factory()`: wraps `logging.setLogRecordFactory` to stamp `record.trace_id` from `halbert_core/obs/tracing.py:16`'s existing `_current_trace_id` ContextVar (reuse it; do not mint a second context var) and `record.turn_id`/`record.thread_id` from a new module-level ContextVar pair here in obs/logging.py, exported as `set_turn_context(turn_id, thread_id)` / `clear_turn_context()`; `JsonFormatter.format()` gains `trace_id`, `turn_id`, `thread_id` to its structured-key tuple. Wire the set call at the one turn choke point: `agents/state_machine.py:1182` `self._enter_turn_scope(turn.turn_id)` already knows `turn.turn_id` and `turn.thread_id` (persisted at :1276) — set the context there and clear on scope exit. Compose with any pre-existing factory (call the old one, then stamp) so nothing else's factory is clobbered.
4. `install_file_handler(logger=None) -> RotatingFileHandler`: a `logging.handlers.RotatingFileHandler` at `log_subdir("dashboard")/halbert.log` (`utils/paths.py:88` creates the dir), `maxBytes=5_000_000`, `backupCount=3`, formatted with `JsonFormatter`, with the `RedactingFilter` attached. Return the handler so tests can introspect it.

In `halbert_core/halbert_core/dashboard/__main__.py`:
5. Replace the `logging.basicConfig(format='{"ts": ...}')` block (:21-25) with a `configure_root_logging()` call imported from `obs/logging`: installs `JsonFormatter` on the existing root `StreamHandler` (stdout stays — Tauri/launchd capture it), attaches `RedactingFilter` to the root logger (handlers inherit), calls `install_file_handler()` and `install_log_record_factory()`. Keep `logging.INFO`. Pass `log_config=None` implicitly (already default) and leave both `uvicorn.run` call sites (:188, :196) untouched — uvicorn's loggers propagate to root, so the fix covers them.

Tests: extend `halbert_core/tests/test_log_redaction.py` (R-05's file, already exercises JsonFormatter) with a new class of cases, plus a new `halbert_core/tests/test_obs_logging_install.py` — see field 10.

## 4. What NOT to build

- No support bundle, no log-tail reader, no byte-bounded partial-line dropper — the bundle (redacted zip: config + doctor JSON + log tail) is the SUPPORT-BUNDLE unit in the dispatch index (deps DIAG-01 + LOG-01); this packet only guarantees a parseable, rotated file exists for it to tail.
- No Logs page / cursor-based incremental tail UI (OC23-C16) — deferred per the deep-eval MVP line ("DEFER the Logs page, support bundle, and diagnostics-export variant to follow-on packets after DIAG-01 lands").
- No diagnostics-export redaction variant (OC04-M6) — merged into SUPPORT-BUNDLE per backlog §3.6 "one bundle, one redaction variant, one packet".
- No `QueueListener`/QueueHandler async logging — OTHER-P2's verifier dropped it; stderr + one rotating file handler, synchronous, is the whole design. No second file handler, no syslog, no network sink.
- No `get_subsystem_logger()` factory and no per-logger filters — the section file forbids it; every module keeps calling `logging.getLogger(__name__)` and the filter lives on the root handler only.
- No new redaction pass, no changes to `ingestion/redaction_registry.py`, `ingestion/redaction.py`, or `security/result_redaction.py` — this packet consumes R-05's registry; a second/weaker pass regresses the audit.
- Do not touch the other `logging.basicConfig` call sites (`mcp/server.py:1965`, `rag/*`, `tools/migrate_*`) — CLI one-shots, out of the daemon seam; and do not modify `Halbert/main.py`'s root handler (OTHER-P2's CLI half was noted but the merged packet's target files are the two named above; the CLI root is residual OTHER-P2 scope if a follow-up wants it).
- No control-character sanitizer — that is the text_hygiene primitive (dependency); if it has not landed, log lines pass through as today. Do not rebuild it here.
- No log rotation policy knobs in settings, no log-level UI, no retention/deletion of old logs (no-users rule: leave superseded data on disk, never delete).

## 5. Target files
- `halbert_core/halbert_core/obs/logging.py`
- `halbert_core/halbert_core/dashboard/__main__.py`

## 6. Dependencies

text_hygiene

## 7. Effort

**M** — M — half of it is already built. `JsonFormatter` exists and is tested (test_log_redaction.py, 6 tests); `_redact_log_text`/`_safe_redact` exist with the correct registry-first order; the ContextVar pattern exists in obs/tracing.py:16; `log_subdir()` exists at utils/paths.py:88. The residual is: one filter class (~40 lines), one factory installer + two ContextVars + setter/clearer (~30 lines), one RotatingFileHandler installer (~15 lines), the `configure_root_logging()` swap in `__main__.py` (~15 lines replacing a 5-line block), the `set_turn_context` call at the state_machine turn-scope seam (~4 lines), the first-char pre-check with invalidation (~20 lines), and the two test files. The M — not S — is for the seams that must not regress: composing `setLogRecordFactory` with any existing factory, keeping uvicorn's loggers flowing through the new root config in both reload and non-reload paths, the filter's rewrite of `msg`/`args` without breaking `record.getMessage()` for downstream handlers, and the failure-never-silences-the-line contract the audit hardened. Two files of product code plus tests, one hub, one merge — exactly the backlog's "one commit sequence, one reviewer, one merge."

## 8. UX rationale

Invisible by design — no surface changes, no new copy, so no colour/model-name/emoji exposure at all. What the founder experiences is the absence of two failure modes: (1) after a wedged turn or a crash followed by `make dev-restart`, there is now a rotated JSON log under the data dir's log subdir that answers "what happened before it died" instead of nothing — grounded in measured data, the system's own first-person account of itself; (2) the stderr stream Tauri and launchd capture stays intact and parseable — one JSON object per line, every line — instead of shattering on the first quoted tool argument. The correlation stamps mean "show me everything from that turn" is a grep on `turn_id`, which is what makes the later SUPPORT-BUNDLE's log tail and the future Logs page cheap: they read a clean, redacted, rotated file rather than reconstructing one. Secrets-handling posture the user never sees but benefits from: an acknowledged credential pasted into chat and echoed into a warning no longer lands on disk in the clear.

## 9. Acceptance criteria

1. `halbert_core/halbert_core/dashboard/__main__.py` no longer contains the `'{"ts": "%(asctime)s"...'` basicConfig format string; `configure_root_logging()` from `obs/logging` runs before any `logger.info` in `main()` and before `uvicorn.run`.
2. Starting the dashboard writes valid JSON lines (one object per line, `json.loads` succeeds on every line) to both stdout and `<log_dir>/dashboard/halbert.log`; the file is a `RotatingFileHandler` target with `maxBytes=5_000_000`, `backupCount=3`.
3. A log record whose message contains a registry-acknowledged secret (registered via `get_global_registry().register(...)`) emits the placeholder, not the value, on BOTH the stream handler and the file handler — including when the secret arrives via an arbitrary `extra={}` key outside JsonFormatter's fixed eight (this is the RedactingFilter, not the formatter, catching it).
4. The first-character pre-check is present: with an empty registry, records skip the registry alternation build (O(1) path preserved); the lazy first-char set invalidates when registry length changes (test registers a value, then logs a line whose only match is that value, and asserts redaction without rebuilding the alternation per record).
5. Records emitted inside a turn scope carry `trace_id`, `turn_id`, `thread_id` keys in the JSON payload; records outside any turn scope carry none of them (or nulls) and still format cleanly.
6. A redactor that raises does not drop the line (the R-05 contract, extended to the filter: record passes through).
7. All six pre-existing tests in test_log_redaction.py still pass unmodified.

## 10. Verification (measured state, not model judgment)

Measured, runnable:

A. New unit tests — `arch -arm64 .venv/bin/python -m pytest halbert_core/tests/test_log_redaction.py halbert_core/tests/test_obs_logging_install.py -x -q` (from the worktree: `arch -arm64 ./wt_pytest.py halbert_core/tests/test_obs_logging_install.py -x -q`). The new test file must assert: (a) every line emitted through a root handler configured by `configure_root_logging()` round-trips `json.loads` — feed a message containing `{"a": "b", "level": "error"}` and newline/quote/backslash payloads and assert parse + `level == "info"` (the forgery case from the basicConfig bug); (b) a `RotatingFileHandler` instance is attached to the root logger after install, with `maxBytes == 5_000_000` and `backupCount == 3`; (c) the extra-key redaction case (acceptance 3); (d) the factory composition case — install a sentinel factory first, then `install_log_record_factory()`, and assert both the sentinel's attribute and `trace_id` land on the record; (e) filter-never-raises case (acceptance 6); (f) `set_turn_context("t1","th1")` then a logged line yields `"turn_id": "t1"` in the parsed payload, and after `clear_turn_context()` it does not. All must exit 0.

B. Baseline diff — run `arch -arm64 ./wt_pytest.py halbert_core/tests -x -q --ignore=halbert_core/tests/test_cognition_tick_once.py 2>&1 | tail -5`; any failure not in the known-red baseline listed in PKT-log-01.md's Repo traps (test_agent_model_override.py, test_agent_model_selected_event.py, test_no_model_names_in_user_facing_source.py, test_num_ctx.py, ~23 failures) is attributable to this change. Exit code of the run must match the pre-change baseline run.

C. Live smoke (measured OS state) — `arch -arm64 .venv/bin/python -m halbert_core.dashboard --port 8123 --no-ollama-check &` then: (1) the path printed by `arch -arm64 .venv/bin/python -c "from halbert_core.utils.paths import log_subdir; print(log_subdir('dashboard'))"` contains `halbert.log` with nonzero size (`test -s`); (2) `head -1 <that file>` parses as JSON (`python -c "import json,sys; json.loads(sys.stdin.readline())"` exits 0); (3) `lsof -nP -iTCP:8123 -sTCP:LISTEN` shows the port bound; kill the process, restart on the same port, and confirm the same file grows (handler reattached, not duplicated — exactly one RotatingFileHandler on root: `python -c "import logging; print(sum(isinstance(h, logging.handlers.RotatingFileHandler) for h in logging.getLogger().handlers))"` inside a configure-then-check snippet prints 1 even when called twice, i.e. idempotent install).

## 11. Exclusions

Named exclusions and their destinations: (1) Support bundle (OC08-C7) and diagnostics-export redaction variant (OC04-M6) → SUPPORT-BUNDLE unit, already split out in the dispatch index (deps: DIAG-01 doctor JSON + this packet's log file); backlog §3.6 merged T5's OC09-C13 into that same unit — one bundle, one redaction variant. (2) Logs page with cursor-based incremental tail (OC23-C16) and the byte-bounded tail reader that drops corrupted partial lines → deferred per the deep-eval's MVP line; natural home is the follow-on packet after DIAG-01 lands (the tail reader is the bundle's and the page's shared reader — build it once, with SUPPORT-BUNDLE). (3) QueueListener/QueueHandler async logging → dropped per OTHER-P2's verifier (stderr + one file handler, synchronous, suffices). (4) `Halbert/main.py` CLI root handler half of OTHER-P2 → residual OTHER-P2 scope, not this packet (target files are the two named; the CLI entry is a separate root-handler seam). (5) The scattered CLI `logging.basicConfig` sites (mcp/server.py:1965, rag/*, tools/migrate_*) → not this packet; one-shot tools, not the daemon egress surface. (6) Control-character sanitization of log text → text_hygiene primitive (declared dependency, M0/M3 wave); consumed, never rebuilt here. (7) `set_turn_context` wiring beyond the single state_machine turn-scope seam (e.g. scheduler-submitted turns, MCP channel turns) → leave to CH-A's turn-cause axis work, which owns how non-agent-route turns identify themselves; this packet exports the API and wires the one choke point every turn already passes through.

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
