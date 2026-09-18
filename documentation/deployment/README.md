# Halbert Deployment Topologies

This directory documents deployment topologies, operational architectures, and production setups for running Halbert across different hardware configurations, smart home environments, and homelab clusters.

---

## 1. Setup Selection Guide: Which Guide Fits Your Environment?

Use this decision table to find the appropriate deployment guide for your hardware and operational goals:

| Your Hardware & Environment | Recommended Deployment Guide | Architecture Summary |
|:---|:---|:---|
| **Dedicated Mini-PC (Intel N100 / N150 / Beelink / GMKtec)** | **[Dedicated Home Automation Server](home-automation-server.md)** | Ubuntu/Debian host + Docker Sidecar (`network_mode: host` Home Assistant + Mosquitto + Zigbee2MQTT) + native Halbert Home systemd service. Full host custodian capabilities. |
| **Homelab Hypervisor (Proxmox VE Cluster)** | **[Proxmox VE Homelab Guide](proxmox-homelab.md)** | Turnkey Home Assistant OS VM (with official Supervisor & Add-ons) paired with an independent Halbert VM/LXC node over virtual bridge network (`vmbr0`). |
| **Existing Smart Home Appliance (HA Green / Yellow / Pi running HAOS)** | **[Existing HA Appliance + Workstation](existing-ha-appliance.md)** | Leave existing HAOS appliance untouched; Halbert runs on your Mac/Linux workstation, ingesting states via LAN WebSocket and serving Wyoming voice requests. |
| **Always-On Mac Server (Mac mini M1/M2/M4 / Mac Studio)** | **[macOS Always-On Server](macos-server.md)** | Native Halbert Pro on macOS (leveraging high-bandwidth unified memory for local MLX inference) + HA running headlessly in UTM VM with bridged networking. |
| **Storage NAS (Synology DSM / TrueNAS SCALE / Unraid)** | **[NAS & Container-Centric Deployments](nas-and-containers.md)** | Multi-container Docker Compose stack on persistent NAS storage pools; port remapping to avoid NAS UI conflicts and persistent USB coordinator passthrough. |

---

## 2. Core Deployment Invariants

Regardless of which topology you deploy, Halbert adheres to these design invariants:

1. **Host Custodian, Not an Embedded Plugin:**  
   Halbert identifies as the physical computer itself. In full host deployments, it monitors CPU thermals (`hwmon`), inspects system services (`systemd`), analyzes logs (`journald`), and watches filesystem changes. Deploying Halbert inside an immutable appliance sandbox (like an HAOS container) strips away this host visibility.

2. **The Sidecar Architecture ("No House of Cards"):**  
   Home Assistant and Halbert operate as decoupled peer services rather than a nested hierarchy. If Home Assistant restarts or encounters an upgrade error, Halbert continues operating independently. If Halbert updates, your physical switches and native automations continue uninterrupted.

3. **Singular Entity Across Linked Devices:**  
   Halbert's identity and memory can span multiple physical nodes:
   * **Home Body:** Operates 24/7 on an energy-efficient headless server (e.g. Intel N100 or Mac mini), maintaining smart home state and server telemetry.
   * **Desk Body / Companion:** Runs on your primary desktop/laptop, providing the conversation dashboard, ambient voice HUD, and approval surface.

---

## 3. Documents in this Section

* **[Dedicated Home Automation Server Guide](home-automation-server.md)** — Architectural comparison, hardware guidelines (N100/N150), step-by-step Docker Sidecar configuration, systemd services, and Home Assistant integration.
* **[Proxmox VE Homelab Guide](proxmox-homelab.md)** — Configuring HAOS VM with USB passthrough alongside a dedicated Halbert Linux VM/LXC node over sub-millisecond virtual bridges.
* **[Distributed Topology: Existing HA Appliance + Workstation](existing-ha-appliance.md)** — Integrating Halbert on a workstation with an existing, unmodified Home Assistant Green, Yellow, or Raspberry Pi hub.
* **[macOS Always-On Server Guide](macos-server.md)** — Overcoming macOS Docker networking limitations using UTM bridged VMs, PoE network coordinators, and native Halbert Pro launchd services.
* **[NAS & Container-Centric Guide](nas-and-containers.md)** — Running Halbert and Home Assistant on Synology DSM, TrueNAS SCALE, and Unraid with persistent storage pools and USB driver mapping.
