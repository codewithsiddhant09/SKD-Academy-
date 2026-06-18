from __future__ import annotations

import re
from datetime import date, datetime

from app.models.schemas import BookingPayload

_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11,
    "december": 12,
}


class BookingAgent:
    REQUIRED_FIELDS = ["salon", "service", "date", "time"]

    @staticmethod
    def parse_date(value: str | None) -> date | None:
        """Parse a supported date string into a date object, or None.

        Supports: "15 July 2026", "2026-07-15", "15/07/2026".
        """
        if not value:
            return None
        text = value.strip()

        m = re.search(
            r"\b(\d{1,2})\s+(January|February|March|April|May|June|July|August|"
            r"September|October|November|December)\s+(\d{4})\b",
            text,
            re.IGNORECASE,
        )
        if m:
            day, month_name, year = int(m.group(1)), m.group(2).lower(), int(m.group(3))
            try:
                return date(year, _MONTHS[month_name], day)
            except ValueError:
                return None

        m = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", text)
        if m:
            try:
                return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except ValueError:
                return None

        m = re.search(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b", text)
        if m:
            try:
                return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
            except ValueError:
                return None

        return None

    def is_past_date(self, value: str | None, today: date | None = None) -> bool:
        """True when `value` parses to a date strictly before today.

        Unparseable / empty dates are NOT considered past (returns False) so
        existing free-text flows are unaffected.
        """
        parsed = self.parse_date(value)
        if parsed is None:
            return False
        reference = today or datetime.now().date()
        return parsed < reference

    def extract_date_and_time(self, text: str, current: BookingPayload) -> BookingPayload:
        """Extract ONLY date and time from user message. Skip name, phone, email."""
        payload = current.model_copy(deep=True)

        # Extract date: support formats like "15 July 2026", "15/07/2026", "2026-07-15"
        date_patterns = [
            r"\b(\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4})\b",
            r"\b(\d{4}-\d{2}-\d{2})\b",
            r"\b(\d{1,2}/\d{1,2}/\d{4})\b",
        ]
        for pattern in date_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                payload.date = match.group(1).strip()
                break

        # Extract time: support formats like "4 PM", "16:00", "4:00 PM", "3:30 PM".
        # The HH:MM pattern must be tried first; otherwise "3:30 PM" would be
        # mis-parsed as "30 PM" by the bare hour pattern.
        time_patterns = [
            r"\b(\d{1,2}:\d{2}\s*(?:AM|PM|am|pm)?)\b",
            r"\b(\d{1,2}\s*(?:AM|PM|am|pm))\b",
        ]
        for pattern in time_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                payload.time = match.group(1).strip()
                break

        return payload

    def extract_fields(self, text: str, current: BookingPayload) -> BookingPayload:
        """Legacy method - now delegates to extract_date_and_time for simplified booking."""
        return self.extract_date_and_time(text, current)

    def missing_fields(self, payload: BookingPayload) -> list[str]:
        return [field for field in self.REQUIRED_FIELDS if not getattr(payload, field)]
