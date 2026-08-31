# Task Packet 04: GPU Deep-Scan Refactor & Agent Specialist Tooling

**Target Model:** **GLM-5.3 medium** (reassigned 2026-08-30; Batch U4 — runs with TASK-01 env override, TASK-05 harvester, TASK-10 verification, REV-05/REV-06 reviews)  
**Domain:** System Tooling, Agent Specialist Routing, Hardware Context Gathering, and Knowledge Indexing  
**Target Date:** 2026-08-29  
**Status:** Ready for Implementation  
**Verified 2026-08-30:** confirmed still open — raw Ollama `/api/chat` call lives at `dashboard/routes/gpu.py:693`, `POST /api/gpu/analyze` at `gpu.py:588`. `test_gpu_tools.py`/`test_gpu_routes.py` do not exist yet.  
**Governing Documents:**
- [`.handoff/MASTER-TODO.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/MASTER-TODO.md) § "GPU Page — Roll into Analyze tooling"

---

## 1. Executive Summary & Objective

The GPU Dashboard page ([`pages/GPU.tsx`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend/src/pages/GPU.tsx)) currently features a "Deep Scan" button calling `POST /api/gpu/analyze`. This route bypasses Halbert's agent architecture, personality configuration, scoped retrieval, and thread persistence, instead issuing a raw Ollama `/api/chat` call with a hardcoded 120-line system prompt containing NVIDIA/CUDA compatibility tables.

This task packet details the complete migration to:
1. Roll GPU diagnostic context gathering into official **Agent Tools** (`get_gpu_info`, `get_deep_system_context`, `search_latest_driver_info`).
2. Move NVIDIA driver and CUDA compatibility knowledge into the SourcePrep knowledge base.
3. Route GPU diagnosis through `POST /api/agent/message` with `tier: "specialist"` and `scope: "host"`.
4. Update `pages/GPU.tsx` to adopt the shared [`AIAnalysisPanel.tsx`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend/src/components/AIAnalysisPanel.tsx) component.

---

## 2. Detailed Task Breakdown & Implementation Steps

### Task 4.1: Convert GPU Context Gatherers into Registered Agent Tools
- **File:** `halbert_core/halbert_core/tools/gpu_tools.py`
  1. Extract `get_gpu_info()`, `get_deep_system_context()`, and `search_latest_driver_info()` from `dashboard/routes/gpu.py`.
  2. Decorate them as agent tools with strict Pydantic schemas and mock fallbacks for non-Linux/non-GPU test environments:
     ```python
     @tool("get_gpu_hardware_info", description="Query local NVIDIA GPU hardware, driver versions, and VRAM utilization")
     def tool_get_gpu_info() -> Dict[str, Any]: ...
     ```
  3. Register these tools in the agent tool registry (`halbert_core/halbert_core/tools/registry.py`).

### Task 4.2: Move CUDA Knowledge into SourcePrep Knowledge Base
- **File:** `data/knowledge/linux/nvidia_cuda_compatibility.md`
  1. Extract the hardcoded compatibility tables and driver upgrade matrices from the prompt in `routes/gpu.py`.
  2. Structure as clean markdown documentation with clear headings, version matrices, and troubleshooting steps so the specialist model retrieves it via `knowledge_linux` scope.

### Task 4.3: Route GPU Diagnosis through Agent Path
- **File:** [`halbert_core/halbert_core/dashboard/routes/gpu.py`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/routes/gpu.py)
  1. Deprecate the raw Ollama `POST /api/gpu/analyze` endpoint.
  2. Implement an agent message wrapper that dispatches a structured diagnostic prompt to `/api/agent/message` with `tier: "specialist"` and `scope: "host"`.

### Task 4.4: Update Frontend `pages/GPU.tsx`
- **File:** [`halbert_core/halbert_core/dashboard/frontend/src/pages/GPU.tsx`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend/src/pages/GPU.tsx)
  1. Replace custom inline analysis rendering with the shared `AIAnalysisPanel.tsx` component.
  2. Wire the "Deep Scan" button to stream agent output and display structured findings cards.

---

## 3. Verification & Test Plan

1. **Unit Tests (with mocked `nvidia-smi` and `/proc`):**
   ```bash
   pytest halbert_core/tests/test_gpu_tools.py halbert_core/tests/test_gpu_routes.py -v
   ```
2. **Frontend Build Check:**
   ```bash
   npm --prefix halbert_core/halbert_core/dashboard/frontend run build
   ```
