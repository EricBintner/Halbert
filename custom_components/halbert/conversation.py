"""Halbert conversation entity for Home Assistant.

This entity implements HA's ConversationEntity interface, proxying
user messages to the Halbert Wyoming TCP agent. When a user selects
"Halbert" as their conversation agent in HA Voice Assistant settings,
messages are sent over TCP to the Halbert instance, which processes
them through its agent state machine and returns a text response.

Spatial context: HA passes the device_id of the satellite that
initiated the conversation. We resolve the device's area_id and
forward it to Halbert so it knows which room the user is in.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from homeassistant.components.conversation import (
    ConversationEntity,
    ConversationInput,
    ConversationResult,
)
from homeassistant.components.conversation.models import ConversationEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers import intent
import homeassistant.util.ulid as ulid_util

from .const import DOMAIN, CONF_HOST, CONF_PORT, ATTR_AREA_ID, ATTR_CONVERSATION_ID

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Halbert conversation entity from a config entry."""
    host = entry.data.get(CONF_HOST, "localhost")
    port = entry.data.get(CONF_PORT, 10400)
    async_add_entities([HalbertConversationEntity(hass, entry, host, port)])


class HalbertConversationEntity(ConversationEntity):
    """Halbert conversation agent entity."""

    _attr_supported_features = ConversationEntityFeature.CONTROL

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        host: str,
        port: int,
    ) -> None:
        """Initialize the conversation entity."""
        self.hass = hass
        self._entry = entry
        self._host = host
        self._port = port
        self._attr_name = "Halbert"
        self._attr_unique_id = f"{entry.entry_id}-conversation"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Halbert",
            manufacturer="Halbert",
            model="AI Home Assistant",
        )

    @property
    def supported_languages(self) -> set[str] | str:
        """Return all languages (Halbert handles language internally)."""
        return "*"

    async def _async_handle_message(
        self,
        user_input: ConversationInput,
        chat_log: Any,
    ) -> ConversationResult:
        """Handle a conversation message by proxying to Halbert's Wyoming agent."""
        _LOGGER.debug(
            "Halbert conversation: text=%s, conversation_id=%s",
            user_input.text,
            user_input.conversation_id,
        )

        # Resolve area_id from the device that initiated the conversation
        area_id = await self._resolve_area_id(user_input)

        # Send the transcript to Halbert's Wyoming TCP agent
        response_text = await self._send_to_wyoming(
            text=user_input.text,
            conversation_id=user_input.conversation_id or "",
            area_id=area_id,
        )

        # Add the response to the chat log
        chat_log.async_add_assistant_content_without_tools(
            content=response_text,
        )

        # Build the conversation result
        response = intent.IntentResponse(language=user_input.language)
        response.async_set_speech(response_text)

        return ConversationResult(
            conversation_id=user_input.conversation_id,
            response=response,
            continue_conversation=False,
        )

    async def _resolve_area_id(self, user_input: ConversationInput) -> str | None:
        """Resolve the area_id from the device that sent the message."""
        if not user_input.device_id:
            return None

        try:
            device_registry = self.hass.helpers.device_registry.async_get(self.hass)
            device = device_registry.async_get(user_input.device_id)
            if device and device.area_id:
                return device.area_id
        except Exception as e:
            _LOGGER.debug("Could not resolve area_id: %s", e)

        return None

    async def _send_to_wyoming(
        self,
        text: str,
        conversation_id: str,
        area_id: str | None,
    ) -> str:
        """Send a transcript to Halbert's Wyoming TCP agent and get the response.

        Protocol: JSONL over TCP — one JSON object per line.
        """
        message = {
            "type": "transcript",
            "data": {
                "text": text,
                "conversation_id": conversation_id,
                "context": {"area_id": area_id} if area_id else {},
            },
        }

        try:
            reader, writer = await asyncio.open_connection(self._host, self._port)
        except (OSError, ConnectionError) as e:
            _LOGGER.error("Cannot connect to Halbert Wyoming agent at %s:%s: %s",
                          self._host, self._port, e)
            return "I can't reach Halbert right now. Please check that it's running."

        try:
            writer.write((json.dumps(message) + "\n").encode("utf-8"))
            await writer.drain()

            # Read the response line
            line = await asyncio.wait_for(reader.readline(), timeout=30.0)
            if not line:
                return "Halbert didn't respond. Please try again."

            response = json.loads(line.decode("utf-8"))
            return response.get("data", {}).get("text", "I didn't get a response.")

        except TimeoutError:
            _LOGGER.warning("Timeout waiting for Halbert response")
            return "Halbert took too long to respond."
        except json.JSONDecodeError as e:
            _LOGGER.error("Invalid JSON response from Halbert: %s", e)
            return "I got an invalid response from Halbert."
        except Exception as e:
            _LOGGER.error("Error communicating with Halbert: %s", e)
            return "Something went wrong talking to Halbert."
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
