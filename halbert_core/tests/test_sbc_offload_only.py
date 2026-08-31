# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""SBC_LOW_POWER is offload-only: no local model, wizard peer prompt.

Handoff HOME-AUTOMATION-SIMPLIFICATION-2026-08-30, S4 (W17/W19): devices
with <4GB RAM drop the emergent ~1B local tier entirely. The size budget
is zeroed with an explicit offload-only note, nothing installed can be
picked against it, the installation guidance points at a compute peer
instead of a model pull, and the wizard never lists local models on
these devices — it prompts for a peer address and writes the endpoint.

The >=4GB classification boundary itself is NOT this change's to move
(decision D2): a 4GB host still classifies ENTRY_8GB and keeps its
local-model budget, so these tests pin that too.
"""
from unittest.mock import MagicMock

import pytest

from halbert_core.model import llm_config as store
from halbert_core.model.config_wizard import ConfigWizard
from halbert_core.model.hardware_detector import (
    HardwareDetector, HardwareCapabilities, HardwareProfile,
    GB_PER_BILLION_PARAMS_4BIT, SYSTEM_RAM_FRACTION, pick_installed_model,
)

OLLAMA = "http://localhost:11434"


def _hardware(profile: HardwareProfile, ram_gb: int) -> HardwareCapabilities:
    """A plain Linux host of the given shape, already classified."""
    return HardwareCapabilities(
        total_ram_gb=ram_gb,
        available_ram_gb=float(ram_gb),
        cpu_count=4,
        platform="linux",
        platform_friendly="Linux",
        profile=profile,
    )


def _sbc() -> HardwareCapabilities:
    return _hardware(HardwareProfile.SBC_LOW_POWER, 2)


def _wizard() -> ConfigWizard:
    return ConfigWizard.__new__(ConfigWizard)   # skip hardware detection in __init__


# ── Budget clamp ────────────────────────────────────────────────────────


def test_sbc_budget_is_offload_only():
    budget = HardwareDetector().recommend_budget(_sbc())
    assert budget.offload_only is True
    assert budget.max_params_b_4bit == 0
    assert budget.max_params_b_8bit == 0
    assert budget.memory_budget_gb == 0.0
    assert "offload only" in budget.summary
    assert "a compute peer is required" in " ".join(budget.notes)
    assert budget.to_dict()["offload_only"] is True


def test_sbc_budget_fits_nothing():
    """The zeroed budget admits no parameter count and no weight file."""
    budget = HardwareDetector().recommend_budget(_sbc())
    assert budget.fits(0.5) is False
    assert budget.fits_bytes(int(0.7 * 1024 ** 3)) is False


def test_entry_8gb_budget_is_unchanged():
    """D2: 4GB+ hosts keep the generic arithmetic — no offload clamp here."""
    budget = HardwareDetector().recommend_budget(_hardware(HardwareProfile.ENTRY_8GB, 8))
    assert budget.offload_only is False
    assert budget.memory_budget_gb == 8 * SYSTEM_RAM_FRACTION
    assert budget.max_params_b_4bit == int(8 * SYSTEM_RAM_FRACTION / GB_PER_BILLION_PARAMS_4BIT)


def test_classification_boundary_unchanged():
    """D2: strictly <4GB is SBC_LOW_POWER; 4GB itself is ENTRY_8GB."""
    detector = HardwareDetector()
    assert detector._classify_hardware(_hardware(HardwareProfile.UNKNOWN, 4)) is HardwareProfile.ENTRY_8GB
    assert detector._classify_hardware(_hardware(HardwareProfile.UNKNOWN, 2)) is HardwareProfile.SBC_LOW_POWER


# ── Installation guidance ────────────────────────────────────────────────


def test_installation_commands_point_at_a_peer_not_a_pull():
    budget = HardwareDetector().recommend_budget(_sbc())
    commands = HardwareDetector().get_installation_commands(budget)
    assert "ollama" not in commands
    guidance = "\n".join(commands["peer"])
    assert "ollama pull" not in guidance
    assert "--peer <hostname:port>" in guidance


def test_installation_commands_still_pull_for_capable_hosts():
    budget = HardwareDetector().recommend_budget(_hardware(HardwareProfile.ENTRY_8GB, 8))
    commands = HardwareDetector().get_installation_commands(budget)
    assert "ollama pull <model>" in commands["ollama"]


# ── Nothing installed can be picked against a zeroed budget ──────────────


def _installed_models():
    """Ollama /api/tags-shaped entries, including one that once 'fit' the
    emergent ~1B budget on a 2GB host."""
    return [
        {"name": "tiny-chat", "size": int(0.7 * 1024 ** 3)},          # ~1B at 4-bit
        {"name": "mid-chat", "size": int(2.4 * 1024 ** 3)},
        {"name": "embed-small", "size": int(0.1 * 1024 ** 3)},        # skipped anyway
        {"name": "sized-unknown", "details": {"parameter_size": "1B"}},
    ]


def test_pick_installed_model_selects_nothing_on_offload_budget():
    budget = HardwareDetector().recommend_budget(_sbc())
    assert pick_installed_model(_installed_models(), budget) is None


def test_wizard_find_installed_model_selects_nothing(monkeypatch):
    monkeypatch.setattr(
        "halbert_core.model.config_wizard.list_models_raw",
        lambda endpoint: _installed_models(),
    )
    budget = HardwareDetector().recommend_budget(_sbc())
    assert _wizard().find_installed_model(budget, OLLAMA) is None


# ── Wizard: run_auto on SBC ──────────────────────────────────────────────


def _sbc_wizard(monkeypatch) -> ConfigWizard:
    """A wizard whose hardware probe reports a 2GB SBC."""
    wizard = _wizard()
    monkeypatch.setattr(wizard, "detect_hardware", lambda: _sbc())
    monkeypatch.setattr(wizard, "get_budget",
                        lambda hw: HardwareDetector().recommend_budget(hw))
    return wizard


def test_run_auto_on_sbc_skips_the_installed_model_lookup(monkeypatch):
    wizard = _sbc_wizard(monkeypatch)
    find_installed_model = MagicMock()
    monkeypatch.setattr(wizard, "find_installed_model", find_installed_model)

    config = wizard.run_auto(peer="desktop.lan:8000")

    find_installed_model.assert_not_called()
    llm = config["llm_config"]
    assert llm["chat_model"] == {"enabled": False, "endpoint_id": "", "model": ""}
    assert [ep["url"] for ep in llm["saved_endpoints"]] == ["peer://desktop.lan:8000"]
    assert llm["saved_endpoints"][0]["provider"] == "peer"


def test_run_auto_on_sbc_without_a_peer_writes_no_endpoints(monkeypatch):
    wizard = _sbc_wizard(monkeypatch)
    config = wizard.run_auto()
    assert config["llm_config"]["saved_endpoints"] == []


def test_run_auto_on_sbc_normalises_a_bare_host_port(monkeypatch):
    """--peer accepts bare hostname:port and http:// forms alike."""
    wizard = _sbc_wizard(monkeypatch)
    config = wizard.run_auto(peer="http://desktop.lan:8000")
    urls = [ep["url"] for ep in config["llm_config"]["saved_endpoints"]]
    assert urls == ["peer://desktop.lan:8000"]


def test_run_auto_on_sbc_ignores_a_malformed_peer(monkeypatch):
    """A bad --peer value is dropped with a warning, never a hard error."""
    wizard = _sbc_wizard(monkeypatch)
    config = wizard.run_auto(peer="not a host:80000")
    assert config["llm_config"]["saved_endpoints"] == []


# ── Wizard: _build_config peer endpoint shape ────────────────────────────


def _budget_mock():
    budget = MagicMock()
    budget.to_dict.return_value = {"max_params_b_4bit": 0, "offload_only": True}
    return budget


def test_build_config_writes_the_peer_endpoint_shape():
    cfg = _wizard()._build_config(
        None, "ollama", _budget_mock(), _sbc(),
        endpoint=OLLAMA, peer_url="peer://desktop.lan:8000",
    )
    assert cfg["llm_config"]["saved_endpoints"] == [{
        "id": "ep_compute_peer",
        "name": "Compute Peer",
        "provider": "peer",
        "url": "peer://desktop.lan:8000",
        "api_key": "",
    }]
    assert cfg["llm_config"]["chat_model"]["model"] == ""


def test_build_config_without_a_peer_writes_no_peer_endpoint():
    cfg = _wizard()._build_config(None, "ollama", _budget_mock(), _sbc(), endpoint=OLLAMA)
    assert cfg["llm_config"]["saved_endpoints"] == []


def test_save_config_round_trips_the_peer_endpoint(variant, models_config_dir):
    """The store mints the endpoint id; the peer:// URL and provider survive."""
    variant["variant"] = "home-light"
    wizard = _wizard()
    wizard.save_config(wizard._build_config(
        None, "ollama", _budget_mock(), _sbc(),
        endpoint=OLLAMA, peer_url="peer://desktop.lan:8000",
    ))

    endpoints = store.load()["saved_endpoints"]
    assert [(e["provider"], e["url"]) for e in endpoints] == [("peer", "peer://desktop.lan:8000")]
    assert store.load()["chat_model"]["model"] == ""


# ── Wizard: interactive SBC flow ─────────────────────────────────────────


@pytest.fixture
def variant(monkeypatch):
    """Controllable variant, patched where the wizard resolves it."""
    from halbert_core.integrations import cognition_wiring
    holder = {"variant": "sysadmin"}
    monkeypatch.setattr(cognition_wiring, "_get_variant", lambda: holder["variant"])
    return holder


def test_run_interactive_on_sbc_prompts_for_a_peer_not_a_model(monkeypatch, variant):
    wizard = _sbc_wizard(monkeypatch)

    inputs = iter(["desktop.lan:9000", "n", "y"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))

    listed = MagicMock()
    monkeypatch.setattr("halbert_core.model.config_wizard.list_models_raw", listed)

    config = wizard.run_interactive()

    listed.assert_not_called()      # no local-model listing on an SBC
    llm = config["llm_config"]
    assert [ep["url"] for ep in llm["saved_endpoints"]] == ["peer://desktop.lan:9000"]
    assert llm["chat_model"]["model"] == ""


def test_run_interactive_on_sbc_uses_the_flag_default_when_left_blank(monkeypatch, variant):
    wizard = _sbc_wizard(monkeypatch)

    inputs = iter(["", "n", "y"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))

    config = wizard.run_interactive(peer="desktop.lan:8000")

    assert [ep["url"] for ep in config["llm_config"]["saved_endpoints"]] == ["peer://desktop.lan:8000"]


def test_run_interactive_on_sbc_without_any_peer_writes_nothing(monkeypatch, variant):
    wizard = _sbc_wizard(monkeypatch)

    # A blank address cancels the peer prompt (no test prompt follows),
    # then the configuration is accepted with nothing configured.
    inputs = iter(["", "y"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))

    config = wizard.run_interactive()

    assert config["llm_config"]["saved_endpoints"] == []


def test_run_interactive_offers_local_models_on_capable_hosts(monkeypatch, variant):
    """The SBC gate must not leak: a 16GB host still gets the model prompt."""
    hardware = _hardware(HardwareProfile.LAPTOP_16GB, 16)
    wizard = _wizard()
    monkeypatch.setattr(wizard, "detect_hardware", lambda: hardware)
    monkeypatch.setattr(wizard, "get_budget",
                        lambda hw: HardwareDetector().recommend_budget(hw))
    monkeypatch.setattr("halbert_core.model.config_wizard.list_models_raw",
                        lambda endpoint: [{"name": "chat-a", "size": int(4 * 1024 ** 3)}])

    inputs = iter(["chat-a", "y"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))

    config = wizard.run_interactive()

    assert config["llm_config"]["chat_model"]["model"] == "chat-a"


# ── Peer address normalisation ───────────────────────────────────────────


@pytest.mark.parametrize("raw,expected", [
    ("desktop.lan:8000", "peer://desktop.lan:8000"),
    ("desktop.lan", "peer://desktop.lan:8000"),                    # default port
    ("http://desktop.lan:8000", "peer://desktop.lan:8000"),
    ("https://desktop.lan:8000/", "peer://desktop.lan:8000"),
    ("peer://100.64.1.10:8000", "peer://100.64.1.10:8000"),         # Tailscale IP
    ("mac-studio.tailnet.ts.net:8000", "peer://mac-studio.tailnet.ts.net:8000"),
])
def test_normalise_peer_url_accepts_host_and_scheme_forms(raw, expected):
    assert ConfigWizard._normalise_peer_url(raw) == (expected, None)


@pytest.mark.parametrize("raw", [
    "desktop lan:8000",       # space in the host
    "desktop.lan:99999",      # port out of range shape
    "://only-scheme",
    "",
])
def test_normalise_peer_url_rejects_malformed_addresses(raw):
    assert ConfigWizard._normalise_peer_url(raw)[0] is None


def test_test_compute_peer_reports_an_unreachable_peer(monkeypatch):
    import requests

    def _boom(url, timeout=None):
        raise requests.ConnectionError("no route to host")

    monkeypatch.setattr(requests, "get", _boom)
    ok, detail = ConfigWizard._test_compute_peer("peer://desktop.lan:8000")
    assert ok is False
    assert detail


def test_test_compute_peer_probes_the_health_route(monkeypatch):
    import requests

    seen = {}

    class _Resp:
        status_code = 200

    def _fake_get(url, timeout=None):
        seen["url"] = url
        return _Resp()

    monkeypatch.setattr(requests, "get", _fake_get)
    ok, detail = ConfigWizard._test_compute_peer("peer://desktop.lan:8000")
    assert ok is True
    assert seen["url"] == "http://desktop.lan:8000/api/compute/v1/health"


# ── Hardware payload carried through ──────────────────────────────────────


def test_config_records_the_offload_only_budget():
    cfg = _wizard()._build_config(
        None, "ollama", HardwareDetector().recommend_budget(_sbc()), _sbc(),
        endpoint=OLLAMA,
    )
    assert cfg["hardware"]["model_budget"]["offload_only"] is True