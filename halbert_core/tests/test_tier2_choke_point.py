# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""R-05 Phase B: nothing crosses the Tier-2 boundary uncoerced.

- **A03-G1 + bug 1** (fix-first row 7) -- ``redact_result`` returned
  anything that was not a str, dict or list untouched, and the MCP
  dispatcher then ran ``json.dumps(result, default=str)`` AFTER the pass.
  So ``{'blob': b'password=hunter2'}``, a ``PurePosixPath``, an Enum or
  any object with a ``__str__`` serialized its secret raw, downstream of
  the one place that was supposed to catch it. Coerce first, then redact,
  then re-scan the serialized text.
- **A03-G2** -- the registry runs BEFORE the pattern pass. Pattern
  redaction can rewrite part of a value, and an exact-value registry
  cannot match what has already been partly rewritten.
- **A03-G3** -- a self-referencing structure recursed until the stack
  gave out.
- **A03 bug 5** -- the confirmation message's args preview and the
  absent-server reason interpolated raw config text.
"""

import enum
import pathlib

import pytest

from halbert_core.ingestion.redaction_registry import get_global_registry
from halbert_core.security.result_redaction import redact_result

SECRET = "hunter2-hunter2-hunter2"


@pytest.fixture(autouse=True)
def _registered():
    get_global_registry().register(SECRET)
    yield


def test_bytes_are_coerced_before_redaction():
    out = redact_result({"blob": f"password={SECRET}".encode()})
    assert SECRET not in str(out)


def test_a_path_is_coerced_before_redaction():
    out = redact_result({"where": pathlib.PurePosixPath("/tmp") / SECRET})
    assert SECRET not in str(out)


def test_an_enum_is_coerced_before_redaction():
    class _E(enum.Enum):
        LEAK = f"token={SECRET}"

    assert SECRET not in str(redact_result({"e": _E.LEAK}))


def test_an_arbitrary_object_with_a_str_is_coerced():
    class _Thing:
        def __str__(self):
            return f"creds={SECRET}"

    assert SECRET not in str(redact_result({"t": _Thing()}))


def test_a_bare_non_native_value_is_coerced_too():
    assert SECRET not in str(redact_result(f"x={SECRET}".encode()))


def test_structural_values_survive_coercion():
    """Numbers and booleans are structure, not text: they stay themselves."""
    out = redact_result({"count": 3, "ok": True, "nothing": None})
    assert out == {"count": 3, "ok": True, "nothing": None}


def test_a_circular_structure_does_not_recurse_forever():
    payload = {"name": "loop"}
    payload["self"] = payload
    out = redact_result(payload)
    assert out["name"] == "loop"
    assert out["self"] is not None


def test_a_circular_list_is_survivable():
    items = ["a"]
    items.append(items)
    assert redact_result(items)[0] == "a"


def test_the_registry_runs_before_the_pattern_pass():
    """A03-G2: a pattern pass that rewrites PART of a value leaves the
    exact-value registry nothing to match."""
    import halbert_core.security.result_redaction as module
    import inspect

    source = inspect.getsource(module.redact_string)
    registry_at = source.index("get_global_registry")
    pattern_at = source.index("redact_text(get_global_registry")
    # The registry call is the INNER one: redact_text(registry(text)).
    assert registry_at > pattern_at, source
    assert "redact_text(get_global_registry().redact_text(" in source


# ---------------------------------------------------------------------------
# The serialized re-scan at the MCP dispatcher
# ---------------------------------------------------------------------------

def test_the_dispatchers_serialized_text_is_rescanned(monkeypatch):
    import halbert_core.mcp.server as server_mod

    def _leaky(args):
        # A shape redact_result cannot see into: the secret only appears
        # once default=str has stringified it.
        class _Opaque:
            def __str__(self):
                return f"key={SECRET}"

        return {"thing": _Opaque()}

    monkeypatch.setitem(server_mod.TOOL_HANDLERS, "leaky_obj", _leaky)
    monkeypatch.setattr(
        server_mod, "_MCP_READ_ONLY_TOOLS",
        server_mod._MCP_READ_ONLY_TOOLS | {"leaky_obj"})

    reply = server_mod.MCPServer().handle_request({
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": "leaky_obj", "arguments": {}},
    })
    assert SECRET not in str(reply)


# ---------------------------------------------------------------------------
# A03 bug 5: the args preview and the absent-server reason
# ---------------------------------------------------------------------------

def test_the_confirmation_args_preview_is_redacted():
    from halbert_core.tools.mcp_safety import mcp_args_preview

    preview = mcp_args_preview({"token": SECRET, "path": "/etc/hosts"})
    assert SECRET not in preview


def test_the_args_preview_is_capped():
    from halbert_core.tools.mcp_safety import mcp_args_preview

    assert len(mcp_args_preview({"blob": "x" * 100_000})) < 5_000


def test_the_absent_server_reason_is_redacted(monkeypatch):
    from types import SimpleNamespace

    import halbert_core.tools.mcp_safety as mcp_safety

    monkeypatch.setattr(
        mcp_safety, "_current_config",
        lambda: SimpleNamespace(
            servers=[SimpleNamespace(
                name=f"srv-{SECRET}", tool_risk={}, risk_override=None)],
            skipped_servers=[f"dropped-{SECRET}"],
            load_error="",
        ),
    )
    result = mcp_safety.classify_mcp_tool("mcp__gone__tool", {})
    assert SECRET not in result.reason
