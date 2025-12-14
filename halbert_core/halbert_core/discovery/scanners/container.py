"""
Container Scanner - Docker/Podman container issues.

Common forum questions this addresses:
- "Docker eating all my disk space"
- "Container won't start"
- "Docker daemon not running"
- "Permission denied with Docker"
- "Out of memory in container"
- "Docker network issues"
- "Orphaned volumes eating space"

Discovers:
- Docker daemon status
- Running/stopped containers
- Disk usage (images, volumes, build cache)
- Resource-heavy containers
- Network configuration
- Permission issues
"""

from __future__ import annotations
from typing import List, Dict, Optional
from pathlib import Path
import json
import re

from .base import BaseScanner
from ..schema import (
    Discovery,
    DiscoveryType,
    DiscoverySeverity,
    DiscoveryAction,
    make_discovery_id,
)


class ContainerScanner(BaseScanner):
    """
    Scanner for Docker/Podman containers.
    """
    
    @property
    def discovery_type(self) -> DiscoveryType:
        return DiscoveryType.CONTAINER
    
    def scan(self) -> List[Discovery]:
        """Scan container environment."""
        discoveries = []
        
        # Check Docker first, then Podman
        if self._has_docker():
            discoveries.extend(self._scan_docker())
        elif self._has_podman():
            discoveries.extend(self._scan_podman())
        
        self.logger.info(f"Found {len(discoveries)} container discoveries")
        return discoveries
    
    def _has_docker(self) -> bool:
        """Check if Docker is available."""
        code, _, _ = self.run_command(["docker", "version"], timeout=5)
        return code == 0
    
    def _has_podman(self) -> bool:
        """Check if Podman is available."""
        code, _, _ = self.run_command(["podman", "version"], timeout=5)
        return code == 0
    
    def _scan_docker(self) -> List[Discovery]:
        """Scan Docker environment."""
        discoveries = []
        
        # Check daemon status
        code, stdout, stderr = self.run_command(["docker", "info", "--format", "json"], timeout=10)
        
        if code != 0:
            # Docker daemon not running or permission issue
            issues = []
            if "permission denied" in stderr.lower():
                issues.append("Permission denied - user not in docker group")
            elif "Cannot connect" in stderr:
                issues.append("Docker daemon not running")
            
            discovery_id = make_discovery_id(DiscoveryType.CONTAINER, "docker-status")
            discoveries.append(Discovery(
                id=discovery_id,
                type=DiscoveryType.CONTAINER,
                name="docker-status",
                title="Docker Status",
                description="Docker daemon not accessible",
                icon="box",
                severity=DiscoverySeverity.WARNING,
                status="Not Running",
                status_detail="; ".join(issues) if issues else None,
                data={
                    "daemon_running": False,
                    "issues": issues,
                    "is_docker_status": True,
                },
                actions=[
                    DiscoveryAction(
                        id="start",
                        label="Start Docker",
                        icon="play",
                        command="sudo systemctl start docker",
                        requires_approval=True,
                    ),
                    DiscoveryAction(
                        id="add-group",
                        label="Add to docker group",
                        icon="user-plus",
                        command="sudo usermod -aG docker $USER",
                        requires_approval=True,
                    ),
                ],
                chat_context=f"Docker daemon not accessible. "
                            f"{'Issues: ' + '; '.join(issues) + '. ' if issues else ''}"
                            f"Start with 'sudo systemctl start docker'. "
                            f"For permission issues: 'sudo usermod -aG docker $USER' then logout/login.",
            ))
            return discoveries
        
        # Parse Docker info
        try:
            info = json.loads(stdout)
            containers_running = info.get("ContainersRunning", 0)
            containers_stopped = info.get("ContainersStopped", 0)
            images = info.get("Images", 0)
            
            discovery_id = make_discovery_id(DiscoveryType.CONTAINER, "docker-status")
            discoveries.append(Discovery(
                id=discovery_id,
                type=DiscoveryType.CONTAINER,
                name="docker-status",
                title="Docker Status",
                description=f"{containers_running} running, {containers_stopped} stopped, {images} images",
                icon="box",
                severity=DiscoverySeverity.SUCCESS,
                status=f"{containers_running} running",
                data={
                    "daemon_running": True,
                    "containers_running": containers_running,
                    "containers_stopped": containers_stopped,
                    "images": images,
                    "is_docker_status": True,
                },
                chat_context=f"Docker running: {containers_running} containers active, "
                            f"{containers_stopped} stopped, {images} images.",
            ))
        except:
            pass
        
        # Check disk usage
        code, stdout, _ = self.run_command(["docker", "system", "df", "--format", "json"], timeout=15)
        if code == 0:
            try:
                # Parse disk usage
                df_data = json.loads(stdout)
                
                total_size = 0
                reclaimable = 0
                
                for item in df_data:
                    size_str = item.get("Size", "0B")
                    reclaim_str = item.get("Reclaimable", "0B")
                    
                    # Simple size parsing
                    size_bytes = self._parse_docker_size(size_str)
                    reclaim_bytes = self._parse_docker_size(reclaim_str)
                    
                    total_size += size_bytes
                    reclaimable += reclaim_bytes
                
                # Report if significant disk usage
                if total_size > 1024**3:  # > 1GB
                    total_gb = total_size / 1024**3
                    reclaim_gb = reclaimable / 1024**3
                    
                    severity = DiscoverySeverity.WARNING if total_gb > 20 else DiscoverySeverity.INFO
                    
                    discovery_id = make_discovery_id(DiscoveryType.CONTAINER, "docker-disk")
                    discoveries.append(Discovery(
                        id=discovery_id,
                        type=DiscoveryType.CONTAINER,
                        name="docker-disk",
                        title="Docker Disk Usage",
                        description=f"Using {total_gb:.1f}GB ({reclaim_gb:.1f}GB reclaimable)",
                        icon="hard-drive",
                        severity=severity,
                        status=f"{total_gb:.1f}GB",
                        status_detail=f"{reclaim_gb:.1f}GB reclaimable",
                        data={
                            "total_bytes": total_size,
                            "reclaimable_bytes": reclaimable,
                            "is_docker_disk": True,
                        },
                        actions=[
                            DiscoveryAction(
                                id="prune",
                                label="Cleanup",
                                icon="trash-2",
                                command="docker system prune -af",
                                requires_approval=True,
                            ),
                        ],
                        chat_context=f"Docker using {total_gb:.1f}GB disk space. "
                                    f"{reclaim_gb:.1f}GB can be reclaimed. "
                                    f"Cleanup with 'docker system prune -af' (removes all unused data).",
                    ))
            except:
                pass
        
        # List resource-heavy containers
        code, stdout, _ = self.run_command([
            "docker", "stats", "--no-stream", "--format", 
            "{{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}"
        ], timeout=10)
        
        if code == 0:
            for line in stdout.strip().splitlines():
                parts = line.split('\t')
                if len(parts) >= 3:
                    name = parts[0]
                    cpu = parts[1].replace('%', '')
                    mem = parts[2]
                    
                    try:
                        cpu_pct = float(cpu)
                        if cpu_pct > 50:  # High CPU
                            discovery_id = make_discovery_id(DiscoveryType.CONTAINER, f"container-{name}")
                            discoveries.append(Discovery(
                                id=discovery_id,
                                type=DiscoveryType.CONTAINER,
                                name=f"container-{name}",
                                title=f"Container: {name}",
                                description=f"High CPU: {cpu_pct:.1f}%, Memory: {mem}",
                                icon="box",
                                severity=DiscoverySeverity.WARNING,
                                status=f"CPU: {cpu_pct:.1f}%",
                                status_detail=f"Memory: {mem}",
                                data={
                                    "container_name": name,
                                    "cpu_percent": cpu_pct,
                                    "memory_usage": mem,
                                    "is_resource_heavy": True,
                                },
                                chat_context=f"Container '{name}' using {cpu_pct:.1f}% CPU, {mem} memory. "
                                            f"Consider resource limits.",
                            ))
                    except:
                        pass
        
        return discoveries
    
    def _scan_podman(self) -> List[Discovery]:
        """Scan Podman environment (similar to Docker)."""
        discoveries = []
        
        code, stdout, _ = self.run_command(["podman", "ps", "-a", "--format", "json"], timeout=10)
        
        if code == 0:
            try:
                containers = json.loads(stdout)
                running = sum(1 for c in containers if c.get("State") == "running")
                stopped = len(containers) - running
                
                discovery_id = make_discovery_id(DiscoveryType.CONTAINER, "podman-status")
                discoveries.append(Discovery(
                    id=discovery_id,
                    type=DiscoveryType.CONTAINER,
                    name="podman-status",
                    title="Podman Status",
                    description=f"{running} running, {stopped} stopped",
                    icon="box",
                    severity=DiscoverySeverity.SUCCESS,
                    status=f"{running} running",
                    data={
                        "containers_running": running,
                        "containers_stopped": stopped,
                        "is_podman_status": True,
                    },
                    chat_context=f"Podman: {running} containers running, {stopped} stopped.",
                ))
            except:
                pass
        
        return discoveries
    
    def _parse_docker_size(self, size_str: str) -> int:
        """Parse Docker size strings like '2.5GB' to bytes."""
        try:
            size_str = size_str.strip().upper()
            if 'TB' in size_str:
                return int(float(size_str.replace('TB', '')) * 1024**4)
            elif 'GB' in size_str:
                return int(float(size_str.replace('GB', '')) * 1024**3)
            elif 'MB' in size_str:
                return int(float(size_str.replace('MB', '')) * 1024**2)
            elif 'KB' in size_str:
                return int(float(size_str.replace('KB', '')) * 1024)
            elif 'B' in size_str:
                return int(float(size_str.replace('B', '')))
            return 0
        except:
            return 0
