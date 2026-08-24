"""
Drop-in conflict detector.

Scans for conflicting directives across sshd_config drop-ins and systemd
unit drop-in directories. Uses the PrecedenceEngine to detect cases where
the same key is set to different values in different files.

Phase 5 / T5c.1.
"""

from __future__ import annotations

import logging
from typing import List

from ..store import Finding, FindingStore
from ..precedence import PrecedenceEngine

logger = logging.getLogger(__name__)


class DropinConflictDetector:
    """Detect conflicting directives in sshd and systemd drop-in files."""

    def __init__(
        self,
        config_dir: str = "/etc",
        precedence_engine: PrecedenceEngine | None = None,
    ):
        self.engine = precedence_engine or PrecedenceEngine(config_dir=config_dir)

    def detect(self) -> List[Finding]:
        """Run detection and return a list of findings."""
        findings: List[Finding] = []

        # Check sshd drop-in conflicts
        findings.extend(self._detect_sshd_conflicts())

        # Check systemd unit drop-in conflicts
        findings.extend(self._detect_systemd_conflicts())

        return findings

    def _detect_sshd_conflicts(self) -> List[Finding]:
        """Detect conflicts in sshd_config + drop-ins."""
        findings: List[Finding] = []
        result = self.engine.resolve_sshd()

        for conflict in result.get("conflicts", []):
            key = conflict["key"]
            values = conflict["values"]
            effective = conflict["effective"]
            eff_source = conflict["effective_source"]

            affected_paths = list(set(v["file"] for v in values))

            findings.append(Finding(
                id="",
                detector="dropin_conflicts",
                severity="warning",
                title=f"sshd config conflict: {key}",
                description=(
                    f"Directive '{key}' is set to different values across "
                    f"sshd_config and drop-in files. Effective value is "
                    f"'{effective}' (from {eff_source[0]}:{eff_source[1]})."
                ),
                why_now=(
                    f"Drop-in file overrides '{key}' with a conflicting value "
                    f"during configuration scan."
                ),
                why_care=(
                    f"The effective sshd configuration may not match intent — "
                    f"the service may behave unexpectedly if the wrong value "
                    f"takes precedence."
                ),
                why_so=(
                    f"Directive '{key}' appears {len(values)} times with "
                    f"different values: "
                    + "; ".join(f"{v['file']}:{v['line']}={v['value']}" for v in values)
                    + f". Drop-in files override the base config in alphabetical order."
                ),
                why_trust=[
                    f"{v['file']}:{v['line']}" for v in values
                ],
                affected_paths=affected_paths,
                affected_services=["sshd"],
            ))

        return findings

    def _detect_systemd_conflicts(self) -> List[Finding]:
        """Detect conflicts in systemd unit drop-ins."""
        findings: List[Finding] = []
        import os

        # Find all units that have drop-in directories
        systemd_dir = self.engine.systemd_dir
        if not os.path.isdir(systemd_dir):
            return findings

        # Collect unit names from base files and drop-in dirs
        unit_names: set[str] = set()
        for fname in os.listdir(systemd_dir):
            for ext in (".service", ".mount", ".timer", ".socket"):
                if fname.endswith(ext):
                    unit_names.add(fname[: -len(ext)])
                if fname.endswith(ext + ".d"):
                    # Drop-in dir: extract unit name
                    unit_names.add(fname[: -(len(ext) + 2)])

        for unit_name in sorted(unit_names):
            result = self.engine.resolve_systemd_unit(unit_name)
            for conflict in result.get("conflicts", []):
                key = conflict["key"]
                values = conflict["values"]
                effective = conflict["effective"]
                eff_source = conflict["effective_source"]

                affected_paths = list(set(v["file"] for v in values))

                findings.append(Finding(
                    id="",
                    detector="dropin_conflicts",
                    severity="warning",
                    title=f"systemd {unit_name}: {key} conflict",
                    description=(
                        f"Directive '{key}' in {unit_name} is set to different "
                        f"values across the base unit and drop-in files. "
                        f"Effective value is '{effective}'."
                    ),
                    why_now=(
                        f"Drop-in file overrides '{key}' with a conflicting "
                        f"value in {unit_name}."
                    ),
                    why_care=(
                        f"The effective {unit_name} configuration may not match "
                        f"intent — the service may behave unexpectedly."
                    ),
                    why_so=(
                        f"Directive '{key}' appears {len(values)} times: "
                        + "; ".join(f"{v['file']}:{v['line']}={v['value']}" for v in values)
                        + ". Drop-ins override the base unit."
                    ),
                    why_trust=[
                        f"{v['file']}:{v['line']}" for v in values
                    ],
                    affected_paths=affected_paths,
                    affected_services=[unit_name],
                ))

        return findings
