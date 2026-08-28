# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Async REST client for Home Assistant."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import aiohttp

from .ha_config import HAConfig

logger = logging.getLogger("halbert.integrations.home_assistant.client")


class HAClient:
    """Async REST API client for Home Assistant.

    Uses aiohttp to talk to HA's REST API (/api/states, /api/services,
    /api/services/{domain}/{service}, etc).
    """

    def __init__(self, config: HAConfig) -> None:
        self.config = config
        self._session: Optional[aiohttp.ClientSession] = None

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.config.token}",
            "Content-Type": "application/json",
        }

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
        json_data: Optional[dict] = None,
    ) -> Any:
        """Make an authenticated request to HA and return parsed JSON."""
        session = await self._get_session()
        url = f"{self._base_url()}{path}"
        try:
            async with session.request(
                method,
                url,
                headers=self._headers(),
                json=json_data,
                ssl=self.config.verify_ssl,
            ) as resp:
                if resp.status == 401:
                    raise HAAuthError("Invalid HA token or unauthorized")
                if resp.status == 404:
                    raise HANotFoundError(f"HA endpoint not found: {path}")
                resp.raise_for_status()
                if resp.content_type == "application/json":
                    return await resp.json()
                return await resp.text()
        except aiohttp.ClientError as e:
            raise HAConnectionError(f"HA connection error: {e}") from e

    async def get_status(self) -> Dict[str, Any]:
        """Check if HA is reachable and return config info."""
        try:
            result = await self._request("GET", "/api/")
            return {"connected": True, "message": result.get("message", "OK")}
        except Exception as e:
            return {"connected": False, "error": str(e)}

    async def get_states(self) -> List[Dict[str, Any]]:
        """Get all entity states from HA."""
        return await self._request("GET", "/api/states")

    async def get_entity_state(self, entity_id: str) -> Dict[str, Any]:
        """Get the state of a single entity."""
        return await self._request("GET", f"/api/states/{entity_id}")

    async def get_areas(self) -> List[Dict[str, Any]]:
        """List all areas defined in HA."""
        return await self._request("GET", "/api/config/area_registry")

    async def call_service(
        self,
        domain: str,
        service: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Call a HA service (e.g. light.turn_off, climate.set_temperature)."""
        result = await self._request(
            "POST",
            f"/api/services/{domain}/{service}",
            json_data=data or {},
        )
        # HA returns a list of affected entity states or an empty dict
        if isinstance(result, list):
            return {"success": True, "entities": result}
        return {"success": True, "result": result}

    async def get_entities_by_domain(
        self,
        domain: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Get entity states, optionally filtered by domain."""
        states = await self.get_states()
        if domain:
            return [s for s in states if s["entity_id"].startswith(f"{domain}.")]
        return states


class HAConnectionError(Exception):
    """Raised when HA is unreachable."""


class HAAuthError(Exception):
    """Raised when HA rejects the token."""


class HANotFoundError(Exception):
    """Raised when an HA endpoint or entity is not found."""
