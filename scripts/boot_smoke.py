#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Boot-gate smoke check for the Halbert stack (Phase 4.5).

Read-only verification that a live dashboard serves the agent path, the
being config, and the module registry. Prints one PASS/FAIL line per check
and exits 1 if any check fails.

Usage:
    python scripts/boot_smoke.py [--base-url http://localhost:8000]
"""

from __future__ import annotations

import argparse
import json
import logging
import socket
import sys
import urllib.error
import urllib.request

logger = logging.getLogger("halbert.boot_smoke")

AGENT_TIMEOUT_S = 30
HTTP_TIMEOUT_S = 10

# SSE event types that terminate the agent stream.
TERMINAL_EVENTS = {"response_complete", "session_ended", "error", "cancelled"}


def _get_json(url: str) -> dict:
    """GET a URL and parse the response body as JSON."""
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_S) as resp:
        return json.loads(resp.read().decode("utf-8"))


def check_health(base_url: str) -> tuple[bool, str]:
    """Check 1: server reachable, agent health endpoint reports healthy."""
    url = f"{base_url}/api/agent/health"
    try:
        data = _get_json(url)
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as e:
        return False, f"GET {url} failed: {e}"
    if data.get("status") == "healthy":
        return True, f"agent state={data.get('current_state')}"
    return False, f"agent unhealthy: {data.get('error', data)}"


def check_agent_send(base_url: str) -> tuple[bool, str]:
    """Check 2: POST /api/agent/message streams an assistant response."""
    url = f"{base_url}/api/agent/message"
    payload = json.dumps({"message": "hi"}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
    )
    got_response = False
    terminal = None
    try:
        with urllib.request.urlopen(req, timeout=AGENT_TIMEOUT_S) as resp:
            for raw_line in resp:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line.startswith("data:"):
                    continue
                try:
                    event = json.loads(line[5:].strip())
                except json.JSONDecodeError:
                    continue
                etype = event.get("type", "")
                if etype == "response_chunk":
                    got_response = True
                if etype in TERMINAL_EVENTS:
                    terminal = etype
                    break
    except socket.timeout:
        return (
            got_response,
            f"stream timed out after {AGENT_TIMEOUT_S}s"
            + (" (response chunks seen)" if got_response else " (no response)"),
        )
    except (urllib.error.URLError, OSError) as e:
        return False, f"POST {url} failed: {e}"
    if got_response:
        return True, f"assistant response received (terminal={terminal})"
    return False, f"stream ended without response chunks (terminal={terminal})"


def check_being_config(base_url: str) -> tuple[bool, str]:
    """Check 3: GET /api/settings/being returns JSON with a voice field."""
    url = f"{base_url}/api/settings/being"
    try:
        data = _get_json(url)
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as e:
        return False, f"GET {url} failed: {e}"
    voice = (data.get("config") or {}).get("voice", data.get("voice"))
    if voice:
        return True, f"voice={voice}"
    return False, f"no voice field in response: {list(data.keys())}"


def check_modules(base_url: str) -> tuple[bool, str]:
    """Check 4: GET /api/modules returns JSON containing 'vitals'."""
    url = f"{base_url}/api/modules"
    try:
        data = _get_json(url)
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as e:
        return False, f"GET {url} failed: {e}"
    names = [m.get("name") for m in data.get("modules", []) if isinstance(m, dict)]
    if "vitals" in names:
        return True, f"modules={names}"
    return False, f"'vitals' not in module list: {names}"


# A troubleshooting prompt that intake should classify as non-trivial.
# When specialist routing is enabled (models.yml), this routes to 'specialist';
# when disabled (e.g. a dev host without models.yml), it falls back to 'guide'
# but is_troubleshooting is still true — which is what we assert in that case.
_TROUBLESHOOTING_MSG = (
    "my nginx service keeps crashing with exit code 1 and the journal shows a "
    "bind error on port 80, how do I fix this?"
)


def _post_json(url: str, payload: dict, timeout: float = HTTP_TIMEOUT_S) -> dict:
    """POST JSON and parse the response body as JSON."""
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def check_intake_routing(base_url: str) -> tuple[bool, str]:
    """Check 5: POST /api/agent/intake classifies routing correctly.

    Greetings must route to the guide. A troubleshooting prompt must route to
    the specialist when specialist routing is enabled; when it is not enabled
    (dev host without models.yml), we instead assert that intake still flagged
    the message as troubleshooting (signal detection is correct even though
    model selection falls back to guide).
    """
    url = f"{base_url}/api/agent/intake"

    # 5a: greeting -> guide
    try:
        greeting = _post_json(url, {"message": "hi"}, timeout=AGENT_TIMEOUT_S)
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as e:
        return False, f"POST {url} (greeting) failed: {e}"
    if greeting.get("recommended_model") != "guide":
        return False, f"greeting routed to {greeting.get('recommended_model')!r}, expected 'guide'"
    if not greeting.get("is_greeting"):
        return False, "greeting not detected as is_greeting"

    # 5b: troubleshooting -> specialist (when enabled) or at least flagged as troubleshooting
    try:
        trouble = _post_json(url, {"message": _TROUBLESHOOTING_MSG}, timeout=AGENT_TIMEOUT_S)
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as e:
        return False, f"POST {url} (troubleshooting) failed: {e}"

    specialist_enabled = bool(trouble.get("specialist_enabled"))
    if specialist_enabled:
        if trouble.get("recommended_model") != "specialist":
            return False, (
                f"troubleshooting routed to {trouble.get('recommended_model')!r}, "
                f"expected 'specialist' (specialist_enabled=True, "
                f"complexity={trouble.get('complexity_score')})"
            )
        routing_detail = "troubleshooting->specialist"
    else:
        if not trouble.get("is_troubleshooting"):
            return False, (
                "troubleshooting not detected as is_troubleshooting "
                "(specialist disabled, so routing fell back to guide — "
                "but signal detection must still fire)"
            )
        routing_detail = (
            f"troubleshooting flagged (specialist disabled; routed to "
            f"{trouble.get('recommended_model')!r})"
        )

    return True, f"greeting->guide, {routing_detail}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Halbert boot-gate smoke check")
    parser.add_argument(
        "--base-url",
        default="http://localhost:8000",
        help="dashboard base URL (default: http://localhost:8000)",
    )
    args = parser.parse_args()
    base_url = args.base_url.rstrip("/")

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

    checks = [
        ("server reachable / agent health", check_health),
        ("agent send round-trip ('hi')", check_agent_send),
        ("being config exposes voice", check_being_config),
        ("module registry lists vitals", check_modules),
        ("intake routing (guide / specialist)", check_intake_routing),
    ]

    failures = 0
    for label, check in checks:
        try:
            ok, detail = check(base_url)
        except Exception as e:  # defensive: a check must never traceback out
            ok, detail = False, f"unexpected error: {e}"
        print(f"{'PASS' if ok else 'FAIL'}  {label} — {detail}")
        if not ok:
            failures += 1

    print(f"{len(checks) - failures}/{len(checks)} checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
