# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""MCP client configuration.

Loaded from ``get_config_dir()/mcp_config.yml`` (platform dependent:
``~/Library/Application Support/Halbert/`` on macOS, ``~/.config/halbert/``
on Linux). The shipped default is EMPTY — no servers, capability inert.
There are no curated defaults and no discovery suggestions; servers are
configured one at a time by the host (founder ruling, 2026-09-08).

The config is read on EVERY call (not cached), so changes take effect
immediately without a restart — the same pattern as vision/config.py and
applescript_config.py. A user who removes a server must not have the
client still talking to it from a stale cache.

Security: ``auth.token_env`` names an environment variable; the token
value lives in the environment, never in the config. A literal ``token``
key IS accepted (some users will write one), but it is treated as a
secret at every logging site — warnings about config problems are
scrubbed of every literal token in the file before they are emitted, and
``MCPServerConfig.describe()`` never includes it.

Config shape (see .handoff workstream B plan):

    servers:
      - name: filesystem
        transport: stdio
        command: npx
        args: ["-y", "@modelcontextprotocol/server-filesystem", "/Users/eric"]
        env: {KEY: value}            # extra subprocess env (merged over os.environ)
        risk_override: high           # B3: every tool from this server classifies HIGH
        tool_risk:                   # B3: per-tool levels, each beats the server override
          delete_file: critical
          read_file: safe
      - name: linear
        transport: http
        url: https://mcp.linear.app/mcp
        auth:
          type: bearer
          token_env: LINEAR_MCP_TOKEN
        timeout_seconds: 30

Risk classification (B3), honestly: MCP tools are remote. The safety
framework's pattern-matching classifier reads shell commands and script
text — it cannot read what a server on the other end of a transport will
do with a ``tools/call``. Config overrides are therefore the PRIMARY
mechanism and the burden is on the operator to classify servers
correctly. Absent any override a tool classifies MEDIUM (executes, with
the framework's warning semantics — see tools/safety.py). Levels are the
framework's own: safe, low, medium, high, critical (case-insensitive).
Precedence per call: per-tool ``tool_risk`` > server ``risk_override`` >
MEDIUM default.

Overrides are parsed HERE (validated once per config read, into
``tools.safety.RiskLevel`` values) but consumed per call by
``tools/mcp_safety.py`` against this freshly re-read config — a risk flip
gates the NEXT tool call with no restart, exactly like every other key
in this file. ``tool_risk`` keys are tool names as the SERVER advertises
them (the unsanitized form you would see in tools/list); matching
against a registered ``mcp__{server}__{tool}`` name goes through the
registry's sanitization.

Fail TIGHT, not loose: an invalid level name (``risk_override: extreme``,
``tool_risk: {x: banana}``) or a non-mapping ``tool_risk`` skips the
whole server entry with a warning. The loader's rule for every other
validation failure (unknown transport, missing command) is "the server
contributes nothing"; a typo'd risk level must not silently downgrade a
server the operator meant to fence — and at agent start a skipped server
connects to nothing, so its tools are absent entirely. (Mid-process,
classification itself fails closed on the skip — see
tools/mcp_safety.py.)

Sanitized-name collisions: two servers whose names sanitize to the same
registered namespace (``my-fs`` and ``my_fs``; also a case-only
difference, since override matching is case-insensitive) would make
classification depend on config order, so the loader keeps the FIRST and
skips the later colliding entry with a warning naming both raw names.
Honest consequence, for whoever builds on this: that check is a
determinism win, NOT a closure — a colliding entry inserted BEFORE a
fenced server displaces the fence at load, and tools registered from
the displaced server classify under the surviving entry, not fail
closed. B4's health-refresh re-registration (dropping stale ``mcp__``
registrations and re-bridging from current config) is what closes the
displacement; this load-time check cannot.

Entries that fail validation are skipped with a warning, never raise —
a corrupt config means "no servers", not a dead agent.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

from ..tools.safety import RiskLevel
from .registry import components_match, sanitize_component

logger = logging.getLogger("halbert.mcp.config")

#: Default per-request / per-operation timeout. A hung server must never
#: hang the agent (workstream B1 acceptance).
DEFAULT_TIMEOUT_SECONDS = 30.0

_SUPPORTED_TRANSPORTS = ("stdio", "http")


def config_path() -> Path:
    """Path to mcp_config.yml in the user's config directory."""
    try:
        from ..utils.platform import get_config_dir
        return get_config_dir() / "mcp_config.yml"
    except Exception:
        return Path.home() / ".config" / "halbert" / "mcp_config.yml"


def _redact(text: str) -> str:
    """Redact a log/error string. Belt-and-suspenders: callers already
    avoid interpolating secrets, but ``redact_text`` runs last so a
    future edit that leaks a value into a message still fails closed."""
    try:
        from ..ingestion.redaction import redact_text
        return redact_text(text, prose=True)
    except Exception:
        return text


def redact_url(url: str) -> str:
    """A URL safe to put in a log or error message: stripped of embedded
    credentials (``user:pass@``) and query-string secrets (``?key=...``,
    ``?token=...``). Every message that interpolates a configured server
    URL goes through here — a URL is config/user input, and the
    tokens-never-logged rule applies to it too."""
    return _redact(str(url))


def redact(text: str) -> str:
    """Public alias of the module's redactor, for sibling modules that
    interpolate config-written text into messages or logs
    (tools/mcp_safety.py does, for dropped server names in fail-closed
    refusal reasons) — the same scrub ``load_error`` gets, without
    reaching into a module-private name."""
    return _redact(str(text))


#: Variable names already warned about as unset (see
#: MCPAuthConfig.resolve_token). One warning per misconfigured name,
#: ever — resolve_token runs on every HTTP request and a repeat warning
#: per call would flood the log.
_WARNED_MISSING_TOKEN_ENVS: set = set()


@dataclass
class MCPAuthConfig:
    """How to authenticate to a remote (HTTP) server.

    ``token_env`` — name of the environment variable holding the token
    (preferred). ``token`` — a literal token; accepted but never logged.
    """
    type: str = ""        # "bearer" (the only type today)
    token_env: str = ""
    token: str = ""

    def resolve_token(self) -> Optional[str]:
        """The token value: literal first, else the named env var.

        Re-resolved on every call — rotating the env var takes effect
        without a restart, same as the rest of the config. A missing env
        var resolves to None (and the server's 401 is the clear error);
        it is logged as the variable NAME, never a value — and the
        warning fires ONCE per variable name, not once per HTTP call
        (resolve_token runs on every request; a misconfigured variable
        must not flood the log).
        """
        if self.token:
            return self.token
        if self.token_env:
            value = os.environ.get(self.token_env)
            if not value:
                if self.token_env in _WARNED_MISSING_TOKEN_ENVS:
                    logger.debug(
                        "MCP auth: token env var '%s' is still not set",
                        self.token_env)
                else:
                    _WARNED_MISSING_TOKEN_ENVS.add(self.token_env)
                    logger.warning(
                        "MCP auth: token env var '%s' is not set",
                        self.token_env)
            return value or None
        return None


@dataclass
class MCPServerConfig:
    """One configured MCP server.

    B3 risk fields: ``risk_override`` is the per-server classification
    (None = no override, the classifier's MEDIUM default applies);
    ``tool_risk`` maps server-advertised tool names to levels, each
    beating the server override for that tool. Both are None/empty when
    the config does not set them, and both are DELIBERATELY excluded
    from :meth:`signature` — a risk flip is a classification change, not
    a connection change, and classification re-reads this config on
    every call anyway (forcing a reconnect would gate nothing that the
    per-call read does not already gate).
    """
    name: str
    transport: str = "stdio"      # stdio | http
    command: str = ""             # stdio: executable to launch
    args: List[str] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)
    url: str = ""                 # http: server endpoint
    auth: Optional[MCPAuthConfig] = None
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    risk_override: Optional[RiskLevel] = None       # B3: per-server level
    tool_risk: Dict[str, RiskLevel] = field(default_factory=dict)  # B3: per-tool

    def signature(self) -> Tuple:
        """Identity of the CONNECTION this config produces. The client
        compares signatures on every call to decide whether a live
        connection still matches the config (hot-reload): a change means
        disconnect and reconnect. The literal token VALUE is included —
        the transport binds this config object's resolver, so a rotated
        literal token only takes effect through a reconnect — but the
        signature is compared, never logged. An ``token_env`` rotation
        needs no reconnect (the env var is re-read per request)."""
        auth = self.auth
        return (
            self.name,
            self.transport,
            self.command,
            tuple(self.args),
            tuple(sorted(self.env.items())),
            self.url,
            auth.type if auth else "",
            auth.token_env if auth else "",
            auth.token if auth else "",
            self.timeout_seconds,
        )

    def describe(self) -> str:
        """A loggable one-line description. Never includes the token;
        the URL passes through redaction because a URL may embed
        user:pass credentials."""
        if self.transport == "stdio":
            text = f"stdio server '{self.name}' ({self.command} {' '.join(self.args)})"
        else:
            text = f"http server '{self.name}' ({self.url})"
        return _redact(text)


@dataclass
class MCPClientConfig:
    """The whole mcp_config.yml, re-read on every use.

    B3 diagnostics, so a fail-closed classification can say WHY a
    registered tool's server is absent (see tools/mcp_safety.py):
    ``skipped_servers`` names the entries dropped at load — by
    validation, by the duplicate-name rule, or by the sanitized-name
    collision rule (only entries that had a name at all);
    ``load_error`` says why nothing could be read — missing file,
    unparseable YAML, wrong shape — redacted, never raw file content.
    Both are empty when the config is merely empty: no servers and no
    problems are different states, and the refusal reason should not
    claim a problem that is not there.
    """
    servers: List[MCPServerConfig] = field(default_factory=list)
    skipped_servers: List[str] = field(default_factory=list)
    load_error: str = ""

    def server(self, name: str) -> Optional[MCPServerConfig]:
        for s in self.servers:
            if s.name == name:
                return s
        return None


def _collect_literal_tokens(data: Any) -> List[str]:
    """Every literal token value in the raw parsed config, so config
    warnings can be scrubbed of secrets the user wrote into the file."""
    tokens: List[str] = []
    if isinstance(data, dict):
        if isinstance(data.get("servers"), list):
            for entry in data["servers"]:
                if not isinstance(entry, dict):
                    continue
                auth = entry.get("auth")
                if isinstance(auth, dict):
                    t = auth.get("token")
                    if isinstance(t, str) and t:
                        tokens.append(t)
    return tokens


def _scrub(text: str, secrets: List[str]) -> str:
    for s in secrets:
        if s:
            text = text.replace(s, "<redacted>")
    return _redact(text)


def _parse_auth(entry: Dict[str, Any]) -> Optional[MCPAuthConfig]:
    auth = entry.get("auth")
    if auth is None:
        return None
    if not isinstance(auth, dict):
        raise ValueError("auth must be a mapping")
    auth_type = str(auth.get("type", "bearer")).strip().lower()
    if auth_type not in ("bearer", ""):
        raise ValueError(f"unsupported auth type '{auth_type}' (supported: bearer)")
    return MCPAuthConfig(
        type=auth_type or "bearer",
        token_env=str(auth.get("token_env", "") or ""),
        token=str(auth.get("token", "") or ""),
    )


#: Valid risk level names, for the invalid-override warning message.
_RISK_LEVEL_NAMES = tuple(level.value for level in RiskLevel)


def _parse_risk_level(value: Any) -> RiskLevel:
    """A config-written risk level name → RiskLevel. Case-insensitive.

    Raises ValueError for anything that is not a valid level name —
    never a silent fallback. The caller (``_parse_server``) skips the
    whole server on a bad level: classification fails TIGHT, not loose
    (see the module docstring).
    """
    if not isinstance(value, str):
        raise ValueError(
            f"risk level must be one of {', '.join(_RISK_LEVEL_NAMES)}, "
            f"got {type(value).__name__}")
    name = value.strip().lower()
    try:
        return RiskLevel(name)
    except ValueError:
        raise ValueError(
            f"unknown risk level '{value}' "
            f"(valid: {', '.join(_RISK_LEVEL_NAMES)})") from None


def _parse_risk_overrides(entry: Dict[str, Any]) -> "tuple":
    """The B3 override keys of one servers[] entry:
    (risk_override, tool_risk). Raises ValueError on an invalid level —
    a ValueError here means the whole server entry is skipped (fail
    tight), matching how every other validation failure is handled."""
    risk_override = entry.get("risk_override")
    if risk_override is not None:
        risk_override = _parse_risk_level(risk_override)

    tool_risk: Dict[str, RiskLevel] = {}
    raw_tool_risk = entry.get("tool_risk")
    if raw_tool_risk is not None:
        if not isinstance(raw_tool_risk, dict):
            raise ValueError("tool_risk must be a mapping of tool name to risk level")
        for tool_name, level in raw_tool_risk.items():
            if level is None:
                raise ValueError(
                    f"tool_risk['{tool_name}'] has no risk level "
                    f"(valid: {', '.join(_RISK_LEVEL_NAMES)})")
            tool_risk[str(tool_name)] = _parse_risk_level(level)

    return risk_override, tool_risk


def _parse_server(entry: Any, index: int, default_timeout: float) -> Optional[MCPServerConfig]:
    """Validate one `servers:` entry. Returns None (with a warning) for
    anything unusable — never raises."""
    if not isinstance(entry, dict):
        logger.warning("MCP config: servers[%d] is not a mapping, skipping", index)
        return None
    name = str(entry.get("name", "") or "").strip()
    if not name:
        logger.warning("MCP config: servers[%d] has no name, skipping", index)
        return None

    transport = str(entry.get("transport", "stdio") or "stdio").strip().lower()
    if transport not in _SUPPORTED_TRANSPORTS:
        logger.warning(
            "MCP config: server '%s' has unknown transport '%s' "
            "(supported: stdio, http), skipping", name, transport)
        return None

    command = str(entry.get("command", "") or "").strip()
    url = str(entry.get("url", "") or "").strip()
    if transport == "stdio" and not command:
        logger.warning("MCP config: stdio server '%s' has no command, skipping", name)
        return None
    if transport == "http" and not url:
        logger.warning("MCP config: http server '%s' has no url, skipping", name)
        return None

    raw_args = entry.get("args") or []
    if not isinstance(raw_args, list):
        logger.warning("MCP config: server '%s' args is not a list, skipping", name)
        return None
    args = [str(a) for a in raw_args]

    raw_env = entry.get("env") or {}
    if not isinstance(raw_env, dict):
        logger.warning("MCP config: server '%s' env is not a mapping, ignoring env", name)
        raw_env = {}
    env = {str(k): str(v) for k, v in raw_env.items()}

    try:
        auth = _parse_auth(entry)
    except ValueError as e:
        logger.warning("MCP config: server '%s' auth invalid (%s), skipping", name, e)
        return None

    try:
        timeout = float(entry.get("timeout_seconds", default_timeout))
    except (TypeError, ValueError):
        logger.warning(
            "MCP config: server '%s' timeout_seconds is not a number, using default", name)
        timeout = default_timeout
    if timeout <= 0:
        logger.warning(
            "MCP config: server '%s' timeout_seconds must be positive, using default", name)
        timeout = default_timeout

    # B3 risk overrides. A ValueError skips the WHOLE server (fail
    # tight): an invalid level name must never silently fall back to
    # MEDIUM for a server the operator meant to fence, and a skipped
    # server connects to nothing in production — its tools are absent,
    # not medium.
    try:
        risk_override, tool_risk = _parse_risk_overrides(entry)
    except ValueError as e:
        logger.warning(
            "MCP config: server '%s' risk classification invalid (%s), "
            "skipping the server — overrides fail tight, not loose", name, e)
        return None

    return MCPServerConfig(
        name=name,
        transport=transport,
        command=command,
        args=args,
        env=env,
        url=url,
        auth=auth,
        timeout_seconds=timeout,
        risk_override=risk_override,
        tool_risk=tool_risk,
    )


def load_config() -> MCPClientConfig:
    """Load the MCP client config from disk.

    Re-read on every call. Missing file, unparseable YAML, or a
    non-mapping document all mean the SAME thing: zero servers, the
    capability inert, no crash (founder ruling: absent/corrupt config
    degrades to "no servers").
    """
    path = config_path()
    if not path.exists():
        return MCPClientConfig(load_error="config file missing")
    try:
        with open(path) as f:
            data = yaml.safe_load(f)
    except Exception as e:
        logger.warning("MCP config: failed to load %s (%s); no servers", path, e)
        return MCPClientConfig(load_error=f"unparseable: {_redact(str(e))}")

    if data is None:
        return MCPClientConfig()  # empty file — the shipped default
    if not isinstance(data, dict):
        logger.warning("MCP config: %s is not a mapping; no servers", path)
        return MCPClientConfig(load_error="file is not a mapping")

    # Scrub literal tokens out of every warning below — the user may
    # have written one into the file despite token_env being preferred.
    secrets = _collect_literal_tokens(data)
    raw_servers = data.get("servers")
    if raw_servers is None:
        return MCPClientConfig()
    if not isinstance(raw_servers, list):
        logger.warning(
            "MCP config: 'servers' is not a list; no servers (%s)",
            _scrub(repr(raw_servers)[:200], secrets))
        return MCPClientConfig(load_error="'servers' is not a list")

    try:
        default_timeout = float(data.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS))
    except (TypeError, ValueError):
        default_timeout = DEFAULT_TIMEOUT_SECONDS

    servers: List[MCPServerConfig] = []
    skipped: List[str] = []
    seen: set = set()                    # raw names (the classic dup rule)
    seen_sanitized: Dict[str, str] = {}  # sanitized+lower key -> raw name
    for index, entry in enumerate(raw_servers):
        parsed = _parse_server(entry, index, default_timeout)
        if parsed is None:
            # B3 diagnostic: name what was dropped, so a fail-closed
            # classification can say "dropped by validation: fs" instead
            # of a bare "absent". Entries with no name cannot be named.
            if isinstance(entry, dict):
                dropped = str(entry.get("name", "") or "").strip()
                if dropped:
                    skipped.append(dropped)
            continue
        if parsed.name in seen:
            logger.warning(
                "MCP config: duplicate server name '%s', keeping the first",
                parsed.name)
            skipped.append(parsed.name)
            continue
        # The shared matcher (registry.components_match) decides what
        # collides — the same rule classification and the bridge's
        # unmatched-key warning use, so the three cannot drift.
        colliding_with = next(
            (raw for raw in seen_sanitized.values()
             if components_match(raw, parsed.name)), None)
        if colliding_with is not None:
            # B3: ``my-fs`` and ``my_fs`` (and a case-only difference)
            # sanitize to the SAME registered namespace, so keeping both
            # would make classification order-dependent — the first
            # matching config entry would win. Keep the first, name both.
            # NOTE: this is a determinism win, not a closure — a
            # colliding entry inserted BEFORE a fenced server displaces
            # the fence; B4's re-registration closes that.
            logger.warning(
                "MCP config: server '%s' sanitizes to the same name as "
                "server '%s'; keeping the first, skipping '%s' — "
                "otherwise classification would depend on config order",
                parsed.name, colliding_with, parsed.name)
            skipped.append(parsed.name)
            continue
        seen.add(parsed.name)
        seen_sanitized[sanitize_component(parsed.name).lower()] = parsed.name
        servers.append(parsed)
    return MCPClientConfig(
        servers=servers, skipped_servers=skipped)