"""
Anomaly Detector (Phase 3 M6)

Basic anomaly detection rules for autonomous operations.
"""

from __future__ import annotations
from typing import Dict, Any, List
from dataclasses import dataclass
from datetime import datetime, timedelta
from collections import deque
import psutil
from ..obs.logging import get_logger

logger = get_logger("halbert")


class AnomalyDetected(Exception):
    """Raised when an anomaly is detected."""
    pass


@dataclass
class AnomalyEvent:
    """Record of an anomaly detection."""
    timestamp: datetime
    anomaly_type: str
    severity: str  # "warning", "critical"
    description: str
    metrics: Dict[str, Any]


class AnomalyDetector:
    """
    Detects anomalies in system behavior and job execution.
    
    Detection rules:
    - CPU spike (>90% sustained)
    - Memory leak (growth >500MB in short time)
    - Repeated failures (3+ consecutive failures)
    - High error rate (>50% errors in recent jobs)
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize anomaly detector.
        
        Args:
            config: anomalies section from autonomy.yml
        """
        self.config = config
        self.history = deque(maxlen=100)  # Last 100 events
        self.failure_streak = 0
        self.recent_outcomes = deque(maxlen=20)  # Last 20 job outcomes
        
        logger.info("AnomalyDetector initialized", extra={"config": config})
    
    def check_cpu_spike(self) -> bool:
        """
        Check for sustained high CPU usage.
        
        Returns:
            True if CPU spike detected
        """
        threshold = self.config["cpu_spike_threshold"]
        current_cpu = psutil.cpu_percent(interval=1.0)
        
        if current_cpu > threshold:
            anomaly = AnomalyEvent(
                timestamp=datetime.now(),
                anomaly_type="cpu_spike",
                severity="warning",
                description=f"CPU usage {current_cpu:.1f}% above threshold {threshold}%",
                metrics={"cpu_percent": current_cpu, "threshold": threshold}
            )
            self.history.append(anomaly)
            logger.warning("CPU spike detected", extra={
                "cpu": current_cpu,
                "threshold": threshold
            })
            return True
        
        return False
    
    def check_memory_leak(self, baseline_mb: int) -> bool:
        """
        Check for suspicious memory growth.
        
        Args:
            baseline_mb: Memory usage at start of job
        
        Returns:
            True if memory leak suspected
        """
        leak_threshold = self.config["memory_leak_mb"]
        current_mb = int(psutil.Process().memory_info().rss / (1024 * 1024))
        growth = current_mb - baseline_mb
        
        if growth > leak_threshold:
            anomaly = AnomalyEvent(
                timestamp=datetime.now(),
                anomaly_type="memory_leak",
                severity="warning",
                description=f"Memory grew {growth}MB (baseline {baseline_mb}MB → current {current_mb}MB)",
                metrics={
                    "baseline_mb": baseline_mb,
                    "current_mb": current_mb,
                    "growth_mb": growth,
                    "threshold_mb": leak_threshold
                }
            )
            self.history.append(anomaly)
            logger.warning("Memory leak suspected", extra=anomaly.metrics)
            return True
        
        return False
    
    def record_job_outcome(self, success: bool, job_id: str):
        """
        Record job outcome for error rate tracking.
        
        Args:
            success: True if job succeeded
            job_id: Job identifier
        """
        self.recent_outcomes.append({
            "timestamp": datetime.now(),
            "success": success,
            "job_id": job_id
        })
        
        if not success:
            self.failure_streak += 1
        else:
            self.failure_streak = 0
        
        # Check for repeated failures
        repeated_failures_threshold = self.config["repeated_failures"]
        if self.failure_streak >= repeated_failures_threshold:
            anomaly = AnomalyEvent(
                timestamp=datetime.now(),
                anomaly_type="repeated_failures",
                severity="critical",
                description=f"{self.failure_streak} consecutive job failures",
                metrics={
                    "failure_streak": self.failure_streak,
                    "threshold": repeated_failures_threshold,
                    "job_id": job_id
                }
            )
            self.history.append(anomaly)
            logger.error("Repeated failures detected", extra=anomaly.metrics)
            raise AnomalyDetected(anomaly.description)
    
    def check_error_rate(self) -> bool:
        """
        Check if error rate is too high.
        
        Returns:
            True if error rate exceeds threshold
        """
        if len(self.recent_outcomes) < 5:
            # Not enough data
            return False
        
        failures = sum(1 for outcome in self.recent_outcomes if not outcome["success"])
        error_rate = failures / len(self.recent_outcomes)
        threshold = self.config["error_rate_threshold"]
        
        if error_rate > threshold:
            anomaly = AnomalyEvent(
                timestamp=datetime.now(),
                anomaly_type="high_error_rate",
                severity="critical",
                description=f"Error rate {error_rate:.1%} exceeds threshold {threshold:.1%}",
                metrics={
                    "error_rate": error_rate,
                    "threshold": threshold,
                    "failures": failures,
                    "total": len(self.recent_outcomes)
                }
            )
            self.history.append(anomaly)
            logger.error("High error rate detected", extra=anomaly.metrics)
            return True
        
        return False
    
    def get_recent_anomalies(self, hours: int = 24) -> List[AnomalyEvent]:
        """
        Get anomalies detected in the last N hours.
        
        Args:
            hours: Look back window in hours
        
        Returns:
            List of recent anomalies
        """
        cutoff = datetime.now() - timedelta(hours=hours)
        return [a for a in self.history if a.timestamp > cutoff]
    
    def get_summary(self) -> Dict[str, Any]:
        """
        Get summary of anomaly detection status.
        
        Returns:
            Summary dict for dashboard
        """
        recent = self.get_recent_anomalies(hours=24)
        critical = [a for a in recent if a.severity == "critical"]
        
        return {
            "total_anomalies_24h": len(recent),
            "critical_anomalies_24h": len(critical),
            "failure_streak": self.failure_streak,
            "recent_error_rate": (
                sum(1 for o in self.recent_outcomes if not o["success"]) / len(self.recent_outcomes)
                if self.recent_outcomes else 0.0
            ),
            "last_anomaly": (
                {
                    "type": recent[-1].anomaly_type,
                    "severity": recent[-1].severity,
                    "description": recent[-1].description,
                    "timestamp": recent[-1].timestamp.isoformat()
                }
                if recent else None
            )
        }
