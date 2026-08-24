"""
Proposal generator — ties findings to proposals to approvals to execution.

For a given finding, generates a proposed config change, creates a dry-run
preview, calculates blast radius, creates a Proposal in the store, and
creates an ApprovalRequest via the approval engine.

When the approval is decided:
- Approved → execute via WriteConfig with backup=True, dry_run=False
- Rejected → update proposal status, no changes applied
- Execution failure → auto-rollback, proposal marked ROLLED_BACK

Phase 5 / T5f.1.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, Optional

from ..approval.engine import ApprovalEngine, ApprovalRequest
from ..tools.base import ToolRequest
from ..tools.write_config import WriteConfig
from .blast_radius import BlastRadiusCalculator
from .proposals import Proposal, ProposalStore, ProposalStatus
from .store import Finding, FindingStore, FindingStatus

logger = logging.getLogger(__name__)


class ProposalGenerator:
    """Generate and execute config change proposals for findings."""

    def __init__(
        self,
        finding_store: FindingStore,
        proposal_store: ProposalStore,
        approval_engine: ApprovalEngine,
        write_config: WriteConfig,
        blast_radius: BlastRadiusCalculator,
    ):
        self.findings = finding_store
        self.proposals = proposal_store
        self.approvals = approval_engine
        self.write_config = write_config
        self.blast = blast_radius

    def generate_for_finding(self, finding_id: str) -> Optional[str]:
        """Generate a proposal for a finding.

        Args:
            finding_id: The finding to propose a fix for.

        Returns:
            The proposal ID if created, None if no fix could be generated.
        """
        finding = self.findings.get(finding_id)
        if not finding:
            logger.warning(f"Finding {finding_id} not found")
            return None

        # Generate the proposed changes based on the detector
        changes = self._generate_changes(finding)
        if not changes:
            logger.info(f"No automatic fix for finding {finding_id} ({finding.detector})")
            return None

        # Generate a dry-run preview
        dry_run_result = self._dry_run(changes)
        if dry_run_result is None:
            dry_run_result = {"error": "dry-run failed"}

        # Calculate blast radius
        affected_paths = finding.affected_paths
        blast = self.blast.calculate_multi(affected_paths)

        # Create the proposal
        proposal = Proposal(
            id="",
            finding_id=finding_id,
            action=self._describe_action(finding, changes),
            changes=changes,
            dry_run_result=dry_run_result,
            blast_radius=blast,
        )
        proposal_id = self.proposals.add(proposal)

        # Link proposal to finding
        self.findings.link_proposal(finding_id, proposal_id)

        # Create an approval request
        approval_req = ApprovalRequest(
            id=str(uuid.uuid4()),
            task=f"Apply config change for: {finding.title}",
            action=proposal.action,
            reasoning=finding.why_so,
            confidence=0.8,
            risk_level=finding.severity,
            system_state={"finding_id": finding_id, "proposal_id": proposal_id},
            affected_resources=blast + affected_paths,
            simulation_result=dry_run_result,
        )

        try:
            decision = self.approvals.request_approval(
                approval_req, mode="dashboard"
            )
            # Update proposal based on decision
            if decision.approved:
                self.proposals.approve(proposal_id, approval_request_id=approval_req.id)
                logger.info(f"Proposal {proposal_id} approved — executing")
                self._execute(proposal_id, changes)
            else:
                self.proposals.reject(proposal_id, decision.reason or "rejected by user")
                logger.info(f"Proposal {proposal_id} rejected: {decision.reason}")
        except Exception as e:
            logger.warning(f"Approval flow failed (non-fatal): {e}")
            # Proposal stays pending — can be approved later

        return proposal_id

    def _generate_changes(self, finding: Finding) -> list[Dict[str, Any]]:
        """Generate proposed config changes for a finding.

        This is a heuristic mapping from detector type to fix action.
        """
        changes: list[Dict[str, Any]] = []

        if finding.detector == "dropin_conflicts":
            # Propose removing the conflicting directive from the drop-in
            for path in finding.affected_paths:
                if ".d/" in path or "sshd_config.d" in path:
                    # This is a drop-in file — propose removing the conflict
                    changes.append({
                        "path": path,
                        "action": "remove_conflicting_directive",
                        "description": f"Remove or comment out the conflicting directive in {path}",
                    })

        elif finding.detector == "fstab_phantom":
            # Propose commenting out the phantom entry
            for path in finding.affected_paths:
                if path.endswith("fstab"):
                    changes.append({
                        "path": path,
                        "action": "comment_out_entry",
                        "description": "Comment out the fstab entry referencing the non-existent device",
                    })

        elif finding.detector == "permissions_hygiene":
            # Propose chmod to fix permissions
            for path in finding.affected_paths:
                if ".ssh" in path and path.endswith(".ssh"):
                    changes.append({
                        "path": path,
                        "action": "chmod",
                        "mode": "700",
                        "description": f"chmod 700 {path}",
                    })
                elif "id_" in path or "authorized_keys" in path:
                    changes.append({
                        "path": path,
                        "action": "chmod",
                        "mode": "600",
                        "description": f"chmod 600 {path}",
                    })

        return changes

    def _describe_action(self, finding: Finding, changes: list[Dict[str, Any]]) -> str:
        """Generate a human-readable description of the proposed action."""
        if not changes:
            return "No changes proposed"
        first = changes[0]
        if first.get("action") == "chmod":
            return f"Fix permissions: chmod {first['mode']} {first['path']}"
        elif first.get("action") == "remove_conflicting_directive":
            return f"Remove conflicting directive in {first['path']}"
        elif first.get("action") == "comment_out_entry":
            return f"Comment out phantom entry in {first['path']}"
        return f"Apply config change to {first.get('path', 'unknown')}"

    def _dry_run(self, changes: list[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Generate a dry-run preview of the changes."""
        if not changes:
            return None

        first = changes[0]
        path = first.get("path", "")
        if not path:
            return None

        try:
            req = ToolRequest(
                tool="write_config",
                dry_run=True,
                confirm=False,
                request_id=str(uuid.uuid4()),
                inputs={
                    "path": path,
                    "changes": first,
                    "backup": True,
                },
            )
            resp = self.write_config.execute(req)
            return {
                "ok": resp.ok,
                "outputs": resp.outputs,
                "error": resp.error,
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _execute(self, proposal_id: str, changes: list[Dict[str, Any]]) -> None:
        """Execute the proposed changes (after approval)."""
        if not changes:
            return

        first = changes[0]
        path = first.get("path", "")
        if not path:
            return

        try:
            req = ToolRequest(
                tool="write_config",
                dry_run=False,
                confirm=True,
                request_id=str(uuid.uuid4()),
                inputs={
                    "path": path,
                    "changes": first,
                    "backup": True,
                },
            )
            resp = self.write_config.execute(req)

            if resp.ok:
                self.proposals.mark_applied(proposal_id)
                logger.info(f"Proposal {proposal_id} applied successfully")
            else:
                # Attempt rollback
                logger.warning(f"Apply failed for {proposal_id}: {resp.error}")
                rollback_req = ToolRequest(
                    tool="write_config",
                    dry_run=False,
                    confirm=True,
                    request_id=str(uuid.uuid4()),
                    inputs={
                        "path": path,
                        "rollback": True,
                    },
                )
                self.write_config.execute(rollback_req)
                self.proposals.mark_rolled_back(proposal_id)
                logger.info(f"Proposal {proposal_id} rolled back")
        except Exception as e:
            logger.error(f"Execution error for {proposal_id}: {e}")
            self.proposals.mark_rolled_back(proposal_id)
