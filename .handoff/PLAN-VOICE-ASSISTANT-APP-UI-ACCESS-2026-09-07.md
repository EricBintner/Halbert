# IMPLEMENTATION PLAN: Voice Assistant App UI Access

**Date:** 2026-09-07
**Author:** Devin session
**Status:** Plan for review — no implementation started
**Related:** RESEARCH-VOICE-ASSISTANT-APP-UI-ACCESS-2026-09-07.md (the research doc this plan is built from)
**Predecessor:** RESEARCH-UNIFIED-SYSTEM-ONTOLOGY-2026-09-07.md

---

## 0. How to Read This Document

This is a verbose implementation plan for giving Halbert the ability to
interface with other applications' UIs. It is built directly on the
research document (`RESEARCH-VOICE-ASSISTANT-APP-UI-ACCESS-2026-09-07.md`)
which maps the three mechanism tiers (structured API, accessibility
tree, screenshot+coordinate) and the current 2026 ecosystem.

Each workstream below is broken into tasks. Every task has:

- **Model tier:** Which AI model should be assigned the work
  - `fable` — the most capable model, for the hardest
    architectural/creative/safety-critical work
  - `opus` — large model, for complex implementation and
    architectural decisions with non-obvious tradeoffs
  - `sonnet` — medium model, for well-scoped implementation tasks
    that follow existing patterns with clear specs
- **Effort level:** How hard the model should work on it
  - `ultracode` — maximum reasoning depth, for the hardest problems
  - `max` — very high effort, exhaustive analysis
  - `xhigh` — extra high effort, thorough but bounded
  - `high` — solid, careful implementation of understood patterns
  - `med` — medium effort, straightforward work with clear specs
- **Dependencies:** What must be done first
- **Acceptance criteria:** What "done" means
- **Risks:** What could go wrong

The workstreams are labeled A through G. They are not all meant to be
done — Section 12 gives the recommended sequencing and which to defer.

---

## 1. Goal Statement

Give Halbert, as a voice assistant, the ability to:

1. **Read** what's on the screen in other applications (structured, not
   just screenshots)
2. **Act** on other applications — send emails, create calendar events,
   control media playback, fill forms, click buttons
3. **Connect** to applications that expose their own interfaces (MCP
   servers, App Intents, scripting dictionaries) so Halbert can drive
   them through their native APIs rather than screen-scraping
4. **Discover** what apps are running and which ones are controllable,
   and expose that knowledge to the agent as context

The north star: a user can say "Halbert, send an email to Sarah saying
I'll be late" and Halbert generates and executes the right AppleScript
in Mail, confirms the action verbally, and the email is sent — without
the user touching the keyboard.

---

## 2. Architectural Foundation (What Halbert Already Has)

Before describing new work, this section documents the existing
infrastructure that new work will build on. Every workstream below
plugs into these systems.

### 2.1 Tool Registration Pattern

Halbert's tool system follows a consistent pattern. A tool module
exports a `SCHEMAS` dict and a `HANDLERS` dict, plus a
`register_*_tools(tool_executor)` function. The agent init code in
`dashboard/routes/agent.py` calls each registrar, usually wrapped in a
try/except so a failure in one module doesn't break the agent.

Example (from `halbert_core/tools/gpu_tools.py`, lines 1188-1201):

```python
def register_gpu_tools(tool_executor) -> None:
    for name, schema in GPU_TOOL_SCHEMAS.items():
        handler = GPU_TOOL_HANDLERS.get(name)
        if handler:
            tool_executor.register(name, handler, schema)
        else:
            logger.warning(f"GPU tool '{name}' has schema but no handler — skipped")
    logger.info("Registered GPU tools (...)")
```

The `ToolExecutor.register(name, handler, schema)` method (line 371)
simply stores the handler and schema in dicts. Every new tool module
follows this exact pattern.

### 2.2 Capability Gating

Halbert has a capability system (`halbert_core/capabilities.py`) that
controls which features are active. Capabilities are `CAP_*` string
constants (e.g., `CAP_TERMINAL`, `CAP_SOURCEPREP`, `CAP_WEB`,
`CAP_AUDIO`). They are set by variant presets (sysadmin vs. home) and
can be overridden in `being.yml`. The `has_capability(cap)` function
checks if a capability is available.

Agent init gates tool registration on capabilities. Example (from
`dashboard/routes/agent.py`, lines 172-176):

```python
from ...capabilities import has_capability, CAP_SOURCEPREP
if has_capability(CAP_SOURCEPREP):
    rag_service = SourcePrepAdapter()
```

New capabilities for app UI access would follow this pattern: define
`CAP_APPLESCRIPT`, `CAP_MCP_CLIENT`, `CAP_DESKTOP_CONTROL`, etc., add
them to `ALL_CAPABILITIES`, set defaults in presets, and gate
registration on them.

### 2.3 Config File Gating

Some features are gated by config files rather than capabilities. The
vision subsystem is the model example: all vision features are OFF by
default and must be explicitly enabled in `~/.config/halbert/vision_config.yml`.
The config is read on every capture attempt (not cached) so changes
take effect immediately.

Agent init checks this (from `dashboard/routes/agent.py`, lines 147-149):

```python
from ...vision.config import is_screen_capture_enabled, is_webcam_enabled
if is_screen_capture_enabled() or is_webcam_enabled():
    tool_executor.register_vision_tools()
```

Desktop control features should follow this same pattern — a
`desktop_control_config.yml` that is OFF by default, read on every
tool call, and requires explicit user opt-in.

### 2.4 Safety Framework

The `ToolSafetyFramework` (`halbert_core/tools/safety.py`) classifies
tool operations by risk level:

| Level | Behavior |
|-------|----------|
| `SAFE` | Auto-execute, no logging |
| `LOW` | Auto-execute, log for audit |
| `MEDIUM` | Execute, warn user in response |
| `HIGH` | Require explicit user confirmation |
| `CRITICAL` | Block entirely, never execute |

The framework uses pattern-matching rules to classify shell commands.
The `RoleGate` wrapper tightens (never loosens) tool access based on
the speaker's role (admin vs. guest persona).

Desktop control tools are inherently high-risk — clicking and typing
in arbitrary apps can delete data, send messages, make purchases. The
safety framework integration is the hardest part of this entire plan.

### 2.5 Vision Subsystem (Existing Tier 3 Infrastructure)

Halbert already has a vision subsystem (`halbert_core/vision/`) that
can capture screenshots and webcam frames, run OCR, redact sensitive
content, detect motion, and watch zones. This is the existing Tier 3
(screenshot-based) infrastructure. Any desktop control work would
build on this for the screenshot fallback path.

### 2.6 Discovery Engine

The Discovery Engine (`halbert_core/discovery/`) has a pluggable
scanner registry that probes the system for hardware, services,
network config, etc. New scanners follow a consistent pattern: inherit
from `BaseScanner`, implement `scan()`, register in the engine. The
GPU and AI accelerator scanners (recently built) are the latest
examples.

A "scriptable apps" scanner would follow this same pattern — scan for
apps with `.sdef` files, apps with App Intents, and running apps, and
expose them as discovery results that the agent can use as context.

---

## 3. Workstream A: AppleScript / JXA Tool (Tier 1, macOS)

### 3.0 Overview

Register a tool that lets the agent execute AppleScript / JXA commands
via `osascript`. This gives Halbert structured control over every
scriptable macOS app — Mail, Safari, Calendar, Music, Notes, Reminders,
Messages, Finder, Photos, plus third-party scriptable apps (OmniFocus,
BBEdit, etc.).

This is the **highest ROI workstream**: days of work, immediate
voice-controllable access to the apps people use every day. It also
reveals what users actually want to do, which informs the bigger
investments.

**Mechanism tier:** 1 (structured API / scripting bridge)
**Platforms:** macOS only (Linux has no equivalent; D-Bus is the
rough analog but far less capable for GUI apps)

### 3.1 Task A1: AppleScript Tool Scaffold

**Model:** sonnet
**Effort:** high
**Dependencies:** None — can start immediately
**Estimated scope:** 1 tool module, ~200 lines + tests

Build `halbert_core/tools/applescript_tools.py` following the existing
tool module pattern:

1. Define `APPLESCRIPT_TOOL_SCHEMAS` dict with two tool schemas:
   - `run_applescript` — execute an AppleScript string via `osascript -e`
   - `run_jxa` — execute a JavaScript for Automation string via `osascript -l JavaScript -e`
2. Define `APPLESCRIPT_TOOL_HANDLERS` dict with async handler functions
   that:
   - Accept the script string from args
   - Run `osascript` via `asyncio.create_subprocess_exec`
   - Capture stdout, stderr, and exit code
   - Return a structured result dict: `{success, output, error, exit_code}`
   - Enforce a timeout (default 10 seconds, configurable)
3. Define `register_applescript_tools(tool_executor)` function
4. Register in `dashboard/routes/agent.py` agent init, gated by:
   - Platform check (macOS only — `platform.system() == "Darwin"`)
   - Capability check (`has_capability(CAP_APPLESCRIPT)`)
   - Config check (a new `applescript_config.yml` or reuse a
     `desktop_control_config.yml`, OFF by default)
5. Add `CAP_APPLESCRIPT` to `capabilities.py`:
   - Add to `ALL_CAPABILITIES` set
   - Set `True` in `_PRESET_SYSADMIN`, `False` in `_PRESET_HOME`
   - No probe needed (it's a config decision, not a runtime detection)

**Acceptance criteria:**
- `run_applescript` tool is registered and visible to the agent on macOS
- Executing `tell application "Finder" to name of home folder` returns
  the home folder name
- Executing an invalid script returns a structured error, not a crash
- Timeout is enforced (a script that sleeps for 30s is killed at 10s)
- Tool is NOT registered on Linux
- Tool is NOT registered when capability is off
- Unit tests cover: success, error, timeout, platform gating

**Risks:**
- `osascript` subprocess overhead (~50-100ms per call) — acceptable for
  voice interaction latency
- AppleScript syntax errors produce unhelpful error messages — the
  handler should surface stderr clearly so the agent can self-correct

### 3.2 Task A2: AppleScript Safety Classifier

**Model:** opus
**Effort:** high
**Dependencies:** A1 (tool scaffold must exist to integrate safety into)
**Estimated scope:** Safety rule definitions, ~300 lines + tests

This is the hard part. AppleScript can do anything — delete files via
Finder, send emails via Mail, erase disks, empty the trash, move items
to Trash. The safety framework needs to classify AppleScript commands
by risk level before execution.

Approach:
1. Define pattern-based safety rules in `safety.py` (or a new
   `applescript_safety.py` module) that match known-dangerous
   AppleScript patterns:
   - `delete`, `empty trash`, `erase` → CRITICAL or HIGH
   - `send` (in Mail context) → HIGH (sends real email)
   - `move to trash` → HIGH
   - `make new` (creates objects) → MEDIUM
   - `set` (modifies properties) → MEDIUM
   - `get`, `name of`, `count of` → SAFE (read-only)
2. The classifier should parse the script for target application
   context — `tell application "Finder" to delete` is different from
   `tell application "Calendar" to delete` (Calendar doesn't have
   destructive delete in the same way)
3. Integrate with the existing `ToolSafetyFramework` so the risk level
   flows through to the confirmation gating system
4. The `RoleGate` should block AppleScript entirely for guest personas
   (guests should not be able to run arbitrary AppleScript)

**Acceptance criteria:**
- `tell application "Finder" to name of home folder` → SAFE, auto-execute
- `tell application "Mail" to send ...` → HIGH, requires confirmation
- `tell application "Finder" to delete item "x"` → HIGH, requires confirmation
- `do shell script "rm -rf /"` → CRITICAL, blocked entirely
- Guest persona cannot invoke `run_applescript` at all
- Tests cover each risk level with representative scripts
- The classifier handles multi-statement scripts (classifies the
  highest-risk statement in the block)

**Risks:**
- AppleScript is Turing-complete and can obfuscate intent (variables,
  loops, computed targets). A pattern-based classifier will never be
  perfect. The mitigation is: default to MEDIUM for anything that
  doesn't match a known-safe pattern, and HIGH for anything that
  touches a known-dangerous verb.
- `do shell script` is an escape hatch that bypasses AppleScript
  safety entirely — it must be classified as at least HIGH, and
  patterns like `do shell script "rm"` must be CRITICAL.

### 3.3 Task A3: Scriptable App Discovery Scanner

**Model:** sonnet
**Effort:** med
**Dependencies:** None (independent of A1/A2)
**Estimated scope:** 1 scanner, ~150 lines + tests

Add a scanner to the Discovery Engine that finds scriptable macOS apps
and exposes their scripting dictionaries as discovery context. This
lets the agent know "Mail is scriptable, here are its commands" without
the user having to tell it.

1. Create `halbert_core/discovery/scanners/scriptable_apps.py`:
   - `ScriptableAppsScanner(BaseScanner)` with `DiscoveryType.APP`
   - Scan `/Applications/` and `~/Applications/` for `.app` bundles
   - For each app, check for `.sdef` file (either embedded in the
     bundle at `Contents/Resources/*.sdef` or extractable via `sdef`)
   - Parse the `.sdef` XML to extract: app name, bundle ID, commands,
     classes, properties
   - Return discovery items with the app name, bundle ID, and a
     summary of available commands
2. Register in the Discovery Engine for macOS
3. The agent prompt builder can then include "these apps are
   scriptable: Mail (send email, check inbox), Calendar (create
   events), Music (play, pause, skip)..." as context

**Acceptance criteria:**
- Scanner discovers Mail, Safari, Calendar, Music, Notes, Reminders,
  Finder, Messages on a stock macOS install
- Each discovery item includes the app name, bundle ID, and a list of
  available scripting commands (extracted from `.sdef`)
- Scanner does not crash on apps without `.sdef` files
- Scanner is registered only on macOS
- Tests use a mock `.sdef` to verify parsing

**Risks:**
- Some apps have very large `.sdef` files (Finder's is enormous). The
  scanner should summarize, not dump the full dictionary.
- `sdef` extraction can be slow for some apps. Consider caching results
  and only re-scanning when apps are added/removed.

### 3.4 Task A4: AppleScript Prompt Context

**Model:** sonnet
**Effort:** med
**Dependencies:** A3 (needs discovery results to inject)
**Estimated scope:** Prompt builder integration, ~100 lines

Wire the scriptable app discovery results into the agent's system
prompt so the agent knows what apps are available and what commands
they support. This is what makes the agent actually *use* the
AppleScript tool — without it, the agent would have to guess what
apps are scriptable.

1. Add a context injector (following the `ContextInjector` pattern)
   that reads the latest scriptable apps discovery results and
   includes a concise summary in the system prompt
2. Format: "You have access to AppleScript. The following apps are
   scriptable on this machine: Mail (commands: send, check, reply),
   Calendar (commands: create event, list events), Music (commands:
   play, pause, next)..."
3. Gate on `CAP_APPLESCRIPT` — only inject if the capability is on

**Acceptance criteria:**
- Agent system prompt includes scriptable app list when capability is on
- Prompt does not include the list when capability is off
- Prompt is concise (not the full `.sdef` — just app names + key commands)
- Agent can answer "what apps can you control?" based on the injected context

**Risks:**
- Prompt bloat — if there are many scriptable apps, the context could
  be large. Mitigation: only include apps that are actually running,
  or limit to the top N most useful apps.

---

## 4. Workstream B: MCP Client Capability (Tier 1, Cross-Platform)

### 4.0 Overview

Make Halbert an MCP client. It connects to local and remote MCP servers
and merges their tools into its tool registry. This is the **strategic
bet** — as more apps and services ship MCP servers (Linear, GitHub,
Slack, filesystem, browser, desktop control), Halbert automatically
gains the ability to control them without writing custom integrations.

This is the most architecturally significant workstream. It touches the
core tool executor, the agent init, the capabilities system, and
introduces a new lifecycle concern (managing external server
connections).

**Mechanism tier:** 1 (structured API — MCP is the standard protocol)
**Platforms:** Cross-platform (MCP is transport-agnostic)

### 4.1 Task B1: MCP Client Library Integration

**Model:** opus
**Effort:** xhigh
**Dependencies:** None — can start immediately
**Estimated scope:** New `halbert_core/mcp/` submodule, ~800 lines + tests

Build the MCP client infrastructure that connects to MCP servers and
discovers their tools.

1. Create `halbert_core/mcp/client.py`:
   - `MCPClient` class that manages connections to multiple MCP servers
   - Support both transports: stdio (local servers launched as
     subprocesses) and Streamable HTTP (remote servers)
   - For stdio: launch the server process, communicate over stdin/stdout
     using JSON-RPC
   - For HTTP: connect to the server URL, communicate over Streamable HTTP
   - Implement MCP protocol handshake: `initialize`, `initialized`
   - Implement tool discovery: `tools/list` → get tool schemas
   - Implement tool execution: `tools/call` → invoke a tool, get result
   - Implement resource discovery: `resources/list`, `resources/read`
   - Handle connection lifecycle: connect, reconnect, disconnect, timeout
2. Create `halbert_core/mcp/config.py`:
   - `MCPClientConfig` dataclass loaded from `~/.config/halbert/mcp_config.yml`
   - Config format:
     ```yaml
     servers:
       - name: filesystem
         transport: stdio
         command: npx
         args: ["-y", "@modelcontextprotocol/server-filesystem", "/Users/eric"]
       - name: linear
         transport: http
         url: https://mcp.linear.app/sse
         auth:
           type: bearer
           token_env: LINEAR_MCP_TOKEN
     ```
   - Config is read on every tool call (not cached) — same pattern as
     vision config, so changes take effect without restart
3. Create `halbert_core/mcp/registry.py`:
   - `MCPToolRegistry` that tracks which tools come from which server
   - Maps MCP tool names to Halbert tool names (namespaced:
     `mcp__filesystem__read_file`, `mcp__linear__list_issues`)
   - Handles tool name collisions between servers

**Acceptance criteria:**
- Can connect to a stdio MCP server (e.g., the filesystem server) and
  list its tools
- Can connect to an HTTP MCP server and list its tools
- Can call a tool on a connected server and get a structured result
- Connection failures are logged and don't crash the agent
- Config is re-read on each tool call (hot-reload of server config)
- Tests use a mock MCP server (or the in-process test server from the
  MCP SDK) to verify connect/list/call/disconnect

**Risks:**
- MCP SDK Python package availability and version compatibility — need
  to verify the official `mcp` Python SDK is stable and compatible with
  Halbert's Python 3.11+ runtime
- Server process lifecycle management — stdio servers are subprocesses
  that need to be launched, monitored, and cleaned up. A crashed
  server needs reconnection logic.
- The Haloysius Subtractive Contract (from CLAUDE.md): only 2 hard
  dependencies (`pyyaml`, `requests`). The MCP client must be a lazy
  optional extra — imported only when `CAP_MCP_CLIENT` is on, not a
  hard dependency.

### 4.2 Task B2: MCP Tool Registration Bridge

**Model:** opus
**Effort:** high
**Dependencies:** B1 (client library must exist)
**Estimated scope:** ~400 lines + tests

Bridge MCP server tools into Halbert's existing `ToolExecutor` so the
agent sees them as native tools.

1. Create `halbert_core/mcp/bridge.py`:
   - `register_mcp_tools(tool_executor, mcp_client)` function
   - For each connected MCP server, call `tools/list`
   - For each MCP tool, create an async handler wrapper that:
     - Calls `mcp_client.call_tool(server_name, tool_name, args)`
     - Converts the MCP result to Halbert's `ExecutionResult` format
     - Handles errors, timeouts, and connection failures gracefully
   - Register each tool with `tool_executor.register(name, handler, schema)`
   - Tool names are namespaced: `mcp__{server_name}__{tool_name}`
2. Integrate into agent init (`dashboard/routes/agent.py`):
   - Check `has_capability(CAP_MCP_CLIENT)`
   - If on, load MCP config, create `MCPClient`, connect to all
     configured servers
   - Call `register_mcp_tools(tool_executor, mcp_client)`
   - Wrap in try/except so MCP failures don't break the agent
3. Add `CAP_MCP_CLIENT` to capabilities:
   - `ALL_CAPABILITIES` set
   - `True` in `_PRESET_SYSADMIN`, `False` in `_PRESET_HOME`
   - No probe (config-driven, not runtime detection)

**Acceptance criteria:**
- MCP server tools appear in the agent's tool list as
  `mcp__{server}__{tool}` names
- Agent can call an MCP tool and get the result
- If an MCP server is not running, its tools are simply absent (no
  crash, no error in agent response)
- Adding a new server to `mcp_config.yml` and restarting makes its
  tools available
- Removing a server from config and restarting removes its tools
- Tests verify tool registration, namespacing, and graceful degradation

**Risks:**
- Tool schema format differences between MCP and Halbert's expected
  format — MCP schemas are JSON Schema, Halbert uses OpenAI function
  calling format. The bridge must convert.
- Large numbers of MCP tools could bloat the agent's context window.
  Mitigation: consider tool filtering or lazy tool exposure (only
  register tools the agent is likely to need based on context).

### 4.3 Task B3: MCP Safety Integration

**Model:** opus
**Effort:** high
**Dependencies:** B2 (tools must be registered to gate them)
**Estimated scope:** ~200 lines + tests

Integrate MCP tools into Halbert's safety framework. MCP tools can do
anything — the filesystem server can delete files, a desktop control
server can click things, a browser server can navigate to URLs. The
safety framework needs to gate them.

1. Define a risk classification strategy for MCP tools:
   - **Default:** MEDIUM (unknown tools require a warning)
   - **Configurable per-server:** `mcp_config.yml` can specify a
     `risk_override` per server or per tool:
     ```yaml
     servers:
       - name: filesystem
         risk_override: high  # all tools from this server are HIGH
       - name: read-only-api
         risk_override: safe  # all tools from this server are SAFE
     ```
   - **Per-tool overrides:** individual tools can be classified in config
2. The `RoleGate` should block all MCP tools for guest personas by
   default (guests should not be able to invoke external MCP servers)
3. HIGH-risk MCP tools go through the existing confirmation gating

**Acceptance criteria:**
- MCP tools default to MEDIUM risk (warn user in response)
- Config can override risk per-server and per-tool
- Guest persona cannot invoke any MCP tool
- HIGH-risk MCP tools require confirmation
- Tests verify default classification, overrides, and guest gating

**Risks:**
- The safety framework's pattern-matching approach doesn't apply to
  MCP tools (they're not shell commands). The per-server/per-tool
  config override is the primary mechanism, which puts the burden on
  the user to classify their MCP servers correctly.

### 4.4 Task B4: MCP Server Health Monitoring

**Model:** sonnet
**Effort:** med
**Dependencies:** B1 (client library)
**Estimated scope:** ~200 lines + tests

Monitor MCP server health and reconnect on failure. A crashed stdio
server or a dropped HTTP connection should be detected and recovered
without agent intervention.

1. Background task (asyncio) that pings each connected server
   periodically (every 30 seconds)
2. If a server is unresponsive, mark its tools as unavailable
3. Attempt reconnection with exponential backoff
4. Log health status for the dashboard to display
5. Expose a `/api/mcp/status` endpoint that shows connected servers,
   their health, and their tool counts

**Acceptance criteria:**
- Server crash is detected within 30 seconds
- Reconnection is attempted automatically
- Agent calls to a disconnected server's tools return a clear error
  ("MCP server 'filesystem' is not connected")
- Dashboard shows MCP server status
- Tests verify health check, reconnection, and error handling

**Risks:**
- Background task lifecycle management in the FastAPI/uvicorn context
- Reconnection storms if a server is permanently down — backoff cap
  is needed

### 4.5 Task B5: MCP Dashboard UI

**Model:** sonnet
**Effort:** med
**Dependencies:** B4 (status endpoint)
**Estimated scope:** 1 React page, ~300 lines + tests

Add an MCP management page to the Halbert dashboard where users can:
1. See connected MCP servers and their health status
2. See the tools each server exposes
3. Add/remove servers (edits `mcp_config.yml`)
4. Set risk overrides per server
5. Test a server connection

This follows the existing dashboard page pattern (like the GPU page,
Settings page, etc.).

**Acceptance criteria:**
- MCP page shows server list with health indicators
- Adding a server via the UI updates `mcp_config.yml` and connects
- Removing a server disconnects and removes its tools
- Risk overrides are editable
- Page is accessible only when `CAP_MCP_CLIENT` is on
- Tests verify rendering, config editing, and status display

**Risks:**
- Config file editing from the UI needs to be safe (atomic writes,
  validation) — follow the existing config editing patterns in the
  Settings page

---

## 5. Workstream C: Accessibility Tree Reader (Tier 2, macOS)

### 5.0 Overview

Register tools that read the macOS Accessibility API (AXUIElement). This
gives the agent *structured eyes* on any running app — it can see the
UI element tree (buttons, text fields, menus, windows) without taking
screenshots. Read-only first; interaction (click/type) comes in
Workstream D.

This is the foundation for all Tier 2 automation. Even read-only, it
lets the agent answer "what's on my screen right now" structurally
instead of via screenshot+vision, which is faster, cheaper, and more
accurate.

**Mechanism tier:** 2 (accessibility tree)
**Platforms:** macOS (Linux equivalent is AT-SPI2, deferred)

### 5.1 Task C1: Accessibility Helper Binary

**Model:** opus
**Effort:** high
**Dependencies:** None
**Estimated scope:** Swift helper binary + Python wrapper, ~600 lines

The macOS Accessibility API (AXUIElement) is a C/Obj-C API. The cleanest
way to access it from Python is a small Swift helper binary that Halbert
calls via subprocess (same pattern as `osascript`, `system_profiler`,
etc. in the existing scanners).

1. Create `halbert_core/tools/desktop_control/ax_helper/`:
   - Swift source file (`ax_helper.swift`) that:
     - Accepts JSON commands on stdin
     - Uses `AXUIElement` API to: list apps, list windows, get element
       tree, find elements by role/name, read element text/properties
     - Returns JSON results on stdout
     - Handles errors gracefully (permission denied, app not found, etc.)
   - Build script that compiles the Swift binary (or ship a prebuilt
     binary, or use `swift run` for development)
2. Create `halbert_core/tools/desktop_control/ax_client.py`:
   - Python wrapper that launches the Swift helper and communicates
     via JSON over stdin/stdout
   - Methods: `list_apps()`, `list_windows(bundle_id)`,
     `get_element_tree(bundle_id, depth)`, `find_elements(bundle_id,
     role, name)`, `read_element(bundle_id, element_id)`
   - Caches the helper process for the session (don't relaunch per call)
3. Permission check: verify Accessibility permission is granted. If
   not, return a clear error message instructing the user to grant it
   in System Settings → Privacy & Security → Accessibility.

**Acceptance criteria:**
- `list_apps()` returns all running apps with bundle IDs and PIDs
- `list_windows("com.apple.Safari")` returns Safari's windows with
  titles and positions
- `get_element_tree("com.apple.Safari", depth=3)` returns a JSON tree
  of UI elements (role, title, value, position, size, enabled state)
- `find_elements("com.apple.Safari", role="AXButton", name="Back")`
  finds the back button
- Clear error when Accessibility permission is not granted
- Helper binary compiles and runs on macOS 14+
- Tests mock the helper binary's JSON output

**Risks:**
- Swift compilation requirement — the build environment needs Xcode
  or Swift toolchain. Consider shipping a prebuilt universal binary.
- Accessibility permission is per-process — the helper binary (or the
  process that launches it) needs the permission. This is a UX hurdle.
- Some apps (Electron/WebView apps) have poor accessibility trees.
  The helper should report what it finds without crashing.
- The Haloysius Subtractive Contract: the Swift binary is a build-time
  artifact, not a Python dependency. This is fine — it doesn't add a
  Python package dependency.

### 5.2 Task C2: Accessibility Reader Tools

**Model:** sonnet
**Effort:** high
**Dependencies:** C1 (helper binary and Python client)
**Estimated scope:** Tool schemas + handlers, ~300 lines + tests

Register the accessibility reader tools with the agent, following the
existing tool registration pattern.

1. Create `halbert_core/tools/desktop_control/accessibility_tools.py`:
   - `AX_TOOL_SCHEMAS` dict with tool schemas:
     - `list_apps` — list running applications
     - `list_windows` — list windows for an app (by bundle ID)
     `get_app_tree` — get the accessibility tree of an app's front window
     - `find_element` — find UI elements by role and/or name
     - `read_element` — read the text/value/properties of an element
   - `AX_TOOL_HANDLERS` dict with async handlers that call `ax_client`
   - `register_accessibility_tools(tool_executor)` function
2. Register in agent init, gated by:
   - Platform check (macOS only)
   - Capability check (`CAP_ACCESSIBILITY_READER`)
   - Config check (`desktop_control_config.yml`, OFF by default)
3. Add `CAP_ACCESSIBILITY_READER` to capabilities

**Acceptance criteria:**
- All 5 tools are registered and visible to the agent on macOS
- `list_apps` returns running apps
- `get_app_tree` returns a structured UI tree for a specified app
- `find_element` finds elements by role/name
- Tools are NOT registered on Linux
- Tools are NOT registered when capability or config is off
- Tests mock the AX client and verify tool schemas + handler logic

**Risks:**
- Large accessibility trees (e.g., a complex web page in Safari) could
  produce very large JSON results. The `get_app_tree` tool should
  accept a `depth` parameter and default to a shallow depth.
- The agent needs to know which bundle ID to use. The `list_apps` tool
  is the entry point — the agent calls it first, then uses bundle IDs
  from the result for subsequent calls.

### 5.3 Task C3: Accessibility Prompt Context

**Model:** sonnet
**Effort:** med
**Dependencies:** C2 (tools must be registered)
**Estimated scope:** ~100 lines

Inject a brief context note into the agent's system prompt when
accessibility tools are available, explaining what the agent can do
and how to use the tools (call `list_apps` first, then use bundle IDs).

This is small but important — without it, the agent may not know to
use the accessibility tools.

**Acceptance criteria:**
- System prompt includes usage guidance when `CAP_ACCESSIBILITY_READER` is on
- Prompt is concise (2-3 sentences)
- Tests verify prompt injection is gated by capability

**Risks:** None significant.

---

## 6. Workstream D: Desktop Interaction Tools (Tier 2+3, macOS)

### 6.0 Overview

Add interaction tools — `click`, `type_text`, `press_key`, `scroll`,
`drag` — backed by the Accessibility API (Tier 2), with
screenshot+coordinate as a fallback (Tier 3) for apps with poor
accessibility trees. This is the full desktop automation stack.

This is the **highest-risk, highest-complexity** workstream. Clicking
and typing in arbitrary apps can do anything: delete data, send
messages, make purchases, change system settings. The safety design
is the core challenge, not the technical implementation.

**Mechanism tier:** 2 (accessibility) + 3 (screenshot fallback)
**Platforms:** macOS

### 6.1 Task D1: Accessibility Interaction Primitives

**Model:** opus
**Effort:** xhigh
**Dependencies:** C1 (AX helper binary), C2 (reader tools)
**Estimated scope:** Extend AX helper + new tools, ~500 lines + tests

Extend the Swift helper binary and Python client to support interaction:

1. Extend `ax_helper.swift` with new commands:
   - `click_element` — perform AXPress on an element by reference
   - `set_value` — set the value of a text field or control
   - `press_key` — send a key event (key chord like `cmd+s`)
   - `scroll` — scroll an element or window
   - `drag` — drag between two elements or coordinates
   - Background-safe input via `CGEventPostToPid` where possible (no
     focus steal, no cursor movement — confirmed working in axcli/silk)
2. Extend `ax_client.py` with corresponding methods
3. Create `halbert_core/tools/desktop_control/interaction_tools.py`:
   - `INTERACTION_TOOL_SCHEMAS` and `INTERACTION_TOOL_HANDLERS`
   - `register_interaction_tools(tool_executor)`
4. Register in agent init, gated by `CAP_DESKTOP_CONTROL` + config

**Acceptance criteria:**
- `click_element` clicks a button by element reference (from `find_element`)
- `set_value` types text into a text field
- `press_key` sends keyboard shortcuts
- Background-safe input works (target app doesn't need to be focused)
- Screenshot fallback: if an element can't be found via accessibility,
  accept (x, y) coordinates and click via CGEvent
- Tests mock the AX client and verify handler logic

**Risks:**
- Background-safe input doesn't work for all apps / all actions. Some
  apps require focus. The tool should fall back to focus+act if
  background-safe fails.
- CGEvent coordinate clicking requires Screen Recording permission
  (in addition to Accessibility). This is a second permission hurdle.
- Interaction with Electron apps is unreliable — AXPress often doesn't
  work. The screenshot+coordinate fallback is essential for these.

### 6.2 Task D2: Desktop Control Safety Framework

**Model:** fable
**Effort:** max
**Dependencies:** D1 (interaction tools must exist to gate them)
**Estimated scope:** Safety rules + confirmation UX, ~500 lines + tests

This is the hardest task in the entire plan. The safety framework for
desktop interaction needs to prevent catastrophic actions while still
being useful. A misclassified click could delete files, send emails,
or make purchases.

Approach:
1. **Per-app risk allowlisting:** A config file
   (`desktop_control_config.yml`) defines which apps the agent is
   allowed to interact with, and at what risk level:
   ```yaml
   apps:
     com.apple.Music:
       allowed: true
       risk: low  # music playback is low-risk
     com.apple.Mail:
       allowed: true
       risk: high  # sending email is high-risk
     com.apple.Finder:
       allowed: true
       risk: high  # file operations are high-risk
     com.apple.SystemPreferences:
       allowed: false  # never let the agent change system settings
   ```
2. **Action classification:**
   - Read-only actions (list_apps, get_app_tree, find_element,
     read_element) → SAFE always
   - Click on a button whose title matches dangerous patterns
     ("Delete", "Send", "Submit", "Confirm", "Erase", "Empty Trash")
     → HIGH, require confirmation
   - Type into a field → MEDIUM (could be typing a password, a
     message, etc.)
   - Press key → MEDIUM (could be cmd+Q, cmd+W, etc.)
   - Any interaction with a non-allowlisted app → CRITICAL, blocked
3. **Confirmation UX for voice:** When a HIGH-risk action needs
   confirmation, the agent should:
   - Describe what it's about to do ("I'm about to click Send in Mail,
     which will send the email to Sarah. Should I proceed?")
   - Wait for voice confirmation ("yes" / "no")
   - If no response within a timeout, abort
   - This is a new interaction pattern — the existing confirmation
     gating is text-based (dashboard). Voice confirmation needs design.
4. **RoleGate:** All interaction tools are blocked for guest personas.
   Read-only accessibility tools (C2) can be allowed for guests at
   the founder's discretion, but interaction is admin-only.

**Acceptance criteria:**
- Agent cannot interact with apps not in the allowlist
- Clicking "Delete" or "Send" buttons requires confirmation
- Typing into fields is classified MEDIUM (warns user)
- System Preferences is blocked by default
- Guest persona cannot use any interaction tool
- Voice confirmation flow works: agent describes action, waits for
  "yes"/"no", executes or aborts
- Tests verify each risk classification and the confirmation flow

**Risks:**
- Button title matching is fragile — a button labeled "Send" in one
  app might be "Send Message" in another, or a localized string. The
  classifier should use substring matching with a curated dangerous-word list.
- The voice confirmation flow is a new UX pattern for Halbert. It
  needs careful design to avoid being annoying (confirming every
  click) or dangerous (never confirming). The per-app risk config is
  the primary lever — low-risk apps auto-execute, high-risk apps
  always confirm.
- This task requires the deepest reasoning about safety tradeoffs.
  That's why it's assigned to fable at max effort.

### 6.3 Task D3: Screenshot+Coordinate Fallback

**Model:** sonnet
**Effort:** high
**Dependencies:** D1 (interaction infrastructure), existing vision subsystem
**Estimated scope:** ~300 lines + tests

For apps where the accessibility tree is poor (Electron apps, canvas
apps, remote desktops), fall back to screenshot+coordinate interaction.

1. Integrate with the existing vision subsystem (`halbert_core/vision/`):
   - Use `ScreenCapture` to take a screenshot of the target app's window
   - Send the screenshot to the vision model with a prompt like "Where
     is the [button name] button? Return coordinates."
   - The vision model returns coordinates
   - Click at those coordinates via CGEvent
2. Register a `click_coordinates` tool that accepts (x, y) and clicks
3. Register a `screenshot_and_find` tool that takes a screenshot and
   uses vision to find an element by description
4. This is explicitly a fallback — the agent should prefer
   accessibility-based interaction and only use screenshot+coordinate
   when accessibility fails

**Acceptance criteria:**
- `click_coordinates` clicks at the specified screen coordinates
- `screenshot_and_find` takes a screenshot, sends to vision model,
  returns element coordinates
- The agent can use this as a fallback when `find_element` returns
  nothing for an Electron app
- Screen Recording permission is required and checked
- Tests mock the vision model and ScreenCapture

**Risks:**
- Vision model latency (3-5 seconds per screenshot analysis) makes
  this slow for multi-step interactions
- Coordinate accuracy depends on display scaling (Retina vs. non-Retina)
- This path is expensive (one vision model call per action)

### 6.4 Task D4: Desktop Control Dashboard UI

**Model:** sonnet
**Effort:** med
**Dependencies:** D1, D2
**Estimated scope:** Settings page section, ~200 lines + tests

Add a "Desktop Control" section to the Settings page where users can:
1. Enable/disable desktop control (toggles `desktop_control_config.yml`)
2. View and edit the app allowlist (which apps the agent can interact with)
3. Set per-app risk levels
4. Check permission status (Accessibility, Screen Recording)
5. View a log of recent desktop control actions

**Acceptance criteria:**
- Settings section appears only when `CAP_DESKTOP_CONTROL` is on
- App allowlist is editable
- Permission status is displayed with a link to System Settings
- Action log shows recent clicks/types with timestamps
- Tests verify rendering and config editing

**Risks:** None significant — follows existing Settings page patterns.

---

## 7. Workstream E: App Intents Integration (Apple Ecosystem)

### 7.0 Overview

If Halbert ships as a macOS app (it has a Tauri shell), it could both
expose and consume App Intents — Apple's sanctioned framework for
inter-app AI automation. This is the most "native" Apple integration
path and it's expanding rapidly (WWDC26 added App Schemas, cross-app
actions, onscreen awareness).

This workstream is **deferred** until the Tauri app packaging is
further along. It requires Halbert to be a proper macOS app bundle,
not just a Python process. It also requires Swift development for the
App Intents implementation.

**Mechanism tier:** 1 (structured API — Apple's native inter-app framework)
**Platforms:** macOS + iOS (Apple ecosystem only)

### 7.1 Task E1: Halbert App Intents Exposure

**Model:** fable
**Effort:** xhigh
**Dependencies:** Tauri app packaging must be complete (external dependency)
**Estimated scope:** Swift App Intents extension, ~800 lines

Expose Halbert's own actions as App Intents so Siri and Shortcuts can
invoke them.

1. Create a Swift App Intents extension in the Tauri app bundle
2. Define App Intents for key Halbert actions:
   - "Check system status" → calls Halbert's `/api/status`
   - "Run a discovery scan" → calls `/api/discovery/scan`
   - "Ask Halbert a question" → sends a message to the agent
   - "List running services" → calls `/api/services`
   - "Check GPU status" → calls `/api/gpu/info`
3. Define App Entities for Halbert's data model (services, devices,
   GPUs, discovery items) so Siri can reference them
4. Conform to relevant App Schemas (`.system` domain for system
   admin actions) so Apple Intelligence understands Halbert's capabilities
5. Test with Siri and Shortcuts

**Acceptance criteria:**
- "Hey Siri, ask Halbert to check system status" works
- Halbert actions appear in the Shortcuts app
- App Entities are searchable via Spotlight
- Conforms to at least one App Schema domain
- Tests use the new AppIntentsTesting framework (WWDC26)

**Risks:**
- Requires Tauri app to be a proper macOS app bundle with Swift
  extension support — this is a significant packaging change
- App Intents require code signing and notarization for distribution
- Siri integration testing is inherently manual (can't fully automate
  voice interaction tests)

### 7.2 Task E2: App Intents Consumption

**Model:** fable
**Effort:** xhigh
**Dependencies:** E1 (App Intents infrastructure)
**Estimated scope:** ~600 lines

Let Halbert invoke other apps' App Intents programmatically. This is
the reverse direction — Halbert calls other apps' exposed actions.

1. Build an App Intents invocation bridge in Swift:
   - Discover apps that expose App Intents (via `AppIntentManager`)
   - List their available intents and parameters
   - Invoke an intent by name with parameters
   - Return the result to Halbert's agent
2. Register as agent tools: `list_app_intents`, `invoke_app_intent`
3. This is Apple's sanctioned path for inter-app automation — no
   accessibility permission needed, no screenshot fallback

**Acceptance criteria:**
- `list_app_intents` returns intents exposed by installed apps
- `invoke_app_intent` invokes an intent and returns the result
- Works with Apple's built-in apps (Mail, Calendar, Safari, etc.)
- No Accessibility permission required (this is the key advantage
  over Workstream C/D)
- Tests verify intent discovery and invocation

**Risks:**
- App Intents adoption by third-party apps is still limited (mostly
  Apple apps and early adopters). The value grows as more apps adopt it.
- The Swift bridge needs to handle intent parameters of various types
  (strings, integers, App Entities, enums)
- This is deep Apple ecosystem work requiring Swift expertise — hence
  fable at xhigh

---

## 8. Workstream F: Scriptable App Discovery (Discovery Engine)

### 8.0 Overview

This was already described as Task A3 in Workstream A. It's listed
separately here because it can be done independently and has value
even without the AppleScript tool — it tells the agent (and the user)
what apps on the system are controllable.

**Status:** See Task A3 (Section 3.3). Same scope, same model/effort.

---

## 9. Workstream G: Cross-Device Node Pattern (Federated)

### 9.0 Overview

The phone-to-computer bridge pattern (Antigravity Phone Chat, Antimatter,
OpenClaw nodes) suggests an opportunity: a Halbert node on a phone (or
a lightweight mobile companion) that gives the desktop Halbert *remote
access* to the phone's screen, camera, and sensors.

This is the **largest scope** workstream and is already partially on
the roadmap via the federated multi-node architecture work. The
research here validates the direction — it's what OpenClaw and the
Antigravity bridge ecosystem are all doing.

**Status:** Deferred. This depends on the federated multi-node
architecture being complete (in progress, per the node list rail
design handoff). Do not start until that work is done.

### 9.1 Task G1: Mobile Companion Node Design

**Model:** fable
**Effort:** max
**Dependencies:** Federated multi-node architecture (in progress)
**Estimated scope:** Design document + prototype, ~2000 lines

Design and prototype a mobile companion node that:
1. Runs on iOS or Android (likely a lightweight app, not full Halbert)
2. Pairs with a desktop Halbert node (following the existing peer
   pairing pattern)
3. Exposes the phone's screen, camera, microphone, and sensors to the
   desktop Halbert
4. The desktop Halbert can then "see" the phone's screen and "act" on
   it (via accessibility on Android, or via App Intents on iOS)

This is a massive scope item that needs its own research and design
phase before implementation. It's listed here for completeness and to
show where the architecture is heading.

**Acceptance criteria:** (For the design document, not implementation)
- Design document covers: platform choice (iOS vs. Android vs. both),
  pairing protocol, security model, latency budget, capability surface
- Prototype demonstrates: phone → desktop pairing, screen capture
  streaming, at least one remote action

**Risks:**
- Android AccessibilityService automation violates Play Store policy
  (sideloaded only) — see research doc Section 2.6
- iOS is even more restricted — App Intents is the only sanctioned path
- This is a multi-month effort and should not be started until the
  federated architecture is stable

---

## 10. Dependency Graph

```
A1 (AppleScript scaffold) ──┐
                             ├── A2 (Safety classifier)
                             │
A3 (Scriptable app scanner) ── A4 (Prompt context)

B1 (MCP client library) ──── B2 (Tool registration bridge) ──── B3 (Safety)
                         │
                         └── B4 (Health monitoring) ──── B5 (Dashboard UI)

C1 (AX helper binary) ──── C2 (Reader tools) ──── C3 (Prompt context)
                         │
                         └── D1 (Interaction primitives) ──── D2 (Safety framework)
                                                              │
                                                              └── D3 (Screenshot fallback)
                                                                  │
                                                                  └── D4 (Dashboard UI)

E1 (App Intents exposure) ──── E2 (App Intents consumption)
  ↑
  └── Tauri app packaging (external dependency)

G1 (Mobile companion node)
  ↑
  └── Federated multi-node architecture (in progress)
```

**Independent start points (no dependencies):**
- A1, A3, B1, C1 — can all begin immediately in parallel

**Critical path (longest dependency chain):**
- C1 → D1 → D2 → D3 → D4 (desktop control, ~5 tasks)
- B1 → B2 → B3 (MCP client, ~3 tasks)

---

## 11. Model Tier and Effort Summary

| Task | Name | Model | Effort | Rationale |
|------|------|-------|--------|-----------|
| A1 | AppleScript tool scaffold | sonnet | high | Well-scoped, follows existing pattern. Main work is subprocess wrapping + tests. |
| A2 | AppleScript safety classifier | opus | high | Pattern-based classification of a Turing-complete language. Needs careful thought about dangerous patterns and escape hatches (`do shell script`). |
| A3 | Scriptable app discovery scanner | sonnet | med | Follows existing scanner pattern. Parsing `.sdef` XML is straightforward. |
| A4 | AppleScript prompt context | sonnet | med | Simple context injection, follows existing `ContextInjector` pattern. |
| B1 | MCP client library integration | opus | xhigh | Architecturally significant. New subsystem with connection lifecycle, two transports, protocol handshake. Must respect Haloysius Subtractive Contract (lazy import). |
| B2 | MCP tool registration bridge | opus | high | Bridges two tool systems with different schema formats. Namespacing, error handling, graceful degradation. |
| B3 | MCP safety integration | opus | high | Per-server/per-tool risk classification. No pattern-matching available (MCP tools aren't shell commands). Config-driven. |
| B4 | MCP server health monitoring | sonnet | med | Background task with reconnection logic. Well-understood pattern. |
| B5 | MCP dashboard UI | sonnet | med | Follows existing dashboard page pattern. Config editing + status display. |
| C1 | Accessibility helper binary | opus | high | Swift + AXUIElement API. Platform-specific. Permission handling. New build artifact type in the project. |
| C2 | Accessibility reader tools | sonnet | high | Tool registration following existing pattern. 5 tools, mock-tested. |
| C3 | Accessibility prompt context | sonnet | med | Simple context injection. |
| D1 | Accessibility interaction primitives | opus | xhigh | Extends C1 with click/type/press/scroll/drag. Background-safe input. CGEvent fallback. Electron app reliability issues. |
| D2 | Desktop control safety framework | fable | max | The hardest task. Preventing catastrophic actions while staying useful. Per-app allowlisting, dangerous-button detection, voice confirmation UX. Requires deepest reasoning about safety tradeoffs. |
| D3 | Screenshot+coordinate fallback | sonnet | high | Integrates existing vision subsystem with coordinate clicking. Vision model latency is the main challenge. |
| D4 | Desktop control dashboard UI | sonnet | med | Settings page section. Follows existing patterns. |
| E1 | Halbert App Intents exposure | fable | xhigh | Deep Apple ecosystem work. Swift App Intents extension in Tauri bundle. App Schemas conformance. Requires Tauri packaging to be complete. |
| E2 | App Intents consumption | fable | xhigh | Swift bridge to invoke other apps' intents. Various parameter types. Apple's sanctioned inter-app path. |
| G1 | Mobile companion node design | fable | max | Largest scope. Multi-month. Needs its own research phase. Depends on federated architecture. |

---

## 12. Recommended Sequencing

### Phase 1: Immediate Value (Weeks 1-2)

**Do these first.** They are independent, high-ROI, and reveal what
users actually want.

1. **A1 — AppleScript tool scaffold** (sonnet/high)
   - Days of work. Immediate voice control over Mail, Calendar, Music,
     Safari, Notes, Reminders.
2. **A3 — Scriptable app discovery scanner** (sonnet/med)
   - Parallel to A1. Tells the agent what's controllable.
3. **A2 — AppleScript safety classifier** (opus/high)
   - After A1. Makes AppleScript safe enough for voice use.
4. **A4 — AppleScript prompt context** (sonnet/med)
   - After A3. Makes the agent actually use the tool.

**Deliverable:** Halbert can send emails, create calendar events,
control music playback, and read/write Notes via voice — all through
AppleScript, with safety gating.

### Phase 2: Strategic Platform (Weeks 3-6)

**This is the long-term bet.** MCP is where the ecosystem is heading.

5. **B1 — MCP client library** (opus/xhigh)
   - The foundation. Can start in parallel with Phase 1.
6. **B2 — MCP tool registration bridge** (opus/high)
   - After B1. Makes MCP tools available to the agent.
7. **B3 — MCP safety integration** (opus/high)
   - After B2. Gates MCP tools by risk.
8. **B4 — MCP health monitoring** (sonnet/med)
   - After B1. Keeps connections alive.
9. **B5 — MCP dashboard UI** (sonnet/med)
   - After B4. User-facing management.

**Deliverable:** Halbert is an MCP client. Any MCP server the user
configures (filesystem, Linear, GitHub, browser, desktop control)
automatically extends Halbert's capabilities. This subsumes much of
Workstream D because the user can connect a desktop-control MCP
server (like open-computer-use or axcli) instead of Halbert building
its own.

### Phase 3: Native Eyes (Weeks 5-8, can overlap with Phase 2)

**Only if Phase 2's MCP approach doesn't cover the need.** Building
native accessibility is expensive; the MCP client may make it
unnecessary if users connect a desktop-control MCP server.

10. **C1 — Accessibility helper binary** (opus/high)
11. **C2 — Accessibility reader tools** (sonnet/high)
12. **C3 — Accessibility prompt context** (sonnet/med)

**Deliverable:** Halbert can read any running app's UI tree
structurally, without screenshots.

### Phase 4: Native Hands (Weeks 8-14, only if Phase 3 is done)

**Highest risk, highest complexity.** Only do this if the MCP approach
(Phase 2) doesn't provide sufficient desktop control and native
accessibility (Phase 3) is already in place.

13. **D1 — Interaction primitives** (opus/xhigh)
14. **D2 — Safety framework** (fable/max) — the critical safety task
15. **D3 — Screenshot fallback** (sonnet/high)
16. **D4 — Dashboard UI** (sonnet/med)

**Deliverable:** Halbert can click, type, and interact with any
running app, with comprehensive safety gating and voice confirmation.

### Deferred

- **Workstream E (App Intents):** Wait until Tauri app packaging is
  further along. This is the right long-term Apple integration story
  but depends on Halbert being a proper macOS app bundle.
- **Workstream G (Mobile companion node):** Wait until federated
  multi-node architecture is complete. This is a multi-month effort
  that needs its own research and design phase.

---

## 13. Open Decisions for Review

Before implementation begins, the following decisions need to be made
by the founder:

### D1: Scope question — what is Halbert?

> Is Halbert a voice assistant that *can* control apps, or a desktop
> automation agent that *has* a voice interface?

These are different products. If Halbert is primarily a system admin
assistant (the current positioning), then Workstream A (AppleScript
for Mail/Calendar/Music) + Workstream B (MCP client for structured
integrations) may be sufficient. If Halbert should be a general-purpose
desktop automation agent, then Workstreams C and D are necessary.

**Recommendation:** Start with A + B (Phase 1 + 2). Let usage patterns
reveal whether C and D are needed. Don't build desktop control
speculatively.

### D2: Platform priority — macOS-first or cross-platform?

AppleScript (Workstream A) and App Intents (Workstream E) are
macOS-only. Accessibility (Workstream C/D) is macOS now but AT-SPI2
on Linux later. MCP (Workstream B) is cross-platform.

**Recommendation:** macOS-first for A (the user is on macOS and it's
the highest ROI). Cross-platform for B (MCP is inherently
cross-platform). Defer Linux accessibility until there's a Linux user
who needs it.

### D3: Voice confirmation UX — how should it work?

When Halbert is about to do something high-risk (click "Send" in Mail,
delete a file), how does the voice interaction model handle
confirmation? Options:

- **Option A:** Always describe + ask. "I'm about to send an email to
  Sarah. Say 'yes' to confirm." — Safe but verbose.
- **Option B:** Configurable per-app. Low-risk apps (Music) auto-execute.
  High-risk apps (Mail, Finder) always confirm. — Balanced.
- **Option C:** Trust the safety framework's existing text-based
  confirmation (dashboard popup). Voice user has to look at the screen.
  — Simple but defeats the purpose of voice.

**Recommendation:** Option B. This needs design work as part of Task D2.

### D4: MCP server default configuration

Should Halbert ship with any MCP servers pre-configured? Options:

- **Option A:** None. User adds their own. — Clean but requires
  technical knowledge.
- **Option B:** A curated set of safe, useful servers (e.g., a
  read-only filesystem server for the home directory). — Convenient
  but opinionated.
- **Option C:** A discovery mechanism that suggests MCP servers based
  on what's installed (e.g., if Linear is detected, suggest the Linear
  MCP server). — Smart but complex.

**Recommendation:** Option A for now. Option C is a future enhancement
that ties into the Discovery Engine.

### D5: Build vs. buy for desktop control

Should Halbert build its own accessibility/desktop control stack
(Workstreams C + D, ~3000 lines, months of work) or should it be an
MCP client and let users connect existing desktop-control MCP servers
(open-computer-use, axcli, silk, etc.)?

**Recommendation:** Buy (MCP client). Let the ecosystem do the heavy
lifting. Halbert's value is the voice assistant + safety framework +
agent loop, not reimplementing accessibility automation. Only build
native if the MCP servers prove insufficient.

### D6: AppleScript safety — how aggressive?

The AppleScript safety classifier (Task A2) needs a default risk level
for unrecognized scripts. Options:

- **Option A:** Default to MEDIUM (warn but execute). — Permissive.
- **Option B:** Default to HIGH (require confirmation). — Safe but
  annoying for simple scripts.
- **Option C:** Default to CRITICAL (block). — Very safe but makes the
  tool nearly useless for anything not explicitly allowlisted.

**Recommendation:** Option B. Better to over-confirm than to
auto-execute an unknown script. The allowlist of known-safe patterns
(get, name of, count of) keeps read-only scripts frictionless.

---

## 14. Files That Will Be Created or Modified

### New files (Workstream A)
- `halbert_core/halbert_core/tools/applescript_tools.py` — tool module
- `halbert_core/halbert_core/tools/applescript_safety.py` — safety classifier (or extend `safety.py`)
- `halbert_core/halbert_core/discovery/scanners/scriptable_apps.py` — discovery scanner
- `halbert_core/tests/test_applescript_tools.py` — tests
- `halbert_core/tests/test_applescript_safety.py` — tests
- `halbert_core/tests/test_scriptable_apps_scanner.py` — tests
- `halbert_core/config/applescript_config.yml` — default config (or part of `desktop_control_config.yml`)

### New files (Workstream B)
- `halbert_core/halbert_core/mcp/client.py` — MCP client
- `halbert_core/halbert_core/mcp/config.py` — MCP config loader
- `halbert_core/halbert_core/mcp/registry.py` — tool registry
- `halbert_core/halbert_core/mcp/bridge.py` — tool registration bridge
- `halbert_core/halbert_core/mcp/health.py` — health monitoring
- `halbert_core/halbert_core/dashboard/frontend/src/pages/MCP.tsx` — dashboard page
- `halbert_core/tests/test_mcp_client.py` — tests
- `halbert_core/tests/test_mcp_bridge.py` — tests
- `halbert_core/config/mcp_config.yml` — default config

### New files (Workstream C + D)
- `halbert_core/halbert_core/tools/desktop_control/ax_helper/ax_helper.swift` — Swift binary
- `halbert_core/halbert_core/tools/desktop_control/ax_client.py` — Python wrapper
- `halbert_core/halbert_core/tools/desktop_control/accessibility_tools.py` — reader tools
- `halbert_core/halbert_core/tools/desktop_control/interaction_tools.py` — interaction tools
- `halbert_core/halbert_core/tools/desktop_control/screenshot_fallback.py` — Tier 3 fallback
- `halbert_core/halbert_core/tools/desktop_control/safety.py` — desktop control safety
- `halbert_core/halbert_core/dashboard/frontend/src/pages/DesktopControl.tsx` — dashboard section
- `halbert_core/tests/test_accessibility_tools.py` — tests
- `halbert_core/tests/test_interaction_tools.py` — tests
- `halbert_core/tests/test_desktop_control_safety.py` — tests
- `halbert_core/config/desktop_control_config.yml` — default config

### Modified files (all workstreams)
- `halbert_core/halbert_core/capabilities.py` — add `CAP_APPLESCRIPT`, `CAP_MCP_CLIENT`, `CAP_ACCESSIBILITY_READER`, `CAP_DESKTOP_CONTROL`
- `halbert_core/halbert_core/dashboard/routes/agent.py` — add tool registration calls (lines ~140-314 area)
- `halbert_core/halbert_core/tools/safety.py` — extend with AppleScript and desktop control safety rules
- `halbert_core/halbert_core/tools/executor.py` — possibly extend `register()` for MCP tool lifecycle
- `halbert_core/halbert_core/prompts/` — add context injectors for scriptable apps, accessibility, MCP
- `halbert_core/halbert_core/dashboard/frontend/src/components/Layout.tsx` — add MCP and Desktop Control nav items
- `halbert_core/halbert_core/dashboard/frontend/src/App.tsx` — add routes for new pages

---

## 15. Risks and Mitigations (Cross-Cutting)

### 15.1 Security

Desktop control and AppleScript can do anything a user can do. The
safety framework is the primary mitigation. Additional measures:

- **Audit logging:** Every desktop control action (click, type,
  AppleScript execution) should be logged with timestamp, target app,
  action, and result. The existing `chat_audit.py` pattern applies.
- **Rate limiting:** Prevent the agent from executing rapid-fire
  actions without user awareness. A configurable delay between
  high-risk actions.
- **Reversibility preference:** The agent should prefer reversible
  actions over irreversible ones. "Create a draft email" before
  "send email." "Move to Trash" before "empty trash."

### 15.2 Privacy

Accessibility tree reading and screenshot capture expose everything on
the user's screen, including passwords, private messages, financial
data. Mitigations:

- **Redaction:** The existing vision redaction system
  (`halbert_core/vision/redact.py`) should be applied to screenshots
  used for desktop control.
- **Element-level redaction:** The accessibility reader should redact
  values of password fields (`AXPasswordField` role) and other
  sensitive element types.
- **No persistent storage:** Desktop control observations (screenshots,
  element trees) should not be stored to disk or sent to external
  services. They exist only in the agent's ephemeral context.

### 15.3 Permission UX

macOS requires explicit permissions (Accessibility, Screen Recording).
This is a one-time setup but it's a UX hurdle. Mitigations:

- **Clear onboarding:** When desktop control is first enabled, guide
  the user through the permission grants with screenshots and
  step-by-step instructions.
- **Graceful degradation:** If permissions are not granted, the tools
  should return clear error messages, not crash. The agent should be
  able to explain what permission is needed and why.
- **Permission status in dashboard:** The Desktop Control settings page
  should show current permission status.

### 15.4 Latency

Voice interaction has a latency budget. The user speaks, STT processes,
the agent thinks, the agent acts, TTS responds. Adding desktop control
adds action latency on top of this.

- AppleScript execution: ~50-100ms per call — acceptable
- Accessibility tree read: ~100-500ms depending on tree depth — acceptable
- Screenshot + vision model: 3-5 seconds — borderline for voice
- MCP tool call: depends on the server, usually <1s — acceptable

The screenshot fallback (Task D3) is the main latency risk. It should
be used sparingly and only when accessibility is unavailable.

### 15.5 The Haloysius Subtractive Contract

From CLAUDE.md: "Only 2 hard dependencies (`pyyaml>=6.0`,
`requests>=2.31.0`); all heavy/ML stacks must remain function-level
lazy optional extras."

All new code must respect this:
- The MCP client library must be a lazy import (only when
  `CAP_MCP_CLIENT` is on)
- The AppleScript tool uses `osascript` (system binary, no Python
  dependency) — fine
- The accessibility helper is a Swift binary (build artifact, not a
  Python dependency) — fine
- No new hard Python dependencies in `pyproject.toml`

---

## 16. Success Metrics

How to know if this work is succeeding:

1. **Adoption:** Users enable `CAP_APPLESCRIPT` and/or `CAP_MCP_CLIENT`
   in their config. Track via anonymous capability telemetry (if
   Halbert has it) or dashboard analytics.
2. **Usage:** The agent invokes AppleScript / MCP tools in
   conversations. Track tool invocation counts in the audit log.
3. **Safety incidents:** Zero unconfirmed high-risk actions execute.
   Track confirmation rates and any safety framework bypasses.
4. **User satisfaction:** Users report that voice-controlled app
   interaction works reliably. Qualitative feedback via dashboard or
   support channel.
5. **MCP ecosystem growth:** Number of MCP servers configured per
   user increases over time as more servers become available.

---

## 17. References

- Research doc: `RESEARCH-VOICE-ASSISTANT-APP-UI-ACCESS-2026-09-07.md`
- Tool registration pattern: `halbert_core/halbert_core/tools/gpu_tools.py` (lines 1188-1201)
- Agent init / tool registration: `halbert_core/halbert_core/dashboard/routes/agent.py` (lines 140-314)
- Tool executor register method: `halbert_core/halbert_core/tools/executor.py` (line 371)
- Safety framework: `halbert_core/halbert_core/tools/safety.py`
- Capabilities system: `halbert_core/halbert_core/capabilities.py`
- Vision config gating pattern: `halbert_core/halbert_core/vision/config.py`
- Vision subsystem: `halbert_core/halbert_core/vision/__init__.py`
- Discovery scanner pattern: `halbert_core/halbert_core/discovery/scanners/`
- MCP protocol spec: https://modelcontextprotocol.io/docs/2026-07-28/learn/architecture
- Apple App Intents: https://developer.apple.com/documentation/appintents/appintent
- Anthropic Computer Use: https://platform.claude.com/docs/en/agents-and-tools/tool-use/computer-use-tool
