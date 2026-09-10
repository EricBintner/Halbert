# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The one redaction core for tool results (Packet 05 Phase C1).

Extracted byte-for-byte from ``mcp/response.py``'s ``_redact_value`` /
``_redact_dict`` so there is exactly one implementation of structural +
text redaction and no future drift between the surfaces that need it.
``mcp.response.mcp_response`` is a thin delegate over ``redact_result``;
the parity pin lives in ``tests/test_result_redaction.py``.

Routing internal (executor) results through this core is deliberately NOT
done here: whether internal tool results need the same treatment is a
design question (they may already pass through ingestion redaction), and
the extraction alone kills the drift risk. The decision is recorded with
the packet status rows.

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

3. **Acknowledged egress exception.**  A dict carrying
   ``_egress_ack: True`` — set only by ``config.queries.get_config_value``
   after verifying tier + acknowledgment + TTL — keeps its ``"value"``
   field raw. The exception is per-dict and per-field; the marker itself
   is dropped. Without it, the per-key escape hatch would be inert for
   vocabulary keys (rule 1 re-redacts what the tier legitimately let
   through) while leaking silently for user-classified keys.

   KNOWN RISK (NEW-01, tracked not fixed): "set only by
   ``get_config_value``" is a naming convention, not an enforced
   invariant — ``_redact_dict`` honours the marker on ANY dict at ANY
   depth of the payload purely by structural shape (see
   ``test_egress_ack_does_not_leak_to_sibling_dicts`` and
   ``test_nested_secret_dict_keys_still_redacted_under_marker`` in
   test_mcp_response_boundary.py, which deliberately exercise and rely
   on that at-any-depth behaviour for nested/multi-result payloads).
   Nothing stops a different, careless, or compromised tool handler
   from returning ``{"_egress_ack": True, "value": <anything>}``
   anywhere in its own response and getting the same unredacted pass.
   Narrowing this to a provenance-checked exemption (e.g. only the
   direct top-level result, or a signed marker) is a real design
   change — it would need to preserve or deliberately retire the
   nested-payload contract those tests encode — not a mechanical fix,
   so it is left open rather than changed under time pressure.

After the structural rules, every remaining string is passed through
``redact_text()`` (key-shape, PEM, JWT, URL-credential, IP, email and MAC
patterns) and then the secret variant registry (exact-value pass over the
encoded forms of deliberately egressed values — see
``ingestion.redaction_registry``).

Non-string scalars (int, float, bool, None) are returned as-is — a number
like a port or a UID is not a credential by itself.

Known limit: a short context-free secret under a neutral key (e.g.
``{"key": "location", "value": "hunter2"}``) is not caught by either
rule.  ``_is_secret_key("location")`` is False and ``redact_text("hunter2")``
has no pattern to match it.  This is the same gap the sensitivity
classifier documents; the variant registry closes it only for values that
were egress-acked once.

The function returns a new structure rather than mutating in place, so the
caller's internal copy retains the raw value if it held one.
"""
from __future__ import annotations

from typing import Any

from ..ingestion.redaction import _is_secret_key, redact_text
from ..ingestion.redaction_registry import get_global_registry
from ..config.security_constants import EGRESS_ACK_FIELD

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

    Two passes on strings, in this order: ``redact_text()`` (key-shape and
    pattern redaction) first, then the secret variant registry (exact-value,
    so it is safe after key-based redaction). The registry holds the
    encoded forms of values that were deliberately egressed through the
    acknowledged path — see ``ingestion.redaction_registry``.

    Note the acked ``value`` field in ``_redact_dict`` deliberately does NOT
    reach this branch (it is passed through raw) — the registry protects
    every other path, never the one that was acked.

    Returns a new structure; the input is not mutated.
    """
    if isinstance(value, str):
        redacted = redact_text(value)
        return get_global_registry().redact_text(redacted)
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

    Acknowledged egress exception: a dict carrying
    ``_egress_ack: True`` (set only by ``config.queries.get_config_value``
    after verifying tier + acknowledgment + TTL) keeps its ``"value"``
    field raw. The exception is per-dict and per-field — everything else
    in the payload is still redacted, sibling dicts are unaffected, and
    the marker itself never egresses. This is what makes the per-key
    escape hatch behave identically for vocabulary keys and
    ``extra_secret_keys``-classified keys.
    """
    result = {}
    has_secret_key_field = False
    egress_ack = d.get(EGRESS_ACK_FIELD) is True

    # Rule 1: config-value-pair shape.
    key_val = d.get("key")
    if isinstance(key_val, str) and _is_secret_key(key_val):
        has_secret_key_field = True

    for k, v in d.items():
        # Acknowledged egress: enforcement metadata never egresses.
        if egress_ack and k == EGRESS_ACK_FIELD:
            continue
        # Acknowledged egress: this one value crosses deliberately.
        if egress_ack and k == "value":
            result[k] = v
            continue

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


def redact_result(payload: Any) -> Any:
    """Run the shared redaction core over a tool result payload.

    Call this as the last step before a result crosses a trust boundary.
    The MCP surface reaches it through ``mcp.response.mcp_response``;
    any future internal-results routing (recorded as an open decision in
    the packet) would call this directly.

    Two passes: structural (secret-key-aware dict redaction) then text
    (``redact_text()`` on every remaining string).  Non-string scalars
    pass through unchanged.

    Returns a new structure; the input is not mutated.
    """
    return _redact_value(payload)


#: How much of an error string may reach the model or the UI. Server- and
#: tool-controlled error text is the one path the executor's 2000-char
#: observation cap does not cover (A17 bug 6, A03 bug 5).
MAX_ERROR_CHARS = 2000


def redact_error_text(text: Any, *, limit: int = MAX_ERROR_CHARS) -> str:
    """The one treatment every error string gets before it is shown.

    A03-G5. Error messages are the quietest egress in the system: they
    are assembled from whatever failed -- a server's reply, a config
    line, an exception's ``str()`` -- and then interpolated into a
    message that reaches the model, the UI and the log. Three things
    happen here, in this order: pattern redaction, then the acknowledged-
    value registry (exact-value, so it is safe to run after key-shape
    redaction), then a cap that says it capped.

    Never raises: an error path that fails to render is worse than one
    that renders bluntly, so a failure inside the redactors falls back
    to the capped raw text rather than propagating.
    """
    if text is None:
        return ""
    raw = text if isinstance(text, str) else str(text)
    try:
        out = redact_text(raw, prose=True)
        out = get_global_registry().redact_text(out)
    except Exception:  # pragma: no cover - defensive
        out = raw
    if len(out) > limit:
        out = out[:limit].rstrip() + f"\n[error text truncated at {limit} characters]"
    return out
