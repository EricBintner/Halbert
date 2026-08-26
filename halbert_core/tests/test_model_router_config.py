# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""ModelRouter (services/{name}/explain) resolves its models from llm_config."""
import yaml

from halbert_core.model.router import ModelRouter, TaskType


def _router(tmp_path, monkeypatch, data):
    monkeypatch.setattr(ModelRouter, "_init_providers", lambda self: None)  # no network
    cfg = tmp_path / "models.yml"
    cfg.write_text(yaml.safe_dump(data))
    return ModelRouter(config_path=cfg)


def test_router_reads_llm_config_slots(tmp_path, monkeypatch):
    router = _router(tmp_path, monkeypatch, {
        "llm_config": {
            "saved_endpoints": [
                {"id": "l", "name": "Local", "provider": "ollama", "url": "http://localhost:11434"},
                {"id": "r", "name": "Remote", "provider": "openai", "url": "http://gpu:1234", "api_key": "k"},
            ],
            "chat_model": {"enabled": True, "endpoint_id": "l", "model": "chat-a"},
            "specialist_model": {"enabled": True, "endpoint_id": "r", "model": "spec-b"},
        },
        "routing": {"strategy": "auto", "prefer_specialist_for": ["code_generation"], "complexity_threshold": 0.5},
    })
    assert router.orchestrator_id == "chat-a"
    assert router.specialist_id == "spec-b"
    assert router._route_task(TaskType.CODE_GENERATION, prefer_specialist=False) == ("spec-b", "openai", "http://gpu:1234")
    assert router._route_task(TaskType.CHAT, prefer_specialist=False) == ("chat-a", "ollama", "http://localhost:11434")
    assert router.get_status()["specialist"]["enabled"] is True


def test_router_migrates_legacy_keys_in_memory(tmp_path, monkeypatch):
    router = _router(tmp_path, monkeypatch, {
        "orchestrator": {"model": "old", "endpoint": "http://localhost:11434"},
    })
    assert router.orchestrator_id == "old"
    assert router.specialist_id is None
    assert "orchestrator" not in router.config
    assert router._route_task(TaskType.CHAT, prefer_specialist=True) == ("old", "ollama", "http://localhost:11434")
