"""
Extended Context Adapters

Additional context source adapters for the ContextAssembler, porting
critical gaps identified in the RQ-D re-audit:
  - SystemIdentityAdapter: machine identity, hostname, OS info
  - SelfKnowledgeAdapter: CRAG-enriched self-knowledge context
  - TelemetryAdapter: system telemetry and health data
  - SafetyAdapter: input validation and output filtering

These adapters follow the same async interface as the existing adapters
in adapters.py: they provide async search()/recall() methods that return
List[Dict[str, Any]].

The ContextAssembler's priority system and budget allocation are extended
to include these new sources.
"""

from __future__ import annotations

import logging
import socket
from typing import Any, Dict, List, Optional

logger = logging.getLogger("halbert.context.extra_adapters")


class SystemIdentityAdapter:
    """Provides system identity context (hostname, OS, hardware summary).

    This is the machine's sense of self — who it is, what hardware it runs on.
    Equivalent to chat.py's get_system_identity() but as an async adapter
    for the ContextAssembler.
    """

    def __init__(self, identity_override: Optional[str] = None):
        self._identity_override = identity_override
        self._cached: Optional[str] = None

    async def search(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Return system identity context. Query is ignored — identity is static."""
        identity = self._get_identity()
        if not identity:
            return []
        return [
            {
                "content": identity,
                "category": "identity",
                "metadata": {"source": "system_identity"},
            }
        ]

    def _get_identity(self) -> str:
        """Build system identity string."""
        if self._identity_override:
            return self._identity_override

        if self._cached:
            return self._cached

        try:
            import platform

            hostname = socket.gethostname()
            os_name = platform.system()
            os_release = platform.release()
            machine = platform.machine()

            parts = [
                f"## System Identity",
                f"- Hostname: {hostname}",
                f"- OS: {os_name} {os_release}",
                f"- Architecture: {machine}",
            ]

            # Try to get more info from discovery
            try:
                from ..discovery.engine import get_engine

                engine = get_engine()
                if engine:
                    summary = engine.get_system_summary()
                    if summary:
                        if hasattr(summary, "cpu_count"):
                            parts.append(f"- CPU cores: {summary.cpu_count}")
                        if hasattr(summary, "memory_total"):
                            parts.append(f"- Memory: {summary.memory_total}")
                        if hasattr(summary, "disk_count"):
                            parts.append(f"- Disks: {summary.disk_count}")
            except Exception:
                pass

            self._cached = "\n".join(parts)
            return self._cached
        except Exception as e:
            logger.warning(f"Failed to build system identity: {e}")
            return ""


class SelfKnowledgeAdapter:
    """Provides CRAG-enriched self-knowledge context.

    Wraps the self-knowledge retrieval from chat.py's
    get_self_knowledge_context() as an async adapter.
    """

    def __init__(self, self_knowledge_store=None):
        self._store = self_knowledge_store
        self._initialized = False

    def _ensure_initialized(self):
        if self._initialized:
            return
        if self._store is None:
            try:
                from ..memory.store import get_memory_store

                self._store = get_memory_store()
                logger.info("SelfKnowledge adapter initialized")
            except Exception as e:
                logger.warning(f"Could not initialize self-knowledge store: {e}")
        self._initialized = True

    async def search(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Search self-knowledge for relevant context."""
        self._ensure_initialized()
        if self._store is None:
            return []

        try:
            if hasattr(self._store, "search"):
                results = self._store.search(query, limit=limit)
            elif hasattr(self._store, "recall"):
                results = self._store.recall(query, limit=limit)
            else:
                return []

            items = []
            for r in results:
                if isinstance(r, dict):
                    items.append(
                        {
                            "content": r.get("content", str(r)),
                            "category": r.get("type", "self_knowledge"),
                            "metadata": r.get("metadata", {}),
                        }
                    )
                else:
                    items.append(
                        {
                            "content": str(r),
                            "category": "self_knowledge",
                            "metadata": {},
                        }
                    )
            return items
        except Exception as e:
            logger.error(f"Self-knowledge search error: {e}")
            return []


class TelemetryAdapter:
    """Provides system telemetry context.

    Wraps the telemetry retrieval from chat.py's get_telemetry_context()
    as an async adapter. Returns recent telemetry events relevant to the query.
    """

    def __init__(self, telemetry_store=None):
        self._store = telemetry_store
        self._initialized = False

    def _ensure_initialized(self):
        if self._initialized:
            return
        if self._store is None:
            # Try existing telemetry modules (if they exist in future)
            try:
                from ..obs.collector import get_collector

                self._store = get_collector()
                logger.info("Telemetry adapter initialized from obs.collector")
            except Exception:
                pass
        self._initialized = True

    async def search(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Search telemetry for relevant events.

        Falls back to live psutil readings if no telemetry store is wired.
        """
        self._ensure_initialized()

        # If we have a store, use it
        if self._store is not None:
            try:
                if hasattr(self._store, "search"):
                    results = self._store.search(query, limit=limit)
                elif hasattr(self._store, "get_recent"):
                    results = self._store.get_recent(limit=limit)
                else:
                    results = []

                items = []
                for r in results:
                    if isinstance(r, dict):
                        items.append(
                            {
                                "content": r.get("content", r.get("summary", str(r))),
                                "category": r.get("category", "telemetry"),
                                "metadata": {
                                    k: v
                                    for k, v in r.items()
                                    if k not in ("content", "summary", "category")
                                },
                            }
                        )
                    else:
                        items.append(
                            {
                                "content": str(r),
                                "category": "telemetry",
                                "metadata": {},
                            }
                        )
                return items
            except Exception as e:
                logger.error(f"Telemetry search error: {e}")

        # Fallback: live psutil readings
        return self._get_live_telemetry()

    def _get_live_telemetry(self) -> List[Dict[str, Any]]:
        """Get live system telemetry via psutil."""
        try:
            import psutil
            import os

            cpu_percent = psutil.cpu_percent(interval=0.5)
            mem = psutil.virtual_memory()
            load_avg = os.getloadavg()[0] if hasattr(os, "getloadavg") else 0.0

            parts = [
                f"## System Telemetry",
                f"- CPU usage: {cpu_percent:.1f}%",
                f"- Memory: {mem.percent:.1f}% ({mem.used // (1024**3):.1f}GB / {mem.total // (1024**3):.1f}GB)",
                f"- Load average: {load_avg:.2f}",
            ]

            # Disk usage for root
            try:
                disk = psutil.disk_usage("/")
                parts.append(f"- Root disk: {disk.percent:.1f}% ({disk.used // (1024**3):.1f}GB / {disk.total // (1024**3):.1f}GB)")
            except Exception:
                pass

            # Network connections count
            try:
                net = psutil.net_connections()
                parts.append(f"- Network connections: {len(net)}")
            except Exception:
                pass

            return [
                {
                    "content": "\n".join(parts),
                    "category": "telemetry",
                    "metadata": {"source": "psutil", "live": True},
                }
            ]
        except ImportError:
            logger.debug("psutil not available for live telemetry")
            return []
        except Exception as e:
            logger.error(f"Live telemetry error: {e}")
            return []


class SafetyAdapter:
    """Input/output safety validation adapter.

    Wraps the SafetyValidator and OutputFilter from prompts/safety.py.
    This is NOT a context source — it's a gate that runs before/after
    context assembly. The ContextAssembler calls validate_input() before
    assembly and filter_output() after response generation.

    However, for integration with the ContextAssembler's source model,
    we expose it as a "safety" source that returns safety rules as
    context for the LLM.
    """

    def __init__(self, validator=None):
        self._validator = validator
        self._initialized = False

    def _ensure_initialized(self):
        if self._initialized:
            return
        if self._validator is None:
            try:
                from ..prompts.safety import get_safety_validator

                self._validator = get_safety_validator()
            except Exception:
                pass
        self._initialized = True

    async def search(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Return safety rules as context for the LLM."""
        self._ensure_initialized()
        if self._validator is None:
            return []

        try:
            rules = self._validator.get_rules_summary() if hasattr(
                self._validator, "get_rules_summary"
            ) else ""
            if not rules:
                return []
            return [
                {
                    "content": rules,
                    "category": "safety_rules",
                    "metadata": {"source": "safety_validator"},
                }
            ]
        except Exception as e:
            logger.error(f"Safety rules retrieval error: {e}")
            return []

    def validate_input(self, message: str) -> Dict[str, Any]:
        """Validate user input before processing."""
        self._ensure_initialized()
        if self._validator is None:
            return {"safe": True, "blocked": False}

        try:
            result = self._validator.validate_input(message)
            return {
                "safe": result.safe if hasattr(result, "safe") else True,
                "blocked": result.blocked if hasattr(result, "blocked") else False,
                "reason": result.reason if hasattr(result, "reason") else None,
            }
        except Exception as e:
            logger.error(f"Input validation error: {e}")
            return {"safe": True, "blocked": False}

    def filter_output(self, response: str) -> str:
        """Filter LLM output before sending to user."""
        self._ensure_initialized()
        if self._validator is None:
            return response

        try:
            if hasattr(self._validator, "filter_output"):
                return self._validator.filter_output(response)
            return response
        except Exception as e:
            logger.error(f"Output filter error: {e}")
            return response


def create_extended_context_assembler():
    """Create a ContextAssembler with all sources wired (existing + extended).

    This extends create_wired_context_assembler() with the new adapters:
    system_identity, self_knowledge, telemetry, safety.

    The ContextAssembler's priority system is extended to include the
    new sources with appropriate weights.
    """
    from .assembler import ContextAssembler
    from .tokens import TokenCounter
    from .adapters import (
        RAGServiceAdapter,
        SourcePrepAdapter,
        DiscoveryServiceAdapter,
        MemoryServiceAdapter,
    )

    token_counter = TokenCounter()
    retrieval_adapter = SourcePrepAdapter()
    discovery_adapter = DiscoveryServiceAdapter()
    memory_adapter = MemoryServiceAdapter()
    identity_adapter = SystemIdentityAdapter()
    self_knowledge_adapter = SelfKnowledgeAdapter()
    telemetry_adapter = TelemetryAdapter()
    safety_adapter = SafetyAdapter()

    # Extended priorities — new sources added with moderate weights
    extended_priorities = {
        "conversation": 1.0,
        "retrieval": 0.8,
        "memory": 0.7,
        "discovery": 0.6,
        "observations": 0.5,
        "system_identity": 0.4,
        "self_knowledge": 0.45,
        "telemetry": 0.35,
        "safety": 0.3,
    }

    return ContextAssembler(
        retrieval_service=retrieval_adapter,
        memory_service=memory_adapter,
        discovery_service=discovery_adapter,
        token_counter=token_counter,
        priorities=extended_priorities,
        extra_sources={
            "system_identity": identity_adapter,
            "self_knowledge": self_knowledge_adapter,
            "telemetry": telemetry_adapter,
            "safety": safety_adapter,
        },
    )
