"""
Hardware detection and profiling for model recommendations (Phase 5 M3).

Detects system resources and recommends optimal models for the hardware.
"""

from __future__ import annotations
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from enum import Enum
import psutil
import platform
import subprocess
import logging

from ..utils.platform import (
    is_linux, is_macos, is_mac_apple_silicon,
    get_unified_memory_gb, get_platform_info
)
from ..obs.logging import get_logger

logger = get_logger("halbert")


class HardwareProfile(str, Enum):
    """Hardware profile categories."""
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
    
    Used for model selection and configuration recommendations.
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
            "profile": self.profile.value,
        }


@dataclass
class ModelRecommendation:
    """
    Model recommendation for specific hardware.
    """
    orchestrator_model: str
    orchestrator_provider: str
    
    specialist_model: Optional[str] = None
    specialist_provider: Optional[str] = None
    specialist_enabled: bool = False
    
    reasoning: str = ""
    expected_memory_mb: int = 0
    performance_notes: List[str] = None
    
    def __post_init__(self):
        if self.performance_notes is None:
            self.performance_notes = []
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for configuration."""
        return {
            "orchestrator": {
                "model": self.orchestrator_model,
                "provider": self.orchestrator_provider,
            },
            "specialist": {
                "enabled": self.specialist_enabled,
                "model": self.specialist_model,
                "provider": self.specialist_provider,
            },
            "reasoning": self.reasoning,
            "expected_memory_mb": self.expected_memory_mb,
            "performance_notes": self.performance_notes,
        }


class HardwareDetector:
    """
    Detect system hardware and recommend optimal model configuration.
    
    Phase 5 M3: Auto-configuration based on hardware
    
    Usage:
        detector = HardwareDetector()
        hardware = detector.detect()
        recommendation = detector.recommend_models(hardware)
        
        print(f"Profile: {hardware.profile}")
        print(f"Recommended: {recommendation.orchestrator_model}")
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
        
        return HardwareProfile.UNKNOWN
    
    def recommend_models(self, hw: HardwareCapabilities) -> ModelRecommendation:
        """
        Recommend optimal models for hardware.
        
        Args:
            hw: Hardware capabilities
        
        Returns:
            Model recommendation
        """
        logger.info(f"Generating model recommendation for profile: {hw.profile}")
        
        if hw.profile == HardwareProfile.MAC_STUDIO_128GB:
            return self._recommend_mac_studio_128gb(hw)
        elif hw.profile == HardwareProfile.SERVER_128GB_PLUS:
            return self._recommend_server_128gb_plus(hw)
        elif hw.profile == HardwareProfile.WORKSTATION_64GB:
            return self._recommend_workstation_64gb(hw)
        elif hw.profile == HardwareProfile.WORKSTATION_32GB:
            return self._recommend_workstation_32gb(hw)
        elif hw.profile == HardwareProfile.LAPTOP_16GB:
            return self._recommend_laptop_16gb(hw)
        else:
            return self._recommend_fallback(hw)
    
    def _recommend_mac_studio_128gb(self, hw: HardwareCapabilities) -> ModelRecommendation:
        """Recommend for Mac Studio with 128GB unified memory."""
        return ModelRecommendation(
            orchestrator_model="llama3.1:8b-instruct",
            orchestrator_provider="mlx",  # Use MLX on Apple Silicon!
            specialist_model="deepseek-coder:33b",
            specialist_provider="mlx",
            specialist_enabled=True,
            reasoning="Mac Studio with 128GB unified memory - optimal for MLX provider. "
                     "Can load both orchestrator and specialist simultaneously. "
                     "Excellent for LoRA training and hot-swapping.",
            expected_memory_mb=41000,  # 8GB + 33GB
            performance_notes=[
                "MLX provider optimized for Apple Silicon",
                "Unified memory enables simultaneous model loading",
                "LoRA training supported (QLoRA recommended)",
                "Hot-swap adapters in <2s",
                "Expected: 20+ tokens/sec (orchestrator), 10+ tokens/sec (specialist)"
            ]
        )
    
    def _recommend_server_128gb_plus(self, hw: HardwareCapabilities) -> ModelRecommendation:
        """Recommend for high-end server (128GB+ RAM)."""
        provider = "ollama"
        if hw.has_nvidia_gpu:
            provider = "ollama"  # Ollama with CUDA
        
        return ModelRecommendation(
            orchestrator_model="llama3.1:8b-instruct",
            orchestrator_provider=provider,
            specialist_model="deepseek-coder:33b",
            specialist_provider=provider,
            specialist_enabled=True,
            reasoning=f"High-end server with {hw.total_ram_gb}GB RAM. "
                     f"Can run both orchestrator and large specialist. "
                     f"GPU: {'NVIDIA (CUDA)' if hw.has_nvidia_gpu else 'CPU'}",
            expected_memory_mb=41000,
            performance_notes=[
                "Sufficient RAM for large models",
                "GPU acceleration available" if hw.has_nvidia_gpu else "CPU inference",
                "Can experiment with larger models if needed",
                "Consider Qwen2.5-Coder-32B or CodeLlama-70B for specialist"
            ]
        )
    
    def _recommend_workstation_64gb(self, hw: HardwareCapabilities) -> ModelRecommendation:
        """Recommend for workstation with 64GB RAM."""
        return ModelRecommendation(
            orchestrator_model="llama3.1:8b-instruct",
            orchestrator_provider="ollama",
            specialist_model="deepseek-coder:33b",
            specialist_provider="ollama",
            specialist_enabled=True,
            reasoning=f"Workstation with {hw.total_ram_gb}GB RAM - great balance. "
                     "Can run orchestrator + large specialist (DeepSeek Coder 33B).",
            expected_memory_mb=41000,
            performance_notes=[
                "Optimal for heavy development work",
                "Best code quality with DeepSeek Coder 33B",
                "GPU recommended for faster inference" if not hw.has_nvidia_gpu else "GPU acceleration active",
                "Expected: 15-20 tokens/sec (orchestrator), 8-12 tokens/sec (specialist)"
            ]
        )
    
    def _recommend_workstation_32gb(self, hw: HardwareCapabilities) -> ModelRecommendation:
        """Recommend for workstation with 32GB RAM."""
        return ModelRecommendation(
            orchestrator_model="llama3.1:8b-instruct",
            orchestrator_provider="ollama",
            specialist_model="qwen2.5-coder:14b",
            specialist_provider="ollama",
            specialist_enabled=True,
            reasoning=f"Workstation with {hw.total_ram_gb}GB RAM - good for development. "
                     "Orchestrator + small specialist (Qwen2.5-Coder 14B) for speed.",
            expected_memory_mb=22000,  # 8GB + 14GB
            performance_notes=[
                "Good balance of speed and quality",
                "Qwen2.5-Coder 14B is fast and capable",
                "Sufficient for most coding tasks",
                "Expected: 20+ tokens/sec (orchestrator), 12-15 tokens/sec (specialist)"
            ]
        )
    
    def _recommend_laptop_16gb(self, hw: HardwareCapabilities) -> ModelRecommendation:
        """Recommend for laptop with 16GB RAM."""
        return ModelRecommendation(
            orchestrator_model="llama3.1:8b-instruct",
            orchestrator_provider="ollama",
            specialist_model=None,
            specialist_provider=None,
            specialist_enabled=False,
            reasoning=f"Laptop with {hw.total_ram_gb}GB RAM - run orchestrator only. "
                     "Llama 3.1 8B is very capable for most tasks.",
            expected_memory_mb=8000,
            performance_notes=[
                "Orchestrator-only mode recommended",
                "Llama 3.1 8B handles most tasks well",
                "128k context window is very useful",
                "Enable specialist only when needed",
                "Expected: 15-20 tokens/sec (orchestrator)"
            ]
        )
    
    def _recommend_fallback(self, hw: HardwareCapabilities) -> ModelRecommendation:
        """Fallback recommendation for unknown hardware."""
        return ModelRecommendation(
            orchestrator_model="llama3.1:8b-instruct",
            orchestrator_provider="ollama",
            specialist_model=None,
            specialist_provider=None,
            specialist_enabled=False,
            reasoning=f"Conservative recommendation for {hw.total_ram_gb}GB RAM. "
                     "Start with orchestrator only, enable specialist if performance allows.",
            expected_memory_mb=8000,
            performance_notes=[
                "Conservative configuration",
                "Monitor memory usage",
                "Upgrade to specialist if RAM allows"
            ]
        )
    
    def get_installation_commands(self, recommendation: ModelRecommendation) -> Dict[str, List[str]]:
        """
        Get installation commands for recommended models.
        
        Args:
            recommendation: Model recommendation
        
        Returns:
            Dict with installation commands per provider
        """
        commands = {}
        
        if recommendation.orchestrator_provider == "ollama":
            commands["ollama"] = [
                "# Install Ollama",
                "curl -fsSL https://ollama.com/install.sh | sh",
                "",
                "# Pull orchestrator model",
                f"ollama pull {recommendation.orchestrator_model}",
            ]
            
            if recommendation.specialist_enabled and recommendation.specialist_model:
                commands["ollama"].extend([
                    "",
                    "# Pull specialist model",
                    f"ollama pull {recommendation.specialist_model}",
                ])
        
        elif recommendation.orchestrator_provider == "mlx":
            commands["mlx"] = [
                "# Install MLX (Mac Apple Silicon only)",
                "pip install mlx mlx-lm",
                "",
                "# Models will be downloaded on first use",
                "# MLX uses HuggingFace Hub for model downloads",
            ]
        
        return commands
