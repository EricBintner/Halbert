# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""halbert_core.model.llm_config — the single owner of llm_config in models.yml."""
from pathlib import Path

import pytest
import yaml

from halbert_core.model import llm_config as store

OLLAMA = "http://localhost:11434"

# Shape of a real pre-migration user file: legacy top-level keys populated,
# SourcePrep-shaped llm_config slots all disabled, two diverged endpoint lists.
LEGACY_FILE = {
    "compression": {"backend": "lingua", "enabled": True, "threshold": 4000},
    "llm_config": {
        "advanced": {"enforce_cloud_token_safety": True},
        "assignment_mode": "structured",
        "embedding": {"source": "endpoint"},
        "small_model": {"enabled": False},
        "large_model": {"enabled": False},
        "saved_endpoints": [
            {"id": "ep_new", "name": "Ollama", "provider": "ollama", "url": OLLAMA, "cloud_concurrency": 10},
        ],
    },
    "orchestrator": {"model": "guide-a", "endpoint": OLLAMA, "endpoint_id": "d7f68bda",
                     "provider": "ollama", "always_loaded": True},
    "specialist": {"enabled": True, "model": "", "endpoint": OLLAMA},
    "vision": {"model": "", "endpoint": OLLAMA},
    "saved_endpoints": [
        {"id": "d7f68bda", "name": "Local Ollama", "provider": "ollama", "url": OLLAMA, "api_key": "k1"},
        {"id": "8eb82036", "name": "LM Studio", "provider": "openai", "url": "http://192.168.1.5:1234", "api_key": ""},
    ],
}


def _write(user: Path, data: dict) -> Path:
    p = user / "models.yml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(yaml.safe_dump(data))
    return p


def _read(user: Path) -> dict:
    return yaml.safe_load((user / "models.yml").read_text())


def test_defaults_when_no_file(models_config_dir):
    assert store.load() == store.default_llm_config()
    assert not (models_config_dir / "models.yml").exists()   # load never creates a file


def test_legacy_orchestrator_becomes_chat_model(models_config_dir):
    _write(models_config_dir, LEGACY_FILE)
    cfg = store.load()
    assert cfg["chat_model"]["model"] == "guide-a"
    assert cfg["chat_model"]["enabled"] is True
    ollama = [e for e in cfg["saved_endpoints"] if e["url"] == OLLAMA]
    assert len(ollama) == 1                     # (provider, url) de-dupe
    assert ollama[0]["id"] == "ep_new"          # llm_config entry keeps its id
    assert ollama[0]["api_key"] == "k1"         # empty key back-filled from legacy
    assert cfg["chat_model"]["endpoint_id"] == "ep_new"
    assert len(cfg["saved_endpoints"]) == 2     # LM Studio entry survives


def test_legacy_specialist_without_model_stays_disabled(models_config_dir):
    _write(models_config_dir, LEGACY_FILE)
    cfg = store.load()
    assert cfg["specialist_model"] == {"enabled": False, "endpoint_id": "", "model": ""}
    assert cfg["vision_model"]["enabled"] is False


def test_legacy_specialist_enabled_flag_and_unknown_url(models_config_dir):
    data = dict(LEGACY_FILE)
    data["specialist"] = {"enabled": False, "model": "big-b", "endpoint": OLLAMA}
    data["vision"] = {"model": "eyes-c", "endpoint": "http://gpu-box:11434"}
    _write(models_config_dir, data)
    cfg = store.load()
    assert cfg["specialist_model"]["model"] == "big-b"
    assert cfg["specialist_model"]["enabled"] is False
    vision = cfg["vision_model"]
    assert vision["enabled"] is True and vision["model"] == "eyes-c"
    created = next(e for e in cfg["saved_endpoints"] if e["id"] == vision["endpoint_id"])
    assert created["url"] == "http://gpu-box:11434"
    assert created["name"] == "Migrated endpoint"


def test_migration_rewrites_file_once_with_backup(models_config_dir):
    path = _write(models_config_dir, LEGACY_FILE)
    store.load()
    on_disk = _read(models_config_dir)
    for key in ("orchestrator", "specialist", "vision", "saved_endpoints"):
        assert key not in on_disk
    for key in ("advanced", "embedding", "small_model", "large_model", "assignment_mode"):
        assert key not in on_disk["llm_config"]
    assert on_disk["compression"]["backend"] == "lingua"      # sibling key untouched
    assert (models_config_dir / "models.yml.bak").exists()
    first = path.read_text()
    store.load()                                               # idempotent
    assert path.read_text() == first


def test_small_large_slots_migrate_only_when_in_use(models_config_dir):
    _write(models_config_dir, {"llm_config": {
        "saved_endpoints": [{"id": "e1", "name": "x", "provider": "ollama", "url": OLLAMA}],
        "small_model": {"enabled": True, "endpoint_id": "e1", "model": "fast-a"},
        "large_model": {"enabled": True, "endpoint_id": "e1", "model": "think-b"},
        "code_model": {"enabled": False},
    }})
    cfg = store.load()
    assert cfg["chat_model"]["model"] == "fast-a"
    assert cfg["specialist_model"]["model"] == "think-b"
    assert "small_model" not in _read(models_config_dir)["llm_config"]


def test_slot_with_unknown_endpoint_is_disabled(models_config_dir):
    _write(models_config_dir, {"llm_config": {
        "saved_endpoints": [],
        "chat_model": {"enabled": True, "endpoint_id": "ghost", "model": "m"},
    }})
    assert store.load()["chat_model"]["enabled"] is False


def test_slot_on_non_chat_capable_provider_is_disabled_on_load(models_config_dir):
    _write(models_config_dir, {"llm_config": {
        "saved_endpoints": [{"id": "g1", "name": "Gemini", "provider": "google",
                             "url": "https://generativelanguage.googleapis.com", "api_key": "k"}],
        "chat_model": {"enabled": True, "endpoint_id": "g1", "model": "m"},
    }})
    assert store.load()["chat_model"]["enabled"] is False


def test_update_rejects_non_chat_capable_slot(models_config_dir):
    store.save({"saved_endpoints": [{"id": "g1", "name": "Gemini", "provider": "google",
                                     "url": "https://generativelanguage.googleapis.com", "api_key": "k"}]})
    with pytest.raises(store.SlotProviderError) as exc:
        store.update({"specialist_model": {"enabled": True, "endpoint_id": "g1", "model": "m"}})
    assert exc.value.slot == "specialist_model" and exc.value.provider == "google"
    assert store.load()["specialist_model"]["enabled"] is False


def test_update_merges_and_persists(models_config_dir):
    store.save({"saved_endpoints": [{"id": "e1", "name": "Local", "provider": "ollama", "url": OLLAMA}]})
    store.update({"chat_model": {"enabled": True, "endpoint_id": "e1", "model": "m1"}})
    cfg = store.load()
    assert cfg["chat_model"] == {"enabled": True, "endpoint_id": "e1", "model": "m1"}
    assert cfg["saved_endpoints"][0]["name"] == "Local"


def test_save_strips_legacy_keys_but_keeps_others(models_config_dir):
    _write(models_config_dir, {"orchestrator": {"model": "old"}, "routing": {"complexity_threshold": 3}})
    store.save(store.default_llm_config())
    on_disk = _read(models_config_dir)
    assert "orchestrator" not in on_disk
    assert on_disk["routing"] == {"complexity_threshold": 3}


def test_resolve_and_api_key_for(models_config_dir):
    store.save({
        "saved_endpoints": [{"id": "o1", "name": "OpenAI", "provider": "openai",
                             "url": "https://api.openai.com/v1/", "api_key": "sk-x"}],
        "chat_model": {"enabled": True, "endpoint_id": "o1", "model": "m"},
    })
    assert store.resolve("chat_model") == store.ResolvedModel(
        model="m", url="https://api.openai.com/v1", provider="openai", api_key="sk-x")
    assert store.resolve("vision_model") is None
    assert store.api_key_for("https://api.openai.com/v1") == "sk-x"
    assert store.api_key_for("http://elsewhere") == ""


def test_provider_for_and_resolve_endpoint_by_id(models_config_dir):
    store.save({
        "saved_endpoints": [
            {"id": "o1", "name": "OpenAI", "provider": "openai", "url": "https://api.openai.com/v1", "api_key": "k"},
            {"id": "l1", "name": "Local", "provider": "ollama", "url": OLLAMA},
        ],
    })
    assert store.provider_for("https://api.openai.com/v1") == "openai"
    assert store.provider_for("http://unknown") == "ollama"
    assert store.resolve_endpoint_by_id("o1") == ("https://api.openai.com/v1", "openai", "k")
    assert store.resolve_endpoint_by_id("nope") is None
    assert store.resolve_endpoint_by_id("") is None


def test_ensure_ollama_endpoint_creates_once(models_config_dir):
    first = store.ensure_ollama_endpoint()
    second = store.ensure_ollama_endpoint()
    assert first == second
    eps = store.load()["saved_endpoints"]
    assert len(eps) == 1
    assert eps[0]["name"] == "Local Ollama" and eps[0]["url"] == OLLAMA


def test_ensure_local_ollama_endpoint_probes_only_when_empty(models_config_dir, monkeypatch):
    calls = []
    monkeypatch.setattr(store, "_probe_ollama", lambda url, timeout: calls.append(url) or True)
    assert store.ensure_local_ollama_endpoint() is True
    assert store.ensure_local_ollama_endpoint() is False   # list no longer empty → no probe
    assert calls == [OLLAMA]


def test_set_slot_and_set_top_level(models_config_dir):
    ep_id = store.ensure_ollama_endpoint()
    store.set_slot("chat_model", "m9", ep_id)
    store.set_top_level("compression", {"backend": "semantic", "enabled": True})
    on_disk = _read(models_config_dir)
    assert on_disk["compression"] == {"backend": "semantic", "enabled": True}
    assert on_disk["llm_config"]["chat_model"] == {"enabled": True, "endpoint_id": ep_id, "model": "m9"}


def test_atomic_write_leaves_original_intact_on_failure(models_config_dir, monkeypatch):
    """A crash during write must not truncate the existing file."""
    _write(models_config_dir, {"llm_config": store.default_llm_config()})
    original = (models_config_dir / "models.yml").read_text()

    def boom(data):
        raise OSError("disk full")
    monkeypatch.setattr(store, "_write_raw", boom)
    with pytest.raises(OSError):
        store.save(store.default_llm_config())
    assert (models_config_dir / "models.yml").read_text() == original


def test_file_and_bak_are_mode_0600(models_config_dir):
    _write(models_config_dir, LEGACY_FILE)
    store.load()  # triggers migration → .bak + rewrite
    import os
    cfg_mode = os.stat(models_config_dir / "models.yml").st_mode & 0o777
    bak_mode = os.stat(models_config_dir / "models.yml.bak").st_mode & 0o777
    assert cfg_mode == 0o600
    assert bak_mode == 0o600
