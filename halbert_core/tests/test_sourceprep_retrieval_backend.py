# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""SourcePrepRetrievalBackend: the live retrieval path is
context.adapters.SourcePrepAdapter -> backend.search(); format_context is gone."""

from __future__ import annotations

import asyncio

from halbert_core.context.adapters import SourcePrepAdapter
from halbert_core.integrations.sourceprep_retrieval_backend import (
    SourcePrepRetrievalBackend,
)


class _FakeBackend:
    def __init__(self):
        self.calls = []

    def search(self, query, k=5, figure_id=None):
        self.calls.append((query, k, figure_id))
        return [{"text": "t", "source_path": "p", "score": 0.5}]


def test_search_has_no_format_context_and_adapter_still_works():
    assert not hasattr(SourcePrepRetrievalBackend, "format_context")

    fake = _FakeBackend()
    adapter = SourcePrepAdapter(backend=fake)
    out = asyncio.run(adapter.search("q"))
    assert out == [{"content": "t", "metadata": {}, "source": "p", "score": 0.5}]
    assert fake.calls[0][0] == "q"


# ── Scope resolution ──────────────────────────────────────────────────
#
# SourcePrep answers an unknown scope with a silent global union
# (scope_resolver.resolve_mask rule 2), so an unprovisioned scope used to
# widen retrieval instead of narrowing it. resolve_scope walks to the
# nearest provisioned ancestor before the query goes out.


class _FakeClient:
    """Stands in for SourcePrepClient: scope list + captured context call."""

    def __init__(self, scopes=("host", "knowledge_linux"), response=None, raises=False,
                 roles=None):
        self._scopes = list(scopes)
        self._roles = dict(roles or {})
        self._raises = raises
        self.response = response or {"data": {"chunks": []}}
        self.context_calls = []
        self.list_calls = 0

    def list_scopes(self, project_id=None):
        self.list_calls += 1
        if self._raises:
            raise RuntimeError("daemon down")
        return [
            {"id": s, "assigned_to_role": self._roles.get(s)} for s in self._scopes
        ]

    def get_context(self, **kwargs):
        self.context_calls.append(kwargs)
        return self.response


def _backend(**kw):
    return SourcePrepRetrievalBackend(client=_FakeClient(**kw))


def test_resolve_scope_narrows_to_nearest_provisioned_ancestor():
    b = _backend()
    # Fine-grained role scopes are not built yet -> fall back to coarse host.
    assert b.resolve_scope("host_storage") == "host"
    assert b.resolve_scope("host_network_firewall") == "host"
    # An exact match is returned untouched.
    assert b.resolve_scope("knowledge_linux") == "knowledge_linux"
    assert b.resolve_scope("host") == "host"


def test_resolve_scope_returns_none_when_no_ancestor_exists():
    # Deliberate unscoped union beats tripping the daemon's silent fallback.
    assert _backend().resolve_scope("nonsense_xyz") is None
    assert _backend().resolve_scope(None) is None
    assert _backend().resolve_scope("") is None


def test_resolve_scope_fails_open_when_scope_list_unavailable():
    # "Could not verify" must not be read as "no scopes exist", or a daemon
    # hiccup would silently widen every scoped query.
    b = _backend(raises=True)
    assert b.resolve_scope("host_storage") == "host_storage"


def test_scope_list_is_cached_and_invalidatable():
    b = _backend()
    b.resolve_scope("host")
    b.resolve_scope("host")
    assert b.client.list_calls == 1
    b.invalidate_scope_cache()
    b.resolve_scope("host")
    assert b.client.list_calls == 2


def test_search_sends_the_resolved_scope_not_the_requested_one():
    b = _backend()
    b.search("zfs pool degraded", figure_id="host_storage")
    assert b.client.context_calls[0]["scope"] == "host"


def test_search_logs_when_daemon_does_not_honour_the_scope(caplog):
    response = {
        "data": {
            "chunks": [],
            "applied_scope": "global",
            "scope_warning": "requested 'host_storage' not found, used global",
        }
    }
    b = _backend(scopes=("host_storage",), response=response)
    with caplog.at_level("WARNING"):
        b.search("q", figure_id="host_storage")
    assert "scope not honoured" in caplog.text


# ── Role resolution ───────────────────────────────────────────────────
#
# The daemon's role path fails open AND silently: an unknown role returns
# applied_scope="global", echoes applied_role back, and sets no
# scope_warning. Halbert therefore resolves role -> scope id locally and
# never sends role= over the wire.


def test_resolve_role_maps_to_the_scope_carrying_it():
    b = _backend(scopes=("host", "storage_admin"), roles={"storage_admin": "storage-ops"})
    assert b.resolve_role("storage-ops") == "storage_admin"


def test_resolve_role_returns_none_for_an_unassigned_role():
    # Must not be sent to the daemon as role= — that would silently go global.
    b = _backend(scopes=("host", "knowledge_linux"))
    assert b.resolve_role("storage-ops") is None
    assert b.resolve_role(None) is None


def test_resolve_role_result_survives_the_scope_chain():
    # A resolved role id is a real scope, so resolve_scope returns it intact.
    b = _backend(scopes=("host", "storage_admin"), roles={"storage_admin": "storage-ops"})
    assert b.resolve_scope(b.resolve_role("storage-ops")) == "storage_admin"


def test_role_map_is_invalidated_with_the_scope_cache():
    b = _backend(scopes=("host", "storage_admin"), roles={"storage_admin": "storage-ops"})
    b.resolve_role("storage-ops")
    assert b.client.list_calls == 1
    b.invalidate_scope_cache()
    b.resolve_role("storage-ops")
    assert b.client.list_calls == 2
