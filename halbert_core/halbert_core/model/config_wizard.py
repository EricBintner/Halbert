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

from . import llm_config
from .auto_provision import auto_provision_apple_intelligence
from .hardware_detector import (
    HardwareDetector, HardwareCapabilities, ModelBudget, pick_installed_model
)
from ..utils.ollama import list_models_raw, DEFAULT_ENDPOINT
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

        # Apple Intelligence: provision secure_model (and chat_model on
        # 16-24GB Macs) before looking at Ollama. On 16-24GB Macs the
        # single-model rule means chat_model is already set and the Ollama
        # model lookup below is skipped.
        if hardware.apple_intelligence_available:
            auto_provision_apple_intelligence(hardware)
            logger.info("Apple Intelligence (On-Device) detected — configured as secure model")

        # Size budget
        budget = self.get_budget(hardware)
        logger.info(f"Model budget: {budget.summary}")

        # On 16-24GB Macs with Apple Intelligence, chat_model is already
        # assigned — skip the Ollama model lookup.
        chat_already_set = (
            hardware.apple_intelligence_available
            and hardware.unified_memory_gb
            and hardware.unified_memory_gb <= 24
        )
        if chat_already_set and not model:
            logger.info("Chat model already set to Apple Intelligence (single local model rule)")
        else:
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
        if hardware.metal_gpu:
            print(f"  Metal GPU: {hardware.metal_gpu['gpu_name']} ({hardware.metal_gpu['metal_version']})")
        if hardware.apple_intelligence_available:
            status = "running" if hardware.apple_intelligence_bridge_running else "eligible (bridge not started)"
            print(f"  Apple Intelligence: {status}")
        if hardware.has_nvidia_gpu:
            print(f"  NVIDIA GPU: Yes ({hardware.gpu_memory_gb}GB VRAM)" if hardware.gpu_memory_gb else "  NVIDIA GPU: Yes")

        print(f"  Profile: {hardware.profile.value}")
        print()
        
        # Size budget
        print("Model size budget:")
        budget = self.get_budget(hardware)
        print(f"  {budget.summary}")
        for note in budget.notes:
            print(f"  - {note}")
        print()

        # Apple Intelligence provisioning
        if hardware.apple_intelligence_available:
            auto_provision_apple_intelligence(hardware)
            print("Apple Intelligence (On-Device) detected:")
            print(f"  secure_model: Apple Intelligence (zero download, ANE-powered)")
            mem = hardware.unified_memory_gb or 0
            if mem and mem <= 24:
                print(f"  chat_model: Apple Intelligence (single local model rule for {mem}GB)")
            else:
                print(f"  chat_model: not set (configure cloud or local model in Settings)")
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

        # Apple Intelligence: when the host is eligible, include the
        # apple-foundation endpoint and set secure_model (and chat_model
        # on 16-24GB Macs per the single local model rule). This must be
        # in _build_config because save_config writes ALL slots via
        # deep-merge — an empty secure_model here would clobber what
        # auto_provision_apple_intelligence wrote to the store.
        ai_available = hardware.apple_intelligence_available
        ai_ep_id = "ep_apple_foundation" if ai_available else ""
        ai_model = llm_config.APPLE_FOUNDATION_MODEL if ai_available else ""
        mem = hardware.unified_memory_gb or 0
        ai_takes_chat = ai_available and mem and mem <= 24

        # On 16-24GB Macs with Apple Intelligence, chat_model is set to
        # Apple Intelligence and the Ollama model is not used.
        if ai_takes_chat:
            chat_ep_id = ai_ep_id
            chat_model = ai_model
        else:
            chat_ep_id = ep_id
            chat_model = model or ""

        endpoints = []
        if model and not ai_takes_chat:
            endpoints.append({
                "id": "ep_local_ollama",
                "name": "Local Ollama",
                "provider": provider,
                "url": endpoint,
                "api_key": "",
            })
        if ai_available:
            endpoints.append({
                "id": "ep_apple_foundation",
                "name": "Apple Intelligence (On-Device)",
                "provider": llm_config.APPLE_FOUNDATION_PROVIDER,
                "url": llm_config.APPLE_FOUNDATION_URL,
                "api_key": "",
            })

        config = {
            "# Halbert Model Configuration": None,
            "# Generated by configuration wizard": None,
            "# Edit this file to customize model selection": None,

            "llm_config": {
                "saved_endpoints": endpoints,
                "chat_model": {
                    "enabled": bool(chat_model),
                    "endpoint_id": chat_ep_id,
                    "model": chat_model,
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
                "secure_model": {
                    "enabled": bool(ai_model),
                    "endpoint_id": ai_ep_id,
                    "model": ai_model,
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
                "apple_intelligence_available": hardware.apple_intelligence_available,
                "model_budget": budget.to_dict(),
            },
        }

        return config
    
    def save_config(self, config: Dict[str, Any]) -> Optional[Path]:
        """
        Save configuration through the models.yml store.

        Args:
            config: Configuration dictionary from :meth:`run_auto` /
                :meth:`run_interactive`

        Returns:
            Path the store wrote to, or None when there was nothing to save

        Dumping the whole file in place is what let a rerun of the wizard
        delete every key the store owns but the wizard does not build —
        compression settings, a workspace declaration, saved API keys — and
        leave a file that may hold those keys world-readable. Going through
        the store merges instead, and keeps the backup, atomic rename and
        0600 mode with it.
        """
        if not config:
            logger.warning("Empty configuration, not saving")
            return None

        clean_config = {k: v for k, v in config.items() if not k.startswith('#')}
        llm = dict(clean_config.pop("llm_config", None) or {})

        # Only the store can mint an endpoint id, and a slot naming an id the
        # store never saved is disabled on the next read — so the wizard's own
        # placeholder ids are translated here, not persisted.
        saved_ids = {
            str(ep.get("id") or ""): llm_config.ensure_endpoint(
                ep.get("url") or "",
                ep.get("provider") or "ollama",
                ep.get("name") or "",
            )
            for ep in (llm.pop("saved_endpoints", None) or [])
            if isinstance(ep, dict) and ep.get("url")
        }

        slots: Dict[str, Any] = {}
        for slot in llm_config.SLOTS:
            chosen = llm.get(slot)
            if not isinstance(chosen, dict):
                continue
            endpoint_id = saved_ids.get(str(chosen.get("endpoint_id") or ""), "")
            model = str(chosen.get("model") or "")
            slots[slot] = {
                "enabled": bool(model and endpoint_id),
                "endpoint_id": endpoint_id,
                "model": model,
            }
        llm_config.update(slots)

        for key, value in clean_config.items():
            llm_config.set_top_level(key, value)

        config_path = llm_config.global_config_path()
        logger.info(f"Configuration saved to: {config_path}")

        return config_path

    def validate_config(self, config_path: Optional[Path] = None) -> bool:
        """
        Validate existing configuration.
        
        Args:
            config_path: Path to config file
        
        Returns:
            True if valid, False otherwise

        With no path it validates the file the store actually reads, so
        ``$HALBERT_MODELS_CONFIG`` is not reported as a missing config.
        """
        if config_path is None:
            config_path = llm_config.global_config_path()
        if config_path is None:
            logger.warning("No configuration file found")
            return False

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
            for slot in ("chat_model", "specialist_model", "vision_model", "secure_model"):
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
