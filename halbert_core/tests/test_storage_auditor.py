# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for StorageAuditorAgent (D1b)."""

import asyncio
import pytest

from halbert_core.agents.subagents.storage_auditor import (
    StorageAuditorAgent, parse_smartctl, parse_zpool, parse_lsblk,
)


# ---------------------------------------------------------------------------
# Parsers (pure)
# ---------------------------------------------------------------------------

SMARTCTL_HEALTHY = """
SMART overall-health self-assessment test result: PASSED
ID# ATTRIBUTE_NAME          FLAG     VALUE WORST THRESH TYPE UPDATED WHEN_FAIL RAW_VALUE
  5 Reallocated_Sector_Ct   0x0032   100   100   000    Old_age   Online      -       0
  9 Power_On_Hours           0x0032   097   097   000    Old_age   Online      -       3500
 197 Current_Pending_Sector 0x0012   100   100   000    Old_age   Online      -       0
"""

SMARTCTL_FAILING = """
SMART overall-health self-assessment test result: FAILED!
ID# ATTRIBUTE_NAME          FLAG     VALUE WORST THRESH TYPE UPDATED WHEN_FAIL RAW_VALUE
  5 Reallocated_Sector_Ct   0x0032   001   001   000    Old_age   Online      -       42
 197 Current_Pending_Sector 0x0012   050   050   000    Old_age   Online      -       7
 198 Offline_Uncorrectable  0x0010   050   050   000    Old_age   Online      -       3
"""

ZPOOL_HEALTHY = """
  pool: tank
 state: ONLINE
config:
        NAME        STATE     READ WRITE CKSUM
        tank        ONLINE       0     0     0
errors: No known data errors
"""

ZPOOL_DEGRADED = """
  pool: tank
 state: DEGRADED
config:
        NAME        STATE     READ WRITE CKSUM
        tank        DEGRADED     0     0     0
errors: 1 data errors
"""

LSBLK_OUT = """
NAME    SIZE TYPE MOUNTPOINT
sda       1T disk
sda1    512M part /boot
nvme0n1   2T disk
"""


class TestParsers:
    def test_smartctl_healthy_no_anomalies(self):
        assert parse_smartctl(SMARTCTL_HEALTHY) == []

    def test_smartctl_failing_flags_health_and_attrs(self):
        anomalies = parse_smartctl(SMARTCTL_FAILING)
        types = {a["type"] for a in anomalies}
        assert "smart_health_fail" in types
        assert "reallocated_sector_count" in types
        assert "current_pending_sector" in types
        assert "offline_uncorrectable" in types

    def test_smartctl_empty(self):
        assert parse_smartctl("") == []

    def test_zpool_healthy_no_anomalies(self):
        assert parse_zpool(ZPOOL_HEALTHY) == []

    def test_zpool_degraded_flagged(self):
        anomalies = parse_zpool(ZPOOL_DEGRADED)
        assert any(a["type"] == "zpool_state" and a["state"] == "DEGRADED" for a in anomalies)
        assert any(a["type"] == "zpool_errors" for a in anomalies)

    def test_lsblk_inventory(self):
        drives = parse_lsblk(LSBLK_OUT)
        assert len(drives) == 3
        assert drives[0]["name"] == "sda"
        assert drives[2]["name"] == "nvme0n1"


# ---------------------------------------------------------------------------
# Runner with a fake PTY manager
# ---------------------------------------------------------------------------

class _FakeSession:
    def __init__(self, output_bytes):
        self._out = output_bytes
        self.exit_code = 0

    async def read_chunk(self):
        if self._out:
            yield self._out


class _FakePty:
    """Returns canned output keyed by command substring."""

    def __init__(self, canned: dict):
        self._canned = canned  # {substring: bytes}
        self._sessions = {}
        self._counter = 0

    async def spawn(self, command, **kw):
        self._counter += 1
        sid = f"fake-{self._counter}"
        out = b""
        for key, val in self._canned.items():
            if key in command:
                out = val
                break
        self._sessions[sid] = _FakeSession(out)
        return sid

    def get(self, sid):
        return self._sessions.get(sid)

    def kill(self, sid):
        self._sessions.pop(sid, None)


class _FakeFindingStore:
    def __init__(self):
        self.findings = {}

    def add(self, finding):
        self.findings[finding.id] = finding
        return finding.id


@pytest.mark.asyncio
async def test_run_detects_anomalies_and_creates_finding():
    pty = _FakePty({
        "smartctl": SMARTCTL_FAILING.encode(),
        "zpool": ZPOOL_DEGRADED.encode(),
        "lsblk": LSBLK_OUT.encode(),
    })
    store = _FakeFindingStore()
    agent = StorageAuditorAgent(pty_manager=pty, finding_store=store)
    result = await agent.run()

    assert len(result["anomalies"]) >= 4
    assert result["finding_id"] is not None
    assert result["finding_id"] in store.findings
    assert store.findings[result["finding_id"]].severity == "critical"
    assert len(result["drives"]) == 3


@pytest.mark.asyncio
async def test_run_healthy_no_finding():
    pty = _FakePty({
        "smartctl": SMARTCTL_HEALTHY.encode(),
        "zpool": ZPOOL_HEALTHY.encode(),
        "lsblk": LSBLK_OUT.encode(),
    })
    store = _FakeFindingStore()
    agent = StorageAuditorAgent(pty_manager=pty, finding_store=store)
    result = await agent.run()
    assert result["anomalies"] == []
    assert result["finding_id"] is None


@pytest.mark.asyncio
async def test_run_without_finding_store_still_parses():
    pty = _FakePty({
        "smartctl": SMARTCTL_FAILING.encode(),
        "zpool": ZPOOL_HEALTHY.encode(),
        "lsblk": LSBLK_OUT.encode(),
    })
    agent = StorageAuditorAgent(pty_manager=pty, finding_store=None)
    result = await agent.run()
    assert len(result["anomalies"]) >= 2
    assert result["finding_id"] is None  # no store -> no finding


@pytest.mark.asyncio
async def test_run_without_pty_manager():
    agent = StorageAuditorAgent(pty_manager=None, finding_store=_FakeFindingStore())
    result = await agent.run()
    assert result["anomalies"] == []
    assert result["finding_id"] is None
