from __future__ import annotations

from typing import Any

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.schemas import Category
from app.services.cache import TTLCache
from app.utils.http import get_json

logger = get_logger(__name__)


def _is_active_admin_category(item: dict[str, Any]) -> bool:
    """Return True only for admin-added categories that should be visible."""
    if not item.get("name"):
        return False
    if item.get("isDeleted") is True:
        return False
    status = item.get("status")
    if status is False or str(status).lower() in {"false", "inactive", "0"}:
        return False
    if str(item.get("adminApproval", "")).lower() == "rejected":
        return False
    return True


def _normalize_categories_payload(data: Any) -> list[dict[str, str]]:
    """Parse category list from API JSON; return [] when shape is invalid."""
    if data is None:
        return []

    if isinstance(data, dict):
        if data.get("error"):
            logger.warning("Category API returned error payload: %s", data.get("error"))
            return []
        for key in ("data", "categories", "result", "items"):
            nested = data.get(key)
            if isinstance(nested, list):
                data = nested
                break
        else:
            cat_id = data.get("id") or data.get("_id")
            name = data.get("name")
            if cat_id is not None and name:
                return [{"id": str(cat_id), "name": str(name)}]
            return []

    if not isinstance(data, list):
        logger.warning("Category API unexpected payload type: %s", type(data).__name__)
        return []

    items: list[dict[str, str]] = []
    for item in data:
        if not isinstance(item, dict):
            logger.warning("Category API skipped non-object item: %r", item)
            continue
        if not _is_active_admin_category(item):
            logger.info("Category API skipped inactive/deleted item: %s", item.get("name"))
            continue
        cat_id = item.get("id") or item.get("_id")
        name = item.get("name")
        if cat_id is None or not name:
            logger.warning("Category API skipped incomplete item: %s", item)
            continue
        items.append({"id": str(cat_id), "name": str(name)})
    return items


class CategoryService:
    def __init__(self) -> None:
        settings = get_settings()
        self.settings = settings
        self.cache = TTLCache[list[Category]](settings.categories_cache_ttl_seconds)

    def _load_active_categories_from_mongo(self) -> list[dict[str, str]]:
        """Fallback: active admin categories stored in MongoDB (not hardcoded)."""
        uri = self.settings.mongodb_uri
        if not uri:
            return []
        try:
            from pymongo import MongoClient

            client = MongoClient(uri, serverSelectionTimeoutMS=5000)
            db = client[self.settings.mongodb_db_name]
            coll = db[self.settings.mongodb_categories_collection]
            query = {"isDeleted": {"$ne": True}, "status": {"$ne": False}}
            items: list[dict[str, str]] = []
            for doc in coll.find(query, {"name": 1}):
                if doc.get("name"):
                    items.append({"id": str(doc["_id"]), "name": str(doc["name"])})
            logger.info("CATEGORIES_LOADED_FROM_MONGO: %s active categories", len(items))
            return items
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("CATEGORIES_MONGO_FALLBACK failed: %s", exc)
            return []

    def warmup(self) -> None:
        _ = self.get_categories(force_refresh=True)

    def get_categories(self, force_refresh: bool = False) -> list[Category]:
        cached = None if force_refresh else self.cache.get()
        if cached is not None:
            return cached

        raw: Any = None
        source = "Categories API"
        try:
            raw = get_json(self.settings.categories_api_url)
        except (httpx.RequestError, httpx.HTTPStatusError) as exc:
            logger.warning("Category API unreachable: %s", exc)

        items = _normalize_categories_payload(raw) if raw is not None else []
        if not items:
            source = "MongoDB admin categories"
            items = self._load_active_categories_from_mongo()

        if not items:
            logger.warning("No active admin categories available from API or MongoDB")
            self.cache.set([])
            return []

        categories = [Category.model_validate(item) for item in items]
        self.cache.set(categories)
        logger.info("Loaded %s categories from %s", len(categories), source)
        return categories

    def get_category_names(self) -> list[str]:
        return [c.name for c in self.get_categories()]

    def is_cached(self) -> bool:
        return self.cache.has_value()
