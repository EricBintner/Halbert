"""
Findings store — persistent storage for config brain findings.

A finding is a detected issue with the host's configuration, annotated
with the "Four Whys" framework:
  - why_now:   what triggered this detection right now
  - why_care:  consequence if ignored
  - why_so:    the reasoning / evidence
  - why_trust: provenance refs (log cursors, snapshot ids, path:lines)

Phase 5 / T5b.1.
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


class FindingStatus(Enum):
    OPEN = "open"
    SNOOZED = "snoozed"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


@dataclass
class Finding:
    """A detected configuration issue with the Four Whys framework."""

    id: str
    detector: str  # which detector found this
    severity: str  # info | warning | critical
    title: str
    description: str

    # The four whys
    why_now: str  # what triggered this detection right now
    why_care: str  # consequence if ignored
    why_so: str  # the reasoning / evidence
    why_trust: List[str] = field(default_factory=list)  # provenance refs

    # Config refs
    affected_paths: List[str] = field(default_factory=list)
    affected_services: List[str] = field(default_factory=list)

    # State
    status: str = "open"
    created_at: str = ""
    snoozed_until: str = ""
    resolved_at: str = ""
    dismissed_reason: str = ""

    # Link to proposal if one exists
    proposal_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Finding":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


_SCHEMA = """
CREATE TABLE IF NOT EXISTS findings (
    id TEXT PRIMARY KEY,
    detector TEXT NOT NULL,
    severity TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    why_now TEXT NOT NULL,
    why_care TEXT NOT NULL,
    why_so TEXT NOT NULL,
    why_trust TEXT NOT NULL,  -- JSON array
    affected_paths TEXT NOT NULL,  -- JSON array
    affected_services TEXT NOT NULL,  -- JSON array
    status TEXT NOT NULL DEFAULT 'open',
    created_at TEXT NOT NULL,
    snoozed_until TEXT NOT NULL DEFAULT '',
    resolved_at TEXT NOT NULL DEFAULT '',
    dismissed_reason TEXT NOT NULL DEFAULT '',
    proposal_id TEXT
);

CREATE INDEX IF NOT EXISTS idx_findings_status ON findings(status);
CREATE INDEX IF NOT EXISTS idx_findings_severity ON findings(severity);
CREATE INDEX IF NOT EXISTS idx_findings_detector ON findings(detector);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_timestamp(value: str) -> Optional[datetime]:
    """Parse an ISO-8601 timestamp tolerantly.

    Handles a trailing 'Z', an explicit offset ('+00:00'), and the
    redundant '+00:00Z' combination produced by some code paths in this
    repo. Naive timestamps are assumed UTC. Returns None when the value
    is empty or unparseable.
    """
    if not value:
        return None
    v = value.strip()
    if v.endswith("Z"):
        if "+" in v[10:] or (len(v) > 10 and "-" in v[10:]):
            # Offset already present (e.g. '+00:00Z') — drop the 'Z'.
            v = v[:-1]
        else:
            v = v[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(v)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _row_to_finding(row: sqlite3.Row) -> Finding:
    return Finding(
        id=row["id"],
        detector=row["detector"],
        severity=row["severity"],
        title=row["title"],
        description=row["description"],
        why_now=row["why_now"],
        why_care=row["why_care"],
        why_so=row["why_so"],
        why_trust=json.loads(row["why_trust"]),
        affected_paths=json.loads(row["affected_paths"]),
        affected_services=json.loads(row["affected_services"]),
        status=row["status"],
        created_at=row["created_at"],
        snoozed_until=row["snoozed_until"],
        resolved_at=row["resolved_at"],
        dismissed_reason=row["dismissed_reason"],
        proposal_id=row["proposal_id"],
    )


def _finding_to_row(f: Finding) -> Dict[str, Any]:
    d = f.to_dict()
    d["why_trust"] = json.dumps(f.why_trust)
    d["affected_paths"] = json.dumps(f.affected_paths)
    d["affected_services"] = json.dumps(f.affected_services)
    return d


class FindingStore:
    """SQLite-backed store for findings.

    Default db_path: ~/.local/share/halbert/findings.db
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

    def add(self, finding: Finding) -> str:
        """Add a finding. Generates ID and created_at if not set."""
        if not finding.id:
            finding.id = str(uuid.uuid4())
        if not finding.created_at:
            finding.created_at = _now()

        row = _finding_to_row(finding)
        cols = ", ".join(row.keys())
        placeholders = ", ".join(["?"] * len(row))
        with self._connect() as conn:
            conn.execute(
                f"INSERT OR REPLACE INTO findings ({cols}) VALUES ({placeholders})",
                list(row.values()),
            )
            conn.commit()
        logger.info(f"Finding added: {finding.id} [{finding.severity}] {finding.title}")
        return finding.id

    def get(self, finding_id: str) -> Optional[Finding]:
        """Get a single finding by ID."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM findings WHERE id = ?", (finding_id,)
            ).fetchone()
        return _row_to_finding(row) if row else None

    def list_all(self, limit: int = 100) -> List[Finding]:
        """List all findings, most recent first."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM findings ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [_row_to_finding(r) for r in rows]

    def list_open(self) -> List[Finding]:
        """List all open findings."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM findings WHERE status = 'open' ORDER BY created_at DESC"
            ).fetchall()
        return [_row_to_finding(r) for r in rows]

    def list_by_severity(self, severity: str) -> List[Finding]:
        """List findings by severity (open only)."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM findings WHERE severity = ? AND status = 'open' "
                "ORDER BY created_at DESC",
                (severity,),
            ).fetchall()
        return [_row_to_finding(r) for r in rows]

    def find_by_detector_title(self, detector: str, title: str) -> Optional[Finding]:
        """Find the newest finding matching detector + title, any status.

        Single targeted query used by DetectorRunner's dedup instead of
        scanning list_all() per finding.
        """
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM findings WHERE detector = ? AND title = ? "
                "ORDER BY created_at DESC LIMIT 1",
                (detector, title),
            ).fetchone()
        return _row_to_finding(row) if row else None

    def list_by_detector(self, detector: str) -> List[Finding]:
        """List findings by detector name (all statuses)."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM findings WHERE detector = ? ORDER BY created_at DESC",
                (detector,),
            ).fetchall()
        return [_row_to_finding(r) for r in rows]

    def update_status(
        self, finding_id: str, status: str, **kwargs: Any
    ) -> bool:
        """Update a finding's status. Extra kwargs set additional fields."""
        allowed = {"snoozed_until", "resolved_at", "dismissed_reason", "proposal_id"}
        extras = {k: v for k, v in kwargs.items() if k in allowed}

        if status == FindingStatus.RESOLVED.value and "resolved_at" not in extras:
            extras["resolved_at"] = _now()

        set_parts = ["status = ?"]
        params: List[Any] = [status]
        for k, v in extras.items():
            set_parts.append(f"{k} = ?")
            params.append(v)

        params.append(finding_id)
        with self._connect() as conn:
            cur = conn.execute(
                f"UPDATE findings SET {', '.join(set_parts)} WHERE id = ?",
                params,
            )
            conn.commit()
            updated = cur.rowcount > 0

        if updated:
            logger.info(f"Finding {finding_id} status -> {status}")
        return updated

    def snooze(self, finding_id: str, days: int) -> bool:
        """Snooze a finding for N days.

        The snooze is also saved as a SourcePrep observation (mirroring
        dismiss()). SourcePrep failures are logged but never fail the
        store operation — SourcePrep is optional infrastructure.
        """
        from datetime import timedelta

        now = datetime.now(timezone.utc)
        until = (now + timedelta(days=days)).isoformat()
        updated = self.update_status(
            finding_id, FindingStatus.SNOOZED.value, snoozed_until=until
        )

        if updated:
            # Try to record the snooze in SourcePrep
            try:
                from ..integrations.sourceprep_client import SourcePrepClient

                client = SourcePrepClient()
                finding = self.get(finding_id)
                if finding:
                    client.save_observation(
                        content=f"Snoozed finding '{finding.title}' for {days} days",
                        file_path=(
                            finding.affected_paths[0]
                            if finding.affected_paths
                            else None
                        ),
                        category="decision",
                    )
                    logger.info(f"Snooze saved to SourcePrep observation: {finding_id}")
            except Exception as e:
                logger.debug(f"Could not save snooze to SourcePrep: {e}")

        return updated

    def dismiss(self, finding_id: str, reason: str) -> bool:
        """Dismiss a finding, recording the reason.

        The reason is also saved as a SourcePrep concept (why the user said
        it's not a problem) if SourcePrep is available.
        """
        updated = self.update_status(
            finding_id, FindingStatus.DISMISSED.value, dismissed_reason=reason
        )

        if updated:
            # Try to record the dismissal reason in SourcePrep
            try:
                from ..integrations.sourceprep_client import SourcePrepClient

                client = SourcePrepClient()
                finding = self.get(finding_id)
                if finding:
                    client.save_concept(
                        title=f"Dismissed: {finding.title}",
                        content=f"User dismissed this finding. Reason: {reason}",
                        category="decision",
                        anchors=finding.affected_paths,
                    )
                    logger.info(f"Dismissal reason saved to SourcePrep: {finding_id}")
            except Exception as e:
                logger.debug(f"Could not save dismissal to SourcePrep: {e}")

        return updated

    def link_proposal(self, finding_id: str, proposal_id: str) -> bool:
        """Link a proposal to a finding."""
        return self.update_status(
            finding_id, FindingStatus.OPEN.value, proposal_id=proposal_id
        )

    def count(self, status: Optional[str] = None) -> int:
        """Count findings, optionally filtered by status."""
        with self._connect() as conn:
            if status:
                row = conn.execute(
                    "SELECT COUNT(*) FROM findings WHERE status = ?", (status,)
                ).fetchone()
            else:
                row = conn.execute("SELECT COUNT(*) FROM findings").fetchone()
        return row[0] if row else 0

    def delete(self, finding_id: str) -> bool:
        """Permanently delete a finding."""
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM findings WHERE id = ?", (finding_id,))
            conn.commit()
            return cur.rowcount > 0
