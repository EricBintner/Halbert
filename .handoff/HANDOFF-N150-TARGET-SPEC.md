# Handoff: N150 Home Assistant + Halbert Target Spec

**To:** Hardware-build AI (N150 motherboard assembly)  
**From:** Architecture / product planning  
**Date:** 2026-08-30  
**Status:** Ready for procurement  

---

## 1. What this box is

This is a **home server** that runs:
- Home Assistant (primary body of the home)
- Halbert in a **light, home-only** configuration (cognition + HA integration + voice)
- It offloads heavy inference to a **Mac Studio** compute host over Tailscale

It is always-on, silent or near-silent, low power, and network-tethered to the Mac Studio for large-model work.

---

## 2. Hardware target

| Component | Target | Why |
|---|---|---|
| CPU | Intel N150 (Alder Lake-N, 6W TDP) | Sufficient for HA + Halbert Python runtime + light local fallback. Not for LLM inference. |
| RAM | **16 GB DDR5** (single SODIMM) | 7B Q4 is ~5 GB if run locally; HA ~1 GB; Halbert ~300 MB. 8 GB is a hard squeeze. 16 GB gives headroom. |
| Boot + HA storage | 256 GB NVMe or larger | Home Assistant recorder + add-ons. HA with default DB grows fast. |
| Bulk/Optane tier | 375 GB Optane M.2 if available | Second M.2 slot. Optional but historically referenced in this project. |
| NIC | 2.5 GbE on board | Adequate. Tailscale is the transport, not raw throughput. |
| Cooling | Fanless or low-RPM case | It sits in a living space. N150 allows fanless. |
| PSU | 19 V barrel or passive PoE | Match the case. N150 motherboards are usually 12-19 V. |

---

## 3. OS and base platform

- **Ubuntu 24.04 LTS** is the reference platform.
- **Home Assistant** can run as:
  - A Docker container (recommended for this build), or
  - HA OS in a VM, or
  - HA Core in a venv
- The Halbert daemon will run as a **separate systemd service** (not inside HA).

The N150 is x86. The existing N150 sizing in the project assumed x86, not ARM, so do not size this like a Raspberry Pi.

---

## 4. Resource budget after OS + HA

Approximate steady-state memory after base load:

| Component | RAM |
|---|---|
| Ubuntu + HA (Docker) | ~1.0–1.5 GB |
| Halbert daemon + Haloysius | ~300–500 MB |
| `sentence-transformers` / embeddings | ~90 MB model (defer to Ollama if possible) |
| Ollama 7B Q4 (if local) | ~5 GB |
| SourcePrep (optional, off-loadable) | ~200 MB |
| **Total with local 7B** | **~7 GB** |
| **Total without local 7B** | **~2 GB** |

16 GB is the target. With 8 GB, local 7B is not viable and even 3B/4B is tight. Offload to the Mac Studio makes 8 GB acceptable but 16 GB is safer.

---

## 5. What the N150 should NOT try to do

Do not plan the N150 for:
- Running 14B+ models
- SourcePrep AST indexing of large codebases
- RAG with 16K document corpus
- Frigate object-detection inference
- Video decoding / camera AI

Those belong on the Mac Studio or a separate GPU box.

---

## 6. Network assumptions

- The N150 and the Mac Studio are on the **same LAN** or joined via **Tailscale**.
- mDNS auto-discovery is **LAN-only**. Over Tailscale, the Mac Studio IP/hostname must be entered manually.
- Tailscale is the practical remote-access path. Configure it before Halbert pairing.

---

## 7. Out-of-scope for you

This handoff is the **hardware target**. The next two handoffs cover:
- `HANDOFF-N150-HALBERT-STACK.md` — what software to install on this box
- `HANDOFF-N150-PEER-OFFLOAD.md` — how it connects to the Mac Studio for compute

---

## 8. Coordination checklist

- [ ] Confirm 16 GB RAM can fit in the selected N150 board
- [ ] Confirm a 256 GB+ NVMe is in the BOM
- [ ] Confirm case has a quiet or passive thermal solution
- [ ] Confirm 2.5 GbE or at least Gigabit Ethernet is available
- [ ] Note whether the board has one or two M.2 slots (affects Optane decision)
- [ ] Share final BOM before ordering so the install handoff can be reconciled
