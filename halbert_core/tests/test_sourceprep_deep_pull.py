# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The retrieval backend's deep pull + per-source cap.

The cap can only choose from what the candidate list contains, so the backend
has to ask the daemon for more candidates than the caller wants (k=50) and for
enough character budget to carry them (max_chars=60000). Both are prerequisites
measured to be worth nothing on their own — raising max_chars alone scored the
same 9/15 as the baseline — and everything together scored 14/15.
"""

from __future__ import annotations

from halbert_core.integrations.sourceprep_retrieval_backend import (
    SourcePrepRetrievalBackend,
)


class _RecordingClient:
    """Stands in for SourcePrepClient; records the request, replays a corpus."""

    def __init__(self, chunks=None):
        self.calls = []
        self.chunks = chunks if chunks is not None else []
        self.project_id = "pid"

    def get_context(self, **kwargs):
        self.calls.append(kwargs)
        return {"data": {"chunks": self.chunks}}

    def health(self):
        return True


def _chunk(path, score=0.0):
    return {"text": f"text for {path}", "source_path": path, "score": score}


AW = "knowledge/linux/arch-wiki/arch_wiki_{}.md"
WS = "knowledge/linux/webserver-docs/webserver_docs_{}.md"


def _skewed_corpus():
    """Six arch-wiki chunks outranking the webserver-docs chunk with the answer."""
    chunks = [_chunk(AW.format(i), score=0.90 - i / 100) for i in range(6)]
    chunks.append(_chunk(WS.format(0), score=0.80))
    chunks += [
        _chunk(f"knowledge/linux/topic{i}/f.md", score=0.70 - i / 100)
        for i in range(6)
    ]
    return chunks


# ── S0: the deep pull needs budget ────────────────────────────────────


def test_pulls_more_candidates_than_the_caller_asked_for():
    client = _RecordingClient()
    SourcePrepRetrievalBackend(client=client).search("nginx reverse proxy", k=5)
    assert client.calls[0]["k"] == 50


def test_asks_for_enough_character_budget_to_carry_the_deep_pull():
    # max_chars binds: at k=25 the same query returns 9 chunks at 12000 and 17
    # at 60000. Without the budget the candidate list is truncated before the
    # cap can choose from it.
    client = _RecordingClient()
    SourcePrepRetrievalBackend(client=client).search("q", k=5)
    assert client.calls[0]["max_chars"] == 60000


def test_never_pulls_shallower_than_the_caller_asked_for():
    client = _RecordingClient()
    SourcePrepRetrievalBackend(client=client).search("q", k=80)
    assert client.calls[0]["k"] == 80


# ── S1: cap, then trim ────────────────────────────────────────────────


def test_returns_the_requested_count_not_the_pull_depth():
    client = _RecordingClient(_skewed_corpus())
    out = SourcePrepRetrievalBackend(client=client).search("q", k=5)
    assert len(out) == 5


def test_the_small_directory_holding_the_answer_reaches_the_result():
    client = _RecordingClient(_skewed_corpus())
    out = SourcePrepRetrievalBackend(client=client).search("q", k=5)
    paths = [r["source_path"] for r in out]
    assert WS.format(0) in paths


def test_the_giant_is_capped_to_one_slot_not_excluded():
    client = _RecordingClient(_skewed_corpus())
    out = SourcePrepRetrievalBackend(client=client).search("q", k=5)
    arch = [r for r in out if "arch-wiki" in r["source_path"]]
    assert len(arch) == 1
    # and it keeps the rank-1 position it earned
    assert out[0]["source_path"] == AW.format(0)


def test_uncapped_baseline_would_have_returned_all_giant():
    # Documents the defect being fixed: without the cap the top 5 are the six
    # arch-wiki chunks, and webserver-docs never appears.
    client = _RecordingClient(_skewed_corpus())
    backend = SourcePrepRetrievalBackend(client=client, source_cap=0)
    out = backend.search("q", k=5)
    assert all("arch-wiki" in r["source_path"] for r in out)


# ── The off switch ────────────────────────────────────────────────────


def test_disabling_the_cap_restores_the_shallow_pull():
    # An A/B against the pre-cap behaviour has to be an A/B on latency too,
    # so turning the cap off must not leave the expensive request behind.
    client = _RecordingClient()
    SourcePrepRetrievalBackend(client=client, source_cap=0).search("q", k=5)
    assert client.calls[0]["k"] == 5


def test_pull_depth_and_cap_size_are_configurable():
    client = _RecordingClient(_skewed_corpus())
    backend = SourcePrepRetrievalBackend(client=client, source_cap=2, pull_k=25)
    out = backend.search("q", k=5)
    assert client.calls[0]["k"] == 25
    assert sum(1 for r in out if "arch-wiki" in r["source_path"]) == 2


# ── The pool is score-ordered before it is capped ─────────────────────


LOG = "knowledge/linux/logging-docs/logging_docs_01.md"


def _inverted_corpus():
    """The live ``journalctl filter by unit since boot`` pool, in miniature.

    The daemon returns chunks out of score order. ``logging-docs`` — which
    holds the answer — arrives *last*, behind five other distinct directories,
    yet outscores three of them. In daemon order it is the 6th distinct
    directory, so a cap of 1 at k=5 drops it; by score it is 3rd and survives.

    man-pages/arch-wiki-ext are also transposed against their scores, so the
    daemon order is inverted *within* the first five as well as at the tail.
    """
    return [
        _chunk("knowledge/linux/tldr/tldr_02.md", score=0.7761),
        _chunk(AW.format(0), score=0.6574),
        _chunk("knowledge/macos/man-pages/man_01.md", score=0.6110),
        _chunk("knowledge/linux/arch-wiki-ext/ext_01.md", score=0.6243),
        _chunk("knowledge/macos/homebrew/brew_01.md", score=0.6059),
        _chunk(LOG, score=0.6248),
    ]


def test_a_high_scoring_answer_ranked_late_by_the_daemon_still_reaches_the_result():
    client = _RecordingClient(_inverted_corpus())
    out = SourcePrepRetrievalBackend(client=client).search("journalctl by unit", k=5)
    assert LOG in [r["source_path"] for r in out]


def test_the_returned_chunks_are_in_score_order():
    client = _RecordingClient(_inverted_corpus())
    out = SourcePrepRetrievalBackend(client=client).search("q", k=5)
    scores = [r["score"] for r in out]
    assert scores == sorted(scores, reverse=True)


def test_the_lower_scoring_chunk_is_the_one_displaced():
    # homebrew (0.6059) is the weakest of the six and is what logging-docs
    # (0.6248) takes the slot from — not one of the stronger directories.
    client = _RecordingClient(_inverted_corpus())
    out = SourcePrepRetrievalBackend(client=client).search("q", k=5)
    paths = [r["source_path"] for r in out]
    assert "knowledge/macos/homebrew/brew_01.md" not in paths


def test_disabling_the_cap_also_leaves_the_daemon_order_untouched():
    # The A/B arm must reproduce the pre-cap behaviour exactly, sort included.
    client = _RecordingClient(_inverted_corpus())
    out = SourcePrepRetrievalBackend(client=client, source_cap=0).search("q", k=5)
    assert [r["score"] for r in out] == [0.7761, 0.6574, 0.6110, 0.6243, 0.6059]


def test_equal_scores_keep_the_daemon_order():
    client = _RecordingClient(
        [_chunk(f"knowledge/linux/d{i}/f.md", score=0.5) for i in range(4)]
    )
    out = SourcePrepRetrievalBackend(client=client).search("q", k=4)
    assert [r["source_path"] for r in out] == [
        f"knowledge/linux/d{i}/f.md" for i in range(4)
    ]


# ── Scope interaction ─────────────────────────────────────────────────


def test_the_cap_still_applies_to_a_scoped_query():
    # A scope is candidate removal plus a constant score offset — it does not
    # re-rank within the scope, so knowledge_linux still contains all 2,331
    # arch-wiki documents and the dominance problem is entirely intact.
    client = _RecordingClient(_skewed_corpus())
    out = SourcePrepRetrievalBackend(client=client).search(
        "q", k=5, figure_id="knowledge_linux"
    )
    assert client.calls[0]["scope"] == "knowledge_linux"
    assert sum(1 for r in out if "arch-wiki" in r["source_path"]) == 1


# ── Failure modes must not regress ────────────────────────────────────


def test_empty_query_still_short_circuits():
    client = _RecordingClient()
    assert SourcePrepRetrievalBackend(client=client).search("   ") == []
    assert client.calls == []


def test_client_failure_still_returns_empty():
    class _Boom:
        project_id = "pid"

        def get_context(self, **kwargs):
            raise RuntimeError("daemon down")

    assert SourcePrepRetrievalBackend(client=_Boom()).search("q") == []


def test_ambient_response_without_chunks_survives_the_cap():
    class _Ambient:
        project_id = "pid"

        def get_context(self, **kwargs):
            return {"data": {"context": "some prose"}}

    out = SourcePrepRetrievalBackend(client=_Ambient()).search("q", k=5)
    assert out == [{"text": "some prose", "source_path": "", "score": 0.0}]


def test_all_chunks_from_one_source_still_fill_the_result():
    # Backfill: the capped path must never return fewer chunks than the
    # uncapped path would have.
    client = _RecordingClient([_chunk(AW.format(i), score=0.9 - i / 100) for i in range(8)])
    out = SourcePrepRetrievalBackend(client=client).search("q", k=5)
    assert len(out) == 5
