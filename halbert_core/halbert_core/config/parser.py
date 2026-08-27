# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
from __future__ import annotations
import configparser
import json as pyjson
import os
import plistlib
from typing import Any, Dict, Tuple

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None  # Fallback: treat as text

"""
Config canonicalizer & parser (Phase 1)
- INI/Systemd (.conf/.ini/.service/.timer): configparser
- YAML/JSON: pyyaml/json
- Fallback: text lines
Output: canonical JSON with sections/keys and lines for citation.
"""


def _read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def _hash_bytes(b: bytes) -> str:
    import hashlib

    h = hashlib.sha256()
    h.update(b)
    return h.hexdigest()


def parse(path: str) -> Dict[str, Any]:
    lower = path.lower()
    # Plists are checked before the text read: binary plists are not UTF-8,
    # and _read_text's errors="replace" would corrupt them into U+FFFD soup
    # that then gets hashed — making drift detection compare corruption to
    # corruption. plistlib handles both binary and XML natively.
    if lower.endswith(".plist"):
        parsed = _parse_plist(path)
        if parsed is not None:
            return parsed
    text = _read_text(path)
    h = _hash_bytes(text.encode("utf-8", errors="replace"))
    if lower.endswith((".ini", ".conf", ".service", ".timer")):
        return _parse_ini_like(path, text, h)
    if lower.endswith((".yaml", ".yml")) and yaml is not None:
        return _parse_yaml(path, text, h)
    if lower.endswith(".json"):
        return _parse_json(path, text, h)
    return _parse_text(path, text, h)


def _parse_ini_like(path: str, text: str, h: str) -> Dict[str, Any]:
    parser = configparser.ConfigParser(interpolation=None)
    # Allow ; and # comments
    try:
        parser.read_string(text)
    except configparser.Error:
        # Real config routinely violates strict ini rules: systemd drop-ins
        # repeat directives (Environment=, ExecStartPre=), and dispatcher
        # scripts / bare KEY=value files have no [Section] header. Degrading
        # to text keeps the content searchable; raising would drop the file
        # entirely, because snapshot.py wraps parse + raw-write in one try.
        return _parse_text(path, text, h)
    sections: Dict[str, Dict[str, Any]] = {}
    for section in parser.sections():
        items: Dict[str, Any] = {}
        for k, v in parser.items(section):
            items[k] = _normalize_scalar(v)
        sections[section] = items
    return {
        "path": path,
        "hash": h,
        "kind": "ini",
        "sections": sections,
        "lines": _lines(text),
    }


def _parse_yaml(path: str, text: str, h: str) -> Dict[str, Any]:
    try:
        data = yaml.safe_load(text) if yaml else None  # type: ignore
    except Exception:
        return _parse_text(path, text, h)
    return {
        "path": path,
        "hash": h,
        "kind": "yaml",
        "tree": data,
        "lines": _lines(text),
    }


def _parse_json(path: str, text: str, h: str) -> Dict[str, Any]:
    try:
        data = pyjson.loads(text)
    except Exception:
        return _parse_text(path, text, h)
    return {
        "path": path,
        "hash": h,
        "kind": "json",
        "tree": data,
        "lines": _lines(text),
    }


def _parse_plist(path: str) -> Dict[str, Any] | None:
    """Parse a binary or XML plist. Returns None if it isn't a valid plist,
    so the caller falls through to the generic text path."""
    try:
        with open(path, "rb") as f:
            data = plistlib.load(f)
    except Exception:
        return None
    # Re-serialize to XML text so the content is greppable, citable by line,
    # and hashable over real content rather than raw binary.
    try:
        text = plistlib.dumps(data, fmt=plistlib.FMT_XML).decode("utf-8")
    except Exception:
        return None
    return {
        "path": path,
        "hash": _hash_bytes(text.encode("utf-8")),
        "kind": "plist",
        "tree": data,
        "lines": _lines(text),
    }


def _parse_text(path: str, text: str, h: str) -> Dict[str, Any]:
    return {
        "path": path,
        "hash": h,
        "kind": "text",
        "lines": _lines(text),
    }


def _lines(text: str) -> Any:
    return [{"n": i + 1, "text": line.rstrip("\n")} for i, line in enumerate(text.splitlines())]


def _normalize_scalar(v: str) -> Any:
    lv = v.strip().lower()
    if lv in {"true", "yes", "on"}:
        return True
    if lv in {"false", "no", "off"}:
        return False
    try:
        if "." in lv:
            return float(lv)
        return int(lv)
    except Exception:
        return v
