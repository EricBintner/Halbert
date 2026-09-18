# Proxmox VE Homelab Deployment (HAOS VM + Halbert Host Custodian)

This guide documents the technical architecture, virtual machine configuration, and network topology for running Halbert and Home Assistant on a **Proxmox VE** hypervisor host.

---

## 1. Architectural Model

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ PROXMOX VE HYPERVISOR (Debian Host)                                         │
│                                                                             │
│  vmbr0 (Linux Bridge / LAN 192.168.1.0/24)                                  │
│  ├── [VM 100] Home Assistant OS (HAOS)                                      │
│  │   ├── Static IP: 192.168.1.10                                            │
│  │   ├── Hardware USB Passthrough: Sonoff / SkyConnect Zigbee Dongle        │
│  │   └── Official Supervisor, Add-on Store, and Core Automations            │
│  │                                                                          │
│  ├── [VM 101 or LXC] Halbert Node (Ubuntu / Debian)                         │
│  │   ├── Static IP: 192.168.1.11                                            │
│  │   ├── Hardware Passthrough: iGPU (renderD128) / Coral TPU (optional)     │
│  │   ├── Halbert Home Instance (systemd service)                            │
│  │   ├── Outbound REST / WebSocket link to 192.168.1.10:8123                │
│  │   └── Inbound Wyoming Voice Satellite listener (port 10401)              │
│  │                                                                          │
│  └── Optional: Proxmox Host Monitoring                                      │
│      └── Halbert monitoring Proxmox host vitals via SSH / QEMU Guest Agent  │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Why Choose Proxmox VE?
* **Best of Both Worlds:** Gives you the official, turnkey **Home Assistant OS** appliance (with 1-click Supervisor add-ons like ESPHome, Z-Wave JS UI, and Cloudflared) while simultaneously giving Halbert a **standard Linux OS** environment with full root access, systemd, package management, and hardware telemetry.
* **Snapshot & Backup Isolation:** Proxmox Backup Server (PBS) or scheduled VM snapshots protect Home Assistant independently from Halbert, eliminating cross-dependency breakage.
* **Hardware Passthrough Granularity:** Dedicated PCIe/USB devices (e.g. Zigbee coordinator) map cleanly to the HAOS VM, while compute accelerators (e.g. Intel QuickSync iGPU, Coral TPU) map to the Halbert node.

---

## 2. VM 1: Home Assistant OS (HAOS) Setup

1. **Provisioning HAOS:**
   * Download the official KVM/Proxmox image (`qcow2.xz`) from the Home Assistant website.
   * Unpack the image and import it into Proxmox:
     ```bash
     qm importdisk 100 haos_ova-XX.X.qcow2 local-lvm
     ```
   * Recommended VM Resources:
     * **CPU:** 2 vCPUs (host type)
     * **Memory:** 4096 MB (ballooning enabled)
     * **Disk:** SCSI, 32 GB+ SSD/NVMe storage
     * **Network:** VirtIO on `vmbr0` (bridged to physical LAN)
     * **BIOS:** OVMF (UEFI)

2. **USB Coordinator Passthrough:**
   * In Proxmox VE Web UI: **VM 100 → Hardware → Add → USB Device**.
   * Select **Use USB Vendor/Device ID** or specify the USB port location.
   * *Recommendation:* Use a short USB 2.0 extension cable connected to the Proxmox host to prevent USB 3.0 RF interference with the 2.4 GHz Zigbee radio.

3. **HA Network Configuration:**
   * Ensure HAOS receives a static DHCP reservation (e.g., `192.168.1.10`).
   * Complete onboarding and generate a **Long-Lived Access Token** (Profile → Security).

---

## 3. VM 2 / LXC: Halbert Node Setup

Halbert can run in either an unprivileged LXC container with appropriate device mounts or a dedicated lightweight Ubuntu Server / Debian VM. For full systemd service isolation and kernel-level metrics, a dedicated lightweight VM is recommended.

1. **Provisioning Halbert Node (VM 101):**
   * **Base OS:** Ubuntu Server 24.04 LTS or Debian 12
   * **CPU:** 2 to 4 vCPUs
   * **Memory:** 4096 MB to 8192 MB (increase to 16 GB if running local Ollama inference)
   * **Disk:** 30 GB+ on fast storage

2. **Halbert Installation:**
   ```bash
   sudo apt update && sudo apt install -y git python3-venv python3-pip lm-sensors smartmontools
   git clone https://github.com/EricBintner/Halbert.git /opt/halbert
   cd /opt/halbert
   python3 -m venv .venv
   source .venv/bin/activate
   pip install --upgrade pip
   pip install -e ./halbert_core
   ```

3. **System Configuration:**
   Create system user and directories:
   ```bash
   sudo useradd -r -s /bin/false -d /var/lib/halbert-home halbert || true
   sudo mkdir -p /var/lib/halbert-home /etc/halbert-home /var/log/halbert-home
   sudo chown -R halbert:halbert /var/lib/halbert-home /etc/halbert-home /var/log/halbert-home
   ```

   Configure `/etc/halbert-home/being.yml`:
   ```yaml
   name: Home
   voice: first_person
   proactivity: balanced
   purpose: Homelab cluster custodian and smart home intelligence
   ```

4. **Connect Halbert to Home Assistant:**
   ```bash
   sudo -u halbert HALBERT_DATA_DIR=/var/lib/halbert-home /opt/halbert/.venv/bin/python -c "
   from halbert_core.integrations.home_assistant.ha_config import save_ha_config, HAConfig
   save_ha_config(HAConfig(
       url='http://192.168.1.10:8123',
       token='YOUR_HA_LONG_LIVED_TOKEN'
   ))
   "
   ```

5. **Enable Halbert Service:**
   ```bash
   sudo cp /opt/halbert/deploy/halbert-home.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now halbert-home
   ```

---

## 4. Inbound Voice Assistant Routing (HA Assist to Halbert)

To route voice satellite and HA Assist queries through Halbert:

1. In the HAOS VM, open HACS or manually copy `custom_components/halbert` into `/config/custom_components/halbert`.
2. Restart Home Assistant.
3. Go to **Settings → Devices & Services → Add Integration → Halbert**.
4. Configure the Halbert Wyoming address:
   * **Host:** `192.168.1.11` (the Halbert VM IP)
   * **Port:** `10401` (the default Wyoming port for Halbert Home instance)
5. Go to **Settings → Voice Assistants** and select Halbert as the pipeline's conversation engine.

---

## 5. Network Optimization & Latency Considerations

* **Local Virtual Switch Latency:** Because both VMs communicate over the Proxmox Linux bridge (`vmbr0`), packet latency between Halbert and Home Assistant is sub-millisecond (<0.1ms), significantly faster than cross-LAN physical hops.
* **VLAN Segregation:** If Home Assistant is placed on an IoT VLAN (e.g. VLAN 20) and Halbert is on a Management VLAN (e.g. VLAN 10):
  * Allow TCP port `8123` (HA REST/WebSocket) from Halbert to HA.
  * Allow TCP port `10401` (Wyoming voice stream) from HA to Halbert.
  * Enable mDNS reflection (Avahi or firewall IGMP/mDNS repeater) across the VLANs so device auto-discovery is preserved.
