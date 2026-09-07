# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Echo-guard wiring at the outbound seam (Packet 05 Phase B2).

The seam is the RESPONDING finalize commit in
``agents.state_machine._handle_responding``: the point where
``clean_response`` becomes the turn's committed text. Downstream of that
commit, the same text reaches (1) the ``response_complete`` SSE event the
frontend adopts as the rendered bubble, (2) ``_end_turn``'s persisted
assistant row via ``ctx.response_chunks``, and (3) the modality demux
(display text, speech text, TTS egress) — so one scan-and-redact covers
every user-visible surface of the final reply.

The injection site is the acknowledged-egress path in
``config.queries.get_config_value`` (the same site that feeds the variant
registry), which is what makes the two layers independent: the registry
redacts known forms, the guard detects echoes of the injected material
and raises the structured warning.
"""
import logging
import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from halbert_core.agents.conversation_sqlite import SqliteConversationStore
from halbert_core.agents.state_machine import AgentStateMachine
from halbert_core.agents.threads import ThreadManager
from halbert_core.ingestion import redaction_registry as _rr
from halbert_core.prompts.agent_prompts import AgentPromptBuilder
from halbert_core.security import echo_guard as _eg
from halbert_core.tools.executor import ToolExecutor
from halbert_core.tools.safety import ToolSafetyFramework

# A tier-2 secret long enough that the guard's default 80-char window sees
# a full chunk of it inside a reply (the guard's design floor — OpenClaw's
# 80-char contiguous chunk rule).
SECRET = (
    "sk-live-9f8e7d6c5b4a3f2e1d0c9b8a7f6e5d4c3b2a1f0e9d8c7b6a5f4e3d2c1b0a987654321"
    "9f8e7d6c5b4a3f2e1d"
)
REPLY_WITH_ECHO = (
    f"Heads up: the password is {SECRET} for tonight's deploy window, ok?"
)
REPLY_PARAPHRASED = (
    "I confirmed the password is configured correctly; I won't repeat it here."
)


@pytest.fixture(autouse=True)
def _fresh_globals():
    """Isolate the process-global registry and echo guard around every
    test here — this file deliberately populates both via the ack path."""
    saved_reg, saved_guard = _rr._GLOBAL, _eg._GLOBAL
    _rr._GLOBAL = None
    _eg._GLOBAL = None
    try:
        yield
    finally:
        _rr._GLOBAL = saved_reg
        _eg._GLOBAL = saved_guard


@pytest.fixture
def temp_config_env(tmp_path, monkeypatch):
    """Real config env (same shape as test_redaction_registry.py's fixture):
    a small ini file snapshotted unredacted into a temp canon DB."""
    from halbert_core.config.snapshot import snapshot

    config_file = tmp_path / "test.conf"
    config_file.write_text(
        "[Service]\n"
        "ExecStart=/usr/bin/myapp\n"
        f"Password={SECRET}\n"
        "Token=abcd9876\n"
        "Enabled=true\n"
    )
    manifest = tmp_path / "manifest.yml"
    manifest.write_text(
        f"include:\n  - '{config_file}'\n" "exclude: []\n" "parsers: {}\n"
    )
    canon_dir = tmp_path / "canon"
    snap_dir = tmp_path / "snapshots"
    canon_dir.mkdir()
    snap_dir.mkdir()
    monkeypatch.setattr("halbert_core.config.snapshot.CANON_DIR", str(canon_dir))
    monkeypatch.setattr("halbert_core.config.snapshot.SNAP_DIR", str(snap_dir))
    monkeypatch.setattr("halbert_core.config.queries.CANON_DIR", str(canon_dir))
    monkeypatch.setattr("halbert_core.config.queries.SNAP_DIR", str(snap_dir))
    monkeypatch.setattr("halbert_core.config.drift.CANON_DIR", str(canon_dir))
    snapshot(str(manifest), redact=False)
    return str(config_file)


class ScriptedLLM:
    """A one-turn LLM: chat() answers with no tool calls, stream() yields
    the scripted reply (the same shape test_thread_e2e drives)."""

    def __init__(self, reply: str):
        self._reply = reply
        self.stream_prompts = []

    async def chat(self, messages, tools=None, **kwargs):
        return SimpleNamespace(content="", tool_calls=None, plan=None)

    async def stream(self, messages, **kwargs):
        self.stream_prompts.append("\n".join(m.get("content", "") for m in messages))
        yield self._reply


@pytest.fixture
def store(tmp_path):
    s = SqliteConversationStore(str(tmp_path / "threads.db"))
    yield s
    s.close()


@pytest.fixture
def tm(store):
    return ThreadManager(store, now=lambda: 1_750_000_000.0)


def _ack_the_secret(config_path: str) -> None:
    """Push the secret through the real acknowledged-egress path, which is
    what feeds both the variant registry (A2) and the echo guard (B2)."""
    from halbert_core.config.queries import get_config_value

    result = get_config_value(
        config_path, "Password", secret_tier="cloud_ok_acknowledged"
    )
    assert result["_egress_ack"] is True  # the ack path, not the locked path
    assert result["value"] == SECRET


async def _run_turn(agent, tm) -> list:
    events = []
    async for event in agent.process(
        "what is the deploy password?", session_id="sess-echo", thread_manager=tm
    ):
        events.append(event)
    return events


def _agent(llm) -> AgentStateMachine:
    return AgentStateMachine(
        llm_client=llm,
        tool_executor=ToolExecutor(safety=ToolSafetyFramework()),
        prompt_builder=AgentPromptBuilder(),
        max_loops=2,
    )


# ---------------------------------------------------------------------------
# The integration case: acked value, echoed verbatim, redacted + warned
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_acked_value_echoed_in_reply_arrives_redacted_with_warning(
    temp_config_env, tm, store, caplog
):
    _ack_the_secret(temp_config_env)
    assert len(_eg.get_global_echo_guard()) > 0  # the ack site noted it

    caplog.set_level(logging.WARNING, logger="halbert.agents.state_machine")
    agent = _agent(ScriptedLLM(REPLY_WITH_ECHO))
    events = await _run_turn(agent, tm)

    # the committed reply — what the frontend renders (response_complete)
    # and what the timeline stores — carries no raw secret
    complete = next(e for e in events if e.type == "response_complete")
    assert SECRET not in complete.data["content"]
    assert "<secret>" in complete.data["content"]

    # the persisted assistant row is the same redacted text
    rows = store.recent_messages(
        store.current_open_thread()["thread_id"], limit=8
    )
    assistant_rows = [r for r in rows if r["role"] == "assistant"]
    assert len(assistant_rows) == 1
    assert SECRET not in assistant_rows[0]["content"]
    assert "<secret>" in assistant_rows[0]["content"]

    # the structured warning is logged, with a hash — never the material
    assert "echo_guard_flagged" in caplog.text
    assert "match_sha256" in caplog.text
    assert SECRET not in caplog.text


@pytest.mark.asyncio
async def test_paraphrased_reply_is_not_flagged(temp_config_env, tm, store, caplog):
    _ack_the_secret(temp_config_env)

    caplog.set_level(logging.WARNING, logger="halbert.agents.state_machine")
    agent = _agent(ScriptedLLM(REPLY_PARAPHRASED))
    events = await _run_turn(agent, tm)

    complete = next(e for e in events if e.type == "response_complete")
    assert complete.data["content"] == REPLY_PARAPHRASED  # untouched
    assert "echo_guard_flagged" not in caplog.text


# ---------------------------------------------------------------------------
# The injection site: only the acknowledged-egress path feeds the guard
# ---------------------------------------------------------------------------


def test_locked_tier2_path_does_not_note_the_guard(temp_config_env):
    from halbert_core.config.queries import get_config_value

    locked = get_config_value(temp_config_env, "Password", secret_tier="local_only")
    assert locked["redacted"] is True
    assert len(_eg.get_global_echo_guard()) == 0

    tier0 = get_config_value(temp_config_env, "Enabled")
    assert tier0["tier"] == 0
    assert len(_eg.get_global_echo_guard()) == 0


def test_acked_short_secret_noted_but_below_guard_floor(temp_config_env, tmp_path):
    """A value shorter than the guard window is noted (whole-text chunk)
    but a reply that merely embeds it is not flagged — the guard's 80-char
    design floor. Pinning this documents the boundary: short exact echoes
    are the registry's job at surfaces that run the registry pass, not the
    guard's at the reply seam."""
    from halbert_core.config.queries import get_config_value

    result = get_config_value(
        temp_config_env, "Token", secret_tier="cloud_ok_acknowledged"
    )
    assert result["_egress_ack"] is True
    guard = _eg.get_global_echo_guard()
    assert len(guard) > 0
    # a reply embedding the short value does not reproduce a whole window
    assert not guard.scan_outbound("the token is abcd9876 for the api")