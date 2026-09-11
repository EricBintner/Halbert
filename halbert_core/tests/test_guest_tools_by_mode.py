# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The guest tool profile depends on the mode, for the first time.

Founder ruling 2026-09-10: the guest does home automation but never IT; the
main Halbert *shares its memory* with a fronting guest in normal mode; and
**only private mode is the fully isolated memory** -- private still controls
the house, it just cannot read Halbert's memory.

Why I6 permits the share rather than forbidding it: ``route_write`` already
sends ``conversation.message`` to HALBERT in normal mode and to the guest's
home in private mode. In normal mode the guest therefore *writes* to
Halbert's conversation store, so "may not read what it may not write" is
satisfied symmetrically. In private mode it stops writing there, so the read
must close with it.

``cognition.tick`` does not move: it is the guest's in every mode under R2,
so Halbert's psyche never learns a guest's evenings. Sharing a conversation
is not merging a psyche.

**The gate fails closed.** ``ownership._private_mode()`` returns False when it
cannot tell, which is the safe direction for a *write* (it lands in Halbert's
visible, erasable store) and exactly the wrong one for a *read gate*, where
False is the wider set. This module resolves the mode itself and treats
"cannot tell" as private.
"""
from unittest import mock

import pytest

from halbert_core.persona import guest_tools as gt


HALBERT_MEMORY_READS = ("recall_memory", "recall_thread", "resume_thread")
THE_HOUSE = ("ha_get_entity_state", "ha_call_service")
IT_TOOLS = ("run_command", "get_service_status", "get_cpu_info", "read_file")


def _mode(private: bool):
    """Patch the private-mode signal this module reads."""
    return mock.patch.object(gt, "_private_mode_for_tools", return_value=private)


class TestNormalModeSharesHalbertsMemory:

    def test_halbert_memory_reads_are_allowed(self):
        with _mode(private=False):
            for name in HALBERT_MEMORY_READS:
                assert gt.is_tool_allowed_for_guest(name), name

    def test_the_house_still_works(self):
        with _mode(private=False):
            for name in THE_HOUSE:
                assert gt.is_tool_allowed_for_guest(name), name

    def test_it_stays_denied(self):
        with _mode(private=False):
            for name in IT_TOOLS:
                assert not gt.is_tool_allowed_for_guest(name), name


class TestPrivateModeIsolatesMemoryOnly:

    def test_halbert_memory_reads_are_denied(self):
        with _mode(private=True):
            for name in HALBERT_MEMORY_READS:
                assert not gt.is_tool_allowed_for_guest(name), name

    def test_the_house_still_works(self):
        """Private isolates memory, not the home. The founder's words."""
        with _mode(private=True):
            for name in THE_HOUSE:
                assert gt.is_tool_allowed_for_guest(name), name

    def test_the_guest_still_reads_its_own_memory(self):
        with _mode(private=True):
            assert gt.is_tool_allowed_for_guest(gt.RECALL_GUEST_MEMORY_TOOL_NAME)

    def test_it_stays_denied(self):
        with _mode(private=True):
            for name in IT_TOOLS:
                assert not gt.is_tool_allowed_for_guest(name), name


class TestPrivateNeverWidens:
    """The structural invariant: private mode is a subset of normal, always."""

    def test_private_is_a_strict_subset_of_normal(self):
        with _mode(private=True):
            private = gt.guest_allowed_tools()
        with _mode(private=False):
            normal = gt.guest_allowed_tools()
        assert private < normal
        assert normal - private == frozenset(HALBERT_MEMORY_READS)


class TestTheGateFailsClosed:
    """`_private_mode()` in ownership returns False when it cannot tell, which
    is the wider set here. This gate must not inherit that."""

    def test_an_unreadable_signal_is_treated_as_private(self):
        with mock.patch(
            "halbert_core.persona.private_sources.active",
            side_effect=RuntimeError("source registry unavailable"),
        ):
            assert gt._private_mode_for_tools() is True
            for name in HALBERT_MEMORY_READS:
                assert not gt.is_tool_allowed_for_guest(name), name

    def test_the_house_survives_an_unreadable_signal(self):
        with mock.patch(
            "halbert_core.persona.private_sources.active",
            side_effect=RuntimeError("boom"),
        ):
            for name in THE_HOUSE:
                assert gt.is_tool_allowed_for_guest(name), name


class TestTheScriptPipelineSeesTheSameProfile:
    """execute_code reads the allowlist directly; it must get the mode too,
    or private mode leaks through the second path."""

    def test_execute_code_allowlist_is_mode_aware(self):
        from halbert_core.tools.execute_code import _guest_allowed
        with _mode(private=True):
            private = _guest_allowed()
        with _mode(private=False):
            normal = _guest_allowed()
        assert frozenset(HALBERT_MEMORY_READS) & private == frozenset()
        assert frozenset(HALBERT_MEMORY_READS) <= normal


class TestClassificationStillExhaustive:

    def test_no_tool_is_both_conditionally_allowed_and_denied(self):
        assert gt.HALBERT_MODE_ONLY_TOOLS & gt.GUEST_DENIED_TOOLS == frozenset()

    def test_self_check_passes(self):
        gt._self_check()
