# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""SK-1: the CC-compatible skill format — namespaced frontmatter, stable ids,
capability requirements, and the boundary-safe reader.

The design (DESIGN-SKILLS-SYSTEM-2026-09-07 §1, §4.2–4.3) is byte-compatible
with Claude Code's frontmatter at the core (`name`, `description`,
`allowed-tools`, `license`, `metadata`) and carries Halbert's own extensions
under a single namespaced `halbert:` mapping, so an upstream field can never
collide with ours. Flat Halbert keys stay readable for one cycle through a
compat reader that warns and rewrites nothing.

The Determination rule retires the `provider:model` passthrough here
(§4.3, seam 2): `halbert.tier` accepts chat | specialist | vision — nothing
else — and the compat reader downgrades legacy passthrough values to `chat`
with a warning rather than honoring them.
"""

from __future__ import annotations

import logging

import pytest

from halbert_core.skills.parser import (
    MAX_FRONTMATTER_BYTES,
    MAX_SKILL_FILE_BYTES,
    SKILL_ID_RE,
    SkillRequirements,
    SkillParseError,
    clamp_description,
    new_skill_id,
    parse_skill,
    parse_skill_file,
    validate_description,
)


def _md(meta: str, body: str = "Expertise.") -> str:
    return f"---\n{meta}---\n{body}"


# ── The namespaced halbert: block ─────────────────────────────────────

def test_the_halbert_block_parses_every_extension_field():
    # Built without dedent: the nested `halbert` block has its own
    # indentation, which dedent would flatten into bad YAML.
    s = parse_skill(_md(
        "name: storage-ops\n"
        "description: Disk and filesystem operations\n"
        "halbert:\n"
        "  id: sk_01JZQ0A1B2C3D4E5F6G7H8J9K0\n"
        "  kind: ops\n"
        "  state: trusted\n"
        "  tier: specialist\n"
        "  priority: high\n"
        "  budget_multiplier: 1.5\n"
        "  subagent: true\n"
        "  max_turns: 4\n"
        "  role: storage-ops\n"
        "  scope: host-storage\n"
        "  knowledge_scope: knowledge-linux\n"
        "  trace_expand: false\n"
        "  extends: storage-ops-base\n"
        "  aliases: [disk, zfs]\n"
        "  triggers:\n"
        "    domains: [storage]\n"
        "    keywords: [zfs]\n"
        "  safety:\n"
        "    destructive_requires_approval: true\n"
        "    protected_paths: [/boot]\n"
        "  requires:\n"
        "    bins: [zfs]\n"
        "    os: [darwin, linux]\n"
    ))
    assert s.name == "storage-ops"
    assert s.description == "Disk and filesystem operations"
    assert s.id == "sk_01JZQ0A1B2C3D4E5F6G7H8J9K0"
    assert s.kind == "ops"
    assert s.state == "trusted"
    assert s.tier == "specialist"
    assert s.priority == "high"
    assert s.budget_multiplier == 1.5
    assert s.subagent is True
    assert s.max_turns == 4
    assert s.role == "storage-ops"
    assert s.scope == "host_storage"          # normalized, as today
    assert s.knowledge_scope == "knowledge_linux"
    assert s.trace_expand is False
    assert s.extends == "storage-ops-base"
    assert s.aliases == ("disk", "zfs")
    assert s.triggers.domains == ("storage",)
    assert s.triggers.keywords == ("zfs",)
    assert s.safety.destructive_requires_approval is True
    assert s.safety.protected_paths == ("/boot",)
    assert s.requires.bins == ("zfs",)
    assert s.requires.os == ("darwin", "linux")


def test_a_non_mapping_halbert_block_is_an_error():
    with pytest.raises(SkillParseError, match="halbert"):
        parse_skill(_md("name: x\nhalbert: oops\n"))


def test_unknown_keys_inside_halbert_are_refused_not_tolerated():
    # Top-level unknown keys stay tolerated (that is what loads third-party
    # packs), but tolerance ends at our own extension schema: a key inside
    # `halbert:` that is not ours is namespace squatting, not a typo upstream.
    with pytest.raises(SkillParseError, match="not one of"):
        parse_skill(_md("name: x\nhalbert:\n  wat: 1\n"))


def test_unknown_top_level_keys_stay_tolerated():
    s = parse_skill(_md("name: x\nlicense: MIT\nmetadata:\n  source: pack\n"))
    assert s.name == "x"


def test_cc_writes_allowed_tools_with_a_hyphen_and_it_maps_onto_ours():
    s = parse_skill(_md("name: x\nallowed-tools: read_file, run_command\n"))
    assert s.allowed_tools == ("read_file", "run_command")
    # The Halbert spelling keeps working; both mean the same tuple.
    s2 = parse_skill(_md("name: x\nallowed_tools: [read_file]\n"))
    assert s2.allowed_tools == ("read_file",)


# ── The compat reader: flat keys, one more cycle ──────────────────────

def test_flat_keys_still_parse_with_a_deprecation_warning(caplog):
    with caplog.at_level(logging.WARNING, logger="halbert_core.skills.parser"):
        s = parse_skill(_md(
            "name: flat-ops\n"
            "model: specialist\n"
            "priority: high\n"
            "triggers:\n"
            "  domains: [storage]\n"
        ))
    assert s.tier == "specialist"
    assert s.priority == "high"
    assert s.triggers.domains == ("storage",)
    warned = " ".join(r.message for r in caplog.records)
    assert "flat" in warned and "halbert:" in warned, (
        "the compat reader must warn — the one-cycle clock is the warning"
    )


def test_the_halbert_block_wins_over_a_flat_key_and_says_so(caplog):
    with caplog.at_level(logging.WARNING, logger="halbert_core.skills.parser"):
        s = parse_skill(_md(
            "name: x\n"
            "model: chat\n"
            "halbert:\n"
            "  tier: specialist\n"
        ))
    assert s.tier == "specialist"
    assert any("overrid" in r.message for r in caplog.records)


def test_a_pure_cc_format_pack_warns_not_at_all(caplog):
    # The warning is for Halbert's own flat keys, not for the ecosystem's
    # core fields: a pack must load silently.
    with caplog.at_level(logging.WARNING, logger="halbert_core.skills.parser"):
        s = parse_skill(_md(
            "name: pack-skill\n"
            "description: Does a thing\n"
            "license: MIT\n"
        ))
    assert s.name == "pack-skill"
    assert not [r for r in caplog.records if "flat" in r.message]


# ── The Determination rule: tier, not models ──────────────────────────

def test_tier_accepts_exactly_the_three_slot_names():
    for tier in ("chat", "specialist", "vision"):
        s = parse_skill(_md(f"name: x\nhalbert:\n  tier: {tier}\n"))
        assert s.tier == tier


def test_a_bad_tier_inside_halbert_is_an_error():
    with pytest.raises(SkillParseError, match="tier"):
        parse_skill(_md("name: x\nhalbert:\n  tier: orchestrator\n"))


def test_a_model_id_inside_halbert_tier_is_an_error_not_a_downgrade():
    # The downgrade is for *legacy* flat files only. Our own namespace
    # accepts the three slot names and nothing else.
    with pytest.raises(SkillParseError, match="tier"):
        parse_skill(_md("name: x\nhalbert:\n  tier: ollama:qwen3-coder\n"))


def test_the_legacy_provider_model_passthrough_is_retired_not_honored(caplog):
    # The old behavior passed "provider:model" through untouched, which is a
    # model recommendation smuggled in a config file. The compat reader
    # downgrades it to the chat tier with a warning (design §4.3).
    with caplog.at_level(logging.WARNING, logger="halbert_core.skills.parser"):
        s = parse_skill(_md("name: x\nmodel: ollama:qwen3-coder\n"))
    assert s.tier == "chat"
    assert any("downgrad" in r.message or "retired" in r.message
               for r in caplog.records), (
        "a silently honored passthrough is the defect this retires"
    )


def test_a_bad_flat_tier_is_still_an_error():
    with pytest.raises(SkillParseError, match="tier"):
        parse_skill(_md("name: x\nmodel: mega-brain\n"))


# ── Stable ids ────────────────────────────────────────────────────────

def test_new_skill_ids_look_like_stamped_ulids():
    first = new_skill_id()
    second = new_skill_id()
    assert SKILL_ID_RE.fullmatch(first), first
    assert SKILL_ID_RE.fullmatch(second), second
    assert first != second
    # Monotonic within a stamp: a later stamp never sorts first.
    assert second > first


def test_an_id_is_validated_at_parse():
    with pytest.raises(SkillParseError, match="id"):
        parse_skill(_md("name: x\nhalbert:\n  id: not-a-ulid\n"))


def test_an_absent_id_is_none_not_invented():
    # Provenance is never inferred: the id is stamped at creation (SK-6) and
    # the loader reading a file without one leaves it absent.
    assert parse_skill(_md("name: x\n")).id is None


# ── The requires schema ────────────────────────────────────────────────

def test_requires_parses_all_five_clauses():
    s = parse_skill(_md(
        "name: x\n"
        "halbert:\n"
        "  requires:\n"
        "    bins: [zfs, smartctl]\n"
        "    anyBins: [gsed, sed]\n"
        "    env: [HA_TOKEN]\n"
        "    os: [darwin]\n"
        "    config: [ha_connection]\n"
    ))
    assert s.requires == SkillRequirements(
        bins=("zfs", "smartctl"),
        any_bins=("gsed", "sed"),
        env=("HA_TOKEN",),
        os=("darwin",),
        config=("ha_connection",),
    )


def test_requires_is_none_when_not_declared():
    assert parse_skill(_md("name: x\n")).requires is None


def test_requires_accepts_a_scalar_as_a_one_tuple():
    s = parse_skill(_md("name: x\nhalbert:\n  requires:\n    bins: zfs\n"))
    assert s.requires.bins == ("zfs",)


def test_requires_refuses_unknown_clauses():
    with pytest.raises(SkillParseError, match="requires"):
        parse_skill(_md("name: x\nhalbert:\n  requires:\n    gpus: [rtx]\n"))


def test_requires_must_be_a_mapping():
    with pytest.raises(SkillParseError, match="requires"):
        parse_skill(_md("name: x\nhalbert:\n  requires: yes\n"))


def test_requires_entries_must_be_strings():
    with pytest.raises(SkillParseError, match="requires"):
        parse_skill(_md("name: x\nhalbert:\n  requires:\n    bins: [[1]]\n"))


# ── Lifecycle state ───────────────────────────────────────────────────

def test_state_accepts_the_three_lifecycle_values():
    for state in ("draft", "trusted", "archived"):
        s = parse_skill(_md(f"name: x\nhalbert:\n  state: {state}\n"))
        assert s.state == state


def test_state_defaults_to_trusted_for_operator_files():
    # Bundled and operator files carry no lifecycle marker; `draft` is what
    # agent-authored skills are born as (SK-6), not what a loaded file is.
    assert parse_skill(_md("name: x\n")).state == "trusted"


def test_a_bad_state_is_an_error():
    with pytest.raises(SkillParseError, match="state"):
        parse_skill(_md("name: x\nhalbert:\n  state: golden\n"))


# ── Name and description discipline ────────────────────────────────────

def test_the_name_charset_is_enforced():
    # The CC-compatible rule (design §1.2): ^[a-z0-9][a-z0-9-]{0,63}$ —
    # lowercase alphanumerics and hyphens, 1–64 chars, starting
    # alphanumeric. An underscored name would collide with the tool
    # namespace the reserved-name check compares against.
    for bad in ("Storage-Ops", "storage_ops", "-leading", "a" * 65,
                "has space"):
        with pytest.raises(SkillParseError, match="name"):
            parse_skill(_md(f"name: {bad}\n"))


def test_a_sixty_four_char_name_is_fine():
    s = parse_skill(_md(f"name: {'a' * 64}\n"))
    assert len(s.name) == 64


def test_descriptions_over_sixty_chars_are_refused_by_the_validator():
    # The 60-char discipline is create-time hard rejection, not lint
    # (design §1.2). The create tool is SK-6; the parse-side seam is this
    # pure validator, so both ends enforce the same number.
    assert validate_description("Short and routing-worthy") is None
    reason = validate_description("x" * 61)
    assert reason and "60" in reason


def test_the_ingest_clamp_marks_the_cut_visibly():
    # Ecosystem packs we do not control are load-time clamped with a visible
    # marker, never edited on disk — a silent trim is unauditable.
    clamped = clamp_description("y" * 100)
    assert len(clamped) == 60
    assert clamped.endswith("…")


# ── Lens purity through the namespace ─────────────────────────────────

def test_a_lens_cannot_smuggle_bindings_inside_halbert():
    with pytest.raises(SkillParseError, match="lens is voice only"):
        parse_skill(_md(
            "name: lensy\n"
            "kind: lens\n"
            "halbert:\n"
            "  safety:\n"
            "    protected_paths: [/boot]\n"
        ))


# ── Boundary-safe reads ───────────────────────────────────────────────

def test_an_oversized_skill_file_is_refused(tmp_path):
    big = tmp_path / "big" / "SKILL.md"
    big.parent.mkdir()
    filler = "z" * (MAX_SKILL_FILE_BYTES - 500) + "\n" + "x" * 600
    big.write_text(f"---\nname: big\n---\n{filler}", encoding="utf-8")
    assert big.stat().st_size > MAX_SKILL_FILE_BYTES
    with pytest.raises(SkillParseError, match="128"):
        parse_skill_file(big)


def test_an_oversized_frontmatter_block_is_refused(tmp_path):
    meta = "name: x\nnote: " + "y" * (MAX_FRONTMATTER_BYTES + 100)
    path = tmp_path / "fat.md"
    path.write_text(f"---\n{meta}\n---\nbody", encoding="utf-8")
    with pytest.raises(SkillParseError, match="frontmatter"):
        parse_skill_file(path)


def test_a_nul_byte_in_a_skill_file_is_refused(tmp_path):
    path = tmp_path / "nul.md"
    path.write_bytes(b"---\nname: x\n---\nbo\x00dy")
    with pytest.raises(SkillParseError, match="NUL"):
        parse_skill_file(path)


def test_non_utf8_bytes_are_refused(tmp_path):
    path = tmp_path / "latin.md"
    path.write_bytes(b"---\nname: x\n---\ncaf\xe9 au lait")
    with pytest.raises(SkillParseError, match="UTF-8"):
        parse_skill_file(path)


def test_a_well_formed_file_parses_unchanged(tmp_path):
    path = tmp_path / "fine" / "SKILL.md"
    path.parent.mkdir()
    path.write_text(
        "---\nname: fine-ops\ndescription: d\nhalbert:\n  tier: chat\n---\nB.",
        encoding="utf-8",
    )
    s = parse_skill_file(path)
    assert s.name == "fine-ops"  # from the directory, not the file name
    assert s.tier == "chat"
    assert s.source_path == path


# ── Extends keeps the invariants SK-1 adds ────────────────────────────

def test_extends_never_inherits_identity_or_lifecycle():
    parent = parse_skill(_md(
        "name: base\n"
        "halbert:\n"
        "  id: sk_01JZQ0A1B2C3D4E5F6G7H8J9K0\n"
        "  state: archived\n"
        "  tier: specialist\n"
    ))
    child = parse_skill(_md(
        "name: derived\n"
        "extends: base\n"
        "halbert:\n"
        "  id: sk_01JZQ0A1B2C3D4E5F6G7H8J9K1\n"
    ))
    from halbert_core.skills.registry import resolve_extends
    merged = resolve_extends(child, {"base": parent, "derived": child})
    assert merged.tier == "specialist"        # scalar: child left default
    assert merged.id == "sk_01JZQ0A1B2C3D4E5F6G7H8J9K1", (
        "an id is identity, not inheritance — a rename or a move must not "
        "smuggle the parent's provenance"
    )
    assert merged.state == "trusted", (
        "lifecycle is per-skill; extending an archived skill must not "
        "archive the child"
    )


def test_extends_inherits_requirements_like_any_other_capability():
    parent = parse_skill(_md(
        "name: base\nhalbert:\n  requires:\n    bins: [zfs]\n"
    ))
    child = parse_skill(_md("name: derived\nextends: base\n"))
    from halbert_core.skills.registry import resolve_extends
    merged = resolve_extends(child, {"base": parent, "derived": child})
    assert merged.requires is not None and merged.requires.bins == ("zfs",)


def test_the_skill_dataclass_is_still_frozen():
    s = parse_skill(_md("name: x\n"))
    with pytest.raises(Exception):
        s.tier = "vision"  # type: ignore[misc]