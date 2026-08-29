# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for T3.6 — context-assembly secure content backstop."""
from __future__ import annotations

import asyncio
import os
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from halbert_core.context.assembler import ContextAssembler, AssembledContext
from halbert_core.context.tokens import TokenCounter


@pytest.fixture
def assembler():
    """A minimal assembler with no retrieval/memory/discovery services."""
    return ContextAssembler(
        retrieval_service=None,
        memory_service=None,
        discovery_service=None,
        token_counter=TokenCounter(),
    )


class TestSecureFlag:
    """The secure flag on AssembledContext."""

    def test_default_secure_false(self):
        ctx = AssembledContext(content="hello", sources=[], total_tokens=1)
        assert ctx.secure is False

    def test_to_dict_includes_secure(self):
        ctx = AssembledContext(content="hello", sources=[], total_tokens=1, secure=True)
        d = ctx.to_dict()
        assert "secure" in d
        assert d["secure"] is True


class TestSecureDetection:
    """detect_secure_content runs over assembled context."""

    @pytest.mark.asyncio
    async def test_clean_context_not_secure(self, assembler):
        """A context with no secrets should not set secure=True."""
        result = await assembler.assemble(
            query="what is my hostname",
            conversation=None,
            observations=["hostname is myhost"],
            max_tokens=1000,
        )
        assert result.secure is False

    @pytest.mark.asyncio
    async def test_password_in_observations_sets_secure(self, assembler):
        """A password in observations should trigger secure detection."""
        result = await assembler.assemble(
            query="check my config",
            conversation=None,
            observations=["password=hunter2 found in config"],
            max_tokens=1000,
        )
        assert result.secure is True

    @pytest.mark.asyncio
    async def test_pem_in_observations_sets_secure(self, assembler):
        """A PEM block in observations should trigger secure detection."""
        pem = "-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIKB\n-----END RSA PRIVATE KEY-----"
        result = await assembler.assemble(
            query="check keys",
            conversation=None,
            observations=[f"found key: {pem}"],
            max_tokens=1000,
        )
        assert result.secure is True

    @pytest.mark.asyncio
    async def test_clean_observations_not_secure(self, assembler):
        """Clean observations should not trigger secure detection."""
        result = await assembler.assemble(
            query="system status",
            conversation=None,
            observations=["CPU usage: 15%", "Memory: 4GB/16GB"],
            max_tokens=1000,
        )
        assert result.secure is False
