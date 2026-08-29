# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Home package — the sentient home cognitive and orchestration layer.

Modules:
- cognitive_loop: Autonomous perception-reason-action tick
- timeline: Persistent event ledger (SQLite-backed)
- occupancy: Multi-signal presence correlation
- behavior: Pattern learning and prediction from timeline history
"""

from .cognitive_loop import HomeCognitiveLoop, CognitiveTickResult
from .timeline import TimelineStore, TimelineEvent
from .occupancy import OccupancyModel, PresenceSignal, PersonPresence
from .behavior import BehaviorStore, BehaviorPattern, PatternInferrer

__all__ = [
    "HomeCognitiveLoop",
    "CognitiveTickResult",
    "TimelineStore",
    "TimelineEvent",
    "OccupancyModel",
    "PresenceSignal",
    "PersonPresence",
    "BehaviorStore",
    "BehaviorPattern",
    "PatternInferrer",
]
