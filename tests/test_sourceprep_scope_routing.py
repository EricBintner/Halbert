"""Tests: SourcePrep intake-domain → scope routing (T-H1.3).

The scope_for_query heuristic routes a natural-language query to the right
SourcePrep scope (host config tree vs per-platform knowledge corpus) without
a running daemon. These are unit tests of the routing logic only; end-to-end
scoped retrieval is verified by the quality gate (T-V.2).
"""
from __future__ import annotations

import pytest

from halbert_core.integrations.sourceprep_retrieval_backend import scope_for_query


@pytest.mark.parametrize(
    "query, expected",
    [
        # Possessive / "this host" → host config tree.
        ("what is my sshd_config set to?", "host"),
        ("show me my current firewall rules", "host"),
        ("is my sshd using port 22", "host"),
        ("what's currently configured on this host", "host"),
        # Platform named → knowledge-<platform>.
        ("how do I configure sshd on linux?", "knowledge-linux"),
        ("how to set up nfs on macos", "knowledge-macos"),
        ("freebsd service management", "knowledge-bsd"),
        # Operational domain, no host cue → reference knowledge about the
        # default platform.
        ("explain the Port directive", "knowledge-linux"),
        ("how does dns resolution work", "knowledge-linux"),
        # No signal → unscoped union.
        ("what does PermitRootLogin accept", None),
        ("tell me a joke", None),
        ("", None),
    ],
)
def test_scope_for_query_routes(query, expected):
    assert scope_for_query(query, platform="linux") == expected


def test_scope_for_query_platform_override():
    # Default platform comes from the override / running host when none named.
    assert scope_for_query("explain the Port directive", platform="macos") == "knowledge-macos"


def test_get_context_passes_scope(monkeypatch):
    """get_context includes 'scope' in the request body only when set."""
    from halbert_core.integrations.sourceprep_client import SourcePrepClient

    captured: dict = {}

    def fake_post(self, path, json_body, project_id=None):
        captured["path"] = path
        captured["body"] = json_body
        return {"chunks": []}

    monkeypatch.setattr(SourcePrepClient, "_post", fake_post)
    client = SourcePrepClient(project_id="halbert")

    client.get_context(query="x", scope="host")
    assert captured["body"]["scope"] == "host"

    client.get_context(query="x")  # no scope → not in body
    assert "scope" not in captured["body"]


def test_backend_search_passes_figure_id_as_scope(monkeypatch):
    """SourcePrepRetrievalBackend.search maps figure_id → scope with
    trace_expand=True (T-H1.3)."""
    from halbert_core.integrations.sourceprep_retrieval_backend import (
        SourcePrepRetrievalBackend,
    )

    captured: dict = {}

    class _FakeClient:
        def health(self):
            return True

        def get_context(self, **kw):
            captured.update(kw)
            return {"chunks": []}

    backend = SourcePrepRetrievalBackend(client=_FakeClient())
    backend.search("how do I configure sshd on linux?", k=3, figure_id="knowledge-linux")
    assert captured["scope"] == "knowledge-linux"
    assert captured["trace_expand"] is True