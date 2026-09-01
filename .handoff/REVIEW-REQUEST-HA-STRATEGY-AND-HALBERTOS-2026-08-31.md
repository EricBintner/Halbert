# Home Assistant Strategy & HalbertOS Foundation — Review Request

**Date:** 2026-08-31
**From:** Experimental documentation sanity-pass session
**To:** Review AI (Fable Level Review)
**Status:** Awaiting strategic and architectural review

---

## Context

The `documentation/experimental/` folder contains five forward-looking
documents proposing HalbertOS (an AI-native Linux distribution), a Universal
Rust crate core, cross-platform migration (macOS/Windows/Linux), competitive
analysis, and an OS-native MCP server. A sanity pass was performed on all
five documents; the full sanity-pass findings are in the session transcript
and summarized in Section 9 below.

During the sanity pass, the founder raised a specific strategic concern about
**the relationship between HalbertOS and Home Assistant**: the experimental
docs propose HalbertOS hosting HA "inside an isolated container" (Tier B in
`SINGULAR-ENTITY-HOME-ASSISTANT-AND-HALBERTOS-ECOSYSTEM.md`), and the founder
identified this as a potential "house of cards" scenario. The founder also
stated: "I am not sold on Home Assistant, it just has a lot of users."

This handoff documents:
1. A factual finding that changes the strategic landscape (HA Supervised is dead)
2. An analysis of why hosting HA is the house of cards
3. Four strategic options with trade-offs
4. A recommended three-layer strategy
5. Specific corrections needed to the experimental docs
6. Open questions for the reviewer

**This is a strategic and architectural review, not an implementation handoff.**
No code has been written for any of the options below. We want architectural
feedback and strategic scrutiny before any direction is committed to.

---

## 1. The Factual Finding: HA Supervised Is Dead

**This is the single most important finding in this review.**

The experimental docs (all dated 2026-08-31) propose HalbertOS hosting Home
Assistant via the Supervised installation method. As of August 2026, that
installation method no longer exists as a supported product.

### Timeline

| Date | Event |
|------|-------|
| 2025-02-11 | Nabu Casa opens Discussion #1198 proposing to drop Supervised (3.3% of active installs) |
| 2025-05-22 | Official deprecation announcement (blog post) |
| 2025-06 | HA 2025.6 shows deprecation warning to all Supervised installs |
| 2025-12 | HA 2025.12 — Supervised becomes formally unsupported; ADR-0014 reverted |
| 2026-08 (today) | Only two supported methods remain: HAOS and HA Container |

### What's left

| Method | What it is | Add-ons | Supervisor | Status |
|--------|-----------|---------|------------|--------|
| **HAOS** | Nabu Casa's appliance OS (the only full-experience option) | Yes | Yes | Supported, recommended |
| **HA Container** | Docker image of HA Core only | **No** | **No** | Supported, but no add-on store |
| ~~HA Supervised~~ | HA + Supervisor on your own Debian | Yes | Yes | **DEAD** (unsupported since 2025.12) |
| ~~HA Core~~ | Python venv install | No | No | **DEAD** |

### Sources

- Official deprecation blog: `https://www.home-assistant.io/blog/2025/05/22/deprecating-core-and-supervised-installation-methods-and-32-bit-systems/`
- ADR-0014 (reverted): `https://github.com/home-assistant/architecture/blob/master/adr/0014-home-assistant-supervised.md`
- Drop discussion: `https://github.com/home-assistant/architecture/discussions/1198`
- Supervised installer repo (now shows WARNING banner): `https://github.com/home-assistant/supervised-installer`

### Impact on the experimental docs

The Tier B proposal in
`SINGULAR-ENTITY-HOME-ASSISTANT-AND-HALBERTOS-ECOSYSTEM.md` §2 describes
HalbertOS hosting "Home Assistant Supervised (Docker)" — an installation
method that was killed 8 months before the doc was written. The proposal is
factually broken and must be corrected regardless of the strategic decision.

The remaining options for "HA on HalbertOS" are:
- **HA Container** — works, but loses the add-on store (no Zigbee2MQTT,
  Mosquitto, Node-RED, etc. via HA's add-on system). User must run those as
  separate containers.
- **HAOS in a VM** — works, but is circular: why run HAOS in a VM on
  HalbertOS when you could just run HAOS on bare metal?

---

## 2. Why Hosting HA Is the House of Cards

The founder's instinct is correct. Here is the precise mechanism.

### The dependency stack

```
HalbertOS kernel (eBPF, Btrfs, Landlock)        ← You own this
  └── halbertd init system                       ← You own this
       └── Docker                                ← Docker Inc. / moby
            └── HA Supervisor (DEAD)             ← Nabu Casa (killed it)
                 └── HA Core                     ← Nabu Casa
                      └── Zigbee2MQTT add-on     ← Z2M community
                           └── USB coordinator   ← Hardware vendor
                                └── devices      ← Physical
```

### Why it's fragile

Every layer is owned by a different party with different release cadences and
different incentives. If any layer changes its assumptions, the stack breaks.

The layer Halbert doesn't control (HA) has **already** proven it will make
breaking changes — they deprecated the exact installation method the doc
proposes. Building an OS whose thesis is "the best host for HA" makes the
OS's reason-for-existing dependent on a third party's container orchestration
decisions.

### The specific failure modes

1. **API churn:** HA's WebSocket and REST APIs change between major releases.
   If HalbertOS is tightly coupled to HA's internal state, every HA update
   is a potential breaking change to the OS.

2. **Installation method instability:** Nabu Casa killed Supervised. They
   could narrow HA Container next (e.g., requiring their own container
   runtime, or dropping Docker support). If HalbertOS is built around hosting
   HA Container, that's a repeat of the Supervised risk.

3. **Add-on ecosystem loss:** HA Container has no add-ons. The "superpowers"
   the doc claims (Btrfs rollbacks for HA updates, eBPF IoT isolation) are
   OS features, not HA-hosting features. They work for any service. Framing
   them as HA-specific benefits conflates OS value with application hosting
   value.

4. **Competitive misalignment:** "We're a better HAOS than HAOS" puts
   HalbertOS in direct competition with Nabu Casa on their own turf, with
   fewer resources and a dependency on their platform. That's a losing
   position.

---

## 3. Reframing: What Does Halbert Actually Need from HA?

Home Assistant provides three things:

| # | Capability | Does Halbert already have it? |
|---|-----------|-------------------------------|
| 1 | **Device bus** — talks to Zigbee/Matter/Z-Wave devices, exposes state | No (currently delegates to HA) |
| 2 | **Integration library** — thousands of integrations for obscure devices/services | No (currently delegates to HA) |
| 3 | **Automation engine + UI** — YAML automations, dashboards | **Yes** — cognitive loop, proactive gate, event mapper, own dashboard |

Halbert already has #3. The cognitive loop (advance_turn, event queues,
template thoughts), the proactive gate, the HA event mapper, and the full
dashboard make HA's automation engine redundant. A sentient agent doesn't
need YAML automations.

So the only things Halbert actually needs from HA are #1 (device bus) and the
long tail of #2. That reframes the problem:

> **HA is not a foundation. It is a convenience adapter for device access.
> And device access is increasingly a commodity.**

---

## 4. The Device Layer Is Not HA

The actual device protocols are open standards, not HA-proprietary:

| Protocol | What it is | How Halbert can speak to it natively |
|----------|-----------|--------------------------------------|
| **Zigbee2MQTT** | Exposes all Zigbee devices over MQTT | Halbert already has an MQTT subscriber (for Frigate). Speaking to Z2M directly is just MQTT topics. |
| **Matter** | Cross-platform standard (Apple/Google/Amazon) | `matter-rs` is a Rust Matter controller. Halbert could be a Matter controller natively — fits the Universal Rust Core plan. |
| **MQTT** | Universal smart home bus | Mosquitto + MQTT subscriber. Already partially built. |
| **Z-Wave JS** | Exposes Z-Wave over JSON API | HTTP/WebSocket client. Trivial. |
| **Bluetooth LE** | Direct device access | `btleplug` Rust crate. |
| **Thread** | Mesh networking (Matter's transport) | `openthread` Rust bindings. |

If Halbert speaks MQTT + Matter natively, then HA becomes **one optional
front-end**, not a requirement:

```
Physical devices
  ├── Zigbee2MQTT ──→ MQTT broker ──→ Halbert (native subscriber)
  ├── Matter controller (matter-rs) ──→ Halbert (native)
  ├── Z-Wave JS ──→ Halbert (HTTP/WS)
  ├── BLE (btleplug) ──→ Halbert (native)
  └── HA (optional) ──→ HA WebSocket API ──→ Halbert (existing integration)
```

The long tail of HA integrations (weather APIs, obscure IoT brands, cloud
services) is breadth, not depth. Most homes use 5-15 device types, all of
which are Zigbee/Matter/MQTT. HA's integration count (2000+) is a marketing
number, not a reflection of what real homes need.

---

## 5. Four Strategic Options

### Option A: Build HalbertOS around hosting HA (the doc's Tier B)

**What:** HalbertOS is the OS, HA runs inside it as the smart home engine.

**Verdict: Do not pursue.** This is the house of cards. HA Supervised is
dead, HA Container loses add-ons, and HAOS-in-a-VM is circular. The OS
thesis becomes dependent on a third party that has already demonstrated
willingness to break installation methods.

### Option B: HA as a peer (current approach — Tier A)

**What:** HA runs wherever the user already has it (HAOS on a Pi, Container
on a NAS). Halbert connects via WebSocket API. Halbert is the brain; HA is
a device bus.

**Pros:**
- Zero coupling. HA can be replaced or removed.
- No OS dependency on HA.
- 90% of smart home enthusiasts already have HA running somewhere.
- Already built and working in the current codebase.

**Cons:**
- Still need HA to exist somewhere for device access (until Option C).
- Dependent on HA's API stability (though far less so than hosting).

**Verdict: Keep as the primary integration path.** It's already built and
it's the right architecture for the current stage.

### Option C: Halbert speaks to devices directly — HA becomes optional

**What:** Build native MQTT + Zigbee2MQTT + Matter support into Halbert.
The cognitive loop IS the automation engine. HA becomes one optional
adapter, not a requirement.

**Pros:**
- No HA dependency. No house of cards.
- Halbert's cognitive loop is already the automation engine — just need the
  device bus to be direct.
- Lighter weight (no HA overhead on the edge node).
- HalbertOS's thesis becomes "the best OS for an autonomous agent," not
  "the best HA host."
- `matter-rs` and MQTT are both Rust-native, fitting the Universal Rust
  Core plan perfectly.
- Aligns with the Singular Entity vision: the agent's body is the house,
  not a container running someone else's app.

**Cons:**
- Lose HA's integration long tail (weather APIs, obscure IoT brands).
  But most homes use 5-15 device types, all Zigbee/Matter/MQTT.
- Lose HA's device-pairing UI, but Halbert has its own dashboard.
- More engineering work (Matter controller, MQTT device registry, Z2M
  integration) vs. just consuming HA's API.
- Matter is still maturing; `matter-rs` is functional but not production-
  hardened for all device types.

**Verdict: This is the right long-term direction.** It doesn't require
abandoning HA (Option B still works for HA users) — it makes HA optional
instead of load-bearing.

### Option D: Don't do smart home at all

**What:** Halbert is a sysadmin/OS guardian only. Drop HA, Frigate, voice,
the whole home automation track.

**Verdict: Ship has sailed.** The codebase already has HA integration,
Frigate, auditory cortex, Wyoming voice, proactive gate, cognitive loop,
home variant. The question isn't whether Halbert does smart home — it's how.

---

## 6. Recommended Strategy: Three-Layer, No House of Cards

### Layer 1 — Short term (now): HA as peer (Option B)

Keep the current HA WebSocket integration as the primary smart home path.
It's built, it works, it's the path of least resistance for existing HA
users. Don't host it, don't build an OS around it.

### Layer 2 — Medium term: Native device bus (Option C)

Build native MQTT + Zigbee2MQTT + Matter support into Halbert. This makes
HA optional. The cognitive loop already is the automation engine — you just
need the device bus to be direct.

Concrete first steps:
- `crates/halbert-mqtt` — Rust MQTT client (rumqttc) + device state cache
- `crates/halbert-matter` — `matter-rs` wrapper for Matter controller mode
- MQTT device registry in the Python agent (map MQTT topics to Halbert
  entity concepts, similar to how HAEventMapper maps HA entities now)
- Zigbee2MQTT discovery (auto-detect Z2M on the network, subscribe to its
  topics)

This fits the Universal Rust Core plan: the MQTT and Matter crates are
Rust-native, consumed by Tauri (direct), Python (PyO3), and HalbertOS
daemons (standalone).

### Layer 3 — Long term (HalbertOS): Agent-first OS, not HA host

The OS thesis is "an OS where the agent is a first-class kernel citizen" —
eBPF telemetry, Btrfs atomic rollback, Landlock sandboxing for the agent's
own actions. Not "a better HAOS." HA is one integration among many,
running on a Pi somewhere, consumed via API. The OS doesn't know or care
that HA exists.

### The key architectural principle

> **Halbert's value is the cognitive layer, not the device bus.**
> The device bus is a commodity (MQTT/Matter/Zigbee).
> HA is a convenient adapter for that commodity, not a foundation to build on.
> Never let a third-party application be load-bearing in your OS thesis.

---

## 7. Corrections Needed in the Experimental Docs

### 7.1 `SINGULAR-ENTITY-HOME-ASSISTANT-AND-HALBERTOS-ECOSYSTEM.md`

**§2, Tier B:** "HalbertOS hosts Home Assistant Supervised (Docker)" is
factually broken. Supervised was deprecated 2025-05, unsupported since
2025-12. Tier B must either:
- Be removed entirely, OR
- Be reframed as "HalbertOS runs HA Container (no add-ons) for users who
  want HA on the same box" — with the explicit caveat that this loses the
  add-on ecosystem and is not the recommended path.

**§2, Tier B "Superpowers":** The three claimed superpowers (Btrfs rollbacks
for HA updates, eBPF IoT isolation, local AI model provisioning) are valid
as OS features but should be reframed as "what HalbertOS does for any
service it runs" not "what it does for HA specifically." They are not
reasons to host HA; they are reasons to have an OS.

**§2, overall:** Add Option C (native MQTT/Matter) as the strategic
direction. The doc currently presents HA as the only smart home path. It
shouldn't be.

### 7.2 `HALBERT-OS-DISTRO-AND-UNIVERSAL-RUST-ARCHITECTURE.md`

**§2, Ring 1 (Storage):** "Instant Rollback ... rolls back in under 5ms" —
snapshot *creation* is fast, but rollback to a root subvolume typically
requires unmount or reboot. Relabel as a target, not a measurement.

**§4, table:** "Audio Capture & Echo Cancel — Already native in src-tauri!"
— `audio_capture.rs` exists as a stub, but AEC is listed as remaining work
in the auditory cortex handoff. Mark as "stubbed, not complete."

**§5, overall:** Add a maturity caveat. HalbertOS as a full distro (mkosi +
Btrfs + eBPF + Landlock + initramfs sentinel + Wayland compositor + halbertd
as PID 1) is a multi-year effort. The Rust crates are the tractable first
step; the distro is the north star.

### 7.3 `UNIVERSAL-CROSS-PLATFORM-AND-MIGRATION-ROADMAP.md`

**§2.1 (macOS):** APFS snapshot transactions via `fs_snapshot_create`/
`fs_snapshot_revert` are private SPIs. Using them in a shipping, notarized
app risks breakage across macOS versions and App Review friction. Add a
caveat.

**§2.2 (Windows):** ETW + VSS + ConPTY + DirectML + Job Objects is a second
full platform engineering effort. The matrix presents it as a neat parallel
column, but it should be explicitly deferred behind Linux + macOS.

**§4 (Timeline):** M1 Q4 2026, M2 Q1 2027, M3 Q2 2027, M4 Q3 2027 —
aggressive for a small team already juggling modality/voice, security
reviews, HA integration, marketing, and three sister apps on Haloysius.
The crates are plausible; the integration milestones are not. Mark as
aspirational.

### 7.4 `COMPETITIVE-ANALYSIS-AI-OS-LANDSCAPE.md`

**§1 and §4:** "14,000+ indexed docs" — the actual corpus is 24,643 docs
per `marketing/VECTOR-PARALLAX-VISION-AND-SPECIFICATION.md:156`. The
experimental docs undercount. Reconcile to the real number.

**§3.1:** "Apple Intelligence (macOS Sequoia/Tahoe)" — Sequoia is macOS 15
(2024); the doc is dated 2026. Tahoe (macOS 26) is current. Drop Sequoia
or clarify the version range.

**§5, item 3:** "0% unrecoverable failure rate" is a marketing aspiration
stated as a future benchmark result. Relabel as a target.

### 7.5 `OS-NATIVE-MCP-WARP-AND-SOURCEPREP-INTEGRATION.md`

**§1, "14,000+ Sysadmin Offline RAG Documents":** Same doc count issue —
reconcile to 24,643.

**Overall:** This is the most near-term-actionable doc. The `os://` MCP
server concept is buildable on the existing MCP server (`halbert_core/mcp/`)
and SourcePrep integration. No major corrections needed beyond the doc count.

### 7.6 `README.md` (experimental folder index)

Add a **"Status & Maturity" preamble** distinguishing:
- **Near-term actionable:** Rust crates (halbert-telemetry, halbert-snapshots,
  halbert-sandbox, halbert-pty), OS-native MCP server, capability registry
- **North-star / multi-year:** HalbertOS distro, Windows platform, Wayland
  compositor, halbertd as PID 1

---

## 8. Open Questions for the Reviewer

### Q1: Is the three-layer strategy sound?

Layer 1 (HA as peer, now) → Layer 2 (native MQTT/Matter, medium term) →
Layer 3 (agent-first OS, long term). Is this the right sequencing? Should
Layer 2 come sooner or later? Is there a risk of building native device
support that HA already covers well enough?

### Q2: Matter maturity — is it ready for a native controller?

`matter-rs` exists and is functional, but Matter device certification is
still maturing. Is it too early to bet on native Matter support, or is this
the right time to start? What's the fallback if Matter adoption stalls?

### Q3: Should HalbertOS exist at all?

The founder's "house of cards" concern extends beyond HA hosting. Is
building a custom Linux distro the right move for a small team, or should
Halbert remain a userspace application (Tauri + Python + Rust crates) on
standard distros? What does HalbertOS buy that a well-packaged app on
Ubuntu/Arch doesn't?

### Q4: If HalbertOS does exist, what's its thesis?

If not "a better HAOS," then what? Options:
- "The safest OS for autonomous agents" (Landlock + Btrfs + eBPF)
- "The OS where the agent is PID 1's peer" (halbertd as system broker)
- "The OS that heals itself" (sentinel recovery + atomic rollback)
- Something else?

### Q5: HA Container as a compromise?

If a user wants HA on the same box as Halbert (no separate Pi), is HA
Container (no add-ons) acceptable? The user would run Zigbee2MQTT,
Mosquitto, etc. as separate Docker containers. This is more work for the
user but avoids the Supervised dependency. Is this worth supporting as a
documented path, or should we steer users to "HA on a separate device,
always"?

### Q6: The integration long tail

If Halbert goes native (Option C), it loses HA's 2000+ integrations. How
much does this matter in practice? Is there a middle ground — e.g., a
"HA compatibility layer" that lets Halbert consume HA integrations without
running HA as the automation engine?

### Q7: Competitive positioning

The competitive analysis doc positions Halbert as "The Sovereign
Self-Healing Host Custodian." If Halbert de-emphasizes HA hosting, does
this positioning still hold? Or does it need to shift toward "The
Autonomous Agent OS" framing?

---

## 9. Sanity-Pass Summary (Full Session Findings)

For the reviewer's context, the sanity pass on all five experimental docs
found:

### What's genuinely valuable (real, not optimistic)

1. **Universal Rust Tri-Bridge** (doc 1, §3) — sharing crates between
   Tauri, Python (PyO3), and native daemons. Highest-leverage idea;
   `audio_capture.rs` proves the seam exists.
2. **Two-track migration strategy** (doc 2, §1) — keep Python velocity,
   subtractively carve out Rust. Shows restraint.
3. **Competitive taxonomy** (doc 3) — three-flaw framing is accurate;
   "Sovereign Self-Healing Host" positioning is right.
4. **Three-layer decoupling** (doc 4, §1) — Identity/Memory ↔ Body
   Capability ↔ Host Runtime. Clean abstraction of work already happening
   (F5 capability registry, PeerMemoryBackend).
5. **OS-as-MCP-server** (doc 5) — most near-term-actionable idea; the MCP
   server and SourcePrep already exist.

### What's optimistic (temper these)

1. **HalbertOS as a full distro** — each ring (eBPF, Btrfs, Landlock,
   initramfs, Wayland compositor, halbertd PID 1) is a multi-month effort.
2. **Performance table** (doc 4, §4) — "<12 MB RAM", "15 ms cold start",
   "2 ms mTLS", "1 ms PTY/voice" are aspirational, not measured.
3. **"5ms rollback"** (docs 1, 3, 5) — creation is fast, rollback typically
   needs unmount/reboot.
4. **APFS snapshot SPIs** (doc 2, §2.1) — private APIs, notarization risk.
5. **Windows as parallel track** (doc 2, §2.2) — second full platform
   effort, should be deferred.
6. **Timelines** (doc 2, §4) — aggressive for a small team.
7. **HA Supervised hosting** (doc 4, §2 Tier B) — factually broken,
   Supervised is dead.

### Factual nits

- Doc count: docs say "14,000+", actual is 24,643.
- Audio capture: stub exists, AEC does not.
- Apple Intelligence: Sequoia reference is stale for a 2026 doc.

---

## 10. Source Documents

All documents referenced in this review request:

| Document | Path |
|----------|------|
| HalbertOS & Universal Rust Architecture | `documentation/experimental/HALBERT-OS-DISTRO-AND-UNIVERSAL-RUST-ARCHITECTURE.md` |
| Universal Cross-Platform & Migration Roadmap | `documentation/experimental/UNIVERSAL-CROSS-PLATFORM-AND-MIGRATION-ROADMAP.md` |
| Competitive Analysis: AI OS Landscape | `documentation/experimental/COMPETITIVE-ANALYSIS-AI-OS-LANDSCAPE.md` |
| Singular Entity, HA & HalbertOS Ecosystem | `documentation/experimental/SINGULAR-ENTITY-HOME-ASSISTANT-AND-HALBERTOS-ECOSYSTEM.md` |
| OS-Native MCP, Warp-CLI & SourcePrep | `documentation/experimental/OS-NATIVE-MCP-WARP-AND-SOURCEPREP-INTEGRATION.md` |
| Experimental README | `documentation/experimental/README.md` |
| HA deprecation blog (external) | `https://www.home-assistant.io/blog/2025/05/22/deprecating-core-and-supervised-installation-methods-and-32-bit-systems/` |
| ADR-0014 (reverted) (external) | `https://github.com/home-assistant/architecture/blob/master/adr/0014-home-assistant-supervised.md` |
| Drop discussion #1198 (external) | `https://github.com/home-assistant/architecture/discussions/1198` |
| Vector parallax spec (doc count source) | `marketing/VECTOR-PARALLAX-VISION-AND-SPECIFICATION.md` |

---

## Review Directives

**Review level:** Fable Level (highest scrutiny).

**What we want from you:**

1. **Scrutinize the three-layer strategy** (Section 6). Is the sequencing
   right? Are there hidden dependencies between layers? Is Layer 2 (native
   MQTT/Matter) worth the engineering cost, or is HA-as-peer good enough
   indefinitely?

2. **Pressure-test the "HA is optional" thesis** (Section 4). Is the device
   layer really a commodity? Are there device categories that only HA
   supports well? What's the real cost of losing the integration long tail?

3. **Evaluate the HalbertOS question** (Q3, Q4). Should a custom distro
   exist at all? If yes, what's the right thesis? If no, what's the
   alternative for the kernel-level features (eBPF, Landlock, Btrfs)?

4. **Verify the factual claims** (Section 1, Section 7). The HA Supervised
   deprecation is the headline. Are there other factual errors in the
   experimental docs that the sanity pass missed?

5. **Challenge the house-of-cards analysis** (Section 2). Is the dependency
   stack really as fragile as described? Are there ways to host HA that
   avoid the fragility? Or is the analysis correct that hosting is always
   the wrong move?

6. **Identify missing options.** Are there strategic paths (A-D or beyond)
   that this analysis didn't consider?

**What we do NOT want:**

- Implementation plans. This is strategy, not execution.
- Marketing copy. The competitive positioning is for internal alignment.
- Unbounded scope expansion. If you find the docs are trying to do too
  much, say so — don't add more.

---

## Current State

The experimental documentation folder exists and has been read. No changes
have been made to any files. This review request is the output of the
sanity-pass session. The founder has reviewed the analysis verbally and
agreed it should be documented and handed off for external review before
any corrections are applied to the experimental docs.

**Next steps after review:**
1. Incorporate review feedback
2. Apply corrections to the five experimental docs + README
3. Decide on the three-layer strategy (commit, modify, or reject)
4. If Layer 2 (native MQTT/Matter) is approved, create an implementation
   handoff for the Rust crates
