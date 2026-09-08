# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""SK-1: the provenance sidecar schema (`.halbert-skill.json`).

Design §5.4: provenance lives in the sidecar beside SKILL.md, keyed by the
stable id — "never inferred from location, never keyed by name. A rename, a
moved root, or an ecosystem pack that happens to collidingly share a name
must not smuggle or forfeit provenance." SK-1 owns the schema and the reader;
the write path is SK-6's, so this suite pins what the reader accepts and
what it refuses, and what a join means.
"""

from __future__ import annotations

import json

import pytest

from halbert_core.skills.parser import parse_skill
from halbert_core.skills.sidecar import (
    MAX_SIDECAR_BYTES,
    SIDECAR_NAME,
    SkillSidecar,
    SkillSidecarError,
    load_sidecar,
    verify_sidecar_join,
)

_ID = "sk_01JZQ0A1B2C3D4E5F6G7H8J9K0"


def _skill(skill_id=_ID, name="storage-ops"):
    halbert = f"halbert:\n  id: {skill_id}\n" if skill_id else ""
    return parse_skill(f"---\nname: {name}\n{halbert}---\nbody")


def _write_sidecar(tmp_path, payload, name=SIDECAR_NAME):
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / name
    if isinstance(payload, str):
        path.write_text(payload, encoding="utf-8")
    else:
        path.write_text(json.dumps(payload), encoding="utf-8")
    return path


# ── Reading ────────────────────────────────────────────────────────────

def test_a_sidecar_is_read_and_parsed(tmp_path):
    path = _write_sidecar(tmp_path, {"id": _ID, "created_by": "operator"})
    sidecar = load_sidecar(path)
    assert sidecar == SkillSidecar(id=_ID, created_by="operator", state=None)


def test_a_missing_sidecar_is_none_not_an_error(tmp_path):
    assert load_sidecar(tmp_path / SIDECAR_NAME) is None


def test_created_by_accepts_exactly_agent_or_operator(tmp_path):
    for good in ("agent", "operator"):
        path = _write_sidecar(tmp_path, {"id": _ID, "created_by": good})
        assert load_sidecar(path).created_by == good
    bad = _write_sidecar(tmp_path, {"id": _ID, "created_by": "the-llm"})
    with pytest.raises(SkillSidecarError, match="created_by"):
        load_sidecar(bad)


def test_an_id_outside_the_sidecar_must_still_be_a_valid_skill_id(tmp_path):
    path = _write_sidecar(tmp_path, {"id": "just-some-string"})
    with pytest.raises(SkillSidecarError, match="id"):
        load_sidecar(path)


def test_sidecar_state_is_validated(tmp_path):
    path = _write_sidecar(tmp_path, {"id": _ID, "state": "draft"})
    assert load_sidecar(path).state == "draft"
    bad = _write_sidecar(tmp_path, {"id": _ID, "state": "golden"})
    with pytest.raises(SkillSidecarError, match="state"):
        load_sidecar(bad)


def test_unknown_sidecar_keys_are_tolerated(tmp_path):
    # The sidecar is JSON an operator may hand-edit; a forward-compat key
    # must not brick provenance.
    path = _write_sidecar(
        tmp_path, {"id": _ID, "created_by": "agent", "future_field": [1]}
    )
    assert load_sidecar(path).id == _ID


def test_a_non_mapping_sidecar_is_refused(tmp_path):
    path = _write_sidecar(tmp_path, "[1, 2, 3]")
    with pytest.raises(SkillSidecarError, match="mapping"):
        load_sidecar(path)


# ── The same untrusted-input treatment as SKILL.md ────────────────────

def test_an_oversized_sidecar_is_refused(tmp_path):
    big = {"id": _ID, "note": "y" * (MAX_SIDECAR_BYTES + 200)}
    path = tmp_path / SIDECAR_NAME
    tmp_path.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(big), encoding="utf-8")
    with pytest.raises(SkillSidecarError, match="8"):
        load_sidecar(path)


def test_a_nul_byte_in_a_sidecar_is_refused(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / SIDECAR_NAME
    path.write_bytes(b'{"id": "x\x00"}')
    with pytest.raises(SkillSidecarError, match="NUL"):
        load_sidecar(path)


def test_non_utf8_sidecars_are_refused(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / SIDECAR_NAME
    path.write_bytes(b'{"note": "caf\xe9"}')
    with pytest.raises(SkillSidecarError, match="UTF-8"):
        load_sidecar(path)


# ── The join ──────────────────────────────────────────────────────────

def test_a_matching_id_joins():
    skill = _skill()
    sidecar = SkillSidecar(id=_ID, created_by="agent", state=None)
    assert verify_sidecar_join(skill, sidecar)


def test_a_mismatched_id_does_not_join():
    other = "sk_01JZQ0A1B2C3D4E5F6G7H8J9K1"
    skill = _skill(skill_id=_ID)
    sidecar = SkillSidecar(id=other, created_by="agent", state=None)
    assert not verify_sidecar_join(skill, sidecar), (
        "a pack that collidingly shares a name must not smuggle provenance; "
        "the id is the identity and a mismatch is a mismatch"
    )


def test_a_join_needs_both_ids():
    # Provenance is never inferred from location: a sidecar without an id,
    # or a skill without one, has nothing to join on.
    skill_with = _skill()
    skill_without = _skill(skill_id=None)
    sidecar_without = SkillSidecar(id=None, created_by="agent", state=None)
    assert not verify_sidecar_join(skill_without, sidecar_without)
    assert not verify_sidecar_join(skill_with, sidecar_without)
    assert not verify_sidecar_join(skill_without, SkillSidecar(
        id=_ID, created_by="agent", state=None))


