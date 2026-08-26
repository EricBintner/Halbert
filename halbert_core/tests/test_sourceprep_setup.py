# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for the SourcePrep unified-template apply script (T-H1.2).

Runtime verification against a live daemon is deferred (needs the S1/S2
machinery deployed); these tests pin the apply() contract against a
scripted fake transport: call ordering, idempotency, edge remapping,
the daemon-restart-race config ordering, and legacy retirement gating.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import pytest

from halbert_core.integrations.sourceprep_setup import (
    SourcePrepSetup,
    remap_edges_for_unified_root,
    load_template,
)


TEMPLATE_PATH = (
    Path(__file__).parent.parent
    / "halbert_core" / "integrations" / "sourceprep_template.yml"
)


class FakeTransport:
    """Scripted transport: (method, path) handlers, records every call."""

    def __init__(self) -> None:
        self.calls: List[Tuple[str, str, Any]] = []
        self._handlers: Dict[Tuple[str, str], Callable[[Any, Any], Tuple[int, Dict]]] = {}
        self._pid = "proj-halbert-1"
        self._scopes: Dict[str, Dict[str, Any]] = {}
        self._projects: List[Dict[str, Any]] = []
        self._pipeline_active: Dict[str, List[bool]] = {}
        self._building: List[bool] = []
        self.drop_profiles = False  # simulate a pre-T-S1.4 daemon
        self._bind_defaults()

    # -- scripting helpers --
    def add_project(self, name: str, pid: str) -> str:
        self._projects.append({"id": pid, "name": name, "path": "/x", "config": {}})
        return pid

    def set_scopes(self, scopes: List[Dict[str, Any]]) -> None:
        self._scopes = {s["id"]: s for s in scopes}

    def script_pipeline_active(self, group: str, seq: List[bool]) -> None:
        self._pipeline_active[group] = list(seq)

    # -- transport --
    def __call__(self, method: str, path: str, json_body=None, params=None) -> Tuple[int, Dict[str, Any]]:
        self.calls.append((method, path, json_body))
        handler = self._handlers.get((method, path))
        if handler is None:
            for (m, pat), h in self._handlers.items():
                if m == method and "{" in pat:
                    import re
                    regex = re.sub(r"\{[^}]+\}", "[^/]+", pat)
                    if re.fullmatch(regex, path):
                        return h(json_body, params)
            return 404, {"success": False, "error": {"code": "NOT_FOUND", "message": path}}
        return handler(json_body, params)

    def _bind_defaults(self) -> None:
        def ok(data):
            return {"success": True, "data": data}

        def list_projects(body, params):
            return 200, ok({"projects": list(self._projects)})

        def create_project(body, params):
            pid = self._pid
            self._projects.append({"id": pid, "name": body["name"], "path": body["path"], "config": {}})
            return 200, ok({"project": {"id": pid, "name": body["name"]}})

        def put_project(body, params):
            # find pid from last matching create/list... fake: single unified project
            for p in self._projects:
                if p["id"] == self._pid or p["name"] == "halbert":
                    p["config"] = body.get("config", {})
            return 200, ok({})

        def list_scopes(body, params):
            scopes = []
            for s in self._scopes.values():
                s = dict(s)
                if self.drop_profiles:
                    s.pop("pipeline_profile", None)
                scopes.append(s)
            return 200, ok({"scopes": scopes})

        def create_scope(body, params):
            sid = f"scope-{len(self._scopes)+1}"
            rec = {"id": sid, "display_name": body["display_name"], "paths": []}
            if not self.drop_profiles:
                rec["pipeline_profile"] = body.get("pipeline_profile")
            self._scopes[body["display_name"]] = rec
            return 200, ok(rec)

        def update_scope(body, params, _path=None):
            return 200, ok({})

        def add_paths(body, params):
            return 200, ok({})

        def remove_paths(body, params):
            return 200, ok({})

        def pipeline_start(group):
            def h(body, params):
                seq = self._pipeline_active.setdefault(group, [False])
                return 200, ok({"started": True, "group": group})
            return h

        def pipeline_status(body, params):
            data = {}
            for group in ("fast_sync", "deep_enrichment", "finalize"):
                seq = self._pipeline_active.get(group, [False])
                active = seq.pop(0) if len(seq) > 1 else seq[0]
                data[group] = {"is_active": active, "phase": "completed" if not active else "running"}
            return 200, ok(data)

        def project_status(body, params):
            seq = self._building or [False]
            building = seq.pop(0) if len(seq) > 1 else seq[0]
            return 200, ok({"building": building})

        def build(body, params):
            return 200, ok({"started": True})

        def push_edges(body, params):
            return 200, ok({"accepted": len(body.get("edges", [])), "rejected_unknown": 0})

        def delete_project(body, params):
            return 200, ok({"deleted": True})

        def health(body, params):
            return 200, {"status": "ok"}

        self._handlers = {
            ("GET", "/projects"): list_projects,
            ("POST", "/projects"): create_project,
            ("PUT", "/projects/{pid}"): put_project,
            ("DELETE", "/projects/{pid}"): delete_project,
            ("GET", "/projects/{pid}/scopes"): list_scopes,
            ("POST", "/projects/{pid}/scopes"): create_scope,
            ("PUT", "/projects/{pid}/scopes/{sid}"): update_scope,
            ("POST", "/projects/{pid}/scopes/{sid}/add"): add_paths,
            ("POST", "/projects/{pid}/scopes/{sid}/remove"): remove_paths,
            ("POST", "/projects/{pid}/pipeline/fast"): pipeline_start("fast_sync"),
            ("POST", "/projects/{pid}/pipeline/deep"): pipeline_start("deep_enrichment"),
            ("POST", "/projects/{pid}/pipeline/finalize"): pipeline_start("finalize"),
            ("GET", "/projects/{pid}/pipeline/status"): pipeline_status,
            ("POST", "/projects/{pid}/build"): build,
            ("GET", "/projects/{pid}/status"): project_status,
            ("POST", "/projects/{pid}/trace/external-edges"): push_edges,
            ("GET", "/health"): health,
        }

    def calls_to(self, method: str, suffix: str) -> List[Any]:
        return [body for (m, p, body) in self.calls
                if m == method and p.endswith(suffix)]


# ── Template ────────────────────────────────────────────────────


def test_template_loads_and_has_contract_surface():
    t = load_template(TEMPLATE_PATH)
    assert t["project"]["name"] == "halbert"
    cfg = t["project"]["config"]
    assert cfg["atlas_deep_dirs"] == ["knowledge"]
    assert set(cfg["disabled_stages"]) >= {"rules", "concepts", "audit", "antibodies"}
    assert cfg["auto_config"]["fastSync"] is True
    names = [s["id"] for s in t["scopes"]]
    assert names == ["host", "knowledge-linux", "knowledge-macos",
                     "knowledge-bsd", "knowledge-common"]
    profiles = {s["id"]: s["pipeline_profile"] for s in t["scopes"]}
    assert profiles["host"] == "system_config"
    assert all(v == "prose_docs" for k, v in profiles.items() if k != "host")


# ── Edge remapping ──────────────────────────────────────────────


def test_remap_edges_absolute_to_unified_host_prefix():
    edges = [
        {"source": "file:/etc/ssh/sshd_config",
         "target": "file:/etc/ssh/sshd_config.d/10-local.conf",
         "kind": "includes", "origin": "config"},
        {"source": "file:host/etc/hostname",  # already project-relative
         "target": "file:/etc/hosts", "kind": "references"},
    ]
    out = remap_edges_for_unified_root(edges, host_prefix="host/")
    assert out[0]["source"] == "file:host/etc/ssh/sshd_config"
    assert out[0]["target"] == "file:host/etc/ssh/sshd_config.d/10-local.conf"
    assert out[1]["source"] == "file:host/etc/hostname"  # untouched
    assert out[1]["target"] == "file:host/etc/hosts"


# ── apply() sequencing ──────────────────────────────────────────


@pytest.fixture
def setup(tmp_path):
    transport = FakeTransport()
    s = SourcePrepSetup(
        base_url="http://fake",
        template_path=TEMPLATE_PATH,
        transport=transport,
        project_root_override=tmp_path / "sp-root",
        sleep=lambda *_: None,
    )
    return s, transport, tmp_path


SAMPLE_EDGES = [
    {"source": "file:/etc/ssh/sshd_config",
     "target": "file:/etc/ssh/sshd_config.d/10-local.conf",
     "kind": "includes"},
]


def _stages_host_tree(s: SourcePrepSetup, root: Path):
    """Pretend host/ and knowledge/ are already staged."""
    (root / "host" / "etc").mkdir(parents=True)
    (root / "host" / "etc" / "sshd_config").write_text("Port 22\n")
    (root / "knowledge" / "linux").mkdir(parents=True)


def test_apply_full_sequence_ordering(setup):
    s, transport, tmp_path = setup
    _stages_host_tree(s, tmp_path / "sp-root")
    result = s.apply(stage_host=False, edges=SAMPLE_EDGES)

    # Ordering invariants from the API execution findings:
    post_paths = [(m, p) for (m, p, _) in transport.calls if m == "POST" or m == "PUT"]
    seq = [p for (_m, p) in post_paths]

    def first(suffix):
        for i, p in enumerate(seq):
            if p.endswith(suffix) or suffix in p:
                return i
        raise AssertionError(f"{suffix} never called; sequence: {seq}")

    i_config_first = first("/projects/proj-halbert-1")
    i_fast = first("/pipeline/fast")
    i_edges = first("/trace/external-edges")
    i_deep = first("/pipeline/deep")
    i_finalize = first("/pipeline/finalize")
    assert i_config_first < i_fast < i_edges < i_deep < i_finalize

    # Daemon-restart race: the FIRST config PUT must carry fastSync=false,
    # the LAST must carry fastSync=true.
    puts = [body for (m, p, body) in transport.calls
            if m == "PUT" and p.endswith("proj-halbert-1")]
    assert puts, "no config PUTs recorded"
    assert puts[0]["config"]["auto_config"]["fastSync"] is False
    assert puts[-1]["config"]["auto_config"]["fastSync"] is True

    assert result.get("project_id") == "proj-halbert-1"
    assert result.get("status") == "applied"


def test_apply_creates_scopes_with_profiles_and_paths(setup):
    s, transport, tmp_path = setup
    _stages_host_tree(s, tmp_path / "sp-root")
    s.apply(stage_host=False, edges=SAMPLE_EDGES)

    creates = transport.calls_to("POST", "/scopes")
    assert len(creates) == 5
    names = {c["display_name"] for c in creates}
    assert names == {"host", "knowledge-linux", "knowledge-macos",
                     "knowledge-bsd", "knowledge-common"}
    host_create = next(c for c in creates if c["display_name"] == "host")
    assert host_create.get("pipeline_profile") == "system_config"
    adds = transport.calls_to("POST", "/add")
    assert len(adds) == 5  # one add-paths call per created scope


def test_apply_second_run_is_noop_for_scopes(setup):
    s, transport, tmp_path = setup
    _stages_host_tree(s, tmp_path / "sp-root")
    s.apply(stage_host=False, edges=SAMPLE_EDGES)

    # Daemon now has the scopes; simulate the persisted state.
    n_scope_posts_before = len(transport.calls_to("POST", "/scopes"))
    transport.calls.clear()
    s.apply(stage_host=False, edges=SAMPLE_EDGES)
    assert len(transport.calls_to("POST", "/scopes")) == 0, (
        "second apply created scopes again — reconcile is not idempotent"
    )


def test_apply_up_to_date_pipeline_treated_as_noop(setup):
    s, transport, tmp_path = setup
    _stages_host_tree(s, tmp_path / "sp-root")

    def up_to_date(body, params):
        return 409, {"success": False, "error": {
            "code": "PIPELINE_UP_TO_DATE", "message": "nothing to do"}}

    transport._handlers[("POST", "/projects/{pid}/pipeline/fast")] = up_to_date
    transport._handlers[("POST", "/projects/{pid}/pipeline/deep")] = up_to_date
    transport._handlers[("POST", "/projects/{pid}/pipeline/finalize")] = up_to_date
    result = s.apply(stage_host=False, edges=SAMPLE_EDGES)
    assert result.get("status") == "applied"


def test_fast_sync_only_path_skips_deep_and_finalize(setup):
    s, transport, tmp_path = setup
    _stages_host_tree(s, tmp_path / "sp-root")
    result = s.apply(build_fast_sync_only=True, stage_host=False, edges=SAMPLE_EDGES)
    paths = [p for (_m, p, _) in transport.calls]
    assert any(p.endswith("/pipeline/fast") for p in paths)
    assert not any(p.endswith("/pipeline/deep") for p in paths)
    assert not any(p.endswith("/pipeline/finalize") for p in paths)
    # ConfigWatcher path needs quick retrieval: CodeIndex build IS triggered
    # here (deep_enrichment's auto-trigger doesn't run on this path).
    assert any(p.endswith("/build") for p in paths)
    assert result.get("status") == "applied"


def test_full_apply_does_not_double_embed_codeindex(setup):
    """Full path: deep_enrichment auto-triggers the CodeIndex build; apply
    must NOT do an explicit build first (16K-doc double-embed)."""
    s, transport, tmp_path = setup
    _stages_host_tree(s, tmp_path / "sp-root")
    s.apply(stage_host=False, edges=SAMPLE_EDGES)
    build_calls = [p for (_m, p, _) in transport.calls if p.endswith("/build")]
    assert not build_calls, f"explicit CodeIndex build on full path: {build_calls}"


def test_retire_legacy_projects_only_on_success_and_flag(setup):
    s, transport, tmp_path = setup
    _stages_host_tree(s, tmp_path / "sp-root")
    transport.add_project("halbert-host", "legacy-1")
    transport.add_project("halbert-knowledge", "legacy-2")

    # without flag: no deletes
    s.apply(stage_host=False, edges=SAMPLE_EDGES)
    assert not transport.calls_to("DELETE", "legacy")

    s.apply(stage_host=False, edges=[], retire_legacy_projects=True)
    deletes = [p for (m, p, _) in transport.calls if m == "DELETE"]
    assert any("legacy-1" in p for p in deletes)
    assert any("legacy-2" in p for p in deletes)


def test_apply_warns_when_daemon_drops_pipeline_profile(setup):
    """Pre-T-S1.4 daemon: accepts scope create but silently drops
    pipeline_profile. apply() must surface that instead of trusting it."""
    s, transport, tmp_path = setup
    _stages_host_tree(s, tmp_path / "sp-root")
    transport.drop_profiles = True
    result = s.apply(stage_host=False, edges=SAMPLE_EDGES)
    assert result["scopes"].get("_warning", "").startswith("pipeline_profile not persisted")


def test_apply_daemon_unreachable_returns_skipped(tmp_path):
    def dead_transport(method, path, json_body=None, params=None):
        raise ConnectionError("refused")

    s = SourcePrepSetup(
        base_url="http://dead",
        template_path=TEMPLATE_PATH,
        transport=dead_transport,
        project_root_override=tmp_path / "sp-root",
        sleep=lambda *_: None,
    )
    result = s.apply(stage_host=False, edges=SAMPLE_EDGES)
    assert result.get("status") == "skipped"
    assert "unreachable" in str(result.get("reason", "")).lower()
