# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Key custody for Halbert's cryptographic identity.

``haloysius.integrity`` defines *how* a record is signed; this package
decides *where the private key lives*, which is the part the engine
deliberately does not own (see the ``SigningBackend`` seam).
"""
from .storage import (
    CustodyError,
    FileKeyStore,
    HalbertSigner,
    HardwareKeyStore,
    KeychainKeyStore,
    KeyStore,
    SecretServiceKeyStore,
    clear_hardware_provider,
    default_stores,
    register_hardware_provider,
    resolve_signer,
)

__all__ = [
    "CustodyError",
    "KeyStore",
    "FileKeyStore",
    "KeychainKeyStore",
    "SecretServiceKeyStore",
    "HardwareKeyStore",
    "HalbertSigner",
    "resolve_signer",
    "default_stores",
    "register_hardware_provider",
    "clear_hardware_provider",
]
