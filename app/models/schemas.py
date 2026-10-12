from __future__ import annotations

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




class ServiceOffer(BaseModel):
    """One service a salon offers (services collection)."""

    id: str
    name: str
    price: float | None = None
    duration: int | None = None
    category: str | None = None


class Salon(BaseModel):
    vendor_id: str
    salon_name: str
    categories: list[str]
    services: list[str]
    offers: list[ServiceOffer] = Field(default_factory=list)
    location: str
    image: str | None = None
    rating: float | None = Field(default=None, ge=0, le=5)


class SalonRecommendation(BaseModel):
    vendor_id: str | None = None
    salon_name: str
    rating: float | None = None
    reason: str
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




class DebugRagRequest(BaseModel):
    question: str = Field(..., min_length=1)


class DebugRagResponse(BaseModel):
    question: str
    retrieved_chunks: list[str]
    similarity_scores: list[float]
    sources: list[str | None]



class HealthResponse(BaseModel):
    status: str
    app: str
    rag_ready: bool
    categories_cached: bool
