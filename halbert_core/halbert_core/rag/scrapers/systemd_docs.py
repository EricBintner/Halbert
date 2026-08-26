# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
systemd Documentation Scraper - Comprehensive systemd reference.

Phase 27: RAG Coverage

Generates synthetic documentation covering:
- Unit file syntax and options
- Service management commands
- Timer units (cron replacement)
- Socket activation
- Targets and dependencies
- Journald logging
- systemctl commands
- Common troubleshooting
"""

import logging
from typing import List
from datetime import datetime
from pathlib import Path

from .base import BaseScraper, ScrapedDocument, ScraperConfig

logger = logging.getLogger('halbert')


class SystemdDocsScraper(BaseScraper):
    """
    Generates comprehensive systemd documentation for RAG.
    
    Covers unit files, service management, timers, and troubleshooting.
    """
    
    def __init__(self, config: ScraperConfig):
        super().__init__(config)
    
    def get_source_name(self) -> str:
        return "systemd-docs"
    
    def scrape(self) -> List[ScrapedDocument]:
        """Generate systemd documentation."""
        logger.info("Generating systemd documentation...")
        
        documents = []
        documents.extend(self._generate_guides())
        
        logger.info(f"Total systemd documents: {len(documents)}")
        return documents
    
    def _generate_guides(self) -> List[ScrapedDocument]:
        """Generate all systemd guides."""
        guides = []
        
        # Core guides
        guides.append(self._unit_file_guide())
        guides.append(self._service_management_guide())
        guides.append(self._timer_units_guide())
        guides.append(self._socket_activation_guide())
        guides.append(self._targets_guide())
        guides.append(self._journald_guide())
        guides.append(self._troubleshooting_guide())
        guides.append(self._security_guide())
        guides.append(self._user_services_guide())
        guides.append(self._dependencies_guide())
        
        return guides
    
    def _unit_file_guide(self) -> ScrapedDocument:
        """Unit file syntax guide."""
        content = """# systemd Unit File Complete Reference

## Unit File Locations

```
/etc/systemd/system/          # Local administrator units (highest priority)
/run/systemd/system/          # Runtime units
/usr/lib/systemd/system/      # Distribution packages (lowest priority)
~/.config/systemd/user/       # User units
```

## Basic Unit File Structure

```ini
[Unit]
Description=My Custom Service
Documentation=https://example.com/docs
After=network.target
Wants=network-online.target
Requires=postgresql.service

[Service]
Type=simple
User=myuser
Group=mygroup
WorkingDirectory=/opt/myapp
Environment=NODE_ENV=production
EnvironmentFile=/etc/myapp/env
ExecStartPre=/usr/bin/myapp-check
ExecStart=/usr/bin/myapp --config /etc/myapp/config.yml
ExecStartPost=/usr/bin/myapp-notify
ExecReload=/bin/kill -HUP $MAINPID
ExecStop=/usr/bin/myapp-shutdown
Restart=on-failure
RestartSec=5
TimeoutStartSec=30
TimeoutStopSec=30

[Install]
WantedBy=multi-user.target
```

## [Unit] Section Options

| Option | Description | Example |
|--------|-------------|---------|
| `Description=` | Human-readable description | `Description=My Web Server` |
| `Documentation=` | URL to documentation | `Documentation=man:nginx(8)` |
| `After=` | Start after these units | `After=network.target` |
| `Before=` | Start before these units | `Before=httpd.service` |
| `Requires=` | Hard dependency (fails if dep fails) | `Requires=postgresql.service` |
| `Wants=` | Soft dependency (continues if dep fails) | `Wants=redis.service` |
| `Conflicts=` | Cannot run with these units | `Conflicts=sendmail.service` |
| `BindsTo=` | Stops when dependency stops | `BindsTo=dev-sda1.device` |

## [Service] Section Options

### Type Options
- `simple` (default): ExecStart is main process
- `exec`: Like simple, but manager waits for exec() to complete
- `forking`: Traditional daemon that forks
- `oneshot`: Short-lived tasks, exits after ExecStart
- `dbus`: Waits for D-Bus name acquisition
- `notify`: Uses sd_notify() to signal readiness
- `idle`: Delays until other jobs complete

### Restart Options
- `no`: Never restart
- `on-success`: Restart only on clean exit (code 0)
- `on-failure`: Restart on non-zero exit, signal, timeout
- `on-abnormal`: Restart on signal, timeout, watchdog
- `on-watchdog`: Restart only on watchdog timeout
- `on-abort`: Restart only on signal
- `always`: Always restart

### Resource Limits
```ini
LimitNOFILE=65535
LimitNPROC=4096
LimitCORE=infinity
MemoryMax=2G
CPUQuota=50%
TasksMax=100
```

## [Install] Section

```ini
[Install]
WantedBy=multi-user.target    # Enable for multi-user mode
RequiredBy=graphical.target   # Required by graphical mode
Also=myapp-worker.service     # Also enable this unit
Alias=myservice.service       # Create symlink alias
```

## Creating a New Service

```bash
# 1. Create unit file
sudo nano /etc/systemd/system/myapp.service

# 2. Reload systemd
sudo systemctl daemon-reload

# 3. Enable and start
sudo systemctl enable --now myapp.service

# 4. Check status
sudo systemctl status myapp.service

# 5. View logs
sudo journalctl -u myapp.service -f
```

## Best Practices

1. **Always specify Type=** - Don't rely on defaults
2. **Use After= for ordering** - Not for dependencies
3. **Use Wants= over Requires=** - More fault tolerant
4. **Set appropriate RestartSec=** - Prevent restart loops
5. **Use EnvironmentFile=** - Keep secrets out of unit files
6. **Specify User= and Group=** - Never run as root unless needed
7. **Use ExecStartPre= for checks** - Validate before starting
"""
        return ScrapedDocument(
            id=self._generate_id("systemd-unit-files"),
            url="https://www.freedesktop.org/software/systemd/man/systemd.unit.html",
            title="systemd Unit File Complete Reference",
            content=content,
            source=self.get_source_name(),
            category="system_admin",
            tags=["systemd", "unit-file", "service", "linux", "init"],
            scraped_at=datetime.utcnow().isoformat(),
            metadata={"type": "reference", "priority": "high"}
        )
    
    def _service_management_guide(self) -> ScrapedDocument:
        """Service management commands."""
        content = """# systemctl Command Reference

## Basic Service Management

```bash
# Start/stop/restart
systemctl start nginx.service
systemctl stop nginx.service
systemctl restart nginx.service
systemctl reload nginx.service        # Reload config without restart

# Enable/disable (start at boot)
systemctl enable nginx.service
systemctl disable nginx.service
systemctl enable --now nginx.service  # Enable AND start

# Status
systemctl status nginx.service
systemctl is-active nginx.service     # Returns "active" or "inactive"
systemctl is-enabled nginx.service    # Returns "enabled" or "disabled"
systemctl is-failed nginx.service
```

## Listing Units

```bash
# All loaded units
systemctl list-units

# All services
systemctl list-units --type=service

# Failed units
systemctl list-units --failed

# All unit files (installed)
systemctl list-unit-files

# Specific state
systemctl list-units --state=running
systemctl list-units --state=failed
```

## Dependency Management

```bash
# Show dependencies
systemctl list-dependencies nginx.service
systemctl list-dependencies --reverse nginx.service  # Who depends on this?
systemctl list-dependencies --all nginx.service      # Recursive

# Show what target wants
systemctl list-dependencies multi-user.target
```

## System State

```bash
# System targets
systemctl get-default                  # Current default target
systemctl set-default graphical.target # Set default target
systemctl isolate rescue.target        # Switch to rescue mode

# Power management
systemctl reboot
systemctl poweroff
systemctl suspend
systemctl hibernate

# Emergency modes
systemctl rescue       # Single-user mode
systemctl emergency    # Emergency shell (minimal)
```

## Unit File Management

```bash
# Reload unit files after changes
systemctl daemon-reload

# Show unit file content
systemctl cat nginx.service

# Edit unit file (creates override)
systemctl edit nginx.service           # Creates drop-in override
systemctl edit --full nginx.service    # Edit full file

# Revert to package default
systemctl revert nginx.service

# Show effective configuration
systemctl show nginx.service
systemctl show -p ExecStart nginx.service
```

## Masking Units

```bash
# Mask: prevent unit from starting (even manually)
systemctl mask nginx.service

# Unmask
systemctl unmask nginx.service
```

## User Services

```bash
# Manage user services (no sudo)
systemctl --user start myservice.service
systemctl --user enable myservice.service
systemctl --user status myservice.service

# Enable lingering (run user services without login)
loginctl enable-linger username
```

## Troubleshooting Commands

```bash
# Analyze boot time
systemd-analyze
systemd-analyze blame
systemd-analyze critical-chain
systemd-analyze plot > boot.svg

# Check unit file syntax
systemd-analyze verify /etc/systemd/system/myapp.service

# Show unit properties
systemctl show nginx.service

# Reset failed state
systemctl reset-failed
systemctl reset-failed nginx.service
```
"""
        return ScrapedDocument(
            id=self._generate_id("systemctl-commands"),
            url="https://www.freedesktop.org/software/systemd/man/systemctl.html",
            title="systemctl Command Reference",
            content=content,
            source=self.get_source_name(),
            category="system_admin",
            tags=["systemd", "systemctl", "service", "linux", "commands"],
            scraped_at=datetime.utcnow().isoformat(),
            metadata={"type": "reference", "priority": "high"}
        )
    
    def _timer_units_guide(self) -> ScrapedDocument:
        """Timer units (cron replacement)."""
        content = """# systemd Timers - Modern Cron Replacement

## Why Use Timers Instead of Cron?

- **Logging**: Automatic journald integration
- **Dependencies**: Can depend on other units
- **Persistence**: Can run missed jobs on boot
- **Accuracy**: Randomized delays prevent thundering herd
- **Management**: Standard systemctl commands

## Timer Unit Structure

You need TWO files:
1. `mytask.timer` - Defines when to run
2. `mytask.service` - Defines what to run

### Example: Daily Backup

**`/etc/systemd/system/backup.timer`**:
```ini
[Unit]
Description=Daily backup timer

[Timer]
OnCalendar=daily
Persistent=true
RandomizedDelaySec=1h

[Install]
WantedBy=timers.target
```

**`/etc/systemd/system/backup.service`**:
```ini
[Unit]
Description=Daily backup

[Service]
Type=oneshot
ExecStart=/usr/local/bin/backup.sh
```

## Timer Options

### Calendar-Based (OnCalendar=)

```ini
# Specific times
OnCalendar=*-*-* 03:00:00          # Daily at 3 AM
OnCalendar=Mon *-*-* 00:00:00      # Mondays at midnight
OnCalendar=*-*-01 00:00:00         # First of month
OnCalendar=*-01,07-01 00:00:00     # Jan 1 and Jul 1
OnCalendar=hourly                   # Every hour
OnCalendar=daily                    # Every day at midnight
OnCalendar=weekly                   # Every Monday at midnight
OnCalendar=monthly                  # First of month at midnight
OnCalendar=yearly                   # Jan 1 at midnight

# Every 15 minutes
OnCalendar=*:0/15                   # :00, :15, :30, :45

# Multiple schedules
OnCalendar=Mon..Fri *-*-* 09:00:00
OnCalendar=Mon..Fri *-*-* 17:00:00
```

### Monotonic Timers (Relative)

```ini
OnBootSec=5min                      # 5 min after boot
OnStartupSec=10min                  # 5 min after systemd start
OnActiveSec=1h                      # 1 hour after timer activated
OnUnitActiveSec=1h                  # 1 hour after service last ran
OnUnitInactiveSec=30min             # 30 min after service stopped
```

### Other Options

```ini
Persistent=true                     # Run missed timers on boot
RandomizedDelaySec=30min            # Random delay up to 30 min
AccuracySec=1s                      # Timer accuracy (default 1min)
Unit=other.service                  # Trigger different service
```

## Managing Timers

```bash
# List all timers
systemctl list-timers
systemctl list-timers --all

# Enable and start timer
systemctl enable --now backup.timer

# Check timer status
systemctl status backup.timer

# Manually trigger the service
systemctl start backup.service

# Test calendar expression
systemd-analyze calendar "Mon *-*-* 03:00:00"
systemd-analyze calendar "daily" --iterations=5
```

## Migrating from Cron

| Cron | systemd Timer |
|------|---------------|
| `0 3 * * *` | `OnCalendar=*-*-* 03:00:00` |
| `*/15 * * * *` | `OnCalendar=*:0/15` |
| `0 0 * * 0` | `OnCalendar=Sun *-*-* 00:00:00` |
| `0 0 1 * *` | `OnCalendar=*-*-01 00:00:00` |
| `@reboot` | `OnBootSec=0` |

## Transient Timers (One-Off)

```bash
# Run command in 10 minutes
systemd-run --on-active=10m /usr/bin/touch /tmp/test

# Run at specific time
systemd-run --on-calendar="2025-12-25 00:00:00" /usr/bin/merry-christmas

# With user unit
systemd-run --user --on-active=5m notify-send "Timer fired"
```
"""
        return ScrapedDocument(
            id=self._generate_id("systemd-timers"),
            url="https://www.freedesktop.org/software/systemd/man/systemd.timer.html",
            title="systemd Timers - Modern Cron Replacement",
            content=content,
            source=self.get_source_name(),
            category="system_admin",
            tags=["systemd", "timer", "cron", "scheduling", "linux"],
            scraped_at=datetime.utcnow().isoformat(),
            metadata={"type": "guide", "priority": "high"}
        )
    
    def _socket_activation_guide(self) -> ScrapedDocument:
        """Socket activation guide."""
        content = """# systemd Socket Activation

## What is Socket Activation?

Socket activation lets systemd listen on a socket and start the service only when a connection arrives. Benefits:
- **Faster boot**: Services start on-demand
- **Parallel startup**: No need to order socket-using services
- **Automatic restart**: Service can restart without dropping connections

## How It Works

1. systemd creates socket and listens
2. Connection arrives on socket
3. systemd starts the service
4. systemd passes socket file descriptor to service
5. Service handles connection

## Socket Unit Example

**`/etc/systemd/system/myapp.socket`**:
```ini
[Unit]
Description=My App Socket

[Socket]
ListenStream=8080
Accept=no

[Install]
WantedBy=sockets.target
```

**`/etc/systemd/system/myapp.service`**:
```ini
[Unit]
Description=My App Service
Requires=myapp.socket

[Service]
Type=simple
ExecStart=/usr/bin/myapp
StandardInput=socket
```

## Socket Options

```ini
[Socket]
# TCP socket
ListenStream=8080                    # Port 8080
ListenStream=127.0.0.1:8080          # Localhost only
ListenStream=[::1]:8080              # IPv6 localhost

# Unix socket
ListenStream=/run/myapp.sock
ListenDatagram=/run/myapp-udp.sock   # UDP

# Socket options
SocketMode=0660                      # Permissions
SocketUser=myapp
SocketGroup=myapp
Accept=no                            # One service for all connections
Accept=yes                           # Fork per connection (inetd style)
MaxConnections=64                    # Limit connections
KeepAlive=true
NoDelay=true
```

## Checking Sockets

```bash
# List sockets
systemctl list-sockets

# Socket status
systemctl status myapp.socket

# Enable socket (not service)
systemctl enable --now myapp.socket
```

## Common Use Cases

1. **Web servers**: Nginx, Apache with socket activation
2. **Database pools**: PostgreSQL, MySQL
3. **Print servers**: CUPS
4. **SSH**: On-demand SSH daemon
"""
        return ScrapedDocument(
            id=self._generate_id("systemd-sockets"),
            url="https://www.freedesktop.org/software/systemd/man/systemd.socket.html",
            title="systemd Socket Activation",
            content=content,
            source=self.get_source_name(),
            category="system_admin",
            tags=["systemd", "socket", "activation", "linux"],
            scraped_at=datetime.utcnow().isoformat(),
            metadata={"type": "guide", "priority": "medium"}
        )
    
    def _targets_guide(self) -> ScrapedDocument:
        """Targets and runlevels."""
        content = """# systemd Targets (Runlevels)

## What Are Targets?

Targets are systemd's replacement for SysV runlevels. They group units and define system states.

## Standard Targets

| Target | SysV Runlevel | Description |
|--------|---------------|-------------|
| `poweroff.target` | 0 | System shutdown |
| `rescue.target` | 1, S | Single-user mode |
| `multi-user.target` | 2, 3, 4 | Multi-user, no GUI |
| `graphical.target` | 5 | Multi-user with GUI |
| `reboot.target` | 6 | System reboot |
| `emergency.target` | - | Emergency shell |

## Managing Default Target

```bash
# Check current default
systemctl get-default

# Set default to multi-user (no GUI)
systemctl set-default multi-user.target

# Set default to graphical (with GUI)
systemctl set-default graphical.target

# Switch target now (like changing runlevel)
systemctl isolate multi-user.target
```

## Boot Targets

```
                     ┌─────────────────────┐
                     │   graphical.target  │
                     └──────────┬──────────┘
                                │
                     ┌──────────▼──────────┐
                     │  multi-user.target  │
                     └──────────┬──────────┘
                                │
          ┌─────────────────────┼─────────────────────┐
          │                     │                     │
┌─────────▼─────────┐ ┌─────────▼─────────┐ ┌────────▼────────┐
│  network.target   │ │  basic.target     │ │ timers.target   │
└───────────────────┘ └─────────┬─────────┘ └─────────────────┘
                                │
                     ┌──────────▼──────────┐
                     │   sysinit.target    │
                     └──────────┬──────────┘
                                │
                     ┌──────────▼──────────┐
                     │   local-fs.target   │
                     └─────────────────────┘
```

## Creating Custom Targets

```ini
# /etc/systemd/system/myapp.target
[Unit]
Description=My Application Stack
Requires=multi-user.target
After=multi-user.target
AllowIsolate=yes

[Install]
WantedBy=multi-user.target
```

## Common Target Directories

```bash
# Services wanted by multi-user.target
/etc/systemd/system/multi-user.target.wants/

# Services wanted by graphical.target
/etc/systemd/system/graphical.target.wants/
```
"""
        return ScrapedDocument(
            id=self._generate_id("systemd-targets"),
            url="https://www.freedesktop.org/software/systemd/man/systemd.target.html",
            title="systemd Targets (Runlevels)",
            content=content,
            source=self.get_source_name(),
            category="system_admin",
            tags=["systemd", "target", "runlevel", "boot", "linux"],
            scraped_at=datetime.utcnow().isoformat(),
            metadata={"type": "guide", "priority": "medium"}
        )
    
    def _journald_guide(self) -> ScrapedDocument:
        """journald logging guide."""
        content = """# journald and journalctl Reference

## Basic Log Viewing

```bash
# View all logs
journalctl

# Follow logs (like tail -f)
journalctl -f

# Show only recent logs
journalctl -n 50           # Last 50 lines
journalctl --since "1 hour ago"
journalctl --since today
journalctl --since "2025-01-01" --until "2025-01-02"
```

## Filtering Logs

### By Unit
```bash
journalctl -u nginx.service
journalctl -u nginx.service -u php-fpm.service
journalctl -u "nginx*"     # Wildcard
```

### By Priority
```bash
journalctl -p err          # Errors and above
journalctl -p warning      # Warnings and above

# Priority levels: emerg, alert, crit, err, warning, notice, info, debug
```

### By Boot
```bash
journalctl -b              # Current boot
journalctl -b -1           # Previous boot
journalctl --list-boots    # List all boots
```

### By Process/User
```bash
journalctl _PID=1234
journalctl _UID=1000
journalctl _COMM=sshd
```

### Kernel Messages
```bash
journalctl -k              # Kernel messages only
journalctl -k -b           # Kernel messages from current boot
```

## Output Formats

```bash
journalctl -o short        # Default
journalctl -o short-precise # With microseconds
journalctl -o verbose      # All fields
journalctl -o json         # JSON format
journalctl -o json-pretty  # Pretty JSON
journalctl -o cat          # Just message text
```

## Log Management

```bash
# Disk usage
journalctl --disk-usage

# Rotate/vacuum logs
journalctl --rotate
journalctl --vacuum-time=7d    # Keep 7 days
journalctl --vacuum-size=500M  # Keep 500MB

# Verify log integrity
journalctl --verify
```

## Configuration

**`/etc/systemd/journald.conf`**:
```ini
[Journal]
Storage=persistent          # persistent, volatile, auto, none
Compress=yes
SystemMaxUse=500M           # Max disk space
SystemMaxFileSize=50M       # Max per file
MaxRetentionSec=1month      # Max retention time
ForwardToSyslog=no
```

Apply changes:
```bash
systemctl restart systemd-journald
```

## Logging From Scripts

```bash
# Log to journal from shell
echo "My message" | systemd-cat -t myscript -p info

# With priority
systemd-cat -t backup -p warning echo "Backup took too long"

# Logger (syslog compatible)
logger -t myapp "Application started"
```

## Common Queries

```bash
# SSH login attempts
journalctl -u sshd.service | grep -i "failed"

# Boot errors
journalctl -b -p err

# Service crashes
journalctl -u myapp.service --since "1 hour ago" | grep -i "error\|fail\|crash"

# Disk-related messages
journalctl -k | grep -i "disk\|sd[a-z]\|nvme"
```
"""
        return ScrapedDocument(
            id=self._generate_id("journald-journalctl"),
            url="https://www.freedesktop.org/software/systemd/man/journalctl.html",
            title="journald and journalctl Reference",
            content=content,
            source=self.get_source_name(),
            category="system_admin",
            tags=["systemd", "journald", "journalctl", "logging", "linux"],
            scraped_at=datetime.utcnow().isoformat(),
            metadata={"type": "reference", "priority": "high"}
        )
    
    def _troubleshooting_guide(self) -> ScrapedDocument:
        """Troubleshooting guide."""
        content = """# systemd Troubleshooting Guide

## Service Won't Start

### 1. Check Status
```bash
systemctl status myservice.service
```

Look for:
- **Active**: Should show "active (running)"
- **Main PID**: Process ID if running
- **Log excerpt**: Recent log entries

### 2. Check Full Logs
```bash
journalctl -u myservice.service -n 100 --no-pager
journalctl -u myservice.service -f  # Follow live
```

### 3. Verify Unit File Syntax
```bash
systemd-analyze verify /etc/systemd/system/myservice.service
```

### 4. Check Dependencies
```bash
systemctl list-dependencies myservice.service
```

### 5. Try Manual Start
```bash
# Run the ExecStart command manually
sudo -u myuser /path/to/command --args
```

## Common Errors and Solutions

### "Failed to start: Unit not found"
```bash
# Reload unit files
sudo systemctl daemon-reload

# Check unit file location
ls -la /etc/systemd/system/myservice.service
```

### "Main process exited, code=exited, status=1/FAILURE"
```bash
# Check what exit code 1 means for your app
# Run manually to see error
/path/to/myapp

# Check permissions
ls -la /path/to/myapp
```

### "Failed to start: Unit is masked"
```bash
# Unmask the unit
sudo systemctl unmask myservice.service
```

### "Dependency failed"
```bash
# Check which dependency failed
systemctl list-dependencies myservice.service
systemctl status failed-dependency.service
```

### "Start request repeated too quickly"
```bash
# Service is crash-looping
# Check logs for the root cause
journalctl -u myservice.service --since "10 min ago"

# Increase restart delay
# In unit file:
RestartSec=30
StartLimitIntervalSec=500
StartLimitBurst=5
```

## Boot Issues

### Analyze Boot Time
```bash
systemd-analyze
systemd-analyze blame
systemd-analyze critical-chain

# Generate boot chart
systemd-analyze plot > boot.svg
```

### Rescue Mode
```bash
# At boot menu (GRUB), add to kernel line:
systemd.unit=rescue.target

# Or
systemctl rescue
```

### Emergency Mode
```bash
# Minimal boot with root filesystem
systemd.unit=emergency.target
```

## Reset Failed Units

```bash
# Reset all failed units
systemctl reset-failed

# Reset specific unit
systemctl reset-failed myservice.service
```

## Debug Mode

```bash
# Start unit in debug mode
SYSTEMD_LOG_LEVEL=debug systemctl start myservice.service

# Or set in unit file
[Service]
Environment=SYSTEMD_LOG_LEVEL=debug
```

## Check Configuration
```bash
# Show effective unit configuration
systemctl show myservice.service

# Show specific property
systemctl show -p ExecStart myservice.service
```
"""
        return ScrapedDocument(
            id=self._generate_id("systemd-troubleshooting"),
            url="synthetic://systemd-troubleshooting",
            title="systemd Troubleshooting Guide",
            content=content,
            source=self.get_source_name(),
            category="troubleshooting",
            tags=["systemd", "troubleshooting", "debug", "linux"],
            scraped_at=datetime.utcnow().isoformat(),
            metadata={"type": "troubleshooting", "priority": "high"}
        )
    
    def _security_guide(self) -> ScrapedDocument:
        """Security hardening guide."""
        content = """# systemd Security Hardening

## Service Sandboxing Options

### User/Group Isolation
```ini
[Service]
User=myapp
Group=myapp
DynamicUser=yes                    # Create ephemeral user
```

### Filesystem Restrictions
```ini
[Service]
# Read-only root filesystem
ProtectSystem=strict               # /usr, /boot, /efi read-only
ProtectHome=yes                    # /home inaccessible
PrivateTmp=yes                     # Private /tmp

# Specific paths
ReadOnlyPaths=/etc
ReadWritePaths=/var/lib/myapp
InaccessiblePaths=/root

# No new files
NoNewPrivileges=yes
```

### Network Restrictions
```ini
[Service]
PrivateNetwork=yes                 # No network access
RestrictAddressFamilies=AF_INET AF_INET6  # IPv4/6 only
IPAddressDeny=any                  # Deny all by default
IPAddressAllow=192.168.1.0/24      # Allow specific
```

### Capability Restrictions
```ini
[Service]
CapabilityBoundingSet=CAP_NET_BIND_SERVICE
AmbientCapabilities=CAP_NET_BIND_SERVICE
NoNewPrivileges=yes
```

### System Call Filtering
```ini
[Service]
SystemCallFilter=@system-service   # Allow basic syscalls
SystemCallFilter=~@clock           # Deny clock syscalls
SystemCallArchitectures=native     # Native arch only
```

## Complete Hardened Example

```ini
[Unit]
Description=Hardened Web Application

[Service]
Type=simple
User=webapp
Group=webapp

# Execution
ExecStart=/opt/webapp/bin/start
WorkingDirectory=/opt/webapp

# Filesystem
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
PrivateDevices=yes
ReadWritePaths=/var/lib/webapp /var/log/webapp

# Privileges
NoNewPrivileges=yes
CapabilityBoundingSet=
AmbientCapabilities=

# Network
PrivateNetwork=no
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX

# System
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectControlGroups=yes
LockPersonality=yes
RestrictRealtime=yes
RestrictSUIDSGID=yes

# Syscalls
SystemCallFilter=@system-service
SystemCallArchitectures=native
SystemCallErrorNumber=EPERM

[Install]
WantedBy=multi-user.target
```

## Check Security Score

```bash
# Analyze service security
systemd-analyze security myservice.service

# Check specific service
systemd-analyze security nginx.service
```
"""
        return ScrapedDocument(
            id=self._generate_id("systemd-security"),
            url="synthetic://systemd-security",
            title="systemd Security Hardening",
            content=content,
            source=self.get_source_name(),
            category="security",
            tags=["systemd", "security", "hardening", "sandboxing", "linux"],
            scraped_at=datetime.utcnow().isoformat(),
            metadata={"type": "guide", "priority": "high"}
        )
    
    def _user_services_guide(self) -> ScrapedDocument:
        """User services guide."""
        content = """# systemd User Services

## Overview

User services run as regular users (no sudo) and start when the user logs in.

## User Unit Location

```
~/.config/systemd/user/          # User's units
/etc/systemd/user/               # System-wide user units
/usr/lib/systemd/user/           # Distribution units
```

## Creating a User Service

```ini
# ~/.config/systemd/user/myapp.service
[Unit]
Description=My User Application
After=default.target

[Service]
Type=simple
ExecStart=/home/user/bin/myapp
Restart=on-failure

[Install]
WantedBy=default.target
```

## Managing User Services

```bash
# Note: No sudo needed!
systemctl --user daemon-reload
systemctl --user enable myapp.service
systemctl --user start myapp.service
systemctl --user status myapp.service

# List user services
systemctl --user list-units --type=service

# View logs
journalctl --user -u myapp.service
```

## Lingering (Run Without Login)

By default, user services only run when logged in. Enable lingering to run always:

```bash
# Enable lingering for user
sudo loginctl enable-linger username

# Check lingering status
loginctl show-user username | grep Linger

# Disable lingering
sudo loginctl disable-linger username
```

## Environment Variables

User services don't get your shell environment. Set explicitly:

```ini
[Service]
Environment=HOME=/home/user
Environment=PATH=/usr/local/bin:/usr/bin:/bin
EnvironmentFile=%h/.config/myapp/env
```

## Common User Services

- Syncthing
- Custom backup scripts
- Development servers
- Background download managers
- Notification daemons
"""
        return ScrapedDocument(
            id=self._generate_id("systemd-user-services"),
            url="synthetic://systemd-user-services",
            title="systemd User Services",
            content=content,
            source=self.get_source_name(),
            category="system_admin",
            tags=["systemd", "user-service", "linux"],
            scraped_at=datetime.utcnow().isoformat(),
            metadata={"type": "guide", "priority": "medium"}
        )
    
    def _dependencies_guide(self) -> ScrapedDocument:
        """Dependencies and ordering guide."""
        content = """# systemd Dependencies and Ordering

## Dependency Types

### Wants= (Soft Dependency)
```ini
[Unit]
Wants=redis.service
```
- Tries to start redis.service
- Continues even if redis fails
- Use for optional dependencies

### Requires= (Hard Dependency)
```ini
[Unit]
Requires=postgresql.service
```
- Must start postgresql.service
- Fails if postgresql fails
- Use for essential dependencies

### BindsTo= (Strong Bind)
```ini
[Unit]
BindsTo=postgresql.service
```
- Like Requires, plus:
- Stops when postgresql stops
- Use when units must run together

### PartOf= (Lifecycle Bind)
```ini
[Unit]
PartOf=mystack.target
```
- Stops/restarts when parent does
- Doesn't affect startup

### Requisite= (Pre-Check)
```ini
[Unit]
Requisite=network.target
```
- Fails immediately if dependency not already running
- Doesn't try to start dependency

## Ordering

### After= (Start After)
```ini
[Unit]
After=network.target postgresql.service
```
- Waits for listed units to start
- Does NOT create dependency (combine with Wants/Requires)

### Before= (Start Before)
```ini
[Unit]
Before=nginx.service
```
- Ensures this unit starts before nginx
- Rarely needed (usually use After= in other unit)

## Common Patterns

### Database-Backed Application
```ini
[Unit]
Description=My Web App
After=network.target postgresql.service
Requires=postgresql.service
Wants=redis.service
```

### Wait for Network
```ini
[Unit]
After=network.target                    # Network configured
After=network-online.target             # Network actually reachable
Wants=network-online.target
```

### Multiple Services as Stack
```ini
# mystack.target
[Unit]
Description=My Application Stack
Requires=myapp-web.service
Requires=myapp-worker.service
Requires=myapp-scheduler.service
After=myapp-web.service myapp-worker.service myapp-scheduler.service
```

## Viewing Dependencies

```bash
# What this unit needs
systemctl list-dependencies myapp.service

# What needs this unit
systemctl list-dependencies --reverse myapp.service

# Full recursive tree
systemctl list-dependencies --all myapp.service
```

## Ordering Analysis

```bash
# Check for ordering cycles
systemd-analyze verify myapp.service

# Show boot order
systemd-analyze critical-chain myapp.service
```
"""
        return ScrapedDocument(
            id=self._generate_id("systemd-dependencies"),
            url="synthetic://systemd-dependencies",
            title="systemd Dependencies and Ordering",
            content=content,
            source=self.get_source_name(),
            category="system_admin",
            tags=["systemd", "dependencies", "ordering", "linux"],
            scraped_at=datetime.utcnow().isoformat(),
            metadata={"type": "guide", "priority": "high"}
        )
    
    def _generate_id(self, name: str) -> str:
        """Generate document ID."""
        import hashlib
        return hashlib.md5(f"systemd-docs:{name}".encode()).hexdigest()[:16]


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Generate systemd documentation")
    parser.add_argument("--output-dir", default="data/linux/systemd-docs")
    args = parser.parse_args()
    
    logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(name)s:%(message)s')
    
    config = ScraperConfig(output_dir=Path(args.output_dir))
    scraper = SystemdDocsScraper(config)
    
    docs = scraper.scrape()
    scraper.save_documents(docs, "systemd_docs.jsonl")
