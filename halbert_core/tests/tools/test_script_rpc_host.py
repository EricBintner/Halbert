# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Host-side RPC: the ONLY place a stub call is served. Enforcement order is
fixed (Hermes order): token -> allow-list -> budget -> dispatch -> log.
Budget is consumed only by a dispatched call (refusals are free)."""
import pytest

from halbert_core.tools.script_rpc_host import ScriptRpcHost


def _host(allowed=("recall_memory",), budget=3):
    calls = []
    host = ScriptRpcHost(allowed_tools=set(allowed), budget=budget)
    host.dispatch_hook = lambda name, args: calls.append((name, args)) or {"ok": True}
    return host, calls


def test_valid_token_and_tool_dispatches():
    host, calls = _host()
    host.reveal_token_for_test = True
    tok = host.issue_token()
    assert host.handle(tok, "recall_memory", {"query": "x"}) == {"ok": True}
    assert calls == [("recall_memory", {"query": "x"})]


def test_bad_token_fails_closed():
    host, _ = _host()
    assert "error" in host.handle("wrong", "recall_memory", {})
    assert "error" in host.handle("", "recall_memory", {})


def test_disallowed_tool_refused_without_budget_cost():
    host, calls = _host(allowed=("recall_memory",), budget=1)
    before = host.budget_remaining
    res = host.handle(host.issue_token_for_test(), "write_file", {"path": "x"})
    assert "error" in res and "not available in scripts" in res["error"]
    assert host.budget_remaining == before  # refusal is free
    assert calls == []  # and never dispatched


def test_budget_exhaustion_then_dispatch_refused():
    host, calls = _host(budget=1)
    host.reveal_token_for_test = True
    tok = host.issue_token()
    host.handle(tok, "recall_memory", {})
    assert "error" in host.handle(tok, "recall_memory", {})


def test_token_is_a_real_secret():
    host, _ = _host()
    host.reveal_token_for_test = True
    tok = host.issue_token()
    assert len(tok) == 64  # token_hex(32)
    other, _ = _host()
    other.reveal_token_for_test = True
    assert tok != other.issue_token()  # per-run, never shared


def test_token_never_leaves_the_host_without_a_test_flag():
    host, _ = _host()
    with pytest.raises(RuntimeError):
        host.issue_token()  # production wiring uses bind_call(), not the token


def test_bind_call_closes_over_the_token():
    host, calls = _host()
    call = host.bind_call()
    assert call("recall_memory", {"query": "y"}) == {"ok": True}
    assert calls == [("recall_memory", {"query": "y"})]
    # A forged direct handle() without the token gets nothing.
    assert "error" in host.handle("", "recall_memory", {})


def test_dispatch_exception_surfaces_as_error_dict_never_raises():
    host, _ = _host()

    def boom(name, args):
        raise RuntimeError("hook exploded")

    host.dispatch_hook = boom
    res = host.handle(host.issue_token_for_test(), "recall_memory", {})
    assert "error" in res and "hook exploded" in res["error"]


def test_missing_hook_is_an_error_not_a_crash():
    host = ScriptRpcHost(allowed_tools={"recall_memory"}, budget=3)  # no hook wired
    res = host.handle(host.issue_token_for_test(), "recall_memory", {})
    assert "error" in res


def test_dispatched_calls_are_counted():
    host, _ = _host(budget=5)
    call = host.bind_call()
    call("recall_memory", {})
    call("recall_memory", {})
    call("write_file", {})  # refused: not counted
    assert host.calls_dispatched == 2
    assert host.budget_remaining == 3


def test_non_string_token_fails_closed():
    host, _ = _host()
    assert "error" in host.handle(None, "recall_memory", {})
    assert "error" in host.handle(b"not-a-string", "recall_memory", {})