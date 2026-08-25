"""Tests for the terminal WebSocket bridge (B1f)."""

import json
import pytest

fastapi_ok = True
try:
    from fastapi import FastAPI
    from starlette.testclient import TestClient
except ImportError:
    fastapi_ok = False

from halbert_core.streaming.session_manager import (
    TerminalSessionManager, set_terminal_manager,
)
from halbert_core.dashboard.routes.terminal import router as terminal_router
from halbert_core.dashboard.routes.websocket import router as ws_router


class _DummyWsManager:
    """Stub app.state.ws_manager so /ws (unused here) doesn't break."""
    def connect(self, ws): pass
    def disconnect(self, ws): pass


pytestmark = pytest.mark.skipif(not fastapi_ok, reason="fastapi required")


@pytest.fixture
def app_client():
    set_terminal_manager(TerminalSessionManager(max_sessions=4))
    app = FastAPI()
    app.include_router(terminal_router, prefix="/terminal")
    app.include_router(ws_router)
    app.state.ws_manager = _DummyWsManager()
    client = TestClient(app)
    yield client
    # cleanup any leftover sessions
    mgr = set_terminal_manager(None)
    if mgr is not None:
        for s in list(mgr._sessions):
            mgr.kill(s)


def _spawn(app_client, command):
    r = app_client.post("/terminal/sessions", json={"command": command})
    assert r.status_code == 200, r.text
    return r.json()["session_id"]


def test_ws_unknown_session_closes(app_client):
    with pytest.raises(Exception):
        with app_client.websocket_connect("/ws/terminal/nope") as ws:
            ws.receive_text()


def test_ws_streams_stdout_and_exit(app_client):
    sid = _spawn(app_client, "printf 'hello\\n'")
    with app_client.websocket_connect(f"/ws/terminal/{sid}") as ws:
        msgs = []
        for _ in range(20):
            msg = ws.receive_text()
            msgs.append(json.loads(msg))
            if msgs[-1].get("type") == "exit":
                break
    types = [m.get("type") for m in msgs]
    assert "stdout" in types
    stdout_data = "".join(m["data"] for m in msgs if m["type"] == "stdout")
    assert "hello" in stdout_data
    assert "exit" in types
    exit_msgs = [m for m in msgs if m["type"] == "exit"]
    assert exit_msgs[0]["code"] == 0


def test_ws_forwards_stdin(app_client):
    # head -n 1 reads one line of stdin then exits -> stream closes cleanly
    sid = _spawn(app_client, "head -n 1")
    with app_client.websocket_connect(f"/ws/terminal/{sid}") as ws:
        ws.send_text(json.dumps({"type": "stdin", "data": "ping\n"}))
        msgs = []
        for _ in range(20):
            msg = ws.receive_text()
            msgs.append(json.loads(msg))
            if msgs[-1].get("type") == "exit":
                break
    stdout_data = "".join(m["data"] for m in msgs if m["type"] == "stdout")
    assert "ping" in stdout_data
    assert any(m["type"] == "exit" for m in msgs)


def test_ws_resize_message_accepted(app_client):
    sid = _spawn(app_client, "sleep 2")
    with app_client.websocket_connect(f"/ws/terminal/{sid}") as ws:
        ws.send_text(json.dumps({"type": "resize", "cols": 100, "rows": 30}))
        # session should still be alive; no crash
        session = __import__("halbert_core.dashboard.routes.websocket", fromlist=["get_terminal_manager"]).get_terminal_manager().get(sid)
        assert session is not None
    # kill explicitly (sleep keeps it alive)
    __import__("halbert_core.dashboard.routes.websocket", fromlist=["get_terminal_manager"]).get_terminal_manager().kill(sid)