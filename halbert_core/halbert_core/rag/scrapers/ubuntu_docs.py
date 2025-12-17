"""
Ubuntu Documentation Scraper - Comprehensive Ubuntu/Debian guides.

Phase 27: RAG Coverage

Generates synthetic documentation covering:
- Package management (apt, dpkg)
- System administration
- Networking (netplan, NetworkManager)
- Security (UFW, AppArmor)
- Server setup and configuration
"""

import logging
from typing import List
from datetime import datetime
from pathlib import Path

from .base import BaseScraper, ScrapedDocument, ScraperConfig

logger = logging.getLogger('halbert')


class UbuntuDocsScraper(BaseScraper):
    """
    Generates comprehensive Ubuntu/Debian documentation for RAG.
    """
    
    def __init__(self, config: ScraperConfig):
        super().__init__(config)
    
    def get_source_name(self) -> str:
        return "ubuntu-docs"
    
    def scrape(self) -> List[ScrapedDocument]:
        """Generate Ubuntu documentation."""
        logger.info("Generating Ubuntu documentation...")
        
        documents = []
        documents.extend(self._generate_guides())
        
        logger.info(f"Total Ubuntu documents: {len(documents)}")
        return documents
    
    def _generate_guides(self) -> List[ScrapedDocument]:
        """Generate all Ubuntu guides."""
        guides = []
        
        guides.append(self._apt_guide())
        guides.append(self._dpkg_guide())
        guides.append(self._netplan_guide())
        guides.append(self._ufw_guide())
        guides.append(self._apparmor_guide())
        guides.append(self._snap_ubuntu_guide())
        guides.append(self._server_setup_guide())
        guides.append(self._troubleshooting_guide())
        
        return guides
    
    def _apt_guide(self) -> ScrapedDocument:
        """APT package management guide."""
        content = """# APT Package Management Complete Guide

## Basic Commands

```bash
# Update package lists
sudo apt update

# Upgrade all packages
sudo apt upgrade
sudo apt full-upgrade    # Also handles dependencies that require removal

# Install packages
sudo apt install nginx
sudo apt install nginx php-fpm mysql-server  # Multiple packages

# Remove packages
sudo apt remove nginx           # Keep config files
sudo apt purge nginx            # Remove config files too
sudo apt autoremove             # Remove unused dependencies

# Search packages
apt search nginx
apt show nginx                  # Package details
apt list --installed            # All installed packages
apt list --upgradable           # Packages with updates
```

## Advanced APT Operations

### Hold/Pin Packages
```bash
# Prevent package from being upgraded
sudo apt-mark hold nginx
sudo apt-mark unhold nginx
apt-mark showhold
```

### Install Specific Version
```bash
# List available versions
apt-cache policy nginx

# Install specific version
sudo apt install nginx=1.18.0-0ubuntu1
```

### Download Without Installing
```bash
apt download nginx
apt source nginx                # Download source
```

### Clean Cache
```bash
sudo apt clean                  # Remove all cached packages
sudo apt autoclean              # Remove old cached packages
du -sh /var/cache/apt/archives  # Check cache size
```

## Repository Management

### Add Repository
```bash
# Add PPA (Personal Package Archive)
sudo add-apt-repository ppa:ondrej/php
sudo apt update

# Add third-party repository
echo "deb https://packages.example.com/ubuntu focal main" | sudo tee /etc/apt/sources.list.d/example.list
wget -qO - https://packages.example.com/key.gpg | sudo apt-key add -
sudo apt update
```

### Remove Repository
```bash
sudo add-apt-repository --remove ppa:ondrej/php
# Or delete file in /etc/apt/sources.list.d/
```

### List Repositories
```bash
cat /etc/apt/sources.list
ls /etc/apt/sources.list.d/
apt-cache policy
```

## Troubleshooting

### Fix Broken Packages
```bash
sudo apt --fix-broken install
sudo dpkg --configure -a
```

### Clear Lock Files (if apt is stuck)
```bash
sudo rm /var/lib/dpkg/lock-frontend
sudo rm /var/lib/apt/lists/lock
sudo rm /var/cache/apt/archives/lock
```

### Rebuild Package Cache
```bash
sudo apt clean
sudo apt update
```

## Configuration Files

- `/etc/apt/sources.list` - Main repository list
- `/etc/apt/sources.list.d/` - Additional repositories
- `/etc/apt/apt.conf.d/` - APT configuration
- `/var/lib/dpkg/status` - Package database
- `/var/cache/apt/archives/` - Downloaded packages

## Unattended Upgrades

```bash
# Install
sudo apt install unattended-upgrades

# Configure
sudo dpkg-reconfigure unattended-upgrades

# Check status
systemctl status unattended-upgrades
cat /var/log/unattended-upgrades/unattended-upgrades.log
```
"""
        return ScrapedDocument(
            id=self._generate_id("apt-guide"),
            url="https://help.ubuntu.com/community/AptGet",
            title="APT Package Management Complete Guide",
            content=content,
            source=self.get_source_name(),
            category="packages",
            tags=["ubuntu", "apt", "dpkg", "packages", "linux", "debian"],
            scraped_at=datetime.utcnow().isoformat(),
            metadata={"type": "reference", "priority": "high"}
        )
    
    def _dpkg_guide(self) -> ScrapedDocument:
        """dpkg low-level package management."""
        content = """# dpkg Low-Level Package Management

## Basic Commands

```bash
# Install .deb file
sudo dpkg -i package.deb
sudo dpkg -i *.deb               # Install multiple

# Remove package
sudo dpkg -r packagename         # Keep config
sudo dpkg -P packagename         # Purge all

# List installed packages
dpkg -l
dpkg -l | grep nginx
dpkg -l nginx                    # Specific package

# List package contents
dpkg -L nginx                    # Files installed by package

# Find which package owns a file
dpkg -S /usr/bin/nginx
dpkg -S nginx.conf

# Show package info
dpkg -s nginx
dpkg --info package.deb          # Info from .deb file
```

## Package States

| Status | Meaning |
|--------|---------|
| `ii` | Installed |
| `rc` | Removed, config remains |
| `un` | Unknown/not installed |
| `hi` | Half-installed (error) |
| `iU` | Unpacked, not configured |

## Troubleshooting

### Fix Half-Installed Packages
```bash
sudo dpkg --configure -a
sudo apt --fix-broken install
```

### Force Remove Broken Package
```bash
sudo dpkg --remove --force-remove-reinstreq packagename
```

### Reconfigure Package
```bash
sudo dpkg-reconfigure packagename
sudo dpkg-reconfigure tzdata     # Example: timezone
```

### Extract .deb Without Installing
```bash
dpkg-deb -x package.deb /tmp/extracted/
dpkg-deb -e package.deb /tmp/control/   # Extract control files
```

## dpkg Database

```bash
# Database location
/var/lib/dpkg/

# Backup database
sudo cp -r /var/lib/dpkg /var/lib/dpkg.backup

# List available files
ls /var/lib/dpkg/info/*.list
```
"""
        return ScrapedDocument(
            id=self._generate_id("dpkg-guide"),
            url="https://help.ubuntu.com/community/dpkg",
            title="dpkg Low-Level Package Management",
            content=content,
            source=self.get_source_name(),
            category="packages",
            tags=["ubuntu", "dpkg", "packages", "linux", "debian"],
            scraped_at=datetime.utcnow().isoformat(),
            metadata={"type": "reference", "priority": "high"}
        )
    
    def _netplan_guide(self) -> ScrapedDocument:
        """Netplan networking guide."""
        content = """# Netplan Network Configuration

## Overview

Netplan is Ubuntu's network configuration tool (17.10+). It uses YAML files and can render to NetworkManager or systemd-networkd.

## Configuration Location

```
/etc/netplan/*.yaml
```

## Basic Examples

### DHCP (Default)
```yaml
# /etc/netplan/00-installer-config.yaml
network:
  version: 2
  ethernets:
    enp0s3:
      dhcp4: true
```

### Static IP
```yaml
network:
  version: 2
  ethernets:
    enp0s3:
      dhcp4: false
      addresses:
        - 192.168.1.100/24
      routes:
        - to: default
          via: 192.168.1.1
      nameservers:
        addresses:
          - 8.8.8.8
          - 8.8.4.4
```

### Multiple Addresses
```yaml
network:
  version: 2
  ethernets:
    enp0s3:
      addresses:
        - 192.168.1.100/24
        - 192.168.1.101/24
        - 10.0.0.50/8
```

### Bonding (Link Aggregation)
```yaml
network:
  version: 2
  ethernets:
    enp0s3: {}
    enp0s4: {}
  bonds:
    bond0:
      interfaces:
        - enp0s3
        - enp0s4
      addresses:
        - 192.168.1.100/24
      parameters:
        mode: 802.3ad
        mii-monitor-interval: 100
```

### VLAN
```yaml
network:
  version: 2
  ethernets:
    enp0s3:
      dhcp4: false
  vlans:
    vlan100:
      id: 100
      link: enp0s3
      addresses:
        - 192.168.100.10/24
```

### WiFi
```yaml
network:
  version: 2
  wifis:
    wlan0:
      access-points:
        "MyNetwork":
          password: "secretpassword"
      dhcp4: true
```

## Commands

```bash
# Apply configuration
sudo netplan apply

# Test configuration (auto-reverts in 120s if no confirmation)
sudo netplan try

# Generate backend config without applying
sudo netplan generate

# Debug
sudo netplan --debug apply
```

## Troubleshooting

### Check Configuration
```bash
sudo netplan generate 2>&1
```

### View Applied Config
```bash
ip addr show
ip route show
cat /etc/resolv.conf
```

### Common Errors
- **Indentation**: YAML requires consistent spaces (2 spaces, not tabs)
- **Interface names**: Use `ip link` to find correct names
- **Permissions**: File must be readable by root
"""
        return ScrapedDocument(
            id=self._generate_id("netplan-guide"),
            url="https://netplan.io/examples",
            title="Netplan Network Configuration",
            content=content,
            source=self.get_source_name(),
            category="networking",
            tags=["ubuntu", "netplan", "networking", "linux"],
            scraped_at=datetime.utcnow().isoformat(),
            metadata={"type": "guide", "priority": "high"}
        )
    
    def _ufw_guide(self) -> ScrapedDocument:
        """UFW firewall guide."""
        content = """# UFW (Uncomplicated Firewall) Guide

## Basic Commands

```bash
# Enable/disable
sudo ufw enable
sudo ufw disable

# Check status
sudo ufw status
sudo ufw status verbose
sudo ufw status numbered    # Show rule numbers

# Reset to defaults
sudo ufw reset
```

## Allow/Deny Rules

### By Port
```bash
sudo ufw allow 22
sudo ufw allow 22/tcp
sudo ufw allow 80,443/tcp

# Port ranges
sudo ufw allow 6000:6007/tcp

# Deny
sudo ufw deny 23
```

### By Service Name
```bash
sudo ufw allow ssh
sudo ufw allow http
sudo ufw allow https
sudo ufw allow 'Nginx Full'

# List available services
sudo ufw app list
```

### By IP Address
```bash
# Allow from specific IP
sudo ufw allow from 192.168.1.100

# Allow from subnet
sudo ufw allow from 192.168.1.0/24

# Allow to specific port from IP
sudo ufw allow from 192.168.1.100 to any port 22

# Allow to specific interface
sudo ufw allow in on eth0 to any port 80
```

## Delete Rules

```bash
# By rule number
sudo ufw status numbered
sudo ufw delete 2

# By specification
sudo ufw delete allow 80
sudo ufw delete allow ssh
```

## Default Policies

```bash
# Deny all incoming, allow all outgoing (recommended)
sudo ufw default deny incoming
sudo ufw default allow outgoing

# Check defaults
sudo ufw status verbose
```

## Logging

```bash
# Enable logging
sudo ufw logging on
sudo ufw logging medium    # low, medium, high, full

# View logs
sudo tail -f /var/log/ufw.log
journalctl -f | grep UFW
```

## Application Profiles

```bash
# List profiles
sudo ufw app list

# Show profile details
sudo ufw app info 'Nginx Full'

# Create custom profile
# /etc/ufw/applications.d/myapp
[MyApp]
title=My Application
description=My application description
ports=8080/tcp
```

## Advanced Rules

```bash
# Rate limiting (prevent brute force)
sudo ufw limit ssh

# Allow outgoing to specific IP
sudo ufw allow out to 8.8.8.8

# Deny outgoing
sudo ufw deny out 25    # Block SMTP
```

## Configuration Files

- `/etc/ufw/ufw.conf` - Main config
- `/etc/ufw/before.rules` - Rules before user rules
- `/etc/ufw/after.rules` - Rules after user rules
- `/etc/ufw/user.rules` - User-added rules
"""
        return ScrapedDocument(
            id=self._generate_id("ufw-guide"),
            url="https://help.ubuntu.com/community/UFW",
            title="UFW (Uncomplicated Firewall) Guide",
            content=content,
            source=self.get_source_name(),
            category="security",
            tags=["ubuntu", "ufw", "firewall", "security", "linux"],
            scraped_at=datetime.utcnow().isoformat(),
            metadata={"type": "guide", "priority": "high"}
        )
    
    def _apparmor_guide(self) -> ScrapedDocument:
        """AppArmor security guide."""
        content = """# AppArmor Security Guide

## Overview

AppArmor is a Linux Security Module that restricts program capabilities with per-program profiles.

## Status and Profiles

```bash
# Check status
sudo aa-status
sudo apparmor_status

# List profiles
ls /etc/apparmor.d/

# View profile
cat /etc/apparmor.d/usr.sbin.nginx
```

## Profile Modes

| Mode | Description |
|------|-------------|
| **enforce** | Violations are blocked and logged |
| **complain** | Violations are logged but allowed |
| **disabled** | Profile is not loaded |

```bash
# Set to complain mode
sudo aa-complain /etc/apparmor.d/usr.sbin.nginx

# Set to enforce mode
sudo aa-enforce /etc/apparmor.d/usr.sbin.nginx

# Disable profile
sudo ln -s /etc/apparmor.d/usr.sbin.nginx /etc/apparmor.d/disable/
sudo apparmor_parser -R /etc/apparmor.d/usr.sbin.nginx
```

## Managing Profiles

```bash
# Reload all profiles
sudo systemctl reload apparmor

# Load specific profile
sudo apparmor_parser -r /etc/apparmor.d/usr.sbin.nginx

# Unload profile
sudo apparmor_parser -R /etc/apparmor.d/usr.sbin.nginx
```

## Creating Profiles

```bash
# Generate profile from running program
sudo aa-genprof /usr/bin/myapp

# Generate from logs
sudo aa-logprof

# Install profile tools
sudo apt install apparmor-utils
```

## Profile Syntax Basics

```
# /etc/apparmor.d/usr.local.bin.myapp
#include <tunables/global>

/usr/local/bin/myapp {
  #include <abstractions/base>
  
  # Allow read access
  /etc/myapp/** r,
  
  # Allow read-write
  /var/lib/myapp/** rw,
  
  # Allow execution
  /usr/bin/helper px,
  
  # Network access
  network inet tcp,
  
  # Capabilities
  capability net_bind_service,
}
```

## Troubleshooting

```bash
# View denials
sudo dmesg | grep apparmor
journalctl -k | grep apparmor

# Audit log
sudo cat /var/log/audit/audit.log | grep apparmor
```
"""
        return ScrapedDocument(
            id=self._generate_id("apparmor-guide"),
            url="https://help.ubuntu.com/community/AppArmor",
            title="AppArmor Security Guide",
            content=content,
            source=self.get_source_name(),
            category="security",
            tags=["ubuntu", "apparmor", "security", "linux"],
            scraped_at=datetime.utcnow().isoformat(),
            metadata={"type": "guide", "priority": "medium"}
        )
    
    def _snap_ubuntu_guide(self) -> ScrapedDocument:
        """Snap on Ubuntu guide."""
        content = """# Snap Packages on Ubuntu

## Why Snap?

- **Universal**: Works across distributions
- **Sandboxed**: Isolated from system
- **Auto-updates**: Automatic security updates
- **Multiple versions**: Run different versions simultaneously

## Basic Commands

```bash
# Search for snaps
snap find firefox
snap search "web browser"

# Install
sudo snap install firefox
sudo snap install --classic code    # Classic confinement

# Remove
sudo snap remove firefox

# List installed
snap list

# Update
sudo snap refresh
sudo snap refresh firefox           # Specific snap
```

## Snap Channels

```bash
# Install from channel
sudo snap install firefox --channel=esr/stable
sudo snap install firefox --channel=beta

# Switch channel
sudo snap switch --channel=beta firefox
sudo snap refresh firefox

# List channels
snap info firefox
```

## Managing Snaps

```bash
# Disable/enable
sudo snap disable firefox
sudo snap enable firefox

# Hold updates
sudo snap refresh --hold firefox
sudo snap refresh --unhold firefox

# Revert to previous version
sudo snap revert firefox

# View changes
snap changes
snap change 123                     # Specific change
```

## Connections (Permissions)

```bash
# List connections
snap connections firefox

# Connect interface
sudo snap connect firefox:camera

# Disconnect interface
sudo snap disconnect firefox:camera

# List available interfaces
snap interfaces
```

## Snap Services

```bash
# List services
snap services

# Start/stop service
sudo snap start lxd
sudo snap stop lxd
sudo snap restart lxd

# Logs
snap logs lxd
snap logs -f lxd                    # Follow
```

## Storage

```bash
# Snap data locations
/snap/                              # Snap installations
/var/snap/                          # Snap data
~/snap/                             # User snap data

# Check snap disk usage
du -sh /var/lib/snapd/snaps/
```

## Configuration

```bash
# Get configuration
sudo snap get lxd

# Set configuration
sudo snap set lxd key=value

# Unset
sudo snap unset lxd key
```

## Classic vs Strict Confinement

| Type | Description |
|------|-------------|
| **strict** | Full sandboxing (default) |
| **classic** | Full system access (like apt) |
| **devmode** | Development mode |

```bash
# Check confinement
snap info firefox | grep confinement
```
"""
        return ScrapedDocument(
            id=self._generate_id("snap-ubuntu-guide"),
            url="https://snapcraft.io/docs",
            title="Snap Packages on Ubuntu",
            content=content,
            source=self.get_source_name(),
            category="packages",
            tags=["ubuntu", "snap", "packages", "linux"],
            scraped_at=datetime.utcnow().isoformat(),
            metadata={"type": "guide", "priority": "medium"}
        )
    
    def _server_setup_guide(self) -> ScrapedDocument:
        """Ubuntu Server setup guide."""
        content = """# Ubuntu Server Initial Setup Guide

## Post-Installation Checklist

### 1. Update System
```bash
sudo apt update && sudo apt upgrade -y
sudo reboot
```

### 2. Create Admin User
```bash
# Create user
sudo adduser admin

# Add to sudo group
sudo usermod -aG sudo admin

# Test sudo access
su - admin
sudo whoami
```

### 3. Configure SSH

```bash
# Install SSH server (usually pre-installed)
sudo apt install openssh-server

# Edit configuration
sudo nano /etc/ssh/sshd_config
```

Recommended settings:
```
Port 22
PermitRootLogin no
PasswordAuthentication no
PubkeyAuthentication yes
```

```bash
# Copy SSH key from local machine
ssh-copy-id admin@server-ip

# Restart SSH
sudo systemctl restart sshd
```

### 4. Configure Firewall

```bash
# Enable UFW
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow ssh
sudo ufw enable

# Add application rules as needed
sudo ufw allow 'Nginx Full'
```

### 5. Set Timezone

```bash
sudo timedatectl set-timezone America/New_York
timedatectl
```

### 6. Configure Automatic Updates

```bash
sudo apt install unattended-upgrades
sudo dpkg-reconfigure unattended-upgrades
```

### 7. Install Essential Tools

```bash
sudo apt install -y \
    curl \
    wget \
    git \
    htop \
    vim \
    tmux \
    net-tools \
    fail2ban
```

### 8. Configure Fail2ban

```bash
sudo cp /etc/fail2ban/jail.conf /etc/fail2ban/jail.local
sudo nano /etc/fail2ban/jail.local
```

```ini
[sshd]
enabled = true
port = ssh
filter = sshd
logpath = /var/log/auth.log
maxretry = 3
bantime = 3600
```

```bash
sudo systemctl enable fail2ban
sudo systemctl start fail2ban
```

### 9. Set Hostname

```bash
sudo hostnamectl set-hostname myserver
echo "127.0.1.1 myserver" | sudo tee -a /etc/hosts
```

### 10. Configure Swap (if needed)

```bash
# Create swap file
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile

# Make permanent
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

## Security Hardening Checklist

- [ ] Disable root login via SSH
- [ ] Use SSH key authentication only
- [ ] Configure UFW firewall
- [ ] Enable automatic security updates
- [ ] Install and configure fail2ban
- [ ] Set up log monitoring
- [ ] Configure AppArmor profiles
- [ ] Regular backup schedule
"""
        return ScrapedDocument(
            id=self._generate_id("server-setup-guide"),
            url="https://help.ubuntu.com/lts/serverguide/",
            title="Ubuntu Server Initial Setup Guide",
            content=content,
            source=self.get_source_name(),
            category="system_admin",
            tags=["ubuntu", "server", "setup", "security", "linux"],
            scraped_at=datetime.utcnow().isoformat(),
            metadata={"type": "guide", "priority": "high"}
        )
    
    def _troubleshooting_guide(self) -> ScrapedDocument:
        """Ubuntu troubleshooting guide."""
        content = """# Ubuntu Troubleshooting Guide

## Boot Issues

### GRUB Not Loading
```bash
# Boot from live USB, then:
sudo mount /dev/sdaX /mnt          # Your root partition
sudo mount /dev/sdaY /mnt/boot/efi # EFI partition if UEFI
sudo mount --bind /dev /mnt/dev
sudo mount --bind /proc /mnt/proc
sudo mount --bind /sys /mnt/sys

sudo chroot /mnt
grub-install /dev/sda
update-grub
exit
```

### Boot to Recovery Mode
1. Hold Shift during boot (BIOS) or press Esc (UEFI)
2. Select "Advanced options"
3. Select recovery mode

### View Boot Logs
```bash
journalctl -b                       # Current boot
journalctl -b -1                    # Previous boot
dmesg | less
```

## Package Issues

### Broken Packages
```bash
sudo apt --fix-broken install
sudo dpkg --configure -a
sudo apt update --fix-missing
```

### Dependency Hell
```bash
# Check what's broken
sudo apt-get check

# Try aptitude (smarter solver)
sudo apt install aptitude
sudo aptitude install problematic-package
```

### Locked Package Manager
```bash
# Check for running processes
ps aux | grep -i apt
ps aux | grep -i dpkg

# Kill if stuck
sudo killall apt apt-get dpkg

# Remove locks
sudo rm /var/lib/dpkg/lock-frontend
sudo rm /var/lib/apt/lists/lock
sudo rm /var/cache/apt/archives/lock
```

## Network Issues

### No Internet Connection
```bash
# Check interface status
ip link show
ip addr show

# Check connectivity
ping 8.8.8.8                        # IP connectivity
ping google.com                     # DNS resolution

# Restart networking
sudo systemctl restart NetworkManager
# Or for netplan:
sudo netplan apply
```

### DNS Not Working
```bash
# Check resolv.conf
cat /etc/resolv.conf

# Test DNS
nslookup google.com
dig google.com

# Temporary fix
echo "nameserver 8.8.8.8" | sudo tee /etc/resolv.conf
```

### Restart Network Completely
```bash
sudo systemctl restart systemd-networkd
sudo systemctl restart NetworkManager
sudo netplan apply
```

## Disk Issues

### Disk Full
```bash
# Find what's using space
df -h
du -sh /* 2>/dev/null | sort -h
du -sh /var/log/*

# Clean package cache
sudo apt clean
sudo apt autoremove

# Clean journal logs
sudo journalctl --vacuum-time=7d

# Find large files
find / -type f -size +100M 2>/dev/null
```

### Read-Only Filesystem
```bash
# Check disk health
sudo smartctl -a /dev/sda

# Check filesystem
sudo fsck /dev/sdaX

# Remount as read-write
sudo mount -o remount,rw /
```

## Service Issues

### Service Won't Start
```bash
# Check status
sudo systemctl status servicename

# View logs
journalctl -u servicename -n 50
journalctl -u servicename -f       # Follow

# Try manual start with debug
sudo /usr/sbin/servicename --debug
```

### List Failed Services
```bash
systemctl --failed
systemctl reset-failed
```

## GUI Issues

### Display Not Working
```bash
# Reconfigure display
sudo dpkg-reconfigure gdm3

# Check Xorg logs
cat /var/log/Xorg.0.log | grep EE

# Install driver
sudo ubuntu-drivers autoinstall
```

### Desktop Not Loading
```bash
# From TTY (Ctrl+Alt+F3):
sudo apt install --reinstall ubuntu-desktop
sudo systemctl restart gdm3
```

## Performance Issues

### High CPU Usage
```bash
top
htop
ps aux --sort=-%cpu | head
```

### High Memory Usage
```bash
free -h
ps aux --sort=-%mem | head
sudo sysctl vm.drop_caches=3       # Clear cache (safe)
```

### High Disk I/O
```bash
sudo iotop
sudo iostat -x 1
```
"""
        return ScrapedDocument(
            id=self._generate_id("ubuntu-troubleshooting"),
            url="synthetic://ubuntu-troubleshooting",
            title="Ubuntu Troubleshooting Guide",
            content=content,
            source=self.get_source_name(),
            category="troubleshooting",
            tags=["ubuntu", "troubleshooting", "debug", "linux"],
            scraped_at=datetime.utcnow().isoformat(),
            metadata={"type": "troubleshooting", "priority": "high"}
        )
    
    def _generate_id(self, name: str) -> str:
        """Generate document ID."""
        import hashlib
        return hashlib.md5(f"ubuntu-docs:{name}".encode()).hexdigest()[:16]


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Generate Ubuntu documentation")
    parser.add_argument("--output-dir", default="data/linux/ubuntu-docs")
    args = parser.parse_args()
    
    logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(name)s:%(message)s')
    
    config = ScraperConfig(output_dir=Path(args.output_dir))
    scraper = UbuntuDocsScraper(config)
    
    docs = scraper.scrape()
    scraper.save_documents(docs, "ubuntu_docs.jsonl")
