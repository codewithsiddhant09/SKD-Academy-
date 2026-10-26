from __future__ import annotations

from typing import Any, Literal

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
    status: bool | str | None = None
    business_location: str | None = None
    service_type: str | None = None
    is_completed: bool | None = None
    admin_approval: str | None = None
    dob: str | None = None
    gender: str | None = None
    nationality: str | None = None
    address: str | None = None
    city: str | None = None
    zip_code: str | None = None
    latitude: float | None = None
    longitude: float | None = None


class SessionContext(BaseModel):
    model_config = {"extra": "ignore"}

    """Lightweight per-session user context stored in conversation state."""

    user_id: str | None = None
    full_name: str | None = None
    email: str | None = None
    phone_number: str | None = None
    country_code: str | None = None
    gender: str | None = None
    nationality: str | None = None
    business_location: str | None = None
    address: str | None = None
    city: str | None = None
    zip_code: str | None = None
    latitude: float | None = None
    longitude: float | None = None


class ChatRequest(BaseModel):
    session_id: str = Field(..., min_length=1)
    message: str = Field(..., min_length=1)
    user_id: str | None = None


class SessionStartRequest(BaseModel):
    session_id: str = Field(..., min_length=1)
    user_id: str | None = None

class LoginResponse(BaseModel):
    authenticated: bool
    user_id: str


class BookingContactUpdate(BaseModel):
    address: str = Field(..., min_length=3)
    city: str = Field(..., min_length=2)
    zip_code: str = Field(..., min_length=2)
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    country_code: str = Field(..., min_length=1)
    contact_name: str | None = None
    email: str | None = None
    phone_number: str | None = None
    booking_appointment: str = "Home"
    additional_note: str | None = None
    booking_appointment: str = "Home"
    coupon_id: str | None = None
    discount_amount: float | None = None
    final_amount: float | None = None
    vat: float | None = None


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
