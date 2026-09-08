# HANDOFF: GPU-1 Next Phases — Request for a Richer Implementation Plan

**Date:** 2026-09-07
**Author:** Devin session (continuation of GPU-1 workstream)
**Status:** Handoff for a fable-tier planning session
**Related:**
- `.handoff/RESEARCH-MAC-GPU-SUPPORT-2026-09-07.md` — the original research doc
- `ROADMAP.md` row `GPU-1` — the workstream definition
- `DECISIONS.md` `GPU-ARCH` — the architectural decision
- Commits `c294091f` through `fd5758b5` on `main` — Phases 1-6 implementation

---

## 0. Purpose

We completed the first six phases of the GPU-1 workstream: a universal
GPU/accelerator telemetry model that spans NVIDIA, AMD, Intel, Apple
Silicon, and AI accelerators (Coral, Hailo, MemryX, Intel NPU, AMD NPU,
Apple ANE). The probe registry, agent tools, frontend, and discovery
scanners are all wired and tested (44 tests passing).

This handoff asks a fable-tier AI to produce a richer, deeper
implementation plan for the **next phases** — the work that takes us
from "telemetry is collected and displayed" to "Halbert actually
understands and reasons about its own hardware in real time, and uses
that understanding to make intelligent decisions about model sizing,
runtime selection, and workload placement."

We have opinions about what we need and why. We want a fable-tier
session to pressure-test those opinions, surface what we're missing,
and produce a plan with the architectural depth that the problem
deserves.

---

## 1. What We Built (Phases 1-6, now on `main`)

### 1.1 Universal GPU probe (`tools/gpu_tools.py`)

`get_gpu_info()` was refactored from a single Linux/NVIDIA path into a
**probe dispatcher**. Each probe enriches a vendor's GPUs with live
stats and classifies the memory architecture:

- `memory_architecture`: `discrete` | `unified` | `integrated`
- `memory_source_label`: `VRAM` | `Unified Memory` | `System RAM`
- `compute_api`: `cuda` | `metal` | `rocm` | `directml` | `opencl`
- `core_count`, `unified_memory_gb`, `gpu_memory_ceiling_gb`,
  `gpu_memory_in_use_gb`
- Existing compatibility fields preserved: `vram_mb`, `memory_used_mb`,
  `memory_total_mb`, `temperature_c`, `power_draw_w`, `power_limit_w`,
  `utilization_percent`, `driver_version`, `driver_type`, `cuda_version`,
  `role`, `pci_id`

Probes implemented:
- NVIDIA discrete (`nvidia-smi`)
- NVIDIA unified (RTX Spark / DGX Spark — `nvidia-smi` reports "Not
  Supported" for memory; we fall back to system memory queries)
- NVIDIA nouveau (driver-missing warning)
- AMD discrete (`rocm-smi` — fills a major pre-existing gap)
- AMD unified (Strix Halo — VRAM/GTT dual-pool, we avoid summing
  overlapping memory)
- AMD sysfs (temperature/clocks when `rocm-smi` is absent)
- Intel integrated (`i915` driver detection)
- Apple Silicon (`ioreg` for live GPU utilization + memory;
  `system_profiler` for hardware identity, core count, memory)

Verified on real hardware: Apple M1 Ultra, 128 GB unified, 48 GPU
cores, macOS 26.5.1. The probe correctly reports 96 GB GPU memory
ceiling and live memory usage.

### 1.2 AI accelerator probe (`tools/accelerator_tools.py`)

`get_accelerator_info()` detects:
- Google Coral Edge TPU (USB, M.2, Mini PCIe — `lsusb`/`lspci`/sysfs)
- Hailo-8 / 8L / 10H (`lspci` vendor `1e60`, `hailortcli scan`)
- MemryX MX3 (`lspci` vendor `1ed9`, `/dev/memx0`)
- Intel NPU (`lspci` class, `/dev/accel/accel0`, `intel_vpu` driver)
- AMD XDNA NPU (`xrt-smi`, `/dev/accel/accel0`)
- Apple Neural Engine (integrated, CoreML runtime)

Each accelerator reports: `type`, `vendor`, `model`, `form_factor`,
`device_node`, `tops`, `driver_loaded`, `driver_name`,
`driver_version`, `firmware_version`, `temperature_c`,
`utilization_percent`, `power_draw_w`, `runtime_available`,
`runtime_version`, `status`.

### 1.3 Agent tools (cross-platform)

GPU and accelerator tools are registered with the agent executor on
**all platforms** (was Linux-only). The agent can call `gpu_info`,
`gpu_system_context`, `gpu_architecture`, `search_latest_driver_info`,
and `accelerator_info` during diagnosis.

### 1.4 Frontend (`pages/GPU.tsx`)

The GPU page now:
- Uses `memory_architecture` to label memory correctly (VRAM / Unified
  Memory / System RAM) instead of hardcoding "VRAM"
- Shows `compute_api` (CUDA / Metal / ROCm / DirectML) in the card
  subtitle
- Displays `core_count` for Apple Silicon and other architectures
- Has a unified-memory detail panel (total pool, GPU ceiling, in-use)
- Hides the role selector and driver download links for Apple Silicon
- Notes when temp/power require elevated privileges on unified platforms
- Fetches `/api/gpu/accelerators` in parallel and renders an AI
  Accelerators section (TOPS, driver, runtime, firmware, device node,
  temp, utilization)
- Replaced emoji vendor icons with lucide icons (project no-emoji rule)

### 1.5 Discovery scanners (`discovery/scanners/gpu.py`,
`discovery/scanners/ai_accelerator.py`)

`GpuScanner` and `AiAcceleratorScanner` reuse the same probe functions
(`get_gpu_info()` / `get_accelerator_info()`) — no duplicate command
parsing. Both are registered in `DiscoveryEngine` for Linux and macOS.
A new `DiscoveryType.AI_ACCELERATOR` was added to the schema.

### 1.6 API endpoints

- `GET /api/gpu/info` — existing, now returns universal GPU data
- `GET /api/gpu/accelerators` — new, returns accelerator inventory
- `GET /api/gpu/deep-context` — existing, includes architecture info
- `PUT /api/gpu/role/{pci_id}` — existing, role management
- `GET /api/gpu/nvidia-smi` — existing, raw nvidia-smi (legacy)
- `POST /api/gpu/analyze` — existing, delegates to agent specialist

### 1.7 Tests

44 tests covering all GPU probes, accelerator probes, and discovery
scanners. All command output is mocked — tests pass on any platform.

---

## 2. What We Think We Need Next (and Why)

These are our opinions. We want a fable-tier session to validate,
reject, or replace them with better ideas.

### 2.1 Model sizing and runtime selection

**What:** Halbert should use its GPU/accelerator telemetry to make
intelligent decisions about which LLM model to load, what quantization
to use, and where to run inference. On an M1 Ultra with 128 GB unified
memory and 96 GB GPU ceiling, Halbert should know it can run a 70B
model at Q4 without swapping. On a system with a Coral TPU but no GPU,
it should know that inference goes to CPU and the TPU is for vision
offload (Frigate, etc.).

**Why:** Right now the GPU telemetry is display-only. The agent can
*see* its hardware but doesn't *reason* about it. The model picker
(`@halbert/model-picker`) and the inference runtime selection don't
consume the normalized GPU data. This is the biggest gap between
"telemetry" and "self-awareness."

**Open questions we want answered:**
- Should model-fit recommendations live in the probe layer, in a
  separate "hardware advisor" module, or in the agent's reasoning?
- How do we handle the unified-memory sizing problem (GPU ceiling vs
  total pool vs OS-reserved) without overclaiming?
- Should we integrate with Ollama's /api/ps or llama.cpp's server
  metrics to get *live* model memory usage, not just hardware capacity?
- How do we represent "this model fits but will be slow because the
  GPU has 12 cores" vs "this model fits and will be fast because the
  GPU has 48 cores"?
- What's the right abstraction for TPU/NPU workload routing? Coral
  can't run LLMs but can run vision models. Hailo can run some small
  models. Apple ANE can run CoreML models but not raw LLM weights.

### 2.2 GPU process attribution

**What:** On NVIDIA, `nvidia-smi` can show per-process GPU memory and
utilization. On AMD, `rocm-smi` has some process info. On Apple
Silicon, there's no per-process GPU attribution without Instruments or
`powermetrics` (sudo). We need to know *what* is using the GPU, not
just *how much*.

**Why:** When Halbert sees 90% GPU utilization, it should know whether
that's its own inference, a Frigate camera pipeline, a game, or
something else. This matters for workload scheduling — if Frigate is
pegging the Coral TPU, Halbert shouldn't try to offload vision to it.

**Open questions:**
- Is per-process GPU attribution worth the complexity on Apple Silicon
  where it requires sudo?
- Should we model GPU processes as Discovery objects (type PROCESS or
  GPU)?
- How do we correlate GPU processes with the existing process scanner?

### 2.3 Thermal and power integration

**What:** The thermal scanner (`scanners/thermal.py`) reads hwmon
sensors independently. It doesn't consume the normalized GPU/accelerator
telemetry. On Apple Silicon, GPU temperature comes from `ioreg`, not
hwmon. On AMD, it comes from `rocm-smi`. The thermal scanner is
Linux-hwmon-only and misses GPU temps on macOS and on systems where
GPU temp is only available through the vendor tool.

**Why:** Thermal throttling affects inference performance. If the GPU
is at 85C and throttling, Halbert should know that model inference
will be slower than the raw TOPS/Tflops suggest. The thermal scanner
and GPU probe should share data, not duplicate it.

**Open questions:**
- Should the thermal scanner call `get_gpu_info()` and merge GPU temps
  into its sensor list, or should the GPU scanner publish a thermal
  discovery that the thermal scanner references?
- How do we model thermal throttling as a performance modifier?
- On Apple Silicon, `powermetrics` (sudo) gives ANE power and GPU
  power domains. Should we have an optional elevated-privilege probe
  that fills in power/thermal when available?

### 2.4 Confidence, permissions, and unsupported states

**What:** The current probes return data or don't, but they don't
explicitly communicate *confidence* or *permission level*. A
temperature reading from `nvidia-smi` is authoritative. A "no
temperature" on Apple Silicon might mean "requires sudo" or "not
exposed by this API" or "the GPU is asleep." These are different
states.

**Why:** The agent needs to know not just *what* it knows but *how
reliable* that knowledge is. If the GPU memory ceiling is inferred
from `ioreg` on Apple Silicon, that's high-confidence. If it's
inferred from system memory minus a heuristic, that's lower
confidence. The agent should be able to say "I'm 90% sure I can fit a
70B model" vs "I'm guessing based on total RAM."

**Open questions:**
- Should every normalized field carry a `confidence` sub-field, or
  should confidence be a separate metadata layer?
- How do we represent "this field requires sudo and we don't have it"
  vs "this field is not exposed on this platform"?
- Should the agent's self-awareness prompt include confidence
  annotations?

### 2.5 Generalized GPU diagnostic prompts

**What:** The diagnostic prompt in `dashboard/routes/gpu.py`
(`_build_diagnostic_prompt`) and the frontend
(`GPU_DIAGNOSTIC_MESSAGE` in `GPU.tsx`) are still NVIDIA/CUDA-centric.
They say "CUDA compatibility," "NVIDIA driver/CUDA compatibility
guidance," and "NVIDIA Packages." On an Apple Silicon Mac or an AMD
ROCm system, these prompts are wrong.

**Why:** The agent's diagnostic reasoning is only as good as the
prompt that frames it. If the prompt says "check CUDA compatibility"
on a Metal-only system, the agent will either hallucinate or waste
effort. The prompt should be `compute_api`-aware: CUDA for NVIDIA,
Metal for Apple, ROCm for AMD, DirectML for Windows.

**Open questions:**
- Should the diagnostic prompt be fully templated by
  `memory_architecture` + `compute_api`, or should it be a general
  prompt with the hardware context injected?
- Should we have separate knowledge-base entries for Metal/ROCm
  driver compatibility, or should the agent web-search for them?
- How do we handle systems with multiple compute APIs (e.g., NVIDIA
  GPU + Intel NPU)?

### 2.6 Live refresh and polling strategy

**What:** The frontend polls `/api/gpu/info` every 5 seconds. The
discovery scanners run on a schedule (or on demand). The agent tools
call `get_gpu_info()` on demand. There's no unified refresh strategy.

**Why:** GPU utilization changes second-to-second. Memory usage
changes when models load/unload. Temperature trends matter for
throttling prediction. A 5-second poll is fine for the dashboard but
the agent might want a snapshot at the start of a turn and a
difference since the last turn. The discovery feed doesn't need
per-second data but should reflect model load state.

**Open questions:**
- Should we have a GPU telemetry cache with a TTL, so the agent,
  dashboard, and discovery scanners all read from the same snapshot?
- Should we support WebSocket push for GPU stats (the dashboard
  already has a WS connection for other data)?
- How do we handle the cost of `system_profiler` on Apple Silicon
  (it's slow — 2-5 seconds — vs `ioreg` which is fast)?

### 2.7 Optional runtime integrations (lazy extras)

**What:** We deliberately kept heavy dependencies out of the initial
phases. The probes use subprocess calls to CLI tools (`nvidia-smi`,
`rocm-smi`, `ioreg`, `system_profiler`, `lspci`, `lsusb`,
`hailortcli`, `xrt-smi`). But there are richer integrations possible:
- Metal framework via PyObjC for GPU utilization, memory pressure,
  and MPS (Metal Performance Shaders) device info
- CUDA Python or `pynvml` for per-process GPU memory and
  non-`nvidia-smi` telemetry
- ROCm Python bindings for richer AMD telemetry
- HailoRT SDK for Hailo FPS/latency/power benchmarking
- OpenVINO / Level Zero for Intel NPU utilization
- `xrt-smi` for AMD XDNA NPU telemetry

**Why:** CLI tools are universal and dependency-free, but they're
limited in what they expose. PyObjC/Metal can give real-time GPU
memory pressure and utilization without parsing `ioreg` text. `pynvml`
can give per-process GPU memory. These are the difference between
"good enough telemetry" and "production-grade monitoring."

**Open questions:**
- Which of these are worth the dependency cost?
- Should they be optional extras (like the `vision` extra) or
  function-level lazy imports?
- How do we handle the case where the optional dependency is installed
  but the hardware isn't present?
- Should the probe registry try the rich API first and fall back to
  the CLI tool, or should they be separate probes?

### 2.8 Qualcomm Snapdragon X and Windows-on-ARM

**What:** The Snapdragon X Elite (and the NVIDIA RTX Spark running
Windows-on-ARM) represent a growing class of Windows-on-ARM AI
computers with unified memory and significant NPUs (45 TOPS Hexagon).
We have no probe for Windows. The current code is Linux + macOS only.

**Why:** These machines are shipping now and will be a significant
part of the personal AI computer market. If Halbert runs on Windows
(via Tauri), it should be able to detect the GPU and NPU.

**Open questions:**
- Should we add a Windows probe using `wmic` / PowerShell / DXGI?
- Is Windows support in scope for GPU-1 or should it be a separate
  workstream?
- How do we model the Snapdragon X's Adreno GPU + Hexagon NPU
  relationship?

### 2.9 Federation: remote node GPU awareness

**What:** Halbert has a federation system for managing multiple nodes.
When Halbert on Machine A talks to Halbert on Machine B, it should
know Machine B's GPU/accelerator capabilities. Currently the GPU data
is local-only.

**Why:** A user might ask "which of my machines can run a 70B model?"
or "offload this vision pipeline to the machine with the Coral TPU."
That requires federated GPU/accelerator awareness.

**Open questions:**
- Should GPU/accelerator data be part of the federation peer info
  exchange?
- Should the model sizing advisor work across federated nodes?
- How do we handle stale remote GPU data (a peer that was probed 6
  hours ago)?

---

## 3. What We Want From the Fable-Tier Session

### 3.1 Pressure-test our opinions

We have nine areas of proposed work above. We want a fable-tier
session to:
- Tell us which are wrong, redundant, or premature
- Surface areas we missed
- Identify the critical path vs nice-to-have
- Flag architectural decisions that are hard to reverse

### 3.2 Produce a phased plan with model-tier assignments

Following the convention in `.handoff/PLAN-VOICE-ASSISTANT-APP-UI-ACCESS-2026-09-07.md`:
- Each workstream broken into tasks
- Each task has: model tier (`fable`/`opus`/`sonnet`), effort level
  (`ultracode`/`max`/`xhigh`/`high`/`med`), dependencies, acceptance
  criteria, risks
- Recommended sequencing and what to defer

### 3.3 Address the hard architectural questions

The open questions in each section above are not rhetorical. We want
real answers with tradeoff analysis. The hardest ones:

1. **Where does model-fit reasoning live?** (probe layer vs separate
   advisor vs agent reasoning)
2. **How do we represent confidence and permission states** without
   making every field a nested object?
3. **What's the right thermal integration architecture** — does the
   thermal scanner consume GPU data, or do they publish to a shared
   bus?
4. **Which optional runtime integrations are worth the dependency
   cost?**
5. **Is Windows-on-ARM in scope for GPU-1 or a separate workstream?**

### 3.4 Consider the Halbert-specific context

This isn't a generic GPU monitoring tool. It's Halbert's
self-awareness. The plan should consider:
- Halbert identifies as the computer itself (not an "assistant")
- The agent uses GPU data for self-modeling ("I have 128 GB of unified
  memory and 48 GPU cores, so I can run a 70B model at Q4")
- The dashboard is for the user to understand the machine; the agent
  tools are for Halbert to understand itself
- The discovery feed is for long-term memory and cross-correlation
- The subtractive dependency contract: only 2 hard deps (`pyyaml`,
  `requests`); everything else is lazy optional extras
- No model names in user-facing surfaces; no "assistant" terminology
- No emoji in UI; use design tokens for colors

### 3.5 Reference the existing code

The plan should reference the actual files and functions:
- `halbert_core/halbert_core/tools/gpu_tools.py` — probe registry
- `halbert_core/halbert_core/tools/accelerator_tools.py` — accelerator
  probes
- `halbert_core/halbert_core/dashboard/routes/gpu.py` — API routes +
  diagnostic prompt
- `halbert_core/halbert_core/dashboard/frontend/src/pages/GPU.tsx` —
  frontend
- `halbert_core/halbert_core/discovery/scanners/gpu.py` — GpuScanner
- `halbert_core/halbert_core/discovery/scanners/ai_accelerator.py` —
  AiAcceleratorScanner
- `halbert_core/halbert_core/discovery/scanners/thermal.py` — thermal
  scanner (Linux hwmon only, doesn't consume GPU probe data)
- `halbert_core/halbert_core/discovery/engine.py` — discovery engine
- `halbert_core/halbert_core/discovery/schema.py` — Discovery schema
- `halbert_core/halbert_core/dashboard/routes/agent.py` — agent tool
  registration

---

## 4. Constraints

- **No new mandatory dependencies.** Heavy ML/runtime deps must remain
  function-level lazy optional extras (the subtractive contract).
- **Python >=3.10** target (dev env is 3.9.18, which causes
  `contextlib.aclosing` import errors in `gpu.py` — this is a known
  pre-existing issue, not introduced by GPU-1).
- **Node.js 22 LTS**, npm 10.9+ / pnpm 10.29+ for frontend.
- **React 18.2** in the desktop app (planned upgrade to 19).
- **No emoji in UI.** Use lucide icons or design tokens.
- **No model names in user-facing surfaces.**
- **No "assistant" terminology.** Halbert is the computer.
- **`ROADMAP.md` is the sole authoritative planning document.**
- **`DECISIONS.md` is append-only.**
- **No `Co-Authored-By` or generation attribution in commits.**
- **Before editing hub files, use SourcePrep impact analysis.**

---

## 5. Current State Summary

| Component | Status | Key gap |
|-----------|--------|---------|
| GPU probe registry | Done (Phases 1-2) | No Windows, no Qualcomm |
| Accelerator probes | Done (Phase 3) | No live utilization for most accelerators |
| Agent tool registration | Done (Phase 4) | Agent doesn't *reason* about hardware yet |
| Frontend display | Done (Phase 5) | No model-fit UI, no live process list |
| Discovery scanners | Done (Phase 6) | Thermal scanner doesn't consume GPU data |
| Model sizing advisor | Not started | Biggest gap — telemetry is display-only |
| GPU process attribution | Not started | Need per-process GPU memory |
| Thermal integration | Not started | Thermal scanner is hwmon-only |
| Confidence/permissions | Not started | No explicit confidence semantics |
| Diagnostic prompt generalization | Not started | Still NVIDIA/CUDA-centric |
| Live refresh strategy | Not started | 5s poll, no cache, no WS push |
| Optional runtime integrations | Not started | PyObjC/Metal, pynvml, HailoRT, etc. |
| Windows-on-ARM | Not started | No Windows probe |
| Federation GPU awareness | Not started | Remote nodes don't exchange GPU data |

---

## 6. Suggested Reading Order for the Fable Session

1. This handoff (you're reading it)
2. `.handoff/RESEARCH-MAC-GPU-SUPPORT-2026-09-07.md` — the full
   research doc with vendor architecture details, memory semantics,
   and the dual-pool problem
3. `halbert_core/halbert_core/tools/gpu_tools.py` — the actual probe
   code (read the probe functions and the `get_gpu_info()` dispatcher)
4. `halbert_core/halbert_core/tools/accelerator_tools.py` — the
   accelerator probes
5. `halbert_core/halbert_core/dashboard/routes/gpu.py` — the
   diagnostic prompt that needs generalizing (lines 107-183)
6. `halbert_core/halbert_core/discovery/scanners/thermal.py` — the
   thermal scanner that should consume GPU data
7. `halbert_core/halbert_core/discovery/engine.py` — the discovery
   engine registration
8. `halbert_core/halbert_core/dashboard/frontend/src/pages/GPU.tsx` —
   the frontend (just updated in Phase 5)
9. `ROADMAP.md` row `GPU-1` — the workstream definition
10. `DECISIONS.md` entry `GPU-ARCH` — the architectural decision

---

## 7. Deliverable

A single implementation plan document at:
`.handoff/PLAN-GPU-1-NEXT-PHASES-2026-09-07.md`

Following the format of
`.handoff/PLAN-VOICE-ASSISTANT-APP-UI-ACCESS-2026-09-07.md`:
- Numbered sections
- Workstreams labeled with letters
- Each task has model tier, effort, dependencies, acceptance criteria,
  risks
- Section 12 (or equivalent): recommended sequencing and what to defer
- Reference actual files and functions
- Address every open question in Section 2
- No implementation — plan only
