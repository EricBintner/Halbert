# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Living Reflexes (F3).

A reflex is a user-defined rule that fires when a detector finding / system
event matches a regex pattern AND clears a severity threshold. Reflexes are
stored in a YAML file (~/.halbert/reflexes.yaml) and evaluated on each detector
sweep by the DetectorRunner (which the existing scheduler already drives), so
no new cron is needed — "use the existing morning-report scheduler for cron"
means the reflexes ride the existing sweep cadence.

Actions (v1, conservative):
- ``notify``    -> publish a ``reflex_fired`` proactive event
- ``escalate``  -> publish a ``reflex_escalate`` event at critical severity
- ``command``   -> publish a ``reflex_command_proposed`` event carrying the
                   command (execution is left to the approval/agent layer, not
                   auto-run, for safety)

See OPUS-HANDOFF §F3.
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("halbert.proactive.reflexes")

__all__ = ["Reflex", "ReflexStore", "ReflexMatcher", "severity_rank"]

_DEFAULT_PATH = str(Path.home() / ".halbert" / "reflexes.yaml")

_SEVERITY_RANK = {"info": 1, "warning": 2, "critical": 3, "low": 1, "medium": 2, "high": 3}


def severity_rank(severity: str) -> int:
    """Map a severity string to a comparable rank (higher = more severe)."""
    return _SEVERITY_RANK.get((severity or "info").lower(), 1)


@dataclass
class Reflex:
    """A single living-reflex rule."""
    id: str
    name: str
    pattern: str  # regex matched against title + body + category
    threshold: str = "info"  # min severity to fire (info|warning|critical)
    action: str = "notify"  # notify | escalate | command
    command: Optional[str] = None  # for action == "command"
    category: str = "general"
    description: str = ""
    enabled: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id, "name": self.name, "pattern": self.pattern,
            "threshold": self.threshold, "action": self.action,
            "command": self.command, "category": self.category,
            "description": self.description, "enabled": self.enabled,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Reflex":
        return cls(
            id=d.get("id") or str(uuid.uuid4()),
            name=d.get("name", "unnamed"),
            pattern=d.get("pattern", ""),
            threshold=d.get("threshold", "info"),
            action=d.get("action", "notify"),
            command=d.get("command"),
            category=d.get("category", "general"),
            description=d.get("description", ""),
            enabled=d.get("enabled", True),
        )


class ReflexStore:
    """YAML-backed store of reflexes."""

    def __init__(self, path: Optional[str] = None):
        self.path = Path(path or _DEFAULT_PATH)

    def load(self) -> List[Reflex]:
        if not self.path.exists():
            return []
        try:
            import yaml
            with open(self.path, "r") as f:
                data = yaml.safe_load(f) or []
        except Exception as e:
            logger.warning(f"ReflexStore load failed: {e}")
            return []
        if not isinstance(data, list):
            return []
        out: List[Reflex] = []
        for item in data:
            if isinstance(item, dict):
                out.append(Reflex.from_dict(item))
        return out

    def save(self, reflexes: List[Reflex]) -> None:
        try:
            import yaml
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "w") as f:
                yaml.safe_dump([r.to_dict() for r in reflexes], f, sort_keys=False)
        except Exception as e:
            logger.warning(f"ReflexStore save failed: {e}")

    def add(self, reflex: Reflex) -> None:
        reflexes = self.load()
        reflexes = [r for r in reflexes if r.id != reflex.id]
        reflexes.append(reflex)
        self.save(reflexes)

    def remove(self, reflex_id: str) -> bool:
        reflexes = self.load()
        before = len(reflexes)
        reflexes = [r for r in reflexes if r.id != reflex_id]
        if len(reflexes) != before:
            self.save(reflexes)
            return True
        return False


class ReflexMatcher:
    """Match findings/events against a list of reflexes (regex + threshold)."""

    def __init__(self, reflexes: Optional[List[Reflex]] = None):
        self.reflexes = reflexes or []
        # Pre-compile patterns for speed; tolerate bad regex.
        self._compiled: Dict[str, re.Pattern] = {}
        for r in self.reflexes:
            self._compile(r)

    def _compile(self, r: Reflex) -> None:
        try:
            self._compiled[r.id] = re.compile(r.pattern, re.IGNORECASE)
        except re.error as e:
            logger.warning(f"Reflex {r.id} has bad pattern {r.pattern!r}: {e}")
            self._compiled[r.id] = re.compile(r"(?!)")  # never matches

    def add(self, reflex: Reflex) -> None:
        self.reflexes.append(reflex)
        self._compile(reflex)

    def match(
        self,
        *,
        title: str = "",
        body: str = "",
        severity: str = "info",
        category: str = "",
    ) -> List[Reflex]:
        """Return the reflexes that fire for the given event fields."""
        haystack = f"{title}\n{body}\n{category}"
        sev_rank = severity_rank(severity)
        hits: List[Reflex] = []
        for r in self.reflexes:
            if not r.enabled:
                continue
            if sev_rank < severity_rank(r.threshold):
                continue
            pat = self._compiled.get(r.id)
            if pat is not None and pat.search(haystack):
                hits.append(r)
        return hits

    @classmethod
    def from_store(cls, store: ReflexStore) -> "ReflexMatcher":
        return cls(store.load())
