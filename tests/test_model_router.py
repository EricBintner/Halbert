"""
Test model router infrastructure (Phase 5 M1).

Tests the router, providers, and configuration system.
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


def test_router_initialization():
    """Test that ModelRouter can be initialized."""
    try:
        from cerebric_core.cerebric_core.model import ModelRouter
        
        router = ModelRouter()
        assert router is not None
        
        print("✅ ModelRouter initialization test passed")
        return True
    
    except Exception as e:
        print(f"❌ ModelRouter initialization failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_router_status():
    """Test getting router status."""
    try:
        from cerebric_core.cerebric_core.model import ModelRouter
        
        router = ModelRouter()
        status = router.get_status()
        
        assert "orchestrator" in status
        assert "specialist" in status
        assert "providers" in status
        
        print("✅ Router status test passed")
        print(f"   Providers: {list(status['providers'].keys())}")
        return True
    
    except Exception as e:
        print(f"❌ Router status test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_task_classification():
    """Test task type classification."""
    try:
        from cerebric_core.cerebric_core.model import TaskType
        
        # Test all task types exist
        assert TaskType.CHAT is not None
        assert TaskType.CODE_GENERATION is not None
        assert TaskType.CODE_ANALYSIS is not None
        assert TaskType.SYSTEM_COMMAND is not None
        assert TaskType.REASONING is not None
        assert TaskType.QUICK_QUERY is not None
        
        print("✅ Task classification test passed")
        print(f"   Task types: {[t.value for t in TaskType]}")
        return True
    
    except Exception as e:
        print(f"❌ Task classification test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_provider_abstraction():
    """Test provider interface."""
    try:
        from cerebric_core.cerebric_core.model.providers import (
            ModelProvider, ModelCapability, OllamaProvider
        )
        
        # Test Ollama provider
        ollama = OllamaProvider()
        assert ollama is not None
        
        # Test capabilities enum
        assert ModelCapability.CHAT is not None
        assert ModelCapability.CODE is not None
        
        print("✅ Provider abstraction test passed")
        print(f"   Capabilities: {[c.value for c in ModelCapability]}")
        return True
    
    except Exception as e:
        print(f"❌ Provider abstraction test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_configuration_loading():
    """Test configuration system."""
    try:
        from cerebric_core.cerebric_core.model import ModelRouter
        
        router = ModelRouter()
        config = router.config
        
        assert "orchestrator" in config
        assert "specialist" in config
        assert "routing" in config
        
        print("✅ Configuration loading test passed")
        print(f"   Orchestrator: {config.get('orchestrator', {}).get('model')}")
        return True
    
    except Exception as e:
        print(f"❌ Configuration loading test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all model router tests."""
    print("=" * 70)
    print("MODEL ROUTER TESTS (Phase 5 M1)")
    print("=" * 70)
    print()
    
    tests = [
        ("Router Initialization", test_router_initialization),
        ("Router Status", test_router_status),
        ("Task Classification", test_task_classification),
        ("Provider Abstraction", test_provider_abstraction),
        ("Configuration Loading", test_configuration_loading),
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
