# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
POST /compute/endpoint-probe — the route behind EndpointManager's
"Probe Capacity" button.

The button shipped without a backend: every click returned a 404 that the
component rendered as "Probe failed". These cover the contract the frontend's
``ProbeResult`` type already declared.
"""

import pytest
from unittest.mock import MagicMock, patch

pytest.importorskip("fastapi")

from halbert_core.dashboard.routes import compute


ENDPOINT = {
    "id": "ep-1",
    "name": "OpenAI",
    "provider": "openai",
    "url": "https://api.openai.com/v1",
    "api_key": "sk-test",
}


def _resp(status=200, headers=None):
    r = MagicMock()
    r.status_code = status
    r.headers = headers or {}
    return r


def _probe(body, fire):
    """Run the route with a stubbed per-request timing function."""
    with patch.object(compute.llm_store, "load",
                      return_value={"saved_endpoints": [ENDPOINT]}), \
         patch.object(compute, "_fire", side_effect=fire):
        return compute.endpoint_probe(compute.EndpointProbeRequest(**body))


# -----------------------------------------------------------------------------
# Wave splitting
# -----------------------------------------------------------------------------

class TestWaveSizes:

    def test_waves_double_and_sum_to_the_burst(self):
        assert compute._wave_sizes(20) == [1, 2, 4, 8, 5]
        assert sum(compute._wave_sizes(20)) == 20

    def test_exact_power_of_two(self):
        assert compute._wave_sizes(15) == [1, 2, 4, 8]

    def test_single_request_burst(self):
        assert compute._wave_sizes(1) == [1]


class TestPercentile:

    def test_single_sample(self):
        assert compute._percentile([42.0], 50) == 42.0
        assert compute._percentile([42.0], 99) == 42.0

    def test_nearest_rank(self):
        values = [10.0, 20.0, 30.0, 40.0, 50.0]
        assert compute._percentile(values, 50) == 30.0
        assert compute._percentile(values, 90) == 50.0

    def test_empty(self):
        assert compute._percentile([], 50) == 0.0


# -----------------------------------------------------------------------------
# Saturation detection
# -----------------------------------------------------------------------------

class TestFindSaturation:

    def test_flat_curve_has_no_saturation(self):
        assert compute._find_saturation([(1, 100.0), (2, 105.0), (4, 110.0)]) is None

    def test_knee_is_reported_at_the_wave_that_tipped(self):
        assert compute._find_saturation([(1, 100.0), (2, 120.0), (4, 400.0)]) == 4

    def test_baseline_only_is_inconclusive(self):
        assert compute._find_saturation([(1, 100.0)]) is None

    def test_zero_baseline_is_inconclusive(self):
        # A 0ms baseline would make every later wave "saturated".
        assert compute._find_saturation([(1, 0.0), (2, 50.0)]) is None


# -----------------------------------------------------------------------------
# Route behaviour
# -----------------------------------------------------------------------------

class TestEndpointProbeRoute:

    def test_unknown_endpoint_id_is_an_error_not_a_crash(self):
        with patch.object(compute.llm_store, "load", return_value={"saved_endpoints": []}):
            result = compute.endpoint_probe(
                compute.EndpointProbeRequest(endpoint_id="nope", burst_size=4)
            )
        assert "error" in result
        assert "nope" in result["error"]["message"]

    def test_unsafe_url_is_refused(self):
        bad = dict(ENDPOINT, url="file:///etc/passwd")
        with patch.object(compute.llm_store, "load",
                          return_value={"saved_endpoints": [bad]}):
            result = compute.endpoint_probe(
                compute.EndpointProbeRequest(endpoint_id="ep-1", burst_size=4)
            )
        assert "error" in result

    def test_flat_latency_reports_no_saturation(self):
        result = _probe(
            {"endpoint_id": "ep-1", "burst_size": 7},
            lambda *a: (100.0, True, _resp()),
        )["data"]

        assert result["successes"] == 7
        assert result["errors"] == 0
        assert result["saturation_method"] == "none"
        assert result["saturation_point"] is None
        assert result["recommended_concurrent"] is None
        assert result["wall_clock_ms"]["p50"] == 100.0

    def test_latency_staircase_recommends_the_last_fast_wave(self):
        # Waves for burst 15 are [1, 2, 4, 8]; latency tips over at 4.
        latencies = iter([100.0] + [110.0] * 2 + [500.0] * 4 + [900.0] * 8)

        result = _probe(
            {"endpoint_id": "ep-1", "burst_size": 15},
            lambda *a: (next(latencies), True, _resp()),
        )["data"]

        assert result["saturation_method"] == "latency_staircase"
        assert result["saturation_point"] == 4
        assert result["recommended_concurrent"] == 2

    def test_provider_rate_limit_header_wins_over_the_curve(self):
        latencies = iter([100.0] + [110.0] * 2 + [500.0] * 4 + [900.0] * 8)
        headers = {"x-ratelimit-limit-requests": "12"}

        result = _probe(
            {"endpoint_id": "ep-1", "burst_size": 15},
            lambda *a: (next(latencies), True, _resp(headers=headers)),
        )["data"]

        assert result["saturation_method"] == "header"
        assert result["recommended_concurrent"] == 12

    def test_all_requests_failing_reports_no_recommendation(self):
        """A dead endpoint's latency curve is noise. Recommending a
        concurrency from it would be worse than admitting nothing was learnt.
        """
        result = _probe(
            {"endpoint_id": "ep-1", "burst_size": 7},
            lambda *a: (30.0, False, None),
        )["data"]

        assert result["successes"] == 0
        assert result["errors"] == 7
        assert result["recommended_concurrent"] is None
        assert result["saturation_method"] == "none"

    def test_partial_failures_are_counted_separately(self):
        outcomes = iter([True, False, True, True, False, True, True])
        result = _probe(
            {"endpoint_id": "ep-1", "burst_size": 7},
            lambda *a: (100.0, next(outcomes), _resp()),
        )["data"]
        assert result["successes"] == 5
        assert result["errors"] == 2

    def test_response_matches_the_frontend_ProbeResult_shape(self):
        result = _probe(
            {"endpoint_id": "ep-1", "burst_size": 3},
            lambda *a: (100.0, True, _resp()),
        )["data"]

        assert set(result) == {
            "endpoint_id", "probed_at", "burst_size", "wall_clock_ms",
            "saturation_point", "saturation_method", "recommended_concurrent",
            "successes", "errors", "histogram_path",
        }
        assert set(result["wall_clock_ms"]) == {"p50", "p90", "p99"}
        assert result["saturation_method"] in (
            "latency_staircase", "header", "none"
        )

    def test_burst_size_is_capped(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            compute.EndpointProbeRequest(endpoint_id="ep-1", burst_size=500)


# -----------------------------------------------------------------------------
# Probe targets (free, side-effect-free requests only)
# -----------------------------------------------------------------------------

class TestProbeTarget:

    def test_ollama_uses_tags(self):
        url, headers = compute._probe_target({"provider": "ollama", "url": "http://x:11434"})
        assert url == "http://x:11434/api/tags"
        assert headers == {}

    def test_openai_bearer_auth(self):
        url, headers = compute._probe_target(ENDPOINT)
        assert url == "https://api.openai.com/v1/models"
        assert headers["Authorization"] == "Bearer sk-test"

    def test_anthropic_uses_its_own_auth_headers(self):
        url, headers = compute._probe_target(
            {"provider": "anthropic", "url": "https://api.anthropic.com", "api_key": "k"}
        )
        assert url == "https://api.anthropic.com/v1/models"
        assert headers["x-api-key"] == "k"
        assert "anthropic-version" in headers

    def test_google_puts_the_key_in_the_query(self):
        url, _ = compute._probe_target(
            {"provider": "google", "url": "https://g.test", "api_key": "k"}
        )
        assert url.startswith("https://g.test/v1beta/models?")
        assert "key=k" in url

    def test_no_probe_target_generates_tokens(self):
        """Every provider's probe must be a listing GET — a probe that
        generated would bill the user twenty times per click."""
        for provider in ("ollama", "openai", "anthropic", "google"):
            url, _ = compute._probe_target(
                {"provider": provider, "url": "https://x.test", "api_key": "k"}
            )
            assert "models" in url or "tags" in url
            assert "completion" not in url and "chat" not in url


class TestRouteIsMounted:

    def test_app_serves_the_probe_path(self):
        """The button 404'd because nothing served this path. A 422 on a bad
        body is proof enough that it is routed now."""
        from fastapi.testclient import TestClient
        from halbert_core.dashboard.app import create_app

        client = TestClient(create_app())
        resp = client.post("/compute/endpoint-probe", json={})
        assert resp.status_code != 404
        assert resp.status_code == 422  # missing endpoint_id


# -----------------------------------------------------------------------------
# POST /compute/peer-probe — the Compute Peer card's "Test Connection" button
# (home automation simplification, S3 / W15)
# -----------------------------------------------------------------------------

PEER_URL = "peer://desktop.lan:8000"


def _peer_probe(body, provider_mock, variant_value="home"):
    """Run the route with the variant pinned and PeerProvider stubbed."""
    from halbert_core.dashboard.routes import compute
    from halbert_core.integrations import cognition_wiring

    with patch.object(cognition_wiring, "_get_variant", lambda: variant_value), \
         patch("halbert_core.model.providers.peer.PeerProvider", provider_mock):
        return compute.peer_probe(compute.PeerProbeRequest(**body))


def _stub_provider(healthy=True, models=("m-alpha", "m-beta")):
    from types import SimpleNamespace

    provider = MagicMock()
    provider.health_check.return_value = healthy
    provider.list_models.return_value = [
        SimpleNamespace(model_id=m) for m in models
    ]
    factory = MagicMock(return_value=provider)
    return factory, provider


class TestPeerProbeRoute:

    def test_healthy_peer_reports_the_model_list(self):
        factory, provider = _stub_provider()
        result = _peer_probe({"endpoint": "desktop.lan:8000"}, factory)["data"]

        assert result["ok"] is True
        assert result["models"] == ["m-alpha", "m-beta"]
        assert result["url"] == PEER_URL
        # The probe reuses the provider's health path and its model listing,
        # so the card and TierRouter's health tracking ask the same question.
        provider.health_check.assert_called_once()
        provider.list_models.assert_called_once()

    def test_address_shapes_are_normalised_like_the_link_route(self):
        factory, _ = _stub_provider()
        for address in ("desktop.lan:8000", PEER_URL,
                        "http://desktop.lan:8000/", "https://desktop.lan:8000"):
            factory.reset_mock()
            result = _peer_probe({"endpoint": address}, factory)["data"]
            assert result["url"] == PEER_URL

    def test_dead_peer_reports_failure_with_a_hint_when_no_token(self):
        factory, provider = _stub_provider(healthy=False)
        result = _peer_probe({"endpoint": PEER_URL}, factory)["data"]

        assert result["ok"] is False
        assert result["models"] == []
        assert "did not answer" in result["message"]
        assert "token" in result["message"]
        provider.list_models.assert_not_called()

    def test_sysadmin_variant_is_refused(self):
        factory, _ = _stub_provider()
        result = _peer_probe({"endpoint": PEER_URL}, factory, variant_value="sysadmin")

        assert "error" in result
        assert result["error"]["code"] == "NOT_HOME_VARIANT"
        factory.assert_not_called()

    def test_an_address_without_a_host_is_rejected(self):
        factory, _ = _stub_provider()
        result = _peer_probe({"endpoint": "   "}, factory)

        assert "error" in result
        factory.assert_not_called()

    def test_cloud_metadata_endpoints_are_never_probed(self):
        factory, _ = _stub_provider()
        result = _peer_probe({"endpoint": "169.254.169.254:8000"}, factory)

        assert "error" in result
        factory.assert_not_called()


class TestPeerProbeStoredToken:
    """The probe reuses the credential the link route persisted, so
    "Test Connection" works after pairing without re-entering the token."""

    def test_saved_peer_endpoint_api_key_is_used(self, models_config_dir):
        from halbert_core.dashboard.routes import compute
        from halbert_core.integrations import cognition_wiring
        from halbert_core.model import llm_config as store

        cfg = store.load()
        cfg["saved_endpoints"].append({
            "id": "ep-peer", "name": "Compute Peer", "provider": "peer",
            "url": PEER_URL, "api_key": "tok-1",
        })
        store.save(cfg)

        factory, _ = _stub_provider()
        with patch.object(cognition_wiring, "_get_variant", lambda: "home"), \
             patch("halbert_core.model.providers.peer.PeerProvider", factory):
            compute.peer_probe(compute.PeerProbeRequest(endpoint=PEER_URL))

        factory.assert_called_once_with(PEER_URL, "tok-1")

    def test_saved_credential_is_used_for_the_same_address_only(self, models_config_dir):
        from halbert_core.dashboard.routes import compute
        from halbert_core.integrations import cognition_wiring
        from halbert_core.model import llm_config as store

        cfg = store.load()
        cfg["saved_endpoints"].append({
            "id": "ep-peer", "name": "Compute Peer", "provider": "peer",
            "url": PEER_URL, "api_key": "tok-1",
        })
        store.save(cfg)

        factory, _ = _stub_provider()
        with patch.object(cognition_wiring, "_get_variant", lambda: "home"), \
             patch("halbert_core.model.providers.peer.PeerProvider", factory):
            compute.peer_probe(
                compute.PeerProbeRequest(endpoint="other.lan:8000"))

        factory.assert_called_once_with("peer://other.lan:8000", "")

    def test_an_explicit_token_wins_over_the_stored_one(self, models_config_dir):
        from halbert_core.dashboard.routes import compute
        from halbert_core.integrations import cognition_wiring
        from halbert_core.model import llm_config as store

        cfg = store.load()
        cfg["saved_endpoints"].append({
            "id": "ep-peer", "name": "Compute Peer", "provider": "peer",
            "url": PEER_URL, "api_key": "tok-1",
        })
        store.save(cfg)

        factory, _ = _stub_provider()
        with patch.object(cognition_wiring, "_get_variant", lambda: "home"), \
             patch("halbert_core.model.providers.peer.PeerProvider", factory):
            compute.peer_probe(
                compute.PeerProbeRequest(endpoint=PEER_URL, token="tok-2"))

        factory.assert_called_once_with(PEER_URL, "tok-2")


class TestPeerProbeRouteIsMounted:

    def test_app_serves_the_peer_probe_path(self):
        from fastapi.testclient import TestClient
        from halbert_core.dashboard.app import create_app

        client = TestClient(create_app())
        resp = client.post("/compute/peer-probe", json={})
        assert resp.status_code != 404
        assert resp.status_code == 422  # missing endpoint
