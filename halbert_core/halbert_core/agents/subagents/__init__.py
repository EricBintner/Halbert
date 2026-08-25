"""Subagent implementations (D1b+).

Each subagent is a deterministic, scoped worker. The first is the
StorageAuditorAgent (D1b): runs smartctl/zpool/lsblk and parses anomalies
into a Finding — no LLM call.
"""

from .storage_auditor import (
    StorageAuditorAgent,
    parse_smartctl,
    parse_zpool,
    parse_lsblk,
)

__all__ = [
    "StorageAuditorAgent",
    "parse_smartctl",
    "parse_zpool",
    "parse_lsblk",
]