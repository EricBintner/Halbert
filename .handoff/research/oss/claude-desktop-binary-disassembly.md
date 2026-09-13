# macOS Claude.app Binary Disassembly & Reverse-Engineering

**Document Path**: `.handoff/research/oss/claude-desktop-binary-disassembly.md`  
**Date**: 2026-09-12  
**Target Binary**: `/Applications/Claude.app/Contents/Resources/app.asar` (44.2 MB)  
**Application Version**: `1.52386.3` (Build `24F74`, Xcode `16F6`)  
**Package Date**: September 11, 2026

---

## 1. Inspection Methodology

The production Electron archive (`app.asar`) installed in the local system's `/Applications/Claude.app` was inspected via `asar list` and decompiled chunk analysis. This inspection exposed the underlying runtime mechanisms powering Anthropic's official desktop client.

---

## 2. Key Architectural Discoveries

### 2.1 Native Swift Computer Use Bridge (`@ant/claude-swift`)
Located in `node_modules/@ant/claude-swift/`:
- **Compiled Binaries**:
  - `build/Release/computer_use.node`
  - `build/Release/swift_addon.node`
- **Mechanism**:
  Anthropic completely bypassed AppleScript (`osascript`) for Computer Use on macOS. Instead, they wrote a native Swift library interfacing directly with macOS frameworks and compiled it into a Node-API (`.node`) C++ addon.
- **Underlying macOS Frameworks Used**:
  1. **Quartz Display Services** (`CoreGraphics`): Screen capture via `CGDisplayStream` and `CGWindowListCreateImage` allows real-time, high-frame-rate display capture with hardware acceleration.
  2. **Event Injection** (`CGEvent`): Simulates mouse clicks, movements, drags, and keystrokes directly through Quartz event taps (`CGEventCreateMouseEvent`, `CGEventPost`).
  3. **Accessibility Hierarchy** (`ApplicationServices` / `HIServices`): Uses `AXUIElementCopyAttributeValue` to inspect the UI element hierarchy under the cursor, reading accessibility labels, roles, and focus states.
- **Security Fencing**:
  Calls are intercepted by macOS TCC (Transparency, Consent, and Control). Claude Desktop checks for `kAXTrustedCheckOptionPrompt` and explicitly verifies Screen Recording and Accessibility entitlements at launch.

---

### 2.2 Dedicated PTY Host Worker (`pty-host/ptyHostWorker.js`)
Located in `.vite/build/pty-host/ptyHostWorker.js`:
- **Threading Model**:
  Terminal sessions are not spawned directly from the Electron main process or browser windows. Instead, Anthropic uses an isolated background Node.js worker thread (`ptyHostWorker.js`).
- **Terminal Backend**:
  Uses `node-pty` with native Mach-O prebuilds (`node-pty/prebuilds/darwin-arm64/pty.node`).
- **Performance Advantage**:
  High-throughput terminal output (such as `npm install`, test suites, or compilation logs emitting thousands of lines per second) is ingested and buffered off the main thread. This completely eliminates UI freezing and maintains 60 FPS animation in the chat window.

---

### 2.3 Command Approval Dialog Architecture (`local_exec_consent`)
Located in:
- `.vite/build/localExecConsent.js`
- `.vite/renderer/local_exec_consent/localExecConsent.html`
- `.vite/renderer/local_exec_consent/assets/main-DInLOA-Y.js`

- **Implementation**:
  When a shell command or file modification requires user approval under Manual or Ask permission mode, Electron spawns a dedicated lightweight modal window rather than rendering inline HTML in the chat DOM.
- **Security Isolation**:
  The consent window operates in an isolated renderer context. Command text, arguments, working directory, and risk classifications are passed via secure IPC, preventing compromised webviews from injecting clickjacking overlays.

---

### 2.4 Pre-Packaged Bundled Skills (`resources/bundled-skills/`)
Located in `/resources/bundled-skills/`:
- Rather than leaving skill prompt files loose on disk, Anthropic packages production skills into atomic `.skill` archives with a unified `manifest.json`:
  - `frontend-design.skill`
  - `docx.skill`
  - `pdf.skill` / `pdf-reading.skill`
  - `pptx.skill`
  - `xlsx.skill`
- **Format**:
  A `.skill` bundle contains the system prompt extensions, tool schema definitions, validation rules, and bundled helper scripts. The manifest registers versioning, required capabilities, and model compatibility flags.

---

### 2.5 Integrated Local MCP Servers (`/resources/`)
Claude Desktop ships with embedded Model Context Protocol (MCP) servers:
1. **GitHub MCP Server** (`/resources/github-mcp/github-mcp-server`): Precompiled binary managing GitHub issues, PRs, and branch states.
2. **Office 365 MCP Server** (`/resources/office365-mcp/`):
   - `office365-mcp-stdio.mjs`
   - Native MSAL runtime: `libmsalruntime_arm64.dylib` and `msal-node-runtime.node`
   - PDF extraction sub-process: `pdfExtractorProcess.mjs`
