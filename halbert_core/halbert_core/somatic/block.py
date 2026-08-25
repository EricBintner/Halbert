"""SomaticBlock dataclass + status/type enums (C1a).

A SomaticBlock is the wrapper that drives one self-management cycle. It
references the existing models by id rather than embedding them:

- ``finding_id``         -> findings.store.Finding.id
- ``proposal_id``        -> findings.proposals.Proposal.id
- ``approval_request_id``-> approval.engine.ApprovalRequest.id
- ``action_id``          -> the executed change record id
- ``reflection_id``      -> the post-action reflection record id

The existing models stay in their modules; SomaticLifecycle (C1b) calls them.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional

__all__ = ["BlockType", "BlockStatus", "SomaticBlock"]


class BlockType(Enum):
    """The 5 phases of a somatic cycle."""
    SENSORY = "sensory"            # detector output -> a finding was raised
    DELIBERATION = "deliberation"  # cognitive tick considered it
    PROPOSAL = "proposal"          # a fix was proposed + approval requested
    ACTION = "action"              # the approved change was executed
    REFLECTION = "reflection"      # post-action reflection recorded


class BlockStatus(Enum):
    """Lifecycle status of a somatic block."""
    DETECTED = "detected"
    DELIBERATING = "deliberating"
    PROPOSED = "proposed"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    EXECUTING = "executing"
    COMPLETED = "completed"
    ROLLED_BACK = "rolled_back"
    REJECTED = "rejected"

    @classmethod
    def terminal(cls) -> tuple:
        """Statuses that end the block's lifecycle."""
        return (cls.COMPLETED, cls.ROLLED_BACK, cls.REJECTED)

    def is_terminal(self) -> bool:
        return self in self.terminal()


@dataclass
class SomaticBlock:
    """A single self-management cycle wrapper.

    The optional ``*_id`` fields are foreign keys into the existing modules,
    filled in as the lifecycle advances. ``metadata`` carries anything the
    lifecycle or UI needs that doesn't deserve a column.
    """
    id: str
    block_type: BlockType
    status: BlockStatus
    session_id: str
    finding_id: Optional[str] = None
    proposal_id: Optional[str] = None
    approval_request_id: Optional[str] = None
    action_id: Optional[str] = None
    reflection_id: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def new(
        cls,
        block_type: BlockType,
        session_id: str,
        status: BlockStatus = BlockStatus.DETECTED,
        **kwargs: Any,
    ) -> "SomaticBlock":
        """Create a block with a fresh id."""
        now = time.time()
        return cls(
            id=str(uuid.uuid4()),
            block_type=block_type,
            status=status,
            session_id=session_id,
            created_at=now,
            updated_at=now,
            **kwargs,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize for storage / SSE. Enums become their string values."""
        return {
            "id": self.id,
            "block_type": self.block_type.value,
            "status": self.status.value,
            "session_id": self.session_id,
            "finding_id": self.finding_id,
            "proposal_id": self.proposal_id,
            "approval_request_id": self.approval_request_id,
            "action_id": self.action_id,
            "reflection_id": self.reflection_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SomaticBlock":
        """Deserialize (e.g. from a SQLite row's metadata json)."""
        return cls(
            id=d["id"],
            block_type=BlockType(d.get("block_type")),
            status=BlockStatus(d.get("status")),
            session_id=d.get("session_id", ""),
            finding_id=d.get("finding_id"),
            proposal_id=d.get("proposal_id"),
            approval_request_id=d.get("approval_request_id"),
            action_id=d.get("action_id"),
            reflection_id=d.get("reflection_id"),
            created_at=float(d.get("created_at", 0.0)),
            updated_at=float(d.get("updated_at", 0.0)),
            metadata=d.get("metadata", {}) or {},
        )