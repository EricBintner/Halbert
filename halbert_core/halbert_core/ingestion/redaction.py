# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
from __future__ import annotations
import re
from typing import Any, Dict

# Patterns from docs schemas (tokens/keys, home paths, emails, IPv4)
# Keyword list covers config formats staged into SourcePrep scopes:
# `psk` (NetworkManager WiFi), `privatekey`/`presharedkey` (WireGuard), plus
# the original generic terms. Whitespace around the separator is required —
# WireGuard's standard formatting is `PrivateKey = <value>`, which the
# original no-whitespace pattern silently missed.
#
# That whitespace is horizontal-only (`[ \t]*`) on purpose. `\s*` also matches
# newlines, so a key-like mapping at end-of-line would consume the next line's
# first token: `api:\n  - foo` collapsed to `<secret> foo`. Harvested YAML
# (/etc/netplan/*.yaml) must keep its structure, so the separator may never
# span a line break.
TOKEN_RE = re.compile(
    r"(?i)(api|secret|token|key|password|psk|privatekey|presharedkey)[ \t]*[=:][ \t]*\S+"
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

# --- Structured (line-oriented) redaction --------------------------------
#
# TOKEN_RE only sees one line at a time, by design: it uses horizontal-only
# whitespace so it can never span a line break and mangle a harvested file.
# That leaves the shapes where the value lives on a *later* line than the
# key uncovered — a next-line scalar, and a YAML block scalar (`|` / `>`),
# which is the normal way to write a multi-line credential.
#
# Those cannot be closed by widening the regex. The blocker is telling a
# child line that is a *value* from one that is *structure*:
#
#     password:                 api:
#       "pa55:word:here"          endpoint: https://x
#
# Both are "keyword key, separator at end of line, indented child". Any
# regex narrow enough to spare the mapping on the right (by rejecting child
# lines containing a colon) also spares the quoted scalar on the left and
# leaks it; any regex loose enough to catch the left destroys the right.
# That trade is not fixable in a pattern, so shape decides it here instead:
# a leading quote means scalar unambiguously, `- ` means a sequence item,
# and an unquoted `key:` / `key =` prefix means a nested mapping.
#
# Unquoted scalars containing a colon (`pa55:word`) are read as mappings and
# left alone. YAML itself is ambiguous there and requires quoting, so this
# matches how a parser would read the file.

# Key tokens whose *value* is a credential. Matched anywhere inside the key
# so `wifi-password`, `admin_token` and `api-key` are all covered.
_SECRET_KEY_RE = re.compile(r"(?i)(api|secret|token|key|password|psk|privatekey|presharedkey)")
# `key: value` / `key = value`: indent, key token, separator, remainder.
_KEY_LINE_RE = re.compile(r"^([ \t]*)([^\s:=#][^\s:=]*)[ \t]*[=:][ \t]*(.*)$")
# YAML block scalar header: | or >, with optional indentation and chomping
# modifiers (|-, |+, >-, |2, |2-).
_BLOCK_HEADER_RE = re.compile(r"^[|>][0-9]*[-+]?$")
_SEQUENCE_ITEM_RE = re.compile(r"^-(?:\s|$)")
_MAPPING_ITEM_RE = re.compile(r"^[^\s:=#][^\s:=]*[ \t]*[=:]")


def _leading_ws(line: str) -> str:
    return line[: len(line) - len(line.lstrip(" \t"))]


def _is_structure(content: str) -> bool:
    """True when a child line is structure rather than a scalar value.

    `content` is the line with its indentation stripped. A leading quote is
    decisive: it marks a scalar even when the text inside contains a colon.
    """
    if content[:1] in ('"', "'"):
        return False
    if content.startswith("#") or _SEQUENCE_ITEM_RE.match(content):
        return True
    return bool(_MAPPING_ITEM_RE.match(content))


def redact_structured_values(text: str) -> str:
    """Redact secret values that sit on a later line than their key.

    Handles next-line scalars and `|`/`>` block scalar bodies, replacing the
    value while preserving the key line, each value line's indentation, and
    the total line count. Inline `key: value` pairs are left for TOKEN_RE.
    """
    lines = text.split("\n")
    total = len(lines)
    i = 0
    while i < total:
        m = _KEY_LINE_RE.match(lines[i])
        if not m or not _SECRET_KEY_RE.search(m.group(2)):
            i += 1
            continue
        key_indent = len(m.group(1))
        rest = m.group(3).strip()
        is_block = bool(_BLOCK_HEADER_RE.match(rest))
        if rest and not is_block:
            i += 1  # inline value — TOKEN_RE's job
            continue

        j = i + 1
        hit = False
        while j < total:
            line = lines[j]
            if not line.strip():
                j += 1  # a blank line does not terminate the value
                continue
            if len(_leading_ws(line)) <= key_indent:
                break  # dedent: a sibling, not part of the value
            if not is_block and _is_structure(line.strip()):
                break
            lines[j] = _leading_ws(line) + "<secret>"
            hit = True
            j += 1
            if not is_block:
                break  # a plain next-line scalar is a single line
        i = j if hit else i + 1
    return "\n".join(lines)


def redact_text(text: str) -> str:
    # Must run first: TOKEN_RE would otherwise eat the `|` off `password: |`
    # and orphan the block body.
    text = redact_structured_values(text)
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
