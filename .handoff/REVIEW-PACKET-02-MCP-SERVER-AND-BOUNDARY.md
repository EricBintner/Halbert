# Review Packet 02: Halbert MCP Server & Client Boundary Architecture

**Review Level:** **GLM-5.3 (reassigned 2026-08-30 — see MASTER-REVIEW-INDEX § 2 for effort tier and batch)**  
**Domain:** Model Context Protocol (MCP) Server, JSON-RPC 2.0 Stdio/SSE Transports, Security Tier Routing, and Multi-Instance Bearer Authentication  
**Target Date:** 2026-08-29  
**Status:** Ready for Protocol Adherence & Concurrency Scrutiny  

---

## 1. Executive Summary & Review Scope

Halbert provides a native Model Context Protocol (MCP) server implementation enabling external AI orchestrators (e.g. Claude Desktop, Cursor, external agent harnesses) and internal autonomous loops to query host state, execute actions, and inspect configuration trees.

Over the past week, the MCP layer was completely modernized:
1. Standardized 12 core tools over **JSON-RPC 2.0** with strict Pydantic argument schemas.
2. Built a hybrid dual-transport layer: high-performance **stdio transport** for local CLI/subprocesses and an **HTTP/SSE transport** for remote and networked multi-instance operation.
3. Enforced multi-instance isolation via `BearerTokenAuthMiddleware` and integrated the `PREP_DAEMON_TOKEN` handshake.
4. Embedded security tier routing: Tier 2 secrets are automatically intercepted and routed to `describe_secret` metadata rather than emitting raw values.

The reviewing model (**GLM-5.3**) must evaluate protocol compliance, transport lifecycle stability, token authentication resilience, tool execution error boundaries, and concurrency handling.

---

## 2. Planning & Design Documents (Past 2 Weeks)

| Document | Purpose | Key Themes |
|---|---|---|
| [`.handoff/HALBERT-MCP-PLAN-2026-08-28.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/HALBERT-MCP-PLAN-2026-08-28.md) | Architectural blueprint for Halbert MCP Server | Tool definitions, JSON-RPC 2.0 schema, transport decoupling, security integration |
| [`.handoff/HALBERT-MCP-HANDOFF-2026-08-28.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/HALBERT-MCP-HANDOFF-2026-08-28.md) | Implementation handoff & test report | Stdio/SSE endpoints, tool inventory, tier validation, client sample configurations |

---

## 3. Git History & Code Commits (Past Week: Aug 22 – Aug 29)

| Commit | Date | Summary | Key Files Changed |
|---|---|---|---|
| `3144d5b4` | 2026-08-28 | Task 2: `PREP_DAEMON_TOKEN` authentication for SourcePrep API | `integrations/sourceprep_client.py`, `dashboard/app.py` |
| `4499d2e8` | 2026-08-28 | Phase 4: MCP server stdio — 12 tools, JSON-RPC 2.0, tier routing | `mcp/server.py`, `mcp/tools.py`, `tests/test_mcp_server.py` |
| `90395b01` | 2026-08-28 | Phase 4b: HTTP/SSE transport + multi-instance bearer auth | `mcp/transport.py`, `mcp/auth.py`, `dashboard/routes/mcp.py` |
| `2ea32789` | 2026-08-29 | Merge main into `feat/halbert-mcp` | Merge commit |
| `4f1f2ce0` | 2026-08-29 | Merge `feat/halbert-mcp` into `home-automation` with security tiers + autonomy fields | Merge commit |

---

## 4. Key Files & Architectural Components

- **MCP Protocol Engine & Tools:**
  - [`halbert_core/halbert_core/mcp/server.py`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/mcp/server.py) (Main JSON-RPC dispatcher & tool catalog)
  - [`halbert_core/halbert_core/mcp/tools.py`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/mcp/tools.py) (Tool declarations: `get_config_value`, `list_findings`, `execute_proposal`, `query_telemetry`, etc.)
- **Transports & Authentication:**
  - [`halbert_core/halbert_core/mcp/transport.py`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/mcp/transport.py) (Async stdio reader/writer & SSE event channel)
  - [`halbert_core/halbert_core/mcp/auth.py`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/mcp/auth.py) (Bearer token validation middleware)
  - [`halbert_core/halbert_core/dashboard/routes/mcp.py`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/routes/mcp.py) (FastAPI endpoint wrapper)

---

## 5. Incomplete Work & Open Items

1. **SSE Client Reconnection Resiliency:** Validate that broken SSE connections from clients (e.g. Claude Desktop reconnection loops) do not leak background listener tasks or unbounded event queues.
2. **Client Config Snippets:** Create and verify copy-paste configuration snippets for Cursor (`~/.cursor/mcp.json`) and Claude Desktop (`claude_desktop_config.json`) in `documentation/guides/mcp-setup.md`.
3. **Concurrency Pressure Testing:** Profile multiple concurrent MCP tool executions against shared config stores to verify no SQLite locks or race conditions occur.

---

## 6. Review Directives for Fable

- **Specification Adherence:** Verify JSON-RPC 2.0 spec compliance (proper error codes `-32600`, `-32601`, `-32602`, `-32603`, `-32700` and response envelope formatting).
- **Security Boundary Gate:** Trace `get_config_value` and confirm that requesting a Tier 2 key never returns the plaintext value over the MCP socket, returning `describe_secret` metadata instead.
- **Autonomy Validation:** Ensure tools with destructive side effects (`execute_proposal`, `apply_fix`) strictly verify `BeingConfig.autonomy_level` before execution.
- **Verification Command:** Run `pytest halbert_core/tests/test_mcp_server.py halbert_core/tests/test_mcp_transport.py -v`.
