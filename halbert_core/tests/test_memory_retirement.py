# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The unreadable file-memory subsystem is gone (audit F1)."""

import importlib

import pytest


def test_writer_module_is_gone():
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("halbert_core.memory.writer")


def test_retrieval_module_is_gone():
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("halbert_core.memory.retrieval")


def test_memory_package_no_longer_exports_them():
    import halbert_core.memory as m

    assert "MemoryWriter" not in m.__all__
    assert "MemoryRetrieval" not in m.__all__
    assert "HybridMemorySystem" in m.__all__   # the eval/browser path stays


def test_hybrid_memory_still_importable():
    from halbert_core.memory import HybridMemorySystem, MemoryType, get_hybrid_memory  # noqa: F401


def test_scheduler_no_longer_imports_or_calls_the_writer():
    """The explanatory docstring may name it; nothing may import or construct it."""
    from pathlib import Path

    text = (Path(__file__).resolve().parents[1]
            / "halbert_core" / "scheduler" / "executor.py").read_text()
    assert "from ..memory.writer import" not in text
    assert "MemoryWriter()" not in text


def test_no_module_imports_the_deleted_pair():
    """Repo-wide ratchet: nothing may import the retired modules again."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    offenders = []
    for py in root.rglob("*.py"):
        if "node_modules" in py.parts or py.name == Path(__file__).name:
            continue
        t = py.read_text(errors="replace")
        if "memory.writer import" in t or "memory.retrieval import" in t:
            offenders.append(str(py.relative_to(root)))
    assert offenders == []
