"""Background cron jobs for booking management - payment hold expiry."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Any

from app.core.logging import get_logger
from app.utils.booking_payment import (
    is_payment_hold_expired,
    verify_ziina_payment,
    PAYMENT_HOLD_MINUTES
)

logger = get_logger(__name__)


class BookingCronService:
    """
    Handles periodic booking tasks:
    - Payment hold expiry (PayNow unpaid bookings)
    - Payment verification retries
    """
    
    def __init__(self, booking_repository: Any):
        self.repository = booking_repository
        self._running = False
    
    async def start(self):
        """Start the cron service."""
        if self._running:
            return
        
        self._running = True
        logger.info("Starting booking cron service")
        
        # Start background task
        asyncio.create_task(self._run_payment_hold_check())
    
    async def stop(self):
        """Stop the cron service."""
        self._running = False
        logger.info("Stopping booking cron service")
    
    async def _run_payment_hold_check(self):
        """
        Check for expired payment holds every minute.
        
        Rules:
        - PayNow unpaid bookings 10 min after creation (old flow: 10 min after approval)
        - Ask Ziina first: completed → confirm, pending → wait up to 5 more min
        - Otherwise → Cancelled (cancelledReason: "Payment Timeout", cancelledBy: "System")
        - PayNow holds cancelled silently (no notification)
        - Ziina unreachable → skip and retry next minute (never cancel unverified)
        """
        while self._running:
            try:
                await self._check_payment_holds()
            except Exception as e:
                logger.error(f"Error in payment hold check: {e}")
            
            # Wait 1 minute before next check
            await asyncio.sleep(60)
    
    async def _check_payment_holds(self):
        """Check and process expired payment holds."""
        now = datetime.now(datetime.now().astimezone().tzinfo)
        
        # Find PayNow bookings that are unpaid and past the hold period
        cutoff_time = now - timedelta(minutes=PAYMENT_HOLD_MINUTES)
        
        try:
            expired_bookings = self.repository.find_expired_payment_holds(cutoff_time)
            
            for booking in expired_bookings:
                await self._process_expired_hold(booking, now)
                
        except Exception as e:
            logger.error(f"Error finding expired payment holds: {e}")
    
    async def _process_expired_hold(self, booking: dict[str, Any], now: datetime):
        """
        Process a single expired payment hold.
        
        Steps:
        1. Verify with Ziina first
        2. If completed → confirm payment
        3. If pending and < 15 min total → wait (extended grace period)
        4. Otherwise → cancel with "Payment Timeout"
        """
        booking_id = booking.get("_id")
        order_id = booking.get("orderId")
        payment_id = booking.get("ziinaPaymentId")
        created_at = booking.get("createdAt")
        
        logger.info(f"Processing expired payment hold for booking {order_id}")
        
        # If no payment ID, cancel immediately
        if not payment_id:
            await self._cancel_for_timeout(booking_id, order_id)
            return
        
        # Verify with Ziina
        try:
            payment_status = await verify_ziina_payment(payment_id)
            
            if payment_status["status"] == "completed":
                # Payment was completed - confirm it
                logger.info(f"Payment completed for {order_id}, confirming")
                await self._confirm_payment(booking_id, order_id, payment_id, payment_status["amount"])
                return
            
            # Check if we're in the extended grace period (up to 15 min total)
            if created_at:
                minutes_since_creation = (now - created_at).total_seconds() / 60
                if minutes_since_creation < (PAYMENT_HOLD_MINUTES + 5):
                    logger.info(f"Booking {order_id} in grace period, waiting")
                    return
            
            # Payment still pending after grace period - cancel
            logger.info(f"Payment {payment_id} still pending after grace period, cancelling {order_id}")
            await self._cancel_for_timeout(booking_id, order_id)
            
        except Exception as e:
            # Ziina unreachable - don't cancel, retry next minute
            logger.error(f"Could not verify payment {payment_id} with Ziina, skipping: {e}")
            return
    
    async def _confirm_payment(
        self,
        booking_id: str,
        order_id: str,
        payment_id: str,
        amount: float
    ):
        """Confirm a completed payment."""
        try:
            self.repository.confirm_booking_payment(
                booking_id=booking_id,
                payment_id=payment_id,
                amount=amount
            )
            logger.info(f"Confirmed payment for booking {order_id}")
        except Exception as e:
            logger.error(f"Error confirming payment for {order_id}: {e}")
    
    async def _cancel_for_timeout(self, booking_id: str, order_id: str):
        """
        Cancel a booking due to payment timeout.
        
        Silent cancellation - no notifications sent for PayNow timeout.
        """
        try:
            self.repository.cancel_booking_for_timeout(
                booking_id=booking_id,
                cancelled_reason="Payment Timeout",
                cancelled_by="System"
            )
            logger.info(f"Cancelled booking {order_id} due to payment timeout")
        except Exception as e:
            logger.error(f"Error cancelling booking {order_id}: {e}")
