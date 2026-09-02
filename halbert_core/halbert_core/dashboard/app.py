# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
FastAPI dashboard application.

Provides REST API + WebSocket for Halbert dashboard.
"""

from __future__ import annotations
import logging
import json
from typing import List
from pathlib import Path

try:
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import FileResponse
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False

logger = logging.getLogger('halbert.dashboard')

# Phase 23: Global scheduler executor reference
_scheduler_executor = None

# Phase 5+7: Global ConfigWatcher reference (T5a.2 + T7e.1)
_config_watcher = None

# Frigate MQTT subscriber + event mapper (global for shutdown)
_frigate_mqtt_subscriber = None
_frigate_event_mapper = None

# Phase 4: Wyoming voice agent (global for shutdown)
_wyoming_agent = None


def _parse_hhmm(value) -> tuple:
    """Parse an 'HH:MM' string into (hour, minute). Raises ValueError if malformed."""
    if not isinstance(value, str):
        raise ValueError(f"morning_report.time must be a string, got {type(value).__name__}")
    hh, sep, mm = value.partition(":")
    if not sep:
        raise ValueError(f"morning_report.time must be 'HH:MM', got {value!r}")
    hour, minute = int(hh), int(mm)
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"morning_report.time out of range: {value!r}")
    return hour, minute


def _find_config_registry():
    """Locate config/config-registry.yml. Returns a Path or None."""
    candidates = [Path.cwd() / "config" / "config-registry.yml"]
    for parent in Path(__file__).resolve().parents:
        candidates.append(parent / "config" / "config-registry.yml")
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def run_conversation_boot_hooks() -> dict:
    """Plan A boot hooks for the one continuous conversation (spec §8, §12).

    1. Migrate the two legacy JSON conversation stores into the SQLite
       thread store as closed threads (idempotent, counts successful saves).
    2. Mark every message row still ``in_progress`` from a previous process
       as ``interrupted`` so the timeline can render "(Halbert restarted here)".

    Runs synchronously at startup, before the background starters. Never
    raises: a failure here must not stop the dashboard from serving.
    """
    result = {"agent_json": 0, "legacy_json": 0, "interrupted": 0}
    try:
        from ..agents.threads import get_thread_manager
        from ..agents.migrations import migrate_legacy_conversations

        tm = get_thread_manager()
        counts = migrate_legacy_conversations(tm.store)
        result["agent_json"] = int(counts.get("agent_json", 0))
        result["legacy_json"] = int(counts.get("legacy_json", 0))
        try:
            result["interrupted"] = int(tm.mark_interrupted())
        except Exception as e:
            logger.warning(f"Could not mark interrupted turns (non-fatal): {e}")
        logger.info(
            "Conversation boot hooks: migrated %d agent JSON + %d dashboard JSON "
            "conversations, %d interrupted turn(s) marked",
            result["agent_json"], result["legacy_json"], result["interrupted"],
        )
    except Exception as e:
        logger.warning(f"Conversation boot hooks failed (non-fatal): {e}")
    return result


def get_recent_config_changes(within_hours: int = 24) -> list:
    """Recent config changes recorded by the running ConfigWatcher.

    Consumed by MorningReportTask (T7d.1) via attribute lookup — returns
    an empty list when no watcher is running.
    """
    watcher = _config_watcher
    if watcher is None:
        return []
    try:
        return watcher.get_recent_changes(within_hours=within_hours)
    except Exception as e:
        logger.warning(f"Failed to read recent config changes: {e}")
        return []


class ConnectionManager:
    """
    WebSocket connection manager for real-time updates.
    
    Broadcasts events to all connected clients:
    - System status updates
    - New approval requests
    - Job status changes
    - LLM decisions
    """
    
    def __init__(self):
        self.active_connections: List[WebSocket] = []
    
    async def connect(self, websocket: WebSocket):
        """Accept and track new WebSocket connection."""
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket connected. Total connections: {len(self.active_connections)}")
    
    def disconnect(self, websocket: WebSocket):
        """Remove WebSocket connection."""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(f"WebSocket disconnected. Total connections: {len(self.active_connections)}")
    
    async def broadcast(self, message: dict):
        """
        Broadcast message to all connected clients.
        
        Args:
            message: Dict with 'type' and 'data' keys
        """
        disconnected = []
        
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Error sending message to WebSocket: {e}")
                disconnected.append(connection)
        
        # Remove disconnected clients
        for connection in disconnected:
            self.disconnect(connection)
    
    async def send_system_status(self, status: dict):
        """Broadcast system status update."""
        await self.broadcast({
            'type': 'system_status',
            'data': status
        })
    
    async def send_approval_request(self, request: dict):
        """Broadcast new approval request."""
        await self.broadcast({
            'type': 'approval_request',
            'data': request
        })
    
    async def send_job_update(self, job_id: str, status: str, progress: float = None):
        """Broadcast job status update."""
        await self.broadcast({
            'type': 'job_update',
            'data': {
                'job_id': job_id,
                'status': status,
                'progress': progress
            }
        })
    
    async def send_decision(self, decision: dict):
        """Broadcast LLM decision."""
        await self.broadcast({
            'type': 'decision',
            'data': decision
        })
    
    async def send_chat_token(self, request_id: str, token: str, done: bool = False):
        """Stream chat response tokens in real-time."""
        await self.broadcast({
            'type': 'chat_token',
            'data': {
                'request_id': request_id,
                'token': token,
                'done': done
            }
        })
    
    async def send_chat_complete(self, request_id: str, full_response: str, metadata: dict = None):
        """Signal chat response completion."""
        await self.broadcast({
            'type': 'chat_complete',
            'data': {
                'request_id': request_id,
                'response': full_response,
                'metadata': metadata or {}
            }
        })


def create_app(enable_cors: bool = True) -> FastAPI:
    """
    Create FastAPI dashboard application.
    
    Args:
        enable_cors: Enable CORS for local development
    
    Returns:
        Configured FastAPI app
    """
    if not FASTAPI_AVAILABLE:
        raise ImportError("FastAPI not installed. Run: pip install fastapi uvicorn")
    
    app = FastAPI(
        title="Halbert Dashboard",
        description="Web UI for Halbert autonomous IT management",
        version="0.1.1"
    )
    
    # CORS for local development and the Tauri desktop webview.
    # allow_credentials=True forbids the "*" wildcard, so origins are explicit;
    # HALBERT_CORS_ORIGINS (comma-separated) adds more.
    if enable_cors:
        import os
        default_origins = [
            "http://localhost:5173", "http://localhost:3000",   # Vite, CRA
            "tauri://localhost", "http://tauri.localhost",       # Tauri v2 webview
        ]
        extra = []
        for raw in os.environ.get("HALBERT_CORS_ORIGINS", "").split(","):
            origin = raw.strip()
            if not origin:
                continue
            if "*" in origin:
                # A wildcard with allow_credentials=True would let any site
                # make credentialed requests; never honour it.
                logger.warning(
                    "HALBERT_CORS_ORIGINS: ignoring wildcard entry %r (explicit origins only)",
                    origin,
                )
                continue
            extra.append(origin)
        app.add_middleware(
            CORSMiddleware,
            allow_origins=default_origins + extra,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    
    # WebSocket connection manager
    manager = ConnectionManager()
    
    # Store in app state
    app.state.ws_manager = manager
    
    # Register routes
    from .routes import approvals, jobs, memory, settings, system, websocket, persona, discovery, terminal, alerts, rag, services, web_search, gpu, containers, development, editor, storage, downloads, agent, compression, being, modules, llm, legal, compute, vision, home, frigate, instance, peers, fleet, audio, conversations, devices
    
    app.include_router(system.router, prefix="/api", tags=["system"])
    app.include_router(agent.router, tags=["agent"])  # Phase 36: Agent state machine
    app.include_router(approvals.router, prefix="/api/approvals", tags=["approvals"])
    app.include_router(jobs.router, prefix="/api/jobs", tags=["jobs"])
    app.include_router(memory.router, prefix="/api/memory", tags=["memory"])
    app.include_router(settings.router, prefix="/api/settings", tags=["settings"])
    app.include_router(discovery.router, prefix="/api/discoveries", tags=["discoveries"])  # Phase 11
    app.include_router(terminal.router, prefix="/api/terminal", tags=["terminal"])  # Phase 11
    app.include_router(alerts.router, prefix="/api/alerts", tags=["alerts"])  # Phase 11
    app.include_router(rag.router, prefix="/api", tags=["rag"])  # Phase 10
    app.include_router(services.router, prefix="/api/services", tags=["services"])  # Service explanations
    app.include_router(web_search.router, prefix="/api", tags=["web-search"])  # Web grounding
    app.include_router(gpu.router, prefix="/api", tags=["gpu"])  # Phase 14: GPU
    app.include_router(containers.router, prefix="/api", tags=["containers"])  # Phase 15: Containers
    app.include_router(development.router, prefix="/api", tags=["development"])  # Phase 16: Development
    app.include_router(editor.router, tags=["editor"])  # Phase 18: Config Editor
    app.include_router(persona.router, tags=["persona"])  # Phase 4 M3
    app.include_router(websocket.router, tags=["websocket"])
    app.include_router(storage.router, prefix="/api/storage", tags=["storage"])  # Phase 52: ChromaDB management
    app.include_router(downloads.router, prefix="/api/downloads", tags=["downloads"])  # Dataset downloads
    app.include_router(compression.router, tags=["compression"])  # Phase 72: Compression cascade
    app.include_router(being.router, prefix="/api", tags=["being"])  # Phase 7: Proactive channel
    app.include_router(modules.router, prefix="/api", tags=["modules"])  # Phase 8: Module registry
    app.include_router(llm.router, tags=["llm"])  # Unified LLM model picker
    app.include_router(compute.router, tags=["compute"])  # Endpoint capacity probe
    app.include_router(legal.router, tags=["legal"])  # LEG-MOD-01/02: Legal notices & cloud disclosure
    app.include_router(vision.router, prefix="/api", tags=["vision"])  # Screen capture for vision model
    app.include_router(audio.router, prefix="/api", tags=["audio"])  # Auditory cortex
    app.include_router(home.router, prefix="/api", tags=["home"])  # Home Assistant panel
    app.include_router(frigate.router, prefix="/api", tags=["frigate"])  # Frigate NVR panel
    app.include_router(instance.router, tags=["instance"])  # Multi-instance info
    app.include_router(peers.router, tags=["peers"])  # Phase 9.1: Peer pairing
    # prefix="/api": devices.py writes its paths as "/devices/..." (unlike
    # peers.py, which spells "/api/peers/..." into each decorator), so
    # mounting it bare put every route at /devices/* while the frontend and
    # the G12 design both call /api/devices/* — Settings > Devices was a 404
    # from the day it shipped (ROUTE-01 / R10-N1).
    app.include_router(devices.router, prefix="/api", tags=["devices"])  # P7a: Devices page & entity mode
    app.include_router(fleet.router, tags=["fleet"])  # Phase 9.9: Fleet Cockpit
    app.include_router(conversations.router, prefix="/api/conversations", tags=["conversations"])  # P3b: Peer conversation API
    
    # Serve static frontend (production)
    frontend_dist = Path(__file__).parent / "frontend" / "dist"
    if frontend_dist.exists():
        app.mount("/assets", StaticFiles(directory=frontend_dist / "assets"), name="assets")

        # The self-hosted brand typefaces. This mount is load-bearing: the SPA
        # route table below is explicit rather than a catch-all, so without it
        # /fonts/fonts.css 404s and the whole triad silently falls back to
        # system faces in the packaged app — which is the one place a CDN is
        # not available to paper over it.
        fonts_dir = frontend_dist / "fonts"
        if fonts_dir.exists():
            app.mount("/fonts", StaticFiles(directory=fonts_dir), name="fonts")
        else:
            logger.warning(
                "frontend/dist/fonts is missing - run scripts/sync_fonts.py before "
                "building the frontend, or the app will render without its typefaces"
            )

        @app.get("/Halbert.png")
        async def serve_logo():
            """Serve brand logo."""
            return FileResponse(frontend_dist / "Halbert.png")

        @app.get("/")
        async def serve_frontend():
            """Serve React app."""
            return FileResponse(
                frontend_dist / "index.html",
                headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
            )

        # SPA routes - explicit frontend paths only (not a catch-all)
        # This avoids conflicts with API routes
        @app.get("/dashboard")
        @app.get("/terminal")
        @app.get("/services")
        @app.get("/storage")
        @app.get("/gpu")
        @app.get("/containers")
        @app.get("/development")
        @app.get("/network")
        @app.get("/sharing")
        @app.get("/security")
        @app.get("/backups")
        @app.get("/apps")
        @app.get("/approvals")
        @app.get("/settings")
        @app.get("/home")
        async def serve_spa():
            """Serve React app for frontend routes."""
            return FileResponse(
                frontend_dist / "index.html",
                headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
            )

        @app.get("/frigate")
        async def serve_spa_frigate():
            """Serve React app for Frigate panel route."""
            return FileResponse(
                frontend_dist / "index.html",
                headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
            )
    
    # Startup event: auto-start services
    @app.on_event("startup")
    async def startup_event():
        """Start background services on app startup."""
        # Multi-instance identity logging
        import os
        _persona = os.environ.get("HALBERT_PERSONA_ID", "halbert")
        _scene = os.environ.get("HALBERT_SCENE_CONTEXT", "")
        _port = os.environ.get("HALBERT_PORT", "8000")
        _data = os.environ.get("HALBERT_DATA_DIR") or os.environ.get("Halbert_DATA_DIR", "")
        _config = os.environ.get("HALBERT_CONFIG_DIR") or os.environ.get("Halbert_CONFIG_DIR", "")
        logger.info(
            f"Halbert instance starting — persona={_persona}, scene={_scene or '(default)'}, "
            f"port={_port}, data_dir={_data or '(default)'}, config_dir={_config or '(default)'}"
        )

        # Sidecar mode (Tauri sets HALBERT_PARENT_PID): stop when the shell dies.
        try:
            from .parent_watchdog import start_parent_watchdog
            start_parent_watchdog()
        except Exception as e:
            logger.warning(f"Parent watchdog not started: {e}")

        # Reset indexing state to prevent stuck state from hot-reload
        try:
            from .routes.settings import _reset_indexing_state
            _reset_indexing_state()
            logger.info("Indexing state reset on startup")
        except Exception as e:
            logger.warning(f"Failed to reset indexing state: {e}")

        # Plan A: one-time JSON -> SQLite conversation migration, then mark any
        # turn that was in flight when the last process died as interrupted.
        # Synchronous on purpose: the first /api/agent/message must see the
        # migrated threads and no phantom in_progress rows.
        run_conversation_boot_hooks()
        
        # Bootstrap system identity (if not already done)
        try:
            from ..knowledge import get_self_knowledge, bootstrap_identity
            sk = get_self_knowledge()
            if not sk.get_identity():
                logger.info("Bootstrapping system identity...")
                bootstrap_identity()
            else:
                logger.info(f"Self-knowledge loaded: {len(sk._knowledge)} entries")
        except Exception as e:
            logger.warning(f"Failed to bootstrap identity: {e}")
        
        # Start ingestion service in background (non-blocking)
        # Uses daemon threads so won't block shutdown
        # Capability-based gating: a node runs ingestion only if it has
        # the ingestion capability. The variant preset sets defaults
        # (home = no ingestion), but being.yml capabilities: section can
        # override — a Mac Studio with HA configured can do both.
        from ..capabilities import get_capability_registry, CAP_INGESTION, CAP_DISCOVERY, CAP_SCHEDULER, CAP_CONFIG_WATCHER, CAP_SOURCEPREP, CAP_TERMINAL, CAP_HA_CONNECTION, CAP_AUDIO
        _caps = get_capability_registry()
        _caps.probe()
        if not _caps.has(CAP_INGESTION):
            logger.info("Ingestion service skipped (no ingestion capability)")
        else:
            def start_ingestion_delayed():
                """Start ingestion after a short delay to let ChromaDB initialize."""
                import time
                time.sleep(2)  # Wait for ChromaDB to be ready
                try:
                    from ..ingestion.service import get_ingestion_service
                    service = get_ingestion_service()
                    service.start()
                    logger.info("Ingestion service started (journald + hwmon)")
                except Exception as e:
                    logger.warning(f"Failed to start ingestion: {e}")

            import threading
            ingestion_starter = threading.Thread(target=start_ingestion_delayed, daemon=True)
            ingestion_starter.start()
            logger.info("Ingestion service starting in background...")

        # Auto-scan discovery engine on startup so dashboard pages have data
        # without requiring a manual scan click. Runs in a daemon thread after
        # a short delay to avoid competing with ChromaDB/ingestion init.
        # Capability-based: skip if no discovery capability.
        if not _caps.has(CAP_DISCOVERY):
            logger.info("Discovery scan skipped (no discovery capability)")
        else:
            def start_discovery_scan_delayed():
                """Run all discovery scanners in the background on startup."""
                import time
                time.sleep(5)  # Wait for other services to initialize
                try:
                    from ..discovery.engine import get_engine
                    engine = get_engine()
                    discoveries = engine.scan_all()
                    logger.info(f"Startup discovery scan complete: {len(discoveries)} items found")
                except Exception as e:
                    logger.warning(f"Startup discovery scan failed (non-fatal): {e}")

            discovery_starter = threading.Thread(target=start_discovery_scan_delayed, daemon=True)
            discovery_starter.start()
            logger.info("Discovery scan starting in background...")
        
        # Phase 23: Start scheduler (re-enabled with delayed start)
        # Capability-based: skip if no scheduler capability.
        if not _caps.has(CAP_SCHEDULER):
            logger.info("Scheduler skipped (no scheduler capability)")
        else:
            def start_scheduler_delayed():
                """Start scheduler after a short delay."""
                import time
                time.sleep(3)  # Wait for other services to initialize
                try:
                    from ..scheduler.executor import AutonomousExecutor, APSCHEDULER_AVAILABLE
                    if APSCHEDULER_AVAILABLE:
                        global _scheduler_executor
                        # Resolve timezone from being config (default: local system tz)
                        scheduler_tz = 'UTC'
                        try:
                            from ..config.being_config import load_being_config, resolve_timezone
                            being_cfg = load_being_config()
                            scheduler_tz = resolve_timezone(being_cfg.timezone)
                        except Exception:
                            pass  # Fall back to UTC
                        _scheduler_executor = AutonomousExecutor(
                            max_workers=3,
                            enable_llm=False,  # Disable LLM for scheduler jobs
                            enable_guardrails=True,
                            timezone=scheduler_tz,
                        )
                        _scheduler_executor.start()
                        logger.info(f"Scheduler started successfully (timezone: {scheduler_tz})")
                    else:
                        logger.info("APScheduler not available, scheduler disabled")
                except Exception as e:
                    logger.warning(f"Failed to start scheduler: {e}")

            scheduler_starter = threading.Thread(target=start_scheduler_delayed, daemon=True)
            scheduler_starter.start()
            logger.info("Scheduler starting in background...")

            # Phase 7 / T7d.2 + T7e.1: schedule morning report and detector sweep
            def schedule_proactive_jobs_delayed():
                """Register proactive jobs once the scheduler has had time to start."""
                import time
                time.sleep(4)  # after the delayed scheduler start above
                try:
                    executor = _scheduler_executor
                    if executor is None:
                        logger.info("Scheduler not running; proactive jobs not scheduled")
                        return

                    from ..scheduler.autonomous_tasks import create_autonomous_task

                    # T7e.1: scheduled detector sweep every 6 hours
                    try:
                        sweep_task = create_autonomous_task('detector_sweep')
                        executor.schedule_cron_job(
                            job_id='detector_sweep',
                            task_func=lambda: sweep_task.execute({}),
                            cron_expr={'hour': '*/6', 'minute': 12},
                            description='Detector sweep (drop-ins, fstab, permissions)',
                        )
                        logger.info("Detector sweep scheduled every 6 hours")
                    except Exception as e:
                        logger.warning(f"Failed to schedule detector sweep: {e}")

                    # T7d.2: daily morning report per being.yml
                    # Missing / disabled / malformed being.yml → log and skip,
                    # never crash startup.
                    try:
                        from ..config.being_config import load_being_config
                        being_config = load_being_config()
                        report_cfg = being_config.morning_report or {}
                        if not isinstance(report_cfg, dict) or not report_cfg.get('enabled'):
                            logger.info("Morning report disabled or unconfigured; not scheduled")
                            return
                        hour, minute = _parse_hhmm(report_cfg.get('time', '08:00'))
                        report_task = create_autonomous_task('morning_report')
                        executor.schedule_cron_job(
                            job_id='morning_report',
                            task_func=lambda: report_task.execute({}),
                            cron_expr={'hour': hour, 'minute': minute},
                            description='Daily morning report',
                        )
                        logger.info(
                            f"Morning report scheduled daily at {hour:02d}:{minute:02d} {executor.timezone}"
                        )
                    except Exception as e:
                        logger.warning(f"Failed to schedule morning report: {e}")

                    # VisualWatcher: standalone background thread for proactive
                    # screen monitoring. NOT a cron job — cadence is adaptive
                    # (30s-5min), too fast for the cron scheduler. Gated by
                    # both vision_config.yml (system) and being.yml (persona).
                    try:
                        from ..vision.config import is_screen_capture_enabled
                        being_config = load_being_config()
                        if (being_config.senses.vision.enabled
                                and being_config.senses.vision.proactive_monitoring
                                and is_screen_capture_enabled()):
                            from ..vision.watcher import VisualWatcher
                            from ..proactive.gate import ProactiveGate
                            from ..autonomy.guardrails import GuardrailEnforcer
                            from ..findings.store import FindingStore
                            gate = ProactiveGate(
                                being_config=being_config,
                                guardrail_enforcer=GuardrailEnforcer(),
                                finding_store=FindingStore(),
                            )
                            watcher = VisualWatcher(
                                being_config=being_config,
                                gate=gate,
                                finding_store=FindingStore(),
                            )
                            watcher.start()
                            logger.info("VisualWatcher started (proactive screen monitoring)")
                    except Exception as e:
                        logger.warning(f"Failed to start VisualWatcher: {e}")
                except Exception as e:
                    logger.warning(f"Failed to schedule proactive jobs: {e}")

            proactive_starter = threading.Thread(target=schedule_proactive_jobs_delayed, daemon=True)
            proactive_starter.start()

        # Phase 5+7 / T5a.2 + T7e.1: watch host config files (Linux hosts only).
        # The whole thing no-ops gracefully if the platform is unsupported,
        # the manifest is missing/unwatched, or SourcePrep is down.
        # Capability-based: skip if no config_watcher capability.
        if not _caps.has(CAP_CONFIG_WATCHER):
            logger.info("Config watcher skipped (no config_watcher capability)")
        else:
            def start_config_watcher():
                global _config_watcher
                try:
                    from ..utils.platform import is_linux
                    if not is_linux():
                        logger.info("Config watcher not started (Linux hosts only)")
                        return
                    manifest = _find_config_registry()
                    if manifest is None:
                        logger.info("No config-registry.yml found; config watcher not started")
                        return
                    from ..config.watcher import (
                        ConfigWatcher,
                        create_sourceprep_reindex_callback,
                        create_detector_trigger_callback,
                    )
                    change_callbacks = [create_detector_trigger_callback()]
                    # SourcePrep re-index callback only if sourceprep capability
                    if _caps.has(CAP_SOURCEPREP):
                        change_callbacks.insert(0, create_sourceprep_reindex_callback())
                    watcher = ConfigWatcher(
                        manifest_path=str(manifest),
                        change_callbacks=change_callbacks,
                    )
                    watcher.start()
                    _config_watcher = watcher
                    logger.info(f"Config watcher started on {manifest}")
                except Exception as e:
                    logger.warning(f"Config watcher failed to start (non-fatal): {e}")

            start_config_watcher()

        # Terminal session manager (B1b): start the idle/dead session reaper so
        # exited PTY sessions don't permanently exhaust the session cap.
        # Capability-based: skip if no terminal capability.
        if _caps.has(CAP_TERMINAL):
            try:
                from ..streaming.session_manager import get_terminal_manager
                get_terminal_manager().start_reaper()
                logger.info("Terminal session reaper started")
            except Exception as e:
                logger.warning(f"Failed to start terminal session reaper: {e}")

        # Voice mode (O2): audio pipeline coordinator — the dashboard's ears.
        # Capability-gated presence check (config enabled + sherpa-onnx, probed
        # in capabilities.py — never a variant check). being.yml
        # ``capabilities: {audio: false}`` is the operator override. Audio is
        # optional: a coordinator that fails to start leaves the coordinator
        # slot None and the dashboard keeps booting (/api/audio/stream then
        # answers 1013 "try again later").
        app.state.audio_coordinator = None
        if not _caps.has(CAP_AUDIO):
            logger.info("Audio pipeline skipped (no audio capability)")
        else:
            coordinator = None
            # Imported before the try: the handler below calls it, so a
            # failure in one of the audio imports must not turn into a
            # NameError in the cleanup path.
            from .routes.audio import set_audio_pipeline
            try:
                from ..audio.config import load_config as load_audio_config
                from ..audio.pipeline import AudioPipelineCoordinator
                from ..audio.ingress.webrtc_ingress import WebRtcIngress
                coordinator = AudioPipelineCoordinator(config=load_audio_config())
                attached = await coordinator.add_ingress(
                    WebRtcIngress(area_id="dashboard_voice")
                )
                if not attached:
                    logger.warning(
                        "Dashboard audio ingress failed to start — "
                        "/api/audio/stream will answer 1013"
                    )
                await coordinator.start()
                app.state.audio_coordinator = coordinator
                # Publish it where code outside a request can see it. The
                # channel capability asks this to decide whether Halbert has
                # a mouth; until it did, has_speaker() was always False and
                # every downstream voice seam — should_speak(), the TTS
                # egress hook, the speaking state, the HUD relay — was
                # unreachable in production (U2-15 / R9-F05).
                set_audio_pipeline(coordinator)
                logger.info(
                    "Audio pipeline coordinator started "
                    f"(dashboard ingress {'attached' if attached else 'NOT attached'})"
                )
            except Exception as e:
                logger.warning(f"Audio pipeline failed to start (non-fatal): {e}")
                # Best-effort cleanup: start() can raise after the ingress was
                # started or after loop tasks were created (and gains more raise
                # points as it grows, e.g. O3) — stop whatever partially came up
                # so no adapter or task is left orphaned spinning forever.
                if coordinator is not None:
                    try:
                        await coordinator.stop()
                    except Exception as stop_err:
                        logger.debug(f"Coordinator cleanup after failed start: {stop_err}")
                app.state.audio_coordinator = None
                set_audio_pipeline(None)

        # Voice mode: a spoken turn has to reach the page that spoke it.
        #
        # ``on_voice_turn`` was declared on the coordinator and invoked by
        # the speech track, and nothing ever set it — so a completed voice
        # turn produced a VoiceTurnObservation that went nowhere, /voice's
        # "Tap to speak" ended in an empty turn, and the on-screen keyboard
        # was the only working input. The status endpoint deliberately never
        # carries the transcript (it answers who spoke, not what was said),
        # so the return path is the mic uplink the browser is already holding
        # open (VM-STT).
        if app.state.audio_coordinator is not None:
            try:
                _coordinator = app.state.audio_coordinator

                async def _relay_voice_turn(observation) -> None:
                    text = getattr(observation, "text", "") or ""
                    if not text.strip():
                        return
                    ingress = _coordinator.get_ingress("dashboard")
                    if ingress is None or not hasattr(ingress, "broadcast"):
                        return
                    await ingress.broadcast({
                        "type": "transcript",
                        "text": text,
                        "speaker_name": getattr(observation, "speaker_name", ""),
                        "speaker_role": getattr(observation, "speaker_role", "unknown"),
                        "area_id": getattr(observation, "area_id", ""),
                    })

                _coordinator.on_voice_turn = _relay_voice_turn
                logger.info("Voice turn relay wired to the dashboard uplink")
            except Exception as e:
                logger.warning(f"Voice turn relay not wired (non-fatal): {e}")

        # Voice mode (O5): acoustic anomalies ride the findings chain. The
        # bridge sets the coordinator's on_acoustic_event callback; a tagged
        # anomaly then flows AcousticAnomalyDetector -> DetectorRunner ->
        # ProactiveEventBus -> /api/being/events. Strictly optional — the
        # DetectorRunner is built lazily on the first event, and a broken
        # findings stack degrades to a warning-once drop, never a boot
        # failure.
        if app.state.audio_coordinator is not None:
            try:
                from ..proactive.acoustic_bridge import attach_acoustic_bridge
                attach_acoustic_bridge(app.state.audio_coordinator)
            except Exception as e:
                logger.warning(f"Acoustic anomaly bridge attach failed (non-fatal): {e}")

        # Voice mode (O3): TTS egress hub — the dashboard's mouth. A dumb
        # relay from the agent state machine to /api/audio/tts subscribers,
        # deliberately NOT gated on the audio capability: it forwards
        # nothing until a browser subscribes, and only the synthesis (in the
        # state machine hook) needs the audio stack. Aliased onto app.state
        # per the plan; the state machine reaches it through the module
        # singleton (the get_event_bus pattern) because it holds no app ref.
        from .routes.tts_egress import get_tts_egress_hub
        app.state.tts_egress = get_tts_egress_hub()
        # When the pipeline runs, the state machine's TTS hook mints
        # coordinator-owned barge-in tokens through this reference (so VAD
        # barge-in cancels browser playback too); without it the hook falls
        # back to a standalone token.
        app.state.tts_egress.set_pipeline(app.state.audio_coordinator)

        # Phase 2: Start HA WebSocket event stream if configured
        # Capability-based: start if HA connection is configured.
        if _caps.has(CAP_HA_CONNECTION):
            try:
                from ..config.being_config import load_being_config
                from ..integrations.home_assistant.ha_config import seed_ha_config_from_being
                being_cfg = load_being_config()
                if being_cfg.ha_url and being_cfg.ha_token:
                    seed_ha_config_from_being(being_cfg.ha_url, being_cfg.ha_token)
            except Exception as e:
                logger.warning(f"Failed to seed HA config from being.yml: {e}")
        try:
            from ..integrations.cognition_wiring import start_ha_event_stream
            start_ha_event_stream()
            # The event stream needs async start; do it in a delayed thread
            def start_ha_stream_delayed():
                import time, asyncio
                time.sleep(5)  # Wait for other services
                try:
                    from ..integrations.cognition_wiring import _ha_event_stream
                    if _ha_event_stream is not None:
                        loop = asyncio.new_event_loop()
                        loop.run_until_complete(_ha_event_stream.start())
                        loop.run_forever()
                except Exception as e:
                    logger.warning(f"HA event stream start failed: {e}")
            ha_starter = threading.Thread(target=start_ha_stream_delayed, daemon=True)
            ha_starter.start()
            logger.info("HA event stream starting in background...")
        except Exception as e:
            logger.warning(f"HA event stream not started: {e}")

        # Phase 4: Start Wyoming voice agent if enabled
        try:
            from ..integrations.wyoming_agent import HalbertWyomingAgent, WyomingConfig
            wyoming_cfg = WyomingConfig.from_env()
            if wyoming_cfg.enabled:
                global _wyoming_agent
                _wyoming_agent = HalbertWyomingAgent(config=wyoming_cfg)
                def start_wyoming_delayed():
                    import time, asyncio
                    time.sleep(7)  # after Frigate
                    try:
                        loop = asyncio.new_event_loop()
                        loop.run_until_complete(_wyoming_agent.start())
                        loop.run_forever()
                    except Exception as e:
                        logger.warning(f"Wyoming agent start failed: {e}")
                wyoming_starter = threading.Thread(target=start_wyoming_delayed, daemon=True)
                wyoming_starter.start()
                logger.info(f"Wyoming voice agent starting on {wyoming_cfg.host}:{wyoming_cfg.port}...")
        except Exception as e:
            logger.warning(f"Wyoming voice agent not started: {e}")

        # Frigate MQTT subscriber — start if MQTT is configured
        try:
            from ..integrations.frigate.frigate_config import load_frigate_config
            frigate_cfg = load_frigate_config()
            if frigate_cfg.is_mqtt_configured():
                from ..integrations.cognition_wiring import get_frigate_event_mapper
                from ..integrations.frigate.frigate_event_mapper import FrigateEventMapper
                from ..integrations.frigate.frigate_mqtt_subscriber import FrigateMQTTSubscriber
                global _frigate_mqtt_subscriber, _frigate_event_mapper
                # Use the cognition_wiring singleton so the same mapper
                # is used by both the MQTT subscriber and the composite
                # event mapper in the agent state machine.
                _frigate_event_mapper = get_frigate_event_mapper()
                if _frigate_event_mapper is None:
                    _frigate_event_mapper = FrigateEventMapper()
                _frigate_mqtt_subscriber = FrigateMQTTSubscriber(
                    config=frigate_cfg,
                    on_event=_frigate_event_mapper.handle_event,
                )
                def start_frigate_mqtt_delayed():
                    import time, asyncio
                    time.sleep(6)  # after HA stream
                    try:
                        loop = asyncio.new_event_loop()
                        loop.run_until_complete(_frigate_mqtt_subscriber.start())
                        loop.run_forever()
                    except Exception as e:
                        logger.warning(f"Frigate MQTT start failed: {e}")
                frigate_starter = threading.Thread(target=start_frigate_mqtt_delayed, daemon=True)
                frigate_starter.start()
                logger.info("Frigate MQTT subscriber starting in background...")
        except Exception as e:
            logger.warning(f"Frigate MQTT subscriber not started: {e}")

    # Shutdown event: stop background services
    @app.on_event("shutdown")
    async def shutdown_event():
        """Stop background services on app shutdown."""
        global _scheduler_executor
        global _config_watcher

        # Stop config watcher (T5a.2 + T7e.1)
        if _config_watcher is not None:
            try:
                _config_watcher.stop()
                _config_watcher = None
                logger.info("Config watcher stopped")
            except Exception as e:
                logger.warning(f"Failed to stop config watcher: {e}")

        # Stop scheduler
        if _scheduler_executor is not None:
            try:
                _scheduler_executor.stop()
                logger.info("Scheduler stopped")
            except Exception as e:
                logger.warning(f"Failed to stop scheduler: {e}")

        # Stop ingestion
        try:
            from ..ingestion.service import get_ingestion_service
            service = get_ingestion_service()
            service.stop()
            logger.info("Ingestion service stopped")
        except Exception as e:
            logger.warning(f"Failed to stop ingestion: {e}")

        # Stop terminal session manager (stops the reaper, kills live sessions)
        try:
            from ..streaming.session_manager import get_terminal_manager
            await get_terminal_manager().shutdown()
            logger.info("Terminal session manager shut down")
        except Exception as e:
            logger.warning(f"Failed to shut down terminal session manager: {e}")

        # Phase 2: Stop HA WebSocket event stream
        try:
            from ..integrations.cognition_wiring import _ha_event_stream, shutdown as cognition_shutdown
            if _ha_event_stream is not None:
                await _ha_event_stream.stop()
                logger.info("HA event stream stopped")
            cognition_shutdown()
        except Exception as e:
            logger.warning(f"Failed to stop HA event stream: {e}")

        # Stop Frigate MQTT subscriber
        try:
            global _frigate_mqtt_subscriber
            if _frigate_mqtt_subscriber is not None:
                await _frigate_mqtt_subscriber.stop()
                _frigate_mqtt_subscriber = None
                logger.info("Frigate MQTT subscriber stopped")
        except Exception as e:
            logger.warning(f"Failed to stop Frigate MQTT subscriber: {e}")

        # Phase 4: Stop Wyoming voice agent
        try:
            global _wyoming_agent
            if _wyoming_agent is not None:
                await _wyoming_agent.stop()
                _wyoming_agent = None
                logger.info("Wyoming voice agent stopped")
        except Exception as e:
            logger.warning(f"Failed to stop Wyoming voice agent: {e}")

        # Voice mode (O2): stop the audio pipeline coordinator (also closes
        # any open /api/audio/stream WebSocket via the ingress stop()).
        audio_coordinator = getattr(app.state, "audio_coordinator", None)
        if audio_coordinator is not None:
            try:
                await audio_coordinator.stop()
                app.state.audio_coordinator = None
                logger.info("Audio pipeline coordinator stopped")
            except Exception as e:
                logger.warning(f"Failed to stop audio pipeline coordinator: {e}")
        # Cleared unconditionally: a stop() that raised still leaves a
        # coordinator nobody should answer has_speaker() from.
        from .routes.audio import set_audio_pipeline as _clear_audio_pipeline
        _clear_audio_pipeline(None)

        # Voice mode (O3): drop the hub's pipeline reference on shutdown so
        # it can never mint barge-in tokens against a stopped coordinator.
        tts_hub = getattr(app.state, "tts_egress", None)
        if tts_hub is not None:
            tts_hub.set_pipeline(None)

        # Close Frigate tools singleton client
        try:
            from ..integrations.frigate.frigate_tools import close_client as close_frigate_client
            await close_frigate_client()
            logger.info("Frigate tools client closed")
        except Exception as e:
            logger.warning(f"Failed to close Frigate tools client: {e}")
    
    logger.info("Halbert Dashboard API created")
    
    return app


# Module-level app instance for uvicorn
app = create_app()


if __name__ == "__main__":
    import os
    import uvicorn
    port = int(os.environ.get("HALBERT_PORT", "8000"))
    host = os.environ.get("HALBERT_HOST", "127.0.0.1")
    uvicorn.run(app, host=host, port=port)
