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

Two fixtures live here:

* ``generate_corpus`` — N short receipt-shaped threads for retrieval-precision
  decay (the ``ReceiptIndex`` measurement in ``recall_eval``).
* ``synthetic_thread`` — one long message-shaped thread with a distinctive
  planted fact every 10th turn, for the consolidation eval (R5): the exam is
  generated from the region a policy will destroy, and recall of the planted
  facts measures what that policy threw away.
"""

from __future__ import annotations

import hashlib
import random
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

__all__ = [
    "Domain", "SyntheticThread", "generate_corpus", "DOMAIN_VOCAB",
    # R5 eval corpus
    "EVAL_DOMAINS", "EVAL_DOMAIN_ORDER", "EvalMessage", "EvalThread",
    "PlantedFact", "synthetic_thread", "planted_facts", "content_digest",
]


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


# ---------------------------------------------------------------------------
# R5 eval corpus — one long thread with planted facts every 10th turn
# ---------------------------------------------------------------------------
#
# The Hermes compaction-eval fixture pattern: a deterministic synthetic
# transcript with plausible conversation around a distinctive planted fact
# ("the garage keypad code is 47-29") at a known turn, so the harness can
# smoke-test itself in CI with no models anywhere.

#: Device-flavored domains from the ledger's real subject vocabulary — scanner,
#: printer, HA devices — so FTS/tokenization over the corpus behaves like it
#: does over production transcripts.
EVAL_DOMAINS: Dict[str, Dict[str, Sequence[str]]] = {
    "scanner": {
        "entities": ["sane", "scanbd", "flatbed", "ocr pipeline", "sheet feeder"],
        "symptoms": ["jams on duplex", "returns blank pages", "drops off USB",
                     "loses the lamp mid-scan"],
        "files": ["/etc/sane.d/epjitsu.conf", "/etc/scanbd/scanbd.conf"],
        "fact_names": ["scanner unlock code", "scan station pin",
                       "ocr service pin", "scanbd admin code",
                       "flatbed release pin", "feeder access code"],
    },
    "printer": {
        "entities": ["cups", "lpadmin", "duplex unit", "print queue", "toner"],
        "symptoms": ["stalls on large jobs", "prints ghost pages",
                     "refuses raw sockets", "spools forever"],
        "files": ["/etc/cups/printers.conf", "/etc/cups/cupsd.conf"],
        "fact_names": ["printer admin pin", "cups admin code",
                       "duplex release code", "queue override pin",
                       "toner reorder code", "lpadmin fallback pin"],
    },
    "ha_devices": {
        "entities": ["zigbee dongle", "z-wave repeater", "smart lock",
                     "motion sensor", "home assistant"],
        "symptoms": ["falls off the mesh", "drops events at night",
                     "flaps its battery report", "pairs then vanishes"],
        "files": ["/etc/homeassistant/configuration.yaml", "/etc/zigbee2mqtt/data"],
        "fact_names": ["garage keypad code", "smart lock code",
                       "zigbee network key", "guest house entry code",
                       "shed door code", "basement hatch code"],
    },
}

EVAL_DOMAIN_ORDER: List[str] = sorted(EVAL_DOMAINS)

#: A planted fact reads "the <name> is <NN-NN>" and ends the message; the value
#: pattern is deliberately distinctive so chatter can never collide with it.
_PLANTED_RE = re.compile(r"\bthe (?P<name>[a-z][a-z0-9 ]*?) is (?P<value>\d{2}-\d{2})")

_USER_CHATTER = [
    "the {entity} is acting up again — {symptom}",
    "can you look at the {entity}? it {symptom} since the update",
    "quick one: the {entity} {symptom} and i need it working today",
    "the {entity} on this host {symptom} — same as last month",
]

_ASSISTANT_CHATTER = [
    "checked {file} and cycled the {entity}; logs are quiet now, keep an eye on it",
    "{file} needed a small correction; the {entity} should behave now",
    "restarted the unit for the {entity} and re-ran the check — clean since",
    "the {entity} responded after {file} was reloaded; call it fixed for now",
]


@dataclass
class EvalMessage:
    """One turn of the synthetic transcript. Index == turn number."""

    role: str  # "user" | "assistant"
    content: str


@dataclass
class PlantedFact:
    """A fact planted at a known turn, with the exam's gold answer."""

    statement: str      # "the garage keypad code is 47-29"
    source_turn: int    # turn the statement appears in
    question: str       # "what is the garage keypad code?"
    gold: str           # "47-29"


@dataclass
class EvalThread:
    """A synthetic conversation for the consolidation eval."""

    thread_id: str
    domain: str
    entities: List[str]
    messages: List[EvalMessage]


def synthetic_thread(seed: int, turns: int = 40, domain: Optional[str] = None,
                     thread_id: Optional[str] = None) -> EvalThread:
    """Build a deterministic transcript with a planted fact every 10th turn.

    Same seed and turn count produce the identical thread, so a change in any
    eval number is a change in the policy under test, never in the fixture.
    The first entity is shared across a domain's threads (the pattern the
    deterministic Consolidator promotes to a durable fact); the second is
    thread-unique.
    """
    rng = random.Random(seed)
    if domain is None:
        domain = EVAL_DOMAIN_ORDER[seed % len(EVAL_DOMAIN_ORDER)]
    vocab = EVAL_DOMAINS[domain]
    entities = [list(vocab["entities"])[0], f"issue-{seed}"]
    fact_names = list(vocab["fact_names"])

    messages: List[EvalMessage] = []
    for turn in range(turns):
        if turn % 10 == 0:
            name = fact_names[(turn // 10) % len(fact_names)]
            value = f"{rng.randrange(10, 100):02d}-{rng.randrange(0, 100):02d}"
            messages.append(EvalMessage(
                role="user",
                content=f"writing this down so it does not get lost: "
                        f"the {name} is {value}",
            ))
        elif turn % 2 == 0:
            template = rng.choice(_USER_CHATTER)
            messages.append(EvalMessage(
                role="user",
                content=template.format(
                    entity=rng.choice(list(vocab["entities"])),
                    symptom=rng.choice(list(vocab["symptoms"])),
                ),
            ))
        else:
            template = rng.choice(_ASSISTANT_CHATTER)
            messages.append(EvalMessage(
                role="assistant",
                content=template.format(
                    entity=rng.choice(list(vocab["entities"])),
                    file=rng.choice(list(vocab["files"])),
                ),
            ))

    return EvalThread(
        thread_id=thread_id or f"eval-{seed:04d}",
        domain=domain,
        entities=entities,
        messages=messages,
    )


def planted_facts(thread: EvalThread) -> List[PlantedFact]:
    """Extract the planted facts back out of the transcript text.

    Recovery is by pattern, not by replaying the generator, so the fixture
    and the exam stay honest: a fact only exists if it is literally in the
    text at its source turn.
    """
    facts: List[PlantedFact] = []
    for i, message in enumerate(thread.messages):
        for hit in _PLANTED_RE.finditer(message.content):
            name = hit.group("name").strip()
            value = hit.group("value")
            facts.append(PlantedFact(
                statement=f"the {name} is {value}",
                source_turn=i,
                question=f"what is the {name}?",
                gold=value,
            ))
    return facts


def content_digest(messages: Sequence[EvalMessage]) -> str:
    """SHA-256 over the messages — the cache key for question-bank invariance.

    Every arm of a policy matrix must answer the identical exam; keying the
    bank on the *content* of the region under test (not on the arm, seed
    order, or wall clock) is what makes that invariance checkable.
    """
    h = hashlib.sha256()
    for m in messages:
        h.update(m.role.encode("utf-8"))
        h.update(b"\x1f")
        h.update(m.content.encode("utf-8"))
        h.update(b"\x1e")
    return h.hexdigest()
