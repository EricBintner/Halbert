#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""P-04 — peerApi: bare /api fetches that 404 in the Tauri webview.

The seam (found 2026-09-01, 1 real red in the frontend suite): ``lib/peerApi.ts``
issued bare ``fetch("/api/peers|/api/fleet...")`` calls, which 404 in the
Tauri webview where the dashboard is not served from the origin root.

Probe (static, no pytest, no JS runtime): scan the source and assert every
``fetch(`` call routes its path through ``apiUrl(...)`` — the seam is
source-shape, so the source IS the oracle.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _env import bootstrap  # noqa: E402

bootstrap()  # keeps the probe honest about which checkout it scans

PROBE_ID = "P-04"

CHECKOUT = Path(__file__).resolve().parents[2]
PEERAPI = CHECKOUT / "halbert_core" / "halbert_core" / "dashboard" / "frontend" / "src" / "lib" / "peerApi.ts"


def main() -> int:
    if not PEERAPI.exists():
        print(f"PROBE {PROBE_ID} peerapi-bare-fetch: OBSERVED -- {PEERAPI} not present in this checkout")
        return 0
    text = PEERAPI.read_text(encoding="utf-8")
    fetches = re.findall(r"fetch\(([^;]{0,80})", text)
    bare = [f.strip() for f in fetches if re.search(r"""['"`]/api/""", f) and "apiUrl" not in f]
    routed = [f.strip() for f in fetches if "apiUrl" in f]

    if bare:
        print(f"PROBE {PROBE_ID} peerapi-bare-fetch: RED -- bare /api fetch(es): {bare}")
        return 0
    if not routed:
        print(f"PROBE {PROBE_ID} peerapi-bare-fetch: OBSERVED -- {len(fetches)} fetches, none via apiUrl")
        return 0

    print(
        f"PROBE P-04 peerapi-bare-fetch: FIXED -- all {len(routed)} fetch calls "
        "route through apiUrl(); no bare /api paths remain"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as exc:
        print(f"PROBE {PROBE_ID} peerapi-bare-fetch: HARNESS-ERROR -- {exc!r}")
        raise SystemExit(3)