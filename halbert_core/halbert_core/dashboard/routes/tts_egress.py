# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""TTS egress hub (O3) — session-keyed pub/sub for spoken audio.

The browser is the voice-mode audio terminal (Decision 1 in doc 16): when the
agent state machine speaks a voice turn, the PiperTTS PCM must reach the
browser over ``/api/audio/tts`` so it plays there and the audio-reactive mark
can visualize the *actual spoken output*.

This module is the relay between the two sides:

    state_machine (publisher)  --publish()-->  hub  --WS frames-->  browser

- ``publish(session_id, bytes)``   -> one binary PCM frame (s16le mono)
- ``publish(session_id, dict)``    -> one JSON text frame
- ``cancel(session_id)``           -> fires the session's registered barge-in
   token and publishes ``{"type": "cancelled"}``

Wire protocol over ``/api/audio/tts?session_id=...``:

    {"type": "begin", "sample_rate": <int>, "format": "s16le"}   (text)
    <binary PCM frames>                                          (binary)
    {"type": "end"} or {"type": "cancelled"}                     (text)

The hub is deliberately a dumb relay and is NOT gated on the audio
capability: it exists even when the audio pipeline is down, and forwards
nothing until a browser subscribes — a subscriber check is the only gate.
Synthesis itself (PiperTTS) is what needs the audio stack, and that is
checked where it happens, in the state machine's hook.

Process-wide singleton via ``get_tts_egress_hub()`` — the same pattern as
``proactive.events.get_event_bus()`` — because the publisher (the agent
state machine, built once in ``routes/agent.py`` without an app reference)
and the subscribers (the WebSocket route) meet here without either holding
the FastAPI app. ``app.py`` aliases the singleton onto ``app.state.tts_egress``
so the route can find it the way the plan documents.

Publishers and subscribers share the dashboard's event loop (the agent turn
runs inside the SSE generator on the same loop as the sockets), so publish()
sends directly; a send that fails means the socket is dead and the subscriber
is dropped — no sends to closed sockets, no leaks.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("halbert.dashboard.tts_egress")


class TtsEgressHub:
    """Relay of TTS frames from the state machine to browser subscribers."""

    def __init__(self) -> None:
        # session_id -> live WebSockets subscribed to that session's audio.
        self._subscribers: Dict[str, List[Any]] = {}
        # session_id -> the BargeInToken of the turn currently synthesizing,
        # registered by the state machine hook so cancel() can abort it.
        self._cancel_tokens: Dict[str, Any] = {}
        # Optional AudioPipelineCoordinator. Held so the state machine hook
        # can mint coordinator-owned barge-in tokens (VAD barge-in then
        # cancels browser playback too); None when the pipeline is down.
        self._pipeline: Any = None

    # ------------------------------------------------------------------
    # Subscription
    # ------------------------------------------------------------------

    def subscribe(self, session_id: str, websocket: Any) -> Callable[[], None]:
        """Register ``websocket`` as a subscriber of ``session_id``'s audio.

        Returns an unsubscribe handle the WS route calls on disconnect.
        Multiple subscribers per session are allowed (e.g. two tabs).
        """
        self._subscribers.setdefault(session_id, []).append(websocket)
        logger.debug(f"TTS egress: subscriber added for session {session_id}")
        return lambda: self.unsubscribe(session_id, websocket)

    def unsubscribe(self, session_id: str, websocket: Any) -> None:
        """Drop one subscriber; safe to call twice (disconnect cleanup)."""
        sockets = self._subscribers.get(session_id)
        if sockets is None:
            return
        try:
            sockets.remove(websocket)
        except ValueError:
            return
        if not sockets:
            self._subscribers.pop(session_id, None)
        logger.debug(f"TTS egress: subscriber removed for session {session_id}")

    def has_subscribers(self, session_id: str) -> bool:
        """True if any live socket awaits this session's audio.

        This is the state machine hook's gate: no subscriber, no synthesis.
        """
        return bool(self._subscribers.get(session_id))

    # ------------------------------------------------------------------
    # Publishing
    # ------------------------------------------------------------------

    async def publish(self, session_id: str, data: "bytes | dict") -> None:
        """Send one frame to every subscriber of ``session_id``.

        ``bytes`` goes out as a binary PCM frame; ``dict`` is JSON-encoded
        into a text frame (begin/end/cancelled). A send that fails means the
        socket is gone — the subscriber is dropped, never retried.
        """
        for websocket in list(self._subscribers.get(session_id, [])):
            try:
                if isinstance(data, bytes):
                    await websocket.send_bytes(data)
                else:
                    await websocket.send_text(json.dumps(data))
            except Exception:
                logger.debug(
                    f"TTS egress: dropping dead subscriber of {session_id}"
                )
                self.unsubscribe(session_id, websocket)

    async def cancel(self, session_id: str) -> None:
        """Barge in on ``session_id``: fire the registered barge-in token
        (aborting in-flight synthesis between chunks) and tell the browser
        with ``{"type": "cancelled"}``."""
        token = self._cancel_tokens.get(session_id)
        if token is not None:
            try:
                token.trigger()
            except Exception as e:
                logger.debug(f"TTS egress: cancel token trigger failed: {e}")
        await self.publish(session_id, {"type": "cancelled"})

    # ------------------------------------------------------------------
    # Barge-in token registry
    # ------------------------------------------------------------------

    def register_cancel_token(self, session_id: str, token: Any) -> None:
        """Register the barge-in token of the turn being synthesized."""
        self._cancel_tokens[session_id] = token

    def clear_cancel_token(self, session_id: str) -> None:
        """Drop the session's token (turn finished or cancelled)."""
        self._cancel_tokens.pop(session_id, None)

    # ------------------------------------------------------------------
    # Pipeline reference
    # ------------------------------------------------------------------

    def set_pipeline(self, pipeline: Any) -> None:
        """Remember the audio pipeline coordinator (or None when it is down).

        Set by ``app.py`` right after the O2 coordinator bootstrap; the state
        machine hook reads it to mint coordinator-owned barge-in tokens so
        VAD barge-in cancels browser playback, falling back to a standalone
        token when the pipeline is not running.
        """
        self._pipeline = pipeline

    @property
    def pipeline(self) -> Any:
        return self._pipeline


# ---------------------------------------------------------------------------
# Process-wide singleton (get_event_bus pattern — see module docstring)
# ---------------------------------------------------------------------------

_hub: Optional[TtsEgressHub] = None


def get_tts_egress_hub() -> TtsEgressHub:
    """Get the process-wide TTS egress hub singleton."""
    global _hub
    if _hub is None:
        _hub = TtsEgressHub()
    return _hub


def _reset_tts_egress_hub() -> None:
    """Drop the singleton (test isolation only)."""
    global _hub
    _hub = None