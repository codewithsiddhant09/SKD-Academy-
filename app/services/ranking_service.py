from __future__ import annotations

from app.models.schemas import Salon, SalonRecommendation
from app.utils.text import normalize_text


class RankingService:
    def _service_match_score(self, service: str, salon: Salon) -> float:
        target = normalize_text(service)
        services = [normalize_text(s) for s in salon.services]
        if target in services:
            return 1.0
        if any(target in s or s in target for s in services):
            return 0.75
        return 0.4

    def _distance_score(self, distance_km: float, radius: int) -> float:
        if radius <= 0:
            return 0.0
        score = max(0.0, 1 - (distance_km / radius))
        return min(score, 1.0)

    def rank(self, salons: list[Salon], service: str, radius_km: int) -> list[SalonRecommendation]:
        items: list[SalonRecommendation] = []
        for salon in salons:
            service_match = self._service_match_score(service, salon)
            distance = self._distance_score(salon.distance_km, radius_km)
            rating_norm = salon.rating / 5
            availability = salon.availability_score

            score = (
                0.40 * service_match
                + 0.30 * distance
                + 0.20 * rating_norm
                + 0.10 * availability
            )
            if service and service.strip():
                reason = f"Best match for {service} based on service fit, distance, and rating."
            else:
                reason = "Recommended based on rating and proximity."
            items.append(
                SalonRecommendation(
                    vendor_id=salon.vendor_id,
                    salon_name=salon.salon_name,
                    rating=salon.rating,
                    distance=f"{salon.distance_km:.1f}km",
                    reason=reason,
                    score=round(score, 4),
                    location=salon.location,
                    services=salon.services,
                    redirect_url=f"/salon/{salon.vendor_id}" if salon.vendor_id else None,
                )
            )
        return sorted(items, key=lambda s: s.score, reverse=True)
