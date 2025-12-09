from __future__ import annotations
import os
from typing import Any, Dict
import yaml  # type: ignore
from ..utils.paths import config_dir

DEFAULT_POLICY: Dict[str, Any] = {
    "default_allow": True,
    "tools": {},
}


def load_policy() -> Dict[str, Any]:
    """
    Load policy from <config>/policy.yml if present, else return DEFAULT_POLICY.
    """
    path = os.path.join(config_dir(), "policy.yml")
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                doc = yaml.safe_load(f) or {}
            # Merge with defaults
            pol = dict(DEFAULT_POLICY)
            pol.update({k: v for k, v in (doc or {}).items() if k in ("default_allow", "tools")})
            pol["tools"] = pol.get("tools") or {}
            return pol
    except Exception:
        pass
    return dict(DEFAULT_POLICY)
