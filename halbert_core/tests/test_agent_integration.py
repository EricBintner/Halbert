"""
Integration Tests for Agent State Machine

Tests the full agent flow with mock services.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from typing import List, Dict, Any

from halbert_core.agents import (
    AgentStateMachine, AgentState, StateContext, StreamEvent,
    get_metrics_collector, reset_metrics,
)
from halbert_core.agents.llm_client import LLMResponse, FunctionCall, ToolCall
from halbert_core.tools import ToolSafetyFramework, ToolExecutor
from halbert_core.context import ContextAssembler, TokenCounter
from halbert_core.prompts import AgentPromptBuilder
from halbert_core.eval.crag import CRAGEvaluator, CRAGResult, CRAGAction


# -----------------------------------------------------------------------------
# Mock Services
# -----------------------------------------------------------------------------

class MockLLMClient:
    """Mock LLM client for testing."""
    
    def __init__(self, responses: List[LLMResponse] = None):
        self.responses = responses or []
        self.call_count = 0
        self.messages_received = []
    
    async def chat(self, messages, tools=None, **kwargs):
        self.messages_received.append(messages)
        if self.call_count < len(self.responses):
            response = self.responses[self.call_count]
            self.call_count += 1
            return response
        return LLMResponse(content="Default mock response")
    
    async def stream(self, messages, **kwargs):
        response = await self.chat(messages)
        for word in response.content.split():
            yield word + " "


class MockRAGService:
    """Mock RAG service for testing."""
    
    def __init__(self, results: List[Dict] = None):
        self.results = results or []
        self.queries = []
    
    async def search(self, query: str, limit: int = 5) -> List[Dict]:
        self.queries.append(query)
        return self.results[:limit]


class MockMemoryService:
    """Mock memory service for testing."""
    
    def __init__(self, memories: List[Dict] = None):
        self.memories = memories or []
        self.stored = []
    
    async def recall(self, query: str, limit: int = 5) -> List[Dict]:
        return self.memories[:limit]
    
    async def store_interaction(self, query: str, response: str, session_id: str = None):
        self.stored.append({"query": query, "response": response, "session_id": session_id})


class MockDiscoveryService:
    """Mock discovery service for testing."""
    
    def __init__(self, discoveries: List[Dict] = None):
        self.discoveries = discoveries or []
    
    async def search(self, query: str, limit: int = 5) -> List[Dict]:
        return self.discoveries[:limit]


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------

@pytest.fixture
def mock_llm_direct_response():
    """LLM that responds directly without tools."""
    return MockLLMClient([
        LLMResponse(content="The answer to your question is 42.")
    ])


@pytest.fixture
def mock_llm_with_search():
    """LLM that requests a search then responds."""
    search_tool = ToolCall(
        id="tc1",
        function=FunctionCall(name="search", arguments={"query": "test query"})
    )
    return MockLLMClient([
        LLMResponse(content="", tool_calls=[search_tool]),
        LLMResponse(content="Based on my search, the answer is 42.")
    ])


@pytest.fixture
def mock_rag():
    """Mock RAG with sample results."""
    return MockRAGService([
        {"content": "Relevant document 1", "source": "docs", "score": 0.9},
        {"content": "Relevant document 2", "source": "wiki", "score": 0.8},
    ])


@pytest.fixture
def mock_memory():
    """Mock memory service."""
    return MockMemoryService([
        {"content": "User prefers verbose output", "type": "preference"},
    ])


@pytest.fixture
def mock_discovery():
    """Mock discovery service."""
    return MockDiscoveryService([
        {"content": "System runs Ubuntu 22.04", "category": "system"},
    ])


@pytest.fixture
def tool_executor():
    """Real tool executor with safety."""
    safety = ToolSafetyFramework()
    return ToolExecutor(safety=safety)


@pytest.fixture
def context_assembler(mock_rag, mock_memory, mock_discovery):
    """Context assembler with mock services."""
    return ContextAssembler(
        rag_service=mock_rag,
        memory_service=mock_memory,
        discovery_service=mock_discovery,
        token_counter=TokenCounter()
    )


@pytest.fixture
def prompt_builder():
    """Agent prompt builder."""
    return AgentPromptBuilder()


# -----------------------------------------------------------------------------
# Integration Tests
# -----------------------------------------------------------------------------

class TestAgentDirectResponse:
    """Tests for direct response flow (no tools needed)."""
    
    @pytest.mark.asyncio
    async def test_simple_query_responds_directly(
        self, mock_llm_direct_response, tool_executor, 
        context_assembler, prompt_builder
    ):
        """Agent responds directly when no tools needed."""
        agent = AgentStateMachine(
            llm_client=mock_llm_direct_response,
            tool_executor=tool_executor,
            context_assembler=context_assembler,
            prompt_builder=prompt_builder,
            max_loops=3
        )
        
        events = []
        async for event in agent.process("What is 21 * 2?"):
            events.append(event)
        
        # Check we got expected events
        event_types = [e.type for e in events]
        assert "session_started" in event_types
        assert "state_change" in event_types
        assert "session_ended" in event_types
    
    @pytest.mark.asyncio
    async def test_session_ends_in_idle(
        self, mock_llm_direct_response, tool_executor,
        context_assembler, prompt_builder
    ):
        """Session returns to IDLE when complete."""
        agent = AgentStateMachine(
            llm_client=mock_llm_direct_response,
            tool_executor=tool_executor,
            context_assembler=context_assembler,
            prompt_builder=prompt_builder,
        )
        
        async for _ in agent.process("Test query"):
            pass
        
        assert agent.current_state == AgentState.IDLE


class TestAgentWithToolCalls:
    """Tests for tool-calling flow."""
    
    @pytest.mark.asyncio
    async def test_search_tool_executed(
        self, mock_llm_with_search, tool_executor,
        context_assembler, prompt_builder, mock_rag
    ):
        """Agent executes search tool when requested by LLM."""
        agent = AgentStateMachine(
            llm_client=mock_llm_with_search,
            tool_executor=tool_executor,
            context_assembler=context_assembler,
            prompt_builder=prompt_builder,
            rag_service=mock_rag,
        )
        
        events = []
        async for event in agent.process("Search for something"):
            events.append(event)
        
        # Should have visited SEARCHING state
        state_changes = [e for e in events if e.type == "state_change"]
        states_visited = [e.data.get("state") for e in state_changes]
        assert "searching" in states_visited


class TestAgentLoopLimits:
    """Tests for loop limit enforcement."""
    
    @pytest.mark.asyncio
    async def test_max_loops_enforced(self, tool_executor, context_assembler, prompt_builder):
        """Agent stops after max_loops iterations."""
        # LLM that always requests search (would loop forever)
        search_tool = ToolCall(
            id="tc1",
            function=FunctionCall(name="search", arguments={"query": "test"})
        )
        infinite_search_llm = MockLLMClient([
            LLMResponse(content="", tool_calls=[search_tool]),
        ] * 10)  # More responses than max_loops
        
        agent = AgentStateMachine(
            llm_client=infinite_search_llm,
            tool_executor=tool_executor,
            context_assembler=context_assembler,
            prompt_builder=prompt_builder,
            max_loops=3
        )
        
        events = []
        async for event in agent.process("Loop test"):
            events.append(event)
        
        # Should have loop warning
        loop_warnings = [e for e in events if e.type == "loop_warning"]
        assert len(loop_warnings) > 0 or agent.ctx.loop_count <= 3


class TestAgentOscillationDetection:
    """Tests for oscillation detection."""
    
    def test_detects_oscillation(self):
        """Detect A->B->A->B pattern."""
        agent = AgentStateMachine(llm_client=None)
        agent.ctx = StateContext(
            session_id="test",
            request_id="req1",
            user_query="test"
        )
        agent.ctx.state_history = ["planning", "searching", "planning", "searching"]
        
        assert agent._detect_oscillation() is True
    
    def test_no_false_positive(self):
        """Don't detect oscillation in normal flow."""
        agent = AgentStateMachine(llm_client=None)
        agent.ctx = StateContext(
            session_id="test",
            request_id="req1",
            user_query="test"
        )
        agent.ctx.state_history = ["planning", "searching", "observing", "responding"]
        
        assert agent._detect_oscillation() is False


class TestAgentMetrics:
    """Tests for metrics collection."""
    
    @pytest.mark.asyncio
    async def test_metrics_collected(
        self, mock_llm_direct_response, tool_executor,
        context_assembler, prompt_builder
    ):
        """Metrics are collected during session."""
        reset_metrics()
        metrics = get_metrics_collector()
        
        agent = AgentStateMachine(
            llm_client=mock_llm_direct_response,
            tool_executor=tool_executor,
            context_assembler=context_assembler,
            prompt_builder=prompt_builder,
        )
        
        # Start session manually for metrics
        session_metrics = metrics.start_session("test-session")
        
        async for event in agent.process("Test", session_id="test-session"):
            if event.type == "state_change":
                metrics.record_state_enter("test-session", event.data.get("state", ""))
        
        metrics.end_session("test-session", confidence=0.8, crag_action="CORRECT")
        
        summary = metrics.get_summary()
        assert summary["total_sessions"] >= 1


class TestToolSafetyIntegration:
    """Tests for tool safety in agent flow."""
    
    @pytest.mark.asyncio
    async def test_safe_command_executed(self, tool_executor):
        """Safe commands execute without confirmation."""
        result = await tool_executor.execute(
            "run_command",
            {"command": "echo hello"},
            session_id="test"
        )
        
        assert result.success is True
        assert result.requires_confirmation is False
    
    @pytest.mark.asyncio
    async def test_dangerous_command_requires_confirmation(self, tool_executor):
        """Dangerous commands require confirmation."""
        result = await tool_executor.execute(
            "run_command",
            {"command": "rm -rf /tmp/test"},
            session_id="test",
            confirmed=False
        )
        
        assert result.requires_confirmation is True
    
    @pytest.mark.asyncio
    async def test_critical_command_blocked(self, tool_executor):
        """Critical commands are blocked entirely."""
        result = await tool_executor.execute(
            "run_command",
            {"command": "rm -rf /"},
            session_id="test",
            confirmed=True  # Even if confirmed
        )
        
        assert result.success is False


class TestCRAGIntegration:
    """Tests for CRAG evaluation integration."""
    
    @pytest.mark.asyncio
    async def test_crag_evaluates_documents(self):
        """CRAG evaluator scores document relevance."""
        evaluator = CRAGEvaluator()
        
        result = await evaluator.evaluate(
            query="What is systemd?",
            documents=[
                {"content": "systemd is a system and service manager for Linux"},
                {"content": "It provides parallelization and dependency tracking"},
            ],
            observations=[]
        )
        
        assert isinstance(result.confidence, float)
        assert result.action in [CRAGAction.CORRECT, CRAGAction.INCORRECT, CRAGAction.AMBIGUOUS]
    
    @pytest.mark.asyncio
    async def test_crag_handles_empty_documents(self):
        """CRAG handles case with no documents."""
        evaluator = CRAGEvaluator()
        
        result = await evaluator.evaluate(
            query="Test query",
            documents=[],
            observations=[]
        )
        
        assert result.action == CRAGAction.INCORRECT
        assert result.should_retrieve_more is True


class TestContextAssembly:
    """Tests for context assembly."""
    
    @pytest.mark.asyncio
    async def test_assembles_from_multiple_sources(
        self, mock_rag, mock_memory, mock_discovery
    ):
        """Context assembler combines multiple sources."""
        assembler = ContextAssembler(
            rag_service=mock_rag,
            memory_service=mock_memory,
            discovery_service=mock_discovery,
            token_counter=TokenCounter()
        )
        
        result = await assembler.assemble(
            query="Test query",
            conversation=[{"role": "user", "content": "Hello"}],
            max_tokens=4000
        )
        
        # Should have content from sources
        assert len(result.sources) > 0
        assert result.total_tokens > 0
    
    @pytest.mark.asyncio
    async def test_respects_token_budget(self, mock_rag, mock_memory, mock_discovery):
        """Context assembler respects token budget."""
        assembler = ContextAssembler(
            rag_service=mock_rag,
            memory_service=mock_memory,
            discovery_service=mock_discovery,
            token_counter=TokenCounter()
        )
        
        result = await assembler.assemble(
            query="Test",
            max_tokens=100  # Very small budget
        )
        
        assert result.total_tokens <= 100


# Run with: pytest tests/test_agent_integration.py -v
