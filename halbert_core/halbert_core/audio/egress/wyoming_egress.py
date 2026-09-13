# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Wyoming egress — stream synthesized PCM to satellite speakers.

The existing ``WyomingIngress`` accepts audio from satellites; this
module sends synthesized PCM *back* to satellites so a thin satellite
(a wall-mounted ESP32, an Atom Echo, a Pi) can play Halbert's voice
without running TTS locally.

Protocol: the satellite opens a TCP connection to Halbert's Wyoming
port and sends ``audio-start`` / ``audio-chunk`` / ``audio-stop``
frames for ingress. Halbert sends the same frame types back on the
same connection for egress — the satellite's speaker is the output
sink. The connection is bidirectional.

Security: the satellite must already be authenticated by the ingress
handler. Egress is never sent to an unauthenticated connection. The
ingress server binds to ``127.0.0.1`` by default (the security
decision that prevents unauthenticated LAN audio ingress); a
satellite on the LAN needs an explicit allow-list entry or a tunnel.

The egress hub is a process singleton (like the TTS egress hub for
browser subscribers). The state machine's streaming TTS path can
publish to both the browser hub and the Wyoming hub.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from ..ingress.wyoming_ingress import write_wyoming_frame

logger = logging.getLogger("halbert.audio.egress.wyoming")


class WyomingEgressHub:
    """Relay of TTS PCM frames to connected Wyoming satellites.

    Each connected satellite that has a speaker gets audio frames
    published to it. The hub tracks which satellite connections are
    eligible for egress (the satellite must have sent a ``describe``
    frame with ``audio_output: True``).

    The hub is deliberately a dumb relay, like the browser TTS egress
    hub. It does not synthesize — it receives PCM from the state
    machine's streaming TTS path and forwards it.
    """

    def __init__(self) -> None:
        # session_id -> list of (area_id, writer) pairs for satellites
        # that can play audio.
        self._subscribers: Dict[str, List[Dict[str, Any]]] = {}
        # session_id -> BargeInToken (shared with the browser hub).
        self._cancel_tokens: Dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Subscription (called by the ingress handler when a satellite
    # describes itself as having audio output capability)
    # ------------------------------------------------------------------

    def subscribe(
        self,
        session_id: str,
        writer: asyncio.StreamWriter,
        area_id: str = "",
    ) -> None:
        """Register a satellite connection as an egress target."""
        self._subscribers.setdefault(session_id, []).append({
            "writer": writer,
            "area_id": area_id,
        })
        logger.info(
            f"Wyoming egress: satellite subscribed "
            f"(session={session_id}, area={area_id})"
        )

    def unsubscribe(self, session_id: str, writer: asyncio.StreamWriter) -> None:
        """Drop a satellite egress subscription."""
        subs = self._subscribers.get(session_id)
        if subs is None:
            return
        self._subscribers[session_id] = [
            s for s in subs if s["writer"] is not writer
        ]
        if not self._subscribers[session_id]:
            del self._subscribers[session_id]
        logger.debug(f"Wyoming egress: satellite unsubscribed (session={session_id})")

    def has_subscribers(self, session_id: str) -> bool:
        """True if any satellite is waiting for this session's audio."""
        return bool(self._subscribers.get(session_id))

    def subscriber_areas(self, session_id: str) -> List[str]:
        """List the area_ids of subscribed satellites for this session."""
        return [s["area_id"] for s in self._subscribers.get(session_id, [])]

    # ------------------------------------------------------------------
    # Publishing
    # ------------------------------------------------------------------

    async def publish(
        self,
        session_id: str,
        data: "bytes | dict",
    ) -> None:
        """Send one frame to every subscribed satellite for this session.

        ``bytes`` is sent as an ``audio-chunk`` frame with the raw PCM
        payload. ``dict`` is sent as a text control frame
        (``audio-start`` / ``audio-stop``).
        """
        subs = self._subscribers.get(session_id, [])
        if not subs:
            return

        if isinstance(data, bytes):
            # Send as audio-chunk with raw PCM payload.
            for sub in list(subs):
                writer = sub["writer"]
                try:
                    await write_wyoming_frame(
                        writer,
                        "audio-chunk",
                        {"rate": 22050, "width": 2, "channels": 1},
                        payload=data,
                    )
                except Exception:
                    logger.debug(
                        f"Wyoming egress: dropping dead satellite "
                        f"(session={session_id}, area={sub.get('area_id', '')})"
                    )
                    self.unsubscribe(session_id, writer)
        else:
            # Control frame: audio-start or audio-stop.
            msg_type = data.get("type", "")
            if msg_type == "begin":
                frame_type = "audio-start"
                frame_data = {
                    "rate": data.get("sample_rate", 22050),
                    "width": 2,
                    "channels": 1,
                }
            elif msg_type in ("end", "cancelled"):
                frame_type = "audio-stop"
                frame_data = {}
            else:
                return  # Unknown control frame

            for sub in list(subs):
                writer = sub["writer"]
                try:
                    await write_wyoming_frame(writer, frame_type, frame_data)
                except Exception:
                    logger.debug(
                        f"Wyoming egress: dropping dead satellite "
                        f"(session={session_id}, area={sub.get('area_id', '')})"
                    )
                    self.unsubscribe(session_id, writer)

    async def cancel(self, session_id: str) -> None:
        """Barge in: fire the cancel token and send audio-stop."""
        token = self._cancel_tokens.get(session_id)
        if token is not None:
            try:
                token.trigger()
            except Exception:
                pass
        await self.publish(session_id, {"type": "cancelled"})

    # ------------------------------------------------------------------
    # Barge-in token registry
    # ------------------------------------------------------------------

    def register_cancel_token(self, session_id: str, token: Any) -> None:
        self._cancel_tokens[session_id] = token

    def clear_cancel_token(self, session_id: str) -> None:
        self._cancel_tokens.pop(session_id, None)


# ---------------------------------------------------------------------------
# Process-wide singleton
# ---------------------------------------------------------------------------

_hub: Optional[WyomingEgressHub] = None


def get_wyoming_egress_hub() -> WyomingEgressHub:
    """Return the process-wide WyomingEgressHub singleton."""
    global _hub
    if _hub is None:
        _hub = WyomingEgressHub()
    return _hub
