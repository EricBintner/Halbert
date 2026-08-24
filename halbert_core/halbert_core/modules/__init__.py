"""
Modules — shared module registry for context modules.

Neutral home for the module registry, imported by both the dashboard
(data-fetch routes) and the agent state machine (module-invocation
validation). Moved here from ``halbert_core.dashboard.modules`` to keep
the agent layer free of dashboard dependencies.
"""

from .registry import ModuleDef, ModuleRegistry, get_module_registry

__all__ = [
    "ModuleDef",
    "ModuleRegistry",
    "get_module_registry",
]
