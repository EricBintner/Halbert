# HA Strategy, HalbertOS Scope & Deployment Paths — Synthesis & Scoping

**Date:** 2026-08-31
**Status:** Founder decision document
**Builds on:**
- `REVIEW-REQUEST-HA-STRATEGY-AND-HALBERTOS-2026-08-31.md` (original analysis)
- `REVIEW-RESULTS-HA-STRATEGY-AND-HALBERTOS-2026-08-31.md` (external review, approved with refinements)

---

## 1. What the Review Confirmed

| Finding | Status |
|----------|--------|
| HA Supervised is dead (unsupported since 2025.12) | Confirmed |
| Hosting HA is the house of cards | Confirmed |
| Three-layer strategy (peer → native bus → agent OS) | Approved |
| HA is architecturally optional, not marketing-optional | Approved |
| "Sovereign Self-Healing Host Custodian" positioning holds | Confirmed |
| Doc count should be 24,643 not 14,000 | Confirmed |
| Audio capture stubbed, AEC incomplete | Confirmed |

## 2. What the Review Added

Two options the original analysis missed, plus key refinements:

### Option E: Halbert as an HA Add-on (inside HAOS)

Halbert runs as a Docker container managed by HA's Supervisor, installable
from the HACS add-on store.

**Verdict: Distribution funnel, not product architecture.** Good for
adoption (zero-friction install for ~500k HAOS users), but the HAOS
sandbox kills the core value proposition (no host kernel access, no eBPF,
no Btrfs, no Landlock). Use it to acquire users; migrate them to Path 1
or 2 for the full experience.

### Option F: The Sidecar Model (Docker compose on standard Linux) ← KEY

Both Halbert and HA run as independent Docker containers on the same host,
orchestrated by `docker-compose`. `halbertd` runs as a systemd service on
the host for kernel-level features. Halbert connects to HA via localhost
WebSocket.

**This is the actual recommended deployment for "everything on one box"
users.** It avoids every house-of-cards failure mode and preserves
Halbert's access to the host kernel.

**Why this works:**
- HA is a tenant, not a foundation. If HA breaks, Halbert still runs.
- `halbertd` has host kernel access (eBPF, Btrfs, Landlock) — HA doesn't.
- Docker compose is a standard, stable orchestration layer. No dependency
  on HA's Supervisor or installation method.
- HA Container is an OCI image — it runs on any container runtime. Nabu
  Casa has no incentive to break it (it's the foundation of HAOS too).
- Zigbee2MQTT and Mosquitto run as their own containers. No HA add-on
  dependency.

### Key Refinements from Review

1. **Start Layer 2 with MQTT/Z2M only** — defer Matter. `rs-matter` is not
   production-ready for a native controller. MQTT + Zigbee2MQTT covers ~80%
   of real-world devices with zero new protocol work (reuses Frigate MQTT
   infrastructure).

2. **HalbertOS = daemon first, distro later** — ship `halbertd` as a
   package on standard distros. The "OS" brand applies to a turnkey
   appliance image only once the daemon is proven.

3. **HA remains the recommended smart home path** — architecturally
   optional, not marketing-optional. "Works great with Home Assistant,
   but doesn't require it."

4. **The long tail is real for some users** — cloud integrations (Nest,
   Ring, Ecobee), proprietary protocols (Lutron, Insteon), composite
   automations. Layer 1 (HA as peer) handles these. Layer 2 doesn't need to.

5. **HA community as distribution channel** — 500k+ r/homeassistant
   subscribers. HACS integration gives free discovery. Don't burn this
   channel by going "HA-optional" in marketing.

---

## 3. Reeling In the Scope

The experimental docs propose a massive surface area. The review confirms
most of it is north-star, not near-term. Here is the scoped breakdown:

### Near-term actionable (build now)

| Item | What | Why |
|------|------|-----|
| **Rust crates** | `halbert-telemetry`, `halbert-snapshots`, `halbert-sandbox` | Deliver value to the existing app on standard distros. Zero-overhead telemetry, atomic rollback, kernel sandboxing — without a custom OS. |
| **`halbertd` daemon** | Systemd/launchd service installable via apt/pacman/brew | The OS-level features (eBPF, MCP server, Btrfs hooks) without the OS. This IS the near-term "HalbertOS." |
| **MQTT device bus** | `crates/halbert-mqtt` + Python device registry | Makes HA optional for core local devices. Reuses Frigate MQTT infra. ~2 weeks. |
| **Zigbee2MQTT integration** | Auto-discover Z2M on network, subscribe to topics | Covers ~80% of smart home devices. Trivial on top of MQTT. |
| **Sidecar deployment docs** | docker-compose template for Halbert + HA + Z2M + Mosquitto | The "one box" path. No house of cards. |
| **HA Add-on (Option E)** | HACS add-on package | Distribution funnel for HAOS users. Limited but zero-friction. |
| **OS-native MCP server** | Expose `os://` MCP tools to Warp/Claude/Cursor | Most near-term-actionable idea in the experimental folder. MCP server already exists. |

### Medium-term (build after near-term proves out)

| Item | What | Why |
|------|------|-----|
| **Z-Wave JS native** | HTTP/WebSocket client | Trivial (~3 days). Covers Z-Wave devices without HA. |
| **BLE native** | `btleplug` wrapper | Basic support ~1 week, reliable multi-device ~months. |
| **Turnkey appliance image** | Arch/Fedora + halbertd pre-installed + Btrfs default | The "HalbertOS" brand, but really just a pre-configured standard distro. Not a custom OS. |
| **`halbert-sh` PTY proxy** | Rust terminal interceptor with inline safety gating | Valuable but independent of the HA strategy. |

### North-star / deferred (do not build now)

| Item | What | Why deferred |
|------|------|-------------|
| **HalbertOS as custom distro** | mkosi + custom kernel + Wayland compositor + halbertd as PID 1 | Multi-year effort. `halbertd` as a package delivers 90% of the value on standard distros. |
| **Native Matter controller** | `rs-matter` wrapper | `rs-matter` not production-ready for controllers. No commercial hub uses it. Defer until 1.0 API freeze. |
| **Windows platform** | ETW + VSS + ConPTY + DirectML | Second full platform effort. Deferred behind Linux + macOS. |
| **Wayland compositor HUD** | smithay/wlroots custom compositor | Enormous effort. Tauri webview covers the UI need. |
| **Custom initramfs sentinel** | Early-boot recovery shell | Only meaningful with a custom distro. Deferred. |
| **APFS snapshot transactions** | `fs_snapshot_create`/`fs_snapshot_revert` | Private SPIs, notarization risk. Research only. |

---

## 4. The Deployment Paths (Clarified)

Four paths, ordered by recommendation. All four coexist. No house of cards
in any of them.

### Path 1: Distributed (recommended for most users)

```
┌─────────────────────────┐     ┌─────────────────────────┐
│  WORKSTATION (Mac/Linux) │     │  EDGE NODE (Pi / N100)   │
│                          │     │                           │
│  Halbert Desktop (Tauri) │─────│  HAOS or HA Container     │
│  + halbertd (optional)   │ WS  │  + Zigbee2MQTT            │
│  + Rust crates           │     │  + Mosquitto              │
│  + local LLM (optional)  │     │  + USB coordinator        │
└─────────────────────────┘     └─────────────────────────┘
```

- Halbert runs as a desktop app on the user's main machine.
- HA runs on a separate small device (Pi, N100, NAS).
- Halbert connects to HA via WebSocket API (Layer 1).
- `halbertd` optional on the workstation for eBPF/Btrfs/MCP.
- This is what's already built. Zero new work to ship.

**Who this is for:** Everyone with an existing HA setup. 90% of smart home
enthusiasts.

### Path 2: Sidecar on one box (Option F — Docker compose)

```
┌──────────────────────────────────────────────────────────┐
│  STANDARD LINUX (Debian / Arch / Fedora)                  │
│                                                            │
│  ┌────────────────┐  systemd  ┌─────────────────────────┐ │
│  │   halbertd     │←──────────│  host kernel             │ │
│  │  (eBPF, Btrfs, │           │  (Landlock, Btrfs CoW)   │ │
│  │   MCP server)  │           └─────────────────────────┘ │
│  └───────┬────────┘                                       │
│          │ localhost                                      │
│  ┌───────▼────────────────────────────────────────────┐   │
│  │              docker-compose                         │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────────────┐  │   │
│  │  │ Halbert  │  │   HA     │  │  Zigbee2MQTT     │  │   │
│  │  │ (agent)  │──│ Container│  │  (USB coordinator)│  │   │
│  │  └──────────┘  └────┬─────┘  └────────┬─────────┘  │   │
│  │                       │                 │            │   │
│  │                ┌──────▼─────┐    ┌──────▼─────────┐  │   │
│  │                │ Mosquitto  │    │  USB Zigbee    │  │   │
│  │                │ (MQTT bus) │    │  Coordinator   │  │   │
│  │                └────────────┘    └────────────────┘  │   │
│  └──────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────┘
```

- Standard Linux distro (no custom OS).
- `halbertd` as systemd service — host kernel access (eBPF, Btrfs, Landlock).
- HA Container, Zigbee2MQTT, Mosquitto as Docker containers via compose.
- Halbert agent connects to HA via localhost WebSocket.
- Halbert agent also subscribes to Mosquitto directly (Layer 2 — MQTT device bus).
- If HA breaks, Halbert still has direct MQTT device access.
- If Halbert breaks, HA still runs independently.

**Who this is for:** Power users who want everything on one mini-PC (N100,
N150, GMKtec). No separate Pi needed.

**What needs to be built:** docker-compose template, `halbertd` packaging,
MQTT device registry. The HA integration already works.

### Path 3: HA Add-on (Option E — distribution funnel)

```
┌─────────────────────────────────────────┐
│  HOME ASSISTANT OS (Pi / N100)           │
│                                          │
│  ┌────────────────────────────────────┐  │
│  │  HA Supervisor                      │  │
│  │  ┌──────────┐  ┌─────────────────┐  │  │
│  │  │ HA Core  │  │ Halbert Add-on  │  │  │
│  │  │          │──│ (Docker,        │  │  │
│  │  │          │  │  sandboxed)     │  │  │
│  │  └──────────┘  └─────────────────┘  │  │
│  └────────────────────────────────────┘  │
│  (read-only OS, no kernel access)        │
└─────────────────────────────────────────┘
```

- Halbert packaged as an HA Add-on, installable from HACS store.
- HAOS handles infrastructure (networking, storage, updates).
- Halbert is a tenant — no host kernel access, no eBPF, no Btrfs.
- Connects to HA via localhost WebSocket (same as Path 1, just local).
- Limited experience: no sysadmin features, no OS-level safety.

**Who this is for:** HAOS users who want to try Halbert without a second
device. Zero-friction adoption.

**Strategic role:** Funnel, not destination. Users discover Halbert via
HACS, try the voice/automation features, then graduate to Path 1 or 2 for
the full experience (sysadmin, OS-level safety, native device bus).

**What needs to be built:** HA Add-on package (Dockerfile + config.yaml +
HA Supervisor integration). The agent code already runs in Docker.

### Path 4: HalbertOS appliance (north-star, not near-term)

```
┌──────────────────────────────────────────────────────────┐
│  HALBERTOS APPLIANCE (turnkey image)                      │
│                                                            │
│  Arch/Fedora base + halbertd pre-installed + Btrfs default │
│  ┌────────────────┐     ┌──────────────────────────────┐  │
│  │   halbertd     │     │  docker-compose               │  │
│  │  (PID 1 peer,  │     │  HA Container + Z2M + MQTT    │  │
│  │   eBPF, Btrfs, │     │  (same as Path 2)             │  │
│  │   Landlock)    │     └──────────────────────────────┘  │
│  └────────────────┘                                       │
│  Pre-configured, signed UKI, dm-verity /usr               │
└──────────────────────────────────────────────────────────┘
```

- Not a custom kernel. Not a custom init. Not a Wayland compositor.
- Just: standard distro + `halbertd` + Btrfs defaults + docker-compose,
  pre-installed and pre-configured as a flashable image.
- Think: "Raspberry Pi OS for Halbert" not "custom Linux kernel."
- The mkosi/UKI/dm-verity hardening is a later phase, not v1.

**Who this is for:** Users who want a flash-and-go appliance. No OS setup.

**What needs to be built:** First, `halbertd` must be proven on standard
distros (Paths 1-2). Then, the appliance image is just packaging. The
custom kernel / Wayland compositor / PID 1 items from the experimental
docs are explicitly deferred — they're a different product, years out.

---

## 5. The Layer 2 Strategy (Scoped)

The review's key refinement: **start with MQTT + Zigbee2MQTT only.**

### Phase 2a: MQTT device bus (near-term, ~2 weeks)

- `crates/halbert-mqtt` — Rust MQTT client (`rumqttc`) + device state cache
- Python device registry — map MQTT topics to Halbert entity concepts
  (similar to how `ha_event_mapper.py` maps HA entities)
- Zigbee2MQTT auto-discovery — detect Z2M on network, subscribe to its
  topics, expose devices as Halbert entities
- Reuses `FrigateMQTTSubscriber` patterns — proven infrastructure

**Result:** Halbert can see and control Zigbee devices without HA. HA
becomes optional for the core local device layer.

### Phase 2b: Z-Wave JS (trivial, ~3 days)

- HTTP/WebSocket client to Z-Wave JS container
- Map Z-Wave devices to Halbert entities
- Same pattern as HA entity mapping

### Phase 2c: Matter (DEFERRED)

- `rs-matter` is not production-ready for a native controller
- No commercial hub uses it for controller mode
- Defer until `rs-matter` reaches 1.0 API freeze
- Until then, Matter devices are accessed via HA (Layer 1) or via
  Zigbee2MQTT if they're Zigbee+Matter combo devices

### Phase 2d: BLE (deferred)

- `btleplug` is functional but multi-device reliability is months of work
- Defer until there's user demand

**What this means:** Layer 2 is much smaller than the original analysis
implied. It's MQTT + Z2M + Z-Wave JS. That's it for the foreseeable future.
Matter and BLE are tracked but not committed.

---

## 6. What HalbertOS Actually Is (Scoped)

The experimental docs describe HalbertOS as a five-ring AI-native Linux
distribution with custom kernel, Wayland compositor, and PID 1 replacement.
That's a multi-year north star. Here's what HalbertOS actually is near-term:

### Near-term: `halbertd` as a package

```
apt install halbertd    # Debian/Ubuntu
pacman -S halbertd      # Arch
brew install halbertd   # macOS (limited — no eBPF/Btrfs)
```

`halbertd` provides:
- eBPF telemetry streaming (Linux) / Endpoint Security (macOS, future)
- Btrfs snapshot hooks (Linux) / APFS snapshots (macOS, research only)
- Landlock sandboxing (Linux) / App Sandbox (macOS, existing)
- OS-native MCP server (`/var/run/halbert.sock` or stdio)
- SourcePrep graph engine (embedded, not external client)

This is "HalbertOS" as a software package, not a custom OS. It runs on any
standard distro. The user doesn't need to install a new operating system.

### Medium-term: Turnkey appliance image

Once `halbertd` is proven on standard distros, package it as a flashable
image:
- Arch or Fedora base (via mkosi)
- `halbertd` pre-installed and enabled
- Btrfs as default filesystem
- docker-compose for HA + Z2M + Mosquitto pre-configured
- SSH + Halbert dashboard for setup

This is "HalbertOS" as a brand — a pre-configured standard distro, not a
custom OS. Think "Home Assistant OS" approach: they didn't write a custom
kernel, they packaged Buildroot + HA + Supervisor.

### North-star: Custom kernel features (deferred)

These are explicitly deferred and should not be in any near-term plan:
- Custom eBPF-LSM policies baked into kernel
- Wayland compositor (smithay/wlroots)
- `halbertd` as PID 1
- Custom initramfs sentinel
- dm-verity /usr partition
- Signed UKI boot

These are interesting research directions but they're a different product,
years out, and require a dedicated OS engineering team.

---

## 7. The Docker Compose Template (Path 2 Concrete)

This is what the "one box" deployment looks like in practice:

```yaml
# docker-compose.yml — Halbert sidecar deployment
version: "3.8"

services:
  halbert:
    image: halbert/halbert-core:latest
    network_mode: host  # for localhost WS to HA
    volumes:
      - halbert-data:/data
      - /var/run/halbert.sock:/var/run/halbert.sock  # halbertd MCP
    environment:
      - HALBERT_HA_URL=ws://localhost:8123/api/websocket
      - HALBERT_MQTT_HOST=localhost:1883
    depends_on:
      - homeassistant
      - mosquitto

  homeassistant:
    image: ghcr.io/home-assistant/home-assistant:stable
    network_mode: host
    volumes:
      - ha-config:/config
      - /etc/localtime:/etc/localtime:ro

  zigbee2mqtt:
    image: koenkk/zigbee2mqtt:latest
    network_mode: host
    volumes:
      - z2m-data:/app/data
      - /run/udev:/run/udev:ro
    devices:
      - /dev/ttyUSB0:/dev/ttyUSB0  # Zigbee coordinator
    depends_on:
      - mosquitto

  mosquitto:
    image: eclipse-mosquitto:2
    network_mode: host
    volumes:
      - mosquitto-config:/mosquitto/config
      - mosquitto-data:/mosquitto/data

volumes:
  halbert-data:
  ha-config:
  z2m-data:
  mosquitto-config:
  mosquitto-data:
```

`halbertd` runs on the host as a systemd service, not in Docker, because it
needs kernel access (eBPF, Btrfs, Landlock). The Halbert agent container
connects to it via the Unix socket.

**Key properties:**
- HA is a peer container. If it breaks, Halbert still has MQTT.
- Z2M is a peer container. If HA breaks, Z2M still works.
- `halbertd` is on the host. If Docker breaks, `halbertd` still runs.
- No layer depends on a layer owned by a different party's release cadence.
- This is not a house of cards. This is a set of independent services on
  a standard host, connected by localhost networking.

---

## 8. Decisions (All Confirmed 2026-08-31)

| # | Decision | Status |
|---|----------|--------|
| D1 | Adopt the three-layer strategy (peer → MQTT bus → daemon-first OS) | Confirmed (review-approved) |
| D2 | Start Layer 2 with MQTT/Z2M only — defer Matter, BLE | Confirmed (review-approved) |
| D3 | Ship `halbertd` as a package, not a custom OS — daemon first, distro later | Confirmed (review-approved) |
| D4 | Add Option F (sidecar docker-compose) as a first-class deployment path | Confirmed (founder) |
| D5 | Build HA Add-on (Option E) as a distribution funnel into HAOS ecosystem | Confirmed (founder) |
| D6 | Keep HA as the recommended/marketed smart home path — architecturally optional, not marketing-optional | Confirmed (review-approved) |
| D7 | Defer Windows, Wayland compositor, custom kernel, PID 1, initramfs sentinel, dm-verity to north-star | Confirmed (founder) |
| D8 | Apply all 14 P0-P2 doc corrections to experimental docs | Confirmed (founder) |

---

## 9. What Gets Built (Scoped Roadmap)

### Now (near-term)

1. **Rust crates** — `halbert-telemetry`, `halbert-snapshots`, `halbert-sandbox`
2. **`halbertd` daemon** — systemd/launchd package, MCP server, eBPF/Btrfs hooks
3. **MQTT device bus** — `crates/halbert-mqtt` + Python device registry + Z2M auto-discovery
4. **Sidecar docker-compose template** — documented Path 2 deployment
5. **HA Add-on package** — HACS-distributable Path 3
6. **OS-native MCP server** — `os://` tools for Warp/Claude/Cursor
7. **Doc corrections** — fix the 14 factual/scope errors from the review

### Next (medium-term)

8. **Z-Wave JS native** — HTTP client, trivial
9. **Turnkey appliance image** — mkosi + halbertd + Btrfs defaults
10. **`halbert-sh` PTY proxy** — terminal interceptor (independent of HA)

### Later (north-star, not committed)

11. Native Matter controller (gated on `rs-matter` 1.0)
12. BLE native support
13. Windows platform
14. Custom kernel features (eBPF-LSM, Wayland compositor, PID 1)
15. APFS snapshot transactions (research only)

---

## 10. What This Document Replaces

This synthesis supersedes the strategic sections of:
- `REVIEW-REQUEST-HA-STRATEGY-AND-HALBERTOS-2026-08-31.md` (Sections 4-6)
- The Tier A/B framing in `SINGULAR-ENTITY-HOME-ASSISTANT-AND-HALBERTOS-ECOSYSTEM.md` §2

The original review request and review results remain as supporting
documentation. This document is the actionable scoping decision.
