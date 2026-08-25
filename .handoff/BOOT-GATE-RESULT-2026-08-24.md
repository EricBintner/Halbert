# Boot-Gate Result — Mac Local Run

**Date:** 2026-08-24
**Target:** §1.2 (T4.5a.1 / T4.5b.1) of `REMAINING-WORK-2026-08-24.md`
**Host:** macOS (Darwin 25.5.0), local — NOT the Ubuntu deployment
**Command:** `python scripts/boot_smoke.py --base-url http://localhost:8000`

## Stack state at run
- uvicorn serving `halbert_core.halbert_core.dashboard.app:app` on 127.0.0.1:8000 (venv python 3.10, uvicorn 0.52.4)
- Local LLM backend: Ollama at localhost:11434, model `qwen3.8:27b-mlx` (the configured default path — no `models.yml` present, so model config fell back to defaults)
- No `~/.config/halbert/being.yml` present → being config used built-in defaults (`voice=first_person`)
- MLX not installed (benign — Ollama is the backend on this host)
- Non-fatal startup noise (expected on macOS, did not affect any check):
  - "Journald ingestion error: No such file or directory: 'journalctl'" (Linux-only collector)
  - "Config watcher not started (Linux hosts only)"

## Result: 5/5 PASS
```
PASS  server reachable / agent health — agent state=idle
PASS  agent send round-trip ('hi') — assistant response received (terminal=response_complete)
PASS  being config exposes voice — voice=first_person
PASS  module registry lists vitals — modules=['config-diff', 'vitals', 'drive-health', 'evidence']
PASS  intake routing (guide / specialist) — greeting->guide, troubleshooting flagged (specialist disabled; routed to 'guide')
5/5 checks passed
```

> **Updated 2026-08-24 (same day):** the smoke was extended from 4 to 5 checks. A new read-only `POST /api/agent/intake` endpoint (added to `dashboard/routes/agent.py`) exposes the intake pipeline's routing classification. Check 5 asserts greetings route to `guide` and a troubleshooting prompt routes to `specialist` when `specialist_enabled` is true (Ubuntu with `models.yml`); on a dev host without `models.yml` it instead asserts the message was still flagged `is_troubleshooting` (signal detection correct, model selection falls back to guide). This automates the manual intake-routing check the plan listed for §1.2.

## What this verifies / what it does NOT
- **Verifies:** the agent path serves a real assistant SSE response end-to-end (LLM round-trip via Ollama succeeded), being config exposes voice, module registry lists `vitals`. This is the repeatable automated portion of the boot gate.
- **Does NOT verify (still Ubuntu-only per plan):**
  - The no-ChromaDB chat fallback path.
  - Intake routing semantics — the plan asks to confirm "hi" routes to the **guide** and troubleshooting routes to a **specialist**. The smoke only confirms "hi" produced a response; it does not assert which sub-agent/model handled it.
- **Not yet closed:** §1.2 stays OPEN until the same gate runs against the Ubuntu deployment plus the two manual intake-routing checks above are recorded there. This Mac run is a partial confirmation, not full closure.

## Repro
```bash
.venv/bin/python -m uvicorn halbert_core.halbert_core.dashboard.app:app --host 127.0.0.1 --port 8000 --log-level warning
.venv/bin/python scripts/boot_smoke.py --base-url http://localhost:8000   # now 5 checks
```

## Notes for the Ubuntu run
- Re-run the identical `boot_smoke.py` command against `--base-url http://<ubuntu-host>:8000`.
- Add explicit intake-routing assertions (guide vs specialist) — the current smoke does not check classification, only round-trip.
- Verify the no-ChromaDB chat path explicitly (Mac run used the ChromaDB-initialized path).