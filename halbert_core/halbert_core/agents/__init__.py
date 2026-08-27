# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Agents module for agentic AI patterns.

Phase 21: Implements ReAct pattern for iterative reasoning.
Phase 36: Adds state machine architecture with CRAG evaluation.
"""

from .react_agent import ReActAgent, ThinkingStep, ThinkingStepType, ReActResponse
from .states import AgentState, StateContext, CRAGAction, PlanStep, ToolCall
from .events import StreamEvent
from .state_machine import AgentStateMachine
from .llm_client import (
    BaseLLMClient, OllamaClient, AnthropicClient,
    LLMResponse, get_llm_client,
)
from .metrics import (
    AgentMetricsCollector, SessionMetrics,
    get_metrics_collector, reset_metrics,
)
from .conversation import Conversation, Message
from .error_recovery import (
    ErrorRecoveryManager, ErrorType, RecoveryStrategy,
    GracefulDegradation, get_recovery_manager,
)

__all__ = [
    # Phase 21: ReAct
    'ReActAgent', 'ThinkingStep', 'ThinkingStepType', 'ReActResponse',
    # Phase 36: State Machine
    'AgentState', 'StateContext', 'CRAGAction', 'PlanStep', 'ToolCall',
    'StreamEvent', 'AgentStateMachine',
    # LLM Clients
    'BaseLLMClient', 'OllamaClient', 'AnthropicClient',
    'LLMResponse', 'get_llm_client',
    # Metrics
    'AgentMetricsCollector', 'SessionMetrics',
    'get_metrics_collector', 'reset_metrics',
    # Conversation records (the SQLite thread store is the store of record)
    'Conversation', 'Message',
    # Error Recovery
    'ErrorRecoveryManager', 'ErrorType', 'RecoveryStrategy',
    'GracefulDegradation', 'get_recovery_manager',
]
