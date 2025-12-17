"""
Logging Documentation Scraper.

Phase 27: RAG Coverage

Comprehensive logging guides covering:
- journald/journalctl
- rsyslog
- logrotate
- Log analysis
"""

import logging
from typing import List
from datetime import datetime
from pathlib import Path

from .base import BaseScraper, ScrapedDocument, ScraperConfig

logger = logging.getLogger('halbert')


class LoggingDocsScraper(BaseScraper):
    """Generates comprehensive logging documentation."""
    
    def __init__(self, config: ScraperConfig):
        super().__init__(config)
    
    def get_source_name(self) -> str:
        return "logging-docs"
    
    def scrape(self) -> List[ScrapedDocument]:
        """Generate logging documentation."""
        logger.info("Generating logging documentation...")
        
        documents = []
        documents.extend(self._generate_guides())
        
        logger.info(f"Total logging documents: {len(documents)}")
        return documents
    
    def _generate_guides(self) -> List[ScrapedDocument]:
        """Generate all logging guides."""
        guides = []
        
        guides.append(self._journalctl_guide())
        guides.append(self._rsyslog_guide())
        guides.append(self._logrotate_guide())
        guides.append(self._log_files_guide())
        guides.append(self._log_analysis_guide())
        guides.append(self._centralized_logging_guide())
        
        return guides
    
    def _journalctl_guide(self) -> ScrapedDocument:
        """journalctl guide."""
        content = """# journalctl Guide

## Basic Usage

```bash
# View all logs
journalctl

# Follow new logs
journalctl -f

# Last N lines
journalctl -n 100

# Reverse order (newest first)
journalctl -r

# No pager
journalctl --no-pager
```

## Filter by Unit

```bash
# Specific service
journalctl -u nginx
journalctl -u nginx.service

# Multiple units
journalctl -u nginx -u php-fpm

# User units
journalctl --user -u myapp
```

## Filter by Time

```bash
# Since/until
journalctl --since "2024-01-01"
journalctl --since "1 hour ago"
journalctl --since "yesterday"
journalctl --until "2024-01-01 12:00:00"

# Boot
journalctl -b                    # Current boot
journalctl -b -1                 # Previous boot
journalctl --list-boots          # List boots
```

## Filter by Priority

```bash
# Priority levels: emerg, alert, crit, err, warning, notice, info, debug
journalctl -p err                # Errors and above
journalctl -p warning            # Warnings and above
journalctl -p 0..4               # Range (emerg to warning)
```

## Filter by Other Criteria

```bash
# By PID
journalctl _PID=1234

# By UID
journalctl _UID=1000

# By executable
journalctl /usr/bin/nginx

# Kernel messages
journalctl -k
journalctl --dmesg

# By transport
journalctl _TRANSPORT=kernel
journalctl _TRANSPORT=syslog
```

## Output Formats

```bash
# Short (default)
journalctl -o short

# Verbose
journalctl -o verbose

# JSON
journalctl -o json
journalctl -o json-pretty

# Cat (message only)
journalctl -o cat

# Export
journalctl -o export
```

## Disk Usage

```bash
# Current usage
journalctl --disk-usage

# Vacuum by size
sudo journalctl --vacuum-size=500M

# Vacuum by time
sudo journalctl --vacuum-time=7d

# Vacuum by files
sudo journalctl --vacuum-files=5
```

## Configuration

```ini
# /etc/systemd/journald.conf

[Journal]
Storage=persistent           # persistent, volatile, auto, none
Compress=yes
SystemMaxUse=500M           # Max disk usage
SystemMaxFileSize=50M       # Max file size
MaxRetentionSec=1month      # Max retention time
ForwardToSyslog=yes
```

```bash
# Restart after changes
sudo systemctl restart systemd-journald
```

## Examples

```bash
# SSH login failures
journalctl -u sshd | grep -i "failed"

# Nginx errors today
journalctl -u nginx --since today -p err

# Kernel errors this boot
journalctl -k -b -p err

# Follow multiple services
journalctl -f -u nginx -u php-fpm

# Export for analysis
journalctl -u nginx --since "1 week ago" -o json > nginx.json
```
"""
        return ScrapedDocument(
            id=self._generate_id("journalctl"),
            url="https://www.freedesktop.org/software/systemd/man/journalctl.html",
            title="journalctl Guide",
            content=content,
            source=self.get_source_name(),
            category="logging",
            tags=["journalctl", "systemd", "logging", "linux"],
            scraped_at=datetime.utcnow().isoformat(),
            metadata={"type": "guide", "priority": "high"}
        )
    
    def _rsyslog_guide(self) -> ScrapedDocument:
        """rsyslog guide."""
        content = """# rsyslog Guide

## Overview

rsyslog is the traditional syslog daemon, still used alongside journald.

## Configuration

```bash
# Main config
/etc/rsyslog.conf

# Drop-in configs
/etc/rsyslog.d/*.conf
```

### Basic Syntax

```
facility.priority    destination
```

### Facilities

| Facility | Description |
|----------|-------------|
| auth | Authentication |
| authpriv | Private auth |
| cron | Cron daemon |
| daemon | System daemons |
| kern | Kernel |
| local0-7 | Custom use |
| mail | Mail system |
| syslog | Syslog itself |
| user | User processes |
| * | All facilities |

### Priorities

| Priority | Description |
|----------|-------------|
| emerg | System unusable |
| alert | Immediate action |
| crit | Critical |
| err | Errors |
| warning | Warnings |
| notice | Normal but significant |
| info | Informational |
| debug | Debug messages |
| none | Disable facility |

## Configuration Examples

```bash
# /etc/rsyslog.conf

# Log all kernel messages
kern.*                          /var/log/kern.log

# Log auth messages
auth,authpriv.*                 /var/log/auth.log

# Log everything except auth
*.*;auth,authpriv.none          /var/log/syslog

# Log warnings and above
*.warning                       /var/log/warnings.log

# Log errors to separate file
*.err                           /var/log/errors.log

# Local custom logs
local0.*                        /var/log/myapp.log
```

## Remote Logging

### Receiving Logs

```bash
# /etc/rsyslog.conf

# UDP
module(load="imudp")
input(type="imudp" port="514")

# TCP
module(load="imtcp")
input(type="imtcp" port="514")
```

### Sending Logs

```bash
# Send to remote server
*.* @192.168.1.100:514          # UDP
*.* @@192.168.1.100:514         # TCP

# Send specific logs
auth.* @@logserver.example.com:514
```

## Templates

```bash
# Custom log format
template(name="CustomFormat" type="string"
    string="%timegenerated% %HOSTNAME% %syslogtag% %msg%\n")

*.* /var/log/custom.log;CustomFormat

# JSON format
template(name="JsonFormat" type="list") {
    constant(value="{")
    constant(value="\"timestamp\":\"")
    property(name="timereported" dateFormat="rfc3339")
    constant(value="\",\"host\":\"")
    property(name="hostname")
    constant(value="\",\"message\":\"")
    property(name="msg" format="json")
    constant(value="\"}\n")
}
```

## Filtering

```bash
# Property-based filter
:msg, contains, "error" /var/log/errors.log

# Expression-based filter
if $programname == 'nginx' then /var/log/nginx/nginx.log

# Stop processing
if $programname == 'nginx' then {
    /var/log/nginx/nginx.log
    stop
}
```

## Commands

```bash
# Test configuration
sudo rsyslogd -N1

# Restart service
sudo systemctl restart rsyslog

# Check status
sudo systemctl status rsyslog
```
"""
        return ScrapedDocument(
            id=self._generate_id("rsyslog"),
            url="https://www.rsyslog.com/doc/",
            title="rsyslog Guide",
            content=content,
            source=self.get_source_name(),
            category="logging",
            tags=["rsyslog", "syslog", "logging", "linux"],
            scraped_at=datetime.utcnow().isoformat(),
            metadata={"type": "guide", "priority": "medium"}
        )
    
    def _logrotate_guide(self) -> ScrapedDocument:
        """logrotate guide."""
        content = """# logrotate Guide

## Overview

logrotate rotates, compresses, and removes old log files.

## Configuration

```bash
# Main config
/etc/logrotate.conf

# Drop-in configs
/etc/logrotate.d/
```

## Basic Syntax

```bash
/var/log/myapp/*.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
    create 644 root root
    postrotate
        systemctl reload myapp
    endscript
}
```

## Common Options

| Option | Description |
|--------|-------------|
| daily/weekly/monthly | Rotation frequency |
| rotate N | Keep N rotated files |
| compress | Compress rotated files |
| delaycompress | Compress after next rotation |
| missingok | Don't error if log missing |
| notifempty | Don't rotate empty files |
| create MODE USER GROUP | Create new log file |
| copytruncate | Copy and truncate (for apps that can't reopen) |
| dateext | Add date to rotated filename |
| maxsize SIZE | Rotate when exceeds size |
| minsize SIZE | Don't rotate if smaller |
| size SIZE | Rotate only by size |

## Example Configurations

### nginx
```bash
/var/log/nginx/*.log {
    daily
    rotate 14
    compress
    delaycompress
    missingok
    notifempty
    create 0640 www-data adm
    sharedscripts
    postrotate
        [ -f /var/run/nginx.pid ] && kill -USR1 $(cat /var/run/nginx.pid)
    endscript
}
```

### Application Log
```bash
/var/log/myapp/app.log {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
    copytruncate
    dateext
    dateformat -%Y%m%d
    maxsize 100M
}
```

### System Log
```bash
/var/log/syslog {
    rotate 7
    daily
    compress
    delaycompress
    missingok
    notifempty
    postrotate
        /usr/lib/rsyslog/rsyslog-rotate
    endscript
}
```

## Scripts

```bash
/var/log/myapp/*.log {
    daily
    rotate 7
    
    # Run once before all rotations
    firstaction
        echo "Starting rotation" | mail -s "Rotation starting" admin@example.com
    endscript
    
    # Run before each log rotation
    prerotate
        # Pre-rotation commands
    endscript
    
    # Run after each log rotation
    postrotate
        systemctl reload myapp
    endscript
    
    # Run once after all rotations
    lastaction
        echo "Rotation complete"
    endscript
}

# sharedscripts - run scripts once for all matched files
/var/log/myapp/*.log {
    sharedscripts
    postrotate
        systemctl reload myapp
    endscript
}
```

## Commands

```bash
# Test configuration
logrotate -d /etc/logrotate.conf

# Force rotation
sudo logrotate -f /etc/logrotate.conf

# Force specific config
sudo logrotate -f /etc/logrotate.d/nginx

# Verbose
sudo logrotate -v /etc/logrotate.conf

# Status file
cat /var/lib/logrotate/status
```

## Troubleshooting

```bash
# Debug mode
logrotate -d /etc/logrotate.conf

# Check status
cat /var/lib/logrotate/status

# Force rotation for testing
sudo logrotate -f -v /etc/logrotate.d/myapp

# Check cron is running logrotate
cat /etc/cron.daily/logrotate
```
"""
        return ScrapedDocument(
            id=self._generate_id("logrotate"),
            url="https://man7.org/linux/man-pages/man8/logrotate.8.html",
            title="logrotate Guide",
            content=content,
            source=self.get_source_name(),
            category="logging",
            tags=["logrotate", "logging", "linux", "rotation"],
            scraped_at=datetime.utcnow().isoformat(),
            metadata={"type": "guide", "priority": "high"}
        )
    
    def _log_files_guide(self) -> ScrapedDocument:
        """Common log files guide."""
        content = """# Linux Log Files Reference

## System Logs

| File | Description |
|------|-------------|
| `/var/log/syslog` | General system log (Debian) |
| `/var/log/messages` | General system log (RHEL) |
| `/var/log/dmesg` | Kernel ring buffer |
| `/var/log/kern.log` | Kernel logs |
| `/var/log/boot.log` | Boot messages |

## Authentication Logs

| File | Description |
|------|-------------|
| `/var/log/auth.log` | Authentication (Debian) |
| `/var/log/secure` | Authentication (RHEL) |
| `/var/log/faillog` | Failed login attempts |
| `/var/log/lastlog` | Last login for each user |
| `/var/log/wtmp` | Login history (binary) |
| `/var/log/btmp` | Bad login attempts (binary) |

## Service Logs

| File | Description |
|------|-------------|
| `/var/log/apache2/` | Apache web server |
| `/var/log/nginx/` | Nginx web server |
| `/var/log/mysql/` | MySQL database |
| `/var/log/postgresql/` | PostgreSQL database |
| `/var/log/mail.log` | Mail server |

## Package Management

| File | Description |
|------|-------------|
| `/var/log/apt/` | APT package manager |
| `/var/log/dpkg.log` | dpkg operations |
| `/var/log/yum.log` | YUM package manager |
| `/var/log/dnf.log` | DNF package manager |

## Viewing Logs

```bash
# Real-time viewing
tail -f /var/log/syslog
tail -f /var/log/nginx/access.log

# Last N lines
tail -100 /var/log/syslog

# Search logs
grep "error" /var/log/syslog
grep -i "failed" /var/log/auth.log

# View compressed logs
zcat /var/log/syslog.1.gz
zgrep "error" /var/log/syslog.*.gz

# Follow multiple files
tail -f /var/log/nginx/*.log

# View binary logs
last                     # wtmp
lastb                    # btmp (failed logins)
faillog -a               # faillog
```

## journald Equivalents

```bash
# syslog
journalctl

# auth.log
journalctl -u sshd
journalctl _COMM=sudo

# kern.log
journalctl -k

# Service logs
journalctl -u nginx
journalctl -u mysql
```

## Log Permissions

```bash
# Most logs owned by root
-rw-r----- root adm /var/log/syslog

# Some logs more restricted
-rw-r----- root adm /var/log/auth.log
-rw------- root root /var/log/btmp

# Add user to adm group to read logs
sudo usermod -aG adm username
```

## Finding Logs

```bash
# Find all logs modified today
find /var/log -mtime 0 -type f

# Find large log files
find /var/log -size +100M -type f

# Disk usage
du -sh /var/log/*
```
"""
        return ScrapedDocument(
            id=self._generate_id("log-files"),
            url="synthetic://log-files",
            title="Linux Log Files Reference",
            content=content,
            source=self.get_source_name(),
            category="logging",
            tags=["logs", "linux", "reference", "files"],
            scraped_at=datetime.utcnow().isoformat(),
            metadata={"type": "reference", "priority": "high"}
        )
    
    def _log_analysis_guide(self) -> ScrapedDocument:
        """Log analysis guide."""
        content = """# Log Analysis Guide

## Text Processing Tools

### grep

```bash
# Search pattern
grep "error" /var/log/syslog
grep -i "error" /var/log/syslog        # Case insensitive
grep -v "debug" /var/log/syslog        # Exclude pattern
grep -c "error" /var/log/syslog        # Count matches
grep -n "error" /var/log/syslog        # Line numbers

# Context
grep -A 5 "error" /var/log/syslog      # 5 lines after
grep -B 5 "error" /var/log/syslog      # 5 lines before
grep -C 5 "error" /var/log/syslog      # 5 lines around

# Multiple patterns
grep -E "error|warning" /var/log/syslog
egrep "error|warning" /var/log/syslog
```

### awk

```bash
# Extract fields (space-separated)
awk '{print $1, $4}' /var/log/nginx/access.log

# Count by field
awk '{print $1}' access.log | sort | uniq -c | sort -rn

# Filter by field
awk '$9 == 500' access.log             # HTTP 500 errors

# Sum values
awk '{sum += $10} END {print sum}' access.log
```

### sed

```bash
# Extract between patterns
sed -n '/START/,/END/p' logfile

# Remove timestamps
sed 's/^.*\] //' logfile
```

## Common Analysis Tasks

### Count Occurrences

```bash
# Count lines with pattern
grep -c "error" /var/log/syslog

# Count unique values
awk '{print $1}' access.log | sort | uniq -c | sort -rn | head

# Count by hour
awk '{print $4}' access.log | cut -d: -f2 | sort | uniq -c
```

### Find Top Items

```bash
# Top IPs in access log
awk '{print $1}' access.log | sort | uniq -c | sort -rn | head -10

# Top URLs
awk '{print $7}' access.log | sort | uniq -c | sort -rn | head -10

# Top user agents
awk -F'"' '{print $6}' access.log | sort | uniq -c | sort -rn | head
```

### Time-based Analysis

```bash
# Requests per minute
awk '{print $4}' access.log | cut -d: -f1-2 | uniq -c

# Requests per hour
awk '{print $4}' access.log | cut -d: -f1-2 | cut -d: -f1-2 | uniq -c

# Errors in last hour
grep "$(date -d '1 hour ago' +'%d/%b/%Y:%H')" access.log | grep -c " 500 "
```

### Response Codes

```bash
# Count by response code
awk '{print $9}' access.log | sort | uniq -c | sort -rn

# Find 5xx errors
awk '$9 ~ /^5/' access.log

# Error rate
awk '{total++; if($9 ~ /^5/) errors++} END {print errors/total*100"%"}' access.log
```

## Real-time Monitoring

```bash
# Follow with highlighting
tail -f /var/log/syslog | grep --color=always -E "error|warning|$"

# Count in real-time
tail -f access.log | awk '{count[$1]++; print $1, count[$1]}'

# Monitor rate
tail -f access.log | pv -l -i 1 -r > /dev/null
```

## Tools

### lnav (Log Navigator)

```bash
# Install
sudo apt install lnav

# View logs
lnav /var/log/syslog
lnav /var/log/nginx/*.log

# Features:
# - Automatic format detection
# - Syntax highlighting
# - Filtering
# - SQL queries on logs
```

### GoAccess (Web Log Analyzer)

```bash
# Install
sudo apt install goaccess

# Real-time terminal
goaccess /var/log/nginx/access.log

# Generate HTML report
goaccess /var/log/nginx/access.log -o report.html --real-time-html
```

### jq (JSON Logs)

```bash
# Parse JSON logs
cat log.json | jq '.message'
cat log.json | jq 'select(.level == "error")'
cat log.json | jq -r '[.timestamp, .message] | @tsv'
```
"""
        return ScrapedDocument(
            id=self._generate_id("log-analysis"),
            url="synthetic://log-analysis",
            title="Log Analysis Guide",
            content=content,
            source=self.get_source_name(),
            category="logging",
            tags=["logs", "analysis", "grep", "awk", "linux"],
            scraped_at=datetime.utcnow().isoformat(),
            metadata={"type": "guide", "priority": "high"}
        )
    
    def _centralized_logging_guide(self) -> ScrapedDocument:
        """Centralized logging guide."""
        content = """# Centralized Logging Guide

## Overview

Centralized logging collects logs from multiple servers to a central location.

## rsyslog Remote Logging

### Server (Receiver)

```bash
# /etc/rsyslog.conf

# Load modules
module(load="imudp")
input(type="imudp" port="514")

module(load="imtcp")
input(type="imtcp" port="514")

# Template for organizing by host
template(name="RemoteLogs" type="string"
    string="/var/log/remote/%HOSTNAME%/%PROGRAMNAME%.log")

# Store remote logs
if $fromhost-ip != '127.0.0.1' then ?RemoteLogs
& stop
```

### Client (Sender)

```bash
# /etc/rsyslog.conf

# Forward all logs
*.* @@logserver.example.com:514        # TCP
*.* @logserver.example.com:514         # UDP

# Forward specific logs
auth.* @@logserver.example.com:514
*.err @@logserver.example.com:514

# Queue for reliability
*.* action(type="omfwd"
    target="logserver.example.com"
    port="514"
    protocol="tcp"
    queue.filename="fwdRule1"
    queue.maxdiskspace="1g"
    queue.saveonshutdown="on"
    queue.type="LinkedList"
    action.resumeRetryCount="-1")
```

## systemd-journal-remote

### Server

```bash
# Install
sudo apt install systemd-journal-remote

# Configure
# /etc/systemd/journal-remote.conf
[Remote]
ServerKeyFile=/etc/ssl/private/journal-remote.pem
ServerCertificateFile=/etc/ssl/certs/journal-remote.pem
TrustedCertificateFile=/etc/ssl/ca/trusted.pem

# Enable and start
sudo systemctl enable --now systemd-journal-remote.socket
```

### Client

```bash
# Install
sudo apt install systemd-journal-upload

# Configure
# /etc/systemd/journal-upload.conf
[Upload]
URL=https://logserver.example.com:19532
ServerKeyFile=/etc/ssl/private/key.pem
ServerCertificateFile=/etc/ssl/certs/cert.pem

# Enable
sudo systemctl enable --now systemd-journal-upload
```

## Promtail + Loki (Modern Stack)

### Promtail Client

```yaml
# /etc/promtail/config.yml
server:
  http_listen_port: 9080
  grpc_listen_port: 0

positions:
  filename: /tmp/positions.yaml

clients:
  - url: http://loki:3100/loki/api/v1/push

scrape_configs:
  - job_name: system
    static_configs:
      - targets:
          - localhost
        labels:
          job: varlogs
          host: ${HOSTNAME}
          __path__: /var/log/*log

  - job_name: nginx
    static_configs:
      - targets:
          - localhost
        labels:
          job: nginx
          __path__: /var/log/nginx/*.log
```

## Filebeat + Elasticsearch

### Filebeat

```yaml
# /etc/filebeat/filebeat.yml
filebeat.inputs:
  - type: log
    enabled: true
    paths:
      - /var/log/*.log
      - /var/log/nginx/*.log

output.elasticsearch:
  hosts: ["elasticsearch:9200"]
  
# Or to Logstash
output.logstash:
  hosts: ["logstash:5044"]
```

## Best Practices

1. **Use TCP for reliability** (UDP can drop packets)
2. **Enable queuing** for network failures
3. **Encrypt in transit** (TLS)
4. **Normalize timestamps** (NTP sync)
5. **Set retention policies**
6. **Monitor log volume**
7. **Test failover scenarios**
"""
        return ScrapedDocument(
            id=self._generate_id("centralized-logging"),
            url="synthetic://centralized-logging",
            title="Centralized Logging Guide",
            content=content,
            source=self.get_source_name(),
            category="logging",
            tags=["logging", "centralized", "rsyslog", "remote"],
            scraped_at=datetime.utcnow().isoformat(),
            metadata={"type": "guide", "priority": "medium"}
        )
    
    def _generate_id(self, name: str) -> str:
        """Generate document ID."""
        import hashlib
        return hashlib.md5(f"logging-docs:{name}".encode()).hexdigest()[:16]


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Generate logging documentation")
    parser.add_argument("--output-dir", default="data/linux/logging-docs")
    args = parser.parse_args()
    
    logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(name)s:%(message)s')
    
    config = ScraperConfig(output_dir=Path(args.output_dir))
    scraper = LoggingDocsScraper(config)
    
    docs = scraper.scrape()
    scraper.save_documents(docs, "logging_docs.jsonl")
