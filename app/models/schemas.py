from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.enums import IntentType


class Category(BaseModel):
    id: str
    name: str


class UserProfile(BaseModel):
    """User document loaded from MongoDB (field names mapped from the DB schema).

    Types are intentionally permissive because the live `users` collection
    stores some fields with varying shapes (e.g. `status` as a bool,
    `businessLocation` as an object, `serviceType` as a list). Values are
    normalized in `UserService._to_profile` before construction.
    """

    user_id: str
    full_name: str | None = None
    country_code: str | None = None
    phone_number: str | None = None
    email: str | None = None
    user_type: str | None = None
    is_verified: bool | None = None
    status: bool | str | None = None
    business_location: str | None = None
    service_type: str | None = None
    is_completed: bool | None = None
    admin_approval: str | None = None
    dob: str | None = None
    gender: str | None = None
    nationality: str | None = None


class SessionContext(BaseModel):
    """Lightweight per-session user context stored in conversation state."""

    user_id: str | None = None
    full_name: str | None = None
    email: str | None = None
    phone_number: str | None = None
    gender: str | None = None
    nationality: str | None = None
    business_location: str | None = None


class SessionMemory(BaseModel):
    """Explicit per-session fields persisted for the duration of a chat session."""

    selected_salon: str | None = None
    selected_service: str | None = None
    selected_category: str | None = None
    preferred_location: str | None = None
    appointment_date: str | None = None
    appointment_time: str | None = None
    last_intent: str | None = None
    salon_id: str | None = None
    booking_summary_shown: bool = False
    awaiting_confirmation: bool = False
    booking_status: str | None = None  # collecting | awaiting_confirmation | paused | completed

    def to_api_dict(self, conversation_history: list[dict[str, str]] | None = None) -> dict[str, Any]:
        return {
            "selectedSalon": self.selected_salon,
            "selectedService": self.selected_service,
            "selectedCategory": self.selected_category,
            "preferredLocation": self.preferred_location,
            "appointmentDate": self.appointment_date,
            "appointmentTime": self.appointment_time,
            "lastIntent": self.last_intent,
            "salonId": self.salon_id,
            "bookingSummaryShown": self.booking_summary_shown,
            "awaitingConfirmation": self.awaiting_confirmation,
            "bookingStatus": self.booking_status,
            "conversationHistory": conversation_history or [],
        }


class ChatRequest(BaseModel):
    session_id: str = Field(..., min_length=1)
    message: str = Field(..., min_length=1)
    user_id: str | None = None


class SessionStartRequest(BaseModel):
    session_id: str = Field(..., min_length=1)
    user_id: str | None = None


class SessionStartResponse(BaseModel):
    session_id: str
    greeting: str
    context: SessionContext


class IntentAnalysis(BaseModel):
    intent: IntentType
    category: str | None = None
    service: str | None = None
    location: str | None = None
    confidence: float | None = None
    reason: str | None = None


class LocationAnalysis(BaseModel):
    normalized_location: str
    radius_km: int = Field(default=15, ge=1, le=50)


class Salon(BaseModel):
    vendor_id: str
    salon_name: str
    categories: list[str]
    services: list[str]
    location: str
    image: str | None = None
    rating: float = Field(ge=0, le=5)
    availability_score: float = Field(default=0.8, ge=0, le=1)
    distance_km: float = Field(default=0, ge=0)


class SalonRecommendation(BaseModel):
    vendor_id: str | None = None
    salon_name: str
    rating: float
    distance: str
    reason: str
    score: float
    location: str | None = None
    services: list[str] = Field(default_factory=list)
    image: str | None = None
    redirect_url: str | None = None


class BookingPayload(BaseModel):
    customer_name: str | None = None
    phone: str | None = None
    salon: str | None = None
    salon_id: str | None = None
    service: str | None = None
    category: str | None = None
    date: str | None = None
    time: str | None = None
    user_id: str | None = None


class BookAppointmentRequest(BookingPayload):
    session_id: str = Field(..., min_length=1)


class BookingResponse(BaseModel):
    booking_id: str
    status: str
    payload: BookingPayload


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    intent: IntentType
    structured: dict[str, Any] = Field(default_factory=dict)
    recommendations: list[SalonRecommendation] = Field(default_factory=list)


class DebugIntentRequest(BaseModel):
    message: str = Field(..., min_length=1)


class DebugIntentResponse(BaseModel):
    message: str
    intent: IntentType
    category: str | None = None
    service: str | None = None
    explanation: str


class DebugRagRequest(BaseModel):
    question: str = Field(..., min_length=1)


class DebugRagResponse(BaseModel):
    question: str
    retrieved_chunks: list[str]
    similarity_scores: list[float]
    context: str
    prompt: str
    answer: str
    explanation: str | None = None


class Message(BaseModel):
    role: str
    content: str
    ts: datetime = Field(default_factory=datetime.utcnow)


class HealthResponse(BaseModel):
    status: str
    app: str
    rag_ready: bool
    categories_cached: bool
