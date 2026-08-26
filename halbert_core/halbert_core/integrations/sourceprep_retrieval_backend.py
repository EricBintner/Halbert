# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
SourcePrep Retrieval Backend

Wraps the SourcePrep HTTP client behind the shape of Haloysius's
RetrievalBackend protocol. Its live consumer is
halbert_core.context.adapters.SourcePrepAdapter (the agent's ContextAssembler
retrieval source); Haloysius defines the Protocol but does not call it.

Methods:
    load(figure_id) -> bool
    search(query, k, figure_id) -> List[Dict[str, Any]]

The `figure_id` parameter is repurposed as a scope filter — SourcePrep supports
named scopes (Phase 120) which can partition the config tree by domain
(e.g. "network", "storage", "security"). When figure_id is provided, it's
passed as the `scope` parameter to SourcePrep's context endpoint.
"""

from __future__ import annotations

import logging
import platform
import re
from typing import Any, Dict, List, Optional

from .sourceprep_client import SourcePrepClient

logger = logging.getLogger(__name__)


# ── Intake-domain → scope routing (T-H1.3) ────────────────────────────
#
# Map a natural-language query to a SourcePrep scope so retrieval targets the
# right corpus: this host's live config tree ("host") or the per-platform
# reference/knowledge corpus ("knowledge_<platform>" — scope IDs on the
# SourcePrep daemon use underscores, e.g. "knowledge_macos"; hyphens silently
# fall back to the global union). Ambiguous queries stay unscoped (full
# union). This is a v1 keyword heuristic — the retrieval quality
# gate (T-V.2) validates it on the real corpus and the corpus-classification
# pre-flight (T-V.0) informs tuning.

# Domains from intake/signals.py that are about THIS host's own state/config.
_HOST_DOMAINS = {"config", "service", "security", "network", "storage"}

# Possessive / "this host" language — strong signal the query is about the
# host's own configuration, not general reference knowledge.
_HOST_CUE = re.compile(
    r"\b("
    r"my\s+(?:host|machine|system|server|config|sshd|ssh|firewall|network|service|setup)"
    r"|this\s+(?:host|machine|system|server)"
    r"|currently\s+(?:set|configured|running|using|enabled|disabled)"
    r"|what'?s\s+(?:my|set|configured|currently)"
    r"|on\s+(?:this\s+host|my\s+(?:system|machine|host))"
    r"|show\s+me\s+my"
    r")",
    re.IGNORECASE,
)

# Platform name → knowledge scope suffix.
_PLATFORM_SCOPES = {
    "linux": "linux",
    "darwin": "macos",
    "macos": "macos",
    "freebsd": "bsd",
    "bsd": "bsd",
    "common": "common",
}
_PLATFORM_RE = re.compile(r"\b(linux|mac\s?os|os\s?x|darwin|freebsd|bsd)\b", re.IGNORECASE)


def _default_platform_scope() -> str:
    """Map the running platform to a knowledge scope suffix."""
    sysname = platform.system().lower()
    if sysname == "linux":
        return "linux"
    if sysname == "darwin":
        return "macos"
    if "bsd" in sysname:
        return "bsd"
    return "common"


def scope_for_query(query: str, *, platform: Optional[str] = None) -> Optional[str]:
    """Route *query* to a SourcePrep scope (T-H1.3).

    Resolution:
    1. Detect intake domains; if a host-operational domain is present AND the
       query is phrased about the host's own state → ``"host"``.
    2. Else if a platform is named (or the *platform* override / the running
       host's platform) → ``"knowledge_<platform>"``.
    3. Else if a host-operational domain is present but not host-possessive →
       treat as reference knowledge about the default platform →
       ``"knowledge_<default>"``.
    4. Ambiguous / no signal → ``None`` (unscoped union).
    """
    if not query or not query.strip():
        return None

    # Detect intake domains (cheap, no import cycle: signals is intake).
    domains: set = set()
    try:
        from ..intake.signals import analyze_message  # type: ignore

        sig = analyze_message(query)
        domains = set(sig.detected_domains)
    except Exception:  # pragma: no cover - routing must never raise
        logger.debug("scope_for_query: domain detection failed", exc_info=True)

    host_operational = bool(domains & _HOST_DOMAINS)
    host_cue = bool(_HOST_CUE.search(query))

    # A possessive/this-host cue is specific enough to route to the host
    # config tree on its own — "what's my sshd_config set to?" is about THIS
    # host regardless of which domain keyword matched.
    if host_cue:
        return "host"

    # Named platform in the query wins over the default.
    m = _PLATFORM_RE.search(query)
    plat = _PLATFORM_SCOPES.get((m.group(1).lower().replace(" ", "").replace("osx", "macos")
                                 if m else ""), None)
    if plat is None:
        plat = platform or _default_platform_scope()

    # A host-operational domain without a host cue reads as reference
    # knowledge about the platform (e.g. "explain the Port directive").
    if host_operational or m:
        return f"knowledge_{plat}"

    return None


class SourcePrepRetrievalBackend:
    """Retrieval backend backed by SourcePrep's HTTP API.

    search() is consumed by halbert_core.context.adapters.SourcePrepAdapter
    (the agent's ContextAssembler retrieval source). Haloysius defines the
    RetrievalBackend Protocol but does not call it.

    Note: haloysius.seam.RetrievalBackend is @runtime_checkable and lists a
    format_context() method that this class deliberately does not implement
    (it had no callers). No isinstance(..., RetrievalBackend) checks exist in
    Halbert or Haloysius; HalbertAppSeam only type-annotates the backend.

    Usage:
        # Live agent path (retrieval):
        from halbert_core.context.adapters import SourcePrepAdapter
        adapter = SourcePrepAdapter(project_id="halbert-host")
        docs = await adapter.search("why is sshd refusing connections?")

        # Seam registration (retrieval + model + governance):
        from halbert_core.integrations.app_seam import wire_halbert_seam
        wire_halbert_seam(sourceprep_project_id="halbert-host")
    """

    def __init__(
        self,
        project_id: Optional[str] = None,
        base_url: Optional[str] = None,
        client: Optional[SourcePrepClient] = None,
        default_k: int = 5,
        default_max_chars: int = 12000,
    ):
        self.client = client or SourcePrepClient(
            base_url=base_url,
            project_id=project_id,
        )
        self.default_k = default_k
        self.default_max_chars = default_max_chars
        self._loaded = False

    def load(self, figure_id: Optional[str] = None) -> bool:
        """Verify the SourcePrep daemon is reachable and project is built.

        The `figure_id` parameter is unused here — SourcePrep doesn't have
        a per-figure load concept. We check daemon health and project
        availability.

        Returns:
            True if the daemon is reachable, False otherwise.
        """
        if not self.client.health():
            logger.warning("SourcePrep daemon not reachable")
            self._loaded = False
            return False

        self._loaded = True
        return True

    def search(
        self,
        query: str,
        k: int = 3,
        figure_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Search the SourcePrep index for relevant context.

        Uses the /projects/{id}/context endpoint (structured mode) which
        returns chunks with source paths, scores, and trace-expanded
        neighbors. This is richer than raw search — it includes LOD
        compression and trace expansion.

        The `figure_id` parameter is mapped to SourcePrep's `scope` filter
        for domain-specific retrieval (e.g. "network", "storage").

        Args:
            query: Natural language search query.
            k: Number of results to retrieve.
            figure_id: Optional scope filter (mapped to SourcePrep scope).

        Returns:
            List of result dicts with at least a 'text' key, plus
            'source_path', 'score', and 'metadata' when available.
        """
        if not query.strip():
            return []

        try:
            response = self.client.get_context(
                query=query,
                k=k,
                max_chars=self.default_max_chars,
                structured=True,
                trace_expand=True,
                scope=figure_id,
            )
        except Exception as e:
            logger.error(f"SourcePrep context retrieval failed: {e}")
            return []

        return self._parse_context_response(response)

    def _parse_context_response(
        self, response: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Parse SourcePrep's structured context response into result dicts.

        SourcePrep returns either:
        - {'data': {'chunks': [...], 'context': '...'}} (structured mode)
        - {'data': {'results': [...]}} (search mode)
        - {'data': {'context': '...'}} (ambient mode, no chunks)

        We normalize to a list of dicts with 'text', 'source_path', 'score'.
        """
        data = response.get("data", response)

        # Structured context mode — has chunks list
        chunks = data.get("chunks")
        if chunks and isinstance(chunks, list):
            results = []
            for chunk in chunks:
                if not isinstance(chunk, dict):
                    continue
                text = chunk.get("text") or chunk.get("content") or ""
                if not text:
                    continue
                results.append(
                    {
                        "text": text,
                        "source_path": chunk.get("source_path", ""),
                        "score": chunk.get("score", 0.0),
                        "metadata": {
                            k: v
                            for k, v in chunk.items()
                            if k not in ("text", "content", "source_path", "score")
                        },
                    }
                )
            return results

        # Search mode — has results list
        results = data.get("results")
        if results and isinstance(results, list):
            normalized = []
            for r in results:
                if not isinstance(r, dict):
                    continue
                doc = r.get("doc", r)
                text = doc.get("text") or doc.get("content") or ""
                if not text:
                    continue
                normalized.append(
                    {
                        "text": text,
                        "source_path": doc.get("source_path", ""),
                        "score": r.get("score", doc.get("score", 0.0)),
                        "metadata": {
                            k: v
                            for k, v in doc.items()
                            if k not in ("text", "content", "source_path", "score")
                        },
                    }
                )
            return normalized

        # Ambient mode — has context string but no chunks
        context_text = data.get("context")
        if context_text and isinstance(context_text, str):
            return [{"text": context_text, "source_path": "", "score": 0.0}]

        logger.debug(f"SourcePrep response had no parseable content")
        return []
