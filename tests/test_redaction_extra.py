# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
from halbert_core.ingestion.redaction import redact_text


def test_redact_ipv6_mac_jwt_pem():
    s = (
        "v6 2001:4860:4860::8888 linklocal fe80::1ff:fe23:4567:890a "
        "mac aa:bb:cc:dd:ee:ff "
        "jwt eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.abc.def "
        "key -----BEGIN PRIVATE KEY-----\nAAAA\n-----END PRIVATE KEY-----"
    )
    r = redact_text(s)
    assert "<ip6>" in r
    assert "<mac>" in r
    assert "<jwt>" in r
    assert "<pem_block>" in r
    # Globally routable v6 goes; link-local is this host's own addressing.
    assert "2001:4860:4860::8888" not in r
    assert "fe80::1ff:fe23:4567:890a" in r
