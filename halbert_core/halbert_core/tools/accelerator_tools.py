# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
AI Accelerator Tools

Detection and monitoring of AI accelerators beyond GPUs: TPUs, NPUs,
and Neural Engines. These are increasingly common on Home Assistant
servers (Coral Edge TPU, Hailo-8 for Frigate) and modern SoCs (Intel
NPU, AMD XDNA NPU, Apple Neural Engine).

Each probe detects presence, driver status, and live stats where
available. All probes degrade gracefully — missing tools or devices
return empty lists, not errors.

The accelerator list is returned alongside the GPU list by the same
HTTP route and agent tool, so the AI gets a complete picture of the
machine's AI compute capacity.
"""

from __future__ import annotations

import json
import platform
import re
import subprocess
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("halbert.tools.accelerator")


def run_command(cmd: List[str], timeout: int = 10) -> Optional[str]:
    """Run a command and return stdout, or None on error."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return result.stdout.strip() if result.returncode == 0 else None
    except Exception:
        return None


def _make_accelerator_dict(
    acc_type: str,
    vendor: str,
    model: str,
) -> Dict[str, Any]:
    """Create an accelerator dict with all fields."""
    return {
        "type": acc_type,           # "tpu" | "npu" | "ane"
        "vendor": vendor,
        "model": model,
        "form_factor": None,        # "usb" | "m.2" | "mini_pcie" | "pcie" | "integrated"
        "device_node": None,        # "/dev/apex_0", "/dev/hailo0", etc.
        "tops": None,               # peak INT8 throughput
        "driver_loaded": False,
        "driver_name": None,
        "driver_version": None,
        "firmware_version": None,
        "temperature_c": None,
        "utilization_percent": None,
        "power_draw_w": None,
        "runtime_available": False,
        "runtime_version": None,
        "status": "not_detected",   # "active" | "idle" | "missing_driver" | "missing_runtime" | "not_detected"
    }


# ─────────────────────────────────────────────────────────────────────────────
# Coral Edge TPU probe
# ─────────────────────────────────────────────────────────────────────────────

# Coral PCI vendor/device IDs
_CORAL_PCI_VENDOR = "1ac1"
_CORAL_PCI_DEVICE = "089a"
_CORAL_USB_VENDOR = "1a6e"
_CORAL_USB_PRODUCT = "089a"


def _probe_coral_edgetpu() -> List[Dict]:
    """Detect Google Coral Edge TPU devices (USB, M.2, Mini PCIe).

    Detection:
    - PCIe/M.2: lspci vendor 1ac1:089a, device node /dev/apex_*
    - USB: lsusb vendor 1a6e:089a
    - Driver: apex/gasket kernel module
    - Temperature: sysfs (PCIe only; USB Coral has no temp sensor)
    """
    accelerators: List[Dict] = []
    if platform.system() != "Linux":
        return accelerators

    # PCIe Coral
    lspci = run_command(["lspci", "-nn"])
    if lspci:
        for line in lspci.split("\n"):
            if _CORAL_PCI_VENDOR in line and _CORAL_PCI_DEVICE in line:
                acc = _make_accelerator_dict("tpu", "Google", "Coral Edge TPU")
                acc["form_factor"] = "pcie"
                # Extract PCI address
                pci_match = re.match(r'^([0-9a-f:.]+)', line)
                if pci_match:
                    acc["pci_id"] = pci_match.group(1)
                # Check for device node
                import os
                for i in range(4):
                    node = f"/dev/apex_{i}"
                    if os.path.exists(node):
                        acc["device_node"] = node
                        break
                # Check driver
                lsmod = run_command(["lsmod"])
                if lsmod and ("apex" in lsmod or "gasket" in lsmod):
                    acc["driver_loaded"] = True
                    acc["driver_name"] = "apex"
                    acc["status"] = "active"
                else:
                    acc["status"] = "missing_driver"
                # Temperature from sysfs (millidegree Celsius)
                acc["temperature_c"] = _read_coral_temp_sysfs()
                accelerators.append(acc)

    # USB Coral
    lsusb = run_command(["lsusb"])
    if lsusb:
        for line in lsusb.split("\n"):
            if _CORAL_USB_VENDOR in line and _CORAL_USB_PRODUCT in line:
                acc = _make_accelerator_dict("tpu", "Google", "Coral Edge TPU (USB)")
                acc["form_factor"] = "usb"
                acc["tops"] = 4
                # Check if edgetpu runtime is installed
                runtime = run_command(["python3", "-c",
                    "from pycoral.utils import edgetpu; print('available')"])
                if runtime and "available" in runtime:
                    acc["runtime_available"] = True
                    acc["runtime_version"] = "pycoral"
                # USB Coral has no temperature sensor
                acc["status"] = "active" if acc["runtime_available"] else "missing_runtime"
                accelerators.append(acc)

    return accelerators


def _read_coral_temp_sysfs() -> Optional[float]:
    """Read Coral Edge TPU temperature from sysfs.

    The exact path varies by carrier board. Common locations:
    /sys/class/apex/apex_0/device/temp
    """
    import glob
    for temp_path in glob.glob("/sys/class/apex/apex_*/device/temp"):
        try:
            with open(temp_path) as f:
                # Temperature is in millidegree Celsius
                millideg = int(f.read().strip())
                return millideg / 1000.0
        except (OSError, ValueError):
            continue
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Hailo probe
# ─────────────────────────────────────────────────────────────────────────────

_HAILO_PCI_VENDOR = "1e60"


def _probe_hailo() -> List[Dict]:
    """Detect Hailo-8 / Hailo-8L / Hailo-10H AI accelerators.

    Detection:
    - lspci: vendor 1e60 (Co-processor class)
    - hailortcli scan: lists devices
    - hailortcli fw-control identify: firmware version, serial
    - Driver: hailo_pci (Hailo-8/8L) or hailo1x_pci (Hailo-10H)
    """
    accelerators: List[Dict] = []
    if platform.system() != "Linux":
        return accelerators

    lspci = run_command(["lspci"])
    if not lspci:
        return accelerators

    hailo_count = 0
    for line in lspci.split("\n"):
        if _HAILO_PCI_VENDOR in line and ("Hailo" in line or "Co-processor" in line):
            hailo_count += 1
            # Determine model from lspci line
            model = "Hailo AI Processor"
            if "Hailo-8L" in line:
                model = "Hailo-8L"
                tops = 13
            elif "Hailo-8" in line:
                model = "Hailo-8"
                tops = 26
            elif "Hailo-10H" in line:
                model = "Hailo-10H"
                tops = 40
            else:
                tops = None

            acc = _make_accelerator_dict("npu", "Hailo", model)
            acc["form_factor"] = "m.2"
            acc["tops"] = tops
            acc["device_node"] = "/dev/hailo0"

            # Check driver
            lsmod = run_command(["lsmod"])
            if lsmod:
                if "hailo1x_pci" in lsmod:
                    acc["driver_loaded"] = True
                    acc["driver_name"] = "hailo1x_pci"
                elif "hailo_pci" in lsmod:
                    acc["driver_loaded"] = True
                    acc["driver_name"] = "hailo_pci"

            # Check runtime via hailortcli
            hailortcli = run_command(["hailortcli", "scan"])
            if hailortcli and "Hailo" in hailortcli:
                acc["runtime_available"] = True
                # Get firmware version
                fw_info = run_command(["hailortcli", "fw-control", "identify"])
                if fw_info:
                    fw_match = re.search(r"Firmware\s+:\s*(\S+)", fw_info)
                    if fw_match:
                        acc["firmware_version"] = fw_match.group(1)
                    # Get driver version from modinfo
                    modinfo = run_command(["modinfo", acc["driver_name"] or "hailo_pci"])
                    if modinfo:
                        ver_match = re.search(r"version:\s*(\S+)", modinfo)
                        if ver_match:
                            acc["driver_version"] = ver_match.group(1)

            acc["status"] = "active" if acc["driver_loaded"] and acc["runtime_available"] else \
                           "missing_driver" if not acc["driver_loaded"] else "missing_runtime"
            accelerators.append(acc)

    return accelerators


# ─────────────────────────────────────────────────────────────────────────────
# MemryX MX3 probe
# ─────────────────────────────────────────────────────────────────────────────

_MEMRYX_PCI_VENDOR = "1ed9"


def _probe_memryx() -> List[Dict]:
    """Detect MemryX MX3 AI accelerators.

    Detection:
    - lspci: vendor 1ed9
    - Device node: /dev/memx0
    - Driver: memx_cascade_plus_pcie
    - Runtime: mxa-manager service
    """
    accelerators: List[Dict] = []
    if platform.system() != "Linux":
        return accelerators

    lspci = run_command(["lspci"])
    if not lspci:
        return accelerators

    for line in lspci.split("\n"):
        if _MEMRYX_PCI_VENDOR in line:
            acc = _make_accelerator_dict("npu", "MemryX", "MX3")
            acc["form_factor"] = "m.2"
            acc["tops"] = 26
            acc["device_node"] = "/dev/memx0"

            # Check driver
            lsmod = run_command(["lsmod"])
            if lsmod and "memx_cascade_plus_pcie" in lsmod:
                acc["driver_loaded"] = True
                acc["driver_name"] = "memx_cascade_plus_pcie"

            # Check runtime
            import os
            if os.path.exists("/dev/memx0"):
                acc["runtime_available"] = True

            acc["status"] = "active" if acc["driver_loaded"] and acc["runtime_available"] else \
                           "missing_driver" if not acc["driver_loaded"] else "missing_runtime"
            accelerators.append(acc)

    return accelerators


# ─────────────────────────────────────────────────────────────────────────────
# Intel NPU probe
# ─────────────────────────────────────────────────────────────────────────────

_INTEL_NPU_PCI_IDS = ["8086:ad1d", "8086:677e", "8086:7d19"]


def _probe_intel_npu() -> List[Dict]:
    """Detect Intel NPU (Meteor Lake / Arrow Lake / Lunar Lake / Panther Lake).

    Detection:
    - /dev/accel/accel0 (driver: intel_vpu)
    - lsmod | grep intel_vpu
    - PCI ID 8086:ad1d (Arrow Lake), others for Meteor/Lunar Lake
    - Runtime: OpenVINO + Level Zero
    """
    accelerators: List[Dict] = []
    if platform.system() != "Linux":
        return accelerators

    import os
    if not os.path.exists("/dev/accel/accel0"):
        return accelerators

    acc = _make_accelerator_dict("npu", "Intel", "Intel AI Boost NPU")
    acc["form_factor"] = "integrated"
    acc["device_node"] = "/dev/accel/accel0"

    # Check driver
    lsmod = run_command(["lsmod"])
    if lsmod and "intel_vpu" in lsmod:
        acc["driver_loaded"] = True
        acc["driver_name"] = "intel_vpu"
        # Get driver version
        modinfo = run_command(["modinfo", "intel_vpu"])
        if modinfo:
            ver_match = re.search(r"version:\s*(\S+)", modinfo)
            if ver_match:
                acc["driver_version"] = ver_match.group(1)

    # Check OpenVINO runtime
    openvino = run_command(["python3", "-c",
        "from openvino.runtime import Core; print(Core().available_devices)"])
    if openvino and "NPU" in openvino:
        acc["runtime_available"] = True
        acc["runtime_version"] = "openvino"

    # Try to get NPU stats from sysfs (requires root for some metrics)
    # npu-monitor-tool reads /sys/class/intel_pmt/ — we do a basic check
    acc["status"] = "active" if acc["driver_loaded"] and acc["runtime_available"] else \
                   "missing_driver" if not acc["driver_loaded"] else "missing_runtime"
    accelerators.append(acc)

    return accelerators


# ─────────────────────────────────────────────────────────────────────────────
# AMD XDNA NPU probe
# ─────────────────────────────────────────────────────────────────────────────

def _probe_amd_npu() -> List[Dict]:
    """Detect AMD XDNA NPU (Strix Halo / Ryzen AI 300).

    Detection:
    - /dev/accel/accel0 with amdxdna driver (shared device node with Intel)
    - lsmod | grep amdxdna
    - xrt-smi examine (XRT tool)
    """
    accelerators: List[Dict] = []
    if platform.system() != "Linux":
        return accelerators

    import os
    # AMD NPU also uses /dev/accel/accel0 but with amdxdna driver
    lsmod = run_command(["lsmod"])
    if not lsmod or "amdxdna" not in lsmod:
        return accelerators

    acc = _make_accelerator_dict("npu", "AMD", "AMD XDNA NPU")
    acc["form_factor"] = "integrated"
    acc["tops"] = 50  # Strix Halo XDNA 2

    if os.path.exists("/dev/accel/accel0"):
        acc["device_node"] = "/dev/accel/accel0"

    acc["driver_loaded"] = True
    acc["driver_name"] = "amdxdna"

    # Check XRT runtime
    xrt_smi = run_command(["xrt-smi", "examine"])
    if xrt_smi:
        acc["runtime_available"] = True
        ver_match = re.search(r"Version:\s*(\S+)", xrt_smi)
        if ver_match:
            acc["runtime_version"] = ver_match.group(1)

    acc["status"] = "active" if acc["runtime_available"] else "missing_runtime"
    accelerators.append(acc)

    return accelerators


# ─────────────────────────────────────────────────────────────────────────────
# Apple Neural Engine probe
# ─────────────────────────────────────────────────────────────────────────────

def _probe_apple_ane() -> List[Dict]:
    """Detect Apple Neural Engine (ANE).

    The ANE is always present on Apple Silicon (M1+). It's a coprocessor
    on the SoC, not a separate device. Power/frequency monitoring requires
    `powermetrics --samplers ane_power` (sudo), so baseline detection is
    presence-only.
    """
    if platform.system() != "Darwin":
        return []

    try:
        from ..utils.platform import is_mac_apple_silicon
        if not is_mac_apple_silicon():
            return []
    except Exception:
        import os
        if os.uname().machine != "arm64":
            return []

    acc = _make_accelerator_dict("ane", "Apple", "Apple Neural Engine")
    acc["form_factor"] = "integrated"
    acc["driver_loaded"] = True
    acc["driver_name"] = "ane"
    acc["runtime_available"] = True
    acc["runtime_version"] = "CoreML"
    acc["status"] = "active"

    # ANE TOPS by model (approximate, INT8)
    model_str = run_command(["sysctl", "-n", "machdep.cpu.brand_string"]) or ""
    if "Ultra" in model_str:
        acc["tops"] = 22  # M1 Ultra: ~22 TOPS
    elif "Max" in model_str:
        acc["tops"] = 11
    else:
        acc["tops"] = 11  # baseline

    return [acc]


# ─────────────────────────────────────────────────────────────────────────────
# Dispatcher
# ─────────────────────────────────────────────────────────────────────────────

def get_accelerator_info() -> Dict[str, Any]:
    """Detect all AI accelerators (TPUs, NPUs, ANEs) on the system.

    Runs all applicable probes and merges results. Each probe degrades
    gracefully — missing tools or devices return empty lists.

    Returns a dict with an ``accelerators`` list and summary flags.
    """
    accelerators: List[Dict] = []
    issues: List[str] = []

    # Linux probes
    if platform.system() == "Linux":
        accelerators.extend(_probe_coral_edgetpu())
        accelerators.extend(_probe_hailo())
        accelerators.extend(_probe_memryx())
        accelerators.extend(_probe_intel_npu())
        accelerators.extend(_probe_amd_npu())

    # macOS probe
    if platform.system() == "Darwin":
        accelerators.extend(_probe_apple_ane())

    # Summary
    has_tpu = any(a["type"] == "tpu" for a in accelerators)
    has_npu = any(a["type"] == "npu" for a in accelerators)
    has_ane = any(a["type"] == "ane" for a in accelerators)
    total_tops = sum(a["tops"] for a in accelerators if a["tops"])

    # Issues for detected but non-functional accelerators
    for acc in accelerators:
        if acc["status"] == "missing_driver":
            issues.append(
                f"{acc['vendor']} {acc['model']} detected but driver not loaded. "
                f"Install the {acc['driver_name'] or 'kernel'} driver."
            )
        elif acc["status"] == "missing_runtime":
            issues.append(
                f"{acc['vendor']} {acc['model']} driver loaded but runtime not available. "
                f"Install the {acc['vendor']} runtime software."
            )

    return {
        "accelerators": accelerators,
        "has_tpu": has_tpu,
        "has_npu": has_npu,
        "has_ane": has_ane,
        "total_tops": total_tops if total_tops else None,
        "issues": issues,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Agent tool handlers
# ─────────────────────────────────────────────────────────────────────────────

async def _accelerator_info_handler(args: Dict) -> str:
    """Get AI accelerator hardware information."""
    info = get_accelerator_info()
    return json.dumps(info, indent=2, default=str)


ACCELERATOR_TOOL_SCHEMAS = {
    "accelerator_info": {
        "name": "accelerator_info",
        "description": (
            "Detect AI accelerators (TPUs, NPUs, Neural Engines) on this system: "
            "Google Coral Edge TPU, Hailo-8/8L/10H, MemryX MX3, Intel NPU, "
            "AMD XDNA NPU, Apple Neural Engine. Reports TOPS, driver status, "
            "runtime availability, temperature, and utilization where available."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
}

ACCELERATOR_TOOL_HANDLERS = {
    "accelerator_info": _accelerator_info_handler,
}


def register_accelerator_tools(tool_executor) -> None:
    """Register accelerator tools with the tool executor."""
    for name, schema in ACCELERATOR_TOOL_SCHEMAS.items():
        handler = ACCELERATOR_TOOL_HANDLERS[name]
        tool_executor.register(name, handler, schema)
    logger.info(f"Registered {len(ACCELERATOR_TOOL_SCHEMAS)} accelerator tools")
