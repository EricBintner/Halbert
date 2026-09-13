# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Vault encryption — PBKDF2 key derivation + AES-256-GCM.

The archive carries the body's private signing key; there is no
plaintext fallback. If ``cryptography`` is absent, backup fails —
it never silently writes an unencrypted copy of the entity's identity.

- One master key per archive: PBKDF2-HMAC-SHA256(passphrase, salt,
  iterations). The salt is random per archive and lives in the
  manifest — it is a parameter, not a secret.
- A fresh random 12-byte nonce per file.
- The archive member name is bound as AEAD additional data, so a
  ciphertext cannot be renamed or swapped between members without the
  tag failing — the manifest's digests cover the plaintext, the AAD
  covers the name.
"""
from __future__ import annotations

import hashlib
import logging
import os

logger = logging.getLogger('halbert.backup.encrypt')

DEFAULT_KDF_ITERATIONS = 600_000
_NONCE_BYTES = 12
_KEY_BYTES = 32


class CryptoUnavailable(RuntimeError):
    """cryptography is not installed — there is no plaintext fallback."""


def check_crypto_available() -> bool:
    """Can we encrypt at all?"""
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # noqa: F401
        return True
    except ImportError:
        return False


def _aesgcm():
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        return AESGCM
    except ImportError as e:
        raise CryptoUnavailable(
            "cryptography is not installed — the vault cannot encrypt. "
            "Install the backup extra; the archive carries the body's "
            "private key and is never written in plaintext."
        ) from e


def derive_key(
    passphrase: str,
    salt: bytes,
    iterations: int = DEFAULT_KDF_ITERATIONS,
) -> bytes:
    """PBKDF2-HMAC-SHA256 — stdlib, no new hard dependency."""
    if not passphrase:
        raise ValueError("a backup passphrase may not be empty")
    return hashlib.pbkdf2_hmac(
        "sha256", passphrase.encode(), salt, iterations, dklen=_KEY_BYTES)


def new_salt() -> bytes:
    return os.urandom(16)


def encrypt_file(plaintext: bytes, key: bytes, member_name: str) -> bytes:
    """AES-256-GCM encrypt. Output is ``nonce || ciphertext || tag``;
    the member name is authenticated data, not encrypted data."""
    AESGCM = _aesgcm()
    nonce = os.urandom(_NONCE_BYTES)
    aad = member_name.encode()
    return nonce + AESGCM(key).encrypt(nonce, plaintext, aad)


def decrypt_file(ciphertext: bytes, key: bytes, member_name: str) -> bytes:
    """Reverse of encrypt_file — fails on a wrong key, a tampered body,
    or a member name that is not the one the ciphertext was sealed for."""
    AESGCM = _aesgcm()
    nonce, body = ciphertext[:_NONCE_BYTES], ciphertext[_NONCE_BYTES:]
    return AESGCM(key).decrypt(nonce, body, member_name.encode())
