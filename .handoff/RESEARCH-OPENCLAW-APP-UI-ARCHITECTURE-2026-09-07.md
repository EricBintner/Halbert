# RESEARCH: OpenClaw App UI Access Architecture — How OpenClaw Does It

**Date:** 2026-09-07
**Author:** Devin session
**Status:** Research complete — findings documented, cross-referenced to Halbert plan
**Related:**
- RESEARCH-VOICE-ASSISTANT-APP-UI-ACCESS-2026-09-07.md (the original landscape research)
- PLAN-VOICE-ASSISTANT-APP-UI-ACCESS-2026-09-07.md (the Halbert implementation plan)
**Source codebase:** `/Volumes/Thunderbolt/AI/openclaw` (local checkout, version 2026.9.2)

---

## 0. Why This Research Matters

The original research doc mapped the broad 2026 ecosystem of AI-to-app-UI
interaction. This document narrows to one production system — OpenClaw —
that has already solved many of the problems Halbert's plan addresses.
OpenClaw is the closest architectural analog to Halbert: a self-hosted
gateway that connects chat channels to an AI agent, with companion apps
on multiple platforms, voice interaction, browser control, desktop
control, and MCP integration.

By studying how OpenClaw actually implemented these capabilities, we can:
1. Validate or revise the Halbert plan's approach
2. Borrow proven patterns (especially the voice confirmation gate)
3. Avoid mistakes OpenClaw already made and fixed
4. Understand the complexity ceiling for each capability

---

## 1. OpenClaw's Architecture at a Glance

OpenClaw is a TypeScript monorepo with a central **Gateway** and
peripheral **nodes**:

```
Chat channels (WhatsApp, Telegram, Slack, Discord, Signal, ...)
    │
    ▼
┌──────────────────────────────────────────┐
│              Gateway                      │
│  (runs the model, routes tool calls,      │
│   manages sessions, auth, pairing)        │
│                                           │
│  Agent tools: browser, computer, message, │
│   exec, web_search, cron, automations,    │
│   + plugin tools + MCP client tools       │
└──────────┬──────────────────┬─────────────┘
           │                  │
     node.invoke        MCP (client+server)
           │                  │
    ┌──────┴──────┐    ┌──────┴──────┐
    │   Nodes     │    │ MCP Servers │
    │ (peripheral)│    │ (external)  │
    └─────────────┘    └─────────────┘
```

Key architectural principles (from `AGENTS.md`):
- **Core stays plugin-agnostic.** Optional capabilities ship as plugins.
- **Two plugin styles:** code plugins (runtime hooks) and bundle-style
  plugins (package stable external surfaces like MCP servers).
- **Runtime state in SQLite**, not JSON sidecar files.
- **Channels are transport-only.** Shared typed actions belong to their
  owners; channel adapters encode them.
- **Tool descriptions mention only capabilities actually available.**

---

## 2. Desktop Control (Computer Use) — The `computer` Tool

### 2.1 Architecture

OpenClaw's desktop control is **capability-based and node-mediated**. The
agent doesn't directly control the desktop — it calls the `computer` tool,
which routes through `node.invoke` to a paired node that advertises both
`computer.act` and `screen.snapshot` commands.

Source: `docs/nodes/computer-use.md`

```
Agent calls `computer` tool
    │
    ▼
Gateway routes via node.invoke to paired desktop node
    │
    ▼
Node-local provider fulfills the action:
  macOS: Peekaboo (default, in-process) or CUA (driver daemon)
  Windows/Linux: cua-computer plugin (direct SDK)
    │
    ▼
Provider executes: screenshot, click, type, scroll, etc.
    │
    ▼
Result returned to agent (fresh screenshot after input actions)
```

### 2.2 The Single `computer` Tool Surface

The agent sees **one tool** called `computer` that takes one action per
call. The action types (from `docs/nodes/computer-use.md:30-46`):

| Category | Actions |
|----------|---------|
| **Reads** | `screenshot` |
| **Pointer** | `left_click`, `right_click`, `middle_click`, `double_click`, `triple_click`, `mouse_move`, `left_click_drag`, `left_mouse_down`, `left_mouse_up` |
| **Scroll** | `scroll` (with `scrollDirection` and `scrollAmount`) |
| **Keyboard** | `type` (text), `key` (combo like `cmd+shift+t`), `hold_key` |
| **Pacing** | `wait` (duration, followed by screenshot) |

Providers with the v2 window/element family additionally expose:
`list_apps`, `list_windows`, `get_accessibility_tree`, `get_cursor_position`,
`get_window_state`, `launch_app`, `kill_app`, `bring_to_front`, `set_value`,
`zoom`, `escalate_scope`, `invoke_menu`.

The CUA provider also exposes browser-family actions: `get_browser_state`,
`browser_prepare`, `browser_navigate`, `browser_click`, `browser_type`,
`browser_dialog`, `browser_set_input_files`, `browser_download`,
`browser_pointer`.

**Key design decision:** The agent emits one uniform `computer.act`
command and **cannot choose how the node fulfills it**. Provider selection
is a node-local setting, not an agent decision. This prevents the agent
from bypassing safety layers by selecting a different provider.

### 2.3 Coordinate Safety

Coordinates are bound to a node-issued reference frame (`frameId`):
- Coordinate actions must echo the screenshot result's `frameId`
- An explicit `screenIndex` must match that frame
- OpenClaw carries a node-issued display identity from the screenshot
  into the action, so a display reconnect or geometry change **fails
  closed** instead of silently retargeting the same index
- A token is not a freshness guarantee — apps can change pixels after
  capture, so take a new screenshot whenever the scene may have changed

### 2.4 Provider Abstraction (macOS)

On macOS, **Settings → General → Capabilities** selects the provider:
- **Peekaboo** (default) — in-process, uses CoreGraphics input primitives,
  requires Accessibility + Screen Recording + Event Posting
- **CUA** — driver daemon embedded in `OpenClaw.app`, spawned directly
  so it inherits the app's TCC grants

Provider selection **never falls back per action**. Switching providers
closes the active execution surface, rotates the provider generation, and
re-advertises the node commands. A CUA failure becomes an unavailable
result instead of silently running through Peekaboo.

### 2.5 Trust Model

From `docs/nodes/computer-use.md:62-74`:

> The Gateway is the authorization chokepoint; the driver is a dumb
> effector. OpenClaw deliberately leaves the daemon unceilinged and
> authorizes computer use above it through tool exposure, the
> dangerous-command allowlist, device and command pairing approval,
> node-local provider enablement, and OS permissions.

The managed endpoint is **not part of the model contract**. The CUA
plugin registers no model tool, CLI command, service, or raw node-MCP
descriptor. Its action schema accepts neither helper binaries, sockets,
native sessions, driver arguments, nor provider tool names. This
prevents an OpenClaw model action from selecting an alternate route to
the managed daemon.

### 2.6 Screenshots Are Model-Only

Screenshots are kept **model-only**: they are never auto-delivered to the
chat channel. Treat all on-screen content as untrusted input; the tool
warns the model not to follow on-screen instructions that conflict with
the user's request.

---

## 3. Browser Control — The `browser` Tool

### 3.1 Architecture

Browser control lives in `extensions/browser/` as a bundled plugin. It's
**lazy-loaded** — the plugin registers descriptors at startup but only
imports the heavy runtime when a browser tool, CLI command, or the
control server actually needs it.

Source: `extensions/browser/plugin-registration.ts`

```
Agent calls `browser` tool (single tool, action-driven)
    │
    ▼
Tool dispatch (browser-tool.ts:195) parses action, resolves profile/target/node
    │
    ▼
Profile resolution (config.ts:377) — openclaw | user | chrome
    │
    ▼
CDP layer (cdp.ts) — raw WebSocket to Chrome DevTools Protocol
    │  OR
Playwright layer (pw-session-connection.ts:394) — connectOverCDP
    │
    ▼
Action execution: click, type, navigate, snapshot, screenshot, etc.
```

### 3.2 Profile Isolation Model

Three profile types with different capability matrices:

| Profile | Driver | Mode | What it is |
|---------|--------|------|------------|
| `openclaw` (default) | `openclaw` | `local-managed` | Dedicated Chromium with its own user-data-dir |
| `user` | `existing-session` | `local-existing-session` | Attaches to user's real signed-in Chrome via CDP MCP |
| `chrome` | `extension` | `local-extension` | Drives signed-in Chrome through bundled extension relay |

**Key insight:** The managed (`openclaw`) profile is isolated from the
user's personal browser. The `user` profile attaches to the real signed-in
session but has reduced capabilities (no batch actions, downloads, PDF,
network logs, etc.) because the MCP transport is more restricted.

### 3.3 The Single `browser` Tool Surface

One tool, action-driven (from `extensions/browser/src/browser-tool.schema.ts:36-61`):

```typescript
const BROWSER_TOOL_ACTIONS = [
  "doctor", "status", "start", "stop",
  "profiles", "importprofile",
  "tabs", "open", "focus", "close",
  "snapshot", "screenshot", "navigate",
  "console", "requests", "errors",
  "text", "emulate", "pdf",
  "download", "waitfordownload",
  "upload", "dialog",
  "act",
];

const BROWSER_ACT_KINDS = [
  "batch", "click", "clickCoords",
  "type", "press", "hover", "scrollIntoView",
  "drag", "select", "fill",
  "resize", "wait", "evaluate", "close",
];
```

The schema is **deliberately flattened** because some model providers
reject nested `anyOf` JSON schemas.

### 3.4 Stable Ref System

OpenClaw generates stable element references (`eN`, `axN`, `f1e12`)
from snapshots:
- Role refs from Playwright accessibility snapshot, post-processed to
  inject `eN` refs
- ARIA refs from CDP `Accessibility.getFullAXTree`
- If CDP provides `backendDOMNodeId`, OpenClaw injects a
  `data-openclaw-browser-ref` attribute into the DOM for unambiguous
  action resolution
- Refs are cached per target and page
- `newElements` counter compares ref identity sets between snapshots

### 3.5 Loopback HTTP Control Server

An opt-in, loopback-only Express server (`127.0.0.1`, port `gateway.port + 2`):
- Enabled by `OPENCLAW_EAGER_BROWSER_CONTROL_SERVER=1`
- Auto-generates auth token/password
- Full REST API: status, start/stop, profiles, tabs, snapshot, screenshot,
  screencast, navigate, act, download, console, errors, requests, etc.
- The agent tool and CLI both call the same routes

---

## 4. Voice Confirmation Gate — The Critical Pattern for Halbert

### 4.1 The Problem This Solves

This is the exact problem flagged as "the hardest task" in the Halbert
plan (Task D2, fable/max): how to prevent catastrophic voice-initiated
actions while keeping the voice assistant useful.

OpenClaw has already solved this. The solution is in
`src/talk/client-voice-confirmation.ts`.

### 4.2 How It Works

**Voice-originated consult runs require a new, exact spoken confirmation
before high-impact actions.** The gate applies to runs started through
`talk.client.toolCall`, the Gateway relay, and GPT-Live sideband
delegations.

The flow:

```
1. User speaks a command ("send an email to Sarah")
2. STT transcribes → agent consult runs
3. Agent attempts a high-impact tool (e.g., `message` send)
4. checkClientVoiceToolConfirmationPolicy() blocks it
   → returns VOICE_CONFIRMATION_REQUIRED:<confirmationId>
5. Consult returns that reason to the realtime provider
6. Provider speaks: "Should I send an email to Sarah?"
7. User says: "yes" / "yes do it" / "go ahead" / "confirm" / "send it"
8. noteClientVoiceConfirmationUtterance() records the affirmation
9. authorizeClientVoiceConfirmation() matches utterance to pending challenge
   → binds approval to the run
10. Next openclaw_agent_consult call includes the confirmationId
11. Agent retries the tool
12. consumeClientVoiceToolConfirmationPolicy() checks run-bound fingerprint
    → allows the tool ONCE
```

Source: `src/talk/client-voice-confirmation.ts`

### 4.3 What's Gated

`requiresHighImpactVoiceConfirmation()` (`client-voice-confirmation.ts:150-180`)
returns `true` for these tool categories when the action is mutating:

| Tool | Why it's high-impact |
|------|---------------------|
| `message` | Sends messages to chat channels |
| `gateway` | Changes gateway configuration |
| `nodes` | Controls paired devices |
| `browser` | Web automation (navigation, clicks, form submission) |
| `computer` | Desktop control (clicks, typing, app control) |
| `mobile_ui` | Mobile UI automation |
| `canvas` | Canvas interactions |
| `automations` | Creates/modifies automations |
| `process` | Process management |

**Workspace-local edits are NOT gated:** `write`, `edit`, `apply_patch`,
`create_goal`, etc. are confirmation-free because they're reversible and
local.

### 4.4 Fingerprint Binding

`stableToolFingerprint()` (`client-voice-confirmation.ts:131-148`) hashes
the tool name and sorted params. The confirmation is bound to the exact
action — if a policy or hook rewrites the approved action, OpenClaw
blocks it until the rewritten action is confirmed.

The confirmation is **consumed once**. One spoken "yes" cannot authorize
multiple actions.

### 4.5 Affirmation and Refusal Matching

`isExplicitAffirmation()` (`client-voice-confirmation.ts:337-346`) matches:
`yes`, `yes do it`, `do it`, `confirm`, `confirmed`, `go ahead`,
`proceed`, `send it`, `make the change`, `restart it`

A spoken refusal (`no`, `don't`, `do not`, `cancel`, `stop`, `never mind`)
kills the pending challenge.

### 4.6 TTL and Cleanup

- `CONFIRMATION_TTL_MS = 2 * 60_000` (2 minutes)
- Pending state is cleaned up after completion or expiry
- Only **finalized** user transcripts (not partial) can authorize a tool

### 4.7 What This Means for Halbert

This is a **production-tested pattern** for exactly the problem the
Halbert plan's Task D2 describes. Key takeaways:

1. **Fingerprint the exact action** — hash tool name + params, bind
   confirmation to that fingerprint, re-confirm if the action changes
2. **One-shot consumption** — one "yes" authorizes one action, not a
   session
3. **Categorize tools by impact** — mutating external-state tools are
   gated; local reversible edits are not
4. **Use finalized transcripts only** — partial STT results can't
   authorize actions
5. **Match both affirmations and refusals** — "no" and "cancel" kill
   the pending challenge
6. **2-minute TTL** — pending confirmations expire if the user doesn't
   respond
7. **The confirmation flows through the tool policy chain** — it's not
   a separate system, it's integrated into `before-tool-call` policy

This downgrades Halbert's Task D2 from fable/max to opus/xhigh — the
design problem is solved, the implementation is a matter of porting the
pattern to Halbert's Python safety framework.

---

## 5. Node Architecture — Companion Devices

### 5.1 What a Node Is

A **node** is a peripheral, authenticated device that connects to the
Gateway as `role: "node"` and exposes a command surface invoked through
`node.invoke`. Nodes are **peripherals, not gateways** — channel messages
land on the Gateway, not on nodes.

Supported node forms:
- iOS, Android, watchOS, macOS companion apps
- Headless Linux node host (`openclaw node run`)
- Native macOS app in node mode
- Apple Watch HTTPS-polling node

### 5.2 Connection and Pairing

Nodes use **device pairing** with signed device identities:
1. Node presents a signed device identity during WebSocket connect
2. Gateway creates a pending pairing request for `role: "node"`
3. Operator approves via `openclaw devices approve <requestId>`
4. Pairing is durable — token rotation cannot upgrade beyond approved
   role/caps
5. Expanding the command surface requires re-approval

The connect frame declares:
- `caps`: high-level categories (`camera`, `screen`, `location`, `voice`, `talk`)
- `commands`: the command allowlist the Gateway is allowed to invoke
- `permissions`: granular toggles (`camera.capture`, `screen.record`)

### 5.3 Layered Authorization

A usable capability requires **all** of these to agree:
1. Agent tool policy (tool is exposed to the agent)
2. Gateway command policy (`gateway.nodes.commands.allow/deny`)
3. Pairing approval (operator approved the command surface)
4. Node-local feature toggle (e.g., `camera.enabled` in app settings)
5. OS permission (Accessibility, Screen Recording, CAMERA, etc.)
6. Foreground/background state (iOS camera is foreground-only)

This is the same layered approach the Halbert plan describes (capability
+ config + safety framework + role gate), but more mature.

### 5.4 Per-Platform Capabilities

| Platform | Default commands |
|----------|-----------------|
| iOS | `camera.list`, `location.get`, `device.info`, `contacts.search`, `calendar.events`, `reminders.list`, `photos.latest`, `motion.activity`, `system.notify` |
| Android | adds `notifications.list`, `mobile.ui.observe`, `mobile.ui.act`, `callLog.search` |
| macOS | adds `computer.act`, `camera.ptz.status`, `desktop.stream` |
| Linux | `system.notify`, `computer.act` + approval-gated `system.run` |

### 5.5 What This Means for Halbert

OpenClaw's node architecture is the **production version** of what
Halbert's federated multi-node architecture is reaching toward. Key
patterns to borrow:

1. **Central gateway + peripheral nodes** — one control plane
   authenticates, dispatches, authorizes; nodes are capability hosts
2. **Capability advertisement** — nodes publish `caps`, `commands`,
   `permissions`; the gateway selects and invokes
3. **Durable pairing contract** — pairing records the approved surface;
   token rotation stays within that contract
4. **Capability re-approval on expansion** — new commands trigger a new
   pending request
5. **Local provider isolation** — platform-specific implementation stays
   local; the agent sees normalized commands
6. **Stable error taxonomy** — commands return stable error codes
   (`NODE_BACKGROUND_UNAVAILABLE`, `CAMERA_DISABLED`, etc.)

---

## 6. MCP Integration — Both Client and Server

### 6.1 OpenClaw Is Both

OpenClaw does not choose a single MCP role:
- **MCP server:** Exposes its own tools (channel conversation tools,
  plugin tools, built-in tools) over stdio to external MCP clients
- **MCP client:** Consumes external MCP servers, merging their tools
  into the agent's tool catalog

### 6.2 MCP Server Side

Multiple MCP servers in `src/mcp/`:
- `channel-server.ts` — serves channel conversation tools over stdio
- `plugin-tools-serve.ts` — serves plugin-registered agent tools
- `openclaw-tools-serve.ts` — serves selected built-in tools
- `codex-supervision-tools-serve.ts` — legacy Codex supervision tools

The common pattern (`src/mcp/tools-stdio-server.ts`): create an MCP
`Server` with `tools` capability, bind `ListToolsRequestSchema` and
`CallToolRequestSchema` to generic handlers. **The same `AnyAgentTool`
objects used by the agent are exposed to MCP clients through a thin
adapter** — no tool reimplementation.

### 6.3 MCP Client Side

- `src/agents/agent-bundle-mcp-runtime.ts` — session-scoped MCP runtime
  catalog loader; paginates `tools/list`, normalizes schemas, builds
  merged catalog
- `src/node-host/mcp.ts` — calls remote tools via
  `session.client.callTool(...)` with timeout, abort signal, session
  expiry handling
- Supports `stdio`, `sse`, and `streamable-http` transports
- Tool names are assigned stable prefixes (`src/agents/agent-bundle-mcp-names.ts`)

### 6.4 Node-Hosted MCP Servers

MCP servers can be configured on the **node machine** (not the Gateway):

```json5
{
  nodeHost: {
    mcp: {
      servers: {
        localDocs: {
          command: "npx",
          args: ["-y", "@modelcontextprotocol/server-filesystem", "/srv/docs"],
          toolFilter: { include: ["read_*", "search"] },
        },
        internalApi: {
          url: "https://mcp.internal.example/mcp",
          transport: "streamable-http",
          headers: { Authorization: "Bearer ${INTERNAL_MCP_TOKEN}" },
        },
      },
    },
  },
}
```

The node host starts these servers, lists their tools, and publishes
descriptors after connecting. Tool calls return to that node through
`mcp.tools.call.v1`. The Gateway doesn't need matching MCP config.

### 6.5 What This Means for Halbert

This validates the Halbert plan's Workstream B (MCP client) and adds a
key insight: **be both client and server**. Halbert should:
1. Consume external MCP servers (the plan's Workstream B)
2. Expose its own tools as an MCP server (not in the original plan —
   this would let other AI agents use Halbert's system admin tools)
3. Support node-hosted MCP servers (MCP servers running on Halbert
   nodes, not just the main machine)

---

## 7. Plugin System

### 7.1 Architecture

OpenClaw's plugin system has a **control-plane / runtime-plane split**:
1. **Discovery & manifest parsing** — `openclaw.plugin.json` is read
   without executing plugin code (cheap metadata for control-plane
   planning)
2. **Activation planning** — based on manifest `activation`, config,
   enablement flags
3. **Lazy runtime loading** — heavy runtime imported only when needed
4. **Tool resolution** — filter malformed, undeclared, conflicting,
   unavailable, or denied tools; attach ownership metadata
5. **Execution** — the resolved `AnyAgentTool` is what the agent, HTTP,
   worker, and MCP paths invoke

### 7.2 Plugin Manifest

`openclaw.plugin.json` fields include: `id`, `name`, `description`,
`configSchema`, `contracts`, `cliCommands`, `providers`, `cliBackends`,
`mcpServers`, `activation` hints, `setup`, `uiHints`, `dashboard` widgets.

### 7.3 Plugin SDK

- `definePluginEntry(...)` — the entry shape with `register(api)` callback
- `defineToolPlugin(...)` — tool helper that builds config schema,
  captures tool metadata, registers tools via `api.registerTool(...)`
- `AnyAgentTool` — canonical tool shape: `name`, `description`,
  `parameters`, `execute(toolCallId, params, signal, onUpdate)`

### 7.4 What This Means for Halbert

Halbert's current tool registration pattern (`register_gpu_tools`,
`register_accelerator_tools`, etc.) is simpler but less extensible than
OpenClaw's plugin system. The key takeaway: **a manifest-first approach
that reads metadata without executing code** is valuable for:
- Tool discovery without loading heavy dependencies
- Security review before activation
- Dashboard display of available capabilities

This is a future direction for Halbert, not an immediate need. The
current `register_*_tools()` pattern works fine for built-in tools.

---

## 8. Voice / Talk Architecture

### 8.1 Three Voice Pipelines

| Path | STT | Agent | TTS |
|------|-----|-------|-----|
| Provider-native realtime | Realtime provider (OpenAI, Google) | OpenClaw via `openclaw_agent_consult` | Realtime provider |
| Gateway transcription relay | Realtime transcription provider | OpenClaw Talkback / agent consult | OpenClaw TTS or provider |
| Explicit `talk.speak` | N/A | N/A | OpenClaw TTS |

### 8.2 The `openclaw_agent_consult` Pattern

The realtime model sees a function tool called `openclaw_agent_consult`.
Its description tells the model to call it for "normal OpenClaw tools,
memory, workspace context, or current information." It accepts a
`confirmationId` "supplied only after the user explicitly confirms aloud."

The consult runs as an **embedded OpenClaw agent run** with:
- Voice-specific prompt
- The agent's normal configured tools
- Tool authority overlay
- `verboseLevel: "off"`, `reasoningLevel: "off"`, `toolResultFormat: "plain"`
- Only visible text is returned (errors, reasoning, commentary filtered out)

This is a clean separation: the realtime voice provider handles
conversation, VAD, barge-in, and audio synthesis; OpenClaw handles tool
execution and workspace context. The bridge is the `openclaw_agent_consult`
function tool.

### 8.3 On-Device TTS (`apps/macos-mlx-tts/`)

A Swift helper binary built on Apple's MLX framework:
- Runs outside the main TypeScript runtime
- Communicates over stdin/stdout using length-prefixed JSON frames
- Caches one loaded model at a time
- Supports buffered and streaming synthesis
- Returns PCM16 audio
- Events: `ready`, `audio`, `streamStarted`, `audioChunk`, `completed`,
  `error`, `canceled`

This is a local, offline TTS worker — not a network TTS provider.

### 8.4 What This Means for Halbert

Halbert's voice architecture should consider:
1. **The consult pattern** — separate the voice conversation layer from
   the tool execution layer, bridged by a single function tool
2. **Filtering speakable output** — only return concise visible text,
   not errors/reasoning/commentary
3. **On-device TTS option** — a local TTS worker (like the MLX helper)
   for offline/low-latency speech

---

## 9. Cross-Reference: OpenClaw Patterns → Halbert Plan Tasks

| Halbert Plan Task | OpenClaw Pattern | Impact on Plan |
|---|---|---|
| **A1** (AppleScript scaffold) | N/A — OpenClaw doesn't use AppleScript | No change |
| **A2** (AppleScript safety) | Voice confirmation gate (`client-voice-confirmation.ts`) — fingerprint, one-shot, TTL | **Downgrade from opus/high to sonnet/high** — the safety pattern is proven, just port it |
| **B1** (MCP client library) | `src/agents/agent-bundle-mcp-runtime.ts` — paginated tool discovery, schema normalization, stable prefixes | **Reference implementation exists** — study OpenClaw's client for transport handling, session expiry, tool filtering |
| **B2** (MCP tool bridge) | `src/mcp/plugin-tools-handlers.ts` — thin adapter, no tool reimplementation | **Validate approach** — wrap existing tools, don't reimplement |
| **B3** (MCP safety) | Layered authorization (tool policy + command policy + pairing + local toggle + OS permission) | **Upgrade complexity estimate** — OpenClaw's layered approach is more robust than the plan's simple per-server config |
| **C1** (AX helper binary) | CUA driver daemon — app-owned, inherits TCC grants, private socket | **Key insight** — the helper must be spawned by the app process to inherit permissions, not launched independently |
| **C2** (AX reader tools) | `computer` tool's v2 window/element family — `list_apps`, `list_windows`, `get_accessibility_tree` | **Validate tool surface** — OpenClaw's action list is a proven set |
| **D1** (Interaction primitives) | `computer.act` — single command, provider-fulfilled, background-safe via CGEventPostToPid | **Validate approach** — single tool, action-driven, provider abstraction |
| **D2** (Safety framework) | `client-voice-confirmation.ts` — fingerprint-bound, one-shot, spoken confirmation | **Major downgrade: fable/max → opus/xhigh** — the design is solved, port the pattern |
| **D3** (Screenshot fallback) | `computer` tool's `screenshot` action — model-only, never auto-delivered to chat, frame-bound coordinates | **Validate approach** — screenshots are model-only, coordinates bound to frame ID |
| **E1/E2** (App Intents) | N/A — OpenClaw doesn't use App Intents | No change |
| **G1** (Mobile node) | Full node architecture — device pairing, capability advertisement, `node.invoke`, per-platform companion apps | **Reference architecture exists** — OpenClaw's node system is the production version of Halbert's federated multi-node vision |

---

## 10. Revised Effort Estimates Based on OpenClaw Evidence

| Task | Original | Revised | Reason |
|------|----------|---------|--------|
| A2 (AppleScript safety) | opus/high | sonnet/high | Voice confirmation pattern is proven; port it |
| B1 (MCP client) | opus/xhigh | opus/high | OpenClaw's client is a reference; transports and session handling are understood |
| B3 (MCP safety) | opus/high | opus/xhigh | OpenClaw's layered authorization is more complex than the plan assumed |
| D2 (Desktop safety) | fable/max | opus/xhigh | The voice confirmation gate is a solved design problem |
| G1 (Mobile node) | fable/max | fable/xhigh | Still large scope, but OpenClaw's node architecture is a reference |

**Net effect:** The overall effort is **lower than originally estimated**
because OpenClaw has already solved the hardest design problems (voice
confirmation, layered authorization, node architecture). The remaining
work is implementation and porting, not original design.

---

## 11. Key OpenClaw Source Files for Reference

### Voice confirmation (the most important pattern for Halbert)
- `src/talk/client-voice-confirmation.ts` — the full confirmation engine
- `src/agents/agent-tools.before-tool-call.policy.ts:85-99, 183-200` — policy integration
- `src/talk/client-voice-session.ts:555-563` — transcript-driven confirmation
- `src/talk/agent-consult-tool.ts:13-65` — the `openclaw_agent_consult` tool

### Computer use / desktop control
- `docs/nodes/computer-use.md` — full documentation
- `src/node-host/computer-command.ts:13-49` — worker-side command adapter
- `src/node-host/desktop-stream-command.ts` — VNC/RFB streaming

### Browser control
- `extensions/browser/plugin-registration.ts:281-346` — tool registration
- `extensions/browser/src/browser-tool.schema.ts:19-61` — tool schema
- `extensions/browser/src/browser/cdp.ts` — CDP layer
- `extensions/browser/src/browser/pw-session-connection.ts:394` — Playwright layer
- `extensions/browser/src/browser/profile-capabilities.ts:38-112` — capability matrix

### Node architecture
- `docs/nodes/index.md` — full node documentation
- `src/node-host/runtime.ts:55-92, 377-410` — manifest construction
- `src/node-host/invoke.ts:86-120` — command dispatcher
- `src/gateway/server-methods/nodes.invoke.ts:57-77` — gateway-side dispatch
- `src/infra/device-pairing.types.ts:11-30, 79-96` — pairing record types

### MCP integration
- `src/mcp/plugin-tools-serve.ts:79-139` — MCP server for plugin tools
- `src/mcp/plugin-tools-handlers.ts:68-129` — listTools/callTool adapter
- `src/agents/agent-bundle-mcp-runtime.ts` — MCP client catalog loader
- `src/node-host/mcp.ts:581-615` — remote tool calls with timeout/abort

### Plugin system
- `src/plugin-sdk/plugin-entry.ts:202-259` — `definePluginEntry`
- `src/plugin-sdk/tool-plugin.ts:167-251` — `defineToolPlugin`
- `src/plugins/plugin-api.types.ts:209-225` — registration API
- `src/plugins/tools.ts:601-628, 660-707` — tool resolution pipeline

### Voice / Talk
- `src/talk/session-runtime.ts:41-91` — session bridge facade
- `src/talk/agent-consult-runtime.ts:486-550` — embedded agent run
- `src/gateway/server-methods/talk.ts:917-1006` — `talk.speak` RPC
- `src/tts/tts-synthesis.ts:220-283` — TTS synthesis
- `apps/macos-mlx-tts/` — on-device MLX TTS helper

---

## 12. Summary: What Halbert Should Borrow

### Immediately borrowable patterns (no design work needed)

1. **Voice confirmation gate** (`client-voice-confirmation.ts`) —
   fingerprint the action, one-shot consumption, 2-minute TTL, match
   affirmations and refusals, use finalized transcripts only. This
   solves Task D2.

2. **Single tool, action-driven schema** — instead of many tools
   (`click`, `type`, `scroll`...), expose one tool with an `action`
   enum. This reduces context window usage and simplifies the model's
   decision space.

3. **Frame-bound coordinates** — screenshot coordinates must echo the
   screenshot's `frameId`. Display changes fail closed. This prevents
   stale-coordinate disasters.

4. **Screenshots are model-only** — never auto-delivered to chat.
   Treat screen content as untrusted (prompt injection risk).

5. **Provider abstraction with no fallback** — the agent can't choose
   the provider. Provider selection is node-local. A provider failure
   is an unavailable result, not a silent fallback.

6. **MCP: wrap existing tools, don't reimplement** — the MCP server
   adapter calls the same `AnyAgentTool.execute` that the agent uses.
   One tool implementation, multiple exposure paths.

### Architectural patterns to study for the longer term

7. **Node capability advertisement** — nodes publish `caps`,
   `commands`, `permissions`; the gateway selects and invokes. This is
   the mature version of Halbert's federated multi-node vision.

8. **Layered authorization** — tool policy + command policy + pairing
   approval + local toggle + OS permission + foreground state. All
   must agree.

9. **Plugin manifest-first approach** — read metadata without executing
   code. Cheap discovery, security review before activation.

10. **The consult pattern** — separate voice conversation from tool
    execution, bridged by a single function tool. The realtime provider
    handles audio; OpenClaw handles tools.

### What OpenClaw does that Halbert should NOT copy

11. **TypeScript monorepo** — Halbert is Python. Don't switch.
12. **SQLite for all runtime state** — Halbert uses different storage.
    The principle (canonical state, not sidecar files) is good, but the
    implementation should follow Halbert's existing patterns.
13. **Plugin system complexity** — OpenClaw's plugin system is
    production-grade but complex. Halbert's `register_*_tools()` pattern
    is sufficient for now; a full plugin system is a future direction.

---

## 13. Impact on the Halbert Implementation Plan

Based on this research, the following changes to the plan
(`PLAN-VOICE-ASSISTANT-APP-UI-ACCESS-2026-09-07.md`) are recommended:

### D2 (Desktop control safety framework)
- **Downgrade from fable/max to opus/xhigh**
- **Add reference:** Study `src/talk/client-voice-confirmation.ts` for
  the confirmation pattern
- **Add to design:** Fingerprint the action (hash tool name + params),
  one-shot consumption, 2-minute TTL, match affirmations and refusals,
  use finalized transcripts only
- **Add to design:** Categorize tools by impact — mutating external-state
  tools are gated; local reversible edits are not

### B1 (MCP client library)
- **Reference:** Study `src/agents/agent-bundle-mcp-runtime.ts` for
  transport handling, session expiry, paginated tool discovery
- **Add:** Support node-hosted MCP servers (MCP servers running on
  Halbert nodes, not just the main machine)

### B3 (MCP safety)
- **Upgrade from opus/high to opus/xhigh**
- **Add reference:** Study OpenClaw's layered authorization approach
- **Add to design:** Multiple authorization layers (tool policy +
  command policy + pairing + local toggle + OS permission) rather than
  just per-server config

### C1 (AX helper binary)
- **Add key insight:** The helper must be spawned by the app process
  to inherit TCC permissions (Accessibility, Screen Recording). Study
  how OpenClaw's CUA daemon is "spawned directly as an app child" to
  inherit the app's TCC grants.

### D1 (Interaction primitives)
- **Validate:** Single tool, action-driven schema (like OpenClaw's
  `computer` tool) rather than many separate tools
- **Add:** Frame-bound coordinates — screenshot coordinates must echo
  the screenshot's frame ID; display changes fail closed

### New task: B6 (MCP server exposure)
- **Not in original plan**
- **Add:** Expose Halbert's own tools as an MCP server, so other AI
  agents can use Halbert's system admin tools
- **Model:** sonnet, **Effort:** high
- **Reference:** `src/mcp/plugin-tools-serve.ts` and
  `src/mcp/plugin-tools-handlers.ts`

### G1 (Mobile companion node)
- **Downgrade from fable/max to fable/xhigh**
- **Reference:** OpenClaw's entire node architecture is a production
  reference for Halbert's federated multi-node vision
