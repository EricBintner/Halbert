from __future__ import annotations
import json
import os
from typing import Any, Dict, List

from ..index.chroma_index import Index
from ..utils.paths import data_subdir

CANON_DIR = data_subdir("config", "canon")


def _iter_canon_files() -> List[str]:
    if not os.path.isdir(CANON_DIR):
        return []
    files = [os.path.join(CANON_DIR, f) for f in os.listdir(CANON_DIR) if f.endswith('.json')]
    files.sort()
    return files


def _load(path: str) -> Dict[str, Any] | None:
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def index_all(index_persist: str | None = "data/index") -> int:
    """
    Index canonical config records into the vector DB.
    For ini/systemd: index each section/key/value as a document.
    For yaml/json: index top-level keys and values.
    """
    idx = Index(index_persist)
    count = 0
    for jf in _iter_canon_files():
        rec = _load(jf)
        if not rec:
            continue
        path = rec.get('path')
        h = rec.get('hash')
        kind = rec.get('kind')
        # Build events consistent with telemetry event structure for indexing
        base = {
            'source': 'config',
            'host': '',
            'type': 'config_record',
            'subsystem': kind or 'config',
            'severity': 'info',
            'tags': ['config'],
            'hash': h,
        }
        if kind in {'ini'} or 'sections' in rec:
            sections = rec.get('sections', {})
            for sec, kv in sections.items():
                for k, v in kv.items():
                    evt = dict(base)
                    evt['message'] = f"{path} [{sec}] {k} = {v}"
                    evt['data'] = {'path': path, 'section': sec, 'key': k, 'value': v}
                    idx.upsert_event(evt)
                    count += 1
        elif kind in {'yaml', 'json'} and 'tree' in rec:
            tree = rec.get('tree', {})
            if isinstance(tree, dict):
                for k, v in tree.items():
                    evt = dict(base)
                    evt['message'] = f"{path} {k} = {v}"
                    evt['data'] = {'path': path, 'key': k, 'value': v}
                    idx.upsert_event(evt)
                    count += 1
            else:
                evt = dict(base)
                evt['message'] = f"{path} content"
                evt['data'] = {'path': path}
                idx.upsert_event(evt)
                count += 1
        else:
            # text fallback
            evt = dict(base)
            evt['message'] = f"{path} (text file)"
            evt['data'] = {'path': path}
            idx.upsert_event(evt)
            count += 1
    return count
