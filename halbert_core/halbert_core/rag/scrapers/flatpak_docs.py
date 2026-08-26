# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Flatpak Documentation Scraper.

Phase 26: Universal App Management

Scrapes Flatpak documentation and generates troubleshooting guides.
"""

import logging
import json
from typing import List
from datetime import datetime
from pathlib import Path
import hashlib

from .base import BaseScraper, ScrapedDocument, ScraperConfig

logger = logging.getLogger('halbert')


class FlatpakDocsScraper(BaseScraper):
    """
    Scraper for Flatpak documentation and troubleshooting guides.
    """
    
    # Flatpak documentation pages
    DOC_PAGES = [
        ("https://docs.flatpak.org/en/latest/introduction.html", "Introduction to Flatpak"),
        ("https://docs.flatpak.org/en/latest/using-flatpak.html", "Using Flatpak"),
        ("https://docs.flatpak.org/en/latest/flatpak-command-reference.html", "Command Reference"),
    ]
    
    def __init__(self, config: ScraperConfig):
        """Initialize Flatpak docs scraper."""
        super().__init__(config)
    
    def get_source_name(self) -> str:
        """Get source name."""
        return "flatpak-docs"
    
    def scrape(self) -> List[ScrapedDocument]:
        """Scrape Flatpak documentation."""
        documents = []
        
        # Generate comprehensive troubleshooting guides
        logger.info("Generating Flatpak documentation...")
        documents.extend(self._generate_guides())
        
        logger.info(f"Total Flatpak documents: {len(documents)}")
        return documents
    
    def _generate_guides(self) -> List[ScrapedDocument]:
        """Generate Flatpak guides and troubleshooting docs."""
        documents = []
        
        guides = [
            {
                "title": "Flatpak Quick Start Guide",
                "content": self._quick_start_guide(),
                "tags": ["flatpak", "installation", "basics"],
                "category": "getting_started",
            },
            {
                "title": "Flatpak Command Reference",
                "content": self._command_reference(),
                "tags": ["flatpak", "commands", "cli"],
                "category": "reference",
            },
            {
                "title": "Flatpak Troubleshooting Guide",
                "content": self._troubleshooting_guide(),
                "tags": ["flatpak", "troubleshooting", "errors"],
                "category": "troubleshooting",
            },
            {
                "title": "Flatpak Permissions and Sandboxing",
                "content": self._permissions_guide(),
                "tags": ["flatpak", "permissions", "sandbox", "security"],
                "category": "security",
            },
            {
                "title": "Managing Flatpak Remotes",
                "content": self._remotes_guide(),
                "tags": ["flatpak", "remotes", "flathub", "repositories"],
                "category": "configuration",
            },
            {
                "title": "Flatpak vs Native Packages",
                "content": self._comparison_guide(),
                "tags": ["flatpak", "comparison", "native", "packages"],
                "category": "concepts",
            },
        ]
        
        for guide in guides:
            doc_id = f"flatpak-guide-{hashlib.md5(guide['title'].encode()).hexdigest()[:12]}"
            
            documents.append(ScrapedDocument(
                id=doc_id,
                url=f"synthetic://halbert/flatpak/{doc_id}",
                title=guide["title"],
                content=guide["content"],
                source="halbert-flatpak-guides",
                category=guide["category"],
                tags=["linux", "package-manager"] + guide["tags"],
                scraped_at=datetime.utcnow().isoformat(),
                metadata={
                    "platform": "linux",
                    "doc_type": "guide",
                    "synthetic": True,
                }
            ))
        
        return documents
    
    def _quick_start_guide(self) -> str:
        return """# Flatpak Quick Start Guide

Flatpak is a universal package format for Linux that provides sandboxed applications.

## Installation

### Ubuntu/Debian
```bash
sudo apt install flatpak
```

### Fedora
```bash
# Flatpak is pre-installed on Fedora Workstation
sudo dnf install flatpak  # If not installed
```

### Arch Linux
```bash
sudo pacman -S flatpak
```

## Add Flathub Repository

Flathub is the main repository for Flatpak applications:

```bash
flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
```

## Basic Usage

### Search for apps
```bash
flatpak search firefox
```

### Install an app
```bash
flatpak install flathub org.mozilla.firefox
```

### Run an app
```bash
flatpak run org.mozilla.firefox
```

### List installed apps
```bash
flatpak list --app
```

### Update all apps
```bash
flatpak update
```

### Uninstall an app
```bash
flatpak uninstall org.mozilla.firefox
```

## System vs User Installation

- **System-wide** (default): Available to all users, requires sudo
- **User**: Available only to current user, no sudo needed

```bash
# User installation
flatpak install --user flathub org.mozilla.firefox

# List user apps
flatpak list --user --app
```

## Desktop Integration

After installation, apps appear in your desktop menu. If not:

```bash
# Restart your session or run:
update-desktop-database ~/.local/share/applications
```
"""

    def _command_reference(self) -> str:
        return """# Flatpak Command Reference

## Installation Commands

```bash
# Install from Flathub
flatpak install flathub org.mozilla.firefox

# Install from .flatpakref file
flatpak install ./app.flatpakref

# Install from .flatpak bundle
flatpak install ./app.flatpak

# Install specific version/branch
flatpak install flathub org.mozilla.firefox//stable
```

## Listing and Info

```bash
# List all installed apps
flatpak list --app

# List all installed (including runtimes)
flatpak list

# List with columns
flatpak list --app --columns=application,name,version,origin

# App info
flatpak info org.mozilla.firefox

# Show app size
flatpak info --show-size org.mozilla.firefox
```

## Updates

```bash
# Check for updates
flatpak remote-ls --updates

# Update all
flatpak update

# Update specific app
flatpak update org.mozilla.firefox

# Auto-confirm updates
flatpak update -y
```

## Uninstallation

```bash
# Uninstall app
flatpak uninstall org.mozilla.firefox

# Uninstall with data
flatpak uninstall --delete-data org.mozilla.firefox

# Remove unused runtimes
flatpak uninstall --unused
```

## Remote Management

```bash
# List remotes
flatpak remotes

# Add remote
flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo

# Remove remote
flatpak remote-delete flathub

# List apps in remote
flatpak remote-ls flathub --app
```

## Permissions

```bash
# Show permissions
flatpak info --show-permissions org.mozilla.firefox

# Override permission (user)
flatpak override --user --filesystem=home org.mozilla.firefox

# Reset overrides
flatpak override --user --reset org.mozilla.firefox

# List all overrides
flatpak override --user --show
```

## Running Apps

```bash
# Run app
flatpak run org.mozilla.firefox

# Run with specific command
flatpak run --command=bash org.mozilla.firefox

# Run with environment variable
flatpak run --env=MY_VAR=value org.mozilla.firefox
```

## Maintenance

```bash
# Repair installation
flatpak repair

# Show disk usage
flatpak list --app --columns=application,size

# Clean up old versions
flatpak uninstall --unused
```
"""

    def _troubleshooting_guide(self) -> str:
        return """# Flatpak Troubleshooting Guide

## Common Issues

### App Won't Start

**Symptom**: App closes immediately or shows error

**Solutions**:
1. Run from terminal to see errors:
   ```bash
   flatpak run org.example.app
   ```

2. Check if runtime is installed:
   ```bash
   flatpak info org.example.app
   # Look for "Runtime:" line and verify it's installed
   flatpak list --runtime | grep <runtime-name>
   ```

3. Reinstall the app:
   ```bash
   flatpak uninstall org.example.app
   flatpak install flathub org.example.app
   ```

### Permission Denied Errors

**Symptom**: App can't access files, devices, or network

**Solutions**:
1. Check current permissions:
   ```bash
   flatpak info --show-permissions org.example.app
   ```

2. Grant filesystem access:
   ```bash
   # Access home directory
   flatpak override --user --filesystem=home org.example.app
   
   # Access specific path
   flatpak override --user --filesystem=/path/to/folder org.example.app
   
   # Full filesystem access (not recommended)
   flatpak override --user --filesystem=host org.example.app
   ```

3. Grant device access:
   ```bash
   flatpak override --user --device=all org.example.app
   ```

### App Can't Find Files in Home Directory

**Symptom**: App doesn't see files in ~/Documents, ~/Downloads, etc.

**Cause**: Flatpak apps use XDG portals for file access

**Solutions**:
1. Use the app's file picker (goes through portal)
2. Grant explicit filesystem access:
   ```bash
   flatpak override --user --filesystem=~/Documents org.example.app
   ```

### Slow App Startup

**Symptom**: Flatpak apps take much longer to start than native

**Causes**:
- First run downloads fonts/themes
- Disk I/O on slower drives
- Missing GPU acceleration

**Solutions**:
1. Wait for first-run setup to complete
2. Enable GPU:
   ```bash
   flatpak override --user --device=dri org.example.app
   ```

### Theme/Icon Issues

**Symptom**: App looks different from native apps, wrong icons

**Solutions**:
1. Install theme as Flatpak:
   ```bash
   flatpak install flathub org.gtk.Gtk3theme.Adwaita-dark
   ```

2. Grant theme access:
   ```bash
   flatpak override --user --filesystem=~/.themes org.example.app
   flatpak override --user --filesystem=~/.icons org.example.app
   ```

### "No remote refs found" Error

**Symptom**: Can't install apps, remote seems empty

**Solutions**:
1. Update remote:
   ```bash
   flatpak update --appstream
   ```

2. Re-add Flathub:
   ```bash
   flatpak remote-delete flathub
   flatpak remote-add flathub https://dl.flathub.org/repo/flathub.flatpakrepo
   ```

### Disk Space Issues

**Symptom**: Flatpak using too much disk space

**Solutions**:
1. Check usage:
   ```bash
   du -sh ~/.local/share/flatpak
   du -sh /var/lib/flatpak
   ```

2. Remove unused runtimes:
   ```bash
   flatpak uninstall --unused
   ```

3. Remove old app data:
   ```bash
   flatpak uninstall --delete-data org.example.app
   ```

### Sound Not Working

**Symptom**: No audio in Flatpak app

**Solutions**:
1. Check PulseAudio access:
   ```bash
   flatpak override --user --socket=pulseaudio org.example.app
   ```

2. Check PipeWire access:
   ```bash
   flatpak override --user --socket=pipewire org.example.app
   ```

## Repair Commands

```bash
# Repair Flatpak installation
flatpak repair

# Repair user installation
flatpak repair --user

# Force reinstall app
flatpak uninstall org.example.app
flatpak install flathub org.example.app
```

## Logs and Debugging

```bash
# Run app with debug output
flatpak run --verbose org.example.app

# Check system journal
journalctl --user -f

# Flatpak-specific logs
journalctl -b | grep flatpak
```
"""

    def _permissions_guide(self) -> str:
        return """# Flatpak Permissions and Sandboxing

## Understanding the Sandbox

Flatpak apps run in a sandbox with limited access to your system:
- **Filesystem**: Limited to app-specific directories
- **Network**: May be restricted
- **Devices**: GPU, webcam, etc. need explicit access
- **IPC**: Inter-process communication controlled

## Viewing Permissions

```bash
# Show all permissions
flatpak info --show-permissions org.example.app

# Show metadata file
flatpak info --show-metadata org.example.app
```

## Common Permission Overrides

### Filesystem Access

```bash
# Home directory
flatpak override --user --filesystem=home org.example.app

# Specific folder
flatpak override --user --filesystem=/path/to/folder org.example.app

# Read-only access
flatpak override --user --filesystem=/path:ro org.example.app

# Remove filesystem access
flatpak override --user --nofilesystem=home org.example.app
```

### Device Access

```bash
# All devices
flatpak override --user --device=all org.example.app

# Just GPU (DRI)
flatpak override --user --device=dri org.example.app
```

### Socket Access

```bash
# X11 display
flatpak override --user --socket=x11 org.example.app

# Wayland display
flatpak override --user --socket=wayland org.example.app

# PulseAudio
flatpak override --user --socket=pulseaudio org.example.app

# PipeWire (modern audio)
flatpak override --user --socket=pipewire org.example.app

# Session bus (D-Bus)
flatpak override --user --socket=session-bus org.example.app

# System bus (requires care)
flatpak override --user --socket=system-bus org.example.app
```

### Network Access

```bash
# Enable network
flatpak override --user --share=network org.example.app

# Disable network (for privacy)
flatpak override --user --unshare=network org.example.app
```

### Environment Variables

```bash
flatpak override --user --env=MY_VARIABLE=value org.example.app
```

## Resetting Overrides

```bash
# Reset all overrides for an app
flatpak override --user --reset org.example.app

# Show current overrides
flatpak override --user --show org.example.app
```

## XDG Portals

Flatpak uses "portals" to safely provide system access:

- **File Chooser**: Let apps open/save files without full filesystem access
- **Screenshot**: Capture screen through portal
- **Notifications**: Send desktop notifications
- **Print**: Print documents

Portals are handled by `xdg-desktop-portal` and backend for your desktop.

```bash
# Check if portals are running
systemctl --user status xdg-desktop-portal
```

## Security Considerations

1. **Avoid --filesystem=host**: Gives full system access, defeats sandboxing
2. **Be careful with --device=all**: May expose sensitive devices
3. **Check app permissions before installing**: Some apps request excessive access
4. **Use Flatseal**: GUI tool for managing Flatpak permissions
   ```bash
   flatpak install flathub com.github.tchx84.Flatseal
   ```
"""

    def _remotes_guide(self) -> str:
        return """# Managing Flatpak Remotes

## What are Remotes?

Remotes are repositories where Flatpak apps are hosted. Flathub is the largest.

## Listing Remotes

```bash
# List configured remotes
flatpak remotes

# Detailed info
flatpak remotes -d

# Show remote URL
flatpak remote-info --show-url flathub
```

## Adding Remotes

### Flathub (Main Repository)
```bash
flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
```

### Flathub Beta
```bash
flatpak remote-add --if-not-exists flathub-beta https://flathub.org/beta-repo/flathub-beta.flatpakrepo
```

### GNOME Nightly
```bash
flatpak remote-add --if-not-exists gnome-nightly https://nightly.gnome.org/gnome-nightly.flatpakrepo
```

### KDE Applications
```bash
flatpak remote-add --if-not-exists kdeapps https://distribute.kde.org/kdeapps.flatpakrepo
```

## User vs System Remotes

```bash
# Add remote for current user only
flatpak remote-add --user flathub https://dl.flathub.org/repo/flathub.flatpakrepo

# Add remote system-wide (requires sudo)
sudo flatpak remote-add --system flathub https://dl.flathub.org/repo/flathub.flatpakrepo
```

## Removing Remotes

```bash
flatpak remote-delete flathub
```

## Modifying Remotes

```bash
# Disable a remote (keep but don't use)
flatpak remote-modify --disable flathub

# Re-enable
flatpak remote-modify --enable flathub

# Change priority (lower = higher priority)
flatpak remote-modify --prio=1 flathub
```

## Updating Remote Data

```bash
# Update appstream data (app listings)
flatpak update --appstream

# Force update for specific remote
flatpak remote-ls flathub --force-update
```

## Listing Apps in a Remote

```bash
# All apps
flatpak remote-ls flathub --app

# Search
flatpak remote-ls flathub --app | grep -i firefox

# With columns
flatpak remote-ls flathub --app --columns=application,name,version
```

## Private/Corporate Remotes

You can host your own Flatpak repository:

```bash
# Add with GPG key
flatpak remote-add --gpg-import=key.gpg myrepo https://repo.example.com/repo
```
"""

    def _comparison_guide(self) -> str:
        return """# Flatpak vs Native Packages

## Overview

| Aspect | Native (APT/DNF) | Flatpak |
|--------|------------------|---------|
| **Sandboxing** | None | Yes |
| **Dependencies** | Shared system libs | Bundled |
| **Updates** | With system | Independent |
| **Disk usage** | Lower | Higher |
| **Startup speed** | Faster | Slightly slower |
| **System integration** | Full | Limited by sandbox |
| **Security** | Trusts distro | Sandboxed |

## When to Use Flatpak

✅ **Good for Flatpak**:
- Desktop applications (browsers, office, media)
- Apps needing latest versions
- Apps from untrusted sources
- Testing software safely
- Running multiple versions

❌ **Better as native**:
- System tools and services
- CLI utilities
- Development libraries
- Performance-critical apps
- Apps needing deep system integration

## Running Both

You can have both Flatpak and native versions:

```bash
# Run Flatpak Firefox
flatpak run org.mozilla.firefox

# Run native Firefox
/usr/bin/firefox
```

## Disk Usage Comparison

Flatpak uses more disk space because:
1. Each app bundles its dependencies
2. Runtimes are shared but still large
3. Multiple versions can coexist

Mitigation:
```bash
# Remove unused runtimes
flatpak uninstall --unused

# Check total Flatpak usage
du -sh ~/.local/share/flatpak /var/lib/flatpak
```

## Performance Considerations

**First launch**: Slower (loading bundled libs)
**Subsequent launches**: Nearly equal
**Runtime**: Usually equivalent
**GPU apps**: Ensure DRI access: `flatpak override --user --device=dri`

## Security Trade-offs

**Native packages**:
- Trust your distro's security team
- Full system access
- Potential for system-wide damage

**Flatpak**:
- Sandboxed by default
- Limited blast radius
- May request excessive permissions
- Use Flatseal to audit/limit

## Migration Tips

### From Native to Flatpak
1. Install Flatpak version
2. Export data/settings from native
3. Import into Flatpak app
4. Test thoroughly
5. Uninstall native version

### Finding Flatpak Alternatives
```bash
# Search Flathub
flatpak search <app-name>

# Or browse https://flathub.org
```
"""


def main():
    """CLI entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Generate Flatpak documentation")
    parser.add_argument('--output-dir', type=Path, required=True)
    
    args = parser.parse_args()
    
    logging.basicConfig(level=logging.INFO)
    
    config = ScraperConfig(output_dir=args.output_dir)
    scraper = FlatpakDocsScraper(config)
    documents = scraper.scrape()
    
    output_file = args.output_dir / "flatpak_docs.jsonl"
    args.output_dir.mkdir(parents=True, exist_ok=True)
    
    with open(output_file, 'w') as f:
        for doc in documents:
            f.write(json.dumps(doc.to_dict()) + '\n')
    
    print(f"Saved {len(documents)} documents to {output_file}")


if __name__ == '__main__':
    main()
