from fastapi import APIRouter, HTTPException

from app.api import deps
from app.models.schemas import BookAppointmentRequest, BookingPayload, BookingResponse

router = APIRouter()


@router.post("/book-appointment", response_model=BookingResponse)
def book_appointment(payload: BookAppointmentRequest) -> BookingResponse:
    if deps.orchestrator_service is None:
        raise HTTPException(status_code=503, detail="Service not initialized")

    booking_service = deps.orchestrator_service.workflow.booking_service
    booking_payload = BookingPayload(
        customer_name=payload.customer_name,
        phone=payload.phone,
        salon=payload.salon,
        service=payload.service,
        date=payload.date,
        time=payload.time,
    )
    missing = [k for k, v in booking_payload.model_dump().items() if not v]
    if missing:
        raise HTTPException(status_code=400, detail=f"Missing required fields: {', '.join(missing)}")

    return booking_service.create_booking(booking_payload)
