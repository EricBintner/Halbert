# GitHub Citations: Screen Capture Patterns for AI Assistants

**Date:** 2026-08-27
**Purpose:** Reference projects for Halbert's screen capture foundation. Documented so future work can build on these patterns.

---

## AI Agent Vision (Closest to Halbert's Use Case)

### LocalEyes
- **URL:** https://github.com/NoPainNullGain/LocalEyes
- **Stack:** Python, MSS, Ollama
- **What it does:** Gives text-only LLMs in Claude Code working eyes via a local Ollama vision model. 100% local, no cloud.
- **Pattern to borrow:** "Model looks itself" agentic mode — `python vision.py screen` captures the display and the model decides when it needs visual context mid-workflow. This is exactly our agent-callable `capture_screenshot` tool (Phase 3).
- **Relevance:** High. Same architecture: local Ollama vision model, MSS capture, agent-initiated capture.

### agent-eyes-mcp
- **URL:** https://github.com/huangzhixin0420/agent-eyes-mcp
- **Stack:** Node.js, MCP server, OpenAI/Anthropic/Gemini/Ollama
- **What it does:** MCP server exposing a `describe_image` tool. Sends image to VLM, returns text description. Image never enters the text model's context.
- **Pattern to borrow:** "VLM does the seeing, text model reads the answer" — an alternative to attaching images directly to the LLM context. Useful when the main chat model doesn't support image inputs. A separate vision call returns a text description that gets injected as an observation.
- **Relevance:** Medium. Halbert's current architecture attaches images directly to the vision model's context, but this pattern is a fallback for text-only chat models.

### eyes-mcp
- **URL:** https://github.com/JamesbbBriz/eyes-mcp
- **Stack:** Python, llama.cpp, RapidOCR (ONNX), MCP
- **What it does:** Two tools: `analyze_image` (VLM via llama.cpp) and `ocr_image` (RapidOCR, ~20MB model). Local vision for coding agents.
- **Pattern to borrow:** Separate OCR from vision understanding. Terminal output, logs, and config files are text — OCR is faster and more accurate than asking a VLM to read them. A `capture_and_ocr` tool alongside `capture_screenshot` would serve sysadmin use cases better. RapidOCR is ~20MB, runs on CPU, no GPU needed.
- **Pattern to borrow:** Lifecycle follows the agent — VLM server spawns when MCP starts, shuts down when agent exits. No orphan processes.
- **Relevance:** High. The OCR-vs-vision split is directly applicable to Halbert's sysadmin domain.

### Peekaboo
- **URL:** https://github.com/mmrech/Peekaboo
- **Stack:** Python, macOS `screencapture` CLI, Ollama/GPT-4/Claude
- **What it does:** macOS CLI + MCP server. Captures screenshots of specific applications or windows, not just full screen.
- **Pattern to borrow:** Per-window and per-application capture. On macOS: `screencapture -l<windowid>` captures a specific window. "Capture the Terminal window" is more useful than "capture everything" for sysadmin tasks. Also lists windows/apps for the agent to choose from.
- **Relevance:** Medium. Per-window capture is a refinement on full-screen capture, not a foundation requirement. But the macOS `screencapture -l` approach is simpler than MSS for window-specific capture.

### agent-vision-toolkit
- **URL:** https://github.com/Anionex/agent-vision-toolkit
- **Stack:** Python, CLI tools, MCP, multiple agent integrations
- **What it does:** Vision toolkit for text-only coding agents. Image Q&A, long-screenshot OCR, frontend UI restoration, GUI automation.
- **Pattern to borrow:** "An agent's vision capability doesn't have to live in the model — it can live in the harness." This validates Halbert's architecture: the `vision_model` slot is harness-level vision, separate from the chat model. The agent calls vision tools; the harness does the seeing.
- **Relevance:** Medium. Architectural validation more than implementation reference.

---

## Tauri-Specific (Same Stack as Halbert)

### quickshotter
- **URL:** https://github.com/ChefJulio/quickshotter
- **Stack:** Tauri 2, Rust, React, TypeScript
- **What it does:** System tray screenshot + screen recording tool. Region/fullscreen/window capture, annotation editor, OCR, GIF/MP4 recording.
- **Key crates:** `xcap` (cross-platform capture), `arboard` (clipboard), `image` (encoding)
- **Pattern to borrow:** The `xcap` Rust crate as an alternative to Python MSS. If capture moves to the Tauri/Rust layer, `xcap` provides native multi-monitor, per-window capture on macOS/Linux/Windows with no Python dependency. Faster than MSS, native APIs.
- **Pattern to borrow:** Region selection overlay — a fullscreen dimmed overlay where the user drags to select a capture region. Implemented as a separate Tauri window.
- **Relevance:** High for architecture decision. Python MSS vs Rust `xcap` is the key choice for where capture lives (backend vs Tauri shell).

### aurora-screenshots
- **URL:** https://github.com/daniacosta-dev/aurora-screenshots
- **Stack:** Tauri v2, React 19, TypeScript, Rust, Tailwind CSS v4, SQLite (rusqlite), Zustand
- **What it does:** Linux screenshot tool with annotation. X11 and Wayland support.
- **Key crates:** `screenshots` (X11 capture), `ashpd` (Wayland via XDG portal), `x11rb` (input grab), `arboard` (clipboard)
- **Pattern to borrow:** Wayland support via `ashpd` (XDG Desktop Portal). Wayland doesn't allow direct screen access — the compositor's picker is the only way. This is the correct Linux approach for Wayland compatibility.
- **Pattern to borrow:** SQLite-backed capture history with metadata (source window, timestamp, dimensions). Could be useful for Halbert's conversation history with images.
- **Relevance:** High for Linux portability. The Wayland/X11 split is essential for proper Linux support.

### snapdoc
- **URL:** https://github.com/dev-truonglx/snapdoc
- **Stack:** Tauri 2, React 19, TypeScript, Rust, Konva (editor), Zustand
- **What it does:** macOS + Windows screenshot, recording, and annotation. Multi-monitor, capture bar UI.
- **Key detail:** macOS uses ScreenCaptureKit (native), Windows uses Windows Graphics Capture.
- **Pattern to borrow:** macOS ScreenCaptureKit integration in Rust. Shows how to structure Rust-side capture commands for the native macOS fast path (our Phase 6). ScreenCaptureKit is hardware-accelerated and supports per-window capture natively.
- **Pattern to borrow:** Multi-monitor UI — every window opens on the display containing the mouse cursor. Relevant if Halbert runs on multi-monitor setups.
- **Relevance:** Medium. macOS ScreenCaptureKit reference for Phase 6.

---

## Python MSS + OpenCV (Our Planned Stack)

### FireScreen
- **URL:** https://github.com/acrocan/FireScreen
- **Stack:** Python, MSS, OpenCV, numpy, tkinter, pyautogui
- **What it does:** Screenshot + screen recording tool with settings UI.
- **Pattern to borrow:** The MSS → numpy → OpenCV JPEG encode pipeline. This is exactly our `screen_capture.py` `_encode_jpeg()` method. Shows it working with configurable quality, cursor overlay, and auto-minimize.
- **Relevance:** High as implementation reference. Minimal, readable code.

### Shadow-play
- **URL:** https://github.com/Issac-Moses/Shadow-play
- **Stack:** Python, MSS, OpenCV, PyQt5, sounddevice
- **What it does:** NVIDIA ShadowPlay-inspired lightweight screen recorder with hotkeys.
- **Pattern to borrow:** Global hotkeys for capture (start/stop/screenshot). GUI + headless modes — the headless mode is relevant since Halbert's capture is backend-only (no capture GUI, the chat UI just triggers it).
- **Pattern to borrow:** Customizable output folders — maps to our `vision_config.yml` settings.
- **Relevance:** Medium. Headless capture pattern and hotkey registration.

### Realtime-Screen-Object-Detection
- **URL:** https://github.com/grebtsew/Realtime-Screen-Object-Detection
- **Stack:** Python, MSS, TensorFlow, PyQt5
- **What it does:** Real-time object detection on screen capture with overlay visualization.
- **Pattern to borrow:** Client/server split — `MssClient` captures frames, `TfServer` does detection, `QtServer` shows overlays. This separation of capture from processing maps to Halbert's backend capture + vision model inference split. Capture and inference are decoupled processes.
- **Relevance:** Low for implementation, medium for architecture reference.

---

## Screenshot Annotation (Future Polish, Not Foundation)

### ksnip
- **URL:** https://github.com/ksnip/ksnip
- **Stack:** Qt/C++, kImageAnnotator, kColorPicker
- **What it does:** Cross-platform screenshot + annotation. Pen, marker, shapes, text, blur, stickers, OCR. Linux (X11/Wayland), Windows, macOS.
- **When to revisit:** If users want to highlight or annotate screenshots before sending to the vision model. Not needed for the foundation — the vision model can understand unannotated screenshots.
- **Relevance:** Low for foundation. Reference for future annotation features.

### ShotQuill
- **URL:** https://github.com/wardmos/shotquill
- **Stack:** macOS native, CLI, MCP server
- **What it does:** Privacy-respecting screenshot + annotation with CLI/MCP support for AI agents.
- **Pattern to borrow:** Blocklist/allowlist redaction — automatically blur or exclude sensitive screen regions (password fields, private messages) before sending to the vision model. This is a privacy feature that maps to our `vision_config.yml` privacy section.
- **Pattern to borrow:** Audit logging for programmatic captures — every agent-initiated capture is logged. Relevant for Halbert's accountability.
- **Relevance:** Medium for privacy patterns. The redaction and audit concepts are directly applicable.

### pypeek
- **URL:** https://github.com/firatkiral/pypeek
- **Stack:** Python, PySide6, FFmpeg
- **What it does:** Cross-platform screen recorder + screenshot with annotation. GIF/MP4 recording, drawing, text, arrows, highlights.
- **When to revisit:** Simple annotation reference if we add a lightweight annotation layer. PySide6 is a possible UI framework for a capture overlay (alternative to the React/Tauri approach).
- **Relevance:** Low for foundation.

---

## MSS Library (Core Dependency)

### python-mss
- **URL:** https://github.com/BoboTiG/python-mss
- **Docs:** https://python-mss.readthedocs.io/
- **What it is:** Ultra-fast cross-platform screenshots in pure Python using ctypes. No dependencies, thread-safe, Python 3.9+.
- **Key API:**
  - `sct.grab(monitor_or_region)` → `ScreenShot` object with `.bgra`, `.rgb`, `.size`
  - `sct.monitors` → list of monitor dicts with `top`, `left`, `width`, `height`
  - Region capture: `sct.grab({"top": y, "left": x, "width": w, "height": h})`
  - PIL bbox style: `sct.grab((left, top, right, bottom))`
  - `mss.tools.to_png(sct_img.rgb, sct_img.size)` → PNG bytes
- **Performance:** ~15-22 FPS full screen on M2 Pro, ~60 FPS for regions. 30x faster than pyautogui/PIL on macOS.
- **Backends:** macOS (CoreGraphics), Linux (XShm/XGetImage/XLib), Windows (GDI). Linux backend is configurable.
- **CLI:** `python -m mss -c TOP,LEFT,WIDTH,HEIGHT -m MONITOR -o OUTPUT --with-cursor`
- **Version:** v10.2.0+ has `--backend` flag and `--with-cursor` support.

---

## Architecture Decision: Python MSS vs Rust xcap

The key decision for Phase 2 is where screen capture lives:

| Factor | Python MSS | Rust xcap (Tauri) |
|--------|-----------|-------------------|
| Dependencies | `pip install mss` (~50KB) | `cargo add xcap` (compiled in) |
| Performance | ~15-22 FPS full screen | Native API, potentially faster |
| Per-window capture | No (full screen or region only) | Yes (native window enumeration) |
| macOS ScreenCaptureKit | No (uses CoreGraphics) | Yes (via xcap on macOS 12.1+) |
| Wayland support | No (X11 only) | Yes (via ashpd/XDG portal) |
| Code location | Python backend (`vision/screen_capture.py`) | Rust Tauri shell (`src-tauri/`) |
| Integration with existing code | Direct (Python backend already handles vision) | Requires Tauri command + IPC |
| Cursor inclusion | v10.2.0+ `--with-cursor` | Native support |

**Recommendation for foundation:** Start with Python MSS (Phase 2 as planned). It's simpler, integrates directly with the existing Python backend, and is sufficient for full-screen capture. Move to Rust `xcap` only if we need per-window capture, Wayland support, or ScreenCaptureKit acceleration — those are Phase 6+ refinements.

The Tauri projects (quickshotter, aurora-screenshots, snapdoc) show that `xcap` is the mature choice for Tauri apps, but adding Rust-side capture is a bigger change than adding a Python module. Keep the foundation thin.
