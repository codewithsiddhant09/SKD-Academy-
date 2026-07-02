from app.models.schemas import LocationAnalysis
from app.utils.location import sanitize_location
from app.utils.text import title_case_safe


class LocationService:
    def analyze(self, location: str) -> LocationAnalysis:
        cleaned = sanitize_location(location) or location.strip()
        normalized = title_case_safe(cleaned)
        radius = 10 if "marina" in normalized.lower() else 15
        return LocationAnalysis(normalized_location=normalized, radius_km=radius)
