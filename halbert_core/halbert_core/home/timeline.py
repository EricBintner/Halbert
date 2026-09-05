# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Shim — TimelineStore moved to :mod:`halbert_core.continuity.timeline`.

"observation" already means ``ctx.observations`` tool output, Haloysius's
``ObservationStore``, ``STATE-1``'s citable observation ids and SourcePrep
observations; "timeline" already names ``/api/agent/timeline`` and the
somatic stream. The event ledger belongs with the rest of Halbert's
continuity group (state_store, provenance, freshness), not under ``home/``
— it is a sysadmin-install concern as much as a home one.
"""

from __future__ import annotations

from ..continuity.timeline import TimelineEvent, TimelineStore

__all__ = ["TimelineStore", "TimelineEvent"]
