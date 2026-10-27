"""Phone-based user matching and guest booking linking utilities."""

from __future__ import annotations

import re
from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)

# Known country codes
KNOWN_COUNTRY_CODES = {"971", "91"}
DEFAULT_COUNTRY_CODE = "971"


def normalize_whatsapp_phone(phone_raw: str) -> tuple[str, str] | None:
    """
    Normalize WhatsApp phone number to phone + country code.
    
    Format: 971501234567 → (501234567, +971)
    
    Rules:
    - Known codes: 971, 91
    - Default: 971
    - Strip leading zeros
    - Needs ≥ 7 digits after normalization
    
    Args:
        phone_raw: Raw phone number from WhatsApp
    
    Returns:
        Tuple of (phone_number, country_code) or None if invalid
    """
    if not phone_raw or not isinstance(phone_raw, str):
        return None
    
    # Remove all non-digit characters
    digits = re.sub(r"\D", "", phone_raw)
    
    if len(digits) < 7:
        return None
    
    # Try to extract country code
    country_code = None
    phone_number = digits
    
    for code in KNOWN_COUNTRY_CODES:
        if digits.startswith(code):
            country_code = f"+{code}"
            phone_number = digits[len(code):]
            break
    
    # If no known code found, use default
    if not country_code:
        country_code = f"+{DEFAULT_COUNTRY_CODE}"
    
    # Strip leading zeros from phone number
    phone_number = phone_number.lstrip("0")
    
    # Validate minimum length
    if len(phone_number) < 7:
        return None
    
    return phone_number, country_code


def find_registered_user_by_contact(
    contact: dict[str, str | None],
    users_repository: Any
) -> dict[str, Any] | None:
    """
    Find registered user by phone number only (never email for WhatsApp).
    
    Args:
        contact: Dict with phoneNumber and countryCode
        users_repository: Repository with find_user_by_phone method
    
    Returns:
        User document or None if not found
    """
    phone_number = contact.get("phoneNumber")
    country_code = contact.get("countryCode")
    
    if not phone_number or not country_code:
        return None
    
    try:
        # Only match by phone, never email
        user = users_repository.find_user_by_phone(phone_number, country_code)
        return user
    except Exception as e:
        logger.error(f"Error finding user by contact: {e}")
        return None


def link_guest_bookings_to_user(
    user_id: str,
    email: str | None,
    phone_number: str | None,
    country_code: str | None,
    bookings_repository: Any
) -> int:
    """
    Link guest bookings (userId: null) to a registered user after login/signup.
    
    Matches on email and/or phone from Contact document.
    
    Args:
        user_id: The user ID to link bookings to
        email: User's email
        phone_number: User's phone number
        country_code: User's country code
        bookings_repository: Repository with link_guest_bookings method
    
    Returns:
        Number of bookings linked
    """
    try:
        count = bookings_repository.link_guest_bookings(
            user_id=user_id,
            email=email,
            phone_number=phone_number,
            country_code=country_code
        )
        if count > 0:
            logger.info(f"Linked {count} guest bookings to user {user_id}")
        return count
    except Exception as e:
        logger.error(f"Error linking guest bookings: {e}")
        return 0


def extract_salon_info(
    vendor_id: str | None,
    salon_id: str | None,
    salon_name: str | None,
    vendor_name: str | None,
    services: list[dict[str, Any]],
    salons_repository: Any
) -> dict[str, Any] | None:
    """
    Resolve salon information from various input sources.
    
    Priority:
    1. vendorId
    2. salonId → exact case-insensitive match on businessName/fullName/name
    3. salonName/vendorName → first serviceId's vendorId
    
    Args:
        vendor_id: Vendor ID if provided
        salon_id: Salon ID for lookup
        salon_name: Salon name for matching
        vendor_name: Vendor name for matching
        services: List of selected services with vendorId
        salons_repository: Repository with salon lookup methods
    
    Returns:
        Salon document or None
    """
    try:
        # Priority 1: Direct vendor ID
        if vendor_id:
            salon = salons_repository.find_by_id(vendor_id)
            if salon:
                return salon
        
        # Priority 2: Salon ID with name matching
        if salon_id:
            salon = salons_repository.find_by_name(salon_id)
            if salon:
                return salon
        
        # Priority 3: Name matching or first service's vendor
        name_to_match = salon_name or vendor_name
        if name_to_match:
            salon = salons_repository.find_by_business_name(name_to_match)
            if salon:
                return salon
        
        # Fallback: Get vendor from first service
        if services and len(services) > 0:
            service = services[0]
            if isinstance(service, dict) and service.get("vendorId"):
                salon = salons_repository.find_by_id(service["vendorId"])
                if salon:
                    return salon
        
        return None
        
    except Exception as e:
        logger.error(f"Error extracting salon info: {e}")
        return None
