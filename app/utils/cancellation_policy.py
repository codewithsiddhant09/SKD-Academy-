"""Cancellation policy calculator with 2-hour rule and fees."""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Any, TypedDict

from app.core.logging import get_logger
from app.utils.timezone import get_scheduled_moment, DEFAULT_IANA_TIMEZONE

logger = get_logger(__name__)

# Environment variables with defaults
FREE_CANCELLATION_HOURS = float(os.getenv("FREE_CANCELLATION_HOURS", "2"))
CANCELLATION_FEE_AED = float(os.getenv("CANCELLATION_FEE_AED", "10"))
CANCELLATION_FEE_PERCENTAGE = float(os.getenv("CANCELLATION_FEE_PERCENTAGE", "0"))  # 0 = use flat fee


class CancellationTerms(TypedDict):
    """Result of cancellation policy calculation."""
    allowed: bool
    reason: str | None
    fee: float
    refund_amount: float
    is_late_cancellation: bool
    appointment_at: str | None


def get_cancellation_terms(
    booking: dict[str, Any], 
    now: datetime | None = None,
    booking_timezone: str | None = None
) -> CancellationTerms:
    """
    Calculate cancellation fee and refund based on the 2-hour rule.
    
    Rules:
    - After appointment start: Not allowed
    - Within 2 hours before start: Fee applies (flat or percentage)
    - More than 2 hours before: Free, full refund
    - Unpaid booking: Fee always 0
    - Invalid date/slot: Allowed with fee 0 (logged)
    
    Args:
        booking: Booking document with date, slot, finalAmount, paymentStatus
        now: Current time (defaults to datetime.now(UTC))
        booking_timezone: IANA timezone name (defaults to BOOKING_TIMEZONE env or Asia/Dubai)
    
    Returns:
        CancellationTerms with allowed, reason, fee, refund_amount, etc.
    """
    if now is None:
        now = datetime.now(datetime.now().astimezone().tzinfo)
    
    tz_name = booking_timezone or os.getenv("BOOKING_TIMEZONE", DEFAULT_IANA_TIMEZONE)
    
    # Extract booking details
    date_str = booking.get("date", "")
    slot = booking.get("slot", "")
    paid_amount = float(booking.get("finalAmount", 0) or 0)
    payment_status = booking.get("paymentStatus", "")
    
    # Parse appointment time
    appointment_dt = get_scheduled_moment(date_str, slot, tz_name)
    
    if not appointment_dt:
        logger.warning(f"Could not parse appointment time - date: {date_str}, slot: {slot}")
        return CancellationTerms(
            allowed=True,
            reason=None,
            fee=0.0,
            refund_amount=paid_amount,
            is_late_cancellation=False,
            appointment_at=None
        )
    
    appointment_at_str = appointment_dt.isoformat()
    
    # Check if appointment has already started
    if now >= appointment_dt:
        return CancellationTerms(
            allowed=False,
            reason="Booking cannot be cancelled after the appointment start time",
            fee=0.0,
            refund_amount=0.0,
            is_late_cancellation=False,
            appointment_at=appointment_at_str
        )
    
    # Calculate time until appointment
    time_until = appointment_dt - now
    hours_until = time_until.total_seconds() / 3600
    
    # Unpaid bookings always have 0 fee
    is_paid = payment_status == "Paid"
    
    # Within FREE_CANCELLATION_HOURS window
    if hours_until < FREE_CANCELLATION_HOURS:
        if not is_paid:
            fee = 0.0
        elif CANCELLATION_FEE_PERCENTAGE > 0:
            # Use percentage fee if configured
            fee = (paid_amount * CANCELLATION_FEE_PERCENTAGE / 100)
            # Cap at paid amount
            fee = min(fee, paid_amount)
        else:
            # Use flat fee
            fee = min(CANCELLATION_FEE_AED, paid_amount)
        
        refund = paid_amount - fee
        
        return CancellationTerms(
            allowed=True,
            reason=None,
            fee=round(fee, 2),
            refund_amount=round(refund, 2),
            is_late_cancellation=True,
            appointment_at=appointment_at_str
        )
    
    # More than 2 hours before: free cancellation
    return CancellationTerms(
        allowed=True,
        reason=None,
        fee=0.0,
        refund_amount=paid_amount,
        is_late_cancellation=False,
        appointment_at=appointment_at_str
    )


def calculate_fee_split(
    fee: float, 
    admin_commission_percentage: float
) -> tuple[float, float]:
    """
    Calculate admin and salon shares of the cancellation fee.
    
    Args:
        fee: Total cancellation fee
        admin_commission_percentage: Admin commission (e.g., 20 for 20%)
    
    Returns:
        Tuple of (admin_share, salon_share)
    """
    admin_share = round(fee * admin_commission_percentage / 100, 2)
    salon_share = round(fee - admin_share, 2)
    return admin_share, salon_share
