from __future__ import annotations

from typing import Any

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.schemas import Category
from app.services.cache import TTLCache
from app.utils.http import get_json

logger = get_logger(__name__)

DEFAULT_CATEGORIES = [
    {"id": "1", "name": "Hair"},
    {"id": "2", "name": "Body"},
    {"id": "3", "name": "Nails"},
    {"id": "4", "name": "Face"},
    {"id": "5", "name": "Makeup"},
    {"id": "6", "name": "Henna"},
    {"id": "7", "name": "Hair Removal"},
    {"id": "8", "name": "Bath Treatment"},
]


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

    def warmup(self) -> None:
        _ = self.get_categories(force_refresh=True)

    def get_categories(self, force_refresh: bool = False) -> list[Category]:
        cached = None if force_refresh else self.cache.get()
        if cached is not None:
            return cached

        raw: Any
        try:
            raw = get_json(self.settings.categories_api_url)
        except (httpx.RequestError, httpx.HTTPStatusError) as exc:
            logger.warning(
                "Category API unreachable, using default categories fallback: %s",
                exc,
            )
            raw = DEFAULT_CATEGORIES

        items = _normalize_categories_payload(raw)
        if not items:
            logger.warning("Category API returned no valid categories; using defaults")
            items = DEFAULT_CATEGORIES

        categories = [Category.model_validate(item) for item in items]
        self.cache.set(categories)
        logger.info("Loaded %s categories", len(categories))
        return categories

    def get_category_names(self) -> list[str]:
        return [c.name for c in self.get_categories()]

    def is_cached(self) -> bool:
        return self.cache.has_value()
