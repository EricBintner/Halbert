# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The vault's crypto: deterministic derivation, sealed files, named AAD."""
import pytest

from halbert_core.backup.encrypt import (
    check_crypto_available,
    decrypt_file,
    derive_key,
    encrypt_file,
    new_salt,
)


def test_pbkdf2_derives_deterministic_key():
    a = derive_key("correct horse", b"salt" * 4, iterations=1000)
    b = derive_key("correct horse", b"salt" * 4, iterations=1000)
    assert a == b
    assert len(a) == 32


def test_different_salt_different_key():
    a = derive_key("pw", b"aaaaaaaaaaaaaaaa", iterations=1000)
    b = derive_key("pw", b"bbbbbbbbbbbbbbbb", iterations=1000)
    assert a != b


def test_empty_passphrase_refused():
    with pytest.raises(ValueError):
        derive_key("", b"salt" * 4)


def test_aes_gcm_roundtrip():
    key = derive_key("pw", new_salt(), iterations=1000)
    ct = encrypt_file(b"the entity's autobiography", key, "databases/memories.json.enc")
    assert decrypt_file(ct, key, "databases/memories.json.enc") == \
        b"the entity's autobiography"


def test_decrypt_with_wrong_key_raises():
    a = derive_key("pw-a", new_salt(), iterations=1000)
    b = derive_key("pw-b", new_salt(), iterations=1000)
    ct = encrypt_file(b"secret", a, "f.enc")
    with pytest.raises(Exception):
        decrypt_file(ct, b, "f.enc")


def test_member_name_is_bound():
    """Filename AAD: a ciphertext sealed for one member cannot be renamed
    or swapped into another member's slot without the tag failing."""
    key = derive_key("pw", new_salt(), iterations=1000)
    ct = encrypt_file(b"payload", key, "databases/memories.json.enc")
    with pytest.raises(Exception):
        decrypt_file(ct, key, "databases/conversations.db.enc")


def test_tampered_body_fails():
    key = derive_key("pw", new_salt(), iterations=1000)
    ct = bytearray(encrypt_file(b"payload", key, "f.enc"))
    ct[-1] ^= 0xFF
    with pytest.raises(Exception):
        decrypt_file(bytes(ct), key, "f.enc")


def test_each_file_gets_a_fresh_nonce():
    key = derive_key("pw", new_salt(), iterations=1000)
    a = encrypt_file(b"same", key, "f.enc")
    b = encrypt_file(b"same", key, "f.enc")
    assert a != b  # nonce randomness makes identical plaintexts distinct


def test_check_crypto_available_true():
    assert check_crypto_available() is True
