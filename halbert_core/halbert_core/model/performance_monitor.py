"""
Performance monitoring for multi-model system (Phase 5 M5).

Tracks model performance, detects degradation, and provides recommendations.
"""

from __future__ import annotations
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from enum import Enum
import json
import logging
import statistics

logger = logging.getLogger('halbert.model')


class PerformanceLevel(str, Enum):
    """Performance quality levels."""
    EXCELLENT = "excellent"
    GOOD = "good"
    ACCEPTABLE = "acceptable"
    DEGRADED = "degraded"
    CRITICAL = "critical"


class AlertSeverity(str, Enum):
    """Alert severity levels."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class ModelMetrics:
    """Performance metrics for a model."""
    model_id: str
    provider: str
    
    # Latency metrics (ms)
    latency_samples: List[int] = field(default_factory=list)
    avg_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    p99_latency_ms: float = 0.0
    
    # Quality metrics
    quality_scores: List[float] = field(default_factory=list)
    avg_quality: float = 0.0
    
    # Error tracking
    total_requests: int = 0
    failed_requests: int = 0
    error_rate: float = 0.0
    
    # Memory tracking
    memory_samples: List[int] = field(default_factory=list)
    avg_memory_mb: float = 0.0
    peak_memory_mb: int = 0
    
    # Timestamps
    first_seen: datetime = field(default_factory=datetime.now)
    last_seen: datetime = field(default_factory=datetime.now)
    
    def update(self):
        """Update calculated metrics from samples."""
        # Latency
        if self.latency_samples:
            self.avg_latency_ms = statistics.mean(self.latency_samples)
            sorted_latency = sorted(self.latency_samples)
            n = len(sorted_latency)
            self.p95_latency_ms = sorted_latency[int(n * 0.95)] if n > 0 else 0
            self.p99_latency_ms = sorted_latency[int(n * 0.99)] if n > 0 else 0
        
        # Quality
        if self.quality_scores:
            self.avg_quality = statistics.mean(self.quality_scores)
        
        # Error rate
        if self.total_requests > 0:
            self.error_rate = self.failed_requests / self.total_requests
        
        # Memory
        if self.memory_samples:
            self.avg_memory_mb = statistics.mean(self.memory_samples)
            self.peak_memory_mb = max(self.memory_samples)
        
        self.last_seen = datetime.now()
    
    def get_performance_level(self) -> PerformanceLevel:
        """Determine overall performance level."""
        # Check error rate first
        if self.error_rate > 0.2:  # >20% errors
            return PerformanceLevel.CRITICAL
        elif self.error_rate > 0.1:  # >10% errors
            return PerformanceLevel.DEGRADED
        
        # Check quality
        if self.avg_quality > 0:
            if self.avg_quality < 0.6:
                return PerformanceLevel.DEGRADED
            elif self.avg_quality < 0.7:
                return PerformanceLevel.ACCEPTABLE
            elif self.avg_quality < 0.85:
                return PerformanceLevel.GOOD
            else:
                return PerformanceLevel.EXCELLENT
        
        # Default based on error rate
        if self.error_rate < 0.01:
            return PerformanceLevel.EXCELLENT
        elif self.error_rate < 0.05:
            return PerformanceLevel.GOOD
        else:
            return PerformanceLevel.ACCEPTABLE


@dataclass
class PerformanceAlert:
    """Performance alert."""
    severity: AlertSeverity
    message: str
    model_id: Optional[str]
    metric: str
    value: float
    threshold: float
    timestamp: datetime = field(default_factory=datetime.now)
    recommendation: Optional[str] = None


class PerformanceMonitor:
    """
    Monitor model performance and health.
    
    Features:
    - Track latency, quality, errors per model
    - Detect performance degradation
    - Generate alerts and recommendations
    - Memory pressure monitoring
    - Automatic model suggestions
    
    Usage:
        monitor = PerformanceMonitor()
        
        # Record metrics
        monitor.record_request("llama3.1:8b", latency_ms=234, success=True)
        monitor.record_quality("llama3.1:8b", quality_score=0.92)
        
        # Get status
        status = monitor.get_status()
        alerts = monitor.get_alerts()
    """
    
    def __init__(
        self,
        state_file: Optional[Path] = None,
        alert_thresholds: Optional[Dict[str, float]] = None
    ):
        """
        Initialize performance monitor.
        
        Args:
            state_file: Path to save state (for persistence)
            alert_thresholds: Custom alert thresholds
        """
        if state_file is None:
            state_file = Path.home() / '.local/share/halbert/performance_state.json'
        
        self.state_file = Path(state_file)
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Metrics per model
        self.metrics: Dict[str, ModelMetrics] = {}
        
        # Alert history
        self.alerts: List[PerformanceAlert] = []
        
        # Alert thresholds
        self.thresholds = alert_thresholds or {
            "latency_p95_ms": 5000,      # P95 latency > 5s
            "latency_p99_ms": 10000,     # P99 latency > 10s
            "error_rate": 0.1,           # Error rate > 10%
            "quality_min": 0.7,          # Quality < 70%
            "memory_percent": 0.85,      # Memory > 85%
        }
        
        # Sample limits (to prevent unbounded growth)
        self.max_samples = 1000
        
        # Load state if exists
        self._load_state()
        
        logger.info("PerformanceMonitor initialized")
    
    def record_request(
        self,
        model_id: str,
        provider: str,
        latency_ms: int,
        success: bool,
        memory_mb: Optional[int] = None
    ):
        """
        Record a model request.
        
        Args:
            model_id: Model identifier
            provider: Provider name
            latency_ms: Request latency in milliseconds
            success: Whether request succeeded
            memory_mb: Current memory usage
        """
        # Get or create metrics
        if model_id not in self.metrics:
            self.metrics[model_id] = ModelMetrics(
                model_id=model_id,
                provider=provider
            )
        
        metrics = self.metrics[model_id]
        
        # Update counters
        metrics.total_requests += 1
        if not success:
            metrics.failed_requests += 1
        
        # Add latency sample
        metrics.latency_samples.append(latency_ms)
        if len(metrics.latency_samples) > self.max_samples:
            metrics.latency_samples.pop(0)
        
        # Add memory sample
        if memory_mb is not None:
            metrics.memory_samples.append(memory_mb)
            if len(metrics.memory_samples) > self.max_samples:
                metrics.memory_samples.pop(0)
        
        # Update calculated metrics
        metrics.update()
        
        # Check for alerts
        self._check_alerts(model_id)
        
        logger.debug(f"Recorded request: {model_id}, latency={latency_ms}ms, success={success}")
    
    def record_quality(self, model_id: str, quality_score: float):
        """
        Record quality score for a model.
        
        Args:
            model_id: Model identifier
            quality_score: Quality score (0.0-1.0)
        """
        if model_id not in self.metrics:
            logger.warning(f"No metrics for model: {model_id}")
            return
        
        metrics = self.metrics[model_id]
        
        # Add quality sample
        metrics.quality_scores.append(quality_score)
        if len(metrics.quality_scores) > self.max_samples:
            metrics.quality_scores.pop(0)
        
        # Update calculated metrics
        metrics.update()
        
        # Check for quality alerts
        self._check_alerts(model_id)
    
    def _check_alerts(self, model_id: str):
        """Check if model metrics trigger any alerts."""
        if model_id not in self.metrics:
            return
        
        metrics = self.metrics[model_id]
        
        # Check P95 latency
        if metrics.p95_latency_ms > self.thresholds["latency_p95_ms"]:
            self._create_alert(
                AlertSeverity.WARNING,
                f"High P95 latency for {model_id}",
                model_id,
                "latency_p95_ms",
                metrics.p95_latency_ms,
                self.thresholds["latency_p95_ms"],
                "Consider upgrading hardware or switching to a smaller model"
            )
        
        # Check error rate
        if metrics.error_rate > self.thresholds["error_rate"]:
            severity = AlertSeverity.ERROR if metrics.error_rate > 0.2 else AlertSeverity.WARNING
            self._create_alert(
                severity,
                f"High error rate for {model_id}",
                model_id,
                "error_rate",
                metrics.error_rate,
                self.thresholds["error_rate"],
                "Check model configuration and system resources"
            )
        
        # Check quality
        if metrics.avg_quality > 0 and metrics.avg_quality < self.thresholds["quality_min"]:
            self._create_alert(
                AlertSeverity.WARNING,
                f"Low quality for {model_id}",
                model_id,
                "quality",
                metrics.avg_quality,
                self.thresholds["quality_min"],
                "Consider switching to a larger model for better quality"
            )
    
    def _create_alert(
        self,
        severity: AlertSeverity,
        message: str,
        model_id: Optional[str],
        metric: str,
        value: float,
        threshold: float,
        recommendation: Optional[str] = None
    ):
        """Create a new alert if not duplicate."""
        # Check for recent duplicate
        recent_cutoff = datetime.now() - timedelta(minutes=5)
        for alert in self.alerts:
            if (alert.model_id == model_id and 
                alert.metric == metric and 
                alert.timestamp > recent_cutoff):
                # Duplicate alert, skip
                return
        
        alert = PerformanceAlert(
            severity=severity,
            message=message,
            model_id=model_id,
            metric=metric,
            value=value,
            threshold=threshold,
            recommendation=recommendation
        )
        
        self.alerts.append(alert)
        
        # Keep only recent alerts (last 100)
        if len(self.alerts) > 100:
            self.alerts = self.alerts[-100:]
        
        logger.warning(f"Performance alert: {message} ({metric}={value:.2f}, threshold={threshold})")
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get overall performance status.
        
        Returns:
            Status dictionary with metrics and alerts
        """
        status = {
            "timestamp": datetime.now().isoformat(),
            "models": {},
            "alerts": {
                "total": len(self.alerts),
                "critical": 0,
                "error": 0,
                "warning": 0,
                "info": 0,
            },
            "recommendations": [],
        }
        
        # Count alerts by severity
        for alert in self.alerts:
            if alert.timestamp > datetime.now() - timedelta(hours=1):
                status["alerts"][alert.severity.value] += 1
        
        # Add model metrics
        for model_id, metrics in self.metrics.items():
            status["models"][model_id] = {
                "provider": metrics.provider,
                "performance_level": metrics.get_performance_level().value,
                "avg_latency_ms": round(metrics.avg_latency_ms, 1),
                "p95_latency_ms": round(metrics.p95_latency_ms, 1),
                "error_rate": round(metrics.error_rate, 3),
                "avg_quality": round(metrics.avg_quality, 2),
                "total_requests": metrics.total_requests,
                "avg_memory_mb": round(metrics.avg_memory_mb, 1),
            }
        
        # Generate recommendations
        status["recommendations"] = self._generate_recommendations()
        
        return status
    
    def get_alerts(
        self,
        severity: Optional[AlertSeverity] = None,
        since: Optional[datetime] = None
    ) -> List[PerformanceAlert]:
        """
        Get alerts, optionally filtered.
        
        Args:
            severity: Filter by severity
            since: Only alerts after this time
        
        Returns:
            List of alerts
        """
        alerts = self.alerts
        
        if severity:
            alerts = [a for a in alerts if a.severity == severity]
        
        if since:
            alerts = [a for a in alerts if a.timestamp > since]
        
        return sorted(alerts, key=lambda a: a.timestamp, reverse=True)
    
    def _generate_recommendations(self) -> List[Dict[str, str]]:
        """Generate performance recommendations."""
        recommendations = []
        
        for model_id, metrics in self.metrics.items():
            level = metrics.get_performance_level()
            
            # High latency recommendation
            if metrics.p95_latency_ms > 3000:
                recommendations.append({
                    "model": model_id,
                    "type": "latency",
                    "message": f"P95 latency is {metrics.p95_latency_ms}ms",
                    "action": "Consider switching to a smaller/faster model",
                    "priority": "medium"
                })
            
            # Quality recommendation
            if metrics.avg_quality > 0 and metrics.avg_quality < 0.75:
                recommendations.append({
                    "model": model_id,
                    "type": "quality",
                    "message": f"Average quality is {metrics.avg_quality:.1%}",
                    "action": "Consider switching to a larger/better model",
                    "priority": "medium"
                })
            
            # Error rate recommendation
            if metrics.error_rate > 0.05:
                recommendations.append({
                    "model": model_id,
                    "type": "reliability",
                    "message": f"Error rate is {metrics.error_rate:.1%}",
                    "action": "Check system resources and model configuration",
                    "priority": "high"
                })
        
        return recommendations
    
    def get_model_metrics(self, model_id: str) -> Optional[ModelMetrics]:
        """
        Get metrics for a specific model.
        
        Args:
            model_id: Model identifier
        
        Returns:
            ModelMetrics or None
        """
        return self.metrics.get(model_id)
    
    def reset_metrics(self, model_id: Optional[str] = None):
        """
        Reset metrics.
        
        Args:
            model_id: Specific model to reset, or None for all
        """
        if model_id:
            if model_id in self.metrics:
                del self.metrics[model_id]
                logger.info(f"Reset metrics for: {model_id}")
        else:
            self.metrics.clear()
            logger.info("Reset all metrics")
    
    def _save_state(self):
        """Save state to disk."""
        try:
            state = {
                "metrics": {},
                "alerts": [],
            }
            
            # Serialize metrics (keep only recent samples)
            for model_id, metrics in self.metrics.items():
                state["metrics"][model_id] = {
                    "model_id": metrics.model_id,
                    "provider": metrics.provider,
                    "latency_samples": metrics.latency_samples[-100:],
                    "quality_scores": metrics.quality_scores[-100:],
                    "total_requests": metrics.total_requests,
                    "failed_requests": metrics.failed_requests,
                    "memory_samples": metrics.memory_samples[-100:],
                }
            
            # Serialize recent alerts
            recent_alerts = [a for a in self.alerts if a.timestamp > datetime.now() - timedelta(days=1)]
            for alert in recent_alerts:
                state["alerts"].append({
                    "severity": alert.severity.value,
                    "message": alert.message,
                    "model_id": alert.model_id,
                    "metric": alert.metric,
                    "value": alert.value,
                    "threshold": alert.threshold,
                    "timestamp": alert.timestamp.isoformat(),
                    "recommendation": alert.recommendation,
                })
            
            with open(self.state_file, 'w') as f:
                json.dump(state, f, indent=2)
        
        except Exception as e:
            logger.error(f"Failed to save performance state: {e}")
    
    def _load_state(self):
        """Load state from disk."""
        if not self.state_file.exists():
            return
        
        try:
            with open(self.state_file, 'r') as f:
                state = json.load(f)
            
            # Load metrics
            for model_id, data in state.get("metrics", {}).items():
                metrics = ModelMetrics(
                    model_id=data["model_id"],
                    provider=data["provider"],
                    latency_samples=data.get("latency_samples", []),
                    quality_scores=data.get("quality_scores", []),
                    total_requests=data.get("total_requests", 0),
                    failed_requests=data.get("failed_requests", 0),
                    memory_samples=data.get("memory_samples", []),
                )
                metrics.update()
                self.metrics[model_id] = metrics
            
            # Load alerts
            for alert_data in state.get("alerts", []):
                alert = PerformanceAlert(
                    severity=AlertSeverity(alert_data["severity"]),
                    message=alert_data["message"],
                    model_id=alert_data.get("model_id"),
                    metric=alert_data["metric"],
                    value=alert_data["value"],
                    threshold=alert_data["threshold"],
                    timestamp=datetime.fromisoformat(alert_data["timestamp"]),
                    recommendation=alert_data.get("recommendation"),
                )
                self.alerts.append(alert)
            
            logger.info(f"Loaded performance state: {len(self.metrics)} models, {len(self.alerts)} alerts")
        
        except Exception as e:
            logger.error(f"Failed to load performance state: {e}")
    
    def __del__(self):
        """Save state on destruction."""
        try:
            self._save_state()
        except:
            pass
