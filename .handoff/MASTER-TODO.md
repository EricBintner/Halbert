# Master TODO

Living task list. Items move here from session handoffs so nothing gets
lost between sessions. Strike through and date when done.

---

## Dead Code Cleanup (from Analyze button refactor, 2026-08-28)

- [ ] Remove `api.analyzeDiscoveries()` from `dashboard/frontend/src/lib/api.ts` — defined, never called from any frontend file after AIAnalysisPanel was rewired to `/api/agent/message`.
- [ ] Remove or deprecate `POST /api/discoveries/analyze/{analysis_type}` endpoint in `dashboard/routes/discovery.py` (lines ~434-476) and its helpers (`_call_llm_analysis`, `_build_analysis_context`, `_generate_fallback_analysis`). No frontend caller remains. Keep if other non-frontend consumers exist — verify first.
- [ ] Remove or wire the `context` field on `SendMessageRequest` in `dashboard/routes/agent.py` (line ~51). It is accepted by the Pydantic model but never read by `send_message()` or `process()`. Either remove it or thread it through to the agent as seeded context.

## GPU Page — Roll into Analyze tooling

The GPU page (`pages/GPU.tsx`) has its own "Deep Scan" button that calls
`POST /api/gpu/analyze` — a completely separate LLM path (raw Ollama
`/api/chat` with a hardcoded 120-line system prompt containing NVIDIA
driver/CUDA compatibility tables). This is the same pattern as the old
discovery analyze: bypasses being config, retrieval, intake, voice, and
thread persistence.

**What the GPU analyze does differently from the silo analyze:**
1. Gathers hardware context via `get_gpu_info()` + `get_deep_system_context()` (kernel, distro, display server, NVIDIA packages, ML frameworks)
2. Does a **web search** for latest driver info via `search_latest_driver_info()` (uses `WebSearch` — this is the "web grounding" part)
3. Feeds both into a hardcoded system prompt with driver/CUDA compatibility tables
4. Returns structured JSON (health_score, driver_assessment, cuda_assessment, recommendations)
5. Frontend renders structured driver/CUDA assessment cards, not just text

**Plan to roll in:**
- Route through `/api/agent/message` with `tier: "specialist"`, `scope: "host"` — same as the silo analyze.
- The GPU-specific context gathering (`get_gpu_info`, `get_deep_system_context`, `search_latest_driver_info`) should become **agent tools** the specialist model can call, rather than being pre-stuffed into a prompt. The agent already has a tool framework.
- The NVIDIA driver/CUDA compatibility knowledge should live in the knowledge base (SourcePrep), not in a hardcoded system prompt. The specialist model can retrieve it via the `host` or `knowledge_linux` scope.
- The structured UI (driver assessment cards, CUDA compatibility badges) can stay — the agent's response is markdown, and the frontend can parse structured sections out of it, or we emit module invocations (the module system from Phase 8 already supports this).
- **Cannot test on Mac** — GPU detection uses `nvidia-smi`, `lspci`, `/proc/driver/nvidia/`, all Linux-only. Implementation can be written but not verified until on a Linux machine with a GPU.

**Files involved:**
- `dashboard/routes/gpu.py` — `analyze_gpu_setup()`, `get_gpu_info()`, `get_deep_system_context()`, `search_latest_driver_info()`
- `dashboard/frontend/src/pages/GPU.tsx` — inline analysis UI (lines ~509-700+)
- `dashboard/frontend/src/components/AIAnalysisPanel.tsx` — the reusable panel to adopt

**Status:** Research complete. Implementation deferred (needs Linux + GPU to test).

## RAG Trending — Assessment (no action needed)

RAG trending (`rag/trending_discovery.py`) is a **GitHub repo discovery
feature**, not a system config analyzer. It:

1. Detects the user's tech stack (runtimes, package managers, tools, editors) via `TechStackDetector`
2. Fetches trending GitHub repos via the GitHub Search API, filtered by topics matching the user's stack
3. Scores repos by relevance to the user's stack (language match, topic overlap, stars, docs)
4. `analyze_repo_with_llm()` calls the LLM to classify a repo (category, is_alternative_to, key_features, maturity, learning_curve) — raw Ollama `/api/chat`, hardcoded prompt, returns structured JSON
5. The route `POST /api/rag/trending/{repo_name}/analyze` exposes this per-repo analysis

**This is a different domain from the Analyze button.** It's not analyzing
the user's system — it's analyzing external GitHub repos for relevance.
The "analyze" here means "classify this trending repo for the user," not
"diagnose this system silo."

**Recommendation:** Leave as-is for now. If we want to route it through
the agent later, it would be a different kind of analyze — "research this
repo" rather than "diagnose my system." The agent's web search tool and
retrieval could replace the hardcoded LLM call, but the value is lower
than the GPU page since this is a discovery/recommendation feature, not a
system health feature.

**Status:** Research complete. No action recommended.
