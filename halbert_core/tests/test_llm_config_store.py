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


# ── Unparsable file: readers cope, writers refuse ──────────────────

# Truncated mid-flow-sequence: parses far enough to look like a real config,
# but yaml.safe_load raises, so the store cannot know what the sibling keys are.
BROKEN_YAML = """compression:
  backend: lingua
  enabled: true
routing:
  complexity_threshold: 3
llm_config:
  saved_endpoints: [{id: e1, url: "http://localhost:11434"
"""


def _write_broken(user: Path) -> Path:
    p = user / "models.yml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(BROKEN_YAML)
    return p


def test_unparsable_file_serves_defaults_to_readers(models_config_dir):
    _write_broken(models_config_dir)
    assert store.load() == store.default_llm_config()
    assert store.load_file() == {"llm_config": store.default_llm_config()}
    assert store.resolve("chat_model") is None


def test_unparsable_file_refuses_every_writer_byte_for_byte(models_config_dir):
    path = _write_broken(models_config_dir)
    before = path.read_bytes()

    with pytest.raises(store.ConfigUnreadableError) as exc:
        store.save(store.default_llm_config())
    assert exc.value.path == path
    with pytest.raises(store.ConfigUnreadableError):
        store.update({"chat_model": {"enabled": True, "endpoint_id": "e1", "model": "some-model"}})
    with pytest.raises(store.ConfigUnreadableError):
        store.set_top_level("compression", {"backend": "semantic", "enabled": True})

    assert path.read_bytes() == before
    assert "complexity_threshold: 3" in path.read_text()   # sibling keys still there
    assert not (models_config_dir / "models.yml.bak").exists()


# ── Minted endpoint ids must be persisted ─────────────────────────


def test_endpoint_without_id_gets_a_stable_persisted_id(models_config_dir):
    """An unpersisted id is a fresh id on every read, which disables every slot pointing at it."""
    _write(models_config_dir, {"llm_config": {
        "saved_endpoints": [{"name": "Local Ollama", "provider": "ollama", "url": OLLAMA}],
    }})
    minted = store.load()["saved_endpoints"][0]["id"]
    assert minted
    assert _read(models_config_dir)["llm_config"]["saved_endpoints"][0]["id"] == minted
    assert store.load()["saved_endpoints"][0]["id"] == minted


def test_endpoints_that_already_have_ids_do_not_trigger_a_rewrite(models_config_dir):
    path = _write(models_config_dir, {"llm_config": {
        "saved_endpoints": [{"id": "e1", "name": "Local Ollama", "provider": "ollama", "url": OLLAMA}],
        "chat_model": {"enabled": True, "endpoint_id": "e1", "model": "some-model"},
    }})
    before = path.read_bytes()
    store.load()
    assert path.read_bytes() == before
    assert not (models_config_dir / "models.yml.bak").exists()


# ── Migration must not duplicate an endpoint the user already has ──


def test_legacy_slot_without_endpoint_reuses_the_default_ollama_endpoint(models_config_dir):
    """A legacy slot with no endpoint key still means the default Ollama URL."""
    _write(models_config_dir, {
        "llm_config": {"saved_endpoints": [
            {"id": "e_local", "name": "Local Ollama", "provider": "ollama", "url": OLLAMA + "/"},
        ]},
        "orchestrator": {"model": "some-model", "always_loaded": True},
    })
    cfg = store.load()
    assert len(cfg["saved_endpoints"]) == 1
    assert cfg["saved_endpoints"][0]["id"] == "e_local"
    assert cfg["chat_model"] == {"enabled": True, "endpoint_id": "e_local", "model": "some-model"}
    assert not any(e["name"] == "Migrated endpoint" for e in cfg["saved_endpoints"])


# ── The migrating write is a write too: it takes the backup ────────


def test_set_top_level_backs_up_a_legacy_file_before_rewriting(models_config_dir):
    path = _write(models_config_dir, LEGACY_FILE)
    before = path.read_bytes()
    store.set_top_level("compression", {"backend": "semantic", "enabled": True})
    bak = models_config_dir / "models.yml.bak"
    assert bak.read_bytes() == before
    assert bak.stat().st_mode & 0o777 == 0o600
    assert path.stat().st_mode & 0o777 == 0o600
    on_disk = _read(models_config_dir)
    assert "orchestrator" not in on_disk
    assert on_disk["compression"] == {"backend": "semantic", "enabled": True}
    assert on_disk["llm_config"]["chat_model"]["model"] == "guide-a"


def test_save_backs_up_a_legacy_file_before_rewriting(models_config_dir):
    path = _write(models_config_dir, LEGACY_FILE)
    before = path.read_bytes()
    store.save(store.default_llm_config())
    bak = models_config_dir / "models.yml.bak"
    assert bak.read_bytes() == before
    assert bak.stat().st_mode & 0o777 == 0o600


def test_no_backup_when_the_write_is_not_a_migration(models_config_dir):
    _write(models_config_dir, {"llm_config": store.default_llm_config()})
    store.set_top_level("compression", {"backend": "semantic", "enabled": True})
    assert not (models_config_dir / "models.yml.bak").exists()


# ── api_key carry-forward ─────────────────────────────────────────


def _endpoint_with_key(user: Path) -> Path:
    return _write(user, {
        "llm_config": {
            "saved_endpoints": [{
                "id": "ep1", "name": "Gateway", "provider": "openai-compatible",
                "url": "https://gw.test", "api_key": "secret-key",
            }],
            "chat_model": {"enabled": False, "endpoint_id": "", "model": ""},
        }
    })


def test_update_carries_forward_an_omitted_api_key(models_config_dir):
    """saved_endpoints is a list, so a deep merge replaces it wholesale.

    A client renaming an endpoint it never showed the key for would otherwise
    erase that key, after which auth silently sends an empty bearer token.
    """
    _endpoint_with_key(models_config_dir)
    store.update({"saved_endpoints": [{
        "id": "ep1", "name": "Renamed", "provider": "openai-compatible",
        "url": "https://gw.test",
    }]})
    saved = store.load()["saved_endpoints"][0]
    assert saved["name"] == "Renamed"
    assert saved["api_key"] == "secret-key"


def test_update_clears_the_key_on_an_explicit_empty_string(models_config_dir):
    """Carrying forward must not make a key impossible to remove."""
    _endpoint_with_key(models_config_dir)
    store.update({"saved_endpoints": [{
        "id": "ep1", "name": "Gateway", "provider": "openai-compatible",
        "url": "https://gw.test", "api_key": "",
    }]})
    assert store.load()["saved_endpoints"][0]["api_key"] == ""


def test_update_replaces_the_key_when_a_new_one_is_sent(models_config_dir):
    _endpoint_with_key(models_config_dir)
    store.update({"saved_endpoints": [{
        "id": "ep1", "name": "Gateway", "provider": "openai-compatible",
        "url": "https://gw.test", "api_key": "rotated",
    }]})
    assert store.load()["saved_endpoints"][0]["api_key"] == "rotated"


def test_carry_forward_does_not_invent_a_key_for_a_new_endpoint(models_config_dir):
    _endpoint_with_key(models_config_dir)
    store.update({"saved_endpoints": [
        {"id": "ep1", "name": "Gateway", "provider": "openai-compatible", "url": "https://gw.test"},
        {"id": "ep2", "name": "Local", "provider": "ollama", "url": OLLAMA},
    ]})
    by_id = {e["id"]: e for e in store.load()["saved_endpoints"]}
    assert by_id["ep1"]["api_key"] == "secret-key"
    assert by_id["ep2"]["api_key"] == ""
