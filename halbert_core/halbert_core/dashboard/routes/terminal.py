"""
Terminal API routes.

Provides endpoints for terminal command execution.
Uses subprocess for now - can be upgraded to full PTY later.

Phase 13d: Integrated with ToolSafetyFramework for tiered safety checks.
"""

from __future__ import annotations
import asyncio
import logging
import subprocess
import shlex
from typing import Optional
from enum import Enum

try:
    from fastapi import APIRouter, HTTPException
    from pydantic import BaseModel
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    APIRouter = object

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
        import json
        
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
