# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Layered model configuration: defaults < global < workspace < session."""
import logging
import os
from pathlib import Path

import pytest
import yaml

from halbert_core.model import config_layers as layers
from halbert_core.model import config_locator
from halbert_core.model import llm_config as store
from halbert_core.model.config_locator import ENV_VAR, WORKSPACE_ENV_VAR

OLLAMA = "http://localhost:11434"
GPU_BOX = "http://gpu-box:11434"

LOCAL_EP = {"id": "e_local", "name": "Local", "provider": "ollama", "url": OLLAMA, "api_key": ""}
GPU_EP = {"id": "e_gpu", "name": "GPU box", "provider": "ollama", "url": GPU_BOX, "api_key": ""}

# A fully configured global file: all four slots present, three pinned on the local runtime.
GLOBAL_FILE = {
    "compression": {"backend": "lingua", "enabled": True},
    "llm_config": {
        "saved_endpoints": [LOCAL_EP],
        "chat_model": {"enabled": True, "endpoint_id": "e_local", "model": "chat-a"},
        "specialist_model": {"enabled": True, "endpoint_id": "e_local", "model": "spec-b"},
        "vision_model": {"enabled": True, "endpoint_id": "e_local", "model": "vision-c"},
        "secure_model": {"enabled": False, "endpoint_id": "", "model": ""},
    },
}


@pytest.fixture(autouse=True)
def _no_leaked_layers():
    """No test may inherit another's session pins.

    The workspace declaration is cleared in conftest instead, so every suite
    gets that protection and not only this one.
    """
    layers.reset_sessions()
    yield
    layers.reset_sessions()


def _write(path: Path, data: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data))
    return path


def _global(models_config_dir: Path, data: dict = None) -> Path:
    return _write(models_config_dir / "models.yml", GLOBAL_FILE if data is None else data)


def _workspace(tmp_path: Path, llm: dict, monkeypatch) -> Path:
    path = _write(tmp_path / "workspace" / "models.yml", {"llm_config": llm})
    monkeypatch.setenv(WORKSPACE_ENV_VAR, str(path))
    return path


def _models(cfg: dict) -> dict:
    return {slot: cfg[slot]["model"] for slot in store.SLOTS}


# ── Per-slot precedence ───────────────────────────────────────────


def test_workspace_pinning_one_slot_leaves_its_siblings_alone(models_config_dir, tmp_path, monkeypatch):
    """Whole-file precedence is the obvious implementation and the wrong one."""
    _global(models_config_dir)
    _workspace(tmp_path, {
        "specialist_model": {"enabled": True, "endpoint_id": "e_local", "model": "spec-workspace"},
    }, monkeypatch)
    assert _models(store.load()) == {
        "chat_model": "chat-a",
        "specialist_model": "spec-workspace",
        "vision_model": "vision-c",
        "secure_model": "",
    }


def test_a_layer_with_empty_slots_wipes_nothing(models_config_dir, tmp_path, monkeypatch):
    """A workspace copied from a store-written file carries three empty slots."""
    _global(models_config_dir)
    _workspace(tmp_path, {
        "saved_endpoints": [],
        "chat_model": {"enabled": False, "endpoint_id": "", "model": ""},
        "specialist_model": {"enabled": False, "endpoint_id": "", "model": ""},
        "vision_model": {"enabled": False, "endpoint_id": "", "model": ""},
        "secure_model": {"enabled": False, "endpoint_id": "", "model": ""},
    }, monkeypatch)
    assert _models(store.load()) == {
        "chat_model": "chat-a", "specialist_model": "spec-b", "vision_model": "vision-c",
        "secure_model": "",
    }


def test_session_beats_workspace_beats_global_per_slot(models_config_dir, tmp_path, monkeypatch):
    _global(models_config_dir)
    _workspace(tmp_path, {
        "chat_model": {"enabled": True, "endpoint_id": "e_local", "model": "chat-workspace"},
        "specialist_model": {"enabled": True, "endpoint_id": "e_local", "model": "spec-workspace"},
    }, monkeypatch)
    layers.set_session_slot("s1", "chat_model", "chat-session", "e_local")
    assert _models(store.load("s1")) == {
        "chat_model": "chat-session",
        "specialist_model": "spec-workspace",
        "vision_model": "vision-c",
        "secure_model": "",
    }
    assert _models(store.load()) == {           # another session sees the file layers
        "chat_model": "chat-workspace",
        "specialist_model": "spec-workspace",
        "vision_model": "vision-c",
        "secure_model": "",
    }


def test_a_globally_disabled_slot_stays_disabled_until_a_layer_pins_it(models_config_dir):
    data = {"llm_config": dict(GLOBAL_FILE["llm_config"],
                               specialist_model={"enabled": False, "endpoint_id": "e_local",
                                                 "model": "spec-b"})}
    _global(models_config_dir, data)
    assert store.load()["specialist_model"]["enabled"] is False
    layers.set_session_slot("s1", "specialist_model", "spec-session", "e_local")
    assert store.load("s1")["specialist_model"] == {
        "enabled": True, "endpoint_id": "e_local", "model": "spec-session"}


def test_a_layer_inherits_the_endpoint_of_the_slot_it_overrides(models_config_dir):
    """Pinning a model on the runtime already configured must not need a lookup."""
    _global(models_config_dir)
    layers.set_session_slot("s1", "chat_model", "chat-session")
    assert store.resolve("chat_model", "s1") == store.ResolvedModel(
        model="chat-session", url=OLLAMA, provider="ollama", api_key="")


def test_a_layer_may_bring_its_own_endpoint(models_config_dir, tmp_path, monkeypatch):
    _global(models_config_dir)
    _workspace(tmp_path, {
        "saved_endpoints": [GPU_EP],
        "specialist_model": {"enabled": True, "endpoint_id": "e_gpu", "model": "spec-remote"},
    }, monkeypatch)
    assert store.resolve("specialist_model") == store.ResolvedModel(
        model="spec-remote", url=GPU_BOX, provider="ollama", api_key="")
    assert store.resolve("chat_model").url == OLLAMA
    assert {e["id"] for e in store.load()["saved_endpoints"]} == {"e_local", "e_gpu"}


# ── The workspace layer is opt-in only ────────────────────────────


def test_no_workspace_layer_without_an_explicit_declaration(models_config_dir, tmp_path, monkeypatch):
    """Nothing is discovered by walking a directory, so an undeclared file is inert.

    repo_root() is *Halbert's own* tree, so a discovered project layer would
    scope a user's configuration to Halbert's source rather than to their work.
    """
    _global(models_config_dir)
    cwd = tmp_path / "somewhere" / "a-user-project"
    for candidate in (cwd / ".halbert" / "models.yml",
                      cwd.parent / ".halbert" / "models.yml",
                      config_locator.repo_root() / ".halbert" / "models.yml"):
        _write(candidate, {"llm_config": {
            "chat_model": {"enabled": True, "endpoint_id": "e_local", "model": "chat-discovered"}}})
    monkeypatch.chdir(cwd)
    assert config_locator.workspace_models_config() is None
    assert [l.name for l in config_locator.resolve_layers(include_repo=False)] == ["global"]
    assert store.load()["chat_model"]["model"] == "chat-a"


def test_workspace_declared_by_the_global_file_setting(models_config_dir, tmp_path):
    path = _write(tmp_path / "ws.yml", {"llm_config": {
        "chat_model": {"enabled": True, "endpoint_id": "e_local", "model": "chat-declared"}}})
    _global(models_config_dir, dict(GLOBAL_FILE, workspace_models_config=str(path)))
    assert store.load()["chat_model"]["model"] == "chat-declared"


def test_the_setting_survives_a_write_and_can_be_written_by_the_store(models_config_dir, tmp_path):
    path = _write(tmp_path / "ws.yml", {"llm_config": {
        "vision_model": {"enabled": True, "endpoint_id": "e_local", "model": "vision-declared"}}})
    _global(models_config_dir)
    store.set_top_level("workspace_models_config", str(path))
    store.update({"chat_model": {"enabled": True, "endpoint_id": "e_local", "model": "chat-edited"}})
    on_disk = yaml.safe_load((models_config_dir / "models.yml").read_text())
    assert on_disk["workspace_models_config"] == str(path)
    assert _models(store.load()) == {
        "chat_model": "chat-edited", "specialist_model": "spec-b", "vision_model": "vision-declared",
        "secure_model": ""}


def test_a_declared_workspace_that_does_not_exist_warns_and_is_skipped(models_config_dir, tmp_path,
                                                                      monkeypatch, caplog):
    import logging

    _global(models_config_dir)
    missing = tmp_path / "gone.yml"
    monkeypatch.setenv(WORKSPACE_ENV_VAR, str(missing))
    with caplog.at_level(logging.WARNING, logger=config_locator.logger.name):
        assert store.load()["chat_model"]["model"] == "chat-a"
    assert any(str(missing) in r.getMessage() and r.levelno == logging.WARNING
               for r in caplog.records)


def test_an_unparsable_workspace_falls_back_to_the_global_layer(models_config_dir, tmp_path, monkeypatch):
    """One bad operator file must not take the whole model configuration down."""
    _global(models_config_dir)
    broken = tmp_path / "broken.yml"
    broken.write_text('llm_config:\n  saved_endpoints: [{id: e1, url: "http://x"\n')
    monkeypatch.setenv(WORKSPACE_ENV_VAR, str(broken))
    assert _models(store.load()) == {
        "chat_model": "chat-a", "specialist_model": "spec-b", "vision_model": "vision-c",
        "secure_model": ""}


def test_env_var_wins_over_the_global_file_setting(models_config_dir, tmp_path, monkeypatch):
    from_setting = _write(tmp_path / "setting.yml", {"llm_config": {
        "chat_model": {"enabled": True, "endpoint_id": "e_local", "model": "chat-setting"}}})
    _global(models_config_dir, dict(GLOBAL_FILE, workspace_models_config=str(from_setting)))
    _workspace(tmp_path, {
        "chat_model": {"enabled": True, "endpoint_id": "e_local", "model": "chat-env"}}, monkeypatch)
    assert store.load()["chat_model"]["model"] == "chat-env"


def test_an_overlay_endpoint_without_an_id_is_skipped(models_config_dir, tmp_path, monkeypatch, caplog):
    """No writer touches an overlay, so a minted id would differ on every read."""
    import logging

    _global(models_config_dir)
    _workspace(tmp_path, {
        "saved_endpoints": [{"name": "Anonymous", "provider": "ollama", "url": GPU_BOX}],
        "specialist_model": {"enabled": True, "endpoint_id": "e_local", "model": "spec-workspace"},
    }, monkeypatch)
    with caplog.at_level(logging.WARNING, logger=layers.logger.name):
        cfg = store.load()
    assert [e["id"] for e in cfg["saved_endpoints"]] == ["e_local"]
    assert cfg["specialist_model"]["model"] == "spec-workspace"
    assert any("no id" in r.getMessage() for r in caplog.records)


# ── $HALBERT_MODELS_CONFIG still selects the global layer ─────────


def test_env_models_config_is_still_the_global_layer(models_config_dir, tmp_path, monkeypatch):
    fixture = _write(tmp_path / "fixture.yml", GLOBAL_FILE)
    _write(models_config_dir / "models.yml", {"llm_config": {
        "saved_endpoints": [LOCAL_EP],
        "chat_model": {"enabled": True, "endpoint_id": "e_local", "model": "chat-user"}}})
    monkeypatch.setenv(ENV_VAR, str(fixture))
    assert config_locator.resolve_layers(include_repo=False)[0].path == fixture
    assert store.load()["chat_model"]["model"] == "chat-a"
    layers.set_session_slot("s1", "chat_model", "chat-session", "e_local")
    assert store.load("s1")["chat_model"]["model"] == "chat-session"


def test_env_models_config_is_also_the_write_target(models_config_dir, tmp_path, monkeypatch):
    fixture = _write(tmp_path / "fixture.yml", GLOBAL_FILE)
    monkeypatch.setenv(ENV_VAR, str(fixture))
    store.set_slot("chat_model", "chat-written", "e_local")
    assert yaml.safe_load(fixture.read_text())["llm_config"]["chat_model"]["model"] == "chat-written"
    assert not (models_config_dir / "models.yml").exists()


# ── Writes target the global layer, never a higher one ────────────


def test_a_write_never_persists_a_higher_layer(models_config_dir, tmp_path, monkeypatch):
    """The settings drawer starts from load_global, so an editor cannot copy a
    workspace's pins or endpoints into the user's own file."""
    _global(models_config_dir)
    _workspace(tmp_path, {
        "saved_endpoints": [GPU_EP],
        "specialist_model": {"enabled": True, "endpoint_id": "e_gpu", "model": "spec-workspace"},
    }, monkeypatch)
    layers.set_session_slot("s1", "chat_model", "chat-session", "e_local")
    with layers.bind_session("s1"):
        store.update({"vision_model": {"enabled": True, "endpoint_id": "e_local",
                                       "model": "vision-edited"}})
    on_disk = yaml.safe_load((models_config_dir / "models.yml").read_text())["llm_config"]
    assert [e["id"] for e in on_disk["saved_endpoints"]] == ["e_local"]
    assert on_disk["chat_model"]["model"] == "chat-a"
    assert on_disk["specialist_model"]["model"] == "spec-b"
    assert on_disk["vision_model"]["model"] == "vision-edited"


def test_load_global_ignores_every_layer_above_it(models_config_dir, tmp_path, monkeypatch):
    _global(models_config_dir)
    _workspace(tmp_path, {
        "chat_model": {"enabled": True, "endpoint_id": "e_local", "model": "chat-workspace"}},
        monkeypatch)
    layers.set_session_slot("s1", "vision_model", "vision-session", "e_local")
    with layers.bind_session("s1"):
        assert _models(store.load_global()) == {
            "chat_model": "chat-a", "specialist_model": "spec-b", "vision_model": "vision-c",
            "secure_model": ""}
        assert store.load_global_file()["compression"] == {"backend": "lingua", "enabled": True}


def test_ensure_ollama_endpoint_does_not_adopt_a_workspace_endpoint(models_config_dir, tmp_path,
                                                                    monkeypatch):
    _write(models_config_dir / "models.yml", {"llm_config": {"saved_endpoints": []}})
    _workspace(tmp_path, {"saved_endpoints": [
        {"id": "e_ws", "name": "Workspace Ollama", "provider": "ollama", "url": OLLAMA}]},
        monkeypatch)
    minted = store.ensure_ollama_endpoint(OLLAMA)
    assert minted != "e_ws"
    on_disk = yaml.safe_load((models_config_dir / "models.yml").read_text())["llm_config"]
    assert [e["id"] for e in on_disk["saved_endpoints"]] == [minted]


def test_a_session_pin_never_touches_a_file(models_config_dir):
    path = _global(models_config_dir)
    before = path.read_bytes()
    layers.set_session_slot("s1", "chat_model", "chat-session", "e_local")
    assert store.load("s1")["chat_model"]["model"] == "chat-session"
    assert path.read_bytes() == before
    assert not (models_config_dir / "models.yml.bak").exists()


# ── The bound session ─────────────────────────────────────────────


def test_the_bound_session_is_what_resolution_uses(models_config_dir):
    _global(models_config_dir)
    layers.set_session_slot("s1", "chat_model", "chat-session", "e_local")
    assert store.resolve("chat_model").model == "chat-a"
    with layers.bind_session("s1"):
        assert layers.active_session() == "s1"
        assert store.resolve("chat_model").model == "chat-session"
    assert layers.active_session() is None
    assert store.resolve("chat_model").model == "chat-a"


def test_clearing_a_pin_falls_back_to_the_file_layers(models_config_dir):
    _global(models_config_dir)
    layers.set_session_slot("s1", "chat_model", "chat-session", "e_local")
    layers.set_session_slot("s1", "vision_model", "vision-session", "e_local")
    layers.clear_session_slot("s1", "chat_model")
    assert _models(store.load("s1")) == {
        "chat_model": "chat-a", "specialist_model": "spec-b", "vision_model": "vision-session",
        "secure_model": ""}
    layers.clear_session("s1")
    assert _models(store.load("s1")) == {
        "chat_model": "chat-a", "specialist_model": "spec-b", "vision_model": "vision-c",
        "secure_model": ""}


def test_session_pins_are_bounded(models_config_dir):
    """A long-lived server would otherwise keep an entry per session forever."""
    for i in range(layers.MAX_TRACKED_SESSIONS + 10):
        layers.set_session_slot(f"s{i}", "chat_model", "chat-session", "e_local")
    assert layers.session_layer("s0") == {}
    assert layers.session_layer(f"s{layers.MAX_TRACKED_SESSIONS + 9}")["chat_model"]["model"] == \
        "chat-session"


def test_a_session_pin_needs_a_session_id(models_config_dir):
    with pytest.raises(ValueError):
        layers.set_session_slot("", "chat_model", "chat-session", "e_local")


def test_session_layer_is_a_copy(models_config_dir):
    layers.set_session_slot("s1", "chat_model", "chat-session", "e_local")
    layers.session_layer("s1")["chat_model"]["model"] = "mutated"
    assert layers.session_layer("s1")["chat_model"]["model"] == "chat-session"


# ── The merge, on its own ─────────────────────────────────────────


def test_merge_is_pure_and_ordered_lowest_first():
    merged = layers.merge_layers([
        layers.Layer("global", {"saved_endpoints": [LOCAL_EP],
                                "chat_model": {"enabled": True, "endpoint_id": "e_local",
                                               "model": "chat-a"}}),
        layers.Layer("session", {"chat_model": {"enabled": True, "endpoint_id": "",
                                                "model": "chat-session"}}),
    ], store.SLOTS)
    assert merged["chat_model"] == {"enabled": True, "endpoint_id": "e_local",
                                    "model": "chat-session"}
    assert "specialist_model" not in merged        # undefined stays undefined
    assert merged["saved_endpoints"] == [LOCAL_EP]


def test_higher_layer_wins_a_colliding_endpoint_id():
    merged = layers.merge_layers([
        layers.Layer("global", {"saved_endpoints": [LOCAL_EP]}),
        layers.Layer("workspace", {"saved_endpoints": [dict(LOCAL_EP, url=GPU_BOX,
                                                            name="Redirected")]}),
    ], store.SLOTS)
    assert merged["saved_endpoints"] == [dict(LOCAL_EP, url=GPU_BOX, name="Redirected")]


def test_no_layers_at_all_is_just_the_defaults(models_config_dir):
    assert store.load() == store.default_llm_config()
    assert not (models_config_dir / "models.yml").exists()


async def test_the_bound_session_survives_the_hop_to_a_worker_thread(models_config_dir):
    """Sync route handlers and blocking model calls run in a threadpool, so a
    pin bound in the request would be lost if the binding were thread-local."""
    import asyncio

    _global(models_config_dir)
    layers.set_session_slot("s1", "chat_model", "chat-session", "e_local")
    with layers.bind_session("s1"):
        resolved = await asyncio.to_thread(store.resolve, "chat_model")
    assert resolved.model == "chat-session"


def test_pinning_an_unknown_slot_is_rejected(models_config_dir):
    """The merge only walks the known slots, so a typo would never be applied."""
    with pytest.raises(ValueError, match="chat-model"):
        layers.set_session_slot("s1", "chat-model", "chat-session", "e_local")
    assert layers.session_layer("s1") == {}


def test_the_returned_pin_layer_is_a_copy(models_config_dir):
    returned = layers.set_session_slot("s1", "chat_model", "chat-session", "e_local")
    returned["chat_model"]["model"] = "mutated"
    assert layers.session_layer("s1")["chat_model"]["model"] == "chat-session"


def test_no_suite_inherits_a_workspace_declaration():
    """A developer with $HALBERT_WORKSPACE_MODELS_CONFIG exported would otherwise
    have their own overlay pin models inside every suite that resolves one — this
    test asks for no fixture on purpose, because the conftest guard is autouse."""
    assert os.environ.get(WORKSPACE_ENV_VAR) is None


def test_resolve_layers_defaults_to_the_files_the_store_reads(models_config_dir, tmp_path):
    """The default used to name the repo checkout, which no reader or writer opens."""
    _write(tmp_path / "repo" / "config" / "models.yml", GLOBAL_FILE)
    assert config_locator.resolve_layers() == []
    _global(models_config_dir)
    assert [l.name for l in config_locator.resolve_layers()] == ["global"]


def test_a_session_pin_needs_a_model(models_config_dir):
    """An empty pin was stored, reported back to the caller, and never applied."""
    with pytest.raises(ValueError, match="needs a model"):
        layers.set_session_slot("s1", "chat_model", "", "e_local")
    assert layers.session_layer("s1") == {}


# ── An overlay reaches only the slots it names ────────────────────


def test_an_overlay_redeclaring_an_endpoint_reaches_only_its_own_slots(
    models_config_dir, tmp_path, monkeypatch
):
    """One shared endpoint list let a layer naming one slot redirect the others."""
    _global(models_config_dir)
    _workspace(tmp_path, {
        "saved_endpoints": [dict(LOCAL_EP, url=GPU_BOX, name="Redirected")],
        "specialist_model": {"enabled": True, "endpoint_id": "e_local", "model": "spec-workspace"},
    }, monkeypatch)
    assert store.resolve("chat_model") == store.ResolvedModel(
        model="chat-a", url=OLLAMA, provider="ollama", api_key="")
    assert store.resolve("vision_model") == store.ResolvedModel(
        model="vision-c", url=OLLAMA, provider="ollama", api_key="")
    assert store.resolve("specialist_model") == store.ResolvedModel(
        model="spec-workspace", url=GPU_BOX, provider="ollama", api_key="")


def test_a_scoped_endpoint_keeps_the_same_id_on_every_read(
    models_config_dir, tmp_path, monkeypatch
):
    """Slots are resolved by endpoint id on every read, so an id that changed
    between reads would disable the slot pointing at it — the same trap that
    makes an id-less overlay endpoint unusable."""
    _global(models_config_dir)
    _workspace(tmp_path, {
        "saved_endpoints": [dict(LOCAL_EP, url=GPU_BOX, name="Redirected")],
        "specialist_model": {"enabled": True, "endpoint_id": "e_local", "model": "spec-workspace"},
    }, monkeypatch)
    first, second = store.load(), store.load()
    assert first == second
    assert len(first["saved_endpoints"]) == 2       # the redeclaration, and global's own


def test_nothing_is_scoped_when_no_layer_redeclares_an_endpoint(
    models_config_dir, tmp_path, monkeypatch
):
    _global(models_config_dir)
    _workspace(tmp_path, {
        "specialist_model": {"enabled": True, "endpoint_id": "e_local", "model": "spec-workspace"},
    }, monkeypatch)
    cfg = store.load()
    assert [e["id"] for e in cfg["saved_endpoints"]] == ["e_local"]
    assert cfg["specialist_model"]["endpoint_id"] == "e_local"


def test_an_overlay_with_an_uncallable_provider_darkens_only_its_own_slot(
    models_config_dir, tmp_path, monkeypatch
):
    """Redeclaring an id with a provider chat cannot use took all three slots down."""
    _global(models_config_dir)
    _workspace(tmp_path, {
        "saved_endpoints": [dict(LOCAL_EP, provider="other-provider")],
        "specialist_model": {"enabled": True, "endpoint_id": "e_local", "model": "spec-workspace"},
    }, monkeypatch)
    cfg = store.load()
    assert cfg["chat_model"]["enabled"] is True
    assert cfg["vision_model"]["enabled"] is True
    # The layer that named the endpoint gets what it asked for, and only it.
    assert cfg["specialist_model"]["enabled"] is False


def test_an_overlay_without_an_api_key_keeps_the_stored_one(
    models_config_dir, tmp_path, monkeypatch
):
    """The overlay an operator writes is models.yml with the secret stripped out."""
    cloud = {"id": "e_cloud", "name": "Cloud", "provider": "openai",
             "url": "https://api.example.test", "api_key": "stored-secret"}
    _global(models_config_dir, {"llm_config": {
        "saved_endpoints": [cloud],
        "chat_model": {"enabled": True, "endpoint_id": "e_cloud", "model": "chat-a"},
        "specialist_model": {"enabled": True, "endpoint_id": "e_cloud", "model": "spec-b"},
    }})
    _workspace(tmp_path, {
        "saved_endpoints": [{"id": "e_cloud", "name": "Shared", "provider": "openai",
                             "url": "https://api.example.test"}],
        "specialist_model": {"enabled": True, "endpoint_id": "e_cloud", "model": "spec-workspace"},
    }, monkeypatch)
    assert store.resolve("specialist_model").api_key == "stored-secret"
    assert store.resolve("chat_model").api_key == "stored-secret"


def test_an_overlay_can_still_clear_an_api_key_on_purpose(
    models_config_dir, tmp_path, monkeypatch
):
    """Absent means "I never had it"; empty means "call this one unauthenticated"."""
    cloud = {"id": "e_cloud", "name": "Cloud", "provider": "openai",
             "url": "https://api.example.test", "api_key": "stored-secret"}
    _global(models_config_dir, {"llm_config": {
        "saved_endpoints": [cloud],
        "chat_model": {"enabled": True, "endpoint_id": "e_cloud", "model": "chat-a"},
    }})
    _workspace(tmp_path, {
        "saved_endpoints": [dict(cloud, api_key="")],
        "chat_model": {"enabled": True, "endpoint_id": "e_cloud", "model": "chat-workspace"},
    }, monkeypatch)
    assert store.resolve("chat_model").api_key == ""


def test_an_overlay_slot_with_an_unknown_endpoint_falls_back_to_the_layer_below(
    models_config_dir, tmp_path, monkeypatch, caplog
):
    """A typo in an overlay blinded the slot instead of leaving the global one in charge."""
    _global(models_config_dir)
    _workspace(tmp_path, {
        "chat_model": {"enabled": True, "endpoint_id": "e_typo", "model": "chat-workspace"},
    }, monkeypatch)
    with caplog.at_level(logging.WARNING, logger=layers.logger.name):
        cfg = store.load()
    assert cfg["chat_model"] == {"enabled": True, "endpoint_id": "e_local", "model": "chat-a"}
    assert any("e_typo" in r.getMessage() for r in caplog.records)


def test_an_overlay_in_the_legacy_shape_says_it_was_ignored(
    models_config_dir, tmp_path, monkeypatch, caplog
):
    """Migration rewrites what it reads, so an overlay is never migrated — but
    being skipped in silence is what makes an operator trust a pin that never applied."""
    _global(models_config_dir)
    path = _write(tmp_path / "legacy.yml", {
        "orchestrator": {"model": "chat-legacy"},
        "llm_config": {"small_model": {"enabled": True, "model": "chat-sourceprep"}},
    })
    monkeypatch.setenv(WORKSPACE_ENV_VAR, str(path))
    with caplog.at_level(logging.WARNING, logger=layers.logger.name):
        assert _models(store.load())["chat_model"] == "chat-a"
    said = " ".join(r.getMessage() for r in caplog.records)
    assert "orchestrator" in said and "small_model" in said


# ── The editor edits one layer, never the merged view ─────────────


def _routes():
    from halbert_core.dashboard.routes import llm as llm_routes
    return llm_routes


def _picker_state(models_config_dir, tmp_path, monkeypatch):
    """A global file, a workspace layer bringing its own endpoint, a session pin."""
    _global(models_config_dir)
    _workspace(tmp_path, {
        "saved_endpoints": [GPU_EP],
        "specialist_model": {"enabled": True, "endpoint_id": "e_gpu", "model": "spec-workspace"},
    }, monkeypatch)
    layers.set_session_slot("s1", "chat_model", "chat-session", "e_local")


def test_the_editor_round_trip_cannot_write_a_higher_layer(
    models_config_dir, tmp_path, monkeypatch
):
    """GET served the merged view and PUT took a whole document back, so the
    workspace's endpoint and the session's pin landed in the user's own file the
    first time anyone opened Settings."""
    routes = _routes()
    _picker_state(models_config_dir, tmp_path, monkeypatch)
    with layers.bind_session("s1"):
        served = routes.get_llm_config()["data"]
        routes.update_llm_config(routes.LLMConfigUpdate(llm_config=served["llm_config"]))
    on_disk = yaml.safe_load((models_config_dir / "models.yml").read_text())["llm_config"]
    assert [e["id"] for e in on_disk["saved_endpoints"]] == ["e_local"]
    assert on_disk["chat_model"]["model"] == "chat-a"
    assert on_disk["specialist_model"]["model"] == "spec-b"


def test_the_editor_is_served_the_global_layer_with_the_effective_view_beside_it(
    models_config_dir, tmp_path, monkeypatch
):
    routes = _routes()
    _picker_state(models_config_dir, tmp_path, monkeypatch)
    served = routes.get_llm_config(session_id="s1")["data"]
    assert _models(served["llm_config"]) == {
        "chat_model": "chat-a", "specialist_model": "spec-b", "vision_model": "vision-c",
        "secure_model": ""}
    assert [e["id"] for e in served["llm_config"]["saved_endpoints"]] == ["e_local"]
    assert _models(served["effective"]["llm_config"]) == {
        "chat_model": "chat-session", "specialist_model": "spec-workspace",
        "vision_model": "vision-c", "secure_model": ""}
    assert served["effective"]["overridden_slots"] == {
        "chat_model": "session", "specialist_model": "workspace"}


def test_the_effective_view_has_a_route_of_its_own_and_no_way_to_write_it(
    models_config_dir, tmp_path, monkeypatch
):
    routes = _routes()
    _picker_state(models_config_dir, tmp_path, monkeypatch)
    data = routes.get_effective_llm_config(session_id="s1")["data"]
    assert data["llm_config"]["specialist_model"]["model"] == "spec-workspace"
    assert data["slot_layers"] == {
        "chat_model": "session", "specialist_model": "workspace", "vision_model": "global",
        "secure_model": "global"}
    assert data["layers"] == ["global", "workspace", "session"]
    assert not [r for r in routes.router.routes
                if r.path == "/llm/config/effective" and set(r.methods) - {"GET", "HEAD"}]


def test_a_put_still_edits_the_global_layer_under_a_bound_session(
    models_config_dir, tmp_path, monkeypatch
):
    routes = _routes()
    _picker_state(models_config_dir, tmp_path, monkeypatch)
    with layers.bind_session("s1"):
        body = routes.LLMConfigUpdate(llm_config={
            "vision_model": {"enabled": True, "endpoint_id": "e_local", "model": "vision-edited"}})
        saved = routes.update_llm_config(body)["data"]
    assert _models(saved["llm_config"]) == {
        "chat_model": "chat-a", "specialist_model": "spec-b", "vision_model": "vision-edited",
        "secure_model": ""}
    on_disk = yaml.safe_load((models_config_dir / "models.yml").read_text())["llm_config"]
    assert [e["id"] for e in on_disk["saved_endpoints"]] == ["e_local"]
    assert on_disk["specialist_model"]["model"] == "spec-b"


# ── TierRouter and the app seam resolve the same layers ───────────


def _tier_router():
    from halbert_core.model.tier_router import TierRouter
    return TierRouter()


def test_the_tier_router_resolves_the_layers_not_the_raw_file(
    models_config_dir, tmp_path, monkeypatch
):
    """Parsing models.yml itself let the router pick the global specialist while
    the same request's get_specialist_model() picked the workspace's."""
    _global(models_config_dir)
    _workspace(tmp_path, {
        "specialist_model": {"enabled": True, "endpoint_id": "e_local", "model": "spec-workspace"},
    }, monkeypatch)
    router = _tier_router()
    assert router.config.models["specialist-model"].model_id == "spec-workspace"
    assert router.config.models["guide-model"].model_id == "chat-a"


def test_the_tier_router_re_resolves_when_a_session_binds(models_config_dir):
    _global(models_config_dir)
    router = _tier_router()
    assert router.config.models["guide-model"].model_id == "chat-a"
    layers.set_session_slot("s1", "chat_model", "chat-session", "e_local")
    with layers.bind_session("s1"):
        assert router.refresh() is True
        assert router.config.models["guide-model"].model_id == "chat-session"
        assert router.refresh() is False
    assert router.refresh() is True
    assert router.config.models["guide-model"].model_id == "chat-a"


def test_an_explicit_path_is_still_parsed_as_one_file(models_config_dir, tmp_path, monkeypatch):
    """A caller that names a file means that file — not the store's layers."""
    from halbert_core.model.tier_router import TierRouter

    _global(models_config_dir)
    _workspace(tmp_path, {
        "chat_model": {"enabled": True, "endpoint_id": "e_local", "model": "chat-workspace"},
    }, monkeypatch)
    other = _write(tmp_path / "other.yml", {"llm_config": {
        "saved_endpoints": [LOCAL_EP],
        "chat_model": {"enabled": True, "endpoint_id": "e_local", "model": "chat-elsewhere"}}})
    assert TierRouter(other).config.models["guide-model"].model_id == "chat-elsewhere"


def test_the_seam_lets_its_cached_router_re_resolve(models_config_dir):
    """The router is built once per process; the session layer changes per turn."""
    from halbert_core.integrations.app_seam import HalbertModelBackend

    _global(models_config_dir)

    class _Router:
        def __init__(self):
            self.refreshed = 0
            self.config = type("Cfg", (), {"models": {"guide-model": object()}})()

        def refresh(self) -> bool:
            self.refreshed += 1
            return False

    backend = HalbertModelBackend()
    backend._tier_router = _Router()
    assert backend._get_tier_router() is backend._tier_router
    assert backend._get_tier_router().refreshed == 2


def test_with_no_layer_above_it_the_two_views_are_the_same_document(models_config_dir):
    """What the picker is served today does not change: only a declared
    workspace file or a session pin can make the editable and effective views
    differ, and the response still carries the editable one under llm_config.

    R05-F3: both views redact each endpoint's api_key (never "" here since
    LOCAL_EP already carries none) and add key_set, so the comparison to
    the stored document strips that one field back out first."""
    routes = _routes()
    _global(models_config_dir)
    served = routes.get_llm_config()["data"]
    assert served["llm_config"] == served["effective"]["llm_config"]
    for ep in served["llm_config"]["saved_endpoints"]:
        assert ep.pop("key_set") is False
    assert served["llm_config"] == store.load()
    assert served["effective"]["overridden_slots"] == {}
