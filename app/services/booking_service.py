from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from app.models.schemas import BookingPayload, BookingResponse


class BookingService:
    def __init__(self) -> None:
        self._store: dict[str, BookingResponse] = {}

    def create_booking(self, payload: BookingPayload) -> BookingResponse:
        booking_id = f"BKL-{datetime.utcnow().strftime('%Y%m%d')}-{uuid4().hex[:8].upper()}"
        response = BookingResponse(booking_id=booking_id, status="confirmed", payload=payload)
        self._store[booking_id] = response
        return response
