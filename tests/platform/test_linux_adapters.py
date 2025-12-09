#!/usr/bin/env python3
"""
Test Linux adapters directly.
"""

import sys
import os

# Add cerebric-linux to path
linux_path = os.path.join(os.path.dirname(__file__), '../../cerebric-linux')
sys.path.insert(0, linux_path)

# Add cerebric_core to path
cerebric_path = os.path.join(os.path.dirname(__file__), '../../cerebric_core')
sys.path.insert(0, cerebric_path)

from adapters import JournaldAdapter, HwmonAdapter, SystemdAdapter


def test_journald_adapter():
    """Test journald adapter."""
    print("Testing JournaldAdapter...")
    
    journald = JournaldAdapter()
    assert journald.name == "journald"
    
    # Test status
    status = journald.get_status()
    assert 'ok' in status
    print(f"  ✓ Journald status: {status.get('active', False)}")
    
    # Test log collection (non-following, limited)
    logs = list(journald.collect_logs(follow=False))
    if logs and 'error' not in logs[0]:
        print(f"  ✓ Collected {len(logs)} log entries")
    else:
        print("  ℹ Log collection not available (journalctl may not be installed)")


def test_hwmon_adapter():
    """Test hwmon adapter."""
    print("Testing HwmonAdapter...")
    
    hwmon = HwmonAdapter()
    assert hwmon.name == "hwmon"
    
    # Test availability
    available = hwmon.is_available()
    print(f"  ✓ hwmon available: {available}")
    
    if available:
        # Test list sensors
        sensors_list = hwmon.list_sensors()
        print(f"  ✓ Found {len(sensors_list)} sensors")
        
        # Test read all sensors
        readings = hwmon.read_all_sensors()
        if readings and 'error' not in readings[0]:
            print(f"  ✓ Read {len(readings)} sensor values")
            # Show first few
            for reading in readings[:3]:
                if 'data' in reading:
                    temp = reading['data'].get('temp_c', 0)
                    label = reading['data'].get('label', 'unknown')
                    print(f"    - {label}: {temp}°C")
    else:
        print("  ℹ hwmon not available on this system")


def test_systemd_adapter():
    """Test systemd adapter."""
    print("Testing SystemdAdapter...")
    
    systemd = SystemdAdapter()
    assert systemd.name == "systemd"
    
    # Test availability
    available = systemd.is_available()
    print(f"  ✓ systemd available: {available}")
    
    if available:
        # Test list services (limit output)
        services = systemd.list_services()
        print(f"  ✓ Found {len(services)} services")
        
        # Test dry-run
        result = systemd.manage_service('fake-service', 'status', dry_run=True)
        assert result['dry_run'] is True
        print(f"  ✓ Dry-run works: {result['message']}")
        
        # Test get service status (use a common service)
        for service_name in ['systemd-journald', 'dbus']:
            status = systemd.get_service_status(service_name)
            if status.get('ok'):
                print(f"  ✓ {service_name}: active={status.get('active')}, enabled={status.get('enabled')}")
                break
    else:
        print("  ℹ systemd not available on this system")


def test_adapter_integration():
    """Test that adapters integrate with platform bridge."""
    print("Testing adapter integration with platform bridge...")
    
    from cerebric_core.platform import get_platform_bridge
    
    bridge = get_platform_bridge()
    assert bridge.platform_name == 'linux'
    
    # Bridge should be using adapters internally
    print("  ✓ Platform bridge loads adapters")


def run_all_tests():
    """Run all adapter tests."""
    print("=" * 60)
    print("Linux Adapter Test Suite")
    print("=" * 60)
    print()
    
    tests = [
        test_journald_adapter,
        test_hwmon_adapter,
        test_systemd_adapter,
        test_adapter_integration,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
            print()
        except AssertionError as e:
            failed += 1
            print(f"  ✗ FAILED: {e}")
            print()
        except Exception as e:
            failed += 1
            print(f"  ✗ ERROR: {e}")
            import traceback
            traceback.print_exc()
            print()
    
    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)
    
    return failed == 0


if __name__ == '__main__':
    success = run_all_tests()
    sys.exit(0 if success else 1)
