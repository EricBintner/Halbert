# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
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
import uuid
from dataclasses import dataclass
from typing import Dict, Any, Optional, Callable, List, TYPE_CHECKING

from .safety import ToolSafetyFramework, RiskLevel, SafetyCheckResult, THREAD_META_TOOLS
from ..streaming.terminal_bridge import (
    current_agent_session, publish_terminal_event, terminal_stream_wanted,
    terminal_pool_wanted,
)

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

        # Plan B: terminal_blocks fetch tool (B11)
        self.register(
            "terminal_blocks",
            self._terminal_blocks,
            {
                "name": "terminal_blocks",
                "description": "Fetch stored terminal block output",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "session_id": {
                            "type": "string",
                            "description": "Terminal session id",
                        },
                        "n": {
                            "type": "integer",
                            "description": "Number of recent blocks (default 5)",
                            "default": 5,
                        },
                    },
                },
            },
        )

        # Thread meta-tools (Plan A, spec §7). The schemas are what the model
        # sees; PLANNING handles the calls inline and never dispatches them
        # here, so the handler is a stub (see execute()). Descriptions stay
        # under 60 characters on purpose.
        self.register(
            "new_thread",
            self._meta_tool_inline,
            {
                "name": "new_thread",
                "description": "Start a new subject; pauses the current one",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "Short title for the new subject"},
                        "reason": {"type": "string", "description": "Why the subject changed"},
                    },
                    "required": ["title", "reason"],
                },
            },
        )
        self.register(
            "recall_thread",
            self._meta_tool_inline,
            {
                "name": "recall_thread",
                "description": "Find earlier subjects by query or thread id",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Words to search earlier subjects for"},
                        "thread_id": {"type": "string", "description": "A specific earlier thread id"},
                    },
                    "required": [],
                },
            },
        )
        self.register(
            "resume_thread",
            self._meta_tool_inline,
            {
                "name": "resume_thread",
                "description": "Return to a paused earlier subject",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "thread_id": {"type": "string", "description": "The paused thread to reopen"},
                    },
                    "required": ["thread_id"],
                },
            },
        )

    async def _meta_tool_inline(self, args: Dict) -> str:
        """Stub for the thread meta-tools; the state machine handles them."""
        return "handled inline"

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

        # Thread meta-tools never run here: PLANNING handles them inline
        # (spec §7). Reaching this branch means a caller bypassed PLANNING;
        # answer as a side-effect-free success with no audit entry.
        if tool_name in THREAD_META_TOOLS:
            logger.warning(
                f"{tool_name} reached the executor; PLANNING should have handled it inline"
            )
            return ExecutionResult(
                success=True,
                result="handled inline",
                execution_time_ms=0,
                risk_level=RiskLevel.SAFE,
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
        #
        # The agent session id rides in a ContextVar rather than a handler
        # parameter: handlers take only their args dict, and threading an extra
        # argument would break every registered tool. Anything running under
        # the handler (notably _run_command) can therefore publish terminal
        # lifecycle events to the right SSE stream. See streaming/terminal_bridge.
        session_token = current_agent_session.set(session_id)
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

        finally:
            current_agent_session.reset(session_token)

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
        """Execute a shell command.

        When an agent turn is streaming (``terminal_stream_wanted()``), the
        command's output is also published chunk-by-chunk to the terminal event
        bridge so the conversation can render a live terminal tile while the
        command is still running. The return value — what the model sees — is
        identical either way.

        Plan B: when streaming, the pool path is tried first. The pool runs
        the command in a PTY-backed bash session with OSC 133 block markers,
        producing a terminal_block row. At cap or on failure, falls back to
        the subprocess path.
        """
        command = args["command"]
        timeout = args.get("timeout", self.DEFAULT_TIMEOUT)
        cwd = args.get("cwd")
        # background is accepted but ignored (Plan C).

        # Expand user paths
        if cwd:
            cwd = os.path.expanduser(cwd)

        logger.debug(f"Running command: {command}")

        streaming = terminal_stream_wanted()
        pool_wanted = terminal_pool_wanted()

        # Plan B: try the pool first (only when streaming + pool enabled)
        if pool_wanted:
            try:
                from halbert_core.streaming.agent_pool import get_terminal_pool
                pool = get_terminal_pool()
                result = await pool.run_block(command, cwd=cwd, timeout=timeout)
                if result is not None:
                    # Store the terminal_block row
                    try:
                        from halbert_core.agents.threads import get_thread_manager
                        store = get_thread_manager().store
                        store.insert_terminal_block({
                            "block_id": result["block_id"],
                            "session_id": result["session_id"],
                            "thread_id": None,
                            "turn_id": None,
                            "command": command,
                            "cwd": cwd,
                            "owner": "agent",
                            "interactive": 0,
                            "remote": 0,
                            "redacted": 1 if result.get("redacted") else 0,
                            "started_at": result.get("started_at", 0.0),
                            "ended_at": result.get("ended_at", 0.0),
                            "exit_code": result["exit_code"],
                            "output_head": result["output_head"],
                            "output_tail": result["output_tail"],
                        })
                    except Exception as e:
                        logger.warning(f"Failed to store terminal_block: {e}")
                    return self._format_block_result(result)
            except Exception as e:
                logger.warning(f"Pool path failed, falling back to subprocess: {e}")

        # Fallback: subprocess path (unchanged)
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd
        )

        terminal_id = f"cmd-{uuid.uuid4()}"
        if streaming:
            publish_terminal_event({
                "kind": "spawn",
                "terminal_session_id": terminal_id,
                "command": command,
                "pid": proc.pid,
                "cwd": cwd,
                "sandboxed": False,
                "attach": "sse",
            })

        out_buf: List[str] = []
        err_buf: List[str] = []

        async def pump(stream, buf: List[str]) -> None:
            """Drain one pipe, buffering it and (optionally) streaming it."""
            while True:
                chunk = await stream.read(4096)
                if not chunk:
                    return
                text = chunk.decode('utf-8', errors='replace')
                buf.append(text)
                if streaming:
                    publish_terminal_event({
                        "kind": "output",
                        "terminal_session_id": terminal_id,
                        "data": text,
                    })

        pumps = asyncio.gather(
            pump(proc.stdout, out_buf),
            pump(proc.stderr, err_buf),
        )

        async def drain_and_wait() -> int:
            """Drain both pipes, then reap the child."""
            await pumps
            return await proc.wait()

        try:
            # One deadline covers draining *and* exit. EOF on the pipes is not
            # the same event as the child exiting: a process that closes or
            # redirects its std fds and keeps running (`exec 1>&- 2>&-; sleep`,
            # a daemonising helper) reaches EOF immediately. Timing only the
            # drain would let such a command outlive its timeout entirely —
            # the proc.communicate() this replaced bounded exit for free.
            returncode = await asyncio.wait_for(drain_and_wait(), timeout=timeout)

            output = "".join(out_buf)
            errors = "".join(err_buf)

            if streaming:
                publish_terminal_event({
                    "kind": "complete",
                    "terminal_session_id": terminal_id,
                    "exit_code": returncode,
                })

            if returncode != 0:
                return f"Exit code {returncode}\n{output}\n{errors}".strip()

            return output.strip() if output else "(no output)"

        except BaseException:
            # Timeout (wait_for cancelled the pumps) or an unexpected reader
            # failure. Either way the child must not outlive the tool call.
            pumps.cancel()
            if proc.returncode is None:
                proc.kill()
                await proc.wait()
            if streaming:
                publish_terminal_event({
                    "kind": "complete",
                    "terminal_session_id": terminal_id,
                    "exit_code": proc.returncode if proc.returncode is not None else -1,
                })
            raise

    @staticmethod
    def _format_block_result(result: Dict) -> str:
        """Format a pool block result for the model.

        Returns the same string shape the model sees from the subprocess
        path: exit code + output, or just output on success.
        """
        exit_code = result.get("exit_code", -1)
        output = result.get("output_head", "")
        tail = result.get("output_tail", "")
        # Combine head and tail (head is first 20 lines, tail is last 4 KiB)
        full_output = output
        if tail and tail != output:
            full_output = output + "\n" + tail
        if exit_code != 0:
            return f"Exit code {exit_code}\n{full_output}".strip()
        return full_output.strip() if full_output else "(no output)"

    async def _terminal_blocks(self, args: Dict) -> str:
        """Fetch stored terminal block output (Plan B: B11).

        Returns a JSON string listing recent terminal blocks for a session.
        SAFE risk level — read-only.
        """
        session_id = args.get("session_id")
        n = args.get("n", 5)
        try:
            from halbert_core.agents.threads import get_thread_manager
            store = get_thread_manager().store
            blocks = store.list_terminal_blocks(
                session_id=session_id,
                limit=n,
            ) if session_id else store.list_terminal_blocks(limit=n)
            # Trim to the fields the model needs
            result = [
                {
                    "block_id": b.get("block_id"),
                    "command": b.get("command"),
                    "exit_code": b.get("exit_code"),
                    "cwd": b.get("cwd"),
                    "output_head": b.get("output_head", ""),
                    "output_tail": b.get("output_tail", ""),
                    "started_at": b.get("started_at"),
                    "ended_at": b.get("ended_at"),
                }
                for b in blocks
            ]
            import json
            return json.dumps(result, indent=2, default=str)
        except Exception as e:
            logger.warning(f"terminal_blocks tool failed: {e}")
            return "[]"

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

    def register_vision_tools(self):
        """Register vision capture tools (screen, webcam).

        Vision tool handlers return a dict with an "image" key (base64
        JPEG). The state machine detects this and appends the image to
        ctx.images, routing the next LLM call through the vision model.
        """
        from .vision_tools import VISION_TOOL_SCHEMAS, VISION_TOOL_HANDLERS

        for name, schema in VISION_TOOL_SCHEMAS.items():
            handler = VISION_TOOL_HANDLERS.get(name)
            if handler:
                self.register(name, handler, schema)
            else:
                logger.warning(f"Vision tool '{name}' has schema but no handler — skipped")
