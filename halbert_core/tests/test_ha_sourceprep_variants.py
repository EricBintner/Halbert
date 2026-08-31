# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""S2: home automation variants run without SourcePrep retrieval.

(handoff HOME-AUTOMATION-SIMPLIFICATION-2026-08-30, W7-W12) The HA agent
answers from live HA state and conversational context, never a
documentation index, so no SourcePrepAdapter / SourcePrepRetrievalBackend
may be constructed on any wiring path for home:

- the context assembler factories (agent, wired, extended)
- the dashboard agent's SEARCHING-state rag_service
- the haloysius app seam (wired with skip_retrieval=True)
- the /home/config-search HTTP surface (retired outright)

The sysadmin variant keeps the full SourcePrep wiring.
"""

from unittest.mock import MagicMock

import pytest

from halbert_core.integrations import cognition_wiring


@pytest.fixture
def variant(monkeypatch, capability_registry):
    """Controllable variant behind every consumer's resolution chain.

    Patched at cognition_wiring._get_variant — the single source backend
    gating uses (being.yml > HALBERT_VARIANT env > 'sysadmin') — so each
    consumer's lazy lookup is exercised for real.

    F5: gating now reads the capability registry, not the variant
    directly. The holder syncs writes into the isolated registry (probes
    off, preset-driven), so sysadmin wires SourcePrep and home does not —
    the exact matrix this file pins — on any machine, regardless of
    whether this developer's venv can import sourceprep.
    """

    class _VariantHolder(dict):
        """A variant holder whose writes the capability registry follows."""

        def __init__(self):
            super().__init__(variant="sysadmin")
            self.registry = None

        def __setitem__(self, key, value):
            super().__setitem__(key, value)
            if key == "variant" and self.registry is not None:
                self.registry.set_variant(value)

    holder = _VariantHolder()
    monkeypatch.setattr(cognition_wiring, "_get_variant", lambda: holder["variant"])
    capability_registry.set_variant("sysadmin")
    holder.registry = capability_registry
    return holder


# ── Assembler factories ────────────────────────────────────────────────


@pytest.mark.parametrize("ha", ["home"])
def test_agent_assembler_has_no_retrieval_for_home_variants(variant, ha):
    variant["variant"] = ha
    from halbert_core.context import create_agent_context_assembler

    assembler = create_agent_context_assembler()
    assert assembler.retrieval is None
    # The other agent-path sources keep wiring — only retrieval is gated.
    assert assembler.discovery is not None
    assert assembler.memory is None  # R9 fence, unchanged


def test_agent_assembler_wires_sourceprep_for_sysadmin(variant):
    from halbert_core.context import create_agent_context_assembler
    from halbert_core.context.adapters import SourcePrepAdapter

    assembler = create_agent_context_assembler()
    assert isinstance(assembler.retrieval, SourcePrepAdapter)


@pytest.mark.parametrize("ha", ["home"])
def test_wired_assembler_has_no_retrieval_for_home_variants(variant, ha):
    variant["variant"] = ha
    from halbert_core.context import create_wired_context_assembler

    assembler = create_wired_context_assembler()
    assert assembler.retrieval is None
    assert assembler.memory is not None


def test_wired_assembler_wires_sourceprep_for_sysadmin(variant):
    from halbert_core.context import create_wired_context_assembler
    from halbert_core.context.adapters import SourcePrepAdapter

    assembler = create_wired_context_assembler()
    assert isinstance(assembler.retrieval, SourcePrepAdapter)


@pytest.mark.parametrize("ha", ["home"])
def test_extended_assembler_has_no_retrieval_for_home_variants(variant, ha):
    variant["variant"] = ha
    from halbert_core.context.extra_adapters import create_extended_context_assembler

    assembler = create_extended_context_assembler()
    assert assembler.retrieval is None


def test_extended_assembler_wires_sourceprep_for_sysadmin(variant):
    from halbert_core.context.extra_adapters import create_extended_context_assembler
    from halbert_core.context.adapters import SourcePrepAdapter

    assembler = create_extended_context_assembler()
    assert isinstance(assembler.retrieval, SourcePrepAdapter)


@pytest.mark.parametrize("ha", ["home"])
def test_retrieval_adapter_factory_returns_none_for_home_variants(variant, ha):
    """The backend must not be constructed at all — absence of a URL is
    not a mechanism; the gate is the only thing keeping it off an HA node."""
    variant["variant"] = ha
    from halbert_core.context.adapters import retrieval_adapter_for_variant

    assert retrieval_adapter_for_variant() is None


def test_retrieval_adapter_factory_constructs_for_sysadmin(variant):
    from halbert_core.context.adapters import SourcePrepAdapter, retrieval_adapter_for_variant

    assert isinstance(retrieval_adapter_for_variant(), SourcePrepAdapter)


# ── Dashboard agent (SEARCHING-state rag_service) ──────────────────────


def _agent_routes(monkeypatch):
    """Import agent routes with the heavyweight cognition wiring mocked out.

    Same pattern as test_agent_integration.py's
    test_get_agent_uses_sourceprep_for_searching.
    """
    from halbert_core.dashboard.routes import agent as agent_routes

    monkeypatch.setattr(agent_routes, "_agent_instance", None)
    monkeypatch.setattr(agent_routes, "_get_llm_client", lambda: MagicMock())
    monkeypatch.setattr(
        "halbert_core.integrations.cognition_wiring.get_cognition_tick",
        lambda: None,
    )
    monkeypatch.setattr(
        "halbert_core.integrations.cognition_wiring.get_event_mapper",
        lambda: None,
    )
    return agent_routes


@pytest.mark.asyncio
@pytest.mark.parametrize("ha", ["home"])
async def test_get_agent_has_no_rag_service_for_home_variants(monkeypatch, variant, ha):
    variant["variant"] = ha
    agent_routes = _agent_routes(monkeypatch)

    agent = agent_routes.get_agent()
    try:
        assert agent.rag is None
        assert agent.context.retrieval is None
    finally:
        monkeypatch.setattr(agent_routes, "_agent_instance", None)


@pytest.mark.asyncio
async def test_get_agent_wires_sourceprep_for_sysadmin(monkeypatch, variant):
    from halbert_core.context.adapters import SourcePrepAdapter

    agent_routes = _agent_routes(monkeypatch)

    agent = agent_routes.get_agent()
    try:
        assert isinstance(agent.rag, SourcePrepAdapter)
        assert isinstance(agent.context.retrieval, SourcePrepAdapter)
    finally:
        monkeypatch.setattr(agent_routes, "_agent_instance", None)


# ── Haloysius app seam ─────────────────────────────────────────────────


@pytest.mark.parametrize("ha", ["home"])
def test_app_seam_wiring_skips_retrieval_for_home_variants(monkeypatch, variant, ha):
    pytest.importorskip("haloysius")
    import haloysius.seam as hs
    import halbert_core.integrations.app_seam as app_seam

    calls = {}

    def fake_wire(**kwargs):
        calls.update(kwargs)
        return None

    monkeypatch.setattr(hs, "get_app_seam", lambda: None)
    monkeypatch.setattr(app_seam, "wire_halbert_seam", fake_wire)
    variant["variant"] = ha

    cognition_wiring._ensure_app_seam_wired()
    assert calls, "the seam must have been wired"
    assert calls["skip_retrieval"] is True


def test_app_seam_wiring_keeps_retrieval_for_sysadmin(monkeypatch, variant):
    pytest.importorskip("haloysius")
    import haloysius.seam as hs
    import halbert_core.integrations.app_seam as app_seam

    calls = {}

    def fake_wire(**kwargs):
        calls.update(kwargs)
        return None

    monkeypatch.setattr(hs, "get_app_seam", lambda: None)
    monkeypatch.setattr(app_seam, "wire_halbert_seam", fake_wire)

    cognition_wiring._ensure_app_seam_wired()
    assert calls, "the seam must have been wired"
    assert calls["skip_retrieval"] is False


# ── Retired HTTP surface ───────────────────────────────────────────────


def test_home_router_has_no_config_search_endpoints():
    """S2 retired /home/config-search and /home/config-search/status —
    config-search is HA-specific and HA variants have no SourcePrep, so
    the endpoints must not exist for any variant."""
    from halbert_core.dashboard.routes import home

    paths = {getattr(route, "path", None) for route in home.router.routes}
    assert "/home/config-search" not in paths
    assert "/home/config-search/status" not in paths


def test_ha_config_tools_module_is_retired():
    """register_ha_config_tools was never called in production (agent.py
    registers only register_ha_tools); the dead module was deleted."""
    import importlib.util

    spec = importlib.util.find_spec(
        "halbert_core.integrations.home_assistant.ha_config_tools"
    )
    assert spec is None