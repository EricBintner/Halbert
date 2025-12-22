"""
Terminal API routes.

Provides endpoints for terminal command execution.
Uses subprocess for now - can be upgraded to full PTY later.
"""

from __future__ import annotations
import asyncio
import logging
import subprocess
import shlex
from typing import Optional

try:
    from fastapi import APIRouter, HTTPException
    from pydantic import BaseModel
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    APIRouter = object

logger = logging.getLogger('halbert.dashboard.routes.terminal')

router = APIRouter() if FASTAPI_AVAILABLE else None


class CommandRequest(BaseModel):
    command: str
    cwd: Optional[str] = None
    timeout: int = 30


class CommandResponse(BaseModel):
    output: str
    error: str
    exit_code: int
    command: str


# Blocked commands for safety
BLOCKED_COMMANDS = {
    'rm -rf /',
    'rm -rf /*',
    'dd if=/dev/zero',
    'mkfs',
    ':(){:|:&};:',  # Fork bomb
    '> /dev/sda',
}

# Commands that require approval (future integration)
DANGEROUS_PATTERNS = [
    'rm -rf',
    'dd ',
    'mkfs',
    'format',
    'fdisk',
    'parted',
    'sudo rm',
    'chmod 777',
    'chown -R',
]


def is_command_safe(command: str) -> tuple[bool, str]:
    """Check if command is safe to execute."""
    cmd_lower = command.lower().strip()
    
    # Check blocked commands
    for blocked in BLOCKED_COMMANDS:
        if blocked in cmd_lower:
            return False, f"Blocked command pattern: {blocked}"
    
    # Check dangerous patterns (warn but allow)
    for pattern in DANGEROUS_PATTERNS:
        if pattern in cmd_lower:
            return True, f"Warning: potentially dangerous command ({pattern})"
    
    return True, ""


if FASTAPI_AVAILABLE:
    
    @router.post("/exec", response_model=CommandResponse)
    async def execute_command(request: CommandRequest):
        """
        Execute a shell command.
        
        For MVP, uses subprocess. Full PTY support can be added later.
        """
        command = request.command.strip()
        
        if not command:
            raise HTTPException(400, "Empty command")
        
        # Safety check
        is_safe, warning = is_command_safe(command)
        if not is_safe:
            raise HTTPException(403, warning)
        
        # Handle sudo commands: In web context, pkexec hangs waiting for GUI dialog
        # Instead, run without sudo and let the command fail with a clear message
        # OR suggest copying the command to run in a real terminal
        if command.startswith('sudo '):
            # Try running without sudo first - many read-only commands work
            actual_command = command[5:].strip()
            logger.info(f"Sudo command requested: {actual_command[:50]} - trying without sudo")
            command = actual_command  # Run without sudo, will fail if privileges needed
        
        try:
            # Run command
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=request.cwd,
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=request.timeout
                )
            except asyncio.TimeoutError:
                process.kill()
                return CommandResponse(
                    output="",
                    error=f"Command timed out after {request.timeout}s",
                    exit_code=-1,
                    command=command,
                )
            
            output = stdout.decode('utf-8', errors='replace')
            error = stderr.decode('utf-8', errors='replace')
            
            # Improve error messages for common privilege failures
            if 'Permission denied' in error or 'Operation not permitted' in error:
                error = f"Permission denied. This command requires sudo. Copy and run in terminal:\n\nsudo {request.command[5:].strip() if request.command.startswith('sudo ') else request.command}"
            elif 'sudo: a password is required' in error or 'sudo: a terminal is required' in error:
                error = "This command requires sudo privileges. Run it manually in a terminal where you can enter your password."
            
            # Combine stdout and stderr for display
            combined = output
            if error and process.returncode != 0:
                combined = f"{output}\n{error}" if output else error
            
            logger.info(f"Executed: {command[:50]}... (exit={process.returncode})")
            
            return CommandResponse(
                output=combined.rstrip(),
                error=error.rstrip(),
                exit_code=process.returncode or 0,
                command=command,
            )
            
        except Exception as e:
            logger.error(f"Command execution failed: {e}")
            return CommandResponse(
                output="",
                error=str(e),
                exit_code=-1,
                command=command,
            )
    
    
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
            "requires_sudo": command.strip().startswith('sudo'),
            "is_destructive": any(p in command.lower() for p in ['rm ', 'del ', 'format', 'mkfs']),
        }
    
    
    @router.get("/history")
    async def get_history(limit: int = 50):
        """
        Get command history.
        
        TODO: Implement persistent history storage.
        """
        return {
            "history": [],
            "message": "History not implemented yet",
        }
