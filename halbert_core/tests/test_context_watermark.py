"""Tests for ContextWatermark (F4)."""

import pytest

from halbert_core.context.watermark import ContextWatermark
from halbert_core.agents.blocks import ToolResultBlock, TextBlock


# ---------------------------------------------------------------------------
# should_compact (trigger + gates)
# ---------------------------------------------------------------------------

class TestShouldCompact:
    def test_below_watermark_never_compacts(self):
        wm = ContextWatermark()
        assert wm.should_compact(70, max_tokens=100) is False

    def test_at_watermark_with_temporal_gate(self):
        wm = ContextWatermark(temporal_gate_seconds=7200)
        # 80 tokens / 100 max = 80% watermark; last compaction 3h ago -> compact
        assert wm.should_compact(80, 100, last_compaction_ts=0.0, now=10800.0) is True

    def test_within_temporal_gate_no_topic_change_blocks(self):
        wm = ContextWatermark(temporal_gate_seconds=7200)
        # watermark reached but only 30min since last compaction, no topic change
        assert wm.should_compact(85, 100, last_compaction_ts=0.0, now=1800.0) is False

    def test_topic_change_compacts_within_temporal_gate(self):
        wm = ContextWatermark(temporal_gate_seconds=7200)
        assert wm.should_compact(85, 100, last_compaction_ts=0.0,
                                 now=1800.0, topic_changed=True) is True

    def test_topic_change_below_watermark_still_no(self):
        wm = ContextWatermark()
        assert wm.should_compact(50, 100, topic_changed=True) is False

    def test_zero_max_tokens_safe(self):
        wm = ContextWatermark()
        assert wm.should_compact(999, 0) is False


# ---------------------------------------------------------------------------
# micro_compact (truncate long tool results)
# ---------------------------------------------------------------------------

class TestMicroCompact:
    def test_truncates_long_tool_result_dataclass(self):
        long = "x" * 500
        msg = {"role": "user", "content": [ToolResultBlock(content=long)]}
        n = ContextWatermark().micro_compact([msg])
        assert n == 1
        assert len(msg["content"][0].content) < 500
        assert "truncated" in msg["content"][0].content

    def test_truncates_long_tool_result_dict(self):
        long = "y" * 400
        msg = {"role": "user", "content": [{"type": "tool_result", "content": long}]}
        n = ContextWatermark().micro_compact([msg])
        assert n == 1
        assert "truncated" in msg["content"][0]["content"]

    def test_leaves_short_tool_results(self):
        msg = {"role": "user", "content": [ToolResultBlock(content="short")]}
        assert ContextWatermark().micro_compact([msg]) == 0
        assert msg["content"][0].content == "short"

    def test_leaves_text_blocks(self):
        msg = {"role": "user", "content": [TextBlock(text="x" * 500)]}
        assert ContextWatermark().micro_compact([msg]) == 0

    def test_handles_legacy_string_content(self):
        msg = {"role": "user", "content": "x" * 500}
        assert ContextWatermark().micro_compact([msg]) == 0

    def test_truncate_count_across_messages(self):
        msgs = [
            {"role": "user", "content": [ToolResultBlock(content="a" * 300)]},
            {"role": "user", "content": [ToolResultBlock(content="short")]},
            {"role": "user", "content": [ToolResultBlock(content="b" * 250)]},
        ]
        assert ContextWatermark().micro_compact(msgs) == 2

    def test_custom_cap(self):
        msg = {"role": "user", "content": [ToolResultBlock(content="x" * 100)]}
        # cap 50 -> 100 chars is over -> truncated
        assert ContextWatermark(tool_result_truncate=50).micro_compact([msg]) == 1
        # cap 200 -> 100 chars under -> not truncated
        msg2 = {"role": "user", "content": [ToolResultBlock(content="x" * 100)]}
        assert ContextWatermark(tool_result_truncate=200).micro_compact([msg2]) == 0


# ---------------------------------------------------------------------------
# detect_topic_change
# ---------------------------------------------------------------------------

class TestTopicChange:
    def test_no_prev_query_is_change(self):
        wm = ContextWatermark()
        assert wm.detect_topic_change("disk usage", None) is True

    def test_similar_query_not_change(self):
        wm = ContextWatermark()
        assert wm.detect_topic_change("disk usage is high",
                                      "disk usage report") is False

    def test_different_query_is_change(self):
        wm = ContextWatermark()
        assert wm.detect_topic_change("configure the nginx firewall",
                                      "disk usage is high") is True

    def test_empty_prev_is_change(self):
        wm = ContextWatermark()
        assert wm.detect_topic_change("something", "") is True