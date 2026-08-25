from __future__ import annotations
import logging
import os
import threading
import time
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Deque, Dict, List, Optional

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
        change_callbacks: Optional[List[Callback]] = None,
        max_recent_changes: int = 200,
    ) -> None:
        self.manifest_path = manifest_path
        self.on_snapshot = on_snapshot or (lambda x: None)
        self.interval_s = interval_s
        self.on_change = on_change
        # Composed change callbacks (T5a.2 + T7e.1). The legacy single
        # `on_change` is folded into the same list so both call styles work.
        self._change_callbacks: List[Callback] = []
        if on_change is not None:
            self._change_callbacks.append(on_change)
        if change_callbacks:
            self._change_callbacks.extend(change_callbacks)
        # Rolling recent-changes log (T7d.1): entries {"ts", "path", "kind"}
        self._changes: Deque[Dict[str, Any]] = deque(maxlen=max_recent_changes)
        # Per-path last known state (content hash or "error:<msg>") used to
        # detect real changes between snapshots. The first snapshot is a
        # baseline and records nothing.
        self._last_state: Dict[str, str] = {}
        self._baseline_taken = False
        self._change_lock = threading.Lock()
        self._observer: Optional[Observer] = None  # type: ignore
        self._thread: Optional[threading.Thread] = None
        self._stop = False

    def _handle_change(self, snapshot_result: List[Dict]) -> None:
        self.on_snapshot(snapshot_result)
        self._record_changes(snapshot_result)
        for callback in self._change_callbacks:
            try:
                callback(snapshot_result)
            except Exception as e:
                logger.warning(f"Config change callback failed (non-fatal): {e}")

    def _record_changes(self, snapshot_result: List[Dict]) -> None:
        """Diff this snapshot against the last one and log real changes.

        Entries are timestamped dicts: {"ts", "path", "kind"}. Files that
        disappear from the manifest are recorded with kind="deleted".
        """
        ts = datetime.now(timezone.utc).isoformat()
        with self._change_lock:
            seen: Dict[str, str] = {}
            for row in snapshot_result:
                path = row.get("path")
                if not path:
                    continue
                state = row.get("hash") or (
                    f"error:{row.get('error')}" if row.get("error") else ""
                )
                seen[path] = state
                if not self._baseline_taken:
                    continue
                prev = self._last_state.get(path)
                if prev is None or prev != state:
                    kind = row.get(
                        "kind", "error" if row.get("error") else "unknown"
                    )
                    self._changes.append({"ts": ts, "path": path, "kind": kind})
            if self._baseline_taken:
                for removed in set(self._last_state) - set(seen):
                    self._changes.append(
                        {"ts": ts, "path": removed, "kind": "deleted"}
                    )
            self._last_state = seen
            self._baseline_taken = True

    def get_recent_changes(self, within_hours: float = 24) -> List[Dict[str, Any]]:
        """Return change log entries recorded within the last N hours.

        Oldest first. Entries with unparseable timestamps are skipped.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(hours=within_hours)
        with self._change_lock:
            entries = list(self._changes)
        recent: List[Dict[str, Any]] = []
        for entry in entries:
            try:
                ts = datetime.fromisoformat(str(entry.get("ts", "")))
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                continue
            if ts >= cutoff:
                recent.append(dict(entry))
        return recent

    def start(self) -> None:
        if Observer is None:
            # Fallback polling mode
            self._stop = False
            self._thread = threading.Thread(target=self._poll_loop, daemon=True)
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
# SourcePrep re-index callback (Phase 5 / T5a.2; T-H1.4 unified project)
# ---------------------------------------------------------------------------

def create_sourceprep_reindex_callback(
    project_name: str = "halbert",
    debounce_s: float = 5.0,
) -> Callback:
    """Create a debounced callback that re-stages host config files and
    triggers an incremental SourcePrep rebuild of the unified "halbert"
    project (T-H1.4).

    Replaces the old two-project HostProjectRegistrar.register("halbert-host")
    path: the unified template's apply(build_fast_sync_only=True) re-stages
    host/, runs an incremental fast_sync, and re-pushes the config external
    edges with replace_origin="config". knowledge/ is untouched — the
    changeset gate drops its unchanged doc files, so this never re-embeds
    the doc corpus.

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
            from ..integrations.sourceprep_setup import SourcePrepSetup
            setup = SourcePrepSetup()
            result = setup.apply(build_fast_sync_only=True)
            if result.get("status") == "skipped":
                logger.info(f"SourcePrep re-index skipped: {result.get('reason')}")
            else:
                build = result.get("build", {}) if isinstance(result.get("build"), dict) else {}
                logger.info(
                    f"SourcePrep re-index: project={result.get('project')} "
                    f"fast_sync={build.get('fast_sync', {}).get('status', 'n/a')}"
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
