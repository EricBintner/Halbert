# GPU Deep Scan Rebuild — Implementation Plan

**Date:** 2026-08-29
**Status:** Ready for implementation. Cannot test on Mac (all GPU detection is Linux-only). Code can be written and unit-tested with mocks; integration testing requires a Linux machine with an NVIDIA GPU.
**Depends on:** Analyze button refactor (completed, commit `f63c2bc2`)

---

## Goal

Replace the GPU page's "Deep Scan" AI analysis (raw Ollama `/api/chat` with a 120-line hardcoded system prompt) with the same agent-driven pattern used by the Analyze button refactor. The specialist model gets GPU-specific tools, retrieves driver/CUDA compatibility from the knowledge base instead of a hardcoded table, and emits a structured module invocation for the frontend to render.

The live monitoring UI (GPU cards, live stats, role selector, quick links) stays untouched.

---

## Architecture

```
User clicks "Deep Scan"
    |
    v
AIAnalysisPanel (or GPU-specific variant)
    |  POST /api/agent/message
    |  { message: "Analyze my GPU setup...", tier: "specialist", scope: "host" }
    v
AgentStateMachine.process()
    |
    +-- PLANNING: specialist model decides which tools to call
    |       |-- gpu_info tool        -> get_gpu_info() (lspci, nvidia-smi)
    |       |-- gpu_system_context   -> get_deep_system_context() (kernel, distro, packages)
    |       |-- web_search           -> search_latest_driver_info() (existing web_search tool)
    |       |-- (retrieval)          -> SourcePrep host scope: driver/CUDA compatibility docs
    |
    +-- RESPONDING: specialist model synthesizes analysis
    |       |-- Emits markdown analysis (streamed via response_chunk SSE)
    |       |-- Emits {"action": "invoke_module", "module": "gpu-assessment", "props": {...}}
    |
    v
Frontend:
    |-- response_chunk events -> streamed markdown in AIAnalysisPanel
    |-- module_invoke event   -> GpuAssessmentModule renders structured cards
```

Key differences from the old Deep Scan:
1. **No hardcoded compatibility table.** The specialist model retrieves driver/CUDA compatibility from the knowledge base (SourcePrep `host` scope). The knowledge base content is maintained as documents, not code.
2. **Tools, not pre-stuffed context.** The GPU context-gathering functions become agent tools the model calls on demand. The model decides what to gather based on what it finds.
3. **Same Halbert voice.** Being config, intake, retrieval, CRAG, thread persistence all apply.
4. **Structured UI via module invocation.** The model emits a `gpu-assessment` module invocation with structured props; the frontend renders it as driver/CUDA assessment cards.

---

## Step-by-step

### Step 1: Create GPU agent tools (`tools/gpu_tools.py`)

New file: `halbert_core/halbert_core/tools/gpu_tools.py`

Move the GPU context-gathering functions out of `dashboard/routes/gpu.py` into tool handlers. The existing functions (`get_gpu_info`, `get_deep_system_context`, `search_latest_driver_info`) become tool handlers. The route file keeps its HTTP endpoints (`/api/gpu/info`, `/api/gpu/role/{pci_id}`, etc.) but imports the shared functions from `tools/gpu_tools.py`.

**Tools to register:**

| Tool name | Handler | Description |
|-----------|---------|-------------|
| `gpu_info` | `_gpu_info_handler` | Detect GPU hardware, driver, VRAM, CUDA version, live stats (temp, power, utilization). Returns structured JSON as a string. |
| `gpu_system_context` | `_gpu_system_context_handler` | Gather deep system context: kernel, distro, display server, secure boot, NVIDIA packages, CUDA paths, ML frameworks, container runtime. |
| `gpu_architecture` | `_gpu_architecture_handler` | Determine GPU architecture (Ampere, Ada Lovelace, Hopper, etc.) from model name. Lightweight — just the `get_gpu_architecture()` function. |

**Note on `search_latest_driver_info`:** Do NOT create a separate GPU web search tool. The agent already has a `web_search` tool (registered in `executor.py:108-130`). The specialist model can use it to search for "NVIDIA Linux driver latest version 2026" etc. The old `search_latest_driver_info()` function with its naive regex version parsing is replaced by the model's ability to read and interpret search results.

**Pattern to follow:** Same as `tools/system_info.py` — module-level async handler functions, `GPU_TOOL_SCHEMAS` dict, `GPU_TOOL_HANDLERS` dict, `register_gpu_tools(tool_executor)` function.

**Schema example:**
```python
GPU_TOOL_SCHEMAS = {
    "gpu_info": {
        "name": "gpu_info",
        "description": "Detect GPU hardware, driver version, VRAM, CUDA version, and live statistics (temperature, power, utilization). Linux-only — uses lspci and nvidia-smi.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    "gpu_system_context": {
        "name": "gpu_system_context",
        "description": "Gather deep system context for GPU analysis: kernel version, distro, display server (X11/Wayland), secure boot status, installed NVIDIA packages, CUDA toolkit paths, ML frameworks (PyTorch/TensorFlow), container runtime. Linux-only.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
}
```

**Handler example:**
```python
async def _gpu_info_handler(args: Dict) -> str:
    """Get GPU hardware and driver information."""
    import json
    info = get_gpu_info()  # shared function, moved from gpu.py
    return json.dumps(info, indent=2, default=str)
```

**Refactor `dashboard/routes/gpu.py`:**
- Move `get_gpu_info()`, `get_deep_system_context()`, `get_gpu_architecture()`, `run_command()`, `get_gpu_role()`, `set_gpu_role()` into `tools/gpu_tools.py` (or a shared `tools/gpu_helpers.py` that both the tools and the route import).
- `gpu.py` imports them: `from ...tools.gpu_helpers import get_gpu_info, get_deep_system_context, ...`
- The `/api/gpu/info`, `/api/gpu/role/{pci_id}`, `/api/gpu/deep-context` endpoints still work — they just call the shared functions.
- The `/api/gpu/analyze` endpoint and `search_latest_driver_info()` are removed (dead code after the rebuild).
- The `/api/gpu/analysis-cache` endpoint and `save_gpu_analysis()`/`load_gpu_analysis()` are removed — the agent persists the turn as a thread, so a separate YAML cache is redundant. The frontend can show "last analyzed" from the thread timestamp if needed.

### Step 2: Register GPU tools in the agent (`dashboard/routes/agent.py`)

In `get_agent()`, after the existing tool registrations (line ~229), add:

```python
# GPU tools — only register on Linux (detection uses lspci, nvidia-smi)
import platform
if platform.system() == "Linux":
    try:
        from ...tools.gpu_tools import register_gpu_tools
        register_gpu_tools(tool_executor)
    except Exception as e:
        logger.warning(f"Could not register GPU tools (non-fatal): {e}")
```

The Linux guard prevents the model from being offered GPU tools on macOS where they'd return empty results. On macOS, the GPU page still shows the monitoring UI (which uses the `/api/gpu/info` endpoint directly), but the "Deep Scan" button is hidden or disabled.

### Step 3: Register `gpu-assessment` module (`modules/registry.py`)

Add a new module to the registry:

```python
self.register(ModuleDef(
    name="gpu-assessment",
    component="GpuAssessmentModule",
    data_fetcher="/api/modules/gpu-assessment/data",
    prop_contract={
        "health_score": "integer",
        "current_status": "string",
        "driver_assessment": "object?",
        "cuda_assessment": "object?",
        "ml_compatibility": "object?",
        "warnings": "array?",
        "recommendations": "array?",
        "known_compatible_combos": "array?",
    },
    standalone_route="/modules/gpu-assessment",
    icon="Cpu",
    description="GPU driver and CUDA compatibility assessment cards",
))
```

The module's `data_fetcher` endpoint is optional — the props arrive via the `module_invoke` SSE event, so the frontend component renders from props directly. The `data_fetcher` is for the standalone route (if someone bookmarks it). For MVP, the standalone route can return the props from the last analysis (or a 404 if none cached).

### Step 4: Create `GpuAssessmentModule` frontend component

New file: `dashboard/frontend/src/components/modules/GpuAssessmentModule.tsx`

This is a React component that receives the structured props from the `module_invoke` event and renders the same driver/CUDA assessment cards, ML compatibility badges, warnings, and recommendations that the current GPU page renders inline (lines 605-897 of `GPU.tsx`).

**Props interface:**
```typescript
interface GpuAssessmentModuleProps {
  health_score: number
  current_status: string
  driver_assessment?: {
    current_version?: string
    latest_stable_version?: string | null
    version_comparison?: string
    action_recommended?: string
    version_analysis?: string
    change_risk?: string
  }
  cuda_assessment?: {
    compatible: boolean
    current_version?: string
    latest_version?: string | null
    version_analysis?: string
  }
  ml_compatibility?: Record<string, string>
  warnings?: string[]
  recommendations?: Array<{
    priority: string
    action: string
    command?: string
    reason?: string
  }>
  known_compatible_combos?: Array<{
    driver: string
    cuda: string
    note?: string
  }>
}
```

**Implementation:** Move the rendering logic from `GPU.tsx` lines 605-897 into this component. The component is self-contained — it takes props and renders cards. No data fetching needed (props come from the module_invoke event).

### Step 5: Register `GpuAssessmentModule` in `ModuleRenderer.tsx`

Add to the lazy imports and registry:

```typescript
const GpuAssessmentModule = lazy(() => import('./modules/GpuAssessmentModule'))

const MODULE_REGISTRY: Record<string, React.LazyExoticComponent<React.ComponentType<any>>> = {
  'config-diff': ConfigDiffModule,
  'vitals': VitalsModule,
  'drive-health': DriveHealthModule,
  'evidence': EvidenceModule,
  'gpu-assessment': GpuAssessmentModule,  // NEW
}
```

### Step 6: Rewrite the GPU page's "Deep Scan" section (`GPU.tsx`)

Replace lines 509-900 of `GPU.tsx` (the inline "AI GPU Advisor" Card with the Deep Scan button and all the structured rendering) with:

1. **The `AIAnalysisPanel` component** (or a GPU-specific variant) that streams from `/api/agent/message` with `tier: "specialist"`, `scope: "host"`, and a GPU-specific message.

2. **A `module_invoke` handler** that renders `GpuAssessmentModule` when the agent emits one. The `AIAnalysisPanel` currently only handles `response_chunk` and `thinking` events. It needs to also surface `module_invoke` events so the GPU page can render the structured module alongside the streamed text.

**Two options for the frontend approach:**

**Option A (simpler): GPU-specific analysis panel.** Create a `GpuAnalysisPanel` component (or extend `AIAnalysisPanel` with an optional `onModuleInvoke` callback) that handles `module_invoke` events. The GPU page renders the streamed markdown from `AIAnalysisPanel` and the structured cards from `GpuAssessmentModule` side by side.

**Option B (more reusable): Extend `AIAnalysisPanel` to handle `module_invoke`.** Add an optional `onModuleInvoke` prop to `AIAnalysisPanel`. When the agent emits a `module_invoke` event, the panel calls the callback. The GPU page passes a callback that renders `GpuAssessmentModule`. This makes the pattern reusable for future analysis types that want structured output.

**Recommendation: Option B.** It's a small change to `AIAnalysisPanel` (add `onModuleInvoke` prop, parse `module_invoke` SSE events) and makes the pattern reusable.

**Changes to `AIAnalysisPanel.tsx`:**
- Add `onModuleInvoke?: (module: string, props: Record<string, any>) => void` to props
- In the SSE parsing loop, handle `data.type === 'module_invoke'` and call `onModuleInvoke(data.module, data.props)`

**Changes to `GPU.tsx`:**
- Remove the inline "AI GPU Advisor" Card (lines 509-900)
- Remove `analysis`, `analyzing`, `copiedCommand`, `analysisCache` state
- Remove `loadCachedAnalysis()` function
- Add `const [gpuModule, setGpuModule] = useState<{module: string, props: any} | null>(null)`
- Render `<AIAnalysisPanel type="GPU" title="GPU" onModuleInvoke={(_, props) => setGpuModule({module: 'gpu-assessment', props})} />`
- Render `<ModuleRenderer module={gpuModule.module} props={gpuModule.props} />` below the panel when `gpuModule` is set
- Remove the `GPUAnalysis` interface (no longer needed — the structured data comes through the module props)
- Remove imports for the structured rendering icons (`ArrowUpCircle`, `ShieldCheck`, `Package`, `Globe`, `Clock`, `HelpCircle`) that are no longer used in GPU.tsx (they move to `GpuAssessmentModule.tsx`)

**macOS guard:** On macOS, the "Deep Scan" button should be hidden or show a message like "GPU analysis requires a Linux system with GPU detection tools." The monitoring UI (Part 1) still works — it just shows "No GPU detected" or the integrated Intel GPU. The `AIAnalysisPanel` can stay visible but the `canAnalyze` prop should be `false` on macOS, or the message should be GPU-specific.

### Step 7: Knowledge base content for driver/CUDA compatibility

Create a knowledge base document (in the SourcePrep `host` scope) with the NVIDIA driver/CUDA compatibility matrix. This replaces the hardcoded table in the old system prompt.

**File:** A markdown document in the host knowledge base (e.g., `~/.config/halbert/knowledge/host/nvidia-driver-cuda-compat.md`).

**Content:** The same compatibility table that was in the hardcoded system prompt, but as a maintainable document. Updated to 2026:

```markdown
# NVIDIA Driver / CUDA Compatibility Matrix

## Production Branch Drivers (2026)

| Driver | CUDA | Branch | Notes |
|--------|------|--------|-------|
| 580.x  | 13.0 | Production | Latest production (2026) |
| 575.x  | 12.8 | Production | |
| 565.x  | 12.7 | Production | |
| 560.x  | 12.6 | Production | |
| 550.x  | 12.4 | LTS | Very stable, widely deployed |
| 535.x  | 12.2 | LTS | Previous LTS |

## Compatibility Rules
- A driver supports its matched CUDA version AND all older CUDA versions.
- If CUDA is newer than what the driver supports → incompatible (HIGH priority).
- For Ampere+ (RTX 30xx, A-series, RTX 40xx, RTX 50xx): driver 550+ recommended.
- Display GPUs need Wayland/X11 compatibility — check compositor support.
- Compute-only GPUs can use any driver branch; no display server constraints.

## ML Framework Compatibility
- PyTorch: check torch.cuda.is_available() and CUDA version match.
- TensorFlow: check tf.config.list_physical_devices('GPU').
- JAX: check jax.devices() for GPU devices.
```

This document is maintained as a file, not code. When NVIDIA releases a new driver, update the document — no code change needed. The specialist model retrieves it via the `host` scope during analysis.

**Note:** This step requires the SourcePrep daemon to be running and the host project to be indexed. If SourcePrep is not available, the agent can still do the analysis using `web_search` for current driver info — it just won't have the curated compatibility matrix. The knowledge base content is an enhancement, not a hard dependency.

### Step 8: Remove dead code from `gpu.py`

After the rebuild, remove from `dashboard/routes/gpu.py`:
- `analyze_gpu_setup()` function (the `/api/gpu/analyze` endpoint) — replaced by agent
- `search_latest_driver_info()` function — replaced by agent's `web_search` tool
- `save_gpu_analysis()` / `load_gpu_analysis()` / `_get_analysis_cache_path()` — replaced by thread persistence
- The `/api/gpu/analysis-cache` endpoint — replaced by thread timestamp
- The hardcoded 120-line system prompt (lines 700-766) — replaced by knowledge base

Keep in `gpu.py`:
- `get_gpu_data()` (`/api/gpu/info`) — used by the monitoring UI
- `get_nvidia_smi()` (`/api/gpu/nvidia-smi`) — used by the monitoring UI
- `update_gpu_role()` (`/api/gpu/role/{pci_id}`) — used by the role selector
- `get_deep_context()` (`/api/gpu/deep-context`) — can stay for debugging, or be removed if the agent tools cover it

### Step 9: Unit tests

**Backend tests** (`tests/test_gpu_tools.py`):
- Mock `run_command()` to return fake `lspci` and `nvidia-smi` output
- Test `gpu_info` tool handler parses GPU data correctly
- Test `gpu_system_context` tool handler gathers context
- Test `register_gpu_tools()` registers all expected tools
- Test that tools return empty/graceful results on macOS (no `lspci`)

**Frontend:**
- No new tests needed — `GpuAssessmentModule` is a presentational component receiving props. The existing GPU page tests (if any) should still pass for the monitoring UI.

---

## File change summary

| File | Change | New/Modified |
|------|--------|-------------|
| `tools/gpu_helpers.py` | Shared GPU detection functions (moved from gpu.py) | New |
| `tools/gpu_tools.py` | Agent tool handlers + schemas + register function | New |
| `dashboard/routes/gpu.py` | Remove analyze endpoint, cache, search; import from gpu_helpers | Modified |
| `dashboard/routes/agent.py` | Register GPU tools (Linux-only guard) | Modified |
| `modules/registry.py` | Register `gpu-assessment` module | Modified |
| `dashboard/frontend/src/components/modules/GpuAssessmentModule.tsx` | Structured assessment cards (moved from GPU.tsx) | New |
| `dashboard/frontend/src/components/ModuleRenderer.tsx` | Add GpuAssessmentModule to registry | Modified |
| `dashboard/frontend/src/components/AIAnalysisPanel.tsx` | Add `onModuleInvoke` callback prop | Modified |
| `dashboard/frontend/src/pages/GPU.tsx` | Replace inline Deep Scan with AIAnalysisPanel + ModuleRenderer | Modified |
| `tests/test_gpu_tools.py` | Unit tests for GPU tools with mocked command output | New |
| Knowledge base: `nvidia-driver-cuda-compat.md` | Driver/CUDA compatibility matrix document | New |

---

## What NOT to do

- **Don't eliminate the GPU page.** The monitoring UI is useful. GPU driver/CUDA compatibility is a real pain point.
- **Don't keep the hardcoded compatibility table in code.** It's already 2 years stale. Move it to a knowledge base document.
- **Don't create a separate GPU web search tool.** The agent already has `web_search`. The model can interpret search results better than a naive regex.
- **Don't pre-stuff GPU context into the prompt.** Let the model call tools on demand — it decides what to gather based on what it finds.
- **Don't remove the monitoring UI endpoints** (`/api/gpu/info`, `/api/gpu/role`, `/api/gpu/nvidia-smi`). They're used by the live stats polling.

---

## Testing strategy (Mac development, Linux deployment)

1. **Unit tests with mocks** — can run on Mac. Mock `run_command()` to return fake `lspci`/`nvidia-smi` output. Verify the tool handlers parse correctly.
2. **Frontend build** — `npm run build` verifies TypeScript compiles and the new component renders.
3. **Integration test on Linux** — when on the Linux box with a GPU:
   - Click "Deep Scan" on the GPU page
   - Verify the agent calls `gpu_info` and `gpu_system_context` tools
   - Verify the agent retrieves driver/CUDA compatibility from the knowledge base
   - Verify the streamed markdown analysis appears in the panel
   - Verify the `gpu-assessment` module renders structured cards
   - Verify the analysis is persisted as a thread (check thread history)

---

## Open questions

1. **Should the `gpu-assessment` module's `data_fetcher` endpoint be implemented?** The props arrive via `module_invoke` SSE events, so the component renders without fetching. The `data_fetcher` is only needed for the standalone route (`/modules/gpu-assessment` as a bookmarkable URL). For MVP, skip it — return 404 or "no cached analysis" if someone hits the standalone route.

2. **Should the old `/api/gpu/analyze` endpoint be kept as a fallback?** No. The agent path is the new path. Keeping the old endpoint means maintaining two code paths. The old endpoint's structured JSON contract is rigid and the hardcoded prompt is stale. Remove it cleanly.

3. **Should the analysis cache (YAML file) be kept?** No. The agent persists the turn as a thread. If the user wants to see a previous analysis, they can find it in thread history. The 7-day staleness check is unnecessary — the user can just re-run the analysis.

4. **What about the `secure_model` slot from the Phase 7/8 transition plan?** If the GPU analysis involves sensitive system config (which it does — kernel version, installed packages, etc.), it should run on the `secure_model` (local-only) once that slot exists. For now, `tier: "specialist"` routes through the specialist model. When `secure_model` is implemented, GPU analysis should be a candidate for routing there. This is a future consideration, not a blocker.
