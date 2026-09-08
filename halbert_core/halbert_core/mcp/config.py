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
      - name: linear
        transport: http
        url: https://mcp.linear.app/sse
        auth:
          type: bearer
          token_env: LINEAR_MCP_TOKEN
        timeout_seconds: 30

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
        it is logged as the variable NAME, never a value.
        """
        if self.token:
            return self.token
        if self.token_env:
            value = os.environ.get(self.token_env)
            if not value:
                logger.warning(
                    "MCP auth: token env var '%s' is not set", self.token_env)
            return value or None
        return None


@dataclass
class MCPServerConfig:
    """One configured MCP server."""
    name: str
    transport: str = "stdio"      # stdio | http
    command: str = ""             # stdio: executable to launch
    args: List[str] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)
    url: str = ""                 # http: server endpoint
    auth: Optional[MCPAuthConfig] = None
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS

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
    """The whole mcp_config.yml, re-read on every use."""
    servers: List[MCPServerConfig] = field(default_factory=list)

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

    return MCPServerConfig(
        name=name,
        transport=transport,
        command=command,
        args=args,
        env=env,
        url=url,
        auth=auth,
        timeout_seconds=timeout,
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
        return MCPClientConfig()
    try:
        with open(path) as f:
            data = yaml.safe_load(f)
    except Exception as e:
        logger.warning("MCP config: failed to load %s (%s); no servers", path, e)
        return MCPClientConfig()

    if data is None:
        return MCPClientConfig()  # empty file — the shipped default
    if not isinstance(data, dict):
        logger.warning("MCP config: %s is not a mapping; no servers", path)
        return MCPClientConfig()

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
        return MCPClientConfig()

    try:
        default_timeout = float(data.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS))
    except (TypeError, ValueError):
        default_timeout = DEFAULT_TIMEOUT_SECONDS

    servers: List[MCPServerConfig] = []
    seen: set = set()
    for index, entry in enumerate(raw_servers):
        parsed = _parse_server(entry, index, default_timeout)
        if parsed is None:
            continue
        if parsed.name in seen:
            logger.warning(
                "MCP config: duplicate server name '%s', keeping the first",
                parsed.name)
            continue
        seen.add(parsed.name)
        servers.append(parsed)
    return MCPClientConfig(servers=servers)