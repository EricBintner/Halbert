# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for the stage endpoint (Plan B: B9)."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from halbert_core.dashboard.routes.terminal import StageRequest
from halbert_core.dashboard.app import create_app


@pytest.fixture
def client():
    return TestClient(create_app())


class TestStageEndpoint:
    def test_stage_at_prompt_succeeds(self, client):
        """Staging into a shell at an empty prompt returns 200."""
        from halbert_core.dashboard.routes.terminal import get_terminal_manager
        manager = get_terminal_manager()

        # Mock a session and parser state
        mock_session = MagicMock()
        mock_session.write_stdin = AsyncMock()

        with patch.object(manager, "get", return_value=mock_session), \
             patch.object(manager, "is_at_prompt", return_value=True), \
             patch.object(manager, "touch"):
            resp = client.post(
                "/api/terminal/sessions/sess-1/stage",
                json={"command": "echo hello"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["staged"] == "echo hello"
        mock_session.write_stdin.assert_called_once_with("echo hello")

    def test_stage_when_busy_returns_409(self, client):
        """Staging into a busy shell returns 409."""
        from halbert_core.dashboard.routes.terminal import get_terminal_manager
        manager = get_terminal_manager()

        mock_session = MagicMock()

        with patch.object(manager, "get", return_value=mock_session), \
             patch.object(manager, "is_at_prompt", return_value=False):
            resp = client.post(
                "/api/terminal/sessions/sess-1/stage",
                json={"command": "echo hello"},
            )
        assert resp.status_code == 409
        assert "busy" in resp.json()["detail"].lower()

    def test_stage_unknown_session_returns_404(self, client):
        """Staging into a non-existent session returns 404."""
        from halbert_core.dashboard.routes.terminal import get_terminal_manager
        manager = get_terminal_manager()

        with patch.object(manager, "get", return_value=None):
            resp = client.post(
                "/api/terminal/sessions/no-such/stage",
                json={"command": "echo hi"},
            )
        assert resp.status_code == 404

    def test_stage_no_newline_in_command(self, client):
        """The staged command must not have a newline appended."""
        from halbert_core.dashboard.routes.terminal import get_terminal_manager
        manager = get_terminal_manager()

        mock_session = MagicMock()
        mock_session.write_stdin = AsyncMock()

        with patch.object(manager, "get", return_value=mock_session), \
             patch.object(manager, "is_at_prompt", return_value=True), \
             patch.object(manager, "touch"):
            resp = client.post(
                "/api/terminal/sessions/sess-1/stage",
                json={"command": "ls -la"},
            )
        assert resp.status_code == 200
        # Verify no newline was added
        mock_session.write_stdin.assert_called_once_with("ls -la")


class TestStageRequestModel:
    def test_command_required(self):
        with pytest.raises(Exception):
            StageRequest()

    def test_command_stored(self):
        req = StageRequest(command="echo test")
        assert req.command == "echo test"


class TestManagerIsAtPrompt:
    def test_no_parser_state_returns_false(self):
        from halbert_core.streaming.session_manager import TerminalSessionManager
        m = TerminalSessionManager()
        assert m.is_at_prompt("no-such-session") is False

    def test_at_prompt_true(self):
        from halbert_core.streaming.session_manager import TerminalSessionManager
        m = TerminalSessionManager()
        # Inject a fake session + parser state
        m._sessions["s1"] = MagicMock()
        m.update_parser_state("s1", at_prompt=True)
        assert m.is_at_prompt("s1") is True

    def test_at_prompt_false(self):
        from halbert_core.streaming.session_manager import TerminalSessionManager
        m = TerminalSessionManager()
        m._sessions["s1"] = MagicMock()
        m.update_parser_state("s1", at_prompt=False)
        assert m.is_at_prompt("s1") is False

    def test_kill_clears_parser_state(self):
        from halbert_core.streaming.session_manager import TerminalSessionManager
        m = TerminalSessionManager()
        mock_session = MagicMock()
        m._sessions["s1"] = mock_session
        m.update_parser_state("s1", at_prompt=True)
        m.kill("s1")
        assert "s1" not in m._parser_states
        assert m.is_at_prompt("s1") is False
