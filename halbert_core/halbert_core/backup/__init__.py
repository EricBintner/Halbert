# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The State Vault — portable encrypted backup of the entity.

Where the replica answers "the canonical died an hour ago" (Phase 1),
the vault answers "the canonical died, the satellite died, and the house
burned down" — a passphrase-encrypted archive the user can keep anywhere:
a USB stick, a NAS, a friend's machine.

Everything an entity is fits in one tar: the signing key (custody
permitting), the configs, and the autobiography. Encrypted at rest —
the passphrase is the only thing the user must remember.
"""
