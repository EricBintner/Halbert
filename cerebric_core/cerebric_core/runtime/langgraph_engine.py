from __future__ import annotations
from typing import Any, Dict, Optional

"""
LangGraph POC engine (soft import). If langgraph is unavailable, this module
provides a no-op shim so environments without the dependency keep working.
"""

try:
    from langgraph.graph import StateGraph  # type: ignore
except Exception:  # pragma: no cover
    StateGraph = None  # type: ignore


def _friend_and_guide(state: Dict[str, Any]) -> Dict[str, Any]:
    msgs = state.get("messages", [])
    msgs.append({"role": "assistant", "text": "Hello from LangGraph POC."})
    state["messages"] = msgs
    return state


def _eyes_monitor(state: Dict[str, Any]) -> Dict[str, Any]:
    state.setdefault("telemetry_checked", True)
    return state


def _deep_thinker(state: Dict[str, Any]) -> Dict[str, Any]:
    state.setdefault("analysis", "none")
    return state


class LGEngine:
    def __init__(self) -> None:
        self._graph = None
        if StateGraph is not None:
            try:
                g = StateGraph(dict)  # type: ignore[arg-type]
                g.add_node("friend_and_guide", _friend_and_guide)
                g.add_node("eyes_monitor", _eyes_monitor)
                g.add_node("deep_thinker", _deep_thinker)
                g.add_edge("friend_and_guide", "eyes_monitor")
                g.add_edge("eyes_monitor", "deep_thinker")
                g.set_entry_point("friend_and_guide")
                self._graph = g.compile()
            except Exception:
                self._graph = None

    def available(self) -> bool:
        return self._graph is not None

    def run_once(self, state: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if self._graph is None:
            raise RuntimeError("LangGraph not available")
        s = state or {}
        out = self._graph.invoke(s)  # type: ignore[no-untyped-call]
        return dict(out or {})
