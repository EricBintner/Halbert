# Remaining Work — Halbert Being Overhaul

> **⚠️ STALE — superseded 2026-08-24 by `FABLE-HANDOFF-2026-08-24.md`.**
> This doc was written *before* commit `682468f` ("fix: close remaining-work items...") landed. That commit **closed** §1.3 (in-doc chunking), §1.4 (vision routing), §2.1 (5 state-machine failures — fixed via `asyncio.run()`), §2.2 (`importorskip`), and the §3 UTC-morning-report watch item. Verified this session: `halbert_core/tests/` = **418 passed / 2 skipped / 0 failed** (deterministic ×2). The §3 marketing-ports watch item is also resolved (intentional, landed in `d93c12e`, `dev-restart.sh` depends on 5173).
>
> **Only four items below are still open:** §1.1 (chat.py retirement — fable-level), §1.2 (Ubuntu boot gate — blocked on Linux host; Mac run done, 5/5, see `BOOT-GATE-RESULT-2026-08-24.md`), §1.5 (drive-health SMART — blocked on Linux), §1.6 (SourcePrep scopes — blocked upstream). Read `FABLE-HANDOFF-2026-08-24.md` for the corrected, current picture. The body below is left unchanged for the record.

**Created:** 2026-08-24
**Context:** Follow-up to the full audit of `.handoff/IMPLEMENTATION-PLAN-2026-08-23.md` (74 tasks, Phases 0–8) and the fix pass that closed the found gaps. Everything committable from that pass landed in the same-day commits; this document is the leftover list — what is deliberately open, what is deferred, and what to watch.

**State at writing:** 381 passed / 7 failed in `halbert_core/tests/` (all 7 failures are the pre-existing items in §2 below), 95 passed in top-level `tests/`, frontend `tsc --noEmit` clean, all new modules import cleanly.

---

## 1. Deliberately deferred (plan-level decisions)

### 1.1 T4b.1 — chat.py retirement is not done
- `dashboard/routes/chat.py` remains fully registered (`app.py:175`); deprecation headers landed on the three conversation endpoints (`send_message`, `send_message_stream`, `config_chat`), but no endpoint has been removed and the file grew (3,914 → ~3,926 lines).
- **Why deferred:** the plan itself sequences retirement behind a verification period. Retiring endpoints before the frontend is confirmed fully on the agent path risks breaking conversation traffic.
- **To close:** (a) confirm no frontend code calls `/api/chat/*` (audit via browser network trace on a full UI walkthrough), (b) remove endpoints from the router one by one, (c) delete chat.py, (d) mark Phase 4 closed in the plan.

### 1.2 T4.5a.1 / T4.5b.1 — boot-test gate is formally OPEN
- The audit found no recorded evidence the gate ran before Phases 5–8 proceeded. The plan document now says so explicitly.
- **`scripts/boot_smoke.py`** (added in the fix pass) is the repeatable check — run it against a live stack on the Ubuntu host:
  ```
  python scripts/boot_smoke.py --base-url http://<host>:8000
  ```
  It verifies: server reachable, agent send produces an assistant response (SSE, 30s timeout), `/api/settings/being` returns voice config, `/api/modules` lists `vitals`.
- **To close:** run against the Ubuntu deployment, additionally verify the no-ChromaDB chat path and intake routing (guide for "hi", specialist for troubleshooting) per the plan's manual steps, and record the result in `.handoff/`.

### 1.3 T0d.1 — in-document chunking for oversized corpus docs (future work)
- 8 single-document markdown files exceed the 500KB split ceiling (largest: `macos_man_pages_52.md` at 1.55MB, `nvidia_cuda_docs_01.md` at 1.13MB). The doc-boundary splitter is correct by design; these are irreducible single docs, and SourcePrep's large-file truncation will clip them.
- **To close:** add content chunking to `rag/jsonl_to_markdown.py` for docs over the threshold.

### 1.4 Vision model routing (T4a.5, partial by plan design)
- Image attachments pass through the agent path to the LLM, but no explicit vision-model selection exists; the intake pipeline never returns `recommended_model="vision"` (plan marked it future).
- **To close:** add image detection to intake signals and a vision routing branch in `dashboard/routes/agent.py` model selection.

### 1.5 Drive-health module lacks SMART/temperature
- `GET /api/modules/drive-health/data` returns psutil partition usage only; the payload is self-describing (`telemetry_source: "psutil-partitions"`) so nothing lies about it, but SMART status/temperature needs a real smartctl layer (Linux host, likely sudo-wrapped).
- **To close:** on the Ubuntu host, add a `smartctl -a -j` collector with graceful degradation, and surface temperature/health fields in the payload.

### 1.6 T0a.1 — SourcePrep declarative project scopes (blocked upstream)
- The installed SourcePrep's project pointer file is intentionally minimal (`{id, mode, daemon}` only); `include_globs` and `scopes` are walker call parameters, not project config. Platform routing is realized via directory layout + caller-side scope args. The plan carries an as-built note.
- **To close:** only if SourcePrep adds declarative project scopes.

---

## 2. Pre-existing test failures (NOT regressions from the audit/fix work)

### 2.1 Order-dependent `TestStateTransitions` failures (5 tests)
- `test_state_machine.py::TestStateTransitions::{test_idle_to_planning_valid, test_idle_to_responding_invalid, test_planning_to_searching_valid, test_executing_to_awaiting_confirmation, test_state_history_recorded}` fail in a full-suite run but pass 28/28 when the file runs alone — cross-file test pollution.
- Observed BEFORE any of this session's changes. The fix pass did not touch the polluter (not identified yet).
- **To close:** bisect with `-p no:randomly`-style isolation (e.g. `pytest --forked` or running candidate upstream files incrementally) to find which earlier test mutates shared state — likely a module-global singleton (`get_event_bus`, `_scheduler_executor`, model client) leaking between files. Then isolate via fixtures.

### 2.2 `haloysius` package not installed in `.venv` (2 tests)
- `test_phase_d_integration.py::TestSystemEventMapper::{test_disk_failure_creates_worry, test_service_recovered_resolves_worry}` fail with `ModuleNotFoundError` from the lazy import in `integrations/system_event_mapper.py:315`.
- These tests only became visible once `pytest-asyncio` was installed in this pass — they env-failed silently before.
- **To close:** either `pip install` the sibling Haloysius package into `.venv` (it's a separate repo/checkout), or mark the tests with `pytest.importorskip("haloysius")` so a dev venv without it skips cleanly.

---

## 3. Watch items (minor, no action required now)

- **Morning report time is UTC.** `CronTrigger(**cron_expr, timezone='UTC')` in `scheduler/executor.py` means `being.yml`'s `morning_report.time` ("08:00") fires at 08:00 **UTC**, not host-local. Deliberate-looking and consistent with app.py's own log line, but if the user expects local time, add timezone resolution to the scheduling call in `dashboard/app.py`.
- **Scheduler slow-init race.** The delayed-start threads in `app.py` sleep ~3s/~4s; a slow scheduler init can silently skip proactive job registration until the next restart (logged at info level). If morning reports go missing after a boot, check that first.
- **`ProactiveEventBus` no-client behavior.** Events published before any SSE client connects (loop never attached) are retained in the ring buffer and replayed to the next subscriber's initial backlog — closed-loop redelivery now falls back inline with a log line. This is deliberate; just don't be surprised by the log.
- **Drift-skipped executions leave findings open.** A proposal whose every change is skipped for drift now lands APPLIED *without* resolving the finding — the next 6-hour detector sweep will re-surface it. That's honest, but recurring drift means recurring findings.
- **Marketing dev-server ports.** `marketing/web/vite.config.js` (5173) and `marketing/web-v2/vite.config.js` (5174) gained `server.port`/`host: true` during the session from outside the fix pass. Committed separately for visibility — revert those two hunks if they came from an abandoned experiment.

---

## 4. What the audit + fix pass verified as working (for the record)

- Phase 0 corpus: 28,869 docs / 56 JSONL files, zero empty docs, zero exact duplicates, zero backspace artifacts, unified schema across sources, manifest v2.0.0 totals match line counts exactly.
- Phase 1 intake: signals/budget/complexity/pipeline all meet acceptance cases at runtime; 99 intake tests green. (Implementation deviation documented: budget `conversation` bucket scaled to satisfy sum-to-total.)
- Phase 2: SourcePrep is the sole chat-path retrieval backend; `RAGServiceAdapter` deprecated but importable for eval; migration scripts exist with dry-run modes.
- Phase 3: intake runs pre-PLANNING, drives model selection and per-category context budgets; backward compat when intake is absent.
- Phase 5: findings/proposals stores, three detectors, precedence engine (additive-aware, sshd Include-aware), blast radius, propose → queue → approve → execute → rollback flow now reachable end-to-end from the dashboard approval API. Idempotent decisions; multi-change apply; drift-aware chmod.
- Phase 6: being config schema/API/UI, voice wired into prompts.
- Phase 7: event bus (thread-safe), SSE transport with heartbeat, gate with category overrides, snooze/dismiss actually work (event id or finding id), snooze expires and re-surfaces, morning report scheduled from being.yml and gated, 6-hour detector sweep scheduled, watcher callbacks wired at startup.
- Phase 8: provenance refs validated against real files; WhyChip renders and expands refs into modules; module registry lives in a neutral package (`halbert_core.modules`); `invoke_module` JSON stripped from displayed responses; module endpoints path-allowlisted (`/etc`, `~/.config`, host-config staging) and run off the event loop.

---

*Next session starting point: §1.2 (boot gate on Ubuntu) and §1.1 (chat.py retirement) are the two items that unblock "plan complete".*
