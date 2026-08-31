# Handoff: N150 Halbert Light Stack Install

**To:** Hardware-build AI / install AI  
**From:** Architecture / product planning  
**Date:** 2026-08-30  
**Status:** Install instructions for N150 home server  

---

## 1. Goal

Install a **light Halbert variant** on the N150 that:
- Talks to Home Assistant on the same box
- Falls back to deterministic template thoughts when the Mac Studio is asleep (an optional local 3B/4B Ollama fallback may be installed, but is not part of the default install)
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
HALBERT_VARIANT=home-light
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
| SourcePrep | No | Removed from HA variants entirely (simplification Finding 2). No `SOURCEPREP_URL` configured; the retrieval backend is not instantiated. HA YAML awareness comes from live HA state and the event stream. |
| ChromaDB | No | Not used by HA variants. Persona memory (haloysius ONNX/Ollama `MemoryEmbedder` embeddings) is NOT ChromaDB/SourcePrep and remains enabled locally. |

---

## 4. Default models

**Revised 2026-08-30 per `HANDOFF-HOME-AUTOMATION-SIMPLIFICATION-2026-08-30.md`:** `secure_model` is removed from `home`/`home-light` variants — the slot exists only in the sysadmin variant, and sensitive reasoning about this box is done from the workstation's Halbert via the fleet cockpit/MCP path. There is also **no model picker UI** for this node; the settings page shows a single "Compute Peer" field, and the workstation's own picker governs which models serve peer requests.

| Slot | Default on N150 | Notes |
|---|---|---|
| `chat_model` | `peer://mac-studio.tailnet:8000` | Offload to Mac Studio |
| `specialist_model` | `peer://mac-studio.tailnet:8000` | Offload to Mac Studio |
| `vision_model` | `peer://mac-studio.tailnet:8000` if peer advertises vision | Optional |
| Fallback (peer offline) | Template thoughts (default) | A local 3B/4B Q4 is an optional extra, not the target |

Ollama on the N150 is optional and not installed by default. When the peer is asleep, cognition uses template thoughts (`HALBERT_LLM_THOUGHTS=0`); a 3B/4B local fallback may be added deliberately. No 1B-class model is supported (simplification Finding 4).

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
variant: home-light  # gates the home stack: no secure_model, no SourcePrep, Compute Peer UI (simplification handoff Findings 1-3)
persona_id: home
voice: first_person
purpose: "I am the home. I manage comfort, security, and energy."
ha_url: "http://localhost:8123"
ha_token: "${HA_LONG_LIVED_TOKEN}"  # set in env, not checked in
archetype_id: steward
chat_model:
  provider: peer
  url: "http://mac-studio.tailnet.ts.net:8000"
specialist_model:
  provider: peer
  url: "http://mac-studio.tailnet.ts.net:8000"
# secure_model: intentionally absent — sysadmin variant only
# (simplification Finding 1). No sourceprep_project_id / SOURCEPREP_URL:
# SourcePrep is removed from home/home-light variants (Finding 2).
```

The next handoff (`HANDOFF-N150-PEER-OFFLOAD.md`) explains the pairing and routing.

---

## 8. Verification steps

- [ ] Verify the instance variant resolves to `home-light` (`being.yml` `variant:` or `HALBERT_VARIANT` env — backend gating prefers being.yml, see simplification handoff Section 12 / D1)
- [ ] `halbert ask "What is the front door state?"` should query HA
- [ ] `halbert ask "Turn off the living room lights"` should call `light.turn_off`
- [ ] With Mac Studio offline, cognition uses template thoughts (a 3B/4B local fallback may answer instead only if deliberately installed)
- [ ] Verify `secure_model` is not configured and not rendered in the dashboard UI for the home/home-light variant
- [ ] Verify no `SOURCEPREP_URL` is set and the SourcePrep retrieval backend is not instantiated
- [ ] Verify the settings page shows a "Compute Peer" field and does not render the model picker
- [ ] Wyoming server responds on `n150.tailnet.ts.net:10400`
- [ ] Dashboard reachable at `http://n150.tailnet.ts.net:8001`
