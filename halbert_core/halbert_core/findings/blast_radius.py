# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Blast-radius calculator.

Uses the ConfigEdgeExtractor to determine which services and files
depend on a given config path. Returns the shallow (direct) dependents
only — deep traversal is a future enhancement.

Phase 5 / T5e.1.
"""

from __future__ import annotations

import logging
from typing import List

from ..config.edge_extractor import ConfigEdge, ConfigEdgeExtractor

logger = logging.getLogger(__name__)


class BlastRadiusCalculator:
    """Calculate the blast radius of a config change.

    Given a config file path, returns all paths/services that directly
    depend on it (based on the edge extractor's dependency graph).
    """

    def __init__(self, edge_extractor: ConfigEdgeExtractor | None = None):
        self.edge_extractor = edge_extractor or ConfigEdgeExtractor()
        self._edges: List[ConfigEdge] | None = None

    def _ensure_edges(self) -> List[ConfigEdge]:
        """Lazily load edges on first use."""
        if self._edges is None:
            self._edges = self.edge_extractor.extract_all()
            logger.info(f"Loaded {len(self._edges)} config edges for blast radius")
        return self._edges

    def calculate(self, path: str) -> List[str]:
        """Calculate the blast radius for a given config path.

        Args:
            path: The config file path that would be changed.

        Returns:
            List of dependent paths and service names (shallow, direct
            dependents only).
        """
        edges = self._ensure_edges()
        dependents: List[str] = []

        # Find edges where the target is our path
        # (if A depends on B, then edge source=A, target=B)
        # Changing B affects A
        path_norm = path.rstrip("/")

        for edge in edges:
            target = edge.target.rstrip("/")
            source = edge.source

            # Match if the edge target is our path or contains it
            if target == path_norm or target.startswith(path_norm + "/"):
                if source not in dependents:
                    dependents.append(source)

        # Also check reverse: if our path is a source, what does it affect?
        # (e.g., changing sshd_config affects sshd.service)
        for edge in edges:
            source = edge.source.rstrip("/")
            if source == path_norm:
                if edge.target not in dependents:
                    dependents.append(edge.target)

        return dependents

    def calculate_multi(self, paths: List[str]) -> List[str]:
        """Calculate blast radius for multiple paths. Returns union."""
        all_deps: List[str] = []
        for p in paths:
            deps = self.calculate(p)
            for d in deps:
                if d not in all_deps:
                    all_deps.append(d)
        return all_deps

    def refresh(self) -> None:
        """Force a reload of edges on next calculate() call."""
        self._edges = None
