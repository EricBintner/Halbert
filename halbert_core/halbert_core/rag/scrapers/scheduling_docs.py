# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Task Scheduling Documentation Scraper.

Phase 27: RAG Coverage

Comprehensive scheduling guides covering:
- Cron jobs
- Systemd timers
- at command
- Anacron
"""

import logging
from typing import List
from datetime import datetime
from pathlib import Path

from .base import BaseScraper, ScrapedDocument, ScraperConfig

logger = logging.getLogger('halbert')


class SchedulingDocsScraper(BaseScraper):
    """Generates comprehensive task scheduling documentation."""
    
    def __init__(self, config: ScraperConfig):
        super().__init__(config)
    
    def get_source_name(self) -> str:
        return "scheduling-docs"
    
    def scrape(self) -> List[ScrapedDocument]:
        """Generate scheduling documentation."""
        logger.info("Generating scheduling documentation...")
        
        documents = []
        documents.extend(self._generate_guides())
        
        logger.info(f"Total scheduling documents: {len(documents)}")
        return documents
    
    def _generate_guides(self) -> List[ScrapedDocument]:
        """Generate all scheduling guides."""
        guides = []
        
        guides.append(self._cron_guide())
        guides.append(self._crontab_examples_guide())
        guides.append(self._systemd_timers_guide())
        guides.append(self._at_command_guide())
        guides.append(self._anacron_guide())
        guides.append(self._comparison_guide())
        
        return guides
    
    def _cron_guide(self) -> ScrapedDocument:
        """Cron basics guide."""
        content = """# Cron Jobs Guide

## Crontab Basics

```bash
# Edit user crontab
crontab -e

# List crontab
crontab -l

# Remove crontab
crontab -r

# Edit another user's crontab (root)
sudo crontab -u username -e
```

## Cron Syntax

```
┌───────────── minute (0-59)
│ ┌───────────── hour (0-23)
│ │ ┌───────────── day of month (1-31)
│ │ │ ┌───────────── month (1-12)
│ │ │ │ ┌───────────── day of week (0-7, 0 and 7 = Sunday)
│ │ │ │ │
* * * * * command
```

## Special Characters

| Character | Meaning |
|-----------|---------|
| `*` | Any value |
| `,` | Value list separator |
| `-` | Range of values |
| `/` | Step values |

## Examples

```bash
# Every minute
* * * * * /script.sh

# Every hour
0 * * * * /script.sh

# Every day at midnight
0 0 * * * /script.sh

# Every day at 2:30 AM
30 2 * * * /script.sh

# Every Monday at 9 AM
0 9 * * 1 /script.sh

# First day of every month
0 0 1 * * /script.sh

# Every 15 minutes
*/15 * * * * /script.sh

# Every weekday at 6 PM
0 18 * * 1-5 /script.sh

# Multiple times
0 8,12,18 * * * /script.sh

# Every 2 hours
0 */2 * * * /script.sh
```

## Special Strings

```bash
@reboot     # Run once at startup
@yearly     # 0 0 1 1 *
@annually   # Same as @yearly
@monthly    # 0 0 1 * *
@weekly     # 0 0 * * 0
@daily      # 0 0 * * *
@midnight   # Same as @daily
@hourly     # 0 * * * *

# Examples
@reboot /path/to/startup-script.sh
@daily /path/to/daily-backup.sh
```

## Environment Variables

```bash
# Set in crontab
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/sbin:/bin:/usr/sbin:/usr/bin
MAILTO=admin@example.com
HOME=/home/user

# Example with variables
0 * * * * /home/user/script.sh
```

## Output Handling

```bash
# Redirect output to file
0 * * * * /script.sh >> /var/log/cron.log 2>&1

# Discard output
0 * * * * /script.sh > /dev/null 2>&1

# Email output (default behavior if MAILTO set)
MAILTO=admin@example.com
0 * * * * /script.sh

# Disable email
0 * * * * /script.sh > /dev/null 2>&1
```

## Cron Directories

```bash
# Drop scripts in these directories
/etc/cron.hourly/
/etc/cron.daily/
/etc/cron.weekly/
/etc/cron.monthly/

# System crontab
/etc/crontab

# User crontabs stored in
/var/spool/cron/crontabs/  # Debian/Ubuntu
/var/spool/cron/           # RHEL/CentOS
```

## Troubleshooting

```bash
# Check cron logs
grep CRON /var/log/syslog
journalctl -u cron

# Verify cron service
systemctl status cron

# Test command manually
/bin/bash -c '/path/to/script.sh'

# Common issues:
# - Wrong PATH (use full paths)
# - Missing shebang in script
# - Wrong permissions
# - Script not executable
```
"""
        return ScrapedDocument(
            id=self._generate_id("cron-guide"),
            url="https://man7.org/linux/man-pages/man5/crontab.5.html",
            title="Cron Jobs Guide",
            content=content,
            source=self.get_source_name(),
            category="system_admin",
            tags=["cron", "scheduling", "linux", "automation"],
            scraped_at=datetime.utcnow().isoformat(),
            metadata={"type": "guide", "priority": "high"}
        )
    
    def _crontab_examples_guide(self) -> ScrapedDocument:
        """Crontab examples guide."""
        content = """# Crontab Examples

## Common Schedules

```bash
# Every minute
* * * * * command

# Every 5 minutes
*/5 * * * * command

# Every 10 minutes
*/10 * * * * command

# Every 15 minutes
*/15 * * * * command

# Every 30 minutes
*/30 * * * * command
0,30 * * * * command

# Every hour
0 * * * * command

# Every 2 hours
0 */2 * * * command

# Every 6 hours
0 */6 * * * command

# Every 12 hours
0 0,12 * * * command
```

## Daily Schedules

```bash
# Every day at midnight
0 0 * * * command

# Every day at 6 AM
0 6 * * * command

# Every day at 2:30 AM
30 2 * * * command

# Every day at 11 PM
0 23 * * * command

# Twice a day (6 AM and 6 PM)
0 6,18 * * * command

# Every day at 8 AM, 12 PM, 6 PM
0 8,12,18 * * * command
```

## Weekly Schedules

```bash
# Every Sunday at midnight
0 0 * * 0 command

# Every Monday at 9 AM
0 9 * * 1 command

# Every Friday at 5 PM
0 17 * * 5 command

# Weekdays at 8 AM
0 8 * * 1-5 command

# Weekends at 10 AM
0 10 * * 0,6 command

# Monday, Wednesday, Friday at 9 AM
0 9 * * 1,3,5 command
```

## Monthly Schedules

```bash
# First day of month at midnight
0 0 1 * * command

# Last day of month (approximate)
0 0 28-31 * * [ "$(date +%d -d tomorrow)" = "01" ] && command

# 15th of each month
0 0 15 * * command

# First Monday of month
0 9 1-7 * 1 command

# First and 15th of month
0 0 1,15 * * command
```

## Real-World Examples

```bash
# System Maintenance
# Update packages weekly
0 3 * * 0 apt update && apt upgrade -y

# Clean temp files daily
0 4 * * * find /tmp -type f -mtime +7 -delete

# Rotate logs
0 0 * * * logrotate /etc/logrotate.conf

# Backups
# Daily database backup at 2 AM
0 2 * * * /usr/local/bin/backup-db.sh

# Weekly full backup on Sunday
0 1 * * 0 /usr/local/bin/full-backup.sh

# Daily incremental backup
0 1 * * 1-6 /usr/local/bin/incremental-backup.sh

# Monitoring
# Check disk space every hour
0 * * * * /usr/local/bin/check-disk.sh

# Health check every 5 minutes
*/5 * * * * /usr/local/bin/health-check.sh

# Certificate renewal
0 3 1 * * certbot renew --quiet

# Web Tasks
# Clear cache at midnight
0 0 * * * /usr/local/bin/clear-cache.sh

# Generate reports at 6 AM
0 6 * * * /usr/local/bin/generate-reports.sh

# Sync data every 15 minutes
*/15 * * * * rsync -avz /source/ /destination/
```

## Crontab Template

```bash
# Edit with: crontab -e
# ┌───────────── minute (0-59)
# │ ┌───────────── hour (0-23)
# │ │ ┌───────────── day of month (1-31)
# │ │ │ ┌───────────── month (1-12)
# │ │ │ │ ┌───────────── day of week (0-7)
# │ │ │ │ │
# * * * * * command

# Environment
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/sbin:/bin:/usr/sbin:/usr/bin
MAILTO=admin@example.com

# Hourly tasks
0 * * * * /home/user/scripts/hourly-task.sh >> /var/log/hourly.log 2>&1

# Daily tasks
0 2 * * * /home/user/scripts/daily-backup.sh >> /var/log/backup.log 2>&1

# Weekly tasks
0 3 * * 0 /home/user/scripts/weekly-cleanup.sh >> /var/log/cleanup.log 2>&1
```
"""
        return ScrapedDocument(
            id=self._generate_id("crontab-examples"),
            url="synthetic://crontab-examples",
            title="Crontab Examples",
            content=content,
            source=self.get_source_name(),
            category="system_admin",
            tags=["cron", "crontab", "examples", "scheduling"],
            scraped_at=datetime.utcnow().isoformat(),
            metadata={"type": "reference", "priority": "high"}
        )
    
    def _systemd_timers_guide(self) -> ScrapedDocument:
        """Systemd timers guide."""
        content = """# Systemd Timers Guide

## Overview

Systemd timers are the modern alternative to cron. They offer:
- Better logging (journald)
- Dependencies on other units
- Precise timing options
- Easy monitoring

## Timer Files

A timer requires two files:
1. `myservice.timer` - When to run
2. `myservice.service` - What to run

### Example Timer

```ini
# /etc/systemd/system/backup.timer
[Unit]
Description=Daily backup timer

[Timer]
OnCalendar=*-*-* 02:00:00
Persistent=true

[Install]
WantedBy=timers.target
```

### Example Service

```ini
# /etc/systemd/system/backup.service
[Unit]
Description=Backup service

[Service]
Type=oneshot
ExecStart=/usr/local/bin/backup.sh
```

## Timer Options

### Monotonic Timers (Relative)

```ini
[Timer]
OnBootSec=15min          # 15 min after boot
OnStartupSec=5min        # 5 min after systemd start
OnActiveSec=1h           # 1 hour after timer activation
OnUnitActiveSec=1d       # 1 day after service last ran
OnUnitInactiveSec=1h     # 1 hour after service stopped
```

### Realtime Timers (Calendar)

```ini
[Timer]
OnCalendar=hourly
OnCalendar=daily
OnCalendar=weekly
OnCalendar=monthly
OnCalendar=*-*-* 00:00:00        # Daily at midnight
OnCalendar=Mon *-*-* 09:00:00    # Every Monday 9 AM
OnCalendar=*-*-01 00:00:00       # First of month
OnCalendar=*:0/15                # Every 15 minutes
```

### Calendar Syntax

```
DayOfWeek Year-Month-Day Hour:Minute:Second

Examples:
Mon,Tue,Wed *-*-* 00:00:00   # Mon-Wed midnight
*-*-* 08:00:00               # Daily 8 AM
*-*-1,15 00:00:00            # 1st and 15th
Sat,Sun *-*-* 10:00:00       # Weekends 10 AM
*-01,07 01 00:00:00          # Jan and Jul 1st
*:0/5                        # Every 5 minutes
*:*:0/30                     # Every 30 seconds
```

## Common Options

```ini
[Timer]
# Accuracy (default 1 minute)
AccuracySec=1s

# Run missed events after boot
Persistent=true

# Random delay
RandomizedDelaySec=1h

# Wake from suspend
WakeSystem=true
```

## Management Commands

```bash
# List all timers
systemctl list-timers
systemctl list-timers --all

# Enable timer
sudo systemctl enable backup.timer
sudo systemctl start backup.timer

# Disable timer
sudo systemctl disable backup.timer
sudo systemctl stop backup.timer

# Check status
systemctl status backup.timer
systemctl status backup.service

# View logs
journalctl -u backup.service
journalctl -u backup.timer

# Reload after changes
sudo systemctl daemon-reload

# Test timer expression
systemd-analyze calendar "*-*-* 02:00:00"
systemd-analyze calendar --iterations=5 "daily"
```

## User Timers

```bash
# Create in user directory
mkdir -p ~/.config/systemd/user/

# User timer
# ~/.config/systemd/user/mytask.timer

# Enable user timer
systemctl --user enable mytask.timer
systemctl --user start mytask.timer

# Enable lingering (run without login)
loginctl enable-linger $USER
```

## Complete Example

```ini
# /etc/systemd/system/cleanup.timer
[Unit]
Description=Weekly cleanup timer

[Timer]
OnCalendar=Sun *-*-* 03:00:00
Persistent=true
RandomizedDelaySec=30min

[Install]
WantedBy=timers.target
```

```ini
# /etc/systemd/system/cleanup.service
[Unit]
Description=Weekly cleanup

[Service]
Type=oneshot
ExecStart=/usr/local/bin/cleanup.sh
Nice=19
IOSchedulingClass=idle
```

```bash
# Enable and start
sudo systemctl daemon-reload
sudo systemctl enable --now cleanup.timer
```
"""
        return ScrapedDocument(
            id=self._generate_id("systemd-timers"),
            url="https://www.freedesktop.org/software/systemd/man/systemd.timer.html",
            title="Systemd Timers Guide",
            content=content,
            source=self.get_source_name(),
            category="system_admin",
            tags=["systemd", "timers", "scheduling", "linux"],
            scraped_at=datetime.utcnow().isoformat(),
            metadata={"type": "guide", "priority": "high"}
        )
    
    def _at_command_guide(self) -> ScrapedDocument:
        """at command guide."""
        content = """# at Command Guide

## Overview

The `at` command runs commands once at a specific time.

## Installation

```bash
# Debian/Ubuntu
sudo apt install at

# RHEL/CentOS
sudo dnf install at

# Start service
sudo systemctl enable --now atd
```

## Basic Usage

```bash
# Schedule command
at 10:00
at> /path/to/script.sh
at> <Ctrl+D>

# One-liner
echo "/path/to/script.sh" | at 10:00

# From file
at 10:00 -f /path/to/script.sh
```

## Time Specifications

```bash
# Specific time
at 10:00                  # 10:00 AM
at 10:00 PM               # 10:00 PM
at 22:00                  # 22:00 (10 PM)
at 2:30 AM                # 2:30 AM

# Relative time
at now + 5 minutes
at now + 1 hour
at now + 2 days
at now + 1 week

# Specific date
at 10:00 Dec 25
at 10:00 12/25/2024
at 10:00 2024-12-25

# Keywords
at noon                   # 12:00 PM
at midnight              # 00:00
at teatime               # 4:00 PM
at tomorrow              # Tomorrow same time
at next week             # Next week same time
```

## Managing Jobs

```bash
# List pending jobs
atq
at -l

# View job contents
at -c job_number

# Remove job
atrm job_number
at -r job_number

# Remove all jobs
atrm $(atq | cut -f1)
```

## Examples

```bash
# Shutdown at midnight
echo "shutdown -h now" | sudo at midnight

# Reminder in 30 minutes
echo 'notify-send "Meeting in 5 minutes"' | at now + 25 minutes

# Run backup tomorrow at 2 AM
at 2:00 AM tomorrow << EOF
/usr/local/bin/backup.sh
EOF

# Multiple commands
at 10:00 tomorrow << 'EOF'
cd /var/www
git pull
systemctl restart nginx
EOF
```

## Batch Command

```bash
# Run when system load is low
batch << EOF
/path/to/heavy-script.sh
EOF

# Same as
echo "/path/to/heavy-script.sh" | batch
```

## Access Control

```bash
# Allow users
/etc/at.allow

# Deny users
/etc/at.deny

# If neither exists, only root can use at
# If at.deny exists and is empty, all can use at
```

## Output

```bash
# Output is mailed to user by default
# Redirect to file
at 10:00 << EOF
/script.sh > /var/log/output.log 2>&1
EOF

# Or set MAILTO
echo 'MAILTO=""; /script.sh' | at 10:00
```
"""
        return ScrapedDocument(
            id=self._generate_id("at-command"),
            url="https://man7.org/linux/man-pages/man1/at.1.html",
            title="at Command Guide",
            content=content,
            source=self.get_source_name(),
            category="system_admin",
            tags=["at", "scheduling", "linux", "one-time"],
            scraped_at=datetime.utcnow().isoformat(),
            metadata={"type": "guide", "priority": "medium"}
        )
    
    def _anacron_guide(self) -> ScrapedDocument:
        """Anacron guide."""
        content = """# Anacron Guide

## Overview

Anacron runs periodic jobs that would be missed if the system was off.
Unlike cron, it doesn't assume the system runs 24/7.

## How It Works

1. Checks if job was run within its period
2. If not, waits the delay time, then runs
3. Records timestamp when job completes

## Configuration

```bash
# /etc/anacrontab
# period  delay  job-id  command

1       5       daily-backup    /usr/local/bin/daily-backup.sh
7       10      weekly-cleanup  /usr/local/bin/weekly-cleanup.sh
30      15      monthly-report  /usr/local/bin/monthly-report.sh
@monthly 15     monthly-alt     /usr/local/bin/monthly-alt.sh
```

### Fields

| Field | Description |
|-------|-------------|
| period | Days between runs (or @daily, @weekly, @monthly) |
| delay | Minutes to wait after anacron starts |
| job-id | Unique identifier for the job |
| command | Command to run |

## Default Anacron Jobs

```bash
# /etc/anacrontab includes:
1       5       cron.daily      run-parts /etc/cron.daily
7       10      cron.weekly     run-parts /etc/cron.weekly
@monthly 15     cron.monthly    run-parts /etc/cron.monthly
```

## Commands

```bash
# Run anacron manually
sudo anacron

# Test (don't run, just show what would run)
sudo anacron -T

# Force run all jobs
sudo anacron -f

# Run now (ignore delays)
sudo anacron -n

# Update timestamps without running
sudo anacron -u
```

## Timestamps

```bash
# Timestamp directory
/var/spool/anacron/

# Files named by job-id
/var/spool/anacron/daily-backup
/var/spool/anacron/weekly-cleanup
```

## When Anacron Runs

Typically triggered by:

1. **Systemd timer** (modern systems)
```bash
systemctl status anacron.timer
```

2. **Cron** (older systems)
```bash
# /etc/cron.d/anacron
30 7 * * * root anacron -s
```

## Comparison with Cron

| Feature | Cron | Anacron |
|---------|------|---------|
| Minimum interval | 1 minute | 1 day |
| Runs missed jobs | No | Yes |
| Requires uptime | Yes | No |
| Best for | Servers | Desktops/Laptops |

## Example Setup

```bash
# /etc/anacrontab

# Environment
SHELL=/bin/bash
PATH=/sbin:/bin:/usr/sbin:/usr/bin
MAILTO=admin@example.com

# Jobs
# Daily tasks - run 5 min after anacron starts
1       5       daily-tasks     /usr/local/bin/daily-tasks.sh

# Weekly on Sunday equivalent - 10 min delay
7       10      weekly-tasks    /usr/local/bin/weekly-tasks.sh

# Monthly - 15 min delay
@monthly 15     monthly-tasks   /usr/local/bin/monthly-tasks.sh
```
"""
        return ScrapedDocument(
            id=self._generate_id("anacron-guide"),
            url="https://man7.org/linux/man-pages/man8/anacron.8.html",
            title="Anacron Guide",
            content=content,
            source=self.get_source_name(),
            category="system_admin",
            tags=["anacron", "scheduling", "linux", "periodic"],
            scraped_at=datetime.utcnow().isoformat(),
            metadata={"type": "guide", "priority": "medium"}
        )
    
    def _comparison_guide(self) -> ScrapedDocument:
        """Scheduling tools comparison guide."""
        content = """# Linux Task Scheduling Comparison

## Quick Reference

| Tool | Use Case | Min Interval | Catches Missed |
|------|----------|--------------|----------------|
| cron | Regular scheduled tasks | 1 minute | No |
| systemd timer | Modern alternative to cron | 1 second | Yes (Persistent) |
| at | One-time scheduled task | N/A | N/A |
| anacron | Daily+ tasks on desktops | 1 day | Yes |

## When to Use What

### Use Cron When:
- Simple, recurring tasks
- Minute-level precision needed
- System runs 24/7
- Legacy compatibility required

### Use Systemd Timers When:
- Better logging needed (journald)
- Dependencies matter
- Second-level precision needed
- Need to catch missed runs
- Complex scheduling logic

### Use at When:
- One-time future task
- Scheduling during conversation
- Quick ad-hoc scheduling

### Use Anacron When:
- Desktop/laptop that's not always on
- Daily or less frequent tasks
- Must not miss scheduled tasks

## Feature Comparison

### Cron
```bash
# Pros
+ Simple syntax
+ Universal availability
+ Well documented
+ Lightweight

# Cons
- No dependency management
- Basic logging
- Misses tasks if system off
- No sub-minute scheduling
```

### Systemd Timers
```bash
# Pros
+ Integrated logging
+ Dependency support
+ Second precision
+ Persistent option
+ Resource controls

# Cons
- More complex setup
- Two files needed
- Systemd required
```

### Migration Example

#### Cron to Systemd Timer

**Before (cron):**
```
0 2 * * * /usr/local/bin/backup.sh
```

**After (systemd):**
```ini
# /etc/systemd/system/backup.timer
[Unit]
Description=Daily backup

[Timer]
OnCalendar=*-*-* 02:00:00
Persistent=true

[Install]
WantedBy=timers.target
```

```ini
# /etc/systemd/system/backup.service
[Unit]
Description=Backup service

[Service]
Type=oneshot
ExecStart=/usr/local/bin/backup.sh
```

```bash
sudo systemctl enable --now backup.timer
```

## Best Practices

1. **Always use full paths** in scheduled tasks
2. **Log output** to files or use proper logging
3. **Handle errors** in scripts
4. **Set proper permissions** on scripts
5. **Test manually** before scheduling
6. **Use comments** to document schedules
7. **Monitor** scheduled tasks regularly

## Debugging Checklist

```bash
# Cron
- [ ] Check /var/log/syslog or journalctl -u cron
- [ ] Verify PATH in crontab
- [ ] Test script manually with same user
- [ ] Check file permissions
- [ ] Verify cron service running

# Systemd Timer
- [ ] systemctl status mytask.timer
- [ ] systemctl status mytask.service
- [ ] journalctl -u mytask.service
- [ ] systemd-analyze calendar "expression"
- [ ] Check for typos in unit files
```
"""
        return ScrapedDocument(
            id=self._generate_id("scheduling-comparison"),
            url="synthetic://scheduling-comparison",
            title="Linux Task Scheduling Comparison",
            content=content,
            source=self.get_source_name(),
            category="system_admin",
            tags=["cron", "systemd", "scheduling", "comparison"],
            scraped_at=datetime.utcnow().isoformat(),
            metadata={"type": "comparison", "priority": "high"}
        )
    
    def _generate_id(self, name: str) -> str:
        """Generate document ID."""
        import hashlib
        return hashlib.md5(f"scheduling-docs:{name}".encode()).hexdigest()[:16]


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Generate scheduling documentation")
    parser.add_argument("--output-dir", default="data/linux/scheduling-docs")
    args = parser.parse_args()
    
    logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(name)s:%(message)s')
    
    config = ScraperConfig(output_dir=Path(args.output_dir))
    scraper = SchedulingDocsScraper(config)
    
    docs = scraper.scrape()
    scraper.save_documents(docs, "scheduling_docs.jsonl")
