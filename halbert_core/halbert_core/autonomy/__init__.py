# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Autonomy Guardrails (Phase 3 M6)

Safety systems for autonomous operations:
- Confidence thresholds
- Resource budgets
- Anomaly detection
- Safe-mode fallback
- Recovery playbooks
"""

from .guardrails import GuardrailEnforcer, GuardrailViolation
from .budgets import BudgetTracker, BudgetExceeded
from .anomaly_detector import AnomalyDetector, AnomalyDetected
from .recovery import RecoveryExecutor, RecoveryAction

__all__ = [
    "GuardrailEnforcer",
    "GuardrailViolation",
    "BudgetTracker",
    "BudgetExceeded",
    "AnomalyDetector",
    "AnomalyDetected",
    "RecoveryExecutor",
    "RecoveryAction",
]
