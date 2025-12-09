from __future__ import annotations
import difflib
import subprocess
from typing import Any, Dict, Tuple
from .base import BaseTool, ToolRequest, ToolResponse
from ..obs.audit import write_audit
from ..obs.tracing import trace_call

class ScheduleCron(BaseTool):
    name = "schedule_cron"
    side_effects = True

    @trace_call("schedule_cron.execute")
    def execute(self, req: ToolRequest) -> ToolResponse:
        name = req.inputs.get("name")
        schedule = req.inputs.get("schedule")
        command = req.inputs.get("command")
        if not all([name, schedule, command]):
            return ToolResponse(request_id=req.request_id, ok=False, error="name/schedule/command required", outputs={})
        header = f"# {name}".rstrip()
        line = f"{schedule} {command}".rstrip()
        desired_block = f"{header}\n{line}\n"
        # Build preview and optionally apply
        try:
            before = self._read_crontab()
        except Exception as e:
            before = ""
        after, changed = self._upsert_block(before, header, line)
        diff = self._unified_diff(before, after)
        outputs = {"entry": desired_block, "installed": False, "diff": diff}
        if req.dry_run or not req.confirm:
            write_audit(
                tool=self.name,
                mode="dry_run",
                request_id=req.request_id,
                ok=True,
                summary=f"preview cron entry for {name}",
                name=name,
            )
            return ToolResponse(request_id=req.request_id, ok=True, outputs=outputs)
        # Centralized policy gate for apply path
        allowed, deny = self._policy_check(req)
        is_apply = not (req.dry_run or not req.confirm)
        if not allowed and deny is not None:
            return deny
        # Apply if there is a change
        try:
            if changed:
                self._write_crontab(after)
                outputs["installed"] = True
                write_audit(
                    tool=self.name,
                    mode="apply",
                    request_id=req.request_id,
                    ok=True,
                    summary=f"installed/updated cron entry for {name}",
                    name=name,
                )
            else:
                write_audit(
                    tool=self.name,
                    mode="apply",
                    request_id=req.request_id,
                    ok=True,
                    summary=f"no-op (already present) for {name}",
                    name=name,
                )
            return ToolResponse(request_id=req.request_id, ok=True, outputs=outputs)
        except Exception as e:
            write_audit(
                tool=self.name,
                mode="apply",
                request_id=req.request_id,
                ok=False,
                summary=str(e),
                name=name,
            )
            return ToolResponse(request_id=req.request_id, ok=False, error=str(e), outputs=outputs)

    # Helpers
    def _read_crontab(self) -> str:
        try:
            res = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
        except FileNotFoundError:
            raise RuntimeError("crontab command not found")
        if res.returncode != 0:
            # No crontab for user → treat as empty
            return ""
        return res.stdout

    def _write_crontab(self, text: str) -> None:
        res = subprocess.run(["crontab", "-"], input=text, text=True)
        if res.returncode != 0:
            raise RuntimeError("failed to install crontab")

    def _upsert_block(self, before: str, header: str, line: str) -> Tuple[str, bool]:
        lines = before.splitlines()
        n = len(lines)
        i = 0
        found = False
        while i < n:
            if lines[i].strip() == header:
                found = True
                # Replace the following line (if any) with new line; keep header
                after_lines = lines[:i] + [header, line] + lines[i + 2 :]
                after = "\n".join(after_lines).rstrip() + "\n"
                changed = (after != (before if before.endswith("\n") else before + "\n"))
                return after, changed
            i += 1
        # Not found: append block with separating newline if needed
        sep = "\n" if (before and not before.endswith("\n")) else ""
        after = f"{before}{sep}{header}\n{line}\n"
        return after, True

    def _unified_diff(self, before: str, after: str) -> str:
        a = before.splitlines(keepends=True)
        b = after.splitlines(keepends=True)
        return "".join(difflib.unified_diff(a, b, fromfile="crontab (before)", tofile="crontab (after)"))
