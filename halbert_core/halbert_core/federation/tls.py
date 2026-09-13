# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Self-signed TLS for inter-node transport (Task 1 of the multi-node dispatch).

Peer traffic — compute offload, the conversation mesh, pairing — used to ride
cleartext HTTP with a bearer token. On a compromised home LAN that token, the
4-digit pairing PIN, and every conversation payload crossed the wire readable.
This module replaces that with per-node self-signed certificates and SHA-256
fingerprint pinning:

- Every node owns one long-lived certificate at
  ``<state_dir>/peer-tls/{node.crt,node.key}``. It is a transport identity
  only — deliberately NOT the ``body.key`` Ed25519 key that signs the audit
  chain. Rotating or leaking the transport cert must not implicate the
  audit identity, and vice versa.
- Peers pin the certificate by SHA-256 fingerprint (``PeerCredential.tls_pin``)
  rather than trusting a CA. There is no CA: a 2-3 node cluster does not need
  one, and a CA the size of the thing it protects is how small deployments
  end up with a signing key on a laptop.
- The bearer token stays. TLS protects the channel; the token still carries
  the authorization. Losing one does not open the other.
- A dedicated listener serves the peer-facing routes over HTTPS on
  ``HALBERT_PEER_TLS_PORT`` (default 8001, bound to ``HALBERT_PEER_TLS_HOST``,
  default ``0.0.0.0`` — peers are by definition off-host). The loopback
  frontend listener on ``HALBERT_PORT`` is untouched.

Residual risk, stated plainly: the satellite pins the fingerprint it receives
in the pairing response, over whichever channel carried that response. An
active MITM inside the pairing window could substitute its own fingerprint —
the same window the PIN + local-approval gate exists for. The approve screen
carries the fingerprints so an operator CAN compare out of band, and the
PAKE/key-exchange upgrade that closes the window entirely is deferred
deliberately (dispatch AD-1).

``cryptography`` is an optional import: certificate *generation* needs it,
but fingerprinting a PEM and building a pinned session do not. When it is
absent the listener simply does not start and pairing advertises no pin —
HTTP transport still works, loudly logged.
"""
from __future__ import annotations

import hashlib
import logging
import os
import socket
import ssl
import threading
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

DEFAULT_PEER_TLS_PORT = 8001

_ENV_TLS_ENABLE = "HALBERT_PEER_TLS"
_ENV_TLS_PORT = "HALBERT_PEER_TLS_PORT"
_ENV_TLS_HOST = "HALBERT_PEER_TLS_HOST"


class TLSUnavailable(RuntimeError):
    """The TLS layer cannot operate — typically ``cryptography`` not installed."""


# ---------------------------------------------------------------------------
# Identity and paths
# ---------------------------------------------------------------------------

def local_node_id() -> str:
    """This node's federation identity — the same formula the pairing and
    mDNS modules use, kept in one place so the cert CN matches what peers
    record."""
    return os.environ.get("HALBERT_PERSONA_ID", "halbert") + "-" + socket.gethostname()


def peer_tls_dir() -> Path:
    """``<state_dir>/peer-tls`` — created ``0700``; the private key lives here."""
    from ..utils.paths import state_subdir

    p = Path(state_subdir("peer-tls"))
    try:
        os.chmod(p, 0o700)
    except OSError:
        pass
    return p


def peer_tls_port() -> int:
    return int(os.environ.get(_ENV_TLS_PORT, str(DEFAULT_PEER_TLS_PORT)))


def peer_tls_host() -> str:
    return os.environ.get(_ENV_TLS_HOST, "0.0.0.0")


def tls_listener_enabled() -> bool:
    """Kill switch: ``HALBERT_PEER_TLS=0`` keeps everything on HTTP."""
    return os.environ.get(_ENV_TLS_ENABLE, "1").strip().lower() not in ("0", "false", "off", "no")


def _cert_paths() -> Tuple[Path, Path]:
    d = peer_tls_dir()
    return d / "node.crt", d / "node.key"


# ---------------------------------------------------------------------------
# Certificate generation (needs the optional ``cryptography`` import)
# ---------------------------------------------------------------------------

def ensure_node_cert(node_id: Optional[str] = None) -> Tuple[Path, Path]:
    """Return ``(cert_path, key_path)``, generating a self-signed cert on
    first call.

    Ed25519, CN=<node_id>, SAN carries the node id and hostname, 10-year
    validity — home nodes outlive CAs and a certificate expiring on a shelf
    node is a failure mode, not a feature. Idempotent: an existing pair is
    returned untouched, so the fingerprint a peer pinned stays valid.

    Raises ``TLSUnavailable`` when ``cryptography`` is not installed — the
    caller (listener startup) logs and degrades to HTTP rather than dying.
    """
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ed25519
        from cryptography.x509.oid import NameOID
    except ImportError as e:
        raise TLSUnavailable(
            "cryptography is not installed — cannot generate a node TLS "
            "certificate. Peer transport stays on HTTP. Install the "
            "`cryptography` package or drop a cert/key pair into "
            f"{peer_tls_dir()} to enable TLS."
        ) from e

    cert_path, key_path = _cert_paths()
    if cert_path.exists() and key_path.exists():
        return cert_path, key_path

    node_id = node_id or local_node_id()
    key = ed25519.Ed25519PrivateKey.generate()

    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, node_id)])
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=3650))
        .add_extension(
            x509.SubjectAlternativeName(
                [x509.DNSName(node_id), x509.DNSName(socket.gethostname())]
            ),
            critical=False,
        )
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .sign(key, algorithm=None)
    )

    # Key first, written with restrictive perms from the start — there is no
    # window where the private key is world-readable.
    fd = os.open(str(key_path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(
            fd,
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            ),
        )
    finally:
        os.close(fd)
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    logger.info("generated self-signed peer TLS certificate for %s at %s", node_id, cert_path)
    return cert_path, key_path


# ---------------------------------------------------------------------------
# Fingerprints — stdlib only, no ``cryptography`` needed
# ---------------------------------------------------------------------------

def cert_fingerprint(cert_path) -> str:
    """``sha256:<hex>`` of the PEM certificate at ``cert_path``."""
    pem = Path(cert_path).read_text(encoding="utf-8")
    der = ssl.PEM_cert_to_DER_cert(pem)
    return "sha256:" + hashlib.sha256(der).hexdigest()


def fingerprint_of_pem(pem: str) -> str:
    """``sha256:<hex>`` of a PEM certificate string."""
    return "sha256:" + hashlib.sha256(ssl.PEM_cert_to_DER_cert(pem)).hexdigest()


def node_cert_fingerprint() -> Optional[str]:
    """This node's fingerprint when a cert exists, else None."""
    cert_path, key_path = _cert_paths()
    if not (cert_path.exists() and key_path.exists()):
        return None
    try:
        return cert_fingerprint(cert_path)
    except Exception as e:
        logger.warning("could not fingerprint %s: %s", cert_path, e)
        return None


def _bare_fingerprint(fingerprint: str) -> str:
    """``sha256:<hex>`` or bare hex → the bare hex urllib3 wants."""
    fp = fingerprint.strip().lower()
    return fp.split(":", 1)[1] if fp.startswith("sha256:") else fp.replace(":", "")


# ---------------------------------------------------------------------------
# Client side — a requests.Session pinned to one certificate
# ---------------------------------------------------------------------------

def make_pinned_session(fingerprint: str):
    """A ``requests.Session`` that accepts exactly one server certificate.

    ``cert_reqs=CERT_NONE`` skips CA validation (the peer cert is self-signed
    and would never chain); ``assert_fingerprint`` then checks the peer's
    certificate bytes against the pin — the certificate IS the identity, so
    hostname checking is disabled too (the cert's CN is a node id, not the
    address it happens to be dialed at).
    """
    import requests
    from requests.adapters import HTTPAdapter

    bare = _bare_fingerprint(fingerprint)

    class _FingerprintAdapter(HTTPAdapter):
        def init_poolmanager(self, connections, maxsize, block=False, **pool_kwargs):
            pool_kwargs["assert_fingerprint"] = bare
            pool_kwargs["cert_reqs"] = "CERT_NONE"
            pool_kwargs["assert_hostname"] = False
            return super().init_poolmanager(connections, maxsize, block, **pool_kwargs)

        def proxy_manager_for(self, proxy, **proxy_kwargs):
            proxy_kwargs["assert_fingerprint"] = bare
            proxy_kwargs["cert_reqs"] = "CERT_NONE"
            proxy_kwargs["assert_hostname"] = False
            return super().proxy_manager_for(proxy, **proxy_kwargs)

        def cert_verify(self, conn, url, verify, cert):
            # The base adapter overrides the pool's cert_reqs to
            # CERT_REQUIRED whenever session.verify is truthy — which would
            # break pinning against a self-signed cert. The pin IS the
            # verification here, so the pool's settings stand.
            pass

    session = requests.Session()
    session.verify = False  # silence the CA path; the pin does the checking
    session.mount("https://", _FingerprintAdapter())
    return session


# ---------------------------------------------------------------------------
# Server side — the dedicated peer-facing listener
# ---------------------------------------------------------------------------

def make_server_ssl_context(cert_path, key_path) -> ssl.SSLContext:
    """TLS context for the peer listener.

    ``verify_mode=CERT_NONE``: peer clients authenticate with the bearer
    token, not a client certificate — mutual TLS is the deferred second
    phase, not this one.
    """
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.load_cert_chain(str(cert_path), str(key_path))
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def build_peer_app():
    """The app the TLS listener serves: the peer-facing routers only.

    Serving the full dashboard app on a second port would re-run every
    startup hook (migrations, watchers) and put owner-only routes on the
    LAN. This mounts exactly the surface a peer needs — pairing, the
    conversation mesh, compute offload — each of which carries its own
    per-route credential checks (SELF_AUTHENTICATING, finding F-A/F-E).
    """
    from fastapi import FastAPI

    from ..dashboard.routes import conversations, peers
    from . import compute_endpoint

    app = FastAPI(title="Halbert Peer", docs_url=None, redoc_url=None, openapi_url=None)
    app.include_router(peers.router)
    app.include_router(conversations.router, prefix="/api/conversations")
    app.include_router(compute_endpoint.router)
    return app


_peer_listener_lock = threading.Lock()
_peer_listener = None  # (fingerprint, port, uvicorn.Server, asyncio.Task)


def peer_tls_advertisement() -> Tuple[Optional[str], Optional[int]]:
    """``(fingerprint, port)`` to advertise in pairing, or ``(None, None)``.

    Advertised only when the listener is actually up — a pin for a port
    nothing serves would send every client to a dead endpoint.
    """
    with _peer_listener_lock:
        if _peer_listener is None:
            return None, None
        return _peer_listener[0], _peer_listener[1]


async def start_peer_tls_listener() -> bool:
    """Start the HTTPS peer listener on this event loop. True on success.

    Scheduled from the main app's startup event. Degrades gracefully:
    disabled by env, missing ``cryptography``, or a bind failure all log a
    warning and return False — the node still works, just on HTTP.
    """
    global _peer_listener
    if not tls_listener_enabled():
        logger.info("peer TLS listener disabled by %s", _ENV_TLS_ENABLE)
        return False
    try:
        cert_path, key_path = ensure_node_cert()
    except TLSUnavailable as e:
        logger.warning("%s", e)
        return False

    import asyncio
    import contextlib

    import uvicorn

    port = peer_tls_port()
    host = peer_tls_host()

    class _PeerServer(uvicorn.Server):
        @contextlib.contextmanager
        def capture_signals(self):
            # The main uvicorn owns the signal handlers; stealing them here
            # would break Ctrl-C/shutdown of the primary listener.
            yield

    config = uvicorn.Config(
        build_peer_app(),
        host=host,
        port=port,
        ssl_certfile=str(cert_path),
        ssl_keyfile=str(key_path),
        log_level="warning",
        access_log=False,
    )
    server = _PeerServer(config)
    try:
        # Mirror Server._serve()'s prelude: load the config (builds the SSL
        # context) and create the lifespan object startup() expects.
        if not config.loaded:
            config.load()
        server.lifespan = config.lifespan_class(config)
        await server.startup()
    except SystemExit:
        # Lifespan startup failure exits the process in _serve(); here it
        # must only mean the peer listener didn't come up.
        logger.warning("peer TLS listener aborted during startup on %s:%s", host, port)
        return False
    except Exception as e:
        logger.warning("peer TLS listener failed to bind %s:%s — %s", host, port, e)
        return False
    task = asyncio.create_task(server.main_loop())
    fingerprint = cert_fingerprint(cert_path)
    with _peer_listener_lock:
        _peer_listener = (fingerprint, port, server, task)
    logger.info("peer TLS listener on %s:%s (fingerprint %s)", host, port, fingerprint)
    return True


async def stop_peer_tls_listener() -> None:
    """Shut the peer listener down (called from the app's shutdown event)."""
    global _peer_listener
    with _peer_listener_lock:
        listener, _peer_listener = _peer_listener, None
    if listener is None:
        return
    _, _, server, task = listener
    server.should_exit = True
    try:
        await task
    except Exception:
        pass
    try:
        await server.shutdown()
    except Exception:
        pass
