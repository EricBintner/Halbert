# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Hermes fixtures.py pattern: a deterministic synthetic corpus with planted
facts every N turns, so the harness itself is CI-testable without models."""

from halbert_core.continuity.corpus import (
    EVAL_DOMAINS,
    PlantedFact,
    content_digest,
    planted_facts,
    synthetic_thread,
)


def test_deterministic():
    a = synthetic_thread(seed=7, turns=40)
    b = synthetic_thread(seed=7, turns=40)
    assert a == b
    c = synthetic_thread(seed=8, turns=40)
    assert a != c


def test_facts_planted_every_ten_turns():
    thread = synthetic_thread(seed=7, turns=40)
    facts = planted_facts(thread)
    assert len(facts) >= 4  # one fact per 10 turns
    assert all(f.source_turn % 10 == 0 for f in facts)


def test_facts_recoverable_from_text():
    thread = synthetic_thread(seed=7, turns=40)
    facts = planted_facts(thread)
    assert all(f.statement in thread.messages[f.source_turn].content for f in facts)


def test_facts_carry_a_question_and_gold():
    """The exam protocol needs one template question per fact, with the
    planted value as gold — no LLM in question generation."""
    thread = synthetic_thread(seed=7, turns=40)
    for f in planted_facts(thread):
        stem = f.statement[: -len(f.gold)].strip()  # "the garage keypad code is"
        assert stem.endswith(" is")
        name = stem[: -len(" is")]
        assert f.question == f"what is {name}?"
        assert f.statement.endswith(f.gold)


def test_messages_index_matches_turn_number():
    thread = synthetic_thread(seed=7, turns=40)
    assert len(thread.messages) == 40
    # planted turns are user turns; the alternation stays plausible
    assert thread.messages[0].role == "user"
    assert all(m.role in ("user", "assistant") for m in thread.messages)


def test_domains_match_device_vocabulary():
    """The eval corpus speaks the ledger's real subject vocabulary (scanner,
    printer, HA devices) so FTS/tokenization behaves like production."""
    for seed in range(1, 10):
        thread = synthetic_thread(seed=seed, turns=40)
        assert thread.domain in EVAL_DOMAINS
        assert thread.entities[0] in EVAL_DOMAINS[thread.domain]["entities"]


def test_content_digest_is_stable_and_seed_sensitive():
    a = synthetic_thread(seed=7, turns=40)
    b = synthetic_thread(seed=7, turns=40)
    c = synthetic_thread(seed=8, turns=40)
    assert content_digest(a.messages) == content_digest(b.messages)
    assert content_digest(a.messages) != content_digest(c.messages)
    assert content_digest(a.messages[:20]) != content_digest(a.messages)
    assert len(content_digest(a.messages)) == 64