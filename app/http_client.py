"""Reusable async HTTP helpers for inter-replica communication."""

from __future__ import annotations

import asyncio
import logging
from typing import Iterable, Optional, Union

import httpx
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel

logger = logging.getLogger("coordination.http")

_client = httpx.AsyncClient(timeout=5.0)


async def close_http_client() -> None:
    """Close the shared HTTP client during FastAPI shutdown."""

    await _client.aclose()


async def post_json(
    url: str,
    payload: Optional[Union[BaseModel, dict]],
    *,
    log_errors: bool = True,
) -> None:
    """Send a JSON payload to the given URL, logging failures."""

    if isinstance(payload, BaseModel):
        body = payload.model_dump(mode="json")
    else:
        body = jsonable_encoder(payload)
    try:
        response = await _client.post(url, json=body)
        response.raise_for_status()
    except httpx.HTTPError as exc:  # pragma: no cover - log-only branch
        if log_errors:
            logger.warning("HTTP POST to %s failed: %s", url, exc)


async def broadcast_json(
    urls: Iterable[str], payload: Optional[Union[BaseModel, dict]]
) -> None:
    """Post the same payload to many URLs concurrently."""

    tasks = [post_json(url, payload) for url in urls]
    if tasks:
        await asyncio.gather(*tasks)
