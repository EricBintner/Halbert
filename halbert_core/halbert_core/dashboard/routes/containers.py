"""
Container API Routes

Provides endpoints for Docker and Podman container management.
Phase 15: Container Management
"""

import logging
import subprocess
import json
from typing import Any, Dict, List, Optional

try:
    from fastapi import APIRouter, HTTPException
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    APIRouter = object

logger = logging.getLogger("halbert.containers")
router = APIRouter(prefix="/containers", tags=["containers"])


def run_command(cmd: List[str], timeout: int = 30) -> Optional[str]:
    """Run a command and return stdout, or None on error."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return result.stdout.strip() if result.returncode == 0 else None
    except Exception:
        return None


def detect_runtime() -> tuple[Optional[str], Optional[str]]:
    """Detect which container runtime is available."""
    # Check for Docker
    docker_version = run_command(["docker", "--version"])
    if docker_version:
        # Parse version: Docker version 24.0.7, build afdd53b
        import re
        match = re.search(r"Docker version (\S+)", docker_version)
        version = match.group(1).rstrip(",") if match else docker_version
        return "docker", version
    
    # Check for Podman
    podman_version = run_command(["podman", "--version"])
    if podman_version:
        import re
        match = re.search(r"podman version (\S+)", podman_version)
        version = match.group(1) if match else podman_version
        return "podman", version
    
    return None, None


def get_containers(runtime: str) -> List[Dict[str, Any]]:
    """Get list of containers."""
    containers = []
    
    # Use JSON format for reliable parsing
    cmd = [runtime, "ps", "-a", "--format", "json"]
    output = run_command(cmd)
    
    if not output:
        # Fallback to non-JSON format
        cmd = [runtime, "ps", "-a", "--format", "{{.ID}}|{{.Names}}|{{.Image}}|{{.Status}}|{{.Ports}}"]
        output = run_command(cmd)
        if output:
            for line in output.split("\n"):
                if line.strip():
                    parts = line.split("|")
                    if len(parts) >= 5:
                        status_text = parts[3].lower()
                        status = "running" if "up" in status_text else "exited" if "exited" in status_text else "stopped"
                        containers.append({
                            "id": parts[0],
                            "name": parts[1],
                            "image": parts[2],
                            "status": status,
                            "created": "",
                            "ports": parts[4].split(", ") if parts[4] else [],
                            "runtime": runtime,
                            "cpu_percent": None,
                            "memory_mb": None,
                            "memory_limit_mb": None,
                        })
        return containers
    
    # Parse JSON output (Docker and Podman have slightly different formats)
    try:
        # Docker outputs one JSON object per line
        for line in output.split("\n"):
            if line.strip():
                try:
                    data = json.loads(line)
                    
                    # Handle Docker format
                    name = data.get("Names", data.get("Name", ""))
                    if isinstance(name, list):
                        name = name[0] if name else ""
                    
                    status_text = data.get("Status", data.get("State", "")).lower()
                    if "up" in status_text or status_text == "running":
                        status = "running"
                    elif "exited" in status_text:
                        status = "exited"
                    elif "paused" in status_text:
                        status = "paused"
                    else:
                        status = "stopped"
                    
                    ports_raw = data.get("Ports", "")
                    if isinstance(ports_raw, str):
                        ports = [p.strip() for p in ports_raw.split(",") if p.strip()]
                    else:
                        ports = []
                    
                    containers.append({
                        "id": data.get("ID", data.get("Id", ""))[:12],
                        "name": name,
                        "image": data.get("Image", ""),
                        "status": status,
                        "created": data.get("CreatedAt", data.get("Created", "")),
                        "ports": ports,
                        "runtime": runtime,
                        "cpu_percent": None,
                        "memory_mb": None,
                        "memory_limit_mb": None,
                    })
                except json.JSONDecodeError:
                    continue
    except Exception as e:
        logger.warning(f"Failed to parse container JSON: {e}")
    
    # Get stats for running containers
    running_ids = [c["id"] for c in containers if c["status"] == "running"]
    if running_ids:
        stats_output = run_command([runtime, "stats", "--no-stream", "--format", "{{.ID}}|{{.CPUPerc}}|{{.MemUsage}}"] + running_ids)
        if stats_output:
            for line in stats_output.split("\n"):
                if line.strip():
                    parts = line.split("|")
                    if len(parts) >= 3:
                        container_id = parts[0][:12]
                        for container in containers:
                            if container["id"] == container_id:
                                try:
                                    container["cpu_percent"] = float(parts[1].replace("%", ""))
                                except ValueError:
                                    pass
                                try:
                                    # Parse memory: "256MiB / 16GiB"
                                    mem_parts = parts[2].split("/")
                                    if mem_parts:
                                        mem_str = mem_parts[0].strip()
                                        if "GiB" in mem_str:
                                            container["memory_mb"] = float(mem_str.replace("GiB", "")) * 1024
                                        elif "MiB" in mem_str:
                                            container["memory_mb"] = float(mem_str.replace("MiB", ""))
                                        elif "KiB" in mem_str:
                                            container["memory_mb"] = float(mem_str.replace("KiB", "")) / 1024
                                except (ValueError, IndexError):
                                    pass
                                break
    
    return containers


def get_images(runtime: str) -> List[Dict[str, Any]]:
    """Get list of images."""
    images = []
    
    cmd = [runtime, "images", "--format", "{{.ID}}|{{.Repository}}|{{.Tag}}|{{.Size}}|{{.CreatedAt}}"]
    output = run_command(cmd)
    
    if output:
        for line in output.split("\n"):
            if line.strip():
                parts = line.split("|")
                if len(parts) >= 5:
                    # Parse size (e.g., "1.2GB", "500MB")
                    size_str = parts[3]
                    size_mb = 0
                    try:
                        if "GB" in size_str:
                            size_mb = float(size_str.replace("GB", "")) * 1024
                        elif "MB" in size_str:
                            size_mb = float(size_str.replace("MB", ""))
                        elif "KB" in size_str:
                            size_mb = float(size_str.replace("KB", "")) / 1024
                    except ValueError:
                        pass
                    
                    images.append({
                        "id": parts[0],
                        "repository": parts[1],
                        "tag": parts[2],
                        "size_mb": size_mb,
                        "created": parts[4],
                    })
    
    return images


def get_disk_usage(runtime: str) -> int:
    """Get total disk usage for containers/images in MB."""
    cmd = [runtime, "system", "df", "--format", "{{.Size}}"]
    output = run_command(cmd)
    
    total_mb = 0
    if output:
        for line in output.split("\n"):
            if line.strip():
                try:
                    if "GB" in line:
                        total_mb += float(line.replace("GB", "")) * 1024
                    elif "MB" in line:
                        total_mb += float(line.replace("MB", ""))
                except ValueError:
                    pass
    
    return int(total_mb)


def get_container_info() -> Dict[str, Any]:
    """Get full container runtime information."""
    runtime, version = detect_runtime()
    
    if not runtime:
        return {
            "runtime": None,
            "runtime_version": None,
            "containers": [],
            "images": [],
            "stats": {
                "running": 0,
                "stopped": 0,
                "total": 0,
                "images": 0,
                "disk_usage_mb": 0,
            },
            "socket_available": False,
            "error": None,
        }
    
    containers = get_containers(runtime)
    images = get_images(runtime)
    
    running = sum(1 for c in containers if c["status"] == "running")
    stopped = sum(1 for c in containers if c["status"] != "running")
    
    return {
        "runtime": runtime,
        "runtime_version": version,
        "containers": containers,
        "images": images,
        "stats": {
            "running": running,
            "stopped": stopped,
            "total": len(containers),
            "images": len(images),
            "disk_usage_mb": get_disk_usage(runtime),
        },
        "socket_available": True,
        "error": None,
    }


if FASTAPI_AVAILABLE:
    
    @router.get("/info")
    async def get_containers_data() -> Dict[str, Any]:
        """Get container runtime and container information."""
        try:
            return get_container_info()
        except Exception as e:
            logger.error(f"Failed to get container info: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    
    @router.post("/{container_id}/start")
    async def start_container(container_id: str) -> Dict[str, Any]:
        """Start a stopped container."""
        runtime, _ = detect_runtime()
        if not runtime:
            raise HTTPException(status_code=400, detail="No container runtime available")
        
        result = run_command([runtime, "start", container_id])
        if result is not None:
            return {"success": True, "message": f"Container {container_id} started"}
        raise HTTPException(status_code=500, detail=f"Failed to start container {container_id}")
    
    
    @router.post("/{container_id}/stop")
    async def stop_container(container_id: str) -> Dict[str, Any]:
        """Stop a running container."""
        runtime, _ = detect_runtime()
        if not runtime:
            raise HTTPException(status_code=400, detail="No container runtime available")
        
        result = run_command([runtime, "stop", container_id])
        if result is not None:
            return {"success": True, "message": f"Container {container_id} stopped"}
        raise HTTPException(status_code=500, detail=f"Failed to stop container {container_id}")
    
    
    @router.post("/{container_id}/restart")
    async def restart_container(container_id: str) -> Dict[str, Any]:
        """Restart a container."""
        runtime, _ = detect_runtime()
        if not runtime:
            raise HTTPException(status_code=400, detail="No container runtime available")
        
        result = run_command([runtime, "restart", container_id])
        if result is not None:
            return {"success": True, "message": f"Container {container_id} restarted"}
        raise HTTPException(status_code=500, detail=f"Failed to restart container {container_id}")
    
    
    @router.post("/{container_id}/remove")
    async def remove_container(container_id: str) -> Dict[str, Any]:
        """Remove a container."""
        runtime, _ = detect_runtime()
        if not runtime:
            raise HTTPException(status_code=400, detail="No container runtime available")
        
        result = run_command([runtime, "rm", container_id])
        if result is not None:
            return {"success": True, "message": f"Container {container_id} removed"}
        raise HTTPException(status_code=500, detail=f"Failed to remove container {container_id}")
    
    
    @router.get("/{container_id}/logs")
    async def get_container_logs(container_id: str, tail: int = 100) -> Dict[str, Any]:
        """Get container logs."""
        runtime, _ = detect_runtime()
        if not runtime:
            raise HTTPException(status_code=400, detail="No container runtime available")
        
        logs = run_command([runtime, "logs", "--tail", str(tail), container_id])
        return {"logs": logs or "No logs available"}
