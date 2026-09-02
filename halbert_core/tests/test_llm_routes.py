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
    assert set(data["llm_config"]) == {"saved_endpoints", "chat_model", "specialist_model", "vision_model", "secure_model"}
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


# ── V-01: a fresh install boots usable, without a detour into Settings ──


def _installed(entries, chooses="model-a"):
    """(hardware, library) patchers for the first-run selection behind GET /llm/config."""
    from unittest.mock import MagicMock
    budget = MagicMock(max_params_b_4bit=14, memory_budget_gb=10.0)
    budget.to_dict.return_value = {"max_params_b_4bit": 14}
    detector = MagicMock()
    detector.recommend_budget.return_value = budget
    # These tests exercise the Ollama fresh-install flow, not Apple
    # Intelligence — an unconfigured MagicMock is truthy on every
    # attribute, which used to be harmless because the old (buggy)
    # CAP_SECURE_MODEL gate short-circuited before HardwareDetector was
    # ever instantiated. Now that provisioning is correctly gated on
    # CAP_SECURE_MODEL_ALLOWED (sysadmin-preset True by default), the
    # detector actually runs, so its result must say "not eligible".
    detector.detect.return_value = MagicMock(apple_intelligence_available=False)
    return patch.multiple(
        "halbert_core.model.hardware_detector",
        HardwareDetector=MagicMock(return_value=detector),
        pick_installed_model=MagicMock(return_value={"name": chooses} if chooses else None),
    ), patch("halbert_core.utils.ollama.list_models_raw", return_value=entries)


def test_fresh_install_registers_the_endpoint_but_chooses_no_model(models_config_dir):
    """Registering what is reachable needs no permission; choosing does.

    An earlier version of this test asserted the opposite. Selecting on the
    user's behalf is off by default: a VRAM heuristic cannot say anything
    useful about a hosted model, and the picker exists to give an operator
    control over which model answers.
    """
    hardware, library = _installed([{"name": "model-a", "size": 1}])
    with patch.object(store, "_probe_ollama", return_value=True), hardware, library:
        data = routes.get_llm_config()["data"]
    cfg = data["llm_config"]
    assert cfg["chat_model"]["enabled"] is False
    assert [e["url"] for e in cfg["saved_endpoints"]] == [OLLAMA]


def test_fresh_install_chooses_when_the_operator_opted_in(models_config_dir):
    store.set_top_level(store.AUTO_SELECT_KEY, {"auto_select_model": True})
    hardware, library = _installed([{"name": "model-a", "size": 1}])
    with patch.object(store, "_probe_ollama", return_value=True), hardware, library:
        data = routes.get_llm_config()["data"]
    cfg = data["llm_config"]
    assert cfg["chat_model"]["enabled"] is True
    assert cfg["chat_model"]["model"] == "model-a"
    ep = next(e for e in cfg["saved_endpoints"] if e["id"] == cfg["chat_model"]["endpoint_id"])
    assert ep["url"] == OLLAMA
    # The pill names the effective slot, so the first response must carry it.
    assert data["effective"]["llm_config"]["chat_model"]["model"] == "model-a"


def test_fresh_install_with_nothing_that_fits_still_serves_the_picker(models_config_dir):
    hardware, library = _installed([{"name": "model-a", "size": 1}], chooses=None)
    with patch.object(store, "_probe_ollama", return_value=True), hardware, library:
        cfg = routes.get_llm_config()["data"]["llm_config"]
    assert cfg["chat_model"]["enabled"] is False
    assert [e["url"] for e in cfg["saved_endpoints"]] == [OLLAMA]


def test_second_boot_does_not_reselect(models_config_dir):
    """Only the boot that registers the endpoint may choose; later ones must not."""
    store.save({"saved_endpoints": [{"id": "e1", "name": "Local", "provider": "ollama", "url": OLLAMA}],
                "chat_model": {"enabled": False, "endpoint_id": "", "model": ""}})
    hardware, library = _installed([{"name": "model-a", "size": 1}])
    with patch.object(store, "_probe_ollama", return_value=True), hardware, library:
        cfg = routes.get_llm_config()["data"]["llm_config"]
    assert cfg["chat_model"]["enabled"] is False


@pytest.mark.parametrize("ha", ["home"])
def test_home_variant_skips_apple_provisioning(models_config_dir, monkeypatch, ha,
                                                capability_registry):
    """home never configure secure_model, so the auto-provisioning
    (and the expensive hardware probe behind it) is not run for them.

    F5: provisioning is capability-gated (CAP_SECURE_MODEL); the home
    preset carries no secure_model, which is what this pins."""
    from halbert_core.integrations import cognition_wiring

    monkeypatch.setattr(cognition_wiring, "_get_variant", lambda: ha)
    capability_registry.set_variant(ha)
    with patch.object(store, "_probe_ollama", return_value=False), \
         patch("halbert_core.model.hardware_detector.HardwareDetector") as detector:
        data = routes.get_llm_config()["data"]
    detector.assert_not_called()
    assert data["llm_config"]["secure_model"]["model"] == ""


# ── first-run model selection is opt-in ───────────────────────────────


def _fresh(models_config_dir):
    """An empty config: no endpoints, no chat model."""
    models_config_dir.mkdir(parents=True, exist_ok=True)
    (models_config_dir / "models.yml").write_text("")
    return models_config_dir


def test_a_fresh_install_does_not_choose_a_model(models_config_dir, monkeypatch):
    """Which model answers is the operator's decision.

    A VRAM heuristic cannot say anything useful about a hosted model, and
    picking one silently is the opposite of the control the picker exists to
    give. Quick-setup offers the same suggestion as something to accept.
    """
    from halbert_core.model import llm_config as store
    from halbert_core.dashboard.routes import llm as route

    _fresh(models_config_dir)
    monkeypatch.setattr(store, "_probe_ollama", lambda *a, **k: True)
    chose = []
    from halbert_core.dashboard.routes import settings as settings_routes
    monkeypatch.setattr(settings_routes, "configure_first_run_model",
                        lambda: chose.append(True))

    route.get_llm_config()

    assert chose == []
    assert store.load_global()["chat_model"]["model"] == ""
    # The endpoint is still registered — that part needs no permission.
    assert store.load_global()["saved_endpoints"]


def test_opting_in_lets_the_first_run_choose(models_config_dir, monkeypatch):
    from halbert_core.model import llm_config as store
    from halbert_core.dashboard.routes import llm as route
    from halbert_core.dashboard.routes import settings as settings_routes

    _fresh(models_config_dir)
    store.set_top_level(store.AUTO_SELECT_KEY, {"auto_select_model": True})
    monkeypatch.setattr(store, "_probe_ollama", lambda *a, **k: True)
    chose = []
    monkeypatch.setattr(settings_routes, "configure_first_run_model",
                        lambda: chose.append(True))

    route.get_llm_config()

    assert chose == [True]


def test_auto_select_is_off_when_the_key_is_absent_or_malformed(models_config_dir):
    from halbert_core.model import llm_config as store

    _fresh(models_config_dir)
    assert store.auto_select_enabled() is False
    store.set_top_level(store.AUTO_SELECT_KEY, {"auto_select_model": False})
    assert store.auto_select_enabled() is False
    store.set_top_level(store.AUTO_SELECT_KEY, "not-a-mapping")
    assert store.auto_select_enabled() is False
