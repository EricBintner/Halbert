from __future__ import annotations
from typing import Dict, Any
from .graph import Graph, friend_and_guide, eyes_monitor, deep_thinker
from .state import HalbertState

"""
Minimal runtime Engine to wire the placeholder graph and state.
Replace with real orchestration (e.g., LangGraph) during POC.
"""

class Engine:
    def __init__(self) -> None:
        self.graph = Graph()
        self.state = HalbertState()
        # Register nodes (placeholder)
        self.graph.add_node("friend_and_guide", friend_and_guide, start=True)
        self.graph.add_node("eyes_monitor", eyes_monitor)
        self.graph.add_node("deep_thinker", deep_thinker)

    def tick(self, ctx: Dict[str, Any] | None = None) -> HalbertState:
        """Run a single iteration in the placeholder graph."""
        self.state = self.graph.run_once(self.state, ctx or {})
        return self.state
