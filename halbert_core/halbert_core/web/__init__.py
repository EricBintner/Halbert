# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Web search and grounding module for Halbert.

Provides web search capabilities using SearXNG public instances.
"""

from .search import WebSearch, SearchResult

__all__ = ["WebSearch", "SearchResult"]
