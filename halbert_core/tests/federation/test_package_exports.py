# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Test: the federation package's lazy public API resolves.

Regression test for the scaffold bug found during the 2026-08-30 code
verification: ``__all__`` advertised ``PeerAuthMiddleware``, which
``peer_middleware.py`` never defined — accessing it raised ImportError.
Every advertised name must resolve on first attribute access.
"""
import halbert_core.federation as federation_pkg


class TestPackageExports:
    """Verify every name in __all__ is importable via the lazy loader."""

    def test_all_names_resolve(self):
        """Every entry in __all__ resolves to a real attribute."""
        for name in federation_pkg.__all__:
            assert getattr(federation_pkg, name, None) is not None, (
                f"federation.__all__ advertises {name!r} but it does not resolve"
            )

    def test_peer_auth_middleware_not_exported(self):
        """PeerAuthMiddleware does not exist and must not be advertised.

        peer_middleware.py defines the FastAPI dependencies
        ``require_peer_auth``/``optional_peer_auth`` and ``PeerContext`` —
        there is no middleware class, so the stale export was removed.
        """
        assert "PeerAuthMiddleware" not in federation_pkg.__all__
        assert not hasattr(federation_pkg, "PeerAuthMiddleware")

    def test_unknown_name_raises_attribute_error(self):
        """Unknown attributes raise AttributeError (lazy loader contract)."""
        try:
            federation_pkg.NotARealExport
        except AttributeError:
            pass
        else:
            raise AssertionError("expected AttributeError for unknown export")