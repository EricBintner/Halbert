# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
GPU Scanner - Discover GPU hardware using the universal probe registry.

GPU-1 Phase 6: Converges discovery with the normalized gpu_tools probe so
the dashboard, agent, and discovery feed all share one telemetry source.

Discovers:
- Discrete GPUs (NVIDIA, AMD, Intel) with live stats
- Unified-memory GPUs (Apple Silicon, NVIDIA RTX Spark, AMD Strix Halo)
- Integrated GPUs
- Memory architecture classification (discrete / unified / integrated)
- Compute API (CUDA, Metal, ROCm, etc.)
- Driver status and version
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


class GpuScanner(BaseScanner):
    """
    Scanner for GPU hardware using the universal gpu_tools probe registry.

    Reuses ``get_gpu_info()`` so discovery, dashboard, and agent all see
    the same normalized data — no duplicate command parsing.
    """

    @property
    def discovery_type(self) -> DiscoveryType:
        return DiscoveryType.GPU

    def is_available(self) -> bool:
        """Available on Linux and macOS (the probe handles platform dispatch)."""
        import platform
        return platform.system() in ("Linux", "Darwin")

    def scan(self) -> List[Discovery]:
        """Scan for GPU hardware via the universal probe."""
        discoveries: List[Discovery] = []

        try:
            from ...tools.gpu_tools import get_gpu_info
            info = get_gpu_info()
        except Exception as e:
            self.logger.error(f"GPU probe failed: {e}")
            return discoveries

        gpus = info.get("gpus", [])
        issues = info.get("issues", [])

        for i, gpu in enumerate(gpus):
            discoveries.append(self._gpu_to_discovery(gpu, i))

        # If there are global issues but no GPUs, surface them as a single
        # warning discovery so the feed isn't empty.
        if not gpus and issues:
            discoveries.append(Discovery(
                id=make_discovery_id(DiscoveryType.GPU, "probe-issues"),
                type=DiscoveryType.GPU,
                name="probe-issues",
                title="GPU Probe Issues",
                description="; ".join(issues[:3]),
                icon="alert-triangle",
                severity=DiscoverySeverity.WARNING,
                status="Issues",
                data={"issues": issues},
                chat_context="GPU probe reported issues: " + "; ".join(issues),
            ))

        self.logger.info(f"Found {len(discoveries)} GPU discoveries")
        return discoveries

    def _gpu_to_discovery(self, gpu: dict, index: int) -> Discovery:
        """Convert a normalized GPU dict into a Discovery object."""
        vendor = gpu.get("vendor", "Unknown")
        model = gpu.get("model", "Unknown GPU")
        pci_id = gpu.get("pci_id", f"index-{index}")
        mem_arch = gpu.get("memory_architecture", "discrete")
        compute_api = gpu.get("compute_api")
        driver_type = gpu.get("driver_type")
        driver_version = gpu.get("driver_version")

        # Determine severity from driver / issue state
        if not driver_type:
            severity = DiscoverySeverity.WARNING
            status = "No driver"
        elif gpu.get("temperature_c") and gpu["temperature_c"] > 80:
            severity = DiscoverySeverity.WARNING
            status = f"Hot: {gpu['temperature_c']:.0f}C"
        else:
            severity = DiscoverySeverity.SUCCESS
            status = "Active"

        # Build memory label
        if mem_arch == "unified":
            mem_label = "Unified Memory"
            mem_size = gpu.get("unified_memory_gb")
        elif mem_arch == "integrated":
            mem_label = "System RAM"
            mem_size = None
        else:
            mem_label = "VRAM"
            vram_mb = gpu.get("vram_mb")
            mem_size = f"{vram_mb / 1024:.0f} GB" if vram_mb else None

        # Build a stable ID from PCI ID or vendor+model
        safe_id = pci_id.replace(":", "-").replace(" ", "-").lower()
        if not safe_id or safe_id == "unknown":
            safe_id = f"{vendor.lower()}-{index}"
        discovery_id = make_discovery_id(DiscoveryType.GPU, safe_id)

        # Description
        desc_parts = [vendor]
        if compute_api:
            desc_parts.append(compute_api.upper())
        if gpu.get("core_count"):
            desc_parts.append(f"{gpu['core_count']} cores")
        if mem_size:
            desc_parts.append(f"{mem_size} {mem_label}")
        description = " · ".join(desc_parts)

        # Data payload — pass through all normalized fields
        data = {
            "vendor": vendor,
            "model": model,
            "pci_id": pci_id,
            "memory_architecture": mem_arch,
            "memory_source_label": gpu.get("memory_source_label", mem_label),
            "compute_api": compute_api,
            "core_count": gpu.get("core_count"),
            "driver_type": driver_type,
            "driver_version": driver_version,
            "cuda_version": gpu.get("cuda_version"),
            "vram_mb": gpu.get("vram_mb"),
            "unified_memory_gb": gpu.get("unified_memory_gb"),
            "gpu_memory_ceiling_gb": gpu.get("gpu_memory_ceiling_gb"),
            "gpu_memory_in_use_gb": gpu.get("gpu_memory_in_use_gb"),
            "temperature_c": gpu.get("temperature_c"),
            "power_draw_w": gpu.get("power_draw_w"),
            "power_limit_w": gpu.get("power_limit_w"),
            "utilization_percent": gpu.get("utilization_percent"),
            "memory_used_mb": gpu.get("memory_used_mb"),
            "memory_total_mb": gpu.get("memory_total_mb"),
            "role": gpu.get("role", "auto"),
            "is_gpu": True,
        }

        # Chat context
        ctx_parts = [f"GPU: {model} ({vendor})."]
        if compute_api:
            ctx_parts.append(f"Compute API: {compute_api.upper()}.")
        if mem_arch == "unified":
            ctx_parts.append(f"Unified memory architecture — {mem_size or 'unknown size'} shared pool.")
        elif mem_size:
            ctx_parts.append(f"{mem_size} {mem_label}.")
        if driver_type:
            ctx_parts.append(f"Driver: {driver_type} {driver_version or ''}.")
        else:
            ctx_parts.append("No driver detected.")
        if gpu.get("utilization_percent") is not None:
            ctx_parts.append(f"Utilization: {gpu['utilization_percent']}%.")
        if gpu.get("temperature_c") is not None:
            ctx_parts.append(f"Temperature: {gpu['temperature_c']:.0f}C.")

        return Discovery(
            id=discovery_id,
            type=DiscoveryType.GPU,
            name=safe_id,
            title=model,
            description=description,
            icon="cpu",
            severity=severity,
            status=status,
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
