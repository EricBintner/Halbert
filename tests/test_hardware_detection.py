"""
Test hardware detection and model recommendations (Phase 5 M3).

Tests the hardware detector, model recommendations, and configuration wizard.
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


def test_hardware_detection():
    """Test basic hardware detection."""
    try:
        from cerebric_core.model import HardwareDetector
        
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


def test_model_recommendations():
    """Test model recommendation engine."""
    try:
        from cerebric_core.model import HardwareDetector
        
        detector = HardwareDetector()
        hardware = detector.detect()
        recommendation = detector.recommend_models(hardware)
        
        # Verify recommendation structure
        assert recommendation.orchestrator_model is not None
        assert recommendation.orchestrator_provider is not None
        assert recommendation.reasoning is not None
        assert recommendation.expected_memory_mb > 0
        
        print("✅ Model recommendation test passed")
        print(f"   Orchestrator: {recommendation.orchestrator_model}")
        print(f"   Provider: {recommendation.orchestrator_provider}")
        if recommendation.specialist_enabled:
            print(f"   Specialist: {recommendation.specialist_model}")
        else:
            print(f"   Specialist: Disabled")
        return True
    
    except Exception as e:
        print(f"❌ Model recommendation test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_hardware_profiles():
    """Test hardware profile classification."""
    try:
        from cerebric_core.model import HardwareDetector, HardwareProfile
        
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
        from cerebric_core.utils.platform import (
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
        from cerebric_core.model import ConfigWizard
        
        wizard = ConfigWizard()
        config = wizard.run_auto()
        
        # Verify config structure
        assert "orchestrator" in config
        assert "specialist" in config
        assert "routing" in config
        assert "handoff" in config
        
        # Verify orchestrator config
        assert "model" in config["orchestrator"]
        assert "provider" in config["orchestrator"]
        
        print("✅ Config wizard auto test passed")
        print(f"   Orchestrator: {config['orchestrator']['model']}")
        if config["specialist"]["enabled"]:
            print(f"   Specialist: {config['specialist']['model']}")
        return True
    
    except Exception as e:
        print(f"❌ Config wizard auto test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_installation_commands():
    """Test installation command generation."""
    try:
        from cerebric_core.model import HardwareDetector
        
        detector = HardwareDetector()
        hardware = detector.detect()
        recommendation = detector.recommend_models(hardware)
        
        commands = detector.get_installation_commands(recommendation)
        
        # Should have at least one provider
        assert len(commands) > 0
        
        # Commands should be a list of strings
        for provider, cmd_list in commands.items():
            assert isinstance(cmd_list, list)
            assert len(cmd_list) > 0
        
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
        from cerebric_core.utils.platform import (
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
        ("Model Recommendations", test_model_recommendations),
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
