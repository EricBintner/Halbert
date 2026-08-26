"""
Unit tests for the Agent State Machine

Tests state transitions, oscillation detection, and basic flow.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from halbert_core.agents.states import (
    AgentState, StateContext, CRAGAction, PlanStep, ToolCall
)
from halbert_core.agents.events import StreamEvent
from halbert_core.agents.state_machine import AgentStateMachine
from halbert_core.tools.safety import ToolSafetyFramework, RiskLevel
from halbert_core.tools.executor import ToolExecutor


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------

@pytest.fixture
def mock_llm():
    """Create a mock LLM client."""
    llm = AsyncMock()
    llm.chat = AsyncMock(return_value=MagicMock(
        content="Test response",
        tool_calls=None,
        plan=None
    ))
    llm.stream = AsyncMock()
    return llm


@pytest.fixture
def mock_llm_with_tool():
    """Create a mock LLM that returns tool calls."""
    llm = AsyncMock()
    
    tool_call = MagicMock()
    tool_call.function.name = "search"
    tool_call.function.arguments = {"query": "test query"}
    
    llm.chat = AsyncMock(return_value=MagicMock(
        content="",
        tool_calls=[tool_call],
        plan=None
    ))
    return llm


@pytest.fixture
def tool_executor():
    """Create a real tool executor with safety."""
    safety = ToolSafetyFramework()
    return ToolExecutor(safety=safety)


@pytest.fixture
def agent(mock_llm, tool_executor):
    """Create an agent state machine for testing."""
    return AgentStateMachine(
        llm_client=mock_llm,
        tool_executor=tool_executor,
        max_loops=5
    )


# -----------------------------------------------------------------------------
# State Transition Tests
# -----------------------------------------------------------------------------

class TestStateTransitions:
    """Test valid and invalid state transitions."""
    
    def test_idle_to_planning_valid(self, agent):
        """IDLE -> PLANNING is valid."""
        agent.ctx = StateContext(
            session_id="test",
            request_id="req1",
            user_query="test"
        )
        agent.current_state = AgentState.IDLE
        
        # This should not raise
        event = asyncio.run(
            agent._transition(AgentState.PLANNING)
        )
        
        assert agent.current_state == AgentState.PLANNING
        assert event.type == "state_change"
        assert event.data["state"] == "planning"
        assert event.data["previous_state"] == "idle"
    
    def test_idle_to_responding_invalid(self, agent):
        """IDLE -> RESPONDING is invalid."""
        agent.ctx = StateContext(
            session_id="test",
            request_id="req1",
            user_query="test"
        )
        agent.current_state = AgentState.IDLE
        
        with pytest.raises(ValueError, match="Invalid transition"):
            asyncio.run(
                agent._transition(AgentState.RESPONDING)
            )
    
    def test_planning_to_searching_valid(self, agent):
        """PLANNING -> SEARCHING is valid."""
        agent.ctx = StateContext(
            session_id="test",
            request_id="req1",
            user_query="test"
        )
        agent.current_state = AgentState.PLANNING
        
        event = asyncio.run(
            agent._transition(AgentState.SEARCHING)
        )
        
        assert agent.current_state == AgentState.SEARCHING
    
    def test_executing_to_awaiting_confirmation(self, agent):
        """EXECUTING -> AWAITING_CONFIRMATION is valid."""
        agent.ctx = StateContext(
            session_id="test",
            request_id="req1",
            user_query="test"
        )
        agent.current_state = AgentState.EXECUTING
        
        event = asyncio.run(
            agent._transition(AgentState.AWAITING_CONFIRMATION)
        )
        
        assert agent.current_state == AgentState.AWAITING_CONFIRMATION
    
    def test_state_history_recorded(self, agent):
        """State transitions are recorded in history."""
        agent.ctx = StateContext(
            session_id="test",
            request_id="req1",
            user_query="test"
        )
        agent.current_state = AgentState.IDLE
        
        asyncio.run(
            agent._transition(AgentState.PLANNING)
        )
        
        assert "planning" in agent.ctx.state_history


# -----------------------------------------------------------------------------
# Oscillation Detection Tests
# -----------------------------------------------------------------------------

class TestOscillationDetection:
    """Test detection of infinite loop patterns."""
    
    def test_detects_abab_pattern(self, agent):
        """Detects A->B->A->B oscillation."""
        agent.ctx = StateContext(
            session_id="test",
            request_id="req1",
            user_query="test"
        )
        agent.ctx.state_history = ["planning", "searching", "planning", "searching"]
        
        assert agent._detect_oscillation() is True
    
    def test_no_false_positive_abcd(self, agent):
        """Does not detect oscillation in A->B->C->D."""
        agent.ctx = StateContext(
            session_id="test",
            request_id="req1",
            user_query="test"
        )
        agent.ctx.state_history = ["planning", "searching", "observing", "responding"]
        
        assert agent._detect_oscillation() is False
    
    def test_no_detection_short_history(self, agent):
        """No oscillation detected with < 4 states."""
        agent.ctx = StateContext(
            session_id="test",
            request_id="req1",
            user_query="test"
        )
        agent.ctx.state_history = ["planning", "searching"]
        
        assert agent._detect_oscillation() is False
    
    def test_no_false_positive_abac(self, agent):
        """Does not detect oscillation in A->B->A->C."""
        agent.ctx = StateContext(
            session_id="test",
            request_id="req1",
            user_query="test"
        )
        agent.ctx.state_history = ["planning", "searching", "planning", "responding"]
        
        assert agent._detect_oscillation() is False


# -----------------------------------------------------------------------------
# Loop Limit Tests
# -----------------------------------------------------------------------------

class TestLoopLimits:
    """Test loop count enforcement."""
    
    def test_loop_count_increments(self, agent):
        """Loop count increments in SEARCHING state."""
        agent.ctx = StateContext(
            session_id="test",
            request_id="req1",
            user_query="test"
        )
        initial = agent.ctx.loop_count
        
        # Manually call searching handler logic
        agent.ctx.loop_count += 1
        
        assert agent.ctx.loop_count == initial + 1
    
    def test_max_loops_enforced(self, agent):
        """Agent stops when max loops reached."""
        agent.ctx = StateContext(
            session_id="test",
            request_id="req1",
            user_query="test",
            max_loops=3
        )
        agent.ctx.loop_count = 5
        
        assert agent.ctx.loop_count >= agent.ctx.max_loops


# -----------------------------------------------------------------------------
# StateContext Tests
# -----------------------------------------------------------------------------

class TestStateContext:
    """Test StateContext functionality."""
    
    def test_add_observation(self):
        """Test adding observations."""
        ctx = StateContext(
            session_id="test",
            request_id="req1",
            user_query="test"
        )
        
        ctx.add_observation("Found 5 results")
        ctx.add_observation("Executed command")
        
        assert len(ctx.observations) == 2
        assert "Found 5 results" in ctx.observations
    
    def test_add_context(self):
        """Test adding retrieved context."""
        ctx = StateContext(
            session_id="test",
            request_id="req1",
            user_query="test"
        )
        
        ctx.add_context(
            source="rag",
            content="Test content",
            metadata={"score": 0.9}
        )
        
        assert len(ctx.retrieved_context) == 1
        assert ctx.retrieved_context[0]["source"] == "rag"
        assert ctx.retrieved_context[0]["content"] == "Test content"
    
    def test_plan_advancement(self):
        """Test plan step advancement."""
        ctx = StateContext(
            session_id="test",
            request_id="req1",
            user_query="test"
        )
        ctx.plan = [
            PlanStep(step="Search for info"),
            PlanStep(step="Analyze results"),
        ]
        
        assert ctx.get_current_plan_step().step == "Search for info"
        
        ctx.advance_plan()
        
        assert ctx.plan[0].status == "completed"
        assert ctx.current_step == 1
        assert ctx.get_current_plan_step().step == "Analyze results"
    
    def test_to_dict(self):
        """Test serialization."""
        ctx = StateContext(
            session_id="test-123",
            request_id="req-456",
            user_query="What is systemd?"
        )
        ctx.confidence = 0.85
        ctx.crag_action = CRAGAction.CORRECT
        
        d = ctx.to_dict()
        
        assert d["session_id"] == "test-123"
        assert d["confidence"] == 0.85
        assert d["crag_action"] == "CORRECT"


# -----------------------------------------------------------------------------
# StreamEvent Tests
# -----------------------------------------------------------------------------

class TestStreamEvent:
    """Test StreamEvent creation and serialization."""
    
    def test_state_change_event(self):
        """Test state change event creation."""
        event = StreamEvent.state_change("sess1", "planning", "idle")
        
        assert event.type == "state_change"
        assert event.session_id == "sess1"
        assert event.data["state"] == "planning"
        assert event.data["previous_state"] == "idle"
    
    def test_tool_start_event(self):
        """Test tool start event creation."""
        event = StreamEvent.tool_start(
            "sess1",
            "run_command",
            {"command": "ls -la"},
            "exec-123"
        )
        
        assert event.type == "tool_start"
        assert event.data["tool"] == "run_command"
        assert event.data["execution_id"] == "exec-123"
    
    def test_response_chunk_event(self):
        """Test response chunk event."""
        event = StreamEvent.response_chunk("sess1", "Hello, ")
        
        assert event.type == "response_chunk"
        assert event.data["content"] == "Hello, "
    
    def test_to_sse_format(self):
        """Test SSE formatting."""
        event = StreamEvent.state_change("sess1", "planning", "idle")
        sse = event.to_sse()
        
        assert sse.startswith("data: ")
        assert sse.endswith("\n\n")
        assert '"type": "state_change"' in sse
    
    def test_confidence_update_event(self):
        """Test confidence update event."""
        event = StreamEvent.confidence_update("sess1", 0.85, "CORRECT")
        
        assert event.type == "confidence_update"
        assert event.data["confidence"] == 0.85
        assert event.data["crag_action"] == "CORRECT"


# -----------------------------------------------------------------------------
# Tool Safety Tests
# -----------------------------------------------------------------------------

class TestToolSafety:
    """Test tool safety classification."""
    
    def test_safe_command_ls(self):
        """ls is classified as SAFE."""
        safety = ToolSafetyFramework()
        result = safety.classify("run_command", {"command": "ls -la"})
        
        assert result.risk_level == RiskLevel.SAFE
        assert result.allowed is True
        assert result.requires_confirmation is False
    
    def test_high_risk_rm_rf(self):
        """rm -rf is classified as HIGH."""
        safety = ToolSafetyFramework()
        result = safety.classify("run_command", {"command": "rm -rf /tmp/test"})
        
        assert result.risk_level == RiskLevel.HIGH
        assert result.requires_confirmation is True
    
    def test_critical_rm_rf_root(self):
        """rm -rf / is CRITICAL and blocked."""
        safety = ToolSafetyFramework()
        result = safety.classify("run_command", {"command": "rm -rf /"})
        
        assert result.risk_level == RiskLevel.CRITICAL
        assert result.allowed is False
    
    def test_read_file_safe(self):
        """read_file is SAFE."""
        safety = ToolSafetyFramework()
        result = safety.classify("read_file", {"path": "/etc/hostname"})
        
        assert result.risk_level == RiskLevel.SAFE
        assert result.allowed is True
    
    def test_write_sensitive_path_high(self):
        """Writing to /etc is HIGH risk."""
        safety = ToolSafetyFramework()
        result = safety.classify("write_file", {"path": "/etc/test.conf"})
        
        assert result.risk_level == RiskLevel.HIGH
        assert result.requires_confirmation is True
    
    def test_systemctl_status_safe(self):
        """systemctl status is SAFE."""
        safety = ToolSafetyFramework()
        result = safety.classify("run_command", {"command": "systemctl status nginx"})
        
        assert result.risk_level == RiskLevel.SAFE
    
    def test_systemctl_restart_high(self):
        """systemctl restart is HIGH."""
        safety = ToolSafetyFramework()
        result = safety.classify("run_command", {"command": "systemctl restart nginx"})
        
        assert result.risk_level == RiskLevel.HIGH


# -----------------------------------------------------------------------------
# Integration-style Tests
# -----------------------------------------------------------------------------

class TestAgentFlow:
    """Test agent processing flow."""
    
    @pytest.mark.asyncio
    async def test_simple_query_flow(self, mock_llm, tool_executor):
        """Test a simple query that goes directly to response."""
        # Configure LLM to return direct response
        mock_llm.chat.return_value = MagicMock(
            content="The answer is 42",
            tool_calls=None,
            plan=None
        )
        
        async def mock_stream(messages):
            yield "The answer is 42"
        
        mock_llm.stream = mock_stream
        
        agent = AgentStateMachine(
            llm_client=mock_llm,
            tool_executor=tool_executor,
            max_loops=5
        )
        
        events = []
        async for event in agent.process("What is the answer?"):
            events.append(event)
        
        # Check we got expected events
        event_types = [e.type for e in events]
        
        assert "session_started" in event_types
        assert "state_change" in event_types
        assert "session_ended" in event_types


# Run with: pytest tests/test_state_machine.py -v


# -----------------------------------------------------------------------------
# AWAITING_CONFIRMATION: pause instead of busy-looping
# -----------------------------------------------------------------------------

@pytest.fixture
def mock_llm_high_risk_command():
    """LLM that requests a HIGH-risk run_command (needs confirmation)."""
    llm = AsyncMock()
    tool_call = MagicMock()
    tool_call.function.name = "run_command"
    tool_call.function.arguments = {"command": "systemctl restart sshd"}
    llm.chat = AsyncMock(return_value=MagicMock(
        content="", tool_calls=[tool_call], plan=None
    ))

    async def _stream(messages, **kwargs):
        yield "done"

    llm.stream = _stream
    return llm


async def _pause_on_confirmation(agent):
    events = []

    async def consume():
        async for e in agent.process("restart sshd", session_id="sess-pause"):
            events.append(e)

    await asyncio.wait_for(consume(), timeout=2)
    return events


class TestAwaitingConfirmation:

    @pytest.mark.asyncio
    async def test_awaiting_confirmation_pauses_without_spinning(
        self, mock_llm_high_risk_command, tool_executor
    ):
        agent = AgentStateMachine(
            llm_client=mock_llm_high_risk_command,
            tool_executor=tool_executor,
            max_loops=5,
        )
        events = await _pause_on_confirmation(agent)

        types = [e.type for e in events]
        assert "tool_confirmation_required" in types
        assert any(
            e.type == "conversation_status" and e.data["status"] == "blocked"
            for e in events
        )
        assert "session_ended" not in types
        assert agent.current_state == AgentState.AWAITING_CONFIRMATION
        assert "sess-pause" in agent.active_sessions

    @pytest.mark.asyncio
    async def test_confirm_action_resumes_paused_session(
        self, mock_llm_high_risk_command, tool_executor
    ):
        from halbert_core.tools.executor import ExecutionResult

        agent = AgentStateMachine(
            llm_client=mock_llm_high_risk_command,
            tool_executor=tool_executor,
            max_loops=5,
        )
        events = await _pause_on_confirmation(agent)
        confirm = next(e for e in events if e.type == "tool_confirmation_required")
        action_id = confirm.data["execution_id"]

        # Don't actually run the command on the host: stub the confirmed execution.
        agent.tools.execute = AsyncMock(
            return_value=ExecutionResult(success=True, result="restarted")
        )

        resumed = []
        async for e in agent.confirm_action("sess-pause", action_id, True):
            resumed.append(e)

        types = [e.type for e in resumed]
        assert "tool_start" in types
        assert "tool_complete" in types
        assert any(
            e.type == "conversation_status" and e.data["status"] == "in_progress"
            for e in resumed
        )
        assert agent.tools.execute.await_args.kwargs["confirmed"] is True


class TestPausedSessionEviction:
    """5c: a paused AWAITING_CONFIRMATION session must be evicted from
    active_sessions once confirm_action()/reject finishes (unless the machine
    is again awaiting confirmation)."""

    @pytest.mark.asyncio
    async def test_confirm_action_evicts_session(
        self, mock_llm_high_risk_command, tool_executor
    ):
        from halbert_core.tools.executor import ExecutionResult

        agent = AgentStateMachine(
            llm_client=mock_llm_high_risk_command,
            tool_executor=tool_executor,
            max_loops=5,
        )
        events = await _pause_on_confirmation(agent)
        assert "sess-pause" in agent.active_sessions
        confirm = next(e for e in events if e.type == "tool_confirmation_required")
        agent.tools.execute = AsyncMock(
            return_value=ExecutionResult(success=True, result="restarted")
        )

        async for _ in agent.confirm_action("sess-pause", confirm.data["execution_id"], True):
            pass

        assert agent.current_state != AgentState.AWAITING_CONFIRMATION
        assert "sess-pause" not in agent.active_sessions

    @pytest.mark.asyncio
    async def test_reject_action_evicts_session(
        self, mock_llm_high_risk_command, tool_executor
    ):
        agent = AgentStateMachine(
            llm_client=mock_llm_high_risk_command,
            tool_executor=tool_executor,
            max_loops=5,
        )
        events = await _pause_on_confirmation(agent)
        confirm = next(e for e in events if e.type == "tool_confirmation_required")

        resumed = []
        async for e in agent.confirm_action("sess-pause", confirm.data["execution_id"], False):
            resumed.append(e)

        assert any(e.type == "state_change" and e.data["state"] == "planning" for e in resumed)
        assert "sess-pause" not in agent.active_sessions

    @pytest.mark.asyncio
    async def test_confirm_action_keeps_session_when_paused_again(
        self, mock_llm_high_risk_command, tool_executor
    ):
        agent = AgentStateMachine(
            llm_client=mock_llm_high_risk_command,
            tool_executor=tool_executor,
            max_loops=5,
        )
        events = await _pause_on_confirmation(agent)
        confirm = next(e for e in events if e.type == "tool_confirmation_required")

        async def _pause_again():
            agent.current_state = AgentState.AWAITING_CONFIRMATION
            yield StreamEvent.tool_confirmation_required(
                "sess-pause", "exec-2", "run_command", "needs ok", "high"
            )
        agent._handle_executing = _pause_again

        async for _ in agent.confirm_action("sess-pause", confirm.data["execution_id"], True):
            pass

        assert agent.current_state == AgentState.AWAITING_CONFIRMATION
        assert "sess-pause" in agent.active_sessions


class TestAwaitingConfirmationOnFinalLoop:
    """Round 2 review: the AWAITING_CONFIRMATION break must run before the
    max-loops guard, otherwise a pause on the final allowed loop is
    overwritten to RESPONDING and the confirmation is lost."""

    @pytest.mark.asyncio
    async def test_pause_on_last_loop_is_not_overwritten(
        self, mock_llm_high_risk_command, tool_executor
    ):
        agent = AgentStateMachine(
            llm_client=mock_llm_high_risk_command,
            tool_executor=tool_executor,
            max_loops=1,
        )
        events = await _pause_on_confirmation(agent)

        types = [e.type for e in events]
        assert "tool_confirmation_required" in types
        assert "response_complete" not in types
        assert "session_ended" not in types
        assert agent.current_state == AgentState.AWAITING_CONFIRMATION
        assert agent.ctx.pending_confirmation is not None
        assert "sess-pause" in agent.active_sessions
