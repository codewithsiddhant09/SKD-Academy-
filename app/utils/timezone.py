"""Timezone utilities for booking slot and date parsing."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from app.core.logging import get_logger

logger = get_logger(__name__)

# Default timezone for bookings (can be overridden by BOOKING_TIMEZONE env var)
DEFAULT_IANA_TIMEZONE = "Asia/Dubai"

# Accepted slot formats: "02:20 PM", "2:20 pm", "02:20PM", "14:20", "02:20 PM - 02:50 PM"
SLOT_TIME_PATTERN = re.compile(
    r"^(\d{1,2}):(\d{2})\s*(AM|PM|am|pm)?(?:\s*-\s*\d{1,2}:\d{2}\s*(?:AM|PM|am|pm)?)?$"
)


def get_scheduled_moment(
    date_str: str, slot_start: str, tz_name: str = DEFAULT_IANA_TIMEZONE
) -> datetime | None:
    """
    Build a timezone-aware datetime from a booking date and slot start time.
    
    Args:
        date_str: ISO date string (YYYY-MM-DD)
        slot_start: Time string in formats like "02:20 PM", "14:20", "02:20 PM - 02:50 PM"
        tz_name: IANA timezone name (default: Asia/Dubai)
    
    Returns:
        Timezone-aware datetime or None if parsing fails
    """
    try:
        # Parse date
        booking_date = datetime.fromisoformat(date_str).date()
        
        # Extract start time from slot (handle range format)
        if " - " in slot_start:
            slot_start = slot_start.split(" - ")[0].strip()
        
        # Parse time
        match = SLOT_TIME_PATTERN.match(slot_start.strip())
        if not match:
            logger.warning(f"Invalid slot format: {slot_start}")
            return None
        
        hour_str, minute_str, meridiem = match.groups()
        hour = int(hour_str)
        minute = int(minute_str)
        
        # Convert to 24-hour format if AM/PM is present
        if meridiem:
            meridiem_upper = meridiem.upper()
            if meridiem_upper == "PM" and hour != 12:
                hour += 12
            elif meridiem_upper == "AM" and hour == 12:
                hour = 0
        
        # Build datetime in the booking timezone
        tz = ZoneInfo(tz_name)
        scheduled_dt = datetime(
            booking_date.year,
            booking_date.month,
            booking_date.day,
            hour,
            minute,
            tzinfo=tz
        )
        
        return scheduled_dt
        
    except Exception as e:
        logger.error(f"Error parsing scheduled moment - date: {date_str}, slot: {slot_start}, error: {e}")
        return None


def parse_slot_start(slot: str) -> str:
    """Extract the start time from a slot string (handles range format)."""
    if " - " in slot:
        return slot.split(" - ")[0].strip()
    return slot.strip()


def is_valid_slot_format(slot: str) -> bool:
    """Check if a slot string matches accepted formats."""
    start = parse_slot_start(slot)
    return bool(SLOT_TIME_PATTERN.match(start))
