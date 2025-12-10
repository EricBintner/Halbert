# Halbert Linux Platform Adapter

**Platform-specific implementations for Linux systems**

---

## Overview

This package provides Linux-specific adapters that integrate with the Halbert platform abstraction layer. It wraps existing Linux tools and libraries to provide a consistent interface.

---

## Structure

```
halbert-linux/
├── __init__.py
└── adapters/
    ├── __init__.py
    ├── ingestion.py    # journald log collection
    ├── sensors.py      # hwmon hardware sensors
    └── services.py     # systemd service management
```

---

## Adapters

### JournaldAdapter

**Purpose**: Linux system log collection via journald

**Features**:
- Streams logs from journald
- Supports filtering (units, identifiers, severities)
- Cursor-based resuming
- Falls back to `journalctl` if python-systemd unavailable

**Usage**:
```python
from adapters import JournaldAdapter

journald = JournaldAdapter()

# Collect logs (streaming)
for log in journald.collect_logs(follow=True):
    print(log['message'])

# With filters
filters = {
    'units': ['sshd.service'],
    'severities': ['error', 'warning']
}
for log in journald.collect_logs(filters=filters):
    print(log)
```

---

### HwmonAdapter

**Purpose**: Hardware sensor reading via Linux hwmon

**Features**:
- Reads temperature sensors from `/sys/class/hwmon`
- Auto-discovers all available sensors
- Normalizes readings to Halbert format

**Usage**:
```python
from adapters import HwmonAdapter

hwmon = HwmonAdapter()

# Read all sensors
sensors = hwmon.read_all_sensors()
for sensor in sensors:
    temp = sensor.get('data', {}).get('temp_c', 0)
    label = sensor.get('data', {}).get('label', 'unknown')
    print(f"{label}: {temp}°C")

# List available sensors
for sensor in hwmon.list_sensors():
    print(f"{sensor['label']} at {sensor['path']}")

# Check availability
if hwmon.is_available():
    print("hwmon is available")
```

---

### SystemdAdapter

**Purpose**: systemd service management

**Features**:
- Start/stop/restart services
- Enable/disable services
- List all services
- Get service status
- Dry-run mode

**Usage**:
```python
from adapters import SystemdAdapter

systemd = SystemdAdapter()

# Manage service (dry-run)
result = systemd.manage_service('nginx', 'restart', dry_run=True)
print(result['message'])  # "Would execute: systemctl restart nginx"

# Actually restart
result = systemd.manage_service('nginx', 'restart')
if result['ok']:
    print("Service restarted")

# List all services
for service in systemd.list_services():
    print(f"{service['name']}: {service['active']}")

# Get detailed status
status = systemd.get_service_status('nginx')
print(status['status'])

# Check availability
if systemd.is_available():
    print("systemd is available")
```

---

## Integration with Platform Bridge

These adapters are automatically used by `LinuxPlatformBridge`:

```python
from halbert_core.platform import get_platform_bridge

# Auto-detects Linux and loads LinuxPlatformBridge
bridge = get_platform_bridge()

# Uses JournaldAdapter internally
for log in bridge.collect_logs(follow=True):
    print(log)

# Uses HwmonAdapter internally
sensors = bridge.read_sensors()

# Uses SystemdAdapter internally
result = bridge.manage_service('nginx', 'status')
```

---

## Wrapped Functionality

### Existing Code Reuse

These adapters wrap existing `halbert_core` functionality:

**JournaldAdapter** wraps:
- `halbert_core.ingestion.journald.follow_journal()`
- `halbert_core.ingestion.journald._normalize()`

**HwmonAdapter** wraps:
- `halbert_core.ingestion.hwmon.collect_temp()`

**SystemdAdapter**:
- Direct systemctl integration (no existing wrapper)

**Why**: Clean separation between core logic and platform-specific implementation.

---

## Dependencies

### Required
- Linux operating system
- psutil (cross-platform stats)

### Optional
- python-systemd (for native journald access)
- systemd (service management)
- /sys/class/hwmon (sensor reading)

### Fallbacks
- JournaldAdapter falls back to `journalctl` command if python-systemd unavailable
- All adapters gracefully handle missing dependencies

---

## Installation

This package is automatically included when installing Halbert on Linux:

```bash
pip install halbert-linux
```

Or as part of the main installation:

```bash
cd ~/LinuxBrain
pip install -e halbert_core
pip install -e halbert-linux
```

---

## Testing

Test adapters directly:

```python
# Test journald
from adapters import JournaldAdapter
journald = JournaldAdapter()
print(journald.get_status())

# Test hwmon
from adapters import HwmonAdapter
hwmon = HwmonAdapter()
print(f"Available: {hwmon.is_available()}")
print(f"Sensors: {len(hwmon.list_sensors())}")

# Test systemd
from adapters import SystemdAdapter
systemd = SystemdAdapter()
print(f"Available: {systemd.is_available()}")
```

Or through platform bridge tests:

```bash
python3 tests/platform/test_runner.py
```

---

## Design Philosophy

### Adapter Pattern

These adapters follow the **Adapter Pattern**:
- Wrap existing implementations
- Provide consistent interface
- Enable platform abstraction
- Preserve existing functionality

### Separation of Concerns

```
Platform Bridge (interface)
    ↓
Linux Adapter (platform-specific)
    ↓
Existing halbert_core code (reused)
```

### Fallback Strategy

All adapters implement fallbacks:
1. Try adapter (best)
2. Try direct command (good)
3. Return error (graceful)

---

## Git Strategy

**Public** (in GitHub repo):
- ✅ halbert-linux/ (this directory)
- ✅ All adapter code
- ✅ Linux-specific implementations

**Private** (gitignored):
- halbert-mac/ (macOS equivalent)

---

## Related

- **Platform Abstraction**: `halbert_core/platform/`
- **Tests**: `tests/platform/`
- **Mac Adapter**: `halbert-mac/adapters/` (gitignored)

---

**Version**: 0.1.0  
**License**: Same as Halbert  
**Maintainer**: Halbert team
