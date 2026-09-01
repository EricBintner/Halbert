# Rust Native Core & HalbertOS — Long-Term Project TODO & Implementation Plan

**Date:** 2026-08-31
**Status:** Living document — synced with MASTER-TODO and the HA strategy scoping decisions. **Augmented per sanity review 2026-08-31; edits landed 2026-09-01.** Findings F1–F13 and recommendations RA–RE applied (see `REVIEW-REQUEST-RUST-NATIVE-CORE-2026-08-31.md`). **Scope: 72 tasks across 8 phases (R0–R7); 56 of them in the R1–R6 build phases.**

**Source documents:**
- `HA-STRATEGY-SCOPING-AND-DEPLOYMENT-PATHS-2026-08-31.md` (8 confirmed decisions)
- `documentation/experimental/` (5 corrected experimental docs)
- `MASTER-TODO.md` (existing work batches U1-U6)
- `REVIEW-REQUEST-RUST-NATIVE-CORE-2026-08-31.md` (sanity review: 13 findings F1–F13 + 5 recommendations RA–RE, verified against `main` 2026-08-31; applied per founder directive 2026-08-31, landed 2026-09-01)

---

## 0. Project Overview & Principles

### What this project is

A multi-phase effort to build a **Universal Rust Core** (`crates/halbert-*`)
that delivers kernel-level features (eBPF telemetry, Btrfs snapshots, Landlock
sandboxing, native MQTT) to the existing Halbert app on standard distros —
without requiring a custom OS. The "HalbertOS" brand applies to a future
turnkey appliance image (pre-configured standard distro + `halbertd`), not a
custom kernel.

**Container deployment is a first-class early-phase citizen, not a distant
Path-2 appendix.** The Docker track (R0.9 Dockerfile + R0.10 CI image
build/publish) starts on day one, in parallel with the R0 scaffolding — the
agent container image is pure Python packaging with **zero Rust dependency**.
Every deployment path in the scoping doc (sidecar compose, HA Add-on, Path 3)
and every integration test that references `image: halbert/halbert-core:latest`
presupposes this image, yet before the 2026-08-31 sanity review no task built
it (verified: no `Dockerfile` exists anywhere in the repo; `deploy/` contains
only `halbert-home.service`, `halbert-host.service`, and `README.md`). The
track exists so the whole stack can be **dogfooded in containers from week 1**.
The canonical published name is **`ghcr.io/ericbintner/halbert-core`** (GHCR
lowercases the repo owner); the old `halbert/halbert-core` placeholder that
appears in pre-review deployment docs is retired.

### What this project is NOT

- A rewrite of the Python agent brain (state machine, CRAG, prompts, RAG)
- A rewrite of the 24 discovery scanners (I/O-bound, not CPU-bound)
- A custom Linux distribution (north-star only, deferred per D7)
- A Windows platform port (deferred per D7)

### Architectural principle

> **Rewrite the interfaces to stable system APIs in Rust.**
> **Keep the application logic in Python.**
> Rust crates are thin native layers; Python is the brain that calls them.

### Stability test (what qualifies for Rust)

A component qualifies for Rust rewrite only if:
1. It wraps a **stable kernel/syscall API** (eBPF, Btrfs ioctl, Landlock) or a
   **stable protocol** (MQTT, PTY) that hasn't changed in years
2. It is **CPU-bound or latency-sensitive** (not I/O-bound text parsing)
3. Its **interface contract** is unlikely to change (the application logic
   on top may churn, but the native layer itself is stable)

### Plan amendments applied 2026-08-31 (sanity review F1–F13 / RA–RE)

The plan was reviewed against `main` before execution began. All findings
accepted and applied per founder directive; the full edit list is §7 of the
review request. Quick index of what changed and where:

| Finding / Rec | Severity | Amendment | Where it lands |
|---|---|---|---|
| **F1 / RA** | HIGH | R4 restructured from a monolithic phase into **three FFI waves** (R4a after R1, R4b after R2, R4c after R3). R1 is now verifiable end-to-end on its own timeline instead of waiting behind R2+R3 | §2 diagram + dependency rule; §7 (R4 wave accounting); §14 effort table |
| **F2 / RB** | HIGH | Docker track added: **R0.9** (root `Dockerfile` for the agent — Python runtime, `halbert-mcp-serve` entry, data volume contract; no GPU/voice/Tauri) + **R0.10** (CI build + smoke-test on every PR, publish to registry on tagged releases). Compose template revises to pull from the registry with an optional `halbert.sock` mount | §3 (R0 rows); §9 (R6.1/R6.3 revisions); §14 |
| F3 | MED | Per-crate PyO3/C-ABI surfaces eliminated. R1.3/R2.8/R3.6 define only the Rust-side trait contract; **all** Python exposure goes through the single `halbert-ffi` crate, incrementally per wave | §4–§6 per-phase task rows |
| F4 | MED | §2 dependency rule corrected: **R3 depends on R0 only**; R2 is a recommended companion, not a blocker. R1/R2/R3 all parallelize after R0 | §2 diagram + dependency rule |
| F5 | LOW | Task counts corrected everywhere: 72 tasks across 8 phases (R0–R7); 56 in R1–R6 | Header; §14; MASTER-TODO subsection |
| F6 | MED (security) | Sidecar compose template revised: HA keeps `network_mode: host` (mDNS), halbert/mosquitto/zigbee2mqtt move to a **bridge network**, Mosquitto bound inside the bridge with `password_file` auth, Linux stated as the only supported host, obsolete `version:` key dropped | Scoping doc §7 (owned there) and §9.1's revised template at `deploy/sidecar/` |
| F7 | MED | R5.2 systemd unit drops the hard `Requires=` on a Btrfs mount — replaced by a conditional drop-in / runtime feature detection, so `halbertd` still starts on ext4/xfs | §8 (R5.2 wording) |
| F8 | MED | Two-MQTT-stack transition stated explicitly: `aiomqtt` (Python, lazy optional — per the Frigate subscriber pattern in `halbert_core/integrations/frigate/frigate_mqtt_subscriber.py`) stays for Frigate through R1–R6; the Rust bus owns the device layer; Frigate migration onto `halbert_rs.mqtt` is an optional follow-up, never a requirement | §4 (R1 section note) |
| F9 / RC | MED | **One external MCP surface.** The `/var/run/halbert.sock` JSON-RPC socket is internal IPC, not a second MCP server. `halbert-mcp-serve` (`halbert_core/mcp/server.py` — stdio, plus the already-implemented HTTP/SSE+bearer transport) remains the only external surface; its new `halbert.*` tools and `os://` resources are thin proxies to `halbertd`. `mcp_response()` stays the single deterministic egress scrub point | §8 (R5.1/R5.4/R5.8 notes); §15 Q2/Q7 |
| F10 | LOW | R0.1 adds `rust-toolchain.toml`; R0.7 must extend the CI suite-census gate (`.github/workflows/ci.yml` fails if any test file exists that no job runs) so Rust tests register, plus the cargo job itself | §3 (R0.1/R0.7 wording) |
| F11 / RD | INFO | Reference test environment documented in `crates/README.md` (R0.8): Linux VM (UTM/limactl on the dev Mac), Btrfs root, kernel ≥ 5.13, Docker + systemd. R2.9 and R3.8 integration tests gate on it explicitly | §5/§6 phase prerequisites |
| F12 | INFO | §11 gains one clarifying sentence: signed UKI and dm-verity are R7-phase items, deferred from R1–R6, not from the plan | §11 |
| RE | (process) | macOS stubs (R2.7/R3.7) must be exercised in CI (or imported in the pytest suite) so graceful degradation is tested, not asserted; the no-`halbert_rs` path gets one pytest | §15 Q3; §3–§6 rows |

---

## 1. Model Tier & Effort Level Conventions

Consistent with MASTER-TODO conventions:

| Model | When to use | Effort levels |
|-------|-------------|---------------|
| **Fable** | Reserved for security review of kernel-level code, founder sign-off on OS-level architecture | n/a (review only) |
| **Opus** | Safety-critical kernel wrappers (eBPF, Landlock, Btrfs), system daemon design, MCP protocol extension | ultracode, max, xhigh, high |
| **Sonnet** | Well-specified mechanical work (FFI bindings, MQTT client, packaging, docker-compose, HA Add-on) | ultracode, max, xhigh, high, med |
| **GLM-5.3** | Default workhorse for Python-side integration (device registry, entity mapping) | ultracode, max, xhigh, high, med |

**Effort level definitions:**
- **ultracode**: Fan-out multi-agent workflow, full verify pass, production-ready
- **max**: Single-agent, maximum effort, thorough testing
- **xhigh**: High effort with extensive testing, but single-pass
- **high**: Standard implementation effort with tests
- **med**: Lighter effort, well-specified, lower risk

---

## 2. Phase Overview

```
            Phase R0: Foundation
            (crates/ workspace + scaffolding)
            ├─ R0.1–R0.8  crates, CI, trait contracts
            └─ Docker track — starts day one, parallel:
               R0.9  root Dockerfile (agent image, zero Rust dep)
               R0.10 CI image build + smoke + registry publish
                       │          dogfood in containers from week 1
        ┌──────────────┼──────────────────────────────┐
        │              │                              │
  Phase R1        Phase R2                       Phase R3
  Native Device   Kernel Telemetry               Atomic Safety
  Bus             (halbert-telemetry             (halbert-snapshots
  (halbert-mqtt   / eBPF)                        + halbert-sandbox)
  + registry)         │                              │
        │              │                              │
  Wave R4a         Wave R4b                      Wave R4c
  halbert_rs.mqtt  halbert_rs.telemetry          halbert_rs.snapshots
  └─ R1.4–R1.9     └─ R2.8 Python consumer       + halbert_rs.sandbox
     unlock HERE        (same leg)                  └─ R3.6 Python consumer
        │              │                              (same leg)
        └──────────────┼──────────────────────────────┘
                       │  (R5 needs ALL THREE waves landed)
            Phase R5: halbertd Daemon
            (systemd/launchd + internal Unix-socket IPC)
            ONE external MCP surface: Python halbert-mcp-serve;
            halbert.* tools / os:// resources proxy /var/run/halbert.sock
                       │
            Phase R6: Deployment Paths
            (sidecar compose on the PUBLISHED registry image
             + HA Add-on wrapping that image + OS-MCP registration)
                       │
            Phase R7: Turnkey Appliance
            (north-star, GATED on R1–R6 + founder approval)
```

**Dependency rule (corrected per F1/RA + F4):**

- **R0** is prerequisite for everything. The Docker track (R0.9/R0.10) has no
  Rust dependency and runs **in parallel with R0.1–R0.8 from day one** (RB).
- **R1, R2, R3 all depend on R0 only and are parallelizable as soon as R0
  lands.** R3 does *not* depend on R2 — Landlock syscalls and Btrfs ioctls
  function without eBPF (F4; §6 always said R2 is "recommended but not
  strictly required" — the §2 rule is now aligned to that). R2 remains a
  *recommended companion* because telemetry context improves sandbox
  observability, but it never blocks R3.
- **R4 is no longer a monolithic phase.** It is a recurring FFI step executed
  as three waves (F1/RA):
  - **R4a** — after R1.1–R1.3 land: `halbert_rs.mqtt`. Unblocks R1's entire
    Python side (R1.4–R1.9: registry, Z2M discovery, agent tools, event
    mapper, dashboard list, tests). *This is what makes R1 independently
    verifiable.*
  - **R4b** — after R2.1–R2.8 land (crate code + Python-side contract):
    `halbert_rs.telemetry`. R2.9 (VM integration test) closes the leg inside
    the same wave.
  - **R4c** — after R3.1–R3.7 land: `halbert_rs.snapshots` +
    `halbert_rs.sandbox`. R3.8 (VM integration test) closes the leg inside the
    same wave.
  - There is exactly **one** Python boundary surface — the `halbert-ffi`
    crate — per F3. No per-crate C-ABI/PyO3 side doors.
- **R5 depends on R4a + R4b + R4c** (it wires all three already-bridged
  crates into `halbertd`; it does not do the first Python↔Rust contact).
- **R6 depends on R5** (Path 2 sidecar needs `halbertd`). Exception per
  F2/RB: the compose template can be **drafted alongside R0.9** and finalized
  once the image is published — only the daemon-dependent volume mount waits
  for R5.
- **R7 is north-star**, gated on R1–R6 completion and founder approval
  (unchanged, per D7).

**What this fixes.** The pre-review graph hid the real critical path: R4 was
gated on R1+R2+R3, so R1's verification criterion (Halbert controls a Zigbee
device via Z2M + Mosquitto with no HA running) could not be reached until the
two hardest phases finished — the "highest product value, ~2 weeks" phase
silently slipped ~5 weeks. Under the wave model, each crate's Python consumers
start **in the same leg** as the crate itself lands, and "HA optional" is
achievable and demonstrably verifiable ~2.5 weeks after R0 instead of ~7. New
spine: **R0 → (R1+R4a ∥ R2+R4b ∥ R3+R4c) → R5 → R6; R7 gated.**

---

## 3. Phase R0 — Foundation (crates/ workspace + agent container + scaffolding)

**Goal:** Create the Cargo workspace, stub all crate skeletons, set up Rust CI —
and ship the **agent container image** (pure Python, zero Rust dependency) so
the Docker deployment paths have a real image to reference from week 1.
**Prerequisite:** None.
**Risk:** Zero on the Rust side (build infrastructure only); Low on the
container side (packaging work against an already-installable package).
**Scope note (RB / F2 amendment):** R0 previously carried 8 tasks. Two
containerization tasks are pulled forward from the deployment phases: nothing
about the agent image needs Rust, and the R6.1 compose template, the R6.3 HA
Add-on, and R7.2 all reference an image (`halbert/halbert-core`) that no task
otherwise builds. R0 now carries **10 tasks**; the plan total rises from 70 to
**72**. Desktop/Tauri, GPU inference, and voice (Wyoming, sherpa-onnx) stay
**host-side** — the container packages the agent brain and dashboard only.

| Task | Description | Model / Effort | Status |
|------|-------------|----------------|--------|
| R0.1 | Create `crates/` directory at repo root with Cargo workspace `Cargo.toml`, **plus `rust-toolchain.toml` pinning the toolchain** (F10 amendment) | Sonnet med | Pending |
| R0.2 | Stub `crates/halbert-mqtt/` — `Cargo.toml`, `src/lib.rs` with trait definitions (`MqttClient`, `DeviceStateCache`), empty implementations | Sonnet med | Pending |
| R0.3 | Stub `crates/halbert-telemetry/` — `Cargo.toml`, `src/lib.rs` with trait definitions (`TelemetrySource`, `EventStream`), empty implementations | Sonnet med | Pending |
| R0.4 | Stub `crates/halbert-snapshots/` — `Cargo.toml`, `src/lib.rs` with trait definitions (`SnapshotEngine`, `SnapshotHandle`), empty implementations | Sonnet med | Pending |
| R0.5 | Stub `crates/halbert-sandbox/` — `Cargo.toml`, `src/lib.rs` with trait definitions (`SandboxEngine`, `SandboxRules`), empty implementations | Sonnet med | Pending |
| R0.6 | Stub `crates/halbert-ffi/` — `Cargo.toml` with `pyo3` dependency, `src/lib.rs` with empty Python module skeleton (`halbert_rs`) | Sonnet med | Pending |
| R0.7 | Add `crates/` to CI — workspace compiles, clippy clean, fmt clean, tests pass (even if empty); **teach the suite-census gate about Rust tests** (F10 amendment); **plus a minimal `rust-macos` job** (build + test on `macos-latest`) so the macOS stub paths of R2.7/R3.7 are exercised in CI, not asserted (RE) | Sonnet med | Pending |
| R0.8 | Document crate trait contracts in `crates/README.md` — the trait definitions ARE the interface spec; Python side will implement against these. **Owns the "Reference test environment" section** (RD/F11 amendment, see below) | Sonnet high | Pending |
| R0.9 | Author root `Dockerfile` for the Halbert agent — Python runtime, `halbert`/`halbert-mcp-serve` entries, data-volume contract mirroring `deploy/README.md`. No GPU, voice, or Tauri desktop. | Sonnet high | Pending |
| R0.10 | CI job: build + smoke-test the agent image on every PR; publish to the registry on tagged releases (extends existing `ci.yml`) | Sonnet med | Pending |

### R0.1 implementation note — workspace + toolchain pin

The workspace manifest lives at the **repo root** so every bare `cargo`
command in this plan works from the root without `--manifest-path` — and the
`rust-toolchain.toml` pin, `.gitignore` (`/target` entry), and the CI job all
hang off the same root. `crates/` holds member crates only:

```toml
# Cargo.toml (repo root)
[workspace]
resolver = "2"
members = [
    "crates/halbert-mqtt",
    "crates/halbert-telemetry",
    "crates/halbert-snapshots",
    "crates/halbert-sandbox",
    "crates/halbert-ffi",
]

[workspace.package]
edition = "2021"
license = "GPL-3.0-or-later"

[workspace.dependencies]
# Single source of truth for shared crate versions (tokio, serde, pyo3, nix, ...)
```

`rust-toolchain.toml` at **repo root** (F10): CI, dev machines, and the future
appliance image build must resolve the identical toolchain. Pin the exact
stable version current on the day R0.1 lands (`rustup show` / `rustc -V`);
the shape:

```toml
[toolchain]
channel = "X.Y.Z"          # exact pin, not "stable" — set on the day R0.1 lands
components = ["clippy", "rustfmt"]
targets = [
    "x86_64-unknown-linux-gnu",   # CI + sidecar/servers
    "aarch64-unknown-linux-gnu",  # Pi / ARM appliance path (R7)
    "aarch64-apple-darwin",       # primary dev machines
]
profile = "minimal"
```

A floating `channel = "stable"` silently re-breaks clippy/fmt gates every
toolchain release, so an exact version pin is the deliverable, with the bump
procedure ("edit one line, PR, CI green") documented in `crates/README.md`.

### R0.2–R0.6 implementation note — stub shape

Each stub crate is the same minimal skeleton: a `Cargo.toml` inheriting
`[workspace.package]` fields, and a `src/lib.rs` containing **only** the trait
definitions plus `todo!()`-bodied or `unimplemented!()`-returning
implementations, and one tautological `#[cfg(test)]` module so
`cargo test --workspace` exercises every crate from day one. The traits are
the deliverable — R0.8 turns them into the interface spec. The crates must
compile on macOS (the dev machines) even where the real backends are
Linux-only: `halbert-telemetry`, `halbert-snapshots`, and `halbert-sandbox`
stubs include the `#[cfg(target_os)]` split now so the macOS graceful-
degradation path (R2.7/R3.7) has scaffolding to grow into.

### R0.7 implementation note — cargo job + census amendment (F10)

`ci.yml` today has six jobs (`suite-census`, `design-tokens`, `design-system`,
`model-picker`, `dashboard-frontend`, `test`) and a meta-gate whose own
comment warns: *"Adding a job below means adding its suite to GATES here, or
this fails."* R0.7 therefore lands both halves in one PR:

1. **New `rust` job:**

```yaml
  rust:
    name: Rust workspace (fmt + clippy + build + test)
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: dtolnay/rust-toolchain@master
        with:
          # `toolchain` input omitted: the action honors the repo-root
          # rust-toolchain.toml pin (R0.1) — never pin the toolchain twice
          components: clippy, rustfmt
      - uses: Swatinem/rust-cache@v2
      - run: cargo fmt --all -- --check
      - run: cargo clippy --workspace -- -D warnings
      - run: cargo build --workspace
      - run: cargo test --workspace
```

2. **Census extension.** The census's `is_test_file()` only recognizes `.py`
   and `.ts/.tsx/.js/.jsx/.mts/.cts` — in-file Rust `#[cfg(test)]` modules are
   invisible to it, so the first real Rust test is only gated if the census is
   taught where Rust tests live. Extend the inline script in `ci.yml`:

```python
          if path.suffix == ".rs":
              # Rust tests live in-crate via #[cfg(test)]; count a .rs file as
              # a test file iff it contains a test module.
              return "#[cfg(test)]" in path.read_text()
```

   and add the gate entry:

```python
              ("crates/",
               "job `rust` -> cargo test --workspace"),
```

   Never add `crates/` to `SKIP`: that would exempt the whole subtree from the
   census permanently.

3. **`rust-macos` job (R2.7/R3.7 + RE — stub honesty).** The kernel crates'
   macOS stub paths must be *exercised*, not asserted. Scope kept minimal
   (macOS runner minutes are 10x): build + test the workspace once; clippy/fmt
   stay on the ubuntu job — this job exists to prove the stubs run on macOS:

```yaml
  rust-macos:
    name: Rust workspace on macOS (stub-path honesty, RE)
    runs-on: macos-latest
    steps:
      - uses: actions/checkout@v4
      - uses: dtolnay/rust-toolchain@master
      - uses: Swatinem/rust-cache@v2
      - run: cargo build --workspace
      - run: cargo test --workspace
```

   The census needs no further change: `crates/` already has its gate entry.

### R0.9 implementation note — agent container `Dockerfile`

Pure Python packaging of `halbert-core` (`halbert_core/pyproject.toml`: name
`halbert-core`, `requires-python = ">=3.10"`, build backend `setuptools>=77`).
The image installs the package **non-editable with the `dashboard` extra** —
the `[dev]` extras are CI tooling and stay out. Per the review's Q5
recommendation (adopted): the image is **dumb** — it bakes in no model
endpoints, no Ollama/vLLM assumptions; everything arrives via environment
variables and mounted config. The `systemd-python>=235` core dependency is
Linux-only and compiles a C extension, so the build is two-stage (CI's `test`
job installs `libsystemd-dev` for the same reason):

```dockerfile
# syntax=docker/dockerfile:1
FROM python:3.12-slim AS builder
RUN apt-get update && apt-get install -y --no-install-recommends \
      gcc libsystemd-dev \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /build
COPY halbert_core/ halbert_core/
# package-data (scopes/*.yml, integrations/*.yml, prompts/*.txt) rides along —
# the pyproject stanza exists precisely so non-editable installs keep them.
RUN pip install --no-cache-dir --prefix=/install "./halbert_core[dashboard]"

FROM python:3.12-slim
COPY --from=builder /install /usr/local
RUN useradd --system --uid 1000 --create-home halbert \
    && mkdir -p /var/lib/halbert /etc/halbert /var/log/halbert \
    && chown -R halbert:halbert /var/lib/halbert /etc/halbert /var/log/halbert
USER halbert
# Data-volume contract mirrors deploy/README.md so systemd and container
# deployments share one mental model:
ENV HALBERT_DATA_DIR=/var/lib/halbert \
    HALBERT_CONFIG_DIR=/etc/halbert \
    HALBERT_LOG_DIR=/var/log/halbert \
    HALBERT_PORT=8000 \
    HALBERT_HOST=0.0.0.0   # dashboard/__main__.py binds 127.0.0.1 by default;
                           # a container must listen on 0.0.0.0 for the
                           # published port (-p 8000:8000) to answer
VOLUME ["/var/lib/halbert", "/etc/halbert"]
EXPOSE 8000
# Console scripts from pyproject.toml [project.scripts]. The dashboard entry
# is the long-running process; halbert-mcp-serve is stdio and is invoked per
# MCP client session (docker exec / host-spawned), never as CMD.
CMD ["halbert"]
```

Explicitly out of the image (host-side per RB): the Tauri desktop shell, GPU
inference, the voice stack (Wyoming ports 10400/10401, sherpa-onnx,
openWakeWord — the `audio-*` and `vision` extras), and the `rag-legacy`/`full`
extras (chromadb + sentence-transformers would multiply image size for a
mid-migration retrieval path). Deliberate failure-mode test: launch with no
`halbert.sock` mount, no `SOURCEPREP_URL`, and confirm the Q3-style graceful
degradation the revised R6.1 template depends on.

### R0.10 implementation note — image CI job

A new `docker-agent-image` job in `ci.yml`. It builds and smoke-tests on every
PR (`pull_request` and main-push triggers are already in place) and publishes
only on version tags. It does **not** touch the suite-census lists: the
census only tracks test *files in the tree*, and the smoke test lives in the
workflow YAML, not in a `test_*` file — verified against the census's
`is_test_file()`/`rglob` logic, so the meta-gate stays green untouched.

```yaml
  docker-agent-image:
    name: Agent container image (build + smoke)
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-buildx-action@v3
      - name: Build the image
        run: docker build -t halbert/halbert-core:ci-${{ github.sha }} .
      - name: Smoke test — dashboard comes up and answers
        run: |
          docker run -d --name halbert-ci -p 8000:8000 \
            halbert/halbert-core:ci-${{ github.sha }}
          for i in $(seq 1 30); do
            curl -sf http://localhost:8000/api/instance/info && exit 0
            sleep 1
          done
          docker logs halbert-ci
          exit 1
      - name: Smoke test — MCP entry point exists
        run: |
          docker run --rm halbert/halbert-core:ci-${{ github.sha }} \
            python -c "from halbert_core.mcp.server import main; print('mcp entry ok')"
      - name: Publish on tags
        if: startsWith(github.ref, 'refs/tags/')
        run: |
          echo "${{ secrets.GITHUB_TOKEN }}" | docker login ghcr.io -u ${{ github.actor }} --password-stdin
          IMAGE=ghcr.io/${{ github.repository_owner }}/halbert-core
          docker tag halbert/halbert-core:ci-${{ github.sha }} $IMAGE:${{ github.ref_name }}
          docker tag halbert/halbert-core:ci-${{ github.sha }} $IMAGE:latest
          docker push $IMAGE:${{ github.ref_name }}
          docker push $IMAGE:latest
```

Registry: GHCR via the built-in `GITHUB_TOKEN` (no new secrets, image lives
beside the repo). On this repo the published name resolves to
**`ghcr.io/ericbintner/halbert-core`** (GHCR lowercases the owner) — that exact
name is the canonical reference in every deployment template and in R6.3/R7.2.
The published `ghcr.io/<owner>/halbert-core` image is what
the revised R6.1 compose template (registry image, optional `halbert.sock`
mount), R6.3 (HA Add-on `Dockerfile` becomes a thin wrapper over this base),
and R7.2 (appliance compose) consume. Published images are `amd64` only at
R0.10; `buildx` is already in the job so adding `arm64` for Pi/ARM servers is
a one-line `platforms:` follow-up when the appliance path needs it, not a
redesign.

### Reference test environment (RD / F11 — hard prerequisite gate)

The primary dev machine is **macOS**. eBPF probes (kernel ≥ 5.8), Landlock
(≥ 5.13), Btrfs ioctls, the R2.9/R3.8 integration tests, R6.7's sidecar
integration test, and R7's image builds **cannot run or be verified locally**.
`crates/README.md` (owned by R0.8) must carry this section, and the tasks
below are **blocked until the checklist passes**:

| Task | Blocked on reference VM because |
|------|---------------------------------|
| R2.9 | eBPF integration test needs real probes on a live kernel |
| R3.8 | Btrfs snapshot + Landlock integration test needs a Btrfs root on kernel ≥ 5.13 |
| R6.7 | Sidecar `docker-compose up` end-to-end test needs native Linux Docker |

**Specification:** a Linux VM on the Apple Silicon dev machine —
**UTM** (GUI; Fedora Workstation aarch64 ISO) or **`limactl`** (CLI;
`limactl start --name=halbert-ref template://fedora`). Fedora is the reference
distro: its **Workstation desktop image has used a Btrfs root by default since
Fedora 33** (Server/Cloud images default to LVM+XFS — if you install Server,
select the Btrfs partitioning layout at install time) and it ships kernels far
above the 5.13 Landlock floor. Requirements, all four
mandatory:

```
kernel >= 5.13   Btrfs root filesystem   systemd   Docker (with compose plugin)
```

First-boot checklist (paste output into the task handoff as gate evidence):

```bash
uname -r                                  # MUST be >= 5.13
findmnt -n -o FSTYPE /                    # MUST print: btrfs
systemctl --version | head -1             # systemd present and PID 1
docker --version && docker run --rm hello-world
test -f /sys/kernel/btf/vmlinux && echo "BTF ok (eBPF CO-RE ready)"
cat /sys/kernel/security/lsm              # Landlock should appear; Fedora enables it
```

A checklist failure is a VM-fixture bug, not a code bug — fix the image
settings (or pick the Fedora Btrfs layout at install time in UTM) before any
R2/R3 task is marked started. The macOS host remains the build-and-lint
machine (`cargo build/clippy/test` all run natively there); the VM is for
kernel-touching verification only.

### Step-by-step execution order

```
Day 1, parallel:
  ├─ R0.1  workspace + rust-toolchain.toml        (everything Rust hangs off this)
  └─ R0.9  Dockerfile                             (no Rust dependency — start immediately)
After R0.1, parallel:  R0.2 → R0.3 → R0.4 → R0.5 → R0.6  (disjoint directories)
After stubs:           R0.7  rust CI job + census amendment (same PR is safest)
Anytime after R0.1:    R0.8  crates/README.md  (trait contracts + reference-test-env section)
After R0.9:            R0.10 docker CI job (needs the Dockerfile to build)
```

### Verification gate (exact commands)

On the macOS dev machine and again in CI:

```bash
cargo build --workspace
cargo clippy --workspace -- -D warnings
cargo fmt --all -- --check
cargo test --workspace
docker build -t halbert/halbert-core:dev .
docker run -d --rm -p 8000:8000 halbert/halbert-core:dev   # then:
curl -sf http://localhost:8000/api/instance/info           # deploy/README verification endpoint
docker run --rm halbert/halbert-core:dev python -c "from halbert_core.mcp.server import main; print('mcp entry ok')"
```

CI green across **all nine** jobs (the six existing + `rust` +
`docker-agent-image` + `rust-macos`) — including `suite-census` with the
`crates/` gate entry — before R0 is called done. On the reference VM: repeat
the four `cargo` commands plus the smoke run, proving the Linux path the
kernel phases will depend on.

### Failure modes + rollback

| Failure | Cause | Response / rollback |
|---------|-------|---------------------|
| `fmt`/`clippy` drift between dev and CI | floating toolchain | `rust-toolchain.toml` exact pin is the fix; never merge with `channel = "stable"` alone |
| suite-census red after R0.7 | a `.rs` file with `#[cfg(test)]` not under `crates/`, or GATES entry missing | amend GATES in the same PR; never add `crates/` to `SKIP` |
| Image build fails on `systemd-python` | missing `gcc`/`libsystemd-dev` in the image | keep the two-stage builder; do not drop the dep (it's a core dependency for Linux journald reading) |
| Image balloons past a few hundred MB | someone installs `[full]`/`[rag-legacy]` (chromadb, sentence-transformers) | the image contract is `halbert_core[dashboard]` only; heavier extras are a separate, deliberate image variant later |
| Container won't boot on a user machine | config/env mismatch vs systemd deployment | the env contract deliberately mirrors `deploy/README.md`; diff `docker inspect` env against the table there |
| Docker Desktop on macOS behaves differently (no host networking) | macOS Docker runs in its own VM | expected and documented: the compose/sidecar path is Linux-only; the reference VM above is where container networking gets exercised |
| R0 must be unwound | n/a | every R0 task is an isolated commit touching only `crates/`, `Dockerfile`, `crates/README.md`, and `ci.yml` — revert individually; nothing else in the repo depends on them yet |

### Dogfooding plan

From R0.10 onward, **the team runs the agent as the container image before
any user does.** The published `ghcr.io/<owner>/halbert-core` image becomes
the daily-driver deployment on the reference VM and any spare Linux box; the
systemd units in `deploy/` stay supported but are no longer the first-tested
path. Rules:

1. A PR's `ci-<sha>` image must be pulled and run for at least one workday
   before the corresponding release tag is cut.
2. Dogfooding includes the **failure path**: run with no `halbert.sock`
   mounted and no `SOURCEPREP_URL` set; the agent must still boot, serve the
   dashboard, and degrade gracefully per Q3 — the exact contract the revised
   R6.1 template ships to users.
3. Any discrepancy between the systemd deployment and the container
   deployment (env handling, paths, ports) is fixed in the container to match
   the documented `deploy/README.md` contract, not the reverse.

---

## 4. Phase R1 — Native Device Bus (halbert-mqtt + Python registry)

**Goal:** Halbert can see and control Zigbee devices via MQTT without HA.
**Prerequisite:** R0 + **R4a** (the incremental `halbert_rs.mqtt` FFI wave defined
in §7). R1 does **not** wait for R2 (eBPF) or R3 (Btrfs/Landlock).
**Risk:** Low — MQTT is a 25-year-old standard. `rumqttc` is production-grade.
**Product value:** High — makes HA optional for core local devices (Layer 2).
**Amendments folded in:** F1/RA (verifiable before R2/R3 via wave R4a), F3
(R1.3 defines the Rust-side trait contract only; all Python exposure goes
through `halbert-ffi`), F8 (explicit aiomqtt coexistence rule).

### 4.1 Dependency restatement (F1 / RA)

Under the original graph, R1's Python side had no working transport until the
monolithic R4 bridge landed — which was itself gated on R2+R3, silently
converting the critical path into R0 → R2 → R3 → R4 → R1-done. Per rec RA,
R4 is a **recurring step**, not a phase gate: `halbert-ffi` wraps each crate as
that crate completes. Wave **R4a** lands the moment R1.1–R1.3 are done and
gives Python `import halbert_rs.mqtt`. The full incremental model (waves
R4a/R4b/R4c) is defined in §7 and not repeated here.

Consequence: R1's phase verification (below) depends only on R0 + R4a. Docker
runs everywhere the dev machine does (macOS included), so **none of R1 needs a
Linux VM** — eBPF, Btrfs, and Landlock are not on this phase's path.

### 4.2 Rust/Python boundary in this phase (F3)

`crates/halbert-mqtt` exports a pure Rust trait contract (`MqttClient`,
`DeviceStateCache`) — `subscribe(topic)`, `publish(topic, payload, qos, retain)`,
`get_state(topic)` — and nothing else. **There is no per-crate PyO3 or C-ABI
surface.** Python sees this crate exclusively through `halbert-ffi`
(`halbert_rs.mqtt`, wave R4a). One FFI surface, one place where the
Rust↔Python contract can drift.

| Task | Description | Model / Effort | Status | Stable? |
|------|-------------|----------------|--------|---------|
| R1.1 | Implement `crates/halbert-mqtt` — `rumqttc` client wrapper, connection management, QoS 0/1/2 handling, auto-reconnect with exponential backoff + jitter (mirrors the proven `FrigateMQTTSubscriber` policy: 1s start, 60s cap, stop after N consecutive auth failures) | Sonnet xhigh | Pending | Yes — MQTT 3.1.1/5.0 is a frozen OASIS standard |
| R1.2 | Implement device state cache in `halbert-mqtt` — in-memory topic → state map, retained-message replay on subscribe, last-will (LWT) offline marking | Sonnet high | Pending | Yes — retained messages and LWT are spec-defined |
| R1.3 | Define the crate's Rust-side trait contract (`MqttClient`, `DeviceStateCache` traits + `MqttConfig` struct with host/port/credentials/TLS). **No PyO3/C-ABI here** — Python exposure happens exclusively through `halbert-ffi` when wave R4a lands (F3) | Sonnet high | Pending | Yes — the interface is `subscribe(topic)`, `publish(topic, payload)`, `get_state(topic)` |
| R1.4 | Build Python `mqtt_device_registry.py` (new package `halbert_core/halbert_core/integrations/mqtt_bus/`) — map MQTT topics to Halbert entity concepts (device_class, entity_id, state, attributes). Pattern follows the existing HA integration package (§4.4) | GLM-5.3 high | Pending | Medium — entity schema may evolve, but the MQTT→entity mapping pattern is stable |
| R1.5 | Build Zigbee2MQTT auto-discovery — subscribe to `zigbee2mqtt/bridge/devices` (always published) and, when present, HA-discovery config under `homeassistant/#`; auto-subscribe to device topics, expose as Halbert entities. Handles both prefix conventions (§4.5) | GLM-5.3 high | Pending | Medium — Z2M discovery topic format is stable, but new Z2M versions may add fields |
| R1.6 | Wire MQTT device bus into agent tools — `turn_on`, `turn_off`, `set_state` via `halbert_rs.mqtt` publish (parallel to existing `integrations/home_assistant/ha_tool.py` — the HA tool layer today talks HA's REST API, e.g. `/api/services/...`) | GLM-5.3 high | Pending | Medium — tool interface follows existing HA tool pattern |
| R1.7 | Wire MQTT events into cognition — `MQTTEventMapper` in the new `mqtt_bus` package, registered as a `secondary_mappers` entry in `get_event_mapper()` (`integrations/cognition_wiring.py`) so the existing `CompositeEventMapper` calls its `populate_cognition()` (§4.4) | GLM-5.3 high | Pending | Medium — follows existing event mapper pattern |
| R1.8 | Frontend: MQTT device list in dashboard — show MQTT-discovered devices alongside HA entities, indicate source (MQTT vs HA) | Sonnet high | Pending | Medium — follows existing device card pattern |
| R1.9 | Tests — unit tests for MQTT client (Rust), device registry, Z2M discovery; integration test against a **Mosquitto container with authentication enabled by default and a loopback-only port publish** (§4.5, §4.7), matching the sidecar compose template's auth *and* exposure posture | Sonnet high | Pending | Yes |

**Verification:** Halbert discovers and controls a Zigbee device via
Zigbee2MQTT + Mosquitto without Home Assistant running. Gate: R0 + R4a only
(§4.7 for the exact commands).

**What stays in Python (may churn):** The device registry, entity mapping, tool
definitions, event mapper. These follow existing patterns but the schema may
evolve.
**What's in Rust (won't churn):** The MQTT transport layer (connect, subscribe,
publish, reconnect, state cache).

### 4.3 Coexistence with aiomqtt (F8)

Two MQTT client stacks will exist side by side after R1. This is deliberate,
not a defect:

- **aiomqtt (Python) stays for Frigate, for the whole R1–R6 timeframe.**
  `integrations/frigate/frigate_mqtt_subscriber.py` (`FrigateMQTTSubscriber`)
  lazy-imports aiomqtt as an optional dependency — the module imports fine
  without it, per the Haloysius subtractive contract — subscribes to
  `frigate/events` and `frigate/reviews`, filters via `FrigateConfig`
  (cameras, labels, zones, min_score), and dispatches to its callback
  (typically `FrigateEventMapper.handle_event`). That is the camera/NVR event
  path, and it is proven.
- **The Rust bus owns the device layer.** All Zigbee2MQTT device traffic —
  discovery, state, and command publish — flows through `halbert_rs.mqtt`.
- Both stacks may connect to the same Mosquitto broker; they simply own
  disjoint topic namespaces (`frigate/` vs `zigbee2mqtt/`+`homeassistant/`).
- **Migrating `FrigateMQTTSubscriber` onto `halbert_rs.mqtt` is an optional
  later follow-up, not a requirement of R1.** The pleasant side-effect stands
  regardless: aiomqtt disappears from the *device* path even while it lingers
  for cameras.

### 4.4 The pattern R1.4/R1.6/R1.7 follow (existing-code grounding)

The HA integration already implements the exact two-stage shape the MQTT bus
replicates, in `halbert_core/halbert_core/integrations/`:

```
  transport                      mapper                     cognition
  ─────────                      ──────                     ─────────
  HAEventStream          ──▶  HAEventMapper.add_event  ──▶  populate_cognition()
  (home_assistant/              (dicts: entity_id,            (flushes pending
   ha_event_stream.py —          domain, old_state,            queue into worries,
   WebSocket to                  new_state, attributes,        drives, emotions)
   /api/websocket,               timestamp)
   subscribe_events              MAX_PENDING_EVENTS = 500,
   state_changed,                drop-oldest, threading.Lock
   FILTERED_DOMAINS,             (REV-03 F1)
   DEBOUNCE_DOMAINS
   {sensor: 30s})

  FrigateMQTTSubscriber  ──▶  FrigateEventMapper.handle_event
  (frigate/                       (via the on_event callback)
   frigate_mqtt_subscriber.py —
   aiomqtt, frigate/events +
   frigate/reviews)
```

Both mappers feed one consumer: **`CompositeEventMapper`**
(`integrations/cognition_wiring.py`, class at line 507). `get_event_mapper()`
builds the primary `SystemEventMapper`, then appends optional secondaries —
`get_ha_event_mapper()`, `get_frigate_event_mapper()` — to a
`secondary_mappers` list and wraps everything in
`CompositeEventMapper(primary=..., secondary_mappers=...)`. The composite calls
`populate_cognition()` on the primary and each secondary (swallowing secondary
exceptions) before each cognitive tick, so the agent's state machine holds
exactly one `event_mapper` reference.

The MQTT phase plugs in at the same seams:

- **R1.4's registry** plays the `HAEventStream` role: it turns bus traffic
  (`zigbee2mqtt/<friendly_name>` state topics, discovery config) into the same
  event dicts — `entity_id`, `domain`, `old_state`, `new_state`, `attributes`,
  `timestamp`.
- **R1.7's `MQTTEventMapper`** plays the `HAEventMapper` role: `add_event()`
  buffer with a bounded queue (same 500-entry, drop-oldest, locked discipline —
  REV-03 F1 exists precisely because unbounded mapper queues already bit us
  once) and `populate_cognition()`. It is registered by adding one block to
  `get_event_mapper()`: `get_mqtt_event_mapper()` → append when non-None. No
  change to `CompositeEventMapper` itself.
- **R1.6's tools** parallel `ha_tool.py`, publishing through
  `halbert_rs.mqtt` instead of the HA REST API.

### 4.5 Z2M discovery-topic reality (R1.5) and broker auth (R1.9)

Z2M's topic conventions, and what R1.5 must handle:

- `zigbee2mqtt/bridge/devices` — a retained JSON array of every paired device
  (friendly_name, ieee_address, model, definition). **Always published**,
  regardless of configuration. This is the discovery source of truth.
- `zigbee2mqtt/<friendly_name>` — per-device state topics (JSON payloads).
- `zigbee2mqtt/bridge/state` and `zigbee2mqtt/bridge/logging` — bridge health
  and log stream (LWT marks the bridge `offline`).
- `homeassistant/<component>/<node_id>/<object_id>/config` — Home Assistant
  discovery config. **Only published when Z2M's `homeassistant:` integration
  is enabled** in `configuration.yaml` (discovery prefix defaults to
  `homeassistant` but is configurable). A user running Z2M without HA — the
  exact audience this phase serves — may never emit these topics.

R1.5 therefore treats `homeassistant/#` as an **optional enrichment layer**
(pre-cooked `device_class`/unit/name metadata when present), never a
requirement. Baseline discovery comes from `zigbee2mqtt/bridge/devices` +
heuristic mapping from Z2M `exposes` definitions to Halbert entity classes.

R1.9's integration test runs Mosquitto **with authentication on by default**,
matching the sidecar compose template's auth posture (password file, no
anonymous access — F6). Test fixture `testdata/mqtt/mosquitto.conf`:

```
listener 1883
allow_anonymous false
password_file /mosquitto/config/password.txt
```

Create the password file once with
`docker run --rm -v "$PWD/testdata/mqtt:/mosquitto/config" eclipse-mosquitto:2 mosquitto_passwd -b -c /mosquitto/config/password.txt halbert testpass`.
This is not ceremony: "works against an open broker" tells us nothing about
the configuration users will actually copy, and auth-broken reconnect loops
are a first-class failure mode (§4.8).

### 4.6 Implementation strategy (order of execution inside R1)

1. **R0 completes** (workspace + stubs + CI). R4a's `halbert-ffi` scaffolding
   (R0.6) already exists at this point.
2. **R1.1 + R1.2 sequentially** (Sonnet) — the state cache layers on the client.
3. **R1.3** — freeze the trait contract; this unblocks both downstream tracks.
4. **R4a** (per §7) — wrap `halbert-mqtt` in `halbert-ffi`; `pip install -e`
   the wheel. **Everything Rust-side up to here is one chain** (~1 week).
5. Then **two tracks parallelize**:
   - GLM-5.3 track: R1.4 → R1.5 → R1.6 → R1.7 (each builds on the previous).
   - Sonnet track: R1.8 (frontend, needs only the registry shape to mock
     against) and the Rust unit-test half of R1.9.
6. **R1.9 integration run + verification gate** (§4.7) closes the phase.

R1 runs on any machine, including the macOS dev box — no Linux VM required
(unlike R2/R3).

### 4.7 Verification gate (exact commands)

```bash
# Rust unit level
cargo test -p halbert-mqtt
cargo clippy -p halbert-mqtt -- -D warnings

# Wave R4a bridge import (see §7 for the R4a definition)
arch -arm64 .venv/bin/python -c "import halbert_rs.mqtt; print(halbert_rs.mqtt.MqttClient)"

# Authenticated broker fixture (new; no Dockerfile or compose file exists in
# the repo today)
docker run -d --name halbert-test-mqtt -p 127.0.0.1:1883:1883 \
  -v "$PWD/testdata/mqtt:/mosquitto/config" eclipse-mosquitto:2

# Python side — run from halbert_core/ with the arch prefix (repo conventions:
# the universal2 venv starts x86_64 without it, and pytest-from-root resolves
# halbert_core as the wrong namespace package)
cd halbert_core
arch -arm64 ../.venv/bin/python -m pytest \
  tests/test_mqtt_device_registry.py \
  tests/test_z2m_discovery.py \
  tests/test_mqtt_event_mapper.py -v

# Phase verification (the R1 acceptance test): with a Zigbee2MQTT instance
# pointed at the broker above and HA NOT running, Halbert lists the Z2M
# devices and toggles one:
arch -arm64 ../.venv/bin/python -m pytest tests/test_mqtt_bus_integration.py -v
# then manually: ask the agent "turn on the desk lamp" and observe the
# zigbee2mqtt/desk_lamp/set publish + state echo in `mosquitto_sub -t '#'`.

docker rm -f halbert-test-mqtt
```

CI registration: the new pytest files must be picked up by an existing job —
the suite-census meta-gate in `.github/workflows/ci.yml` fails on unrun test
files. The cargo side rides on R0.7's workspace job.

### 4.8 Failure modes + rollback

- **Broker down / unreachable:** `halbert-mqtt` reconnects with exponential
  backoff + jitter (1s → 60s cap, the `FrigateMQTTSubscriber` policy). Device
  entities render as `unavailable` from the last-will/state-cache rather than
  freezing on stale values; agent tools return a clean "device bus offline"
  error instead of hanging.
- **Auth failure:** consecutive auth rejections trip the N-strike stop (5,
  matching the Frigate subscriber) and surface a loud config error. Retrying a
  bad password forever is how you get rate-limited by the broker and paged by
  the logs.
- **Retained-message storms:** subscribing to `zigbee2mqtt/#` on a busy broker
  replays every retained topic at once. The state cache (R1.2) absorbs the
  replay before the registry is notified; the mapper queue cap (500,
  drop-oldest) bounds cognition-side memory. Wildcard subscriptions are
  narrowed to bridge + known-device topics after discovery completes.
- **Reconnect resubscription:** `rumqttc` re-subscribes on reconnect; the test
  suite asserts subscriptions are re-issued (kill the broker mid-test,
  restart it, verify state resumes).
- **Z2M bridge offline:** `zigbee2mqtt/bridge/state` LWT flips to `offline`;
  all Z2M-sourced entities degrade together and recover together.
- **`halbert_rs` missing:** the Python side degrades gracefully per Q3 — the
  MQTT tools/registry are simply absent from the catalog (same shape as the
  HA-integration-disabled path), never an import-time crash.
- **Rollback:** every Python piece is a new additive package
  (`integrations/mqtt_bus/`) plus one `get_event_mapper()` append; rollback is
  reverting the append and the package. No existing HA or Frigate code path is
  modified.

### 4.9 Dogfooding plan (run our own Z2M network)

R1 is not done when tests pass; it is done when it runs our house.

1. Stand up a dedicated dev Zigbee network: one coordinator (e.g. a Sonoff
   dongle) + 2–3 cheap devices (bulb, plug, contact sensor), Z2M in Docker
   pointed at the authenticated Mosquitto fixture. (Note: Docker Desktop on
   macOS cannot pass through USB serial — run Z2M from source on the Mac or
   put bridge+Z2M on a small Linux box/SBC; the Halbert side itself runs
   fine on macOS.)
2. Run Halbert against it daily with HA **stopped**. Week-one checklist: all
   devices discovered via `zigbee2mqtt/bridge/devices` (HA discovery
   disabled — proving the `homeassistant/`-optional path), state parity
   correct within 2s, agent `turn_on`/`turn_off` round-trips, broker restart
   recovery without an agent restart.
3. Then start HA against the same broker and confirm HA entities and MQTT
   entities coexist in the dashboard without double-registration (R1.8's
   source indicator).
4. Log every surprise (naming collisions, weird `exposes` payloads, retained
   junk) into the device registry — that log is R1.5's real-world test corpus
   and the seed for the R6.1 sidecar template.

---

## 5. Phase R2 — Kernel Telemetry (halbert-telemetry / eBPF)

**Goal:** Zero-overhead kernel event streaming via eBPF.
**Prerequisite:** R0, **plus the reference test environment** documented in
`crates/README.md` (owned by R0.8, per review F11/RD): a Linux VM
(UTM/limactl on the Mac), kernel >= 5.13 — the eBPF ring buffer needs >= 5.8,
but we standardize the floor on 5.13 to match Landlock (R3) — with a Btrfs
root, systemd, and Docker. R2's verification gate is **un-runnable on the
primary dev machine (macOS)**; do not start R2.9 work before the VM exists.
**Risk:** Medium — eBPF programs require Linux kernel >= 5.13 (our floor),
root access, and the `aya` toolchain. Cannot be tested on macOS beyond the
stub.
**Product value:** High — this is the "zero-overhead observability" claim in
the competitive analysis and the Ring 0 "eBPF Tracepoint Streaming" layer of
`documentation/experimental/HALBERT-OS-DISTRO-AND-UNIVERSAL-RUST-ARCHITECTURE.md`
(`sys_enter_execve`, `oom_mark_victim`, `tcp_connect`, `vfs_unlink` —
the event set below matches that doc). Differentiator vs. all competitors.
**Platform:** Linux only. macOS stub returns empty (Endpoint Security
framework is future research). Per review RE, the stub must be *exercised in
CI*, not merely asserted (R2.7).

**Tracepoint-first policy (review question 2, resolved in-plan):** hook
kernel **tracepoints wherever the kernel exposes one** for the signal we
want; use kprobes only where no tracepoint exists. Tracepoints are stable
kernel ABI; kprobe targets (function names, signatures, struct layouts) are
not and drift between kernel releases. This resolves Q2's `tcp_v4_connect`
question in favor of the `sock:inet_sock_set_state` tracepoint (see R2.4).

| Task | Description | Model / Effort | Status | Stable? |
|------|-------------|----------------|--------|---------|
| R2.1 | Choose eBPF framework — `aya` (pure Rust) vs `libbpf-rs` (C bindings). Recommendation stands: `aya`, for pure-Rust stack alignment, **pending external reviewer confirmation — Q1 (§15) stays open until then**. Whichever is chosen, the change must not alter the `TelemetrySource`/`EventStream` trait contract from R0.3 | Opus high | Pending | Yes — both are stable; `aya` is the Rust-native choice |
| R2.2 | Implement `execve` event — `syscalls:sys_enter_execve` tracepoint, stream process creation events (pid, ppid, comm, filename, bounded argv) via ring buffer | Opus xhigh | Pending | Yes — syscall tracepoints are stable kernel ABI |
| R2.3 | Implement the OOM-kill event — hook the `oom:mark_victim` tracepoint (the correct tracefs/aya attach name; the distro doc's `oom_mark_victim` is informal shorthand for the `TRACE_EVENT(mark_victim)` in `include/trace/events/oom.h`), stream OOM events (pid, comm) | Opus high | Pending | Yes — tracepoint stable since kernel 4.15 |
| R2.4 | Implement outbound TCP connect event — **tracepoint-first (Q2 resolution):** primary probe on `sock:inet_sock_set_state` (present since kernel 4.16, well under our 5.13 floor), consumer filters `newstate == TCP_SYN_SENT` to isolate outbound connects; one tracepoint covers v4+v6 (family field). Fallback only if insufficient: `aya` kprobes on `tcp_v4_connect`/`tcp_v6_connect` — extra ceremony (symbol resolution, two probes, signature drift risk) and a non-stable ABI, so tracepoint is recommended | Opus xhigh | Pending | Yes — tracepoint is stable ABI; the kprobe fallback is not |
| R2.5 | Implement file-deletion event — tracepoint-first: `syscalls:sys_enter_unlinkat` + `syscalls:sys_exit_unlinkat` (path arg from enter, retval from exit). Kprobe `vfs_unlink` only if inode-level detail is later required (same Q2 rule) | Opus high | Pending | Yes — syscall tracepoints are stable ABI |
| R2.6 | Implement ring buffer consumer — parse ring buffer records, convert to typed `TelemetryEvent` structs, expose via async stream. Userspace delivery is a **bounded channel with drop-oldest + drop counter** (§5.3) | Opus xhigh | Pending | Yes — ring buffer format is defined by our eBPF programs |
| R2.7 | macOS stub — `TelemetrySource` trait returns empty stream on non-Linux, logs once at startup. **CI honesty requirement (review RE):** the stub must be exercised, not asserted — a cargo test on a macOS runner that builds + calls the stub, plus one pytest in the existing Python suite that drives the graceful-degradation path | Sonnet med | Pending | Yes — stub interface is stable |
| R2.8 | Expose to Python **via `halbert-ffi` when R2's incremental FFI step (R4b per review F1(a)/RA) lands** — no separate per-crate PyO3 surface (review F3). The Python-side contract is: subscribe to the typed `TelemetryEvent` stream | Sonnet high | Pending | Yes — `TelemetryEvent` struct is the stable contract |
| R2.9 | Tests — unit tests for event parsing (recorded/mock ring buffer bytes, run in the R0.7 cargo CI job); load/unload cycle test (attach+detach 100x, verify no leaked programs via `bpftool prog list`); integration test with real probes — **gated on the reference Linux VM (RD)**, not a hosted CI runner | Opus high | Pending | Yes — event format is defined by our probes |
| R2.10 | Safety review — Fable second opinion, against the explicit checklist in §5.6 | Fable review | Pending | n/a |

### 5.1 Implementation strategy (`aya` layout, attach, consume)

Assuming R2.1 lands on `aya` (pending Q1 confirmation), the crate adopts the
standard aya-rs project template layout — a separate eBPF crate and a
userspace crate, sharing a common types crate:

```
crates/halbert-telemetry/
├── Cargo.toml                  # userspace crate: aya + tokio + thiserror
├── src/lib.rs                  # TelemetrySource / EventStream impl (load, attach, consume)
├── halbert-telemetry-common/   # shared payload structs (Pod/Plain Old Data),
│   └── src/lib.rs              #   #![no_std]; consumed by both crates below
├── halbert-telemetry-ebpf/     # eBPF crate: aya-ebpf, #![no_std] #![no_main]
│   ├── Cargo.toml              #   panic-never; one #[tracepoint] fn per event
│   └── src/main.rs
└── xtask/                      # build orchestration: `cargo xtask build-ebpf`,
                                #   `cargo xtask run` (sudo wrapper for dev)
```

- **Build:** the eBPF crate compiles to BPF bytecode with the `bpfel-unknown-none`
  target (nightly toolchain via `rust-toolchain.toml` from R0.1/F10); the
  userspace crate embeds the compiled object with `include_bytes_aligned!` so
  the shipped artifact is one self-contained library — no clang/libbpf on the
  target host.
- **Attach:** userspace loads via `aya::Ebpf::load` (`Bpf::load` in aya <=
  0.12), fetches each program by name, calls `program.load()`, then
  `TracePoint::attach("syscalls", "sys_enter_execve")`-style calls (or
  `attach("sock", "inet_sock_set_state")`). Each attach returns a link handle
  whose drop detaches the probe (detach-on-drop is part of the R2.10 review).
- **Consume:** events are emitted in-kernel via `bpf_ringbuf_reserve` /
  `bpf_ringbuf_submit` into a fixed-size `BPF_MAP_TYPE_RINGBUF` map; the
  userspace consumer is a dedicated tokio task polling aya's `RingBuf` map,
  copying each record into the shared `halbert-telemetry-common` payload
  struct, and pushing typed `TelemetryEvent`s onto the bounded channel.
- **Ordering:** `BPF_MAP_TYPE_RINGBUF` is chosen over per-CPU perf buffers
  precisely because it preserves **global cross-CPU submission order** — its
  headline property. Events still embed `bpf_ktime_get_ns()` timestamps for
  correlation with external clocks (journald, HA history), and Python-side
  consumers should tolerate the small reorder window that reserve-then-submit
  can introduce around busy producers.

### 5.2 Event taxonomy

| Event | Probe point (primary) | Payload fields | Python reaction use |
|-------|----------------------|----------------|---------------------|
| `ProcessExec` | `syscalls:sys_enter_execve` | ts_ns, pid, ppid, comm, filename, argv (bounded: max args + max len, truncated) | Observation loop: correlate agent-planned commands with actual execs; build process lineage for blast-radius diffs |
| `OomKill` | `oom:mark_victim` | ts_ns, pid, comm | Immediate alert + remediation trigger (memory pressure on the host the agent manages) |
| `TcpConnect` | `sock:inet_sock_set_state` filtered to `newstate == TCP_SYN_SENT`; pid/comm via `bpf_get_current_pid_tgid()`/`bpf_get_current_comm()` at fire time | ts_ns, pid, comm, family, saddr, daddr, dport | Egress watch: unexpected outbound connections feed the deterministic pre-model scrub/egress posture (host telemetry only — never raw payloads) |
| `FileUnlink` | `syscalls:sys_enter_unlinkat` + `sys_exit_unlinkat` | ts_ns, pid, comm, dfd, flags, path (bounded str), retval | Deletion-storm detection → suggest/trigger a snapshot (R3) before bulk deletes; feeds the "guaranteed reversibility" claim |

Payload sizing rules (reviewed at R2.10): every variable-length field is
bounded in the struct (fixed-size arrays with truncation flags); no event
payload ever captures process **environ** (argv only — environ is where
secrets conventionally live); truncation is recorded in a flags field so the
Python side can distinguish "short" from "truncated".

### 5.3 Back-pressure semantics

Two fullness regimes, handled differently:

1. **Kernel ring full (imposed):** if the userspace consumer falls behind,
   `bpf_ringbuf_reserve` returns NULL (the helper signals out-of-space by
   returning no reservation, not an errno) and the sample is dropped in-kernel —
   the kernel cannot block on us. The eBPF program increments a per-event-type
   `ring_dropped` counter map on reserve failure.
2. **Userspace channel full (our policy): drop-oldest with a counter.** The
   consumer drains the ring into a bounded tokio channel (capacity ~1024
   events). On full: evict the oldest queued event, push the new one,
   increment `consumer_dropped_total`. **Justification:** telemetry is
   observability for *current* state — the newest event is always the most
   actionable (an OOM or egress event is useful now, useless after 30 s),
   while drop-newest would let an attacker or a noisy process permanently
   starve the freshest signal, and blocking would push back-pressure into
   the kernel ring and silently convert us to regime (1) anyway. Ordered
   history is not a requirement (§5.1 ordering caveat); both counters are
   surfaced as metrics (`halbert_telemetry_ring_dropped_total`,
   `halbert_telemetry_consumer_dropped_total`) so Python can detect overload
   and react (raise alert, widen ring) instead of losing events silently.

### 5.4 Verification gate (exact commands)

Runs in the **reference Linux VM** from `crates/README.md` (RD) — kernel
>= 5.13 floor. Not runnable on macOS or assumed of hosted CI runners.

```bash
# --- environment check (gate 0) ---
uname -r                                  # must be >= 5.13
ls /sys/kernel/btf/vmlinux                # BTF present (see §5.5 if missing)
cat /sys/kernel/security/lockdown 2>/dev/null   # must not say [confidentiality]

# --- unit tests (also run in the R0.7 cargo CI job) ---
cargo test -p halbert-telemetry

# --- build eBPF objects and run the real-probe integration tests (VM only) ---
cd crates/halbert-telemetry
cargo xtask build-ebpf
sudo -E cargo test -p halbert-telemetry --features integration -- --ignored --test-threads=1

# --- end-to-end demo: stream real events ---
sudo -E cargo xtask run -- --dump-events &   # test consumer
/bin/true                                    # expect one ProcessExec event
curl -s https://example.com -o /dev/null     # expect one TcpConnect event

# --- load/unload leak check (R2.9) ---
sudo bpftool prog list | grep -c halbert || true   # baseline
# run attach/detach cycle test; then:
sudo bpftool prog list | grep -c halbert || true   # must equal baseline
```

Gate passes when: events for all four taxonomy rows are observed end-to-end,
drop counters are zero at idle load, and 100 load/unload cycles leave zero
leaked programs. On success, the R2 half of the distro doc's Ring 0 diagram
(`execve, connect, oom` + unlink streaming through a ring buffer into the
observation loop) is demonstrably true.

### 5.5 Failure modes + rollback

| Failure mode | Detection | Behaviour |
|---|---|---|
| Kernel < 5.8 (no `BPF_MAP_TYPE_RINGBUF`) | `uname -r` check at startup; map creation `EINVAL` | `TelemetrySource` returns empty stream + one log line; agent runs on Python scanners (Q3 graceful degradation) |
| Kernel 5.8–5.12 (ring buffer exists, below our floor) | version check | Warn + run best-effort, but outside the supported matrix — we standardize on 5.13 to match Landlock (RD) |
| Kernel in LOCKDOWN mode (Secure Boot); `lockdown=confidentiality` blocks kernel-memory reads from eBPF | read `/sys/kernel/security/lockdown`; probe load returns `EPERM` | Degrade to stub path; log the lockdown state once. Never tell the user to disable Secure Boot |
| Missing BTF (`/sys/kernel/btf/vmlinux` absent — `CONFIG_DEBUG_INFO_BTF` off) | file check at load | CO-RE relocations fail; fallback: ship the matching kernel's BTF blob from BTFhub (`btfhub-archive`) as an optional asset, else degrade per-probe |
| Individual tracepoint absent (config compiled out) | `TracePoint::attach` error | Disable that probe only (per-probe degradation); other events keep streaming; log once |
| Unprivileged BPF disabled (`kernel.unprivileged_bpf_disabled=1`) | `bpf()` `EPERM` | Non-issue in production (daemon runs privileged, R5); dev/CI uses `sudo -E` as in §5.4 |
| Drop storms (consumer saturated) | drop counters > 0 sustained | Alert via metrics; mitigations: raise channel capacity, filter noisy pids in-kernel. Never switch to an unbounded queue |

**Rollback:** detach-on-drop means "rollback" is process exit — no kernel
state persists. If a bad probe build ever ships, reverting the crate version
and restarting the consumer/daemon fully removes it; nothing remains pinned
in `/sys/fs/bpf` (R2.10 verifies this).

### 5.6 R2.10 — Fable review checklist (what the reviewer verifies)

1. **Bounded loops:** no unbounded loops in any eBPF program; all iteration
   (argv walk, path copy) is `#pragma unroll`-bounded or verifier-bounded
   `for` with explicit constant limits; instruction count well under the
   verifier limit.
2. **Bounded maps:** every map has explicit `max_entries`/fixed size —
   ring buffer fixed (e.g. 1 MiB), lookup maps use `BPF_MAP_TYPE_LRU_HASH`
   so a hostile workload cannot pin host memory.
3. **No unbounded growth in the userspace consumer:** the async channel is
   bounded with the §5.3 drop-oldest policy; no `Vec` accumulates events
   without a cap; batch buffers are size-capped.
4. **Detach-on-drop:** link handles detach their probes on `Drop`; consumer
   shutdown closes all links and map FDs; the load/unload cycle test (R2.9)
   proves zero leaked programs via `bpftool prog list`.
5. **Cleanup on unload:** nothing is pinned under `/sys/fs/bpf` unless
   explicitly intentional and documented; map lifetime is tied to the
   program object.
6. **No plaintext secrets in event payloads:** payload structs carry argv
   only, never `environ`; all strings bounded and flagged when truncated
   (§5.2); events are host-local telemetry — any path that later exports
   them toward an external LLM must pass the existing deterministic
   scrub/egress boundary first (founder-anchored, same rule as
   `mcp_response()`); the reviewer confirms no payload field can carry
   credential-shaped data by construction.

### 5.7 Step-by-step execution order & dogfooding

1. R2.1 (framework decision, awaits Q1 confirmation) →
2. scaffold the §5.1 layout + R2.6 consumer skeleton against mock bytes →
3. R2.2 (first real probe — cheapest tracepoint, proves the whole pipeline) →
4. R2.3/R2.4/R2.5 probes in any order →
5. R2.7 stub + CI honesty jobs (can run in parallel on macOS from step 2) →
6. R2.8 (Python-side contract documented) → **R4b wraps the crate** (R4.3 +
   R4.7's telemetry installment) → R2.9 (unit tests from step 2; VM integration
   last) →
7. R2.10 Fable review, then the phase closes.

**Dogfooding:** once R2.9 passes, run the consumer on the founder's Linux
box for a week, streaming events into the agent's observation loop, and
watch the two drop counters. A week at zero drops under real workload *is*
the "zero-overhead observability" claim's first evidence; sustained drops
mean the §5.3 capacities need tuning before R5 wires the stream into
`halbertd`.

**Verification:** On the reference Linux VM (RD), `halbert-telemetry` streams
real `ProcessExec`, `OomKill`, `TcpConnect`, and `FileUnlink` events to a
test consumer; no kernel panics and zero leaked programs on load/unload
(§5.4). macOS exercised via the stub CI path (R2.7/RE).

**What's in Rust (won't churn):** The eBPF programs, ring buffer parser,
payload/event structs, drop policy. These are defined by the kernel ABI and
our own wire format.
**What stays in Python (may churn):** Which events to react to, how to feed
them into the cognition loop, alert thresholds, reorder-window sizing.

---

## 6. Phase R3 — Atomic Safety (halbert-snapshots + halbert-sandbox)

**Goal:** Btrfs snapshot/rollback + Landlock kernel sandboxing for agent actions.
**Prerequisite:** **R0 only.** R2 is a *recommended companion* (telemetry enriches rollback decisions), **not a blocker** — Landlock + Btrfs ioctls genuinely don't need eBPF to function. The §2 dependency diagram has been corrected to match: R3 hangs off R0, parallelizable with R1 and R2 where staffing allows.
**Risk:** Medium — Btrfs ioctls require privileges and a Btrfs filesystem. Landlock requires kernel >= 5.13. Both are Linux-only.
**Product value:** High — this is the "guaranteed reversibility" and "kernel-enforced blast radius" claims. Core differentiator.
**Platform:** Linux only. macOS stubs return `Unsupported`.
**Test environment (per RD/F11):** R3.8 (integration test) is gated on the `crates/README.md` "Test environment" section owned by R0.8 — a Linux VM (UTM/limactl on the Mac) with a **Btrfs root**, kernel >= 5.13, Docker + systemd. The primary dev machine is macOS; the Landlock eBPF/Btrfs work cannot be verified locally.

| Task | Description | Model / Effort | Status | Stable? |
|------|-------------|----------------|--------|---------|
| R3.1 | Implement `crates/halbert-snapshots` Btrfs backend — `BTRFS_IOC_SNAP_CREATE`, `BTRFS_IOC_SNAP_DESTROY`, `BTRFS_IOC_SUBVOL_CREATE` ioctl wrappers via `nix` crate | Opus xhigh | Pending | Yes — Btrfs ioctls are stable since 2009 |
| R3.2 | Implement `SnapshotEngine` trait — `create_snapshot(label, path)`, `rollback_snapshot(handle)`, `list_snapshots()`. Btrfs implementation + trait + stub for non-Btrfs | Opus high | Pending | Yes — trait contract is stable (create/rollback/list) |
| R3.3 | Implement `crates/halbert-sandbox` Landlock backend — `landlock_create_ruleset`, `landlock_add_rule`, `landlock_restrict_self` syscall wrappers, with **best-effort ABI degradation** (see below). Open sub-decision: evaluate the `landlock` crate's maintenance status vs. direct syscall wrappers before committing to a binding | Opus xhigh | Pending | Yes — Landlock syscalls are stable since kernel 5.13 |
| R3.4 | Implement `SandboxEngine` trait — `create_sandbox(allowed_paths, allowed_network)`, `enter_sandbox()`, `exit_sandbox()`. Landlock implementation + stub for non-Linux | Opus high | Pending | Yes — trait contract is stable (restrict paths + network) |
| R3.5 | Implement cgroups v2 resource limits — CPU, memory, and PID limits for sandboxed command execution only (scoped; see design intent below) | Opus high | Pending | Yes — cgroups v2 is stable since kernel 4.15 |
| R3.6 | Expose to Python **via `halbert-ffi`** — Python agent can create snapshots and enter sandboxes before executing commands. Per F3/RA, this task defines only the Rust-side trait contract; the Python surface lands with R3's FFI step (R4c), not as a separate per-crate binding | Sonnet high | Pending | Yes — interface is `snapshot.create()` / `sandbox.enter()` |
| R3.7 | macOS stubs — return `Unsupported` error, log once at startup. (The agent-level halbert_rs-absent fallback test is owned by R4 §7.3.) **CI-honesty requirement (per RE):** the stub modules must be exercised in CI on a macOS runner (and, once R4c lands, imported in the Python pytest suite) so that graceful degradation is *tested*, not just asserted | Sonnet med | Pending | Yes |
| R3.8 | Tests — unit tests for ioctl wrapping (mock), integration test on Btrfs Linux VM (verification gate below) | Opus high | Pending | Yes |
| R3.9 | Safety review — Fable second opinion on Landlock policy generation; enumerated check-list below | Fable review | Pending | n/a |

### 6.1 Landlock ABI versioning (R3.3 design constraint)

Landlock exposes an explicit ABI version, and `halbert-sandbox` must degrade
best-effort rather than fail closed-or-crash. At engine init:

1. Query the running kernel's ABI:
   `landlock_create_ruleset(NULL, 0, LANDLOCK_CREATE_RULESET_VERSION)`.
2. Build the ruleset enabling **only the access rights that ABI supports**:
   - ABI v1 (kernel 5.13): filesystem access rights only.
   - ABI v2 (kernel 5.19): adds refer/rename/link handling.
   - ABI v3 (kernel 6.2): adds `LANDLOCK_ACCESS_FS_TRUNCATE`.
   - ABI v4 (kernel 6.7): adds network restriction (`LANDLOCK_ACCESS_NET_BIND_TCP` / `CONNECT_TCP`). **Network restriction is only available from ABI v4 — guard it by kernel-version/ABI check. On ABI < 4, a sandbox policy requesting `allowed_network` must either refuse loudly or proceed network-unrestricted with a logged warning; the default is refuse.**
3. Log the effective restriction level at startup (ABI version, which rights classes are enforced, which were dropped). The log line is part of the audit story: "sandboxed with Landlock ABI v2 — network policy not enforced" is an operator-visible fact, not a silent no-op.

Kernels < 5.13 (no Landlock at all) yield an explicit `Unsupported` error
carrying the detected kernel version — never a silent pass-through.

### 6.2 Btrfs privilege model (DESIGN decision)

Snapshot creation via `BTRFS_IOC_SNAP_CREATE` requires effective privileges
(root, or ownership within a suitably-mounted user subvolume tree). The design:

- **Production path is daemon-mediated.** `halbertd` (R5) executes snapshot
  create/rollback/destroy on privileged request over the IPC socket; the Python
  agent and MCP tools (R5.6/R5.8) are thin clients that never call the ioctls
  directly.
- The **PyO3-exposed `SnapshotEngine`** (via `halbert-ffi`, R4c) works when the
  caller has rights — this exists for tests, the CLI, and environments running
  Halbert components as root — but it is not the production call path.
- **Snapshot pool location:** daemon-managed top-level subvolume
  `/.halbert-snapshots/`, created at daemon package install time (the
  R5.10–R5.12 postinst/sysusers hooks) or lazily by R3.1's engine init when run
  privileged.
- **Labeling convention:** `halbert-<purpose>-<timestamp>` —
  e.g. `halbert-pre-execution-20260901T143000Z`, `halbert-pre-upgrade-…`.
  Purpose strings are a small enumerated set (`pre-execution`, `pre-upgrade`,
  `manual`, `scheduled`) so retention and tooling can pattern-match reliably.
- **RETENTION:** labeled snapshots are **never auto-pruned in R1–R6**. Snapshot
  creation is cheap (CoW), but silent deletion of a rollback target under disk
  pressure is exactly the trust-destroying failure this phase exists to prevent.
  A disk-pressure janitor (usage thresholds, oldest-first pruning of
  non-`manual` labels, operator notification before any destroy) is a later
  task — recorded as new open question **Q6** (see §15), pending reviewer.

### 6.3 cgroups v2 (R3.5) design intent — deliberately scoped

R3.5 is **not a container runtime.** No namespaces, no pivot_root, no image or
layer management, no OCI anything. The scope is exactly: when `halbertd`
executes a sandboxed command (a remediation step, an agent tool call that
touches the filesystem), it places the child process into a delegated cgroup
under `/sys/fs/cgroup/halbert/` and writes `cpu.max`, `memory.max`, and
`pids.max` before exec. Values come from policy (Python side, R5 wiring); the
crate provides only `create_cgroup(limits)`, `assign(pid)`,
`destroy_cgroup()`. Purpose: a Landlock-sandboxed command that escapes policy
*intentions* (fork bomb, memory hog) still can't harm the host — resource
containment complements filesystem containment; it does not replace isolation.

### 6.4 Step-by-step execution order

1. **R3.2 first** — land the `SnapshotEngine`/`SandboxEngine` trait contracts
   in R0.4/R0.5 stubs (they are the interface spec; everything below
   implements against them).
2. **R3.1** — Btrfs ioctl wrappers, unit-tested against mocked ioctl
   boundaries on any machine (including macOS; ioctls never fire in mocks).
3. **R3.3 + R3.4** — Landlock backend with ABI-degradation logic and the
   engine trait implementation; resolve the `landlock`-crate sub-decision
   before writing wrapper code.
4. **R3.5** — cgroups v2 scoping implementation (independent of R3.1/R3.3;
   can run in parallel after trait contracts land).
5. **R3.7** — macOS stubs (trivial; slot any time, required before CI wiring).
6. **R3.8** — integration tests on the Btrfs Linux VM (the verification gate
   below); stub-path CI coverage lands here too.
7. **R3.6** — Python exposure via `halbert-ffi`, sequenced with R4c per RA.
8. **R3.9 last** — Fable safety review runs against the *complete* sandbox
   policy generator, after all of the above compiles and passes.

### 6.5 Verification gate (Btrfs Linux VM)

All commands run on the reference VM (Btrfs root, kernel >= 5.13). Snapshot
tests run with privileges; Landlock tests run **unprivileged** (Landlock is
deliberately unprivileged — the sandbox self-restricts).

```bash
# --- Btrfs: create / modify / rollback / verify ---
sudo btrfs subvolume create /var/lib/halbert/testvol
echo original | sudo tee /var/lib/halbert/testvol/marker

# create snapshot via the crate's test harness (runs as root on the VM)
sudo cargo test -p halbert-snapshots --test btrfs_integration create -- --ignored --nocapture
#   harness prints the handle/label, e.g. halbert-pre-execution-20260901T143000Z

echo mutated | sudo tee /var/lib/halbert/testvol/marker
cat /var/lib/halbert/testvol/marker            # expect: mutated

sudo cargo test -p halbert-snapshots --test btrfs_integration rollback -- --ignored --nocapture
cat /var/lib/halbert/testvol/marker            # expect: original  ← gate

# cleanup path also exercised
sudo cargo test -p halbert-snapshots --test btrfs_integration destroy -- --ignored --nocapture

# --- Landlock: write-outside-allowed-paths must be blocked by the kernel ---
# test binary sandboxes itself: only /tmp writable
cargo test -p halbert-sandbox --test landlock_integration -- --ignored --nocapture
#   test body:
#     enter_sandbox(allowed_paths=["/tmp"], network=deny)
#     write /tmp/ok            -> succeeds
#     write /etc/halbert-pwn   -> EACCES (kernel-enforced)  ← gate
#     open TCP connect         -> EACCES, ONLY asserted when ABI >= 4
#   log line must report the effective ABI + enforced rights classes
```

Pass criteria: rollback restores `original`; the `/etc` write is refused with
`EACCES` from the kernel; the effective-ABI log line is emitted; on an
ABI < 4 kernel the network assertion is skipped and the refusal/warning path
is exercised instead.

### 6.6 Failure modes + rollback

| Failure | Behavior | Coverage |
|---|---|---|
| Non-Btrfs root filesystem | `SnapshotEngine::open()` → `Unsupported(BackendUnavailable)`; agent degrades to no-snapshot mode per Q3 principle | **Exercised in CI**: a stub-path test runs on the default ext4 CI runner asserting the graceful error (not just compiled) |
| Kernel < 5.13 (no Landlock) | `SandboxEngine::create()` → explicit `Unsupported` error carrying detected kernel version; never a silent no-restriction pass | Stub/VM test on old-kernel image or mocked ABI query |
| ABI < 4 + network policy requested | Refuse loudly (default) or proceed network-unrestricted with warning log — engine init config selects; default is refuse | Unit test with mocked ABI v2 response |
| Snapshot handle replayed/confused | Rollback validates handle→subvolume mapping before any ioctl; wrong-engine or forged handle → hard error, no filesystem touch | Fable review checklist item, R3.9 |
| `halbertd` absent (pre-R5) | PyO3 path works when caller has rights; otherwise MCP/CLI reports daemon-unavailable, no partial state | R3.8 + R5.13 integration tests |

Rollback of the phase itself: all crates are additive under `crates/`; reverting
R3 is a workspace-member removal with zero Python-side impact (R3.6 exposure
lands via `halbert-ffi`, which degrades per Q3 when the crate is absent).

### 6.7 R3.9 Fable review — enumerated checks

The Fable second opinion is scoped to the sandbox policy generator and must
sign off on each of:

1. **Ruleset layering order** — Landlock layers stack as an intersection
   (each layer can only narrow); verify the generator never creates a later
   layer that is unintentionally *wider* than intended, and that multi-policy
   composition (global baseline + per-step temporal policy) layers in the
   correct order.
2. **No path escape via bind mounts** — Landlock scopes to the mount
   namespace view; verify policy generation resolves real paths (symlinks,
   `..`) against the *current* mount table and that a bind mount into an
   allowed directory cannot smuggle a denied target in.
3. **No escape via `/proc`** — verify `/proc/<pid>/cwd`, `/proc/self/fd`,
   and magic-symlink dereference cannot route around the path ruleset;
   deny/allow decisions on `/proc` covered explicitly, not by accident.
4. **Network restriction gating** — enforceable only from ABI v4; verify the
   guard is by ABI query (not `uname` string parse) and that the ABI < 4 path
   refuses rather than silently proceeds.
5. **Snapshot-handle confusion attacks** — handles are unforgeable, scoped to
   the issuing engine instance, and re-validated (handle → subvolume path →
   label) before `rollback_snapshot()` touches anything; a handle from a
   destroyed snapshot or another engine yields a hard error.

**What's in Rust (won't churn):** The ioctl wrappers, syscall wrappers, ABI
degradation logic, trait definitions, cgroup filesystem writes. These are
kernel ABI.
**What stays in Python (may churn):** Which paths to snapshot, which paths to
allow in sandbox, cgroup limit values, when to rollback, who is notified (the
policy logic).

---

## 7. Phase R4 — PyO3 Bridge (halbert-ffi)

**Goal:** The Python agent can `import halbert_rs` and call each Rust crate as that crate completes.
**Model:** **Incremental (amended per F1(a)/RA).** R4 is no longer a phase-gate on R1+R2+R3. It is a recurring wave that runs immediately after each crate phase: **R4a** wraps `halbert-mqtt` (right after R1.1–R1.3, **before** R1.4 starts), **R4b** wraps `halbert-telemetry` (after R2), **R4c** wraps `halbert-snapshots` + `halbert-sandbox` (after R3). The old R4.1 setup task runs **once**, in R4a.
**Prerequisite per wave:** R4a needs R0 + R1.1–R1.3. R4b needs R4a + R2.1–R2.8 (R2.9's VM integration test concludes the same leg). R4c needs R4a + R3.1–R3.7 (R3.8 concludes the same leg).
**Risk:** Low — PyO3/Maturin is well-established. The only non-trivial piece is R4.3's async bridge.
**Product value:** Critical — without the bridge the Rust crates are inaccessible to the Python agent. Shipping incrementally makes R1 ("HA optional") verifiable end-to-end on its own timeline, ~5 weeks earlier than the old serial graph allowed.

### 7.1 New dependency rule (supersedes §2 and the old §7 wording)

> **Each crate's Python consumers wait only on that crate's wave.**
> R1's Python-side tasks (R1.4–R1.9, tests included) depend on **R4a** — not on R2 or R3.
> R2's Python-side consumers depend on R4b; R3's depend on R4c.
> The old rule "R4 depends on R1+R2+R3 (wraps all crates)" is **superseded**;
> §2's dependency rule and diagram are amended accordingly.

```
R1.1–R1.3 (halbert-mqtt)      ──▶ R4a ──▶ R1.4–R1.9 (registry, Z2M, tools, UI)
R2.1–R2.9 (halbert-telemetry) ──▶ R4b ──▶ Python telemetry consumers
R3.1–R3.8 (snapshots+sandbox) ──▶ R4c ──▶ Python safety consumers
                                          R5 then wires three *already-bridged* crates
```

R5's prerequisite ("needs all crates accessible") is unchanged in spirit: R5
starts only after R4c, but it now consumes three already-bridged, already-
dogfooded crates instead of making first Python↔Rust contact inside the most
complex phase.

### 7.2 Task table (by wave)

Task IDs are stable; the Wave column is new. R4.7 is one task executed in
**three** installments (mqtt scope in R4a, telemetry stream round-trip in R4b,
snapshot/sandbox scope in R4c) — do not renumber it.

| Task | Wave | Description | Model / Effort | Status | Stable? |
|------|------|-------------|----------------|--------|---------|
| R4.1 | R4a | Set up `crates/halbert-ffi` with `pyo3` + `maturin` build config (workspace member `crate-type = ["cdylib"]`, lib name `halbert_rs`, abi3-py310 — see 7.4). Runs **once**. | Sonnet high | Pending | Yes — PyO3/Maturin is stable |
| R4.2 | R4a | Expose `halbert_rs.mqtt` module — `MqttClient`, `DeviceStateCache` Python classes wrapping the Rust implementations | Sonnet high | Pending | Yes — mirrors Rust trait interface |
| R4.6 | R4a, re-runs every wave | Build and publish wheel — `maturin build --release`, verify `pip install` works. CI build matrix (7.5) is set up once here; each later wave re-releases the wheel with the new module included | Sonnet high | Pending | Yes |
| R4.7 (mqtt scope) | R4a | Python integration tests for `halbert_rs.mqtt` — publish/subscribe round-trip against a Mosquitto container, state-cache integrity; **plus** the `halbert_rs`-absent degradation test (7.3) | Sonnet high | Pending | Yes |
| R4.3 | R4b | Expose `halbert_rs.telemetry` module — `TelemetryStream` async iterator wrapping the Rust event stream (async bridge detail in 7.6) | Sonnet xhigh | Pending | Yes — async bridge is the only non-trivial part |
| R4.7 (telemetry scope) | R4b | Python integration test for `halbert_rs.telemetry` — async round-trip stream test on the Linux VM (trigger an exec, assert the event arrives via the Python iterator); macOS stub-path check (empty stream, one log line) | Sonnet high | Pending | Yes |
| R4.4 | R4c | Expose `halbert_rs.snapshots` module — `SnapshotEngine` Python class | Sonnet high | Pending | Yes |
| R4.5 | R4c | Expose `halbert_rs.sandbox` module — `SandboxEngine` Python class with context manager support (`with sandbox.enter(): ...`) | Sonnet high | Pending | Yes |
| R4.7 (safety scope) | R4c | Python integration tests for `halbert_rs.snapshots` + `halbert_rs.sandbox` on the Linux+Btrfs VM (RD environment), verify round-trip data integrity | Sonnet high | Pending | Yes |

### 7.3 One FFI surface, plus the absent-path guarantee (F3 + RE)

**F3 amendment:** there is exactly **one** Python-facing FFI surface —
`crates/halbert-ffi` producing the single `halbert_rs` module. R1.3, R2.8, and
R3.6 define Rust-side **trait contracts only**; Python exposure happens
exclusively through `halbert-ffi`, incrementally per wave. Any per-crate
PyO3/C-ABI exposure language elsewhere in this plan is **superseded** by this
section.

**Graceful degradation (RE amendment):** `halbert_rs` is optional at runtime.
The agent imports it exactly once, behind a bridge module:

```python
# halbert_core/halbert_core/integrations/rust_bridge.py   (new, R4a)
"""Single import boundary for the optional Rust core (halbert-core[rust])."""
try:
    import halbert_rs
    HAS_HALBERT_RS = True
except ImportError:  # halbert-core[rust] extra not installed
    halbert_rs = None
    HAS_HALBERT_RS = False

def has_module(name: str) -> bool:
    """Feature-detect one bridge module: 'mqtt' (R4a), 'telemetry' (R4b),
    'snapshots'/'sandbox' (R4c)."""
    return HAS_HALBERT_RS and hasattr(halbert_rs, name)
```

Consumers never `import halbert_rs` directly — they ask `rust_bridge` and
fall back to the pure-Python path when the answer is no. This matches the
lazy-optional precedent already set by the Frigate subscriber (`aiomqtt`) and
the guarded `haloysius` imports.

**RE test:** one new test file `halbert_core/tests/test_halbert_rs_optional.py`
covers the absent path inside the existing suite:

```python
def test_agent_degrades_when_halbert_rs_absent(monkeypatch):
    import sys, importlib
    monkeypatch.setitem(sys.modules, "halbert_rs", None)  # import -> ImportError
    from halbert_core.integrations import rust_bridge
    importlib.reload(rust_bridge)
    assert rust_bridge.HAS_HALBERT_RS is False
    assert not rust_bridge.has_module("mqtt")
```

The file lands in the already-swept `halbert_core/tests/` tree, so the CI
suite-census gate (F10) covers it with no census change. The suite's existing
`asyncio_mode = "auto"` pytest config also means the R4b async-consumer tests
need no new Python dependencies.

### 7.4 Build configuration — pyo3 + maturin, abi3-py310

`crates/halbert-ffi/Cargo.toml` (the stub from R0.6 grows into this; pin
current-stable versions at implementation time, commit `Cargo.lock`):

```toml
[package]
name = "halbert-ffi"
edition = "2021"

[lib]
name = "halbert_rs"             # the Python import name
crate-type = ["cdylib"]

[dependencies]
pyo3 = { version = "0", features = ["extension-module", "abi3-py310"] }  # pin current stable
pyo3-async-runtimes = { version = "0", features = ["tokio-runtime"] }    # R4b only; pin
tokio = { version = "1", features = ["sync", "rt"] }
halbert-mqtt = { path = "../halbert-mqtt", optional = true }
halbert-telemetry = { path = "../halbert-telemetry", optional = true }
halbert-snapshots = { path = "../halbert-snapshots", optional = true }
halbert-sandbox = { path = "../halbert-sandbox", optional = true }

[features]
default = ["mqtt"]                       # R4a; grows to ["mqtt","telemetry"] at R4b,
                                         # then all three flags (four crates) at R4c
mqtt = ["dep:halbert-mqtt"]
telemetry = ["dep:halbert-telemetry"]
safety = ["dep:halbert-snapshots", "dep:halbert-sandbox"]
```

Maturin project metadata at `crates/halbert-ffi/pyproject.toml`:

```toml
[build-system]
requires = ["maturin>=1"]
build-backend = "maturin"

[project]
name = "halbert-rs"                     # the pip distribution name
requires-python = ">=3.10"

[tool.maturin]
bindings = "pyo3"
features = ["pyo3/extension-module"]
```

**abi3-py310 choice:** `halbert-core` declares `requires-python = ">=3.10"` in
`halbert_core/pyproject.toml`, so the `abi3-py310` floor matches the package
floor exactly — one `cp310-abi3-*` wheel per platform covers every supported
interpreter (3.10, 3.11, 3.12+), with no per-Python-version build matrix.

### 7.5 Wheel build matrix

Wheels land in `target/wheels/`. The two Linux wheels are built on the Linux
VM/CI (the R0.7 cargo job gains a wheel step); the macOS wheel is a dev-only
artifact built locally.

| Wheel tag | Target | Built where | Command | Consumers |
|-----------|--------|-------------|---------|-----------|
| `cp310-abi3-manylinux_2_28_x86_64` | Linux x86_64 | Linux CI, manylinux container (`ghcr.io/pyo3/maturin`) | `maturin build --release --target x86_64-unknown-linux-gnu` | sidecar containers, R7 appliance, generic Linux servers |
| `cp310-abi3-manylinux_2_28_aarch64` | Linux arm64 | Linux CI arm64 runner or cross (`--target aarch64-unknown-linux-gnu`, `--zig` if needed) | `maturin build --release --target aarch64-unknown-linux-gnu` | Pi-class appliance images |
| `cp310-abi3-macosx_*_arm64` | macOS arm64 | local dev machine | `arch -arm64 maturin build --release` | dev dogfooding on the primary Mac |

Linux wheels are published as CI release artifacts (alongside the R0.10
container publish). The macOS wheel is intentionally not published — devs
build it into the `.venv` per 7.7.

### 7.6 Packaging — `halbert_rs` ships as the `halbert-core[rust]` extra (Q3 rewrite)

The old Q3 answer ("the agent's `requirements.txt` gains `halbert_rs` as a
dependency") is superseded. Mechanism — extras for `halbert-core` are declared
in `[project.optional-dependencies]` in `halbert_core/pyproject.toml`
(alongside `dashboard`, `cloud-apis`, `rag-legacy`, …). Add:

```toml
# Native Rust core (crates/halbert-ffi -> module halbert_rs). Strictly
# optional: the agent imports it inside try/except via rust_bridge and
# degrades to pure-Python paths when absent (7.3).
rust = [
  "halbert-rs>=0.1.0",
]
```

- Distribution name is `halbert-rs`; import name is `halbert_rs`. Do not
  conflate them in docs or install instructions.
- The `rust` extra is deliberately **not** folded into the `full` extra: the
  default install stays pure-Python per the Haloysius subtractive contract,
  and container/appliance images opt in explicitly.
  `pip install halbert-core[rust]` is the user-facing opt-in.
- Replacement Q3 answer: *"The Python agent starts consuming Rust crates from
  R4a onward, per wave. `halbert_rs` ships as the optional pip extra
  `halbert-core[rust]`. With the extra absent, the agent runs unchanged on
  pure-Python paths (covered by `tests/test_halbert_rs_optional.py`)."*
  (Q3's graceful-degradation sentence stays; the requirements.txt sentence is
  struck.)

### 7.7 R4.3 technical detail — the async bridge

R2.6 delivers a tokio ring-buffer consumer stream of typed `TelemetryEvent`
structs. R4.3 bridges it to a Python async iterator via `pyo3-async-runtimes`
(preferred; manual `tokio::sync::oneshot`-per-await futures are the documented
fallback if the dep pins fight us):

```rust
// sketch — crates/halbert-ffi/src/telemetry.rs
#[pymethods]
impl TelemetryStream {
    fn __anext__<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let mut rx = self.rx.resubscribe();
        pyo3_async_runtimes::tokio::future_into_py(py, async move {
            match rx.recv().await {
                Ok(ev) => Ok(Some(ev)),                       // next event
                Err(RecvError::Closed) => Ok(None),           // -> StopAsyncIteration
                Err(RecvError::Lagged(n)) => { /* bump dropped counter, keep going */ }
            }
        })
    }
}
```

**Back-pressure policy inherits R2.6 unchanged: drop-oldest + counter.** The
bridge never blocks the producer for a slow Python consumer; lagged events are
dropped and counted. The counter is exposed read-only:

```python
stream = halbert_rs.telemetry.TelemetryStream()
async for ev in stream:
    ...
print(stream.dropped_events)   # R2.6 back-pressure accounting, visible to the agent
```

**GIL rules (hard requirements, review checklist on every `#[pymethods]`):**
- Never hold the GIL across a blocking `recv()`. All waiting happens inside
  `future_into_py`, which parks on tokio and releases the GIL.
- `TelemetryEvent` → Python-object conversion happens only after the await
  completes, briefly re-acquiring the GIL — never around an `.await`.

### 7.8 Verification gates (per wave, exact commands)

**R4a gate (dev Mac, no root):**

```bash
cd crates/halbert-ffi && arch -arm64 maturin develop --release && cd ../..
arch -arm64 .venv/bin/python -c "import halbert_rs; print(halbert_rs.mqtt.MqttClient)"
docker run --rm -d --name halbert-mqtt-smoke -p 127.0.0.1:1883:1883 eclipse-mosquitto:2
arch -arm64 .venv/bin/python - <<'PY'
import halbert_rs
c = halbert_rs.mqtt.MqttClient("localhost", 1883)
c.publish("halbert/smoke", "ok")
assert c.get_state("halbert/smoke") == "ok"
print("mqtt round-trip OK")
PY
docker rm -f halbert-mqtt-smoke
(cd halbert_core && arch -arm64 ../.venv/bin/pytest tests/test_halbert_rs_optional.py -v)
```

**R4b gate (Linux+Btrfs VM per RD, root for eBPF):**

```bash
cd crates/halbert-ffi && maturin develop --release && cd ../..
sudo .venv/bin/python - <<'PY'
import asyncio, halbert_rs
async def main():
    s = halbert_rs.telemetry.TelemetryStream()
    async for ev in s:          # run `ls` in a second shell to trigger execve
        print(ev.kind, ev.pid, ev.comm); break
    print("dropped:", s.dropped_events)
asyncio.run(main())
PY
# macOS honesty check (dev machine): stub yields an empty stream and logs once
arch -arm64 .venv/bin/python -c "import asyncio, halbert_rs; print(asyncio.run(halbert_rs.telemetry.TelemetryStream().__anext__()))"
```

**R4c gate (same VM):** create snapshot of a scratch subvolume → modify a file
→ rollback → verify restored; enter a sandbox with one allowed path → write
outside it → `PermissionError` from the kernel. macOS: both calls raise
`Unsupported` and log once.

Old §7 verification line is superseded by the three gates above; the summary
check remains `python -c "import halbert_rs"` succeeding on every wave.

### 7.9 Failure modes + rollback

| Failure mode | Detection | Prevention / rollback |
|--------------|-----------|-----------------------|
| **GIL deadlock** — a blocking `recv()` executed while holding the GIL stalls the interpreter (deadlock whenever the producer path needs the GIL for callbacks or error conversion) | Async consumer hangs; telemetry integration test hits CI timeout | Hard rules in 7.7; review every `#[pymethods]` for `block_on`/blocking `recv`. Rollback: swap the pyclass body to the manual-futures variant |
| **Version skew between wheel and daemon** — the `halbert_rs` wheel and `halbertd` embed different `crates/halbert-*` builds | `halbert_rs.version_info()` (R4a addition: per-crate semver dict) compared against daemon-reported versions at the R5.4 handshake; mismatch → warn + that module features off | Never crash on skew — degrade via `rust_bridge.has_module`. Republish matched wheel+daemon from one commit |
| **Stale module set** — R4a-era wheel installed on a post-R4b system | `has_module("telemetry")` is `False` | Consumers always gate via `rust_bridge`; treat missing module as extra-absent |
| **Wrong wheel tag installed** | pip refuses at resolve time, or `ImportError` at load | abi3-py310 + the 7.5 matrix is the contract; never hand-build per-Python wheels |
| **Slow Python consumer** floods the bridge | `dropped_events` climbs | By design (R2.6 drop-oldest); alert threshold is app-side policy, stays in Python |

**Universal rollback:** the bridge is optional by construction —
`pip uninstall halbert-rs` returns any system to the pure-Python baseline with
zero code changes. That is the escape hatch for every bridge failure.

### 7.10 Dogfooding plan

- **R4a:** the dev machine's own Halbert instance runs all device-bus traffic
  through `halbert_rs.mqtt` against the real Mosquitto + Zigbee2MQTT broker
  (Frigate stays on aiomqtt per F8). Watch reconnect behavior across broker
  restarts for a week before R1.9 signs off.
- **R4b:** on the Linux VM, run the agent under its own telemetry stream —
  observe the agent's own `execve`/`vfs_unlink` activity; use `dropped_events`
  as the load signal during a full agent session.
- **R4c:** wrap one real agent maintenance action (config edit + validation)
  in snapshot → act → verify → rollback-or-keep on the Btrfs VM.
- **Degradation dogfood:** keep one permanently extra-less install (a second
  checkout, plus the 7.3 pytest in CI) exercising the absent path continuously.
  The test is the gate; the running system is the proof.

### 7.11 Effect on §14 effort summary

R4 remains **7 tasks / ~1 engineering week** in aggregate; the calendar
placement changes — each wave is ~1–2 days slotted immediately after its crate
phase (R4a after R1.3, R4b after R2, R4c after R3). The §14 R4 row should read
"7 (3 waves)" and its prerequisite note updated per 7.1.

---

## 8. Phase R5 — halbertd Daemon (systemd + proxies into the existing MCP server)

**Goal:** `halbertd` as a systemd/launchd service providing eBPF telemetry, Btrfs snapshots, and Landlock sandboxing — wired into the agent through **one** external MCP surface (see 8.1).
**Prerequisite:** R4 (needs all crates accessible).
**Risk:** Medium — system service packaging, privilege management.
**Product value:** Critical — this IS the near-term "HalbertOS." Without it, the kernel features are library-only.

> **Amendments from external review 2026-08-31** (findings F7, F9; recommendation RC; reviewer questions 3–4):
> 1. **F9/RC (headline): there is exactly ONE external MCP surface** — the existing Python server. The daemon's socket is internal IPC. See 8.1.
> 2. **Reviewer Q4 → R5.1 simplification:** because external clients never touch `halbertd`, the split-privilege design ("root for kernel ops, unprivileged for MCP") loses its second half. See 8.3.
> 3. **F7 → R5.2:** no `Requires=` on a Btrfs mount. Runtime feature detection; the unit starts everywhere. See R5.2 row and 8.4.

### 8.1 One MCP Surface, the Socket Is Internal IPC (F9/RC)

Three things were being conflated. Stated plainly:

1. **The existing Python MCP server** — `halbert_core/halbert_core/mcp/server.py` — is the **only** surface external LLM clients ever talk to. It serves **18 tools** (`get_vitals` … `get_autonomy_level`/`set_autonomy_level`) over **stdio**, and additionally over **HTTP/SSE with a generated bearer token** — that transport (its docstring's "Phase 4b") is already implemented in the same file; the module docstring is stale on this point and R5.8 ships a one-line docstring correction alongside. Every result, on both transports, passes through **`mcp_response()`** (`halbert_core/halbert_core/mcp/response.py`) — the deterministic credential-scrub at the response choke point. This is a **founder security invariant**: same-user `cat` access does not justify raw host config flowing into a vendor's cloud context; the scrub happens before the model, at the egress boundary, and it is the single point where that happens.
2. **`halbertd`'s JSON-RPC 2.0 over `/var/run/halbert.sock` (R5.4) is INTERNAL IPC.** It is never registered with any AI CLI, never bound to TCP, never exposed to external LLM clients. Its only caller is Halbert's own Python process running as the `halbert` user.
3. **The new daemon-backed tools (R5.8) are thin proxies inside the Python server.** They call `halbertd` over the socket and pass **every response through `mcp_response()`** before returning — even though daemon responses should never contain secrets. The rule is absolute: every byte that reaches an external client crosses the scrub.

There is **no Rust-side MCP implementation and never will be**: a second MCP stack would silently bypass the egress boundary. RC is adopted verbatim as a plan amendment.

```
 External LLM clients (Claude Code, Cursor, Warp)
        │  MCP over stdio
        ▼
  halbert-mcp-serve                      (EXISTING Python server — 18 tools today,
        │                                 + halbert.* proxies added in R5.8)
        │  every response → mcp_response()   ◄── SINGLE EGRESS BOUNDARY (invariant)
        ▼  daemon-backed calls only
  /var/run/halbert.sock   JSON-RPC 2.0, 0660 root:halbert   (INTERNAL IPC — never external)
        ▼
  halbertd (root or ambient caps) ──► halbert-telemetry / halbert-snapshots / halbert-sandbox
        ▼
  host kernel (eBPF ring buffers, Btrfs ioctls, Landlock/cgroups)
```

### 8.2 Naming Convention: tools are `halbert.*`, resources are `os://` (F9)

The docs previously alternated between `os://` and `halbert.*`. Picked convention:

| Surface | Namespace | Examples | Served by |
|---|---|---|---|
| Existing 18 tools | unprefixed (names frozen — do not rename) | `get_vitals`, `ha_call_service`, `get_config_value` | Python server, in-process |
| New daemon-backed tools | `halbert.*` | `halbert.create_atomic_snapshot`, `halbert.rollback_snapshot`, `halbert.execute_transactional_step`, `halbert.preview_blast_radius` | thin proxy → `halbertd` over the socket |
| New in-process tools | `halbert.*` | `halbert.query_rag` (RAG lives in Python, mid-migration — not daemon work) | Python server, in-process |
| Read-only host views | `os://` **MCP resources** (not tools) | `os://vitals`, `os://snapshots`, `os://telemetry` | proxy or in-process — always through `mcp_response()` |

`halbert.preview_blast_radius` is a **hybrid**: static path analysis workspure-Python, enriched with snapshot/diff data when the daemon is reachable. Daemon-absent behavior is defined per Q3 (graceful degradation), not by hiding the tool.

The socket protocol methods mirror the crate traits directly (`telemetry.subscribe`, `snapshot.create`, …) — one naming system end to end, and the IPC names are never visible to external clients anyway.

### 8.3 Privilege Model (R5.1 — decision-proposal, pending reviewer confirmation)

Reviewer question 4 asked whether F9 makes the "unprivileged for MCP" half of R5.1 moot. It does: `halbertd` serves no MCP at all, so it needs no unprivileged front half. **Decision-proposal (recorded here, not yet ratified):**

| Variant | Mechanism | Trade-off |
|---|---|---|
| **A — single root daemon, capabilities bounded (recommended)** | systemd unit starts as root; privileges bounded with `CapabilityBoundingSet=CAP_BPF CAP_SYS_ADMIN CAP_DAC_READ_SEARCH` (`AmbientCapabilities` only applies to *non-root* services; a root process's caps are bounded via the bounding set); socket `0660 root:halbert` | Least privilege. `CAP_BPF` needs kernel ≥ 5.8 (already the eBPF floor); Btrfs management ioctls need `CAP_SYS_ADMIN` on all kernels. Caps must be re-verified against each crate's actual syscalls during R5.7. |
| **B — plain root daemon (fallback)** | Root process, socket `0660 root:halbert`, `NoNewPrivileges=true` where compatible | Simplest to reason about; larger blast radius if the daemon is compromised. |

Both variants: the agent and dashboard join group `halbert` to reach the socket. One binary, one unit — Q2's single-binary recommendation stands. **Do not overclaim:** this collapse of the split-privilege design is proposed, not confirmed; final answer awaits the reviewer's reply to Q4 and Fable's R5.14 review.

### 8.4 Socket Protocol v1 (R5.4 detail)

- JSON-RPC 2.0, newline-delimited frames, over `/var/run/halbert.sock` (0660, owner `root:halbert`).
- **Versioned handshake:** the first frame must be `halbert.hello { "protocol": 1 }`. The daemon replies with its supported protocol range and rejects unknown majors with a structured error. This is the upgrade path: v1 is frozen once R5 ships; breaking changes go to v2 alongside v1 for one release.
- Methods mirror the crate traits: `telemetry.subscribe`, `snapshot.create|rollback|list`, `sandbox.create|enter`. Feature-unsupported errors are structured (`{"code": -32001, "data": {"feature": "snapshots", "reason": "not_btrfs"}}`) so the Python proxy can translate them into the actionable error text in 8.6.
- No tokens, no TLS: filesystem permissions ARE the auth boundary, which is exactly why the socket must never leave the host.

### Task Table (14 tasks — IDs unchanged)

| Task | Description | Model / Effort | Status | Stable? |
|------|-------------|----------------|--------|---------|
| R5.1 | Design `halbertd` architecture — **single binary** (Q2), internal IPC socket (`/var/run/halbert.sock`), privilege model per 8.3 (**decision-proposal: single root daemon with ambient caps; pending reviewer Q4 confirmation**). No MCP serving in the daemon — F9/RC. | Opus xhigh | Pending | Medium — daemon architecture is a design decision |
| R5.2 | Implement systemd unit file — `halbertd.service` with `After=network.target` and **runtime Btrfs detection (F7): no `Requires=` on any mount**. Snapshot RPCs self-disable on non-Btrfs roots; the unit starts on ext4/xfs everywhere. | Sonnet high | Pending | Yes — systemd unit format is stable |
| R5.3 | Implement launchd plist (macOS) — `ai.halbert.halbertd.plist` with KeepAlive and RunAtLoad. Daemon runs, kernel features return unsupported (stubs, per R2.7/R3.7). | Sonnet high | Pending | Yes — launchd plist format is stable |
| R5.4 | Implement Unix socket IPC server — JSON-RPC 2.0 over `/var/run/halbert.sock`, auth via socket permissions (0660, group `halbert`), **protocol v1 with `halbert.hello` handshake (8.4)**. **Internal IPC only — never registered with external clients (F9/RC).** | Opus high | Pending | Yes — JSON-RPC 2.0 is a stable spec |
| R5.5 | Wire telemetry stream into daemon — `halbertd` subscribes to eBPF events, exposes via IPC `telemetry.subscribe` method | Opus high | Pending | Yes — follows R2 interface |
| R5.6 | Wire snapshot engine into daemon — `halbertd` exposes `snapshot.create`, `snapshot.rollback`, `snapshot.list` via IPC | Opus high | Pending | Yes — follows R3 interface |
| R5.7 | Wire sandbox engine into daemon — `halbertd` exposes `sandbox.create`, `sandbox.enter` via IPC. Verify the ambient-cap set from 8.3 against Landlock/cgroups syscalls; daemon handles privilege escalation for Landlock setup | Opus xhigh | Pending | Yes — follows R3 interface |
| R5.8 | Extend the **existing Python MCP server** (`halbert_core/mcp/server.py`) with the new surface — tools `halbert.query_rag`, `halbert.preview_blast_radius`, `halbert.create_atomic_snapshot`, `halbert.rollback_snapshot`, `halbert.execute_transactional_step`; resources `os://vitals`, `os://snapshots`, `os://telemetry`. Daemon-backed tools are **thin socket proxies; every response passes `mcp_response()`** (egress invariant). Naming per 8.2. | Opus xhigh | Pending | Medium — tool definitions are new, but MCP protocol is stable |
| R5.9 | Implement `halbertd` CLI — `halbertd start/stop/status/snapshot list/rollback <id>` (talks to the running daemon over the socket, same protocol v1) | Sonnet high | Pending | Yes |
| R5.10 | Package for apt (Debian/Ubuntu) — `.deb` per 8.5: binary, systemd unit, postinst creates `halbert` system user/group + dirs, enables unit | Sonnet high | Pending | Yes |
| R5.11 | Package for pacman (Arch) — `PKGBUILD` per 8.5: `sysusers.d` entry, systemd unit, same layout as the .deb | Sonnet high | Pending | Yes |
| R5.12 | Package for Homebrew (macOS) — `Formula` with launchd plist. **Ships stubs:** daemon installs and runs, eBPF/Btrfs/Landlock report unsupported — keeps the macOS path honest (RE) | Sonnet high | Pending | Yes |
| R5.13 | Tests — integration test on the R0 Linux VM reference environment: start daemon, `halbert.hello` handshake, call each IPC method, verify structured unsupported-errors on a non-Btrfs filesystem, verify daemon-down degradation of the R5.8 proxies | Opus high | Pending | Yes |
| R5.14 | Security review — Fable second opinion on daemon privilege model (8.3), IPC auth (8.4), and **confirmation that no second egress path exists** — every externally reachable byte goes through `mcp_response()` | Fable review | Pending | n/a |

### 8.5 What the Packages Actually Contain (R5.10–R5.12 expanded)

Common filesystem layout (matches the existing `deploy/` conventions — `halbert` user, `/etc/halbert`, `/var/lib/halbert`, `/var/log/halbert`):

| Path | Owner / mode | Contents |
|---|---|---|
| `/usr/bin/halbertd` | root:root 0755 | Single Rust binary (all crates linked in) |
| `/lib/systemd/system/halbertd.service` (Arch: `/usr/lib/systemd/system/`) | root:root 0644 | Unit from R5.2 — no Btrfs `Requires=` |
| `/etc/halbert/halbertd.toml` | root:halbert 0640 | Daemon config: socket path, snapshot root, telemetry ring size |
| `/var/lib/halbert/daemon/` | halbert:halbert 0750 | Daemon state (snapshot registry, telemetry spill) |
| `/var/run/halbert.sock` | root:halbert 0660 | Created at bind time by the daemon; tmpfs, recreated per boot |
| Logs | journald | `journalctl -u halbertd` is the primary log path; no file logging on Linux |

- **R5.10 `.deb`:** above files + `postinst` that runs `adduser --system --group --home /var/lib/halbert halbert` (idempotent), creates the state dir, and `deb-systemd-helper enable halbertd`; `prerm` stops the unit. The Python-side companion is the `halbert-core[rust]` pip extra (ships the `halbert_rs` wheel from R4.6) — packages recommend it, never vendor it.
- **R5.11 `PKGBUILD`:** same payload; user creation via `/usr/lib/sysusers.d/halbert.conf` (`u halbert - "Halbert system daemon" /var/lib/halbert`) — the Arch idiom, no install-script useradd.
- **R5.12 brew Formula:** installs the binary, writes `ai.halbert.halbertd.plist` (R5.3, `StandardOutPath`/`StandardErrorPath` under Homebrew's `var/log`), and prints a caveats block stating that kernel features are stubs on macOS.

### 8.6 Failure Modes + Rollback

| Failure | Behavior | Repair |
|---|---|---|
| `halbertd` down / not installed | Agent continues on the pure-Python path (Q3 principle): no eBPF, no snapshots, no Landlock, all scanners unaffected. R5.8 proxy tools return a structured error: "halbertd not reachable at `/var/run/halbert.sock` — start with `sudo systemctl start halbertd` or install the halbertd package" | Start/install daemon; nothing else changes |
| Socket permission denied (caller not in group `halbert`) | Proxy error names the fix: `sudo usermod -aG halbert <user>` then re-login | Group membership |
| Protocol version mismatch (old agent, new daemon) | `halbert.hello` rejected; agent logs once and degrades to the pure-Python path | Upgrade Python side; v1 stays frozen precisely so this is rare |
| Non-Btrfs root | `snapshot.*` returns structured `not_btrfs`; proxies surface "snapshots require a Btrfs root (kernel feature unavailable on this host)" | Re-root to Btrfs, or accept degraded mode |
| Package upgrade goes bad | `apt install ./halbertd_<prev>.deb` / `pacman -U` downgrade; daemon state in `/var/lib/halbert/daemon/` is not schema-versioned to the package in v1 — snapshots on disk survive any downgrade | Rollback package; snapshots are Btrfs objects, independent of the daemon |

### 8.7 Dogfooding Plan

- Install the R5.10 `.deb` on the **R0 reference Linux VM** (Btrfs root, kernel ≥ 5.13 — the environment RD adds to `crates/README.md`) and run the founder's daily-driver workload through it: snapshots before any config mutation task, telemetry stream visible in the dashboard.
- Install the R5.12 brew formula on the macOS dev machine **with stubs live** — the "graceful degradation" path is exercised daily, not asserted (RE).
- Every R5 PR must pass R5.13 on the reference VM; stubs must stay import-clean in the macOS CI job.

**Verification gate (exact commands):**

```bash
# On the R0 reference Linux VM (Btrfs root, kernel >= 5.13):
sudo apt install ./halbertd_0.1.0_amd64.deb
systemctl status halbertd                       # active (running)
sudo -u halbert halbertd status                 # protocol v1, features listed
halbertd snapshot list                          # via socket, as root
claude mcp add halbert -- halbert-mcp-serve     # register the EXISTING server
# In Claude Code: call halbert.create_atomic_snapshot → returns a handle
#                 call halbert.rollback_snapshot with it → pre-snapshot state restored
# Repeat on an ext4 VM: unit starts, snapshot.* returns structured not_btrfs errors.
```

---

## 9. Phase R6 — Deployment Paths (sidecar + HA Add-on + OS-MCP)

**Goal:** Document and package all three near-term deployment paths.
**Prerequisite:** R5 for the *full* template (daemon-mounted variant). The compose template and agent image are unblocked earlier (R0.9/R0.10, RB) — R6.1 finalizes and documents them.
**Risk:** Low — mostly documentation and packaging.
**Product value:** High — enables user adoption across all three paths.

> **Amendments from external review 2026-08-31** (findings F2, F6, F13; recommendation RB; reviewer question 3):
> 1. **F2/RB:** the agent container image is **built by R0.9 and published by R0.10** — nothing in R6 builds it. The template *pulls* `ghcr.io/ericbintner/halbert-core:latest`. The scoping doc's "the agent code already runs in Docker" was false and is struck (F13).
> 2. **F6:** the revised template (9.1) drops host-networking-everywhere, puts Mosquitto behind a `password_file`, publishes `1883` on loopback only, and drops the obsolete `version:` key. Bridge + authenticated broker is the adopted default (reviewer Q3's host-net alternative rejected for the *template* — a template users copy verbatim must fail safe on the LAN).

### 9.1 Revised Sidecar Template (R6.1 — F6)

**Linux hosts only.** `network_mode: host` is used exactly once (HA, mDNS — see the callout), and host networking behaves differently/absent under Docker Desktop on macOS/Windows, so this path is not offered there.

```yaml
# deploy/sidecar/docker-compose.yml — Halbert sidecar deployment (Linux only)
# Compose v2 — no top-level `version:` key (obsolete).

services:
  halbert:
    image: ghcr.io/ericbintner/halbert-core:latest   # pulled from GHCR (built by R0.9, published by R0.10)
    networks:
      - halbert-net
    extra_hosts:
      - "host.docker.internal:host-gateway"   # reach host-networked HA
    volumes:
      - halbert-data:/data
      # OPTIONAL — only when halbertd (R5) is installed on the host.
      # Without this mount the agent runs the pure-Python path (Q3):
      # no eBPF telemetry, no snapshots, no sandbox.
      # NOTE: halbertd must be running BEFORE this container starts, or
      # Docker creates an empty directory at the mount point instead of
      # binding the socket file.
      # - /var/run/halbert.sock:/var/run/halbert.sock
    environment:
      - HALBERT_HA_URL=ws://host.docker.internal:8123/api/websocket
      - HALBERT_MQTT_HOST=mosquitto:1883
      # MQTT credentials generated in deploy/sidecar/README.md step 2 (R6.2);
      # consumed by the R1.6 agent tool wiring.
    depends_on:
      - mosquitto

  mosquitto:
    image: eclipse-mosquitto:2
    networks:
      - halbert-net
    ports:
      # Loopback ONLY — the LAN never sees 1883. Required so the
      # host-networked HA container can reach the broker at 127.0.0.1:1883,
      # and so host-side tooling (mosquitto_sub) can still debug.
      - "127.0.0.1:1883:1883"
    volumes:
      - ./mosquitto/mosquitto.conf:/mosquitto/config/mosquitto.conf:ro
      - ./mosquitto/passwords:/mosquitto/config/passwords:ro
      - mosquitto-data:/mosquitto/data

  zigbee2mqtt:
    image: koenkk/zigbee2mqtt:latest
    networks:
      - halbert-net
    ports:
      - "127.0.0.1:8080:8080"   # Z2M frontend, loopback only (onboarding UX)
    volumes:
      - z2m-data:/app/data
      - /run/udev:/run/udev:ro
    devices:
      - /dev/ttyUSB0:/dev/ttyUSB0   # Zigbee coordinator — passthrough kept
    depends_on:
      - mosquitto

  homeassistant:
    image: ghcr.io/home-assistant/home-assistant:stable
    network_mode: host   # REQUIRED — see callout below
    volumes:
      - ha-config:/config
      - /etc/localtime:/etc/localtime:ro

networks:
  halbert-net:
    driver: bridge

volumes:
  halbert-data:
  z2m-data:
  mosquitto-data:
  ha-config:
```

`deploy/sidecar/mosquitto/mosquitto.conf` (auth is **required**, the template refuses to teach anonymous broker access):

```
listener 1883 0.0.0.0
allow_anonymous false
password_file /mosquitto/config/passwords
```

Password generation (step 2 of the R6.2 README — run before first `up`):

```bash
cd deploy/sidecar && mkdir -p mosquitto
docker run --rm -v "$PWD/mosquitto:/mosquitto/config" eclipse-mosquitto:2 \
  mosquitto_passwd -c /mosquitto/config/passwords halbert
docker run --rm -v "$PWD/mosquitto:/mosquitto/config" eclipse-mosquitto:2 \
  mosquitto_passwd /mosquitto/config/passwords zigbee2mqtt
chmod 600 mosquitto/passwords
# Put the matching server/user/password block into z2m's configuration.yaml
# (z2m-data volume) — README walks through it.
```

> **Why not host networking everywhere?** Host mode binds every published port on every LAN interface by default (this is how the old template exposed an unauthenticated Mosquitto to the whole network), gives you no container DNS (services can't resolve `mosquitto` by name), invites port collisions with anything else on the host, and is silently different under Docker Desktop. The one service that genuinely needs it is **HA Container: Zeroconf/mDNS and other multicast discovery protocols do not traverse bridge NAT**, so HA keeps host mode and everything else lives on `halbert-net` with names, not ports. The `127.0.0.1:1883` publish exists *because* HA is host-networked — it's the loopback bridge between the two worlds, and loopback is where the exposure ends.

### Task Table (7 tasks — IDs unchanged)

| Task | Description | Model / Effort | Status | Stable? |
|------|-------------|----------------|--------|---------|
| R6.1 | Sidecar docker-compose template — **9.1's revised file at `deploy/sidecar/docker-compose.yml`**: pulls the published agent image (R0.9/R0.10), bridge network, authenticated loopback-only Mosquitto, HA alone on host networking, **`halbert.sock` mount OPTIONAL — daemon-less compose runs degraded (Q3)**. First draft lands alongside R0.9 (it needs no daemon) | Sonnet high | Pending | Yes — docker-compose format is stable |
| R6.2 | Sidecar documentation — `deploy/sidecar/README.md`: prerequisites (Linux, Docker + compose plugin, free `/dev/ttyUSB*`), the mosquitto password generation step above, Z2M `configuration.yaml` broker credentials, optional `halbertd` host install + uncommenting the sock mount, upgrade (`docker compose pull && docker compose up -d`), troubleshooting matrix (9.5) | Sonnet med | Pending | Yes |
| R6.3 | HA Add-on package — **thin wrapper over the published base image** (RB): `Dockerfile` = `FROM ghcr.io/ericbintner/halbert-core:latest` + `COPY run.sh /`, plus Supervisor-format `config.yaml` and `run.sh` entrypoint. **No new packaging work; presupposes R0.10's published image. No kernel access (HAOS sandbox) — funnel per D5.** Distribution artifact is a **Supervisor add-on repository** (a GitHub repo with `repository.yaml`) — HACS lists custom integrations and frontend cards, not add-ons | Sonnet xhigh | Pending | Medium — HA Add-on format is stable but Supervisor API may evolve |
| R6.4 | HA Add-on documentation — setup guide, limitations (no eBPF/Btrfs/Landlock inside HAOS), graduation path to Path 1/2 | Sonnet med | Pending | Yes |
| R6.5 | OS-native MCP server documentation — stdio registration of `halbert-mcp-serve` per 9.3: `claude mcp add`, `~/.claude.json`, Cursor `.cursor/mcp.json`, Warp when its format stabilizes. **The socket is never part of any client config (F9/RC)** | Sonnet high | Pending | Yes |
| R6.6 | OS-native MCP auto-registration — probe which AI CLIs exist (`command -v claude` / `cursor` / `warp-cli`; config-file presence), offer to write the stdio `halbert-mcp-serve` entry into each found client's config per 9.3. Register only what's found; never fail when nothing is | Sonnet high | Pending | Medium — CLI config formats may change |
| R6.7 | Integration test — **gated on the R0 reference test environment** (Linux VM via UTM/limactl, Btrfs root, kernel ≥ 5.13, Docker + systemd; RD). Runs the 30-minute acceptance script in 9.4 on a fresh VM | Opus high | Pending | Yes |

### 9.2 HA Add-on Thin Wrapper (R6.3 — RB)

```dockerfile
# deploy/ha-addon/Dockerfile
ARG BUILD_FROM=ghcr.io/ericbintner/halbert-core:latest
FROM ${BUILD_FROM}
COPY run.sh /run.sh
ENTRYPOINT ["/run.sh"]
```

`config.yaml` declares name/slug/version/arch list and an options schema (HA URL defaulting to the Supervisor-injected `SUPERVISOR_TOKEN` flow); `run.sh` maps add-on options to the agent's env and execs the agent. The HA-funnel framing is unchanged (D5): the add-on acquires users, Paths 1–2 give them the full experience. What changes is only the framing of effort — there is no new container to build, because R0.9/R0.10 already ship it.

### 9.3 OS-MCP Registration Detail (R6.5/R6.6)

**Transport is stdio to the `halbert-mcp-serve` console script** (`halbert_core.mcp.server:main` in `halbert_core/pyproject.toml`). The Python server also offers HTTP/SSE with bearer auth (transport exists today), but auto-registration targets stdio — portable, no credentials to manage. Registration never references `/var/run/halbert.sock` (internal IPC, F9/RC).

| Client | Detection | Registration |
|---|---|---|
| Claude Code | `command -v claude` | `claude mcp add halbert -- halbert-mcp-serve` — or write `"halbert": {"command": "halbert-mcp-serve", "args": []}` under `mcpServers` in `~/.claude.json` |
| Cursor | `command -v cursor`, `~/.cursor/` present | `mcpServers` entry in `~/.cursor/mcp.json` |
| Warp | `command -v warp-cli` | Its MCP config format is not yet stable — document manual setup and revisit; do not write files we can't verify |

Auto-registration (R6.6) runs these probes, reports what it found, and asks before writing. The new `halbert.*` tools appear in the tool list regardless of daemon state; daemon-absent calls return the actionable error from 8.6 rather than disappearing — a stable tool list is easier for clients to reason about than a shape-shifting one.

### 9.4 R6.7 — The 30-Minute Acceptance Script

Gated on the R0 reference test environment (RD). Fresh VM each run. Wall-clock budget in parentheses.

```bash
# 0. Provision fresh VM per crates/README.md "Test environment"      (~5 min)
#    Linux, Btrfs root, kernel >= 5.13, Docker + systemd
# 1. Install halbertd                                                (~3 min)
sudo apt install ./halbertd_0.1.0_amd64.deb
systemctl status halbertd                       # active (running)
# 2. Install the agent side (reference for the image contents)       (~5 min)
pipx install 'halbert-core[rust]'
# 3. Deploy the sidecar                                              (~10 min, mostly image pulls)
git clone <repo> && cd deploy/sidecar
mkdir -p mosquitto                                # generate passwords per 9.1
docker compose up -d
# 4. Register MCP and exercise                                       (~5 min)
claude mcp add halbert -- halbert-mcp-serve
#   get_vitals -> JSON vitals         halbert.create_atomic_snapshot -> handle
#   halbert.rollback_snapshot -> pre-snapshot state restored
# 5. Control one Zigbee bulb                                         (~7 min)
#   Pair the bulb in Z2M (frontend on 127.0.0.1:8080), confirm it appears in
#   the Halbert dashboard device list from the MQTT source.
#   docker compose stop homeassistant   # kill Layer 1
#   Agent toggles the bulb via the MQTT bus anyway -> Layer 2 proven.
```

**Acceptance:** bulb toggles with the HA container stopped; snapshot created and rolled back; total elapsed ≤ 30 minutes. This script is also the R7 appliance's first-boot smoke test.

### 9.5 Failure Modes + Rollback (R6)

| Failure | Behavior | Repair |
|---|---|---|
| No daemon on host (sock mount commented out) | Compose runs degraded: pure-Python agent (Q3), dashboard shows no telemetry/snapshot features | Install `halbertd`, uncomment mount, `up -d` |
| Sock mount uncommented but daemon not running at container start | Docker bind-creates an empty **directory** at `/var/run/halbert.sock`; agent can't connect | Start `halbertd` first, `docker compose up -d --force-recreate halbert` |
| Mosquitto auth failures | Clients refused; Z2M logs "not authorized" | Regenerate `mosquitto/passwords` per 9.1, restart `mosquitto` |
| HA can't reach the broker | HA is host-networked; it dials `127.0.0.1:1883` | Verify the loopback publish exists (`docker compose port mosquitto 1883`) |
| Registry unreachable / image pull fails | Build locally as fallback: `docker build -t halbert/halbert-core:local .` from repo root (Dockerfile from R0.9), pin `image:` to the local tag | Retry pull; the pinned tag makes rollback a one-line edit |

### 9.6 Dogfooding Plan (R6)

- The founder's N100 mini-PC runs exactly `deploy/sidecar/` — no hand-edits; drift between docs and running system is a bug.
- Every tagged release re-runs 9.4 on a fresh VM before publish.
- The dev Mac exercises only the MCP-registration half (9.3) — registration never depends on the kernel features.

**Verification gate (exact commands):**

```bash
cd deploy/sidecar && docker compose config -q     # template parses
bash /path/to/acceptance-9.4.sh                    # full 30-minute script on a fresh reference VM
docker compose stop homeassistant && <toggle bulb via agent>   # Layer 2 acceptance
# HAOS side: install the add-on from the Supervisor add-on test repo on a HAOS VM,
# confirm the agent boots and reaches HA via the Supervisor token.
```

**Verification:** A user can follow the sidecar README and get Halbert + HA + Z2M running on one box in under 30 minutes — proven by the 9.4 script, not asserted. A HAOS user can install the Halbert Add-on from the published Supervisor add-on repository.

---

## 10. Phase R7 — Turnkey Appliance (north-star, gated)

**Goal:** A flashable HalbertOS appliance image — a pre-configured standard
distro with `halbertd` pre-installed, not a custom OS.
**Prerequisite:** R1–R6 complete and verified, plus founder approval. In
practice this means stages L0 and the L1 entry gate from §16 are satisfied:
the daemon has run crash-free for a month of real dogfooding, and external
users are on Path 2.
**Risk:** High — mkosi image building, UKI signing, dm-verity scope, and a
first-boot UX that must never strand a user with an unbootable appliance.
**Product value:** Medium near-term, high long-term — convenience for
dedicated appliance users; not required for the core value proposition
(Paths 1–3 deliver it on standard distros).
**Status:** **North-star. Do not start until R1–R6 are proven in production.**

**How R7 maps to the long-term strategy (§16):** R7 covers exactly stages
L1 and L2. R7.1–R7.3 plus R7.6 are the **L1 Appliance Beta** scope (it boots,
it configures itself, it updates, no hardening). R7.4 and R7.5 plus the
update-channel work are the **L2 Hardened Appliance** scope (signed UKI,
dm-verity `/usr`, A/B or snapshot-based rollback). Anything beyond that —
custom kernel, `halbertd` as PID 1, Wayland compositor, initramfs sentinel —
is **not R7 work at all**; it can only be reconsidered at the L3 decision
gate in §16, whose default answer is NO. Consistent with F12: signed UKI and
dm-verity are R7-phase items — deferred from R1–R6, not from the plan.

| Task | Description | Model / Effort | Status |
|------|-------------|----------------|--------|
| R7.1 | mkosi build recipe — Arch or Fedora base, `halbertd` pre-installed, Btrfs default filesystem | Opus xhigh | Gated |
| R7.2 | Pre-configure docker-compose — HA + Z2M + Mosquitto template ready on first boot | Sonnet high | Gated |
| R7.3 | First-boot setup wizard — SSH + Halbert dashboard for HA URL, MQTT broker, model config | Opus high | Gated |
| R7.4 | Signed UKI boot — unified kernel image with Halbert recovery hooks | Opus xhigh | Gated |
| R7.5 | dm-verity `/usr` partition — read-only, verified OS image layer | Opus xhigh | Gated |
| R7.6 | QEMU/KVM test image — bootable VM image for testing without hardware | Sonnet high | Gated |

**Verification (phase gate, expanded):** Build the image from a clean tree,
boot it in QEMU headlessly via the R7.6 harness, then flash it to USB and
boot a real mini-PC. On both targets: `halbertd status` (R5.9) reports
healthy on first boot, the compose stack comes up, and the dashboard is
reachable from a browser on the LAN without any manual package installs.
The first-boot wizard completes end-to-end with HA omitted (Layer 2 only)
and again with HA attached (Layer 1).

---

### 10.1 Implementation strategy

The image is **packaging, not engineering**. Everything that runs inside it
already exists by the time R7 starts: `halbertd` (R5), the agent container
image (R0.9/R0.10), the sidecar compose template (R6.1), the MQTT device bus
(R1). R7's job is to assemble those proven parts behind a bootloader and a
first-boot flow. Follow the "Home Assistant OS" precedent from the scoping
doc: HA did not write a custom kernel — they packaged Buildroot + HA +
Supervisor. We package Fedora/Arch + `halbertd` + compose.

**Base distro decision (owned by R7.1):** Fedora vs Arch. Recommendation:
**Fedora**, because its kernel, systemd, and mkosi integration give
predictable release trains and a smoother path to signed UKIs and dm-verity
in R7.4/R7.5 (the tooling — `ukify`, `systemd-repart`, `sbsign` — is
first-class there). Arch remains acceptable if the team prefers a rolling
base; the recipe is identical in structure.

### 10.2 R7.1 — mkosi recipe contents (expanded)

`deploy/appliance/mkosi.conf` (new file, created by this task) contains, at
minimum:

```ini
[Distribution]
Distribution=fedora
Release=41

[Output]
Format=disk
ImageId=halbertos
Bootable=yes

[Content]
Packages=
    systemd-udev
    NetworkManager
    openssh-server
    podman
    podman-compose
    git
    btrfs-progs
    halbertd
# halbertd comes from our own COPR/repo produced by R5.10/R5.11 packaging
BuildPackages=
    systemd-devel

```

The Btrfs subvolume layout is realized via **systemd-repart definitions**
shipped with the recipe (`RepartDirectories=` in mkosi.conf — partitions and
subvolumes are not mkosi.conf sections):

- `@` → `/` (system; snapshot before updates)
- `@home` → `/home`
- `@var` → `/var` (compose stacks, HA config, halbert data)

This is the layout `halbert-snapshots` (R3) can roll back cleanly.

Additional recipe requirements:

- A drop-in enabling `halbertd.service` (R5.2, with the F7 non-blocking
  mount condition) and `sshd.service` in the image preset.
- The compose template from R6.1 vendored into `/etc/halbert/compose/`
  (used by R7.2).
- Hostname default `halbert` and mDNS/`avahi` enabled so the appliance is
  findable as `halbert.local` on first boot.
- No desktop environment, no Wayland, no Tauri shell — the appliance is
  headless; the dashboard is served over HTTP and reached from the user's
  existing machine. (The Tauri desktop app is a Path 1 artifact.)

### 10.3 R7.2 — Pre-configured compose (expanded)

- On first boot, a one-shot systemd unit copies
  `/etc/halbert/compose/docker-compose.yml` (the R6.1 template, F6-revised:
  bridge network, authenticated Mosquitto) into `/var/lib/halbert/stack/`
  and starts it via `podman-compose` (or `docker compose` if we ship the
  Docker CLI — one runtime, decided at execution).
- The Mosquitto password file is generated at first boot with a random
  password, written into both the broker config and the Z2M/Halbert env
  files, never logged.
- USB Zigbee coordinator passthrough is pre-wired but disabled unless a
  coordinator is detected (the wizard, R7.3, flips the flag).
- Volume layout follows the Btrfs subvolumes from R7.1 so container state
  is covered by `halbert-snapshots` rollback.

### 10.4 R7.3 — First-boot wizard screens (expanded)

Delivered two ways from one implementation: an SSH-accessible flow
(`ssh halbert@halbert.local`) and the same steps in the web dashboard.
Screens, in order:

1. **Welcome + hostname** — confirm or change hostname, timezone, locale.
2. **Network check** — show LAN IP, confirm internet reachability, offer
   static-IP configuration.
3. **Assistant identity** — set the onboarding `ai_name` (the engaged
   surface is labelled with this name, never the raw hostname or a generic
   codename — standing founder directive).
4. **LLM backend connection** — endpoint and credentials for whatever
   backends the user already runs. The wizard presents connection slots
   only: **no model names are displayed, recommended, or ranked on any
   user-facing surface** (founder directive, §16.5).
5. **Zigbee coordinator** — detect `/dev/ttyUSB*` / `/dev/ttyACM*`; if a
   coordinator is found, offer to enable the Z2M service and pair the first
   device (Layer 2 path).
6. **Home Assistant (optional)** — toggle + URL + long-lived token. Default
   copy: "Works great with Home Assistant, but doesn't require it." Skipping
   this leaves the appliance fully functional via the MQTT device bus (R1).
7. **MQTT broker status** — show the generated broker credentials were
   applied, list discovered Z2M topics.
8. **Baseline snapshot** — offer "Create baseline snapshot now" (calls
   `halbert.create_atomic_snapshot` through the one MCP surface per F9/RC)
   so the very first state is rollback-able.
9. **Summary + finish** — recap choices, show the dashboard URL, done.

The wizard must be idempotent and re-runnable (`halbert-firstboot --rerun`)
so a bad choice never bricks the setup.

### 10.5 R7.4 — Signed UKI: key custody (expanded)

- Build one Unified Kernel Image per release via `ukify` (kernel + initrd +
  cmdline in a single signed PE binary), enrolled against Secure Boot.
- **Recovery hooks:** a UKI cmdline/drop-in hook that, on a failed boot
  counter (systemd boot assessment), offers to boot from the most recent
  known-good Btrfs root snapshot via `halbert-snapshots` — the appliance
  heals itself back to the last working image without a reflash.
- **Key custody:** the Secure Boot signing key is generated **offline**,
  stored on a hardware security key held by the founder, with a backup
  escrowed separately. The private key **never enters CI** for v1 — release
  signing is a manual, air-gapped ceremony (build in CI, sign offline,
  publish). The public key is enrolled in the image's MOK/secure-boot db at
  build time. Key-rotation and key-compromise procedures are written down
  before the first signed release ships; if custody can't be run this way,
  R7.4 does not ship — unsigned-UKI boot remains the L1 behavior.

### 10.6 R7.5 — dm-verity scope: `/usr` read-only only (expanded)

- **Scope is deliberately narrow:** dm-verity covers **`/usr` and only
  `/usr`** (mkosi `Verity=` on the `/usr` partition, hash tree verified at
  mount). Root, `/etc`, and `/var` stay *writable* — config, the compose
  stack, HA data, and `halbert` state all live there and must not be
  verity-locked.
- Rationale: verity on `/usr` guarantees the OS binaries we ship are the
  binaries that run (tamper-evidence for the appliance layer), while
  keeping the entire mutable surface — exactly the surface
  `halbert-snapshots` rollbacks target — outside the verity tree. Full-root
  verity is a custom-distro property and stays deferred (§11, L3 gate).
- Interaction with updates: a new release ships a new `/usr` + verity tree
  as one signed unit (L2 update story, §16.3); rollback restores the
  previous `/usr` and the matching system snapshot together.

### 10.7 R7.6 — QEMU/KVM test harness (expanded)

The appliance must be testable without hardware on the dev bench (the
primary dev machine is macOS — F11/RD's Linux VM environment applies).

- `mkosi qemu` boots the built image directly for interactive smoke tests.
- Headless harness at `scripts/appliance-tests/` (new, this task):

```bash
# Boot the qcow2 image headlessly, forwarding SSH + dashboard
qemu-system-x86_64 \
  -machine q35 -enable-kvm -m 4G -smp 4 \
  -drive if=pflash,format=raw,readonly=on,file=/usr/share/OVMF/OVMF_CODE.fd \
  -drive format=qcow2,file=halbertos.qcow2 \
  -netdev user,id=n0,hostfwd=tcp::2222-:22 \
  -device virtio-net-pci,netdev=n0

# Harness assertions (run over the forwarded ports):
ssh -p 2222 halbert@localhost 'halbertd status'                 # R5.9 CLI: daemon healthy
ssh -p 2222 halbert@localhost 'podman ps | grep -c halbert'     # compose stack up
ssh -p 2222 halbert@localhost 'halbert-firstboot --headless --accept-defaults'
# wizard completes end-to-end without a TTY; rerun proves idempotency
```

- The harness runs in CI on a Linux runner for every appliance-image build,
  plus — once R7.4 lands — a Secure-Boot-enabled variant that boots an image
  signed with a **throwaway CI-only key** (generated per-run, discarded). The
  production signing key never enters CI (§10.5): the SB harness proves the
  *harness*; release images are signed offline.
- **Failure modes + rollback:** image fails to boot → harness captures the
  serial log and fails the build; wizard fails mid-run → rerun path above;
  bad update on L2 → boot-assessment hook rolls back to the prior
  `/usr` + snapshot pair. An appliance that cannot complete first boot
  headlessly never leaves CI.

### 10.8 Execution order within R7

1. **R7.6 first** — the harness exists before the image is real, so every
   subsequent task lands on a tested base.
2. **R7.1** — recipe + image build green in the harness.
3. **R7.2**, then **R7.3** — stack automation, then wizard, each verified
   headlessly. This completes **L1 (Appliance Beta)** per §16.2 — pause
   here; the L2 entry gate applies before continuing.
4. **R7.5 then R7.4** — verity partition first (build-time concern), signed
   UKI last (key ceremony gates release). With the update channel from
   §16.3, this completes **L2 (Hardened Appliance)**.

### 10.9 Dogfooding plan

- We run the L1 image on our own bench hardware (one mini-PC per core
  contributor) for a full update cycle before any external flash.
- The M5 milestone (§16.6) is the external bet: three hardware configs
  (x86 mini-PC class N100/N150, one aarch64 ARM board with UEFI firmware,
  and the QEMU VM) booting and self-updating cleanly is the L1 exit gate.

---

## 11. Explicitly Deferred (North-Star, Not in This Plan)

These items from the experimental docs are explicitly deferred per founder
decision D7. They are tracked here for visibility but have no model/effort
assignment and no engineering time allocated. **Clarification (F12): signed
UKI boot and dm-verity are R7-phase items (R7.4/R7.5), gated with the rest
of R7 — deferred from R1–R6, not from the plan; they therefore do not
appear in this table.** The revisit triggers below are folded into the
stage gates in §16 — a row graduating means it re-enters planning at the
stage named there, not before.

| Item | Why deferred | Revisit when |
|------|-------------|--------------|
| Custom kernel with eBPF-LSM policies baked in | Multi-year effort, requires OS engineering team | `halbertd` proven in production for 12+ months |
| Wayland compositor (smithay/wlroots) | Enormous effort, Tauri webview covers UI need | Never, unless webview proves insufficient |
| `halbertd` as PID 1 | Only meaningful with custom distro | R7 appliance image proves viable |
| Custom initramfs sentinel | Only meaningful with custom distro | R7 appliance image proves viable |
| Native Matter controller (`rs-matter`) | `rs-matter` not production-ready for controllers, no 1.0 API freeze | `rs-matter` reaches 1.0 stability |
| BLE native support (`btleplug`) | Multi-device reliability is months of work | User demand justifies the investment |
| Windows platform (ETW, VSS, ConPTY, DirectML) | Second full platform engineering effort | `halbertd` proven on Linux + macOS for 12+ months |
| APFS snapshot transactions | Private SPIs, notarization risk | Apple publishes a stable public API |
| Z-Wave JS native client | Trivial but not on critical path | R1 MQTT bus proves the native device pattern |

---

## 12. Sync Points with MASTER-TODO

This plan intersects with existing MASTER-TODO items:

| MASTER-TODO item | This plan | Relationship |
|------------------|-----------|--------------|
| U2 — Voice / Auditory Cortex (Rust AEC) | R0–R4 infrastructure | AEC work in `src-tauri/audio_capture.rs` is separate from the crates/ workspace but benefits from the PyO3 bridge pattern established by R4a |
| U6 — Home Automation Simplification (S1–S7) | R1 (MQTT device bus) | R1 makes HA architecturally optional, which is the end state U6 is working toward. U6 removes HA dependencies from the home variant; R1 provides the alternative device bus. Unchanged by the 2026-08-31 review. Lands before federated Phase 9 regardless of Rust progress |
| U6 — Compute Peer / model config contract | R0.9 agent image | The image stays **dumb** — receives model/peer-compute configuration via env, never bakes Ollama/vLLM expectations in. Review recommendation adopted in-plan (its §6 question 5); external confirmation optional, not a gate |
| Response Modality & Voice Path items | None | These are Python/React work, not Rust. No overlap. |
| `HALBERT_MODEL` env var wiring (TASK-01, U4) | None | Python-only, no Rust involvement. |

### Recommended execution order

1. **Finish in-flight U-batches (U1–U6).** Pure Python/React work; no Rust
   dependency either direction. U6's relation to R1 is complementary, not
   blocking.
2. **Start R0 now — both tracks in parallel.** R0.1–R0.8 scaffolding
   (Cargo workspace, crate stubs, CI incl. census-gate extension,
   `crates/README.md` contracts + test-environment spec) *and* the Docker
   track (R0.9 Dockerfile, R0.10 CI build/publish). Everything in R0 is
   buildable on the dev Mac — nothing in R0 needs the Linux VM.
3. **Start R1 + wave R4a immediately after R0** — highest product value
   (Layer 2, "HA optional") and, post-F1, the first leg that is verifiable
   end-to-end on its own timeline.
4. **Start R2 + R4b and R3 + R4c in parallel on the Linux+Btrfs reference
   VM** as soon as R0 lands and staffing allows. R2 is the longer leg
   (~3 weeks) and therefore the critical-path leg; R3 (~2 weeks) fills spare
   capacity. Neither blocks R1.
5. **Start R5 (halbertd) when R4a + R4b + R4c have all landed.** Gate is the
   three-module import test below.
6. **R6 after R5.** The compose template travels with R0.9 as a draft and
   finalizes here against the published registry tag; the HA Add-on
   `Dockerfile` becomes a thin wrapper over that image (F2/RB), not new
   packaging work.
7. **R7 stays gated.** No mkosi/UKI/dm-verity work until R1–R6 are proven in
   production and the founder approves.

### Cross-leg verification gates (exact)

Between legs, the plan advances only when the gate command passes. These are
gates for future work — the commands will exist once their phase lands:

| Gate | Command | Passes when |
|------|---------|-------------|
| R0 exit | `cargo build --workspace && cargo clippy --workspace --all-targets -- -D warnings && cargo fmt --all -- --check && cargo test --workspace` | Workspace compiles, clippy clean, fmt clean, stub tests pass |
| R0 exit (Docker) | `docker build -t halbert/halbert-core:dev .` + R0.10 CI job green on a PR | Image builds; CI job builds + smoke-tests it; tagged release publishes |
| R4a → R1 verification | `maturin build --release -m crates/halbert-ffi/Cargo.toml` then `python -c "import halbert_rs.mqtt"` | Wheel builds and the mqtt module imports |
| R1 exit (end-to-end) | R1 verification: Z2M + Mosquitto running, HA container **stopped**; Halbert discovers and controls one real Zigbee device | R1's "HA optional" criterion demonstrably met |
| R4b / R2 exit (VM) | On the Linux+Btrfs VM: run the R2.9 integration test; consumer receives real `execve` events; clean attach/detach, no kernel panic | eBPF probes stream events on kernel ≥ 5.13 (the standardized floor) |
| R4c / R3 exit (VM) | On the same VM: create snapshot → modify file → rollback → verify restored; enter Landlock sandbox → write outside allowed paths → kernel blocks | R3 criterion met |
| R5 entry gate | `python -c "import halbert_rs.mqtt, halbert_rs.telemetry, halbert_rs.snapshots, halbert_rs.sandbox"` | All three waves importable — R5 never does first-contact FFI |
| R5 exit | `sudo systemctl start halbertd && halbertd status`; MCP client calls `halbert.create_atomic_snapshot` via `halbert-mcp-serve` and receives a handle | Daemon live, proxies wired |
| R6 exit | Fresh Linux box: sidecar README followed → Halbert + HA + Z2M healthy in < 30 min; HAOS Add-on installs from the published Supervisor add-on repository | Both paths reproducible |
| Continuous | Repo pytest suite stays green, including the no-`halbert_rs` fallback test (RE) and the R0.10 census-gate extension | Graceful degradation tested, not asserted |

### Dogfooding plan

- **Week 1 (R0.10):** the agent image is built and smoke-tested on every PR.
  The container is dogfooded from the first green PR, not from R6. Rollback
  target is always the previous registry tag.
- **R1+R4a leg:** the dev Mac runs `halbert_rs` via `maturin develop` daily;
  Mosquitto + Z2M run in a local docker-compose stack (drafted with R0.9) for
  every R1.x verification.
- **R2+R4b / R3+R4c legs:** the Linux+Btrfs VM is a daily driver for the
  agent that owns those legs, not a one-shot CI fixture — per RD, it is
  specified in `crates/README.md` before R2.9/R3.8 are even scheduled.
- **Post-R4c:** every risky agent execution on the VM runs wrapped in
  snapshot+rollback (R3 verification becomes daily workflow).
- **Post-R5:** `halbertd` runs as a systemd service on the VM continuously;
  the founder's Mac dashboard connects through the unchanged Python MCP
  surface.

### Failure modes + rollback (plan level)

| Failure mode | Containment / rollback |
|---|---|
| eBPF probe instability on a particular kernel (R2) | `halbert_rs` is a lazy optional extra; the Python fallback path means the app boots and functions with zero Rust present. Rollback = uninstall the extra |
| Wheel build failure on macOS (any wave) | Per RE the macOS stub path is exercised in CI; the stub keeps imports working and returns unsupported/empty — never a boot blocker |
| Published image regression (R0.10+) | Immutable semver tags; `:latest` moves only after smoke tests. Rollback = pin compose to the previous tag |
| Privilege-collapse proposal (Q7) rejected by reviewer | R5.1 retains the sketched two-tier privilege model; no design is destroyed by keeping it |
| Non-Btrfs host (R3/R5) | Already stubbed by R3.7; F7's edit removes the hard `Requires=` so `halbertd` still starts — snapshot features degrade, daemon lives |
| Two-MQTT-stack drift (F8) | Frigate stays on `aiomqtt` through R1–R6 by explicit decision; device bus owns `rumqttc`. Migration is optional follow-up, never silently assumed |

---

## 13. What Qualifies for Rust vs. Stays in Python (Reference)

### In Rust (stable interfaces, won't churn)

| Component | Interface | Stability proof |
|-----------|-----------|-----------------|
| MQTT transport | MQTT 3.1.1/5.0 (OASIS standard) | 25+ years, frozen spec |
| eBPF probes | Kernel tracepoints (`sys_enter_execve`, etc.) | Stable kernel ABI |
| Btrfs snapshots | Btrfs ioctls (`BTRFS_IOC_SNAP_*`) | Stable since 2009 |
| Landlock sandbox | Landlock syscalls | Stable since kernel 5.13 (2021) |
| cgroups v2 | cgroups v2 filesystem interface | Stable since kernel 4.15 |
| PyO3 bridge | PyO3/Maturin ABI | Stable, well-maintained |
| Unix socket IPC | JSON-RPC 2.0 over Unix domain socket | Both are stable specs |
| PTY plumbing | POSIX `forkpty`/`openpty` | Stable since 1980s |

### In Python (application logic, may churn)

| Component | Why it stays in Python |
|-----------|----------------------|
| Agent state machine / CRAG | High-velocity, LangGraph-style logic, idiomatic Python |
| Prompt assembly | Still evolving (modality/voice work, XML prompt system) |
| RAG / vector search | Mid-migration (ChromaDB retirement), retrieval backend changing |
| Discovery scanners (24 files) | I/O-bound, not CPU-bound. Rust won't help. Schema still evolving. |
| Device registry / entity mapping | Application logic on top of stable transport. Schema may evolve. |
| Event mappers (HA, MQTT) | Application logic, follows existing patterns but may change |
| Dashboard frontend | React/TypeScript, already fast, Tauri shell is already Rust |
| Tool definitions | Agent tool interface, high-velocity |
| Safety policy generation | Deciding which paths to snapshot/allow is application logic |

### The boundary rule

> If the interface is defined by a **kernel ABI, a published standard, or a
> stable protocol spec**, it goes in Rust.
> If the interface is defined by **our application's evolving logic**, it
> stays in Python.
> The Rust crate exposes a stable trait; Python implements the policy on top.

---

## 14. Effort Summary

| Phase | Tasks | Estimated effort | Model mix |
|-------|-------|-----------------|-----------|
| R0 — Foundation + Docker track | 10 | ~3 days (added R0.9/R0.10 Docker work) | Sonnet med/high |
| R1 + wave R4a — MQTT Device Bus + `halbert_rs.mqtt` | 9 (+ wave share) | ~2.5 weeks | Sonnet xhigh + GLM-5.3 high |
| R2 + wave R4b — Kernel Telemetry + `halbert_rs.telemetry` | 10 (+ wave share) | ~3 weeks | Opus xhigh + Fable review |
| R3 + wave R4c — Atomic Safety + `halbert_rs.snapshots/.sandbox` | 9 (+ wave share) | ~2 weeks | Opus xhigh + Fable review |
| R4 — PyO3 Bridge (waves only, distributed) | 7 | absorbed into the three legs above | Sonnet xhigh |
| R5 — halbertd Daemon | 14 | ~3 weeks | Opus xhigh + Fable review |
| R6 — Deployment Paths | 7 | ~1 week | Sonnet high |
| **R1–R6 total** | **56** | **see critical path below** | |
| R7 — Appliance (gated) | 6 | ~4 weeks | Opus xhigh |

**Wave accounting for R4's 7 tasks** (no task executes twice; R4.6/R4.7 run
per wave as machinery): R4a = R4.1 (pyo3/maturin setup) + R4.2 (mqtt module) +
per-wave R4.6/R4.7; R4b = R4.3 (telemetry module) + per-wave R4.6/R4.7;
R4c = R4.4–R4.5 (snapshots + sandbox modules) + per-wave R4.6/R4.7. The old
"~1 week, after everything" estimate disappears into the legs.

**Critical path (post-F1/RA):** `max(R1+R4a ≈ 2.5 wk, R2+R4b ≈ 3 wk,
R3+R4c ≈ 2 wk) + R5 ≈ 3 wk + R6 ≈ 1 wk` ⇒ **roughly 7 weeks fully parallel,
vs ~12 weeks sequential** (one agent, legs run strictly in order: R0 3 d +
R1+R4a 2.5 + R2+R4b 3 + R3+R4c 2 + R5 3 + R6 1 ≈ 11.7 wk). The deterministic
bottleneck is the R2 leg (eBPF) — it owns the VM.

**What changed from the pre-review estimate** (F1): R4 no longer serializes
behind R1+R2+R3, so wall-clock to "HA optional" (R1 verified end-to-end)
drops from ~7–8 weeks to ~2.5 weeks after R0. R0 grew by one day for the
Docker track (RB) — bought back many times over by R6.3 becoming a wrapper
and by week-1 container dogfooding.

**Staffing scenarios:**

| Scenario | Wall-clock to R6-verified | Constraint |
|---|---|---|
| Single agent, strictly sequential | ~12 weeks | Simple; correct when only one keyboard exists |
| Two agents (Mac: R0→R1+R4a→R5 wiring; VM: R2+R4b then R3+R4c) | ~7–8 weeks | Requires the RD-specified Linux+Btrfs VM before R2.9/R3.8 |
| Three agents (R1, R2, R3 legs in parallel after R0) | ~7 weeks | Critical path pinned by the R2 leg |

---

## 15. Open Questions

### Q1: `aya` vs `libbpf-rs` for eBPF? — **OPEN, pending reviewer**

`aya` is pure Rust (no C dependencies), aligns with the Universal Rust Core
vision, and is actively maintained. `libbpf-rs` is more mature and has more
examples but requires the libbpf C library. **Recommendation stands: `aya`**
for architectural consistency, but this remains an Opus-level design decision
(R2.1) and the reviewer's question is noted: `aya`'s kprobe support for
`tcp_v4_connect` (R2.4) takes more ceremony than its tracepoint support.
Independently of the framework verdict, the **tracepoint-first probe-selection
policy is adopted in-plan** (§5 header and R2.4): tracepoints where the kernel
exposes them (stable ABI), kprobes only where it doesn't. **Status: framework
choice pending external confirm; probe policy decided.**

### Q2: Should `halbertd` be a single binary or multiple? — **ANSWERED: single binary**

**Recommendation adopted: single binary with subcommands** (`halbertd
telemetry`, `halbertd snapshot`, `halbertd mcp`) — simpler packaging, shared
state, one systemd unit. Note the interaction with F9's one-MCP-surface
amendment: since external MCP clients never touch `halbertd` directly (the
Python `halbert-mcp-serve` proxies over the socket), the "unprivileged for
MCP" half of R5.1's privilege model is likely **moot** — see Q7, pending
reviewer confirm.

### Q3: When does the Python agent start consuming Rust crates? — **REWRITTEN: per wave**

**Per FFI wave, not "after R4."** The first consumption point is **R4a**
(`halbert_rs.mqtt`), the same leg in which the crate lands — this is the
F1/RA amendment that decouples R1's verification from R2/R3:

- **Packaging:** `halbert_rs` ships as a lazy optional **pip extra**
  (`halbert-core[rust]`), consistent with the Haloysius subtractive contract
  (only `pyyaml` + `requests` hard; everything else optional). Each wave
  extends the wheel; the extra name stays stable.
- **Graceful degradation:** the agent without `halbert_rs` falls back to
  pure-Python scanners — no eBPF, no snapshots, no sandboxed execution, no
  MQTT device bus. Degradation is a designed branch per crate module, not an
  `ImportError` crash.
- **Tested, not asserted (RE):** one pytest exercises the absent path
  (`halbert_core/tests/test_halbert_rs_optional.py` — test body specified in
  §7.3) — import fails,
  agent must remain fully bootable and the suite must stay green. The macOS
  stub modules (R2.7/R3.7) get CI exercise the same way.

### Q4: How does `halbertd` interact with the existing Tauri desktop app?

The Tauri app (which is already Rust) can link the crates directly (Cargo
dependency). The Python agent uses PyO3 via the waves. `halbertd` uses the
crates as a standalone binary. All three consume the same `crates/halbert-*`
code. Post-F9, the Tauri app's OS-feature calls also route through the single
Python MCP surface where they cross the egress boundary.

### Q5: Separate repo for `crates/` or monorepo? — **ANSWERED: monorepo**

The crates are tightly coupled to Halbert's trait contracts; a separate repo
would create version-sync overhead. `crates/` at repo root, alongside
`halbert_core/`, matches the experimental docs' proposed layout. Corollary
from F10: `rust-toolchain.toml` lands at R0.1 so CI, dev machines, and the
future appliance build agree on one toolchain inside that same monorepo.

### Q6: Snapshot auto-prune policy — who decides when a snapshot is "safe" to delete? — **NEW, DEFERRED**

**Deferred; R1–R6 never auto-prunes.** Snapshots are retained until explicit
user action (`halbertd snapshot list` / `rollback <id>` + a manual prune
command) — an agent that silently destroys its own checkpoints is worse than
disk pressure. "Safe to prune" requires judgment the plan deliberately does
not automate yet (did the change survive? Was rollback exercised?). Revisit
with R7 appliance UX, where unattended operation forces a documented
retention policy (capacity-based, e.g. keep-N + keep-days, with a prominent
never-auto-prune opt-out for pre-mutation snapshots). Candidate criteria for
that revisit: keep-N + keep-days caps, a disk-pressure threshold with
mandatory operator notification before any destroy, and a permanent exemption
for `manual`-labeled snapshots.

### Q7: Can `halbertd`'s privilege model collapse given the one-MCP-surface amendment? — **NEW, PROPOSAL PENDING REVIEWER**

**Proposal:** since F9/RC makes `/var/run/halbert.sock` (0660, group
`halbert`) internal IPC served only to the trusted local Python MCP server,
`halbertd`'s sketched second tier ("unprivileged for MCP") serves no external
client and may be unnecessary — the daemon could run as a single root-owned
process behind the permission-gated socket, privileges bounded by
`CapabilityBoundingSet=CAP_BPF CAP_SYS_ADMIN CAP_DAC_READ_SEARCH` (the §8.3
Variant-A mechanism; `AmbientCapabilities` only constrains non-root services),
which simplifies R5.1 substantially. This is phrased as a question (the reviewer's
§6 question 4) because it is a privilege-boundary decision: **R5.1 keeps
both halves until reviewer confirm.** If confirmed, R5.1 simplifies; if
rejected, the two-tier model ships as designed — no rework in either case.

---

## 16. Long-Term Strategy Beyond R7

This section is the **"distro, but not yet"** doctrine made operational. R7
is not the end of the road and it is not the start of a custom operating
system — it is the middle of a funnel. The stages below (L0–L3) define
where we are, what unlocks what, and — critically — the **measurable entry
criteria** for each stage. No stage advances on vibes. Every date in this
section is planning-level only; the gates, not the calendar, drive
progression.

```
L0  Native core proof (now) ──────────►  R1–R6 shipped, dogfooded
         │                                    entry: R0 starts
         ▼
L1  Appliance beta ───────────────────►  R7.1–R7.3 + R7.6 (no UKI/verity)
         │                                    entry: all R1–R6 verified
         ▼                                    + 2 external Path-2 users
L2  Hardened appliance ───────────────►  R7.4/R7.5 + update channel
         │                                    entry: L1 exit + update-channel
         ▼                                    security review
L3  Distro decision gate ─────────────►  THE ONLY gate where custom kernel /
                                            PID 1 / Wayland can be reconsidered
                                            default answer: NO
```

### 16.1 L0 — Native core proof (now)

**Scope:** R0–R6 as planned, plus **three months of dogfooding** the sidecar
image (R0.9/R0.10 + R6.1) and the `halbertd` packages on our own machines
before any external adoption claim is made.

**Entry:** already running — R0 is unblocked today.

**Exit criteria (all required, all measurable):**

1. R1–R6 shipped and passing their per-phase verification gates (§4–§9).
2. One **crash-free month** of `halbertd` in real daily use on our own
   machines: no daemon crashes, no eBPF load/unload panics, no silent
   snapshot failures in `halbertd` logs across 30 consecutive days.
3. One **external user** running Path 2 (sidecar compose on standard Linux)
   from the R6.2 README without hand-holding.

### 16.2 L1 — Appliance beta

**Scope:** R7.1, R7.2, R7.3, and **R7.6 only** — the appliance boots,
configures itself, and updates. **No signed UKI, no dm-verity yet** (those
are L2). Updates at L1 are deliberately simple: pull a new image and
re-image, or `halbert-snapshots`-protected in-place upgrade — the hardened
channel is not a precondition for beta.

**Entry criteria:**

1. All R1–R6 phases verified (their phase gates, not just "task marked
   done").
2. **Two external Path-2 users** active (self-installed, self-updated, and
   reporting back).

**Exit criteria:**

1. The appliance image **boots and self-updates on three hardware
   configs**: one x86 mini-PC (N100/N150 class), one aarch64 ARM board with
   UEFI firmware, and the QEMU/KVM VM from the R7.6 harness.
2. The first-boot wizard (R7.3) completes headlessly on all three via the
   harness assertions in §10.7.

### 16.3 L2 — Hardened appliance

**Scope:** R7.4 (signed UKI) and R7.5 (dm-verity `/usr`), plus the **full
auto-update story**:

- **A/B partitions** *or* **Btrfs-snapshotted upgrades** — one mechanism,
  chosen at execution; the recommendation is Btrfs-snapshotted upgrades
  because the plumbing already exists (R3) and the L1 update path already
  exercises it. A/B is the fallback if snapshot-based upgrade recovery
  proves fragile in dogfooding.
- **Rollback wired to `halbert-snapshots`:** a failed update (boot
  assessment failure, health-check failure after first boot) automatically
  restores the previous `/usr` + system snapshot pair — the recovery hooks
  from §10.5.
- The update channel is signed end-to-end: image signed offline (key
  custody per §10.5), verified by the appliance before application.

**Tasking note:** the update channel is L2 scope *beyond* R7.1–R7.6 — its task
IDs are created at L2 entry (this plan deliberately does not pre-author it).

**Entry criteria:**

1. L1 exit met (three-config boot + self-update).
2. A **security review of the update channel** (Fable second opinion, same
   posture as R2.10/R3.9/R5.14): signature verification path, rollback
   abuse cases, key custody procedure — all pass before the first signed
   release.

### 16.4 L3 — Distro decision gate

**This is the only gate where custom kernel / PID 1 / Wayland can be
reconsidered.** Not a commitment — a gate.

**Entry criteria (both required):**

1. `halbertd` in production **across both service paths** (Path 2 sidecar
   and Path 4 appliance) for **12+ months**.
2. **Demonstrated user pull** for custom-OS features — real requests,
   measured, not projected enthusiasm.

**Default answer stays NO.** Passing the entry criteria earns the question
a serious, founder-decided evaluation — nothing more. The §11 rows (custom
kernel, Wayland compositor, PID 1, initramfs sentinel) remain deferred
unless L3 both opens *and* produces a YES, and the D7 de-commitments stand
until a founder decision explicitly reverses them.

### 16.4a Revisit triggers

The §11 deferred rows are not frozen forever; each has a named trigger that
moves it back into planning (at the stage noted — none before L1):

| Deferred item | Trigger that revives it | Re-enters at |
|---|---|---|
| Native Matter controller (`rs-matter`) | `rs-matter` reaches 1.0 API stability | L1 planning review |
| BLE native (`btleplug`) | Measured user demand justifies multi-device reliability work | L1 planning review |
| Windows platform (ETW/VSS/ConPTY/DirectML) | `halbertd` proven on Linux + macOS for 12+ months (dual-platform) | L2 planning review |
| APFS snapshot transactions | Apple publishes a stable public API | Any stage — research task only |
| Custom kernel / PID 1 / Wayland / initramfs sentinel | L3 gate opens *and* returns YES | L3 only |
| Z-Wave JS native client | R1 MQTT bus proves the native device pattern (scoping doc medium-term; trivial, ~3 days) | L0 — may slot into any R-phase gap |

### 16.5 Ecosystem & distribution funnel

Adoption flows downhill through existing communities — we attach to them,
we do not compete with them:

```
r/homeassistant (500k+ subscribers, per scoping doc §2)
   │  HACS listing, community posts
   ▼
Path 3: HA Add-on (funnel, not destination)
   │  "graduate for the full experience"
   ▼
Path 1 (distributed) / Path 2 (sidecar)  ──►  Path 4: HalbertOS appliance

Developer CLIs (Claude Code, Cursor, Warp)
   │  MCP auto-registration (R6.5/R6.6) — the developer-audience wedge
   ▼
the `halbert-mcp-serve` MCP surface (`halbert.*` tools + `os://` resources proxying `halbertd` over the internal socket — one egress boundary, F9/RC)
```

**Engagement norms with upstreams (HA, Z2M, Mosquitto, kernel tooling):**

- **Contribute fixes upstream, never fork.** A Halbert fork of HA or Z2M
  is a permanent maintenance tax and a community-relationship own goal. If
  we hit an upstream bug, we patch it upstream and pin a version meanwhile.
- HACS add-on and community presence follow HA community norms — Halbert is
  presented as "works great with Home Assistant" (D6), never as a
  replacement pitch inside HA channels.
- MCP registration (R6.5/R6.6) is **the developer-audience wedge**: the
  cheapest-to-try surface, existing infrastructure, and the natural entry
  point for the sysadmin/developer persona before they ever touch smart
  home features.

### 16.5a What we will NOT do at any stage

Regardless of stage, gate, or user pull, these hold (D1–D8 and standing
founder directives are not up for renegotiation here):

1. **Never name or recommend AI models on any user-facing surface** —
   dashboards, wizard, marketing, docs aimed at users. Connection slots,
   not model menus (founder directive).
2. **Never fork HA or Z2M.** Fixes go upstream; see §16.5.
3. **Never ship a kernel patchset.** If a capability needs code in the
   kernel tree, that capability waits for mainline. (eBPF probes we *load*
   are fine — they are programs, not patches.)
4. **Never collect telemetry by default.** All reporting off-by-default,
   explicit opt-in only, and the eBPF *kernel* telemetry (R2) is a local
   feature for the user's own machine — it is not a phone-home channel.

### 16.6 Dogfooding milestone ladder

Internal proof steps that pace the L-stages. **All dates are planning-level
only** — the ladder orders the work; it does not schedule it.

| Milestone | Scope | Rough quarter (planning-level) | Exit signal |
|---|---|---|---|
| **M0** | R0 (crates scaffolding) + agent Docker image (R0.9/R0.10) | now — 2026 Q3 | `cargo build --workspace` green; image builds in CI and the agent starts in a container on our own machines |
| **M1** | R1 + R4a (incremental FFI per RA) — "HA optional" for Zigbee | 2026 Q4 | Halbert controls a real Zigbee device via Z2M + Mosquitto with HA shut down, on a contributor's home network |
| **M2** | R2 / R3 on the Linux VM lab (F11/RD environment) | 2026 Q4 – 2027 Q1 | eBPF event stream + Btrfs snapshot/rollback + Landlock block verified in integration tests (R2.9, R3.8) |
| **M3** | R5 `halbertd` packaged: apt + pacman + brew | 2027 Q1 | `apt install halbertd` / `brew install halbertd` installs and starts on a fresh machine; the 30-day crash-free clock (L0 exit) starts here |
| **M4** | R6 — all three paths live: Path 2 sidecar, Path 3 add-on, OS MCP | 2027 Q1 – Q2 | Under-30-minute sidecar setup from README (R6.7 verification); add-on installable; `claude mcp add halbert` works |
| **M5** | R7 appliance beta = L1 scope | 2027 Q2+ | Image boots + self-updates on the three L1 hardware configs; external beta users flashing without help |

M0–M4 **are** the L0 dogfooding content; M5 **is** L1. L2 and L3 have no
milestones on this ladder because their entry gates cannot be scheduled —
they open when §16.3/§16.4 criteria are met, whenever that is.
