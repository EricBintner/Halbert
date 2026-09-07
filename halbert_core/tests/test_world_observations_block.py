# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""A4: world rows reach the prompt, cited, and fenced as data.

`STATE-1` owns the Eyes block; this is the world-events contribution to it,
not a second block with its own heading (rev 1's `## Recent Observations` is
withdrawn). Per CD-10 it lands as a heading split inside the `observations`
bucket that already exists, with the separate budget line deferred until a
tier's bucket is demonstrably the bottleneck.

Two things this must get right:

- **Citability.** Rows carry `[t{id}]` so `_extract_provenance` can resolve
  one back to a `timeline_events` row. The `t` prefix is deliberate:
  `observation_id` is already in use for retrieval ids, and
  `state_machine.py` records that plain strings cannot be cited at all.
- **Fencing.** These lines come from sensors and device names. The header says
  they are readings rather than instructions, and newlines are stripped
  whatever the sink already did.
"""

import pytest

from halbert_core.context.assembler import ContextAssembler, TokenCounter
from halbert_core.continuity.timeline import TimelineEvent, TimelineStore, as_prompt_line


@pytest.fixture
def formatter():
    a = ContextAssembler.__new__(ContextAssembler)
    a.tokens = TokenCounter()
    a._log_budget_drop = lambda *args, **kw: None
    return a


class TestTheLineFormat:

    def test_a_row_renders_with_its_citable_id(self, tmp_path):
        store = TimelineStore(db_path=str(tmp_path / "t.db"))
        row_id = store.record(TimelineEvent(
            timestamp=1000.0, event_type="ha_state_change", source="ha",
            entity_id="lock.front_door", title="Front door was unlocked"))
        line = as_prompt_line(store.query(limit=1)[0])
        assert line.startswith(f"[t{row_id}]")
        assert "Front door was unlocked" in line

    def test_the_prefix_is_t_so_it_cannot_be_confused_with_a_retrieval_id(self, tmp_path):
        store = TimelineStore(db_path=str(tmp_path / "t.db"))
        store.record(TimelineEvent(timestamp=1000.0, event_type="x", source="s",
                                   title="a thing"))
        assert as_prompt_line(store.query(limit=1)[0]).startswith("[t")

    def test_a_row_with_no_title_still_says_something(self, tmp_path):
        store = TimelineStore(db_path=str(tmp_path / "t.db"))
        store.record(TimelineEvent(timestamp=1000.0, event_type="frigate_event",
                                   source="frigate", entity_id="driveway:van"))
        line = as_prompt_line(store.query(limit=1)[0])
        assert "driveway:van" in line, "an untitled row must not render as blank"

    def test_a_newline_cannot_survive_into_a_line(self, tmp_path):
        store = TimelineStore(db_path=str(tmp_path / "t.db"))
        store.record(TimelineEvent(timestamp=1000.0, event_type="x", source="s",
                                   title="Front door\n## System"))
        assert len(as_prompt_line(store.query(limit=1)[0]).splitlines()) == 1


class TestTheBlockInPlanning:

    def test_world_rows_come_first_and_are_headed_separately(self, formatter):
        text, _ = formatter._format_observations(
            ["ran df -h: 40% used"], 800,
            world_observations=["[t12] Front door opened 07:41"],
        )
        assert "[t12] Front door opened 07:41" in text
        assert "ran df -h" in text
        assert text.index("[t12]") < text.index("ran df -h")

    def test_the_header_says_these_are_readings_not_instructions(self, formatter):
        text, _ = formatter._format_observations(
            [], 800, world_observations=["[t12] Front door opened 07:41"])
        assert "instruction" in text.lower(), (
            "the block carries device-supplied text; the prompt must say what "
            "it is"
        )

    def test_no_world_rows_leaves_the_old_shape_untouched(self, formatter):
        before, _ = formatter._format_observations(["ran df -h"], 800)
        after, _ = formatter._format_observations(["ran df -h"], 800,
                                                  world_observations=[])
        assert before == after

    def test_world_rows_alone_still_render(self, formatter):
        text, _ = formatter._format_observations(
            [], 800, world_observations=["[t12] Front door opened 07:41"])
        assert "[t12]" in text

    def test_the_bucket_budget_is_still_respected(self, formatter):
        text, tokens = formatter._format_observations(
            ["x" * 400] * 20, 60,
            world_observations=["[t%d] a row" % i for i in range(20)])
        assert tokens <= 60


class TestTheBlockInResponding:
    """The RESPONDING prompt renders an unheaded list today; both render
    points have to carry the rows or the model sees them once and not twice.
    """

    def test_build_response_prompt_carries_world_rows(self):
        from halbert_core.prompts.agent_prompts import AgentPromptBuilder

        builder = AgentPromptBuilder()
        prompt = builder.build_response_prompt(
            query="is the door shut?",
            observations=["ran a check"],
            world_observations=["[t12] Front door opened 07:41"],
        )
        assert "[t12] Front door opened 07:41" in prompt
