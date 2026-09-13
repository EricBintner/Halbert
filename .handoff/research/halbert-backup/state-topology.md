# State Topology: What Lives Where in the Singular Entity Model

**Date**: 2026-09-12

---

## 1. The Two-Node Architecture

In Halbert's singular entity model, one node is the **canonical host** (typically the always-on Home Assistant server) and others are **bodies** (workstation, laptop, etc.). The canonical host holds the authoritative copies of identity and conversation state. Bodies are proxied clients.

```
┌──────────────────────────────────────────────────────────────────────┐
│                        SINGULAR ENTITY                               │
│                                                                      │
│  ┌─────────────────────────────┐    ┌─────────────────────────────┐  │
│  │   CANONICAL HOST (HA server)│    │   BODY (Workstation)        │  │
│  │                             │    │                             │  │
│  │  ■ PersonaMemoryStore (auth)│◄───│  ○ PeerMemoryBackend (proxy)│  │
│  │  ■ conversation.db (auth)   │◄───│  ○ PeerConversationStore    │  │
│  │  ■ peers.json (credentials) │    │  ■ state_ledger.db (local)  │  │
│  │  ■ being.yml (persona)      │    │  ■ timeline.db (local)      │  │
│  │  ■ body.key (this node DID) │    │  ■ body.key (this node DID) │  │
│  │  ■ state_ledger.db (local)  │    │  ■ being.yml (peer config)  │  │
│  │  ■ timeline.db (local)      │    │  ■ ObservationStore (local) │  │
│  │  ■ ObservationStore (local) │    │                             │  │
│  │  ■ findings.db (local)      │    │  ■ findings.db (local)      │  │
│  └─────────────────────────────┘    └─────────────────────────────┘  │
│                                                                      │
│  ■ = Authoritative data on this node                                 │
│  ○ = HTTP proxy to canonical host (no local copy)                    │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 2. State Classification

### 2A. Replicated / Centralized State (Lives on Canonical Node Only)

| Store | What It Holds | How Satellites Access It |
|---|---|---|
| **PersonaMemoryStore** | Learned facts about the user (interests, preferences, biographical facts, opinions). The entity's autobiography. | `PeerMemoryBackend` — HTTP proxy. Writes are forwarded over bearer-token-authed `POST`. Reads are forwarded the same way. **No local copy on the satellite.** |
| **conversation.db** | All conversation threads, turns, messages, receipts, somatic blocks, open loops. | `PeerConversationStore` — HTTP proxy via `POST /api/conversations/invoke`. Atomic leaf operations (`get_or_open_thread`, `move_leaf`) execute in `BEGIN IMMEDIATE` on the server. **No local copy on the satellite.** |

**Implication**: If a satellite body dies, **zero conversation history or persona memory is lost**. The satellite was only a client proxy.

### 2B. Host-Local State (Must Be Backed Up Per Node)

| Store | What It Holds | Location |
|---|---|---|
| **Cryptographic Identity (`body.key`)** | Ed25519 private key generating the node's `did:key` identity. The DID *is* the body — regenerating a key creates a different body and permanently breaks attribution history. | `~/.local/state/halbert/keys/body.key` (file tier) or macOS Keychain / Linux Secret Service |
| **Machine State Ledger (`state_ledger.db`)** | Host-bound config changes, file hashes, and change provenance triples with mandatory `reason` and `actor`. | `~/.local/share/halbert/state_ledger.db` |
| **Timeline (`timeline.db`)** | 90-day append-only event ledger: `ha_state_change`, `frigate_event`, `scanner_finding`, `proposal`, `occupancy_change`, `cognitive_tick`. | `~/.local/share/halbert/timeline.db` |
| **Observation Search Index** | Vector/search index over what *this specific body* observed and indexed. Deliberately NOT proxied — a peer's index is not this body's index. | `~/.local/share/halbert/observations.db` |
| **Node Configuration** | `being.yml` (body name, persona, voice, `peer_token`, `canonical_*_url`), `models.yml`, `preferences.yml` | `~/.config/halbert/` |
| **Peer Credentials (`peers.json`)** | SHA-256 hashes of paired peer bearer tokens, endpoint URLs, capabilities, WoL config. Raw tokens are NEVER persisted on disk (M14 invariant). | `~/.config/halbert/peers.json` |
| **Findings (`findings.db`)** | Active and resolved system findings for this host. | `~/.local/share/halbert/findings.db` |

### 2C. Derived / Rebuildable State (Exclude from Backups)

| Asset | Why It's Excluded |
|---|---|
| **Foundation model weights** (`.gguf`, `.safetensors`) | Commodity downloads. 10–70 GB. Re-downloaded from HuggingFace/Ollama on demand. |
| **Vault Markdown projections** (`vault/`) | Deterministically rebuilt from `state_ledger.db` via `halbert vault-rebuild`. |
| **Python venv, node_modules, Rust target/** | Package manager artifacts. |
| **Config canon mirrors** (`data/config/raw/`, `data/config/canon/`) | Rebuilt by `snapshot.py` on next scan. |
| **SQLite `-wal` and `-shm` sidecars** | Transient. Flushed via `PRAGMA wal_checkpoint(TRUNCATE)` before backup. |
| **Cache directories** (`~/.cache/halbert/`) | Volatile. |

---

## 3. Node Death Scenarios

### Scenario A: Satellite / Body Dies
**Impact**: Trivial.
- Persona memory and conversation threads are safe on the canonical host.
- Re-pairing a replacement machine: install Halbert, run the 4-digit PIN pairing handshake, set `role: "body"` and `entity-mode: singular`.
- The new machine gets a new `body.key` (new DID) and body name.
- Local state ledger and timeline for the old body are lost (host-local by design).

### Scenario B: Canonical Host Dies (Catastrophic)
**Impact**: Critical under the current architecture if unbacked.
- The canonical host is the single point of failure for the unified autobiography (`PersonaMemoryStore`) and all conversation threads (`conversation.db`).
- Satellite bodies fail soft: `PeerConversationUnavailable` raised, memory writes dropped, nodes degrade to local-only.
- **To restore**, you need:
  1. All SQLite databases from the canonical host's data directory.
  2. `being.yml` (persona definitions, security tier config).
  3. `peers.json` (peer credential hashes). If lost, all satellite bearer tokens become invalid and every satellite must re-pair.
  4. `body.key` (node identity). If lost, the node becomes a *different* entity from an attribution perspective.

### Scenario C: Both Die (Total Loss)
**Impact**: Without a backup archive, the entity — its memories, personality tuning, conversation history, and learned preferences — is permanently lost. Hardware is replaceable. Identity is not.

---

## 4. The Peer Sync Asymmetry

A critical architectural observation: **PeerMemoryBackend and PeerConversationStore are live HTTP proxies, not replication engines.** They exist to give satellites real-time access to the canonical store. They do not maintain local replicas, journals, or offline caches.

This means:
- When the canonical host is healthy, satellite operations work seamlessly.
- When the canonical host goes down, satellites immediately lose access to memory and conversation history.
- When the canonical host's storage fails permanently, there is no satellite-side copy to promote.

This is the gap the State Vault must fill.

---

## 5. Technical Review (2026-09-12)

**Reviewer**: Verified against `halbert_core/` and `Haloysius/` source.

### 5.1 PersonaMemoryStore is JSON, not SQLite

Section 2A lists `PersonaMemoryStore` as holding "Learned facts about the user" and the active-passive doc proposes replicating it as `memory_v2.db`. But the actual storage is a **JSON file** (`memories.json`), confirmed at `Haloysius/src/haloysius/memory_v2/store.py:149-152`:

```python
def _get_data_path(self) -> Path:
    data_dir = state_dir("personas", self.persona_id)
    return data_dir / "memories.json"
```

The store loads all memories into an in-memory dict on init and flushes to JSON. There is no SQLite database for persona memory. The `observations.db` (SQLite, in `observation_store.py`) is the FTS5 search index, which is body-local and deliberately not proxied (`cognition_wiring.py:228-252`).

**Fix**: Update the table in section 2A to say the store is backed by `memories.json` (JSON file), not a SQLite database. The `PeerMemoryBackend` proxies `smart_add`/`search` calls over HTTP to the canonical host's `PersonaMemoryStore`, which reads/writes the JSON file.

### 5.2 `conversation.db` → `conversations.db` (plural)

Section 2A and the topology diagram use `conversation.db` (singular). The actual file is `conversations.db` (plural), at `halbert_core/agents/conversation_sqlite.py:150`:
```python
resolved = Path(data_dir()) / "conversations.db"
```

**Fix**: Global rename to `conversations.db`.

### 5.3 `state_ledger.db` and `timeline.db` are correctly classified as host-local — but the active-passive doc contradicts this

Section 2B correctly classifies `state_ledger.db` and `timeline.db` as host-local. The code confirms this:
- `state_store.py:11-12`: "No `persona_id`. Halbert is the machine; there is exactly one subject of these facts. Memory is host-bound."
- `timeline.py:108-118`: defaults to `~/.local/share/halbert/timeline.db` (per-body)
- `cognition_wiring.py:228-252`: `ObservationStore` is "deliberately **not** proxied"

However, `active-passive-replication.md` section 2 includes `state_ledger.db` in the replication set (`memory_v2.db`, `conversation.db`, `state_ledger.db`). This is a contradiction. The review of that document (section 6.3) flags and corrects it.

**No fix needed here** — this document is correct. The contradiction is in the active-passive doc.

### 5.4 Stale pairing flow reference

Section 3, Scenario A says: "Re-pairing a replacement machine: install Halbert, run the 4-digit PIN pairing handshake."

The pairing flow has been hardened (SE-16 / R10-F1, confirmed in `dashboard/routes/peers.py:135-144`):
- `PairResponse` returns **no PIN** — the PIN is shown only on the host's local-admin screen
- An explicit **approval step** is required before the verify endpoint will issue a token
- The verify endpoint rejects with **403 Forbidden** if not approved

**Fix**: Change "run the 4-digit PIN pairing handshake" to "run the pairing handshake (request → approve on host → verify)".

### 5.5 `peers.json` stores SHA-256 hashes — confirmed correct

Section 2B says `peers.json` stores "SHA-256 hashes of paired peer bearer tokens" and "Raw tokens are NEVER persisted on disk (M14 invariant)." Confirmed accurate at `federation/peers_config.py:18-21`:
> *Each satellite gets its own token... Tokens are stored as SHA-256 hashes — the raw token is never persisted to disk.*

No fix needed.

### 5.6 `body.key` is Ed25519 — confirmed correct

Section 2B says `body.key` is an "Ed25519 private key generating the node's `did:key` identity." Confirmed at `crypto/storage.py:47-53` (imports `ED25519` from `haloysius.integrity`) and `crypto/storage.py:253` (keychain stores "Private key for this body's did:key identity").

No fix needed.

### 5.7 `being.yml` has both `canonical_memory_url` and `canonical_thread_url`

The topology diagram shows `being.yml (peer config)` on the body but doesn't mention that it contains two separate canonical URLs:
- `canonical_memory_url` — for `PeerMemoryBackend` (`being_config.py:267`)
- `canonical_thread_url` — for `PeerConversationStore` (`being_config.py:271`)

Both are needed for a satellite to proxy to the canonical host. The promotion flow (in the active-passive doc) must clear both.

**Fix**: Add `canonical_thread_url` to the body's `being.yml` entry in the topology diagram.
