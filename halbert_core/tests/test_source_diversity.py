# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Per-source-directory diversity cap — pure ranking policy, no daemon.

The corpus is skewed by document count: knowledge/linux/arch-wiki holds 2,331
documents and knowledge/macos/man-pages ~5,280, while the topic directories
that usually hold the precise answer hold 10-70 each. The giants therefore win
top-k on volume alone. The cap pulls a deep candidate list and keeps at most
one chunk per source directory, which was measured (see
documentation/design/KNOWLEDGE-SCOPE-REVISION-2026-08-27.md) at 14/15 against a
9/15 baseline, with zero regression on the five probes where a giant source
genuinely is the right answer.
"""

import logging

from halbert_core.integrations.source_diversity import (
    by_score_desc,
    cap_by_source_directory,
    source_directory,
)


# ── source_directory: the grouping key ────────────────────────────────


class TestSourceDirectory:
    def test_knowledge_path_groups_by_full_parent_directory(self):
        assert (
            source_directory("knowledge/linux/arch-wiki/arch_wiki_23.md")
            == "knowledge/linux/arch-wiki"
        )

    def test_sibling_files_share_a_key(self):
        a = source_directory("knowledge/linux/arch-wiki/arch_wiki_23.md")
        b = source_directory("knowledge/linux/arch-wiki/arch_wiki_04.md")
        assert a == b

    def test_different_topic_directories_do_not_share_a_key(self):
        a = source_directory("knowledge/linux/arch-wiki/arch_wiki_23.md")
        b = source_directory("knowledge/linux/webserver-docs/webserver_docs_01.md")
        assert a != b

    def test_same_directory_name_under_different_platforms_is_distinct(self):
        a = source_directory("knowledge/linux/man-pages/man_01.md")
        b = source_directory("knowledge/macos/man-pages/man_01.md")
        assert a != b

    def test_host_config_path_keeps_its_host_prefix(self):
        # host/** is the live config tree, not the reference corpus. Keeping
        # the leading segment stops it colliding with a knowledge directory
        # and keeps host directories at their natural (narrow) granularity.
        assert source_directory("host/etc/ssh/sshd_config") == "host/etc/ssh"
        assert (
            source_directory("host/Library/LaunchAgents/us.zoom.plist")
            == "host/Library/LaunchAgents"
        )

    def test_host_and_knowledge_never_collide(self):
        assert source_directory("host/etc/nginx/nginx.conf") != source_directory(
            "knowledge/linux/etc/nginx/nginx.conf"
        )

    def test_absolute_and_relative_forms_agree(self):
        assert source_directory("/etc/ssh/sshd_config") == source_directory(
            "etc/ssh/sshd_config"
        )

    def test_redundant_separators_are_normalised(self):
        assert (
            source_directory("knowledge//linux///arch-wiki/a.md")
            == "knowledge/linux/arch-wiki"
        )

    def test_surrounding_whitespace_is_ignored(self):
        assert (
            source_directory("  knowledge/linux/arch-wiki/a.md  ")
            == "knowledge/linux/arch-wiki"
        )

    def test_a_directory_shaped_path_keys_to_itself_not_its_parent(self):
        # A trailing slash means the path already IS the directory. Treating
        # its last segment as a filename walked one level too far up, and
        # collapsed every topic directory under a platform into one bucket —
        # the silent over-filter direction.
        assert (
            source_directory("knowledge/linux/arch-wiki/")
            == "knowledge/linux/arch-wiki"
        )

    def test_two_directory_shaped_paths_do_not_collapse_together(self):
        assert source_directory("knowledge/linux/arch-wiki/") != source_directory(
            "knowledge/linux/webserver-docs/"
        )

    def test_a_directory_shaped_path_agrees_with_its_files_key(self):
        assert source_directory("knowledge/linux/arch-wiki/") == source_directory(
            "knowledge/linux/arch-wiki/arch_wiki_01.md"
        )

    def test_dot_segments_are_resolved(self):
        assert (
            source_directory("knowledge/./linux/arch-wiki/a.md")
            == "knowledge/linux/arch-wiki"
        )

    def test_dotdot_segments_are_resolved(self):
        assert (
            source_directory("knowledge/linux/../macos/man-pages/x.md")
            == "knowledge/macos/man-pages"
        )

    def test_a_resolved_path_keys_the_same_as_the_direct_one(self):
        assert source_directory(
            "knowledge/linux/../macos/man-pages/x.md"
        ) == source_directory("knowledge/macos/man-pages/x.md")

    def test_a_path_escaping_the_corpus_root_is_unkeyable(self):
        # Nothing is known about where this actually lives, so it carries no
        # evidence of a shared source. None means "never cap" — the safe
        # direction, which can only under-filter.
        for bad in ["../etc/passwd", "..", "../..", "knowledge/../../x/y.md"]:
            assert source_directory(bad) is None, bad

    def test_unkeyable_paths_return_none(self):
        # No directory component means no evidence of a shared source.
        for bad in ["", "   ", "README.md", "/", "///", None, 17, [], {"a": 1}]:
            assert source_directory(bad) is None, bad


# ── cap_by_source_directory: the policy ───────────────────────────────


def _chunk(path, score=0.0, text="t"):
    return {"text": text, "source_path": path, "score": score}


AW = "knowledge/linux/arch-wiki/arch_wiki_{}.md"
MP = "knowledge/macos/man-pages/man_pages_{}.md"
WS = "knowledge/linux/webserver-docs/webserver_docs_{}.md"
BK = "knowledge/linux/backup-docs/backup_docs_{}.md"


# ── by_score_desc: the pool ordering ──────────────────────────────────


class TestByScoreDesc:
    """The daemon's chunk order is NOT score-descending.

    Measured against the live daemon: 12 of the 15 probe pools contain score
    inversions. On "journalctl filter by unit since boot",
    knowledge/linux/logging-docs sits at rank 25 of 29 with score 0.6248 —
    *behind* macos/homebrew (0.6059 at rank 18) and macos/man-pages (0.6110 at
    rank 11). It is the 6th distinct directory in daemon order, and a cap of 1
    at k=5 can surface only 5, so the answer is lost. Sorting the pool by score
    first makes it the 3rd distinct directory and rescues the probe.
    """

    def test_sorts_by_score_descending(self):
        chunks = [_chunk(WS.format(0), 0.1), _chunk(BK.format(0), 0.9)]
        assert [c["score"] for c in by_score_desc(chunks)] == [0.9, 0.1]

    def test_the_journalctl_inversion_is_corrected(self):
        # The live shape: the answer scores higher than chunks ranked above it.
        pool = [
            _chunk(MP.format(0), 0.6110),
            _chunk("knowledge/macos/homebrew/brew_01.md", 0.6059),
            _chunk("knowledge/linux/logging-docs/logging_01.md", 0.6248),
        ]
        top = by_score_desc(pool)[0]["source_path"]
        assert top == "knowledge/linux/logging-docs/logging_01.md"

    def test_is_stable_so_equal_scores_keep_daemon_order(self):
        chunks = [
            _chunk(AW.format(0), 0.5),
            _chunk(WS.format(0), 0.5),
            _chunk(BK.format(0), 0.5),
        ]
        out = by_score_desc(chunks)
        assert [c["source_path"] for c in out] == [
            AW.format(0),
            WS.format(0),
            BK.format(0),
        ]

    def test_missing_score_sorts_last(self):
        chunks = [{"source_path": WS.format(0)}, _chunk(BK.format(0), 0.1)]
        out = by_score_desc(chunks)
        assert [c["source_path"] for c in out] == [BK.format(0), WS.format(0)]

    def test_non_numeric_score_sorts_last(self):
        chunks = [_chunk(WS.format(0), "high"), _chunk(BK.format(0), 0.1)]
        out = by_score_desc(chunks)
        assert [c["source_path"] for c in out] == [BK.format(0), WS.format(0)]

    def test_nan_score_sorts_last(self):
        # NaN compares false against everything; left in the key it corrupts
        # the sort rather than merely misplacing one chunk.
        chunks = [_chunk(WS.format(0), float("nan")), _chunk(BK.format(0), 0.1)]
        out = by_score_desc(chunks)
        assert [c["source_path"] for c in out] == [BK.format(0), WS.format(0)]

    def test_booleans_are_not_scores(self):
        chunks = [_chunk(WS.format(0), True), _chunk(BK.format(0), 0.1)]
        out = by_score_desc(chunks)
        assert [c["source_path"] for c in out] == [BK.format(0), WS.format(0)]

    def test_uniformly_unscored_input_degrades_to_the_given_order(self):
        # The safety property of "unscored sorts last" plus a stable sort: if
        # the score key ever disappears wholesale, ordering falls back to the
        # daemon's own ranking rather than scrambling.
        chunks = [{"source_path": p} for p in (AW.format(0), WS.format(0), BK.format(0))]
        out = by_score_desc(chunks)
        assert [c["source_path"] for c in out] == [
            AW.format(0),
            WS.format(0),
            BK.format(0),
        ]

    def test_negative_scores_still_outrank_unscored(self):
        chunks = [{"source_path": WS.format(0)}, _chunk(BK.format(0), -5.0)]
        out = by_score_desc(chunks)
        assert [c["source_path"] for c in out] == [BK.format(0), WS.format(0)]

    def test_non_mapping_entries_do_not_raise(self):
        assert len(by_score_desc(["a", None, _chunk(WS.format(0), 0.5)])) == 3

    def test_empty_input_returns_empty(self):
        assert by_score_desc([]) == []

    def test_accepts_any_iterable(self):
        chunks = (_chunk(AW.format(i), score=i / 10) for i in range(4))
        assert [c["score"] for c in by_score_desc(chunks)] == [0.3, 0.2, 0.1, 0.0]

    def test_input_is_not_mutated_and_chunks_are_returned_as_is(self):
        a, b = _chunk(WS.format(0), 0.1), _chunk(BK.format(0), 0.9)
        chunks = [a, b]
        out = by_score_desc(chunks)
        assert chunks == [a, b]
        assert out[0] is b and out[1] is a


class TestCapRespected:
    """The cap in isolation. Backfill is disabled here so these assert the cap
    itself; the interaction between the two is TestBackfill's subject."""

    def test_keeps_one_chunk_per_directory_by_default(self):
        chunks = [_chunk(AW.format(i)) for i in range(6)]
        assert len(cap_by_source_directory(chunks, 5, backfill=False)) == 1

    def test_the_giant_keeps_its_single_best_slot_and_only_that_slot(self):
        # The control case: when a giant source genuinely is right, it must be
        # capped, not excluded. Both halves are asserted — the earlier version
        # of this test checked only that the giant held rank 1, which is also
        # true with the cap switched off, so it never tested the cap.
        chunks = [_chunk(AW.format(i), score=0.9 - i / 100) for i in range(3)]
        chunks += [
            _chunk(f"knowledge/linux/topic{i}/f.md", score=0.5 - i / 100)
            for i in range(4)
        ]
        out = cap_by_source_directory(chunks, 5)
        assert out[0]["source_path"] == AW.format(0)
        assert sum(1 for c in out if "arch-wiki" in c["source_path"]) == 1

    def test_cap_of_two_keeps_two(self):
        chunks = [_chunk(AW.format(i)) for i in range(6)]
        out = cap_by_source_directory(chunks, 5, per_source=2, backfill=False)
        assert len(out) == 2

    def test_deep_pull_of_giants_yields_the_small_directories(self):
        # Six arch-wiki chunks outrank the one webserver-docs chunk that holds
        # the answer. Baseline top-5 is all arch-wiki; the cap surfaces it.
        # The pool carries 5 distinct directories, so every slot is filled by
        # the cap and backfill never engages.
        chunks = [_chunk(AW.format(i), score=0.9 - i * 0.01) for i in range(6)]
        chunks += [
            _chunk(WS.format(0), score=0.80),
            _chunk(MP.format(0), score=0.79),
            _chunk(BK.format(0), score=0.78),
            _chunk("knowledge/linux/systemd-docs/systemd_docs_01.md", score=0.77),
        ]
        out = cap_by_source_directory(chunks, 5)
        paths = [c["source_path"] for c in out]
        assert len(out) == 5
        assert WS.format(0) in paths
        assert sum(1 for p in paths if "arch-wiki" in p) == 1

    def test_every_directory_appears_at_most_once_when_slots_are_filled(self):
        chunks = [_chunk(AW.format(i), score=0.9 - i / 100) for i in range(6)]
        chunks += [
            _chunk(WS.format(0), score=0.5),
            _chunk(MP.format(0), score=0.4),
            _chunk(BK.format(0), score=0.3),
            _chunk("knowledge/linux/systemd-docs/s.md", score=0.2),
        ]
        out = cap_by_source_directory(chunks, 5)
        dirs = [source_directory(c["source_path"]) for c in out]
        assert len(dirs) == len(set(dirs))


class TestOrderingPreserved:
    def test_relative_rank_order_of_kept_chunks_is_unchanged(self):
        chunks = [
            _chunk(AW.format(0), score=0.9),
            _chunk(AW.format(1), score=0.8),
            _chunk(WS.format(0), score=0.7),
            _chunk(MP.format(0), score=0.6),
            _chunk(BK.format(0), score=0.5),
        ]
        # limit=4 == the four surviving chunks, so backfill stays out of it.
        out = cap_by_source_directory(chunks, 4)
        assert [c["score"] for c in out] == [0.9, 0.7, 0.6, 0.5]

    def test_the_chunk_a_directory_keeps_is_its_first_one(self):
        # Backfill off: with it on all four come back regardless, so the
        # earlier version of this test held with the cap switched off too.
        chunks = [_chunk(AW.format(i), score=0.9 - i * 0.1) for i in range(4)]
        out = cap_by_source_directory(chunks, 5, backfill=False)
        assert len(out) == 1
        assert out[0]["score"] == 0.9

    def test_does_not_sort_by_score(self):
        # The daemon's order is authoritative; the cap must not re-sort it
        # even when the scores look out of order.
        chunks = [_chunk(WS.format(0), score=0.1), _chunk(BK.format(0), score=0.9)]
        out = cap_by_source_directory(chunks, 5)
        assert [c["score"] for c in out] == [0.1, 0.9]


class TestLimit:
    def test_returns_at_most_the_requested_count(self):
        chunks = [
            _chunk(f"knowledge/linux/dir{i}/f.md", score=1.0 - i / 100)
            for i in range(20)
        ]
        assert len(cap_by_source_directory(chunks, 5)) == 5

    def test_fewer_candidates_than_the_limit_returns_them_all(self):
        chunks = [_chunk(WS.format(0)), _chunk(BK.format(0))]
        out = cap_by_source_directory(chunks, 5)
        assert len(out) == 2

    def test_empty_input_returns_empty(self):
        assert cap_by_source_directory([], 5) == []

    def test_zero_limit_returns_empty(self):
        assert cap_by_source_directory([_chunk(AW.format(0))], 0) == []


class TestBackfill:
    def test_backfills_from_capped_out_chunks_rather_than_under_delivering(self):
        # All-same-source: capping alone would return 1 where the baseline
        # returned 5. Showing more of the only source that matched beats
        # showing nothing, so the spilled chunks top the result back up.
        chunks = [_chunk(AW.format(i), score=0.9 - i / 100) for i in range(8)]
        out = cap_by_source_directory(chunks, 5)
        assert len(out) == 5
        assert [c["score"] for c in out] == [0.9, 0.89, 0.88, 0.87, 0.86]

    def test_backfilled_chunks_come_after_the_diverse_ones(self):
        chunks = [
            _chunk(AW.format(0), score=0.99),
            _chunk(AW.format(1), score=0.98),
            _chunk(AW.format(2), score=0.97),
            _chunk(WS.format(0), score=0.10),
        ]
        out = cap_by_source_directory(chunks, 4)
        assert [c["score"] for c in out] == [0.99, 0.10, 0.98, 0.97]

    def test_backfill_can_be_disabled(self):
        chunks = [_chunk(AW.format(i)) for i in range(8)]
        assert len(cap_by_source_directory(chunks, 5, backfill=False)) == 1

    def test_backfill_does_not_engage_when_there_are_enough_directories(self):
        # The production case: a deep pull carries far more distinct
        # directories than the caller's limit, so nothing spills back in.
        chunks = [_chunk(AW.format(i), score=0.99 - i / 100) for i in range(10)]
        chunks += [
            _chunk(f"knowledge/linux/topic{i}/f.md", score=0.5 - i / 100)
            for i in range(8)
        ]
        out = cap_by_source_directory(chunks, 5)
        assert sum(1 for c in out if "arch-wiki" in c["source_path"]) == 1

    def test_backfill_never_returns_fewer_than_the_uncapped_path_would(self):
        # Guards the one real regression risk of turning the cap on: a query
        # whose candidates are all one source must not shrink from 5 to 1.
        chunks = [_chunk(AW.format(i), score=0.9 - i / 100) for i in range(8)]
        capped = cap_by_source_directory(chunks, 5)
        uncapped = cap_by_source_directory(chunks, 5, per_source=0)
        assert len(capped) == len(uncapped) == 5


class TestUnkeyablePaths:
    """Backfill is disabled throughout.

    Every fixture here holds fewer distinct directories than the limit, so
    backfill would refill the result from the spilled chunks and make the
    capped output identical to the uncapped one — these tests would then pass
    against a build that buckets unkeyable paths under "", which is the exact
    trap they exist to catch.
    """

    def test_unkeyable_paths_are_never_collapsed_into_one_bucket(self):
        # The trap: treating "" as a directory would keep 1 of these 4.
        chunks = [_chunk("", score=0.9 - i / 100) for i in range(4)]
        out = cap_by_source_directory(chunks, 5, backfill=False)
        assert len(out) == 4

    def test_unkeyable_paths_do_not_consume_another_directory_budget(self):
        chunks = [
            _chunk("", score=0.9),
            _chunk("README.md", score=0.8),
            _chunk(AW.format(0), score=0.7),
            _chunk(AW.format(1), score=0.6),
        ]
        out = cap_by_source_directory(chunks, 5, backfill=False)
        assert [c["score"] for c in out] == [0.9, 0.8, 0.7]

    def test_missing_source_path_key_is_unkeyable(self):
        chunks = [{"text": "a"}, {"text": "b"}, {"text": "c"}]
        assert len(cap_by_source_directory(chunks, 5, backfill=False)) == 3

    def test_non_mapping_entries_are_passed_through_uncapped(self):
        assert len(cap_by_source_directory(["a", "b", None], 5, backfill=False)) == 3


class TestExemptTrees:
    """``host/**`` is this machine's live config, not a reference corpus.

    The cap exists to stop a corpus that is large *by document count* from
    monopolising top-k. ``host/**`` has the opposite shape, and when several
    files in one host directory match, that IS the answer: "my launch agents"
    wants the list, not one example.

    Measured against the live daemon over 16 host probes (8 specific config
    lookups, 8 enumerations) and the 15 knowledge probes:

        policy                    lookups(8)  enums(8)  knowledge(15)
        uncapped (pre-cap prod)        5          4          8/15
        cap 1 everywhere               5          0         14/15
        cap 2 everywhere               5          1         12/15
        cap 3 everywhere               5          5         11/15
        host exempt, knowledge 1       5          6         14/15

    Exempting host costs nothing: isolating the cap from the deep pull (same
    k=50 score-sorted pool, cap on vs off) it surfaces a narrow host config
    directory on 0 of 24 host-shaped queries — it is inert on lookups and
    purely destructive on enumerations. Raising the cap globally instead is
    not an option: it buys the enumerations by wrecking knowledge, 14 -> 11.
    """

    def _agents(self, n, score=0.9):
        return [
            _chunk(f"host/Library/LaunchAgents/com.vendor.{i}.plist", score - i / 100)
            for i in range(n)
        ]

    def test_an_enumeration_of_host_config_survives_the_cap(self):
        out = cap_by_source_directory(self._agents(4), 5, backfill=False)
        assert len(out) == 4

    def test_knowledge_is_still_capped_while_host_is_not(self):
        chunks = self._agents(3) + [_chunk(AW.format(i), 0.5 - i / 100) for i in range(3)]
        out = cap_by_source_directory(chunks, 5, backfill=False)
        paths = [c["source_path"] for c in out]
        assert sum(1 for p in paths if "LaunchAgents" in p) == 3
        assert sum(1 for p in paths if "arch-wiki" in p) == 1

    def test_exempt_chunks_do_not_consume_another_directorys_budget(self):
        chunks = self._agents(2) + [
            _chunk(AW.format(0), 0.5),
            _chunk(WS.format(0), 0.4),
        ]
        out = cap_by_source_directory(chunks, 5, backfill=False)
        assert len(out) == 4

    def test_exemption_matches_a_whole_segment_not_a_string_prefix(self):
        # "hostile" starts with "host" and must NOT be exempt.
        chunks = [
            _chunk(f"hostile/tracking/file_{i}.md", 0.9 - i / 100) for i in range(4)
        ]
        assert len(cap_by_source_directory(chunks, 5, backfill=False)) == 1

    def test_a_host_lookup_still_gets_its_narrow_directory(self):
        # The exemption must not stop host/etc/ssh reaching the result.
        chunks = self._agents(2) + [_chunk("host/etc/ssh/sshd_config", 0.4)]
        paths = [c["source_path"] for c in cap_by_source_directory(chunks, 5)]
        assert "host/etc/ssh/sshd_config" in paths

    def test_the_exempt_set_is_configurable(self):
        chunks = self._agents(4)
        out = cap_by_source_directory(chunks, 5, exempt_trees=(), backfill=False)
        assert len(out) == 1

    def test_another_tree_can_be_exempted(self):
        chunks = [_chunk(AW.format(i), 0.9 - i / 100) for i in range(4)]
        out = cap_by_source_directory(
            chunks, 5, exempt_trees=("knowledge",), backfill=False
        )
        assert len(out) == 4

    def test_disabling_the_cap_still_wins_over_the_exemption(self):
        chunks = self._agents(3) + [_chunk(AW.format(i)) for i in range(3)]
        out = cap_by_source_directory(chunks, 5, per_source=0)
        assert len(out) == 5


class TestDisabled:
    """Backfill is disabled throughout, for the same reason as
    TestUnkeyablePaths: with it on, an all-one-directory fixture is refilled
    to the limit either way, so these assertions hold even if the ``per_source
    <= 0`` branch is deleted outright."""

    def test_per_source_zero_disables_capping(self):
        chunks = [_chunk(AW.format(i)) for i in range(8)]
        out = cap_by_source_directory(chunks, 5, per_source=0, backfill=False)
        assert len(out) == 5
        assert all("arch-wiki" in c["source_path"] for c in out)

    def test_negative_per_source_disables_capping(self):
        chunks = [_chunk(AW.format(i)) for i in range(8)]
        out = cap_by_source_directory(chunks, 5, per_source=-1, backfill=False)
        assert len(out) == 5


class TestObservability:
    """A systematic path-key failure disables the whole feature silently.

    Treating an unreadable path as "unique, never cap" is right for one chunk,
    but if the key drifts for *every* chunk — the daemon renaming source_path,
    a caller passing the wrong path_key — the cap becomes a no-op and nothing
    notices. Demonstrated: feed the corpus with the key spelled "file_path"
    and the top-5 reverts to six-of-six arch-wiki, with no error and no test
    failure. One debug line makes that visible.
    """

    LOGGER = "halbert_core.integrations.source_diversity"

    def _capture(self, caplog, chunks, **kw):
        caplog.set_level(logging.DEBUG, logger=self.LOGGER)
        out = cap_by_source_directory(chunks, 5, **kw)
        return out, [r.getMessage() for r in caplog.records if r.name == self.LOGGER]

    def test_it_reports_what_it_capped(self, caplog):
        chunks = [_chunk(AW.format(i), 0.9 - i / 100) for i in range(4)]
        chunks += [_chunk(WS.format(0), 0.5)]
        _, msgs = self._capture(caplog, chunks, backfill=False)
        assert len(msgs) == 1
        # 3 arch-wiki chunks spilled; 2 directories were seen.
        assert "3" in msgs[0] and "2" in msgs[0]

    def test_a_total_no_op_is_visible(self, caplog):
        # The exact drift: the path lives under a key the cap is not reading.
        chunks = [{"text": "t", "file_path": AW.format(i)} for i in range(6)]
        out, msgs = self._capture(caplog, chunks, backfill=False)
        # The silent no-op itself: nothing was capped, so all six survive the
        # cap and only the limit trims them.
        assert len(out) == 5
        assert msgs == ["source cap: 0 chunks spilled across 0 directories (6 unkeyable)"]

    def test_the_line_distinguishes_drift_from_a_genuinely_diverse_pool(self, caplog):
        chunks = [_chunk(f"knowledge/linux/topic{i}/f.md", 0.9) for i in range(6)]
        _, msgs = self._capture(caplog, chunks, backfill=False)
        assert len(msgs) == 1
        assert msgs[0] != ""

    def test_logging_does_not_change_the_result(self, caplog):
        chunks = [_chunk(AW.format(i), 0.9 - i / 100) for i in range(4)]
        out, _ = self._capture(caplog, chunks, backfill=False)
        assert out == cap_by_source_directory(chunks, 5, backfill=False)

    def test_the_disabled_path_stays_quiet(self, caplog):
        chunks = [_chunk(AW.format(i)) for i in range(4)]
        _, msgs = self._capture(caplog, chunks, per_source=0)
        assert msgs == []


class TestPurity:
    def test_input_list_is_not_mutated(self):
        chunks = [_chunk(AW.format(i)) for i in range(4)]
        before = list(chunks)
        cap_by_source_directory(chunks, 5)
        assert chunks == before

    def test_chunk_dicts_are_returned_unmodified(self):
        chunk = _chunk(AW.format(0), score=0.5)
        out = cap_by_source_directory([chunk], 5)
        assert out[0] is chunk

    def test_accepts_any_iterable(self):
        chunks = (_chunk(AW.format(i)) for i in range(4))
        assert len(cap_by_source_directory(chunks, 5)) == 4
