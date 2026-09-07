# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
GPU Tools

GPU hardware detection, deep system context gathering, and driver
information search, shared between the dashboard routes and the agent.

The detection functions moved here from dashboard/routes/gpu.py so the
agent can call them as tools during GPU diagnosis (the specialist model
decides what to gather) while the monitoring endpoints keep calling the
same functions directly. Tool registration follows the executor pattern
(register_ha_tools / register_system_tools).

GPU-1 (2026-09-07): refactored from a single Linux/NVIDIA path into a
**probe dispatcher**. Each probe enriches a vendor's GPUs with live
stats and classifies the memory architecture (``discrete`` /
``unified`` / ``integrated``). The dispatcher runs all applicable probes
and merges results. This handles the 2026 unified-memory landscape
(Apple Silicon, NVIDIA RTX Spark, AMD Strix Halo, Qualcomm Snapdragon)
without per-platform special cases at the call site.
"""

from __future__ import annotations

import json
import platform
import re
import subprocess
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("halbert.tools.gpu")


# ─────────────────────────────────────────────────────────────────────────────
# GPU Role Configuration (display vs compute)
# ─────────────────────────────────────────────────────────────────────────────

def _get_gpu_config_path():
    """Get path to GPU config file."""
    try:
        from ..utils.platform import get_config_dir
        return get_config_dir() / 'gpu_config.yml'
    except Exception:
        return None


def load_gpu_config() -> Dict[str, Any]:
    """Load GPU configuration (roles, etc.)."""
    try:
        import yaml
        config_path = _get_gpu_config_path()
        if not config_path or not config_path.exists():
            return {'gpu_roles': {}}

        with open(config_path, 'r') as f:
            return yaml.safe_load(f) or {'gpu_roles': {}}
    except Exception as e:
        logger.warning(f"Failed to load GPU config: {e}")
        return {'gpu_roles': {}}


def save_gpu_config(config: Dict[str, Any]) -> bool:
    """Save GPU configuration."""
    try:
        import yaml
        config_path = _get_gpu_config_path()
        if not config_path:
            return False

        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, 'w') as f:
            yaml.dump(config, f, default_flow_style=False)
        return True
    except Exception as e:
        logger.warning(f"Failed to save GPU config: {e}")
        return False


def get_gpu_role(pci_id: str) -> str:
    """Get role for a specific GPU. Returns 'auto', 'display', or 'compute'."""
    config = load_gpu_config()
    return config.get('gpu_roles', {}).get(pci_id, 'auto')


def set_gpu_role(pci_id: str, role: str) -> bool:
    """Set role for a specific GPU."""
    if role not in ('auto', 'display', 'compute'):
        return False

    config = load_gpu_config()
    if 'gpu_roles' not in config:
        config['gpu_roles'] = {}

    config['gpu_roles'][pci_id] = role
    return save_gpu_config(config)


def run_command(cmd: List[str], timeout: int = 10) -> Optional[str]:
    """Run a command and return stdout, or None on error."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return result.stdout.strip() if result.returncode == 0 else None
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Normalized GPU dict helpers (GPU-1)
# ─────────────────────────────────────────────────────────────────────────────

def _make_gpu_dict(vendor: str, model: str, pci_id: str) -> Dict[str, Any]:
    """Create a GPU dict with all fields (legacy + GPU-1 normalized)."""
    return {
        # Legacy fields (backward compatible)
        "vendor": vendor,
        "model": model,
        "pci_id": pci_id,
        "vram_mb": None,
        "driver_version": None,
        "driver_type": None,
        "cuda_version": None,
        "temperature_c": None,
        "power_draw_w": None,
        "power_limit_w": None,
        "utilization_percent": None,
        "memory_used_mb": None,
        "memory_total_mb": None,
        "role": get_gpu_role(pci_id),
        # GPU-1 normalized fields
        "memory_architecture": "discrete",  # default; probes override
        "unified_memory_gb": None,
        "gpu_memory_ceiling_gb": None,
        "gpu_memory_in_use_gb": None,
        "core_count": None,
        "compute_api": None,
        "memory_source_label": "VRAM",
    }


def _normalize_gpu(gpu: Dict[str, Any]) -> None:
    """Populate normalized fields from legacy fields if not already set.

    Called after each probe enriches the GPU dict. Ensures the normalized
    fields are consistent with the legacy fields for backward compatibility.
    """
    arch = gpu.get("memory_architecture", "discrete")
    if arch == "discrete":
        gpu.setdefault("memory_source_label", "VRAM")
        if gpu.get("memory_total_mb") and not gpu.get("gpu_memory_ceiling_gb"):
            gpu["gpu_memory_ceiling_gb"] = round(gpu["memory_total_mb"] / 1024, 1)
        if gpu.get("memory_used_mb") and not gpu.get("gpu_memory_in_use_gb"):
            gpu["gpu_memory_in_use_gb"] = round(gpu["memory_used_mb"] / 1024, 1)
    elif arch == "unified":
        gpu.setdefault("memory_source_label", "Unified Memory")
    elif arch == "integrated":
        gpu.setdefault("memory_source_label", "System RAM")

    # Set compute_api from driver_type if not explicitly set
    if not gpu.get("compute_api"):
        dt = gpu.get("driver_type") or ""
        if "nvidia" in dt:
            gpu["compute_api"] = "cuda"
        elif "amdgpu" in dt or "radeon" in dt:
            gpu["compute_api"] = "rocm"
        elif "i915" in dt:
            gpu["compute_api"] = "opencl"
        elif "metal" in dt:
            gpu["compute_api"] = "metal"


# ─────────────────────────────────────────────────────────────────────────────
# Hardware detection via lspci (Linux)
# ─────────────────────────────────────────────────────────────────────────────

def _detect_gpus_via_lspci() -> tuple[List[Dict], bool, bool, bool]:
    """Detect GPUs via lspci. Returns (gpus, has_nvidia, has_amd, has_intel).

    Each GPU dict is initialized with vendor, model, pci_id and default
    values. Probes enrich these with live stats.
    """
    gpus: List[Dict] = []
    has_nvidia = False
    has_amd = False
    has_intel = False

    lspci_output = run_command(["lspci", "-nn"])
    if not lspci_output:
        return gpus, has_nvidia, has_amd, has_intel

    for line in lspci_output.split("\n"):
        if "VGA" not in line and "3D controller" not in line and "Display controller" not in line:
            continue
        # Example: "01:00.0 VGA compatible controller [0300]: NVIDIA Corporation GA106 [GeForce RTX 3060] [10de:2503] (rev a1)"
        pci_match = re.match(
            r'^([0-9a-f:.]+)\s+(.+?):\s+(.+?)(?:\s+\[([0-9a-f:]+)\])?(?:\s+\(rev.*\))?$',
            line, re.I,
        )
        if not pci_match:
            continue
        pci_id = pci_match.group(1)
        vendor_model = pci_match.group(3)

        vendor = "Unknown"
        vm_lower = vendor_model.lower()
        if "nvidia" in vm_lower:
            vendor = "NVIDIA"
            has_nvidia = True
        elif "amd" in vm_lower or "radeon" in vm_lower:
            vendor = "AMD"
            has_amd = True
        elif "intel" in vm_lower:
            vendor = "Intel"
            has_intel = True

        gpus.append(_make_gpu_dict(vendor, vendor_model, pci_id))

    return gpus, has_nvidia, has_amd, has_intel


# ─────────────────────────────────────────────────────────────────────────────
# Probes — each enriches GPU dicts with vendor-specific live stats
# ─────────────────────────────────────────────────────────────────────────────

def _probe_nvidia_discrete(gpus: List[Dict], issues: List[str]) -> bool:
    """Enrich NVIDIA GPUs with nvidia-smi live stats (discrete GPUs).

    Returns True if nvidia-smi was available (even if memory fields are
    "Not Supported" — that signals a unified-memory NVIDIA device like
    RTX Spark, handled by _probe_nvidia_unified).
    """
    nvidia_smi = run_command([
        "nvidia-smi",
        "--query-gpu=name,driver_version,memory.total,memory.used,temperature.gpu,power.draw,power.limit,utilization.gpu",
        "--format=csv,noheader,nounits",
    ])
    if not nvidia_smi:
        return False

    nvidia_gpus = [g for g in gpus if g["vendor"] == "NVIDIA"]
    for i, line in enumerate(nvidia_smi.split("\n")):
        if not line.strip():
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 8 or i >= len(nvidia_gpus):
            continue
        gpu = nvidia_gpus[i]
        gpu["driver_version"] = parts[1] if parts[1] != "[N/A]" else None
        gpu["driver_type"] = "nvidia"

        # RTX Spark / unified memory: nvidia-smi reports "Not Supported"
        # for memory fields. Detect this and mark for the unified probe.
        mem_total_raw = parts[2]
        if mem_total_raw in ("[N/A]", "Not Supported", "N/A", ""):
            gpu["memory_architecture"] = "unified"
            gpu["compute_api"] = "cuda"
            # Util/temp/power still work on unified NVIDIA
            try:
                gpu["temperature_c"] = int(float(parts[4])) if parts[4] != "[N/A]" else None
                gpu["power_draw_w"] = float(parts[5]) if parts[5] != "[N/A]" else None
                gpu["power_limit_w"] = float(parts[6]) if parts[6] != "[N/A]" else None
                gpu["utilization_percent"] = int(float(parts[7])) if parts[7] != "[N/A]" else None
            except (ValueError, IndexError):
                pass
            continue

        gpu["memory_architecture"] = "discrete"
        try:
            gpu["memory_total_mb"] = int(float(mem_total_raw))
            gpu["vram_mb"] = gpu["memory_total_mb"]
            gpu["memory_used_mb"] = int(float(parts[3]))
            gpu["temperature_c"] = int(float(parts[4])) if parts[4] != "[N/A]" else None
            gpu["power_draw_w"] = float(parts[5]) if parts[5] != "[N/A]" else None
            gpu["power_limit_w"] = float(parts[6]) if parts[6] != "[N/A]" else None
            gpu["utilization_percent"] = int(float(parts[7])) if parts[7] != "[N/A]" else None
        except (ValueError, IndexError):
            pass

    # CUDA version via nvcc
    nvcc_output = run_command(["nvcc", "--version"])
    if nvcc_output:
        cuda_match = re.search(r"release (\d+\.\d+)", nvcc_output)
        if cuda_match:
            for gpu in nvidia_gpus:
                gpu["cuda_version"] = cuda_match.group(1)

    return True


def _probe_nvidia_unified(gpus: List[Dict], issues: List[str]) -> None:
    """Fill memory fields for NVIDIA unified-memory GPUs (RTX Spark).

    nvidia-smi reports "Not Supported" for memory on these devices.
    Fall back to system memory queries. The GPU working-set ceiling is
    ~75% of total unified memory (NVIDIA's documented fraction for Spark,
    matching Apple's UNIFIED_MEMORY_FRACTION in hardware_detector.py).
    """
    nvidia_unified = [g for g in gpus if g["vendor"] == "NVIDIA" and g.get("memory_architecture") == "unified"]
    if not nvidia_unified:
        return

    # System memory total (Linux: /proc/meminfo; WSL2 also has this)
    meminfo = run_command(["cat", "/proc/meminfo"])
    mem_total_kb = None
    mem_avail_kb = None
    if meminfo:
        for line in meminfo.split("\n"):
            if line.startswith("MemTotal:"):
                mem_total_kb = int(line.split()[1])
            elif line.startswith("MemAvailable:"):
                mem_avail_kb = int(line.split()[1])

    if mem_total_kb:
        unified_gb = mem_total_kb // (1024 * 1024)
        ceiling_gb = round(unified_gb * 0.75, 1)
        for gpu in nvidia_unified:
            gpu["unified_memory_gb"] = unified_gb
            gpu["gpu_memory_ceiling_gb"] = ceiling_gb
            gpu["memory_total_mb"] = int(ceiling_gb * 1024)
            gpu["vram_mb"] = gpu["memory_total_mb"]
            if mem_avail_kb:
                used_gb = round((mem_total_kb - mem_avail_kb) / (1024 * 1024), 1)
                gpu["gpu_memory_in_use_gb"] = used_gb
                gpu["memory_used_mb"] = int(used_gb * 1024)
            gpu["compute_api"] = "cuda"
            gpu["memory_source_label"] = "Unified Memory"


def _probe_nvidia_nouveau(gpus: List[Dict], issues: List[str]) -> None:
    """Detect nouveau driver for NVIDIA GPUs without nvidia-smi."""
    nvidia_gpus = [g for g in gpus if g["vendor"] == "NVIDIA" and not g.get("driver_type")]
    if not nvidia_gpus:
        return
    lsmod = run_command(["lsmod"])
    if lsmod and "nouveau" in lsmod:
        for gpu in nvidia_gpus:
            gpu["driver_type"] = "nouveau"
        issues.append(
            "NVIDIA GPU using open-source nouveau driver. "
            "Consider installing proprietary drivers for better performance."
        )


def _probe_amd_discrete(gpus: List[Dict], issues: List[str]) -> None:
    """Enrich AMD GPUs with rocm-smi live stats (discrete GPUs).

    Fills the pre-existing gap where AMD GPUs were detected via lspci
    but never queried for utilization, memory, temperature, or power.
    Also detects Strix Halo (unified) and delegates to _probe_amd_unified.
    """
    amd_gpus = [g for g in gpus if g["vendor"] == "AMD"]
    if not amd_gpus:
        return

    # Detect driver via lsmod
    lsmod = run_command(["lsmod"])
    if lsmod:
        if "amdgpu" in lsmod:
            for gpu in amd_gpus:
                gpu["driver_type"] = "amdgpu"
        elif "radeon" in lsmod:
            for gpu in amd_gpus:
                gpu["driver_type"] = "radeon"
            issues.append(
                "AMD GPU using legacy radeon driver. "
                "Consider amdgpu for newer GPUs."
            )

    # rocm-smi for live stats
    rocm_smi = run_command([
        "rocm-smi",
        "--showuse",
        "--showtemp",
        "--showpower",
        "--showclocks",
        "--json",
    ])
    if not rocm_smi:
        # rocm-smi not available — try sysfs for VRAM (amdgpu)
        _probe_amd_sysfs(amd_gpus)
        return

    try:
        data = json.loads(rocm_smi)
    except (json.JSONDecodeError, ValueError):
        _probe_amd_sysfs(amd_gpus)
        return

    # rocm-smi --json keys are like "GPU 0 [GPU 0]": { ... }
    for i, gpu in enumerate(amd_gpus):
        key = f"GPU {i}"
        # rocm-smi json format varies; try common key patterns
        gpu_data = None
        for k, v in data.items():
            if k.startswith(key) or (isinstance(v, dict) and f"card {i}" in k.lower()):
                gpu_data = v
                break
        if not gpu_data:
            continue

        # Parse rocm-smi JSON fields (names vary by version)
        def _get(fields):
            for f in fields:
                if f in gpu_data:
                    val = gpu_data[f]
                    if val not in ("N/A", "[N/A]", "", None):
                        return val
            return None

        try:
            util = _get(["GPU use (%)", "GPU-0 use (%)", "GPU use"])
            if util:
                gpu["utilization_percent"] = int(float(str(util).replace("%", "").strip()))
        except (ValueError, TypeError):
            pass

        try:
            temp = _get(["Temperature (C)", "GPU-0 temp (C)", "Temperature"])
            if temp:
                gpu["temperature_c"] = int(float(str(temp).strip()))
        except (ValueError, TypeError):
            pass

        try:
            power = _get(["Average Graphics Package Power (W)", "GPU-0 power (W)", "Power"])
            if power:
                gpu["power_draw_w"] = float(str(power).replace("W", "").strip())
        except (ValueError, TypeError):
            pass

        # Memory — check for unified memory indicators (Strix Halo)
        vram_total = _get(["VRAM Total Memory (B)", "Memory total"])
        vram_used = _get(["VRAM Used Memory (B)", "Memory used"])
        gtt_total = _get(["GTT Total Memory (B)", "GTT total"])

        if gtt_total:
            # Strix Halo: VRAM + GTT pools share physical memory.
            # Report VRAM carve-out as the guaranteed ceiling, not the sum.
            gpu["memory_architecture"] = "unified"
            gpu["compute_api"] = "rocm"
            gpu["memory_source_label"] = "Unified Memory"
            try:
                vram_bytes = int(str(vram_total).replace(",", "").strip()) if vram_total else 0
                gpu["gpu_memory_ceiling_gb"] = round(vram_bytes / (1024 ** 3), 1)
                gpu["memory_total_mb"] = int(vram_bytes / (1024 ** 2))
                gpu["vram_mb"] = gpu["memory_total_mb"]
            except (ValueError, TypeError):
                pass
            try:
                used_bytes = int(str(vram_used).replace(",", "").strip()) if vram_used else 0
                gpu["gpu_memory_in_use_gb"] = round(used_bytes / (1024 ** 3), 1)
                gpu["memory_used_mb"] = int(used_bytes / (1024 ** 2))
            except (ValueError, TypeError):
                pass
            # Total system memory from /proc/meminfo
            meminfo = run_command(["cat", "/proc/meminfo"])
            if meminfo:
                for line in meminfo.split("\n"):
                    if line.startswith("MemTotal:"):
                        gpu["unified_memory_gb"] = int(line.split()[1]) // (1024 * 1024)
                        break
        elif vram_total:
            # Discrete AMD GPU
            gpu["memory_architecture"] = "discrete"
            try:
                vram_bytes = int(str(vram_total).replace(",", "").strip())
                gpu["memory_total_mb"] = int(vram_bytes / (1024 ** 2))
                gpu["vram_mb"] = gpu["memory_total_mb"]
            except (ValueError, TypeError):
                pass
            try:
                used_bytes = int(str(vram_used).replace(",", "").strip()) if vram_used else 0
                gpu["memory_used_mb"] = int(used_bytes / (1024 ** 2))
            except (ValueError, TypeError):
                pass


def _probe_amd_sysfs(amd_gpus: List[Dict]) -> None:
    """Fallback: read AMD GPU memory from sysfs (/sys/class/drm).

    Used when rocm-smi is not installed. The amdgpu driver exposes
    mem_info_vram_total and mem_info_vram_used in bytes.
    """
    import glob
    for gpu in amd_gpus:
        # Try to find the matching drm card — we don't have a perfect
        # pci_id → cardN mapping, so try all cards and use the first
        # that has VRAM info.
        for vram_path in sorted(glob.glob("/sys/class/drm/card*/device/mem_info_vram_total")):
            try:
                with open(vram_path) as f:
                    vram_bytes = int(f.read().strip())
                gpu["memory_total_mb"] = int(vram_bytes / (1024 ** 2))
                gpu["vram_mb"] = gpu["memory_total_mb"]
                gpu["memory_architecture"] = "discrete"
                # Read used
                used_path = vram_path.replace("vram_total", "vram_used")
                try:
                    with open(used_path) as f:
                        used_bytes = int(f.read().strip())
                    gpu["memory_used_mb"] = int(used_bytes / (1024 ** 2))
                except (OSError, ValueError):
                    pass
                break
            except (OSError, ValueError):
                continue


def _probe_intel(gpus: List[Dict], issues: List[str]) -> None:
    """Detect Intel GPU driver."""
    intel_gpus = [g for g in gpus if g["vendor"] == "Intel"]
    if not intel_gpus:
        return
    lsmod = run_command(["lsmod"])
    if lsmod and "i915" in lsmod:
        for gpu in intel_gpus:
            gpu["driver_type"] = "i915"
            gpu["memory_architecture"] = "integrated"
            gpu["memory_source_label"] = "System RAM"


# ─────────────────────────────────────────────────────────────────────────────
# Dispatcher
# ─────────────────────────────────────────────────────────────────────────────

def get_gpu_info() -> Dict[str, Any]:
    """Detect GPU hardware and driver information.

    Uses a probe dispatcher: lspci detects all GPUs, then vendor-specific
    probes enrich them with live stats and classify the memory architecture
    (``discrete`` / ``unified`` / ``integrated``).

    Non-Linux/non-Darwin platforms return an empty result with an
    explanatory issue. macOS is handled by the Apple Silicon probe
    (Phase 2 — until then, macOS gets the unsupported fallback).
    """
    if platform.system() == "Darwin":
        # Phase 2 will add _probe_apple_silicon here.
        # Until then, macOS gets the unsupported fallback.
        return {
            "gpus": [],
            "has_nvidia": False,
            "has_amd": False,
            "has_intel": False,
            "nvidia_smi_available": False,
            "recommended_driver": None,
            "driver_status": "missing",
            "issues": ["GPU detection on macOS is not yet implemented (GPU-1 Phase 2 pending)."],
        }

    if platform.system() != "Linux":
        return {
            "gpus": [],
            "has_nvidia": False,
            "has_amd": False,
            "has_intel": False,
            "nvidia_smi_available": False,
            "recommended_driver": None,
            "driver_status": "missing",
            "issues": ["GPU detection requires Linux (lspci / nvidia-smi / rocm-smi); this platform is not supported."],
        }

    gpus, has_nvidia, has_amd, has_intel = _detect_gpus_via_lspci()
    issues: List[str] = []
    nvidia_smi_available = False

    # NVIDIA probes
    if has_nvidia:
        nvidia_smi_available = _probe_nvidia_discrete(gpus, issues)
        if nvidia_smi_available:
            # _probe_nvidia_discrete may have marked some GPUs as "unified"
            # (RTX Spark) — fill their memory from system queries.
            _probe_nvidia_unified(gpus, issues)
        else:
            _probe_nvidia_nouveau(gpus, issues)

    # AMD probes (NEW — fills the pre-existing rocm-smi gap)
    if has_amd:
        _probe_amd_discrete(gpus, issues)

    # Intel probe
    if has_intel:
        _probe_intel(gpus, issues)

    # Normalize all GPUs (fill derived fields)
    for gpu in gpus:
        _normalize_gpu(gpu)

    # Determine overall driver status
    driver_status = "unknown"
    if len(gpus) == 0:
        driver_status = "missing"
    elif has_nvidia:
        if nvidia_smi_available:
            driver_status = "optimal"
        else:
            driver_status = "missing" if not any(g["driver_type"] for g in gpus if g["vendor"] == "NVIDIA") else "outdated"
    elif has_amd or has_intel:
        driver_status = "optimal" if any(g["driver_type"] for g in gpus) else "missing"

    return {
        "gpus": gpus,
        "has_nvidia": has_nvidia,
        "has_amd": has_amd,
        "has_intel": has_intel,
        "nvidia_smi_available": nvidia_smi_available,
        "recommended_driver": None,
        "driver_status": driver_status,
        "issues": issues,
    }


def get_deep_system_context() -> Dict[str, Any]:
    """
    Gather deep system context for GPU analysis.

    Collects: kernel, distro, display server, secure boot, installed packages,
    ML frameworks, container runtimes, etc.
    """
    context = {
        "kernel": None,
        "distro": None,
        "distro_version": None,
        "display_server": None,
        "secure_boot": None,
        "nvidia_packages": [],
        "cuda_paths": [],
        "ml_frameworks": {},
        "container_runtime": None,
    }

    # Kernel version
    kernel = run_command(["uname", "-r"])
    if kernel:
        context["kernel"] = kernel

    # Distro info
    os_release = run_command(["cat", "/etc/os-release"])
    if os_release:
        for line in os_release.split("\n"):
            if line.startswith("NAME="):
                context["distro"] = line.split("=")[1].strip('"')
            elif line.startswith("VERSION_ID="):
                context["distro_version"] = line.split("=")[1].strip('"')

    # Display server (X11 vs Wayland)
    session_type = run_command(["printenv", "XDG_SESSION_TYPE"])
    context["display_server"] = session_type or "unknown"

    # Secure Boot status
    mokutil = run_command(["mokutil", "--sb-state"])
    if mokutil:
        context["secure_boot"] = "enabled" if "enabled" in mokutil.lower() else "disabled"

    # Installed NVIDIA packages
    dpkg_nvidia = run_command(["dpkg", "-l"])
    if dpkg_nvidia:
        for line in dpkg_nvidia.split("\n"):
            if "nvidia" in line.lower() and line.startswith("ii"):
                parts = line.split()
                if len(parts) >= 3:
                    context["nvidia_packages"].append({
                        "name": parts[1],
                        "version": parts[2],
                    })

    # CUDA toolkit paths
    cuda_paths = ["/usr/local/cuda", "/usr/local/cuda-12", "/usr/local/cuda-11"]
    for path in cuda_paths:
        version_file = run_command(["cat", f"{path}/version.txt"])
        if version_file:
            context["cuda_paths"].append({"path": path, "version": version_file.strip()})

    # ML Frameworks detection
    # PyTorch
    pytorch_check = run_command(["python3", "-c", "import torch; print(torch.__version__, torch.cuda.is_available())"])
    if pytorch_check:
        parts = pytorch_check.split()
        context["ml_frameworks"]["pytorch"] = {
            "version": parts[0] if parts else "unknown",
            "cuda_available": "True" in pytorch_check,
        }

    # TensorFlow
    tf_check = run_command(["python3", "-c", "import tensorflow as tf; print(tf.__version__, len(tf.config.list_physical_devices('GPU')) > 0)"])
    if tf_check:
        parts = tf_check.split()
        context["ml_frameworks"]["tensorflow"] = {
            "version": parts[0] if parts else "unknown",
            "cuda_available": "True" in tf_check,
        }

    # Check for nvidia-container-toolkit
    nvidia_docker = run_command(["which", "nvidia-container-toolkit"])
    if nvidia_docker:
        context["container_runtime"] = "nvidia-container-toolkit"

    return context


def get_gpu_architecture(model: str) -> Optional[str]:
    """Determine GPU architecture from model name."""
    model_lower = model.lower()

    # NVIDIA architectures
    if "rtx 50" in model_lower or "blackwell" in model_lower or "gb10" in model_lower or "rtx spark" in model_lower or "n1x" in model_lower:
        return "Blackwell"
    elif "rtx 40" in model_lower or "ada" in model_lower:
        return "Ada Lovelace"
    elif "rtx 30" in model_lower or "ampere" in model_lower or "a2000" in model_lower or "a4000" in model_lower or "a5000" in model_lower or "a6000" in model_lower:
        return "Ampere"
    elif "rtx 20" in model_lower or "turing" in model_lower:
        return "Turing"
    elif "gtx 10" in model_lower or "pascal" in model_lower:
        return "Pascal"
    elif "gtx 9" in model_lower or "maxwell" in model_lower:
        return "Maxwell"

    # AMD architectures
    elif "rx 90" in model_lower or "rdna 4" in model_lower:
        return "RDNA 4"
    elif "rx 7" in model_lower or "rdna 3" in model_lower or "8060s" in model_lower or "strix halo" in model_lower:
        return "RDNA 3.5"
    elif "rx 6" in model_lower or "rdna 2" in model_lower:
        return "RDNA 2"

    # Apple Silicon architectures
    elif "m6" in model_lower:
        return "Apple Silicon M6"
    elif "m5" in model_lower:
        return "Apple Silicon M5"
    elif "m4" in model_lower:
        return "Apple Silicon M4"
    elif "m3" in model_lower:
        return "Apple Silicon M3"
    elif "m2" in model_lower:
        return "Apple Silicon M2"
    elif "m1" in model_lower:
        return "Apple Silicon M1"

    # Intel architectures
    elif "arc" in model_lower or "alchemist" in model_lower:
        return "Intel Arc (Alchemist)"
    elif "meteor lake" in model_lower or "core ultra" in model_lower:
        return "Intel Meteor Lake"

    return None


async def search_latest_driver_info(gpu_model: str, vendor: str) -> Dict[str, Any]:
    """
    Use web grounding to find latest driver information.
    """
    try:
        from ..web.search import WebSearch

        search = WebSearch()

        if vendor == "NVIDIA":
            # Search for latest NVIDIA driver
            query = f"NVIDIA Linux driver latest version {gpu_model} 2024 2025"
            results = await search.search(query, max_results=5)

            driver_info = {
                "latest_stable": None,
                "latest_beta": None,
                "cuda_latest": None,
                "sources": [],
                "recommendations": [],
            }

            # Parse results for version numbers
            for result in results:
                driver_info["sources"].append({
                    "title": result.title,
                    "url": result.url,
                    "snippet": result.snippet,
                })

                # Look for version patterns in snippets
                version_match = re.search(r"(\d{3}\.\d+(?:\.\d+)?)", result.snippet)
                if version_match:
                    version = version_match.group(1)
                    if not driver_info["latest_stable"]:
                        driver_info["latest_stable"] = version

            # Also search for CUDA
            cuda_query = "NVIDIA CUDA toolkit latest version Linux"
            cuda_results = await search.search(cuda_query, max_results=3)
            for result in cuda_results:
                cuda_match = re.search(r"CUDA (\d+\.\d+)", result.snippet)
                if cuda_match and not driver_info["cuda_latest"]:
                    driver_info["cuda_latest"] = cuda_match.group(1)

            return driver_info

        elif vendor == "AMD":
            query = f"AMD Linux amdgpu driver latest version {gpu_model}"
            results = await search.search(query, max_results=5)

            return {
                "sources": [{"title": r.title, "url": r.url, "snippet": r.snippet} for r in results],
                "recommendations": [],
            }

        return {"sources": [], "recommendations": []}

    except Exception as e:
        logger.warning(f"Web search failed: {e}")
        return {"error": str(e), "sources": []}


# ─────────────────────────────────────────────────────────────────────────────
# Agent tool handlers (same pattern as tools/system_info.py)
# ─────────────────────────────────────────────────────────────────────────────

async def _gpu_info_handler(args: Dict) -> str:
    """Get GPU hardware and driver information."""
    info = get_gpu_info()
    return json.dumps(info, indent=2, default=str)


async def _gpu_system_context_handler(args: Dict) -> str:
    """Gather deep system context for GPU analysis."""
    context = get_deep_system_context()
    return json.dumps(context, indent=2, default=str)


async def _gpu_architecture_handler(args: Dict) -> str:
    """Determine GPU architecture from a model name."""
    result = {
        "model": args.get("model", ""),
        "architecture": get_gpu_architecture(args.get("model", "")),
    }
    return json.dumps(result, indent=2, default=str)


async def _search_latest_driver_info_handler(args: Dict) -> str:
    """Search the web for the latest driver release for a GPU model."""
    info = await search_latest_driver_info(
        args.get("gpu_model", ""),
        args.get("vendor", "NVIDIA"),
    )
    return json.dumps(info, indent=2, default=str)


# Tool schemas for registration
GPU_TOOL_SCHEMAS = {
    "gpu_info": {
        "name": "gpu_info",
        "description": "Detect GPU hardware, driver version, memory architecture (discrete/unified/integrated), VRAM or unified memory, CUDA/Metal/ROCm version, and live statistics (temperature, power, utilization). Works on Linux (NVIDIA/AMD/Intel) with macOS and Windows support in progress.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    "gpu_system_context": {
        "name": "gpu_system_context",
        "description": "Gather deep system context for GPU analysis: kernel version, distro, display server (X11/Wayland), secure boot status, installed NVIDIA packages, CUDA toolkit paths, ML frameworks (PyTorch/TensorFlow), container runtime. Linux currently; macOS and Windows support in progress.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    "gpu_architecture": {
        "name": "gpu_architecture",
        "description": "Determine GPU architecture (Ampere, Ada Lovelace, Turing, RDNA, etc.) from a GPU model name",
        "parameters": {
            "type": "object",
            "properties": {
                "model": {
                    "type": "string",
                    "description": "GPU model name (e.g. 'NVIDIA GeForce RTX 3060')",
                },
            },
            "required": ["model"],
        },
    },
    "search_latest_driver_info": {
        "name": "search_latest_driver_info",
        "description": "Search the web for the latest stable driver release for a GPU model and vendor, with source links",
        "parameters": {
            "type": "object",
            "properties": {
                "gpu_model": {
                    "type": "string",
                    "description": "GPU model name to search for",
                },
                "vendor": {
                    "type": "string",
                    "enum": ["NVIDIA", "AMD"],
                    "description": "GPU vendor",
                },
            },
            "required": ["gpu_model", "vendor"],
        },
    },
}

# Handler mapping
GPU_TOOL_HANDLERS = {
    "gpu_info": _gpu_info_handler,
    "gpu_system_context": _gpu_system_context_handler,
    "gpu_architecture": _gpu_architecture_handler,
    "search_latest_driver_info": _search_latest_driver_info_handler,
}


def register_gpu_tools(tool_executor) -> None:
    """Register GPU tools with a ToolExecutor instance.

    Call this alongside register_system_tools(); the caller is expected to
    guard it to Linux (detection uses lspci/nvidia-smi), mirroring how
    register_ha_tools is conditionally wired in routes/agent.py.
    """
    for name, schema in GPU_TOOL_SCHEMAS.items():
        handler = GPU_TOOL_HANDLERS.get(name)
        if handler:
            tool_executor.register(name, handler, schema)
        else:
            logger.warning(f"GPU tool '{name}' has schema but no handler — skipped")
    logger.info("Registered GPU tools (gpu_info, gpu_system_context, gpu_architecture, search_latest_driver_info)")