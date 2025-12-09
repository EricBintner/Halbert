"""
Guardrail Enforcement (Phase 3 M6)

Enforces confidence thresholds, budgets, and safety policies for autonomous operations.
"""

from __future__ import annotations
from typing import Dict, Any, Optional
from pathlib import Path
import yaml
from ..obs.logging import get_logger
from ..obs.audit import write_audit

logger = get_logger("cerebric")


class GuardrailViolation(Exception):
    """Raised when a guardrail check fails."""
    pass


class GuardrailEnforcer:
    """
    Enforces guardrails for autonomous operations.
    
    Checks:
    - Confidence thresholds (min confidence for auto-execution)
    - Resource budgets (CPU, memory, time limits)
    - Anomaly conditions (triggers safe-mode)
    - Policy compliance (defers to policy engine)
    """
    
    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialize guardrail enforcer.
        
        Args:
            config_path: Path to autonomy.yml (defaults to config/autonomy.yml)
        """
        if config_path is None:
            config_path = Path("config/autonomy.yml")
        
        self.config_path = config_path
        self.config = self._load_config()
        self.safe_mode_active = False
        
        logger.info("GuardrailEnforcer initialized", extra={
            "config_path": str(config_path),
            "safe_mode": self.safe_mode_active
        })
    
    def _load_config(self) -> Dict[str, Any]:
        """Load guardrail configuration."""
        try:
            with open(self.config_path) as f:
                config = yaml.safe_load(f)
            logger.info("Loaded guardrail config", extra={"source": str(self.config_path)})
            return config
        except Exception as e:
            logger.error(f"Failed to load guardrail config: {e}")
            # Return safe defaults
            return {
                "confidence": {"min_auto_execute": 0.8, "min_approval_execute": 0.5},
                "budgets": {
                    "cpu_percent_max": 50,
                    "memory_mb_max": 2048,
                    "time_minutes_max": 30,
                    "frequency_per_hour_max": 10
                },
                "safe_mode": {"auto_pause_on_anomaly": True}
            }
    
    def check_confidence(self, confidence: float, task: str) -> tuple[bool, Optional[str]]:
        """
        Check if confidence meets threshold for auto-execution.
        
        Args:
            confidence: Confidence score (0.0-1.0)
            task: Task description (for logging)
        
        Returns:
            (allowed, reason)
            - (True, None) = Auto-execute allowed
            - (False, "approval_required") = Requires manual approval
            - (False, "rejected") = Confidence too low, reject
        
        Raises:
            GuardrailViolation: If confidence is below minimum threshold
        """
        min_auto = self.config["confidence"]["min_auto_execute"]
        min_approval = self.config["confidence"]["min_approval_execute"]
        
        if confidence >= min_auto:
            # High confidence: auto-execute
            logger.info("Confidence check passed (auto-execute)", extra={
                "confidence": confidence,
                "threshold": min_auto,
                "task": task
            })
            write_audit(
                tool="guardrails",
                mode="confidence_check",
                request_id="",
                ok=True,
                summary=f"Auto-execute allowed (confidence={confidence:.2f})",
                task=task
            )
            return (True, None)
        
        elif confidence >= min_approval:
            # Medium confidence: require approval
            logger.warning("Confidence check requires approval", extra={
                "confidence": confidence,
                "threshold": min_auto,
                "task": task
            })
            write_audit(
                tool="guardrails",
                mode="confidence_check",
                request_id="",
                ok=True,
                summary=f"Approval required (confidence={confidence:.2f})",
                task=task
            )
            return (False, "approval_required")
        
        else:
            # Low confidence: reject
            logger.error("Confidence check failed (too low)", extra={
                "confidence": confidence,
                "threshold": min_approval,
                "task": task
            })
            write_audit(
                tool="guardrails",
                mode="confidence_check",
                request_id="",
                ok=False,
                summary=f"Rejected (confidence={confidence:.2f} below threshold)",
                task=task
            )
            raise GuardrailViolation(
                f"Confidence {confidence:.2f} below minimum {min_approval:.2f}"
            )
    
    def check_budgets(self, estimated_resources: Dict[str, Any]) -> bool:
        """
        Check if estimated resource usage is within budgets.
        
        Args:
            estimated_resources: {
                "cpu_percent": float,
                "memory_mb": int,
                "time_minutes": int
            }
        
        Returns:
            True if within budgets, False otherwise
        
        Raises:
            GuardrailViolation: If budgets exceeded
        """
        budgets = self.config["budgets"]
        violations = []
        
        # Check each budget
        if estimated_resources.get("cpu_percent", 0) > budgets["cpu_percent_max"]:
            violations.append(
                f"CPU: {estimated_resources['cpu_percent']}% > {budgets['cpu_percent_max']}%"
            )
        
        if estimated_resources.get("memory_mb", 0) > budgets["memory_mb_max"]:
            violations.append(
                f"Memory: {estimated_resources['memory_mb']}MB > {budgets['memory_mb_max']}MB"
            )
        
        if estimated_resources.get("time_minutes", 0) > budgets["time_minutes_max"]:
            violations.append(
                f"Time: {estimated_resources['time_minutes']}min > {budgets['time_minutes_max']}min"
            )
        
        if violations:
            logger.error("Budget check failed", extra={
                "violations": violations,
                "estimated": estimated_resources
            })
            write_audit(
                tool="guardrails",
                mode="budget_check",
                request_id="",
                ok=False,
                summary=f"Budget violations: {'; '.join(violations)}",
                resources=estimated_resources
            )
            raise GuardrailViolation(f"Budget exceeded: {'; '.join(violations)}")
        
        logger.info("Budget check passed", extra={"estimated": estimated_resources})
        write_audit(
            tool="guardrails",
            mode="budget_check",
            request_id="",
            ok=True,
            summary="Within budgets",
            resources=estimated_resources
        )
        return True
    
    def enter_safe_mode(self, reason: str):
        """
        Enter safe-mode (pause autonomous operations).
        
        Args:
            reason: Reason for entering safe-mode
        """
        self.safe_mode_active = True
        logger.critical("ENTERING SAFE MODE", extra={"reason": reason})
        write_audit(
            tool="guardrails",
            mode="safe_mode",
            request_id="",
            ok=True,
            summary=f"Safe mode activated: {reason}"
        )
        
        # Write safe-mode indicator file
        safe_mode_file = Path("data/safe_mode_active.flag")
        safe_mode_file.parent.mkdir(parents=True, exist_ok=True)
        with open(safe_mode_file, "w") as f:
            f.write(reason)
    
    def exit_safe_mode(self, user: str):
        """
        Exit safe-mode (resume autonomous operations).
        
        Args:
            user: User who authorized exit
        """
        self.safe_mode_active = False
        logger.info("EXITING SAFE MODE", extra={"authorized_by": user})
        write_audit(
            tool="guardrails",
            mode="safe_mode",
            request_id="",
            ok=True,
            summary=f"Safe mode deactivated by {user}"
        )
        
        # Remove safe-mode indicator file
        safe_mode_file = Path("data/safe_mode_active.flag")
        if safe_mode_file.exists():
            safe_mode_file.unlink()
    
    def is_safe_mode_active(self) -> bool:
        """Check if safe-mode is currently active."""
        # Check file in case of restart
        safe_mode_file = Path("data/safe_mode_active.flag")
        if safe_mode_file.exists() and not self.safe_mode_active:
            self.safe_mode_active = True
            logger.warning("Safe mode detected from file (survived restart)")
        
        return self.safe_mode_active
    
    def check_all(
        self,
        confidence: float,
        estimated_resources: Dict[str, Any],
        task: str
    ) -> tuple[bool, Optional[str]]:
        """
        Convenience method: check all guardrails.
        
        Args:
            confidence: Confidence score
            estimated_resources: Resource estimates
            task: Task description
        
        Returns:
            (allowed, reason) - See check_confidence() for details
        
        Raises:
            GuardrailViolation: If any guardrail violated
        """
        # Check safe-mode first
        if self.is_safe_mode_active():
            logger.warning("Safe mode active, rejecting task", extra={"task": task})
            raise GuardrailViolation("Safe mode is active")
        
        # Check budgets
        self.check_budgets(estimated_resources)
        
        # Check confidence (returns tuple)
        return self.check_confidence(confidence, task)
