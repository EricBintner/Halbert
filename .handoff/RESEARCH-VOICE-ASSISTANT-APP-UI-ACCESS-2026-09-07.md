# RESEARCH: Voice Assistant App UI Access — How Halbert Could Interface with Other Apps

**Date:** 2026-09-07
**Author:** Devin session
**Status:** Preliminary research — landscape mapped, opportunities framed, no implementation
**Related:** RESEARCH-UNIFIED-SYSTEM-ONTOLOGY-2026-09-07.md

---

## 0. The Question

> How can Halbert, as a voice assistant, gain access to other apps' UIs
> and interface with them? I understand this is extraordinarily complex,
> but the common use case today is a chat that interfaces with Gemini on
> a phone + Antigravity on a computer as a proprietary link, or OpenClaw
> or various other AI/chat type integrations. I want to research how an
> AI like Halbert can gain access to an app with an MCP or an app with a
> means to communicate with an external. I don't really know what's
> possible and I don't know what I could use it for in this app, but I
> am curious to discover any opportunities.

This document maps the current landscape (as of September 2026) of how
AI agents gain access to and control application UIs, identifies the
architectural patterns that exist, and frames what opportunities exist
for Halbert specifically.

---

## 1. The Three Mechanism Tiers

There are three fundamentally different ways an AI agent can interface
with an application's UI. They are not mutually exclusive — most mature
systems layer them as a fallback chain.

### Tier 1: Structured API / Scripting Bridge (Best — when it exists)

The app exposes a documented programmatic interface. The agent calls
named commands with typed parameters and gets structured responses
back. No vision needed, no coordinate guessing, no screenshots.

| Platform | Mechanism | Maturity |
|----------|-----------|----------|
| macOS | **AppleScript / JXA / Scripting Bridge** — apps with an `.sdef` scripting dictionary expose commands, objects, and properties | Mature (decades old) but app-dependent |
| macOS / iOS | **App Intents framework** — Swift macros that expose app actions to Siri, Shortcuts, Spotlight, and Apple Intelligence | GA, rapidly expanding (WWDC26 added App Schemas, cross-app actions, onscreen awareness) |
| Linux | **D-Bus / MPRIS / custom IPC** — media players expose MPRIS, many apps expose D-Bus interfaces | Fragmented, app-by-app |
| Windows | **UI Automation / COM automation** — Office apps, some Win32 apps | Mature for Office, sparse elsewhere |
| Cross-platform | **MCP (Model Context Protocol)** — apps expose tools/resources/prompts over JSON-RPC to any MCP-compatible agent | Emerging standard, rapid adoption |
| Web apps | **REST/GraphQL APIs, Chrome DevTools Protocol (CDP)** | Universal for web |

**Key insight:** This tier is the cheapest, fastest, and most reliable.
If an app has any structured interface, you use it. The problem is that
most apps don't expose one, or expose a limited one.

### Tier 2: Accessibility Tree (Good — universal on modern OSes)

Every modern OS has an accessibility framework originally built for
screen readers. It exposes a semantic tree of UI elements (buttons,
text fields, menus, windows) with roles, titles, states, and sometimes
values. An agent can traverse this tree, find elements by role/name,
and invoke actions (press, set value, focus) without needing to "see"
the screen.

| Platform | API | What it gives you |
|----------|-----|-------------------|
| macOS | **Accessibility API (AXUIElement)** | Full UI tree of any running app, element inspection, programmatic click/type/press, background-safe input (no focus steal) |
| Windows | **UI Automation (UIA)** | Same — element tree, patterns (invoke, toggle, scroll), property queries |
| Linux | **AT-SPI2** | Same — GNOME/KDE ship it by default |
| Android | **AccessibilityService** | UI tree, gesture dispatch, screenshot, text injection — the foundation of every Android AI agent |
| iOS | **Accessibility** (more restricted) | Limited programmatic access; Apple pushes App Intents instead |

**Key insight:** This is the "Playwright for native apps" pattern. It
works on *any* app without the app's cooperation. It's what most of the
2026 MCP desktop-automation servers (see Section 3) are built on. The
trade-off: you need Accessibility permission granted, and some apps
(especially Electron/WebView apps) have poor accessibility trees.

### Tier 3: Screenshot + Coordinate (Fallback — works everywhere, expensive)

The agent takes a screenshot, a vision model (or OCR) interprets it,
the model decides where to click, and mouse/keyboard events are
injected at pixel coordinates. This is what Anthropic's "computer use"
toolset does.

- **Pros:** Works on literally any app, any platform, including
  canvas-rendered apps, games, and remote desktops.
- **Cons:** Slow (3-5 seconds per action), expensive (one LLM/vision
  call per action), fragile (layout shifts break coordinates), and
  requires taking over the real mouse/keyboard (or a virtual display).

**The 2026 consensus:** Use Tier 1 when available, Tier 2 as the
primary general-purpose mechanism, Tier 3 only as a last-resort fallback
for apps with no accessibility tree (canvas apps, remote sessions,
games).

---

## 2. The Current Ecosystem (September 2026)

### 2.1 Desktop MCP Servers for UI Automation

A burst of open-source MCP servers now give any MCP-compatible AI agent
(Claude, Cursor, Codex, Gemini CLI) desktop control. The best-in-class
ones all follow the same pattern: accessibility-tree-first, screenshot
as fallback, cross-platform.

| Project | Platforms | Approach | Notable |
|---------|-----------|----------|---------|
| **open-computer-use** (opensymph) | macOS, Windows, Linux | Accessibility-first, 9 core tools, background-safe input | Installs into Claude Code, Codex, Gemini CLI |
| **Screenhand** | macOS, Windows | Native accessibility APIs, CDP for browsers, ~50ms actions, 0 LLM calls per click | Claims 60x speedup over screenshot-based |
| **axcli** | macOS | Playwright-style CLI for AX API, background-safe via CGEventPostToPid | Confirmed working on Electron apps |
| **silk** | macOS | Accessibility + humanized input (Bezier curves, Fitts's Law), trusted events | Focus on anti-detection / human-like |
| **axon** | macOS | Three-tier: AppleScript/JXA → Accessibility → screenshot fallback | Has HTTP server mode for remote agents |
| **agent-swift** | macOS | CLI with `@eN` element refs, snapshot/press/fill/wait/assert | Playwright ergonomics for native apps |
| **Pathlight MCP** | macOS, Windows | Accessibility tree + CDP, 17 tools, no screenshots needed | `desktop.` namespace, wait_for conditions |
| **vision-mcp** | macOS, Windows | Hybrid AX/UIA + OCR + vision, records reusable `.yaml` interaction maps | Learns and replays workflows |
| **OmniCommanderMCP** | All 3 | 84 tools, system/CLI control + computer use + OCR | Most comprehensive single server |
| **FlaUI-MCP** (shanselman) | Windows | FlaUI + UIA, Playwright-style refs (`w1e5`) | Windows-focused reference impl |

**Pattern:** All of these are MCP servers that run locally, expose a
tool surface (snapshot, click, type, find, screenshot), and let the
LLM drive the desktop through the MCP protocol. The agent never needs
to be on the same machine — the MCP server bridges the gap.

### 2.2 Anthropic Computer Use (Production GA — August 2026)

Anthropic's `computer_toolset_20260801` went GA on August 19, 2026. It
gives Claude 17 member tools (screenshot, left_click, type, zoom, etc.)
as a single toolset entry. Key 2026 additions:

- **Batch actions** — multiple actions per turn instead of one-at-a-time
- **macOS native reference implementation** (no Docker required) in the
  best-practices quickstart, using `pyautogui` + `sandbox-exec`
- **Browser Use tool** — separate from computer use, Playwright-backed,
  for web-only automation
- **Agent Skills API** — lets agents package and share reusable
  interaction patterns

This is Tier 3 (screenshot+coordinate) but productionized. Anthropic
explicitly recommends it only when no API or accessibility approach
exists.

### 2.3 Phone-to-Computer Bridges (The "Antigravity" Pattern)

The user mentioned "Gemini on a phone + Antigravity on a computer."
What's actually happening in this ecosystem is a set of **remote
control bridges** — they don't give the AI access to *other* apps' UIs,
they give the user remote access to an AI agent that's running on their
computer, from their phone.

| Project | What it does |
|---------|--------------|
| **Antigravity Phone Chat** | Mirrors desktop Antigravity AI session to phone via CDP, sub-100ms snapshots, ngrok/Cloudflare tunnel |
| **Antigravity Mobile Proxy** | Chat with Antigravity agent from phone/tablet, approve actions remotely, browse artifacts |
| **Antimatter** | Mobile companion + VS Code extension bridge, Cloudflare Zero Trust tunnel, Ed25519 pairing, supports Antigravity + Claude Code |
| **Gravity Bridge** | Local reverse proxy, exposes desktop AI agent to phone browser, includes phone file explorer via ADB |

**These are not app-UI-access systems.** They are remote-presence
systems for an AI agent that already lives on the desktop. The
distinction matters: the user may be conflating "I can talk to my AI
from my phone" with "my AI can control other apps." They're different
problems.

### 2.4 OpenClaw — A Different Model

OpenClaw is closer to what Halbert is: a self-hosted **gateway** that
connects chat channels (WhatsApp, Telegram, Slack, Discord, Signal,
iMessage, etc.) to AI coding agents. Key architectural points:

- Single **Gateway** process on your machine, bridges messaging apps ↔ agent
- **Channels** bring the assistant to messaging services via plugins
- **Companion apps and nodes** add voice, camera, screen, device-local actions
- **Browser control** via dedicated Chrome/Brave profile + CDP (Playwright-backed)
- **Nodes** — iOS and Android nodes pair for camera, screen, and voice workflows
- **Skills and plugins** extend capabilities

OpenClaw's browser control is Tier 1/2 (CDP = structured web
automation). Its "nodes" concept — pairing mobile devices for
camera/screen/voice — is the closest analog to what Halbert's
federated multi-node architecture is reaching toward.

### 2.5 Voice-First Desktop Assistants

Several projects combine voice input with desktop control. The
architecture is consistently: STT → intent classification → agent loop
→ tool execution (accessibility or screenshot) → TTS.

| Project | Platform | Stack |
|---------|----------|-------|
| **Jarvis** (ONEPUNCHMAN411) | Windows | faster-whisper + Silero VAD + Edge TTS, Windows UI Automation tree, Playwright, 50+ tools |
| **AURA** | Windows | Face auth, dual-layer NLU (rules + LLM), Groq Whisper STT, SAPI5 TTS, event bus |
| **AIRA** | Linux | Gemini Live API (bidirectional voice), Playwright + xdotool, React/FastAPI |
| **EasySpeak** | Linux/Wayland | Fully local, openwakeword + Whisper + Piper, plugin system |

**Key pattern from Jarvis:** "Computer control goes through the Windows
UI Automation accessibility tree instead of pixel coordinates. Most
LLMs can't see your screen, they need structured data about what's in
each window. The accessibility tree gives that without needing a vision
model." This validates Tier 2 as the primary mechanism.

### 2.6 Android AI Agents (AccessibilityService-Based)

Android is the most mature mobile platform for AI-driven app control
because AccessibilityService gives full programmatic access to the UI
tree and gesture injection.

| Project | Approach |
|---------|----------|
| **DroidPilot** | AccessibilityService + MCP over WiFi, no ADB, 18 tools, structured UI data |
| **Genie** | On-device Gemma 4 via LiteRT-LM, intercepts every tool call for biometric approval before execution |
| **PhoneClaw** | AccessibilityService, React Native ↔ Kotlin bridge, tool registry |
| **Handy AI** | Claude Opus 4.7 + screenshot loop + AccessibilityService gestures |
| **OpenRing** | On-device RPA engine, Gemini or local GGUF, scheduled scripts |

**Critical note:** General-purpose automation via AccessibilityService
violates Google Play Store policy. All of these are sideloaded. This is
a fundamental constraint for Android — you can't ship this through the
Play Store. iOS is even more restricted; Apple's answer is App Intents,
not accessibility-driven automation.

---

## 3. The MCP Layer — The Emerging Standard

MCP (Model Context Protocol) deserves separate treatment because it's
the connective tissue that's standardizing all of this.

### 3.1 What MCP Is

MCP is a JSON-RPC protocol (Anthropic-introduced, now multi-vendor)
that defines how an AI application (the "host") connects to external
context/tool providers (the "servers"). It has two layers:

- **Data layer:** tools, resources, prompts, notifications
- **Transport layer:** stdio (local), Streamable HTTP (remote)

An MCP server can run locally on the same machine or remotely. The host
(Claude Desktop, Cursor, Codex, etc.) launches/connects to servers and
exposes their tools to the LLM.

### 3.2 Why This Matters for Halbert

MCP is becoming the standard way apps expose themselves to AI agents.
Instead of Halbert needing to know how to control every app, apps (or
third-party MCP servers) expose a standard tool surface. Halbert would
be an **MCP client** — it connects to MCP servers and gets tools.

This is architecturally clean:
- Halbert already has a tool executor and tool registry
- MCP tools are just another source of tools, discovered at runtime
- The agent loop doesn't change — it just has more tools available
- Apps that ship MCP servers (increasingly common) work automatically

### 3.3 MCP Apps (Interactive UI Extension)

A newer MCP extension (SEP-1865, GA 2026) lets MCP servers return
**interactive HTML interfaces** that render inside the host's chat. This
is bidirectional — the UI can call server tools and the host can push
updates. Google's A2UI proposal is a complementary native-rendering
approach.

This is relevant if Halbert ever wants to render rich interactive
controls (dashboards, forms, visualizations) as part of a conversation
rather than just text.

---

## 4. Apple-Specific Deep Dive

Since Halbert runs on macOS (and the user is on an M1 Ultra), the Apple
ecosystem mechanisms deserve attention.

### 4.1 AppleScript / Scripting Bridge (Tier 1, macOS)

- Apps with an `.sdef` (scripting definition) expose commands and
  objects. Finder, Mail, Safari, Calendar, Music, Notes, Reminders,
  Messages, Photos, and many third-party apps (OmniFocus, BBEdit, etc.)
  are scriptable.
- `sdef /Applications/SomeApp.app | sdp -fh --basename SomeApp`
  generates an Objective-C header; Scripting Bridge lets you call these
  from Python via PyObjC.
- **osascript** / **JXA** (JavaScript for Automation) can be called
  from subprocess — no compilation needed.
- This is the most reliable, lowest-latency way to control scriptable
  apps. No accessibility permission needed for most operations.

### 4.2 App Intents (Tier 1, macOS + iOS, 2026-era)

WWDC26 (June 2026) significantly expanded App Intents:
- **App Schemas** — conform to system-defined schemas (`.photos`,
  `.mail`, `.browser`, etc.) so Siri/Apple Intelligence understands
  your app's content and actions without custom training
- **Cross-app actions** — actions that span multiple apps via onscreen
  awareness and content transfer
- **SyncableEntity** — entities that travel across devices via stable IDs
- **LongRunningIntent** — intents that exceed the 30-second limit
- **ExecutionTargets** — control which process runs an intent
- **AppIntentsTesting** — new testing framework, no UI automation needed

**For Halbert:** If Halbert shipped as a macOS app with App Intents,
Siri could invoke Halbert actions, and Halbert could appear in
Shortcuts. More importantly, Halbert could *invoke* other apps' App
Intents — but only programmatically if those apps expose them. This is
Apple's sanctioned path for inter-app AI automation, and it's expanding
fast.

### 4.3 Accessibility API (Tier 2, macOS)

- Requires **Accessibility** permission (System Settings → Privacy &
  Security → Accessibility) granted to the controlling process
- **Screen Recording** permission needed for screenshots
- The AXUIElement API exposes: app lists, window lists, UI element
  trees (role, title, value, state, position, size), and actions
  (AXPress, AXConfirm, AXShowMenu, etc.)
- Background-safe input is possible via `CGEventPostToPid` — the target
  app doesn't need to be focused
- Confirmed working on native AppKit apps AND Chromium/Electron apps
  (VS Code, Chrome, Slack, Discord)

### 4.4 The Permission Wall

macOS requires explicit user-granted permissions for both Accessibility
and Screen Recording. This is a one-time setup but it's a UX hurdle.
Every desktop automation tool (Section 2.1) has to guide users through
this. Halbert would be no different.

---

## 5. How This Maps to Halbert's Architecture

### 5.1 What Halbert Already Has

From the codebase review:

- **ToolExecutor** with a tool registry, safety framework, role gate,
  and audit logging — tools are registered at agent init time
  (`register_system_tools`, `register_vision_tools`, `register_gpu_tools`,
  `register_accelerator_tools`, HA tools, Frigate tools, become tool)
- **Vision subsystem** — screen capture, webcam capture, OCR, redaction,
  motion detection, zone watching, Wayland capture. This is already
  Tier 3 infrastructure (screenshot-based).
- **AgentStateMachine** — the agent loop (IDLE → PLANNING → SEARCHING →
  EXECUTING → CRAG evaluation) with tool execution
- **Safety framework** — risk levels, confirmation gating, role-based
  tool access
- **Discovery Engine** — knows what's on the system (scanners for
  network, sharing, GPU, accelerators, services, etc.)
- **Federated multi-node architecture** — Halbert nodes on multiple
  machines, with peer pairing (in progress)

### 5.2 The Gap

Halbert can *see* the system (discovery, vision capture) and *act* on
the system (shell tools, HA tools, file tools), but it **cannot interact
with GUI applications**. There is no:

- Accessibility tree reader (no AXUIElement integration)
- AppleScript/JXA execution tool (no `osascript` tool registered)
- App Intents invocation
- MCP client capability (Halbert is not an MCP client — it can't
  connect to external MCP servers and use their tools)
- Desktop automation tool surface (no click, type, find-element tools)

The vision subsystem can *capture* the screen but cannot *act* on what
it sees beyond sending the image to a vision model. There's no
closed-loop "look at app → find element → click it → verify" pipeline.

### 5.3 Integration Points

The architecture is already designed for this. Adding app UI access
would follow the existing pattern:

1. **New tool module** (e.g., `halbert_core/tools/desktop_control.py`)
   that registers tools like `list_apps`, `get_app_state`, `click`,
   `type_text`, `find_element` — same pattern as `gpu_tools.py`,
   `accelerator_tools.py`
2. **Register in agent init** — one more `register_desktop_control_tools()`
   call in `dashboard/routes/agent.py`, gated by a capability/config flag
   (same pattern as vision tools being gated by `vision_config.yml`)
3. **Safety framework integration** — desktop control is high-risk
   (it can click things, type things), so it would go through the
   existing `RiskLevel` / confirmation gating / role gate system
4. **Discovery integration** — the Discovery Engine could scan for
   scriptable apps (apps with `.sdef` files), apps with App Intents,
   and running apps, making them available as context to the agent

---

## 6. Opportunities for Halbert

These are framed as possibilities, not recommendations. Each has
different complexity and value.

### 6.1 Low-Hanging Fruit: AppleScript Tool (Days, Tier 1)

Register an `applescript` / `run_script` tool that lets the agent
execute `osascript` commands. This immediately gives Halbert structured
control over every scriptable macOS app (Mail, Safari, Calendar, Music,
Notes, Reminders, Messages, Finder, plus third-party scriptable apps).

- **Complexity:** Low — it's a subprocess wrapper with safety checks
- **Value:** High for macOS users — "send an email in Mail," "create a
  calendar event," "play this playlist in Music," "search in Safari"
- **Risk:** Medium — AppleScript can do destructive things (delete
  files via Finder, send emails). Needs the safety framework's
  confirmation gating.
- **Voice use case:** "Halbert, send an email to Sarah saying I'll be
  late" → agent generates AppleScript → executes in Mail → confirms

### 6.2 Medium Effort: MCP Client Capability (Weeks, Tier 1)

Make Halbert an MCP client. It connects to local and remote MCP servers
and merges their tools into its tool registry. This is the most
future-proof investment — as more apps ship MCP servers, Halbert
automatically gains the ability to control them.

- **Complexity:** Medium — MCP SDKs exist for Python; need to integrate
  the client lifecycle, tool discovery, and tool execution into
  Halbert's existing executor
- **Value:** Very high long-term — this is where the ecosystem is
  heading. Halbert becomes a universal MCP host.
- **Risk:** Low per-tool (MCP servers define their own safety), but
  Halbert's safety framework should still gate high-risk MCP tools
- **Voice use case:** "Halbert, check my Linear issues" → Halbert
  connects to Linear MCP server → calls `list_issues` tool → reads
  results back

### 6.3 Medium Effort: Accessibility Tree Reader (Weeks, Tier 2)

Register tools that read the macOS Accessibility API: `list_windows`,
`get_app_tree`, `find_element`, `read_element_text`. This gives the
agent *eyes* on any running app without screenshots. Read-only first;
interaction (click/type) comes later.

- **Complexity:** Medium — needs PyObjC or a Swift helper binary;
  permission flow for Accessibility
- **Value:** High — this is the foundation for all Tier 2 automation.
  Even read-only, it lets the agent answer "what's on my screen right
  now" structurally instead of via screenshot+vision.
- **Risk:** Low for read-only; the permission grant is the main hurdle
- **Voice use case:** "Halbert, what's in my Safari window?" → agent
  reads AX tree → "You have 3 tabs open: ..."

### 6.4 Higher Effort: Full Desktop Control (Months, Tier 2 + 3)

Add interaction tools (`click`, `type_text`, `press_key`, `scroll`,
`drag`) backed by the Accessibility API, with screenshot+coordinate as
fallback. This is what the MCP servers in Section 2.1 do. Halbert would
essentially build its own equivalent, or wrap one of the existing
servers as an MCP client.

- **Complexity:** High — this is a full desktop automation stack
- **Value:** Very high but broad — "do anything in any app." The
  question is whether Halbert *should* be a general desktop automation
  agent or whether that's a different product.
- **Risk:** High — clicking and typing in arbitrary apps can do
  anything: delete data, send messages, make purchases. Needs very
  careful safety gating.
- **Alternative:** Instead of building this, be an MCP client and let
  the user connect a desktop-control MCP server (like
  open-computer-use or axcli). Halbert gets the capability without
  owning the implementation.

### 6.5 Strategic: App Intents Integration (Months, Apple ecosystem)

If Halbert ships as a macOS app (it has a Tauri shell), it could:
- **Expose App Intents** — Siri and Shortcuts could invoke Halbert
  ("Hey Siri, ask Halbert to check the GPU status")
- **Consume App Intents** — Halbert could invoke other apps' App Intents
  programmatically, for apps that expose them

This is Apple's sanctioned path and it's expanding rapidly (WWDC26).
It's the most "native" way to integrate with the Apple ecosystem but
it requires Halbert to be a proper macOS app bundle, not just a Python
process.

### 6.6 Cross-Device: The "Node as Remote Eyes/Hands" Pattern

Halbert's federated multi-node architecture is already heading toward
multiple machines. The phone-to-computer bridge pattern (Section 2.3)
suggests an opportunity: a Halbert node on a phone (or a lightweight
mobile companion) that gives the desktop Halbert *remote access* to the
phone's screen, camera, and sensors.

OpenClaw's "nodes" concept is the closest analog — iOS/Android nodes
that pair with the gateway for camera, screen, and voice workflows.

This is the largest scope item and probably the furthest out, but it's
where the architecture is naturally pointing.

---

## 7. What I'd Actually Recommend (If Asked)

Given Halbert's current state and the user's "I don't know what I'd use
it for yet" framing:

1. **Start with AppleScript (6.1).** It's the highest ROI: days of work,
   immediate voice-controllable access to Mail, Calendar, Music, Safari,
   Notes, Reminders, Messages. This alone makes Halbert dramatically
   more useful as a voice assistant on macOS. It also reveals what
   users actually want to do, which informs the bigger investments.

2. **Then MCP client (6.2).** This is the strategic bet. The ecosystem
   is standardizing on MCP. Being an MCP client means Halbert
   automatically benefits from every MCP server that gets written —
   Linear, GitHub, Slack, filesystem, browser, desktop control, etc.
   This subsumes much of 6.4 (desktop control) because the user can
   just connect a desktop-control MCP server.

3. **Defer accessibility tree and full desktop control (6.3, 6.4).**
   These are expensive to build and the MCP client approach (6.2) can
   bring them in via third-party servers. Only build native if there's
   a specific need that MCP servers don't cover.

4. **Watch App Intents (6.5).** This is the right long-term Apple
   integration story but it depends on Halbert's app packaging
   trajectory. Don't invest until the Tauri shell is further along.

5. **The cross-device pattern (6.6) is already on the roadmap** via the
   federated multi-node work. The research here validates that
   direction — it's what OpenClaw and the Antigravity bridge ecosystem
   are all doing.

---

## 8. Open Questions

1. **Safety model for desktop control.** Halbert's safety framework has
   risk levels and confirmation gating. How should clicking/typing in
   arbitrary apps be gated? Per-action confirmation? Per-app allowlists?
   A "trusted apps" concept?

2. **Voice confirmation loop.** If Halbert is about to click something
   destructive in a GUI app, how does the voice interaction model
   handle confirmation? "Should I click Delete?" → user says "yes" →
   click. This needs design.

3. **MCP client lifecycle.** When does Halbert connect to MCP servers?
   At startup? On-demand? User-configured in settings? How are MCP
   server tools merged with native tools in the safety framework?

4. **Scriptable app discovery.** Should the Discovery Engine scan for
   scriptable apps (apps with `.sdef`) and expose them as context? This
   would let the agent know "Mail is scriptable, here are its commands"
   without the user having to tell it.

5. **Scope question.** Is Halbert a voice assistant that *can* control
   apps, or a desktop automation agent that *has* a voice interface?
   These are different products with different design centers. The
   answer determines how much to invest in 6.3/6.4 vs. 6.1/6.2.

6. **Platform priority.** macOS is the user's platform. But Halbert
   also runs on Linux. AppleScript is macOS-only; accessibility works
   on both but with different APIs. MCP is cross-platform. How much
   should be macOS-first vs. cross-platform from the start?

---

## 9. Key References

### MCP Desktop Automation Servers
- open-computer-use: https://github.com/opensymph/open-computer-use
- Screenhand: https://github.com/manushi4/screenhand
- axcli: https://github.com/andelf/axcli
- silk: https://github.com/saucesteals/silk
- axon: https://github.com/gxcsoccer/axon
- agent-swift: https://github.com/beastoin/agent-swift
- Pathlight MCP: https://github.com/Mikenahh92/Pathlight-mcp
- vision-mcp: https://github.com/Haruhiyuki/vision-mcp
- OmniCommanderMCP: https://github.com/kaannsaydamm/OmniCommanderMCP

### Anthropic Computer Use
- Computer use tool docs: https://platform.claude.com/docs/en/agents-and-tools/tool-use/computer-use-tool
- Best practices (macOS native): https://github.com/anthropics/claude-quickstarts/tree/main/computer-use-best-practices

### Phone-to-Computer Bridges
- Antigravity Phone Chat: https://github.com/krishnakanthb13/antigravity_phone_chat
- Antigravity Mobile Proxy: https://github.com/Belal33/antigravity-mobile-proxy
- Antimatter: https://github.com/saifmukhtar/antimatter

### OpenClaw
- Docs: https://docs.openclaw.ai/
- GitHub: https://github.com/openclaw/openclaw
- Browser control: https://docs.openclaw.ai/tools/browser-control

### Apple Ecosystem
- App Intents: https://developer.apple.com/documentation/appintents/appintent
- WWDC26 App Schemas: https://developer.apple.com/videos/play/wwdc2026/240/
- WWDC26 Advanced App Intents: https://developer.apple.com/videos/play/wwdc2026/345/
- Scripting Bridge: https://developer.apple.com/library/archive/documentation/Cocoa/Conceptual/ScriptingBridgeConcepts/

### Android Agents
- DroidPilot: https://github.com/youichi-uda/droidpilot
- Genie: https://github.com/Akeem1955/Genie
- PhoneClaw: https://github.com/8dazo/phoneclaw

### Voice-First Assistants
- Jarvis: https://github.com/ONEPUNCHMAN411/Jarvis
- AIRA: https://github.com/bertila-ngong/aira
- EasySpeak: https://github.com/ctsdownloads/easyspeak

### MCP Protocol
- Architecture: https://modelcontextprotocol.io/docs/2026-07-28/learn/architecture
- MCP Apps: https://modelcontextprotocol.io/extensions/apps/overview
- SEP-1865: https://modelcontextprotocol.org/seps/1865-mcp-apps-interactive-user-interfaces-for-mcp

### Halbert Internal (integration points)
- Tool executor: `halbert_core/halbert_core/tools/executor.py`
- Agent init / tool registration: `halbert_core/halbert_core/dashboard/routes/agent.py` (lines 140-314)
- Vision subsystem: `halbert_core/halbert_core/vision/__init__.py`
- Safety framework: `halbert_core/halbert_core/tools/safety.py`
- GPU tools (registration pattern example): `halbert_core/halbert_core/tools/gpu_tools.py`
