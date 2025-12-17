"""
Linux Filesystem Documentation Scraper.

Phase 27: RAG Coverage

Comprehensive filesystem guides covering:
- Disk management (fdisk, parted, lsblk)
- Filesystems (ext4, xfs, btrfs)
- LVM (Logical Volume Management)
- RAID configuration
- Mount options and fstab
- Disk troubleshooting
"""

import logging
from typing import List
from datetime import datetime
from pathlib import Path

from .base import BaseScraper, ScrapedDocument, ScraperConfig

logger = logging.getLogger('halbert')


class FilesystemDocsScraper(BaseScraper):
    """Generates comprehensive Linux filesystem documentation."""
    
    def __init__(self, config: ScraperConfig):
        super().__init__(config)
    
    def get_source_name(self) -> str:
        return "filesystem-docs"
    
    def scrape(self) -> List[ScrapedDocument]:
        """Generate filesystem documentation."""
        logger.info("Generating filesystem documentation...")
        
        documents = []
        documents.extend(self._generate_guides())
        
        logger.info(f"Total filesystem documents: {len(documents)}")
        return documents
    
    def _generate_guides(self) -> List[ScrapedDocument]:
        """Generate all filesystem guides."""
        guides = []
        
        guides.append(self._disk_management_guide())
        guides.append(self._lsblk_guide())
        guides.append(self._mount_fstab_guide())
        guides.append(self._lvm_guide())
        guides.append(self._raid_guide())
        guides.append(self._ext4_guide())
        guides.append(self._btrfs_guide())
        guides.append(self._troubleshooting_guide())
        
        return guides
    
    def _disk_management_guide(self) -> ScrapedDocument:
        """Disk partitioning guide."""
        content = """# Linux Disk Partitioning Guide

## View Disk Information

```bash
# List all block devices
lsblk
lsblk -f                         # With filesystem info
lsblk -o NAME,SIZE,TYPE,MOUNTPOINT,FSTYPE

# Disk details
sudo fdisk -l
sudo fdisk -l /dev/sda

# Partition info
sudo parted -l
cat /proc/partitions

# Disk usage
df -h
df -hT                           # With filesystem type
```

## fdisk (MBR Partitions)

```bash
# Start fdisk
sudo fdisk /dev/sdb

# Common commands within fdisk:
# m - help menu
# p - print partition table
# n - new partition
# d - delete partition
# t - change partition type
# w - write and exit
# q - quit without saving
```

### Create Partition with fdisk
```bash
sudo fdisk /dev/sdb
# n (new)
# p (primary) or e (extended)
# 1 (partition number)
# Enter (default first sector)
# +10G (size) or Enter (use all)
# w (write)
```

## parted (GPT and MBR)

```bash
# Interactive mode
sudo parted /dev/sdb

# Common commands:
# print - show partitions
# mklabel gpt - create GPT table
# mklabel msdos - create MBR table
# mkpart primary ext4 0% 100% - create partition
# rm 1 - remove partition 1
# quit

# Non-interactive
sudo parted /dev/sdb mklabel gpt
sudo parted /dev/sdb mkpart primary ext4 0% 50%
sudo parted /dev/sdb mkpart primary ext4 50% 100%
```

## gdisk (GPT Only)

```bash
sudo gdisk /dev/sdb

# Similar to fdisk but for GPT
# n - new partition
# d - delete partition
# p - print table
# w - write
```

## Create Filesystem

```bash
# ext4 (most common)
sudo mkfs.ext4 /dev/sdb1

# With label
sudo mkfs.ext4 -L mydisk /dev/sdb1

# XFS
sudo mkfs.xfs /dev/sdb1

# Btrfs
sudo mkfs.btrfs /dev/sdb1

# FAT32 (for USB drives)
sudo mkfs.vfat -F 32 /dev/sdb1

# exFAT
sudo mkfs.exfat /dev/sdb1

# Swap
sudo mkswap /dev/sdb2
sudo swapon /dev/sdb2
```

## Resize Partitions

```bash
# IMPORTANT: Backup data first!

# Resize with parted
sudo parted /dev/sdb
resizepart 1 20GB

# Resize filesystem after partition
sudo resize2fs /dev/sdb1        # ext4
sudo xfs_growfs /mount/point    # XFS (grow only)
```

## Partition Labels and UUIDs

```bash
# View UUIDs
blkid
lsblk -f

# Set label
sudo e2label /dev/sdb1 mylabel      # ext4
sudo xfs_admin -L mylabel /dev/sdb1 # XFS

# Change UUID
sudo tune2fs -U random /dev/sdb1
```
"""
        return ScrapedDocument(
            id=self._generate_id("disk-partitioning"),
            url="https://man7.org/linux/man-pages/man8/fdisk.8.html",
            title="Linux Disk Partitioning Guide",
            content=content,
            source=self.get_source_name(),
            category="storage",
            tags=["linux", "disk", "partition", "fdisk", "parted"],
            scraped_at=datetime.utcnow().isoformat(),
            metadata={"type": "guide", "priority": "high"}
        )
    
    def _lsblk_guide(self) -> ScrapedDocument:
        """lsblk and block device guide."""
        content = """# lsblk - List Block Devices

## Basic Usage

```bash
# Simple list
lsblk

# With filesystem info
lsblk -f

# All columns
lsblk -a

# Output as pairs
lsblk -P

# JSON output
lsblk -J
```

## Useful Column Combinations

```bash
# Storage overview
lsblk -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINT

# Disk health info
lsblk -o NAME,SIZE,ROTA,DISC-GRAN,MODEL

# Complete info
lsblk -o NAME,SIZE,TYPE,FSTYPE,LABEL,UUID,MOUNTPOINT

# For scripting
lsblk -rno NAME,SIZE,TYPE
```

## Available Columns

| Column | Description |
|--------|-------------|
| NAME | Device name |
| SIZE | Size of device |
| TYPE | Type (disk, part, lvm, raid) |
| FSTYPE | Filesystem type |
| MOUNTPOINT | Where mounted |
| UUID | Filesystem UUID |
| LABEL | Filesystem label |
| MODEL | Device model |
| SERIAL | Serial number |
| ROTA | Rotational (1=HDD, 0=SSD) |
| RO | Read-only |
| RM | Removable |
| HOTPLUG | Hotpluggable |

## Filter by Type

```bash
# Only disks
lsblk -d

# Exclude loop devices
lsblk -e 7

# Only specific device
lsblk /dev/sda
```

## Related Commands

```bash
# Block device attributes
sudo blkid
sudo blkid /dev/sda1

# Detailed disk info
sudo hdparm -I /dev/sda

# SMART info
sudo smartctl -a /dev/sda

# Device mapper
sudo dmsetup ls
```
"""
        return ScrapedDocument(
            id=self._generate_id("lsblk-guide"),
            url="https://man7.org/linux/man-pages/man8/lsblk.8.html",
            title="lsblk - List Block Devices",
            content=content,
            source=self.get_source_name(),
            category="storage",
            tags=["linux", "lsblk", "disk", "block-device"],
            scraped_at=datetime.utcnow().isoformat(),
            metadata={"type": "reference", "priority": "medium"}
        )
    
    def _mount_fstab_guide(self) -> ScrapedDocument:
        """Mount and fstab guide."""
        content = """# Linux Mount and fstab Guide

## mount Command

### Basic Mounting
```bash
# Mount device
sudo mount /dev/sdb1 /mnt/data

# Mount with filesystem type
sudo mount -t ext4 /dev/sdb1 /mnt/data

# Mount by UUID
sudo mount UUID=xxxx-xxxx /mnt/data

# Mount by label
sudo mount LABEL=mydisk /mnt/data

# Mount ISO
sudo mount -o loop image.iso /mnt/iso

# Mount Windows share (CIFS)
sudo mount -t cifs //server/share /mnt/share -o username=user
```

### Mount Options
```bash
# Read-only
sudo mount -o ro /dev/sdb1 /mnt

# Read-write (default)
sudo mount -o rw /dev/sdb1 /mnt

# No execute
sudo mount -o noexec /dev/sdb1 /mnt

# No setuid
sudo mount -o nosuid /dev/sdb1 /mnt

# Multiple options
sudo mount -o rw,noexec,nosuid /dev/sdb1 /mnt
```

### Remount
```bash
# Remount with different options
sudo mount -o remount,rw /mnt

# Remount read-only
sudo mount -o remount,ro /
```

## umount Command

```bash
# Basic unmount
sudo umount /mnt/data
sudo umount /dev/sdb1

# Force unmount (use carefully)
sudo umount -f /mnt/data

# Lazy unmount (detach now, cleanup later)
sudo umount -l /mnt/data

# Find what's using mount point
lsof +D /mnt/data
fuser -mv /mnt/data
```

## /etc/fstab

### Format
```
<device>  <mountpoint>  <fstype>  <options>  <dump>  <pass>
```

### Example fstab
```
# /etc/fstab

# Root filesystem
UUID=abc123-def456  /         ext4  defaults        0 1

# Home partition
UUID=789xyz-abc123  /home     ext4  defaults        0 2

# Data partition with options
UUID=data-uuid-here /data     ext4  defaults,noatime  0 2

# Swap
UUID=swap-uuid-here swap      swap  defaults        0 0

# NFS mount
server:/share       /mnt/nfs  nfs   defaults,_netdev  0 0

# CIFS/Samba mount
//server/share      /mnt/smb  cifs  credentials=/etc/samba/creds,uid=1000  0 0

# tmpfs (RAM disk)
tmpfs               /tmp      tmpfs defaults,noatime,mode=1777  0 0
```

### Common Options

| Option | Description |
|--------|-------------|
| `defaults` | rw, suid, dev, exec, auto, nouser, async |
| `auto` | Mount at boot |
| `noauto` | Don't mount at boot |
| `ro` | Read-only |
| `rw` | Read-write |
| `noexec` | No executable files |
| `nosuid` | Ignore setuid bits |
| `nodev` | No device files |
| `noatime` | Don't update access time |
| `nofail` | Don't fail boot if mount fails |
| `_netdev` | Wait for network before mounting |
| `user` | Allow users to mount |
| `x-systemd.automount` | Automount on access |

### Dump and Pass Fields

- **dump** (5th field): 0 = no backup, 1 = backup
- **pass** (6th field): 0 = no check, 1 = check first (root), 2 = check after root

## Testing fstab

```bash
# Test without rebooting
sudo mount -a

# Check specific entry
sudo mount /mnt/data

# Validate fstab syntax
sudo findmnt --verify
```

## Systemd Mount Units

```bash
# View mount units
systemctl list-units --type=mount

# fstab entries become mount units
# /mnt/data -> mnt-data.mount
systemctl status mnt-data.mount
```
"""
        return ScrapedDocument(
            id=self._generate_id("mount-fstab"),
            url="https://man7.org/linux/man-pages/man5/fstab.5.html",
            title="Linux Mount and fstab Guide",
            content=content,
            source=self.get_source_name(),
            category="storage",
            tags=["linux", "mount", "fstab", "filesystem"],
            scraped_at=datetime.utcnow().isoformat(),
            metadata={"type": "guide", "priority": "high"}
        )
    
    def _lvm_guide(self) -> ScrapedDocument:
        """LVM guide."""
        content = """# LVM (Logical Volume Management) Guide

## LVM Concepts

```
Physical Volumes (PV) → Volume Groups (VG) → Logical Volumes (LV)
     /dev/sda1              vg_data              lv_home
     /dev/sdb1                                   lv_var
```

## View LVM Configuration

```bash
# Physical volumes
sudo pvs
sudo pvdisplay

# Volume groups
sudo vgs
sudo vgdisplay

# Logical volumes
sudo lvs
sudo lvdisplay

# All LVM info
sudo lvm fullreport
```

## Create LVM Setup

### 1. Create Physical Volumes
```bash
# Initialize disk for LVM
sudo pvcreate /dev/sdb1
sudo pvcreate /dev/sdc1

# Verify
sudo pvs
```

### 2. Create Volume Group
```bash
# Create VG from PVs
sudo vgcreate vg_data /dev/sdb1 /dev/sdc1

# Verify
sudo vgs
```

### 3. Create Logical Volumes
```bash
# Fixed size
sudo lvcreate -L 50G -n lv_home vg_data

# Percentage of VG
sudo lvcreate -l 100%FREE -n lv_data vg_data

# Percentage of remaining space
sudo lvcreate -l 50%FREE -n lv_logs vg_data

# Verify
sudo lvs
```

### 4. Create Filesystem and Mount
```bash
# Create filesystem
sudo mkfs.ext4 /dev/vg_data/lv_home

# Mount
sudo mkdir /home
sudo mount /dev/vg_data/lv_home /home

# Add to fstab
echo '/dev/vg_data/lv_home /home ext4 defaults 0 2' | sudo tee -a /etc/fstab
```

## Extend Logical Volume

```bash
# Extend LV by size
sudo lvextend -L +10G /dev/vg_data/lv_home

# Extend to specific size
sudo lvextend -L 100G /dev/vg_data/lv_home

# Extend to fill VG
sudo lvextend -l +100%FREE /dev/vg_data/lv_home

# Extend filesystem (after lvextend)
sudo resize2fs /dev/vg_data/lv_home        # ext4
sudo xfs_growfs /home                       # XFS
```

### Extend in One Command
```bash
# LV + filesystem together
sudo lvextend -r -L +10G /dev/vg_data/lv_home
```

## Add Disk to Volume Group

```bash
# Create PV on new disk
sudo pvcreate /dev/sdd1

# Extend VG
sudo vgextend vg_data /dev/sdd1

# Now you can extend LVs with new space
sudo lvextend -r -l +100%FREE /dev/vg_data/lv_home
```

## Reduce Logical Volume

```bash
# WARNING: Backup first! Data loss possible!

# Unmount
sudo umount /home

# Check filesystem
sudo e2fsck -f /dev/vg_data/lv_home

# Reduce filesystem first
sudo resize2fs /dev/vg_data/lv_home 40G

# Reduce LV
sudo lvreduce -L 40G /dev/vg_data/lv_home

# Remount
sudo mount /home
```

## LVM Snapshots

```bash
# Create snapshot
sudo lvcreate -L 5G -s -n lv_home_snap /dev/vg_data/lv_home

# Mount snapshot (read-only)
sudo mount -o ro /dev/vg_data/lv_home_snap /mnt/snapshot

# Merge snapshot back (revert)
sudo lvconvert --merge /dev/vg_data/lv_home_snap

# Remove snapshot
sudo lvremove /dev/vg_data/lv_home_snap
```

## Remove LVM

```bash
# Unmount
sudo umount /home

# Remove LV
sudo lvremove /dev/vg_data/lv_home

# Remove VG
sudo vgremove vg_data

# Remove PV
sudo pvremove /dev/sdb1 /dev/sdc1
```
"""
        return ScrapedDocument(
            id=self._generate_id("lvm-guide"),
            url="https://man7.org/linux/man-pages/man8/lvm.8.html",
            title="LVM (Logical Volume Management) Guide",
            content=content,
            source=self.get_source_name(),
            category="storage",
            tags=["linux", "lvm", "storage", "disk", "volume"],
            scraped_at=datetime.utcnow().isoformat(),
            metadata={"type": "guide", "priority": "high"}
        )
    
    def _raid_guide(self) -> ScrapedDocument:
        """RAID configuration guide."""
        content = """# Linux Software RAID (mdadm) Guide

## RAID Levels Overview

| Level | Min Disks | Description | Use Case |
|-------|-----------|-------------|----------|
| RAID 0 | 2 | Striping, no redundancy | Performance |
| RAID 1 | 2 | Mirroring | Redundancy |
| RAID 5 | 3 | Striping + parity | Balance |
| RAID 6 | 4 | Striping + double parity | High redundancy |
| RAID 10 | 4 | Mirror + stripe | Performance + redundancy |

## View RAID Status

```bash
# Overview
cat /proc/mdstat

# Detailed info
sudo mdadm --detail /dev/md0

# Examine disk
sudo mdadm --examine /dev/sdb1
```

## Create RAID Array

### RAID 1 (Mirror)
```bash
# Create RAID 1
sudo mdadm --create /dev/md0 --level=1 --raid-devices=2 /dev/sdb1 /dev/sdc1

# Wait for sync
watch cat /proc/mdstat
```

### RAID 5
```bash
sudo mdadm --create /dev/md0 --level=5 --raid-devices=3 /dev/sdb1 /dev/sdc1 /dev/sdd1
```

### RAID 10
```bash
sudo mdadm --create /dev/md0 --level=10 --raid-devices=4 /dev/sdb1 /dev/sdc1 /dev/sdd1 /dev/sde1
```

### With Spare Disk
```bash
sudo mdadm --create /dev/md0 --level=5 --raid-devices=3 --spare-devices=1 /dev/sdb1 /dev/sdc1 /dev/sdd1 /dev/sde1
```

## Save Configuration

```bash
# Save config (IMPORTANT!)
sudo mdadm --detail --scan | sudo tee -a /etc/mdadm/mdadm.conf

# Update initramfs
sudo update-initramfs -u
```

## After Creating RAID

```bash
# Create filesystem
sudo mkfs.ext4 /dev/md0

# Mount
sudo mkdir /mnt/raid
sudo mount /dev/md0 /mnt/raid

# Add to fstab (use UUID)
sudo blkid /dev/md0
echo 'UUID=xxxx /mnt/raid ext4 defaults 0 2' | sudo tee -a /etc/fstab
```

## Managing RAID

### Add Disk
```bash
# Add as spare
sudo mdadm --add /dev/md0 /dev/sde1

# Grow array (after adding disk)
sudo mdadm --grow /dev/md0 --raid-devices=4
```

### Remove Disk
```bash
# Mark as failed
sudo mdadm --fail /dev/md0 /dev/sdc1

# Remove
sudo mdadm --remove /dev/md0 /dev/sdc1
```

### Replace Failed Disk
```bash
# Mark failed
sudo mdadm --fail /dev/md0 /dev/sdc1

# Remove
sudo mdadm --remove /dev/md0 /dev/sdc1

# Partition new disk same as old
sudo sfdisk -d /dev/sdb | sudo sfdisk /dev/sdc

# Add new disk
sudo mdadm --add /dev/md0 /dev/sdc1

# Watch rebuild
watch cat /proc/mdstat
```

## Stop and Destroy RAID

```bash
# Unmount
sudo umount /mnt/raid

# Stop array
sudo mdadm --stop /dev/md0

# Zero superblocks (destroy)
sudo mdadm --zero-superblock /dev/sdb1
sudo mdadm --zero-superblock /dev/sdc1
```

## Monitoring

```bash
# Email alerts
echo "MAILADDR your@email.com" | sudo tee -a /etc/mdadm/mdadm.conf

# Enable monitoring
sudo systemctl enable mdmonitor
sudo systemctl start mdmonitor
```
"""
        return ScrapedDocument(
            id=self._generate_id("raid-guide"),
            url="https://man7.org/linux/man-pages/man8/mdadm.8.html",
            title="Linux Software RAID (mdadm) Guide",
            content=content,
            source=self.get_source_name(),
            category="storage",
            tags=["linux", "raid", "mdadm", "storage", "redundancy"],
            scraped_at=datetime.utcnow().isoformat(),
            metadata={"type": "guide", "priority": "high"}
        )
    
    def _ext4_guide(self) -> ScrapedDocument:
        """ext4 filesystem guide."""
        content = """# ext4 Filesystem Guide

## Create ext4 Filesystem

```bash
# Basic
sudo mkfs.ext4 /dev/sdb1

# With label
sudo mkfs.ext4 -L mylabel /dev/sdb1

# With larger inode size (for extended attributes)
sudo mkfs.ext4 -I 256 /dev/sdb1

# Reserved blocks (default 5%)
sudo mkfs.ext4 -m 1 /dev/sdb1     # 1% reserved
```

## Filesystem Information

```bash
# Superblock info
sudo tune2fs -l /dev/sdb1

# Disk usage
df -h /mount/point

# Inode usage
df -i /mount/point

# Filesystem stats
sudo dumpe2fs -h /dev/sdb1
```

## Tune Filesystem

```bash
# Change label
sudo e2label /dev/sdb1 newlabel
sudo tune2fs -L newlabel /dev/sdb1

# Change reserved blocks
sudo tune2fs -m 2 /dev/sdb1       # 2%

# Change reserved for user
sudo tune2fs -r 10000 /dev/sdb1   # 10000 blocks

# Set mount count before check
sudo tune2fs -c 50 /dev/sdb1

# Set time between checks
sudo tune2fs -i 6m /dev/sdb1      # 6 months

# Disable checks (not recommended)
sudo tune2fs -c 0 -i 0 /dev/sdb1
```

## Check and Repair

```bash
# Check filesystem (must be unmounted)
sudo e2fsck /dev/sdb1

# Force check
sudo e2fsck -f /dev/sdb1

# Automatic repair
sudo e2fsck -p /dev/sdb1          # Preen (safe fixes)
sudo e2fsck -y /dev/sdb1          # Yes to all

# Check bad blocks
sudo e2fsck -c /dev/sdb1
```

## Resize Filesystem

```bash
# Grow to fill partition (online OK)
sudo resize2fs /dev/sdb1

# Grow to specific size
sudo resize2fs /dev/sdb1 100G

# Shrink (must be unmounted)
sudo umount /mnt/data
sudo e2fsck -f /dev/sdb1
sudo resize2fs /dev/sdb1 50G
```

## Mount Options

```bash
# Common mount options
sudo mount -o defaults,noatime /dev/sdb1 /mnt

# Recommended for SSDs
sudo mount -o defaults,noatime,discard /dev/sdb1 /mnt

# Journaling options
sudo mount -o data=journal /dev/sdb1 /mnt    # Safest
sudo mount -o data=ordered /dev/sdb1 /mnt    # Default
sudo mount -o data=writeback /dev/sdb1 /mnt  # Fastest
```

## Journal Management

```bash
# View journal status
sudo tune2fs -l /dev/sdb1 | grep -i journal

# Recreate journal (if corrupted)
sudo tune2fs -O ^has_journal /dev/sdb1
sudo tune2fs -j /dev/sdb1
```

## Extended Attributes

```bash
# List attributes
lsattr file.txt

# Set immutable (can't delete or modify)
sudo chattr +i file.txt

# Remove immutable
sudo chattr -i file.txt

# Append only
sudo chattr +a file.log

# Common attributes:
# i - immutable
# a - append only
# s - secure deletion
# u - undeletable
```
"""
        return ScrapedDocument(
            id=self._generate_id("ext4-guide"),
            url="https://man7.org/linux/man-pages/man5/ext4.5.html",
            title="ext4 Filesystem Guide",
            content=content,
            source=self.get_source_name(),
            category="storage",
            tags=["linux", "ext4", "filesystem", "storage"],
            scraped_at=datetime.utcnow().isoformat(),
            metadata={"type": "guide", "priority": "high"}
        )
    
    def _btrfs_guide(self) -> ScrapedDocument:
        """Btrfs filesystem guide."""
        content = """# Btrfs Filesystem Guide

## Why Btrfs?

- **Snapshots**: Instant, space-efficient snapshots
- **Compression**: Transparent compression
- **Checksums**: Data integrity verification
- **RAID**: Built-in RAID support
- **Subvolumes**: Flexible data organization

## Create Btrfs Filesystem

```bash
# Single disk
sudo mkfs.btrfs /dev/sdb1

# With label
sudo mkfs.btrfs -L mydata /dev/sdb1

# Multiple disks (RAID)
sudo mkfs.btrfs -d raid1 -m raid1 /dev/sdb /dev/sdc

# RAID levels: single, raid0, raid1, raid10, raid5, raid6
```

## View Btrfs Info

```bash
# Filesystem info
sudo btrfs filesystem show
sudo btrfs filesystem show /mnt

# Disk usage
sudo btrfs filesystem df /mnt
sudo btrfs filesystem usage /mnt

# Device stats
sudo btrfs device stats /mnt
```

## Subvolumes

```bash
# Create subvolume
sudo btrfs subvolume create /mnt/data

# List subvolumes
sudo btrfs subvolume list /mnt

# Delete subvolume
sudo btrfs subvolume delete /mnt/data

# Mount specific subvolume
sudo mount -o subvol=@home /dev/sdb1 /home
sudo mount -o subvolid=256 /dev/sdb1 /home
```

### Common Subvolume Layout
```
/mnt                    # Top-level
├── @                   # Root subvolume
├── @home               # Home subvolume
├── @snapshots          # Snapshots
└── @var                # Var subvolume
```

## Snapshots

```bash
# Create snapshot
sudo btrfs subvolume snapshot /mnt/data /mnt/snapshots/data-2025-01-15

# Read-only snapshot
sudo btrfs subvolume snapshot -r /mnt/data /mnt/snapshots/data-2025-01-15

# List snapshots
sudo btrfs subvolume list -s /mnt

# Delete snapshot
sudo btrfs subvolume delete /mnt/snapshots/data-2025-01-15
```

## Compression

```bash
# Mount with compression
sudo mount -o compress=zstd /dev/sdb1 /mnt
sudo mount -o compress=lzo /dev/sdb1 /mnt
sudo mount -o compress=zlib /dev/sdb1 /mnt

# Defragment and compress existing files
sudo btrfs filesystem defragment -r -v -czstd /mnt

# Check compression ratio
sudo compsize /mnt
```

## Scrub (Data Integrity)

```bash
# Start scrub
sudo btrfs scrub start /mnt

# Check status
sudo btrfs scrub status /mnt

# Cancel scrub
sudo btrfs scrub cancel /mnt

# Schedule with cron
# 0 3 * * 0 /usr/bin/btrfs scrub start /mnt
```

## Balance (Redistribute Data)

```bash
# Full balance (can be slow)
sudo btrfs balance start /mnt

# Balance only unallocated
sudo btrfs balance start -dusage=50 /mnt

# Check status
sudo btrfs balance status /mnt

# Cancel
sudo btrfs balance cancel /mnt
```

## Add/Remove Devices

```bash
# Add device
sudo btrfs device add /dev/sdc /mnt
sudo btrfs balance start /mnt

# Remove device
sudo btrfs device remove /dev/sdc /mnt

# Replace device
sudo btrfs replace start /dev/sdb /dev/sdc /mnt
```

## Repair

```bash
# Check filesystem (unmounted)
sudo btrfs check /dev/sdb1

# Repair (use with caution)
sudo btrfs check --repair /dev/sdb1

# Rescue mode
sudo btrfs rescue super-recover /dev/sdb1
```

## Quotas

```bash
# Enable quotas
sudo btrfs quota enable /mnt

# Show quotas
sudo btrfs qgroup show /mnt

# Set limit
sudo btrfs qgroup limit 10G /mnt/data
```
"""
        return ScrapedDocument(
            id=self._generate_id("btrfs-guide"),
            url="https://btrfs.readthedocs.io/",
            title="Btrfs Filesystem Guide",
            content=content,
            source=self.get_source_name(),
            category="storage",
            tags=["linux", "btrfs", "filesystem", "storage", "snapshots"],
            scraped_at=datetime.utcnow().isoformat(),
            metadata={"type": "guide", "priority": "high"}
        )
    
    def _troubleshooting_guide(self) -> ScrapedDocument:
        """Filesystem troubleshooting guide."""
        content = """# Filesystem Troubleshooting Guide

## Disk Full

```bash
# Check usage
df -h

# Find large files
sudo find / -type f -size +100M 2>/dev/null | head -20
du -sh /* 2>/dev/null | sort -h | tail -20

# Find large directories
sudo du -h --max-depth=1 / 2>/dev/null | sort -h

# Inode exhaustion
df -i
sudo find / -xdev -type f | cut -d "/" -f 2 | sort | uniq -c | sort -n
```

### Quick Cleanup
```bash
# Package cache
sudo apt clean                    # Debian/Ubuntu
sudo dnf clean all               # Fedora/RHEL

# Journal logs
sudo journalctl --vacuum-time=7d

# Old kernels (Ubuntu)
sudo apt autoremove

# Temp files
sudo rm -rf /tmp/*
sudo rm -rf /var/tmp/*
```

## Read-Only Filesystem

```bash
# Check for errors
dmesg | tail -50
journalctl -k | grep -i "error\|readonly\|read-only"

# Check mount status
mount | grep "ro,"

# Remount read-write
sudo mount -o remount,rw /

# If that fails, filesystem is damaged
# Boot to recovery, then:
sudo fsck -y /dev/sda1
```

## Filesystem Corruption

### ext4
```bash
# Unmount first
sudo umount /dev/sda1

# Check and repair
sudo e2fsck -f /dev/sda1
sudo e2fsck -y /dev/sda1       # Auto-yes

# If can't unmount root
# Boot with: init=/bin/bash
# Then: fsck -y /dev/sda1
```

### XFS
```bash
sudo xfs_repair /dev/sda1

# If log is dirty
sudo xfs_repair -L /dev/sda1   # Zeros log (data loss possible)
```

### Btrfs
```bash
sudo btrfs check /dev/sda1
sudo btrfs check --repair /dev/sda1

# Rescue
sudo btrfs rescue super-recover /dev/sda1
```

## Can't Unmount (Device Busy)

```bash
# Find what's using it
lsof +D /mnt/data
fuser -mv /mnt/data

# Kill processes
sudo fuser -k /mnt/data

# Lazy unmount (last resort)
sudo umount -l /mnt/data
```

## Bad Blocks

```bash
# Check for bad blocks (non-destructive)
sudo badblocks -v /dev/sdb

# Mark bad blocks in ext4
sudo e2fsck -c /dev/sdb1

# SMART test (better)
sudo smartctl -t short /dev/sdb
sudo smartctl -a /dev/sdb | grep -i "reallocated\|pending\|uncorrect"
```

## LVM Issues

```bash
# Scan for LVM
sudo pvscan
sudo vgscan
sudo lvscan

# Activate volume group
sudo vgchange -ay vg_name

# Check LVM metadata
sudo vgck vg_name

# Repair LVM metadata
sudo vgcfgrestore vg_name
```

## RAID Recovery

```bash
# Check RAID status
cat /proc/mdstat
sudo mdadm --detail /dev/md0

# Assemble array
sudo mdadm --assemble --scan

# Force assemble degraded array
sudo mdadm --assemble --force /dev/md0 /dev/sdb1 /dev/sdc1

# Add replacement disk
sudo mdadm --add /dev/md0 /dev/sdd1
```

## Recovery Tools

```bash
# Data recovery (read damaged disk)
sudo ddrescue /dev/sdb /dev/sdc rescue.log

# File recovery
sudo testdisk /dev/sdb
sudo photorec /dev/sdb

# Mount corrupted filesystem read-only
sudo mount -o ro,noload /dev/sda1 /mnt
```
"""
        return ScrapedDocument(
            id=self._generate_id("filesystem-troubleshooting"),
            url="synthetic://filesystem-troubleshooting",
            title="Filesystem Troubleshooting Guide",
            content=content,
            source=self.get_source_name(),
            category="troubleshooting",
            tags=["linux", "filesystem", "troubleshooting", "repair"],
            scraped_at=datetime.utcnow().isoformat(),
            metadata={"type": "troubleshooting", "priority": "high"}
        )
    
    def _generate_id(self, name: str) -> str:
        """Generate document ID."""
        import hashlib
        return hashlib.md5(f"filesystem-docs:{name}".encode()).hexdigest()[:16]


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Generate filesystem documentation")
    parser.add_argument("--output-dir", default="data/linux/filesystem-docs")
    args = parser.parse_args()
    
    logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(name)s:%(message)s')
    
    config = ScraperConfig(output_dir=Path(args.output_dir))
    scraper = FilesystemDocsScraper(config)
    
    docs = scraper.scrape()
    scraper.save_documents(docs, "filesystem_docs.jsonl")
