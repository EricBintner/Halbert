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
    
    # CORS for local development
    if enable_cors:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["http://localhost:5173", "http://localhost:3000"],  # Vite, CRA
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    
    # WebSocket connection manager
    manager = ConnectionManager()
    
    # Store in app state
    app.state.ws_manager = manager
    
    # Register routes
    from .routes import approvals, jobs, memory, settings, system, websocket, persona, discovery, terminal, chat, alerts, rag, conversations, services, web_search, gpu, containers, development, editor, storage, downloads, agent, compression, being
    
    app.include_router(system.router, prefix="/api", tags=["system"])
    app.include_router(agent.router, tags=["agent"])  # Phase 36: Agent state machine
    app.include_router(approvals.router, prefix="/api/approvals", tags=["approvals"])
    app.include_router(jobs.router, prefix="/api/jobs", tags=["jobs"])
    app.include_router(memory.router, prefix="/api/memory", tags=["memory"])
    app.include_router(settings.router, prefix="/api/settings", tags=["settings"])
    app.include_router(discovery.router, prefix="/api/discoveries", tags=["discoveries"])  # Phase 11
    app.include_router(terminal.router, prefix="/api/terminal", tags=["terminal"])  # Phase 11
    app.include_router(chat.router, prefix="/api/chat", tags=["chat"])  # Phase 11
    app.include_router(alerts.router, prefix="/api/alerts", tags=["alerts"])  # Phase 11
    app.include_router(rag.router, prefix="/api", tags=["rag"])  # Phase 10
    app.include_router(conversations.router, prefix="/api/conversations", tags=["conversations"])  # Phase 12
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
    
    # Serve static frontend (production)
    frontend_dist = Path(__file__).parent / "frontend" / "dist"
    if frontend_dist.exists():
        app.mount("/assets", StaticFiles(directory=frontend_dist / "assets"), name="assets")

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
        async def serve_spa():
            """Serve React app for frontend routes."""
            return FileResponse(
                frontend_dist / "index.html",
                headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
            )
    
    # Startup event: auto-start services
    @app.on_event("startup")
    async def startup_event():
        """Start background services on app startup."""
        # Reset indexing state to prevent stuck state from hot-reload
        try:
            from .routes.settings import _reset_indexing_state
            _reset_indexing_state()
            logger.info("Indexing state reset on startup")
        except Exception as e:
            logger.warning(f"Failed to reset indexing state: {e}")
        
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
        
        # Phase 23: Start scheduler (re-enabled with delayed start)
        def start_scheduler_delayed():
            """Start scheduler after a short delay."""
            import time
            time.sleep(3)  # Wait for other services to initialize
            try:
                from ..scheduler.executor import AutonomousExecutor, APSCHEDULER_AVAILABLE
                if APSCHEDULER_AVAILABLE:
                    global _scheduler_executor
                    _scheduler_executor = AutonomousExecutor(
                        max_workers=3,
                        enable_llm=False,  # Disable LLM for scheduler jobs
                        enable_guardrails=True
                    )
                    _scheduler_executor.start()
                    logger.info("Scheduler started successfully")
                else:
                    logger.info("APScheduler not available, scheduler disabled")
            except Exception as e:
                logger.warning(f"Failed to start scheduler: {e}")
        
        scheduler_starter = threading.Thread(target=start_scheduler_delayed, daemon=True)
        scheduler_starter.start()
        logger.info("Scheduler starting in background...")
    
    # Shutdown event: stop background services
    @app.on_event("shutdown")
    async def shutdown_event():
        """Stop background services on app shutdown."""
        global _scheduler_executor
        
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
    
    logger.info("Halbert Dashboard API created")
    
    return app


# Module-level app instance for uvicorn
app = create_app()
