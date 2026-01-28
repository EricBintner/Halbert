"""
System tools for LLM function calling (Phase 12d).

Provides tools for real-time system queries that the LLM can invoke.
Phase 36: Adds safety framework and async executor.
"""

from .system_tools import (
    SYSTEM_TOOLS,
    execute_tool,
    get_tool_schemas,
)
from .safety import ToolSafetyFramework, RiskLevel, SafetyCheckResult
from .executor import ToolExecutor, ExecutionResult

__all__ = [
    # Phase 12d: System tools
    'SYSTEM_TOOLS',
    'execute_tool',
    'get_tool_schemas',
    # Phase 36: Safety and Executor
    'ToolSafetyFramework',
    'RiskLevel',
    'SafetyCheckResult',
    'ToolExecutor',
    'ExecutionResult',
]
