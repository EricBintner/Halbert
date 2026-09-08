# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Consent copy and its manifest — Gate 4's evidentiary half.

PERMISSION-AND-CONSENT-SYSTEM-2026-09-06.md §1.5:

    ``text_shown_sha256`` is the field that turns a record into evidence.
    Without it, \"the user consented\" is a boolean anyone can assert.
    With it, \"the user agreed to X\" resolves to a specific wording in a
    specific release. It only works if the wording is resolvable, so:

    - All consent copy lives in exactly one module, ``consent/copy.py``.
    - ``consent/copy_manifest.json`` is committed alongside, mapping
      capability → copy key → digest.
    - the test asserts (a) every consenting capability in the vocabulary
      has copy, and (b) the shipped digests match the manifest.
    - Superseded copy versions ship as versioned assets, so a
      two-year-old record still resolves.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from halbert_core.consent.copy import (
    CURRENT_VERSION,
    available_versions,
    copy_for,
    copy_manifest_path,
    digest_for,
)
from halbert_core.persona.permission import (
    NEVER_CEILING_IDS,
    VOCABULARY,
    takes_consent_records,
)


def _manifest() -> dict:
    return json.loads(copy_manifest_path().read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# (a) Every consenting capability in the vocabulary has copy.
# ---------------------------------------------------------------------------


def test_every_consenting_capability_has_copy():
    consenting = {
        cap for cap in VOCABULARY if takes_consent_records(cap)
    }

    assert consenting == set(_manifest().keys())


def test_the_copy_module_covers_the_consenting_set_too():
    from halbert_core.consent.copy import copy_for as _copy_for

    for capability in VOCABULARY:
        if not takes_consent_records(capability):
            continue
        assert _copy_for(capability).strip(), capability


def test_copy_exists_for_the_declared_absent_capability_as_the_absence_notice():
    """egress.telemetry never grants, but it is a consenting kind — its
    copy is the notice that the absence is provable, so the manifest
    covers the whole consenting vocabulary with nothing skipped."""
    text = copy_for("egress.telemetry")

    assert "never" in text.lower()


def test_non_consenting_capabilities_have_no_copy():
    """sys.* has no consent surface (§1.3), so it has no copy to show."""
    sys_ids = {
        cap for cap, kind in VOCABULARY.items() if kind == "sys"
    }
    assert not sys_ids & set(_manifest().keys())


# ---------------------------------------------------------------------------
# (b) The shipped digests match the manifest.
# ---------------------------------------------------------------------------


def test_every_shipped_digest_matches_the_copy():
    manifest = _manifest()

    for capability, versions in manifest.items():
        for version, digest in versions.items():
            assert digest == digest_for(capability, version), (
                f"{capability}/{version}: manifest digest does not match the "
                f"shipped copy — the evidence link is broken"
            )


def test_the_digest_is_the_sha256_of_the_exact_text():
    text = copy_for("sensor.screen")
    assert digest_for("sensor.screen") == hashlib.sha256(text.encode("utf-8")).hexdigest()


def test_the_manifest_is_committed_alongside():
    assert copy_manifest_path().is_file()
    assert copy_manifest_path().name == "copy_manifest.json"


def test_a_manifest_gap_is_a_failure():
    """No consenting capability may lose its copy in a release — the
    manifest and the module are generated from the same source of truth
    and must not drift."""
    manifest = _manifest()
    for capability in manifest:
        assert manifest[capability], f"{capability}: no versions in the manifest"


# ---------------------------------------------------------------------------
# Superseded copy resolves — versioned assets.
# ---------------------------------------------------------------------------


def test_superseded_versions_ship_as_assets():
    """At least one superseded wording is shipped so the round trip from a
    two-year-old text_shown_sha256 to its words stays provable."""
    assert "v0" in available_versions("sensor.screen")
    assert digest_for("sensor.screen", "v0") in set(
        _manifest()["sensor.screen"].values()
    )


def test_the_current_version_is_in_the_manifest_for_every_capability():
    manifest = _manifest()
    for capability, versions in manifest.items():
        assert CURRENT_VERSION in versions, capability


def test_copy_for_a_missing_version_fails_closed():
    with pytest.raises(KeyError):
        copy_for("sensor.screen", "v99")


def test_copy_for_a_missing_capability_fails_closed():
    with pytest.raises(KeyError):
        copy_for("sensor.mind_reader")


# ---------------------------------------------------------------------------
# The copy is honest — deterministic, in Halbert's voice, no LLM.
# ---------------------------------------------------------------------------


def test_every_copy_names_what_it_does():
    for capability in _manifest():
        text = copy_for(capability)
        assert len(text) > 40, f"{capability}: copy too thin to be evidence"


def test_the_privileged_copy_states_the_reauth():
    assert "password" in copy_for("reach.privileged").lower() or "re-auth" in copy_for("reach.privileged").lower()


def test_the_biometric_copy_states_its_biometric():
    assert "biometric" in copy_for("sensor.voiceprint").lower()