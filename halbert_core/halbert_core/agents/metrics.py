"""
Agent Metrics and Observability

Tracks agent performance, errors, and usage patterns.
"""

import time
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from collections import defaultdict
from datetime import datetime, timedelta

logger = logging.getLogger('halbert.agents.metrics')


@dataclass
class StateMetrics:
    """Metrics for a single state."""
    count: int = 0
    total_duration_ms: float = 0.0
    errors: int = 0
    
    @property
    def avg_duration_ms(self) -> float:
        return self.total_duration_ms / self.count if self.count > 0 else 0.0


@dataclass
class SessionMetrics:
    """Metrics for a single session."""
    session_id: str
    started_at: float
    ended_at: Optional[float] = None
    
    states_visited: List[str] = field(default_factory=list)
    tool_calls: int = 0
    tool_errors: int = 0
    
    loops: int = 0
    final_confidence: float = 0.0
    crag_action: str = ""
    
    tokens_used: int = 0
    response_length: int = 0
    
    error: Optional[str] = None
    
    @property
    def duration_ms(self) -> float:
        end = self.ended_at or time.time()
        return (end - self.started_at) * 1000
    
    @property
    def success(self) -> bool:
        return self.error is None
    
    def to_dict(self) -> Dict:
        return {
            "session_id": self.session_id,
            "duration_ms": self.duration_ms,
            "states_visited": self.states_visited,
            "tool_calls": self.tool_calls,
            "tool_errors": self.tool_errors,
            "loops": self.loops,
            "final_confidence": self.final_confidence,
            "crag_action": self.crag_action,
            "tokens_used": self.tokens_used,
            "response_length": self.response_length,
            "success": self.success,
            "error": self.error,
        }


class AgentMetricsCollector:
    """
    Collects and aggregates agent metrics.
    
    Tracks:
    - Session counts and durations
    - State transition frequencies
    - Tool call success rates
    - CRAG confidence distribution
    - Error rates
    """
    
    def __init__(self, retention_hours: int = 24):
        self.retention_hours = retention_hours
        
        # Session metrics
        self._sessions: Dict[str, SessionMetrics] = {}
        self._completed_sessions: List[SessionMetrics] = []
        
        # Aggregate metrics
        self._state_metrics: Dict[str, StateMetrics] = defaultdict(StateMetrics)
        self._tool_metrics: Dict[str, Dict[str, int]] = defaultdict(
            lambda: {"calls": 0, "success": 0, "errors": 0}
        )
        
        # Counters
        self._total_sessions = 0
        self._total_errors = 0
        self._confidence_buckets: Dict[str, int] = defaultdict(int)
        
        # State timing
        self._state_start_times: Dict[str, float] = {}
    
    def start_session(self, session_id: str) -> SessionMetrics:
        """Record session start."""
        metrics = SessionMetrics(
            session_id=session_id,
            started_at=time.time()
        )
        self._sessions[session_id] = metrics
        self._total_sessions += 1
        
        logger.debug(f"Metrics: session started {session_id}")
        return metrics
    
    def end_session(
        self,
        session_id: str,
        confidence: float = 0.0,
        crag_action: str = "",
        error: str = None
    ):
        """Record session end."""
        if session_id not in self._sessions:
            return
        
        metrics = self._sessions[session_id]
        metrics.ended_at = time.time()
        metrics.final_confidence = confidence
        metrics.crag_action = crag_action
        metrics.error = error
        
        if error:
            self._total_errors += 1
        
        # Bucket confidence
        bucket = self._get_confidence_bucket(confidence)
        self._confidence_buckets[bucket] += 1
        
        # Move to completed
        self._completed_sessions.append(metrics)
        del self._sessions[session_id]
        
        # Cleanup old sessions
        self._cleanup_old_sessions()
        
        logger.debug(
            f"Metrics: session ended {session_id}, "
            f"duration={metrics.duration_ms:.0f}ms, confidence={confidence:.2f}"
        )
    
    def record_state_enter(self, session_id: str, state: str):
        """Record entering a state."""
        if session_id in self._sessions:
            self._sessions[session_id].states_visited.append(state)
        
        self._state_metrics[state].count += 1
        self._state_start_times[f"{session_id}:{state}"] = time.time()
    
    def record_state_exit(self, session_id: str, state: str, error: bool = False):
        """Record exiting a state."""
        key = f"{session_id}:{state}"
        if key in self._state_start_times:
            duration = (time.time() - self._state_start_times[key]) * 1000
            self._state_metrics[state].total_duration_ms += duration
            del self._state_start_times[key]
        
        if error:
            self._state_metrics[state].errors += 1
    
    def record_tool_call(
        self,
        session_id: str,
        tool_name: str,
        success: bool
    ):
        """Record a tool call."""
        if session_id in self._sessions:
            self._sessions[session_id].tool_calls += 1
            if not success:
                self._sessions[session_id].tool_errors += 1
        
        self._tool_metrics[tool_name]["calls"] += 1
        if success:
            self._tool_metrics[tool_name]["success"] += 1
        else:
            self._tool_metrics[tool_name]["errors"] += 1
    
    def record_loop(self, session_id: str):
        """Record a loop iteration."""
        if session_id in self._sessions:
            self._sessions[session_id].loops += 1
    
    def record_tokens(self, session_id: str, tokens: int):
        """Record token usage."""
        if session_id in self._sessions:
            self._sessions[session_id].tokens_used += tokens
    
    def get_summary(self) -> Dict[str, Any]:
        """Get metrics summary."""
        completed = self._completed_sessions
        
        # Calculate averages
        if completed:
            avg_duration = sum(s.duration_ms for s in completed) / len(completed)
            avg_loops = sum(s.loops for s in completed) / len(completed)
            avg_confidence = sum(s.final_confidence for s in completed) / len(completed)
            avg_tools = sum(s.tool_calls for s in completed) / len(completed)
            success_rate = sum(1 for s in completed if s.success) / len(completed)
        else:
            avg_duration = avg_loops = avg_confidence = avg_tools = 0.0
            success_rate = 1.0
        
        return {
            "total_sessions": self._total_sessions,
            "active_sessions": len(self._sessions),
            "completed_sessions": len(completed),
            "total_errors": self._total_errors,
            "success_rate": success_rate,
            "averages": {
                "duration_ms": avg_duration,
                "loops": avg_loops,
                "confidence": avg_confidence,
                "tool_calls": avg_tools,
            },
            "state_metrics": {
                state: {
                    "count": m.count,
                    "avg_duration_ms": m.avg_duration_ms,
                    "errors": m.errors
                }
                for state, m in self._state_metrics.items()
            },
            "tool_metrics": dict(self._tool_metrics),
            "confidence_distribution": dict(self._confidence_buckets),
        }
    
    def get_recent_sessions(self, limit: int = 10) -> List[Dict]:
        """Get recent completed sessions."""
        recent = sorted(
            self._completed_sessions,
            key=lambda s: s.ended_at or 0,
            reverse=True
        )[:limit]
        return [s.to_dict() for s in recent]
    
    def _get_confidence_bucket(self, confidence: float) -> str:
        """Get confidence bucket label."""
        if confidence >= 0.9:
            return "very_high"
        elif confidence >= 0.7:
            return "high"
        elif confidence >= 0.5:
            return "medium"
        elif confidence >= 0.3:
            return "low"
        else:
            return "very_low"
    
    def _cleanup_old_sessions(self):
        """Remove sessions older than retention period."""
        cutoff = time.time() - (self.retention_hours * 3600)
        self._completed_sessions = [
            s for s in self._completed_sessions
            if (s.ended_at or 0) > cutoff
        ]


# Global metrics collector
_metrics: Optional[AgentMetricsCollector] = None


def get_metrics_collector() -> AgentMetricsCollector:
    """Get global metrics collector."""
    global _metrics
    if _metrics is None:
        _metrics = AgentMetricsCollector()
    return _metrics


def reset_metrics():
    """Reset global metrics (for testing)."""
    global _metrics
    _metrics = None
