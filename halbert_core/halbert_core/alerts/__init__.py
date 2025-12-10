"""
Alert Engine - Threshold monitoring and notifications.

Based on Phase 9 research: docs/Phase9/deep-dives/17-alerts.md

Features:
- Configurable thresholds
- Multiple severity levels
- Alert history
- Notification channels (future: desktop, email)
"""

from .engine import AlertEngine, Alert, AlertSeverity, AlertRule

__all__ = ['AlertEngine', 'Alert', 'AlertSeverity', 'AlertRule']
