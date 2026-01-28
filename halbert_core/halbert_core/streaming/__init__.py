"""
Streaming Infrastructure

Event emitter and SSE helpers for real-time agent communication.
Based on research5.md Part 16.
"""

from .emitter import EventEmitter, StreamConfig
from .sse import create_sse_response, sse_generator

__all__ = [
    'EventEmitter',
    'StreamConfig',
    'create_sse_response',
    'sse_generator',
]
