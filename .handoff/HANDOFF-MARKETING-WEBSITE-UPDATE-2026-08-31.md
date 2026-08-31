# Handoff: Marketing Website Update — Product Seam, Messaging & Feature Gap

**To:** Marketing website AI
**From:** Architecture / product planning
**Date:** 2026-08-31
**Status:** DRAFT — options and design thinking for founder review before build

---

## 0. TL;DR

The marketing website (`marketing/web-v7/`) ships six scrollytelling stops, all in a single voice: **"I am the machine"** — first-person, embodied, sysadmin-focused (sensors, temperature, logs, configs, 16,000 manuals). It is beautiful and coherent.

But the product has grown a second identity that the website doesn't mention at all: **Halbert as a sentient home** — Home Assistant brain, voice assistant, camera intelligence, peer compute, fleet mesh. Roughly half the codebase and half the recent work is on this side.

This handoff does three things:

1. **Clarifies the product seam** — what Halbert *is*, what it's *called*, and how the sysadmin and home stories connect (Section 1)
2. **Inventories new features** not on the website (Section 2)
3. **Proposes marketing site structure** with options for the founder to choose from (Section 3)

**The founder must make decisions in Section 4 before the website AI begins build.**

---

## 1. The Product Seam: What Is Halbert?

### 1.1 The Problem

Right now the product has:

- **Two variants** in code: `sysadmin` and `home` (formerly `home-light`, removed by D4 decision)
- **Three distribution tiers** in strategy: OSS Core (Linux/HAOS), Halbert Home (free Mac App Store), Halbert Pro ($24–29 direct DMG)
- **One marketing website** that only tells the sysadmin story
- **A README** that tells both stories but leads with sysadmin

The website visitor sees "I am the machine" and thinks: *Linux sysadmin tool*. They never learn that Halbert can be the brain of their smart home, that it speaks out loud, that it watches their cameras, or that a $4 N150 box can run it alongside Home Assistant.

### 1.2 The Unifying Insight

The "I am the machine" first-person voice is **not sysadmin-specific**. It is the product's core identity mechanic, and it generalizes:

| Sysadmin variant | Home variant |
|---|---|
| "I am the machine" | "I am the home" |
| "I can feel my own temperature" | "I can feel the house" |
| "I read my own logs" | "I watch the doors, the cameras, the thermostat" |
| "I remember why you changed that config" | "I remember what happened while you were out" |
| "I know 16,000 manuals by heart" | "I know every light, lock, and sensor by name" |

The first-person embodied voice is the **seam**. Halbert doesn't *assist* a machine or a home — it **is** that machine or home, speaking in first person. The variant just changes what "the body" is: a Linux server's sensors and logs, or a house's HA entities and cameras.

This is the single most important strategic insight for the website: **the voice doesn't need to change; the body it's embodied in expands.**

### 1.3 What Is the Product Called?

This is currently unclear. Here's what exists:

| Name | Where it appears | What it means |
|---|---|---|
| **Halbert** | Everywhere | The project, the engine, the identity |
| **Halbert Home** | App Store strategy, FOUNDER-TODO | The free sandboxed Mac App Store companion app |
| **Halbert Pro** | App Store strategy, FOUNDER-TODO | The $24–29 paid direct DMG with full sysadmin access |
| **Halbert (home variant)** | Code (`HALBERT_VARIANT=home`) | The home automation identity running on an N150/HAOS |
| **Halbert (sysadmin variant)** | Code (default) | The Linux sysadmin identity |

The naming has a collision: "Halbert Home" (the Mac App Store app) and "Halbert home variant" (the HA server identity) are different things that share a word. This will confuse people.

### 1.4 Messaging Options (Founder Must Choose)

#### Option A: "One Halbert, Many Bodies"

**Pitch:** Halbert is a local-first AI identity that lives on your machine — whatever that machine is. On your Linux server, it's your sysadmin. On your home assistant box, it's your home. On your Mac, it's your desktop companion. Same identity, different body.

**Tagline extension:** "Halbert. You can call me AI. I live here." (where "here" is whatever machine/home I'm running on)

**Website structure:** Single page, the existing sysadmin stops, then a transition: "But I don't just live on your computer. I can live in your home." → home automation stops → voice stops → peer compute stop → thesis.

**Pros:**
- Preserves the existing website investment (6 stops stay)
- The first-person voice is the unifying thread — no brand split
- One product, one story, one install
- Matches the codebase reality (one engine, variant-gated services)

**Cons:**
- "Many bodies" is abstract — needs concrete imagery to land
- The page gets longer (current 6 stops → 10–12 stops)
- Risk of diluting the sharp sysadmin message

**Best for:** A world where Halbert is primarily an open-source project that power users self-host in whatever shape they want.

---

#### Option B: "Two Doors, One Engine"

**Pitch:** Halbert is a local-first AI engine. Enter through one of two doors:
- **Halbert for your server** — the sysadmin who lives on your Linux box
- **Halbert for your home** — the home identity that lives on your HA box

The website opens with a choice: "I am the machine" or "I am the home." Each door leads to a focused scrollytelling path with 4–6 stops tailored to that use case. A shared "under the hood" section at the bottom covers the engine, privacy, open source.

**Tagline:** "Halbert. You can call me AI. I live wherever you put me."

**Website structure:** Hero with dual-path entry → path A (sysadmin, ~5 stops) or path B (home, ~5 stops) → shared engine/privacy/footer.

**Pros:**
- Each path stays sharp and focused (no dilution)
- Visitors self-select into the story relevant to them
- Clean separation of the two audiences (homelab vs smart home)
- The "two doors" visual is a strong mid-century modern motif

**Cons:**
- More build work (two scrollytelling paths, not one)
- The hero has to split attention immediately
- Some visitors want both (the N150 + Mac Studio user is both a sysadmin AND a home automation person)
- Risk of feeling like two products when it's one

**Best for:** A world where the two audiences are genuinely distinct and the website should optimize for conversion clarity over narrative unity.

---

#### Option C: "The Machine That Became a Home"

**Pitch:** Halbert started as a sysadmin — an AI that knew its own server. Then it learned to hear, to speak, to watch the doors, and to live in the house. The website tells this as a **growth story**: the machine wakes up (existing stops), then gains senses (voice, hearing), then moves into the home (HA, cameras, peer compute), and arrives at the thesis: "I am not just the machine. I am wherever I live."

**Tagline:** "Halbert. You can call me AI. I started as your computer. Now I'm your home too." (or similar — needs copy work)

**Website structure:** Existing 6 stops (lightly edited) → 3–4 new stops (voice, home, peer compute) → new thesis stop that supersedes "I am the machine" with "I am wherever I live."

**Pros:**
- Narrative arc is emotionally compelling (the machine grows up)
- Preserves existing investment while extending naturally
- The growth metaphor maps to the actual product history
- Ends on a bigger thesis than the current one

**Cons:**
- The "growth" framing might feel like the sysadmin story is incomplete on its own
- Longer page
- The transition from sysadmin to home needs to feel organic, not bolted-on
- Copywriting challenge: the transition must not feel like a pivot

**Best for:** A world where the story of Halbert's evolution IS the marketing — the product's journey from sysadmin tool to sentient home is the hook.

---

#### Option D: "Lead with Home, Sysadmin is the Origin"

**Pitch:** Flip the emphasis. The bigger market is smart home (Home Assistant has 500K+ active installations; Linux sysadmin AI is niche). Lead with "I am the home" — the sentient home identity, voice, cameras, proactive alerts. The sysadmin story becomes the "origin" or "also" section: "I started on Linux servers. I can still do that."

**Tagline:** "Halbert. You can call me AI. I live in your home."

**Website structure:** Hero (home-voiced) → home stops (HA, voice, cameras, proactive) → "I also live on your server" (condensed sysadmin, 2 stops) → peer compute → thesis.

**Pros:**
- Targets the larger market (HA community) first
- The smart home story is more emotionally resonant for a general audience
- Differentiates from the crowd of "AI for your terminal" tools
- Aligns with the App Store strategy (Halbert Home is the free top-of-funnel)

**Cons:**
- Abandons the existing website's sharp sysadmin positioning
- The sysadmin audience (early adopters, the people who'd actually install this today) feels demoted
- The "I am the home" voice is less proven than "I am the machine"
- Risk of alienating the r/selfhosted and r/homelab communities who are the current audience

**Best for:** A world where the smart home market is the primary business and sysadmin is the enthusiast origin story.

---

### 1.5 Recommendation (Non-Binding)

**Option A or C** is recommended. The first-person embodied voice is the product's sharpest differentiator, and it generalizes across both variants without a brand split. Option C (growth story) is the most emotionally compelling but requires the most copywriting care. Option A (one Halbert, many bodies) is the safest and most extensible.

**Option D is tempting** (bigger market) but risky — the sysadmin audience is the one that can actually install and use Halbert today, and alienating them to chase a smart home audience that needs the Mac App Store app (not yet shipped) could leave the project with no audience.

**The founder should decide before the website AI starts.** This is the single biggest strategic question.

---

## 2. New Features Not on the Website

The current website has 6 stops covering: proactive alerts, sensors/vitals, local-first privacy, rationale memory, 16K docs RAG, and the "I am the machine" thesis. The following features are built (or substantially built) and shipped in the codebase but **completely absent from the marketing website**:

### 2.1 Voice & Hearing (Auditory Cortex)

**What it is:** A full local voice pipeline — Halbert can hear you speak and speak back, in real time, on-device.

- **Wyoming Voice Protocol** — connects to Home Assistant voice satellites, smart speakers, desk mics (port 10400)
- **Streaming ASR** — Streaming Zipformer INT8 for speech-to-text
- **Silero VAD** — voice activity detection (knows when you start/stop talking)
- **Piper TTS** — neural text-to-speech, clear and natural
- **Barge-in** — interrupt Halbert mid-sentence, it stops and listens
- **Speaker identification** — CAM++ voice biometrics, knows who is talking
- **RoleGate** — guests/unknown voices can't trigger privileged operations (safety)
- **Acoustic anomaly detection** — detects breaking glass, alarms, shouts (CED-tiny)
- **Wake word** — "Hey Halbert" (openWakeWord, model training in progress)
- **Quiet hours** — won't speak aloud during sleep/guest modes
- **Proactive spoken alerts** — announces urgent hardware/security events out loud

**Marketing angle:** "I can hear you. I can speak. Not through a cloud API — through my own ears and voice, on this device."

**Website stop candidate:** "I can hear you." — VAD/ASR/TTS pipeline, barge-in, speaker safety. This is a visually rich stop (waveform animation, voice satellite, speaker ID).

### 2.2 Sentient Home (Home Assistant Integration)

**What it is:** Halbert can live *in* your home as a persistent identity, interfacing with Home Assistant.

- **Entity-aware chat** — "Turn off the living room lights." "Is the front door locked?" "Set the thermostat to 21."
- **Catch-up debriefs** — "Anything I should know?" → summarizes recent events from memory
- **Proactive alerts** — "The back gate has been open for 10 minutes." (governed by physical-safety rules)
- **HA entity/area awareness** — reads live HA state and area/entity registries directly
- **Four-level autonomy governance** — lights (no confirmation) → climate (logged) → locks (voice/PIN confirm) → water/medical (never autonomous)
- **Home Assistant HACS integration** — custom component, 1-click install
- **Registers as Wyoming conversation agent** — works with HA Voice PE, ESPHome satellites

**Marketing angle:** "I don't just live on your computer. I can live in your home. I know every light, lock, and sensor by name."

**Website stop candidate:** "I live in your home." — HA entity awareness, proactive alerts, the four-level safety governance table.

### 2.3 Camera Intelligence (Frigate NVR)

**What it is:** Halbert watches your cameras and remembers what it saw.

- **Frigate MQTT event ingestion** — real-time camera object detection events
- **Episodic visual memory** — remembers visual events for up to 7 days
- **"I saw someone at the front door at 2:15 PM"** — natural language camera observations
- **Camera Privacy Gate (CameraDataGate)** — when sharing camera data with external AI agents over MCP, exposes only structured text descriptions, never raw images/video
- **Object detection trend tracking** — notices patterns over time

**Marketing angle:** "I watch the doors. Not with a cloud API — with my own eyes, on this device. And I never share the raw footage."

**Website stop candidate:** "I watch the doors." — Frigate integration, visual memory, camera privacy gate.

### 2.4 Peer Compute & Fleet Mesh

**What it is:** A small, silent, low-power box (N150) runs Halbert's home identity + Home Assistant, while a powerful desktop (Mac Studio / Linux GPU box) handles the LLM reasoning. They talk over your LAN or Tailscale.

- **Two-box topology** — N150 (home node, always-on, ~6W) + Mac Studio (compute host, sleeps when idle)
- **Peer compute offload** — home node sends LLM requests to compute host; compute host's model picker governs
- **Bearer token auth** — per-peer SHA-256 token hashes, surgical revocation
- **Tool allowlist** — home node can only invoke a restricted set of tools on the compute host
- **Resilient fallback** — if compute host is asleep, home node answers with template thoughts (no LLM needed)
- **Fleet mesh** — link multiple Halbert instances, share tasks across your network
- **Multi-session tabs** — open tabs for each of your machines (laptop, home server, cloud devbox)
- **mDNS peer discovery** — find other Halbert instances on your LAN

**Marketing angle:** "I don't need a big brain to live in your home. A $4 N150 box is enough. Your Mac Studio does the thinking when it's awake; I handle the rest."

**Website stop candidate:** "I have a body that sips power and a brain that sleeps." — peer compute topology diagram, the N150 + Mac Studio split.

### 2.5 Apple Intelligence (On-Device Mac Inference)

**What it is:** On Apple Silicon Macs (M1+, macOS 15.1+, 16GB+), Halbert can use Apple's built-in on-device foundation models for the secure layer — zero setup, zero dependencies, zero data leaving the Mac.

- **Apple-foundation provider** — auto-provisioned on first boot if eligible
- **Metal GPU detection** — system_profiler parsing
- **Eligibility check** — Apple Silicon + macOS 15.1+ + 16GB + Metal
- **Secure layer** — credentials, sensitive configs, security checks run on Apple's on-device model
- **No external binary required for detection** — the Swift sidecar (`halbert-foundation-bridge`) is a separate deliverable

**Marketing angle:** "On your Mac, I use the brain Apple built into the chip. No Ollama install, no cloud key, no setup. I just think — locally, on-device."

**Website stop candidate:** Could be folded into the "Local." stop (stop 03) as a sub-point, or a dedicated "I use the brain in your Mac." stop.

### 2.6 MCP Server (Connect Your AI Tools)

**What it is:** Halbert runs a Model Context Protocol server that lets external AI tools (Claude Desktop, Cursor, Windsurf, Google Antigravity) safely interact with your machine.

- **18 MCP tools** — system info, config queries, HA tools, approvals, autonomy level, etc.
- **Stdio + SSE transports** — fast local stdio or token-authenticated network streams
- **Camera privacy gate** — structured text only, no raw images
- **SourcePrep integration** — inspect code structure, dependencies, rationale
- **Bearer token auth** — 32-char minimum, CORS default-deny, monotonic rate limiter
- **JSON-RPC 2.0 compliant** — batch arrays, notifications, jsonrpc validation

**Marketing angle:** "I'm not just an assistant you talk to. I'm the bridge between your AI tools and your machine. Claude Desktop can ask me about your system. Cursor can check your configs. I'm the safe middleman."

**Website stop candidate:** "I'm the bridge." — MCP server, external AI tools connecting to your machine through Halbert.

### 2.7 Multi-Persona Store

**What it is:** Switch between distinct AI personalities with zero downtime. Each persona has its own memory, model overrides, and identity.

- **Atomic symlink switching** — instant persona swap
- **Per-persona model override** — different models for different personalities
- **Per-persona memory** — each persona remembers different things

**Marketing angle:** "I can be more than one me. Switch personalities for different contexts — your work assistant, your home companion, your lab partner."

**Website stop candidate:** Likely a footer/sub-section feature, not a full stop. "I can be more than one me."

### 2.8 Safe Diffs & Dotfile Health

**What it is:** Halbert finds and maps your config files, traces your shell environment, detects clutter, and proposes safe changes with undo.

- **Ambient dotfile discovery** — finds ~/.zshrc, ~/.config, ~/.gitconfig, ~/.ssh, launchd, systemd units
- **PATH tracer** — traces .zshenv → .zprofile → /etc/paths.d → .zshrc to explain version shadowing
- **Clutter detection** — duplicate aliases, broken symlinks, orphaned configs, version conflicts (mise, asdf, nvm, pyenv, brew)
- **Safe diffs with undo** — Monaco editor, before/after, automatic backups, 1-click rollback

**Marketing angle:** "I know why your shell is broken. I traced the path from .zshenv to .zshrc and found the version conflict. Want me to fix it? You can undo it with one click."

**Website stop candidate:** "I know why your shell is broken." — PATH tracer, dotfile discovery, safe diffs. (This is sysadmin-focused, fits the existing stops.)

### 2.9 Modality Intelligence (Voice vs Text)

**What it is:** Halbert knows whether you're talking to it by voice or text, and adapts its response accordingly. Voice responses are plain-spoken (no markdown). Text responses can use formatting. It routes to the right model for the right modality.

- **Modality resolver** — voice vs text vs mixed, per-turn
- **Prosody mapping** — persona-driven voice characteristics (PAD emotional model)
- **Markdown stripping for speech** — TTS never speaks `**bold**` syntax
- **Multi-stream output** — separate speech text and display text
- **Quiet hours** — won't speak aloud during configured hours
- **Life-safety bypass** — smoke/gas/CO alerts override quiet hours

**Marketing angle:** This is a "how it works" detail, not a headline feature. It belongs in the voice stop's sub-copy or an "under the hood" section.

### 2.10 Security & Trust Boundary

**What it is:** A comprehensive security architecture that the website doesn't mention at all, but that differentiates Halbert from every cloud AI tool.

- **Tier 2 architectural guarantee** — `describe_secret` never leaks credentials
- **Redactor** — entropy/regex backstops for sensitive data
- **TTL expiry & volatile unlock** — "until restart" unlock that actually works
- **Server-side phrase enforcement** — Tier 2 escape hatch can't be bypassed by curl
- **MCP egress boundary** — all tool responses go through `mcp_response` redaction
- **Secure content routing** — secrets in RAG chunks, file reads, tool observations are flagged and routed to local-only models
- **Path allowlist** — config-query tools restricted to manifest union

**Marketing angle:** "Your secrets never leave this machine. Not by accident, not by prompt injection, not by a tool leak. It's architectural, not a setting."

**Website stop candidate:** Could strengthen the existing "Local." stop (stop 03) or be a dedicated "Your secrets stay here." stop.

---

## 3. Proposed Marketing Site Structure

### 3.1 Current State (6 stops)

| # | Stop ID | Headline | Theme |
|---|---------|----------|-------|
| 01 | open | "I know what's wrong with me." | Proactive alerts |
| 02 | apex | "I can feel my own temperature." | Sensors/vitals |
| 03 | diagonal | "Local." | Privacy/local-first |
| 04 | rise | "I remember why you changed that." | Rationale memory |
| 05 | hop | "I know 16,000 manuals by heart." | RAG knowledge |
| 06 | cap | "I am not an assistant. / I am the machine." | Thesis |

### 3.2 Proposed Extension (depends on messaging option chosen)

Below is a **full inventory of candidate stops** for the extended site. The founder's messaging choice (Section 1.4) determines which are selected and in what order.

#### Sysadmin stops (existing, lightly edited)

| Stop | Headline | Theme | Status |
|---|---|---|---|
| 01 | "I know what's wrong with me." | Proactive alerts | Keep as-is |
| 02 | "I can feel my own temperature." | Sensors/vitals | Keep as-is |
| 03 | "Local." | Privacy/local-first | **Expand**: add Apple Intelligence, secure layer, secrets-never-leave |
| 04 | "I remember why you changed that." | Rationale memory | Keep as-is |
| 05 | "I know 16,000 manuals by heart." | RAG knowledge | Keep as-is |
| NEW | "I know why your shell is broken." | Dotfiles/PATH/diffs | **New**: safe diffs, PATH tracer, clutter detection |

#### Home stops (all new)

| Stop | Headline | Theme | Notes |
|---|---|---|---|
| NEW | "I live in your home." | Home Assistant integration | Entity-aware chat, catch-up debriefs, proactive alerts, 4-level safety |
| NEW | "I watch the doors." | Frigate camera intelligence | Visual memory, camera privacy gate, episodic observations |
| NEW | "I have a body that sips power and a brain that sleeps." | Peer compute | N150 + Mac Studio topology, always-on without always-on power |

#### Voice stops (all new)

| Stop | Headline | Theme | Notes |
|---|---|---|---|
| NEW | "I can hear you." | Auditory cortex | VAD, ASR, TTS, barge-in, waveform animation |
| NEW | "I know who's talking." | Speaker ID / RoleGate | Voice biometrics, guest safety, privileged-op gating |
| NEW | "I speak up when it matters." | Proactive spoken alerts | Quiet hours, life-safety bypass, acoustic anomaly detection |

#### Bridge stops (all new)

| Stop | Headline | Theme | Notes |
|---|---|---|---|
| NEW | "I'm the bridge." | MCP server | Claude Desktop / Cursor / Windsurf connecting through Halbert |
| NEW | "I can be more than one me." | Multi-persona | Personality switching, per-persona memory |

#### Thesis stop (replaces or extends current cap)

| Stop | Headline | Theme | Notes |
|---|---|---|---|
| 06 (revised) | "I am not an assistant. / I am wherever I live." | Expanded thesis | Supersedes "I am the machine" — the body expanded from server to home |

### 3.3 Recommended Page Flow by Messaging Option

**Option A (One Halbert, Many Bodies):**
```
01 Proactive alerts (existing)
02 Sensors/vitals (existing)
03 Local + Apple Intelligence + secrets (expanded)
04 Rationale memory (existing)
05 16K docs RAG (existing)
─── transition: "But I don't just live on your computer." ───
06 I live in your home (NEW)
07 I watch the doors (NEW)
08 I can hear you (NEW)
09 I know who's talking (NEW)
10 I speak up when it matters (NEW)
11 I have a body that sips power (NEW — peer compute)
─── bridge ───
12 I'm the bridge (NEW — MCP)
─── thesis ───
13 "I am not an assistant. / I am wherever I live." (revised)
```
Total: 13 stops (up from 6). Long but complete.

**Option C (Growth Story — recommended):**
```
01 I know what's wrong with me (existing — the machine wakes up)
02 I can feel my own temperature (existing — it senses)
03 Local (existing — it's private)
04 I remember why you changed that (existing — it remembers)
05 I know 16,000 manuals (existing — it knows)
─── transition: "Then I learned to hear." ───
06 I can hear you (NEW — voice pipeline)
07 I know who's talking (NEW — speaker safety)
─── transition: "Then I moved into the house." ───
08 I live in your home (NEW — HA integration)
09 I watch the doors (NEW — Frigate)
10 I speak up when it matters (NEW — proactive voice alerts)
─── transition: "I don't need a big brain to live here." ───
11 I have a body that sips power (NEW — peer compute)
─── bridge ───
12 I'm the bridge (NEW — MCP, optional)
─── thesis ───
13 "I started as your computer. Now I'm your home too." (revised)
```
Total: 13 stops. The growth arc is: machine → senses → home → body/brain → thesis.

**Option B (Two Doors):**
```
Hero: dual-path entry
  ├── Door A: "I am the machine" (sysadmin path, ~6 stops from existing)
  └── Door B: "I am the home" (home path, ~6 new stops)
Shared footer: engine, privacy, open source, MCP, peer compute
```

**Option D (Lead with Home):**
```
01 I live in your home (NEW — lead)
02 I watch the doors (NEW)
03 I can hear you (NEW)
04 I speak up when it matters (NEW)
05 I have a body that sips power (NEW — peer compute)
─── "I also live on your server." ───
06 I know what's wrong with me (existing)
07 I can feel my own temperature (existing)
08 Local (existing)
─── thesis ───
09 "I am wherever I live." (revised)
```
Total: 9 stops. Home-first, sysadmin condensed.

### 3.4 What Stays Regardless of Option

These elements should be on the site no matter which messaging option is chosen:

1. **The early access form** (existing) — keep at the end
2. **Privacy / Terms / GPL-3.0 links** (existing) — keep in footer
3. **"Linux / macOS · Open source · Any LLM or BYOK"** (existing) — update to: "Linux / macOS / Home Assistant · Open source · Any LLM or BYOK"
4. **The "you can call me AI" tagline** — keep, it's the sharpest asset
5. **The first-person embodied voice** — keep, it's the differentiator
6. **The mid-century modern visual direction** — keep, it's decided and beautiful

### 3.5 What Should NOT Be on the Marketing Site

- **Implementation details** (Wyoming port numbers, MCP JSON-RPC spec, bearer token lengths) — these belong in docs, not marketing
- **The word "federated" or "federalist"** — founder directive: use "peer compute" and "fleet mesh" in user-facing copy
- **The word "Sovereign"** — founder directive: user-facing copy never uses this word; a machine is named by its onboarding name
- **Pricing for Halbert Pro** — the website is for the open-source project; Pro pricing lives on a separate page or the App Store. (Unless the founder wants a pricing section — see open question Q5)
- **The internal variant names** ("sysadmin variant", "home variant") — use user-facing language ("your server", "your home")
- **Roadmap promises** — only ship stops for features that are built or substantially built. The wake word model is in training; don't promise "Hey Halbert" until it works.

---

## 4. Decisions Required from Founder

These must be answered before the website AI begins build:

| ID | Question | Options | Recommendation |
|---|---|---|---|
| **Q1** | Which messaging option? | A (one Halbert, many bodies), B (two doors), C (growth story), D (lead with home) | **C** (growth story) — most emotionally compelling, preserves existing investment |
| **Q2** | Does the thesis stop change? | Keep "I am the machine" / Change to "I am wherever I live" / Other | If A/C/D: change. If B: keep per-path. |
| **Q3** | Is the MCP "bridge" stop included? | Yes (full stop) / No (footer mention only) / Sub-point of another stop | **Footer mention** — MCP is a power-user feature, not a headline |
| **Q4** | Is the multi-persona stop included? | Yes / No (footer feature) | **No** — it's a feature, not a story. Footer or "under the hood" section. |
| **Q5** | Is there a pricing/distribution section? | No (OSS only) / Yes (OSS + Halbert Home free + Halbert Pro $24-29) / Separate page | **Separate page** — the landing page is for the story, not the storefront |
| **Q6** | Does the site mention Home Assistant by name? | Yes (prominent) / Yes (subtle) / No (generic "smart home") | **Yes, prominent** — HA has 500K+ installs; naming it is SEO and community signal |
| **Q7** | Does the site mention the N150 / peer compute hardware? | Yes (specific hardware) / Yes (generic "low-power box") / No | **Generic** — "a small, silent box" is more evocative than "Intel N150" |
| **Q8** | How many stops total? | 6 (current) / 9–10 (curated) / 12–13 (complete) | **9–10** — enough to tell both stories without fatigue |

---

## 5. Design Notes for the Website AI

### 5.1 Visual Treatment for New Stops

The existing stops use "plates" — placeholder app surfaces (`ProactiveEventsPlate`, `VitalsPlate`, `RationalePlate`, `KnowledgePlate`) rendered as warm paper windows with hairlines, status pills, and mono microcopy. New stops need matching plates:

| New stop | Plate content | Visual element |
|---|---|---|
| I live in your home | HA entity list (lights, locks, climate) with status pills | Entity grid, area labels |
| I watch the doors | Frigate event log with camera thumbnails (abstracted) | Event timeline, camera cards |
| I can hear you | Voice waveform with VAD markers, ASR transcript | Animated waveform, transcript lines |
| I know who's talking | Speaker ID card with role badges | Speaker avatar, role pill (admin/guest) |
| I speak up when it matters | Proactive alert card with quiet-hours indicator | Alert card, clock with shaded quiet zone |
| I have a body that sips power | Two-box topology diagram (N150 ↔ Mac Studio) | Network diagram, power draw comparison |
| I'm the bridge | MCP connection diagram (Claude/Cursor → Halbert → machine) | Connection graph |
| I know why your shell is broken | PATH tracer visualization, dotfile tree | Shell config chain, diff view |

### 5.2 Transition Copy

The transitions between the sysadmin and home sections are the hardest copywriting challenge. Some candidates:

- **Option A transition:** "But I don't just live on your computer."
- **Option C transition 1 (machine → voice):** "Then I learned to hear."
- **Option C transition 2 (voice → home):** "Then I moved into the house."
- **Option C transition 3 (home → peer compute):** "I don't need a big brain to live here."
- **Option D transition:** "I also live on your server."

The transitions must feel like the same identity growing, not a product pivoting. The first-person voice is what makes this work — "I learned", "I moved", not "Halbert now supports..."

### 5.3 The Voice Must Not Break

The existing voice rules (from `stops.jsx` header comment) are:
- Halbert speaks in first person as the host machine
- Embodied, not personified — every adjective maps to a number it measured
- Never calls itself an assistant
- Never names a rival
- The foil is always "a chatbot somewhere else"
- Headlines are fixed; everything else is copy

**For the home stops, the voice rule extends:** Halbert speaks in first person as the home. "I watched the front door." "I turned off the lights." "I heard you come in." Every claim maps to a sensor reading, an HA entity state, a camera event. The embodiment is the house, not just the server.

### 5.4 The "you can call me AI" Tagline

The tagline stays. The Al/AI visual pun is the strongest brand asset. The wordmark treatment doesn't change. The tagline works for both sysadmin and home because "AI" is the identity, not the domain.

---

## 6. Feature-to-Website Mapping Summary

| Feature | On current website? | Proposed treatment | Priority |
|---|---|---|---|
| Proactive alerts | Yes (stop 01) | Keep | — |
| Sensors/vitals | Yes (stop 02) | Keep | — |
| Local-first privacy | Yes (stop 03) | Expand (Apple Intelligence, secure layer, secrets) | High |
| Rationale memory | Yes (stop 04) | Keep | — |
| 16K docs RAG | Yes (stop 05) | Keep | — |
| "I am the machine" thesis | Yes (stop 06) | Revise to "I am wherever I live" (if A/C/D) | High |
| Voice pipeline (VAD/ASR/TTS) | No | New stop: "I can hear you" | High |
| Speaker ID / RoleGate | No | New stop: "I know who's talking" | Medium |
| Proactive spoken alerts | No | New stop: "I speak up when it matters" | Medium |
| Home Assistant integration | No | New stop: "I live in your home" | **Critical** |
| Frigate camera intelligence | No | New stop: "I watch the doors" | High |
| Camera privacy gate | No | Sub-point of camera stop | Medium |
| Peer compute (N150 + Mac Studio) | No | New stop: "I have a body that sips power" | High |
| Fleet mesh / multi-session | No | Footer or "under the hood" | Low |
| Apple Intelligence | No | Expand "Local." stop | Medium |
| MCP server | No | Footer mention or "under the hood" | Low |
| Multi-persona | No | Footer feature | Low |
| Dotfile health / safe diffs | No | New stop: "I know why your shell is broken" | Medium |
| Modality intelligence | No | Sub-copy in voice stop | Low |
| Security & trust boundary | No | Expand "Local." stop | Medium |
| Acoustic anomaly detection | No | Sub-point of voice/proactive stop | Low |
| Wake word ("Hey Halbert") | No | **Do not include** (in training, not shipped) | — |

---

## 7. Source Material for the Website AI

| Document | What it's for |
|---|---|
| `marketing/web-v7/src/content/stops.jsx` | Current stop content — the voice, the plates, the structure |
| `marketing/web-v7/src/content/ui.jsx` | Plate components — visual language for app surfaces |
| `marketing/MARKETING-WEBPAGE-PLAN-2026-08-23.md` | Original page structure plan (sysadmin-only, needs extension) |
| `marketing/VISUAL-DESIGN-DIRECTION-2026-08-23.md` | Visual design direction (mid-century modern, light, decided) |
| `marketing/creative-concepts/you-can-call-me-ai.md` | Tagline concept and legal analysis |
| `README.md` | Comprehensive feature list (both sysadmin and home) |
| `documentation/FEATURES.md` | Feature catalog (dated December 2025, needs update) |
| `.handoff/HANDOFF-README-HOME-AUTOMATION.md` | Home automation README section (standalone build) |
| `.handoff/HANDOFF-README-PEER-COMPUTE.md` | Peer compute README section (N150 + Mac Studio) |
| `documentation/legal/OPEN-CORE-AND-DISTRIBUTION-STRATEGY.md` | Product matrix (OSS / Halbert Home / Halbert Pro) |
| `FOUNDER-TODO.md` | Distribution milestones, bundle IDs, pricing |

---

## 8. Open Questions (Non-Blocking for Founder, but Worth Discussing)

1. **Is the website one page or multiple?** The current plan is a single-page scroll. If the home story is substantial, a `/home` route might serve the HA community better than a very long scroll. (Recommendation: single page with Option C flow; add `/home` and `/pro` routes later if needed.)

2. **Should the site link to the GitHub README?** Currently it links to the repo. The README is now comprehensive but sysadmin-leaded. If the website tells the full story, the README becomes the docs entry point, not the marketing entry point.

3. **What's the CTA?** The current CTA is an early-access email form. Once Halbert Home is on the App Store and the OSS core is installable, the CTA should split: "Get the Mac app" / "Self-host (GitHub)" / "Home Assistant setup." This is a post-launch concern.

4. **Does the site need a "for developers" section?** The MCP server, SourcePrep integration, and open-source nature are developer-facing. A small "for developers" footer section could capture this without cluttering the main narrative.

5. **Should the four-level autonomy governance table be on the site?** It's a strong trust signal ("I won't unlock your doors without your voice") and differentiates from cloud AI tools. Could be a sub-element of the home stop.

---

## 9. What to Do Next

1. **Founder reviews this document** and makes the 8 decisions in Section 4
2. **Founder (or this AI) writes a final messaging brief** based on the chosen option, with finalized stop list, headlines, and transition copy
3. **Website AI receives the brief** plus this document and the source material in Section 7
4. **Website AI builds the extended site** in `marketing/web-v7/` (or a new `web-v8/` if the structure changes significantly)
5. **Founder reviews the build** and iterates on copy

The website AI should NOT start building until the founder has answered Q1 (messaging option) and Q2 (thesis stop). Everything else can be decided during build.
