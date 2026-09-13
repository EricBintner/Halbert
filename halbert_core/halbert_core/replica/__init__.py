# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Warm-standby replication for the singular entity.

The canonical host snapshots its entity-level state (persona memory,
conversation threads) and pushes it to paired body peers. A satellite
keeps the result as a read-only replica; if the canonical goes away the
body can still recall the mind, and the operator can promote it.

Phase 1 scope: memories.json + conversations.db — the two files that ARE
the entity's autobiography. Everything else (config, schedules, caches)
is node-local or rebuildable and is deliberately not replicated.
"""
