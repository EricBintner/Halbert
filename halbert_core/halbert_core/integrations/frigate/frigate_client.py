# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Async REST client for Frigate NVR.

Mirrors HAClient: aiohttp session, lazy init, token auth, structured
exceptions. Wraps the Frigate REST API:

  GET /api/events           — query detection events
  GET /api/reviews          — query review segments
  GET /api/config           — get Frigate config (cameras, zones)
  GET /{camera}/latest.jpg  — latest frame from a camera
  GET /events/{id}/snapshot.jpg — event snapshot
  GET /events/{id}/clip.mp4    — event clip (redirect to file)
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import aiohttp

from .frigate_config import FrigateConfig

logger = logging.getLogger("halbert.integrations.frigate.client")


class FrigateClient:
    """Async REST API client for Frigate NVR.

    Uses aiohttp to talk to Frigate's REST API. All methods are async
    and return parsed JSON (or raw bytes for image endpoints).
    """

    def __init__(self, config: FrigateConfig) -> None:
        self.config = config
        self._session: Optional[aiohttp.ClientSession] = None

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        return headers

    def _base_url(self) -> str:
        return self.config.url.rstrip("/")

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def _request(
        self,
        method: str,
        path: str,
        params: Optional[dict] = None,
        json_data: Optional[dict] = None,
    ) -> Any:
        """Make an authenticated request to Frigate and return parsed JSON."""
        session = await self._get_session()
        url = f"{self._base_url()}{path}"
        try:
            async with session.request(
                method,
                url,
                headers=self._headers(),
                params=params,
                json=json_data,
                ssl=self.config.verify_ssl,
            ) as resp:
                if resp.status == 401:
                    raise FrigateAuthError("Invalid Frigate API key or unauthorized")
                if resp.status == 404:
                    raise FrigateNotFoundError(f"Frigate endpoint not found: {path}")
                resp.raise_for_status()
                if resp.content_type == "application/json":
                    return await resp.json()
                return await resp.text()
        except aiohttp.ClientError as e:
            raise FrigateConnectionError(f"Frigate connection error: {e}") from e

    async def _request_bytes(
        self,
        method: str,
        path: str,
        params: Optional[dict] = None,
    ) -> bytes:
        """Make an authenticated request and return raw bytes (for images)."""
        session = await self._get_session()
        url = f"{self._base_url()}{path}"
        try:
            async with session.request(
                method,
                url,
                headers=self._headers(),
                params=params,
                ssl=self.config.verify_ssl,
            ) as resp:
                if resp.status == 401:
                    raise FrigateAuthError("Invalid Frigate API key or unauthorized")
                if resp.status == 404:
                    raise FrigateNotFoundError(f"Frigate endpoint not found: {path}")
                resp.raise_for_status()
                return await resp.read()
        except aiohttp.ClientError as e:
            raise FrigateConnectionError(f"Frigate connection error: {e}") from e

    # ── Status / Config ─────────────────────────────────────────

    async def get_status(self) -> Dict[str, Any]:
        """Check if Frigate is reachable and return basic info."""
        try:
            result = await self._request("GET", "/api/config")
            return {"connected": True, "cameras": list(result.get("cameras", {}).keys())}
        except Exception as e:
            return {"connected": False, "error": str(e)}

    async def get_config(self) -> Dict[str, Any]:
        """Get the full Frigate configuration (cameras, zones, objects)."""
        return await self._request("GET", "/api/config")

    async def get_cameras(self) -> List[Dict[str, Any]]:
        """List configured cameras with their zones and labels."""
        config = await self.get_config()
        cameras = []
        for name, cam_cfg in config.get("cameras", {}).items():
            cameras.append({
                "name": name,
                "zones": list(cam_cfg.get("zones", {}).keys()),
                "objects": cam_cfg.get("objects", {}),
                "detect": cam_cfg.get("detect", {}).get("enabled", True),
            })
        return cameras

    # ── Events ──────────────────────────────────────────────────

    async def get_events(
        self,
        camera: str = "all",
        labels: str = "all",
        zones: str = "all",
        after: Optional[float] = None,
        before: Optional[float] = None,
        limit: int = 100,
        has_snapshot: Optional[bool] = None,
        has_clip: Optional[bool] = None,
        in_progress: bool = False,
        favorites: bool = False,
        min_score: float = 0.0,
        sort: str = "score",
    ) -> List[Dict[str, Any]]:
        """Query detection events from Frigate.

        Args:
            camera: Camera name or "all".
            labels: Comma-separated labels or "all" (person, car, dog).
            zones: Comma-separated zones or "all".
            after: Unix timestamp — events starting after this time.
            before: Unix timestamp — events starting before this time.
            limit: Maximum number of events to return.
            has_snapshot: Filter to events with/without snapshots.
            has_clip: Filter to events with/without clips.
            in_progress: Only return in-progress events.
            favorites: Only return favorited events.
            min_score: Minimum detection score (0.0-1.0).
            sort: Sort order ("score", "time", "speed").
        """
        params = {
            "cameras" if camera == "all" else "camera": camera,
            "labels": labels,
            "zones": zones,
            "limit": limit,
            "in_progress": in_progress,
            "favorites": favorites,
            "min_score": min_score,
            "sort": sort,
        }
        if after is not None:
            params["after"] = after
        if before is not None:
            params["before"] = before
        if has_snapshot is not None:
            params["has_snapshot"] = has_snapshot
        if has_clip is not None:
            params["has_clip"] = has_clip

        result = await self._request("GET", "/api/events", params=params)
        if isinstance(result, list):
            return result
        return []

    async def get_event(self, event_id: str) -> Dict[str, Any]:
        """Get a single event by ID."""
        return await self._request("GET", f"/api/events/{event_id}")

    # ── Reviews ─────────────────────────────────────────────────

    async def get_reviews(
        self,
        camera: str = "all",
        severity: str = "all",
        after: Optional[float] = None,
        before: Optional[float] = None,
        limit: int = 100,
        has_clip: Optional[bool] = None,
    ) -> List[Dict[str, Any]]:
        """Query review segments from Frigate.

        Reviews are Frigate's higher-level grouping of events into
        alert (severity=alert) or detection (severity=detection) segments.
        """
        params = {
            "cameras" if camera == "all" else "camera": camera,
            "severity": severity,
            "limit": limit,
        }
        if after is not None:
            params["after"] = after
        if before is not None:
            params["before"] = before
        if has_clip is not None:
            params["has_clip"] = has_clip

        result = await self._request("GET", "/api/reviews", params=params)
        if isinstance(result, list):
            return result
        return []

    # ── Media (images) ──────────────────────────────────────────

    async def get_latest_frame(
        self,
        camera: str,
        extension: str = "jpg",
        bbox: bool = True,
        timestamp: bool = True,
        zones: bool = True,
        quality: int = 70,
    ) -> bytes:
        """Get the latest frame from a camera as raw image bytes.

        Returns JPEG bytes by default. Falls back to preview frames
        if the camera is offline (Frigate handles this server-side).
        """
        params = {
            "bbox": int(bbox),
            "timestamp": int(timestamp),
            "zones": int(zones),
            "quality": quality,
        }
        return await self._request_bytes(
            "GET",
            f"/api/{camera}/latest.{extension}",
            params=params,
        )

    async def get_event_snapshot(
        self,
        event_id: str,
        bbox: bool = True,
        timestamp: bool = True,
        crop: bool = False,
        height: Optional[int] = None,
        quality: int = 70,
    ) -> bytes:
        """Get the snapshot JPEG for a specific event.

        Returns raw JPEG bytes. The snapshot is the best frame captured
        during the detection event, with optional bounding box overlay.
        """
        params = {
            "bbox": int(bbox),
            "timestamp": int(timestamp),
            "crop": int(crop),
            "quality": quality,
        }
        if height is not None:
            params["h"] = height
        return await self._request_bytes(
            "GET",
            f"/api/events/{event_id}/snapshot.jpg",
            params=params,
        )

    async def get_label_snapshot(
        self,
        camera: str,
        label: str = "any",
        bbox: bool = True,
        timestamp: bool = True,
        quality: int = 70,
    ) -> bytes:
        """Get the most recent snapshot for a camera + label combination."""
        params = {
            "bbox": int(bbox),
            "timestamp": int(timestamp),
            "quality": quality,
        }
        return await self._request_bytes(
            "GET",
            f"/api/{camera}/{label}/snapshot.jpg",
            params=params,
        )

    # ── Stats ───────────────────────────────────────────────────

    async def get_stats(self) -> Dict[str, Any]:
        """Get Frigate system stats (CPU, detection FPS, camera health)."""
        return await self._request("GET", "/api/stats")


class FrigateConnectionError(Exception):
    """Raised when Frigate is unreachable."""


class FrigateAuthError(Exception):
    """Raised when Frigate rejects the API key."""


class FrigateNotFoundError(Exception):
    """Raised when a Frigate endpoint or event is not found."""
