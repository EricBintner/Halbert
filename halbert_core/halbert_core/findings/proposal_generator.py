"""
Proposal generator — ties findings to proposals to approvals to execution.

For a given finding, generates a proposed config change, creates a dry-run
preview, calculates blast radius, creates a Proposal in the store, and
queues an ApprovalRequest in the approval engine (PENDING — the dashboard
user approves or rejects later via /api/approvals).

When the approval is decided (see handle_approval_decision):
- Approved → execute ALL changes. Config-file changes go through
  WriteConfig.execute(backup=True, dry_run=False, confirm=True); chmod
  changes are applied directly with drift detection, old-mode recording,
  and audit logging.
- Rejected → proposal marked rejected with the real reason, no changes.
- Execution failure → rollback of what was applied, proposal ROLLED_BACK.

Phase 5 / T5f.1.
"""

from __future__ import annotations

import logging
import os
import uuid
from typing import Any, Dict, List, Optional

from ..approval.engine import ApprovalEngine, ApprovalRequest
from ..tools.base import ToolRequest
from ..tools.write_config import WriteConfig
from .blast_radius import BlastRadiusCalculator
from .proposals import Proposal, ProposalStore, ProposalStatus
from .store import Finding, FindingStore, FindingStatus

logger = logging.getLogger(__name__)


def handle_approval_decision(
    request_id: str,
    approved: bool,
    reason: str = "",
    generator: Optional["ProposalGenerator"] = None,
) -> Dict[str, Any]:
    """Handle a decision made on an approval request.

    Looks up the proposal whose approval_request_id matches and either
    rejects it (recording the real reason) or executes its changes.

    Args:
        request_id: The approval request that was decided.
        approved: Whether the request was approved.
        reason: The decision reason (used as the rejection reason, or
            recorded alongside execution).
        generator: ProposalGenerator to use; constructed with default
            stores/tools when omitted (injectable for tests).

    Returns:
        A result dict describing what happened. ``{"linked": False, ...}``
        when no proposal references this approval request.
    """
    if generator is None:
        generator = ProposalGenerator(
            finding_store=FindingStore(),
            proposal_store=ProposalStore(),
            approval_engine=ApprovalEngine(),
            write_config=WriteConfig(),
            blast_radius=BlastRadiusCalculator(),
        )

    proposal = generator.proposals.find_by_approval_request(request_id)
    if proposal is None:
        logger.info(f"No proposal linked to approval request {request_id}")
        return {
            "linked": False,
            "request_id": request_id,
            "message": "no proposal linked to this approval request",
        }

    # Idempotency: a proposal that already reached a terminal status is not
    # re-executed (double-clicked approvals would otherwise re-apply changes
    # and overwrite the rollback backup with intermediate state).
    terminal = {
        ProposalStatus.APPLIED.value,
        ProposalStatus.ROLLED_BACK.value,
        ProposalStatus.REJECTED.value,
    }
    if proposal.status in terminal:
        logger.info(
            f"Proposal {proposal.id} already {proposal.status}; "
            f"ignoring duplicate decision for request {request_id}"
        )
        return {
            "linked": True,
            "request_id": request_id,
            "proposal_id": proposal.id,
            "status": proposal.status,
            "idempotent": True,
            "execution": proposal.execution_result or None,
        }

    if not approved:
        generator.proposals.reject(
            proposal.id, reason or "rejected by user"
        )
        logger.info(f"Proposal {proposal.id} rejected: {reason}")
        return {
            "linked": True,
            "request_id": request_id,
            "proposal_id": proposal.id,
            "status": ProposalStatus.REJECTED.value,
            "reason": reason or "rejected by user",
        }

    generator.proposals.approve(proposal.id, approval_request_id=request_id)
    return generator.execute_proposal(proposal.id, reason=reason)


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

        The proposal is created PENDING and its approval request is queued
        (also PENDING) for a dashboard decision — nothing is auto-approved
        or auto-rejected here.

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

        # Generate a dry-run preview covering every change
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

        # Queue an approval request (PENDING — decided via the dashboard)
        approval_req = ApprovalRequest(
            id=str(uuid.uuid4()),
            task="Apply config change",
            action=proposal.action,
            reasoning=finding.why_so,
            confidence=0.8,
            risk_level=finding.severity,
            system_state={"finding_id": finding_id, "proposal_id": proposal_id},
            affected_resources=blast + affected_paths,
            simulation_result=dry_run_result,
        )

        try:
            self.approvals.queue_request(approval_req)
            self.proposals.link_approval(proposal_id, approval_req.id)
            logger.info(
                f"Proposal {proposal_id} pending approval request {approval_req.id}"
            )
        except Exception as e:
            logger.warning(f"Approval queuing failed (non-fatal): {e}")
            # Proposal stays pending — an approval request can be queued later

        return proposal_id

    def execute_proposal(
        self, proposal_id: str, reason: str = ""
    ) -> Dict[str, Any]:
        """Execute ALL changes of an approved proposal.

        Config-file changes go through WriteConfig (backup=True,
        dry_run=False, confirm=True). chmod changes are applied directly
        with drift detection, old-mode recording for rollback, and audit
        logging. On any failure, already-applied changes are rolled back
        (WriteConfig rollback for files, os.chmod restore for modes) and
        the proposal is marked ROLLED_BACK with the error recorded. On
        full success the proposal is APPLIED and the linked finding is
        marked resolved.
        """
        proposal = self.proposals.get(proposal_id)
        if proposal is None:
            return {"proposal_id": proposal_id, "status": "not_found"}

        # Idempotent re-entry: never re-execute a finished proposal.
        if proposal.status in (
            ProposalStatus.APPLIED.value,
            ProposalStatus.ROLLED_BACK.value,
        ):
            logger.info(
                f"Proposal {proposal_id} already {proposal.status}; "
                "returning recorded result"
            )
            return {
                "linked": True,
                "proposal_id": proposal_id,
                "status": proposal.status,
                "idempotent": True,
                "execution": proposal.execution_result or None,
            }

        result: Dict[str, Any] = {
            "linked": True,
            "proposal_id": proposal_id,
            "applied": [],
            "skipped": [],
            "rolled_back": [],
            "error": None,
            "reason": reason,
        }

        if not proposal.changes:
            self.proposals.mark_applied(proposal_id)
            self._resolve_finding(proposal)
            result["status"] = ProposalStatus.APPLIED.value
            return self._record_result(proposal_id, result)

        applied: List[Dict[str, Any]] = []  # rollback info per applied change

        try:
            for change in proposal.changes:
                try:
                    outcome = self._apply_change(change)
                except Exception:
                    # The failing config-file change may be partially
                    # applied — add its path to the rollback set too.
                    if (
                        not change.get("requires_manual_review")
                        and change.get("action") != "chmod"
                        and change.get("path")
                    ):
                        applied.append({
                            "kind": "write_config",
                            "path": change["path"],
                        })
                    raise
                if outcome["status"] == "skipped":
                    result["skipped"].append(outcome)
                    continue
                if outcome["status"] == "manual_review":
                    result["skipped"].append(outcome)
                    continue
                applied.append(outcome["rollback"])
                result["applied"].append(outcome)
        except Exception as e:
            # Roll back everything applied so far (reverse order)
            result["error"] = str(e)
            logger.warning(
                f"Execution failed for proposal {proposal_id}: {e} — rolling back"
            )
            for rb in reversed(applied):
                try:
                    self._rollback_change(rb)
                    result["rolled_back"].append(rb)
                except Exception as rb_err:
                    logger.error(f"Rollback failed for {rb}: {rb_err}")
            self.proposals.mark_rolled_back(proposal_id)
            result["status"] = ProposalStatus.ROLLED_BACK.value
            return self._record_result(proposal_id, result)

        self.proposals.mark_applied(proposal_id)
        # Only resolve the finding when something actually changed — an
        # all-skipped execution (e.g. every chmod drifted) fixed nothing,
        # and the next detector sweep should legitimately re-surface it.
        if result["applied"]:
            self._resolve_finding(proposal)
        else:
            logger.info(
                f"Proposal {proposal_id} applied with no effective changes "
                "(all skipped); finding left open"
            )
        result["status"] = ProposalStatus.APPLIED.value
        logger.info(f"Proposal {proposal_id} applied successfully")
        return self._record_result(proposal_id, result)

    # ------------------------------------------------------------------
    # Change generation

    def _generate_changes(self, finding: Finding) -> List[Dict[str, Any]]:
        """Generate proposed config changes for a finding.

        This is a heuristic mapping from detector type to fix action.
        """
        changes: List[Dict[str, Any]] = []

        if finding.detector == "dropin_conflicts":
            # Propose removing the conflicting directive from the drop-in
            for path in finding.affected_paths:
                if ".d/" in path or "sshd_config.d" in path:
                    # This is a drop-in file — propose removing the conflict
                    changes.append({
                        "path": path,
                        "action": "remove_conflicting_directive",
                        "description": f"Remove or comment out the conflicting directive in {path}",
                        "requires_manual_review": True,
                    })

        elif finding.detector == "fstab_phantom":
            # Propose commenting out the phantom entry
            for path in finding.affected_paths:
                if path.endswith("fstab"):
                    changes.append({
                        "path": path,
                        "action": "comment_out_entry",
                        "description": "Comment out the fstab entry referencing the non-existent device",
                        "requires_manual_review": True,
                    })

        elif finding.detector == "permissions_hygiene":
            # Propose chmod to fix permissions
            for path in finding.affected_paths:
                if path.endswith(".ssh") and os.path.isdir(path):
                    changes.append(self._chmod_change(path, "700"))
                elif "id_" in path or "authorized_keys" in path:
                    changes.append(self._chmod_change(path, "600"))
                elif path.replace("\\", "/").endswith(".ssh/config"):
                    changes.append(self._chmod_change(path, "644"))

        return changes

    def _chmod_change(self, path: str, mode: str) -> Dict[str, Any]:
        """Build a chmod change dict, recording the current mode so
        execution-time drift (the file's mode having changed since the
        proposal was generated) can be detected."""
        change: Dict[str, Any] = {
            "path": path,
            "action": "chmod",
            "mode": mode,
            "description": f"chmod {mode} {path}",
        }
        try:
            current = os.stat(path).st_mode & 0o777
            change["expected_current_mode"] = oct(current)
        except OSError:
            pass  # no recorded expectation; drift check will be skipped
        return change

    def _describe_action(self, finding: Finding, changes: List[Dict[str, Any]]) -> str:
        """Generate a human-readable description of the proposed action."""
        if not changes:
            return "No changes proposed"
        first = changes[0]
        suffix = f" (+{len(changes) - 1} more)" if len(changes) > 1 else ""
        if first.get("action") == "chmod":
            base = f"Fix permissions: chmod {first['mode']} {first['path']}"
        elif first.get("action") == "remove_conflicting_directive":
            base = f"Remove conflicting directive in {first['path']}"
        elif first.get("action") == "comment_out_entry":
            base = f"Comment out phantom entry in {first['path']}"
        else:
            base = f"Apply config change to {first.get('path', 'unknown')}"
        return base + suffix

    # ------------------------------------------------------------------
    # Dry-run preview (covers every change)

    def _dry_run(self, changes: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Generate a dry-run preview covering ALL proposed changes."""
        if not changes:
            return None

        previews = [self._dry_run_change(c) for c in changes]
        return {
            "ok": all(p.get("ok", False) for p in previews),
            "changes": previews,
        }

    def _dry_run_change(self, change: Dict[str, Any]) -> Dict[str, Any]:
        """Dry-run preview for a single change."""
        action = change.get("action", "")
        path = change.get("path", "")
        if not path:
            return {"ok": False, "error": "no path", "change": change}

        try:
            if change.get("requires_manual_review"):
                # Actions that require manual review can't be auto-executed
                return {
                    "ok": True,
                    "outputs": {
                        "preview": change.get("description", action),
                        "requires_manual_review": True,
                    },
                }
            elif action == "chmod":
                # chmod actions don't use WriteConfig — just report what would happen
                if os.path.exists(path):
                    current_mode = os.stat(path).st_mode & 0o777
                    return {
                        "ok": True,
                        "outputs": {
                            "current_mode": oct(current_mode),
                            "target_mode": change.get("mode", "600"),
                            "preview": f"chmod {change['mode']} {path} (currently {oct(current_mode)})",
                        },
                    }
                else:
                    return {"ok": False, "error": f"File not found: {path}"}
            else:
                # Config file changes use WriteConfig
                config_changes = change.get("config_changes", {})
                req = ToolRequest(
                    tool="write_config",
                    dry_run=True,
                    confirm=False,
                    request_id=str(uuid.uuid4()),
                    inputs={
                        "path": path,
                        "changes": config_changes,
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

    # ------------------------------------------------------------------
    # Execution

    def _apply_change(self, change: Dict[str, Any]) -> Dict[str, Any]:
        """Apply a single change. Returns an outcome dict; raises on failure."""
        action = change.get("action", "")
        path = change.get("path", "")
        if not path:
            raise ValueError("change has no path")

        if change.get("requires_manual_review"):
            # Can't auto-execute — needs a human to edit the file
            logger.info(f"Change requires manual review — not auto-executing: {path}")
            return {
                "status": "manual_review",
                "path": path,
                "action": action,
                "message": "requires manual review",
            }

        if action == "chmod":
            return self._apply_chmod(change)

        return self._apply_config_change(change)

    def _apply_config_change(self, change: Dict[str, Any]) -> Dict[str, Any]:
        """Apply a config-file change through WriteConfig."""
        path = change["path"]
        req = ToolRequest(
            tool="write_config",
            dry_run=False,
            confirm=True,
            request_id=str(uuid.uuid4()),
            inputs={
                "path": path,
                "changes": change.get("config_changes", {}),
                "backup": True,
            },
        )
        resp = self.write_config.execute(req)
        if not resp.ok:
            raise RuntimeError(resp.error or f"write_config failed for {path}")
        return {
            "status": "applied",
            "path": path,
            "action": change.get("action", "config_change"),
            "rollback": {"kind": "write_config", "path": path},
        }

    def _apply_chmod(self, change: Dict[str, Any]) -> Dict[str, Any]:
        """Apply a chmod change with drift detection, old-mode recording,
        and audit logging."""
        from ..obs.audit import write_audit

        path = change["path"]
        mode_str = change.get("mode", "600")
        mode_int = int(mode_str, 8)
        request_id = str(uuid.uuid4())

        if not os.path.exists(path):
            write_audit(
                tool="chmod",
                mode="apply",
                request_id=request_id,
                ok=False,
                summary=f"file not found: {path}",
                path=path,
            )
            raise RuntimeError(f"File not found for chmod: {path}")

        current_mode = os.stat(path).st_mode & 0o777

        # Drift detection: skip if the mode changed since proposal generation
        expected = change.get("expected_current_mode")
        if expected and oct(current_mode) != expected:
            msg = (
                f"skipping chmod on {path}: current mode {oct(current_mode)} "
                f"differs from recorded expectation {expected} (drift)"
            )
            logger.warning(msg)
            write_audit(
                tool="chmod",
                mode="apply",
                request_id=request_id,
                ok=True,
                summary=msg,
                path=path,
            )
            return {
                "status": "skipped",
                "path": path,
                "action": "chmod",
                "message": msg,
            }

        already_ok = current_mode == mode_int
        old_mode = current_mode
        if not already_ok:
            os.chmod(path, mode_int)

        write_audit(
            tool="chmod",
            mode="apply",
            request_id=request_id,
            ok=True,
            summary=(
                f"chmod {mode_str} {path} (was {oct(old_mode)})"
                if not already_ok
                else f"no-op (already {mode_str}) for {path}"
            ),
            path=path,
        )
        return {
            "status": "applied",
            "path": path,
            "action": "chmod",
            "mode": mode_str,
            "old_mode": oct(old_mode),
            "rollback": {"kind": "chmod", "path": path, "old_mode": old_mode},
        }

    def _rollback_change(self, rollback: Dict[str, Any]) -> None:
        """Undo a previously applied change."""
        if rollback["kind"] == "chmod":
            os.chmod(rollback["path"], rollback["old_mode"])
            from ..obs.audit import write_audit

            write_audit(
                tool="chmod",
                mode="apply",
                request_id=str(uuid.uuid4()),
                ok=True,
                summary=f"rollback chmod on {rollback['path']} "
                f"(restored {oct(rollback['old_mode'])})",
                path=rollback["path"],
            )
        else:
            # Config-file change: restore from WriteConfig's backup
            req = ToolRequest(
                tool="write_config",
                dry_run=False,
                confirm=True,
                request_id=str(uuid.uuid4()),
                inputs={
                    "path": rollback["path"],
                    "rollback": True,
                },
            )
            resp = self.write_config.execute(req)
            if not resp.ok:
                raise RuntimeError(resp.error or "write_config rollback failed")

    def _resolve_finding(self, proposal: Proposal) -> None:
        """Mark the finding linked to this proposal as resolved."""
        try:
            self.findings.update_status(
                proposal.finding_id, FindingStatus.RESOLVED.value
            )
        except Exception as e:
            logger.warning(
                f"Could not mark finding {proposal.finding_id} resolved: {e}"
            )

    def _record_result(
        self, proposal_id: str, result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Persist the execution result on the proposal (best effort)."""
        try:
            self.proposals.update_status(
                proposal_id, result["status"], execution_result=result
            )
        except Exception as e:
            logger.warning(f"Could not record execution result on {proposal_id}: {e}")
        return result
