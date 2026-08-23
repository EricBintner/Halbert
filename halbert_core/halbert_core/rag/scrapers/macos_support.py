"""
macOS Support/Troubleshooting documentation scraper.

Scrapes macOS troubleshooting and how-to articles from various sources.
Works on any platform.
"""

import logging
import json
from typing import List, Dict, Any, Optional
from datetime import datetime
from pathlib import Path
import hashlib
import re

from .base import BaseScraper, ScrapedDocument, ScraperConfig

logger = logging.getLogger('halbert')


class MacOSSupportScraper(BaseScraper):
    """
    Scrape macOS troubleshooting and support documentation.
    
    Sources:
    - ss64.com/osx (command reference)
    - Various open documentation sources
    """
    
    # SS64 macOS command pages
    SS64_BASE = "https://ss64.com/osx"
    SS64_COMMANDS = [
        # File system
        "cat", "cd", "chmod", "chown", "cp", "df", "du", "find", "ln", "ls",
        "mkdir", "mv", "pwd", "rm", "rmdir", "tar", "touch",
        # Text processing
        "awk", "cut", "diff", "grep", "head", "less", "sed", "sort", "tail",
        "tr", "uniq", "wc",
        # System
        "defaults", "diskutil", "ditto", "env", "export", "hostname", "id",
        "kill", "launchctl", "log", "open", "osascript", "pbcopy", "pbpaste",
        "pmset", "ps", "screencapture", "scutil", "security", "softwareupdate",
        "spctl", "sw_vers", "sysctl", "system_profiler", "tmutil", "top",
        "uname", "who", "whoami",
        # Networking
        "curl", "dig", "dscacheutil", "ftp", "ifconfig", "ipconfig", "netstat",
        "networksetup", "ping", "scp", "sftp", "ssh", "traceroute", "wget",
        # Package/App
        "brew", "caffeinate", "codesign", "csrutil", "hdiutil", "installer",
        "lipo", "mdls", "mdfind", "mdutil", "pkgutil", "plutil", "xattr",
        "xcode-select", "xcrun",
        # User management
        "chpass", "dscl", "groups", "passwd", "sudo", "su",
    ]
    
    def __init__(self, config: ScraperConfig):
        """Initialize macOS support scraper."""
        super().__init__(config)
    
    def get_source_name(self) -> str:
        """Get source name."""
        return "macos-support"
    
    def _rate_limit(self):
        """Rate limit wrapper."""
        self.rate_limit()
    
    def _make_request(self, url: str):
        """Make HTTP request with rate limiting."""
        import requests
        self.rate_limit()
        try:
            response = requests.get(url, timeout=self.config.timeout)
            response.raise_for_status()
            return response
        except Exception:
            return None
    
    def scrape(self) -> List[ScrapedDocument]:
        """
        Scrape macOS support documentation.
        
        Returns:
            List of scraped documents
        """
        documents = []
        
        # 1. Scrape SS64 command reference
        logger.info("Scraping SS64 macOS command reference...")
        documents.extend(self._scrape_ss64_commands())
        
        # 2. Create synthetic docs for common tasks
        logger.info("Generating macOS task documentation...")
        documents.extend(self._generate_task_docs())
        
        logger.info(f"Total macOS support documents: {len(documents)}")
        return documents
    
    def _scrape_ss64_commands(self) -> List[ScrapedDocument]:
        """Scrape SS64 macOS command reference."""
        documents = []
        
        for cmd in self.SS64_COMMANDS:
            url = f"{self.SS64_BASE}/{cmd}.html"
            
            try:
                response = self._make_request(url)
                if response is None:
                    continue
                
                content = self._extract_ss64_content(response.text, cmd)
                
                if content and len(content) > 100:
                    doc_id = f"macos-cmd-{cmd}"
                    
                    documents.append(ScrapedDocument(
                        id=doc_id,
                        url=url,
                        title=f"macOS Command: {cmd}",
                        content=content,
                        source="ss64-macos",
                        category="command_reference",
                        tags=["macos", "command", "terminal", cmd],
                        scraped_at=datetime.utcnow().isoformat(),
                        metadata={
                            "platform": "macos",
                            "command": cmd,
                        }
                    ))
                    logger.debug(f"Scraped command: {cmd}")
                
                self._rate_limit()
                
            except Exception as e:
                logger.warning(f"Failed to scrape {cmd}: {e}")
        
        return documents
    
    def _extract_ss64_content(self, html: str, cmd: str) -> str:
        """Extract content from SS64 page."""
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, 'html.parser')
            
            # Find main content area
            content_div = soup.find('div', id='content') or soup.find('article')
            
            if not content_div:
                # Try body with class
                content_div = soup.find('body')
            
            if content_div:
                # Remove navigation, ads, etc.
                for tag in content_div.find_all(['script', 'style', 'nav', 'header', 'footer']):
                    tag.decompose()
                
                text = content_div.get_text(separator='\n', strip=True)
                
                # Clean up
                text = re.sub(r'\n{3,}', '\n\n', text)
                
                return f"# {cmd}\n\n{text}"
            
            return ""
        except Exception as e:
            logger.debug(f"Failed to extract content for {cmd}: {e}")
            return ""
    
    def _generate_task_docs(self) -> List[ScrapedDocument]:
        """Generate documentation for common macOS tasks."""
        documents = []
        
        # Common macOS administration tasks
        tasks = [
            {
                "title": "Managing macOS Services with launchd",
                "content": self._launchd_guide(),
                "tags": ["launchd", "services", "daemons"],
                "category": "service_management",
            },
            {
                "title": "Homebrew Package Management",
                "content": self._homebrew_guide(),
                "tags": ["homebrew", "packages", "installation"],
                "category": "package_management",
            },
            {
                "title": "macOS Disk Management with diskutil",
                "content": self._diskutil_guide(),
                "tags": ["diskutil", "apfs", "disk", "storage"],
                "category": "storage",
            },
            {
                "title": "macOS Network Configuration",
                "content": self._network_guide(),
                "tags": ["network", "wifi", "dns", "networksetup"],
                "category": "networking",
            },
            {
                "title": "Time Machine Backup Management",
                "content": self._timemachine_guide(),
                "tags": ["timemachine", "backup", "tmutil"],
                "category": "backup",
            },
            {
                "title": "macOS Security: Gatekeeper and SIP",
                "content": self._security_guide(),
                "tags": ["security", "gatekeeper", "sip", "codesign"],
                "category": "security",
            },
            {
                "title": "Reading macOS Logs with Unified Logging",
                "content": self._logging_guide(),
                "tags": ["logs", "unified-logging", "log", "console"],
                "category": "logging",
            },
            {
                "title": "macOS Power Management with pmset",
                "content": self._power_guide(),
                "tags": ["power", "battery", "sleep", "pmset"],
                "category": "power_management",
            },
            {
                "title": "APFS (Apple File System) Guide",
                "content": self._apfs_guide(),
                "tags": ["apfs", "filesystem", "storage", "snapshots"],
                "category": "storage",
            },
            {
                "title": "Apple Silicon and Rosetta 2",
                "content": self._apple_silicon_guide(),
                "tags": ["apple-silicon", "rosetta", "arm", "unified-memory"],
                "category": "hardware",
            },
            {
                "title": "macOS Notarization and Code Distribution",
                "content": self._notarization_guide(),
                "tags": ["notarization", "codesign", "xcrun", "distribution"],
                "category": "security",
            },
            {
                "title": "macOS Mobile Device Management (MDM)",
                "content": self._mdm_guide(),
                "tags": ["mdm", "configuration-profiles", "mobileconfig", "enterprise"],
                "category": "enterprise",
            },
            {
                "title": "macOS Recovery and Reinstall",
                "content": self._recovery_guide(),
                "tags": ["recovery", "reinstall", "internet-recovery", "startup"],
                "category": "recovery",
            },
            {
                "title": "macOS User and Group Management",
                "content": self._user_management_guide(),
                "tags": ["users", "groups", "dscl", "directory"],
                "category": "system_admin",
            },
            {
                "title": "macOS Software Update Management",
                "content": self._software_update_guide(),
                "tags": ["softwareupdate", "updates", "macos-update"],
                "category": "system_admin",
            },
            {
                "title": "macOS Spotlight Search and Metadata",
                "content": self._spotlight_guide(),
                "tags": ["spotlight", "mdfind", "mdls", "metadata", "search"],
                "category": "system_admin",
            },
            {
                "title": "macOS System Diagnostics",
                "content": self._diagnostics_guide(),
                "tags": ["sysdiagnose", "system_profiler", "diagnostics", "troubleshooting"],
                "category": "diagnostics",
            },
        ]
        
        for task in tasks:
            doc_id = f"macos-guide-{hashlib.md5(task['title'].encode()).hexdigest()[:12]}"
            
            documents.append(ScrapedDocument(
                id=doc_id,
                url=f"synthetic://halbert/macos/{doc_id}",
                title=task["title"],
                content=task["content"],
                source="halbert-macos-guides",
                category=task["category"],
                tags=["macos", "guide"] + task["tags"],
                scraped_at=datetime.utcnow().isoformat(),
                metadata={
                    "platform": "macos",
                    "doc_type": "guide",
                    "synthetic": True,
                }
            ))
        
        return documents
    
    def _launchd_guide(self) -> str:
        return """# Managing macOS Services with launchd

launchd is the macOS service manager, equivalent to systemd on Linux.

## Key Concepts

- **LaunchDaemons**: System-wide services in `/Library/LaunchDaemons/`
- **LaunchAgents**: Per-user services in `~/Library/LaunchAgents/`
- **Plist files**: XML configuration files defining services

## Common Commands

### List all services
```bash
launchctl list
```

### Check service status
```bash
launchctl list | grep servicename
```

### Load a service
```bash
launchctl load /Library/LaunchDaemons/com.example.service.plist
```

### Unload a service
```bash
launchctl unload /Library/LaunchDaemons/com.example.service.plist
```

### Start/Stop a service
```bash
launchctl start com.example.service
launchctl stop com.example.service
```

### Enable service at boot
```bash
launchctl enable system/com.example.service
```

### Disable service
```bash
launchctl disable system/com.example.service
```

## Example Plist File

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.example.myservice</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/local/bin/myservice</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
</dict>
</plist>
```

## Troubleshooting

### Service won't start
1. Check plist syntax: `plutil -lint /path/to/service.plist`
2. Check logs: `log show --predicate 'subsystem == "com.apple.launchd"' --last 5m`
3. Verify permissions: plist should be owned by root:wheel with 644 permissions

### Finding service logs
```bash
log show --predicate 'process == "myservice"' --last 1h
```
"""

    def _homebrew_guide(self) -> str:
        return """# Homebrew Package Management

Homebrew is the de facto package manager for macOS.

## Installation

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

## Basic Commands

### Update Homebrew
```bash
brew update
```

### Search for packages
```bash
brew search package_name
```

### Install a package
```bash
brew install package_name
```

### Install a GUI application (cask)
```bash
brew install --cask application_name
```

### Upgrade packages
```bash
brew upgrade              # Upgrade all
brew upgrade package_name # Upgrade specific
```

### List installed packages
```bash
brew list
brew list --cask  # GUI apps only
```

### Show package info
```bash
brew info package_name
```

### Uninstall a package
```bash
brew uninstall package_name
```

## Maintenance

### Check for issues
```bash
brew doctor
```

### Clean up old versions
```bash
brew cleanup
brew cleanup -n  # Dry run first
```

### List outdated packages
```bash
brew outdated
```

## Services (via brew services)

```bash
brew services list
brew services start service_name
brew services stop service_name
brew services restart service_name
```

## Troubleshooting

### Permission issues
```bash
sudo chown -R $(whoami) /usr/local/Homebrew
sudo chown -R $(whoami) /usr/local/var/homebrew
```

### Reset Homebrew
```bash
cd /usr/local/Homebrew && git fetch && git reset --hard origin/master
brew update-reset
```
"""

    def _diskutil_guide(self) -> str:
        return """# macOS Disk Management with diskutil

diskutil is the command-line interface for Disk Utility.

## List Disks

```bash
diskutil list                    # All disks
diskutil list internal           # Internal only
diskutil list external physical  # External only
```

## Disk Information

```bash
diskutil info disk0              # Physical disk
diskutil info disk0s1            # Partition
diskutil info /                  # Mount point
```

## APFS Operations

### List APFS containers
```bash
diskutil apfs list
```

### Add APFS volume
```bash
diskutil apfs addVolume disk1 APFS "NewVolume"
```

### Delete APFS volume
```bash
diskutil apfs deleteVolume disk1s3
```

### Resize APFS container
```bash
diskutil apfs resizeContainer disk1 500g
```

## Mount/Unmount

```bash
diskutil mount disk2s1
diskutil unmount disk2s1
diskutil unmountDisk disk2       # Unmount all volumes
```

## Eject

```bash
diskutil eject disk2
```

## Erase Disk

```bash
# Erase and format as APFS
diskutil eraseDisk APFS "DiskName" disk2

# Erase and format as Mac OS Extended
diskutil eraseDisk JHFS+ "DiskName" disk2

# Erase partition only
diskutil eraseVolume APFS "VolumeName" disk2s1
```

## Verify and Repair

```bash
diskutil verifyDisk disk0
diskutil verifyVolume disk0s1
diskutil repairVolume disk0s1
```

## First Aid (equivalent to Disk Utility First Aid)

```bash
diskutil repairDisk disk0
```

## RAID Operations

```bash
diskutil listRAID
diskutil createRAID stripe|mirror "RAIDName" JHFS+ disk1 disk2
diskutil destroyRAID disk3
```
"""

    def _network_guide(self) -> str:
        return """# macOS Network Configuration

## networksetup Commands

### List network services
```bash
networksetup -listallnetworkservices
```

### List hardware ports
```bash
networksetup -listallhardwareports
```

### Get current network info
```bash
networksetup -getinfo "Wi-Fi"
```

### Set DHCP
```bash
networksetup -setdhcp "Wi-Fi"
```

### Set static IP
```bash
networksetup -setmanual "Wi-Fi" 192.168.1.100 255.255.255.0 192.168.1.1
```

### Get/Set DNS servers
```bash
networksetup -getdnsservers "Wi-Fi"
networksetup -setdnsservers "Wi-Fi" 8.8.8.8 8.8.4.4
```

### Turn Wi-Fi on/off
```bash
networksetup -setairportpower en0 on
networksetup -setairportpower en0 off
```

## Wi-Fi Commands

### Get current Wi-Fi network
```bash
/System/Library/PrivateFrameworks/Apple80211.framework/Versions/Current/Resources/airport -I
```

### Scan for networks
```bash
/System/Library/PrivateFrameworks/Apple80211.framework/Versions/Current/Resources/airport -s
```

### Join network
```bash
networksetup -setairportnetwork en0 "NetworkName" "password"
```

## DNS Cache

### Flush DNS cache
```bash
sudo dscacheutil -flushcache
sudo killall -HUP mDNSResponder
```

## Checking Connectivity

```bash
ping -c 3 8.8.8.8           # Test internet
ping -c 3 google.com        # Test DNS
traceroute google.com       # Trace route
```

## Active Connections

```bash
netstat -an | grep ESTABLISHED
lsof -i -P | grep LISTEN    # Listening ports
```
"""

    def _timemachine_guide(self) -> str:
        return """# Time Machine Backup Management

## tmutil Commands

### Check Time Machine status
```bash
tmutil status
```

### List backup destinations
```bash
tmutil destinationinfo
```

### Get latest backup
```bash
tmutil latestbackup
```

### List all backups
```bash
tmutil listbackups
```

### Start a backup now
```bash
tmutil startbackup
tmutil startbackup --block  # Wait for completion
```

### Stop current backup
```bash
tmutil stopbackup
```

### Enable/Disable Time Machine
```bash
sudo tmutil enable
sudo tmutil disable
```

### Add backup destination
```bash
sudo tmutil setdestination /Volumes/BackupDrive
```

### Exclude paths from backup
```bash
sudo tmutil addexclusion /path/to/exclude
tmutil isexcluded /path/to/check
```

### Remove exclusion
```bash
sudo tmutil removeexclusion /path
```

### Delete old backups
```bash
sudo tmutil delete /Volumes/BackupDrive/Backups.backupdb/MacName/2024-01-01-120000
```

### Compare backups
```bash
tmutil compare /path/to/backup1 /path/to/backup2
```

## Restoring Files

### Restore via Finder
Enter Time Machine by clicking the icon in menu bar.

### Restore via tmutil
```bash
tmutil restore /path/to/backup/file /path/to/destination
```

## Troubleshooting

### Check backup integrity
```bash
tmutil verifychecksums /Volumes/BackupDrive/Backups.backupdb
```

### Reset Time Machine
```bash
sudo tmutil disable
rm -rf /Volumes/BackupDrive/Backups.backupdb
sudo tmutil enable
```
"""

    def _security_guide(self) -> str:
        return """# macOS Security: Gatekeeper and SIP

## System Integrity Protection (SIP)

### Check SIP status
```bash
csrutil status
```

### Disable SIP (requires Recovery Mode)
1. Restart and hold Cmd+R
2. Open Terminal from Utilities menu
3. Run: `csrutil disable`
4. Restart

### Enable SIP (requires Recovery Mode)
```bash
csrutil enable
```

## Gatekeeper

### Check Gatekeeper status
```bash
spctl --status
```

### Enable/Disable Gatekeeper
```bash
sudo spctl --master-enable
sudo spctl --master-disable
```

### Allow specific app
```bash
sudo spctl --add /Applications/SomeApp.app
```

### Check if app is allowed
```bash
spctl --assess -v /Applications/SomeApp.app
```

## Code Signing

### Check app signature
```bash
codesign -dv --verbose=4 /Applications/SomeApp.app
```

### Verify signature
```bash
codesign --verify --verbose /Applications/SomeApp.app
```

### Remove quarantine attribute
```bash
xattr -d com.apple.quarantine /Applications/SomeApp.app
```

## Keychain

### List keychains
```bash
security list-keychains
```

### Find password in keychain
```bash
security find-generic-password -s "service-name" -w
```

### Add password to keychain
```bash
security add-generic-password -a "account" -s "service" -w "password"
```

## FileVault

### Check FileVault status
```bash
fdesetup status
```

### Enable FileVault
```bash
sudo fdesetup enable
```

### List FileVault users
```bash
sudo fdesetup list
```

## Privacy (TCC)

### Reset privacy permissions
```bash
tccutil reset All  # Reset all
tccutil reset Camera  # Reset camera only
```

## Firewall

### Check firewall status
```bash
/usr/libexec/ApplicationFirewall/socketfilterfw --getglobalstate
```

### Enable/Disable firewall
```bash
sudo /usr/libexec/ApplicationFirewall/socketfilterfw --setglobalstate on
sudo /usr/libexec/ApplicationFirewall/socketfilterfw --setglobalstate off
```
"""

    def _logging_guide(self) -> str:
        return """# Reading macOS Logs with Unified Logging

macOS uses Unified Logging instead of traditional syslog.

## log Command

### Show recent logs
```bash
log show --last 5m           # Last 5 minutes
log show --last 1h           # Last hour
log show --last 1d           # Last day
```

### Stream live logs
```bash
log stream
log stream --level debug     # Include debug messages
```

### Filter by process
```bash
log show --predicate 'process == "Safari"' --last 1h
```

### Filter by subsystem
```bash
log show --predicate 'subsystem == "com.apple.wifi"' --last 1h
```

### Filter by message content
```bash
log show --predicate 'eventMessage contains "error"' --last 1h
```

### Combine filters
```bash
log show --predicate 'process == "kernel" AND eventMessage contains "USB"' --last 1h
```

### Filter by log level
```bash
log show --predicate 'messageType == error' --last 1h
log show --predicate 'messageType == fault' --last 1h
```

### Show specific category
```bash
log show --predicate 'category == "security"' --last 1h
```

## Output Formats

### JSON output
```bash
log show --last 5m --style json
```

### Compact output
```bash
log show --last 5m --style compact
```

### Include debug info
```bash
log show --last 5m --info --debug
```

## Common Filters

### Kernel messages
```bash
log show --predicate 'process == "kernel"' --last 1h
```

### Network issues
```bash
log show --predicate 'subsystem contains "network"' --last 1h
```

### App crashes
```bash
log show --predicate 'process == "ReportCrash"' --last 1h
```

### Disk issues
```bash
log show --predicate 'subsystem == "com.apple.diskmanagement"' --last 1h
```

### Authentication
```bash
log show --predicate 'subsystem == "com.apple.Authorization"' --last 1h
```

## Console.app

For GUI-based log viewing, use Console.app:
- Open from /Applications/Utilities/Console.app
- Supports searching, filtering, and streaming
"""

    def _power_guide(self) -> str:
        return """# macOS Power Management with pmset

## Check Current Settings

```bash
pmset -g                     # Current settings
pmset -g batt                # Battery info
pmset -g ps                  # Power source
pmset -g assertions          # Power assertions
pmset -g sched               # Scheduled events
```

## Power Settings

### Sleep settings
```bash
sudo pmset -a sleep 30       # Sleep after 30 min (all power sources)
sudo pmset -b sleep 10       # Sleep after 10 min (battery)
sudo pmset -c sleep 0        # Never sleep (charger)
```

### Display sleep
```bash
sudo pmset -a displaysleep 15
```

### Disk sleep
```bash
sudo pmset -a disksleep 10
```

### Wake on network access
```bash
sudo pmset -a womp 1         # Enable
sudo pmset -a womp 0         # Disable
```

### Power nap
```bash
sudo pmset -a powernap 1     # Enable
sudo pmset -a powernap 0     # Disable
```

### Auto restart after power failure
```bash
sudo pmset -a autorestart 1
```

## Prevent Sleep

### Prevent sleep temporarily
```bash
caffeinate -d               # Prevent display sleep
caffeinate -i               # Prevent idle sleep
caffeinate -s               # Prevent system sleep
caffeinate -u -t 3600       # Prevent sleep for 1 hour
```

### Run command without sleeping
```bash
caffeinate -i long_running_command
```

## Scheduled Events

### Schedule shutdown
```bash
sudo pmset schedule shutdown "12/25/2024 23:00:00"
```

### Schedule startup
```bash
sudo pmset schedule wake "12/26/2024 08:00:00"
```

### Cancel scheduled events
```bash
sudo pmset schedule cancelall
```

## Battery Health

### Check cycle count
```bash
system_profiler SPPowerDataType | grep "Cycle Count"
```

### Battery health status
```bash
system_profiler SPPowerDataType | grep -A 5 "Health Information"
```

## Restore Defaults

```bash
sudo pmset -a restoredefaults
```
"""

    def _apfs_guide(self) -> str:
        return """# APFS (Apple File System) Guide

APFS is the default file system for macOS since High Sierra (10.13).
It is optimized for SSD storage and supports snapshots, cloning, and encryption.

## Key Features

- **Snapshots**: Point-in-time read-only copies of the filesystem
- **Cloning**: Instant file copies (copy-on-write)
- **Space Sharing**: Multiple volumes share the same container
- **Encryption**: Per-volume encryption with FileVault
- **Crash Protection**: Copy-on-write ensures filesystem consistency

## Container and Volume Management

### List APFS containers
```bash
diskutil apfs list
```

### List specific container
```bash
diskutil apfs listContainer disk1
```

### Create APFS container
```bash
diskutil apfs createContainer disk0s2
```

### Add APFS volume to container
```bash
diskutil apfs addVolume disk1 APFS "MyVolume"
diskutil apfs addVolume disk1 APFS "Data" -mountpoint /Volumes/Data
```

### Delete APFS volume
```bash
diskutil apfs deleteVolume disk1s3
```

### Resize APFS container
```bash
diskutil apfs resizeContainer disk1 500g
```

### Sync APFS container
```bash
diskutil apfs syncContainer disk1
```

## APFS Snapshots

### List snapshots
```bash
tmutil listlocalsnapshots /
```

### Create a local snapshot
```bash
tmutil localsnapshot
```

### Delete a local snapshot
```bash
tmutil deletelocalsnapshots <snapshot-date>
```

### Mount a snapshot (read-only)
```bash
# Snapshots are mounted automatically under /.DocumentRevisions-V100/
# Or via Time Machine interface
```

## FileVault with APFS

### Check FileVault status
```bash
fdesetup status
```

### Enable FileVault
```bash
sudo fdesetup enable
```

### Enable with institutional recovery key
```bash
sudo fdesetup enable -institutional -keychain /path/to/keychain
```

## APFS Encryption Status

### Check encryption progress
```bash
diskutil apfs list
# Look for "FileVault" and "Encryption" fields
```

### Decrypt APFS volume
```bash
sudo fdesetup disable
```

## APFS and Time Machine

Time Machine uses APFS local snapshots for local backups:
- Snapshots are created automatically every hour
- Stored in the APFS container
- Can consume significant disk space
- Old snapshots are pruned automatically

### Manage Time Machine snapshots
```bash
tmutil listlocalsnapshots /
tmutil deletelocalsnapshots 2024-01-15-100000
```

## Troubleshooting APFS

### Check APFS object map
```bash
diskutil apfs verifyObjectMap disk1s1
```

### Repair APFS volume
```bash
diskutil apfs repairVolume disk1s1
```

### Force unmount APFS volume
```bash
diskutil apfs forceUnmount disk1s1
```

### APFS container out of space
If container is full but volumes show free space:
```bash
# Check for orphaned snapshots
tmutil listlocalsnapshots /
# Delete old snapshots
tmutil deletelocalsnapshots <date>
# Resize container if physical space allows
diskutil apfs resizeContainer disk1 0
```
"""

    def _apple_silicon_guide(self) -> str:
        return """# Apple Silicon and Rosetta 2

Apple Silicon (M1, M2, M3, M4) is Apple's ARM-based chip architecture
replacing Intel x86 in Macs. It uses unified memory architecture (UMA).

## Architecture Overview

- **ARM64 (AArch64)**: Native instruction set
- **Unified Memory**: CPU and GPU share the same memory pool
- **Neural Engine (NPU)**: Dedicated AI/ML accelerator
- **Secure Enclave**: Hardware security module
- **Media Engine**: Hardware video encode/decode

## Checking Apple Silicon

### Check chip type
```bash
sysctl -n machdep.cpu.brand_string
# Apple Silicon: "Apple M2 Pro" etc.
# Intel: "Intel(R) Core(TM) i7..." etc.
```

### Check architecture
```bash
uname -m
# arm64 = Apple Silicon
# x86_64 = Intel
```

### Detailed hardware info
```bash
system_profiler SPHardwareDataType
```

## Rosetta 2

Rosetta 2 is Apple's translation layer that runs Intel (x86_64) binaries
on Apple Silicon. It translates code at install time for most apps.

### Install Rosetta 2
```bash
softwareupdate --install-rosetta
# Or agree to license:
softwareupdate --install-rosetta --agree-to-license
```

### Check if Rosetta is installed
```bash
arch -arch x86_64 /usr/bin/true 2>/dev/null && echo "Rosetta available" || echo "Rosetta not installed"
```

### Run Intel binary explicitly
```bash
arch -x86_64 <command>
```

### Run ARM binary explicitly
```bash
arch -arm64 <command>
```

### Check binary architecture
```bash
file /path/to/binary
# "Mach-O 64-bit executable arm64" = Apple Silicon native
# "Mach-O 64-bit executable x86_64" = Intel
# "Mach-O universal binary" = Both architectures
```

### List architectures in universal binary
```bash
lipo -info /path/to/binary
lipo -archs /path/to/binary
```

### Extract specific architecture
```bash
lipo -extract arm64 /path/to/binary -output /path/to/arm64_binary
```

## Homebrew on Apple Silicon

Homebrew installs to different paths on Apple Silicon:
- **Apple Silicon**: `/opt/homebrew`
- **Intel**: `/usr/local`

### Check Homebrew prefix
```bash
brew --prefix
```

### Install ARM-native formula
```bash
arch -arm64 brew install <formula>
```

### Install Intel formula via Rosetta
```bash
arch -x86_64 brew install <formula>
```

## Unified Memory Architecture

On Apple Silicon, CPU and GPU share the same memory:
- No data copy needed between CPU and GPU
- Total system memory is shared
- More efficient for ML/GPU workloads

### Check memory
```bash
sysctl -n hw.memsize
# Convert to GB: divide by 1073741824
```

### Check GPU memory (shared)
```bash
system_profiler SPDisplaysDataType
```

## Performance Considerations

- Native ARM64 binaries are significantly faster than Rosetta-translated ones
- Rosetta 2 has some overhead (~20-30% for compute-heavy tasks)
- Some Intel-only apps may not work under Rosetta (kernel extensions, virtualization)
- Docker uses a lightweight VM on Apple Silicon
- x86_64 Docker images run via emulation (slow); use ARM images when possible

## Virtualization on Apple Silicon

- Virtualization Framework supports ARM VMs natively
- UTM, Parallels, VMware Fusion support ARM Linux/Windows
- Intel OS virtualization requires emulation (very slow)
- Docker runs in a lightweight ARM Linux VM
"""

    def _notarization_guide(self) -> str:
        return """# macOS Notarization and Code Distribution

Notarization is Apple's security process that verifies software is free from
malware before distribution. Required for Gatekeeper to allow execution.

## Prerequisites

- Apple Developer account
- App-specific password for notarytool
- Developer ID Application certificate

### Create app-specific password
1. Go to https://appleid.apple.com
2. Sign in > App-Specific Passwords > Generate
3. Save the password for notarytool

### Store credentials for notarytool
```bash
xcrun notarytool store-credentials "AC_PASSWORD" \
  --apple-id "you@example.com" \
  --team-id "TEAM123456" \
  --password "app-specific-password"
```

## Code Signing

### Sign an application
```bash
codesign --deep --force --verify --verbose=4 \
  --sign "Developer ID Application: Your Name (TEAM123456)" \
  /path/to/YourApp.app
```

### Sign with options
```bash
codesign --deep --force --options runtime \
  --sign "Developer ID Application: Your Name (TEAM123456)" \
  --entitlements entitlements.plist \
  /path/to/YourApp.app
```

### Verify code signature
```bash
codesign --verify --verbose=4 /path/to/YourApp.app
codesign -dv --verbose=4 /path/to/YourApp.app
```

### Check entitlements
```bash
codesign -d --entitlements - /path/to/YourApp.app
```

## Notarization Process

### Submit for notarization
```bash
# Zip the app first
ditto -c -k --keepParent /path/to/YourApp.app /path/to/YourApp.zip

# Submit
xcrun notarytool submit /path/to/YourApp.zip \
  --keychain-profile "AC_PASSWORD" \
  --wait
```

### Check notarization status
```bash
xcrun notarytool info <submission-id> --keychain-profile "AC_PASSWORD"
```

### Get notarization log
```bash
xcrun notarytool log <submission-id> --keychain-profile "AC_PASSWORD"
```

### Staple the notarization ticket
```bash
xcrun stapler staple /path/to/YourApp.app
xcrun stapler validate /path/to/YourApp.app
```

## Full Distribution Workflow

```bash
# 1. Build your app
xcodebuild -project YourApp.xcodeproj -scheme YourApp -configuration Release

# 2. Code sign
codesign --deep --force --options runtime \
  --sign "Developer ID Application: Your Name (TEAM123456)" \
  /path/to/YourApp.app

# 3. Create zip
ditto -c -k --keepParent /path/to/YourApp.app YourApp.zip

# 4. Submit for notarization
xcrun notarytool submit YourApp.zip --keychain-profile "AC_PASSWORD" --wait

# 5. Staple ticket
xcrun stapler staple /path/to/YourApp.app

# 6. Verify
xcrun stapler validate /path/to/YourApp.app
spctl --assess --verbose=4 /path/to/YourApp.app
```

## Creating an Installer Package

### Build a pkg
```bash
pkgbuild --component /path/to/YourApp.app \
  --install-location /Applications \
  --sign "Developer ID Installer: Your Name (TEAM123456)" \
  YourApp.pkg
```

### Notarize a pkg
```bash
xcrun notarytool submit YourApp.pkg --keychain-profile "AC_PASSWORD" --wait
xcrun stapler staple YourApp.pkg
```

## Troubleshooting Notarization

### Common rejection reasons
- Unsigned binaries or libraries
- Missing hardened runtime (--options runtime)
- Embedded libraries not signed
- Using deprecated APIs
- Including executable stack

### Check bundle for unsigned binaries
```bash
find /path/to/YourApp.app -type f -exec sh -c 'file "$1" | grep -q "Mach-O" && codesign -dv "$1" 2>&1 | grep -q "not signed" && echo "UNSIGNED: $1"' _ {} \;
```
"""

    def _mdm_guide(self) -> str:
        return """# macOS Mobile Device Management (MDM)

MDM allows centralized management of macOS devices in enterprise environments.
Uses configuration profiles (.mobileconfig) to enforce settings.

## Configuration Profiles

### Profile structure
Configuration profiles are XML plist files with `.mobileconfig` extension:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>PayloadContent</key>
    <array>
        <!-- Payload dictionaries -->
    </array>
    <key>PayloadDisplayName</key>
    <string>WiFi Configuration</string>
    <key>PayloadIdentifier</key>
    <string>com.example.wifi</string>
    <key>PayloadType</key>
    <string>Configuration</string>
    <key>PayloadUUID</key>
    <string>A1B2C3D4-E5F6-7890-ABCD-EF1234567890</string>
    <key>PayloadVersion</key>
    <integer>1</integer>
</dict>
</plist>
```

### Install a profile (command line)
```bash
profiles install -path /path/to/profile.mobileconfig
```

### List installed profiles
```bash
profiles list
profiles show -type configuration
```

### Remove a profile
```bash
profiles remove -identifier com.example.wifi
```

### Remove all profiles
```bash
profiles remove -all -forced
```

## Common MDM Payloads

### WiFi Configuration
- SSID, security type, password
- 802.1X enterprise settings
- Hidden networks

### Restrictions
- Disable camera, FaceTime
- Prevent app installation/removal
- Enforce passcode policy
- Disable USB storage

### Email Configuration
- Exchange/IMAP/POP settings
- S/MIME certificates

### VPN Configuration
- IKEv2, L2TP, Cisco IPSec
- Always-on VPN
- Per-app VPN

### Security
- FileVault enable/escrow
- Firewall settings
- Gatekeeper settings

## Managed Preferences (ManagedSettings)

MDM can enforce user preferences via managed preferences:
- Settings appear in System Settings with "managed by organization" badge
- Users cannot change managed settings
- Applied at the domain level (e.g., com.apple.finder)

### Example: Disable external volumes in Finder
```xml
<dict>
    <key>PayloadType</key>
    <string>com.apple.ManagedClient.preferences</string>
    <key>PayloadContent</key>
    <dict>
        <key>com.apple.finder</key>
        <dict>
            <key>Forced</key>
            <array>
                <dict>
                    <key>mcx_preference_settings</key>
                    <dict>
                        <key>ProhibitBurn</key>
                        <true/>
                        <key>ShowExternalHardDrivesOnDesktop</key>
                        <false/>
                    </dict>
                </dict>
            </array>
        </dict>
    </dict>
</dict>
```

## MDM Enrollment

### Automated Device Enrollment (DEP)
- Devices enrolled automatically when activated
- Requires Apple Business/School Manager
- Supervision is enforced
- Cannot be removed by user

### Manual Enrollment
- User installs enrollment profile
- Device becomes supervised
- Can be unenrolled by user (unless DEP)

### Check supervision status
```bash
profiles status -type enrollment
```

## Useful MDM Commands

### Check MDM enrollment
```bash
profiles status -type enrollment
```

### Renew MDM enrollment
```bash
profiles renew -type enrollment
```

### Show MDM profile details
```bash
profiles show -type enrollment
```

## Popular MDM Solutions

- **Jamf Pro**: Enterprise-focused, most popular for Mac
- **Microsoft Intune**: Integrated with Microsoft 365
- **VMware Workspace ONE**: Cross-platform
- **Kandji**: Modern Mac-focused MDM
- **Mosyle**: Education and business
- **SimpleMDM**: Lightweight, easy to use
"""

    def _recovery_guide(self) -> str:
        return """# macOS Recovery and Reinstall

macOS Recovery provides tools to repair, restore, and reinstall macOS.

## Entering Recovery Mode

### Apple Silicon
1. Shut down the Mac
2. Press and hold the power button
3. Keep holding until "Loading startup options" appears
4. Click "Options" > Continue

### Intel Macs
1. Restart the Mac
2. Immediately press and hold Cmd + R
3. Release when the Apple logo appears

### Internet Recovery (Intel)
- Cmd + Option + R: Latest compatible macOS
- Shift + Cmd + Option + R: Original macOS that shipped with Mac

## Recovery Tools

### Disk Utility
- Repair disks with First Aid
- Erase and reformat disks
- Restore from disk images

### Reinstall macOS
- Downloads and installs the current macOS version
- Preserves user data (if disk is healthy)

### Terminal (from Recovery)
Available commands in Recovery Terminal:
```bash
# Mount the main volume
diskutil apfs list
diskutil mount /dev/disk1s1

# Reset user password
resetpassword

# Check system integrity
csrutil status

# Disable SIP (for troubleshooting)
csrutil disable

# Re-enable SIP
csrutil enable

# Start from a specific volume
bless --mount /Volumes/Macintosh\ HD --setBoot
```

## Reinstall macOS

### From Recovery
1. Boot into Recovery Mode
2. Select "Reinstall macOS"
3. Follow the installer prompts
4. macOS will download and install

### From Terminal (createinstallmedia)
```bash
# Download macOS installer from App Store first
# Then create a bootable installer:
sudo /Applications/Install\ macOS\ Sonoma.app/Contents/Resources/createinstallmedia \
  --volume /Volumes/MyVolume
```

### Boot from installer USB
- Apple Silicon: Hold power button > select USB drive
- Intel: Hold Option key at startup > select USB drive

## Reset NVRAM/PRAM

### Intel Macs
1. Shut down
2. Press power, immediately hold Cmd + Option + P + R
3. Hold for 20 seconds (or until second startup chime)

### Apple Silicon
NVRAM resets automatically during a full shutdown:
1. Apple menu > Shut Down
2. Wait 10 seconds
3. Press power button

## Reset SMC (Intel only)

### MacBook with T2 chip
1. Shut down
2. Hold Ctrl + Option + Shift + power button for 7 seconds
3. Release, wait 5 seconds, press power button

### MacBook without T2
1. Shut down
2. Hold Shift + Ctrl + Option + power button for 10 seconds
3. Release, press power button

## Safe Mode

### Boot into Safe Mode (Apple Silicon)
1. Shut down
2. Hold power button until startup options
3. Select startup disk, hold Shift
4. Click "Continue in Safe Mode"

### Boot into Safe Mode (Intel)
1. Restart
2. Hold Shift key immediately
3. Release when login window appears

### Safe Mode effects
- Disables third-party kernel extensions
- Clears font caches
- Disables startup items
- Forces directory check

## DFU Mode (Device Firmware Update)

Used for restoring Apple Silicon Macs with Apple Configurator:
1. Connect two Macs via USB-C/Thunderbolt
2. On target Mac: hold power, press left Ctrl, left Option, right Shift for 7 seconds
3. Continue holding power for 10 more seconds
4. Use Apple Configurator on the other Mac to Restore
"""

    def _user_management_guide(self) -> str:
        return """# macOS User and Group Management

macOS uses Directory Service (dscl) for user and group management.
Users and groups are stored in the local directory node.

## User Management

### List all users
```bash
dscl . list /Users UniqueID
```

### List users with home directories
```bash
dscl . list /Users NFSHomeDirectory
```

### Get user details
```bash
dscl . read /Users/username
```

### Create a new user
```bash
# Create user
sudo dscl . create /Users/newuser

# Set shell
sudo dscl . create /Users/newuser UserShell /bin/bash

# Set full name
sudo dscl . create /Users/newuser RealName "New User"

# Set UniqueID (find next available)
sudo dscl . create /Users/newuser UniqueID 501

# Set primary group ID (20 = staff)
sudo dscl . create /Users/newuser PrimaryGroupID 20

# Set home directory
sudo dscl . create /Users/newuser NFSHomeDirectory /Users/newuser

# Create home directory
sudo createhomedir -c -u newuser
```

### Set user password
```bash
# Interactive
sudo dscl . passwd /Users/newuser

# Non-interactive (less secure)
sudo dscl . passwd /Users/newuser newpassword
```

### Delete a user
```bash
sudo dscl . delete /Users/username
sudo rm -rf /Users/username
```

### Modify user properties
```bash
# Change shell
sudo dscl . create /Users/username UserShell /bin/zsh

# Change full name
sudo dscl . create /Users/username RealName "New Name"

# Disable login
sudo dscl . create /Users/username UserShell /usr/bin/false
```

## Group Management

### List all groups
```bash
dscl . list /Groups PrimaryGroupID
```

### Get group details
```bash
dscl . read /Groups/groupname
```

### Create a new group
```bash
sudo dscl . create /Groups/newgroup
sudo dscl . create /Groups/newgroup RealName "New Group"
sudo dscl . create /Groups/newgroup PrimaryGroupID 1000
```

### Add user to group
```bash
sudo dscl . append /Groups/groupname GroupMembership username
```

### Remove user from group
```bash
sudo dscl . delete /Groups/groupname GroupMembership username
```

### List group members
```bash
dscl . read /Groups/groupname GroupMembership
```

## Standard macOS Groups

| Group | GID | Description |
|-------|-----|-------------|
| admin | 80 | Administrators |
| staff | 20 | All users |
| wheel | 0 | System operators |
| daemon | 1 | System daemons |
| _lp | 26 | Print operators |
| _developer | 206 | Developer tools |

## Check User/Group Membership

### Check current user's groups
```bash
groups
id
```

### Check if user is admin
```bash
groups username | grep -w admin
```

### Check user's UID
```bash
id -u username
```

## Guest User Management

### Enable guest user
```bash
sudo defaults write /Library/Preferences/com.apple.loginwindow GuestEnabled -bool true
```

### Disable guest user
```bash
sudo defaults write /Library/Preferences/com.apple.loginwindow GuestEnabled -bool false
```

## Login Window Settings

### Show full names in login window
```bash
sudo defaults write /Library/Preferences/com.apple.loginwindow SHOWFULLNAME -bool true
```

### Hide restart/shutdown buttons
```bash
sudo defaults write /Library/Preferences/com.apple.loginwindow HIDESHUTDOWNTIMER -bool true
```
"""

    def _software_update_guide(self) -> str:
        return """# macOS Software Update Management

macOS software updates can be managed via the `softwareupdate` command line tool.

## Check for Updates

### List available updates
```bash
softwareupdate --list
```

### List with full details
```bash
softwareupdate --list --verbose
```

## Install Updates

### Install all available updates
```bash
sudo softwareupdate --install --all
```

### Install specific update
```bash
sudo softwareupdate --install "macOS Sonoma 14.5-23F79"
```

### Install and restart if needed
```bash
sudo softwareupdate --install --all --restart
```

### Download only (don't install)
```bash
sudo softwareupdate --download --all
```

### Install downloaded updates
```bash
sudo softwareupdate --install --all --no-scan
```

## Update Settings

### Check automatic update settings
```bash
sudo defaults read /Library/Preferences/com.apple.SoftwareUpdate
```

### Enable automatic check
```bash
sudo defaults write /Library/Preferences/com.apple.SoftwareUpdate AutomaticCheckEnabled -bool true
```

### Set update frequency (days)
```bash
sudo defaults write /Library/Preferences/com.apple.SoftwareUpdate ScheduleFrequency -int 1
```

### Enable automatic download
```bash
sudo defaults write /Library/Preferences/com.apple.SoftwareUpdate AutomaticDownload -int 1
```

### Enable automatic macOS updates
```bash
sudo defaults write /Library/Preferences/com.apple.SoftwareUpdate AutomaticallyInstallMacOSUpdates -bool true
```

### Enable automatic app store updates
```bash
sudo defaults write /Library/Preferences/com.apple.commerce AutoUpdate -bool true
```

### Enable automatic security updates
```bash
sudo defaults write /Library/Preferences/com.apple.SoftwareUpdate CriticalUpdateInstall -bool true
```

### Enable automatic config data updates (XProtect, MRT)
```bash
sudo defaults write /Library/Preferences/com.apple.SoftwareUpdate ConfigDataInstall -bool true
```

## Clear Update Cache

### Clear downloaded updates
```bash
sudo rm -rf /Library/Updates/*
sudo softwareupdate --clear-catalog
```

## macOS Major Upgrades

### Download macOS installer
```bash
# List available full installers
softwareupdate --list-full-installers

# Download specific version
softwareupdate --fetch-full-installer --full-installer-version 14.5
```

### Check installer availability
```bash
# Installers are downloaded to /Applications
ls /Applications/ | grep "Install macOS"
```

## XProtect and MRT Updates

XProtect (anti-malware) and MRT (Malware Removal Tool) update silently:

### Check XProtect version
```bash
system_profiler SPInstallHistoryDataType | grep -A 5 "XProtect"
```

### Force XProtect update
```bash
sudo softwareupdate --background
```

## Deferred Updates (MDM)

When managed by MDM, updates can be deferred:
```bash
# Check deferred update policy
sudo defaults read /Library/Preferences/com.apple.SoftwareUpdate DeferredUpdates
```
"""

    def _spotlight_guide(self) -> str:
        return """# macOS Spotlight Search and Metadata

Spotlight is macOS's built-in search system, powered by a metadata index.
The command-line tools mdfind, mdls, and mdutil provide direct access.

## mdfind - Spotlight Search

### Basic search
```bash
mdfind "search term"
```

### Search by name only
```bash
mdfind -name "filename"
```

### Search only in specific directory
```bash
mdfind -onlyin /Users/username "search term"
```

### Live search (streaming results)
```bash
mdfind -live "search term"
```

### Search with metadata attributes
```bash
# Find PDF files
mdfind "kMDItemContentType == 'com.adobe.pdf'"

# Find images modified today
mdfind "kMDItemFSContentChangeDate >= \$time.today"

# Find files larger than 100MB
mdfind "kMDItemFSSize > 104857600"

# Find apps
mdfind "kMDItemContentType == 'com.apple.application-bundle'"

# Find files by kind
mdfind "kind:application"
mdfind "kind:image"
mdfind "kind:pdf"
```

### Boolean operators
```bash
mdfind "macos AND troubleshooting"
mdfind "macos OR linux"
mdfind "macos NOT windows"
```

## mdls - List Metadata Attributes

### List all metadata for a file
```bash
mdls /path/to/file
```

### Get specific attribute
```bash
mdls -name kMDItemContentType /path/to/file
mdls -name kMDItemFSSize /path/to/file
mdls -name kMDItemFSContentChangeDate /path/to/file
```

### List only specific attributes
```bash
mdls -name kMDItemContentType -name kMDItemFSSize /path/to/file
```

### Raw output (no attribute names)
```bash
mdls -raw -name kMDItemFSSize /path/to/file
```

## Common Metadata Attributes

| Attribute | Description |
|-----------|-------------|
| kMDItemFSName | Filename |
| kMDItemFSSize | File size (bytes) |
| kMDItemContentType | UTI type |
| kMDItemFSContentChangeDate | Last modified |
| kMDItemFSCreationDate | Creation date |
| kMDItemTitle | Document title |
| kMDItemAuthors | Document authors |
| kMDItemKeywords | Document keywords |
| kMDItemWhereFroms | Download source URL |
| kMDItemPixelWidth | Image width |
| kMDItemPixelHeight | Image height |
| kMDItemDurationSeconds | Media duration |

## mdutil - Spotlight Index Management

### Check indexing status
```bash
mdutil -s /
```

### Enable indexing
```bash
sudo mdutil -i on /
```

### Disable indexing
```bash
sudo mdutil -i off /
```

### Rebuild index from scratch
```bash
sudo mdutil -E /
```

### Erase and rebuild index
```bash
sudo mdutil -Er /
```

### Disable indexing for specific volume
```bash
sudo mdutil -i off /Volumes/ExternalDrive
```

### Check Spotlight status for all volumes
```bash
mdutil -as
```

## Privacy Settings

### Add folder to Spotlight privacy (exclude from indexing)
```bash
# Via System Settings > Siri & Spotlight > Privacy
# Or via defaults:
sudo defaults write /.Spotlight-V100/VolumeConfiguration.plist Exclusions -array-add "/path/to/exclude"
```

## Using Spotlight in Scripts

### Find recently modified files
```bash
mdfind -onlyin /Users/username 'kMDItemFSContentChangeDate >= $time.today(-7)'
```

### Find large files
```bash
mdfind -onlyin / 'kMDItemFSSize > 1073741824' 2>/dev/null | head -20
```

### Find duplicate filenames
```bash
mdfind -name "file.txt" | sort
```
"""

    def _diagnostics_guide(self) -> str:
        return """# macOS System Diagnostics

macOS provides several built-in tools for system diagnostics and troubleshooting.

## sysdiagnose

sysdiagnose collects comprehensive system diagnostic data.

### Generate a sysdiagnose
```bash
sudo sysdiagnose -f ~/Desktop/
# Output: sysdiagnose_<hostname>.<date>.<time>.tar.gz
```

### Quick sysdiagnose (no wait)
```bash
sudo sysdiagnose -b -f ~/Desktop/
```

### What sysdiagnose collects
- System logs (unified logging)
- Process list and memory usage
- Network configuration and state
- File system information
- Kernel state and extensions
- I/O Kit registry
- System profiler data
- Power management state
- Launchd services
- User preferences

## system_profiler

system_profiler provides detailed hardware and software information.

### Full system report
```bash
system_profiler
```

### Specific data types
```bash
system_profiler SPHardwareDataType
system_profiler SPSoftwareDataType
system_profiler SPStorageDataType
system_profiler SPNetworkDataType
system_profiler SPUSBDataType
system_profiler SPThunderboltDataType
system_profiler SPPCIDataType
system_profiler SPDisplaysDataType
system_profiler SPMemoryDataType
system_profiler SPPowerDataType
system_profiler SPBluetoothDataType
```

### XML output
```bash
system_profiler -xml SPHardwareDataType
```

### List all data types
```bash
system_profiler -listDataTypes
```

### Save full report to file
```bash
system_profiler > ~/Desktop/system_report.txt
```

## Hardware Diagnostics

### Apple Diagnostics (Apple Silicon)
1. Shut down
2. Hold power button until startup options
3. Press Cmd + D

### Apple Diagnostics (Intel)
1. Restart
2. Hold D key during startup
3. (Or Option + D for internet diagnostics)

### Check hardware via command line
```bash
# Memory
sysctl -n hw.memsize
sysctl hw.model

# CPU
sysctl -n machdep.cpu.brand_string
sysctl -n hw.ncpu

# Disk health
diskutil info disk0
smartctl -a /dev/disk0  # If smartmontools installed

# Battery
system_profiler SPPowerDataType
pmset -g batt
```

## Network Diagnostics

### Network interfaces
```bash
ifconfig -a
networksetup -listallhardwareports
```

### DNS diagnostics
```bash
scutil --dns
dig example.com
nslookup example.com
```

### Route table
```bash
netstat -rn
route -n get default
```

### Network quality
```bash
networkQuality
networkQuality -v
```

### Port scanning
```bash
# Check if port is open
nc -z -w 5 hostname 80

# Scan range
for port in {1..1024}; do (echo >/dev/tcp/hostname/$port) 2>/dev/null && echo "Port $port open"; done
```

## Performance Diagnostics

### CPU usage
```bash
top -l 1 -n 10
ps aux --sort=-%cpu | head -20
```

### Memory usage
```bash
vm_stat
top -l 1 -s 0 | grep PhysMem
```

### Disk I/O
```bash
iostat
iotop  # If available
```

### Process monitoring
```bash
# Real-time process monitoring
top
htop  # If installed via Homebrew

# Process tree
pstree  # If installed

# Open files by process
lsof -c processname
```

## Crash Reports

### View crash reports
```bash
ls ~/Library/Logs/DiagnosticReports/
ls /Library/Logs/DiagnosticReports/
```

### View recent crashes
```bash
log show --predicate 'eventMessage contains "crash"' --last 1h
```

### Check for kernel panics
```bash
ls /Library/Logs/DiagnosticReports/ | grep -i kernel
log show --predicate 'messageType == "fault"' --last 24h
```

## Log Collection for Support

### Collect specific logs
```bash
log collect --last 1h --output ~/Desktop/logs.logarchive
```

### Collect with predicate
```bash
log collect --predicate 'subsystem == "com.apple.networkextension"' --last 24h --output ~/Desktop/network_logs.logarchive
```
"""


def main():
    """CLI entry point for macOS support scraper."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Scrape macOS support documentation")
    parser.add_argument('--output-dir', type=Path, required=True, help="Output directory")
    parser.add_argument('--rate-limit', type=float, default=1.0, help="Seconds between requests")
    
    args = parser.parse_args()
    
    logging.basicConfig(level=logging.INFO)
    
    config = ScraperConfig(
        output_dir=args.output_dir,
        rate_limit_delay=args.rate_limit,
    )
    
    scraper = MacOSSupportScraper(config)
    documents = scraper.scrape()
    
    # Save to JSONL
    output_file = args.output_dir / "macos_support.jsonl"
    args.output_dir.mkdir(parents=True, exist_ok=True)
    
    with open(output_file, 'w') as f:
        for doc in documents:
            f.write(json.dumps(doc.to_dict()) + '\n')
    
    print(f"Saved {len(documents)} documents to {output_file}")


if __name__ == '__main__':
    main()
