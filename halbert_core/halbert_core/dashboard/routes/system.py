"""
System status API routes.
"""

from fastapi import APIRouter, Depends
from typing import Dict, Any
import psutil
from datetime import datetime, timezone

router = APIRouter()


@router.get("/status")
async def get_system_status() -> Dict[str, Any]:
    """
    Get current system status.
    
    Returns system metrics (CPU, memory, disk, uptime).
    """
    # CPU
    cpu_percent = psutil.cpu_percent(interval=0.5)
    cpu_temp = get_cpu_temp()
    
    # Memory
    memory = psutil.virtual_memory()
    
    # Disk
    disk = psutil.disk_usage('/')
    
    # Uptime
    boot_time = datetime.fromtimestamp(psutil.boot_time(), tz=timezone.utc)
    uptime_seconds = (datetime.now(timezone.utc) - boot_time).total_seconds()
    
    # Load average
    load_avg = psutil.getloadavg()
    
    return {
        "cpu": {
            "percent": cpu_percent,
            "temperature": cpu_temp,
            "cores": psutil.cpu_count()
        },
        "memory": {
            "total_gb": memory.total / (1024**3),
            "used_gb": memory.used / (1024**3),
            "available_gb": memory.available / (1024**3),
            "percent": memory.percent
        },
        "disk": {
            "total_gb": disk.total / (1024**3),
            "used_gb": disk.used / (1024**3),
            "free_gb": disk.free / (1024**3),
            "percent": disk.percent
        },
        "uptime": {
            "seconds": int(uptime_seconds),
            "boot_time": boot_time.isoformat()
        },
        "load_average": {
            "1min": load_avg[0],
            "5min": load_avg[1],
            "15min": load_avg[2]
        },
        "timestamp": datetime.now(timezone.utc).isoformat() + 'Z'
    }


def get_cpu_temp() -> float | None:
    """Get CPU temperature if available."""
    try:
        temps = psutil.sensors_temperatures()
        
        # Try common sensor names
        for name in ['coretemp', 'k10temp', 'cpu_thermal']:
            if name in temps:
                entries = temps[name]
                if entries:
                    return entries[0].current
        
        return None
    
    except (AttributeError, Exception):
        return None
