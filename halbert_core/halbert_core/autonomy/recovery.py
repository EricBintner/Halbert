"""
Recovery Playbooks (Phase 3 M6)

Executes recovery actions when jobs fail or anomalies detected.
"""

from __future__ import annotations
from typing import Dict, Any, Optional
from enum import Enum
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import shutil
from ..obs.logging import get_logger
from ..obs.audit import write_audit

logger = get_logger("halbert")


class RecoveryAction(Enum):
    """Types of recovery actions."""
    ROLLBACK = "rollback"
    RESTART_SERVICE = "restart_service"
    ALERT_USER = "alert_user"
    ENTER_SAFE_MODE = "enter_safe_mode"


@dataclass
class RecoveryResult:
    """Result of a recovery action."""
    action: RecoveryAction
    success: bool
    message: str
    timestamp: datetime
    details: Dict[str, Any]


class RecoveryExecutor:
    """
    Executes recovery playbooks when failures occur.
    
    Recovery actions:
    - Rollback: Restore previous config version
    - Restart service: Attempt service restart
    - Alert user: Send notification
    - Enter safe-mode: Pause autonomous operations
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize recovery executor.
        
        Args:
            config: recovery section from autonomy.yml
        """
        self.config = config
        self.history = []
        
        logger.info("RecoveryExecutor initialized", extra={"config": config})
    
    def execute_rollback(self, file_path: str) -> RecoveryResult:
        """
        Roll back a config file to previous version.
        
        Args:
            file_path: Path to config file to rollback
        
        Returns:
            RecoveryResult with success/failure
        """
        if not self.config.get("rollback", {}).get("enabled", False):
            return RecoveryResult(
                action=RecoveryAction.ROLLBACK,
                success=False,
                message="Rollback disabled in config",
                timestamp=datetime.now(),
                details={}
            )
        
        backup_path = f"{file_path}.bak"
        
        try:
            if not Path(backup_path).exists():
                return RecoveryResult(
                    action=RecoveryAction.ROLLBACK,
                    success=False,
                    message=f"Backup not found: {backup_path}",
                    timestamp=datetime.now(),
                    details={"file": file_path, "backup": backup_path}
                )
            
            # Restore from backup
            shutil.copy2(backup_path, file_path)
            
            result = RecoveryResult(
                action=RecoveryAction.ROLLBACK,
                success=True,
                message=f"Rolled back {file_path} from backup",
                timestamp=datetime.now(),
                details={"file": file_path, "backup": backup_path}
            )
            
            logger.info("Rollback successful", extra=result.details)
            write_audit(
                tool="recovery",
                mode="rollback",
                request_id="",
                ok=True,
                summary=result.message,
                path=file_path
            )
            
            self.history.append(result)
            return result
        
        except Exception as e:
            result = RecoveryResult(
                action=RecoveryAction.ROLLBACK,
                success=False,
                message=f"Rollback failed: {e}",
                timestamp=datetime.now(),
                details={"file": file_path, "error": str(e)}
            )
            
            logger.error("Rollback failed", extra=result.details)
            self.history.append(result)
            return result
    
    def execute_restart_service(self, service_name: str) -> RecoveryResult:
        """
        Attempt to restart a service.
        
        Args:
            service_name: Name of service to restart
        
        Returns:
            RecoveryResult with success/failure
        """
        if not self.config.get("restart_service", {}).get("enabled", False):
            return RecoveryResult(
                action=RecoveryAction.RESTART_SERVICE,
                success=False,
                message="Service restart disabled in config",
                timestamp=datetime.now(),
                details={}
            )
        
        try:
            import subprocess
            
            # Try systemctl restart (Linux)
            result_proc = subprocess.run(
                ["systemctl", "restart", service_name],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result_proc.returncode == 0:
                result = RecoveryResult(
                    action=RecoveryAction.RESTART_SERVICE,
                    success=True,
                    message=f"Restarted service: {service_name}",
                    timestamp=datetime.now(),
                    details={"service": service_name}
                )
                
                logger.info("Service restart successful", extra=result.details)
                write_audit(
                    tool="recovery",
                    mode="restart_service",
                    request_id="",
                    ok=True,
                    summary=result.message,
                    service=service_name
                )
            else:
                result = RecoveryResult(
                    action=RecoveryAction.RESTART_SERVICE,
                    success=False,
                    message=f"Service restart failed: {result_proc.stderr}",
                    timestamp=datetime.now(),
                    details={"service": service_name, "stderr": result_proc.stderr}
                )
                
                logger.error("Service restart failed", extra=result.details)
            
            self.history.append(result)
            return result
        
        except Exception as e:
            result = RecoveryResult(
                action=RecoveryAction.RESTART_SERVICE,
                success=False,
                message=f"Service restart exception: {e}",
                timestamp=datetime.now(),
                details={"service": service_name, "error": str(e)}
            )
            
            logger.error("Service restart exception", extra=result.details)
            self.history.append(result)
            return result
    
    def execute_alert_user(self, alert_message: str, severity: str = "warning") -> RecoveryResult:
        """
        Send alert to user.
        
        Args:
            alert_message: Alert message
            severity: Alert severity (info, warning, critical)
        
        Returns:
            RecoveryResult with success/failure
        """
        if not self.config.get("alert_user", {}).get("enabled", False):
            return RecoveryResult(
                action=RecoveryAction.ALERT_USER,
                success=False,
                message="User alerts disabled in config",
                timestamp=datetime.now(),
                details={}
            )
        
        try:
            # Write alert to dashboard artifacts
            alert_file = Path("data/dashboard/alerts.jsonl")
            alert_file.parent.mkdir(parents=True, exist_ok=True)
            
            import json
            alert_record = {
                "timestamp": datetime.now().isoformat(),
                "severity": severity,
                "message": alert_message,
                "source": "recovery"
            }
            
            with open(alert_file, "a") as f:
                f.write(json.dumps(alert_record) + "\n")
            
            result = RecoveryResult(
                action=RecoveryAction.ALERT_USER,
                success=True,
                message=f"Alert sent: {alert_message}",
                timestamp=datetime.now(),
                details={"severity": severity, "message": alert_message}
            )
            
            logger.info("User alert sent", extra=result.details)
            self.history.append(result)
            return result
        
        except Exception as e:
            result = RecoveryResult(
                action=RecoveryAction.ALERT_USER,
                success=False,
                message=f"Alert failed: {e}",
                timestamp=datetime.now(),
                details={"error": str(e)}
            )
            
            logger.error("User alert failed", extra=result.details)
            self.history.append(result)
            return result
    
    def get_history(self, limit: int = 20) -> list[RecoveryResult]:
        """
        Get recent recovery action history.
        
        Args:
            limit: Number of recent actions to return
        
        Returns:
            List of recent recovery results
        """
        return self.history[-limit:]
    
    def get_summary(self) -> Dict[str, Any]:
        """
        Get summary of recovery actions.
        
        Returns:
            Summary dict for dashboard
        """
        if not self.history:
            return {
                "total_actions": 0,
                "recent_actions": [],
                "success_rate": 0.0
            }
        
        successful = sum(1 for r in self.history if r.success)
        recent = self.history[-5:]
        
        return {
            "total_actions": len(self.history),
            "successful_actions": successful,
            "success_rate": successful / len(self.history),
            "recent_actions": [
                {
                    "action": r.action.value,
                    "success": r.success,
                    "message": r.message,
                    "timestamp": r.timestamp.isoformat()
                }
                for r in recent
            ]
        }
