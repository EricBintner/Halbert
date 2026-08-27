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

from halbert_core.integrations.source_diversity import (
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


class TestCapRespected:
    """The cap in isolation. Backfill is disabled here so these assert the cap
    itself; the interaction between the two is TestBackfill's subject."""

    def test_keeps_one_chunk_per_directory_by_default(self):
        chunks = [_chunk(AW.format(i)) for i in range(6)]
        assert len(cap_by_source_directory(chunks, 5, backfill=False)) == 1

    def test_the_giant_keeps_its_single_best_slot(self):
        # The control case: when a giant source genuinely is right, it must
        # not be excluded — only capped.
        chunks = [_chunk(AW.format(0), score=0.9)] + [
            _chunk(WS.format(i), score=0.5) for i in range(4)
        ]
        out = cap_by_source_directory(chunks, 5)
        assert out[0]["source_path"] == AW.format(0)

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

    def test_the_first_chunk_of_a_directory_is_the_one_kept(self):
        chunks = [_chunk(AW.format(i), score=0.9 - i * 0.1) for i in range(4)]
        out = cap_by_source_directory(chunks, 5)
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
    def test_unkeyable_paths_are_never_collapsed_into_one_bucket(self):
        # The trap: treating "" as a directory would keep 1 of these 4.
        chunks = [_chunk("", score=0.9 - i / 100) for i in range(4)]
        out = cap_by_source_directory(chunks, 5)
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
        assert len(cap_by_source_directory(chunks, 5)) == 3

    def test_non_mapping_entries_are_passed_through_uncapped(self):
        assert len(cap_by_source_directory(["a", "b", None], 5)) == 3


class TestDisabled:
    def test_per_source_zero_disables_capping(self):
        chunks = [_chunk(AW.format(i)) for i in range(8)]
        out = cap_by_source_directory(chunks, 5, per_source=0)
        assert len(out) == 5
        assert all("arch-wiki" in c["source_path"] for c in out)

    def test_negative_per_source_disables_capping(self):
        chunks = [_chunk(AW.format(i)) for i in range(8)]
        assert len(cap_by_source_directory(chunks, 5, per_source=-1)) == 5


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
