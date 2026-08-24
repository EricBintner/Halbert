"""
Proposals store — config change proposals linked to findings and approvals.

A proposal is a suggested fix for a finding. It contains the config changes,
a dry-run preview, blast-radius analysis, and links to both the finding it
fixes and the approval request that gates its execution.

Phase 5 / T5b.2.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..utils.paths import data_subdir

logger = logging.getLogger(__name__)


class ProposalStatus(Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    APPLIED = "applied"
    ROLLED_BACK = "rolled_back"


@dataclass
class Proposal:
    """A proposed config change to fix a finding."""

    id: str
    finding_id: str  # the finding this proposes to fix
    action: str  # what to do
    changes: List[Dict[str, Any]] = field(default_factory=list)  # config changes
    dry_run_result: Dict[str, Any] = field(default_factory=dict)  # preview
    blast_radius: List[str] = field(default_factory=list)  # affected paths/services

    # State
    status: str = "pending"
    created_at: str = ""
    approved_at: str = ""
    applied_at: str = ""
    rolled_back_at: str = ""
    rejection_reason: str = ""

    # Link to approval request
    approval_request_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Proposal":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


_SCHEMA = """
CREATE TABLE IF NOT EXISTS proposals (
    id TEXT PRIMARY KEY,
    finding_id TEXT NOT NULL,
    action TEXT NOT NULL,
    changes TEXT NOT NULL,  -- JSON array
    dry_run_result TEXT NOT NULL,  -- JSON object
    blast_radius TEXT NOT NULL,  -- JSON array
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL,
    approved_at TEXT NOT NULL DEFAULT '',
    applied_at TEXT NOT NULL DEFAULT '',
    rolled_back_at TEXT NOT NULL DEFAULT '',
    rejection_reason TEXT NOT NULL DEFAULT '',
    approval_request_id TEXT,
    FOREIGN KEY (finding_id) REFERENCES findings(id)
);

CREATE INDEX IF NOT EXISTS idx_proposals_status ON proposals(status);
CREATE INDEX IF NOT EXISTS idx_proposals_finding ON proposals(finding_id);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_proposal(row: sqlite3.Row) -> Proposal:
    return Proposal(
        id=row["id"],
        finding_id=row["finding_id"],
        action=row["action"],
        changes=json.loads(row["changes"]),
        dry_run_result=json.loads(row["dry_run_result"]),
        blast_radius=json.loads(row["blast_radius"]),
        status=row["status"],
        created_at=row["created_at"],
        approved_at=row["approved_at"],
        applied_at=row["applied_at"],
        rolled_back_at=row["rolled_back_at"],
        rejection_reason=row["rejection_reason"],
        approval_request_id=row["approval_request_id"],
    )


def _proposal_to_row(p: Proposal) -> Dict[str, Any]:
    d = p.to_dict()
    d["changes"] = json.dumps(p.changes)
    d["dry_run_result"] = json.dumps(p.dry_run_result)
    d["blast_radius"] = json.dumps(p.blast_radius)
    return d


class ProposalStore:
    """SQLite-backed store for proposals.

    Default db_path: ~/.local/share/halbert/findings.db (shared with findings)
    """

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            db_path = str(Path(data_subdir("findings")) / "findings.db")
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript(_SCHEMA)
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def add(self, proposal: Proposal) -> str:
        """Add a proposal. Generates ID and created_at if not set."""
        if not proposal.id:
            proposal.id = str(uuid.uuid4())
        if not proposal.created_at:
            proposal.created_at = _now()

        row = _proposal_to_row(proposal)
        cols = ", ".join(row.keys())
        placeholders = ", ".join(["?"] * len(row))
        with self._connect() as conn:
            conn.execute(
                f"INSERT OR REPLACE INTO proposals ({cols}) VALUES ({placeholders})",
                list(row.values()),
            )
            conn.commit()
        logger.info(f"Proposal added: {proposal.id} for finding {proposal.finding_id}")
        return proposal.id

    def get(self, proposal_id: str) -> Optional[Proposal]:
        """Get a single proposal by ID."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM proposals WHERE id = ?", (proposal_id,)
            ).fetchone()
        return _row_to_proposal(row) if row else None

    def list_pending(self) -> List[Proposal]:
        """List all pending proposals."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM proposals WHERE status = 'pending' "
                "ORDER BY created_at DESC"
            ).fetchall()
        return [_row_to_proposal(r) for r in rows]

    def list_for_finding(self, finding_id: str) -> List[Proposal]:
        """List all proposals for a given finding."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM proposals WHERE finding_id = ? "
                "ORDER BY created_at DESC",
                (finding_id,),
            ).fetchall()
        return [_row_to_proposal(r) for r in rows]

    def list_all(self, limit: int = 100) -> List[Proposal]:
        """List all proposals, most recent first."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM proposals ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [_row_to_proposal(r) for r in rows]

    def update_status(
        self, proposal_id: str, status: str, **kwargs: Any
    ) -> bool:
        """Update a proposal's status. Extra kwargs set additional fields."""
        allowed = {
            "approved_at",
            "applied_at",
            "rolled_back_at",
            "rejection_reason",
            "approval_request_id",
        }
        extras = {k: v for k, v in kwargs.items() if k in allowed}

        if status == ProposalStatus.APPROVED.value and "approved_at" not in extras:
            extras["approved_at"] = _now()
        if status == ProposalStatus.APPLIED.value and "applied_at" not in extras:
            extras["applied_at"] = _now()
        if status == ProposalStatus.ROLLED_BACK.value and "rolled_back_at" not in extras:
            extras["rolled_back_at"] = _now()

        set_parts = ["status = ?"]
        params: List[Any] = [status]
        for k, v in extras.items():
            set_parts.append(f"{k} = ?")
            params.append(v)

        params.append(proposal_id)
        with self._connect() as conn:
            cur = conn.execute(
                f"UPDATE proposals SET {', '.join(set_parts)} WHERE id = ?",
                params,
            )
            conn.commit()
            updated = cur.rowcount > 0

        if updated:
            logger.info(f"Proposal {proposal_id} status -> {status}")
        return updated

    def approve(self, proposal_id: str, approval_request_id: str = "") -> bool:
        """Mark a proposal as approved."""
        kwargs: Dict[str, Any] = {}
        if approval_request_id:
            kwargs["approval_request_id"] = approval_request_id
        return self.update_status(
            proposal_id, ProposalStatus.APPROVED.value, **kwargs
        )

    def reject(self, proposal_id: str, reason: str) -> bool:
        """Mark a proposal as rejected."""
        return self.update_status(
            proposal_id,
            ProposalStatus.REJECTED.value,
            rejection_reason=reason,
        )

    def mark_applied(self, proposal_id: str) -> bool:
        """Mark a proposal as successfully applied."""
        return self.update_status(proposal_id, ProposalStatus.APPLIED.value)

    def mark_rolled_back(self, proposal_id: str) -> bool:
        """Mark a proposal as rolled back (execution failed)."""
        return self.update_status(proposal_id, ProposalStatus.ROLLED_BACK.value)

    def delete(self, proposal_id: str) -> bool:
        """Permanently delete a proposal."""
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM proposals WHERE id = ?", (proposal_id,))
            conn.commit()
            return cur.rowcount > 0
