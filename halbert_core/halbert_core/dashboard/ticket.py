# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Print a one-time URL that authenticates a browser (SEC-1).

Every dashboard route now needs a credential, and a browser cannot be handed a
header. This mints a short-lived single-use ticket from the API token and prints
the URL that redeems it for a session cookie.

    python -m halbert_core.dashboard.ticket                # open the dashboard
    python -m halbert_core.dashboard.ticket --path /voice  # open Voice Mode

It reads the token file directly rather than asking the running server, so it
works before the server is up — which is what lets ``halbert-kiosk.service``
compute its URL in an ``ExecStart`` line.

The URL is a credential for the next five minutes. Printing it is fine; pasting
it into a chat log or a ticket is not.
"""
from __future__ import annotations

import argparse
import os
import sys

from .auth import load_or_create_token, mint_ticket


def build_url(host: str, port: int, path: str = "/") -> str:
    ticket = mint_ticket(load_or_create_token())
    target = path if path.startswith("/") else f"/{path}"
    return f"http://{host}:{port}/auth/enter?ticket={ticket}&next={target}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m halbert_core.dashboard.ticket",
        description="Print a one-time URL that authenticates a browser to this Halbert.",
    )
    parser.add_argument("--host", default=os.environ.get("HALBERT_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("HALBERT_PORT", "8000")))
    parser.add_argument(
        "--path", default="/", help="Where to land after authenticating (default: /)"
    )
    args = parser.parse_args(argv)

    print(build_url(args.host, args.port, args.path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
