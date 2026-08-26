# Opus Handoff — Remaining Work (Post Sovereign Host v2.0)

**Created:** 2026-08-25
**Model tier:** opus
**Effort levels:** high, xhigh, max
**Ignore:** All Linux-specific work (bwrap sandbox, Linux man pages, deb/rpm packaging, config watcher). This is a macOS dev machine.

**Reads with:**
- [FABLE-HANDOFF-REMAINING-WORK-2026-08-25.md](./FABLE-HANDOFF-REMAINING-WORK-2026-08-25.md) — fable track is doing the prep work (installing Haloysius, smoke-testing the CodeIndex, writing the halbert-api binary, wiring ModelBackend)
- [HANDOFF-RAG-ARCHITECTURE-REVIEW-2026-08-25.md](./HANDOFF-RAG-ARCHITECTURE-REVIEW-2026-08-25.md) — RAG architecture findings
- [HANDOFF-STAGED-CODEINDEX-BUILD-2026-08-25.md](./HANDOFF-STAGED-CODEINDEX-BUILD-2026-08-25.md) — CodeIndex build plan
- [STRATEGY-V2-SCRUTINY.md](../documentation/sovereign-host-vision/STRATEGY-V2-SCRUTINY.md) — what was built

> **STOP: Read [CODEINDEX-BUILD-LOCK.txt](./CODEINDEX-BUILD-LOCK.txt) before touching anything related to SourcePrep, embeddings, or CodeIndex.**
> A staged embedding build is IN PROGRESS (PID 66131, `staged_knowledge_embed.py --stage 2`). It has been restarted 3 times by AI sessions, wasting 26+ hours and only reaching 5%. DO NOT start any build, DO NOT call POST /build on the daemon, DO NOT restart the daemon, DO NOT kill the running process.

---

## Context

The sovereign host v2.0 plan is complete — all 25 tasks committed and pushed, 769 tests passing. But three systems have gaps that were discovered during post-implementation review. This handoff covers the **opus-level work** (harder, requires architectural decisions or long compute). The fable-level work is in a separate handoff.

**Test runner:** Always use `.venv/bin/python -m pytest`, NOT system `python3`.

**Dependency:** Tasks O1-O3 depend on the fable track completing F1 (install Haloysius) and F2 (CodeIndex smoke test). Check whether those are done before starting.

---

## Task O1: Full CodeIndex build — IN PROGRESS, DO NOT START

**Tier:** opus
**Effort:** xhigh (long compute, needs babysitting)
**Lines:** 0 (data build, not code)
**Status:** RUNNING NOW — `staged_knowledge_embed.py --stage 2` (PID 66131)

This build has been restarted 3 times by different AI sessions, wasting 26+ hours and only reaching 5% completion. Each restart loses all progress.

**DO NOT:**
- Run `staged_knowledge_embed.py` — it's already running
- Call `POST /projects/{id}/build` on the SourcePrep daemon — this starts a DUPLICATE build inside the daemon that competes with the staged script for the same index files
- Restart the SourcePrep daemon (PID 44108)
- Kill PID 66131 or PID 44108

**Read [CODEINDEX-BUILD-LOCK.txt](./CODEINDEX-BUILD-LOCK.txt) for full details.**

**To check progress (read-only, safe):**
```bash
ps -p 66131 -o pid,stat,%cpu,etime,command
curl -s "http://localhost:8400/projects/735a592e-a2da-499b-a614-854a5fc461f5/status"
```

**When the build is DONE** (process gone, `building=False`):
1. Verify the index has thousands of chunks (not 98):
   ```bash
   curl -s "http://localhost:8400/projects/735a592e-a2da-499b-a614-854a5fc461f5/status" \
     | python3 -c "import json,sys; d=json.load(sys.stdin)['data']; print('chunks:', d['index']['total_chunks'], 'source:', d['index']['source'])"
   ```
2. Run scoped queries (see acceptance queries below)
3. Remove `CODEINDEX-BUILD-LOCK.txt`
4. Proceed to O4 (retrieval quality validation)

**Acceptance queries (run after build completes):**
```bash
# Scoped query — should return macOS man page content
curl -s -X POST "http://localhost:8400/projects/735a592e-a2da-499b-a614-854a5fc461f5/context" \
  -H "Content-Type: application/json" \
  -d '{"query": "what does PermitRootLogin accept", "scope": "knowledge_macos", "structured": true}' \
  | python3 -c "import json,sys; d=json.load(sys.stdin); chunks=d.get('chunks',[]); print(f'chunks: {len(chunks)}'); [print(f'  {c[\"source_path\"]}: {c[\"text\"][:100]}...') for c in chunks[:3]]"

# Host-scoped query
curl -s -X POST "http://localhost:8400/projects/735a592e-a2da-499b-a614-854a5fc461f5/context" \
  -H "Content-Type: application/json" \
  -d '{"query": "my sshd config", "scope": "host", "structured": true}' \
  | python3 -c "import json,sys; d=json.load(sys.stdin); chunks=d.get('chunks',[]); print(f'chunks: {len(chunks)}'); [print(f'  {c[\"source_path\"]}: {c[\"text\"][:100]}...') for c in chunks[:3]]"
```

**Do NOT run stages 2 (linux) or 3 (bsd)** — Linux-specific work is deferred.
   ```bash
   SP=/Volumes/4TB-BAD/HumanAI/CoDRAG/.venv/bin/python
   cd /Volumes/4TB-BAD/Halbert
   $SP scripts/staged_knowledge_embed.py --stage 1
   ```
3. Monitor the build:
   - Watch files/min throughput
   - Check the ETA — if it's >12h, let it run overnight
   - If it errors, read the log, check if it's a transient failure (Ollama timeout, OOM) or a real bug
   - The script snapshots `documents.json`/`embeddings.npy`/`manifest.json`/`fts.sqlite3` before writing — if the build fails, restore from the snapshot
4. After stage 1 completes, verify:
   ```bash
   curl -s "http://localhost:8400/projects/735a592e-a2da-499b-a614-854a5fc461f5/status" \
     | python3 -c "import json,sys; d=json.load(sys.stdin)['data']; print('chunks:', d['index']['total_chunks'], 'source:', d['index']['source'])"
   ```
   `total_chunks` should be in the thousands (not 98). `source` should be `code` (not `knowledge`).
5. Run acceptance queries:
   ```bash
   # Scoped query — should return macOS man page content
   curl -s -X POST "http://localhost:8400/projects/735a592e-a2da-499b-a614-854a5fc461f5/context" \
     -H "Content-Type: application/json" \
     -d '{"query": "what does PermitRootLogin accept", "scope": "knowledge_macos", "structured": true}' \
     | python3 -c "import json,sys; d=json.load(sys.stdin); chunks=d.get('chunks',[]); print(f'chunks: {len(chunks)}'); [print(f'  {c[\"source_path\"]}: {c[\"text\"][:100]}...') for c in chunks[:3]]"

   # Host-scoped query
   curl -s -X POST "http://localhost:8400/projects/735a592e-a2da-499b-a614-854a5fc461f5/context" \
     -H "Content-Type: application/json" \
     -d '{"query": "my sshd config", "scope": "host", "structured": true}' \
     | python3 -c "import json,sys; d=json.load(sys.stdin); chunks=d.get('chunks',[]); print(f'chunks: {len(chunks)}'); [print(f'  {c[\"source_path\"]}: {c[\"text\"][:100]}...') for c in chunks[:3]]"
   ```
6. Verify scope filtering works — a `knowledge_macos` scoped query should NOT return Linux man pages, and vice versa.

**Commit:** None — this is a data build.

---

## Task O2: Tauri native build decision and execution

**Tier:** opus
**Effort:** xhigh
**Lines:** variable
**When:** After F3 (fable track writes the halbert-api binary)

**Problem:** The Tauri desktop shell is scaffolded but not built. The frontend is a working web app at `localhost:8000`, but there's no native macOS app bundle. The `tauri.conf.json` is configured, `lib.rs` has 6 Tauri commands, but `cargo tauri build` has never been run.

**Decision required:** Is Tauri worth it? The frontend already works as a web app. The Tauri commands in `lib.rs` (system_info, metrics, approvals) are dead — the frontend uses HTTP endpoints via `tauri.ts` instead. The only real value of Tauri is:
1. Native window with dock icon
2. System tray (`trayIcon` is configured)
3. Bundled distribution (`.app` for macOS)
4. The `externalBin` mechanism to auto-start the Python backend

**If the decision is YES, build Tauri:**
1. Verify the fable track's halbert-api binary works (F3 should be done)
2. Check Rust toolchain:
   ```bash
   rustc --version
   cargo --version
   rustup target list --installed
   ```
3. Install Tauri CLI if needed:
   ```bash
   cargo install tauri-cli --version "^2.0"
   ```
4. Try a dev build first:
   ```bash
   cd halbert_core/halbert_core/dashboard/frontend
   npm run build  # build the frontend
   cargo tauri dev  # launch in dev mode
   ```
   This will fail if there are Rust compilation errors. Fix them.
5. Check the `lib.rs` commands — are they actually used by the frontend? If not, consider removing them to simplify the build.
6. Once dev works, do a release build:
   ```bash
   cargo tauri build
   ```
   This produces a `.app` bundle in `target/release/bundle/macos/`.
7. Test the built app — does it launch? Does the Python backend start? Does the frontend connect?

**If the decision is NO, ship as web app:**
1. Remove the `src-tauri/` directory (or archive it)
2. Set up a LaunchAgent plist to auto-start the Python server on login
3. Document the web-app deployment path

**Do not:**
- Spend more than 4 hours on Tauri build issues — if it doesn't build cleanly, fall back to web app
- Modify the frontend to use Tauri IPC commands — the HTTP approach works fine
- Build for Linux targets — macOS only for now

**Commit:** Either `build(tauri): produce native macOS app bundle` or `chore: remove Tauri shell, commit to web-app deployment`

---

## Task O3: Deep investigation — end-to-end agent flow with Haloysius

**Tier:** opus
**Effort:** xhigh
**Lines:** 0 (investigation, then a report)
**When:** After F1 + F7 (fable track installs Haloysius and does initial cognition tick check)

**Problem:** The agent state machine, cognition wiring, and somatic blocks were all built without Haloysius installed. Now that Haloysius is installed (by fable F1), we need to verify the full end-to-end flow works:

1. User sends message → agent state machine starts
2. Intake pipeline routes to guide/specialist
3. Context assembler retrieves from SourcePrep (currently fallback — CodeIndex not built)
4. LLM call via tier router
5. Tool execution (if needed)
6. CRAG evaluation
7. **Cognition tick fires** (REFLECTING state → `advance_turn()` → thought generation → memory promotion)
8. Somatic block lifecycle (if triggered)
9. Response streamed via SSE
10. Conversation status updated

**Steps:**
1. Start the server with debug logging:
   ```bash
   cd /Volumes/4TB-BAD/Halbert
   .venv/bin/python -m halbert_core.dashboard.app 2>&1 | tee /tmp/halbert-server.log &
   ```
2. Send a test message and watch the full flow:
   ```bash
   curl -s -X POST http://localhost:8000/api/agent/message \
     -H "Content-Type: application/json" \
     -d '{"message": "check my disk health"}' | python3 -m json.tool
   ```
3. Read the server log. Trace the full flow:
   - Did intake pipeline fire? (look for "Intake pipeline wired")
   - Did the context assembler retrieve anything? (look for SourcePrep calls)
   - Did the tier router select a model? (look for model selection logs)
   - Did the LLM call succeed? (look for response chunks)
   - Did the cognition tick fire? (look for "cognition" or "advance_turn" in REFLECTING state)
   - Did any somatic blocks get created?
   - Did the conversation status reach SUCCESS?
4. If any step fails, investigate the root cause:
   - Is it a missing dependency?
   - Is it a configuration issue?
   - Is it a code bug?
5. Test with a more complex query that should trigger tool execution:
   ```bash
   curl -s -X POST http://localhost:8000/api/agent/message \
     -H "Content-Type: application/json" \
     -d '{"message": "what services are running on this host?"}'
   ```
6. Test with a query that should trigger approval flow:
   ```bash
   curl -s -X POST http://localhost:8000/api/agent/message \
     -H "Content-Type: application/json" \
     -d '{"message": "restart the ssh service"}'
   ```
7. **Write a report** covering:
   - Which steps in the flow work
   - Which steps fail and why
   - What needs to be fixed (with file references)
   - Whether the cognition tick produces useful output
   - Whether somatic blocks are created correctly
   - Whether the approval flow works end-to-end

**Do not:**
- Fix bugs during this investigation — just document them
- Test with destructive commands
- Leave the server running when done

**Commit:** None — investigation report. Post findings as a comment.

---

## Task O4: SourcePrep retrieval quality validation

**Tier:** opus
**Effort:** high
**Lines:** 0 (investigation)
**When:** After O1 (CodeIndex build complete)

**Problem:** The RAG architecture review identified that scope routing uses a keyword heuristic (`scope_for_query()` in `sourceprep_retrieval_backend.py`). This may not be accurate enough — "how do I configure SSH" doesn't mention "linux" or "macos", so it goes to the default platform scope, which might be wrong.

**Steps:**
1. After the CodeIndex build (O1) is complete, run a battery of test queries:
   ```python
   queries = [
       # Should route to knowledge_macos
       "how do I configure sshd on macos",
       "what does PermitRootLogin accept",
       "how to set up nfs on macos",
       "macos service management",
       
       # Should route to host
       "is my sshd using port 22",
       "what's currently configured on this host",
       "show me my firewall rules",
       
       # Ambiguous — should go to default platform (macos)
       "how does dns resolution work",
       "explain the Port directive",
       
       # Should be unscoped
       "tell me a joke",
       "what time is it",
   ]
   ```
2. For each query, call the retrieval backend and check:
   - Which scope was selected by `scope_for_query()`?
   - Were the right chunks returned?
   - Were the chunks from the right platform?
   - Was the content useful (raw man page content, not just summaries)?
3. Identify queries where the scope routing is wrong.
4. Propose improvements to the keyword heuristic (don't implement — just propose).

**Do not:**
- Implement a machine learning classifier — the keyword heuristic is fine for v1
- Modify `scope_for_query()` — just document what's wrong

**Commit:** None — investigation report.

---

## Task O5: Haloysius memory persistence verification

**Tier:** opus
**Effort:** high
**Lines:** 0 (investigation)
**When:** After F1 + O3

**Problem:** The cognition wiring connects `HaloysiusMemoryAdapter` to `PersonaMemoryStore` for thought promotion persistence. But this has never been tested with Haloysius actually installed. We need to verify that:
1. Thoughts generated by `advance_turn()` are persisted to the memory store
2. The memory store can be searched
3. Memories survive across sessions (process restarts)

**Steps:**
1. After O3 confirms the cognition tick fires, check if thoughts are being persisted:
   ```bash
   .venv/bin/python -c "
   from halbert_core.integrations.cognition_wiring import get_cognition, _create_memory_adapter
   adapter = _create_memory_adapter()
   if adapter:
       print('adapter created:', adapter)
       # Try searching for any stored memories
       results = adapter.store.search('halbert', k=5)
       print(f'stored memories: {len(results)}')
       for r in results:
           print(f'  {r}')
   else:
       print('adapter creation failed')
   "
   ```
2. If no memories are stored, the cognition tick may not be promoting thoughts. Check the `advance_turn()` call in `state_machine.py` — is `memory_store_add` being passed?
3. Send a few messages to the agent, then check the memory store again.
4. Restart the server and check if memories persist.
5. **Report:** Are thoughts being persisted? Do they survive restarts? If not, what's the gap?

**Do not:**
- Fix bugs — document them
- Modify the memory adapter or store

**Commit:** None — investigation report.

---

## Summary

| Task | Type | Est. time | Depends on |
|---|---|---|---|
| O1: Full CodeIndex build (macOS only) | Data build | 6-12h compute | F1, F2 |
| O2: Tauri native build decision | Code + build | 2-4h | F3 |
| O3: End-to-end agent flow investigation | Investigation | 2-3h | F1, F7 |
| O4: SourcePrep retrieval quality | Investigation | 1-2h | O1 |
| O5: Haloysius memory persistence | Investigation | 1-2h | F1, O3 |

**Total:** ~12-23 hours, dominated by the CodeIndex build compute time.

**Priority order:**
1. O1 (CodeIndex build) — start first, runs unattended
2. O3 (end-to-end flow) — while O1 builds, investigate the agent flow
3. O2 (Tauri) — can be done in parallel with O3
4. O4 (retrieval quality) — after O1 completes
5. O5 (memory persistence) — after O3 completes

**After completing all tasks:** Write a comprehensive report covering:
- CodeIndex build result (chunk count, build time, scope filtering works?)
- Tauri build decision (built or abandoned, why)
- End-to-end flow (which steps work, which fail, what needs fixing)
- Retrieval quality (is scope routing accurate enough?)
- Memory persistence (do thoughts survive restarts?)
- Prioritized list of bugs to fix
