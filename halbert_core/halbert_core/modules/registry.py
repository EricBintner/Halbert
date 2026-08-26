# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Module registry — defines available context modules for the reactive slice.

Modules are self-contained UI components that can be summoned into the
conversation context region. Each module has:
- A name (unique identifier)
- A React component name (frontend looks up the actual component)
- A data fetcher (API endpoint path)
- A prop contract (expected props)
- A standalone route (for full-page view)
- An icon name

This lives in the agent-neutral ``halbert_core.modules`` package (not under
``dashboard``) because the agent state machine validates LLM-emitted module
invocations against this registry — the agent layer must not depend on the
dashboard layer.

Phase 8 / T8b.1.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ModuleDef:
    """Definition of a context module."""

    name: str  # "config-diff", "drive-health", "vitals", "evidence"
    component: str  # React component name (frontend)
    data_fetcher: str  # API endpoint path for data
    prop_contract: dict  # expected props
    standalone_route: str  # route for full-page view
    icon: str = ""  # icon name
    description: str = ""  # human-readable description

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "component": self.component,
            "data_fetcher": self.data_fetcher,
            "prop_contract": self.prop_contract,
            "standalone_route": self.standalone_route,
            "icon": self.icon,
            "description": self.description,
        }


class ModuleRegistry:
    """In-memory registry of available modules."""

    def __init__(self):
        self._modules: Dict[str, ModuleDef] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        """Register the default module set."""
        self.register(ModuleDef(
            name="config-diff",
            component="ConfigDiffModule",
            data_fetcher="/api/modules/config-diff/data",
            prop_contract={"path": "string", "findingId": "string?"},
            standalone_route="/modules/config-diff",
            icon="FileText",
            description="Shows a config file diff inline",
        ))
        self.register(ModuleDef(
            name="vitals",
            component="VitalsModule",
            data_fetcher="/api/modules/vitals/data",
            prop_contract={"timeframe": "string"},
            standalone_route="/modules/vitals",
            icon="Activity",
            description="Compact system vitals (CPU, memory, disk, network)",
        ))
        self.register(ModuleDef(
            name="drive-health",
            component="DriveHealthModule",
            data_fetcher="/api/modules/drive-health/data",
            prop_contract={},
            standalone_route="/modules/drive-health",
            icon="HardDrive",
            description=(
                "Drive partition capacity and usage (psutil-based). "
                "SMART status and temperature are NOT available "
                "cross-platform — payload reports telemetry_source "
                "'psutil-partitions'."
            ),
        ))
        self.register(ModuleDef(
            name="evidence",
            component="EvidenceModule",
            data_fetcher="/api/modules/evidence/data",
            prop_contract={"source": "string", "cursor": "string", "query": "string?"},
            standalone_route="/modules/evidence",
            icon="BookOpen",
            description="Log excerpt viewer with highlighting",
        ))

    def register(self, module: ModuleDef) -> None:
        """Register a module."""
        self._modules[module.name] = module
        logger.info(f"Module registered: {module.name}")

    def get(self, name: str) -> Optional[ModuleDef]:
        """Get a module by name."""
        return self._modules.get(name)

    def list_all(self) -> List[ModuleDef]:
        """List all registered modules."""
        return list(self._modules.values())


# Global singleton
_registry: Optional[ModuleRegistry] = None


def get_module_registry() -> ModuleRegistry:
    """Get the global ModuleRegistry singleton."""
    global _registry
    if _registry is None:
        _registry = ModuleRegistry()
    return _registry
