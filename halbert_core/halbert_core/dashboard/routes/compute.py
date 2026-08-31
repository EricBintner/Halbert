# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Compute capacity probing.

Backs the "Probe Capacity" button in EndpointManager, which fires a burst of
parallel requests at a saved endpoint and reports where latency starts to
climb — an empirical alternative to guessing a provider's concurrency cap
from its published plan tier.

Endpoints:
  - POST /compute/endpoint-probe  — probe a saved endpoint, recommend a cap
  - POST /compute/peer-probe     — test a workstation's compute endpoint

The probe deliberately calls the provider's *model listing* endpoint rather
than generating anything. It costs no tokens, cannot be charged for, and has
no side effects, which is what makes it safe to fire twenty of at once
against someone's paid endpoint. The trade-off is that it measures request
handling and rate limiting, not inference throughput; when the provider
publishes rate-limit headers those are preferred over the latency curve.
"""

from __future__ import annotations

import logging
import math
import statistics
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Tuple

import requests
from fastapi import APIRouter
from pydantic import BaseModel, Field

from .llm import is_safe_url
from ...model import llm_config as llm_store

logger = logging.getLogger("halbert.dashboard.routes.compute")

router = APIRouter(tags=["compute"])

# Per-request ceiling. A probe is meant to be quick and free; anything slower
# than this is a dead endpoint, not a slow one.
PROBE_TIMEOUT = 15

# Wave concurrency doubles until the burst is spent: 1, 2, 4, 8, …
# The single-request wave is the baseline every later wave is compared to.
SATURATION_FACTOR = 2.0

# Rate-limit headers, most-specific first. Providers disagree on spelling.
_RATE_LIMIT_HEADERS = (
    "x-ratelimit-limit-requests",
    "x-ratelimit-limit",
    "ratelimit-limit",
    "anthropic-ratelimit-requests-limit",
)


class EndpointProbeRequest(BaseModel):
    """Probe a saved endpoint for its usable concurrency."""
    endpoint_id: str = Field(..., description="id of a saved endpoint")
    burst_size: int = Field(20, ge=1, le=50, description="parallel requests to fire")


class PeerProbeRequest(BaseModel):
    """Probe a workstation's compute endpoint (the Compute Peer card).

    Sent by the "Test Connection" button on a home/home-light variant's
    AI tab. ``endpoint`` is whatever the user typed — a bare ``host:port``,
    a saved ``peer://`` URL, or an ``http(s)://`` URL — normalised the same
    way the compute-peer link route normalises it, so testing and linking
    can never disagree about which address they mean.
    """
    endpoint: str = Field(..., description="Workstation address: host:port, peer://host:port, or http(s)://host:port")
    token: str = Field("", description="Bearer token issued by the workstation's pairing; empty falls back to the saved link's stored credential")


def _find_endpoint(endpoint_id: str) -> Optional[Dict[str, Any]]:
    """Look up a saved endpoint in models.yml by id."""
    config = llm_store.load()
    for ep in config.get("saved_endpoints") or []:
        if isinstance(ep, dict) and ep.get("id") == endpoint_id:
            return ep
    return None


def _probe_target(endpoint: Dict[str, Any]) -> Tuple[str, Dict[str, str]]:
    """Build the (url, headers) of a free, side-effect-free request.

    Mirrors the provider handling in ``llm.proxy_test`` — the listing endpoint
    each provider actually answers on.
    """
    url = (endpoint.get("url") or "").rstrip("/")
    provider = endpoint.get("provider") or "openai"
    api_key = endpoint.get("api_key") or ""
    headers: Dict[str, str] = {}

    if provider == "ollama":
        return f"{url}/api/tags", headers

    if provider == "google":
        target = f"{url}/v1beta/models"
        if api_key:
            target = f"{target}?{urllib.parse.urlencode({'key': api_key})}"
        return target, headers

    if provider == "anthropic":
        if api_key:
            headers["x-api-key"] = api_key
        headers["anthropic-version"] = "2023-06-01"
        return f"{url}/v1/models", headers

    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    target = f"{url}/models" if "v1" in url else f"{url}/v1/models"
    return target, headers


def _wave_sizes(burst_size: int) -> List[int]:
    """Split a burst into doubling waves that sum to exactly burst_size.

    20 → [1, 2, 4, 8, 5]. The trailing wave is whatever is left over; it is
    still measured, just not treated as a clean rung of the staircase.
    """
    sizes: List[int] = []
    remaining = burst_size
    width = 1
    while remaining > 0:
        take = min(width, remaining)
        sizes.append(take)
        remaining -= take
        width *= 2
    return sizes


def _fire(url: str, headers: Dict[str, str]) -> Tuple[float, bool, Optional[requests.Response]]:
    """One timed request. Returns (elapsed_ms, ok, response)."""
    start = time.perf_counter()
    try:
        resp = requests.get(url, headers=headers, timeout=PROBE_TIMEOUT)
        elapsed = (time.perf_counter() - start) * 1000
        return elapsed, resp.status_code < 400, resp
    except Exception as e:
        elapsed = (time.perf_counter() - start) * 1000
        logger.debug(f"Probe request failed after {elapsed:.0f}ms: {e}")
        return elapsed, False, None


def _run_wave(url: str, headers: Dict[str, str], size: int):
    """Fire `size` requests at once and return their results."""
    with ThreadPoolExecutor(max_workers=size) as pool:
        return list(pool.map(lambda _: _fire(url, headers), range(size)))


def _percentile(values: List[float], pct: float) -> float:
    """Nearest-rank percentile: ``ceil(pct/100 * N)``.

    statistics.quantiles needs n>1 and interpolates; a 1-request probe is a
    legitimate input here. ceil rather than round because round() bankers'-
    rounds, which would put p50 of five samples below the median.
    """
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(1, min(len(ordered), math.ceil(pct / 100 * len(ordered))))
    return ordered[rank - 1]


def _header_limit(responses: List[requests.Response]) -> Optional[int]:
    """Concurrency the provider itself advertises, if any."""
    for resp in responses:
        if resp is None:
            continue
        for name in _RATE_LIMIT_HEADERS:
            raw = resp.headers.get(name)
            if not raw:
                continue
            try:
                value = int(str(raw).strip())
            except (TypeError, ValueError):
                continue
            if value > 0:
                return value
    return None


def _find_saturation(waves: List[Tuple[int, float]]) -> Optional[int]:
    """First wave whose median latency exceeds the baseline by the factor.

    ``waves`` is [(concurrency, p50_ms), …] in the order they were fired.
    Returns the concurrency at which the endpoint started to push back, or
    None when it never did within this burst.
    """
    if len(waves) < 2:
        return None
    baseline = waves[0][1]
    if baseline <= 0:
        return None
    for concurrency, p50 in waves[1:]:
        if p50 > baseline * SATURATION_FACTOR:
            return concurrency
    return None


@router.post("/compute/endpoint-probe")
def endpoint_probe(req: EndpointProbeRequest) -> Dict[str, Any]:
    """Probe a saved endpoint's usable concurrency."""
    endpoint = _find_endpoint(req.endpoint_id)
    if endpoint is None:
        return {
            "error": {"message": f"No saved endpoint with id {req.endpoint_id!r}"},
        }

    url = (endpoint.get("url") or "").rstrip("/")
    provider = endpoint.get("provider") or "openai"
    if not url or not is_safe_url(url, provider):
        return {"error": {"message": "Endpoint URL is missing, unsafe, or not HTTP(S)"}}

    target, headers = _probe_target(endpoint)

    latencies: List[float] = []
    responses: List[requests.Response] = []
    successes = 0
    errors = 0
    waves: List[Tuple[int, float]] = []

    for size in _wave_sizes(req.burst_size):
        results = _run_wave(target, headers, size)
        wave_latencies = []
        for elapsed, ok, resp in results:
            latencies.append(elapsed)
            wave_latencies.append(elapsed)
            if ok:
                successes += 1
            else:
                errors += 1
            if resp is not None:
                responses.append(resp)
        waves.append((size, statistics.median(wave_latencies)))

    # A provider that publishes its limit beats anything inferred from timing.
    header_limit = _header_limit(responses)
    if header_limit is not None:
        saturation_point: Optional[int] = header_limit
        saturation_method = "header"
        recommended: Optional[int] = header_limit
    else:
        saturation_point = _find_saturation(waves)
        if saturation_point is not None:
            saturation_method = "latency_staircase"
            # Recommend the last wave that was still fast, not the one that
            # tipped over.
            below = [c for c, _ in waves if c < saturation_point]
            recommended = max(below) if below else 1
        else:
            saturation_method = "none"
            recommended = None

    if successes == 0:
        # Every request failed: the latency curve is noise, not a measurement.
        saturation_point = None
        saturation_method = "none"
        recommended = None

    return {
        "data": {
            "endpoint_id": req.endpoint_id,
            "probed_at": time.time(),
            "burst_size": req.burst_size,
            "wall_clock_ms": {
                "p50": _percentile(latencies, 50),
                "p90": _percentile(latencies, 90),
                "p99": _percentile(latencies, 99),
            },
            "saturation_point": saturation_point,
            "saturation_method": saturation_method,
            "recommended_concurrent": recommended,
            "successes": successes,
            "errors": errors,
            "histogram_path": None,
        }
    }


# ---------------------------------------------------------------------------
# Compute-peer health probe (home automation simplification, S3 / W15)
# ---------------------------------------------------------------------------

# Never a compute peer: a probe of a cloud metadata service would be reading
# the host's own cloud credentials, not testing a workstation link.
_METADATA_HOSTS = {"169.254.169.254", "metadata.google.internal"}


@router.post("/compute/peer-probe")
def peer_probe(req: PeerProbeRequest) -> Dict[str, Any]:
    """Probe a workstation's compute endpoint — the Compute Peer card's
    "Test Connection" button.

    Reuses ``PeerProvider``'s health probe (GET ``/api/compute/v1/models`` on
    the peer — authenticated, read-only, costs no GPU time) so the card and
    ``TierRouter``'s health tracking ask the peer the same question. The
    model list the probe returns is the card's read-only summary of what the
    workstation serves; an empty list is the honest state until the
    workstation's models route is implemented (TODO(federation-9.3)) — the
    workstation's own configuration still governs which model answers.

    Home/home-light only, matching the compute-peer link route in
    ``routes/peers.py``: a sysadmin instance assigns models per slot and has
    no compute-peer surface to test. An omitted token falls back to the
    credential the saved link already carries, so "Test Connection" works
    after pairing without asking for the token again.
    """
    from ...integrations.cognition_wiring import is_home_variant
    from ...model.providers.peer import PeerProvider
    # Same normalisation as the link route, so the address that tested
    # healthy is the address a subsequent link persists.
    from .peers import _peer_url

    if not is_home_variant():
        return {"error": {
            "code": "NOT_HOME_VARIANT",
            "message": "Compute-peer probing is a home/home-light feature; "
                       "the sysadmin variant assigns models per slot in Settings.",
        }}

    try:
        url = _peer_url(req.endpoint)
    except ValueError as e:
        return {"error": {"code": "BAD_PEER_ADDRESS", "message": str(e)}}

    if (urllib.parse.urlparse(url).hostname or "") in _METADATA_HOSTS:
        return {"error": {
            "code": "BAD_PEER_ADDRESS",
            "message": "A cloud metadata endpoint is not a compute peer.",
        }}

    token = req.token
    if not token:
        # The saved link carries the credential the pairing issued; a probe
        # must not require the user to re-enter it.
        for ep in llm_store.load().get("saved_endpoints") or []:
            if (ep.get("provider") == "peer"
                    and (ep.get("url") or "").rstrip("/") == url):
                token = ep.get("api_key") or ""
                break

    provider = PeerProvider(url, token)
    ok = provider.health_check()

    models: List[str] = []
    message = (
        f"Peer {url} answered the health probe."
        if ok else
        f"Peer {url} did not answer the health probe."
    )
    if ok:
        try:
            models = [m.model_id for m in provider.list_models()]
        except Exception as e:
            message = f"Peer is reachable but its model list failed: {e}"
    elif not token:
        message += (" No pairing token is stored for this address — if the "
                    "workstation requires one, pair it first.")

    return {"data": {"ok": ok, "message": message, "models": models, "url": url}}
