# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Unit tests for Phase 4 Wyoming voice agent."""

import asyncio
import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from halbert_core.integrations.wyoming_agent import (
    HalbertWyomingAgent,
    WyomingConfig,
    proactive_speak,
)


class TestWyomingConfig:
    def test_from_env_defaults(self):
        """R9-F01: the defaults must not open agent turns to the network.

        This used to bind 0.0.0.0 and start automatically, so every install
        accepted a transcript from anyone who could reach port 10400 and ran
        it at speaker_role="unknown" — whose RoleGate cap is MEDIUM with no
        confirmation. Reaching a satellite on another host is now something
        the operator asks for, with a token.
        """
        config = WyomingConfig.from_env()
        assert config.host == "127.0.0.1"
        assert config.port == 10400
        assert config.enabled is False
        assert config.is_loopback_only is True
        assert config.require_token is False  # loopback needs no secret
        assert config.guest_mode_entity == "input_boolean.guest_mode"
        assert config.sleep_mode_entity == "input_boolean.sleeping"
        assert config.proactive_min_level == 2

    def test_a_public_bind_requires_a_token(self):
        config = WyomingConfig(host="0.0.0.0")
        assert config.is_loopback_only is False
        assert config.require_token is True

    def test_from_env_custom(self):
        with patch.dict(os.environ, {
            "WYOMING_HOST": "127.0.0.1",
            "WYOMING_PORT": "10401",
            "WYOMING_ENABLED": "false",
            "WYOMING_GUEST_MODE_ENTITY": "input_boolean.visitors",
            "WYOMING_SLEEP_MODE_ENTITY": "input_boolean.do_not_disturb",
            "WYOMING_PROACTIVE_MIN_LEVEL": "3",
        }):
            config = WyomingConfig.from_env()
            assert config.host == "127.0.0.1"
            assert config.port == 10401
            assert config.enabled is False
            assert config.guest_mode_entity == "input_boolean.visitors"
            assert config.sleep_mode_entity == "input_boolean.do_not_disturb"
            assert config.proactive_min_level == 3


class TestHalbertWyomingAgent:
    def test_init_defaults(self):
        agent = HalbertWyomingAgent()
        assert agent.config.port == 10400
        assert agent.is_running is False

    def test_init_with_config(self):
        config = WyomingConfig(host="127.0.0.1", port=10401)
        agent = HalbertWyomingAgent(config=config)
        assert agent.config.host == "127.0.0.1"
        assert agent.config.port == 10401

    @pytest.mark.asyncio
    async def test_handle_transcript_empty(self):
        agent = HalbertWyomingAgent()
        result = await agent.handle_transcript("")
        assert "didn't catch that" in result

    @pytest.mark.asyncio
    async def test_handle_transcript_no_agent(self):
        agent = HalbertWyomingAgent(agent_factory=lambda: None)
        result = await agent.handle_transcript("turn on the light")
        assert "not fully started" in result

    @pytest.mark.asyncio
    async def test_handle_transcript_with_mock_agent(self):
        """Test that transcript events are processed and response text is collected."""
        from halbert_core.agents.events import StreamEvent

        # Real StreamEvents: _process_agent_turn filters with
        # isinstance(event, StreamEvent), which a MagicMock is not.
        mock_event = StreamEvent(type="response_chunk", session_id="t", data={"content": "The light is on."})
        mock_complete = StreamEvent(type="response_complete", session_id="t", data={})

        async def mock_process(*args, **kwargs):
            yield mock_event
            yield mock_complete

        mock_agent = MagicMock()
        mock_agent.process = mock_process

        agent = HalbertWyomingAgent(agent_factory=lambda: mock_agent)
        result = await agent.handle_transcript("turn on the light")
        assert result == "The light is on."

    @pytest.mark.asyncio
    async def test_handle_transcript_with_area_context(self):
        """Test that area_id triggers spatial context resolution."""
        from halbert_core.agents.events import StreamEvent

        mock_event = StreamEvent(type="response_chunk", session_id="t", data={"content": "Done."})
        mock_complete = StreamEvent(type="response_complete", session_id="t", data={})

        async def mock_process(*args, **kwargs):
            yield mock_event
            yield mock_complete

        mock_agent = MagicMock()
        mock_agent.process = mock_process

        agent = HalbertWyomingAgent(agent_factory=lambda: mock_agent)

        with patch.object(agent, "_resolve_area_context", new_callable=AsyncMock) as mock_area:
            mock_area.return_value = "[Spatial context: The user is in the Kitchen.]"
            result = await agent.handle_transcript("turn on the light", area_id="kitchen")
            assert result == "Done."
            mock_area.assert_called_once_with("kitchen")

    @pytest.mark.asyncio
    async def test_handle_transcript_timeout(self, monkeypatch):
        """Test that agent timeout returns a graceful message."""
        from halbert_core.integrations import wyoming_agent as wyoming_mod

        # Shrink the turn ceiling so the test does not wait the real 30s.
        monkeypatch.setattr(wyoming_mod, "TURN_TIMEOUT_S", 0.1)

        async def mock_process(*args, **kwargs):
            await asyncio.sleep(60)  # Exceeds the (patched) timeout
            yield MagicMock()

        mock_agent = MagicMock()
        mock_agent.process = mock_process

        agent = HalbertWyomingAgent(agent_factory=lambda: mock_agent)
        result = await agent.handle_transcript("test")
        assert "too long" in result.lower()

    @pytest.mark.asyncio
    async def test_start_stop(self):
        """Test TCP server start and stop."""
        config = WyomingConfig(host="127.0.0.1", port=10499)
        agent = HalbertWyomingAgent(config=config)

        await agent.start()
        assert agent.is_running is True

        await agent.stop()
        assert agent.is_running is False

    @pytest.mark.asyncio
    async def test_start_idempotent(self):
        config = WyomingConfig(host="127.0.0.1", port=10498)
        agent = HalbertWyomingAgent(config=config)

        await agent.start()
        await agent.start()  # Should not raise
        assert agent.is_running is True

        await agent.stop()

    @pytest.mark.asyncio
    async def test_stop_when_not_running(self):
        agent = HalbertWyomingAgent()
        await agent.stop()  # Should not raise
        assert agent.is_running is False


class TestWyomingClientHandler:
    """Tests for the TCP JSONL protocol handler."""

    @pytest.mark.asyncio
    async def test_transcript_message(self):
        """Test that a transcript message produces a response."""
        config = WyomingConfig(host="127.0.0.1", port=10497)
        agent = HalbertWyomingAgent(config=config)

        # Mock handle_transcript
        with patch.object(agent, "handle_transcript", new_callable=AsyncMock) as mock_handler:
            mock_handler.return_value = "The light is on."

            await agent.start()
            try:
                reader, writer = await asyncio.open_connection("127.0.0.1", 10497)

                # Send a transcript message
                msg = json.dumps({
                    "type": "transcript",
                    "data": {"text": "turn on the light", "context": {"area_id": "living_room"}},
                })
                writer.write((msg + "\n").encode("utf-8"))
                await writer.drain()

                # Read response
                line = await asyncio.wait_for(reader.readline(), timeout=5.0)
                response = json.loads(line.decode("utf-8"))

                assert response["type"] == "response"
                assert response["data"]["text"] == "The light is on."

                writer.close()
                await writer.wait_closed()
            finally:
                await agent.stop()

    @pytest.mark.asyncio
    async def test_ping_pong(self):
        config = WyomingConfig(host="127.0.0.1", port=10496)
        agent = HalbertWyomingAgent(config=config)

        await agent.start()
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", 10496)

            msg = json.dumps({"type": "ping"})
            writer.write((msg + "\n").encode("utf-8"))
            await writer.drain()

            line = await asyncio.wait_for(reader.readline(), timeout=5.0)
            response = json.loads(line.decode("utf-8"))

            assert response["type"] == "pong"

            writer.close()
            await writer.wait_closed()
        finally:
            await agent.stop()

    @pytest.mark.asyncio
    async def test_describe_message(self):
        config = WyomingConfig(host="127.0.0.1", port=10495)
        agent = HalbertWyomingAgent(config=config)

        await agent.start()
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", 10495)

            msg = json.dumps({"type": "describe"})
            writer.write((msg + "\n").encode("utf-8"))
            await writer.drain()

            line = await asyncio.wait_for(reader.readline(), timeout=5.0)
            response = json.loads(line.decode("utf-8"))

            assert response["type"] == "info"  # REV-03 F3: spec-mandated info reply
            assert response["data"]["name"] == "halbert"
            assert "conversation" in response["data"]

            writer.close()
            await writer.wait_closed()
        finally:
            await agent.stop()

    @pytest.mark.asyncio
    async def test_a_malformed_frame_drops_the_connection(self):
        """Wyoming framing is a JSON header plus optional binary payload, so
        a header this server cannot parse means it no longer knows where the
        next frame begins. It used to skip the line and keep reading, which
        on a binary protocol risks reading payload bytes as commands — on a
        port that runs agent turns. It now closes and lets the client
        reconnect at a known boundary."""
        config = WyomingConfig(host="127.0.0.1", port=10494)
        agent = HalbertWyomingAgent(config=config)

        await agent.start()
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", 10494)

            writer.write(b"not valid json\n")
            await writer.drain()
            writer.write((json.dumps({"type": "ping"}) + "\n").encode("utf-8"))
            await writer.drain()

            # EOF, not a pong.
            line = await asyncio.wait_for(reader.readline(), timeout=5.0)
            assert line == b""

            writer.close()
            await writer.wait_closed()
        finally:
            await agent.stop()


class TestWyomingAuthAndFraming:
    """R9-F01 and R3-F04: who may drive a turn, and how frames are read."""

    @pytest.mark.asyncio
    async def test_a_public_bind_without_a_token_refuses_to_start(self):
        agent = HalbertWyomingAgent(config=WyomingConfig(host="0.0.0.0", port=10492))
        with pytest.raises(RuntimeError, match="shared secret"):
            await agent.start()
        assert agent.is_running is False

    @pytest.mark.asyncio
    async def test_a_transcript_before_authenticating_is_refused(self):
        config = WyomingConfig(host="0.0.0.0", port=10491, auth_token="s3cret")
        agent = HalbertWyomingAgent(config=config)
        await agent.start()
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", 10491)
            writer.write((json.dumps({
                "type": "transcript", "data": {"text": "unlock the front door"},
            }) + "\n").encode("utf-8"))
            await writer.drain()

            line = await asyncio.wait_for(reader.readline(), timeout=5.0)
            assert json.loads(line.decode())["type"] == "error"
            # And the connection is closed, not left open to try again.
            assert await asyncio.wait_for(reader.readline(), timeout=5.0) == b""
            writer.close()
            await writer.wait_closed()
        finally:
            await agent.stop()

    @pytest.mark.asyncio
    async def test_a_wrong_token_is_refused(self):
        config = WyomingConfig(host="0.0.0.0", port=10490, auth_token="s3cret")
        agent = HalbertWyomingAgent(config=config)
        await agent.start()
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", 10490)
            writer.write((json.dumps({
                "type": "authenticate", "data": {"token": "s3cre"},
            }) + "\n").encode("utf-8"))
            await writer.drain()
            line = await asyncio.wait_for(reader.readline(), timeout=5.0)
            assert json.loads(line.decode())["type"] == "error"
            writer.close()
            await writer.wait_closed()
        finally:
            await agent.stop()

    @pytest.mark.asyncio
    async def test_the_right_token_opens_the_connection(self):
        config = WyomingConfig(host="0.0.0.0", port=10489, auth_token="s3cret")
        agent = HalbertWyomingAgent(config=config)
        await agent.start()
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", 10489)
            writer.write((json.dumps({
                "type": "authenticate", "data": {"token": "s3cret"},
            }) + "\n").encode("utf-8"))
            await writer.drain()
            assert json.loads((await asyncio.wait_for(reader.readline(), 5.0)).decode())["type"] == "authenticated"

            writer.write((json.dumps({"type": "ping"}) + "\n").encode("utf-8"))
            await writer.drain()
            assert json.loads((await asyncio.wait_for(reader.readline(), 5.0)).decode())["type"] == "pong"
            writer.close()
            await writer.wait_closed()
        finally:
            await agent.stop()

    @pytest.mark.asyncio
    async def test_an_audio_chunk_does_not_desynchronise_the_stream(self):
        """R3-F04. payload_length rides on the HEADER, not in data{}. Reading
        it from data{} meant the PCM was never drained, so the next
        readline() parsed raw audio as JSON: one canonical audio-chunk frame
        produced eight "Invalid JSON" warnings and no pong."""
        config = WyomingConfig(host="127.0.0.1", port=10488)
        agent = HalbertWyomingAgent(config=config)
        await agent.start()
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", 10488)

            pcm = bytes(range(256)) * 4  # 1024 bytes that look nothing like JSON
            header = json.dumps({
                "type": "audio-chunk",
                "data": {"rate": 16000, "width": 2, "channels": 1},
                "payload_length": len(pcm),
            })
            writer.write((header + "\n").encode("utf-8") + pcm)
            await writer.drain()

            writer.write((json.dumps({"type": "ping"}) + "\n").encode("utf-8"))
            await writer.drain()

            line = await asyncio.wait_for(reader.readline(), timeout=5.0)
            assert json.loads(line.decode())["type"] == "pong"
            writer.close()
            await writer.wait_closed()
        finally:
            await agent.stop()


class TestSatelliteRepliesAreSpeakable:
    """U2-05: what goes back to HA is read aloud verbatim."""

    @pytest.mark.asyncio
    async def test_markdown_is_stripped_from_the_turn_reply(self):
        from halbert_core.agents.events import StreamEvent

        markdown = "## Samba shares\n\nEdit **/etc/samba/smb.conf**, then `systemctl restart smbd`."

        class _Agent:
            async def process(self, *args, **kwargs):
                yield StreamEvent(
                    type="response_chunk", session_id="s", timestamp=0,
                    data={"content": markdown},
                )
                yield StreamEvent(
                    type="response_complete", session_id="s", timestamp=0, data={},
                )

        wyoming = HalbertWyomingAgent(config=WyomingConfig(host="127.0.0.1"))
        spoken = await wyoming._process_agent_turn(
            _Agent(), "how do I share a folder", spatial_context="",
        )

        assert "##" not in spoken
        assert "**" not in spoken
        assert "`" not in spoken
        assert "Samba shares" in spoken
        assert "/etc/samba/smb.conf" in spoken


class TestProactiveSpeak:
    @pytest.mark.asyncio
    async def test_disabled_returns_false(self):
        config = WyomingConfig(enabled=False)
        result = await proactive_speak("test message", config=config)
        assert result is False

    @pytest.mark.asyncio
    async def test_ha_not_configured(self):
        config = WyomingConfig(enabled=True)
        with patch("halbert_core.integrations.home_assistant.ha_config.load_ha_config") as mock_load:
            mock_config = MagicMock()
            mock_config.is_configured.return_value = False
            mock_load.return_value = mock_config
            result = await proactive_speak("test", config=config)
        assert result is False

    @pytest.mark.asyncio
    async def test_suppressed_by_guest_mode(self):
        config = WyomingConfig(enabled=True, guest_mode_entity="input_boolean.guest_mode")
        with patch("halbert_core.integrations.home_assistant.ha_config.load_ha_config") as mock_load:
            mock_config = MagicMock()
            mock_config.is_configured.return_value = True
            mock_load.return_value = mock_config

            with patch("halbert_core.integrations.home_assistant.ha_client.HAClient") as mock_client_cls:
                mock_client = MagicMock()
                mock_client.get_entity_state = AsyncMock(return_value={"state": "on"})
                mock_client.close = AsyncMock()
                mock_client_cls.return_value = mock_client

                result = await proactive_speak("alert", config=config)
        assert result is False

    @pytest.mark.asyncio
    async def test_successful_speak(self):
        config = WyomingConfig(enabled=True)
        with patch("halbert_core.integrations.home_assistant.ha_config.load_ha_config") as mock_load:
            mock_config = MagicMock()
            mock_config.is_configured.return_value = True
            mock_load.return_value = mock_config

            with patch("halbert_core.integrations.home_assistant.ha_client.HAClient") as mock_client_cls:
                mock_client = MagicMock()
                mock_client.get_entity_state = AsyncMock(return_value={"state": "off"})
                mock_client.call_service = AsyncMock(return_value={"success": True})
                mock_client.close = AsyncMock()
                mock_client_cls.return_value = mock_client

                result = await proactive_speak("Front door unlocked", area_id="living_room", config=config)
        assert result is True
        mock_client.call_service.assert_called_once_with(
            "tts", "speak", {"message": "Front door unlocked", "area_id": "living_room"}
        )

    @pytest.mark.asyncio
    async def test_speak_without_area(self):
        config = WyomingConfig(enabled=True)
        with patch("halbert_core.integrations.home_assistant.ha_config.load_ha_config") as mock_load:
            mock_config = MagicMock()
            mock_config.is_configured.return_value = True
            mock_load.return_value = mock_config

            with patch("halbert_core.integrations.home_assistant.ha_client.HAClient") as mock_client_cls:
                mock_client = MagicMock()
                mock_client.get_entity_state = AsyncMock(return_value={"state": "off"})
                mock_client.call_service = AsyncMock(return_value={"success": True})
                mock_client.close = AsyncMock()
                mock_client_cls.return_value = mock_client

                result = await proactive_speak("Alert", config=config)
        assert result is True
        call_args = mock_client.call_service.call_args
        assert "area_id" not in call_args[0][2]
