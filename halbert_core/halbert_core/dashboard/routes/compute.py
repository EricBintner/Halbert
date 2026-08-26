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
