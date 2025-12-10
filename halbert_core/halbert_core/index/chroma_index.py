from __future__ import annotations
from typing import Dict, Any, List, Optional, Tuple

"""
ChromaDB-backed index (Phase 1) with safe in-memory fallback.
Collections: self_hwmon, self_journald, self_dbus, self_ebpf, self_knowledge_all
Text for embedding: f"{message} {compact(data)}"; metadata filters per docs.
"""

try:
    import chromadb  # type: ignore
    from chromadb.config import Settings  # type: ignore
except Exception:
    chromadb = None  # type: ignore
    Settings = None  # type: ignore


def _compact_text(event: Dict[str, Any]) -> str:
    msg = str(event.get("message", ""))
    data = event.get("data")
    if isinstance(data, dict):
        parts = []
        for k, v in data.items():
            parts.append(f"{k}={v}")
        return (msg + " " + " ".join(parts)).strip()
    return msg


class _MemoryIndex:
    def __init__(self) -> None:
        self.events: List[Dict[str, Any]] = []

    def upsert(self, *events: Dict[str, Any]) -> None:
        self.events.extend(events)

    def query(self, text: str, k: int = 5) -> List[Dict[str, Any]]:
        return list(reversed(self.events))[:k]


class Index:
    def __init__(self, persist_path: Optional[str] = None) -> None:
        self.mem = _MemoryIndex()
        self.client = None
        self.collections: Dict[str, Any] = {}
        if chromadb is not None:
            try:
                self.client = chromadb.Client(Settings(persist_directory=persist_path) if persist_path else chromadb.Settings())  # type: ignore
            except Exception:
                self.client = None

    def _collection(self, name: str):
        if self.client is None:
            return None
        if name in self.collections:
            return self.collections[name]
        try:
            col = self.client.get_or_create_collection(name=name)  # type: ignore
            self.collections[name] = col
            return col
        except Exception:
            return None

    def upsert_event(self, event: Dict[str, Any]) -> None:
        text = _compact_text(event)
        meta = {k: event.get(k) for k in ("source", "host", "ts", "type", "subsystem", "severity", "tags", "hash")}
        doc_id = event.get("hash") or f"{event.get('source','evt')}:{event.get('ts','')}:{len(text)}"
        src = str(event.get("source", "misc"))
        col_name = {
            "hwmon": "self_hwmon",
            "journald": "self_journald",
            "dbus": "self_dbus",
            "ebpf": "self_ebpf",
        }.get(src, f"self_{src}")

        # Memory fallback
        self.mem.upsert(event)

        # Chroma collections
        for name in (col_name, "self_knowledge_all"):
            col = self._collection(name)
            if col is not None:
                try:
                    col.upsert(ids=[doc_id], documents=[text], metadatas=[meta])  # type: ignore
                except Exception:
                    pass

    def query(self, text: str, k: int = 5) -> List[Dict[str, Any]]:
        # If chroma is available with a global collection, query it; else memory fallback
        col = self._collection("self_knowledge_all")
        if col is not None:
            try:
                res = col.query(query_texts=[text], n_results=k)  # type: ignore
            except Exception:
                res = None
            if res and res.get("metadatas"):
                # Return metadatas; they include fields we stored
                metas = res["metadatas"][0]
                return metas
        return self.mem.query(text, k)
