from app.models.schemas import Salon
from app.services.salon_service import SalonService


class SalonDiscoveryAgent:
    def __init__(self) -> None:
        self._service = SalonService()

    def discover(self, category: str, service: str, location: str, radius_km: int) -> list[Salon]:
        return self._service.discover(category=category, service=service, location=location, radius_km=radius_km)
