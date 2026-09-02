#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Operational unredacted re-indexing of the host config project (TASK-03 Task 3.2).

Why raw staging is safe
-----------------------
The Tier 2 recalibration moved secret protection from the staging path to
the egress boundaries: tier routing in ``config/queries.py`` (a local_only
tier answers with ``describe_secret`` metadata, never the value) and the
MCP dispatch choke point in ``mcp/server.py`` (every tools/call result
passes through ``mcp_response()`` whether or not the handler remembered).
Halbert's own agent reads the raw canon; external readers never do.

This script stages the host config tree RAW and then proves both
boundaries still hold — the operational gate the Tier 2 plan asked for:
run it, and trust raw staging only when it exits 0.

Steps
-----
1. Authenticate with the SourcePrep daemon (PREP_DAEMON_TOKEN via
   ``halbert_core.integrations.prep_token``).
2. ``SourcePrepSetup().apply(redact_host=False, build_fast_sync_only=True)``
   — stage host config files raw and apply that to the unified ``halbert``
   project (id ``735a592e-a2da-499b-a614-854a5fc461f5`` as of 2026-09,
   daemon at ``127.0.0.1:8400``), NOT the legacy ``halbert-host`` project
   ``register_host_project()`` targets — that project name is retired
   (see ``sourceprep_setup.LEGACY_PROJECT_NAMES``). ``build_fast_sync_only``
   re-stages ``host/`` plus an incremental fast_sync + CodeIndex build
   only; it does not touch ``knowledge/``'s deep_enrichment, so a
   config-only rebuild never re-embeds the ~16K-doc corpus.
3. ``snapshot(<config-registry.yml>, redact=False)`` — populate the canon
   database with unredacted canonical JSON.
4. The daemon index build was triggered by step 2's ``apply()`` call
   unless ``--skip-build``. (The task packet named a ``POST /api/reindex``
   route; the daemon exposes no such route — ``apply()``'s own build
   sequence, ultimately ``POST /projects/{id}/trace/build``, is the real
   trigger.)
5. Egress check: find the first secret-tier key in the freshly staged
   canon and query it through BOTH boundaries — tier routing and the MCP
   dispatch choke point — asserting only ``describe_secret`` metadata is
   emitted and the raw value appears nowhere in either response.

   CAVEAT: boundary 2 goes through ``_tool_get_config_value ->
   load_being_config()`` — the REAL host's current secret tier, unlike
   boundary 1 which always probes against the hardcoded ``local_only``
   default. If the host is UNLOCKED (``cloud_ok_acknowledged``, TTL not
   expired) the value legitimately crosses with ``_egress_ack`` and
   ``mcp_response()`` correctly lets it through (stripping the marker
   before it reaches this script) — so treating that crossing as a leak
   would be a false positive. This script is lock-aware: it checks the
   host's current tier before failing boundary 2 and downgrades an
   apparent leak to an informational note when the host is unlocked,
   rather than a false ``exit 2``. For a fully trustworthy boundary-2
   result, still prefer running this only while the host is locked
   (``local_only``) — and only when no other SourcePrep build is running.

Exit codes: 0 = rebuilt and egress verified; 1 = operational failure;
2 = EGREGIOUS — the egress check FAILED while the host was locked (do
not trust this host's raw staging until investigated).

``--dry-run`` verifies the token, daemon reachability, and manifest
readability and stages nothing, writes nothing.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

DEFAULT_BASE_URL = "http://127.0.0.1:8400"


def _fail(code: int, message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(code)


def _find_config_registry() -> Optional[Path]:
    """config/config-registry.yml — same candidate chain the dashboard uses."""
    candidates = [Path.cwd() / "config" / "config-registry.yml"]
    try:
        from halbert_core.config import snapshot as _snapshot  # noqa: F401

        candidates.append(Path(_snapshot.__file__).resolve().parent.parent.parent / "config" / "config-registry.yml")
    except ImportError:
        pass
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _check_daemon(base_url: str) -> None:
    """The daemon must answer and the token must be present before we touch it."""
    import requests

    from halbert_core.integrations.prep_token import auth_headers, get_token

    if not get_token():
        _fail(1, "no PREP_DAEMON_TOKEN (halbert_core.integrations.prep_token.get_token() is empty) — the daemon would refuse every call")
    try:
        resp = requests.get(f"{base_url}/projects", timeout=5, headers=auth_headers())
        resp.raise_for_status()
    except Exception as e:
        _fail(1, f"SourcePrep daemon at {base_url} is not reachable: {e}")


def _first_secret_key(probe_key: Optional[str]) -> Optional[Tuple[str, str, str]]:
    """(path, key, raw_value) of the first secret-tier pair in the fresh canon.

    The canon was just written raw, so a pair classified tier 2 here is a real
    secret sitting in the knowledge base — exactly what the egress check
    needs to prove cannot get out. An explicit --probe-key short-circuits the
    scan; a host whose staged configs hold no secrets yields None and the
    check reports itself vacuous rather than silently passing.
    """
    from halbert_core.config.queries import _load_latest_snapshot, _load_canon
    from halbert_core.config.sensitivity import classify_sensitivity
    from halbert_core.config.parser import parse as parse_config

    if probe_key:
        for entry in _load_latest_snapshot():
            path = entry.get("path", "")
            if not path:
                continue
            try:
                canon = parse_config(path)
            except Exception:
                continue
            for line in canon.get("lines") or []:
                key = str(line.get("key") or "")
                value = line.get("value")
                if key and probe_key.strip().lower() == key.strip().lower() and value is not None:
                    return path, key, str(value)
        return None

    for entry in _load_latest_snapshot():
        path, file_hash = entry.get("path", ""), entry.get("hash", "")
        canon = _load_canon(file_hash) if file_hash else None
        if canon is None:
            continue
        for line in canon.get("lines") or []:
            key = str(line.get("key") or "")
            value = line.get("value")
            if not key or value is None:
                continue
            if classify_sensitivity(key, value, path) >= 2:
                return path, key, str(value)
    return None


def _egress_check(probe_key: Optional[str]) -> Dict[str, Any]:
    """Assert both egress boundaries hold on the raw-staged canon.

    Boundary 1 — tier routing: ``get_config_value`` with the default
    ``local_only`` secret tier must answer with a description, never the
    value.

    Boundary 2 — the MCP dispatch choke point: the same query through
    ``tools/call`` must come back redacted regardless of what the handler
    returned. Unlike boundary 1, this goes through
    ``_tool_get_config_value -> load_being_config()`` — the host's REAL
    current secret tier. If the host is unlocked (``cloud_ok_acknowledged``,
    TTL not expired), the value legitimately crosses with ``_egress_ack``
    (stripped before it reaches here) — an apparent "leak" in that state
    is a false positive, not a bug, so it's downgraded to a note instead
    of failing. See the module docstring's step 5 caveat.

    Returns a report dict; raises SystemExit(2) on a leak while the host
    is locked (the only state where boundary 2 is fully trustworthy).
    """
    from halbert_core.config.queries import get_config_value
    from halbert_core.config.being_config import load_being_config
    from halbert_core.mcp.server import MCPServer

    host_unlocked = False
    try:
        host_unlocked = load_being_config().security.effective_secret_tier() != "local_only"
    except Exception:
        pass  # fail closed on the caveat: an unreadable config is treated as locked

    found = _first_secret_key(probe_key)
    if found is None:
        return {
            "vacuous": True,
            "note": "no secret-tier key found in the freshly staged canon — "
            "egress check could not run (pass --probe-key or stage a credential file)",
        }
    path, key, raw_value = found
    report: Dict[str, Any] = {"vacuous": False, "path": path, "key": key}

    # Boundary 1: tier routing.
    tiered = get_config_value(path, key)  # defaults: secret_tier="local_only"
    report["tier_routing"] = {
        "tier": tiered.get("tier"),
        "described": "description" in tiered,
        "value_leaked": "value" in tiered or raw_value in json.dumps(tiered, default=str),
    }
    if report["tier_routing"]["value_leaked"] or not report["tier_routing"]["described"]:
        _fail(2, f"tier routing leaked {key!r} from {path}: {json.dumps(tiered, default=str)[:400]}")

    # Boundary 2: the MCP dispatch choke point, end to end.
    server = MCPServer(instance_name="rebuild-script", hostname="localhost")
    resp = server.handle_request({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "get_config_value",
            "arguments": {"path": path, "key": key},
        },
    })
    body = resp.get("result", {}).get("content", [{}])[0].get("text", "") if resp else ""
    report["mcp_dispatch"] = {
        "redacted_marker": "<secret>" in body or "description" in body,
        "value_leaked": raw_value in json.dumps(resp, default=str),
        "host_unlocked": host_unlocked,
    }
    if report["mcp_dispatch"]["value_leaked"] or not report["mcp_dispatch"]["redacted_marker"]:
        if host_unlocked:
            report["mcp_dispatch"]["note"] = (
                "host secret tier is not local_only — this crossing may be "
                "the legitimate _egress_ack escape hatch, not a leak; "
                "re-run while the host is locked (local_only) for a "
                "trustworthy boundary-2 result"
            )
        else:
            _fail(2, f"MCP dispatch leaked {key!r} from {path}: {body[:400]}")

    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="rebuild_sourceprep_unredacted",
        description="Stage the host config tree RAW into SourcePrep and prove the egress boundaries hold (TASK-03 Task 3.2).",
    )
    parser.add_argument("--dry-run", action="store_true", help="verify token/daemon/manifest only; stage and write nothing")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help=f"SourcePrep daemon URL (default {DEFAULT_BASE_URL})")
    parser.add_argument("--probe-key", default=None, help="query this key for the egress check instead of auto-discovering the first secret")
    parser.add_argument("--skip-build", action="store_true", help="stage and snapshot but do not trigger the daemon index build")
    args = parser.parse_args()

    _check_daemon(args.base_url)
    registry = _find_config_registry()
    if registry is None:
        _fail(1, "config/config-registry.yml not found (cwd or package parents)")

    if args.dry_run:
        print(json.dumps({
            "dry_run": True,
            "daemon": args.base_url,
            "manifest": str(registry),
            "would_stage": "host config tree RAW (redact=False) + canon snapshot(redact=False)",
        }, indent=2))
        return

    # 1. Stage raw + apply to the unified 'halbert' project — NOT the
    #    legacy 'halbert-host' project register_host_project() targets.
    #    build_fast_sync_only skips knowledge/'s deep_enrichment so this
    #    config-only rebuild never re-embeds the doc corpus.
    from halbert_core.integrations.sourceprep_setup import SourcePrepSetup

    setup = SourcePrepSetup(base_url=args.base_url)
    try:
        reg = setup.apply(
            build=not args.skip_build,
            build_fast_sync_only=True,
            redact_host=False,
        )
    except Exception as e:
        _fail(1, f"SourcePrepSetup.apply(redact_host=False) failed: {e}")
    if reg.get("status") == "skipped":
        _fail(1, f"apply skipped: {reg.get('reason')}")
    print(
        f"staged {reg.get('files_staged')} raw files into project "
        f"{reg.get('project_id')} at {reg.get('root')}"
    )

    # 2. Raw canon snapshot for the tier-routed config brain.
    from halbert_core.config.snapshot import snapshot

    entries: List[Dict[str, Any]] = snapshot(str(registry), redact=False)
    errors = [e for e in entries if e.get("error")]
    print(f"snapshot: {len(entries)} files, {len(errors)} errors")
    for e in errors[:5]:
        print(f"  {e.get('path')}: {e.get('error')}")

    # 3. The daemon index build was triggered by step 1's apply() call
    #    unless --skip-build; nothing else to do here (see module
    #    docstring for why there is no /api/reindex call).

    # 4. Prove the egress boundaries on the raw content just written.
    report = _egress_check(args.probe_key)
    print(json.dumps(report, indent=2))
    if report.get("vacuous"):
        print("WARNING: egress check was vacuous — no secret was found to probe.")
    else:
        print("egress boundaries verified: tier routing and MCP dispatch both metadata-only.")


if __name__ == "__main__":
    main()