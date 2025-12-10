from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional


@dataclass
class Job:
    """
    Phase 2 scheduler job model.
    Represents a scheduled maintenance routine with retries and state tracking.
    """
    id: str
    task: str  # e.g., "snapshot_configs", "update_packages"
    schedule: str  # cron expression or ISO timestamp
    priority: int = 5  # 1=highest, 10=lowest
    inputs: Dict[str, Any] = field(default_factory=dict)
    state: str = "pending"  # pending, running, completed, failed, cancelled
    retries: int = 0
    max_retries: int = 3
    timeout_s: int = 600
    created_at: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error: Optional[str] = None

    def is_terminal(self) -> bool:
        return self.state in ("completed", "failed", "cancelled")
