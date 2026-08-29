# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Priority-queued compute broker for multi-satellite inference.

Implements finding H6 from the federated multi-node review.

H6 — 1:N from Day One is over-scoped
--------------------------------------
Phase 7 proved 1:1 (two processes, one machine).  Jumping to 1:25+ with
a priority concurrency broker in a single phase is a 10x complexity jump
with no intermediate validation.

This broker is scaffolded for the full 1:N design but defaults to
``max_concurrent=1`` for Phase 9.2a (1:1 validation).  The priority queue
and semaphore are in place but effectively pass-through when
``max_concurrent=1``.  Phase 9.8 (2b) increases ``max_concurrent`` and
enables preemption.

Priority levels (from the handoff §4 Pillar 2)
----------------------------------------------
  Priority 1 (Interactive Local User): Immediate execution for the
    direct desktop user's prompt.  Preempts everything.
  Priority 2 (Interactive Remote Voice/Sensor): Real-time queries from
    a satellite's wake-word / smart home action.  High priority but
    does not preempt Priority 1.
  Priority 3 (Background Batch): Daily digests, log indexing, scheduled
    maintenance.  Lowest priority, FIFO within this level.

Concurrency model
-----------------
An ``asyncio.Semaphore(max_concurrent)`` gates how many inference
requests can run simultaneously on the GPU.  When all slots are full,
new requests wait in the priority queue.  Priority 1 requests can
preempt Priority 3 requests (the preempted request is re-queued).

VRAM thrashing prevention
-------------------------
The semaphore prevents VRAM thrashing by limiting concurrent model
loads.  If the GPU has 24GB VRAM and the model uses 16GB, only one
concurrent request is safe (``max_concurrent=1``).  If the model uses
8GB, two concurrent requests fit (``max_concurrent=2``).  The broker
does not manage VRAM directly — the operator sets ``max_concurrent``
based on their GPU and model size.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Priority levels
# ---------------------------------------------------------------------------

class ComputePriority(IntEnum):
    """Priority level for a compute request.

    Lower number = higher priority (matches asyncio and Unix conventions).
    """
    LOCAL_INTERACTIVE = 1    # Direct desktop user prompt
    REMOTE_INTERACTIVE = 2   # Satellite voice/sensor real-time query
    BACKGROUND_BATCH = 3     # Daily digest, log indexing, maintenance


# ---------------------------------------------------------------------------
# Request envelope
# ---------------------------------------------------------------------------

@dataclass(order=True)
class ComputeRequest:
    """A queued compute request, ordered by (priority, timestamp).

    Uses ``field(compare=True/False)`` (NOT ``metadata={"compare": ...}``
    which the dataclasses module ignores). Only ``priority`` and
    ``timestamp`` participate in ordering; all other fields are excluded
    so that non-comparable types (list, dict, None Future) don't break
    PriorityQueue sorting on tie-breaks.
    """
    # Comparison fields (sort by priority then timestamp):
    priority: int = field(compare=True)  # ComputePriority value
    timestamp: float = field(default_factory=time.time, compare=True)
    # Non-comparison fields:
    peer_node_id: str = field(default="", compare=False)
    model: str = field(default="", compare=False)
    messages: list = field(default_factory=list, compare=False)
    tools: Optional[list] = field(default=None, compare=False)
    # Future for the result:
    _future: asyncio.Future = field(default=None, compare=False)
    _preempted: bool = field(default=False, compare=False)


# ---------------------------------------------------------------------------
# Broker
# ---------------------------------------------------------------------------

class ComputeBroker:
    """Manages multi-satellite inference with priority queueing.

    Phase 9.2a (1:1): ``max_concurrent=1``, no preemption.
    Phase 9.8 (2b): ``max_concurrent=N``, preemption of P3 by P1.

    The broker runs as an asyncio task that pulls from the priority queue
    and acquires the semaphore before dispatching to the local model.
    """

    def __init__(
        self,
        max_concurrent: int = 1,
        enable_preemption: bool = False,
    ):
        """
        Args:
            max_concurrent: How many inference requests can run
                simultaneously on the GPU.  Default 1 for Phase 9.2a.
                Increase to 2-4 for Phase 9.8 based on GPU VRAM.
            enable_preemption: If True, Priority 1 requests can preempt
                Priority 3 requests.  Default False for 9.2a.
        """
        self.max_concurrent = max_concurrent
        self.enable_preemption = enable_preemption
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._queue: asyncio.PriorityQueue[ComputeRequest] = asyncio.PriorityQueue()
        self._running: Dict[int, ComputeRequest] = {}  # id(req) -> req
        self._worker_task: Optional[asyncio.Task] = None
        self._shutdown = False

        logger.info(
            "ComputeBroker initialized: max_concurrent=%d, preemption=%s",
            max_concurrent, enable_preemption,
        )

    async def start(self) -> None:
        """Start the broker's worker loop.

        TODO(federation-9.3): Start the asyncio task that pulls from
        the queue, acquires the semaphore, and dispatches to the local
        model provider.
        """
        # TODO(federation-9.3): self._worker_task = asyncio.create_task(self._worker_loop())
        raise NotImplementedError("ComputeBroker.start() — TODO(federation-9.3)")

    async def stop(self) -> None:
        """Stop the broker, cancel pending requests."""
        self._shutdown = True
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass

    async def submit(self, request: ComputeRequest) -> Dict[str, Any]:
        """Submit a compute request and wait for the result.

        This is called by ``compute_endpoint._submit_to_broker()``.

        TODO(federation-9.3): Put the request on the priority queue,
        await the future, and return the raw model response.
        """
        # TODO(federation-9.3):
        # 1. Create a Future for the result
        # 2. Put the ComputeRequest on the priority queue
        # 3. Await the future
        # 4. Return the result (or re-raise if the request was cancelled)
        raise NotImplementedError("ComputeBroker.submit() — TODO(federation-9.3)")

    async def _worker_loop(self) -> None:
        """Main worker loop — pull from queue, acquire semaphore, dispatch.

        TODO(federation-9.3): Implement the loop:
        1. Get the highest-priority request from the queue
        2. Acquire the semaphore (await self._semaphore.acquire())
        3. If enable_preemption and the request is P1 and a P3 is running:
           a. Cancel the P3 request's model call
           b. Re-queue the P3 request
           c. Release the P3's semaphore slot
        4. Dispatch to the local model provider
        5. Set the request's future result
        6. Release the semaphore
        """
        raise NotImplementedError("ComputeBroker._worker_loop() — TODO(federation-9.3)")

    def get_stats(self) -> Dict[str, Any]:
        """Return broker statistics for monitoring.

        TODO(federation-9.8): Return queue depth, active requests,
        average wait time, preemption count.
        """
        return {
            "max_concurrent": self.max_concurrent,
            "queue_depth": self._queue.qsize(),
            "running": len(self._running),
            "preemption_enabled": self.enable_preemption,
        }
