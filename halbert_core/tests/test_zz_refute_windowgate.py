# SPDX-License-Identifier: GPL-3.0-or-later
"""Probe: is the window-tool surface reachable by a narrowed persona?"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from halbert_core.persona import guest
from halbert_core.persona.guest_tools import (
    GUEST_ALLOWED_TOOLS, GUEST_DENIED_TOOLS, is_tool_allowed_for_guest,
)
from halbert_core.tools.executor import ToolExecutor

WINDOW_TOOLS = ("list_windows", "capture_window", "capture_active_window")


@pytest.fixture(autouse=True)
def _fresh():
    guest.reset_for_tests()
    yield
    guest.reset_for_tests()


def _front(name="Marnie"):
    persona, _ = guest.GuestPersona.from_payload({"name": name})
    return guest.offer(persona, offered_by="h2-node", offered_by_name="H2")


def _exec() -> ToolExecutor:
    ex = ToolExecutor(web_search=True)
    ex.register_system_tools()
    ex.register_vision_tools()
    return ex


def test_window_tools_are_registered_at_all():
    ex = _exec()
    for t in WINDOW_TOOLS:
        assert t in ex.tools, t


def test_window_tools_are_on_the_denylist_not_the_allowlist():
    for t in WINDOW_TOOLS:
        assert t in GUEST_DENIED_TOOLS, t
        assert t not in GUEST_ALLOWED_TOOLS, t
        assert not is_tool_allowed_for_guest(t), t


def test_guest_never_sees_the_window_tools_in_its_schemas():
    ex = _exec()
    _front()
    names = {s["function"]["name"] for s in ex.get_schemas()}
    for t in WINDOW_TOOLS:
        assert t not in names, t


@pytest.mark.asyncio
async def test_guest_naming_a_window_tool_anyway_is_refused():
    ex = _exec()
    _front()
    for t in WINDOW_TOOLS:
        res = await ex.execute(t, {"window_id": 1})
        assert not res.success, t
        assert "not available while" in (res.error or ""), (t, res.error)


def test_a_guest_persona_cannot_declare_senses_at_all():
    persona, rejected = guest.GuestPersona.from_payload(
        {"name": "Marnie", "senses": {"vision": {"sources": ["frigate:patio"]}}}
    )
    assert not hasattr(persona, "senses") or getattr(persona, "senses", None) in (None, {}, [])
    assert "senses" in (rejected or []), rejected
