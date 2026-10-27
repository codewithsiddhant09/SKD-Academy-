import hmac
import re

from fastapi import APIRouter, Header, HTTPException, Request

from app.api import deps


router = APIRouter()
_BOOKING_ID_RE = re.compile(r"^[A-Fa-f0-9]{24}$")


@router.get("/bookings/{booking_id}")
def view_booking(
    booking_id: str,
    x_auth_language: str | None = Header(default=None, alias="x-auth-language"),
    x_user_type: str | None = Header(default=None, alias="x-user-type"),
    x_auth_token: str | None = Header(default=None, alias="x-auth-token-user"),
) -> dict:
    x_auth_language = x_auth_language or "English"
    x_user_type = x_user_type or "User"
    if not _BOOKING_ID_RE.fullmatch(booking_id):
        raise HTTPException(status_code=400, detail="Invalid booking ID")
    missing = [
        name for name, value in (
            ("x-auth-language", x_auth_language),
            ("x-user-type", x_user_type),
            ("x-auth-token-user", x_auth_token),
        ) if not value
    ]
    if missing:
        raise HTTPException(status_code=401, detail=f"Missing required authentication headers: {', '.join(missing)}")
    if deps.assistant is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    if not x_auth_token:
        raise HTTPException(status_code=401, detail="Missing required authentication header: x-auth-token-user")

    try:
        booking = deps.assistant.bookings.view_external_booking(
            booking_id,
            {
                "x-auth-language": x_auth_language,
                "x-user-type": x_user_type,
                "x-auth-token-user": x_auth_token,
            },
        )
    except RuntimeError as exc:
        message = str(exc)
        status_code = next((code for code in (400, 401, 403, 404, 422) if f"HTTP {code}" in message), 502)
        raise HTTPException(status_code=status_code, detail=message) from exc

    return {"booking": _public_booking(booking)}


def _public_booking(booking: dict) -> dict:
    vendor = booking.get("vendorId") if isinstance(booking.get("vendorId"), dict) else {}
    services = booking.get("services") if isinstance(booking.get("services"), list) else []
    return {
        "booking_id": booking.get("_id"),
        "order_id": booking.get("orderId"),
        "booking_status": booking.get("bookingStatus"),
        "payment_status": booking.get("paymentStatus"),
        "payment_url": booking.get("paymentUrl") or booking.get("payment_url"),
        "payment_method": booking.get("paymentMethod") or booking.get("payment_method"),
        "service_ids": booking.get("serviceId") or booking.get("services") or [],
        "date": booking.get("date"),
        "slot": booking.get("slot"),
        "booking_type": booking.get("bookingType"),
        "appointment": booking.get("BookingAppointment"),
        "salon": vendor.get("businessName") or vendor.get("fullName"),
        "services": [
            {key: service.get(key) for key in ("_id", "name", "duration", "price") if key in service}
            for service in services if isinstance(service, dict)
        ],
        "final_amount": booking.get("finalAmount"),
        "vat": booking.get("vat"),
        "vat_percentage": booking.get("vatPercentage"),
        "contact": {
            key: (booking.get("contactId") or {}).get(key)
            for key in ("contactName", "address", "city", "zipCode")
            if isinstance(booking.get("contactId"), dict) and key in booking["contactId"]
        },
    }


@router.post("/book-appointment")
async def book_appointment(
    request: Request,
    x_auth_language: str | None = Header(default=None, alias="x-auth-language"),
    x_user_type: str | None = Header(default=None, alias="x-user-type"),
    x_auth_token: str | None = Header(default=None, alias="x-auth-token"),
) -> dict:
    if deps.assistant is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Request body must be valid JSON") from exc
    if not isinstance(payload, dict) or not payload:
        raise HTTPException(status_code=422, detail="Request body must be a non-empty Bookly booking object")

    whatsapp_mode = payload.get("mode") == "whatsapp"
    if whatsapp_mode:
        expected_secret = deps.assistant.settings.whatsapp_booking_secret
        supplied_secret = request.headers.get("x-whatsapp-booking-key", "")
        if not expected_secret or not hmac.compare_digest(supplied_secret, expected_secret):
            raise HTTPException(status_code=401, detail="Invalid WhatsApp booking credentials")
        try:
            result = await deps.assistant.bookings.create_external_booking(payload, {"x-whatsapp-booking-key": supplied_secret})
        except RuntimeError as exc:
            message = str(exc)
            status_code = next((code for code in (400, 401, 403, 404, 422) if f"HTTP {code}" in message), 502)
            raise HTTPException(status_code=status_code, detail=message) from exc
        booking = result["results"]["booking"]
        return {"booking": {"_id": booking.get("_id"), "orderId": booking.get("orderId"), **{key: booking[key] for key in ("bookingStatus", "paymentStatus", "paymentUrl", "paymentId") if key in booking}}}
    token = x_auth_token or deps.assistant.settings.bookly_api_token
    if not token:
        raise HTTPException(status_code=503, detail="BOOKLY_API_TOKEN is not configured")
    auth_headers = {
        "x-auth-language": x_auth_language or "English",
        "x-user-type": x_user_type or "User",
        "x-auth-token": token,
    }
    try:
        result = await deps.assistant.bookings.create_external_booking(payload, auth_headers)
    except RuntimeError as exc:
        message = str(exc)
        status_code = next((code for code in (400, 401, 403, 404, 422) if f"HTTP {code}" in message), 502)
        raise HTTPException(status_code=status_code, detail=message) from exc

    booking = result["results"]["booking"]
    return {"booking": {"_id": booking.get("_id"), "orderId": booking.get("orderId"), **{key: booking[key] for key in ("bookingStatus", "paymentStatus", "paymentUrl", "paymentId") if key in booking}}}


@router.get("/bookings/{order_id}/cancellation-quote")
def cancellation_quote(
    order_id: str,
    x_auth_language: str | None = Header(default="English", alias="x-auth-language"),
    x_user_type: str | None = Header(default="User", alias="x-user-type"),
    x_auth_token: str | None = Header(default=None, alias="x-auth-token"),
) -> dict:
    if deps.assistant is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    token = x_auth_token or deps.assistant.settings.bookly_api_token
    if not token:
        raise HTTPException(status_code=503, detail="BOOKLY_API_TOKEN is not configured")
    headers = {"x-auth-language": x_auth_language or "English", "x-user-type": x_user_type or "User", "x-auth-token": token}
    try:
        quote = deps.assistant.bookings.get_cancellation_amount(order_id, headers)
    except RuntimeError as exc:
        message = str(exc)
        status_code = next((code for code in (400, 401, 403, 404, 422) if f"HTTP {code}" in message), 502)
        raise HTTPException(status_code=status_code, detail=message) from exc
    return {"cancellation": quote}


@router.put("/bookings/cancel")
async def cancel_booking(
    request: Request,
    x_auth_language: str | None = Header(default="English", alias="x-auth-language"),
    x_user_type: str | None = Header(default="User", alias="x-user-type"),
    x_auth_token: str | None = Header(default=None, alias="x-auth-token"),
) -> dict:
    if deps.assistant is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Request body must be valid JSON") from exc
    token = x_auth_token or deps.assistant.settings.bookly_api_token
    if not token:
        raise HTTPException(status_code=503, detail="BOOKLY_API_TOKEN is not configured")
    headers = {"x-auth-language": x_auth_language or "English", "x-user-type": x_user_type or "User", "x-auth-token": token}
    try:
        result = await deps.assistant.bookings.cancel_external_booking(payload, headers)
    except RuntimeError as exc:
        message = str(exc)
        status_code = next((code for code in (400, 401, 403, 404, 422) if f"HTTP {code}" in message), 502)
        raise HTTPException(status_code=status_code, detail=message) from exc
    return {"result": result}

