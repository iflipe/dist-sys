from __future__ import annotations

import asyncio
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.models import (  # noqa: E402
    CoordinatorAnnouncement,
    ElectionMessage,
    MulticastAck,
    MulticastIngress,
    TokenPayload,
    TokenRequest,
)
from app.state import BullyState, MulticastState, TokenRingState  # noqa: E402


def test_multicast_requires_quorum() -> None:
    async def scenario() -> None:
        state = MulticastState(total_servers=3)
        payload = MulticastIngress(content="hello world")
        message = await state.add_external(payload, "server-a")
        assert state.pending_messages() == 1

        await state.register_ack(
            MulticastAck(
                uuid=message.uuid, sender_id="server-b", timestamp=datetime.utcnow()
            )
        )
        assert state.pending_messages() == 1  # still waiting for server-c

        await state.register_ack(
            MulticastAck(
                uuid=message.uuid, sender_id="server-c", timestamp=datetime.utcnow()
            )
        )
        assert state.pending_messages() == 0

    asyncio.run(scenario())


def test_multicast_deduplicates_ack_senders() -> None:
    async def scenario() -> None:
        state = MulticastState(total_servers=3)
        payload = MulticastIngress(content="dedupe")
        message = await state.add_external(payload, "server-a")

        first = await state.register_ack(
            MulticastAck(
                uuid=message.uuid, sender_id="server-b", timestamp=datetime.utcnow()
            )
        )
        assert first == 1

        duplicate = await state.register_ack(
            MulticastAck(
                uuid=message.uuid, sender_id="server-b", timestamp=datetime.utcnow()
            )
        )
        assert duplicate == 1  # same sender id does not increase the count

    asyncio.run(scenario())


def test_token_ring_respects_fifo_queue() -> None:
    async def scenario() -> None:
        state = TokenRingState()
        req1 = TokenRequest(payload="first")
        req2 = TokenRequest(payload="second")
        await state.enqueue(req1)
        await state.enqueue(req2)

        processed_first = await state.acquire_token(TokenPayload(sender_id="server-a"))
        assert processed_first is req1
        await state.release_token()

        processed_second = await state.acquire_token(TokenPayload(sender_id="server-b"))
        assert processed_second is req2

    asyncio.run(scenario())


def test_bully_lamport_time_advances() -> None:
    async def scenario() -> None:
        state = BullyState()
        assert await state.tick() == 1

        lamport = await state.update_from_message(
            ElectionMessage(sender_id="server-b", lamport_time=5)
        )
        assert lamport == 6

        await state.set_leader(
            CoordinatorAnnouncement(leader_id="server-b", lamport_time=10)
        )
        assert state.leader_id == "server-b"
        assert state.lamport_time == 10

    asyncio.run(scenario())
