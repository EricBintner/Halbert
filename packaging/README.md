# Packaging Directory

**Purpose**: Deployment and installation artifacts for Cerebric

---

## What This Is

This directory contains files needed to **deploy and install** Cerebric on production systems, particularly for Linux.

**Not to be confused with**:
- `scripts/` - Development and demo scripts
- `release/` - Build artifacts (temporary, gets gitignored)

---

## Contents

### `systemd/system/`

**Purpose**: Linux systemd service files for background services

**What these do**: Allow Cerebric to run as a system service on Linux, starting automatically on boot.

**Files**:

#### `cerebric-ingest-journald.service`
- **What**: Background service that reads system logs (journald)
- **When**: Runs continuously on Linux systems
- **Used by**: Data ingestion system (Phase 1-3)

#### `cerebric-ingest-hwmon.service`
- **What**: Background service that reads hardware sensors (hwmon)
- **When**: Runs continuously on Linux systems
- **Used by**: Hardware monitoring (Phase 1-3)

#### `cerebric-config-watch.service`
- **What**: Watches for configuration file changes
- **When**: Runs when config files are modified
- **Triggered by**: `cerebric-config-watch.path`

#### `cerebric-config-watch.path`
- **What**: systemd path unit (watches for file changes)
- **When**: Always active, triggers service on changes
- **Watches**: Cerebric config directory

---

## How These Are Used

### Linux Installation
```bash
# During installation, these files are copied to:
/etc/systemd/system/

# Then enabled and started:
sudo systemctl enable cerebric-ingest-journald
sudo systemctl start cerebric-ingest-journald
```

### Development
Not used during development - these are for **production deployment** only.

### Mac
Not used on Mac - Mac uses launchd instead of systemd.

---

## When You Need This

### ✅ You need this for:
- Creating Linux installers (.deb, .rpm)
- Production Linux deployment
- System integration on Linux servers
- Running Cerebric as a service

### ❌ You don't need this for:
- Development/testing (use scripts/)
- Mac development (Mac doesn't use systemd)
- Running demos (use scripts/)

---

## Related Files

- **Installation script** (future): Will copy these to `/etc/systemd/system/`
- **Uninstall script** (future): Will remove these from system
- **Linux packaging** (future): .deb/.rpm will include these

---

## Status

✅ **KEEP** - These are operational files needed for Linux deployment  
❌ **DO NOT DELETE** - Required for production installations  
🔒 **PUBLIC** - These should be in the public GitHub repo

---

## Summary

**What**: systemd service files for Linux  
**Why**: Run Cerebric services in background  
**When**: Production Linux deployment  
**Platform**: Linux only (not Mac, not Windows)  
**Status**: Operational, required for deployment
