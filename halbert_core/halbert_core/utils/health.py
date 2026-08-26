# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Health Check Utilities

Provides system health checks for:
- Ollama service
- ChromaDB
- Dashboard API
- Disk space
- Memory usage

Phase 31: Backend deployment support
"""

import logging
import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class HealthCheck:
    """Result of a single health check."""
    name: str
    status: str  # "healthy", "degraded", "unhealthy"
    message: str
    details: Dict = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class SystemHealth:
    """Overall system health status."""
    status: str  # "healthy", "degraded", "unhealthy"
    checks: List[HealthCheck]
    timestamp: datetime = field(default_factory=datetime.now)
    
    @property
    def healthy_count(self) -> int:
        return sum(1 for c in self.checks if c.status == "healthy")
    
    @property
    def unhealthy_count(self) -> int:
        return sum(1 for c in self.checks if c.status == "unhealthy")


def check_ollama() -> HealthCheck:
    """Check Ollama service health."""
    try:
        from .ollama import get_status
        status = get_status()
        
        if status.running:
            model_count = len(status.models)
            return HealthCheck(
                name="ollama",
                status="healthy",
                message=f"Ollama running with {model_count} models",
                details={"models": [m.name for m in status.models]}
            )
        elif status.installed:
            return HealthCheck(
                name="ollama",
                status="degraded",
                message="Ollama installed but not running",
                details={"error": "Service not started"}
            )
        else:
            return HealthCheck(
                name="ollama",
                status="unhealthy",
                message="Ollama not installed",
                details={"install": "curl -fsSL https://ollama.com/install.sh | sh"}
            )
    except Exception as e:
        return HealthCheck(
            name="ollama",
            status="unhealthy",
            message=f"Ollama check failed: {e}",
            details={"error": str(e)}
        )


def check_chromadb() -> HealthCheck:
    """Check ChromaDB health."""
    try:
        import chromadb
        
        # Try to create a client
        client = chromadb.Client()
        collections = client.list_collections()
        
        return HealthCheck(
            name="chromadb",
            status="healthy",
            message=f"ChromaDB ready with {len(collections)} collections",
            details={"collections": len(collections)}
        )
    except ImportError:
        return HealthCheck(
            name="chromadb",
            status="degraded",
            message="ChromaDB not installed",
            details={"install": "pip install chromadb"}
        )
    except Exception as e:
        return HealthCheck(
            name="chromadb",
            status="unhealthy",
            message=f"ChromaDB error: {e}",
            details={"error": str(e)}
        )


def check_disk_space(min_gb: float = 1.0) -> HealthCheck:
    """Check available disk space."""
    try:
        home = os.path.expanduser("~")
        usage = shutil.disk_usage(home)
        
        free_gb = usage.free / (1024**3)
        total_gb = usage.total / (1024**3)
        used_pct = (usage.used / usage.total) * 100
        
        if free_gb >= min_gb * 5:
            status = "healthy"
            message = f"{free_gb:.1f} GB free ({100-used_pct:.0f}%)"
        elif free_gb >= min_gb:
            status = "degraded"
            message = f"Low disk space: {free_gb:.1f} GB free"
        else:
            status = "unhealthy"
            message = f"Critical: Only {free_gb:.1f} GB free"
        
        return HealthCheck(
            name="disk_space",
            status=status,
            message=message,
            details={
                "free_gb": round(free_gb, 2),
                "total_gb": round(total_gb, 2),
                "used_percent": round(used_pct, 1)
            }
        )
    except Exception as e:
        return HealthCheck(
            name="disk_space",
            status="unhealthy",
            message=f"Disk check failed: {e}",
            details={"error": str(e)}
        )


def check_memory(min_mb: int = 500) -> HealthCheck:
    """Check available memory."""
    try:
        import psutil
        
        mem = psutil.virtual_memory()
        available_mb = mem.available / (1024**2)
        total_mb = mem.total / (1024**2)
        used_pct = mem.percent
        
        if available_mb >= min_mb * 4:
            status = "healthy"
            message = f"{available_mb:.0f} MB available ({100-used_pct:.0f}%)"
        elif available_mb >= min_mb:
            status = "degraded"
            message = f"Low memory: {available_mb:.0f} MB available"
        else:
            status = "unhealthy"
            message = f"Critical: Only {available_mb:.0f} MB available"
        
        return HealthCheck(
            name="memory",
            status=status,
            message=message,
            details={
                "available_mb": round(available_mb, 0),
                "total_mb": round(total_mb, 0),
                "used_percent": round(used_pct, 1)
            }
        )
    except ImportError:
        return HealthCheck(
            name="memory",
            status="degraded",
            message="psutil not installed",
            details={"install": "pip install psutil"}
        )
    except Exception as e:
        return HealthCheck(
            name="memory",
            status="unhealthy",
            message=f"Memory check failed: {e}",
            details={"error": str(e)}
        )


def check_dashboard_api(port: int = 8000) -> HealthCheck:
    """Check if dashboard API is responding."""
    try:
        import requests
        
        response = requests.get(f"http://127.0.0.1:{port}/api/status", timeout=2)
        
        if response.status_code == 200:
            return HealthCheck(
                name="dashboard_api",
                status="healthy",
                message=f"Dashboard API running on port {port}",
                details={"port": port}
            )
        else:
            return HealthCheck(
                name="dashboard_api",
                status="degraded",
                message=f"API returned status {response.status_code}",
                details={"status_code": response.status_code}
            )
    except Exception:
        return HealthCheck(
            name="dashboard_api",
            status="unhealthy",
            message=f"Dashboard API not responding on port {port}",
            details={"port": port}
        )


def get_system_health(include_api: bool = False) -> SystemHealth:
    """
    Run all health checks and return overall status.
    
    Args:
        include_api: Whether to check the dashboard API (skip if we ARE the API)
    
    Returns:
        SystemHealth with all check results
    """
    checks = [
        check_ollama(),
        check_chromadb(),
        check_disk_space(),
        check_memory(),
    ]
    
    if include_api:
        checks.append(check_dashboard_api())
    
    # Determine overall status
    if any(c.status == "unhealthy" for c in checks):
        overall = "unhealthy"
    elif any(c.status == "degraded" for c in checks):
        overall = "degraded"
    else:
        overall = "healthy"
    
    return SystemHealth(
        status=overall,
        checks=checks
    )


def print_health_report():
    """Print a formatted health report to console."""
    health = get_system_health()
    
    status_icons = {
        "healthy": "✅",
        "degraded": "⚠️",
        "unhealthy": "❌"
    }
    
    print(f"\n{'=' * 50}")
    print(f"Halbert System Health: {status_icons[health.status]} {health.status.upper()}")
    print(f"{'=' * 50}\n")
    
    for check in health.checks:
        icon = status_icons[check.status]
        print(f"  {icon} {check.name}: {check.message}")
    
    print(f"\n{'=' * 50}")
    print(f"Healthy: {health.healthy_count}/{len(health.checks)}")
    print(f"{'=' * 50}\n")


if __name__ == "__main__":
    print_health_report()
