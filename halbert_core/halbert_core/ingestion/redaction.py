# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
from __future__ import annotations
import re
from typing import Any, Dict

# Patterns from docs schemas (tokens/keys, home paths, emails, IPv4)
# Keyword list covers config formats staged into SourcePrep scopes:
# `psk` (NetworkManager WiFi), `privatekey`/`presharedkey` (WireGuard), plus
# the original generic terms. `\s*` around the separator is required —
# WireGuard's standard formatting is `PrivateKey = <value>`, which the
# original no-whitespace pattern silently missed.
TOKEN_RE = re.compile(
    r"(?i)(api|secret|token|key|password|psk|privatekey|presharedkey)\s*[=:]\s*\S+"
)
HOME_RE = re.compile(r"/home/[^/\s]+")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
IPV4_RE = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")
IPV6_RE = re.compile(r"\b([0-9a-fA-F]{0,4}:){2,7}[0-9a-fA-F]{0,4}\b")
MAC_RE = re.compile(r"\b[0-9A-Fa-f]{2}(:[0-9A-Fa-f]{2}){5}\b")
# JWT (very rough): three base64url segments
JWT_RE = re.compile(r"\beyJ[0-9A-Za-z_-]*\.[0-9A-Za-z_-]*\.[0-9A-Za-z_-]*\b")
# PEM headers/footers
PEM_RE = re.compile(r"-----BEGIN [^-]+-----[\s\S]+?-----END [^-]+-----", re.MULTILINE)
# macOS: local Kerberos realm identifiers in com.apple.smb.server.plist and
# related SystemConfiguration plists. Format is LKDC:SHA1.<40 hex chars>.
LKDC_RE = re.compile(r"LKDC:SHA1\.[0-9A-Fa-f]{40}")


def redact_text(text: str) -> str:
    text = TOKEN_RE.sub("<secret>", text)
    text = HOME_RE.sub("/home/<user>", text)
    text = EMAIL_RE.sub("<email>", text)
    text = IPV4_RE.sub("<ip>", text)
    text = MAC_RE.sub("<mac>", text)  # MAC before IPv6 (IPv6 pattern is greedy)
    text = IPV6_RE.sub("<ip6>", text)
    text = JWT_RE.sub("<jwt>", text)
    text = PEM_RE.sub("<pem_block>", text)
    text = LKDC_RE.sub("<lkdc_realm>", text)
    return text


def redact_event(evt: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(evt)
    msg = out.get("message")
    if isinstance(msg, str):
        out["message"] = redact_text(msg)
    data = out.get("data")
    if isinstance(data, dict):
        red = {}
        for k, v in data.items():
            if isinstance(v, str):
                red[k] = redact_text(v)
            else:
                red[k] = v
        out["data"] = red
    return out
