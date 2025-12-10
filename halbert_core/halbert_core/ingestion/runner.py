from __future__ import annotations
import time
from collections import defaultdict, deque
from datetime import datetime
from typing import Any, Deque, Dict, Iterable, List, Optional

import yaml  # type: ignore

from .journald import follow_journal
from .redaction import redact_event
from .jsonl_writer import append_event
from ..index.chroma_index import Index
from .validate import TelemetryValidator
from ..utils.paths import data_subdir, state_subdir
from ..obs.tracing import trace_call


class RateLimiter:
    def __init__(self, per_minute: int) -> None:
        self.per_minute = max(1, per_minute)
        self.buckets: Dict[str, Deque[float]] = defaultdict(deque)

    def allow(self, key: str, now: float) -> bool:
        q = self.buckets[key]
        # Drop events older than 60s
        while q and now - q[0] > 60.0:
            q.popleft()
        if len(q) < self.per_minute:
            q.append(now)
            return True
        return False


@trace_call("ingest.run_journald")
def run_journald(
    ingestion_cfg_path: str,
    base_dir: str | None = None,
    index_persist: str | None = None,
    schema_path: str | None = None,
) -> None:
    """
    Read config, follow journald with filters, apply redaction & rate limits, and write JSONL.
    """
    with open(ingestion_cfg_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    jcfg = (cfg.get("sources") or {}).get("journald") or {}
    if not jcfg.get("enabled", True):
        return
    idents: List[str] = list(jcfg.get("identifiers") or [])
    units: List[str] = list(jcfg.get("units") or [])
    severities: List[str] = list(jcfg.get("severities") or [])
    rate_per_min = int(jcfg.get("rate_limit_per_min") or 60)

    rl = RateLimiter(rate_per_min)
    base_dir = base_dir or data_subdir("raw")
    index_persist = index_persist or data_subdir("index")
    idx = Index(index_persist)
    validator = TelemetryValidator(schema_path)
    cursor_path = state_subdir("journald", "cursor.txt")
    persist_every = int(jcfg.get("cursor_persist_every") or 100)

    for evt in follow_journal({"identifiers": idents, "units": units, "severities": severities}, cursor_path=cursor_path, persist_every=persist_every):
        now = time.time()
        ident = (evt.get("data") or {}).get("identifier") or ""
        sev = evt.get("severity", "info")
        key = f"{ident or 'unknown'}:{sev}"
        if not rl.allow(key, now):
            continue
        red = redact_event(evt)
        if not validator.validate(red):
            continue
        append_event(base_dir, red)
        try:
            idx.upsert_event(red)
        except Exception:
            pass
