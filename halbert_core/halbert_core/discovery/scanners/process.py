# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Process Scanner - Discover resource-consuming processes.

Enables scenarios:
- S1.2: "Why am I slow?" → Top CPU/RAM consumers
- S1.6: "What's eating resources?" → Resource hogs
- S10.6: "System hang" → Blocked/zombie processes
- S11.2: "Performance degradation" → Memory growth trends

Discovers:
- Top processes by CPU, RAM, I/O
- Zombie and blocked processes
- Process → parent relationships
- Memory growth trends (when run periodically)
"""

from __future__ import annotations
from typing import List, Dict, Optional
from dataclasses import dataclass
from datetime import datetime

from .base import BaseScanner
from ..schema import (
    Discovery,
    DiscoveryType,
    DiscoverySeverity,
    DiscoveryAction,
    make_discovery_id,
)


@dataclass
class ProcessInfo:
    """Information about a process."""
    pid: int
    name: str
    user: str
    cpu_percent: float
    mem_percent: float
    mem_mb: float
    state: str  # R=running, S=sleeping, D=uninterruptible, Z=zombie, T=stopped
    parent_pid: int
    command: str
    threads: int = 1
    io_read_mb: float = 0.0
    io_write_mb: float = 0.0


class ProcessScanner(BaseScanner):
    """
    Scanner for processes and resource usage.
    
    Discovers:
    - Resource hog processes (high CPU/RAM)
    - Problem processes (zombie, blocked)
    - System resource summary
    """
    
    @property
    def discovery_type(self) -> DiscoveryType:
        return DiscoveryType.PROCESS
    
    def scan(self) -> List[Discovery]:
        """Scan system for processes."""
        discoveries = []
        
        # Get all processes
        processes = self._get_all_processes()
        
        # Create discoveries for resource hogs
        discoveries.extend(self._discover_resource_hogs(processes))
        
        # Create discoveries for problem processes
        discoveries.extend(self._discover_problem_processes(processes))
        
        # Create system summary
        discoveries.append(self._create_system_summary(processes))
        
        self.logger.info(f"Found {len(discoveries)} process discoveries")
        return discoveries
    
    def _get_all_processes(self) -> List[ProcessInfo]:
        """Get all process information using ps."""
        processes = []
        
        # Get process info: pid, user, %cpu, %mem, rss, stat, ppid, comm, args
        code, stdout, _ = self.run_command([
            "ps", "aux", "--no-headers", "-o", 
            "pid,user,%cpu,%mem,rss,stat,ppid,comm,args"
        ])
        
        if code != 0:
            return processes
        
        for line in stdout.strip().splitlines():
            parts = line.split(None, 8)  # Split into max 9 parts
            if len(parts) < 8:
                continue
            
            try:
                pid = int(parts[0])
                user = parts[1]
                cpu_percent = float(parts[2])
                mem_percent = float(parts[3])
                rss_kb = int(parts[4])
                state = parts[5][0] if parts[5] else 'S'  # First char of stat
                ppid = int(parts[6])
                comm = parts[7]
                args = parts[8] if len(parts) > 8 else comm
                
                processes.append(ProcessInfo(
                    pid=pid,
                    name=comm,
                    user=user,
                    cpu_percent=cpu_percent,
                    mem_percent=mem_percent,
                    mem_mb=rss_kb / 1024.0,
                    state=state,
                    parent_pid=ppid,
                    command=args[:200],  # Truncate long commands
                ))
            except (ValueError, IndexError):
                continue
        
        return processes
    
    def _discover_resource_hogs(self, processes: List[ProcessInfo]) -> List[Discovery]:
        """Find processes using excessive resources."""
        discoveries = []
        
        # Sort by CPU and get top consumers
        cpu_hogs = sorted(processes, key=lambda p: p.cpu_percent, reverse=True)[:5]
        # Sort by memory and get top consumers
        mem_hogs = sorted(processes, key=lambda p: p.mem_mb, reverse=True)[:5]
        
        # Combine and dedupe
        seen_pids = set()
        hogs = []
        for p in cpu_hogs + mem_hogs:
            if p.pid not in seen_pids and (p.cpu_percent > 5.0 or p.mem_mb > 500):
                seen_pids.add(p.pid)
                hogs.append(p)
        
        for proc in hogs[:10]:  # Limit to top 10
            # Determine severity
            if proc.cpu_percent > 80 or proc.mem_mb > 4000:
                severity = DiscoverySeverity.WARNING
            else:
                severity = DiscoverySeverity.INFO
            
            discovery_id = make_discovery_id(DiscoveryType.PROCESS, f"hog-{proc.pid}")
            
            discoveries.append(Discovery(
                id=discovery_id,
                type=DiscoveryType.PROCESS,
                name=f"hog-{proc.pid}",
                title=f"{proc.name} (PID {proc.pid})",
                description=f"Using {proc.cpu_percent:.1f}% CPU, {proc.mem_mb:.0f}MB RAM",
                icon="activity",
                severity=severity,
                status=f"CPU: {proc.cpu_percent:.1f}%, RAM: {proc.mem_mb:.0f}MB",
                status_detail=f"User: {proc.user}",
                source=f"/proc/{proc.pid}",
                data={
                    "pid": proc.pid,
                    "name": proc.name,
                    "user": proc.user,
                    "cpu_percent": proc.cpu_percent,
                    "mem_percent": proc.mem_percent,
                    "mem_mb": proc.mem_mb,
                    "state": proc.state,
                    "parent_pid": proc.parent_pid,
                    "command": proc.command,
                    "is_resource_hog": True,
                },
                actions=[
                    DiscoveryAction(
                        id="kill",
                        label="Kill Process",
                        icon="x-circle",
                        command=f"kill {proc.pid}",
                        requires_approval=True,
                        danger=True,
                    ),
                ],
                chat_context=f"Process '{proc.name}' (PID {proc.pid}) is consuming "
                            f"{proc.cpu_percent:.1f}% CPU and {proc.mem_mb:.0f}MB RAM. "
                            f"Run by user '{proc.user}'. Command: {proc.command[:100]}",
            ))
        
        return discoveries
    
    def _discover_problem_processes(self, processes: List[ProcessInfo]) -> List[Discovery]:
        """Find zombie, blocked, or stuck processes."""
        discoveries = []
        
        for proc in processes:
            problem_type = None
            severity = DiscoverySeverity.INFO
            
            if proc.state == 'Z':
                problem_type = "Zombie"
                severity = DiscoverySeverity.WARNING
            elif proc.state == 'D':
                problem_type = "Blocked (uninterruptible)"
                severity = DiscoverySeverity.WARNING
            elif proc.state == 'T':
                problem_type = "Stopped"
                severity = DiscoverySeverity.INFO
            
            if problem_type:
                discovery_id = make_discovery_id(DiscoveryType.PROCESS, f"problem-{proc.pid}")
                
                discoveries.append(Discovery(
                    id=discovery_id,
                    type=DiscoveryType.PROCESS,
                    name=f"problem-{proc.pid}",
                    title=f"{proc.name} ({problem_type})",
                    description=f"Process in {problem_type} state",
                    icon="alert-triangle",
                    severity=severity,
                    status=problem_type,
                    status_detail=f"PID: {proc.pid}, Parent: {proc.parent_pid}",
                    source=f"/proc/{proc.pid}",
                    data={
                        "pid": proc.pid,
                        "name": proc.name,
                        "user": proc.user,
                        "state": proc.state,
                        "problem_type": problem_type,
                        "parent_pid": proc.parent_pid,
                        "is_problem_process": True,
                    },
                    chat_context=f"Process '{proc.name}' (PID {proc.pid}) is in {problem_type} state. "
                                f"Parent PID: {proc.parent_pid}. This may indicate a stuck operation or resource wait.",
                ))
        
        return discoveries
    
    def _create_system_summary(self, processes: List[ProcessInfo]) -> Discovery:
        """Create a summary discovery of system resource usage."""
        total_cpu = sum(p.cpu_percent for p in processes)
        total_mem_mb = sum(p.mem_mb for p in processes)
        zombie_count = sum(1 for p in processes if p.state == 'Z')
        blocked_count = sum(1 for p in processes if p.state == 'D')
        
        # Get system totals
        code, stdout, _ = self.run_command(["free", "-m"])
        total_ram_mb = 0
        if code == 0:
            for line in stdout.splitlines():
                if line.startswith("Mem:"):
                    parts = line.split()
                    if len(parts) >= 2:
                        total_ram_mb = int(parts[1])
        
        mem_percent = (total_mem_mb / total_ram_mb * 100) if total_ram_mb > 0 else 0
        
        # Determine severity
        if zombie_count > 5 or blocked_count > 10 or mem_percent > 90:
            severity = DiscoverySeverity.WARNING
            status = "Issues detected"
        else:
            severity = DiscoverySeverity.SUCCESS
            status = "Healthy"
        
        discovery_id = make_discovery_id(DiscoveryType.PROCESS, "summary")
        
        return Discovery(
            id=discovery_id,
            type=DiscoveryType.PROCESS,
            name="summary",
            title="Process Summary",
            description=f"{len(processes)} processes, {mem_percent:.0f}% RAM used",
            icon="cpu",
            severity=severity,
            status=status,
            status_detail=f"Zombies: {zombie_count}, Blocked: {blocked_count}",
            data={
                "process_count": len(processes),
                "total_cpu_percent": total_cpu,
                "total_mem_mb": total_mem_mb,
                "total_ram_mb": total_ram_mb,
                "mem_percent": mem_percent,
                "zombie_count": zombie_count,
                "blocked_count": blocked_count,
                "is_summary": True,
            },
            chat_context=f"System has {len(processes)} running processes using {total_mem_mb:.0f}MB "
                        f"({mem_percent:.0f}%) of {total_ram_mb}MB RAM. "
                        f"Zombie processes: {zombie_count}. Blocked processes: {blocked_count}.",
        )
