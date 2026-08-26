# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""SourcePrepRetrievalBackend: the live retrieval path is
context.adapters.SourcePrepAdapter -> backend.search(); format_context is gone."""

from __future__ import annotations

import asyncio

from halbert_core.context.adapters import SourcePrepAdapter
from halbert_core.integrations.sourceprep_retrieval_backend import (
    SourcePrepRetrievalBackend,
)


class _FakeBackend:
    def __init__(self):
        self.calls = []

    def search(self, query, k=5, figure_id=None):
        self.calls.append((query, k, figure_id))
        return [{"text": "t", "source_path": "p", "score": 0.5}]


def test_search_has_no_format_context_and_adapter_still_works():
    assert not hasattr(SourcePrepRetrievalBackend, "format_context")

    fake = _FakeBackend()
    adapter = SourcePrepAdapter(backend=fake)
    out = asyncio.run(adapter.search("q"))
    assert out == [{"content": "t", "metadata": {}, "source": "p", "score": 0.5}]
    assert fake.calls[0][0] == "q"
