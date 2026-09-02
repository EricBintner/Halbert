# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Key custody: where this body's private key lives, and how it signs.

Implements the ``haloysius.seam.SigningBackend`` protocol for Halbert
(integrity handoff §3.1).  Haloysius owns the record format and the
signature algorithm; custody is OS-specific and therefore ours.

The ladder, in the handoff's order of preference:

1. **Hardware** -- Secure Enclave (macOS) or TPM (Linux).  Both do
   **P-256 and nothing else**, which is why the curve is pluggable at all.
   No provider ships yet; :func:`register_hardware_provider` is the seam a
   platform backend registers through, and until one does,
   :class:`HardwareKeyStore` reports itself unavailable and the ladder
   moves on.
2. **OS keystore** -- macOS Keychain via ``security``, Linux Secret
   Service via ``secret-tool``.  Both are driven as subprocesses rather
   than through a binding, so neither adds a dependency.
3. **``0600`` file** for headless daemons.  Approved with conditions, and
   the conditions are enforced here: the parent directory is ``0700``, a
   key whose permissions are looser than ``0600`` is *refused* rather than
   loaded (OpenSSH's behaviour), and a fall back to this tier from a
   keystore that was available but failed is logged at WARNING -- a silent
   downgrade would quietly weaken custody without anyone noticing.

Nothing here ever logs, serializes or transmits private key bytes.
"""
from __future__ import annotations

import logging
import os
import shutil
import stat
import subprocess
import sys
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, List, Optional

try:  # POSIX only; used to keep two starts from minting two identities
    import fcntl
except ImportError:  # pragma: no cover - Windows
    fcntl = None  # type: ignore[assignment]

from haloysius.integrity import (
    ED25519,
    Curve,
    IdentityError,
    SoftwareSigner,
    verify as verify_signature,
)

from ..utils.paths import state_subdir

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

log = logging.getLogger(__name__)

#: Default identifier for this body's signing key.
DEFAULT_KEY_ID = "body"

#: Service name under which OS keystores file Halbert's secrets.
KEYCHAIN_SERVICE = "halbert-identity"


class CustodyError(RuntimeError):
    """A key could not be stored, loaded, or was refused as unsafe."""


# ---------------------------------------------------------------------------
# The store protocol.
# ---------------------------------------------------------------------------


class KeyStore:
    """One tier of the custody ladder.

    Subclasses hold raw private key bytes and say nothing about signing --
    the split matters because ``SoftwareSigner`` can be reconstructed from
    bytes, while a future hardware key never leaves its chip and will
    instead supply its own signer.
    """

    #: Short name used in logs and in ``HalbertSigner.custody``.
    name: str = "abstract"

    #: The curve keys in this store are generated on.
    curve: Curve = ED25519

    def available(self) -> bool:
        """Whether this tier can be used on this machine at all."""
        raise NotImplementedError

    def load(self, key_id: str) -> Optional[bytes]:
        """Return the stored private key, or ``None`` if there is none.

        Raises:
            CustodyError: the store exists but could not be read, or holds
                a key that is not safe to use.
        """
        raise NotImplementedError

    def store(self, key_id: str, private_bytes: bytes) -> None:
        """Persist a private key. Never log the argument."""
        raise NotImplementedError

    def describe(self, key_id: str) -> str:
        """Where a person should go to look at this key.

        Used in errors: "the key cannot be used" is only actionable if it
        says *which* key. Never include key material.
        """
        return f"{self.name} store entry {key_id!r}"


# ---------------------------------------------------------------------------
# Tier 3 -- 0600 file.
# ---------------------------------------------------------------------------


class FileKeyStore(KeyStore):
    """A ``0600`` key file in a ``0700`` directory.

    The fallback for headless daemons with no keystore and no hardware.
    """

    name = "file"
    curve = ED25519

    def __init__(self, directory: Optional[Any] = None):
        self._directory = Path(directory) if directory is not None else None

    @property
    def directory(self) -> Path:
        if self._directory is None:
            self._directory = Path(state_subdir("keys"))
        return self._directory

    def _path(self, key_id: str) -> Path:
        return self.directory / f"{key_id}.key"

    def describe(self, key_id: str) -> str:
        return str(self._path(key_id))

    def available(self) -> bool:
        return True

    def load(self, key_id: str) -> Optional[bytes]:
        path = self._path(key_id)
        try:
            mode = stat.S_IMODE(path.stat().st_mode)
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise CustodyError(f"cannot stat {path}: {exc}") from exc
        if mode & 0o077:
            raise CustodyError(
                f"refusing to load {path}: permissions are 0{mode:o}, which is "
                f"more permissive than 0600 -- other users on this machine can "
                f"read this body's private key. Run: chmod 600 {path}"
            )
        try:
            return path.read_bytes()
        except OSError as exc:
            raise CustodyError(f"cannot read {path}: {exc}") from exc

    def store(self, key_id: str, private_bytes: bytes) -> None:
        directory = self.directory
        try:
            directory.mkdir(parents=True, exist_ok=True)
            os.chmod(directory, 0o700)
            path = self._path(key_id)
            # Create with 0600 from the outset: writing then chmod-ing
            # leaves a window in which the key is world-readable.
            handle = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            try:
                os.write(handle, private_bytes)
            finally:
                os.close(handle)
            os.chmod(path, 0o600)
        except OSError as exc:
            raise CustodyError(f"cannot write key to {directory}: {exc}") from exc


# ---------------------------------------------------------------------------
# Tier 2 -- OS keystores.
# ---------------------------------------------------------------------------


def _run(argv: List[str], stdin: Optional[bytes] = None) -> subprocess.CompletedProcess:
    return subprocess.run(argv, input=stdin, capture_output=True)


class KeychainKeyStore(KeyStore):
    """macOS Keychain, driven through the ``security`` binary.

    ``keychain`` names a specific keychain file; the default is the
    user's search list, which is what a real install wants.  Tests pass a
    throwaway keychain so they never touch ``login.keychain``.
    """

    name = "keychain"
    curve = ED25519

    def __init__(self, keychain: Optional[Any] = None, service: str = KEYCHAIN_SERVICE):
        self.keychain = Path(keychain) if keychain is not None else None
        self.service = service

    def _suffix(self) -> List[str]:
        return [str(self.keychain)] if self.keychain else []

    def available(self) -> bool:
        return sys.platform == "darwin" and shutil.which("security") is not None

    def load(self, key_id: str) -> Optional[bytes]:
        result = _run(
            ["security", "find-generic-password", "-s", self.service,
             "-a", key_id, "-w"] + self._suffix()
        )
        if result.returncode != 0:
            # 44 is errSecItemNotFound -- an absent key, not a failure.
            if result.returncode == 44:
                return None
            raise CustodyError(
                f"keychain lookup failed: {result.stderr.decode(errors='replace').strip()}"
            )
        try:
            return bytes.fromhex(result.stdout.decode().strip())
        except ValueError as exc:
            raise CustodyError(f"keychain holds a malformed key for {key_id!r}") from exc

    def store(self, key_id: str, private_bytes: bytes) -> None:
        # -U updates in place; without it `add-generic-password` fails on
        # a duplicate item rather than replacing it.
        result = _run(
            ["security", "add-generic-password", "-U", "-s", self.service,
             "-a", key_id, "-w", private_bytes.hex(),
             "-D", "Halbert signing key",
             "-j", "Private key for this body's did:key identity"] + self._suffix()
        )
        if result.returncode != 0:
            raise CustodyError(
                f"keychain store failed: {result.stderr.decode(errors='replace').strip()}"
            )


class SecretServiceKeyStore(KeyStore):
    """Linux Secret Service (GNOME Keyring, KWallet) via ``secret-tool``."""

    name = "secret-service"
    curve = ED25519

    def __init__(self, service: str = KEYCHAIN_SERVICE):
        self.service = service

    def available(self) -> bool:
        if sys.platform.startswith("linux") and shutil.which("secret-tool"):
            # secret-tool needs a session bus; a headless daemon has none,
            # and probing here is what routes it to file custody instead.
            return bool(os.environ.get("DBUS_SESSION_BUS_ADDRESS"))
        return False

    def load(self, key_id: str) -> Optional[bytes]:
        result = _run(
            ["secret-tool", "lookup", "service", self.service, "account", key_id]
        )
        if result.returncode != 0:
            if not result.stderr.strip():
                return None  # not found
            raise CustodyError(
                f"secret-service lookup failed: "
                f"{result.stderr.decode(errors='replace').strip()}"
            )
        raw = result.stdout.decode().strip()
        if not raw:
            return None
        try:
            return bytes.fromhex(raw)
        except ValueError as exc:
            raise CustodyError(
                f"secret-service holds a malformed key for {key_id!r}"
            ) from exc

    def store(self, key_id: str, private_bytes: bytes) -> None:
        result = _run(
            ["secret-tool", "store", "--label", f"Halbert signing key ({key_id})",
             "service", self.service, "account", key_id],
            stdin=private_bytes.hex().encode(),
        )
        if result.returncode != 0:
            raise CustodyError(
                f"secret-service store failed: "
                f"{result.stderr.decode(errors='replace').strip()}"
            )


# ---------------------------------------------------------------------------
# Tier 1 -- hardware. A seam, not an implementation.
# ---------------------------------------------------------------------------

_hardware_provider: Optional[KeyStore] = None


def register_hardware_provider(provider: KeyStore) -> None:
    """Install a Secure Enclave / TPM backed store at the top of the ladder.

    A real provider generates a key that never leaves the chip, so it will
    usually supply its own signer rather than raw bytes; the seam is kept
    deliberately narrow until one exists to shape it.  It must use
    :data:`~haloysius.integrity.P256` -- neither Secure Enclave nor any
    shipping TPM supports Ed25519.
    """
    global _hardware_provider
    _hardware_provider = provider


def clear_hardware_provider() -> None:
    """Remove any registered hardware provider (tests, and teardown)."""
    global _hardware_provider
    _hardware_provider = None


class HardwareKeyStore(KeyStore):
    """Delegates to a registered hardware provider, if there is one.

    Unregistered it is simply unavailable, and the ladder falls through to
    the OS keystore *without* a downgrade warning: no hardware backend on
    this machine is a fact about the machine, not a weakening of custody.
    """

    name = "hardware"

    @property
    def curve(self) -> Curve:  # type: ignore[override]
        return _hardware_provider.curve if _hardware_provider else ED25519

    def available(self) -> bool:
        return _hardware_provider is not None and _hardware_provider.available()

    def load(self, key_id: str) -> Optional[bytes]:
        if _hardware_provider is None:
            return None
        return _hardware_provider.load(key_id)

    def store(self, key_id: str, private_bytes: bytes) -> None:
        if _hardware_provider is None:
            raise CustodyError("no hardware provider registered")
        _hardware_provider.store(key_id, private_bytes)


# ---------------------------------------------------------------------------
# The signer.
# ---------------------------------------------------------------------------


class HalbertSigner:
    """A ``SigningBackend`` whose key came out of a named custody tier.

    Thin over :class:`~haloysius.integrity.SoftwareSigner`; what it adds is
    :attr:`custody`, so a caller (and ``halbert audit-verify``) can say
    *where* the key that signed a record is kept rather than only that a
    signature checked out.
    """

    __slots__ = ("_signer", "_custody")

    def __init__(self, signer: SoftwareSigner, custody: str):
        self._signer = signer
        self._custody = custody

    @classmethod
    def from_private_bytes(
        cls, private_bytes: bytes, curve: Curve, custody: str
    ) -> "HalbertSigner":
        return cls(SoftwareSigner.from_private_bytes(private_bytes, curve), custody)

    @classmethod
    def generate(cls, curve: Curve, custody: str) -> "HalbertSigner":
        return cls(SoftwareSigner.generate(curve), custody)

    @property
    def did(self) -> str:
        """This body's ``did:key``, embedded in every record it authors."""
        return self._signer.did

    @property
    def curve(self) -> Curve:
        return self._signer.curve

    @property
    def custody(self) -> str:
        """Which tier holds the private key: hardware, keychain, ... file."""
        return self._custody

    def private_bytes(self) -> bytes:
        """Raw private key. Only a :class:`KeyStore` should call this."""
        return self._signer.private_bytes()

    def sign(self, payload: bytes) -> bytes:
        return self._signer.sign(payload)

    def verify(self, did: str, payload: bytes, signature: bytes) -> bool:
        """Verify against *any* DID, not only this body's."""
        return verify_signature(did, payload, signature)

    def __repr__(self) -> str:
        return (
            f"HalbertSigner(did={self.did!r}, custody={self._custody!r}, "
            f"curve={self.curve.name!r})"
        )

    __str__ = __repr__


# ---------------------------------------------------------------------------
# The ladder.
# ---------------------------------------------------------------------------


def default_stores() -> List[KeyStore]:
    """The custody ladder in the handoff's order of preference."""
    return [
        HardwareKeyStore(),
        KeychainKeyStore(),
        SecretServiceKeyStore(),
        FileKeyStore(),
    ]


#: Serializes identity resolution within one process; the file lock below
#: covers separate processes.
_local_custody_lock = threading.Lock()

#: Lock file guarding "find or create this body's key".
CUSTODY_LOCK_FILE = ".custody.lock"


def _lock_directory(candidates: List[KeyStore]) -> Path:
    """Where to put the custody lock.

    The first file-backed tier in the ladder, so a test driving a temporary
    store locks inside that store rather than in the developer's real state
    directory. Falls back to the default key directory when the ladder is
    entirely keystore- or hardware-backed.
    """
    for store in candidates:
        if isinstance(store, FileKeyStore):
            return store.directory
    return Path(state_subdir("keys"))


@contextmanager
def _custody_lock(candidates: List[KeyStore]):
    """Hold "find or create the key" as one operation.

    Without this, concurrent first starts each generate a key and the last
    write wins: five racing processes mint five identities, destroy four
    keys, and four of them go on signing with a key no longer in custody.
    A body whose DID depends on a startup race cannot be attributed to,
    which is the only reason it has a DID.
    """
    with _local_custody_lock:
        if fcntl is None:
            yield
            return
        try:
            directory = _lock_directory(candidates)
            directory.mkdir(parents=True, exist_ok=True)
            os.chmod(directory, 0o700)
            handle = os.open(
                str(directory / CUSTODY_LOCK_FILE), os.O_RDWR | os.O_CREAT, 0o600
            )
        except OSError as exc:
            log.debug("custody lock unavailable (%s); resolving unlocked", exc)
            yield
            return
        try:
            fcntl.flock(handle, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)
        finally:
            os.close(handle)


def resolve_signer(
    key_id: str = DEFAULT_KEY_ID,
    stores: Optional[List[KeyStore]] = None,
) -> Optional[HalbertSigner]:
    """Find or create this body's signing key, best custody first.

    Walks the ladder once: the first available store that already holds a
    key wins, and if none does, the key is generated in the most-preferred
    available store.  Landing on a lower tier because a higher one *failed*
    is logged at WARNING; landing there because the higher one is not on
    this machine is not.

    Returns ``None`` when there is no custody story at all -- no available
    store, or no ``cryptography`` to sign with.  That is not an error: an
    unsigned log still appends and still verifies, and reports ``signed:
    0``.  Signing a record is worth less than being honest about not
    having signed it.
    """
    candidates = [s for s in (stores if stores is not None else default_stores())
                  if _is_available(s)]
    if not candidates:
        log.info("no key custody available on this machine; running unsigned")
        return None

    with _custody_lock(candidates):
        return _resolve_locked(key_id, candidates)


def _resolve_locked(
    key_id: str, candidates: List[KeyStore]
) -> Optional[HalbertSigner]:
    """The body of :func:`resolve_signer`, run under the custody lock."""
    preferred = candidates[0]
    failures: List[str] = []
    # Stores holding material we could not read. Never written to below:
    # generating over them would destroy an identity, irreversibly.
    unusable: List[KeyStore] = []

    # Pass 1 -- an existing key anywhere on the ladder.
    for store in candidates:
        try:
            private_bytes = store.load(key_id)
        except CustodyError as exc:
            failures.append(f"{store.name}: {exc}")
            unusable.append(store)
            continue
        if private_bytes is None:
            continue
        try:
            signer = HalbertSigner.from_private_bytes(
                private_bytes, store.curve, store.name
            )
        except Exception as exc:
            failures.append(f"{store.describe(key_id)}: {exc}")
            unusable.append(store)
            continue
        _warn_on_downgrade(store, preferred, failures)
        return signer

    # Pass 2 -- no usable key; make one, but never on top of one we could
    # not read. The DID *is* the body: replacing a key that merely failed to
    # load turns this into a different body and overwrites the only copy of
    # the old key, undoing every attribution made under it. A truncated file
    # or a locked keystore is a thing for a person to look at, not something
    # to recover from by inventing a new identity.
    writable = [s for s in candidates if s not in unusable]
    if not writable:
        log.error(
            "this body holds a signing key that cannot be used, and no other "
            "custody is available: %s. Refusing to generate a new identity, "
            "because that would overwrite the existing key and change who "
            "this body is. Running unsigned until the key is repaired or "
            "removed deliberately.",
            "; ".join(failures),
        )
        return None

    for store in writable:
        try:
            signer = HalbertSigner.generate(store.curve, store.name)
        except IdentityError as exc:
            # No `cryptography`. Every tier will fail the same way, so stop.
            log.warning("cannot generate a signing key, running unsigned: %s", exc)
            return None
        try:
            store.store(key_id, signer.private_bytes())
        except CustodyError as exc:
            failures.append(f"{store.name}: {exc}")
            continue
        _warn_on_downgrade(store, preferred, failures)
        log.info(
            "generated this body's identity %s under %s custody",
            signer.did, store.name,
        )
        return signer

    log.warning(
        "every key store failed; running unsigned. Tried: %s", "; ".join(failures)
    )
    return None


def _is_available(store: KeyStore) -> bool:
    try:
        return store.available()
    except Exception as exc:  # a broken probe must not take the process down
        log.warning("key store %s failed its availability probe: %s", store.name, exc)
        return False


def _warn_on_downgrade(
    chosen: KeyStore, preferred: KeyStore, failures: List[str]
) -> None:
    """Say out loud when custody is weaker than this machine can support.

    §3.1: never fall back silently from keystore to file. Two ways that
    happens, and both warn -- the second is the likelier one in practice: a
    body that once ran headless keeps its ``0600`` key file after moving to
    a machine with a keystore. Reusing that key is correct, since the DID
    *is* the identity and regenerating would orphan it, but continuing under
    weaker custody than the machine supports is not something to discover by
    reading the source.
    """
    if chosen is preferred:
        return
    if failures:
        log.warning(
            "key custody downgraded from %s to %s -- %s. The signing key is "
            "now held with weaker protection than this machine supports.",
            preferred.name, chosen.name, "; ".join(failures),
        )
    else:
        log.warning(
            "this body's signing key is held under %s custody, but %s is "
            "available on this machine and is stronger. The key was left "
            "where it is because moving it is not possible without changing "
            "the body's identity.",
            chosen.name, preferred.name,
        )
