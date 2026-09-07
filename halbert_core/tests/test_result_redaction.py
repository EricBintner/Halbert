# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Parity pin for the shared redaction core (Packet 05 Phase C1).

``security.result_redaction.redact_result`` is the one implementation of
structural + text redaction; ``mcp.response.mcp_response`` is a thin
delegate over it. This table runs identical payloads through BOTH surfaces
and asserts byte-identical outputs — the drift-prevention pattern OpenClaw
uses everywhere two surfaces must never diverge.

Internal-executor routing is deliberately NOT done in this packet: whether
internal tool results need the same treatment is a recorded design decision
(the extraction alone kills the drift risk). The absolute behaviors are
pinned by ``test_mcp_response_boundary.py`` through the delegate; the cases
below pin the two surfaces to each other.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from halbert_core.mcp.response import mcp_response
from halbert_core.security.result_redaction import redact_result


# Cases named after the rule they exercise in the core (see
# mcp/response.py's boundary documentation). Every case must produce
# identical output through redact_result() and mcp_response().
CASES = [
    # 0: plain string, nothing to redact
    ("plain string", "nothing sensitive here"),
    # 1: config-value-pair shape — the primary MCP payload
    (
        "config value pair",
        {"path": "/etc/app.conf", "key": "password", "value": "hunter2"},
    ),
    # 2: secret dict key
    ("secret dict key", {"password": "hunter2"}),
    # 3: MCP field names are metadata, not config keys
    (
        "mcp metadata field names skipped",
        {"path": "/etc/app.conf", "key": "location", "value": "hunter2",
         "type": "str", "status": "ok"},
    ),
    # 4: nested structures — dict in list in dict
    (
        "nested dict/list",
        {"results": [
            {"path": "/a.conf", "key": "api_key", "value": "sk-abc123def456ghi789jkl"},
            {"path": "/b.conf", "note": "token=hunter2 inline"},
            ["password", "hunter2"],
        ]},
    ),
    # 5: acknowledged egress — the acked value crosses raw, marker dropped
    (
        "egress ack escape",
        {"path": "/etc/app.conf", "key": "password", "value": "hunter2",
         "_egress_ack": True, "tier": 2},
    ),
    # 6: the escape is per-dict — sibling dicts still redact
    (
        "egress ack does not leak to siblings",
        {"results": [
            {"key": "password", "value": "hunter2", "_egress_ack": True},
            {"key": "password", "value": "hunter2"},
        ]},
    ),
    # 7: nested secret dict keys under the marker
    (
        "nested secret keys under marker",
        {"_egress_ack": True, "value": "deliberate",
         "extra": {"password": "hunter2"}},
    ),
    # 8: non-string scalars pass through
    (
        "non-string scalars",
        {"port": 2222, "ratio": 0.5, "enabled": True, "note": None},
    ),
    # 9: text-level pattern redaction on every remaining string
    (
        "text pattern redaction",
        {"note": "connect with password=hunter2 please",
         "url": "https://user:hunter2@example.com/db"},
    ),
    # 10: empty and None shapes
    ("empty dict", {}),
    ("empty list", []),
    ("none", None),
    ("empty string", ""),
    # 11: tuples recurse too
    (
        "tuple structure",
        ({"key": "password", "value": "hunter2"}, "plain tail"),
    ),
    # 12: marker with non-True value does not escape
    (
        "marker must be exactly True",
        {"key": "password", "value": "hunter2", "_egress_ack": "True"},
    ),
]


@pytest.mark.parametrize("name,payload", CASES, ids=[c[0] for c in CASES])
def test_parity_redact_result_matches_mcp_response(name, payload):
    """Identical inputs through the core and the MCP boundary produce
    identical outputs — the two surfaces cannot drift."""
    via_core = redact_result(payload)
    via_mcp = mcp_response(payload)
    assert via_core == via_mcp, f"parity drift on case {name!r}"


@pytest.mark.parametrize("name,payload", CASES, ids=[c[0] for c in CASES])
def test_neither_surface_mutates_the_input(name, payload):
    """Both return new structures; the caller's raw copy is retained (the
    contract that lets the acked escape work at all)."""
    import copy

    before = copy.deepcopy(payload)
    redact_result(payload)
    mcp_response(payload)
    assert payload == before, f"input mutated on case {name!r}"


def test_absolute_spot_checks():
    """The parity pin proves the surfaces agree; these prove what they
    agree ON for the two rules the boundary is named for."""
    out = mcp_response({"path": "/x", "key": "password", "value": "hunter2"})
    assert out["value"] == "<secret>"

    acked = mcp_response(
        {"path": "/x", "key": "password", "value": "hunter2", "_egress_ack": True}
    )
    assert acked["value"] == "hunter2"
    assert "_egress_ack" not in acked

    # key=value text shapes redact through the pattern pass
    plain = mcp_response({"note": "connect with password=hunter2 ok"})
    assert "hunter2" not in plain["note"]


def test_registry_pass_composes_in_both_surfaces():
    """An egress-acked value (registered in the variant registry) redacts
    from bare text through BOTH surfaces identically — the composed
    two-pass (pattern first, registry second) is part of the shared core,
    not an MCP-boundary extra."""
    from halbert_core.ingestion import redaction_registry as _rr
    from halbert_core.ingestion.redaction_registry import REDACTION_PLACEHOLDER

    saved = _rr._GLOBAL
    _rr._GLOBAL = None
    try:
        _rr.get_global_registry().register("hunter2")
        payload = {"note": "the value hunter2 is set"}
        via_core = redact_result(payload)
        via_mcp = mcp_response(payload)
        assert via_core == via_mcp
        assert via_core["note"] == f"the value {REDACTION_PLACEHOLDER} is set"
    finally:
        _rr._GLOBAL = saved