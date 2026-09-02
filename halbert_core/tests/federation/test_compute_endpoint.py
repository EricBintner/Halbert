# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""SE-09 / R10-F2 / SE-08 / R10-F3: the workstation side of peer compute.

The Compute Peer card ships on the home variant and every turn through it
was a 404: ``federation/compute_endpoint`` was never mounted (app.py mounts
``routes.compute``, which is the capacity *probe* — a different module), and
``_submit_to_broker`` raised NotImplementedError behind it. Three components
also disagreed about the health route's address, and none of them was right,
because it did not exist.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from halbert_core.federation import compute_endpoint as ce


# ---------------------------------------------------------------------------
# Mounted
# ---------------------------------------------------------------------------

class TestTheEndpointIsReachable:

    @pytest.fixture
    def client(self):
        from halbert_core.dashboard.app import create_app
        return TestClient(create_app())

    @pytest.mark.parametrize("method,path", [
        ("get", ce.COMPUTE_HEALTH_PATH),
        ("get", ce.COMPUTE_MODELS_PATH),
        ("post", ce.COMPUTE_CHAT_PATH),
    ])
    def test_the_real_app_serves_it(self, client, method, path):
        resp = getattr(client, method)(path) if method == "get" else client.post(path, json={})
        assert resp.status_code != 404, f"{path} is served by nothing"
        # 401, not 200: peer auth is required, which is the point.
        assert resp.status_code == 401

    def test_everyone_agrees_where_health_lives(self):
        """SE-08. compute_router probed /health, config_wizard probed
        /health, PeerProvider probed /models, and /health existed nowhere."""
        from halbert_core.model.providers.peer import (
            COMPUTE_CHAT_PATH, COMPUTE_HEALTH_PATH, COMPUTE_MODELS_PATH,
        )

        assert COMPUTE_HEALTH_PATH == ce.COMPUTE_HEALTH_PATH
        assert COMPUTE_MODELS_PATH == ce.COMPUTE_MODELS_PATH
        assert COMPUTE_CHAT_PATH == ce.COMPUTE_CHAT_PATH


# ---------------------------------------------------------------------------
# What a peer may run here
# ---------------------------------------------------------------------------

def _config(**slots):
    """A models.yml-shaped dict with the given slots enabled."""
    endpoints: list = []
    llm: dict = {"saved_endpoints": endpoints}
    for i, (slot, (model, provider)) in enumerate(slots.items()):
        ep_id = f"ep{i}"
        endpoints.append({
            "id": ep_id, "url": f"http://localhost:1143{i}",
            "provider": provider, "api_key": "",
        })
        llm[slot] = {"enabled": True, "endpoint_id": ep_id, "model": model}
    return {"llm_config": llm}


class TestWhichModelsAreOffered:

    def _with_config(self, monkeypatch, cfg):
        monkeypatch.setattr("halbert_core.model.llm_config.load_file", lambda *a, **k: cfg)

    def test_an_ordinary_local_model_is_servable(self, monkeypatch):
        self._with_config(monkeypatch, _config(chat_model=("qwen:7b", "ollama")))
        assert set(ce._peer_servable_models()) == {"qwen:7b"}

    def test_the_secure_slot_is_never_offered(self, monkeypatch):
        """It exists so secret-bearing turns stay on this machine; serving it
        to a peer inverts its whole reason (finding M11)."""
        self._with_config(monkeypatch, _config(
            chat_model=("qwen:7b", "ollama"),
            secure_model=("private:7b", "ollama"),
        ))
        servable = ce._peer_servable_models()
        assert "qwen:7b" in servable
        assert "private:7b" not in servable

    def test_apple_foundation_is_never_offered(self, monkeypatch):
        """Local-only by licence and by design — it backs the Mac's own
        slots, never peer offload."""
        self._with_config(monkeypatch, _config(
            chat_model=("afm", "apple-foundation"),
        ))
        assert ce._peer_servable_models() == {}

    def test_a_cloud_slot_is_not_relayed(self, monkeypatch):
        """A peer asking this host to spend the operator's cloud credit is
        not what peer compute is."""
        self._with_config(monkeypatch, _config(chat_model=("gpt-x", "openai")))
        assert ce._peer_servable_models() == {}

    def test_no_configured_model_is_a_503_not_a_crash(self, monkeypatch):
        from fastapi import HTTPException

        self._with_config(monkeypatch, {"llm_config": {}})
        with pytest.raises(HTTPException) as exc:
            ce._resolve_peer_model("anything")
        assert exc.value.status_code == 503

    def test_an_unservable_model_is_refused(self, monkeypatch):
        from fastapi import HTTPException

        self._with_config(monkeypatch, _config(
            chat_model=("qwen:7b", "ollama"),
            secure_model=("private:7b", "ollama"),
        ))
        with pytest.raises(HTTPException) as exc:
            ce._resolve_peer_model("private:7b")
        # Same answer as a model that does not exist: the refusal must not
        # tell a peer which secure model this host holds.
        assert exc.value.status_code == 404
        with pytest.raises(HTTPException) as missing:
            ce._resolve_peer_model("no-such-model")
        assert missing.value.detail.replace("no-such-model", "private:7b") == exc.value.detail

    def test_naming_no_model_lets_the_workstation_govern(self, monkeypatch):
        """Handoff S3 5.2: an empty model means the host chooses."""
        self._with_config(monkeypatch, _config(chat_model=("qwen:7b", "ollama")))
        assert ce._resolve_peer_model("").model == "qwen:7b"


# ---------------------------------------------------------------------------
# Running the turn
# ---------------------------------------------------------------------------

class TestTheTurnActuallyRuns:

    @pytest.mark.asyncio
    async def test_a_peer_turn_reaches_the_local_model_and_comes_back(self, monkeypatch):
        seen = {}

        def _fake_chat(endpoint, model, messages, **kwargs):
            seen.update(endpoint=endpoint, model=model, messages=messages, **kwargs)
            return {"content": "42", "raw": {"usage": {"total_tokens": 7}}}

        monkeypatch.setattr("halbert_core.model.llm_config.load_file",
                            lambda *a, **k: _config(chat_model=("qwen:7b", "ollama")))
        monkeypatch.setattr("halbert_core.model.client.call_llm_chat", _fake_chat)

        resp = await ce.peer_compute_chat(
            ce.ChatCompletionRequest(
                model="qwen:7b",
                messages=[ce.ChatMessage(role="user", content="what is 6 times 7")],
            ),
            peer=ce.PeerContext(
                node_id="sat-1", node_name="Kitchen", role="satellite",
                capabilities=[], credential=None,
            ),
        )

        assert resp.choices[0].message.content == "42"
        assert resp.usage.total_tokens == 7
        assert seen["model"] == "qwen:7b"
        assert seen["provider"] == "ollama"
        assert seen["messages"] == [{"role": "user", "content": "what is 6 times 7"}]

    @pytest.mark.asyncio
    async def test_an_unreachable_local_model_is_a_502_not_a_500(self, monkeypatch):
        from fastapi import HTTPException

        def _boom(*args, **kwargs):
            raise ConnectionError("ollama is not running")

        monkeypatch.setattr("halbert_core.model.llm_config.load_file",
                            lambda *a, **k: _config(chat_model=("qwen:7b", "ollama")))
        monkeypatch.setattr("halbert_core.model.client.call_llm_chat", _boom)

        with pytest.raises(HTTPException) as exc:
            await ce.peer_compute_chat(
                ce.ChatCompletionRequest(
                    model="qwen:7b",
                    messages=[ce.ChatMessage(role="user", content="hi")],
                ),
                peer=ce.PeerContext(
                    node_id="sat-1", node_name="Kitchen", role="satellite",
                    capabilities=[], credential=None,
                ),
            )
        assert exc.value.status_code == 502
        # And says nothing about the host's internals.
        assert "ollama" not in str(exc.value.detail).lower()
