"""
Test persona API endpoints (Phase 4 M3).

Tests the FastAPI endpoints for persona management.
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


def test_api_imports():
    """Test that API dependencies are available."""
    try:
        from fastapi.testclient import TestClient
        from halbert_core.dashboard.app import create_app
        
        print("✅ FastAPI and TestClient imported successfully")
        return True
    except ImportError as e:
        print(f"⚠ FastAPI not installed: {e}")
        print("   Install with: pip install fastapi python-multipart")
        return False


def test_persona_status_endpoint():
    """Test GET /api/persona/status endpoint."""
    try:
        from fastapi.testclient import TestClient
        from halbert_core.dashboard.app import create_app
        
        app = create_app(enable_cors=False)
        client = TestClient(app)
        
        response = client.get("/api/persona/status")
        assert response.status_code == 200
        
        data = response.json()
        assert "active_persona" in data
        assert "memory_dir" in data
        assert data["active_persona"] in ["it_admin", "friend", "custom"]
        
        print("✅ Persona status endpoint test passed")
        print(f"   Active persona: {data['active_persona']}")
        return True
    
    except ImportError:
        print("⚠ Skipping API tests (FastAPI not installed)")
        return True  # Don't fail if FastAPI not installed
    except Exception as e:
        print(f"❌ Persona status endpoint test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_persona_list_endpoint():
    """Test GET /api/persona/list endpoint."""
    try:
        from fastapi.testclient import TestClient
        from halbert_core.dashboard.app import create_app
        
        app = create_app(enable_cors=False)
        client = TestClient(app)
        
        response = client.get("/api/persona/list")
        assert response.status_code == 200
        
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 3  # it_admin, friend, custom
        
        # Check first persona
        persona = data[0]
        assert "id" in persona
        assert "name" in persona
        assert "icon" in persona
        assert "active" in persona
        
        print("✅ Persona list endpoint test passed")
        print(f"   Found {len(data)} personas")
        return True
    
    except ImportError:
        print("⚠ Skipping API tests (FastAPI not installed)")
        return True
    except Exception as e:
        print(f"❌ Persona list endpoint test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_lora_list_endpoint():
    """Test GET /api/persona/lora/list endpoint."""
    try:
        from fastapi.testclient import TestClient
        from halbert_core.dashboard.app import create_app
        
        app = create_app(enable_cors=False)
        client = TestClient(app)
        
        response = client.get("/api/persona/lora/list")
        assert response.status_code == 200
        
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1  # At least "none" LoRA
        
        # Check first LoRA
        if data:
            lora = data[0]
            assert "key" in lora
            assert "category" in lora
            assert "description" in lora
        
        print("✅ LoRA list endpoint test passed")
        print(f"   Found {len(data)} LoRAs")
        return True
    
    except ImportError:
        print("⚠ Skipping API tests (FastAPI not installed)")
        return True
    except Exception as e:
        print(f"❌ LoRA list endpoint test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_memory_stats_endpoint():
    """Test GET /api/persona/memory/stats endpoint."""
    try:
        from fastapi.testclient import TestClient
        from halbert_core.dashboard.app import create_app
        
        app = create_app(enable_cors=False)
        client = TestClient(app)
        
        response = client.get("/api/persona/memory/stats")
        assert response.status_code == 200
        
        data = response.json()
        assert "core" in data
        assert "personas" in data
        
        print("✅ Memory stats endpoint test passed")
        return True
    
    except ImportError:
        print("⚠ Skipping API tests (FastAPI not installed)")
        return True
    except Exception as e:
        print(f"❌ Memory stats endpoint test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all API tests."""
    print("=" * 60)
    print("PERSONA API ENDPOINT TESTS (Phase 4 M3)")
    print("=" * 60)
    print()
    
    # Check if FastAPI is available first
    if not test_api_imports():
        print("\n" + "=" * 60)
        print("SKIPPED: FastAPI not installed")
        print("=" * 60)
        return True  # Don't fail if FastAPI not installed
    
    tests = [
        ("Persona Status Endpoint", test_persona_status_endpoint),
        ("Persona List Endpoint", test_persona_list_endpoint),
        ("LoRA List Endpoint", test_lora_list_endpoint),
        ("Memory Stats Endpoint", test_memory_stats_endpoint),
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
