"""FastAPI application entrypoint for the distributed coordination protocols."""

from __future__ import annotations

import asyncio
import logging
import random
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import BackgroundTasks, FastAPI

from .config import get_config
from .http_client import broadcast_json, close_http_client, post_json
from .models import (
    CoordinatorAnnouncement,
    ElectionMessage,
    Heartbeat,
    MulticastAck,
    MulticastIngress,
    MulticastMessage,
    StatusResponse,
    TokenPayload,
    TokenRequest,
)
from .state import global_state

# Basic logging configuration to include timestamps in log lines. This will
# prepend an ISO-like timestamp to log messages (including access logs).
logging.basicConfig(
    format="%(asctime)s %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

app = FastAPI(title="Coordination Algorithms", version="0.1.0")


@app.on_event("shutdown")
async def shutdown_event() -> None:
    await close_http_client()


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/status", response_model=StatusResponse)
async def status() -> StatusResponse:
    return global_state.snapshot()


@app.post("/multicast/messages", response_model=MulticastMessage)
async def post_multicast_message(
    payload: MulticastIngress, tasks: BackgroundTasks
) -> MulticastMessage:
    config = get_config()
    message = await global_state.multicast.add_external(payload, config.server_id)
    tasks.add_task(_disseminate_message, message)
    return message


@app.post("/multicast/internal", status_code=202)
async def receive_internal_message(
    message: MulticastMessage, tasks: BackgroundTasks
) -> None:
    await global_state.multicast.add_remote(message)
    tasks.add_task(_send_ack, message.uuid)


@app.post("/multicast/acks", status_code=202)
async def receive_ack(ack: MulticastAck) -> dict[str, int]:
    ack_count = await global_state.multicast.register_ack(ack)
    return {"acks": ack_count}


@app.post("/token/request", response_model=TokenRequest)
async def enqueue_critical_request(request: TokenRequest) -> TokenRequest:
    # stamp the request with a lamport time at enqueue time
    try:
        request.lamport_time = await global_state.bully.tick()
    except Exception:
        request.lamport_time = 0

    await global_state.token_ring.enqueue(request)
    return request


@app.post("/ring/token")
async def accept_token(payload: TokenPayload) -> dict[str, str]:
    request = await global_state.token_ring.acquire_token(payload)
    if request:
        # Placeholder for real critical section work.
        print(f"[TokenRing] Processing request {request.request_id}: {request.payload}")
    completed_id = request.request_id if request else None
    await _forward_token(completed_id)
    await global_state.token_ring.release_token()
    return {"status": "forwarded"}


@app.post("/ring/heartbeat")
async def token_heartbeat(heartbeat: Heartbeat) -> dict[str, str]:
    # Heartbeat processing would update neighbor liveness; stubbed for now.
    return {"received_from": heartbeat.sender_id}


@app.post("/bully/heartbeat")
async def bully_heartbeat(heartbeat: Heartbeat) -> dict[str, str]:
    global_state.bully.leader_id = heartbeat.sender_id
    return {"leader": heartbeat.sender_id}


@app.post("/bully/election")
async def bully_election(message: ElectionMessage) -> dict[str, int]:
    lamport = await global_state.bully.update_from_message(message)
    return {"lamport_time": lamport}


@app.post("/bully/answer")
async def bully_answer(message: ElectionMessage) -> dict[str, int]:
    lamport = await global_state.bully.update_from_message(message)
    return {"lamport_time": lamport}


@app.post("/bully/coordinator")
async def bully_coordinator(announcement: CoordinatorAnnouncement) -> dict[str, str]:
    await global_state.bully.set_leader(announcement)
    return {"leader": announcement.leader_id}


async def _disseminate_message(message: MulticastMessage) -> None:
    """Send the message to all peers over HTTP."""

    await broadcast_json(_peer_endpoints("/multicast/internal"), message)


async def _send_ack(message_uuid: UUID) -> None:
    """Simulate delayed ack logic before responding."""
    # 10% chance to sleep between 2 and 10 seconds.
    if random.randint(1, 10) == 1:
        await asyncio.sleep(random.randint(2, 10))
    # Advance lamport and attach to ack
    try:
        lamport = await global_state.bully.tick()
    except Exception:
        lamport = 0

    ack = MulticastAck(
        uuid=message_uuid,
        sender_id=get_config().server_id,
        timestamp=datetime.utcnow(),
        lamport_time=lamport,
    )
    await global_state.multicast.register_ack(ack)
    await broadcast_json(_peer_endpoints("/multicast/acks"), ack)


async def _forward_token(completed_request_id: Optional[UUID]) -> None:
    successor = get_config().token_successor
    if not successor:
        return
    # attach lamport time to the forwarded token payload
    try:
        lamport = await global_state.bully.tick()
    except Exception:
        lamport = 0

    payload = TokenPayload(
        pending_work_ids=[completed_request_id] if completed_request_id else [],
        sender_id=get_config().server_id,
        lamport_time=lamport,
    )
    await post_json(
        _absolute_url(successor, "/ring/token"),
        payload,
        log_errors=completed_request_id is not None,
    )


def _peer_endpoints(path: str) -> List[str]:
    config = get_config()
    return [_absolute_url(peer, path) for peer in config.peer_urls]


def _absolute_url(base: str, path: str) -> str:
    base_clean = base.rstrip("/")
    return f"{base_clean}{path}"
