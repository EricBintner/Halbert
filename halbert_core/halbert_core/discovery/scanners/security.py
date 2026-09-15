# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Security Scanner - Discover security configuration and potential issues.

Implements Phase 9 research from docs/Phase9/deep-dives/08-security-hardening.md

Discovers:
- SSH configuration (including sshd_config.d drop-in conflicts)
- Firewall status
- Sudo users
- Failed login attempts
- Unattended upgrades
"""

from __future__ import annotations
from typing import List

from .base import BaseScanner
from ...findings.precedence import PrecedenceEngine
from ..schema import (
    Discovery,
    DiscoveryType,
    DiscoverySeverity,
    DiscoveryAction,
    make_discovery_id,
    sanitize_discovery_text,
)


class SecurityScanner(BaseScanner):
    """
    Scanner for security configuration.
    """

    def __init__(self, config_dir: str = "/etc"):
        super().__init__()
        self._precedence = PrecedenceEngine(config_dir=config_dir)
        self._sshd_config = self._precedence.sshd_base

    @property
    def discovery_type(self) -> DiscoveryType:
        return DiscoveryType.SECURITY
    
    def is_available(self) -> bool:
        """Check if this scanner can run on the current platform."""
        return self.command_exists('systemctl')
    
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
        """Scan SSH configuration, including sshd_config.d drop-ins.

        OpenSSH on modern distros reads drop-ins from sshd_config.d/*.conf
        (typically pulled in by an Include near the top of sshd_config)
        and resolves FIRST-match-wins — so a drop-in can silently override
        the main file. The effective values here account for that; the
        conflict discoveries cite the exact drop-in path and line.
        """
        discoveries = []

        sshd_config = self._sshd_config
        if not self.file_exists(sshd_config):
            return discoveries

        # Gate on readability of the main file, as before: an unreadable
        # or empty sshd_config yields no discoveries rather than a
        # defaults-based claim about a file we could not read.
        if not self.read_file(sshd_config):
            return discoveries

        result = self._precedence.resolve_sshd()
        effective = result["effective"]

        # Effective values for the settings this scanner tracks. Keys are
        # the lowercase directive names the precedence engine resolves.
        root_login = effective.get("permitrootlogin", "prohibit-password")
        password_auth = effective.get("passwordauthentication", "yes")
        pubkey_auth = effective.get("pubkeyauthentication", "yes")

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
                "dropins": result["dropin_files"],
            },
            actions=[
                DiscoveryAction(id="details", label="View Config", icon="file"),
                DiscoveryAction(id="chat", label="Chat", icon="message-circle"),
            ],
            chat_context=f"SSH Configuration: PermitRootLogin={root_login}, "
                        f"PasswordAuthentication={password_auth}. "
                        f"Issues: {', '.join(issues) if issues else 'None'}.",
        ))

        # A drop-in overriding the main file's value for a tracked setting
        # is its own discovery, so the conflict is visible without reading
        # the config — shaped like the proactive-event row it feeds.
        tracked = {
            "permitrootlogin": "PermitRootLogin",
            "passwordauthentication": "PasswordAuthentication",
            "pubkeyauthentication": "PubkeyAuthentication",
        }
        for conflict in result["conflicts"]:
            key = conflict["key"]
            if key not in tracked:
                continue
            directive = tracked[key]
            # Config text comes from /etc — sanitize each fragment through
            # the schema's choke point before it reaches a description or
            # prompt. Paths get a larger cap than the default 64: real
            # sshd_config.d citations fit either way, but tmp-path fixtures
            # in tests do not.
            effective_value = sanitize_discovery_text(conflict["effective"]) or "?"
            eff_file, eff_line = conflict["effective_source"]
            eff_cite = f"{sanitize_discovery_text(eff_file, max_chars=256)}:{eff_line}"
            affected_paths = sorted({v["file"] for v in conflict["values"]})
            # The conflict is between the main file and a drop-in only if
            # the main file actually sets the directive.
            base_sets_it = any(
                v["file"] == sshd_config for v in conflict["values"]
            )
            where = (
                "across sshd_config and a drop-in"
                if base_sets_it
                else "across drop-in files"
            )

            discoveries.append(Discovery(
                id=make_discovery_id(DiscoveryType.SECURITY, f"ssh-dropin-conflict-{directive}"),
                type=DiscoveryType.SECURITY,
                name=f"ssh-dropin-conflict-{directive}",
                title=f"sshd config conflict: {directive}",
                description=(
                    f"{directive} set to different values {where}. "
                    f"Effective value is '{effective_value}' — from {eff_cite}."
                ),
                icon="alert-triangle",
                severity=DiscoverySeverity.WARNING,
                status="Drop-in override",
                source=eff_file,
                data={
                    "directive": directive,
                    "effective_value": effective_value,
                    "effective_source": eff_cite,
                    "values": conflict["values"],
                    "affected_paths": affected_paths,
                },
                actions=[
                    DiscoveryAction(id="details", label="View Config", icon="file"),
                    DiscoveryAction(id="chat", label="Chat", icon="message-circle"),
                ],
                related_to=[discovery_id],
                chat_context=(
                    f"sshd config conflict: {directive} is set to different values "
                    f"{where}. Effective value is "
                    f"'{effective_value}' (from {eff_cite}). "
                    f"OpenSSH uses first-match-wins, so the value the service "
                    f"actually applies may not be the one in sshd_config."
                ),
            ))

        return discoveries

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
