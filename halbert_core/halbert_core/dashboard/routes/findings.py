# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Findings routes — the attention surface's reader and its "propose fix" path.

A Finding is the unit of attention (C2-03): it carries the four whys
(why now / why care / why so / why trust) and the paths it touches. This
module is the single reader the Findings page, the bell and the MCP
``get_findings`` tool share, plus the manual finding -> proposal joint
(J3-7) for detectors whose fix the user asks for rather than gets at
detection time.

Provides (mounted under /api in app.py):
- GET  /api/findings?status=open|snoozed|resolved|dismissed|all
- GET  /api/findings/{finding_id}
- POST /api/findings/{finding_id}/propose

Store/generator construction goes through the module-level factories so
tests can point the routes at a temporary database without a hand-built
app; everything else is the real code path.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query

from ...findings.proposals import ProposalStore
from ...findings.store import FindingStore, Finding, FindingStatus

logger = logging.getLogger("halbert.dashboard.findings")

router = APIRouter()


# ---------------------------------------------------------------------------
# Factories (patched in tests)


def _finding_store() -> FindingStore:
    return FindingStore()


def _proposal_store() -> ProposalStore:
    return ProposalStore()


def _proposal_generator(finding_store: FindingStore, proposal_store: ProposalStore):
    """Build the real ProposalGenerator over the given stores.

    Mirrors the construction in mcp/server.py: each route call builds its
    own ApprovalEngine (it persists to disk, so the queued request is the
    same one /api/approvals reads back).
    """
    from ...approval.engine import ApprovalEngine
    from ...findings.blast_radius import BlastRadiusCalculator
    from ...findings.proposal_generator import ProposalGenerator
    from ...tools.write_config import WriteConfig

    return ProposalGenerator(
        finding_store=finding_store,
        proposal_store=proposal_store,
        approval_engine=ApprovalEngine(),
        write_config=WriteConfig(),
        blast_radius=BlastRadiusCalculator(),
    )


# ---------------------------------------------------------------------------
# Serialisation


def _finding_payload(finding: Finding) -> Dict[str, Any]:
    d = finding.to_dict()
    # Transient event payload — never persisted, never on this surface.
    d.pop("data", None)
    return d


# ---------------------------------------------------------------------------
# Routes


@router.get("/findings")
def list_findings(
    status: str = Query("open", description="open | snoozed | resolved | dismissed | all"),
    limit: int = Query(100, ge=0, le=500),
):
    """List findings with their four whys, newest first (default: open)."""
    store = _finding_store()
    try:
        findings = store.list_findings(status=status, limit=limit)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    payload = [_finding_payload(f) for f in findings]
    return {"status": "ok", "findings": payload, "count": len(payload)}


@router.get("/findings/{finding_id}")
def get_finding(finding_id: str):
    """One finding plus its linked proposal, when it has one."""
    store = _finding_store()
    finding = store.get(finding_id)
    if finding is None:
        raise HTTPException(status_code=404, detail="Finding not found")
    proposal: Optional[Dict[str, Any]] = None
    if finding.proposal_id:
        row = _proposal_store().get(finding.proposal_id)
        proposal = row.to_dict() if row else None
    return {"status": "ok", "finding": _finding_payload(finding), "proposal": proposal}


@router.post("/findings/{finding_id}/propose")
def propose_fix(finding_id: str):
    """Generate the proposal (and queue its approval) for a finding.

    404 unknown finding; 409 when the finding already has a proposal or is
    no longer actionable (resolved / dismissed); 422 when the generator has
    no automatic fix for this detector.
    """
    fs = _finding_store()
    ps = _proposal_store()
    finding = fs.get(finding_id)
    if finding is None:
        raise HTTPException(status_code=404, detail="Finding not found")
    if finding.proposal_id:
        raise HTTPException(
            status_code=409,
            detail=f"Finding already has proposal {finding.proposal_id}",
        )
    if finding.status in (FindingStatus.RESOLVED.value, FindingStatus.DISMISSED.value):
        raise HTTPException(
            status_code=409,
            detail=f"Finding is {finding.status}; nothing to propose",
        )

    generator = _proposal_generator(fs, ps)
    try:
        proposal_id = generator.generate_for_finding(finding_id)
    except Exception as e:
        logger.warning(f"Proposal generation failed for {finding_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Proposal generation failed: {e}")
    if not proposal_id:
        raise HTTPException(
            status_code=422,
            detail="No automatic fix is available for this finding",
        )
    proposal = ps.get(proposal_id)
    return {
        "status": "ok",
        "finding_id": finding_id,
        "proposal": proposal.to_dict() if proposal else {"id": proposal_id},
    }
