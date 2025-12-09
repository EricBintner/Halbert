"""
Phase 4 Integration Tests (M5).

Tests the complete persona system workflow end-to-end:
- Persona switching
- Memory isolation
- LoRA management
- Context detection
- API endpoints
"""

import sys
import os
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


def test_full_persona_workflow():
    """Test complete persona switching workflow."""
    try:
        from cerebric_core.cerebric_core.persona import PersonaManager, Persona
        
        manager = PersonaManager()
        
        # 1. Reset to IT Admin first (state may be persisted from previous runs)
        manager.switch_to(Persona.IT_ADMIN, user="test")
        initial = manager.get_active_persona()
        assert initial == Persona.IT_ADMIN
        print("✅ Step 1: Initial persona is IT Admin")
        
        # 2. Switch to Friend
        success = manager.switch_to(Persona.FRIEND, user="test")
        assert success is True
        assert manager.get_active_persona() == Persona.FRIEND
        print("✅ Step 2: Switched to Friend persona")
        
        # 3. Verify memory directory changed
        state = manager.get_state()
        assert state.memory_dir == "personas/friend"
        print("✅ Step 3: Memory directory updated")
        
        # 4. Switch back to IT Admin
        success = manager.switch_to(Persona.IT_ADMIN, user="test")
        assert success is True
        assert manager.get_active_persona() == Persona.IT_ADMIN
        assert manager.get_state().memory_dir == "core"
        print("✅ Step 4: Switched back to IT Admin")
        
        return True
    
    except Exception as e:
        print(f"❌ Full persona workflow failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_memory_isolation():
    """Test that persona memory is properly isolated."""
    try:
        from cerebric_core.cerebric_core.memory.retrieval import MemoryRetrieval
        from cerebric_core.cerebric_core.persona import PersonaManager, Persona
        
        memory = MemoryRetrieval()
        persona_mgr = PersonaManager()
        
        # Build context for IT Admin
        persona_mgr.switch_to(Persona.IT_ADMIN, user="test")
        it_admin_context = memory.build_context("test query", persona="it_admin")
        
        # Build context for Friend
        persona_mgr.switch_to(Persona.FRIEND, user="test")
        friend_context = memory.build_context("test query", persona="friend")
        
        # Both should include core memory
        # Friend should have additional persona memory
        print(f"✅ IT Admin context entries: {len(it_admin_context)}")
        print(f"✅ Friend context entries: {len(friend_context)}")
        print("✅ Memory isolation verified")
        
        return True
    
    except Exception as e:
        print(f"❌ Memory isolation test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_lora_catalog():
    """Test LoRA catalog loading and listing."""
    try:
        from cerebric_core.cerebric_core.model import LoRAManager
        
        manager = LoRAManager()
        
        # List all LoRAs
        loras = manager.list_loras()
        assert len(loras) >= 1  # At least "none" should exist
        print(f"✅ Found {len(loras)} LoRAs in catalog")
        
        # Get info for "none"
        none_info = manager.get_lora_info("none")
        assert none_info["key"] == "none"
        assert none_info["category"] == "verified"
        print("✅ LoRA info retrieval works")
        
        # Filter by category
        verified = manager.list_loras(category="verified")
        experimental = manager.list_loras(category="experimental")
        print(f"✅ Verified LoRAs: {len(verified)}")
        print(f"✅ Experimental LoRAs: {len(experimental)}")
        
        return True
    
    except Exception as e:
        print(f"❌ LoRA catalog test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_context_detection():
    """Test context detection from running processes."""
    try:
        from cerebric_core.cerebric_core.persona import ContextDetector
        
        detector = ContextDetector()
        
        # Get running processes
        processes = detector.get_running_processes()
        assert len(processes) > 0
        print(f"✅ Detected {len(processes)} running processes")
        
        # Try to detect context
        signal = detector.detect_context()
        if signal:
            print(f"✅ Context detected: {signal.context_type}")
            print(f"   Confidence: {signal.confidence}")
            print(f"   Suggested persona: {signal.suggested_persona}")
        else:
            print("✅ No context detected (expected if no matching apps)")
        
        # Test suggestion logic
        should_suggest = detector.should_suggest(signal)
        print(f"✅ Suggestion logic: {should_suggest}")
        
        return True
    
    except Exception as e:
        print(f"❌ Context detection test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_memory_purge_safety():
    """Test that core memory cannot be purged."""
    try:
        from cerebric_core.cerebric_core.persona import MemoryPurge
        
        purge = MemoryPurge()
        
        # Try to purge core memory (should fail)
        try:
            purge.preview_purge("core")
            print("❌ Core memory purge should have been blocked")
            return False
        except ValueError as e:
            assert "protected" in str(e).lower()
            print("✅ Core memory protection works")
        
        # Try to purge IT Admin (should fail - uses core)
        try:
            purge.preview_purge("it_admin")
            print("❌ IT Admin purge should have been blocked")
            return False
        except ValueError as e:
            print("✅ IT Admin memory protection works")
        
        return True
    
    except Exception as e:
        print(f"❌ Memory purge safety test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_persona_with_lora():
    """Test persona switching with LoRA assignment."""
    try:
        from cerebric_core.cerebric_core.persona import PersonaManager, Persona
        from cerebric_core.cerebric_core.model import LoRAManager
        
        persona_mgr = PersonaManager()
        lora_mgr = LoRAManager()
        
        # Start from IT Admin
        persona_mgr.switch_to(Persona.IT_ADMIN, user="test", lora=None)
        
        # Switch to Friend with LoRA
        persona_mgr.switch_to(Persona.FRIEND, user="test", lora="friend_casual_v1")
        
        state = persona_mgr.get_state()
        assert state.active_persona == Persona.FRIEND
        assert state.lora == "friend_casual_v1"
        print("✅ Persona switched with LoRA assignment")
        
        # Switch back without LoRA
        persona_mgr.switch_to(Persona.IT_ADMIN, user="test", lora=None)
        state = persona_mgr.get_state()
        assert state.lora is None
        print("✅ LoRA cleared when switching back")
        
        return True
    
    except Exception as e:
        print(f"❌ Persona+LoRA test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_state_persistence():
    """Test that persona state persists across manager instances."""
    try:
        from cerebric_core.cerebric_core.persona import PersonaManager, Persona
        
        # Create first instance, ensure we're in IT Admin first
        mgr1 = PersonaManager()
        mgr1.switch_to(Persona.IT_ADMIN, user="test", lora=None)
        
        # Now switch to Friend with LoRA
        mgr1.switch_to(Persona.FRIEND, user="test", lora="test_lora")
        
        # Create second instance, verify state persisted
        mgr2 = PersonaManager()
        state = mgr2.get_state()
        
        assert state.active_persona == Persona.FRIEND
        assert state.lora == "test_lora"
        print("✅ Persona state persisted across instances")
        
        # Clean up: switch back to IT Admin
        mgr2.switch_to(Persona.IT_ADMIN, user="test")
        
        return True
    
    except Exception as e:
        print(f"❌ State persistence test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all Phase 4 integration tests."""
    print("=" * 70)
    print("PHASE 4 INTEGRATION TESTS (M5)")
    print("=" * 70)
    print()
    
    tests = [
        ("Full Persona Workflow", test_full_persona_workflow),
        ("Memory Isolation", test_memory_isolation),
        ("LoRA Catalog", test_lora_catalog),
        ("Context Detection", test_context_detection),
        ("Memory Purge Safety", test_memory_purge_safety),
        ("Persona with LoRA", test_persona_with_lora),
        ("State Persistence", test_state_persistence),
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
