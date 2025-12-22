"""
Linux RAG Trigger Keywords

Comprehensive keyword lists for triggering RAG context injection by discovery type.
Based on Phase 36 research: docs/Phase36_system-prompt-research/keywords.md
"""

from typing import Dict, Set

# ═══════════════════════════════════════════════════════════════════════════════
# BACKUP KEYWORDS (~60)
# ═══════════════════════════════════════════════════════════════════════════════
BACKUP_KEYWORDS: Set[str] = {
    # Core concepts
    'backup', 'restore', 'recovery', 'snapshot', 'rollback', 'revert',
    'incremental', 'differential', 'archive', 'retention', 'disaster recovery',
    
    # Tools & commands
    'btrbk', 'timeshift', 'rsync', 'borg', 'borgbackup', 'restic', 'duplicity',
    'rclone', 'syncthing', 'deja-dup', 'backintime', 'snapper', 'zfs-auto-snapshot',
    'rdiff-backup', 'duplicati', 'kopia', 'vorta', 'pika-backup',
    
    # Filesystem snapshots
    'subvolume', '@home', '@root', '@snapshots', 'btrfs snapshot', 'zfs snapshot',
    'lvm snapshot', 'previous version',
    
    # Config & paths
    '/etc/btrbk', 'btrbk.conf', '/etc/snapper', '/etc/timeshift',
    '.borgmatic', 'borg repo', '/var/backup',
    
    # Common questions
    'last backup', 'when backed up', 'backup history', 'backup schedule',
    'restore from', 'recover file', 'backup status', 'backup failed',
}

# ═══════════════════════════════════════════════════════════════════════════════
# STORAGE KEYWORDS (~80)
# ═══════════════════════════════════════════════════════════════════════════════
STORAGE_KEYWORDS: Set[str] = {
    # Filesystems
    'btrfs', 'zfs', 'ext4', 'xfs', 'bcachefs', 'f2fs', 'ntfs', 'exfat', 'fat32',
    'reiserfs', 'jfs', 'nilfs2', 'overlay', 'squashfs', 'tmpfs', 'ramfs',
    'filesystem', 'mkfs',
    
    # Disk & partitions
    'disk', 'drive', 'partition', 'volume', 'block device',
    'nvme', 'ssd', 'hdd', 'sata', 'scsi', 'usb drive',
    'gpt', 'mbr', 'partition table', 'fdisk', 'gdisk', 'parted',
    'lsblk', 'blkid', '/dev/sd', '/dev/nvme', '/dev/vd',
    
    # RAID & LVM
    'raid', 'raid0', 'raid1', 'raid5', 'raid6', 'raid10', 'raidz',
    'mdadm', '/dev/md', 'degraded', 'rebuild',
    'lvm', 'physical volume', 'volume group', 'logical volume',
    'lvextend', 'lvreduce', 'pvmove', 'vgextend',
    
    # Mount & paths
    'mount', 'umount', 'fstab', '/etc/fstab', 'mountpoint',
    '/home', '/root', '/var', '/tmp', '/opt', '/mnt', '/media',
    'bind mount', 'loop device', 'nfs mount', 'cifs mount',
    
    # Storage health
    'smart', 'smartctl', 'disk health', 'bad sectors', 'reallocated',
    'wear level', 'trim', 'fstrim', 'scrub', 'balance',
    'disk full', 'no space', 'quota',
    
    # Tools
    'gparted', 'gnome-disks', 'btrfs-progs', 'zfsutils',
    'cryptsetup', 'luks', 'dm-crypt', 'veracrypt',
}

# ═══════════════════════════════════════════════════════════════════════════════
# NETWORK KEYWORDS (~70)
# ═══════════════════════════════════════════════════════════════════════════════
NETWORK_KEYWORDS: Set[str] = {
    # Interfaces & config
    'network', 'interface', 'ethernet', 'wifi', 'wireless', 'wlan',
    'ip address', 'subnet', 'gateway', 'dns', 'dhcp', 'static ip',
    'networkmanager', 'netplan', '/etc/network', 'ifconfig', 'ip addr',
    'bridge', 'bond', 'vlan', 'tap', 'tun',
    
    # Connectivity
    'ping', 'traceroute', 'connection', 'disconnect', 'timeout',
    'internet', 'online', 'offline', 'latency', 'packet loss',
    'firewall', 'iptables', 'nftables', 'ufw', 'firewalld',
    
    # Services
    'ssh', 'sshd', 'openssh', 'sftp', 'scp',
    'ftp', 'http', 'https', 'nginx', 'apache', 'caddy',
    'dns server', 'bind', 'dnsmasq', 'resolved', '/etc/resolv.conf',
    'vpn', 'wireguard', 'openvpn', 'tailscale',
    
    # Sharing
    'samba', 'smb', 'cifs', 'nfs', 'network share',
    'avahi', 'mdns', 'zeroconf',
    
    # Diagnostics
    'netstat', 'ss', 'nmap', 'tcpdump', 'wireshark',
    'curl', 'wget', 'nc', 'netcat', 'dig', 'nslookup',
}

# ═══════════════════════════════════════════════════════════════════════════════
# SERVICE KEYWORDS (~60)
# ═══════════════════════════════════════════════════════════════════════════════
SERVICE_KEYWORDS: Set[str] = {
    # Systemd
    'systemd', 'systemctl', 'service', 'unit', 'daemon',
    'start service', 'stop service', 'restart service', 'reload',
    'enable', 'disable', 'status', 'failed', 'active', 'inactive', 'masked',
    '.service', '.timer', '.socket', '.mount', '.path',
    'journalctl', 'journal', 'syslog',
    
    # Init systems
    'init', 'sysvinit', 'upstart', 'openrc', 'runit',
    '/etc/init.d', 'rc.local', 'runlevel',
    
    # Process management
    'process', 'pid', 'kill', 'pkill', 'killall',
    'top', 'htop', 'btop', 'ps aux', 'pgrep',
    'cron', 'crontab', 'anacron', 'at',
    'supervisor', 'pm2',
    
    # Common services
    'nginx', 'apache', 'httpd', 'mysql', 'mariadb', 'postgresql', 'postgres',
    'redis', 'memcached', 'mongodb', 'elasticsearch',
    'docker', 'containerd', 'podman', 'kubelet',
    'sshd', 'cups', 'bluetooth', 'pulseaudio', 'pipewire',
}

# ═══════════════════════════════════════════════════════════════════════════════
# SECURITY KEYWORDS (~55)
# ═══════════════════════════════════════════════════════════════════════════════
SECURITY_KEYWORDS: Set[str] = {
    # Authentication
    'password', 'passwd', 'shadow', 'authentication', 'pam',
    'sudo', 'su', 'root', 'privilege', 'permission denied',
    'ssh key', 'authorized_keys', 'known_hosts',
    '2fa', 'totp', 'yubikey', 'fido',
    
    # Access control
    'chmod', 'chown', 'acl', 'setfacl', 'getfacl',
    'selinux', 'apparmor', 'seccomp', 'capabilities',
    'user', 'group', 'uid', 'gid', '/etc/passwd', '/etc/group',
    
    # Encryption
    'encrypt', 'decrypt', 'gpg', 'pgp', 'openssl',
    'luks', 'dm-crypt', 'ecryptfs', 'gocryptfs',
    'certificate', 'cert', 'ssl', 'tls',
    
    # Firewall
    'firewall', 'iptables', 'nftables', 'ufw', 'firewalld',
    'port', 'allow', 'deny', 'block', 'rule',
    
    # Auditing
    'audit', 'auditd', 'auditctl', 'ausearch',
    'fail2ban', 'intrusion', 'breach', 'vulnerability',
    'cve', 'security update', 'patch',
}

# ═══════════════════════════════════════════════════════════════════════════════
# HARDWARE KEYWORDS (~65)
# ═══════════════════════════════════════════════════════════════════════════════
HARDWARE_KEYWORDS: Set[str] = {
    # CPU
    'cpu', 'processor', 'core', 'thread', 'frequency',
    'intel', 'amd', 'arm', 'risc-v',
    'temperature', 'thermal', 'throttle', 'governor',
    'lscpu', '/proc/cpuinfo', 'turbo',
    
    # Memory
    'ram', 'memory', 'swap', 'dimm', 'ddr4', 'ddr5',
    'free memory', 'available', 'cached', 'buffer',
    'oom', 'out of memory', 'memory pressure',
    '/proc/meminfo', 'vmstat', 'swapon',
    
    # GPU
    'gpu', 'graphics', 'nvidia', 'amd gpu', 'intel gpu',
    'cuda', 'rocm', 'opencl', 'vulkan',
    'driver', 'mesa', 'xorg', 'wayland',
    'nvidia-smi', 'rocm-smi', 'glxinfo',
    
    # Sensors
    'sensor', 'fan', 'voltage',
    'lm-sensors', 'sensors', 'hwmon',
    'acpi', 'power', 'battery', 'charging',
    
    # Peripherals
    'usb', 'pci', 'pcie', 'thunderbolt',
    'keyboard', 'mouse', 'monitor', 'display',
    'audio', 'sound', 'bluetooth',
    'lsusb', 'lspci', 'xinput',
}

# ═══════════════════════════════════════════════════════════════════════════════
# PACKAGE KEYWORDS (~50)
# ═══════════════════════════════════════════════════════════════════════════════
PACKAGE_KEYWORDS: Set[str] = {
    # Package managers
    'apt', 'apt-get', 'dpkg', 'deb', 'debian',
    'dnf', 'yum', 'rpm', 'fedora', 'rhel',
    'pacman', 'aur', 'arch', 'manjaro',
    'zypper', 'suse', 'opensuse',
    'nix', 'guix', 'emerge', 'portage',
    
    # Operations
    'install', 'uninstall', 'remove', 'purge',
    'update', 'upgrade', 'dist-upgrade',
    'search package', 'list packages', 'package info',
    'dependency', 'depends', 'conflicts',
    
    # Universal packages
    'flatpak', 'snap', 'snapd', 'appimage',
    'flathub', 'snap store',
    '/var/lib/flatpak', '/var/lib/snapd',
    
    # Build
    'make', 'cmake', 'meson', 'ninja',
    'gcc', 'clang', 'rustc', 'cargo',
    'pip', 'npm', 'yarn', 'gem',
}

# ═══════════════════════════════════════════════════════════════════════════════
# CONTAINER KEYWORDS (~45)
# ═══════════════════════════════════════════════════════════════════════════════
CONTAINER_KEYWORDS: Set[str] = {
    # Docker
    'docker', 'dockerfile', 'docker-compose',
    'container', 'image', 'docker volume', 'docker network',
    'docker pull', 'docker push', 'docker build', 'docker run', 'docker exec',
    'docker ps', 'docker images',
    
    # Podman & others
    'podman', 'buildah', 'skopeo',
    'lxc', 'lxd', 'systemd-nspawn',
    'incus', 'kata', 'gvisor',
    
    # Orchestration
    'kubernetes', 'k8s', 'kubectl', 'helm',
    'pod', 'deployment', 'service', 'ingress',
    'minikube', 'k3s', 'microk8s', 'kind',
    
    # Registry
    'registry', 'docker hub', 'gcr', 'ecr', 'acr',
    'docker.io', 'ghcr.io', 'quay.io',
}

# ═══════════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

def get_matching_categories(query: str) -> list[str]:
    """
    Get all discovery categories that match keywords in the query.
    
    Args:
        query: User's chat message (will be lowercased)
        
    Returns:
        List of matching category names (e.g., ['backup', 'storage'])
    """
    query_lower = query.lower()
    matches = []
    
    keyword_map = {
        'backup': BACKUP_KEYWORDS,
        'storage': STORAGE_KEYWORDS,
        'network': NETWORK_KEYWORDS,
        'service': SERVICE_KEYWORDS,
        'security': SECURITY_KEYWORDS,
        'hardware': HARDWARE_KEYWORDS,
        'package': PACKAGE_KEYWORDS,
        'container': CONTAINER_KEYWORDS,
    }
    
    for category, keywords in keyword_map.items():
        if any(kw in query_lower for kw in keywords):
            matches.append(category)
    
    return matches


def get_keywords_for_category(category: str) -> Set[str]:
    """Get keyword set for a specific category."""
    return {
        'backup': BACKUP_KEYWORDS,
        'storage': STORAGE_KEYWORDS,
        'network': NETWORK_KEYWORDS,
        'service': SERVICE_KEYWORDS,
        'security': SECURITY_KEYWORDS,
        'hardware': HARDWARE_KEYWORDS,
        'package': PACKAGE_KEYWORDS,
        'container': CONTAINER_KEYWORDS,
    }.get(category, set())


# Total keyword count
TOTAL_KEYWORDS = sum(len(kw) for kw in [
    BACKUP_KEYWORDS, STORAGE_KEYWORDS, NETWORK_KEYWORDS, SERVICE_KEYWORDS,
    SECURITY_KEYWORDS, HARDWARE_KEYWORDS, PACKAGE_KEYWORDS, CONTAINER_KEYWORDS
])

if __name__ == "__main__":
    print(f"Total keywords defined: {TOTAL_KEYWORDS}")
    for cat, kws in [
        ("Backup", BACKUP_KEYWORDS),
        ("Storage", STORAGE_KEYWORDS),
        ("Network", NETWORK_KEYWORDS),
        ("Service", SERVICE_KEYWORDS),
        ("Security", SECURITY_KEYWORDS),
        ("Hardware", HARDWARE_KEYWORDS),
        ("Package", PACKAGE_KEYWORDS),
        ("Container", CONTAINER_KEYWORDS),
    ]:
        print(f"  {cat}: {len(kws)} keywords")
