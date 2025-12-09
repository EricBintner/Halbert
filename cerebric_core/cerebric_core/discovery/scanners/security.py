"""
Security Scanner - Discover security configuration and potential issues.

Implements Phase 9 research from docs/Phase9/deep-dives/08-security-hardening.md

Discovers:
- SSH configuration
- Firewall status
- Sudo users
- Failed login attempts
- Unattended upgrades
"""

from __future__ import annotations
from typing import List, Optional
import re

from .base import BaseScanner
from ..schema import (
    Discovery, 
    DiscoveryType, 
    DiscoverySeverity,
    DiscoveryAction,
    make_discovery_id,
)


class SecurityScanner(BaseScanner):
    """
    Scanner for security configuration.
    """
    
    @property
    def discovery_type(self) -> DiscoveryType:
        return DiscoveryType.SECURITY
    
    def scan(self) -> List[Discovery]:
        """Scan system for security configuration."""
        discoveries = []
        
        discoveries.extend(self._scan_ssh())
        discoveries.extend(self._scan_sudo())
        discoveries.extend(self._scan_updates())
        discoveries.extend(self._scan_fail2ban())
        
        self.logger.info(f"Found {len(discoveries)} security items")
        return discoveries
    
    def _scan_ssh(self) -> List[Discovery]:
        """Scan SSH configuration."""
        discoveries = []
        
        sshd_config = "/etc/ssh/sshd_config"
        if not self.file_exists(sshd_config):
            return discoveries
        
        content = self.read_file(sshd_config)
        if not content:
            return discoveries
        
        # Parse key settings
        root_login = self._get_ssh_setting(content, "PermitRootLogin", "prohibit-password")
        password_auth = self._get_ssh_setting(content, "PasswordAuthentication", "yes")
        pubkey_auth = self._get_ssh_setting(content, "PubkeyAuthentication", "yes")
        
        # Determine security level
        issues = []
        if root_login.lower() == "yes":
            issues.append("Root login enabled")
        if password_auth.lower() == "yes":
            issues.append("Password auth enabled")
        
        if issues:
            severity = DiscoverySeverity.WARNING
            status = f"{len(issues)} issue(s)"
        else:
            severity = DiscoverySeverity.SUCCESS
            status = "Secure"
        
        discovery_id = make_discovery_id(DiscoveryType.SECURITY, "ssh-config")
        
        discoveries.append(Discovery(
            id=discovery_id,
            type=DiscoveryType.SECURITY,
            name="ssh-config",
            title="SSH Configuration",
            description="; ".join(issues) if issues else "SSH is securely configured",
            icon="lock",
            severity=severity,
            status=status,
            source=sshd_config,
            data={
                "root_login": root_login,
                "password_auth": password_auth,
                "pubkey_auth": pubkey_auth,
                "issues": issues,
            },
            actions=[
                DiscoveryAction(id="details", label="View Config", icon="file"),
                DiscoveryAction(id="chat", label="Chat", icon="message-circle"),
            ],
            chat_context=f"SSH Configuration: PermitRootLogin={root_login}, "
                        f"PasswordAuthentication={password_auth}. "
                        f"Issues: {', '.join(issues) if issues else 'None'}.",
        ))
        
        return discoveries
    
    def _get_ssh_setting(self, content: str, key: str, default: str) -> str:
        """Get an SSH config setting."""
        for line in content.splitlines():
            line = line.strip()
            if line.startswith('#'):
                continue
            if line.lower().startswith(key.lower()):
                parts = line.split()
                if len(parts) >= 2:
                    return parts[1]
        return default
    
    def _scan_sudo(self) -> List[Discovery]:
        """Scan sudo configuration."""
        discoveries = []
        
        # Get sudo users
        code, stdout, _ = self.run_command(["getent", "group", "sudo"])
        
        sudo_users = []
        if code == 0 and stdout:
            parts = stdout.strip().split(':')
            if len(parts) >= 4:
                sudo_users = [u for u in parts[3].split(',') if u]
        
        # Also check wheel group (RHEL/Fedora)
        code, stdout, _ = self.run_command(["getent", "group", "wheel"])
        if code == 0 and stdout:
            parts = stdout.strip().split(':')
            if len(parts) >= 4:
                sudo_users.extend([u for u in parts[3].split(',') if u and u not in sudo_users])
        
        if sudo_users:
            severity = DiscoverySeverity.INFO if len(sudo_users) <= 3 else DiscoverySeverity.WARNING
            
            discovery_id = make_discovery_id(DiscoveryType.SECURITY, "sudo-users")
            
            discoveries.append(Discovery(
                id=discovery_id,
                type=DiscoveryType.SECURITY,
                name="sudo-users",
                title="Sudo Users",
                description=f"{len(sudo_users)} user(s) with sudo access",
                icon="users",
                severity=severity,
                status=f"{len(sudo_users)} users",
                source="/etc/group",
                data={
                    "users": sudo_users,
                    "count": len(sudo_users),
                },
                actions=[
                    DiscoveryAction(id="list", label="List Users", icon="list"),
                    DiscoveryAction(id="chat", label="Chat", icon="message-circle"),
                ],
                chat_context=f"Sudo access: {len(sudo_users)} users ({', '.join(sudo_users[:5])}...)",
            ))
        
        return discoveries
    
    def _scan_updates(self) -> List[Discovery]:
        """Check for unattended upgrades / automatic updates."""
        discoveries = []
        
        # Check unattended-upgrades (Debian/Ubuntu)
        if self.file_exists("/etc/apt/apt.conf.d/20auto-upgrades"):
            content = self.read_file("/etc/apt/apt.conf.d/20auto-upgrades")
            
            auto_update = "1" in content if content else False
            auto_upgrade = False
            if content:
                for line in content.splitlines():
                    if "Unattended-Upgrade" in line and '"1"' in line:
                        auto_upgrade = True
            
            if auto_update and auto_upgrade:
                severity = DiscoverySeverity.SUCCESS
                status = "Enabled"
                desc = "Automatic security updates are enabled"
            elif auto_update:
                severity = DiscoverySeverity.INFO
                status = "Partial"
                desc = "Auto-update enabled, but upgrades may be manual"
            else:
                severity = DiscoverySeverity.WARNING
                status = "Disabled"
                desc = "Automatic updates are disabled"
            
            discovery_id = make_discovery_id(DiscoveryType.SECURITY, "auto-updates")
            
            discoveries.append(Discovery(
                id=discovery_id,
                type=DiscoveryType.SECURITY,
                name="auto-updates",
                title="Automatic Updates",
                description=desc,
                icon="refresh-cw",
                severity=severity,
                status=status,
                source="/etc/apt/apt.conf.d/20auto-upgrades",
                data={
                    "auto_update": auto_update,
                    "auto_upgrade": auto_upgrade,
                },
                chat_context=f"Automatic updates: {status}. {desc}",
            ))
        
        return discoveries
    
    def _scan_fail2ban(self) -> List[Discovery]:
        """Check fail2ban status."""
        discoveries = []
        
        if not self.command_exists("fail2ban-client"):
            return discoveries
        
        code, stdout, _ = self.run_command(["fail2ban-client", "status"])
        
        if code == 0:
            # Parse jails
            jails = []
            for line in stdout.splitlines():
                if "Jail list:" in line:
                    jail_part = line.split(":", 1)[1].strip()
                    jails = [j.strip() for j in jail_part.split(",") if j.strip()]
            
            severity = DiscoverySeverity.SUCCESS
            status = f"{len(jails)} jails"
            desc = f"Active jails: {', '.join(jails[:3])}" if jails else "No active jails"
            
            discovery_id = make_discovery_id(DiscoveryType.SECURITY, "fail2ban")
            
            discoveries.append(Discovery(
                id=discovery_id,
                type=DiscoveryType.SECURITY,
                name="fail2ban",
                title="Fail2Ban",
                description=desc,
                icon="shield",
                severity=severity,
                status=status,
                source="fail2ban",
                data={
                    "jails": jails,
                    "jail_count": len(jails),
                },
                chat_context=f"Fail2Ban is active with {len(jails)} jails: {', '.join(jails)}",
            ))
        
        return discoveries
