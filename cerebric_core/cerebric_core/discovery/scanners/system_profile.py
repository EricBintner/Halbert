"""
Comprehensive System Profile Scanner (Phase 14: Self-Awareness)

Gathers everything about this system that Cerebric should know:
- OS and kernel details
- Hardware (CPU, RAM, GPU, disks)
- Network configuration
- Installed software and packages
- Users and security
- Containers and virtualization
- And more...

This creates the "system memory" that makes Cerebric self-aware.
"""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
import logging

logger = logging.getLogger('cerebric.discovery.system_profile')


class SystemProfiler:
    """
    Comprehensive system profiler that gathers all discoverable information.
    
    Supports multiple scan levels:
    - DEEP: Full scan of everything (first boot, manual trigger)
    - QUICK: Fast scan of frequently-changing items (app startup)
    - PAGE: Targeted scan for specific categories (page rescan)
    
    Results are cached and can be persisted to disk for quick startup.
    """
    
    def __init__(self):
        self.profile: Dict[str, Any] = {}
        self.scan_time: Optional[datetime] = None
        self.quick_scan_time: Optional[datetime] = None
    
    def run_command(self, cmd: List[str], timeout: int = 10) -> tuple[int, str, str]:
        """Run a command and return (exit_code, stdout, stderr)."""
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            return result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return -1, "", "timeout"
        except FileNotFoundError:
            return -1, "", "command not found"
        except Exception as e:
            return -1, "", str(e)
    
    def scan_all(self) -> Dict[str, Any]:
        """Run all scanners and return complete system profile."""
        logger.info("Starting comprehensive system profile scan...")
        
        self.profile = {
            "scan_time": datetime.now().isoformat(),
            "hostname": socket.gethostname(),
        }
        
        # Run all scanners
        self.profile["os"] = self._scan_os()
        self.profile["hardware"] = self._scan_hardware()
        self.profile["network"] = self._scan_network()
        self.profile["storage"] = self._scan_storage_summary()
        self.profile["services"] = self._scan_services_summary()
        self.profile["packages"] = self._scan_packages()
        self.profile["users"] = self._scan_users()
        self.profile["security"] = self._scan_security()
        self.profile["containers"] = self._scan_containers()
        self.profile["virtualization"] = self._scan_virtualization()
        self.profile["scheduled_tasks"] = self._scan_scheduled_tasks()
        self.profile["kernel"] = self._scan_kernel()
        self.profile["boot"] = self._scan_boot()
        self.profile["development"] = self._scan_development()
        self.profile["desktop"] = self._scan_desktop()
        
        self.scan_time = datetime.now()
        self.quick_scan_time = datetime.now()
        logger.info(f"System profile scan complete: {len(self.profile)} categories")
        
        return self.profile
    
    def quick_scan(self) -> Dict[str, Any]:
        """
        Fast scan of frequently-changing items only.
        
        Used on app startup. Takes 2-5 seconds.
        Updates the existing profile in-place.
        """
        logger.info("Starting quick system scan...")
        
        # Load existing profile if not in memory
        if not self.profile:
            self.load_profile()
        
        # If still no profile, do a deep scan instead
        if not self.profile:
            logger.info("No existing profile, running deep scan instead")
            return self.scan_all()
        
        # Update only frequently-changing categories
        self.profile["quick_scan_time"] = datetime.now().isoformat()
        
        # Services (status changes constantly)
        self.profile["services"] = self._scan_services_summary()
        
        # Storage usage (changes constantly)
        self.profile["storage"] = self._scan_storage_summary()
        
        # Network state (IPs can change)
        self.profile["network"] = self._scan_network()
        
        # Containers (start/stop frequently)
        self.profile["containers"] = self._scan_containers()
        
        # Update uptime
        code, stdout, _ = self.run_command(["uptime", "-p"])
        if code == 0:
            self.profile.setdefault("os", {})["uptime"] = stdout.strip()
        
        # Memory (changes constantly)
        hw = self.profile.get("hardware", {})
        try:
            with open('/proc/meminfo') as f:
                for line in f:
                    if line.startswith('MemAvailable:'):
                        kb = int(line.split()[1])
                        hw.setdefault("memory", {})["available_gb"] = round(kb / 1024 / 1024, 1)
        except Exception:
            pass
        
        self.quick_scan_time = datetime.now()
        logger.info("Quick scan complete")
        
        # Save updated profile
        self.save_profile()
        
        return self.profile
    
    def scan_category(self, category: str) -> Dict[str, Any]:
        """
        Scan a specific category (for page rescans).
        
        Args:
            category: One of 'storage', 'services', 'network', 'packages',
                     'security', 'containers', 'users'
        
        Returns:
            Updated data for that category
        """
        logger.info(f"Scanning category: {category}")
        
        scanners = {
            'storage': self._scan_storage_summary,
            'services': self._scan_services_summary,
            'network': self._scan_network,
            'packages': self._scan_packages,
            'security': self._scan_security,
            'containers': self._scan_containers,
            'users': self._scan_users,
            'hardware': self._scan_hardware,
            'os': self._scan_os,
            'kernel': self._scan_kernel,
            'boot': self._scan_boot,
            'development': self._scan_development,
            'desktop': self._scan_desktop,
            'scheduled_tasks': self._scan_scheduled_tasks,
            'virtualization': self._scan_virtualization,
        }
        
        if category not in scanners:
            raise ValueError(f"Unknown category: {category}")
        
        result = scanners[category]()
        
        # Update profile in memory
        if self.profile:
            self.profile[category] = result
            self.save_profile()
        
        return result
    
    # ─────────────────────────────────────────────────────────────────────────
    # OS & Distribution
    # ─────────────────────────────────────────────────────────────────────────
    
    def _scan_os(self) -> Dict[str, Any]:
        """Scan OS and distribution information."""
        result = {
            "type": "linux",
            "distro": {},
            "kernel": "",
            "arch": "",
            "uptime": "",
        }
        
        # Parse /etc/os-release
        os_release = Path("/etc/os-release")
        if os_release.exists():
            try:
                with open(os_release) as f:
                    for line in f:
                        if '=' in line:
                            key, value = line.strip().split('=', 1)
                            value = value.strip('"').strip("'")
                            result["distro"][key.lower()] = value
            except Exception as e:
                logger.warning(f"Failed to parse os-release: {e}")
        
        # Determine package manager
        distro_id = result["distro"].get("id", "").lower()
        id_like = result["distro"].get("id_like", "").lower()
        
        if distro_id in ("ubuntu", "debian", "linuxmint", "pop") or "debian" in id_like:
            result["package_manager"] = "apt"
            result["family"] = "debian"
        elif distro_id in ("arch", "manjaro", "endeavouros") or "arch" in id_like:
            result["package_manager"] = "pacman"
            result["family"] = "arch"
        elif distro_id in ("fedora", "rhel", "centos", "rocky", "alma"):
            result["package_manager"] = "dnf"
            result["family"] = "rhel"
        elif distro_id in ("opensuse", "sles"):
            result["package_manager"] = "zypper"
            result["family"] = "suse"
        else:
            result["package_manager"] = "unknown"
            result["family"] = distro_id
        
        # Kernel version
        code, stdout, _ = self.run_command(["uname", "-r"])
        if code == 0:
            result["kernel"] = stdout.strip()
        
        # Architecture
        code, stdout, _ = self.run_command(["uname", "-m"])
        if code == 0:
            result["arch"] = stdout.strip()
        
        # Uptime
        code, stdout, _ = self.run_command(["uptime", "-p"])
        if code == 0:
            result["uptime"] = stdout.strip()
        
        return result
    
    # ─────────────────────────────────────────────────────────────────────────
    # Hardware
    # ─────────────────────────────────────────────────────────────────────────
    
    def _scan_hardware(self) -> Dict[str, Any]:
        """Scan hardware information."""
        result = {
            "cpu": {},
            "memory": {},
            "gpu": [],
            "motherboard": {},
            "usb_devices": [],
        }
        
        # CPU info from lscpu
        code, stdout, _ = self.run_command(["lscpu"])
        if code == 0:
            for line in stdout.split('\n'):
                if ':' in line:
                    key, value = line.split(':', 1)
                    key = key.strip().lower().replace(' ', '_')
                    value = value.strip()
                    if key in ('model_name', 'cpu(s)', 'thread(s)_per_core', 
                               'core(s)_per_socket', 'socket(s)', 'cpu_max_mhz'):
                        result["cpu"][key] = value
        
        # Memory from /proc/meminfo
        try:
            with open('/proc/meminfo') as f:
                for line in f:
                    if line.startswith('MemTotal:'):
                        kb = int(line.split()[1])
                        result["memory"]["total_gb"] = round(kb / 1024 / 1024, 1)
                    elif line.startswith('MemAvailable:'):
                        kb = int(line.split()[1])
                        result["memory"]["available_gb"] = round(kb / 1024 / 1024, 1)
                    elif line.startswith('SwapTotal:'):
                        kb = int(line.split()[1])
                        result["memory"]["swap_gb"] = round(kb / 1024 / 1024, 1)
        except Exception:
            pass
        
        # GPU from lspci
        code, stdout, _ = self.run_command(["lspci"])
        if code == 0:
            for line in stdout.split('\n'):
                if 'VGA' in line or '3D controller' in line or 'Display controller' in line:
                    # Extract GPU name
                    match = re.search(r':\s+(.+)$', line)
                    if match:
                        result["gpu"].append(match.group(1).strip())
        
        # Also check for NVIDIA specifically
        code, stdout, _ = self.run_command(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"])
        if code == 0 and stdout.strip():
            result["nvidia_gpu"] = stdout.strip().split('\n')
        
        # USB devices (summary)
        code, stdout, _ = self.run_command(["lsusb"])
        if code == 0:
            for line in stdout.split('\n'):
                if line.strip():
                    # Extract device description
                    match = re.search(r'ID \w+:\w+ (.+)$', line)
                    if match:
                        result["usb_devices"].append(match.group(1).strip())
        
        return result
    
    # ─────────────────────────────────────────────────────────────────────────
    # Network
    # ─────────────────────────────────────────────────────────────────────────
    
    def _scan_network(self) -> Dict[str, Any]:
        """Scan network configuration."""
        result = {
            "interfaces": [],
            "dns": [],
            "hostname": socket.gethostname(),
            "fqdn": socket.getfqdn(),
            "routes": [],
        }
        
        # Network interfaces with ip addr
        code, stdout, _ = self.run_command(["ip", "-j", "addr"])
        if code == 0:
            try:
                interfaces = json.loads(stdout)
                for iface in interfaces:
                    if iface.get("ifname") == "lo":
                        continue  # Skip loopback
                    
                    iface_info = {
                        "name": iface.get("ifname"),
                        "state": iface.get("operstate", "unknown"),
                        "mac": iface.get("address"),
                        "ipv4": [],
                        "ipv6": [],
                    }
                    
                    for addr_info in iface.get("addr_info", []):
                        if addr_info.get("family") == "inet":
                            iface_info["ipv4"].append(f"{addr_info['local']}/{addr_info.get('prefixlen', '')}")
                        elif addr_info.get("family") == "inet6":
                            iface_info["ipv6"].append(addr_info.get("local", ""))
                    
                    result["interfaces"].append(iface_info)
            except json.JSONDecodeError:
                pass
        
        # DNS servers
        code, stdout, _ = self.run_command(["resolvectl", "status"])
        if code == 0:
            for line in stdout.split('\n'):
                if 'DNS Servers:' in line:
                    servers = line.split(':', 1)[1].strip()
                    result["dns"].extend(servers.split())
        else:
            # Fallback to /etc/resolv.conf
            try:
                with open('/etc/resolv.conf') as f:
                    for line in f:
                        if line.startswith('nameserver'):
                            result["dns"].append(line.split()[1])
            except Exception:
                pass
        
        # Default gateway
        code, stdout, _ = self.run_command(["ip", "route", "show", "default"])
        if code == 0 and stdout.strip():
            match = re.search(r'via (\S+)', stdout)
            if match:
                result["default_gateway"] = match.group(1)
        
        return result
    
    # ─────────────────────────────────────────────────────────────────────────
    # Storage (Summary - detailed scan is in storage.py)
    # ─────────────────────────────────────────────────────────────────────────
    
    def _scan_storage_summary(self) -> Dict[str, Any]:
        """Get storage summary (detailed scan is separate)."""
        result = {
            "filesystems": [],
            "total_capacity_tb": 0,
            "used_tb": 0,
            "disk_count": 0,
        }
        
        # Get filesystem summary from df
        code, stdout, _ = self.run_command(["df", "-h", "--output=source,fstype,size,used,avail,pcent,target"])
        if code == 0:
            lines = stdout.strip().split('\n')[1:]  # Skip header
            for line in lines:
                parts = line.split()
                if len(parts) >= 7 and not parts[0].startswith('tmpfs'):
                    result["filesystems"].append({
                        "device": parts[0],
                        "fstype": parts[1],
                        "size": parts[2],
                        "used": parts[3],
                        "avail": parts[4],
                        "use_percent": parts[5],
                        "mountpoint": parts[6],
                    })
        
        # Count physical disks
        code, stdout, _ = self.run_command(["lsblk", "-d", "-o", "NAME,TYPE,SIZE"])
        if code == 0:
            for line in stdout.split('\n')[1:]:
                if 'disk' in line:
                    result["disk_count"] += 1
        
        # Check for special filesystems
        result["has_btrfs"] = any(fs.get("fstype") == "btrfs" for fs in result["filesystems"])
        result["has_zfs"] = any(fs.get("fstype") == "zfs" for fs in result["filesystems"])
        result["has_bcachefs"] = any(fs.get("fstype") == "bcachefs" for fs in result["filesystems"])
        result["has_lvm"] = Path("/dev/mapper").exists()
        result["has_raid"] = Path("/dev/md0").exists() or any(
            fs.get("device", "").startswith("/dev/md") for fs in result["filesystems"]
        )
        
        return result
    
    # ─────────────────────────────────────────────────────────────────────────
    # Services
    # ─────────────────────────────────────────────────────────────────────────
    
    def _scan_services_summary(self) -> Dict[str, Any]:
        """Get services summary."""
        result = {
            "running_count": 0,
            "failed_count": 0,
            "enabled_count": 0,
            "notable_services": [],
        }
        
        # Notable services to track
        notable = [
            'docker', 'podman', 'containerd',  # Containers
            'sshd', 'ssh',  # Remote access
            'nginx', 'apache2', 'httpd', 'caddy',  # Web servers
            'postgresql', 'mysql', 'mariadb', 'mongodb', 'redis',  # Databases
            'smbd', 'nmbd', 'nfs-server',  # File sharing
            'cups',  # Printing
            'fail2ban', 'ufw', 'firewalld',  # Security
            'cron', 'anacron',  # Scheduling
            'tailscaled',  # VPN
            'syncthing', 'restic', 'borg',  # Backup/sync
        ]
        
        # Count services
        code, stdout, _ = self.run_command(["systemctl", "list-units", "--type=service", "--no-pager", "--no-legend"])
        if code == 0:
            for line in stdout.split('\n'):
                if not line.strip():
                    continue
                parts = line.split()
                if len(parts) >= 4:
                    service_name = parts[0].replace('.service', '')
                    state = parts[3] if len(parts) > 3 else ''
                    
                    if state == 'running':
                        result["running_count"] += 1
                    elif state == 'failed':
                        result["failed_count"] += 1
                    
                    # Check if notable
                    for notable_svc in notable:
                        if notable_svc in service_name.lower():
                            result["notable_services"].append({
                                "name": service_name,
                                "state": state,
                            })
                            break
        
        # Count enabled services
        code, stdout, _ = self.run_command(["systemctl", "list-unit-files", "--type=service", "--state=enabled", "--no-pager", "--no-legend"])
        if code == 0:
            result["enabled_count"] = len([l for l in stdout.split('\n') if l.strip()])
        
        return result
    
    # ─────────────────────────────────────────────────────────────────────────
    # Packages
    # ─────────────────────────────────────────────────────────────────────────
    
    def _scan_packages(self) -> Dict[str, Any]:
        """Scan installed packages (summary + notable)."""
        result = {
            "total_count": 0,
            "package_manager": "",
            "notable_packages": [],
            "recently_updated": [],
        }
        
        # Notable packages to track
        notable = [
            # Development
            'python3', 'nodejs', 'npm', 'go', 'rust', 'gcc', 'make', 'cmake', 'git',
            # Containers
            'docker-ce', 'docker.io', 'podman', 'containerd',
            # Databases
            'postgresql', 'mysql-server', 'mariadb-server', 'mongodb', 'redis-server',
            # Web
            'nginx', 'apache2', 'caddy',
            # Virtualization
            'qemu-kvm', 'libvirt', 'virtualbox',
            # Media
            'ffmpeg', 'vlc',
            # Backup
            'restic', 'borg', 'rsync', 'timeshift',
            # System
            'htop', 'neofetch', 'tmux', 'vim', 'neovim', 'zsh',
        ]
        
        # Try apt (Debian/Ubuntu)
        code, stdout, _ = self.run_command(["dpkg-query", "-f", "${Package}\n", "-W"], timeout=30)
        if code == 0:
            result["package_manager"] = "apt"
            packages = stdout.strip().split('\n')
            result["total_count"] = len(packages)
            
            # Check for notable packages
            for pkg in packages:
                for notable_pkg in notable:
                    if notable_pkg == pkg or pkg.startswith(notable_pkg + '-'):
                        result["notable_packages"].append(pkg)
                        break
            
            # Get recently installed/updated (last 10)
            code2, stdout2, _ = self.run_command([
                "grep", "install", "/var/log/dpkg.log"
            ])
            if code2 == 0:
                lines = stdout2.strip().split('\n')[-10:]
                for line in lines:
                    parts = line.split()
                    if len(parts) >= 4:
                        result["recently_updated"].append({
                            "date": f"{parts[0]} {parts[1]}",
                            "action": parts[2],
                            "package": parts[3].split(':')[0],
                        })
        else:
            # Try pacman (Arch)
            code, stdout, _ = self.run_command(["pacman", "-Q"])
            if code == 0:
                result["package_manager"] = "pacman"
                result["total_count"] = len(stdout.strip().split('\n'))
            else:
                # Try rpm (RHEL/Fedora)
                code, stdout, _ = self.run_command(["rpm", "-qa"])
                if code == 0:
                    result["package_manager"] = "rpm"
                    result["total_count"] = len(stdout.strip().split('\n'))
        
        return result
    
    # ─────────────────────────────────────────────────────────────────────────
    # Users
    # ─────────────────────────────────────────────────────────────────────────
    
    def _scan_users(self) -> Dict[str, Any]:
        """Scan user accounts."""
        result = {
            "current_user": os.environ.get('USER', 'unknown'),
            "sudo_users": [],
            "human_users": [],
            "logged_in": [],
        }
        
        # Get human users (UID >= 1000, has shell)
        try:
            with open('/etc/passwd') as f:
                for line in f:
                    parts = line.strip().split(':')
                    if len(parts) >= 7:
                        username, _, uid_str, _, _, home, shell = parts[:7]
                        try:
                            uid = int(uid_str)
                        except ValueError:
                            continue
                        
                        # Human users typically have UID >= 1000 and a real shell
                        if uid >= 1000 and not shell.endswith('nologin') and not shell.endswith('false'):
                            result["human_users"].append({
                                "username": username,
                                "uid": uid,
                                "home": home,
                                "shell": shell,
                            })
        except Exception:
            pass
        
        # Get sudo users (members of sudo/wheel group)
        try:
            with open('/etc/group') as f:
                for line in f:
                    parts = line.strip().split(':')
                    if len(parts) >= 4:
                        group_name = parts[0]
                        members = parts[3].split(',') if parts[3] else []
                        
                        if group_name in ('sudo', 'wheel', 'admin'):
                            result["sudo_users"].extend(members)
        except Exception:
            pass
        
        # Get logged in users
        code, stdout, _ = self.run_command(["who"])
        if code == 0:
            for line in stdout.split('\n'):
                if line.strip():
                    parts = line.split()
                    if parts:
                        result["logged_in"].append(parts[0])
        
        result["sudo_users"] = list(set(result["sudo_users"]))  # Dedupe
        
        return result
    
    # ─────────────────────────────────────────────────────────────────────────
    # Security
    # ─────────────────────────────────────────────────────────────────────────
    
    def _scan_security(self) -> Dict[str, Any]:
        """Scan security configuration."""
        result = {
            "firewall": None,
            "selinux": None,
            "apparmor": None,
            "fail2ban": False,
            "ssh_config": {},
            "updates_available": 0,
        }
        
        # Check firewall status
        code, stdout, _ = self.run_command(["ufw", "status"])
        if code == 0:
            result["firewall"] = {
                "type": "ufw",
                "status": "active" if "Status: active" in stdout else "inactive",
            }
        else:
            code, stdout, _ = self.run_command(["firewall-cmd", "--state"])
            if code == 0:
                result["firewall"] = {
                    "type": "firewalld",
                    "status": stdout.strip(),
                }
            else:
                # Check iptables
                code, stdout, _ = self.run_command(["iptables", "-L", "-n"])
                if code == 0:
                    rules_count = len([l for l in stdout.split('\n') if l.strip() and not l.startswith('Chain') and not l.startswith('target')])
                    result["firewall"] = {
                        "type": "iptables",
                        "rules_count": rules_count,
                    }
        
        # Check SELinux
        code, stdout, _ = self.run_command(["getenforce"])
        if code == 0:
            result["selinux"] = stdout.strip()
        
        # Check AppArmor
        code, stdout, _ = self.run_command(["aa-status", "--enabled"])
        if code == 0:
            result["apparmor"] = "enabled"
            # Get profile count
            code2, stdout2, _ = self.run_command(["aa-status"])
            if code2 == 0:
                match = re.search(r'(\d+) profiles are loaded', stdout2)
                if match:
                    result["apparmor_profiles"] = int(match.group(1))
        
        # Check fail2ban
        code, _, _ = self.run_command(["systemctl", "is-active", "fail2ban"])
        result["fail2ban"] = code == 0
        
        # SSH config highlights
        ssh_config = Path("/etc/ssh/sshd_config")
        if ssh_config.exists():
            try:
                with open(ssh_config) as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith('#') or not line:
                            continue
                        if line.startswith('PasswordAuthentication'):
                            result["ssh_config"]["password_auth"] = 'yes' in line.lower()
                        elif line.startswith('PermitRootLogin'):
                            result["ssh_config"]["root_login"] = line.split()[1]
                        elif line.startswith('Port'):
                            result["ssh_config"]["port"] = line.split()[1]
            except Exception:
                pass
        
        # Check for available updates (apt)
        code, stdout, _ = self.run_command(["apt", "list", "--upgradable"], timeout=30)
        if code == 0:
            result["updates_available"] = len([l for l in stdout.split('\n') if 'upgradable' in l])
        
        return result
    
    # ─────────────────────────────────────────────────────────────────────────
    # Containers
    # ─────────────────────────────────────────────────────────────────────────
    
    def _scan_containers(self) -> Dict[str, Any]:
        """Scan container runtimes and containers."""
        result = {
            "docker": None,
            "podman": None,
            "lxc": None,
            "containers": [],
        }
        
        # Docker
        code, stdout, _ = self.run_command(["docker", "info", "--format", "{{.Containers}}"])
        if code == 0:
            result["docker"] = {
                "installed": True,
                "container_count": int(stdout.strip()) if stdout.strip().isdigit() else 0,
            }
            
            # Get running containers
            code2, stdout2, _ = self.run_command(["docker", "ps", "--format", "{{.Names}}\t{{.Image}}\t{{.Status}}"])
            if code2 == 0:
                for line in stdout2.strip().split('\n'):
                    if line:
                        parts = line.split('\t')
                        if len(parts) >= 3:
                            result["containers"].append({
                                "runtime": "docker",
                                "name": parts[0],
                                "image": parts[1],
                                "status": parts[2],
                            })
        
        # Podman
        code, stdout, _ = self.run_command(["podman", "ps", "-a", "--format", "{{.Names}}\t{{.Image}}\t{{.Status}}"])
        if code == 0:
            result["podman"] = {"installed": True}
            for line in stdout.strip().split('\n'):
                if line:
                    parts = line.split('\t')
                    if len(parts) >= 3:
                        result["containers"].append({
                            "runtime": "podman",
                            "name": parts[0],
                            "image": parts[1],
                            "status": parts[2],
                        })
        
        # LXC/LXD
        code, stdout, _ = self.run_command(["lxc", "list", "--format", "csv"])
        if code == 0:
            result["lxc"] = {"installed": True}
            for line in stdout.strip().split('\n'):
                if line:
                    parts = line.split(',')
                    if parts:
                        result["containers"].append({
                            "runtime": "lxc",
                            "name": parts[0],
                            "status": parts[1] if len(parts) > 1 else "unknown",
                        })
        
        return result
    
    # ─────────────────────────────────────────────────────────────────────────
    # Virtualization
    # ─────────────────────────────────────────────────────────────────────────
    
    def _scan_virtualization(self) -> Dict[str, Any]:
        """Scan virtualization status and VMs."""
        result = {
            "is_vm": False,
            "vm_type": None,
            "hypervisor": None,
            "vms": [],
        }
        
        # Check if we're running in a VM
        code, stdout, _ = self.run_command(["systemd-detect-virt"])
        if code == 0:
            virt_type = stdout.strip()
            if virt_type and virt_type != "none":
                result["is_vm"] = True
                result["vm_type"] = virt_type
        
        # Check for KVM/QEMU
        code, stdout, _ = self.run_command(["virsh", "list", "--all"])
        if code == 0:
            result["hypervisor"] = "libvirt/kvm"
            for line in stdout.split('\n')[2:]:  # Skip headers
                parts = line.split()
                if len(parts) >= 2:
                    result["vms"].append({
                        "name": parts[1],
                        "state": parts[2] if len(parts) > 2 else "unknown",
                    })
        
        # Check for VirtualBox
        code, stdout, _ = self.run_command(["VBoxManage", "list", "vms"])
        if code == 0:
            if not result["hypervisor"]:
                result["hypervisor"] = "virtualbox"
            for line in stdout.split('\n'):
                match = re.search(r'"([^"]+)"', line)
                if match:
                    result["vms"].append({
                        "name": match.group(1),
                        "type": "virtualbox",
                    })
        
        return result
    
    # ─────────────────────────────────────────────────────────────────────────
    # Scheduled Tasks
    # ─────────────────────────────────────────────────────────────────────────
    
    def _scan_scheduled_tasks(self) -> Dict[str, Any]:
        """Scan cron jobs and systemd timers."""
        result = {
            "cron_jobs": [],
            "systemd_timers": [],
            "anacron": False,
        }
        
        # User crontab
        code, stdout, _ = self.run_command(["crontab", "-l"])
        if code == 0:
            for line in stdout.split('\n'):
                line = line.strip()
                if line and not line.startswith('#'):
                    result["cron_jobs"].append({
                        "type": "user",
                        "schedule": ' '.join(line.split()[:5]) if len(line.split()) > 5 else line,
                        "command": ' '.join(line.split()[5:]) if len(line.split()) > 5 else "",
                    })
        
        # System cron
        cron_dirs = ['/etc/cron.d', '/etc/cron.daily', '/etc/cron.hourly', '/etc/cron.weekly']
        for cron_dir in cron_dirs:
            cron_path = Path(cron_dir)
            if cron_path.exists():
                for f in cron_path.iterdir():
                    if f.is_file() and not f.name.startswith('.'):
                        result["cron_jobs"].append({
                            "type": cron_dir.split('/')[-1],
                            "name": f.name,
                        })
        
        # Systemd timers
        code, stdout, _ = self.run_command(["systemctl", "list-timers", "--no-pager", "--no-legend"])
        if code == 0:
            for line in stdout.split('\n'):
                if line.strip():
                    parts = line.split()
                    if len(parts) >= 5:
                        result["systemd_timers"].append({
                            "next": f"{parts[0]} {parts[1]}",
                            "unit": parts[-1],
                        })
        
        # Check anacron
        result["anacron"] = Path("/etc/anacrontab").exists()
        
        return result
    
    # ─────────────────────────────────────────────────────────────────────────
    # Kernel
    # ─────────────────────────────────────────────────────────────────────────
    
    def _scan_kernel(self) -> Dict[str, Any]:
        """Scan kernel information."""
        result = {
            "version": "",
            "modules_loaded": 0,
            "notable_modules": [],
        }
        
        # Kernel version
        code, stdout, _ = self.run_command(["uname", "-r"])
        if code == 0:
            result["version"] = stdout.strip()
        
        # Loaded modules
        code, stdout, _ = self.run_command(["lsmod"])
        if code == 0:
            modules = stdout.strip().split('\n')[1:]  # Skip header
            result["modules_loaded"] = len(modules)
            
            # Notable modules to track
            notable = ['nvidia', 'amdgpu', 'i915', 'nouveau',  # GPU
                      'kvm', 'vboxdrv',  # Virtualization
                      'bcachefs', 'btrfs', 'zfs',  # Filesystems
                      'wireguard', 'tun', 'tap',  # VPN/Network
                      'snd_', 'usb',]  # Audio/USB
            
            for line in modules:
                mod_name = line.split()[0]
                for notable_mod in notable:
                    if mod_name.startswith(notable_mod):
                        result["notable_modules"].append(mod_name)
                        break
        
        return result
    
    # ─────────────────────────────────────────────────────────────────────────
    # Boot
    # ─────────────────────────────────────────────────────────────────────────
    
    def _scan_boot(self) -> Dict[str, Any]:
        """Scan boot configuration."""
        result = {
            "bootloader": None,
            "efi": False,
            "secure_boot": None,
            "boot_time": None,
        }
        
        # Check if EFI
        result["efi"] = Path("/sys/firmware/efi").exists()
        
        # Check bootloader
        if Path("/boot/grub/grub.cfg").exists() or Path("/boot/grub2/grub.cfg").exists():
            result["bootloader"] = "grub"
        elif Path("/boot/loader/loader.conf").exists():
            result["bootloader"] = "systemd-boot"
        
        # Check secure boot
        code, stdout, _ = self.run_command(["mokutil", "--sb-state"])
        if code == 0:
            result["secure_boot"] = "enabled" in stdout.lower()
        
        # Boot time
        code, stdout, _ = self.run_command(["systemd-analyze"])
        if code == 0:
            match = re.search(r'= ([\d.]+)s', stdout)
            if match:
                result["boot_time"] = f"{match.group(1)}s"
        
        return result
    
    # ─────────────────────────────────────────────────────────────────────────
    # Development Tools
    # ─────────────────────────────────────────────────────────────────────────
    
    def _scan_development(self) -> Dict[str, Any]:
        """Scan development tools and environments."""
        result = {
            "languages": {},
            "tools": {},
            "editors": [],
        }
        
        # Check common languages
        lang_checks = [
            ("python3", ["python3", "--version"]),
            ("python", ["python", "--version"]),
            ("node", ["node", "--version"]),
            ("go", ["go", "version"]),
            ("rust", ["rustc", "--version"]),
            ("java", ["java", "-version"]),
            ("ruby", ["ruby", "--version"]),
            ("php", ["php", "--version"]),
        ]
        
        for lang, cmd in lang_checks:
            code, stdout, stderr = self.run_command(cmd)
            if code == 0:
                version = stdout.strip() or stderr.strip()
                # Extract just version number
                match = re.search(r'[\d.]+', version)
                result["languages"][lang] = match.group(0) if match else version[:50]
        
        # Check tools
        tool_checks = [
            ("git", ["git", "--version"]),
            ("docker", ["docker", "--version"]),
            ("make", ["make", "--version"]),
            ("cmake", ["cmake", "--version"]),
            ("npm", ["npm", "--version"]),
            ("yarn", ["yarn", "--version"]),
            ("pip", ["pip3", "--version"]),
            ("cargo", ["cargo", "--version"]),
        ]
        
        for tool, cmd in tool_checks:
            code, stdout, _ = self.run_command(cmd)
            if code == 0:
                match = re.search(r'[\d.]+', stdout)
                result["tools"][tool] = match.group(0) if match else "installed"
        
        # Check editors
        editors = ['vim', 'nvim', 'nano', 'emacs', 'code', 'subl', 'atom']
        for editor in editors:
            code, _, _ = self.run_command(["which", editor])
            if code == 0:
                result["editors"].append(editor)
        
        return result
    
    # ─────────────────────────────────────────────────────────────────────────
    # Desktop Environment
    # ─────────────────────────────────────────────────────────────────────────
    
    def _scan_desktop(self) -> Dict[str, Any]:
        """Scan desktop environment."""
        result = {
            "display_server": None,
            "desktop_environment": None,
            "session_type": None,
        }
        
        # Check XDG session
        result["session_type"] = os.environ.get('XDG_SESSION_TYPE', None)
        result["desktop_environment"] = os.environ.get('XDG_CURRENT_DESKTOP', None)
        
        # Check display server
        if os.environ.get('WAYLAND_DISPLAY'):
            result["display_server"] = "wayland"
        elif os.environ.get('DISPLAY'):
            result["display_server"] = "x11"
        
        return result
    
    # ─────────────────────────────────────────────────────────────────────────
    # Persistence
    # ─────────────────────────────────────────────────────────────────────────
    
    def save_profile(self, path: Optional[Path] = None) -> Path:
        """Save profile to disk."""
        if path is None:
            from ...utils.platform import get_data_dir
            path = get_data_dir() / "system_profile.json"
        
        path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(path, 'w') as f:
            json.dump(self.profile, f, indent=2, default=str)
        
        logger.info(f"System profile saved to {path}")
        return path
    
    def load_profile(self, path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
        """Load profile from disk."""
        if path is None:
            from ...utils.platform import get_data_dir
            path = get_data_dir() / "system_profile.json"
        
        if not path.exists():
            return None
        
        try:
            with open(path) as f:
                self.profile = json.load(f)
            self.scan_time = datetime.fromisoformat(self.profile.get("scan_time", ""))
            logger.info(f"Loaded system profile from {path}")
            return self.profile
        except Exception as e:
            logger.warning(f"Failed to load profile: {e}")
            return None
    
    def get_summary(self) -> str:
        """
        Get human-readable summary of system profile in FIRST PERSON.
        
        The computer should describe itself: "I am Linus, I have 24 cores..."
        This creates deep self-awareness identity for the AI.
        """
        if not self.profile:
            return "No system profile available. Run scan_all() first."
        
        lines = []
        
        # Get AI name from preferences (set during onboarding) with fallback to hostname
        # Priority: ai_name from preferences > user_settings.computer_name > hostname
        import yaml
        preferences_path = Path.home() / '.config' / 'cerebric' / 'preferences.yml'
        computer_name = None
        admin_name = "my administrator"
        
        try:
            if preferences_path.exists():
                with open(preferences_path, 'r') as f:
                    prefs = yaml.safe_load(f) or {}
                computer_name = prefs.get('ai_name')
                admin_name = prefs.get('user_name', admin_name)
        except:
            pass
        
        # Fallback to user_settings or hostname
        if not computer_name:
            user_settings = self.profile.get("user_settings", {})
            computer_name = user_settings.get("computer_name") or self.profile.get("hostname", "this computer")
        
        # OS info
        os_info = self.profile.get("os", {})
        distro = os_info.get("distro", {})
        
        # First person identity header
        lines.append(f"=== I AM {computer_name.upper()} ===")
        lines.append(f"I run {distro.get('name', 'Linux')} {distro.get('version_id', '')} with kernel {os_info.get('kernel', 'unknown')}.")
        lines.append(f"My administrator is {admin_name}.")
        lines.append(f"I use {os_info.get('package_manager', 'unknown')} for package management.")
        lines.append(f"I have been running for {os_info.get('uptime', 'unknown')}.")
        
        # Hardware in first person
        hw = self.profile.get("hardware", {})
        cpu = hw.get("cpu", {})
        mem = hw.get("memory", {})
        
        lines.append(f"\n--- My Hardware ---")
        lines.append(f"I have a {cpu.get('model_name', 'processor')} with {cpu.get('cpu(s)', '?')} cores.")
        lines.append(f"I have {mem.get('total_gb', '?')} GB of RAM ({mem.get('available_gb', '?')} GB currently available).")
        
        if hw.get("gpu"):
            gpu_list = hw['gpu'][:2]
            if len(gpu_list) == 1:
                lines.append(f"I have a {gpu_list[0]} GPU.")
            else:
                lines.append(f"I have {len(gpu_list)} GPUs: {', '.join(gpu_list)}.")
        else:
            lines.append("I do not have a dedicated GPU.")
        
        # Storage in first person
        storage = self.profile.get("storage", {})
        disk_count = storage.get('disk_count', 0)
        fs_count = len(storage.get('filesystems', []))
        lines.append(f"\n--- My Storage ---")
        lines.append(f"I have {disk_count} storage device{'s' if disk_count != 1 else ''} with {fs_count} filesystem{'s' if fs_count != 1 else ''}.")
        
        special_fs = []
        if storage.get("has_btrfs"): special_fs.append("btrfs")
        if storage.get("has_zfs"): special_fs.append("ZFS")
        if storage.get("has_bcachefs"): special_fs.append("bcachefs")
        if storage.get("has_raid"): special_fs.append("RAID")
        if storage.get("has_lvm"): special_fs.append("LVM")
        if special_fs:
            lines.append(f"I use {', '.join(special_fs)} for advanced storage management.")
        
        # Services
        services = self.profile.get("services", {})
        running = services.get('running_count', 0)
        failed = services.get('failed_count', 0)
        lines.append(f"\n--- My Services ---")
        lines.append(f"I am running {running} services" + (f" ({failed} have failed)" if failed > 0 else "."))
        
        notable = services.get("notable_services", [])
        if notable:
            running_notable = [s['name'] for s in notable if s.get('state') == 'running']
            if running_notable:
                lines.append(f"Notable services I'm running: {', '.join(running_notable[:5])}")
        
        # Containers
        containers = self.profile.get("containers", {})
        if containers.get("docker") or containers.get("podman"):
            container_count = len(containers.get("containers", []))
            runtime = "Docker" if containers.get("docker") else "Podman"
            lines.append(f"\n--- My Containers ---")
            lines.append(f"I run containers using {runtime}. Currently {container_count} container{'s' if container_count != 1 else ''} running.")
        
        # Security
        security = self.profile.get("security", {})
        fw = security.get("firewall", {})
        if fw:
            lines.append(f"\n--- My Security ---")
            fw_status = fw.get('status', 'unknown')
            lines.append(f"I am protected by {fw.get('type', 'a firewall')} (currently {fw_status}).")
        updates = security.get("updates_available", 0)
        if updates > 0:
            lines.append(f"I have {updates} update{'s' if updates != 1 else ''} available.")
        
        # Network
        network = self.profile.get("network", {})
        interfaces = network.get("interfaces", [])
        if interfaces:
            primary = next((i for i in interfaces if i.get("ipv4")), None)
            if primary:
                lines.append(f"\n--- My Network ---")
                ip = primary['ipv4'][0] if primary.get('ipv4') else 'no IP assigned'
                lines.append(f"My primary interface is {primary.get('name')} ({ip}).")
        
        # Development
        dev = self.profile.get("development", {})
        if dev.get("languages"):
            lines.append(f"\n--- Development Tools ---")
            lines.append(f"I have these development languages installed: {', '.join(dev['languages'].keys())}.")
        
        lines.append(f"\n(Last scanned: {self.profile.get('scan_time', 'unknown')})")
        
        return '\n'.join(lines)


# Singleton instance
_profiler: Optional[SystemProfiler] = None


def get_system_profiler() -> SystemProfiler:
    """Get the singleton system profiler."""
    global _profiler
    if _profiler is None:
        _profiler = SystemProfiler()
    return _profiler
