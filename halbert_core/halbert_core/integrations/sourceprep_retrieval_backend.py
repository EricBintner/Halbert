"""
SourcePrep Retrieval Backend

Wraps the SourcePrep HTTP client behind Haloysius's RetrievalBackend protocol.
This is the seam adapter that lets Haloysius's cognitive core retrieve context
from SourcePrep's semantic index without knowing about SourcePrep directly.

Implements the RetrievalBackend protocol from haloysius.seam:
    load(figure_id) -> bool
    search(query, k, figure_id) -> List[Dict[str, Any]]
    format_context(results, max_chars) -> str

The `figure_id` parameter is repurposed as a scope filter — SourcePrep supports
named scopes (Phase 120) which can partition the config tree by domain
(e.g. "network", "storage", "security"). When figure_id is provided, it's
passed as the `scope` parameter to SourcePrep's context endpoint.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from .sourceprep_client import SourcePrepClient

logger = logging.getLogger(__name__)


class SourcePrepRetrievalBackend:
    """RetrievalBackend implementation backed by SourcePrep's HTTP API.

    Implements the RetrievalBackend protocol from haloysius.seam.
    Haloysius's cognitive core calls search() and format_context() to
    inject retrieved context into prompts.

    Usage:
        from halbert_core.integrations.sourceprep_retrieval_backend import SourcePrepRetrievalBackend

        backend = SourcePrepRetrievalBackend(
            project_id="halbert-host",
        )

        # Register with Haloysius
        from haloysius.seam import register_app_seam, AppSeam

        class HalbertAppSeam:
            def get_model_backend(self): return None  # wired separately
            def get_retrieval_backend(self): return backend
            def get_governance(self): return None  # permissive for now

        register_app_seam(HalbertAppSeam())
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

    def format_context(
        self,
        results: List[Dict[str, Any]],
        max_chars: int = 1500,
    ) -> str:
        """Format search results into a context string for prompt injection.

        Produces a clean, readable context block with source citations:

            [Source: /etc/fstab]
            UUID=a1b2... / ext4 defaults 0 1
            ...

            [Source: /etc/systemd/system/foo.service]
            [Unit]
            ...

        Args:
            results: List of result dicts from search().
            max_chars: Maximum total characters to include.

        Returns:
            Formatted context string.
        """
        if not results:
            return ""

        parts: List[str] = []
        total = 0

        for r in results:
            text = r.get("text", "")
            source = r.get("source_path", "")

            if not text:
                continue

            header = f"[Source: {source}]" if source else "[Source: unknown]"
            block = f"{header}\n{text}"

            if total + len(block) > max_chars:
                remaining = max_chars - total
                if remaining > 100:
                    block = block[:remaining] + "\n...[truncated]"
                    parts.append(block)
                break

            parts.append(block)
            total += len(block)

        return "\n\n".join(parts)
