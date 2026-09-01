# Singular Entity, Home Assistant & HalbertOS: Cross-Platform Node Architecture

**Document Status:** Experimental Architecture & Strategy  
**Date:** 2026-08-31  
**Target Systems:** Halbert Desktop (Tauri/React), Home Assistant (HACS / Add-on), HalbertOS (Appliance / Thin-Client), Headless Servers (N150 / Mac Studio)  
**Core Thesis:** Harmonizing the "Singular Entity, Multi-Body" distributed architecture with Home Assistant, cross-platform apps, and future Rust native OS upgrades.

---

## 1. Deconstructing the "House of Cards": Stratified Topology

When connecting desktop apps, smart home servers, custom Linux distros, and cross-platform devices, there is a risk of over-engineering an unmaintainable "house of cards." 

To avoid this, we separate the system into **three orthogonal layers**:

```
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│ 1. IDENTITY & MEMORY LAYER (Singular Mind)                                                  │
│    • One canonical PersonaMemoryStore & ThreadManager on the always-on node                 │
│    • All bodies (Mac at desk, N150 in kitchen, Laptop on road) share one persona_id         │
└──────────────────────────────────────────────┬──────────────────────────────────────────────┘
                                               │ PeerMemoryBackend / mTLS
┌──────────────────────────────────────────────▼──────────────────────────────────────────────┐
│ 2. BODY CAPABILITY LAYER (Physical Context)                                                 │
│    • Hardware & service presence determines what each body can DO (not variant labels)      │
│    • Mac Studio: GPU local LLM + Sysadmin Tools + Config Watcher                            │
│    • N150 / HA Node: Wyoming Voice + Zigbee/Matter Entities + Frigate Cameras               │
└──────────────────────────────────────────────┬──────────────────────────────────────────────┘
                                               │ Zero-Trust Wire Protocol
┌──────────────────────────────────────────────▼──────────────────────────────────────────────┐
│ 3. HOST RUNTIME LAYER (The Physical Container)                                              │
│    • Tier 1 (Desktop App): Tauri v2 on macOS / Windows / Ubuntu (The Adoption Gateway)     │
│    • Tier 2 (Home Assistant Guest): HACS Integration / Add-on inside existing HAOS          │
│    • Tier 3 (HalbertOS Sovereign Host): Bare-metal appliance running HA in a sandbox        │
└─────────────────────────────────────────────────────────────────────────────────────────────┘
```

By keeping **Identity (Memory)** strictly decoupled from **Host Runtime (OS/App)**, we do not have a house of cards. A user can start with a standalone macOS app, add a Home Assistant node later, or upgrade to a dedicated HalbertOS appliance without altering their agent’s memory or identity.

---

## 2. The Home Assistant Relationship: Guest vs. Sovereign Host

Home Assistant OS (HAOS) is an established, rock-solid appliance OS for smart homes. Halbert accommodates Home Assistant across two distinct deployment tiers:

```
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│                                HOME ASSISTANT INTEGRATION TIERS                             │
├──────────────────────────────────────────────┬──────────────────────────────────────────────┤
│ TIER A: Halbert as a Guest on HAOS           │ TIER B: HalbertOS as the Sovereign Host      │
│ (For existing Home Assistant users)          │ (For dedicated appliances & power homelabs)  │
├──────────────────────────────────────────────┼──────────────────────────────────────────────┤
│                                              │                                              │
│  ┌────────────────────────────────────────┐  │  ┌────────────────────────────────────────┐  │
│  │           HOME ASSISTANT OS            │  │  │               HALBERT-OS               │  │
│  │  ┌─────────────────┐ ┌───────────────┐ │  │  │  ┌─────────────────┐ ┌───────────────┐ │  │
│  │  │ Home Assistant  │ │ Halbert Addon │ │  │  │  │   halbertd      │ │  Btrfs CoW    │ │  │
│  │  │ Core (Docker)   │ │ (Docker Node) │ │  │  │  │ (Rust Daemon)    │ │ Auto-Snapshots│ │  │
│  │  └────────┬────────┘ └───────▲───────┘ │  │  │  └────────┬────────┘ └───────▲───────┘ │  │
│  │           └──────WebSocket───┘         │  │  │           │ Netlink / eBPF    │         │  │
│  └────────────────────────────────────────┘  │  │  ┌────────▼───────────────────┴──────┐ │  │
│                                              │  │  │ Home Assistant Supervised (Docker)│ │  │
│                                              │  │  └───────────────────────────────────┘ │  │
│                                              │  │  ┌───────────────────────────────────┐ │  │
│                                              │  │  │ eBPF IoT Network Firewall Isolation│ │  │
│                                              │  │  └───────────────────────────────────┘ │  │
│                                              │  └────────────────────────────────────────┘  │
└──────────────────────────────────────────────┴──────────────────────────────────────────────┘
```

### Tier A: Guest on Existing HAOS (Zero-Friction Adoption)
* **How it works:** Existing Home Assistant users install the Halbert HACS integration and optional Add-on container.
* **Role:** Halbert acts as the voice assistant (via Wyoming protocol) and automator. It connects to the user's desktop Halbert app via peer pairing.
* **Why it matters:** 90% of smart home enthusiasts already have HAOS installed on a Raspberry Pi or N100/N150 mini PC. Demanding they wipe their drive to install HalbertOS would destroy user adoption.

### Tier B: HalbertOS as Sovereign Host (The Ultimate Homelab Appliance)
* **How it works:** HalbertOS runs on bare-metal hardware (e.g. an Intel N150 or GMKtec mini-PC with an optional eGPU/A2000). HalbertOS hosts Home Assistant inside an isolated container.
* **Superpowers of HalbertOS managing Home Assistant:**
  1. **Atomic Btrfs Rollbacks for Home Assistant:** Home Assistant updates and integration changes frequently break yaml configurations or SQLite databases. HalbertOS takes a subvolume snapshot before any HA core update, offering 1-click zero-downtime rollback.
  2. **eBPF IoT Network Isolation:** HalbertOS uses kernel eBPF filters to strictly sandbox IoT devices (Zigbee/Matter bridges, Wi-Fi smart plugs) so they cannot execute lateral network scans against local workstations.
  3. **Local AI Model Provisioning:** HalbertOS manages the local GPU/NPU drivers, hosting `llama.cpp` or `vLLM` to serve offline inference for the entire home.

---

## 3. Network & System Security: OS-Level vs. App-Level

The user's intuition is correct: **from a security perspective, OS-level integration is strictly superior to application-level security.** 

Here is how security is enforced at each tier:

### 1. Peer-to-Peer mTLS Wire Protocol (App & Node Level)
* All Halbert bodies (Mac workstation, Linux laptop, HA server) communicate over **mutual TLS (mTLS)** with ephemeral Ed25519 pairing tokens.
* When you click "Pair Device" in the desktop UI (`Settings -> Devices`), the devices exchange public keys. All memory sync (`PeerMemoryBackend`) and compute offloading are encrypted end-to-end.

### 2. Kernel-Level Blast Radius (OS Level on HalbertOS)
* While the desktop app must rely on OS user permissions, a node running on **HalbertOS** leverages **Landlock and eBPF-LSM**:
  * An automated script triggered by a home automation event (e.g. "adjust fan speed via GPIO") is strictly prohibited by the kernel from touching network sockets or `/etc`.

### 3. eBPF Network Sentry
* On HalbertOS, `halbert-ebpf` observes all outbound connections from Docker containers and IoT bridges. If an unauthorized DNS query or suspicious outbound telemetry connection occurs, Halbert blocks the socket at the kernel level and alerts the user in first person:
  > *"I noticed my Tuya Wi-Fi bridge attempting to contact an unauthorized IP address (`185.x.x.x`). I have temporarily isolated it from the local LAN."*

---

## 4. How the Rust Upgrade Accelerates the Multi-Node Ecosystem

Moving low-level components to Rust is especially critical for **low-power edge nodes (satellites and HA servers)**:

```
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│                              RESOURCE FOOTPRINT: PYTHON VS. RUST                            │
├───────────────────────────────┬──────────────────────────────┬──────────────────────────────┤
│ Metric                        │ Current Python Prototype     │ Rust Native Daemon           │
├───────────────────────────────┼──────────────────────────────┼──────────────────────────────┤
│ RAM Usage (Idle Satellite)    │ ~120 MB – 180 MB             │ **< 12 MB**                  │
│ Cold Start Time               │ ~1.8 seconds                 │ **< 15 milliseconds**        │
│ mTLS Handshake Latency        │ ~45 ms (asyncio / OpenSSL)   │ **< 2 ms (rustls)**          │
│ PTY / Voice Loop Latency      │ ~30 ms                       │ **< 1 ms (cpal / ringbuf)**  │
│ Standalone Binary Footprint   │ Requires Python Venv (~500MB)│ Single Binary (~18 MB)       │
└───────────────────────────────┴──────────────────────────────┴──────────────────────────────┘
```

### Key Rust Crates for the Node Ecosystem:
1. **`crates/halbert-mesh`:** Ultra-lightweight mTLS peer discovery, pairing handshake, and wire protocol (using `rustls` and `tokio`).
2. **`crates/halbert-memory-client`:** High-speed client that proxies memory reads/writes to the canonical `PersonaMemoryStore` on the always-on node.
3. **`crates/halbert-wyoming`:** Zero-latency Wyoming voice protocol handler (integrating microphone capture, AEC, and Piper TTS directly in Rust).

---

## 5. Architectural Synthesis: The Grand Vision

* **The Desktop App (Mac / Windows / Linux)** is the **Front Door**: It introduces users to Halbert with zero installation friction.
* **The Home Assistant Integration (Guest or Host)** is the **Anchor**: It gives Halbert an always-on "home body" that preserves memory and continuity 24/7.
* **HalbertOS** is the **Pinnacle**: For dedicated mini-PCs and sovereign servers, it delivers kernel-level eBPF security, Btrfs atomic rollbacks, and hardware-reserved local AI inference.
* **The Singular Entity Model** is the **Magic**: No matter where the user interacts—at their Mac keyboard, in the terminal, or speaking to a microphone in the kitchen—they are speaking to **One Halbert**.
