"""StorageAuditorAgent (D1b).

A deterministic subagent: spawns smartctl/zpool/lsblk via the PTY manager,
parses the output for storage anomalies (reallocated/pending/offline-uncorrect
SMART sectors, zpool DEGRADED/FAULTED/errors), and — when a FindingStore is
injected — records a Finding summarizing them. NO LLM call: pure command
execution + regex parsing.

Tolerant of missing tools/devices: a command that fails or produces no
output contributes no anomalies (the auditor runs on macOS dev machines where
smartctl/zpool may be absent; on Linux hosts it does the real work).

See OPUS-HANDOFF §D1b.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
import uuid
from typing import Any, Dict, List, Optional

logger = logging.getLogger("halbert.agents.subagents.storage_auditor")

# Commands to run (name -> shell command). Chosen to be safe read-only probes.
COMMANDS: Dict[str, str] = {
    "smartctl": "smartctl -a /dev/sda 2>/dev/null || true",
    "zpool": "zpool status 2>/dev/null || true",
    "lsblk": "lsblk -o NAME,SIZE,TYPE,MOUNTPOINT 2>/dev/null || true",
}

# SMART attribute IDs we flag as anomalies when non-zero
_SMART_ANOMALY_ATTRS = {
    "5": "reallocated_sector_count",
    "197": "current_pending_sector",
    "198": "offline_uncorrectable",
    "9": "power_on_hours",  # informational, not flagged
}


# ---------------------------------------------------------------------------
# Parsers (pure functions — unit-testable with canned strings)
# ---------------------------------------------------------------------------

def parse_smartctl(output: str) -> List[Dict[str, Any]]:
    """Parse smartctl -a output for anomalies.

    Flags: SMART overall-health failing, and non-zero reallocated/pending/
    offline-uncorrectable attribute raw values.
    """
    anomalies: List[Dict[str, Any]] = []
    if not output:
        return anomalies

    # Overall health
    health = re.search(r"SMART overall-health self-assessment test result:\s*(.+)", output)
    if health and "PASSED" not in health.group(1).upper():
        anomalies.append({
            "type": "smart_health_fail",
            "detail": health.group(1).strip(),
        })

    # Attributes table: each line is "ID NAME FLAG VALUE WORST THRESH TYPE
    # UPDATED WHEN_FAIL RAW_VALUE". Capture the leading ID and the trailing
    # raw value (the last integer on the line). We only flag known attr IDs.
    for m in re.finditer(r"^\s*(\d+)\s+\S[^\n]*?\s+(\d+)\s*$", output, re.MULTILINE):
        attr_id, raw = m.group(1), m.group(2)
        if attr_id in _SMART_ANOMALY_ATTRS and attr_id != "9":
            raw_int = int(raw)
            if raw_int > 0:
                anomalies.append({
                    "type": _SMART_ANOMALY_ATTRS[attr_id],
                    "raw": raw_int,
                })
    return anomalies


def parse_zpool(output: str) -> List[Dict[str, Any]]:
    """Parse `zpool status` for pool errors / degraded / faulted state."""
    anomalies: List[Dict[str, Any]] = []
    if not output:
        return anomalies
    for m in re.finditer(
        r"^\s*(\S+)\s+(\S+)\s+(\S+)(?:\s+(\S+))?", output, re.MULTILINE,
    ):
        pool, state = m.group(1), m.group(2)
        if state in ("DEGRADED", "FAULTED", "SUSPENDED", "UNAVAIL"):
            anomalies.append({"type": "zpool_state", "pool": pool, "state": state})
    # Explicit error counters
    err = re.search(r"errors:\s*(.+)", output, re.IGNORECASE)
    if err and "No known data errors" not in err.group(1):
        anomalies.append({"type": "zpool_errors", "detail": err.group(1).strip()})
    return anomalies


def parse_lsblk(output: str) -> List[Dict[str, Any]]:
    """Parse lsblk into a drive inventory (no anomaly flagging)."""
    drives: List[Dict[str, Any]] = []
    if not output:
        return drives
    for line in output.splitlines():
        parts = line.split()
        if not parts or parts[0] == "NAME":  # skip blank + header
            continue
        if len(parts) >= 3:
            drives.append({
                "name": parts[0],
                "size": parts[1],
                "type": parts[2],
                "mountpoint": parts[3] if len(parts) > 3 else "",
            })
    return drives


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class StorageAuditorAgent:
    """Deterministic storage auditor: runs SMART/ZFS/lsblk, parses, reports."""

    def __init__(
        self,
        pty_manager: Any = None,
        finding_store: Any = None,
        command_timeout: float = 15.0,
    ):
        self.pty_manager = pty_manager
        self.finding_store = finding_store
        self.command_timeout = command_timeout

    async def run(self) -> Dict[str, Any]:
        """Run all probes, parse, and (optionally) record a Finding.

        Returns a result dict: {anomalies, drives, raw, finding_id}.
        """
        raw: Dict[str, Dict[str, Any]] = {}
        for name, cmd in COMMANDS.items():
            raw[name] = await self._run_command(cmd)

        anomalies: List[Dict[str, Any]] = []
        anomalies += parse_smartctl(raw["smartctl"]["output"])
        anomalies += parse_zpool(raw["zpool"]["output"])
        drives = parse_lsblk(raw["lsblk"]["output"])

        finding_id: Optional[str] = None
        if anomalies and self.finding_store is not None:
            finding_id = self._record_finding(anomalies, drives)

        return {
            "anomalies": anomalies,
            "drives": drives,
            "raw": raw,
            "finding_id": finding_id,
        }

    async def _run_command(self, command: str) -> Dict[str, Any]:
        """Spawn one command via the PTY manager, drain it, return output/exit."""
        if self.pty_manager is None:
            return {"output": "", "exit_code": -1, "error": "no pty_manager"}
        try:
            session_id = await self.pty_manager.spawn(command)
        except Exception as e:
            return {"output": "", "exit_code": -1, "error": str(e)}

        session = self.pty_manager.get(session_id)
        output = bytearray()

        async def drain():
            if session is None:
                return
            gen = session.read_chunk()
            try:
                async for chunk in gen:
                    output.extend(chunk)
            finally:
                await gen.aclose()

        try:
            await asyncio.wait_for(drain(), timeout=self.command_timeout)
        except asyncio.TimeoutError:
            pass

        exit_code = getattr(session, "exit_code", None) if session else -1
        try:
            self.pty_manager.kill(session_id)
        except Exception:
            pass
        return {
            "output": bytes(output).decode("utf-8", errors="replace"),
            "exit_code": exit_code if exit_code is not None else -1,
            "error": "",
        }

    def _record_finding(
        self, anomalies: List[Dict[str, Any]], drives: List[Dict[str, Any]]
    ) -> Optional[str]:
        """Create a Finding summarizing the anomalies and add it to the store."""
        try:
            from ...findings.store import Finding
        except Exception as e:
            logger.debug(f"FindingStore import failed: {e}")
            return None

        severity = "critical" if any(
            a.get("type") in ("smart_health_fail", "zpool_state") for a in anomalies
        ) else "warning"
        summary = "; ".join(
            a.get("type", "anomaly") + (f"={a.get('raw')}" if "raw" in a else "")
            for a in anomalies
        )
        affected = [f"/dev/{d['name']}" for d in drives if d.get("name")]

        finding = Finding(
            id=str(uuid.uuid4()),
            detector="storage_auditor",
            severity=severity,
            title=f"Storage anomalies detected ({len(anomalies)})",
            description=summary,
            why_now="smartctl/zpool probes reported non-normal values",
            why_care="Failing disks or a degraded pool can cause data loss",
            why_so=summary,
            why_trust=["smartctl", "zpool"],
            affected_paths=affected,
            affected_services=["storage"],
            status="open",
            created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        )
        try:
            return self.finding_store.add(finding)
        except Exception as e:
            logger.warning(f"Finding add failed: {e}")
            return None