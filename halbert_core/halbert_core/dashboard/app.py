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
        version="0.1.0"
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
    from .routes import approvals, jobs, memory, settings, system, websocket, persona, discovery, terminal, chat, alerts, rag, conversations, services, web_search, gpu, containers, development, editor
    
    app.include_router(system.router, prefix="/api", tags=["system"])
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
            return FileResponse(frontend_dist / "index.html")
        
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
        @app.get("/approvals")
        @app.get("/settings")
        async def serve_spa():
            """Serve React app for frontend routes."""
            return FileResponse(frontend_dist / "index.html")
    
    logger.info("Halbert Dashboard API created")
    
    return app


# Module-level app instance for uvicorn
app = create_app()
