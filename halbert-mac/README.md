# Halbert macOS Platform Adapter

**Platform-specific implementations for macOS systems**

✅ **Note**: This directory is now **public** as part of Phase 25 (macOS App Store strategy).

---

## Overview

This package provides macOS-specific adapters that integrate with the Cerebrix platform abstraction layer. It uses native macOS tools and APIs to provide a consistent interface.

---

## Structure

```
halbert-mac/
├── __init__.py
└── adapters/
    ├── __init__.py
    ├── ingestion.py    # Unified Logging collection
    ├── sensors.py      # IOKit hardware sensors
    └── services.py     # launchd service management
```

---

## Adapters

### UnifiedLoggingAdapter

**Purpose**: macOS system log collection via Unified Logging

**macOS Equivalent**: Linux journald

**Features**:
- Streams logs from Unified Logging system
- Supports filtering (process, subsystem, level)
- Uses `log stream` for real-time, `log show` for historical
- Normalizes to Cerebrix telemetry format

**Usage**:
```python
from adapters import UnifiedLoggingAdapter

unified_log = UnifiedLoggingAdapter()

# Stream logs (real-time)
for log in unified_log.collect_logs(follow=True):
    print(log['message'])

# Historical logs (last hour)
for log in unified_log.collect_logs(follow=False):
    print(log)

# With filters
filters = {
    'process': 'sshd',
    'level': 'error'
}
for log in unified_log.collect_logs(filters=filters):
    print(log)

# Check availability
if unified_log.is_available():
    print("Unified Logging available")
```

**macOS Tools Used**:
- `log stream --style json` - Real-time log streaming
- `log show --style json` - Historical logs

---

### IOKitAdapter

**Purpose**: Hardware sensor reading via macOS IOKit

**macOS Equivalent**: Linux hwmon

**Features**:
- Reads CPU temperature via `powermetrics`
- Reads battery info via `psutil` or `system_profiler`
- Auto-discovers available sensors
- Normalizes readings to Cerebrix format

**Usage**:
```python
from adapters import IOKitAdapter

iokit = IOKitAdapter()

# Read all sensors
sensors = iokit.read_all_sensors()
for sensor in sensors:
    if sensor.get('subsystem') == 'thermal':
        temp = sensor['data']['temp_c']
        label = sensor['data']['label']
        print(f"{label}: {temp}°C")

# Read specific sensor
cpu_temp = iokit.read_sensor('cpu_temp')
if cpu_temp:
    print(cpu_temp)

# List available sensors
for sensor in iokit.list_sensors():
    print(f"{sensor['label']} ({sensor['type']})")

# Check availability
if iokit.is_available():
    print("IOKit sensors available")
```

**macOS Tools Used**:
- `powermetrics --samplers thermal` - CPU/GPU temperature (requires sudo)
- `psutil.sensors_battery()` - Battery info
- `system_profiler SPPowerDataType` - Detailed power info

**Note**: `powermetrics` requires sudo access. Configure passwordless sudo for automated monitoring:
```bash
# Add to /etc/sudoers (use visudo)
username ALL=(ALL) NOPASSWD: /usr/bin/powermetrics
```

---

### LaunchdAdapter

**Purpose**: launchd service management

**macOS Equivalent**: Linux systemd

**Features**:
- Start/stop/enable/disable services
- List all launchd services
- Get service status
- Dry-run mode
- List available launch daemons

**Usage**:
```python
from adapters import LaunchdAdapter

launchd = LaunchdAdapter()

# Manage service (dry-run)
result = launchd.manage_service('com.apple.sshd', 'status', dry_run=True)
print(result['message'])

# Actually check status
result = launchd.manage_service('com.apple.sshd', 'status')
if result['ok']:
    print("Service status retrieved")

# List all services
for service in launchd.list_services():
    print(f"{service['name']}: PID {service['pid']}")

# Get detailed status
status = launchd.get_service_status('com.apple.sshd')
print(f"Loaded: {status['loaded']}, Active: {status['active']}")

# List available daemons
for daemon in launchd.list_launch_daemons():
    print(daemon)

# Check availability
if launchd.is_available():
    print("launchd is available")
```

**macOS Tools Used**:
- `launchctl bootstrap` - Start service
- `launchctl bootout` - Stop service
- `launchctl enable` - Enable service
- `launchctl disable` - Disable service
- `launchctl list` - List services

**Note**: launchd uses different terminology than systemd:
- `load/unload` (older) vs `bootstrap/bootout` (newer)
- Service names use reverse-domain notation (e.g., `com.apple.sshd`)
- Plist files in `/Library/LaunchDaemons/` or `~/Library/LaunchAgents/`

---

## Integration with Platform Bridge

These adapters are automatically used by `MacPlatformBridge`:

```python
from halbert_core.platform import get_platform_bridge

# Auto-detects macOS and loads MacPlatformBridge
bridge = get_platform_bridge()

# Uses UnifiedLoggingAdapter internally
for log in bridge.collect_logs(follow=True):
    print(log)

# Uses IOKitAdapter internally
sensors = bridge.read_sensors()

# Uses LaunchdAdapter internally
result = bridge.manage_service('com.apple.sshd', 'status')
```

---

## macOS vs Linux Comparison

| Feature | Linux | macOS | Notes |
|---------|-------|-------|-------|
| **Log Collection** | journald | Unified Logging | Both JSON output |
| **Sensors** | hwmon (/sys) | IOKit (powermetrics) | macOS requires sudo |
| **Services** | systemd | launchd | Different commands |
| **Packages** | apt/yum | brew | Both work |
| **System Stats** | psutil | psutil | Cross-platform |

---

## Dependencies

### Required
- macOS operating system
- psutil (cross-platform stats)

### Optional
- sudo access for `powermetrics` (CPU temp)
- Homebrew (package management)

### Fallbacks
- UnifiedLoggingAdapter falls back to basic `log` command
- IOKitAdapter uses psutil for battery if powermetrics unavailable
- All adapters gracefully handle missing dependencies

---

## Installation

This package is automatically included when installing Cerebrix on macOS:

```bash
pip install halbert-mac
```

Or as part of the main installation:

```bash
cd ~/LinuxBrain
pip install -e halbert_core
pip install -e halbert-mac
```

---

## Testing

⚠️ **Testing requires macOS system**

Test adapters directly:

```python
# Test Unified Logging
from adapters import UnifiedLoggingAdapter
unified_log = UnifiedLoggingAdapter()
print(unified_log.get_status())

# Test IOKit
from adapters import IOKitAdapter
iokit = IOKitAdapter()
print(f"Available: {iokit.is_available()}")
print(f"Sensors: {len(iokit.list_sensors())}")

# Test launchd
from adapters import LaunchdAdapter
launchd = LaunchdAdapter()
print(f"Available: {launchd.is_available()}")
```

Or through platform bridge tests (on macOS):

```bash
python3 tests/platform/test_runner.py
```

---

## Design Philosophy

### Adapter Pattern

These adapters follow the **Adapter Pattern**:
- Use native macOS tools
- Provide consistent interface
- Enable platform abstraction
- Match Linux adapter structure

### macOS-Specific Considerations

**Unified Logging**:
- Different from journald but similar concept
- JSON output available via `--style json`
- Filtering by process, subsystem, level

**IOKit Sensors**:
- Not as accessible as Linux /sys/class/hwmon
- Requires `powermetrics` with sudo
- Battery info via psutil works well

**launchd**:
- Different command structure than systemd
- Reverse-domain naming convention
- Plist files instead of unit files

### Fallback Strategy

All adapters implement fallbacks:
1. Try adapter (best)
2. Try direct command (good)
3. Return error (graceful)

---

## Git Strategy

**Public** (in GitHub repo):
- ✅ halbert-mac/ (this directory)
- ✅ halbert-linux/ (Linux adapters)
- ✅ halbert_core/platform/ (shared abstraction)

**Why public (Phase 25)**: 
- Mac App Store as discovery channel for Linux product
- Free/low-cost Mac app advertises full Linux experience
- Platform-separated RAG (Mac data ships with Mac, Linux data with Linux)

---

## Related

- **Platform Abstraction**: `halbert_core/platform/`
- **Linux Adapter**: `halbert-linux/adapters/` (public)
- **Tests**: `tests/platform/` (Linux tests public, Mac tests gitignored)

---

## macOS Security Notes

### Sudo Access

CPU temperature reading requires sudo:

```bash
# Option 1: Passwordless sudo (for automation)
sudo visudo
# Add: username ALL=(ALL) NOPASSWD: /usr/bin/powermetrics

# Option 2: Run once with password
sudo powermetrics -n 1

# Option 3: Skip temperature monitoring
# IOKitAdapter will gracefully skip if no sudo access
```

### Privacy & Security

macOS may require permission for:
- Reading logs (Unified Logging)
- Accessing system info
- Managing services (requires admin)

Grant permissions in **System Preferences → Security & Privacy**.

---

**Version**: 0.1.0  
**License**: Same as Cerebrix  
**Maintainer**: Cerebrix team  
**Platform**: macOS only (Darwin)

✅ **This code is now public (Phase 25)**
