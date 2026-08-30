# Handoff: N150 ↔ Mac Studio Peer Compute Offload

**To:** Integration AI / install AI  
**From:** Architecture / product planning  
**Date:** 2026-08-30  
**Status:** Integration wiring, built on existing `federation/` scaffold  

---

## 1. One-sentence model

The **N150** is a sovereign home node: it holds its own identity, state, and voice. Heavy LLM inference is **offloaded** to the **Mac Studio** over a bearer-token-authenticated peer link. When the Mac Studio is asleep or unreachable, the N150 falls back to a tiny local model or template thoughts.

---

## 2. Architecture map

```
N150 (Satellite)
├─ Home Assistant           :8123
├─ Halbert daemon           :8001
│  ├─ ComputeRouter ──► PeerProvider ──► Mac Studio :8000
│  ├─ 3B/4B local fallback (optional Ollama)
│  └─ Wyoming voice         :10400
└─ Tailscale IP: n150.tailnet.ts.net

Mac Studio (Compute Host)
├─ Halbert daemon           :8000
├─ Ollama / MLX / Apple Intelligence
├─ ComputeBroker (priority queue)
└─ Tailscale IP: mac-studio.tailnet.ts.net
```

---

## 3. Pairing flow

1. **Mac Studio advertises** a peer service (`_halbert._tcp` on LAN). On Tailscale, skip mDNS and use manual IP.
2. **N150 requests pairing** via `POST /api/peers/pair` on the Mac Studio.
3. **Mac Studio confirms** and issues a per-peer token (PIN or UI confirmation).
4. **N150 stores the token** in its `peers.json` config.
5. **All subsequent compute requests** carry `Authorization: Bearer <token>`.

This reuses the MCP Phase 4b bearer auth. There is only one token system, not a separate "peer token."

---

## 4. Slot routing rules

| Model slot | Can offload to Mac Studio? | Why |
|---|---|---|
| `chat_model` | Yes | General conversation |
| `specialist_model` | Yes | Deep reasoning, the main use case |
| `vision_model` | Only if Mac advertises vision capability | Optional |
| `secure_model` | **No** | Must stay on-box; `secure_model` rejects non-local endpoints |

These rules are enforced in `PeerProvider.can_serve_slot()` and `llm_config._is_local_url()`.

---

## 5. Turn classification and priorities

The `ComputeRouter` tags every request:

| Turn type | Offload? | Priority | Timeout / fallback |
|---|---|---|---|
| `cognitive_monologue` | No | — | Template thoughts locally |
| `interactive_user` | Yes | P2 | 1.5s voice queue timeout, then local fallback |
| `high_value_event` | Yes | P3 | Local heuristic rules |
| `sleep_consolidation` | Yes | P3 batch | Deferred until Mac Studio idle |

**Important:** cognitive monologue never offloads. If the Mac Studio sleeps and 200 monologue turns queue up, they are **not** replayed on wake. They fallback to local template thoughts.

---

## 6. What runs where

### On the N150 (local)
- HA state, WebSocket events, entity trackers
- Voice wake-word, ASR, TTS, barge-in
- `secure_model` (secrets, tokens, camera frames)
- Template thoughts when peer is offline
- Persona memory and embeddings

### On the Mac Studio (offloaded)
- `chat_model` and `specialist_model` inference
- Vision analysis (if enabled)
- SourcePrep-heavy retrieval (if used)
- Batch summaries and sleep consolidation

---

## 7. Security boundary

Every response that leaves the Mac Studio toward the N150 passes through `mcp_response()` and `redact_text()`. The N150 cannot instruct the Mac Studio to:
- Read `~/.ssh/id_rsa`
- Run `run_scanner` or `approve_proposal`
- Read arbitrary files outside the peer tool allowlist

The peer prompt tool set is restricted. See `federation/tool_allowlist.py`.

---

## 8. mDNS vs Tailscale

- **LAN**: mDNS auto-discovery works. TXT record advertises `role=compute_provider`, `compute_backends=ollama,apple_foundation`, `api_port=8000`.
- **Tailscale**: mDNS does **not** cross Tailscale without an mDNS reflector. Use manual IP/hostname entry in the pairing UI.
- **Travel / remote Mac**: if the Mac is not on the same LAN or Tailscale, pairing fails. The N150 falls back to local 3B.

---

## 9. Config snippet for N150

```yaml
# /etc/halbert-home/being.yml
chat_model:
  provider: peer
  url: "http://mac-studio.tailnet.ts.net:8000/api/compute/v1"
  token_env: HALBERT_MACSTUDIO_TOKEN

specialist_model:
  provider: peer
  url: "http://mac-studio.tailnet.ts.net:8000/api/compute/v1"
  token_env: HALBERT_MACSTUDIO_TOKEN

secure_model:
  provider: ollama
  url: "http://localhost:11434"
  model: qwen2.5:3b
```

The token is created at pairing time and stored as `HALBERT_MACSTUDIO_TOKEN` in the N150 systemd unit or a dotenv file.

---

## 10. Fallback behavior

If the Mac Studio is unreachable:
1. `chat_model` and `specialist_model` fall back to `ollama` 3B/4B if installed locally.
2. If no local model, use **template thoughts** for the cognition loop.
3. `secure_model` is unaffected — it was always local.
4. Voice requests fall back within 1.5s so the user does not wait.

---

## 11. Files that matter

- `halbert_core/halbert_core/federation/` — peer auth, compute broker, discovery, tool allowlist
- `halbert_core/halbert_core/model/providers/peer.py` — `PeerProvider` implementation
- `halbert_core/halbert_core/model/tier_router.py` — fallback chains and health probes
- `halbert_core/halbert_core/federation/README.md` — full scaffold overview

---

## 12. Integration checklist

- [ ] Both machines on the same Tailnet
- [ ] Mac Studio Halbert running and port 8000 reachable
- [ ] N150 can `curl http://mac-studio.tailnet.ts.net:8000/api/health`
- [ ] Pairing handshake succeeds and token stored
- [ ] Test offload: `chat_model` response comes from Mac Studio
- [ ] Test offline fallback: disconnect Mac, response comes from local 3B or template
- [ ] Test `secure_model`: stays on `localhost:11434`, never routes to peer
