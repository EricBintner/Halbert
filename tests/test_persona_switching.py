"""
Test persona switching and memory isolation (Phase 4 M1).
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


def test_persona_manager_initialization():
    """Test that PersonaManager initializes and loads state."""
    try:
        from halbert_core.persona import PersonaManager, Persona
        
        manager = PersonaManager()
        state = manager.get_state()
        
        # State should be loaded (may not be IT_ADMIN if previously switched)
        assert state.active_persona in [Persona.IT_ADMIN, Persona.FRIEND, Persona.CUSTOM]
        assert state.memory_dir is not None
        assert isinstance(state.switched_at, str)
        assert isinstance(state.switched_by, str)
        
        print("✅ PersonaManager initialization test passed")
        return True
    except Exception as e:
        print(f"❌ Initialization test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_persona_switching():
    """Test switching between personas."""
    try:
        from halbert_core.persona import PersonaManager, Persona
        
        manager = PersonaManager()
        initial_persona = manager.get_active_persona()
        
        # Switch to opposite persona
        target_persona = Persona.IT_ADMIN if initial_persona == Persona.FRIEND else Persona.FRIEND
        expected_memory = "core" if target_persona == Persona.IT_ADMIN else "personas/friend"
        
        success = manager.switch_to(target_persona, user="test_user")
        assert success is True
        
        state = manager.get_state()
        assert state.active_persona == target_persona
        assert state.memory_dir == expected_memory
        assert state.switched_by == "test_user"
        
        print("✅ Persona switching test passed")
        return True
    except Exception as e:
        print(f"❌ Persona switching test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_persona_list():
    """Test listing available personas."""
    try:
        from halbert_core.persona import PersonaManager
        
        manager = PersonaManager()
        personas = manager.list_personas()
        
        assert len(personas) == 3
        assert personas[0]['id'] == 'it_admin'
        assert personas[1]['id'] == 'friend'
        assert personas[2]['id'] == 'custom'
        
        # Check that one is marked active
        active_count = sum(1 for p in personas if p['active'])
        assert active_count == 1
        
        print("✅ Persona list test passed")
        return True
    except Exception as e:
        print(f"❌ Persona list test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_custom_persona_blocked():
    """Test that custom persona is blocked (Phase 5)."""
    try:
        from halbert_core.persona import PersonaManager, Persona, PersonaSwitchError
        
        manager = PersonaManager()
        
        try:
            manager.switch_to(Persona.CUSTOM, user="test_user")
            print("❌ Custom persona should be blocked")
            return False
        except PersonaSwitchError as e:
            assert "Phase 5" in str(e)
            print("✅ Custom persona block test passed")
            return True
    except Exception as e:
        print(f"❌ Custom persona block test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_memory_purge_protected():
    """Test that core memory cannot be purged."""
    try:
        from halbert_core.persona import MemoryPurge
        
        purge = MemoryPurge()
        
        # Try to purge core memory
        try:
            purge.preview_purge("core")
            print("❌ Core memory purge should be blocked")
            return False
        except ValueError as e:
            assert "protected" in str(e).lower()
            print("✅ Core memory protection test passed")
            return True
    except Exception as e:
        print(f"❌ Memory purge protection test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all persona tests."""
    print("=" * 60)
    print("PERSONA SYSTEM TESTS (Phase 4 M1)")
    print("=" * 60)
    print()
    
    tests = [
        ("PersonaManager Initialization", test_persona_manager_initialization),
        ("Persona Switching", test_persona_switching),
        ("Persona List", test_persona_list),
        ("Custom Persona Blocked", test_custom_persona_blocked),
        ("Core Memory Protection", test_memory_purge_protected),
    ]
    
    passed = 0
    failed = 0
    
    for test_name, test_func in tests:
        print(f"\n--- Test: {test_name} ---")
        try:
            if test_func():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"❌ Test crashed: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
    
    print("\n" + "=" * 60)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("=" * 60)
    
    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
