# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Peer liveness probe — 3-strike hysteresis before calling a peer dead.

A satellite needs one honest answer: "is the canonical still there?"
The naive answer — one failed request flips the flag — flaps on every
network blip and sends the UI's "canonical offline" banner flickering.
The hysteresis is the same shape compute_router uses: three consecutive
failures to declare unreachable, one success to declare reachable again.

The probe polls the peer's health endpoint — the same
``/api/conversations/health`` the conversation proxy uses — and reports
``canonical_reachable``. Fallback (Step 1.6) and the status surfaces
read the flag; nobody else makes the reachability call.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Optional

logger = logging.getLogger('halbert.replica.liveness')

_FAILURES_TO_MARK_UNREACHABLE = 3


class PeerLivenessProbe:
    """Polls the canonical host's health endpoint on an interval.

    Args:
        peer_url: the peer's base URL (``http://mac-mini:8000``).
        bearer_token: the peer token to present.
        interval_s: poll period.
        http_get: transport seam — ``requests.get`` by default; a stub in
            tests. Called as ``http_get(url, headers=…, timeout=…)``.
    """

    def __init__(
        self,
        peer_url: str,
        bearer_token: str,
        interval_s: float = 30.0,
        http_get: Optional[Callable[..., Any]] = None,
    ):
        self._peer_url = peer_url.rstrip("/")
        self._token = bearer_token
        self._interval = interval_s
        self._http_get = http_get
        self._failures = 0
        self._reachable = True
        self._task: Optional[asyncio.Task] = None
        self.last_error: Optional[str] = None

    @property
    def canonical_reachable(self) -> bool:
        return self._reachable

    @property
    def consecutive_failures(self) -> int:
        return self._failures

    async def start(self) -> None:
        if self._task is not None:
            return
        self._task = asyncio.get_running_loop().create_task(self._loop())

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    async def _loop(self) -> None:
        while True:
            await self.poll_once()
            await asyncio.sleep(self._interval)

    async def poll_once(self) -> bool:
        """One probe. Returns the post-update reachability.

        Runs the blocking GET in a worker thread; any exception counts as
        a failure — the probe's whole job is that distinction.
        """
        ok = await asyncio.to_thread(self._get_health)
        if ok:
            if not self._reachable:
                logger.info("Peer %s reachable again", self._peer_url)
            self._failures = 0
            self._reachable = True
        else:
            self._failures += 1
            if self._failures >= _FAILURES_TO_MARK_UNREACHABLE:
                if self._reachable:
                    logger.warning(
                        "Peer %s unreachable after %d failures (%s)",
                        self._peer_url, self._failures, self.last_error,
                    )
                self._reachable = False
        return self._reachable

    def _get_health(self) -> bool:
        """GET {peer_url}/api/conversations/health → True on a healthy 200."""
        http_get = self._http_get
        if http_get is None:
            import requests
            http_get = requests.get
        try:
            resp = http_get(
                f"{self._peer_url}/api/conversations/health",
                headers={"Authorization": f"Bearer {self._token}"},
                timeout=10.0,
            )
            if resp.status_code != 200:
                self.last_error = f"HTTP {resp.status_code}"
                return False
            healthy = resp.json().get("healthy")
            self.last_error = None if healthy else "unhealthy"
            return bool(healthy)
        except Exception as e:
            self.last_error = f"{type(e).__name__}: {e}"
            return False


# ---------------------------------------------------------------------------
# Lifecycle — the satellite's half of warm standby
# ---------------------------------------------------------------------------

#: The running probe, for the status surfaces. One per process.
_current_probe: Optional[PeerLivenessProbe] = None


def current_probe() -> Optional[PeerLivenessProbe]:
    """The live probe if one is running — /api/replica/status reads this."""
    return _current_probe


def _body_peer_target() -> Optional[tuple]:
    """(peer_origin_url, bearer_token) when this node is a body."""
    try:
        from ..integrations.cognition_wiring import (
            _get_canonical_memory_url,
            _get_canonical_thread_url,
            _get_peer_token,
        )
        from urllib.parse import urlsplit
        url = _get_canonical_thread_url() or _get_canonical_memory_url() or ""
        if not url:
            return None
        token = _get_peer_token() or ""
        parts = urlsplit(url)
        return f"{parts.scheme}://{parts.netloc}", token
    except Exception:
        return None


async def start_liveness_probe(app, interval_s: float = 30.0) -> Optional[PeerLivenessProbe]:
    """Start the probe on a body node. Returns the probe or None.

    Mirrors start_replica_push_loop: a node that is not a body gets no
    probe — a canonical host does not watch itself, and an independent
    node has no canonical to watch. The probe lives on
    app.state.liveness_probe for shutdown, and is registered as the
    module singleton for the status surfaces.
    """
    global _current_probe
    target = _body_peer_target()
    if target is None:
        return None
    url, token = target
    probe = PeerLivenessProbe(url, token, interval_s=interval_s)
    await probe.start()
    app.state.liveness_probe = probe
    _current_probe = probe
    logger.info("Peer liveness probe started against %s (every %.0fs)", url, interval_s)
    return probe


async def stop_liveness_probe(app) -> None:
    """Stop the running probe, if any."""
    global _current_probe
    probe = getattr(app.state, "liveness_probe", None) or _current_probe
    if probe is None:
        return
    await probe.stop()
    app.state.liveness_probe = None
    _current_probe = None
