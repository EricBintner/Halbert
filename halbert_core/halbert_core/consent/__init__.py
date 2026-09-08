# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The consent ledger — D3-P2 of the OpenClaw lift permission series.

The D3-P1 pure evaluator (``halbert_core.persona.permission``) named the
*record* (``persona/permission/consent.py`` — the frozen ``ConsentRecord``
dataclass and its pure reads). This package is everything the record needs
in order to exist on a machine:

- ``store`` — the append-only ``haloysius.integrity.EventLog`` ledger at
  ``<data_dir>/consent`` and its ``<config_dir>/consent-state.json``
  projection, with ``record_decision()`` as the one writer and the
  widening asymmetry enforced at the function.
- ``copy`` — every word an owner can be shown, with digests pinned by the
  committed ``copy_manifest.json`` (Gate 4: consent resolves to specific
  words in a specific release).
- ``denials`` — the typed ``Denied`` the gate raises instead of answering
  ``False``, and ``ConsentUnavailable``, which is a Stop, never a
  fallback value.
- ``selfmod`` — ``GOVERNED_PATHS``: the Class-1 governing artefacts as a
  function of the resolved dirs, so no write primitive the agent drives
  can reach them (PART 6, layer 1).

Design: ``documentation/design/PERMISSION-AND-CONSENT-SYSTEM-2026-09-06.md``
PART 1 (§1.5, §1.7) and PART 6. Series:
``.handoff/OPENCLAW-LIFT-PACKET-SERIES-D3-PERMISSION-2026-09-07.md`` (D3-P2).
"""
from __future__ import annotations

from .denials import CLOSED_REASONS, ConsentUnavailable, Denied, denial_copy

__all__ = [
    "CLOSED_REASONS",
    "ConsentUnavailable",
    "Denied",
    "denial_copy",
]