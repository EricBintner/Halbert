# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Test: pairing persists the compute peer into the model slots (S3 / W16).

Home automation simplification (handoff
HOME-AUTOMATION-SIMPLIFICATION-2026-08-30, 5.2/W16): an HA node has no
model picker. When it pairs with a workstation, ONE ``peer://`` endpoint
is saved and BOTH ``chat_model`` and ``specialist_model`` point at it —
the same endpoint, the same model list — with the workstation's own model
configuration governing which model serves the requests. Home/home-light
variants only; the sysadmin variant keeps the per-slot picker.
"""
import asyncio

import pytest

pytest.importorskip("fastapi")

from fastapi import HTTPException

from halbert_core.dashboard.routes import peers as routes
from halbert_core.integrations import cognition_wiring
from halbert_core.model import llm_config as store
from halbert_core.model.providers.peer import PEER_GOVERNED_MODEL

PEER_URL = "peer://desktop.lan:8000"


def _link(address=PEER_URL, token="tok-1", model="", name=""):
    req = routes.ComputePeerLinkRequest(
        endpoint=address, token=token, model=model, name=name,
    )
    return asyncio.run(routes.link_compute_peer(req))


@pytest.fixture
def variant(monkeypatch):
    """Pin the active variant; None leaves the real resolution in place."""
    def _set(value):
        if value is not None:
            monkeypatch.setattr(cognition_wiring, "_get_variant", lambda: value)
        return value
    return _set


# ---------------------------------------------------------------------------
# Persistence — both slots resolve to the one peer endpoint
# ---------------------------------------------------------------------------

class TestLinkPersistsSlots:

    @pytest.mark.parametrize("ha", ["home", "home-light"])
    def test_pairing_points_both_slots_at_the_peer(self, models_config_dir, variant, ha):
        variant(ha)
        out = _link()
        assert out.url == PEER_URL
        assert out.model == PEER_GOVERNED_MODEL

        cfg = store.load()
        # One saved endpoint, provider peer, carrying the bearer token
        endpoint = next(e for e in cfg["saved_endpoints"] if e["url"] == PEER_URL)
        assert endpoint["provider"] == "peer"
        assert endpoint["api_key"] == "tok-1"
        # chat_model and specialist_model: the same endpoint, the same model
        for slot in ("chat_model", "specialist_model"):
            assert cfg[slot]["enabled"] is True
            assert cfg[slot]["endpoint_id"] == endpoint["id"]
            assert cfg[slot]["model"] == PEER_GOVERNED_MODEL
        # secure_model is never touched (S1: HA variants leave it empty)
        assert cfg["secure_model"] == {"enabled": False, "endpoint_id": "", "model": ""}

    def test_explicit_model_tag_is_honoured(self, models_config_dir, variant):
        variant("home")
        out = _link(model="m-a")
        assert out.model == "m-a"
        assert store.load()["chat_model"]["model"] == "m-a"

    def test_repairing_refreshes_the_stored_token(self, models_config_dir, variant):
        variant("home")
        _link(token="tok-1")
        _link(token="tok-2")
        endpoint = next(e for e in store.load()["saved_endpoints"] if e["url"] == PEER_URL)
        assert endpoint["api_key"] == "tok-2"

    def test_an_omitted_token_never_clears_a_stored_one(self, models_config_dir, variant):
        variant("home")
        _link(token="tok-1")
        _link(token="")
        endpoint = next(e for e in store.load()["saved_endpoints"] if e["url"] == PEER_URL)
        assert endpoint["api_key"] == "tok-1"

    def test_linking_is_idempotent(self, models_config_dir, variant):
        variant("home")
        first = _link()
        second = _link()
        assert first.endpoint_id == second.endpoint_id
        assert len(store.load()["saved_endpoints"]) == 1


# ---------------------------------------------------------------------------
# Variant gate — HA variants only
# ---------------------------------------------------------------------------

class TestVariantGate:

    def test_sysadmin_variant_is_rejected(self, models_config_dir, variant):
        variant("sysadmin")
        with pytest.raises(HTTPException) as exc:
            _link()
        assert exc.value.status_code == 403
        # Nothing was persisted
        assert store.load()["saved_endpoints"] == []
        assert store.load()["chat_model"]["enabled"] is False

    @pytest.mark.parametrize("ha", ["home", "home-light"])
    def test_real_resolution_agrees_for_ha_variants(self, models_config_dir,
                                                    monkeypatch, ha):
        """The gate uses cognition_wiring's variant resolution (being.yml >
        env > sysadmin), same as every other HA gating site."""
        from halbert_core.config import being_config
        monkeypatch.setattr(being_config, "explicit_variant", lambda: "")
        monkeypatch.setenv("HALBERT_VARIANT", ha)
        out = _link()
        assert out.status == "linked"


# ---------------------------------------------------------------------------
# Address normalisation
# ---------------------------------------------------------------------------

class TestPeerUrl:

    def test_bare_host_port(self):
        assert routes._peer_url("desktop.lan:8000") == PEER_URL

    def test_http_url(self):
        assert routes._peer_url("http://desktop.lan:8000/") == PEER_URL

    def test_https_url(self):
        assert routes._peer_url("https://desktop.lan:8000") == PEER_URL

    def test_peer_scheme_passthrough(self):
        assert routes._peer_url(PEER_URL) == PEER_URL

    def test_tailscale_hostname(self):
        assert routes._peer_url("n150.tailnet.ts.net:8000") == "peer://n150.tailnet.ts.net:8000"

    def test_empty_address_is_rejected(self, models_config_dir, variant):
        variant("home")
        with pytest.raises(HTTPException) as exc:
            _link(address="   ")
        assert exc.value.status_code == 400