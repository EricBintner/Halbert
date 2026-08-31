# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Hardware detection and profiling (Phase 5 M3).

Detects system resources (RAM / VRAM / GPU / Apple Silicon) and converts
them into a model *size budget* -- the largest parameter count that fits at
4-bit and 8-bit quantization. It never names or recommends specific models;
the user picks whichever model fits the budget.
"""

from __future__ import annotations
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
import re
from enum import Enum
import psutil
import platform
import subprocess
import logging

from ..utils.platform import (
    is_linux, is_macos, is_mac_apple_silicon,
    get_unified_memory_gb, get_platform_info,
    detect_metal_gpu, apple_intelligence_eligible,
)
from ..obs.logging import get_logger

logger = get_logger("halbert")


class HardwareProfile(str, Enum):
    """Hardware profile categories."""
    SBC_LOW_POWER = "sbc_low_power"       # <=4GB RAM (Pi 4 2GB, legacy Celeron)
    ENTRY_8GB = "entry_8gb"               # 4-8GB RAM (N100, Pi 5 4GB, older laptops)
    LAPTOP_16GB = "laptop_16gb"
    WORKSTATION_32GB = "workstation_32gb"
    WORKSTATION_64GB = "workstation_64gb"
    MAC_STUDIO_128GB = "mac_studio_128gb"
    SERVER_128GB_PLUS = "server_128gb_plus"
    UNKNOWN = "unknown"


@dataclass
class HardwareCapabilities:
    """
    Hardware capabilities and constraints.
    
    Used to derive a model size budget for configuration.
    """
    total_ram_gb: int
    available_ram_gb: float
    cpu_count: int
    platform: str
    platform_friendly: str
    
    # GPU info (if available)
    has_nvidia_gpu: bool = False
    has_amd_gpu: bool = False
    gpu_memory_gb: Optional[int] = None
    
    # Mac-specific
    is_apple_silicon: bool = False
    unified_memory_gb: Optional[int] = None

    # Apple Intelligence (FoundationModels) — on-device LLM via ANE
    metal_gpu: Optional[Dict[str, Any]] = None
    apple_intelligence_available: bool = False
    apple_intelligence_bridge_running: bool = False

    # Computed profile
    profile: HardwareProfile = HardwareProfile.UNKNOWN

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging/serialization."""
        return {
            "total_ram_gb": self.total_ram_gb,
            "available_ram_gb": self.available_ram_gb,
            "cpu_count": self.cpu_count,
            "platform": self.platform,
            "platform_friendly": self.platform_friendly,
            "has_nvidia_gpu": self.has_nvidia_gpu,
            "has_amd_gpu": self.has_amd_gpu,
            "gpu_memory_gb": self.gpu_memory_gb,
            "is_apple_silicon": self.is_apple_silicon,
            "unified_memory_gb": self.unified_memory_gb,
            "metal_gpu": self.metal_gpu,
            "apple_intelligence_available": self.apple_intelligence_available,
            "apple_intelligence_bridge_running": self.apple_intelligence_bridge_running,
            "profile": self.profile.value,
        }


# Rough memory cost per billion parameters, including KV-cache / runtime
# overhead. Used only to translate a memory budget into a parameter count.
GB_PER_BILLION_PARAMS_4BIT = 0.65
GB_PER_BILLION_PARAMS_8BIT = 1.15

# Fraction of each memory pool that can realistically hold model weights.
UNIFIED_MEMORY_FRACTION = 0.75   # macOS caps GPU use of unified memory
VRAM_RESERVE_GB = 1.0            # driver / display headroom on discrete GPUs
SYSTEM_RAM_FRACTION = 0.6        # leave room for the OS and other processes


@dataclass
class ModelBudget:
    """
    Model size budget derived from detected hardware.

    Expressed as parameter counts and memory, never as model names --
    the user chooses any model that fits.
    """
    memory_budget_gb: float
    max_params_b_4bit: int
    max_params_b_8bit: int
    memory_source: str          # "unified", "vram" or "ram"
    provider: str               # runtime suited to this platform (ollama / mlx / llamacpp)

    summary: str = ""
    notes: List[str] = field(default_factory=list)

    # True when the profile cannot run any useful local model and all LLM
    # work is offloaded to a compute peer (SBC_LOW_POWER).
    offload_only: bool = False

    def fits(self, params_b: float, bits: int = 4) -> bool:
        """Return True if a model of ``params_b`` billion parameters fits."""
        limit = self.max_params_b_8bit if bits >= 8 else self.max_params_b_4bit
        return params_b <= limit

    def fits_bytes(self, size_bytes: int, overhead: float = 1.2) -> bool:
        """Return True if weights of ``size_bytes`` (plus runtime overhead) fit."""
        return (size_bytes / (1024 ** 3)) * overhead <= self.memory_budget_gb

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for configuration / API responses."""
        return {
            "memory_budget_gb": round(self.memory_budget_gb, 1),
            "max_params_b_4bit": self.max_params_b_4bit,
            "max_params_b_8bit": self.max_params_b_8bit,
            "memory_source": self.memory_source,
            "provider": self.provider,
            "summary": self.summary,
            "notes": self.notes,
            "offload_only": self.offload_only,
        }


# Backwards-compatible name kept for ``halbert_core.model`` re-exports.
ModelRecommendation = ModelBudget


_PARAM_SIZE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*([mMbB])\b")
_NAME_TAG_RE = re.compile(r":(?:(\d+)x)?(\d+(?:\.\d+)?)b(?:[-_.]|$)", re.IGNORECASE)


def parse_parameter_size(value: Optional[str]) -> Optional[float]:
    """
    Parse a parameter-size string ("7.6B", "137M") into billions of parameters.

    Returns None when the value cannot be parsed.
    """
    if not value:
        return None
    m = _PARAM_SIZE_RE.search(str(value))
    if not m:
        return None
    number = float(m.group(1))
    unit = m.group(2).lower()
    return number / 1000.0 if unit == "m" else number


def estimate_model_params_b(model: Dict[str, Any]) -> Optional[float]:
    """
    Estimate parameter count (billions) for an Ollama ``/api/tags`` entry.

    Prefers runtime metadata (``details.parameter_size``), then a generic
    size tag in the name (":7b", ":8x22b"), then the weight file size.
    """
    details = model.get("details") or {}
    params = parse_parameter_size(details.get("parameter_size"))
    if params is not None:
        return params

    name = model.get("name") or model.get("model") or ""
    m = _NAME_TAG_RE.search(name)
    if m:
        experts = int(m.group(1)) if m.group(1) else 1
        return experts * float(m.group(2))

    size_bytes = model.get("size")
    if isinstance(size_bytes, (int, float)) and size_bytes > 0:
        # Assume 4-bit weights when nothing better is known.
        return round(size_bytes / (1024 ** 3) / 0.55, 1)

    return None


def pick_installed_model(models: List[Dict[str, Any]], budget: ModelBudget) -> Optional[Dict[str, Any]]:
    """
    Choose the largest already-installed model that fits the budget.

    Args:
        models: Raw entries from Ollama ``GET /api/tags`` (``data["models"]``).
        budget: Size budget from :meth:`HardwareDetector.recommend_budget`.

    Returns:
        The chosen entry (with an added ``params_b`` key) or None when no
        installed model fits. Embedding models are skipped.
    """
    if budget.offload_only:
        # Offload-only profiles run no local model at all — nothing fits,
        # not even the ~1B size the raw memory arithmetic would allow.
        return None

    best: Optional[Dict[str, Any]] = None
    best_key = (-1.0, -1.0)

    for entry in models or []:
        name = entry.get("name") or entry.get("model") or ""
        if not name or "embed" in name.lower():
            continue

        size_bytes = entry.get("size") or 0
        params_b = estimate_model_params_b(entry)

        if size_bytes and not budget.fits_bytes(size_bytes):
            continue
        if not size_bytes and (params_b is None or not budget.fits(params_b)):
            continue

        key = (params_b or 0.0, float(size_bytes))
        if key > best_key:
            best_key = key
            best = dict(entry)
            best["params_b"] = params_b

    return best


class HardwareDetector:
    """
    Detect system hardware and derive a model size budget.
    
    Phase 5 M3: Auto-configuration based on hardware
    
    Usage:
        detector = HardwareDetector()
        hardware = detector.detect()
        budget = detector.recommend_budget(hardware)
        
        print(f"Profile: {hardware.profile}")
        print(budget.summary)
    """
    
    def __init__(self):
        """Initialize hardware detector."""
        logger.info("HardwareDetector initialized")
    
    def detect(self) -> HardwareCapabilities:
        """
        Detect hardware capabilities.
        
        Returns:
            HardwareCapabilities with detected system info
        """
        logger.info("Detecting hardware capabilities")
        
        # Get basic system info
        total_ram_bytes = psutil.virtual_memory().total
        available_ram_bytes = psutil.virtual_memory().available
        total_ram_gb = total_ram_bytes // (1024 ** 3)
        available_ram_gb = available_ram_bytes / (1024 ** 3)
        cpu_count = psutil.cpu_count(logical=False) or 1
        
        # Platform info
        platform_info = get_platform_info()
        platform_name = platform_info["platform"]
        platform_friendly = platform_info.get("recommended_provider", platform_name)
        
        # GPU detection
        has_nvidia = self._detect_nvidia_gpu()
        has_amd = self._detect_amd_gpu()
        gpu_memory = self._get_gpu_memory() if (has_nvidia or has_amd) else None
        
        # Mac-specific
        is_apple = is_mac_apple_silicon()
        unified_mem = get_unified_memory_gb() if is_apple else None
        metal = detect_metal_gpu() if is_apple else None

        # Apple Intelligence: eligible by hardware, available if the bridge
        # is also running. The bridge may not be bundled yet (Swift sidecar
        # is a separate deliverable), so eligibility without the bridge is
        # a valid state — the endpoint is registered but inert until the
        # bridge exists.
        ai_eligible = apple_intelligence_eligible() if is_apple else False
        bridge_running = False
        if ai_eligible:
            bridge_running = self._probe_apple_foundation_bridge()

        # Create capabilities object
        capabilities = HardwareCapabilities(
            total_ram_gb=total_ram_gb,
            available_ram_gb=available_ram_gb,
            cpu_count=cpu_count,
            platform=platform_name,
            platform_friendly=str(platform_friendly),
            has_nvidia_gpu=has_nvidia,
            has_amd_gpu=has_amd,
            gpu_memory_gb=gpu_memory,
            is_apple_silicon=is_apple,
            unified_memory_gb=unified_mem,
            metal_gpu=metal,
            apple_intelligence_available=ai_eligible,
            apple_intelligence_bridge_running=bridge_running,
        )
        
        # Determine hardware profile
        capabilities.profile = self._classify_hardware(capabilities)
        
        logger.info("Hardware detection complete", extra=capabilities.to_dict())
        
        return capabilities
    
    def _detect_nvidia_gpu(self) -> bool:
        """Detect NVIDIA GPU."""
        try:
            result = subprocess.run(
                ["nvidia-smi", "-L"],
                capture_output=True,
                timeout=2
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False
    
    def _detect_amd_gpu(self) -> bool:
        """Detect AMD GPU."""
        try:
            result = subprocess.run(
                ["rocm-smi", "--showproductname"],
                capture_output=True,
                timeout=2
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False
    
    def _get_gpu_memory(self) -> Optional[int]:
        """Get GPU memory in GB."""
        # Try NVIDIA
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
                capture_output=True,
                text=True,
                timeout=2
            )
            if result.returncode == 0:
                # Returns MB, convert to GB
                memory_mb = int(result.stdout.strip().split('\n')[0])
                return memory_mb // 1024
        except (FileNotFoundError, subprocess.TimeoutExpired, ValueError):
            pass
        
        # Try AMD
        try:
            result = subprocess.run(
                ["rocm-smi", "--showmeminfo", "vram"],
                capture_output=True,
                text=True,
                timeout=2
            )
            if result.returncode == 0:
                # Parse output for memory size
                # This is a simplified version
                return None
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        return None

    def _probe_apple_foundation_bridge(self) -> bool:
        """Check whether the Swift FoundationModels bridge is running on loopback.

        The bridge (``halbert-foundation-bridge``) is a Tauri sidecar that
        exposes Apple Intelligence via an OpenAI-compatible HTTP server on
        port 11435. When it answers, Apple Intelligence is fully available;
        when it does not, the host is *eligible* but the endpoint is inert
        until the bridge is bundled and started.
        """
        try:
            import requests as _requests
            resp = _requests.get(
                "http://127.0.0.1:11435/v1/models",
                timeout=0.5,
            )
            return resp.status_code == 200
        except Exception:
            return False

    def _classify_hardware(self, hw: HardwareCapabilities) -> HardwareProfile:
        """
        Classify hardware into a profile category.
        
        Args:
            hw: Hardware capabilities
        
        Returns:
            Hardware profile classification
        """
        # Mac Apple Silicon with 128GB (user's setup!)
        if hw.is_apple_silicon and hw.unified_memory_gb and hw.unified_memory_gb >= 96:
            return HardwareProfile.MAC_STUDIO_128GB
        
        # High-end server/workstation
        if hw.total_ram_gb >= 96:
            return HardwareProfile.SERVER_128GB_PLUS
        
        # Workstation 64GB
        if hw.total_ram_gb >= 48:
            return HardwareProfile.WORKSTATION_64GB
        
        # Workstation 32GB
        if hw.total_ram_gb >= 24:
            return HardwareProfile.WORKSTATION_32GB
        
        # Laptop 16GB
        if hw.total_ram_gb >= 12:
            return HardwareProfile.LAPTOP_16GB
        
        # Entry-level 8GB (N100, Pi 5 4GB, older laptops)
        if hw.total_ram_gb >= 4:
            return HardwareProfile.ENTRY_8GB
        
        # Single-board / very low power (Pi 4 2GB, etc.)
        return HardwareProfile.SBC_LOW_POWER
    
    def recommend_budget(self, hw: HardwareCapabilities) -> ModelBudget:
        """
        Convert detected hardware into a model size budget.
        
        Args:
            hw: Hardware capabilities

        Returns:
            ModelBudget with the largest parameter counts that fit at 4-bit
            and 8-bit quantization, plus a human-readable summary. For
            SBC_LOW_POWER the budget is offload-only: zeroed parameter
            counts, because a compute peer is required for LLM
            functionality on these devices.
        """
        logger.info(f"Computing model size budget for profile: {hw.profile}")

        # SBC_LOW_POWER (<4GB RAM) runs no local model. The generic
        # arithmetic below would still emit a ~1B-parameter budget on a 2GB
        # host (2GB x 0.6 / 0.65), but a model that small is inadequate for
        # any slot that needs it — so the tier is dropped entirely and all
        # LLM work is offloaded to a compute peer, with template thoughts
        # covering the peer-asleep gap.
        if hw.profile == HardwareProfile.SBC_LOW_POWER:
            logger.info("SBC_LOW_POWER profile — offload-only budget (no local model)")
            return ModelBudget(
                memory_budget_gb=0.0,
                max_params_b_4bit=0,
                max_params_b_8bit=0,
                memory_source="ram",
                provider="peer",
                summary=(
                    "Local LLM inference is not supported on this device: "
                    "offload only — a compute peer is required for LLM functionality."
                ),
                notes=[
                    "Offload only — a compute peer is required for LLM functionality",
                    "Point this node at a peer with: halbert config-wizard --peer <hostname:port>",
                    "While the peer is asleep, template thoughts stand in for LLM responses",
                ],
                offload_only=True,
            )

        if hw.is_apple_silicon and hw.unified_memory_gb:
            memory_gb = hw.unified_memory_gb * UNIFIED_MEMORY_FRACTION
            source = "unified"
            provider = "mlx"
        elif (hw.has_nvidia_gpu or hw.has_amd_gpu) and hw.gpu_memory_gb:
            memory_gb = max(hw.gpu_memory_gb - VRAM_RESERVE_GB, 0.0)
            source = "vram"
            provider = "ollama"
        else:
            memory_gb = hw.total_ram_gb * SYSTEM_RAM_FRACTION
            source = "ram"
            provider = "ollama"
        
        max_4bit = int(memory_gb // GB_PER_BILLION_PARAMS_4BIT)
        max_8bit = int(memory_gb // GB_PER_BILLION_PARAMS_8BIT)
        
        source_label = {
            "unified": "unified memory",
            "vram": "GPU VRAM",
            "ram": "system RAM",
        }[source]
        summary = (
            f"About {memory_gb:.0f} GB of {source_label} is available for model weights: "
            f"a ~{max_4bit}B-parameter model at 4-bit quantization or a ~{max_8bit}B model "
            f"at 8-bit fits."
        )
        
        notes: List[str] = []
        if source == "unified":
            notes.append("Apple Silicon shares memory between CPU and GPU; MLX or Ollama both work")
        elif source == "vram":
            notes.append("Models larger than VRAM spill to system RAM and run much slower")
        else:
            notes.append("No discrete GPU detected; inference runs on the CPU")
        if max_4bit >= 30:
            notes.append("Enough headroom to keep a guide model and a larger specialist loaded at once")
        else:
            notes.append("Best used with a single model; a second model would split this budget")
        notes.append("Parameter counts are estimates -- check the model's actual download size")
        
        return ModelBudget(
            memory_budget_gb=memory_gb,
            max_params_b_4bit=max_4bit,
            max_params_b_8bit=max_8bit,
            memory_source=source,
            provider=provider,
            summary=summary,
            notes=notes,
        )
    
    def get_installation_commands(self, budget: ModelBudget) -> Dict[str, List[str]]:
        """
        Get generic installation commands for the budget's runtime.
        
        The commands use a ``<model>`` placeholder; no model is named.
        
        Args:
            budget: Model size budget

        Returns:
            Dict with installation commands per provider. Offload-only
            budgets get peer-configuration guidance instead of a local
            model install/pull block.
        """
        commands: Dict[str, List[str]] = {}

        if budget.offload_only:
            # No local model is installed or pulled on an offload-only
            # device; the only setup is pointing it at a compute peer.
            commands["peer"] = [
                "# This device runs no local model — all LLM work is offloaded",
                "# to a compute peer (a Halbert node with a GPU or Apple Silicon).",
                "",
                "# Point this node at the peer (hostname:port, LAN IP, or Tailscale name):",
                "halbert config-wizard --peer <hostname:port>",
            ]
            return commands

        if budget.provider == "mlx":
            commands["mlx"] = [
                "# Install MLX (Mac Apple Silicon only)",
                "pip install mlx mlx-lm",
                "",
                "# Models are downloaded from HuggingFace Hub on first use",
                f"# Choose one of up to ~{budget.max_params_b_4bit}B parameters at 4-bit",
            ]
        
        commands["ollama"] = [
            "# Install Ollama",
            "curl -fsSL https://ollama.com/install.sh | sh",
            "",
            f"# Pull any model of up to ~{budget.max_params_b_4bit}B parameters (4-bit)",
            "ollama pull <model>",
            "",
            "# Then select it in Halbert: Settings -> AI Models",
        ]
        
        return commands
