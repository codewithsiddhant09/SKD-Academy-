from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from app.core.logging import get_logger
from app.models.schemas import BookingPayload, BookingResponse

logger = get_logger(__name__)


class BookingService:
    REQUIRED_FIELDS = ("salon", "service", "date", "time")

    def __init__(self) -> None:
        self._store: dict[str, BookingResponse] = {}

    def create_booking(self, payload: BookingPayload) -> BookingResponse:
        missing = [field for field in self.REQUIRED_FIELDS if not getattr(payload, field)]
        if missing:
            raise ValueError(f"Missing required booking fields: {', '.join(missing)}")

        booking_id = f"BKL-{datetime.utcnow().strftime('%Y%m%d')}-{uuid4().hex[:8].upper()}"
        response = BookingResponse(booking_id=booking_id, status="confirmed", payload=payload)
        self._store[booking_id] = response
        logger.info(
            "BOOKING_API_CALLED: salon=%s service=%s date=%s time=%s user_id=%s",
            payload.salon,
            payload.service,
            payload.date,
            payload.time,
            payload.user_id,
        )
        logger.info("BOOKING_STORED: booking_id=%s status=%s", booking_id, response.status)
        return response
