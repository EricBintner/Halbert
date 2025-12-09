from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import fnmatch
import getpass
import os
import socket
from datetime import datetime, time as dtime


@dataclass
class Decision:
    allow: bool
    reason: str = ""
    simulation_required: bool = False
    rollback_required: bool = False
    approvals_needed: list[str] = None  # type: ignore

    def __post_init__(self):
        if self.approvals_needed is None:
            self.approvals_needed = []


def _parse_range(r: str) -> Optional[tuple[dtime, dtime]]:
    try:
        s, e = r.split("-", 1)
        sh, sm = [int(x) for x in s.split(":", 1)]
        eh, em = [int(x) for x in e.split(":", 1)]
        return dtime(sh, sm), dtime(eh, em)
    except Exception:
        return None


def _in_hours(now: dtime, ranges: List[str]) -> bool:
    for r in ranges:
        pe = _parse_range(r)
        if not pe:
            continue
        start, end = pe
        if start <= end:
            if start <= now <= end:
                return True
        else:  # wraps midnight
            if now >= start or now <= end:
                return True
    return False


def decide(policy: Dict[str, Any], tool_name: str, *, is_apply: bool, ctx: Optional[Dict[str, Any]] = None) -> Decision:
    """
    Evaluate allow/deny for a tool apply request.
    Supported conditions (optional, tool-specific):
      - users: ["alice", "root"]
      - hosts: ["*.corp", "host-01"] (glob)
      - hours_allow: ["08:00-18:00", "20:00-22:00"] (local time)
      - paths_allow: ["/etc/cerebric/*", "/etc/systemd/system/*.service"] (write_config)
      - paths_deny: ["**/*.service"]
      - names_allow: ["backup", "rotate"] (schedule_cron)
    """
    tools = policy.get("tools") or {}
    if not is_apply:
        return Decision(True)

    # Tool config & default allow
    tcfg = tools.get(tool_name) or {}
    allow_default = bool(tcfg.get("allow", policy.get("default_allow", True)))
    if not allow_default:
        return Decision(False, reason=f"tool {tool_name} denied by policy")

    # Extract policy directives
    simulation_required = bool(tcfg.get("simulation_required", False))
    rollback_required = bool(tcfg.get("rollback_required", False))
    approvals = tcfg.get("approvals") or []

    cond = tcfg.get("conditions") or {}
    if not cond:
        return Decision(True, simulation_required=simulation_required, rollback_required=rollback_required, approvals_needed=approvals)

    # Gather context
    inputs = (ctx or {}).get("inputs") or {}
    cur_user = os.environ.get("SUDO_USER") or getpass.getuser()
    host = socket.gethostname()

    # Users
    users = cond.get("users")
    if isinstance(users, list) and users:
        if cur_user not in users:
            return Decision(False, reason=f"user {cur_user} not allowed")

    # Hosts (glob)
    hosts = cond.get("hosts")
    if isinstance(hosts, list) and hosts:
        if not any(fnmatch.fnmatch(host, patt) for patt in hosts):
            return Decision(False, reason=f"host {host} not allowed")

    # Hours allow
    hours = cond.get("hours_allow")
    if isinstance(hours, list) and hours:
        now = datetime.now().time()
        if not _in_hours(now, [str(x) for x in hours]):
            return Decision(False, reason="outside allowed hours")

    # Paths allow/deny (for write_config)
    path = str(inputs.get("path") or "")
    if path:
        paths_allow = cond.get("paths_allow")
        if isinstance(paths_allow, list) and paths_allow:
            if not any(fnmatch.fnmatch(path, patt) for patt in paths_allow):
                return Decision(False, reason=f"path not allowed: {path}")
        paths_deny = cond.get("paths_deny")
        if isinstance(paths_deny, list) and paths_deny:
            if any(fnmatch.fnmatch(path, patt) for patt in paths_deny):
                return Decision(False, reason=f"path denied: {path}")

    # Names allow (for schedule_cron)
    name = str(inputs.get("name") or "")
    if name:
        names_allow = cond.get("names_allow")
        if isinstance(names_allow, list) and names_allow:
            if name not in names_allow:
                return Decision(False, reason=f"name not allowed: {name}")

    return Decision(True, simulation_required=simulation_required, rollback_required=rollback_required, approvals_needed=approvals)
