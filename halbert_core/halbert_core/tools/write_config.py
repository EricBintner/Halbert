from __future__ import annotations
import configparser
import difflib
import json
import os
import shutil
from io import StringIO
from typing import Any, Dict
from .base import BaseTool, ToolRequest, ToolResponse
from ..obs.audit import write_audit
import yaml  # type: ignore
from ..obs.tracing import trace_call

class WriteConfig(BaseTool):
    name = "write_config"
    side_effects = True

    @trace_call("write_config.execute")
    def execute(self, req: ToolRequest) -> ToolResponse:
        path = req.inputs.get("path")
        changes = req.inputs.get("changes", {})
        backup = bool(req.inputs.get("backup", True))
        do_rollback = bool(req.inputs.get("rollback", False))
        if not path:
            return ToolResponse(request_id=req.request_id, ok=False, error="path required", outputs={})
        # Centralized policy gate for apply path
        allowed, deny = self._policy_check(req)
        is_apply = not (req.dry_run or not req.confirm)
        if not allowed and deny is not None:
            return deny
        try:
            # Rollback branch: restore from <path>.bak
            if do_rollback:
                bak = f"{path}.bak"
                if not os.path.exists(bak):
                    write_audit(tool=self.name, mode="dry_run" if not is_apply else "apply", request_id=req.request_id, ok=False, summary=f"backup not found: {bak}", path=path)
                    return ToolResponse(request_id=req.request_id, ok=False, error=f"backup not found: {bak}", outputs={"diff": "", "applied": False})
                before_txt = ""
                if os.path.exists(path):
                    try:
                        with open(path, "r", encoding="utf-8") as f:
                            before_txt = f.read()
                    except Exception:
                        before_txt = ""
                with open(bak, "r", encoding="utf-8", errors="replace") as f:
                    after_txt = f.read()
                diff = self._unified_diff(before_txt, after_txt, path)
                outputs = {"diff": diff, "applied": False}
                if not is_apply:
                    write_audit(tool=self.name, mode="dry_run", request_id=req.request_id, ok=True, summary=f"preview rollback for {path}", path=path)
                    return ToolResponse(request_id=req.request_id, ok=True, outputs=outputs)
                # Apply rollback
                with open(path, "w", encoding="utf-8") as f:
                    f.write(after_txt)
                write_audit(tool=self.name, mode="apply", request_id=req.request_id, ok=True, summary=f"rollback applied for {path}", path=path)
                outputs["applied"] = True
                return ToolResponse(request_id=req.request_id, ok=True, outputs=outputs)

            lower = str(path).lower()
            if lower.endswith((".yaml", ".yml")):
                preview, applied = self._apply_yaml(path, changes, backup, apply=not (req.dry_run or not req.confirm))
            elif lower.endswith(".json"):
                preview, applied = self._apply_json(path, changes, backup, apply=not (req.dry_run or not req.confirm))
            elif lower.endswith((".ini", ".conf", ".service", ".timer")):
                preview, applied = self._apply_ini(path, changes, backup, apply=not (req.dry_run or not req.confirm))
            else:
                # Text fallback unsupported for apply in Phase 1
                preview = "# Unsupported file type for apply; supported: yaml/json/ini-like\n"
                applied = False
                if not (req.dry_run or not req.confirm):
                    return ToolResponse(request_id=req.request_id, ok=False, error="unsupported file type for apply", outputs={"diff": preview, "applied": False})

            mode = "dry_run" if (req.dry_run or not req.confirm) else "apply"
            ok = True
            summary = ("preview changes for " + path) if mode == "dry_run" else ("applied changes for " + path if applied else "no-op (already up to date) for " + path)
            write_audit(tool=self.name, mode=mode, request_id=req.request_id, ok=ok, summary=summary, path=path)
            return ToolResponse(request_id=req.request_id, ok=True, outputs={"diff": preview, "applied": applied})
        except Exception as e:
            write_audit(tool=self.name, mode="apply" if req.confirm and not req.dry_run else "dry_run", request_id=req.request_id, ok=False, summary=str(e), path=path)
            return ToolResponse(request_id=req.request_id, ok=False, error=str(e), outputs={"diff": "", "applied": False})

    # Helpers
    def _unified_diff(self, before: str, after: str, path: str) -> str:
        a = before.splitlines(keepends=True)
        b = after.splitlines(keepends=True)
        diff = difflib.unified_diff(a, b, fromfile=f"{path} (before)", tofile=f"{path} (after)")
        return "".join(diff)

    def _deep_merge(self, base: Any, changes: Any) -> Any:
        if isinstance(base, dict) and isinstance(changes, dict):
            out = dict(base)
            for k, v in changes.items():
                out[k] = self._deep_merge(base.get(k), v)
            return out
        return changes

    def _apply_yaml(self, path: str, changes: Dict[str, Any], backup: bool, apply: bool) -> tuple[str, bool]:
        before_obj: Dict[str, Any] = {}
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    before_obj = yaml.safe_load(f) or {}
            except Exception:
                before_obj = {}
        after_obj = self._deep_merge(before_obj, changes if isinstance(changes, dict) else {})
        before_txt = yaml.safe_dump(before_obj, sort_keys=False) if before_obj else ""
        after_txt = yaml.safe_dump(after_obj, sort_keys=False)
        diff = self._unified_diff(before_txt, after_txt, path)
        if not apply:
            return diff, False
        if before_txt == after_txt:
            return diff, False
        if backup and os.path.exists(path):
            shutil.copy2(path, f"{path}.bak")
        with open(path, "w", encoding="utf-8") as f:
            f.write(after_txt)
        return diff, True

    def _apply_json(self, path: str, changes: Dict[str, Any], backup: bool, apply: bool) -> tuple[str, bool]:
        before_obj: Any = {}
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    before_obj = json.load(f)
            except Exception:
                before_obj = {}
        if not isinstance(changes, dict):
            raise ValueError("changes must be an object for JSON files")
        after_obj = self._deep_merge(before_obj if isinstance(before_obj, dict) else {}, changes)
        before_txt = json.dumps(before_obj, ensure_ascii=False, indent=2) if before_obj else ""
        after_txt = json.dumps(after_obj, ensure_ascii=False, indent=2)
        diff = self._unified_diff(before_txt, after_txt, path)
        if not apply:
            return diff, False
        if before_txt == after_txt:
            return diff, False
        if backup and os.path.exists(path):
            shutil.copy2(path, f"{path}.bak")
        with open(path, "w", encoding="utf-8") as f:
            f.write(after_txt)
        return diff, True

    def _apply_ini(self, path: str, changes: Dict[str, Any], backup: bool, apply: bool) -> tuple[str, bool]:
        parser = configparser.ConfigParser(interpolation=None)
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    parser.read_file(f)
            except Exception:
                # Start with empty config
                parser = configparser.ConfigParser(interpolation=None)
        before_io = StringIO()
        parser.write(before_io)
        before_txt = before_io.getvalue()
        # Apply changes: expected structure {section: {key: value}}
        if isinstance(changes, dict):
            for section, kv in changes.items():
                if not parser.has_section(section) and section != parser.default_section:
                    parser.add_section(section)
                if isinstance(kv, dict):
                    for k, v in kv.items():
                        parser.set(section, k, str(v))
        after_io = StringIO()
        parser.write(after_io)
        after_txt = after_io.getvalue()
        diff = self._unified_diff(before_txt, after_txt, path)
        if not apply:
            return diff, False
        if before_txt == after_txt:
            return diff, False
        if backup and os.path.exists(path):
            shutil.copy2(path, f"{path}.bak")
        with open(path, "w", encoding="utf-8") as f:
            f.write(after_txt)
        return diff, True
