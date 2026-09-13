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
