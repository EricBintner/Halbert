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
| CPU | Intel N150 (Alder Lake-N, 6W TDP) | Sufficient for HA + Halbert Python runtime + voice + memory embeddings. Local LLM inference is not part of the plan; fallback is template thoughts (an optional 3B/4B local fallback only if deliberately installed). |
| RAM | **16 GB DDR5** (single SODIMM) | HA ~1–2 GB; Halbert home-light daemon ~300 MB; Wyoming voice ~300 MB; memory embeddings ~200 MB; SnapRAID nightly peak ~2 GB. No local LLM is planned — all inference offloads to the Mac Studio. 16 GB gives ~10 GB headroom. |
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

**Revised 2026-08-30 per `HANDOFF-HOME-AUTOMATION-SIMPLIFICATION-2026-08-30.md`:** no local LLM is planned for this box (peer offload to the Mac Studio, template thoughts as fallback), and SourcePrep is removed from HA variants entirely. The budget below no longer reserves RAM for a local 7B model or SourcePrep.

Approximate steady-state memory after base load:

| Component | RAM |
|---|---|
| Ubuntu + HA (Docker) | ~2–3 GB |
| Halbert `home-light` daemon + Haloysius | ~300–500 MB |
| Wyoming voice (sherpa-onnx ASR + Piper TTS) | ~300 MB |
| Memory embeddings (haloysius ONNX/Ollama `MemoryEmbedder` — NOT SourcePrep, not offloadable) | ~200 MB |
| SnapRAID (nightly sync, peak) | ~2 GB |
| **Total, default stack (no local LLM, no SourcePrep)** | **~5–6 GB; 16 GB leaves ~10 GB headroom** |

An optional local 3B/4B Q4 fallback model (~2.5 GB via Ollama) may be added deliberately, but it is not part of the target stack.

16 GB is the target for HA + voice + persona memory + SnapRAID headroom, not for local models. Local inference is not part of the HA-node plan; if a fallback model is ever installed, 3B/4B Q4 (~2.5 GB) is the ceiling and 2B-3B is the minimum viable class (see simplification handoff Finding 4).

---

## 5. What the N150 should NOT try to do

Do not plan the N150 for:
- Running 14B+ models
- SourcePrep in any form, including HA-scoped corpora — removed from HA variants entirely (simplification handoff Finding 2)
- RAG of any scale — the HA Halbert answers from live HA state and persona memory, not a documentation index
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
