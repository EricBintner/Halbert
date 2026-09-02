# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
WebSocket routes.

- ``/ws``: existing dashboard real-time update channel (unchanged).
- ``/ws/terminal/{session_id}`` (B1f): bidirectional bridge to a PTY session.
- ``/api/audio/stream`` (O2): browser microphone uplink — binary frames of
  16kHz s16le mono PCM from the frontend AudioWorklet, handed to the audio
  pipeline's dashboard ingress (``WebRtcIngress``). Closed with 1013 ("try
  again later") when no coordinator/ingress is running — the pipeline is
  capability-gated and optional.
- ``/api/audio/tts`` (O3): TTS egress downlink — the agent state machine's
  spoken Piper PCM streamed to the browser that subscribed with the turn's
  session id. Server->client frames only (begin/binary PCM/end/cancelled),
  except the {"type": "cancel"} control frame the browser can send to barge
  in (see ``routes/tts_egress.py`` for the protocol).

  Terminal message protocol (JSON, both directions):
    client -> server: {"type": "stdin",  "data": "..."}
                      {"type": "resize", "cols": 80, "rows": 24}
    server -> client: {"type": "stdout", "data": "..."}
                      {"type": "exit",   "code": 0}

  On connect the WS attaches to an existing PTY session (created via
  POST /sessions). stdout is streamed from session.read_chunk(); stdin and
  resize are forwarded to the session. The session is left alive on
  disconnect so the frontend can reattach; the manager's idle reaper reclaims
  it.
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.requests import Request
import asyncio
import json
import logging

from ...streaming.session_manager import get_terminal_manager

router = APIRouter()
logger = logging.getLogger('halbert.dashboard.websocket')


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time dashboard updates.

    Sends events:
    - system_status: System metrics every 5s
    - approval_request: New approval needed
    - job_update: Job status changed
    - decision: New LLM decision made
    """
    # Get connection manager from app state
    manager = websocket.app.state.ws_manager

    await manager.connect(websocket)

    try:
        while True:
            # Keep connection alive
            # Actual data is sent via manager.broadcast()
            await websocket.receive_text()

    except WebSocketDisconnect:
        manager.disconnect(websocket)
        logger.info("Client disconnected")


@router.websocket("/ws/terminal/{session_id}")
async def terminal_websocket(websocket: WebSocket, session_id: str):
    """Bidirectional WebSocket bridge to a PTY session (B1f)."""
    manager = get_terminal_manager()
    session = manager.get(session_id)
    if session is None:
        await websocket.close(code=4404, reason="Session not found")
        return

    await websocket.accept()
    # An attached client is what keeps a user shell out of the reaper's reach
    # (session_manager._reap_once). Without this the count stayed at zero and
    # the exemption was dead code (R04-F1).
    manager.attach_client(session_id)
    logger.info(f"WS attached to terminal session {session_id}")

    async def pump_stdout():
        """Forward PTY stdout -> WebSocket until the child exits."""
        try:
            async for chunk in session.read_chunk():
                try:
                    await websocket.send_text(json.dumps({
                        "type": "stdout",
                        "data": chunk.decode("utf-8", errors="replace"),
                    }))
                except Exception:
                    # Client went away
                    return
        finally:
            manager.touch(session_id)
        # Child exited
        exit_code = session.exit_code if session.exit_code is not None else -1
        try:
            await websocket.send_text(json.dumps({"type": "exit", "code": exit_code}))
        except Exception:
            pass

    async def pump_stdin():
        """Forward WebSocket messages -> PTY stdin/resize."""
        while True:
            msg = await websocket.receive_text()
            manager.touch(session_id)
            try:
                parsed = json.loads(msg)
            except (json.JSONDecodeError, ValueError):
                continue
            mtype = parsed.get("type")
            if mtype == "stdin":
                await session.write_stdin(parsed.get("data", ""))
            elif mtype == "resize":
                cols = int(parsed.get("cols", 80))
                rows = int(parsed.get("rows", 24))
                session.resize(cols, rows)

    stdout_task = asyncio.create_task(pump_stdout())
    stdin_task = asyncio.create_task(pump_stdin())
    try:
        # Either side closing ends the bridge
        done, pending = await asyncio.wait(
            {stdout_task, stdin_task}, return_when=asyncio.FIRST_COMPLETED
        )
        for t in pending:
            t.cancel()
    except WebSocketDisconnect:
        for t in (stdout_task, stdin_task):
            t.cancel()
    finally:
        manager.detach_client(session_id)
        logger.info(f"WS detached from terminal session {session_id}")
        # Leave the session alive for potential reattach; the reaper reclaims
        # it once it has been idle past its kind's TTL with nobody attached.


@router.websocket("/api/audio/stream")
async def audio_stream_endpoint(websocket: WebSocket):
    """Browser microphone uplink for the voice pipeline (O2).

    Binary frames of 16kHz s16le mono PCM (frontend AudioWorklet) are
    forwarded to the coordinator's dashboard ingress, which turns them
    into ``AudioChunk``s (queue-full drop-oldest) for VAD/ASR.

    The router is mounted without a prefix, so the path string above is
    the public URL. Closing with 1013 ("try again later") rather than an
    error code lets the frontend retry harmlessly when the audio pipeline
    is disabled or still booting — audio is an optional capability.
    """
    await websocket.accept()
    coordinator = getattr(websocket.app.state, "audio_coordinator", None)
    ingress = None
    if coordinator is not None:
        ingress = coordinator.get_ingress("dashboard")
    if ingress is None:
        await websocket.close(code=1013)  # try again later — pipeline disabled
        return
    await ingress.handle_websocket(websocket)


@router.websocket("/api/audio/tts")
async def tts_egress_endpoint(websocket: WebSocket, session_id: str = ""):
    """TTS egress downlink for voice sessions (O3).

    Subscribes the socket to the session's audio on the TTS egress hub; the
    agent state machine then publishes the turn's spoken Piper PCM here as
    begin / binary s16le frames / end (or cancelled). The hub is a dumb relay
    and exists even when the audio pipeline is down — only the *synthesis*
    needs the audio stack, gated on the subscriber check where it happens —
    so this route never refuses on capability grounds.

    Client -> server frames are ignored except ``{"type": "cancel"}``, the
    barge-in control frame: it fires the session's barge-in token (aborting
    in-flight synthesis) and answers with ``{"type": "cancelled"}``.
    """
    await websocket.accept()
    if not session_id:
        await websocket.close(code=4400, reason="session_id required")
        return

    # app.py aliases the singleton onto app.state; a fresh test app (or one
    # that never ran startup) falls back to the module singleton, which is
    # the same hub the state machine publishes through.
    hub = getattr(websocket.app.state, "tts_egress", None)
    if hub is None:
        from .tts_egress import get_tts_egress_hub
        hub = get_tts_egress_hub()

    unsubscribe = hub.subscribe(session_id, websocket)
    logger.info(f"TTS egress: browser subscribed to session {session_id}")
    try:
        while True:
            # Receiving keeps the connection alive and surfaces disconnects;
            # the only frame with meaning is the barge-in control frame.
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                break
            if "text" in message:
                try:
                    parsed = json.loads(message["text"])
                except (json.JSONDecodeError, ValueError):
                    continue
                if parsed.get("type") == "cancel":
                    await hub.cancel(session_id)
    except WebSocketDisconnect:
        pass
    finally:
        unsubscribe()
        logger.info(f"TTS egress: browser unsubscribed from session {session_id}")
