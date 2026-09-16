# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Capacity is not one number.

A btrfs or bcachefs filesystem allocates block groups for data, for metadata
and for its own bookkeeping, and a volume can run out of metadata space with
terabytes of data space free. `btrfs fi df` and `bcachefs fs usage` both report
that split; these tests pin that we keep the bytes rather than only the RAID
profile string, and that we report nothing at all when the tool is unavailable
instead of inventing a zero.
"""

import pytest

from halbert_core.discovery.scanners.storage import StorageScanner, parse_iec_bytes


class TestParseIecBytes:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("4.00TiB", 4 * 1024**4),
            ("1.40TiB", int(1.40 * 1024**4)),
            ("10.00GiB", 10 * 1024**3),
            ("2.85GiB", int(2.85 * 1024**3)),
            ("64.00MiB", 64 * 1024**2),
            ("176.00KiB", 176 * 1024),
            ("512.00B", 512),
            ("1.40 TiB", int(1.40 * 1024**4)),  # bcachefs spaces its units
            ("123456789", 123456789),  # and sometimes emits raw bytes
        ],
    )
    def test_parses_the_units_these_tools_emit(self, text, expected):
        assert parse_iec_bytes(text) == expected

    @pytest.mark.parametrize("text", ["", "   ", "n/a", "-", "TiB", None])
    def test_unreadable_values_are_none_not_zero(self, text):
        # Zero is a measurement. Absence is not.
        assert parse_iec_bytes(text) is None


BTRFS_FI_DF = """Data, RAID0: total=4.00TiB, used=1.40TiB
System, RAID1: total=64.00MiB, used=176.00KiB
Metadata, RAID1: total=10.00GiB, used=2.85GiB
GlobalReserve, single: total=512.00MiB, used=0.00B
"""

BCACHEFS_FS_USAGE = """Filesystem: 3f2a1b00-0000-0000-0000-000000000000
Size:                    10995116277760
Used:                     5497558138880
Online reserved:               67108864

Data type       Required/total  Durability    Devices
btree:          1/2             2             [nvme0 nvme1]          21474836480
user:           1/1             1             [sdb]                5368709120000
cached:         1/1             1             [nvme0]               107374182400

nvme.u2_01 (device 0):         nvme0n1
"""


def _scanner(command_output):
    """A StorageScanner whose shell is a lookup table keyed on the command."""
    scanner = StorageScanner()

    def fake_run_command(argv, timeout=None):
        for key, out in command_output.items():
            if key in " ".join(argv):
                return (0, out, "")
        return (1, "", "not found")

    scanner.run_command = fake_run_command  # type: ignore[method-assign]
    # The host running these tests has neither tool; the lookup table above is
    # the only shell that matters here.
    scanner.command_exists = lambda name: True  # type: ignore[method-assign]
    return scanner


class TestBtrfsAllocation:
    def test_keeps_the_bytes_not_only_the_profile(self):
        scanner = _scanner({"btrfs fi df": BTRFS_FI_DF, "findmnt": ""})
        result = scanner._scan_btrfs_array("/mnt/tank")

        assert result["data_profile"] == "raid0"
        assert result["metadata_profile"] == "raid1"

        alloc = result["allocation"]
        assert alloc["data_bytes"] == int(1.40 * 1024**4)
        assert alloc["metadata_bytes"] == int(2.85 * 1024**3)
        assert alloc["system_bytes"] == 176 * 1024
        assert alloc["source"] == "btrfs fi df"

    def test_no_allocation_when_the_tool_is_absent(self):
        scanner = _scanner({"findmnt": ""})
        result = scanner._scan_btrfs_array("/mnt/tank")
        assert result.get("allocation") is None


class TestBcachefsAllocation:
    def test_reads_the_data_type_table(self):
        scanner = _scanner(
            {"fs usage": BCACHEFS_FS_USAGE, "findmnt": "", "show-super": ""}
        )
        result = scanner._scan_bcachefs_array("/mnt/pool")

        alloc = result["allocation"]
        assert alloc["data_bytes"] == 5368709120000
        assert alloc["metadata_bytes"] == 21474836480
        assert alloc["cached_bytes"] == 107374182400
        assert alloc["total_bytes"] == 10995116277760
        assert alloc["source"] == "bcachefs fs usage"

    def test_no_allocation_when_the_tool_is_absent(self):
        scanner = _scanner({"findmnt": ""})
        result = scanner._scan_bcachefs_array("/mnt/pool")
        assert result.get("allocation") is None
