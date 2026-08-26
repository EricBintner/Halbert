# Fable Handoff — Remaining Work (Post Sovereign Host v2.0)

**Created:** 2026-08-25
**Model tier:** fable
**Effort levels:** med
**Ignore:** All Linux-specific work (bwrap sandbox, Linux man pages, deb/rpm packaging, config watcher). This is a macOS dev machine.

**Reads with:**
- [HANDOFF-RAG-ARCHITECTURE-REVIEW-2026-08-25.md](./HANDOFF-RAG-ARCHITECTURE-REVIEW-2026-08-25.md) — RAG architecture findings
- [HANDOFF-STAGED-CODEINDEX-BUILD-2026-08-25.md](./HANDOFF-STAGED-CODEINDEX-BUILD-2026-08-25.md) — CodeIndex build plan
- [STRATEGY-V2-SCRUTINY.md](../documentation/sovereign-host-vision/STRATEGY-V2-SCRUTINY.md) — what was built

> **STOP: Read [CODEINDEX-BUILD-LOCK.txt](./CODEINDEX-BUILD-LOCK.txt) before touching anything related to SourcePrep, embeddings, or CodeIndex.**
> A staged embedding build is IN PROGRESS. It has been restarted 3 times by AI sessions, wasting 26+ hours. DO NOT start any build, DO NOT call POST /build on the daemon, DO NOT restart the daemon. The running process (staged_knowledge_embed.py --stage 2, PID 66131) must be left alone.

---

## Context

The sovereign host v2.0 plan is complete — all 25 tasks committed and pushed, 769 tests passing. But three systems have gaps that were discovered during the post-implementation review. This handoff covers the **fable-level work** (well-defined, low-risk, no architectural decisions). The opus-level work is in a separate handoff.

**Test runner:** Always use `.venv/bin/python -m pytest`, NOT system `python3`. The venv has pytest-asyncio installed; system python does not.

---

## Task F1: Install Haloysius into Halbert's venv

**Effort:** med
**Lines:** 0
**When:** FIRST

**Problem:** Haloysius is a separate repo at `/Volumes/4TB-BAD/Haloysius` with 369 passing tests. Halbert's integration code (`integrations/cognition_wiring.py`, `app_seam.py`, etc.) imports from `haloysius.*` with lazy try/except. But `haloysius` is not installed in Halbert's `.venv`. Every import silently fails, so the persona cognition layer is dead code.

**Steps:**
1. Install Haloysius as an editable package:
   ```bash
   cd /Volumes/4TB-BAD/Haloysius
   /Volumes/4TB-BAD/Halbert/.venv/bin/pip install -e .
   ```
2. Verify the import works:
   ```bash
   /Volumes/4TB-BAD/Halbert/.venv/bin/python -c "import haloysius; print('OK:', haloysius.__file__)"
   ```
3. Run the 2 previously-skipped tests:
   ```bash
   cd /Volumes/4TB-BAD/Halbert
   .venv/bin/python -m pytest halbert_core/tests/test_phase_d_integration.py -q -rs
   ```
   These are the `haloysius` cognitive A/B tests at lines 249 and 278. They should now run instead of skipping.
4. Run the full test suite to verify nothing broke:
   ```bash
   .venv/bin/python -m pytest halbert_core/tests/ -q
   ```
   Must still be 769+ passed, 0 failed (the 2 previously skipped should now pass or fail — if they fail, report it but don't fix).
5. Verify the cognition wiring actually connects:
   ```bash
   .venv/bin/python -c "
   from halbert_core.integrations.cognition_wiring import get_cognition_tick, get_cognition
   tick = get_cognition_tick()
   cog = get_cognition()
   print('cognition:', cog)
   print('tick:', tick)
   print('persona_id:', cog.persona_id if cog else 'None')
   "
   ```

**Do not:**
- Modify any Haloysius source code
- Modify any Halbert integration code — just install and verify
- Install Haloysius into system Python — only the `.venv`

**Commit:** None needed — this is an environment change, not a code change. But add `haloysius` to `halbert_core/pyproject.toml` dependencies if it's not already there (check first — it might be in optional-dependencies).

---

## Task F2: CodeIndex smoke test — ALREADY DONE, DO NOT RE-RUN

**Status:** COMPLETE. Smoke test ran successfully (20 files, 4150 chunks, all reused from KnowledgeIndex).
A full staged build (`staged_knowledge_embed.py --stage 2`, PID 66131) is NOW RUNNING and has been repeatedly killed and restarted by AI sessions, wasting 26+ hours.

**DO NOT:**
- Run `staged_knowledge_embed.py` — it's already running
- Call `POST /projects/{id}/build` on the SourcePrep daemon — this starts a DUPLICATE build that competes with the staged script
- Restart the SourcePrep daemon
- Kill PID 66131 or PID 44108

**Read [CODEINDEX-BUILD-LOCK.txt](./CODEINDEX-BUILD-LOCK.txt) for full details.**

To check progress (read-only, safe):
```bash
ps -p 66131 -o pid,stat,%cpu,etime,command
curl -s "http://localhost:8400/projects/735a592e-a2da-499b-a614-854a5fc461f5/status"
```

When the build finishes (process gone, `building=False`), verify the index has thousands of chunks and run scoped queries. Until then, hands off.
**When:** After F1

**Problem:** The SourcePrep CodeIndex for the standalone halbert project has only 98 chunks (KnowledgeIndex fallback — LLM summaries, not raw content). 245 knowledge markdown files (87MB) are staged but not embedded. The staged embed script exists but has never been run.

**This task is ONLY the smoke test** — embed `knowledge/common` (5M, ~20 files) to verify the pipeline works and measure throughput. The full build is opus-level work (24h compute).

**Steps:**
1. Verify SourcePrep daemon is running:
   ```bash
   curl -s http://localhost:8400/health
   # Expect: {"status":"ok","version":"0.1.0"}
   ```
2. Run the smoke test:
   ```bash
   SP=/Volumes/4TB-BAD/HumanAI/CoDRAG/.venv/bin/python
   cd /Volumes/4TB-BAD/Halbert
   $SP scripts/staged_knowledge_embed.py --paths knowledge/common --yes-i-know-its-not-staged
   ```
3. Watch the output for:
   - Files per minute throughput
   - ETA for the full corpus
   - Any errors
4. After it completes, verify the index:
   ```bash
   curl -s "http://localhost:8400/projects/735a592e-a2da-499b-a614-854a5fc461f5/status" \
     | python3 -c "import json,sys; d=json.load(sys.stdin)['data']; print('chunks:', d['index']['total_chunks'], 'source:', d['index']['source'])"
   ```
   `total_chunks` should be > 98 (the fallback count). `source` should still be `knowledge` or change to `code`.
5. Test a scoped query:
   ```bash
   curl -s -X POST "http://localhost:8400/projects/735a592e-a2da-499b-a614-854a5fc461f5/context" \
     -H "Content-Type: application/json" \
     -d '{"query": "what does PermitRootLogin accept", "scope": "knowledge_common", "structured": true}' \
     | python3 -c "import json,sys; d=json.load(sys.stdin); chunks=d.get('chunks',[]); print(f'chunks returned: {len(chunks)}'); [print(f'  source: {c.get(\"source_path\",\"?\")}, score: {c.get(\"score\",0):.3f}') for c in chunks[:3]]"
   ```
6. **Report the throughput and ETA** in a comment. This determines whether the full build is feasible.

**Do not:**
- Run stage 1, 2, or 3 — that's opus-level work
- Modify the staged_knowledge_embed.py script
- Restart the SourcePrep daemon

**Commit:** None — this is a data build, not code.

---

## Task F3: Write real halbert-api binary for Tauri

**Effort:** med
**Lines:** ~30
**When:** After F1

**Problem:** The Tauri config (`src-tauri/tauri.conf.json`) specifies `externalBin: ["binaries/halbert-api"]`. The only binary file is `binaries/halbert-api-x86_64-unknown-linux-gnu` which is a 12-byte empty bash stub (`#!/bin/bash\n`). There's no macOS binary. Tauri requires a binary for each target platform.

**Steps:**
1. Write a shell script that starts the Halbert FastAPI server:
   ```bash
   #!/bin/bash
   # halbert-api — starts the Halbert dashboard backend for the Tauri shell.
   # Tauri launches this as an external process; the frontend connects to it.
   set -euo pipefail
   
   # Find the venv python (prefer .venv at repo root, fall back to system)
   REPO_ROOT="$(cd "$(dirname "$0")/../../../../.." && pwd)"
   PYTHON="$REPO_ROOT/.venv/bin/python"
   if [ ! -x "$PYTHON" ]; then
       PYTHON="$(command -v python3)"
   fi
   
   # Default port (Tauri frontend expects this)
   export HALBERT_PORT="${HALBERT_PORT:-8000}"
   
   exec "$PYTHON" -m halbert_core.dashboard.app
   ```
2. Save it as `binaries/halbert-api-aarch64-apple-darwin` (macOS arm64 target — this is an M-series Mac)
3. Also save a copy as `binaries/halbert-api-x86_64-apple-darwin` (Intel Mac fallback — same content)
4. Update the existing `binaries/halbert-api-x86_64-unknown-linux-gnu` with the same script (but with `python3` instead of venv path, since Linux deployment won't have the same venv path)
5. Make all three executable: `chmod +x binaries/halbert-api-*`
6. Verify the macOS one runs:
   ```bash
   ./binaries/halbert-api-aarch64-apple-darwin &
   sleep 3
   curl -s http://localhost:8000/api/agent/health
   kill %1
   ```

**Do not:**
- Try to run `cargo tauri build` — that's opus-level work
- Modify `tauri.conf.json` — it's already configured correctly
- Add a systemd/LaunchAgent plist — that's a deployment decision for later

**Commit:** `feat(tauri): add real halbert-api binary for macOS and Linux targets`

---

## Task F4: Wire HalbertModelBackend to tier_router

**Effort:** med
**Lines:** ~40
**When:** After F1

**Problem:** `integrations/app_seam.py:HalbertModelBackend` is a placeholder. Its `chat()` method makes a raw Ollama HTTP call, bypassing Halbert's tier router (`model/tier_router.py`). Its `raw_provider()` returns `None`. The docstring says "the actual LLM routing will be wired here once the LLMClientAdapter circular dependency is resolved (Phase C)."

The tier router is now complete (including the MetaHarnessRouter from C2a/C2b). The circular dependency may no longer exist.

**Steps:**
1. Read `model/tier_router.py` to find the `generate()` method signature and how to call it.
2. Read `integrations/app_seam.py:HalbertModelBackend` to see the current placeholder.
3. Check if there's still a circular import issue:
   ```bash
   .venv/bin/python -c "from halbert_core.integrations.app_seam import HalbertModelBackend; from halbert_core.model.tier_router import TierRouter; print('no circular import')"
   ```
4. If no circular import, update `HalbertModelBackend.chat()` to delegate to the tier router:
   - Import `TierRouter` lazily inside `chat()` (not at module level — avoids import order issues)
   - Call `tier_router.generate(messages=messages, ...)` 
   - If the tier router is unavailable, fall back to the existing raw Ollama call
5. Update `raw_provider()` to return the tier router's underlying provider if available.
6. Run tests:
   ```bash
   .venv/bin/python -m pytest halbert_core/tests/ -q
   ```

**Do not:**
- Break the existing fallback Ollama call — keep it as a safety net
- Import TierRouter at module level — use lazy import inside the method
- Change the ModelBackend protocol interface

**Commit:** `feat(integrations): wire HalbertModelBackend to tier_router instead of raw Ollama`

---

## Task F5: Verify boot smoke passes

**Effort:** med
**Lines:** 0
**When:** After F1, F3

**Problem:** The boot smoke script (`scripts/boot_smoke.py`) reports 0/5 checks passing because the server isn't running. After F1 (Haloysius installed) and F3 (halbert-api binary), the server should start cleanly.

**Steps:**
1. Start the server:
   ```bash
   cd /Volumes/4TB-BAD/Halbert
   .venv/bin/python -m halbert_core.dashboard.app &
   SERVER_PID=$!
   sleep 5
   ```
2. Run the boot smoke:
   ```bash
   python3 scripts/boot_smoke.py
   ```
3. Check the output — which checks pass, which fail?
4. If any fail, read the server logs to understand why.
5. Kill the server: `kill $SERVER_PID`
6. **Report the results** — which checks pass, which fail, and what the failures mean.

**Do not:**
- Fix server bugs — just report them. Fixes are opus-level.
- Modify the boot smoke script
- Leave the server running

**Commit:** None — this is verification, not code change.

---

## Task F6: Investigate the dead format_context path

**Effort:** med
**Lines:** 0 (investigation only)
**When:** After F1

**Problem:** `SourcePrepRetrievalBackend.format_context(max_chars=1500)` exists but has zero callers in Halbert. The RAG architecture review says "format_context(max_chars=1500) is a dead path (no callers in Halbert)." But it's part of the Haloysius `RetrievalBackend` protocol — Haloysius's cognitive core might call it.

**Steps:**
1. Search for all callers of `format_context`:
   ```bash
   cd /Volumes/4TB-BAD/Halbert
   grep -rn "format_context" halbert_core/ --include="*.py" | grep -v __pycache__
   ```
2. Search in Haloysius:
   ```bash
   cd /Volumes/4TB-BAD/Haloysius
   grep -rn "format_context" src/ --include="*.py" | grep -v __pycache__
   ```
3. Determine: does Haloysius's cognitive core call `format_context()` on the retrieval backend? If yes, it's NOT dead — it's called when Haloysius is installed and active. If no callers anywhere, it's truly dead.
4. If it IS called by Haloysius, check whether `max_chars=1500` is too small for man page content (the RAG review says it is). Report the finding.
5. If it is truly dead (no callers anywhere), report that it can be safely removed.

**Do not:**
- Delete anything — this is investigation only
- Modify format_context — just report

**Commit:** None — investigation only. Report findings in a comment.

---

## Task F7: Check if cognition tick actually fires

**Effort:** med
**Lines:** 0 (investigation only)
**When:** After F1

**Problem:** The state machine calls `cognition_tick` in the REFLECTING state (line 883 of `state_machine.py`). But since Haloysius was never installed, this has never actually run. After F1 installs Haloysius, we need to verify the tick fires.

**Steps:**
1. After F1 is done, start the server:
   ```bash
   .venv/bin/python -m halbert_core.dashboard.app &
   sleep 5
   ```
2. Send a message to the agent:
   ```bash
   curl -s -X POST http://localhost:8000/api/agent/message \
     -H "Content-Type: application/json" \
     -d '{"message": "hello, what can you do?"}'
   ```
3. Watch the server logs for:
   - "Cognitive tick and event mapper wired" (from `agent.py:148`)
   - "Created PersonaCognition for halbert" (from `cognition_wiring.py:28`)
   - Any errors from the cognition tick
4. Check if the REFLECTING state is reached and the tick is called. Look for log lines containing "cognition" or "reflection".
5. **Report:** Does the cognition tick fire? Does it produce any errors? Does it affect the response?

**Do not:**
- Fix bugs — just report
- Leave the server running

**Commit:** None — investigation only.

---

## Summary

| Task | Type | Est. time |
|---|---|---|
| F1: Install Haloysius | Environment | 5 min |
| F2: CodeIndex smoke test | Data build | 10-30 min |
| F3: halbert-api binary | Code | 15 min |
| F4: Wire ModelBackend | Code | 30 min |
| F5: Boot smoke | Verification | 10 min |
| F6: format_context investigation | Investigation | 10 min |
| F7: Cognition tick investigation | Investigation | 15 min |

**Total:** ~2 hours of fable work. All well-defined, no architectural decisions.

**After completing all tasks:** Post a summary comment with:
- Haloysius install result (did the 2 skipped tests pass?)
- CodeIndex smoke test throughput and ETA for full build
- Boot smoke results (how many of 5 checks pass?)
- format_context investigation result (dead or alive?)
- Cognition tick investigation result (fires or errors?)
- Any bugs discovered
