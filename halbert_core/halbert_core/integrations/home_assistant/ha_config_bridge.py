# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""HA Config SourcePrep Bridge — register and index HA config files.

Phase 3: SourcePrep for HA configs. This module provides:

1. A config dataclass for the HA config SourcePrep project settings.
2. Functions to check SourcePrep daemon health and project status.
3. A function to search HA configs via SourcePrep semantic search.
4. A function to push HA automation dependency edges into SourcePrep.

The home instance sets SOURCEPREP_PROJECT_ID=ha-config (or a custom ID)
and this module provides the glue between HA config files and the
SourcePrep retrieval backend.

No Halbert refactoring needed — this is a consumer-side bridge that
uses the existing SourcePrepClient API.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..sourceprep_client import SourcePrepClient

logger = logging.getLogger("halbert.integrations.home_assistant.config_bridge")


@dataclass
class HAConfigSourcePrep:
    """Configuration for the HA config SourcePrep project."""
    project_id: str = "ha-config"
    sourceprep_url: str = "http://localhost:8400"
    ha_config_path: str = "/config"  # HA config directory
    enabled: bool = True

    @classmethod
    def from_env(cls) -> "HAConfigSourcePrep":
        """Load config from environment variables."""
        return cls(
            project_id=os.environ.get("HA_SOURCEPREP_PROJECT_ID", "ha-config"),
            sourceprep_url=os.environ.get("SOURCEPREP_URL", "http://localhost:8400"),
            ha_config_path=os.environ.get("HA_CONFIG_PATH", "/config"),
            enabled=os.environ.get("HA_SOURCEPREP_ENABLED", "1").lower() in ("1", "true", "yes"),
        )


def get_client(config: Optional[HAConfigSourcePrep] = None) -> SourcePrepClient:
    """Get a SourcePrep client configured for the HA config project."""
    cfg = config or HAConfigSourcePrep.from_env()
    return SourcePrepClient(
        base_url=cfg.sourceprep_url,
        project_id=cfg.project_id,
    )


def check_sourceprep_status(config: Optional[HAConfigSourcePrep] = None) -> Dict[str, Any]:
    """Check if SourcePrep is running and the HA config project is indexed.

    Returns:
        Dict with:
            - daemon_reachable: bool
            - project_id: str
            - config_path: str
            - indexed: bool (project exists and has content)
            - error: Optional[str]
    """
    cfg = config or HAConfigSourcePrep.from_env()

    if not cfg.enabled:
        return {
            "daemon_reachable": False,
            "project_id": cfg.project_id,
            "config_path": cfg.ha_config_path,
            "indexed": False,
            "error": "HA SourcePrep integration disabled",
        }

    client = get_client(cfg)

    try:
        healthy = client.health()
        if not healthy:
            return {
                "daemon_reachable": False,
                "project_id": cfg.project_id,
                "config_path": cfg.ha_config_path,
                "indexed": False,
                "error": f"SourcePrep daemon not reachable at {cfg.sourceprep_url}",
            }

        # Try a simple search to see if the project has content
        try:
            result = client.search("automations", k=1, min_score=0.0)
            chunks = result.get("chunks", result.get("results", []))
            indexed = len(chunks) > 0
        except Exception:
            indexed = False

        return {
            "daemon_reachable": True,
            "project_id": cfg.project_id,
            "config_path": cfg.ha_config_path,
            "indexed": indexed,
            "error": None,
        }

    except Exception as e:
        return {
            "daemon_reachable": False,
            "project_id": cfg.project_id,
            "config_path": cfg.ha_config_path,
            "indexed": False,
            "error": str(e),
        }


def search_ha_config(
    query: str,
    k: int = 5,
    config: Optional[HAConfigSourcePrep] = None,
) -> List[Dict[str, Any]]:
    """Search HA config files via SourcePrep semantic search.

    This is the core function that lets Halbert answer questions like:
    - "Why is the living room light automation triggering twice?"
    - "Show me all automations that touch the front door lock"
    - "What changed in the thermostat schedule?"

    Args:
        query: Natural language query about HA config.
        k: Number of results to return.
        config: Optional config override.

    Returns:
        List of chunk dicts with content, file_path, score, etc.
    """
    cfg = config or HAConfigSourcePrep.from_env()
    if not cfg.enabled:
        return []

    client = get_client(cfg)

    try:
        result = client.get_context(
            query=query,
            k=k,
            structured=True,
            min_score=0.10,
        )
        chunks = result.get("chunks", [])
        return chunks if isinstance(chunks, list) else []
    except Exception as e:
        logger.warning(f"HA config search failed: {e}")
        return []


def search_ha_automations(query: str, k: int = 5) -> List[Dict[str, Any]]:
    """Search specifically for automation-related config entries.

    Convenience wrapper that scopes the query to automation files.
    """
    results = search_ha_config(f"automation {query}", k=k)
    # Filter to automation-related files
    filtered = [
        r for r in results
        if "automation" in r.get("file_path", "").lower()
        or "script" in r.get("file_path", "").lower()
    ]
    return filtered if filtered else results


def push_automation_edges(
    automations: List[Dict[str, Any]],
    config: Optional[HAConfigSourcePrep] = None,
) -> bool:
    """Push HA automation dependency edges into SourcePrep trace graph.

    This enables impact analysis: "what breaks if I change this entity?"

    Args:
        automations: List of automation dicts with:
            - id: Automation ID/alias
            - file_path: YAML file path
            - triggers: List of entity_ids that trigger it
            - actions: List of entity_ids it controls
        config: Optional config override.

    Returns:
        True if edges were pushed successfully.
    """
    cfg = config or HAConfigSourcePrep.from_env()
    if not cfg.enabled:
        return False

    client = get_client(cfg)

    edges = []
    for auto in automations:
        auto_id = auto.get("id", "")
        file_path = auto.get("file_path", "")
        triggers = auto.get("triggers", [])
        actions = auto.get("actions", [])

        # Trigger edges: trigger entity -> automation
        for trigger_id in triggers:
            edges.append({
                "source": f"entity:{trigger_id}",
                "target": f"automation:{auto_id}",
                "relation": "triggers",
                "file_path": file_path,
                "origin": "ha-config",
            })

        # Action edges: automation -> target entity
        for action_id in actions:
            edges.append({
                "source": f"automation:{auto_id}",
                "target": f"entity:{action_id}",
                "relation": "controls",
                "file_path": file_path,
                "origin": "ha-config",
            })

    if not edges:
        return True

    try:
        client.push_external_edges(edges, replace_origin="ha-config")
        logger.info(f"Pushed {len(edges)} HA automation edges to SourcePrep")
        return True
    except Exception as e:
        logger.warning(f"Failed to push HA automation edges: {e}")
        return False
