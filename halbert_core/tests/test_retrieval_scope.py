# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Retrieval scoping: the boundary must hold on every path that retrieves.

A scope is a narrowing — "answer this from the host silo", "answer this from
the skill's own KB". Two things had defeated it:

* ``R06-F3``: PLANNING's context assembly honoured the scope, but SEARCHING
  called ``rag.search`` with no scope at all — and routing sends every
  non-greeting first loop with no tool call through SEARCHING, so for those
  turns the unscoped search *was* the retrieval.
* ``R06-F8``: the assembler decided "this adapter takes no scope" by calling
  it and catching TypeError, which cannot tell that case apart from a
  TypeError raised inside a scope-aware adapter — and then retried unscoped.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from halbert_core.agents.state_machine import AgentStateMachine
from halbert_core.context.assembler import (
    resolve_retrieval_scope,
    scope_kwargs_for,
)


# -----------------------------------------------------------------------------
# scope_kwargs_for — decide by signature, never by catching TypeError
# -----------------------------------------------------------------------------

class TestScopeKwargsFor:

    def test_scope_aware_source_is_narrowed(self):
        async def search(query, limit=5, scope=None, role=None):
            ...

        assert scope_kwargs_for(search, "host", None) == {"scope": "host"}
        assert scope_kwargs_for(search, "host", "ops") == {
            "scope": "host", "role": "ops",
        }

    def test_source_that_cannot_narrow_is_called_plainly(self):
        async def search(query, limit=5):
            ...

        assert scope_kwargs_for(search, "host", "ops") == {}

    def test_source_taking_only_role_gets_only_role(self):
        async def search(query, limit=5, role=None):
            ...

        assert scope_kwargs_for(search, "host", "ops") == {"role": "ops"}

    def test_kwargs_source_is_narrowed(self):
        async def search(query, limit=5, **kwargs):
            ...

        assert scope_kwargs_for(search, "host", None) == {"scope": "host"}

    def test_no_scope_asked_for_means_no_kwargs(self):
        async def search(query, limit=5, scope=None, role=None):
            ...

        assert scope_kwargs_for(search, None, None) == {}

    def test_a_typeerror_inside_the_adapter_is_not_read_as_unscoped(self):
        """The R06-F8 seam. A scope-aware adapter that raises TypeError from
        its own body must surface that error, not be silently re-run over
        everything."""
        calls = []

        class Adapter:
            async def search(self, query, limit=5, scope=None, role=None):
                calls.append(scope)
                raise TypeError("bug inside the adapter")

        adapter = Adapter()
        kwargs = scope_kwargs_for(adapter.search, "host", None)
        assert kwargs == {"scope": "host"}

        async def _drive():
            with pytest.raises(TypeError):
                await adapter.search("q", limit=5, **kwargs)

        import asyncio
        asyncio.run(_drive())
        # One scoped attempt, and no unscoped retry behind it.
        assert calls == ["host"]

    def test_unintrospectable_callable_is_not_guessed_at(self):
        # str.startswith and friends have no introspectable signature.
        assert scope_kwargs_for(len, "host", "ops") == {}


# -----------------------------------------------------------------------------
# resolve_retrieval_scope — a skill's own scope wins over the fallback
# -----------------------------------------------------------------------------

class TestResolveRetrievalScope:

    def test_skill_scope_wins_over_the_fallback(self):
        composed = MagicMock(scope="skill-kb", role=None)
        assert resolve_retrieval_scope(composed, "host") == ("skill-kb", None)

    def test_skill_role_alone_suppresses_the_fallback_scope(self):
        composed = MagicMock(scope=None, role="ops")
        assert resolve_retrieval_scope(composed, "host") == (None, "ops")

    def test_fallback_applies_when_no_skill_said_anything(self):
        assert resolve_retrieval_scope(None, "host") == ("host", None)

    def test_nothing_asked_for_stays_nothing(self):
        assert resolve_retrieval_scope(None, None) == (None, None)


# -----------------------------------------------------------------------------
# R06-F3 — SEARCHING must honour the turn's scope
# -----------------------------------------------------------------------------

class _ScopeRecordingRag:
    """A scope-aware RAG adapter that records how it was called."""

    def __init__(self):
        self.calls = []

    async def search(self, query, limit=5, scope=None, role=None):
        self.calls.append({"query": query, "scope": scope, "role": role})
        return []


def _mk_llm():
    llm = MagicMock()
    llm.chat = AsyncMock(
        return_value=MagicMock(content="ok", tool_calls=None, plan=None)
    )

    async def _stream(messages, **kwargs):
        yield "hello"

    llm.stream = _stream
    return llm


class TestSearchingHonoursTheTurnScope:

    @pytest.mark.asyncio
    async def test_a_scoped_turn_never_issues_an_unscoped_search(self):
        rag = _ScopeRecordingRag()
        agent = AgentStateMachine(llm_client=_mk_llm(), rag_service=rag, max_loops=5)

        async for _ in agent.process("deep scan the GPU", retrieval_scope="host"):
            pass

        assert rag.calls, "SEARCHING never reached the RAG adapter"
        assert all(c["scope"] == "host" for c in rag.calls), rag.calls

    @pytest.mark.asyncio
    async def test_an_unscoped_turn_is_still_searched(self):
        rag = _ScopeRecordingRag()
        agent = AgentStateMachine(llm_client=_mk_llm(), rag_service=rag, max_loops=5)

        async for _ in agent.process("what is sshd_config"):
            pass

        assert rag.calls
        assert all(c["scope"] is None for c in rag.calls)

    @pytest.mark.asyncio
    async def test_a_rag_source_that_cannot_narrow_still_retrieves(self):
        """Losing retrieval entirely would be worse than not narrowing."""
        calls = []

        class PlainRag:
            async def search(self, query, limit=5):
                calls.append(query)
                return []

        agent = AgentStateMachine(
            llm_client=_mk_llm(), rag_service=PlainRag(), max_loops=5
        )
        async for _ in agent.process("deep scan the GPU", retrieval_scope="host"):
            pass

        assert calls, "an un-narrowable source must still be searched"
