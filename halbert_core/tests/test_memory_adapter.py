"""Tests for MemoryServiceAdapter / SelfKnowledgeAdapter wiring (B8)."""
import asyncio
import logging

from halbert_core.context.adapters import MemoryServiceAdapter
from halbert_core.context.extra_adapters import SelfKnowledgeAdapter


def test_memory_adapter_initialises_without_warning(caplog):
    adapter = MemoryServiceAdapter()
    with caplog.at_level(logging.WARNING, logger="halbert_core.context.adapters"):
        adapter._ensure_initialized()
    assert adapter._service is not None
    assert type(adapter._service).__name__ == "HybridMemorySystem"
    assert not [r for r in caplog.records if "Could not initialize memory service" in r.getMessage()]


def test_recall_awaits_async_service():
    class Fake:
        async def recall(self, query, limit=5):
            return [{"content": "x", "type": "fact", "metadata": {"a": 1}}]

    result = asyncio.run(MemoryServiceAdapter(Fake()).recall("q"))
    assert result == [{"content": "x", "type": "fact", "metadata": {"a": 1}}]


def test_recall_prefers_recall_over_search():
    class Fake:
        async def recall(self, query, limit=5):
            return [{"content": "from-recall"}]

        def search(self, query, limit=5):
            raise AssertionError("search should not be used when recall exists")

    result = asyncio.run(MemoryServiceAdapter(Fake()).recall("q"))
    assert result[0]["content"] == "from-recall"


def test_store_interaction_awaits_async_service():
    recorded = []

    class Fake:
        async def store_interaction(self, query, response, session_id=None):
            recorded.append((query, response, session_id))

        async def store(self, *a, **kw):
            raise AssertionError("store should not be used when store_interaction exists")

    asyncio.run(MemoryServiceAdapter(Fake()).store_interaction("q", "r" * 60, "s1"))
    assert recorded == [("q", "r" * 60, "s1")]


def test_self_knowledge_adapter_initialises_without_warning(caplog, monkeypatch):
    import halbert_core.knowledge.self_knowledge as sk

    class FakeSK:
        def search(self, query, k=5):
            return []

    monkeypatch.setattr(sk, "get_self_knowledge", lambda: FakeSK())
    adapter = SelfKnowledgeAdapter()
    with caplog.at_level(logging.WARNING, logger="halbert_core.context.extra_adapters"):
        adapter._ensure_initialized()
    assert adapter._store is not None
    assert not [r for r in caplog.records if "Could not initialize self-knowledge store" in r.getMessage()]


def test_self_knowledge_adapter_search_uses_k_and_entry_objects():
    from halbert_core.knowledge.self_knowledge import KnowledgeEntry, KnowledgeType

    class FakeSK:
        def search(self, query, k=5):
            assert k == 3
            return [KnowledgeEntry(id="1", type=KnowledgeType.CONFIG_RATIONALE, subject="s", content="body")]

    items = asyncio.run(SelfKnowledgeAdapter(FakeSK()).search("q", limit=3))
    assert items[0]["content"] == "body"


# ---------------------------------------------------------------------------
# HybridMemorySystem <-> SelfKnowledge wiring (round 2)
# ---------------------------------------------------------------------------

def _make_entry(content="sshd listens on 22", subject="sshd"):
    from halbert_core.knowledge.self_knowledge import KnowledgeEntry, KnowledgeType
    return KnowledgeEntry(
        id="k1", type=KnowledgeType.CONFIG_RATIONALE, subject=subject,
        content=content, metadata={"port": 22},
    )


class _RealSigSK:
    """Fake store with the REAL SelfKnowledge signature: search(query, k) / add(entry)."""

    def __init__(self):
        self.added = []

    def search(self, query, k=5):
        return [_make_entry()][:k]

    def add(self, entry):
        self.added.append(entry)
        return entry.id


def _hybrid(sk):
    from halbert_core.memory.hybrid import HybridMemorySystem
    h = HybridMemorySystem(vector_store=False, knowledge_graph=False,
                           self_knowledge=sk, embedding_service=False)
    h._initialized = True
    return h


def test_hybrid_search_self_knowledge_uses_k_and_maps_entries(caplog):
    sk = _RealSigSK()
    h = _hybrid(sk)
    with caplog.at_level(logging.WARNING):
        results = asyncio.run(h._search_self_knowledge("sshd", limit=3))
    assert "Self-knowledge search failed" not in caplog.text
    assert len(results) == 1
    r = results[0]
    assert r["id"] == "k1"
    assert r["content"] == "sshd listens on 22"
    assert r["type"] == "semantic"
    assert r["relevance"] == 0.5 and r["importance"] == 0.6
    assert r["metadata"]["subject"] == "sshd"
    assert r["metadata"]["port"] == 22


def test_hybrid_recall_with_real_signature_store_has_no_warning(caplog):
    h = _hybrid(_RealSigSK())
    with caplog.at_level(logging.WARNING):
        mems = asyncio.run(h.recall("sshd"))
    assert "Self-knowledge search failed" not in caplog.text
    assert any(m["content"] == "sshd listens on 22" for m in mems)


def test_hybrid_search_self_knowledge_keeps_dict_shaped_stores():
    class DictSK:
        def search(self, query, k=5):
            return [{"id": "d1", "content": "dict content", "score": 0.9}]
    results = asyncio.run(_hybrid(DictSK())._search_self_knowledge("x", limit=2))
    assert results[0]["content"] == "dict content"
    assert results[0]["relevance"] == 0.9


def test_hybrid_store_self_knowledge_builds_knowledge_entry(caplog):
    from halbert_core.knowledge.self_knowledge import KnowledgeEntry, KnowledgeType
    from halbert_core.memory.hybrid import MemoryType
    sk = _RealSigSK()
    h = _hybrid(sk)
    with caplog.at_level(logging.WARNING):
        asyncio.run(h.store("backups live on /Volumes/4TB", MemoryType.SEMANTIC,
                            metadata={"subject": "backups", "tags": ["disk"]}))
    assert "Failed to store memory" not in caplog.text
    assert len(sk.added) == 1
    entry = sk.added[0]
    assert isinstance(entry, KnowledgeEntry)
    assert entry.content == "backups live on /Volumes/4TB"
    assert entry.subject == "backups"
    assert entry.type == KnowledgeType.OBSERVATION
    assert entry.tags == ["disk"]


def test_hybrid_store_self_knowledge_skips_incompatible_store_quietly(caplog):
    from halbert_core.memory.hybrid import MemoryType

    class NoAdd:
        def search(self, query, k=5):
            return []
    h = _hybrid(NoAdd())
    with caplog.at_level(logging.WARNING):
        asyncio.run(h.store("x", MemoryType.SEMANTIC))
    assert caplog.text == ""


def test_hybrid_embedding_wiring_uses_rag_embedding_manager(monkeypatch, caplog):
    """No dead halbert_core.model.embeddings import; wires rag.embeddings.EmbeddingManager."""
    import numpy as np
    import halbert_core.rag.embeddings as emb
    from halbert_core.memory.hybrid import HybridMemorySystem

    class FakeManager:
        def __init__(self, *a, **kw):
            pass
        def encode_queries(self, queries, batch_size=32):
            return np.array([[0.1, 0.2, 0.3] for _ in queries])
    monkeypatch.setattr(emb, "EmbeddingManager", FakeManager)

    h = HybridMemorySystem(vector_store=False, knowledge_graph=False, self_knowledge=False)
    with caplog.at_level(logging.WARNING):
        h._ensure_initialized()
    assert "Embedding service not available" not in caplog.text
    assert h.embeddings is not None
    vec = asyncio.run(h._get_embedding("hello"))
    assert vec == [0.1, 0.2, 0.3]
