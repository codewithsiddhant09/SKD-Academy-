from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import uuid4

from app.core.logging import get_logger
from app.models.schemas import BookingPayload, BookingResponse
from app.repositories.booking_repository import BookingRepository

logger = get_logger(__name__)

# Used only without MongoDB (local dev/tests): every salon open 10:00-19:00.
MOCK_HOURS = (10 * 60, 19 * 60)


class BookingService:
    """Availability, history and booking requests. MongoDB when configured,
    in-memory otherwise so the assistant still runs locally and in tests."""

    REQUIRED_FIELDS = ("salon", "service", "date", "time")

    def __init__(self, repository: BookingRepository | None = None) -> None:
        self._repository = repository or BookingRepository()
        self._memory: dict[str, Any] = {}

    def working_hours(self, salon_id: str, day: date) -> tuple[int, int] | None:
        """(open, close) minutes after midnight, or None when the salon is closed that day."""
        if self._repository.is_available():
            return self._repository.working_hours(salon_id, day)
        return MOCK_HOURS

    def next_available_dates(self, salon_ids: list[str], from_day: date) -> dict[str, str]:
        if self._repository.is_available():
            return self._repository.next_available_dates(salon_ids, from_day)
        return {sid: from_day.isoformat() for sid in salon_ids}

    def history(self, user_id: str) -> dict[str, list[dict[str, Any]]]:
        if self._repository.is_available():
            return self._repository.user_history(user_id)
        return {"bookings": [], "requests": []}

    def submit_request(self, doc: dict[str, Any]) -> str:
        """Store a booking request for the salon to accept; returns its request id."""
        if self._repository.is_available():
            return self._repository.insert_request(doc)
        request_id = f"BKLY-{datetime.now():%d%m%Y}-{uuid4().hex[:3].upper()}"
        self._memory[request_id] = {**doc, "request_id": request_id, "status": "pending", "bookingStatus": "Pending"}
        logger.info("BOOKING_REQUEST_STORED_IN_MEMORY: %s", request_id)
        return request_id

    def find_request(self, request_id: str) -> dict[str, Any] | None:
        if self._repository.is_available():
            return self._repository.find_request(request_id)
        return self._memory.get(request_id.strip().upper())

    def update_request(self, request_id: str, expected_status: str, fields: dict[str, Any]) -> bool:
        """Change a request in place, keeping its request_id. False if its status changed meanwhile."""
        if self._repository.is_available():
            return self._repository.update_request(request_id, expected_status, fields)
        doc = self._memory.get(request_id)
        if not doc or doc.get("status") != expected_status:
            return False
        doc.update(fields)
        return True

    def create_booking(self, payload: BookingPayload) -> BookingResponse:
        """Legacy POST /book-appointment (kept in memory; not sent to salons)."""
        missing = [field for field in self.REQUIRED_FIELDS if not getattr(payload, field)]
        if missing:
            raise ValueError(f"Missing required booking fields: {', '.join(missing)}")
        booking_id = f"BKL-{datetime.now():%Y%m%d}-{uuid4().hex[:8].upper()}"
        response = BookingResponse(booking_id=booking_id, status="confirmed", payload=payload)
        self._memory[booking_id] = response
        return response
