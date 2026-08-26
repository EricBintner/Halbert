# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Zero-LLM signal detection for incoming messages.

Analyzes a user message and extracts structural signals (intent, domains,
error indicators, etc.) in <1ms with no external dependencies.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Set

# ── Pattern definitions ──────────────────────────────────────────

_GREETING_RE = re.compile(
    r"^\s*(hi|hello|hey|howdy|greetings|yo|sup|what'?s up|good (morning|afternoon|evening)|halbert)\b",
    re.IGNORECASE,
)

_FAREWELL_RE = re.compile(
    r"^\s*(bye|goodbye|goodnight|good night|see ya|see you|talk (to you )?later|catch you later|heading out|i'?m out|later)\b",
    re.IGNORECASE,
)

_ERROR_INDICATORS = (
    "error", "failed", "failure", "fail", "fails", "failing",
    "broken", "not working", "won't start",
    "won't boot", "traceback", "panic", "segfault", "crash", "exception",
    "denied", "refused", "timeout", "timed out", "unable to", "cannot",
    "can't", "fatal", "oom", "out of memory", "kernel panic",
)

# Domain keywords — reused from chat.py TOPIC_KEYWORDS + "config" added
_DOMAIN_KEYWORDS: dict[str, list[str]] = {
    "storage": [
        "disk", "filesystem", "mount", "zfs", "btrfs", "bcachefs", "ext4",
        "nvme", "ssd", "raid", "partition", "volume", "drive", "storage",
        "hdd", "space", "full", "lvm", "df", "zpool", "smartctl", "smartd",
    ],
    "backup": [
        "backup", "restore", "rsync", "borg", "snapshot", "timeshift",
        "archive", "recovery", "tar",
    ],
    "service": [
        "service", "systemd", "daemon", "process", "restart", "start",
        "stop", "status", "running", "failed", "enabled", "nginx",
        "apache", "docker", "container", "journalctl", "cron", "crontab",
    ],
    "network": [
        "network", "wifi", "ethernet", "dns", "firewall", "ip", "port",
        "internet", "connection", "ping", "ssh", "curl", "wget",
        "iptables", "nftables", "netstat", "ss", "samba", "smb", "nfs",
        "cupsd", "printer", "wireguard", "vpn", "scanner",
    ],
    "security": [
        "ssh", "sudo", "permission", "firewall", "fail2ban", "root",
        "password", "key", "certificate", "ssl", "tls", "selinux",
        "apparmor", "audit", "auth",
    ],
    "config": [
        "config", "configure", "configuration", "settings", "etc",
        "conf", "yaml", "json", "toml", "ini", "environment",
        "env", "profile",
    ],
}

# Raw-regex alternatives per domain, tried before the escaped keyword list.
# "share" alone is too ambiguous ("can you share that document?") to count as
# a network signal — only count it when a networking word qualifies it
# (review: Plan A / A4).
_DOMAIN_EXTRA_PATTERNS: dict[str, list[str]] = {
    "network": [r"(?:file|windows|smb|cifs|nfs|network)\s+share"],
}

# Pre-compile domain patterns for speed
_DOMAIN_PATTERNS: dict[str, re.Pattern] = {
    domain: re.compile(
        r"\b(" + "|".join(_DOMAIN_EXTRA_PATTERNS.get(domain, []) + [re.escape(k) for k in keywords]) + r")\b",
        re.IGNORECASE,
    )
    for domain, keywords in _DOMAIN_KEYWORDS.items()
}

_FILE_PATH_RE = re.compile(
    r"(?:~/|/)[a-zA-Z0-9._~\-/]+|\.\./[a-zA-Z0-9._~\-/]+|\./[a-zA-Z0-9._~\-/]+"
)

# ── Entity canonicalisation (spec §6 alias table) ────────────────

#: Surface form -> canonical entity. Applied at index and query time.
ENTITY_ALIASES: dict[str, str] = {
    "smb": "samba",
    "cifs": "samba",
    "smbd": "samba",
    "nmbd": "samba",
    "file share": "samba",
    "windows share": "samba",
    "exports": "nfs",
    "wg": "wireguard",
    "vpn": "wireguard",
    "certbot": "tls",
    "letsencrypt": "tls",
    "acme": "tls",
    "zpool": "zfs",
    "smb.conf": "samba",
}

_ALIAS_PHRASES = [
    (re.compile(r"\b" + re.escape(k) + r"\b"), v)
    for k, v in ENTITY_ALIASES.items() if " " in k
]
_ENTITY_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9._\-]*")

# Domain keywords too generic to count as entities for overlap scoring.
_GENERIC_KEYWORDS = frozenset({
    "etc", "df", "ss", "ip", "port", "full", "space", "status", "running", "start",
    "stop", "restart", "failed", "enabled", "process", "key", "root", "env", "conf",
    "config", "configure", "configuration", "settings", "json", "yaml", "toml", "ini",
    "environment", "profile", "drive", "volume", "storage", "service", "daemon",
    "network", "internet", "connection", "security", "permission", "password",
    "audit", "auth", "tar", "recovery", "archive",
})

# ── Thread cues (spec §4.2) ──────────────────────────────────────

PAST_REF_RE = re.compile(
    r"\b(we (discussed|did|set ?up|talked about|configured)"
    r"|last (week|month|time|tuesday|monday|wednesday|thursday|friday|saturday|sunday)"
    r"|remember when|back when|earlier|the other day"
    r"|(a )?(few )?(weeks?|days?|months?) ago|as we did|like (we did|before))\b",
    re.IGNORECASE,
)

ANAPHORA_RE = re.compile(
    r"^\s*(?:so|ok|okay|and|well)?,?\s*"
    r"(?P<phrase>did (?:that|it) work|any luck|is (?:that|it) (?:done|working|fixed)"
    r"|still (?:broken|failing|not working)|what happened with (?:that|it)"
    r"|how did (?:that|it) go)\b"
    r"|^\s*(?P<bare>that|it)\b",
    re.IGNORECASE,
)

_CODE_BLOCK_FENCE_RE = re.compile(r"```")
_CODE_BLOCK_INDENT_RE = re.compile(r"(?m)^    \S")

# Image detection — markdown image syntax, data URIs, HTML img tags, image file extensions
_IMAGE_MARKDOWN_RE = re.compile(r"!\[[^\]]*\]\([^)]+\)", re.IGNORECASE)
_IMAGE_DATA_URI_RE = re.compile(r"data:image/[a-zA-Z+]+;base64,", re.IGNORECASE)
_IMAGE_HTML_RE = re.compile(r"<img\b", re.IGNORECASE)
_IMAGE_EXT_RE = re.compile(
    r"\b\w+\.(png|jpe?g|gif|webp|svg|bmp|tiff?|heic|avif)\b", re.IGNORECASE
)

_COMMAND_VERBS = frozenset(
    {"show", "list", "check", "run", "install", "configure", "enable",
     "disable", "restart", "stop", "start", "update", "remove", "create",
     "delete", "set", "get", "find", "grep", "kill", "mount", "unmount",
     "format", "wipe", "clean", "clear", "reset", "reboot", "shutdown"}
)

_QUESTION_RE = re.compile(
    r"\?\s*$"  # ends with question mark
    r"|^\s*(how|why|what|when|where|which|who|can|could|should|would|is|are|do|does|did|will)\b",  # starts with question word
    re.IGNORECASE,
)


# ── Dataclass ────────────────────────────────────────────────────

@dataclass
class MessageSignals:
    """Structural signals extracted from a user message."""
    intent: str = "informational"  # question|command|troubleshooting|informational|greeting|farewell
    is_question: bool = False
    is_greeting: bool = False
    is_farewell: bool = False
    is_troubleshooting: bool = False
    message_length: str = "normal"  # short|normal|long
    detected_domains: List[str] = field(default_factory=list)
    has_error_indicators: bool = False
    has_code_blocks: bool = False
    has_file_paths: bool = False
    has_images: bool = False
    # Thread cues (spec §4.2 / §6)
    entities: Set[str] = field(default_factory=set)
    past_reference: bool = False
    anaphora: bool = False


# ── Entities ─────────────────────────────────────────────────────

def _scan(text: str) -> tuple[list[str], set[str], list[str]]:
    """One pass over ``text``: (detected domains, canonical entities, file paths).

    ``analyze_message`` and ``canonical_entities`` both need domain-keyword
    and file-path matches; running each regex once here — instead of a
    `search` pass for domains/paths plus a separate `finditer`/`findall` pass
    for entities — keeps analyze_message within its <1ms budget (review:
    Plan A / A4).
    """
    lower = text.lower()
    entities: set[str] = set()
    for tok in _ENTITY_TOKEN_RE.findall(lower):
        alias = ENTITY_ALIASES.get(tok.strip("._-"))
        if alias:
            entities.add(alias)
    for pattern, alias in _ALIAS_PHRASES:
        if pattern.search(lower):
            entities.add(alias)

    domains: list[str] = []
    for domain, pattern in _DOMAIN_PATTERNS.items():
        matched = False
        for m in pattern.finditer(text):
            matched = True
            raw = m.group(1).lower()
            # A qualified multi-word alternative (e.g. "windows share")
            # canonicalizes to its last word ("share"); single-word
            # alternatives are unaffected.
            kw = raw.split()[-1] if " " in raw else raw
            if kw not in _GENERIC_KEYWORDS:
                entities.add(ENTITY_ALIASES.get(kw, kw))
        if matched:
            domains.append(domain)

    paths: list[str] = []
    for path in _FILE_PATH_RE.findall(text):
        path = path.rstrip(".,;:")
        if len(path) > 1:
            paths.append(path)
            entities.add(path)

    return domains, entities, paths


def canonical_entities(text: str) -> set[str]:
    """Canonical entities of ``text``: alias hits, non-generic domain keywords, file paths."""
    if not text:
        return set()
    _, entities, _ = _scan(text)
    return entities


# ── Analysis ─────────────────────────────────────────────────────

def analyze_message(message: str) -> MessageSignals:
    """Analyze a message and extract structural signals.

    Pure function, <1ms, zero LLM, zero external deps.
    """
    if not message or not message.strip():
        return MessageSignals()

    text = message.strip()
    text_lower = text.lower()
    word_count = len(text.split())

    signals = MessageSignals()

    # ── Length ───────────────────────────────────────────────────
    if word_count <= 3:
        signals.message_length = "short"
    elif word_count > 50:
        signals.message_length = "long"
    else:
        signals.message_length = "normal"

    # ── Greeting / Farewell ──────────────────────────────────────
    signals.is_greeting = bool(_GREETING_RE.match(text))
    signals.is_farewell = bool(_FAREWELL_RE.match(text))

    # ── Error indicators ─────────────────────────────────────────
    signals.has_error_indicators = any(ind in text_lower for ind in _ERROR_INDICATORS)

    # ── Domains + entities + file paths (one pass, see _scan) ─────
    domains, entities, paths = _scan(text)
    signals.detected_domains = domains
    signals.entities = entities
    signals.has_file_paths = bool(paths)

    # ── Thread cues ───────────────────────────────────────────────
    signals.past_reference = bool(PAST_REF_RE.search(text))
    cue = ANAPHORA_RE.match(text)
    if cue:
        if cue.group("phrase"):
            signals.anaphora = True
        elif cue.group("bare") and not signals.entities:
            # bare "that"/"it" counts only when no entity was detected. Domain
            # hits alone don't gate this: `entities` already excludes generic
            # domain keywords ("failed", "running", "start", "status", ...),
            # so gating on detected_domains too let those generic words
            # silently suppress the cue (review: Plan A / A4) — "it failed
            # again" has detected_domains=["service"] but no real entity, and
            # is exactly the kind of vague follow-up this cue exists to catch.
            signals.anaphora = True

    # ── Code blocks ──────────────────────────────────────────────
    # Either triple-backtick fences or 4-space indented blocks
    signals.has_code_blocks = (
        bool(_CODE_BLOCK_FENCE_RE.search(text))
        or bool(_CODE_BLOCK_INDENT_RE.search(text))
    )

    # ── Image references ────────────────────────────────────────
    signals.has_images = (
        bool(_IMAGE_MARKDOWN_RE.search(text))
        or bool(_IMAGE_DATA_URI_RE.search(text))
        or bool(_IMAGE_HTML_RE.search(text))
        or bool(_IMAGE_EXT_RE.search(text))
    )

    # ── Question detection ───────────────────────────────────────
    signals.is_question = bool(_QUESTION_RE.search(text))

    # ── Intent derivation (priority order) ───────────────────────
    # greeting > farewell > troubleshooting/error > question > command > informational
    if signals.is_greeting:
        signals.intent = "greeting"
    elif signals.is_farewell:
        signals.intent = "farewell"
    elif signals.has_error_indicators or "troubleshoot" in text_lower:
        signals.intent = "troubleshooting"
        signals.is_troubleshooting = True
    elif signals.is_question:
        signals.intent = "question"
    elif word_count > 0:
        first_word = text_lower.split()[0].rstrip(",.!?;:")
        if first_word in _COMMAND_VERBS:
            signals.intent = "command"
        else:
            signals.intent = "informational"

    return signals
