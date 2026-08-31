# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Role scope registry.

One source of truth for the role axis: which roles exist, which manifest
feeds each, where each stages, and which platforms each is file-backed on.
Both the staging code and the SourcePrep scope registration read from here
rather than hardcoding the list twice.

Names follow the DiscoveryType vocabulary in discovery/schema.py, in
underscore form so `id == display_name` and reconcile-by-name matches
query-by-id (the existing knowledge-linux/knowledge_linux split is a
hyphen/underscore mismatch we are not repeating).

Design: .handoff/ROLE-SCOPED-CONFIG-HARVESTING-DESIGN-2026-08-26.md
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, List

# Manifests ship *inside* the package, as package data.
#
# They started at the repo's `config/scopes/`, resolved through
# `<package>/../../../config/scopes`, on the reasoning that they are editable
# configuration alongside config-registry.yml. That path does not exist under
# any non-editable install: stage_role_tree raised FileNotFoundError,
# _stage_host_tree logged it as non-fatal, and sourceprep_template.yml went
# on to register host/network, host/service and host/storage against
# directories nothing had created -- the empty-scope condition this module
# warns about, and under scope_mode="hard" an empty mask excludes everything
# rather than narrowing. The whole role axis silently did nothing off a
# wheel, which is the only form most installs take.
#
# They are not user configuration in any useful sense: `ROLES` below names
# each manifest file, so the dict and the files are one unit, and editing a
# manifest changes what the product harvests the way editing this module
# would. If per-host overrides are wanted later, model/config_locator.py
# already has the candidate-chain pattern for it -- a packaged default is a
# prerequisite for that, not an alternative to it.
#
# Reachability is enforced by tests/test_config_roles.py: one asserts the
# path resolves inside the package, the other that pyproject declares it as
# package-data. Both are needed -- a wheel built without the second stanza
# contained 331 entries and zero non-.py files.
_MANIFEST_DIR = os.path.join(os.path.dirname(__file__), "scopes")


@dataclass(frozen=True)
class RoleScope:
    """One role scope: its manifest, staging location, and platform reach."""

    name: str
    manifest: str
    #: platform.system() values where this role harvests real files.
    #: A role absent here is docs-only on that platform, not broken. No
    #: wave-one role uses that today: a role whose manifest matches even
    #: one real file must be listed, because staging nothing produces an
    #: empty scope and under scope_mode="hard" an empty mask excludes
    #: everything rather than narrowing.
    file_backed_platforms: tuple = ()
    #: Roles whose primary-owned files are aliased INTO this scope.
    #: Membership is a mask over one shared index, so aliasing costs no
    #: extra indexing — see the design doc's primary+alias section.
    aliases_from: tuple = ()

    def file_backed_on(self, system: str) -> bool:
        return system in self.file_backed_platforms


ROLES: Dict[str, RoleScope] = {
    "network_admin": RoleScope(
        name="network_admin",
        manifest="network.yml",
        file_backed_platforms=("Linux", "Darwin"),
        # Firewall rule files are primary to security_admin (they answer
        # "is this machine hardened", not "how does this machine connect")
        # but a network question still needs them.
        aliases_from=("security_admin",),
    ),
    "service_admin": RoleScope(
        name="service_admin",
        manifest="service.yml",
        file_backed_platforms=("Linux", "Darwin"),
    ),
    "storage_admin": RoleScope(
        name="storage_admin",
        manifest="storage.yml",
        # macOS storage is thin, not absent. There is no fstab and no stock
        # /etc/synthetic.conf, and APFS container layout is genuinely
        # command-output-only (`diskutil apfs list`) — but autofs is real
        # mount intent that lives in files, and /etc/auto_master,
        # /etc/auto_home and /etc/autofs.conf all exist on a stock host.
        # Gating Darwin out left the scope empty, and under scope_mode="hard"
        # an empty mask excludes everything rather than narrowing.
        file_backed_platforms=("Linux", "Darwin"),
        # exports/nfs.conf answer "what does this machine serve", not "what
        # does it mount" (sharing primary); /etc/default/grub carries one
        # storage line (resume=, rd.luks.*) with boot primary.
        aliases_from=("sharing_admin", "boot_admin"),
    ),
    "credentials_admin": RoleScope(
        name="credentials_admin",
        manifest="credentials.yml",
        # Credential files exist on both platforms — cloud CLIs, container
        # registries, SSH config, .env files are cross-platform. This scope
        # is the one that makes the trust boundary real: without it, the
        # agent reads ~/.aws/credentials via a file-read tool and the secret
        # enters context raw, bypassing tier routing entirely.
        file_backed_platforms=("Linux", "Darwin"),
    ),
    "security_admin": RoleScope(
        name="security_admin",
        manifest="security.yml",
        # Rich on Linux (firewall four ways, MAC, sudo, PAM, audit), moderate
        # on macOS — /etc/pam.d (~25 files), sshd_config, sudoers, ftpusers
        # are all real harvestable files. Firewall rule files are primary
        # HERE (design rev. 2): they answer "is this machine hardened", not
        # "how does this machine connect", and are aliased into network.
        # kernel_admin's files (sysctl.d, modprobe.d) and users_admin's
        # (nsswitch.conf, passwd) are held here until those roles' promotion
        # triggers fire.
        file_backed_platforms=("Linux", "Darwin"),
        # /etc/default/grub carries one hardening line; auto-upgrade policy
        # answers "is this machine getting security patches".
        aliases_from=("package_admin", "boot_admin"),
    ),
    "shell_admin": RoleScope(
        name="shell_admin",
        manifest="shell.yml",
        # Login environment, PATH, shell rc, locale/time. Per-user files are
        # where the value is; both platforms have the /etc-level ones
        # (macOS: /etc/paths, /etc/zshrc, /etc/manpaths — plain text, small,
        # high signal).
        file_backed_platforms=("Linux", "Darwin"),
    ),
    "package_admin": RoleScope(
        name="package_admin",
        manifest="package.yml",
        # Linux-only, and the asymmetry is genuine (design: "do not tidy
        # this away"): Homebrew is effectively command-only on macOS — no
        # Brewfile exists, Library/Taps is empty on modern Homebrew, and
        # HOMEBREW_* settings live in shell rc files already covered by
        # shell_admin. Staging nothing would create an empty scope.
        file_backed_platforms=("Linux",),
    ),
    "boot_admin": RoleScope(
        name="boot_admin",
        manifest="boot.yml",
        # Linux-only: macOS com.apple.Boot.plist holds one empty Kernel
        # Flags key — there is no bootloader-config surface to harvest.
        file_backed_platforms=("Linux",),
        # fstab/crypttab (storage primary) are consulted at boot.
        aliases_from=("storage_admin",),
    ),
    "sharing_admin": RoleScope(
        name="sharing_admin",
        manifest="sharing.yml",
        # Linux is rich (samba/NFS/avahi/rsyncd/vsftpd). macOS is thin but
        # REAL, which is what keeps it file-backed on Darwin:
        # com.apple.smb.server.plist and /etc/nfs.conf both exist on a stock
        # host (verified) — gating Darwin out would stage nothing and leave
        # an empty scope under scope_mode="hard".
        file_backed_platforms=("Linux", "Darwin"),
    ),
}


def manifest_path_for(role: str) -> str:
    """Absolute path to a role's manifest file."""
    return os.path.join(_MANIFEST_DIR, ROLES[role].manifest)


def staging_subdir_for(role: str) -> str:
    """Directory name under sourceprep/host/ for a role's staged files."""
    return role.removesuffix("_admin")


def roles_for_platform(system: str) -> List[str]:
    """Role names that harvest real files on this platform.

    Docs-only roles are excluded: staging them would create an empty scope,
    and under scope_mode="hard" an empty mask excludes everything.
    """
    return [name for name, role in ROLES.items() if role.file_backed_on(system)]
