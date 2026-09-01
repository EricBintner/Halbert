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
│    • Path 1 (Distributed): Tauri v2 desktop + separate HA edge node                         │
│    • Path 2 (Sidecar): Standard Linux + halbertd + docker-compose (HA + Z2M + MQTT)         │
│    • Path 3 (HA Add-on): HACS integration inside existing HAOS (distribution funnel)        │
│    • Path 4 (Appliance): Turnkey image = standard distro + halbertd pre-installed (future)  │
└─────────────────────────────────────────────────────────────────────────────────────────────┘
```

By keeping **Identity (Memory)** strictly decoupled from **Host Runtime (OS/App)**, we do not have a house of cards. A user can start with a standalone macOS app, add a Home Assistant node later, or upgrade to a dedicated HalbertOS appliance without altering their agent's memory or identity.

---

## 2. The Home Assistant Relationship: Peer, Sidecar, or Guest

> **Important correction (2026-08-31):** The original version of this section
> proposed "HalbertOS hosting Home Assistant Supervised (Docker)" as Tier B.
> Home Assistant Supervised was deprecated by Nabu Casa in May 2025 and became
> formally unsupported with HA 2025.12 (December 2025). ADR-0014 was reverted.
> Only HAOS and HA Container remain as supported installation methods. The
> Tier B proposal has been rewritten below to reflect this reality and the
> approved sidecar deployment strategy. See
> [`.handoff/HA-STRATEGY-SCOPING-AND-DEPLOYMENT-PATHS-2026-08-31.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/HA-STRATEGY-SCOPING-AND-DEPLOYMENT-PATHS-2026-08-31.md)
> for the full strategic analysis.

Home Assistant OS (HAOS) is an established, rock-solid appliance OS for smart
homes. Halbert accommodates Home Assistant across three deployment paths —
none of which involve Halbert hosting HA as a foundation (that creates a
house-of-cards dependency on Nabu Casa's installation method decisions):

```
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│                            HOME ASSISTANT INTEGRATION PATHS                                 │
├──────────────────────────────┬──────────────────────────────┬──────────────────────────────┤
│ PATH 1: Distributed (Peer)   │ PATH 2: Sidecar (One Box)    │ PATH 3: HA Add-on (Funnel)   │
│ (Recommended for most users) │ (Power users, single device) │ (Zero-friction HAOS install) │
├──────────────────────────────┼──────────────────────────────┼──────────────────────────────┤
│                              │                              │                              │
│  ┌────────────────────────┐  │  ┌────────────────────────┐  │  ┌────────────────────────┐  │
│  │  WORKSTATION           │  │  │  STANDARD LINUX        │  │  │  HOME ASSISTANT OS     │  │
│  │  Halbert Desktop       │  │  │  halbertd (systemd)    │  │  │  ┌──────────────────┐  │  │
│  │  + halbertd (optional) │  │  │  ┌──────────────────┐  │  │  │  │ HA Supervisor    │  │  │
│  └───────────┬────────────┘  │  │  │ docker-compose    │  │  │  │  ┌──────────────┐ │  │  │
│              │ WebSocket     │  │  │ HA + Z2M + MQTT   │  │  │  │  │ Halbert      │ │  │  │
│  ┌───────────▼────────────┐  │  │  └──────────────────┘  │  │  │  │ Add-on       │ │  │  │
│  │  EDGE NODE (Pi / N100) │  │  └────────────────────────┘  │  │  │ (sandboxed)  │ │  │  │
│  │  HAOS or HA Container  │  │  halbertd has kernel access  │  │  └──────────────┘ │  │  │
│  │  + Zigbee2MQTT         │  │  HA is a peer, not foundation│  │  (no kernel access)│  │  │
│  └────────────────────────┘  │                              │  └────────────────────────┘  │
└──────────────────────────────┴──────────────────────────────┴──────────────────────────────┘
```

### Path 1: Distributed Peer (Recommended for Most Users)
* **How it works:** Halbert runs as a desktop app on the user's main machine. HA runs on a separate small device (Pi, N100, NAS). Halbert connects to HA via WebSocket API.
* **Role:** Halbert is the brain; HA is a device bus. HA handles device protocol translation; Halbert handles cognition, automation, and voice.
* **Why it matters:** 90% of smart home enthusiasts already have HAOS installed on a Raspberry Pi or N100/N150 mini PC. No new hardware required. This is already built and working.
* **Security boundary:** Halbert never touches Zigbee keys, Z-Wave network secrets, or RTSP credentials. HA handles all credential isolation internally.

### Path 2: Sidecar on One Box (Power Users)
* **How it works:** Standard Linux distro (Debian/Arch/Fedora). `halbertd` runs as a systemd service on the host (kernel access: eBPF, Btrfs, Landlock). HA Container, Zigbee2MQTT, and Mosquitto run as independent Docker containers via `docker-compose`. Halbert connects to HA via localhost WebSocket and to Mosquitto directly.
* **Why no house of cards:** Each service is independent. If HA breaks, Halbert still has direct MQTT device access. If Docker breaks, `halbertd` still runs. No layer depends on a layer owned by a different party's release cadence.
* **OS-level capabilities (not HA-specific):** These are features of `halbertd` on the host, available to any service:
  1. **Atomic Btrfs Rollbacks:** `halbertd` takes a subvolume snapshot before any system change (HA update, config edit, package install), offering 1-click rollback. This is an OS capability, not an HA hosting feature.
  2. **eBPF IoT Network Isolation:** `halbertd` uses kernel eBPF filters to sandbox IoT device containers so they cannot execute lateral network scans against local workstations.
  3. **Local AI Model Provisioning:** `halbertd` manages local GPU/NPU drivers, hosting `llama.cpp` or `vLLM` to serve offline inference.

### Path 3: HA Add-on Guest (Distribution Funnel)
* **How it works:** Halbert packaged as an HA Add-on, installable from the HACS add-on store. HAOS handles infrastructure (networking, storage, updates). Halbert is a tenant.
* **Role:** Zero-friction discovery for the ~500k HAOS user base. Users try Halbert's voice and automation features, then graduate to Path 1 or 2 for the full experience (sysadmin, OS-level safety, native device bus).
* **Limitations:** HAOS is a read-only sandbox — no host kernel access, no eBPF, no Btrfs, no Landlock. This is a funnel, not the product.

### The Strategic Direction: HA Architecturally Optional

> **Halbert's value is the cognitive layer, not the device bus.**
> The device bus is a commodity (MQTT/Matter/Zigbee).
> HA is a convenient adapter for that commodity, not a foundation to build on.

In the near term, HA remains the recommended and marketed smart home path
("Works great with Home Assistant, but doesn't require it"). In the medium
term, Halbert gains native MQTT + Zigbee2MQTT support, making HA optional
for core local devices. The long tail of HA integrations (cloud APIs,
proprietary protocols) remains accessible via the HA peer integration
(Path 1/2). Both paths coexist — native device bus for the core, HA as peer
for the long tail.

---

## 3. Network & System Security: OS-Level vs. App-Level

The user's intuition is correct: **from a security perspective, OS-level integration is strictly superior to application-level security.** 

Here is how security is enforced at each path:

### 1. Peer-to-Peer mTLS Wire Protocol (App & Node Level)
* All Halbert bodies (Mac workstation, Linux laptop, HA server) communicate over **mutual TLS (mTLS)** with ephemeral Ed25519 pairing tokens.
* When you click "Pair Device" in the desktop UI (`Settings -> Devices`), the devices exchange public keys. All memory sync (`PeerMemoryBackend`) and compute offloading are encrypted end-to-end.

### 2. Kernel-Level Blast Radius (OS Level via `halbertd`)
* While the desktop app must rely on OS user permissions, a host running **`halbertd`** (Path 2 or 4) leverages **Landlock and eBPF-LSM**:
  * An automated script triggered by a home automation event (e.g. "adjust fan speed via GPIO") is strictly prohibited by the kernel from touching network sockets or `/etc`.

### 3. eBPF Network Sentry
* On a host with `halbertd`, `halbert-ebpf` observes all outbound connections from Docker containers and IoT bridges. If an unauthorized DNS query or suspicious outbound telemetry connection occurs, Halbert blocks the socket at the kernel level and alerts the user in first person:
  > *"I noticed my Tuya Wi-Fi bridge attempting to contact an unauthorized IP address (`185.x.x.x`). I have temporarily isolated it from the local LAN."*

---

## 4. How the Rust Upgrade Accelerates the Multi-Node Ecosystem

Moving low-level components to Rust is especially critical for **low-power edge nodes (satellites and HA servers)**:

```
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│                              RESOURCE FOOTPRINT: PYTHON VS. RUST                            │
├───────────────────────────────┬──────────────────────────────┬──────────────────────────────┤
│ Metric                        │ Current Python Prototype     │ Rust Native Daemon (target) │
├───────────────────────────────┼──────────────────────────────┼──────────────────────────────┤
│ RAM Usage (Idle Satellite)    │ ~120 MB – 180 MB             │ **< 30–60 MB** (target)      │
│ Cold Start Time               │ ~1.8 seconds                 │ **< 50 ms** (target)         │
│ mTLS Handshake Latency        │ ~45 ms (asyncio / OpenSSL)   │ **< 5 ms (rustls)** (target) │
│ PTY / Voice Loop Latency      │ ~30 ms                       │ **< 5 ms (cpal / ringbuf)**  │
│ Standalone Binary Footprint   │ Requires Python Venv (~500MB)│ Single Binary (~18 MB)       │
└───────────────────────────────┴──────────────────────────────┴──────────────────────────────┘
```

> **Note:** The figures in the Rust column are **engineering targets**, not
> measured results. Realistic estimates for a rustls+tokio+audio+memory-client
> daemon are higher than the aspirational numbers in the original version of
> this table. These will be updated with real measurements once the crates
> are built.

### Key Rust Crates for the Node Ecosystem:
1. **`crates/halbert-mesh`:** Ultra-lightweight mTLS peer discovery, pairing handshake, and wire protocol (using `rustls` and `tokio`).
2. **`crates/halbert-memory-client`:** High-speed client that proxies memory reads/writes to the canonical `PersonaMemoryStore` on the always-on node.
3. **`crates/halbert-wyoming`:** Zero-latency Wyoming voice protocol handler (integrating microphone capture, AEC, and Piper TTS directly in Rust).
4. **`crates/halbert-mqtt`:** Native MQTT client (`rumqttc`) + device state cache for direct Zigbee2MQTT / Mosquitto device bus access.

---

## 5. Architectural Synthesis: The Grand Vision

* **The Desktop App (Mac / Linux)** is the **Front Door**: It introduces users to Halbert with zero installation friction.
* **The Home Assistant Integration (Peer or Add-on)** is the **Anchor**: It gives Halbert an always-on "home body" that preserves memory and continuity 24/7. HA is a peer, not a foundation.
* **`halbertd` + Rust Crates** is the **Engine**: Delivers kernel-level eBPF security, Btrfs atomic rollbacks, and native device bus access on standard distros — no custom OS required.
* **The Singular Entity Model** is the **Magic**: No matter where the user interacts—at their Mac keyboard, in the terminal, or speaking to a microphone in the kitchen—they are speaking to **One Halbert**.
