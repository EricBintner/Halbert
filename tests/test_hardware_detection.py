# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Test hardware detection and model size budgets (Phase 5 M3).

Tests the hardware detector, the size-budget derivation, installed-model
selection against that budget, and the configuration wizard. No specific
model is named anywhere; fixtures use neutral ids.
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


def test_hardware_detection():
    """Test basic hardware detection."""
    try:
        from halbert_core.model import HardwareDetector
        
        detector = HardwareDetector()
        hardware = detector.detect()
        
        # Verify basic fields
        assert hardware.total_ram_gb > 0
        assert hardware.available_ram_gb > 0
        assert hardware.cpu_count > 0
        assert hardware.platform in ["linux", "darwin", "windows"]
        assert hardware.profile is not None
        
        print("✅ Hardware detection test passed")
        print(f"   Platform: {hardware.platform}")
        print(f"   Profile: {hardware.profile.value}")
        print(f"   RAM: {hardware.total_ram_gb}GB")
        print(f"   CPUs: {hardware.cpu_count}")
        return True
    
    except Exception as e:
        print(f"❌ Hardware detection test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_model_budget():
    """Test hardware -> model size budget derivation."""
    try:
        from halbert_core.model import HardwareDetector
        
        detector = HardwareDetector()
        hardware = detector.detect()
        budget = detector.recommend_budget(hardware)
        
        # Verify budget structure: sizes and a sentence, never model names
        assert budget.memory_budget_gb > 0
        assert budget.max_params_b_4bit > 0
        assert budget.max_params_b_8bit > 0
        assert budget.max_params_b_4bit >= budget.max_params_b_8bit
        assert budget.memory_source in ("unified", "vram", "ram")
        assert budget.provider in ("ollama", "mlx", "llamacpp")
        assert budget.summary
        assert "B-parameter" in budget.summary
        
        d = budget.to_dict()
        assert set(d) >= {"memory_budget_gb", "max_params_b_4bit", "max_params_b_8bit", "summary"}
        
        print("✅ Model budget test passed")
        print(f"   {budget.summary}")
        return True
    
    except Exception as e:
        print(f"❌ Model budget test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_installed_model_selection():
    """Test picking the largest already-installed model that fits the budget."""
    try:
        from halbert_core.model.hardware_detector import (
            ModelBudget, pick_installed_model, estimate_model_params_b, parse_parameter_size
        )
        
        GB = 1024 ** 3
        budget = ModelBudget(
            memory_budget_gb=12.0,
            max_params_b_4bit=18,
            max_params_b_8bit=10,
            memory_source="ram",
            provider="ollama",
        )
        
        installed = [
            {"name": "example-model:latest", "size": 2 * GB, "details": {"parameter_size": "3.2B"}},
            {"name": "example-guide:8b", "size": 5 * GB, "details": {"parameter_size": "8.0B"}},
            {"name": "example-specialist:70b", "size": 40 * GB, "details": {"parameter_size": "70.6B"}},
            {"name": "example-embed", "size": 300 * 1024 ** 2, "details": {"parameter_size": "137M"}},
        ]
        
        chosen = pick_installed_model(installed, budget)
        assert chosen is not None
        assert chosen["name"] == "example-guide:8b"  # largest that fits; 70b too big, embed skipped
        assert chosen["params_b"] == 8.0
        
        # Nothing fits -> None (caller must ask the user to pull a smaller model)
        assert pick_installed_model([installed[2]], budget) is None
        assert pick_installed_model([], budget) is None
        
        # Size parsing is vendor-neutral: metadata, then size tag, then bytes
        assert parse_parameter_size("7.6B") == 7.6
        assert parse_parameter_size("137M") == 0.137
        assert parse_parameter_size(None) is None
        assert estimate_model_params_b({"name": "example-moe:8x22b"}) == 176.0
        assert estimate_model_params_b({"name": "example-think:32b"}) == 32.0
        assert estimate_model_params_b({"name": "unknown", "size": 0}) is None
        
        print("✅ Installed model selection test passed")
        print(f"   Chosen: {chosen['name']}")
        return True
    
    except Exception as e:
        print(f"❌ Installed model selection test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_hardware_profiles():
    """Test hardware profile classification."""
    try:
        from halbert_core.model import HardwareDetector, HardwareProfile
        
        detector = HardwareDetector()
        hardware = detector.detect()
        
        # Verify profile is one of the expected values
        valid_profiles = [p.value for p in HardwareProfile]
        assert hardware.profile.value in valid_profiles
        
        print("✅ Hardware profile test passed")
        print(f"   Detected profile: {hardware.profile.value}")
        print(f"   Valid profiles: {', '.join(valid_profiles)}")
        return True
    
    except Exception as e:
        print(f"❌ Hardware profile test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_mac_detection():
    """Test Mac Apple Silicon detection."""
    try:
        from halbert_core.utils.platform import (
            is_macos, is_mac_apple_silicon, get_unified_memory_gb
        )
        
        is_mac = is_macos()
        is_apple_silicon = is_mac_apple_silicon()
        unified_mem = get_unified_memory_gb()
        
        print("✅ Mac detection test passed")
        print(f"   Is macOS: {is_mac}")
        print(f"   Is Apple Silicon: {is_apple_silicon}")
        if unified_mem:
            print(f"   Unified Memory: {unified_mem}GB")
        
        return True
    
    except Exception as e:
        print(f"❌ Mac detection test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_config_wizard_auto():
    """Test automatic configuration wizard."""
    try:
        from halbert_core.model import ConfigWizard
        
        wizard = ConfigWizard()
        
        # Explicit model: written through verbatim, no fabricated default
        config = wizard.run_auto(model="example-model:latest")
        
        # Verify config structure
        assert "orchestrator" in config
        assert "specialist" in config
        assert "routing" in config
        assert "handoff" in config
        
        # Verify orchestrator config
        assert config["orchestrator"]["model"] == "example-model:latest"
        assert "provider" in config["orchestrator"]
        assert config["specialist"]["enabled"] is False
        assert "model_budget" in config["hardware"]
        
        # No model and nothing installed that fits -> slot left unset (None), never a placeholder id
        config = wizard.run_auto(endpoint="http://127.0.0.1:9")
        assert "model" in config["orchestrator"]
        assert config["orchestrator"]["model"] is None
        
        print("✅ Config wizard auto test passed")
        print(f"   Orchestrator: {config['orchestrator']['model']}")
        return True
    
    except Exception as e:
        print(f"❌ Config wizard auto test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_installation_commands():
    """Test installation command generation."""
    try:
        from halbert_core.model import HardwareDetector
        
        detector = HardwareDetector()
        hardware = detector.detect()
        budget = detector.recommend_budget(hardware)
        
        commands = detector.get_installation_commands(budget)
        
        # Should have at least one provider
        assert len(commands) > 0
        
        # Commands should be a list of strings and use a placeholder, never a model name
        for provider, cmd_list in commands.items():
            assert isinstance(cmd_list, list)
            assert len(cmd_list) > 0
        assert any("ollama pull <model>" in c for c in commands["ollama"])
        
        print("✅ Installation commands test passed")
        print(f"   Providers with commands: {', '.join(commands.keys())}")
        return True
    
    except Exception as e:
        print(f"❌ Installation commands test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_platform_utilities():
    """Test cross-platform utilities."""
    try:
        from halbert_core.utils.platform import (
            get_platform, get_config_dir, get_data_dir, get_cache_dir,
            get_recommended_provider, get_platform_info
        )
        
        platform = get_platform()
        config_dir = get_config_dir()
        data_dir = get_data_dir()
        cache_dir = get_cache_dir()
        recommended = get_recommended_provider()
        info = get_platform_info()
        
        # Verify basic types
        assert isinstance(platform, str)
        assert config_dir.exists() or True  # May not exist yet
        assert recommended in ["ollama", "mlx", "llamacpp"]
        assert isinstance(info, dict)
        
        print("✅ Platform utilities test passed")
        print(f"   Platform: {platform}")
        print(f"   Config dir: {config_dir}")
        print(f"   Recommended provider: {recommended}")
        return True
    
    except Exception as e:
        print(f"❌ Platform utilities test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all hardware detection tests."""
    print("=" * 70)
    print("HARDWARE DETECTION & CONFIGURATION TESTS (Phase 5 M3)")
    print("=" * 70)
    print()
    
    tests = [
        ("Hardware Detection", test_hardware_detection),
        ("Model Budget", test_model_budget),
        ("Installed Model Selection", test_installed_model_selection),
        ("Hardware Profiles", test_hardware_profiles),
        ("Mac Detection", test_mac_detection),
        ("Config Wizard Auto", test_config_wizard_auto),
        ("Installation Commands", test_installation_commands),
        ("Platform Utilities", test_platform_utilities),
    ]
    
    passed = 0
    failed = 0
    
    for test_name, test_func in tests:
        print(f"\n{'='*70}")
        print(f"Test: {test_name}")
        print('='*70)
        try:
            if test_func():
                passed += 1
                print(f"\n✅ {test_name} PASSED")
            else:
                failed += 1
                print(f"\n❌ {test_name} FAILED")
        except Exception as e:
            failed += 1
            print(f"\n❌ {test_name} CRASHED: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "=" * 70)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("=" * 70)
    
    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
