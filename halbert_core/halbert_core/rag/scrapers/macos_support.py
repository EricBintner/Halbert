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
