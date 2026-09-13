# Shared Redundant Databases & State Replication in Home Networks

**Location**: `.handoff/research/multi-node-systems/02-SHARED-REDUNDANT-DATABASES-AND-STATE.md`  
**Date**: 2026-09-12  
**Focus**: Distributed state synchronization, SQLite replication technologies, split-brain avoidance in small clusters, and local-first CRDT architectures for Halbert.

---

## 1. The SQLite Dilemma in Distributed Agent Systems

Halbert's architecture is deeply committed to **SQLite** (`timeline.db`, `state_ledger.db`, `conversation.db`, `findings.db`, `memory_v2`). SQLite provides immense benefits:
- Zero operational overhead (no database daemons, background server processes, or connection pool configuration).
- In-process execution with microsecond query latency.
- Strict ACID compliance with Write-Ahead Logging (WAL).
- Single-file portability and straightforward file-level backups.

However, **SQLite is fundamentally an embedded, single-node database**. It relies on OS-level file locks (`fcntl` / `flock`), which do not work reliably over network filesystems (NFS, SMB) without risking catastrophic database corruption.

### Halbert's Current Reality: The Fragile RPC Proxy

Today, Halbert handles multi-node state via `PeerConversationStore` and `PeerMemoryBackend` (`agents/peer_conversation_store.py`):

```
CURRENT ARCHITECTURE (STATISTICALLY FRAGILE):

Satellite (Raspberry Pi 5)                             Canonical Host (Mac Studio)
┌──────────────────────────────────────┐               ┌──────────────────────────────────────┐
│ ThreadManager                        │               │ ThreadManager                        │
│  └─► PeerConversationStore           │  HTTP RPC     │  └─► SqliteConversationStore         │
│       - get_thread()                 ├──────────────►│       - SELECT / INSERT in SQLite    │
│       - append_message()             ├──────────────►│       - BEGIN IMMEDIATE transaction  │
│                                      │               │                                      │
│  NO LOCAL COPY                       │               │ AUTHORITATIVE DATABASE               │
│  NO OFFLINE CACHE                    │               │ (conversation.db, memories.db)       │
└──────────────────────────────────────┘               └──────────────────────────────────────┘
```

**Why This Breaks in Real Home Environments**:
1. **Network Jitter & Wi-Fi Roaming**: A 2-second Wi-Fi drop causes `PeerConversationStore` to raise `PeerConversationUnavailable`, crashing ongoing user turns.
2. **Host Sleep**: When the Mac Studio enters system sleep, the satellite completely loses conversation history and memory.
3. **Zero Offline Capability**: The satellite cannot answer even the simplest query from local memory when disconnected.
4. **Single Point of Failure (SPOF)**: If the canonical host's SSD dies, all conversation history and entity autobiography are lost forever.

---

## 2. The 2-Node Quorum & Split-Brain Paradox

When engineers attempt to make databases "distributed," their instinct is to reach for **Consensus Protocols** like **Raft** or **Paxos** (e.g., `rqlite`, `dqlite`, `etcd`, `Consul`).

In a typical home network, this creates a catastrophic architectural trap: **The 2-Node Quorum Impasse**.

### 2.1 The Mathematics of Quorum
Raft guarantees safety (no split-brain) by requiring a strict majority quorum $Q$ for any leader election or write commit:
$$Q = \left\lfloor \frac{N}{2} \right\rfloor + 1$$

| Total Nodes ($N$) | Quorum Needed ($Q$) | Max Fault Tolerated ($f$) | What Happens if 1 Node Goes Offline? |
|:---:|:---:|:---:|---|
| **1** | 1 | 0 | Works normally (single point of failure). |
| **2** | **2** | **0** | **CLUSTER DEADLOCK**: If either node sleeps or drops, quorum is lost ($1 < 2$). **Writes are 100% blocked!** |
| **3** | 2 | 1 | Survives 1 node failure ($2 \ge 2$). |
| **5** | 3 | 2 | Survives 2 node failures ($3 \ge 3$). |

### 2.2 The Home Reality: Asymmetric 2-Node Clusters
A standard Halbert deployment consists of:
- **Node A**: An always-on low-power coordinator (e.g., Home Assistant Yellow, Raspberry Pi 5, or Intel N100).
- **Node B**: A high-power workstation (e.g., Apple Silicon Mac Studio or PC). **Enters sleep mode frequently.**
- *(Optional) Node C*: A laptop (roams between home Wi-Fi and coffee shops).

> [!WARNING]
> **Why Consensus Daemons Fail in Home Environments**:
> If you deploy a Raft-based database (like `rqlite` or `dqlite`) across Node A and Node B, **putting your workstation to sleep immediately freezes the always-on smart home node**. Because $N=2$, Node A cannot achieve quorum alone ($1 < 2$). It cannot record timeline events, write state changes, or log sensor discoveries until the workstation is awakened!

### 2.3 Solutions to the 2-Node Dilemma

1. **The Witness / Arbiter Pattern**:
   - A tiny, stateless daemon runs on a lightweight third device (e.g., the home router, a NAS, or a cloud VPS).
   - The witness holds no database data; it only casts a tie-breaker vote during elections to establish quorum ($N=3$, $Q=2$).
2. **Lease-Based Active-Passive with Heartbeat**:
   - Instead of dynamic Raft elections, one node is designated the **Primary** and acquires a renewable lease.
   - If the primary fails, the secondary does not automatically promote itself unless an explicit out-of-band condition is met (or the user approves promotion via UI), preventing split-brain writes.
3. **Local-First Conflict-Free Replicated Data Types (CRDTs)**:
   - **Completely eliminates the quorum requirement.**
   - Every node is a full master that can read and write locally at full speed, completely offline.
   - Replicas converge deterministically upon reconnection.

---

## 3. Comprehensive Survey of SQLite Replication Technologies

We evaluated the leading open-source SQLite replication engines across five critical criteria for Halbert:

```
                  SQLITE REPLICATION LANDSCAPE (2024–2026)
                                     
            Consensus / Raft               Physical WAL Streaming          Logical / CRDT
         ┌────────────────────┐          ┌───────────────────────┐      ┌───────────────────┐
         │ rqlite / dqlite    │          │ Litestream / LiteFS   │      │ cr-sqlite /       │
         │ - Strong Consist.  │          │ - Log shipping / LTX  │      │ ElectricSQL       │
         │ - Requires Quorum  │          │ - Single writer       │      │ - Active-Active   │
         │ - Heavy Daemons    │          │ - Microsecond replica │      │ - Partition-safe  │
         └────────────────────┘          └───────────────────────┘      └───────────────────┘
```

### 3.1 Detailed Technology Comparison

| Technology | Architecture | Consistency Model | Multi-Writer? | Kernel / Daemon Requirements | Suitability for Halbert |
|---|---|---|:---:|---|---|
| **Litestream** (Ben Johnson) | Continuous WAL frame streaming to S3/SFTP/LAN. | Asynchronous snapshot replication (RPO < 1s). | No (Single writer only). | Single background Go binary; zero SQLite patches. | **Excellent for continuous backup and disaster recovery.** |
| **LiteFS** (Fly.io / Superfly) | FUSE filesystem intercepting SQLite writes into LTX files. | Primary-replica with transactional LTX streams. | No (Primary writes, replicas read). | Requires FUSE (`macFUSE` on macOS, FUSE in Linux kernel); Consul/Lease required. | **Challenging on macOS** (macFUSE requires kernel extensions/SIP reduction). |
| **rqlite** (Philip O'Toole) | Standalone Go daemon wrapping SQLite via HashiCorp Raft. | Strict Serializable (Raft consensus). | Leader writes; followers proxy. | External Go daemon per node; port 4001/4002. | **Poor fit**: Quorum failure on 2 nodes; breaks subtractive contract. |
| **dqlite** (Canonical / LXD) | In-process C library implementing C-Raft over SQLite. | Sequential consistency (Raft). | Leader writes. | Complex C library; Raft quorum constraint. | **Poor fit**: C library maintenance; 2-node deadlock. |
| **cr-sqlite** (Matt Wonlaw / VLCN) | Run-time loadable SQLite extension (`.so` / `.dylib`). | Eventual Consistency via Conflict-Free Replicated Relations (CRRs). | **YES (Multi-writer active-active).** | **Zero daemons.** Loadable extension via `db.load_extension()`. | **Ideal for active-active multi-node sync.** |
| **ElectricSQL** | Sync service pairing SQLite with Postgres logical replication. | Causal Consistency via Shapes & Datalog. | **YES.** | Requires external Elixir sync service + Postgres. | **Too heavy**: Requires Postgres backend. |

---

## 4. Deep Dive: CRDT-Based SQLite Replication (`cr-sqlite`)

For active multi-node computing where any node must be able to record observations or chat turns while offline, **`cr-sqlite`** represents the state of the art in local-first database engineering.

### 4.1 How `cr-sqlite` Works
1. **Loadable Extension**: It loads directly into standard SQLite without patching the engine:
   ```sql
   SELECT load_extension('crsqlite');
   ```
2. **Replicated Relations (`crsql_as_crr`)**:
   Existing SQLite tables are upgraded to CRDT-tracked relations:
   ```sql
   CREATE TABLE messages (id TEXT PRIMARY KEY, turn_id TEXT, content TEXT, timestamp REAL);
   SELECT crsql_as_crr('messages');
   ```
   `cr-sqlite` automatically injects triggers that record column-level changes into a companion table with Hybrid Logical Clocks (HLC), site IDs, and version counters.
3. **The `crsql_changes` Virtual Table**:
   Nodes sync by simply reading and writing rows to a virtual changeset table:
   ```sql
   -- On Node A: Get all changes since version 42
   SELECT "table", "pk", "cid", "val", "col_version", "db_version", "site_id"
   FROM crsql_changes
   WHERE db_version > 42 AND site_id != ?;

   -- On Node B: Apply changes received from Node A
   INSERT INTO crsql_changes ("table", "pk", "cid", "val", "col_version", "db_version", "site_id")
   VALUES (?, ?, ?, ?, ?, ?, ?);
   ```
4. **Mathematical Convergence**:
   Because the underlying data structure is a state-based CRDT, changes can arrive out of order, be applied multiple times (idempotence), and merge concurrently without data loss or locking.

---

## 5. Semantic State Classification for Halbert

Not all data in Halbert behaves the same way. Trying to force a single distributed replication model onto all tables is a major architectural mistake.

We must partition Halbert's state into **Four Semantic Tiers**:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       HALBERT STATE REPLICATION TIERS                       │
│                                                                             │
│  Tier 1: Append-Only Event Logs        Tier 2: Hierarchical Conversation DAG│
│  (timeline.db, state_ledger.db)         (conversation.db)                   │
│  ┌───────────────────────────────┐     ┌──────────────────────────────────┐ │
│  │ Pure G-Set (Grow-only Set)    │     │ Git-like DAG Branch Merging      │ │
│  │ UUID + HLC Timestamp          │     │ Concurrent turns form branches   │ │
│  │ Mathematical Set Union (∪)    │     │ Deterministic leaf resolution    │ │
│  │ ZERO merge conflicts          │     │ Preserves all messages           │ │
│  └───────────────────────────────┘     └──────────────────────────────────┘ │
│                                                                             │
│  Tier 3: Persona & Knowledge Memory    Tier 4: Host-Bound Physical State    │
│  (memories.db, memory_v2)              (findings.db, being.yml, body.key)   │
│  ┌───────────────────────────────┐     ┌──────────────────────────────────┐ │
│  │ MELD Contradiction-Preserving │     │ Node-Local ONLY                  │ │
│  │ Retain conflicting facts with │     │ Never replicated across nodes    │ │
│  │ provenance; flag for review   │     │ Backed up per-host               │ │
│  └───────────────────────────────┘     └──────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 5.1 Tier 1: Append-Only Event Logs (`timeline.db`, `state_ledger.db`)
- **Nature**: Immutable sequence of events (`ha_state_change`, `scanner_finding`, `file_edit_digest`).
- **CRDT Model**: **Grow-Only Set (G-Set)**.
- **Replication Strategy**:
  - Each event has a unique UUID (`event_id`) and a monotonic Hybrid Logical Clock (`hlc_timestamp`).
  - To sync between Node A and Node B:
    $$\text{State}_A \cup \text{State}_B$$
  - Node A sends: `SELECT event_id, ... FROM timeline WHERE hlc > ?`
  - Node B executes: `INSERT OR IGNORE INTO timeline VALUES (...)`
  - **Result**: Perfect, conflict-free synchronization with zero coordination.

### 5.2 Tier 2: Conversation Trees (`conversation.db`)
- **Nature**: Halbert conversations are not linear logs; they are branching trees of turns (`parent_turn_id`, `branch_id`, `move_leaf`).
- **Replication Strategy (DAG Merging)**:
  - Modeled identically to Git commit DAGs.
  - If a user interacts with the satellite while disconnected and also with the workstation, two leaves are created with the same parent turn.
  - When the nodes reconnect, the conversation store incorporates both turns into the tree.
  - The UI's `ThreadManager` displays the active branch and allows switching leaves, exactly as the desktop shell already does (`DECISIONS.md` line 13: "one seamless conversation with hidden topic threads").
  - **No turn is ever lost or overwritten.**

### 5.3 Tier 3: Persona Memory & Knowledge (`memory_v2`)
- **Nature**: Semantic claims about the user and the world (`PersonaMemory`).
- **Replication Strategy (MELD Contradiction Preservation)**:
  - Standard databases use Last-Write-Wins (LWW), which silently deletes older facts.
  - Under the **MELD principle** (ratified in `DECISIONS.md` and `.handoff/DISTRIBUTED-MEMORY-ARCHITECTURE-2026-09-09.md` §13.4):
    - When two conflicting memories exist (e.g. Node A records "User drinks tea" while Node B records "User drinks coffee"):
    - **Both memories are preserved** with their respective provenance, timestamp, and confidence scores.
    - The background consolidation pipeline (`reflection.py`) or a human interaction resolves the tension gracefully.

### 5.4 Tier 4: Node-Local State (`findings.db`, hardware profiles, `being.yml`)
- **Nature**: Bound to physical sensors, local disks, and operating system packages.
- **Replication Strategy**: **NEVER REPLICATED**.
  - A finding that `/etc/fstab` has a syntax error on the workstation is irrelevant to the Raspberry Pi.
  - Physical node state is inspected on demand via MCP proxies (`fleet_proxy.py`), not synced into the central database.

---

## 6. Recommended Replication Architecture for Halbert

To respect the Haloysius subtractive contract while eliminating single points of failure:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    HALBERT HYBRID REPLICATION BLUEPRINT                     │
│                                                                             │
│  Satellite Node (Pi 5)                               Canonical Host         │
│  ┌───────────────────────────┐                       ┌────────────────────┐ │
│  │ Local Read-Through Cache  │                       │ Authoritative DBs  │ │
│  │ (SQLite replica)          │                       │ (conversation.db,  │ │
│  │                           │                       │  timeline.db)      │ │
│  │  1. Local reads: 0ms      │                       │                    │ │
│  │     (hits local cache)    │                       │                    │ │
│  │                           │   mTLS Sync Channel   │                    │ │
│  │  2. Writes:               │ ◄───────────────────► │                    │ │
│  │     - If online:          │   Delta-Push / Pull   │                    │ │
│  │       forward + ack       │   (Event G-Set sync)  │                    │ │
│  │     - If offline:         │                       │                    │ │
│  │       stage in local WAL  │                       │                    │ │
│  │       sync on reconnect   │                       │                    │ │
│  │                           │                       │                    │ │
│  │  3. Warm Standby Replica: │ ◄───────────────────  │ Daily / Hourly     │ │
│  │     Ready for promotion   │   Encrypted Snapshot  │ Snapshot streaming │ │
│  │     if Host dies          │   (Active-Passive)    │ (Litestream style) │ │
│  └───────────────────────────┘                       └────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Architectural Guarantees:
1. **Zero Downtime Reads**: Satellites read conversation history and memory locally. A rebooting workstation does not impact the smart home speaker.
2. **Offline-Resilient Writes**: Messages typed or spoken on a satellite while offline are staged in a local pending queue (`local_staging.db`) and flushed automatically via G-Set / DAG merge when the link recovers.
3. **Disaster Recovery**: Satellites maintain an encrypted, warm-standby copy of canonical databases. If the host fails permanently, the user can promote the satellite to canonical with a single click.
4. **Zero Heavy Daemons**: Implemented purely in Python using existing SQLite connections and mTLS HTTP endpoints.
