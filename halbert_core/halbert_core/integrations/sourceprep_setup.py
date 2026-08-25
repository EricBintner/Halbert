"""SourcePrep unified-project template apply (T-H1.2).

Applies `sourceprep_template.yml` against a running SourcePrep daemon:
one project ("halbert") over a unified staging root with two scope
families — host/ (system_config profile) and knowledge/{platform}/
(prose_docs profile).

Replaces the two-project split (halbert-host / halbert-knowledge) from
IMPLEMENTATION-PLAN-2026-08-23 T0a.1/T5a.1 — see
.handoff/SOURCEPREP-HALBERT-TEMPLATE-2026-08-24.md and the implementation
plan's "API execution findings" section, which this module encodes:

1. Build steps are ASYNC daemons-side; every step is polled to completion
   before the next begins (else: edges pushed before fast_sync finishes →
   409 TRACE_NOT_BUILT; fast_sync during a CodeIndex build → I/O race).
2. No explicit CodeIndex build on the full-apply path — deep_enrichment
   auto-triggers one with enriched embeddings on completion
   (orchestrator.py:2342). An explicit first build would double-embed the
   16K-doc corpus. The fast-sync-only path (ConfigWatcher) DOES build
   CodeIndex incrementally because deep enrichment doesn't run there.
3. Daemon-restart race: startup auto-runs fast_sync for projects with
   auto_config.fastSync=true + staleness. apply() writes fastSync=false
   up front and flips to true only after the build verifies.

Scopes note (scrutiny §6.5): the scopes API's update endpoint does NOT
accept paths — path mutation is POST /scopes/{id}/add and /remove.
Template scope `id` maps to display_name (daemon assigns real ids);
reconciliation is keyed on display_name.

CLI:
    python -m halbert_core.integrations.sourceprep_setup apply [--no-build]
        [--fast-sync-only] [--retire-legacy-projects] [--base-url URL]
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import yaml

logger = logging.getLogger(__name__)

DEFAULT_TEMPLATE_PATH = Path(__file__).parent / "sourceprep_template.yml"
LEGACY_PROJECT_NAMES = ("halbert-host", "halbert-knowledge")

Transport = Callable[
    [str, str, Optional[Dict[str, Any]], Optional[Dict[str, Any]]],
    Tuple[int, Dict[str, Any]],
]

# Pipeline group name ↔ daemon group key (pipeline/status payload)
_PIPELINE_GROUPS = {
    "fast": "fast_sync",
    "deep": "deep_enrichment",
    "finalize": "finalize",
}


class ApplyError(RuntimeError):
    """A build step failed; apply() aborts before flipping fastSync."""


def load_template(path: Path) -> Dict[str, Any]:
    """Load and minimally validate the template YAML."""
    data = yaml.safe_load(Path(path).read_text())
    if not isinstance(data, dict) or "project" not in data or "scopes" not in data:
        raise ValueError(f"template {path} missing project/scopes sections")
    return data


def remap_edges_for_unified_root(
    edges: List[Dict[str, Any]],
    host_prefix: str = "host/",
) -> List[Dict[str, Any]]:
    """Map Halbert's absolute-path node ids onto the unified project root.

    ConfigEdgeExtractor ids are `file:/etc/...` (live paths). The unified
    project's nodes are root-relative: `file:host/etc/...`. Strip the
    leading slash and prepend the host prefix. Already-root-relative ids
    (no leading slash) pass through untouched.
    """
    out: List[Dict[str, Any]] = []
    for e in edges:
        e = dict(e)
        for key in ("source", "target"):
            nid = e.get(key, "")
            if isinstance(nid, str) and nid.startswith("file:/"):
                e[key] = f"file:{host_prefix}{nid[len('file:/'):]}"
        out.append(e)
    return out


def _requests_transport(base_url: str, timeout: float) -> Transport:
    import requests

    def transport(method, path, json_body=None, params=None):
        resp = requests.request(
            method, f"{base_url}{path}",
            json=json_body, params=params, timeout=timeout,
        )
        try:
            body = resp.json()
        except ValueError:
            body = {"success": False, "error": {"code": "NON_JSON", "message": resp.text[:200]}}
        return resp.status_code, body

    return transport


class SourcePrepSetup:
    """Idempotent applicator for the SourcePrep unified template."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        template_path: Path = DEFAULT_TEMPLATE_PATH,
        transport: Optional[Transport] = None,
        project_root_override: Optional[Path] = None,
        sleep: Callable[[float], None] = time.sleep,
        poll_interval: float = 5.0,
        step_timeout: float = 6 * 3600,
        timeout: float = 60.0,
    ):
        import os

        self.base_url = (
            base_url
            or os.environ.get("SOURCEPREP_URL", "http://localhost:8400")
        ).rstrip("/")
        self.template_path = Path(template_path)
        self.transport = transport or _requests_transport(self.base_url, timeout)
        self.project_root_override = project_root_override
        self.sleep = sleep
        self.poll_interval = poll_interval
        self.step_timeout = step_timeout

    # ── low-level API helpers ─────────────────────────────────

    def _call(
        self,
        method: str,
        path: str,
        body: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        allow_up_to_date: bool = False,
    ) -> Dict[str, Any]:
        """Envelope-unwrapping call. PIPELINE_UP_TO_DATE is a no-op success
        when allow_up_to_date (idempotent re-runs)."""
        status, payload = self.transport(method, path, body, params)
        ok = payload.get("success")
        if ok is None:  # non-envelope endpoints (health)
            if 200 <= status < 300:
                return payload
        if ok:
            return payload.get("data") if "data" in payload else payload
        err = payload.get("error") or {}
        code = err.get("code", f"HTTP_{status}")
        if allow_up_to_date and code == "PIPELINE_UP_TO_DATE":
            return {"up_to_date": True}
        raise ApplyError(f"{method} {path} → {status} {code}: {err.get('message')}")

    def _health_ok(self) -> bool:
        try:
            status, _payload = self.transport("GET", "/api/system/health", None, None)
            return 200 <= status < 300
        except Exception as e:
            logger.info("SourcePrep daemon unreachable at %s: %s", self.base_url, e)
            return False

    # ── template application ──────────────────────────────────

    def apply(
        self,
        build: bool = True,
        build_fast_sync_only: bool = False,
        retire_legacy_projects: bool = False,
        stage_host: bool = True,
        edges: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Apply the template. Safe to re-run; only changed steps do work.

        build_fast_sync_only: ConfigWatcher path (T-H1.4) — re-stage host/,
        incremental fast_sync, refresh external edges, incremental
        CodeIndex build; deep/finalize untouched (changed scope files fail
        the changeset gate for knowledge/, so this never re-embeds docs).
        edges: pre-extracted config edges (absolute file:/... ids — remapped
        here). None → extract via ConfigEdgeExtractor. Extraction failure
        skips the push EXCEPT when an explicit list was provided (explicit
        [] clears origin=config edges — replacement semantics).
        """
        if not self._health_ok():
            return {"status": "skipped", "reason": "daemon unreachable"}

        template = load_template(self.template_path)
        proj_spec = template["project"]
        root = Path(
            self.project_root_override
            or Path(str(proj_spec["root"])).expanduser()
        )
        root.mkdir(parents=True, exist_ok=True)

        result: Dict[str, Any] = {"project": proj_spec["name"], "root": str(root)}

        # 1. Stage host/ (knowledge/ is corpus-conversion output, one-time;
        #    T-H1.1 wires jsonl_to_markdown to write here directly).
        if stage_host:
            staged = self._stage_host_tree(root)
            result["files_staged"] = staged

        # 2. Find-or-create project.
        project = self._find_or_create_project(proj_spec, root)
        pid = project["id"]
        result["project_id"] = pid
        result["created"] = project.get("_created", False)

        # 3. Config PUT #1 — fastSync=false so a daemon restart mid-apply
        #    can't auto-fire fast_sync and race the explicit sequence.
        desired_config = dict(proj_spec["config"])
        self._put_config(pid, desired_config, fast_sync=False)

        # 4. Scope reconciliation (create → add-paths; existing → diff).
        result["scopes"] = self._reconcile_scopes(pid, template["scopes"])

        # 5. Build sequence.
        if build:
            try:
                if build_fast_sync_only:
                    result["build"] = self._build_fast_only(pid, edges)
                else:
                    result["build"] = self._build_full(pid, edges)
            except ApplyError:
                logger.exception("apply: build sequence failed — fastSync stays manual")
                raise

            # 6. Config PUT #2 — flip fastSync to the template's steady
            #    state ONLY after the build verified.
            self._put_config(pid, desired_config, fast_sync=True)
            result["status"] = "applied"
        else:
            self._put_config(pid, desired_config, fast_sync=True)
            result["status"] = "applied" if not build else "configured"
            if not build:
                result["status"] = "configured (no build)"

        # 7. Legacy retirement — explicit flag only, after success.
        if retire_legacy_projects and result.get("status", "").startswith("applied"):
            result["retired"] = self._retire_legacy_projects()

        verify_hint = self._verify_hint(template)
        if verify_hint:
            result["verify_hint"] = verify_hint
        return result

    # ── step implementations ──────────────────────────────────

    def _stage_host_tree(self, root: Path) -> int:
        from ..tools.register_host_project import (
            _os_config_paths,
            _stage_config_files,
        )

        staged = _stage_config_files(_os_config_paths(), root / "host")
        logger.info("Staged %d host config files under %s/host", staged, root)
        return staged

    def _find_or_create_project(
        self, proj_spec: Dict[str, Any], root: Path
    ) -> Dict[str, Any]:
        projects = self._call("GET", "/projects") or {}
        for p in projects.get("projects", []):
            if p.get("name") == proj_spec["name"]:
                return p
        created = self._call("POST", "/projects", {
            "path": str(root),
            "name": proj_spec["name"],
            "mode": proj_spec.get("mode", "standalone"),
        })
        project = created.get("project", created)
        project["_created"] = True
        return project

    def _put_config(self, pid: str, config: Dict[str, Any], fast_sync: bool) -> None:
        cfg = dict(config)
        auto = dict(cfg.get("auto_config") or {})
        auto["fastSync"] = fast_sync
        cfg["auto_config"] = auto
        self._call("PUT", f"/projects/{pid}", {"config": cfg, "touch": True})

    def _reconcile_scopes(
        self, pid: str, wanted: List[Dict[str, Any]]
    ) -> Dict[str, str]:
        """Converge daemon scopes to the template. Keyed on display_name;
        path mutation via add/remove (PUT does not accept paths)."""
        existing = {
            s.get("display_name"): s
            for s in (self._call("GET", f"/projects/{pid}/scopes") or [])
            if s.get("display_name")
        }
        outcomes: Dict[str, str] = {}

        for spec in wanted:
            name = spec["id"]
            paths = [str(p) for p in spec.get("paths", [])]
            profile = spec.get("pipeline_profile")
            rec = existing.get(name)
            if rec is None:
                body: Dict[str, Any] = {"display_name": name, "paths": []}
                if profile:
                    body["pipeline_profile"] = profile
                created = self._call("POST", f"/projects/{pid}/scopes", body)
                sid = created.get("id")
                if paths:
                    self._call("POST", f"/projects/{pid}/scopes/{sid}/add",
                               {"paths": paths})
                current_paths: set = set(paths)
                rec = {"id": sid, "pipeline_profile": created.get("pipeline_profile"),
                       "paths": paths}
                outcomes[name] = "created"
            else:
                sid = rec["id"]
                current_paths = set(rec.get("paths") or [])
                to_add = sorted(set(paths) - current_paths)
                to_remove = sorted(current_paths - set(paths))
                if to_add:
                    self._call("POST", f"/projects/{pid}/scopes/{sid}/add",
                               {"paths": to_add})
                if to_remove:
                    self._call("POST", f"/projects/{pid}/scopes/{sid}/remove",
                               {"paths": to_remove})
                current_paths = set(paths)
                if profile and rec.get("pipeline_profile") != profile:
                    try:
                        self._call("PUT", f"/projects/{pid}/scopes/{sid}",
                                   {"pipeline_profile": profile})
                    except ApplyError as e:
                        logger.warning("scope profile update failed for %s: %s", name, e)
                outcomes[name] = "updated" if (to_add or to_remove) else "unchanged"

        # Verify profiles actually persisted (re-GET once). Pre-T-S1.4
        # daemons silently drop the field — Pydantic ignores extras — so
        # only the round-trip proves support.
        wanted_profiles = {
            s["id"]: s["pipeline_profile"]
            for s in wanted if s.get("pipeline_profile")
        }
        if wanted_profiles:
            final = {
                s.get("display_name"): s
                for s in (self._call("GET", f"/projects/{pid}/scopes") or [])
                if s.get("display_name")
            }
            missing = [
                name for name, prof in wanted_profiles.items()
                if (final.get(name) or {}).get("pipeline_profile") != prof
            ]
            if missing:
                logger.warning(
                    "pipeline_profile not persisted for scopes %s — daemon "
                    "predates T-S1.4; profile gating is inert for this build.",
                    ", ".join(missing),
                )
                outcomes["_warning"] = (
                    f"pipeline_profile not persisted for: {', '.join(missing)}"
                )
        return outcomes

    def _build_fast_only(
        self, pid: str, edges: Optional[List[Dict[str, Any]]]
    ) -> Dict[str, Any]:
        out = {"mode": "fast_sync_only"}
        out["fast_sync"] = self._run_group(pid, "fast")
        out["edges"] = self._push_edges(pid, edges)
        # No deep_enrichment on this path → its CodeIndex auto-trigger never
        # runs; do the incremental embed here (host-scope changes are small).
        out["codeindex"] = self._build_code_index(pid, full=False)
        return out

    def _build_full(
        self, pid: str, edges: Optional[List[Dict[str, Any]]]
    ) -> Dict[str, Any]:
        out = {"mode": "full"}
        out["fast_sync"] = self._run_group(pid, "fast")
        # Edges BEFORE deep: clustering/group_reasoning consume them (C2 fix).
        out["edges"] = self._push_edges(pid, edges)
        out["deep_enrichment"] = self._run_group(pid, "deep")
        # deep completion auto-triggers the enriched CodeIndex build
        # (orchestrator.py:2342). Deliberately NO explicit build first —
        # that would double-embed a 16K-doc corpus. Wait it out.
        out["finalize"] = self._run_group(pid, "finalize")
        self._wait_code_index_idle(pid)
        return out

    def _run_group(self, pid: str, group: str) -> Dict[str, Any]:
        started = self._call(
            "POST", f"/projects/{pid}/pipeline/{group}", {},
            allow_up_to_date=True,
        )
        if started.get("up_to_date"):
            logger.info("%s: pipeline %s already up-to-date", pid, group)
            return {"status": "up_to_date"}
        if not started.get("started", True):
            return {"status": "not_started", "detail": started}

        key = _PIPELINE_GROUPS[group]
        deadline = time.monotonic() + self.step_timeout
        while time.monotonic() < deadline:
            status = self._call("GET", f"/projects/{pid}/pipeline/status") or {}
            st = status.get(key) or {}
            if not st.get("is_active"):
                phase = st.get("phase")
                if phase == "completed":
                    return {"status": "completed"}
                raise ApplyError(
                    f"pipeline {key} ended in phase={phase!r}: "
                    f"{st.get('stage_results')}"
                )
            self.sleep(self.poll_interval)
        raise ApplyError(f"pipeline {key} exceeded timeout {self.step_timeout}s")

    def _build_code_index(self, pid: str, full: bool = False) -> Dict[str, Any]:
        self._call("POST", f"/projects/{pid}/build", params={"full": str(full).lower()})
        self._wait_code_index_idle(pid)
        return {"status": "completed", "full": full}

    def _wait_code_index_idle(self, pid: str) -> None:
        deadline = time.monotonic() + self.step_timeout
        while time.monotonic() < deadline:
            status = self._call("GET", f"/projects/{pid}/status") or {}
            if not status.get("building"):
                return
            self.sleep(self.poll_interval)
        raise ApplyError(f"CodeIndex build for {pid} exceeded timeout")

    def _push_edges(self, pid: str, edges: Optional[List[Dict[str, Any]]]) -> Dict[str, Any]:
        if edges is None:
            try:
                from ..config.edge_extractor import ConfigEdgeExtractor

                extractor = ConfigEdgeExtractor()
                edges = extractor.to_sourceprep_format(extractor.extract_all())
            except Exception as e:
                logger.warning("Config edge extraction failed — skipping push: %s", e)
                return {"status": "skipped", "reason": str(e)}
        remapped = remap_edges_for_unified_root(edges)
        result = self._call(
            "POST", f"/projects/{pid}/trace/external-edges",
            {"edges": remapped, "replace_origin": "config"},
        )
        accepted = result.get("accepted", 0)
        rejected = result.get("rejected_unknown", 0)
        if rejected:
            logger.warning(
                "%d/%d config edges rejected as unknown nodes — "
                "check host/ staging vs edge ids",
                rejected, len(remapped),
            )
        return {"status": "pushed", "edges": len(remapped), "accepted": accepted}

    def _retire_legacy_projects(self) -> List[str]:
        retired: List[str] = []
        projects = self._call("GET", "/projects") or {}
        for p in projects.get("projects", []):
            if p.get("name") in LEGACY_PROJECT_NAMES:
                self._call("DELETE", f"/projects/{p['id']}", params={"purge": "false"})
                retired.append(p["name"])
                logger.info("Retired legacy project %s", p["name"])
        return retired

    @staticmethod
    def _verify_hint(template: Dict[str, Any]) -> Optional[str]:
        for step in template.get("post_build") or []:
            if isinstance(step, dict) and "verify" in step:
                return str(step["verify"])
        return None


def main(argv: Optional[List[str]] = None) -> int:
    import argparse
    import json as _json

    parser = argparse.ArgumentParser(
        prog="halbert_core.integrations.sourceprep_setup",
        description="Apply the SourcePrep unified-project template",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    ap = sub.add_parser("apply", help="Apply the template (idempotent)")
    ap.add_argument("--no-build", action="store_true",
                    help="Configure project+scopes only, no build")
    ap.add_argument("--fast-sync-only", action="store_true",
                    help="ConfigWatcher path: fast_sync + edges + incremental CodeIndex")
    ap.add_argument("--retire-legacy-projects", action="store_true",
                    help="Delete halbert-host / halbert-knowledge after a verified build")
    ap.add_argument("--base-url", default=None)
    ap.add_argument("--template", default=str(DEFAULT_TEMPLATE_PATH))
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    if args.command == "apply":
        setup = SourcePrepSetup(
            base_url=args.base_url, template_path=Path(args.template),
        )
        result = setup.apply(
            build=not args.no_build,
            build_fast_sync_only=args.fast_sync_only,
            retire_legacy_projects=args.retire_legacy_projects,
        )
        print(_json.dumps(result, indent=2))
        return 0 if result.get("status", "").startswith(("applied", "skipped", "configured")) else 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
