# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Discovery scanners for GPU and AI accelerators (GPU-1 Phase 6).

Tests verify that GpuScanner and AiAcceleratorScanner correctly convert
the normalized probe output into Discovery objects. The underlying probe
functions are mocked so tests are platform-independent.
"""
import platform

import pytest

from halbert_core.discovery.scanners.gpu import GpuScanner
from halbert_core.discovery.scanners.ai_accelerator import AiAcceleratorScanner
from halbert_core.discovery.schema import DiscoveryType, DiscoverySeverity


# ─── GpuScanner ──────────────────────────────────────────────────────────────

def _mock_gpu_info(monkeypatch, info_dict):
    """Mock get_gpu_info in the gpu_tools module used by the scanner."""
    import halbert_core.tools.gpu_tools as gt
    monkeypatch.setattr(gt, "get_gpu_info", lambda: info_dict)
    # Also patch the import path the scanner uses
    import halbert_core.discovery.scanners.gpu as gpu_scanner_mod
    # The scanner imports get_gpu_info at call time, so patch the source
    monkeypatch.setattr(
        "halbert_core.tools.gpu_tools.get_gpu_info",
        lambda: info_dict,
    )


def test_gpu_scanner_discrete_nvidia(monkeypatch):
    """Discrete NVIDIA GPU produces a GPU discovery with VRAM label."""
    _mock_gpu_info(monkeypatch, {
        "gpus": [{
            "vendor": "NVIDIA",
            "model": "GeForce RTX 3060",
            "pci_id": "10de:2503",
            "vram_mb": 12288,
            "driver_type": "nvidia",
            "driver_version": "550.107.02",
            "cuda_version": "12.4",
            "temperature_c": 45.0,
            "power_draw_w": 120.5,
            "power_limit_w": 170.0,
            "utilization_percent": 12,
            "memory_used_mb": 512,
            "memory_total_mb": 12288,
            "memory_architecture": "discrete",
            "memory_source_label": "VRAM",
            "compute_api": "cuda",
            "core_count": None,
            "unified_memory_gb": None,
            "gpu_memory_ceiling_gb": None,
            "gpu_memory_in_use_gb": None,
            "role": "auto",
        }],
        "has_nvidia": True,
        "has_amd": False,
        "has_intel": False,
        "nvidia_smi_available": True,
        "recommended_driver": None,
        "driver_status": "optimal",
        "issues": [],
    })

    scanner = GpuScanner()
    discoveries = scanner.scan()

    assert len(discoveries) == 1
    d = discoveries[0]
    assert d.type == DiscoveryType.GPU
    assert "RTX 3060" in d.title
    assert d.data["vendor"] == "NVIDIA"
    assert d.data["memory_architecture"] == "discrete"
    assert d.data["compute_api"] == "cuda"
    assert d.data["vram_mb"] == 12288
    assert d.severity == DiscoverySeverity.SUCCESS


def test_gpu_scanner_apple_unified(monkeypatch):
    """Apple Silicon GPU produces a unified-memory discovery."""
    _mock_gpu_info(monkeypatch, {
        "gpus": [{
            "vendor": "Apple",
            "model": "Apple M1 Ultra",
            "pci_id": "apple-gpu",
            "vram_mb": None,
            "driver_type": None,
            "driver_version": None,
            "cuda_version": None,
            "temperature_c": None,
            "power_draw_w": None,
            "power_limit_w": None,
            "utilization_percent": None,
            "memory_used_mb": None,
            "memory_total_mb": None,
            "memory_architecture": "unified",
            "memory_source_label": "Unified Memory",
            "compute_api": "metal",
            "core_count": 48,
            "unified_memory_gb": 128,
            "gpu_memory_ceiling_gb": 96,
            "gpu_memory_in_use_gb": 12.5,
            "role": "auto",
        }],
        "has_nvidia": False,
        "has_amd": False,
        "has_intel": False,
        "has_apple": True,
        "nvidia_smi_available": False,
        "recommended_driver": None,
        "driver_status": "optimal",
        "issues": [],
    })

    scanner = GpuScanner()
    discoveries = scanner.scan()

    assert len(discoveries) == 1
    d = discoveries[0]
    assert d.type == DiscoveryType.GPU
    assert "M1 Ultra" in d.title
    assert d.data["memory_architecture"] == "unified"
    assert d.data["compute_api"] == "metal"
    assert d.data["core_count"] == 48
    assert d.data["unified_memory_gb"] == 128
    assert "unified memory" in d.chat_context.lower()


def test_gpu_scanner_no_driver_warning(monkeypatch):
    """GPU without a driver is flagged as WARNING."""
    _mock_gpu_info(monkeypatch, {
        "gpus": [{
            "vendor": "NVIDIA",
            "model": "GeForce RTX 4090",
            "pci_id": "10de:2684",
            "vram_mb": 24576,
            "driver_type": None,
            "driver_version": None,
            "cuda_version": None,
            "temperature_c": None,
            "power_draw_w": None,
            "power_limit_w": None,
            "utilization_percent": None,
            "memory_used_mb": None,
            "memory_total_mb": None,
            "memory_architecture": "discrete",
            "memory_source_label": "VRAM",
            "compute_api": None,
            "core_count": None,
            "unified_memory_gb": None,
            "gpu_memory_ceiling_gb": None,
            "gpu_memory_in_use_gb": None,
            "role": "auto",
        }],
        "has_nvidia": True,
        "has_amd": False,
        "has_intel": False,
        "nvidia_smi_available": False,
        "recommended_driver": None,
        "driver_status": "missing",
        "issues": ["NVIDIA GPU detected but nvidia-smi not available."],
    })

    scanner = GpuScanner()
    discoveries = scanner.scan()

    assert len(discoveries) == 1
    d = discoveries[0]
    assert d.severity == DiscoverySeverity.WARNING
    assert d.status == "No driver"


def test_gpu_scanner_empty_with_issues(monkeypatch):
    """No GPUs but probe issues produce a warning discovery."""
    _mock_gpu_info(monkeypatch, {
        "gpus": [],
        "has_nvidia": False,
        "has_amd": False,
        "has_intel": False,
        "nvidia_smi_available": False,
        "recommended_driver": None,
        "driver_status": "missing",
        "issues": ["No GPU detected."],
    })

    scanner = GpuScanner()
    discoveries = scanner.scan()

    assert len(discoveries) == 1
    assert discoveries[0].severity == DiscoverySeverity.WARNING


def test_gpu_scanner_empty_no_issues(monkeypatch):
    """No GPUs and no issues produce an empty list."""
    _mock_gpu_info(monkeypatch, {
        "gpus": [],
        "has_nvidia": False,
        "has_amd": False,
        "has_intel": False,
        "nvidia_smi_available": False,
        "recommended_driver": None,
        "driver_status": "missing",
        "issues": [],
    })

    scanner = GpuScanner()
    discoveries = scanner.scan()
    assert len(discoveries) == 0


# ─── AiAcceleratorScanner ────────────────────────────────────────────────────

def _mock_accel_info(monkeypatch, info_dict):
    """Mock get_accelerator_info in the accelerator_tools module."""
    monkeypatch.setattr(
        "halbert_core.tools.accelerator_tools.get_accelerator_info",
        lambda: info_dict,
    )


def test_accelerator_scanner_coral(monkeypatch):
    """Coral Edge TPU produces an AI_ACCELERATOR discovery."""
    _mock_accel_info(monkeypatch, {
        "accelerators": [{
            "type": "tpu",
            "vendor": "Google",
            "model": "Coral Edge TPU (M.2)",
            "form_factor": "M.2",
            "device_node": "/dev/apex_0",
            "tops": 4.0,
            "driver_loaded": True,
            "driver_name": "apex",
            "driver_version": None,
            "firmware_version": None,
            "temperature_c": 55.0,
            "utilization_percent": None,
            "power_draw_w": None,
            "runtime_available": True,
            "runtime_version": "2.0.2",
            "status": "active",
        }],
        "has_tpu": True,
        "has_npu": False,
        "has_ane": False,
        "total_tops": 4.0,
        "issues": [],
    })

    scanner = AiAcceleratorScanner()
    discoveries = scanner.scan()

    assert len(discoveries) == 1
    d = discoveries[0]
    assert d.type == DiscoveryType.AI_ACCELERATOR
    assert "Coral" in d.title
    assert d.data["type"] == "tpu"
    assert d.data["tops"] == 4.0
    assert d.data["driver_loaded"] is True
    assert d.severity == DiscoverySeverity.SUCCESS


def test_accelerator_scanner_apple_ane(monkeypatch):
    """Apple Neural Engine produces an AI_ACCELERATOR discovery."""
    _mock_accel_info(monkeypatch, {
        "accelerators": [{
            "type": "ane",
            "vendor": "Apple",
            "model": "Apple Neural Engine",
            "form_factor": "integrated",
            "device_node": None,
            "tops": 11.0,
            "driver_loaded": True,
            "driver_name": "AppleANE",
            "driver_version": None,
            "firmware_version": None,
            "temperature_c": None,
            "utilization_percent": None,
            "power_draw_w": None,
            "runtime_available": True,
            "runtime_version": "CoreML",
            "status": "active",
        }],
        "has_tpu": False,
        "has_npu": False,
        "has_ane": True,
        "total_tops": 11.0,
        "issues": [],
    })

    scanner = AiAcceleratorScanner()
    discoveries = scanner.scan()

    assert len(discoveries) == 1
    d = discoveries[0]
    assert d.type == DiscoveryType.AI_ACCELERATOR
    assert d.data["type"] == "ane"
    assert d.data["vendor"] == "Apple"
    assert d.severity == DiscoverySeverity.SUCCESS


def test_accelerator_scanner_missing_driver(monkeypatch):
    """Accelerator with missing driver is WARNING severity."""
    _mock_accel_info(monkeypatch, {
        "accelerators": [{
            "type": "tpu",
            "vendor": "Google",
            "model": "Coral Edge TPU (USB)",
            "form_factor": "USB",
            "device_node": None,
            "tops": 4.0,
            "driver_loaded": False,
            "driver_name": "gasket",
            "driver_version": None,
            "firmware_version": None,
            "temperature_c": None,
            "utilization_percent": None,
            "power_draw_w": None,
            "runtime_available": False,
            "runtime_version": None,
            "status": "missing_driver",
        }],
        "has_tpu": True,
        "has_npu": False,
        "has_ane": False,
        "total_tops": 4.0,
        "issues": ["Google Coral Edge TPU (USB) detected but driver not loaded."],
    })

    scanner = AiAcceleratorScanner()
    discoveries = scanner.scan()

    assert len(discoveries) == 1
    d = discoveries[0]
    assert d.severity == DiscoverySeverity.WARNING
    assert "Missing Driver" in d.status


def test_accelerator_scanner_multiple(monkeypatch):
    """Multiple accelerators produce multiple discoveries."""
    _mock_accel_info(monkeypatch, {
        "accelerators": [
            {
                "type": "tpu",
                "vendor": "Google",
                "model": "Coral Edge TPU",
                "form_factor": "M.2",
                "device_node": "/dev/apex_0",
                "tops": 4.0,
                "driver_loaded": True,
                "driver_name": "apex",
                "driver_version": None,
                "firmware_version": None,
                "temperature_c": None,
                "utilization_percent": None,
                "power_draw_w": None,
                "runtime_available": True,
                "runtime_version": "2.0.2",
                "status": "active",
            },
            {
                "type": "npu",
                "vendor": "Intel",
                "model": "Intel NPU",
                "form_factor": "integrated",
                "device_node": "/dev/accel/accel0",
                "tops": 11.0,
                "driver_loaded": True,
                "driver_name": "intel_vpu",
                "driver_version": None,
                "firmware_version": None,
                "temperature_c": None,
                "utilization_percent": None,
                "power_draw_w": None,
                "runtime_available": False,
                "runtime_version": None,
                "status": "missing_runtime",
            },
        ],
        "has_tpu": True,
        "has_npu": True,
        "has_ane": False,
        "total_tops": 15.0,
        "issues": [],
    })

    scanner = AiAcceleratorScanner()
    discoveries = scanner.scan()

    assert len(discoveries) == 2
    types = {d.data["type"] for d in discoveries}
    assert types == {"tpu", "npu"}


def test_accelerator_scanner_empty(monkeypatch):
    """No accelerators produces an empty list."""
    _mock_accel_info(monkeypatch, {
        "accelerators": [],
        "has_tpu": False,
        "has_npu": False,
        "has_ane": False,
        "total_tops": None,
        "issues": [],
    })

    scanner = AiAcceleratorScanner()
    discoveries = scanner.scan()
    assert len(discoveries) == 0


# ─── Engine registration ─────────────────────────────────────────────────────

def test_engine_registers_gpu_and_accel_scanners(monkeypatch):
    """DiscoveryEngine registers GpuScanner and AiAcceleratorScanner."""
    monkeypatch.setattr(platform, "system", lambda: "Linux")

    from halbert_core.discovery.engine import DiscoveryEngine
    engine = DiscoveryEngine(use_chromadb=False)

    scanner_names = engine.registered_scanners
    assert "GpuScanner" in scanner_names
    assert "AiAcceleratorScanner" in scanner_names


def test_engine_registers_gpu_and_accel_scanners_macos(monkeypatch):
    """DiscoveryEngine registers GPU + accelerator scanners on macOS too."""
    monkeypatch.setattr(platform, "system", lambda: "Darwin")

    from halbert_core.discovery.engine import DiscoveryEngine
    engine = DiscoveryEngine(use_chromadb=False)

    scanner_names = engine.registered_scanners
    assert "GpuScanner" in scanner_names
    assert "AiAcceleratorScanner" in scanner_names
