"""
Configuration wizard for model setup (Phase 5 M3).

Interactive wizard to help users configure models based on their hardware.
"""

from __future__ import annotations
from typing import Dict, Any, Optional
from pathlib import Path
import yaml

from .hardware_detector import HardwareDetector, HardwareCapabilities, ModelRecommendation
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
    
    def get_recommendation(self, hardware: HardwareCapabilities) -> ModelRecommendation:
        """
        Get model recommendation for hardware.
        
        Args:
            hardware: Hardware capabilities
        
        Returns:
            Model recommendation
        """
        return self.detector.recommend_models(hardware)
    
    def run_auto(self) -> Dict[str, Any]:
        """
        Run automatic configuration (non-interactive).
        
        Detects hardware and creates optimal configuration automatically.
        
        Returns:
            Configuration dictionary
        """
        logger.info("Running automatic configuration")
        
        # Detect hardware
        hardware = self.detect_hardware()
        logger.info(f"Detected profile: {hardware.profile.value}")
        
        # Get recommendation
        recommendation = self.get_recommendation(hardware)
        logger.info(f"Recommended: {recommendation.orchestrator_model}")
        
        # Build configuration
        config = self._build_config(recommendation, hardware)
        
        return config
    
    def run_interactive(self) -> Dict[str, Any]:
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
        
        # Get recommendation
        print("💡 Generating recommendation...")
        recommendation = self.get_recommendation(hardware)
        
        # Show recommendation
        print()
        print("Recommended Configuration:")
        print(f"  Orchestrator: {recommendation.orchestrator_model} ({recommendation.orchestrator_provider})")
        
        if recommendation.specialist_enabled:
            print(f"  Specialist: {recommendation.specialist_model} ({recommendation.specialist_provider})")
        else:
            print(f"  Specialist: Disabled (orchestrator-only mode)")
        
        print()
        print(f"Reasoning: {recommendation.reasoning}")
        print()
        print(f"Expected Memory Usage: {recommendation.expected_memory_mb}MB")
        
        if recommendation.performance_notes:
            print()
            print("Performance Notes:")
            for note in recommendation.performance_notes:
                print(f"  • {note}")
        
        print()
        
        # Ask for confirmation
        choice = input("Accept this configuration? [Y/n]: ").strip().lower()
        
        if choice in ('n', 'no'):
            print()
            print("Configuration cancelled. You can manually edit ~/.config/halbert/models.yml")
            return {}
        
        # Build configuration
        config = self._build_config(recommendation, hardware)
        
        print()
        print("✅ Configuration created!")
        
        return config
    
    def _build_config(
        self,
        recommendation: ModelRecommendation,
        hardware: HardwareCapabilities
    ) -> Dict[str, Any]:
        """
        Build configuration dictionary from recommendation.
        
        Args:
            recommendation: Model recommendation
            hardware: Hardware capabilities
        
        Returns:
            Configuration dictionary
        """
        config = {
            "# Halbert Model Configuration": None,
            "# Generated by configuration wizard": None,
            "# Edit this file to customize model selection": None,
            
            "orchestrator": {
                "model": recommendation.orchestrator_model,
                "provider": recommendation.orchestrator_provider,
                "always_loaded": True,
            },
            
            "specialist": {
                "enabled": recommendation.specialist_enabled,
                "model": recommendation.specialist_model,
                "provider": recommendation.specialist_provider or "ollama",
                "load_strategy": "on_demand",
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
    
    def show_installation_instructions(self, recommendation: ModelRecommendation):
        """
        Show installation instructions for recommended models.
        
        Args:
            recommendation: Model recommendation
        """
        print()
        print("=" * 70)
        print("INSTALLATION INSTRUCTIONS")
        print("=" * 70)
        print()
        
        commands = self.detector.get_installation_commands(recommendation)
        
        for provider, cmd_list in commands.items():
            print(f"Provider: {provider.upper()}")
            print()
            for cmd in cmd_list:
                print(cmd)
            print()
        
        print("After installation, models will be automatically downloaded on first use.")
        print()
    
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
            required = ["orchestrator", "specialist", "routing", "handoff"]
            for key in required:
                if key not in config:
                    logger.error(f"Missing required key: {key}")
                    return False
            
            # Check orchestrator
            if "model" not in config["orchestrator"]:
                logger.error("Orchestrator missing 'model' key")
                return False
            
            logger.info("Configuration validated successfully")
            return True
        
        except Exception as e:
            logger.error(f"Configuration validation failed: {e}")
            return False
    
    def generate_summary(self, hardware: HardwareCapabilities, recommendation: ModelRecommendation) -> str:
        """
        Generate human-readable configuration summary.
        
        Args:
            hardware: Hardware capabilities
            recommendation: Model recommendation
        
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
        lines.append("Configuration:")
        lines.append(f"  Orchestrator: {recommendation.orchestrator_model}")
        lines.append(f"    Provider: {recommendation.orchestrator_provider}")
        lines.append(f"    Always loaded: Yes")
        
        if recommendation.specialist_enabled:
            lines.append(f"  Specialist: {recommendation.specialist_model}")
            lines.append(f"    Provider: {recommendation.specialist_provider}")
            lines.append(f"    Load strategy: On-demand")
        else:
            lines.append(f"  Specialist: Disabled")
        
        lines.append("")
        lines.append(f"Expected Memory: {recommendation.expected_memory_mb}MB")
        lines.append("")
        lines.append("Reasoning:")
        lines.append(f"  {recommendation.reasoning}")
        
        if recommendation.performance_notes:
            lines.append("")
            lines.append("Performance Notes:")
            for note in recommendation.performance_notes:
                lines.append(f"  • {note}")
        
        lines.append("")
        lines.append("=" * 70)
        
        return "\n".join(lines)
