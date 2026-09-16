# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""A02-G3 — the arm that measures what production actually does.

The harness scored four arms and none of them retrieved anything, so the
scorecard answered a question nobody is asking. Production never destroys a
region: the Consolidator only *adds* durable facts, the raw turns stay in
the store, and `recall_gate` reaches them by FTS. So the real user-facing
recall after an idle consolidation pass is "durable facts **plus** receipt
retrieval" — and a founder reading CONSOLIDATOR_DETERMINISTIC at 0.000 would
conclude the deterministic pass loses everything, which is not what the
machine does. Worse in the other direction: an LLM arm that beats
TRUNCATE_OLDEST but loses to deterministic+retrieval would have been opened
on a comparison that never included the option it was competing with.

The sonnet session that built the rest of the harness stopped here and said
why: retrieval is *per question*, and `Arm.policy(thread, region) ->
Retained` returns one text for the whole bank. It escalated rather than
force-fit, which was right.

The seam it was looking for is one layer down. The policy is not where a
question is seen — the *answerer* is, and `_run_arm` already builds one from
the retained text. So the arm keeps its policy exactly, and says how its
retained text becomes an answerer. Nothing the policy sees changes, which is
what the region-scoping sentinel pins.
"""

import pytest

from halbert_core.continuity import corpus, eval_consolidation
from halbert_core.continuity.eval_consolidation import (
    Arm,
    Retained,
    default_arms,
    recovery_answerer,
)


def _matrix(tmp_path, threads, arms, region):
    return eval_consolidation.run_matrix(
        threads=threads, arms=arms, region=region,
        cache_dir=tmp_path / "cache",
    )


def _row(report, arm_name):
    return next(r for r in report.rows if r.arm == arm_name)


# ---------------------------------------------------------------------------
# The arm exists, and it is not the bare one
# ---------------------------------------------------------------------------

class TestTheRecoveryArmIsInTheMatrix:
    def test_the_default_matrix_offers_one(self):
        arms = {a.name for a in default_arms(_StubStore())}
        assert "CONSOLIDATOR_DETERMINISTIC+RECOVERY" in arms

    def test_it_is_open_by_default(self):
        """No gate: there is no model anywhere in it.

        The retrieval is keyword FTS over the region — the same read path
        `recall_gate` uses in production. A gate here would hold back the
        one arm that measures the shipped behaviour.
        """
        arm = next(
            a for a in default_arms(_StubStore())
            if a.name == "CONSOLIDATOR_DETERMINISTIC+RECOVERY"
        )
        assert arm.gate == "open"


# ---------------------------------------------------------------------------
# What it measures
# ---------------------------------------------------------------------------

class TestRecoveryBeatsTheBareArm:
    def test_retrieval_finds_what_the_durable_facts_dropped(self, tmp_path):
        thread = corpus.synthetic_thread(seed=7, turns=40)

        bare = Arm(
            name="EMPTY",
            policy=lambda t, r: Retained(text=""),
        )
        recovered = Arm(
            name="EMPTY+RECOVERY",
            policy=lambda t, r: Retained(text=""),
            answerer=recovery_answerer(top_k=5),
        )
        report = _matrix(tmp_path, [thread], [bare, recovered], (0, 20))

        bare_row = _row(report, "EMPTY")
        rec_row = _row(report, "EMPTY+RECOVERY")
        assert bare_row.status == "OK" and rec_row.status == "OK"
        assert rec_row.recall > bare_row.recall, (
            "retrieval over the region recovered nothing an empty policy lost"
        )

    def test_it_never_scores_below_its_base(self, tmp_path):
        """Retrieval is concatenated, never substituted.

        An arm that answered *only* from what it retrieved could score worse
        than its own base — which would make the scorecard say retrieval
        hurts, when what happened is that the base's text was thrown away.
        """
        thread = corpus.synthetic_thread(seed=11, turns=40)
        base_policy = eval_consolidation.truncate_oldest_policy(keep_turns=4)
        base = Arm(name="BASE", policy=base_policy)
        recovered = Arm(
            name="BASE+RECOVERY",
            policy=base_policy,
            answerer=recovery_answerer(top_k=5),
        )
        report = _matrix(tmp_path, [thread], [base, recovered], (0, 20))
        assert _row(report, "BASE+RECOVERY").recall >= _row(report, "BASE").recall

    def test_retained_tokens_count_what_was_retrieved(self, tmp_path):
        """The cost side of the comparison has to be honest.

        An arm that recalls more because it read more is not free, and a
        scorecard that shows the recall without the tokens is an argument
        for retrieval that nobody can check.
        """
        thread = corpus.synthetic_thread(seed=7, turns=40)
        base = Arm(name="BASE", policy=lambda t, r: Retained(text=""))
        recovered = Arm(
            name="BASE+RECOVERY",
            policy=lambda t, r: Retained(text=""),
            answerer=recovery_answerer(top_k=5),
        )
        report = _matrix(tmp_path, [thread], [base, recovered], (0, 20))
        assert _row(report, "BASE").retained_tokens == 0
        assert _row(report, "BASE+RECOVERY").retained_tokens > 0


# ---------------------------------------------------------------------------
# What must not have changed
# ---------------------------------------------------------------------------

class TestTheInvariantsHold:
    def test_a_recovery_arm_still_sees_only_the_region(self, tmp_path):
        """The sentinel, run against the new seam.

        Retrieval reaches further than the base policy's text by design —
        that is the whole arm — but not further than the REGION. A recovery
        answerer that could see the preserved tail would be scoring the
        harness against itself.
        """
        thread = corpus.synthetic_thread(seed=7, turns=30)
        thread.messages[0].content += " SENTINELHEAD"
        thread.messages[15].content += " SENTINELMIDDLE"
        thread.messages[29].content += " SENTINELTAIL"

        seen = []

        def spy_answerer(retained, region):
            seen.append(list(region))
            return lambda question: "NOT IN CONTEXT"

        arm = Arm(
            name="SPY",
            policy=lambda t, r: Retained(text="nothing"),
            answerer=spy_answerer,
        )
        _matrix(tmp_path, [thread], [arm], (0, 10))

        assert len(seen) == 1
        contents = " | ".join(m.content for m in seen[0])
        assert "SENTINELHEAD" in contents
        assert "SENTINELMIDDLE" not in contents
        assert "SENTINELTAIL" not in contents

    def test_an_arm_without_an_answerer_is_unchanged(self, tmp_path):
        """Additive: the default is exactly the context answerer it was."""
        thread = corpus.synthetic_thread(seed=7, turns=40)
        policy = eval_consolidation.verbatim_policy()
        before = _matrix(tmp_path, [thread], [Arm(name="A", policy=policy)], (0, 20))
        after = _matrix(tmp_path, [thread], [Arm(name="A", policy=policy)], (0, 20))
        assert _row(before, "A").recall == _row(after, "A").recall
        assert _row(after, "A").recall == 1.0

    def test_no_model_is_reachable_from_the_recovery_path(self):
        """The standing rule: never a model where a template suffices.

        Grepped over the CODE, with the docstrings stripped — the existing
        module-level version of this test carries a hand-written carve-out
        for one prose phrase, which is a lint that gets weaker every time
        someone explains themselves in a comment.
        """
        import ast
        import inspect

        tree = ast.parse(inspect.getsource(recovery_answerer).strip())
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                                 ast.ClassDef, ast.Module)):
                doc = ast.get_docstring(node, clean=False)
                if doc is not None and node.body:
                    node.body = node.body[1:] or [ast.Pass()]
        code = ast.unparse(ast.fix_missing_locations(tree)).lower()
        for forbidden in ("llm", "summarizer", "chat(", "resolve_aux_model",
                          "model"):
            assert forbidden not in code, f"{forbidden!r} reachable"

    def test_the_answerer_never_sees_the_bank_row(self, tmp_path):
        """Gold stays withheld (A02-G1), through the new seam too."""
        thread = corpus.synthetic_thread(seed=7, turns=40)
        asked = []

        def spy_answerer(retained, region):
            def answer(question, *args, **kwargs):
                asked.append((question, args, kwargs))
                return "NOT IN CONTEXT"
            return answer

        arm = Arm(
            name="SPY",
            policy=lambda t, r: Retained(text=""),
            answerer=spy_answerer,
        )
        _matrix(tmp_path, [thread], [arm], (0, 20))
        assert asked, "the answerer was never called"
        for _question, args, kwargs in asked:
            assert not args and not kwargs, (
                "the answerer was handed more than the question text"
            )


class _StubStore:
    def current_state(self, *, subject, strict=False):
        return []
