"""
Service Scanner - Discover systemd services and Docker containers.

Implements Phase 9 research from docs/Phase9/deep-dives/05-services-daemons.md

Discovers:
- systemd services (running, failed, enabled)
- Docker containers (if installed)
- Key system services
"""

from __future__ import annotations
from typing import List, Optional
import json

from .base import BaseScanner
from ..schema import (
    Discovery, 
    DiscoveryType, 
    DiscoverySeverity,
    DiscoveryAction,
    service_discovery,
)


class ServiceScanner(BaseScanner):
    """
    Scanner for system services.
    
    Discovers:
    - systemd units
    - Docker containers
    - Failed/problematic services
    """
    
    @property
    def discovery_type(self) -> DiscoveryType:
        return DiscoveryType.SERVICE
    
    def scan(self) -> List[Discovery]:
        """Scan system for services."""
        discoveries = []
        
        discoveries.extend(self._scan_systemd())
        discoveries.extend(self._scan_docker())
        
        self.logger.info(f"Found {len(discoveries)} services")
        return discoveries
    
    def _scan_systemd(self) -> List[Discovery]:
        """Scan systemd services."""
        discoveries = []
        
        # Get all services with their status
        code, stdout, _ = self.run_command([
            "systemctl", "list-units", "--type=service", 
            "--all", "--no-pager", "--plain", "--no-legend"
        ])
        
        if code != 0:
            return discoveries
        
        for line in stdout.strip().splitlines():
            parts = line.split()
            if len(parts) < 4:
                continue
            
            unit = parts[0]
            load_state = parts[1]
            active_state = parts[2]
            sub_state = parts[3]
            description = ' '.join(parts[4:]) if len(parts) > 4 else ""
            
            # Skip template units and socket units
            if '@' in unit or not unit.endswith('.service'):
                continue
            
            name = unit.replace('.service', '')
            
            # Determine severity based on state
            if active_state == 'failed':
                severity = DiscoverySeverity.CRITICAL
                status = 'Failed'
            elif active_state == 'active' and sub_state == 'running':
                severity = DiscoverySeverity.SUCCESS
                status = 'Running'
            elif active_state == 'active' and sub_state == 'exited':
                # Oneshot services that completed successfully
                severity = DiscoverySeverity.INFO
                status = 'Completed'
            elif active_state == 'active':
                severity = DiscoverySeverity.SUCCESS
                status = sub_state.title()
            elif active_state == 'inactive':
                severity = DiscoverySeverity.INFO
                status = 'Stopped'
            else:
                severity = DiscoverySeverity.WARNING
                status = active_state.title()
            
            # Get more details for important services
            memory_mb = None
            cpu_percent = None
            
            if active_state == 'active':
                mem_info = self._get_service_memory(unit)
                if mem_info:
                    memory_mb = mem_info
            
            # Categorize and get metadata
            category = categorize_service(name)
            is_critical = is_critical_service(name)
            install_source = get_installation_source(name, unit)
            context_hint = generate_context_hint(name, description, category, status)
            
            discoveries.append(service_discovery(
                name=name,
                description=description or f"Systemd service: {name}",
                status=status,
                service_type="systemd",
                enabled=load_state == 'loaded',
                memory_mb=memory_mb,
                severity=severity,
                unit_file=unit,
                active_state=active_state,
                sub_state=sub_state,
                # New metadata fields
                category=category,
                is_critical=is_critical,
                install_source=install_source,
                context_hint=context_hint,
            ))
        
        return discoveries
    
    def _get_service_memory(self, unit: str) -> Optional[float]:
        """Get memory usage for a service."""
        code, stdout, _ = self.run_command([
            "systemctl", "show", unit, "--property=MemoryCurrent"
        ])
        
        if code == 0:
            for line in stdout.splitlines():
                if line.startswith("MemoryCurrent="):
                    try:
                        bytes_val = int(line.split("=")[1])
                        if bytes_val > 0 and bytes_val < 2**63:  # Valid value
                            return bytes_val / (1024 * 1024)  # Convert to MB
                    except (ValueError, IndexError):
                        pass
        return None
    
    def _scan_docker(self) -> List[Discovery]:
        """Scan Docker containers."""
        discoveries = []
        
        if not self.command_exists("docker"):
            return discoveries
        
        # Check if docker daemon is running
        code, _, _ = self.run_command(["docker", "info"], timeout=5)
        if code != 0:
            return discoveries
        
        # List containers
        code, stdout, _ = self.run_command([
            "docker", "ps", "-a", "--format", 
            '{"name":"{{.Names}}","status":"{{.Status}}","image":"{{.Image}}","ports":"{{.Ports}}"}'
        ])
        
        if code != 0:
            return discoveries
        
        for line in stdout.strip().splitlines():
            try:
                container = json.loads(line)
                name = container.get('name', 'unknown')
                status_str = container.get('status', '')
                image = container.get('image', '')
                
                # Parse status
                if status_str.startswith('Up'):
                    status = 'Running'
                    severity = DiscoverySeverity.SUCCESS
                elif status_str.startswith('Exited'):
                    if '(0)' in status_str:
                        status = 'Exited (OK)'
                        severity = DiscoverySeverity.INFO
                    else:
                        status = 'Exited (Error)'
                        severity = DiscoverySeverity.WARNING
                else:
                    status = status_str.split()[0] if status_str else 'Unknown'
                    severity = DiscoverySeverity.INFO
                
                discoveries.append(service_discovery(
                    name=f"docker-{name}",
                    description=f"Docker container: {image}",
                    status=status,
                    service_type="docker",
                    enabled=True,
                    severity=severity,
                    container_name=name,
                    image=image,
                    ports=container.get('ports', ''),
                ))
                
            except json.JSONDecodeError:
                continue
        
        return discoveries


# Key services to highlight
KEY_SERVICES = [
    'nginx', 'apache2', 'httpd',
    'mysql', 'mariadb', 'postgresql', 'redis', 'mongodb',
    'docker', 'containerd',
    'sshd', 'ssh',
    'NetworkManager', 'systemd-networkd',
    'cups', 'bluetooth',
    'gdm', 'sddm', 'lightdm',
]

# Service category mappings for filtering
SERVICE_CATEGORIES = {
    # Audio services
    'audio': [
        'alsa', 'pulseaudio', 'pipewire', 'pulse', 'sound', 'audio',
        'jack', 'bluetooth-audio', 'wireplumber', 'speech',
    ],
    # Network services
    'network': [
        'NetworkManager', 'systemd-networkd', 'wpa_supplicant', 'avahi',
        'dhcp', 'dns', 'bind', 'dnsmasq', 'resolvconf', 'resolved',
        'openvpn', 'wireguard', 'samba', 'smb', 'nmb', 'nfs',
        'netfilter', 'network', 'modem', 'ppp', 'wlan', 'wifi',
        'hostapd', 'iwd', 'connman', 'netplan', 'ifup', 'networking',
    ],
    # Storage services
    'storage': [
        'lvm', 'btrfs', 'zfs', 'mdadm', 'raid', 'fstrim', 'smartd', 'smart',
        'udisks', 'mount', 'autofs', 'cifs', 'gvfs', 'fuse', 'bcache',
        'dm-', 'device-mapper', 'multipath', 'iscsi', 'nvme', 'scsi',
        'blk-availability', 'cryptsetup', 'luks', 'disk', 'partition',
    ],
    # Desktop/Display services
    'desktop': [
        'gdm', 'sddm', 'lightdm', 'xdm', 'display-manager', 'x11', 'xorg',
        'wayland', 'gnome', 'kde', 'plasma', 'xfce', 'colord', 'geoclue',
        'tracker', 'evolution', 'goa', 'at-spi', 'ibus', 'fcitx',
        'xdg', 'desktop', 'session', 'seat', 'graphical',
    ],
    # Security services
    'security': [
        'apparmor', 'selinux', 'firewall', 'ufw', 'iptables', 'fail2ban',
        'clamav', 'rkhunter', 'aide', 'auditd', 'policykit', 'polkit',
        'gpg', 'pam', 'sssd', 'krb5', 'kerberos', 'opensc', 'tpm',
        'secureboot', 'verity', 'integrity', 'keyring', 'secret',
        'certbot', 'ssl', 'cert', 'ca-certificates',
    ],
    # Print services
    'print': [
        'cups', 'cupsd', 'printer', 'lpd', 'print', 'ipp', 'hplip',
    ],
    # Virtualization/Container services
    'virtualization': [
        'docker', 'containerd', 'podman', 'lxc', 'lxd', 'libvirt',
        'qemu', 'kvm', 'virtualbox', 'vmware', 'vagrant', 'multipass',
        'vbox', 'hyperv',
    ],
    # Database services
    'database': [
        'mysql', 'mariadb', 'postgresql', 'postgres', 'redis', 'mongodb',
        'memcached', 'sqlite', 'couchdb', 'elasticsearch', 'influxdb',
    ],
    # Web services
    'web': [
        'nginx', 'apache', 'httpd', 'lighttpd', 'caddy', 'traefik',
        'haproxy', 'php-fpm', 'gunicorn', 'uwsgi', 'tomcat', 'jetty',
    ],
    # Package management
    'packages': [
        'apt', 'dpkg', 'snap', 'snapd', 'flatpak', 'packagekit', 'dnf',
        'yum', 'pacman', 'zypper', 'apk', 'unattended-upgrades', 'update',
    ],
    # Power management  
    'power': [
        'acpid', 'thermald', 'cpupower', 'tlp', 'power', 'suspend',
        'hibernate', 'sleep', 'upower', 'battery', 'thermal', 'fan',
        'powertop', 'laptop-mode', 'pm-utils',
    ],
    # Logging & monitoring
    'logging': [
        'rsyslog', 'syslog', 'journald', 'journal', 'log', 'auditd',
        'logrotate', 'sysstat', 'collectd', 'telegraf', 'prometheus',
        'grafana', 'zabbix', 'nagios', 'monit',
    ],
    # Time & scheduling
    'time': [
        'chrony', 'ntp', 'ntpd', 'timesyncd', 'timesync', 'cron',
        'anacron', 'atd', 'timer', 'systemd-time',
    ],
    # Hardware & firmware
    'hardware': [
        'udev', 'fwupd', 'firmware', 'bios', 'efi', 'modules', 'kmod',
        'nvidia', 'amd', 'intel', 'gpu', 'video', 'drm', 'acpi',
        'usb', 'pci', 'i2c', 'hwmon', 'sensors', 'lm-sensors',
        'irqbalance', 'mcelog', 'rasdaemon',
    ],
    # User session & login
    'session': [
        'logind', 'login', 'pam', 'accounts', 'user', 'passwd', 'shadow',
        'getty', 'agetty', 'console', 'tty', 'motd', 'issue', 'sshd', 'ssh',
    ],
    # Cloud & provisioning
    'cloud': [
        'cloud-init', 'cloud-config', 'cloud-final', 'waagent', 'azure',
        'ec2', 'gce', 'digitalocean', 'linode', 'vultr', 'hetzner',
        'terraform', 'ansible', 'puppet', 'chef', 'salt',
    ],
    # Backup services
    'backup': [
        'backup', 'restic', 'borg', 'rsync', 'duplicity', 'bacula',
        'amanda', 'bareos', 'timeshift', 'snapper', 'btrbk', 'bcachefs',
    ],
    # Bluetooth
    'bluetooth': [
        'bluetooth', 'bluez', 'blueman', 'obex',
    ],
    # Message bus & IPC
    'messaging': [
        'dbus', 'd-bus', 'dbus-daemon', 'dbus-broker', 'rabbitmq', 
        'activemq', 'kafka', 'mosquitto', 'mqtt',
    ],
    # Error reporting & diagnostics
    'diagnostics': [
        'apport', 'whoopsie', 'kerneloops', 'abrt', 'crash', 'coredump',
        'dump', 'debug', 'trace', 'strace', 'perf',
    ],
}

# Critical system services (should not be stopped)
CRITICAL_SERVICES = {
    'systemd-journald', 'systemd-logind', 'systemd-udevd', 'dbus',
    'NetworkManager', 'systemd-networkd', 'systemd-resolved',
    'gdm', 'sddm', 'lightdm',  # Display managers
    'polkit', 'accounts-daemon',
    'udisks2', 'upower',
}

# Services typically installed by the OS (not user)
SYSTEM_INSTALLED = {
    'systemd', 'dbus', 'rsyslog', 'syslog', 'journald', 'logind',
    'udev', 'acpid', 'cron', 'anacron', 'atd', 'polkit',
    'NetworkManager', 'systemd-networkd', 'wpa_supplicant',
    'gdm', 'sddm', 'lightdm', 'xdm',
    'alsa', 'pulseaudio', 'pipewire',
    'cups', 'bluetooth', 'avahi',
    'udisks', 'upower', 'colord', 'geoclue',
    'snapd', 'packagekit', 'fwupd',
}


def categorize_service(name: str) -> str:
    """Determine the category of a service based on its name."""
    name_lower = name.lower()
    
    for category, patterns in SERVICE_CATEGORIES.items():
        for pattern in patterns:
            if pattern.lower() in name_lower:
                return category
    
    return 'other'


def is_critical_service(name: str) -> bool:
    """Check if a service is critical to system operation."""
    name_lower = name.lower()
    for critical in CRITICAL_SERVICES:
        if critical.lower() in name_lower or name_lower in critical.lower():
            return True
    return False


def get_installation_source(name: str, unit_file: Optional[str] = None) -> str:
    """Determine if a service was installed by the system or user."""
    name_lower = name.lower()
    
    # Check against known system services
    for sys_svc in SYSTEM_INSTALLED:
        if sys_svc.lower() in name_lower:
            return 'system'
    
    # Check unit file path if available
    if unit_file:
        if '/usr/lib/' in unit_file or '/lib/systemd/' in unit_file:
            return 'system'
        elif '/etc/systemd/user/' in unit_file or '/.local/' in unit_file:
            return 'user'
    
    return 'unknown'


def generate_context_hint(name: str, description: str, category: str, status: str) -> str:
    """Generate a brief context hint about what the service does."""
    hints = {
        'audio': 'Manages audio/sound hardware and routing',
        'network': 'Handles network connectivity and communication',
        'storage': 'Manages disk storage, filesystems, or data',
        'desktop': 'Part of the desktop environment and user interface',
        'security': 'Provides security, authentication, or access control',
        'print': 'Manages printing and print queues',
        'virtualization': 'Provides containerization or virtual machines',
        'database': 'Database server or data storage engine',
        'web': 'Web server or HTTP-related service',
        'packages': 'Manages software packages and updates',
        'power': 'Handles power management and energy saving',
        'logging': 'Collects and manages system logs',
        'time': 'Manages time synchronization and scheduling',
        'hardware': 'Interfaces with hardware and firmware',
        'session': 'Manages user sessions and login',
        'cloud': 'Cloud provisioning and configuration',
        'backup': 'Handles data backup and recovery',
        'bluetooth': 'Manages Bluetooth connectivity',
        'messaging': 'Provides inter-process communication',
        'diagnostics': 'Error reporting and system diagnostics',
    }
    
    base_hint = hints.get(category, 'System service')
    
    # Add status context
    if status == 'Running':
        return f"{base_hint}. Currently active."
    elif status == 'Failed':
        return f"{base_hint}. ⚠️ Service has failed and may need attention."
    elif status == 'Stopped':
        return f"{base_hint}. Not currently running."
    
    return base_hint
