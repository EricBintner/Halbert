# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""GET/PUT /llm/config — the picker's config API, a thin layer over model.llm_config."""
import json
from unittest.mock import patch

import pytest

pytest.importorskip("fastapi")

from halbert_core.dashboard.routes import llm as routes
from halbert_core.model import llm_config as store

OLLAMA = "http://localhost:11434"


def test_get_config_shape(models_config_dir):
    with patch.object(routes.llm_store, "ensure_local_ollama_endpoint", return_value=False):
        out = routes.get_llm_config()
    data = out["data"]
    assert set(data["llm_config"]) == {"saved_endpoints", "chat_model", "specialist_model", "vision_model"}
    assert "ollama" in data["chat_capable_providers"]
    assert "anthropic" in data["chat_capable_providers"]


def test_put_merges_and_returns_config(models_config_dir):
    body = routes.LLMConfigUpdate(llm_config={
        "saved_endpoints": [{"id": "e1", "name": "Local", "provider": "ollama", "url": OLLAMA}],
        "chat_model": {"enabled": True, "endpoint_id": "e1", "model": "m1"},
    })
    out = routes.update_llm_config(body)
    assert out["data"]["llm_config"]["chat_model"]["model"] == "m1"
    assert store.load()["chat_model"]["enabled"] is True


def test_put_rejects_non_chat_capable_provider(models_config_dir):
    store.save({"saved_endpoints": [{"id": "g1", "name": "Gemini", "provider": "google",
                                     "url": "https://generativelanguage.googleapis.com", "api_key": "k"}]})
    resp = routes.update_llm_config(routes.LLMConfigUpdate(llm_config={
        "chat_model": {"enabled": True, "endpoint_id": "g1", "model": "m"},
    }))
    assert resp.status_code == 422
    err = json.loads(resp.body)["error"]
    assert err["code"] == "PROVIDER_NOT_CHAT_CAPABLE" and err["slot"] == "chat_model"
    assert store.load()["chat_model"]["enabled"] is False


def test_sourceprep_stubs_are_gone():
    paths = {r.path for r in routes.router.routes}
    for gone in ("/global/config", "/llm/plan-limits", "/embedding/status", "/embedding/download",
                 "/llm/slots/status", "/api/llm/proxy/cloud-models"):
        assert gone not in paths
    assert {"/llm/config", "/api/llm/proxy/models", "/api/llm/proxy/test", "/api/llm/proxy/test-model"} <= paths
