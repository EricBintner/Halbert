# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""/settings/model/* — read-only status for the Quick-setup strip, store-backed writers.

Coroutines are driven with asyncio.run so these pass with or without
pytest-asyncio (CI has it; a bare dev venv may not).
"""
import asyncio
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("fastapi")

from halbert_core.dashboard.routes import settings as routes
from halbert_core.model import llm_config as store

OLLAMA = "http://localhost:11434"


def _fake_models(entries):
    async def fake(_client, _url):
        return entries
    return fake


def test_status_reports_chat_and_is_read_only(models_config_dir):
    store.save({
        "saved_endpoints": [{"id": "e1", "name": "Local", "provider": "ollama", "url": OLLAMA}],
        "chat_model": {"enabled": True, "endpoint_id": "e1", "model": "m1"},
    })
    before = (models_config_dir / "models.yml").read_text()
    with patch.object(routes, "_ollama_models", _fake_models([{"name": "m1"}, {"name": "m2"}])), \
         patch.object(routes, "_detect_hardware_tier", return_value=(3, None)):
        out = asyncio.run(routes.get_model_status())
    assert out["chat"] == {"configured": True, "model": "m1", "endpoint_url": OLLAMA,
                           "provider": "ollama", "reachable": True, "model_available": True}
    assert out["local_ollama"] == {"reachable": True, "url": OLLAMA, "model_count": 2}
    assert out["hardware"] == {"tier": 3, "total_vram_gb": None}
    assert (models_config_dir / "models.yml").read_text() == before


def test_status_on_fresh_install_writes_nothing(models_config_dir):
    with patch.object(routes, "_ollama_models", _fake_models([{"name": "m1"}])), \
         patch.object(routes, "_detect_hardware_tier", return_value=(1, None)):
        out = asyncio.run(routes.get_model_status())
    assert out["chat"]["configured"] is False
    assert out["local_ollama"]["reachable"] is True
    assert not (models_config_dir / "models.yml").exists()


def test_status_when_ollama_is_down(models_config_dir):
    with patch.object(routes, "_ollama_models", _fake_models(None)), \
         patch.object(routes, "_detect_hardware_tier", return_value=(1, None)):
        out = asyncio.run(routes.get_model_status())
    assert out["local_ollama"] == {"reachable": False, "url": OLLAMA, "model_count": 0}
    assert out["chat"]["reachable"] is False


def _budget(max_params=14, mem=10.0):
    budget = MagicMock(max_params_b_4bit=max_params, memory_budget_gb=mem)
    budget.to_dict.return_value = {"max_params_b_4bit": max_params}
    detector = MagicMock()
    detector.recommend_budget.return_value = budget
    return detector


def test_apply_recommended_writes_chat_model_and_compression(models_config_dir):
    with patch.object(routes, "_ollama_models", _fake_models([{"name": "big", "size": 1}])), \
         patch.object(routes, "_detect_hardware_tier", return_value=(2, 48.0)), \
         patch("halbert_core.model.hardware_detector.HardwareDetector", return_value=_budget()), \
         patch("halbert_core.model.hardware_detector.pick_installed_model", return_value={"name": "big"}):
        out = asyncio.run(routes.apply_recommended_config())
    assert out["success"] is True and out["applied"]["chat_model"] == "big"
    cfg = store.load()
    assert cfg["chat_model"]["model"] == "big" and cfg["chat_model"]["enabled"] is True
    ep = next(e for e in cfg["saved_endpoints"] if e["id"] == cfg["chat_model"]["endpoint_id"])
    assert ep["url"] == OLLAMA and ep["provider"] == "ollama"
    assert store.load_file()["compression"] == {"backend": "lingua", "enabled": True}


def test_apply_recommended_when_nothing_fits_writes_nothing(models_config_dir):
    with patch.object(routes, "_ollama_models", _fake_models([])), \
         patch.object(routes, "_detect_hardware_tier", return_value=(1, None)), \
         patch("halbert_core.model.hardware_detector.HardwareDetector", return_value=_budget(7, 6.0)), \
         patch("halbert_core.model.hardware_detector.pick_installed_model", return_value=None):
        out = asyncio.run(routes.apply_recommended_config())
    assert out["success"] is False
    assert not (models_config_dir / "models.yml").exists()
