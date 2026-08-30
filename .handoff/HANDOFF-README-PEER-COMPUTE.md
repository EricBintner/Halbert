# Handoff: README — Minimal Peer-Compute Home Build

**To:** README / docs AI  
**From:** Architecture / product planning  
**Date:** 2026-08-30  
**Status:** Terminology rules + README section outline  

---

## 1. Terminology rules (mandatory)

| Do use | Do NOT use | Why |
|---|---|---|
| "peer compute" | "federalist" | Project lead's instruction |
| "fleet mesh" or "peer mesh" | "federated" (in user-facing copy) | Code uses `federation/`, README should use friendlier product language |
| "Sovereign Self, Shared Commons" | — | The architecture's user-facing framing |
| "compute host" | — | The powerful Mac Studio / Linux GPU box |
| "home node" or "satellite node" | — | The N150 / low-power box |
| "offload" | — | Natural verb for sending inference to another machine |
| "pair" / "paired" | — | Natural for the one-click setup |

In code snippets and API paths, the word `federation` may still appear because the package is named `federation/`. In prose, avoid it.

---

## 2. Where it fits in README.md

This is a new section placed **after** the standalone Home Automation section. It explains the optional, richer setup where the N150 offloads heavy thinking to the Mac Studio.

Title suggestion: `### Minimal Home Build with a Desktop Brain` or `### Home Build with Peer Compute`.

---

## 3. Lead paragraph

> Not every home server can run a 14B model. With peer compute, a small, silent N150 box can hand off complex reasoning to your Mac Studio or Linux GPU box while keeping Home Assistant and your home identity local. The N150 stays private, always-on, and low power; the desktop adds its GPU only when it is awake.

---

## 4. Suggested section body

### 4.1 The two-box idea

- **Home node** (N150): Home Assistant, Halbert home identity, voice, secure model, memory.
- **Compute host** (Mac Studio / Linux desktop): 14B–70B models, batch summaries, optional vision.
- They talk over your LAN or Tailscale.

### 4.2 Why this matters

- **Always-on without always-on power draw.** A Mac Studio idling all day wastes energy. The N150 sips power.
- **Private.** All requests stay on your network. No cloud.
- **Resilient.** If the desktop is asleep, the N150 falls back to a small local model or template thoughts.

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

secure_model:
  provider: ollama
  url: "http://localhost:11434"
  model: qwen2.5:3b
```

Pair the two in the fleet settings, or enter the Mac Studio IP/hostname manually if on Tailscale.

### 4.4 What the desktop handles

- General chat and specialist reasoning
- Optional vision analysis
- Batch summaries and sleep consolidation

### 4.5 What stays on the home node

- Home Assistant state, WebSocket events, entity tracking
- Voice wake-word, ASR, TTS
- `secure_model` — secrets, tokens, camera frames never leave the box
- Persona memory and embeddings

### 4.6 Security

- Every cross-machine request uses a per-peer bearer token.
- The compute host redacts responses before sending them back.
- The home node cannot invoke dangerous tools on the desktop. Only a restricted allowlist is available.
- `secure_model` never offloads. It is architecturally local-only.

---

## 5. Diagram to include

```
┌─────────────────────────────┐            ┌──────────────────────────────┐
│  N150 / Home Node           │  bearer    │  Mac Studio / Compute Host   │
│  ├─ Home Assistant :8123    │  token     │  ├─ Ollama / MLX / Apple     │
│  ├─ Halbert (home) :8001    │  over      │  │   Intelligence             │
│  ├─ 3B secure model         │  Tailscale │  ├─ Compute broker           │
│  └─ Wyoming :10400          │  or LAN    │  └─ Peer service :8000       │
└─────────────────────────────┘            └──────────────────────────────┘
           ↑
    voice satellite / iPad
```

---

## 6. Notes for the README AI

- Keep the **standalone** section before this one. This is an optional upgrade.
- Use `## Home Automation` as the parent heading, with `### Standalone Home Server` and `### Home Server with Peer Compute` as subsections.
- Do not list all the federation implementation steps. The README is a user overview, not a build manual.
- Reference `documentation/design/home-automation.md` (or create it later) for the deep-dive guide.
- Match the existing README tone: concrete, confident, privacy-first.
