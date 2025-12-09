"""
WebSocket route for real-time updates.
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.requests import Request
import logging

router = APIRouter()
logger = logging.getLogger('cerebric.dashboard.websocket')


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time dashboard updates.
    
    Sends events:
    - system_status: System metrics every 5s
    - approval_request: New approval needed
    - job_update: Job status changed
    - decision: New LLM decision made
    """
    # Get connection manager from app state
    manager = websocket.app.state.ws_manager
    
    await manager.connect(websocket)
    
    try:
        while True:
            # Keep connection alive
            # Actual data is sent via manager.broadcast()
            await websocket.receive_text()
    
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        logger.info("Client disconnected")
