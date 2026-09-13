# Peer Authentication, Trust Roots & Zero-Trust Clustering for Local Networks

**Location**: `.handoff/research/multi-node-systems/01-AUTH-AND-ZERO-TRUST-CLUSTERING.md`  
**Date**: 2026-09-12  
**Focus**: Mutual node authentication, cryptographic identity, PAKE pairing handshakes, and transport encryption across untrusted home LANs.

---

## 1. The Home Network Threat Model

Modern smart homes and home labs are no longer single-tenant, perimeter-secured enclaves. A realistic home network contains:
- **High-vulnerability IoT appliances** (smart bulbs, cheap IP cameras, robot vacuums) running unpatched vendor firmware on shared Wi-Fi.
- **Guest and personal devices** (smartphones, visiting laptops) that may carry malware or ad-trackers.
- **Unsegmented LAN topology**: In >85% of households, all devices share a single `/24` broadcast domain, enabling trivial ARP spoofing, DHCP poisoning, and promiscuous packet capture.

> [!CAUTION]
> **The Fallacy of the Trusted LAN**: Treating local network traffic as inherently benign ("it's on 192.168.1.x, so it doesn't need encryption") completely invalidates the privacy and security guarantees of an AI agent. If a satellite node sends prompt text, tool invocations, or biometric voice data over cleartext HTTP, any compromised smart plug or script-kiddie device on the LAN can intercept user secrets.

### Threat Vectors Against Local Multi-Node Agents:

| Vector | Mechanism | Impact on Agent Cluster |
|---|---|---|
| **Eavesdropping / Packet Sniffing** | Promiscuous mode Wi-Fi capture, ARP cache poisoning (`arpspoof`). | Intercepts private conversation turns, user secrets, system configurations, and raw audio. |
| **Token Theft & Impersonation** | Sniffing cleartext HTTP `Authorization: Bearer <token>` headers. | Attacker acquires permanent control of the compute endpoint and can execute sensitive MCP tools. |
| **Rogue Node Insertion** | Malicious device broadcasting mDNS `_halbert._tcp` service. | Satellite connects to attacker's fake compute node, leaking all user queries and system context. |
| **Man-in-the-Middle (MITM)** | Intercepting initial unauthenticated pairing handshake. | Attacker establishes sessions with both nodes, recording all subsequent traffic. |
| **Replay Attacks** | Re-sending captured tool execution or state change requests. | Unauthorized execution of physical home automation or system commands. |

---

## 2. Audit of Halbert's Current Pairing & Auth Code

Halbert's current federation layer (`halbert_core/federation/peers_config.py`, `dashboard/routes/peers.py`) laid solid conceptual groundwork (per-peer tokens, SHA-256 token hashing on the host, 60s PIN expiration, attempt limits). However, an audit reveals critical cryptographic vulnerabilities:

```
CURRENT FLOW IN CODE (dashboard/routes/peers.py):

Satellite Node                                          Desktop (Compute Host)
     │                                                            │
     │ 1. POST /api/peers/pair (cleartext HTTP)                   │
     ├───────────────────────────────────────────────────────────►│ (Generates 4-digit PIN: "4821")
     │ ◄──────────────────────────────────────────────────────────┤
     │    200 OK {"request_id": "req-123", "status": "pending"}   │
     │                                                            │
     │ [User manually enters PIN on satellite UI]                 │
     │                                                            │
     │ 2. POST /api/peers/verify (cleartext HTTP!)                │
     │    {"request_id": "req-123", "pin": "4821"}               │
     ├───────────────────────────────────────────────────────────►│ (Matches PIN)
     │                                                            │ (Generates 32-byte hex token)
     │ 3. 200 OK {"token": "a1f90b...", "status": "paired"}      │
     │ ◄──────────────────────────────────────────────────────────┤
     │                                                            │
     ▼                                                            ▼
Stores raw token in plain JSON                            Stores SHA-256(token)
(~/.config/halbert/peers.json)                            (~/.config/halbert/peers.json)
```

### Critical Vulnerabilities in Current Code:
1. **Cleartext PIN on the Wire**: In Step 2, the satellite sends `pin: "4821"` in a plaintext HTTP POST body. Anyone sniffing the network learns the PIN instantly.
2. **Cleartext Bearer Token**: In Step 3, the host returns the raw 32-byte secret token over plaintext HTTP. Once sniffed, the token grants perpetual access.
3. **No Mutual Authentication**: The satellite has no cryptographic assurance that the endpoint answering `/api/peers/verify` is the legitimate host and not an attacker spoofing the IP address.
4. **Static Credentials**: The bearer token never expires or rotates unless manually revoked.

---

## 3. Cutting-Edge Pairing: Password-Authenticated Key Exchange (PAKE)

How do modern zero-trust IoT standards (like Apple HomeKit and the Connectivity Standards Alliance **Matter** specification) solve zero-config device pairing without certificates or pre-shared keys?

They use **Augmented PAKE (Password-Authenticated Key Exchange)** — specifically **SPAKE2+ (RFC 9383)** or **CPace (RFC 9497)**.

```
PAKE PROPERTY:
Even if an adversary records every byte of network traffic during pairing,
they CANNOT perform an offline dictionary attack to guess the PIN.
Every guess requires an active, online interaction that can be rate-limited and locked out.
```

### 3.1 SPAKE2+ (RFC 9383) Mechanics

SPAKE2+ operates over an elliptic curve group (typically `Ed25519` or `P-256`):
- **Parties**: Prover (Satellite entering PIN) and Verifier (Host displaying PIN).
- **Setup**: The PIN $P$ is converted into two group elements $(w_0, w_1)$ using a password-hashing function (Argon2id or PBKDF2). The Verifier stores only $w_0$ and $L = w_1 \cdot P$ (a public point). The Verifier *never stores the raw password or $w_1$*.
- **Exchange (1 Round Trip)**:
  1. Satellite generates ephemeral keypair $x$, computes $X = x \cdot G + w_0 \cdot M$ (where $M$ is a fixed domain point). Sends $X$ to Host.
  2. Host generates ephemeral keypair $y$, computes $Y = y \cdot G + w_0 \cdot N$ (where $N$ is a fixed domain point). Sends $Y$ to Satellite.
  3. Both parties compute the shared Diffie-Hellman secret $K = x \cdot y \cdot G$ by subtracting out $w_0$.
  4. Both parties derive confirmation MACs. If the PIN was correct, both parties now possess a high-entropy, cryptographically strong 256-bit symmetric session key $K$.
- **Result**:
  - The PIN was **never transmitted**.
  - A passive listener sees only pseudo-random points $X$ and $Y$.
  - An active attacker attempting to guess the PIN must interact online; after 3 failed attempts, the host aborts and invalidates the session.

### 3.2 Comparison of Pairing Protocols

| Protocol | Standard | Used In | Security Proof | CPU Cost (Pi 5) | Halbert Fit |
|---|---|---|---|---|---|
| **SPAKE2+** | RFC 9383 | Matter (CSA), Apple HomeKit PASE | Formally verified (Bellare-Pointcheval) | < 2 ms | **Ideal (Gold Standard)** |
| **CPace** | RFC 9497 | IETF CFRG balanced PAKE | Highly efficient, simple | < 1.5 ms | Excellent alternative |
| **SRP-6a** | RFC 5054 | Legacy Apple HomeKit, TLS-SRP | Aging design, complex modular math | ~8 ms | Deprecated in modern standards |
| **Magic Wormhole** | SPAKE2 + Transit | CLI file transfer | Robust, but requires transit relay | ~3 ms | Over-engineered for pure LAN |

---

## 4. Secure Transport & Mutual Authentication: mTLS vs. Noise Protocol

Once pairing establishes initial trust, what transport protocol should nodes use for day-to-day communication?

```
TWO COMPETING ZERO-TRUST LAN ARCHITECTURES:

Architecture A: Mutual TLS (mTLS 1.3)          Architecture B: Noise Protocol Framework
┌──────────────────────────────────────┐       ┌──────────────────────────────────────┐
│ Standard HTTPS/REST/SSE stack        │       │ Raw TCP / Encrypted Framing          │
│ Local Certificate Authority (CA)     │       │ Static Public Key Pinning (Ed25519)  │
│ X.509 Node Certificates              │       │ Noise_IK or Noise_XX Handshake       │
│ Natively supported by FastAPI / curl │       │ WireGuard-like cryptographic minimal │
└──────────────────────────────────────┘       └──────────────────────────────────────┘
```

### 4.1 Architecture A: Mutual TLS 1.3 with an Automated Local CA

In an mTLS 1.3 architecture:
1. When Halbert initializes on the **Canonical Host**, it generates an **Internal Root CA** (ECDSA P-256 or Ed25519, self-signed, 10-year validity).
2. The Root CA private key is stored securely in the host's hardware custody ladder (`crypto/storage.py`).
3. During the SPAKE2+ pairing handshake:
   - The satellite sends its public key and a Certificate Signing Request (CSR) over the encrypted PAKE channel.
   - The Canonical Host signs the CSR, issuing a **Node Operational Certificate (NOC)** valid for this specific `node_id`.
   - The Host sends back the signed NOC along with the Root CA certificate.
4. **All Subsequent HTTP Calls**:
   - The FastAPI backend listens on HTTPS with `ssl_context.verify_mode = ssl.CERT_REQUIRED`.
   - The satellite HTTP client (`requests` / `httpx` with `client.cert = ("node.crt", "node.key")`, `verify="root_ca.crt"`) connects.
   - The TLS 1.3 handshake verifies both client and server certificates.
   - Traffic is encrypted with AES-256-GCM or ChaCha20-Poly1305.

**Advantages**:
- Works out-of-the-box with standard HTTP, SSE (Server-Sent Events) for token streaming, and WebSockets.
- Standard tools (browsers, curl, Python `requests`, Rust `reqwest`, Tauri HTTP) natively understand TLS certificates.
- Zero custom wire framing.

### 4.2 Architecture B: Noise Protocol Framework (Noise_IK / Noise_XX)

The **Noise Protocol Framework** (Trevor Perrin, 2018) is the cryptographic foundation behind WireGuard, Lightning Network, and libp2p. Instead of X.509 certificates and ASN.1 parsing, Noise operates on raw 32-byte Curve25519 public keys.

- **`Noise_XX` Pattern (Mutual Discovery & Authentication)**:
  Used when neither node knows the other's static key beforehand (1.5 round trips):
  ```
  -> e               (Initiator sends ephemeral key)
  <- e, ee, s, es    (Responder sends ephemeral + encrypted static key)
  -> s, se           (Initiator sends encrypted static key)
  ```
  Both identities are hidden from eavesdroppers, and forward secrecy is guaranteed.
- **`Noise_IK` Pattern (Known Host Key)**:
  Used after pairing when the satellite already has the host's pinned public key (1 round trip):
  ```
  -> e, es, s, ss    (Initiator sends ephemeral + encrypted static key, authed against host's known key)
  <- e, ee, se       (Responder responds with ephemeral key; session established)
  ```

**Advantages**:
- Extremely lightweight (<100 lines of code in Python or Rust).
- Immune to X.509 certificate parsing bugs and expiration handling.
- Cryptographically elegant, identical to WireGuard.

**Trade-off**: Requires running over custom TCP sockets or tunneling HTTP over a raw encrypted stream.

---

## 5. Cryptographic Node Identity & Capability Delegation

Halbert already assigns each node an **Ed25519 cryptographic identity key** (`body.key`) formatted as a Decentralized Identifier (`did:key:z6M...`). This key is currently used only for signing audit logs (`crypto/storage.py`).

### 5.1 Node Identity Binding

We must elevate `body.key` into the **root of node identity for networking**:
- When node $A$ pairs with node $B$, they exchange and cryptographically pin their `did:key` values.
- In `peers.json`, the record becomes:
  ```json
  {
    "node_id": "living-room-pi",
    "did": "did:key:z6MkiTBz1ymuepAQ4HEHYSF1H8quG5GLWEmGoL8q2H28XoEa",
    "public_key_b64": "O2m6N8...=",
    "endpoint": "https://192.168.1.50:8000",
    "capabilities": ["voice", "home_tools"],
    "paired_at": "2026-09-12T12:00:00Z"
  }
  ```
- Every incoming request must be cryptographically bound to that DID — either via the mTLS client certificate CN/SAN or via HTTP Signatures (RFC 9421).

### 5.2 Attenuated Capability Tokens (Beyond Static Bearer Tokens)

Static bearer tokens have a fatal flaw: once issued, they are all-or-nothing and valid indefinitely. If an attacker gains read access to `peers.json` on a low-security satellite (e.g. a Pi in the garage), they gain full admin power over the Mac Studio.

Modern distributed systems use **Attenuated Capability Tokens** (such as **Biscuit** or **Macaroons**):
- A capability token is cryptographically signed by the Canonical Host.
- **Offline Attenuation**: The satellite itself (or the host) can append caveats (restrictions) to the token *without talking to the server*.
- **Caveat Examples**:
  ```datalog
  // Token issued to Living Room Pi
  right("compute", "infer");
  check if operation == "chat_completion";
  check if model in ["qwen2.5:32b", "llama3.3:70b"];
  check if time < 2026-09-13T00:00:00Z;
  deny if tool in ["execute_bash", "write_system_config"];
  ```
- The compute host verifies the cryptographic signature and executes the Datalog logic. Even if the garage satellite is compromised, the attacker cannot execute shell tools or access secrets because the capability token strictly forbids it.

---

## 6. Recommended Architecture for Halbert

To satisfy Halbert's **Haloysius subtractive contract** (minimal dependencies, zero heavy external daemons) while achieving enterprise-grade zero-trust security:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    RECOMMENDED ZERO-TRUST PAIRING & AUTH                    │
│                                                                             │
│  Satellite Node                                     Canonical Host          │
│  ┌─────────────────────────┐                        ┌─────────────────────┐ │
│  │ 1. Discover host via    │                        │ 1. Announce via     │ │
│  │    mDNS (_halbert._tcp) │                        │    mDNS with TXT rec│ │
│  │                         │                        │                     │ │
│  │ 2. SPAKE2+ PAKE Handshake (RFC 9383 over ephemeral TLS or Noise)       │ │
│  │    User types 6-digit numeric PIN shown on Host UI.                    │ │
│  │    Mutual key agreement -> 256-bit ephemeral master secret derived.     │ │
│  │                                                                        │ │
│  │ 3. Mutual Identity Pinning:                                            │ │
│  │    - Satellite sends its Ed25519 body.key public DID.                  │ │
│  │    - Host signs a 90-day Node Certificate or Pins the DID.             │ │
│  │    - Host mints an attenuated Capability Token (scoped permissions).   │ │
│  │                                                                        │ │
│  │ 4. Day-to-Day Operations:                                              │ │
│  │    - Mutual TLS 1.3 on all REST/SSE endpoints.                         │ │
│  │    - Host verifies client cert matches pinned DID.                     │ │
│  │    - Auto-rotation: Certificate renewed automatically every 30 days.   │ │
│  └─────────────────────────┘                        └─────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Key Implementation Decisions:
1. **Replace Cleartext PIN with SPAKE2+**: Implement a lightweight Python SPAKE2+ exchange in `halbert_core/federation/crypto_pake.py` using `cryptography` (already available). PIN is never sent over the wire.
2. **mTLS 1.3 for API Transport**: Configure FastAPI (`uvicorn` with `ssl_version=PROTOCOL_TLS_SERVER`, `cert_reqs=CERT_REQUIRED`) and client HTTP sessions with mutually verified certificates.
3. **DID Key Pinning**: Bind every peer record in `peers_config.py` to the peer's permanent `did:key`. Reject any connection where the presented public key does not match the pinned DID.
4. **Attenuated Capability Scopes**: Replace raw `token: str` with a scoped, time-bounded JWT or Biscuit token carrying explicit tool allowlists and 30-day expiration with rolling refresh.
