# HANDOFF: Integrity Phases 1–2 — peer signing (Haloysius) and key custody (Halbert)

**Status:** ACTIVE — §3 (Halbert) landed 2026-09-02; §2 (Haloysius Phase 1) not started
**ROADMAP row:** `TRUST-1`
**Date:** 2026-09-02
**From:** Haloysius — Phase 0 complete
**To:** Halbert (Phase 2), and any other app consuming `haloysius.integrity`
**Supersedes:** Phases 3–4 of [`Halbert/.handoff/HANDOFF-CRYPTOGRAPHIC-IDENTITY-AND-MERKLE-MEMORY-2026-09-02.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/HANDOFF-CRYPTOGRAPHIC-IDENTITY-AND-MERKLE-MEMORY-2026-09-02.md)
**Context / rationale:** [`Haloysius/.handoff/REVIEW-CRYPTOGRAPHIC-IDENTITY-AND-MERKLE-MEMORY-2026-09-02.md`](file:///Volumes/4TB-BAD/Haloysius/.handoff/REVIEW-CRYPTOGRAPHIC-IDENTITY-AND-MERKLE-MEMORY-2026-09-02.md)
**Halbert's work is §3** — the rest is context and the Haloysius side.

---

## 1. What landed (Phase 0, Haloysius)

`src/haloysius/integrity/` — 1,016 lines, 96 tests, no new hard dependencies.
Full suite green: **63,386 passed**. Verified on Python 3.11 and 3.12.

| Module | What it gives you |
| :--- | :--- |
| `canonical.py` | RFC 8785 (JCS) canonical bytes + NFC normalization; floats rejected; `to_millis` refuses naive datetimes |
| `identity.py` | `did:key` over a pluggable curve (Ed25519 / P-256), inlined base58btc, `verify(did, payload, sig)` from a DID string alone |
| `eventlog.py` | Append-only JSONL, chain **continuous across shards**, persisted head, atomic append, salted commitments, `erase()` |
| `seam.py` | New `SigningBackend` Protocol — consumers own key custody |

`pyproject.toml` gains `[crypto] = ["cryptography>=42.0"]`. Nothing else changed.

**Verified behaviours** (not claims — these are covered by tests and were run):

```
truncate the last record         -> detected: True  (truncated)
delete an entire shard file      -> detected: True  (truncated)
edit a memory's `believed` field -> detected: True  (commitment_mismatch)
```

The first two are exactly what `halbert_core`'s current per-file chain cannot
see (review finding P12). The third is caught because commitments cover the
whole payload, unlike the 6-of-22 fields the original spec signed (P3).

**Subtractive contract, verified in a clean 3.11 venv with no third-party
packages installed:** `import haloysius.integrity` loads zero third-party
modules; the event log appends and verifies; `did:key` encode/decode works;
`SoftwareSigner.generate()` raises a clear `IdentityError` naming the extra.

**DID interop:** Ed25519 DIDs render `did:key:z6Mk…`, P-256 DIDs render
`did:key:zDn…`, both matching the W3C `did:key` spec.

---

## 2. Phase 1 — sign at the boundary (Haloysius). NOT STARTED.

Deliberately not started, because it is a **two-sided wire-protocol change**.
`peer_backend.py` talks to a canonical host that Halbert implements; changing
the request shape unilaterally breaks the live peer link. It needs to land
with §3 or behind a negotiated capability flag.

### 1.1 Per-node identity on the peer link

`PeerMemoryBackend.__init__` currently takes `bearer_token` and nothing else.
Every body holds the **same** token, so a write cannot be attributed to a body
and one body cannot be revoked without re-keying all of them. This is the
highest-value item in the whole programme and needs no Merkle work.

Add an optional `signer: SigningBackend`. When present:

- Each request carries `X-Haloysius-DID` and `X-Haloysius-Signature`, the
  latter over `canonicalize({"method", "path", "body_commitment", "ts_ms",
  "nonce"})`.
- **Include `ts_ms` and a nonce, and have the host reject stale or replayed
  ones.** A signature without them is replayable — the review did not raise
  this because the original spec had no wire protocol at all, but it applies
  the moment signing goes on a network.
- The bearer token stays for one release as the transition path, then goes.

### 1.2 Signed export bundles (`.halmem`)

The clearest case for signatures: a bundle leaves the trust domain and the
recipient has no other basis to trust origin or integrity. Bundle = the event
log's shards + head + a manifest signed by the exporting body's DID.

Note for whoever builds this: an exported bundle's **salts travel with it**,
so exporting re-exposes content that was erasable at rest. Decide explicitly
whether export strips erased events (it should) and whether bundles are
encrypted at rest.

---

## 3. Phase 2 — key custody and audit (Halbert). YOURS.

Paths below are corrected — everything is one level deeper than the original
handoff said, under `halbert_core/halbert_core/`.

### 3.1 `halbert_core/halbert_core/crypto/storage.py` — implement `SigningBackend`

```python
from haloysius.seam import SigningBackend          # Protocol
from haloysius.integrity import SoftwareSigner, ED25519, P256
```

Wrap `SoftwareSigner` with real custody. Order of preference:

1. **Hardware** (Secure Enclave on macOS, TPM on Linux) — **P-256 only.**
   Neither supports Ed25519. This is why the curve is pluggable; use
   `P256` here and `ED25519` for software custody.
2. **OS keystore** — macOS Keychain, Linux Secret Service.
3. **`0600` file** for headless daemons — approved, with these conditions:
   parent directory `0700`; **refuse to load a key whose permissions are
   looser than `0600`** (OpenSSH behaviour); never fall back silently from
   keystore to file — log the downgrade at WARNING.

`SoftwareSigner.private_bytes()` / `.from_private_bytes(b, curve)` are the
custody round-trip. Never log the result.

### 3.2 Replace the shared peer bearer token

Consume §2.1 once it lands. This is the actual security win — per-body
attribution and per-body revocation.

### 3.3 `obs/audit.py` — fix continuity BEFORE adding signatures

The current chain restarts at `prev_hash = None` in every new
`YYYY/MM/DD/<tool>.jsonl`. **Signing a truncatable log misrepresents its
integrity**, so do these in order:

1. Carry the chain head across day and tool boundaries; persist a head
   pointer. (`EventLog._check_head` is the reference for why this is what
   makes truncation visible.)
2. *Then* sign records with the active `SigningBackend`.

Simplest path: back `write_audit` with `haloysius.integrity.EventLog` and
delete the hand-rolled chain. It already does continuity, atomic append,
salted commitments and verification.

### 3.4 `halbert audit-verify` CLI

Must detect **truncation and whole-file deletion**, not only in-file edits —
the original spec's "checks continuous unbroken links" would pass a truncated
log. `EventLog.verify()` returns `VerifyResult(ok, checked, signed, problems)`;
render `problems` directly, they are written to be read by a human.

### 3.5 UI copy is a correctness requirement

No "memory verified" badge. On a single machine the key and the log share a
disk, and the badge would assert something the system cannot back. Accurate
copy: *"no tampering detected since last sync with `<peer>`"*.

---

## 4. Phase 3 — Merkle. Unblocked but NOT next.

Decision D2 resolved to **peer bodies co-sign roots on sync**, so Phase 3 now
has an anchor and is in scope. It still comes last: co-signing needs per-node
identity (Phase 1) and custody (Phase 2) to exist first.

When it is built, it must be RFC 6962-correct. The original spec's reference
implementation is not, and this was reproduced by running it:

- **Root collision** — duplicate-last-leaf makes `[A,B,C]` and `[A,B,C,C]`
  yield the same root (CVE-2012-2459 class). Fix: promote odd nodes unchanged.
- **Second preimage** — no `0x00`/`0x01` leaf/node domain separation, so an
  internal node verifies as an included leaf. `eventlog.py` already reserves
  `0x00` for commitments and `0x02` for records; `0x01` is held for nodes.
- **O(n²) appends** — 8k leaves took 19.9 s. Fix: incremental mountain-range,
  O(log n) per append.

Leaves must commit through `Event.commitment`, which is already salted — do
not hash payloads directly, or erasure breaks (decision D3).

---

## 5. For other apps (H2, H3)

Nothing here is app-specific. Consume `haloysius.integrity` through the
`SigningBackend` seam and supply your own custody. **If you have no custody
story, register nothing** — the log runs unsigned, verifies, and reports
`signed: 0`. The subtractive contract holds: a thin consumer registers
nothing and still runs.

---

## 6. Two things not to repeat from the original spec

1. **Do not sign `PersonaMemory` rows.** They mutate constantly — `strength`
   decays, `access_count` increments, `embedding` and `epistemic` are attached
   later. Sign the immutable *event*; treat the memory object as a projection.
2. **Do not sign a subset of fields.** The original `canonical_bytes` left 16
   of 22 fields unsigned, including `believed` and `invented` — the truth-state
   fields — while signing `metadata`, which downstream code mutates. Commit to
   the whole payload, as `Event.commitment` does.

---

## 7. What landed for §3 (Halbert, 2026-09-02)

59 new tests, all green. Full Python suite: **4,937 passed / 5 failed**, and all
five failures reproduce on a clean tree (licence gate ×2 — pre-existing
unregistered deps; `test_llm_config_parse_cache` ×2; `test_multi_instance` ×1,
order-dependent).

| Item | State | Where |
| :--- | :--- | :--- |
| §3.1 key custody | **Done**, hardware tier is a seam | `halbert_core/halbert_core/crypto/storage.py` |
| §3.2 per-body peer identity | **Blocked** on §2.1 — two-sided wire change, Haloysius side not started | — |
| §3.3 chain continuity, then signing | **Done** | `halbert_core/halbert_core/obs/audit.py` |
| §3.4 `halbert audit-verify` | **Done** | `Halbert/main.py` |
| §3.5 UI copy | **Done** for the CLI; no badge existed to remove | `render_verify_report` |

### 7.1 Custody ladder

`resolve_signer()` walks hardware → Keychain → Secret Service → `0600` file,
takes the first available tier that already holds a key, and generates into the
most-preferred available tier when none does. Enforced as specified: key file
created `0600` from the outset (not written-then-chmod-ed, which leaves a
world-readable window), parent `0700`, and a key whose mode is looser than
`0600` is **refused** with the offending mode and a `chmod` line, OpenSSH-style.
A downgrade caused by a *failing* higher tier logs at WARNING naming both tiers;
a tier that is merely absent from this machine does not, because that is a fact
about the machine rather than a weakening of custody.

Keychain and Secret Service are driven as subprocesses (`security`,
`secret-tool`) so neither adds a dependency. The keychain tier is tested
against a real throwaway keychain created in `tmp_path`, not a mock and not
`login.keychain`.

**Hardware is a seam, not an implementation** (agreed with the founder
before starting). `register_hardware_provider()` installs a P-256 provider at
the top of the ladder; unregistered, `HardwareKeyStore` reports itself
unavailable and the ladder falls through. Secure Enclave key creation
generally needs a signed binary with entitlements and could not be verified
from this environment, so shipping untested `Security.framework` bridging
would have been a claim, not a feature.

### 7.2 Continuity, and a defect found on the way

`write_audit` is now backed by `EventLog`; the hand-rolled per-file chain is
gone. Verified against the three §1 behaviours plus a removed middle record.

**`EventLog.append` is not safe under concurrency, and this bites hard.**
It reads the head, writes a record, then writes the head back, with nothing
holding the three together. Halbert runs tool calls concurrently — async
request handlers, the scheduler, guardrails, recovery — and 24 concurrent
`write_audit` calls produced **46 integrity problems on a log nobody touched**:
duplicate `seq`, repeated `prev_hash`, `audit-verify` reporting TAMPERING.
An audit check that cries wolf is one people learn to ignore, so this is as
damaging as a missed detection.

Halbert now takes an `flock` on `<audit>/.append.lock` around the append —
a *file* lock, because the daemon, tool subprocesses and the CLI are separate
processes. Same probe after the fix: 24/24 records, 0 problems.

**This belongs in Haloysius**, not in every consumer: `EventLog.append` should
serialize its own read-modify-write. Until it does, every consumer of
`haloysius.integrity` that writes concurrently has this bug. Flagging for
Phase 1.

### 7.3 Signing is opt-in

Off unless `set_audit_signer()` is called or `HALBERT_AUDIT_SIGNING=1` is set.
Two reasons: §3.3 orders continuity before signatures, and resolving a signer
*creates a private key on this machine* — on macOS, in the user's login
keychain — which is not something a tool call should do unannounced. Unsigned,
the log appends, verifies, and reports `signed: 0`, per §5.

### 7.4 The core still imports without haloysius

`obs/audit.py` is imported by `tools/base.py`, `autonomy/guardrails.py`,
`persona/`, and `findings/` — so an unguarded `haloysius` import there would
have broken the documented invariant that halbert_core's core runs without it
(the other 18 haloysius imports in the tree are all guarded). The import is
guarded, and **absent haloysius the log writes nothing, loudly**: it does not
fall back to a chain nobody can verify, since a log that only looks
tamper-evident is the failure this change exists to remove. `verify_audit`
raises `AuditUnavailable`, and the CLI exits **2** — "I could not check" must
not share an exit code with "I checked and found tampering".

A `[integrity]` extra was added to `halbert_core/pyproject.toml`, and
`cryptography` was registered in `config/dependency-licenses.yml`
(Apache-2.0, taken from its Apache-2.0-OR-BSD-3-Clause dual licence).

### 7.5 Copy (§3.5)

No badge existed to remove. The CLI never says "verified"; it says
*"No tampering detected since this log began"*, or *"...since last sync with
`<peer>`"* when `--peer` names one, and states what it cannot back:

> Both the log and the key that would sign it live on the same machine, so
> this cannot prove the log was never rewritten — only that nothing has been
> altered underneath the running system.

`--json` emits `{ok, checked, signed, unsigned, problems[]}` for the dashboard
when an integrity surface is built. Whoever builds it inherits the same
constraint: **no "memory verified" badge.**

### 7.6 Adversarial pass (same day, after the above)

The first pass was re-attacked rather than re-read. Six defects were found by
probe, not by inspection — every one reproduced before the fix and was
re-probed after. Two are the same class as the concurrency bug in §7.2, which
is the lesson: **the read-modify-write hazard was not one bug, it was a
pattern**, and the first fix only covered half of it.

| # | Defect | Evidence before fix |
| :-- | :--- | :--- |
| D1 | `write_audit` could raise, despite "never raises" — the payload was built *outside* the try. `tools/base.py` calls it on failure paths, so a half-constructed object in a kwarg turned a handled tool error into a crash. | `RuntimeError` propagated from a value's `__str__` |
| D2 | An `extra` kwarg silently overwrote an audited field. `write_audit(..., ts=...)` rewrote the record's own timestamp; `tool`, `ok`, `mode`, `request_id`, `summary` likewise. Whatever produced that value — a tool result, a model-supplied string — got to decide what the log claimed happened. | `payload["ts"] == "1999-01-01"` |
| D3 | `verify_audit(directory=…)` **created** a missing directory and reported it clean. `halbert audit-verify --dir /typo` exited 0 saying "no tampering detected". | directory created, exit 0 |
| D4 | A corrupt or truncated key file made the body **silently mint a new identity and overwrite the old key** — irreversible, at INFO level. Every attribution under the old DID undone by a filesystem hiccup. | DID changed, old key gone, nothing logged above INFO |
| D5 | Verifying *while writing* reported tampering. `append` writes the record then the head, so a verify landing between the two sees a log one record ahead of its head and calls it truncated. | **288 false "TAMPERING DETECTED" in 3 s** |
| D6 | Concurrent first starts each generated a key; last write won. Five racing processes minted **five identities and destroyed four keys**, leaving four processes signing with keys no longer in custody. A body whose DID depends on a startup race cannot be attributed to — which is the only reason it has one. | 5 distinct DIDs, 1 survivor |

Fixes: payload construction moved inside the try and `_canonical_safe` made
total (one unrenderable field costs that field, not the record); audited fields
are reserved and collisions preserved under `shadowed`; `verify_audit` raises
`AuditUnavailable` for a missing directory and never creates one; a store
holding material that could not be read is **never written to** — the body runs
unsigned and says why, because destroying an identity is not error recovery;
`verify_audit` takes the append lock; and a second file lock
(`<keys>/.custody.lock`) makes "find or create the key" one operation.

Cost of the verify lock, measured: 0.23 s on a 5,000-record log (append
throughput 1,817 records/s with fsync). Acceptable.

**Two of these belong upstream.** `EventLog.append`'s unlocked
read-modify-write is Haloysius's, and so is the reader side of it: every
consumer of `haloysius.integrity` that writes concurrently, or verifies a live
log, has D5 and D6 today. Halbert defends its own log; the library should
defend everyone's.

### 7.7 Left for later

- **§3.2** — needs Haloysius §2.1 first. When it lands, the signer is already
  here: `resolve_signer()` returns a `SigningBackend`, so the peer link takes
  it directly.
- **`EventLog.append` locking** — should move into Haloysius (§7.2).
- **Hardware custody** — the seam is in place; a Secure Enclave provider needs
  a signed binary to develop against.
- **Legacy `audit/YYYY/MM/DD/*.jsonl` records** — left untouched on disk and
  not read. No migration was built: no users, so no legacy support is owed
  (founder call). `EventLog` globs `audit/*.jsonl`, so the old nested tree is
  invisible to it.
