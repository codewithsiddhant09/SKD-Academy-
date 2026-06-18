from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.enums import IntentType


class Category(BaseModel):
    id: str
    name: str


class UserProfile(BaseModel):
    """User document loaded from MongoDB (field names mapped from the DB schema)."""

    user_id: str
    full_name: str | None = None
    country_code: str | None = None
    phone_number: str | None = None
    email: str | None = None
    user_type: str | None = None
    is_verified: bool | None = None
    status: str | None = None
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
