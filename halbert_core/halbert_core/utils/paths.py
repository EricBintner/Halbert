from __future__ import annotations
import os
from pathlib import Path
from typing import Optional

"""
Path resolver for FHS/XDG compliance with env overrides.
Priority:
1) Explicit env overrides: Halbert_CONFIG_DIR, Halbert_DATA_DIR, Halbert_LOG_DIR
2) If running as root (uid==0): /etc/halbert, /var/lib/halbert, /var/log/halbert
3) XDG (user scope):
   - CONFIG: $XDG_CONFIG_HOME/halbert or ~/.config/halbert
   - DATA:   $XDG_DATA_HOME/halbert or ~/.local/share/halbert
   - STATE:  $XDG_STATE_HOME/halbert or ~/.local/state/halbert (fallback to DATA)
   - LOGS:   $XDG_STATE_HOME/halbert/log or ~/.local/state/halbert/log
4) Dev fallback: repo-relative 'data' and 'logs' under Halbert_REPO_ROOT if set
"""


def _is_root() -> bool:
    try:
        return os.geteuid() == 0
    except Exception:
        return False


def _env_or(default: str, env_key: str) -> str:
    v = os.environ.get(env_key)
    return v if v else default


def repo_root() -> Optional[str]:
    return os.environ.get("Halbert_REPO_ROOT")


def config_dir() -> str:
    if os.environ.get("Halbert_CONFIG_DIR"):
        return os.environ["Halbert_CONFIG_DIR"]
    if _is_root():
        return "/etc/halbert"
    xdg = os.environ.get("XDG_CONFIG_HOME") or os.path.join(Path.home(), ".config")
    return os.path.join(xdg, "halbert")


def data_dir() -> str:
    if os.environ.get("Halbert_DATA_DIR"):
        return os.environ["Halbert_DATA_DIR"]
    if _is_root():
        return "/var/lib/halbert"
    xdg = os.environ.get("XDG_DATA_HOME") or os.path.join(Path.home(), ".local", "share")
    return os.path.join(xdg, "halbert")


def state_dir() -> str:
    if _is_root():
        return "/var/lib/halbert/state"
    x = os.environ.get("XDG_STATE_HOME") or os.path.join(Path.home(), ".local", "state")
    return os.path.join(x, "halbert")


def log_dir() -> str:
    if os.environ.get("Halbert_LOG_DIR"):
        return os.environ["Halbert_LOG_DIR"]
    if _is_root():
        return "/var/log/halbert"
    # Prefer state dir for logs
    return os.path.join(state_dir(), "log")


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def data_subdir(*parts: str) -> str:
    p = os.path.join(data_dir(), *parts)
    ensure_dir(p)
    return p
def log_subdir(*parts: str) -> str:
    p = os.path.join(log_dir(), *parts)
    ensure_dir(p)
    return p


def state_subdir(*parts: str) -> str:
    p = os.path.join(state_dir(), *parts)
    ensure_dir(p)
    return p
