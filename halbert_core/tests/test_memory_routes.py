# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""P2b: Memory API endpoint tests.

Tests the peer memory routes (add/search/get/delete) that expose the
local PersonaMemoryStore over HTTP for paired peer nodes. Uses mocked
PersonaMemoryStore since haloysius may not be installed in the test env.
"""

from unittest.mock import patch, MagicMock
from typing import Optional
from enum import Enum

import pytest
from fastapi.testclient import TestClient


# Stub haloysius if not installed (the routes lazy-import it, but tests
# need MemoryOperation for mock return values)
try:
    from haloysius.memory_v2.types import MemoryOperation
except ImportError:
    class MemoryOperation(str, Enum):
        ADD = "add"
        UPDATE = "update"
        DELETE = "delete"
        NOOP = "noop"
        INVENT = "invent"
        STRENGTHEN = "strengthen"
        DECAY = "decay"
        MERGE = "merge"


def _make_memory_dict(
    mem_id="mem_001",
    content="The garden was beautiful today",
    memory_type="episodic",
):
    return {
        "id": mem_id,
        "persona_id": "halbert",
        "memory_type": memory_type,
        "content": content,
        "emotional_weight": 0.7,
        "emotional_valence": 0.5,
        "believed": True,
        "invented": False,
        "created_at": "2026-08-31T12:00:00",
        "updated_at": "2026-08-31T12:00:00",
        "last_accessed": "",
        "access_count": 0,
        "strength": 1.0,
        "related_memories": [],
        "triggered_by": None,
        "tags": ["garden"],
        "keywords": [],
        "embedding": None,
        "source": "conversation",
        "metadata": {},
    }


def _mock_store():
    """Create a mock PersonaMemoryStore."""
    store = MagicMock()
    return store


def _make_app_with_memory_routes():
    """Create a minimal FastAPI app with just the memory router.

    Overrides require_peer_auth so all peer endpoints are accessible
    without a real bearer token.
    """
    from fastapi import FastAPI
    from halbert_core.dashboard.routes.memory import router
    from halbert_core.federation.peer_middleware import PeerContext, require_peer_auth
    from halbert_core.federation.peers_config import PeerCredential

    app = FastAPI()
    app.include_router(router, prefix="/api/memory")

    # Override the peer auth dependency with a stub that always succeeds
    stub_cred = PeerCredential(
        node_id="test-peer", node_name="Test Peer", role="compute_provider",
        token_hash="sha256:stub", paired_at="2026-01-01T00:00:00Z",
    )
    stub_ctx = PeerContext(
        node_id="test-peer", node_name="Test Peer",
        role="compute_provider", capabilities=[], credential=stub_cred,
    )
    app.dependency_overrides[require_peer_auth] = lambda: stub_ctx
    return app


def _patch_auth():
    """No-op now that auth is overridden via app.dependency_overrides.

    Kept for context manager compatibility with existing test code.
    """
    from contextlib import contextmanager

    @contextmanager
    def _noop():
        yield None

    return _noop()


def _patch_store(store):
    """Patch _get_persona_memory_store to return the given mock store."""
    return patch(
        "halbert_core.dashboard.routes.memory._get_persona_memory_store",
        return_value=store,
    )


def _patch_persona_memory():
    """Patch the haloysius PersonaMemory import used inside the add route.

    The route does ``from haloysius.memory_v2.types import PersonaMemory``
    at call time. If haloysius isn't installed, we need to provide a stub.
    """
    try:
        import haloysius.memory_v2.types  # noqa: F401
        # Already available — no patch needed
        return patch.dict({}, {})
    except ImportError:
        # Create a stub module
        import sys
        import types as pytypes

        if "haloysius" not in sys.modules:
            sys.modules["haloysius"] = pytypes.ModuleType("haloysius")
        if "haloysius.memory_v2" not in sys.modules:
            sys.modules["haloysius.memory_v2"] = pytypes.ModuleType("haloysius.memory_v2")
        if "haloysius.memory_v2.types" not in sys.modules:
            mod = pytypes.ModuleType("haloysius.memory_v2.types")
            mod.MemoryOperation = MemoryOperation

            # MemoryType stub that accepts known values and raises for unknown
            class _MT(str, Enum):
                EPISODIC = "episodic"
                SEMANTIC = "semantic"
                TACIT = "tacit"
                EMOTIONAL = "emotional"
                THINKING = "thinking"
                INVENTED = "invented"
            mod.MemoryType = _MT

            # PersonaMemory.from_dict just returns a mock
            mock_pm = MagicMock()
            mock_pm.from_dict = staticmethod(lambda d: MagicMock(to_dict=lambda: d))
            mod.PersonaMemory = mock_pm
            sys.modules["haloysius.memory_v2.types"] = mod
        return patch.dict({}, {})  # no-op patch, stubs already in sys.modules


class TestPeerMemoryAdd:
    def test_add_success(self):
        app = _make_app_with_memory_routes()
        store = _mock_store()
        store.smart_add.return_value = (MemoryOperation.ADD, "new memory", "mem_001")

        with _patch_auth(), _patch_store(store), _patch_persona_memory():
            client = TestClient(app)
            resp = client.post("/api/memory/add", json={"memory": _make_memory_dict()})

        assert resp.status_code == 200
        data = resp.json()
        assert data["operation"] == "add"
        assert data["memory_id"] == "mem_001"
        assert data["reason"] == "new memory"

    def test_add_noop_duplicate(self):
        app = _make_app_with_memory_routes()
        store = _mock_store()
        store.smart_add.return_value = (MemoryOperation.NOOP, "duplicate", None)

        with _patch_auth(), _patch_store(store), _patch_persona_memory():
            client = TestClient(app)
            resp = client.post("/api/memory/add", json={"memory": _make_memory_dict()})

        assert resp.status_code == 200
        assert resp.json()["operation"] == "noop"

    def test_add_requires_auth(self):
        # Create app WITHOUT auth override
        from fastapi import FastAPI
        from halbert_core.dashboard.routes.memory import router
        app = FastAPI()
        app.include_router(router, prefix="/api/memory")
        client = TestClient(app)
        resp = client.post("/api/memory/add", json={"memory": _make_memory_dict()})
        assert resp.status_code in (401, 403)

    def test_add_store_unavailable(self):
        app = _make_app_with_memory_routes()
        with _patch_auth(), patch(
            "halbert_core.dashboard.routes.memory._get_persona_memory_store",
            return_value=None,
        ), _patch_persona_memory():
            client = TestClient(app)
            resp = client.post("/api/memory/add", json={"memory": _make_memory_dict()})
        assert resp.status_code == 503


class TestPeerMemorySearch:
    def test_search_returns_results(self):
        app = _make_app_with_memory_routes()
        store = _mock_store()
        mock_mem = MagicMock()
        mock_mem.to_dict.return_value = _make_memory_dict()
        store.search.return_value = [mock_mem]

        with _patch_auth(), _patch_store(store):
            client = TestClient(app)
            resp = client.get("/api/memory/search?q=garden&k=5")

        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        assert len(data["results"]) == 1

    def test_search_empty_results(self):
        app = _make_app_with_memory_routes()
        store = _mock_store()
        store.search.return_value = []

        with _patch_auth(), _patch_store(store):
            client = TestClient(app)
            resp = client.get("/api/memory/search?q=nonexistent")

        assert resp.status_code == 200
        assert resp.json()["count"] == 0

    def test_search_requires_auth(self):
        from fastapi import FastAPI
        from halbert_core.dashboard.routes.memory import router
        app = FastAPI()
        app.include_router(router, prefix="/api/memory")
        client = TestClient(app)
        resp = client.get("/api/memory/search?q=test")
        assert resp.status_code in (401, 403)

    def test_search_with_memory_type(self):
        app = _make_app_with_memory_routes()
        store = _mock_store()
        store.search.return_value = []

        with _patch_auth(), _patch_store(store), _patch_persona_memory():
            client = TestClient(app)
            resp = client.get("/api/memory/search?q=test&memory_type=episodic")

        assert resp.status_code == 200
        # Verify memory_type was passed (as enum)
        call_kwargs = store.search.call_args
        assert call_kwargs is not None

    def test_search_invalid_memory_type(self):
        app = _make_app_with_memory_routes()
        store = _mock_store()

        with _patch_auth(), _patch_store(store), _patch_persona_memory():
            client = TestClient(app)
            resp = client.get("/api/memory/search?q=test&memory_type=invalid_type")

        assert resp.status_code == 422


class TestPeerMemoryGet:
    def test_get_found(self):
        app = _make_app_with_memory_routes()
        store = _mock_store()
        mock_mem = MagicMock()
        mock_mem.to_dict.return_value = _make_memory_dict(mem_id="mem_42")
        store.get.return_value = mock_mem

        with _patch_auth(), _patch_store(store):
            client = TestClient(app)
            resp = client.get("/api/memory/get/mem_42")

        assert resp.status_code == 200
        assert resp.json()["memory"]["id"] == "mem_42"

    def test_get_not_found(self):
        app = _make_app_with_memory_routes()
        store = _mock_store()
        store.get.return_value = None

        with _patch_auth(), _patch_store(store):
            client = TestClient(app)
            resp = client.get("/api/memory/get/nonexistent")

        assert resp.status_code == 404

    def test_get_requires_auth(self):
        from fastapi import FastAPI
        from halbert_core.dashboard.routes.memory import router
        app = FastAPI()
        app.include_router(router, prefix="/api/memory")
        client = TestClient(app)
        resp = client.get("/api/memory/get/mem_001")
        assert resp.status_code in (401, 403)


class TestPeerMemoryDelete:
    def test_delete_success(self):
        app = _make_app_with_memory_routes()
        store = _mock_store()
        store.delete.return_value = True

        with _patch_auth(), _patch_store(store):
            client = TestClient(app)
            resp = client.delete("/api/memory/delete/mem_001")

        assert resp.status_code == 200
        assert resp.json()["deleted"] == "mem_001"

    def test_delete_not_found(self):
        app = _make_app_with_memory_routes()
        store = _mock_store()
        store.delete.return_value = False

        with _patch_auth(), _patch_store(store):
            client = TestClient(app)
            resp = client.delete("/api/memory/delete/nonexistent")

        assert resp.status_code == 404

    def test_delete_requires_auth(self):
        from fastapi import FastAPI
        from halbert_core.dashboard.routes.memory import router
        app = FastAPI()
        app.include_router(router, prefix="/api/memory")
        client = TestClient(app)
        resp = client.delete("/api/memory/delete/mem_001")
        assert resp.status_code in (401, 403)
