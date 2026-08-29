# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Home package — the sentient home cognitive and orchestration layer.

Modules:
- cognitive_loop: Autonomous perception-reason-action tick
- (future) occupancy: Multi-signal occupancy model
- (future) timeline: Persistent event timeline store
- (future) behavior: Pattern learning and prediction
"""

from .cognitive_loop import HomeCognitiveLoop, CognitiveTickResult

__all__ = ["HomeCognitiveLoop", "CognitiveTickResult"]
