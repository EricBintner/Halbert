# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Deterministic secure responder — describe a secret without revealing it.

``describe_secret`` returns structured facts *about* a config value without
the value itself: key name, file, length, character classes, entropy
estimate, and a local command to view the real value.

No model call.  No LLM.  A template cannot be talked into quoting a value,
cannot be injected, and does not vary with which model is loaded.

This replaces the "local secure LLM" that the original tiered sensitivity
plan proposed.  Measured across 3 local models with planted sentinels using
the exact "describe, don't transcribe" system prompt:

    qwen3:4b      leaked 4/4 secrets; echoed a bare token verbatim
    qwen3.5:27b   leaked on adversarial fixtures and obeyed the injection
    llama3.1:8b   leaked nothing, but refused 2/5 requests

Posture is non-monotonic in model size — the 27B was the worst.  By the
time ``classify_sensitivity`` has flagged a value as Tier 2, there is no
judgement left for a model to make.  Every job the secure LLM would do is
template-able or computable.
"""
from __future__ import annotations

import datetime
import math
import os
import shlex
from collections import Counter
from typing import Any, Dict, Optional

from .credential_formats import identify_credential


def _charset_classes(text: str) -> list[str]:
    """Character classes present in ``text``."""
    classes = []
    if any(c.islower() for c in text):
        classes.append("lowercase")
    if any(c.isupper() for c in text):
        classes.append("uppercase")
    if any(c.isdigit() for c in text):
        classes.append("digits")
    if any(c in "!@#$%^&*()_+-=[]{}|;':\",./<>?`~" for c in text):
        classes.append("symbols")
    # base64 alphabet (without checking strict validity)
    if all(c in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=" for c in text) and len(text) > 8:
        classes.append("base64")
    # hex string
    if all(c in "0123456789abcdefABCDEF" for c in text) and len(text) > 8:
        classes.append("hex")
    return classes


def _shannon_entropy(text: str) -> float:
    """Estimated Shannon entropy in bits per character."""
    if not text:
        return 0.0
    counts = Counter(text)
    length = len(text)
    entropy = 0.0
    for count in counts.values():
        p = count / length
        entropy -= p * math.log2(p)
    return entropy


def _view_command(key: str, file_path: str, *, remote: bool = False) -> str:
    """A local shell command to view the real value.

    The command is safe to show to any model — it does not contain the
    secret, only instructions for where to find it locally.

    When ``remote=True``, the command is prefixed with a note that the
    client must SSH to the host first. This is for HTTP/SSE transport
    where the MCP client is on a different machine and cannot execute
    the command directly.
    """
    if not file_path:
        return "# value is in memory only"
    lower = file_path.lower()
    if lower.endswith(".plist"):
        cmd = f"plutil -p {shlex.quote(file_path)}"
    elif key:
        cmd = f"grep {shlex.quote(key)} {shlex.quote(file_path)}"
    else:
        cmd = f"cat {shlex.quote(file_path)}"
    if remote:
        return f"# Run on the host machine:\n# {cmd}"
    return cmd


def describe_secret(
    key: str,
    value: Any,
    file_path: str = "",
    *,
    identify: bool = True,
    remote: bool = False,
) -> Dict[str, Any]:
    """Return structured facts about ``value`` without the value itself.

    Architectural guarantee: this function has no code path that sends
    the secret value to any external service. The value is used only
    for local computation (length, charset, entropy, format matching).
    It does not appear in any network call, log, or return field. This
    is an architectural guarantee, not a policy — there is no config
    option that enables sending the value, because the code path does
    not exist. See `.handoff/TIER2-RECALIBRATION-2026-08-29.md` for
    the research basis (AWS describe-secret, Snowflake DESCRIBE SECRET,
    AgentSecrets zero-knowledge architecture).

    Parameters
    ----------
    key
        The config key name.
    value
        The secret value.  Converted to string for analysis.
    file_path
        The file the value came from (for the view command and
        last_changed timestamp).
    identify
        When True (default), consult the credential format database to
        identify the credential type. No secret leaves the tool — only
        the value's shape is matched against known formats.
    remote
        When True, the view command is annotated for a remote client
        (HTTP/SSE transport). The client must SSH to the host to run it.

    Returns
    -------
    dict with keys: ``key``, ``file``, ``length``, ``charset``,
    ``entropy_bits``, ``view_command``, ``redacted``, ``last_changed``,
    and optionally ``credential_type`` and ``breach_risk`` (if the
    format was identified).
    The ``redacted`` field is always ``True`` — callers can check it to
    distinguish a secure description from a raw value response.
    """
    text = "" if value is None else str(value)
    result: Dict[str, Any] = {
        "key": key,
        "file": file_path,
        "length": len(text),
        "charset": _charset_classes(text),
        "entropy_bits": round(_shannon_entropy(text), 2),
        "view_command": _view_command(key, file_path, remote=remote),
        "redacted": True,
    }

    # last_changed: file modification time (local filesystem call, no
    # secret leaves). Returns ISO timestamp or None if file not found.
    # This is the field AWS describe-secret and Snowflake DESCRIBE SECRET
    # both return — it tells the LLM "this secret hasn't been changed in
    # 2 years, recommend rotation."
    if file_path and os.path.exists(file_path):
        mtime = os.path.getmtime(file_path)
        result["last_changed"] = datetime.datetime.fromtimestamp(
            mtime, tz=datetime.timezone.utc
        ).isoformat()
    else:
        result["last_changed"] = None

    # Token format identification — local pattern matching only.
    # A bundled credential format database, no secret sent anywhere.
    if identify and text:
        cred_info = identify_credential(text)
        if cred_info:
            result["credential_type"] = cred_info
            # Surface breach_risk as a top-level field for easier LLM access.
            # The value comes from the static format database (e.g. "high"
            # for GitHub PATs). No secret leaves the tool.
            result["breach_risk"] = cred_info.get("breach_risk", "unknown")

    return result
