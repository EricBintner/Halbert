from __future__ import annotations
import logging
import os
import threading
import time
from typing import Callable, Dict, List, Optional

try:
    from watchdog.observers import Observer  # type: ignore
    from watchdog.events import FileSystemEventHandler  # type: ignore
except Exception:  # pragma: no cover
    Observer = None  # type: ignore
    FileSystemEventHandler = object  # type: ignore

from .manifest import Manifest
from .snapshot import snapshot

logger = logging.getLogger(__name__)

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
    def __init__(
        self,
        manifest_path: str,
        on_snapshot: Optional[Callback] = None,
        interval_s: int = 600,
        on_change: Optional[Callback] = None,
    ) -> None:
        self.manifest_path = manifest_path
        self.on_snapshot = on_snapshot or (lambda x: None)
        self.interval_s = interval_s
        self.on_change = on_change
        self._observer: Optional[Observer] = None  # type: ignore
        self._thread: Optional[Thread] = None
        self._stop = False

    def _handle_change(self, snapshot_result: List[Dict]) -> None:
        self.on_snapshot(snapshot_result)
        if self.on_change:
            self.on_change(snapshot_result)

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
        handler = _Handler(self.manifest_path, self._handle_change)
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
            self._handle_change(out)
            time.sleep(self.interval_s)


# ---------------------------------------------------------------------------
# SourcePrep re-index callback (Phase 5 / T5a.2)
# ---------------------------------------------------------------------------

def create_sourceprep_reindex_callback(
    project_name: str = "halbert-host",
    debounce_s: float = 5.0,
) -> Callback:
    """Create a debounced callback that re-stages config files and triggers
    a SourcePrep rebuild for the halbert-host project.

    Usage:
        watcher = ConfigWatcher(
            manifest_path="config/config-registry.yml",
            on_change=create_sourceprep_reindex_callback(),
        )

    The callback is debounced — rapid successive file changes only trigger
    one re-stage + rebuild after debounce_s seconds of quiet.
    """
    timer: Optional[threading.Timer] = None
    lock = threading.Lock()

    def _do_reindex() -> None:
        try:
            from ..tools.register_host_project import HostProjectRegistrar
            registrar = HostProjectRegistrar()
            result = registrar.register(name=project_name, build=True)
            logger.info(
                f"SourcePrep re-index: staged={result.get('files_staged', 0)}, "
                f"created={result.get('created')}"
            )
        except Exception as e:
            logger.warning(f"SourcePrep re-index failed (non-fatal): {e}")

    def callback(_snapshot_result: List[Dict]) -> None:
        nonlocal timer
        with lock:
            if timer is not None:
                timer.cancel()
            timer = threading.Timer(debounce_s, _do_reindex)
            timer.daemon = True
            timer.start()

    return callback


# ---------------------------------------------------------------------------
# Detector trigger callback (Phase 7 / T7e.1)
# ---------------------------------------------------------------------------

def create_detector_trigger_callback(
    debounce_s: float = 10.0,
) -> Callback:
    """Create a debounced callback that runs all detectors after config changes.

    This runs the detector sweep (drop-in conflicts, fstab phantoms,
    permissions hygiene) and publishes proactive events for any new
    findings, filtered by the ProactiveGate.

    Usage:
        watcher = ConfigWatcher(
            manifest_path="config/config-registry.yml",
            on_change=create_detector_trigger_callback(),
        )

    Debounced separately from the SourcePrep reindex — detectors run
    after a longer quiet period (default 10s) to avoid running on
    every intermediate file write.
    """
    timer: Optional[threading.Timer] = None
    lock = threading.Lock()

    def _do_detect() -> None:
        try:
            from ..proactive.detector_runner import DetectorRunner
            runner = DetectorRunner()
            events = runner.run_all_sync()
            logger.info(f"Detector sweep: {len(events)} events published")
        except Exception as e:
            logger.warning(f"Detector sweep failed (non-fatal): {e}")

    def callback(_snapshot_result: List[Dict]) -> None:
        nonlocal timer
        with lock:
            if timer is not None:
                timer.cancel()
            timer = threading.Timer(debounce_s, _do_detect)
            timer.daemon = True
            timer.start()

    return callback
