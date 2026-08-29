# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Zone watcher — ROI-based motion monitoring with event publishing.

Defines rectangular zones of interest on a camera feed and monitors
them for motion. When motion is detected in a zone, publishes a
ProactiveEvent so the cognitive layer can react.

Pairs with:
  - Frigate latest-frame polling (REST) for remote cameras
  - AmbientWebcamMonitor for local webcam
  - BackgroundSubtractor for adaptive motion detection

Usage:
    from halbert_core.vision.zone_watcher import ZoneWatcher, Zone
    watcher = ZoneWatcher(zones=[
        Zone(name="front_door", x=0, y=0, width=640, height=480),
    ])
    watcher.start()
"""

from __future__ import annotations

import asyncio
import base64
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from .motion import BackgroundSubtractor, MotionResult

logger = logging.getLogger("halbert.vision.zone_watcher")


@dataclass
class Zone:
    """A rectangular zone of interest.

    Coordinates are in pixels relative to the source frame.
    """
    name: str
    x: int
    y: int
    width: int
    height: int
    # Minimum motion ratio within the zone to trigger an event.
    # Lower = more sensitive. Default 0.02 (2% of zone area).
    min_motion_ratio: float = 0.02
    # Cooldown in seconds between events for this zone.
    cooldown_seconds: float = 30.0

    @property
    def rect(self) -> Tuple[int, int, int, int]:
        """Return (x1, y1, x2, y2)."""
        return (self.x, self.y, self.x + self.width, self.y + self.height)

    def crop(self, frame: bytes) -> bytes:
        """Crop a JPEG frame to this zone. Returns JPEG bytes.

        Clamps the crop region to the frame bounds. Raises ValueError
        if the zone is entirely outside the frame or the crop is empty.
        """
        import cv2
        import numpy as np
        img_array = np.frombuffer(frame, dtype=np.uint8)
        img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError("Failed to decode frame")

        h, w = img.shape[:2]
        x1 = max(0, self.x)
        y1 = max(0, self.y)
        x2 = min(self.x + self.width, w)
        y2 = min(self.y + self.height, img.shape[0])

        if x2 <= x1 or y2 <= y1:
            raise ValueError(
                f"Zone '{self.name}' is entirely outside the frame "
                f"(zone=({self.x},{self.y},{self.width},{self.height}), "
                f"frame=({w}x{h}))"
            )

        cropped = img[y1:y2, x1:x2]
        success, buf = cv2.imencode(".jpg", cropped)
        if not success or buf is None:
            raise ValueError("Failed to encode cropped frame")
        return buf.tobytes()


@dataclass
class ZoneEvent:
    """A motion event in a zone."""
    zone_name: str
    timestamp: float
    motion_ratio: float
    bounding_boxes: List[Tuple[int, int, int, int]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "zone_name": self.zone_name,
            "timestamp": self.timestamp,
            "motion_ratio": round(self.motion_ratio, 4),
            "bounding_boxes": [list(b) for b in self.bounding_boxes],
        }


class ZoneWatcher:
    """Monitors defined zones for motion using background subtraction.

    Each zone has its own BackgroundSubtractor instance so it learns
    the background independently. Events are published via a callback
    (typically to ProactiveEvent / cognition).
    """

    def __init__(
        self,
        zones: List[Zone],
        frame_source: Callable[[], bytes],
        on_event: Callable[[ZoneEvent], Any],
        interval_seconds: float = 5.0,
    ):
        """
        Args:
            zones: List of Zone definitions.
            frame_source: Callable that returns the current frame as JPEG bytes.
            on_event: Callback for zone motion events. Can be sync or async.
            interval_seconds: Polling interval for frame capture.
        """
        self.zones = {z.name: z for z in zones}
        self.frame_source = frame_source
        self.on_event = on_event
        self.interval = interval_seconds
        self._subtractors: Dict[str, BackgroundSubtractor] = {
            name: BackgroundSubtractor(min_motion_ratio=z.min_motion_ratio)
            for name, z in self.zones.items()
        }
        self._last_event_time: Dict[str, float] = {}
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()  # protects subtractors and _last_event_time

    def start(self) -> None:
        """Start the zone monitoring loop."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._watch_loop, daemon=True,
            name="halbert-zone-watcher",
        )
        self._thread.start()
        logger.info(f"ZoneWatcher started with {len(self.zones)} zones")

    def stop(self) -> None:
        """Stop the zone monitoring loop."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None
        logger.info("ZoneWatcher stopped")

    def _watch_loop(self) -> None:
        """Main loop: capture, crop, detect, publish."""
        while self._running:
            try:
                self._check_all_zones()
            except Exception as e:
                logger.warning(f"ZoneWatcher error: {e}")
            time.sleep(self.interval)

    def _check_all_zones(self) -> None:
        """Capture a frame and check all zones for motion."""
        try:
            frame = self.frame_source()
        except Exception as e:
            logger.debug(f"ZoneWatcher: frame source failed: {e}")
            return

        if not frame:
            return

        for name, zone in self.zones.items():
            self._check_zone(name, zone, frame)

    def _check_zone(self, name: str, zone: Zone, frame: bytes) -> None:
        """Check a single zone for motion. Thread-safe via _lock."""
        try:
            cropped = zone.crop(frame)
        except Exception as e:
            logger.debug(f"ZoneWatcher: crop failed for {name}: {e}")
            return

        with self._lock:
            sub = self._subtractors[name]
            result = sub.process(cropped)

            if not result.has_motion:
                return

            # Cooldown check
            now = time.time()
            last = self._last_event_time.get(name, 0)
            if now - last < zone.cooldown_seconds:
                return

            self._last_event_time[name] = now

        event = ZoneEvent(
            zone_name=name,
            timestamp=now,
            motion_ratio=result.motion_ratio,
            bounding_boxes=result.bounding_boxes,
        )

        try:
            result_cb = self.on_event(event)
            if asyncio.iscoroutine(result_cb):
                loop = asyncio.new_event_loop()
                try:
                    loop.run_until_complete(result_cb)
                finally:
                    loop.close()
        except Exception as e:
            logger.warning(f"ZoneWatcher: callback error for {name}: {e}")

    def check_once(self) -> List[ZoneEvent]:
        """Run a single check of all zones and return any events.

        This is a **peek** — it does NOT invoke the on_event callback
        and does NOT apply cooldown. It's useful for testing and
        one-shot queries. For continuous monitoring with callbacks,
        use start() instead.

        Thread-safe: acquires _lock to avoid concurrent access to
        the BackgroundSubtractor instances from the watch loop.
        """
        events = []
        try:
            frame = self.frame_source()
        except Exception:
            return events

        if not frame:
            return events

        with self._lock:
            for name, zone in self.zones.items():
                try:
                    cropped = zone.crop(frame)
                    sub = self._subtractors[name]
                    result = sub.process(cropped)
                    if result.has_motion:
                        events.append(ZoneEvent(
                            zone_name=name,
                            timestamp=time.time(),
                            motion_ratio=result.motion_ratio,
                            bounding_boxes=result.bounding_boxes,
                        ))
                except Exception:
                    continue
        return events
