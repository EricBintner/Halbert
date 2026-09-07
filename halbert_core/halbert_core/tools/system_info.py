# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
System Information Tools

Provides system monitoring tools for the agent.
"""

from __future__ import annotations
import asyncio
import os
import logging
import re
from typing import Dict, Any, List

logger = logging.getLogger('halbert.tools.system_info')


#: A systemd unit name, as strictly as systemd itself will accept one. Anchored,
#: and deliberately excluding a leading '-' so a unit name can never be read as
#: an option by the binary we hand it to.
_UNIT_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9:_.@-]{0,255}$")


async def _run(*argv: str, timeout: float = 15.0) -> tuple[int, str, str]:
    """Run a command as an argv list and return (returncode, stdout, stderr).

    SEC-2: every call site in this module used ``create_subprocess_shell`` with an
    f-string. One of them interpolated a *model-supplied* service name
    (``get_service_status``), so a tool call was a shell. There is no argument for
    a shell here — none of these commands need globbing, pipes or expansion that
    Python cannot do itself — so the shell is gone rather than escaped. Escaping
    is a thing you get wrong once.
    """
    proc = await asyncio.create_subprocess_exec(
        *argv,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise
    return proc.returncode or 0, out.decode(errors="replace"), err.decode(errors="replace")


async def get_disk_usage(args: Dict) -> str:
    """Get disk usage information."""
    path = args.get("path", "/")
    
    try:
        import shutil
        total, used, free = shutil.disk_usage(path)
        
        def format_size(bytes_val):
            for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
                if bytes_val < 1024:
                    return f"{bytes_val:.1f} {unit}"
                bytes_val /= 1024
            return f"{bytes_val:.1f} PB"
        
        percent = (used / total) * 100
        
        return f"""Disk Usage for {path}:
  Total: {format_size(total)}
  Used:  {format_size(used)} ({percent:.1f}%)
  Free:  {format_size(free)}"""
        
    except Exception as e:
        return f"Error getting disk usage: {e}"


async def get_memory_info(args: Dict) -> str:
    """Get memory usage information."""
    try:
        with open('/proc/meminfo', 'r') as f:
            meminfo = {}
            for line in f:
                parts = line.split(':')
                if len(parts) == 2:
                    key = parts[0].strip()
                    value = parts[1].strip().split()[0]
                    meminfo[key] = int(value) * 1024  # Convert to bytes
        
        total = meminfo.get('MemTotal', 0)
        free = meminfo.get('MemFree', 0)
        available = meminfo.get('MemAvailable', 0)
        buffers = meminfo.get('Buffers', 0)
        cached = meminfo.get('Cached', 0)
        
        used = total - available
        percent = (used / total) * 100 if total > 0 else 0
        
        def format_size(bytes_val):
            return f"{bytes_val / (1024**3):.1f} GB"
        
        return f"""Memory Usage:
  Total:     {format_size(total)}
  Used:      {format_size(used)} ({percent:.1f}%)
  Available: {format_size(available)}
  Buffers:   {format_size(buffers)}
  Cached:    {format_size(cached)}"""
        
    except Exception as e:
        return f"Error getting memory info: {e}"


async def get_cpu_info(args: Dict) -> str:
    """Get CPU information and load."""
    try:
        # Get CPU model
        cpu_model = "Unknown"
        try:
            with open('/proc/cpuinfo', 'r') as f:
                for line in f:
                    if 'model name' in line:
                        cpu_model = line.split(':')[1].strip()
                        break
        except:
            pass
        
        # Get load average
        load1, load5, load15 = os.getloadavg()
        
        # Get CPU count
        cpu_count = os.cpu_count() or 1
        
        # Get uptime
        uptime = "Unknown"
        try:
            with open('/proc/uptime', 'r') as f:
                seconds = float(f.read().split()[0])
                days = int(seconds // 86400)
                hours = int((seconds % 86400) // 3600)
                minutes = int((seconds % 3600) // 60)
                uptime = f"{days}d {hours}h {minutes}m"
        except:
            pass
        
        return f"""CPU Information:
  Model:  {cpu_model}
  Cores:  {cpu_count}
  Load:   {load1:.2f} (1m) / {load5:.2f} (5m) / {load15:.2f} (15m)
  Uptime: {uptime}"""
        
    except Exception as e:
        return f"Error getting CPU info: {e}"


async def get_network_info(args: Dict) -> str:
    """Get network interface information."""
    try:
        interfaces = []
        
        # Read network interfaces
        net_path = '/sys/class/net'
        if os.path.exists(net_path):
            for iface in os.listdir(net_path):
                if iface == 'lo':
                    continue
                
                # Get IP address
                ip = "No IP"
                try:
                    _rc, out, _err = await _run("ip", "addr", "show", iface)
                    # The grep|awk pipeline this replaces existed only to pull
                    # the inet field out; Python can do that without a shell.
                    addrs = [
                        parts[1]
                        for parts in (line.split() for line in out.splitlines())
                        if len(parts) > 1 and parts[0] == "inet"
                    ]
                    ip = " ".join(addrs) or "No IP"
                except:
                    pass
                
                # Get state
                state = "unknown"
                try:
                    with open(f'{net_path}/{iface}/operstate', 'r') as f:
                        state = f.read().strip()
                except:
                    pass
                
                interfaces.append(f"  {iface}: {state} - {ip}")
        
        if not interfaces:
            return "No network interfaces found"
        
        return "Network Interfaces:\n" + "\n".join(interfaces)
        
    except Exception as e:
        return f"Error getting network info: {e}"


async def get_process_list(args: Dict) -> str:
    """Get running processes sorted by CPU or memory."""
    sort_by = args.get("sort", "cpu")  # cpu or memory
    # The model supplies `limit`, and it reached an f-string. Coerce and bound it
    # rather than trusting the type: `head -n <whatever the model said>` is not a
    # thing to find out about later.
    try:
        limit = max(1, min(int(args.get("limit", 10)), 200))
    except (TypeError, ValueError):
        limit = 10

    try:
        sort_key = "-%mem" if sort_by == "memory" else "-%cpu"
        _rc, out, _err = await _run("ps", "aux", f"--sort={sort_key}")
        # `| head -n N` in Python, so there is no pipeline and so no shell.
        lines = out.splitlines()
        trimmed = "\n".join(lines[: limit + 1])

        return f"Top {limit} processes by {sort_by}:\n{trimmed}"
        
    except Exception as e:
        return f"Error getting process list: {e}"


async def get_service_status(args: Dict) -> str:
    """Get systemd service status."""
    service = args.get("service", "")
    
    if not service:
        # List failed services
        try:
            _rc, out, _err = await _run(
                "systemctl", "list-units", "--state=failed", "--no-pager", "--no-legend"
            )
            output = out.strip()
            
            if not output:
                return "No failed services"
            return f"Failed services:\n{output}"
        except Exception as e:
            return f"Error listing services: {e}"
    
    # Get specific service status.
    #
    # SEC-2 (F5/F15): this was f"systemctl status {service} --no-pager" through a
    # shell, with `service` supplied by the model — so any text that reached the
    # model and produced this tool call was arbitrary command execution. It was
    # also never seen by the command classifier, which only inspects run_command.
    if not _UNIT_NAME.match(service):
        return (
            f"'{service}' is not a unit name I will pass to systemctl. "
            f"Unit names start with a letter or digit and contain only "
            f"letters, digits and . _ - : @"
        )
    try:
        rc, out, err = await _run("systemctl", "status", service, "--no-pager")

        if rc != 0 and not out:
            return f"Service '{service}' not found or error: {err}"

        return out
        
    except Exception as e:
        return f"Error getting service status: {e}"


# Tool schemas for registration
SYSTEM_TOOL_SCHEMAS = {
    "get_disk_usage": {
        "name": "get_disk_usage",
        "description": "Get disk usage information for a path",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to check (default: /)",
                    "default": "/"
                }
            }
        }
    },
    "get_memory_info": {
        "name": "get_memory_info",
        "description": "Get system memory usage information",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    },
    "get_cpu_info": {
        "name": "get_cpu_info",
        "description": "Get CPU information and load averages",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    },
    "get_network_info": {
        "name": "get_network_info",
        "description": "Get network interface information",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    },
    "get_process_list": {
        "name": "get_process_list",
        "description": "Get top processes by CPU or memory usage",
        "parameters": {
            "type": "object",
            "properties": {
                "sort": {
                    "type": "string",
                    "enum": ["cpu", "memory"],
                    "description": "Sort by CPU or memory",
                    "default": "cpu"
                },
                "limit": {
                    "type": "integer",
                    "description": "Number of processes to show",
                    "default": 10
                }
            }
        }
    },
    "get_service_status": {
        "name": "get_service_status",
        "description": "Get systemd service status. Without service name, lists failed services.",
        "parameters": {
            "type": "object",
            "properties": {
                "service": {
                    "type": "string",
                    "description": "Service name (optional)"
                }
            }
        }
    }
}

# Handler mapping
SYSTEM_TOOL_HANDLERS = {
    "get_disk_usage": get_disk_usage,
    "get_memory_info": get_memory_info,
    "get_cpu_info": get_cpu_info,
    "get_network_info": get_network_info,
    "get_process_list": get_process_list,
    "get_service_status": get_service_status,
}
