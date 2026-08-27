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
from typing import List

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
        "hdd", "space", "full", "lvm", "df",
    ],
    "backup": [
        "backup", "restore", "rsync", "borg", "snapshot", "timeshift",
        "archive", "recovery", "tar",
    ],
    "service": [
        "service", "systemd", "daemon", "process", "restart", "start",
        "stop", "status", "running", "failed", "enabled", "nginx",
        "apache", "docker", "container", "journalctl",
    ],
    "network": [
        "network", "wifi", "ethernet", "dns", "firewall", "ip", "port",
        "internet", "connection", "ping", "ssh", "curl", "wget",
        "iptables", "nftables", "netstat", "ss",
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

# Pre-compile domain patterns for speed
# `\b` treats "_" as a word character, so \bconfig\b misses "sshd_config" and
# \bnginx\b misses "nginx_proxy" — exactly the identifiers these keywords are
# meant to catch. Bound on alphanumerics instead, so separators (_ - . /) end a
# word but letters and digits still do not ("ssh" must not match "sshd").
_DOMAIN_PATTERNS: dict[str, re.Pattern] = {
    domain: re.compile(
        r"(?<![a-zA-Z0-9])(" + "|".join(re.escape(k) for k in keywords) + r")(?![a-zA-Z0-9])",
        re.IGNORECASE,
    )
    for domain, keywords in _DOMAIN_KEYWORDS.items()
}

_FILE_PATH_RE = re.compile(
    r"(?:~/|/)[a-zA-Z0-9._~\-/]+|\.\./[a-zA-Z0-9._~\-/]+|\./[a-zA-Z0-9._~\-/]+"
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

    # ── Domains ──────────────────────────────────────────────────
    signals.detected_domains = [
        domain for domain, pattern in _DOMAIN_PATTERNS.items()
        if pattern.search(text)
    ]

    # ── File paths ───────────────────────────────────────────────
    signals.has_file_paths = bool(_FILE_PATH_RE.search(text))

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
