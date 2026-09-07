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

Implementation
--------------
Since Packet 05 Phase C1 the redaction logic itself lives in
``security.result_redaction.redact_result`` — one implementation shared
by every surface that needs it, so no drift is possible between the MCP
boundary and any future internal-results routing (that routing is a
recorded open decision, deliberately not made here).  ``mcp_response``
is a thin delegate: identical input, identical output.  The design notes
(the two structural rules, the acknowledged-egress exception and its
NEW-01 known risk, the text passes, the known limits) moved with the
code — see ``security/result_redaction.py``.

The boundary function stays here, and stays the name every MCP tool
returns through, because the boundary is a *placement* property: what
matters is that every handler's last step before returning crosses it,
not what the function's body contains.
"""
from __future__ import annotations

from typing import Any

from ..security.result_redaction import redact_result

# Re-exported for the boundary's existing consumers (tests, the federation
# compute endpoint) and for anyone reasoning about where the rules live.
from ..security.result_redaction import (  # noqa: F401
    _redact_dict,
    _redact_value,
)


def mcp_response(payload: Any) -> Any:
    """Run the redaction boundary over an MCP tool response.

    Call this as the last step before returning from every MCP tool that
    may contain host config content::

        def get_config_value(path: str, key: str) -> dict:
            raw = _query_config_db(path, key)
            return mcp_response(raw)

    Structural (secret-key-aware dict redaction) then text
    (``redact_text()`` and the variant registry on every remaining
    string) — implemented by the shared core in
    ``security.result_redaction``; the parity test
    (``tests/test_result_redaction.py``) pins the delegate to it.

    Returns a new structure; the input is not mutated.
    """
    return redact_result(payload)