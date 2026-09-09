# HANDOFF: Voice Assistant App UI Access — Implementation Plan for Review

**Date:** 2026-09-07
**Status:** Ready for founder review — no implementation started
**Decision needed:** Approve plan, resolve open decisions (Section 5), authorize Phase 1

---

## 0. What This Is

This is a consolidated review handoff for giving Halbert the ability to
interface with other applications' UIs — as a voice assistant that can
read what's on screen, act on other apps, connect to apps via structured
APIs, and discover what's controllable.

Three supporting documents exist in `.handoff/`:

| Document | Purpose |
|----------|---------|
| `RESEARCH-VOICE-ASSISTANT-APP-UI-ACCESS-2026-09-07.md` | Original landscape research — maps the three mechanism tiers (structured API, accessibility tree, screenshot+coordinate) and the 2026 ecosystem |
| `PLAN-VOICE-ASSISTANT-APP-UI-ACCESS-2026-09-07.md` | Full implementation plan — 7 workstreams (A-G), 19 tasks, dependency graph, file list, risks |
| `RESEARCH-OPENCLAW-APP-UI-ARCHITECTURE-2026-09-07.md` | OpenClaw architecture deep-dive — production reference for voice confirmation, browser control, node architecture, MCP integration |

**This handoff supersedes the effort estimates in the original plan.**
The OpenClaw research revealed that the hardest design problems are
already solved in production, which downgrades several tasks.

---

## 1. The Goal

A user can say "Halbert, send an email to Sarah saying I'll be late" and
Halbert:
1. Generates the right AppleScript for Mail
2. Asks for voice confirmation ("I'm about to send an email to Sarah.
   Say 'yes' to confirm.")
3. User says "yes"
4. Halbert executes the script
5. The email is sent — without the user touching the keyboard

The north star extends to: controlling any scriptable app, connecting to
any MCP server, reading screen state structurally, and eventually
controlling mobile devices via paired nodes.

---

## 2. Mechanism Tiers (How AI Accesses App UIs)

| Tier | Mechanism | Reliability | Cost | Latency |
|------|-----------|-------------|------|---------|
| 1 | Structured API (AppleScript, MCP, App Intents) | High — semantic, deterministic | Low — no vision model needed | ~50-100ms |
| 2 | Accessibility tree (AXUIElement) | Medium — semantic but incomplete for some apps | Low — no vision model | ~100-500ms |
| 3 | Screenshot + vision model + coordinates | Lower — depends on model interpretation | High — one vision call per action | 3-5 seconds |

**Strategy:** Tier 1 first, Tier 2 as needed, Tier 3 as last resort.

---

## 3. The Plan — 7 Workstreams, 19 Tasks

### Workstream A: AppleScript / JXA Tool (Tier 1, macOS)

The highest ROI workstream. Days of work, immediate voice-controllable
access to Mail, Calendar, Music, Safari, Notes, Reminders, Finder, and
any scriptable third-party app.

| Task | Description | Model | Effort | Deps |
|------|-------------|-------|--------|------|
| A1 | AppleScript tool scaffold — `osascript` subprocess wrapper | sonnet | high | None |
| A2 | AppleScript safety classifier — pattern-based risk classification | opus | high | A1 |
| A3 | Scriptable app discovery scanner — finds `.sdef` files | sonnet | med | None |
| A4 | AppleScript prompt context — injects app list into system prompt | sonnet | med | A3 |

### Workstream B: MCP Client Capability (Tier 1, Cross-Platform)

The strategic bet. As more apps ship MCP servers (Linear, GitHub,
filesystem, browser, desktop control), Halbert automatically gains
capabilities without writing custom integrations.

| Task | Description | Model | Effort | Deps | Revised? |
|------|-------------|-------|--------|------|----------|
| B1 | MCP client library — stdio + HTTP transports, tool discovery | opus | high | None | **Downgraded from xhigh** — OpenClaw reference exists |
| B2 | MCP tool registration bridge — namespaced tools into ToolExecutor | opus | high | B1 | |
| B3 | MCP safety integration — per-server risk classification | opus | xhigh | B2 | **Upgraded from high** — OpenClaw's layered auth is more complex |
| B4 | MCP server health monitoring — reconnect with backoff | sonnet | med | B1 | |
| B5 | MCP dashboard UI — server management page | sonnet | med | B4 | |
| **B6** | **MCP server exposure — expose Halbert's tools as MCP server** | **sonnet** | **high** | **B1** | **NEW** — not in original plan; OpenClaw is both client and server |

### Workstream C: Accessibility Tree Reader (Tier 2, macOS)

Structured eyes on any running app — see the UI element tree without
screenshots. Read-only first; interaction comes in Workstream D.

| Task | Description | Model | Effort | Deps |
|------|-------------|-------|--------|------|
| C1 | Accessibility helper binary — Swift + AXUIElement, JSON over stdio | opus | high | None |
| C2 | Accessibility reader tools — 5 tools registered with agent | sonnet | high | C1 |
| C3 | Accessibility prompt context — usage guidance in system prompt | sonnet | med | C2 |

### Workstream D: Desktop Interaction Tools (Tier 2+3, macOS)

The highest-risk, highest-complexity workstream. Clicking and typing in
arbitrary apps can do anything. The safety design is the core challenge.

| Task | Description | Model | Effort | Deps | Revised? |
|------|-------------|-------|--------|------|----------|
| D1 | Interaction primitives — click, type, press, scroll, drag | opus | xhigh | C1, C2 | |
| D2 | Desktop control safety framework — per-app allowlisting, voice confirmation | opus | xhigh | D1 | **Downgraded from fable/max** — OpenClaw solved the voice confirmation design |
| D3 | Screenshot+coordinate fallback — vision model for poor-AX apps | sonnet | high | D1 | |
| D4 | Desktop control dashboard UI — settings, allowlist, action log | sonnet | med | D1, D2 | |

### Workstream E: App Intents Integration (Apple Ecosystem) — DEFERRED

Apple's sanctioned inter-app framework. Requires Tauri app packaging to
be complete first. This is the right long-term Apple integration story.

| Task | Description | Model | Effort | Deps |
|------|-------------|-------|--------|------|
| E1 | Halbert App Intents exposure — Siri/Shortcuts integration | fable | xhigh | Tauri packaging |
| E2 | App Intents consumption — invoke other apps' intents | fable | xhigh | E1 |

### Workstream F: Scriptable App Discovery — MERGED INTO A3

Already covered as Task A3. Listed separately in the original plan for
clarity but is the same work.

### Workstream G: Cross-Device Node Pattern (Federated) — DEFERRED

Mobile companion node that gives desktop Halbert remote access to phone
screen, camera, sensors. Depends on federated multi-node architecture.

| Task | Description | Model | Effort | Deps | Revised? |
|------|-------------|-------|--------|------|----------|
| G1 | Mobile companion node design — pairing, security, capability surface | fable | xhigh | Federated arch | **Downgraded from max** — OpenClaw's node architecture is a reference |

---

## 4. Revised Model Tier and Effort Summary

### What changed and why

The OpenClaw research (`RESEARCH-OPENCLAW-APP-UI-ARCHITECTURE-2026-09-07.md`)
inspected a production system that has already solved the hardest design
problems in this plan. Key findings that changed estimates:

1. **Voice confirmation gate is a solved problem.** OpenClaw's
   `src/talk/client-voice-confirmation.ts` implements fingerprint-bound,
   one-shot, spoken confirmation for high-impact actions. This is exactly
   what Task D2 needs. The design is done; the work is porting the
   pattern to Halbert's Python safety framework.

2. **MCP client has a reference implementation.** OpenClaw's
   `src/agents/agent-bundle-mcp-runtime.ts` shows transport handling,
   session expiry, paginated tool discovery, and stable name prefixing.

3. **MCP safety is more complex than originally estimated.** OpenClaw
   uses layered authorization (tool policy + command policy + pairing +
   local toggle + OS permission + foreground state). The original plan's
   simple per-server config is insufficient.

4. **Node architecture has a production reference.** OpenClaw's entire
   node system (device pairing, capability advertisement, `node.invoke`,
   per-platform companion apps) is the mature version of Halbert's
   federated multi-node vision.

5. **MCP server exposure is a new opportunity.** OpenClaw is both MCP
   client and server. Halbert should expose its own tools as an MCP
   server so other AI agents can use them. This is a new task (B6).

### Revised table

| Task | Original | Revised | Reason |
|------|----------|---------|--------|
| B1 (MCP client) | opus/xhigh | opus/high | Reference implementation exists |
| B3 (MCP safety) | opus/high | opus/xhigh | Layered auth is more complex |
| D2 (Desktop safety) | fable/max | opus/xhigh | Voice confirmation design is solved |
| G1 (Mobile node) | fable/max | fable/xhigh | Node architecture reference exists |
| B6 (MCP server) | — | sonnet/high | New task, follows OpenClaw's adapter pattern |

**Net effect:** Overall effort is lower. The hardest design problems are
solved; remaining work is implementation and porting.

---

## 5. Open Decisions for Founder Review

These decisions need to be made before implementation begins.

### Decision 1: Scope — what is Halbert?

> Is Halbert a voice assistant that *can* control apps, or a desktop
> automation agent that *has* a voice interface?

- **Option A:** Voice assistant that can control apps. Build A + B only.
  Let usage patterns reveal whether C and D are needed.
- **Option B:** Full desktop automation agent. Build A + B + C + D.

**Recommendation:** Option A. Start with AppleScript + MCP. Don't build
desktop control speculatively.

### Decision 2: Platform priority

- **Option A:** macOS-first for everything. Simplest, highest ROI for the
  current user.
- **Option B:** macOS for A (AppleScript), cross-platform for B (MCP).
  Defer Linux accessibility.

**Recommendation:** Option B. MCP is inherently cross-platform.

### Decision 3: Voice confirmation UX

When Halbert is about to do something high-risk, how does confirmation work?

- **Option A:** Always describe + ask. Safe but verbose.
- **Option B:** Configurable per-app. Low-risk apps auto-execute,
  high-risk apps always confirm.
- **Option C:** Use existing text-based dashboard confirmation. Simple
  but defeats voice purpose.

**Recommendation:** Option B. OpenClaw's pattern (fingerprint the action,
one-shot consumption, 2-minute TTL, match affirmations/refusals) is the
proven approach. See `RESEARCH-OPENCLAW-APP-UI-ARCHITECTURE-2026-09-07.md`
Section 4 for the full pattern.

### Decision 4: MCP server default configuration

- **Option A:** None. User adds their own.
- **Option B:** Curated safe defaults (read-only filesystem).
- **Option C:** Discovery-based suggestions.

**Recommendation:** Option A for now. Option C is a future enhancement.

### Decision 5: Build vs. buy for desktop control

- **Option A:** Build native accessibility stack (Workstreams C + D,
  ~3000 lines, months of work).
- **Option B:** Be an MCP client. Let users connect existing
  desktop-control MCP servers (open-computer-use, axcli, etc.).

**Recommendation:** Option B. Let the ecosystem do the heavy lifting.
Halbert's value is the voice assistant + safety framework + agent loop.
Only build native if MCP servers prove insufficient.

### Decision 6: AppleScript safety default

- **Option A:** Default to MEDIUM (warn but execute).
- **Option B:** Default to HIGH (require confirmation).
- **Option C:** Default to CRITICAL (block).

**Recommendation:** Option B. Over-confirm rather than auto-execute
unknown scripts. Known-safe patterns (get, name of, count of) stay
frictionless.

### Decision 7: Should Halbert expose its tools as an MCP server? (NEW)

- **Option A:** Yes — expose Halbert's system admin tools as an MCP
  server so other AI agents can use them.
- **Option B:** No — Halbert is only an MCP client, not a server.

**Recommendation:** Option A. This is low-effort (sonnet/high) and high
value — it makes Halbert a participant in the MCP ecosystem, not just a
consumer. OpenClaw does this with a thin adapter that wraps existing
tools (`src/mcp/plugin-tools-handlers.ts`).

---

## 6. Recommended Sequencing

### Phase 1: Immediate Value (start now)

**Do these first.** Independent, high-ROI, reveals what users want.

1. **A1** — AppleScript tool scaffold (sonnet/high)
2. **A3** — Scriptable app discovery scanner (sonnet/med)
3. **A2** — AppleScript safety classifier (opus/high)
4. **A4** — AppleScript prompt context (sonnet/med)

**Deliverable:** Voice-controlled Mail, Calendar, Music, Safari, Notes,
Reminders via AppleScript, with safety gating.

### Phase 2: Strategic Platform (start in parallel with Phase 1)

**The long-term bet.** MCP is where the ecosystem is heading.

5. **B1** — MCP client library (opus/high)
6. **B2** — MCP tool registration bridge (opus/high)
7. **B3** — MCP safety integration (opus/xhigh)
8. **B4** — MCP health monitoring (sonnet/med)
9. **B5** — MCP dashboard UI (sonnet/med)
10. **B6** — MCP server exposure (sonnet/high) — NEW

**Deliverable:** Halbert is both an MCP client and server. Any MCP server
the user configures extends Halbert's capabilities. Other AI agents can
use Halbert's tools.

### Phase 3: Native Eyes (only if Phase 2 doesn't cover the need)

11. **C1** — Accessibility helper binary (opus/high)
12. **C2** — Accessibility reader tools (sonnet/high)
13. **C3** — Accessibility prompt context (sonnet/med)

**Deliverable:** Halbert can read any running app's UI tree structurally.

### Phase 4: Native Hands (only if Phase 3 is done)

14. **D1** — Interaction primitives (opus/xhigh)
15. **D2** — Safety framework with voice confirmation (opus/xhigh)
16. **D3** — Screenshot fallback (sonnet/high)
17. **D4** — Dashboard UI (sonnet/med)

**Deliverable:** Halbert can click, type, and interact with any running
app, with voice confirmation for high-risk actions.

### Deferred

- **Workstream E (App Intents):** Wait for Tauri app packaging.
- **Workstream G (Mobile node):** Wait for federated multi-node architecture.

---

## 7. Dependency Graph

```
A1 (AppleScript scaffold) ── A2 (Safety classifier)
A3 (Scriptable app scanner) ── A4 (Prompt context)

B1 (MCP client) ── B2 (Tool bridge) ── B3 (Safety)
                ├── B4 (Health monitoring) ── B5 (Dashboard UI)
                └── B6 (MCP server exposure)  [NEW]

C1 (AX helper) ── C2 (Reader tools) ── C3 (Prompt context)
              └── D1 (Interaction) ── D2 (Safety + voice confirm)
                                    └── D3 (Screenshot fallback)
                                        └── D4 (Dashboard UI)

E1 (App Intents exposure) ── E2 (App Intents consumption)
  ↑ Tauri packaging (external)

G1 (Mobile node)
  ↑ Federated multi-node arch (in progress)
```

**Independent start points:** A1, A3, B1, C1 — can all begin immediately.

---

## 8. Key Patterns to Borrow from OpenClaw

These are production-tested patterns from OpenClaw that directly apply to
Halbert's implementation. See `RESEARCH-OPENCLAW-APP-UI-ARCHITECTURE-2026-09-07.md`
for full details.

### Voice confirmation gate (for Task D2)

From `src/talk/client-voice-confirmation.ts`:
- **Fingerprint the action** — hash tool name + sorted params
- **One-shot consumption** — one "yes" authorizes one action
- **2-minute TTL** — pending confirmations expire
- **Match affirmations** — "yes", "go ahead", "confirm", "send it"
- **Match refusals** — "no", "cancel", "stop", "never mind"
- **Finalized transcripts only** — partial STT can't authorize
- **Integrated into tool policy chain** — not a separate system
- **Re-confirm on rewrite** — if a hook changes the action, re-confirm

### Single tool, action-driven schema (for Tasks D1, B2)

From OpenClaw's `browser` and `computer` tools:
- One tool with an `action` enum, not many separate tools
- Reduces context window usage
- Simplifies the model's decision space
- Schema is deliberately flattened (some providers reject nested `anyOf`)

### Frame-bound coordinates (for Task D3)

From OpenClaw's `computer` tool:
- Screenshot coordinates must echo the screenshot's `frameId`
- Display changes fail closed (not silent retargeting)
- Screenshots are model-only (never auto-delivered to chat)
- Treat screen content as untrusted (prompt injection risk)

### MCP: wrap existing tools (for Task B6)

From `src/mcp/plugin-tools-handlers.ts`:
- The MCP server adapter calls the same tool `execute` that the agent uses
- One tool implementation, multiple exposure paths
- Don't reimplement tools for MCP exposure

### Provider abstraction with no fallback (for Task D1)

From OpenClaw's computer-use architecture:
- The agent can't choose the provider
- Provider selection is a local setting
- A provider failure is an unavailable result, not a silent fallback

---

## 9. Security Requirements (Cross-Cutting)

All workstreams must respect these:

1. **Explicit opt-in** — every capability is OFF by default (config file
   gating, same pattern as vision subsystem)
2. **Capability gating** — `CAP_APPLESCRIPT`, `CAP_MCP_CLIENT`,
   `CAP_ACCESSIBILITY_READER`, `CAP_DESKTOP_CONTROL` in `capabilities.py`
3. **RoleGate** — guest personas cannot use AppleScript, MCP, or desktop
   control tools. Read-only accessibility at founder's discretion.
4. **Audit logging** — every action logged with timestamp, target app,
   action, result (follow existing `chat_audit.py` pattern)
5. **Voice confirmation** — high-impact actions require spoken
   confirmation (fingerprint-bound, one-shot, 2-minute TTL)
6. **Per-app allowlisting** — desktop control config defines which apps
   are controllable and at what risk level
7. **Screen content is untrusted** — treat screenshots and accessibility
   trees as prompt injection material
8. **No persistent storage** — observations exist only in ephemeral
   agent context, never written to disk or sent externally
9. **Redaction** — password fields redacted in accessibility reads;
   existing vision redaction applied to screenshots
10. **Haloysius Subtractive Contract** — no new hard Python dependencies;
    MCP client is a lazy import; Swift binary is a build artifact

---

## 10. Testing Strategy

| Layer | What to test | How |
|-------|-------------|-----|
| Unit | Tool schemas, safety classification, risk levels, config parsing | pytest with mock subprocess/API |
| Integration | Tool registration, agent init wiring, capability gating | pytest with mocked ToolExecutor |
| MCP | Connect/list/call/disconnect, reconnection, error handling | Mock MCP server (in-process) |
| AppleScript | Success, error, timeout, platform gating | `osascript` fixtures, mocked subprocess |
| Accessibility | Element tree parsing, find by role/name, permission errors | Mock AX helper JSON output |
| Voice confirmation | Fingerprint matching, one-shot consumption, TTL expiry, affirmation/refusal matching | Unit tests with mock confirmation state |
| Prompt injection | Screen content with embedded instructions doesn't bypass safety | Fixtures with malicious content |
| Wrong-window | Actions target the wrong app/window are blocked | Reference invalidation tests |
| Cancellation | Long-running actions can be cancelled | Timeout + abort signal tests |
| E2E (macOS) | Full voice → agent → AppleScript → result flow | Manual + automated on macOS |

---

## 11. Files That Will Be Created or Modified

### New files (Phase 1 — Workstream A)
- `halbert_core/halbert_core/tools/applescript_tools.py`
- `halbert_core/halbert_core/tools/applescript_safety.py`
- `halbert_core/halbert_core/discovery/scanners/scriptable_apps.py`
- `halbert_core/tests/test_applescript_tools.py`
- `halbert_core/tests/test_applescript_safety.py`
- `halbert_core/tests/test_scriptable_apps_scanner.py`
- `halbert_core/config/applescript_config.yml`

### New files (Phase 2 — Workstream B)
- `halbert_core/halbert_core/mcp/client.py`
- `halbert_core/halbert_core/mcp/config.py`
- `halbert_core/halbert_core/mcp/registry.py`
- `halbert_core/halbert_core/mcp/bridge.py`
- `halbert_core/halbert_core/mcp/health.py`
- `halbert_core/halbert_core/mcp/server.py` — NEW (MCP server exposure)
- `halbert_core/halbert_core/dashboard/frontend/src/pages/MCP.tsx`
- `halbert_core/tests/test_mcp_client.py`
- `halbert_core/tests/test_mcp_bridge.py`
- `halbert_core/tests/test_mcp_server.py` — NEW
- `halbert_core/config/mcp_config.yml`

### New files (Phase 3+4 — Workstreams C + D)
- `halbert_core/halbert_core/tools/desktop_control/ax_helper/ax_helper.swift`
- `halbert_core/halbert_core/tools/desktop_control/ax_client.py`
- `halbert_core/halbert_core/tools/desktop_control/accessibility_tools.py`
- `halbert_core/halbert_core/tools/desktop_control/interaction_tools.py`
- `halbert_core/halbert_core/tools/desktop_control/screenshot_fallback.py`
- `halbert_core/halbert_core/tools/desktop_control/safety.py`
- `halbert_core/halbert_core/tools/desktop_control/voice_confirmation.py` — NEW (from OpenClaw pattern)
- `halbert_core/halbert_core/dashboard/frontend/src/pages/DesktopControl.tsx`
- `halbert_core/tests/test_accessibility_tools.py`
- `halbert_core/tests/test_interaction_tools.py`
- `halbert_core/tests/test_desktop_control_safety.py`
- `halbert_core/tests/test_voice_confirmation.py` — NEW
- `halbert_core/config/desktop_control_config.yml`

### Modified files (all phases)
- `halbert_core/halbert_core/capabilities.py` — add `CAP_APPLESCRIPT`, `CAP_MCP_CLIENT`, `CAP_ACCESSIBILITY_READER`, `CAP_DESKTOP_CONTROL`
- `halbert_core/halbert_core/dashboard/routes/agent.py` — add tool registration calls
- `halbert_core/halbert_core/tools/safety.py` — extend with AppleScript and desktop control safety rules
- `halbert_core/halbert_core/tools/executor.py` — extend for MCP tool lifecycle
- `halbert_core/halbert_core/prompts/` — add context injectors
- `halbert_core/halbert_core/dashboard/frontend/src/components/Layout.tsx` — add nav items
- `halbert_core/halbert_core/dashboard/frontend/src/App.tsx` — add routes

---

## 12. What to Do Next

1. **Review this handoff** and the three supporting documents
2. **Resolve the 7 open decisions** in Section 5
3. **Authorize Phase 1** (Tasks A1-A4) — this can start immediately
4. **Optionally authorize Phase 2** (Tasks B1-B6) in parallel — B1 can
   start immediately alongside A1

Phases 3 and 4 should only be authorized after Phase 2 reveals whether
the MCP client approach is sufficient for desktop control.

---

## 13. Key OpenClaw Source Files for Reference

When implementing, these OpenClaw files are the primary references:

| Halbert task | OpenClaw reference | What to study |
|---|---|---|
| D2 (voice confirmation) | `src/talk/client-voice-confirmation.ts` | Fingerprint, one-shot, TTL, affirmation/refusal matching |
| D2 (policy integration) | `src/agents/agent-tools.before-tool-call.policy.ts:85-99, 183-200` | How confirmation integrates with tool policy |
| B1 (MCP client) | `src/agents/agent-bundle-mcp-runtime.ts` | Transport handling, session expiry, paginated discovery |
| B6 (MCP server) | `src/mcp/plugin-tools-handlers.ts:68-129` | Thin adapter wrapping existing tools |
| B3 (MCP safety) | OpenClaw's layered authorization | Tool policy + command policy + pairing + local toggle |
| D1 (interaction) | `docs/nodes/computer-use.md` | Single tool, action-driven, provider abstraction |
| D3 (screenshot) | `docs/nodes/computer-use.md` | Frame-bound coordinates, model-only screenshots |
| G1 (mobile node) | `docs/nodes/index.md` | Device pairing, capability advertisement, `node.invoke` |
