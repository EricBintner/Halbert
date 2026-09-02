# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""R04-F4: command output must be bounded as it arrives, not after the fact.

The agent's block pool and the dashboard's /exec route both accumulated
every byte a command produced and only cut it down to a short head and tail
at the end — so `cat` on a large file was held whole in memory before being
thrown away (~800 MB reproduced by the REV-04 review). The bound is a
property of the accumulator, so it is asserted here rather than through a
command whose result would look the same either way.
"""

from halbert_core.streaming.bounded_output import BoundedOutput


class TestBoundedOutput:

    def test_keeps_both_ends_and_drops_the_middle(self):
        acc = BoundedOutput(head_cap=10, tail_cap=10)
        acc.extend(b"HEAD______")
        acc.extend(b"x" * 1000)
        acc.extend(b"______TAIL")

        assert len(acc) == 20, "the accumulator grew past its caps"
        assert acc.dropped == 1000
        out = acc.bytes()
        assert out.startswith(b"HEAD______")
        assert out.endswith(b"______TAIL")
        assert b"1000 bytes elided" in out, (
            "a truncated result must read as truncated"
        )

    def test_output_under_the_cap_is_kept_whole_and_unmarked(self):
        acc = BoundedOutput(head_cap=10, tail_cap=10)
        acc.extend(b"short")
        assert acc.dropped == 0
        assert acc.bytes() == b"short"
        assert len(acc) == 5

    def test_a_chunk_straddling_the_head_cap_is_split_not_lost(self):
        acc = BoundedOutput(head_cap=4, tail_cap=100)
        acc.extend(b"abcdefgh")
        assert acc.dropped == 0
        assert acc.bytes() == b"abcdefgh"

    def test_peak_retention_is_capped_no_matter_how_much_arrives(self):
        acc = BoundedOutput(head_cap=1024, tail_cap=1024)
        for _ in range(4096):
            acc.extend(b"y" * 1024)  # 4 MiB through a 2 KiB accumulator
        assert len(acc) <= 2048

    def test_empty_writes_are_ignored(self):
        acc = BoundedOutput(head_cap=4, tail_cap=4)
        acc.extend(b"")
        assert acc.bytes() == b""
        assert acc.dropped == 0
