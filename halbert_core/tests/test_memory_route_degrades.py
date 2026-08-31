# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""U6 S5/W20-W21: the Memory dashboard degrades sanely without ChromaDB.

A home node never installs [rag-legacy] (it bundles chromadb), so the
Memory page's index endpoints must render a clean 'chromadb_available:
false' state rather than 500-ing or spamming warnings. D3 resolution: no
packaging change — the operative agent path is receipts/FTS5 recall
(memory_service=None), and persona memory embeddings are served by the
haloysius ONNX/Ollama embedder, never halbert_core's
sentence-transformers (which stays in [rag-legacy] only, a sysadmin
extra).
"""

from unittest.mock import patch

from halbert_core.dashboard.routes.memory import get_index_stats


class TestMemoryRouteDegrades:
    def test_stats_endpoint_reports_unavailable_not_error_page(self):
        """get_index raising (no chromadb installed / index dir missing)
        must surface a structured 'chromadb_available: false' payload."""
        import asyncio
        with patch(
            "halbert_core.index.chroma_index.get_index",
            side_effect=ModuleNotFoundError("No module named 'chromadb'"),
        ):
            result = asyncio.run(get_index_stats())
        assert result["status"] == "error"
        assert result["chromadb_available"] is False
        assert "chromadb" in result["error"]