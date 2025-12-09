"""
Approval engine for autonomous decisions.

Phase 3 M4: User approval workflows with dry-run simulation.
"""

from __future__ import annotations
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict
from pathlib import Path
from enum import Enum

from ..utils.paths import data_subdir

logger = logging.getLogger('cerebric.approval.engine')


class ApprovalStatus(Enum):
    """Approval request status."""
    PENDING = 'pending'
    APPROVED = 'approved'
    REJECTED = 'rejected'
    EXPIRED = 'expired'


@dataclass
class ApprovalRequest:
    """
    Request for user approval of an autonomous action.
    
    Contains all information needed for user to make informed decision.
    """
    id: str
    task: str
    action: str
    reasoning: str
    confidence: float
    risk_level: str
    
    # Context
    system_state: Dict[str, Any]
    affected_resources: List[str]
    
    # Dry-run simulation (optional)
    simulation_result: Optional[Dict[str, Any]] = None
    
    # Timing
    requested_at: Optional[str] = None
    expires_at: Optional[str] = None
    
    # Decision
    status: str = 'pending'
    approved_at: Optional[str] = None
    rejected_at: Optional[str] = None
    rejection_reason: Optional[str] = None
    
    # Audit
    requested_by: str = 'autonomous_executor'
    approved_by: Optional[str] = None


@dataclass
class ApprovalDecision:
    """
    User's approval decision.
    """
    request_id: str
    approved: bool
    reason: Optional[str] = None
    conditions: Optional[Dict[str, Any]] = None  # e.g., {"max_retries": 1}
    decided_by: str = 'user'
    decided_at: Optional[str] = None


class ApprovalEngine:
    """
    Manages approval workflows for autonomous decisions.
    
    Features:
    - Request approval with dry-run simulation
    - Store approval requests
    - Track approval history
    - CLI/Dashboard approval prompts
    
    Example:
        engine = ApprovalEngine()
        
        # Create approval request
        request = ApprovalRequest(
            id='req_001',
            task='fan_throttle',
            action='Increase fan speed 2000 → 3000 RPM',
            reasoning='CPU temp 89°C exceeds threshold',
            confidence=0.92,
            risk_level='medium',
            system_state={'cpu_temp': 89.0},
            affected_resources=['/sys/class/hwmon/hwmon0/pwm1']
        )
        
        # Request approval (CLI prompt)
        decision = engine.request_approval(request, mode='cli')
        
        if decision.approved:
            # Execute action
            pass
    """
    
    def __init__(self, storage_dir: Optional[str] = None):
        """
        Initialize approval engine.
        
        Args:
            storage_dir: Directory for approval storage (default: data/approval)
        """
        if storage_dir is None:
            storage_dir = data_subdir("approval")
        
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        
        # Separate storage for requests and decisions
        self.requests_dir = self.storage_dir / 'requests'
        self.history_dir = self.storage_dir / 'history'
        self.requests_dir.mkdir(exist_ok=True)
        self.history_dir.mkdir(exist_ok=True)
        
        logger.info(f"Approval engine initialized: {self.storage_dir}")
    
    def request_approval(
        self,
        request: ApprovalRequest,
        mode: str = 'cli',
        timeout_seconds: Optional[int] = None
    ) -> ApprovalDecision:
        """
        Request user approval for an action.
        
        Args:
            request: ApprovalRequest with action details
            mode: Approval mode ('cli', 'dashboard', 'auto')
            timeout_seconds: Timeout for approval (None = no timeout)
        
        Returns:
            ApprovalDecision with user's choice
        """
        # Set timestamps
        if not request.requested_at:
            request.requested_at = self._get_timestamp()
        
        if timeout_seconds:
            # Calculate expiration (simplified - would use proper datetime math)
            request.expires_at = self._get_timestamp()  # TODO: Add timeout_seconds
        
        # Save request
        self._save_request(request)
        
        # Get approval based on mode
        if mode == 'cli':
            decision = self._prompt_cli(request)
        elif mode == 'dashboard':
            decision = self._prompt_dashboard(request)
        elif mode == 'auto':
            # Auto-approve for testing (dangerous in production!)
            logger.warning("Auto-approval mode - ONLY FOR TESTING")
            decision = ApprovalDecision(
                request_id=request.id,
                approved=True,
                reason='Auto-approved (testing mode)',
                decided_by='auto',
                decided_at=self._get_timestamp()
            )
        else:
            raise ValueError(f"Unknown approval mode: {mode}")
        
        # Update request status
        request.status = 'approved' if decision.approved else 'rejected'
        if decision.approved:
            request.approved_at = decision.decided_at
            request.approved_by = decision.decided_by
        else:
            request.rejected_at = decision.decided_at
            request.rejection_reason = decision.reason
        
        # Save updated request and decision
        self._save_request(request)
        self._save_decision(decision)
        
        logger.info(
            f"Approval {'granted' if decision.approved else 'denied'} "
            f"for request {request.id}"
        )
        
        return decision
    
    def _prompt_cli(self, request: ApprovalRequest) -> ApprovalDecision:
        """
        Prompt user for approval via CLI.
        
        Args:
            request: ApprovalRequest
        
        Returns:
            ApprovalDecision from user
        """
        print("\n" + "=" * 70)
        print("🚨 APPROVAL REQUIRED")
        print("=" * 70)
        print(f"Task: {request.task}")
        print(f"Action: {request.action}")
        print(f"Reasoning: {request.reasoning}")
        print(f"Confidence: {request.confidence:.2f}")
        print(f"Risk Level: {request.risk_level}")
        print()
        
        # Show affected resources
        if request.affected_resources:
            print("Affected Resources:")
            for resource in request.affected_resources:
                print(f"  - {resource}")
            print()
        
        # Show system state
        if request.system_state:
            print("Current System State:")
            for key, value in request.system_state.items():
                print(f"  {key}: {value}")
            print()
        
        # Show simulation result if available
        if request.simulation_result:
            print("DRY-RUN SIMULATION:")
            print(json.dumps(request.simulation_result, indent=2))
            print()
        
        print("=" * 70)
        
        # Prompt for decision
        while True:
            response = input("Approve this action? [y/N/details]: ").strip().lower()
            
            if response == 'details':
                # Show full request as JSON
                print("\nFull Request Details:")
                print(json.dumps(asdict(request), indent=2))
                print()
                continue
            
            if response in ('y', 'yes'):
                reason = input("Approval reason (optional): ").strip() or None
                
                return ApprovalDecision(
                    request_id=request.id,
                    approved=True,
                    reason=reason,
                    decided_by='cli_user',
                    decided_at=self._get_timestamp()
                )
            
            elif response in ('n', 'no', ''):
                reason = input("Rejection reason: ").strip() or "User declined"
                
                return ApprovalDecision(
                    request_id=request.id,
                    approved=False,
                    reason=reason,
                    decided_by='cli_user',
                    decided_at=self._get_timestamp()
                )
            
            else:
                print("Invalid response. Please enter 'y', 'n', or 'details'.")
    
    def _prompt_dashboard(self, request: ApprovalRequest) -> ApprovalDecision:
        """
        Prompt user for approval via dashboard (Phase 3 M5).
        
        Currently placeholder - returns auto-reject.
        
        Args:
            request: ApprovalRequest
        
        Returns:
            ApprovalDecision (auto-reject for now)
        """
        logger.warning(
            "Dashboard approval not yet implemented (Phase 3 M5). "
            "Auto-rejecting for safety."
        )
        
        return ApprovalDecision(
            request_id=request.id,
            approved=False,
            reason='Dashboard approval not implemented yet',
            decided_by='system',
            decided_at=self._get_timestamp()
        )
    
    def get_pending_requests(self) -> List[ApprovalRequest]:
        """Get all pending approval requests."""
        pending = []
        
        for request_file in self.requests_dir.glob('*.json'):
            try:
                with open(request_file, 'r') as f:
                    data = json.load(f)
                
                if data.get('status') == 'pending':
                    request = ApprovalRequest(**data)
                    pending.append(request)
            
            except Exception as e:
                logger.error(f"Failed to load request {request_file}: {e}")
        
        return pending
    
    def get_request(self, request_id: str) -> Optional[ApprovalRequest]:
        """Get approval request by ID."""
        request_file = self.requests_dir / f"{request_id}.json"
        
        if not request_file.exists():
            return None
        
        try:
            with open(request_file, 'r') as f:
                data = json.load(f)
            
            return ApprovalRequest(**data)
        
        except Exception as e:
            logger.error(f"Failed to load request {request_id}: {e}")
            return None
    
    def get_approval_history(
        self,
        limit: int = 100,
        approved_only: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Get approval history.
        
        Args:
            limit: Maximum number of records
            approved_only: Only return approved requests
        
        Returns:
            List of approval records (newest first)
        """
        history = []
        
        for history_file in sorted(
            self.history_dir.glob('*.json'),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )[:limit]:
            try:
                with open(history_file, 'r') as f:
                    record = json.load(f)
                
                if approved_only and not record.get('approved'):
                    continue
                
                history.append(record)
            
            except Exception as e:
                logger.error(f"Failed to load history {history_file}: {e}")
        
        return history
    
    def _save_request(self, request: ApprovalRequest):
        """Save approval request to disk."""
        request_file = self.requests_dir / f"{request.id}.json"
        
        with open(request_file, 'w') as f:
            json.dump(asdict(request), f, indent=2)
    
    def _save_decision(self, decision: ApprovalDecision):
        """Save approval decision to history."""
        # Save to history with timestamp in filename
        timestamp = decision.decided_at.replace(':', '-').replace('.', '-')
        history_file = self.history_dir / f"{decision.request_id}_{timestamp}.json"
        
        with open(history_file, 'w') as f:
            json.dump(asdict(decision), f, indent=2)
    
    def _get_timestamp(self) -> str:
        """Get ISO timestamp."""
        return datetime.now(timezone.utc).isoformat() + 'Z'
