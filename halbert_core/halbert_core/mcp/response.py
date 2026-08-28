# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""MCP response boundary — the single choke point for egress to clients.

Every Halbert MCP tool that returns host config content passes its result
through ``mcp_response()`` before returning.  The helper redacts
credentials from the payload so that no secret in the host's config tree
reaches an external AI client's cloud model.

Why this exists
---------------
An MCP client (WarpCLI, Claude Code, Cursor) is not ``cat``.  It forwards
whatever it reads into its own cloud LLM's context and that vendor's
inference logs.  Same-user filesystem access and same-user cloud-forwarding
are different acts with different blast radii.  The MCP surface creates a
new egress path, and redaction on the response boundary is the
deterministic control that closes it.

Internal reads are unaffected — Halbert's own agent keeps the raw path.
The boundary is the MCP response, not Halbert's internal data flow.

Design
------
``_redact_value`` walks the payload recursively with two rules:

1. **Config-value-pair shape.**  When a dict has a ``"key"`` field whose
   value is a secret key name (per ``_is_secret_key``), the sibling
   ``"value"`` field is replaced with ``"<secret>"``.  This catches the
   primary MCP payload shape — ``{"path": ..., "key": "password",
   "value": "hunter2"}`` — where ``redact_text()`` alone would miss the
   bare value because it has no ``key=value`` structure to match.

2. **Secret dict keys.**  A dict key that is itself a secret key name
   (e.g. ``{"password": "hunter2"}``) triggers redaction of its value.
   MCP field names like ``"key"``, ``"value"``, ``"path"`` are NOT secret
   keys in this context — they are payload metadata, not config keys — so
   the ``"key"`` field name does not cause its value (the config key name)
   to be redacted.  The distinction is handled by checking the
   config-value-pair shape first: if the dict has a ``"key"`` field, the
   pair rule handles the secret check and the generic dict-key rule skips
   the ``"key"`` and ``"value"`` entries.

After the structural rules, every remaining string is passed through
``redact_text()``, which catches credentials embedded in text:
``key=value`` shapes, PEM blocks, JWTs, URL-embedded credentials,
routable IPs, email addresses, MAC addresses.

Non-string scalars (int, float, bool, None) are returned as-is — a number
like a port or a UID is not a credential by itself.

Known limit (Task 8): a bare context-free secret under a neutral key
(e.g. ``{"key": "location", "value": "ghp_abc123"}``) is not caught by
either rule.  ``_is_secret_key("location")`` is False and
``redact_text("ghp_abc123")`` has no pattern to match it.  Closing that
gap requires known-prefix detection (``ghp_``, ``sk-``, ``AKIA``, ``xox``)
and a high-entropy backstop — see Task 8 in the implementation plan.

The function returns a new structure rather than mutating in place, so the
caller's internal copy retains the raw value if it held one.
"""
from __future__ import annotations

from typing import Any

from ..ingestion.redaction import _is_secret_key, redact_text

_SECRET_MARKER = "<secret>"

# MCP payload field names that are metadata, not config keys.  When these
# appear as dict keys in the payload, _is_secret_key must not be applied to
# them — "key" the field name is not "key" the credential keyword.  The
# config-value-pair rule handles the actual secret check via the "key"
# field's *value*.
_MCP_FIELD_NAMES = frozenset({
    "path", "key", "value", "tier", "source", "type", "kind",
    "hash", "lines", "sections", "tree", "error", "status",
    "change", "old", "new", "added", "removed", "modified",
    "dependencies", "edges", "scope", "query", "results",
})


def _redact_value(value: Any) -> Any:
    """Recursively redact every string in a nested structure.

    Returns a new structure; the input is not mutated.
    """
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return _redact_dict(value)
    if isinstance(value, list):
        return [_redact_value(v) for v in value]
    if isinstance(value, tuple):
        return tuple(_redact_value(v) for v in value)
    return value


def _redact_dict(d: dict) -> dict:
    """Redact a dict, handling both MCP payload shapes and config-key shapes.

    Two rules, checked in order:

    1. Config-value-pair: if the dict has a ``"key"`` field whose value is
       a secret key name, replace the ``"value"`` field with
       ``"<secret>"``.  This is the primary MCP payload shape for config
       queries.

    2. Secret dict keys: for keys that are NOT MCP field names, check
       ``_is_secret_key``.  If the key is a secret key name, its value is
       replaced with ``"<secret>"`` (unless it's None or a bool — those
       are structural, not credentials).

    After both rules, every remaining string value is passed through
    ``redact_text()``.
    """
    result = {}
    has_secret_key_field = False

    # Rule 1: config-value-pair shape.
    key_val = d.get("key")
    if isinstance(key_val, str) and _is_secret_key(key_val):
        has_secret_key_field = True

    for k, v in d.items():
        if has_secret_key_field and k == "value":
            # Rule 1: value field under a secret key — replace outright.
            if v is not None and not isinstance(v, bool):
                result[k] = _SECRET_MARKER
            else:
                result[k] = v
            continue

        # Rule 2: secret dict keys — but skip MCP field names.
        if k not in _MCP_FIELD_NAMES and _is_secret_key(str(k)):
            if v is not None and not isinstance(v, bool):
                result[k] = _SECRET_MARKER
                continue

        result[k] = _redact_value(v)

    return result


def mcp_response(payload: Any) -> Any:
    """Run the redaction boundary over an MCP tool response.

    Call this as the last step before returning from every MCP tool that
    may contain host config content::

        def get_config_value(path: str, key: str) -> dict:
            raw = _query_config_db(path, key)
            return mcp_response(raw)

    Two passes: structural (secret-key-aware dict redaction) then text
    (``redact_text()`` on every remaining string).  Non-string scalars
    pass through unchanged.

    Returns a new structure; the input is not mutated.
    """
    return _redact_value(payload)
