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
from typing import Dict, Any, List

logger = logging.getLogger('halbert.tools.system_info')


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
                    proc = await asyncio.create_subprocess_shell(
                        f"ip addr show {iface} | grep 'inet ' | awk '{{print $2}}'",
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    stdout, _ = await proc.communicate()
                    ip = stdout.decode().strip() or "No IP"
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
    limit = args.get("limit", 10)
    
    try:
        if sort_by == "memory":
            cmd = f"ps aux --sort=-%mem | head -n {limit + 1}"
        else:
            cmd = f"ps aux --sort=-%cpu | head -n {limit + 1}"
        
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await proc.communicate()
        
        return f"Top {limit} processes by {sort_by}:\n{stdout.decode()}"
        
    except Exception as e:
        return f"Error getting process list: {e}"


async def get_service_status(args: Dict) -> str:
    """Get systemd service status."""
    service = args.get("service", "")
    
    if not service:
        # List failed services
        try:
            proc = await asyncio.create_subprocess_shell(
                "systemctl list-units --state=failed --no-pager --no-legend",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await proc.communicate()
            output = stdout.decode().strip()
            
            if not output:
                return "No failed services"
            return f"Failed services:\n{output}"
        except Exception as e:
            return f"Error listing services: {e}"
    
    # Get specific service status
    try:
        proc = await asyncio.create_subprocess_shell(
            f"systemctl status {service} --no-pager",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        
        if proc.returncode != 0 and not stdout:
            return f"Service '{service}' not found or error: {stderr.decode()}"
        
        return stdout.decode()
        
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
