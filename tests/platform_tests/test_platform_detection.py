"""
Tests for platform detection and loading.
"""

import sys
import pytest
from halbert_core.platform import (
    get_platform_bridge,
    reset_platform_cache,
    PlatformBridge,
    UnsupportedPlatformError,
)


def test_platform_detection():
    """Test that platform is correctly detected."""
    reset_platform_cache()
    bridge = get_platform_bridge()
    
    assert bridge is not None
    assert isinstance(bridge, PlatformBridge)
    
    # Platform name should match system
    if sys.platform.startswith('linux'):
        assert bridge.platform_name == 'linux'
    elif sys.platform == 'darwin':
        assert bridge.platform_name == 'macos'


def test_platform_caching():
    """Test that platform bridge is cached."""
    reset_platform_cache()
    
    bridge1 = get_platform_bridge()
    bridge2 = get_platform_bridge()
    
    # Should return same instance
    assert bridge1 is bridge2


def test_cpu_usage():
    """Test CPU usage works on current platform."""
    bridge = get_platform_bridge()
    cpu = bridge.get_cpu_usage()
    
    assert isinstance(cpu, float)
    assert 0 <= cpu <= 100


def test_memory_info():
    """Test memory info works on current platform."""
    bridge = get_platform_bridge()
    mem = bridge.get_memory_info()
    
    assert isinstance(mem, dict)
    assert 'total' in mem
    assert 'available' in mem
    assert 'percent' in mem
    assert mem['total'] > 0


def test_disk_usage():
    """Test disk usage works on current platform."""
    bridge = get_platform_bridge()
    disk = bridge.get_disk_usage('/')
    
    assert isinstance(disk, dict)
    assert 'total' in disk
    assert 'used' in disk
    assert 'free' in disk
    assert 'percent' in disk
    assert disk['total'] > 0


def test_system_info():
    """Test system info works on current platform."""
    bridge = get_platform_bridge()
    info = bridge.get_system_info()
    
    assert isinstance(info, dict)
    assert 'hostname' in info
    assert 'platform' in info
    assert 'system' in info


def test_execute_command():
    """Test command execution works."""
    bridge = get_platform_bridge()
    
    # Test with dry_run
    result = bridge.execute_command(['echo', 'test'], dry_run=True)
    assert result['ok'] is True
    assert result['dry_run'] is True
    
    # Test actual execution
    result = bridge.execute_command(['echo', 'test'])
    assert result['ok'] is True
    assert 'test' in result['stdout']


def test_read_sensors():
    """Test sensor reading (may return empty list if no sensors)."""
    bridge = get_platform_bridge()
    sensors = bridge.read_sensors()
    
    assert isinstance(sensors, list)
    # Sensors may be empty on some systems, that's OK


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
