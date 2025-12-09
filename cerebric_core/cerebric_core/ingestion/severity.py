from __future__ import annotations

JOURNALD_TO_LEVEL = {
    0: "critical",  # emerg
    1: "critical",  # alert
    2: "critical",  # crit
    3: "error",     # err
    4: "warn",      # warning
    5: "info",      # notice
    6: "info",      # info
    7: "debug",     # debug
}

def map_priority(priority: int | None) -> str:
    if priority is None:
        return "info"
    return JOURNALD_TO_LEVEL.get(int(priority), "info")
