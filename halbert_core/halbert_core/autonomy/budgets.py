"""
Budget Tracking (Phase 3 M6)

Tracks resource usage during job execution and enforces limits.
"""

from __future__ import annotations
from typing import Dict, Any
from dataclasses import dataclass, field
from datetime import datetime
import psutil
from ..obs.logging import get_logger

logger = get_logger("halbert")


class BudgetExceeded(Exception):
    """Raised when a resource budget is exceeded during execution."""
    pass


@dataclass
class BudgetSnapshot:
    """Snapshot of resource usage at a point in time."""
    timestamp: datetime
    cpu_percent: float
    memory_mb: int
    
    @classmethod
    def capture(cls) -> "BudgetSnapshot":
        """Capture current resource usage."""
        return cls(
            timestamp=datetime.now(),
            cpu_percent=psutil.cpu_percent(interval=0.1),
            memory_mb=int(psutil.Process().memory_info().rss / (1024 * 1024))
        )


@dataclass
class BudgetTracker:
    """
    Tracks resource usage during job execution.
    
    Usage:
        tracker = BudgetTracker(cpu_max=50, memory_max=2048, time_max=30)
        tracker.start()
        # ... do work ...
        tracker.check()  # Raises BudgetExceeded if over limits
        tracker.stop()
    """
    
    cpu_percent_max: float
    memory_mb_max: int
    time_minutes_max: float
    
    started: bool = field(default=False, init=False)
    start_time: datetime = field(default=None, init=False)
    start_snapshot: BudgetSnapshot = field(default=None, init=False)
    peak_cpu: float = field(default=0.0, init=False)
    peak_memory: int = field(default=0, init=False)
    
    def start(self):
        """Start tracking resources."""
        self.started = True
        self.start_time = datetime.now()
        self.start_snapshot = BudgetSnapshot.capture()
        self.peak_cpu = self.start_snapshot.cpu_percent
        self.peak_memory = self.start_snapshot.memory_mb
        
        logger.info("Budget tracker started", extra={
            "limits": {
                "cpu": self.cpu_percent_max,
                "memory": self.memory_mb_max,
                "time": self.time_minutes_max
            },
            "baseline": {
                "cpu": self.start_snapshot.cpu_percent,
                "memory": self.start_snapshot.memory_mb
            }
        })
    
    def check(self) -> BudgetSnapshot:
        """
        Check current resource usage against budgets.
        
        Returns:
            Current budget snapshot
        
        Raises:
            BudgetExceeded: If any budget exceeded
        """
        if not self.started:
            raise RuntimeError("BudgetTracker not started")
        
        current = BudgetSnapshot.capture()
        
        # Update peaks
        self.peak_cpu = max(self.peak_cpu, current.cpu_percent)
        self.peak_memory = max(self.peak_memory, current.memory_mb)
        
        # Check time budget
        elapsed_minutes = (current.timestamp - self.start_time).total_seconds() / 60
        if elapsed_minutes > self.time_minutes_max:
            logger.error("Time budget exceeded", extra={
                "elapsed": elapsed_minutes,
                "limit": self.time_minutes_max
            })
            raise BudgetExceeded(
                f"Time budget exceeded: {elapsed_minutes:.1f}min > {self.time_minutes_max}min"
            )
        
        # Check CPU budget
        if current.cpu_percent > self.cpu_percent_max:
            logger.error("CPU budget exceeded", extra={
                "current": current.cpu_percent,
                "limit": self.cpu_percent_max
            })
            raise BudgetExceeded(
                f"CPU budget exceeded: {current.cpu_percent:.1f}% > {self.cpu_percent_max}%"
            )
        
        # Check memory budget
        if current.memory_mb > self.memory_mb_max:
            logger.error("Memory budget exceeded", extra={
                "current": current.memory_mb,
                "limit": self.memory_mb_max
            })
            raise BudgetExceeded(
                f"Memory budget exceeded: {current.memory_mb}MB > {self.memory_mb_max}MB"
            )
        
        return current
    
    def stop(self) -> Dict[str, Any]:
        """
        Stop tracking and return usage summary.
        
        Returns:
            Summary of resource usage during execution
        """
        if not self.started:
            raise RuntimeError("BudgetTracker not started")
        
        end_time = datetime.now()
        duration_seconds = (end_time - self.start_time).total_seconds()
        
        summary = {
            "duration_seconds": duration_seconds,
            "duration_minutes": duration_seconds / 60,
            "peak_cpu_percent": self.peak_cpu,
            "peak_memory_mb": self.peak_memory,
            "within_budgets": True  # If we got here, budgets were respected
        }
        
        logger.info("Budget tracker stopped", extra=summary)
        
        self.started = False
        return summary
    
    @classmethod
    def from_config(cls, budgets_config: Dict[str, Any]) -> "BudgetTracker":
        """
        Create BudgetTracker from config dict.
        
        Args:
            budgets_config: budgets section from autonomy.yml
        """
        return cls(
            cpu_percent_max=budgets_config["cpu_percent_max"],
            memory_mb_max=budgets_config["memory_mb_max"],
            time_minutes_max=budgets_config["time_minutes_max"]
        )
