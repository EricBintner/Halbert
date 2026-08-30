# Handoff: N150 Halbert Light Stack Install

**To:** Hardware-build AI / install AI  
**From:** Architecture / product planning  
**Date:** 2026-08-30  
**Status:** Install instructions for N150 home server  

---

## 1. Goal

Install a **light Halbert variant** on the N150 that:
- Talks to Home Assistant on the same box
- Uses a small local model only as a fallback
- Offloads normal chat and reasoning to the Mac Studio

This is not the full `halbert-core` sysadmin install. This is the home-only minimum.

---

## 2. Two possible install shapes

### 2A. Light `halbert[home]` install (preferred)

A future pip extra. Today the scaffolding uses:

```bash
python3 -m venv /opt/halbert
source /opt/halbert/bin/activate
pip install -e halbert_core/  # or halbert[home] when packaged
```

Then the daemon is started with home-only env vars.

### 2B. Two Halbert processes on one box (current reference)

The existing design uses two processes on the N150:
- `halbert` (host identity, dormant) — can be ignored for a pure home box
- `halbert-home` (home identity, active) — the one that matters

Use env-var isolation:

```bash
# host identity (dormant, optional)
HALBERT_DATA_DIR=/var/lib/halbert
HALBERT_CONFIG_DIR=/etc/halbert

# home identity (active)
HALBERT_DATA_DIR=/var/lib/halbert-home
HALBERT_CONFIG_DIR=/etc/halbert-home
HALBERT_PERSONA_ID=home
HALBERT_SCENE_CONTEXT="smart home automation"
HALBERT_PORT=8001
```

---

## 3. What to enable

| Component | Enable? | Why |
|---|---|---|
| `integrations/home_assistant/` | Yes | HA client, event mapper, tools |
| Cognition loop (`advance_turn`) | Yes | It needs to think about the house |
| Memory (`PersonaMemoryStore`) | Yes | Episodic memory for the home |
| Wyoming voice server | Yes | `HALBERT_WYOMING_ENABLED=1`, default port `10400` |
| Dashboard | Yes | Web chat at `http://n150.tailnet:8001` |
| `config/` subsystem (dotfile watcher) | No | Replaced by HA state |
| `discovery/` hardware scanners | No | The house is the body, not the CPU |
| `rag/` corpus | No | Linux docs are irrelevant |
| `proactive/` psutil anomaly | Optional | Can use HA sensor anomaly later |
| SourcePrep | Optional | For HA YAML awareness; can defer |
| ChromaDB | Optional | Only if SourcePrep is used |

---

## 4. Default models

| Slot | Default on N150 | Notes |
|---|---|---|
| `chat_model` | `peer://mac-studio.tailnet:8000` | Offload to Mac Studio |
| `specialist_model` | `peer://mac-studio.tailnet:8000` | Offload to Mac Studio |
| `vision_model` | `peer://mac-studio.tailnet:8000` if peer advertises vision | Optional |
| `secure_model` | `local` only, never peer | Must stay on-box for secrets |
| Fallback (peer offline) | `SmolLM3 3B` or template thoughts | 3B is the light target |

Ollama on the N150 is optional. It only needs a 3B fallback. Main inference goes to the Mac Studio.

---

## 5. Data isolation

Use separate data directories for the home instance:

```bash
/etc/halbert-home/being.yml
/var/lib/halbert-home/halbert.sqlite
/var/lib/halbert-home/memory/
```

This prevents lock collision with any host identity and lets you back up the home instance independently.

---

## 6. Tailscale before pairing

1. Install and authenticate Tailscale on the N150.
2. Note the N150 Tailscale name, e.g. `n150.tailnet.ts.net`.
3. The Mac Studio must also be authenticated to the same Tailnet.
4. Configure Tailscale to allow LAN access or at least subnet routes so HA and the Mac Studio see each other.

---

## 7. First-boot config

Minimal `being.yml` for the home instance:

```yaml
instance_id: home
persona_id: home
voice: first_person
purpose: "I am the home. I manage comfort, security, and energy."
ha_url: "http://localhost:8123"
ha_token: "${HA_LONG_LIVED_TOKEN}"  # set in env, not checked in
archetype_id: steward
sourceprep_project_id: ha-config
chat_model:
  provider: peer
  url: "http://mac-studio.tailnet.ts.net:8000"
specialist_model:
  provider: peer
  url: "http://mac-studio.tailnet.ts.net:8000"
secure_model:
  provider: ollama
  url: "http://localhost:11434"
  model: qwen2.5:3b
```

The next handoff (`HANDOFF-N150-PEER-OFFLOAD.md`) explains the pairing and routing.

---

## 8. Verification steps

- [ ] `halbert ask "What is the front door state?"` should query HA
- [ ] `halbert ask "Turn off the living room lights"` should call `light.turn_off`
- [ ] With Mac Studio offline, the 3B local fallback answers (or uses template thoughts)
- [ ] Wyoming server responds on `n150.tailnet.ts.net:10400`
- [ ] Dashboard reachable at `http://n150.tailnet.ts.net:8001`
