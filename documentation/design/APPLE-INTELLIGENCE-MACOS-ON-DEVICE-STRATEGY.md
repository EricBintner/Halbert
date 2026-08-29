# Apple Intelligence & On-Device Foundation Models: macOS Strategy & Integration Plan

**Date:** 2026-08-29  
**Status:** Architectural Specification & Implementation Roadmap  
**Target Platforms:** macOS 26 / 27 (macOS 15.1+ Sequoia & next-gen Darwin) on Apple Silicon (M1+)  
**Reads With:**
* [`documentation/design/macos-strategy.md`](file:///Volumes/4TB-BAD/Halbert/documentation/design/macos-strategy.md)
* [`.handoff/HANDOFF-LOW-POWER-HARDWARE-TIERS-AND-EDGE-CASES-2026-08-29.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/HANDOFF-LOW-POWER-HARDWARE-TIERS-AND-EDGE-CASES-2026-08-29.md)
* [`halbert_core/halbert_core/model/hardware_detector.py`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/model/hardware_detector.py)

---

## 1. Executive Summary

Apple's **FoundationModels framework** (`import FoundationModels`), introduced and expanded across macOS 15.1+, macOS 26, and macOS 27, provides native developer access to the on-device language models powering Apple Intelligence.

Running natively on the **Apple Neural Engine (ANE)** and unified memory of M1+ Apple Silicon Macs, Apple Intelligence provides an unprecedented zero-setup, zero-download, privacy-preserving LLM foundation. 

This document defines how Halbert leverages Apple Intelligence as the **default on-device model provider for macOS**, eliminating the initial barrier of downloading multi-gigabyte GGUF models or configuring external daemons.

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                     HALBERT ON-DEVICE AI ON APPLE SILICON (M1+)                       │
├────────────────────────────────────────────┬───────────────────────────────────────────┤
│    1. APPLE INTELLIGENCE (Default Zero-Setup)│         2. APPLE MLX (Power User)         │
│ • Framework: FoundationModels / Swift API  │ • Framework: Apple MLX (mlx-lm / Metal)   │
│ • Model: Built-in OS Foundation Model      │ • Model: Custom HuggingFace weights       │
│ • Storage: 0 MB download (pre-installed)   │ • Storage: User-downloaded 4-bit / 8-bit  │
│ • Compute: Apple Neural Engine (ANE)       │ • Compute: Metal GPU + Unified Memory     │
│ • Role: Default secure_model & chat_model  │ • Role: High-tier specialist & reasoning  │
└────────────────────────────────────────────┴───────────────────────────────────────────┘
```

---

## 2. Technical Capabilities of Apple's FoundationModels Framework

The `FoundationModels` framework provides a direct Swift interface to the on-device system model:

### Core Framework APIs
1. **`SystemLanguageModel`**: The root interface to the on-device model.
   ```swift
   import FoundationModels

   // Availability Guard
   guard SystemLanguageModel.default.availability == .available else {
       // Fall back to MLX, Ollama, or Cloud
       return
   }
   ```
2. **`LanguageModelSession`**: Manages conversational state, system instructions, and tool calling.
   ```swift
   let session = LanguageModelSession(
       instructions: "You are Halbert, a sovereign system administrator."
   )
   ```
3. **Streaming & Text Generation**:
   * Single response: `try await session.respond(to: prompt)`
   * Real-time streaming: `for try await chunk in session.streamRespond(to: prompt)`
4. **Native Tool Calling (`Tool` Protocol)**:
   * The model supports declarative tool schemas and automatically outputs structured tool call invocations.
5. **Guaranteed Structured Output (`@Generable`)**:
   * Uses Swift macro-defined structs to guarantee JSON schema compliance without parsing hallucinated syntax.
6. **Multimodal Support**:
   * Accepts visual attachments (screenshots, system diagnostics images) for native on-device visual reasoning.

---

## 3. The "Zero-Setup" User Experience on Mac

Currently, a fresh install of any local AI software requires the user to:
1. Install an external runtime (Ollama, llama.cpp, LM Studio).
2. Download a 3GB–5GB model over the internet (`ollama pull <model>`).
3. Maintain background daemon lifecycles.

### Halbert's Native Mac Experience:
On an Apple Silicon Mac (M1+ with Apple Intelligence enabled):
1. **Instant First-Run**: Halbert boots and detects macOS + Apple Silicon with `SystemLanguageModel.default.availability == .available`.
2. **Zero Download Footprint**: The `secure_model` slot and default `chat_model` are immediately active using the pre-installed OS Foundation Model.
3. **Hardware Acceleration**: Inference executes on the Apple Neural Engine with virtually zero impact on CPU/GPU thermals and minimal battery drain.
4. **Cloud / MLX Optionality**: The user can optionally attach cloud API keys (OpenAI / Anthropic) or point to custom MLX / Ollama models in Settings, but nothing is required to get a fully working sovereign agent out of the box.

---

## 4. Architectural Integration Options

Halbert's core is Python + FastAPI with a Tauri v2 desktop shell. We evaluate three integration patterns:

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                           INTEGRATION TOPOLOGY OPTIONS                                 │
├────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                        │
│  [ Option A: Native Tauri Swift Bridge / Sidecar ] (RECOMMENDED)                       │
│  ┌─────────────────────────┐          HTTP / Loopback          ┌────────────────────┐  │
│  │ Halbert Python Backend  │ ◀───────────────────────────────▶ │ Swift ANE Sidecar  │  │
│  │ (client.py OpenAI wire) │   http://127.0.0.1:11435/v1       │ (FoundationModels) │  │
│  └─────────────────────────┘                                   └────────────────────┘  │
│                                                                                        │
│  [ Option B: macOS Built-in `fm` CLI / REST Server ]                                   │
│  ┌─────────────────────────┐         Standard CLI Pipe         ┌────────────────────┐  │
│  │ Halbert Python Backend  │ ◀───────────────────────────────▶ │  /usr/bin/fm exec  │  │
│  └─────────────────────────┘                                   └────────────────────┘  │
│                                                                                        │
│  [ Option C: PyObjC / C-FFI Direct Bridge ]                                            │
│  ┌──────────────────────────────────────────────────────────────────────────────────┐  │
│  │ Halbert Python Backend ──▶ PyObjC C-Bridge ──▶ FoundationModels.framework        │  │
│  └──────────────────────────────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

### Option A: Native Swift Sidecar (`halbert-foundation-bridge`) — **Recommended**
* **Mechanism:** A tiny Swift binary bundled inside the Tauri macOS application bundle (`Halbert.app/Contents/MacOS/halbert-foundation-bridge`).
* **Protocol:** Spins up a lightweight localhost server on loopback (`http://127.0.0.1:11435/v1`) implementing standard OpenAI-compatible `/v1/chat/completions` (supporting text, streaming, and tool calling) mapped to `SystemLanguageModel` / `LanguageModelSession`.
* **Benefits:**
  * Zero Python C-extension compilation issues.
  * Reuses Halbert's existing `_call_openai_compatible()` client logic without modifying backend wire formats.
  * Sandboxed or direct distribution compatible.

### Option B: macOS `fm` CLI / System Service
* **Mechanism:** Newer versions of macOS include the `fm` CLI utility capable of executing prompts and serving completions.
* **Benefits:** Zero additional code bundled; uses OS binaries directly.

---

## 5. Model Slot Routing & Fallback Hierarchy on Apple Silicon

On macOS Apple Silicon, Halbert organizes local model resolution into a 4-tier capability hierarchy:

```
                          ┌───────────────────────────────┐
                          │   macOS Apple Silicon Boot    │
                          └───────────────┬───────────────┘
                                          │
                                          ▼
                   ┌─────────────────────────────────────────────┐
                   │  Is Apple Intelligence Available on Host?   │
                   │  (SystemLanguageModel.availability check)   │
                   └──────────────┬───────────────┬──────────────┘
                                  │               │
                            YES   │               │   NO (Disabled / Ineligible)
                                  ▼               ▼
          ┌─────────────────────────────┐   ┌─────────────────────────────┐
          │ TIER 1: Apple Intelligence  │   │ TIER 2: Apple MLX / Ollama  │
          │ • Zero setup / ANE powered  │   │ • Local GPU Metal inference │
          │ • Auto-assign secure_model  │   │ • Custom GGUF / MLX models  │
          └─────────────────────────────┘   └─────────────────────────────┘
                                  │               │
                                  └───────┬───────┘
                                          │
                                          ▼
                   ┌─────────────────────────────────────────────┐
                   │ TIER 3: Cloud Frontier Burst (Optional)     │
                   │ • User-configured OpenAI / Anthropic / Groq │
                   │ • Assigned to chat_model / specialist_model │
                   └─────────────────────────────────────────────┘
```

### Slot Assignments on macOS:
1. **`secure_model` (Mandatory Local):**
   * **Default:** Apple Intelligence (`apple-foundation` endpoint via local bridge).
   * **Fallback:** Local MLX or Local Ollama.
   * **Guarantee:** Private data, credentials, and cognitive monologue never leave the device.
2. **`chat_model` (General Conversation):**
   * **Default:** Apple Intelligence out of the box.
   * **User Override:** Cloud API (Claude 3.5 Sonnet, GPT-4o) or 14B+ local MLX model.
3. **`vision_model` (Screenshot & Visual Diagnostics):**
   * **Default:** Apple Intelligence multimodal session.
   * **User Override:** Cloud VLM or local Qwen-VL.
4. **`specialist_model` (Complex Code Refactoring):**
   * **Default:** Cloud Frontier model or high-parameter local MLX model (e.g. 14B–32B on 32GB+ Macs).

---

## 6. Hardware Detector Updates (`hardware_detector.py`)

To support native Apple Intelligence auto-detection, [`hardware_detector.py`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/model/hardware_detector.py) will incorporate availability probing:

```python
def detect_apple_intelligence_available() -> bool:
    """Check if Apple Intelligence FoundationModels are available on this Mac."""
    if not is_mac_apple_silicon():
        return False
    
    # Check bridge health or macOS FoundationModels availability
    try:
        resp = requests.get("http://127.0.0.1:11435/v1/health", timeout=0.5)
        return resp.status_code == 200
    except Exception:
        pass
    
    # Fallback to checking macOS version (macOS 15.1+ / Darwin 24.1+)
    import platform
    release = platform.release()
    try:
        major = int(release.split(".")[0])
        return major >= 24  # Darwin 24+ = macOS 15+ Sequoia / macOS 26 / 27
    except Exception:
        return False
```

When detected:
* Automatically provisions endpoint `ep_apple_foundation` (`name: "Apple Intelligence (On-Device)"`, `provider: "openai-compatible"`, `url: "http://127.0.0.1:11435"`).
* Pre-sets `secure_model` to point at `ep_apple_foundation`.

---

## 7. Implementation Roadmap for Apple Intelligence Support

### Phase 1: Swift Bridge Prototype (`halbert-foundation-bridge`)
1. Create a lightweight Swift SPM package (`tools/apple_intelligence_bridge`).
2. Implement `LanguageModelSession` wrapper exposing `POST /v1/chat/completions` and `GET /v1/models`.
3. Add `@Tool` schema bridging for Halbert's tool-calling format.

### Phase 2: Tauri Application Bundle Integration
1. Add the compiled Swift bridge as an external binary sidecar in `tauri.conf.json`.
2. Lifecycle management: Tauri starts the bridge on app launch and terminates it on exit.

### Phase 3: Model Config & Hardware Detector Auto-Provisioning
1. Update `llm_config.py` default configuration on Apple Silicon to include `ep_apple_foundation`.
2. Update `@halbert/model-picker` to display the "Apple Intelligence (Built-in)" badge.
3. Update `config_wizard.py` to recognize Apple Intelligence as the zero-setup default.
