# DISPATCH: Multi-Node Systems Phase 1 — Zero-Trust Pairing, Daemon mTLS & Resilient State

**Owner:** Multi-Node / Federation Session  
**Parent Roadmap Rows:** `LD-1` (Linked Devices journey), `HOME-1` (Home body), `TRUST-1` (One trust chain)  
**Parent Research:** [`.handoff/research/multi-node-systems/`](file:///Volumes/4TB-BAD/Halbert/.handoff/research/multi-node-systems/README.md) (`01-AUTH`, `02-DATABASES`, `03-COMPUTE`, `04-NETWORK`, `05-SCOPING`)  
**Evidence IDs:** `SE-15`, `SE-16`, `R10-F1` (PIN handshake), `C1` (MCP/peer auth), `C4` (redaction boundary), `M14` (per-peer token revocation), `LD-1` (two-process test).

---

## 1. Shared Rules & Constraints

1. **Test Environment Requirement**:
   - Python tests **MUST** be run with `arch -arm64`:
     ```bash
     arch -arm64 .venv/bin/python -m pytest halbert_core/tests/federation halbert_core/tests/test_peer*
     ```
   - From a git worktree, use `./wt_pytest.py`:
     ```bash
     arch -arm64 ./wt_pytest.py halbert_core/tests/federation
     ```
2. **Commit Conventions**:
   - Never add `Co-Authored-By`, "Generated with …", or any bot attribution trailer. Subject and body only.
3. **Haloysius Subtractive Contract**:
   - **Exactly two hard dependencies** (`pyyaml>=6.0`, `requests>=2.31.0`).
   - Do **NOT** add third-party PAKE or mTLS packages from PyPI. `cryptography` (v50.0.1) is already in the virtual environment — implement SPAKE2+ and certificate handling directly using `cryptography.hazmat` and standard library `ssl`.
4. **Transport Boundary Rule**:
   - **mTLS is strictly daemon-to-daemon (inter-node)**.
   - The local frontend (Tauri/browser) **always** connects to its own local Halbert backend on loopback (`http://127.0.0.1:8000`) without client certs.
   - Cross-node requests (compute offload, state sync, peer tools) are executed daemon-to-daemon via `requests` / `httpx` with `cert=("node.crt", "node.key")`.
5. **Model & Voice Rules**:
   - `apple-foundation` and `secure_model` are **never** offered to peers (`DECISIONS.md` 2026-08-30). Peers get `ollama` and `vllm` only.
   - Never name or recommend AI models on user surfaces; connection slots, not model menus.
   - The system speaks as the computer itself, first person, grounded in measured data — never as an assistant. Never write "Sovereign" on user-facing surfaces.

---

## 2. File Ownership Map

Developers working on this dispatch own:
- `halbert_core/halbert_core/federation/crypto_pake.py` *(NEW)*
- `halbert_core/halbert_core/federation/peers_config.py`
- `halbert_core/halbert_core/federation/peer_middleware.py`
- `halbert_core/halbert_core/federation/compute_endpoint.py`
- `halbert_core/halbert_core/federation/compute_broker.py`
- `halbert_core/halbert_core/dashboard/routes/peers.py`
- `halbert_core/halbert_core/agents/peer_conversation_store.py`
- `halbert_core/halbert_core/mcp/response.py`
- `halbert_core/halbert_core/dashboard/frontend/src/lib/peerApi.ts`
- `halbert_core/tests/federation/*`
- `halbert_core/tests/test_peer_pairing_security.py`
- `halbert_core/tests/test_peer_conversation_store.py`

Do **NOT** edit:
- `halbert_core/halbert_core/agents/state_machine.py` (owned by core turn loop)
- `halbert_core/halbert_core/capabilities.py` (owned by gating spine)
- `shared-tokens/tokens.css` (design system tokens)

---

## 3. Tasks

### Task 1: SPAKE2+ PAKE Module (`crypto_pake.py`) [P0 — Security]

**File**: `halbert_core/halbert_core/federation/crypto_pake.py` *(NEW)*  
**Research Reference**: `01-AUTH-AND-ZERO-TRUST-CLUSTERING.md` §3 (RFC 9383)

1. Implement the SPAKE2+ (or CPace) protocol over curve Ed25519/X25519 using `cryptography.hazmat`:
   - `Spake2Prover(pin: str, client_id: str, server_id: str)`
   - `Spake2Verifier(pin: str, client_id: str, server_id: str)`
2. Expose a clean 2-step exchange interface:
   - Step 1: Client computes ephemeral public point $X$; Server computes ephemeral public point $Y$.
   - Step 2: Both parties compute shared key $K = \text{HKDF}(x \cdot y \cdot G)$ and exchange confirmation MACs ($\text{HMAC}(K, \text{"client_confirm"})$ and $\text{HMAC}(K, \text{"server_confirm"})$).
3. If confirmation MACs match, both parties output derived 256-bit `session_key`.
4. If confirmation fails (wrong PIN), raise `PakeAuthenticationFailed` and purge state.
5. **Unit Tests**: `tests/federation/test_crypto_pake.py`:
   - Both sides with matching PIN derive identical `session_key`.
   - Mismatched PIN raises `PakeAuthenticationFailed`.
   - Mathematical transcript contains zero cleartext PIN material.

---

### Task 2: Upgrade Pairing Routes to PAKE Handshake [P0 — Security]

**Files**:
- `halbert_core/halbert_core/dashboard/routes/peers.py`
- `halbert_core/halbert_core/dashboard/frontend/src/lib/peerApi.ts`
- `halbert_core/tests/test_peer_pairing_security.py`  
**Research Reference**: `01-AUTH-AND-ZERO-TRUST-CLUSTERING.md` §2, §6

1. **Update Wire Models**:
   - `POST /api/peers/pair`:
     - Satellite requests pairing, sending its node ID, role, capabilities, and `did:key`.
     - Host generates 6-digit numeric PIN, stores PAKE verifier state, returns `request_id` (NO PIN, NO TOKEN).
   - Host Operator Action:
     - Operator visits Settings › Linked Devices on the host machine (`127.0.0.1`).
     - Reads the 6-digit PIN and clicks **Approve** (`POST /api/peers/pending/{rid}/approve`).
   - `POST /api/peers/verify`:
     - Satellite sends `{request_id, pake_client_point, pake_client_mac, node_id}`.
     - **NO raw PIN is sent over the wire**. The PIN was used locally to compute the PAKE point and MAC.
     - Host verifies PAKE state. On success, returns `{pake_server_point, pake_server_mac, encrypted_credential}`.
2. **Preserve All 13 Existing Invariants in `test_peer_pairing_security.py`**:
   - PIN never returned to requester.
   - Approval is local-admin only.
   - 3 wrong PIN attempts permanently purge request.
   - 60s TTL and 16-request bounds.
   - Peer revocation remains surgical.

---

### Task 3: Daemon-to-Daemon Mutual TLS 1.3 Transport [P1 — Transport]

**Files**:
- `halbert_core/halbert_core/crypto/storage.py`
- `halbert_core/halbert_core/federation/peers_config.py`
- `halbert_core/halbert_core/model/providers/peer.py`
- `halbert_core/halbert_core/agents/peer_conversation_store.py`  
**Research Reference**: `01-AUTH-AND-ZERO-TRUST-CLUSTERING.md` §4.1

1. **Local Root CA Initialization**:
   - On Canonical Host startup, ensure `<data_dir>/keys/internal_ca.crt` and `internal_ca.key` exist.
   - Custody ladder follows `crypto/storage.py` (Keychain / Secret Service / `0600` file).
2. **Node Certificate Minting**:
   - During SPAKE2+ pairing, the satellite generates a keypair and sends a CSR inside the encrypted PAKE payload.
   - Host signs a 90-day client certificate with `CN = node_id` and SAN `URI = did:key:...`.
   - Satellite stores certificate and private key in its local data directory.
3. **HTTP Client Configuration**:
   - `PeerProvider` and `PeerConversationStore` configure `requests.Session` (or `httpx`) with:
     ```python
     session.cert = (str(cert_path), str(key_path))
     session.verify = str(ca_cert_path)
     ```
4. **Peer Identity Pinning**:
   - Host endpoint validates client certificate against `internal_ca.crt` and asserts `CN` matches pinned `did:key` in `peers.json`.

---

### Task 4: Sliding-Window Lookahead Redactor for Streaming Responses [P1 — Streaming]

**Files**:
- `halbert_core/halbert_core/mcp/response.py`
- `halbert_core/halbert_core/federation/compute_endpoint.py`  
**Research Reference**: `03-SHARED-COMPUTE-AND-INFERENCE-DISPATCH.md` §6

1. In `halbert_core/mcp/response.py`, implement `SlidingWindowRedactor`:
   - Maintains an unreleased buffer of 32 characters.
   - Scans incoming token stream for partial secret prefixes (`sk-`, `ghp_`, `did:key:`, `BEGIN PRIVATE KEY`, etc.).
   - If buffer is clean, releases leading text up to the lookahead boundary.
   - If partial match is suspected, holds buffer until pattern completes or fails match.
   - If pattern matches, replaces secret text with `<secret>` and releases.
2. In `compute_endpoint.py`:
   - Enable `stream: true` on `/api/compute/v1/chat/completions`.
   - Pipe Ollama/vLLM SSE chunks through `SlidingWindowRedactor` before yielding to the network.
3. **Test**: `tests/federation/test_streaming_redaction.py`:
   - Stream tokens where an API key is split across 3 chunks (`"sk-pr"`, `"oj-9x"`, `"1234"`).
   - Assert the emitted SSE stream contains `<secret>` and zero cleartext fragments.

---

### Task 5: Satellite Local Read Cache & Offline Staging Queue [P1 — Resilience]

**File**: `halbert_core/halbert_core/agents/peer_conversation_store.py`  
**Research Reference**: `02-SHARED-REDUNDANT-DATABASES-AND-STATE.md` §5, §6

1. Convert `PeerConversationStore` from a pure RPC proxy into a **Read-Local / Staged-Write Store**:
   - **Local Mirror**: Maintain a lightweight SQLite replica `~/.local/share/halbert/conversation_replica.db` on the satellite.
   - **Reads** (`get_thread`, `list_messages`, `current_open_thread`): Read directly from `conversation_replica.db` (0ms latency, zero network roundtrips).
   - **Writes** (`append_message`, `create_thread`):
     - If host is reachable: Forward write to host via mTLS; update local replica upon 200 OK.
     - If host is unreachable (Wi-Fi blip or host sleeping):
       - Do **NOT** raise `PeerConversationUnavailable` to crash the conversation.
       - Write turn to local replica with `sync_status = 'staged'`.
       - Append write payload to `local_staging.db`.
2. **Background Flush**:
   - When connection to host is restored, flush pending operations from `local_staging.db` in chronological order.
   - Handle concurrent turns using DAG branch grafting (both turns become siblings; no turn is clobbered).

---

### Task 6: Two-Process Integration Test (`SE-28` / `LD-1`) [P0 — Verification]

**File**: `halbert_core/tests/federation/test_two_node_lifecycle.py` *(NEW)*

Write an automated end-to-end integration test running two `TestClient` instances with separate data directories:
1. **Node 1 (Host)** boots on scratch config.
2. **Node 2 (Satellite)** boots on separate scratch config.
3. Satellite discovers Host via mock mDNS.
4. Execute SPAKE2+ pairing handshake with 6-digit PIN and host approval.
5. Verify mTLS certificates and pinned DIDs are saved in both configs.
6. Satellite executes an interactive chat turn offloaded to Host's compute endpoint with streaming redaction.
7. Pause Host process (simulate sleep).
8. Satellite performs a conversation turn: assert local turn succeeds and stages into `local_staging.db` without raising `PeerConversationUnavailable`.
9. Resume Host process: assert staged turn syncs to Host.

---

## 4. Proposed `DECISIONS.md` Ratification Rows

Add the following rows to [`DECISIONS.md`](file:///Volumes/4TB-BAD/Halbert/DECISIONS.md) under `## Implemented per default — needs ratification`:

```markdown
| 2026-09-12 | `SEC-PAKE` | Peer pairing uses SPAKE2+ (RFC 9383) over Ed25519; numeric PIN is never transmitted over the wire; brute-force attacks locked after 3 attempts. Supersedes cleartext PIN exchange in routes/peers.py. | pending |
| 2026-09-12 | `SEC-mTLS` | Inter-node daemon-to-daemon communication requires Mutual TLS 1.3 with an internal Canonical Root CA; certificates are pinned to the node's Ed25519 body.key DID. Local dashboard loopback is unaffected. | pending |
| 2026-09-12 | `REPL-HYBRID` | Multi-node state replication uses a hybrid model: append-only event logs sync via G-Set union; conversation turns sync via DAG branch merging; satellites maintain local read caches with offline staging queues. Full Raft consensus is rejected to prevent 2-node cluster deadlocks during host sleep. | pending |
| 2026-09-12 | `COMP-STREAM` | Remote compute streaming chunks pass through a 32-character sliding-window lookahead redaction filter before wire emission to enforce deterministic Tier 2 secret scrubbing across chunk boundaries. | pending |
```

---

## 5. Definition of Done

1. `crypto_pake.py` implemented and unit-tested using standard `cryptography` library.
2. All 13 tests in `test_peer_pairing_security.py` pass with zero regressions under the new PAKE handshake.
3. No cleartext PIN or static unencrypted bearer token ever crosses the network wire.
4. Inter-node REST and SSE requests communicate over mTLS 1.3 with client certificate validation.
5. Streaming token redaction passes split-token secret leakage tests.
6. Satellite `PeerConversationStore` survives host reboot/sleep without raising `PeerConversationUnavailable`.
7. Full Python suite passes with `arch -arm64 .venv/bin/python -m pytest halbert_core/tests`.
