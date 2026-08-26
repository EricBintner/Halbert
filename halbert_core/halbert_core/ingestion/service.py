"""
Ingestion Service Manager

Manages background ingestion of journald and hwmon events into ChromaDB.
Can be started/stopped via API or CLI.
"""
from __future__ import annotations

import logging
import os
import shutil
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def journald_available() -> bool:
    """True if this host can be followed via journald (Linux with journalctl, or python-systemd)."""
    from ..utils import platform as _platform

    if not _platform.is_linux():
        return False
    try:
        from systemd import journal  # noqa: F401
        return True
    except Exception:
        pass
    return shutil.which("journalctl") is not None


@dataclass
class IngestionStats:
    """Statistics for ingestion service."""
    started_at: Optional[datetime] = None
    journald_events: int = 0
    hwmon_events: int = 0
    last_journald_event: Optional[datetime] = None
    last_hwmon_event: Optional[datetime] = None
    errors: int = 0
    running: bool = False


class IngestionService:
    """
    Background service for continuous telemetry ingestion.
    
    Collects:
    - journald logs (errors, warnings, key services)
    - hwmon sensor readings (temperatures)
    
    Stores in ChromaDB for RAG retrieval.
    """
    
    _instance: Optional['IngestionService'] = None
    _lock = threading.Lock()
    
    def __new__(cls) -> 'IngestionService':
        """Singleton pattern."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._initialized = True
        self._journald_thread: Optional[threading.Thread] = None
        self._hwmon_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self.stats = IngestionStats()
        
        # Find config
        self._config_path = self._find_config()
        logger.info(f"IngestionService initialized (config: {self._config_path})")
    
    def _find_config(self) -> str:
        """Find ingestion config file."""
        candidates = [
            Path.home() / ".config" / "halbert" / "ingestion.yml",
            Path(__file__).parent.parent.parent.parent / "config" / "ingestion.yml",
            Path("/etc/halbert/ingestion.yml"),
        ]
        for p in candidates:
            if p.exists():
                return str(p)
        # Create default config
        default_path = Path.home() / ".config" / "halbert" / "ingestion.yml"
        default_path.parent.mkdir(parents=True, exist_ok=True)
        default_path.write_text("""sources:
  hwmon:
    enabled: true
    interval_s: 30
  journald:
    enabled: true
    severities: [error, warn]
    identifiers: [systemd, kernel, CRON, NetworkManager, sshd]
    units: []
    rate_limit_per_min: 60
    cursor_persist_every: 100
retention:
  raw_days: 14
  index_days: 60
redaction:
  home_paths: true
  emails: true
  ipv4: true
  secrets: true
""")
        return str(default_path)
    
    def _run_journald(self):
        """Background thread for journald ingestion."""
        from .runner import run_journald
        
        logger.info("Starting journald ingestion thread")
        try:
            # run_journald is blocking, but we'll wrap it to check stop event
            from .journald import follow_journal
            from .redaction import redact_event
            from .jsonl_writer import append_event
            from ..index.chroma_index import get_index
            from .validate import TelemetryValidator
            from ..utils.paths import data_subdir, state_subdir
            
            import yaml
            
            with open(self._config_path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
            
            jcfg = (cfg.get("sources") or {}).get("journald") or {}
            if not jcfg.get("enabled", True):
                logger.info("Journald ingestion disabled in config")
                return
            if not journald_available():
                logger.debug("journald ingestion skipped: not a Linux host with journalctl/python-systemd")
                return
            
            from collections import defaultdict, deque
            
            class RateLimiter:
                def __init__(self, per_minute: int):
                    self.per_minute = max(1, per_minute)
                    self.buckets: Dict[str, deque] = defaultdict(deque)
                
                def allow(self, key: str, now: float) -> bool:
                    q = self.buckets[key]
                    while q and now - q[0] > 60.0:
                        q.popleft()
                    if len(q) < self.per_minute:
                        q.append(now)
                        return True
                    return False
            
            idents = list(jcfg.get("identifiers") or [])
            units = list(jcfg.get("units") or [])
            severities = list(jcfg.get("severities") or [])
            rate_per_min = int(jcfg.get("rate_limit_per_min") or 60)
            
            rl = RateLimiter(rate_per_min)
            base_dir = data_subdir("raw")
            idx = get_index()
            validator = TelemetryValidator(None)
            cursor_path = state_subdir("journald", "cursor.txt")
            persist_every = int(jcfg.get("cursor_persist_every") or 100)
            
            for evt in follow_journal(
                {"identifiers": idents, "units": units, "severities": severities},
                cursor_path=cursor_path,
                persist_every=persist_every
            ):
                if self._stop_event.is_set():
                    break
                
                now = time.time()
                ident = (evt.get("data") or {}).get("identifier") or ""
                sev = evt.get("severity", "info")
                key = f"{ident or 'unknown'}:{sev}"
                
                if not rl.allow(key, now):
                    continue
                
                red = redact_event(evt)
                if not validator.validate(red):
                    continue
                
                try:
                    append_event(base_dir, red)
                except Exception as e:
                    logger.debug(f"Failed to write JSONL: {e}")
                
                try:
                    idx.upsert_event(red)
                    self.stats.journald_events += 1
                    self.stats.last_journald_event = datetime.now()
                except Exception as e:
                    logger.debug(f"Failed to index journald event: {e}")
                    self.stats.errors += 1
                    
        except Exception as e:
            logger.error(f"Journald ingestion error: {e}")
            self.stats.errors += 1
        finally:
            logger.info("Journald ingestion thread stopped")
    
    def _run_hwmon(self):
        """Background thread for hwmon ingestion."""
        logger.info("Starting hwmon ingestion thread")
        try:
            from .hwmon import collect_temp
            from .hwmon_runner import discover_temp_sensors
            from .jsonl_writer import append_event
            from ..index.chroma_index import get_index
            from ..utils.paths import data_subdir
            
            import yaml
            
            with open(self._config_path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
            
            hcfg = (cfg.get("sources") or {}).get("hwmon") or {}
            if not hcfg.get("enabled", True):
                logger.info("Hwmon ingestion disabled in config")
                return
            
            interval = int(hcfg.get("interval_s") or 30)
            base_dir = data_subdir("raw")
            idx = get_index()
            
            sensors = discover_temp_sensors()
            if not sensors:
                logger.info("No hwmon sensors found")
                return
            
            logger.info(f"Monitoring {len(sensors)} temperature sensors")
            
            while not self._stop_event.is_set():
                for s in sensors:
                    if self._stop_event.is_set():
                        break
                    
                    evt = collect_temp(s["path"], label=s.get("label"))
                    
                    try:
                        append_event(base_dir, evt)
                    except Exception as e:
                        logger.debug(f"Failed to write JSONL: {e}")
                    
                    try:
                        idx.upsert_event(evt)
                        self.stats.hwmon_events += 1
                        self.stats.last_hwmon_event = datetime.now()
                    except Exception as e:
                        logger.debug(f"Failed to index hwmon event: {e}")
                        self.stats.errors += 1
                
                # Wait with interruptible sleep
                for _ in range(interval):
                    if self._stop_event.is_set():
                        break
                    time.sleep(1)
                    
        except Exception as e:
            logger.error(f"Hwmon ingestion error: {e}")
            self.stats.errors += 1
        finally:
            logger.info("Hwmon ingestion thread stopped")
    
    def start(self) -> bool:
        """Start ingestion threads."""
        if self.stats.running:
            logger.warning("Ingestion already running")
            return False
        
        self._stop_event.clear()
        self.stats.running = True
        self.stats.started_at = datetime.now()
        
        # Start journald thread (Linux with journalctl/python-systemd only)
        if journald_available():
            self._journald_thread = threading.Thread(
                target=self._run_journald,
                name="ingestion-journald",
                daemon=True
            )
            self._journald_thread.start()
        else:
            logger.debug("journald ingestion skipped: not a Linux host with journalctl/python-systemd")
        
        # Start hwmon thread
        self._hwmon_thread = threading.Thread(
            target=self._run_hwmon,
            name="ingestion-hwmon",
            daemon=True
        )
        self._hwmon_thread.start()
        
        logger.info("Ingestion service started")
        return True
    
    def stop(self) -> bool:
        """Stop ingestion threads."""
        if not self.stats.running:
            logger.warning("Ingestion not running")
            return False
        
        self._stop_event.set()
        self.stats.running = False
        
        # Wait for threads to stop (with timeout)
        if self._journald_thread and self._journald_thread.is_alive():
            self._journald_thread.join(timeout=5.0)
        if self._hwmon_thread and self._hwmon_thread.is_alive():
            self._hwmon_thread.join(timeout=5.0)
        
        logger.info("Ingestion service stopped")
        return True
    
    def status(self) -> Dict[str, Any]:
        """Get ingestion status."""
        return {
            "running": self.stats.running,
            "started_at": self.stats.started_at.isoformat() if self.stats.started_at else None,
            "journald_events": self.stats.journald_events,
            "hwmon_events": self.stats.hwmon_events,
            "last_journald_event": self.stats.last_journald_event.isoformat() if self.stats.last_journald_event else None,
            "last_hwmon_event": self.stats.last_hwmon_event.isoformat() if self.stats.last_hwmon_event else None,
            "errors": self.stats.errors,
            "config_path": self._config_path,
        }


def get_ingestion_service() -> IngestionService:
    """Get the singleton ingestion service."""
    return IngestionService()
