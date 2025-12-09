from __future__ import annotations
from typing import Any, Dict, Optional
from pydantic import BaseModel
from ..policy.loader import load_policy
from ..policy.engine import decide
from ..obs.audit import write_audit

"""
Tool interface and envelopes per docs/Phase1/schemas and tool-spec.
"""

class ToolRequest(BaseModel):
    tool: str
    version: Optional[str] = None
    dry_run: bool = False
    confirm: bool = False
    request_id: str
    inputs: Dict[str, Any]


class ToolResponse(BaseModel):
    request_id: str
    ok: bool
    error: Optional[str] = None
    duration_ms: Optional[float] = None
    outputs: Dict[str, Any] = {}
    audit: Dict[str, Any] = {}


class BaseTool:
    name: str = "base"
    side_effects: bool = False

    def execute(self, req: ToolRequest) -> ToolResponse:
        return ToolResponse(request_id=req.request_id, ok=False, error="NotImplemented", outputs={})

    # Centralized policy enforcement for side-effecting apply paths
    def _policy_check(self, req: ToolRequest) -> tuple[bool, Optional[ToolResponse]]:
        """
        Returns (allowed, deny_response). If not allowed, deny_response is a ToolResponse to return.
        Applies only when side_effects=True AND request is confirm & not dry_run.
        """
        is_apply = self.side_effects and not (req.dry_run or not req.confirm)
        if not is_apply:
            return True, None
        try:
            pol = load_policy()
            dec = decide(pol, self.name, is_apply=True, ctx={"inputs": req.inputs})
            if not dec.allow:
                write_audit(tool=self.name, mode="apply", request_id=req.request_id, ok=False, summary=dec.reason)
                return False, ToolResponse(request_id=req.request_id, ok=False, error=dec.reason, outputs={"diff": "", "applied": False})
        except Exception as e:
            # Fail-safe: deny on policy evaluation errors
            msg = f"policy error: {e}"
            write_audit(tool=self.name, mode="apply", request_id=req.request_id, ok=False, summary=msg)
            return False, ToolResponse(request_id=req.request_id, ok=False, error=msg, outputs={"diff": "", "applied": False})
        return True, None
