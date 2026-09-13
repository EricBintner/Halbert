# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Satellite-side pairing client — drives a remote node's ``/api/peers/*``.

The dashboard routes serve the *host* side of the handshake. This module is
the other end: the calls a satellite (or its operator tooling, or the Task 4
integration test) makes to request pairing and prove the PIN.

Transport escalation (multi-node Task 1):

1. ``request_pairing`` runs over whatever URL the caller dialed — HTTP is
   fine; the request carries no secret. The response advertises the host's
   TLS fingerprint and port when its peer listener is up.
2. ``verify_pairing`` then goes to ``https://<host>:<tls_port>`` on a
   session pinned to that fingerprint — the PIN and the issued bearer token
   never cross the wire in cleartext.
3. When the host advertises no pin, verify falls back to the dialed URL —
   the pre-TLS behavior, not a regression.

The residual (an active MITM inside the pairing window substituting its own
fingerprint) is stated in ``tls.py``'s module docstring — the approval gate
bounds it, PAKE closes it, both out of this task's scope.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse, urlunparse

logger = logging.getLogger(__name__)


def host_tls_url(base_url: str, tls_port: int) -> str:
    """The ``https://host:tls_port`` form of a dialed URL."""
    parsed = urlparse(base_url if "//" in base_url else f"//{base_url}")
    host = parsed.hostname or ""
    if not host:
        raise ValueError(f"cannot derive TLS URL from {base_url!r}")
    return urlunparse(("https", f"{host}:{tls_port}", "", "", "", ""))


def request_pairing(
    base_url: str,
    *,
    node_id: str,
    node_name: str,
    role: str = "satellite",
    capabilities: Optional[List[str]] = None,
    endpoint: Optional[str] = None,
    tls_pin: Optional[str] = None,
    session=None,
    timeout: float = 15.0,
) -> Dict[str, Any]:
    """POST ``/api/peers/pair``. Returns the PairResponse body.

    ``tls_pin`` is THIS node's cert fingerprint — sent so the host can pin
    us for its outbound calls. ``session`` lets a caller inject its own
    transport (tests, pre-pinned retries).
    """
    import requests

    http = session or requests
    resp = http.post(
        f"{base_url.rstrip('/')}/api/peers/pair",
        json={
            "node_id": node_id,
            "node_name": node_name,
            "role": role,
            "capabilities": capabilities or [],
            "endpoint": endpoint,
            "tls_pin": tls_pin,
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json()


def verify_pairing(
    base_url: str,
    *,
    request_id: str,
    pin: str,
    node_id: str,
    tls_pin: Optional[str] = None,
    tls_port: Optional[int] = None,
    session=None,
    timeout: float = 15.0,
) -> Dict[str, Any]:
    """POST ``/api/peers/verify`` — over pinned HTTPS when the host
    advertised ``tls_pin``/``tls_port`` in its pair response.

    Returns the VerifyResponse body (``token``, ``desktop_node_id``, plus
    the host's ``tls_pin``/``tls_port`` again for convenience).
    """
    import requests

    from .tls import make_pinned_session

    http = session
    url = base_url
    if http is None and tls_pin and tls_port:
        url = host_tls_url(base_url, tls_port)
        http = make_pinned_session(tls_pin)
        logger.info("verifying pairing over pinned TLS at %s", url)
    elif http is None:
        http = requests
        logger.warning(
            "host advertised no TLS pin — verify (PIN + token) travels "
            "in cleartext to %s", url,
        )
    resp = http.post(
        f"{url.rstrip('/')}/api/peers/verify",
        json={"request_id": request_id, "pin": pin, "node_id": node_id},
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json()


def pair_and_verify(
    base_url: str,
    *,
    node_id: str,
    node_name: str,
    pin: str,
    role: str = "satellite",
    capabilities: Optional[List[str]] = None,
    endpoint: Optional[str] = None,
    timeout: float = 15.0,
) -> Dict[str, Any]:
    """The whole handshake in one call — for scripted flows and tests.

    The operator has already approved the request on the host and supplies
    the PIN. This node's own cert fingerprint is advertised when it has
    one (its TLS listener need not be running for the pin to be valid —
    the host pins it for calls it makes back to us).
    """
    from .tls import node_cert_fingerprint

    own_pin = node_cert_fingerprint()
    pair = request_pairing(
        base_url,
        node_id=node_id,
        node_name=node_name,
        role=role,
        capabilities=capabilities,
        endpoint=endpoint,
        tls_pin=own_pin,
        timeout=timeout,
    )
    verify = verify_pairing(
        base_url,
        request_id=pair["request_id"],
        pin=pin,
        node_id=node_id,
        tls_pin=pair.get("tls_pin"),
        tls_port=pair.get("tls_port"),
        timeout=timeout,
    )
    return {
        "token": verify["token"],
        "host_node_id": verify["desktop_node_id"],
        "host_tls_pin": verify.get("tls_pin") or pair.get("tls_pin"),
        "host_tls_port": verify.get("tls_port") or pair.get("tls_port"),
        "own_tls_pin": own_pin,
    }
