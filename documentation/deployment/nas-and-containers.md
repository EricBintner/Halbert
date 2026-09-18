# NAS & Container-Centric Deployments (Synology, TrueNAS SCALE, Unraid)

This guide documents deploying Halbert and Home Assistant on Network Attached Storage (NAS) platforms running containerized environments (such as **Synology DSM**, **TrueNAS SCALE**, or **Unraid**).

---

## 1. Architectural Model & NAS Constraints

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ NETWORK ATTACHED STORAGE (Synology DSM / TrueNAS SCALE / Unraid)            │
│                                                                             │
│  Host Storage Pool (ZFS / Btrfs RAID)                                       │
│  └── /volume1/docker/ (or /mnt/pool/appdata/)                               │
│      ├── homeassistant/config/                                              │
│      ├── mosquitto/config/                                                  │
│      ├── zigbee2mqtt/data/                                                  │
│      └── halbert/data/                                                      │
│                                                                             │
│  Docker Engine / Container Runtime:                                         │
│  ├── [Container] Home Assistant (ghcr.io/home-assistant/home-assistant)     │
│  │   └── network_mode: host (for mDNS/Matter discovery)                     │
│  ├── [Container] Mosquitto MQTT Broker                                      │
│  ├── [Container] Zigbee2MQTT (with /dev/serial USB device mapping)          │
│  └── [Container] Halbert Core Agent                                         │
│      └── Degrades gracefully to pure-Python container mode                  │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Operational Trade-Offs on a NAS
* **Storage Resilience:** NAS appliances provide redundant RAID storage (ZFS/Btrfs) with automated snapshot pools, keeping data safe.
* **The Host Custodian Boundary:** When Halbert runs inside a container on a commercial NAS OS, it lacks access to a standard Linux host `systemd`, `apt/dnf`, and low-level kernel eBPF hooks. Halbert operates in **application container mode**—focusing on smart home cognition, timeline ledger ingestion, and API execution.

---

## 2. Port Conflict Avoidance

Commercial NAS operating systems reserve numerous standard ports for their administrative dashboards and built-in services. Verify and adjust bindings before deployment:

| Port | Standard Use | Common NAS Conflict | Recommended Remap (if needed) |
|:---|:---|:---|:---|
| **8000** | Halbert Host Dashboard | Synology Drive Server / Portainer | Remap to `8010` via `HALBERT_PORT=8010` |
| **8001** | Halbert Home Dashboard | Open | Default `8001` |
| **8123** | Home Assistant Web UI | Generally available | Default `8123` |
| **1883** | Mosquitto MQTT | Generally available | Bind to `127.0.0.1:1883` |
| **10401**| Wyoming Voice Port | Generally available | Default `10401` |

---

## 3. Docker Compose Stack for NAS

Create a persistent directory on your storage pool (e.g., `/volume1/docker/home-stack` on Synology or `/mnt/user/appdata/home-stack` on Unraid) with the following `docker-compose.yml`:

```yaml
services:
  homeassistant:
    image: ghcr.io/home-assistant/home-assistant:stable
    container_name: homeassistant
    restart: unless-stopped
    network_mode: host   # Required for mDNS and smart home discovery
    volumes:
      - ./homeassistant/config:/config
      - /etc/localtime:/etc/localtime:ro
      - /run/udev:/run/udev:ro

  mosquitto:
    image: eclipse-mosquitto:2
    container_name: mosquitto
    restart: unless-stopped
    ports:
      - "127.0.0.1:1883:1883"
    volumes:
      - ./mosquitto/config:/mosquitto/config
      - ./mosquitto/data:/mosquitto/data

  zigbee2mqtt:
    image: koenkk/zigbee2mqtt:latest
    container_name: zigbee2mqtt
    restart: unless-stopped
    network_mode: host
    volumes:
      - ./zigbee2mqtt/data:/app/data
      - /run/udev:/run/udev:ro
    devices:
      - /dev/serial/by-id/usb-ITEAD_SONOFF_Zigbee_3.0_USB_Dongle_Plus_V2_...:/dev/ttyUSB0
    depends_on:
      - mosquitto

  halbert:
    image: ghcr.io/ericbintner/halbert-core:latest
    container_name: halbert-home
    restart: unless-stopped
    network_mode: host
    environment:
      - HALBERT_PORT=8001
      - HALBERT_VARIANT=home
      - HALBERT_DATA_DIR=/data
      - HALBERT_CONFIG_DIR=/config
      - WYOMING_ENABLED=1
      - WYOMING_PORT=10401
    volumes:
      - ./halbert/data:/data
      - ./halbert/config:/config
    depends_on:
      - homeassistant
```

---

## 4. Platform-Specific USB Device Passthrough

### Synology DSM 7+
Synology DSM 7 removed native USB kernel drivers for many serial dongles (CH340, CP210x).
1. Install the **SynoKernel USB Serial Drivers** package via SynoCommunity or load kernel modules via a boot task:
   ```bash
   insmod /lib/modules/usbserial.ko
   insmod /lib/modules/cp210x.ko
   insmod /lib/modules/ch341.ko
   ```
2. In DSM Container Manager, grant the container elevated privileges or map the device node via the command-line compose file.

### Unraid
1. Plug the coordinator into the Unraid host.
2. In the Unraid Web UI, install the **USB Manager** plugin to identify the persistent vendor/product ID.
3. Pass through the device path directly in the Docker template using `--device=/dev/serial/by-id/your-dongle:/dev/ttyUSB0`.

### TrueNAS SCALE
1. In TrueNAS SCALE (Electric Eel 24.10+ / standard Docker), map the device under **Custom App → Device Allocation**.
2. Avoid using raw `/dev/ttyUSB0`; always specify the stable `/dev/serial/by-id/...` symlink.
