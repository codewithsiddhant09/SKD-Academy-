from app.models.schemas import LocationAnalysis
from app.services.location_service import LocationService


class LocationAgent:
    def __init__(self) -> None:
        self._service = LocationService()

    def analyze(self, location: str) -> LocationAnalysis:
        return self._service.analyze(location)
