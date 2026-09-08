# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""D3-P4 — the three profiles as data (§2.1 grant table), and acceptance.

PERMISSION-AND-CONSENT-SYSTEM-2026-09-06.md PART 2:

    A profile is a named set of proposals, not a runtime object. On
    acceptance it writes N individual consent records, each carrying
    ``via: "profile:attentive"``. There is no code path anywhere that
    asks "which profile am I?" — every grant is individually recorded,
    individually shown, individually revocable. The profile name is
    provenance.

The five bright lines are import-time invariants of the profile
compiler (§2.1), the shipped-default reversals are data, and the
Attentive/Present boundary — *it is whether anyone asked* — is pinned
as a data assertion. Acceptance goes through the D3-P2 store's one
writer, each record carrying the digest of the shipped review-screen
copy for the profile (Gate 4).
"""
from __future__ import annotations

import pytest

from halbert_core.consent.copy import (
    copy_for,
    digest_for,
    review_copy_key,
    review_digest_for,
)
from halbert_core.consent.store import ConsentStore, GrantRefused
from halbert_core.persona.permission import profiles as profiles_mod
from halbert_core.persona.permission.profiles import (
    ALWAYS_ON_IDS,
    PRESELECTED_PROFILE,
    PROFILE_NAMES,
    PROFILES,
    ProfileRefused,
    ProfileProposal,
    accept_profile,
    profile_proposals_for,
)
from halbert_core.persona.permission.ceiling import VOCABULARY, takes_consent_records


# ---------------------------------------------------------------------------
# Fixtures.
# ---------------------------------------------------------------------------


@pytest.fixture
def store(tmp_path):
    return ConsentStore(
        data_dir=str(tmp_path / "data"), config_dir=str(tmp_path / "config")
    )


def _owner(**kw):
    base = dict(
        kind="owner", id="local:501", name="Eric",
        authn="os_reauth:touchid", at_machine=True,
    )
    base.update(kw)
    return profiles_mod.Principal(**base)


def _accept(store, profile="attentive", channel="macos-pro", **kw):
    return accept_profile(
        profile, store,
        principal=_owner(),
        surface="desktop-app/first-run",
        channel=channel,
        **kw,
    )


# ---------------------------------------------------------------------------
# The profiles exist as data, and only as data.
# ---------------------------------------------------------------------------


def test_exactly_three_profiles_ship():
    assert set(PROFILES) == {"reserved", "attentive", "present"}
    assert PROFILE_NAMES == ("reserved", "attentive", "present")


def test_attentive_is_preselected():
    """§2.3 — Attentive is preselected. That is a first-run-UI fact; this
    packet ships the datum and the copy digests for it, nothing more."""
    assert PRESELECTED_PROFILE == "attentive"
    assert PROFILES["attentive"].preselected is True
    assert PROFILES["reserved"].preselected is False
    assert PROFILES["present"].preselected is False


def test_every_profile_carries_its_statement():
    """The three statements of PART 2 are the profile's own words, shipped
    verbatim so the review screen and the record agree."""
    assert "I don't watch" in PROFILES["reserved"].statement
    assert "I look after this machine" in PROFILES["attentive"].statement
    assert "I'm awake in the room" in PROFILES["present"].statement


def test_present_is_a_superset_of_attentive():
    """§2.2: Present is everything Attentive is, plus the room."""
    attentive = {p.capability for p in PROFILES["attentive"].grants}
    present = {p.capability for p in PROFILES["present"].grants}
    assert attentive < present


# ---------------------------------------------------------------------------
# The five bright lines — compiler invariants, pinned by test.
# ---------------------------------------------------------------------------


def test_no_profile_grants_any_egress():
    """Bright line 1: a profile is a statement about this machine's own
    body; it can never be the reason something left — not even a denial
    that would imply the profile governs egress (§2.5: egress is decided
    per destination at configuration time)."""
    for profile in PROFILES.values():
        for proposal in profile.grants:
            assert not proposal.capability.startswith("egress."), (
                f"{profile.name}: {proposal.capability} — no profile may "
                f"carry any egress row"
            )


def test_no_profile_grants_auto_act():
    """Bright line 2: approval is never granted in bulk. ``act`` and
    ``orchestrate`` are individual typed-phrase grants."""
    for profile in PROFILES.values():
        assert "auto.act" not in {p.capability for p in profile.grants}
        assert profile.autonomy_default in ("observe", "suggest")
        assert profile.autonomy_default != "act"


def test_no_profile_grants_a_biometric():
    """Bright line 3: sensor.voiceprint is always an individual,
    typed-phrase act with its own record and a 400-day default TTL."""
    for profile in PROFILES.values():
        assert "sensor.voiceprint" not in {p.capability for p in profile.grants}


def test_the_voiceprint_ttl_default_is_400_days():
    assert profiles_mod.VOICEPRINT_DEFAULT_TTL_DAYS == 400


def test_privileged_reauths_every_time_in_every_profile():
    """Bright line 4: reach.privileged re-authenticates every single time,
    including in Present. Matching the polkit table: auth_admin_keep
    appears exactly once, on the read-only diagnostic set."""
    for profile in PROFILES.values():
        for proposal in profile.grants:
            if proposal.capability == "reach.privileged":
                assert proposal.decision is profiles_mod.ConsentDecision.GRANTED
                assert proposal.scope.get("re_auth") == "every_time", (
                    f"{profile.name}: reach.privileged without the "
                    f"every-time re-auth promise"
                )
                assert proposal.ask_every_use is True


def test_no_profile_requests_full_disk_access_or_accessibility():
    """Bright line 5: those are the two rows a reviewer reads first, and
    Halbert is on neither list. The vocabulary cannot express them, and no
    proposal escapes the vocabulary."""
    assert "full_disk_access" not in VOCABULARY
    assert "accessibility" not in VOCABULARY
    for profile in PROFILES.values():
        for proposal in profile.grants:
            assert proposal.capability in VOCABULARY, (
                f"{profile.name}: {proposal.capability} is not a shipped "
                f"capability id"
            )


def test_every_profile_id_is_a_consenting_capability():
    """Every id in every profile is in the vocabulary (the gate's wording),
    and takes consent records — surface/sys ids are config or affordance
    facts and ride the profile's own fields, never its grants."""
    for profile in PROFILES.values():
        for proposal in profile.grants:
            assert takes_consent_records(proposal.capability), (
                f"{profile.name}: {proposal.capability} does not take "
                f"consent records"
            )


def test_no_profile_grants_the_unimplemented_photo_library():
    """sensor.photos is not implemented and no row ships — a grant for it
    would be a control that governs nothing."""
    for profile in PROFILES.values():
        assert "sensor.photos" not in {p.capability for p in profile.grants}


def test_a_profile_definition_that_crosses_a_line_fails_at_import():
    """The compiler runs at import, not at runtime: constructing a registry
    with a bright-line violation raises before any record could be
    written."""
    bad = dict(
        name="evil",
        statement="I take everything.",
        preselected=False,
        turn_scoped_only=False,
        autonomy_default="act",
        grants=(
            ProfileProposal(
                capability="egress.cloud_model",
                decision=profiles_mod.ConsentDecision.GRANTED,
            ),
        ),
        surface_defaults={},
    )
    with pytest.raises(ValueError):
        profiles_mod._compile_profiles({bad["name"]: profiles_mod.ProfileDefinition(**bad)})


# ---------------------------------------------------------------------------
# The Attentive/Present line: it is whether anyone asked.
# ---------------------------------------------------------------------------


def test_attentive_grants_zero_always_on_capabilities():
    """§2.3: Attentive grants zero always-on sensors, zero biometrics,
    zero egress, zero unattended change. Pinned as data: every Attentive
    grant opens inside a turn a person started."""
    attentive_granted = {
        p.capability for p in PROFILES["attentive"].grants
        if p.decision is profiles_mod.ConsentDecision.GRANTED
    }
    assert not attentive_granted & ALWAYS_ON_IDS


def test_reserved_grants_zero_always_on_capabilities():
    reserved_granted = {
        p.capability for p in PROFILES["reserved"].grants
        if p.decision is profiles_mod.ConsentDecision.GRANTED
    }
    assert not reserved_granted & ALWAYS_ON_IDS


def test_the_always_on_set_is_the_ones_nobody_asked_for():
    """The set is exactly the design's: the continuous sensors, the loop
    nobody is in, and unprompted speech. auto.scheduler is the deliberate
    exception (§2.1: nightly sweep + morning summary — jobs the owner
    created, each with its own revocable record), so it is not in the
    set."""
    assert ALWAYS_ON_IDS == frozenset({
        "sensor.screen.continuous",
        "sensor.camera.continuous",
        "sensor.mic.continuous",
        "auto.observe",
        "auto.speak",
    })


def test_present_does_hold_the_loops_nobody_asked_for():
    """The boundary is real: Present is where the loops run when nobody is
    there, so the invariant must be falsifiable in that direction."""
    present_granted = {
        p.capability for p in PROFILES["present"].grants
        if p.decision is profiles_mod.ConsentDecision.GRANTED
    }
    assert present_granted & ALWAYS_ON_IDS == {
        "sensor.screen.continuous", "sensor.mic.continuous",
        "auto.observe", "auto.speak",
    }


# ---------------------------------------------------------------------------
# The shipped-default reversals, as data (§2.1).
# ---------------------------------------------------------------------------


def test_silent_capture_on_intent_is_denied_in_every_profile():
    """The reversal: ``senses.vision.capture_on_intent`` ships ``True``
    today; no profile may carry it forward. Acceptance writes the denial
    as a record, so the default is durable and visible in the ledger."""
    for profile in PROFILES.values():
        proposals = {p.capability: p for p in profile.grants}
        assert proposals["auto.capture_on_intent"].decision \
            is profiles_mod.ConsentDecision.DENIED


def test_redaction_is_required_on_on_demand_screen_grants():
    """The reversal: ``redaction.enabled`` ships off today. Every profile
    that grants the on-demand screen requires redaction in the grant's
    own scope."""
    for name in ("attentive", "present"):
        proposals = {p.capability: p for p in PROFILES[name].grants}
        assert proposals["sensor.screen"].scope.get("redaction") == "required"


def test_the_autonomy_default_is_suggest_where_the_product_lives():
    """The reversal: ``observe`` is not the safe default, it is the
    useless one. Reserved stays observe; Attentive and Present propose
    ``suggest``. It is data the first-run wiring reads — never a grant
    (auto.act is bright-line barred)."""
    assert PROFILES["reserved"].autonomy_default == "observe"
    assert PROFILES["attentive"].autonomy_default == "suggest"
    assert PROFILES["present"].autonomy_default == "suggest"


def test_wyoming_degrades_to_loopback_in_attentive():
    """The reversal: Wyoming ships bound to 0.0.0.0 today. Surfaces are
    config facts (they take no consent records), shipped as profile data."""
    assert PROFILES["reserved"].surface_defaults["surface.wyoming"] == "off"
    assert PROFILES["attentive"].surface_defaults["surface.wyoming"] \
        == "loopback_or_uds"
    assert PROFILES["present"].surface_defaults["surface.wyoming"] \
        == "lan_token_pinned_tls"
    for profile in PROFILES.values():
        assert profile.surface_defaults["surface.lan_api"] == "off"
        assert profile.surface_defaults["surface.mcp"] == "off"


# ---------------------------------------------------------------------------
# The grant table, as the §2.1 rows the design states.
# ---------------------------------------------------------------------------


def test_reserved_grants_only_its_four_rows():
    granted = {
        p.capability for p in PROFILES["reserved"].grants
        if p.decision is profiles_mod.ConsentDecision.GRANTED
    }
    assert granted == {
        "sensor.hardware", "reach.config.read",
        "reach.fs.read", "reach.fs.write",
    }


def test_attentive_grants_its_table_rows():
    granted = {
        p.capability for p in PROFILES["attentive"].grants
        if p.decision is profiles_mod.ConsentDecision.GRANTED
    }
    assert granted == {
        "sensor.hardware", "sensor.journal", "sensor.config_watch",
        "sensor.screen", "sensor.window_titles", "sensor.mic.push_to_talk",
        "reach.config.read", "reach.fs.write", "reach.config.write",
        "reach.terminal", "reach.privileged", "reach.service",
        "reach.package", "reach.display_power", "reach.fs.read",
        "auto.scheduler",
    }


def test_attentive_ask_rows_ask_every_use():
    """`ask` = granted, every use confirmed with the literal artefact
    shown."""
    proposals = {p.capability: p for p in PROFILES["attentive"].grants}
    assert proposals["reach.config.write"].ask_every_use is True
    assert proposals["reach.privileged"].ask_every_use is True


def test_present_grants_its_table_rows():
    granted = {
        p.capability for p in PROFILES["present"].grants
        if p.decision is profiles_mod.ConsentDecision.GRANTED
    }
    assert granted == {
        "sensor.hardware", "sensor.journal", "sensor.config_watch",
        "sensor.screen", "sensor.screen.continuous", "sensor.window_titles",
        "sensor.camera", "sensor.camera.network", "sensor.mic.push_to_talk",
        "sensor.mic.continuous",
        "reach.config.read", "reach.fs.read", "reach.fs.write",
        "reach.config.write", "reach.terminal", "reach.privileged",
        "reach.service", "reach.package", "reach.network",
        "reach.display_power", "reach.home",
        "auto.scheduler", "auto.observe", "auto.speak",
    }


def test_present_never_grants_what_the_table_leaves_off():
    """The ○ rows are offered on the settings row, off — never granted by
    the profile, and no record is written for them at acceptance."""
    present_granted = {
        p.capability for p in PROFILES["present"].grants
        if p.decision is profiles_mod.ConsentDecision.GRANTED
    }
    assert "sensor.camera.continuous" not in present_granted
    assert "auto.capture_on_error" not in present_granted
    assert "sensor.voiceprint" not in present_granted


def test_present_home_scope_carries_the_ha_tiers():
    proposals = {p.capability: p for p in PROFILES["present"].grants}
    tiers = proposals["reach.home"].scope["tiers"]
    assert tiers["T0"] == "granted"
    assert tiers["T1"] == "granted"
    assert tiers["T2"] == "offered"
    assert tiers["T3"] == "out_of_band"
    assert tiers["T4"] == "denied"


# ---------------------------------------------------------------------------
# Acceptance — N records, the right via, through the one writer.
# ---------------------------------------------------------------------------


def test_acceptance_writes_exactly_n_records_with_the_right_via(store):
    records = _accept(store, "attentive")
    proposals = profile_proposals_for("attentive", "macos-pro")
    assert len(records) == len(proposals) == 17
    for record in records:
        assert record.via == "profile:attentive"
        assert record.channel == "macos-pro"
        assert record.capability in {p.capability for p in proposals}
    written = store.records()
    assert len(written) == 17
    assert all(r.via == "profile:attentive" for r in written)


def test_every_acceptance_record_carries_the_review_copy_digest(store):
    """Gate 4: every grant resolves to specific words — for a profile,
    the words of the review screen the owner actually read."""
    records = _accept(store, "attentive")
    expected = review_digest_for("attentive")
    for record in records:
        assert record.text_shown_sha256 == expected
    assert expected == digest_for(review_copy_key("attentive"))
    copy_for(review_copy_key("attentive"))  # the digest resolves to words


def test_attentive_grants_read_back_as_granted_and_the_reversal_as_denied(store):
    _accept(store, "attentive")
    assert store.state_for("sensor.screen") is profiles_mod.ConsentDecision.GRANTED
    assert store.state_for("auto.capture_on_intent") \
        is profiles_mod.ConsentDecision.DENIED
    assert store.state_for("sensor.mic.continuous") \
        is profiles_mod.ConsentDecision.ABSENT
    assert store.state_for("egress.cloud_model") \
        is profiles_mod.ConsentDecision.ABSENT


def test_reserved_acceptance_is_small_and_honest(store):
    records = _accept(store, "reserved")
    assert len(records) == 5
    assert store.state_for("sensor.screen") is profiles_mod.ConsentDecision.ABSENT


def test_present_acceptance_records_its_wider_set(store):
    records = _accept(store, "present")
    assert len(records) == 25
    assert store.state_for("auto.observe") is profiles_mod.ConsentDecision.GRANTED
    assert store.state_for("sensor.camera.continuous") \
        is profiles_mod.ConsentDecision.ABSENT


def test_acceptance_refuses_a_profile_the_channel_does_not_offer(store):
    """§2.4: the App Store channel offers Reserved and Attentive; Present
    is not displayed. Refusing the write is the fail-closed half of
    "not rendered"."""
    with pytest.raises(ProfileRefused) as exc:
        _accept(store, "present", channel="macos-appstore")
    assert exc.value.reason_code == "not_offered_on_channel"
    assert store.records() == []


def test_channel_degradation_drops_unreachable_rows_not_grants_them(store):
    """On the App Store channel the screen row is not rendered — so
    acceptance writes no sensor.screen record at all. A capability the
    channel cannot deliver is absent, never silently granted."""
    records = _accept(store, "attentive", channel="macos-appstore")
    assert "sensor.screen" not in {r.capability for r in records}
    assert "reach.terminal" not in {r.capability for r in records}
    assert store.state_for("sensor.screen") is profiles_mod.ConsentDecision.ABSENT


def test_windows_offers_nothing_and_acceptance_refuses(store):
    with pytest.raises(ProfileRefused) as exc:
        _accept(store, "reserved", channel="windows")
    assert store.records() == []


def test_an_agent_principal_cannot_accept_a_profile(store):
    """The §1.5 asymmetry holds at acceptance too: the agent is never an
    owner, it can only ask. Nothing is written."""
    with pytest.raises(GrantRefused):
        accept_profile(
            "attentive", store,
            principal=profiles_mod.Principal(kind="agent", at_machine=False),
            surface="desktop-app/first-run",
            channel="macos-pro",
        )
    assert store.records() == []


def test_a_remote_surface_cannot_accept_a_profile(store):
    with pytest.raises(GrantRefused):
        accept_profile(
            "attentive", store,
            principal=_owner(at_machine=False),
            surface="desktop-app/first-run",
            channel="macos-pro",
        )
    assert store.records() == []


def test_unknown_profile_and_channel_fail_closed(store):
    with pytest.raises(ProfileRefused):
        _accept(store, "obsequious")
    with pytest.raises(ProfileRefused):
        _accept(store, "attentive", channel="steam")
    assert store.records() == []


def test_proposals_for_an_unknown_anything_fail_closed():
    with pytest.raises(ProfileRefused):
        profile_proposals_for("obsequious", "macos-pro")
    with pytest.raises(ProfileRefused):
        profile_proposals_for("attentive", "steam")