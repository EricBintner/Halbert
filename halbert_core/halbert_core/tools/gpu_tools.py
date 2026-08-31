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


def get_gpu_info() -> Dict[str, Any]:
    """Detect GPU hardware and driver information.

    Non-Linux platforms return an empty result with an explanatory issue
    instead of silently looking GPU-less — detection uses lspci/nvidia-smi.
    """
    if platform.system() != "Linux":
        return {
            "gpus": [],
            "has_nvidia": False,
            "has_amd": False,
            "has_intel": False,
            "nvidia_smi_available": False,
            "recommended_driver": None,
            "driver_status": "missing",
            "issues": ["GPU detection requires Linux (lspci / nvidia-smi); this platform is not supported."],
        }

    gpus = []
    issues = []
    has_nvidia = False
    has_amd = False
    has_intel = False
    nvidia_smi_available = False

    # Use lspci to detect GPUs
    lspci_output = run_command(["lspci", "-nn"])
    if lspci_output:
        for line in lspci_output.split("\n"):
            # VGA compatible controller or 3D controller
            if "VGA" in line or "3D controller" in line or "Display controller" in line:
                # Parse the line
                # Example: "01:00.0 VGA compatible controller [0300]: NVIDIA Corporation GA106 [GeForce RTX 3060] [10de:2503] (rev a1)"
                pci_match = re.match(r'^([0-9a-f:.]+)\s+(.+?):\s+(.+?)(?:\s+\[([0-9a-f:]+)\])?(?:\s+\(rev.*\))?$', line, re.I)
                if pci_match:
                    pci_id = pci_match.group(1)
                    vendor_model = pci_match.group(3)

                    # Determine vendor
                    vendor = "Unknown"
                    if "nvidia" in vendor_model.lower():
                        vendor = "NVIDIA"
                        has_nvidia = True
                    elif "amd" in vendor_model.lower() or "radeon" in vendor_model.lower():
                        vendor = "AMD"
                        has_amd = True
                    elif "intel" in vendor_model.lower():
                        vendor = "Intel"
                        has_intel = True

                    gpu = {
                        "vendor": vendor,
                        "model": vendor_model,
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
                        "role": get_gpu_role(pci_id),  # 'auto', 'display', or 'compute'
                    }
                    gpus.append(gpu)

    # Try nvidia-smi for NVIDIA GPUs
    nvidia_smi = run_command(["nvidia-smi", "--query-gpu=name,driver_version,memory.total,memory.used,temperature.gpu,power.draw,power.limit,utilization.gpu", "--format=csv,noheader,nounits"])
    if nvidia_smi:
        nvidia_smi_available = True
        for i, line in enumerate(nvidia_smi.split("\n")):
            if line.strip():
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 8 and i < len(gpus):
                    # Find the NVIDIA GPU in our list
                    for gpu in gpus:
                        if gpu["vendor"] == "NVIDIA":
                            gpu["driver_version"] = parts[1] if parts[1] != "[N/A]" else None
                            gpu["driver_type"] = "nvidia"
                            try:
                                gpu["memory_total_mb"] = int(float(parts[2]))
                                gpu["vram_mb"] = gpu["memory_total_mb"]
                                gpu["memory_used_mb"] = int(float(parts[3]))
                                gpu["temperature_c"] = int(float(parts[4])) if parts[4] != "[N/A]" else None
                                gpu["power_draw_w"] = float(parts[5]) if parts[5] != "[N/A]" else None
                                gpu["power_limit_w"] = float(parts[6]) if parts[6] != "[N/A]" else None
                                gpu["utilization_percent"] = int(float(parts[7])) if parts[7] != "[N/A]" else None
                            except (ValueError, IndexError):
                                pass
                            break

        # Get CUDA version
        cuda_output = run_command(["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"])
        nvcc_output = run_command(["nvcc", "--version"])
        if nvcc_output:
            cuda_match = re.search(r"release (\d+\.\d+)", nvcc_output)
            if cuda_match:
                for gpu in gpus:
                    if gpu["vendor"] == "NVIDIA":
                        gpu["cuda_version"] = cuda_match.group(1)

    # Check for nouveau driver
    if has_nvidia and not nvidia_smi_available:
        # Check if nouveau is loaded
        lsmod = run_command(["lsmod"])
        if lsmod and "nouveau" in lsmod:
            for gpu in gpus:
                if gpu["vendor"] == "NVIDIA":
                    gpu["driver_type"] = "nouveau"
                    issues.append("NVIDIA GPU using open-source nouveau driver. Consider installing proprietary drivers for better performance.")

    # Check for AMD driver
    if has_amd:
        lsmod = run_command(["lsmod"])
        if lsmod:
            if "amdgpu" in lsmod:
                for gpu in gpus:
                    if gpu["vendor"] == "AMD":
                        gpu["driver_type"] = "amdgpu"
            elif "radeon" in lsmod:
                for gpu in gpus:
                    if gpu["vendor"] == "AMD":
                        gpu["driver_type"] = "radeon"
                        issues.append("AMD GPU using legacy radeon driver. Consider amdgpu for newer GPUs.")

    # Check for Intel driver
    if has_intel:
        lsmod = run_command(["lsmod"])
        if lsmod and "i915" in lsmod:
            for gpu in gpus:
                if gpu["vendor"] == "Intel":
                    gpu["driver_type"] = "i915"

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
        "recommended_driver": None,  # Could be populated with web search
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
    if "rtx 40" in model_lower or "ada" in model_lower:
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
    elif "rx 7" in model_lower or "rdna 3" in model_lower:
        return "RDNA 3"
    elif "rx 6" in model_lower or "rdna 2" in model_lower:
        return "RDNA 2"

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