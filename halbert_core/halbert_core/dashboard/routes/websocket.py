# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
WebSocket routes.

- ``/ws``: existing dashboard real-time update channel (unchanged).
- ``/ws/terminal/{session_id}`` (B1f): bidirectional bridge to a PTY session.

  Message protocol (JSON, both directions):
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
        logger.info(f"WS detached from terminal session {session_id}")
        # Leave the session alive for potential reattach; reaper reclaims idle.
