"""In-memory state containers for the coordination protocols."""

from __future__ import annotations

import asyncio
import heapq
import random
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Deque, Dict, List, Optional, Set, Tuple
from uuid import UUID

from .config import get_config
from .models import (
    CoordinatorAnnouncement,
    ElectionMessage,
    MulticastAck,
    MulticastIngress,
    MulticastMessage,
    StatusResponse,
    TokenPayload,
    TokenRequest,
)


@dataclass
class MulticastState:
    total_servers: int
    clock_offset: float = field(default_factory=lambda: random.uniform(0, 10))

    def __post_init__(self) -> None:
        self._heap: List[Tuple[float, int, str]] = []
        self._messages: Dict[UUID, MulticastMessage] = {}
        self._acks: Dict[UUID, Set[str]] = {}
        self._logical_counter = 0
        self._lock = asyncio.Lock()

    def _next_timestamp(self) -> datetime:
        now = datetime.utcnow() + timedelta(seconds=self.clock_offset)
        self._logical_counter += 1
        return now

    async def add_external(
        self, payload: MulticastIngress, server_id: str
    ) -> MulticastMessage:
        async with self._lock:
            # advance local lamport clock and attach to the outgoing message
            try:
                lamport = await global_state.bully.tick()
            except Exception:
                # If global_state isn't available for some reason, fall back to 0
                lamport = 0

            message = MulticastMessage(
                content=payload.content,
                server_id=server_id,
                timestamp=self._next_timestamp(),
                lamport_time=lamport,
                first_receiver_id=server_id,
            )
            self._register_message(message)
            self._acks[message.uuid] = set()
            self._enqueue(message)
            await self._maybe_process()
            return message

    async def add_remote(self, message: MulticastMessage) -> None:
        async with self._lock:
            if message.uuid not in self._messages:
                self._register_message(message)
                self._acks.setdefault(message.uuid, set())
                self._enqueue(message)
            await self._maybe_process()

    async def register_ack(self, ack: MulticastAck) -> int:
        async with self._lock:
            known = self._acks.setdefault(ack.uuid, set())
            known.add(ack.sender_id)
            await self._maybe_process()
            return len(known)

    def _register_message(self, message: MulticastMessage) -> None:
        self._messages[message.uuid] = message

    def _enqueue(self, message: MulticastMessage) -> None:
        priority_ts = message.timestamp.timestamp()
        heapq.heappush(
            self._heap, (priority_ts, self._logical_counter, message.uuid.hex)
        )

    async def _maybe_process(self) -> None:
        while self._heap:
            _, _, uuid_hex = self._heap[0]
            message_uuid = UUID(uuid_hex)
            ack_count = len(self._acks.get(message_uuid, set()))
            if ack_count < max(self.total_servers - 1, 0):
                return
            heapq.heappop(self._heap)
            message = self._messages.pop(message_uuid, None)
            self._acks.pop(message_uuid, None)
            if message:
                # Simple observable side effect: print to stdout.
                print(
                    f"[Multicast] Processed {message.uuid} from {message.server_id} "
                    f"with {ack_count} acknowledgements: {message.content}"
                )

    def pending_messages(self) -> int:
        return len(self._heap)


@dataclass
class TokenRingState:
    has_token: bool = False

    def __post_init__(self) -> None:
        self._queue: Deque[TokenRequest] = deque()
        self._lock = asyncio.Lock()
        self._last_token_time = time.monotonic()

    async def enqueue(self, request: TokenRequest) -> None:
        async with self._lock:
            self._queue.append(request)

    async def acquire_token(self, payload: TokenPayload) -> Optional[TokenRequest]:
        async with self._lock:
            self.has_token = True
            self._last_token_time = time.monotonic()
            if self._queue:
                return self._queue.popleft()
            return None

    async def release_token(self) -> None:
        async with self._lock:
            self.has_token = False
            self._last_token_time = time.monotonic()

    def queue_depth(self) -> int:
        return len(self._queue)

    def token_timeout(self, seconds: float = 10.0) -> bool:
        return (time.monotonic() - self._last_token_time) > seconds


@dataclass
class BullyState:
    lamport_time: int = 0

    def __post_init__(self) -> None:
        config = get_config()
        self.leader_id: Optional[str] = config.initial_leader_id
        self._lock = asyncio.Lock()

    async def tick(self) -> int:
        async with self._lock:
            self.lamport_time += 1
            return self.lamport_time

    async def update_from_message(self, incoming: ElectionMessage) -> int:
        async with self._lock:
            self.lamport_time = max(self.lamport_time, incoming.lamport_time) + 1
            return self.lamport_time

    async def set_leader(self, announcement: CoordinatorAnnouncement) -> None:
        async with self._lock:
            self.lamport_time = max(self.lamport_time, announcement.lamport_time)
            self.leader_id = announcement.leader_id

    def snapshot(self) -> StatusResponse:
        config = get_config()
        return StatusResponse(
            server_id=config.server_id,
            leader_id=self.leader_id,
            has_token=False,
            queue_depth=0,
            pending_messages=0,
        )


class GlobalState:
    """Container holding all protocol states."""

    def __init__(self) -> None:
        config = get_config()
        self.multicast = MulticastState(total_servers=config.total_servers)
        self.token_ring = TokenRingState()
        self.bully = BullyState()

    def snapshot(self) -> StatusResponse:
        config = get_config()
        return StatusResponse(
            server_id=config.server_id,
            leader_id=self.bully.leader_id,
            has_token=self.token_ring.has_token,
            queue_depth=self.token_ring.queue_depth(),
            pending_messages=self.multicast.pending_messages(),
        )


global_state = GlobalState()
