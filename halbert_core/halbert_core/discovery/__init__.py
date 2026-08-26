# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Discovery Engine - Core system discovery for Halbert.

This module provides:
- Discovery schema (what we find)
- Scanner framework (how we find it)
- Storage (where we persist it)
- Engine (orchestration)
"""

from .schema import Discovery, DiscoveryType, DiscoverySeverity, DiscoveryAction
from .engine import DiscoveryEngine

__all__ = [
    'Discovery',
    'DiscoveryType', 
    'DiscoverySeverity',
    'DiscoveryAction',
    'DiscoveryEngine',
]
