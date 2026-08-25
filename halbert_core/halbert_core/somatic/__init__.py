"""Somatic blocks package (C1).

A somatic block is the wrapper that drives a single self-management cycle
through its 5 phases (SENSORY -> DELIBERATION -> PROPOSAL -> ACTION ->
REFLECTION). It references — but does NOT absorb — the existing Finding /
Proposal / ApprovalRequest / Action / Reflection models by id.

See OPUS-HANDOFF §C1.
"""

from .block import BlockType, BlockStatus, SomaticBlock
from .store import SomaticStore, get_somatic_store

__all__ = [
    "BlockType",
    "BlockStatus",
    "SomaticBlock",
    "SomaticStore",
    "get_somatic_store",
]