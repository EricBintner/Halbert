"""
Event Emitter

Manages event streaming to clients with buffering and heartbeats.
Based on research5.md Part 16.1.
"""

from __future__ import annotations
import asyncio
import json
import time
import logging
from dataclasses import dataclass, field
from typing import AsyncIterator, Dict, List, Optional, Any, Callable

logger = logging.getLogger('halbert.streaming.emitter')


@dataclass
class StreamConfig:
    """Configuration for streaming."""
    buffer_size: int = 100
    flush_interval_ms: int = 50
    heartbeat_interval_s: int = 30
    max_subscribers: int = 100


@dataclass
class StreamEvent:
    """An event in the stream."""
    type: str
    session_id: str
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    
    def to_dict(self) -> Dict:
        return {
            "type": self.type,
            "session_id": self.session_id,
            "timestamp": self.timestamp,
            **self.data
        }
    
    def to_sse(self) -> str:
        """Format as Server-Sent Event."""
        return f"data: {json.dumps(self.to_dict())}\n\n"
    
    @classmethod
    def state_change(cls, session_id: str, new_state: str, previous_state: str = None):
        return cls(
            type="state_change",
            session_id=session_id,
            data={"state": new_state, "previous_state": previous_state}
        )
    
    @classmethod
    def response_chunk(cls, session_id: str, content: str):
        return cls(
            type="response_chunk",
            session_id=session_id,
            data={"content": content}
        )
    
    @classmethod
    def tool_start(cls, session_id: str, tool: str, args: Dict, execution_id: str):
        return cls(
            type="tool_start",
            session_id=session_id,
            data={"tool": tool, "args": args, "execution_id": execution_id}
        )
    
    @classmethod
    def tool_complete(cls, session_id: str, execution_id: str, success: bool, result: Any = None, error: str = None):
        return cls(
            type="tool_complete",
            session_id=session_id,
            data={
                "execution_id": execution_id,
                "success": success,
                "result": result,
                "error": error
            }
        )
    
    @classmethod
    def error(cls, session_id: str, message: str, recoverable: bool = True):
        return cls(
            type="error",
            session_id=session_id,
            data={"message": message, "recoverable": recoverable}
        )
    
    @classmethod
    def heartbeat(cls, session_id: str = "system"):
        return cls(
            type="heartbeat",
            session_id=session_id,
            data={"time": int(time.time())}
        )


class EventEmitter:
    """
    Manages event streaming to clients.
    
    Features:
    - Buffered emission for performance
    - Heartbeat for connection health
    - Multiple subscriber support
    - Per-session filtering
    """
    
    def __init__(self, config: StreamConfig = None):
        self.config = config or StreamConfig()
        self.subscribers: Dict[str, asyncio.Queue] = {}
        self.global_subscribers: List[asyncio.Queue] = []
        self.buffer: List[StreamEvent] = []
        self.last_flush = time.time()
        self._running = False
        self._heartbeat_task: Optional[asyncio.Task] = None
    
    async def start(self):
        """Start the emitter (heartbeat task)."""
        if self._running:
            return
        
        self._running = True
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        logger.info("EventEmitter started")
    
    async def stop(self):
        """Stop the emitter."""
        self._running = False
        
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
        
        # Close all subscribers
        for queue in list(self.subscribers.values()) + self.global_subscribers:
            try:
                queue.put_nowait(None)  # Signal end
            except asyncio.QueueFull:
                pass
        
        self.subscribers.clear()
        self.global_subscribers.clear()
        logger.info("EventEmitter stopped")
    
    async def emit(self, event: StreamEvent):
        """
        Emit an event to relevant subscribers.
        
        Events are buffered and flushed for performance.
        """
        self.buffer.append(event)
        
        # Flush if buffer full or interval elapsed
        now = time.time()
        if (len(self.buffer) >= self.config.buffer_size or
            (now - self.last_flush) * 1000 >= self.config.flush_interval_ms):
            await self._flush()
    
    async def emit_immediate(self, event: StreamEvent):
        """Emit an event immediately without buffering."""
        await self._send_event(event)
    
    async def _flush(self):
        """Flush buffer to all subscribers."""
        if not self.buffer:
            return
        
        events = self.buffer.copy()
        self.buffer.clear()
        self.last_flush = time.time()
        
        for event in events:
            await self._send_event(event)
    
    async def _send_event(self, event: StreamEvent):
        """Send event to appropriate subscribers."""
        # Session-specific subscribers
        session_id = event.session_id
        if session_id in self.subscribers:
            queue = self.subscribers[session_id]
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                # Drop oldest if full
                try:
                    queue.get_nowait()
                    queue.put_nowait(event)
                except asyncio.QueueEmpty:
                    pass
        
        # Global subscribers get all events
        for queue in self.global_subscribers:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                try:
                    queue.get_nowait()
                    queue.put_nowait(event)
                except asyncio.QueueEmpty:
                    pass
    
    def subscribe(self, session_id: str) -> asyncio.Queue:
        """
        Subscribe to events for a specific session.
        
        Returns queue to receive events from.
        """
        if len(self.subscribers) >= self.config.max_subscribers:
            # Remove oldest subscriber
            oldest = next(iter(self.subscribers))
            self.unsubscribe(oldest)
            logger.warning(f"Max subscribers reached, removed {oldest}")
        
        if session_id not in self.subscribers:
            self.subscribers[session_id] = asyncio.Queue(
                maxsize=self.config.buffer_size
            )
            logger.debug(f"New subscriber for session {session_id}")
        
        return self.subscribers[session_id]
    
    def subscribe_global(self) -> asyncio.Queue:
        """Subscribe to all events."""
        queue = asyncio.Queue(maxsize=self.config.buffer_size)
        self.global_subscribers.append(queue)
        return queue
    
    def unsubscribe(self, session_id: str):
        """Unsubscribe from session events."""
        if session_id in self.subscribers:
            del self.subscribers[session_id]
            logger.debug(f"Unsubscribed session {session_id}")
    
    def unsubscribe_global(self, queue: asyncio.Queue):
        """Unsubscribe from global events."""
        if queue in self.global_subscribers:
            self.global_subscribers.remove(queue)
    
    async def stream(self, session_id: str) -> AsyncIterator[str]:
        """
        Stream events as SSE for a session.
        
        Yields formatted SSE strings.
        """
        queue = self.subscribe(session_id)
        
        try:
            while True:
                try:
                    # Wait for event with timeout for heartbeat
                    event = await asyncio.wait_for(
                        queue.get(),
                        timeout=self.config.heartbeat_interval_s
                    )
                    
                    if event is None:  # End signal
                        break
                    
                    yield event.to_sse()
                    
                except asyncio.TimeoutError:
                    # Send heartbeat comment
                    yield f": heartbeat {int(time.time())}\n\n"
                    
        except asyncio.CancelledError:
            logger.debug(f"Stream cancelled for session {session_id}")
        finally:
            self.unsubscribe(session_id)
    
    async def stream_global(self) -> AsyncIterator[str]:
        """Stream all events as SSE."""
        queue = self.subscribe_global()
        
        try:
            while True:
                try:
                    event = await asyncio.wait_for(
                        queue.get(),
                        timeout=self.config.heartbeat_interval_s
                    )
                    
                    if event is None:
                        break
                    
                    yield event.to_sse()
                    
                except asyncio.TimeoutError:
                    yield f": heartbeat {int(time.time())}\n\n"
                    
        except asyncio.CancelledError:
            pass
        finally:
            self.unsubscribe_global(queue)
    
    async def _heartbeat_loop(self):
        """Background task to emit heartbeats."""
        while self._running:
            try:
                await asyncio.sleep(self.config.heartbeat_interval_s)
                
                # Send heartbeat to all subscribers
                heartbeat = StreamEvent.heartbeat()
                for session_id in list(self.subscribers.keys()):
                    try:
                        self.subscribers[session_id].put_nowait(heartbeat)
                    except asyncio.QueueFull:
                        pass
                    except KeyError:
                        pass
                        
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Heartbeat error: {e}")
    
    @property
    def subscriber_count(self) -> int:
        """Get number of active subscribers."""
        return len(self.subscribers) + len(self.global_subscribers)


# Global emitter instance
_emitter: Optional[EventEmitter] = None


def get_event_emitter() -> EventEmitter:
    """Get global event emitter."""
    global _emitter
    if _emitter is None:
        _emitter = EventEmitter()
    return _emitter


async def init_event_emitter(config: StreamConfig = None) -> EventEmitter:
    """Initialize and start global event emitter."""
    global _emitter
    _emitter = EventEmitter(config)
    await _emitter.start()
    return _emitter
