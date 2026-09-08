# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
AppleScript / JXA Tools (A1)

Give the agent a voice on macOS: run an AppleScript string or a
JavaScript for Automation string via ``osascript``. Following the tool
module pattern (register_gpu_tools / register_system_tools), this module
exposes ``APPLESCRIPT_TOOL_SCHEMAS`` + ``APPLESCRIPT_TOOL_HANDLERS`` and
a ``register_applescript_tools(tool_executor)`` entry point.

Gating is layered, OFF by default at every layer:

1. Platform — macOS only (``osascript`` does not exist elsewhere).
   Checked at registration and again inside the handler.
2. Capability — ``CAP_APPLESCRIPT`` from capabilities.py (a preset /
   being.yml decision, no probe). Checked at registration.
3. Config — ~/.config/halbert/applescript_config.yml ``enabled:`` is
   re-read on EVERY tool call (never cached), so flipping the file takes
   effect immediately; a registered tool refuses to execute while the
   switch is off (a stale registration is never a leak — only a stale
   schema offered to the model).

RoleGate (guest persona) integration lands in A2; nothing here executes
while the config is off regardless.

Risks noted in the plan: osascript subprocess overhead (~50-100ms per
call, acceptable) and unhelpful syntax-error messages — stderr is
surfaced verbatim in ``error`` so the agent can self-correct.
"""

from __future__ import annotations

import asyncio
import logging
import platform
from typing import Any, Dict, List, Optional

from ..config import applescript_config

logger = logging.getLogger("halbert.tools.applescript")


# ─────────────────────────────────────────────────────────────────────────────
# Subprocess execution
# ─────────────────────────────────────────────────────────────────────────────

def _result(success: bool, output: str = "", error: str = "",
            exit_code: Optional[int] = 0) -> Dict[str, Any]:
    """The structured result shape every handler path returns."""
    return {
        "success": success,
        "output": output,
        "error": error,
        "exit_code": exit_code,
    }


async def _execute(argv: List[str]) -> Dict[str, Any]:
    """Run osascript (argv list, no shell) and capture stdout/stderr/exit code.

    The timeout comes from applescript_config.yml (re-read here, per call)
    and is enforced with asyncio.wait_for: on expiry the process is killed
    and a structured timeout error is returned — never a hang, never a
    raise. SEC-2 lesson (tools/system_info.py): the script travels as one
    ``-e`` argv element, so there is no shell to escape.
    """
    cfg = applescript_config.load_config()
    timeout = max(1, int(cfg.timeout_seconds))

    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except Exception as e:
        logger.warning(f"osascript launch failed: {e}")
        return _result(False, error=f"Failed to launch osascript: {e}",
                       exit_code=None)

    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        logger.warning(f"osascript timed out after {timeout}s and was killed")
        return _result(
            False,
            error=f"Script timed out after {timeout}s and was killed "
                  f"(timeout_seconds in applescript_config.yml).",
            exit_code=None,
        )
    except Exception as e:
        logger.warning(f"osascript communication failed: {e}")
        return _result(False, error=f"osascript communication failed: {e}",
                       exit_code=None)

    output = out.decode(errors="replace")
    error = err.decode(errors="replace")
    exit_code = proc.returncode if proc.returncode is not None else -1
    return _result(exit_code == 0, output=output, error=error, exit_code=exit_code)


# ─────────────────────────────────────────────────────────────────────────────
# Tool handlers
# ─────────────────────────────────────────────────────────────────────────────

def _gate_check() -> Optional[Dict[str, Any]]:
    """Config + platform gates shared by both handlers.

    Returns a refusal result when execution must not proceed, or None to
    go ahead. The config switch is checked FIRST: nothing executes —
    not even the platform check matters — while the user has the feature
    off. The switch is re-read on every call (see applescript_config).
    """
    if not applescript_config.is_applescript_enabled():
        return _result(
            False,
            error="AppleScript execution is disabled "
                  "(applescript_config.yml: enabled: false). "
                  "Enable it to allow script execution.",
            exit_code=None,
        )
    if platform.system() != "Darwin":
        return _result(
            False,
            error="AppleScript tools require macOS (osascript).",
            exit_code=None,
        )
    return None


def _script_from_args(args: Dict) -> Optional[str]:
    """Extract the script string, refusing empty input."""
    script = (args.get("script") or "").strip()
    if not script:
        return None
    return script


async def _run_applescript_handler(args: Dict) -> Dict[str, Any]:
    """Execute an AppleScript string via ``osascript -e``."""
    refusal = _gate_check()
    if refusal is not None:
        return refusal
    script = _script_from_args(args)
    if script is None:
        return _result(False, error="No script provided (empty 'script' argument).",
                       exit_code=None)
    return await _execute(["osascript", "-e", script])


async def _run_jxa_handler(args: Dict) -> Dict[str, Any]:
    """Execute a JavaScript for Automation string via ``osascript -l JavaScript -e``."""
    refusal = _gate_check()
    if refusal is not None:
        return refusal
    script = _script_from_args(args)
    if script is None:
        return _result(False, error="No script provided (empty 'script' argument).",
                       exit_code=None)
    return await _execute(["osascript", "-l", "JavaScript", "-e", script])


# ─────────────────────────────────────────────────────────────────────────────
# Tool schemas + registration (same pattern as gpu_tools.py)
# ─────────────────────────────────────────────────────────────────────────────

# Tool schemas for registration
APPLESCRIPT_TOOL_SCHEMAS = {
    "run_applescript": {
        "name": "run_applescript",
        "description": (
            "Execute an AppleScript string via osascript and capture stdout, "
            "stderr, and exit code. Use for macOS app control (Finder, Music, "
            "System Events, ...). A script that exceeds the configured timeout "
            "is killed. Syntax errors return stderr verbatim so you can "
            "self-correct."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "script": {
                    "type": "string",
                    "description": "The AppleScript source to execute, e.g. "
                                   "'tell application \"Finder\" to name of home'",
                },
            },
            "required": ["script"],
        },
    },
    "run_jxa": {
        "name": "run_jxa",
        "description": (
            "Execute a JavaScript for Automation (JXA) string via "
            "'osascript -l JavaScript' and capture stdout, stderr, and exit "
            "code. Prefer run_applescript for plain AppleScript; JXA suits "
            "JavaScript-native logic and ObjC bridges. Same timeout applies."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "script": {
                    "type": "string",
                    "description": "The JavaScript for Automation source to execute, "
                                   "e.g. 'Application(\"Finder\").home().name()'",
                },
            },
            "required": ["script"],
        },
    },
}

# Handler mapping
APPLESCRIPT_TOOL_HANDLERS = {
    "run_applescript": _run_applescript_handler,
    "run_jxa": _run_jxa_handler,
}


def register_applescript_tools(tool_executor) -> bool:
    """Register AppleScript/JXA tools with a ToolExecutor instance.

    macOS only (osascript) and gated on the CAP_APPLESCRIPT capability;
    returns True when tools were registered. The per-call applescript
    config switch still gates every execution after registration, so the
    caller does not need to check it here.
    """
    if platform.system() != "Darwin":
        logger.info("AppleScript tools not registered: requires macOS")
        return False

    try:
        from ..capabilities import CAP_APPLESCRIPT, has_capability
        if not has_capability(CAP_APPLESCRIPT):
            logger.info("AppleScript tools not registered: capability is off")
            return False
    except Exception as e:
        logger.debug("CAP_APPLESCRIPT lookup failed, applescript stays off: %s", e)
        return False

    for name, schema in APPLESCRIPT_TOOL_SCHEMAS.items():
        handler = APPLESCRIPT_TOOL_HANDLERS.get(name)
        if handler:
            tool_executor.register(name, handler, schema)
        else:
            logger.warning(f"AppleScript tool '{name}' has schema but no handler — skipped")
    logger.info("Registered AppleScript tools (run_applescript, run_jxa)")
    return True