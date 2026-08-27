# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
SourcePrep HTTP Client

Synchronous HTTP wrapper for the SourcePrep daemon API.
Used by the SourcePrepRetrievalBackend adapter to wrap prep_search,
prep_concepts, and prep_observe behind Haloysius's RetrievalBackend protocol.

Does NOT use the MCP tool interface — the MCP tool drops the `chunks` list
from context responses. This client calls the HTTP API directly.

Endpoints wrapped:
  POST /projects/{project_id}/context       — semantic context assembly (structured)
  POST /projects/{project_id}/search        — raw semantic search
  POST /projects/{project_id}/observations  — save observation
  GET  /projects/{project_id}/observations  — list/search observations
  POST /projects/{project_id}/concepts/search — FTS search concepts
  POST /projects/{project_id}/concepts       — save concept
  GET  /projects/{project_id}/concepts       — list concepts
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

_DEFAULT_PROJECT_ROOT = Path("~/.local/share/halbert/sourceprep")  # sourceprep_template.yml project.root


def resolve_default_project_id() -> str:
    """SOURCEPREP_PROJECT_ID env var, else <template root>/.sourceprep/project.json 'id', else ''."""
    pid = os.environ.get("SOURCEPREP_PROJECT_ID", "").strip()
    if pid:
        return pid
    root = Path(os.environ.get("SOURCEPREP_PROJECT_ROOT", str(_DEFAULT_PROJECT_ROOT))).expanduser()
    marker = root / ".sourceprep" / "project.json"
    try:
        data = json.loads(marker.read_text())
        pid = str(data.get("id", "")).strip()
        if pid:
            logger.info(f"SourcePrep project id resolved from {marker}: {pid}")
        return pid
    except (OSError, ValueError, AttributeError):
        return ""


class SourcePrepClient:
    """Synchronous HTTP client for the SourcePrep daemon."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        project_id: Optional[str] = None,
        timeout: float = 30.0,
    ):
        self.base_url = (
            base_url
            or os.environ.get("SOURCEPREP_URL", "http://localhost:8400")
        ).rstrip("/")
        self.project_id = project_id or resolve_default_project_id()
        self.timeout = timeout

    def _url(self, path: str, project_id: Optional[str] = None) -> str:
        pid = project_id or self.project_id
        if not pid:
            raise ValueError(
                "project_id is required — set SOURCEPREP_PROJECT_ID or pass explicitly"
            )
        return f"{self.base_url}{path.format(project_id=pid)}"

    def _post(self, path: str, json_body: Dict[str, Any], project_id: Optional[str] = None) -> Dict[str, Any]:
        url = self._url(path, project_id=project_id)
        try:
            resp = requests.post(url, json=json_body, timeout=self.timeout)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            logger.error(f"SourcePrep POST {url} failed: {e}")
            raise

    def _get(
        self,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        project_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        url = self._url(path, project_id=project_id)
        try:
            resp = requests.get(url, params=params, timeout=self.timeout)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            logger.error(f"SourcePrep GET {url} failed: {e}")
            raise

    # -- Context / Search ---------------------------------------------------

    def get_context(
        self,
        query: str = "",
        k: int = 5,
        max_chars: int = 60000,
        structured: bool = True,
        trace_expand: bool = True,
        min_score: float = 0.15,
        project_id: Optional[str] = None,
        scope: Optional[str] = None,
        scope_mode: str = "hard",
    ) -> Dict[str, Any]:
        """POST /projects/{id}/context — structured context assembly.

        With structured=True, returns a dict with 'chunks' list containing
        individual result chunks. This is the primary retrieval method for
        the RetrievalBackend adapter — we render from structured chunks, not
        stashed markdown.

        ``scope`` (T-H1.3) is included in the request body only when set —
        the SourcePrep API already supports per-scope masking (scope_resolver).
        None (default) leaves the query unscoped (full union).

        ``scope_mode`` defaults to "hard" — out-of-scope files are excluded
        from results entirely (pre-filter via exclude_paths), not just
        score-boosted. This is required for platform isolation: a macOS
        query must never return Linux arch-wiki content.

        ``max_chars`` is a budget over the whole candidate list and it *binds*:
        at k=25 the same query returns 9 chunks at 12000 and 17 at 60000. The
        old 12000 default silently truncated any deep pull, so it is now 60000.
        Note this default does not govern the live agent path —
        SourcePrepRetrievalBackend passes its own ``default_max_chars``.
        """
        body = {
            "query": query,
            "k": k,
            "max_chars": max_chars,
            "structured": structured,
            "trace_expand": trace_expand,
            "min_score": min_score,
            "include_sources": True,
        }
        if scope is not None:
            body["scope"] = scope
            body["scope_mode"] = scope_mode
        return self._post("/projects/{project_id}/context", body)

    def search(
        self,
        query: str,
        k: int = 8,
        min_score: float = 0.15,
        project_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """POST /projects/{id}/search — raw semantic search."""
        return self._post(
            "/projects/{project_id}/search",
            {
                "query": query,
                "k": k,
                "min_score": min_score,
            },
        )

    # -- Scopes -------------------------------------------------------------

    def list_scopes(self, project_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """GET /projects/{id}/scopes — the scopes provisioned on the daemon.

        Returns each scope's ``id`` (daemon-native, underscored), its
        ``display_name`` (as written in sourceprep_template.yml, hyphenated),
        and ``assigned_to_role``. Callers use this to check a scope exists
        before querying it: the context endpoint answers an unknown scope
        with a silent global union (scope_resolver.resolve_mask rule 2), so
        an unchecked scope name degrades retrieval instead of failing.

        Returns an empty list if the daemon is unreachable — callers must
        treat "no scopes known" as "cannot verify", not as "none exist".
        """
        try:
            data = self._get("/projects/{project_id}/scopes", project_id=project_id)
        except Exception:
            logger.debug("SourcePrep scope listing failed", exc_info=True)
            return []
        inner = data.get("data", data) if isinstance(data, dict) else {}
        scopes = inner.get("scopes", inner) if isinstance(inner, dict) else inner
        return [s for s in scopes if isinstance(s, dict)] if isinstance(scopes, list) else []

    # -- Observations -------------------------------------------------------

    def save_observation(
        self,
        content: str,
        file_path: Optional[str] = None,
        category: str = "note",
        created_by: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """POST /projects/{id}/observations — save an observation.

        Categories: note, decision, bug, pattern, assumption.
        This is the objective event log — system events recorded as
        file-anchored, stale-flagged observations.
        """
        return self._post(
            "/projects/{project_id}/observations",
            {
                "content": content,
                "file_path": file_path,
                "category": category,
                "created_by": created_by or "halbert",
            },
        )

    def list_observations(
        self,
        query: Optional[str] = None,
        file_path: Optional[str] = None,
        limit: int = 10,
        include_stale: bool = True,
        project_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """GET /projects/{id}/observations — list/search observations."""
        params: Dict[str, Any] = {"limit": limit, "include_stale": include_stale}
        if query:
            params["query"] = query
        if file_path:
            params["file_path"] = file_path
        return self._get("/projects/{project_id}/observations", params=params)

    # -- Concepts -----------------------------------------------------------

    def search_concepts(
        self,
        query: str,
        limit: int = 10,
        project_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """POST /projects/{id}/concepts/search — FTS search over concepts.

        Concepts are the "WhyBrain" — rationale for configuration decisions,
        constraints, design decisions.
        """
        return self._post(
            "/projects/{project_id}/concepts/search",
            {"query": query, "limit": limit},
        )

    def save_concept(
        self,
        title: str,
        content: str,
        category: str = "technical",
        anchors: Optional[List[str]] = None,
        assertion: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """POST /projects/{id}/concepts — save a concept.

        Categories: architecture, domain, product, epistemic, process,
        brand, security, technical, pattern, constraint, decision.
        """
        body: Dict[str, Any] = {
            "title": title,
            "content": content,
            "category": category,
        }
        if anchors:
            body["anchors"] = anchors
        if assertion:
            body["assertion"] = assertion
        return self._post("/projects/{project_id}/concepts", body)

    def list_concepts(
        self,
        project_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """GET /projects/{id}/concepts — list all concepts."""
        return self._get("/projects/{project_id}/concepts")

    # -- Health -------------------------------------------------------------

    def health(self) -> bool:
        """Check if the SourcePrep daemon is reachable."""
        try:
            resp = requests.get(
                f"{self.base_url}/health",
                timeout=5.0,
            )
            return resp.status_code == 200
        except requests.RequestException:
            return False

    # -- Trace: External Edges & Impact (Phase 3) ---------------------------

    def push_external_edges(
        self,
        edges: List[Dict[str, Any]],
        replace_origin: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """POST /projects/{id}/trace/external-edges — push config dependency edges.

        If replace_origin is set, existing edges with that origin are cleared
        before appending the new edges. Use replace_origin='config' for a
        clean refresh on config changes.
        """
        body: Dict[str, Any] = {"edges": edges}
        if replace_origin:
            body["replace_origin"] = replace_origin
        return self._post("/projects/{project_id}/trace/external-edges", body, project_id=project_id)

    def get_impact(
        self,
        file_path: str,
        max_hops: int = 2,
        max_nodes: int = 30,
        project_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """GET /projects/{id}/trace/impact/{node_id} — blast-radius query.

        Returns the reverse-dependency graph: everything that depends on
        the given file. Answers "what breaks if I edit this config?"
        """
        node_id = file_path if file_path.startswith("file:") else f"file:{file_path}"
        pid = project_id or self.project_id
        if not pid:
            raise ValueError("project_id is required")
        url = f"{self.base_url}/projects/{pid}/trace/impact/{node_id}"
        try:
            resp = requests.get(
                url,
                params={"max_hops": max_hops, "max_nodes": max_nodes},
                timeout=self.timeout,
            )
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            logger.error(f"SourcePrep GET impact {url} failed: {e}")
            raise
