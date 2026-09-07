# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Security: turn-scoped reportability over the write plane.

The hash-chained audit log (``obs.audit``) is the record of what ran;
this package holds per-turn rollups a user can be handed — and spoken —
afterwards (packet 04 B1).
"""