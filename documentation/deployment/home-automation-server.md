# Deploying a Dedicated Home Automation Server (Intel N100 / N150)

This guide provides architectural recommendations, trade-off analyses, and step-by-step setup instructions for deploying Halbert alongside Home Assistant on an always-on, low-power mini-PC (such as an Intel N100, N150, or similar low-TDP x86 system).

---

## 1. Architectural Recommendation

When building a dedicated home automation server, you face three primary architectural approaches:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ OPTION A: Standard Linux + Docker Sidecar (RECOMMENDED)                     │
│                                                                             │
│  Ubuntu Server 24.04 LTS or Debian 12 on Host                               │
│  ├── Halbert Home Instance (systemd service — full host custodian)          │
│  └── Docker Compose:                                                        │
│      ├── Home Assistant Container (network_mode: host)                      │
│      ├── Mosquitto MQTT Broker (authenticated)                              │
│      └── Zigbee2MQTT (USB coordinator mapped via /dev/serial/by-id)         │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ OPTION B: Bare-Metal Home Assistant OS (HAOS) (NOT RECOMMENDED FOR HALBERT) │
│                                                                             │
│  HAOS (Buildroot Appliance)                                                 │
│  └── HA Supervisor manages containers:                                      │
│      ├── Home Assistant Core                                                │
│      └── Halbert Add-on (planned, heavily sandboxed, no host sysadmin)      │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ OPTION C: Proxmox VE Hypervisor (ALTERNATIVE FOR HOMELABBERS)                │
│                                                                             │
│  Proxmox VE on Host                                                         │
│  ├── VM 1: Home Assistant OS (turnkey HAOS with Supervisor & Add-on store)  │
│  └── VM 2 / LXC: Ubuntu Server (Halbert Home instance & host custodian)     │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Why Option A (Standard Linux + Sidecar) is Recommended

1. **Preserves the Host Custodian Role:**  
   Halbert is designed to identify as the physical computer itself. Running directly on Ubuntu/Debian allows Halbert to monitor CPU thermals (`hwmon`), inspect system services (`systemd`), monitor system logs (`journald`), audit storage health (NVMe SMART data), and execute host-level self-healing. Running inside an HAOS container reduces Halbert to an isolated chatbot with no host visibility.

2. **Decoupled Resilience ("No House of Cards"):**  
   Home Assistant and Halbert run as independent peer services. If a monthly Home Assistant update breaks or requires troubleshooting, the host server and Halbert remain completely operational. If Halbert restarts or updates, your smart home automations and physical switches continue functioning without interruption.

3. **Hardware & Network Agility:**  
   Standard Linux natively supports `network_mode: host` in Docker (essential for Home Assistant's mDNS, Zeroconf, Apple HomeKit, Matter, and Google Cast discovery) and standard `udev` rules for USB Zigbee/Z-Wave coordinators and Coral Edge TPUs.

4. **Status of the HA Add-on:**  
   Halbert's outbound REST/WebSocket client is fully functional today and connects to any standard Home Assistant instance over localhost. Packaging Halbert as a 1-click HAOS Supervisor Add-on is planned strictly as an adoption funnel for HAOS users, but is not yet available in the repository.

---

## 2. Hardware Considerations for N100 / N150 Systems

Intel Alder Lake-N processors (N100, N150, N97, N200) are ideal hardware targets for this deployment:

* **Power Consumption:** 6W to 15W TDP idle/low load, making them whisper-quiet and economical for 24/7 duty.
* **Compute:** 4 efficient cores provide ample headroom to run Home Assistant, Halbert Home instance, Mosquitto, Zigbee2MQTT, and Frigate NVR concurrently.
* **Hardware Video Acceleration:** The integrated Intel UHD Graphics includes Intel QuickSync, allowing efficient hardware decoding for security camera streams without saturating the CPU.
* **Memory & Storage:** 16 GB DDR4/DDR5 RAM and an internal NVMe SSD are strongly recommended over eMMC or external USB drives.

### USB Coordinator Placement
* When plugging in a Zigbee or Z-Wave USB coordinator (e.g., Sonoff ZBDongle-E/P, Home Assistant SkyConnect), **always use a short USB 2.0 extension cable (0.5m – 1m)**. Connecting directly to the mini-PC's USB 3.0 ports causes radio frequency interference that severely degrades Zigbee/Z-Wave mesh reliability.

---

## 3. Step-by-Step Installation Guide

### Step 1: Install the Base Operating System

1. Flash **Ubuntu Server 24.04 LTS** (or Debian 12 minimal) to a USB drive and install it to the N100's internal NVMe drive.
2. During setup, create a non-root administrative user (e.g. `halbert` or your personal user) and enable the OpenSSH server.
3. Once booted, update system packages:
   ```bash
   sudo apt update && sudo apt upgrade -y
   sudo apt install -y curl git jq udev lm-sensors smartmontools
   ```

### Step 2: Install Docker and Docker Compose

Install Docker Engine using Docker's official repository:

```bash
# Add Docker's official GPG key and repository
sudo apt install -y ca-certificates
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Allow non-root user to manage containers
sudo usermod -aG docker $USER
newgrp docker
```

### Step 3: Deploy the Home Assistant & MQTT Sidecar Stack

1. Create a deployment directory on the host:
   ```bash
   sudo mkdir -p /opt/home-stack/mosquitto/config /opt/home-stack/z2m-data
   sudo chown -R $USER:$USER /opt/home-stack
   cd /opt/home-stack
   ```

2. Identify the persistent path of your USB Zigbee coordinator:
   ```bash
   ls -la /dev/serial/by-id/
   # Example output:
   # usb-ITEAD_SONOFF_Zigbee_3.0_USB_Dongle_Plus_V2_... -> ../../ttyACM0
   ```
   *Always use the `/dev/serial/by-id/...` symlink rather than `/dev/ttyUSB0` or `/dev/ttyACM0` so the device path remains stable across reboots.*

3. Configure Mosquitto authentication:
   Create `/opt/home-stack/mosquitto/config/mosquitto.conf`:
   ```conf
   listener 1883 0.0.0.0
   allow_anonymous false
   password_file /mosquitto/config/passwords
   ```

   Generate the broker password file:
   ```bash
   docker run --rm -v /opt/home-stack/mosquitto/config:/mosquitto/config eclipse-mosquitto:2 \
     mosquitto_passwd -c -b /mosquitto/config/passwords halbert YourMqttSecretPassword
   
   docker run --rm -v /opt/home-stack/mosquitto/config:/mosquitto/config eclipse-mosquitto:2 \
     mosquitto_passwd -b /mosquitto/config/passwords zigbee2mqtt YourZ2mSecretPassword
   
   chmod 600 /opt/home-stack/mosquitto/config/passwords
   ```

4. Create the `docker-compose.yml` file:
   ```yaml
   # /opt/home-stack/docker-compose.yml
   services:
     homeassistant:
       image: ghcr.io/home-assistant/home-assistant:stable
       container_name: homeassistant
       restart: unless-stopped
       network_mode: host   # REQUIRED: enables mDNS, Zeroconf, Matter, and HomeKit discovery
       volumes:
         - ha-config:/config
         - /etc/localtime:/etc/localtime:ro
         - /run/udev:/run/udev:ro

     mosquitto:
       image: eclipse-mosquitto:2
       container_name: mosquitto
       restart: unless-stopped
       ports:
         - "127.0.0.1:1883:1883"  # Loopback only: accessible by HA on host network and local services
       volumes:
         - ./mosquitto/config/mosquitto.conf:/mosquitto/config/mosquitto.conf:ro
         - ./mosquitto/config/passwords:/mosquitto/config/passwords:ro
         - mosquitto-data:/mosquitto/data

     zigbee2mqtt:
       image: koenkk/zigbee2mqtt:latest
       container_name: zigbee2mqtt
       restart: unless-stopped
       network_mode: host
       volumes:
         - ./z2m-data:/app/data
         - /run/udev:/run/udev:ro
       devices:
         # Replace with your actual /dev/serial/by-id path:
         - /dev/serial/by-id/usb-ITEAD_SONOFF_Zigbee_3.0_USB_Dongle_Plus_V2_...:/dev/ttyUSB0
       depends_on:
         - mosquitto

   volumes:
     ha-config:
     mosquitto-data:
   ```

5. Start the sidecar stack:
   ```bash
   docker compose up -d
   ```

6. Complete Home Assistant onboarding:
   * Open `http://<n100-ip>:8123` in a browser.
   * Complete the initial account creation.
   * Go to **Profile** (bottom-left) → **Security** tab → **Long-Lived Access Tokens**.
   * Generate a token named `halbert` and save the token string securely.

---

### Step 4: Install and Configure Halbert (Home Instance)

1. Clone and install Halbert on the host:
   ```bash
   git clone https://github.com/EricBintner/Halbert.git /opt/halbert
   cd /opt/halbert
   python3 -m venv .venv
   source .venv/bin/activate
   pip install --upgrade pip
   pip install -e ./halbert_core
   ```

2. Create system user and directory structure:
   ```bash
   sudo useradd -r -s /bin/false -d /var/lib/halbert-home halbert || true
   sudo mkdir -p /var/lib/halbert-home /etc/halbert-home /var/log/halbert-home
   sudo chown -R halbert:halbert /var/lib/halbert-home /etc/halbert-home /var/log/halbert-home
   ```

3. Create the Home Being configuration:
   Create `/etc/halbert-home/being.yml`:
   ```yaml
   name: Home
   voice: first_person
   proactivity: balanced
   purpose: Smart home automation and ambient host custodian
   ```

4. Store the Home Assistant connection credentials:
   ```bash
   sudo -u halbert HALBERT_DATA_DIR=/var/lib/halbert-home /opt/halbert/.venv/bin/python -c "
   from halbert_core.integrations.home_assistant.ha_config import save_ha_config, HAConfig
   save_ha_config(HAConfig(
       url='http://127.0.0.1:8123',
       token='YOUR_COPIED_LONG_LIVED_TOKEN'
   ))
   "
   ```

5. Install and start the systemd unit:
   Copy the unit file from the repo:
   ```bash
   sudo cp /opt/halbert/deploy/halbert-home.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now halbert-home
   ```

6. Verify that Halbert is connected to Home Assistant:
   ```bash
   systemctl status halbert-home
   journalctl -u halbert-home -n 50 --no-pager | grep -i "home_assistant"
   curl http://localhost:8001/api/instance/info
   ```

---

## 4. Workstation Integration (Singular Entity & Linked Devices)

Once the N100 mini-PC is running:

1. **Dashboard Access:**  
   You can access Halbert's web interface from any computer or mobile browser on your network at `http://<n100-ip>:8001`.

2. **Mac Operator Workstation (Linked Devices):**  
   * Run the Halbert desktop app on your primary Mac workstation.
   * Open **Settings → Linked Devices** (`/settings/devices`).
   * Click **Pair / Connect Another Instance...** and enter the N100's IP and port (`http://<n100-ip>:8001`).
   * Once paired, your Mac desktop acts as the interactive "Desk" body with voice HUD and approvals, while communicating with the always-on "Home" body running on the N100.

3. **Home Assistant Voice Assistant Integration (Wyoming):**  
   * Halbert serves as a voice conversation agent for Home Assistant via the Wyoming protocol (default port `10401` on the Home instance).
   * Copy `custom_components/halbert` into Home Assistant's `/config/custom_components/` directory (or install via HACS).
   * In Home Assistant, go to **Settings → Devices & Services → Add Integration → Halbert** and point it to `localhost:10401`.
   * In **Settings → Voice Assistants**, select Halbert as your conversation agent for Assist or voice satellites.

---

## 5. Resilience & Failure Modes

| Failure Scenario | What Happens | Recovery Behavior |
|:---|:---|:---|
| **Home Assistant crash or update restart** | Halbert Home instance continues running normally. Host metrics, journal logs, and Halbert API remain active. | Halbert automatically reconnects to HA's WebSocket stream as soon as HA finishes booting. |
| **Halbert process restart** | Home Assistant, Mosquitto, and Zigbee2MQTT remain completely undisturbed. Physical wall switches and native automations function seamlessly. | Systemd automatically restarts Halbert (`Restart=on-failure`), which restores its state from SQLite. |
| **N100 Power Outage** | BIOS power-state setting turns the mini-PC back on automatically upon AC power restoration. | Docker brings up HA, Mosquitto, and Z2M; systemd brings up Halbert Home. The home returns to normal state without human intervention. |
| **Network / Internet Drop** | Both Halbert and Home Assistant run 100% locally on `127.0.0.1`. | All smart home controls, voice pipelines, and host monitoring continue functioning completely offline. |
