# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""R9: Fence HybridMemorySystem off the agent path.

A static text scan that fails if HybridMemorySystem, get_hybrid_memory,
or their MemoryServiceAdapter carrier appear in the agent runtime code.
The fence is a ratchet: once the agent route is clean, any future PR
that re-introduces the ChromaDB-backed memory onto the agent path
fails this test immediately.

HybridMemorySystem remains importable for eval, browser, and migration
tooling — those paths are not scanned here.
"""

from pathlib import Path

import pytest

#: Files and directories that constitute the agent runtime path.
#: If a file here references a forbidden token, the fence fires.
_AGENT_PATHS = [
    "halbert_core/agents",
    "halbert_core/dashboard/routes/agent.py",
]

#: Tokens that must not appear in the agent runtime.
_FORBIDDEN = [
    "get_hybrid_memory",
    "HybridMemorySystem",
    "MemoryServiceAdapter",
    "create_wired_context_assembler",
]


def _scan_agent_path() -> list[str]:
    root = Path(__file__).resolve().parents[1]
    offenders: list[str] = []
    for entry in _AGENT_PATHS:
        path = root / entry
        if path.is_dir():
            files = list(path.rglob("*.py"))
        else:
            files = [path]
        for py in files:
            text = py.read_text(errors="replace")
            for token in _FORBIDDEN:
                if token in text:
                    offenders.append(f"{py.relative_to(root)} references {token}")
    return offenders


def test_hybrid_memory_not_on_agent_path():
    """HybridMemorySystem and its carrier must not be reachable from the agent runtime."""
    offenders = _scan_agent_path()
    assert offenders == [], (
        f"HybridMemorySystem leaked onto the agent path: {offenders}"
    )


def test_hybrid_memory_still_importable():
    """HybridMemorySystem remains importable for eval/browser/migration tooling."""
    from halbert_core.memory.hybrid import HybridMemorySystem, get_hybrid_memory
    assert HybridMemorySystem is not None
    assert get_hybrid_memory is not None
