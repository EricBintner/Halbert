"""
Alert Engine - Core alerting system.

Monitors system metrics and discoveries for threshold violations.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict, Callable, Any
import logging
import threading
import time

logger = logging.getLogger('cerebric.alerts.engine')


class AlertSeverity(Enum):
    """Alert severity levels."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class Alert:
    """An active or historical alert."""
    id: str
    rule_id: str
    severity: AlertSeverity
    title: str
    message: str
    source: str
    timestamp: datetime = field(default_factory=datetime.now)
    resolved_at: Optional[datetime] = None
    acknowledged: bool = False
    data: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def is_active(self) -> bool:
        return self.resolved_at is None
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "rule_id": self.rule_id,
            "severity": self.severity.value,
            "title": self.title,
            "message": self.message,
            "source": self.source,
            "timestamp": self.timestamp.isoformat(),
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "acknowledged": self.acknowledged,
            "is_active": self.is_active,
            "data": self.data,
        }


@dataclass
class AlertRule:
    """A rule that defines when to trigger an alert."""
    id: str
    name: str
    description: str
    severity: AlertSeverity
    check_fn: Callable[[], Optional[str]]  # Returns message if triggered, None if OK
    cooldown_seconds: int = 300  # 5 minutes default
    enabled: bool = True
    last_triggered: Optional[datetime] = None
    
    def should_trigger(self) -> bool:
        """Check if cooldown has passed."""
        if not self.enabled:
            return False
        if self.last_triggered is None:
            return True
        elapsed = (datetime.now() - self.last_triggered).total_seconds()
        return elapsed >= self.cooldown_seconds


class AlertEngine:
    """
    Central alert management for Cerebric.
    
    Usage:
        engine = AlertEngine()
        engine.add_rule(AlertRule(...))
        engine.start_monitoring()
    """
    
    def __init__(self):
        self.rules: Dict[str, AlertRule] = {}
        self.active_alerts: Dict[str, Alert] = {}
        self.alert_history: List[Alert] = []
        self._monitoring = False
        self._monitor_thread: Optional[threading.Thread] = None
        self._alert_counter = 0
        
        # Register default rules
        self._register_default_rules()
    
    def _register_default_rules(self):
        """Register built-in alert rules."""
        
        # CPU threshold
        self.add_rule(AlertRule(
            id="cpu_high",
            name="High CPU Usage",
            description="CPU usage exceeds 90%",
            severity=AlertSeverity.WARNING,
            check_fn=self._check_cpu_high,
            cooldown_seconds=300,
        ))
        
        # Memory threshold
        self.add_rule(AlertRule(
            id="memory_high",
            name="High Memory Usage",
            description="Memory usage exceeds 85%",
            severity=AlertSeverity.WARNING,
            check_fn=self._check_memory_high,
            cooldown_seconds=300,
        ))
        
        # Disk threshold
        self.add_rule(AlertRule(
            id="disk_critical",
            name="Disk Space Critical",
            description="Disk usage exceeds 95%",
            severity=AlertSeverity.CRITICAL,
            check_fn=self._check_disk_critical,
            cooldown_seconds=600,
        ))
        
        # Failed services
        self.add_rule(AlertRule(
            id="services_failed",
            name="Failed Services",
            description="One or more systemd services have failed",
            severity=AlertSeverity.CRITICAL,
            check_fn=self._check_failed_services,
            cooldown_seconds=300,
        ))
    
    def _check_cpu_high(self) -> Optional[str]:
        """Check if CPU is above threshold."""
        try:
            import psutil
            cpu = psutil.cpu_percent(interval=1)
            if cpu > 90:
                return f"CPU usage is at {cpu:.1f}%"
        except:
            pass
        return None
    
    def _check_memory_high(self) -> Optional[str]:
        """Check if memory is above threshold."""
        try:
            import psutil
            mem = psutil.virtual_memory()
            if mem.percent > 85:
                return f"Memory usage is at {mem.percent:.1f}% ({mem.available / (1024**3):.1f} GB free)"
        except:
            pass
        return None
    
    def _check_disk_critical(self) -> Optional[str]:
        """Check if any disk is critically full."""
        try:
            import psutil
            for partition in psutil.disk_partitions():
                try:
                    usage = psutil.disk_usage(partition.mountpoint)
                    if usage.percent > 95:
                        return f"Disk {partition.mountpoint} is at {usage.percent:.1f}%"
                except:
                    pass
        except:
            pass
        return None
    
    def _check_failed_services(self) -> Optional[str]:
        """Check for failed systemd services."""
        try:
            import subprocess
            result = subprocess.run(
                ["systemctl", "--failed", "--no-legend", "--plain"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0 and result.stdout.strip():
                lines = result.stdout.strip().split('\n')
                count = len(lines)
                if count > 0:
                    first_service = lines[0].split()[0] if lines else "unknown"
                    return f"{count} service(s) failed. First: {first_service}"
        except:
            pass
        return None
    
    def add_rule(self, rule: AlertRule):
        """Add an alert rule."""
        self.rules[rule.id] = rule
        logger.info(f"Registered alert rule: {rule.id}")
    
    def remove_rule(self, rule_id: str):
        """Remove an alert rule."""
        if rule_id in self.rules:
            del self.rules[rule_id]
    
    def check_rules(self) -> List[Alert]:
        """Check all rules and return any new alerts."""
        new_alerts = []
        
        for rule in self.rules.values():
            if not rule.should_trigger():
                continue
            
            try:
                message = rule.check_fn()
                if message:
                    # Create alert
                    self._alert_counter += 1
                    alert = Alert(
                        id=f"alert_{self._alert_counter}",
                        rule_id=rule.id,
                        severity=rule.severity,
                        title=rule.name,
                        message=message,
                        source=rule.id,
                    )
                    
                    # Track it
                    self.active_alerts[alert.id] = alert
                    self.alert_history.append(alert)
                    new_alerts.append(alert)
                    
                    # Update rule
                    rule.last_triggered = datetime.now()
                    
                    logger.warning(f"Alert triggered: {rule.name} - {message}")
                else:
                    # Check if we should resolve existing alert
                    for alert_id, alert in list(self.active_alerts.items()):
                        if alert.rule_id == rule.id and alert.is_active:
                            alert.resolved_at = datetime.now()
                            del self.active_alerts[alert_id]
                            logger.info(f"Alert resolved: {alert.title}")
                            
            except Exception as e:
                logger.error(f"Error checking rule {rule.id}: {e}")
        
        return new_alerts
    
    def acknowledge_alert(self, alert_id: str):
        """Acknowledge an alert."""
        if alert_id in self.active_alerts:
            self.active_alerts[alert_id].acknowledged = True
    
    def resolve_alert(self, alert_id: str):
        """Manually resolve an alert."""
        if alert_id in self.active_alerts:
            alert = self.active_alerts[alert_id]
            alert.resolved_at = datetime.now()
            del self.active_alerts[alert_id]
    
    def get_active_alerts(self) -> List[Alert]:
        """Get all active alerts."""
        return list(self.active_alerts.values())
    
    def get_alert_history(self, limit: int = 100) -> List[Alert]:
        """Get alert history."""
        return self.alert_history[-limit:]
    
    def start_monitoring(self, interval_seconds: int = 60):
        """Start background monitoring."""
        if self._monitoring:
            return
        
        self._monitoring = True
        
        def monitor_loop():
            while self._monitoring:
                try:
                    self.check_rules()
                except Exception as e:
                    logger.error(f"Monitor loop error: {e}")
                time.sleep(interval_seconds)
        
        self._monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
        self._monitor_thread.start()
        logger.info("Alert monitoring started")
    
    def stop_monitoring(self):
        """Stop background monitoring."""
        self._monitoring = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5)
        logger.info("Alert monitoring stopped")


# Global instance
_engine: Optional[AlertEngine] = None

def get_alert_engine() -> AlertEngine:
    """Get global alert engine instance."""
    global _engine
    if _engine is None:
        _engine = AlertEngine()
    return _engine
