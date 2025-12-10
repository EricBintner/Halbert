"""
Test scheduler integration with guardrails (Phase 3 M6).

Tests the integration without requiring APScheduler.
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

def test_guardrail_imports():
    """Test that scheduler can import guardrail modules."""
    try:
        from halbert_core.autonomy import (
            GuardrailEnforcer,
            GuardrailViolation,
            BudgetTracker,
            BudgetExceeded,
            AnomalyDetector,
            RecoveryExecutor
        )
        print("✅ All guardrail imports successful")
        return True
    except Exception as e:
        print(f"❌ Import failed: {e}")
        return False


def test_guardrail_initialization():
    """Test that guardrails can be initialized."""
    try:
        from halbert_core.autonomy import GuardrailEnforcer
        
        enforcer = GuardrailEnforcer()
        assert enforcer.config is not None
        assert 'confidence' in enforcer.config
        assert 'budgets' in enforcer.config
        
        print("✅ GuardrailEnforcer initialized successfully")
        print(f"   - Confidence threshold: {enforcer.config['confidence']['min_auto_execute']}")
        print(f"   - CPU budget: {enforcer.config['budgets']['cpu_percent_max']}%")
        print(f"   - Safe-mode: {'Active' if enforcer.is_safe_mode_active() else 'Inactive'}")
        return True
    except Exception as e:
        print(f"❌ Initialization failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_confidence_check():
    """Test confidence checking logic."""
    try:
        from halbert_core.autonomy import GuardrailEnforcer, GuardrailViolation
        
        enforcer = GuardrailEnforcer()
        
        # Test high confidence (auto-execute)
        allowed, reason = enforcer.check_confidence(0.9, "test_task_high")
        assert allowed is True
        assert reason is None
        print("✅ High confidence (0.9): auto-execute allowed")
        
        # Test medium confidence (approval required)
        allowed, reason = enforcer.check_confidence(0.6, "test_task_medium")
        assert allowed is False
        assert reason == "approval_required"
        print("✅ Medium confidence (0.6): approval required")
        
        # Test low confidence (rejected)
        try:
            enforcer.check_confidence(0.3, "test_task_low")
            print("❌ Low confidence should raise exception")
            return False
        except GuardrailViolation:
            print("✅ Low confidence (0.3): rejected (exception raised)")
        
        return True
    except Exception as e:
        print(f"❌ Confidence check failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_budget_tracking():
    """Test budget tracking."""
    try:
        from halbert_core.autonomy import BudgetTracker
        
        tracker = BudgetTracker(
            cpu_percent_max=90,
            memory_mb_max=4096,
            time_minutes_max=5
        )
        
        tracker.start()
        print("✅ Budget tracker started")
        
        # Simulate work
        import time
        time.sleep(0.1)
        
        # Check budgets (should pass)
        snapshot = tracker.check()
        assert snapshot.cpu_percent >= 0
        print(f"✅ Budget check passed (CPU: {snapshot.cpu_percent:.1f}%, Memory: {snapshot.memory_mb} MB)")
        
        # Stop tracking
        usage = tracker.stop()
        assert usage['within_budgets'] is True
        print(f"✅ Budget tracker stopped (duration: {usage['duration_seconds']:.2f}s)")
        
        return True
    except Exception as e:
        print(f"❌ Budget tracking failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_anomaly_detection():
    """Test anomaly detection."""
    try:
        from halbert_core.autonomy import AnomalyDetector, AnomalyDetected
        
        config = {
            "cpu_spike_threshold": 90,
            "memory_leak_mb": 500,
            "repeated_failures": 3,
            "error_rate_threshold": 0.5
        }
        
        detector = AnomalyDetector(config)
        print("✅ AnomalyDetector initialized")
        
        # Record some successful outcomes
        detector.record_job_outcome(True, "job_1")
        detector.record_job_outcome(True, "job_2")
        print("✅ Recorded 2 successful outcomes")
        
        # Record 2 failures (below threshold)
        detector.record_job_outcome(False, "job_3")
        detector.record_job_outcome(False, "job_4")
        print("✅ Recorded 2 failures (below threshold of 3)")
        
        # 3rd consecutive failure should trigger anomaly
        try:
            detector.record_job_outcome(False, "job_5")
            print("❌ 3rd failure should trigger anomaly")
            return False
        except AnomalyDetected as e:
            print(f"✅ Anomaly detected on 3rd failure: {e}")
        
        return True
    except Exception as e:
        print(f"❌ Anomaly detection failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_safe_mode_lifecycle():
    """Test safe-mode enter/exit."""
    try:
        from halbert_core.autonomy import GuardrailEnforcer
        
        enforcer = GuardrailEnforcer()
        
        # Should start inactive
        assert not enforcer.is_safe_mode_active()
        print("✅ Safe-mode initially inactive")
        
        # Enter safe-mode
        enforcer.enter_safe_mode("Test reason")
        assert enforcer.is_safe_mode_active()
        print("✅ Entered safe-mode")
        
        # Exit safe-mode
        enforcer.exit_safe_mode("test_user")
        assert not enforcer.is_safe_mode_active()
        print("✅ Exited safe-mode")
        
        return True
    except Exception as e:
        print(f"❌ Safe-mode lifecycle failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests."""
    print("=" * 60)
    print("SCHEDULER GUARDRAILS INTEGRATION TESTS")
    print("=" * 60)
    print()
    
    tests = [
        ("Imports", test_guardrail_imports),
        ("Initialization", test_guardrail_initialization),
        ("Confidence Checks", test_confidence_check),
        ("Budget Tracking", test_budget_tracking),
        ("Anomaly Detection", test_anomaly_detection),
        ("Safe-Mode Lifecycle", test_safe_mode_lifecycle),
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
