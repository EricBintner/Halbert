# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Hardware detection for TTS execution provider selection.

Probes the host for available ONNX Runtime execution providers and
classifies the hardware tier so the TTS engine can pick the right
model, quantization, and thread count.

Tiers (from the handoff):
  1 — High-end GPU workstation (CUDA >= 40GB VRAM, or Apple Silicon >= 32GB)
  2 — Standard desktop (CUDA < 40GB, or Apple Silicon < 32GB, or modern CPU)
  3 — Low-power (Intel N100/N150, Raspberry Pi 5, similar)
  4 — Mobile (iOS/Android — remote stream by default)

Providers are probed lazily and cached. A probe that fails degrades to
"cpu" — never raises. The detection is deliberately conservative: it
only claims a provider is available after a probe succeeds.
"""

from __future__ import annotations

import logging
import os
import platform
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from typing import List, Optional

logger = logging.getLogger("halbert.audio.hardware_detect")


@dataclass(frozen=True)
class HardwareProfile:
    """Detected hardware capabilities for TTS/ASR execution.

    ``tier`` is the coarse classification (1-4). ``providers`` is the
    ordered list of available ONNX Runtime execution providers, best
    first. ``vram_gb`` is the GPU VRAM (or Apple Silicon unified memory)
    when detectable, else None. ``cpu_cores`` is the logical core count.
    """

    tier: int = 2
    providers: tuple = ("cpu",)
    vram_gb: Optional[float] = None
    cpu_cores: int = 4
    is_apple_silicon: bool = False
    is_mobile: bool = False

    @property
    def best_provider(self) -> str:
        """The highest-priority available provider."""
        return self.providers[0] if self.providers else "cpu"

    @property
    def recommended_threads(self) -> int:
        """Thread count appropriate for this hardware.

    Tier 1: up to 8 threads. Tier 2: up to 4. Tier 3: 1-2. Mobile: 1.
    """
        if self.is_mobile:
            return 1
        if self.tier == 1:
            return min(8, self.cpu_cores)
        if self.tier == 2:
            return min(4, self.cpu_cores)
        if self.tier == 3:
            return min(2, self.cpu_cores)
        return 1

    @property
    def recommended_quantization(self) -> str:
        """Model quantization hint: 'fp16', 'fp32', or 'int8'.

    Tier 1 can afford fp32. Tier 2 uses fp16. Tier 3 needs int8.
    """
        if self.tier == 1:
            return "fp32"
        if self.tier == 2:
            return "fp16"
        return "int8"


@lru_cache(maxsize=1)
def detect_hardware() -> HardwareProfile:
    """Probe the host and return a cached HardwareProfile.

    Safe to call from any thread. The result is cached for the process
    lifetime — hardware does not change at runtime.
    """
    cpu_cores = os.cpu_count() or 4
    is_apple_silicon = platform.machine() == "arm64" and platform.system() == "Darwin"
    is_mobile = platform.system() in ("iOS", "Android")

    # --- Provider detection ---
    providers: List[str] = ["cpu"]  # CPU is always available

    # Try onnxruntime for provider enumeration.
    try:
        import onnxruntime as ort
        available = ort.get_available_providers()
        # Order by preference: CUDA > CoreML > NNAPI > DirectML > CPU
        for p in ("CUDAExecutionProvider", "CoreMLExecutionProvider",
                  "NNAPIExecutionProvider", "DmlExecutionProvider"):
            if p in available and p not in providers:
                providers.insert(0, p)
    except ImportError:
        pass

    # Fallback: check for CUDA via nvidia-smi (no onnxruntime needed).
    if "CUDAExecutionProvider" not in providers:
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=3,
            )
            if result.returncode == 0 and result.stdout.strip():
                # nvidia-smi succeeded — CUDA is present even if ORT
                # wasn't built with CUDA support. Insert it so the
                # config can still request it.
                if "CUDAExecutionProvider" not in providers:
                    providers.insert(0, "CUDAExecutionProvider")
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

    # --- VRAM detection ---
    vram_gb: Optional[float] = None

    if "CUDAExecutionProvider" in providers:
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=3,
            )
            if result.returncode == 0 and result.stdout.strip():
                vram_gb = float(result.stdout.strip().split("\n")[0]) / 1024
        except (FileNotFoundError, subprocess.TimeoutExpired, ValueError):
            pass

    if is_apple_silicon and vram_gb is None:
        # Apple Silicon: unified memory. Use sysctl to get total RAM.
        try:
            result = subprocess.run(
                ["sysctl", "-n", "hw.memsize"],
                capture_output=True, text=True, timeout=3,
            )
            if result.returncode == 0:
                total_bytes = int(result.stdout.strip())
                vram_gb = total_bytes / (1024 ** 3)
        except (FileNotFoundError, subprocess.TimeoutExpired, ValueError):
            pass

    # --- Tier classification ---
    if is_mobile:
        tier = 4
    elif "CUDAExecutionProvider" in providers and vram_gb is not None:
        tier = 1 if vram_gb >= 40 else 2
    elif is_apple_silicon and vram_gb is not None:
        tier = 1 if vram_gb >= 32 else 2
    elif is_apple_silicon:
        tier = 2  # Apple Silicon without memory detection — assume desktop
    elif cpu_cores <= 4:
        # Low-power: N100/N150/RPi5 typically have 4-8 cores but low TDP.
        # Check for known low-power CPU model strings.
        model = platform.processor() or ""
        if any(s in model.lower() for s in ("n100", "n150", "n97", "n200")):
            tier = 3
        elif "raspberry" in (platform.uname().release or "").lower():
            tier = 3
        else:
            tier = 2
    else:
        tier = 2  # Modern desktop CPU

    profile = HardwareProfile(
        tier=tier,
        providers=tuple(providers),
        vram_gb=vram_gb,
        cpu_cores=cpu_cores,
        is_apple_silicon=is_apple_silicon,
        is_mobile=is_mobile,
    )

    logger.info(
        f"Hardware detected: tier={tier}, providers={providers}, "
        f"vram={vram_gb}, cores={cpu_cores}, apple_silicon={is_apple_silicon}"
    )
    return profile


def recommended_tts_config(profile: HardwareProfile) -> dict:
    """Map a HardwareProfile to TTS config values.

    Returns a dict with ``engine``, ``num_threads``, ``execution_provider``,
    and ``quantization`` — the fields the TTS config uses to select and
    tune the engine.
    """
    p = profile
    return {
        "execution_provider": p.best_provider,
        "num_threads": p.recommended_threads,
        "quantization": p.recommended_quantization,
        "hardware_tier": p.tier,
    }
