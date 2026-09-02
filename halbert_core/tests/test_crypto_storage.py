# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Key custody for the ``SigningBackend`` seam (integrity handoff §3.1).

Custody is the whole point of these tests: a signer that verifies is easy,
a signer whose private key is not readable by every process on the box is
the actual deliverable.  So the assertions are mostly about *where the key
lives and who can read it*, not about signatures round-tripping.

The keychain tier is exercised against a real ``security`` keychain created
in ``tmp_path`` — not a mock, and not the developer's login keychain.
"""
from __future__ import annotations

import logging
import os
import shutil
import stat
import subprocess
import sys

import pytest

from haloysius.integrity import ED25519, P256, verify as verify_signature
from haloysius.seam import SigningBackend

from halbert_core.crypto.storage import (
    CustodyError,
    FileKeyStore,
    HalbertSigner,
    KeychainKeyStore,
    SecretServiceKeyStore,
    resolve_signer,
)


@pytest.fixture(autouse=True)
def _no_leaked_hardware_provider():
    """The provider seam is process-global; a failing test must not leak it."""
    from halbert_core.crypto.storage import clear_hardware_provider

    clear_hardware_provider()
    yield
    clear_hardware_provider()


# ---------------------------------------------------------------------------
# File custody -- the headless-daemon fallback, approved with conditions.
# ---------------------------------------------------------------------------


def test_file_store_writes_key_0600_in_a_0700_directory(tmp_path):
    """The two permission conditions the handoff attaches to file custody."""
    store = FileKeyStore(tmp_path / "keys")
    store.store("body", b"\x01" * 32)

    key_path = tmp_path / "keys" / "body.key"
    assert stat.S_IMODE(key_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(key_path.parent.stat().st_mode) == 0o700


def test_file_store_refuses_a_key_readable_by_others(tmp_path):
    """OpenSSH behaviour: a key group- or world-readable is not loaded."""
    store = FileKeyStore(tmp_path / "keys")
    store.store("body", b"\x02" * 32)
    key_path = tmp_path / "keys" / "body.key"
    os.chmod(key_path, 0o644)

    with pytest.raises(CustodyError) as excinfo:
        store.load("body")

    assert "body.key" in str(excinfo.value)
    assert "0644" in str(excinfo.value)


def test_file_store_round_trips_the_private_key(tmp_path):
    store = FileKeyStore(tmp_path / "keys")
    store.store("body", b"\x03" * 32)

    assert store.load("body") == b"\x03" * 32


def test_file_store_returns_none_for_an_absent_key(tmp_path):
    assert FileKeyStore(tmp_path / "keys").load("body") is None


# ---------------------------------------------------------------------------
# Keychain custody -- real `security`, isolated keychain.
# ---------------------------------------------------------------------------


@pytest.fixture
def temp_keychain(tmp_path):
    """A throwaway macOS keychain, so no test touches login.keychain."""
    if sys.platform != "darwin" or not shutil.which("security"):
        pytest.skip("macOS `security` not available")
    path = tmp_path / "halbert-test.keychain-db"
    subprocess.run(
        ["security", "create-keychain", "-p", "testpw", str(path)],
        check=True, capture_output=True,
    )
    subprocess.run(
        ["security", "unlock-keychain", "-p", "testpw", str(path)],
        check=True, capture_output=True,
    )
    yield path
    subprocess.run(["security", "delete-keychain", str(path)], capture_output=True)


def test_keychain_store_round_trips_the_private_key(temp_keychain):
    store = KeychainKeyStore(keychain=temp_keychain)

    store.store("body", b"\x04" * 32)

    assert store.load("body") == b"\x04" * 32


def test_keychain_store_overwrites_an_existing_key(temp_keychain):
    """Without -U, `security add-generic-password` fails on a duplicate."""
    store = KeychainKeyStore(keychain=temp_keychain)
    store.store("body", b"\x05" * 32)

    store.store("body", b"\x06" * 32)

    assert store.load("body") == b"\x06" * 32


def test_keychain_store_returns_none_for_an_absent_key(temp_keychain):
    assert KeychainKeyStore(keychain=temp_keychain).load("body") is None


# ---------------------------------------------------------------------------
# The signer itself.
# ---------------------------------------------------------------------------


def test_signer_satisfies_the_signing_backend_protocol(tmp_path):
    signer = resolve_signer(stores=[FileKeyStore(tmp_path / "keys")])

    assert isinstance(signer, SigningBackend)


def test_signature_verifies_against_the_did_alone(tmp_path):
    """The property the whole scheme rests on: offline verification."""
    signer = resolve_signer(stores=[FileKeyStore(tmp_path / "keys")])
    payload = b'{"kind":"tool_call"}'

    signature = signer.sign(payload)

    assert verify_signature(signer.did, payload, signature) is True


def test_signature_does_not_verify_against_a_different_body(tmp_path):
    first = resolve_signer(stores=[FileKeyStore(tmp_path / "a")])
    second = resolve_signer(stores=[FileKeyStore(tmp_path / "b")])
    payload = b"attributable"

    assert verify_signature(second.did, payload, first.sign(payload)) is False


def test_repr_never_carries_key_material(tmp_path):
    """Identities end up in log lines; key bytes must not ride along."""
    store = FileKeyStore(tmp_path / "keys")
    signer = resolve_signer(stores=[store])
    secret = store.load("body").hex()

    assert secret not in repr(signer)
    assert secret not in str(signer)


# ---------------------------------------------------------------------------
# The custody ladder.
# ---------------------------------------------------------------------------


def test_the_did_is_stable_across_processes(tmp_path):
    """A body keeps its identity; a fresh key each start would be useless."""
    store_dir = tmp_path / "keys"
    first = resolve_signer(stores=[FileKeyStore(store_dir)])

    second = resolve_signer(stores=[FileKeyStore(store_dir)])

    assert second.did == first.did


def test_the_most_preferred_available_store_wins(tmp_path, temp_keychain):
    keychain = KeychainKeyStore(keychain=temp_keychain)
    file_store = FileKeyStore(tmp_path / "keys")

    signer = resolve_signer(stores=[keychain, file_store])

    assert signer.custody == "keychain"
    assert keychain.load("body") is not None
    assert file_store.load("body") is None


def test_an_existing_key_is_reused_rather_than_regenerated(tmp_path):
    store = FileKeyStore(tmp_path / "keys")
    store.store("body", b"\x07" * 32)

    signer = resolve_signer(stores=[store])

    assert store.load("body") == b"\x07" * 32
    assert signer.did == HalbertSigner.from_private_bytes(b"\x07" * 32, ED25519, "file").did


def test_downgrading_to_file_custody_is_logged_at_warning(tmp_path, caplog):
    """§3.1: never fall back silently from keystore to file."""
    class BrokenKeystore(KeychainKeyStore):
        name = "keychain"

        def available(self) -> bool:
            return True

        def load(self, key_id):
            raise CustodyError("keychain is locked")

        def store(self, key_id, private_bytes):
            raise CustodyError("keychain is locked")

    with caplog.at_level(logging.WARNING):
        signer = resolve_signer(
            stores=[BrokenKeystore(), FileKeyStore(tmp_path / "keys")]
        )

    assert signer.custody == "file"
    warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert warnings, "a silent downgrade to file custody is the failure mode"
    assert "keychain" in caplog.text and "file" in caplog.text


def test_unavailable_stores_are_skipped_without_a_downgrade_warning(tmp_path, caplog):
    """A store that is simply not on this OS is not a downgrade."""
    with caplog.at_level(logging.WARNING):
        signer = resolve_signer(
            stores=[SecretServiceKeyStore(), FileKeyStore(tmp_path / "keys")]
        )

    if sys.platform == "darwin":
        assert signer.custody == "file"
        assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


def test_no_available_store_yields_no_signer(tmp_path):
    """The subtractive contract: no custody story, register nothing."""
    class Unavailable(FileKeyStore):
        def available(self) -> bool:
            return False

    assert resolve_signer(stores=[Unavailable(tmp_path / "keys")]) is None


# ---------------------------------------------------------------------------
# Curve selection -- P-256 exists for hardware, Ed25519 for software.
# ---------------------------------------------------------------------------


def test_software_custody_uses_ed25519(tmp_path):
    signer = resolve_signer(stores=[FileKeyStore(tmp_path / "keys")])

    assert signer.curve is ED25519
    assert signer.did.startswith("did:key:z6Mk")


def test_a_hardware_capable_store_uses_p256(tmp_path):
    """Neither Secure Enclave nor a shipping TPM does Ed25519."""
    class FakeHardware(FileKeyStore):
        name = "hardware"
        curve = P256

    signer = resolve_signer(stores=[FakeHardware(tmp_path / "keys")])

    assert signer.curve is P256
    assert signer.did.startswith("did:key:zDn")


# ---------------------------------------------------------------------------
# The hardware seam.
# ---------------------------------------------------------------------------


def test_hardware_store_is_unavailable_until_a_provider_registers():
    from halbert_core.crypto.storage import HardwareKeyStore, clear_hardware_provider

    clear_hardware_provider()

    assert HardwareKeyStore().available() is False


def test_a_registered_hardware_provider_outranks_the_keystore(tmp_path):
    from halbert_core.crypto.storage import (
        HardwareKeyStore,
        clear_hardware_provider,
        register_hardware_provider,
    )

    class FakeEnclave(FileKeyStore):
        name = "hardware"
        curve = P256

    provider = FakeEnclave(tmp_path / "enclave")
    file_store = FileKeyStore(tmp_path / "keys")
    register_hardware_provider(provider)
    try:
        signer = resolve_signer(stores=[HardwareKeyStore(), file_store])
    finally:
        clear_hardware_provider()

    assert signer.custody == "hardware"
    assert signer.curve is P256
    assert file_store.load("body") is None


def test_without_cryptography_the_body_runs_unsigned(tmp_path, monkeypatch, caplog):
    """§5: no signing story is a reported state, not a crash."""
    from haloysius.integrity import IdentityError

    import halbert_core.crypto.storage as storage

    def _no_crypto(curve):
        raise IdentityError("signing requires the optional [crypto] extra")

    monkeypatch.setattr(storage.SoftwareSigner, "generate", staticmethod(_no_crypto))

    with caplog.at_level(logging.WARNING):
        signer = resolve_signer(stores=[FileKeyStore(tmp_path / "keys")])

    assert signer is None
    assert "unsigned" in caplog.text


def test_holding_the_key_in_a_weaker_store_than_available_is_logged(
    tmp_path, temp_keychain, caplog
):
    """§3.1's rule covers this case too, and it is the likelier one.

    A body that once ran headless has its key in a ``0600`` file. It later
    runs somewhere with a keychain. Reusing the file key is right -- the DID
    *is* the identity, and regenerating would orphan it -- but continuing
    under weaker custody than the machine supports must not be silent.
    """
    file_store = FileKeyStore(tmp_path / "keys")
    file_store.store("body", b"\x08" * 32)
    keychain = KeychainKeyStore(keychain=temp_keychain)

    with caplog.at_level(logging.WARNING):
        signer = resolve_signer(stores=[keychain, file_store])

    assert signer.custody == "file", "the existing identity must be reused"
    assert "keychain" in caplog.text and "file" in caplog.text


# ---------------------------------------------------------------------------
# Adversarial pass, 2026-09-02: destroying an identity must not be quiet.
# ---------------------------------------------------------------------------


def test_a_corrupt_key_file_is_not_silently_replaced(tmp_path, caplog):
    """The DID *is* the body. Minting a new one is not error recovery.

    A truncated key file -- an interrupted write, a filesystem hiccup, a
    restore from a bad backup -- must not cause the body to quietly become
    a different body, overwriting the only copy of the old key on the way.
    That is irreversible and undoes every attribution made under the old
    identity.
    """
    store = FileKeyStore(tmp_path / "keys")
    original = resolve_signer(stores=[store])
    key_path = tmp_path / "keys" / "body.key"
    key_path.write_bytes(b"")
    os.chmod(key_path, 0o600)

    with caplog.at_level(logging.ERROR):
        signer = resolve_signer(stores=[store])

    assert signer is None, "a body with an unusable key must not invent a new one"
    assert key_path.read_bytes() == b"", "the unusable key must not be overwritten"
    assert "body.key" in caplog.text
    assert original.did not in caplog.text  # never log what the key was


def test_a_wrong_length_key_file_is_not_silently_replaced(tmp_path):
    store = FileKeyStore(tmp_path / "keys")
    resolve_signer(stores=[store])
    key_path = tmp_path / "keys" / "body.key"
    key_path.write_bytes(b"\x01" * 16)
    os.chmod(key_path, 0o600)

    assert resolve_signer(stores=[store]) is None
    assert key_path.read_bytes() == b"\x01" * 16


def test_a_corrupt_higher_store_does_not_block_a_good_lower_one(tmp_path, temp_keychain):
    """Refusing to overwrite is not the same as refusing to run.

    A broken keychain entry must not stop a body that has a perfectly good
    key in file custody -- it just must not *overwrite* the broken one.
    """
    keychain = KeychainKeyStore(keychain=temp_keychain)
    keychain.store("body", b"")  # present, unusable
    file_store = FileKeyStore(tmp_path / "keys")
    file_store.store("body", b"\x09" * 32)

    signer = resolve_signer(stores=[keychain, file_store])

    assert signer is not None
    assert signer.custody == "file"
    assert keychain.load("body") == b"", "the broken entry must be left alone"


def test_concurrent_first_starts_agree_on_one_identity(tmp_path):
    """Five processes starting at once must not mint five bodies.

    Pass 2 generates, then stores. Without a lock every racer generates its
    own key and the last write wins, so four identities are destroyed and
    four processes go on signing with keys no longer in custody. The body's
    DID would then depend on a startup race -- and per-body attribution is
    the whole point of having one.
    """
    import subprocess
    import sys
    import textwrap

    script = textwrap.dedent(
        f"""
        from halbert_core.crypto.storage import FileKeyStore, resolve_signer
        print(resolve_signer(stores=[FileKeyStore({str(tmp_path / 'keys')!r})]).did)
        """
    )
    procs = [
        subprocess.Popen([sys.executable, "-c", script],
                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        for _ in range(5)
    ]
    dids = {p.communicate()[0].strip() for p in procs}

    assert len(dids) == 1, f"{len(dids)} identities minted: {dids}"
    surviving = resolve_signer(stores=[FileKeyStore(tmp_path / "keys")])
    assert surviving.did == dids.pop(), "the key on disk is not the one handed out"


def test_concurrent_threads_agree_on_one_identity(tmp_path):
    import threading

    results = []
    threads = [
        threading.Thread(
            target=lambda: results.append(
                resolve_signer(stores=[FileKeyStore(tmp_path / "keys")]).did
            )
        )
        for _ in range(12)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(set(results)) == 1, f"{len(set(results))} identities minted"
