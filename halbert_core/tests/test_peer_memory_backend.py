# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""P2d: PeerMemoryBackend integration tests — the singular-entity memory loop.

The P2d acceptance, end to end against the REAL pieces: a workstation's
``PeerMemoryBackend`` (haloysius, P2a) writes through the HA server's
real peer memory routes (``routes/memory.py``, P2b, FastAPI TestClient)
into a real ``PersonaMemoryStore`` — and the HA server's own cognition
side retrieves it. Plus the P2c wiring: ``_create_memory_store`` picks
the peer backend when canonical_memory_url + peer_token are set, and
falls back to a local store when the token is missing.

Unit-level wire-contract coverage lives with the backend
(haloysius memory_v2/tests/test_peer_backend.py); this file is the
cross-repo loop.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from haloysius.memory_v2.peer_backend import (
    PeerMemoryBackend,
    PeerMemoryUnavailable,
)
from haloysius.memory_v2.store import PersonaMemoryStore
from haloysius.memory_v2.types import MemoryOperation, MemoryType, PersonaMemory

from halbert_core.dashboard.routes import memory as memory_routes
from halbert_core.federation.peer_middleware import (
    PeerContext,
    require_peer_auth,
    get_peers_config,
)
from halbert_core.federation.peers_config import PeerCredential

TOKEN = "peer-token-1"


# ---------------------------------------------------------------------------
# The HA server: real routes + real store, peer auth stubbed to a paired peer
# ---------------------------------------------------------------------------

@pytest.fixture
def ha_store(tmp_path):
    with patch.object(PersonaMemoryStore, "_get_data_path",
                      return_value=tmp_path / "memories.json"):
        yield PersonaMemoryStore("ha_persona")


@pytest.fixture
def ha_server(ha_store, monkeypatch):
    """The HA server's memory API over a real FastAPI app + real store."""
    monkeypatch.setattr(memory_routes, "_get_persona_memory_store", lambda: ha_store)
    # The per-persona store cache must not leak between tests.
    monkeypatch.setattr(memory_routes, "_persona_stores", {})

    app = FastAPI()
    app.include_router(memory_routes.router, prefix="/api/memory")
    stub = PeerContext(
        node_id="workstation", node_name="Workstation",
        role="compute_provider", capabilities=[],
        credential=PeerCredential(
            node_id="workstation", node_name="Workstation",
            role="compute_provider", token_hash="sha256:stub",
            paired_at="2026-01-01T00:00:00Z",
        ),
    )
    app.dependency_overrides[require_peer_auth] = lambda: stub
    return TestClient(app)


# ---------------------------------------------------------------------------
# The workstation: a PeerMemoryBackend pointed at the (TestClient) server
# ---------------------------------------------------------------------------

class _TestClientTransport:
    """Requests-shaped transport that routes the backend's calls into the
    FastAPI TestClient — no socket, full real-route semantics."""

    def __init__(self, client: TestClient, token: str = TOKEN):
        self.client = client
        self.token = token
        self.base = "http://ha-server.lan:8001"

    def __call__(self, verb, url, headers=None, timeout=None, **kw):
        path = url[len(self.base):]
        auth = (headers or {}).get("Authorization", "")
        request_headers = {"Authorization": auth} if auth else {}
        if verb == "POST":
            resp = self.client.post(path, json=kw.get("json"),
                                    headers=request_headers)
        elif verb == "DELETE":
            resp = self.client.delete(path, headers=request_headers)
        else:
            resp = self.client.get(path, params=kw.get("params"),
                                   headers=request_headers)
        wrapped = MagicMock()
        wrapped.status_code = resp.status_code
        wrapped.text = resp.text
        wrapped.json = resp.json
        return wrapped


@pytest.fixture
def backend(ha_server):
    transport = _TestClientTransport(ha_server)
    with patch("haloysius.memory_v2.peer_backend.requests.request", new=transport):
        yield PeerMemoryBackend(
            peer_url="http://ha-server.lan:8001",
            bearer_token=TOKEN,
            timeout=5.0,
        )


def _memory(content: str, **kwargs) -> PersonaMemory:
    return PersonaMemory(
        id=kwargs.pop("id", "mem_001"),
        persona_id="ha_persona",
        memory_type=kwargs.pop("memory_type", MemoryType.SEMANTIC),
        content=content,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# The loop: workstation writes → HA server's store has it → HA retrieves
# ---------------------------------------------------------------------------

class TestSingularEntityMemoryLoop:
    def test_workstation_write_lands_in_ha_store_and_is_retrievable(self, backend, ha_store):
        operation, reason, memory_id = backend.smart_add(
            _memory("They showed me their garden today",
                    memory_type=MemoryType.EPISODIC, emotional_weight=0.8))
        assert operation is MemoryOperation.ADD
        assert memory_id == "mem_001"

        # The HA server's OWN store has it — no sync step, one store.
        assert ha_store.get("mem_001").content == "They showed me their garden today"

        # And the HA server's cognition side retrieves it (store.search
        # is what HaloysiusMemoryAdapter's search callback calls).
        results = ha_store.search("garden", k=5)
        assert results and "garden" in results[0].content

    def test_ha_side_search_answers_through_the_backend(self, backend):
        """The workstation's own cognition reads the same autobiography."""
        backend.smart_add(_memory("They run Arch Linux on the server",
                                  keywords=["arch", "linux"]))
        results = backend.search("arch linux", k=5)
        assert results and results[0].content == "They run Arch Linux on the server"

    def test_duplicate_detection_runs_on_the_canonical_host(self, backend, ha_store):
        """A re-add of identical content is a NOOP decided where the whole
        autobiography is visible — the HA server's store."""
        backend.smart_add(_memory("Their name is Alex"))
        operation, _, _ = backend.smart_add(_memory("Their name is Alex"))
        assert operation is MemoryOperation.NOOP

    def test_get_and_delete_through_the_routes(self, backend, ha_store):
        backend.smart_add(_memory("Their name is Alex"))
        assert backend.get("mem_001").content == "Their name is Alex"
        assert backend.delete("mem_001") is True
        # Soft delete: retained but out of retrieval.
        assert backend.search("Alex", k=10) == []

    def test_missing_memory_is_none_not_an_error(self, backend):
        assert backend.get("nope") is None
        assert backend.delete("nope") is False


# ---------------------------------------------------------------------------
# P2c wiring: _create_memory_store picks the right backend
# ---------------------------------------------------------------------------

class TestCognitionWiring:
    def test_peer_backend_when_canonical_url_and_token_set(self, monkeypatch):
        from halbert_core.integrations import cognition_wiring as cw

        monkeypatch.setattr(cw, "_get_canonical_memory_url",
                            lambda: "http://ha-server.lan:8001")
        monkeypatch.setattr(cw, "_get_peer_token", lambda: "tok")
        monkeypatch.setattr(cw, "_get_persona_id", lambda: "ha_persona")
        store = cw._create_memory_store()
        assert isinstance(store, PeerMemoryBackend)
        assert store.peer_url == "http://ha-server.lan:8001"

    def test_local_store_without_canonical_url(self, monkeypatch):
        from halbert_core.integrations import cognition_wiring as cw

        monkeypatch.setattr(cw, "_get_canonical_memory_url", lambda: "")
        monkeypatch.setattr(cw, "_get_peer_token", lambda: "tok")
        monkeypatch.setattr(cw, "_get_persona_id", lambda: "ha_persona")
        assert isinstance(cw._create_memory_store(), PersonaMemoryStore)

    def test_local_store_when_token_missing(self, monkeypatch):
        """canonical URL set but no peer token: a cognition tick with local
        memory beats no cognition at all."""
        from halbert_core.integrations import cognition_wiring as cw

        monkeypatch.setattr(cw, "_get_canonical_memory_url",
                            lambda: "http://ha-server.lan:8001")
        monkeypatch.setattr(cw, "_get_peer_token", lambda: "")
        monkeypatch.setattr(cw, "_get_persona_id", lambda: "ha_persona")
        assert isinstance(cw._create_memory_store(), PersonaMemoryStore)

    def test_adapter_callbacks_fail_soft_when_peer_down(self, monkeypatch):
        """The P2c degradation contract: when the canonical host is
        unreachable, the adapter's callbacks log and continue — the
        cognition tick never crashes on a dead peer."""
        from halbert_core.integrations import cognition_wiring as cw
        from halbert_core.integrations.haloysius_memory_adapter import (
            HaloysiusMemoryAdapter,
        )

        monkeypatch.setattr(cw, "_get_canonical_memory_url",
                            lambda: "http://ha-server.lan:8001")
        monkeypatch.setattr(cw, "_get_peer_token", lambda: "tok")
        monkeypatch.setattr(cw, "_get_persona_id", lambda: "ha_persona")
        adapter = HaloysiusMemoryAdapter(cw._create_memory_store())

        def dead(verb, url, **kw):
            raise PeerMemoryUnavailable("refused")

        with patch("haloysius.memory_v2.peer_backend.requests.request", new=dead):
            # Neither callback raises; search degrades to [].
            adapter.add_callback()(_memory("x"))
            assert adapter.search_callback()("garden", 5) == []