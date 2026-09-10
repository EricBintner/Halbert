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
import re
import threading
import urllib.parse
from collections import OrderedDict
from typing import List, Optional, Pattern, Tuple

REDACTION_PLACEHOLDER = "<secret>"

#: The shortest value worth registering (A03-G6, FD-15). The origin's
#: bound, and for the origin's reason: an exact-value match on four
#: characters blanks out ordinary prose, so a short acked value is
#: protected by the PATTERN pass rather than by this one. Lowering this
#: does not buy coverage; it buys false positives that teach people to
#: ignore the placeholder.
MIN_SECRET_VARIANT_LEN = 6


class SecretVariantRegistry:
    """Bounded FIFO registry of known secret values and their encoded forms."""

    def __init__(self, max_entries: int = 512):
        self._max = max_entries
        self._variants: "OrderedDict[str, None]" = OrderedDict()
        self._sorted_cache: Optional[Tuple[str, ...]] = None
        self._pattern_cache: Optional[Pattern[str]] = None
        # A03: the registry is written from request threads (a config
        # egress ack, an MCP token resolve) and read from the turn's. The
        # OrderedDict and its caches were unguarded.
        self._lock = threading.RLock()

    @staticmethod
    def _variants_of(value: str) -> List[str]:
        """Every form this value can wear on the way out, RAW LAST.

        A03-G4: four encoders, not one. ``quote`` with its default
        ``safe='/'`` is what a URL path builder produces and was the only
        form registered; ``quote(safe="")`` is what a browser's
        ``encodeURIComponent`` produces (it percent-encodes the slash);
        ``quote_plus`` writes a space as ``+``, which is what a form
        encoder produces; and the JSON-escaped form is what a serialized
        capture holds. A secret egressed through any of the last three
        used to wear a shape the registry had never seen. Registering
        all four costs at most three extra entries per secret and covers
        every encoder that actually appears on an egress path.

        A03 bug 2: the order is load-bearing. This returned its forms
        SORTED, so insertion order was alphabetical and FIFO eviction
        could drop the RAW value while keeping a percent-encoded variant
        of it -- and the raw form is the one most likely to appear.
        Encoded forms first, raw last, so the raw form is the newest
        entry and survives eviction longest.
        """
        encoded = {
            urllib.parse.quote(value),            # URL path builder
            urllib.parse.quote(value, safe=""),   # encodeURIComponent
            urllib.parse.quote_plus(value),       # form encoding
            json.dumps(value)[1:-1],              # serialized capture
        }
        encoded.discard(value)
        forms = [f for f in sorted(encoded) if len(f) >= MIN_SECRET_VARIANT_LEN]
        if len(value) >= MIN_SECRET_VARIANT_LEN:
            forms.append(value)
        return forms

    def register(self, value: str) -> None:
        """Register a secret's exact value and its encoded variants.

        Re-registering a known form refreshes its recency (it is the same
        leak risk as a new form, not a second entry). Insertion beyond
        ``max_entries`` evicts the oldest form, FIFO.
        """
        if not value or len(value) < MIN_SECRET_VARIANT_LEN:
            return
        with self._lock:
            for form in self._variants_of(value):
                if form in self._variants:
                    self._variants.move_to_end(form)
                else:
                    self._variants[form] = None
                    if len(self._variants) > self._max:
                        self._variants.popitem(last=False)
            self._sorted_cache = None
            self._pattern_cache = None

    def _sorted_forms(self) -> Tuple[str, ...]:
        """Registered forms, longest first.

        Longest-first so a longer variant never gets partially replaced by a
        shorter prefix of itself. Cached: rebuilding a sorted view on every
        redaction call would put the cost on the hot MCP response path.
        """
        with self._lock:
            if self._sorted_cache is None:
                self._sorted_cache = tuple(
                    sorted(self._variants, key=len, reverse=True))
            return self._sorted_cache

    def _alternation(self) -> Optional[Pattern[str]]:
        """One compiled longest-first alternation over every form.

        A03 bug 3: replacement used to be a SEQUENCE of ``str.replace``
        calls, so a form could match inside the placeholder an earlier
        form had just written -- the ``<secret>`` self-collision -- and
        the output was mangled in a way that could reveal where a value
        had been. One alternation and one pass cannot collide with its
        own output: ``re.sub`` never re-scans what it has written.
        Longest-first so a shorter form never claims a prefix of a
        longer one.
        """
        with self._lock:
            if self._pattern_cache is None:
                forms = self._sorted_forms()
                if not forms:
                    return None
                self._pattern_cache = re.compile(
                    "|".join(re.escape(f) for f in forms))
            return self._pattern_cache

    def __contains__(self, text: str) -> bool:
        with self._lock:
            return text in self._variants

    def __len__(self) -> int:
        with self._lock:
            return len(self._variants)

    def redact_text(self, text: str) -> str:
        """Replace every registered form found in ``text`` with the placeholder.

        An empty registry returns the text untouched in O(1) — the common
        case on the MCP response path before anything has been egress-acked.
        """
        if not text:
            return text
        pattern = self._alternation()
        if pattern is None:
            return text
        return pattern.sub(REDACTION_PLACEHOLDER, text)


_GLOBAL: Optional[SecretVariantRegistry] = None


def get_global_registry() -> SecretVariantRegistry:
    """Process-global registry; redaction is belt-and-suspenders and must be cheap."""
    global _GLOBAL
    if _GLOBAL is None:
        _GLOBAL = SecretVariantRegistry()
    return _GLOBAL