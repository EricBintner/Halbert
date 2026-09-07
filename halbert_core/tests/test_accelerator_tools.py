# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""AI accelerator tools (tools/accelerator_tools.py) — TPU/NPU/ANE detection.

All command output is mocked: lspci/lsusb/hailortcli never run here,
so the tests pass on any platform.
"""
import asyncio
import json
import platform

import pytest

from halbert_core.tools import accelerator_tools
from halbert_core.tools.accelerator_tools import (
    ACCELERATOR_TOOL_HANDLERS,
    ACCELERATOR_TOOL_SCHEMAS,
    get_accelerator_info,
    register_accelerator_tools,
)


def _mock_run_command(monkeypatch, outputs, platform_system="Linux"):
    """Map a command (as a tuple) to canned stdout; unknown commands -> None."""
    monkeypatch.setattr(accelerator_tools, "run_command",
                        lambda cmd, timeout=10: outputs.get(tuple(cmd)))
    monkeypatch.setattr(platform, "system", lambda: platform_system)


def _mock_file_exists(monkeypatch, paths):
    """Mock os.path.exists to return True only for given paths."""
    monkeypatch.setattr("os.path.exists", lambda p: p in paths)


# ─────────────────────────────────────────────────────────────────────────────
# Coral Edge TPU
# ─────────────────────────────────────────────────────────────────────────────

LSPCI_CORAL = (
    "01:00.0 Co-processor [0880]: Global Unichip Corp. Coral Edge TPU [1ac1:089a]\n"
)

LSUSB_CORAL = (
    "Bus 001 Device 004: ID 1a6e:089a Global Unichip Corp. Coral Edge TPU\n"
)


def test_coral_pcie_detected(monkeypatch):
    """Coral Edge TPU PCIe detected with driver loaded."""
    outputs = {
        ("lspci", "-nn"): LSPCI_CORAL,
        ("lsmod",): "apex 12345 0\ngasket 45678 1 apex\n",
    }
    _mock_run_command(monkeypatch, outputs)
    _mock_file_exists(monkeypatch, {"/dev/apex_0"})

    info = get_accelerator_info()

    coral = [a for a in info["accelerators"] if a["vendor"] == "Google"]
    assert len(coral) == 1
    acc = coral[0]
    assert acc["type"] == "tpu"
    assert acc["form_factor"] == "pcie"
    assert acc["device_node"] == "/dev/apex_0"
    assert acc["driver_loaded"] is True
    assert acc["driver_name"] == "apex"
    assert acc["status"] == "active"
    assert info["has_tpu"] is True


def test_coral_usb_detected(monkeypatch):
    """Coral Edge TPU USB detected (no temperature sensor on USB)."""
    outputs = {
        ("lsusb",): LSUSB_CORAL,
        ("python3", "-c",
         "from pycoral.utils import edgetpu; print('available')"): "available",
    }
    _mock_run_command(monkeypatch, outputs)

    info = get_accelerator_info()

    coral = [a for a in info["accelerators"] if "Coral" in a["model"]]
    assert len(coral) == 1
    acc = coral[0]
    assert acc["form_factor"] == "usb"
    assert acc["tops"] == 4
    assert acc["runtime_available"] is True
    assert acc["status"] == "active"
    # USB Coral has no temperature
    assert acc["temperature_c"] is None


def test_coral_missing_driver_warning(monkeypatch):
    """Coral detected but driver not loaded produces a warning issue."""
    outputs = {
        ("lspci", "-nn"): LSPCI_CORAL,
        ("lsmod",): "i915 12345 0\n",  # no apex/gasket
    }
    _mock_run_command(monkeypatch, outputs)
    _mock_file_exists(monkeypatch, set())  # no /dev/apex_0

    info = get_accelerator_info()

    coral = [a for a in info["accelerators"] if a["vendor"] == "Google"]
    assert len(coral) == 1
    assert coral[0]["status"] == "missing_driver"
    assert any("driver not loaded" in issue for issue in info["issues"])


# ─────────────────────────────────────────────────────────────────────────────
# Hailo
# ─────────────────────────────────────────────────────────────────────────────

LSPCI_HAILO = (
    "04:00.0 Co-processor [0880]: Hailo Technologies Ltd. Hailo-8 AI Processor [1e60:2864] (rev 01)\n"
)

HAILORTCLI_SCAN = "Hailo Devices:\n  [-] Device: 0000:04:00.0\n"
HAILORTCLI_IDENTIFY = "Hailo-8\nFirmware        : 4.21.0\nSerial          : HA12345\n"


def test_hailo_8_detected(monkeypatch):
    """Hailo-8 detected with driver and runtime."""
    outputs = {
        ("lspci",): LSPCI_HAILO,
        ("lsmod",): "hailo_pci 12345 0\n",
        ("hailortcli", "scan"): HAILORTCLI_SCAN,
        ("hailortcli", "fw-control", "identify"): HAILORTCLI_IDENTIFY,
        ("modinfo", "hailo_pci"): "filename: hailo_pci.ko\nversion: 4.21.0\nlicense: GPL v2\n",
    }
    _mock_run_command(monkeypatch, outputs)
    _mock_file_exists(monkeypatch, {"/dev/hailo0"})

    info = get_accelerator_info()

    hailo = [a for a in info["accelerators"] if a["vendor"] == "Hailo"]
    assert len(hailo) == 1
    acc = hailo[0]
    assert acc["model"] == "Hailo-8"
    assert acc["tops"] == 26
    assert acc["driver_loaded"] is True
    assert acc["driver_name"] == "hailo_pci"
    assert acc["driver_version"] == "4.21.0"
    assert acc["firmware_version"] == "4.21.0"
    assert acc["runtime_available"] is True
    assert acc["status"] == "active"
    assert info["has_npu"] is True


# ─────────────────────────────────────────────────────────────────────────────
# MemryX MX3
# ─────────────────────────────────────────────────────────────────────────────

LSPCI_MEMRYX = (
    "02:00.0 Co-processor [0880]: MemryX Inc. MX3 AI Accelerator [1ed9:1234]\n"
)


def test_memryx_detected(monkeypatch):
    """MemryX MX3 detected with driver loaded."""
    outputs = {
        ("lspci",): LSPCI_MEMRYX,
        ("lsmod",): "memx_cascade_plus_pcie 12345 0\n",
    }
    _mock_run_command(monkeypatch, outputs)
    _mock_file_exists(monkeypatch, {"/dev/memx0"})

    info = get_accelerator_info()

    mx3 = [a for a in info["accelerators"] if a["vendor"] == "MemryX"]
    assert len(mx3) == 1
    acc = mx3[0]
    assert acc["model"] == "MX3"
    assert acc["tops"] == 26
    assert acc["driver_loaded"] is True
    assert acc["driver_name"] == "memx_cascade_plus_pcie"
    assert acc["device_node"] == "/dev/memx0"
    assert acc["status"] == "active"


# ─────────────────────────────────────────────────────────────────────────────
# Intel NPU
# ─────────────────────────────────────────────────────────────────────────────

def test_intel_npu_detected(monkeypatch):
    """Intel NPU detected via /dev/accel/accel0 + intel_vpu driver."""
    outputs = {
        ("lsmod",): "intel_vpu 12345 0\n",
        ("modinfo", "intel_vpu"): "filename: intel_vpu.ko\nversion: 1.8.0\n",
        ("python3", "-c",
         "from openvino.runtime import Core; print(Core().available_devices)"):
            "['CPU', 'NPU']",
    }
    _mock_run_command(monkeypatch, outputs)
    _mock_file_exists(monkeypatch, {"/dev/accel/accel0"})

    info = get_accelerator_info()

    npu = [a for a in info["accelerators"] if a["vendor"] == "Intel"]
    assert len(npu) == 1
    acc = npu[0]
    assert acc["model"] == "Intel AI Boost NPU"
    assert acc["device_node"] == "/dev/accel/accel0"
    assert acc["driver_loaded"] is True
    assert acc["driver_name"] == "intel_vpu"
    assert acc["driver_version"] == "1.8.0"
    assert acc["runtime_available"] is True
    assert acc["status"] == "active"


def test_intel_npu_not_detected(monkeypatch):
    """No Intel NPU when /dev/accel/accel0 doesn't exist."""
    outputs = {("lsmod",): "intel_vpu 12345 0\n"}
    _mock_run_command(monkeypatch, outputs)
    _mock_file_exists(monkeypatch, set())

    info = get_accelerator_info()
    intel = [a for a in info["accelerators"] if a["vendor"] == "Intel"]
    assert len(intel) == 0


# ─────────────────────────────────────────────────────────────────────────────
# AMD XDNA NPU
# ─────────────────────────────────────────────────────────────────────────────

def test_amd_npu_detected(monkeypatch):
    """AMD XDNA NPU detected via amdxdna driver."""
    outputs = {
        ("lsmod",): "amdxdna 12345 0\n",
        ("xrt-smi", "examine"): "Version: 2.17.0\nDevice 0: NPU\n",
    }
    _mock_run_command(monkeypatch, outputs)
    _mock_file_exists(monkeypatch, {"/dev/accel/accel0"})

    info = get_accelerator_info()

    npu = [a for a in info["accelerators"] if a["vendor"] == "AMD"]
    assert len(npu) == 1
    acc = npu[0]
    assert acc["model"] == "AMD XDNA NPU"
    assert acc["tops"] == 50
    assert acc["driver_loaded"] is True
    assert acc["driver_name"] == "amdxdna"
    assert acc["runtime_available"] is True
    assert acc["status"] == "active"


# ─────────────────────────────────────────────────────────────────────────────
# Apple Neural Engine
# ─────────────────────────────────────────────────────────────────────────────

def test_apple_ane_detected(monkeypatch):
    """Apple ANE detected on Apple Silicon."""
    outputs = {
        ("sysctl", "-n", "machdep.cpu.brand_string"): "Apple M1 Ultra",
    }
    _mock_run_command(monkeypatch, outputs, platform_system="Darwin")
    import halbert_core.utils.platform as plat
    monkeypatch.setattr(plat, "is_mac_apple_silicon", lambda: True)

    info = get_accelerator_info()

    ane = [a for a in info["accelerators"] if a["type"] == "ane"]
    assert len(ane) == 1
    acc = ane[0]
    assert acc["vendor"] == "Apple"
    assert acc["model"] == "Apple Neural Engine"
    assert acc["form_factor"] == "integrated"
    assert acc["driver_loaded"] is True
    assert acc["runtime_available"] is True
    assert acc["runtime_version"] == "CoreML"
    assert acc["status"] == "active"
    assert acc["tops"] == 22  # M1 Ultra
    assert info["has_ane"] is True


def test_apple_ane_not_on_intel_mac(monkeypatch):
    """No ANE on Intel Macs."""
    _mock_run_command(monkeypatch, {}, platform_system="Darwin")
    import halbert_core.utils.platform as plat
    monkeypatch.setattr(plat, "is_mac_apple_silicon", lambda: False)

    info = get_accelerator_info()
    assert info["accelerators"] == []
    assert info["has_ane"] is False


# ─────────────────────────────────────────────────────────────────────────────
# Empty / no accelerators
# ─────────────────────────────────────────────────────────────────────────────

def test_no_accelerators(monkeypatch):
    """No accelerators on a system with none."""
    _mock_run_command(monkeypatch, {})
    _mock_file_exists(monkeypatch, set())

    info = get_accelerator_info()

    assert info["accelerators"] == []
    assert info["has_tpu"] is False
    assert info["has_npu"] is False
    assert info["has_ane"] is False
    assert info["total_tops"] is None
    assert info["issues"] == []


# ─────────────────────────────────────────────────────────────────────────────
# Tool handlers and registration
# ─────────────────────────────────────────────────────────────────────────────

class TestAcceleratorToolHandlers:
    def test_accelerator_info_handler_returns_json(self, monkeypatch):
        _mock_run_command(monkeypatch, {})
        _mock_file_exists(monkeypatch, set())

        result = json.loads(asyncio.run(ACCELERATOR_TOOL_HANDLERS["accelerator_info"]({})))

        assert "accelerators" in result
        assert isinstance(result["accelerators"], list)


def test_register_accelerator_tools():
    class FakeExecutor:
        def __init__(self):
            self.registered = {}

        def register(self, name, handler, schema):
            self.registered[name] = (handler, schema)

    executor = FakeExecutor()
    register_accelerator_tools(executor)

    assert set(executor.registered) == set(ACCELERATOR_TOOL_SCHEMAS)
    assert set(ACCELERATOR_TOOL_HANDLERS) == set(ACCELERATOR_TOOL_SCHEMAS)
    for name, (handler, schema) in executor.registered.items():
        assert handler is ACCELERATOR_TOOL_HANDLERS[name]
        assert schema is ACCELERATOR_TOOL_SCHEMAS[name]
        assert schema["name"] == name
        assert "description" in schema
