# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""SomaticLifecycle (C1b).

Drives a SomaticBlock through its 5 phases by *calling* the existing modules —
it does NOT replace them:

- advance_to_proposal  -> ProposalGenerator.generate_for_finding() (creates
  Proposal + ApprovalRequest, both PENDING) and records the ids on the block.
- advance_to_action    -> findings.proposal_generator.handle_approval_decision()
  (approves+executes or rejects, with rollback on failure).
- advance_to_sensory / advance_to_deliberation / advance_to_reflection are
  status transitions that record metadata on the block.

The lifecycle is async so it slots into the agent state machine (C1d), even
though the wrapped ProposalGenerator methods are currently synchronous.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable, Dict, List, Optional

from .block import BlockStatus, BlockType, SomaticBlock
from .store import SomaticStore
from .checkpoints import CheckpointManager

logger = logging.getLogger("halbert.somatic.lifecycle")


def _summarize(value: Any, max_chars: int = 500) -> Any:
    """Coerce a value to a JSON-safe, length-bounded summary for block metadata."""
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        s = str(value)
        return s if len(s) <= max_chars else s[:max_chars] + "..."
    if isinstance(value, dict):
        return {str(k): _summarize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_summarize(v) for v in value][:50]
    return str(value)[:max_chars]


def _handle_approval_decision_default(
    request_id: str, approved: bool, reason: str = "",
    generator: Optional[Any] = None,
) -> Dict[str, Any]:
    # Late import so the somatic package stays importable without the
    # findings/approval packages loaded at module import time.
    from ..findings.proposal_generator import handle_approval_decision
    return handle_approval_decision(request_id, approved, reason, generator=generator)


class SomaticLifecycle:
    """Orchestrates a SomaticBlock through its phases, wrapping existing modules."""

    def __init__(
        self,
        store: SomaticStore,
        proposal_generator: Any,
        approval_engine: Optional[Any] = None,
        recovery_executor: Optional[Any] = None,
        guardrail_enforcer: Optional[Any] = None,
        handle_approval_decision: Callable = _handle_approval_decision_default,
        checkpoints: Optional[CheckpointManager] = None,
    ):
        self.store = store
        self.generator = proposal_generator
        self.approvals = approval_engine or getattr(proposal_generator, "approvals", None)
        self.recovery_executor = recovery_executor
        self.guardrail_enforcer = guardrail_enforcer
        self._handle_approval_decision = handle_approval_decision
        self.checkpoints = checkpoints if checkpoints is not None else CheckpointManager()

    # ------------------------------------------------------------------
    # Phases
    # ------------------------------------------------------------------

    async def advance_to_sensory(
        self,
        block: SomaticBlock,
        finding_id: Optional[str] = None,
        detector_output: Optional[Any] = None,
    ) -> SomaticBlock:
        """A finding was raised (by detectors, externally). Record it on the block."""
        block.block_type = BlockType.SENSORY
        block.status = BlockStatus.DETECTED
        if finding_id:
            block.finding_id = finding_id
        if detector_output is not None:
            block.metadata["detector_output"] = _summarize(detector_output)
        self._persist(block, finding_id=block.finding_id)
        return block

    async def advance_to_deliberation(
        self,
        block: SomaticBlock,
        cognitive_tick_output: Optional[Any] = None,
    ) -> SomaticBlock:
        """Cognitive tick considered the finding."""
        block.block_type = BlockType.DELIBERATION
        block.status = BlockStatus.DELIBERATING
        if cognitive_tick_output is not None:
            block.metadata["deliberation"] = _summarize(cognitive_tick_output)
        self._persist(block)
        return block

    async def advance_to_proposal(self, block: SomaticBlock) -> SomaticBlock:
        """Generate a proposal + approval request for the block's finding.

        Calls ``ProposalGenerator.generate_for_finding(finding_id)`` (existing)
        and records proposal_id + approval_request_id on the block. If no fix
        can be generated, the block is rejected.
        """
        block.block_type = BlockType.PROPOSAL
        if not block.finding_id:
            raise ValueError("advance_to_proposal requires block.finding_id")

        proposal_id = self.generator.generate_for_finding(block.finding_id)
        if not proposal_id:
            logger.info(f"No proposal generated for finding {block.finding_id}")
            block.status = BlockStatus.REJECTED
            block.metadata["proposal_result"] = "no_fix_available"
            self._persist(block)
            return block

        proposal = self.generator.proposals.get(proposal_id)
        approval_request_id = getattr(proposal, "approval_request_id", None) if proposal else None

        block.proposal_id = proposal_id
        block.approval_request_id = approval_request_id
        block.status = BlockStatus.PENDING_APPROVAL
        self._persist(
            block,
            proposal_id=proposal_id,
            approval_request_id=approval_request_id,
        )
        return block

    async def advance_to_action(
        self, block: SomaticBlock, approved: bool, reason: str = ""
    ) -> SomaticBlock:
        """Execute or reject the proposal via the existing approval flow.

        Calls ``handle_approval_decision(request_id, approved, reason,
        generator=...)`` which executes the changes (with rollback on failure)
        or rejects the proposal. Maps the result status onto the block.
        """
        block.block_type = BlockType.ACTION
        if not block.approval_request_id:
            raise ValueError("advance_to_action requires block.approval_request_id")

        block.status = BlockStatus.EXECUTING
        self._persist(block)

        # Checkpoint affected files before executing so a failed/rolled-back
        # action can be undone (C1c). Best-effort: no paths -> nothing saved.
        affected = []
        if approved:
            affected = self._affected_paths(block)
            if affected:
                self.checkpoints.checkpoint_many(affected)

        result = self._handle_approval_decision(
            block.approval_request_id, approved, reason, generator=self.generator
        )
        block.metadata["execution"] = _summarize(result)

        status_str = str(result.get("status") or "").lower()
        if approved and status_str == "applied":
            block.status = BlockStatus.COMPLETED
            block.action_id = result.get("proposal_id") or block.proposal_id
        elif approved and status_str == "rolled_back":
            block.status = BlockStatus.ROLLED_BACK
            # Execution failed and rolled back via WriteConfig; also restore
            # our checkpoints as a belt-and-suspenders undo (C1c).
            if affected:
                self.checkpoints.rollback_many(affected)
        elif not approved:
            block.status = BlockStatus.REJECTED
        else:
            # approved but unclear result -> rolled back (safe default)
            block.status = BlockStatus.ROLLED_BACK
            if affected:
                self.checkpoints.rollback_many(affected)

        self._persist(block, action_id=block.action_id)
        return block

    async def advance_to_reflection(
        self, block: SomaticBlock, tick_output: Optional[Any] = None
    ) -> SomaticBlock:
        """Record post-action reflection and mark the block complete."""
        block.block_type = BlockType.REFLECTION
        if tick_output is not None:
            block.metadata["reflection"] = _summarize(tick_output)
        if not block.status.is_terminal():
            block.status = BlockStatus.COMPLETED
        self._persist(block)
        return block

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _persist(self, block: SomaticBlock, **link_ids: Optional[str]) -> None:
        """Write the full block (status, link ids, metadata) to the store."""
        block.updated_at = time.time()
        # link_ids are already set on the in-memory block; save() upserts all.
        self.store.save(block)

    def _affected_paths(self, block: SomaticBlock) -> List[str]:
        """Best-effort extraction of file paths a proposal will modify.

        Prefers the finding's ``affected_paths``; falls back to path-like keys
        in the proposal's ``changes``. Returns [] if nothing is determinable.
        """
        paths: List[str] = []
        seen = set()
        # 1. finding.affected_paths
        finding = None
        if block.finding_id and hasattr(self.generator, "findings"):
            try:
                finding = self.generator.findings.get(block.finding_id)
            except Exception:
                finding = None
        if finding is not None:
            for p in getattr(finding, "affected_paths", None) or []:
                if p and p not in seen:
                    seen.add(p)
                    paths.append(p)
        # 2. proposal.changes path-like keys
        proposal = None
        if block.proposal_id and hasattr(self.generator, "proposals"):
            try:
                proposal = self.generator.proposals.get(block.proposal_id)
            except Exception:
                proposal = None
        if proposal is not None:
            for change in getattr(proposal, "changes", None) or []:
                if not isinstance(change, dict):
                    continue
                for key in ("path", "file", "target", "file_path"):
                    p = change.get(key)
                    if p and p not in seen:
                        seen.add(p)
                        paths.append(p)
        return paths
