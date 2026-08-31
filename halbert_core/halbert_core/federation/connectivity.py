# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Internet connectivity detection with caching.

P4a — Supports the compute fallback chain reorder (P4b) by letting the
``ComputeRouter`` know whether the cloud LLM provider is reachable before
attempting a cloud request.  Without this probe, a satellite with no
internet would burn the full request timeout on every turn before falling
back to the local model or peer.

Design
------
- Probes a configurable URL (default: a lightweight HEAD to a well-known
  endpoint).  The caller can pass the cloud LLM provider's base URL so
  the probe tests the *actual* endpoint that will be used.
- Results are cached for ``cache_interval`` seconds (default 30s) so a
  burst of turns probes once, not once per turn.
- Thread-safe: a ``threading.Lock`` guards the cache.  Safe to call from
  ``asyncio.run_in_executor`` (matching ``ComputeRouter._probe_peer_health``).
- Pure stdlib + ``requests`` (already a hard dep).  No new dependencies.

Usage
-----
::

    probe = ConnectivityProbe(
        probe_url="https://api.openai.com/v1/models",
        cache_interval=30,
    )

    if probe.is_online():
        # cloud is reachable — try cloud model first
    else:
        # no internet — fall back to local model / peer / template
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Optional

logger = logging.getLogger(__name__)

# A lightweight, widely-available endpoint for the default probe.
# We use a HEAD request with a short timeout — we only care that the
# TCP+TLS handshake succeeds, not the response body.
_DEFAULT_PROBE_URL = "https://api.github.com"  # stable, CDN-backed, low-latency
_DEFAULT_TIMEOUT = 3.0  # seconds — generous enough for slow DNS, tight enough for UX
_DEFAULT_CACHE_INTERVAL = 30.0  # seconds


class ConnectivityProbe:
    """Cached internet-connectivity checker.

    The probe is intentionally simple: one HTTP HEAD request to a
    configurable URL.  If it gets any HTTP response (even a 4xx/5xx),
    the internet is reachable — we're testing *connectivity*, not the
    specific service's health.  A connection error (DNS failure, TCP
    timeout, refused) means offline.
    """

    def __init__(
        self,
        probe_url: str = _DEFAULT_PROBE_URL,
        timeout: float = _DEFAULT_TIMEOUT,
        cache_interval: float = _DEFAULT_CACHE_INTERVAL,
    ):
        """
        Args:
            probe_url: URL to probe.  Defaults to a well-known CDN-backed
                endpoint.  Callers should pass the cloud LLM provider's
                base URL when available so the probe tests the actual
                endpoint.
            timeout: HTTP request timeout in seconds.
            cache_interval: How long to cache a probe result before
                re-probing (seconds).  Default 30s.
        """
        self._probe_url = probe_url
        self._timeout = timeout
        self._cache_interval = cache_interval
        self._lock = threading.Lock()
        self._cached: Optional[bool] = None
        self._last_probe: float = 0.0

    def is_online(self) -> bool:
        """Return True if the internet is reachable, False if not.

        Uses the cached result if it's younger than ``cache_interval``;
        otherwise re-probes.  Thread-safe.
        """
        now = time.monotonic()
        # Fast path: check cache without acquiring the lock
        if self._cached is not None and (now - self._last_probe) < self._cache_interval:
            return self._cached

        with self._lock:
            # Re-check under the lock: a concurrent probe may have just
            # refreshed the cache.
            now = time.monotonic()
            if self._cached is not None and (now - self._last_probe) < self._cache_interval:
                return self._cached

            result = self._http_probe()
            self._cached = result
            self._last_probe = now
            if not result:
                logger.debug("Connectivity probe: offline (url=%s)", self._probe_url)
            return result

    def force_recheck(self) -> bool:
        """Bypass the cache and probe immediately. Returns the fresh result."""
        with self._lock:
            result = self._http_probe()
            self._cached = result
            self._last_probe = time.monotonic()
            return result

    def _http_probe(self) -> bool:
        """Blocking HTTP HEAD probe. Returns True if any response received."""
        import requests

        try:
            resp = requests.head(
                self._probe_url,
                timeout=self._timeout,
                allow_redirects=True,
                headers={"User-Agent": "Halbert-ConnectivityProbe/1.0"},
            )
            # Any HTTP response means we reached the internet — even 4xx/5xx.
            return resp.status_code is not None
        except requests.RequestException:
            return False

    @property
    def probe_url(self) -> str:
        return self._probe_url

    @property
    def cache_interval(self) -> float:
        return self._cache_interval
