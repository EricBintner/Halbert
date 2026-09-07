# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""GPU agent tools (tools/gpu_tools.py) — shared detection + tool handlers.

All command output is mocked: lspci/nvidia-smi/uname never run here, so the
tests pass on any platform (Mac development, Linux deployment).
"""
import asyncio
import json
import platform
from types import SimpleNamespace

import pytest

from halbert_core.tools import gpu_tools
from halbert_core.tools.gpu_tools import (
    GPU_TOOL_HANDLERS,
    GPU_TOOL_SCHEMAS,
    get_deep_system_context,
    get_gpu_architecture,
    get_gpu_info,
    register_gpu_tools,
    search_latest_driver_info,
)

LSPCI_OUTPUT = (
    "00:02.0 VGA compatible controller [0300]: Intel Corporation UHD Graphics 630 [8086:3e92] (rev 02)\n"
    "01:00.0 VGA compatible controller [0300]: NVIDIA Corporation GA106 [GeForce RTX 3060] [10de:2503] (rev a1)\n"
)

NVIDIA_SMI_OUTPUT = (
    "NVIDIA GeForce RTX 3060, 550.107.02, 12288, 512, 45, 120.5, 170, 12\n"
)

NVCC_OUTPUT = "nvcc: NVIDIA (R) Cuda compiler driver\nCuda release 12.4, V12.4.131"

OS_RELEASE = 'NAME="Ubuntu"\nVERSION_ID="24.04"\n'


def _mock_run_command(monkeypatch, outputs, platform_system="Linux"):
    """Map a command (as a tuple) to canned stdout; unknown commands -> None."""
    monkeypatch.setattr(gpu_tools, "run_command",
                        lambda cmd, timeout=10: outputs.get(tuple(cmd)))
    monkeypatch.setattr(platform, "system", lambda: platform_system)


def _linux_gpu_outputs():
    return {
        ("lspci", "-nn"): LSPCI_OUTPUT,
        ("nvidia-smi", "--query-gpu=name,driver_version,memory.total,memory.used,temperature.gpu,power.draw,power.limit,utilization.gpu",
         "--format=csv,noheader,nounits"): NVIDIA_SMI_OUTPUT,
        ("nvcc", "--version"): NVCC_OUTPUT,
        ("uname", "-r"): "6.8.0-45-generic",
        ("cat", "/etc/os-release"): OS_RELEASE,
    }


def _isolated_gpu_config(monkeypatch, tmp_path):
    """Keep role lookups off the developer's real config dir."""
    monkeypatch.setattr(gpu_tools, "_get_gpu_config_path", lambda: tmp_path / "gpu_config.yml")


def test_get_gpu_info_parses_nvidia_gpu(monkeypatch, tmp_path):
    _mock_run_command(monkeypatch, _linux_gpu_outputs())
    _isolated_gpu_config(monkeypatch, tmp_path)

    info = get_gpu_info()

    nvidia = [g for g in info["gpus"] if g["vendor"] == "NVIDIA"]
    assert len(nvidia) == 1
    gpu = nvidia[0]
    assert gpu["model"] == "NVIDIA Corporation GA106 [GeForce RTX 3060]"
    assert gpu["pci_id"] == "01:00.0"
    assert gpu["driver_version"] == "550.107.02"
    assert gpu["driver_type"] == "nvidia"
    assert gpu["vram_mb"] == 12288
    assert gpu["memory_used_mb"] == 512
    assert gpu["temperature_c"] == 45
    assert gpu["power_draw_w"] == 120.5
    assert gpu["power_limit_w"] == 170.0
    assert gpu["utilization_percent"] == 12
    assert gpu["cuda_version"] == "12.4"
    assert gpu["role"] == "auto"
    assert info["has_nvidia"] is True
    assert info["nvidia_smi_available"] is True
    assert info["driver_status"] == "optimal"


def test_get_gpu_info_non_linux_fallback(monkeypatch):
    _mock_run_command(monkeypatch, {}, platform_system="Darwin")

    info = get_gpu_info()

    assert info["gpus"] == []
    assert info["has_nvidia"] is False
    assert info["nvidia_smi_available"] is False
    assert info["driver_status"] == "missing"
    # The fallback says why, rather than silently looking GPU-less.
    assert any("not yet implemented" in issue or "not supported" in issue for issue in info["issues"])


def test_get_gpu_architecture_known_models():
    assert get_gpu_architecture("NVIDIA GeForce RTX 3060") == "Ampere"
    assert get_gpu_architecture("NVIDIA GeForce RTX 4070") == "Ada Lovelace"
    assert get_gpu_architecture("NVIDIA GeForce RTX 5090") == "Blackwell"
    assert get_gpu_architecture("AMD Radeon RX 7900") == "RDNA 3.5"
    assert get_gpu_architecture("AMD Radeon RX 6800") == "RDNA 2"
    assert get_gpu_architecture("Apple M1 Ultra") == "Apple Silicon M1"
    assert get_gpu_architecture("Apple M4 Max") == "Apple Silicon M4"
    assert get_gpu_architecture("Mystery Card") is None


# ─────────────────────────────────────────────────────────────────────────────
# GPU-1 Phase 1: probe dispatcher + memory_architecture + AMD stats
# ─────────────────────────────────────────────────────────────────────────────

LSPCI_AMD = (
    "01:00.0 VGA compatible controller [0300]: Advanced Micro Devices, Inc. [AMD/ATI] Navi 31 [Radeon RX 7900 XT] [1002:744c]\n"
)

ROCM_SMI_JSON = json.dumps({
    "GPU 0 [Navi 31]": {
        "GPU use (%)": "42",
        "Temperature (C)": "65",
        "Average Graphics Package Power (W)": "210.5",
        "VRAM Total Memory (B)": "21474836480",
        "VRAM Used Memory (B)": "4294967296",
    },
})

LSPCI_STRIX_HALO = (
    "06:00.0 Display controller [0380]: Advanced Micro Devices, Inc. [AMD/ATI] Strix Halo [Radeon 8060S] [1002:150e]\n"
)

ROCM_SMI_STRIX_HALO = json.dumps({
    "GPU 0 [Radeon 8060S]": {
        "GPU use (%)": "15",
        "Temperature (C)": "55",
        "Average Graphics Package Power (W)": "45.2",
        "VRAM Total Memory (B)": "9663676416",   # ~9 GB carve-out
        "VRAM Used Memory (B)": "2147483648",    # ~2 GB used
        "GTT Total Memory (B)": "68719476736",   # ~64 GB GTT
    },
})

PROC_MEMINFO = (
    "MemTotal:       134217728 kB\n"
    "MemFree:        67108864 kB\n"
    "MemAvailable:   100663296 kB\n"
)

NVIDIA_SMI_UNIFIED = (
    "NVIDIA RTX Spark N1X, 560.31, Not Supported, Not Supported, 42, 15.2, 25, 8\n"
)


def test_nvidia_discrete_probe_sets_memory_architecture(monkeypatch, tmp_path):
    """NVIDIA discrete GPU gets memory_architecture='discrete' and normalized fields."""
    _mock_run_command(monkeypatch, _linux_gpu_outputs())
    _isolated_gpu_config(monkeypatch, tmp_path)

    info = get_gpu_info()
    nvidia = [g for g in info["gpus"] if g["vendor"] == "NVIDIA"][0]

    assert nvidia["memory_architecture"] == "discrete"
    assert nvidia["compute_api"] == "cuda"
    assert nvidia["memory_source_label"] == "VRAM"
    assert nvidia["gpu_memory_ceiling_gb"] == 12.0  # 12288 MB -> 12.0 GB
    assert nvidia["gpu_memory_in_use_gb"] == 0.5     # 512 MB -> 0.5 GB


def test_amd_discrete_probe_via_rocm_smi(monkeypatch, tmp_path):
    """AMD GPU gets live stats from rocm-smi (fills the pre-existing gap)."""
    outputs = {
        ("lspci", "-nn"): LSPCI_AMD,
        ("rocm-smi", "--showuse", "--showtemp", "--showpower", "--showclocks", "--json"): ROCM_SMI_JSON,
        ("lsmod",): "amdgpu 1234567 0\n",
        ("uname", "-r"): "6.8.0-45-generic",
        ("cat", "/etc/os-release"): OS_RELEASE,
    }
    _mock_run_command(monkeypatch, outputs)
    _isolated_gpu_config(monkeypatch, tmp_path)

    info = get_gpu_info()
    amd = [g for g in info["gpus"] if g["vendor"] == "AMD"]
    assert len(amd) == 1
    gpu = amd[0]

    assert gpu["driver_type"] == "amdgpu"
    assert gpu["memory_architecture"] == "discrete"
    assert gpu["compute_api"] == "rocm"
    assert gpu["utilization_percent"] == 42
    assert gpu["temperature_c"] == 65
    assert gpu["power_draw_w"] == 210.5
    # 21474836480 bytes = 20480 MB
    assert gpu["memory_total_mb"] == 20480
    assert gpu["vram_mb"] == 20480
    # 4294967296 bytes = 4096 MB
    assert gpu["memory_used_mb"] == 4096
    assert gpu["gpu_memory_ceiling_gb"] == 20.0
    assert gpu["memory_source_label"] == "VRAM"


def test_amd_strix_halo_unified_memory(monkeypatch, tmp_path):
    """Strix Halo: VRAM+GTT share physical memory. Don't sum them."""
    outputs = {
        ("lspci", "-nn"): LSPCI_STRIX_HALO,
        ("rocm-smi", "--showuse", "--showtemp", "--showpower", "--showclocks", "--json"): ROCM_SMI_STRIX_HALO,
        ("lsmod",): "amdgpu 1234567 0\n",
        ("cat", "/proc/meminfo"): PROC_MEMINFO,
        ("uname", "-r"): "6.8.0-45-generic",
        ("cat", "/etc/os-release"): OS_RELEASE,
    }
    _mock_run_command(monkeypatch, outputs)
    _isolated_gpu_config(monkeypatch, tmp_path)

    info = get_gpu_info()
    amd = [g for g in info["gpus"] if g["vendor"] == "AMD"]
    assert len(amd) == 1
    gpu = amd[0]

    assert gpu["memory_architecture"] == "unified"
    assert gpu["compute_api"] == "rocm"
    assert gpu["memory_source_label"] == "Unified Memory"
    assert gpu["unified_memory_gb"] == 128  # 134217728 kB / (1024*1024)
    # Ceiling is the VRAM carve-out (~9 GB), NOT VRAM+GTT sum
    assert gpu["gpu_memory_ceiling_gb"] == 9.0
    # Must NOT be 9+64=73 GB (the overcounting bug)
    assert gpu["gpu_memory_ceiling_gb"] < 20
    assert gpu["utilization_percent"] == 15
    assert gpu["temperature_c"] == 55


def test_nvidia_unified_rtx_spark(monkeypatch, tmp_path):
    """RTX Spark: nvidia-smi says 'Not Supported' for memory; fall back to /proc/meminfo."""
    lspci = (
        "01:00.0 3D controller [0302]: NVIDIA Corporation GB10 [RTX Spark N1X] [10de:2840]\n"
    )
    outputs = {
        ("lspci", "-nn"): lspci,
        ("nvidia-smi", "--query-gpu=name,driver_version,memory.total,memory.used,temperature.gpu,power.draw,power.limit,utilization.gpu",
         "--format=csv,noheader,nounits"): NVIDIA_SMI_UNIFIED,
        ("nvcc", "--version"): NVCC_OUTPUT,
        ("cat", "/proc/meminfo"): PROC_MEMINFO,
        ("uname", "-r"): "6.8.0-45-generic",
        ("cat", "/etc/os-release"): OS_RELEASE,
    }
    _mock_run_command(monkeypatch, outputs)
    _isolated_gpu_config(monkeypatch, tmp_path)

    info = get_gpu_info()
    nvidia = [g for g in info["gpus"] if g["vendor"] == "NVIDIA"]
    assert len(nvidia) == 1
    gpu = nvidia[0]

    assert gpu["memory_architecture"] == "unified"
    assert gpu["compute_api"] == "cuda"
    assert gpu["memory_source_label"] == "Unified Memory"
    assert gpu["unified_memory_gb"] == 128
    # Ceiling is 75% of 128 = 96 GB
    assert gpu["gpu_memory_ceiling_gb"] == 96.0
    # Util/temp/power still work from nvidia-smi
    assert gpu["utilization_percent"] == 8
    assert gpu["temperature_c"] == 42
    assert gpu["power_draw_w"] == 15.2
    assert gpu["driver_version"] == "560.31"
    assert info["nvidia_smi_available"] is True


def test_intel_integrated_gpu(monkeypatch, tmp_path):
    """Intel iGPU gets memory_architecture='integrated'."""
    lspci = (
        "00:02.0 VGA compatible controller [0300]: Intel Corporation UHD Graphics 630 [8086:3e92] (rev 02)\n"
    )
    outputs = {
        ("lspci", "-nn"): lspci,
        ("lsmod",): "i915 1234567 0\n",
        ("uname", "-r"): "6.8.0-45-generic",
        ("cat", "/etc/os-release"): OS_RELEASE,
    }
    _mock_run_command(monkeypatch, outputs)
    _isolated_gpu_config(monkeypatch, tmp_path)

    info = get_gpu_info()
    intel = [g for g in info["gpus"] if g["vendor"] == "Intel"]
    assert len(intel) == 1
    gpu = intel[0]

    assert gpu["driver_type"] == "i915"
    assert gpu["memory_architecture"] == "integrated"
    assert gpu["compute_api"] == "opencl"
    assert gpu["memory_source_label"] == "System RAM"


def test_nvidia_nouveau_driver_warning(monkeypatch, tmp_path):
    """NVIDIA with nouveau driver produces a warning issue."""
    lspci = (
        "01:00.0 VGA compatible controller [0300]: NVIDIA Corporation GA106 [GeForce RTX 3060] [10de:2503] (rev a1)\n"
    )
    outputs = {
        ("lspci", "-nn"): lspci,
        ("lsmod",): "nouveau 1234567 0\n",
        ("uname", "-r"): "6.8.0-45-generic",
        ("cat", "/etc/os-release"): OS_RELEASE,
    }
    _mock_run_command(monkeypatch, outputs)
    _isolated_gpu_config(monkeypatch, tmp_path)

    info = get_gpu_info()
    nvidia = [g for g in info["gpus"] if g["vendor"] == "NVIDIA"][0]
    assert nvidia["driver_type"] == "nouveau"
    assert any("nouveau" in issue for issue in info["issues"])


def test_gpu_system_context_parses_kernel_and_distro(monkeypatch):
    outputs = {
        ("uname", "-r"): "6.8.0-45-generic",
        ("cat", "/etc/os-release"): OS_RELEASE,
    }
    _mock_run_command(monkeypatch, outputs)

    context = get_deep_system_context()

    assert context["kernel"] == "6.8.0-45-generic"
    assert context["distro"] == "Ubuntu"
    assert context["distro_version"] == "24.04"
    assert context["ml_frameworks"] == {}


class TestToolHandlers:
    def test_gpu_info_handler_returns_json(self, monkeypatch, tmp_path):
        _mock_run_command(monkeypatch, _linux_gpu_outputs())
        _isolated_gpu_config(monkeypatch, tmp_path)

        result = json.loads(asyncio.run(GPU_TOOL_HANDLERS["gpu_info"]({})))

        assert result["has_nvidia"] is True
        nvidia = [g for g in result["gpus"] if g["vendor"] == "NVIDIA"]
        assert nvidia[0]["driver_version"] == "550.107.02"

    def test_gpu_info_handler_graceful_on_non_linux(self, monkeypatch):
        _mock_run_command(monkeypatch, {}, platform_system="Darwin")

        result = json.loads(asyncio.run(GPU_TOOL_HANDLERS["gpu_info"]({})))

        assert result["gpus"] == []

    def test_gpu_system_context_handler_returns_json(self, monkeypatch):
        _mock_run_command(monkeypatch, {
            ("uname", "-r"): "6.8.0-45-generic",
            ("cat", "/etc/os-release"): OS_RELEASE,
        })

        result = json.loads(asyncio.run(GPU_TOOL_HANDLERS["gpu_system_context"]({})))

        assert result["kernel"] == "6.8.0-45-generic"

    def test_gpu_architecture_handler(self):
        result = json.loads(asyncio.run(GPU_TOOL_HANDLERS["gpu_architecture"]({
            "model": "NVIDIA GeForce RTX 3060",
        })))

        assert result["architecture"] == "Ampere"


def test_search_latest_driver_info_parses_versions(monkeypatch):
    """The web-grounding helper extracts a driver version from search snippets."""
    results = [
        SimpleNamespace(
            title="NVIDIA Unix Driver",
            url="https://www.nvidia.com/drivers",
            snippet="NVIDIA 575.57.08 released for production Linux",
        ),
    ]

    class FakeSearch:
        async def search(self, query, max_results=5):
            if "CUDA" in query:
                return [SimpleNamespace(
                    title="CUDA Toolkit",
                    url="https://developer.nvidia.com/cuda",
                    snippet="CUDA 12.8 toolkit is the latest release",
                )]
            return results

    import halbert_core.web.search as web_search
    monkeypatch.setattr(web_search, "WebSearch", FakeSearch)

    import asyncio
    info = asyncio.run(search_latest_driver_info("GeForce RTX 3060", "NVIDIA"))

    assert info["latest_stable"] == "575.57.08"
    assert info["cuda_latest"] == "12.8"
    assert info["sources"][0]["title"] == "NVIDIA Unix Driver"


def test_register_gpu_tools():
    class FakeExecutor:
        def __init__(self):
            self.registered = {}

        def register(self, name, handler, schema):
            self.registered[name] = (handler, schema)

    executor = FakeExecutor()
    register_gpu_tools(executor)

    assert set(executor.registered) == set(GPU_TOOL_SCHEMAS)
    assert set(GPU_TOOL_HANDLERS) == set(GPU_TOOL_SCHEMAS)
    for name, (handler, schema) in executor.registered.items():
        assert handler is GPU_TOOL_HANDLERS[name]
        assert schema is GPU_TOOL_SCHEMAS[name]
        assert schema["name"] == name
        assert "description" in schema