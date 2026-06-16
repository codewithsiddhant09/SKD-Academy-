from app.models.schemas import Salon, SalonRecommendation
from app.services.ranking_service import RankingService


class SalonRankingAgent:
    def __init__(self) -> None:
        self._service = RankingService()

    def rank(self, salons: list[Salon], service: str, radius_km: int) -> list[SalonRecommendation]:
        return self._service.rank(salons=salons, service=service, radius_km=radius_km)
