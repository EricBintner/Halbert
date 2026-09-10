# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""R-11 Phase D tail: names a skill may not claim, and ids that survive a
restart.

- **A13-G13**: the reserved set is assembled from static lists and lazily
  imported schema registries, and cached for the process. Every tool the
  daemon registers at RUNTIME is therefore missing from it — Home
  Assistant's two, Frigate's six, and every tool an MCP server publishes
  through the bridge. A skill named ``ha_call_service`` is a name trap
  exactly where a name trap is worst: the user types the name meaning the
  tool that turns lights off.
- **A13-G8**: an id-less skill gets a fresh random ULID at every load, so
  it is a different skill to the telemetry table after every restart —
  which makes "which skills does the model actually consult?" a question
  the table cannot answer. Every bundled and operator skill is id-less;
  ids are stamped at creation and none of these were created through the
  authoring tool.
"""
from __future__ import annotations

import dataclasses

import pytest

from halbert_core.skills.parser import SKILL_ID_RE, derived_skill_id, parse_skill
from halbert_core.skills.registry import SkillRegistry
from halbert_core.skills.reserved import (
    add_live_tool_source,
    clear_live_tool_sources,
    is_reserved_skill_name,
    live_tool_names,
    reserved_skill_names,
)


@pytest.fixture(autouse=True)
def _clean_sources():
    clear_live_tool_sources()
    yield
    clear_live_tool_sources()


def _skill(name, *, source=None):
    return parse_skill(
        f"---\nname: {name}\ndescription: d\n"
        "halbert:\n  kind: ops\n  state: trusted\n---\nBody.",
        source_path=source,
    )


# ---------------------------------------------------------------------------
# A13-G13 — the live half of the reserved set
# ---------------------------------------------------------------------------

class TestRuntimeToolsAreReservedToo:
    def test_a_registered_executor_tool_is_reserved(self):
        assert is_reserved_skill_name("ha_call_service") is False
        add_live_tool_source(lambda: ["ha_call_service", "ha_get_entity_state"])
        assert is_reserved_skill_name("ha_call_service") is True

    def test_both_spellings_are_reserved(self):
        add_live_tool_source(lambda: ["frigate_list_cameras"])
        assert is_reserved_skill_name("frigate-list-cameras") is True
        assert is_reserved_skill_name("Frigate_List_Cameras") is True

    def test_a_tool_registered_after_the_first_scan_is_still_reserved(self):
        """The cache was the bug. Tool registration is not static in this
        process: HA, Frigate and the MCP bridge all register after the
        skills package has been imported, and some of them after skills
        have already been loaded once."""
        assert reserved_skill_names()
        add_live_tool_source(lambda: ["late_tool"])
        assert is_reserved_skill_name("late_tool") is True

    def test_the_mcp_bridge_is_a_source_without_anyone_wiring_it(self):
        """MCP tool names arrive from other people's servers; they are the
        least predictable names in the process and the most important not
        to let a skill shadow."""
        from halbert_core.mcp.registry import get_tool_registry

        registry = get_tool_registry()
        try:
            names = registry.register("weatherd", [{"name": "forecast"}])
            live = set(live_tool_names())
            assert live & set(names)
        finally:
            registry.unregister_server("weatherd")

    def test_a_source_that_raises_costs_its_names_not_the_load(self):
        def _boom():
            raise RuntimeError("injected")

        add_live_tool_source(_boom)
        add_live_tool_source(lambda: ["still_reserved"])
        assert is_reserved_skill_name("still_reserved") is True

    def test_a_source_returning_junk_is_ignored(self):
        add_live_tool_source(lambda: [None, 42, "", "  ", "real_tool"])
        assert is_reserved_skill_name("real_tool") is True
        assert is_reserved_skill_name("") is False

    def test_the_static_set_still_holds(self):
        assert is_reserved_skill_name("run_command") is True
        assert is_reserved_skill_name("read_file") is True
        assert is_reserved_skill_name("storage-ops") is False

    def test_the_same_source_is_not_registered_twice(self):
        def _src():
            return ["once"]

        add_live_tool_source(_src)
        add_live_tool_source(_src)
        assert sorted(live_tool_names()).count("once") == 1


class TestTheExecutorIsActuallyWired:
    def test_the_daemon_registers_its_executor_as_a_source(self):
        """The consumer half. A live reserved set nothing feeds is the
        static list with extra steps."""
        import inspect

        from halbert_core.dashboard.routes import agent as route

        src = inspect.getsource(route.get_agent)
        assert "add_live_tool_source" in src

    def test_a_real_executors_tools_become_reserved(self):
        from halbert_core.tools import ToolExecutor, ToolSafetyFramework

        executor = ToolExecutor(safety=ToolSafetyFramework())
        executor.register_system_tools()
        add_live_tool_source(lambda: list(executor.tools))
        for name in executor.tools:
            assert is_reserved_skill_name(name) is True


# ---------------------------------------------------------------------------
# A13-G8 — an id that means the same skill tomorrow
# ---------------------------------------------------------------------------

class TestIdsSurviveARestart:
    def test_the_same_file_stamps_the_same_id_twice(self, tmp_path):
        src = tmp_path / "disk-ops" / "SKILL.md"
        src.parent.mkdir()
        src.write_text("body")
        first = SkillRegistry([_skill("disk-ops", source=src)]).get("disk-ops")
        second = SkillRegistry([_skill("disk-ops", source=src)]).get("disk-ops")
        assert first.id == second.id
        assert SKILL_ID_RE.fullmatch(first.id)

    def test_two_files_never_share_an_id(self, tmp_path):
        ids = set()
        for name in ("disk-ops", "net-ops"):
            src = tmp_path / name / "SKILL.md"
            src.parent.mkdir()
            src.write_text("body")
            ids.add(SkillRegistry([_skill(name, source=src)]).get(name).id)
        assert len(ids) == 2

    def test_a_durable_id_still_wins(self, tmp_path):
        from halbert_core.skills.parser import new_skill_id

        src = tmp_path / "disk-ops" / "SKILL.md"
        src.parent.mkdir()
        src.write_text("body")
        minted = new_skill_id()
        skill = dataclasses.replace(_skill("disk-ops", source=src), id=minted)
        assert SkillRegistry([skill]).get("disk-ops").id == minted

    def test_a_skill_with_no_file_still_gets_an_id(self):
        """Nothing durable to key on, so the old behaviour stands — and it
        is still a well-formed id, because the telemetry table keys on it."""
        got = SkillRegistry([_skill("in-memory")]).get("in-memory")
        assert SKILL_ID_RE.fullmatch(got.id)

    def test_the_derivation_is_shape_compatible_with_a_minted_id(self, tmp_path):
        assert SKILL_ID_RE.fullmatch(derived_skill_id(tmp_path / "x" / "SKILL.md"))

    def test_moving_the_root_moves_the_id_and_that_is_the_honest_answer(self, tmp_path):
        """Derived from the canonical path, so a skill copied to a new root
        is a new row. Not free — but the alternative to deriving is a fresh
        random id EVERY restart, which loses the join unconditionally. A
        skill that wants an identity across moves carries a durable one.
        """
        a = tmp_path / "a" / "disk-ops" / "SKILL.md"
        b = tmp_path / "b" / "disk-ops" / "SKILL.md"
        for p in (a, b):
            p.parent.mkdir(parents=True)
            p.write_text("body")
        assert (SkillRegistry([_skill("disk-ops", source=a)]).get("disk-ops").id
                != SkillRegistry([_skill("disk-ops", source=b)]).get("disk-ops").id)

    def test_the_bundled_set_is_stable_across_two_loads(self):
        from halbert_core.skills.loader import daemon_skill_dirs

        first = {s.name: s.id
                 for s in SkillRegistry.from_disk(dirs=daemon_skill_dirs()).all()}
        second = {s.name: s.id
                  for s in SkillRegistry.from_disk(dirs=daemon_skill_dirs()).all()}
        assert first == second
        assert first
