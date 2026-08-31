# Handoff: README — Minimal Peer-Compute Home Build

**To:** README / docs AI  
**From:** Architecture / product planning  
**Date:** 2026-08-30  
**Status:** Terminology rules + README section outline  
**Revised 2026-08-30 per `HANDOFF-HOME-AUTOMATION-SIMPLIFICATION-2026-08-30.md`:** peer compute is the recommended HA build, not an optional upgrade. Home variants have no `secure_model` (that slot is sysadmin-only), no SourcePrep, and no model picker — a single "Compute Peer" setting instead. Apple Intelligence is never a peer backend; peer requests on a Mac route to Ollama.

---

## 1. Terminology rules (mandatory)

| Do use | Do NOT use | Why |
|---|---|---|
| "peer compute" | "federalist" | Project lead's instruction |
| "fleet mesh" or "peer mesh" | "federated" (in user-facing copy) | Code uses `federation/`, README should use friendlier product language |
| the computer's onboarding name (`ai_name`) | "Sovereign", raw hostnames | Founder directive: user-facing copy never uses the word "Sovereign" — a machine is named by the name the user chose in onboarding, never a product word or a raw hostname |
| "compute host" | — | The powerful Mac Studio / Linux GPU box |
| "home node" or "satellite node" | — | The N150 / low-power box |
| "offload" | — | Natural verb for sending inference to another machine |
| "pair" / "paired" | — | Natural for the one-click setup |

In code snippets and API paths, the word `federation` may still appear because the package is named `federation/`. In prose, avoid it.

---

## 2. Where it fits in README.md

This is a new section placed **after** the standalone Home Automation section. It explains the recommended setup where the N150 offloads all LLM work to the Mac Studio; the standalone section covers the simpler build without a compute host.

Title suggestion: `### Minimal Home Build with a Desktop Brain` or `### Home Build with Peer Compute`.

---

## 3. Lead paragraph

> Not every home server can run a 14B model. With peer compute, a small, silent N150 box can hand off complex reasoning to your Mac Studio or Linux GPU box while keeping Home Assistant and your home identity local. The N150 stays private, always-on, and low power; the desktop adds its GPU only when it is awake.

---

## 4. Suggested section body

### 4.1 The two-box idea

- **Home node** (N150): Home Assistant, Halbert home identity, voice, persona memory.
- **Compute host** (Mac Studio / Linux desktop): Ollama 7B–14B models (a Linux GPU box can serve larger), batch summaries, optional vision.
- They talk over your LAN or Tailscale.

### 4.2 Why this matters

- **Always-on without always-on power draw.** A Mac Studio idling all day wastes energy. The N150 sips power.
- **Private.** All requests stay on your network. No cloud.
- **Resilient.** If the desktop is asleep, the N150 answers instantly with template thoughts — no LLM needed. Hosts with 8 GB+ RAM may optionally keep a small 3B/4B local fallback.

### 4.3 Quick setup

On the **compute host** (Mac Studio):

```bash
halbert dashboard-serve --port 8000
# Enable peer compute in the fleet / peers settings
```

On the **home node** (N150):

```yaml
# /etc/halbert-home/being.yml
chat_model:
  provider: peer
  url: "http://mac-studio.tailnet.ts.net:8000/api/compute/v1"

specialist_model:
  provider: peer
  url: "http://mac-studio.tailnet.ts.net:8000/api/compute/v1"
```

Pair the two in the fleet settings, or enter the Mac Studio IP/hostname manually if on Tailscale.

In the home node's settings UI this is a single **Compute Peer** field (hostname:port or Tailscale address) with a Test Connection button. Home variants have no model picker — the compute host's own picker governs which models serve the home node's requests.

### 4.4 What the desktop handles

- General chat and specialist reasoning
- Optional vision analysis
- Batch summaries and sleep consolidation

### 4.5 What stays on the home node

- Home Assistant state, WebSocket events, entity tracking
- Voice wake-word, ASR, TTS
- Credentials — HA tokens and device keys stay inside HA's integration layer; Halbert's LLM sees only tool results, never credentials
- Persona memory and embeddings

### 4.6 Security

- Every cross-machine request uses a per-peer bearer token.
- The compute host redacts responses before sending them back.
- The home node cannot invoke dangerous tools on the desktop. Only a restricted allowlist is available.
- The sysadmin variant's `secure_model` never offloads — it is local-only by rule. Home variants don't configure a `secure_model` at all.

---

## 5. Diagram to include

```
┌─────────────────────────────┐            ┌──────────────────────────────┐
│  N150 / Home Node           │  bearer    │  Mac Studio / Compute Host   │
│  ├─ Home Assistant :8123    │  token     │  ├─ Ollama / vLLM            │
│  ├─ Halbert (home) :8001    │  over      │  ├─ Compute broker           │
│  └─ Wyoming :10400          │  Tailscale │  └─ Peer service :8000       │
└─────────────────────────────┘  or LAN    └──────────────────────────────┘
           ↑
    voice satellite / iPad
```

---

## 6. Notes for the README AI

- Keep the **standalone** section before this one, but present peer compute as the recommended build — the standalone section covers the simpler no-peer setup, not a local-model alternative.
- Use `## Home Automation` as the parent heading, with `### Standalone Home Server` and `### Home Server with Peer Compute` as subsections.
- Do not list all the federation implementation steps. The README is a user overview, not a build manual.
- If Apple Intelligence is mentioned anywhere in final README copy, caption it as local-only to the Mac's own use — it is never a peer compute backend; peer requests on a Mac route to Ollama.
- "Optional vision analysis" is pending the open question of whether Frigate handles all vision for the home node (`HANDOFF-HOME-AUTOMATION-SIMPLIFICATION-2026-08-30.md`, open question 3); be ready to drop it if `vision_model` is removed from home variants.
- Reference `documentation/design/home-automation.md` (or create it later) for the deep-dive guide.
- Match the existing README tone: concrete, confident, privacy-first.
