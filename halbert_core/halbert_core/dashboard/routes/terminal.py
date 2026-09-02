# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Terminal API routes.

Provides endpoints for terminal command execution via real PTY sessions
(B1e), plus session lifecycle endpoints (list/input/resize/stream/kill) for
interactive terminal tiles in the frontend.

Safety layering (B1e):
- ``check_command_safety`` (Phase 13d tier checks) stays — the frontend uses it.
- ``streaming/injection_check`` adds the injection/danger patterns terminal.py
  doesn't cover (superset).
- ``streaming/sandbox.Sandbox`` wraps the command before the PTY runs it.
- sudo is NOT stripped: the PTY handles password prompts and the frontend
  shows the ``Password:`` prompt in the output stream.
"""

from __future__ import annotations
import asyncio
import json
import logging
import shlex
from typing import Literal, Optional, List
from enum import Enum

try:
    from fastapi import APIRouter, HTTPException
    from fastapi.responses import StreamingResponse
    from pydantic import BaseModel, Field
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    APIRouter = object
    StreamingResponse = None  # type: ignore

from ...streaming.session_manager import (
    get_terminal_manager, AtCapacityError,
)
from ...streaming.bounded_output import BoundedOutput
from ...streaming.sandbox import Sandbox
from ...streaming.injection_check import (
    is_blocked, uses_elevation, check_injection, worst_severity,
    InjectionSeverity,
)

logger = logging.getLogger('halbert.dashboard.routes.terminal')

router = APIRouter() if FASTAPI_AVAILABLE else None


class SafetyTier(str, Enum):
    """Phase 13d: Command safety tiers."""
    SAFE = "safe"           # Auto-execute without warning
    CAUTION = "caution"     # Show warning, execute on confirm
    DANGEROUS = "dangerous" # Show strong warning, require explicit confirm
    BLOCKED = "blocked"     # Never execute


class CommandRequest(BaseModel):
    command: str
    cwd: Optional[str] = None
    # Bounded: an unvalidated timeout let a caller pin a PTY session and an
    # unbounded output buffer open for as long as it liked (R04-F7). Five
    # minutes is well past anything /exec should be used for -- longer work
    # belongs in a session tile.
    timeout: int = Field(default=30, ge=1, le=300)
    force: bool = False  # Skip safety confirmation (for pre-approved commands)


class CommandResponse(BaseModel):
    output: str
    error: str
    exit_code: int
    command: str
    safety_tier: str = "safe"
    safety_warning: str = ""


class SafetyCheckResponse(BaseModel):
    """Phase 13d: Safety check result for frontend."""
    command: str
    tier: str
    allowed: bool
    warning: str
    requires_confirmation: bool
    suggestion: str = ""


class SpawnRequest(BaseModel):
    """B1e: Spawn an interactive PTY session."""
    command: str
    cwd: Optional[str] = None
    cols: int = 80
    rows: int = 24
    writable_paths: Optional[List[str]] = None
    # The manager reaps by kind: oneshot at 60s idle, user at 1800s and never
    # while a client is attached. This endpoint backs the interactive tiles,
    # so its default is "user" -- spawning without one made every dashboard
    # terminal a oneshot and the reaper killed shells the user simply was not
    # typing into (R04-F1). Whitelisted: a caller must not be able to name a
    # kind with a longer TTL or a different cap than the manager expects.
    kind: Literal["user", "oneshot"] = "user"


class SpawnResponse(BaseModel):
    session_id: str
    pid: int
    command: str
    sandboxed: bool


class InputRequest(BaseModel):
    data: str


class ResizeRequest(BaseModel):
    cols: int
    rows: int


class StageRequest(BaseModel):
    """Plan B: B9 — Stage a command into a user shell at an empty prompt."""
    command: str


class WatchedRequest(BaseModel):
    """Plan B: B8 — Toggle watched status of a user shell session."""
    watched: bool


# Blocked commands - NEVER execute
BLOCKED_COMMANDS = {
    'rm -rf /',
    'rm -rf /*',
    'dd if=/dev/zero of=/dev/sd',
    'mkfs.',
    ':(){:|:&};:',  # Fork bomb
    '> /dev/sda',
    '> /dev/nvme',
}

# Dangerous commands - require explicit confirmation
DANGEROUS_PATTERNS = [
    ('rm -rf', 'Recursive forced delete - files cannot be recovered'),
    ('dd if=', 'Direct disk write - can destroy data'),
    ('mkfs', 'Filesystem format - will erase all data'),
    ('fdisk', 'Partition table modification'),
    ('parted', 'Partition modification'),
    ('sudo rm -rf', 'Elevated recursive delete'),
    ('chmod -R 777', 'Recursive world-writable permissions'),
    ('chown -R', 'Recursive ownership change'),
    ('systemctl disable', 'Disabling system service'),
    ('apt remove', 'Package removal'),
    ('apt purge', 'Package purge with config'),
]

# Caution commands - show warning but allow
CAUTION_PATTERNS = [
    ('sudo ', 'Elevated privileges required'),
    ('rm ', 'File deletion'),
    ('mv ', 'File move/rename'),
    ('chmod ', 'Permission change'),
    ('chown ', 'Ownership change'),
    ('systemctl restart', 'Service restart'),
    ('systemctl stop', 'Service stop'),
    ('pip install', 'Python package installation'),
    ('npm install', 'Node.js package installation'),
    ('apt install', 'Package installation'),
]


def check_command_safety(command: str) -> tuple[SafetyTier, str, str]:
    """
    Phase 13d: Check command safety tier.

    Returns: (tier, warning, suggestion)
    """
    cmd_lower = command.lower().strip()

    # Check blocked commands first
    for blocked in BLOCKED_COMMANDS:
        if blocked in cmd_lower:
            return SafetyTier.BLOCKED, f"This command is blocked: {blocked}", ""

    # Delegate to the injection gate: it covers order/form variants the
    # substring lists below miss (dd of=<device>, split rm flags, pipes
    # into interpreters). BLOCKED findings always win.
    findings = check_injection(command)
    if findings:
        worst = worst_severity(findings)
        if worst is InjectionSeverity.BLOCKED:
            reason = next(f.reason for f in findings
                          if f.severity is InjectionSeverity.BLOCKED)
            return SafetyTier.BLOCKED, f"Blocked by injection check: {reason}", ""
        if worst is InjectionSeverity.DANGEROUS:
            reason = next(f.reason for f in findings
                          if f.severity is InjectionSeverity.DANGEROUS)
            return SafetyTier.DANGEROUS, reason, ""

    # Check dangerous patterns
    for pattern, reason in DANGEROUS_PATTERNS:
        if pattern in cmd_lower:
            suggestion = ""
            if 'rm -rf' in pattern:
                suggestion = "Consider using 'rm -ri' for interactive deletion"
            return SafetyTier.DANGEROUS, reason, suggestion

    # Check caution patterns
    for pattern, reason in CAUTION_PATTERNS:
        if pattern in cmd_lower:
            return SafetyTier.CAUTION, reason, ""

    return SafetyTier.SAFE, "", ""


def is_command_safe(command: str) -> tuple[bool, str]:
    """Legacy safety check for backward compatibility."""
    tier, warning, _ = check_command_safety(command)

    if tier == SafetyTier.BLOCKED:
        return False, warning

    return True, warning


def _gate_command(command: str) -> tuple[SafetyTier, str, str, Optional[str]]:
    """Run both safety layers and return (tier, warning, suggestion, blocked_reason).

    If either layer blocks, returns BLOCKED with the blocking reason. Used by
    /exec and the spawn endpoint so the gate is consistent.
    """
    tier, warning, suggestion = check_command_safety(command)
    if tier == SafetyTier.BLOCKED:
        return tier, warning, suggestion, f"Blocked by safety check: {warning}"
    # Injection check is a superset; its BLOCKED findings override.
    if is_blocked(command):
        findings = check_injection(command)
        reason = next((f.reason for f in findings
                       if f.severity is InjectionSeverity.BLOCKED), "blocked")
        return SafetyTier.BLOCKED, reason, suggestion, f"Blocked by injection check: {reason}"
    return tier, warning, suggestion, None


if FASTAPI_AVAILABLE:

    @router.post("/exec", response_model=CommandResponse)
    async def execute_command(request: CommandRequest):
        """
        Execute a shell command one-shot via a real PTY session.

        The session is spawned, drained to completion, and killed. For
        interactive use (stdin, resize, streaming), use the /sessions
        endpoints instead. sudo is NOT stripped — the PTY surfaces password
        prompts in the output.
        """
        command = request.command.strip()

        if not command:
            raise HTTPException(400, "Empty command")

        tier, warning, _suggestion, blocked = _gate_command(command)
        if blocked:
            raise HTTPException(403, blocked)

        # Wrap with the platform sandbox (no-op if unavailable)
        sandbox = Sandbox()
        writable = [request.cwd] if request.cwd else None
        wrapped = sandbox.wrap_command(command, writable_paths=writable)

        manager = get_terminal_manager()
        try:
            session_id = await manager.spawn(
                wrapped, cwd=request.cwd,
                cols=80, rows=24,
            )
        except AtCapacityError:
            raise HTTPException(503, "Terminal session manager at capacity")

        session = manager.get(session_id)
        # Same bound as the agent pool's blocks, for the same reason: the
        # response is a string a human reads, so holding the whole of a
        # `cat /dev/urandom` in memory to build it is pure loss.
        output = BoundedOutput()

        async def drain():
            async for chunk in session.read_chunk():
                output.extend(chunk)

        try:
            await asyncio.wait_for(drain(), timeout=request.timeout)
        except asyncio.TimeoutError:
            manager.kill(session_id)
            return CommandResponse(
                output=output.bytes().decode('utf-8', errors='replace'),
                error=f"Command timed out after {request.timeout}s",
                exit_code=-1,
                command=command,
                safety_tier=tier.value,
                safety_warning=warning,
            )

        exit_code = session.exit_code if session.exit_code is not None else -1
        manager.kill(session_id)  # idempotent cleanup

        logger.info(f"Executed (PTY): {command[:50]}... (exit={exit_code})")
        return CommandResponse(
            output=output.bytes().decode('utf-8', errors='replace'),
            error="",
            exit_code=exit_code,
            command=command,
            safety_tier=tier.value,
            safety_warning=warning,
        )

    # ------------------------------------------------------------------
    # Session lifecycle endpoints (B1e)
    # ------------------------------------------------------------------

    @router.post("/sessions", response_model=SpawnResponse)
    async def spawn_session(request: SpawnRequest):
        """Spawn an interactive PTY session and return its id."""
        command = request.command.strip()
        if not command:
            raise HTTPException(400, "Empty command")

        _tier, warning, _sug, blocked = _gate_command(command)
        if blocked:
            raise HTTPException(403, blocked)

        sandbox = Sandbox()
        wrapped = sandbox.wrap_command(command, writable_paths=request.writable_paths)
        manager = get_terminal_manager()
        try:
            session_id = await manager.spawn(
                wrapped, cwd=request.cwd,
                cols=request.cols, rows=request.rows,
                kind=request.kind,
            )
        except AtCapacityError:
            raise HTTPException(503, "Terminal session manager at capacity")

        session = manager.get(session_id)
        return SpawnResponse(
            session_id=session_id,
            pid=session.pid,
            command=command,
            sandboxed=(wrapped != command),
        )

    @router.get("/sessions")
    async def list_sessions():
        """List all active terminal sessions."""
        return {"sessions": get_terminal_manager().list_active()}

    @router.post("/sessions/{session_id}/input")
    async def send_input(session_id: str, request: InputRequest):
        """Write to a session's stdin."""
        session = get_terminal_manager().get(session_id)
        if session is None:
            raise HTTPException(404, "Session not found")
        await session.write_stdin(request.data)
        get_terminal_manager().touch(session_id)
        return {"ok": True}

    @router.post("/sessions/{session_id}/resize")
    async def resize_session(session_id: str, request: ResizeRequest):
        """Resize a session's PTY window."""
        session = get_terminal_manager().get(session_id)
        if session is None:
            raise HTTPException(404, "Session not found")
        session.resize(request.cols, request.rows)
        return {"ok": True, "cols": request.cols, "rows": request.rows}

    @router.get("/sessions/{session_id}/stream")
    async def stream_session(session_id: str):
        """SSE stream of a session's stdout until the child exits."""
        session = get_terminal_manager().get(session_id)
        if session is None:
            raise HTTPException(404, "Session not found")

        async def event_gen():
            try:
                async for chunk in session.read_chunk():
                    payload = json.dumps({"type": "stdout",
                                           "data": chunk.decode('utf-8', errors='replace')})
                    yield f"data: {payload}\n\n"
            finally:
                get_terminal_manager().touch(session_id)

            exit_code = session.exit_code if session.exit_code is not None else -1
            yield f"data: {json.dumps({'type': 'exit', 'code': exit_code})}\n\n"

        return StreamingResponse(event_gen(), media_type="text/event-stream")

    @router.delete("/sessions/{session_id}")
    async def kill_session(session_id: str):
        """Kill and remove a session."""
        if not get_terminal_manager().kill(session_id):
            raise HTTPException(404, "Session not found")
        return {"ok": True}

    # ------------------------------------------------------------------
    # Stage endpoint (Plan B: B9)
    # ------------------------------------------------------------------

    @router.post("/sessions/{session_id}/stage")
    async def stage_into_shell(session_id: str, request: StageRequest):
        """Write command text (no newline) to a user PTY at an empty prompt.

        Allowed only when the parser sees the shell at an empty prompt:
        state A/B seen, no C, no bytes typed since B. Otherwise 409.
        """
        manager = get_terminal_manager()
        session = manager.get(session_id)
        if session is None:
            raise HTTPException(404, "Session not found")
        if not manager.is_at_prompt(session_id):
            raise HTTPException(409, "shell busy")
        # Write the command without a newline — the user presses Enter
        await session.write_stdin(request.command)
        manager.touch(session_id)
        return {"ok": True, "staged": request.command}

    # ------------------------------------------------------------------
    # Watched toggle endpoint (Plan B: B8)
    # ------------------------------------------------------------------

    @router.post("/sessions/{session_id}/watched")
    async def set_watched(session_id: str, request: WatchedRequest):
        """Toggle the watched status of a user shell session.

        When unwatched, block closes still store the block row (for xterm
        replay) but do not insert messages rows or hint entries.
        """
        manager = get_terminal_manager()
        session = manager.get(session_id)
        if session is None:
            raise HTTPException(404, "Session not found")
        manager.set_watched(session_id, request.watched)
        # Persist to the terminal_sessions table
        try:
            from halbert_core.agents.threads import get_thread_manager
            store = get_thread_manager().store
            store.update_terminal_session(session_id, watched=1 if request.watched else 0)
        except Exception:
            pass
        return {"ok": True, "watched": request.watched}

    # ------------------------------------------------------------------
    # Existing validation/safety/history endpoints (unchanged behavior)
    # ------------------------------------------------------------------

    @router.post("/validate")
    async def validate_command(request: CommandRequest):
        """
        Validate a command without executing.

        Returns safety check results and dry-run analysis.
        """
        command = request.command.strip()

        is_safe, warning = is_command_safe(command)

        # Parse command
        try:
            parts = shlex.split(command)
            base_command = parts[0] if parts else ""
        except ValueError:
            base_command = command.split()[0] if command.split() else ""

        return {
            "command": command,
            "base_command": base_command,
            "is_safe": is_safe,
            "warning": warning,
            "requires_sudo": uses_elevation(command),
            "is_destructive": any(p in command.lower() for p in ['rm ', 'del ', 'format', 'mkfs']),
        }

    @router.post("/check-safety", response_model=SafetyCheckResponse)
    async def check_safety(request: CommandRequest):
        """
        Phase 13d: Check command safety tier before execution.

        Frontend should call this before executing dangerous commands
        to show appropriate warnings and get user confirmation.
        """
        command = request.command.strip()
        tier, warning, suggestion = check_command_safety(command)

        return SafetyCheckResponse(
            command=command,
            tier=tier.value,
            allowed=tier != SafetyTier.BLOCKED,
            warning=warning,
            requires_confirmation=tier in (SafetyTier.CAUTION, SafetyTier.DANGEROUS),
            suggestion=suggestion,
        )

    # GET /history is gone (Plan B B11, TERM-10). It read
    # ~/.config/halbert/terminal_history.json, which nothing has ever
    # written, so it could only ever answer {"history": [], "total": 0} —
    # and no frontend called it. Command history lives in the
    # terminal_blocks table, and the agent reads it there through the
    # terminal-blocks tool (tools/executor.py).
