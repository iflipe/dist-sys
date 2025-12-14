"""Convenience entrypoint for running the FastAPI app locally."""

from __future__ import annotations

import uvicorn
from dotenv import load_dotenv

from app.config import get_config


def main() -> None:
    load_dotenv()
    config = get_config()
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=config.server_port,
        reload=True,
    )


if __name__ == "__main__":
    main()
