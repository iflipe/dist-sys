"""Application configuration helpers."""

from __future__ import annotations

import os
from functools import lru_cache
from typing import List, Optional

from dotenv import load_dotenv
from pydantic import BaseModel, Field

load_dotenv()


def _split_csv(value: Optional[str]) -> List[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


class AppConfig(BaseModel):
    """Runtime configuration derived from environment variables."""

    server_id: str = Field(default="server-1")
    server_port: int = Field(default=8000)
    peer_urls: List[str] = Field(default_factory=list)
    token_successor: Optional[str] = None
    token_predecessor: Optional[str] = None
    total_servers: int = Field(default=3, ge=1)
    initial_leader_id: Optional[str] = None


@lru_cache
def get_config() -> AppConfig:
    """Load configuration once per process."""

    return AppConfig(
        server_id=os.getenv("SERVER_ID", "server-1"),
        server_port=int(os.getenv("SERVER_PORT", "8000")),
        peer_urls=_split_csv(os.getenv("PEER_URLS")),
        token_successor=os.getenv("TOKEN_SUCCESSOR"),
        token_predecessor=os.getenv("TOKEN_PREDECESSOR"),
        total_servers=int(os.getenv("TOTAL_SERVERS", "3")),
        initial_leader_id=os.getenv("INITIAL_LEADER_ID"),
    )
