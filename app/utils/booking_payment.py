"""Payment option rules, Ziina payment integration, and payment confirmation."""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Any, Literal

import httpx

from app.core.logging import get_logger

logger = get_logger(__name__)

PaymentStatus = Literal["Pending", "Paid", "Refunded", "Failed"]
TransactionStatus = Literal["Pending", "Successful", "Failed", "Refunded", "RefundError"]
TransactionType = Literal["Booking Payment", "Refund", "Cancellation Fee"]

# Environment variables
ZIINA_BASE_URL = os.getenv("ZIINA_BASE_URL", "https://api.ziina.com/v1")
ZIINA_API_KEY = os.getenv("ZIINA_API_KEY", "")
ZIINA_TEST_MODE = os.getenv("ZIINA_TEST_MODE", "false").lower() == "true"
ZIINA_REFUND_MOCK = os.getenv("ZIINA_REFUND_MOCK", "false").lower() == "true"
PAYMENT_RESULT_BASE_URL = os.getenv("PAYMENT_RESULT_BASE_URL", "http://localhost:8000/payment/paymentResult")
PAYMENT_HOLD_MINUTES = int(os.getenv("PAYMENT_HOLD_MINUTES", "10"))


def determine_pay_option(
    body_pay_option: str | None,
    is_whatsapp: bool,
    is_vendor: bool
) -> str:
    """
    Determine the payment option based on caller type.
    
    Rules:
    - WhatsApp: defaults to "PayAtStore" if not provided
    - Vendor: defaults to "PayAtStore" if not provided
    - Customer app: must be explicitly provided
    - Missing payOption is never treated as Pay Now
    
    Args:
        body_pay_option: Payment option from request body
        is_whatsapp: Whether caller is WhatsApp bot
        is_vendor: Whether caller is salon app
    
    Returns:
        Validated payment option ("PayNow", "PayAtStore", or None)
    
    Raises:
        ValueError: If payOption is invalid
    """
    valid_options = {"PayNow", "PayAtStore"}
    
    if is_whatsapp or is_vendor:
        pay_option = body_pay_option or "PayAtStore"
    else:
        pay_option = body_pay_option  # Can be None (old flow)
    
    # Validate if provided
    if pay_option and pay_option not in valid_options:
        raise ValueError("Invalid payment option")
    
    return pay_option


def calculate_booking_status(pay_option: str | None, is_vendor: bool) -> str:
    """
    Calculate initial booking status based on payment option.
    
    Rules:
    - PayAtStore or vendor-created: "Approved"
    - PayNow: "Pending"
    - Old flow (no pay_option): "Pending"
    
    Args:
        pay_option: Payment option ("PayNow", "PayAtStore", or None)
        is_vendor: Whether booking is vendor-created
    
    Returns:
        Initial booking status
    """
    if pay_option == "PayAtStore" or is_vendor:
        return "Approved"
    return "Pending"


def calculate_booking_amounts(
    service_prices: list[float],
    coupon_discount: float,
    vat_percentage: float
) -> dict[str, float]:
    """
    Calculate booking amounts: subtotal, discount, VAT, and final amount.
    
    Formula: subtotal - coupon (capped at subtotal) + VAT → finalAmount
    
    Args:
        service_prices: List of service prices
        coupon_discount: Coupon discount amount (will be capped at subtotal)
        vat_percentage: VAT percentage (e.g., 5.0 for 5%)
    
    Returns:
        Dict with subtotal, discount, vat, vatPercentage, finalAmount
    """
    subtotal = round(sum(service_prices), 2)
    
    # Cap coupon at subtotal
    discount = min(coupon_discount, subtotal)
    discount = round(discount, 2)
    
    # Calculate amount after discount
    after_discount = subtotal - discount
    
    # Calculate VAT
    vat = round(after_discount * vat_percentage / 100, 2)
    
    # Final amount
    final_amount = round(after_discount + vat, 2)
    
    return {
        "subtotal": subtotal,
        "discount": discount,
        "vat": vat,
        "vatPercentage": vat_percentage,
        "finalAmount": final_amount
    }


def calculate_commission(
    gross_amount: float,
    commission_percentage: float
) -> tuple[float, float]:
    """
    Calculate commission split.
    
    Args:
        gross_amount: Total amount
        commission_percentage: Admin commission percentage
    
    Returns:
        Tuple of (commission_amount, net_amount)
    """
    commission = round(gross_amount * commission_percentage / 100, 2)
    net = round(gross_amount - commission, 2)
    return commission, net


async def create_ziina_payment_intent(
    booking_id: str,
    amount_aed: float,
    description: str,
    customer_email: str | None = None,
    customer_phone: str | None = None
) -> dict[str, Any]:
    """
    Create a Ziina payment intent for online payment.
    
    Args:
        booking_id: Booking ID for reference
        amount_aed: Amount in AED
        description: Payment description
        customer_email: Customer email (optional)
        customer_phone: Customer phone (optional)
    
    Returns:
        Dict with id, url, status
    
    Raises:
        RuntimeError: If Ziina API call fails
    """
    if not ZIINA_API_KEY:
        raise RuntimeError("ZIINA_API_KEY is not configured")
    
    # Convert AED to fils (1 AED = 100 fils)
    amount_fils = int(amount_aed * 100)
    
    # Build return URL
    return_url = f"{PAYMENT_RESULT_BASE_URL}?orderId={booking_id}"
    
    payload = {
        "amount": amount_fils,
        "currency": "AED",
        "description": description,
        "return_url": return_url,
        "metadata": {
            "booking_id": booking_id,
            "test_mode": ZIINA_TEST_MODE
        }
    }
    
    if customer_email:
        payload["customer_email"] = customer_email
    if customer_phone:
        payload["customer_phone"] = customer_phone
    
    headers = {
        "Authorization": f"Bearer {ZIINA_API_KEY}",
        "Content-Type": "application/json"
    }
    
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"{ZIINA_BASE_URL}/payment_intents",
                json=payload,
                headers=headers
            )
            response.raise_for_status()
            result = response.json()
            
            return {
                "id": result.get("id"),
                "url": result.get("url"),
                "status": result.get("status"),
                "amount": amount_aed
            }
            
    except httpx.HTTPStatusError as e:
        logger.error(f"Ziina API error: {e.response.status_code} - {e.response.text}")
        raise RuntimeError(f"Payment link creation failed: {e.response.text}")
    except Exception as e:
        logger.error(f"Error creating Ziina payment intent: {e}")
        raise RuntimeError(f"Payment link creation failed: {str(e)}")


async def verify_ziina_payment(payment_id: str) -> dict[str, Any]:
    """
    Verify payment status with Ziina.
    
    Args:
        payment_id: Ziina payment intent ID
    
    Returns:
        Dict with id, status, amount
    
    Raises:
        RuntimeError: If Ziina API call fails
    """
    if not ZIINA_API_KEY:
        raise RuntimeError("ZIINA_API_KEY is not configured")
    
    headers = {
        "Authorization": f"Bearer {ZIINA_API_KEY}",
        "Content-Type": "application/json"
    }
    
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                f"{ZIINA_BASE_URL}/payment_intents/{payment_id}",
                headers=headers
            )
            response.raise_for_status()
            result = response.json()
            
            return {
                "id": result.get("id"),
                "status": result.get("status"),
                "amount": result.get("amount", 0) / 100  # Convert fils to AED
            }
            
    except httpx.HTTPStatusError as e:
        logger.error(f"Ziina API error: {e.response.status_code} - {e.response.text}")
        raise RuntimeError(f"Payment verification failed: {e.response.text}")
    except Exception as e:
        logger.error(f"Error verifying Ziina payment: {e}")
        raise RuntimeError(f"Payment verification failed: {str(e)}")


async def refund_ziina_payment(
    payment_id: str,
    refund_amount_aed: float,
    reason: str = "Customer cancellation"
) -> dict[str, Any]:
    """
    Refund a Ziina payment.
    
    Args:
        payment_id: Ziina payment intent ID
        refund_amount_aed: Amount to refund in AED (capped at original amount)
        reason: Refund reason
    
    Returns:
        Dict with refund_id, status, amount
    
    Raises:
        RuntimeError: If Ziina API call fails or payment cannot be refunded
    """
    if ZIINA_REFUND_MOCK:
        logger.info(f"MOCK: Refunding {refund_amount_aed} AED for payment {payment_id}")
        return {
            "refund_id": f"mock_refund_{payment_id}",
            "status": "refunded",
            "amount": refund_amount_aed
        }
    
    if not ZIINA_API_KEY:
        raise RuntimeError("ZIINA_API_KEY is not configured")
    
    # First, get the payment intent to verify it's completed
    payment_info = await verify_ziina_payment(payment_id)
    
    if payment_info["status"] != "completed":
        raise RuntimeError(f"Cannot refund a payment with status: {payment_info['status']}")
    
    # Cap refund at original payment amount
    max_amount = payment_info["amount"]
    actual_refund = min(refund_amount_aed, max_amount)
    
    # Convert to fils
    refund_fils = int(actual_refund * 100)
    
    payload = {
        "amount": refund_fils,
        "reason": reason
    }
    
    headers = {
        "Authorization": f"Bearer {ZIINA_API_KEY}",
        "Content-Type": "application/json"
    }
    
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"{ZIINA_BASE_URL}/payment_intents/{payment_id}/refund",
                json=payload,
                headers=headers
            )
            response.raise_for_status()
            result = response.json()
            
            return {
                "refund_id": result.get("id"),
                "status": result.get("status"),
                "amount": actual_refund
            }
            
    except httpx.HTTPStatusError as e:
        error_text = e.response.text
        logger.error(f"Ziina refund error: {e.response.status_code} - {error_text}")
        
        # Specific handling for test payments
        if "test payment" in error_text.lower():
            raise RuntimeError("Cannot refund a test payment - use ZIINA_REFUND_MOCK=true in test mode")
        
        raise RuntimeError(f"Refund failed: {error_text}")
    except Exception as e:
        logger.error(f"Error refunding Ziina payment: {e}")
        raise RuntimeError(f"Refund failed: {str(e)}")


def should_notify_pay_at_store(pay_option: str | None) -> bool:
    """Check if PayAtStore notifications should be sent."""
    return pay_option == "PayAtStore"


def is_payment_hold_expired(
    created_at: datetime,
    now: datetime | None = None,
    hold_minutes: int = PAYMENT_HOLD_MINUTES
) -> bool:
    """
    Check if payment hold period has expired.
    
    Args:
        created_at: Booking creation time
        now: Current time (defaults to datetime.now)
        hold_minutes: Hold period in minutes
    
    Returns:
        True if hold has expired
    """
    if now is None:
        now = datetime.now(datetime.now().astimezone().tzinfo)
    
    expiry = created_at + timedelta(minutes=hold_minutes)
    return now >= expiry
