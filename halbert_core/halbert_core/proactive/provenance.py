# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Provenance reference data model.

A ProvenanceRef is a structured citation that links a claim in a response
to real evidence (log cursors, snapshot IDs, metric windows, file lines,
memory entries, observation IDs).

The backend validates refs before attaching them — never trust the LLM
to fabricate evidence. The hybrid approach from explorations.md §A2:
the LLM expresses intent to cite, the backend validates and attaches
real refs.

Phase 8 / T8a.1.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, asdict
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# Valid provenance ref types
VALID_REF_TYPES = {
    "log_cursor",       # e.g. "journald:2026-08-23:10:30:00"
    "snapshot_id",      # e.g. "snap-2026-08-23-001"
    "metric_window",    # e.g. "cpu:2026-08-23T10:00-10:05"
    "path_lines",       # e.g. "/etc/sshd_config:42-50"
    "memory_id",        # e.g. "mem-abc123"
    "observation_id",   # e.g. "obs-xyz789"
}


@dataclass
class ProvenanceRef:
    """A structured citation linking a claim to real evidence."""

    type: str  # one of VALID_REF_TYPES
    ref: str   # the reference value
    label: str = ""  # human-readable label for the UI
    url: str = ""    # deep-link if applicable

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def validate(self) -> bool:
        """Validate this ref. Returns True if valid."""
        if self.type not in VALID_REF_TYPES:
            logger.warning(f"Invalid provenance type: {self.type}")
            return False

        if not self.ref:
            return False

        # Type-specific validation
        if self.type == "path_lines":
            return self._validate_path_lines()
        elif self.type == "log_cursor":
            return self._validate_log_cursor()
        # Other types: basic non-empty check is sufficient for v1
        return True

    def _validate_path_lines(self) -> bool:
        """Validate a path_lines ref (e.g. '/etc/sshd_config:42-50')."""
        # Format: /path/to/file:line or /path/to/file:start-end
        if ":" not in self.ref:
            return False
        path, _, line_spec = self.ref.rpartition(":")
        if not path or not os.path.exists(path):
            logger.debug(f"Path does not exist: {path}")
            return False
        # Line spec can be "42" or "42-50"
        if "-" in line_spec:
            start, _, end = line_spec.partition("-")
            return start.isdigit() and end.isdigit()
        return line_spec.isdigit()

    def _validate_log_cursor(self) -> bool:
        """Validate a log_cursor ref (e.g. 'journald:2026-08-23:10:30:00')."""
        # Basic format check: source:timestamp
        if ":" not in self.ref:
            return False
        source, _, _ = self.ref.partition(":")
        valid_sources = {"journald", "syslog", "file", "kernel"}
        return source.lower() in valid_sources


def attach_provenance(
    response: str, refs: List[ProvenanceRef]
) -> Dict[str, Any]:
    """Package a response with its provenance refs for the frontend.

    Only valid refs are attached — invalid ones are silently dropped.
    """
    valid_refs = [r for r in refs if r.validate()]
    if len(valid_refs) < len(refs):
        dropped = len(refs) - len(valid_refs)
        logger.info(f"Dropped {dropped} invalid provenance refs")

    return {
        "content": response,
        "provenance": [r.to_dict() for r in valid_refs],
    }


def parse_path_lines_ref(path: str, start: int, end: int | None = None) -> ProvenanceRef:
    """Helper to create a path_lines ref."""
    line_spec = f"{start}-{end}" if end else str(start)
    ref = f"{path}:{line_spec}"
    label = f"{os.path.basename(path)} line {line_spec}"
    return ProvenanceRef(type="path_lines", ref=ref, label=label)
