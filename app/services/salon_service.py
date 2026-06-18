from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.logging import get_logger
from app.models.schemas import Salon
from app.repositories.salon_repository import SalonRepository
from app.utils.http import get_json
from app.utils.text import normalize_text

logger = get_logger(__name__)


class SalonService:
    def __init__(self, repository: SalonRepository | None = None) -> None:
        self._mock_file = Path(__file__).resolve().parent.parent / "data" / "mock_salons.json"
        self._repository = repository or SalonRepository()

    # ------------------------------------------------------------------ #
    # Discovery (MongoDB first, mock fallback)
    # ------------------------------------------------------------------ #
    def discover(
        self,
        category: str,
        service: str,
        location: str,
        radius_km: int,
    ) -> list[Salon]:
        # 1) Primary source: MongoDB salon discovery.
        try:
            mongo_results = self._repository.discover(
                location=location,
                category=category,
                service=service,
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Salon discovery via MongoDB failed: %s", exc)
            mongo_results = []

        if mongo_results:
            salons = [self._to_salon(item) for item in mongo_results]
            logger.info("Cards Returned: %s salon card(s) from MongoDB", len(salons))
            return salons

        # 2) Fallback: bundled mock data (keeps the demo populated).
        logger.info("MongoDB returned no salons; falling back to mock_salons.json")
        salons = self._discover_mock(
            category=category, service=service, location=location, radius_km=radius_km
        )
        logger.info("Cards Returned: %s salon card(s) from mock fallback", len(salons))
        return salons

    def _to_salon(self, item: dict[str, Any]) -> Salon:
        rating = item.get("rating")
        return Salon(
            vendor_id=str(item.get("salonId")),
            salon_name=item.get("salonName") or "Salon",
            categories=item.get("categories") or [],
            services=item.get("services") or [],
            location=item.get("location") or "",
            image=item.get("image"),
            rating=float(rating) if rating is not None else 0.0,
            availability_score=0.8,
            distance_km=0.0,
        )

    # ------------------------------------------------------------------ #
    # Mock fallback (unchanged matching logic)
    # ------------------------------------------------------------------ #
    def _load_mock_salons(self) -> list[Salon]:
        data = json.loads(self._mock_file.read_text(encoding="utf-8"))
        return [Salon.model_validate(item) for item in data]

    def _discover_mock(
        self,
        category: str,
        service: str,
        location: str,
        radius_km: int,
    ) -> list[Salon]:
        category_n = normalize_text(category)
        service_n = normalize_text(service)
        location_n = normalize_text(location)

        salons = self._load_mock_salons()
        matched: list[Salon] = []
        for salon in salons:
            categories = [normalize_text(c) for c in salon.categories]
            services = [normalize_text(s) for s in salon.services]
            location_match = location_n in normalize_text(salon.location)
            category_match = category_n in categories
            service_match = any(service_n in s or s in service_n for s in services)
            distance_match = salon.distance_km <= radius_km

            if category_match and service_match and location_match and distance_match:
                matched.append(salon)

        return matched

    def get_salon_details(self, vendor_id: str, base_url: str) -> dict:
        return get_json(f"{base_url}/{vendor_id}")
