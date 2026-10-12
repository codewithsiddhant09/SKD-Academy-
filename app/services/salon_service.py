from __future__ import annotations

import json
from pathlib import Path

from app.core.logging import get_logger
from app.models.schemas import Salon, ServiceOffer
from app.repositories.salon_repository import SalonRepository

logger = get_logger(__name__)

MOCK_FILE = Path(__file__).resolve().parent.parent / "data" / "mock_salons.json"


class SalonService:
    """Salon search. MongoDB is the source of truth; the bundled mock file is used
    only when MongoDB is not configured/reachable (local development and tests)."""

    def __init__(self, repository: SalonRepository | None = None) -> None:
        self._repository = repository or SalonRepository()

    def search(
        self,
        location: str | None = None,
        service: str | None = None,
        salon_name: str | None = None,
        category: str | None = None,
    ) -> list[Salon]:
        if self._repository.is_available():
            rows = self._repository.discover(
                location=location, service=service, category=category, salon_name=salon_name
            )
            logger.info("SALON_SEARCH: %s result(s) from MongoDB", len(rows))
            return [self._to_salon(row) for row in rows]

        logger.info("SALON_SEARCH: MongoDB unavailable, using mock_salons.json")
        return [s for s in self._load_mock() if self._mock_matches(s, location, service, salon_name, category)]

    def list_services(self, category: str, location: str | None = None) -> list[dict]:
        """Distinct services in `category` with price range and salon count."""
        if self._repository.is_available():
            return self._repository.list_services(category, location)
        salons = [s for s in self._load_mock() if self._mock_matches(s, location, None, None, category)]
        names = sorted({name for s in salons for name in s.services})
        return [
            {"service": n, "price_from": 100.0, "price_to": 100.0, "salons": sum(n in s.services for s in salons)}
            for n in names
        ]

    def get_by_ids(self, salon_ids: list[str]) -> list[Salon]:
        """Salons by vendor id (used for salons in a customer's booking history)."""
        if self._repository.is_available():
            return [self._to_salon(row) for row in self._repository.get_salons_by_ids(salon_ids)]
        return [s for s in self._load_mock() if s.vendor_id in salon_ids]

    @staticmethod
    def _to_salon(row: dict) -> Salon:
        return Salon(
            vendor_id=row["salonId"],
            salon_name=row["salonName"],
            categories=row.get("categories") or [],
            services=row.get("services") or [],
            offers=row.get("offers") or [],
            location=row.get("location") or "",
            image=row.get("image"),
            rating=row.get("rating"),
        )

    @staticmethod
    def _load_mock() -> list[Salon]:
        salons = [Salon.model_validate(item) for item in json.loads(MOCK_FILE.read_text(encoding="utf-8"))]
        for salon in salons:
            salon.offers = [
                ServiceOffer(id=f"mock-{salon.vendor_id}-{i}", name=name, price=100.0, duration=30)
                for i, name in enumerate(salon.services)
            ]
        return salons

    @staticmethod
    def _mock_matches(
        salon: Salon, location: str | None, service: str | None, salon_name: str | None, category: str | None = None
    ) -> bool:
        def contains(haystack: str, needle: str | None) -> bool:
            return not needle or needle.lower() in haystack.lower()

        return (
            contains(salon.location, location)
            and contains(salon.salon_name, salon_name)
            and (not service or any(contains(s, service) for s in salon.services))
            and (not category or any(contains(c, category) for c in salon.categories))
        )
