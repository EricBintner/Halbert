# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Plan A / A7: thread SSE events, StateContext thread fields, the three
thread meta-tool schemas and their SAFE classification."""

import json
import pytest

from halbert_core.agents.events import StreamEvent
from halbert_core.agents.states import StateContext
from halbert_core.tools.safety import ToolSafetyFramework, RiskLevel, THREAD_META_TOOLS
from halbert_core.tools.executor import ToolExecutor


class TestThreadEvents:
    def test_thread_started_shape(self):
        d = StreamEvent.thread_started(
            "s1", "t2", "Scanner share", reason="new subject", previous_thread_id="t1"
        ).to_dict()
        assert d["type"] == "thread_started" and d["session_id"] == "s1"
        assert d["thread_id"] == "t2" and d["title"] == "Scanner share"
        assert d["reason"] == "new subject" and d["previous_thread_id"] == "t1"
        json.dumps(d)

    def test_thread_started_defaults(self):
        d = StreamEvent.thread_started("s1", "t2", "Untitled").to_dict()
        assert d["reason"] == "" and d["previous_thread_id"] is None

    def test_thread_recalled_shape_and_copies_terms(self):
        terms = ["samba", "share"]
        d = StreamEvent.thread_recalled("s1", "t9", "Samba media share", "2026-07-14", terms, "auto").to_dict()
        terms.append("x")
        assert d["type"] == "thread_recalled" and d["thread_id"] == "t9"
        assert d["title"] == "Samba media share" and d["date"] == "2026-07-14"
        assert d["match_terms"] == ["samba", "share"] and d["mode"] == "auto"
        assert d["last_turn_id"] is None
        json.dumps(d)

    def test_thread_recalled_carries_last_turn_id(self):
        d = StreamEvent.thread_recalled(
            "s1", "t9", "Samba media share", "2026-07-14", [], "tool", last_turn_id="turn-77"
        ).to_dict()
        assert d["last_turn_id"] == "turn-77" and d["mode"] == "tool"
        json.dumps(d)

    def test_thread_store_error_and_turn_persisted(self):
        e = StreamEvent.thread_store_error("s1", "disk full").to_dict()
        assert e["type"] == "thread_store_error" and e["message"] == "disk full"
        t = StreamEvent.turn_persisted("s1", "t2", "turn-abc").to_dict()
        assert t["type"] == "turn_persisted" and t["thread_id"] == "t2" and t["turn_id"] == "turn-abc"
        sse = StreamEvent.turn_persisted("s1", "t2", "turn-abc").to_sse()
        assert sse.startswith("data: ") and sse.endswith("\n\n")
        assert json.loads(sse[6:].strip())["turn_id"] == "turn-abc"


class TestStateContextThreadFields:
    def test_defaults_and_unshared_lists(self):
        a = StateContext(session_id="a", request_id="r", user_query="q")
        b = StateContext(session_id="b", request_id="r", user_query="q")
        assert a.thread_id is None and a.continuity_hint == ""
        assert a.thread_switched is False and a.thread_manager is None
        assert a.recalled_threads == [] and a.terminal_session_ids == []
        assert a.turn_context is None
        a.recalled_threads.append({"thread_id": "t"})
        a.terminal_session_ids.append("term-1")
        assert b.recalled_threads == [] and b.terminal_session_ids == []


class TestMetaToolSchemas:
    def test_registered_short_and_shaped(self):
        schemas = {s["function"]["name"]: s["function"] for s in ToolExecutor().get_schemas()}
        assert set(THREAD_META_TOOLS) == {"new_thread", "recall_thread", "resume_thread"}
        for name in THREAD_META_TOOLS:
            assert name in schemas
            assert len(schemas[name]["description"]) <= 60, name
        assert schemas["new_thread"]["parameters"]["required"] == ["title", "reason"]
        assert set(schemas["new_thread"]["parameters"]["properties"]) == {"title", "reason"}
        assert set(schemas["recall_thread"]["parameters"]["properties"]) == {"query", "thread_id"}
        assert schemas["recall_thread"]["parameters"]["required"] == []
        assert schemas["resume_thread"]["parameters"]["required"] == ["thread_id"]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("name,args", [
        ("new_thread", {"title": "x", "reason": "y"}),
        ("recall_thread", {"query": "samba"}),
        ("resume_thread", {"thread_id": "t1"}),
    ])
    async def test_execute_is_an_inline_stub(self, name, args):
        result = await ToolExecutor().execute(name, args, session_id="s")
        assert result.success is True and result.result == "handled inline"
        assert result.requires_confirmation is False
        assert result.risk_level == RiskLevel.SAFE


class TestMetaToolSafety:
    @pytest.mark.parametrize("name", ["new_thread", "recall_thread", "resume_thread"])
    def test_meta_tools_are_safe(self, name):
        r = ToolSafetyFramework().classify(name, {})
        assert r.risk_level == RiskLevel.SAFE and r.allowed is True
        assert r.requires_confirmation is False

    def test_unknown_tool_still_medium(self):
        assert ToolSafetyFramework().classify("frobnicate", {}).risk_level == RiskLevel.MEDIUM
