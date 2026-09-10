# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Screen one MCP server config entry before it is allowed to spawn.

A17-G3's loader rule. ``mcp_config.yml`` is a list of commands Halbert
will execute, and two things were true of it: on macOS it lived under
``~/Library/Application Support``, which the write classifier did not
treat as sensitive (fixed in ``tools/safety.py``), and the health monitor
relaunches a server within a tick of its config identity changing. So an
edit to that file is a command execution, and the write gate is only the
first of the two places to catch one -- a hand edit, a restored backup or
a file planted by anything other than the agent never passes through the
classifier at all.

This is the second gate, run where the entry is *used*: the loader
refuses to return a suspicious entry (contributing zero servers, the
module's existing graceful-absence rule) and the dashboard's write path
refuses to save one.

Deliberately **not** an allowlist. ``npx``, ``uvx``, ``pipx`` and
``python`` are how MCP servers are actually distributed, and a list of
approved commands would either block real servers or be widened until it
meant nothing. What is screened is *shape*: a shell interpreter invoked
with an inline script, a fetch piped into an interpreter, a raw egress
helper, a write to a persistence surface. Deterministic patterns only --
no model, no network call, no reputation list (the origin's campaign-IOC
substrings are deliberately dropped: an indicator list is stale the day
it ships).

Findings name the shape and never the value: the entry's own strings are
what a planted file controls, so echoing them into a UI error or a log
line is how a screen becomes an amplifier.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

#: Programs whose whole job is to run a script someone hands them. An
#: MCP server is a program with a protocol; a shell with an inline
#: script is a payload with a launcher.
_SHELL_INTERPRETERS = frozenset({
    "sh", "bash", "zsh", "dash", "ksh", "csh", "tcsh", "fish",
    "cmd", "cmd.exe", "powershell", "powershell.exe", "pwsh",
})

#: The inline-script flags those interpreters take.
_INLINE_SCRIPT_FLAGS = frozenset({"-c", "-Command", "/c", "/C", "-e"})

#: A fetch piped into something that runs it -- the shape, in either order.
_FETCH_PIPE = re.compile(
    r"\b(curl|wget|fetch|iwr|invoke-webrequest)\b[^|]*\|\s*"
    r"(sudo\s+)?(sh|bash|zsh|dash|python[0-9.]*|perl|ruby|node)\b",
    re.IGNORECASE,
)

#: Raw egress helpers: no MCP server needs one to speak its protocol.
_EGRESS = re.compile(
    r"(^|[\s;&|])(nc|ncat|netcat|socat|telnet)([\s]|$)|/dev/tcp/|/dev/udp/",
    re.IGNORECASE,
)

#: Surfaces that survive a restart. A server entry that writes to one is
#: not configuring a server.
_PERSISTENCE = re.compile(
    r"authorized_keys|\.ssh/|sudoers|/etc/cron|crontab|systemd/system|"
    r"LaunchAgents|LaunchDaemons|\.bashrc|\.zshrc|\.profile|"
    r"/etc/rc\.local",
    re.IGNORECASE,
)

#: Base64-into-interpreter, the other common inline payload shape.
_ENCODED_EXEC = re.compile(
    r"\b(base64|openssl\s+enc|xxd)\b[^|]*\|\s*(sh|bash|python[0-9.]*|perl)\b",
    re.IGNORECASE,
)


def _scan(text: str) -> List[str]:
    """Findings for one flattened string."""
    findings: List[str] = []
    if _FETCH_PIPE.search(text):
        findings.append(
            "entry fetches a remote script and pipes it into an interpreter"
        )
    if _ENCODED_EXEC.search(text):
        findings.append("entry decodes an inline payload into an interpreter")
    if _EGRESS.search(text):
        findings.append("entry invokes a raw network egress helper")
    if _PERSISTENCE.search(text):
        findings.append("entry references a persistence surface")
    return findings


def validate_server_entry(name: str, entry: Dict[str, Any]) -> List[str]:
    """Findings for one server entry; an empty list means "may spawn".

    ``name`` is used only for the caller's log line -- the screen itself
    reads the command, its arguments and its env VALUES, because a
    command can be innocent while the payload rides in the environment.
    """
    transport = str(entry.get("transport") or "stdio").strip().lower()
    if transport != "stdio":
        # Nothing to launch: an HTTP entry's URL is screened by the
        # transport's own scheme check, not by shell heuristics.
        return []

    command = str(entry.get("command") or "").strip()
    args = [str(a) for a in (entry.get("args") or [])]
    env_values = [str(v) for v in (entry.get("env") or {}).values()]

    findings: List[str] = []
    program = command.rsplit("/", 1)[-1]
    if program.lower() in _SHELL_INTERPRETERS and any(
        a in _INLINE_SCRIPT_FLAGS for a in args
    ):
        findings.append(
            "entry launches a shell interpreter with an inline script"
        )
    if program.lower() in {"nc", "ncat", "netcat", "socat", "telnet"}:
        findings.append("entry invokes a raw network egress helper")

    for text in [command, *args, *env_values]:
        for finding in _scan(text):
            if finding not in findings:
                findings.append(finding)
    return findings
