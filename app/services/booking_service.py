from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import uuid4

import httpx

from app.core.config import get_settings
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

    def vat_percentage(self) -> float:
        return float(get_settings().booking_vat_percentage)

    def create_external_booking(
        self, payload: dict[str, Any], auth_headers: dict[str, str] | None = None
    ) -> dict[str, Any]:
        """Create a Bookly booking once; never retry ambiguous POST failures."""
        settings = get_settings()
        try:
            with httpx.Client(timeout=settings.booking_api_timeout_seconds, verify=settings.booking_api_verify_ssl) as client:
                response = client.post(settings.booking_create_api_url, json=payload, headers=auth_headers or {})
                response.raise_for_status()
                result = response.json()
        except httpx.TimeoutException as exc:
            raise RuntimeError("Booking request timed out; verify booking status before retrying.") from exc
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(f"Booking API returned HTTP {exc.response.status_code}: {exc.response.text[:500]}") from exc
        except httpx.RequestError as exc:
            raise RuntimeError(f"Booking API request failed: {exc}") from exc
        except ValueError as exc:
            raise RuntimeError("Booking API returned invalid JSON.") from exc

        if not isinstance(result, dict) or result.get("error") is True:
            message = result.get("message", "Booking API rejected the booking.") if isinstance(result, dict) else "Booking API returned an invalid response."
            raise RuntimeError(str(message))
        booking = (result.get("results") or {}).get("booking") if isinstance(result.get("results"), dict) else None
        if not isinstance(booking, dict) or not booking.get("_id") or not booking.get("orderId"):
            raise RuntimeError("Booking API response did not contain both booking _id and orderId.")
        return result

    def view_external_booking(self, booking_id: str, auth_headers: dict[str, str]) -> dict[str, Any]:
        """Fetch one Bookly booking using the app's Bookly API token."""
        settings = get_settings()
        url = f"{settings.booking_view_api_url.rstrip('/')}/{booking_id}"
        headers = {
            "x-auth-language": auth_headers.get("x-auth-language", "English"),
            "x-user-type": auth_headers.get("x-user-type", "User"),
            "x-auth-token": auth_headers.get("x-auth-token") or get_settings().bookly_api_token,
        }
        if not headers["x-auth-token"]:
            raise RuntimeError("BOOKLY_API_TOKEN is not configured.")
        try:
            with httpx.Client(timeout=settings.booking_api_timeout_seconds, verify=settings.booking_api_verify_ssl) as client:
                response = client.get(url, headers=headers)
                response.raise_for_status()
                result = response.json()
        except httpx.TimeoutException as exc:
            raise RuntimeError("Booking lookup timed out; please try again later.") from exc
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(f"Booking API returned HTTP {exc.response.status_code}: {exc.response.text[:500]}") from exc
        except httpx.RequestError as exc:
            raise RuntimeError(f"Booking API request failed: {exc}") from exc
        except ValueError as exc:
            raise RuntimeError("Booking API returned invalid JSON.") from exc

        if not isinstance(result, dict) or result.get("error") is True:
            message = result.get("message", "Booking lookup failed.") if isinstance(result, dict) else "Booking API returned an invalid response."
            raise RuntimeError(str(message))
        booking = (result.get("results") or {}).get("booking") if isinstance(result.get("results"), dict) else None
        if not isinstance(booking, dict) or str(booking.get("_id")) != booking_id:
            raise RuntimeError("Booking API response did not contain the requested booking details.")
        if not booking.get("orderId"):
            raise RuntimeError("Booking API response did not contain the booking orderId.")
        booking["bookingId"] = booking.get("_id")
        booking["bookingStatus"] = booking.get("bookingStatus", booking.get("status"))
        booking["paymentStatus"] = booking.get("paymentStatus", booking.get("payment_status"))
        booking["finalAmount"] = booking.get("finalAmount", booking.get("final_amount"))
        booking["date"] = booking.get("date", booking.get("requestedDate"))
        booking["slot"] = booking.get("slot", booking.get("requestedTime"))
        booking["services"] = booking.get("services") or booking.get("serviceId") or []
        return booking


    def create_booking(self, payload: BookingPayload) -> BookingResponse:
        """Legacy local booking response for the non-conversational endpoint."""
        missing = [field for field in self.REQUIRED_FIELDS if not getattr(payload, field)]
        if missing:
            raise ValueError(f"Missing required booking fields: {', '.join(missing)}")
        booking_id = f"BKL-{datetime.now():%Y%m%d}-{uuid4().hex[:8].upper()}"
        response = BookingResponse(booking_id=booking_id, status="pending", payload=payload)
        self._memory[booking_id] = response
        return response
