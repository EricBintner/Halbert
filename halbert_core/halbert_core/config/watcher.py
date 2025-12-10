from __future__ import annotations
import os
import time
from threading import Thread
from typing import Callable, Dict, List, Optional

try:
    from watchdog.observers import Observer  # type: ignore
    from watchdog.events import FileSystemEventHandler  # type: ignore
except Exception:  # pragma: no cover
    Observer = None  # type: ignore
    FileSystemEventHandler = object  # type: ignore

from .manifest import Manifest
from .snapshot import snapshot

Callback = Callable[[List[Dict]], None]


class _Handler(FileSystemEventHandler):  # type: ignore
    def __init__(self, manifest_path: str, on_snapshot: Callback) -> None:
        super().__init__()
        self.manifest_path = manifest_path
        self.on_snapshot = on_snapshot

    def on_modified(self, event):  # type: ignore
        out = snapshot(self.manifest_path)
        self.on_snapshot(out)

    on_created = on_modified
    on_moved = on_modified
    on_deleted = on_modified


class ConfigWatcher:
    def __init__(self, manifest_path: str, on_snapshot: Optional[Callback] = None, interval_s: int = 600) -> None:
        self.manifest_path = manifest_path
        self.on_snapshot = on_snapshot or (lambda x: None)
        self.interval_s = interval_s
        self._observer: Optional[Observer] = None  # type: ignore
        self._thread: Optional[Thread] = None
        self._stop = False

    def start(self) -> None:
        if Observer is None:
            # Fallback polling mode
            self._stop = False
            self._thread = Thread(target=self._poll_loop, daemon=True)
            self._thread.start()
            return

        man = Manifest.from_file(self.manifest_path)
        # Watch unique directories in include globs
        dirs = sorted(set(os.path.dirname(p) or "." for p in man.include))
        handler = _Handler(self.manifest_path, self.on_snapshot)
        self._observer = Observer()  # type: ignore
        for d in dirs:
            if os.path.isdir(d):
                self._observer.schedule(handler, d, recursive=True)  # type: ignore
        self._observer.start()  # type: ignore

    def stop(self) -> None:
        self._stop = True
        if self._observer is not None:
            self._observer.stop()
            self._observer.join()
        if self._thread is not None:
            self._thread.join(timeout=1)

    def _poll_loop(self) -> None:
        while not self._stop:
            out = snapshot(self.manifest_path)
            self.on_snapshot(out)
            time.sleep(self.interval_s)
