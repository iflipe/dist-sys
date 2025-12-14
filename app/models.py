"""Pydantic models shared by the services."""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class MulticastIngress(BaseModel):
    content: str = Field(min_length=1, max_length=1024)


class MulticastMessage(BaseModel):
    uuid: UUID = Field(default_factory=uuid4)
    server_id: str
    timestamp: datetime
    lamport_time: int = 0
    content: str
    first_receiver_id: Optional[str] = None


class MulticastAck(BaseModel):
    uuid: UUID
    sender_id: str
    timestamp: datetime
    lamport_time: int = 0


class TokenRequest(BaseModel):
    request_id: UUID = Field(default_factory=uuid4)
    payload: str = Field(min_length=1, max_length=1024)
    lamport_time: int = 0


class TokenPayload(BaseModel):
    pending_work_ids: List[UUID] = Field(default_factory=list)
    sender_id: str
    lamport_time: int = 0


class Heartbeat(BaseModel):
    sender_id: str
    timestamp: datetime
    lamport_time: int = 0


class ElectionMessage(BaseModel):
    sender_id: str
    lamport_time: int


class CoordinatorAnnouncement(BaseModel):
    leader_id: str
    lamport_time: int


class StatusResponse(BaseModel):
    server_id: str
    leader_id: Optional[str]
    has_token: bool
    queue_depth: int
    pending_messages: int
