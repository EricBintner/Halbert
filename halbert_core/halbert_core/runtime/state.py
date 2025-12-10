from __future__ import annotations
from typing import Any, Dict, List
from pydantic import BaseModel, Field

"""
Halbert Phase 1 typed shared state.
See docs/Phase1/engineering-spec.md and docs/Phase1/architecture.md
"""

class HalbertState(BaseModel):
    conversation: List[Dict[str, Any]] = Field(default_factory=list)
    tasks: List[Dict[str, Any]] = Field(default_factory=list)
    metrics: Dict[str, float] = Field(default_factory=dict)
    flags: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        extra = "allow"
