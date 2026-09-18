# Distributed Topology: Existing Home Assistant Appliance + Workstation

This guide documents the setup for users who **already operate an existing Home Assistant appliance** (such as a Home Assistant Green, Home Assistant Yellow, Raspberry Pi 4/5, or dedicated NUC running HAOS) and wish to integrate Halbert running on a **workstation** (macOS or Linux).

---

## 1. Architectural Model

```
┌──────────────────────────────────────┐        ┌──────────────────────────────────────┐
│  EXISTING SMART HOME APPLIANCE       │        │  PRIMARY WORKSTATION (Mac or Linux)  │
│  (HA Green, Yellow, Pi, or NUC)      │        │                                      │
│                                      │  REST/ │  Halbert Desktop (Tauri v2 App)     │
│  Home Assistant OS (HAOS)            │   WS   │  + halbert_core backend              │
│  - Static IP: e.g. 192.168.1.50:8123 │◄───────│  + Local LLM (Ollama or MLX)         │
│  - Zigbee / Z-Wave Coordinator       │        │  - Ingests entity changes into ledger│
│  - Core Automations & Integrations   │        │  - Triggers service actions          │
│                                      │        │                                      │
│  Halbert Custom Component (HACS)     │ Wyoming│                                      │
│  - Installed in custom_components/   │ (TCP)  │  Wyoming Voice Endpoint              │
│  - Registered as Conversation Agent  │───────►│  - Port 10400 (with auth token)      │
│  - Routes satellite voice to Halbert │        │  - Processes user natural language   │
└──────────────────────────────────────┘        └──────────────────────────────────────┘
                   ▲
                   │ Wi-Fi / Zigbee / Thread
        Smart Home Devices & Voice Satellites
```

### Key Advantages
* **Zero Disruption to Existing Smart Home:** Your existing automations, dashboards, Zigbee network, and Matter fabric remain completely untouched.
* **Leverages Workstation Compute:** Offloads LLM and vision reasoning to your primary workstation (such as an Apple Silicon Mac with high unified memory bandwidth or a Linux PC with a dedicated GPU), sparing the low-power smart home hub from computational exhaustion.

---

## 2. Step 1: Prepare the Existing Home Assistant Instance

### 1. Reserve a Static IP or Note Hostname
Ensure your Home Assistant hub has a static DHCP lease on your router (e.g. `192.168.1.50`) or verify that `http://homeassistant.local:8123` resolves reliably from your workstation.

### 2. Generate a Long-Lived Access Token
1. Open your Home Assistant web interface.
2. Click your **User Profile** (bottom-left avatar).
3. Select the **Security** tab.
4. Scroll down to **Long-Lived Access Tokens** and click **Create Token**.
5. Name the token `halbert-workstation` and copy the generated token string.

---

## 3. Step 2: Configure Halbert on the Workstation

### 1. Install Halbert
Follow the standard installation instructions for your platform:
* **macOS:** Install the direct Halbert Pro application (`ai.halbert.macos.pro`) or run from source in a virtual environment.
* **Linux:** Install the desktop package or run via virtual environment:
  ```bash
  git clone https://github.com/EricBintner/Halbert.git
  cd Halbert
  python3 -m venv .venv
  source .venv/bin/activate
  pip install -e ./halbert_core
  ```

### 2. Configure the Home Assistant Connection
Provide the connection details to Halbert using the CLI or direct configuration:

```bash
python -c "
from halbert_core.integrations.home_assistant.ha_config import save_ha_config, HAConfig
save_ha_config(HAConfig(
    url='http://192.168.1.50:8123',
    token='YOUR_COPIED_LONG_LIVED_TOKEN',
    verify_ssl=False
))
"
```

Once configured, Halbert automatically starts its WebSocket event listener on boot, ingesting entity state changes (lights, climate, motion, door sensors) into its cognitive world model and timeline store.

---

## 4. Step 3: Enable Inbound Voice via Wyoming Protocol

To allow Home Assistant voice satellites (such as ESP32-S3 Box, Wyoming satellite devices, or the HA mobile app) to use Halbert as their conversation brain:

### 1. Configure the Workstation Wyoming Endpoint
Per standing security directives (`DECISIONS.md`), any non-loopback Wyoming binding requires an authentication token:

In your workstation environment or configuration:
```bash
export WYOMING_ENABLED=1
export WYOMING_HOST=0.0.0.0      # Listen on LAN interface
export WYOMING_PORT=10400
export WYOMING_TOKEN=your_secure_shared_secret_token
```

### 2. Install the Halbert Integration in Home Assistant
1. In Home Assistant, install the custom component:
   * **Via HACS:** Integrations → Three dots (top right) → **Custom repositories** → Add `https://github.com/EricBintner/Halbert` with category **Integration**. Search for "Halbert" and install.
   * **Manual:** Copy the `custom_components/halbert` directory from this repository into your Home Assistant `/config/custom_components/halbert` folder.
2. Restart Home Assistant.
3. In Home Assistant, navigate to **Settings → Devices & Services → Add Integration**.
4. Search for **Halbert**.
5. Enter:
   * **Host:** Your workstation LAN IP (e.g. `192.168.1.100`)
   * **Port:** `10400`
   * **Token:** `your_secure_shared_secret_token`
6. Click **Submit**.

### 3. Assign Halbert to Voice Assistants
1. Navigate to **Settings → Voice Assistants**.
2. Select your default assistant (or create a new one).
3. Under **Conversation agent**, select **Halbert**.
4. Test the pipeline in the Assist dialog (`Ctrl+Alt+A` / `Cmd+Alt+A`).

---

## 5. Technical Realities & Operational Caveats

| Factor | Technical Impact | Mitigation Strategy |
|:---|:---|:---|
| **Workstation Sleep / Lid Closure** | If Halbert runs on a laptop that closes its lid, the Wyoming socket closes and HA Assist queries will fail with a connection timeout. | Run Halbert on an always-on desktop (Mac Studio, Mac mini, or Linux workstation), or configure system power settings (`caffeinate -s` on macOS) during active hours. |
| **LAN Security & Plaintext TCP** | Raw Wyoming protocol sends TCP streams across the LAN. | Do not expose the Wyoming port (10400) to the public Internet. Keep all communication within a trusted local VLAN or WireGuard VPN subnet. Always set `WYOMING_TOKEN`. |
| **Network Latency & Wi-Fi Jitter** | High packet latency on congested 2.4 GHz Wi-Fi can delay conversational responses. | Connect the workstation and the Home Assistant hub to wired gigabit Ethernet or a low-latency 5 GHz / 6 GHz Wi-Fi 6 network. |
