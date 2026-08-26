# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Configuration wizard for model setup (Phase 5 M3).

Interactive wizard that detects hardware, reports the model size budget
that fits it, and writes models.yml around the model the user chooses.
It never recommends or names specific models.
"""

from __future__ import annotations
from typing import Dict, Any, Optional
from pathlib import Path
import yaml

from .hardware_detector import (
    HardwareDetector, HardwareCapabilities, ModelBudget, pick_installed_model
)
from ..utils.ollama import list_models_raw, DEFAULT_ENDPOINT
from ..utils.platform import get_config_dir, ensure_directories
from ..obs.logging import get_logger

logger = get_logger("halbert")


class ConfigWizard:
    """
    Interactive configuration wizard for model setup.
    
    Phase 5 M3: User-friendly setup
    
    Usage:
        wizard = ConfigWizard()
        config = wizard.run_interactive()
        wizard.save_config(config)
    """
    
    def __init__(self):
        """Initialize configuration wizard."""
        self.detector = HardwareDetector()
        logger.info("ConfigWizard initialized")
    
    def detect_hardware(self) -> HardwareCapabilities:
        """
        Detect hardware capabilities.
        
        Returns:
            Hardware capabilities
        """
        return self.detector.detect()
    
    def get_budget(self, hardware: HardwareCapabilities) -> ModelBudget:
        """
        Get the model size budget for detected hardware.
        
        Args:
            hardware: Hardware capabilities
        
        Returns:
            Model size budget (parameter counts, never model names)
        """
        return self.detector.recommend_budget(hardware)
    
    def find_installed_model(
        self,
        budget: ModelBudget,
        endpoint: str = DEFAULT_ENDPOINT,
    ) -> Optional[str]:
        """
        Pick the largest model already installed on the endpoint that fits.
        
        Returns:
            Model name, or None when nothing installed fits (or Ollama is down).
        """
        chosen = pick_installed_model(list_models_raw(endpoint), budget)
        return chosen["name"] if chosen else None
    
    def run_auto(self, model: Optional[str] = None, endpoint: str = DEFAULT_ENDPOINT) -> Dict[str, Any]:
        """
        Run automatic configuration (non-interactive).
        
        Detects hardware and writes a configuration around ``model``. When no
        model is given, the largest already-installed model that fits the
        budget is used; if none fits, the guide model is left unset and must
        be chosen in Settings -> AI Models.
        
        Args:
            model: Model name as served by the endpoint (optional)
            endpoint: Ollama endpoint used to look up installed models
        
        Returns:
            Configuration dictionary
        """
        logger.info("Running automatic configuration")
        
        # Detect hardware
        hardware = self.detect_hardware()
        logger.info(f"Detected profile: {hardware.profile.value}")
        
        # Size budget
        budget = self.get_budget(hardware)
        logger.info(f"Model budget: {budget.summary}")
        
        if not model:
            model = self.find_installed_model(budget, endpoint)
        if model:
            logger.info(f"Guide model: {model}")
        else:
            logger.warning("No model configured - choose one in Settings -> AI Models")
        
        # Build configuration
        config = self._build_config(model, "ollama", budget, hardware, endpoint=endpoint)

        return config
    
    def run_interactive(self, endpoint: str = DEFAULT_ENDPOINT) -> Dict[str, Any]:
        """
        Run interactive configuration wizard.
        
        Guides user through setup with prompts.
        
        Returns:
            Configuration dictionary
        """
        print("=" * 70)
        print("Halbert MODEL CONFIGURATION WIZARD")
        print("=" * 70)
        print()
        
        # Detect hardware
        print("🔍 Detecting hardware...")
        hardware = self.detect_hardware()
        
        # Show hardware info
        print()
        print("Hardware Profile:")
        print(f"  Platform: {hardware.platform_friendly}")
        print(f"  RAM: {hardware.total_ram_gb}GB")
        print(f"  CPUs: {hardware.cpu_count}")
        
        if hardware.is_apple_silicon:
            print(f"  Apple Silicon: Yes ({hardware.unified_memory_gb}GB unified memory)")
        if hardware.has_nvidia_gpu:
            print(f"  NVIDIA GPU: Yes ({hardware.gpu_memory_gb}GB VRAM)" if hardware.gpu_memory_gb else "  NVIDIA GPU: Yes")
        
        print(f"  Profile: {hardware.profile.value}")
        print()
        
        # Size budget
        print("📐 Model size budget:")
        budget = self.get_budget(hardware)
        print(f"  {budget.summary}")
        for note in budget.notes:
            print(f"  • {note}")
        print()
        
        # Installed models on the endpoint (the user's own, not suggestions)
        installed = list_models_raw(endpoint)
        default_model = None
        if installed:
            print(f"Models installed on {endpoint}:")
            for entry in installed:
                size_gb = (entry.get("size") or 0) / (1024 ** 3)
                fits = "fits" if budget.fits_bytes(entry.get("size") or 0) else "too large"
                print(f"  - {entry.get('name')}  ({size_gb:.1f} GB, {fits})")
            chosen = pick_installed_model(installed, budget)
            default_model = chosen["name"] if chosen else None
        else:
            print("No models found on the endpoint. Pull one that fits the budget with")
            print("  ollama pull <model>")
        print()
        
        prompt = "Guide model name"
        if default_model:
            prompt += f" [{default_model}]"
        prompt += " (leave blank to choose later in Settings): "
        model = input(prompt).strip() or default_model
        
        print()
        print("Configuration:")
        print(f"  Guide model: {model or 'not set'}")
        print(f"  Provider: ollama")
        print()
        
        # Ask for confirmation
        choice = input("Accept this configuration? [Y/n]: ").strip().lower()
        
        if choice in ('n', 'no'):
            print()
            print("Configuration cancelled. You can manually edit ~/.config/halbert/models.yml")
            return {}
        
        # Build configuration
        config = self._build_config(model, "ollama", budget, hardware, endpoint=endpoint)
        
        print()
        print("✅ Configuration created!")
        if not model:
            print("   No model configured — choose one in Settings → AI Models")
        
        return config
    
    def _build_config(
        self,
        model: Optional[str],
        provider: str,
        budget: ModelBudget,
        hardware: HardwareCapabilities,
        endpoint: str = DEFAULT_ENDPOINT,
    ) -> Dict[str, Any]:
        """
        Build configuration dictionary using the llm_config schema.

        Args:
            model: Chat model name (None leaves the slot unset)
            provider: Runtime serving the model
            budget: Model size budget
            hardware: Hardware capabilities
            endpoint: Endpoint URL for the local Ollama

        Returns:
            Configuration dictionary
        """
        ep_id = "ep_local_ollama" if model else ""
        config = {
            "# Halbert Model Configuration": None,
            "# Generated by configuration wizard": None,
            "# Edit this file to customize model selection": None,

            "llm_config": {
                "saved_endpoints": [
                    {
                        "id": "ep_local_ollama",
                        "name": "Local Ollama",
                        "provider": provider,
                        "url": endpoint,
                        "api_key": "",
                    }
                ] if model else [],
                "chat_model": {
                    "enabled": bool(model),
                    "endpoint_id": ep_id,
                    "model": model or "",
                },
                "specialist_model": {
                    "enabled": False,
                    "endpoint_id": "",
                    "model": "",
                },
                "vision_model": {
                    "enabled": False,
                    "endpoint_id": "",
                    "model": "",
                },
            },

            "routing": {
                "strategy": "auto",
                "prefer_specialist_for": [
                    "code_generation",
                    "code_analysis",
                ],
            },

            "handoff": {
                "strategy": "summarized",
                "max_context_tokens": 4096,
                "include_rag": True,
            },

            "# Hardware Profile": None,
            "hardware": {
                "profile": hardware.profile.value,
                "total_ram_gb": hardware.total_ram_gb,
                "platform": hardware.platform,
                "is_apple_silicon": hardware.is_apple_silicon,
                "model_budget": budget.to_dict(),
            },
        }

        return config
    
    def save_config(self, config: Dict[str, Any], config_path: Optional[Path] = None) -> Path:
        """
        Save configuration to file.
        
        Args:
            config: Configuration dictionary
            config_path: Optional path (defaults to platform config dir)
        
        Returns:
            Path where config was saved
        """
        if not config:
            logger.warning("Empty configuration, not saving")
            return None
        
        # Ensure directories exist
        ensure_directories()
        
        # Determine config path
        if config_path is None:
            config_path = get_config_dir() / 'models.yml'
        
        config_path = Path(config_path)
        config_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Clean config (remove comment keys)
        clean_config = {k: v for k, v in config.items() if not k.startswith('#')}
        
        # Save to YAML
        with open(config_path, 'w') as f:
            # Write comments manually
            f.write("# Halbert Model Configuration\n")
            f.write("# Generated by configuration wizard\n")
            f.write("# Edit this file to customize model selection\n\n")
            
            # Write YAML
            yaml.dump(clean_config, f, default_flow_style=False, sort_keys=False)
        
        logger.info(f"Configuration saved to: {config_path}")
        
        return config_path
    
    def validate_config(self, config_path: Optional[Path] = None) -> bool:
        """
        Validate existing configuration.
        
        Args:
            config_path: Path to config file
        
        Returns:
            True if valid, False otherwise
        """
        if config_path is None:
            config_path = get_config_dir() / 'models.yml'
        
        config_path = Path(config_path)
        
        if not config_path.exists():
            logger.warning(f"Configuration file not found: {config_path}")
            return False
        
        try:
            with open(config_path) as f:
                config = yaml.safe_load(f)

            # Check required keys
            required = ["llm_config", "routing", "handoff"]
            for key in required:
                if key not in config:
                    logger.error(f"Missing required key: {key}")
                    return False

            # Check llm_config has the three slots
            llm = config["llm_config"]
            for slot in ("chat_model", "specialist_model", "vision_model"):
                if slot not in llm:
                    logger.error(f"llm_config missing '{slot}' slot")
                    return False

            logger.info("Configuration validated successfully")
            return True
        
        except Exception as e:
            logger.error(f"Configuration validation failed: {e}")
            return False
    
    def generate_summary(
        self,
        hardware: HardwareCapabilities,
        budget: ModelBudget,
        model: Optional[str] = None,
    ) -> str:
        """
        Generate human-readable configuration summary.
        
        Args:
            hardware: Hardware capabilities
            budget: Model size budget
            model: Configured guide model, if any
        
        Returns:
            Summary string
        """
        lines = []
        lines.append("=" * 70)
        lines.append("Halbert MODEL CONFIGURATION SUMMARY")
        lines.append("=" * 70)
        lines.append("")
        
        lines.append("Hardware:")
        lines.append(f"  Platform: {hardware.platform_friendly}")
        lines.append(f"  RAM: {hardware.total_ram_gb}GB")
        lines.append(f"  Profile: {hardware.profile.value}")
        
        if hardware.is_apple_silicon:
            lines.append(f"  Apple Silicon: {hardware.unified_memory_gb}GB unified memory")
        
        lines.append("")
        lines.append("Model size budget:")
        lines.append(f"  {budget.summary}")
        for note in budget.notes:
            lines.append(f"  • {note}")
        
        lines.append("")
        lines.append("Configuration:")
        lines.append(f"  Guide model: {model or 'not set (choose one in Settings -> AI Models)'}")
        lines.append(f"    Provider: ollama")
        lines.append(f"    Always loaded: Yes")
        lines.append(f"  Specialist: Disabled")
        
        lines.append("")
        lines.append("=" * 70)
        
        return "\n".join(lines)
