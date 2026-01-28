"""
Tool Executor

Executes tools with safety checks, timeouts, and audit logging.
Based on research5.md Part 11.
"""

from __future__ import annotations
import asyncio
import os
import time
import logging
from dataclasses import dataclass
from typing import Dict, Any, Optional, Callable, List, TYPE_CHECKING

from .safety import ToolSafetyFramework, RiskLevel, SafetyCheckResult

if TYPE_CHECKING:
    from .base import BaseTool

logger = logging.getLogger('halbert.tools.executor')


@dataclass
class ExecutionResult:
    """Result of a tool execution."""
    success: bool
    result: Any = None
    error: Optional[str] = None
    execution_time_ms: float = 0.0
    risk_level: RiskLevel = RiskLevel.SAFE
    requires_confirmation: bool = False
    confirmation_message: Optional[str] = None


class ToolExecutor:
    """
    Executes tools with safety checks, timeouts, and logging.
    
    Features:
        - Risk classification before execution
        - Blocking of CRITICAL operations
        - Confirmation required for HIGH risk
        - Timeout handling
        - Audit logging
    """
    
    DEFAULT_TIMEOUT = 30  # seconds
    
    def __init__(
        self,
        safety: ToolSafetyFramework = None,
        audit_fn: Callable = None,
    ):
        """
        Initialize the tool executor.
        
        Args:
            safety: Safety framework for risk classification
            audit_fn: Optional function to call for audit logging
        """
        self.safety = safety or ToolSafetyFramework()
        self.audit_fn = audit_fn
        
        # Registered tools
        self.tools: Dict[str, Callable] = {}
        self.schemas: Dict[str, Dict] = {}
        
        # Register built-in tools
        self._register_builtins()
    
    def _register_builtins(self):
        """Register built-in tool handlers."""
        self.register(
            "run_command",
            self._run_command,
            {
                "name": "run_command",
                "description": "Execute a shell command on the system",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": "The shell command to execute"
                        },
                        "timeout": {
                            "type": "integer",
                            "description": "Timeout in seconds (default: 30)"
                        },
                        "cwd": {
                            "type": "string",
                            "description": "Working directory for the command"
                        }
                    },
                    "required": ["command"]
                }
            }
        )
        
        self.register(
            "web_search",
            self._web_search,
            {
                "name": "web_search",
                "description": "Search the web for current information not in training data",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query"
                        },
                        "num_results": {
                            "type": "integer",
                            "description": "Number of results (1-10)",
                            "default": 5
                        }
                    },
                    "required": ["query"]
                }
            }
        )
        
        self.register(
            "read_file",
            self._read_file,
            {
                "name": "read_file",
                "description": "Read the contents of a file",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Path to the file to read"
                        },
                        "encoding": {
                            "type": "string",
                            "description": "File encoding (default: utf-8)"
                        }
                    },
                    "required": ["path"]
                }
            }
        )
        
        self.register(
            "write_file",
            self._write_file,
            {
                "name": "write_file",
                "description": "Write content to a file",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Path to the file to write"
                        },
                        "content": {
                            "type": "string",
                            "description": "Content to write"
                        },
                        "append": {
                            "type": "boolean",
                            "description": "Append instead of overwrite"
                        }
                    },
                    "required": ["path", "content"]
                }
            }
        )
        
        self.register(
            "list_directory",
            self._list_directory,
            {
                "name": "list_directory",
                "description": "List contents of a directory",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Path to the directory"
                        }
                    },
                    "required": ["path"]
                }
            }
        )
    
    def register(self, name: str, handler: Callable, schema: Dict):
        """
        Register a tool.
        
        Args:
            name: Tool name
            handler: Async function to execute the tool
            schema: Tool schema for LLM
        """
        self.tools[name] = handler
        self.schemas[name] = schema
        logger.debug(f"Registered tool: {name}")
    
    def get_schemas(self) -> List[Dict]:
        """Get all tool schemas for LLM."""
        return [
            {"type": "function", "function": schema}
            for schema in self.schemas.values()
        ]
    
    async def execute(
        self,
        tool_name: str,
        args: Dict[str, Any],
        session_id: str = None,
        confirmed: bool = False,
    ) -> ExecutionResult:
        """
        Execute a tool with safety checks.
        
        Args:
            tool_name: Name of the tool to execute
            args: Tool arguments
            session_id: Optional session ID for audit
            confirmed: Whether user has confirmed (for HIGH risk)
            
        Returns:
            ExecutionResult with success status and result/error
        """
        start = time.time()
        
        # Check if tool exists
        if tool_name not in self.tools:
            return ExecutionResult(
                success=False,
                error=f"Unknown tool: {tool_name}",
                execution_time_ms=0
            )
        
        # Classify risk
        safety_result = self.safety.classify(tool_name, args)
        
        # Block CRITICAL
        if safety_result.risk_level == RiskLevel.CRITICAL:
            logger.warning(f"BLOCKED critical operation: {tool_name} {args}")
            self._audit(
                tool_name, args, session_id,
                success=False, error="Blocked: critical risk"
            )
            return ExecutionResult(
                success=False,
                error=f"Operation blocked for safety: {safety_result.reason}",
                risk_level=safety_result.risk_level
            )
        
        # Require confirmation for HIGH risk
        if safety_result.risk_level == RiskLevel.HIGH and not confirmed:
            logger.info(f"HIGH risk operation requires confirmation: {tool_name}")
            return ExecutionResult(
                success=False,
                risk_level=safety_result.risk_level,
                requires_confirmation=True,
                confirmation_message=self.safety.get_confirmation_message(
                    tool_name, args, safety_result
                )
            )
        
        # Execute the tool
        try:
            handler = self.tools[tool_name]
            
            # Handle both sync and async handlers
            if asyncio.iscoroutinefunction(handler):
                result = await handler(args)
            else:
                result = handler(args)
            
            elapsed = (time.time() - start) * 1000
            
            logger.info(f"Executed {tool_name}: success in {elapsed:.0f}ms")
            self._audit(tool_name, args, session_id, success=True)
            
            return ExecutionResult(
                success=True,
                result=result,
                execution_time_ms=elapsed,
                risk_level=safety_result.risk_level
            )
            
        except asyncio.TimeoutError:
            elapsed = (time.time() - start) * 1000
            logger.error(f"Tool timeout: {tool_name}")
            self._audit(tool_name, args, session_id, success=False, error="Timeout")
            return ExecutionResult(
                success=False,
                error="Operation timed out",
                execution_time_ms=elapsed,
                risk_level=safety_result.risk_level
            )
            
        except Exception as e:
            elapsed = (time.time() - start) * 1000
            logger.error(f"Tool execution error: {tool_name}: {e}")
            self._audit(tool_name, args, session_id, success=False, error=str(e))
            return ExecutionResult(
                success=False,
                error=str(e),
                execution_time_ms=elapsed,
                risk_level=safety_result.risk_level
            )
    
    def _audit(
        self,
        tool_name: str,
        args: Dict,
        session_id: str = None,
        success: bool = True,
        error: str = None
    ):
        """Log tool execution for audit."""
        if self.audit_fn:
            try:
                self.audit_fn(
                    tool=tool_name,
                    args=args,
                    session_id=session_id,
                    success=success,
                    error=error
                )
            except Exception as e:
                logger.error(f"Audit logging failed: {e}")
    
    # -------------------------------------------------------------------------
    # Built-in Tool Implementations
    # -------------------------------------------------------------------------
    
    async def _run_command(self, args: Dict) -> str:
        """Execute a shell command."""
        command = args["command"]
        timeout = args.get("timeout", self.DEFAULT_TIMEOUT)
        cwd = args.get("cwd")
        
        # Expand user paths
        if cwd:
            cwd = os.path.expanduser(cwd)
        
        logger.debug(f"Running command: {command}")
        
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd
        )
        
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout
            )
            
            output = stdout.decode('utf-8', errors='replace') if stdout else ""
            errors = stderr.decode('utf-8', errors='replace') if stderr else ""
            
            if proc.returncode != 0:
                return f"Exit code {proc.returncode}\n{output}\n{errors}".strip()
            
            return output.strip() if output else "(no output)"
            
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise
    
    async def _read_file(self, args: Dict) -> str:
        """Read file contents."""
        path = args["path"]
        encoding = args.get("encoding", "utf-8")
        
        # Security: expand and normalize path
        path = os.path.expanduser(path)
        path = os.path.abspath(path)
        
        if not os.path.exists(path):
            raise FileNotFoundError(f"File not found: {path}")
        
        if not os.path.isfile(path):
            raise ValueError(f"Not a file: {path}")
        
        # Check file size (limit to 1MB)
        size = os.path.getsize(path)
        if size > 1024 * 1024:
            raise ValueError(f"File too large: {size} bytes (max 1MB)")
        
        with open(path, 'r', encoding=encoding) as f:
            return f.read()
    
    async def _write_file(self, args: Dict) -> str:
        """Write content to a file."""
        path = args["path"]
        content = args["content"]
        append = args.get("append", False)
        
        # Security: expand and normalize path
        path = os.path.expanduser(path)
        path = os.path.abspath(path)
        
        # Create parent directories if needed
        parent = os.path.dirname(path)
        if parent and not os.path.exists(parent):
            os.makedirs(parent, exist_ok=True)
        
        mode = 'a' if append else 'w'
        with open(path, mode, encoding='utf-8') as f:
            f.write(content)
        
        return f"Written {len(content)} bytes to {path}"
    
    async def _list_directory(self, args: Dict) -> str:
        """List directory contents."""
        path = args["path"]
        
        # Security: expand and normalize path
        path = os.path.expanduser(path)
        path = os.path.abspath(path)
        
        if not os.path.exists(path):
            raise FileNotFoundError(f"Directory not found: {path}")
        
        if not os.path.isdir(path):
            raise ValueError(f"Not a directory: {path}")
        
        entries = []
        for entry in os.listdir(path):
            full_path = os.path.join(path, entry)
            if os.path.isdir(full_path):
                entries.append(f"[DIR]  {entry}/")
            else:
                size = os.path.getsize(full_path)
                entries.append(f"[FILE] {entry} ({size} bytes)")
        
        return "\n".join(sorted(entries)) if entries else "(empty directory)"
    
    async def _web_search(self, args: Dict) -> str:
        """Perform web search."""
        from .web_search import handle_web_search
        return await handle_web_search(args)
    
    def register_system_tools(self):
        """Register system information tools."""
        from .system_info import SYSTEM_TOOL_SCHEMAS, SYSTEM_TOOL_HANDLERS
        
        for name, schema in SYSTEM_TOOL_SCHEMAS.items():
            handler = SYSTEM_TOOL_HANDLERS.get(name)
            if handler:
                self.register(name, handler, schema)
