from __future__ import annotations
from typing import Callable, Dict, Any
from .state import HalbertState

"""
Minimal runtime graph scaffold for Phase 1.
Real orchestration will be implemented (e.g., LangGraph). This stub allows local tests.
"""

NodeFn = Callable[[HalbertState, Dict[str, Any]], HalbertState]

class Graph:
    def __init__(self) -> None:
        self.nodes: Dict[str, NodeFn] = {}
        self.start: str | None = None

    def add_node(self, name: str, fn: NodeFn, start: bool = False) -> None:
        self.nodes[name] = fn
        if start or self.start is None:
            self.start = name

    def run_once(self, state: HalbertState, ctx: Dict[str, Any] | None = None) -> HalbertState:
        if not self.start:
            return state
        fn = self.nodes[self.start]
        return fn(state, ctx or {})

# Placeholder agents

def friend_and_guide(state: HalbertState, ctx: Dict[str, Any]) -> HalbertState:
    state.flags.setdefault("friend", True)
    return state


def eyes_monitor(state: HalbertState, ctx: Dict[str, Any]) -> HalbertState:
    state.flags.setdefault("monitor", True)
    return state


def deep_thinker(state: HalbertState, ctx: Dict[str, Any]) -> HalbertState:
    state.flags.setdefault("thinker", True)
    return state
