from __future__ import annotations
import glob
import os
import time
from typing import Dict, List, Optional

import yaml  # type: ignore

from .hwmon import collect_temp
from .jsonl_writer import append_event
from ..index.chroma_index import Index
from ..utils.paths import data_subdir
from ..obs.tracing import trace_call


def discover_temp_sensors() -> List[Dict[str, str]]:
    sensors: List[Dict[str, str]] = []
    for hwmon in glob.glob("/sys/class/hwmon/hwmon*"):
        name_path = os.path.join(hwmon, "name")
        base_name = None
        try:
            with open(name_path, "r") as f:
                base_name = f.read().strip()
        except Exception:
            base_name = None
        for temp_input in glob.glob(os.path.join(hwmon, "temp*_input")):
            label_path = temp_input.replace("_input", "_label")
            label = None
            if os.path.exists(label_path):
                try:
                    with open(label_path, "r") as f:
                        label = f.read().strip()
                except Exception:
                    label = None
            sensors.append({
                "path": temp_input,
                "label": label or base_name or os.path.basename(temp_input),
            })
    return sensors


@trace_call("ingest.run_hwmon")
def run_hwmon(ingestion_cfg_path: str, base_dir: str | None = None, index_persist: str | None = None) -> None:
    with open(ingestion_cfg_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    hcfg = (cfg.get("sources") or {}).get("hwmon") or {}
    if not hcfg.get("enabled", True):
        return
    interval = int(hcfg.get("interval_s") or 10)
    base_dir = base_dir or data_subdir("raw")
    index_persist = index_persist or data_subdir("index")
    idx = Index(index_persist)

    sensors = discover_temp_sensors()
    if not sensors:
        return

    while True:
        for s in sensors:
            evt = collect_temp(s["path"], label=s.get("label"))
            append_event(base_dir, evt)
            try:
                idx.upsert_event(evt)
            except Exception:
                pass
        time.sleep(interval)
