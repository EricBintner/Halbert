# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Streaming Infrastructure

PTY sessions, the agent block pool, the terminal event bus and SSE helpers.
"""

from .sse import create_sse_response, sse_generator

__all__ = [
    'create_sse_response',
    'sse_generator',
]
