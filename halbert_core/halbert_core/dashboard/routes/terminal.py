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
from typing import Optional, List
from enum import Enum

try:
    from fastapi import APIRouter, HTTPException
    from fastapi.responses import StreamingResponse
    from pydantic import BaseModel
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    APIRouter = object
    StreamingResponse = None  # type: ignore

from ...streaming.session_manager import (
    get_terminal_manager, AtCapacityError,
)
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
    timeout: int = 30
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
        output = bytearray()

        async def drain():
            async for chunk in session.read_chunk():
                output.extend(chunk)

        try:
            await asyncio.wait_for(drain(), timeout=request.timeout)
        except asyncio.TimeoutError:
            manager.kill(session_id)
            return CommandResponse(
                output=bytes(output).decode('utf-8', errors='replace'),
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
            output=bytes(output).decode('utf-8', errors='replace'),
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

    @router.get("/history")
    async def get_history(limit: int = 50):
        """
        Get command history from persistent storage.
        """
        from pathlib import Path

        history_file = Path.home() / '.config' / 'halbert' / 'terminal_history.json'

        if not history_file.exists():
            return {"history": [], "total": 0}

        try:
            with open(history_file) as f:
                all_history = json.load(f)
            return {
                "history": all_history[-limit:],
                "total": len(all_history),
            }
        except Exception:
            return {"history": [], "total": 0}