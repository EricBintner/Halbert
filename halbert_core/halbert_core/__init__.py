# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Halbert core package.
See documentation/ for specifications.
"""

# Keep in sync with halbert_core/pyproject.toml (tests/test_legal_metadata.py asserts it).
__version__ = "0.1.1"
__license__ = "GPL-3.0-or-later"
__copyright__ = "Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors"

# GPLv3 "Appropriate Legal Notices" (GPLv3 §0, §5(d)) shown by the interactive
# entry points: `halbert info`, `halbert --version`, and the dashboard startup log.
LEGAL_NOTICE = (
    "Halbert  Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors\n"
    "This program comes with ABSOLUTELY NO WARRANTY; for details type 'halbert license'.\n"
    "This is free software, and you are welcome to redistribute it under certain\n"
    "conditions (GNU GPL v3.0 or later); type 'halbert license --full' for the licence text."
)
