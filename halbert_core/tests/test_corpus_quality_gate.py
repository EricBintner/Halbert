# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The corpus quality gate's reading of the daemon's context response.

The gate read ``resp.json()["chunks"]``, but SourcePrep replies

    {"success": true, "data": {"chunks": [...], "context": "..."}, "error": null}

with each chunk carrying ``text`` and ``source_path`` — not ``content`` and
``file_path``. Four mismatches, all confirmed against the live daemon, and the
consequence was total: ``chunks`` was always ``[]``, so every query scored as
failed and no gate was protecting any retrieval work. The scoped runner shares
the defect, which means its ``forbidden_path_prefix`` scope-isolation
assertion — the half its own comment calls load-bearing — has never fired
either, because it tested an always-empty path list.
"""

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
GATE = REPO_ROOT / "scripts" / "corpus_quality_gate.py"


@pytest.fixture(scope="module")
def gate():
    spec = importlib.util.spec_from_file_location("corpus_quality_gate", GATE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _daemon_response(chunks=None, context=None):
    """The live daemon's envelope, verbatim in shape."""
    data = {"total_chars": 0, "estimated_tokens": 0, "compression": 1.0}
    if chunks is not None:
        data["chunks"] = chunks
    if context is not None:
        data["context"] = context
    return {"success": True, "data": data, "error": None}


def _chunk(source_path, text, score=0.5):
    return {
        "source_path": source_path,
        "text": text,
        "score": score,
        "section": "x",
        "lod": 0,
    }


class TestExtractChunks:
    def test_chunks_nested_under_data_are_found(self, gate):
        payload = _daemon_response([_chunk("knowledge/linux/tldr/a.md", "journalctl")])
        assert len(gate.extract_chunks(payload)) == 1

    def test_text_is_read_as_content(self, gate):
        payload = _daemon_response([_chunk("k/l/a.md", "how to configure sshd")])
        assert gate.extract_chunks(payload)[0]["content"] == "how to configure sshd"

    def test_source_path_is_read_as_file_path(self, gate):
        payload = _daemon_response([_chunk("knowledge/linux/tldr/a.md", "t")])
        assert gate.extract_chunks(payload)[0]["file_path"] == "knowledge/linux/tldr/a.md"

    def test_the_score_survives(self, gate):
        payload = _daemon_response([_chunk("k/l/a.md", "t", score=0.77)])
        assert gate.extract_chunks(payload)[0]["score"] == 0.77

    def test_the_shape_the_gate_used_to_assume_yields_nothing(self, gate):
        # Documents the defect: chunks at the top level is not what the daemon
        # sends, and reading there is what made every query score as failed.
        assert gate.extract_chunks({"chunks": [_chunk("k/l/a.md", "t")]}) == []

    def test_ambient_mode_falls_back_to_the_context_string(self, gate):
        out = gate.extract_chunks(_daemon_response(context="some prose"))
        assert [c["content"] for c in out] == ["some prose"]

    def test_an_empty_response_yields_no_chunks(self, gate):
        assert gate.extract_chunks(_daemon_response()) == []

    def test_a_failed_response_yields_no_chunks(self, gate):
        assert gate.extract_chunks({"success": False, "data": None, "error": "x"}) == []

    def test_non_mapping_entries_are_skipped(self, gate):
        payload = _daemon_response([_chunk("k/l/a.md", "t"), "junk", None])
        assert len(gate.extract_chunks(payload)) == 1

    def test_a_chunk_missing_its_keys_does_not_raise(self, gate):
        assert gate.extract_chunks(_daemon_response([{}])) == [
            {"content": "", "file_path": "", "score": 0.0}
        ]


class TestScoringReadsRealChunks:
    """The gate's own pass criteria, fed the daemon's real shape."""

    def test_expected_terms_match_against_text_and_source_path(self, gate):
        payload = _daemon_response(
            [_chunk("knowledge/linux/tldr/sshd.md", "Port 22 and sshd_config")]
        )
        chunks = gate.extract_chunks(payload)
        haystack = " ".join(
            c.get("content", "") + " " + c.get("file_path", "") for c in chunks
        ).lower()
        assert all(t in haystack for t in ("ssh", "sshd", "config", "port"))

    def test_scope_isolation_can_now_see_a_forbidden_path(self, gate):
        # all_paths was always empty, so this assertion could never fail.
        payload = _daemon_response([_chunk("knowledge/macos/man-pages/a.md", "t")])
        paths = [c.get("file_path", "") for c in gate.extract_chunks(payload)]
        assert any(p.startswith("knowledge/macos/") for p in paths)
