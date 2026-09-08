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
3. Config — the applescript config file
   (``get_config_dir()/applescript_config.yml``) ``enabled:`` is re-read
   on EVERY tool call (never cached), so flipping the file takes effect
   immediately; a registered tool refuses to execute while the switch is
   off (a stale registration is never a leak — only a stale schema
   offered to the model).

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
from typing import Any, Dict, List, Optional, Tuple

from ..config import applescript_config

logger = logging.getLogger("halbert.tools.applescript")

#: Per-stream output cap (stdout and stderr each). osascript output is
#: read into memory, so an uncapped stream (a huge ``ls``, a log dump)
#: would buffer without bound. At the cap the process is stopped and a
#: truncation notice is returned — the model sees partial output plus
#: why it is partial.
MAX_OUTPUT_BYTES = 1024 * 1024

_READ_CHUNK = 64 * 1024

#: Grace period for reaping a child after its pipes closed or we killed it.
_EXIT_GRACE_SECONDS = 5.0


# ─────────────────────────────────────────────────────────────────────────────
# Subprocess execution
# ─────────────────────────────────────────────────────────────────────────────

def _result(success: bool, output: str = "", error: str = "",
            exit_code: Optional[int] = None) -> Dict[str, Any]:
    """The structured result shape every handler path returns."""
    return {
        "success": success,
        "output": output,
        "error": error,
        "exit_code": exit_code,
    }


def _kill(proc) -> None:
    """Kill the child, tolerating one that already exited.

    Timeout-path kill race: a grandchild holding the pipes can keep the
    reads blocked past the timeout while the child itself is gone —
    ``kill()`` then raises ``ProcessLookupError``, which must not escape
    the structured-result contract.
    """
    try:
        proc.kill()
    except ProcessLookupError:
        pass


async def _reap(proc) -> None:
    """Wait briefly for the child to exit; fall back to a guarded kill."""
    try:
        await asyncio.wait_for(proc.wait(), timeout=_EXIT_GRACE_SECONDS)
    except asyncio.TimeoutError:
        _kill(proc)


async def _read_capped(stream, limit: int) -> Tuple[bytes, bool]:
    """Read one pipe to EOF or the byte cap. Returns (bytes, truncated)."""
    chunks = []
    total = 0
    while True:
        chunk = await stream.read(_READ_CHUNK)
        if not chunk:
            return b"".join(chunks), False
        if total + len(chunk) > limit:
            chunks.append(chunk[: limit - total])
            return b"".join(chunks), True
        chunks.append(chunk)
        total += len(chunk)


async def _collect_output(proc, limit: int) -> Tuple[bytes, bytes, bool, bool]:
    """Read both pipes concurrently (a sequential read can deadlock when
    one pipe fills while we block on the other). The first stream to hit
    the cap ends collection and the sibling read is cancelled — the
    caller then stops the process, since a writer with no reader would
    block forever. Returns (stdout, stderr, stdout_truncated,
    stderr_truncated).
    """
    out_task = asyncio.create_task(_read_capped(proc.stdout, limit))
    err_task = asyncio.create_task(_read_capped(proc.stderr, limit))
    out = err = b""
    out_trunc = err_trunc = False
    pending = {out_task, err_task}
    try:
        while pending:
            done, pending = await asyncio.wait(
                pending, return_when=asyncio.FIRST_COMPLETED)
            truncated_now = False
            for task in done:
                data, was_truncated = task.result()
                if task is out_task:
                    out, out_trunc = data, was_truncated
                else:
                    err, err_trunc = data, was_truncated
                truncated_now = truncated_now or was_truncated
            if truncated_now:
                break
    finally:
        for task in (out_task, err_task):
            if not task.done():
                task.cancel()
        await asyncio.gather(out_task, err_task, return_exceptions=True)
    return out, err, out_trunc, err_trunc


async def _execute(argv: List[str]) -> Dict[str, Any]:
    """Run osascript (argv list, no shell) and capture stdout/stderr/exit code.

    The timeout comes from applescript_config.yml (re-read here, per call)
    and is enforced with asyncio.wait_for: on expiry the process is
    killed and a structured timeout error is returned — never a hang,
    never a raise. SEC-2 lesson (tools/system_info.py): the script
    travels as one ``-e`` argv element, so there is no shell to escape.
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
        return _result(False, error=f"Failed to launch osascript: {e}")

    try:
        out, err, out_trunc, err_trunc = await asyncio.wait_for(
            _collect_output(proc, MAX_OUTPUT_BYTES), timeout=timeout)
    except asyncio.TimeoutError:
        _kill(proc)
        await _reap(proc)
        logger.warning(f"osascript timed out after {timeout}s and was killed")
        return _result(
            False,
            error=f"Script timed out after {timeout}s and was killed "
                  f"(timeout_seconds in applescript_config.yml).",
        )
    except Exception as e:
        _kill(proc)
        await _reap(proc)
        logger.warning(f"osascript communication failed: {e}")
        return _result(False, error=f"osascript communication failed: {e}")

    truncated = out_trunc or err_trunc
    if truncated:
        # The cap cut a stream short: stop the process (it may still be
        # writing into a pipe nobody reads) and report the partial output
        # with a notice, so the model knows the result is partial.
        _kill(proc)
        await _reap(proc)
        stream = "stdout" if out_trunc else "stderr"
        logger.warning(f"osascript output exceeded {MAX_OUTPUT_BYTES} bytes; process stopped")
        err_text = err.decode(errors="replace")
        notice = (f"Output exceeded the {MAX_OUTPUT_BYTES} byte cap "
                  f"({stream} truncated); the process was stopped.")
        return _result(
            False,
            output=out.decode(errors="replace"),
            error=(f"{err_text}\n{notice}" if err_text else notice),
            exit_code=proc.returncode,
        )

    # Both pipes hit EOF — the child is done (or closed its output early).
    await _reap(proc)
    exit_code = proc.returncode if proc.returncode is not None else -1
    return _result(exit_code == 0, output=out.decode(errors="replace"),
                   error=err.decode(errors="replace"), exit_code=exit_code)


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
        try:
            where = str(applescript_config._config_path())
        except Exception:
            where = "applescript_config.yml"
        return _result(
            False,
            error=f"AppleScript execution is disabled ({where}: enabled: false). "
                  "Enable it to allow script execution.",
        )
    if platform.system() != "Darwin":
        return _result(
            False,
            error="AppleScript tools require macOS (osascript).",
        )
    return None


def _script_from_args(args: Dict) -> Tuple[Optional[str], Optional[str]]:
    """Extract the script string. Returns (script, error); error is set
    for missing/empty and non-string input (a list arg must not reach
    ``str.strip`` and crash the handler)."""
    script = args.get("script")
    if script is None or (isinstance(script, str) and not script.strip()):
        return None, "No script provided (empty 'script' argument)."
    if not isinstance(script, str):
        return None, f"'script' must be a string, got {type(script).__name__}."
    return script.strip(), None


async def _run_applescript_handler(args: Dict) -> Dict[str, Any]:
    """Execute an AppleScript string via ``osascript -e``."""
    refusal = _gate_check()
    if refusal is not None:
        return refusal
    script, error = _script_from_args(args)
    if error is not None:
        return _result(False, error=error)
    return await _execute(["osascript", "-e", script])


async def _run_jxa_handler(args: Dict) -> Dict[str, Any]:
    """Execute a JavaScript for Automation string via ``osascript -l JavaScript -e``."""
    refusal = _gate_check()
    if refusal is not None:
        return refusal
    script, error = _script_from_args(args)
    if error is not None:
        return _result(False, error=error)
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
            "stderr, and exit code. Use for querying and controlling macOS "
            "applications. A script that exceeds the configured timeout is "
            "killed. Syntax errors return stderr verbatim so you can "
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


def register_applescript_tools(tool_executor) -> None:
    """Register AppleScript/JXA tools with a ToolExecutor instance.

    macOS only (osascript) and gated on the CAP_APPLESCRIPT capability.
    The per-call applescript config switch still gates every execution
    after registration, so the caller does not need to check it here.
    """
    if platform.system() != "Darwin":
        logger.info("AppleScript tools not registered: requires macOS")
        return

    try:
        from ..capabilities import CAP_APPLESCRIPT, has_capability
        if not has_capability(CAP_APPLESCRIPT):
            logger.info("AppleScript tools not registered: capability is off")
            return
    except Exception as e:
        logger.debug("CAP_APPLESCRIPT lookup failed, applescript stays off: %s", e)
        return

    for name, schema in APPLESCRIPT_TOOL_SCHEMAS.items():
        handler = APPLESCRIPT_TOOL_HANDLERS.get(name)
        if handler:
            tool_executor.register(name, handler, schema)
        else:
            logger.warning(f"AppleScript tool '{name}' has schema but no handler — skipped")
    logger.info("Registered AppleScript tools (run_applescript, run_jxa)")
