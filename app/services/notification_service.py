"""Notification service for sending booking-related notifications."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from app.core.logging import get_logger

logger = get_logger(__name__)

NotificationChannel = Literal["push", "email", "whatsapp", "sms"]


class NotificationService:
    """
    Handles multi-channel notifications for bookings.
    
    Wraps notification calls so failures don't break the main action.
    """
    
    def __init__(self):
        # Load localization files
        self.locales = {}
        locales_dir = Path(__file__).parent.parent / "locales"
        
        for lang_file in ["en.json", "ar.json"]:
            lang_path = locales_dir / lang_file
            if lang_path.exists():
                try:
                    with open(lang_path, "r", encoding="utf-8") as f:
                        lang_code = lang_file.split(".")[0]
                        self.locales[lang_code] = json.load(f)
                except Exception as e:
                    logger.error(f"Error loading locale {lang_file}: {e}")
    
    def get_message(self, key: str, language: str = "en", **kwargs) -> str:
        """
        Get a localized message.
        
        Args:
            key: Message key in dot notation (e.g., "booking.created")
            language: Language code (en, ar)
            **kwargs: Template variables
        
        Returns:
            Localized message
        """
        lang_code = "ar" if language in ["ar", "Arabic"] else "en"
        locale_data = self.locales.get(lang_code, self.locales.get("en", {}))
        
        # Navigate nested keys
        parts = key.split(".")
        message = locale_data
        for part in parts:
            if isinstance(message, dict):
                message = message.get(part)
            else:
                break
        
        if not isinstance(message, str):
            return key  # Fallback to key if not found
        
        # Simple template replacement
        for k, v in kwargs.items():
            message = message.replace(f"{{{{{k}}}}}", str(v))
        
        return message
    
    async def notify_booking_created(
        self,
        booking: dict[str, Any],
        user: dict[str, Any] | None,
        salon: dict[str, Any],
        language: str = "en"
    ):
        """
        Send notifications when a booking is created.
        
        Channels:
        - User: push notification
        - Salon: push + email + WhatsApp
        """
        try:
            order_id = booking.get("orderId")
            booking_status = booking.get("bookingStatus")
            pay_option = booking.get("payOption")
            
            # User notification
            if user:
                message = self.get_message("notifications.booking_created", language)
                await self._send_push(
                    user_id=user.get("_id"),
                    title=message,
                    body=f"Order: {order_id}",
                    data={"bookingId": booking.get("_id"), "orderId": order_id}
                )
            
            # Salon notifications
            salon_id = salon.get("_id")
            salon_message = self.get_message("notifications.new_booking_received", language)
            
            await self._send_push(
                user_id=salon_id,
                title=salon_message,
                body=f"Order: {order_id}",
                data={"bookingId": booking.get("_id"), "orderId": order_id}
            )
            
            # Email and WhatsApp for salon
            await self._send_email(
                to=salon.get("email"),
                subject=salon_message,
                body=f"New booking {order_id} received"
            )
            
            await self._send_whatsapp(
                to=salon.get("phoneNumber"),
                message=f"{salon_message}\nOrder: {order_id}"
            )
            
        except Exception as e:
            logger.error(f"Error sending booking created notifications: {e}")
    
    async def notify_payment_confirmed(
        self,
        booking: dict[str, Any],
        user: dict[str, Any] | None,
        salon: dict[str, Any],
        language: str = "en"
    ):
        """Send notifications when payment is confirmed."""
        try:
            message = self.get_message("notifications.payment_confirmed", language)
            order_id = booking.get("orderId")
            
            # User notification
            if user:
                await self._send_push(
                    user_id=user.get("_id"),
                    title=message,
                    body=f"Order: {order_id}",
                    data={"bookingId": booking.get("_id"), "orderId": order_id}
                )
            
            # Salon notification
            await self._send_push(
                user_id=salon.get("_id"),
                title=message,
                body=f"Order: {order_id}",
                data={"bookingId": booking.get("_id"), "orderId": order_id}
            )
            
        except Exception as e:
            logger.error(f"Error sending payment confirmed notifications: {e}")
    
    async def notify_booking_cancelled(
        self,
        booking: dict[str, Any],
        user: dict[str, Any] | None,
        salon: dict[str, Any],
        refund_amount: float = 0,
        cancellation_fee: float = 0,
        language: str = "en"
    ):
        """Send notifications when a booking is cancelled."""
        try:
            message = self.get_message("notifications.booking_cancelled", language)
            order_id = booking.get("orderId")
            
            # Build detailed message for user
            details = f"Order: {order_id}"
            if refund_amount > 0:
                refund_msg = self.get_message("payment.refund_amount", language, amount=f"{refund_amount:.2f}")
                details += f"\n{refund_msg}"
            if cancellation_fee > 0:
                fee_msg = self.get_message("payment.cancellation_fee", language, fee=f"{cancellation_fee:.2f}")
                details += f"\n{fee_msg}"
            
            # User notifications
            if user:
                await self._send_push(
                    user_id=user.get("_id"),
                    title=message,
                    body=details,
                    data={"bookingId": booking.get("_id"), "orderId": order_id}
                )
                
                await self._send_whatsapp(
                    to=user.get("phoneNumber"),
                    message=f"{message}\n{details}"
                )
                
                await self._send_email(
                    to=user.get("email"),
                    subject=message,
                    body=details
                )
            
            # Salon notifications
            await self._send_push(
                user_id=salon.get("_id"),
                title="Booking Cancelled",
                body=f"Order: {order_id}",
                data={"bookingId": booking.get("_id"), "orderId": order_id}
            )
            
            await self._send_email(
                to=salon.get("email"),
                subject="Booking Cancelled",
                body=f"Booking {order_id} has been cancelled"
            )
            
            await self._send_whatsapp(
                to=salon.get("phoneNumber"),
                message=f"Booking {order_id} has been cancelled"
            )
            
        except Exception as e:
            logger.error(f"Error sending booking cancelled notifications: {e}")
    
    async def notify_pay_at_store_confirmed(
        self,
        booking: dict[str, Any],
        user: dict[str, Any] | None,
        language: str = "en"
    ):
        """Send PayAtStore confirmation to user."""
        try:
            message = self.get_message("notifications.booking_confirmed", language)
            order_id = booking.get("orderId")
            
            if user:
                await self._send_push(
                    user_id=user.get("_id"),
                    title=message,
                    body=f"Order: {order_id}",
                    data={"bookingId": booking.get("_id"), "orderId": order_id}
                )
            
        except Exception as e:
            logger.error(f"Error sending PayAtStore confirmation: {e}")
    
    async def _send_push(self, user_id: str, title: str, body: str, data: dict[str, Any] | None = None):
        """Send push notification (placeholder for actual implementation)."""
        logger.info(f"PUSH to {user_id}: {title} - {body}")
        # TODO: Integrate with actual push notification service (FCM, APNs)
    
    async def _send_email(self, to: str | None, subject: str, body: str):
        """Send email notification (placeholder for actual implementation)."""
        if not to:
            return
        logger.info(f"EMAIL to {to}: {subject}")
        # TODO: Integrate with actual email service (SendGrid, SES, SMTP)
    
    async def _send_whatsapp(self, to: str | None, message: str):
        """Send WhatsApp notification (placeholder for actual implementation)."""
        if not to:
            return
        logger.info(f"WHATSAPP to {to}: {message}")
        # TODO: Integrate with WhatsApp Business API
    
    async def _send_sms(self, to: str | None, message: str):
        """Send SMS notification (placeholder for actual implementation)."""
        if not to:
            return
        logger.info(f"SMS to {to}: {message}")
        # TODO: Integrate with SMS service (Twilio, SNS)
