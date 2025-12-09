"""
Approval workflows for Cerebric (Phase 3 M4).

Provides approval mechanisms for autonomous decisions:
- Dry-run simulation
- User prompts (CLI/Dashboard)
- Rollback strategies
- Approval history tracking
"""

from .engine import ApprovalEngine, ApprovalRequest, ApprovalDecision
from .simulator import DryRunSimulator, SimulationResult

__all__ = [
    'ApprovalEngine',
    'ApprovalRequest',
    'ApprovalDecision',
    'DryRunSimulator',
    'SimulationResult',
]
