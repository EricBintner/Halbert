"""
System tools for LLM function calling (Phase 12d).

These tools allow the LLM to query system state in real-time.
All tools are read-only and safe to execute without user approval.
"""

import subprocess
import shutil
import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

logger = logging.getLogger('cerebric.tools')


@dataclass
class ToolResult:
    """Result from tool execution."""
    success: bool
    data: Any
    error: Optional[str] = None


# Tool definitions for Ollama function calling
SYSTEM_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "check_disk_space",
            "description": "Check disk space usage for a specific path or all mounted filesystems. Use this when the user asks about disk space, storage usage, or if a filesystem is full.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to check (e.g., '/', '/home'). Leave empty for all filesystems."
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_service_status",
            "description": "Get the status of a systemd service. Use this when the user asks if a service is running, or wants to check service health.",
            "parameters": {
                "type": "object",
                "properties": {
                    "service_name": {
                        "type": "string",
                        "description": "Name of the service (e.g., 'docker', 'nginx', 'ssh')"
                    }
                },
                "required": ["service_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_running_services",
            "description": "List all running systemd services. Use this when the user asks what services are running.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filter": {
                        "type": "string",
                        "description": "Optional filter to match service names (e.g., 'docker' to find docker-related services)"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_process",
            "description": "Check if a process is running and get its resource usage. Use this when the user asks about a specific process.",
            "parameters": {
                "type": "object",
                "properties": {
                    "process_name": {
                        "type": "string",
                        "description": "Name of the process to find (e.g., 'python', 'ollama')"
                    }
                },
                "required": ["process_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_system_load",
            "description": "Get current system load average and memory usage. Use this when the user asks about system performance or load.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_log_tail",
            "description": "Read the last N lines from a log file. Use this when the user asks about recent log entries or errors.",
            "parameters": {
                "type": "object",
                "properties": {
                    "log_path": {
                        "type": "string",
                        "description": "Path to log file (e.g., '/var/log/syslog', 'journalctl')"
                    },
                    "lines": {
                        "type": "integer",
                        "description": "Number of lines to read (default: 20, max: 100)"
                    },
                    "filter": {
                        "type": "string",
                        "description": "Optional grep filter for log lines"
                    }
                },
                "required": ["log_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_network_info",
            "description": "Get network interface information and connectivity status. Use this when the user asks about network configuration or connectivity.",
            "parameters": {
                "type": "object",
                "properties": {
                    "interface": {
                        "type": "string",
                        "description": "Specific interface to check (e.g., 'eth0', 'wlan0'). Leave empty for all."
                    }
                },
                "required": []
            }
        }
    },
]


def _run_command(cmd: List[str], timeout: int = 10) -> tuple:
    """Run a command and return (success, stdout, stderr)."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        return result.returncode == 0, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return False, "", "Command timed out"
    except Exception as e:
        return False, "", str(e)


def check_disk_space(path: str = "") -> ToolResult:
    """Check disk space for a path or all filesystems."""
    try:
        if path:
            # Check specific path
            usage = shutil.disk_usage(path)
            total_gb = usage.total / (1024**3)
            used_gb = usage.used / (1024**3)
            free_gb = usage.free / (1024**3)
            percent = (usage.used / usage.total) * 100
            
            return ToolResult(
                success=True,
                data={
                    "path": path,
                    "total_gb": round(total_gb, 2),
                    "used_gb": round(used_gb, 2),
                    "free_gb": round(free_gb, 2),
                    "percent_used": round(percent, 1)
                }
            )
        else:
            # All filesystems via df
            success, stdout, stderr = _run_command(["df", "-h", "--output=target,size,used,avail,pcent"])
            if success:
                lines = stdout.strip().split('\n')
                filesystems = []
                for line in lines[1:]:  # Skip header
                    parts = line.split()
                    if len(parts) >= 5:
                        filesystems.append({
                            "mount": parts[0],
                            "size": parts[1],
                            "used": parts[2],
                            "available": parts[3],
                            "percent": parts[4]
                        })
                return ToolResult(success=True, data={"filesystems": filesystems})
            else:
                return ToolResult(success=False, data=None, error=stderr)
    except Exception as e:
        return ToolResult(success=False, data=None, error=str(e))


def get_service_status(service_name: str) -> ToolResult:
    """Get systemd service status."""
    try:
        success, stdout, stderr = _run_command([
            "systemctl", "show", service_name,
            "--property=ActiveState,SubState,LoadState,MainPID,ExecMainStartTimestamp"
        ])
        
        if success:
            props = {}
            for line in stdout.strip().split('\n'):
                if '=' in line:
                    key, value = line.split('=', 1)
                    props[key] = value
            
            return ToolResult(
                success=True,
                data={
                    "service": service_name,
                    "active": props.get("ActiveState", "unknown"),
                    "sub_state": props.get("SubState", "unknown"),
                    "load_state": props.get("LoadState", "unknown"),
                    "pid": props.get("MainPID", "0"),
                    "started": props.get("ExecMainStartTimestamp", "")
                }
            )
        else:
            return ToolResult(success=False, data=None, error=f"Service not found: {service_name}")
    except Exception as e:
        return ToolResult(success=False, data=None, error=str(e))


def list_running_services(filter: str = "") -> ToolResult:
    """List running systemd services."""
    try:
        cmd = ["systemctl", "list-units", "--type=service", "--state=running", "--no-pager", "--plain"]
        success, stdout, stderr = _run_command(cmd)
        
        if success:
            services = []
            for line in stdout.strip().split('\n')[1:]:  # Skip header
                parts = line.split()
                if len(parts) >= 4:
                    name = parts[0].replace('.service', '')
                    if not filter or filter.lower() in name.lower():
                        services.append({
                            "name": name,
                            "load": parts[1] if len(parts) > 1 else "",
                            "active": parts[2] if len(parts) > 2 else "",
                            "sub": parts[3] if len(parts) > 3 else ""
                        })
            
            return ToolResult(
                success=True,
                data={"count": len(services), "services": services[:30]}  # Limit to 30
            )
        else:
            return ToolResult(success=False, data=None, error=stderr)
    except Exception as e:
        return ToolResult(success=False, data=None, error=str(e))


def check_process(process_name: str) -> ToolResult:
    """Check if a process is running."""
    try:
        success, stdout, stderr = _run_command([
            "ps", "aux"
        ])
        
        if success:
            processes = []
            for line in stdout.strip().split('\n')[1:]:
                if process_name.lower() in line.lower():
                    parts = line.split(None, 10)
                    if len(parts) >= 11:
                        processes.append({
                            "user": parts[0],
                            "pid": parts[1],
                            "cpu": parts[2],
                            "mem": parts[3],
                            "command": parts[10][:80]  # Truncate
                        })
            
            return ToolResult(
                success=True,
                data={
                    "process": process_name,
                    "running": len(processes) > 0,
                    "count": len(processes),
                    "instances": processes[:10]  # Limit to 10
                }
            )
        else:
            return ToolResult(success=False, data=None, error=stderr)
    except Exception as e:
        return ToolResult(success=False, data=None, error=str(e))


def get_system_load() -> ToolResult:
    """Get system load and memory usage."""
    try:
        # Load average
        with open('/proc/loadavg', 'r') as f:
            load_parts = f.read().strip().split()
            load_1, load_5, load_15 = load_parts[0], load_parts[1], load_parts[2]
        
        # Memory
        success, stdout, stderr = _run_command(["free", "-h"])
        mem_info = {}
        if success:
            lines = stdout.strip().split('\n')
            if len(lines) >= 2:
                parts = lines[1].split()
                if len(parts) >= 4:
                    mem_info = {
                        "total": parts[1],
                        "used": parts[2],
                        "free": parts[3],
                        "available": parts[6] if len(parts) > 6 else parts[3]
                    }
        
        # CPU count
        import os
        cpu_count = os.cpu_count() or 1
        
        return ToolResult(
            success=True,
            data={
                "load_1min": float(load_1),
                "load_5min": float(load_5),
                "load_15min": float(load_15),
                "cpu_count": cpu_count,
                "memory": mem_info
            }
        )
    except Exception as e:
        return ToolResult(success=False, data=None, error=str(e))


def read_log_tail(log_path: str, lines: int = 20, filter: str = "") -> ToolResult:
    """Read last N lines from a log file."""
    try:
        lines = min(lines, 100)  # Cap at 100 lines
        
        if log_path == "journalctl" or log_path.startswith("journal"):
            cmd = ["journalctl", "-n", str(lines), "--no-pager"]
            if filter:
                cmd.extend(["--grep", filter])
        else:
            # Validate path (only allow /var/log paths for security)
            if not log_path.startswith('/var/log'):
                return ToolResult(
                    success=False,
                    data=None,
                    error="Only /var/log paths are allowed for security"
                )
            
            if filter:
                cmd = ["sh", "-c", f"tail -n {lines} {log_path} | grep -i '{filter}'"]
            else:
                cmd = ["tail", "-n", str(lines), log_path]
        
        success, stdout, stderr = _run_command(cmd, timeout=5)
        
        if success:
            return ToolResult(
                success=True,
                data={
                    "log": log_path,
                    "lines": stdout.strip().split('\n') if stdout.strip() else []
                }
            )
        else:
            return ToolResult(success=False, data=None, error=stderr or "Failed to read log")
    except Exception as e:
        return ToolResult(success=False, data=None, error=str(e))


def get_network_info(interface: str = "") -> ToolResult:
    """Get network interface information."""
    try:
        if interface:
            cmd = ["ip", "addr", "show", interface]
        else:
            cmd = ["ip", "-brief", "addr", "show"]
        
        success, stdout, stderr = _run_command(cmd)
        
        if success:
            interfaces = []
            if interface:
                # Parse full output for single interface
                interfaces.append({
                    "name": interface,
                    "details": stdout.strip()[:500]  # Limit output
                })
            else:
                # Parse brief output
                for line in stdout.strip().split('\n'):
                    parts = line.split()
                    if len(parts) >= 3:
                        interfaces.append({
                            "name": parts[0],
                            "state": parts[1],
                            "addresses": parts[2:] if len(parts) > 2 else []
                        })
            
            return ToolResult(
                success=True,
                data={"interfaces": interfaces}
            )
        else:
            return ToolResult(success=False, data=None, error=stderr)
    except Exception as e:
        return ToolResult(success=False, data=None, error=str(e))


# Tool execution dispatcher
TOOL_HANDLERS = {
    "check_disk_space": check_disk_space,
    "get_service_status": get_service_status,
    "list_running_services": list_running_services,
    "check_process": check_process,
    "get_system_load": get_system_load,
    "read_log_tail": read_log_tail,
    "get_network_info": get_network_info,
}


def execute_tool(tool_name: str, arguments: Dict[str, Any]) -> ToolResult:
    """Execute a tool by name with given arguments."""
    handler = TOOL_HANDLERS.get(tool_name)
    if not handler:
        return ToolResult(
            success=False,
            data=None,
            error=f"Unknown tool: {tool_name}"
        )
    
    try:
        logger.info(f"Executing tool: {tool_name} with args: {arguments}")
        result = handler(**arguments)
        logger.info(f"Tool {tool_name} result: success={result.success}")
        return result
    except Exception as e:
        logger.error(f"Tool execution failed: {tool_name}: {e}")
        return ToolResult(
            success=False,
            data=None,
            error=str(e)
        )


def get_tool_schemas() -> List[Dict[str, Any]]:
    """Get tool schemas for LLM function calling."""
    return SYSTEM_TOOLS
