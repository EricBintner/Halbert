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
        "ssh", "sshd", "sudo", "permission", "firewall", "fail2ban", "root",
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
# a network signal — only count it when a networking word qualifies it. The
# qualifier is a lookbehind (non-consuming) rather than part of the match, so
# a qualifying word that is *itself* a real entity (e.g. "samba", "nfs")
# still gets its own match right before this one instead of being swallowed
# into a single two-word "samba share"/"nfs share" span (review: Plan A /
# A4 — "add a samba share..." was losing "share"; "an nfs share" was losing
# "nfs").
_DOMAIN_EXTRA_PATTERNS: dict[str, list[str]] = {
    "network": [
        r"(?:(?<=file )|(?<=windows )|(?<=smb )|(?<=cifs )|(?<=nfs )"
        r"|(?<=samba )|(?<=network ))share"
    ],
}

# Pre-compile domain patterns for speed
# `\b` treats "_" as a word character, so \bconfig\b misses "sshd_config" and
# \bnginx\b misses "nginx_proxy" — exactly the identifiers these keywords are
# meant to catch. Bound on alphanumerics instead, so separators (_ - . /) end a
# word but letters and digits still do not ("ssh" must not match "sshd").
_DOMAIN_PATTERNS: dict[str, re.Pattern] = {
    domain: re.compile(
        r"(?<![a-zA-Z0-9])("
        + "|".join(_DOMAIN_EXTRA_PATTERNS.get(domain, []) + [re.escape(k) for k in keywords])
        + r")(?![a-zA-Z0-9])",
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

# Visual intent — the user is asking Halbert to look at the screen, without
# having attached an image. Phrases like "what's on my screen" or "what does
# the error dialog say" signal that the turn needs a screen capture before
# the LLM can plan effectively. Anchored on possessive/demonstrative words
# to avoid false positives like "screening process" or "screenshot tool".
_VISUAL_INTENT_RE = re.compile(
    r"\b(?:"
    r"on (?:my|the) screen"
    r"|look at (?:my|this|the) (?:screen|camera|webcam|window|display|error|dialog|popup)"
    r"|what(?:'s| is|s) on (?:my|the) screen"
    r"|what do you see"
    r"|see (?:this|the) (?:error|dialog|window|message|popup|notification)"
    r"|the (?:error|dialog|popup|notification)(?:\s+\w+)? says"
    r"|what does (?:my|the) screen (?:show|say)"
    r"|what(?:'s| is) on (?:my|the) display"
    r")\b",
    re.IGNORECASE,
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
    has_vision_request: bool = False  # user asks to look at the screen (no attached image)
    # Thread cues (spec §4.2 / §6)
    entities: Set[str] = field(default_factory=set)
    past_reference: bool = False
    anaphora: bool = False


# ── Entities ─────────────────────────────────────────────────────

# Per-occurrence entity extraction (alias tokens/phrases, domain-keyword
# hits, file paths) is bounded to the first N characters of the message.
# Domain *presence* is still checked across the full message via a cheap,
# early-exiting `search` — only building the `entities` set (and scanning
# for file paths) is capped, so a large pasted log can't blow up latency
# the way an unbounded `finditer`/`findall` pass over the whole text did
# (review: Plan A / A4 — 266KB paste went 51ms -> 147ms; the un-early-exited
# domain scan was the dominant cost, not the alias-token loop).
_ENTITY_SCAN_LIMIT = 16 * 1024

# Hard cap on how many file-path entities one message can contribute.
# `entities` is persisted to `threads.entities_json` and folded into a
# SQLite FTS MATCH query, so an unbounded path count (a 400KB log produced
# 5000+ distinct paths, ~208KB of JSON) is a real cost at write and query
# time, not just here (review: Plan A / A4).
_MAX_PATH_ENTITIES = 20


def _looks_like_real_path(path: str) -> bool:
    """Reject one- or two-character noise like "/O" (from "I/O"), "/A"
    (from "N/A"), "/W" (from "R/W") that `_FILE_PATH_RE` matches but that
    isn't a real path (review: Plan A / A4)."""
    return len(path.lstrip("~./")) > 1


def _scan(text: str) -> tuple[list[str], set[str], bool]:
    """One bounded pass: (detected domains, canonical entities, has file path).

    ``analyze_message`` and ``canonical_entities`` share this so neither
    re-runs the domain/alias/path regexes separately.
    """
    scan_text = text[:_ENTITY_SCAN_LIMIT]
    lower = scan_text.lower()
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
        # `search` over the full text is the presence check (early-exiting,
        # same cost profile as pre-A4). If it finds nothing, the bounded
        # prefix can't contain a match either, so skip the finditer entirely
        # instead of paying for both passes on every non-matching domain
        # (review: Plan A / A4).
        if not pattern.search(text):
            continue
        domains.append(domain)
        for m in pattern.finditer(scan_text):
            kw = m.group(1).lower()
            if kw not in _GENERIC_KEYWORDS:
                entities.add(ENTITY_ALIASES.get(kw, kw))

    has_paths = bool(_FILE_PATH_RE.search(text))
    path_count = 0
    for path in _FILE_PATH_RE.findall(scan_text):
        if path_count >= _MAX_PATH_ENTITIES:
            break
        path = path.rstrip(".,;:")
        if _looks_like_real_path(path):
            entities.add(path)
            path_count += 1

    return domains, entities, has_paths


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
    domains, entities, has_paths = _scan(text)
    signals.detected_domains = domains
    signals.entities = entities
    signals.has_file_paths = has_paths

    # ── Thread cues ───────────────────────────────────────────────
    # Bounded to the same prefix as entity extraction: a past-reference cue
    # ("last week", "remember when...") is a conversational opener, not
    # something that shows up 200KB into a pasted log, and PAST_REF_RE's
    # many alternatives make an unbounded full-text `search` one of the
    # larger remaining costs on adversarial input (review: Plan A / A4).
    signals.past_reference = bool(PAST_REF_RE.search(text[:_ENTITY_SCAN_LIMIT]))
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

    # ── Visual intent (no attached image, but user asks to look) ─
    signals.has_vision_request = bool(_VISUAL_INTENT_RE.search(text))

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
