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


# ── First run: V-01, a fresh install is usable without visiting Settings ──


def _first_run(entries, chooses="model-a"):
    """(hardware, library) patchers: a stubbed budget and a stubbed engine library."""
    return patch.multiple(
        "halbert_core.model.hardware_detector",
        HardwareDetector=MagicMock(return_value=_budget()),
        pick_installed_model=MagicMock(return_value={"name": chooses} if chooses else None),
    ), patch("halbert_core.utils.ollama.list_models_raw", return_value=entries)


def test_first_run_picks_a_model_that_fits_the_hardware(models_config_dir):
    hardware, library = _first_run([{"name": "model-a", "size": 1}])
    with hardware, library, patch.object(routes, "_detect_hardware_tier", return_value=(3, None)):
        assert routes.configure_first_run_model() == "model-a"
    cfg = store.load()
    assert cfg["chat_model"]["model"] == "model-a" and cfg["chat_model"]["enabled"] is True
    ep = next(e for e in cfg["saved_endpoints"] if e["id"] == cfg["chat_model"]["endpoint_id"])
    assert ep["url"] == OLLAMA and ep["provider"] == "ollama"
    assert store.load_file()["compression"] == {"backend": "lingua", "enabled": True}


def test_first_run_matches_what_the_quick_setup_button_would_apply(models_config_dir):
    """The button and the first run must never disagree about what fits."""
    hardware, library = _first_run([{"name": "model-a", "size": 1}])
    with hardware, library, patch.object(routes, "_detect_hardware_tier", return_value=(1, None)):
        routes.configure_first_run_model()
        auto = store.load_file()
    (models_config_dir / "models.yml").unlink()
    with hardware, patch.object(routes, "_ollama_models", _fake_models([{"name": "model-a", "size": 1}])), \
         patch.object(routes, "_detect_hardware_tier", return_value=(1, None)):
        asyncio.run(routes.apply_recommended_config())
    button = store.load_file()
    assert auto["llm_config"]["chat_model"]["model"] == button["llm_config"]["chat_model"]["model"]
    assert auto["compression"] == button["compression"]


def test_first_run_never_overwrites_an_existing_choice(models_config_dir):
    store.save({
        "saved_endpoints": [{"id": "e1", "name": "Local", "provider": "ollama", "url": OLLAMA}],
        "chat_model": {"enabled": True, "endpoint_id": "e1", "model": "mine"},
    })
    before = (models_config_dir / "models.yml").read_text()
    hardware, library = _first_run([{"name": "model-a", "size": 1}])
    with hardware, library, patch.object(routes, "_detect_hardware_tier", return_value=(3, None)):
        assert routes.configure_first_run_model() is None
    assert (models_config_dir / "models.yml").read_text() == before


def test_first_run_leaves_a_deliberately_cleared_slot_alone(models_config_dir):
    """Clearing the slot is a choice; the next boot must not undo it."""
    store.save({
        "saved_endpoints": [{"id": "e1", "name": "Local", "provider": "ollama", "url": OLLAMA}],
        "chat_model": {"enabled": False, "endpoint_id": "", "model": ""},
    })
    assert store.ensure_local_ollama_endpoint() is False   # endpoints exist → not a fresh install


def test_first_run_when_nothing_installed_fits_writes_nothing(models_config_dir):
    hardware, library = _first_run([{"name": "model-a", "size": 1}], chooses=None)
    with hardware, library, patch.object(routes, "_detect_hardware_tier", return_value=(1, None)):
        assert routes.configure_first_run_model() is None
    assert not (models_config_dir / "models.yml").exists()


def test_first_run_when_the_engine_has_no_models_writes_nothing(models_config_dir):
    hardware, library = _first_run([], chooses=None)
    with hardware, library, patch.object(routes, "_detect_hardware_tier", return_value=(1, None)):
        assert routes.configure_first_run_model() is None
    assert not (models_config_dir / "models.yml").exists()


def test_first_run_does_not_break_boot_when_detection_fails(models_config_dir):
    with patch("halbert_core.model.hardware_detector.HardwareDetector", side_effect=OSError("no /proc")), \
         patch("halbert_core.utils.ollama.list_models_raw", return_value=[{"name": "model-a"}]), \
         patch.object(routes, "_detect_hardware_tier", return_value=(1, None)):
        assert routes.configure_first_run_model() is None
    assert not (models_config_dir / "models.yml").exists()
