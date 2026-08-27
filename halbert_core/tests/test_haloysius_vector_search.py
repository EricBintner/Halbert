# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Haloysius semantic search is actually semantic, not a keyword fallback.

An audit probe logged "numpy not installed. Vector search disabled." while numpy
was importable in the same interpreter. If retrieval silently degrades to keyword
matching, the semantic recall tier buys nothing over FTS5.

Resolved 2026-08-26: the warning comes from the optional-import guard in the legacy
haloysius.memory.embeddings module, which memory_v2.store imports for its embedder.
``HAS_NUMPY`` is True in every context tested (repo root, and with halbert_core on
sys.path[0]), and the paraphrase assertion below passes, so vector search is live and
the warning is cosmetic. This test is the ratchet: if it ever fails, retrieval has
silently fallen back to keyword matching and the semantic tier is worthless.
"""

import uuid

import pytest


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    from haloysius.memory_v2.store import PersonaMemoryStore

    return PersonaMemoryStore(f"vs_{uuid.uuid4().hex[:8]}")


def _mem(store, text):
    from haloysius.memory_v2 import MemoryType, PersonaMemory

    return PersonaMemory(id=str(uuid.uuid4()), persona_id=store.persona_id,
                         memory_type=MemoryType.SEMANTIC, content=text)


def test_finds_a_paraphrase_with_no_shared_content_words(store):
    """Keyword matching cannot do this; embeddings can."""
    store.smart_add(_mem(store, "The admin prefers explicit valid users on every share"))
    store.smart_add(_mem(store, "Coffee is brewed at 93 degrees"))
    hits = store.search("who is allowed to access the folder", k=3)
    assert hits, "semantic search returned nothing — vector search is likely disabled"
    assert "valid users" in hits[0].content
