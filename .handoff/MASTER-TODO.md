# Master TODO

Living task list. Items move here from session handoffs so nothing gets
lost between sessions. Strike through and date when done.

---

## Dead Code Cleanup (from Analyze button refactor, 2026-08-28)

- [x] ~~Remove `api.analyzeDiscoveries()` from `dashboard/frontend/src/lib/api.ts`~~ — Done 2026-08-30.
- [x] ~~Remove `POST /api/discoveries/analyze/{analysis_type}` endpoint + helpers~~ — Done 2026-08-30. Also removed `AnalysisRequest` model.
- [x] ~~Remove `context` field on `SendMessageRequest`~~ — Done 2026-08-30. Verified never read by `send_message()` or frontend.

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

**Implementation plan:** `.handoff/GPU-DEEP-SCAN-REBUILD-PLAN-2026-08-29.md`
— 9 steps, 11 files (3 new, 8 modified). Code can be written and
unit-tested with mocks on Mac; integration testing requires Linux + GPU.

**Status:** Plan complete, ready for implementation.

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

## Tier 2 Recalibration (from security review, 2026-08-29)

Research and plan: `.handoff/TIER2-RECALIBRATION-2026-08-29.md`

Two modules were built that break Tier 2's architectural guarantee
that a secret value never leaves the tool during `describe_secret`:
`credential_validation.py` (sends secret to service API) and
`compromise_detection.py` (sends secret to HIBP/GitHub). Both are
opt-in (policy-based), but the research (AgentSecrets, AWS, Snowflake)
shows the guarantee must be architectural — no code path exists, not
just no code path enabled.

- [x] **Step 1: Remove the breach from describe_secret.** Done —
  removed CredentialValidationConfig and CompromiseCheckConfig from
  SecurityConfig. (commit 50d17e45)
- [x] **Step 2: Document as standalone human-run tools.** Done —
  fixed docstrings. Modules stay in config/ for now (see follow-up).
- [x] **Step 3: Enrich metadata-only describe_secret.** Done — added
  breach_risk (from format database) and last_changed (file mtime).
  Skipped rotation_status (last_changed covers same ground) and
  last_accessed (atime unreliable).
- [x] **Step 4: Architectural guarantee test.** Done — 7 tests mock
  all network calls, assert describe_secret triggers none. 333 total
  passing.
- [x] **Step 5: Update tests.** Done — no tests referenced the removed
  dataclasses. All existing tests pass.
- [x] **Follow-up: Move validation/compromise modules to CLI.** Done
  2026-08-30. Moved to `cli/` package with console_scripts entries
  (`halbert-check-credential`, `halbert-check-breach`). Updated test
  imports and pyproject.toml.

## Remaining Security Scope (from original review, not yet started)

These items from the security review are independent of the Tier 2
recalibration and can proceed in parallel:

- [x] **Settings UI security tab** — Done. Redesigned per the Daylight
  Mid-Century Modern design system spec
  (`SECURITY-TAB-VISUAL-DESIGN-AND-HANDOFF-2026-08-29.md`). Five new
  components in `SecurityComponents.tsx`: TrustBoundaryTelemetryBar
  (live tier counts), Tier1RockerControl (mechanical segmented switch),
  Tier2StateCard (dual-state vault), EscapeHatchConfirmationModal
  (high-friction phrase typing + TTL), MachinedTagInput (tag chips
  replacing textareas). Backend: fixed BeingConfigUpdate missing
  security field (saves were silently dropped), added
  /settings/security/telemetry endpoint, added TTL support
  (secret_tier_expiry + volatile_unlock with load-time auto-relock),
  fixed security:null crash, added list type validation, recursive
  telemetry walker. 264 tests pass, Vite build passes.
- [x] **Context assembler integration** — Done. The MCP
  `get_config_value` tool is already wired and tier-routed (Tier 2
  -> describe_secret, not raw value). The LLM calls it as a tool and
  gets tier-routed results. The assembler doesn't need a separate
  config source because the tool call path is separate from context
  assembly.
- [x] **Context-assembly backstop** — Done. Lines 334-351 in
  `assembler.py` call `detect_secure_content()` on assembled context
  and set `result.secure = True` when secrets are detected. Catches
  secrets from terminal watch, scanners, pastes.
- [ ] **Rebuild index unredacted (operational)** — Requires SourcePrep
  daemon (currently running on :8400, token generated at
  `~/.config/halbert/prep_token`). Run `register_host_project(redact=False)`
  to re-stage files with raw content, then `snapshot(manifest_path,
  redact=False)` to populate the canon DB with unredacted canonical JSON,
  then trigger a SourcePrep index rebuild via the API. Both egress paths
  (MCP boundary, secure routing) verified working 2026-08-29. Exclude
  globs still strip key material (*.key, *.pem, id_rsa*, etc.)
  regardless. **Deferred — user chose to skip for now.**

## Response Modality & Voice Path (from adversarial review, 2026-08-30)

Adversarial review of the modality handoff design docs (doc 11
interaction spec, doc 12 scrutiny, audio architecture doc 01).
Full findings: `documentation/design/13-adversarial-review-modality-handoff.md`

### Critical — Fix before any voice path goes live

- [ ] **Wyoming agent runs voice turns with `speaker_role="admin"` by default.**
  `wyoming_agent.py` calls `agent.process()` directly, bypassing the audio
  pipeline. `StateContext.speaker_role` defaults to `"admin"` (states.py
  L251), so every voice turn from a kitchen satellite gets admin-level tool
  access. Fix: pass `speaker_role="unknown"` (or HA-provided role) from
  `wyoming_agent.py` to `process()`.
- [ ] **No markdown-to-plaintext converter anywhere in the codebase.**
  `tts_engine.py` passes text directly to `self._tts.generate(text)` with
  zero preprocessing. Piper will speak `## headers` and ```` ``` ````.
  Need a `strip_markdown_for_speech()` utility before any voice path goes
  live. Also needed for `proactive_speak()` which sends raw markdown to
  HA's `tts.speak` service.
- [ ] **Wyoming `session_id` is hardcoded to PID.**
  `wyoming_agent.py` L130: `session_id=f"wyoming-{os.getpid()}"`. Concurrent
  satellite requests collide. Fix: mint UUID per turn, pass HA's
  `conversation_id` as `thread_id` (the param already exists on
  `process()` at state_machine.py L372 — it's just never passed).

### High — Architectural gaps blocking modality-aware responses

- [ ] **No modality signal reaches the prompt builder.**
  `build_response_prompt()` (agent_prompts.py L579) has no parameter for
  modality, intent, or response style. `process()` (state_machine.py L365)
  also has no modality parameter. Need: `modality` field on
  `StateContext`, parameter on `process()`, conditional branch in
  `build_response_prompt()`.
- [ ] **`<speech>` tags would need defanging like `<continuity>` tags.**
  The proposed dual-stream `<speech>...</speech>` delimiter would be
  forgeable from untrusted text (command output, log lines) unless the
  existing `_CONTINUITY_TAG_RE` defanging (agent_prompts.py L197) is
  extended to cover `<speech>` tags.
- [ ] **AEC is designed but `audio_capture.rs` doesn't exist.**
  `local_mic.py` docstring says Rust side applies AEC via
  webrtc-audio-processing, and `audio/config.py` has `aec_enabled: bool =
  True`, but the only Rust files are `lib.rs`, `main.rs`, `build.rs`. No
  `audio_capture.rs`, no AEC implementation. Without it, Halbert's own
  TTS output triggers VAD false barge-in (self-interruption loop).
- [ ] **Barge-in handler exists but is not wired.**
  `BargeInHandler` (audio/speech/barge_in.py) is fully implemented with
  token creation, local TTS cancellation, and satellite stop. But it's
  never instantiated or called by `AudioPipelineCoordinator`. The
  <120ms barge-in latency budget is unmeasurable.

### Medium — Should address during modality work

- [ ] **`proactive_speak()` sends raw markdown to HA TTS.**
  `wyoming_agent.py` L295 sends text directly to HA's `tts.speak` service
  with no markdown stripping. Same fix as the critical markdown stripper
  above — route through the same utility.
- [ ] **`UserPreferences.verbosity` is dead code.**
  `prompts/context.py` L225 defines `verbosity: str = "concise"` but it's
  never instantiated or consumed. The `output-format.xml` prompt component
  with context-sensitive length guidelines is also loaded but never sent
  to the model (`build_system_prompt()` is never called in production).
  Wire in or remove as part of modality work.
- [ ] **Two parallel Wyoming paths don't coordinate.**
  `integrations/wyoming_agent.py` (TCP JSONL, direct agent.process()) and
  `audio/ingress/wyoming_ingress.py` (feeds ring buffer, goes through
  VAD/ASR/speaker ID) serve different purposes but the architecture
  doesn't clarify when each is used or how they coordinate.

### Low — Documentation corrections

- [ ] **Doc 11 has factual errors vs codebase.** 5 of 8 frontend
  components don't exist (2 have wrong filenames). SSE
  `DualStreamMessageEvent` contract is incompatible with actual flat
  `StreamEvent` class. Modality routing matrix has zero implementation.
- [ ] **Doc 12 has 3 factual errors.** Claimed `process()` needs
  `thread_id` added (already exists). Claimed AEC should be Python-side
  (it's planned for Rust). Presented NSPanel keyboard trap as existing
  vulnerability (no floating panel code exists).
- [ ] **Audio architecture doc (01) has 4 discrepancies.** Still says
  "YAMNet" in diagrams when code explicitly says "NOT YAMNet, uses
  CED-tiny". Claims `coordinator.py` (actual: `pipeline.py`). Claims 3
  acoustic files that don't exist (`yamnet.py`, `taxonomy.py`,
  `anomaly_detector.py`).

## Frontend — Settings Monolith Modular Decomposition

The settings page (`dashboard/frontend/src/pages/Settings.tsx`) is currently a 3,273-line monolith (133 KB) containing 10 tabs inline.

- [ ] **Decompose `Settings.tsx` into modular tab components in `src/components/settings/tabs/`**:
  - `types.ts` — shared alert rule, system info, and discovery stats types
  - `SystemTab.tsx` — system info readouts, discovery cache, and system profile scan triggers
  - `KnowledgeTab.tsx` — document scrapers, staged embeddings, and ChromaDB collection stats
  - `SafetyTab.tsx` — trust boundary telemetry, Tier 1/2 rocker controls, and escape hatch modal
  - `VisionTab.tsx` — camera privacy gates, resolution, and OCR toggles
  - `AlertsTab.tsx` — systemd and disk alert rules table
  - `BeingTab.tsx` — persona and identity prompt editor
  - `AboutTab.tsx` — version badges, legal notices triggers, and developer tool viewer
  - `DebugTab.tsx` — raw log stream viewer and test error dispatchers
  - Refactor `Settings.tsx` to a thin ~120-line coordinator / NavRail shell.
