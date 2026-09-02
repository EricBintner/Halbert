# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Web search is a real switch, off by default (C3-08, C3-16, C3-21).

The setting lives in web_search.yml (``web_search.enabled``); the
capability registry exposes it as CAP_WEB (being.yml ``capabilities:
{web: ...}`` overrides it like every other capability); the executor
offers the ``web_search`` tool to the model only when the capability is
on; the handler refuses when it is off; and the safety framework classes
it as egress (MEDIUM), not SAFE.
"""
from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from halbert_core import capabilities as caps
from halbert_core.capabilities import (
    ALL_CAPABILITIES,
    CAP_WEB,
    _PRESET_HOME,
    _PRESET_SYSADMIN,
    _PROBES,
    _probe_web,
)
from halbert_core.web import search_config


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def web_config_dir(monkeypatch, tmp_path):
    """Point the web-search config at an empty temp user dir and an empty
    template dir, so neither the developer's real config nor the repo's
    template leaks into a test."""
    user = tmp_path / "user"
    template = tmp_path / "repo" / "config" / "web_search.yml"
    monkeypatch.setattr(search_config, "user_config_path", lambda: user / "web_search.yml")
    monkeypatch.setattr(search_config, "template_config_path", lambda: template)
    return user


# ---------------------------------------------------------------------------
# search_config: the one home for the setting
# ---------------------------------------------------------------------------

class TestSearchConfig:
    def test_missing_file_means_off(self, web_config_dir):
        assert search_config.is_enabled() is False

    def test_reads_enabled_from_user_file(self, web_config_dir):
        web_config_dir.mkdir(parents=True)
        (web_config_dir / "web_search.yml").write_text("web_search:\n  enabled: true\n")
        assert search_config.is_enabled() is True

    def test_only_a_real_boolean_true_counts(self, web_config_dir):
        web_config_dir.mkdir(parents=True)
        (web_config_dir / "web_search.yml").write_text("web_search:\n  enabled: 'yes'\n")
        assert search_config.is_enabled() is False

    def test_falls_back_to_template_when_no_user_file(self, web_config_dir, monkeypatch):
        template = search_config.template_config_path()
        template.parent.mkdir(parents=True)
        template.write_text("web_search:\n  enabled: true\n")
        assert search_config.is_enabled() is True

    def test_user_file_wins_over_template(self, web_config_dir):
        template = search_config.template_config_path()
        template.parent.mkdir(parents=True)
        template.write_text("web_search:\n  enabled: true\n")
        web_config_dir.mkdir(parents=True)
        (web_config_dir / "web_search.yml").write_text("web_search:\n  enabled: false\n")
        assert search_config.is_enabled() is False

    def test_unreadable_yaml_means_off(self, web_config_dir):
        web_config_dir.mkdir(parents=True)
        (web_config_dir / "web_search.yml").write_text("web_search: [unclosed\n")
        assert search_config.is_enabled() is False

    def test_set_enabled_round_trips_and_writes_user_file(self, web_config_dir):
        path = search_config.set_enabled(True)
        assert path == web_config_dir / "web_search.yml"
        assert path.exists()
        assert search_config.is_enabled() is True
        search_config.set_enabled(False)
        assert search_config.is_enabled() is False

    def test_set_enabled_preserves_other_settings(self, web_config_dir):
        web_config_dir.mkdir(parents=True)
        (web_config_dir / "web_search.yml").write_text(
            "web_search:\n  enabled: false\n  searxng:\n    timeout: 7\n"
        )
        search_config.set_enabled(True)
        import yaml
        raw = yaml.safe_load((web_config_dir / "web_search.yml").read_text())
        assert raw["web_search"]["enabled"] is True
        assert raw["web_search"]["searxng"]["timeout"] == 7

    def test_set_enabled_seeds_from_template_when_no_user_file(self, web_config_dir):
        template = search_config.template_config_path()
        template.parent.mkdir(parents=True)
        template.write_text("web_search:\n  enabled: false\n  cache:\n    ttl_hours: 3\n")
        search_config.set_enabled(True)
        import yaml
        raw = yaml.safe_load((web_config_dir / "web_search.yml").read_text())
        assert raw["web_search"]["enabled"] is True
        assert raw["web_search"]["cache"]["ttl_hours"] == 3
        # The template itself is never written.
        assert yaml.safe_load(template.read_text())["web_search"]["enabled"] is False

    def test_repo_template_is_off_by_default(self):
        """config/web_search.yml ships with enabled: false — the marketing
        claim 'off by default' has to be true on a fresh checkout."""
        import yaml
        template = search_config.template_config_path()
        assert template.exists(), template
        raw = yaml.safe_load(template.read_text())
        assert raw["web_search"]["enabled"] is False


# ---------------------------------------------------------------------------
# Capability: CAP_WEB, preset off everywhere, probe reads the yaml
# ---------------------------------------------------------------------------

class TestCapWeb:
    def test_cap_web_is_registered(self):
        assert CAP_WEB == "web"
        assert CAP_WEB in ALL_CAPABILITIES

    def test_preset_off_for_every_variant(self):
        assert _PRESET_SYSADMIN[CAP_WEB] is False
        assert _PRESET_HOME[CAP_WEB] is False

    def test_probe_is_wired(self):
        assert _PROBES[CAP_WEB] is _probe_web

    def test_probe_reads_yaml(self, web_config_dir):
        assert _probe_web() is False
        web_config_dir.mkdir(parents=True)
        (web_config_dir / "web_search.yml").write_text("web_search:\n  enabled: true\n")
        assert _probe_web() is True

    def test_registry_off_by_default(self, web_config_dir):
        reg = caps.CapabilityRegistry()
        reg._load_config = lambda: ("sysadmin", {})
        assert reg.has(CAP_WEB) is False

    def test_registry_on_when_yaml_enables_it(self, web_config_dir):
        web_config_dir.mkdir(parents=True)
        (web_config_dir / "web_search.yml").write_text("web_search:\n  enabled: true\n")
        reg = caps.CapabilityRegistry()
        reg._load_config = lambda: ("home", {})
        assert reg.has(CAP_WEB) is True

    def test_being_override_wins_over_yaml(self, web_config_dir):
        web_config_dir.mkdir(parents=True)
        (web_config_dir / "web_search.yml").write_text("web_search:\n  enabled: true\n")
        reg = caps.CapabilityRegistry()
        reg._load_config = lambda: ("sysadmin", {CAP_WEB: False})
        assert reg.has(CAP_WEB) is False


# ---------------------------------------------------------------------------
# Executor: the tool is offered to the model only when the switch is on
# ---------------------------------------------------------------------------

def _schema_names(executor):
    return {s["function"]["name"] for s in executor.get_schemas()}


class TestExecutorGate:
    def test_not_registered_when_capability_off(self, capability_registry):
        from halbert_core.tools import ToolExecutor
        capability_registry.set_capability(CAP_WEB, False)
        ex = ToolExecutor()
        assert "web_search" not in ex.tools
        assert "web_search" not in _schema_names(ex)

    def test_registered_when_capability_on(self, capability_registry):
        from halbert_core.tools import ToolExecutor
        capability_registry.set_capability(CAP_WEB, True)
        ex = ToolExecutor()
        assert "web_search" in ex.tools
        assert "web_search" in _schema_names(ex)

    def test_off_by_default_with_no_config(self, web_config_dir):
        """A fresh install (no web_search.yml, template off) never offers the tool."""
        from halbert_core.tools import ToolExecutor
        reg = caps.CapabilityRegistry()
        reg._load_config = lambda: ("sysadmin", {})
        with patch.object(caps, "_registry", reg):
            ex = ToolExecutor()
        assert "web_search" not in ex.tools

    def test_explicit_flag_overrides_capability(self, capability_registry):
        from halbert_core.tools import ToolExecutor
        capability_registry.set_capability(CAP_WEB, False)
        assert "web_search" in ToolExecutor(web_search=True).tools
        capability_registry.set_capability(CAP_WEB, True)
        assert "web_search" not in ToolExecutor(web_search=False).tools

    def test_sync_follows_the_switch_at_runtime(self, capability_registry):
        from halbert_core.tools import ToolExecutor
        capability_registry.set_capability(CAP_WEB, False)
        ex = ToolExecutor()
        assert "web_search" not in ex.tools

        capability_registry.set_capability(CAP_WEB, True)
        assert ex.sync_web_search_tool() is True
        assert "web_search" in ex.tools and "web_search" in _schema_names(ex)

        capability_registry.set_capability(CAP_WEB, False)
        assert ex.sync_web_search_tool() is False
        assert "web_search" not in ex.tools and "web_search" not in _schema_names(ex)

    def test_other_builtins_unaffected(self, capability_registry):
        from halbert_core.tools import ToolExecutor
        capability_registry.set_capability(CAP_WEB, False)
        names = _schema_names(ToolExecutor())
        assert {"run_command", "read_file", "list_directory"} <= names

    def test_execute_when_off_is_unknown_tool(self, capability_registry):
        from halbert_core.tools import ToolExecutor
        capability_registry.set_capability(CAP_WEB, False)
        result = asyncio.run(ToolExecutor().execute("web_search", {"query": "x"}))
        assert result.success is False
        assert "Unknown tool" in (result.error or "")


# ---------------------------------------------------------------------------
# Handler: defence in depth — refuses without touching the network
# ---------------------------------------------------------------------------

class TestHandlerRefuses:
    def test_refuses_when_capability_off(self, capability_registry):
        from halbert_core.tools import web_search as ws
        capability_registry.set_capability(CAP_WEB, False)

        async def _never(self, *a, **kw):
            raise AssertionError("network search must not run when web search is off")

        with patch.object(ws.WebSearchTool, "search", _never):
            out = asyncio.run(ws.handle_web_search({"query": "latest kernel"}))
        assert out == ws.WEB_SEARCH_OFF_MESSAGE
        assert "off" in out.lower() and "settings" in out.lower()

    def test_runs_when_capability_on(self, capability_registry):
        from halbert_core.tools import web_search as ws
        capability_registry.set_capability(CAP_WEB, True)

        async def _fake(self, query, num_results=None):
            return [ws.SearchResult(title="T", url="https://e.example", snippet="s")]

        with patch.object(ws.WebSearchTool, "search", _fake):
            out = asyncio.run(ws.handle_web_search({"query": "latest kernel"}))
        assert "https://e.example" in out

    def test_executor_path_refuses_when_switched_off_after_registration(self, capability_registry):
        """Registered while on, then switched off without a sync: the
        handler still refuses (the executor gate is not the only guard)."""
        from halbert_core.tools import ToolExecutor
        from halbert_core.tools import web_search as ws
        capability_registry.set_capability(CAP_WEB, True)
        ex = ToolExecutor()
        capability_registry.set_capability(CAP_WEB, False)

        async def _never(self, *a, **kw):
            raise AssertionError("must not search")

        with patch.object(ws.WebSearchTool, "search", _never):
            result = asyncio.run(ex.execute("web_search", {"query": "x"}))
        assert result.success is True
        assert result.result == ws.WEB_SEARCH_OFF_MESSAGE


# ---------------------------------------------------------------------------
# Safety: egress, not SAFE
# ---------------------------------------------------------------------------

class TestSafetyClassification:
    def test_web_search_is_medium_egress(self):
        from halbert_core.tools import RiskLevel, ToolSafetyFramework
        r = ToolSafetyFramework().classify("web_search", {"query": "x"})
        assert r.risk_level == RiskLevel.MEDIUM
        assert r.allowed is True
        assert r.requires_confirmation is False
        assert "leaves" in r.reason.lower() or "egress" in r.reason.lower()

    def test_local_searches_stay_safe(self):
        from halbert_core.tools import RiskLevel, ToolSafetyFramework
        fw = ToolSafetyFramework()
        for name in ("search", "search_discoveries", "recall_memory"):
            assert fw.classify(name, {"query": "x"}).risk_level == RiskLevel.SAFE

    def test_guest_role_is_still_allowed_medium(self):
        """MEDIUM executes without confirmation; a guest is capped at MEDIUM,
        so the switch, not the role, is what keeps query text on the machine."""
        from halbert_core.tools import RiskLevel, ToolSafetyFramework
        from halbert_core.tools.role_gate import RoleGate
        fw = ToolSafetyFramework()
        r = RoleGate(fw).classify("web_search", {"query": "x"}, speaker_role="guest")
        assert r.risk_level == RiskLevel.MEDIUM
        assert r.allowed is True


# ---------------------------------------------------------------------------
# Settings route: GET/PUT round-trip, applies to the live executor
# ---------------------------------------------------------------------------

pytest.importorskip("fastapi")


class TestSettingsRoute:
    def test_get_reports_off_by_default(self, web_config_dir, capability_registry):
        from halbert_core.dashboard.routes import settings as routes
        out = asyncio.run(routes.get_web_search_setting())
        assert out["enabled"] is False
        assert out["effective"] is False
        assert out["path"].endswith("web_search.yml")

    def test_put_round_trips_and_reprobes(self, web_config_dir, monkeypatch):
        from halbert_core.dashboard.routes import settings as routes
        # A real registry (probes on) so the PUT's re-probe is observable.
        reg = caps.CapabilityRegistry()
        reg._load_config = lambda: ("sysadmin", {})
        monkeypatch.setattr(caps, "_registry", reg)
        assert caps.has_capability(CAP_WEB) is False

        out = asyncio.run(routes.update_web_search_setting(routes.WebSearchUpdate(enabled=True)))
        assert out["enabled"] is True
        assert out["effective"] is True
        assert caps.has_capability(CAP_WEB) is True
        assert search_config.is_enabled() is True

        out = asyncio.run(routes.update_web_search_setting(routes.WebSearchUpdate(enabled=False)))
        assert out["enabled"] is False
        assert out["effective"] is False
        assert caps.has_capability(CAP_WEB) is False

    def test_put_reports_being_override(self, web_config_dir, monkeypatch):
        """being.yml capabilities: {web: false} pins it off; the route says so."""
        from halbert_core.dashboard.routes import settings as routes
        reg = caps.CapabilityRegistry()
        reg._load_config = lambda: ("sysadmin", {CAP_WEB: False})
        monkeypatch.setattr(caps, "_registry", reg)
        out = asyncio.run(routes.update_web_search_setting(routes.WebSearchUpdate(enabled=True)))
        assert out["enabled"] is True
        assert out["effective"] is False

    def test_put_syncs_the_live_agent_executor(self, web_config_dir, monkeypatch):
        from halbert_core.dashboard.routes import settings as routes
        from halbert_core.dashboard.routes import agent as agent_routes
        from halbert_core.tools import ToolExecutor

        reg = caps.CapabilityRegistry()
        reg._load_config = lambda: ("sysadmin", {})
        monkeypatch.setattr(caps, "_registry", reg)

        ex = ToolExecutor()
        assert "web_search" not in ex.tools

        class _Agent:
            tools = ex

        monkeypatch.setattr(agent_routes, "_agent_instance", _Agent())
        asyncio.run(routes.update_web_search_setting(routes.WebSearchUpdate(enabled=True)))
        assert "web_search" in ex.tools
        asyncio.run(routes.update_web_search_setting(routes.WebSearchUpdate(enabled=False)))
        assert "web_search" not in ex.tools

    def test_put_without_live_agent_is_fine(self, web_config_dir, monkeypatch):
        from halbert_core.dashboard.routes import settings as routes
        from halbert_core.dashboard.routes import agent as agent_routes
        monkeypatch.setattr(agent_routes, "_agent_instance", None)
        out = asyncio.run(routes.update_web_search_setting(routes.WebSearchUpdate(enabled=True)))
        assert out["enabled"] is True
