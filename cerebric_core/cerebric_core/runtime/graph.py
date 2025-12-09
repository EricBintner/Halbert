from __future__ import annotations
from typing import Callable, Dict, Any
from .state import CerebricState

"""
Minimal runtime graph scaffold for Phase 1.
Real orchestration will be implemented (e.g., LangGraph). This stub allows local tests.
"""

NodeFn = Callable[[CerebricState, Dict[str, Any]], CerebricState]

class Graph:
    def __init__(self) -> None:
        self.nodes: Dict[str, NodeFn] = {}
        self.start: str | None = None

    def add_node(self, name: str, fn: NodeFn, start: bool = False) -> None:
        self.nodes[name] = fn
        if start or self.start is None:
            self.start = name

    def run_once(self, state: CerebricState, ctx: Dict[str, Any] | None = None) -> CerebricState:
        if not self.start:
            return state
        fn = self.nodes[self.start]
        return fn(state, ctx or {})

# Placeholder agents

def friend_and_guide(state: CerebricState, ctx: Dict[str, Any]) -> CerebricState:
    state.flags.setdefault("friend", True)
    return state


def eyes_monitor(state: CerebricState, ctx: Dict[str, Any]) -> CerebricState:
    state.flags.setdefault("monitor", True)
    return state


def deep_thinker(state: CerebricState, ctx: Dict[str, Any]) -> CerebricState:
    state.flags.setdefault("thinker", True)
    return state
