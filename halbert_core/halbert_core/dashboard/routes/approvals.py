# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Approval management API routes.
"""

import asyncio
import logging
from fastapi import APIRouter, HTTPException, Request
from typing import List, Dict, Any, Optional
from pydantic import BaseModel

logger = logging.getLogger('halbert.dashboard.routes.approvals')

router = APIRouter()


class ApprovalDecisionRequest(BaseModel):
    """Request to approve/reject."""
    approved: bool
    reason: str | None = None


def _utc_now() -> str:
    """Proper UTC ISO timestamp ('Z' style, never '+00:00Z')."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def _ws_manager(request: Request):
    """Get the WebSocket connection manager from app state, if present."""
    return getattr(request.app.state, 'ws_manager', None)


async def _broadcast(ws_manager, payload: Dict[str, Any]) -> None:
    """Broadcast to WebSocket clients, skipping cleanly when unavailable."""
    if ws_manager is None:
        return
    try:
        await ws_manager.broadcast(payload)
    except Exception as e:
        logger.warning(f"WebSocket broadcast failed (non-fatal): {e}")


def _handle_proposal_decision(request_id: str, approved: bool, reason: str) -> Dict[str, Any]:
    """Forward the decision to the proposal pipeline.

    Lazily imported — findings modules are optional for the dashboard.
    Returns the result dict; tolerant no-op when no proposal is linked.
    """
    try:
        from ...findings.proposal_generator import handle_approval_decision
        return handle_approval_decision(request_id, approved, reason)
    except Exception as e:
        logger.warning(f"Proposal decision handling failed (non-fatal): {e}")
        return {"linked": None, "error": str(e)}


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


@router.get("/proposals")
async def list_pending_proposals() -> List[Dict[str, Any]]:
    """List pending proposals joined with their findings.

    NOTE: registered before /{request_id} so the literal path wins.
    """
    try:
        from ...findings.proposals import ProposalStore
        from ...findings.store import FindingStore

        proposal_store = ProposalStore()
        finding_store = FindingStore(db_path=proposal_store.db_path)

        results = []
        for proposal in proposal_store.list_pending():
            finding = (
                finding_store.get(proposal.finding_id)
                if proposal.finding_id
                else None
            )
            # Self-heal orphaned proposals: if the approval request failed
            # to queue at generation time (approval_request_id empty), the
            # proposal could never be decided — re-queue it now.
            if not proposal.approval_request_id:
                try:
                    import uuid
                    from ...approval.engine import ApprovalEngine, ApprovalRequest

                    engine = ApprovalEngine()
                    req = ApprovalRequest(
                        id=str(uuid.uuid4()),
                        task="Apply config change",
                        action=proposal.action,
                        reasoning=finding.why_so if finding else "",
                        confidence=0.8,
                        risk_level=finding.severity if finding else "medium",
                        system_state={
                            "finding_id": proposal.finding_id,
                            "proposal_id": proposal.id,
                        },
                        affected_resources=proposal.blast_radius,
                        simulation_result=proposal.dry_run_result,
                    )
                    engine.queue_request(req)
                    proposal_store.link_approval(proposal.id, req.id)
                    proposal.approval_request_id = req.id
                    logger.info(
                        f"Re-queued orphaned proposal {proposal.id} "
                        f"as approval request {req.id}"
                    )
                except Exception as e:
                    logger.warning(
                        f"Could not re-queue proposal {proposal.id}: {e}"
                    )
            changes_summary = [
                {
                    "path": c.get("path"),
                    "action": c.get("action"),
                    "description": c.get("description", ""),
                }
                for c in proposal.changes
            ]
            results.append({
                "id": proposal.id,
                "finding_id": proposal.finding_id,
                "finding_title": finding.title if finding else None,
                "finding_severity": finding.severity if finding else None,
                "action": proposal.action,
                "changes": changes_summary,
                "blast_radius": proposal.blast_radius,
                "dry_run_result": proposal.dry_run_result,
                "approval_request_id": proposal.approval_request_id,
                "created_at": proposal.created_at,
            })
        return results

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
async def approve_request(request_id: str, body: ApprovalDecisionRequest, request: Request):
    """
    Approve an approval request.

    Saves the decision, then hands it to the proposal pipeline (if a
    proposal is linked) which executes the approved changes. Broadcasts
    the decision and execution outcome over WebSocket when available.
    """
    try:
        from ...approval.engine import ApprovalEngine, ApprovalDecision

        engine = ApprovalEngine()
        approval_req = engine.get_request(request_id)

        if not approval_req:
            raise HTTPException(status_code=404, detail="Request not found")

        if approval_req.status != 'pending':
            raise HTTPException(status_code=400, detail=f"Request already {approval_req.status}")

        # Create decision
        decision = ApprovalDecision(
            request_id=request_id,
            approved=True,
            reason=body.reason,
            decided_by='dashboard_user',
            decided_at=_utc_now()
        )

        # Update request
        approval_req.status = 'approved'
        approval_req.approved_at = decision.decided_at
        approval_req.approved_by = decision.decided_by

        # Save
        engine._save_request(approval_req)
        engine._save_decision(decision)

        ws_manager = _ws_manager(request)

        # Broadcast decision to WebSocket clients (skipped when absent)
        await _broadcast(ws_manager, {
            'type': 'approval_decision',
            'data': {
                'request_id': request_id,
                'approved': True
            }
        })

        # Hand the decision to the proposal pipeline (no-op if unlinked).
        # Execution does config writes / chmods / SQLite — keep the event
        # loop free by running it in a worker thread.
        proposal_result = await asyncio.to_thread(
            _handle_proposal_decision,
            request_id, True, body.reason or ""
        )

        # Broadcast execution outcome too
        await _broadcast(ws_manager, {
            'type': 'proposal_execution',
            'data': {
                'request_id': request_id,
                'result': proposal_result,
            }
        })

        return {
            'success': True,
            'message': 'Request approved',
            'request_id': request_id,
            'proposal': proposal_result,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{request_id}/reject")
async def reject_request(request_id: str, body: ApprovalDecisionRequest, request: Request):
    """
    Reject an approval request.

    Saves the decision with the real reason and hands it to the proposal
    pipeline (if a proposal is linked) so the proposal is marked rejected.
    """
    try:
        from ...approval.engine import ApprovalEngine, ApprovalDecision

        engine = ApprovalEngine()
        approval_req = engine.get_request(request_id)

        if not approval_req:
            raise HTTPException(status_code=404, detail="Request not found")

        if approval_req.status != 'pending':
            raise HTTPException(status_code=400, detail=f"Request already {approval_req.status}")

        # Create decision
        decision = ApprovalDecision(
            request_id=request_id,
            approved=False,
            reason=body.reason or "User declined",
            decided_by='dashboard_user',
            decided_at=_utc_now()
        )

        # Update request
        approval_req.status = 'rejected'
        approval_req.rejected_at = decision.decided_at
        approval_req.rejection_reason = decision.reason

        # Save
        engine._save_request(approval_req)
        engine._save_decision(decision)

        ws_manager = _ws_manager(request)

        # Broadcast decision (skipped when no ws_manager)
        await _broadcast(ws_manager, {
            'type': 'approval_decision',
            'data': {
                'request_id': request_id,
                'approved': False,
                'reason': decision.reason,
            }
        })

        # Hand the decision to the proposal pipeline (no-op if unlinked).
        # Off the event loop — same reason as in approve_request.
        proposal_result = await asyncio.to_thread(
            _handle_proposal_decision,
            request_id, False, decision.reason or ""
        )

        return {
            'success': True,
            'message': 'Request rejected',
            'request_id': request_id,
            'proposal': proposal_result,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
