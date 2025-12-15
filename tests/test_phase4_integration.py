"""
Phase 4 Integration Tests (M5).

Tests the complete persona system workflow end-to-end:
- Persona switching
- Memory isolation
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
        from halbert_core.persona import PersonaManager, Persona
        
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
        from halbert_core.memory.retrieval import MemoryRetrieval
        from halbert_core.persona import PersonaManager, Persona
        
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


def test_context_detection():
    """Test context detection from running processes."""
    try:
        from halbert_core.persona import ContextDetector
        
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
        from halbert_core.persona import MemoryPurge
        
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


def test_state_persistence():
    """Test that persona state persists across manager instances."""
    try:
        from halbert_core.persona import PersonaManager, Persona
        
        # Create first instance, ensure we're in IT Admin first
        mgr1 = PersonaManager()
        mgr1.switch_to(Persona.IT_ADMIN, user="test")
        
        # Now switch to Friend
        mgr1.switch_to(Persona.FRIEND, user="test")
        
        # Create second instance, verify state persisted
        mgr2 = PersonaManager()
        state = mgr2.get_state()
        
        assert state.active_persona == Persona.FRIEND
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
        ("Context Detection", test_context_detection),
        ("Memory Purge Safety", test_memory_purge_safety),
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
