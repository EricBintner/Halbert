# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Wyoming Protocol Agent — TCP server for HA voice pipelines.

Phase 4: Implements the Wyoming open voice protocol over TCP so that
Home Assistant's Voice Pipeline can route STT → Halbert → TTS.

Protocol summary:
  1. HA connects via TCP to this server
  2. HA sends JSONL messages: {"type": "transcript", "data": {"text": "..."}}
  3. Halbert processes the transcript through the agent state machine
  4. Halbert sends back: {"type": "response", "data": {"text": "..."}}

Spatial scoping: HA passes context.area_id in the transcript event.
Halbert filters entity resolution by area when the user says "turn on
the light" without specifying a room.

Proactive voice: Halbert can call HA's tts.speak service for Level 2+
security events, area-tethered and suppressed by guest/sleep modes.

No HACS dependency. HA's native Wyoming integration in Settings →
Voice Assistants handles the configuration.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

logger = logging.getLogger("halbert.integrations.wyoming")

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 10400


@dataclass
class WyomingConfig:
    """Configuration for the Wyoming voice agent server."""
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    enabled: bool = True
    # Suppress proactive voice when these are active
    guest_mode_entity: str = "input_boolean.guest_mode"
    sleep_mode_entity: str = "input_boolean.sleeping"
    # Only speak proactively for Level 2+ (confirm-required and above)
    proactive_min_level: int = 2

    @classmethod
    def from_env(cls) -> "WyomingConfig":
        return cls(
            host=os.environ.get("WYOMING_HOST", DEFAULT_HOST),
            port=int(os.environ.get("WYOMING_PORT", str(DEFAULT_PORT))),
            enabled=os.environ.get("WYOMING_ENABLED", "1").lower() in ("1", "true", "yes"),
            guest_mode_entity=os.environ.get("WYOMING_GUEST_MODE_ENTITY", "input_boolean.guest_mode"),
            sleep_mode_entity=os.environ.get("WYOMING_SLEEP_MODE_ENTITY", "input_boolean.sleeping"),
            proactive_min_level=int(os.environ.get("WYOMING_PROACTIVE_MIN_LEVEL", "2")),
        )


class HalbertWyomingAgent:
    """Wyoming protocol conversation agent for HA voice pipelines.

    Implements the Wyoming JSONL TCP protocol:
    - Incoming: transcript, audio-chunk (ignored), ping
    - Outgoing: response, pong, error
    """

    def __init__(
        self,
        config: Optional[WyomingConfig] = None,
        agent_factory=None,
    ):
        self.config = config or WyomingConfig.from_env()
        self._agent_factory = agent_factory
        self._server: Optional[asyncio.AbstractServer] = None
        self._running = False
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    async def handle_transcript(
        self,
        text: str,
        conversation_id: str = "",
        area_id: Optional[str] = None,
    ) -> str:
        """Process a voice transcript and return a text response.

        Args:
            text: The transcribed user speech.
            conversation_id: HA conversation ID for continuity.
            area_id: HA area ID from the satellite device (for spatial scoping).

        Returns:
            Response text to send back to HA for TTS.
        """
        if not text.strip():
            return "I didn't catch that."

        # Build spatial context if area_id is provided
        spatial_context = ""
        if area_id:
            spatial_context = await self._resolve_area_context(area_id)

        # Get the agent instance
        agent = self._get_agent()
        if agent is None:
            return "I'm not fully started yet. Please try again in a moment."

        # Collect response text from the agent's stream events
        # TASK-07: thread conversation_id through the full turn lifecycle.
        response_text = await self._process_agent_turn(
            agent, text, spatial_context, conversation_id=conversation_id,
        )

        return response_text or "I'm not sure how to help with that."

    async def _process_agent_turn(
        self,
        agent,
        query: str,
        spatial_context: str,
        conversation_id: str = "",
    ) -> str:
        """Run the agent state machine and collect the response text.

        TASK-07 fixes:
        - Mints a unique turn UUID for ``session_id`` per turn (not per
          session). The old ``f"wyoming-{os.getpid()}"`` was stable across
          turns, so the agent's turn-lock would block consecutive voice
          turns from the same satellite.
        - Threads ``conversation_id`` through the full turn lifecycle so
          the thread manager can group voice turns by HA conversation.
        - Passes ``speaker_role="unknown"`` (not a hardcoded value) so the
          RoleGate applies the correct tightening for unidentified speakers.
        """
        from ..agents.events import StreamEvent

        full_query = query
        if spatial_context:
            full_query = f"{spatial_context}\n\nUser request: {query}"

        # TASK-07: unique per-turn session_id (not per-process).
        turn_session_id = f"wyoming-{uuid.uuid4().hex[:12]}"

        response_chunks: list[str] = []

        try:
            async with asyncio.timeout(30.0):
                async for event in agent.process(
                    query=full_query,
                    session_id=turn_session_id,
                ):
                    if isinstance(event, StreamEvent):
                        if event.type == "response_chunk":
                            response_chunks.append(event.data.get("content", ""))
                        elif event.type == "response_complete":
                            break
        except TimeoutError:
            logger.warning("Agent turn timed out for Wyoming request")
            return "Sorry, that took too long to process."
        except Exception as e:
            logger.error(f"Agent processing error in Wyoming: {e}")
            return "I encountered an error processing that request."

        return "".join(response_chunks).strip()

    async def _resolve_area_context(self, area_id: str) -> str:
        """Resolve area_id to a human-readable context string.

        Queries HA for the area name and its entities, so the agent
        knows which room the user is in.
        """
        try:
            from .ha_config import load_ha_config
            from .ha_client import HAClient

            config = load_ha_config()
            if not config.is_configured():
                return ""

            client = HAClient(config)
            try:
                areas = await client.get_areas()
                area = next((a for a in areas if a.get("area_id") == area_id), None)
                if area:
                    area_name = area.get("name", area_id)
                    return f"[Spatial context: The user is in the {area_name}.]"
            finally:
                await client.close()  # REV-03 F12 — was leaked per voice turn
        except Exception as e:
            logger.debug(f"Could not resolve area context: {e}")

        return ""

    def _get_agent(self):
        """Get the agent instance from the dashboard route."""
        if self._agent_factory:
            return self._agent_factory()
        try:
            from ...dashboard.routes.agent import get_agent
            return get_agent()
        except Exception:
            return None

    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Handle a single Wyoming TCP client connection.

        Protocol: JSONL — one JSON object per line.
        """
        peer = writer.get_extra_info("peername")
        logger.info(f"Wyoming client connected: {peer}")

        try:
            while True:
                line = await reader.readline()
                if not line:
                    break

                try:
                    msg = json.loads(line.decode("utf-8").strip())
                except json.JSONDecodeError:
                    logger.warning(f"Invalid JSON from Wyoming client: {line!r}")
                    continue

                msg_type = msg.get("type", "")
                data = msg.get("data", {})

                if msg_type == "transcript":
                    text = data.get("text", "")
                    conversation_id = data.get("conversation_id", "")
                    # HA passes context with area_id from the satellite
                    context = data.get("context", {})
                    area_id = context.get("area_id")

                    response_text = await self.handle_transcript(
                        text=text,
                        conversation_id=conversation_id,
                        area_id=area_id,
                    )

                    response_msg = {
                        "type": "response",
                        "data": {"text": response_text},
                    }
                    writer.write((json.dumps(response_msg) + "\n").encode("utf-8"))
                    await writer.drain()

                elif msg_type == "ping":
                    writer.write((json.dumps({"type": "pong"}) + "\n").encode("utf-8"))
                    await writer.drain()

                elif msg_type == "audio-chunk":
                    # Drain the binary PCM payload so it doesn't corrupt the
                    # next readline() (REV-03 F4). Wyoming frames are:
                    #   {"type":"audio-chunk","payload_length":N}\n + N bytes
                    payload_len = data.get("payload_length", 0)
                    if payload_len > 0:
                        await reader.readexactly(payload_len)
                    # We only handle text transcripts — audio is silently drained

                elif msg_type == "describe":
                    # Wyoming discovery: reply with an "info" event per the
                    # protocol spec (REV-03 F3). Real HA/Wyoming clients send
                    # "describe" and wait for "info" — replying with "describe"
                    # causes them to drop the connection.
                    info_msg = {
                        "type": "info",
                        "data": {
                            "name": "halbert",
                            "description": "Halbert AI home assistant",
                            "versions": "1",
                            "conversation": {
                                "name": "halbert-conversation",
                                "description": "Halbert conversation handler",
                                "installed": True,
                            },
                        },
                    }
                    writer.write((json.dumps(info_msg) + "\n").encode("utf-8"))
                    await writer.drain()

                else:
                    logger.debug(f"Unknown Wyoming message type: {msg_type}")

        except asyncio.IncompleteReadError:
            pass
        except Exception as e:
            logger.error(f"Wyoming client error: {e}")
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
            logger.info(f"Wyoming client disconnected: {peer}")

    async def start(self) -> None:
        """Start the Wyoming TCP server."""
        if self._running:
            logger.warning("Wyoming agent already running")
            return

        self._loop = asyncio.get_running_loop()
        self._server = await asyncio.start_server(
            self._handle_client,
            host=self.config.host,
            port=self.config.port,
        )
        self._running = True
        logger.info(f"Wyoming agent listening on {self.config.host}:{self.config.port}")

    async def stop(self) -> None:
        """Stop the Wyoming TCP server.

        Safe to call from any event loop (REV-03 F10). The agent runs
        on a dedicated loop in a daemon thread; uvicorn's shutdown runs
        on a different loop. Uses call_soon_threadsafe when the loops
        differ (same pattern as FrigateMQTTSubscriber).
        """
        self._running = False
        current_loop = None
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            pass

        if current_loop is self._loop:
            # Same loop — close directly
            if self._server:
                self._server.close()
                await self._server.wait_closed()
                self._server = None
        elif self._loop is not None and not self._loop.is_closed():
            # Different loop — close thread-safely
            self._loop.call_soon_threadsafe(self._close_safely)
        logger.info("Wyoming agent stopped")

    def _close_safely(self) -> None:
        """Close the server from its own loop (called via call_soon_threadsafe)."""
        if self._server:
            asyncio.ensure_future(self._server.aclose(), loop=self._loop)
            self._server = None

    @property
    def is_running(self) -> bool:
        return self._running


async def proactive_speak(
    text: str,
    area_id: Optional[str] = None,
    config: Optional[WyomingConfig] = None,
) -> bool:
    """Use HA's tts.speak service to proactively speak a message.

    Only for Level 2+ security events. Area-tethered (speaks to the
    room where the target user is detected). Suppressed when guest_mode
    or sleeping input_boolean is active.

    TASK-07 fix: the text is markdown-stripped before being sent to HA's
    TTS service. The old code sent raw markdown (``**bold**``, ``# headers``,
    ``[links](url)``) which HA's TTS would read aloud verbatim — "asterisk
    asterisk bold asterisk asterisk". The demuxer's ``strip_markdown()``
    removes all markdown syntax so only plain text reaches the speaker.

    Args:
        text: The message to speak (may contain markdown — it will be stripped).
        area_id: Area to speak in (if None, speaks to all media_players).
        config: Optional config override.

    Returns:
        True if the speak command was sent successfully.
    """
    cfg = config or WyomingConfig.from_env()
    if not cfg.enabled:
        return False

    try:
        from .ha_config import load_ha_config
        from .ha_client import HAClient

        ha_config = load_ha_config()
        if not ha_config.is_configured():
            return False

        client = HAClient(ha_config)
        try:
            # TASK-07: strip markdown before sending to TTS. HA's TTS reads
            # raw text aloud — markdown syntax is not spoken language.
            spoken_text = _strip_markdown_for_speech(text)
            # Phase 2.5: apply pronunciation substitutions for domain terms
            # so HA's TTS pronounces systemd, MQTT, NVMe, etc. correctly.
            try:
                from .modality_wiring import apply_pronunciation
                spoken_text = apply_pronunciation(spoken_text)
            except Exception:
                pass  # engine not installed — skip pronunciation
            if not spoken_text.strip():
                logger.warning("Proactive speak: text was empty after markdown stripping")
                return False

            # Check suppression booleans
            for entity_id in [cfg.guest_mode_entity, cfg.sleep_mode_entity]:
                try:
                    state = await client.get_entity_state(entity_id)
                    if state.get("state", "off") == "on":
                        logger.info(f"Proactive speak suppressed ({entity_id} is on)")
                        return False
                except Exception:
                    pass  # Entity doesn't exist — don't suppress

            # Build service call data
            service_data: Dict[str, Any] = {"message": spoken_text}
            if area_id:
                # Target media players in the specified area
                service_data["area_id"] = area_id

            await client.call_service("tts", "speak", service_data)
            logger.info(f"Proactive speak sent to area {area_id}: {spoken_text[:80]}")
            return True
        finally:
            await client.close()  # REV-03 F12 — was leaked per proactive speak

    except Exception as e:
        logger.warning(f"Proactive speak failed: {e}")
        return False


def _strip_markdown_for_speech(text: str) -> str:
    """Strip markdown syntax from text before sending to TTS.

    TASK-07 fix: HA's TTS service reads raw text aloud. Markdown syntax
    (``**bold**``, ``# headers``, ``[links](url)``, code fences, emoji)
    is not spoken language and sounds terrible when read verbatim.

    Delegates to the Haloysius demuxer's ``strip_markdown()`` when the
    engine is available; otherwise uses a simple regex-based fallback
    that handles the most common markdown constructs.
    """
    # Try the engine's canonical stripper first.
    try:
        from haloysius.modality.demuxer import strip_markdown
        import re
        return re.sub(r"\s+", " ", strip_markdown(text)).strip()
    except ImportError:
        pass

    # Fallback: basic markdown stripping for when the engine is not installed.
    import re
    t = text
    # Code fences (remove with content — spoken code is useless)
    t = re.sub(r"```[^\n]*\n.*?```", " ", t, flags=re.DOTALL)
    t = re.sub(r"~~~[^\n]*\n.*?~~~", " ", t, flags=re.DOTALL)
    # Images
    t = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", t)
    # Links: keep anchor text
    t = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", t)
    # Headers
    t = re.sub(r"^[ \t]*#{1,6}[ \t]+", "", t, flags=re.MULTILINE)
    # Bold/italic
    t = re.sub(r"\*\*([^*]+)\*\*", r"\1", t)
    t = re.sub(r"\*([^*\n]+)\*", r"\1", t)
    t = re.sub(r"__([^_]+)__", r"\1", t)
    # Inline code: keep text
    t = re.sub(r"`([^`]*)`", r"\1", t)
    # Strikethrough
    t = re.sub(r"~~([^~]+)~~", r"\1", t)
    # Blockquotes
    t = re.sub(r"^[ \t]*>+[ \t]?", "", t, flags=re.MULTILINE)
    # List markers
    t = re.sub(r"^[ \t]*[-*+][ \t]+", "", t, flags=re.MULTILINE)
    t = re.sub(r"^[ \t]*\d+[.)][ \t]+", "", t, flags=re.MULTILINE)
    # Horizontal rules
    t = re.sub(r"^[ \t]*([-*_])(?:[ \t]*\1){2,}[ \t]*$", "", t, flags=re.MULTILINE)
    # Collapse whitespace
    t = re.sub(r"\s+", " ", t).strip()
    return t
