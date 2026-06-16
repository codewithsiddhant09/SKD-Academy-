from __future__ import annotations

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

        try:
            data = get_json(self.settings.categories_api_url)
        except (httpx.RequestError, httpx.HTTPStatusError) as exc:
            logger.warning(
                "Category API unreachable, using default categories fallback: %s",
                exc,
            )
            data = DEFAULT_CATEGORIES

        categories = [Category.model_validate(item) for item in data]
        self.cache.set(categories)
        logger.info("Loaded %s categories", len(categories))
        return categories

    def get_category_names(self) -> list[str]:
        return [c.name for c in self.get_categories()]

    def is_cached(self) -> bool:
        return self.cache.has_value()
