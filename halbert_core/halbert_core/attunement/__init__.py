# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Halbert's adapter onto ``haloysius.attunement``.

The engine decides *whether* the persona speaks. This package is everything
Halbert must supply for that decision to be well-founded: which of our
surfaces counts as speech, who the subject is, what the machine is currently
doing with the user, and where the standing requests live.

Why a package of its own rather than an extension of ``proactive/``:
``proactive/`` is about *events* and ``home/`` is about *the house*.
Attunement is about *the person*, and it is called from both plus the agent
turn path. Filing it under either would bury a cross-cutting concern in a
domain package.

Nothing here imports ``haloysius`` at module scope; the engine is an optional
dependency and every entry point degrades to today's behaviour without it.
"""
