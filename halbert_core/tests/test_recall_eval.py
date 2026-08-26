# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Recall quality under load (handoff R5).

Every other recall test in this repo runs at one or two threads, where any search
looks perfect. These run at 10 through 500 and pin the decay, so a retrieval
regression fails here instead of showing up as Halbert quietly recalling the
wrong conversation a year from now.

No LLM in the evaluation loop: every number below is computed from structured
output and is reproducible from the seed.
"""

import pytest

from halbert_core.continuity.corpus import DOMAIN_VOCAB, Domain, generate_corpus
from halbert_core.continuity.recall_eval import (
    ReceiptIndex,
    cumulative_curve,
    evaluate,
    format_curve,
)


class TestCorpus:
    def test_is_deterministic(self):
        a = generate_corpus(20, seed=7)
        b = generate_corpus(20, seed=7)
        assert [t.receipt for t in a] == [t.receipt for t in b]

    def test_spreads_across_every_domain(self):
        domains = {t.domain for t in generate_corpus(len(Domain.ALL) * 3)}
        assert domains == set(Domain.ALL)

    def test_receipt_has_the_nine_plan_a_sections(self):
        lines = generate_corpus(1)[0].receipt.splitlines()
        assert [l.split(":")[0] for l in lines] == [
            "Title", "When", "Domains", "Entities", "Started with",
            "Last said (2026-07-01)", "Commands", "Files written", "Open loop"]

    def test_queries_share_vocabulary_so_competition_is_real(self):
        """A unique token per thread would make every search trivially perfect.

        Primaries must come from the bounded domain vocabulary, so threads
        genuinely compete for the same query terms as the store grows.
        """
        corpus = generate_corpus(200)
        primaries = [t.query_entities[0] for t in corpus]
        vocab_size = sum(len(v["entities"]) for v in DOMAIN_VOCAB.values())
        assert len(set(primaries)) <= vocab_size
        assert len(set(primaries)) < len(primaries) / 3

    def test_every_domain_has_vocabulary(self):
        for d in Domain.ALL:
            assert DOMAIN_VOCAB[d]["entities"] and DOMAIN_VOCAB[d]["files"]


class TestIndex:
    def test_finds_an_indexed_receipt(self):
        idx = ReceiptIndex()
        corpus = generate_corpus(10)
        idx.add_all(corpus)
        assert corpus[0].thread_id in idx.search(corpus[0].query)
        idx.close()

    def test_empty_query_returns_nothing(self):
        idx = ReceiptIndex()
        idx.add_all(generate_corpus(5))
        assert idx.search("a of") == []
        idx.close()

    def test_no_match_is_a_normal_empty_result(self):
        idx = ReceiptIndex()
        idx.add_all(generate_corpus(5))
        assert idx.search("xylophone quokka") == []
        idx.close()


class TestDecayUnderLoad:
    """The finding this harness exists to catch."""

    def test_small_store_is_effectively_perfect(self):
        m = evaluate(generate_corpus(10))
        assert m.hit_at_1 >= 0.95

    def test_top_1_degrades_measurably_by_500(self):
        small = evaluate(generate_corpus(10))
        large = evaluate(generate_corpus(500))
        assert large.hit_at_1 < small.hit_at_1 - 0.2, (
            "expected measurable top-1 decay; if retrieval improved, re-baseline")

    def test_top_5_holds_up(self):
        """Weak-match (offer candidates) survives where strong-match does not."""
        assert evaluate(generate_corpus(500)).hit_at_5 >= 0.95

    @pytest.mark.parametrize("n,floor", [(10, 0.95), (100, 0.90), (500, 0.55)])
    def test_regression_floors(self, n, floor):
        """Pinned floors. A drop below these is a retrieval regression."""
        assert evaluate(generate_corpus(n)).hit_at_1 >= floor

    def test_competition_becomes_intra_domain_as_the_store_grows(self):
        """At scale the wrong candidates are same-domain, so a domain filter
        alone cannot fix precision — recorded because it revises the design."""
        assert evaluate(generate_corpus(10)).cross_domain_rate > 0.5
        assert evaluate(generate_corpus(500)).cross_domain_rate < 0.05


def test_curve_renders(capsys):
    rows = cumulative_curve((10, 100))
    out = format_curve(rows)
    assert "hit@1" in out and len(out.splitlines()) == 4
