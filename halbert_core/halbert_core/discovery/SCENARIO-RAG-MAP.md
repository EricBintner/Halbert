# Scenario → RAG Data Mapping

How each Genesis scenario (docs/Genesis/scenarios/) is supported by discovery data and RAG retrieval.

## Coverage Summary

| Category | Scenarios | Scanner Coverage | RAG Keywords |
|----------|-----------|------------------|--------------|
| S1: Health/Monitoring | 7 | ProcessScanner, ThermalScanner, ErrorLogScanner | slow, hot, error, status |
| S2: Performance | 7 | ProcessScanner, ThermalScanner, BootScanner | slow, fast, performance, boot |
| S3: Config Management | 7 | BackupScanner | config, backup, restore, dotfiles |
| S4: Packages | 7 | PackageScanner | update, install, package, apt |
| S5: Storage/Backup | 8 | StorageScanner, DiskUsageScanner, BackupScanner | disk, space, backup, mount |
| S6: Network/Security | 8 | NetworkScanner, SecurityScanner, ErrorLogScanner | network, wifi, firewall, ssh |
| S7: Development | 7 | ProcessScanner, ServiceScanner | docker, node, python, port |
| S8: Hardware | 8 | ThermalScanner, StorageScanner | fan, gpu, usb, bluetooth |
| S9: Proactive | 10 | All scanners | (context-aware, no keywords) |
| S10: Troubleshooting | 10 | ErrorLogScanner, BootScanner, PackageScanner | error, crash, boot, failed |
| S11: Edge Cases | 8 | ProcessScanner, PackageScanner, StorageScanner | freeze, lock, memory leak |

## Detailed Mappings

### S1: System Health & Monitoring

#### S1.1: "How am I doing?" (System Status)
**Data needed**: All discovery summaries
**RAG retrieval**: Fetch summary discoveries from each scanner
**Context injection**: Automatic - show all severity=WARNING/CRITICAL

#### S1.2: "Why am I slow?"
**Data needed**: 
- ProcessScanner: Resource hogs (CPU%, RAM)
- ThermalScanner: Temperature (thermal throttling?)
- StorageScanner: I/O wait, disk health
**RAG keywords**: slow, performance, lag, freeze
**Relationships**: High CPU → check if thermal throttling → check if disk I/O

#### S1.3: "Am I running hot?"
**Data needed**: ThermalScanner (temps, fans)
**RAG keywords**: hot, temperature, thermal, fan, heat
**Context injection**: All thermal discoveries

#### S1.4: "Recent errors"
**Data needed**: ErrorLogScanner (journal errors by unit)
**RAG keywords**: error, crash, failed, failure, log
**Relationships**: Error in service → service status → dependent services

#### S1.6: "What's eating resources?"
**Data needed**: ProcessScanner (sorted by CPU/RAM)
**RAG keywords**: ram, memory, cpu, hog, consuming
**Context injection**: Top 10 resource consumers

### S2: Performance & Optimization

#### S2.4: "Speed up boot"
**Data needed**: BootScanner (boot time, slow services)
**RAG keywords**: boot, startup, slow boot
**Relationships**: Slow service → why slow → dependencies

#### S2.6: "Reduce fan noise"
**Data needed**: ThermalScanner (fan RPM, temps)
**RAG keywords**: fan, noise, loud, quiet
**Relationships**: High fan → high temp → resource hog process

### S4: Package Management

#### S4.2: "Update my system"
**Data needed**: PackageScanner (available updates, security)
**RAG keywords**: update, upgrade, apt, dnf
**Context injection**: Update count, security update count

#### S4.3: "Held packages"
**Data needed**: PackageScanner (held packages list)
**RAG keywords**: held, hold, blocked, dependency
**Relationships**: Held package → what depends on it → why held

#### S4.4: "Clean up packages"
**Data needed**: PackageScanner (orphans), DiskUsageScanner (cache)
**RAG keywords**: clean, orphan, unused, autoremove
**Context injection**: Orphan count, cache size

### S5: Storage & Backup

#### S5.2: "What's eating disk space?"
**Data needed**: DiskUsageScanner (large dirs, caches)
**RAG keywords**: space, disk, full, large, cleanup
**Context injection**: Top space consumers, cleanable caches

#### S5.5: "Advanced filesystems"
**Data needed**: StorageScanner (bcachefs, ZFS, btrfs pools)
**RAG keywords**: bcachefs, zfs, btrfs, pool, raid
**Relationships**: Pool → devices → SMART status → mount service

#### S5.6: "Disk health"
**Data needed**: StorageScanner (SMART data)
**RAG keywords**: smart, health, failing, disk
**Relationships**: Failed disk → pools using it → mount services

### S10: Troubleshooting & Recovery

#### S10.1: "Boot failure"
**Data needed**: BootScanner (kernels, errors), ErrorLogScanner
**RAG keywords**: boot, won't start, grub, kernel
**Relationships**: Boot error → failed service → dependency

#### S10.3: "App won't start"
**Data needed**: ServiceScanner, ErrorLogScanner
**RAG keywords**: start, launch, service, failed
**Relationships**: Failed service → its errors → dependencies

#### S10.4: "Full disk emergency"
**Data needed**: DiskUsageScanner, StorageScanner
**RAG keywords**: full, no space, disk full
**Context injection**: Immediate cleanup options (cache, trash, logs)

#### S10.10: "Broken package manager"
**Data needed**: PackageScanner (lock files)
**RAG keywords**: lock, locked, dpkg, apt broken
**Context injection**: Lock file locations, stale process info

### S11: Edge Cases

#### S11.2: "Performance degradation over time"
**Data needed**: ProcessScanner (memory growth trends)
**RAG keywords**: slow over time, memory leak, degradation
**Relationships**: Growing process → its service → when started

#### S11.3: "Package manager locked"
**Data needed**: PackageScanner (lock files, PIDs)
**RAG keywords**: lock, locked, cannot lock
**Context injection**: Lock holder PID, process info

## Correlation Patterns

The RAG should understand these causal chains:

### Storage Failures
```
Disk SMART failure
  → Pool contains failing disk  
  → Pool unmounted
  → Mount service failed
  → Applications using mount fail
```
**RAG retrieval**: When any item in chain mentioned, fetch entire chain.

### Performance Issues
```
High CPU process
  → Causes high temperature
  → Triggers thermal throttling
  → System feels slow
```
**RAG retrieval**: "slow" → fetch processes + temps together

### Package Issues
```
Held package
  → Blocks updates
  → Security vulnerability persists
```
**RAG retrieval**: "update" → show held packages too

### Boot Issues
```
Slow service at boot
  → Depends on network/disk
  → Network/disk has problem
```
**RAG retrieval**: "slow boot" → show slow services + their deps

## Implementation Checklist

- [x] ProcessScanner - resource hogs, zombies
- [x] ThermalScanner - temps, fans
- [x] BootScanner - boot time, slow services
- [x] PackageScanner - updates, orphans, locks
- [x] DiskUsageScanner - space hogs, caches
- [x] ErrorLogScanner - journal errors, auth failures
- [x] StorageScanner - SMART, pools (enhanced)
- [x] ServiceScanner - mount relationships (enhanced)
- [x] Context injection by keywords
- [x] Relationship-based retrieval (service↔storage)
- [ ] Process → service relationship
- [ ] Error → service correlation
- [ ] Thermal → process correlation
- [ ] Time-series data for trends
