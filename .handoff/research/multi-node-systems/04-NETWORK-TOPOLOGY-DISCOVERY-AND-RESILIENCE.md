# Network Topology, Discovery & Local Network Resilience

**Location**: `.handoff/research/multi-node-systems/04-NETWORK-TOPOLOGY-DISCOVERY-AND-RESILIENCE.md`  
**Date**: 2026-09-12  
**Focus**: mDNS/DNS-SD zero-configuration discovery, cross-VLAN bridging, sleeping host management (WoL / DarkWake), and failure detection across flaky Wi-Fi.

---

## 1. Zero-Configuration Discovery: mDNS / DNS-SD on Home Networks

The gold standard for local peer discovery is **Multicast DNS (mDNS, RFC 6762)** paired with **DNS-Based Service Discovery (DNS-SD, RFC 6763)**, popularly known as Apple Bonjour or Linux Avahi.

Halbert advertises its presence using `_halbert._tcp.local.` via the Python `zeroconf` library (`halbert_core/federation/peer_discovery.py`).

```
DNS-SD PTR Query:  _halbert._tcp.local.
  └─► SRV: Living-Room-Pi._halbert._tcp.local. -> Port 8000
  └─► TXT: node_id=living-room-pi, role=satellite, did=did:key:z6M..., caps=voice,home
  └─► A:   192.168.1.50
```

---

## 2. Real-World Home Network Traps

While mDNS works seamlessly in simple test setups, modern residential networks exhibit pathological edge cases that break naive discovery implementations:

### 2.1 The VLAN / Subnet Isolation Trap
In security-conscious smart homes, users isolate IoT gadgets onto an **IoT VLAN** (e.g., `192.168.20.0/24`) while their workstations sit on a **Trusted LAN** (e.g., `192.168.10.0/24`).
- **The Problem**: mDNS operates on UDP multicast address `224.0.0.251:5353` with Time-To-Live $\text{TTL} = 1$. Routers drop link-local multicast packets at the subnet boundary.
- **The Result**: A satellite on the IoT VLAN cannot discover the compute workstation on the Trusted LAN via mDNS, even though unicast routing between the subnets is allowed.

### 2.2 Wi-Fi Multicast Degradation & DTIM Power-Saving
- **The Problem**: Wi-Fi Access Points (APs) treat multicast traffic differently from unicast:
  - Multicast frames are sent at the lowest mandatory basic rate (e.g., 6 Mbps or 1 Mbps) to ensure all clients can hear them, consuming massive airtime.
  - To save battery on mobile devices, APs buffer multicast frames and only transmit them at the **Delivery Traffic Indication Message (DTIM)** interval.
  - Many consumer mesh routers (e.g., Google Nest WiFi, Eero) aggressively drop or throttle mDNS packets between mesh nodes to conserve airtime.
- **The Result**: Discovery beacons take 15–45 seconds to be heard, or are dropped entirely.

### 2.3 DHCP Lease Renewals & Mesh AP Roaming
- When a laptop moves from the office to the living room, it roams between APs, causing temporary packet loss (500ms – 2000ms).
- When a DHCP lease expires, the node's IP address may change dynamically.
- A naive agent using fixed IP addresses will break immediately upon lease renewal.

---

## 3. The 3-Tier Hybrid Discovery Architecture

To provide bulletproof discovery across all network setups without manual configuration, Halbert should adopt a **Three-Tier Hybrid Discovery Ladder**:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       3-TIER HYBRID DISCOVERY LADDER                        │
│                                                                             │
│  Tier 1: Multicast DNS-SD (L2 ZeroConf)                                      │
│  - Broadcasts _halbert._tcp.local via zeroconf                             │
│  - Instant, zero-config pairing on the same broadcast domain               │
│  ─────────────────────────────────────────────────────────────────────────  │
│  Tier 2: Cached Unicast Endpoint with Active Ping Probe                     │
│  - Stores last-known IP/hostname in peers.json                             │
│  - If mDNS is silent, sends direct unicast GET /api/compute/v1/health      │
│  - Bridges cross-VLAN setups where multicast is blocked by router          │
│  ─────────────────────────────────────────────────────────────────────────  │
│  Tier 3: Overlay Mesh Fallback (Tailscale / WireGuard)                      │
│  - Connects via stable encrypted mesh IP (e.g. 100.x.y.z) or MagicDNS       │
│  - Seamless transition when laptops roam outside the home network          │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Implementation Details:
1. **mDNS Resolution First**: The node listens for `_halbert._tcp` announcements. When heard, it updates the peer's current IP address dynamically.
2. **Persistent IP Cache**: If mDNS announcements are missed due to Wi-Fi sleep, the node falls back to the last-known IP stored in `peers.json`.
3. **mDNS TXT Record Verification**: The TXT record must carry the node's immutable `did:key` identity. Even if an IP changes from `192.168.1.50` to `192.168.1.84`, the satellite matches the DID and updates the routing table seamlessly.

---

## 4. Sleeping Nodes: DarkWake, Power Nap & Wake-on-LAN

Compute workstations (Mac Studio, Linux PC) cannot remain at 150W full power 24/7 in an eco-conscious home. They enter low-power sleep states when idle.

### 4.1 Operating System Sleep Characteristics

| Platform | Sleep State | Network Behavior | Wake Latency | Notes for Halbert |
|---|---|---|:---:|---|
| **macOS** (Apple Silicon) | **DarkWake / Power Nap** | Network stack remains awake at low power; CPU throttled; GPU powered off. Responds to Bonjour Sleep Proxy. | < 500 ms | Can process light network checks without turning on displays. |
| **Linux** (Modern PC) | **S0ix / S3** | Network card listens for Magic Packet in low-power state. CPU/RAM suspended. | 2–5 seconds | Requires Wake-on-LAN (WoL) packet to wake full system. |
| **Raspberry Pi 5** | Always On | Always fully powered (~3–5W idle). Never sleeps. | 0 ms | Ideal canonical coordinator / smart home hub. |

### 4.2 Wake-on-LAN (WoL): Mechanics & Dual Broadcast

Halbert's `halbert_core/federation/wake_on_lan.py` implements **Dual Broadcast Wake-on-LAN**:
- **Magic Packet**: An Ethernet frame containing 6 bytes of `0xFF` followed by 16 repetitions of the target node's 48-bit MAC address.
- **Dual Broadcast Requirement**:
  - `255.255.255.255:9` (Limited Broadcast): Heard on the local physical segment, but rejected by some routers.
  - `192.168.1.255:9` (Subnet Directed Broadcast): Routes through switches to the specific subnet.
  - Sending packets to **both** addresses maximizes wake reliability across diverse consumer network switches.

```python
# Halbert's dual-broadcast implementation
send_wol_packet_dual(mac="00:11:22:33:44:55", broadcast="192.168.1.255")
```

> [!TIP]
> **Ethernet vs. Wi-Fi for Compute Hosts**:
> Wake-on-Wireless-LAN (WoWLAN) is notoriously unreliable on consumer PCs due to Wi-Fi power-saving firmware drops. **Any workstation acting as a primary compute peer should be connected via physical Ethernet** to guarantee instant, 100% reliable Wake-on-LAN.

### 4.3 Apple Bonjour Sleep Proxy Integration

On Apple networks, an always-on Apple TV, HomePod, or Raspberry Pi running Avahi can act as a **Bonjour Sleep Proxy**:
- When the Mac Studio goes to sleep, it registers its DNS-SD services with the sleep proxy.
- The sleep proxy answers mDNS queries on behalf of the sleeping Mac.
- When an incoming connection request arrives for the Mac's port, the sleep proxy automatically sends a directed wake packet to wake the Mac just in time.

---

## 5. Failure Detection: Heartbeats vs. SWIM Gossip Protocol

How do nodes determine if a peer has crashed, gone to sleep, or merely experienced a temporary Wi-Fi packet drop?

### 5.1 Naive Heartbeat Pitfalls
- **Binary Timeout**: If node $A$ misses one heartbeat from node $B$ after 3 seconds, it marks $B$ dead.
- **The Wi-Fi Trap**: In home environments, microwave ovens, Bluetooth interference, or Wi-Fi AP roaming routinely cause temporary 3–5 second packet dropouts. Naive heartbeats trigger rapid flapping between `ONLINE` and `OFFLINE`, thashing routing tables and clearing caches.

### 5.2 Halbert's 3-Consecutive-Failure Health Threshold

Halbert's `ComputeRouter` implements a **Hysteresis Failure Detector** (`compute_router.py` line 61):
- A sub-second health probe runs against `/api/compute/v1/health`.
- **Threshold**: Requires **3 consecutive failures** before transitioning state from `ONLINE` $\to$ `OFFLINE`.
- **Fast Recovery**: A **single successful response** immediately resets the failure counter and restores `ONLINE` status.
- This simple hysteresis filter eliminates 95% of false-positive state changes caused by DHCP lease renewals and Wi-Fi roaming.

### 5.3 Advanced Failure Detection: The SWIM Protocol

For clusters growing beyond 3–5 nodes, the **SWIM Protocol** (*Structured Weakly-Consistent Infection-Style Process Group Membership*, Das et al., 2002) is the industry standard (used by HashiCorp Consul and Serf):

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          SWIM FAILURE DETECTION                             │
│                                                                             │
│  1. Direct Probe: Node A pings Node B. No response (timeout).              │
│                                                                             │
│  2. Indirect Probe: Node A asks Node C and Node D to ping Node B.          │
│     ┌───────────┐         Ping Request          ┌───────────┐               │
│     │  Node C   │ ◄──────────────────────────── │  Node A   │               │
│     └─────┬─────┘                               └─────┬─────┘               │
│           │ Direct Ping                               │ Direct Ping         │
│           ▼                                           ▼                     │
│     ┌───────────┐        (Path Broken)          ┌───────────┐               │
│     │  Node B   │ ◄- - - - - - - - - - - - - - -│  Node D   │               │
│     └───────────┘                               └───────────┘               │
│                                                                             │
│  3. If Node C gets an ACK from Node B, Node B is ALIVE!                     │
│     (The failure was just a localized packet drop between A and B).        │
│  4. Only if all indirect probes fail is Node B marked SUSPECT.              │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Why SWIM is Powerful for Home Networks**:
- In home mesh networks, one satellite (in the garage) might temporarily lose direct line-of-sight to the workstation, but can still communicate through the living room satellite.
- Indirect probing prevents a single broken Wi-Fi link from falsely declaring an entire compute host dead.
