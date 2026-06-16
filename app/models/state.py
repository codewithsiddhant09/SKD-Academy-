from typing import Any, TypedDict

from app.models.schemas import BookingPayload, IntentAnalysis, LocationAnalysis, SalonRecommendation


class GraphState(TypedDict, total=False):
    session_id: str
    user_message: str
    history: list[dict[str, str]]
    intent_analysis: IntentAnalysis
    category: str
    service: str
    location: str
    salon_search: bool
    location_analysis: LocationAnalysis
    recommendations: list[SalonRecommendation]
    booking_payload: BookingPayload
    booking_stage: str
    reply: str
    metadata: dict[str, Any]
