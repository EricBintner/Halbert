"""
Haloysius Memory Adapter

Wraps Haloysius's PersonaMemoryStore with dict-based callbacks compatible
with advance_turn()'s memory_store_add / memory_store_search parameters.

advance_turn() expects:
  memory_store_add: Callable[[Any], None]     — receives a PersonaMemory
  memory_store_search: Callable[[str, int], List[Any]] — query, k → results

This adapter bridges Halbert's dict-based world to Haloysius's dataclass-based
world. Halbert code works with plain dicts; this adapter converts to
PersonaMemory before handing to PersonaMemoryStore.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


def _to_memory_type(value: str) -> Any:
    """Convert a string to Haloysius MemoryType enum."""
    from haloysius.memory_v2.types import MemoryType

    try:
        return MemoryType(value)
    except ValueError:
        logger.warning(f"Unknown memory type '{value}', defaulting to EPISODIC")
        return MemoryType.EPISODIC


def dict_to_persona_memory(d: Dict[str, Any]) -> Any:
    """Convert a plain dict to a Haloysius PersonaMemory dataclass."""
    from haloysius.memory_v2.types import PersonaMemory

    mem_type = d.get("memory_type", "episodic")
    if isinstance(mem_type, str):
        mem_type = _to_memory_type(mem_type)

    return PersonaMemory(
        id=d.get("id", f"mem_{uuid.uuid4().hex[:12]}"),
        persona_id=d.get("persona_id", "halbert"),
        memory_type=mem_type,
        content=d["content"],
        emotional_weight=d.get("emotional_weight", 0.5),
        emotional_valence=d.get("emotional_valence", 0.0),
        believed=d.get("believed", True),
        invented=d.get("invented", False),
        occurred_at=d.get("occurred_at"),
        source=d.get("source", "system_event"),
        tags=d.get("tags", []),
        triggered_by=d.get("triggered_by"),
        metadata=d.get("metadata", {}),
    )


def persona_memory_to_dict(mem: Any) -> Dict[str, Any]:
    """Convert a PersonaMemory dataclass back to a plain dict."""
    return mem.to_dict()


class HaloysiusMemoryAdapter:
    """Adapter that connects advance_turn() memory callbacks to PersonaMemoryStore.

    Usage:
        store = PersonaMemoryStore("halbert")
        adapter = HaloysiusMemoryAdapter(store)

        advance_turn(
            cognition=cognition,
            user_message=msg,
            assistant_response=resp,
            memory_store_add=adapter.add_callback(),
            memory_store_search=adapter.search_callback(),
        )
    """

    def __init__(self, store: Any):
        self.store = store

    def add_callback(self) -> Callable[[Any], None]:
        """Returns a callback for advance_turn's memory_store_add parameter.

        Accepts either a PersonaMemory dataclass or a plain dict.
        """

        def _add(memory: Any) -> None:
            if isinstance(memory, dict):
                memory = dict_to_persona_memory(memory)
            try:
                op, reason, mem_id = self.store.smart_add(memory)
                logger.debug(
                    f"Memory store add: op={op}, reason={reason}, id={mem_id}"
                )
            except Exception as e:
                logger.error(f"Memory store add failed: {e}")

        return _add

    def search_callback(self) -> Callable[[str, int], List[Any]]:
        """Returns a callback for advance_turn's memory_store_search parameter.

        Returns a list of PersonaMemory objects (or dicts if the store
        returns dicts). The caller (thought promoter) reads .content
        and .memory_type attributes.
        """

        def _search(query: str, k: int) -> List[Any]:
            try:
                results = self.store.search(query, k=k)
                return results
            except Exception as e:
                logger.error(f"Memory store search failed: {e}")
                return []

        return _search

    def add_system_event(
        self,
        content: str,
        emotional_weight: float = 0.5,
        emotional_valence: float = 0.0,
        occurred_at: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> None:
        """Convenience method: add a system event as an episodic memory.

        This is the autobiographical write path — system events phrased
        in first person become EPISODIC memories in the persona's memory store.
        """
        memory = dict_to_persona_memory(
            {
                "persona_id": "halbert",
                "memory_type": "episodic",
                "content": content,
                "emotional_weight": emotional_weight,
                "emotional_valence": emotional_valence,
                "source": "system_event",
                "occurred_at": occurred_at,
                "tags": tags or [],
            }
        )
        self.add_callback()(memory)
