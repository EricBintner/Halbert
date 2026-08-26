# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Synthetic thread corpus for measuring recall under load.

Every recall test in the codebase runs at one or two threads. Precision decay is
invisible there: with two threads in the index, any search looks perfect. ATANT's
cumulative mode exists because of exactly this — its reference implementation
scores 100% isolated and 96% at 250-thread cumulative scale.

This module generates N threads across Halbert's sysadmin domains, each with a
*known-correct* recall target, so precision can be measured at N=10, 100, 500 and
compared. Generation is deterministic: same seed, same corpus, so a regression in
the numbers is a regression in retrieval, not in the fixture.

No LLM is involved anywhere in generation or scoring.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, List, Sequence

__all__ = ["Domain", "SyntheticThread", "generate_corpus", "DOMAIN_VOCAB"]


class Domain:
    """Halbert's sysadmin domains. A plain namespace, not an enum, so the
    generator can iterate names without importing agent code."""

    DISK = "disk"
    SERVICES = "services"
    NETWORK = "network"
    CONFIG = "config"
    PACKAGES = "packages"
    USERS = "users"
    SECURITY = "security"
    LOGS = "logs"
    PROCESSES = "processes"
    BOOT = "boot"

    ALL = [DISK, SERVICES, NETWORK, CONFIG, PACKAGES,
           USERS, SECURITY, LOGS, PROCESSES, BOOT]


# Per-domain vocabulary: (entities, actions, files). Entities are what a query
# will match on; keeping them domain-local is what makes cross-domain bleed
# measurable.
DOMAIN_VOCAB: Dict[str, Dict[str, Sequence[str]]] = {
    Domain.DISK: {
        "entities": ["zfs", "smart", "lvm", "btrfs", "fstab", "raid", "nvme"],
        "actions": ["expanded the pool", "checked SMART health", "resized the volume"],
        "files": ["/etc/fstab", "/etc/lvm/lvm.conf"],
    },
    Domain.SERVICES: {
        "entities": ["nginx", "smbd", "sshd", "cron", "postgres", "docker", "cups"],
        "actions": ["restarted the unit", "enabled it at boot", "fixed the unit file"],
        "files": ["/etc/systemd/system/app.service"],
    },
    Domain.NETWORK: {
        "entities": ["wireguard", "dns", "firewall", "bridge", "vlan", "dhcp", "nat"],
        "actions": ["opened the port", "fixed resolution", "added the route"],
        "files": ["/etc/resolv.conf", "/etc/network/interfaces"],
    },
    Domain.CONFIG: {
        "entities": ["dropin", "override", "sysctl", "environment", "locale"],
        "actions": ["added a drop-in", "resolved precedence", "reverted the override"],
        "files": ["/etc/sysctl.d/99-tuning.conf"],
    },
    Domain.PACKAGES: {
        "entities": ["apt", "brew", "pacman", "pinning", "repo", "dpkg"],
        "actions": ["pinned the version", "cleaned the cache", "added the repo"],
        "files": ["/etc/apt/sources.list"],
    },
    Domain.USERS: {
        "entities": ["sudoers", "groups", "umask", "shell", "quota"],
        "actions": ["granted sudo", "fixed the group", "changed the shell"],
        "files": ["/etc/sudoers.d/admin"],
    },
    Domain.SECURITY: {
        "entities": ["certificate", "selinux", "apparmor", "fail2ban", "gpg", "tls"],
        "actions": ["renewed the certificate", "tightened the policy", "rotated the key"],
        "files": ["/etc/ssl/certs/site.pem"],
    },
    Domain.LOGS: {
        "entities": ["journald", "syslog", "logrotate", "rsyslog", "auditd"],
        "actions": ["capped the journal", "fixed rotation", "traced the error"],
        "files": ["/etc/systemd/journald.conf"],
    },
    Domain.PROCESSES: {
        "entities": ["oom", "cgroup", "nice", "zombie", "ulimit"],
        "actions": ["raised the limit", "killed the runaway", "capped the cgroup"],
        "files": ["/etc/security/limits.conf"],
    },
    Domain.BOOT: {
        "entities": ["grub", "initramfs", "kernel", "efi", "fsck"],
        "actions": ["rebuilt initramfs", "pinned the kernel", "fixed the entry"],
        "files": ["/etc/default/grub"],
    },
}


#: Topics an admin revisits across different subsystems. Shared on purpose: a
#: realistic store has many threads about "backup" and many about "samba", and the
#: right one is identified by the *combination*, not by a unique token.
TOPICS = ["media", "scanner", "backup", "laptop", "guest", "office", "archive", "nas"]


@dataclass
class SyntheticThread:
    """One generated thread plus the query that must retrieve it."""

    thread_id: str
    domain: str
    entities: List[str]
    receipt: str
    query: str
    #: entities that appear in the query — what a keyword index can match on
    query_entities: List[str] = field(default_factory=list)


def _receipt(thread_id: str, domain: str, entities: Sequence[str],
             action: str, file_path: str, day: int) -> str:
    """A receipt in the nine-line shape Plan A's build_receipt produces."""
    return "\n".join([
        f"Title: {entities[0]} {action.split()[0]}",
        f"When: 2026-07-{day:02d}..2026-07-{day:02d} · 2 turns",
        f"Domains: {domain}",
        f"Entities: {', '.join(entities)}",
        f"Started with: please help me with {entities[0]} on this host",
        f"Last said (2026-07-{day:02d}): {action} for {entities[0]}.",
        f"Commands: systemctl status {entities[0]} (exit 0)",
        f"Files written: {file_path}",
        f"Open loop: confirm {entities[0]} still holds after reboot",
    ])


def generate_corpus(n: int, seed: int = 1) -> List[SyntheticThread]:
    """Generate ``n`` deterministic threads spread evenly across the domains.

    Each thread gets a distinctive primary entity (suffixed with its index) so
    exactly one thread is the correct answer to its own query. Shared background
    entities are drawn from the domain vocabulary, which is what creates
    realistic competition — and therefore measurable precision decay — as n grows.
    """
    rng = random.Random(seed)
    out: List[SyntheticThread] = []
    for i in range(n):
        domain = Domain.ALL[i % len(Domain.ALL)]
        vocab = DOMAIN_VOCAB[domain]
        # Shared vocabulary on purpose. The target is identified by the
        # (entity, topic) pair, and other threads legitimately share one half of
        # it — which is what makes disambiguation, and its decay, measurable.
        primary = rng.choice(list(vocab["entities"]))
        topic = rng.choice(TOPICS)
        background = rng.choice(list(vocab["entities"]))
        entities = [primary, topic, background]
        action = rng.choice(list(vocab["actions"]))
        file_path = rng.choice(list(vocab["files"]))
        tid = f"t{i:04d}"
        out.append(SyntheticThread(
            thread_id=tid,
            domain=domain,
            entities=entities,
            receipt=_receipt(tid, domain, entities, action, file_path, (i % 28) + 1),
            query=f"the {primary} {topic} one we did a while back",
            query_entities=[primary, topic],
        ))
    return out
