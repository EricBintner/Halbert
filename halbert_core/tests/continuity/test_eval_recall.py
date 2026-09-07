# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The exam protocol (Hermes compaction eval):

(1) questions are generated FROM the to-be-destroyed/merged region and cached by
content hash — every policy answers the identical exam;
(2) the answerer is closed-book with a forced NOT_IN_CONTEXT option (measures
hallucination and recall in one instrument);
(3) the judge sees gold; a correct guess is scored partial (hedging measured).
"""

from halbert_core.continuity.corpus import (
    content_digest,
    planted_facts,
    synthetic_thread,
)
from halbert_core.continuity.recall_eval import (
    LLM_JUDGE_ENABLED,
    answer_prompt,
    context_answerer,
    judge_score,
    question_bank,
    run_exam,
)


def _facts(seed=7, turns=40):
    return planted_facts(synthetic_thread(seed=seed, turns=turns))


def test_bank_cached_by_content_hash(tmp_path):
    thread_digest = "a" * 64
    facts = _facts()
    bank = question_bank(thread_digest, facts=facts, cache_dir=tmp_path)
    bank2 = question_bank(thread_digest, facts=facts, cache_dir=tmp_path)
    assert (tmp_path / f"questions-{thread_digest[:10]}.json").exists()
    assert bank == bank2  # second call served from cache


def test_bank_has_one_question_per_fact(tmp_path):
    facts = _facts()
    bank = question_bank("b" * 64, facts=facts, cache_dir=tmp_path)
    assert len(bank) == len(facts)
    assert {row["gold"] for row in bank} == {f.gold for f in facts}
    assert {row["question"] for row in bank} == {f.question for f in facts}


def test_answer_forced_not_in_context_option():
    prompt = answer_prompt([], question="what is the garage keypad code?")
    assert "NOT IN CONTEXT" in prompt
    assert "Question: what is the garage keypad code?" in prompt


def test_judge_scores_partial_for_hedged_guess():
    verdict = judge_score(
        gold="47-29", answer="NOT IN CONTEXT — possibly 47-29 based on the pattern")
    assert verdict == 1  # 2 correct / 1 partial / 0 wrong


def test_judge_scores_correct():
    assert judge_score(gold="47-29", answer="47-29") == 2


def test_judge_scores_wrong_and_refusal():
    assert judge_score(gold="47-29", answer="NOT IN CONTEXT") == 0
    assert judge_score(gold="47-29", answer="the code is 11-11") == 0
    assert judge_score(gold="47-29", answer="") == 0


def test_llm_judge_is_flag_off():
    """The programmatic judge is the oracle of record; an LLM judge (for
    free-text variance a regex cannot score) exists only as a flag-off hook
    routed through the model-picker's slots."""
    assert LLM_JUDGE_ENABLED is False


def test_run_exam_closed_book():
    thread = synthetic_thread(seed=7, turns=40)
    region = thread.messages[:20]
    facts = [f for f in planted_facts(thread) if f.source_turn < 20]
    bank = question_bank(content_digest(region), facts=facts, cache_dir=None)

    full = run_exam(bank, context_answerer("\n".join(m.content for m in region)))
    assert full.summary()["n"] == len(bank)
    assert full.summary()["correct"] == len(bank)
    assert full.summary()["recall"] == 1.0

    empty = run_exam(bank, context_answerer(""))
    assert empty.summary()["correct"] == 0
    assert all(v.score == 0 for v in empty.verdicts)
    # a refusal is distinguishable from a wrong guess
    assert all(v.answer == "NOT IN CONTEXT" for v in empty.verdicts)