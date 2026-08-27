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

# Repo-relative manifest directory. Manifests live outside halbert_core so
# they are editable as configuration, alongside config/config-registry.yml.
_MANIFEST_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "config", "scopes")
)


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
        aliases_from=("sharing_admin",),
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
