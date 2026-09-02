# Review Request — Rust Native Core Plan & Docker Integration Path

**Date:** 2026-08-31
**Status:** APPLIED 2026-09-01 (founder directive) — external confirmation now optional

> **Status update 2026-09-01 — APPLIED.** Per the 2026-08-31 founder directive, all 13 findings (F1-F13) and 5 recommendations (RA-RE) are accepted and every item in the §7 eleven-item edit list has landed in the plan (`RUST-NATIVE-CORE-TODO-AND-IMPLEMENTATION-PLAN-2026-08-31.md`), the scoping doc, and `MASTER-TODO.md`. The external confirmation review requested below is now **optional** — a welcome second opinion, not a gate. The two HIGH findings fixed: **F1** (R1 not verifiable before R4 → R4 restructured as per-crate FFI waves R4a/R4b/R4c) and **F2** (no Docker image build task → R0.9/R0.10 Docker track added to R0). The questions in §6 remain open for the reviewer to confirm.
**Documents under review:**
- `RUST-NATIVE-CORE-TODO-AND-IMPLEMENTATION-PLAN-2026-08-31.md` (the R0–R7 plan)
- `HA-STRATEGY-SCOPING-AND-DEPLOYMENT-PATHS-2026-08-31.md` (decisions D1–D8, deployment paths 1–4, compose template)
- `MASTER-TODO.md` (Rust phase summary cross-reference)

**What this request is:** A sanity review of the roadmap's early phases before
execution begins. The goal is a Linux distro **eventually**, but the immediate
plan is: rebuild a few stable interfaces in Rust (R0–R1 first), then build more
parts, and integrate a Docker deployment method into the stack. This document
records what was verified against the actual code, the defects found in the
plan, and the recommendations. Reviewer: please confirm or reject each finding
(F1–F13) and each recommendation (RA–RE), then answer the questions in §6.

---

## 1. Sanity Verdict (summary)

**The plan is sane.** Specifically:

- The boundary rule ("stable kernel ABI / frozen protocol → Rust; evolving app
  logic → Python") is sound and correctly applied. The 24 discovery scanners
  are I/O-bound text parsing and correctly stay in Python.
- Scope discipline is correct: custom kernel, Wayland, PID 1, dm-verity,
  Windows, Matter, BLE are all genuinely north-star and correctly de-committed.
- Sequencing instinct is correct: R0 scaffolding is zero-risk and parallelizable;
  R1 (MQTT bus) is the highest product value; R7 appliance gating on R1–R6 is
  the right restraint.
- Every code reference the plan makes was verified to exist (see §2).
- The plan correctly inherits the MASTER-TODO 2026-08-30 model-tier conventions.

**However**, the review found **two high-severity defects** that would surface
as soon as execution starts (F1: R1 cannot actually be verified before R4;
F2: no task builds the Docker image the deployment paths depend on), several
medium/low inconsistencies, and one security-relevant issue in the documented
compose template (F6). None invalidates the strategy; all are plan-doc fixes
or task additions.

---

## 2. Verified Against the Code (facts the plan relies on)

Checked 2026-08-31 on `main`:

| Plan claim | Reality | Verdict |
|---|---|---|
| R5.8: wire `os://` tools into `halbert_core/mcp/server.py` | File exists: `halbert_core/halbert_core/mcp/server.py`, 18 tools. **Correction 2026-09-01:** its docstring claims HTTP/SSE is deferred to "Phase 4b", but the transport is in fact implemented in the same file (HTTP/SSE + generated bearer token at line ~1115+) — the docstring is stale, not the code | ✅ exists; docstring correction assigned to R5.8 |
| R1.4: device registry "follows existing `ha_event_mapper.py`" | Exists: `halbert_core/halbert_core/integrations/home_assistant/ha_event_mapper.py` | ✅ |
| Scoping doc: "reuses `FrigateMQTTSubscriber` patterns — proven infrastructure" | Exists: `halbert_core/halbert_core/integrations/frigate/frigate_mqtt_subscriber.py`, uses **aiomqtt** as a lazy optional dependency (consistent with the Haloysius subtractive contract) | ✅ exists; see F8 |
| Scoping doc Path 3: "The agent code already runs in Docker" | **False.** No `Dockerfile`, no `docker-compose.yml`, and no container image reference exists anywhere in the repo. `deploy/` contains only `halbert-home.service`, `halbert-host.service`, `README.md` | ❌ correction needed; see F2 |
| R6.1: compose template references `image: halbert/halbert-core:latest` | That image is referenced **only** in the scoping doc. No task in R0–R7 builds or publishes it | ❌ gap; see F2 |
| R0.7: "add crates/ to CI" | CI exists (`.github/workflows/ci.yml`) and includes a **suite-census meta-gate** that fails CI if any test file exists that no job runs | ✅ exists; see F10 — the census must be extended for `crates/` or R0.7 will fail |
| `crates/` workspace | Does not exist yet (R0 pending). Only existing Rust is `src-tauri` | ✅ as expected |
| Dev environment | Primary dev machine is **macOS**. eBPF (kernel ≥5.8), Landlock (≥5.13), and Btrfs ioctls cannot run or be tested locally | ⚠️ R2/R3/R6.7/R7 all presuppose a Linux VM; see RD |

---

## 3. Findings

### F1 — HIGH: R1 cannot be verified or shipped before R4, but R4 is gated on all of R1+R2+R3

R1's verification criterion is: *"Halbert discovers and controls a Zigbee
device via Zigbee2MQTT + Mosquitto without Home Assistant running."* That
requires the Python-side tasks (R1.4–R1.7: registry, Z2M discovery, agent
tools, event mapper) to actually talk MQTT. But:

- §2 dependency rule: "R4 depends on R1+R2+R3 (wraps all crates)"; §7 repeats it.
- Q3: "the Python agent starts consuming Rust crates after R4 (PyO3 bridge)".

So the Python side of R1 has no working transport until R4 — which cannot
start until R2 (eBPF, ~3 weeks) and R3 (Btrfs/Landlock, ~2 weeks) are done.
The phase advertised as **"highest product value, ~2 weeks"** is not
independently verifiable and slips behind the two hardest phases. This
silently converts the plan's critical path into R0 → R2 → R3 → R4 → R1-done.

**This is the single most important fix.** Options (reviewer: pick one):

- **(a) Incremental FFI (recommended):** redefine R4 as a *recurring* step —
  `halbert-ffi` wraps each crate as that crate completes. R1 earns its
  `halbert_rs.mqtt` module immediately (R4a), R2 earns `telemetry` (R4b),
  R3 earns `snapshots`/`sandbox` (R4c). Then R1 is verifiable end-to-end on
  its own timeline and delivers "HA optional" ~5 weeks earlier than the
  current graph allows.
- (b) Keep R1.3's per-crate PyO3 surface (contradicts the single-`halbert-ffi`
  design; see F3 — not recommended as written).
- (c) Implement R1's Python side against the existing **aiomqtt** client
  first (it already exists and is proven in the Frigate subscriber), then swap
  the transport to `rumqttc` under the hood after R4. Defensible — the
  registry/mapper code wouldn't change — but it demotes the whole point of
  R1 being a Rust crate.

### F2 — HIGH: No task builds the Halbert container image, and the "already runs in Docker" claim is false

The sidecar compose template (`halbert/halbert-core:latest`), R6.7's
integration test, R7.2's appliance compose, and the HA Add-on (R6.3) all
presuppose a Halbert container image. **Nothing in R0–R7 builds one, and none
exists in the repo today** (verified: no Dockerfile anywhere; `deploy/` is
systemd units only). The scoping doc's sentence "The agent code already runs
in Docker" is incorrect and should be struck.

This matters especially because Docker integration is an *intent of the early
phases* (founder direction 2026-08-31), yet as written it sits ~10 weeks out
behind R5. **A container image for the agent has zero Rust dependency**
(pure Python packaging) and can start in parallel with R0.

**Recommended task additions** (proposed numbering; reviewer confirm):

| New task | Description | Model / Effort | Placement |
|---|---|---|---|
| **R0.9** | Author root `Dockerfile` for the Halbert agent (Python runtime, `halbert-mcp-serve` entry, data volume contract) — no GPU, voice, or Tauri desktop; those stay host-side | Sonnet high | R0, parallel-safe |
| **R0.10** | CI job: build + smoke-test the image on every PR; publish to registry on tagged releases | Sonnet med | R0 (extends existing `ci.yml`) |
| R6.1 (revise) | Compose template gets the image from the registry; `halbert.sock` mount becomes **optional** (daemon absent → graceful degradation, per Q3's existing principle) | Sonnet high | R6 as planned, but the *template can be drafted alongside R0.9* since it doesn't need the daemon |

### F3 — MEDIUM: R1.3 per-crate PyO3/C-ABI duplicates the single-FFI design of R4

R1.3 says "Expose C-ABI or PyO3 interface for Python consumption" for the MQTT
crate alone; R4 exists precisely to provide the one `halbert_rs` FFI surface
for all crates. Two overlapping Python-boundary mechanisms invite drift.
**Recommendation:** R1.3 should define only the Rust-side trait contract;
Python exposure happens exclusively through `halbert-ffi` (and per F1(a),
incrementally). Same edit applies to R2.8 and R3.6 — they should read "expose
via `halbert-ffi` when that crate's FFI step lands," not imply separate
surfaces.

### F4 — MEDIUM: §2 dependency graph contradicts §6 on R3's prerequisite

- §2: "R3 depends on R2 (sandbox needs telemetry context)."
- §6 header: "**Prerequisite:** R0. (R2 is recommended but not strictly
  required — sandbox can work without telemetry.)"

§6 is the correct/capable one (Landlock + Btrfs ioctls genuinely don't need
eBPF to function). Align §2 to say: R3 depends on R0; R2 is a *recommended
companion*, not a blocker. This also restores R3 to the parallelizable set,
which the effort summary's parallelization note already assumes.

### F5 — LOW: Task count is wrong in both docs

The commit message, the plan header ("56 tasks across 7 phases (R0-R7)"), and
the MASTER-TODO subsection all say 56. Actual counts: R0=8, R1=9, R2=10,
R3=9, R4=7, R5=14, R6=7, R7=6 → **70 total**; §14's own line "R1-R6 total: 56"
is the only correct usage. Fix: "70 tasks across 8 phases (R0–R7); 56 in the
R1–R6 build phases" in the plan header and MASTER-TODO.

### F6 — MEDIUM (security-relevant): Documented compose template exposes Mosquitto on the LAN

The scoping doc's §7 template puts **all four services** on
`network_mode: host`. Consequences:

1. **Mosquitto binds 0.0.0.0:1883 with no auth configured** — anyone on the
   LAN can publish/subscribe to the device bus. On a template users will copy
   verbatim, this is the one detail that will cause real incidents.
2. Host networking undermines the doc's own "independent services" isolation
   narrative (port collisions; no container DNS).
3. `network_mode: host` behaves differently/absent on Docker Desktop
   (macOS/Windows) — fine for a Linux-only path, but the doc never says so.
4. The `version: "3.8"` key is obsolete under Compose v2 (cosmetic).

Recommended template shape (Linux stated as the only supported host):

- HA Container keeps `network_mode: host` (it needs mDNS/multicast discovery).
- A bridge network for halbert ↔ mosquitto ↔ zigbee2mqtt; publish
  `127.0.0.1:1883:1883` only if host-side tooling needs it.
- Z2M keeps the `devices:` USB passthrough but drops host networking.
- Mosquitto config: explicit `listener 1883 0.0.0.0` **inside the bridge only**,
  plus `password_file` even for localhost (Z2M supports auth; make the
  template teach it by default).

### F7 — LOW: R5.2's `Requires=Btrfs mount` would brick the daemon on non-Btrfs hosts

R3 deliberately ships a non-Btrfs stub; R5.2's systemd unit sketch hard-requires
a Btrfs mount, so `halbertd` would refuse to start on ext4/xfs systems — the
opposite of the graceful-degradation principle in Q3. Use
`ConditionPathIsMountPoint=` on a drop-in for snapshot features, or no
condition at all with runtime feature detection.

### F8 — MEDIUM: Plan never addresses the two-MQTT-stack transition

Today: aiomqtt (Python, lazy optional — correct per the subtractive contract)
serves Frigate. After R1: `rumqttc` (Rust) serves the device bus. The plan is
silent on whether Frigate migrates. **Recommendation:** state explicitly that
aiomqtt stays for Frigate in the R1–R6 timeframe, the Rust bus owns the
device layer, and any Frigate migration onto `halbert_rs.mqtt` is an optional
follow-up, not a requirement. (Also note the pleasant side-effect: the Rust
bus removes aiomqtt from the *device* path even if it lingers for cameras.)

### F9 — MEDIUM: The MCP surface is under-specified — three things are being conflated

1. Existing Python MCP server: stdio, 18 tools, `mcp_response()` egress
   boundary, HTTP/SSE deferred.
2. R5.4: `halbertd` JSON-RPC 2.0 over `/var/run/halbert.sock` (0660, group
   `halbert`) — described as "IPC".
3. R5.8/R6.5: "extend MCP server with `os://` tools" and auto-register to
   Claude/Cursor/Warp.

The plan should state plainly: **the Unix socket is internal IPC, not a second
MCP server.** There remains exactly one external MCP surface — the Python
`halbert-mcp-serve` stdio server — whose new tools
(`create_atomic_snapshot`, `preview_blast_radius`, …) are thin proxies that
call `halbertd` over the socket. This preserves the existing egress boundary
(`mcp_response()`) — a memory-anchored founder security constraint (scrub
deterministically before the model / at the response choke point) that a
second, Rust-side MCP implementation would silently bypass. Also standardize
naming: the docs alternate between the `os://` scheme and `halbert.*` tool
names; pick one convention (tools `halbert.*`; resources `os://` reads fine).

### F10 — LOW: CI suite-census gate will fail the first Rust test unless extended

`ci.yml`'s census meta-gate fails if any test file exists that no job runs.
R0.7 must therefore: (1) add a cargo job (`cargo test --workspace`, clippy
`-D warnings`, `cargo fmt --check`) and (2) register `crates/` in the census
GATES (or teach the census that Rust tests live in-file). Also add
`rust-toolchain.toml` pinning at R0.1 so CI, dev machines, and the future
appliance image build agree on the toolchain.

### F11 — INFO: Execution environment for kernel phases is undocumented

Verified: the dev machine is macOS; R2 (eBPF), R3 (Btrfs/Landlock
integration test), R6.7, and R7 all say "Linux VM" but nothing operationalizes
it. **Recommendation:** add a short `crates/README.md` section (R0.8 owns the
doc) specifying the reference test environment: a Linux VM (UTM/limactl on
the Mac) with a **Btrfs root**, kernel ≥ 5.13, Docker + systemd. Without it,
R2/R3 verification is un-runnable for the person holding the keyboard.

### F12 — INFO: R7.4/R7.5 vs D7 deferral list (clarification only, not an error)

D7 defers "dm-verity" and "signed UKI" to north-star; the scoping doc §6
lists them as "should not be in any near-term plan"; and the plan itself
marks R7 as gated north-star. Since R7.4/R7.5 live *inside* that gated phase,
this is consistent — but the plan's §11 "Explicitly Deferred" table doesn't
mention them, while MASTER-TODO's deferred list does. One clarifying sentence
in §11 ("signed UKI and dm-verity are R7-phase items, gated with the rest of
R7 — deferred from R1–R6, not from the plan") removes the apparent
contradiction.

### F13 — LOW: Scoping doc corrections pending

Two factual strikes in `HA-STRATEGY-SCOPING-AND-DEPLOYMENT-PATHS-2026-08-31.md`
itself (not just downstream):

- Path 3 "What needs to be built: … **The agent code already runs in
  Docker**" → false; replace with "requires the agent container image from
  R0.9/R0.10."
- §7 compose template → revise per F6.

---

## 4. Recommendations (sequencing & process)

### RA — Restructure the critical path around incremental FFI
Adopt F1(a). New spine: **R0 → R1(+R4a) → R2(+R4b) → R3(+R4c) → R5 → R6**,
with R2/R3 still parallelizable where staffing allows. Effect: "HA optional"
becomes deliverable and verifiable after R1 alone; R5's wiring phase then
consumes three *already-bridged* crates instead of doing the first
Python↔Rust contact inside the most complex phase.

### RB — Pull containerization forward to R0
Docker integration is an early-phase goal, and the agent image has no Rust
dependency. R0.9 (Dockerfile) + R0.10 (CI build/publish) + a first draft of
the R6.1 compose template let the whole stack be dogfooded in containers from
week 1. The daemon-dependent volume stays optional. This also unblocks F13's
Path 3 correction and R6.3 (HA Add-on `Dockerfile` becomes a thin wrapper
over the published base image instead of new packaging work).

### RC — One MCP surface, daemon is internal IPC
Adopt F9's statement verbatim as a plan amendment. This is a security-
boundary decision, not style: it keeps `mcp_response()` as the single
deterministic scrub point for every byte that reaches an external LLM client.

### RD — Document the Linux+Btrfs test environment before R2
Per F11: `crates/README.md` gets a "Test environment" section. Gate R2.9 and
R3.8 (the integration tests) on it explicitly.

### RE — Keep the macOS stubs honest
R2.7/R3.7 stubs are the right call; add one line to each: the stub modules
must be exercised in CI on a macOS runner (or at least imported in the Python
test suite) so that "graceful degradation" is tested, not just asserted. The
Q3 fallback path (agent without `halbert_rs`) likewise gets one test in the
existing pytest suite.

---

## 5. What the plan already gets right (do not relitigate)

- Rust/Python boundary rule and the stability test — correct, and the per-task
  "Stable?" column is genuinely useful documentation.
- Explicit deferral table (§11) with revisit triggers — exemplary scope control.
- Fable reserved for security second-opinions on kernel code (R2.10, R3.9,
  R5.14) — consistent with the 2026-08-30 reassessment that implementation
  work doesn't need Fable but kernel-safety review does.
- Q3's graceful-degradation design (`halbert_rs` as an optional dependency)
  — matches the Haloysius subtractive contract; should additionally be
  reflected in packaging (`halbert_rs` as a pip *extra*, e.g.
  `halbert-core[rust]`).
- Q5 monorepo decision — correct; the crates' trait contracts are coupled to
  Halbert's application layer.
- R7 gating ("do not start until R1–R6 are proven in production") — correct
  restraint; R7.1's mkosi-on-standard-distro approach ("Raspberry Pi OS for
  Halbert, not a custom kernel") is the right definition of "distro" here.

---

## 6. Questions for the reviewer

1. **F1 resolution:** incremental FFI (a), per-crate surfaces (b), or
   aiomqtt-first then swap (c)? This document recommends (a) — confirm or
   argue otherwise.
2. **R2.1 (`aya` vs `libbpf-rs`):** the plan recommends `aya` for pure-Rust
   consistency. `aya`'s kprobe support for `tcp_v4_connect` (R2.4) requires
   slightly more ceremony than its tracepoint support — is the consistency
   worth it, or should R2.4 use tracepoints where available and kprobes only
   where not?
3. **F6:** is bridge-network + authenticated Mosquitto the right template
   default, accepting that it makes Z2M onboarding one step harder (Z2M
   device-page discovery of the broker)? Alternative: host networking retained
   but Mosquitto explicitly bound to 127.0.0.1 — simpler, still safe, keeps
   the doc's diagrams unchanged.
4. **R5.1/Q2:** confirm single-binary `halbertd` with the privilege model
   sketched (root daemon for kernel ops; does the MCP proxy path in F9 make
   the "unprivileged for MCP" half of R5.1 moot — i.e., can `halbertd` be
   simpler because external clients never touch it directly)?
5. **R0.9 scope:** should the agent image bake in Ollama/vLLM client config
   expectations (peer-compute model from Batch U6), or stay dumb and receive
   everything via env? Recommend dumb — confirm.
6. Is there any *additional* serious issue in the R0–R7 plan or the deployment
   paths that this review missed? Adversarial pass requested specifically on:
   the R5 privilege/socket model, the Btrfs rollback UX (who decides when a
   snapshot is "safe" to auto-prune), and Z2M's `homeassistant/` vs
   `zigbee2mqtt/` discovery-topic assumption in R1.5.

---

## 7. Proposed edits on review approval

If the reviewer confirms, the following edits land (this session did **not**
mutate the plan docs — per the established request → results → corrections
workflow):

1. Plan §2: R3 prerequisite wording per F4; R4 description changed to
   incremental model per RA; dependency diagram updated.
2. Plan R1.3/R2.8/R3.6: per-crate FFI wording → "via `halbert-ffi`" per F3.
3. Plan header + MASTER-TODO: task count 56 → 70 (56 in R1–R6) per F5.
4. Plan: insert R0.9/R0.10 rows per F2/RB; R6.1 revised (registry image,
   optional sock mount); R6.3 notes dependency on the published image.
5. Plan R5.1/R5.4: add the "one external MCP surface; socket is internal IPC;
   `mcp_response()` remains the only egress boundary" paragraph per F9/RC.
6. Plan R5.2: `Requires=` → conditional/non-blocking per F7.
7. Plan R0.1: add `rust-toolchain.toml`; R0.7: add census-gate note per F10.
8. Plan R2/R3 headers: add test-environment prerequisite per F11/RD; R2.7/
   R3.7: stub-test requirement per RE.
9. Plan §11: one clarifying sentence on R7.4/R7.5 per F12.
10. Scoping doc §7: compose template revised per F6; Path 3 "already runs in
    Docker" corrected per F13; §6/Q3 packaging note (`halbert-core[rust]`
    extra).
11. MASTER-TODO Rust subsection: add R0.9/R0.10 to the phase summary and link
    this review request + results.
