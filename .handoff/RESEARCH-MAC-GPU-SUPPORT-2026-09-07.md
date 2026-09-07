# Research: Universal GPU Support — Unified Memory Architectures

**Date:** 2026-09-07
**Goal:** Bring GPU insights (UI tab + agent self-awareness) to all modern
GPU architectures, with a **universal-first** design that handles the new
class of unified-memory AI computers (Apple Silicon, NVIDIA RTX Spark,
AMD Strix Halo, Qualcomm Snapdragon X) before adding platform-specific
probes. The existing NVIDIA-discrete path stays; it becomes one of several
probes under a common abstraction.

---

## 0. Why this is bigger than "Mac support"

The GPU landscape in 2026 has fundamentally shifted. "Unified memory" is
no longer an Apple-only curiosity — it is the dominant architecture for
the new class of "personal AI computers" from every major vendor:

| Vendor | Product | Ship date | Unified memory | GPU | OS | Stats tool |
|--------|---------|-----------|----------------|-----|----|------------|
| Apple | M1–M6 Ultra | shipping | up to 128GB+ | Metal | macOS | `ioreg` / Metal API |
| NVIDIA | RTX Spark (N1X) | Oct 2026 | up to 128GB LPDDR5X | Blackwell + CUDA | Windows-on-ARM | `nvidia-smi` (but memory = "Not Supported") |
| AMD | Ryzen AI Max+ 395 (Strix Halo) | shipping | up to 128GB LPDDR5X | RDNA 3.5 (Radeon 8060S) + NPU | Linux / Windows | `rocm-smi` (VRAM/GTT dual-pool issue) |
| Qualcomm | Snapdragon X Elite | shipping | up to 32GB LPDDR5X | Adreno + Hexagon NPU (45 TOPS) | Windows-on-ARM | Snapdragon Profiler / DirectML |

**The ASUS machine the user referenced** (announced at IFA 2026, Sept 2) is
the ASUS ProArt P16/P14/GR1X — powered by **NVIDIA RTX Spark**, not a
separate ASUS architecture. ASUS is the first-wave OEM for RTX Spark.

All four architectures share the same fundamental design:
- **Single physical LPDDR5X pool** shared between CPU and GPU
- **No dedicated VRAM chip** — "VRAM" is a software carve-out or virtual
  mapping of the unified pool
- **GPU working-set ceiling** is a fraction of total unified memory
- The old `nvidia-smi`/`rocm-smi` model of "dedicated VRAM used / total"
  **breaks** on these machines

### The critical discovery: `nvidia-smi` itself reports "Memory-Usage: Not Supported" on unified memory

From the **DGX Spark User Guide** (NVIDIA's own docs, section 2.2.2):

> On iGPU platforms, nvidia-smi will display "Memory-Usage: Not Supported"
> even though per process GPU memory is listed. This is expected because
> iGPUs do not have dedicated framebuffer memory.

NVIDIA's guidance (section 2.2.4) is to use **CUDA unified memory APIs**
(`cudaMemGetInfo`, `cudaDeviceGetAttribute`) or system-level memory queries
instead of `nvidia-smi` for memory on these platforms.

### The AMD Strix Halo dual-pool problem

From the ROCm docs and GitHub issues (ROCm/ROCm#6004):

`rocm-smi` on Strix Halo reports **two** memory pools:
- **VRAM pool**: a fixed BIOS carve-out (e.g. 8GB or 96GB — user-configurable)
- **GTT pool**: the remaining system RAM, dynamically mapped to GPU virtual
  address space (~50% of total RAM by default)

Tools that sum these (like Ollama) report ~132GB "available" on a 128GB
machine, which is wrong — they're the same physical memory. The pools have
different allocation semantics:
- VRAM: `hipMalloc` (coarse-grained, limited to carve-out size)
- GTT: `hipMallocManaged` (unified memory, up to actual free system RAM)

This is a **monitoring abstraction problem**, not just a Mac problem. Our
GPU tooling needs to understand "unified memory architecture" as a concept
that spans all four vendors.

---

## 1. Current State (Halbert codebase)

### 1.1 Backend detection — `tools/gpu_tools.py`

`get_gpu_info()` is **hard-gated on Linux**. On non-Linux it returns an
empty result with the issue string
`"GPU detection requires Linux (lspci / nvidia-smi); this platform is not supported."`

On Linux it uses:
- `lspci -nn` — hardware enumeration (NVIDIA / AMD / Intel)
- `nvidia-smi --query-gpu=...` — live stats (driver, VRAM, temp, power, util)
- `nvcc --version` — CUDA version
- `lsmod` — driver module detection (nouveau / amdgpu / radeon / i915)

**Note:** The current code only queries `nvidia-smi` — it does **not**
query `rocm-smi` for AMD GPUs, so AMD live stats (utilization, memory,
temp, power) are never populated even on Linux. This is a pre-existing gap.

Fields produced per GPU:
`vendor, model, pci_id, vram_mb, driver_version, driver_type, cuda_version,
temperature_c, power_draw_w, power_limit_w, utilization_percent,
memory_used_mb, memory_total_mb, role`

The schema assumes **discrete VRAM** — `vram_mb`, `memory_used_mb`,
`memory_total_mb` all refer to a dedicated GPU memory chip. This is wrong
for unified memory architectures.

### 1.2 Agent tool registration — `routes/agent.py` lines 302-308

```python
import platform as _platform
if _platform.system() == "Linux":
    try:
        from ...tools.gpu_tools import register_gpu_tools
        register_gpu_tools(tool_executor)
    except Exception as e:
        logger.warning(f"Could not register GPU tools (non-fatal): {e}")
```

The Halbert AI **never sees GPU tools on macOS or Windows**, and on Linux
only sees NVIDIA (via nvidia-smi) — AMD live stats are missing.

### 1.3 HTTP routes — `dashboard/routes/gpu.py`

`/api/gpu/info`, `/api/gpu/nvidia-smi`, `/api/gpu/role/{pci_id}`,
`/api/gpu/deep-context`, `/api/gpu/analysis-cache`, `/api/gpu/analyze`.
All wrap `gpu_tools` functions, so all return empty/unsupported on Mac/Windows.

### 1.4 Frontend — `pages/GPU.tsx`

Polls `/api/gpu/info` every 5s. Renders GPU cards with live stats
(utilization, VRAM, temp, power), a role selector, vendor icons
(NVIDIA/AMD/Intel), and an AI deep-scan panel. Falls back to "No Dedicated
GPU Detected" when `gpus` is empty — which is what every Mac/Windows user
sees today. The labels are NVIDIA-centric ("VRAM", "CUDA", "NVIDIA Drivers").

### 1.5 Hardware detector — `model/hardware_detector.py`

This is the **one place unified memory is already understood**, but only for
*model-size budgeting*, not for the GPU tab or agent tools. It uses
`utils/platform.py` helpers:

- `is_mac_apple_silicon()` — checks `arm64` / `sysctl machdep.cpu.brand_string`
- `get_unified_memory_gb()` — `sysctl -n hw.memsize`
- `detect_metal_gpu()` — `system_profiler SPDisplaysDataType -json`
- `apple_intelligence_eligible()` — Apple Silicon + macOS >= 15.1 + >= 16GB + Metal

`HardwareCapabilities` carries `is_apple_silicon`, `unified_memory_gb`,
`metal_gpu`. `ModelBudget` has `memory_source: "unified" | "vram" | "ram"`
and `UNIFIED_MEMORY_FRACTION = 0.75`. But none of this flows into
`gpu_tools.py` or the GPU tab.

**This is the right abstraction to extend** — `memory_source` already
distinguishes unified from discrete. We need to bring that concept into
`gpu_tools.py`.

---

## 2. The Universal-First Design

### 2.1 Core concept: `memory_architecture` field

Every GPU gets classified into one of three memory architectures:

| Architecture | Description | Examples | "VRAM" means |
|-------------|-------------|----------|--------------|
| `discrete` | Dedicated GDDR/HBM memory chip | RTX 4090, RX 7900 XTX, data-center A100 | Actual VRAM chip capacity |
| `unified` | CPU+GPU share single LPDDR5X pool; GPU has a large working-set ceiling | Apple M1 Ultra, RTX Spark N1X, Strix Halo | GPU working-set ceiling (fraction of pool) |
| `integrated` | iGPU with small/no dedicated memory; borrows from system RAM | Intel UHD, old AMD APUs, Snapdragon X Elite | System RAM fraction (no separate pool) |

This field drives how the UI labels memory and how the AI reasons about
its memory budget.

### 2.2 Normalized GPU info schema (extends existing)

Add these fields to the per-GPU dict, additive (don't break existing
consumers):

```python
{
    # ... existing fields ...
    "memory_architecture": "discrete" | "unified" | "integrated",
    "unified_memory_gb": int | null,       # total system pool (unified only)
    "gpu_memory_ceiling_gb": float | null, # GPU's max working-set (unified: fraction; discrete: = vram_mb)
    "gpu_memory_in_use_gb": float | null,  # currently allocated by GPU
    "core_count": int | null,              # GPU cores/CUs/SMs
    "npu_tops": float | null,              # NPU throughput (Snapdragon, Strix Halo)
    "npu_utilization_percent": int | null, # NPU load (where available)
    "compute_api": str | null,             # "cuda" | "metal" | "rocm" | "directml" | "opencl"
    "memory_source_label": str,            # human: "Unified Memory" | "VRAM" | "System RAM"
}
```

The existing `vram_mb`, `memory_used_mb`, `memory_total_mb` fields stay
for backward compatibility but are populated from the normalized values:
- `discrete`: `vram_mb` = VRAM chip, `memory_total_mb` = same, `memory_used_mb` = nvidia-smi/rocm-smi
- `unified`: `vram_mb` = `gpu_memory_ceiling_gb * 1024`, `memory_total_mb` = same, `memory_used_mb` = GPU-allocated bytes
- `integrated`: `vram_mb` = null or system RAM fraction, `memory_total_mb` = shared system RAM

### 2.3 Probe dispatcher

Instead of one `get_gpu_info()` that branches on platform, use a
**probe registry** — each probe knows what it can detect and the dispatcher
tries them in priority order:

```
get_gpu_info()
  ├── _probe_nvidia_discrete()   # Linux/Windows: nvidia-smi (existing path, enhanced)
  ├── _probe_nvidia_unified()    # Windows-on-ARM: nvidia-smi for util/temp + CUDA/sys mem
  ├── _probe_amd_discrete()      # Linux: rocm-smi (NEW — not currently implemented)
  ├── _probe_amd_unified()       # Linux: rocm-smi with VRAM/GTT awareness (Strix Halo)
  ├── _probe_apple_silicon()     # macOS: ioreg + system_profiler + Metal
  ├── _probe_intel()             # Linux: lspci + /sys/class/drm (future)
  └── _probe_qualcomm()          # Windows-on-ARM: DirectML / Snapdragon Profiler (future)
```

Each probe returns `Optional[List[Dict]]` — a list of GPU dicts in the
normalized schema, or None if it can't detect anything on this platform.
The dispatcher runs all applicable probes and merges results.

**Probes are platform-aware but not platform-gated** — e.g.
`_probe_nvidia_discrete()` works on both Linux and Windows (nvidia-smi is
cross-platform). `_probe_apple_silicon()` only runs on macOS. The probe
itself checks its prerequisites and returns None if they're not met.

### 2.4 What each probe needs

#### `_probe_nvidia_discrete()` — existing, enhanced
- **Platform:** Linux, Windows (nvidia-smi is cross-platform)
- **Source:** `nvidia-smi --query-gpu=...` (existing command)
- **Memory:** `memory.total`, `memory.used` (dedicated VRAM — works)
- **Architecture:** `discrete`
- **Enhancement:** Also query `nvidia-smi --query-gpu=... --format=xml`
  for more fields (ECC, MIG, etc.) and detect unified vs discrete by
  checking if `memory.total` returns "[N/A]" or "Not Supported"

#### `_probe_nvidia_unified()` — NEW (RTX Spark / DGX Spark)
- **Platform:** Windows-on-ARM (and Linux via WSL2)
- **Source:** `nvidia-smi` for utilization, temp, power, driver, CUDA version
- **Memory:** `nvidia-smi` returns "Not Supported" for memory. Use:
  - WSL2/Linux: `cat /proc/meminfo` (MemTotal, MemAvailable) + CUDA
    `cudaMemGetInfo` if PyTorch/CUDA toolkit available
  - Windows: `GlobalMemoryStatusEx` or WMI `Win32_OperatingSystem` for
    total/available physical memory; GPU working-set ceiling = ~75% of
    total (NVIDIA's documented fraction for Spark)
- **Architecture:** `unified`
- **Key insight:** nvidia-smi works for everything *except* memory on
  these machines. We don't need a different tool — we need a different
  memory query strategy.

#### `_probe_amd_discrete()` — NEW (fills existing gap)
- **Platform:** Linux
- **Source:** `rocm-smi --showuse --showtemp --showpower --showclocks`
- **Memory:** `rocm-smi --showmeminfo vram` (dedicated VRAM — works on
  discrete cards like RX 7900 XTX)
- **Architecture:** `discrete`
- **Note:** The current code detects AMD via `lspci` but never queries
  `rocm-smi` for live stats. This probe fills that gap.

#### `_probe_amd_unified()` — NEW (Strix Halo)
- **Platform:** Linux (ROCm), Windows (ADL SDK)
- **Source:** `rocm-smi` for utilization, temp, power
- **Memory:** This is the hard part. `rocm-smi` reports VRAM + GTT
  separately. The correct interpretation:
  - `gpu_memory_ceiling_gb` = VRAM carve-out (from
    `cat /sys/class/drm/card*/device/mem_info_vram_total`) + GTT
    dynamically-mapped memory, but capped at actual free system memory
  - `gpu_memory_in_use_gb` = VRAM used + GTT used (but don't double-count
    — they're the same physical memory)
  - `unified_memory_gb` = total system RAM (`/proc/meminfo` MemTotal)
  - Practical approach: report VRAM carve-out as the "guaranteed" ceiling
    and note that unified memory extends it dynamically. The AI cares
    about "can I fit a model" — the answer is "up to free system RAM,
    with the VRAM carve-out as the fast path."
- **Architecture:** `unified`
- **NPU:** Strix Halo has XDNA 2 NPU (50 TOPS). Query via
  `xrt-smi examine` (AMD XRT tool) if available.

#### `_probe_apple_silicon()` — NEW (verified on M1 Ultra, this machine)
- **Platform:** macOS only
- **Source:** `system_profiler SPDisplaysDataType -json` (hardware identity)
  + `ioreg -c AGXAccelerator -r -d 1` (live stats, NO ROOT)
  + `sysctl -n hw.memsize` (unified memory total)
  + `sw_vers -productVersion` (OS version = driver version)
- **Memory:**
  - `unified_memory_gb` = `hw.memsize / 1024^3`
  - `gpu_memory_ceiling_gb` = Metal `recommendedMaxWorkingSetSize` (if
    PyObjC-Metal available) or `unified_memory_gb * 0.75` (fallback)
  - `gpu_memory_in_use_gb` = `ioreg` `In use system memory` / 1024^3
- **Utilization:** `ioreg` `PerformanceStatistics` → `Device Utilization %`
- **Architecture:** `unified`
- **Compute API:** `metal`
- **Power/Temp:** Requires `powermetrics` (sudo). Graceful degradation.
- **Verified `ioreg` output on this M1 Ultra (128GB, 48 cores):**
  ```
  Device Utilization %: 0
  Renderer Utilization %: 0
  Tiler Utilization %: 0
  Alloc system memory: 28067201024      (~28 GB)
  In use system memory: 1280835584      (~1.2 GB)
  gpu-core-count: 48
  model: Apple M1 Ultra
  ```

#### `_probe_qualcomm()` — FUTURE (Snapdragon X Elite)
- **Platform:** Windows-on-ARM
- **Source:** DirectML / Windows Device APIs (future investigation)
- **Architecture:** `integrated` (32GB shared, NPU-first)
- **NPU:** 45 TOPS Hexagon NPU — the primary AI accelerator, not the GPU
- **Priority:** Lower — Snapdragon X Elite is a thin-and-light class
  machine, not a workstation. The NPU matters more than the GPU here.

---

## 3. Field Mapping: All architectures -> normalized schema

| Normalized field | NVIDIA discrete | NVIDIA unified (Spark) | AMD discrete | AMD unified (Strix Halo) | Apple Silicon | Qualcomm (future) |
|-----------------|-----------------|------------------------|--------------|--------------------------|---------------|-------------------|
| `vendor` | "NVIDIA" | "NVIDIA" | "AMD" | "AMD" | "Apple" | "Qualcomm" |
| `model` | nvidia-smi name | nvidia-smi name | rocm-smi name | rocm-smi name | system_profiler | DirectML |
| `memory_architecture` | `discrete` | `unified` | `discrete` | `unified` | `unified` | `integrated` |
| `unified_memory_gb` | null | sys mem total | null | /proc/meminfo | hw.memsize | sys mem total |
| `gpu_memory_ceiling_gb` | vram_mb/1024 | sys mem * 0.75 | vram_mb/1024 | VRAM carve-out + GTT | Metal working-set or 0.75*pool | sys mem fraction |
| `gpu_memory_in_use_gb` | nvidia-smi mem.used | sys mem used (approx) | rocm-smi vram used | VRAM used + GTT used | ioreg In use | DirectML |
| `utilization_percent` | nvidia-smi | nvidia-smi | rocm-smi | rocm-smi | ioreg Device Util % | DirectML |
| `temperature_c` | nvidia-smi | nvidia-smi | rocm-smi | rocm-smi | powermetrics (sudo) | — |
| `power_draw_w` | nvidia-smi | nvidia-smi | rocm-smi | rocm-smi | powermetrics (sudo) | — |
| `core_count` | nvidia-smi | nvidia-smi | rocm-smi CUs | rocm-smi CUs | ioreg gpu-core-count | — |
| `npu_tops` | null | null | null | 50 (XDNA 2) | null (ANE separate) | 45 (Hexagon) |
| `compute_api` | "cuda" | "cuda" | "rocm" | "rocm" | "metal" | "directml" |
| `driver_version` | nvidia-smi | nvidia-smi | rocm-smi | rocm-smi | sw_vers | — |
| `memory_source_label` | "VRAM" | "Unified Memory" | "VRAM" | "Unified Memory" | "Unified Memory" | "System RAM" |

---

## 4. What the Halbert AI gains (the "understand itself" requirement)

With the universal-first design, the AI on **any** machine can call
`gpu_info` and learn:

- **Identity:** "I am running on an [Apple M1 Ultra / NVIDIA RTX Spark /
  AMD Ryzen AI Max+ 395] with [48 GPU cores / 6144 CUDA cores / 40 CUs]."
- **Memory architecture:** "My GPU uses unified memory — [128GB] total
  pool, [~96GB] GPU working-set ceiling, [1.2GB] currently in use." This
  tells it whether another model can be loaded.
- **Real-time load:** "GPU at 12% utilization." Tells it whether inference
  is already saturating the GPU.
- **Compute API:** "Metal / CUDA / ROCm is available; [MLX / Ollama /
  vLLM] is my native runtime."
- **NPU (where present):** "I have a 50-TOPS NPU available for
  on-device AI." Relevant for Apple Intelligence and Strix Halo.

This is the same class of self-knowledge the AI already has on Linux
NVIDIA boxes, generalized to every modern platform.

---

## 5. Implementation Plan (phased, universal-first)

### Phase 1 — Refactor to probe registry + `memory_architecture` field

**Files:** `tools/gpu_tools.py`, `tests/test_gpu_tools.py`

1. Add `memory_architecture`, `unified_memory_gb`, `gpu_memory_ceiling_gb`,
   `gpu_memory_in_use_gb`, `core_count`, `compute_api`,
   `memory_source_label` to the GPU dict schema.
2. Refactor `get_gpu_info()` into a **dispatcher** that calls probe
   functions and merges results. Each probe returns
   `Optional[List[Dict]]`.
3. Extract the existing Linux NVIDIA path into `_probe_nvidia_discrete()`.
   Enhance it to detect unified vs discrete (nvidia-smi memory = "Not
   Supported" → unified).
4. Add `_probe_nvidia_unified()` for RTX Spark: nvidia-smi for
  util/temp/power + system memory queries for the memory fields.
5. Add `_probe_amd_discrete()`: rocm-smi for live stats (fills the
   existing gap where AMD is detected but never queried for stats).
6. Add `_probe_amd_unified()`: rocm-smi with VRAM/GTT awareness for
   Strix Halo. Detect via `rocm-smi --showproductname` + checking for
   gfx1151 / "Radeon 8060S" / unified memory indicators.
7. Backward compatibility: existing `vram_mb`, `memory_used_mb`,
   `memory_total_mb` are populated from the normalized values.
8. Tests: mock each probe's command outputs, test the dispatcher, test
   that each probe returns the right `memory_architecture`.

**Result:** `/api/gpu/info` works on all Linux GPU types (NVIDIA discrete,
NVIDIA Spark, AMD discrete, AMD Strix Halo) with correct memory semantics.
The schema is ready for Mac and Windows.

### Phase 2 — Apple Silicon probe

**Files:** `tools/gpu_tools.py`, `tests/test_gpu_tools.py`

1. Add `_probe_apple_silicon()` per section 2.4 above.
2. Wire it into the dispatcher (runs on macOS).
3. Add Apple Silicon entries to `get_gpu_architecture()` (M1/M2/M3/M4/M5/M6
   families).
4. Add `_get_apple_system_context()` for `get_deep_system_context()`
   (macOS version, Metal version, MLX presence, PyTorch MPS backend).
5. Tests: mock `system_profiler`/`ioreg`/`sysctl`/`sw_vers`.

**Result:** `/api/gpu/info` returns a real GPU on Mac. The GPU tab shows
the M1 Ultra with live utilization and memory.

### Phase 3 — Agent tool registration on all platforms

**File:** `routes/agent.py`

Replace the hard Linux guard:
```python
if _platform.system() == "Linux":
    register_gpu_tools(tool_executor)
```
with unconditional registration:
```python
try:
    from ...tools.gpu_tools import register_gpu_tools
    register_gpu_tools(tool_executor)
except Exception as e:
    logger.warning(f"Could not register GPU tools (non-fatal): {e}")
```

The probes themselves handle platform detection — if no probe matches,
`get_gpu_info()` returns an empty list with an explanatory issue, same as
the current non-Linux fallback.

Update the `gpu_info` tool schema description to reflect multi-platform
support.

**Result:** The Halbert AI can call `gpu_info` on any platform and reason
about its own GPU.

### Phase 4 — Frontend: universal labels + vendor awareness

**File:** `pages/GPU.tsx`

1. Read `memory_architecture` from the GPU info and use it to label:
   - `discrete` → "VRAM" (existing)
   - `unified` → "Unified Memory"
   - `integrated` → "System RAM"
2. Read `compute_api` to label the compute column:
   - `cuda` → "CUDA" (existing)
   - `metal` → "Metal"
   - `rocm` → "ROCm"
   - `directml` → "DirectML"
3. Read `core_count` and display it in the card header.
4. Show `unified_memory_gb` and `gpu_memory_ceiling_gb` for unified
   architectures (e.g. "128 GB unified pool / 96 GB GPU ceiling").
5. Vendor-specific sections:
   - Apple: hide role selector (single-GPU), hide driver download links,
     show Metal version.
   - NVIDIA: existing links + show CUDA version.
   - AMD: show ROCm version, link to AMD drivers.
6. Handle `temperature_c === null && power_draw_w === null` gracefully —
   show a note for unified architectures where power/temp require
   elevated privileges.
7. Add NPU info display when `npu_tops` is present (Strix Halo, Snapdragon).
8. No emojis per project rules — use lucide icons for vendor badges.

### Phase 5 — Optional enrichments (lazy, opt-in)

- **Metal API** (PyObjC): `_get_metal_device_info()` for precise
  `recommendedMaxWorkingSetSize` / `currentAllocatedSize`. Lazy import,
  optional extra per the Subtractive Contract.
- **powermetrics sudo** (macOS): documented opt-in for power/temp.
  sudoers entry scoped to the exact command.
- **NPU monitoring** (Strix Halo): `xrt-smi examine` for XDNA NPU stats.
- **Qualcomm probe** (future): DirectML / Windows Device APIs for
  Snapdragon X Elite.

---

## 6. Risks & Open Questions

1. **`nvidia-smi` on RTX Spark hasn't shipped yet** (October 2026). The
   "Memory-Usage: Not Supported" behavior is documented in the DGX Spark
   guide (which uses the same GB10/Grace-Blackwell silicon). We can
   implement the probe now based on the documented behavior, but can't
   test against real hardware until October. The probe should be
   defensive: if nvidia-smi memory fields return "Not Supported", fall
   back to system memory queries.
2. **ROCm VRAM/GTT overcounting.** The correct interpretation is still
   being debated in the ROCm community (ROCm/ROCm#6004). Our probe should
   report VRAM carve-out as the "guaranteed" ceiling and note that GTT
   extends it dynamically — don't sum them.
3. **`ioreg` output stability across macOS versions.** The
   `PerformanceStatistics` keys are not officially documented. They have
   been stable from macOS 11 through 26 but could change. Parse
   defensively, fall back to None for any missing key.
4. **Intel Macs (pre-Apple Silicon).** `ioreg -c AGXAccelerator` won't
   match on Intel Macs with AMD/NVIDIA dGPUs. The Apple Silicon probe
   should check `is_mac_apple_silicon()` first. Intel Macs fall through
   to the unsupported fallback (they're a shrinking population).
5. **Windows support.** Halbert currently runs on Linux and macOS. The
   universal-first design is ready for Windows (nvidia-smi is
   cross-platform, RTX Spark is Windows-on-ARM), but the dashboard server
   would need Windows platform support first. The probes are designed to
   work when that happens — no schema changes needed.
6. **PyObjC Metal framework as optional extra.** Must not break import of
   `gpu_tools` when absent. All `import Metal` calls inside try/except,
   function-level lazy, per the Subtractive Contract.
7. **Probe ordering and conflicts.** A machine could have both an NVIDIA
   discrete GPU and an integrated Intel GPU (common in laptops). The
   dispatcher should run all probes and return all detected GPUs, not
   just the first match. The existing code already handles multi-GPU
   via `lspci` — the probe registry extends this naturally.
8. **Frontend "no emoji" rule.** The existing `vendorIcons` uses emoji
   (🟢🔴🔵). New vendor entries should use lucide icons, not emoji. The
   existing emoji violations are a separate cleanup.

---

## 7. Suggested Implementation Order

1. **Phase 1** (probe registry + AMD + NVIDIA unified) — the structural
   refactor that makes everything else fit. Also fills the existing AMD
   stats gap. Linux-testable today.
2. **Phase 2** (Apple Silicon probe) — the probe that matters for this
   M1 Ultra development machine. Mac-testable today.
3. **Phase 3** (agent registration) — one-line guard removal. Unlocks AI
   self-awareness on all platforms.
4. **Phase 4** (frontend) — universal labels. The normalized schema makes
   this straightforward — it's label/icon work driven by
   `memory_architecture` and `compute_api`.
5. **Phase 5** (optional enrichments) — Metal API, powermetrics sudo, NPU,
   Qualcomm. Additive, no schema changes.

Phases 1-4 are the meaningful deliverable. Phase 5 is nice-to-haves.

---

## 8. AI Accelerators (TPUs / NPUs) — The Third Compute Class

The GPU is no longer the only AI-relevant accelerator on a machine. Home
Assistant servers commonly have a dedicated TPU add-on card for Frigate
NVR object detection, and modern SoCs ship with integrated NPUs. Halbert
already integrates with Frigate (see `routes/agent.py:292-297`,
`register_frigate_tools`), so awareness of these accelerators is directly
relevant.

### 8.1 The accelerator landscape

| Accelerator | Vendor | Form factor | Interface | Detection | Stats source | TOPS | Use case |
|-------------|--------|-------------|-----------|-----------|-------------|------|----------|
| Coral Edge TPU | Google | USB / M.2 / Mini PCIe | USB (`1a6e:089a`) or PCIe (`1ac1:089a`) | `lsusb` / `lspci` / `/dev/apex_*` | sysfs `temp` (millidegree C) | 4 | Frigate object detection |
| Hailo-8 / 8L | Hailo | M.2 (HAT for RPi) | PCIe (`1e60:2864` / `1e60:43a2`) | `lspci` / `hailortcli scan` | `hailortcli fw-control identify` + `benchmark` | 26 (Hailo-8) / 13 (8L) | Frigate, edge AI |
| Hailo-10H | Hailo | M.2 HAT+ (RPi 5) | PCIe (`hailo1x_pci` driver) | `lspci` / `hailortcli scan` | `hailortcli` (HailoRT 5.2+) | 40 | Frigate, LLM inference |
| MemryX MX3 | MemryX | M.2 | PCIe (`1ed9:*`) | `lspci` / `mxa-manager` | `acclBench` / `mxa-manager` | 26 | Frigate (newly supported) |
| Intel NPU | Intel | Integrated (Meteor/Arrow/Lunar/Panther Lake) | `/dev/accel/accel0` (`intel_vpu` driver) | `lsmod \| grep intel_vpu` / `/dev/accel/accel0` | `npu-monitor-tool` (sysfs, requires root) | 11-48 | OpenVINO, Windows Studio Effects |
| AMD XDNA NPU | AMD | Integrated (Strix Halo, Ryzen AI 300) | `/dev/accel/accel0` (xdna driver) | `lsmod` / `xrt-smi examine` | `xrt-smi` | 50 (Strix Halo) | ROCm, ONNX |
| Qualcomm Hexagon NPU | Qualcomm | Integrated (Snapdragon X) | Windows-on-ARM | Snapdragon Profiler / DirectML | Snapdragon Profiler | 45 | Windows Copilot+ |
| Apple Neural Engine | Apple | Integrated (Apple Silicon) | CoreML / ANE | Always present on Apple Silicon | `powermetrics --samplers ane_power` (sudo) | 11-38 | Apple Intelligence, CoreML |

### 8.2 Detection methods (verified from vendor docs)

#### Google Coral Edge TPU
- **PCIe/M.2:** `lspci -nn | grep 089a` (vendor `1ac1`, device `089a`).
  Device node: `/dev/apex_0` (driver: `apex` / `gasket`).
  Temperature: sysfs node, millidegree Celsius — exact path varies by
  carrier board. The `edgetpu-exporter` project reads it per-device.
- **USB:** `lsusb | grep 1a6e:089a` (shows as "Global Unichip Corp." until
  the Edge TPU runtime claims it, then `18d1:9302` "Google Inc.").
  **No temperature available on USB Coral** (per coral.ai docs and
  edgetpu-exporter: "there is presently no mechanism by which to obtain a
  temperature reading from USB-attached devices").
- **Driver check:** `lsmod | grep apex` (PCIe) or `lsmod | grep gasket`.
- **Runtime check:** `python3 -c "from pycoral.utils import edgetpu; print(edgetpu.list_edge_tpus())"` (if pycoral installed).

#### Hailo-8 / 8L / 10H
- **PCIe:** `lspci` shows "Co-processor: Hailo Technologies Ltd. Hailo-8
  AI Processor (rev 01)". Vendor ID `1e60`.
- **CLI:** `hailortcli scan` → lists devices ("Hailo-8L on PCIe slot ...").
  `hailortcli fw-control identify` → firmware version, serial, product.
  `hailortcli benchmark <model.hef>` → FPS, latency, power (W).
- **Driver:** `lsmod | grep hailo` (`hailo_pci` for Hailo-8/8L,
  `hailo1x_pci` for Hailo-10H). Device node: `/dev/hailo0`.
- **Power:** `hailortcli benchmark` reports "Power in streaming mode
  (average) = X W" — but only during an active benchmark, not idle
  monitoring. No continuous power stat.

#### MemryX MX3
- **PCIe:** `lspci | grep 1ed9` (vendor `1ed9`). Device node: `/dev/memx0`.
- **Driver:** `memx_cascade_plus_pcie` kernel module.
- **Manager:** `mxa-manager` service. `acclBench` for benchmarking.
- **Note:** Frigate added MX3 support in v0.17.1. Newly relevant.

#### Intel NPU (Meteor Lake / Arrow Lake / Lunar Lake / Panther Lake)
- **Device:** `/dev/accel/accel0` (driver: `intel_vpu` in kernel).
- **Driver check:** `lsmod | grep intel_vpu`.
- **PCI ID:** `8086:ad1d` (Arrow Lake NPU 3720). Other generations have
  different device IDs.
- **Monitoring:** `npu-monitor-tool` (Intel's open-source tool) reads
  utilization, power (W), temperature, frequency, bandwidth from sysfs
  (`/sys/class/intel_pmt/`). **Requires root.**
- **Software:** OpenVINO + Level Zero user-mode driver.

#### AMD XDNA NPU (Strix Halo / Ryzen AI 300)
- **Device:** `/dev/accel/accel0` (driver: `amdxdna` or `xdna`).
- **CLI:** `xrt-smi examine` (XRT tool) lists NPU devices and status.
- **Note:** This is the NPU *alongside* the Radeon 8060S iGPU on Strix
  Halo. Both are AI-relevant. The GPU runs LLMs; the NPU runs smaller
  inference (object detection, audio processing).

#### Apple Neural Engine (ANE)
- **Always present** on Apple Silicon (M1+). Not a separate device —
  it's a coprocessor on the SoC.
- **Monitoring:** `powermetrics --samplers ane_power` (requires sudo).
  Reports ANE frequency and estimated power.
- **Software:** CoreML, Apple Intelligence (FoundationModels).
- **Note:** The ANE is what runs Apple Intelligence on-device models.
  Tracking its utilization matters for understanding whether Apple
  Intelligence is active and how much headroom it has.

### 8.3 Normalized accelerator schema

Add a parallel `accelerators` list to the GPU info response, separate
from `gpus` but returned by the same `get_gpu_info()` call (or a new
`get_accelerator_info()` — see gap analysis below):

```python
{
    "accelerators": [
        {
            "type": "tpu" | "npu" | "ane",
            "vendor": "Google" | "Hailo" | "MemryX" | "Intel" | "AMD" | "Qualcomm" | "Apple",
            "model": "Coral Edge TPU" | "Hailo-8" | "Hailo-8L" | "Hailo-10H" | "MX3" | "Intel AI Boost NPU" | "AMD XDNA NPU" | "Hexagon NPU" | "Apple Neural Engine",
            "form_factor": "usb" | "m.2" | "mini_pcie" | "pcie" | "integrated",
            "device_node": "/dev/apex_0" | "/dev/hailo0" | "/dev/memx0" | "/dev/accel/accel0" | null,
            "tops": float | null,              # peak INT8 throughput
            "driver_loaded": bool,
            "driver_name": str | null,         # "apex" | "hailo_pci" | "memx_cascade_plus_pcie" | "intel_vpu" | "amdxdna"
            "driver_version": str | null,
            "firmware_version": str | null,
            "temperature_c": float | null,     # where available
            "utilization_percent": float | null, # where available (Intel NPU, Hailo)
            "power_draw_w": float | null,      # where available (Hailo during active use, Intel NPU)
            "runtime_available": bool,         # edgetpu runtime / hailort / openvino / etc.
            "runtime_version": str | null,
            "status": "active" | "idle" | "missing_driver" | "missing_runtime" | "not_detected",
        }
    ]
}
```

### 8.4 Why this matters for Halbert

1. **Frigate integration:** Halbert already registers Frigate tools
   (`register_frigate_tools` in `routes/agent.py:294`). If the AI knows a
   Coral TPU or Hailo-8 is present and active, it can reason about Frigate
   detection capacity — "you have 1 Coral TPU, which can handle ~100 FPS
   of object detection across your cameras."
2. **Model routing:** On Strix Halo, the AI could route small inference
   (object detection, embeddings) to the NPU and large inference (LLM)
   to the GPU. On Apple Silicon, route Apple Intelligence tasks to the
   ANE and MLX tasks to the GPU.
3. **Self-awareness:** "I have a 26-TOPS Hailo-8 accelerator available
   for edge AI tasks, in addition to my 128GB unified-memory GPU for LLM
   inference." This is the full picture of the machine's AI capacity.
4. **Health monitoring:** TPUs run hot and can throttle. The Coral PCIe
   driver has DFS (dynamic frequency scaling) that throttles at trip
   points. Monitoring temperature lets the AI warn about thermal
   throttling before it degrades Frigate detection performance.
5. **Driver issues:** A common HA support scenario is "Frigigate not
   detecting objects" → the Coral driver isn't loaded, or the Hailo
   firmware didn't initialize. The AI can check `driver_loaded` and
   `runtime_available` to diagnose this immediately.

---

## 9. Gap Analysis — What's Missing in the Current Design

### 9.1 Gaps in the existing GPU tools (`gpu_tools.py`)

| Gap | Severity | Description |
|-----|----------|-------------|
| **AMD live stats never queried** | High | `lspci` detects AMD GPUs but `rocm-smi` is never called. No utilization, memory, temp, or power for AMD cards on Linux. The `_probe_amd_discrete()` in Phase 1 fixes this. |
| **No unified-memory concept** | High | The schema assumes discrete VRAM. All four unified-memory architectures (Apple, RTX Spark, Strix Halo, Snapdragon) are misrepresented or invisible. The `memory_architecture` field in Phase 1 fixes this. |
| **NVIDIA unified memory blind spot** | High | `nvidia-smi` reports "Memory-Usage: Not Supported" on RTX Spark. The current code would parse this as null/zero. Need the `_probe_nvidia_unified()` fallback to system memory queries. |
| **No Windows support** | Medium | `get_gpu_info()` hard-gates on Linux. nvidia-smi is cross-platform; the probe could work on Windows if Halbert's dashboard server supported Windows. The probe design is Windows-ready; the platform support is a separate gap. |
| **No NPU/TPU awareness** | High | No concept of AI accelerators beyond GPUs. Section 8 above. |
| **`get_gpu_architecture()` missing modern entries** | Low | No Apple Silicon (M1-M6), no RDNA 3.5, no Blackwell (RTX 50 / Spark), no Lunar Lake graphics. |
| **`get_deep_system_context()` Linux-only** | Medium | No macOS equivalent (Metal version, MLX, PyTorch MPS). No Windows equivalent (DirectML, WSL2 CUDA). |
| **No GPU process attribution** | Low | `nvidia-smi` can show per-process GPU memory/compute (`--query-compute-apps`). Not currently queried. Would let the AI say "Ollama is using 8GB of VRAM" vs just "8GB used." |
| **No historical stats / trends** | Low | Only point-in-time snapshots. No time-series of utilization/memory. The 5s poll in the frontend is the only "trend." A ring buffer or periodic snapshot would enable "GPU has been at 90% for 10 minutes" alerts. |

### 9.2 Gaps in the discovery scanner system

| Gap | Severity | Description |
|-----|----------|-------------|
| **No GPU scanner** | Medium | `DiscoveryType.GPU` exists in the schema (line 44) but no scanner produces GPU discoveries. GPU info lives in `gpu_tools.py` (agent tools + HTTP routes), completely separate from the discovery engine. A `GpuScanner` could surface GPU discoveries (driver issues, thermal warnings, VRAM pressure) in the discovery feed alongside other hardware. |
| **No AI accelerator scanner** | High | No scanner detects Coral TPUs, Hailo cards, Intel NPUs, etc. These are HA-relevant hardware that the discovery engine should find. An `AiAcceleratorScanner` (implementing `BaseScanner`, producing `DiscoveryType.HARDWARE`) would fit the existing pattern perfectly — same shape as `UsbScanner` and `ThermalScanner`. |
| **Thermal scanner doesn't read GPU/TPU temps** | Medium | `ThermalScanner` (Linux) reads hwmon/thermal zones but doesn't specifically query `nvidia-smi` GPU temp or Coral sysfs temp. `MacThermalScanner` reads `powermetrics` GPU die temp but only with sudo. The GPU tools and thermal scanner duplicate effort without sharing. |

### 9.3 Gaps in the frontend

| Gap | Severity | Description |
|-----|----------|-------------|
| **No accelerator display** | High | `GPU.tsx` only renders GPU cards. No UI for TPUs/NPUs. Need an "AI Accelerators" section or a separate tab. |
| **NVIDIA-centric labels** | Medium | "VRAM", "CUDA", "NVIDIA Drivers" hardcoded. Need `memory_architecture`-driven labels. |
| **No NPU utilization display** | Medium | Strix Halo and Snapdragon have NPUs that matter for AI. No UI for NPU load/temp/power. |
| **No process attribution** | Low | Can't see which process is using the GPU. |

### 9.4 Architectural gap: two parallel hardware systems

The codebase has **two separate hardware detection systems** that don't
talk to each other:

1. **`tools/gpu_tools.py`** — agent tools + HTTP routes. Point-in-time
   queries. Used by the GPU tab and the AI. No persistence, no discovery
   feed integration.
2. **`discovery/scanners/`** — the discovery engine. Periodic scans,
   persisted discoveries, rendered in the discovery feed. Has
   `DiscoveryType.GPU` and `DiscoveryType.HARDWARE` but no GPU/accelerator
   scanner is registered.

These should converge. The probe functions in `gpu_tools.py` are the right
low-level detection layer. A `GpuScanner` and `AiAcceleratorScanner` in
the discovery system would call those probes and produce `Discovery`
objects for the feed — same pattern as `ThermalScanner` calling hwmon and
`UsbScanner` calling `lsusb`.

**Proposed convergence:**
- `gpu_tools.py` probes stay as the low-level detection layer (called by
  agent tools + HTTP routes for live stats).
- New `discovery/scanners/gpu.py` → `GpuScanner` calls `get_gpu_info()`
  and produces discoveries for driver issues, thermal warnings, VRAM
  pressure.
- New `discovery/scanners/accelerator.py` → `AiAcceleratorScanner` calls
  the new `get_accelerator_info()` and produces discoveries for TPU/NPU
  presence, driver status, thermal warnings.
- The GPU tab keeps polling `/api/gpu/info` for live stats (5s interval).
- The discovery feed shows persistent hardware state + issues (slower
  scan interval, e.g. 60s).

---

## 10. Revised Implementation Plan

### Phase 1 — Probe registry + unified memory + AMD stats (Linux)

Same as before: refactor `get_gpu_info()` into probe dispatcher, add
`memory_architecture` field, add `_probe_amd_discrete()`,
`_probe_nvidia_unified()`, `_probe_amd_unified()`.

### Phase 2 — Apple Silicon probe

Same as before: `_probe_apple_silicon()` using `ioreg` + `system_profiler`.

### Phase 3 — AI accelerator detection

**New phase.** Add `get_accelerator_info()` to `gpu_tools.py` (or a new
`tools/accelerator_tools.py`) with probes for:
- `_probe_coral_edgetpu()` — `lsusb` + `lspci` + sysfs temp + `/dev/apex_*`
- `_probe_hailo()` — `lspci` + `hailortcli scan` + `hailortcli fw-control identify`
- `_probe_memryx()` — `lspci` + `/dev/memx0` + `mxa-manager` status
- `_probe_intel_npu()` — `lsmod | grep intel_vpu` + `/dev/accel/accel0`
- `_probe_amd_npu()` — `lsmod | grep amdxdna` + `xrt-smi examine`
- `_probe_apple_ane()` — always present on Apple Silicon; power via
  `powermetrics --samplers ane_power` (sudo)

Register an `accelerator_info` agent tool alongside `gpu_info`.

### Phase 4 — Agent tool registration (all platforms)

Remove the Linux-only guard. Register both `gpu_tools` and
`accelerator_tools` unconditionally.

### Phase 5 — Frontend: universal GPU + accelerator display

- GPU cards: `memory_architecture`-driven labels, `compute_api` column,
  core count, unified memory display.
- New "AI Accelerators" section below GPU cards: TPU/NPU cards with
  TOPS, driver status, temperature, utilization.
- NPU section for integrated NPUs (Strix Halo, Snapdragon, Intel).

### Phase 6 — Discovery scanner convergence

- `discovery/scanners/gpu.py` → `GpuScanner` producing
  `DiscoveryType.GPU` discoveries.
- `discovery/scanners/accelerator.py` → `AiAcceleratorScanner`
  producing `DiscoveryType.HARDWARE` discoveries.
- Register both in the discovery engine's default scanners.

### Phase 7 — Optional enrichments

- Metal API (PyObjC) for precise Apple Silicon memory.
- `powermetrics` sudo for macOS GPU/ANE power + temp.
- `npu-monitor-tool` integration for Intel NPU stats.
- GPU process attribution (`nvidia-smi --query-compute-apps`).
- Historical stats ring buffer.

---

## 11. Files Touched (Phases 1-6)

| File | Change |
|------|--------|
| `halbert_core/halbert_core/tools/gpu_tools.py` | Probe dispatcher refactor; `_probe_nvidia_discrete()`, `_probe_nvidia_unified()`, `_probe_amd_discrete()`, `_probe_amd_unified()`, `_probe_apple_silicon()`; `memory_architecture` + normalized fields; Apple arch entries; `_get_apple_system_context()`. |
| `halbert_core/halbert_core/tools/accelerator_tools.py` | **NEW.** `get_accelerator_info()` + probes for Coral, Hailo, MemryX, Intel NPU, AMD NPU, Apple ANE. Agent tool schemas + handlers. |
| `halbert_core/tests/test_gpu_tools.py` | Mock each probe's commands; test dispatcher; test `memory_architecture` per probe; test AMD stats; test Apple Silicon; test NVIDIA unified fallback. |
| `halbert_core/tests/test_accelerator_tools.py` | **NEW.** Mock `lsusb`/`lspci`/`hailortcli`/sysfs; test each accelerator probe. |
| `halbert_core/halbert_core/dashboard/routes/agent.py` | Remove Linux-only guard; register `gpu_tools` + `accelerator_tools` unconditionally. |
| `halbert_core/halbert_core/dashboard/routes/gpu.py` | Add `/api/gpu/accelerators` endpoint wrapping `get_accelerator_info()`. |
| `halbert_core/halbert_core/dashboard/frontend/src/pages/GPU.tsx` | `memory_architecture`-driven labels; `compute_api` column; core count; unified memory; accelerator section; NPU display; lucide icons. |
| `halbert_core/halbert_core/discovery/scanners/gpu.py` | **NEW.** `GpuScanner(BaseScanner)` → `DiscoveryType.GPU`. Calls `get_gpu_info()`, produces discoveries for driver issues, thermal, VRAM pressure. |
| `halbert_core/halbert_core/discovery/scanners/accelerator.py` | **NEW.** `AiAcceleratorScanner(BaseScanner)` → `DiscoveryType.HARDWARE`. Calls `get_accelerator_info()`, produces discoveries for TPU/NPU presence + status. |
| `halbert_core/halbert_core/discovery/engine.py` | Register `GpuScanner` + `AiAcceleratorScanner` in `_register_default_scanners()`. |

No new hard dependencies for Phases 1-6. Phase 7 adds optional extras.

---

## 12. Sources

- NVIDIA RTX Spark announcement (May 31, 2026): nvidianews.nvidia.com
- NVIDIA DGX Spark User Guide (nvidia-smi "Memory-Usage: Not Supported"
  on unified memory): docs.nvidia.com/dgx/dgx-spark/dgx-spark.pdf
- ASUS ProArt P16/P14/GR1X RTX Spark announcement (IFA 2026, Sept 2):
  press.asus.com
- Tom's Hardware RTX Spark N1X specs: tomshardware.com
- AMD ROCm Strix Halo optimization guide: rocm.docs.amd.com
- AMD ROCm VRAM/GTT dual-pool issue: github.com/ROCm/ROCm/issues/6004
- AMD Strix Halo VRAM allocation analysis: aliteq.com
- Qualcomm Snapdragon X Elite product brief: qualcomm.com
- Frigate object detector docs (Coral, Hailo, MemryX, DeGirum):
  github.com/blakeblackshear/frigate/blob/v0.17.1/docs/docs/configuration/object_detectors.md
- Google Coral PCIe temperature/DFS: coral.ai/docs/pcie-parameters
- EdgeTPU Prometheus exporter (temp metrics, USB temp limitation):
  github.com/just5ky/edgetpu-exporter
- Hailo community (lspci detection, hailortcli scan/identify):
  community.hailo.ai
- Hailo-8 benchmark (power during streaming): trac.gateworks.com/wiki/hailoai
- Hailo-10H Frigate add-on (HailoRT 5.2, hailo1x_pci driver):
  github.com/mikehailodev/frigate-hass-addons-h10
- MemryX MX3 driver + detection: developer.memryx.com, github.com/memryx/mx3_driver_pub
- Intel NPU device plugin (Meteor/Arrow/Lunar/Panther Lake detection):
  intel.github.io/intel-device-plugins-for-kubernetes
- Intel npu-monitor-tool (utilization, power, temp, requires root):
  github.com/open-edge-platform/edge-ai-libraries
- Intel linux-npu-driver releases: github.com/intel/linux-npu-driver
- Intel NPU tools (Arrow Lake, PCI ID 8086:ad1d, OpenVINO):
  github.com/etreby/intel-npu-tools
- Verified on this machine: Apple M1 Ultra, 128GB, 48 GPU cores,
  macOS 26.5.1, `ioreg` + `system_profiler` output captured live.
- Halbert codebase: `routes/agent.py:292-297` (Frigate tool registration),
  `discovery/schema.py:44` (`DiscoveryType.GPU` exists, no scanner),
  `discovery/scanners/base.py` (BaseScanner pattern),
  `discovery/scanners/thermal.py` + `macos/thermal.py` (thermal scanning
  pattern, powermetrics sudo approach).

| File | Change |
|------|--------|
| `halbert_core/halbert_core/tools/gpu_tools.py` | Refactor `get_gpu_info()` into probe dispatcher; add `_probe_nvidia_discrete()`, `_probe_nvidia_unified()`, `_probe_amd_discrete()`, `_probe_amd_unified()`, `_probe_apple_silicon()`; add `memory_architecture` + normalized fields; add Apple arch entries; add `_get_apple_system_context()`; update tool schema descriptions. |
| `halbert_core/tests/test_gpu_tools.py` | Mock each probe's command outputs; test dispatcher; test each probe returns correct `memory_architecture`; test AMD stats (new); test Apple Silicon stats (new); test NVIDIA unified fallback when memory = "Not Supported". |
| `halbert_core/halbert_core/dashboard/routes/agent.py` | Remove the `if _platform.system() == "Linux"` guard around `register_gpu_tools` — register unconditionally. |
| `halbert_core/halbert_core/dashboard/frontend/src/pages/GPU.tsx` | Read `memory_architecture` for labels (VRAM / Unified Memory / System RAM); read `compute_api` for compute column (CUDA / Metal / ROCm / DirectML); show `core_count`, `unified_memory_gb`, `gpu_memory_ceiling_gb`; vendor-specific sections (Apple: hide role selector + driver links; AMD: show ROCm); NPU display; lucide icons (no emoji). |

No new hard dependencies required for Phases 1-4. Phase 5 adds optional
extras (`pyobjc-framework-Metal`, `xrt-smi`).

---

## 9. Sources

- NVIDIA RTX Spark announcement (May 31, 2026): nvidianews.nvidia.com
- NVIDIA DGX Spark User Guide (nvidia-smi "Memory-Usage: Not Supported"
  on unified memory): docs.nvidia.com/dgx/dgx-spark/dgx-spark.pdf
- ASUS ProArt P16/P14/GR1X RTX Spark announcement (IFA 2026, Sept 2):
  press.asus.com
- Tom's Hardware RTX Spark N1X specs: tomshardware.com
- AMD ROCm Strix Halo optimization guide: rocm.docs.amd.com
- AMD ROCm VRAM/GTT dual-pool issue: github.com/ROCm/ROCm/issues/6004
- AMD Strix Halo VRAM allocation analysis: aliteq.com
- Qualcomm Snapdragon X Elite product brief: qualcomm.com
- Verified on this machine: Apple M1 Ultra, 128GB, 48 GPU cores,
  macOS 26.5.1, `ioreg` + `system_profiler` output captured live.
