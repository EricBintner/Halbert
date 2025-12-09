#!/usr/bin/env python3
"""
Simple test runner for platform abstraction (no pytest required).
"""

import sys
import os

# Add cerebric_core to path
cerebric_path = os.path.join(os.path.dirname(__file__), '../../cerebric_core')
sys.path.insert(0, cerebric_path)

from cerebric_core.platform import (
    get_platform_bridge,
    reset_platform_cache,
    PlatformBridge,
)


def test_platform_detection():
    """Test that platform is correctly detected."""
    print("Testing platform detection...")
    reset_platform_cache()
    bridge = get_platform_bridge()
    
    assert bridge is not None, "Bridge should not be None"
    assert isinstance(bridge, PlatformBridge), "Bridge should be PlatformBridge instance"
    
    # Platform name should match system
    if sys.platform.startswith('linux'):
        assert bridge.platform_name == 'linux', f"Expected 'linux', got '{bridge.platform_name}'"
    elif sys.platform == 'darwin':
        assert bridge.platform_name == 'macos', f"Expected 'macos', got '{bridge.platform_name}'"
    
    print(f"  ✓ Platform detected: {bridge.platform_name}")


def test_platform_caching():
    """Test that platform bridge is cached."""
    print("Testing platform caching...")
    reset_platform_cache()
    
    bridge1 = get_platform_bridge()
    bridge2 = get_platform_bridge()
    
    assert bridge1 is bridge2, "Bridge should be cached (same instance)"
    print("  ✓ Platform bridge is cached")


def test_cpu_usage():
    """Test CPU usage works on current platform."""
    print("Testing CPU usage...")
    bridge = get_platform_bridge()
    cpu = bridge.get_cpu_usage()
    
    assert isinstance(cpu, float), f"CPU should be float, got {type(cpu)}"
    assert 0 <= cpu <= 100, f"CPU should be 0-100, got {cpu}"
    print(f"  ✓ CPU usage: {cpu:.1f}%")


def test_memory_info():
    """Test memory info works on current platform."""
    print("Testing memory info...")
    bridge = get_platform_bridge()
    mem = bridge.get_memory_info()
    
    assert isinstance(mem, dict), "Memory info should be dict"
    assert 'total' in mem, "Should have 'total' key"
    assert 'available' in mem, "Should have 'available' key"
    assert 'percent' in mem, "Should have 'percent' key"
    assert mem['total'] > 0, "Total memory should be > 0"
    
    total_gb = mem['total'] / (1024**3)
    used_gb = mem['used'] / (1024**3)
    print(f"  ✓ Memory: {used_gb:.1f}GB / {total_gb:.1f}GB ({mem['percent']:.1f}%)")


def test_disk_usage():
    """Test disk usage works on current platform."""
    print("Testing disk usage...")
    bridge = get_platform_bridge()
    disk = bridge.get_disk_usage('/')
    
    assert isinstance(disk, dict), "Disk info should be dict"
    assert 'total' in disk, "Should have 'total' key"
    assert 'used' in disk, "Should have 'used' key"
    assert 'free' in disk, "Should have 'free' key"
    assert 'percent' in disk, "Should have 'percent' key"
    assert disk['total'] > 0, "Total disk should be > 0"
    
    total_gb = disk['total'] / (1024**3)
    used_gb = disk['used'] / (1024**3)
    print(f"  ✓ Disk: {used_gb:.1f}GB / {total_gb:.1f}GB ({disk['percent']:.1f}%)")


def test_system_info():
    """Test system info works on current platform."""
    print("Testing system info...")
    bridge = get_platform_bridge()
    info = bridge.get_system_info()
    
    assert isinstance(info, dict), "System info should be dict"
    assert 'hostname' in info, "Should have 'hostname' key"
    assert 'platform' in info, "Should have 'platform' key"
    assert 'system' in info, "Should have 'system' key"
    
    print(f"  ✓ System: {info['hostname']} ({info['platform']} {info['machine']})")


def test_execute_command():
    """Test command execution works."""
    print("Testing command execution...")
    bridge = get_platform_bridge()
    
    # Test with dry_run
    result = bridge.execute_command(['echo', 'test'], dry_run=True)
    assert result['ok'] is True, "Dry run should succeed"
    assert result['dry_run'] is True, "Should indicate dry run"
    
    # Test actual execution
    result = bridge.execute_command(['echo', 'test'])
    assert result['ok'] is True, "Command should succeed"
    assert 'test' in result['stdout'], "Should contain 'test' in output"
    
    print("  ✓ Command execution works")


def test_read_sensors():
    """Test sensor reading (may return empty list if no sensors)."""
    print("Testing sensor reading...")
    bridge = get_platform_bridge()
    sensors = bridge.read_sensors()
    
    assert isinstance(sensors, list), "Sensors should be list"
    
    if sensors:
        print(f"  ✓ Found {len(sensors)} sensor(s)")
        for sensor in sensors[:3]:  # Show first 3
            if 'error' not in sensor:
                value = sensor.get('value', 'N/A')
                unit = sensor.get('unit', '')
                print(f"    - {sensor.get('label', 'unknown')}: {value}{unit}")
    else:
        print("  ℹ No sensors found (this is OK on some systems)")


def run_all_tests():
    """Run all tests."""
    print("=" * 60)
    print("Platform Abstraction Test Suite")
    print("=" * 60)
    print()
    
    tests = [
        test_platform_detection,
        test_platform_caching,
        test_cpu_usage,
        test_memory_info,
        test_disk_usage,
        test_system_info,
        test_execute_command,
        test_read_sensors,
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
            print()
    
    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)
    
    return failed == 0


if __name__ == '__main__':
    success = run_all_tests()
    sys.exit(0 if success else 1)
