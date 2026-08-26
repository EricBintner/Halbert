# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Snap Documentation Scraper.

Phase 26: Universal App Management

Generates Snap package manager documentation and troubleshooting guides.
"""

import logging
import json
from typing import List
from datetime import datetime
from pathlib import Path
import hashlib

from .base import BaseScraper, ScrapedDocument, ScraperConfig

logger = logging.getLogger('halbert')


class SnapDocsScraper(BaseScraper):
    """Scraper for Snap documentation and troubleshooting guides."""
    
    def __init__(self, config: ScraperConfig):
        super().__init__(config)
    
    def get_source_name(self) -> str:
        return "snap-docs"
    
    def scrape(self) -> List[ScrapedDocument]:
        documents = []
        logger.info("Generating Snap documentation...")
        documents.extend(self._generate_guides())
        logger.info(f"Total Snap documents: {len(documents)}")
        return documents
    
    def _generate_guides(self) -> List[ScrapedDocument]:
        documents = []
        
        guides = [
            {
                "title": "Snap Quick Start Guide",
                "content": self._quick_start(),
                "tags": ["snap", "installation", "basics"],
                "category": "getting_started",
            },
            {
                "title": "Snap Command Reference",
                "content": self._command_reference(),
                "tags": ["snap", "commands", "cli"],
                "category": "reference",
            },
            {
                "title": "Snap Troubleshooting Guide",
                "content": self._troubleshooting(),
                "tags": ["snap", "troubleshooting", "errors"],
                "category": "troubleshooting",
            },
            {
                "title": "Snap Confinement and Permissions",
                "content": self._confinement_guide(),
                "tags": ["snap", "confinement", "permissions", "security"],
                "category": "security",
            },
            {
                "title": "Snap Services Management",
                "content": self._services_guide(),
                "tags": ["snap", "services", "daemons"],
                "category": "services",
            },
        ]
        
        for guide in guides:
            doc_id = f"snap-guide-{hashlib.md5(guide['title'].encode()).hexdigest()[:12]}"
            
            documents.append(ScrapedDocument(
                id=doc_id,
                url=f"synthetic://halbert/snap/{doc_id}",
                title=guide["title"],
                content=guide["content"],
                source="halbert-snap-guides",
                category=guide["category"],
                tags=["linux", "package-manager"] + guide["tags"],
                scraped_at=datetime.utcnow().isoformat(),
                metadata={"platform": "linux", "doc_type": "guide", "synthetic": True}
            ))
        
        return documents
    
    def _quick_start(self) -> str:
        return """# Snap Quick Start Guide

Snap is Canonical's universal package format with automatic updates.

## Installation

### Ubuntu
```bash
# Snap is pre-installed on Ubuntu 16.04+
sudo apt install snapd  # If not installed
```

### Fedora
```bash
sudo dnf install snapd
sudo ln -s /var/lib/snapd/snap /snap
sudo systemctl enable --now snapd.socket
# Log out and back in
```

### Arch Linux
```bash
sudo pacman -S snapd
sudo systemctl enable --now snapd.socket
sudo ln -s /var/lib/snapd/snap /snap
```

## Basic Usage

### Search for snaps
```bash
snap find firefox
```

### Install a snap
```bash
sudo snap install firefox
```

### List installed snaps
```bash
snap list
```

### Update snaps
```bash
sudo snap refresh
```

### Remove a snap
```bash
sudo snap remove firefox
```

## Snap Store

Browse snaps at https://snapcraft.io/store

## Classic vs Strict Confinement

- **Strict**: Sandboxed, limited system access (default)
- **Classic**: Full system access like traditional packages

```bash
# Install classic snap (requires --classic flag)
sudo snap install code --classic
```
"""

    def _command_reference(self) -> str:
        return """# Snap Command Reference

## Installation

```bash
# Install snap
sudo snap install firefox

# Install classic snap (full system access)
sudo snap install code --classic

# Install from edge channel
sudo snap install firefox --edge

# Install specific revision
sudo snap install firefox --revision=123
```

## Listing and Info

```bash
# List installed snaps
snap list

# Detailed info
snap info firefox

# Show all versions/channels
snap info firefox --verbose

# Find snaps
snap find <search-term>
```

## Updates

```bash
# Update all snaps
sudo snap refresh

# Update specific snap
sudo snap refresh firefox

# List available updates
snap refresh --list

# Hold updates for a snap
sudo snap refresh --hold firefox

# Release hold
sudo snap refresh --unhold firefox
```

## Channels

```bash
# Switch channel
sudo snap switch firefox --channel=beta

# Install from specific channel
sudo snap install firefox --channel=edge

# Available channels: stable, candidate, beta, edge
```

## Removal

```bash
# Remove snap
sudo snap remove firefox

# Remove and purge data
sudo snap remove --purge firefox
```

## Revisions

```bash
# List revisions
snap list --all firefox

# Revert to previous revision
sudo snap revert firefox

# Revert to specific revision
sudo snap revert firefox --revision=100

# Remove old revisions
sudo snap remove firefox --revision=100
```

## Connections (Permissions)

```bash
# Show connections
snap connections firefox

# Connect interface
sudo snap connect firefox:camera

# Disconnect interface
sudo snap disconnect firefox:camera

# List all interfaces
snap interfaces
```

## Services

```bash
# List services
snap services

# Start/stop/restart
sudo snap start <snap>.<service>
sudo snap stop <snap>.<service>
sudo snap restart <snap>.<service>

# Enable/disable at boot
sudo snap start --enable <snap>.<service>
sudo snap stop --disable <snap>.<service>

# View logs
sudo snap logs <snap>.<service>
```

## Configuration

```bash
# View config
snap get <snap>

# Set config
sudo snap set <snap> key=value

# Unset config
sudo snap unset <snap> key
```

## Aliases

```bash
# List aliases
snap aliases

# Create alias
sudo snap alias firefox ff

# Remove alias
sudo snap unalias ff
```
"""

    def _troubleshooting(self) -> str:
        return """# Snap Troubleshooting Guide

## Common Issues

### Snap Won't Install: "cannot find snap"

**Cause**: Snapd service not running or not configured

**Solution**:
```bash
# Start snapd
sudo systemctl enable --now snapd.socket

# Create symlink (required on some distros)
sudo ln -s /var/lib/snapd/snap /snap

# Log out and back in
```

### Snap Slow to Start

**Cause**: First launch decompresses snap, or slow disk

**Solutions**:
1. First launch is always slower - wait
2. Classic snaps start faster:
   ```bash
   snap info <snap>  # Check confinement
   ```
3. Move snaps to faster disk (not easy, consider alternatives)

### "Permission denied" Errors

**Cause**: Missing interface connection

**Solution**:
```bash
# Check connections
snap connections <snap>

# Connect needed interface
sudo snap connect <snap>:home
sudo snap connect <snap>:removable-media
```

### Snap Can't Access Files

**Cause**: Strict confinement limits file access

**Solutions**:
```bash
# Connect home interface
sudo snap connect <snap>:home

# Connect removable media
sudo snap connect <snap>:removable-media

# Files must be in standard locations:
# ~/snap/<snap>/current/ - app's data
# ~/Documents, ~/Downloads - with home interface
```

### Theme/Font Issues

**Cause**: Snap can't access system themes

**Solutions**:
```bash
# Install GTK theme snap
sudo snap install gtk-common-themes

# Connect theme interfaces
sudo snap connect <snap>:gtk-3-themes gtk-common-themes
sudo snap connect <snap>:icon-themes gtk-common-themes
```

### Audio Not Working

**Cause**: Missing audio interface

**Solution**:
```bash
# Connect audio interfaces
sudo snap connect <snap>:audio-playback
sudo snap connect <snap>:audio-record  # for mic
sudo snap connect <snap>:pulseaudio
```

### Snap Update Failed

**Cause**: Various - held snap, network, disk space

**Solutions**:
```bash
# Check if held
snap refresh --list

# Release hold
sudo snap refresh --unhold <snap>

# Force refresh
sudo snap refresh <snap> --ignore-validation

# Check disk space
df -h /var/lib/snapd
```

### "snap-confine has elevated permissions" Error

**Cause**: AppArmor or permissions issue

**Solution**:
```bash
# Fix permissions
sudo apparmor_parser -r /var/lib/snapd/apparmor/profiles/*

# Or restart snapd
sudo systemctl restart snapd
```

### Snap Services Won't Start

**Solution**:
```bash
# Check service status
snap services <snap>

# View logs
sudo snap logs <snap>.<service>

# Restart service
sudo snap restart <snap>.<service>
```

## Disk Space Issues

```bash
# Check snap disk usage
du -sh /var/lib/snapd/snaps/

# Remove old revisions (keeps current + 1)
sudo snap set system refresh.retain=2

# Remove specific old revisions
snap list --all | awk '/disabled/{print $1, $3}' | while read snapname revision; do
    sudo snap remove "$snapname" --revision="$revision"
done
```

## Debugging

```bash
# Run snap with debug output
snap run --shell <snap>

# Check system logs
journalctl -u snapd -f

# Verbose refresh
sudo snap refresh --verbose
```
"""

    def _confinement_guide(self) -> str:
        return """# Snap Confinement and Permissions

## Confinement Modes

### Strict (Default)
- Sandboxed with AppArmor and seccomp
- Limited system access
- Uses interfaces for permissions

### Classic
- No sandbox
- Full system access like traditional packages
- Must be explicitly approved by Snap Store

### Devmode
- Developer mode
- Runs without confinement for testing
- Shows security warnings

```bash
# Check confinement
snap info <snap> | grep confinement
```

## Interfaces

Interfaces grant specific permissions to snaps.

### Common Interfaces

| Interface | Access |
|-----------|--------|
| `home` | Home directory |
| `removable-media` | USB drives, /media, /mnt |
| `network` | Network access |
| `network-bind` | Listen on ports |
| `audio-playback` | Play audio |
| `audio-record` | Record audio |
| `camera` | Webcam |
| `x11` | X11 display |
| `wayland` | Wayland display |
| `desktop` | Desktop integration |
| `cups-control` | Printing |

### Managing Interfaces

```bash
# List all interfaces
snap interfaces

# Show snap's connections
snap connections <snap>

# Connect interface
sudo snap connect <snap>:<plug>

# Disconnect interface
sudo snap disconnect <snap>:<plug>

# Example: grant Firefox camera access
sudo snap connect firefox:camera
```

### Auto-Connected Interfaces

Some interfaces connect automatically:
- `network`
- `network-bind` (for server snaps)
- `home` (for desktop apps)
- `desktop`
- `x11` or `wayland`

### Manual Interfaces

Must be explicitly connected:
- `camera`
- `audio-record`
- `removable-media`
- `personal-files`
- `system-files`

## Security Considerations

1. **Check confinement before installing**:
   ```bash
   snap info <snap> | grep -E "confinement|publisher"
   ```

2. **Classic snaps have full access** - trust the publisher

3. **Review connections**:
   ```bash
   snap connections <snap>
   ```

4. **Disconnect unused interfaces**:
   ```bash
   sudo snap disconnect <snap>:camera
   ```
"""

    def _services_guide(self) -> str:
        return """# Snap Services Management

## Listing Services

```bash
# All snap services
snap services

# Specific snap's services
snap services <snap-name>
```

Output columns:
- **Service**: snap.service name
- **Startup**: enabled/disabled
- **Current**: active/inactive
- **Notes**: additional info

## Controlling Services

```bash
# Start service
sudo snap start <snap>.<service>

# Stop service
sudo snap stop <snap>.<service>

# Restart service
sudo snap restart <snap>.<service>

# Start all services of a snap
sudo snap start <snap>
```

## Enable/Disable at Boot

```bash
# Enable at boot
sudo snap start --enable <snap>.<service>

# Disable at boot
sudo snap stop --disable <snap>.<service>
```

## Viewing Logs

```bash
# Recent logs
sudo snap logs <snap>.<service>

# Follow logs
sudo snap logs -f <snap>.<service>

# Last N lines
sudo snap logs -n 100 <snap>.<service>
```

## Timer Services

Some snaps have timer-based services (like cron):

```bash
# Check timer info
snap info <snap>  # Look for timer details

# Timers run automatically based on schedule
```

## Service Configuration

```bash
# View service config
snap get <snap>

# Set config
sudo snap set <snap> key=value

# Example: Set listening port
sudo snap set nextcloud ports.http=8080
```

## Troubleshooting Services

### Service Won't Start

```bash
# Check status
snap services <snap>

# View logs for errors
sudo snap logs <snap>.<service>

# Check system journal
journalctl -u snap.<snap>.<service>.service

# Try restarting
sudo snap restart <snap>.<service>
```

### Service Keeps Crashing

```bash
# Check for AppArmor denials
dmesg | grep -i apparmor

# View detailed logs
sudo snap logs -n 200 <snap>.<service>

# Try reinstalling
sudo snap remove <snap>
sudo snap install <snap>
```

## Common Service Snaps

- **nextcloud**: Self-hosted cloud
- **lxd**: Container manager
- **microk8s**: Kubernetes
- **docker**: Container runtime (classic)
"""


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Generate Snap documentation")
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    
    logging.basicConfig(level=logging.INFO)
    
    config = ScraperConfig(output_dir=args.output_dir)
    scraper = SnapDocsScraper(config)
    documents = scraper.scrape()
    
    output_file = args.output_dir / "snap_docs.jsonl"
    args.output_dir.mkdir(parents=True, exist_ok=True)
    
    with open(output_file, 'w') as f:
        for doc in documents:
            f.write(json.dumps(doc.to_dict()) + '\n')
    
    print(f"Saved {len(documents)} documents to {output_file}")


if __name__ == '__main__':
    main()
