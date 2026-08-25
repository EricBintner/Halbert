# Fable-Level Handoff — Halbert Remaining Work

**Created:** 2026-08-24
**Author:** non-fable pass (this session)
**Supersedes the open-item list in:** `REMAINING-WORK-2026-08-24.md` (that doc is stale — see correction banner added to its top)

## TL;DR

Most of `REMAINING-WORK-2026-08-24.md` is **already closed** by commit `682468f` ("fix: close remaining-work items..."), which landed after that doc was written. After this session's non-fable pass, only **four items remain open**, and only **one (§1.1) is real fable-level implementation work**. The other three are blocked on external access (Linux host / upstream).

---

## Already closed — verified this session, NO action needed

| Item | Status | Evidence |
|------|--------|----------|
| §1.3 in-doc chunking for oversized docs | **CLOSED** | `chunk_large_doc()` in `rag/jsonl_to_markdown.py` splits at paragraph boundaries with "(continued, part N)" headings; `test_jsonl_to_markdown.py` covers it. Landed in `682468f`. |
| §1.4 vision model routing | **CLOSED** | Image detection in `intake/signals.py` (markdown/data-URI/HTML/extension regexes, `has_images`); vision branch in `dashboard/routes/agent.py:284` (`use_vision = bool(images) or intake_result.recommended_model == "vision"`). Landed in `682468f`. |
| §2.1 order-dependent `TestStateTransitions` (5 failures) | **CLOSED** | Fixed in `682468f` by replacing deprecated `asyncio.get_event_loop().run_until_complete()` with `asyncio.run()`. Verified: full `halbert_core/tests/` suite = **418 passed, 2 skipped, 0 failed**, deterministic across 2 runs. |
| §2.2 `haloysius` not installed (2 tests) | **CLOSED** | `pytest.importorskip("haloysius")` at `test_phase_d_integration.py:249,278`. Verified: `1 passed, 2 skipped`. Landed in `682468f`. |
| §3 watch — morning report UTC | **CLOSED** | Configurable timezone in `being.yml` (default `"local"` resolves via `/etc/localtime` on macOS, `/etc/timezone` on Linux), threaded through scheduler executor + cron triggers. Landed in `682468f`. |
| §3 watch — marketing dev-server ports | **NO ACTION** | `server.port`/`host:true` in `marketing/web/vite.config.js` (5173) and `marketing/web-v2/vite.config.js` (5174) landed in legit feature commit `d93c12e` (marketing-v3), and `scripts/dev-restart.sh` depends on 5173. Intentional, not an abandoned experiment. Keep. |
| §1.2 boot gate — Mac run | **DONE (partial)** | `scripts/boot_smoke.py` = **5/5 PASS** on local Mac (Ollama `qwen3.8:27b-mlx`). Recorded in `BOOT-GATE-RESULT-2026-08-24.md`. |

## Done this session (non-fable)

1. **`scripts/boot_smoke.py` extended 4→5 checks** — new `check_intake_routing` (check 5).
2. **New read-only `POST /api/agent/intake` endpoint** in `dashboard/routes/agent.py` — exposes intake routing classification (`recommended_model`, `complexity_score`, `is_greeting`, `is_troubleshooting`, `specialist_enabled`) without running the agent. Reuses the already-wired `agent.intake_pipeline`. This automates the plan's manual intake-routing check for both Mac and Ubuntu.
3. **§1.1 audit completed** — full caller map of `/api/chat/*` (see below). Retirement itself is fable-level and handed off here.

---

## STILL OPEN — handoff to fable

### §1.1 — chat.py retirement  *(the one real fable implementation item)*

**Why fable-level:** the dashboard has **two parallel chat surfaces**. Retirement is not a deletion — it requires deciding which surface ships and migrating/retiring the other, then a full browser-network-trace verification. This is the user's primary conversation surface; getting it wrong breaks conversation + memory traffic.

**Audit findings (done this session, do not re-run):**
- `dashboard/routes/chat.py` is still fully registered (`app.py:175`); the three conversation endpoints have deprecation headers but are **still called by live UI**:
  - `SidePanel.tsx` — `api.sendChatStream` (×2, lines 1160 & 1876), `api.sendConfigChat` (1136), `api.getModels` (339), `api.selectModel` (353), `api.getLoadedModels` (1001)
  - `ChatPanel.tsx` — `api.sendChat` (338)
  - `Memory.tsx` — calls `/api/chat/memory/{collections,entries,query,delete,clear}` directly (lines 53/70/85/106/125)
- The **new agent path UI exists in parallel**: `components/agent/AgentPanel.tsx` + `AgentChat.tsx` use `useAgentStream` → `/api/agent/message`. So the agent path is built and working; the legacy chat path just hasn't been retired.
- **SSE schema mismatch** (the migration's real work): `sendChatStream` parses `{token, done, full_response, reasoning, activity, error}`; the agent stream emits typed events `{response_chunk, response_complete, session_ended, error, cancelled}` (see `useAgentStream.ts:187+` and `boot_smoke.py` `TERMINAL_EVENTS`). Migrating `SidePanel` to the agent stream means rewriting its SSE parser or routing it through `useAgentStream`.
- **Memory endpoints live on the chat router** (`/api/chat/memory/*`), not on `dashboard/routes/memory.py`. Retirement requires moving them (or repointing `Memory.tsx` to a `/api/memory/*` equivalent) first.

**To close (fable):**
1. Product decision: is `AgentPanel`/`AgentChat` the shipping chat surface, or does `SidePanel` get migrated to the agent stream? (They currently coexist.)
2. If migrating `SidePanel`: rewrite its SSE handling to the agent event schema (or adopt `useAgentStream`), and repoint `getModels`/`selectModel`/`getLoadedModels` to a non-chat endpoint (or drop if the agent path doesn't expose model-picking).
3. Move `/api/chat/memory/*` off the chat router (to `memory.py` or an agent route) and repoint `Memory.tsx`.
4. `ChatPanel.tsx` `sendChat` → agent `send_message` or remove `ChatPanel` if superseded.
5. Confirm zero `/api/chat/*` callers remain via browser network trace on a full UI walkthrough (not just grep).
6. Remove the three deprecated endpoints from the router, delete `chat.py`, mark Phase 4 closed in the plan.

### §1.2 — boot gate on Ubuntu  *(blocked: Linux host not connected)*

- Mac run done (5/5, recorded in `BOOT-GATE-RESULT-2026-08-24.md`).
- Still needed on Ubuntu: run `scripts/boot_smoke.py --base-url http://<host>:8000` (now 5 checks; check 5 will assert full `specialist` routing where `models.yml` enables it), **plus** verify the **no-ChromaDB chat fallback path** (Mac run used the ChromaDB-initialized path — not covered).
- **To close:** connect the Ubuntu host, run the 5-check smoke, verify the no-ChromaDB path, record result in `.handoff/`, mark §1.2 closed.

### §1.5 — drive-health SMART/temperature  *(blocked: needs Linux host)*

- `GET /api/modules/drive-health/data` returns psutil partition usage only (`telemetry_source: "psutil-partitions"`); no SMART/temperature.
- **To close:** on the Ubuntu host, add a `smartctl -a -j` collector with graceful degradation (likely sudo-wrapped), surface temperature/health fields in the payload.

### §1.6 — SourcePrep declarative project scopes  *(blocked upstream)*

- Installed SourcePrep's project pointer is intentionally minimal (`{id, mode, daemon}`); globs/scopes are walker call parameters, not project config.
- **To close:** only if SourcePrep adds declarative project scopes. No action available now.

---

## Watch items still valid (no action)

- **Scheduler slow-init race** (`app.py` delayed-start threads sleep ~3s/~4s): a slow scheduler init can silently skip proactive job registration until next restart. If morning reports go missing after boot, check this first.
- **`ProactiveEventBus` no-client behavior:** events published before any SSE client connects are retained in the ring buffer and replayed to the next subscriber. Deliberate; don't be surprised by the log line.
- **Drift-skipped executions leave findings open:** a proposal whose every change is skipped for drift lands APPLIED *without* resolving the finding; the next 6-hour sweep re-surfaces it. Honest, but recurring drift = recurring findings.

---

## Uncommitted changes from this session (not committed — user to decide)

- `dashboard/routes/agent.py` — added `IntakeRequest` model + `POST /api/agent/intake` endpoint
- `scripts/boot_smoke.py` — added `check_intake_routing` (5th check) + `_post_json` helper
- `.handoff/BOOT-GATE-RESULT-2026-08-24.md` — updated to 5/5
- `.handoff/FABLE-HANDOFF-2026-08-24.md` — this file
- `.handoff/REMAINING-WORK-2026-08-24.md` — staleness correction banner added at top

*Next session starting point: §1.1 (chat.py retirement) is the only fable implementation item. §1.2/§1.5 unblock when the Linux host is connected; §1.6 unblocks upstream.*