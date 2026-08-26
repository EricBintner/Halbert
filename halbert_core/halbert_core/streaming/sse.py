# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
SSE Helpers

Utilities for Server-Sent Events streaming.
Based on research5.md Part 16.2.
"""

from __future__ import annotations
import asyncio
import json
import logging
from typing import AsyncIterator, Callable, Optional, Any

logger = logging.getLogger('halbert.streaming.sse')

# Check for FastAPI
try:
    from fastapi.responses import StreamingResponse
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    StreamingResponse = None


def create_sse_response(
    generator: AsyncIterator[str],
    on_disconnect: Callable = None,
    headers: dict = None
):
    """
    Create an SSE streaming response.
    
    Args:
        generator: Async generator yielding SSE formatted strings
        on_disconnect: Optional callback when client disconnects
        headers: Additional response headers
        
    Returns:
        StreamingResponse configured for SSE
    """
    if not FASTAPI_AVAILABLE:
        raise ImportError("FastAPI not available. Install with: pip install fastapi")
    
    async def event_stream():
        try:
            async for event in generator:
                yield event
        except asyncio.CancelledError:
            logger.debug("SSE connection cancelled")
            if on_disconnect:
                try:
                    if asyncio.iscoroutinefunction(on_disconnect):
                        await on_disconnect()
                    else:
                        on_disconnect()
                except Exception as e:
                    logger.error(f"Error in disconnect callback: {e}")
            raise
        except Exception as e:
            logger.error(f"SSE stream error: {e}")
            raise
    
    default_headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",  # Disable nginx buffering
        "Content-Type": "text/event-stream",
    }
    
    if headers:
        default_headers.update(headers)
    
    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers=default_headers
    )


async def sse_generator(
    source: AsyncIterator[Any],
    event_type: str = None,
    transform: Callable = None,
    include_id: bool = False
) -> AsyncIterator[str]:
    """
    Transform an async iterator into SSE formatted strings.
    
    Args:
        source: Source async iterator
        event_type: Optional event type to include
        transform: Optional transform function for data
        include_id: Include incrementing event ID
        
    Yields:
        SSE formatted strings
    """
    event_id = 0
    
    async for item in source:
        # Transform data if needed
        if transform:
            data = transform(item)
        elif hasattr(item, 'to_dict'):
            data = item.to_dict()
        elif isinstance(item, dict):
            data = item
        else:
            data = {"data": item}
        
        # Build SSE message
        lines = []
        
        if include_id:
            lines.append(f"id: {event_id}")
            event_id += 1
        
        if event_type:
            lines.append(f"event: {event_type}")
        
        # JSON encode the data
        json_data = json.dumps(data)
        lines.append(f"data: {json_data}")
        
        # Empty line to end the event
        lines.append("")
        lines.append("")
        
        yield "\n".join(lines)


def format_sse_event(
    data: Any,
    event_type: str = None,
    event_id: int = None,
    retry: int = None
) -> str:
    """
    Format a single SSE event.
    
    Args:
        data: Event data (will be JSON encoded if dict)
        event_type: Optional event type
        event_id: Optional event ID
        retry: Optional retry interval in ms
        
    Returns:
        SSE formatted string
    """
    lines = []
    
    if event_id is not None:
        lines.append(f"id: {event_id}")
    
    if event_type:
        lines.append(f"event: {event_type}")
    
    if retry is not None:
        lines.append(f"retry: {retry}")
    
    # Handle data
    if isinstance(data, dict):
        json_data = json.dumps(data)
    elif hasattr(data, 'to_dict'):
        json_data = json.dumps(data.to_dict())
    else:
        json_data = str(data)
    
    lines.append(f"data: {json_data}")
    lines.append("")
    lines.append("")
    
    return "\n".join(lines)


def format_sse_comment(comment: str) -> str:
    """Format an SSE comment (for keepalive/heartbeat)."""
    return f": {comment}\n\n"


class SSEChannel:
    """
    A channel for broadcasting SSE events to multiple clients.
    
    Useful for pub/sub patterns.
    """
    
    def __init__(self, name: str, max_clients: int = 100):
        self.name = name
        self.max_clients = max_clients
        self.clients: list[asyncio.Queue] = []
        self._lock = asyncio.Lock()
    
    async def subscribe(self) -> asyncio.Queue:
        """Subscribe to this channel."""
        async with self._lock:
            if len(self.clients) >= self.max_clients:
                # Remove oldest
                old = self.clients.pop(0)
                try:
                    old.put_nowait(None)
                except asyncio.QueueFull:
                    pass
            
            queue = asyncio.Queue(maxsize=100)
            self.clients.append(queue)
            return queue
    
    async def unsubscribe(self, queue: asyncio.Queue):
        """Unsubscribe from this channel."""
        async with self._lock:
            if queue in self.clients:
                self.clients.remove(queue)
    
    async def broadcast(self, data: Any, event_type: str = None):
        """Broadcast data to all subscribers."""
        event = format_sse_event(data, event_type)
        
        async with self._lock:
            dead_clients = []
            
            for queue in self.clients:
                try:
                    queue.put_nowait(event)
                except asyncio.QueueFull:
                    # Try to make room
                    try:
                        queue.get_nowait()
                        queue.put_nowait(event)
                    except asyncio.QueueEmpty:
                        dead_clients.append(queue)
            
            # Remove dead clients
            for queue in dead_clients:
                self.clients.remove(queue)
    
    async def stream(self, queue: asyncio.Queue) -> AsyncIterator[str]:
        """Stream events from a subscribed queue."""
        try:
            while True:
                event = await queue.get()
                if event is None:
                    break
                yield event
        finally:
            await self.unsubscribe(queue)
    
    @property
    def client_count(self) -> int:
        return len(self.clients)
