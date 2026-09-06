# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The guest tool profile — what a borrowed face may ask Halbert's body for.

``persona/guest_tools.py`` mirrors ``federation/tool_allowlist.py`` field for
field: a frozen allowlist, a paired denylist for testability, an import-time
self-check. It is applied at the one per-turn choke point
(``ToolExecutor.get_schemas``) so a disallowed tool is absent from the
schema list the model receives — and again at ``ToolExecutor.execute``,
because a guest's conversation history contains Halbert's own earlier turns
calling ``run_command`` and a model can imitate a call it cannot see.

Design: ``.handoff/DESIGN-GUEST-PERSONA-2026-09-06.md`` §4, invariant I1.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from halbert_core.persona import guest
from halbert_core.persona import sibling
from halbert_core.persona.guest import GuestHome
from halbert_core.persona.guest_tools import (
    GUEST_ALLOWED_TOOLS,
    GUEST_DENIED_TOOLS,
    GUEST_ONLY_TOOLS,
    HANDBACK_TOOL_NAME,
    HANDBACK_TOOL_SCHEMA,
    RECALL_GUEST_MEMORY_TOOL_NAME,
    WRITE_PLANE_TOOLS,
    filter_tools_for_guest,
    is_tool_allowed_for_guest,
)
from halbert_core.tools.executor import ToolExecutor


@pytest.fixture(autouse=True)
def _fresh_guest_state():
    guest.reset_for_tests()
    yield
    guest.reset_for_tests()


def _front(name="Marnie"):
    persona, _ = guest.GuestPersona.from_payload({"name": name})
    return guest.offer(persona, offered_by="h2-node", offered_by_name="H2")


def _every_agent_tool() -> ToolExecutor:
    """An executor with every registrar run, the way ``get_agent`` runs them
    when every optional integration is switched on."""
    from halbert_core.integrations.frigate import frigate_tools
    from halbert_core.integrations.home_assistant.ha_tool import register_ha_tools

    executor = ToolExecutor(web_search=True)
    executor.register_system_tools()
    executor.register_vision_tools()
    register_ha_tools(executor)

    class _Configured:
        def is_configured(self):
            return True

    with patch.object(frigate_tools, "load_frigate_config", return_value=_Configured()):
        frigate_tools.register_frigate_tools(executor)
    return executor


# ---------------------------------------------------------------------------
# The lists
# ---------------------------------------------------------------------------

class TestGuestToolAllowlist:

    def test_allowed_tools_pass_through(self):
        for tool in GUEST_ALLOWED_TOOLS:
            assert is_tool_allowed_for_guest(tool), tool

    def test_denied_tools_are_filtered(self):
        for tool in GUEST_DENIED_TOOLS:
            assert not is_tool_allowed_for_guest(tool), tool

    def test_unknown_tool_is_denied(self):
        assert not is_tool_allowed_for_guest("some_random_tool")
        assert not is_tool_allowed_for_guest("shell_exec")

    def test_allowlist_and_denylist_do_not_overlap(self):
        assert not (GUEST_ALLOWED_TOOLS & GUEST_DENIED_TOOLS)

    def test_the_host_is_never_on_the_list(self):
        """System-level work is Halbert's side of the house."""
        for tool in ("run_command", "read_file", "write_file", "list_directory",
                     "terminal_blocks", "capture_screenshot", "capture_window",
                     "capture_active_window", "capture_and_ocr", "list_windows",
                     "get_process_list", "get_service_status", "web_search"):
            assert tool in GUEST_DENIED_TOOLS, tool

    def test_the_home_and_the_view_are_on_the_list(self):
        for tool in ("ha_get_entity_state", "ha_call_service", "frigate_list_cameras",
                     "frigate_get_events", "capture_webcam", "detect_motion",
                     RECALL_GUEST_MEMORY_TOOL_NAME, HANDBACK_TOOL_NAME):
            assert tool in GUEST_ALLOWED_TOOLS, tool

    def test_the_guest_reads_what_it_wrote_and_nothing_of_halberts(self):
        """D3 / I6: no read of Halbert's memory in v1."""
        assert "recall_memory" in GUEST_DENIED_TOOLS
        assert "recall_thread" in GUEST_DENIED_TOOLS
        assert "resume_thread" in GUEST_DENIED_TOOLS

    def test_the_write_plane_never_enters_the_allowlist(self):
        """Design §6: the hash-chained audit log receives user words only
        through the write plane, so a guest turn never reaches it as long as
        this holds."""
        assert WRITE_PLANE_TOOLS >= {"run_command", "write_file", "write_config", "schedule_cron", "terminal_blocks"}
        assert not (GUEST_ALLOWED_TOOLS & WRITE_PLANE_TOOLS)

    def test_guest_only_tools_are_on_the_allowlist_and_nowhere_in_the_registry(self):
        registered = set(_every_agent_tool().tools)
        for name, schema in GUEST_ONLY_TOOLS.items():
            assert name in GUEST_ALLOWED_TOOLS
            assert name not in registered
            assert schema["name"] == name

    def test_filter_keeps_order_and_drops_the_rest(self):
        tools = ["run_command", "ha_get_entity_state", "read_file", "recall_memory", "capture_webcam"]
        assert filter_tools_for_guest(tools) == ["ha_get_entity_state", "capture_webcam"]
        assert filter_tools_for_guest([]) == []

    def test_every_allowlisted_tool_is_a_real_agent_tool(self):
        """The design named four tools; one of them did not exist. Pin the
        allowlist to the registry so that cannot recur."""
        registered = set(_every_agent_tool().tools)
        missing = (GUEST_ALLOWED_TOOLS - set(GUEST_ONLY_TOOLS)) - registered
        assert not missing, f"allowlisted but not registered anywhere: {sorted(missing)}"

    def test_every_registered_tool_has_been_classified(self):
        """A new agent tool is denied by default, but the decision must be
        written down: it goes on one list or the other."""
        registered = set(_every_agent_tool().tools)
        unclassified = registered - GUEST_ALLOWED_TOOLS - GUEST_DENIED_TOOLS
        assert not unclassified, f"neither allowed nor denied for a guest: {sorted(unclassified)}"

    def test_handback_schema_is_a_function_tool(self):
        assert HANDBACK_TOOL_SCHEMA["name"] == HANDBACK_TOOL_NAME
        assert "parameters" in HANDBACK_TOOL_SCHEMA


# ---------------------------------------------------------------------------
# The mask at the choke point
# ---------------------------------------------------------------------------

def _stub_executor(calls):
    executor = ToolExecutor(web_search=False, audit_fn=lambda **kw: calls.append(("audit", kw)))

    async def _run(args):
        calls.append(("run_command", args))
        return "ran"

    async def _look(args):
        calls.append(("capture_webcam", args))
        return "looked"

    executor.register("run_command", _run, {"name": "run_command", "parameters": {}})
    executor.register("capture_webcam", _look, {"name": "capture_webcam", "parameters": {}})
    return executor


class TestSchemasWhileAGuestFronts:

    def test_without_a_guest_the_schemas_are_untouched(self):
        executor = _stub_executor([])
        names = [s["function"]["name"] for s in executor.get_schemas()]
        assert "run_command" in names
        assert HANDBACK_TOOL_NAME not in names

    def test_with_a_guest_the_model_never_sees_the_host_tools(self):
        executor = _stub_executor([])
        _front()
        names = [s["function"]["name"] for s in executor.get_schemas()]
        assert "run_command" not in names
        assert "capture_webcam" in names
        assert RECALL_GUEST_MEMORY_TOOL_NAME in names
        assert set(names) <= GUEST_ALLOWED_TOOLS

    def test_the_handback_tool_is_offered_only_while_a_guest_fronts(self):
        executor = _stub_executor([])
        _front()
        names = [s["function"]["name"] for s in executor.get_schemas()]
        assert HANDBACK_TOOL_NAME in names
        guest.withdraw()
        names = [s["function"]["name"] for s in executor.get_schemas()]
        assert HANDBACK_TOOL_NAME not in names
        assert "run_command" in names


class TestExecuteWhileAGuestFronts:

    async def test_a_hidden_tool_named_anyway_is_refused_not_run(self):
        calls = []
        executor = _stub_executor(calls)
        _front("Marnie")
        result = await executor.execute("run_command", {"command": "ls"}, session_id="s1")
        assert result.success is False
        assert "Marnie" in result.error
        assert ("run_command", {"command": "ls"}) not in calls
        audits = [kw for kind, kw in calls if kind == "audit"]
        assert audits and audits[-1]["success"] is False and audits[-1]["tool"] == "run_command"

    async def test_an_allowed_tool_still_runs(self):
        calls = []
        executor = _stub_executor(calls)
        _front()
        result = await executor.execute("capture_webcam", {"q": "garage"}, session_id="s1")
        assert result.success is True
        assert result.result == "looked"
        assert ("capture_webcam", {"q": "garage"}) in calls

    async def test_without_a_guest_everything_runs_as_before(self):
        calls = []
        executor = _stub_executor(calls)
        result = await executor.execute("run_command", {"command": "ls"}, session_id="s1")
        assert result.success is True
        assert ("run_command", {"command": "ls"}) in calls

    async def test_handback_ends_the_session_and_tells_the_model_who_is_speaking(self):
        calls = []
        executor = _stub_executor(calls)
        session = _front("Marnie")
        result = await executor.execute(HANDBACK_TOOL_NAME, {"reason": "system work"}, session_id="s1")
        assert result.success is True
        assert guest.current_guest() is None
        assert session.end_reason == "handback"
        assert "Marnie" in result.result and "handed" in result.result.lower()

    async def test_handback_without_a_guest_is_refused(self):
        executor = _stub_executor([])
        result = await executor.execute(HANDBACK_TOOL_NAME, {}, session_id="s1")
        assert result.success is False

    async def test_after_handback_the_host_tools_come_back(self):
        executor = _stub_executor([])
        _front()
        await executor.execute(HANDBACK_TOOL_NAME, {}, session_id="s1")
        names = [s["function"]["name"] for s in executor.get_schemas()]
        assert "run_command" in names
        assert HANDBACK_TOOL_NAME not in names


class TestRecallGuestMemory:

    def _home_session(self):
        persona, _ = guest.GuestPersona.from_payload({"name": "Marnie"})
        home = GuestHome(base_url="http://127.0.0.1:8002", persona_id="marnie-7")
        return guest.offer(persona, offered_by="h2-node", home=home)

    async def test_recall_searches_the_guests_own_home(self, monkeypatch):
        calls = []

        def fake_transport(method, url, body, headers):
            calls.append((method, url, body))
            return 200, {"memories": [{"content": "They showed me the garden."}, {"content": "Tea at nine."}]}

        monkeypatch.setattr(sibling, "default_transport", fake_transport)
        self._home_session()
        executor = _stub_executor([])
        result = await executor.execute(RECALL_GUEST_MEMORY_TOOL_NAME, {"query": "garden"}, session_id="s1")
        assert result.success is True
        assert "They showed me the garden." in result.result
        assert "Tea at nine." in result.result
        assert calls and calls[0][1].endswith("/api/personas/marnie-7/memory/search")

    async def test_recall_without_a_home_says_so(self):
        _front()
        executor = _stub_executor([])
        result = await executor.execute(RECALL_GUEST_MEMORY_TOOL_NAME, {"query": "garden"}, session_id="s1")
        assert result.success is True
        assert "no memory" in result.result.lower()

    async def test_recall_without_a_guest_is_refused(self):
        executor = _stub_executor([])
        result = await executor.execute(RECALL_GUEST_MEMORY_TOOL_NAME, {"query": "x"}, session_id="s1")
        assert result.success is False

    async def test_a_dead_home_is_an_honest_empty_answer(self, monkeypatch):
        def dead(method, url, body, headers):
            raise ConnectionError("down")

        monkeypatch.setattr(sibling, "default_transport", dead)
        self._home_session()
        executor = _stub_executor([])
        result = await executor.execute(RECALL_GUEST_MEMORY_TOOL_NAME, {"query": "garden"}, session_id="s1")
        assert result.success is True
        assert "could not reach" in result.result.lower()
