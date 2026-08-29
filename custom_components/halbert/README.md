# Halbert — Home Assistant Custom Integration (HACS)

This custom integration lets you use **Halbert** as your conversation agent in Home Assistant's Voice Assistant settings.

## Requirements

- A running Halbert instance with the Wyoming voice agent enabled (`WYOMING_ENABLED=1`, default port 10400)
- Home Assistant 2024.1+ (for ConversationEntity support)

## Installation via HACS

1. Open HACS in your Home Assistant instance
2. Go to **Integrations**
3. Click the three dots in the top right → **Custom repositories**
4. Add this repository URL: `https://github.com/EricBintner/Halbert`
5. Select **Integration** as the category
6. Click **Add**
7. Search for "Halbert" and install it
8. Restart Home Assistant

## Configuration

1. Go to **Settings → Devices & Services**
2. Click **Add Integration**
3. Search for "Halbert"
4. Enter the host and port of your Halbert Wyoming agent (default: `localhost:10400`)
5. Click **Submit**

## Usage

1. Go to **Settings → Voice Assistants**
2. Create or edit a voice assistant
3. Select **Halbert** as the conversation agent
4. Now any voice command sent through HA's voice pipeline (Wyoming satellite, Assist API, etc.) will be routed to Halbert

## How It Works

```
User speaks → HA Voice Pipeline (STT) → Halbert Conversation Entity
    → TCP JSONL to Halbert Wyoming Agent (port 10400)
    → Halbert Agent State Machine processes the request
    → Response text returned to HA
    → HA Voice Pipeline (TTS) speaks the response
```

Spatial context: When a voice command comes from a satellite device in a specific room, HA passes the device's `area_id` to Halbert, which uses it to resolve entity references like "turn on the light" (without specifying which room).
