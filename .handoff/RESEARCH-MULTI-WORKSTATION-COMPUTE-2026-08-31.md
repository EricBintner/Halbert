# Research Request: Multi-Workstation Compute Sharing

**To:** Research / architecture AI
**From:** Architecture / product planning
**Date:** 2026-08-31
**Status:** Research needed — not blocking singular-entity implementation
**Parent:** `HANDOFF-SINGULAR-ENTITY-MULTI-BODY-2026-08-31.md`

---

## The question

A user has **two workstations** (e.g., a Mac Studio + a Linux box) plus an HA server (N150). Can the HA server offload compute to either workstation? Can workstations offload to each other? What would it take to build this?

This is **not blocking** the singular-entity implementation (`IMPL-PLAN-SINGULAR-ENTITY-2026-08-31.md`), which assumes the common case of 1 HA + 1 workstation. Multi-workstation is a follow-on scope.

---

## What we need researched

### 1. Multi-peer ComputeRouter

The current `ComputeRouter` (`federation/compute_router.py`) has a single `peer_endpoint`. To support multiple workstations, it needs:

- A **list of peer endpoints** with individual health probes
- A **selection strategy** when multiple peers are online:
  - Round-robin? Least-latency? First-available? User-configurable priority?
  - Does it depend on the model requested? (Mac's Ollama might have different models than Linux's LMStudio)
- **Failover** between peers: if peer A fails, try peer B before falling through to "no AI"
- **Concurrent health probing**: probing 2+ peers in parallel, not sequentially

**Research question:** What selection strategy makes sense for the home use case? Is user-configurable priority sufficient, or do we need automatic latency-based selection?

### 2. Workstation-to-workstation offloading

Can one workstation offload to another (Mac → Linux, Linux → Mac)?

- The peer link is symmetric in principle (both have compute endpoints)
- But the current scaffold assumes a directional relationship (compute host vs. satellite)
- In singular entity mode, both workstations share the same `persona_id` and memory (on the HA server) — so offloading between them doesn't create an identity problem
- In independent entity mode, workstation-to-workstation offloading is just compute sharing between two separate AIs

**Research question:** Is workstation-to-workstation offloading a real use case, or is it over-engineering? The common case is HA → workstation. When would a user need Mac → Linux offload?

### 3. Discovery with 3+ nodes

The current mDNS scaffold (`federation/peer_discovery.py`) assumes 1:1 pairing. With 3+ nodes:

- mDNS beacon/listener needs to handle multiple discovered peers
- `peers.json` needs to store multiple peer entries (it already supports a list, but the UI and pairing flow assume 1:1)
- How does a new workstation discover both the HA server AND the other workstation?
- Does each workstation need to know about the other, or only about the HA server?

**Research question:** Is a star topology (HA server at center, workstations as leaves) sufficient, or do we need mesh discovery?

### 4. ComputeBroker multi-peer awareness

The `ComputeBroker` (`federation/compute_broker.py`) on each workstation accepts offload requests. With multiple satellites:

- Does it need to track which peer is sending requests? (for fairness, rate limiting per peer)
- Does it need to prioritize HA server requests over other-workstation requests?
- The priority queue already exists (P1-P3) — does it need a new priority tier for inter-workstation requests?

**Research question:** Is per-peer rate limiting needed, or is a single shared queue sufficient for the home use case?

### 5. Singular entity with 2 workstations

In singular mode with 2 workstations + 1 HA server:

- Memory: still one canonical store on the HA server. Both workstations proxy via `PeerMemoryBackend`. No change from the 1-workstation case.
- Threads: still one canonical `ThreadManager` on the HA server. Both workstations proxy. No change.
- Cognition: each workstation runs its own `PersonaCognition` with the same `persona_id` + shared memory. Three bodies, one entity.
- Body names: `desk-mac`, `desk-linux`, `home` (or whatever the user names them). The entity knows which body it's in.
- Perception: all three write to shared memory. The entity's autobiography includes sysadmin observations from both workstations + home observations.

**Research question:** Does the prompt builder need to know about ALL bodies, or just the current one? "You are currently at your desk-mac body. You also have a desk-linux body and a home body." — is this useful context or noise?

### 6. Wake-on-LAN with multiple workstations

If the HA server needs compute and both workstations are asleep:

- Does it WoL both? One at a time (priority order)?
- If it WoLs the Mac first and the Mac doesn't wake (WoL not enabled), does it try the Linux box?
- Does the user configure WoL per device independently?

**Research question:** What's the right WoL strategy when multiple targets are available?

---

## What does NOT change (already settled)

- **Singular entity mode:** one `persona_id`, one memory store (HA server), one thread registry (HA server). Multi-workstation doesn't change this — both workstations are bodies of the same entity.
- **Independent entity mode:** each device has its own `persona_id`. Compute sharing is separate from identity.
- **The peer link itself:** bearer auth, redaction boundary, health probes — all reusable as-is for multi-peer.
- **Memory/thread federation:** `PeerMemoryBackend` and `PeerThreadBackend` work the same regardless of how many workstations exist — they all point to the HA server.

---

## Deliverable

A research document answering the questions above, with:
- Recommended topology (star vs. mesh)
- Recommended selection strategy for multi-peer ComputeRouter
- Whether workstation-to-workstation offloading is worth building
- Estimated scope for multi-workstation support (files to change, new modules, test surface)
- Whether this should be a Phase 7+ follow-on or can be folded into the existing implementation plan

**Output location:** `.handoff/RESEARCH-MULTI-WORKSTATION-RESULTS.md` (to be created by the research AI)
