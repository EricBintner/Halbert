# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""MCP client configuration.

Loaded from ``get_config_dir()/mcp_config.yml`` (platform dependent:
``~/Library/Application Support/Halbert/`` on macOS, ``~/.config/halbert/``
on Linux). The shipped default is EMPTY — no servers, capability inert.
There are no curated defaults and no discovery suggestions; servers are
configured one at a time by the host (founder ruling, 2026-09-08).

The config is read on every call, MEMOIZED BY FILE IDENTITY (B4): the
stat identity — ``(st_mtime_ns, st_size, st_ino)`` — of
``mcp_config.yml`` is checked first, and an unchanged file serves the
already-parsed :class:`MCPClientConfig` instead of re-parsing. This
collapses the two YAML parses per MCP execute that the per-call readers
(classification + the client's ``_ensure``) used to pay, and collapses
the per-call repeat of every load-time warning (a skipped server or a
collision used to emit its warning twice per call, forever). Freshness
is preserved: any write that changes the file changes its identity, and
the next call reads from disk (verified by tests: flip → seen, pin the
mtime → cached, corrupt → fixed cycle re-reads). Consumers must treat
the returned :class:`MCPClientConfig` as READ-ONLY — it is shared
between every reader until the file changes. The identity (not just
mtime) is what makes this safe to key on: size and inode catch a
rewrite the filesystem timestamps too coarsely to notice, and a path
switch (``HALBERT_CONFIG_DIR``) keys a separate slot per path.

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
closed. The closure lives in the health monitor's refresh
(mcp/health.py): it re-runs discovery/registration from CURRENT config
whenever this file's identity changes, dropping every ``mcp__``
registration whose server the refreshed config does not carry — so the
displaced server's tools do not survive the edit.

Entries that fail validation are skipped with a warning, never raise —
a corrupt config means "no servers", not a dead agent.
"""
from __future__ import annotations

import fnmatch
import logging
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Dict, List, Mapping, Optional, Tuple

import yaml

from ..tools.safety import RiskLevel
from .registry import components_match, sanitize_component

logger = logging.getLogger("halbert.mcp.config")

#: Default per-request / per-operation timeout. A hung server must never
#: hang the agent (workstream B1 acceptance).
DEFAULT_TIMEOUT_SECONDS = 30.0

_SUPPORTED_TRANSPORTS = ("stdio", "http")


def make_tool_filter(tools_entry: Any):
    """Build the "may this tool register" predicate for one server.

    A17-G18. Without it there was no way to say which of a server's
    tools to take: the first 64 in whatever order the server returned
    them, and the 65th dropped with a log line. Include is a whitelist
    where an EMPTY list means nothing (that is how an operator turns a
    server off without deleting its entry); exclude is a blacklist;
    include wins where both name a tool. Names match exactly, by the
    same sanitized-component rule the risk overrides use, or as an
    fnmatch glob.
    """
    if not isinstance(tools_entry, dict):
        return lambda _name: True
    raw_include = tools_entry.get("include")
    include = None
    if isinstance(raw_include, list):
        include = tuple(str(x) for x in raw_include)
    exclude = tuple(
        str(x) for x in (tools_entry.get("exclude") or [])
        if isinstance(tools_entry.get("exclude"), list)
    )
    return _tool_filter(include, exclude)


def _tool_filter(include: Optional[Tuple[str, ...]], exclude: Tuple[str, ...]):
    def _matches(patterns, name: str) -> bool:
        for pattern in patterns:
            if pattern == name or fnmatch.fnmatchcase(name, pattern):
                return True
            if components_match(pattern, name):
                return True
        return False

    def keep(name: str) -> bool:
        if include is not None:
            return _matches(include, name)
        if exclude and _matches(exclude, name):
            return False
        return True

    return keep


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


@dataclass(frozen=True)
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


@dataclass(frozen=True)
class MCPServerConfig:
    """One configured MCP server.

    B4: instances are FROZEN with read-only collection fields — the
    memo (load_config) hands the same object to every reader, so a
    mutation anywhere would silently corrupt classification
    process-wide; a config change is expressed by writing the file.
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
    args: Tuple[str, ...] = field(default_factory=tuple)
    env: Mapping[str, str] = field(default_factory=lambda: MappingProxyType({}))
    url: str = ""                 # http: server endpoint
    auth: Optional[MCPAuthConfig] = None
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    risk_override: Optional[RiskLevel] = None       # B3: per-server level
    tool_risk: Mapping[str, RiskLevel] = field(
        default_factory=lambda: MappingProxyType({}))  # B3: per-tool
    #: A17-G18: which of the server's advertised tools to register.
    #: ``tool_include`` is a whitelist -- present and empty means NONE,
    #: which is how an operator turns a server off without removing it;
    #: absent means "no whitelist". ``tool_exclude`` is a blacklist, and
    #: include wins where both name a tool. Both accept exact names or
    #: fnmatch globs. Excluded from ``signature()`` for the same reason
    #: the risk fields are: a filter change is a registration change,
    #: not a connection change.
    tool_include: Optional[Tuple[str, ...]] = None
    tool_exclude: Tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        """Normalize the collection fields into read-only shapes. The
        memo hands the SAME config object to every reader (classifier,
        client, monitor, status route) until the file changes — so the
        collections are frozen into tuples / mapping proxies at
        construction: one future mutation site would otherwise silently
        corrupt classification process-wide with no local breakage."""
        object.__setattr__(self, "args", tuple(self.args))
        if not isinstance(self.env, MappingProxyType):
            object.__setattr__(self, "env", MappingProxyType(dict(self.env)))
        if not isinstance(self.tool_risk, MappingProxyType):
            object.__setattr__(self, "tool_risk",
                               MappingProxyType(dict(self.tool_risk)))

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


@dataclass(frozen=True)
class MCPClientConfig:
    """The whole mcp_config.yml, re-read on every use.

    B4: FROZEN with read-only collection fields (see MCPServerConfig) —
    the memo hands this same object to classification, the client's
    hot-reload check, the monitor and the status route until the file
    changes.

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
    servers: Tuple[MCPServerConfig, ...] = field(default_factory=tuple)
    skipped_servers: Tuple[str, ...] = field(default_factory=tuple)
    load_error: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "servers", tuple(self.servers))
        object.__setattr__(self, "skipped_servers",
                           tuple(self.skipped_servers))

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

    # A17-G3, the loader rule: an entry whose SHAPE is a payload does not
    # spawn. The write classifier catches the agent's own write to this
    # file; a hand edit, a restored backup or a file planted by anything
    # else never passes through it, so the second gate is here, where the
    # entry is used. Skipping fails tight the same way an invalid risk
    # override does: the server is absent, not degraded. The finding
    # names the shape and never the entry's own strings.
    try:
        from .entry_guard import validate_server_entry
        findings = validate_server_entry(name, entry)
    except Exception as e:  # pragma: no cover - import-time only
        logger.warning(
            "MCP config: entry screen unavailable (%s) — refusing to "
            "launch server '%s' unscreened", e, name)
        return None
    if findings:
        logger.error(
            "MCP config: refusing to launch server '%s' — %s",
            name, "; ".join(findings))
        return None

    # A17-G18: the operator's tool filter for this server.
    tools_entry = entry.get("tools")
    tool_include = None
    tool_exclude: tuple = ()
    if isinstance(tools_entry, dict):
        raw_include = tools_entry.get("include")
        if isinstance(raw_include, list):
            tool_include = tuple(str(x) for x in raw_include)
        raw_exclude = tools_entry.get("exclude")
        if isinstance(raw_exclude, list):
            tool_exclude = tuple(str(x) for x in raw_exclude)
    elif tools_entry is not None:
        logger.warning(
            "MCP config: server '%s' tools is not a mapping, ignoring it",
            name)

    return MCPServerConfig(
        name=name,
        transport=transport,
        command=command,
        args=tuple(args),
        env=MappingProxyType(env),
        url=url,
        auth=auth,
        timeout_seconds=timeout,
        risk_override=risk_override,
        tool_risk=tool_risk,
        tool_include=tool_include,
        tool_exclude=tool_exclude,
    )


def _config_identity(path: Path) -> tuple:
    """The file identity a memo slot is keyed against: mtime nanoseconds,
    size, and inode. ``None`` members mean "no file" — a MISSING file is
    memoizable too (its result is cheap, but memoizing it collapses the
    per-call stat+read for a deployment with no config at all)."""
    try:
        stat = path.stat()
        return (stat.st_mtime_ns, stat.st_size, stat.st_ino)
    except OSError:
        return (None, None, None)


#: The per-path memo slot: ``path`` -> (identity, parsed config). One
#: slot per distinct config path (multi-instance processes each point
#: ``HALBERT_CONFIG_DIR`` at their own directory, so in practice one);
#: a file change replaces its slot in place, so memory never grows with
#: the number of EDITS. Consumers of any returned MCPClientConfig must
#: treat it as READ-ONLY — it is shared between every reader until the
#: file's identity changes.
_CONFIG_MEMO: Dict[str, tuple] = {}


def load_config() -> MCPClientConfig:
    """Load the MCP client config from disk, memoized by file identity.

    Every call stats the file first; an unchanged identity serves the
    cached :class:`MCPClientConfig` (see the module docstring), a changed
    (or first-seen) one re-reads and re-parses. Missing file, unparseable
    YAML, or a non-mapping document all mean the SAME thing: zero
    servers, the capability inert, no crash (founder ruling:
    absent/corrupt config degrades to "no servers").
    """
    path = config_path()
    identity = _config_identity(path)
    slot = _CONFIG_MEMO.get(str(path))
    if slot is not None and slot[0] == identity:
        return slot[1]
    config = _read_config(path)
    _CONFIG_MEMO[str(path)] = (identity, config)
    return config


#: The load_error string for a MISSING file — the one unreadable-config
#: state a consumer may ACT on: a missing file is a legitimate removal
#: (every server is gone), unlike every other load_error ("unparseable:
#: …", "file is not a mapping", "'servers' is not a list"), which means
#: the file EXISTS but could not be read — there the consumer is blind
#: and must keep prior state rather than acting on an empty server list
#: (mcp/bridge.py's diff is the consumer).
MISSING_CONFIG_LOAD_ERROR = "config file missing"


def reset_config_memo() -> None:
    """Drop every memo slot (test isolation; a restart clears it the
    same way by being a new process)."""
    _CONFIG_MEMO.clear()


def _read_config(path: Path) -> MCPClientConfig:
    """The disk read behind :func:`load_config` — the original
    (uncached) loader body."""
    if not path.exists():
        return MCPClientConfig(
            load_error=MISSING_CONFIG_LOAD_ERROR)
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
            # the fence; the health monitor's refresh (B4, mcp/health.py)
            # closes that by re-bridging from current config.
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
        servers=tuple(servers), skipped_servers=tuple(skipped))


# ---------------------------------------------------------------------------
# Dashboard write path (B5): the UI's edits to mcp_config.yml land here.
#
# The loader above is the truth about what a config MEANS; the write path
# reuses it rather than keeping a second, looser validator — every entry
# the dashboard writes is parsed with the SAME ``_parse_server`` before a
# byte is replaced, and the serialized file is parsed back and compared
# against that parse BEFORE the rename. What the UI writes therefore
# loads back exactly, or the write never happens.
#
# Atomicity: temp file in the config's own directory, ``os.replace`` —
# a crash mid-write leaves the previous file intact and never a partial
# one (the same guarantee the memo's identity keying presumes).
#
# Secrets: the dashboard API carries an env var NAME (``token_env``),
# never a token value. A literal ``token`` the user hand-wrote into an
# existing entry is PRESERVED on an unrelated edit (it stays in the file
# it was already in; it never crosses the API and is never echoed back),
# but a write that would INTRODUCE a literal token is refused — the
# token_env flow exists so a secret typed into a web form is not persisted
# to disk in the first place. Every error message this section raises
# passes through ``redact`` before it reaches a response or a log.
# ---------------------------------------------------------------------------

class ConfigWriteError(Exception):
    """A config edit the write path refused (message is safe to serve —
    it is redacted at raise sites that interpolate user input)."""


def _captured_parse_server(
    entry: Any, index: int, default_timeout: float,
) -> MCPServerConfig:
    """``_parse_server`` with its skip-warning captured as the error
    detail. The loader's validation lives in one place (no drift): the
    write path just reads the same warning the loader would log. The
    message is already token-scrubbed (``_scrub`` runs at the warning
    sites for shapes that carry raw config text) and is redacted again
    by the caller before it is served."""
    captured: List[logging.LogRecord] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            captured.append(record)

    handler = _Capture(level=logging.WARNING)
    logger.addHandler(handler)
    try:
        parsed = _parse_server(entry, index, default_timeout)
    finally:
        logger.removeHandler(handler)
    if parsed is None:
        detail = captured[0].getMessage() if captured else (
            "entry is not a valid MCP server configuration")
        raise ValueError(redact(detail))
    return parsed


def serialize_server_entry(config: MCPServerConfig) -> Dict[str, Any]:
    """A parsed server config → the canonical ``servers:`` entry the
    file stores. The dashboard writes THIS (derived from the validated
    parse, not from the request body), so "what was written" and "what
    loads back" are the same object by construction."""
    entry: Dict[str, Any] = {"name": config.name}
    entry["transport"] = config.transport
    if config.transport == "stdio":
        entry["command"] = config.command
        if config.args:
            entry["args"] = list(config.args)
    else:
        entry["url"] = config.url
    if config.env:
        entry["env"] = dict(config.env)
    if config.auth is not None and (config.auth.token_env or config.auth.token):
        auth: Dict[str, Any] = {"type": config.auth.type}
        if config.auth.token_env:
            auth["token_env"] = config.auth.token_env
        if config.auth.token:
            # Only ever reached for a token read back out of the same
            # file (preservation on an unrelated edit) — the dashboard
            # API has no field that could introduce one.
            auth["token"] = config.auth.token
        entry["auth"] = auth
    if config.timeout_seconds != DEFAULT_TIMEOUT_SECONDS:
        entry["timeout_seconds"] = config.timeout_seconds
    if config.risk_override is not None:
        entry["risk_override"] = config.risk_override.value
    if config.tool_risk:
        entry["tool_risk"] = {
            tool: level.value for tool, level in config.tool_risk.items()}
    return entry


def _round_trip_equal(
    first: MCPServerConfig, second: MCPServerConfig,
) -> bool:
    """Did the serialize → file → parse cycle preserve the server?
    Connection identity via ``signature`` (name/transport/command/args/
    env/url/auth incl. a preserved literal token/timeout) plus the B3
    risk fields (excluded from the signature on purpose, so compared
    here explicitly)."""
    return (
        first.signature() == second.signature()
        and first.risk_override == second.risk_override
        and dict(first.tool_risk) == dict(second.tool_risk)
    )


def _read_raw_document(path: Path) -> Optional[Dict[str, Any]]:
    """The fresh (unmemoized) raw document, or ``None`` for a MISSING
    file. A file that exists but cannot be read raises
    :class:`ConfigWriteError` — the dashboard refuses to overwrite a
    config it cannot parse (an unreadable file may hold hand-written
    servers; replacing it with an empty document would silently delete
    them)."""
    if not path.exists():
        return None
    try:
        with open(path) as f:
            data = yaml.safe_load(f)
    except Exception as e:
        raise ConfigWriteError(
            "mcp_config.yml is unreadable (%s) — refusing to overwrite "
            "it from the dashboard; edit the file by hand"
            % redact(str(e))) from None
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ConfigWriteError(
            "mcp_config.yml is not a mapping — refusing to overwrite it "
            "from the dashboard; edit the file by hand")
    raw_servers = data.get("servers")
    if raw_servers is not None and not isinstance(raw_servers, list):
        raise ConfigWriteError(
            "'servers' in mcp_config.yml is not a list — refusing to "
            "overwrite it from the dashboard; edit the file by hand")
    return data


def _atomic_write_yaml(path: Path, document: Dict[str, Any]) -> None:
    """Serialize, then replace atomically (temp file in the same
    directory + ``os.replace``): a crash mid-write leaves the previous
    file intact, never a truncated one. Note the file is rewritten in
    canonical YAML form — hand-written comments are not preserved (the
    established pattern, tools/write_config.py's _apply_yaml)."""
    text = yaml.safe_dump(document, sort_keys=False, allow_unicode=True)
    directory = path.parent
    directory.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=path.name + ".", suffix=".tmp", dir=str(directory))
    try:
        with os.fdopen(fd, "w") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


def edit_servers(
    mutator, default_timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> MCPClientConfig:
    """Apply *mutator* to the raw ``servers:`` list and atomically
    replace the file.

    The mutator receives the raw entries (list of dicts / raw shapes as
    written) and returns ``(new_entries, touched)`` — the new list, plus
    the indexes it changed, so ONLY what the edit wrote is held to the
    validated round-trip (a hand-broken entry elsewhere in the file is
    the operator's own state; the dashboard neither fixes nor clobbers
    it, and the loader keeps skipping it exactly as before).

    Returns the freshly re-read :class:`MCPClientConfig` (the write
    changed the file identity, so ``load_config`` re-parses; nothing
    else is needed to make the next reader see the edit).

    Raises :class:`ConfigWriteError` (or ValueError from the mutator) —
    both mean "nothing was written".
    """
    path = config_path()
    document = _read_raw_document(path) or {}
    raw_servers = document.get("servers")
    entries: List[Any] = list(raw_servers) if isinstance(raw_servers, list) else []
    new_entries, touched = mutator(list(entries))

    new_document = dict(document)
    new_document["servers"] = new_entries

    # Round-trip gate, touched entries only: serialize the whole new
    # document, parse THAT back, and require every touched entry to load
    # back to the same server the pre-write validation produced. A
    # mismatch (a YAML shape that eats a field, a type the dumper
    # mutates) aborts the write before the replace.
    for index in touched:
        raw_entry = new_entries[index]
        expected = _captured_parse_server(raw_entry, index, default_timeout)
        text = yaml.safe_dump(new_document, sort_keys=False,
                              allow_unicode=True)
        try:
            reloaded = yaml.safe_load(text)
        except Exception as e:  # pragma: no cover - safe_dump of parsed data
            raise ConfigWriteError(
                f"serialized config failed to re-parse ({redact(str(e))})")
        round_entries = (reloaded or {}).get("servers") or []
        if index >= len(round_entries):
            raise ConfigWriteError(
                f"server '{expected_name(expected)}' did "
                f"not survive serialization")
        reparsed = _captured_parse_server(
            round_entries[index], index, default_timeout)
        if not _round_trip_equal(expected, reparsed):
            raise ConfigWriteError(
                f"server '{expected.name}' did not round-trip through "
                f"serialization — refusing to write it")

    _atomic_write_yaml(path, new_document)
    return load_config()


def expected_name(expected: Any = None, **_: Any) -> str:
    """The server name a failed round-trip was for (a formatting helper
    kept tiny so the error paths above stay one-line)."""
    try:
        return getattr(expected, "name", "?")
    except Exception:  # pragma: no cover - defensive only
        return "?"


def add_server_entry(entry: Dict[str, Any]) -> MCPClientConfig:
    """Validate *entry* as a whole new server and append it. A name that
    duplicates an existing one (exactly or after sanitization — the same
    rule the loader's collision check applies) is refused here so the
    dashboard answers 400 instead of writing an entry the loader would
    skip."""
    parsed = _captured_parse_server(entry, 0, DEFAULT_TIMEOUT_SECONDS)

    def _mutate(entries: List[Any]) -> "tuple":
        existing_raw = [
            (i, e) for i, e in enumerate(entries) if isinstance(e, dict)]
        for index, existing in existing_raw:
            name = str(existing.get("name", "") or "").strip()
            if not name:
                continue
            if name == parsed.name or components_match(name, parsed.name):
                raise ValueError(
                    f"a server named '{name}' is already configured")
        canonical = serialize_server_entry(parsed)
        entries.append(canonical)
        return entries, [len(entries) - 1]

    return edit_servers(_mutate)


def remove_server_entry(name: str) -> MCPClientConfig:
    """Remove every entry written as *name* (the loader keeps the first
    of a duplicate pair, so removing by exact raw name is the operator's
    own intent). Raises ValueError when the name is not configured —
    never a silent no-op."""

    def _mutate(entries: List[Any]) -> "tuple":
        keep: List[Any] = []
        removed = 0
        for entry in entries:
            if (isinstance(entry, dict)
                    and str(entry.get("name", "") or "").strip() == name):
                removed += 1
                continue
            keep.append(entry)
        if not removed:
            raise ValueError(f"no server named '{name}' is configured")
        return keep, []

    return edit_servers(_mutate)


def set_risk_overrides(
    name: str,
    risk_override: Optional[str],
    tool_risk: Optional[Dict[str, str]],
) -> MCPClientConfig:
    """Set (or clear, with None) one server's B3 override keys. Every
    other key of the entry — including a literal ``auth.token`` the user
    hand-wrote — is preserved untouched. Raises ValueError when the
    server is not configured or the level names are invalid."""

    def _mutate(entries: List[Any]) -> "tuple":
        for index, entry in enumerate(entries):
            if not (isinstance(entry, dict)
                    and str(entry.get("name", "") or "").strip() == name):
                continue
            modified = dict(entry)
            if risk_override is None:
                modified.pop("risk_override", None)
            else:
                modified["risk_override"] = str(risk_override)
            if tool_risk is None:
                modified.pop("tool_risk", None)
            else:
                modified["tool_risk"] = {
                    str(tool): str(level)
                    for tool, level in tool_risk.items()}
            # Validate the MODIFIED entry before anything is written —
            # an invalid level is a 400, never a silently skipped server.
            parsed = _captured_parse_server(
                modified, index, DEFAULT_TIMEOUT_SECONDS)
            canonical = serialize_server_entry(parsed)
            entries[index] = canonical
            return entries, [index]
        raise ValueError(f"no server named '{name}' is configured")

    return edit_servers(_mutate)