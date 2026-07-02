from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from app.models.enums import IntentType
from app.models.schemas import BookingPayload, IntentAnalysis, LocationAnalysis, SalonRecommendation


class RouteTarget(str, Enum):
    GREETING = "greeting"
    PLATFORM_INFORMATION = "platform_information"
    AI_INFORMATION = "ai_information"
    CATEGORY_LIST = "category_list"
    CATEGORY_DETAIL = "category_detail"
    SALON_SEARCH = "salon_search"
    BOOKING = "booking"
    FAQ = "faq"
    FALLBACK = "fallback"


class PendingQuestion(str, Enum):
    NONE = "none"
    SERVICE = "service"
    LOCATION = "location"
    SALON = "salon"
    DATE = "date"
    TIME = "time"
    CONFIRMATION = "confirmation"


class ExtractedEntities(BaseModel):
    service: str | None = None
    category: str | None = None
    location: str | None = None
    salon: str | None = None
    salon_id: str | None = None
    date: str | None = None
    time: str | None = None
    confirmed: bool | None = None
    declined: bool | None = None
    salon_search: bool = False


class OrchestrationContext(BaseModel):
    session_id: str
    user_message: str
    history: list[dict[str, str]] = Field(default_factory=list)
    intent: IntentAnalysis
    entities: ExtractedEntities = Field(default_factory=ExtractedEntities)
    pending_question: PendingQuestion = PendingQuestion.NONE
    resume_booking_after_faq: bool = False


class HandlerResult(BaseModel):
    intent: IntentType
    reply: str = ""
    category: str | None = None
    service: str | None = None
    location: str | None = None
    location_analysis: LocationAnalysis | None = None
    recommendations: list[SalonRecommendation] = Field(default_factory=list)
    booking_payload: BookingPayload | None = None
    booking_response: dict[str, Any] | None = None
    booking_stage: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
