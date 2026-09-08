# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""MCP tool risk classification (Workstream B3).

MCP tools are REMOTE. The filesystem server can delete files; a browser
server can navigate anywhere; any server can expose a tool whose name
says ``read_file`` and whose implementation does something else. The
safety framework's pattern classifier reads shell commands and script
text — it cannot read what a server on the other end of a transport will
do with a ``tools/call`` — so this module does not pattern-match at
all. The operator's config is the primary mechanism:

* per-tool ``tool_risk`` (mcp_config.yml, server entry) — highest
  precedence;
* per-server ``risk_override``;
* MEDIUM default — execute, with the framework's MEDIUM warning
  semantics (the risk level rides the ExecutionResult and the audit
  log) — but ONLY for a server that is present in the config with no
  override.

A REGISTERED ``mcp__`` tool whose server is ABSENT from the current
config FAILS CLOSED (CRITICAL, blocked — never a MEDIUM downgrade).
The invariant that makes this safe to do without tracking registration
state: a bridged tool can only exist if its server was configured at
registration time, and the executor refuses unregistered names before
classification ever runs — so "registered tool, absent server" always
means the server was REMOVED, RENAMED, or DROPPED BY VALIDATION
(a typo'd override) since registration. Per-call freshness must not
turn any of those accidents into a silent auto-execute. The refusal is
diagnosable: it names the server and what the config read saw
(dropped-by-validation names, or the load failure), from
``MCPClientConfig.skipped_servers`` / ``load_error``.

Name matching: the registry sanitizes server and tool names into the
qualified key (``my-fs``/``delete-file`` → ``mcp__my_fs__delete_file``),
so override lookups compare the sanitized form of both sides — and
CASE-INSENSITIVELY, because ``sanitize_component`` preserves case: a
fence written ``Delete_File`` must match the registered
``delete_file``, not silently miss it and auto-execute. The loader
rejects sanitized-name collisions outright (config.py), so the first
match here is deterministic regardless of config order. One honest
limit: a collision-suffixed tool (``..._2``) rides its server's
override or the default — it cannot be individually classified (see
``registry.parse_qualified_tool_name``).

The burden is on the operator to classify their servers correctly; the
classifier's honesty is that it says so (each result's ``reason`` names
which config key decided, or that the MEDIUM default fired).

PER-CALL FRESHNESS — the design trap this module exists around. Tool
registration happens ONCE at agent init (the bridge discovers and
registers ``mcp__{server}__{tool}`` names), but classification is
evaluated on EVERY call, against the CURRENT config
(:func:`halbert_core.mcp.config.load_config` re-reads the file per
call — B1's hot-reload semantics). A config edit flipping a server to
HIGH gates the NEXT tool call with no restart and no re-registration.
That is why classification lives here, in the per-call path the
executor already drives through
:meth:`ToolSafetyFramework._classify_builtin` — not in the bridge's
registration seam: a classification captured at registration time would
be a snapshot that a config flip cannot reach.

Enforcement is NOT here. The returned
:class:`~halbert_core.tools.safety.SafetyCheckResult` flows through the
same executor chain every native tool uses (tools/executor.py): CRITICAL
blocks outright (``allowed=False``, no confirmed=True override), HIGH
requires explicit confirmation (the confirmation message names the
server, the tool and a capped args preview — see
``ToolSafetyFramework.get_confirmation_message``), RoleGate tightens per
speaker role, and guests are structurally denied (B2: the guest
allowlist is the rule and no ``mcp__`` name is ever on it —
classification, even ``risk_override: safe``, is never what saves a
guest).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from ..mcp.config import load_config
from ..mcp.registry import parse_qualified_tool_name, sanitize_component
from .safety import RiskLevel, SafetyCheckResult

logger = logging.getLogger("halbert.tools.mcp_safety")

#: The classification for an MCP tool no override speaks for. MEDIUM is
#: the plan's explicit default: execute, warn in the response — never
#: block, never auto-execute silently.
MCP_DEFAULT_RISK = RiskLevel.MEDIUM


def _result(
    level: RiskLevel, reason: str, matched_rule: str
) -> SafetyCheckResult:
    """A SafetyCheckResult with the policy fields derived from the level
    — the same derivation the framework applies everywhere (a CRITICAL
    classification is allowed=False; HIGH alone requires confirmation)."""
    return SafetyCheckResult(
        risk_level=level,
        allowed=level != RiskLevel.CRITICAL,
        requires_confirmation=level == RiskLevel.HIGH,
        reason=reason,
        matched_rule=matched_rule,
    )


def _current_config():
    """load_config() with a defensive net. load_config never raises by
    design (a corrupt config means "no servers"), so this only guards
    against the unexpected — and on the unexpected it returns None,
    which classify_mcp_tool treats as fail-closed, not as "no overrides
    apply": a config the classifier cannot read must not read as MEDIUM."""
    try:
        return load_config()
    except Exception as e:  # pragma: no cover - load_config swallows all
        logger.warning(
            "MCP risk classification: config unreadable (%s); "
            "classification fails closed", e)
        return None


def _match_component(config_written: str, registered_component: str) -> bool:
    """Does a config-written name (server or tool) refer to the
    registered component of a qualified name? Sanitized on both sides
    (the registry collapsed ``my-fs`` → ``my_fs``), and
    CASE-INSENSITIVELY: ``sanitize_component`` preserves case, so a
    fence written ``Delete_File`` must still match a registered
    ``delete_file`` rather than silently missing it and auto-executing.
    Registered names keep their case — only the comparison lowers it.
    """
    return sanitize_component(config_written).lower() == registered_component.lower()


def _absent_reason(server_component: str, config) -> str:
    """The fail-closed refusal reason for a registered tool whose server
    the current config does not carry — naming what the config read saw,
    so the block is diagnosable, not a mystery."""
    details = []
    if config.load_error:
        details.append(f"config unreadable ({config.load_error})")
    if config.skipped_servers:
        details.append(
            "dropped by validation: " + ", ".join(config.skipped_servers))
    state = "; ".join(details) if details else (
        "removed or renamed since registration")
    return (
        f"Server '{server_component}' is absent from the current "
        f"mcp_config.yml ({state}). A registered MCP tool exists only "
        f"because its server was configured at registration time, so "
        f"classification fails closed rather than downgrading a live "
        f"tool to the MEDIUM default"
    )


def classify_mcp_tool(tool_name: str, args: Any) -> SafetyCheckResult:
    """Classify one ``mcp__{server}__{tool}`` call by risk level.

    Precedence: per-tool ``tool_risk`` > per-server ``risk_override`` >
    MEDIUM default — and a registered tool whose server is ABSENT from
    the current config fails closed (CRITICAL, blocked), never MEDIUM
    (see the module docstring for the registered-tool invariant that
    makes that safe). The config is read fresh on every call; the args
    are not inspected (there is nothing local to inspect — see the
    module docstring).
    """
    parsed = parse_qualified_tool_name(tool_name)
    if parsed is None:
        # Not a well-formed qualified name. A bridged tool always is
        # (the registry produced it), so this is a name a caller
        # hand-typed to look like one. It cannot be registered, and the
        # executor refuses unregistered names before classification —
        # but if one ever reached a handler the honest classification
        # is the default, not a guess.
        return _result(
            MCP_DEFAULT_RISK,
            f"MCP tool with an unparseable name '{tool_name}' — "
            f"no override can apply; defaulting to MEDIUM",
            "mcp.default_medium",
        )
    server_component, tool_component = parsed

    config = _current_config()
    if config is None:
        # Defensive: load_config never raises by design, but an
        # unexpected failure must not read as "no overrides, MEDIUM".
        return _result(
            RiskLevel.CRITICAL,
            f"Server '{server_component}': mcp_config.yml could not be "
            f"read; classification fails closed rather than downgrading "
            f"a live tool to the MEDIUM default",
            "mcp.server_absent_fail_closed",
        )

    for server in config.servers:
        if not _match_component(server.name, server_component):
            continue
        # Per-tool first: the most specific statement wins.
        for tool_key, level in server.tool_risk.items():
            if _match_component(tool_key, tool_component):
                return _result(
                    level,
                    f"Per-tool override: mcp_config.yml server "
                    f"'{server.name}' classifies tool '{tool_key}' "
                    f"as {level.value.upper()}",
                    "mcp.tool_risk",
                )
        if server.risk_override is not None:
            return _result(
                server.risk_override,
                f"Server override: mcp_config.yml classifies every "
                f"tool from server '{server.name}' as "
                f"{server.risk_override.value.upper()}",
                "mcp.risk_override",
            )
        return _result(
            MCP_DEFAULT_RISK,
            "MCP tool with no risk override in mcp_config.yml — "
            "defaulting to MEDIUM (executes with a warning)",
            "mcp.default_medium",
        )

    # Registered tool, absent server: removed, renamed, or dropped by
    # validation since registration. Fail closed — the exact scenario
    # per-call freshness exists for must not become a silent downgrade.
    return _result(
        RiskLevel.CRITICAL,
        _absent_reason(server_component, config),
        "mcp.server_absent_fail_closed",
    )


def mcp_risk_summary() -> Dict[str, Any]:
    """The current per-server MCP risk classification, for display (B5).

    Reads the SAME fresh config classification does (a flip shows here
    without a restart), so the dashboard can render "filesystem: HIGH"
    from live config. Shape::

        {
            "default": "medium",
            "servers": {
                "filesystem": {
                    "risk_override": "high",       # None when unset
                    "tool_risk": {"read_file": "safe"},
                },
            },
            # B3 fail-closed context, so the UI can explain a blocked
            # MCP tool the same way the refusal reason does:
            "skipped_servers": ["filesystem"],     # dropped by validation
            "load_error": "",                      # "" = file was readable
        }

    Server names are as written in the config (not sanitized) — this is
    a config-facing view; the qualified-name mapping is
    classification's business.
    """
    servers: Dict[str, Dict[str, Any]] = {}
    skipped: List[str] = []
    load_error = ""
    config = _current_config()
    if config is not None:
        for server in config.servers:
            servers[server.name] = {
                "risk_override": (
                    server.risk_override.value
                    if server.risk_override is not None else None),
                "tool_risk": {
                    tool: level.value
                    for tool, level in server.tool_risk.items()
                },
            }
        skipped = list(config.skipped_servers)
        load_error = config.load_error
    return {
        "default": MCP_DEFAULT_RISK.value,
        "servers": servers,
        "skipped_servers": skipped,
        "load_error": load_error,
    }


def mcp_args_preview(args: Any, cap: int = 400) -> str:
    """A short, bounded preview of an MCP tool's args for the
    confirmation message. The args are what the REMOTE server will
    receive, so they are the thing to show — capped, because an MCP
    tool's payload can be arbitrarily large and the confirmation
    surface must not flood."""
    import json

    try:
        text = json.dumps(args, default=str)
    except (TypeError, ValueError):
        text = str(args)
    if len(text) > cap:
        return text[:cap] + f"… ({len(text)} characters total; truncated)"
    return text if text else "(no arguments)"


def describe_mcp_tool(tool_name: str) -> Tuple[str, str]:
    """(server, tool) display components for a qualified name; honest
    placeholders when the name does not parse."""
    parsed = parse_qualified_tool_name(tool_name)
    if parsed is None:
        return ("(unknown server)", tool_name)
    return parsed