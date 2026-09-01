# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""System-level hardware control (screen power, and whatever follows).

Modules here touch real hardware paths (sysfs, DPMS) and are best-effort by
contract: they self-report availability — presence checks, not gates (F5) —
and never raise into their callers.
"""