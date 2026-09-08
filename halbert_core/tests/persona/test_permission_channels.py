# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""D3-P4 — distribution channels and their capability ceilings (§2.4).

PERMISSION-AND-CONSENT-SYSTEM-2026-09-06.md §2.4:

    A capability the channel cannot deliver is not rendered disabled —
    it is not rendered. No greyed switches, no padlocks, no upsell.

THREE "channel" vocabularies exist in this codebase and must never be
conflated (the D3-P2/P3 executor's binding warning):

1. **Talk channels** — ``halbert_core/agents/channels.py`` (C1/C5):
   the ingress surfaces a *turn* arrives on (dashboard / voice /
   terminal), stamped into the user row's ``metadata.channel``. This
   module must not import or alias it.
2. **Distribution channels** — THIS module: how the app was
   distributed (macos-pro / macos-appstore / linux / flatpak /
   windows). This is the ``channel`` field of a consent record, and it
   owns the per-channel ``CapabilityCeiling``.
3. **Session-type degradation** — Wayland vs X11, aqua vs SSH: neither
   of the above. A within-channel fact that degrades the *row*, not
   the profile; the wiring reads it at runtime (D3-P5/P6).
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from halbert_core.persona.permission import channels as channels_mod
from halbert_core.persona.permission.ceiling import (
    EMPTY_CEILING,
    NEVER_CEILING_IDS,
    VOCABULARY,
)
from halbert_core.persona.permission.channels import (
    CHANNELS,
    DistributionChannel,
    channel_for,
    ceiling_for,
)


# ---------------------------------------------------------------------------
# The registry and its fail-closed lookup.
# ---------------------------------------------------------------------------


def test_the_shipped_channels_exist():
    assert set(CHANNELS) == {
        "macos-pro", "macos-appstore", "linux", "flatpak", "windows",
    }


def test_every_channel_id_is_stamped_on_the_record_field_vocabulary():
    """These ids are what a consent record's ``channel`` field carries —
    a closed set, so a mis-stamped record is detectable, not noise."""
    for channel in CHANNELS.values():
        assert isinstance(channel, DistributionChannel)
        assert channel.id == channel.id.lower()
        assert channel.label


def test_unknown_channel_fails_closed():
    with pytest.raises(LookupError):
        channel_for("steam")
    with pytest.raises(LookupError):
        ceiling_for("haos")


# ---------------------------------------------------------------------------
# Windows: the empty ceiling, refusing rather than degrading.
# ---------------------------------------------------------------------------


def test_windows_ceiling_is_the_empty_set_and_refuses_to_start():
    """§2.4: the ceiling is the empty set until W1–W13, and the app
    refuses to start rather than degrading permissively."""
    windows = channel_for("windows")
    assert windows.ceiling == EMPTY_CEILING
    assert len(windows.ceiling) == 0
    assert windows.ceiling.permits("sensor.hardware") is False
    assert windows.refuses_to_start is True
    assert windows.profiles_offered == ()


# ---------------------------------------------------------------------------
# The full channels — macOS Pro and native Linux.
# ---------------------------------------------------------------------------


def test_macos_pro_and_linux_carry_the_full_ceiling():
    for name in ("macos-pro", "linux"):
        ceiling = ceiling_for(name)
        assert ceiling.permits("sensor.screen")
        assert ceiling.permits("reach.terminal")
        assert ceiling.permits("reach.privileged")
        assert ceiling.permits("sensor.mic.push_to_talk")
        assert ceiling.permits("surface.lan_api")


def test_no_shipped_channel_carries_the_declared_absent_ids():
    """egress.telemetry is barred from every ceiling structurally
    (P1) — the App Store privacy label stays a compile-time property."""
    for channel in CHANNELS.values():
        assert not channel.ceiling.ids & NEVER_CEILING_IDS


def test_no_shipped_channel_carries_the_photo_library():
    """sensor.photos is not implemented; no row ships, on any channel."""
    for channel in CHANNELS.values():
        assert "sensor.photos" not in channel.ceiling.ids


def test_a_full_ceiling_is_derived_not_hand_listed():
    """The full channel ceiling is the shipped vocabulary minus the
    declared-absent and unimplemented ids — a new vocabulary id lands on
    the full channels by default, and on the companion channels only by
    deliberate decision."""
    full = ceiling_for("macos-pro").ids
    assert full == frozenset(VOCABULARY) - NEVER_CEILING_IDS - {"sensor.photos"}
    assert full == ceiling_for("linux").ids


# ---------------------------------------------------------------------------
# The App Store companion ceiling — provably incapable, not switched off.
# ---------------------------------------------------------------------------


def test_appstore_ceiling_omits_the_sandbox_impossible_set():
    ceiling = ceiling_for("macos-appstore")
    omitted = {
        # no sandbox entitlement grants Screen Recording (§7 matrix)
        "sensor.screen", "sensor.screen.continuous", "sensor.window_titles",
        # 2.5.4 bars ambient loops; single-shot camera + push-to-talk stay
        "sensor.camera.continuous", "sensor.mic.continuous",
        # container-confined: no host logs, no /etc
        "sensor.journal", "sensor.config_watch", "reach.config.read",
        # 2.4.5(vi), 2.5.2, 2.4.5(iii)(vi)
        "reach.config.write", "reach.terminal", "reach.privileged",
        # no host launchd/systemd from inside the sandbox
        "reach.service", "reach.package",
        # network.server is not requested: no inbound listener can exist
        "surface.lan_api", "surface.mcp", "surface.wyoming",
        "surface.ha_component",
        # Ollama is a separate daemon; bundling weights is out
        "sys.local_llm",
    }
    for capability in omitted:
        assert capability in VOCABULARY, capability
        assert not ceiling.permits(capability), (
            f"macos-appstore: {capability} must be off the ceiling, not off "
            f"by a switch"
        )


def test_appstore_ceiling_keeps_what_the_companion_delivers():
    ceiling = ceiling_for("macos-appstore")
    assert ceiling.permits("sensor.hardware")      # standalone posture read
    assert ceiling.permits("sensor.camera")        # single-shot, if it ships
    assert ceiling.permits("sensor.mic.push_to_talk")  # dictation
    assert ceiling.permits("reach.fs.read")        # via NSOpenPanel + bookmarks
    assert ceiling.permits("egress.peer")          # the paired body itself


def test_appstore_structurally_omits_the_biometric_asserted_twice():
    """§2.4: `sensor.voiceprint` is not on the ceiling at all — this is
    what keeps "Sensitive Info → Not Collected" true. Once by the data,
    once by the import-time assertion."""
    ceiling = ceiling_for("macos-appstore")
    assert "sensor.voiceprint" not in ceiling.ids
    assert not ceiling.permits("sensor.voiceprint")


def test_appstore_offers_reserved_and_attentive_only():
    """Present is not displayed on this channel (§2.4)."""
    assert channel_for("macos-appstore").profiles_offered == ("reserved", "attentive")


def test_the_companion_subject_note_ships_with_the_channel():
    note = channel_for("macos-appstore").degradation_note
    assert "companion" in note.lower()
    assert "body" in note.lower()


# ---------------------------------------------------------------------------
# The Flatpak companion ceiling.
# ---------------------------------------------------------------------------


def test_flatpak_omits_the_sysadmin_reach():
    """The Linux appendix: a sandboxed Flatpak cannot be the sysadmin
    product — reading the host's /etc and driving the host's systemd is
    precisely what the sandbox exists to stop."""
    ceiling = ceiling_for("flatpak")
    for capability in (
        "reach.config.read", "reach.config.write", "reach.terminal",
        "reach.privileged", "reach.service", "reach.package",
        "sensor.journal", "sensor.config_watch",
    ):
        assert not ceiling.permits(capability), capability


def test_flatpak_keeps_the_portal_deliverable_set():
    """Screen and camera/mic go through the portals, which are designed
    for sandboxed apps and revocable outside the app."""
    ceiling = ceiling_for("flatpak")
    assert ceiling.permits("sensor.screen")
    assert ceiling.permits("sensor.camera")
    assert ceiling.permits("sensor.mic.push_to_talk")


def test_flatpak_offers_reserved_and_attentive_only():
    assert channel_for("flatpak").profiles_offered == ("reserved", "attentive")


def test_flatpak_omits_local_model_and_inbound_listeners():
    ceiling = ceiling_for("flatpak")
    assert not ceiling.permits("sys.local_llm")
    assert not ceiling.permits("surface.lan_api")


# ---------------------------------------------------------------------------
# Every offered profile name resolves against the profiles registry.
# ---------------------------------------------------------------------------


def test_every_offered_profile_name_is_a_shipped_profile():
    from halbert_core.persona.permission.profiles import PROFILES

    for channel in CHANNELS.values():
        for name in channel.profiles_offered:
            assert name in PROFILES, f"{channel.id} offers unknown '{name}'"
    assert channel_for("macos-pro").profiles_offered == (
        "reserved", "attentive", "present",
    )
    assert channel_for("linux").profiles_offered == (
        "reserved", "attentive", "present",
    )


# ---------------------------------------------------------------------------
# The three vocabularies stay distinct — the binding warning, pinned.
# ---------------------------------------------------------------------------


def test_this_module_does_not_import_the_talk_channels():
    """Importing the distribution-channel module must never pull in
    ``agents/channels.py`` — the two vocabularies are separate facts and
    aliasing them is how a voice turn's provenance would be read as
    build provenance, or the reverse.

    Runs in a subprocess with the same editable-finder strip as
    wt_pytest.py (the shared venv pins halbert_core to the main tree
    otherwise, which resolves a different copy.py and proves nothing).
    """
    pkg_parent = str(Path(__file__).resolve().parents[2])
    code = (
        "import os, sys\n"
        f"sys.path.insert(0, {pkg_parent!r})\n"
        "_KEEP = ('builtins', '_frozen_importlib', '_frozen_importlib_external')\n"
        "sys.meta_path = [f for f in sys.meta_path if type(f).__module__ in _KEEP]\n"
        "for name in [m for m in sys.modules if m == 'halbert_core' or m.startswith('halbert_core.')]:\n"
        "    del sys.modules[name]\n"
        "import halbert_core.persona.permission.channels as pc\n"
        "import halbert_core.consent.copy as copy_mod\n"
        "assert copy_mod.__file__.startswith(os.path.realpath("
        f"{pkg_parent!r}"
        ")), copy_mod.__file__\n"
        "assert not [m for m in sys.modules if m == 'halbert_core.agents.channels'], "
        "'the distribution channels must not import the talk channels'\n"
        "assert not hasattr(pc, 'ChannelDeclaration'), "
        "'the distribution channels must not alias the talk channel type'\n"
    )
    subprocess.run([sys.executable, "-c", code], check=True)


def test_the_degradation_note_is_documented_not_behaviour():
    """§2.4's degradation sentences are shipped data — the honest shorter
    list is a first-run/Settings rendering fact (D3-P6), never a runtime
    downgrade this module performs."""
    for channel in CHANNELS.values():
        assert isinstance(channel.degradation_note, str)
        assert channel.degradation_note


def test_the_session_type_note_names_x11_as_row_degradation():
    """Linux X11 degrades the *row*, not the profile (§2.4): the channel
    still offers all three profiles; the X11 sentence belongs to the
    screen and the wiring, carried here as the channel's note."""
    assert "x11" in channel_for("linux").degradation_note.lower()