"""
Approval management API routes.
"""

from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any
from pydantic import BaseModel

router = APIRouter()


class ApprovalDecisionRequest(BaseModel):
    """Request to approve/reject."""
    approved: bool
    reason: str | None = None


@router.get("")
async def list_pending_approvals() -> List[Dict[str, Any]]:
    """
    Get all pending approval requests.
    
    Returns list of requests awaiting user decision.
    """
    try:
        from ...approval.engine import ApprovalEngine
        
        engine = ApprovalEngine()
        pending = engine.get_pending_requests()
        
        return [
            {
                'id': req.id,
                'task': req.task,
                'action': req.action,
                'reasoning': req.reasoning,
                'confidence': req.confidence,
                'risk_level': req.risk_level,
                'system_state': req.system_state,
                'affected_resources': req.affected_resources,
                'simulation_result': req.simulation_result,
                'requested_at': req.requested_at
            }
            for req in pending
        ]
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{request_id}")
async def get_approval_details(request_id: str) -> Dict[str, Any]:
    """Get detailed information about an approval request."""
    try:
        from ...approval.engine import ApprovalEngine
        
        engine = ApprovalEngine()
        request = engine.get_request(request_id)
        
        if not request:
            raise HTTPException(status_code=404, detail="Request not found")
        
        return {
            'id': request.id,
            'task': request.task,
            'action': request.action,
            'reasoning': request.reasoning,
            'confidence': request.confidence,
            'risk_level': request.risk_level,
            'system_state': request.system_state,
            'affected_resources': request.affected_resources,
            'simulation_result': request.simulation_result,
            'status': request.status,
            'requested_at': request.requested_at,
            'approved_at': request.approved_at,
            'rejected_at': request.rejected_at,
            'rejection_reason': request.rejection_reason
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{request_id}/approve")
async def approve_request(request_id: str, body: ApprovalDecisionRequest):
    """
    Approve an approval request.
    
    This will allow the autonomous action to proceed.
    """
    try:
        from ...approval.engine import ApprovalEngine, ApprovalDecision
        from datetime import datetime, timezone
        
        engine = ApprovalEngine()
        request = engine.get_request(request_id)
        
        if not request:
            raise HTTPException(status_code=404, detail="Request not found")
        
        if request.status != 'pending':
            raise HTTPException(status_code=400, detail=f"Request already {request.status}")
        
        # Create decision
        decision = ApprovalDecision(
            request_id=request_id,
            approved=True,
            reason=body.reason,
            decided_by='dashboard_user',
            decided_at=datetime.now(timezone.utc).isoformat() + 'Z'
        )
        
        # Update request
        request.status = 'approved'
        request.approved_at = decision.decided_at
        request.approved_by = decision.decided_by
        
        # Save
        engine._save_request(request)
        engine._save_decision(decision)
        
        # Broadcast to WebSocket clients
        await engine.app.state.ws_manager.broadcast({
            'type': 'approval_decision',
            'data': {
                'request_id': request_id,
                'approved': True
            }
        })
        
        return {
            'success': True,
            'message': 'Request approved',
            'request_id': request_id
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{request_id}/reject")
async def reject_request(request_id: str, body: ApprovalDecisionRequest):
    """
    Reject an approval request.
    
    This will cancel the autonomous action.
    """
    try:
        from ...approval.engine import ApprovalEngine, ApprovalDecision
        from datetime import datetime, timezone
        
        engine = ApprovalEngine()
        request = engine.get_request(request_id)
        
        if not request:
            raise HTTPException(status_code=404, detail="Request not found")
        
        if request.status != 'pending':
            raise HTTPException(status_code=400, detail=f"Request already {request.status}")
        
        # Create decision
        decision = ApprovalDecision(
            request_id=request_id,
            approved=False,
            reason=body.reason or "User declined",
            decided_by='dashboard_user',
            decided_at=datetime.now(timezone.utc).isoformat() + 'Z'
        )
        
        # Update request
        request.status = 'rejected'
        request.rejected_at = decision.decided_at
        request.rejection_reason = decision.reason
        
        # Save
        engine._save_request(request)
        engine._save_decision(decision)
        
        return {
            'success': True,
            'message': 'Request rejected',
            'request_id': request_id
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history")
async def get_approval_history(
    limit: int = 100,
    approved_only: bool = False
) -> List[Dict[str, Any]]:
    """Get approval decision history."""
    try:
        from ...approval.engine import ApprovalEngine
        
        engine = ApprovalEngine()
        history = engine.get_approval_history(limit=limit, approved_only=approved_only)
        
        return history
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
