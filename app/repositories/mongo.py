"""One shared MongoDB connection for all repositories."""
from __future__ import annotations

from functools import lru_cache
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


@lru_cache
def get_database() -> Any | None:
    """The configured database, or None when MONGODB_URI is unset or unreachable."""
    settings = get_settings()
    if not settings.mongodb_uri:
        logger.info("MONGO: MONGODB_URI not configured")
        return None
    try:
        from pymongo import MongoClient

        client = MongoClient(settings.mongodb_uri, serverSelectionTimeoutMS=5000)
        client.admin.command("ping")
        logger.info("MONGO: connected (db=%s)", settings.mongodb_db_name)
        return client[settings.mongodb_db_name]
    except Exception as exc:
        logger.warning("MONGO: unavailable: %s", exc)
        return None
