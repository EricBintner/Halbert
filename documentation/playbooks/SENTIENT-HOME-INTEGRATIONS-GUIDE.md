# Sentient Home Integrations & Guided Setup Playbook

**Date:** 2026-08-29  
**Audience:** Halbert Autonomous Agent, Sysadmins, and Smart Home Enthusiasts  
**Purpose:** End-to-end operational instructions for deploying, configuring, and connecting Home Assistant, Frigate NVR, Bermuda BLE presence tracking, and per-room lighting.

---

## 1. Overview: The Connected Sentient Stack

Halbert acts as the **cognitive and orchestration mind** of the residence. It connects to specialized local services over private local networks (or Tailscale):

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          HALBERT COGNITIVE CORE                             │
│                     (PersonaCognition + Agent Engine)                       │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
            ┌──────────────────────────┴──────────────────────────┐
            │                                                     │
            ▼                                                     ▼
┌───────────────────────────────┐             ┌───────────────────────────────┐
│     HOME ASSISTANT CORE       │             │         FRIGATE NVR           │
│     (Sensors & Actuators)     │             │     (Ocular Perception)       │
├───────────────────────────────┤             ├───────────────────────────────┤
│ • Area Registry (Rooms)       │             │ • RTSP Stream Ingestion       │
│ • Zigbee / Z-Wave / ESPHome   │             │ • Coral Edge TPU / GPU YOLO   │
│ • Bermuda BLE Presence        │             │ • MQTT Event Broker           │
│ • Adaptive Lighting           │             │ • Zone Object Tracking        │
└───────────────────────────────┘             └───────────────────────────────┘
```

---

## 2. Playbook 1: Home Assistant Setup & Token Generation

### Option A: Guided Deployment via Docker Compose
If Home Assistant is not yet installed on the server, Halbert can execute this deployment:

```bash
mkdir -p /opt/homeassistant/config
cat << 'EOF' > /opt/homeassistant/docker-compose.yml
services:
  homeassistant:
    container_name: homeassistant
    image: "ghcr.io/home-assistant/home-assistant:stable"
    volumes:
      - /opt/homeassistant/config:/config
      - /etc/localtime:/etc/localtime:ro
    restart: unless-stopped
    privileged: true
    network_mode: host
EOF
docker compose -f /opt/homeassistant/docker-compose.yml up -d
```

### Option B: Long-Lived Access Token Generation
1. Navigate to Home Assistant web interface (`http://<server-ip>:8123`).
2. Click your user profile in the bottom-left corner.
3. Scroll to **Long-Lived Access Tokens** $\rightarrow$ Click **Create Token**.
4. Name the token `"Halbert Intelligence"`.
5. Copy the generated token string.

### Option C: Connecting to Halbert
In Halbert's **Settings > Home & Space**:
- **Server URL:** `http://localhost:8123` (or `http://homeassistant.local:8123`)
- **Access Token:** Paste the long-lived token.
- **Auto-sync:** Check `[x] Auto-sync Areas, Devices, and Entities`.

---

## 3. Playbook 2: Frigate NVR Setup & MQTT Wiring

### Step 1: Deploy Mosquitto MQTT & Frigate Stack
```bash
mkdir -p /opt/frigate/config /opt/frigate/storage /opt/mosquitto/config /opt/mosquitto/data

# Mosquitto config
cat << 'EOF' > /opt/mosquitto/config/mosquitto.conf
listener 1883
allow_anonymous true
persistence true
persistence_location /mosquitto/data/
EOF

# Frigate Compose
cat << 'EOF' > /opt/frigate/docker-compose.yml
services:
  mosquitto:
    image: eclipse-mosquitto:2
    container_name: mosquitto
    restart: unless-stopped
    ports:
      - "1883:1883"
    volumes:
      - /opt/mosquitto/config:/mosquitto/config
      - /opt/mosquitto/data:/mosquitto/data

  frigate:
    container_name: frigate
    privileged: true
    restart: unless-stopped
    image: ghcr.io/blakeblackshear/frigate:stable
    shm_size: "128mb"
    devices:
      - /dev/bus/usb:/dev/bus/usb
      - /dev/dri/renderD128:/dev/dri/renderD128
    volumes:
      - /etc/localtime:/etc/localtime:ro
      - /opt/frigate/config:/config
      - /opt/frigate/storage:/media/frigate
      - type: tmpfs
        target: /tmp/cache
        tmpfs:
          size: 1000000000
    ports:
      - "5000:5000"
      - "8554:8554"
      - "8555:8555/tcp"
      - "8555:8555/udp"
EOF
docker compose -f /opt/frigate/docker-compose.yml up -d
```

### Step 2: Frigate Camera Configuration (`/opt/frigate/config/config.yml`)
```yaml
mqtt:
  host: mosquitto

detectors:
  coral:
    type: edgetpu
    device: usb

cameras:
  front_porch:
    ffmpeg:
      inputs:
        - path: rtsp://admin:password@192.168.1.101:554/h264Preview_01_main
          roles:
            - record
        - path: rtsp://admin:password@192.168.1.101:554/h264Preview_01_sub
          roles:
            - detect
    detect:
      width: 1280
      height: 720
      fps: 5
    zones:
      delivery_mat:
        coordinates: 450,500,750,500,800,700,400,700
    objects:
      track:
        - person
        - package
        - dog
        - car
```

---

## 4. Playbook 3: Room-Level Spatial Presence (Bermuda BLE)

To allow Halbert to understand spatial pronouns (*"Turn off the lights in here"*):

1. **Install Bermuda BLE via HACS:**
   - In Home Assistant $\rightarrow$ HACS $\rightarrow$ Integrations $\rightarrow$ Search `"Bermuda BLE Trilateration"`.
   - Click **Download** and restart Home Assistant.
2. **Deploy ESPHome Bluetooth Proxies:**
   - Place inexpensive ESP32 nodes ($4 each) in key rooms (Living Room, Kitchen, Office, Bedroom) running ESPHome Bluetooth Proxy firmware.
3. **Configure Tracked Device:**
   - In Bermuda BLE settings, select your phone or Apple Watch Bluetooth MAC address.
   - Bermuda creates entity `sensor.bermuda_phone_room` (e.g. state = `"Living Room"`).
4. **Link to Halbert:**
   - In Halbert **Settings > Home & Space > Presence Tracking Source**, select `sensor.bermuda_phone_room`.

---

## 5. Playbook 4: Smart Per-Room Lighting & Adaptive Circadian Rhythm

1. **Assign Lights to Areas in Home Assistant:**
   - In HA $\rightarrow$ Settings $\rightarrow$ Areas & Zones $\rightarrow$ Areas.
   - Ensure every light entity is assigned to its proper room Area.
2. **Install Adaptive Lighting (HACS):**
   - Automatically adapts brightness and color temperature (Kelvin) across sunrise, solar noon, and sunset to promote circadian health.
3. **Autonomous Halbert Control:**
   - Halbert uses `ha_tool` with `service: "light.turn_on"` passing `area_id: "office"` to adjust entire rooms seamlessly.

---

## 6. How Halbert Autonomously Guides and Installs

When the user asks Halbert:
- *"How do I set up Frigate?"*
- *"Can you help me install Home Assistant?"*
- *"How do I make you know what room I'm in?"*

Halbert's intake matches the `home-ops` or `frigate-ops` skill, which provides the model with these exact playbooks, enabling Halbert to:
1. Explain the architecture conversationally.
2. Generate tailored `docker-compose.yml` and `config.yml` files for the user's specific IP addresses and hardware (Coral TPU, Intel QSV, etc.).
3. If granted tool execution approval, autonomously create the directory structure, write configs, launch the containers, and verify network connectivity!
