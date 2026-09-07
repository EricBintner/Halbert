# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Exact-value secret redaction with encoded-variant coverage.

OpenClaw's registry (src/logging/secret-redaction-registry.ts) registers the raw
value plus its URL-encoded and JSON-escaped forms so percent-encoded egress and
serialized captures both redact. Bounded FIFO; values shorter than
``MIN_SECRET_VARIANT_LEN`` are ignored (redacting "ab" blanks out ordinary prose).

The registry is deliberately a *learned* layer, not a pattern one: it only ever
contains values that Halbert has observed crossing a boundary it controls (see
``config.queries.get_config_value``'s acknowledged-egress path, which feeds it).
Because redaction is exact-value, it is safe to run *after* key-based redaction
(``ingestion.redaction.redact_text``) — the two passes compose.

Hot-path cost: the registered forms are kept in a cached, length-sorted tuple
rebuilt only when the registry mutates, so ``redact_text`` on a steady-state
registry is one membership scan per form and an empty registry is an O(1)
early return.
"""
from __future__ import annotations

import json
import urllib.parse
from collections import OrderedDict
from typing import List, Optional, Tuple

REDACTION_PLACEHOLDER = "<secret>"
MIN_SECRET_VARIANT_LEN = 4


class SecretVariantRegistry:
    """Bounded FIFO registry of known secret values and their encoded forms."""

    def __init__(self, max_entries: int = 512):
        self._max = max_entries
        self._variants: "OrderedDict[str, None]" = OrderedDict()
        self._sorted_cache: Optional[Tuple[str, ...]] = None

    @staticmethod
    def _variants_of(value: str) -> List[str]:
        forms = {value, urllib.parse.quote(value), json.dumps(value)[1:-1]}
        return sorted(f for f in forms if len(f) >= MIN_SECRET_VARIANT_LEN)

    def register(self, value: str) -> None:
        """Register a secret's exact value and its encoded variants.

        Re-registering a known form refreshes its recency (it is the same
        leak risk as a new form, not a second entry). Insertion beyond
        ``max_entries`` evicts the oldest form, FIFO.
        """
        if not value or len(value) < MIN_SECRET_VARIANT_LEN:
            return
        for form in self._variants_of(value):
            if form in self._variants:
                self._variants.move_to_end(form)
            else:
                self._variants[form] = None
                if len(self._variants) > self._max:
                    self._variants.popitem(last=False)
        self._sorted_cache = None

    def _sorted_forms(self) -> Tuple[str, ...]:
        """Registered forms, longest first.

        Longest-first so a longer variant never gets partially replaced by a
        shorter prefix of itself. Cached: rebuilding a sorted view on every
        redaction call would put the cost on the hot MCP response path.
        """
        if self._sorted_cache is None:
            self._sorted_cache = tuple(sorted(self._variants, key=len, reverse=True))
        return self._sorted_cache

    def __contains__(self, text: str) -> bool:
        return text in self._variants

    def __len__(self) -> int:
        return len(self._variants)

    def redact_text(self, text: str) -> str:
        """Replace every registered form found in ``text`` with the placeholder.

        An empty registry returns the text untouched in O(1) — the common
        case on the MCP response path before anything has been egress-acked.
        """
        forms = self._sorted_forms()
        if not forms:
            return text
        for form in forms:
            if form in text:
                text = text.replace(form, REDACTION_PLACEHOLDER)
        return text


_GLOBAL: Optional[SecretVariantRegistry] = None


def get_global_registry() -> SecretVariantRegistry:
    """Process-global registry; redaction is belt-and-suspenders and must be cheap."""
    global _GLOBAL
    if _GLOBAL is None:
        _GLOBAL = SecretVariantRegistry()
    return _GLOBAL