# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Generated stub module: one def per allowed tool, compiled per-run from the
enabled-tool intersection. A disabled tool physically does not exist in the
module (Hermes pattern) — the model cannot keep trying it."""
from halbert_core.tools.script_stubs import generate_stub_module, DEFAULT_STUB_TOOLS


def test_module_is_plain_source_and_executes():
    src = generate_stub_module(tool_names=["recall_memory", "list_terminals"])
    assert "def recall_memory(" in src and "def list_terminals(" in src
    ns = {}
    exec(src, ns)  # noqa: S102 - testing generated source
    assert callable(ns["recall_memory"])


def test_disabled_tool_absent():
    src = generate_stub_module(tool_names=["recall_memory"])
    assert "write_file" not in src


def test_stub_call_reaches_rpc():
    captured = {}

    def fake_call(name, args):
        captured.update(name=name, args=args)
        return {"ok": True}

    src = generate_stub_module(tool_names=["recall_memory"])
    ns = {"_call": fake_call}
    exec(src, ns)  # noqa: S102
    result = ns["recall_memory"](query="scanner")
    assert captured == {"name": "recall_memory", "args": {"query": "scanner"}}
    assert result == {"ok": True}


def test_default_call_seam_refuses_until_wired():
    """Executed without a host-injected _call, the seam fails loudly rather
    than silently doing nothing."""
    src = generate_stub_module(tool_names=["recall_memory"])
    ns = {}
    exec(src, ns)  # noqa: S102
    try:
        ns["recall_memory"](query="x")
    except NotImplementedError as e:
        assert "wired" in str(e)
    else:
        raise AssertionError("stub call without a host must raise")


def test_docstrings_describe_return_shapes():
    src = generate_stub_module(tool_names=DEFAULT_STUB_TOOLS)
    assert "returns dicts" in src  # failure-hint discipline from Hermes: tools return structured data


def test_stub_set_is_kwonly_and_takes_no_positional_args():
    """The host RPC seam takes (name, args-dict); a stub that accepted
    positional args would let a script smuggle a non-dict through."""
    src = generate_stub_module(tool_names=["recall_memory"])
    ns = {}
    exec(src, ns)  # noqa: S102
    try:
        ns["recall_memory"]("positional")
    except TypeError:
        pass
    else:
        raise AssertionError("stubs must accept keyword arguments only")


def test_default_stub_tools_are_read_only():
    """F-1(b): the ratified default stub set is read-only — no write-plane
    tool may appear in it."""
    from halbert_core.persona.guest_tools import WRITE_PLANE_TOOLS

    assert not (set(DEFAULT_STUB_TOOLS) & WRITE_PLANE_TOOLS)