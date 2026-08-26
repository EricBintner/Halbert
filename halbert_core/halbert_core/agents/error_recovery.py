# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Error Recovery Strategies

Provides intelligent error recovery for the agent state machine.
"""

from __future__ import annotations
import asyncio
import logging
from dataclasses import dataclass
from typing import Optional, Callable, Any, Dict
from enum import Enum

logger = logging.getLogger('halbert.agents.error_recovery')


class ErrorType(Enum):
    """Types of errors that can occur."""
    LLM_TIMEOUT = "llm_timeout"
    LLM_RATE_LIMIT = "llm_rate_limit"
    LLM_API_ERROR = "llm_api_error"
    TOOL_TIMEOUT = "tool_timeout"
    TOOL_EXECUTION = "tool_execution"
    CONTEXT_OVERFLOW = "context_overflow"
    INVALID_RESPONSE = "invalid_response"
    NETWORK_ERROR = "network_error"
    UNKNOWN = "unknown"


@dataclass
class RecoveryStrategy:
    """Strategy for recovering from an error."""
    retry: bool = False
    retry_count: int = 0
    max_retries: int = 3
    backoff_seconds: float = 1.0
    fallback_action: Optional[str] = None
    should_notify_user: bool = False
    message: str = ""


class ErrorRecoveryManager:
    """
    Manages error recovery strategies for the agent.
    
    Provides:
    - Automatic retry with exponential backoff
    - Fallback strategies for different error types
    - Circuit breaker for repeated failures
    - User notification for unrecoverable errors
    """
    
    # Default strategies per error type
    DEFAULT_STRATEGIES: Dict[ErrorType, RecoveryStrategy] = {
        ErrorType.LLM_TIMEOUT: RecoveryStrategy(
            retry=True, max_retries=2, backoff_seconds=2.0,
            fallback_action="use_cached_response",
            message="LLM request timed out, retrying..."
        ),
        ErrorType.LLM_RATE_LIMIT: RecoveryStrategy(
            retry=True, max_retries=3, backoff_seconds=5.0,
            message="Rate limited, waiting before retry..."
        ),
        ErrorType.LLM_API_ERROR: RecoveryStrategy(
            retry=True, max_retries=2, backoff_seconds=1.0,
            fallback_action="respond_with_error",
            should_notify_user=True,
            message="LLM API error"
        ),
        ErrorType.TOOL_TIMEOUT: RecoveryStrategy(
            retry=True, max_retries=1, backoff_seconds=0.5,
            fallback_action="skip_tool",
            message="Tool execution timed out"
        ),
        ErrorType.TOOL_EXECUTION: RecoveryStrategy(
            retry=False,
            fallback_action="report_tool_error",
            message="Tool execution failed"
        ),
        ErrorType.CONTEXT_OVERFLOW: RecoveryStrategy(
            retry=False,
            fallback_action="truncate_context",
            message="Context too large, truncating..."
        ),
        ErrorType.INVALID_RESPONSE: RecoveryStrategy(
            retry=True, max_retries=2, backoff_seconds=0.5,
            message="Invalid LLM response, retrying..."
        ),
        ErrorType.NETWORK_ERROR: RecoveryStrategy(
            retry=True, max_retries=3, backoff_seconds=2.0,
            should_notify_user=True,
            message="Network error"
        ),
        ErrorType.UNKNOWN: RecoveryStrategy(
            retry=False,
            fallback_action="respond_with_error",
            should_notify_user=True,
            message="An unexpected error occurred"
        ),
    }
    
    def __init__(self):
        self._failure_counts: Dict[str, int] = {}
        self._circuit_breakers: Dict[str, float] = {}
        self.circuit_breaker_threshold = 5
        self.circuit_breaker_reset_seconds = 60.0
    
    def classify_error(self, error: Exception) -> ErrorType:
        """Classify an exception into an error type."""
        error_str = str(error).lower()
        error_type = type(error).__name__.lower()
        
        if "timeout" in error_str or "timeout" in error_type:
            if "llm" in error_str or "ollama" in error_str or "anthropic" in error_str:
                return ErrorType.LLM_TIMEOUT
            return ErrorType.TOOL_TIMEOUT
        
        if "rate" in error_str and "limit" in error_str:
            return ErrorType.LLM_RATE_LIMIT
        
        if any(x in error_str for x in ["api", "401", "403", "500", "502", "503"]):
            return ErrorType.LLM_API_ERROR
        
        if any(x in error_str for x in ["connection", "network", "dns", "socket"]):
            return ErrorType.NETWORK_ERROR
        
        if "context" in error_str and ("length" in error_str or "token" in error_str):
            return ErrorType.CONTEXT_OVERFLOW
        
        if any(x in error_str for x in ["json", "parse", "decode", "invalid"]):
            return ErrorType.INVALID_RESPONSE
        
        return ErrorType.UNKNOWN
    
    def get_strategy(self, error_type: ErrorType) -> RecoveryStrategy:
        """Get recovery strategy for an error type."""
        return self.DEFAULT_STRATEGIES.get(error_type, self.DEFAULT_STRATEGIES[ErrorType.UNKNOWN])
    
    def should_retry(self, error_type: ErrorType, attempt: int) -> bool:
        """Check if we should retry for this error type."""
        strategy = self.get_strategy(error_type)
        return strategy.retry and attempt < strategy.max_retries
    
    def get_backoff_time(self, error_type: ErrorType, attempt: int) -> float:
        """Get backoff time for retry (exponential)."""
        strategy = self.get_strategy(error_type)
        return strategy.backoff_seconds * (2 ** attempt)
    
    async def execute_with_retry(
        self,
        func: Callable,
        *args,
        error_type: ErrorType = None,
        on_retry: Callable = None,
        **kwargs
    ) -> Any:
        """
        Execute a function with automatic retry.
        
        Args:
            func: Async function to execute
            error_type: Expected error type (for strategy selection)
            on_retry: Optional callback on retry
            *args, **kwargs: Arguments for func
            
        Returns:
            Function result
            
        Raises:
            Last exception if all retries fail
        """
        strategy = self.get_strategy(error_type or ErrorType.UNKNOWN)
        last_error = None
        
        for attempt in range(strategy.max_retries + 1):
            try:
                if asyncio.iscoroutinefunction(func):
                    return await func(*args, **kwargs)
                else:
                    return func(*args, **kwargs)
                    
            except Exception as e:
                last_error = e
                actual_type = self.classify_error(e)
                actual_strategy = self.get_strategy(actual_type)
                
                if not self.should_retry(actual_type, attempt):
                    break
                
                backoff = self.get_backoff_time(actual_type, attempt)
                logger.warning(
                    f"Error ({actual_type.value}), attempt {attempt + 1}/{actual_strategy.max_retries + 1}, "
                    f"retrying in {backoff:.1f}s: {e}"
                )
                
                if on_retry:
                    on_retry(attempt, actual_type, backoff)
                
                await asyncio.sleep(backoff)
        
        raise last_error
    
    def record_failure(self, component: str):
        """Record a failure for circuit breaker."""
        self._failure_counts[component] = self._failure_counts.get(component, 0) + 1
        
        if self._failure_counts[component] >= self.circuit_breaker_threshold:
            import time
            self._circuit_breakers[component] = time.time()
            logger.warning(f"Circuit breaker opened for {component}")
    
    def record_success(self, component: str):
        """Record a success, reset failure count."""
        self._failure_counts[component] = 0
        if component in self._circuit_breakers:
            del self._circuit_breakers[component]
    
    def is_circuit_open(self, component: str) -> bool:
        """Check if circuit breaker is open for component."""
        if component not in self._circuit_breakers:
            return False
        
        import time
        open_time = self._circuit_breakers[component]
        if time.time() - open_time > self.circuit_breaker_reset_seconds:
            # Reset circuit breaker
            del self._circuit_breakers[component]
            self._failure_counts[component] = 0
            logger.info(f"Circuit breaker reset for {component}")
            return False
        
        return True


class GracefulDegradation:
    """
    Provides fallback responses when services fail.
    """
    
    @staticmethod
    def get_fallback_response(error_type: ErrorType, context: Dict = None) -> str:
        """Get a graceful fallback response for an error."""
        context = context or {}
        query = context.get("query", "your question")
        
        fallbacks = {
            ErrorType.LLM_TIMEOUT: (
                "I'm experiencing some delays in processing. Let me try to help with what I know:\n\n"
                f"Regarding '{query[:50]}...', I'd suggest checking the system documentation or "
                "trying a more specific question."
            ),
            ErrorType.LLM_RATE_LIMIT: (
                "I'm currently handling many requests. Please wait a moment and try again."
            ),
            ErrorType.TOOL_TIMEOUT: (
                "The operation took longer than expected. The system might be under load. "
                "You can try running the command manually or wait and retry."
            ),
            ErrorType.NETWORK_ERROR: (
                "I'm having trouble connecting to external services. Please check your network "
                "connection and try again."
            ),
            ErrorType.CONTEXT_OVERFLOW: (
                "The conversation has become quite long. I'll focus on your most recent question "
                "to provide the best response."
            ),
        }
        
        return fallbacks.get(
            error_type,
            "I encountered an issue processing your request. Please try rephrasing or simplifying your question."
        )


# Global instance
_recovery_manager: Optional[ErrorRecoveryManager] = None


def get_recovery_manager() -> ErrorRecoveryManager:
    """Get global error recovery manager."""
    global _recovery_manager
    if _recovery_manager is None:
        _recovery_manager = ErrorRecoveryManager()
    return _recovery_manager
