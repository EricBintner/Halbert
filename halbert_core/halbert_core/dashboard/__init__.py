# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Halbert Dashboard (Phase 3 M5).

Web-based UI for monitoring autonomous system, managing approvals,
and viewing job execution.
"""

from .app import create_app, ConnectionManager

__all__ = [
    'create_app',
    'ConnectionManager',
]
