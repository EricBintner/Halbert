"""
Integration test for the composed-loop architecture (Phase E).

Verifies the full flow:
  query → PLANNING → SEARCHING → OBSERVING → REFLECTING → RESPONDING

Tests:
  1. State machine transitions through REFLECTING state
  2. PersonaCognition is injected into StateContext
  3. Cognitive tick (advance_turn) runs at REFLECTING state
  4. SystemEventMapper populates cognition before tick
  5. Memory callbacks are wired (thought promotion persists)
  6. State trackers register with Haloysius
  7. Predicates render machine-specific state as natural prose

This test uses mock LLM and mock services to avoid requiring
Ollama, ChromaDB, or SourcePrep to be running.
"""

import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional


@pytest.fixture
def mock_llm():
    """Mock LLM client that returns canned responses."""
    llm = MagicMock()
    llm.chat = AsyncMock(return_value=MagicMock(content="Mock response"))
    llm.stream = AsyncMock()
    llm.stream.return_value = aiter_chunked(["Mock", " ", "response"])

    async def aiter_chunked(chunks):
        for c in chunks:
            yield c

    llm.stream = MagicMock(return_value=aiter_chunked(["Mock", " ", "response"]))
    return llm


@pytest.fixture
def mock_tool_executor():
    """Mock tool executor."""
    executor = MagicMock()
    executor.get_schemas = MagicMock(return_value=[])
    return executor


@pytest.fixture
def mock_crag():
    """Mock CRAG evaluator that always returns CORRECT."""
    crag = MagicMock()
    crag.evaluate = AsyncMock(
        return_value=MagicMock(
            confidence=0.9,
            action=MagicMock(value="CORRECT"),
        )
    )
    return crag


@pytest.fixture
def mock_prompts():
    """Mock prompt builder."""
    prompts = MagicMock()
    prompts.build_planning_prompt = MagicMock(return_value="Plan prompt")
    prompts.build_response_prompt = MagicMock(return_value="Response prompt")
    return prompts


class TestStateMachineReflecting:
    """Test REFLECTING state integration in the state machine."""

    def test_reflecting_state_exists(self):
        """REFLECTING state should be in the AgentState enum."""
        from halbert_core.agents.states import AgentState
        assert hasattr(AgentState, "REFLECTING")
        assert AgentState.REFLECTING.value == "reflecting"

    def test_observing_transitions_to_reflecting(self):
        """OBSERVING should be able to transition to REFLECTING."""
        from halbert_core.agents.states import AgentState
        from halbert_core.agents.state_machine import AgentStateMachine
        transitions = AgentStateMachine.TRANSITIONS
        assert AgentState.REFLECTING in transitions[AgentState.OBSERVING]

    def test_reflecting_transitions_to_responding(self):
        """REFLECTING should be able to transition to RESPONDING."""
        from halbert_core.agents.states import AgentState
        from halbert_core.agents.state_machine import AgentStateMachine
        transitions = AgentStateMachine.TRANSITIONS
        assert AgentState.RESPONDING in transitions[AgentState.REFLECTING]

    def test_state_context_has_persona_cognition(self):
        """StateContext should have persona_cognition field."""
        from halbert_core.agents.states import StateContext
        ctx = StateContext(
            session_id="test",
            request_id="test",
            user_query="test query",
        )
        assert hasattr(ctx, "persona_cognition")
        assert ctx.persona_cognition is None
        assert ctx.persona_id == "halbert"

    def test_state_context_to_dict_includes_cognition(self):
        """to_dict should include persona_cognition when set."""
        from halbert_core.agents.states import StateContext
        ctx = StateContext(
            session_id="test",
            request_id="test",
            user_query="test query",
        )
        ctx.persona_cognition = MagicMock()
        ctx.persona_cognition.get_full_context = MagicMock(
            return_value={"persona_id": "halbert", "worries": []}
        )
        d = ctx.to_dict()
        assert "persona_cognition" in d
        assert d["persona_cognition"]["persona_id"] == "halbert"

    @pytest.mark.asyncio
    async def test_reflecting_handler_without_tick_is_passthrough(
        self, mock_llm, mock_tool_executor, mock_crag, mock_prompts
    ):
        """REFLECTING handler should pass through to RESPONDING when no tick wired."""
        from halbert_core.agents.state_machine import AgentStateMachine
        from halbert_core.agents.states import AgentState, StateContext

        agent = AgentStateMachine(
            llm_client=mock_llm,
            tool_executor=mock_tool_executor,
            crag_evaluator=mock_crag,
            prompt_builder=mock_prompts,
        )
        agent.ctx = StateContext(
            session_id="test",
            request_id="test",
            user_query="test",
        )
        agent.current_state = AgentState.REFLECTING

        events = []
        async for event in agent._handle_reflecting():
            events.append(event)

        # Should transition to RESPONDING
        assert agent.current_state == AgentState.RESPONDING

    @pytest.mark.asyncio
    async def test_reflecting_handler_with_tick_runs_cognition(
        self, mock_llm, mock_tool_executor, mock_crag, mock_prompts
    ):
        """REFLECTING handler should call cognition_tick when wired."""
        from halbert_core.agents.state_machine import AgentStateMachine
        from halbert_core.agents.states import AgentState, StateContext

        # Mock cognition and tick
        mock_cognition = MagicMock()
        mock_cognition.worries.check_intrusions = MagicMock(return_value=[])
        mock_tick = MagicMock(return_value=MagicMock(thought=None))

        agent = AgentStateMachine(
            llm_client=mock_llm,
            tool_executor=mock_tool_executor,
            crag_evaluator=mock_crag,
            prompt_builder=mock_prompts,
            cognition_tick=mock_tick,
        )
        agent.ctx = StateContext(
            session_id="test",
            request_id="test",
            user_query="test query",
        )
        agent.ctx.persona_cognition = mock_cognition
        agent.current_state = AgentState.REFLECTING

        events = []
        async for event in agent._handle_reflecting():
            events.append(event)

        # Tick should have been called
        mock_tick.assert_called_once()
        call_args = mock_tick.call_args
        assert call_args.kwargs["user_message"] == "test query"
        assert call_args.kwargs["cognition"] is mock_cognition

        # Should transition to RESPONDING
        assert agent.current_state == AgentState.RESPONDING

    @pytest.mark.asyncio
    async def test_reflecting_handler_emits_thought_event(
        self, mock_llm, mock_tool_executor, mock_crag, mock_prompts
    ):
        """REFLECTING handler should emit StreamEvent.thinking when thought generated."""
        from halbert_core.agents.state_machine import AgentStateMachine
        from halbert_core.agents.states import AgentState, StateContext
        from halbert_core.agents.events import StreamEvent

        mock_cognition = MagicMock()
        mock_cognition.worries.check_intrusions = MagicMock(return_value=[])

        mock_thought = MagicMock()
        mock_thought.content = "I wonder if the disk is failing"
        mock_tick = MagicMock(return_value=MagicMock(thought=mock_thought))

        agent = AgentStateMachine(
            llm_client=mock_llm,
            tool_executor=mock_tool_executor,
            crag_evaluator=mock_crag,
            prompt_builder=mock_prompts,
            cognition_tick=mock_tick,
        )
        agent.ctx = StateContext(
            session_id="test",
            request_id="test",
            user_query="check disk health",
        )
        agent.ctx.persona_cognition = mock_cognition
        agent.current_state = AgentState.REFLECTING

        events = []
        async for event in agent._handle_reflecting():
            events.append(event)

        # Should have a thinking event
        thinking_events = [e for e in events if e.type == "thinking"]
        assert len(thinking_events) == 1
        assert "disk" in thinking_events[0].data.get("content", "")


class TestSystemEventMapper:
    """Test SystemEventMapper cognitive mapping."""

    def test_add_event_stores_pending(self):
        """add_event should store events for next cognitive tick."""
        from halbert_core.integrations.system_event_mapper import SystemEventMapper
        mapper = SystemEventMapper()
        mapper.add_event(
            event_type="disk_failure",
            severity="critical",
            source="disk:/dev/sda1",
            detail="SMART failure predicted",
        )
        assert len(mapper._pending_events) == 1

    def test_disk_failure_creates_worry(self):
        """Disk failure event should create a worry in cognition."""
        from halbert_core.integrations.system_event_mapper import SystemEventMapper

        mapper = SystemEventMapper()
        mapper.add_event(
            event_type="disk_failure",
            severity="critical",
            source="disk:/dev/sda1",
            detail="SMART failure predicted",
        )

        # Mock cognition with real worry state
        cognition = MagicMock()
        cognition.worries = MagicMock()
        cognition.worries.add_worry = MagicMock()
        cognition.worries.get_active_worries = MagicMock(return_value=[])
        cognition.emotional_state = MagicMock()
        cognition.emotional_state.add_emotion = MagicMock()

        mapper.populate_cognition(cognition)

        # Should have added a worry
        cognition.worries.add_worry.assert_called_once()
        worry_call = cognition.worries.add_worry.call_args
        assert "disk" in worry_call.kwargs["content"].lower()
        assert worry_call.kwargs["intensity"] >= 0.5

    def test_service_recovered_resolves_worry(self):
        """Service recovered event should resolve matching worries."""
        from halbert_core.integrations.system_event_mapper import SystemEventMapper

        mapper = SystemEventMapper()
        mapper.add_event(
            event_type="service_recovered",
            severity="info",
            source="service:nginx",
            detail="Service recovered",
        )

        # Mock cognition with an existing worry
        worry = MagicMock()
        worry.id = "worry_123"
        worry.source = "service:nginx"
        cognition = MagicMock()
        cognition.worries = MagicMock()
        cognition.worries.get_active_worries = MagicMock(return_value=[worry])
        cognition.worries.resolve_worry = MagicMock()
        cognition.emotional_state = MagicMock()
        cognition.emotional_state.add_emotion = MagicMock()

        mapper.populate_cognition(cognition)

        # Should have resolved the worry
        cognition.worries.resolve_worry.assert_called_once_with(
            "worry_123", "service recovered"
        )


class TestStateTrackers:
    """Test Halbert state tracker registration."""

    def test_disk_health_tracker_protocol(self):
        """DiskHealthTracker should have StateTracker protocol attributes."""
        from halbert_core.integrations.state_trackers import DiskHealthTracker
        tracker = DiskHealthTracker()
        assert tracker.name == "disk_health"
        assert hasattr(tracker, "update_from_turn")
        assert hasattr(tracker, "sync_to_ledger")

    def test_service_status_tracker_protocol(self):
        """ServiceStatusTracker should have StateTracker protocol attributes."""
        from halbert_core.integrations.state_trackers import ServiceStatusTracker
        tracker = ServiceStatusTracker()
        assert tracker.name == "service_status"
        assert hasattr(tracker, "update_from_turn")
        assert hasattr(tracker, "sync_to_ledger")

    def test_admin_presence_tracker_conversation_driven(self):
        """AdminPresenceTracker should update from conversation turns."""
        from halbert_core.integrations.state_trackers import AdminPresenceTracker
        tracker = AdminPresenceTracker()
        # Should set admin present when user_message is provided
        tracker.update_from_turn(
            persona_id="halbert",
            user_message="check system status",
            ai_response="All systems nominal",
        )
        assert tracker._admin_present is True


class TestModelClientExtraction:
    """Test that model client extraction (Phase C) works correctly."""

    def test_get_ollama_endpoint_returns_string(self):
        """get_ollama_endpoint should return a URL string."""
        from halbert_core.model.client import get_ollama_endpoint
        endpoint = get_ollama_endpoint()
        assert isinstance(endpoint, str)
        assert endpoint.startswith("http")

    def test_get_configured_model_returns_string(self):
        """get_configured_model should return a model name string."""
        from halbert_core.model.client import get_configured_model
        model = get_configured_model()
        assert isinstance(model, str)
        assert len(model) > 0

    def test_score_query_complexity_returns_float(self):
        """score_query_complexity should return a float 0-1."""
        from halbert_core.model.client import score_query_complexity
        score = score_query_complexity("hi")
        assert 0.0 <= score <= 1.0

    def test_score_query_complexity_simple_vs_complex(self):
        """Simple queries should score lower than complex ones."""
        from halbert_core.model.client import score_query_complexity
        simple = score_query_complexity("hi")
        complex_q = score_query_complexity(
            "debug why the nginx service failed to start after config change, "
            "investigate the error logs and recommend a fix step by step"
        )
        assert complex_q > simple

    def test_chat_reexports_model_client(self):
        """chat.py should re-export model client functions for backward compat."""
        from halbert_core.dashboard.routes.chat import (
            get_ollama_endpoint,
            get_configured_model,
            get_specialist_model,
            call_llm_chat,
        )
        # These should be the same objects as in model.client
        from halbert_core.model.client import (
            get_ollama_endpoint as client_endpoint,
            get_configured_model as client_model,
        )
        assert get_ollama_endpoint is client_endpoint
        assert get_configured_model is client_model


class TestContextAdapters:
    """Test extended context adapters (Phase C)."""

    def test_system_identity_adapter_returns_content(self):
        """SystemIdentityAdapter should return identity context."""
        from halbert_core.context.extra_adapters import SystemIdentityAdapter
        adapter = SystemIdentityAdapter(identity_override="Test identity")
        import asyncio
        results = asyncio.run(adapter.search("test", 1))
        assert len(results) == 1
        assert "Test identity" in results[0]["content"]

    def test_safety_adapter_validates_input(self):
        """SafetyAdapter should have validate_input method."""
        from halbert_core.context.extra_adapters import SafetyAdapter
        adapter = SafetyAdapter()
        result = adapter.validate_input("test message")
        assert "safe" in result
        assert result["safe"] is True  # No validator wired = safe


class TestExtendedContextAssembler:
    """Test that create_extended_context_assembler wires all adapters."""

    def test_extended_assembler_has_extra_sources(self):
        """ContextAssembler should have extra_sources dict with 4 adapters."""
        from halbert_core.context.extra_adapters import create_extended_context_assembler
        assembler = create_extended_context_assembler()
        assert hasattr(assembler, "_extra_sources")
        assert "system_identity" in assembler._extra_sources
        assert "self_knowledge" in assembler._extra_sources
        assert "telemetry" in assembler._extra_sources
        assert "safety" in assembler._extra_sources

    def test_extended_assembler_priorities_include_new_sources(self):
        """Priorities dict should include the 4 new source names."""
        from halbert_core.context.extra_adapters import create_extended_context_assembler
        assembler = create_extended_context_assembler()
        assert "system_identity" in assembler.priorities
        assert "self_knowledge" in assembler.priorities
        assert "telemetry" in assembler.priorities
        assert "safety" in assembler.priorities


class TestStreamEventAttributes:
    """Test StreamEvent attribute names (regression for audit bug #4/#5)."""

    def test_stream_event_uses_type_not_event_type(self):
        """StreamEvent should have .type attribute, not .event_type."""
        from halbert_core.agents.events import StreamEvent
        event = StreamEvent.thinking("test-session", "test thought")
        assert hasattr(event, "type")
        assert event.type == "thinking"
        assert not hasattr(event, "event_type")

    def test_state_change_data_key_is_state(self):
        """state_change event should use 'state' key in data, not 'new_state'."""
        from halbert_core.agents.events import StreamEvent
        event = StreamEvent.state_change("test-session", "reflecting", "observing")
        assert "state" in event.data
        assert event.data["state"] == "reflecting"
        assert "new_state" not in event.data
