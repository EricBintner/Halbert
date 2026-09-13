# DISPATCH v2: Multi-Node Systems — TLS Transport, Streaming Redaction, Resilient State

**Owner:** Multi-Node / Federation Session
**Parent Roadmap Rows:** `LD-1` (Linked Devices journey), `HOME-1` (Home body), `TRUST-1` (One trust chain)
**Parent Research:** [`.handoff/research/multi-node-systems/`](research/multi-node-systems/README.md) (01-AUTH, 02-DATABASES, 03-COMPUTE, 04-NETWORK, 05-SCOPING)
**Review Authority:** [`.handoff/research/multi-node-systems/HANDOFF-REVIEW-2026-09-12.md`](research/multi-node-systems/HANDOFF-REVIEW-2026-09-12.md) — supersedes the research docs where they conflict
**Supersedes:** `DISPATCH-MULTI-NODE-SYSTEMS-2026-09-12.md` (v1 — reintroduced three issues the review caught)
**Evidence IDs:** `SE-15`, `SE-16`, `R10-F1` (PIN handshake — already fixed), `C1` (MCP/peer auth), `C4` (redaction boundary), `M14` (per-peer token revocation), `LD-1` (two-process test)

---

## 0. What changed from v1 and why

v1 was written from the original research docs without incorporating the review. It reintroduced three problems the review had already caught, plus had issues of its own. This version resolves all of them:

| v1 decision | Problem | v2 decision |
|---|---|---|
| Hand-roll SPAKE2+ using `cryptography.hazmat` | `cryptography` provides EC primitives, not the SPAKE2+ protocol. Hand-rolling PAKE is the highest-risk crypto approach. | **Drop PAKE for v1.** TLS + the existing approval gate closes the cleartext gap. PAKE deferred to a future phase if the threat model demands it. |
| Full internal Root CA + mTLS + 90-day certs + 30-day rotation | Enterprise PKI for a 2-3 node home cluster. The review said use pinned keys. | **Self-signed certs + fingerprint pinning.** No CA, no rotation machinery. One cert per node, pinned in `peers.json`. |
| `SlidingWindowRedactor` in `mcp/response.py` | Creates a second redaction implementation alongside the registry. Violates the single-choke-point invariant. | **`SlidingWindowRedactor` in `security/result_redaction.py`.** Wraps the existing `SecretVariantRegistry` + `redact_text` pattern pass. One implementation, one choke point. |
| `cryptography` treated as "already available" | It's an optional extra (`integrity` group), not a hard dep. Federation would crash on import without it. | **Guard all `cryptography` imports.** Degrade gracefully: no cert generation without it, fall back to plaintext HTTP with a warning. |
| `crypto/storage.py` in file ownership for Task 3 | Hub file other systems depend on. | **Don't touch `crypto/storage.py`.** TLS keys live in a new `federation/tls.py` with its own storage path. |
| DAG branch grafting in Task 5 | Underspecified, larger than Tasks 1-4 combined. | **Split into 5a (read cache + staging) and 5b (DAG grafting, deferred).** Ship 5a first. |

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
   - `cryptography` (v50.0.1) is an **optional extra** (in the `integrity` group at `pyproject.toml:96-99`), not a hard dep. All `cryptography` imports in federation code must be guarded. If absent, TLS cert generation is skipped and the node falls back to plaintext HTTP with a logged warning. The `ssl` module from the standard library is always available for TLS transport itself.

4. **Transport Boundary Rule**:
   - **TLS is strictly daemon-to-daemon (inter-node).**
   - The local frontend (Tauri/browser) **always** connects to its own local Halbert backend on loopback (`http://127.0.0.1:8000`) without client certs.
   - Cross-node requests (compute offload, state sync, peer tools) are executed daemon-to-daemon via `requests.Session` configured with a pinned SSL context.

5. **Redaction Invariant**:
   - Redaction has **one choke point**: `ingestion/redaction_registry.py` (exact-value `SecretVariantRegistry`) + `ingestion/redaction.py` (pattern-based `redact_text`), enforced at `security/display_transport.py` (UI) and `security/result_redaction.py` (tool/MCP results).
   - The `SlidingWindowRedactor` is a **buffering adapter** over these existing implementations, not a new redaction implementation. It lives in `security/result_redaction.py` alongside `redact_result`.

6. **Model & Voice Rules**:
   - `apple-foundation` and `secure_model` are **never** offered to peers (`DECISIONS.md` 2026-08-30). Peers get `ollama` and `vllm` only.
   - Never name or recommend AI models on user surfaces; connection slots, not model menus.
   - The system speaks as the computer itself, first person, grounded in measured data — never as an assistant. Never write "Sovereign" on user-facing surfaces.

---

## 2. File Ownership Map

**Files this dispatch owns (may edit):**

| File | Task |
|------|------|
| `halbert_core/halbert_core/federation/tls.py` *(NEW)* | Task 1 — cert generation, SSL context factory |
| `halbert_core/halbert_core/federation/peers_config.py` | Task 1 — add `tls_pin` field to `PeerCredential` |
| `halbert_core/halbert_core/model/providers/peer.py` | Task 1 — `requests.Session` with pinned SSL context |
| `halbert_core/halbert_core/federation/compute_router.py` | Task 1 — pinned session in health probe |
| `halbert_core/halbert_core/dashboard/app.py` | Task 1 — uvicorn SSL config |
| `halbert_core/halbert_core/dashboard/routes/peers.py` | Task 1 — return cert fingerprint during pairing |
| `halbert_core/halbert_core/dashboard/frontend/src/lib/peerApi.ts` | Task 1 — handle https:// endpoint |
| `halbert_core/halbert_core/security/result_redaction.py` | Task 2 — `SlidingWindowRedactor` class |
| `halbert_core/halbert_core/federation/compute_endpoint.py` | Task 2 — enable streaming, pipe through redactor |
| `halbert_core/halbert_core/agents/resilient_peer_store.py` *(NEW)* | Task 3 — `ResilientPeerConversationStore` wrapper |
| `halbert_core/halbert_core/agents/threads.py` | Task 3 — inject wrapper at `_create_conversation_store` |
| `halbert_core/tests/federation/test_tls_transport.py` *(NEW)* | Task 1 tests |
| `halbert_core/tests/federation/test_streaming_redaction.py` *(NEW)* | Task 2 tests |
| `halbert_core/tests/federation/test_resilient_peer_store.py` *(NEW)* | Task 3 tests |
| `halbert_core/tests/federation/test_two_node_lifecycle.py` *(NEW)* | Task 4 integration test |
| `halbert_core/tests/test_peer_pairing_security.py` | Task 1 — verify no regressions |

**Files this dispatch does NOT edit:**

| File | Why |
|------|-----|
| `halbert_core/halbert_core/agents/state_machine.py` | Owned by core turn loop |
| `halbert_core/halbert_core/capabilities.py` | Owned by gating spine |
| `shared-tokens/tokens.css` | Design system tokens |
| `halbert_core/halbert_core/crypto/storage.py` | Custody ladder — TLS keys are separate from audit signing keys. TLS key storage is handled by `federation/tls.py`. |
| `halbert_core/halbert_core/ingestion/redaction_registry.py` | The redaction registry is the single source of truth. The streaming adapter wraps it; it does not modify it. |
| `halbert_core/halbert_core/ingestion/redaction.py` | Same — pattern redaction is wrapped, not modified. |
| `halbert_core/halbert_core/mcp/response.py` | Thin delegate to `result_redaction.py`. The streaming redactor lives in `result_redaction.py`, not here. |
| `halbert_core/halbert_core/agents/peer_conversation_store.py` | The RPC proxy stays as-is. The resilient wrapper composes it; it does not modify it. |
| `halbert_core/halbert_core/agents/conversation_sqlite.py` | The local cache reuses `SqliteConversationStore` as-is at a different path. No schema changes. |

---

## 3. Architecture Decisions (with rationale)

### AD-1: Drop PAKE for v1 — use TLS + existing approval gate

**Decision:** Do not implement SPAKE2+ or any PAKE protocol in this dispatch. Add TLS with self-signed certs + fingerprint pinning instead.

**Rationale:**
- The original research's pairing audit was stale. The PIN is already NOT returned in the `PairResponse` (fixed via SE-16/R10-F1). An explicit approval step (`/api/peers/pending/{rid}/approve`) is required before the verify endpoint issues a token. The only remaining vulnerability is cleartext transport.
- TLS closes that gap: the PIN in the verify request and the bearer token in the response are both encrypted.
- `cryptography` does not provide SPAKE2+ — only EC primitives. The `spake2` PyPI package (warner) implements SPAKE2 (symmetric) but NOT SPAKE2+ (augmented). The `spake2plus` package (jiep) implements RFC 9383 but adds `ecpy` as a second dependency. `noiseprotocol` is abandoned (last release 2020).
- Hand-rolling SPAKE2+ is the highest-risk crypto engineering approach. A subtle bug in point blinding or MAC derivation silently breaks the security guarantee.
- The existing approval gate (operator clicks Approve on the host) provides a social authentication layer that PAKE would replace, not augment. With TLS, an active MITM must break the TLS handshake or present a fake cert — fingerprint pinning prevents the latter.
- For a 2-3 node home cluster, TLS + approval is adequate. PAKE is deferred to a future phase if the threat model demands resistance to active MITM during the initial cert exchange.

**What this means for the pairing flow:** The wire contract stays the same (pair → approve → verify). The only change is that the HTTP transport switches from `http://` to `https://` with pinned self-signed certs. The satellite receives the host's cert fingerprint during pairing and pins it in `peers.json`.

### AD-2: Self-signed certs + fingerprint pinning, no CA

**Decision:** Each node generates a self-signed certificate. The cert fingerprint is exchanged during pairing and pinned in `peers.json`. No internal Root CA, no CSR signing, no certificate rotation.

**Rationale:**
- A CA is enterprise PKI machinery (Root CA key, CSR flow, cert signing, revocation lists, rotation schedules) for a 2-3 node home cluster. The review flagged this as over-engineered.
- Self-signed certs with fingerprint pinning provide the same mutual authentication guarantee: each side verifies the other's cert matches the pinned fingerprint. No CA trust chain needed.
- Cert generation uses `cryptography` (optional). If absent, the operator can supply PEM files manually, or the node runs plaintext HTTP with a warning.
- The existing `body.key` Ed25519 identity is for audit-log signing, not transport. TLS keys are separate, stored under `~/.local/state/halbert/peer-tls/`. Reusing `body.key` for TLS would couple audit key loss to peer-link breakage.

### AD-3: SlidingWindowRedactor in result_redaction.py, wrapping the existing registry

**Decision:** The streaming redaction adapter lives in `security/result_redaction.py` as `SlidingWindowRedactor`. It wraps `SecretVariantRegistry.redact_text` + `ingestion.redaction.redact_text` — the same two-pass redaction that `redact_string` already uses. It does not reimplement matching.

**Rationale:**
- v1 put `SlidingWindowRedactor` in `mcp/response.py`, creating a second redaction implementation. AGENTS.md is explicit: "Redaction — `ingestion/redaction_registry.py`, enforced at the response choke point in `security/display_transport.py`." One implementation, multiple enforcement points.
- `result_redaction.py` already houses `redact_result` and `redact_string`. The streaming adapter is a natural extension: it buffers chunks, runs the same `redact_string` on the accumulated window, and releases the safe prefix.
- `mcp/response.py` stays a thin delegate. `compute_endpoint.py` imports `SlidingWindowRedactor` from `result_redaction.py` (or through `mcp/response.py` as a re-export if the import surface matters).

### AD-4: ResilientPeerConversationStore wrapper, not PeerConversationStore modification

**Decision:** Create a `ResilientPeerConversationStore` wrapper class that composes `PeerConversationStore` (the RPC proxy) + `SqliteConversationStore` (the local cache). Do not modify either underlying class.

**Rationale:**
- `PeerConversationStore` is a clean RPC proxy with ~45 methods. Modifying it to add caching would entangle transport logic with cache logic.
- `SqliteConversationStore` already has a complete, versioned schema (`_REFERENCE_SCHEMA`, `SCHEMA_VERSION = 5`) with `ALTER TABLE` migration. The local cache reuses it at a different path — no new DDL.
- The wrapper has the same method names and signatures as `PeerConversationStore`, so `ThreadManager` requires no changes. It's injected at `_create_conversation_store()` in `threads.py:1389-1419`.
- `PeerConversationUnavailable` is currently NOT caught anywhere at runtime — it propagates all the way up and crashes the conversation. The wrapper catches it and degrades to local cache + staging queue.

### AD-5: Defer DAG branch grafting and full state replication

**Decision:** This dispatch implements read-through cache + offline staging queue only. DAG branch grafting for concurrent turns, G-Set event log sync, and cr-sqlite active-active replication are all deferred.

**Rationale:**
- DAG branch grafting is underspecified and larger than the other three tasks combined. It needs its own design doc.
- cr-sqlite is a native SQLite extension (`.so`/`.dylib`) — a platform-specific compiled binary that violates the subtractive contract if made a hard dep. Making it an optional extra is possible but adds build complexity. Pure-Python G-Set sync for event logs is viable but is a separate feature, not a prerequisite for the read cache.
- The read cache + staging queue solves the immediate problem: satellite crashes when the host sleeps or Wi-Fi blips. That's the highest user-value item.

---

## 4. Tasks

### Task 1: TLS Transport with Self-Signed Certs + Fingerprint Pinning [P0 — Security]

**Files:**
- `halbert_core/halbert_core/federation/tls.py` *(NEW)*
- `halbert_core/halbert_core/federation/peers_config.py`
- `halbert_core/halbert_core/model/providers/peer.py`
- `halbert_core/halbert_core/federation/compute_router.py`
- `halbert_core/halbert_core/dashboard/app.py`
- `halbert_core/halbert_core/dashboard/routes/peers.py`
- `halbert_core/halbert_core/dashboard/frontend/src/lib/peerApi.ts`
- `halbert_core/tests/federation/test_tls_transport.py` *(NEW)*
- `halbert_core/tests/test_peer_pairing_security.py`

**Research Reference:** `01-AUTH-AND-ZERO-TRUST-CLUSTERING.md` §4, `HANDOFF-REVIEW-2026-09-12.md` (AD-1, AD-2)

#### 1.1 Cert generation (`federation/tls.py`)

```python
def ensure_node_cert(data_dir: Path) -> tuple[Path, Path]:
    """Ensure a self-signed TLS cert exists for this node.

    Returns (cert_path, key_path). Uses cryptography (optional) to generate
    if absent. If cryptography is not installed, raises and the caller falls
    back to plaintext HTTP with a warning.
    """
```

- Cert is self-signed, CN = node_id, valid 10 years (no rotation — home cluster, not enterprise).
- Stored at `~/.local/state/halbert/peer-tls/node.crt` and `node.key` (0600).
- Uses `cryptography.x509.CertificateBuilder` — guarded import. If `cryptography` is absent, the function raises `TLSUnavailable` and the caller logs a warning and continues on HTTP.

```python
def make_client_ssl_context(cert_path: Path, key_path: Path, pinned_peer_cert: Optional[Path] = None) -> ssl.SSLContext:
    """Build an SSLContext for the client side (satellite → host).

    If pinned_peer_cert is given, loads it as the only trusted CA (fingerprint
    pinning via a single-cert trust store). If None, uses CERT_REQUIRED with
    the system store (for the initial pairing before a cert is pinned).
    """
```

```python
def make_server_ssl_context(cert_path: Path, key_path: Path, ca_cert_path: Optional[Path] = None) -> ssl.SSLContext:
    """Build an SSLContext for the server side (host receiving peer requests).

    If ca_cert_path is given, sets CERT_REQUIRED to enforce client cert
    validation. If None, sets CERT_OPTIONAL (accept but don't require client
    certs — for the initial pairing handshake).
    """
```

```python
def cert_fingerprint(cert_path: Path) -> str:
    """Return the SHA-256 fingerprint of the cert for pinning in peers.json."""
```

#### 1.2 PeerCredential changes (`peers_config.py`)

Add two fields to `PeerCredential`:

```python
tls_enabled: bool = False          # Whether TLS is active for this peer
tls_pin: Optional[str] = None      # SHA-256 fingerprint of the peer's cert
```

Persist and load them in `_load` / `_save` (additive — existing peers without these fields default to `tls_enabled=False`).

#### 1.3 HTTP client changes (`peer.py`, `compute_router.py`)

Replace direct `requests.get` / `requests.post` with a `requests.Session` that mounts a custom `HTTPAdapter` carrying the pinned `ssl.SSLContext`.

In `peer.py`:
```python
def __init__(self, ...):
    ...
    self._session = requests.Session()
    if peer_tls_enabled and peer_cert_path:
        ctx = make_client_ssl_context(
            cert_path=self_cert_path,
            key_path=self_key_path,
            pinned_peer_cert=peer_cert_path,
        )
        adapter = requests.adapters.HTTPAdapter()
        adapter.ssl_version = ssl.PROTOCOL_TLS_CLIENT
        # Mount the SSL context via a custom HTTPAdapter
        self._session.mount("https://", PinnedSSLAdapter(ctx))
        self._endpoint = endpoint.replace("http://", "https://")
    else:
        self._session = requests.Session()
        self._endpoint = endpoint
```

Same pattern in `compute_router.py`'s `_http_health_probe`.

Note: `requests` does not expose `SSLContext` directly on `HTTPAdapter` in all versions. The `PinnedSSLAdapter` may need to override `init_poolmanager` to pass `ssl_context=` to `urllib3.PoolManager`. Verify the `requests`/`urllib3` version in the venv supports this.

#### 1.4 Server-side TLS (`dashboard/app.py`)

When starting uvicorn, pass `ssl_certfile` and `ssl_keyfile` if the node cert exists:

```python
ssl_kwargs = {}
cert_path, key_path = ensure_node_cert(data_dir)
if cert_path and key_path:
    ssl_kwargs = {
        "ssl_certfile": str(cert_path),
        "ssl_keyfile": str(key_path),
        "ssl_version": ssl.PROTOCOL_TLS_SERVER,
    }
uvicorn.run(app, host=host, port=port, **ssl_kwargs)
```

The server accepts both HTTPS (peer) and HTTP (loopback) connections. For v1, if TLS is enabled, the server listens on HTTPS only. The local frontend connects via `http://127.0.0.1:8000` — this may require a separate plaintext listener or a Tauri-side exception for loopback. **Investigate whether uvicorn can serve both HTTP and HTTPS on the same port (it cannot — TLS is negotiated at connection time).** Options: (a) two listeners (8000 HTTP for loopback, 8001 HTTPS for peers), (b) Tauri connects via HTTPS with cert bypass for loopback, (c) peers use a different port. **Recommendation: option (a) — two listeners, loopback stays plaintext, peers use HTTPS on a separate port.** This preserves the transport boundary rule cleanly.

#### 1.5 Pairing flow changes (`peers.py`)

The pairing flow stays the same (pair → approve → verify). The only addition:

- `POST /api/peers/pair` response includes the host's cert fingerprint (`tls_pin`) so the satellite knows what to pin.
- The satellite stores `tls_pin` in its `peers.json` during pairing.
- `POST /api/peers/verify` is sent over HTTPS (with the host's cert pinned) instead of HTTP.

No PAKE, no CSR, no cert signing. The satellite generates its own self-signed cert independently.

#### 1.6 Frontend changes (`peerApi.ts`)

- Handle `https://` endpoints in the peer URL.
- Allow the user to paste an `https://` URL in the manual pairing form (Tailscale path).
- No cert validation UI needed for v1 — pinning is automatic during pairing.

#### 1.7 Tests (`test_tls_transport.py`)

- Cert generation produces a valid self-signed cert with the correct CN.
- `cert_fingerprint` is deterministic and SHA-256.
- `make_client_ssl_context` with a pinned cert rejects a different cert.
- `make_client_ssl_context` with a pinned cert accepts the matching cert.
- `ensure_node_cert` is idempotent (second call returns existing cert).
- If `cryptography` is not importable, `ensure_node_cert` raises `TLSUnavailable` (mock the import).
- All 13 tests in `test_peer_pairing_security.py` pass with no regressions.

---

### Task 2: Streaming Redaction via SlidingWindowRedactor [P1 — Security]

**Files:**
- `halbert_core/halbert_core/security/result_redaction.py`
- `halbert_core/halbert_core/federation/compute_endpoint.py`
- `halbert_core/tests/federation/test_streaming_redaction.py` *(NEW)*

**Research Reference:** `03-SHARED-COMPUTE-AND-INFERENCE-DISPATCH.md` §6, `HANDOFF-REVIEW-2026-09-12.md` (AD-3)

#### 2.1 SlidingWindowRedactor (`security/result_redaction.py`)

```python
class SlidingWindowRedactor:
    """Buffering adapter for streaming redaction across chunk boundaries.

    Wraps the existing two-pass redaction (SecretVariantRegistry.redact_text
    + ingestion.redaction.redact_text) — the same passes that redact_string
    uses. Does NOT reimplement matching.

    Usage:
        redactor = SlidingWindowRedactor()
        for chunk in stream:
            safe = redactor.feed(chunk)
            if safe:
                yield safe
        tail = redactor.flush()
        if tail:
            yield tail
    """

    def __init__(
        self,
        window_size: int = 48,  # longer than any known secret prefix
    ):
        self._buffer: str = ""
        self._window_size = window_size

    def feed(self, chunk: str) -> str:
        """Accept a new chunk. Return the prefix that is safe to emit.

        Holds back the trailing window_size characters so secrets that span
        chunk boundaries can still be caught by the redaction passes.
        """
        self._buffer += chunk
        if len(self._buffer) <= self._window_size:
            return ""  # Not enough to release anything yet

        # Split: release everything except the hold-back window
        release_len = len(self._buffer) - self._window_size
        to_release = self._buffer[:release_len]
        self._buffer = self._buffer[release_len:]

        # Run the same two-pass redaction as redact_string
        return redact_string(to_release)

    def flush(self) -> str:
        """Drain the hold-back at stream end. Returns any remaining safe text."""
        remaining = self._buffer
        self._buffer = ""
        return redact_string(remaining)
```

Key design rules:
- **Delegates to `redact_string`** — does not call `SecretVariantRegistry` or `redact_text` directly. One implementation, one choke point.
- **Window size 48** — longer than any known secret prefix (`sk-proj-`, `ghp_`, `BEGIN PRIVATE KEY`, `did:key:z6M...`). The exact-value registry matches full secret values, so the window must be large enough to hold a complete secret that straddles a chunk boundary. 48 is a heuristic; make it configurable.
- **No pattern reimplemention** — if the registry or pattern pass changes, the streaming adapter automatically benefits.

#### 2.2 Compute endpoint streaming (`compute_endpoint.py`)

Currently `compute_endpoint.py` calls `call_llm_chat(..., stream=False)` and returns a full `ChatCompletionResponse`. The TODO at lines 62-67 explicitly calls out that streaming will need a buffering redaction filter.

Changes:
1. Add a `stream` parameter to the compute endpoint (`POST /api/compute/v1/chat/completions`).
2. When `stream=True`, call `call_llm_chat(..., stream=True)` and iterate the async generator.
3. Pipe each chunk through `SlidingWindowRedactor.feed()`.
4. Yield SSE chunks with the redacted text.
5. Call `flush()` at stream end and yield the final chunk.

```python
from ..security.result_redaction import SlidingWindowRedactor

async def _stream_to_broker(...):
    redactor = SlidingWindowRedactor()
    async for chunk in call_llm_chat(..., stream=True):
        safe = redactor.feed(chunk)
        if safe:
            yield {"choices": [{"delta": {"content": safe}}]}
    tail = redactor.flush()
    if tail:
        yield {"choices": [{"delta": {"content": tail}}]}
```

**Verify first:** `call_llm_chat` with `stream=True` — does it return an async iterator? The subagent flagged this as an open question. Check `model/client.py` before implementing.

#### 2.3 Tests (`test_streaming_redaction.py`)

- Feed chunks where an API key is split across 3 chunks (`"sk-pr"`, `"oj-9x"`, `"1234"`). Assert the emitted stream contains `<secret>` and zero cleartext fragments.
- Feed chunks where no secret is present. Assert the output equals the input (no data loss).
- Feed a secret that starts at the beginning of a chunk and ends in the next. Assert it's caught.
- Feed a secret that exactly spans the window boundary. Assert it's caught.
- Feed an empty stream. Assert `flush()` returns `""`.
- Feed a stream shorter than the window. Assert `feed()` returns `""` and `flush()` returns the redacted content.

---

### Task 3: Resilient Peer Conversation Store [P1 — Resilience]

**Files:**
- `halbert_core/halbert_core/agents/resilient_peer_store.py` *(NEW)*
- `halbert_core/halbert_core/agents/threads.py` (inject wrapper at `_create_conversation_store`)
- `halbert_core/tests/federation/test_resilient_peer_store.py` *(NEW)*

**Research Reference:** `02-SHARED-REDUNDANT-DATABASES-AND-STATE.md` §5, §6, `HANDOFF-REVIEW-2026-09-12.md` (AD-4, AD-5)

#### 3.1 ResilientPeerConversationStore wrapper

```python
class ResilientPeerConversationStore:
    """Wraps PeerConversationStore with a local SQLite cache and offline staging.

    Same public method names and signatures as PeerConversationStore —
    ThreadManager requires no changes.

    Reads: try peer first, mirror to local cache on success, fall back to
    local cache on PeerConversationUnavailable.

    Writes: try peer first, mirror to local on success. On
    PeerConversationUnavailable, apply locally and stage the invocation
    for later flush.
    """

    def __init__(
        self,
        peer: PeerConversationStore,
        cache_path: Path,
    ):
        self.peer = peer
        self.local = SqliteConversationStore(str(cache_path))
        self._ensure_staging_tables()
        self._flush_lock = threading.Lock()
```

#### 3.2 Staging tables (in the cache DB)

```sql
CREATE TABLE IF NOT EXISTS staged_invocation (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    enqueued_at   REAL NOT NULL,
    method        TEXT NOT NULL,
    args_json     TEXT NOT NULL DEFAULT '[]',
    kwargs_json   TEXT NOT NULL DEFAULT '{}',
    attempts      INTEGER NOT NULL DEFAULT 0,
    next_retry_at REAL NOT NULL,
    last_error    TEXT
);

CREATE TABLE IF NOT EXISTS local_peer_id_map (
    local_id      INTEGER NOT NULL,
    entity_type   TEXT NOT NULL,  -- 'message', 'open_loop', ...
    peer_id       INTEGER,
    resolved_at   REAL,
    PRIMARY KEY (local_id, entity_type)
);
```

#### 3.3 Read path

For every read method (see classification below):
1. Try `getattr(self.peer, method)(*args, **kwargs)`.
2. On success, mirror the result into `self.local` (best-effort — if the mirror fails, log and continue; the cache will be stale but the read succeeded).
3. On `PeerConversationUnavailable`, read from `self.local` instead.
4. If the local cache also has no data, return the store's falsy default (`None`, `False`, `[]`).

**Read methods** (safe to serve from cache): `get`, `list_conversations`, `search`, `get_thread`, `list_threads`, `current_open_thread`, `unresolved_request`, `list_messages`, `recent_messages`, `last_turn_id`, `pending_notes`, `list_turns`, `search_receipts`, `search_snippets`, `list_somatic_blocks`, `get_terminal_block`, `list_terminal_blocks`, `get_terminal_session`, `list_terminal_sessions`, `list_open_loops`.

**Note on `search` methods:** `search`, `search_receipts`, `search_snippets` use FTS indexes. The local cache maintains its own FTS (SqliteConversationStore creates them at open). Results may differ between local and peer — that's acceptable for a degraded fallback.

#### 3.4 Write path

For every write method:
1. Try `getattr(self.peer, method)(*args, **kwargs)`.
2. On success, mirror the result into `self.local` and return.
3. On `PeerConversationUnavailable`:
   - Apply the same operation to `self.local` so `ThreadManager` sees its own write immediately.
   - Insert the invocation envelope into `staged_invocation`.
   - For methods that generate IDs (`append_message`, `add_open_loop`), insert a `local_peer_id_map` row with `peer_id = NULL`.
   - Return the local result (e.g. the local `message_id`).

**Write methods:** `create`, `get_or_create`, `save`, `delete`, `append_message`, `update_message`, `mark_in_progress_interrupted`, `create_thread`, `get_or_open_thread`, `update_thread`, `move_leaf`, `upsert_receipt`, `merge_thread`, `add_somatic_block`, `remove_somatic_block`, `insert_terminal_block`, `update_terminal_block`, `insert_terminal_session`, `update_terminal_session`, `add_open_loop`, `close_open_loop`, `migrate_terminal_block_ids_to_blocks`.

**Exception — `redact_message`:** Never stage. It must either succeed at the peer or raise `RedactionFailed`. On `PeerConversationUnavailable`, re-raise `PeerConversationUnavailable` (not `RedactionFailed`) — the redaction hasn't been attempted yet.

#### 3.5 Flush loop

The flush is driven by a background thread (started in `__init__`, stopped in `close`). It runs every 5 seconds when the staging queue is non-empty:

```python
def _flush_staged(self) -> None:
    with self._flush_lock:
        while True:
            row = self._next_staged()
            if row is None:
                return

            method, args, kwargs = self._decode_invocation(row)
            args, kwargs = self._rewrite_local_ids(method, args, kwargs)

            try:
                result = getattr(self.peer, method)(*args, **kwargs)
            except PeerConversationUnavailable:
                break  # Peer still down; try again next cycle
            except RedactionFailed:
                self._dead_letter(row, "RedactionFailed")
                continue
            except Exception as e:
                self._retry_with_backoff(row, e)
                continue

            self._capture_peer_ids(method, args, kwargs, result)
            self._delete_staged(row["id"])
```

Key rules:
- **Ordered FIFO** — one queue, stop on first `PeerConversationUnavailable`. `create_thread` must land before `append_message` for that thread.
- **ID rewriting** — `update_message(local_id, ...)` must be rewritten to `update_message(peer_id, ...)` using `local_peer_id_map`. If the `append_message` hasn't flushed yet, the `update_message` stays queued (retry).
- **Backoff** — exponential with cap at 300s. After 5 attempts, dead-letter (log + leave in queue for manual inspection).

#### 3.6 Integration (`threads.py`)

In `_create_conversation_store()` at `threads.py:1389-1419`, replace:

```python
return PeerConversationStore(peer_url=thread_url, bearer_token=token)
```

with:

```python
from .resilient_peer_store import ResilientPeerConversationStore
peer = PeerConversationStore(peer_url=thread_url, bearer_token=token)
cache_path = data_dir / "local_conversation_cache.db"
return ResilientPeerConversationStore(peer=peer, cache_path=cache_path)
```

No changes to `ThreadManager` — the wrapper has the same interface.

#### 3.7 Tests (`test_resilient_peer_store.py`)

- Patch `requests.post` to raise `ConnectionError`. Verify:
  - `append_message()` returns a local message ID (no crash).
  - `list_messages()` returns the locally-staged message.
  - The staging queue contains the pending invocation.
- Restore `requests.post`. Trigger flush. Verify:
  - The peer receives the `append_message` call.
  - `local_peer_id_map` records the peer-assigned message ID.
  - The staging queue is empty.
- Test `update_message` ID rewriting: stage `append_message` + `update_message` while offline, flush both, verify the `update_message` is sent with the peer-assigned ID.
- Test `redact_message` raises `PeerConversationUnavailable` (not staged) when the peer is down.
- Test ordered flush: stage `create_thread` + `append_message` while offline, flush, verify `create_thread` is sent first.
- Test backoff: patch `requests.post` to fail 3 times then succeed, verify exponential backoff and eventual success.

---

### Task 4: Two-Process Integration Test [P0 — Verification]

**File:** `halbert_core/tests/federation/test_two_node_lifecycle.py` *(NEW)*

Write an automated end-to-end integration test running two `TestClient` instances with separate data directories:

1. **Node 1 (Host)** boots on scratch config with TLS enabled.
2. **Node 2 (Satellite)** boots on separate scratch config with TLS enabled.
3. Satellite discovers Host via mock mDNS (or direct URL entry).
4. Execute pairing handshake: pair → approve → verify. Verify cert fingerprints are pinned in both `peers.json` files.
5. Satellite executes an interactive chat turn offloaded to Host's compute endpoint. Verify the response is redacted (no secret leakage).
6. Patch the satellite's `requests` to raise `ConnectionError` (simulate host sleep).
7. Satellite performs a conversation turn: assert it succeeds locally and stages into the staging queue without raising `PeerConversationUnavailable`.
8. Restore `requests`. Trigger flush. Assert the staged turn syncs to the host.

This is a smoke test covering the happy path. Edge cases (concurrent turns, split-brain, cert expiry) are separate focused tests, not part of this integration test.

---

## 5. Proposed DECISIONS.md Ratification Rows

Add to `DECISIONS.md` under `## Implemented per default — needs ratification`:

```markdown
| 2026-09-12 | `SEC-TLS` | Inter-node daemon-to-daemon communication uses TLS 1.3 with self-signed certificates and SHA-256 fingerprint pinning. No internal Root CA. The local dashboard loopback stays plaintext HTTP. PAKE (SPAKE2+) is deferred — TLS + the existing approval gate provides adequate security for a 2-3 node home cluster. | pending |
| 2026-09-12 | `REPL-CACHE` | Satellite conversation stores use a resilient wrapper with local SQLite read-through cache and offline staging queue. Full CRDT replication (cr-sqlite) and DAG branch grafting are deferred. The wrapper catches PeerConversationUnavailable and degrades to local cache + staging instead of crashing. | pending |
| 2026-09-12 | `COMP-STREAM` | Remote compute streaming chunks pass through a 48-character sliding-window redaction adapter (SlidingWindowRedactor in security/result_redaction.py) that wraps the existing SecretVariantRegistry + pattern redaction passes. No second redaction implementation. | pending |
```

Note: `SEC-TLS` replaces the v1 dispatch's `SEC-PAKE` and `SEC-mTLS` rows. `REPL-CACHE` replaces `REPL-HYBRID` (the full hybrid model is deferred). `COMP-STREAM` is revised to specify the adapter location.

---

## 6. Definition of Done

1. `federation/tls.py` implemented: cert generation, SSL context factory, fingerprint calculation. All `cryptography` imports guarded.
2. Peer transport uses `requests.Session` with pinned SSL context when TLS is enabled, falls back to plaintext HTTP with a warning when `cryptography` is absent.
3. All 13 tests in `test_peer_pairing_security.py` pass with no regressions.
4. `SlidingWindowRedactor` in `security/result_redaction.py` passes split-token secret leakage tests.
5. `compute_endpoint.py` supports `stream=True` with redacted SSE output.
6. `ResilientPeerConversationStore` survives host reboot/sleep without raising `PeerConversationUnavailable`. Staged writes flush on reconnection.
7. Two-process integration test passes.
8. Full Python suite passes: `arch -arm64 .venv/bin/python -m pytest halbert_core/tests`.

---

## 7. Deferred Items (not in this dispatch)

| Item | Why deferred | Revisit when |
|------|-------------|-------------|
| SPAKE2+ PAKE | TLS + approval gate closes the cleartext gap. PAKE adds complexity for a marginal gain. | Threat model demands resistance to active MITM during initial cert exchange. |
| Internal Root CA + mTLS | Enterprise PKI for a 2-3 node cluster. Self-signed + pinning is simpler. | Node count grows beyond 5, or manual cert management becomes a burden. |
| DAG branch grafting | Underspecified, larger than all other tasks combined. Needs its own design doc. | Two satellites concurrently create turns for the same thread while offline. |
| G-Set event log sync (timeline.db, state_ledger.db) | Separate feature, not a prerequisite for the read cache. | Multiple nodes need a shared timeline without a single canonical host. |
| cr-sqlite active-active replication | Native extension violates the subtractive contract as a hard dep. | A pure-Python CRDT approach is designed, or cr-sqlite is acceptable as an optional extra. |
| SWIM gossip protocol | Overkill at 2-3 nodes. 3-consecutive-failure hysteresis is adequate. | Node count grows beyond 5. |
| Warm standby failover / "Promote to Canonical" | Disaster recovery UX. Periodic snapshots are simpler for v1. | Snapshot approach proves insufficient for recovery needs. |
| Biscuit/Macaroon capability tokens | Existing per-peer bearer tokens with surgical revocation are adequate. | Fine-grained per-tool capability scoping is needed. |
