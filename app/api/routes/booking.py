from fastapi import APIRouter, HTTPException

from app.api import deps
from app.models.schemas import BookAppointmentRequest, BookingPayload, BookingResponse

router = APIRouter()


@router.post("/book-appointment", response_model=BookingResponse)
def book_appointment(payload: BookAppointmentRequest) -> BookingResponse:
    if deps.assistant is None:
        raise HTTPException(status_code=503, detail="Service not initialized")

    booking_payload = BookingPayload.model_validate(payload.model_dump(exclude={"session_id"}))
    missing = [f for f in ("customer_name", "phone", "salon", "service", "date", "time") if not getattr(booking_payload, f)]
    if missing:
        raise HTTPException(status_code=400, detail=f"Missing required fields: {', '.join(missing)}")

    return deps.assistant.bookings.create_booking(booking_payload)
