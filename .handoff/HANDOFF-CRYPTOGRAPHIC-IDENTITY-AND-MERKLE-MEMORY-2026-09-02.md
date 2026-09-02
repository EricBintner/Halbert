# SPEC & HANDOFF: Cryptographic Agent Identity and Signed Merkle Memory Logs

**Date:** 2026-09-02  
**Target:** AI Reviewer / Systems Engineer  
**Status:** ⛔ **REVIEWED 2026-09-02 — NOT APPROVED AS WRITTEN.** Superseded in part; see review banner below.  
**Parent Strategy:** 
- `documentation/experimental/SINGULAR-ENTITY-HOME-ASSISTANT-AND-HALBERTOS-ECOSYSTEM.md` (§ Identity & Memory Layer)
- `.handoff/HALOYSIUS-FRAMEWORK-GENERALIZATION-2026-08-22.md`
- `.handoff/CHROMADB-RETIREMENT-REFACTOR-2026-08-26.md`

---

> ### ⛔ Review outcome (2026-09-02) — read before implementing
>
> This spec was reviewed on the Haloysius side and **must not be implemented
> verbatim**.
>
> ### ➡️ Halbert's replacement work items live in
> [`.handoff/HANDOFF-INTEGRITY-PHASE1-AND-2-2026-09-02.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/HANDOFF-INTEGRITY-PHASE1-AND-2-2026-09-02.md) **§3**
> — corrected paths, ordering constraints, and the Phase 0 primitives
> (`haloysius.integrity`) that already shipped. Start there, not here.
>
> Full review, with reproductions:
> [`Haloysius/.handoff/REVIEW-CRYPTOGRAPHIC-IDENTITY-AND-MERKLE-MEMORY-2026-09-02.md`](file:///Volumes/4TB-BAD/Haloysius/.handoff/REVIEW-CRYPTOGRAPHIC-IDENTITY-AND-MERKLE-MEMORY-2026-09-02.md)
>
> **Summary of the outcome:**
> - **Per-node identity (§3.1A) — approved and promoted.** It fixes a live
>   weakness: `peer_backend.py` authenticates every body with one *shared*
>   bearer token, so writes cannot be attributed and one body cannot be revoked.
> - **Signed memory (§3.1B) — narrowed.** Sign at trust boundaries (peer sync,
>   export bundles), not on every local store write. A key held under the same
>   uid as the log is not a control against a local adversary.
> - **Merkle DAG (§3.1C) — deferred, and the reference code is unsafe.**
>   Executing it verbatim reproduces a CVE-2012-2459-class **root collision**
>   (`[A,B,C]` and `[A,B,C,C]` yield the same root), a **second-preimage**
>   (an internal node verifies as an included leaf), and **O(n²) appends**
>   (~20 s for 8k memories). It also has no anchor: nothing holds $R_t$ that
>   cannot rewrite the leaves.
> - **§1.1's storage premise is false for `memory_v2`.** Memory is a whole-file
>   JSON blob rewritten in place (`store.py:140-152`), not append-only JSONL.
>   Building that log is the real work and is unbudgeted here.
> - **§3.1B's `canonical_bytes` leaves 16 of 22 fields unsigned**, including
>   `believed` and `invented` — the truth-state fields.
> - **Ed25519 forecloses hardware custody.** Apple's Secure Enclave supports
>   only P-256; most TPMs likewise. The curve decision is entangled with
>   custody and must be made before Phase 1, not discovered in Phase 3.
>
> **Phases 3–4 below are superseded** by the resequenced plan in review §5.
> Three decisions (curve/custody, root anchor, erasure policy) gate the rest —
> review §6. Paths in §3.2 are one level shallow: everything is under
> `halbert_core/halbert_core/`.

---

## 1. System Context & Storage Architecture

### 1.1 Storage Foundation & ChromaDB Retirement Context
Halbert is actively phasing out legacy ChromaDB vector collections in favor of **SourcePrep** (chat RAG retrieval + code/concept indexing) and **SQLite / append-only JSONL files** (conversations and structured logs). 

**Constraint:** Under no circumstances should any new identity or memory integrity features introduce dependencies on ChromaDB. All cryptographic identity and Merkle memory structures must be pure-Python primitives with local JSONL/SQLite persistence.

### 1.2 Ecosystem Boundaries: Haloysius vs. Halbert
The design cleanly separates universal agent capabilities from app-specific OS operations:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    UNIVERSAL / HALOYSIUS ENGINE                         │
│                    (/Volumes/4TB-BAD/Haloysius)                         │
│  - Agnostic chat and memory engine (Strict Subtractive Contract)         │
│  - PersonaMemoryStore & TemporalStateLedger                             │
│  - Universal Cryptographic Identity (Ed25519 / did:key)                │
│  - Merkle Memory Tree & State Root Proofs ($R_t$)                       │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │ Imported via HaloysiusMemoryAdapter
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                       HALBERT APP SPECIFIC                              │
│                    (/Volumes/4TB-BAD/Halbert)                           │
│  - Sysadmin Persona & Execution Gating                                  │
│  - Hardware Discovery Scanners & Telemetry (hwmon, journald, dbus)      │
│  - Tool Execution Audit Log Signing (halbert_core/obs/audit.py)         │
│  - OS Keyring Storage (macOS Keychain / Linux Secret Service / 0600)    │
│  - Tauri Desktop Dashboard & CLI (halbert audit-verify)                 │
└─────────────────────────────────────────────────────────────────────────┘
```

* **Haloysius (Universal Engine):** Shared across all apps (Halbert, H2, H3). Must adhere strictly to the **Subtractive Contract** (hard dependencies limited to `pyyaml>=6.0`, `requests>=2.31.0`; heavy ML/DB dependencies remain lazy/optional).
* **Halbert (Application Layer):** Implements OS-level execution, hardware discovery, tool audit logging, secure host key custody, and Tauri desktop integration.

---

## 2. Current State vs. Target Gap Analysis

| Layer | Halbert Current State | Target Cryptographic State | Status / Gap |
| :--- | :--- | :--- | :--- |
| **Agent Identity** | Prompt strings (`AgentPromptBuilder._get_identity`) and config YAMLs. No cryptographic keys. | Ed25519 keypair managed via OS keystore / secure file. Deterministic W3C DID (`did:key:...`). | 🔴 **Missing** (Zero crypto identity built). |
| **Tool Execution Audit** | `halbert_core/obs/audit.py` generates daily JSONL files with SHA-256 hash chains (`prev_hash -> hash`). | Cryptographically signed JSONL records with agent/user signature + verification CLI. | 🟡 **Partial** (Hash chain exists, but is unsigned and tamperable by anyone with filesystem write access). |
| **Memory Integrity** | `PersonaMemory` (Haloysius) and `HybridMemorySystem` (Halbert) store memories as plain objects with UUIDs. | Each memory event contains `author_did`, `prev_hash`, signature, and Merkle leaf hash. | 🔴 **Missing** (Memory entries lack cryptographic integrity). |
| **Merkle Tree & State Roots** | No Merkle DAG or state root calculation in the codebase. | Pure-Python Merkle tree over memory epochs generating verifiable state root hashes ($R_t$) and inclusion proofs. | 🔴 **Missing** (No Merkle data structures). |
| **Cross-Device Portability** | Memory tied to local filesystem paths (`~/.local/share/halbert/`). | Signed and encrypted memory export bundles (`.halmem`) verifiable across nodes. | 🔴 **Missing** (Unbuilt). |

---

## 3. Technical Specifications

### 3.1 Universal Core Layer (`Haloysius`)

#### A. Cryptographic Identity (`haloysius/crypto/identity.py`)
Provides deterministic self-sovereign identity using Ed25519 and standard W3C `did:key` representation.

```python
"""
haloysius.crypto.identity
Pure-Python cryptographic identity using standard 'cryptography' package.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Optional
import base58  # or standard multibase encoding
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization


@dataclass(frozen=True)
class AgentIdentity:
    did: str                 # e.g. "did:key:z6MkuT5..."
    public_key_hex: str
    _private_key: Optional[ed25519.Ed25519PrivateKey] = None

    @classmethod
    def generate(cls) -> AgentIdentity:
        """Generate a new random Ed25519 keypair and derive did:key."""
        private_key = ed25519.Ed25519PrivateKey.generate()
        public_key = private_key.public_key()
        pub_bytes = public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw
        )
        # did:key multicodec prefix for ed25519-pub is 0xed01
        multicodec_bytes = b"\xed\x01" + pub_bytes
        did = f"did:key:z{base58.b58encode(multicodec_bytes).decode('ascii')}"
        return cls(did=did, public_key_hex=pub_bytes.hex(), _private_key=private_key)

    def sign(self, payload: bytes) -> str:
        """Sign bytes and return hex-encoded signature."""
        if not self._private_key:
            raise ValueError("Cannot sign without private key")
        return self._private_key.sign(payload).hex()

    def verify(self, payload: bytes, signature_hex: str) -> bool:
        """Verify signature against public key."""
        pub_bytes = bytes.fromhex(self.public_key_hex)
        public_key = ed25519.Ed25519PublicKey.from_public_bytes(pub_bytes)
        try:
            public_key.verify(bytes.fromhex(signature_hex), payload)
            return True
        except Exception:
            return False
```

#### B. Signed Persona Memory Extension (`haloysius/memory_v2/types.py`)
Extends `PersonaMemory` to support cryptographic signing and chaining.

```python
@dataclass
class PersonaMemory:
    id: str
    persona_id: str
    memory_type: MemoryType
    content: str
    emotional_weight: float = 0.5
    emotional_valence: float = 0.0
    believed: bool = True
    invented: bool = False
    occurred_at: Optional[float] = None
    source: str = "system_event"
    tags: List[str] = field(default_factory=list)
    triggered_by: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # Cryptographic integrity fields
    author_did: Optional[str] = None
    prev_hash: Optional[str] = None
    record_hash: Optional[str] = None
    signature: Optional[str] = None

    def canonical_bytes(self) -> bytes:
        """Deterministic serialization for hashing (excluding hash and signature)."""
        d = {
            "id": self.id,
            "persona_id": self.persona_id,
            "memory_type": self.memory_type.value if hasattr(self.memory_type, "value") else str(self.memory_type),
            "content": self.content,
            "occurred_at": self.occurred_at,
            "author_did": self.author_did,
            "prev_hash": self.prev_hash,
            "metadata": self.metadata,
        }
        import json
        return json.dumps(d, sort_keys=True, ensure_ascii=False).encode("utf-8")
```

#### C. Pure-Python Merkle DAG (`haloysius/memory_v2/merkle.py`)
Maintains an append-only tree of memory event hashes, producing verifiable state root hashes ($R_t$) and inclusion proofs.

```python
"""
haloysius.memory_v2.merkle
Incremental Merkle tree and inclusion proof generator for agent memory.
"""
from __future__ import annotations
import hashlib
from typing import List, Dict, Optional, Tuple


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class MerkleMemoryDAG:
    def __init__(self):
        self.leaves: List[str] = []      # List of leaf record_hashes
        self.tree_levels: List[List[str]] = []

    def append_leaf(self, record_hash: str) -> str:
        """Appends a memory record hash and recomputes the state root."""
        self.leaves.append(record_hash)
        self._rebuild_tree()
        return self.get_state_root()

    def _rebuild_tree(self) -> None:
        if not self.leaves:
            self.tree_levels = []
            return
        
        current_level = list(self.leaves)
        self.tree_levels = [current_level]
        
        while len(current_level) > 1:
            next_level = []
            for i in range(0, len(current_level), 2):
                left = current_level[i]
                right = current_level[i + 1] if i + 1 < len(current_level) else left
                combined = hashlib.sha256(f"{left}{right}".encode("utf-8")).hexdigest()
                next_level.append(combined)
            current_level = next_level
            self.tree_levels.append(current_level)

    def get_state_root(self) -> str:
        """Returns the current Merkle root hash (empty hash if no leaves)."""
        if not self.tree_levels or not self.tree_levels[-1]:
            return sha256(b"")
        return self.tree_levels[-1][0]

    def generate_proof(self, leaf_index: int) -> List[Dict[str, str]]:
        """Generates Merkle audit proof path for a leaf at index."""
        if leaf_index < 0 or leaf_index >= len(self.leaves):
            raise IndexError("Leaf index out of bounds")
        
        proof = []
        idx = leaf_index
        for level in self.tree_levels[:-1]:
            is_right = (idx % 2 == 1)
            sibling_idx = idx - 1 if is_right else idx + 1
            if sibling_idx < len(level):
                sibling_hash = level[sibling_idx]
            else:
                sibling_hash = level[idx]  # duplicate self for odd leaves
            
            proof.append({
                "position": "left" if is_right else "right",
                "hash": sibling_hash
            })
            idx //= 2
        return proof

    @staticmethod
    def verify_proof(leaf_hash: str, proof: List[Dict[str, str]], expected_root: str) -> bool:
        """Verifies inclusion of leaf_hash against expected_root using proof."""
        current = leaf_hash
        for step in proof:
            if step["position"] == "left":
                combined = f"{step['hash']}{current}"
            else:
                combined = f"{current}{step['hash']}"
            current = hashlib.sha256(combined.encode("utf-8")).hexdigest()
        return current == expected_root
```

---

### 3.2 App-Specific Implementation Layer (`Halbert`)

#### A. Secure Host Key Storage (`halbert_core/crypto/storage.py`)
Manages key persistence using OS Keyring when available, with automatic fallback to file permissions `0600` for headless daemons.

* **Primary Path:** `keyring.get_password("halbert_agent", identity_name)`
* **Headless/File Fallback:** `~/.local/share/halbert/identity/{identity_name}.key` (restricted to `chmod 0600`).

#### B. Signed Tool Audit Log (`halbert_core/obs/audit.py` Upgrade)
Upgrades the existing `write_audit` function to sign every entry with the active `AgentIdentity`.

```python
def write_audit(
    tool: str, 
    mode: str, 
    request_id: str, 
    ok: bool, 
    summary: str = "", 
    identity: Optional[AgentIdentity] = None, 
    **extra: Dict[str, Any]
) -> str:
    # 1. Gather timestamp and record fields
    # 2. Compute prev_hash from last line in <log_dir>/audit/YYYY/MM/DD/<tool>.jsonl
    # 3. Serialize record canonically and compute record SHA-256 hash
    # 4. Sign record_hash using identity.sign() if identity is present
    # 5. Append { ..., "prev_hash": ..., "hash": ..., "author_did": ..., "signature": ... }
```

#### C. Verification CLI (`halbert audit-verify`)
Adds a CLI verification command to scan and validate audit logs or memory DAGs:
```bash
python Halbert/main.py audit-verify --tool execute_command --date 2026-09-02
```
* Checks continuous unbroken `prev_hash -> hash` links.
* Validates every `signature` against the record's `author_did` public key.
* Reports any tampering, missing entries, or invalid signatures.

---

## 4. Phased Implementation Plan

```
┌─────────────────────────────────────────────────────────────────────────┐
│ PHASE 1: Universal Cryptographic Primitives (Haloysius repo)            │
│ 1. Add haloysius/crypto/identity.py (Ed25519 & did:key generation)      │
│ 2. Unit tests for signing, verification, and multicodec formatting      │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ PHASE 2: Signed Memory & Merkle DAG (Haloysius repo)                    │
│ 1. Add haloysius/memory_v2/merkle.py (MerkleMemoryDAG & proofs)         │
│ 2. Extend PersonaMemory with cryptographic integrity fields             │
│ 3. Unit tests for Merkle root computation and proof verification        │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ PHASE 3: Halbert Key Storage & Signed Audit Logging (Halbert repo)      │
│ 1. Implement halbert_core/crypto/storage.py (Keyring + 0600 file)       │
│ 2. Upgrade halbert_core/obs/audit.py with signature injection           │
│ 3. Update tests/test_audit_chain.py to verify signatures and hashes     │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ PHASE 4: Bridge Integration & Verification Tooling (Halbert repo)       │
│ 1. Update haloysius_memory_adapter.py to pass identity through          │
│ 2. Add 'audit-verify' CLI command in Halbert/main.py                    │
│ 3. Expose state root verification status in Tauri dashboard             │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 5. Reviewer Decision Checklist

Before execution, the reviewing engineer should confirm:

1. **Key Custody Strategy**: Confirm that headless background daemon instances are allowed to store private keys in `~/.local/share/halbert/identity/` with `0600` permissions when an OS Keychain daemon is not present.
2. **DID Method Standard**: Confirm `did:key` with Ed25519 (`0xed01` multicodec prefix) as the universal default for simplicity and zero-network self-certification.
3. **Memory Compaction / Pruning Policy**: When memory is pruned or summarized by `memory_purge.py` or A-MEM hierarchization, pruned sub-trees should be committed into a permanent Merkle epoch summary root rather than deleting leaf records without a trace.
