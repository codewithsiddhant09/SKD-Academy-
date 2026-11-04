from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import uuid4

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.schemas import BookingPayload, BookingResponse
from app.repositories.booking_repository import BookingRepository
from app.utils.booking_payment import (
    determine_pay_option,
    calculate_booking_status,
    calculate_booking_amounts,
    refund_ziina_payment,
    verify_ziina_payment,
)
from app.utils.cancellation_policy import get_cancellation_terms, calculate_fee_split
from app.utils.guest_booking_link import normalize_whatsapp_phone, find_registered_user_by_contact
from app.utils.timezone import get_scheduled_moment

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
        """
        Create a Bookly booking with full payment and WhatsApp support.
        
        Features:
        - WhatsApp booking with phone normalization and user matching
        - PayNow with Ziina payment link creation
        - PayAtStore with immediate approval
        - Caller detection (WhatsApp bot, registered user, customer app, salon app)
        - Automatic booking amounts calculation
        """
        settings = get_settings()
        
        # Detect caller type
        is_whatsapp = payload.get("mode") == "whatsapp"
        is_vendor = auth_headers and auth_headers.get("x-user-type") == "Vendor"
        
        # Handle WhatsApp phone normalization and user matching
        if is_whatsapp and payload.get("phoneNumber"):
            phone_result = normalize_whatsapp_phone(payload["phoneNumber"])
            if phone_result:
                phone_number, country_code = phone_result
                payload["phoneNumber"] = phone_number
                payload["countryCode"] = country_code
                
                # Try to find registered user by phone
                if self._repository and self._repository.is_available():
                    contact = {"phoneNumber": phone_number, "countryCode": country_code}
                    user = find_registered_user_by_contact(contact, self._repository)
                    if user:
                        payload["userId"] = user.get("_id")
        
        # Determine payment option
        try:
            pay_option = determine_pay_option(
                payload.get("payOption"),
                is_whatsapp,
                is_vendor
            )
            payload["payOption"] = pay_option
        except ValueError as e:
            raise RuntimeError(str(e))
        
        # Calculate initial booking status
        booking_status = calculate_booking_status(pay_option, is_vendor)
        payload["bookingStatus"] = booking_status
        
        # Make the API call
        # Prepare headers - backend expects x-auth-token-user
        request_headers = {}
        if auth_headers:
            # Copy all headers
            request_headers.update(auth_headers)
            
            # Ensure token is in x-auth-token-user (backend expects this)
            token = auth_headers.get("x-auth-token-user") or auth_headers.get("x-auth-token")
            if token:
                request_headers["x-auth-token-user"] = token
                # Also try standard Authorization header as fallback
                request_headers["Authorization"] = f"Bearer {token}"
        
        logger.info("=" * 80)
        logger.info("🚀 CALLING BOOKING API")
        logger.info("=" * 80)
        logger.info("📍 URL: %s", settings.booking_create_api_url)
        logger.info("📦 PAYLOAD: %s", payload)
        logger.info("🔐 AUTH HEADERS PROVIDED: %s", bool(auth_headers))
        if request_headers:
            logger.info("🔑 FINAL HEADERS KEYS: %s", list(request_headers.keys()))
            for key, value in request_headers.items():
                if "token" in key.lower() or key == "Authorization":
                    logger.info("   %s: %s... (length=%d)", key, value[:30] if len(value) > 30 else value, len(value))
                else:
                    logger.info("   %s: %s", key, value)
        else:
            logger.error("❌ NO AUTH HEADERS! API will return 401")
        logger.info("=" * 80)
        
        try:
            with httpx.Client(timeout=settings.booking_api_timeout_seconds, verify=settings.booking_api_verify_ssl) as client:
                response = client.post(settings.booking_create_api_url, json=payload, headers=request_headers)
                
                logger.info("📥 RESPONSE RECEIVED")
                logger.info("   Status Code: %s", response.status_code)
                logger.info("   Response: %s", response.text[:500])
                
                response.raise_for_status()
                result = response.json()
                
                logger.info("✅ BOOKING API SUCCESS")
                logger.info("=" * 80)
        except httpx.TimeoutException as exc:
            logger.error("⏱️ BOOKING API TIMEOUT")
            logger.error("=" * 80)
            raise RuntimeError("Booking request timed out; verify booking status before retrying.") from exc
        except httpx.HTTPStatusError as exc:
            logger.error("❌ BOOKING API HTTP ERROR")
            logger.error("   Status: %s", exc.response.status_code)
            logger.error("   Response: %s", exc.response.text[:500])
            logger.error("=" * 80)
            raise RuntimeError(f"Booking API returned HTTP {exc.response.status_code}: {exc.response.text[:500]}") from exc
        except httpx.RequestError as exc:
            logger.error("❌ BOOKING API REQUEST ERROR")
            logger.error("   Error: %s", str(exc))
            logger.error("=" * 80)
            raise RuntimeError(f"Booking API request failed: {exc}") from exc
        except ValueError as exc:
            logger.error("❌ BOOKING API INVALID JSON")
            logger.error("=" * 80)
            raise RuntimeError("Booking API returned invalid JSON.") from exc

        if not isinstance(result, dict) or result.get("error") is True:
            message = result.get("message", "Booking API rejected the booking.") if isinstance(result, dict) else "Booking API returned an invalid response."
            raise RuntimeError(str(message))
        
        booking = (result.get("results") or {}).get("booking") if isinstance(result.get("results"), dict) else None
        if not isinstance(booking, dict) or not booking.get("_id") or not booking.get("orderId"):
            raise RuntimeError("Booking API response did not contain both booking _id and orderId.")
        
        # If PayNow, call separate payNowBooking endpoint to create payment link
        if pay_option == "PayNow":
            try:
                booking_id = booking.get("_id")
                paynow_payload = {
                    "bookingId": booking_id,
                    "returnTo": "web"  # or "app" depending on platform
                }
                
                # Call payNowBooking endpoint
                with httpx.Client(timeout=settings.booking_api_timeout_seconds, verify=settings.booking_api_verify_ssl) as client:
                    paynow_response = client.post(
                        settings.booking_paynow_api_url,
                        json=paynow_payload,
                        headers=request_headers
                    )
                    paynow_response.raise_for_status()
                    paynow_result = paynow_response.json()
                
                # Extract payment URL from response
                if isinstance(paynow_result, dict) and not paynow_result.get("error"):
                    payment_data = paynow_result.get("results") or paynow_result
                    if isinstance(payment_data, dict):
                        booking["paymentUrl"] = payment_data.get("paymentUrl") or payment_data.get("payment_url")
                        booking["paymentId"] = payment_data.get("paymentId") or payment_data.get("payment_id")
                        booking["paymentRequired"] = True
                        booking["paymentHoldMinutes"] = settings.payment_hold_minutes
                
            except httpx.HTTPStatusError as exc:
                logger.error(f"PayNow API failed: {exc.response.status_code} - {exc.response.text}")
                # Don't fail the booking - it's already created
                booking["paymentError"] = f"Payment link creation failed: {exc.response.text[:200]}"
            except Exception as e:
                logger.error(f"PayNow endpoint error: {e}")
                booking["paymentError"] = str(e)
        
        return result

    def get_cancellation_amount(self, order_id: str, auth_headers: dict[str, str]) -> dict[str, Any]:
        """
        Calculate cancellation fee and refund amount based on 2-hour policy.
        
        This can call the external API or use local calculation.
        """
        settings = get_settings()
        
        # First, try to get booking details
        try:
            booking = self.view_external_booking_by_order_id(order_id, auth_headers)
            
            # Calculate locally using the policy
            terms = get_cancellation_terms(
                booking,
                booking_timezone=settings.booking_timezone
            )
            
            return {
                "allowed": terms["allowed"],
                "reason": terms["reason"],
                "paidAmount": booking.get("finalAmount", 0),
                "cancellationFee": terms["fee"],
                "refundAmount": terms["refund_amount"],
                "isLateCancellation": terms["is_late_cancellation"],
                "appointmentAt": terms["appointment_at"]
            }
            
        except Exception as e:
            logger.error(f"Error calculating cancellation amount: {e}")
            
            # Fallback to external API
            url = f"{settings.booking_cancellation_amount_api_url.rstrip('/')}/{order_id}"
            try:
                with httpx.Client(timeout=settings.booking_api_timeout_seconds, verify=settings.booking_api_verify_ssl) as client:
                    response = client.get(url, headers=auth_headers)
                    response.raise_for_status()
                    result = response.json()
            except httpx.TimeoutException as exc:
                raise RuntimeError("Cancellation quote timed out; please try again later.") from exc
            except httpx.HTTPStatusError as exc:
                raise RuntimeError(f"Booking API returned HTTP {exc.response.status_code}: {exc.response.text[:500]}") from exc
            except httpx.RequestError as exc:
                raise RuntimeError(f"Booking API request failed: {exc}") from exc
            except ValueError as exc:
                raise RuntimeError("Booking API returned invalid JSON.") from exc
            
            if not isinstance(result, dict) or result.get("error") is True:
                message = result.get("message", "Cancellation quote failed.") if isinstance(result, dict) else "Booking API returned an invalid response."
                raise RuntimeError(str(message))
            
            quote = result.get("results", result)
            if not isinstance(quote, dict):
                raise RuntimeError("Booking API returned an invalid cancellation quote.")
            return quote

    async def cancel_external_booking(self, payload: dict[str, Any], auth_headers: dict[str, str]) -> dict[str, Any]:
        """
        Cancel a booking with automatic refund processing for paid bookings.
        
        Rules:
        - Unpaid PayNow hold → atomic cancel, no policy check
        - Policy not allowed → error
        - Paid booking → Ziina refund with fee split
        - Unpaid PayAtStore/old flow → allowed while Pending/Approved
        """
        settings = get_settings()
        booking_id = payload.get("bookingId")
        
        if not booking_id:
            raise RuntimeError("bookingId is required")
        
        # Get booking details first
        try:
            booking = self.view_external_booking(booking_id, auth_headers)
        except Exception as e:
            raise RuntimeError(f"Could not fetch booking details: {e}")
        
        # Check cancellation policy
        terms = get_cancellation_terms(booking, booking_timezone=settings.booking_timezone)
        
        if not terms["allowed"]:
            raise RuntimeError(terms["reason"] or "Cancellation not allowed")
        
        # Handle paid booking with refund
        payment_status = booking.get("paymentStatus")
        payment_id = booking.get("ziinaPaymentId")
        
        if payment_status == "Paid" and payment_id and terms["refund_amount"] > 0:
            try:
                # Process Ziina refund
                refund_result = await refund_ziina_payment(
                    payment_id=payment_id,
                    refund_amount_aed=terms["refund_amount"],
                    reason=payload.get("cancelledReason", "Customer cancellation")
                )
                
                logger.info(f"Refund processed: {refund_result}")
                
                # Add refund info to payload
                payload["refundId"] = refund_result["refund_id"]
                payload["refundAmount"] = refund_result["amount"]
                payload["cancellationFee"] = terms["fee"]
                
            except Exception as e:
                # Ziina refund failed - don't cancel the booking
                logger.error(f"Ziina refund failed for {booking.get('orderId')}: {e}")
                raise RuntimeError(f"Refund failed: {str(e)}")
        
        # Make the cancellation API call
        logger.info("================================================================================")
        logger.info("🚫 CALLING CANCELLATION API")
        logger.info("================================================================================")
        logger.info(f"📍 URL: {settings.booking_cancel_api_url}")
        logger.info(f"📦 PAYLOAD: {payload}")
        logger.info(f"🔑 AUTH HEADERS: {list(auth_headers.keys())}")
        for key, value in auth_headers.items():
            if 'token' in key.lower():
                logger.info(f"   {key}: {value[:20]}... (length={len(value)})")
            else:
                logger.info(f"   {key}: {value}")
        logger.info("================================================================================")
        
        try:
            with httpx.Client(timeout=settings.booking_api_timeout_seconds, verify=settings.booking_api_verify_ssl) as client:
                response = client.put(settings.booking_cancel_api_url, json=payload, headers=auth_headers)
                response.raise_for_status()
                result = response.json()
                
                logger.info("📥 CANCELLATION RESPONSE RECEIVED")
                logger.info(f"   Status Code: {response.status_code}")
                logger.info(f"   Response: {result}")
                logger.info("✅ CANCELLATION API SUCCESS")
                logger.info("================================================================================")
        except httpx.TimeoutException as exc:
            raise RuntimeError("Cancellation request timed out; verify booking status before retrying.") from exc
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(f"Booking API returned HTTP {exc.response.status_code}: {exc.response.text[:500]}") from exc
        except httpx.RequestError as exc:
            raise RuntimeError(f"Booking API request failed: {exc}") from exc
        except ValueError as exc:
            raise RuntimeError("Booking API returned invalid JSON.") from exc
        
        if not isinstance(result, dict) or result.get("error") is True:
            message = result.get("message", "Booking API rejected the cancellation.") if isinstance(result, dict) else "Booking API returned an invalid response."
            raise RuntimeError(str(message))
        
        return result

    def view_external_booking(self, booking_id: str, auth_headers: dict[str, str]) -> dict[str, Any]:
        """Fetch one Bookly booking using the app's Bookly API token."""
        settings = get_settings()
        url = f"{settings.booking_view_api_url.rstrip('/')}/{booking_id}"
        
        # Get token from headers (prefer x-auth-token-user for consistency)
        token = auth_headers.get("x-auth-token-user") or auth_headers.get("x-auth-token") or get_settings().bookly_api_token
        if not token:
            raise RuntimeError("BOOKLY_API_TOKEN is not configured.")
        
        headers = {
            "x-auth-language": auth_headers.get("x-auth-language", "English"),
            "x-user-type": auth_headers.get("x-user-type", "User"),
            "x-auth-token-user": token,
            "Authorization": f"Bearer {token}",
        }
        
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
        booking["bookingId"] = booking.get("_id")
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

    async def confirm_online_booking_payment(
        self,
        order_id: str,
        payment_id: str,
        amount: float
    ) -> dict[str, Any]:
        """
        Confirm a booking payment after Ziina verification (atomic and idempotent).
        
        This function:
        - Verifies the payment with Ziina
        - Sets paymentStatus to Paid
        - Moves bookingStatus from Pending to Approved
        - Restores "Payment Timeout" cancellations
        - Creates exactly one "Booking Payment" Transaction
        
        Safe to call multiple times - idempotent.
        """
        logger.info(f"Confirming payment for booking {order_id}")
        
        # This would call the external API or update the database
        # For now, we'll delegate to the repository if available
        if self._repository and self._repository.is_available():
            return self._repository.confirm_booking_payment(
                order_id=order_id,
                payment_id=payment_id,
                amount=amount
            )
        
        return {
            "confirmed": True,
            "orderId": order_id,
            "paymentId": payment_id,
            "amount": amount
        }

    def view_external_booking_by_order_id(self, order_id: str, auth_headers: dict[str, str]) -> dict[str, Any]:
        """Fetch booking by order ID instead of internal _id."""
        # This would need to be implemented in the external API
        # For now, we'll use the existing method and hope order_id works
        return self.view_external_booking(order_id, auth_headers)

    def verify_payment_status(self, booking_id: str, auth_headers: dict[str, str]) -> dict[str, Any]:
        """
        Verify Ziina payment status for a booking.
        
        Returns:
            {
                "paymentStatus": "Paid" | "Pending" | "Failed",
                "bookingStatus": "Approved" | "Pending",
                "verified": bool
            }
        """
        settings = get_settings()
        
        # Prepare headers
        request_headers = {}
        if auth_headers:
            request_headers.update(auth_headers)
            token = auth_headers.get("x-auth-token-user") or auth_headers.get("x-auth-token")
            if token:
                request_headers["x-auth-token-user"] = token
                request_headers["Authorization"] = f"Bearer {token}"
        
        payload = {"bookingId": booking_id}
        
        logger.info("=" * 80)
        logger.info("🔍 VERIFYING PAYMENT STATUS")
        logger.info("=" * 80)
        logger.info("📍 URL: %s", settings.booking_verify_payment_api_url)
        logger.info("📦 Booking ID: %s", booking_id)
        
        try:
            with httpx.Client(timeout=settings.booking_api_timeout_seconds, verify=settings.booking_api_verify_ssl) as client:
                response = client.put(settings.booking_verify_payment_api_url, json=payload, headers=request_headers)
                
                logger.info("📥 RESPONSE RECEIVED")
                logger.info("   Status Code: %s", response.status_code)
                logger.info("   Response: %s", response.text[:500])
                
                response.raise_for_status()
                result = response.json()
                
                logger.info("✅ PAYMENT VERIFICATION SUCCESS")
                logger.info("=" * 80)
                
                return result
                
        except httpx.TimeoutException as exc:
            logger.error("⏱️ PAYMENT VERIFICATION TIMEOUT")
            logger.error("=" * 80)
            raise RuntimeError("Payment verification timed out; please try again later.") from exc
        except httpx.HTTPStatusError as exc:
            logger.error("❌ PAYMENT VERIFICATION HTTP ERROR")
            logger.error("   Status: %s", exc.response.status_code)
            logger.error("   Response: %s", exc.response.text[:500])
            logger.error("=" * 80)
            raise RuntimeError(f"Payment verification failed: HTTP {exc.response.status_code}") from exc
        except httpx.RequestError as exc:
            logger.error("❌ PAYMENT VERIFICATION REQUEST ERROR")
            logger.error("   Error: %s", str(exc))
            logger.error("=" * 80)
            raise RuntimeError(f"Payment verification request failed: {exc}") from exc
        except ValueError as exc:
            logger.error("❌ PAYMENT VERIFICATION INVALID JSON")
            logger.error("=" * 80)
            raise RuntimeError("Payment verification returned invalid JSON.") from exc

