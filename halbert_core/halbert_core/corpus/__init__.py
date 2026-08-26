# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Corpus governance: licensing policy and distribution gates.

Deliberately dependency-light (stdlib + PyYAML) so the build-time licence gate
can run in a minimal CI environment without pulling chromadb/torch.
"""

from .license_policy import (
    Channel,
    LicensePolicy,
    LicenseTerms,
    LicenseViolation,
    PolicyReport,
    SourceDecision,
    Violation,
)

__all__ = [
    "Channel",
    "LicensePolicy",
    "LicenseTerms",
    "LicenseViolation",
    "PolicyReport",
    "SourceDecision",
    "Violation",
]
