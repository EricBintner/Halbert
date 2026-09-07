# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
AI Accelerator Scanner - Discover TPU/NPU/ANE hardware.

GPU-1 Phase 6: Converges discovery with the universal accelerator_tools
probe so the dashboard, agent, and discovery feed all share one telemetry
source.

Discovers:
- Google Coral Edge TPU (USB, M.2, Mini PCIe)
- Hailo-8 / 8L / 10H
- MemryX MX3
- Intel NPU (Meteor/Arrow/Lunar/Panther Lake)
- AMD XDNA NPU
- Apple Neural Engine
"""

from __future__ import annotations
from typing import List

from .base import BaseScanner
from ..schema import (
    Discovery,
    DiscoveryType,
    DiscoverySeverity,
    DiscoveryAction,
    make_discovery_id,
)


class AiAcceleratorScanner(BaseScanner):
    """
    Scanner for AI accelerators using the universal accelerator_tools probe.

    Reuses ``get_accelerator_info()`` so discovery, dashboard, and agent
    all see the same normalized data.
    """

    @property
    def discovery_type(self) -> DiscoveryType:
        return DiscoveryType.AI_ACCELERATOR

    def is_available(self) -> bool:
        """Available on Linux and macOS (the probe handles platform dispatch)."""
        import platform
        return platform.system() in ("Linux", "Darwin")

    def scan(self) -> List[Discovery]:
        """Scan for AI accelerator hardware via the universal probe."""
        discoveries: List[Discovery] = []

        try:
            from ...tools.accelerator_tools import get_accelerator_info
            info = get_accelerator_info()
        except Exception as e:
            self.logger.error(f"Accelerator probe failed: {e}")
            return discoveries

        accelerators = info.get("accelerators", [])
        issues = info.get("issues", [])

        for acc in accelerators:
            discoveries.append(self._accelerator_to_discovery(acc))

        # Surface issues for detected-but-non-functional accelerators
        if not accelerators and issues:
            discoveries.append(Discovery(
                id=make_discovery_id(DiscoveryType.AI_ACCELERATOR, "probe-issues"),
                type=DiscoveryType.AI_ACCELERATOR,
                name="probe-issues",
                title="AI Accelerator Issues",
                description="; ".join(issues[:3]),
                icon="alert-triangle",
                severity=DiscoverySeverity.WARNING,
                status="Issues",
                data={"issues": issues},
                chat_context="AI accelerator probe reported issues: " + "; ".join(issues),
            ))

        self.logger.info(f"Found {len(discoveries)} AI accelerator discoveries")
        return discoveries

    def _accelerator_to_discovery(self, acc: dict) -> Discovery:
        """Convert a normalized accelerator dict into a Discovery object."""
        vendor = acc.get("vendor", "Unknown")
        model = acc.get("model", "Unknown Accelerator")
        acc_type = acc.get("type", "npu")
        status = acc.get("status", "not_detected")
        tops = acc.get("tops")
        form_factor = acc.get("form_factor")
        device_node = acc.get("device_node")

        # Severity from status
        if status == "active":
            severity = DiscoverySeverity.SUCCESS
        elif status in ("missing_driver", "missing_runtime"):
            severity = DiscoverySeverity.WARNING
        elif status == "idle":
            severity = DiscoverySeverity.INFO
        else:
            severity = DiscoverySeverity.INFO

        # Build a stable ID
        safe_id = f"{vendor.lower()}-{model.lower().replace(' ', '-').replace('/', '-')}"
        discovery_id = make_discovery_id(DiscoveryType.AI_ACCELERATOR, safe_id)

        # Description
        desc_parts = [vendor]
        if tops:
            desc_parts.append(f"{tops} TOPS")
        if form_factor:
            desc_parts.append(form_factor)
        desc_parts.append(acc_type.upper())
        description = " · ".join(desc_parts)

        # Data payload
        data = {
            "type": acc_type,
            "vendor": vendor,
            "model": model,
            "form_factor": form_factor,
            "device_node": device_node,
            "tops": tops,
            "driver_loaded": acc.get("driver_loaded"),
            "driver_name": acc.get("driver_name"),
            "driver_version": acc.get("driver_version"),
            "firmware_version": acc.get("firmware_version"),
            "temperature_c": acc.get("temperature_c"),
            "utilization_percent": acc.get("utilization_percent"),
            "power_draw_w": acc.get("power_draw_w"),
            "runtime_available": acc.get("runtime_available"),
            "runtime_version": acc.get("runtime_version"),
            "status": status,
            "is_ai_accelerator": True,
        }

        # Chat context
        ctx_parts = [f"AI accelerator: {model} ({vendor}). Type: {acc_type.upper()}."]
        if tops:
            ctx_parts.append(f"Performance: {tops} TOPS.")
        if acc.get("driver_loaded"):
            ctx_parts.append(f"Driver: {acc.get('driver_name') or 'loaded'} {acc.get('driver_version') or ''}.")
        else:
            ctx_parts.append("Driver not loaded.")
        if acc.get("runtime_available"):
            ctx_parts.append(f"Runtime: {acc.get('runtime_version') or 'available'}.")
        elif status == "missing_runtime":
            ctx_parts.append("Runtime not available.")
        if acc.get("temperature_c") is not None:
            ctx_parts.append(f"Temperature: {acc['temperature_c']:.0f}C.")
        if acc.get("utilization_percent") is not None:
            ctx_parts.append(f"Utilization: {acc['utilization_percent']}%.")

        return Discovery(
            id=discovery_id,
            type=DiscoveryType.AI_ACCELERATOR,
            name=safe_id,
            title=model,
            description=description,
            icon="cpu",
            severity=severity,
            status=status.replace("_", " ").title(),
            data=data,
            actions=[
                DiscoveryAction(
                    id="chat",
                    label="Chat",
                    icon="message-circle",
                ),
            ],
            chat_context=" ".join(ctx_parts),
        )
