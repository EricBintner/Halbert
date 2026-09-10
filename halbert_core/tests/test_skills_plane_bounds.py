# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""R-11 Phase A: one bad skill file never costs the plane.

- **A13 bug 1** (fix-first row 25) -- YAML alias expansion. A downloaded
  pack with nine chained alias lists allocates gigabytes at
  ``SkillRegistry.from_disk``, because ``str()`` on the aliased node
  materialises the whole expansion. The description is bounded AT PARSE
  and a non-scalar is refused before it is stringified.
- **A13 bug 2** -- ``float()`` accepts ``nan`` and ``inf``, so
  ``budget_multiplier: .nan`` parsed cleanly and then raised out of
  ``ContextAssembler.assemble`` on every matching turn -- the failure
  landing nowhere near the file that caused it.
- **A13-G1** -- the loader caught ``SkillParseError`` and ``OSError``. A
  skill file that raised anything else (a MemoryError from the alias
  bomb, a RecursionError from a self-referential anchor) took the whole
  directory walk with it, so one bad file cost every skill on the
  machine.
"""

import pytest

from halbert_core.skills.parser import (
    MAX_PARSED_DESCRIPTION_CHARS,
    SkillParseError,
    parse_skill,
)


def _skill(front: str, body: str = "Body text.") -> str:
    return f"---\n{front}\n---\n{body}\n"


# ---------------------------------------------------------------------------
# A13 bug 1: the alias bomb
# ---------------------------------------------------------------------------

def test_a_chained_alias_bomb_is_refused_not_expanded():
    """Nine chained alias lists: the classic billion-laughs shape."""
    front = "name: bomb\n"
    front += "a: &a [\"x\",\"x\",\"x\",\"x\",\"x\",\"x\",\"x\",\"x\",\"x\"]\n"
    for i in range(1, 8):
        prev = chr(ord("a") + i - 1)
        cur = chr(ord("a") + i)
        front += f"{cur}: &{cur} [*{prev},*{prev},*{prev},*{prev},*{prev},*{prev},*{prev},*{prev},*{prev}]\n"
    front += "description: *h\n"
    with pytest.raises(SkillParseError):
        parse_skill(_skill(front))


def test_a_non_scalar_description_is_refused():
    with pytest.raises(SkillParseError) as excinfo:
        parse_skill(_skill("name: x\ndescription:\n  - a\n  - b"))
    assert "description" in str(excinfo.value)


def test_a_long_description_is_refused_at_parse():
    long_text = "a" * (MAX_PARSED_DESCRIPTION_CHARS + 10)
    with pytest.raises(SkillParseError):
        parse_skill(_skill(f"name: x\ndescription: {long_text}"))


def test_an_ordinary_description_parses():
    skill = parse_skill(_skill("name: x\ndescription: Reads the disk."))
    assert skill.description == "Reads the disk."


# ---------------------------------------------------------------------------
# A13 bug 2: a multiplier must be a finite number
# ---------------------------------------------------------------------------

def test_a_nan_multiplier_is_refused():
    with pytest.raises(SkillParseError) as excinfo:
        parse_skill(_skill("name: x\nbudget_multiplier: .nan"))
    assert "finite" in str(excinfo.value).lower()


def test_an_infinite_multiplier_is_refused():
    with pytest.raises(SkillParseError):
        parse_skill(_skill("name: x\nbudget_multiplier: .inf"))


def test_a_negative_multiplier_is_refused():
    with pytest.raises(SkillParseError):
        parse_skill(_skill("name: x\nbudget_multiplier: -1"))


def test_an_ordinary_multiplier_parses():
    assert parse_skill(_skill("name: x\nbudget_multiplier: 1.5")).budget_multiplier == 1.5


# ---------------------------------------------------------------------------
# A13-G1: one bad file never costs the plane
# ---------------------------------------------------------------------------

def test_one_exploding_skill_does_not_take_the_directory(tmp_path, monkeypatch):
    import halbert_core.skills.loader as loader
    from halbert_core.skills.parser import parse_skill_file as real_parse

    (tmp_path / "good.md").write_text(_skill("name: good\ndescription: Fine."))
    (tmp_path / "bad.md").write_text(_skill("name: bad\ndescription: Also fine."))

    def _explode(path):
        if path.name == "bad.md":
            raise MemoryError("alias expansion")
        return real_parse(path)

    monkeypatch.setattr(loader, "parse_skill_file", _explode)
    skills = loader.load_skills_from_dir(tmp_path)
    assert [s.name for s in skills] == ["good"]


def test_a_recursion_error_is_survived_too(tmp_path, monkeypatch):
    import halbert_core.skills.loader as loader

    (tmp_path / "a.md").write_text(_skill("name: a\ndescription: Fine."))
    (tmp_path / "b.md").write_text(_skill("name: b\ndescription: Fine."))

    def _explode(path):
        raise RecursionError("self-referential anchor")

    monkeypatch.setattr(loader, "parse_skill_file", _explode)
    assert loader.load_skills_from_dir(tmp_path) == []


def test_a_keyboard_interrupt_is_not_swallowed(tmp_path, monkeypatch):
    """A per-file guard must not eat the operator's own Ctrl-C."""
    import halbert_core.skills.loader as loader

    (tmp_path / "a.md").write_text(_skill("name: a\ndescription: Fine."))

    def _interrupt(path):
        raise KeyboardInterrupt

    monkeypatch.setattr(loader, "parse_skill_file", _interrupt)
    with pytest.raises(KeyboardInterrupt):
        loader.load_skills_from_dir(tmp_path)


# ---------------------------------------------------------------------------
# A13 bug 5 (fix-first row 26): a protected path is compared normalised
# ---------------------------------------------------------------------------

def _skill_safety(paths):
    from types import SimpleNamespace

    return SimpleNamespace(
        blocked_commands=(), protected_paths=tuple(paths),
        protected_services=(), destructive_requires_approval=True,
    )


def _framework(paths):
    from halbert_core.tools.safety import ToolSafetyFramework

    framework = ToolSafetyFramework()
    framework.set_skill_safety(_skill_safety(paths))
    return framework


def test_a_dot_segment_does_not_evade_a_protected_path():
    # A path outside SENSITIVE_PATHS, so the BASE classifier does not
    # answer first -- the point is the skill-declared rule.
    protected = "/opt/tank/data"
    framework = _framework([protected])
    result = framework.classify(
        "write_file", {"path": "/opt/tank/./data/x"})
    assert result.matched_rule == "skill.protected_paths"


def test_a_parent_segment_does_not_evade_it():
    protected = "/opt/tank/data"
    framework = _framework([protected])
    result = framework.classify(
        "write_file", {"path": "/opt/tank/other/../data/x"})
    assert result.matched_rule == "skill.protected_paths"


def test_a_neighbouring_directory_is_not_inside_it():
    """The over-match half: /bootleg is not inside /boot."""
    protected = "/opt/boot"
    framework = _framework([protected])
    result = framework.classify(
        "write_file", {"path": "/opt/bootleg/x"})
    assert result.matched_rule != "skill.protected_paths"


def test_the_exact_path_is_still_protected():
    protected = "/opt/tank/data"
    framework = _framework([protected])
    assert framework.classify(
        "write_file", {"path": protected}).matched_rule == "skill.protected_paths"


def test_an_unrelated_path_is_untouched():
    framework = _framework(["/opt/tank"])
    result = framework.classify("write_file", {"path": "/opt/elsewhere"})
    assert result.matched_rule != "skill.protected_paths"


# ---------------------------------------------------------------------------
# A13 bug 6: the tool allowlist is enforced, not warned about
# ---------------------------------------------------------------------------

def _framework_with_tools(allowed):
    from types import SimpleNamespace

    from halbert_core.tools.safety import ToolSafetyFramework

    framework = ToolSafetyFramework()
    framework.set_skill_safety(SimpleNamespace(
        blocked_commands=(), protected_paths=(), protected_services=(),
        destructive_requires_approval=False, allowed_tools=allowed,
    ))
    return framework


def test_a_tool_outside_the_allowlist_is_blocked():
    result = _framework_with_tools(("read_file",)).classify(
        "run_command", {"command": "ls"})
    assert result.allowed is False
    assert result.matched_rule == "skill.allowed_tools"


def test_a_tool_inside_the_allowlist_passes():
    result = _framework_with_tools(("read_file",)).classify(
        "read_file", {"path": "/etc/hosts"})
    assert result.matched_rule != "skill.allowed_tools"


def test_an_empty_intersection_denies_everything():
    """It used to log "all tools denied" and then run every tool."""
    result = _framework_with_tools(()).classify("read_file", {"path": "/x"})
    assert result.allowed is False


def test_no_allowlist_restricts_nothing():
    result = _framework_with_tools(None).classify("read_file", {"path": "/x"})
    assert result.matched_rule != "skill.allowed_tools"


def test_the_composer_puts_the_allowlist_on_the_safety_object():
    from halbert_core.skills.composer import compose
    from halbert_core.skills.parser import parse_skill

    skill = parse_skill(
        "---\nname: narrow\ndescription: Reads only.\n"
        "allowed-tools: read_file\n---\nBody.\n")
    composed = compose([skill])
    assert composed.safety.allowed_tools == ("read_file",)


# ---------------------------------------------------------------------------
# A13-G7 (FD-19): telemetry is the run's, and goes with it
# ---------------------------------------------------------------------------

def test_skill_events_are_erased_with_the_run(tmp_path):
    from halbert_core.agents.conversation_sqlite import SqliteConversationStore

    store = SqliteConversationStore(db_path=str(tmp_path / "c.db"))
    store.create_thread("c1", title="t")
    store.append_message(
        thread_id="c1", role="user", content="do the thing",
        metadata={"request_id": "run-1"})
    store.append_skill_event(
        skill_id="config-ops", event="matched", run_id="run-1")
    assert store.list_skill_events()

    store.forget_request("run-1")
    assert store.list_skill_events() == [], (
        "a forget that leaves the telemetry behind is a forget that did "
        "not happen"
    )


def test_another_runs_telemetry_survives(tmp_path):
    from halbert_core.agents.conversation_sqlite import SqliteConversationStore

    store = SqliteConversationStore(db_path=str(tmp_path / "c.db"))
    store.create_thread("c1", title="t")
    store.append_message(
        thread_id="c1", role="user", content="a", metadata={"request_id": "r1"})
    store.append_skill_event(skill_id="s", event="matched", run_id="r1")
    store.append_skill_event(skill_id="s", event="matched", run_id="r2")
    store.forget_request("r1")
    assert len(store.list_skill_events()) == 1


def test_telemetry_is_suppressed_when_the_conversation_is_not_halberts(monkeypatch):
    import halbert_core.skills.telemetry as telemetry

    monkeypatch.setattr(telemetry, "_telemetry_permitted", lambda: False)
    assert telemetry.record_skill_event("config-ops", "matched") is False


def test_the_permission_check_fails_closed(monkeypatch):
    """A predicate that cannot be read is not permission."""
    import halbert_core.agents.threads as threads
    import halbert_core.skills.telemetry as telemetry

    def _boom():
        raise RuntimeError("no thread manager")

    monkeypatch.setattr(threads, "_conversation_is_halberts", _boom)
    assert telemetry._telemetry_permitted() is False
